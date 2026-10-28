"""Validate dated primary-source observations; collection never implies verification."""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit


OBSERVATION_FIELDS = {
    "court", "doc_type", "number", "record_hash", "situation", "checked_at", "source_url", "evidence_sha256"
}


def validate_status_observation(record, *, now=None):
    """Optional metadata, mandatory complete binding when supplied. No network or inference."""
    if "status_observation" not in record:
        return
    observation = record["status_observation"]
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
        raise ValueError("status_observation: incomplete or unknown fields")
    if any(not isinstance(value, str) or not value.strip() for value in observation.values()):
        raise ValueError("status_observation: fields must be nonempty strings")
    for field, source in (("court", "source"), ("doc_type", "tipo"), ("number", "numero"),
                          ("record_hash", "hash"), ("situation", "situacao")):
        if observation[field] != record.get(source):
            raise ValueError("status_observation: document/version/situation mismatch")
    if not re.fullmatch(r"(?:[0-9a-f]{16}|[0-9a-f]{64})", observation["record_hash"]):
        raise ValueError("status_observation: invalid content hash")
    if not re.fullmatch(r"[0-9a-f]{64}", observation["evidence_sha256"]):
        raise ValueError("status_observation: invalid evidence hash")
    situation = observation["situation"]
    if len(situation) > 256 or any(ord(char) < 32 for char in situation):
        raise ValueError("status_observation: invalid situation")
    _validate_date(observation["checked_at"], now or datetime.now(timezone.utc))
    validate_official_url(observation["source_url"], observation["court"])


def _validate_date(value, now):
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("status_observation: invalid verification instant") from error
    if "T" not in value or checked.tzinfo is None or checked > now:
        raise ValueError("status_observation: verification requires a past zoned instant")


def validate_official_url(value, court):
    """Source must belong to the issuing court; this validates identity, not its content."""
    try:
        uri = urlsplit(value)
        domain = court.lower() + ".jus.br"
        valid = (len(value) <= 2048 and not any(char.isspace() for char in value)
                 and uri.scheme == "https" and uri.username is None and uri.password is None
                 and uri.hostname is not None and (uri.hostname == domain or uri.hostname.endswith("." + domain))
                 and uri.port in (None, 443))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("status_observation: invalid official source URL") from error
    if not valid:
        raise ValueError("status_observation: invalid official source URL")
