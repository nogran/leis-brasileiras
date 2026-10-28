"""Individual judgments: official identity and reviewed context, never a synthetic súmula."""
import hashlib
import json
import re
from .provenance import validate_official_url, _validate_date
from datetime import date, datetime, timezone

CONTEXT_FIELDS = {"document_id", "case_reference", "facts", "question", "holding", "limits",
                  "source_url", "evidence_sha256"}
REVIEW_FIELDS = {"decision", "reviewer", "reviewed_at", "record_hash", "evidence_sha256", "approval_ref"}
CONTENT_FIELDS = ("source", "tipo", "numero", "enunciado", "has_thesis", "situacao", "ramo",
                  "orgao_julgador", "referencia_legislativa", "data_julgamento", "url_fonte", "decision_context")


def content_hash(record):
    """Version content and scope together; dates of collection/review are not content."""
    raw = json.dumps({key: record.get(key) for key in CONTENT_FIELDS}, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strings(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("acordao: incomplete or unknown fields")
    for text in value.values():
        if not isinstance(text, str) or not text.strip() or len(text) > 16000 or "\x00" in text:
            raise ValueError("acordao: invalid text field")


def validate_decision(record, *, require_review=False):
    if record.get("tipo") != "acordao":
        if "decision_context" in record or "curation_review" in record:
            raise ValueError("acordao: context cannot masquerade as another document type")
        return
    context = record.get("decision_context")
    _strings(context, CONTEXT_FIELDS)
    identity = context["document_id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}", identity) or identity != record.get("numero"):
        raise ValueError("acordao: number must be the official document identity, not just the case")
    if (record.get("has_thesis") is not True or not isinstance(record.get("enunciado"), str)
            or not record["enunciado"].strip() or record.get("tese") is not None
            or "\x00" in record["enunciado"] or not record.get("orgao_julgador")
            or not record.get("data_julgamento")):
        raise ValueError("acordao: official text, body and judgment date required")
    try:
        judgment_date = date.fromisoformat(record["data_julgamento"])
    except (ValueError, TypeError) as error:
        raise ValueError("acordao: invalid judgment date") from error
    if judgment_date > date.today():
        raise ValueError("acordao: future judgment date")
    validate_official_url(context["source_url"], record.get("source"))
    if record.get("url_fonte") != context["source_url"] or not re.fullmatch(r"[0-9a-f]{64}", context["evidence_sha256"]):
        raise ValueError("acordao: source identity/evidence mismatch")
    if record.get("hash") != content_hash(record):
        raise ValueError("acordao: content/scope hash mismatch")
    review = record.get("curation_review")
    if review is None:
        if require_review:
            raise ValueError("acordao: human review required before ingestion")
        return
    _strings(review, REVIEW_FIELDS)
    if (review["decision"] != "approved" or review["record_hash"] != record["hash"]
            or review["evidence_sha256"] != context["evidence_sha256"]):
        raise ValueError("acordao: approval does not cover this content and primary evidence")
    _validate_date(review["reviewed_at"], datetime.now(timezone.utc))
