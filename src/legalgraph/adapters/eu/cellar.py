"""CELLAR / EUR-Lex adapter for EU legislation and case law.

CELLAR RDF gives stable metadata and authority-graph links; the English XHTML
manifestation gives the document anatomy. We seed by CELEX because it is stable
and maps cleanly to both sources:

    metadata: Publications Office SPARQL endpoint
    text:     https://publications.europa.eu/resource/celex/{CELEX}.ENG.xhtml

Regulatory guidance is deliberately out of scope for this adapter. EU guidance
often lives in Commission/agency sites and should be handled by source-specific
adapters once the legal backbone is in place.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from html import unescape
from typing import Iterable

from ...canonical import (
    DocType, Document, Edge, EdgeType, Jurisdiction, LegalForce, Provision,
    SourceMeta, Status,
)
from ...fetch import NotFound
from .. import register
from ..base import SourceAdapter

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR = "https://publications.europa.eu/resource/cellar"
CELEX_RESOURCE = "http://publications.europa.eu/resource/celex"
CDM = "http://publications.europa.eu/ontology/cdm#"
OWL = "http://www.w3.org/2002/07/owl#"
XHTML = "http://www.w3.org/1999/xhtml"


class _TolerantTreeParser(HTMLParser):
    """Build a small ElementTree from imperfect EUR-Lex HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("html")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        el = ET.Element(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].append(el)
        self.stack.append(el)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if not data:
            return
        cur = self.stack[-1]
        if len(cur):
            last = cur[-1]
            last.tail = (last.tail or "") + data
        else:
            cur.text = (cur.text or "") + data


def _parse_markup(markup: str) -> ET.Element:
    try:
        return ET.fromstring(markup)
    except ET.ParseError:
        parser = _TolerantTreeParser()
        parser.feed(markup)
        return parser.root


def _ln(tag: str) -> str:
    return tag.split("}")[-1]


