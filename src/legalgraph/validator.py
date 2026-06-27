"""Integrity checks + the manual navigation queries.

The point: prove the graph is navigable *by hand* before any LLM is involved.
If these return the right rows, the data model works.
"""

from __future__ import annotations

# --- integrity checks (run after load + link) ----------------------------- #
INTEGRITY: dict[str, str] = {
    "node_counts": "MATCH (n) RETURN labels(n) AS labels, count(*) AS n ORDER BY n DESC",
    "rel_counts": "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC",
    # provisions that aren't attached to any document via CONTAINS
    "orphan_provisions": (
        "MATCH (p:Provision) WHERE NOT ()-[:CONTAINS]->(p) "
        "RETURN p.id AS id LIMIT 25"
    ),
    # documents with no internal structure (often fine, but worth eyeballing)
    "documents_without_provisions": (
        "MATCH (d:Document) WHERE NOT (d)-[:CONTAINS]->(:Provision) "
        "RETURN d.id AS id, d.type AS type LIMIT 25"
    ),
}

# --- navigation queries (the 'can I browse it by hand?' proof) ------------- #
NAVIGATION: dict[str, str] = {
    # all cases related to an Act (via any provision), ranked by authority
    "cases_for_act": (
        "MATCH (a:Document {citation: $citation})-[:CONTAINS*]->(p:Provision) "
        "<-[r:CONSIDERS|INTERPRETS|APPLIES]-(c:Case) "
        "RETURN DISTINCT c.citation AS case, c.court AS court, c.level AS level, "
        "p.number AS section, type(r) AS treatment, c.precedence AS precedence "
        "ORDER BY c.precedence DESC"
    ),
    # everything touching an Act across all six layers, in one hop
    "everything_for_act": (
        "MATCH (a:Document {citation: $citation})-[r]-(d:Document) "
        "RETURN labels(d) AS layer, type(r) AS rel, d.citation AS doc "
        "ORDER BY rel"
    ),
    # SIs / regulatory instruments made under an Act
    "instruments_under_act": (
        "MATCH (a:Document {citation: $citation})-[:CONTAINS*0..]->(p) "
        "<-[:MADE_UNDER]-(si:Document) "
        "RETURN DISTINCT si.citation AS instrument, si.type AS type"
    ),
    # a section together with its explanatory note (the EXPLAINS payoff)
    "section_with_note": (
        "MATCH (p:Provision {id: $provision_id}) "
        "OPTIONAL MATCH (en:ExplanatoryNote)-[:EXPLAINS]->(p) "
        "RETURN p.number AS section, p.text AS text, en.citation AS note_source"
    ),
    # RELATED REGIMES: from the anchor's concepts, hop one SKOS step to
    # neighbouring concepts, then collect the documents governing those.
    "related_regimes": (
        "MATCH (anchor:Document {citation: $citation})-[:ABOUT]->(c:Concept) "
        "MATCH (c)-[s:RELATED|BROADER|NARROWER]-(c2:Concept)<-[:ABOUT]-(d:Document) "
        "WHERE d <> anchor "
        "RETURN DISTINCT c.label AS via, type(s) AS link, c2.label AS related_topic, "
        "d.citation AS doc, d.type AS type, d.jurisdiction AS jdx, d.regulator AS regulator, "
        "d.precedence AS precedence "
        "ORDER BY related_topic, precedence DESC"
    ),
    # CROSS-JURISDICTION regime alignment: same concept, different jurisdiction.
    "regime_across_jurisdictions": (
        "MATCH (anchor:Document {citation: $citation})-[:ABOUT]->(c:Concept)"
        "<-[:ABOUT]-(d:Document) "
        "WHERE d.jurisdiction <> anchor.jurisdiction "
        "RETURN c.label AS shared_topic, d.jurisdiction AS jdx, d.citation AS doc, d.type AS type"
    ),
    # regimes that share a regulator (institutional relatedness signal)
    "regimes_sharing_regulator": (
        "MATCH (anchor:Document {citation: $citation}) WHERE anchor.regulator IS NOT NULL "
        "MATCH (d:Document {regulator: anchor.regulator}) WHERE d <> anchor "
        "RETURN d.regulator AS regulator, d.citation AS doc, d.type AS type"
    ),
}


def run_suite(driver, queries: dict[str, str], params: dict | None = None,
              database: str | None = None) -> dict:
    from .db import run_ops

    params = params or {}
    out: dict = {}
    for name, q in queries.items():
        # only pass params the query actually references
        p = {k: v for k, v in params.items() if f"${k}" in q}
        rows = run_ops(driver, [(q, p)], database=database)[0]
        out[name] = rows
    return out
