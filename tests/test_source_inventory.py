"""Inventory derives evidence diagnostics, never fixed completeness totals."""
import json
from pathlib import Path

import pytest

from tools.build_inventory import inventory, readme_inventory, replace_readme_inventory

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def measured():
    return inventory()


def test_inventory_and_both_readmes_reproduce(measured):
    assert json.loads((ROOT / "docs/source-inventory.json").read_text(encoding="utf-8")) == measured
    for name, language in (("README.md", "pt"), ("README.en.md", "en")):
        current = (ROOT / name).read_text(encoding="utf-8")
        assert replace_readme_inventory(current, readme_inventory(measured, language)) == current


def test_source_counts_do_not_hide_missing_evidence_or_divergences(measured):
    assert len(measured) == 15
    by_law = {row["law"]: row for row in measured}
    cf = by_law["CF88"]
    assert cf["articles_by_component"] == {"main": 277, "adct": 148}
    assert cf["source_article_candidates"] == cf["structured_articles"] == 425
    assert not cf["reconciliation"]["missing_identities"]
    assert by_law["L9099"]["source_article_candidates"] is None
    assert by_law["L9099"]["raw_sha256"] is None
    assert all(row["complete"] is False for row in measured)
    assert all(row["blocks_or_parts"] is None for row in measured)


@pytest.mark.parametrize("text", ["", "<!-- article-inventory:end --><!-- article-inventory:start -->",
    "<!-- article-inventory:start --><!-- article-inventory:start --><!-- article-inventory:end -->"])
def test_readme_markers_must_be_unambiguous(text):
    with pytest.raises(ValueError, match="bounded"):
        replace_readme_inventory(text, "replacement")
