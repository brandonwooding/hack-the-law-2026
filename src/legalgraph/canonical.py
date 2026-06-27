"""The canonical, jurisdiction-agnostic representation of a legal document.

This is the contract between adapters (jurisdiction-specific) and the loader
(shared). Every adapter — UK legislation.gov.uk, EU CELLAR, ... — emits a list
of `Document` objects in exactly this shape. Nothing downstream knows or cares
which jurisdiction a record came from.

The `Provision` tree doubles as the PageIndex tree for intra-document retrieval:
one structure, no drift between the graph and the document index.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------- #
# Controlled vocabularies
# --------------------------------------------------------------------------- #
class Jurisdiction(str, Enum):
    UK = "UK"
    EU = "EU"


class DocType(str, Enum):
    """The six canonical layers + Treaty tier + ExplanatoryNote.

    Source-specific types map onto these:
      UK Act / EU Regulation|Directive|Decision -> ACT
      UK SI                                      -> STATUTORY_INSTRUMENT
      EU Delegated/Implementing act / RTS / ITS  -> REGULATORY_INSTRUMENT (if binding)
      FCA Handbook / PRA Rulebook                -> REGULATORY_INSTRUMENT
    """

    TREATY = "Treaty"                       # EU primary law (TEU/TFEU/Charter); constitutions
    ACT = "Act"                             # primary legislation
    STATUTORY_INSTRUMENT = "StatutoryInstrument"   # delegated, ministerial
    REGULATORY_INSTRUMENT = "RegulatoryInstrument" # delegated, regulator-made, BINDING
    REGULATORY_POLICY = "RegulatoryPolicy" # regulator policy/procedure; usually non-binding
    BILL = "Bill"                           # proposed legislation
    HANSARD_DEBATE = "HansardDebate"        # debates / travaux préparatoires
    CASE = "Case"                           # case law
    GUIDANCE = "Guidance"                   # soft law, non-binding
    EXPLANATORY_NOTE = "ExplanatoryNote"    # interpretive aid (UK EN, EU explanatory memo)


class Status(str, Enum):
    IN_FORCE = "in_force"
    REPEALED = "repealed"
    PROSPECTIVE = "prospective"
    PARTIALLY_IN_FORCE = "partially_in_force"
    UNKNOWN = "unknown"


class LegalForce(str, Enum):
    """Force at the *provision* level. Lets a single document mix binding and
    non-binding text (e.g. the FCA Handbook's R/E/G markers)."""

    OPERATIVE = "operative"        # ordinary statutory provision
    BINDING_RULE = "binding_rule"  # FCA 'R'
    EVIDENTIAL = "evidential"      # FCA 'E'
    GUIDANCE = "guidance"          # FCA 'G' / soft provision


class EdgeType(str, Enum):
    # structural
    CONTAINS = "CONTAINS"               # document/provision -> child provision
    # legislative lineage
    MADE_UNDER = "MADE_UNDER"           # SI/RegulatoryInstrument -> enabling Act provision
    BECAME = "BECAME"                   # Bill -> Act
    DEBATED_IN = "DEBATED_IN"           # Bill/Act -> HansardDebate
    # amendment (temporal: carry valid_from/valid_to)
    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    INSERTS = "INSERTS"
    SUBSTITUTES = "SUBSTITUTES"
    # case law
    CITES = "CITES"                     # Case -> Case
    CONSIDERS = "CONSIDERS"             # Case -> Provision
    INTERPRETS = "INTERPRETS"           # Case -> Provision
    APPLIES = "APPLIES"                 # Case -> Provision
    FOLLOWS = "FOLLOWS"                 # Case -> Case
    DISTINGUISHES = "DISTINGUISHES"     # Case -> Case
    OVERRULES = "OVERRULES"             # Case -> Case
    # soft law & aids
    ISSUED_UNDER = "ISSUED_UNDER"       # Guidance/RegulatoryPolicy -> Act/SI/provision
    EXPLAINS = "EXPLAINS"               # ExplanatoryNote -> Act / Provision
    # cross-jurisdiction (the payoff of one multi-jurisdiction graph)
    TRANSPOSES = "TRANSPOSES"           # national SI/Act -> EU Directive
    IMPLEMENTS = "IMPLEMENTS"           # national measure -> EU instrument
    # topical / taxonomy (powers "related regimes")
    ABOUT = "ABOUT"                     # Document -> Concept
    BROADER = "BROADER"                 # Concept -> Concept (SKOS)
    NARROWER = "NARROWER"               # Concept -> Concept (SKOS)
    RELATED = "RELATED"                 # Concept -> Concept (SKOS)


#: Default authority weight per layer. Higher = more authoritative.
#: For cases, refine with court level via `level_precedence()`.
PRECEDENCE: dict[DocType, int] = {
    DocType.TREATY: 100,
    DocType.ACT: 90,
    DocType.STATUTORY_INSTRUMENT: 80,
    DocType.REGULATORY_INSTRUMENT: 70,
    DocType.REGULATORY_POLICY: 15,
    DocType.CASE: 60,
    DocType.HANSARD_DEBATE: 30,
    DocType.EXPLANATORY_NOTE: 20,
    DocType.GUIDANCE: 10,
    DocType.BILL: 0,  # not yet law
}

#: Court-hierarchy bump for case law (added to the CASE base precedence).
COURT_PRECEDENCE: dict[str, int] = {
    # UK
    "UKSC": 9, "UKPC": 8, "EWCA": 6, "EWHC": 4, "UKUT": 3, "UKFTT": 1,
    # EU
    "CJEU": 9, "EGC": 5,  # Court of Justice / General Court
}


def default_precedence(doc_type: DocType, level: Optional[str] = None) -> int:
    base = PRECEDENCE.get(doc_type, 0)
    if doc_type == DocType.CASE and level:
        base += COURT_PRECEDENCE.get(level.upper(), 0)
    return base


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Provision(BaseModel):
    """A node within a document's internal tree (section, subsection, schedule,
    article, handbook rule...). Also serves as the PageIndex tree node."""

    id: str = Field(..., description="Stable, e.g. 'uk-ukpga-2018-12/s/170'")
    number: str = Field(..., description="e.g. '170', 'COBS 9.2.1'")
    heading: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = Field(None, description="deep link to this provision on the source site")
    legal_force: LegalForce = LegalForce.OPERATIVE
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    # point-in-time validity (UK legislation is heavily amended)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    children: list["Provision"] = Field(default_factory=list)

    def walk(self):
        """Depth-first iterator over self and all descendants."""
        yield self
        for child in self.children:
            yield from child.walk()


class Edge(BaseModel):
    """A relationship from this document (or one of its provisions) to another
    node identified by `target` id. Resolved in the link pass."""

    type: EdgeType
    target: str = Field(..., description="id of target Document or Provision")
    source_ref: Optional[str] = Field(
        None, description="id of the originating provision (defaults to the document)"
    )
    reverse: bool = Field(
        False, description="if true, create (target)-[type]->(this doc) instead of the default direction"
    )
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    note: Optional[str] = None


class SourceMeta(BaseModel):
    url: Optional[str] = None
    fetched_at: Optional[str] = None
    hash: Optional[str] = None
    raw_format: Optional[str] = Field(
        None, description="e.g. 'akoma-ntoso', 'formex', 'html'"
    )


class Concept(BaseModel):
    """A node in a controlled subject thesaurus (e.g. EuroVoc). Shared across
    documents and jurisdictions — this is what makes 'related regimes'
    navigable, because concepts relate to *each other* (SKOS), unlike free
    `subject_tags` which can only be equal.

    Tag a UK and an EU document with the same Concept and their regimes align
    across jurisdictions for free.
    """

    id: str = Field(..., description="scheme-prefixed, e.g. 'eurovoc:1854'")
    scheme: str = "EuroVoc"
    label: str
    alt_labels: list[str] = Field(default_factory=list)
    # SKOS relations to other concept ids (resolved in the link pass)
    broader: list[str] = Field(default_factory=list)
    narrower: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class Document(BaseModel):
    """One legal document in canonical form. Adapters emit lists of these."""

    id: str = Field(..., description="Stable, jurisdiction-prefixed, e.g. 'uk-ukpga-2018-12'")
    jurisdiction: Jurisdiction
    type: DocType
    citation: str
    title: Optional[str] = None

    # identifiers
    celex: Optional[str] = None   # EU
    ecli: Optional[str] = None    # case law (UK + EU)

    # temporal (kept separate on purpose — commencement often lags enactment)
    date_enacted: Optional[str] = None
    date_in_force: Optional[str] = None
    date_repealed: Optional[str] = None
    date_decided: Optional[str] = None
    published_date: Optional[str] = None
    updated_date: Optional[str] = None
    withdrawn_date: Optional[str] = None
    version: Optional[str] = None

    # classification
    status: Status = Status.UNKNOWN
    territorial_scope: Optional[str] = Field(
        None, description="E&W / Scotland / NI / UK-wide / EU"
    )
    court: Optional[str] = None
    level: Optional[str] = Field(None, description="UKSC, EWCA, CJEU, ...")
    regulator: Optional[str] = Field(
        None, description="competent authority, e.g. ICO / FCA / EDPB (relatedness signal)"
    )
    publisher: Optional[str] = None
    document_kind: Optional[str] = Field(
        None, description="source-level kind, e.g. guidance, corporate_policy, procedure"
    )
    legal_effect: Optional[str] = Field(
        None, description="binding, statutory_guidance, non_binding_guidance, policy_position"
    )
    precedence: Optional[int] = Field(
        None, description="authority weight; defaults from type+level if omitted"
    )
    subject_tags: list[str] = Field(
        default_factory=list, description="free fallback for un-mapped docs; prefer `concepts`"
    )
    concepts: list[str] = Field(
        default_factory=list, description="Concept ids this doc is ABOUT (controlled vocab)"
    )

    # internal structure (doubles as PageIndex tree)
    provisions: list[Provision] = Field(default_factory=list)

    # cross-document relationships
    edges: list[Edge] = Field(default_factory=list)

    # provenance
    landing_page_url: Optional[str] = None
    pdf_url: Optional[str] = None
    ocr_model: Optional[str] = None
    ocr_parsed_at: Optional[str] = None
    parse_version: Optional[str] = None
    source: SourceMeta = Field(default_factory=SourceMeta)

    @model_validator(mode="after")
    def _fill_precedence(self) -> "Document":
        if self.precedence is None:
            self.precedence = default_precedence(self.type, self.level)
        return self

    def all_provisions(self):
        for p in self.provisions:
            yield from p.walk()
