"""Audit conclusions must distinguish version correspondence from absent evidence."""
import json

from tools.audit_legacy_assertions import audit


def test_legacy_audit_is_explicit_about_every_override_and_no_database():
    result = audit()
    assert len(result["synthetic_records"]) == 15
    assert len(result["overrides"]) == 8
    assert {row["new_export"] for row in result["overrides"]} == {"excluded"}
    assert result["production"] is None


def test_readonly_snapshot_comparison_distinguishes_missing_and_changed_versions(tmp_path):
    historical = audit()["synthetic_records"]
    matching, changed = historical[:2]
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"environment": "TEST", "observedAt": "2026-10-29",
        "inventory": {"documents": [
            {"kind": "law", "key": [matching["law"], matching["article"]],
             "source_hash": matching["legacy_source_hash"]},
            {"kind": "law", "key": [changed["law"], changed["article"]], "source_hash": "different"}]}}))
    matches = audit(path)["production"]["matches"]
    assert matches[0]["present"] and matches[0]["source_hash_matches"]
    assert matches[1]["present"] and not matches[1]["source_hash_matches"]
    assert not matches[2]["present"] and not matches[2]["source_hash_matches"]
