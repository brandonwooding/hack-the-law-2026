# Regime Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the `legalgraph` graph/retrieval backend to the `RegExplorerSite` UI so a topic query surfaces regulatory **regimes**, the chat answers scoped to confirmed regimes, and each regime gets a Claude-drafted, human-editable dossier cached on disk.

**Architecture:** Three new backend capabilities, each a thin orchestrator over a pure, unit-tested core. (1) Regime surfacing rolls provision search hits up to their anchor `Act`/`Treaty` documents. (2) Scoped chat adds a regime-id WHERE constraint to the existing fulltext search, then Claude synthesizes an answer. (3) Dossiers are generated once via Claude (`messages.parse` over the regime subgraph) and cached as editable JSON on disk (cache-aside). The graph stays read-only law; only dossiers persist outside it.

**Tech Stack:** Python 3.11+, FastAPI, Neo4j (`neo4j` driver), `anthropic` SDK (Claude Opus 4.8), `pydantic` v2, `pytest`. Package manager: `uv`.

## Global Constraints

- Claude model id is exactly `claude-opus-4-8` (copy verbatim; no date suffix).
- Claude calls use `thinking={"type": "adaptive"}` and `output_config={"effort": "medium"}`. Never pass `temperature`, `top_p`, `top_k`, or `budget_tokens` — all 400 on Opus 4.8.
- The `anthropic` import is **lazy** (inside functions), mirroring `db.py`'s `from neo4j import GraphDatabase`, so tests and the `/regimes` endpoint run without the SDK installed or a key present.
- Credentials load via the existing `legalgraph.db.load_dotenv()` (reads project-root `.env`, which already holds `ANTHROPIC_API_KEY` and the `NEO4J_*` vars).
- Anchor layers are exactly `{"Act", "Treaty"}` (the `layer` value is `[l IN labels(d) WHERE l <> 'Document'][0]`).
- A regime's `id` is its anchor Document `id` (e.g. `uk-ukpga-2023-50`).
- Dossiers live at `dataset/dossiers/{regime_id}.json`; cache key is the regime id only.
- All retrieval/regime/dossier core functions are pure or take an injected `driver` / `client` / callable, so they unit-test without a live Neo4j or Anthropic.

---

