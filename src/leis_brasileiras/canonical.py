"""Observed legislation from intact evidence; no legal consolidation or editorial repair."""
from collections import OrderedDict
import re

from .catalog import by_sigla
from .evidence import OBSERVATION_CONTRACT, observation, seal, text_digest
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION
from .reconciliation import reconcile, source_article_census
from .source_map import html_map, text_map

ARTICLE = re.compile(r"^Art\s*\.?(?:\s*\.)?\s*(\d+(?:\.\d{3})*)(?:\s*[-–]\s*([A-Z]+)(?![A-Za-z])|([A-Z]+)(?![A-Za-z]))?(?=[.\sº°o-]|$)")
HEADING = re.compile(r"^(?:LIVRO|TÍTULO|TITULO|SUBTÍTULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO)\b")
ANNEX = re.compile(r"^ANEXO(?:\s+([IVXLCDM]+|\d+))?(?:\s|$)")
ADCT = "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"


def extract_document(source: bytes | str, law: str, observed_at: str, *,
                     precision: str = "timestamp", raw_sha256=None,
                     prior_redactions=None) -> dict:
    """Bytes are captured HTML; strings are incomplete historical derivations.

    The source-order transcript is NOT a consolidated reading. Mixed markings have
    no single text; callers retrieve fragments or occurrences explicitly.
    A detached hash cannot promote derived text into primary evidence.
    """
    entry = by_sigla(law)
    if entry is None:
        raise ValueError("Unknown law")
    if raw_sha256 is not None or prior_redactions is not None:
        raise ValueError("Supply captured bytes, not detached hashes or redactions")
    observed = observation(observed_at, precision)
    mapping = html_map(source, entry.get("parse", {}).get("encoding")) if isinstance(source, bytes) else text_map(source)
    blocks = []
    for item in mapping["texts"]:
        if item["kind"] == "content":
            key = item["block"] or item["path"]
            if not blocks or blocks[-1][0] != key:
                blocks.append((key, []))
            blocks[-1][1].append(item)
    units, components = OrderedDict(), OrderedDict()
    component = "main"
    current = None
    reading = None
    hierarchy = []

    def start(kind, label, locator, path):
        nonlocal current, reading
        component_id = f"{entry['public_id']}!{component}"
        components.setdefault(component_id, {"id": component_id, "label": component, "parent_id": entry["public_id"]})
        identity = f"{component_id}/{locator}"
        current = units.setdefault(identity, {"id": identity, "parent_id": component_id,
            "locator": f"{component}/{locator.removeprefix('art-')}", "kind": kind,
            "label": label, "order": len(units) + 1, "readings": [],
            "legal_validity": "unknown", "text": None, "text_sha256": None})
        reading = {"id": f"{identity}/occurrence-{len(current['readings']) + 1}",
                   "source_order": path, "evidence_ids": [], "source_text": "", "text": None,
                   "text_sha256": None, "hierarchy": list(hierarchy), "source_statements": [],
                   "dates": [], "mixed_markings": False}
        current["readings"].append(reading)

    for path, items in blocks:
        literal = "".join(item["text"] for item in items)
        normalized = re.sub(r"\s+", " ", literal).strip()
        match = ARTICLE.match(normalized)
        if normalized == ADCT:
            component, hierarchy = "adct", []
            start("heading", normalized, "heading-" + text_digest(path)[:16], path)
        elif ANNEX.match(normalized):
            component = "annex-" + text_digest(path)[:16]
            hierarchy = []
            start("annex", normalized, "heading", path)
        elif match:
            suffix = match[2] or match[3]
            number = match[1].replace(".", "") + ("-" + suffix if suffix else "")
            start("article", match[0].rstrip(), "art-" + number, path)
        elif HEADING.match(normalized):
            hierarchy = [{"text": literal, "evidence_ids": [item["id"] for item in items]}]
            start("heading", normalized, "heading-" + text_digest(path)[:16], path)
        elif current is None:
            start("unclassified", "", "unclassified-" + text_digest(path)[:16], path)
        for item in items:
            reading["evidence_ids"].append(item["id"])
            reading["source_text"] += item["text"]
            # Mentions are literal observations, not conclusions about the container.
            for marker in re.finditer(r"\b(?:revogad[oa]s?|vetad[oa]s?|suprimid[oa]s?|cancelad[oa]s?)\b", item["text"], re.I):
                reading["source_statements"].append({"literal": marker[0], "evidence_id": item["id"],
                    "start": marker.start(), "end": marker.end(), "target": None})
    by_id = {item["id"]: item for item in mapping["texts"]}
    if not any(unit["kind"] == "article" for unit in units.values()):
        raise ValueError("No legislative articles identified; retain raw source for diagnosis")
    for unit in units.values():
        for occurrence in unit["readings"]:
            marks = {bool(by_id[key]["struck_by"]) for key in occurrence["evidence_ids"] if by_id[key]["text"].strip()}
            occurrence["mixed_markings"] = len(marks) > 1
            occurrence["text_sha256"] = text_digest(occurrence["source_text"])
            if not occurrence["mixed_markings"]:
                occurrence["text"] = occurrence["source_text"]
        unit["quality"] = "ambiguous" if len(unit["readings"]) > 1 or any(r["mixed_markings"] for r in unit["readings"]) else "observed"
        if unit["quality"] == "observed":
            unit["text"] = unit["readings"][0]["text"]
            unit["text_sha256"] = text_digest(unit["text"])
    census = source_article_census(source, mapping["encoding"]) if isinstance(source, bytes) else None
    result = {"format": CANONICAL_FORMAT, "observation_contract": OBSERVATION_CONTRACT,
        "law": {"id": entry["public_id"], "aliases": [law]},
        "provenance": {"source_url": entry["url"], "observation": observed,
            "basis": "source-html" if isinstance(source, bytes) else "historical-clean-text",
            "raw_sha256": mapping["raw_sha256"], "parser_version": CANONICAL_PARSER_VERSION},
        "components": list(components.values()), "units": list(units.values()), "evidence": mapping,
        "reconciliation": reconcile(mapping, list(units.values()), census)}
    return seal(result)
