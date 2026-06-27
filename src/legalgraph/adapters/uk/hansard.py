"""Hansard API (modern) — debates mentioning each seed Act/Bill.

Each debate becomes a HansardDebate node, linked (Act)-[:DEBATED_IN]->(Debate)
via a reversed edge (the Act, created elsewhere, is the source of DEBATED_IN).
We model at debate-section level (not per-speech) to keep volume sane.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from .. import register
from ..base import SourceAdapter

BASE = "https://hansard-api.parliament.uk"          # the JSON API
SITE = "https://hansard.parliament.uk"              # the human-readable site


def _slug(title: str) -> str:
    """'Online Safety Act 2023: Repeal' -> 'OnlineSafetyAct2023Repeal'
    (Hansard's URL slug form: alphanumeric tokens, each capitalised, joined)."""
    return "".join(t[:1].upper() + t[1:] for t in re.findall(r"[A-Za-z0-9]+", title))


def _debate_url(house: str | None, date: str | None, ext: str, title: str) -> str:
    """Human-readable hansard.parliament.uk page; falls back to the API if we
    lack the house/date needed to build it."""
    if house and date:
        return f"{SITE}/{house}/{date}/debates/{ext}/{_slug(title)}"
    return f"{BASE}/debates/debate/{ext}.json"


@register("uk-hansard")
class HansardAdapter(SourceAdapter):
    source = "uk-hansard"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        per_seed = uk.get("limits", {}).get("debates_per_bill", 25)
        docs: list[Document] = []
        seen: set[str] = set()

        for seed in uk.get("seeds", []):
            act_id = "uk-" + seed["id"].replace("/", "-")
            term = seed.get("title", "")
            url = (f"{BASE}/search/debates.json"
                   f"?queryParameters.searchTerm={quote(term)}"
                   f"&queryParameters.take={per_seed}")
            data = self.fetcher.get_json(url)
            results = data.get("Results") or data.get("results") or []
            n = 0
            for r in results:
                ext = (r.get("DebateSectionExtId") or r.get("debateSectionExtId")
                       or r.get("ExternalId"))
                if not ext or ext in seen:
                    continue
                seen.add(ext)
                n += 1
                dtitle = r.get("Title") or r.get("title") or "Debate"
                date = (r.get("SittingDate") or r.get("sittingDate") or "")[:10] or None
                house = r.get("House") or r.get("house")
                docs.append(Document(
                    id=f"uk-hansard-{ext}",
                    jurisdiction=Jurisdiction.UK,
                    type=DocType.HANSARD_DEBATE,
                    citation=f"{dtitle} (Hansard{', ' + house if house else ''})",
                    title=dtitle,
                    date_decided=date,
                    status=Status.IN_FORCE,
                    # (Act)-[:DEBATED_IN]->(this debate)
                    edges=[Edge(type=EdgeType.DEBATED_IN, target=act_id, reverse=True)],
                    source=SourceMeta(
                        url=_debate_url(house, date, ext, dtitle), raw_format="html"),
                ))
            print(f"  [ok] {term}: {n} debates")
        return docs
