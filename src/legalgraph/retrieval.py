"""Two-stage retrieval over the graph — the read side of the system.

Stage 1 (Graph RAG): full-text + concept entry points into the graph, then
graph expansion to the surrounding authorities (parent Act, guidance, SIs,
related regimes, cases).
Stage 2 (PageIndex): the matched provision's place in its document tree
(breadcrumb of ancestors), so the UI can navigate to the exact section.

Pure functions returning JSON-able dicts. No LLM here — natural-language answer
synthesis (Claude) layers on top of `ask()` later. Every result carries a
clickable source link.
"""

from __future__ import annotations

import os
import re

from .db import Op  # noqa: F401  (kept for type parity)

SNIPPET = 320
CHAT_AUTHORITY_LIMIT = 40


def _db(database: str | None) -> str | None:
    return database or os.environ.get("NEO4J_DATABASE")


def _run(driver, cypher: str, params: dict, database: str | None):
    with driver.session(database=_db(database)) as s:
        return [r.data() for r in s.run(cypher, **params)]


def _lucene(query: str) -> str:
    """Turn a natural question into a safe Lucene OR-query of its terms."""
    terms = re.findall(r"[A-Za-z0-9]+", query)
    return " OR ".join(terms) if terms else query


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


def search_provisions(driver, query: str, top_k: int = 10,
                      jurisdiction: str | None = None, database: str | None = None,
                      regime_ids: list[str] | None = None) -> list[dict]:
    """Stage 1+2: best-matching provisions with their document + tree breadcrumb."""
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
    out = []
    for r in rows:
        text = r.get("text") or ""
        out.append({
            "provision_id": r["provision_id"],
            "number": r["number"],
            "heading": r["heading"],
            "snippet": text[:SNIPPET] + ("…" if len(text) > SNIPPET else ""),
            "url": r["url"],
            "score": round(r["score"], 3),
            "breadcrumb": r["breadcrumb"],
            "document": {
                "id": r["doc_id"], "citation": r["document"], "layer": r["layer"],
                "url": r["document_url"], "regulator": r["regulator"],
            },
        })
    return out


def search_documents(driver, query: str, top_k: int = 5,
                     database: str | None = None) -> list[dict]:
    """Document-title matches (e.g. naming an Act directly)."""
    cypher = """
    CALL db.index.fulltext.queryNodes('document_title', $q) YIELD node, score
    RETURN node.id AS id, node.citation AS citation,
           [l IN labels(node) WHERE l <> 'Document'][0] AS layer,
           node.source_url AS url, node.regulator AS regulator, score
    ORDER BY score DESC LIMIT $k
    """
    return _run(driver, cypher, {"q": _lucene(query), "k": top_k}, database)


def related_authorities(driver, doc_id: str, limit: int = 25,
                        database: str | None = None) -> list[dict]:
    """Graph-RAG expansion: documents directly connected to a matched document
    (SIs made under it, guidance, explanatory notes, debates, cases, the bill)."""
    cypher = """
    MATCH (d:Document {id: $id})-[r]-(n:Document)
    WHERE type(r) <> 'CONTAINS'
    RETURN DISTINCT type(r) AS relationship,
           [l IN labels(n) WHERE l <> 'Document'][0] AS layer,
           n.citation AS citation, n.source_url AS url, n.regulator AS regulator
    ORDER BY relationship LIMIT $limit
    """
    return _run(driver, cypher, {"id": doc_id, "limit": limit}, database)


_REGIME_DOCS = """
MATCH (d:Document)
WHERE d.id IN $ids
RETURN d.id AS id, d.citation AS citation,
       [l IN labels(d) WHERE l <> 'Document'][0] AS layer,
       d.source_url AS url, d.regulator AS regulator,
       d.date_enacted AS date_enacted, d.status AS status
ORDER BY d.citation
"""


def get_regime_documents(driver, regime_ids: list[str] | None,
                         database: str | None = None) -> list[dict]:
    """Anchor documents selected by the user as confirmed regimes."""
    if not regime_ids:
        return []
    return _run(driver, _REGIME_DOCS, {"ids": list(regime_ids)}, database)


_RELATED_DOCUMENTS_FOR_REGIMES = """
UNWIND $ids AS regime_id
MATCH (regime:Document {id: regime_id})
CALL (regime) {
  MATCH (regime)-[r]-(n:Document)
  WHERE type(r) <> 'CONTAINS'
  RETURN n, type(r) AS relationship
  UNION
  MATCH (regime)-[:CONTAINS*]->(p:Provision)<-[r]-(n:Document)
  WHERE type(r) <> 'CONTAINS'
  RETURN n, type(r) AS relationship
  UNION
  MATCH (regime)-[:ABOUT]->(:Concept)<-[:ABOUT]-(n:Document)
  WHERE n <> regime AND (n:Guidance OR n:RegulatoryPolicy)
  RETURN n, 'ABOUT' AS relationship
}
WITH DISTINCT regime.id AS regime_id, regime.citation AS regime, n, relationship
WITH regime_id, regime, n, collect(DISTINCT relationship) AS relationships
WITH regime_id, regime, n, relationships,
     CASE
       WHEN 'ISSUED_UNDER' IN relationships THEN 'ISSUED_UNDER'
       WHEN 'MADE_UNDER' IN relationships THEN 'MADE_UNDER'
       WHEN 'DEBATED_IN' IN relationships THEN 'DEBATED_IN'
       ELSE relationships[0]
     END AS relationship
RETURN regime_id, regime,
       n.id AS id, n.citation AS citation, n.title AS title,
       [l IN labels(n) WHERE l <> 'Document'][0] AS layer,
       relationship, relationships, n.source_url AS url, n.regulator AS regulator,
       n.date_enacted AS date_enacted, n.date_decided AS date_decided,
       n.status AS status
LIMIT $limit
"""


