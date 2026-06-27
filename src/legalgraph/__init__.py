"""legalgraph: a jurisdiction-agnostic legal knowledge graph pipeline.

Pipeline stages (all idempotent, disk-backed):
    fetch  -> raw/        (per-jurisdiction adapter; added later, at the source stage)
    parse  -> parsed/     (per-jurisdiction adapter -> canonical JSON)
    load   -> Neo4j       (shared; MERGE nodes: documents + provisions + CONTAINS)
    link   -> Neo4j       (shared; MERGE relationships; logs unresolved targets)
    validate              (shared; integrity checks + navigation queries)

Only the adapter (fetch + parse) is jurisdiction-specific. Everything downstream
of the canonical format is written once and reused for every jurisdiction.
"""

__all__ = ["canonical", "skeleton", "loader", "linker", "validator", "db"]
