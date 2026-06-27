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
from legalgraph.regimes import surface_regimes


def test_surface_regimes_blends_provision_hits_and_related_anchors():
    driver = FakeDriver({
        # search_provisions fulltext query
        "queryNodes": [{
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
