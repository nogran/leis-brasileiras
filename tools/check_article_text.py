"""One law: article text changed relative to the versioned inventory, or not."""
import json
import sys
from pathlib import Path

from leis_brasileiras.catalog import by_sigla
from tools.build_inventory import article_text_sha256
from tools.build_reference import reference

ROOT = Path(__file__).resolve().parents[1]


def check(sigla):
    law = by_sigla(sigla)
    if law is None:
        raise ValueError("Unknown law")
    document, _, _ = reference(law)
    fresh = article_text_sha256(document)
    rows = json.loads((ROOT / "docs/source-inventory.json").read_text(encoding="utf-8"))
    stored = next((row.get("article_text_sha256") for row in rows if row["law"] == sigla), None)
    return {"law": sigla, "changed": fresh != stored, "article_text_sha256": fresh}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        return 2
    try:
        result = check(argv[0])
    except ValueError:
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
