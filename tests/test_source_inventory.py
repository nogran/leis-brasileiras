import json
from pathlib import Path

from tools.build_inventory import inventory


def test_inventory_is_reproducible_and_counts_records_not_articles():
    actual = inventory()
    stored = json.loads((Path(__file__).parents[1] / "docs/source-inventory.json").read_text(encoding="utf-8"))
    assert actual == stored
    assert sum(row["records"] for row in actual) == 6276
    assert sum(row["multipart_units"] for row in actual) == 23
    assert sum(row["multipart_records"] for row in actual) == 54
    assert sum(row["multipart_articles"] for row in actual) == 21
    li = next(row for row in actual if row["law"] == "LI")
    assert (li["records"], li["article_records"], li["other_records"]) == (92, 91, 1)
