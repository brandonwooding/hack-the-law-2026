# Live act ingestion — CLI agent + in-app endpoint

**Date:** 2026-06-28
**Status:** Approved design, pre-implementation

## Goal

Let a user add a single UK or EU act to the Neo4j knowledge graph from a
natural-language request, two ways:

1. A **Claude Agent SDK** CLI script — `python scripts/add_act.py "add the AI
   Act from the EU"`.
2. An **"Add a regime" button** on the RegExplorerSite Regimes page: submit a
   free-text prompt that runs the same agent server-side.

Both surfaces drive the **same agent runner** over the **same deterministic
ingestion core**, so behaviour cannot drift between them.

## Background — the existing pipeline

Adding an act today is manual:

1. Add a seed to [config/scope.yaml](../../../config/scope.yaml) — UK by
   `id: type/year/number` (e.g. `ukpga/2010/15`), EU by `celex` (e.g.
   `32024R1689`).
2. Run the CLI ([src/legalgraph/cli.py](../../../src/legalgraph/cli.py)):
   `legalgraph fetch` -> `load` -> `link` -> `validate`.

Key facts confirmed from the code:

- Adapters are registered by name: **`uk-legislation`** (primary UK acts, via
  `clml`) and **`eu-cellar`** (EU acts by CELEX). Each `collect(scope)` iterates
  `scope[juris]["seeds"]`.
- `uk-legislation` for one seed fetches the act + its explanatory notes only
  (no expansion in `collect`).
- `eu-cellar` for one seed fetches the act, and *also* citing cases up to
  `eu.limits.cases_per_seed` (default 8). Setting `cases_per_seed: 0` limits it
  to just the act — what we want for a targeted single-act add.
- So a **minimal in-memory scope with one seed** ingests exactly one act
  without touching `scope.yaml` expansion settings.
- Neo4j is Aura (~42k nodes). Creds + `ANTHROPIC_API_KEY` are in `.env`
  (`db.load_dotenv` pattern). The Neo4j MCP runs via
  `uvx mcp-neo4j-cypher@0.6.0` (see `.codex/config.toml`).
- Precedent for "refresh from the app" already exists:
  `POST /regime/{id}/regulatory-guidance/refresh` in
  [src/legalgraph/api.py](../../../src/legalgraph/api.py) +
  `refreshRegulatoryGuidance()` in
  [RegExplorerSite/src/lib/api.ts](../../../RegExplorerSite/src/lib/api.ts).

## Architecture

Three components plus frontend wiring. The shared core is the safety boundary
("plan -> confirm -> commit").

### 1. Shared core — `src/legalgraph/ingest.py` (deterministic, no LLM)

Wraps existing `Fetcher`, `ADAPTERS`, `io`, `loader`, `linker`, `connect`. No
new pipeline logic — single-act orchestration only.

```python
JURIS_ADAPTER = {"uk": "uk-legislation", "eu": "eu-cellar"}

def build_seed(jurisdiction: str, identifier: str,
               title: str | None = None, concepts: list[str] | None = None) -> dict:
    """Return a seed dict in the shape scope.yaml uses.
    uk -> {"id": identifier, ...}; eu -> {"celex": identifier, ...}."""

def minimal_scope(jurisdiction: str, seed: dict) -> dict:
    """An in-memory scope with one seed and no expansion.
    eu sets limits.cases_per_seed = 0 so only the act is fetched."""

def add_seed_to_scope(jurisdiction: str, seed: dict,
                      scope_path: Path = DEFAULT_SCOPE) -> bool:
    """Idempotently append seed to scope.yaml (skip if id/celex already present).
    Returns True if added. Keeps future full re-runs inclusive of this act."""

def plan(jurisdiction: str, seed: dict, dataset: Path = DEFAULT_DATASET) -> dict:
    """Run FETCH ONLY for the one seed (minimal_scope). Writes parsed JSON to
    dataset/parsed. Touches NO graph. Returns:
        {"jurisdiction", "identifier", "title", "doc_id",
         "provision_count", "already_present": bool}."""

def commit(jurisdiction: str, seed: dict, dataset: Path = DEFAULT_DATASET) -> dict:
    """Run LOAD + LINK for the fetched doc(s). Returns loader/linker stats:
        {"documents", "provisions", "contains", "edges_created", "unresolved"}."""
```

