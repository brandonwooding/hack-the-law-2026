"""legalgraph CLI — the pipeline entrypoints.

    legalgraph fetch  [--jurisdiction uk]   adapters -> canonical JSON in parsed/
    legalgraph skeleton                      apply constraints + indexes
    legalgraph load   [--dataset DIR]        pass 1: nodes from parsed/*.json
    legalgraph link   [--dataset DIR]        pass 2: edges from parsed/*.json
    legalgraph validate [--citation X]       integrity + navigation queries
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from . import io, loader, linker, skeleton, validator
from .adapters import ADAPTERS
from .adapters import eu as _eu  # noqa: F401  (imports register the EU adapters)
from .adapters import uk as _uk  # noqa: F401  (imports register the UK adapters)
from .db import connect, load_dotenv
from .fetch import Fetcher

_NEEDS_DB = {"skeleton", "load", "link", "validate"}


def _default_dataset() -> Path:
    return Path(__file__).resolve().parents[2] / "dataset"


def _default_scope() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "scope.yaml"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalgraph")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="run source adapters -> parsed/*.json")
    pf.add_argument("--jurisdiction", default="uk")
    pf.add_argument("--sources", nargs="*", default=None, help="adapter names; default all for jurisdiction")
    pf.add_argument("--scope", type=Path, default=_default_scope())
    pf.add_argument("--dataset", type=Path, default=_default_dataset())

    sub.add_parser("skeleton", help="apply constraints + indexes")

    for name in ("load", "link"):
        p = sub.add_parser(name)
        p.add_argument("--dataset", type=Path, default=_default_dataset())

    pv = sub.add_parser("validate")
    pv.add_argument("--citation", default=None)
    pv.add_argument("--provision-id", default=None)

    ps = sub.add_parser("serve", help="run the HTTP API for the UI")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)

    args = ap.parse_args(argv)
    load_dotenv()

    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("legalgraph.api:app", host=args.host, port=args.port)
        return 0

    driver = connect() if args.cmd in _NEEDS_DB else None
    try:
        if args.cmd == "fetch":
            scope = yaml.safe_load(args.scope.read_text())
            fetcher = Fetcher(args.dataset / "raw",
                              user_agent=scope.get("user_agent", "legalgraph/0.1"))
            names = args.sources or sorted(
                n for n in ADAPTERS if n.startswith(args.jurisdiction + "-")
            )
            total = 0
            for name in names:
                print(f"== {name} ==")
                docs = ADAPTERS[name](fetcher).collect(scope)
                for d in docs:
                    io.write_document(d, args.dataset / "parsed")
                total += len(docs)
            print(f"wrote {total} documents to parsed/")

        elif args.cmd == "skeleton":
            n = skeleton.apply(driver)
            print(f"applied {n} DDL statements")

        elif args.cmd == "load":
            concepts = io.read_concepts(args.dataset / "thesaurus")
            if concepts:
                loader.load_concepts(driver, concepts)
                print(f"loaded {len(concepts)} concepts")
            docs = io.read_documents(args.dataset / "parsed")
            stats = loader.load_documents(driver, docs)
            print(f"loaded {stats['documents']} documents, "
                  f"{stats['provisions']} provisions, {stats['contains']} CONTAINS")

        elif args.cmd == "link":
            concepts = io.read_concepts(args.dataset / "thesaurus")
            docs = io.read_documents(args.dataset / "parsed")
            res_c = linker.link_concepts(driver, concepts)
            res_d = linker.link_documents(driver, docs)
            print(f"created {res_c['created']} SKOS edges, {res_d['created']} document edges")
            unresolved = res_c["unresolved"] + res_d["unresolved"]
            if unresolved:
                print(f"WARNING {len(unresolved)} unresolved targets:")
                for src, tgt in unresolved:
                    print(f"  {src} -> {tgt}")

        elif args.cmd == "validate":
            params = {"citation": args.citation, "provision_id": args.provision_id}
            print("== integrity ==")
            print(json.dumps(validator.run_suite(driver, validator.INTEGRITY), indent=2))
            print("== navigation ==")
            print(json.dumps(
                validator.run_suite(driver, validator.NAVIGATION, params), indent=2
            ))
    finally:
        if driver is not None:
            driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
