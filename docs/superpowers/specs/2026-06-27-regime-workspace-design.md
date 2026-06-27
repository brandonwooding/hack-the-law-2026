# Regime Workspace — Design

**Date:** 2026-06-27
**Status:** Approved, pending implementation plan

Connects the existing `legalgraph` graph/retrieval backend to the `RegExplorerSite`
research UI. Turns a free-text "area of law" query into a curatable list of
regulatory **regimes**, lets the chat answer scoped to the regimes the user
confirms, and gives each regime a Claude-drafted, human-editable dossier.

---

## 1. The model: what a Regime is

A **Regime** is a *presentation view* over an anchor `Act`/`Treaty` Document plus
its neighbourhood in the graph — not a new node type.

- **Anchor** = one `Act`-layer (or `Treaty`-layer) Document (e.g. Online Safety
  Act 2023, `ukpga/2023/50`).
- **Neighbourhood** = everything hanging off it via existing edges: SIs
  (`MADE_UNDER`), guidance (`ISSUED_UNDER`), cases (`CONSIDERS`), debates
  (`DEBATED_IN`), explanatory notes (`EXPLAINS`).

Regimes are **derived** from the graph at query time. The graph stays
"real legal sources only." The **one** new persistent artifact is an on-disk
**dossier cache** (§4), which holds editorial prose *about* a regime, kept
deliberately outside the graph.

This matches the seed data in `RegExplorerSite/src/lib/regimes.ts`, where every
"regime" (OSA, UK GDPR/DPA, Communications Act) is a single named statute.

---

## 2. Regime surfacing — `GET /regimes`

Fills the workspace's "Relevant regimes" checklist, replacing `seedRegimes`.

**Request:** `GET /regimes?topic=<free text>&jurisdiction=<UK|EU|...>`

**Logic (blended — reuses both halves of the existing `ask()` bundle):**
1. Run the existing `search_provisions` (fulltext + concept entry points) on
   `topic`.
2. **Roll up** the provision hits to their parent Document via the `CONTAINS`
   path; keep only `Act`/`Treaty`-layer documents (the anchors). Rank anchors by
   `precedence × aggregate hit-score`.
3. **Expand via concepts** (`related_regimes`-style SKOS hop) to catch sibling
   anchors that didn't text-match — e.g. surfacing DPA when the user only typed
   "online safety". These come back flagged as *related* rather than *primary*.
4. Apply the `jurisdiction` filter.

**Response:** a list of **regime cards**:
```jsonc
{
  "regimes": [
    {
      "id": "uk-ukpga-2023-50",        // the anchor Document id
      "name": "Online Safety Act 2023",
      "short_description": "Imposes duties of care on online platforms...",
      "why_surfaced": "primary",        // "primary" (text hit) | "related" (concept hop)
      "anchor_doc_id": "uk-ukpga-2023-50",
      "source_url": "https://www.legislation.gov.uk/ukpga/2023/50"
    }
  ]
}
```
`short_description` is cheap to derive (title + a one-line stub); it is **not**
the dossier. No LLM is needed for this endpoint.

The UI keeps its existing confirm / remove / add affordances over this list.

---

## 3. Scoped chat — `POST /chat`

Once the user has confirmed a subset of regimes, follow-up questions are answered
**scoped to those regimes** (hard filter).

**Request:**
```jsonc
{ "query": "<follow-up question>", "regime_ids": ["uk-ukpga-2023-50", "uk-ukpga-2018-12"] }
```

**Logic:**
1. Retrieve provisions as today, but **hard-filter**: every candidate provision
   must trace (via `CONTAINS` / neighbourhood edges) back to one of the confirmed
   anchor documents. Implemented as a `WHERE` constraint passed into the search
   Cypher — provisions whose anchor is not in `regime_ids` are excluded entirely.
2. Hand the scoped bundle to Claude to synthesize a conversational answer, with
   deep-link citations (every provision already carries a `url`).

**Boundary is literal:** the user sees exactly the scope they drew reflected in
every answer. Deselecting a regime removes it from all subsequent citations.

