"""Deterministic local archives of verified captures; no remote publication."""
from pathlib import Path
import re
import tempfile
import zipfile

from .capture import verify_capture
from .catalog import SOURCE_IDS
from .models import digest, json_bytes
from .validation import load_json


def build_release(captures: list[Path], output: Path, version: str, *, selected_sources=None,
                  scanner=None, allow_samples=False) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise ValueError("Invalid corpus version")
    selected = set(SOURCE_IDS if selected_sources is None else selected_sources)
    if not selected or selected - set(SOURCE_IDS) or not 1 <= len(captures) <= len(SOURCE_IDS):
        raise ValueError("Invalid explicit source selection")
    payload, seen, index = {}, set(), []
    for folder in captures:
        folder = Path(folder)
        report = verify_capture(folder, scanner=scanner)
        identifier = report["source"]
        if identifier in seen:
            raise ValueError("Multiple revisions of one source are not a single corpus")
        seen.add(identifier)
        if report["coverage"] == "sample" and not allow_samples:
            raise ValueError("Sample captures require explicit sample archive selection")
        capture_manifest = load_json(folder / "capture.json")
        names = ["capture.json", "document.json", *(entry["name"] for entry in capture_manifest["files"])]
        for name in names:
            raw = (folder / name).read_bytes()
            payload[f"{identifier}/{name}"] = raw
        index.append({"source": identifier, "coverage": report["coverage"], "complete": report["complete"],
                      "document_sha256": report["document_sha256"], "observed_at": capture_manifest["observed_at"]})
    if seen != selected:
        raise ValueError("Corpus coverage does not match explicit selection")
    manifest = {"format": "jurisprudence-corpus-v2", "version": version,
                "complete": all(entry["complete"] for entry in index),
                "sources": sorted(index, key=lambda entry: entry["source"]),
                "files": {name: digest(raw) for name, raw in sorted(payload.items())}}
    payload["manifest.json"] = json_bytes(manifest)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Corpus archive already exists")
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, raw in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
        # Hard-link creation is atomic and fails if a concurrent writer created output.
        output.hardlink_to(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output
