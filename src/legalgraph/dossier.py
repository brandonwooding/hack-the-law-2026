"""Regime dossiers — cache-aside on disk.

First open of a regime: gather its grounded subgraph, have Claude draft the six
fields, write JSON. Every later open reads the JSON (no LLM). Files are editable
in the UI (save endpoint sets edited_by_human) and survive graph rebuilds, since
they live outside Neo4j. Cache key = regime id only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from . import retrieval

DOSSIER_DIR = Path(__file__).resolve().parents[2] / "dataset" / "dossiers"
DOSSIER_DEFAULTS = {
    "regulatory_guidance": [],
    "regulatory_guidance_updated_at": None,
}


def _db(database: str | None) -> str | None:
    return database or os.environ.get("NEO4J_DATABASE")


def dossier_path(regime_id: str, dossier_dir: Path = DOSSIER_DIR) -> Path:
    safe = regime_id.replace("/", "_")
    return Path(dossier_dir) / f"{safe}.json"


def read_dossier(regime_id: str, dossier_dir: Path = DOSSIER_DIR) -> dict | None:
    path = dossier_path(regime_id, dossier_dir)
    if not path.exists():
        return None
    return _with_defaults(json.loads(path.read_text()))


def write_dossier(data: dict, dossier_dir: Path = DOSSIER_DIR) -> None:
    path = dossier_path(data["regime_id"], dossier_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _with_defaults(data: dict) -> dict:
    return {**DOSSIER_DEFAULTS, **data}


_SUBGRAPH = """
MATCH (d:Document {id: $id})
OPTIONAL MATCH (d)-[:CONTAINS]->(p:Provision)
WITH d, collect({number: p.number, heading: p.heading,
                 text: left(p.text, 600), url: p.url})[..40] AS provisions
OPTIONAL MATCH (c:Document)-[:CONSIDERS]->(d) WHERE c:Case
WITH d, provisions, collect(DISTINCT {citation: c.citation, url: c.source_url}) AS cases
OPTIONAL MATCH (g:Document)-[:ISSUED_UNDER]->(d)
WHERE g:Guidance OR g:RegulatoryPolicy
RETURN d.citation AS citation, provisions, cases,
       collect(DISTINCT {citation: g.citation, url: g.source_url}) AS guidance
"""


def gather_subgraph(driver, regime_id: str, database: str | None = None) -> dict:
    rows = retrieval._run(driver, _SUBGRAPH, {"id": regime_id}, _db(database))
    row = rows[0] if rows else {}
    return {
        "regime_id": regime_id,
        "name": row.get("citation") or regime_id,
        "anchor": {"citation": row.get("citation")},
        "provisions": [p for p in (row.get("provisions") or []) if p.get("number")],
        "cases": [c for c in (row.get("cases") or []) if c.get("citation")],
        "guidance": [g for g in (row.get("guidance") or []) if g.get("citation")],
    }


def get_or_build_dossier(regime_id: str, dossier_dir: Path,
                         gather_fn, draft_fn) -> dict:
    """Cache-aside: serve the JSON if present, else synthesize once and persist."""
    existing = read_dossier(regime_id, dossier_dir)
    if existing is not None:
        return existing

    bundle = gather_fn(regime_id)
    fields = draft_fn(bundle)
    data = {
        "regime_id": regime_id,
        "name": bundle.get("name", regime_id),
        **DOSSIER_DEFAULTS,
        **fields,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "edited_by_human": False,
    }
    write_dossier(data, dossier_dir)
    return data


def refresh_regulatory_guidance(regime_id: str, dossier_dir: Path,
                                gather_fn, refresh_fn) -> dict:
    """Refresh only the web-sourced regulatory guidance section."""
    bundle = gather_fn(regime_id)
    current = read_dossier(regime_id, dossier_dir) or {
        "regime_id": regime_id,
        "name": bundle.get("name", regime_id),
        **DOSSIER_DEFAULTS,
        "edited_by_human": False,
    }
    current["regulatory_guidance"] = refresh_fn(bundle)
    current["regulatory_guidance_updated_at"] = (
        _dt.datetime.now(_dt.timezone.utc).isoformat()
    )
    write_dossier(current, dossier_dir)
    return current


def save_dossier(regime_id: str, fields: dict, dossier_dir: Path) -> dict:
    """UI edit-in-place: merge changed fields, flag as human-edited, persist."""
    data = read_dossier(regime_id, dossier_dir) or {
        "regime_id": regime_id,
        **DOSSIER_DEFAULTS,
    }
    data.update(fields)
    data["regime_id"] = regime_id
    data["edited_by_human"] = True
    write_dossier(data, dossier_dir)
    return data
