"""Inventory derives evidence diagnostics, never fixed completeness totals."""
import json
from pathlib import Path

import pytest

from tools import build_inventory
from tools.build_inventory import inventory, readme_inventory, replace_readme_inventory, summarize_inventory
from leis_brasileiras.evidence import structured_digest

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def measured():
    return inventory()


def test_inventory_and_both_readmes_reproduce(measured):
    assert json.loads((ROOT / "docs/source-inventory.json").read_text(encoding="utf-8")) == summarize_inventory(measured)
    for name, language in (("README.md", "pt"), ("README.en.md", "en")):
        current = (ROOT / name).read_text(encoding="utf-8")
        assert replace_readme_inventory(current, readme_inventory(measured, language)) == current


def test_source_counts_do_not_hide_missing_evidence_or_divergences(measured):
    assert len(measured) == 15
    by_law = {row["law"]: row for row in measured}
    cf = by_law["CF88"]
    assert cf["articles_by_component"] == {"main": 276, "adct": 148}
    assert cf["source_article_candidates"] == cf["structured_articles"] == 424
    assert not cf["reconciliation"]["missing_identities"]
    assert by_law["L9099"]["source_article_candidates"] is None
    assert by_law["L9099"]["raw_sha256"] is None
    assert all(row["complete"] is False for row in measured)
    assert all(row["blocks_or_parts"] is None for row in measured)


def test_summary_keeps_differences_and_binds_the_full_reconciliation(measured):
    for full, summary in zip(measured, summarize_inventory(measured)):
        report = full["reconciliation"]
        brief = summary["reconciliation"]
        assert not {"source_identities", "structured_identities", "source_occurrences"} & brief.keys()
        assert brief["report_sha256"] == structured_digest({k: v for k, v in report.items() if k != "report_sha256"})
        for key in ("missing_identities", "extra_identities", "unmapped_evidence_ids", "unclassified_units", "discrepancies"):
            assert brief[key] == report[key]
        assert summary["parser_version"] and summary["evidence_file"]
        assert brief["source_occurrence_count"] == (len(report["source_occurrences"]) if report["source_occurrences"] is not None else None)


def test_check_exports_full_report_even_when_summary_is_stale(tmp_path, monkeypatch, measured):
    monkeypatch.setattr(build_inventory, "ROOT", tmp_path)
    monkeypatch.setattr(build_inventory, "inventory", lambda: measured)
    (tmp_path / "docs").mkdir()
    for name in ("README.md", "README.en.md"):
        (tmp_path / name).write_text("<!-- article-inventory:start --><!-- article-inventory:end -->")
    report = tmp_path / "dist/report.json"
    assert build_inventory.main(["--report", str(report)]) == 0
    full = report.read_bytes()
    assert json.loads(full)["laws"] == measured
    assert json.loads(full)["complete"] is False
    assert build_inventory.main(["--check", "--report", str(report)]) == 0
    assert report.read_bytes() == full
    summary = tmp_path / "docs/source-inventory.json"
    summary.write_text("[]\n")
    assert build_inventory.main(["--check", "--report", str(report)]) == 1
    assert summary.read_text() == "[]\n"
    assert report.read_bytes() == full
    with pytest.raises(SystemExit):
        build_inventory.main(["--report", str(summary)])


@pytest.mark.parametrize("text", ["", "<!-- article-inventory:end --><!-- article-inventory:start -->",
    "<!-- article-inventory:start --><!-- article-inventory:start --><!-- article-inventory:end -->"])
def test_readme_markers_must_be_unambiguous(text):
    with pytest.raises(ValueError, match="bounded"):
        replace_readme_inventory(text, "replacement")
