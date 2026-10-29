"""Audit historical editorial interventions; never writes or connects to a database."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "Artigo ausente da versão compilada do Planalto"


def audit(production=None):
    registry_path = ROOT / "src/leis_brasileiras/known_issues.json"
    registry = json.loads(registry_path.read_bytes())
    interventions = []
    for kind, laws in registry["overrides_pos_extracao"].items():
        if kind.startswith("_"):
            continue
        for law, targets in laws.items():
            if law.startswith("_"):
                continue
            for target, assertion in targets.items():
                interventions.append({"law": law, "target": target, "kind": kind,
                    "historical_assertion": assertion, "new_export": "excluded",
                    "reason": "registry assertion is not source-bound evidence; extract original wording instead"})
    tombstones = []
    for path in sorted((ROOT / "tests/fixtures/baseline").glob("*.json.gz")):
        records = json.loads(gzip.decompress(path.read_bytes()))
        if not isinstance(records, list):
            continue
        for record in records:
            if MARKER in record.get("texto_limpo", ""):
                tombstones.append({"law": record["lei"], "article": record["artigo"],
                    "legacy_source_hash": record["hash_artigo"],
                    "historical_text_sha256": hashlib.sha256(record["texto_limpo"].encode()).hexdigest(),
                    "fixture": path.relative_to(ROOT).as_posix(),
                    "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {"kind": "technical-legacy-assertion-audit", "format_version": 1,
        "overrides": interventions, "synthetic_records": tombstones,
        "production": None, "legal_validity_determined": False}
    if production is not None:
        raw = Path(production).read_bytes()
        snapshot = json.loads(raw)
        by_key = {}
        for row in snapshot["inventory"]["documents"]:
            if row["kind"] == "law":
                key = tuple(row["key"])
                if key in by_key:
                    raise ValueError("Ambiguous production inventory key")
                by_key[key] = row
        matches = []
        for item in tombstones:
            live = by_key.get((item["law"], item["article"]))
            matches.append({"law": item["law"], "article": item["article"],
                "present": live is not None,
                "source_hash_matches": live is not None and live["source_hash"] == item["legacy_source_hash"],
                "production_record": live})
        result["production"] = {"environment": snapshot["environment"],
            "observed_at": snapshot["observedAt"], "inventory_sha256": hashlib.sha256(raw).hexdigest(),
            "matches": matches,
            "limitation": "legacy source-hash correspondence, not an independent text byte comparison"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.production_inventory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace audit evidence from a previous run.
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