**Deferred (not in v1):** the "soft boost" variant; the escape-hatch where the
assistant offers to *add* an out-of-scope regime it judged relevant ("that's
outside your confirmed regimes — want me to add X?"). Both are additive layers on
top of this same hard-scoped retrieval, so deferring them costs nothing
structurally.

---

## 4. Regime dossier — `GET` / `PUT /regime/{id}`

The detail screen's six fields: `summary`, `scope`, `process`, `consequence`,
`obligations` (each with a reference), `guidance`.

**Generation strategy — hybrid (structure supplies facts, Claude writes prose):**
1. Deterministically **gather** the regime's grounded subgraph: anchor Act + duty
   provisions + penalty/offence provisions + `CONSIDERS` cases + `ISSUED_UNDER`
   guidance.
2. Claude **arranges** that bundle into the six fields and **may not cite
   anything outside the bundle** (guards against inventing case names — the seed
   data's "Ofcom v. Meridian Social Ltd" is fake and a real user would catch it).
   Every claim traces to a real node; obligations link to real provisions/cases.

**Cache-aside persistence (the part the user specifically wanted):**
- Store: `dataset/dossiers/{regime_id}.json`. Key = **regime id only** (a
  regime's summary/scope/consequence are intrinsic to the statute, independent of
  the topic/session that surfaced it).
- `GET /regime/{id}`: if the JSON exists, return it (no LLM call). If missing,
  synthesize → write JSON → return. So Claude runs **once** per regime; every
  later open is a static file read.
- `PUT /regime/{id}`: **UI edit-in-place.** The detail screen has an edit mode;
  on save it PUTs the changed fields, the backend overwrites the JSON and sets
  `"edited_by_human": true`. A future regenerate must not silently stomp a
  human-edited dossier.

**Why disk JSON over an in-graph node (decided):**
- **Survives graph rebuilds** — `legalgraph load` wipes and reloads Neo4j from
  the adapters; an in-graph dossier would be clobbered on every reimport, losing
  human edits. On-disk dossiers outlive every rebuild.
- **Stays out of the authoritative graph** — editorial prose is not law.
- **Reproducible demo** — commit curated JSONs to git and polished dossiers ship
  with the repo.
- *Fallback if file writes feel flaky:* a one-table SQLite store (`regime_id →
  dossier_json`) gives the same survives-rebuild + write-endpoint story with
  transactional saves. Not chosen for v1; noted as the escape route.

**Dossier JSON shape:**
```jsonc
{
  "regime_id": "uk-ukpga-2023-50",
  "name": "Online Safety Act 2023",
  "summary": "...",
  "scope": "...",
  "process": "...",
  "consequence": "...",
  "obligations": [
    { "text": "Carry out and keep up to date suitable illegal-content risk assessments",
      "reference": "s.9 OSA 2023", "url": "https://www.legislation.gov.uk/ukpga/2023/50/section/9" }
  ],
  "guidance": "...",
  "generated_at": "2026-06-27T...",
  "edited_by_human": false
}
```

---

## 5. Frontend changes (shape unchanged)

The 3-screen flow (Setup → Workspace → Detail) stays exactly as-is. Only the data
source changes:
- `seedRegimes` → `GET /regimes?topic=&jurisdiction=` (Workspace load).
- Chat box → `POST /chat` with the confirmed `regime_ids` (Workspace).
- Detail screen → `GET /regime/{id}` to read; add an edit mode → `PUT /regime/{id}`
  to save.

`RegExplorerSite` is Lovable-connected — keep the branch in a working state, no
history rewrites (per its `AGENTS.md`).

---

## 6. New dependency

`ANTHROPIC_API_KEY` — needed by §3 (chat synthesis) and §4 (dossier drafting).
§2 (surfacing) needs no LLM. This is the answer-synthesis slot deliberately left
open on top of `ask()`.

---

## 7. Out of scope (YAGNI — explicitly deferred)

- No `:Regime` node in the graph.
- No embeddings / vector search (additive later).
- No dossier staleness detection (manual delete-to-regenerate is the invalidation
  story).
- No topic/session-specific dossiers (key is regime id only).
- No soft-boost retrieval; no chat escape-hatch to auto-add out-of-scope regimes.
- No SQLite (named only as the fallback if JSON file writes prove flaky).
