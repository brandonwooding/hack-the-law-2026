import hashlib
from pathlib import Path

from legalgraph.canonical import DocType, EdgeType
from legalgraph.adapters.uk.regulator_documents import (
    RegulatorDocumentsAdapter,
    _classify,
    _extract_nemotron_blocks,
    _merge_nvidia_pages,
    _slug,
)


class FakeFetcher:
    def __init__(self, tmp_path: Path, html: str):
        self.cache_dir = tmp_path / "raw"
        self.html = html

    def get(self, url, accept=None, ext="html", force=False, max_retries=5):
        path = self.cache_dir / "example.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.html)
        return self.html, path

    def get_bytes(self, url, accept=None, ext="pdf", force=False, max_retries=5):
        path = self.cache_dir / "example.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = b"%PDF fake"
        path.write_bytes(body)
        return body, path


def _scope(url: str):
    return {
        "uk": {
            "seeds": [{
                "id": "ukpga/2023/50",
                "title": "Online Safety Act 2023",
                "regulator": "Office of Communications (Ofcom)",
                "concepts": ["eurovoc:online-safety"],
            }],
            "regulator_documents": [{
                "code": "ofcom",
                "regulator": "Office of Communications (Ofcom)",
                "publisher": "Ofcom",
                "url": "https://www.ofcom.org.uk/policies",
                "default_kind": "policy",
            }],
        }
    }


def test_classify_guidance_and_policy_as_different_layers():
    assert _classify("Online Safety Act statutory guidance")[0] == DocType.GUIDANCE
    assert _classify("Complaints handling policy")[0] == DocType.REGULATORY_POLICY


def test_adapter_builds_guidance_with_ocr_provisions_and_act_edge(tmp_path):
    pdf_url = "https://www.ofcom.org.uk/siteassets/test/osa-guidance.pdf"
    title = "Online Safety Act 2023 statutory guidance"
    html = f'<html><body><a href="{pdf_url}">{title}</a></body></html>'
    doc_id = (
        "uk-ofcom-guidance-"
        f"{_slug(title)}-{hashlib.sha256(pdf_url.encode()).hexdigest()[:10]}"
    )
    ocr_dir = tmp_path / "ocr" / "uk-regulator-documents"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / f"{doc_id}.json").write_text("""{
      "title": "Online Safety Act 2023 statutory guidance",
      "published_date": "2025-01-01",
      "text": "Issued under the Online Safety Act 2023.",
      "sections": [
        {"number": "1", "heading": "Scope", "text": "Applies to services.", "page_start": 3}
      ]
    }""")

    docs = RegulatorDocumentsAdapter(FakeFetcher(tmp_path, html)).collect(_scope(pdf_url))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.type == DocType.GUIDANCE
    assert doc.legal_effect == "statutory_guidance"
    assert doc.published_date == "2025-01-01"
    assert doc.concepts == ["eurovoc:online-safety"]
    assert [(e.type, e.target) for e in doc.edges] == [
        (EdgeType.ISSUED_UNDER, "uk-ukpga-2023-50")
    ]
    assert doc.provisions[0].heading == "Scope"
    assert doc.provisions[0].page_start == 3


def test_adapter_keeps_unlinked_policy_out_of_regime_neighbourhood(tmp_path):
    pdf_url = "https://www.ofcom.org.uk/siteassets/test/expenses-policy.pdf"
    title = "Expenses policy"
    html = f'<a href="{pdf_url}">{title}</a>'

    docs = RegulatorDocumentsAdapter(FakeFetcher(tmp_path, html)).collect(_scope(pdf_url))

    assert docs[0].type == DocType.REGULATORY_POLICY
    assert docs[0].document_kind == "policy"
    assert docs[0].edges == []


def test_merge_nvidia_pages_preserves_page_sections():
    merged = _merge_nvidia_pages([
        {
            "title": "Penalty guidelines",
            "text": "Intro text",
            "sections": [{"number": "1", "heading": "Intro", "text": "Intro text"}],
        },
        {"text": "Second page text"},
    ], "nvidia/nemotron-parse")

    assert merged["title"] == "Penalty guidelines"
    assert merged["ocr_model"] == "nvidia/nemotron-parse"
    assert merged["sections"][0]["page_start"] == 1
    assert merged["sections"][1]["number"] == "p2"
    assert "Second page text" in merged["text"]


def test_extract_nemotron_markdown_bbox_tool_call():
    response = {
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{
                    "type": "function",
                    "function": {
                        "name": "markdown_bbox",
                        "arguments": '[[{"text": "# Title", "type": "Title"}]]',
                    },
                }],
            },
        }],
    }

    assert _extract_nemotron_blocks(response) == [{"text": "# Title", "type": "Title"}]
