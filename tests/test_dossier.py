from legalgraph.dossier import (
    dossier_path, read_dossier, write_dossier, get_or_build_dossier, save_dossier,
)


def test_read_returns_none_when_absent(tmp_path):
    assert read_dossier("uk-ukpga-2023-50", tmp_path) is None


def test_write_then_read_roundtrips(tmp_path):
    write_dossier({"regime_id": "r1", "summary": "hi"}, tmp_path)
    assert read_dossier("r1", tmp_path)["summary"] == "hi"
    assert dossier_path("r1", tmp_path).exists()


def test_get_or_build_calls_llm_once_then_serves_cache(tmp_path):
    calls = {"gather": 0, "draft": 0}

    def gather(regime_id):
        calls["gather"] += 1
        return {"regime_id": regime_id, "name": "OSA"}

    def draft(bundle):
        calls["draft"] += 1
        return {"summary": "generated", "scope": "", "process": "",
                "consequence": "", "obligations": [], "guidance": ""}

    first = get_or_build_dossier("r1", tmp_path, gather, draft)
    assert first["summary"] == "generated"
    assert first["regime_id"] == "r1"
    assert first["edited_by_human"] is False

    second = get_or_build_dossier("r1", tmp_path, gather, draft)
    assert second["summary"] == "generated"
    assert calls == {"gather": 1, "draft": 1}  # not regenerated


def test_save_marks_human_edited_and_persists(tmp_path):
    get_or_build_dossier(
        "r1", tmp_path, lambda rid: {"regime_id": rid, "name": "OSA"},
        lambda b: {"summary": "auto", "scope": "", "process": "",
                   "consequence": "", "obligations": [], "guidance": ""})
    saved = save_dossier("r1", {"summary": "edited by a human"}, tmp_path)
    assert saved["summary"] == "edited by a human"
    assert saved["edited_by_human"] is True
    assert read_dossier("r1", tmp_path)["summary"] == "edited by a human"


from tests.conftest import FakeDriver
from legalgraph.dossier import gather_subgraph


def test_gather_subgraph_shapes_the_bundle():
    driver = FakeDriver({"CONSIDERS": [{
        "citation": "Online Safety Act 2023",
        "provisions": [{"number": "9", "heading": "Duties",
                        "text": "illegal content", "url": "http://p"}],
        "cases": [{"citation": "R v X", "url": "http://case"}],
        "guidance": [{"citation": "Ofcom code", "url": "http://g"}],
    }]})
    bundle = gather_subgraph(driver, "uk-ukpga-2023-50")
    assert bundle["regime_id"] == "uk-ukpga-2023-50"
    assert bundle["name"] == "Online Safety Act 2023"
    assert bundle["provisions"][0]["number"] == "9"
    assert bundle["cases"][0]["citation"] == "R v X"
