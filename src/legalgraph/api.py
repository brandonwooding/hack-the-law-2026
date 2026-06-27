"""HTTP API over the retrieval layer — what the UI calls.

JSON in/out, CORS open for local dev. Every result carries source links so the
frontend can render clickable citations and drill into the provision tree.

Run:  uv run legalgraph serve   (or: uvicorn legalgraph.api:app --reload)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import retrieval, regimes, llm, dossier
from .db import connect
from pydantic import BaseModel

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["driver"] = connect()
    try:
        yield
    finally:
        _state["driver"].close()


app = FastAPI(title="legalgraph API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to your UI origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)


def _driver():
    return _state["driver"]


def _regulatory_guidance_context(regime_ids: list[str]) -> list[dict]:
    context = []
    for regime_id in regime_ids:
        saved = dossier.read_dossier(regime_id, dossier.DOSSIER_DIR)
        rows = (saved or {}).get("regulatory_guidance") or []
        if not rows:
            continue
        context.append({
            "regime_id": regime_id,
            "regime_name": (saved or {}).get("name") or regime_id,
            "updated_at": (saved or {}).get("regulatory_guidance_updated_at"),
            "guidance": rows,
        })
    return context


@app.get("/health")
def health():
    rows = retrieval._run(_driver(), "MATCH (n) RETURN count(n) AS n", {}, None)
    return {"status": "ok", "nodes": rows[0]["n"]}


@app.get("/ask")
def ask(q: str = Query(..., min_length=2),
        top_k: int = 10,
        jurisdiction: str | None = None):
    """Two-stage retrieval: cited provisions + related authorities + regimes."""
    return retrieval.ask(_driver(), q, top_k=top_k, jurisdiction=jurisdiction)


@app.get("/document/{doc_id}")
def document(doc_id: str):
    doc = retrieval.get_document(_driver(), doc_id)
    if not doc:
        raise HTTPException(404, f"document not found: {doc_id}")
    return doc


@app.get("/provision/{provision_id:path}")
def provision(provision_id: str):
    prov = retrieval.get_provision(_driver(), provision_id)
    if not prov:
        raise HTTPException(404, f"provision not found: {provision_id}")
    return prov


@app.get("/regimes")
def list_regimes(topic: str = Query(..., min_length=2),
                 jurisdiction: list[str] | None = Query(None)):
    """Surface candidate regimes (anchor Acts + related) for a topic.

    `jurisdiction` may be repeated to scope across several jurisdictions at once
    (e.g. ?jurisdiction=UK&jurisdiction=EU); omit it for an unscoped search."""
    cards = regimes.surface_regimes(_driver(), topic, jurisdiction=jurisdiction)
    return {"regimes": cards}


@app.get("/regimes/all")
def list_all_regimes():
    """Every top-level regime (Act/Treaty anchor) — for the Regimes browser."""
    return {"regimes": regimes.list_anchor_regimes(_driver())}


class ChatRequest(BaseModel):
    query: str
    regime_ids: list[str] = []


@app.post("/chat")
def chat(req: ChatRequest):
    """Answer a follow-up, hard-scoped to the confirmed regimes."""
    scoped = retrieval.chat_context(
        _driver(), req.query, top_k=12, regime_ids=req.regime_ids or None)
    scoped["regulatory_guidance"] = _regulatory_guidance_context(
        scoped.get("regime_ids") or req.regime_ids)
    reply = llm.answer(req.query, scoped)
    return {"answer": reply["answer"],
            "suggestions": reply.get("suggestions", []),
            "citations": scoped["provisions"],
            "related_documents": scoped["related_documents"],
            "regulatory_guidance": scoped["regulatory_guidance"]}


@app.get("/regime/{regime_id:path}")
def regime(regime_id: str):
    """Dossier for a regime — synthesized + cached on first open."""
    return dossier.get_or_build_dossier(
        regime_id, dossier.DOSSIER_DIR,
        gather_fn=lambda rid: dossier.gather_subgraph(_driver(), rid),
        draft_fn=llm.draft_dossier,
    )


@app.post("/regime/{regime_id:path}/regulatory-guidance/refresh")
def refresh_regulatory_guidance(regime_id: str):
    """Refresh only the live, web-sourced regulatory guidance section."""
    return dossier.refresh_regulatory_guidance(
        regime_id, dossier.DOSSIER_DIR,
        gather_fn=lambda rid: dossier.gather_subgraph(_driver(), rid),
        refresh_fn=llm.refresh_regulatory_guidance,
    )


@app.put("/regime/{regime_id:path}")
def edit_regime(regime_id: str, fields: dict = Body(...)):
    """Save UI edits to a dossier (overwrites the JSON, flags human-edited)."""
    return dossier.save_dossier(regime_id, fields, dossier.DOSSIER_DIR)
