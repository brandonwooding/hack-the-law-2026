import types

from legalgraph.llm import (
    DossierFields, RegulatoryGuidanceFields, RegulatoryGuidanceItem,
    _dossier_prompt, _regulatory_guidance_prompt, _answer_prompt,
    draft_dossier, refresh_regulatory_guidance, answer,
)


def _bundle():
    return {
        "regime_id": "uk-ukpga-2023-50",
        "name": "Online Safety Act 2023",
        "anchor": {"citation": "Online Safety Act 2023"},
        "provisions": [{"number": "9", "heading": "Illegal content duties",
                        "text": "...", "url": "http://p9"}],
        "cases": [{"citation": "R v X", "url": "http://case"}],
        "guidance": [{"citation": "Ofcom code", "url": "http://g"}],
    }


def test_dossier_prompt_grounds_in_the_bundle():
    p = _dossier_prompt(_bundle())
    assert "Online Safety Act 2023" in p
    assert "Illegal content duties" in p
    assert "R v X" in p
    # the grounding instruction must forbid inventing citations
    assert "only" in p.lower()


def test_answer_prompt_includes_query_and_scope():
    scoped = {"regime_names": ["Online Safety Act 2023"],
              "provisions": [{"number": "9", "heading": "Duties",
                              "snippet": "illegal content", "url": "http://p"}],
              "related_documents": [{"layer": "HansardDebate",
                                     "citation": "OSA debate",
                                     "url": "http://h"}],
              "regulatory_guidance": [{
                  "regime_id": "uk-ukpga-2023-50",
                  "regime_name": "Online Safety Act 2023",
                  "updated_at": "2026-06-27T17:00:00+00:00",
                  "guidance": [{
                      "regulator": "Ofcom",
                      "title": "Illegal content Codes of Practice",
                      "description": "Sets out compliance measures.",
                      "official_link": "https://www.ofcom.org.uk/",
                  }],
              }]}
    p = _answer_prompt("what are the duties?", scoped)
    assert "what are the duties?" in p
    assert "Online Safety Act 2023" in p
    assert "Related documents" in p
    assert "OSA debate" in p
    assert "metadata but not transcript/body text" in p
    assert "Cached Regulatory Guidance" in p
    assert "Illegal content Codes of Practice" in p
    assert "updated_at" in p


def test_regulatory_guidance_prompt_requires_live_official_search():
    p = _regulatory_guidance_prompt(_bundle())
    assert "web_search" in p
    assert "official" in p.lower()
    assert "live" in p.lower()
    assert "Ofcom code" in p


class _FakeMessages:
    def __init__(self, parsed=None, text=None):
        self._parsed, self._text = parsed, text
        self.parse_kwargs = self.create_kwargs = None

    def parse(self, **kwargs):
        self.parse_kwargs = kwargs
        return types.SimpleNamespace(parsed_output=self._parsed)

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self._text)])


class _FakeClient:
    def __init__(self, parsed=None, text=None):
        self.messages = _FakeMessages(parsed, text)


def test_draft_dossier_returns_six_fields_and_uses_opus():
    parsed = DossierFields(summary="s", scope="sc", process="pr",
                           consequence="c", guidance="g", obligations=[])
    client = _FakeClient(parsed=parsed)
    out = draft_dossier(_bundle(), client=client)
    assert out["summary"] == "s"
    assert set(out) >= {"summary", "scope", "process", "consequence",
                        "guidance", "obligations"}
    assert client.messages.parse_kwargs["model"] == "claude-opus-4-8"
    assert client.messages.parse_kwargs["thinking"] == {"type": "adaptive"}
    assert "output_config" not in client.messages.parse_kwargs
    assert client.messages.parse_kwargs["output_format"] is DossierFields


def test_refresh_regulatory_guidance_uses_web_search_tool():
    parsed = RegulatoryGuidanceFields(regulatory_guidance=[
        RegulatoryGuidanceItem(
            regulator="Ofcom",
            title="Online Safety Act guidance",
            description="Explains compliance expectations.",
            official_link="https://www.ofcom.org.uk/",
        )
    ])
    client = _FakeClient(parsed=parsed)
    out = refresh_regulatory_guidance(_bundle(), client=client)
    assert out[0]["regulator"] == "Ofcom"
    assert client.messages.parse_kwargs["model"] == "claude-opus-4-8"
    assert client.messages.parse_kwargs["tools"][0]["name"] == "web_search"
    assert client.messages.parse_kwargs["output_format"] is RegulatoryGuidanceFields


def test_answer_returns_text_and_uses_opus():
    client = _FakeClient(text="Ofcom regulates...")
    scoped = {"regime_names": ["OSA"], "provisions": []}
    out = answer("duties?", scoped, client=client)
    assert out == "Ofcom regulates..."
    assert client.messages.create_kwargs["model"] == "claude-opus-4-8"
    assert client.messages.create_kwargs["thinking"] == {"type": "adaptive"}
    assert client.messages.create_kwargs["output_config"] == {"effort": "medium"}
