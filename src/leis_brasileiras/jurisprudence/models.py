"""Public jurisprudence identities; observed classifications are not legal advice."""
from datetime import datetime
import hashlib
import json

FORMAT = "jurisprudence-v1"
PARSER_VERSION = "jurisprudence@1"
MAX_BYTES = 24 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RECORDS = 20000
MAX_FILES = 128


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_record(record: dict, observed_at: str) -> dict:
    """Keep the complete source projection, including records without an affirmed thesis."""
    court, kind, number = (record[key] for key in ("source", "tipo", "numero"))
    identity = (f"br:{court.lower()}:{kind}:{number}" if kind is not None
                else f"br:{court.lower()}:source-record:{record['sequencial_precedente']}")
    content = {key: value for key, value in record.items()
               if key not in {"extracted_at", "hash", "status_observation", "curation_review"}}
    situation = record.get("situacao")
    basis = "unknown" if situation is None else "parser_classification"
    if "status_observation" in record:
        basis = "dated_source_observation"
    return {
        "id": identity,
        "court": court, "type": kind, "number": number,
        "text": record.get("enunciado") or record.get("tese") or record.get("questao_submetida"),
        "has_thesis": record["has_thesis"],
        "source_url": record["url_fonte"], "observed_at": observed_at,
        "observation_precision": "day" if len(observed_at) == 10 else "instant",
        "situation": situation, "situation_basis": basis, "legal_validity": "unknown",
        "content_sha256": digest(json_bytes(content)), "source_record": record,
    }


def document(identifier: str, records: list[dict], observed_at: str, coverage: str) -> dict:
    datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    entries = [canonical_record(record, observed_at) for record in records]
    entries.sort(key=lambda entry: entry["id"])
    return {"format": FORMAT, "parser_version": PARSER_VERSION, "source": identifier,
            "observed_at": observed_at,
            "observation_precision": "day" if len(observed_at) == 10 else "instant",
            "coverage": coverage, "records": entries}
