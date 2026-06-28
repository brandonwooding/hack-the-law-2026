# Live Act Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single UK or EU act to the Neo4j graph from a natural-language request, via a Claude Agent SDK CLI script and an "Add a regime" button on the RegExplorerSite Regimes page.

**Architecture:** A deterministic `ingest.py` core does the targeted one-seed fetch/load/link over existing adapters. A `legalgraph ingest` CLI subcommand wraps it. A reusable `agent.py` Agent SDK runner drives the whole thing from NL, exposing a write-permission gate; the CLI passes a terminal-confirm callback, the FastAPI `/regimes/add` endpoint passes none (autonomous). The frontend posts a prompt and refetches the regime list.

**Tech Stack:** Python 3.11+, `claude-agent-sdk`, FastAPI, Neo4j (Aura) via `mcp-neo4j-cypher`, pydantic, React/TanStack Router (RegExplorerSite).

## Global Constraints

- Python `requires-python = ">=3.11"`.
- Reuse existing modules — do NOT reimplement fetch/load/link. Use `Fetcher`, `ADAPTERS`, `io`, `loader.load_documents`, `linker.link_documents`, `db.connect`, `db.load_dotenv`.
- Adapter names: UK = `uk-legislation`, EU = `eu-cellar`.
- Seed shape matches `config/scope.yaml`: UK `{"id": "ukpga/2023/50", ...}`, EU `{"celex": "32022R2065", ...}`.
- Doc id patterns produced by adapters: UK `uk-<type>-<year>-<number>` (e.g. `uk-ukpga-2023-50`), EU `eu-celex-<CELEX>` (e.g. `eu-celex-32022R2065`).
- EU single-act ingest must set `eu.limits.cases_per_seed = 0` so only the act (not citing cases) is fetched.
- Default model: `claude-opus-4-8`.
- Neo4j MCP server launch: `uvx mcp-neo4j-cypher@0.6.0`, env keys `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (read from `os.environ` after `load_dotenv()`).
- `.env` at repo root holds `ANTHROPIC_API_KEY` + `NEO4J_*`.
- Commit message trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- Create `src/legalgraph/ingest.py` — deterministic single-act core.
- Create `src/legalgraph/agent.py` — Agent SDK runner + `is_write_command`.
- Create `scripts/add_act.py` — thin CLI wrapper with terminal confirm.
- Create `tests/test_ingest.py` — core unit tests.
- Create `tests/test_agent.py` — `is_write_command` gate tests.
- Modify `src/legalgraph/cli.py` — add `ingest` subcommand.
- Modify `src/legalgraph/api.py` — add `POST /regimes/add`.
- Modify `pyproject.toml` — add `claude-agent-sdk` dependency.
- Modify `RegExplorerSite/src/lib/api.ts` — add `addRegime`.
- Modify `RegExplorerSite/src/routes/regimes/index.tsx` — "Add a regime" button + modal.

---

### Task 1: Add the `claude-agent-sdk` dependency

**Files:**
- Modify: `pyproject.toml` (the `dependencies` list)

**Interfaces:**
- Produces: `claude_agent_sdk` importable in the project venv.

- [ ] **Step 1: Add the dependency line**

In `pyproject.toml`, inside `dependencies = [ ... ]`, add after the `"anthropic>=0.40",` line:

```toml
    "claude-agent-sdk>=0.1",
```

- [ ] **Step 2: Install into the venv**

Run: `uv sync` (or `.venv/bin/pip install "claude-agent-sdk>=0.1"`)
Expected: resolves and installs `claude-agent-sdk` with no errors.

- [ ] **Step 3: Verify the import works**

Run: `.venv/bin/python -c "import claude_agent_sdk; from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add claude-agent-sdk dependency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Deterministic single-act core — `ingest.py`

