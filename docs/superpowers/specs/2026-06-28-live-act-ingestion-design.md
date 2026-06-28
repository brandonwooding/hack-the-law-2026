# Live act ingestion — CLI agent + in-app endpoint

**Date:** 2026-06-28
**Status:** Approved design, pre-implementation

## Goal

Let a user add a single UK or EU act to the Neo4j knowledge graph from a
natural-language request, two ways:

1. A **Claude Agent SDK** CLI script — `python scripts/add_act.py "add the AI
   Act from the EU"`.
2. A **live "Add act" button** in the RegExplorerSite app, backed by new
   FastAPI endpoints.

Both run the **same deterministic ingestion core**, so behaviour cannot drift
between the two surfaces.

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

### 2. CLI agent — `scripts/add_act.py` (the Claude Agent SDK agent)

One-shot. `python scripts/add_act.py "<request>" [--model MODEL] [--yes]`.

- Loads `.env` (so `ANTHROPIC_API_KEY` + `NEO4J_*` are present).
- Runs an async `ClaudeSDKClient` session, streams assistant text to stdout.
- `ClaudeAgentOptions`:
  - `cwd` = repo root.
  - `model` defaults to `claude-opus-4-8` (override via `--model` or env).
  - tools: `Read, Edit, Bash, Glob, Grep, WebSearch` + Neo4j MCP
    (`mcp-neo4j-cypher`, launched by the script with env from `os.environ`).
  - `mcp_servers`: neo4j stdio server, same command/args as `.codex/config.toml`,
    env pulled from the loaded `.env`.
- **System prompt** teaches the pipeline: resolve jurisdiction + identifier
  (NL -> `ukpga/2010/15` / CELEX, using `WebSearch`/`curl` against
  legislation.gov.uk / EUR-Lex when unknown); run the **targeted** core via
  Bash `legalgraph ingest --jurisdiction <j> --id <identifier> --plan` (fetch
  only, one seed), report the plan, then after confirm
  `legalgraph ingest --jurisdiction <j> --id <identifier> --commit` (load +
  link, also appends the seed to `scope.yaml`); verify with `legalgraph
  validate` + a Neo4j read; print a summary.
- **Permission gate** — `can_use_tool` callback:
  - Auto-allow: `Read`, `Glob`, `Grep`, `WebSearch`, `Edit` of `scope.yaml`,
    Bash `legalgraph ingest ... --plan`, Neo4j read/schema MCP tools.
  - Prompt `y/n` in terminal before: Bash containing `legalgraph ingest`
    with `--commit` (also catches bare `legalgraph load`/`legalgraph link`),
    and `mcp__neo4j__write_neo4j_cypher`.
  - `--yes` flag auto-approves (for scripted/demo runs).
  - Deterministic helper `is_write_command(tool_name, tool_input) -> bool`
    decides this — unit-tested.

The agent calls the core through a thin **`legalgraph ingest` subcommand**
(below), so the CLI agent and the API endpoints share the same targeted
one-seed path — no divergence with the full-corpus `fetch`/`load`/`link`.

### 2a. CLI subcommand — `legalgraph ingest`

Added to [src/legalgraph/cli.py](../../../src/legalgraph/cli.py):

```
legalgraph ingest --jurisdiction <uk|eu> --id <identifier> [--plan | --commit]
                  [--title TITLE] [--concepts C1 C2 ...]
```

- `--plan` (default): `ingest.plan` -> prints the plan JSON. No graph write.
- `--commit`: `ingest.add_seed_to_scope` + `ingest.commit` -> prints stats.

This is the single targeted entrypoint both the agent (via Bash) and a human
can use; the API imports `ingest` directly.

### 3. Live app — backend endpoints in `api.py`

Mirrors the existing `refresh` pattern. Deterministic (no Agent SDK in the web
request).

```python
class IngestPlanRequest(BaseModel):
    jurisdiction: str          # "uk" | "eu"
    query: str                 # free text or an exact id/celex

class IngestCommitRequest(BaseModel):
    jurisdiction: str
    identifier: str            # resolved id/celex from the plan step
    title: str | None = None
    concepts: list[str] = []

@app.post("/ingest/plan")    # resolve id (llm helper if free text) -> ingest.plan
@app.post("/ingest/commit")  # ingest.add_seed_to_scope + ingest.commit
```

- `/ingest/plan` resolves the identifier with a small `llm.py` helper
  (`resolve_act_identifier(query, jurisdiction) -> {identifier, title}`) so the
  box accepts "the AI Act"; if `query` already looks like an id/celex, skip the
  LLM. Then `ingest.plan` and return the plan dict.
- `/ingest/commit` appends the seed to `scope.yaml` and runs `ingest.commit`,
  returns stats.
- Runs synchronously. Acceptable for the hackathon demo; `load`/`link` take
  seconds. **Future upgrade (documented, not built):** background task +
  SSE/WebSocket progress streaming.

### 4. Live app — frontend (RegExplorerSite)

- `addActPlan(jurisdiction, query)` and `addActCommit(...)` in `api.ts`.
- An **"Add act"** button + small modal (jurisdiction toggle + text box),
  placed on the Regimes browser. Flow: type -> Plan -> show
  "I'll add <title> (<identifier>, ~N provisions)" -> Confirm -> Commit ->
  re-fetch `/regimes/all` so the new act appears live. Show a loading state
  during commit.

## Data flow

```
NL request
  -> resolve jurisdiction + identifier   (agent: itself; app: llm helper)
  -> add_seed_to_scope (idempotent)
  -> plan = fetch only (parsed/*.json, NO graph write)
  -> CONFIRM gate        (CLI: terminal y/n;  app: Plan->Confirm two-call)
  -> commit = load + link  (writes to Aura)
  -> verify (validate + Neo4j read)  -> summary
```

## Error handling

- Ambiguous / unresolved identifier: agent reports and exits (re-run with
  specifics); endpoint returns 422 with a message.
- Fetch `NotFound` (404): report and stop **before** any graph write; endpoint
  returns 404.
- `already_present`: surface a warning in plan; commit still allowed (re-load is
  idempotent via existing loader MERGE semantics).

## Testing

- `tests/test_ingest.py`: `add_seed_to_scope` idempotency (append once, skip on
  repeat); `build_seed` / `minimal_scope` shapes (uk `id` vs eu `celex`,
  `cases_per_seed == 0`).
- `tests/test_add_act_agent.py`: `is_write_command` gate — allows fetch/read,
  blocks load/link and `write_neo4j_cypher`.
- `plan`/`commit` against a cached fixture if time allows (the `Fetcher` cache
  makes this offline-repeatable).
- LLM agent loop itself is not unit-tested.

## Dependencies

- Add `claude-agent-sdk` to `pyproject.toml` and install into `.venv`.

## Out of scope (v1)

- Background-task / streaming progress for the app endpoint.
- Multi-act / bulk ingestion, hop expansion from the new act.
- EU citing-case ingestion for added acts (`cases_per_seed` kept at 0).
