"""Pure extraction results and filesystem provenance, independent of application storage."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

from . import __version__
from .extraction import LEIS_CONFIG, PARSER_VERSION, harvest_redacoes_riscadas, hash_texto, html_to_clean_text, parse_law
from .transport import MAX_HTML_BYTES
from .canonical import extract_document
from .compatibility import LEGACY_FORMAT
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION, CAPTURE_VERSION


@dataclass
class Capture:
    law: str
    captured_at: str
    source_url: str
    raw_html: bytes
    clean_text: str
    articles: list[dict]
    prior_redactions: dict
    canonical: dict | None = None


def extract_html(raw_html: bytes, law: str, captured_at: str, *, format: str = CANONICAL_FORMAT) -> Capture:
    """Parse a trusted catalog identity and untrusted HTML bytes without executing content.

    captured_at must include a timezone; observation is not legal validity. Application
    Database identifiers are not part of either public representation.
    """
    if law not in LEIS_CONFIG:
        raise ValueError("Unknown law code")
    if format != CANONICAL_FORMAT:
        raise ValueError("Legacy generation disabled: use observed-law-v1; historical files remain evidence")
    if not isinstance(raw_html, bytes) or not raw_html or len(raw_html) > MAX_HTML_BYTES:
        raise ValueError("Invalid HTML bytes or size")
    timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Capture timestamp requires a timezone")
    date = timestamp.date().isoformat()
    cfg = LEIS_CONFIG[law]
    clean = ""
    if format == CANONICAL_FORMAT:
        document = extract_document(raw_html, law, captured_at)
        clean = "".join(item["text"] for item in document["evidence"]["texts"] if item["kind"] == "content")
        return Capture(law, captured_at, cfg["url"], raw_html, clean, [], {}, document)
    articles, stats = parse_law(clean, law, cfg["versao"], cfg["url"], date, cfg)
    prior = harvest_redacoes_riscadas(raw_html, law, cfg)
    for source, records in stats.get("descartes", {}).items():
        for record in records:
            prior.append({"artigo_base": re.sub(r" \(Parte \d+/\d+\)$", "", record["artigo"]),
                          "dispositivo": "", "texto": record["texto"], "fonte_marcacao": source,
                          "hash": hash_texto(record["texto"]), "ordem": len(prior) + 1})
    sidecar = {"lei": law, "versao": cfg["versao"], "data_extracao": date,
               "url_fonte": cfg["url"], "total": len(prior), "riscadas": prior}
    return Capture(law, captured_at, cfg["url"], raw_html, clean, articles, sidecar)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_capture(capture: Capture, root: Path) -> Path:
    """Write a new immutable capture directory. Existing captures are never overwritten."""
    if capture.canonical is None:
        raise ValueError("Legacy export disabled")
    from .canonical_validation import validate_document
    if not validate_document(capture.canonical)["ok"]:
        raise ValueError("Invalid observed document")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(capture.captured_at.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%S%f%z")
    name = f"{capture.law}-{stamp}-{sha256(capture.raw_html)[:12]}"
    if capture.canonical is not None:
        name += "-" + CANONICAL_FORMAT
    destination = root / name
    if destination.exists():
        raise FileExistsError("Capture already exists")
    if capture.canonical is not None:
        payloads = {"canonical.json": json_bytes(capture.canonical),
                    "clean.txt": capture.clean_text.encode("utf-8"), "source.html": capture.raw_html}
    else:
        base = LEIS_CONFIG[capture.law]["nome_base"] + "_" + capture.articles[0]["data_extracao"]
        payloads = {base + ".json": json_bytes(capture.articles),
                    base + "_riscadas.json": json_bytes(capture.prior_redactions),
                    base + "_clean.txt": capture.clean_text.encode("utf-8"),
                    "source.html": capture.raw_html}
    manifest = {"format_version": 1, "law": capture.law, "captured_at": capture.captured_at,
                "source_url": capture.source_url, "extractor_version": __version__,
                "parser_version": PARSER_VERSION, "raw_sha256": sha256(capture.raw_html),
                "content_hash": sha256(capture.clean_text.encode("utf-8")),
                "temporal_semantics": "observed compilation; not an effective-date determination",
                "files": {n: {"sha256": sha256(b), "bytes": len(b)} for n,b in payloads.items()}}
    if capture.canonical is not None:
        manifest.update(format_version=CAPTURE_VERSION, format=CANONICAL_FORMAT,
                        parser_version=CANONICAL_PARSER_VERSION,
                        recorded_at=datetime.now(timezone.utc).isoformat(),
                        document_revision=capture.canonical["revision"])
    with tempfile.TemporaryDirectory(prefix=".capture-", dir=root) as temp:
        staging = Path(temp) / "capture"
        staging.mkdir()
        for filename, data in payloads.items():
            (staging / filename).write_bytes(data)
        (staging / "manifest.json").write_bytes(json_bytes(manifest))
        staging.rename(destination)
    return destination
