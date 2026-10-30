"""Public format names and deterministic revision identifiers."""
import hashlib
import json

CANONICAL_FORMAT = "observed-law-v1"
CAPTURE_VERSION = 3
CORPUS_VERSION = 3
CANONICAL_PARSER_VERSION = "observed-legislation@2"
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024


def digest(value: object) -> str:
    """Hash a JSON value with stable serialization; never use as a permanent unit ID."""
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
