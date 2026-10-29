"""Bounded consistency checks. Source authenticity requires replay against captured bytes."""
import json
from pathlib import Path

from .catalog import by_sigla
from .evidence import OBSERVATION_CONTRACT, observation, text_digest, verify_seal
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION, MAX_DOCUMENT_BYTES
from .reconciliation import reconcile


def _bounded(value):
    pending = [(value, 0)]
    count = size = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 40 or count > 3000000:
            raise ValueError("Excessive document")
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("Non-string key")
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            size += len(item.encode("utf-8"))
            if size > MAX_DOCUMENT_BYTES:
                raise ValueError("Excessive text")
        elif item is not None and type(item) not in (bool, int):
            raise ValueError("Non-JSON documentary value")


def check_document(document):
    _bounded(document)
    if set(document) != {"format", "observation_contract", "law", "provenance", "components",
                         "units", "evidence", "reconciliation", "structured_sha256", "revision"}:
        raise ValueError("Document fields")
    if document["format"] != CANONICAL_FORMAT or document["observation_contract"] != OBSERVATION_CONTRACT:
        raise ValueError("Unsupported format")
    law = document["law"]
    entry = by_sigla(law["aliases"][0])
    if entry is None or law != {"id": entry["public_id"], "aliases": [entry["sigla"]]}:
        raise ValueError("Law identity")
    provenance = document["provenance"]
    if set(provenance) != {"source_url", "observation", "basis", "raw_sha256", "parser_version"}:
        raise ValueError("Provenance fields")
    if provenance["source_url"] != entry["url"] or provenance["parser_version"] != CANONICAL_PARSER_VERSION:
        raise ValueError("Source provenance")
    observed = provenance["observation"]
    if observed != observation(observed["value"], observed["precision"]):
        raise ValueError("Observation")
    mapping = document["evidence"]
    if provenance["raw_sha256"] != mapping["raw_sha256"]:
        raise ValueError("Evidence hash")
    if provenance["basis"] not in {"source-html", "historical-clean-text"} or (
            provenance["basis"] == "source-html") != (mapping["raw_sha256"] is not None):
        raise ValueError("Evidence basis")
    texts = {}
    for item in mapping["texts"]:
        if item["id"] in texts or item["text_sha256"] != text_digest(item["text"]):
            raise ValueError("Duplicate or corrupt evidence")
        texts[item["id"]] = item
    parents = set()
    for component in document["components"]:
        if component["parent_id"] != entry["public_id"] or component["id"] in parents:
            raise ValueError("Component identity")
        if component["id"] != entry["public_id"] + "!" + component["label"]:
            raise ValueError("Component locator")
        parents.add(component["id"])
    ids = set()
    for index, unit in enumerate(document["units"], 1):
        if set(unit) != {"id", "parent_id", "locator", "kind", "label", "order", "readings",
                         "legal_validity", "text", "text_sha256", "quality"}:
            raise ValueError("Unexpected unit fields")
        if (unit["id"] in ids or unit["parent_id"] not in parents
                or not unit["id"].startswith(unit["parent_id"] + "/")
                or type(unit["order"]) is not int or unit["order"] != index
                or unit["legal_validity"] != "unknown" or not unit["readings"]
                or unit["kind"] not in {"article", "heading", "annex", "unclassified"}):
            raise ValueError("Unit identity or classification")
        ids.add(unit["id"])
        for number, reading in enumerate(unit["readings"], 1):
            if set(reading) != {"id", "source_order", "evidence_ids", "source_text", "text",
                               "text_sha256", "hierarchy", "source_statements", "dates", "mixed_markings"}:
                raise ValueError("Unexpected occurrence fields")
            if reading["id"] != unit["id"] + f"/occurrence-{number}":
                raise ValueError("Occurrence identity")
            refs = reading["evidence_ids"]
            if not refs or any(key not in texts or texts[key]["kind"] != "content" for key in refs):
                raise ValueError("Evidence reference")
            transcript = "".join(texts[key]["text"] for key in refs)
            marks = {bool(texts[key]["struck_by"]) for key in refs if texts[key]["text"].strip()}
            mixed = len(marks) > 1
            if (reading["source_text"] != transcript or reading["text_sha256"] != text_digest(transcript)
                    or reading["mixed_markings"] is not mixed
                    or reading["text"] != (None if mixed else transcript)):
                raise ValueError("Text or marking mismatch")
            if reading["dates"]:
                raise ValueError("Dates require an implemented source-bound event adapter")
            for statement in reading["source_statements"]:
                evidence = texts[statement["evidence_id"]]
                if (statement["evidence_id"] not in refs or statement["target"] is not None
                        or evidence["text"][statement["start"]:statement["end"]] != statement["literal"]):
                    raise ValueError("Unsupported source assertion")
        ambiguous = len(unit["readings"]) > 1 or any(r["mixed_markings"] for r in unit["readings"])
        text = None if ambiguous else unit["readings"][0]["text"]
        if (unit["quality"] != ("ambiguous" if ambiguous else "observed")
                or unit["text"] != text or unit["text_sha256"] != (text_digest(text) if text is not None else None)):
            raise ValueError("Silent reading selection")
    report = document["reconciliation"]
    census = None if report["source_identities"] is None else {
        "identities": report["source_identities"], "occurrences": report["source_occurrences"],
        "method": report["census_method"]}
    if report != reconcile(mapping, document["units"], census):
        raise ValueError("Reconciliation mismatch")
    verify_seal(document)


def validate_document(document):
    try:
        check_document(document)
        return {"ok": True, "units": len(document["units"]), "complete": document["reconciliation"]["complete"]}
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError):
        return {"ok": False, "complete": False}


def validate_path(path: Path):
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError("Invalid input")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate key")
                result[key] = value
            return result
        return validate_document(json.loads(path.read_bytes(), object_pairs_hook=unique))
    except (OSError, ValueError):
        return {"ok": False, "complete": False}
