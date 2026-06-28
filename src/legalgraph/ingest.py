"""Targeted single-act ingestion — add ONE UK/EU act to the graph.

Reuses the existing pipeline pieces (adapters -> canonical Documents ->
loader/linker) but bounded to a single seed, so it is fast and safe to run
from the CLI agent or the API. `plan` fetches only (no graph write); `commit`
loads + links.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import io, loader, linker
from .adapters import ADAPTERS
from .adapters import eu as _eu  # noqa: F401  (import registers eu-cellar)
from .adapters import uk as _uk  # noqa: F401  (import registers uk adapters)
from .canonical import Document
from .db import connect, load_dotenv
from .fetch import Fetcher, NotFound

JURIS_ADAPTER = {"uk": "uk-legislation", "eu": "eu-cellar"}
_SEED_KEY = {"uk": "id", "eu": "celex"}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_dataset() -> Path:
    return _root() / "dataset"


def _default_scope() -> Path:
    return _root() / "config" / "scope.yaml"


def _user_agent(scope_path: Path | None = None) -> str:
    scope_path = scope_path or _default_scope()
    if scope_path.exists():
        data = yaml.safe_load(scope_path.read_text()) or {}
        if data.get("user_agent"):
            return data["user_agent"]
    return "legalgraph/0.1"


def build_seed(jurisdiction: str, identifier: str, title: str | None = None,
               concepts: list[str] | None = None) -> dict:
    """A seed dict in scope.yaml's shape. UK keys on `id`, EU on `celex`."""
    if jurisdiction not in _SEED_KEY:
        raise ValueError(f"unknown jurisdiction: {jurisdiction!r}")
    seed: dict = {_SEED_KEY[jurisdiction]: identifier}
    if title:
        seed["title"] = title
    if concepts:
        seed["concepts"] = concepts
    return seed


def minimal_scope(jurisdiction: str, seed: dict) -> dict:
    """In-memory scope with one seed and no expansion. EU disables citing-case
    fetch so only the act itself is collected."""
    block: dict = {"seeds": [seed], "filters": {}}
    if jurisdiction == "eu":
        block["limits"] = {"cases_per_seed": 0, "citations_per_doc": 25}
    return {jurisdiction: block}


def add_seed_to_scope(jurisdiction: str, seed: dict,
                      scope_path: Path | None = None) -> bool:
    """Idempotently append `seed` to scope.yaml. Returns True if added, False if
    an entry with the same id/celex already existed."""
    scope_path = scope_path or _default_scope()
    key = _SEED_KEY[jurisdiction]
    data = yaml.safe_load(scope_path.read_text()) if scope_path.exists() else {}
    data = data or {}
    block = data.setdefault(jurisdiction, {})
    seeds = block.setdefault("seeds", [])
    if any(s.get(key) == seed[key] for s in seeds):
        return False
    seeds.append(seed)
    scope_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return True


def _fetch_docs(jurisdiction: str, seed: dict, dataset: Path) -> list[Document]:
    """Run the jurisdiction's primary adapter for this one seed (cached)."""
    fetcher = Fetcher(dataset / "raw", user_agent=_user_agent())
    adapter = ADAPTERS[JURIS_ADAPTER[jurisdiction]](fetcher)
    docs = adapter.collect(minimal_scope(jurisdiction, seed))
    if not docs:
        raise NotFound(f"no document found for {seed[_SEED_KEY[jurisdiction]]}")
    for d in docs:
        io.write_document(d, dataset / "parsed")
    return docs


def _already_present(doc_id: str) -> bool:
    load_dotenv()
    driver = connect()
    try:
        with driver.session() as s:
            row = s.run(
                "MATCH (d:Document {id: $id}) RETURN count(d) AS n", id=doc_id
            ).single()
            return bool(row and row["n"])
    finally:
        driver.close()


def plan(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict:
    """Fetch only (no graph write). Returns a summary of what would be added."""
    dataset = dataset or _default_dataset()
    docs = _fetch_docs(jurisdiction, seed, dataset)
    act = docs[0]  # both adapters emit the act first
    return {
        "jurisdiction": jurisdiction,
        "identifier": seed[_SEED_KEY[jurisdiction]],
        "title": act.title or act.citation,
        "doc_id": act.id,
        "provision_count": sum(1 for _ in act.all_provisions()),
        "already_present": _already_present(act.id),
    }


def commit(jurisdiction: str, seed: dict, dataset: Path | None = None) -> dict:
    """Load + link this one act into the graph. Returns load/link stats."""
    dataset = dataset or _default_dataset()
    docs = _fetch_docs(jurisdiction, seed, dataset)
    load_dotenv()
    driver = connect()
    try:
        load_stats = loader.load_documents(driver, docs)
        link_stats = linker.link_documents(driver, docs)
    finally:
        driver.close()
    return {
        "documents": load_stats["documents"],
        "provisions": load_stats["provisions"],
        "contains": load_stats["contains"],
        "edges_created": link_stats["created"],
        "unresolved": link_stats["unresolved"],
    }
