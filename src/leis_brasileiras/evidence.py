"""Shared observation primitives. Hashes and dates never establish legal validity."""
from datetime import date, datetime
import hashlib
import json

OBSERVATION_CONTRACT = "source-observation-v1"
MAX_SOURCE_BYTES = 24 * 1024 * 1024
MAX_NODES = 250000


def raw_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def text_digest(text: str) -> str:
    """SHA-256 of exact UTF-8 text, without Unicode/whitespace normalization."""
    return raw_digest(text.encode("utf-8"))


def structured_digest(value: object) -> str:
    """Sorted-key compact UTF-8 JSON; array order significant, non-finite forbidden."""
    return text_digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False))


def observation(value: str, precision: str) -> dict:
    if precision in {"date", "day"}:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Invalid observation day")
        precision = "day"
    elif precision in {"timestamp", "instant"}:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or "T" not in value:
            raise ValueError("Observation instant requires timezone")
        precision = "instant"
    else:
        raise ValueError("Unknown observation precision")
    return {"value": value, "precision": precision}


def seal(document: dict) -> dict:
    """Separate documentary content from capture/execution metadata."""
    content = {key: value for key, value in document.items()
               if key not in {"provenance", "reconciliation", "revision", "structured_sha256"}}
    document["structured_sha256"] = structured_digest(content)
    document["revision"] = structured_digest({k: v for k, v in document.items() if k != "revision"})
    return document


def verify_seal(document: dict) -> None:
    copy = {k: v for k, v in document.items() if k not in {"revision", "structured_sha256"}}
    seal(copy)
    if any(copy[k] != document.get(k) for k in ("revision", "structured_sha256")):
        raise ValueError("Document hash mismatch")
