# 06 · Deployment / demo & documentation

**Scope:** local installation, live demonstration and documentation.

## Local installation

Maintain [Local setup](../LOCAL_SETUP.md), `.env.example` and the locked dependency file. A teammate installs the project, supplies an authorized model key and starts Streamlit. The workspace starts empty; they create a project, enter their schema/rules and submit SQL.

```bash
uv sync --locked
cp .env.example .env
# Fill MODEL_API_KEY in .env.
uv run --locked streamlit run app.py --server.address 127.0.0.1
```

Use PowerShell's `Copy-Item` on Windows, as documented in the setup guide. Do not distribute filled `.env` files or another member's working database.

## Demonstration preparation

1. Install and run the regression suite on the presentation computer.
2. Create the rehearsal project from the schema and rules in [the presentation guide](../SHOWCASE.md).
3. Run a review with the configured provider; inspect the actual output and latency.
4. Rehearse finding inspection, revision comparison, re-review, decisions and history.
5. Keep the separate historical PDFs available for discussing evaluation or a provider failure.
6. Record the rehearsed live walkthrough for the course's required backup video.

If the provider fails, show the incomplete report and use the dated PDF for explanation. Do not present the PDF as a live response. A demo decision should use the presenter's name and explain their judgment; it does not execute SQL.

## Documentation ownership

Keep commands aligned with the implemented CLI. Update page names and screenshots only when they match the application. Keep technical design in the architecture/workflow documents, live steps in the presentation guide and historical results in PDFs. The six role documents describe assigned responsibilities; confirmed contribution statements are separate.

## Release checks

- A clean installation starts without projects, reports, decisions or saved evaluations.
- Creating a project and submitting SQL works with user-entered context.
- Tests pass without credentials; live checks use an authorized key.
- Source archives contain no keys, working databases, virtual environments or temporary logs.
- Documentation links resolve and local setup works on the intended demonstration computer.

Share the repository, release archive and local setup guide with teammates. Each member uses their role document to prepare their part of the presentation. Hosted deployment is outside the current scope.
