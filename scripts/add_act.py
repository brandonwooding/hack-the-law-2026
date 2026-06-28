#!/usr/bin/env python
"""One-shot CLI: add a UK/EU act to the graph from a natural-language request.

    python scripts/add_act.py "add the AI Act from the EU"
    python scripts/add_act.py "add the Equality Act 2010 from the UK" --yes

Prompts y/n in the terminal before anything writes to Neo4j, unless --yes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legalgraph import agent  # noqa: E402


def _build_confirm(auto_yes: bool):
    async def confirm(tool_name: str, tool_input: dict) -> bool:
        if auto_yes:
            return True
        desc = tool_input.get("command", tool_name)
        ans = input(f"\n[write] About to run: {desc}\nProceed? [y/N] ").strip().lower()
        return ans in ("y", "yes")
    return confirm


async def _main_async(request: str, model: str | None, auto_yes: bool) -> int:
    confirm = _build_confirm(auto_yes)
    summary = await agent.run_agent(request, model=model, confirm=confirm)
    print("\n=== summary ===")
    print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add a UK/EU act to the graph")
    ap.add_argument("request", help="natural-language request, e.g. 'add the AI Act from the EU'")
    ap.add_argument("--model", default=None)
    ap.add_argument("--yes", action="store_true", help="auto-approve writes")
    args = ap.parse_args(argv)
    return asyncio.run(_main_async(args.request, args.model, args.yes))


if __name__ == "__main__":
    raise SystemExit(main())
