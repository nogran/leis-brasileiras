"""Bounded structural and semantic validation, independent of any database or LLM."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

from .catalog import source
from .decisions import validate_decision
from .models import FORMAT, PARSER_VERSION, MAX_RECORDS, MAX_TOTAL_BYTES, canonical_record
from .provenance import validate_official_url, validate_status_observation

TYPES = {
    "stj_temas": {"tema_repetitivo", "controversia", "iac", "puil", "sirdr", None},
    "stj_sumulas": {"sumula"}, "stf_teses_rg": {"tese_repercussao_geral"},
    "stf_sumulas_vinculantes": {"sumula_vinculante"},
    "tjpe_sumulas": {"sumula_tj"}, "tjmg_sumulas": {"sumula_tj"},
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def load_json(path: Path) -> object:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError("Invalid or excessive JSON input")
    with path.open("rb") as stream:
        raw = stream.read(MAX_TOTAL_BYTES + 1)
    if len(raw) > MAX_TOTAL_BYTES:
        raise ValueError("Excessive JSON input")
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))


def validate_document(value: dict) -> dict:
    from .observed import FORMAT as OBSERVED_FORMAT, validate_observed

    if isinstance(value, dict) and value.get("format") == OBSERVED_FORMAT:
        return validate_observed(value)
    if not isinstance(value, dict) or set(value) != {
        "format", "parser_version", "source", "observed_at", "observation_precision", "coverage", "records"
    }:
        raise ValueError("Invalid jurisprudence document shape")
    if value["format"] != FORMAT or value["parser_version"] != PARSER_VERSION:
        raise ValueError("Unsupported jurisprudence format or parser")
    identifier = value["source"]
    source(identifier)
    if value["coverage"] not in {"source_snapshot", "sample"}:
        raise ValueError("Coverage must be explicit")
    if value["observation_precision"] == "day":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["observed_at"]) or date.fromisoformat(value["observed_at"]) > datetime.now(timezone.utc).date():
            raise ValueError("Invalid historical observation date")
    else:
        instant = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
        if value["observation_precision"] != "instant" or instant.tzinfo is None or instant > datetime.now(timezone.utc):
            raise ValueError("Capture requires a past zoned observation date")
    records = value["records"]
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("Empty or excessive record set")
    identities = set()
    for entry in records:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_record"), dict):
            raise ValueError("Missing complete source record")
        record = entry["source_record"]
        court = identifier.split("_")[0].upper()
        if record.get("source") != court or record.get("tipo") not in TYPES[identifier]:
            raise ValueError("Court or type does not match the selected source")
        if record.get("tipo") is None:
            sequence = record.get("sequencial_precedente")
            if record.get("tipo_precedente") is not None or not isinstance(sequence, str) or not re.fullmatch(r"[0-9]{1,12}", sequence):
                raise ValueError("Unclassified STJ record requires its explicit official source identity")
        number = record.get("numero")
        if not isinstance(number, str) or not re.fullmatch(r"[0-9]{1,6}", number):
            raise ValueError("Invalid official record number")
        if type(record.get("has_thesis")) is not bool:
            raise ValueError("has_thesis must be boolean")
        if record.get("situacao") is not None and not isinstance(record["situacao"], str):
            raise ValueError("Invalid situation field")
        if not isinstance(record.get("hash"), str) or not re.fullmatch(r"(?:[a-f0-9]{16}|[a-f0-9]{64})", record["hash"]):
            raise ValueError("Invalid source projection hash")
        text = record.get("enunciado") or record.get("tese")
        if record["has_thesis"] and (not isinstance(text, str) or not text.strip()):
            raise ValueError("Affirmed thesis requires text")
        for key, field in record.items():
            if isinstance(field, str) and (len(field) > 200000 or "\x00" in field):
                raise ValueError("Invalid or excessive text field")
        if record.get("extracted_at") != value["observed_at"][:10]:
            raise ValueError("Source record date does not match capture")
        validate_official_url(record["url_fonte"], court)
        validate_status_observation(record)
        validate_decision(record)
        expected = canonical_record(record, value["observed_at"])
        if entry != expected:
            raise ValueError("Identity, content hash or observation mismatch")
        if entry["id"] in identities:
            raise ValueError("Duplicate official identity; resolve conflicting readings explicitly")
        identities.add(entry["id"])
    return {"ok": True, "source": identifier, "records": len(records), "coverage": value["coverage"]}
