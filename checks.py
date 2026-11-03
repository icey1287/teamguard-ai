"""Parse and inspect MySQL; never connect to or execute against a database."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, SqlglotError
from sqlglot.tokens import TokenType
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from contracts import Issue


def read_schema(schema_sql: str) -> dict[str, dict[str, str]]:
    """Accept a small, unqualified CREATE TABLE schema, without executing DDL."""
    try:
        statements = [s for s in sqlglot.parse(schema_sql, dialect="mysql") if s and not isinstance(s, exp.Semicolon)]
    except SqlglotError as error:
        raise ValueError("The schema must contain valid MySQL CREATE TABLE statements.") from error
    tables = {}
    for statement in statements:
        if not isinstance(statement, exp.Create) or statement.kind != "TABLE":
            raise ValueError("Use CREATE TABLE statements only for the schema.")
        definition = statement.this
        if not isinstance(definition, exp.Schema) or not isinstance(definition.this, exp.Table):
            raise ValueError("Each table must declare its columns explicitly.")
        table = definition.this
        if table.db or table.catalog:
            raise ValueError("Use unqualified table names in this prototype's schema.")
        name = table.name
        if name in tables:
            raise ValueError(f"Duplicate table: {name}.")
        columns = {}
        for column in definition.expressions:
            if isinstance(column, exp.ColumnDef):
                key = column.name.lower()
                if key in columns:
                    raise ValueError(f"Duplicate column in {name}: {column.name}.")
                if column.args.get("kind") is None:
                    raise ValueError(f"Declare a type for {name}.{column.name}.")
                columns[key] = column.args["kind"].sql(dialect="mysql")
        if not columns:
            raise ValueError(f"No columns declared for {name}.")
        tables[name] = columns
    if not tables:
        raise ValueError("Add at least one CREATE TABLE statement.")
    return tables


def check_sql(sql: str, schema_sql: str) -> tuple[Issue, ...]:
    schema = read_schema(schema_sql)
    if not sql.strip():
        return (Issue(severity="high", category="syntax", message="The query is empty.",
                      evidence="Empty input", suggestion="Enter one read-only MySQL query."),)
    try:
        tokens = sqlglot.tokenize(sql, dialect="mysql")
        if any(a.token_type == TokenType.COMMA and b.token_type in {
            TokenType.FROM, TokenType.WHERE, TokenType.GROUP_BY, TokenType.ORDER_BY,
            TokenType.HAVING, TokenType.LIMIT, TokenType.SEMICOLON,
        } for a, b in zip(tokens, tokens[1:])) or (tokens and tokens[-1].token_type == TokenType.COMMA):
            raise ValueError("Trailing comma")
        statements = [s for s in sqlglot.parse(sql, dialect="mysql") if s and not isinstance(s, exp.Semicolon)]
        if any(not select.expressions for statement in statements for select in statement.find_all(exp.Select)):
            raise ValueError("Empty SELECT")
    except (SqlglotError, ValueError, RecursionError):
        return (Issue(severity="high", category="syntax", message="MySQL parsing failed.",
                      evidence=sql, suggestion="Correct the SQL syntax and submit again."),)
    if len(statements) != 1:
        return (Issue(severity="high", category="safety", message="Exactly one query is allowed.",
                      evidence=sql, suggestion="Submit a single SELECT or read-only CTE query."),)
    query = statements[0]
    forbidden = (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock, exp.PropertyEQ)
    if not isinstance(query, exp.Query) or any(isinstance(node, forbidden) for node in query.walk()):
        return (Issue(severity="high", category="safety", message="This is not an allowed read-only query.",
                      evidence=sql, suggestion="Remove writes, commands, output files and locking clauses."),)
    # Restrict functions with known side effects even when embedded in SELECT.
    for node in query.find_all(exp.Func):
        name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
        if name.upper() in {"SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "RELEASE_ALL_LOCKS", "LOAD_FILE"}:
            return (Issue(severity="high", category="safety", message=f"Function {name} is not allowed.",
                          evidence=node.sql(dialect="mysql"), suggestion="Remove the side-effect or file-access function."),)
    issues = []
    # Scope resolution separates physical tables from CTEs and derived tables.
    try:
        for scope in traverse_scope(query):
            for _, source in scope.selected_sources.values():
                if isinstance(source, exp.Table) and (
                    source.db or source.catalog or source.name not in schema
                ):
                    issues.append(Issue(severity="high", category="schema",
                                        message=f"Table is outside the approved schema: {source.sql(dialect='mysql')}.",
                                        evidence=source.sql(dialect="mysql"),
                                        suggestion="Use a table from the selected schema version."))
        if not issues:
            qualify(query.copy(), dialect="mysql", schema=schema, validate_qualify_columns=True,
                    allow_partial_qualification=False)
    except (OptimizeError, SqlglotError) as error:
        issues.append(Issue(severity="high", category="schema", message="A table or column reference cannot be resolved.",
                            evidence=str(error), suggestion="Check column names, aliases and ambiguous references against the schema."))
    return tuple(issues)
