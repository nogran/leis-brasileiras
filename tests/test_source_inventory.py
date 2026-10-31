"""Inventory derives evidence diagnostics, never fixed completeness totals."""
import json
from pathlib import Path

import pytest

from tools import build_inventory
from tools import check_article_text
from tools.build_inventory import (article_text_sha256, inventory, readme_inventory,
                                   replace_readme_inventory, summarize_inventory, unit_text_manifest)
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
    cp = by_law["CP"]
    assert cp["source_article_candidates"] == cp["structured_articles"] == 432
    assert cp["observed_occurrences"] == len(cp["reconciliation"]["source_occurrences"]) == 434
    assert not cp["reconciliation"]["missing_identities"]
    assert not cp["reconciliation"]["extra_identities"]
    assert "independent_article_census_mismatch" not in cp["reconciliation"]["discrepancies"]
    assert "structural_boundary_review_required" in cp["reconciliation"]["discrepancies"]
    l9099 = by_law["L9099"]
    assert len(l9099["article_text_sha256"]) == 64
    assert l9099["evidence_basis"] == "source-html"
    assert l9099["evidence_file"] == "source.html"
    assert l9099["observation"]["value"] == "2026-10-30"
    assert l9099["source_article_candidates"] == l9099["structured_articles"] == 99
    assert l9099["raw_sha256"]
    assert not l9099["reconciliation"]["missing_identities"]
    assert "raw_source_unavailable" not in l9099["reconciliation"]["discrepancies"]
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


def test_unit_text_manifest_keeps_every_reading_hash():
    document = {"units": [
        {"locator": "main/23", "kind": "article", "text": None, "readings": [
            {"text_sha256": "aaa", "text": "former"}, {"text_sha256": "bbb", "text": "later"}]},
        {"locator": "main/heading-1", "kind": "heading", "text": "CAPÍTULO I", "readings": [
            {"text_sha256": "ccc", "text": "CAPÍTULO I"}]},
    ]}
    manifest = [
        {"locator": "main/23", "kind": "article", "readings": ["aaa", "bbb"]},
        {"locator": "main/heading-1", "kind": "heading", "readings": ["ccc"]},
    ]
    assert unit_text_manifest(document) == manifest
    assert article_text_sha256(document) == structured_digest(manifest)


def test_check_article_text_reports_a_reading_hash_change(tmp_path, monkeypatch, capsys):
    document = {"units": [{"locator": "main/1", "kind": "article", "readings": [{"text_sha256": "abc"}]}]}
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "source-inventory.json").write_text(json.dumps([
        {"law": "L9099", "article_text_sha256": article_text_sha256(document)}
    ]), encoding="utf-8")
    monkeypatch.setattr(check_article_text, "ROOT", tmp_path)
    monkeypatch.setattr(check_article_text, "reference", lambda law: (document, "source.html", b""))
    assert check_article_text.main(["L9099"]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] is False
    changed = {"units": [{"locator": "main/1", "kind": "article", "readings": [{"text_sha256": "zzz"}]}]}
    monkeypatch.setattr(check_article_text, "reference", lambda law: (changed, "source.html", b""))
    assert check_article_text.main(["L9099"]) == 1
    assert json.loads(capsys.readouterr().out)["changed"] is True
    assert check_article_text.main([]) == 2
    assert check_article_text.main(["NOT_A_LAW"]) == 2


@pytest.mark.parametrize("text", ["", "<!-- article-inventory:end --><!-- article-inventory:start -->",
    "<!-- article-inventory:start --><!-- article-inventory:start --><!-- article-inventory:end -->"])
def test_readme_markers_must_be_unambiguous(text):
    with pytest.raises(ValueError, match="bounded"):
        replace_readme_inventory(text, "replacement")
