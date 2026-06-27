"""Thin Neo4j driver wrapper + the shared `Op` type.

Loader and linker produce `Op = (cypher, params)` tuples. They can be executed
by this driver wrapper (standalone pipeline) or dumped as JSON and run through
the Neo4j MCP for interactive setup — same statements either way.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

Op = tuple[str, dict[str, Any]]


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from a .env file (project root by default).
    Existing environment variables take precedence — does not override."""
    path = path or Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def connect(uri: str | None = None, user: str | None = None, password: str | None = None):
    """Connect using args or NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD.
    Auto-loads a project-root .env if present."""
    from neo4j import GraphDatabase

    load_dotenv()
    uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = user or os.environ.get("NEO4J_USERNAME", os.environ.get("NEO4J_USER", "neo4j"))
    password = password or os.environ.get("NEO4J_PASSWORD", "neo4j")
    auth = (user, password)
    # Our schema is intentionally rich but often sparsely populated, so queries
    # legitimately reference relationship types that don't exist yet. Silence
    # just those "UNRECOGNIZED" advisories; real warnings still surface.
    # (config keyword was renamed across driver majors — try new then old.)
    for kw in ("notifications_disabled_classifications",
               "notifications_disabled_categories"):
        try:
            return GraphDatabase.driver(uri, auth=auth, **{kw: ["UNRECOGNIZED"]})
        except (TypeError, ValueError):
            continue
    return GraphDatabase.driver(uri, auth=auth)


def run_ops(driver, ops: list[Op], database: str | None = None) -> list[Any]:
    """Execute a list of ops in one session. Returns each op's result rows."""
    database = database or os.environ.get("NEO4J_DATABASE")
    results: list[Any] = []
    with driver.session(database=database) as session:
        for cypher, params in ops:
            res = session.run(cypher, **params)
            results.append([r.data() for r in res])
    return results
