from legalgraph.regimes import rollup_regimes


def _prov(doc_id, citation, layer, score, url="http://x", regulator="Ofcom"):
    return {"score": score, "document": {
        "id": doc_id, "citation": citation, "layer": layer,
        "url": url, "regulator": regulator}}


def test_rollup_keeps_only_act_and_treaty_layers_ranked_by_score():
    provisions = [
        _prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0),
        _prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 3.0),  # same anchor
        _prov("uk-uksi-2024-1", "Some SI 2024", "StatutoryInstrument", 9.0),  # dropped
    ]
    cards = rollup_regimes(provisions, related=[])
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    card = cards[0]
    assert card["name"] == "Online Safety Act 2023"
    assert card["why_surfaced"] == "primary"
    assert card["anchor_doc_id"] == "uk-ukpga-2023-50"
    assert card["source_url"] == "http://x"


def test_rollup_appends_related_anchors_not_already_primary():
    provisions = [_prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0)]
    related = [{"id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
                "layer": "Act", "url": "http://dpa", "regulator": "ICO"}]
    cards = rollup_regimes(provisions, related)
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50", "uk-ukpga-2018-12"]
    assert cards[1]["why_surfaced"] == "related"


def test_rollup_does_not_duplicate_a_related_anchor_that_is_already_primary():
    provisions = [_prov("uk-ukpga-2023-50", "Online Safety Act 2023", "Act", 5.0)]
    related = [{"id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
                "layer": "Act", "url": "http://x", "regulator": "Ofcom"}]
    cards = rollup_regimes(provisions, related)
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    assert cards[0]["why_surfaced"] == "primary"


from tests.conftest import FakeDriver
from legalgraph.regimes import (
    surface_regimes,
    normalize_jurisdiction,
    normalize_jurisdictions,
    list_anchor_regimes,
)


def test_list_anchor_regimes_returns_cards_ordered_for_act_and_treaty_anchors():
    driver = FakeDriver({"ORDER BY d.citation": [
        {"id": "uk-ukpga-2003-21", "citation": "Communications Act 2003",
         "layer": "Act", "url": "http://ca", "regulator": "Ofcom"},
        {"id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
         "layer": "Act", "url": "http://osa", "regulator": "Ofcom"},
    ]})
    cards = list_anchor_regimes(driver)
    assert [c["id"] for c in cards] == ["uk-ukpga-2003-21", "uk-ukpga-2023-50"]
    assert cards[1]["name"] == "Online Safety Act 2023"
    assert cards[0]["short_description"]  # non-empty descriptor


def test_list_anchor_regimes_skips_rows_without_an_id():
    driver = FakeDriver({"ORDER BY d.citation": [
        {"id": None, "citation": "Orphan", "layer": "Act"},
        {"id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
         "layer": "Act", "regulator": "ICO"},
    ]})
    cards = list_anchor_regimes(driver)
    assert [c["id"] for c in cards] == ["uk-ukpga-2018-12"]


def test_normalize_jurisdiction_maps_ui_labels_to_graph_codes():
    assert normalize_jurisdiction("United Kingdom") == "UK"
    assert normalize_jurisdiction("united kingdom") == "UK"
    assert normalize_jurisdiction("European Union") == "EU"
    assert normalize_jurisdiction("UK") == "UK"


def test_normalize_jurisdiction_passes_through_none_and_unknown():
    assert normalize_jurisdiction(None) is None
    assert normalize_jurisdiction("") is None
    # unknown-but-given stays as a filter (matches nothing) rather than going unscoped
    assert normalize_jurisdiction("United States (federal)") == "United States (federal)"


def test_normalize_jurisdictions_maps_one_or_many_labels_to_codes():
    assert normalize_jurisdictions(None) is None
    assert normalize_jurisdictions([]) is None
    assert normalize_jurisdictions("United Kingdom") == ["UK"]
    assert normalize_jurisdictions(["United Kingdom", "European Union"]) == ["UK", "EU"]
    # de-duplicates labels that map to the same code, preserving order
    assert normalize_jurisdictions(["UK", "United Kingdom"]) == ["UK"]


