from legalgraph.retrieval import _scope_clause
from tests.conftest import FakeDriver
from legalgraph.retrieval import search_provisions


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
