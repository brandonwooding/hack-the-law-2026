"""Claude synthesis — the only place the app calls Anthropic.

Two jobs: draft a regime dossier (structured, grounded in the regime subgraph)
and answer a scoped chat question. The anthropic import is lazy so the rest of
the system (and /regimes) runs without the SDK or a key. Model is Opus 4.8 with
adaptive thinking; no sampling params (they 400 on 4.8).
"""
from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel

from .db import load_dotenv

MODEL = "claude-opus-4-8"
_THINKING = {"type": "adaptive"}
_EFFORT = {"effort": "medium"}
_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 8,
}


class Obligation(BaseModel):
    text: str
    reference: str
    url: str


class DossierFields(BaseModel):
    summary: str
    scope: str
    process: str
    consequence: str
    obligations: list[Obligation]
    guidance: str


class RegulatoryGuidanceItem(BaseModel):
    regulator: str
    title: str
    description: str
    official_link: str


class RegulatoryGuidanceFields(BaseModel):
    regulatory_guidance: list[RegulatoryGuidanceItem]


def _client():
    import anthropic
    load_dotenv()
    return anthropic.Anthropic()


def _dossier_prompt(bundle: dict) -> str:
    return (
        "You are a legal-research assistant. Using ONLY the material below, write "
        "a dossier for this regulatory regime. Every obligation reference and any "
        "case you name MUST come from the material — do not invent citations.\n\n"
        f"Regime: {bundle.get('name')}\n"
        f"Anchor: {bundle.get('anchor', {}).get('citation')}\n\n"
        f"Provisions:\n{json.dumps(bundle.get('provisions', []), indent=2)}\n\n"
        f"Cases:\n{json.dumps(bundle.get('cases', []), indent=2)}\n\n"
        f"Guidance:\n{json.dumps(bundle.get('guidance', []), indent=2)}\n\n"
        "Fill: summary, scope, process (how it is regulated/enforced), "
        "consequence (penalties), obligations (each with a real reference + url "
        "from the provisions/cases above), and guidance (practical advice)."
    )


def _regulatory_guidance_prompt(bundle: dict) -> str:
    return (
        "You are a legal-research assistant. Perform a live web search to identify "
        "the official regulatory guidance for this Act/regime. Do not rely on "
        "internal training data for this section.\n\n"
        "Find:\n"
        "1. The primary regulatory bodies responsible for enforcing this act or "
        "overseeing compliance.\n"
        "2. The specific regulatory policies, rules, booklets, codes, or guidance "
        "documents they have published to help organizations comply.\n\n"
        "Requirements:\n"
        "- Use the web_search tool.\n"
        "- Use only official regulatory, government, or agency domains.\n"
        "- Verify each official_link is a live official source URL.\n"
        "- Prefer exact source documents or official landing pages for the named "
        "document over secondary summaries.\n"
        "- If multiple regulators are involved, include one row per regulator and "
        "document pair, ordered by regulator so related rows are grouped.\n"
        "- Keep each description to 1-2 sentences and cover what that document "
        "specifically helps organizations do.\n"
        f"- Treat the search as current as of {date.today().isoformat()}.\n\n"
        f"Regime: {bundle.get('name')}\n"
        f"Anchor: {bundle.get('anchor', {}).get('citation')}\n"
        f"Known in-graph guidance metadata:\n"
        f"{json.dumps(bundle.get('guidance', []), indent=2)}\n\n"
        "Return structured data only. Use these fields for each row: regulator, "
        "title, description, official_link."
    )


def _answer_prompt(query: str, scoped: dict) -> str:
    names = ", ".join(scoped.get("regime_names", []))
    return (
        "Answer the question using ONLY the material below, which is scoped to "
        f"the user's confirmed regimes ({names}). The material may include both "
        "provisions and related documents from the regime neighbourhood. Cite "
        "provisions by number and cite related documents by citation/title with "
        "their source URLs. If a related document only has metadata, do not claim "
        "to know its full contents; say the dataset contains the related document "
        "metadata but not transcript/body text. You may also use the cached "
        "Regulatory Guidance section from the dossier when it is provided. Cite "
        "those entries by regulator and document/policy title with their official "
        "links, and mention the cached updated_at timestamp if freshness matters. "
        "Do not claim you refreshed those links during this chat turn.\n\n"
        f"Question: {query}\n\n"
        f"Confirmed regimes:\n{json.dumps(scoped.get('regimes', []), indent=2)}\n\n"
        f"Provisions:\n{json.dumps(scoped.get('provisions', []), indent=2)}\n\n"
        "Related documents in the selected regime neighbourhood "
        f"(debates, guidance, SIs, cases, bills, notes):\n"
        f"{json.dumps(scoped.get('related_documents', []), indent=2)}\n\n"
        "Cached Regulatory Guidance from the selected regime dossiers:\n"
        f"{json.dumps(scoped.get('regulatory_guidance', []), indent=2)}"
    )


def draft_dossier(bundle: dict, client=None) -> dict:
    client = client or _client()
    # NB: messages.parse populates output_config.format from output_format; do not
    # also pass output_config here or it would clobber the schema. Effort defaults
    # to high under adaptive thinking, which is fine for a one-time dossier.
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000, thinking=_THINKING,
        output_format=DossierFields,
        messages=[{"role": "user", "content": _dossier_prompt(bundle)}],
    )
    return resp.parsed_output.model_dump()


def refresh_regulatory_guidance(bundle: dict, client=None) -> list[dict]:
    client = client or _client()
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000, thinking=_THINKING,
        tools=[_WEB_SEARCH_TOOL],
        output_format=RegulatoryGuidanceFields,
        messages=[{"role": "user", "content": _regulatory_guidance_prompt(bundle)}],
    )
    return resp.parsed_output.model_dump()["regulatory_guidance"]


def answer(query: str, scoped: dict, client=None) -> str:
    client = client or _client()
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, thinking=_THINKING, output_config=_EFFORT,
        messages=[{"role": "user", "content": _answer_prompt(query, scoped)}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")
