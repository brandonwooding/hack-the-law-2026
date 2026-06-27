"""Statutory Instruments API (Parliament) — SIs made under each seed Act.

Gives the parliamentary metadata + the enabling-Act linkage (MADE_UNDER) that
legislation.gov.uk doesn't expose cleanly. SI ids are built in legislation.gov.uk
form (uk-uksi-{year}-{number}) so they merge if we later pull the SI text.
"""

from __future__ import annotations

from urllib.parse import quote

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from .. import register
from ..base import SourceAdapter

BASE = "https://statutoryinstruments-api.parliament.uk/api/v2"


@register("uk-si-parliament")
class SIParliamentAdapter(SourceAdapter):
    source = "uk-si-parliament"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        per_seed = uk.get("limits", {}).get("sis_per_seed", 30)
        docs: list[Document] = []

        for seed in uk.get("seeds", []):
            act_id = "uk-" + seed["id"].replace("/", "-")
            title = seed.get("title", "")
            aop_id = self._act_of_parliament_id(title, seed["id"])
            if not aop_id:
                print(f"  [skip] no Parliament Act match for {title}")
                continue

            url = (f"{BASE}/StatutoryInstrument?ActOfParliamentId={aop_id}"
                   f"&take={per_seed}&skip=0")
            data = self.fetcher.get_json(url)
            items = data.get("items", [])
            for it in items:
                v = it.get("value", it)
                year, num = v.get("paperYear"), v.get("paperNumber")
                si_id = f"uk-uksi-{year}-{num}" if year and num else f"uk-si-{v.get('id')}"
                proc = (v.get("procedure") or {}).get("name")
                docs.append(Document(
                    id=si_id,
                    jurisdiction=Jurisdiction.UK,
                    type=DocType.STATUTORY_INSTRUMENT,
                    citation=v.get("name") or si_id,
                    title=v.get("name"),
                    date_enacted=(v.get("paperMadeDate") or "")[:10] or None,
                    status=Status.IN_FORCE,
                    regulator=seed.get("regulator"),
                    concepts=seed.get("concepts"),
                    subject_tags=[f"procedure:{proc}"] if proc else [],
                    edges=[Edge(type=EdgeType.MADE_UNDER, target=act_id)],
                    source=SourceMeta(
                        url=f"https://www.legislation.gov.uk/uksi/{year}/{num}"
                            if year and num else None,
                        raw_format="json"),
                ))
            print(f"  [ok] {title}: {len(items)} SIs")
        return docs

    def _act_of_parliament_id(self, title: str, leg_id: str) -> str | None:
        """Resolve a seed Act to the SI-API's ActOfParliamentId, matching on the
        legislation.gov.uk link so we don't pick a same-named Act by accident."""
        data = self.fetcher.get_json(f"{BASE}/ActOfParliament?Name={quote(title)}&take=10")
        items = data if isinstance(data, list) else data.get("items", [])
        for it in items:
            v = it.get("value", it) if isinstance(it, dict) else it
            if leg_id in (v.get("link") or ""):
                return v.get("id")
        return None
