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


def test_regimes_endpoint_passes_repeated_jurisdictions_as_list(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(api.regimes, "surface_regimes",
                        lambda driver, topic, jurisdiction=None: captured.update(
                            jurisdiction=jurisdiction) or [])
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/regimes",
                      params=[("topic", "online safety"),
                              ("jurisdiction", "United Kingdom"),
                              ("jurisdiction", "European Union")])
    assert resp.status_code == 200
    assert captured["jurisdiction"] == ["United Kingdom", "European Union"]


def test_chat_endpoint_scopes_and_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(api.retrieval, "chat_context",
                        lambda *a, **k: {
                            "regime_names": ["OSA"],
                            "regimes": [{"id": "uk-ukpga-2023-50", "citation": "OSA"}],
                            "provisions": [{"number": "9", "heading": "Duties",
                                            "snippet": "x", "url": "http://p",
                                            "document": {"citation": "OSA"}}],
                            "related_documents": [{
                                "relationship": "DEBATED_IN",
                                "layer": "HansardDebate",
                                "citation": "OSA debate",
                                "url": "http://h",
                            }],
                        })
    client = _client(monkeypatch, tmp_path)
    api.dossier.write_dossier({
        "regime_id": "uk-ukpga-2023-50",
        "name": "OSA",
        "regulatory_guidance": [{
            "regulator": "Ofcom",
            "title": "Illegal content Codes of Practice",
            "description": "Sets out compliance measures.",
            "official_link": "https://www.ofcom.org.uk/",
        }],
        "regulatory_guidance_updated_at": "2026-06-27T17:00:00+00:00",
    }, tmp_path)

    seen = {}

    def fake_answer(q, scoped, **k):
        seen["regulatory_guidance"] = scoped["regulatory_guidance"]
        return {"answer": "Ofcom regulates.", "suggestions": ["What are the penalties?"]}

    monkeypatch.setattr(api.llm, "answer", fake_answer)
    resp = client.post("/chat", json={"query": "duties?",
                                      "regime_ids": ["uk-ukpga-2023-50"]})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Ofcom regulates."
    assert resp.json()["suggestions"] == ["What are the penalties?"]
    assert resp.json()["citations"][0]["number"] == "9"
    assert resp.json()["related_documents"][0]["layer"] == "HansardDebate"
    assert resp.json()["regulatory_guidance"][0]["guidance"][0]["regulator"] == "Ofcom"
    assert seen["regulatory_guidance"][0]["updated_at"] == "2026-06-27T17:00:00+00:00"


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


def test_regulatory_guidance_refresh_endpoint_updates_dossier(monkeypatch, tmp_path):
    monkeypatch.setattr(api.dossier, "gather_subgraph",
                        lambda d, rid, **k: {"regime_id": rid, "name": "OSA"})
    monkeypatch.setattr(api.llm, "refresh_regulatory_guidance",
                        lambda bundle: [{
                            "regulator": "Ofcom",
                            "title": "Online safety guidance",
                            "description": "Explains compliance expectations.",
                            "official_link": "https://www.ofcom.org.uk/",
                        }])
    client = _client(monkeypatch, tmp_path)

    resp = client.post(
        "/regime/uk-ukpga-2023-50/regulatory-guidance/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["regulatory_guidance"][0]["regulator"] == "Ofcom"
    assert body["regulatory_guidance_updated_at"]


def test_chat_empty_regime_ids_passes_none(monkeypatch, tmp_path):
    seen = {}

    def recorder(driver, query, top_k=12, regime_ids=None):
        seen["regime_ids"] = regime_ids
        return {
            "regime_names": [],
            "regimes": [],
            "provisions": [],
            "related_documents": [],
        }

    monkeypatch.setattr(api.retrieval, "chat_context", recorder)
    monkeypatch.setattr(api.llm, "answer",
                        lambda q, scoped, **k: {"answer": "ok", "suggestions": []})
    client = _client(monkeypatch, tmp_path)
    resp = client.post("/chat", json={"query": "duties?", "regime_ids": []})
    assert resp.status_code == 200
    assert seen["regime_ids"] is None  # empty list must become None (unscoped)
