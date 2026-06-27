"""Regime surfacing — turns a topic query into a ranked list of regime cards.

A "regime" is a presentation view over an anchor Act/Treaty Document. We reuse
the existing provision search, roll the hits up to their anchor documents, and
blend in topically-related anchors via the concept (SKOS) layer. Pure rollup is
separated from the DB calls so it unit-tests without Neo4j.
"""
from __future__ import annotations

import os
import re

from . import retrieval

ANCHOR_LAYERS = {"Act", "Treaty"}
SHORT_DESC = 140

# The UI offers human-readable jurisdiction labels; the graph stores short codes
# (canonical.Jurisdiction: "UK", "EU"). Without this mapping the jurisdiction
# filter in search_provisions matches nothing and no regimes surface.
_JURISDICTION_ALIASES = {
    "united kingdom": "UK",
    "uk": "UK",
    "gb": "UK",
    "great britain": "UK",
    "european union": "EU",
    "eu": "EU",
}


def normalize_jurisdiction(jurisdiction: str | None) -> str | None:
    """Map a UI jurisdiction label to the graph's stored code.

    None/empty -> None (unscoped). A known label -> its code ("UK"/"EU"). An
    unknown but non-empty label (e.g. a jurisdiction we hold no data for) is
    returned unchanged so it still scopes the query — matching nothing and
    honestly returning no regimes rather than leaking results from elsewhere."""
    if not jurisdiction:
        return None
    return _JURISDICTION_ALIASES.get(jurisdiction.strip().lower(), jurisdiction)


def _db(database: str | None) -> str | None:
    return database or os.environ.get("NEO4J_DATABASE")


def _card(doc_id, citation, url, why, short_description=""):
    return {
        "id": doc_id,
        "name": citation or doc_id,
        "short_description": short_description,
        "why_surfaced": why,
        "anchor_doc_id": doc_id,
        "source_url": url,
    }


def _terms(query: str) -> list[str]:
    stop = {
        "a", "an", "and", "apply", "are", "for", "in", "of", "or", "regime",
        "regimes", "regulatory", "the", "to", "what", "which",
    }
    return [
        t.lower()
        for t in re.findall(r"[A-Za-z0-9]+", query)
        if len(t) > 2 and t.lower() not in stop
    ]


def _merge_cards(cards: list[dict], docs: list[dict], why: str) -> list[dict]:
    seen = {c.get("anchor_doc_id") or c.get("id") for c in cards}
    for d in docs:
        if d.get("layer") not in ANCHOR_LAYERS:
            continue
        doc_id = d.get("id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        cards.append(_card(
            doc_id,
            d.get("citation"),
            d.get("url"),
            why,
            _short_description(d),
        ))
    return cards


def _short_description(doc: dict) -> str:
    regulator = doc.get("regulator")
    layer = doc.get("layer")
    if regulator:
        return f"{layer or 'Anchor'} document associated with {regulator}"
    return f"{layer or 'Anchor'} document surfaced from the legal graph"


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
  AND ($jdx IS NULL OR o.jurisdiction = $jdx)
RETURN DISTINCT o.id AS id, o.citation AS citation,
       [l IN labels(o) WHERE l <> 'Document'][0] AS layer,
       o.source_url AS url, o.regulator AS regulator
LIMIT 25
"""

_TITLE_ANCHORS = """
CALL db.index.fulltext.queryNodes('document_title', $q) YIELD node, score
WHERE ('Act' IN labels(node) OR 'Treaty' IN labels(node))
  AND ($jdx IS NULL OR node.jurisdiction = $jdx)
RETURN node.id AS id, node.citation AS citation,
       [l IN labels(node) WHERE l <> 'Document'][0] AS layer,
       node.source_url AS url, node.regulator AS regulator, score
ORDER BY score DESC LIMIT $k
"""

_ANCHORS_FOR_DOCUMENTS = """
UNWIND $ids AS source_id
MATCH (s:Document {id: source_id})
CALL (s) {
  MATCH (s)-[r]-(a:Document)
  WHERE type(r) <> 'CONTAINS'
    AND ('Act' IN labels(a) OR 'Treaty' IN labels(a))
  RETURN a, type(r) AS relationship
  UNION
  MATCH (s)-[r]-(p:Provision)<-[:CONTAINS*]-(a:Document)
  WHERE type(r) <> 'CONTAINS'
    AND ('Act' IN labels(a) OR 'Treaty' IN labels(a))
  RETURN a, type(r) AS relationship
}
WITH a, relationship
WHERE ($jdx IS NULL OR a.jurisdiction = $jdx)
RETURN DISTINCT a.id AS id, a.citation AS citation,
       [l IN labels(a) WHERE l <> 'Document'][0] AS layer,
       a.source_url AS url, a.regulator AS regulator,
       collect(DISTINCT relationship) AS relationships
