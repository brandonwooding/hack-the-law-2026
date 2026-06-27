from legalgraph.retrieval import _scope_clause
from tests.conftest import FakeDriver
from legalgraph.retrieval import (
    chat_context, related_documents_for_regimes, search_provisions,
)


def test_scope_clause_empty_when_no_regime_ids():
    frag, params = _scope_clause(None)
    assert frag == ""
    assert params == {}
    frag2, params2 = _scope_clause([])
    assert frag2 == ""
    assert params2 == {}


def test_scope_clause_constrains_to_anchor_or_its_neighbourhood():
    frag, params = _scope_clause(["uk-ukpga-2023-50"])
    assert params == {"regime_ids": ["uk-ukpga-2023-50"]}
    assert "d.id IN $regime_ids" in frag
    assert "EXISTS" in frag
    assert "CONTAINS" in frag  # neighbourhood excludes structural edges


def test_search_provisions_threads_regime_ids_into_query_params():
    driver = FakeDriver({"queryNodes": []})
    search_provisions(driver, "duties", regime_ids=["uk-ukpga-2023-50"])
    cypher, params = driver.calls[0]
    assert params["regime_ids"] == ["uk-ukpga-2023-50"]
    assert "d.id IN $regime_ids" in cypher


def test_search_provisions_unscoped_has_no_regime_constraint():
    driver = FakeDriver({"queryNodes": []})
    search_provisions(driver, "duties")
    cypher, params = driver.calls[0]
    assert "regime_ids" not in params
    assert "$regime_ids" not in cypher


def test_related_documents_for_regimes_returns_document_only_neighbourhood():
    driver = FakeDriver({"CALL (regime)": [{
        "regime_id": "uk-ukpga-2023-50",
        "regime": "Online Safety Act 2023",
        "id": "uk-hansard-1",
        "citation": "Online Safety Act 2023: Effectiveness (Hansard, Commons)",
        "title": "Online Safety Act 2023: Effectiveness",
        "layer": "HansardDebate",
        "relationship": "DEBATED_IN",
        "relationships": ["DEBATED_IN"],
        "url": "http://h",
    }]})
    docs = related_documents_for_regimes(
        driver, ["uk-ukpga-2023-50"], query="What did the Hansard debates say?")
    assert docs[0]["layer"] == "HansardDebate"
    assert docs[0]["relationship"] == "DEBATED_IN"
    assert docs[0]["relationships"] == ["DEBATED_IN"]
    cypher, params = driver.calls[0]
    assert params["ids"] == ["uk-ukpga-2023-50"]
    assert "CONTAINS*" in cypher
    assert "ABOUT" in cypher
    assert "RegulatoryPolicy" in cypher


def test_chat_context_includes_provisions_regimes_and_related_documents():
    driver = FakeDriver({
        "queryNodes": [{
            "provision_id": "uk-ukpga-2023-50/s/9", "number": "9", "heading": "Duties",
            "text": "illegal content", "url": "http://p", "score": 5.0,
            "doc_id": "uk-ukpga-2023-50", "document": "Online Safety Act 2023",
            "layer": "Act", "document_url": "http://osa", "regulator": "Ofcom",
            "breadcrumb": ["9"],
        }],
        "d.id IN $ids": [{
            "id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
            "layer": "Act", "url": "http://osa", "regulator": "Ofcom",
        }],
        "CALL (regime)": [{
            "regime_id": "uk-ukpga-2023-50",
            "regime": "Online Safety Act 2023",
            "id": "uk-hansard-1",
            "citation": "Online Safety Act 2023 debate",
            "layer": "HansardDebate",
            "relationship": "DEBATED_IN",
            "relationships": ["DEBATED_IN"],
            "url": "http://h",
        }],
    })
    scoped = chat_context(driver, "Hansard debates?", regime_ids=["uk-ukpga-2023-50"])
    assert scoped["regime_names"] == ["Online Safety Act 2023"]
    assert scoped["provisions"][0]["number"] == "9"
    assert scoped["related_documents"][0]["layer"] == "HansardDebate"
