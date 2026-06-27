# Handover — Regime workspace deploy fixes (2026-06-27)

Three issues were found running the deployed UI. All three have code changes in the
working tree **but are not yet committed** (see "State of the branch" below). The
regime-surfacing one is the important / least-certain one, so it's covered first
and in most depth.

---

## ⭐ Issue 1 (PRIORITY): "Relevant regimes" panel comes up empty

### Symptom
User types a topic (e.g. "online safety") + jurisdiction "United Kingdom" on the
setup screen. The chat correctly identifies relevant Acts (Online Safety Act 2023,
Communications Act 2003), but the **right-hand "Relevant regimes" panel stays
empty** ("No regimes in this session").

### Root cause
A label-vs-code mismatch on `jurisdiction`.

- The UI dropdown (`RegExplorerSite/src/components/research/SetupScreen.tsx`) sends
  **human-readable labels**: `"United Kingdom"`, `"European Union"`,
  `"United States (federal)"`.
- The graph stores **short codes**. `canonical.Jurisdiction` is `UK = "UK"` /
  `EU = "EU"`, and `loader.py:25` writes `doc.jurisdiction.value` → the node
  property `jurisdiction` is literally `"UK"`.
- `GET /regimes` → `surface_regimes()` → `search_provisions()` applies the filter
  `WHERE ($jdx IS NULL OR d.jurisdiction = $jdx)`. With `$jdx = "United Kingdom"`
  this matches **zero** documents, so nothing rolls up into regime cards.
- Chat (`POST /chat`) was unaffected because it passes **no** jurisdiction — which
  is also why the LLM could still "see" the Acts in its scoped retrieval while the
  panel stayed empty. That divergence is the tell.

### Fix applied
`src/legalgraph/regimes.py`:
- New `normalize_jurisdiction(label)` maps UI labels → graph codes
  (`"United Kingdom"`→`"UK"`, `"European Union"`→`"EU"`, plus a few aliases).
- `None`/`""` → `None` (unscoped).
- An **unknown but non-empty** label (e.g. `"United States (federal)"`, which we
  hold no data for) is **passed through unchanged** so it still scopes the query to
  something that matches nothing — i.e. it honestly returns no regimes rather than
  silently leaking unscoped UK results.
- `surface_regimes()` now calls `normalize_jurisdiction()` before querying.

Tests added in `tests/test_regimes.py` (label→code mapping, pass-through of
None/unknown, and an end-to-end assertion that `"United Kingdom"` reaches the
Cypher as `jdx="UK"`). `uv run pytest -q` → 25 passed.

### ⚠️ What is NOT yet verified — read this before closing the ticket
I verified the fix by **code path + unit test**, NOT against live data. I could not
confirm the panel actually populates end-to-end, because of a database-routing quirk
in this project:

- The **Neo4j MCP** (what Claude can query directly) points at a **local Docker**
  instance (`bolt://localhost:7687`, `neo4j`/`cellarhack123`).
- The **Python pipeline / API** (`uv run legalgraph ...`, the FastAPI app) targets a
  **separate Aura instance** (creds in the gitignored `.env`).
- The real corpus was loaded into **Aura**, not local Docker.

So the next person should do a live check against Aura:

1. Start the API: `uv run legalgraph serve --port 8000` (loads `.env` → Aura).
2. `curl 'http://localhost:8000/regimes?topic=online%20safety&jurisdiction=United%20Kingdom'`
   — expect non-empty `regimes[]` including the Online Safety Act.
3. Sanity-check the data actually has UK anchors with the expected property value:
   ```cypher
   MATCH (d:Document) WHERE d:Act OR d:Treaty
   RETURN d.jurisdiction AS j, count(*) ORDER BY j
   ```
   Confirm `j` is `"UK"` (not `"United Kingdom"`, not `"Jurisdiction.UK"`).