LIMIT 25
"""

_CONCEPT_ANCHORS = """
MATCH (c:Concept)
WHERE toLower($topic) CONTAINS toLower(c.label)
   OR toLower(c.label) CONTAINS toLower($topic)
   OR any(alt IN coalesce(c.alt_labels, [])
          WHERE toLower($topic) CONTAINS toLower(alt)
             OR toLower(alt) CONTAINS toLower($topic))
   OR ($terms <> [] AND all(term IN $terms WHERE toLower(c.label) CONTAINS term))
MATCH (c)-[:RELATED|BROADER|NARROWER*0..1]-(matched:Concept)<-[:ABOUT]-(d:Document)
CALL (d) {
  WITH d WHERE 'Act' IN labels(d) OR 'Treaty' IN labels(d)
  RETURN d AS a
  UNION
  MATCH (d)-[r]-(a:Document)
  WHERE type(r) <> 'CONTAINS'
    AND ('Act' IN labels(a) OR 'Treaty' IN labels(a))
  RETURN a
}
WITH a
WHERE ($jdx IS NULL OR a.jurisdiction = $jdx)
RETURN DISTINCT a.id AS id, a.citation AS citation,
       [l IN labels(a) WHERE l <> 'Document'][0] AS layer,
       a.source_url AS url, a.regulator AS regulator
LIMIT 25
"""


_ALL_ANCHORS = """
MATCH (d:Document)
WHERE 'Act' IN labels(d) OR 'Treaty' IN labels(d)
RETURN d.id AS id, d.citation AS citation,
       [l IN labels(d) WHERE l <> 'Document'][0] AS layer,
       d.source_url AS url, d.regulator AS regulator
ORDER BY d.citation
"""


def list_anchor_regimes(driver, database: str | None = None) -> list[dict]:
    """Every top-level regime (Act/Treaty anchor) in the graph, for the Regimes
    browser. Returns {id, name, short_description} cards ordered by citation."""
    rows = retrieval._run(driver, _ALL_ANCHORS, {}, _db(database))
    return [
        {
            "id": r["id"],
            "name": r.get("citation") or r["id"],
            "short_description": _short_description(r),
        }
        for r in rows
        if r.get("id")
    ]


def surface_regimes(driver, topic: str, jurisdiction: str | None = None,
                    database: str | None = None) -> list[dict]:
    """Provision search → anchor rollup, blended with concept-related anchors."""
    jurisdiction = normalize_jurisdiction(jurisdiction)
    provisions = retrieval.search_provisions(
        driver, topic, top_k=25, jurisdiction=jurisdiction, database=database)
    cards = rollup_regimes(provisions, related=[], jurisdiction=jurisdiction)

    cards = _merge_cards(cards, retrieval._run(
        driver,
        _TITLE_ANCHORS,
        {"q": retrieval._lucene(topic), "k": 10, "jdx": jurisdiction},
        _db(database),
    ), "primary")

    matched_doc_ids = sorted({
        (p.get("document") or {}).get("id")
        for p in provisions
        if (p.get("document") or {}).get("id")
    })
    if matched_doc_ids:
        cards = _merge_cards(cards, retrieval._run(
            driver,
            _ANCHORS_FOR_DOCUMENTS,
            {"ids": matched_doc_ids, "jdx": jurisdiction},
            _db(database),
        ), "primary")

    cards = _merge_cards(cards, retrieval._run(
        driver,
        _CONCEPT_ANCHORS,
        {"topic": topic, "terms": _terms(topic), "jdx": jurisdiction},
        _db(database),
    ), "related")

    related: list[dict] = []
    if cards:
        related = retrieval._run(driver, _RELATED_ANCHORS,
                                 {"id": cards[0]["anchor_doc_id"], "jdx": jurisdiction},
                                 _db(database))
    return _merge_cards(cards, related, "related")
