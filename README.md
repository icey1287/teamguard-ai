# TeamGuard AI

TeamGuard reviews MySQL queries against a team's schema and business rules. It checks SQL structure, calls a configured model for business-rule review, presents evidence and proposed changes, and saves human decisions and review history. Submitted SQL is never executed.

## Run locally

```bash
git clone https://github.com/icey1287/teamguard-ai.git
cd teamguard-ai
uv sync --locked
cp .env.example .env
# Set MODEL_API_KEY in .env before starting.
uv run --locked streamlit run app.py --server.address 127.0.0.1
```

Open **http://127.0.0.1:8501**, create a project with your schema and rules, then submit SQL. A new installation starts with an empty workspace. Full business-rule review requires a working model connection. Windows instructions and configuration details are in [Local setup](docs/LOCAL_SETUP.md).

## Features

- Create projects and save versioned schemas and business rules.
- Paste or upload SQL; check syntax, read-only restrictions and schema references.
- Review model findings with exact SQL/rule evidence, proposed SQL and a diff.
- Recheck a proposed change, accept/reject suggestions and search review history.
- Run baseline comparisons on a separate synthetic benchmark dataset.
- Store results locally in SQLite, export results and back up the workspace.

## Documentation

| Document | Contents |
| --- | --- |
| [Local setup](docs/LOCAL_SETUP.md) | Installation, model configuration, startup and backup |
| [System design](docs/ARCHITECTURE.md) | Components, review flow and data model |
| [Presentation guide](docs/SHOWCASE.md) | Live walkthrough and technical explanation |
| [Recorded system demo (MP4)](TeamGuard_AI_Demo.mp4) | 2 min 39 s continuous walkthrough with visible cursor: project setup, SQL review, revisions, decisions, re-review and history |
| [Evaluation report (PDF)](reports/evaluation-2026-11-03.pdf) | Historical benchmark methods, results and failures |
| [Review records (PDF)](reports/reviews-2026-11-03.pdf) | Four historical review records with inputs and findings |

### Six primary roles

Assignments follow the G12 project plan. Confirm actual contributions separately; development was AI-assisted.

| Primary role | Independent role document |
| --- | --- |
| Product manager / user validation | [01 · Product & user validation](docs/roles/01-product-user-validation.md) |
| Workflow & prompt designer | [02 · Workflow & prompts](docs/roles/02-workflow-prompt-design.md) |
| Data / schema & API lead | [03 · Data, schema & API](docs/roles/03-data-schema-api.md) |
| Evaluation / test-case lead | [04 · Evaluation & test cases](docs/roles/04-evaluation-test-cases.md) |
| Application-layer developer | [05 · Application layer](docs/roles/05-application-layer.md) |
| Deployment / demo & documentation | [06 · Local setup, demo & documentation](docs/roles/06-local-setup-demo-documentation.md) |

## Development

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked python manage.py evaluate --arms A
# With a configured model:
uv run --locked python manage.py evaluate --arms A B C --workers 3
```

Tests use temporary workspaces and mock model responses. Benchmark B/C make real API calls. The benchmark definitions are in `benchmarks.py`; they do not create application projects or preload results.

The repository excludes API keys, working databases and virtual environments. Historical results are separate PDF documents, not application data.
