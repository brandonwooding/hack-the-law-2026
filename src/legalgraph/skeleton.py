"""The Neo4j skeleton: constraints + indexes. Single source of truth.

The same statement list is applied by the Python driver (`apply`) and can be
run verbatim through the Neo4j MCP for interactive setup — no drift.
"""

from __future__ import annotations

#: Uniqueness constraints (also create backing indexes).
CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT doc_id IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT prov_id IF NOT EXISTS "
    "FOR (p:Provision) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS "
    "FOR (c:Concept) REQUIRE c.id IS UNIQUE",
]

#: Secondary indexes to make manual navigation instant.
INDEXES: list[str] = [
    "CREATE INDEX doc_citation IF NOT EXISTS FOR (d:Document) ON (d.citation)",
    "CREATE INDEX doc_celex     IF NOT EXISTS FOR (d:Document) ON (d.celex)",
    "CREATE INDEX doc_ecli      IF NOT EXISTS FOR (d:Document) ON (d.ecli)",
    "CREATE INDEX doc_jdx       IF NOT EXISTS FOR (d:Document) ON (d.jurisdiction)",
    "CREATE INDEX doc_type      IF NOT EXISTS FOR (d:Document) ON (d.type)",
    "CREATE INDEX doc_status    IF NOT EXISTS FOR (d:Document) ON (d.status)",
    "CREATE INDEX doc_regulator IF NOT EXISTS FOR (d:Document) ON (d.regulator)",
    "CREATE INDEX doc_publisher IF NOT EXISTS FOR (d:Document) ON (d.publisher)",
    "CREATE INDEX doc_kind      IF NOT EXISTS FOR (d:Document) ON (d.document_kind)",
    "CREATE INDEX doc_effect    IF NOT EXISTS FOR (d:Document) ON (d.legal_effect)",
    "CREATE INDEX prov_number   IF NOT EXISTS FOR (p:Provision) ON (p.number)",
    "CREATE INDEX concept_label IF NOT EXISTS FOR (c:Concept) ON (c.label)",
]

#: Full-text index over provision text (handy for manual keyword lookup before
#: any LLM is involved). Created separately as it uses different syntax.
FULLTEXT: list[str] = [
    "CREATE FULLTEXT INDEX provision_text IF NOT EXISTS "
    "FOR (p:Provision) ON EACH [p.text, p.heading]",
    "CREATE FULLTEXT INDEX document_title IF NOT EXISTS "
    "FOR (d:Document) ON EACH [d.title, d.citation]",
]


def statements() -> list[str]:
    """All DDL statements in apply order."""
    return [*CONSTRAINTS, *INDEXES, *FULLTEXT]


def apply(driver, database: str | None = None) -> int:
    """Apply the skeleton via a neo4j driver. Idempotent (IF NOT EXISTS)."""
    count = 0
    with driver.session(database=database) as session:
        for stmt in statements():
            session.run(stmt)
            count += 1
    return count