`already_present` is determined by a Neo4j read of the doc id before load, so the
UI/agent can warn "this act is already in the graph".

### 2. Agent runner — `src/legalgraph/agent.py` (the Claude Agent SDK agent)

The single reusable agent, used by **both** the CLI script and the app endpoint.

```python
async def run_agent(prompt: str, *, model: str | None = None,
                    confirm: Callable[[str, dict], Awaitable[bool]] | None = None
                    ) -> str:
    """Run one ingestion request to completion. Returns the agent's final
    summary text. `confirm` is the write-gate decision hook:
      - CLI passes a terminal y/n prompt.
      - App passes None -> autonomous (writes auto-approved)."""
```

- Loads `.env` (so `ANTHROPIC_API_KEY` + `NEO4J_*` are present).
- `ClaudeAgentOptions`:
  - `cwd` = repo root.
  - `model` defaults to `claude-opus-4-8` (override via arg/env).
  - tools: `Read, Edit, Bash, Glob, Grep, WebSearch` + Neo4j MCP
    (`mcp-neo4j-cypher`, launched with env from `os.environ`, same command/args
    as `.codex/config.toml`).
- **System prompt** teaches the pipeline: resolve jurisdiction + identifier
  (NL -> `ukpga/2010/15` / CELEX, using `WebSearch`/`curl` against
  legislation.gov.uk / EUR-Lex when unknown); run the **targeted** core via
  Bash `legalgraph ingest --jurisdiction <j> --id <identifier> --plan` (fetch
  only, one seed), report the plan, then `legalgraph ingest --jurisdiction <j>
  --id <identifier> --commit` (load + link, also appends the seed to
  `scope.yaml`); verify with `legalgraph validate` + a Neo4j read; end with a
  concise summary (title, identifier, provisions/edges added).
- **Permission gate** — `can_use_tool` callback driven by `confirm`:
  - Auto-allow always: `Read`, `Glob`, `Grep`, `WebSearch`, `Edit` of
    `scope.yaml`, Bash `legalgraph ingest ... --plan`, Neo4j read/schema MCP.
  - "Write" actions (Bash `legalgraph ingest --commit`, bare `legalgraph
    load`/`link`, `mcp__neo4j__write_neo4j_cypher`) -> if `confirm` is None,
    auto-approve; else `await confirm(tool_name, tool_input)`.
  - Deterministic helper `is_write_command(tool_name, tool_input) -> bool`
    classifies write vs read — unit-tested.
- Collects assistant text and returns the final summary (for the app) while also
  yielding/printing it (for the CLI).

### 2a. CLI wrapper — `scripts/add_act.py`

Thin one-shot wrapper around `agent.run_agent`:
`python scripts/add_act.py "<request>" [--model MODEL] [--yes]`.

- Passes a `confirm` that prompts `y/n` in the terminal before each write
  (so nothing hits Aura unattended); `--yes` makes `confirm` always-true.
- Streams the agent's text to stdout as it runs.

### 2b. CLI subcommand — `legalgraph ingest`

Added to [src/legalgraph/cli.py](../../../src/legalgraph/cli.py):

```
legalgraph ingest --jurisdiction <uk|eu> --id <identifier> [--plan | --commit]
                  [--title TITLE] [--concepts C1 C2 ...]
```

- `--plan` (default): `ingest.plan` -> prints the plan JSON. No graph write.
- `--commit`: `ingest.add_seed_to_scope` + `ingest.commit` -> prints stats.

