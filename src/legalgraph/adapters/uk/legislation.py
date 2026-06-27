"""legislation.gov.uk adapter — Acts & SIs (text + structure) + explanatory notes.

The backbone source: it alone fills the Provision tree, explanatory-note nodes,
and (later) amendment edges. One whole-document CLML request per Act keeps us
well under the 3000-requests/5-min limit.
"""

from __future__ import annotations

from ...canonical import Document, DocType, Edge, EdgeType, Jurisdiction, SourceMeta, Status
from ...fetch import NotFound
from .. import register
from ..base import SourceAdapter
from . import clml

BASE = "https://www.legislation.gov.uk"


@register("uk-legislation")
class LegislationAdapter(SourceAdapter):
    source = "uk-legislation"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        enacted_from = uk.get("filters", {}).get("enacted_from")
        docs: list[Document] = []

        for seed in uk.get("seeds", []):
            leg_id = seed["id"]
            url = f"{BASE}/{leg_id}/data.xml"
            try:
                xml, _ = self.fetcher.get(url)
            except NotFound:
                print(f"  [skip] {leg_id}: 404")
                continue

            doc = clml.parse_document(
                xml, leg_id,
                regulator=seed.get("regulator"),
                concepts=seed.get("concepts"),
                source_url=f"{BASE}/{leg_id}",
            )

            # date guard
            if enacted_from and doc.date_enacted and doc.date_enacted < enacted_from:
                print(f"  [skip] {doc.citation}: enacted {doc.date_enacted} < {enacted_from}")
                continue

            docs.append(doc)
            n_prov = sum(1 for _ in doc.all_provisions())
            print(f"  [ok] {doc.citation}  ({doc.type.value}, {n_prov} provisions)")

            # explanatory notes -> own node, EXPLAINS the Act (per-section EXPLAINS: TODO).
            # Detected from the Act XML's own navigation link (no extra request).
            en_url = clml.notes_url(xml)
            if en_url:
                docs.append(Document(
                    id=f"{doc.id}-en",
                    jurisdiction=Jurisdiction.UK,
                    type=DocType.EXPLANATORY_NOTE,
                    citation=f"{doc.citation} — Explanatory Notes",
                    status=Status.IN_FORCE,
                    regulator=doc.regulator,
                    edges=[Edge(type=EdgeType.EXPLAINS, target=doc.id)],
                    source=SourceMeta(url=en_url, raw_format="html"),
                ))
                print(f"  [ok] {doc.citation} — Explanatory Notes")

        return docs
