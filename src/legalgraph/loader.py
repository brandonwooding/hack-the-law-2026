"""Pass 1 — load nodes. Turns a canonical Document into idempotent MERGE ops
for the document node, its provision tree, and the CONTAINS hierarchy.

No cross-document edges here; those need every node to exist first (see linker).
"""

from __future__ import annotations

from .canonical import Concept, DocType, Document, Provision
from .db import Op

# Whitelisted from the DocType enum, so safe to interpolate as a label.
_DOC_LABELS = {t.value for t in DocType}


def _clean(d: dict) -> dict:
    """Drop None values so nodes stay tidy."""
    return {k: v for k, v in d.items() if v is not None}


def _doc_props(doc: Document) -> dict:
    return _clean(
        {
            "id": doc.id,
            "jurisdiction": doc.jurisdiction.value,
            "type": doc.type.value,
            "citation": doc.citation,
            "title": doc.title,
            "celex": doc.celex,
            "ecli": doc.ecli,
            "date_enacted": doc.date_enacted,
            "date_in_force": doc.date_in_force,
            "date_repealed": doc.date_repealed,
            "date_decided": doc.date_decided,
            "status": doc.status.value,
            "territorial_scope": doc.territorial_scope,
            "court": doc.court,
            "level": doc.level,
            "regulator": doc.regulator,
            "precedence": doc.precedence,
            "subject_tags": doc.subject_tags or None,
            "source_url": doc.source.url,
            "source_fetched_at": doc.source.fetched_at,
            "source_hash": doc.source.hash,
            "source_format": doc.source.raw_format,
        }
    )


def _prov_props(p: Provision) -> dict:
    return _clean(
        {
            "id": p.id,
            "number": p.number,
            "heading": p.heading,
            "text": p.text,
            "legal_force": p.legal_force.value,
            "valid_from": p.valid_from,
            "valid_to": p.valid_to,
        }
    )


def document_ops(doc: Document) -> list[Op]:
    """Idempotent ops to create the document node + provision tree + CONTAINS."""
    if doc.type.value not in _DOC_LABELS:  # defensive; enum guarantees this
        raise ValueError(f"Unknown document type: {doc.type}")
    label = doc.type.value

    ops: list[Op] = [
        (
            f"MERGE (d:Document {{id: $id}}) SET d:`{label}`, d += $props",
            {"id": doc.id, "props": _doc_props(doc)},
        )
    ]

    # Flatten the provision tree, recording each node's parent for CONTAINS.
    def emit(parent_id: str, parent_label: str, prov: Provision) -> None:
        ops.append(
            (
                "MERGE (p:Provision {id: $id}) SET p += $props",
                {"id": prov.id, "props": _prov_props(prov)},
            )
        )
        ops.append(
            (
                f"MATCH (parent:`{parent_label}` {{id: $pid}}) "
                "MATCH (child:Provision {id: $cid}) "
                "MERGE (parent)-[:CONTAINS]->(child)",
                {"pid": parent_id, "cid": prov.id},
            )
        )
        for child in prov.children:
            emit(prov.id, "Provision", child)

    for top in doc.provisions:
        emit(doc.id, label, top)

    return ops


def concept_node_ops(concept: Concept) -> list[Op]:
    """Idempotent op to create a Concept node (SKOS edges are linked later)."""
    return [
        (
            "MERGE (c:Concept {id: $id}) SET c += $props",
            {
                "id": concept.id,
                "props": _clean(
                    {
                        "id": concept.id,
                        "scheme": concept.scheme,
                        "label": concept.label,
                        "alt_labels": concept.alt_labels or None,
                    }
                ),
            },
        )
    ]


def _walk_prov(prov: Provision, parent_id: str, parent_is_doc: bool,
               prov_rows: list, c_doc: list, c_prov: list) -> None:
    prov_rows.append({"id": prov.id, "props": _prov_props(prov)})
    (c_doc if parent_is_doc else c_prov).append({"pid": parent_id, "cid": prov.id})
    for child in prov.children:
        _walk_prov(child, prov.id, False, prov_rows, c_doc, c_prov)


def _run_batched(driver, query: str, rows: list, batch: int, database) -> None:
    from .db import run_ops
    for i in range(0, len(rows), batch):
        run_ops(driver, [(query, {"rows": rows[i:i + batch]})], database=database)


def load_documents(driver, docs: list[Document], database: str | None = None,
                   batch: int = 500) -> dict:
    """Batched (UNWIND) load of document nodes, provision trees, and CONTAINS.
    Returns counts. Idempotent (MERGE)."""
    doc_rows: dict[str, list] = {}            # label -> rows
    prov_rows: list = []
    c_doc: list = []                          # Document -> Provision
    c_prov: list = []                         # Provision -> Provision
    for doc in docs:
        doc_rows.setdefault(doc.type.value, []).append(
            {"id": doc.id, "props": _doc_props(doc)}
        )
        for top in doc.provisions:
            _walk_prov(top, doc.id, True, prov_rows, c_doc, c_prov)

    for label, rows in doc_rows.items():
        _run_batched(
            driver,
            f"UNWIND $rows AS r MERGE (d:Document {{id: r.id}}) "
            f"SET d:`{label}`, d += r.props",
            rows, batch, database,
        )
    _run_batched(
        driver,
        "UNWIND $rows AS r MERGE (p:Provision {id: r.id}) SET p += r.props",
        prov_rows, batch, database,
    )
    _run_batched(
        driver,
        "UNWIND $rows AS r MATCH (a:Document {id: r.pid}) "
        "MATCH (b:Provision {id: r.cid}) MERGE (a)-[:CONTAINS]->(b)",
        c_doc, batch, database,
    )
    _run_batched(
        driver,
        "UNWIND $rows AS r MATCH (a:Provision {id: r.pid}) "
        "MATCH (b:Provision {id: r.cid}) MERGE (a)-[:CONTAINS]->(b)",
        c_prov, batch, database,
    )
    return {"documents": sum(len(v) for v in doc_rows.values()),
            "provisions": len(prov_rows),
            "contains": len(c_doc) + len(c_prov)}


def load_concepts(driver, concepts: list[Concept], database: str | None = None,
                  batch: int = 500) -> int:
    """Batched create of thesaurus Concept nodes."""
    rows = [
        {"id": c.id, "props": _clean({
            "id": c.id, "scheme": c.scheme, "label": c.label,
            "alt_labels": c.alt_labels or None,
        })}
        for c in concepts
    ]
    _run_batched(
        driver,
        "UNWIND $rows AS r MERGE (c:Concept {id: r.id}) SET c += r.props",
        rows, batch, database,
    )
    return len(rows)
