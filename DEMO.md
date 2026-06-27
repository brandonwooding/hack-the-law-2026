# Showing legalgraph to the team

The data is on **Neo4j Aura (cloud)**, so teammates can explore it live without
running anything locally. From easiest to most involved:

## 1. Screen-share the graph (fastest, highest impact)
Open Neo4j Browser on the Aura instance and run query **#1** from
`demo_queries.cypher` — the Online Safety Act "regime star" (30 connected docs
across all six layers). Keep the **Graph** tab selected; it renders as a labelled
node-link picture. Then run **#2** (related regimes) and **#3** (drill into the
Act's section tree). That's the whole story in three clicks.

## 2. Let teammates connect to the live graph
They don't need an Aura account — any Neo4j Browser can connect:

1. Go to **https://browser.neo4j.io**
2. Connect URL: `neo4j+s://0893f8bb.databases.neo4j.io`
   Database: `0893f8bb` · Username: `0893f8bb`
   **Password: ask Brandon** (it's in the project `.env`, not committed)
3. Paste queries from `demo_queries.cypher`.

> Treat the connection details like a password — share in your team chat, not
> anywhere public. (The `.env` is git-ignored so it won't end up in the repo.)

## 3. Point-and-click exploration (non-technical teammates)
In the Aura console (**https://console.neo4j.io** → your instance → **Explore**),
Neo4j Bloom/Explore lets people click a node (e.g. the Online Safety Act) and
expand its relationships with no Cypher. Good for "walk the law" demos.

## 4. Share the code
The repo is self-contained. Anyone with the creds can reproduce the whole graph:

```bash
uv sync
# put the Aura creds in .env (see .env.example)
uv run legalgraph skeleton
uv run legalgraph fetch --jurisdiction uk     # pulls all 6 sources
uv run legalgraph load && uv run legalgraph link
uv run legalgraph validate --citation "Online Safety Act 2023"
```

## Talking points
- **6 layers, one graph**: Acts, SIs, guidance, explanatory notes, debates,
  bills, case law — 195 docs, ~42k provisions, anchored on the Online Safety Act.
- **Navigable by hand** (deterministic Cypher) *before* any LLM — Graph RAG +
  PageIndex layer on top later.
- **Related regimes**: shared subject concepts link Online Safety ↔ Data
  Protection ↔ Communications automatically.
- **Scales by config, not code**: `config/scope.yaml` bounds the corpus; the same
  pipeline ingests the whole statute book by changing seeds/hops.
- **Jurisdiction-agnostic**: EU/CELLAR is the next adapter, same canonical model.
