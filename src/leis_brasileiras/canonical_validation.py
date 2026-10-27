"""Bounded structural and provenance checks, independent of retrieval policies."""
import json
from pathlib import Path
import re

from .canonical import observation_date
from .catalog import LAWS
from .models import CANONICAL_FORMAT, MAX_DOCUMENT_BYTES, digest, text_digest


def _bounded(value: object) -> None:
    stack = [(value, 0)]
    count = 0
    size = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 32 or count > 2_000_000:
            raise ValueError("Excessive document structure")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("Non-string object key")
            stack.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif isinstance(item, list):
            stack.extend((part, depth + 1) for part in item)
        elif isinstance(item, str):
            size += len(item.encode("utf-8"))
            if size > MAX_DOCUMENT_BYTES or "\x00" in item or "\ufffd" in item:
                raise ValueError("Excessive or corrupted text")
        elif item is not None and type(item) not in (bool, int, float):
            raise ValueError("Non-JSON value")


def _hash(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid SHA-256")


def _fields(value: object, fields: dict) -> None:
    """Closed objects and exact JSON types (not bool-as-int coercion)."""
    if not isinstance(value, dict) or value.keys() != fields.keys():
        raise ValueError("Missing or unexpected fields")
    for key, types in fields.items():
        allowed = types if isinstance(types, tuple) else (types,)
        if type(value[key]) not in allowed:
            raise ValueError("Invalid field type")


def check_document(document: dict) -> None:
    """Raise on malformed data; ambiguity is explicit data, not permission to guess."""
    _bounded(document)
    _fields(document, {"format": str, "law": dict, "provenance": dict,
                       "structure_depth": str, "components": list, "units": list,
                       "editorial_annotations": list, "prior_redactions": list,
                       "limitations": list, "content_revision": str, "revision": str})
    if (any(not isinstance(item, str) for item in document["limitations"])
            or any(not isinstance(item, dict) for item in document["prior_redactions"])):
        raise ValueError("Invalid limitations or redactions")
    if document["format"] != CANONICAL_FORMAT or document["structure_depth"] != "article":
        raise ValueError("Unsupported canonical format")
    law = document["law"]
    _fields(law, {"id": str, "aliases": list, "name": str, "designation": str,
                  "jurisdiction": str, "authority": type(None), "issued_on": type(None),
                  "external_identifiers": list})
    entry = next((row for row in LAWS if row["public_id"] == law["id"]), None)
    if entry is None or law["aliases"] != [entry["sigla"]]:
        raise ValueError("Unknown or mismatched public law identity")
    if (law["name"] != entry["nome"] or law["designation"] != entry["numero"]
            or law["jurisdiction"] != "BR-federal" or law["external_identifiers"]):
        raise ValueError("Law metadata does not match catalog")
    provenance = document["provenance"]
    _fields(provenance, {"source_url": str, "observed_at": str, "observation_precision": str,
                        "raw_sha256": (str, type(None)), "clean_sha256": str, "basis": str,
                        "parser_version": str, "curation_revision": str})
    if not provenance["parser_version"]:
        raise ValueError("Missing parser version")
    if provenance["source_url"] != entry["url"]:
        raise ValueError("Source does not match catalog")
    observation_date(provenance["observed_at"], provenance["observation_precision"])
    _hash(provenance["clean_sha256"])
    if provenance["raw_sha256"] is not None:
        _hash(provenance["raw_sha256"])
    if provenance["basis"] != ("source-html" if provenance["raw_sha256"] else "historical-clean-text"):
        raise ValueError("Inconsistent source evidence")
    components = document["components"]
    for component in components:
        _fields(component, {"id": str, "label": str, "parent_id": str})
    component_ids = [component["id"] for component in components]
    if len(set(component_ids)) != len(component_ids) or any(
        component["parent_id"] != law["id"] or not component["id"].startswith(law["id"] + "!")
        for component in components
    ):
        raise ValueError("Invalid component hierarchy")
    units = document["units"]
    if not isinstance(units, list) or not 1 <= len(units) <= 50_000:
        raise ValueError("Invalid unit count")
    ids = set()
    for index, unit in enumerate(units, 1):
        _fields(unit, {"id": str, "parent_id": str, "kind": str, "label": str,
                       "order": int, "quality": str, "text": (str, type(None)),
                       "text_sha256": (str, type(None)), "readings": list,
                       "legacy_aliases": list, "legal_validity": dict})
        for alias in unit["legacy_aliases"]:
            _fields(alias, {"id": str, "label": str})
        if (unit["id"] in ids or unit["parent_id"] not in component_ids
                or not unit["id"].startswith(unit["parent_id"] + "/") or unit["order"] != index):
            raise ValueError("Invalid unit identity, parent or order")
        ids.add(unit["id"])
        if unit["kind"] not in {"article", "annex", "signatories", "preamble_or_summary", "other"}:
            raise ValueError("Invalid unit kind")
        if not isinstance(unit["label"], str) or not unit["label"]:
            raise ValueError("Missing unit label")
        readings = unit["readings"]
        if not isinstance(readings, list) or not 1 <= len(readings) <= 1000:
            raise ValueError("Invalid readings")
        for reading in readings:
            _fields(reading, {"text": str, "text_sha256": str, "source_text": str,
                             "hierarchy": list, "rubric": str, "observed_status": str,
                             "metadata": dict})
            _fields(reading["metadata"], {"partial_vetoes": list, "amendments": list,
                                         "references": dict, "source_notes": list,
                                         "constitutional_references": list})
            if not reading["text"] or reading["text_sha256"] != text_digest(reading["text"]):
                raise ValueError("Reading text integrity failed")
            if not isinstance(reading["source_text"], str) or not reading["source_text"]:
                raise ValueError("Missing source wording")
            if reading["observed_status"] not in {"vigente", "revogado", "vetado_total"}:
                raise ValueError("Invalid observed classification")
            if not isinstance(reading["metadata"], dict) or not isinstance(reading["hierarchy"], list):
                raise ValueError("Invalid reading metadata")
            for heading in reading["hierarchy"]:
                _fields(heading, {"level": str, "number": str, "title": str})
                if heading["level"] not in {"book", "title", "subtitle", "chapter", "section"}:
                    raise ValueError("Unknown hierarchy level")
                if not all(isinstance(heading[key], str) for key in ("number", "title")):
                    raise ValueError("Invalid heading")
        if len(readings) > 1:
            if unit["quality"] != "ambiguous" or unit["text"] is not None or unit["text_sha256"] is not None:
                raise ValueError("Ambiguous readings must not select text")
        elif (unit["quality"] != "observed" or unit["text"] != readings[0]["text"]
              or unit["text_sha256"] != readings[0]["text_sha256"]):
            raise ValueError("Unit does not match its reading")
        if unit["legal_validity"] != {"status": "unknown", "valid_from": None,
                                      "valid_to": None, "evidence": []}:
            raise ValueError("This format does not establish legal validity")
    if not any(unit["kind"] == "article" for unit in units):
        raise ValueError("No article found")
    for annotation in document["editorial_annotations"]:
        if (not isinstance(annotation, dict) or set(annotation) != {
                "kind", "target_label", "assertion", "origin", "review_status", "evidence"}
                or not isinstance(annotation["kind"], str)
                or not isinstance(annotation["target_label"], str)):
            raise ValueError("Invalid editorial annotation")
        if (annotation["origin"] != "editorial" or annotation["review_status"] != "pending"
                or annotation["evidence"] != []):
            raise ValueError("Unreviewed annotation presented as verified")
    if digest(document["editorial_annotations"]) != provenance["curation_revision"]:
        raise ValueError("Curation revision mismatch")
    expected_content = digest({key: document[key] for key in ("law", "components", "units", "prior_redactions")})
    if expected_content != document["content_revision"]:
        raise ValueError("Content revision mismatch")
    if digest({key: value for key, value in document.items() if key != "revision"}) != document["revision"]:
        raise ValueError("Document revision mismatch")


def validate_document(document: object) -> dict:
    try:
        check_document(document)
        return {"ok": True, "units": len(document["units"]),
                "ambiguous_units": sum(unit["quality"] == "ambiguous" for unit in document["units"])}
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError):
        return {"ok": False, "error": "Invalid canonical structure or provenance"}


def validate_path(path: Path) -> dict:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError("Invalid document file")
        return validate_document(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        return {"ok": False, "error": "Unreadable or excessive canonical document"}
