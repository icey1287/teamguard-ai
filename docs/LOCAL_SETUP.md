# Local setup for team members

This guide runs TeamGuard on your own computer. It does not cover cloud or server deployment.

## 1. Requirements and download

Use Python **3.12** and `uv`. The project requires `>=3.12,<3.13`; `uv` can obtain a compatible interpreter if one is missing. Follow the [official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/). Git is needed only for cloning; the GitHub release ZIP also works.

```bash
git clone https://github.com/icey1287/teamguard-ai.git
cd teamguard-ai
uv sync --locked
```

If the repository is private, sign into the GitHub account that has been granted access. For a downloaded ZIP, extract it, open a terminal in the extracted `teamguard-ai` folder and run `uv sync --locked`. Run all commands below from that folder. First-time installation needs internet access; the virtual environment is recreated locally and is not in the ZIP.

## 2. Configure the model

macOS / Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in your editor. Set `MODEL_API_KEY` to an authorized key. The example uses the endpoint and model tested for this release:

```dotenv
MODEL_BASE_URL=https://discovery-api.intern-ai.org.cn/v1
MODEL_NAME=deepseek-v4.1-flash-1017
MODEL_API_KEY=YOUR_OWN_KEY
MODEL_TIMEOUT=90
MODEL_THINKING=disabled
MODEL_MAX_TOKENS=4096
MODEL_INPUT_RATE=
MODEL_OUTPUT_RATE=
MODEL_CACHED_RATE=
```

Do not commit or share the filled-in file. Credentials from another member's computer are not bundled. The model provider receives SQL, approved schema and rules after structural checks pass. For a rehearsal, use the synthetic inputs in the presentation guide.

For another compatible provider, change its base URL, model and key together. Leave `MODEL_THINKING` blank unless that provider supports the `thinking.type` parameter. The client appends `/chat/completions` unless it is already present in the base URL.

Pricing fields are optional **rates per one million tokens**, in one consistent currency. Blank means unknown, not zero. Token counts can be shown without knowing prices.

Configuration precedence is process environment variables, then the file selected by `TEAMGUARD_MODEL_ENV_FILE`, otherwise the project's `.env`. A stale `MODEL_NAME` or `MODEL_API_KEY` exported in your terminal overrides the file. Configuration is not borrowed from other course projects.

## 3. Start, stop and restart

```bash
uv run --locked streamlit run app.py --server.address 127.0.0.1
```

Keep the terminal open. Stop with **Ctrl+C**. If port 8501 is occupied, use `--server.port 8502` and open http://127.0.0.1:8502. Restart the process after updating Python source or changing configuration.

Open **http://127.0.0.1:8501**. The new workspace is empty. Create a project in **Project & rules**: enter a name, paste/upload MySQL `CREATE TABLE` statements, and add one business rule per line. Save, open **Submit SQL**, select the project/version and submit your query. Inspect the findings and revision, then record your decision. History contains only reviews submitted in this workspace.

The command binds to your own computer. Each teammate has a separate local database.

## 4. Local files and backup

`data/workspace.sqlite3` stores projects, version snapshots, reports, decisions and evaluation runs. Closing the browser does not remove it. Different checkouts and different `TEAMGUARD_DB` paths are separate workspaces; computers do not synchronize automatically.

```bash
uv run --locked python manage.py backup --output data/backup-before-update.sqlite3
```

Choose a new filename each time. The SQLite backup API produces a consistent copy even if the app is open, and an existing backup is never overwritten. For restoration, stop the app, preserve the current database under another filename, copy the chosen backup to `data/workspace.sqlite3`, then restart. If using `TEAMGUARD_DB`, restore to that configured path instead. Keep backups outside Git; they may contain future user inputs.

## 5. Checks and evaluation

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked python manage.py evaluate --arms A
uv run --locked python manage.py results
```

The tests use temporary databases and mocked model responses. They do not modify your workspace or call the model. The browser Evaluation page also supports selecting strategies and case groups. A real A/B/C run is optional, takes several minutes and requires a working key:

```bash
uv run --locked python manage.py evaluate --arms A B C --workers 3
```

Use `--workers 1` if your provider limits concurrent requests. Individual timings exclude worker queue waiting.

## 6. Troubleshooting

| Symptom | Action |
| --- | --- |
| `uv` not found | Install uv, then open a new terminal. |
| Unsupported Python version | Run `uv python install 3.12`, then `uv sync --locked`. |
| Model not configured | Fill `.env`; check terminal environment overrides; restart. |
| HTTP 401 / 403 | Check key validity and permission to use that model. |
| HTTP 404 | Check the exact model name and API base URL. |
| HTTP 429 | Wait and retry; reduce benchmark concurrency. |
| Timeout or invalid evidence | Use the report's retry action. The failed attempt remains in history. |
| Empty history on another machine | Expected for a new workspace. Create a project and submit a query; computers do not share a database. |
| Stale page after source update | Stop and restart Streamlit, then refresh the browser. |
| Workspace cannot be opened | Verify `TEAMGUARD_DB`, directory permissions and disk space; preserve the existing file before attempting recovery. |

Installation follows the official [uv locked-sync behavior](https://docs.astral.sh/uv/concepts/projects/sync/). Model availability and response time depend on the provider.
