"""Build a tiny hand-written sample corpus to prove the model end-to-end.

Exercises every key piece:
  - an Act with a provision, an SI made under it, a case considering it, an
    explanatory note explaining it (the authority graph);
  - a EuroVoc-style Concept thesaurus with SKOS relations, documents tagged
    ABOUT concepts, a `regulator` on each, plus neighbouring regimes
    (e-privacy, freedom of information) and an EU document (GDPR) sharing the
    data-protection concept — so "related regimes" and cross-jurisdiction
    alignment actually return results.

Writes canonical JSON to dataset/parsed/ and the thesaurus to
dataset/thesaurus/, ready for `legalgraph load|link|validate`.

    uv run python scripts/build_sample.py
"""

from __future__ import annotations

from pathlib import Path

from legalgraph import io
from legalgraph.canonical import (
    Concept, Document, Provision, Edge, EdgeType, DocType, Jurisdiction, Status,
    LegalForce, SourceMeta,
)

DATASET = Path(__file__).resolve().parents[1] / "dataset"
ICO = "Information Commissioner's Office (ICO)"

# --- thesaurus (controlled vocab; SKOS relations make regimes relatable) --- #
CONCEPTS = [
    Concept(id="eurovoc:dp", label="data protection",
            broader=["eurovoc:infolaw"], related=["eurovoc:eprivacy", "eurovoc:foi"]),
    Concept(id="eurovoc:eprivacy", label="privacy and electronic communications",
            broader=["eurovoc:infolaw"], related=["eurovoc:dp"]),
    Concept(id="eurovoc:foi", label="freedom of information",
            broader=["eurovoc:infolaw"], related=["eurovoc:dp"]),
    Concept(id="eurovoc:infolaw", label="information law"),
]

# --- the Act, with one provision (s.170) ---------------------------------- #
dpa = Document(
    id="uk-ukpga-2018-12", jurisdiction=Jurisdiction.UK, type=DocType.ACT,
    citation="Data Protection Act 2018", title="Data Protection Act 2018",
    date_enacted="2018-05-23", date_in_force="2018-05-25", status=Status.IN_FORCE,
    territorial_scope="UK-wide", regulator=ICO, concepts=["eurovoc:dp"],
    subject_tags=["data protection", "privacy"],
    provisions=[
        Provision(
            id="uk-ukpga-2018-12/s/170", number="170",
            heading="Unlawful obtaining etc of personal data",
            text="It is an offence for a person knowingly or recklessly to obtain "
                 "or disclose personal data without the consent of the controller.",
            legal_force=LegalForce.OPERATIVE,
        ),
    ],
    source=SourceMeta(url="https://www.legislation.gov.uk/ukpga/2018/12",
                      raw_format="akoma-ntoso"),
)

# --- an SI made under s.170 ----------------------------------------------- #
si = Document(
    id="uk-uksi-2019-419", jurisdiction=Jurisdiction.UK,
    type=DocType.STATUTORY_INSTRUMENT,
    citation="The Data Protection, Privacy and Electronic Communications "
             "(Amendments etc) (EU Exit) Regulations 2019",
    date_enacted="2019-02-28", status=Status.IN_FORCE, territorial_scope="UK-wide",
    regulator=ICO, concepts=["eurovoc:dp"],
    edges=[Edge(type=EdgeType.MADE_UNDER, target="uk-ukpga-2018-12/s/170")],
    source=SourceMeta(url="https://www.legislation.gov.uk/uksi/2019/419"),
)

# --- a case that considers s.170 ------------------------------------------ #
case = Document(
    id="uk-ewca-2021-1565", jurisdiction=Jurisdiction.UK, type=DocType.CASE,
    citation="Scott v LGBT Foundation Ltd [2021] EWCA 1565",
    ecli="ECLI:EW:CA:2021:1565", date_decided="2021-11-02", status=Status.IN_FORCE,
    court="Court of Appeal", level="EWCA",
    edges=[Edge(type=EdgeType.CONSIDERS, target="uk-ukpga-2018-12/s/170")],
    source=SourceMeta(url="https://caselaw.nationalarchives.gov.uk/ewca/2021/1565"),
)

# --- explanatory note that explains both the Act and s.170 ---------------- #
en = Document(
    id="uk-ukpgaen-2018-12", jurisdiction=Jurisdiction.UK,
    type=DocType.EXPLANATORY_NOTE,
    citation="Data Protection Act 2018 — Explanatory Notes", status=Status.IN_FORCE,
    regulator=ICO,
    edges=[
        Edge(type=EdgeType.EXPLAINS, target="uk-ukpga-2018-12"),
        Edge(type=EdgeType.EXPLAINS, target="uk-ukpga-2018-12/s/170"),
    ],
    source=SourceMeta(url="https://www.legislation.gov.uk/ukpga/2018/12/notes"),
)

# --- neighbouring regimes (related via SKOS) ------------------------------ #
pecr = Document(
    id="uk-uksi-2003-2426", jurisdiction=Jurisdiction.UK,
    type=DocType.STATUTORY_INSTRUMENT,
    citation="The Privacy and Electronic Communications (EC Directive) Regulations 2003",
    date_enacted="2003-09-18", status=Status.IN_FORCE, territorial_scope="UK-wide",
    regulator=ICO, concepts=["eurovoc:eprivacy"],
    source=SourceMeta(url="https://www.legislation.gov.uk/uksi/2003/2426"),
)
foia = Document(
    id="uk-ukpga-2000-36", jurisdiction=Jurisdiction.UK, type=DocType.ACT,
    citation="Freedom of Information Act 2000", title="Freedom of Information Act 2000",
    date_enacted="2000-11-30", status=Status.IN_FORCE, territorial_scope="UK-wide",
    regulator=ICO, concepts=["eurovoc:foi"],
    source=SourceMeta(url="https://www.legislation.gov.uk/ukpga/2000/36"),
)

# --- EU document sharing the data-protection concept (cross-jurisdiction) -- #
gdpr = Document(
    id="eu-celex-32016R0679", jurisdiction=Jurisdiction.EU, type=DocType.ACT,
    citation="Regulation (EU) 2016/679 (General Data Protection Regulation)",
    title="General Data Protection Regulation", celex="32016R0679",
    date_enacted="2016-04-27", date_in_force="2018-05-25", status=Status.IN_FORCE,
    territorial_scope="EU", regulator="European Data Protection Board (EDPB)",
    concepts=["eurovoc:dp"],
    source=SourceMeta(url="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                      raw_format="formex"),
)

if __name__ == "__main__":
    parsed = DATASET / "parsed"
    docs = [dpa, si, case, en, pecr, foia, gdpr]
    for doc in docs:
        path = io.write_document(doc, parsed)
        print(f"wrote {path.name}  (precedence={doc.precedence})")
    cpath = io.write_concepts(CONCEPTS, DATASET / "thesaurus")
    print(f"wrote {cpath.name}  ({len(CONCEPTS)} concepts)")
