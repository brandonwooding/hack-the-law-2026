import legalgraph.api as api
from fastapi.testclient import TestClient
from tests.conftest import FakeDriver


def _client(monkeypatch, tmp_path):
    api._state["driver"] = FakeDriver()
    monkeypatch.setattr(api.dossier, "DOSSIER_DIR", tmp_path)
    return TestClient(api.app)


def test_regimes_endpoint_returns_cards(monkeypatch, tmp_path):
    monkeypatch.setattr(api.regimes, "surface_regimes",
                        lambda *a, **k: [{"id": "r1", "name": "OSA",
                                          "why_surfaced": "primary"}])
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/regimes", params={"topic": "online safety"})
    assert resp.status_code == 200
    assert resp.json()["regimes"][0]["id"] == "r1"


def test_chat_endpoint_scopes_and_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(api.retrieval, "search_provisions",
                        lambda *a, **k: [{"number": "9", "heading": "Duties",
                                          "snippet": "x", "url": "http://p",
                                          "document": {"citation": "OSA"}}])
    monkeypatch.setattr(api.llm, "answer", lambda q, scoped, **k: "Ofcom regulates.")
    client = _client(monkeypatch, tmp_path)
    resp = client.post("/chat", json={"query": "duties?",
                                      "regime_ids": ["uk-ukpga-2023-50"]})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Ofcom regulates."
    assert resp.json()["citations"][0]["number"] == "9"


def test_regime_get_synthesizes_then_put_edits(monkeypatch, tmp_path):
    monkeypatch.setattr(api.dossier, "gather_subgraph",
                        lambda d, rid, **k: {"regime_id": rid, "name": "OSA"})
    monkeypatch.setattr(api.llm, "draft_dossier",
                        lambda bundle: {"summary": "auto", "scope": "", "process": "",
                                        "consequence": "", "obligations": [],
                                        "guidance": ""})
    client = _client(monkeypatch, tmp_path)

    got = client.get("/regime/uk-ukpga-2023-50")
    assert got.status_code == 200
    assert got.json()["summary"] == "auto"
    assert got.json()["edited_by_human"] is False

    put = client.put("/regime/uk-ukpga-2023-50",
                     json={"summary": "human edit"})
    assert put.status_code == 200
    assert put.json()["summary"] == "human edit"
    assert put.json()["edited_by_human"] is True


def test_chat_empty_regime_ids_passes_none(monkeypatch, tmp_path):
    seen = {}

    def recorder(driver, query, top_k=12, regime_ids=None):
        seen["regime_ids"] = regime_ids
        return []

    monkeypatch.setattr(api.retrieval, "search_provisions", recorder)
    monkeypatch.setattr(api.llm, "answer", lambda q, scoped, **k: "ok")
    client = _client(monkeypatch, tmp_path)
    resp = client.post("/chat", json={"query": "duties?", "regime_ids": []})
    assert resp.status_code == 200
    assert seen["regime_ids"] is None  # empty list must become None (unscoped)
