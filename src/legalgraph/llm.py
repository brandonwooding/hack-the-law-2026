"""Claude synthesis — the only place the app calls Anthropic.

Two jobs: draft a regime dossier (structured, grounded in the regime subgraph)
and answer a scoped chat question. The anthropic import is lazy so the rest of
the system (and /regimes) runs without the SDK or a key. Model is Opus 4.8 with
adaptive thinking; no sampling params (they 400 on 4.8).
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from .db import load_dotenv

MODEL = "claude-opus-4-8"
_THINKING = {"type": "adaptive"}
_EFFORT = {"effort": "medium"}


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


def _answer_prompt(query: str, scoped: dict) -> str:
    names = ", ".join(scoped.get("regime_names", []))
    return (
        "Answer the question using ONLY the provisions below, which are scoped to "
        f"the user's confirmed regimes ({names}). Cite provisions by number and "
        "include their source URLs. If the answer is not in the material, say so.\n\n"
        f"Question: {query}\n\n"
        f"Provisions:\n{json.dumps(scoped.get('provisions', []), indent=2)}"
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


def answer(query: str, scoped: dict, client=None) -> str:
    client = client or _client()
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, thinking=_THINKING, output_config=_EFFORT,
        messages=[{"role": "user", "content": _answer_prompt(query, scoped)}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")
