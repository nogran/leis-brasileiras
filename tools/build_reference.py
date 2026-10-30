"""Build an explicitly incomplete historical observation archive; no network or database."""
import argparse
import gzip
import json
from pathlib import Path
import re
import zipfile

from leis_brasileiras import __version__
from leis_brasileiras.capture import json_bytes, sha256
from leis_brasileiras.catalog import LAWS
from leis_brasileiras.canonical import extract_document
from leis_brasileiras.canonical_validation import validate_document
from leis_brasileiras.models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION, CORPUS_VERSION

ROOT = Path(__file__).resolve().parents[1]


def reference(law):
    candidates = [p for p in (ROOT / "tests/fixtures/baseline").glob(law["nome_base"] + "_*.json.gz")
                  if re.search(r"_\d{4}-\d{2}-\d{2}\.json\.gz$", p.name)]
    if len(candidates) != 1:
        raise ValueError("Reference requires one historical snapshot")
    path = candidates[0]
    date = path.name.removesuffix(".json.gz")[-10:]
    html = ROOT / "tests/fixtures/html" / (law["nome_base"] + ".htm.gz")
    if html.exists():
        evidence = gzip.decompress(html.read_bytes())
        filename = "source.html"
    else:
        evidence = gzip.decompress(path.with_name(path.name.removesuffix(".json.gz") + "_clean.txt.gz").read_bytes())
        filename = "historical-clean.txt"
    document = extract_document(evidence if filename == "source.html" else evidence.decode("utf-8"),
                                law["sigla"], date, precision="date")
    if not validate_document(document)["ok"]:
        raise ValueError("Observation validation failed")
    return document, filename, evidence


def build(output: Path, version: str, *, format: str = CANONICAL_FORMAT) -> dict:
    if format != CANONICAL_FORMAT:
        raise ValueError("Legacy generation disabled")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Invalid reference version")
    payloads, inventory = {}, []
    for law in LAWS:
        document, filename, raw = reference(law)
        prefix = law["sigla"] + "/"
        payloads[prefix + filename] = raw
        payloads[prefix + "canonical.json"] = json_bytes(document)
        payloads[prefix + "reconciliation.json"] = json_bytes(document["reconciliation"])
        inventory.append({"law": law["sigla"], "observation": document["provenance"]["observation"],
                          "raw_source_available": filename == "source.html",
                          "evidence_file": filename, "evidence_sha256": sha256(raw),
                          "document_revision": document["revision"],
                          "complete": document["reconciliation"]["complete"]})
    manifest = {"format_version": CORPUS_VERSION, "format": format, "corpus_version": version,
                "kind": "historical-observation", "extractor_version": __version__,
                "parser_version": CANONICAL_PARSER_VERSION, "complete": False,
                "laws": inventory, "files": {name: {"bytes": len(raw), "sha256": sha256(raw)}
                                            for name, raw in payloads.items()}}
    payloads["manifest.json"] = json_bytes(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--format", choices=[CANONICAL_FORMAT], default=CANONICAL_FORMAT)
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.version, format=args.format)))
