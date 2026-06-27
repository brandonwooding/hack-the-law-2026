"""GOV.UK adapter — statutory/regulatory guidance related to each seed Act.

Discovery via the GOV.UK Search API; each result becomes a Guidance node
ISSUED_UNDER the Act, tagged with the Act's regulator. (Full body via the
Content API is a later enrichment.)
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from .. import register
from ..base import SourceAdapter

SEARCH = "https://www.gov.uk/api/search.json"
DOC_TYPES = "&filter_content_store_document_type=guidance" \
            "&filter_content_store_document_type=statutory_guidance"


@register("uk-guidance")
class GuidanceAdapter(SourceAdapter):
    source = "uk-guidance"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        per_seed = uk.get("limits", {}).get("guidance_per_seed", 15)
        docs: list[Document] = []
        seen: set[str] = set()

        for seed in uk.get("seeds", []):
            act_id = "uk-" + seed["id"].replace("/", "-")
            title = seed.get("title", "")
            # GOV.UK full-text search is loose, so over-fetch candidates and keep
            # only those whose title/description actually names the Act (drops
            # e.g. building-regs "Approved Documents" that merely match "safety").
            root = re.sub(r"\s+Act\s+\d{4}$", "", title).strip().lower()
            url = f"{SEARCH}?q={quote(title)}{DOC_TYPES}&count={max(per_seed * 3, 45)}"
            results = self.fetcher.get_json(url).get("results", [])
            n = 0
            for r in results:
                if n >= per_seed:
                    break
                link = r.get("link")
                if not link:
                    continue
                blurb = ((r.get("title") or "") + " " + (r.get("description") or "")).lower()
                if root not in blurb:
                    continue
                gid = "uk-guidance-" + link.strip("/").replace("/", "_")
                if gid in seen:
                    continue
                seen.add(gid)
                n += 1
                page = link if link.startswith("http") else f"https://www.gov.uk{link}"
                docs.append(Document(
                    id=gid,
                    jurisdiction=Jurisdiction.UK,
                    type=DocType.GUIDANCE,
                    citation=r.get("title") or gid,
                    title=r.get("title"),
                    status=Status.IN_FORCE,
                    regulator=seed.get("regulator"),
                    concepts=seed.get("concepts"),
                    edges=[Edge(type=EdgeType.ISSUED_UNDER, target=act_id)],
                    source=SourceMeta(url=page, raw_format="govuk-search"),
                ))
            print(f"  [ok] {title}: {n} guidance docs")
        return docs