### Task 1: Project dependencies + test harness

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_harness.py`

**Interfaces:**
- Produces: `FakeDriver` (in `tests/conftest.py`) — a stand-in Neo4j driver used by later tasks. Constructed as `FakeDriver(rows_by_substring: dict[str, list[dict]])`; its `.session(database=...)` returns a context manager whose `.run(cypher, **params)` returns objects exposing `.data()` for the first canned row-list whose substring key appears in `cypher`. Also records `(cypher, params)` tuples on `.calls`.

- [ ] **Step 1: Add dependencies**

Edit `pyproject.toml` — add `anthropic>=0.40` to `dependencies`, and add a dev group below `[project]`:

```toml
dependencies = [
    "pydantic>=2.6",
    "neo4j>=5.20",
    "pyyaml>=6.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "anthropic>=0.40",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]
```

(`httpx` is needed by FastAPI's `TestClient` in Task 6.)

- [ ] **Step 2: Sync the environment**

Run: `uv sync --group dev`
Expected: resolves and installs `anthropic`, `pytest`, `httpx` without error.

- [ ] **Step 3: Write the fake driver**

Create `tests/__init__.py` (empty) and `tests/conftest.py`:

```python
"""Shared test fixtures. FakeDriver lets us unit-test retrieval/regime code
without a live Neo4j — it returns canned rows keyed by a substring of the
Cypher, and records every (cypher, params) call for assertions."""
from __future__ import annotations

from contextlib import contextmanager


class _Row:
    def __init__(self, d: dict):
        self._d = d

    def data(self) -> dict:
        return self._d


class _Session:
    def __init__(self, driver: "FakeDriver"):
        self._driver = driver

    def run(self, cypher: str, **params):
        self._driver.calls.append((cypher, params))
        for substring, rows in self._driver.rows_by_substring.items():
            if substring in cypher:
                return [_Row(r) for r in rows]
        return []


class FakeDriver:
    def __init__(self, rows_by_substring: dict[str, list[dict]] | None = None):
        self.rows_by_substring = rows_by_substring or {}
        self.calls: list[tuple[str, dict]] = []

    @contextmanager
    def session(self, database=None):
        yield _Session(self)

    def close(self):
        pass
```

- [ ] **Step 4: Write a harness smoke test**

Create `tests/test_harness.py`:

```python
from tests.conftest import FakeDriver


def test_fake_driver_returns_canned_rows_by_substring():
    driver = FakeDriver({"queryNodes": [{"id": "x"}]})
    with driver.session() as s:
        rows = s.run("CALL db.index.fulltext.queryNodes('provision_text', $q)", q="abc")
    assert [r.data() for r in rows] == [{"id": "x"}]
    assert driver.calls[0][1] == {"q": "abc"}
```

- [ ] **Step 5: Run it**

Run: `uv run pytest tests/test_harness.py -q`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/__init__.py tests/conftest.py tests/test_harness.py
git commit -m "Add anthropic dep + pytest harness with FakeDriver"
```

---

### Task 2: Regime surfacing (`regimes.py`)

**Files:**
- Create: `src/legalgraph/regimes.py`
- Create: `tests/test_regimes.py`

**Interfaces:**
- Consumes: `legalgraph.retrieval.search_provisions(driver, query, top_k, jurisdiction, database)` returning provision dicts each with a `document` dict (`id`, `citation`, `layer`, `url`, `regulator`) and a numeric `score`.
- Produces:
  - `rollup_regimes(provisions: list[dict], related: list[dict], jurisdiction: str | None = None) -> list[dict]` — pure. Returns regime cards: `{id, name, short_description, why_surfaced, anchor_doc_id, source_url}`. `why_surfaced` is `"primary"` for anchors found via provision hits, `"related"` for anchors found only via the concept hop.
  - `surface_regimes(driver, topic: str, jurisdiction: str | None = None, database: str | None = None) -> list[dict]` — orchestrator returning the same cards.

- [ ] **Step 1: Write the failing test for `rollup_regimes`**

Create `tests/test_regimes.py`:

```python
from legalgraph.regimes import rollup_regimes


def _prov(doc_id, citation, layer, score, url="http://x", regulator="Ofcom"):
    return {"score": score, "document": {
        "id": doc_id, "citation": citation, "layer": layer,
        "url": url, "regulator": regulator}}


def test_rollup_keeps_only_act_and_treaty_layers_ranked_by_score():
    provisions = [
        _prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0),
        _prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 3.0),  # same anchor
        _prov("uk-uksi-2024-1", "Some SI 2024", "StatutoryInstrument", 9.0),  # dropped
    ]
    cards = rollup_regimes(provisions, related=[])
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    card = cards[0]
    assert card["name"] == "Online Safety Act 2023"
    assert card["why_surfaced"] == "primary"
    assert card["anchor_doc_id"] == "uk-ukpga-2023-50"
    assert card["source_url"] == "http://x"


def test_rollup_appends_related_anchors_not_already_primary():
    provisions = [_prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0)]
    related = [{"id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
                "layer": "Act", "url": "http://dpa", "regulator": "ICO"}]
    cards = rollup_regimes(provisions, related)
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50", "uk-ukpga-2018-12"]
    assert cards[1]["why_surfaced"] == "related"


def test_rollup_does_not_duplicate_a_related_anchor_that_is_already_primary():
    provisions = [_prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0)]
    related = [{"id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
                "layer": "Act", "url": "http://x", "regulator": "Ofcom"}]
    cards = rollup_regimes(provisions, related)
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    assert cards[0]["why_surfaced"] == "primary"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_regimes.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'legalgraph.regimes'`.

- [ ] **Step 3: Implement `regimes.py` (rollup + orchestrator)**

Create `src/legalgraph/regimes.py`:

```python
"""Regime surfacing — turns a topic query into a ranked list of regime cards.

A "regime" is a presentation view over an anchor Act/Treaty Document. We reuse
the existing provision search, roll the hits up to their anchor documents, and
blend in topically-related anchors via the concept (SKOS) layer. Pure rollup is
separated from the DB calls so it unit-tests without Neo4j.
"""
from __future__ import annotations

import os

from . import retrieval

ANCHOR_LAYERS = {"Act", "Treaty"}
SHORT_DESC = 140


def _db(database: str | None) -> str | None:
    return database or os.environ.get("NEO4J_DATABASE")


def _card(doc_id, citation, url, why, short_description=""):
    return {
        "id": doc_id,
        "name": citation,
        "short_description": short_description,
        "why_surfaced": why,
        "anchor_doc_id": doc_id,
        "source_url": url,
    }


def rollup_regimes(provisions: list[dict], related: list[dict],
                   jurisdiction: str | None = None) -> list[dict]:
    """Pure: group Act/Treaty-layer provision hits into ranked regime cards,
    then append related anchors not already present."""
    scored: dict[str, dict] = {}
    for p in provisions:
        doc = p.get("document") or {}
        if doc.get("layer") not in ANCHOR_LAYERS:
            continue
        doc_id = doc.get("id")
        if not doc_id:
            continue
        agg = scored.setdefault(doc_id, {"doc": doc, "score": 0.0})
        agg["score"] += float(p.get("score") or 0.0)

    primary = sorted(scored.values(), key=lambda a: a["score"], reverse=True)
    cards = [_card(a["doc"]["id"], a["doc"].get("citation"), a["doc"].get("url"),
                   "primary") for a in primary]

    seen = set(scored)
    for r in related:
        if r.get("layer") not in ANCHOR_LAYERS:
            continue
        doc_id = r.get("id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        cards.append(_card(doc_id, r.get("citation"), r.get("url"), "related"))
    return cards


_RELATED_ANCHORS = """
MATCH (d:Document {id: $id})-[:ABOUT]->(:Concept)-[:RELATED|BROADER]-(:Concept)
      <-[:ABOUT]-(o:Document)
WHERE o.id <> $id AND ('Act' IN labels(o) OR 'Treaty' IN labels(o))
RETURN DISTINCT o.id AS id, o.citation AS citation,
       [l IN labels(o) WHERE l <> 'Document'][0] AS layer,
       o.source_url AS url, o.regulator AS regulator
LIMIT 25
"""


def surface_regimes(driver, topic: str, jurisdiction: str | None = None,
                    database: str | None = None) -> list[dict]:
    """Provision search → anchor rollup, blended with concept-related anchors."""
    provisions = retrieval.search_provisions(
        driver, topic, top_k=25, jurisdiction=jurisdiction, database=database)
    cards = rollup_regimes(provisions, related=[], jurisdiction=jurisdiction)

    related: list[dict] = []
    if cards:
        related = retrieval._run(driver, _RELATED_ANCHORS,
                                 {"id": cards[0]["anchor_doc_id"]}, _db(database))
    return rollup_regimes(provisions, related, jurisdiction)
```

- [ ] **Step 4: Run the unit tests**

Run: `uv run pytest tests/test_regimes.py -q`
Expected: 3 passed.

- [ ] **Step 5: Add an orchestrator test with the fake driver**

Append to `tests/test_regimes.py`:

```python
from tests.conftest import FakeDriver
from legalgraph.regimes import surface_regimes


def test_surface_regimes_blends_provision_hits_and_related_anchors():
    driver = FakeDriver({
        # search_provisions fulltext query
        "queryNodes": [{
            "provision_id": "uk-ukpga-2023-50/s/9", "number": "9", "heading": "Duties",
            "text": "illegal content", "url": "http://p", "score": 5.0,
            "doc_id": "uk-ukpga-2023-50", "document": "Online Safety Act 2023",
            "layer": "Act", "document_url": "http://osa", "regulator": "Ofcom",
            "breadcrumb": ["9"],
        }],
        # related-anchors concept hop
        "RELATED|BROADER": [{
            "id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
            "layer": "Act", "url": "http://dpa", "regulator": "ICO",
        }],
    })
    cards = surface_regimes(driver, "online safety")
    assert cards[0]["id"] == "uk-ukpga-2023-50"
    assert cards[0]["why_surfaced"] == "primary"
    assert any(c["id"] == "uk-ukpga-2018-12" and c["why_surfaced"] == "related"
               for c in cards)
```

(Note: `search_provisions` builds the `document` dict from the flat row keys `doc_id`, `document`, `layer`, `document_url`, `regulator` — see `retrieval.py:57-72`.)

- [ ] **Step 6: Run and commit**

Run: `uv run pytest tests/test_regimes.py -q`
Expected: 4 passed.

```bash
git add src/legalgraph/regimes.py tests/test_regimes.py
git commit -m "Add regime surfacing: roll provision hits up to anchor regimes"
```

---

### Task 3: Regime-scoped provision search (`retrieval.py`)

**Files:**
- Modify: `src/legalgraph/retrieval.py`
- Create: `tests/test_scope.py`

**Interfaces:**
- Produces:
  - `_scope_clause(regime_ids: list[str] | None) -> tuple[str, dict]` — pure. Returns a Cypher `WHERE`-fragment (empty string when no ids) and a params dict (`{}` or `{"regime_ids": [...]}`).
  - `search_provisions(...)` gains a keyword arg `regime_ids: list[str] | None = None` that hard-filters matches to provisions whose parent document is, or hangs off, a confirmed anchor.

- [ ] **Step 1: Write the failing test for `_scope_clause`**

Create `tests/test_scope.py`:

```python
from legalgraph.retrieval import _scope_clause


def test_scope_clause_empty_when_no_regime_ids():
    frag, params = _scope_clause(None)
    assert frag == ""
    assert params == {}
    frag2, params2 = _scope_clause([])
    assert frag2 == ""
    assert params2 == {}


def test_scope_clause_constrains_to_anchor_or_its_neighbourhood():
    frag, params = _scope_clause(["uk-ukpga-2023-50"])
    assert params == {"regime_ids": ["uk-ukpga-2023-50"]}
    assert "d.id IN $regime_ids" in frag
    assert "EXISTS" in frag
    assert "CONTAINS" in frag  # neighbourhood excludes structural edges
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_scope.py -q`
Expected: FAIL with `ImportError: cannot import name '_scope_clause'`.

- [ ] **Step 3: Add `_scope_clause` and wire it into `search_provisions`**

In `src/legalgraph/retrieval.py`, add after `_lucene` (line 36):

```python
def _scope_clause(regime_ids: list[str] | None) -> tuple[str, dict]:
    """A WHERE fragment hard-scoping matched provisions to confirmed regimes:
    the provision's own document is an anchor, or it hangs off one via a
    non-structural edge (SI MADE_UNDER, guidance ISSUED_UNDER, case CONSIDERS).
    Empty when no ids are given."""
    if not regime_ids:
        return "", {}
    frag = ("(d.id IN $regime_ids OR EXISTS { "
            "MATCH (d)-[r2]-(a:Document) "
            "WHERE a.id IN $regime_ids AND type(r2) <> 'CONTAINS' })")
    return frag, {"regime_ids": list(regime_ids)}
```

Then change the `search_provisions` signature and Cypher. Replace the function header (`retrieval.py:39-41`) so it accepts `regime_ids`:

```python
def search_provisions(driver, query: str, top_k: int = 10,
                      jurisdiction: str | None = None, database: str | None = None,
                      regime_ids: list[str] | None = None) -> list[dict]:
```

Inside it, build the WHERE from both the jurisdiction clause and the scope clause. Replace the `cypher = """ ... """` block and the `_run` call (`retrieval.py:42-55`) with:

```python
    scope_frag, scope_params = _scope_clause(regime_ids)
    extra = (" AND " + scope_frag) if scope_frag else ""
    cypher = f"""
    CALL db.index.fulltext.queryNodes('provision_text', $q) YIELD node, score
    WITH node, score ORDER BY score DESC LIMIT $k
    MATCH path = (d:Document)-[:CONTAINS*]->(node)
    WHERE ($jdx IS NULL OR d.jurisdiction = $jdx){extra}
    RETURN node.id AS provision_id, node.number AS number, node.heading AS heading,
           node.text AS text, node.url AS url, score,
           d.id AS doc_id, d.citation AS document,
           [l IN labels(d) WHERE l <> 'Document'][0] AS layer,
           d.source_url AS document_url, d.regulator AS regulator,
           [x IN nodes(path) WHERE x:Provision | x.number] AS breadcrumb
    ORDER BY score DESC
    """
    params = {"q": _lucene(query), "k": top_k, "jdx": jurisdiction, **scope_params}
    rows = _run(driver, cypher, params, database)
```

(Leave the row-shaping loop below unchanged.)

- [ ] **Step 4: Run the scope-clause test**

Run: `uv run pytest tests/test_scope.py -q`
Expected: 2 passed.

- [ ] **Step 5: Add an integration test that scoped search passes regime_ids through**

Append to `tests/test_scope.py`:

```python
from tests.conftest import FakeDriver
from legalgraph.retrieval import search_provisions


def test_search_provisions_threads_regime_ids_into_query_params():
    driver = FakeDriver({"queryNodes": []})
    search_provisions(driver, "duties", regime_ids=["uk-ukpga-2023-50"])
    cypher, params = driver.calls[0]
    assert params["regime_ids"] == ["uk-ukpga-2023-50"]
    assert "d.id IN $regime_ids" in cypher


def test_search_provisions_unscoped_has_no_regime_constraint():
    driver = FakeDriver({"queryNodes": []})
    search_provisions(driver, "duties")
    cypher, params = driver.calls[0]
    assert "regime_ids" not in params
    assert "$regime_ids" not in cypher
```

- [ ] **Step 6: Run and commit**

Run: `uv run pytest tests/test_scope.py -q`
Expected: 4 passed.

```bash
git add src/legalgraph/retrieval.py tests/test_scope.py
git commit -m "Add hard regime scoping to provision search"
```

---

### Task 4: Claude synthesis (`llm.py`)

**Files:**
- Create: `src/legalgraph/llm.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `DossierFields` — a pydantic model with `summary, scope, process, consequence, guidance: str` and `obligations: list[Obligation]` where `Obligation` has `text, reference, url: str`.
  - `draft_dossier(bundle: dict, client=None) -> dict` — calls Claude `messages.parse` to fill `DossierFields`, returns `model_dump()`.
  - `answer(query: str, scoped: dict, client=None) -> str` — calls Claude `messages.create`, returns the answer text.
  - `_dossier_prompt(bundle: dict) -> str` and `_answer_prompt(query, scoped) -> str` — pure prompt builders.
  - `_client()` — lazily constructs `anthropic.Anthropic()` after `db.load_dotenv()`.

- [ ] **Step 1: Write the failing tests (pure prompt builders + injected fake client)**

Create `tests/test_llm.py`:

```python
import types

from legalgraph.llm import (
    DossierFields, _dossier_prompt, _answer_prompt, draft_dossier, answer,
)


def _bundle():
    return {
        "regime_id": "uk-ukpga-2023-50",
        "name": "Online Safety Act 2023",
        "anchor": {"citation": "Online Safety Act 2023"},
        "provisions": [{"number": "9", "heading": "Illegal content duties",
                        "text": "...", "url": "http://p9"}],
        "cases": [{"citation": "R v X", "url": "http://case"}],
        "guidance": [{"citation": "Ofcom code", "url": "http://g"}],
    }


def test_dossier_prompt_grounds_in_the_bundle():
    p = _dossier_prompt(_bundle())
    assert "Online Safety Act 2023" in p
    assert "Illegal content duties" in p
    assert "R v X" in p
    # the grounding instruction must forbid inventing citations
    assert "only" in p.lower()


def test_answer_prompt_includes_query_and_scope():
    scoped = {"regime_names": ["Online Safety Act 2023"],
              "provisions": [{"number": "9", "heading": "Duties",
                              "snippet": "illegal content", "url": "http://p"}]}
    p = _answer_prompt("what are the duties?", scoped)
    assert "what are the duties?" in p
    assert "Online Safety Act 2023" in p


class _FakeMessages:
    def __init__(self, parsed=None, text=None):
        self._parsed, self._text = parsed, text
        self.parse_kwargs = self.create_kwargs = None

    def parse(self, **kwargs):
        self.parse_kwargs = kwargs
        return types.SimpleNamespace(parsed_output=self._parsed)

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self._text)])


