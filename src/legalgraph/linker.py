"""Pass 2 — link edges. Resolves each Document's cross-references into
relationships, after all nodes exist. Unresolved targets are reported, not
fatal: a citation to a document outside your scope simply tells you what's
missing from the corpus.
"""

from __future__ import annotations

from .canonical import Concept, Document, EdgeType
from .db import Op

# Whitelisted from the EdgeType enum, so safe to interpolate as a rel type.
_REL_TYPES = {t.value for t in EdgeType}


def _link_op(rel: str, src_id: str, tgt_id: str, props: dict | None = None) -> Op:
    """A MERGE-relationship op that returns rows only if both endpoints exist,
    so an empty result flags an unresolved target."""
    return (
        "MATCH (s {id: $src}) MATCH (t {id: $tgt}) "
        f"MERGE (s)-[r:`{rel}`]->(t) SET r += $props "
        "RETURN s.id AS src, t.id AS tgt",
        {"src": src_id, "tgt": tgt_id, "props": props or {}},
    )


def edge_ops(doc: Document) -> list[Op]:
    """Cross-document edges declared on the document, plus ABOUT edges derived
    from its `concepts` list (Document -> Concept)."""
    ops: list[Op] = []
    for e in doc.edges:
        if e.type.value not in _REL_TYPES:  # defensive; enum guarantees this
            raise ValueError(f"Unknown edge type: {e.type}")
        rel_props = {
            k: v
            for k, v in {"valid_from": e.valid_from, "valid_to": e.valid_to, "note": e.note}.items()
            if v is not None
        }
        src, tgt = e.source_ref or doc.id, e.target
        if e.reverse:
            src, tgt = tgt, src
        ops.append(_link_op(e.type.value, src, tgt, rel_props))
    for concept_id in doc.concepts:
        ops.append(_link_op(EdgeType.ABOUT.value, doc.id, concept_id))
    return ops


def concept_edge_ops(concept: Concept) -> list[Op]:
    """SKOS relations between concepts (Concept -> Concept)."""
    ops: list[Op] = []
    for tgt in concept.broader:
        ops.append(_link_op(EdgeType.BROADER.value, concept.id, tgt))
    for tgt in concept.narrower:
        ops.append(_link_op(EdgeType.NARROWER.value, concept.id, tgt))
    for tgt in concept.related:
        ops.append(_link_op(EdgeType.RELATED.value, concept.id, tgt))
    return ops


def _run_link(driver, ops: list[Op], database: str | None) -> dict:
    from .db import run_ops

    created = 0
    unresolved: list[tuple[str, str]] = []
    results = run_ops(driver, ops, database=database)
    for (_cypher, params), rows in zip(ops, results):
        if rows:
            created += 1
        else:
            unresolved.append((params["src"], params["tgt"]))
    return {"created": created, "unresolved": unresolved}


def link_documents(driver, docs: list[Document], database: str | None = None) -> dict:
    """Run document edge + ABOUT ops. Returns {'created', 'unresolved'}."""
    ops = [op for doc in docs for op in edge_ops(doc)]
    return _run_link(driver, ops, database)


def link_concepts(driver, concepts: list[Concept], database: str | None = None) -> dict:
    """Run SKOS edge ops between concepts. Returns {'created', 'unresolved'}."""
    ops = [op for c in concepts for op in concept_edge_ops(c)]
    return _run_link(driver, ops, database)