def test_surface_regimes_normalizes_jurisdiction_into_the_query():
    driver = FakeDriver({"queryNodes": []})
    surface_regimes(driver, "online safety", jurisdiction="United Kingdom")
    provision_calls = [p for c, p in driver.calls if "queryNodes" in c]
    assert provision_calls and provision_calls[0]["jdx"] == ["UK"]


def test_surface_regimes_scopes_across_multiple_jurisdictions():
    driver = FakeDriver({"queryNodes": []})
    surface_regimes(driver, "online safety",
                    jurisdiction=["United Kingdom", "European Union"])
    provision_calls = [p for c, p in driver.calls if "queryNodes" in c]
    assert provision_calls and provision_calls[0]["jdx"] == ["UK", "EU"]


def test_surface_regimes_blends_provision_hits_and_related_anchors():
    driver = FakeDriver({
        # search_provisions fulltext query
        "provision_text": [{
            "provision_id": "uk-ukpga-2023-50/s/9", "number": "9", "heading": "Duties",
            "text": "illegal content", "url": "http://p", "score": 5.0,
            "doc_id": "uk-ukpga-2023-50", "document": "Online Safety Act 2023",
            "layer": "Act", "document_url": "http://osa", "regulator": "Ofcom",
            "breadcrumb": ["9"],
        }],
        # related-anchors concept hop
        "RELATED|BROADER": [{
            "id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
            "layer": "Act", "url": "http://dpa", "regulator": "ICO",
        }],
    })
    cards = surface_regimes(driver, "online safety")
    assert cards[0]["id"] == "uk-ukpga-2023-50"
    assert cards[0]["why_surfaced"] == "primary"
    assert any(c["id"] == "uk-ukpga-2018-12" and c["why_surfaced"] == "related"
               for c in cards)


def test_surface_regimes_promotes_title_hits_to_regime_cards():
    driver = FakeDriver({
        "provision_text": [],
        "document_title": [{
            "id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
            "layer": "Act", "url": "http://osa", "regulator": "Ofcom",
            "score": 4.0,
        }],
    })
    cards = surface_regimes(driver, "online safety", jurisdiction="United Kingdom")
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    assert cards[0]["why_surfaced"] == "primary"


def test_surface_regimes_promotes_anchor_for_matched_non_anchor_documents():
    driver = FakeDriver({
        "provision_text": [{
            "provision_id": "uk-guidance-osa/p/1", "number": "1", "heading": "Overview",
            "text": "online safety", "url": "http://g/p", "score": 5.0,
            "doc_id": "uk-guidance-osa", "document": "Online Safety Act explainer",
            "layer": "Guidance", "document_url": "http://g", "regulator": "Ofcom",
            "breadcrumb": ["1"],
        }],
        "source_id": [{
            "id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
            "layer": "Act", "url": "http://osa", "regulator": "Ofcom",
            "relationships": ["ISSUED_UNDER"],
        }],
    })
    cards = surface_regimes(driver, "online safety", jurisdiction="United Kingdom")
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50"]
    assert cards[0]["why_surfaced"] == "primary"


def test_surface_regimes_uses_concept_matches_when_fulltext_has_no_anchor():
    driver = FakeDriver({
        "provision_text": [],
        "matched:Concept": [{
            "id": "uk-ukpga-2023-50", "citation": "Online Safety Act 2023",
            "layer": "Act", "url": "http://osa", "regulator": "Ofcom",
        }, {
            "id": "uk-ukpga-2018-12", "citation": "Data Protection Act 2018",
            "layer": "Act", "url": "http://dpa", "regulator": "ICO",
        }],
    })
    cards = surface_regimes(driver, "What regulatory regimes apply to online safety?",
                            jurisdiction="United Kingdom")
    assert [c["id"] for c in cards] == ["uk-ukpga-2023-50", "uk-ukpga-2018-12"]
    assert all(c["why_surfaced"] == "related" for c in cards)
