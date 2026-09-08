# Proofbound

A local-first operations console with approval gates, source excerpts, a SQLite action ledger, downloadable drafts and diffs, and editable source-linked memory.

## Run it

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Morsmek/proofbound.git
cd proofbound
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
proofbound serve --port 8000
```

Open http://localhost:8000. On Windows activate with `.venv\Scripts\activate`.

Or run `docker compose up --build -d`. The dashboard is published on **127.0.0.1:8000**. SQLite data persists in the `proofbound_data` volume, and workspace files persist in `./workspace_sandbox`.

## Working operations

Enter these in the dashboard or pass them to `proofbound run 'INTENT'`:

| Intent | Result |
| --- | --- |
| `Research https://example.com https://www.python.org` | Fetches both allowed URLs and records actual source excerpts. Network failures are failed steps, never invented citations. |
| `Find file config.txt` | Searches filenames inside the configured workspace. |
| `Write file config.txt content: status=active` | Requests approval, writes the literal content, and records the diff and original content. |
| `Patch file config.txt replace "active" with "paused"` | Requests approval and replaces matching text; fails if the target is absent. |
| `Draft email to person@example.com body: Here is the weekly update.` | Requests approval and stages a downloadable email. It does not send it. |

Review the exact tool parameters before approving. Low-risk plans execute automatically; other plans wait for a decision. The console displays failures, artifacts, and pending memory proposals. Accept a proposal to populate the Memory tab; edit, delete, or roll back accepted facts there. Open previous runs from the Ledger tab to review their complete results or resume an approved, unexecuted run.

**Restore original file** rolls back a completed write, including removing files created by that write. It refuses to overwrite content changed after execution. Original text is stored in the ledger, so the ledger should receive the same access protection as workspace files.

The planner is deterministic and supports the operations above. It is **not** a general LLM agent. LLM provider settings are reserved and currently do not invoke models. Research requires explicit URLs; general search, autonomous code generation, email transmission, and destructive shell commands are not implemented. Unsupported requests fail visibly.

## Configuration

| Environment variable | Default |
| --- | --- |
| `PROOFBOUND_STORAGE_DIR` | `~/.proofbound` |
| `PROOFBOUND_DB_PATH` | `<storage directory>/proofbound.db` |
| `PROOFBOUND_WORKSPACE_ROOT` | `./workspace_sandbox` |
| `PROOFBOUND_HOST` | `127.0.0.1` |
| `PROOFBOUND_PORT` | `8000` |
| `PROOFBOUND_AUTO_APPROVE_LOW_RISK` | `true` |
| `PROOFBOUND_API_KEY` | Empty, for local use |
| `PROOFBOUND_DOMAIN_ALLOWLIST` | JSON array of approved domains; see `proofbound/config.py` |

For example, `PROOFBOUND_DOMAIN_ALLOWLIST='["example.com","python.org"]'`.

Before exposing the backend remotely, set `PROOFBOUND_API_KEY` and use HTTPS. Enter that key in the dashboard's Access key field; it stays in the page's memory. This is a single-user service: `user_id` is an audit label, not a tenant boundary. The API and downloads require the configured bearer key; `/api/health` remains public.

## Cloudflare Pages

The repository includes a Pages API proxy, **not a separate simulated backend**. Python, SQLite and workspace operations must run on a persistent Python/Docker host.

1. Run the backend on a persistent host with HTTPS and `PROOFBOUND_API_KEY` configured.
2. Deploy the Pages project using `wrangler pages deploy proofbound/web/static` from the repository root. The `functions/` directory supplies API routes.
3. Configure the Pages environment variable `PROOFBOUND_BACKEND_URL` with the backend's HTTPS origin and redeploy.
4. Enter the backend access key in the dashboard.

The proxy forwards browser authorization to the backend and disables API caching. Without a backend URL it returns a clear 503 setup error. This repository does not provision a hosting account, domain, TLS certificate or persistent backend automatically.

## Validation

```bash
python -m pytest -q
node --test tests/proxy.test.mjs
proofbound benchmark
python -m proofbound.benchmark.suite
```

The ten benchmark checks use **explicit deterministic HTTP fixtures and temporary databases/workspaces**. They verify core contracts, not live research quality or comprehensive prompt-injection resistance. CI runs Python tests on 3.10 and 3.12, builds the package and Docker image, and checks the Pages proxy.

The ledger's replay command verifies stored event payload hashes; it does not rerun side effects or provide an externally anchored, tamper-proof log. Event IDs now include the run ID, preventing later runs from overwriting earlier events. Events already lost under older versions cannot be reconstructed.

Execution claims prevent concurrent requests from executing the same run twice. Completed runs return their recorded result when execution is retried. After a process crash, a retained claim intentionally blocks automatic retries: inspect the workspace and the run's events before any manual recovery. Do not remove a claim while its worker is running.

## CLI

```bash
proofbound run 'Draft email to person@example.com body: Hello' --yes
proofbound audit list
proofbound audit show --run-id RUN_ID
proofbound audit replay --run-id RUN_ID
proofbound memory list
proofbound memory rollback --fact-id FACT_ID
```

`--yes` approves pending plans; it never overrides blocked commands. File restoration, proposal acceptance and artifact downloads are available through the dashboard and documented endpoints in `/docs`.

MIT License. See [LICENSE](LICENSE).
