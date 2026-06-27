"""Parse legislation.gov.uk CLML XML into canonical Documents.

CLML structure (observed on real Acts/SIs):
    Legislation[@DocumentURI,@RestrictExtent]
      Primary|Secondary
        Body
          Part[@id,@DocumentURI] > Number, Title
            P1group > Title (the section heading) > P1[@DocumentURI] (section)
              Pnumber, P1para > P2 (subsection) > P2para > P3 ...
        Schedules > Schedule ...
      Commentaries > Commentary (amendment / in-force effects)
    ukm:Metadata > ukm:PrimaryMetadata|SecondaryMetadata
      Year, Number, EnactmentDate, ISBN, UnappliedEffects

Provisions carry @DocumentURI, which we turn into stable ids
(e.g. uk-ukpga-2023-50/section/1). The Provision tree doubles as the PageIndex
tree, so we keep Parts/Chapters/Schedules as structural nodes.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Optional

from ...canonical import (
    Document, DocType, Jurisdiction, Provision, SourceMeta, Status,
)

# Primary-legislation type prefixes (everything else we treat as secondary/SI).
PRIMARY_PREFIXES = {"ukpga", "asp", "anaw", "nia", "apni", "aosp", "aep", "apgb", "gbla"}

# Transparent wrappers we recurse through without making a node.
_TRANSPARENT = {"Body", "BlockAmendment"}
# Structural containers we DO make a node for (and recurse into).
_STRUCTURAL = {"Part", "Chapter", "Pblock", "PsubBlock", "Schedule", "Schedules", "Group"}
# Numbered provisions.
_NUMBERED = {"P1", "P2", "P3", "P4", "P5", "P6", "P7"}
# Subtrees whose text we never fold into a provision's body text.
_SKIP_TEXT = {"Pnumber", "Number", "Title", "Subtitle", "CommentaryRef"}


def _ln(tag: str) -> str:
    return tag.split("}")[-1]


def _id_from_uri(uri: str) -> Optional[str]:
    """http://www.legislation.gov.uk/ukpga/2023/50/section/1 ->
    uk-ukpga-2023-50/section/1 ; act-level -> uk-ukpga-2023-50"""
    if "legislation.gov.uk/" not in uri:
        return None
    parts = uri.split("legislation.gov.uk/")[-1].strip("/").split("/")
    if len(parts) < 3:
        return None
    act = "uk-" + "-".join(parts[:3])
    suffix = "/".join(parts[3:])
    return f"{act}/{suffix}" if suffix else act


def notes_url(xml_text: str) -> Optional[str]:
    """Return the Explanatory Notes page URL if the Act XML advertises one
    (via its atom navigation link), else None. No extra HTTP request."""
    root = ET.fromstring(xml_text)
    for el in root.iter():
        if _ln(el.tag) == "link":
            rel = el.attrib.get("rel", "")
            if "navigation/notes" in rel and "toc" not in rel:
                return el.attrib.get("href")
    return None


def _child_text(el: ET.Element, names: set[str]) -> Optional[str]:
    for c in el:
        if _ln(c.tag) in names:
            t = " ".join(s.strip() for s in c.itertext() if s.strip())
            if t:
                return t
    return None


def _body_text(el: ET.Element) -> Optional[str]:
    """Text of `el` excluding numbered sub-provisions and label subtrees."""
    parts: list[str] = []

    def rec(e: ET.Element, root: bool) -> None:
        tag = _ln(e.tag)
        if not root and (tag in _NUMBERED or tag in _STRUCTURAL or tag in _SKIP_TEXT):
            return
        if e.text and e.text.strip():
            parts.append(e.text.strip())
        for c in e:
            rec(c, False)
            if c.tail and c.tail.strip():
                parts.append(c.tail.strip())

    rec(el, True)
    text = " ".join(parts).strip()
    return text or None


def _section_heading(el: ET.Element, parents: dict) -> Optional[str]:
    own = _child_text(el, {"Title"})
    if own:
        return own
    # sections carry their heading on the enclosing P1group
    p = parents.get(el)
    while p is not None:
        if _ln(p.tag) == "P1group":
            return _child_text(p, {"Title"})
        if _ln(p.tag) in _NUMBERED or _ln(p.tag) in _STRUCTURAL:
            break
        p = parents.get(p)
    return None


def _collect_child_nodes(el: ET.Element) -> list[ET.Element]:
    """Next level of numbered/structural elements, descending through any
    other wrapper (so P2s inside P1para are found) but not into found nodes."""
    out: list[ET.Element] = []
    for c in el:
        if _ln(c.tag) in _NUMBERED or _ln(c.tag) in _STRUCTURAL:
            out.append(c)
        else:
            out.extend(_collect_child_nodes(c))
    return out


def _build_node(el: ET.Element, parents: dict, parent_pid: str, index: int) -> Provision:
    uri = el.attrib.get("DocumentURI")
    pid = _id_from_uri(uri) if uri else None
    number = _child_text(el, {"Pnumber", "Number"})
    heading = _section_heading(el, parents)
    if not pid:  # deterministic path-based id (idempotent across runs)
        slug = (number or _ln(el.tag)).strip().replace(" ", "_")
        pid = f"{parent_pid}/{slug}-{index}"
    prov = Provision(
        id=pid,
        number=number or heading or _ln(el.tag),
        heading=heading,
        text=_body_text(el),
        url=uri.replace("http://", "https://") if uri else None,
    )
    for i, child in enumerate(_collect_child_nodes(el)):
        prov.children.append(_build_node(child, parents, pid, i))
    return prov


def parse_document(
    xml_text: str,
    leg_id: str,
    *,
    regulator: Optional[str] = None,
    concepts: Optional[list[str]] = None,
    source_url: Optional[str] = None,
) -> Document:
    root = ET.fromstring(xml_text)
    parents = {child: parent for parent in root.iter() for child in parent}

    # --- metadata ---
    meta = next((e for e in root.iter() if _ln(e.tag) in
                 ("PrimaryMetadata", "SecondaryMetadata")), None)
    title = next((e.text for e in root.iter()
                  if _ln(e.tag) == "title" and e.text), leg_id)
    enacted = None
    extent = root.attrib.get("RestrictExtent")
    in_force_date = root.attrib.get("RestrictStartDate")
    if meta is not None:
        for c in meta:
            if _ln(c.tag) in ("EnactmentDate", "MadeDate"):
                enacted = c.attrib.get("Date")

    prefix = leg_id.split("/")[0]
    is_primary = prefix in PRIMARY_PREFIXES
    doc_type = DocType.ACT if is_primary else DocType.STATUTORY_INSTRUMENT
    act_id = "uk-" + leg_id.replace("/", "-")

    # --- provisions: parse Primary/Secondary (skips Commentaries sibling) ---
    container = next((e for e in root.iter() if _ln(e.tag) in
                      ("Primary", "Secondary")), root)
    provisions = [_build_node(top, parents, act_id, i)
                  for i, top in enumerate(_collect_child_nodes(container))]

    return Document(
        id=act_id,
        jurisdiction=Jurisdiction.UK,
        type=doc_type,
        citation=title,
        title=title,
        date_enacted=enacted,
        date_in_force=in_force_date,
        status=Status.IN_FORCE,
        territorial_scope=extent,
        regulator=regulator,
        concepts=concepts or [],
        provisions=provisions,
        source=SourceMeta(url=source_url, raw_format="clml",
                          hash=hashlib.sha256(xml_text.encode()).hexdigest()),
    )