This is the single targeted entrypoint both the agent (via Bash) and a human
can use; the API imports `ingest` directly.

### 3. Live app — backend endpoint in `api.py` (agent-backed)

The prompt from the Regimes page goes straight to the agent. Mirrors the
existing `refresh` pattern in shape; runs the Agent SDK runner server-side.

```python
class AddRegimeRequest(BaseModel):
    prompt: str                # free text, e.g. "add the AI Act from the EU"

@app.post("/regimes/add")
async def add_regime(req: AddRegimeRequest):
    summary = await agent.run_agent(req.prompt, confirm=None)  # autonomous
    return {"summary": summary}
```

- Endpoint is `async` and `await`s `agent.run_agent` directly (FastAPI handles
  the event loop). `confirm=None` -> writes auto-approved (the UI submission is
  the authorization).
- **Synchronous** from the client's view: returns the agent's final summary when
  done (the agent loop can take 30s–2min). Frontend shows a spinner.
- `ANTHROPIC_API_KEY` + `NEO4J_*` come from the already-loaded `.env`.
- **Note:** the Python `claude-agent-sdk` drives the `claude` CLI under the hood,
  so the server host must have it available — fine for the local hackathon
  setup. Flag in the plan.
- **Future upgrade (documented, not built):** SSE/WebSocket so the agent's steps
  stream into the modal live.

### 4. Live app — frontend (RegExplorerSite)

- `addRegime(prompt: string)` in `api.ts` -> `POST /regimes/add`, returns
  `{ summary }`.
- On the **Regimes page**: an **"Add a regime"** button -> modal with a prompt
  textarea ("e.g. add the AI Act from the EU") + Submit. Flow: type prompt ->
  Submit -> spinner while the agent runs -> show the returned summary ->
  re-fetch `/regimes/all` so the new regime appears in the list. Handle errors
  by showing the message in the modal.

## Data flow

```
Regimes page prompt  /  CLI request
  -> agent.run_agent(prompt, confirm)
       -> resolve jurisdiction + identifier  (WebSearch / curl)
       -> legalgraph ingest --plan   = fetch only (parsed/*.json, NO graph write)
       -> WRITE GATE                  (CLI: terminal y/n;  app: auto-approve)
       -> legalgraph ingest --commit = add_seed_to_scope + load + link (Aura)
       -> verify (validate + Neo4j read)
  -> final summary  -> stdout (CLI) / JSON (app, then refetch /regimes/all)
```

## Error handling

- Ambiguous / unresolved identifier: agent reports it in its summary and stops
  before any write; the app surfaces that text in the modal.
- Fetch `NotFound` (404): `legalgraph ingest --plan` fails, agent stops **before**
  any graph write and reports it.
- `already_present`: agent notes it; re-running commit is safe (loader MERGE
  semantics are idempotent).
- App endpoint wraps `run_agent` in try/except -> HTTP 500 with the error
  message so the modal can display it.

## Testing

- `tests/test_ingest.py`: `add_seed_to_scope` idempotency (append once, skip on
  repeat); `build_seed` / `minimal_scope` shapes (uk `id` vs eu `celex`,
  `cases_per_seed == 0`).
- `tests/test_agent.py`: `is_write_command` gate — classifies `legalgraph
  ingest --plan` / reads as allowed, and `--commit` / `legalgraph load|link` /
  `write_neo4j_cypher` as writes.
- `plan`/`commit` against a cached fixture if time allows (the `Fetcher` cache
  makes this offline-repeatable).
- The LLM agent loop and the `/regimes/add` endpoint are not unit-tested
  (manual demo verification).

## Dependencies

- Add `claude-agent-sdk` to `pyproject.toml` and install into `.venv`.

## Out of scope (v1)

- Background-task / streaming progress for the app endpoint.
- Multi-act / bulk ingestion, hop expansion from the new act.
- EU citing-case ingestion for added acts (`cases_per_seed` kept at 0).