**Files:**
- Create: `src/legalgraph/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `Fetcher` (`fetch.py`), `ADAPTERS` (`adapters/__init__.py`), `io.write_document`, `loader.load_documents`, `linker.link_documents`, `db.connect`, `db.load_dotenv`.
- Produces:
  - `JURIS_ADAPTER: dict[str, str]`  (`{"uk": "uk-legislation", "eu": "eu-cellar"}`)
  - `build_seed(jurisdiction: str, identifier: str, title: str | None = None, concepts: list[str] | None = None) -> dict`
  - `minimal_scope(jurisdiction: str, seed: dict) -> dict`
  - `add_seed_to_scope(jurisdiction: str, seed: dict, scope_path: Path | None = None) -> bool`
  - `plan(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict` returning keys `jurisdiction, identifier, title, doc_id, provision_count, already_present`
  - `commit(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict` returning keys `documents, provisions, contains, edges_created, unresolved`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest.py`:

```python
from pathlib import Path

import yaml

from legalgraph import ingest


def test_build_seed_uk():
    seed = ingest.build_seed("uk", "ukpga/2023/50", title="Online Safety Act 2023",
                             concepts=["eurovoc:online-safety"])
    assert seed == {"id": "ukpga/2023/50", "title": "Online Safety Act 2023",
                    "concepts": ["eurovoc:online-safety"]}


def test_build_seed_eu_uses_celex_key():
    seed = ingest.build_seed("eu", "32024R1689", title="AI Act")
    assert seed["celex"] == "32024R1689"
    assert "id" not in seed


def test_minimal_scope_eu_disables_cases():
    seed = ingest.build_seed("eu", "32024R1689")
    scope = ingest.minimal_scope("eu", seed)
    assert scope["eu"]["seeds"] == [seed]
    assert scope["eu"]["limits"]["cases_per_seed"] == 0


def test_minimal_scope_uk_has_single_seed():
    seed = ingest.build_seed("uk", "ukpga/2023/50")
    scope = ingest.minimal_scope("uk", seed)
    assert scope["uk"]["seeds"] == [seed]


def test_add_seed_to_scope_is_idempotent(tmp_path):
    scope_file = tmp_path / "scope.yaml"
    scope_file.write_text(yaml.safe_dump({
        "uk": {"seeds": [{"id": "ukpga/2003/21"}]},
        "eu": {"seeds": [{"celex": "32022R2065"}]},
    }))
    seed = ingest.build_seed("uk", "ukpga/2023/50", title="Online Safety Act 2023")

    added_first = ingest.add_seed_to_scope("uk", seed, scope_path=scope_file)
    added_again = ingest.add_seed_to_scope("uk", seed, scope_path=scope_file)

    data = yaml.safe_load(scope_file.read_text())
    ids = [s["id"] for s in data["uk"]["seeds"]]
    assert added_first is True
    assert added_again is False
    assert ids.count("ukpga/2023/50") == 1
    assert "ukpga/2003/21" in ids  # existing seeds preserved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'legalgraph.ingest'`.

- [ ] **Step 3: Write the implementation**

Create `src/legalgraph/ingest.py`:

```python
"""Targeted single-act ingestion — add ONE UK/EU act to the graph.

Reuses the existing pipeline pieces (adapters -> canonical Documents ->
loader/linker) but bounded to a single seed, so it is fast and safe to run
from the CLI agent or the API. `plan` fetches only (no graph write); `commit`
loads + links.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import io, loader, linker
from .adapters import ADAPTERS
from .adapters import eu as _eu  # noqa: F401  (import registers eu-cellar)
from .adapters import uk as _uk  # noqa: F401  (import registers uk adapters)
from .canonical import Document
from .db import connect, load_dotenv
from .fetch import Fetcher, NotFound

JURIS_ADAPTER = {"uk": "uk-legislation", "eu": "eu-cellar"}
_SEED_KEY = {"uk": "id", "eu": "celex"}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_dataset() -> Path:
    return _root() / "dataset"


def _default_scope() -> Path:
    return _root() / "config" / "scope.yaml"


def _user_agent(scope_path: Path | None = None) -> str:
    scope_path = scope_path or _default_scope()
    if scope_path.exists():
        data = yaml.safe_load(scope_path.read_text()) or {}
        if data.get("user_agent"):
            return data["user_agent"]
    return "legalgraph/0.1"


def build_seed(jurisdiction: str, identifier: str, title: str | None = None,
               concepts: list[str] | None = None) -> dict:
    """A seed dict in scope.yaml's shape. UK keys on `id`, EU on `celex`."""
    if jurisdiction not in _SEED_KEY:
        raise ValueError(f"unknown jurisdiction: {jurisdiction!r}")
    seed: dict = {_SEED_KEY[jurisdiction]: identifier}
    if title:
        seed["title"] = title
    if concepts:
        seed["concepts"] = concepts
    return seed


def minimal_scope(jurisdiction: str, seed: dict) -> dict:
    """In-memory scope with one seed and no expansion. EU disables citing-case
    fetch so only the act itself is collected."""
    block: dict = {"seeds": [seed], "filters": {}}
    if jurisdiction == "eu":
        block["limits"] = {"cases_per_seed": 0, "citations_per_doc": 25}
    return {jurisdiction: block}


def add_seed_to_scope(jurisdiction: str, seed: dict,
                      scope_path: Path | None = None) -> bool:
    """Idempotently append `seed` to scope.yaml. Returns True if added, False if
    an entry with the same id/celex already existed."""
    scope_path = scope_path or _default_scope()
    key = _SEED_KEY[jurisdiction]
    data = yaml.safe_load(scope_path.read_text()) if scope_path.exists() else {}
    data = data or {}
    block = data.setdefault(jurisdiction, {})
    seeds = block.setdefault("seeds", [])
    if any(s.get(key) == seed[key] for s in seeds):
        return False
    seeds.append(seed)
    scope_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return True


def _fetch_docs(jurisdiction: str, seed: dict, dataset: Path) -> list[Document]:
    """Run the jurisdiction's primary adapter for this one seed (cached)."""
    fetcher = Fetcher(dataset / "raw", user_agent=_user_agent())
    adapter = ADAPTERS[JURIS_ADAPTER[jurisdiction]](fetcher)
    docs = adapter.collect(minimal_scope(jurisdiction, seed))
    if not docs:
        raise NotFound(f"no document found for {seed[_SEED_KEY[jurisdiction]]}")
    for d in docs:
        io.write_document(d, dataset / "parsed")
    return docs


def _already_present(doc_id: str) -> bool:
    load_dotenv()
    driver = connect()
    try:
        with driver.session() as s:
            row = s.run(
                "MATCH (d:Document {id: $id}) RETURN count(d) AS n", id=doc_id
            ).single()
            return bool(row and row["n"])
    finally:
        driver.close()


def plan(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict:
    """Fetch only (no graph write). Returns a summary of what would be added."""
    dataset = dataset or _default_dataset()
    docs = _fetch_docs(jurisdiction, seed, dataset)
    act = docs[0]  # both adapters emit the act first
    return {
        "jurisdiction": jurisdiction,
        "identifier": seed[_SEED_KEY[jurisdiction]],
        "title": act.title or act.citation,
        "doc_id": act.id,
        "provision_count": sum(1 for _ in act.all_provisions()),
        "already_present": _already_present(act.id),
    }


def commit(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict:
    """Load + link this one act into the graph. Returns load/link stats."""
    dataset = dataset or _default_dataset()
    docs = _fetch_docs(jurisdiction, seed, dataset)
    load_dotenv()
    driver = connect()
    try:
        load_stats = loader.load_documents(driver, docs)
        link_stats = linker.link_documents(driver, docs)
    finally:
        driver.close()
    return {
        "documents": load_stats["documents"],
        "provisions": load_stats["provisions"],
        "contains": load_stats["contains"],
        "edges_created": link_stats["created"],
        "unresolved": link_stats["unresolved"],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: all 5 tests PASS. (These exercise only the pure helpers — no network/DB.)

- [ ] **Step 5: Commit**

```bash
git add src/legalgraph/ingest.py tests/test_ingest.py
git commit -m "feat: single-act ingestion core (plan/commit)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `legalgraph ingest` CLI subcommand

**Files:**
- Modify: `src/legalgraph/cli.py`

**Interfaces:**
- Consumes: `ingest.plan`, `ingest.commit`, `ingest.build_seed`, `ingest.add_seed_to_scope`.
- Produces: CLI `legalgraph ingest --jurisdiction <uk|eu> --id <identifier> [--plan|--commit] [--title T] [--concepts C ...]` printing JSON.

- [ ] **Step 1: Add the import**

In `src/legalgraph/cli.py`, change the existing line:

```python
from . import io, loader, linker, skeleton, validator
```

to:

```python
from . import io, loader, linker, skeleton, validator, ingest
```

- [ ] **Step 2: Register the subparser**

In `main()`, after the `serve` subparser block (the `ps = sub.add_parser("serve" ...)` lines and its two `add_argument` calls), add:

```python
    pi = sub.add_parser("ingest", help="add ONE act (uk id or eu celex)")
    pi.add_argument("--jurisdiction", required=True, choices=["uk", "eu"])
    pi.add_argument("--id", dest="identifier", required=True,
                    help="UK legislation id (ukpga/2023/50) or EU CELEX (32024R1689)")
    pi.add_argument("--title", default=None)
    pi.add_argument("--concepts", nargs="*", default=None)
    mode = pi.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="fetch only (default)")
    mode.add_argument("--commit", action="store_true", help="load + link into Neo4j")
```

- [ ] **Step 3: Handle the command**

`ingest` does its own DB connection inside `ingest.commit`, so it must NOT be in `_NEEDS_DB`. Leave `_NEEDS_DB` unchanged. Add this branch inside the `try:` block, after the `elif args.cmd == "validate":` block and before the closing `finally:`:

```python
        elif args.cmd == "ingest":
            seed = ingest.build_seed(args.jurisdiction, args.identifier,
                                     title=args.title, concepts=args.concepts)
            if args.commit:
                ingest.add_seed_to_scope(args.jurisdiction, seed)
                result = ingest.commit(args.jurisdiction, seed)
            else:
                result = ingest.plan(args.jurisdiction, seed)
            print(json.dumps(result, indent=2))
```

- [ ] **Step 4: Verify the parser wiring (no network)**

Run: `.venv/bin/python -c "from legalgraph.cli import main; import sys; sys.argv=['legalgraph','ingest','--help']; main(['ingest','--help'])"`
Expected: prints the `ingest` help text listing `--jurisdiction`, `--id`, `--plan`, `--commit`; exits 0.

- [ ] **Step 5: Commit**

```bash
git add src/legalgraph/cli.py
git commit -m "feat: legalgraph ingest subcommand (plan/commit one act)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Agent runner — `agent.py`

**Files:**
- Create: `src/legalgraph/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `claude_agent_sdk` (`ClaudeSDKClient`, `ClaudeAgentOptions`, `AssistantMessage`, `TextBlock`, `ResultMessage`, `PermissionResultAllow`, `PermissionResultDeny`), `db.load_dotenv`.
- Produces:
  - `is_write_command(tool_name: str, tool_input: dict) -> bool`
  - `SYSTEM_PROMPT: str`
  - `async run_agent(prompt: str, *, model: str | None = None, confirm: Callable[[str, dict], Awaitable[bool]] | None = None) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent.py`:

```python
from legalgraph import agent


def test_write_command_neo4j_write():
    assert agent.is_write_command("mcp__neo4j__write_neo4j_cypher", {}) is True


def test_write_command_neo4j_read_is_not_write():
    assert agent.is_write_command("mcp__neo4j__read_neo4j_cypher", {}) is False


def test_write_command_ingest_commit():
    cmd = {"command": "legalgraph ingest --jurisdiction eu --id 32024R1689 --commit"}
    assert agent.is_write_command("Bash", cmd) is True


def test_write_command_ingest_plan_is_not_write():
    cmd = {"command": "legalgraph ingest --jurisdiction eu --id 32024R1689 --plan"}
    assert agent.is_write_command("Bash", cmd) is False


def test_write_command_bare_load_link():
    assert agent.is_write_command("Bash", {"command": "legalgraph load"}) is True
    assert agent.is_write_command("Bash", {"command": "legalgraph link"}) is True


def test_write_command_read_bash_is_not_write():
    assert agent.is_write_command("Bash", {"command": "legalgraph ingest --plan ..."}) is False
    assert agent.is_write_command("Read", {"file_path": "x"}) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'legalgraph.agent'` (or `AttributeError: is_write_command`).

- [ ] **Step 3: Write the implementation**

Create `src/legalgraph/agent.py`:

```python
"""Claude Agent SDK runner for natural-language act ingestion.

One reusable entrypoint, `run_agent`, used by both the CLI script
(scripts/add_act.py) and the FastAPI `/regimes/add` endpoint. The write gate is
centralised in `is_write_command`; the caller decides what happens on a write
via the `confirm` callback (terminal y/n for the CLI; None = autonomous for the
app).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
)

from .db import load_dotenv

DEFAULT_MODEL = "claude-opus-4-8"

#: MCP read/safe tools + built-ins that never need a write prompt.
_ALLOWED_TOOLS = [
    "Read", "Edit", "Glob", "Grep", "WebSearch",
    "mcp__neo4j__get_neo4j_schema",
    "mcp__neo4j__read_neo4j_cypher",
]

SYSTEM_PROMPT = """\
You add a single UK or EU act to a Neo4j legal knowledge graph, end to end.

The repo has a ready pipeline. Use it via Bash — do NOT write fetch/load code.

Steps for every request:
1. Decide jurisdiction: UK or EU.
2. Resolve the stable identifier:
   - UK: legislation id as type/year/number, e.g. ukpga/2023/50. Use WebSearch
     or `curl -s https://www.legislation.gov.uk/...` if you are unsure.
   - EU: the CELEX number, e.g. 32024R1689. Use WebSearch / EUR-Lex if unsure.
   Never guess; verify the identifier before continuing.
3. Plan (fetch only, no graph write):
   `legalgraph ingest --jurisdiction <uk|eu> --id <identifier> --plan`
   Read the JSON: note title, doc_id, provision_count, already_present.
   If already_present is true, say so but you may still proceed.
4. Commit (writes to Neo4j):
   `legalgraph ingest --jurisdiction <uk|eu> --id <identifier> --commit --title "<title>"`
5. Verify with the neo4j tools, e.g. read_neo4j_cypher:
   MATCH (d:Document {id:'<doc_id>'})-[:CONTAINS*]->(p:Provision) RETURN count(p)
6. Finish with a SHORT summary: the act title, identifier, doc_id, and how many
   provisions / edges were added (or why nothing was added).

If you cannot resolve the identifier or the act is not found, stop before any
commit and explain clearly.
"""


def is_write_command(tool_name: str, tool_input: dict) -> bool:
    """True if this tool call writes to the graph (needs the write gate)."""
    if tool_name == "mcp__neo4j__write_neo4j_cypher":
        return True
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if "legalgraph load" in cmd or "legalgraph link" in cmd:
            return True
        if "ingest" in cmd and "--commit" in cmd:
            return True
    return False


def _neo4j_mcp_config() -> dict:
    return {
        "type": "stdio",
        "command": os.environ.get("LEGALGRAPH_UVX", "uvx"),
        "args": ["mcp-neo4j-cypher@0.6.0"],
        "env": {
            k: os.environ[k]
            for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
                      "NEO4J_DATABASE")
            if k in os.environ
        },
    }


async def run_agent(
    prompt: str,
    *,
    model: str | None = None,
    confirm: Callable[[str, dict], Awaitable[bool]] | None = None,
) -> str:
    """Run one ingestion request to completion; return the final summary text."""
    load_dotenv()

    async def gate(tool_name, tool_input, context):
        if is_write_command(tool_name, tool_input):
            if confirm is None or await confirm(tool_name, tool_input):
                return PermissionResultAllow()
            return PermissionResultDeny(message="User declined the write",
                                        interrupt=True)
        return PermissionResultAllow()

    options = ClaudeAgentOptions(
        model=model or DEFAULT_MODEL,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=_ALLOWED_TOOLS,
        mcp_servers={"neo4j": _neo4j_mcp_config()},
        can_use_tool=gate,
        permission_mode="default",
    )

    async def prompts():
        yield {"type": "user",
               "message": {"role": "user", "content": prompt}}

    summary_parts: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.connect(prompts())
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        summary_parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if getattr(msg, "result", None):
                    summary_parts.append(msg.result)
    return "\n".join(p for p in summary_parts if p).strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_agent.py -v`
Expected: all 6 tests PASS. (Tests touch only `is_write_command`; no SDK/network.)

- [ ] **Step 5: Commit**

```bash
git add src/legalgraph/agent.py tests/test_agent.py
git commit -m "feat: Agent SDK runner with write-permission gate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: CLI wrapper — `scripts/add_act.py`

**Files:**
- Create: `scripts/add_act.py`

**Interfaces:**
- Consumes: `agent.run_agent`.
- Produces: executable script `python scripts/add_act.py "<request>" [--model M] [--yes]`.

- [ ] **Step 1: Write the script**

Create `scripts/add_act.py`:

```python
#!/usr/bin/env python
"""One-shot CLI: add a UK/EU act to the graph from a natural-language request.

    python scripts/add_act.py "add the AI Act from the EU"
    python scripts/add_act.py "add the Equality Act 2010 from the UK" --yes

Prompts y/n in the terminal before anything writes to Neo4j, unless --yes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legalgraph import agent  # noqa: E402


def _build_confirm(auto_yes: bool):
    async def confirm(tool_name: str, tool_input: dict) -> bool:
        if auto_yes:
            return True
        desc = tool_input.get("command", tool_name)
        ans = input(f"\n[write] About to run: {desc}\nProceed? [y/N] ").strip().lower()
        return ans in ("y", "yes")
    return confirm


async def _main_async(request: str, model: str | None, auto_yes: bool) -> int:
    confirm = _build_confirm(auto_yes)
    summary = await agent.run_agent(request, model=model, confirm=confirm)
    print("\n=== summary ===")
    print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add a UK/EU act to the graph")
    ap.add_argument("request", help="natural-language request, e.g. 'add the AI Act from the EU'")
    ap.add_argument("--model", default=None)
    ap.add_argument("--yes", action="store_true", help="auto-approve writes")
    args = ap.parse_args(argv)
    return asyncio.run(_main_async(args.request, args.model, args.yes))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it parses args (no agent run)**

Run: `.venv/bin/python scripts/add_act.py --help`
Expected: prints usage with `request`, `--model`, `--yes`; exits 0.

- [ ] **Step 3: Smoke-test a real run (manual, network + DB)**

Run: `.venv/bin/python scripts/add_act.py "add the AI Act from the EU"`
Expected: agent resolves CELEX `32024R1689`, runs `--plan`, prompts `[write] ... --commit ... Proceed? [y/N]`; answer `y`; finishes with a summary naming the AI Act and a provision count. (If the model id `claude-opus-4-8` is unavailable in your CLI, pass `--model claude-sonnet-4-6`.)

- [ ] **Step 4: Commit**

```bash
git add scripts/add_act.py
git commit -m "feat: add_act.py CLI agent for act ingestion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `POST /regimes/add` endpoint

**Files:**
- Modify: `src/legalgraph/api.py`

**Interfaces:**
- Consumes: `agent.run_agent`.
- Produces: `POST /regimes/add` accepting `{"prompt": str}`, returning `{"summary": str}`.

- [ ] **Step 1: Add the import**

In `src/legalgraph/api.py`, change:

```python
from . import retrieval, regimes, llm, dossier
```

to:

```python
from . import retrieval, regimes, llm, dossier, agent
```

- [ ] **Step 2: Add the request model and endpoint**

In `src/legalgraph/api.py`, after the existing `class ChatRequest(BaseModel): ...` block, add:

```python
class AddRegimeRequest(BaseModel):
    prompt: str
```

Then, after the `@app.get("/regimes/all")` handler, add:

```python
@app.post("/regimes/add")
async def add_regime(req: AddRegimeRequest):
    """Run the ingestion agent from a natural-language prompt (autonomous).

    Submitting the prompt is the authorization, so writes are auto-approved
    (confirm=None). Returns the agent's final summary; the UI then refetches
    /regimes/all to show the new regime."""
    if not req.prompt.strip():
        raise HTTPException(422, "prompt must not be empty")
    try:
        summary = await agent.run_agent(req.prompt, confirm=None)
    except Exception as e:  # surface the failure text to the modal
        raise HTTPException(500, f"ingestion failed: {e}")
    return {"summary": summary}
```

- [ ] **Step 3: Verify the app imports and the route is registered**

Run: `.venv/bin/python -c "from legalgraph.api import app; print([r.path for r in app.routes if getattr(r,'path','')=='/regimes/add'])"`
Expected: prints `['/regimes/add']`.

- [ ] **Step 4: Commit**

```bash
git add src/legalgraph/api.py
git commit -m "feat: POST /regimes/add runs the ingestion agent

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Frontend — `addRegime` API + "Add a regime" modal

**Files:**
- Modify: `RegExplorerSite/src/lib/api.ts`
- Modify: `RegExplorerSite/src/routes/regimes/index.tsx`

**Interfaces:**
- Consumes: `POST /regimes/add` -> `{ summary: string }`; existing `fetchAllRegimes`.
- Produces: `addRegime(prompt: string): Promise<{ summary: string }>`; an "Add a regime" button + modal on the Regimes page that refetches the list on success.

- [ ] **Step 1: Add the API client function**

In `RegExplorerSite/src/lib/api.ts`, after the `saveRegime` function, add:

```ts
export async function addRegime(prompt: string): Promise<{ summary: string }> {
  const r = await fetch(`${BASE}/regimes/add`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!r.ok) {
    let detail = `regimes/add ${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return (await r.json()) as { summary: string };
}
```

- [ ] **Step 2: Refactor the regime fetch so it can be re-run**

In `RegExplorerSite/src/routes/regimes/index.tsx`, replace the import line:

```ts
import { fetchAllRegimes, type RegimeCard } from "@/lib/api";
```

with:

```ts
import { addRegime, fetchAllRegimes, type RegimeCard } from "@/lib/api";
```

Then replace the whole `useEffect(() => { ... }, []);` block (currently lines ~32–45) with a reusable loader + effect:

```tsx
  const loadRegimes = useCallback(() => {
    setState("loading");
    return fetchAllRegimes()
      .then((rs) => {
        setRegimes(rs);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, []);

  useEffect(() => {
    void loadRegimes();
  }, [loadRegimes]);
```

And update the React import at the top:

```tsx
import { useCallback, useEffect, useState } from "react";
```

- [ ] **Step 3: Add modal state and submit handler**

In `RegimesIndex`, after the existing `const [jurisdiction, setJurisdiction] = useState("");` line, add:

```tsx
  const [showAdd, setShowAdd] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addSummary, setAddSummary] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || adding) return;
    setAdding(true);
    setAddError(null);
    setAddSummary(null);
    try {
      const { summary } = await addRegime(prompt.trim());
      setAddSummary(summary);
      setPrompt("");
      await loadRegimes();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add regime");
    } finally {
      setAdding(false);
    }
  }
```

- [ ] **Step 4: Add the button to the header**

In `RegExplorerSite/src/routes/regimes/index.tsx`, replace the header block:

```tsx
          <h1 className="font-serif text-xl font-semibold tracking-tight text-ink">
            Regimes
          </h1>
          <p className="mt-0.5 text-xs text-muted-ink">
            Top-level regulatory regimes in the dataset
          </p>
```

with:

```tsx
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="font-serif text-xl font-semibold tracking-tight text-ink">
                Regimes
              </h1>
              <p className="mt-0.5 text-xs text-muted-ink">
                Top-level regulatory regimes in the dataset
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowAdd(true)}
              className="h-9 flex-shrink-0 rounded-[3px] bg-navy px-4 text-sm font-medium text-paper transition-colors hover:bg-ink"
            >
              Add a regime
            </button>
          </div>
```

- [ ] **Step 5: Add the modal markup**

In `RegExplorerSite/src/routes/regimes/index.tsx`, immediately after the opening `<SidebarLayout>` line, add the modal (it overlays the page):

```tsx
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
          <div className="w-full max-w-[480px] rounded-[4px] border border-hairline bg-paper p-6 shadow-lg">
            <h2 className="font-serif text-lg font-semibold text-ink">Add a regime</h2>
            <p className="mt-1 text-xs text-muted-ink">
              Describe the act to add — the agent resolves it and loads it into the graph.
            </p>
            <form onSubmit={handleAdd} className="mt-4 space-y-3">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. add the AI Act from the EU"
                rows={3}
                disabled={adding}
                className="w-full rounded-[3px] border border-hairline bg-paper p-3 text-sm text-ink outline-none focus:border-navy disabled:opacity-60"
              />
              {addError && <p className="text-xs text-red-700">{addError}</p>}
              {addSummary && (
                <p className="whitespace-pre-wrap rounded-[3px] bg-secondary p-3 text-xs text-ink">
                  {addSummary}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  disabled={adding}
                  className="h-9 rounded-[3px] border border-hairline px-4 text-sm text-ink transition-colors hover:bg-secondary disabled:opacity-60"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={adding || !prompt.trim()}
                  className="h-9 rounded-[3px] bg-navy px-4 text-sm font-medium text-paper transition-colors hover:bg-ink disabled:opacity-60"
                >
                  {adding ? "Adding…" : "Add"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
```

- [ ] **Step 6: Verify the frontend builds**

Run: `cd RegExplorerSite && npm run build`
Expected: TypeScript compiles and the build succeeds (no type errors for `addRegime`, `useCallback`, or the new state).

- [ ] **Step 7: Manual end-to-end check**

Start the API (`.venv/bin/python -m legalgraph.cli serve`) and the frontend (`cd RegExplorerSite && npm run dev`). On the Regimes page, click **Add a regime**, enter "add the AI Act from the EU", submit. Expected: spinner → summary text → the AI Act appears in the regimes list after the auto-refetch.

- [ ] **Step 8: Commit**

```bash
git add RegExplorerSite/src/lib/api.ts RegExplorerSite/src/routes/regimes/index.tsx
git commit -m "feat: Add-a-regime modal on the Regimes page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** core (Task 2) ✓; `legalgraph ingest` subcommand (Task 3) ✓; agent runner + gate (Task 4) ✓; CLI wrapper with terminal confirm (Task 5) ✓; agent-backed `/regimes/add` autonomous endpoint (Task 6) ✓; Regimes-page button/modal + refetch (Task 7) ✓; `claude-agent-sdk` dependency (Task 1) ✓; tests for `add_seed_to_scope`/shapes and `is_write_command` ✓.
- **Out of scope (per spec), intentionally absent:** SSE/streaming progress; background tasks; multi-act/bulk; hop expansion; EU citing-case ingestion (`cases_per_seed=0`).
- **Type consistency:** `build_seed` / `minimal_scope` / `add_seed_to_scope` / `plan` / `commit` signatures match between `ingest.py`, the CLI subcommand, and tests. `run_agent(prompt, *, model, confirm)` and `is_write_command(tool_name, tool_input)` match between `agent.py`, `scripts/add_act.py`, `api.py`, and tests. `commit` returns `documents/provisions/contains/edges_created/unresolved`, consistent with `loader.load_documents` (`documents/provisions/contains`) and `linker.link_documents` (`created/unresolved`).
- **Known risk:** `claude-agent-sdk` drives the `claude` CLI; the API host and the CLI both need it on PATH. The default model `claude-opus-4-8` must be available to that CLI (fallback `--model` documented in Task 5).
```