class _FakeClient:
    def __init__(self, parsed=None, text=None):
        self.messages = _FakeMessages(parsed, text)


def test_draft_dossier_returns_six_fields_and_uses_opus():
    parsed = DossierFields(summary="s", scope="sc", process="pr",
                           consequence="c", guidance="g", obligations=[])
    client = _FakeClient(parsed=parsed)
    out = draft_dossier(_bundle(), client=client)
    assert out["summary"] == "s"
    assert set(out) >= {"summary", "scope", "process", "consequence",
                        "guidance", "obligations"}
    assert client.messages.parse_kwargs["model"] == "claude-opus-4-8"


def test_answer_returns_text_and_uses_opus():
    client = _FakeClient(text="Ofcom regulates...")
    scoped = {"regime_names": ["OSA"], "provisions": []}
    out = answer("duties?", scoped, client=client)
    assert out == "Ofcom regulates..."
    assert client.messages.create_kwargs["model"] == "claude-opus-4-8"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_llm.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'legalgraph.llm'`.

- [ ] **Step 3: Implement `llm.py`**

Create `src/legalgraph/llm.py`:

```python
"""Claude synthesis — the only place the app calls Anthropic.

Two jobs: draft a regime dossier (structured, grounded in the regime subgraph)
and answer a scoped chat question. The anthropic import is lazy so the rest of
the system (and /regimes) runs without the SDK or a key. Model is Opus 4.8 with
adaptive thinking; no sampling params (they 400 on 4.8).
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from .db import load_dotenv

MODEL = "claude-opus-4-8"
_THINKING = {"type": "adaptive"}
_EFFORT = {"effort": "medium"}


class Obligation(BaseModel):
    text: str
    reference: str
    url: str


class DossierFields(BaseModel):
    summary: str
    scope: str
    process: str
    consequence: str
    obligations: list[Obligation]
    guidance: str


def _client():
    import anthropic
    load_dotenv()
    return anthropic.Anthropic()


def _dossier_prompt(bundle: dict) -> str:
    return (
        "You are a legal-research assistant. Using ONLY the material below, write "
        "a dossier for this regulatory regime. Every obligation reference and any "
        "case you name MUST come from the material — do not invent citations.\n\n"
        f"Regime: {bundle.get('name')}\n"
        f"Anchor: {bundle.get('anchor', {}).get('citation')}\n\n"
        f"Provisions:\n{json.dumps(bundle.get('provisions', []), indent=2)}\n\n"
        f"Cases:\n{json.dumps(bundle.get('cases', []), indent=2)}\n\n"
        f"Guidance:\n{json.dumps(bundle.get('guidance', []), indent=2)}\n\n"
        "Fill: summary, scope, process (how it is regulated/enforced), "
        "consequence (penalties), obligations (each with a real reference + url "
        "from the provisions/cases above), and guidance (practical advice)."
    )


def _answer_prompt(query: str, scoped: dict) -> str:
    names = ", ".join(scoped.get("regime_names", []))
    return (
        "Answer the question using ONLY the provisions below, which are scoped to "
        f"the user's confirmed regimes ({names}). Cite provisions by number and "
        "include their source URLs. If the answer is not in the material, say so.\n\n"
        f"Question: {query}\n\n"
        f"Provisions:\n{json.dumps(scoped.get('provisions', []), indent=2)}"
    )


def draft_dossier(bundle: dict, client=None) -> dict:
    client = client or _client()
    # NB: messages.parse populates output_config.format from output_format; do not
    # also pass output_config here or it would clobber the schema. Effort defaults
    # to high under adaptive thinking, which is fine for a one-time dossier.
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000, thinking=_THINKING,
        output_format=DossierFields,
        messages=[{"role": "user", "content": _dossier_prompt(bundle)}],
    )
    return resp.parsed_output.model_dump()


def answer(query: str, scoped: dict, client=None) -> str:
    client = client or _client()
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, thinking=_THINKING, output_config=_EFFORT,
        messages=[{"role": "user", "content": _answer_prompt(query, scoped)}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_llm.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/legalgraph/llm.py tests/test_llm.py
git commit -m "Add Claude synthesis for dossiers and scoped chat answers"
```

---

### Task 5: Dossier cache-aside store (`dossier.py`)

**Files:**
- Create: `src/legalgraph/dossier.py`
- Create: `tests/test_dossier.py`

**Interfaces:**
- Consumes: `legalgraph.llm.draft_dossier(bundle) -> dict`.
- Produces:
  - `dossier_path(regime_id, dossier_dir) -> Path`
  - `read_dossier(regime_id, dossier_dir) -> dict | None`
  - `write_dossier(data: dict, dossier_dir) -> None` (keys off `data["regime_id"]`)
  - `gather_subgraph(driver, regime_id, database=None) -> dict` — assembles the grounding bundle from the graph.
  - `get_or_build_dossier(regime_id, dossier_dir, gather_fn, draft_fn) -> dict` — cache-aside: read on hit; else `gather_fn(regime_id)` → `draft_fn(bundle)` → persist → return.
  - `save_dossier(regime_id, fields: dict, dossier_dir) -> dict` — merge edited fields, set `edited_by_human=True`, write, return.

- [ ] **Step 1: Write the failing tests (cache-aside + save)**

Create `tests/test_dossier.py`:

```python
from legalgraph.dossier import (
    dossier_path, read_dossier, write_dossier, get_or_build_dossier, save_dossier,
)


def test_read_returns_none_when_absent(tmp_path):
    assert read_dossier("uk-ukpga-2023-50", tmp_path) is None


def test_write_then_read_roundtrips(tmp_path):
    write_dossier({"regime_id": "r1", "summary": "hi"}, tmp_path)
    assert read_dossier("r1", tmp_path)["summary"] == "hi"
    assert dossier_path("r1", tmp_path).exists()


def test_get_or_build_calls_llm_once_then_serves_cache(tmp_path):
    calls = {"gather": 0, "draft": 0}

    def gather(regime_id):
        calls["gather"] += 1
        return {"regime_id": regime_id, "name": "OSA"}

    def draft(bundle):
        calls["draft"] += 1
        return {"summary": "generated", "scope": "", "process": "",
                "consequence": "", "obligations": [], "guidance": ""}

    first = get_or_build_dossier("r1", tmp_path, gather, draft)
    assert first["summary"] == "generated"
    assert first["regime_id"] == "r1"
    assert first["edited_by_human"] is False

    second = get_or_build_dossier("r1", tmp_path, gather, draft)
    assert second["summary"] == "generated"
    assert calls == {"gather": 1, "draft": 1}  # not regenerated


def test_save_marks_human_edited_and_persists(tmp_path):
    get_or_build_dossier(
        "r1", tmp_path, lambda rid: {"regime_id": rid, "name": "OSA"},
        lambda b: {"summary": "auto", "scope": "", "process": "",
                   "consequence": "", "obligations": [], "guidance": ""})
    saved = save_dossier("r1", {"summary": "edited by a human"}, tmp_path)
    assert saved["summary"] == "edited by a human"
    assert saved["edited_by_human"] is True
    assert read_dossier("r1", tmp_path)["summary"] == "edited by a human"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_dossier.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'legalgraph.dossier'`.

- [ ] **Step 3: Implement `dossier.py`**

Create `src/legalgraph/dossier.py`:

```python
"""Regime dossiers — cache-aside on disk.

