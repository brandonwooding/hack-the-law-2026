# legalgraph

A jurisdiction-agnostic legal knowledge graph over Neo4j. One graph, many
jurisdictions (UK, EU, ...). Built for two-stage retrieval: **Graph RAG** over
the cross-document authority graph, **PageIndex** over each document's internal
structure — but fully navigable *by hand* first.

## The big idea

Two orthogonal structures, kept separate but linked:

1. **Authority/citation graph** — relationships *between* documents (amends,
   cites, made-under, transposes). → Neo4j, this repo.
2. **Internal anatomy** — structure *within* one document (Part → Section →
   Subsection). → the `Provision` tree, which doubles as the PageIndex tree.

Only **adapters** are jurisdiction-specific. Everything downstream of the
canonical format (`src/legalgraph/canonical.py`) is written once and reused:

```
Source API ──► [ADAPTER] ──► Canonical JSON ──► [LOADER/LINKER] ──► Neo4j
  UK / EU      per-jurisdiction   shared schema       shared          shared
```

## Layers modelled

Treaty (EU primary law / constitutions) · Act (primary legislation) ·
StatutoryInstrument (delegated, ministerial) · RegulatoryInstrument (delegated,
regulator-made, **binding** — e.g. FCA Handbook) · Bill · HansardDebate · Case ·
Guidance (soft law) · ExplanatoryNote (interpretive aid).

`legal_force` on each `Provision` (`binding_rule`/`evidential`/`guidance`/
`operative`) lets one document mix binding and non-binding text (FCA R/E/G).
`precedence` ranks authority across layers (and by court level for cases).

### Related regimes

A *regime* is the cluster of instruments governing a domain. `Concept` nodes
(a controlled thesaurus, e.g. EuroVoc) with SKOS `BROADER`/`NARROWER`/`RELATED`
edges make regimes *relatable* — three independent signals combine:

1. **Taxonomic** — documents `ABOUT` related concepts (the SKOS graph).
2. **Cross-jurisdiction** — UK & EU docs tagged with the *same* concept align
   automatically (the cross-border payoff of one graph).
3. **Institutional** — shared `regulator` (ICO / FCA / EDPB ...).

## Pipeline (all stages idempotent, disk-backed)

```
fetch  -> raw/      per-jurisdiction adapter   (source stage, not yet wired)
parse  -> parsed/   per-jurisdiction adapter -> canonical JSON
load   -> Neo4j     shared: nodes (docs + provisions + CONTAINS)
link   -> Neo4j     shared: edges (logs unresolved targets)
validate            shared: integrity + navigation queries
```

Two passes (load then link) so a citation to a not-yet-ingested document never
crashes the load — unresolved targets are reported, telling you what's missing.

## Quickstart

```bash
uv sync
# point at your Neo4j (or rely on the MCP for interactive work)
export NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=...

uv run legalgraph skeleton                       # constraints + indexes
uv run python scripts/build_sample.py            # write tiny sample to parsed/
uv run legalgraph load
uv run legalgraph link
uv run legalgraph validate --citation "Data Protection Act 2018" \
    --provision-id "uk-ukpga-2018-12/s/170"
```

## Scope

`config/scope.yaml` bounds the corpus: seed documents + how many hops of related
material to pull. Keeps demos small — no whole-history ingestion.

## Status

- [x] Canonical schema, Neo4j skeleton, loader (batched), linker, validator
- [x] Concept/EuroVoc taxonomy layer + `regulator` → "related regimes"
- [x] Shared polite fetch layer (rate-limit, retry, cache)
- [x] All 6 UK adapters (legislation.gov.uk + CLML, SI/Bills/Hansard Parliament
      APIs, Find Case Law, GOV.UK) — Online Safety Act regime ingested to Aura:
      195 docs, ~41.8k provisions, all six layers
- [x] Retrieval (Graph RAG + PageIndex) + HTTP API for the UI (see API.md)
- [ ] Claude answer synthesis on /ask (needs LLM key)
- [ ] AMENDS edges (CLML Commentaries) + per-section EXPLAINS
- [ ] EU adapter (CELLAR SPARQL)
- [ ] Vector search (additive, for paraphrase recall)
```
