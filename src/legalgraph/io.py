"""Read/write canonical Document JSON to/from the dataset's parsed/ dir."""

from __future__ import annotations

import json
from pathlib import Path

from .canonical import Concept, Document


def write_document(doc: Document, parsed_dir: Path) -> Path:
    parsed_dir = Path(parsed_dir)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    path = parsed_dir / f"{doc.id.replace('/', '_')}.json"
    path.write_text(doc.model_dump_json(indent=2, exclude_none=True))
    return path


def read_documents(parsed_dir: Path) -> list[Document]:
    """Load every canonical *.json file in parsed/ (validates against the model)."""
    parsed_dir = Path(parsed_dir)
    docs: list[Document] = []
    for path in sorted(parsed_dir.glob("*.json")):
        docs.append(Document.model_validate_json(path.read_text()))
    return docs


def write_concepts(concepts: list[Concept], thesaurus_dir: Path) -> Path:
    """Write the whole thesaurus to thesaurus/concepts.json."""
    thesaurus_dir = Path(thesaurus_dir)
    thesaurus_dir.mkdir(parents=True, exist_ok=True)
    path = thesaurus_dir / "concepts.json"
    payload = [c.model_dump(exclude_none=True) for c in concepts]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def read_concepts(thesaurus_dir: Path) -> list[Concept]:
    """Load the thesaurus (empty list if none present)."""
    thesaurus_dir = Path(thesaurus_dir)
    concepts: list[Concept] = []
    for path in sorted(thesaurus_dir.glob("*.json")):
        for item in json.loads(path.read_text()):
            concepts.append(Concept.model_validate(item))
    return concepts
