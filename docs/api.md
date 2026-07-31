# legalgraph API (for the UI)

Two-stage retrieval over the legal knowledge graph (Graph RAG + PageIndex),
returned as JSON. Retrieval-only today; a natural-language `answer` field will be
added (Claude) without changing this shape. Every result carries a source link.

## Run

```bash
uv run legalgraph serve --host 0.0.0.0 --port 8000
# needs Neo4j creds in .env (NEO4J_URI / USERNAME / PASSWORD / DATABASE)
```

CORS is open (`*`) for local dev — restrict to your UI origin for production.

## Endpoints

### `GET /health`
`{ "status": "ok", "nodes": 42018 }`

### `GET /ask?q=<question>&top_k=10&jurisdiction=UK`
The main endpoint. Returns matched provisions (with their place in the document
tree), plus graph-RAG expansion and related regimes.

```jsonc
{
  "query": "illegal content duties for user-to-user services",
  "results": [
    {
      "provision_id": "uk-ukpga-2023-50/part/3/chapter/2/crossheading/illegal-content-duties-for-usertouser-services",
      "number": "Illegal content duties for user-to-user services",
      "heading": "Illegal content duties for user-to-user services",
      "snippet": "…",                       // ~320 chars of provision text
      "url": "https://www.legislation.gov.uk/ukpga/2023/50/part/3/chapter/2/...",
      "score": 13.3,
      "breadcrumb": ["PART 3", "CHAPTER 2", "Illegal content duties…"],
      "document": {
        "id": "uk-ukpga-2023-50",
        "citation": "Online Safety Act 2023",
        "layer": "Act",
        "url": "https://www.legislation.gov.uk/ukpga/2023/50",
        "regulator": "Office of Communications (Ofcom)"
      }
    }
  ],
  "documents": [ /* document-title matches: {id,citation,layer,url,regulator,score} */ ],
  "related_authorities": [
    { "relationship": "MADE_UNDER", "layer": "StatutoryInstrument",
      "citation": "…Regulations 2025", "url": "https://…", "regulator": "…" }
  ],
  "related_regimes": [
    { "via_topic": "data protection", "document": "Data Protection Act 2018",
      "layer": "Act", "url": "https://…" }
  ]
}
```

### `GET /document/{doc_id}`
Document metadata + its top-level provision tree (for PageIndex-style navigation).
```jsonc
{ "id":"uk-ukpga-2023-50", "citation":"Online Safety Act 2023", "layer":"Act",
  "url":"…", "regulator":"…", "date_enacted":"2023-10-26", "status":"in_force",
  "children":[ {"id":"…/part/1","number":"PART 1","heading":"Introduction","url":"…"} ] }
```

### `GET /provision/{provision_id}`
A provision's full text + its direct children (drill down level by level). The id
contains slashes — pass it through verbatim, e.g.
`/provision/uk-ukpga-2023-50/section/12`.
```jsonc
{ "id":"uk-ukpga-2023-50/section/12", "number":"12",
  "heading":"Safety duties protecting children", "text":"…", "url":"…",
  "children":[ {"id":"…/section/12/1","number":"1","heading":null} ] }
```

## UI patterns this supports
- **Search/answer page**: call `/ask`, render `results` as cited cards (heading +
  snippet + breadcrumb + link), with `related_authorities`/`related_regimes` as
  side panels.
- **Document reader / PageIndex nav**: `/document/{id}` for the tree, then
  `/provision/{id}` to expand sections lazily; every node deep-links to
  legislation.gov.uk.
- **Graph view**: `related_authorities` + `related_regimes` give the edges to draw
  around a document.

## Coming next (same shapes)
- `answer` string on `/ask` (Claude synthesis over `results`) — needs an LLM key.
- optional vector search for paraphrase recall (additive).