### If it's STILL empty after this fix, look here next (in order)
1. **No Act/Treaty-layer anchors in the corpus for that topic.** `rollup_regimes`
   keeps only `layer ∈ {"Act","Treaty"}` (`regimes.py:ANCHOR_LAYERS`). If the topic
   only matched SIs/guidance/cases, every hit is dropped. Check what layers the
   provision search returns for the topic.
2. **Full-text index missing/empty.** `search_provisions` calls
   `db.index.fulltext.queryNodes('provision_text', …)`. If that index doesn't exist
   on Aura or provisions weren't loaded, zero hits. Verify:
   `SHOW INDEXES` and `MATCH (p:Provision) RETURN count(p)`.
3. **`Act`/`Treaty` labels not applied.** The layer is derived from
   `[l IN labels(d) WHERE l <> 'Document'][0]`. If documents only have the
   `:Document` label (loader didn't add the layer label), `layer` is null and they're
   dropped. Verify: `MATCH (d:Document) RETURN labels(d), count(*)`.
4. **`jurisdiction` stored under a different value/casing** than `"UK"`. The query
   is exact-match and case-sensitive. Re-run the cypher in step 3 above.

---

## Issue 2: Chat replies render as raw markdown text

LLM answers are markdown (`**bold**`, bullet lists, links) but the chat rendered
them with a bare `<p>{text}</p>`, so `**Online Safety Act 2023**` showed literal
asterisks.

**Fix:** added `react-markdown` + `remark-gfm` (now in `package.json`). Assistant
messages render through `<ReactMarkdown>` inside a `.prose-chat` wrapper; user
messages stay plain. Markdown styles (bold/lists/links/headings/code, tuned to the
serif + navy palette) appended to `src/styles.css`. Files:
`RegExplorerSite/src/components/research/WorkspaceScreen.tsx`, `src/styles.css`.

## Issue 3: No "thinking" indicator while awaiting a reply

**Fix:** added a `thinking` state in `WorkspaceScreen`. While awaiting `POST /chat`
a bouncing-three-dots indicator shows under an "Assistant" label, and the input +
send button are disabled. Same file as Issue 2.

---

## State of the branch (IMPORTANT)

All changes are on `main` and **uncommitted** in the working tree:

```
 M RegExplorerSite/package.json                                  (react-markdown, remark-gfm)
 M RegExplorerSite/src/components/research/WorkspaceScreen.tsx   (markdown render + thinking)
 M RegExplorerSite/src/styles.css                               (.prose-chat styles)
 M RegExplorerSite/src/routeTree.gen.ts                         (generated, pre-existing)
 M src/legalgraph/regimes.py                                    (normalize_jurisdiction)
 M tests/test_regimes.py                                        (+3 tests)
?? RegExplorerSite/package-lock.json                            (new lockfile from npm install)
?? dataset/dossiers/                                            (dossier cache, gitignore candidate)
```

Nothing has been committed or pushed. Decide whether to commit as one change or
split frontend/backend.

## Run / verify

- Backend (targets Aura via `.env`): `uv run legalgraph serve --port 8000`
- Frontend: from `RegExplorerSite/`, `npm install` then `npm run dev` (vite :5173).
  Use **npm, not bun**. Reads API base from `VITE_API_BASE ?? "http://localhost:8000"`.
- Tests: `uv run pytest -q` (25 passed). Frontend typecheck: `npx tsc --noEmit` (clean).
- The frontend needs a dev-server restart to pick up the new `react-markdown` dep.

## Key files for this area
- `src/legalgraph/regimes.py` — regime surfacing (`surface_regimes`, `rollup_regimes`, `normalize_jurisdiction`)
- `src/legalgraph/retrieval.py` — `search_provisions` (the jurisdiction filter lives here)
- `src/legalgraph/api.py` — `GET /regimes`, `POST /chat`
- `src/legalgraph/loader.py:25` — where `jurisdiction` is written to the graph
- `RegExplorerSite/src/routes/index.tsx` — maps API `RegimeCard[]` → UI `Regime[]`
- `RegExplorerSite/src/lib/api.ts` — `fetchRegimes`, `sendChat`