def _text(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", unescape(" ".join(t.strip() for t in el.itertext()))).strip()


def _class_attr(el: ET.Element) -> set[str]:
    return set((el.attrib.get("class") or "").split())


def _local_id(celex: str) -> str:
    safe = celex.replace("/", "_").replace("(", "_").replace(")", "_")
    return f"eu-celex-{safe}"


def _celex_uri(celex: str) -> str:
    return f"{CELEX_RESOURCE}/{urllib.parse.quote(celex, safe='')}"


def _doc_type(celex: str, title: str, resource_type: str | None) -> DocType:
    if celex.startswith("1"):
        return DocType.TREATY
    if celex.startswith("6"):
        return DocType.CASE
    upper_title = title.upper()
    if re.search(r"\b(COMMISSION\s+)?(IMPLEMENTING|DELEGATED)\s+(REGULATION|DIRECTIVE|DECISION)\b", upper_title):
        return DocType.REGULATORY_INSTRUMENT
    return DocType.ACT


def _case_level(celex: str) -> tuple[str | None, str | None]:
    if not celex.startswith("6") or len(celex) < 6:
        return None, None
    marker = celex[5].upper()
    if marker in {"C", "J", "O"}:
        return "Court of Justice of the European Union", "CJEU"
    if marker in {"T", "B"}:
        return "General Court", "EGC"
    return "Court of Justice of the European Union", "CJEU"


def _status(in_force: str | None, end_validity: str | None) -> Status:
    if in_force == "1" or in_force == "true":
        return Status.IN_FORCE
    if end_validity and end_validity != "9999-12-31":
        return Status.REPEALED
    return Status.UNKNOWN


def _first(binding: dict, name: str) -> str | None:
    item = binding.get(name)
    return item["value"] if item else None


def _dedupe_edges(edges: Iterable[Edge]) -> list[Edge]:
    seen: set[tuple[str, str, str | None]] = set()
    out: list[Edge] = []
    for edge in edges:
        key = (edge.type.value, edge.target, edge.source_ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _article_number(label: str, fallback: str) -> str:
    match = re.search(r"Article\s+([0-9A-Za-z]+)", label.replace("\xa0", " "))
    if match:
        return match.group(1)
    match = re.search(r"art_([0-9A-Za-z]+)", fallback)
    return match.group(1) if match else fallback


def _flat_article_fallback(
    celex: str,
    root: ET.Element,
    source_url: str,
) -> tuple[str | None, list[Provision]]:
    paragraphs = [_text(el) for el in root.iter() if _ln(el.tag) == "p" and _text(el)]
    title_parts: list[str] = []
    for item in paragraphs[:20]:
        if item.startswith("THE EUROPEAN") or item.startswith("Having regard"):
            break
        if item.lower().startswith("avis juridique"):
            continue
        if item:
            title_parts.append(item)
    title = " ".join(title_parts[:4]) or None

    starts: list[tuple[int, str]] = []
    for i, item in enumerate(paragraphs):
        match = re.fullmatch(r"Article\s+([0-9A-Za-z]+)", item)
        if match:
            starts.append((i, match.group(1)))

    provisions: list[Provision] = []
    for pos, (start, number) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(paragraphs)
        chunk = paragraphs[start + 1:end]
        while chunk and not chunk[0]:
            chunk.pop(0)
        heading = None
        if chunk and not re.match(r"^\d+\.", chunk[0]):
            heading = chunk.pop(0)
        body = " ".join(chunk).strip()
        children: list[Provision] = []
        for item in chunk:
            match = re.match(r"^(\d+)\.\s+", item)
            if not match:
                continue
            para_no = match.group(1)
            children.append(Provision(
                id=f"{_local_id(celex)}/art/{number}/para/{para_no}",
                number=para_no,
                text=item,
                url=f"{source_url}#art_{number}",
            ))
        provisions.append(Provision(
            id=f"{_local_id(celex)}/art/{number}",
            number=number,
            heading=heading,
            text=body or None,
            url=f"{source_url}#art_{number}",
            children=children,
        ))
    return title, provisions


def _first_direct_text_by_class(el: ET.Element, class_name: str) -> str | None:
    for child in el:
        if class_name in _class_attr(child):
            value = _text(child)
            if value:
                return value
        if _ln(child.tag) == "div":
            for grandchild in child:
                if class_name in _class_attr(grandchild):
                    value = _text(grandchild)
                    if value:
                        return value
    return None


def parse_xhtml(celex: str, html: str, source_url: str) -> tuple[str, list[Provision]]:
    """Return title and Article -> paragraph provisions from CELLAR XHTML."""
    root = _parse_markup(html)
    title_parts: list[str] = []
    for el in root.iter():
        if "eli-main-title" in _class_attr(el):
            title_parts = [_text(child) for child in el if _text(child)]
            break
    if not title_parts:
        title_parts = [_text(el) for el in root.iter() if _ln(el.tag) == "title" and _text(el)]
    title = " ".join(title_parts).strip() or celex

    provisions: list[Provision] = []
    for article in root.iter():
        if _ln(article.tag) != "div":
            continue
        art_id = article.attrib.get("id", "")
        if not re.fullmatch(r"art_\d+[A-Za-z]?", art_id):
            continue

        label = _first_direct_text_by_class(article, "oj-ti-art") or art_id
        number = _article_number(label, art_id)
        heading = _first_direct_text_by_class(article, "oj-sti-art")
        paragraphs: list[Provision] = []
        body_parts: list[str] = []

        for child in article:
            child_id = child.attrib.get("id", "")
            if not re.fullmatch(r"\d{3}\.\d{3}", child_id):
                continue
            p_text = _text(child)
            if not p_text:
                continue
            para_no = child_id.split(".")[-1].lstrip("0") or child_id
            pid = f"{_local_id(celex)}/art/{number}/para/{para_no}"
            paragraphs.append(Provision(
                id=pid,
                number=para_no,
                text=p_text,
                url=f"{source_url}#{child_id}",
                legal_force=LegalForce.OPERATIVE,
            ))
            body_parts.append(p_text)

        if not body_parts:
            for child in article:
                if "oj-ti-art" in _class_attr(child) or "eli-title" in _class_attr(child):
                    continue
                text = _text(child)
                if text:
                    body_parts.append(text)

        provisions.append(Provision(
            id=f"{_local_id(celex)}/art/{number}",
            number=number,
            heading=heading,
            text=" ".join(body_parts) or None,
            url=f"{source_url}#{art_id}",
            legal_force=LegalForce.OPERATIVE,
            children=paragraphs,
        ))

    if not provisions:
        flat_title, provisions = _flat_article_fallback(celex, root, source_url)
        if flat_title:
            title = flat_title

    return title, provisions


@register("eu-cellar")
class CellarAdapter(SourceAdapter):
    source = "eu-cellar"
    jurisdiction = Jurisdiction.EU

    def collect(self, scope: dict) -> list[Document]:
        eu = scope.get("eu", {})
        enacted_from = eu.get("filters", {}).get("enacted_from")
        cases_per_seed = eu.get("limits", {}).get("cases_per_seed", 8)
        citations_per_doc = eu.get("limits", {}).get("citations_per_doc", 25)

        docs: list[Document] = []
        seen: set[str] = set()

        for seed in eu.get("seeds", []):
            celex = seed["celex"]
            doc = self._document_from_celex(celex, seed, citations_per_doc)
            if not doc:
                continue
            if enacted_from and doc.date_enacted and doc.date_enacted < enacted_from:
                print(f"  [skip] {doc.citation}: date {doc.date_enacted} < {enacted_from}")
                continue
            docs.append(doc)
            seen.add(doc.celex or celex)
            print(f"  [ok] {doc.citation}  ({doc.type.value}, {sum(1 for _ in doc.all_provisions())} provisions)")

            if cases_per_seed:
                for case_celex in self._case_celexes_citing(celex, cases_per_seed):
                    if case_celex in seen:
                        continue
                    case_doc = self._document_from_celex(
                        case_celex,
                        {
                            "celex": case_celex,
                            "concepts": seed.get("concepts", []),
                            "considers": celex,
                        },
                        citations_per_doc=0,
                    )
                    if not case_doc:
                        continue
                    docs.append(case_doc)
                    seen.add(case_celex)
                print(f"  [ok] {celex}: added {len([d for d in docs if d.type == DocType.CASE])} total EU cases so far")

        return docs

    def _get_json(self, query: str) -> dict:
        url = SPARQL + "?" + urllib.parse.urlencode({
            "query": query,
            "format": "application/sparql-results+json",
        })
        body, _ = self.fetcher.get(
            url,
            accept="application/sparql-results+json",
            ext="json",
        )
        return json.loads(body)

    def _celex_graph(self, celex: str) -> tuple[str, str] | None:
        query = f"""
PREFIX owl: <{OWL}>
SELECT ?g ?work WHERE {{
  GRAPH ?g {{ ?work owl:sameAs <{_celex_uri(celex)}> }}
}} LIMIT 1
"""
        rows = self._get_json(query).get("results", {}).get("bindings", [])
        if not rows:
            return None
        return rows[0]["g"]["value"], rows[0]["work"]["value"]

    def _metadata(self, graph: str, work: str) -> dict[str, str]:
        query = f"""
PREFIX cdm: <{CDM}>
SELECT ?celex ?date ?entry ?end ?inForce ?resourceType WHERE {{
  GRAPH <{graph}> {{
    <{work}> cdm:resource_legal_id_celex ?celex .
    OPTIONAL {{ <{work}> cdm:work_date_document ?date }}
    OPTIONAL {{ <{work}> cdm:resource_legal_date_entry-into-force ?entry }}
    OPTIONAL {{ <{work}> cdm:resource_legal_date_end-of-validity ?end }}
    OPTIONAL {{ <{work}> cdm:resource_legal_in-force ?inForce }}
    OPTIONAL {{
      <{work}> cdm:work_has_resource-type ?rt .
      BIND(REPLACE(STR(?rt), "^.*/", "") AS ?resourceType)
    }}
  }}
}} LIMIT 10
"""
        rows = self._get_json(query).get("results", {}).get("bindings", [])
        merged: dict[str, str] = {}
        for row in rows:
            for key in ("celex", "date", "entry", "end", "inForce", "resourceType"):
                if key not in merged:
                    value = _first(row, key)
                    if value:
                        merged[key] = value
        return merged

    def _linked_celexes(self, graph: str, work: str, predicate: str, limit: int) -> list[str]:
        query = f"""
PREFIX cdm: <{CDM}>
SELECT DISTINCT ?celex WHERE {{
  GRAPH <{graph}> {{ <{work}> cdm:{predicate} ?target . }}
  GRAPH ?tg {{ ?target cdm:resource_legal_id_celex ?celex . }}
}} LIMIT {limit}
"""
        rows = self._get_json(query).get("results", {}).get("bindings", [])
        return [_first(row, "celex") for row in rows if _first(row, "celex")]

    def _case_celexes_citing(self, celex: str, limit: int) -> list[str]:
        resolved = self._celex_graph(celex)
        if not resolved:
            return []
        _, work = resolved
        query = f"""
PREFIX cdm: <{CDM}>
SELECT DISTINCT ?celex ?date WHERE {{
  GRAPH ?g {{ ?case cdm:work_cites_work <{work}> . }}
  GRAPH ?cg {{
    ?case cdm:resource_legal_id_celex ?celex .
    OPTIONAL {{ ?case cdm:work_date_document ?date }}
  }}
  FILTER(REGEX(STR(?celex), "^6[0-9]{{4}}(CJ|TJ|CC|CO)"))
}} ORDER BY DESC(?date) LIMIT {limit}
"""
        rows = self._get_json(query).get("results", {}).get("bindings", [])
        return [_first(row, "celex") for row in rows if _first(row, "celex")]

    def _document_from_celex(
        self,
        celex: str,
        seed: dict,
        citations_per_doc: int,
    ) -> Document | None:
        resolved = self._celex_graph(celex)
        if not resolved:
            print(f"  [skip] {celex}: no CELLAR graph")
            return None
        graph, work = resolved
        meta = self._metadata(graph, work)
        celex = meta.get("celex", celex)
        source_url = f"https://publications.europa.eu/resource/celex/{urllib.parse.quote(celex, safe='')}.ENG.xhtml"
        text_sources = [
            (source_url, "application/xhtml+xml,text/html", "xhtml"),
            (
                f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{urllib.parse.quote(celex, safe='')}",
                "text/html",
                "html",
            ),
        ]
        title, provisions, raw_format, html = seed.get("title", celex), [], "cellar-rdf", ""
        for candidate_url, accept, ext in text_sources:
            try:
                body, _ = self.fetcher.get(candidate_url, accept=accept, ext=ext)
                parsed_title, parsed_provisions = parse_xhtml(celex, body, candidate_url)
            except (NotFound, ET.ParseError):
                continue
            title, provisions, raw_format, html = parsed_title, parsed_provisions, ext, body
            source_url = candidate_url
            if provisions:
                break

        citation = seed.get("title") or title or celex
        doc_type = _doc_type(celex, title, meta.get("resourceType"))
        court, level = _case_level(celex)
        edges: list[Edge] = []

        considers = seed.get("considers")
        if considers:
            edges.append(Edge(type=EdgeType.CONSIDERS, target=_local_id(considers)))

        if citations_per_doc:
            for target in self._linked_celexes(graph, work, "work_cites_work", citations_per_doc):
                edges.append(Edge(type=EdgeType.CITES, target=_local_id(target)))
            for target in self._linked_celexes(graph, work, "resource_legal_amends_resource_legal", citations_per_doc):
                edges.append(Edge(type=EdgeType.AMENDS, target=_local_id(target)))
            for target in self._linked_celexes(graph, work, "resource_legal_based_on_resource_legal", citations_per_doc):
                edges.append(Edge(type=EdgeType.MADE_UNDER, target=_local_id(target)))

        return Document(
            id=_local_id(celex),
            jurisdiction=Jurisdiction.EU,
            type=doc_type,
            citation=citation,
            title=title,
            celex=celex,
            date_enacted=meta.get("date"),
            date_in_force=meta.get("entry"),
            date_decided=meta.get("date") if doc_type == DocType.CASE else None,
            status=_status(meta.get("inForce"), meta.get("end")),
            territorial_scope="EU",
            court=court,
            level=level,
            regulator=seed.get("regulator"),
            concepts=seed.get("concepts", []),
            subject_tags=[seed["title"]] if seed.get("title") else [],
            provisions=provisions,
            edges=_dedupe_edges(edges),
            landing_page_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
            source=SourceMeta(
                url=source_url,
                raw_format=raw_format,
                hash=hashlib.sha256((html or graph).encode()).hexdigest(),
            ),
        )