def _authority_rank(row: dict, query: str) -> tuple[int, str, str]:
    """Query-aware ordering for the prompt; keeps asked-for layers near the top."""
    q = query.lower()
    layer = row.get("layer") or ""
    relationship = row.get("relationship") or ""
    wanted = {
        "HansardDebate": ("hansard", "debate", "parliament", "lords", "commons"),
        "Guidance": ("guidance", "code", "ofcom", "ico"),
        "RegulatoryPolicy": ("policy", "policies", "procedure", "procedures", "ofcom", "ico"),
        "Case": ("case", "court", "judgment", "judgement", "held"),
        "StatutoryInstrument": ("si", "statutory instrument", "regulation", "regulations"),
        "Bill": ("bill", "parliament"),
        "ExplanatoryNote": ("explanatory", "notes"),
    }
    rank = 1
    if any(term in q for term in wanted.get(layer, ())):
        rank = 0
    return (rank, relationship, row.get("citation") or "")


def related_documents_for_regimes(driver, regime_ids: list[str] | None, query: str = "",
                                  limit: int = CHAT_AUTHORITY_LIMIT,
                                  database: str | None = None) -> list[dict]:
    """Documents in the selected regimes' graph neighbourhood.

    This is the chat counterpart to provision retrieval: it exposes document-only
    material such as Hansard debates and Bills that have no Provision text.
    """
    if not regime_ids:
        return []
    rows = _run(driver, _RELATED_DOCUMENTS_FOR_REGIMES,
                {"ids": list(regime_ids), "limit": limit}, database)
    rows.sort(key=lambda r: _authority_rank(r, query))
    return rows[:limit]


def chat_context(driver, query: str, regime_ids: list[str] | None = None,
                 top_k: int = 12, database: str | None = None) -> dict:
    """Ground a chat turn in both scoped provisions and regime neighbourhood docs."""
    regime_ids = list(regime_ids or [])
    provisions = search_provisions(
        driver, query, top_k=top_k, regime_ids=regime_ids or None,
        database=database)
    regimes = get_regime_documents(driver, regime_ids, database=database)
    related_documents = related_documents_for_regimes(
        driver, regime_ids, query=query, database=database)

    names = [r.get("citation") for r in regimes if r.get("citation")]
    if not names:
        names = sorted({(p.get("document") or {}).get("citation")
                        for p in provisions if p.get("document")})
    return {
        "regime_ids": regime_ids,
        "regime_names": [n for n in names if n],
        "regimes": regimes,
        "provisions": provisions,
        "related_documents": related_documents,
    }


def related_regimes(driver, doc_id: str, database: str | None = None) -> list[dict]:
    """Documents governing topically-related regimes (via shared/adjacent concepts)."""
    cypher = """
    MATCH (d:Document {id: $id})-[:ABOUT]->(c:Concept)-[:RELATED|BROADER]-(c2:Concept)
          <-[:ABOUT]-(o:Document)
    WHERE o <> d
    RETURN DISTINCT c2.label AS via_topic, o.citation AS document,
           [l IN labels(o) WHERE l <> 'Document'][0] AS layer, o.source_url AS url
    LIMIT 25
    """
    return _run(driver, cypher, {"id": doc_id}, database)


def get_document(driver, doc_id: str, max_depth: int = 2,
                 database: str | None = None) -> dict | None:
    """Document metadata + a shallow slice of its provision tree (for the UI's
    PageIndex-style navigation). Children are fetched lazily by the UI per id."""
    meta = _run(driver, """
        MATCH (d:Document {id: $id})
        RETURN d.id AS id, d.citation AS citation,
               [l IN labels(d) WHERE l <> 'Document'][0] AS layer,
               d.source_url AS url, d.regulator AS regulator,
               d.date_enacted AS date_enacted, d.status AS status
    """, {"id": doc_id}, database)
    if not meta:
        return None
    children = _run(driver, """
        MATCH (d:Document {id: $id})-[:CONTAINS]->(p:Provision)
        RETURN p.id AS id, p.number AS number, p.heading AS heading, p.url AS url
        ORDER BY p.id
    """, {"id": doc_id}, database)
    doc = meta[0]
    doc["children"] = children
    return doc


def get_provision(driver, provision_id: str, database: str | None = None) -> dict | None:
    """A provision's full text + its direct children (for drill-down)."""
    rows = _run(driver, """
        MATCH (p:Provision {id: $id})
        OPTIONAL MATCH (p)-[:CONTAINS]->(c:Provision)
        RETURN p.id AS id, p.number AS number, p.heading AS heading,
               p.text AS text, p.url AS url,
               collect({id: c.id, number: c.number, heading: c.heading}) AS children
    """, {"id": provision_id}, database)
    if not rows:
        return None
    r = rows[0]
    r["children"] = [c for c in r["children"] if c.get("id")]
    return r


def ask(driver, query: str, top_k: int = 10, jurisdiction: str | None = None,
        database: str | None = None) -> dict:
    """Top-level retrieval bundle for the UI. (Claude synthesis will add an
    'answer' field on top of this same structure later.)"""
    provisions = search_provisions(driver, query, top_k, jurisdiction, database)
    documents = search_documents(driver, query, database=database)
    top_doc = provisions[0]["document"]["id"] if provisions else (
        documents[0]["id"] if documents else None)
    return {
        "query": query,
        "results": provisions,
        "documents": documents,
        "related_authorities": related_authorities(driver, top_doc, database=database) if top_doc else [],
        "related_regimes": related_regimes(driver, top_doc, database=database) if top_doc else [],
    }
