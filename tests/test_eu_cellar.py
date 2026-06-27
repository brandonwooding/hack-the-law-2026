from legalgraph.canonical import DocType
from legalgraph.adapters.eu.cellar import (
    _case_level,
    _doc_type,
    _local_id,
    parse_xhtml,
)


def test_local_id_sanitises_complex_celex_case_ids():
    assert _local_id("62023CO0639(01)") == "eu-celex-62023CO0639_01_"


def test_doc_type_maps_eu_secondary_and_cases():
    assert _doc_type("32022R2065", "Digital Services Act", "REG") == DocType.ACT
    assert _doc_type(
        "32024R0001", "Commission Implementing Regulation (EU) 2024/1", "REG_IMPL"
    ) == DocType.REGULATORY_INSTRUMENT
    assert _doc_type("62023TJ0367", "Amazon Services Europe v Commission", None) == DocType.CASE


def test_case_level_maps_cjeu_and_general_court_markers():
    assert _case_level("62024CJ0001") == ("Court of Justice of the European Union", "CJEU")
    assert _case_level("62023TJ0367") == ("General Court", "EGC")


def test_parse_xhtml_extracts_articles_and_paragraphs():
    html = """<?xml version="1.0" encoding="UTF-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml">
      <head><title>Fallback</title></head>
      <body>
        <div class="eli-main-title">
          <p class="oj-doc-ti">REGULATION (EU) 2022/2065</p>
          <p class="oj-doc-ti">on digital services</p>
        </div>
        <div class="eli-subdivision" id="art_9">
          <p class="oj-ti-art">Article 9</p>
          <div class="eli-title"><p class="oj-sti-art">Orders to act</p></div>
          <div id="009.001"><p class="oj-normal">1. First paragraph.</p></div>
          <div id="009.002"><p class="oj-normal">2. Second paragraph.</p></div>
        </div>
      </body>
    </html>"""

    title, provisions = parse_xhtml("32022R2065", html, "https://example.test/dsa.xhtml")

    assert title == "REGULATION (EU) 2022/2065 on digital services"
    assert len(provisions) == 1
    assert provisions[0].id == "eu-celex-32022R2065/art/9"
    assert provisions[0].heading == "Orders to act"
    assert len(provisions[0].children) == 2
    assert provisions[0].children[0].id == "eu-celex-32022R2065/art/9/para/1"


def test_parse_xhtml_tolerates_non_xml_html():
    html = """<html><head><meta charset="utf-8"></head><body>
      <div class="eli-main-title"><p>Directive title</p></div>
      <div class="eli-subdivision" id="art_1">
        <p class="oj-ti-art">Article 1</p>
        <div class="eli-title"><p class="oj-sti-art">Aim</p></div>
        <div id="001.001"><p class="oj-normal">1. Text.</p></div>
      </div>
    </body></html>"""

    title, provisions = parse_xhtml("32000L0031", html, "https://example.test")

    assert title == "Directive title"
    assert len(provisions) == 1
    assert provisions[0].heading == "Aim"