First open of a regime: gather its grounded subgraph, have Claude draft the six
fields, write JSON. Every later open reads the JSON (no LLM). Files are editable
in the UI (save endpoint sets edited_by_human) and survive graph rebuilds, since
they live outside Neo4j. Cache key = regime id only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from . import retrieval

DOSSIER_DIR = Path(__file__).resolve().parents[2] / "dataset" / "dossiers"


def _db(database: str | None) -> str | None:
    return database or os.environ.get("NEO4J_DATABASE")


def dossier_path(regime_id: str, dossier_dir: Path = DOSSIER_DIR) -> Path:
    safe = regime_id.replace("/", "_")
    return Path(dossier_dir) / f"{safe}.json"


def read_dossier(regime_id: str, dossier_dir: Path = DOSSIER_DIR) -> dict | None:
    path = dossier_path(regime_id, dossier_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_dossier(data: dict, dossier_dir: Path = DOSSIER_DIR) -> None:
    path = dossier_path(data["regime_id"], dossier_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


_SUBGRAPH = """
MATCH (d:Document {id: $id})
OPTIONAL MATCH (d)-[:CONTAINS]->(p:Provision)
WITH d, collect({number: p.number, heading: p.heading,
                 text: left(p.text, 600), url: p.url})[..40] AS provisions
OPTIONAL MATCH (c:Document)-[:CONSIDERS]->(d) WHERE c:Case
WITH d, provisions, collect(DISTINCT {citation: c.citation, url: c.source_url}) AS cases
OPTIONAL MATCH (g:Document)-[:ISSUED_UNDER]->(d) WHERE g:Guidance
RETURN d.citation AS citation, provisions, cases,
       collect(DISTINCT {citation: g.citation, url: g.source_url}) AS guidance
"""


def gather_subgraph(driver, regime_id: str, database: str | None = None) -> dict:
    rows = retrieval._run(driver, _SUBGRAPH, {"id": regime_id}, _db(database))
    row = rows[0] if rows else {}
    return {
        "regime_id": regime_id,
        "name": row.get("citation") or regime_id,
        "anchor": {"citation": row.get("citation")},
        "provisions": [p for p in (row.get("provisions") or []) if p.get("number")],
        "cases": [c for c in (row.get("cases") or []) if c.get("citation")],
        "guidance": [g for g in (row.get("guidance") or []) if g.get("citation")],
    }


def get_or_build_dossier(regime_id: str, dossier_dir: Path,
                         gather_fn, draft_fn) -> dict:
    """Cache-aside: serve the JSON if present, else synthesize once and persist."""
    existing = read_dossier(regime_id, dossier_dir)
    if existing is not None:
        return existing

    bundle = gather_fn(regime_id)
    fields = draft_fn(bundle)
    data = {
        "regime_id": regime_id,
        "name": bundle.get("name", regime_id),
        **fields,
        "generated_at": _dt.datetime.utcnow().isoformat(),
        "edited_by_human": False,
    }
    write_dossier(data, dossier_dir)
    return data


def save_dossier(regime_id: str, fields: dict, dossier_dir: Path) -> dict:
    """UI edit-in-place: merge changed fields, flag as human-edited, persist."""
    data = read_dossier(regime_id, dossier_dir) or {"regime_id": regime_id}
    data.update(fields)
    data["regime_id"] = regime_id
    data["edited_by_human"] = True
    write_dossier(data, dossier_dir)
    return data
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_dossier.py -q`
Expected: 4 passed.

- [ ] **Step 5: Add a gather_subgraph test with the fake driver**

Append to `tests/test_dossier.py`:

```python
from tests.conftest import FakeDriver
from legalgraph.dossier import gather_subgraph


def test_gather_subgraph_shapes_the_bundle():
    driver = FakeDriver({"CONSIDERS": [{
        "citation": "Online Safety Act 2023",
        "provisions": [{"number": "9", "heading": "Duties",
                        "text": "illegal content", "url": "http://p"}],
        "cases": [{"citation": "R v X", "url": "http://case"}],
        "guidance": [{"citation": "Ofcom code", "url": "http://g"}],
    }]})
    bundle = gather_subgraph(driver, "uk-ukpga-2023-50")
    assert bundle["regime_id"] == "uk-ukpga-2023-50"
    assert bundle["name"] == "Online Safety Act 2023"
    assert bundle["provisions"][0]["number"] == "9"
    assert bundle["cases"][0]["citation"] == "R v X"
```

- [ ] **Step 6: Run and commit**

Run: `uv run pytest tests/test_dossier.py -q`
Expected: 5 passed.

```bash
git add src/legalgraph/dossier.py tests/test_dossier.py
git commit -m "Add cache-aside dossier store (disk JSON, UI-editable)"
```

---

### Task 6: HTTP endpoints (`api.py`)

**Files:**
- Modify: `src/legalgraph/api.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `regimes.surface_regimes`, `retrieval.search_provisions`, `llm.answer`, `dossier.{gather_subgraph, get_or_build_dossier, save_dossier, DOSSIER_DIR}`.
- Produces (HTTP):
  - `GET /regimes?topic=&jurisdiction=` → `{"regimes": [card, ...]}`
  - `POST /chat` body `{"query": str, "regime_ids": [str]}` → `{"answer": str, "citations": [provision, ...]}`
  - `GET /regime/{regime_id:path}` → dossier dict (synthesizes on first call)
  - `PUT /regime/{regime_id:path}` body = changed fields → saved dossier dict

- [ ] **Step 1: Write the failing API test**

Create `tests/test_api.py`. It monkeypatches the driver and the LLM/regime functions so no Neo4j or Anthropic is touched:

```python
import legalgraph.api as api
from fastapi.testclient import TestClient
from tests.conftest import FakeDriver


def _client(monkeypatch, tmp_path):
    api._state["driver"] = FakeDriver()
    monkeypatch.setattr(api.dossier, "DOSSIER_DIR", tmp_path)
    return TestClient(api.app)


def test_regimes_endpoint_returns_cards(monkeypatch, tmp_path):
    monkeypatch.setattr(api.regimes, "surface_regimes",
                        lambda *a, **k: [{"id": "r1", "name": "OSA",
                                          "why_surfaced": "primary"}])
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/regimes", params={"topic": "online safety"})
    assert resp.status_code == 200
    assert resp.json()["regimes"][0]["id"] == "r1"


def test_chat_endpoint_scopes_and_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(api.retrieval, "search_provisions",
                        lambda *a, **k: [{"number": "9", "heading": "Duties",
                                          "snippet": "x", "url": "http://p",
                                          "document": {"citation": "OSA"}}])
    monkeypatch.setattr(api.llm, "answer", lambda q, scoped, **k: "Ofcom regulates.")
    client = _client(monkeypatch, tmp_path)
    resp = client.post("/chat", json={"query": "duties?",
                                      "regime_ids": ["uk-ukpga-2023-50"]})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Ofcom regulates."
    assert resp.json()["citations"][0]["number"] == "9"


def test_regime_get_synthesizes_then_put_edits(monkeypatch, tmp_path):
    monkeypatch.setattr(api.dossier, "gather_subgraph",
                        lambda d, rid, **k: {"regime_id": rid, "name": "OSA"})
    monkeypatch.setattr(api.llm, "draft_dossier",
                        lambda bundle: {"summary": "auto", "scope": "", "process": "",
                                        "consequence": "", "obligations": [],
                                        "guidance": ""})
    client = _client(monkeypatch, tmp_path)

    got = client.get("/regime/uk-ukpga-2023-50")
    assert got.status_code == 200
    assert got.json()["summary"] == "auto"
    assert got.json()["edited_by_human"] is False

    put = client.put("/regime/uk-ukpga-2023-50",
                     json={"summary": "human edit"})
    assert put.status_code == 200
    assert put.json()["summary"] == "human edit"
    assert put.json()["edited_by_human"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_api.py -q`
Expected: FAIL (endpoints `/regimes`, `/chat`, `/regime/...` return 404, or attribute errors for `api.regimes`/`api.llm`/`api.dossier`).

- [ ] **Step 3: Add imports and endpoints to `api.py`**

In `src/legalgraph/api.py`, extend the imports (line 16) so the modules are attributes of `api` (needed by the tests' monkeypatching):

```python
from . import retrieval, regimes, llm, dossier
from .db import connect
from pydantic import BaseModel
```

Then add, after the existing `/provision` route (end of file):

```python
@app.get("/regimes")
def list_regimes(topic: str = Query(..., min_length=2),
                 jurisdiction: str | None = None):
    """Surface candidate regimes (anchor Acts + related) for a topic."""
    cards = regimes.surface_regimes(_driver(), topic, jurisdiction=jurisdiction)
    return {"regimes": cards}


class ChatRequest(BaseModel):
    query: str
    regime_ids: list[str] = []


@app.post("/chat")
def chat(req: ChatRequest):
    """Answer a follow-up, hard-scoped to the confirmed regimes."""
    provisions = retrieval.search_provisions(
        _driver(), req.query, top_k=12, regime_ids=req.regime_ids or None)
    names = sorted({(p.get("document") or {}).get("citation")
                    for p in provisions if p.get("document")})
    scoped = {"regime_names": [n for n in names if n], "provisions": provisions}
    return {"answer": llm.answer(req.query, scoped), "citations": provisions}


@app.get("/regime/{regime_id:path}")
def regime(regime_id: str):
    """Dossier for a regime — synthesized + cached on first open."""
    return dossier.get_or_build_dossier(
        regime_id, dossier.DOSSIER_DIR,
        gather_fn=lambda rid: dossier.gather_subgraph(_driver(), rid),
        draft_fn=llm.draft_dossier,
    )


@app.put("/regime/{regime_id:path}")
def edit_regime(regime_id: str, fields: dict):
    """Save UI edits to a dossier (overwrites the JSON, flags human-edited)."""
    return dossier.save_dossier(regime_id, fields, dossier.DOSSIER_DIR)
```

- [ ] **Step 4: Run the API tests**

Run: `uv run pytest tests/test_api.py -q`
Expected: 3 passed.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass (Tasks 1–6).

- [ ] **Step 6: Commit**

```bash
git add src/legalgraph/api.py tests/test_api.py
git commit -m "Add /regimes, /chat, and GET/PUT /regime endpoints"
```

---

### Task 7: Wire the frontend to the API

**Files:**
- Create: `RegExplorerSite/src/lib/api.ts`
- Modify: `RegExplorerSite/src/routes/index.tsx`
- Modify: `RegExplorerSite/src/components/research/WorkspaceScreen.tsx`
- Modify: `RegExplorerSite/src/components/research/RegimeDetailScreen.tsx`

**Interfaces:**
- Consumes the four endpoints from Task 6.
- Produces: `api.ts` with `fetchRegimes(topic, jurisdiction)`, `sendChat(query, regimeIds)`, `fetchRegime(id)`, `saveRegime(id, fields)`.

> **Note:** `RegExplorerSite` is Lovable-connected (`AGENTS.md`) — keep the branch in a working state and do not rewrite pushed history. The existing 3-screen flow and component shapes stay; only the data source changes.

- [ ] **Step 1: Add the API client**

Create `RegExplorerSite/src/lib/api.ts`:

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface RegimeCard {
  id: string;
  name: string;
  short_description?: string;
  why_surfaced?: "primary" | "related";
  source_url?: string;
}

export async function fetchRegimes(topic: string, jurisdiction: string): Promise<RegimeCard[]> {
  const u = new URL(`${BASE}/regimes`);
  u.searchParams.set("topic", topic);
  if (jurisdiction) u.searchParams.set("jurisdiction", jurisdiction);
  const r = await fetch(u);
  if (!r.ok) throw new Error(`regimes ${r.status}`);
  return (await r.json()).regimes;
}

export async function sendChat(query: string, regimeIds: string[]) {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, regime_ids: regimeIds }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return (await r.json()) as { answer: string; citations: unknown[] };
}

export async function fetchRegime(id: string) {
  const r = await fetch(`${BASE}/regime/${id}`);
  if (!r.ok) throw new Error(`regime ${r.status}`);
  return r.json();
}

export async function saveRegime(id: string, fields: Record<string, unknown>) {
  const r = await fetch(`${BASE}/regime/${id}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!r.ok) throw new Error(`save ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Load regimes from the API in `index.tsx`**

In `RegExplorerSite/src/routes/index.tsx`, replace the seed-based `handleStart` (lines 32-38) so it fetches real regimes. Add `import { fetchRegimes, type RegimeCard } from "@/lib/api";` at the top and change `handleStart`:

```tsx
  async function handleStart(j: string, t: string) {
    setJurisdiction(j);
    setTopic(t);
    setNote("");
    setView("workspace");
    try {
      const cards = await fetchRegimes(t, j);
      setRegimes(cards.map((c) => ({
        id: c.id,
        name: c.name,
        shortDescription: c.short_description ?? "",
        confirmed: false,
        summary: "", scope: "", process: "", consequence: "",
        obligations: [], guidance: "",
      })));
    } catch {
      setRegimes([]);
    }
  }
```

- [ ] **Step 3: Verify the dev servers run together**

Start the API: `uv run legalgraph serve --port 8000` (separate terminal).
Start the site: `cd RegExplorerSite && bun run dev`.
Enter a jurisdiction + "online safety" on the setup screen.
Expected: the "Relevant regimes" list populates from `/regimes` (OSA primary + related), not from `seedRegimes`.

- [ ] **Step 4: Wire chat to `/chat` in `WorkspaceScreen.tsx`**

In `handleSend` (lines 54-68), replace the canned assistant reply with a real call. Add `import { sendChat } from "@/lib/api";` and the confirmed ids:

```tsx
  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setMessages((m) => [...m, { id: Date.now(), role: "user", text }]);
    setDraft("");
    const ids = regimes.filter((r) => r.confirmed).map((r) => r.id);
    try {
      const { answer } = await sendChat(text, ids);
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", text: answer }]);
    } catch {
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant",
        text: "Sorry — the assistant is unavailable." }]);
    }
  }
```

- [ ] **Step 5: Load the dossier in `RegimeDetailScreen.tsx`**

The detail screen currently renders the `regime` prop directly. Make it fetch the dossier on open and fall back to the prop. Add at the top:

```tsx
import { useEffect, useState } from "react";
import { fetchRegime, saveRegime } from "@/lib/api";
```

Inside `RegimeDetailScreen`, before the return, add:

```tsx
  const [data, setData] = useState(regime);
  useEffect(() => {
    fetchRegime(regime.id).then((d) => setData({ ...regime, ...d })).catch(() => {});
  }, [regime.id]);
```

Then render from `data` instead of `regime` (replace `regime.summary` → `data.summary`, `regime.scope` → `data.scope`, etc., and `regime.obligations` → `data.obligations`). Keep `regime.name` for the heading or use `data.name`.

- [ ] **Step 6: Verify the detail view and commit**

Click a regime in the workspace.
Expected: first open shows a brief load then the Claude-drafted dossier (real provisions/cases, deep links); re-opening is instant (served from the cached JSON; check `dataset/dossiers/` now contains `{id}.json`).

```bash
cd RegExplorerSite
git add src/lib/api.ts src/routes/index.tsx \
  src/components/research/WorkspaceScreen.tsx \
  src/components/research/RegimeDetailScreen.tsx
git commit -m "Wire UI to legalgraph API: regimes, scoped chat, dossiers"
```

(Add the edit-in-place UI for the dossier — an edit mode on the detail screen that PUTs via `saveRegime` — as a follow-up; the `saveRegime` client and `PUT /regime/{id}` endpoint are already in place.)

---

## Notes for the implementer

- **Run order:** Tasks 1→6 are backend and fully covered by `uv run pytest -q`. Task 7 is frontend and verified by running both dev servers (no automated tests — the site has none).
- **Live smoke test (optional, needs Neo4j + key):** with `.env` populated, `uv run legalgraph serve` then `curl 'localhost:8000/regimes?topic=online+safety'` should return OSA as primary with DPA/Communications as related, matching the proven graph queries in the project memory.
- **Deferred (per the spec, not in this plan):** the chat escape-hatch to auto-add out-of-scope regimes; dossier staleness detection; the in-UI dossier edit mode (endpoint + client are ready).
