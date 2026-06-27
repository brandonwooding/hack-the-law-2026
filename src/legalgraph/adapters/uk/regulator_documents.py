"""Regulator PDF adapter for policy and guidance pages.

This adapter is intentionally split into source discovery and OCR enrichment:
the graph can hold metadata-only regulator documents, but retrieval improves
substantially when a cached OCR JSON exists for each PDF.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ...canonical import (
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
from ...db import load_dotenv
from ...fetch import NotFound
from .. import register
from ..base import SourceAdapter

PARSE_VERSION = "regulator-pdf-v1"
NVIDIA_PARSE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_STATUS_URL = "https://integrate.api.nvidia.com/v1/status/{request_id}"
NVIDIA_ASSET_URL = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
NVIDIA_INLINE_B64_LIMIT = 10_000_000


@dataclass(frozen=True)
class PdfLink:
    url: str
    text: str


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[PdfLink] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = urllib.parse.urljoin(self.base_url, href)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        text = " ".join(" ".join(self._text).split())
        if _looks_like_pdf(self._href):
            self.links.append(PdfLink(url=self._href, text=text))
        self._href = None
        self._text = []


def _looks_like_pdf(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith(".pdf") or ".pdf/" in path or "format=pdf" in url.lower()


def _slug(text: str, fallback: str = "document", max_len: int = 72) -> str:
    text = re.sub(r"\.[Pp][Dd][Ff]$", "", text or "")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (text or fallback)[:max_len].strip("-") or fallback


def _clean_title(text: str, url: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip(" -")
    if text:
        return text
    name = Path(urllib.parse.urlparse(url).path).stem
    return re.sub(r"[-_]+", " ", name).strip().title() or url


def _classify(title: str, default_kind: str = "policy") -> tuple[DocType, str, str]:
    low = title.lower()
    if any(term in low for term in ("statutory guidance", "guidance", "guidelines", "code of practice")):
        effect = "statutory_guidance" if "statutory" in low else "non_binding_guidance"
        return DocType.GUIDANCE, "guidance", effect
    if any(term in low for term in ("procedure", "procedures")):
        return DocType.REGULATORY_POLICY, "procedure", "policy_position"
    if any(term in low for term in ("policy", "policies", "strategy", "framework")):
        return DocType.REGULATORY_POLICY, "policy", "policy_position"
    if default_kind == "guidance":
        return DocType.GUIDANCE, "guidance", "non_binding_guidance"
    return DocType.REGULATORY_POLICY, default_kind, "policy_position"


def _seed_act_id(seed: dict) -> str:
    return "uk-" + seed["id"].replace("/", "-")


def _act_root(title: str) -> str:
    return re.sub(r"\s+Act\s+\d{4}$", "", title or "", flags=re.I).strip().lower()


def _match_anchor_edges(title: str, text: str, seeds: list[dict]) -> list[Edge]:
    haystack = f"{title} {text}".lower()
    edges: list[Edge] = []
    for seed in seeds:
        act_title = (seed.get("title") or "").lower()
        root = _act_root(seed.get("title") or "")
        if act_title and act_title in haystack:
            edges.append(Edge(type=EdgeType.ISSUED_UNDER, target=_seed_act_id(seed)))
        elif root and len(root) > 6 and root in haystack and "act" in haystack:
            edges.append(Edge(type=EdgeType.ISSUED_UNDER, target=_seed_act_id(seed)))
    return edges


def _regulator_concepts(regulator: str, seeds: list[dict]) -> list[str]:
    concepts: list[str] = []
    for seed in seeds:
        if seed.get("regulator") == regulator:
            concepts.extend(seed.get("concepts") or [])
    return sorted(set(concepts))


def _status_from_text(text: str) -> Status:
    low = text.lower()
    if any(term in low for term in ("withdrawn", "superseded", "archived")):
        return Status.REPEALED
    return Status.IN_FORCE


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _provision_from_item(doc_id: str, item: dict, index: int, url: str) -> Provision:
    number = str(item.get("number") or item.get("label") or index)
    heading = item.get("heading") or item.get("title")
    children = item.get("children") or item.get("subsections") or []
    return Provision(
        id=f"{doc_id}/part/{_slug(number, fallback=str(index), max_len=32)}",
        number=number,
        heading=heading,
        text=item.get("text"),
        url=url,
        legal_force=LegalForce.GUIDANCE,
        page_start=_as_int(item.get("page_start") or item.get("page")),
        page_end=_as_int(item.get("page_end")),
        children=[
            _provision_from_item(
                f"{doc_id}/part/{_slug(number, fallback=str(index), max_len=32)}",
                child,
                child_index,
                url,
            )
            for child_index, child in enumerate(children, start=1)
            if isinstance(child, dict)
        ],
    )


def _provisions_from_ocr(doc_id: str, ocr: dict, url: str) -> list[Provision]:
    sections = ocr.get("sections") or ocr.get("provisions") or []
    if sections:
        return [
            _provision_from_item(doc_id, item, i, url)
            for i, item in enumerate(sections, start=1)
            if isinstance(item, dict)
        ]
    text = ocr.get("text") or ocr.get("markdown")
    if not text:
        return []
    return [Provision(
        id=f"{doc_id}/body",
        number="body",
        heading="Body",
        text=text,
        url=url,
        legal_force=LegalForce.GUIDANCE,
    )]


class OcrStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, doc_id: str) -> Path:
        return self.root / f"{doc_id}.json"

    def read(self, doc_id: str) -> dict | None:
        path = self.path(doc_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def write(self, doc_id: str, payload: dict) -> None:
        path = self.path(doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))


def _nvidia_api_key() -> str:
    load_dotenv()
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NGC_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY or NGC_API_KEY is required for Nemotron Parse")
    return key


def _json_request(req: urllib.request.Request, timeout: int = 240) -> tuple[int, dict, dict]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return getattr(resp, "status", 200), dict(resp.headers), data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"error": body}
        return e.code, dict(e.headers), data


def _nvidia_headers(key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update(extra or {})
    return headers


def _create_nvidia_asset(image_bytes: bytes, media_type: str, key: str) -> str:
    payload = {"contentType": media_type, "description": "legalgraph nemotron parse page"}
    req = urllib.request.Request(
        NVIDIA_ASSET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_nvidia_headers(key),
        method="POST",
    )
    _, _, data = _json_request(req)
    asset_id = data.get("assetId") or data.get("asset_id") or data.get("id")
    upload_url = data.get("uploadUrl") or data.get("upload_url")
    if not asset_id or not upload_url:
        raise RuntimeError(f"unexpected NVIDIA asset response: {data}")

    upload_req = urllib.request.Request(
        upload_url,
        data=image_bytes,
        headers={"Content-Type": media_type},
        method="PUT",
    )
    with urllib.request.urlopen(upload_req, timeout=240):
        pass
    return asset_id


def _extract_message_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def _extract_nemotron_blocks(data: dict) -> list[dict]:
    choices = data.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    blocks: list[dict] = []
    for call in message.get("tool_calls") or []:
        if call.get("type") != "function":
            continue
        function = call.get("function") or {}
        if function.get("name") != "markdown_bbox":
            continue
        arguments = function.get("arguments") or "[]"
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            continue
        pages = parsed if isinstance(parsed, list) else [parsed]
        for page in pages:
            items = page if isinstance(page, list) else [page]
            for item in items:
                if isinstance(item, dict):
                    blocks.append(item)
    return blocks


def _page_from_nemotron_blocks(blocks: list[dict], page_number: int) -> dict:
    lines: list[str] = []
    sections: list[dict] = []
    current: dict | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        current["text"] = current["text"].strip()
        if current["heading"] or current["text"]:
            sections.append(current)
        current = None

    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        block_type = str(block.get("type") or "").lower()
        if block_type in {"picture", "caption", "figure"}:
            continue
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        lines.append(text)
        if block_type in {"title", "section", "heading"} or text.startswith("#"):
            flush_current()
            heading = text.lstrip("#").strip()
            current = {
                "number": str(len(sections) + 1),
                "heading": heading,
                "text": "",
                "page_start": page_number,
                "page_end": page_number,
            }
        else:
            if current is None:
                current = {
                    "number": str(len(sections) + 1),
                    "heading": None,
                    "text": "",
                    "page_start": page_number,
                    "page_end": page_number,
                }
            current["text"] += ("\n" if current["text"] else "") + text
    flush_current()

    return {
        "title": next((s["heading"] for s in sections if s.get("heading")), None),
        "text": "\n".join(lines),
        "sections": sections,
        "page": page_number,
    }


def _json_from_model_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"text": text}
    except json.JSONDecodeError:
        return {"text": text}


def _poll_nvidia_status(request_id: str, key: str, timeout_s: int = 600) -> dict:
    deadline = time.monotonic() + timeout_s
    url = NVIDIA_STATUS_URL.format(request_id=urllib.parse.quote(request_id))
    while time.monotonic() < deadline:
        req = urllib.request.Request(url, headers=_nvidia_headers(key), method="GET")
        status, _headers, data = _json_request(req, timeout=120)
        if status == 200:
            return data
        if status == 202:
            time.sleep(2)
            continue
        raise RuntimeError(f"NVIDIA status request failed with HTTP {status}: {data}")
    raise TimeoutError(f"NVIDIA parse request {request_id} did not complete in time")


def _invoke_nvidia_parse_page(image_bytes: bytes, media_type: str, model: str,
                              page_number: int, max_tokens: int = 8192) -> dict:
    key = _nvidia_api_key()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    headers: dict[str, str] = {}
    if len(b64) > NVIDIA_INLINE_B64_LIMIT:
        asset_id = _create_nvidia_asset(image_bytes, media_type, key)
        image_ref = f"data:{media_type};asset_id,{asset_id}"
        headers["NVCF-INPUT-ASSET-REFERENCES"] = asset_id
    else:
        image_ref = f"data:{media_type};base64,{b64}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": f'<img src="{image_ref}" />',
        }],
        "tools": [{
            "type": "function",
            "function": {"name": "markdown_bbox"},
        }],
        "tool_choice": {
            "type": "function",
            "function": {"name": "markdown_bbox"},
        },
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        NVIDIA_PARSE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_nvidia_headers(key, headers),
        method="POST",
    )
    status, headers, data = _json_request(req)
    if status == 202:
        request_id = headers.get("NVCF-REQID") or data.get("requestId") or data.get("id")
        if not request_id:
            raise RuntimeError(f"NVIDIA async response did not include a request id: {data}")
        data = _poll_nvidia_status(request_id, key)
    elif status != 200:
        raise RuntimeError(f"NVIDIA parse request failed with HTTP {status}: {data}")
    content = _extract_message_text(data)
    blocks = _extract_nemotron_blocks(data)
    parsed = _page_from_nemotron_blocks(blocks, page_number) if blocks else _json_from_model_text(content)
    parsed.setdefault("page", page_number)
    return parsed


def _render_pdf_pages(pdf_path: Path, pages_dir: Path, max_pages: int | None = None,
                      scale: float = 2.0) -> list[Path]:
    import pypdfium2 as pdfium

    pages_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    limit = min(len(pdf), max_pages) if max_pages else len(pdf)
    out: list[Path] = []
    for index in range(limit):
        path = pages_dir / f"page-{index + 1:04d}.png"
        if not path.exists():
            page = pdf[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            image.save(path, format="PNG")
        out.append(path)
    return out


def _merge_nvidia_pages(page_payloads: list[dict], model: str) -> dict:
    sections: list[dict] = []
    texts: list[str] = []
    merged: dict[str, Any] = {
        "ocr_model": model,
        "ocr_parsed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    for index, page in enumerate(page_payloads, start=1):
        for key in ("title", "published_date", "updated_date", "version"):
            if page.get(key) and not merged.get(key):
                merged[key] = page[key]
        text = page.get("text") or page.get("markdown") or ""
        if text:
            texts.append(str(text))
        page_sections = page.get("sections") or page.get("provisions") or []
        if isinstance(page_sections, list) and page_sections:
            for section in page_sections:
                if not isinstance(section, dict):
                    continue
                section.setdefault("page_start", index)
                section.setdefault("page_end", index)
                sections.append(section)
        elif text:
            sections.append({
                "number": f"p{index}",
                "heading": f"Page {index}",
                "text": text,
                "page_start": index,
                "page_end": index,
            })
    merged["text"] = "\n\n".join(texts)
    merged["sections"] = sections
    return merged


def parse_pdf_with_nvidia(pdf_path: Path, doc_id: str, model: str,
                          max_pages: int | None = None,
                          render_scale: float = 2.0) -> dict:
    pages_dir = pdf_path.parent / f"{doc_id}-pages"
    page_paths = _render_pdf_pages(pdf_path, pages_dir, max_pages=max_pages,
                                   scale=render_scale)
    payloads: list[dict] = []
    for index, path in enumerate(page_paths, start=1):
        cache_path = pages_dir / f"page-{index:04d}.json"
        if cache_path.exists():
            payloads.append(json.loads(cache_path.read_text()))
            continue
        payload = _invoke_nvidia_parse_page(path.read_bytes(), "image/png", model, index)
        cache_path.write_text(json.dumps(payload, indent=2))
        payloads.append(payload)
    return _merge_nvidia_pages(payloads, model)


@register("uk-regulator-documents")
class RegulatorDocumentsAdapter(SourceAdapter):
    source = "uk-regulator-documents"
    jurisdiction = Jurisdiction.UK

    def collect(self, scope: dict) -> list[Document]:
        uk = scope.get("uk", {})
        pages = uk.get("regulator_documents", [])
        seeds = uk.get("seeds", [])
        docs: list[Document] = []
        seen: set[str] = set()

        ocr_root = self.fetcher.cache_dir.parent / "ocr" / self.source
        ocr_store = OcrStore(ocr_root)

        for page in pages:
            page_url = page["url"]
            regulator = page["regulator"]
            default_kind = page.get("default_kind", "policy")
            html, _ = self.fetcher.get(page_url, accept="text/html", ext="html")
            parser = _LinkParser(page_url)
            parser.feed(html)
            limit = page.get("limit")
            links = parser.links[:limit] if limit else parser.links
            missing = 0

            for link in links:
                title = _clean_title(link.text, link.url)
                doc_type, kind, effect = _classify(title, default_kind)
                regulator_code = _slug(page.get("code") or regulator, max_len=24)
                digest = hashlib.sha256(link.url.encode("utf-8")).hexdigest()[:10]
                doc_id = f"uk-{regulator_code}-{kind}-{_slug(title)}-{digest}"
                if doc_id in seen:
                    continue
                seen.add(doc_id)

                try:
                    pdf_bytes, pdf_path = self.fetcher.get_bytes(
                        link.url, accept="application/pdf", ext="pdf")
                except NotFound:
                    missing += 1
                    continue
                source_hash = hashlib.sha256(pdf_bytes).hexdigest()

                ocr = ocr_store.read(doc_id)
                if ocr is None and page.get("parse_with_nvidia"):
                    model = page.get("nvidia_model") or os.environ.get("NVIDIA_NEMOTRON_PARSE_MODEL")
                    model = model or "nvidia/nemotron-parse"
                    if not model:
                        raise RuntimeError("nvidia_model or NVIDIA_NEMOTRON_PARSE_MODEL is required")
                    ocr = parse_pdf_with_nvidia(
                        pdf_path,
                        doc_id,
                        model,
                        max_pages=page.get("parse_max_pages"),
                        render_scale=float(page.get("parse_render_scale", 2.0)),
                    )
                    ocr_store.write(doc_id, ocr)

                ocr_text = " ".join(str(ocr.get(k) or "") for k in ("title", "text", "markdown")) if ocr else ""
                provisions = _provisions_from_ocr(doc_id, ocr or {}, link.url)
                citation = (ocr or {}).get("title") or title
                edges = _match_anchor_edges(citation, ocr_text, seeds)

                docs.append(Document(
                    id=doc_id,
                    jurisdiction=Jurisdiction.UK,
                    type=doc_type,
                    citation=citation,
                    title=citation,
                    status=_status_from_text(f"{citation} {ocr_text}"),
                    regulator=regulator,
                    publisher=page.get("publisher") or regulator,
                    document_kind=kind,
                    legal_effect=effect,
                    published_date=(ocr or {}).get("published_date"),
                    updated_date=(ocr or {}).get("updated_date"),
                    version=(ocr or {}).get("version"),
                    subject_tags=[kind, regulator_code],
                    concepts=_regulator_concepts(regulator, seeds),
                    provisions=provisions,
                    edges=edges,
                    landing_page_url=page_url,
                    pdf_url=link.url,
                    ocr_model=(ocr or {}).get("ocr_model"),
                    ocr_parsed_at=(ocr or {}).get("ocr_parsed_at"),
                    parse_version=PARSE_VERSION if ocr else None,
                    source=SourceMeta(
                        url=link.url,
                        hash=source_hash,
                        raw_format="pdf",
                    ),
                ))
            skipped = f", {missing} missing" if missing else ""
            print(f"  [ok] {regulator}: {len(links) - missing} regulator PDFs from {page_url}{skipped}")
        return docs
