"""Legislative units from the shared parser, before legacy segmentation and overrides."""
from copy import deepcopy
from datetime import date, datetime
import re
import unicodedata

from .catalog import by_sigla
from .curation import load_curation
from .extraction import LEIS_CONFIG, parse_law
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION, digest, text_digest
from .transport import MAX_HTML_BYTES


def slug(label: str) -> str:
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def unit_kind(label: str) -> str:
    if re.match(r"^Art\.\s*\d", label):
        return "article"
    if label.startswith("ANEXO"):
        return "annex"
    if label.startswith("SIGNAT"):
        return "signatories"
    if label == "EMENTA":
        return "preamble_or_summary"
    return "other"


def observation_date(value: str, precision: str) -> str:
    if precision == "date":
        return date.fromisoformat(value).isoformat()
    if precision != "timestamp":
        raise ValueError("Unknown observation precision")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Observation timestamp requires timezone")
    return timestamp.date().isoformat()


def extract_document(clean_text: str, law: str, observed_at: str, *,
                     precision: str = "timestamp", raw_sha256: str | None = None,
                     prior_redactions: list[dict] | None = None) -> dict:
    """Extract article-level structure without guessing legal validity or merging overlaps.

    Duplicate occurrences stay in readings with quality=ambiguous. Consumers must not
    choose a reading by length or assume the last occurrence is legally applicable.
    This function does not fetch links, execute text, or persist anything.
    """
    entry = by_sigla(law)
    if entry is None:
        raise ValueError("Unknown law")
    if not isinstance(clean_text, str) or not clean_text or len(clean_text.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Invalid or excessive clean text")
    day = observation_date(observed_at, precision)
    cfg = LEIS_CONFIG[law]
    occurrences = []
    legacy, _ = parse_law(clean_text, law, cfg["versao"], cfg["url"], day, cfg,
                          units_out=occurrences)
    law_id = entry["public_id"]
    aliases = {}
    for record in legacy:
        base = re.sub(r" \(Parte \d+/\d+\)$", "", record["artigo"])
        aliases.setdefault(base, []).append({"id": record["id"], "label": record["artigo"]})
    units = {}
    components = {}
    for occurrence in occurrences:
        label = occurrence["label"]
        kind = unit_kind(label)
        component = occurrence["component"]
        if kind == "annex":
            component = slug(label)
        component_id = f"{law_id}!{component}"
        components.setdefault(component_id, {"id": component_id, "label": component,
                                              "parent_id": law_id})
        locator = re.sub(r"\s*\(ADCT\)$", "", label)
        if kind == "article":
            locator = locator.replace(".", "")  # Art. 1.337 and Art. 1337 share identity.
        unit_id = f"{component_id}/{slug(locator)}"
        unit = units.setdefault(unit_id, {
            "id": unit_id, "parent_id": component_id, "kind": kind,
            "label": label, "order": len(units) + 1, "quality": "observed",
            "text": None, "text_sha256": None, "readings": [], "legacy_aliases": [],
            "legal_validity": {"status": "unknown", "valid_from": None,
                               "valid_to": None, "evidence": []},
        })
        reading = {key: deepcopy(occurrence[key]) for key in (
            "text", "source_text", "hierarchy", "rubric", "observed_status", "metadata")}
        reading["text_sha256"] = text_digest(reading["text"])
        unit["readings"].append(reading)
        if len(unit["readings"]) == 1:
            unit["text"] = reading["text"]
            unit["text_sha256"] = reading["text_sha256"]
        else:
            unit["quality"] = "ambiguous"
            unit["text"] = unit["text_sha256"] = None
        # Aliases describe correspondence, not proof of equal text/metadata.
        unit["legacy_aliases"] = deepcopy(aliases.get(label, []))
    if not any(unit["kind"] == "article" for unit in units.values()):
        raise ValueError("No legislative article identified")
    curation_revision, annotations = load_curation(law)
    document = {
        "format": CANONICAL_FORMAT,
        "law": {"id": law_id, "aliases": [law], "name": entry["nome"],
                "designation": entry["numero"], "jurisdiction": "BR-federal",
                "authority": None, "issued_on": None, "external_identifiers": []},
        "provenance": {"source_url": cfg["url"], "observed_at": observed_at,
                       "observation_precision": precision, "raw_sha256": raw_sha256,
                       "clean_sha256": text_digest(clean_text),
                       "basis": "source-html" if raw_sha256 else "historical-clean-text",
                       "parser_version": CANONICAL_PARSER_VERSION,
                       "curation_revision": curation_revision},
        "structure_depth": "article", "components": list(components.values()),
        "units": list(units.values()), "editorial_annotations": annotations,
        "prior_redactions": deepcopy(prior_redactions or []),
        "limitations": ["Observation is not a determination of legal validity",
                        "Paragraphs and clauses are preserved as text, not addressable nodes",
                        "Hierarchy and source metadata may be incomplete",
                        "Editorial assertions require independent evidence review",
                        "Repeated labels retain all readings; no automatic resolution"],
    }
    # Content revision excludes capture time, so repeated observation is not a new text.
    document["content_revision"] = digest({"law": document["law"],
                                            "components": document["components"],
                                            "units": document["units"],
                                            "prior_redactions": document["prior_redactions"]})
    document["revision"] = digest(document)
    return document
