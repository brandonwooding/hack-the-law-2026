"""Ingest the high-value regulator documents for the Online Safety Act regime.

Ofcom documents are PDFs and are parsed page-by-page with NVIDIA Nemotron Parse.
ICO documents are HTML guidance, so they are parsed directly into provisions.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legalgraph.adapters.uk.regulator_documents import parse_pdf_with_nvidia  # noqa: E402
from legalgraph.canonical import (  # noqa: E402
    Document,
    DocType,
    Edge,
    EdgeType,
    Jurisdiction,
    LegalForce,
    Provision,
    SourceMeta,
    Status,
)
from legalgraph.db import load_dotenv  # noqa: E402
from legalgraph.fetch import Fetcher  # noqa: E402
from legalgraph.io import write_document  # noqa: E402

OSA = "uk-ukpga-2023-50"
DPA = "uk-ukpga-2018-12"


@dataclass(frozen=True)
class PdfDoc:
    id: str
    citation: str
    url: str
    concepts: list[str]


OFCOM_PDFS = [
    PdfDoc(
        "uk-ofcom-guidance-osa-risk-assessment-2026",
        "Risk Assessment Guidance and Risk Profiles",
        "https://www.ofcom.org.uk/siteassets/resources/documents/online-safety/information-for-industry/illegal-harms/updates/risk-assessment-guidance-and-risk-profiles.pdf?v=419947",
        ["eurovoc:online-safety"],
    ),
    PdfDoc(
        "uk-ofcom-guidance-osa-illegal-content-code-u2u-2025",
        "Illegal content Codes of Practice for user-to-user services",
        "https://www.ofcom.org.uk/siteassets/resources/documents/online-safety/information-for-industry/illegal-harms/illegal-content-codes-of-practice-for-user-to-user-services-24-feb.pdf?v=391889",
        ["eurovoc:online-safety"],
    ),
    PdfDoc(
        "uk-ofcom-guidance-osa-childrens-risk-assessment-2025",
        "Children's Risk Assessment Guidance and Children's Risk Profiles",
        "https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-1-10-weeks/statement-protecting-children-from-harms-online/main-document/childrens-risk-assessment-guidance-and-childrens-risk-profiles.pdf?v=396653",
        ["eurovoc:online-safety"],
    ),
    PdfDoc(
        "uk-ofcom-guidance-osa-protection-children-code-u2u-2025",
        "Issued Protection of Children Code of Practice for user-to-user services",
        "https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-1-10-weeks/statement-protecting-children-from-harms-online/main-document/protection-of-children-code-of-practice-for-user-to-user-services.pdf?v=403579",
        ["eurovoc:online-safety"],
    ),
    PdfDoc(
        "uk-ofcom-guidance-osa-enforcement-2026",
        "Online Safety Enforcement Guidance",
        "https://www.ofcom.org.uk/siteassets/resources/documents/online-safety/information-for-industry/illegal-harms/online-safety-enforcement-guidance.pdf?v=414891",
        ["eurovoc:online-safety", "eurovoc:electronic-communications"],
    ),
]


@dataclass(frozen=True)
class HtmlDoc:
    id: str
    citation: str
    url: str
    legal_effect: str


ICO_HTML = [
    HtmlDoc(
        "uk-ico-guidance-childrens-code",
        "Age appropriate design: a code of practice for online services",
        "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/",
        "statutory_guidance",
    ),
    HtmlDoc(
        "uk-ico-guidance-children-and-uk-gdpr",
        "Children and the UK GDPR",
        "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/children-and-the-uk-gdpr/",
        "non_binding_guidance",
    ),
]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "section"


class _GuideParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links: list[tuple[str, str]] = []
        self.parts: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "a" and attrs_d.get("href"):
            self._href = urllib.parse.urljoin(self.base, attrs_d["href"] or "")
            self._text = []
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self._tag = tag
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href or self._tag:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = " ".join(" ".join(self._text).split())
        if tag == "a" and self._href:
            self.links.append((self._href, text))
            self._href = None
            self._text = []
        if self._tag == tag:
            if text:
                self.parts.append((tag, text))
            self._tag = None
            self._text = []


def _fetch_html(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "legalgraph/0.1"})
    body = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def _page_to_provision(doc_id: str, index: int, url: str, title: str, html: str) -> Provision:
    parser = _GuideParser(url)
    parser.feed(html)
    heading = title
    lines: list[str] = []
    for tag, text in parser.parts:
        if tag in {"h1", "h2"} and not lines:
            heading = text
        elif tag in {"p", "li", "h2", "h3"}:
            lines.append(text)
    return Provision(
        id=f"{doc_id}/section/{index}-{_slug(heading)[:48]}",
        number=str(index),
        heading=heading,
        text="\n".join(lines[:250]),
        url=url,
        legal_force=LegalForce.GUIDANCE,
    )


def _html_children(root_url: str, html: str, max_pages: int) -> list[tuple[str, str]]:
    parser = _GuideParser(root_url)
    parser.feed(html)
    base = root_url.rstrip("/") + "/"
    out: list[tuple[str, str]] = [(root_url, "Overview")]
    seen = {root_url.rstrip("/")}
    for href, text in parser.links:
        clean = href.split("#", 1)[0].rstrip("/")
        if clean in seen or not clean.startswith(base.rstrip("/")):
            continue
        if not text or "download registration" in text.lower():
            continue
        seen.add(clean)
        out.append((clean + "/", text))
        if len(out) >= max_pages:
            break
    return out


def build_ofcom_doc(fetcher: Fetcher, spec: PdfDoc, parsed_dir: Path,
                    max_pages: int | None, render_scale: float) -> Document:
    body, pdf_path = fetcher.get_bytes(spec.url, accept="application/pdf", ext="pdf")
    ocr = parse_pdf_with_nvidia(
        pdf_path,
        spec.id,
        "nvidia/nemotron-parse",
        max_pages=max_pages,
        render_scale=render_scale,
    )
    provisions = []
    for i, item in enumerate(ocr.get("sections") or [], start=1):
        provisions.append(Provision(
            id=f"{spec.id}/section/{i}-{_slug(str(item.get('heading') or item.get('number') or i))[:48]}",
            number=str(item.get("number") or i),
            heading=item.get("heading"),
            text=item.get("text"),
            url=spec.url,
            legal_force=LegalForce.GUIDANCE,
            page_start=item.get("page_start"),
            page_end=item.get("page_end"),
        ))
    doc = Document(
        id=spec.id,
        jurisdiction=Jurisdiction.UK,
        type=DocType.GUIDANCE,
        citation=spec.citation,
        title=spec.citation,
        status=Status.IN_FORCE,
        regulator="Office of Communications (Ofcom)",
        publisher="Ofcom",
        document_kind="guidance",
        legal_effect="statutory_guidance",
        subject_tags=["online safety", "ofcom"],
        concepts=spec.concepts,
        provisions=provisions,
        edges=[Edge(type=EdgeType.ISSUED_UNDER, target=OSA)],
        landing_page_url="https://www.ofcom.org.uk/online-safety/illegal-and-harmful-content/online-safety-regulatory-documents",
        pdf_url=spec.url,
        ocr_model=ocr.get("ocr_model"),
        ocr_parsed_at=ocr.get("ocr_parsed_at"),
        parse_version="regulator-pdf-v1",
        source=SourceMeta(url=spec.url, hash=hashlib.sha256(body).hexdigest(), raw_format="pdf"),
    )
    write_document(doc, parsed_dir)
    return doc


def build_ico_doc(spec: HtmlDoc, parsed_dir: Path, max_pages: int) -> Document:
    root_html, root_hash = _fetch_html(spec.url)
    children = _html_children(spec.url, root_html, max_pages=max_pages)
    provisions: list[Provision] = []
    for i, (url, title) in enumerate(children, start=1):
        html = root_html if i == 1 else _fetch_html(url)[0]
        provisions.append(_page_to_provision(spec.id, i, url, title, html))
    doc = Document(
        id=spec.id,
        jurisdiction=Jurisdiction.UK,
        type=DocType.GUIDANCE,
        citation=spec.citation,
        title=spec.citation,
        status=Status.IN_FORCE,
        regulator="Information Commissioner's Office (ICO)",
        publisher="Information Commissioner's Office",
        document_kind="guidance",
        legal_effect=spec.legal_effect,
        subject_tags=["online safety", "data protection", "children", "ico"],
        concepts=["eurovoc:online-safety", "eurovoc:dp"],
        provisions=provisions,
        edges=[Edge(type=EdgeType.ISSUED_UNDER, target=DPA)],
        landing_page_url=spec.url,
        source=SourceMeta(url=spec.url, hash=root_hash, raw_format="html"),
    )
    write_document(doc, parsed_dir)
    return doc


def main() -> int:
    load_dotenv()
    dataset = ROOT / "dataset"
    parsed_dir = dataset / "parsed"
    fetcher = Fetcher(dataset / "raw", user_agent="legalgraph/0.1")
    max_pages = int(os.environ["OSA_REGDOC_MAX_PAGES"]) if "OSA_REGDOC_MAX_PAGES" in os.environ else None
    render_scale = float(os.environ.get("OSA_REGDOC_RENDER_SCALE", "1.5"))
    ico_pages = int(os.environ.get("OSA_ICO_MAX_PAGES", "40"))

    docs: list[Document] = []
    for spec in OFCOM_PDFS:
        print(f"== Ofcom: {spec.citation} ==")
        doc = build_ofcom_doc(fetcher, spec, parsed_dir, max_pages, render_scale)
        print(f"  wrote {doc.id}: {len(doc.provisions)} provisions")
        docs.append(doc)
    for spec in ICO_HTML:
        print(f"== ICO: {spec.citation} ==")
        doc = build_ico_doc(spec, parsed_dir, ico_pages)
        print(f"  wrote {doc.id}: {len(doc.provisions)} provisions")
        docs.append(doc)
    print(f"wrote {len(docs)} OSA regulator documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
