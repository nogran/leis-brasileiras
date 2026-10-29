"""Validate capture artifacts and prepare a versioned local release archive."""
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata
import zipfile

from . import __version__
from .capture import json_bytes, sha256
from .catalog import SIGLAS
from .extraction import LEIS_CONFIG, PARSER_VERSION
from .validation import aplicar_ratchet, load_known_issues, suppress_known_issues, validate_file
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION, CAPTURE_VERSION, CORPUS_VERSION
from .canonical_validation import validate_document

PART = re.compile(r"^(.*?)\s*\(Parte (\d+)/(\d+)\)\s*$")


def multipart_errors(records: list[dict]) -> list[str]:
    errors = []
    groups = defaultdict(list)
    texts = set()
    ids = set()
    labels = set()
    for record in records:
        label = record["artigo"]
        text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", record["texto_limpo"])).strip()
        if record["id"] in ids or label in labels:
            errors.append(f"duplicate identity: {label}")
        ids.add(record["id"])
        labels.add(label)
        if len(text) > 40 and text in texts:
            errors.append(f"duplicate text: {label}")
        texts.add(text)
        match = PART.match(label)
        if match:
            base, index, total = match.group(1), int(match.group(2)), int(match.group(3))
            if record.get("parte_num") != index or record.get("total_partes") != total:
                errors.append(f"part metadata mismatch: {label}")
            groups[base].append((index,total,text))
            if len(text) < 100:
                errors.append(f"tiny part: {label}")
    for base, parts in groups.items():
        parts.sort()
        total = parts[0][1]
        if (base in labels or len({p[1] for p in parts}) != 1
                or [p[0] for p in parts] != list(range(1,total+1))):
            errors.append(f"incomplete or conflicting multipart sequence: {base}")
        for (_,_,left), (_,_,right) in zip(parts,parts[1:]):
            if right[:60] not in left[-600:]:
                errors.append(f"broken overlap: {base}")
            width = min(120,len(left)-12,len(right))
            if width > 40 and any(left[offset:offset+width] == right[:width] for offset in range(1,13)):
                errors.append(f"sliding slice: {base}")
    return errors


def validate_articles(path: Path, strict: bool = False) -> dict:
    if Path(path).stat().st_size > 64*1024*1024:
        raise ValueError("Article file exceeds 64 MiB")
    try:
        result = validate_file(str(path))
    except (TypeError, ValueError, AttributeError, KeyError):
        return {"file": Path(path).name, "chunks": 0, "fails": 1,
                "warnings": 0, "multipart_errors": ["malformed article fields"], "ok": False}
    report, data = result if isinstance(result, tuple) else (result, [])
    aplicar_ratchet(report, True)
    suppress_known_issues(report, load_known_issues(str(Path(__file__).with_name("known_issues.json"))))
    errors = []
    if not report.fails:
        try:
            errors = multipart_errors(data)
        except (KeyError, TypeError, ValueError):
            errors = ["malformed article or multipart metadata"]
    return {"file": Path(path).name, "chunks": len(data), "fails": report.fails,
            "warnings": report.warns, "multipart_errors": errors,
            "ok": not (report.fails or errors or (strict and report.warns))}


