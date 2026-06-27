"""Find Case Law (TNA) — judgments that actually cite each seed Act.

LICENCE: the Open Justice Licence bars computational analysis without a free
application to caselaw@nationalarchives.gov.uk. This adapter is deliberately
low-volume (capped per seed) for development until that permission is granted.

Full-text search is loose, so we fetch each candidate's Akoma Ntoso and only
create a CONSIDERS edge if the Act is genuinely referenced (act-level; provision-
level citation parsing from AKN is a later enrichment).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from ...fetch import NotFound
from .. import register
from ..base import SourceAdapter

BASE = "https://caselaw.nationalarchives.gov.uk"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


@register("uk-caselaw")
class CaseLawAdapter(SourceAdapter):
    source = "uk-caselaw"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        per_seed = uk.get("limits", {}).get("cases_per_seed", 10)
        docs: list[Document] = []
        seen: set[str] = set()

        for seed in uk.get("seeds", []):
            act_id = "uk-" + seed["id"].replace("/", "-")
            title = seed.get("title", "")
            url = f"{BASE}/atom.xml?query={quote(title)}&per_page={per_seed}"
            feed, _ = self.fetcher.get(url, accept="application/atom+xml", ext="xml")
            entries = ET.fromstring(feed).findall("a:entry", ATOM)

            kept = 0
            for e in entries:
                akn = self._akn_link(e)
                if not akn:
                    continue
                page = akn[:-len("/data.xml")] if akn.endswith("/data.xml") else akn
                cid = "uk-" + page.split("legislation")[-1].split(".uk/")[-1].strip("/").replace("/", "-")
                if cid in seen:
                    continue
                # verify the judgment really cites this Act
                try:
                    body, _ = self.fetcher.get(akn, accept="application/akn+xml", ext="xml")
                except NotFound:
                    continue
                if title.lower() not in body.lower():
                    continue
                seen.add(cid)
                kept += 1
                ctitle = (e.findtext("a:title", default="", namespaces=ATOM) or cid).strip()
                level = page.rstrip("/").split(".uk/")[-1].split("/")[0].upper()
                docs.append(Document(
                    id=cid,
                    jurisdiction=Jurisdiction.UK,
                    type=DocType.CASE,
                    citation=ctitle,
                    title=ctitle,
                    date_decided=(e.findtext("a:published", default="", namespaces=ATOM) or "")[:10] or None,
                    status=Status.IN_FORCE,
                    level=level,
                    concepts=seed.get("concepts"),
                    edges=[Edge(type=EdgeType.CONSIDERS, target=act_id)],
                    source=SourceMeta(url=page, raw_format="akoma-ntoso"),
                ))
            print(f"  [ok] {title}: {kept}/{len(entries)} cases cite the Act")
        return docs

    @staticmethod
    def _akn_link(entry: ET.Element) -> str | None:
        for link in entry.findall("a:link", ATOM):
            if link.get("type") == "application/akn+xml":
                return link.get("href")
        return None
