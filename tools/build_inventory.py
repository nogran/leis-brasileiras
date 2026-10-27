"""Recompute the public historical inventory exclusively from reviewed package fixtures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

from leis_brasileiras.catalog import LAWS
from leis_brasileiras.compatibility import LEGACY_FORMAT, measure_records

ROOT = Path(__file__).resolve().parents[1]


def inventory() -> list[dict]:
    result = []
    for law in LAWS:
        candidates = [path for path in (ROOT / "tests/fixtures/baseline").glob(law["nome_base"] + "_*.json.gz")
                      if re.search(r"_\d{4}-\d{2}-\d{2}\.json\.gz$", path.name)]
        if len(candidates) != 1:
            raise ValueError("One historical fixture per law required")
        path = candidates[0]
        raw = gzip.decompress(path.read_bytes())
        records = json.loads(raw)
        prior_path = path.with_name(path.name.removesuffix(".json.gz") + "_riscadas.json.gz")
        prior = json.loads(gzip.decompress(prior_path.read_bytes()))
        result.append({"law": law["sigla"], "public_id": law["public_id"], "format": LEGACY_FORMAT,
                       "source_url": law["url"], "reference_snapshot": path.name.removesuffix(".gz"),
                       "reference_date": records[0]["data_extracao"], "observation_precision": "date",
                       "html_fixture": (ROOT / "tests/fixtures/html" / (law["nome_base"] + ".htm.gz")).exists(),
                       "sha256": hashlib.sha256(raw).hexdigest(),
                       **measure_records(records), "prior_redactions": prior["total"]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare without writing")
    args = parser.parse_args()
    path = ROOT / "docs/source-inventory.json"
    measured = inventory()
    if args.check:
        return 0 if json.loads(path.read_text(encoding="utf-8")) == measured else 1
    path.write_text(json.dumps(measured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