def verify_capture(directory: Path, strict: bool = True) -> dict:
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Symlink capture directory refused")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024*1024:
        raise ValueError("Invalid manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    law = manifest["law"]
    if law not in SIGLAS or manifest["source_url"] != LEIS_CONFIG[law]["url"]:
        raise ValueError("Unknown law or source mismatch")
    version = manifest.get("format_version")
    if version != CAPTURE_VERSION:
        raise ValueError("Historical manifest: replay requires its original parser; new generation is disabled")
    canonical = version == CAPTURE_VERSION
    if canonical and manifest.get("format") != CANONICAL_FORMAT:
        raise ValueError("Unknown capture format")
    from datetime import datetime
    timestamp = datetime.fromisoformat(manifest["captured_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Capture timezone missing")
    base = LEIS_CONFIG[law]["nome_base"] + "_" + timestamp.date().isoformat()
    expected = {base+".json",base+"_riscadas.json",base+"_clean.txt","source.html"}
    if canonical:
        expected = {"canonical.json", "clean.txt", "source.html"}
    if set(manifest["files"]) != expected:
        raise ValueError("Unexpected files in capture manifest")
    if {p.name for p in directory.iterdir()} != expected | {"manifest.json"}:
        raise ValueError("Unmanifested capture files")
    for name, info in manifest["files"].items():
        path = directory/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64*1024*1024:
            raise ValueError("Invalid artifact file")
        data = path.read_bytes()
        if len(data) != info["bytes"] or sha256(data) != info["sha256"]:
            raise ValueError("Artifact checksum mismatch")
    if (manifest["raw_sha256"] != manifest["files"]["source.html"]["sha256"]
            or manifest["content_hash"] != manifest["files"]["clean.txt" if canonical else base+"_clean.txt"]["sha256"]):
        raise ValueError("Capture provenance hash mismatch")
    if canonical:
        from .capture import extract_html

        recorded = datetime.fromisoformat(manifest["recorded_at"].replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            raise ValueError("Recording timezone missing")
        document = json.loads((directory / "canonical.json").read_text(encoding="utf-8"))
        if not validate_document(document)["ok"] or document["revision"] != manifest["document_revision"]:
            raise ValueError("Canonical validation failed")
        if manifest["complete"] is not document["reconciliation"]["complete"]:
            raise ValueError("Completeness provenance mismatch")
        if manifest["parser_version"] != document["provenance"]["parser_version"]:
            raise ValueError("Parser provenance mismatch")
        regenerated = extract_html((directory / "source.html").read_bytes(), law,
                                   manifest["captured_at"], format=CANONICAL_FORMAT)
        if (document != regenerated.canonical
                or regenerated.clean_text != (directory / "clean.txt").read_bytes().decode("utf-8")):
            raise ValueError("Canonical capture does not reproduce from source")
        return manifest


def build_release(captures: list[Path], output: Path, version: str, *,
                  selected_laws: list[str] | None = None) -> Path:
    """Prepare only an explicit, complete, validated selection; never upload anything."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",version):
        raise ValueError("Invalid corpus version")
    verified = [(Path(path),verify_capture(Path(path))) for path in captures]
    laws = [manifest["law"] for _,manifest in verified]
    selection = SIGLAS if selected_laws is None else selected_laws
    if (not selection or len(selection) != len(set(selection)) or not set(selection) <= set(SIGLAS)
            or len(laws) != len(set(laws)) or set(laws) != set(selection)):
        raise ValueError("Release requires exactly one validated capture of every catalog law selected")
    formats = {manifest.get("format", "legacy-blocks-v1") for _, manifest in verified}
    if len(formats) != 1:
        raise ValueError("A release cannot mix canonical and legacy captures")
    payloads = {}
    for directory,manifest in sorted(verified,key=lambda item:item[1]["law"]):
        for name in [*manifest["files"],"manifest.json"]:
            payloads[f"{manifest['law']}/{name}"] = (directory/name).read_bytes()
    release = {"corpus_version":version,"format_version":1,"extractor_version":__version__,
               "parser_version":PARSER_VERSION,"laws":sorted(laws),"license_status":"pending owner decision",
               "files":{name:{"sha256":sha256(data),"bytes":len(data)} for name,data in payloads.items()}}
    release.update(format_version=CORPUS_VERSION, format=formats.pop(),
                   complete=all(manifest["complete"] for _, manifest in verified),
                   selection=sorted(selection), coverage="full-catalog" if set(laws) == set(SIGLAS) else "selected-laws")
    if release["format"] == CANONICAL_FORMAT:
        release["parser_version"] = CANONICAL_PARSER_VERSION
    payloads["manifest.json"] = json_bytes(release)
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info,data)
    return output
