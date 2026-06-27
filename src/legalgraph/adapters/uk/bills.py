"""Bills API (Parliament) — the Bill that became each seed Act.

Matches the Bill by name and, when it became law (isAct), links Bill -> Act
via BECAME. Bill ids are uk-bill-{billId}.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from .. import register
from ..base import SourceAdapter

BASE = "https://bills-api.parliament.uk/api/v1"


def _root_name(title: str) -> str:
    """'Online Safety Act 2023' -> 'Online Safety'."""
    return re.sub(r"\s+Act\s+\d{4}$", "", title).strip()


@register("uk-bills")
class BillsAdapter(SourceAdapter):
    source = "uk-bills"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        docs: list[Document] = []

        for seed in uk.get("seeds", []):
            act_id = "uk-" + seed["id"].replace("/", "-")
            root = _root_name(seed.get("title", ""))
            data = self.fetcher.get_json(
                f"{BASE}/Bills?SearchTerm={quote(root)}&Take=20")
            bill = self._best_match(data.get("items", []), root)
            if not bill:
                print(f"  [skip] no Bill match for {root}")
                continue
            became = bill.get("isAct")
            docs.append(Document(
                id=f"uk-bill-{bill['billId']}",
                jurisdiction=Jurisdiction.UK,
                type=DocType.BILL,
                citation=bill.get("shortTitle") or f"Bill {bill['billId']}",
                title=bill.get("shortTitle"),
                status=Status.IN_FORCE if became else Status.PROSPECTIVE,
                regulator=seed.get("regulator"),
                concepts=seed.get("concepts"),
                edges=[Edge(type=EdgeType.BECAME, target=act_id)] if became else [],
                source=SourceMeta(
                    url=f"https://bills.parliament.uk/bills/{bill['billId']}",
                    raw_format="json"),
            ))
            print(f"  [ok] {root}: bill {bill['billId']} "
                  f"({'became Act' if became else 'did not pass'})")
        return docs

    @staticmethod
    def _best_match(items: list[dict], root: str) -> dict | None:
        rl = root.lower()
        # prefer an exact "<root> Bill" that became an Act
        cands = [b for b in items if (b.get("shortTitle") or "").lower().startswith(rl)]
        cands.sort(key=lambda b: (not b.get("isAct"), len(b.get("shortTitle") or "")))
        return cands[0] if cands else None
