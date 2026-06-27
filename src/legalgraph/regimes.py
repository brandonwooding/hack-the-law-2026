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
