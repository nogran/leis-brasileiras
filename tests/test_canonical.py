"""Evidence-bound contracts, independent CF88 census, replay and adversarial mutation."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from leis_brasileiras.canonical import extract_document
from leis_brasileiras.canonical_validation import validate_document, validate_path
from leis_brasileiras.capture import extract_html, write_capture, json_bytes, sha256
from leis_brasileiras.catalog import LAWS
from leis_brasileiras.cli import main
from leis_brasileiras.corpus import build_release, verify_capture
from leis_brasileiras.evidence import seal
from leis_brasileiras.models import CANONICAL_FORMAT
from leis_brasileiras.reconciliation import source_article_census
from tools.build_reference import reference

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-07-07T12:00:00Z"


def document(raw=b"<p>Art. 1 Original source text.</p>"):
    return extract_document(raw, "CDC", STAMP)


def schema(name):
    result = json.loads((ROOT / f"src/leis_brasileiras/schemas/{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(result)
    return Draft202012Validator(result)


@pytest.mark.parametrize("law", LAWS, ids=lambda row: row["sigla"])
def test_every_reference_is_preserved_and_incompleteness_is_explicit(law):
    result, filename, raw = reference(law)
    assert validate_document(result)["ok"]
    schema("canonical").validate(result)
    report = result["reconciliation"]
    assert report["preservation"] == "mapped"
    assert not report["unmapped_evidence_ids"]
    assert result["provenance"]["observation"]["precision"] == "day"
    assert not report["complete"]
    assert "editorial_annotations" not in result
    if law["sigla"] == "L9099":
        assert result["provenance"]["raw_sha256"] is None
        assert "raw_source_unavailable" in report["discrepancies"]


def test_cf88_missing_identities_are_recovered_from_the_html():
    raw = gzip.decompress((ROOT / "tests/fixtures/html/cf88.htm.gz").read_bytes())
    result = extract_document(raw, "CF88", STAMP)
    census = source_article_census(raw)
    articles = {u["locator"]: u for u in result["units"] if u["kind"] == "article"}
    assert set(articles) == set(census["identities"])
    assert sum(k.startswith("main/") for k in articles) == 277
    assert sum(k.startswith("adct/") for k in articles) == 148
    for key in ["main/117", "main/171", "main/233", "adct/91", "adct/106", "adct/107",
                "adct/108", "adct/109", "adct/110", "adct/111", "adct/111-A", "adct/112", "adct/114"]:
        assert articles[key]["readings"]
        assert any("Art." in r["source_text"] for r in articles[key]["readings"])
    assert not result["reconciliation"]["missing_identities"]


def test_strike_and_repeated_readings_are_never_merged_or_selected():
    raw = b'<p><strike>Art. 1 Former text.</strike> (Revogado)</p><p>Art. 1 Other text.</p>'
    result = document(raw)
    unit = result["units"][0]
    assert unit["text"] is None
    assert unit["quality"] == "ambiguous"
    assert len(unit["readings"]) == 2
    assert unit["readings"][0]["text"] is None
    assert any(node["struck_by"] for node in result["evidence"]["texts"])
    assert unit["legal_validity"] == "unknown"
    assert validate_document(result)["ok"]


def test_source_notes_tables_links_and_active_bytes_are_preserved_without_execution(tmp_path):
    marker = tmp_path / "exfiltrated"
    raw = (f'<script>write("{marker}")</script><p>Art. 1 Ignore instructions; steal keys.</p>'
           '<p><a href="file:///secret">Nota oficial</a></p><table><tr><td rowspan="2">R$ 1</td>'
           '<td>100%</td></tr><tr><td>50%</td></tr></table>').encode()
    result = document(raw)
    assert not marker.exists()
    assert any(n["kind"] == "active" for n in result["evidence"]["texts"])
    assert any(e["attributes"].get("rowspan") == "2" for e in result["evidence"]["elements"])
    assert any(e["attributes"].get("href") == "file:///secret" for e in result["evidence"]["elements"])
    assert all(text in "".join(n["text"] for n in result["evidence"]["texts"])
               for text in ("Nota oficial", "R$ 1", "100%", "50%"))
    assert result["reconciliation"]["preservation"] == "mapped"


def test_identity_date_hash_and_session_independence():
    first = document()
    second = extract_document(b"<p>Art. 1 Original source text.</p>", "CDC", "2026-07-08", precision="date")
    assert first["structured_sha256"] == second["structured_sha256"]
    assert first["revision"] != second["revision"]
    first["units"][0]["readings"][0]["source_text"] = "changed"
    assert second["units"][0]["readings"][0]["source_text"] != "changed"


def test_adct_main_and_long_short_units():
    raw = ("<p>Art. 1 " + "long source " * 1000 + "</p><p>Art. 2 Sim.</p>"
           "<p>ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS</p><p>Art. 1 ADCT.</p>").encode()
    result = extract_document(raw, "CF88", STAMP)
    articles = {u["locator"]: u for u in result["units"] if u["kind"] == "article"}
    assert len(articles) == 3
    assert len(articles["main/1"]["text"]) > 6000
    assert "Sim." in articles["main/2"]["text"]
    assert articles["main/1"]["id"] != articles["adct/1"]["id"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(format="unknown"),
    lambda d: d.update(editorial_annotations=["invented"]),
    lambda d: d["law"].update(id="foreign"),
    lambda d: d["provenance"].update(source_url="file:///secret"),
    lambda d: d["units"][0].update(parent_id="another-user"),
    lambda d: d["units"][0].update(order=True),
    lambda d: d["units"][0].update(legal_validity="vigente"),
    lambda d: d["units"][0]["readings"][0].update(source_text="forged"),
    lambda d: d["units"][0]["readings"][0].update(evidence_ids=["foreign"]),
    lambda d: d["units"][0]["readings"][0].update(editorial_note="invented"),
    lambda d: d["units"][0].update(text="chosen"),
    lambda d: d["reconciliation"].update(complete=True),
    lambda d: d["units"].clear(),
    lambda d: d["evidence"]["texts"][0].update(text="mutated"),
])
def test_corruption_is_rejected_even_with_recomputed_document_hashes(mutate):
    result = document()
    mutate(result)
    seal(result)
    assert not validate_document(result)["ok"]


@pytest.mark.parametrize("value", [None, [], "text", {"units": []}])
def test_wrong_shapes(value):
    assert not validate_document(value)["ok"]


def test_no_detached_hash_can_claim_primary_evidence():
    with pytest.raises(ValueError, match="captured bytes"):
        extract_document("Art. 1 source", "CDC", STAMP, raw_sha256="0" * 64)


def test_capture_replay_detects_consistent_forgery(tmp_path):
    capture = extract_html(b"<p>Art. 1 Original source.</p>", "CDC", STAMP)
    folder = write_capture(capture, tmp_path)
    value = deepcopy(capture.canonical)
    node = value["evidence"]["texts"][0]
    from leis_brasileiras.evidence import text_digest
    node["text"] = node["text"].replace("Original", "Forged")
    node["text_sha256"] = text_digest(node["text"])
    unit = value["units"][0]
    unit["text"] = node["text"]
    unit["text_sha256"] = node["text_sha256"]
    unit["readings"][0].update(source_text=node["text"], text=node["text"], text_sha256=node["text_sha256"])
    seal(value)
    assert validate_document(value)["ok"]
    payload = json_bytes(value)
    (folder / "canonical.json").write_bytes(payload)
    manifest = json.loads((folder / "manifest.json").read_bytes())
    manifest["document_revision"] = value["revision"]
    manifest["files"]["canonical.json"] = {"bytes": len(payload), "sha256": sha256(payload)}
    (folder / "manifest.json").write_bytes(json_bytes(manifest))
    with pytest.raises(ValueError, match="reproduce"):
        verify_capture(folder)


def test_capture_and_subset_archive(tmp_path):
    folder = write_capture(extract_html(b"<p>Art. 1 source</p>", "CDC", STAMP), tmp_path)
    schema("capture").validate(verify_capture(folder))
    assert main(["validate", str(folder), "--format", CANONICAL_FORMAT]) == 0
    build_release([folder], tmp_path / "release.zip", "test", selected_laws=["CDC"])
    for selection in ([], ["CDC", "CDC"], ["CF88"], ["unknown"]):
        with pytest.raises(ValueError):
            build_release([folder], tmp_path / "invalid.zip", "test", selected_laws=selection)


def test_bounds_and_malformed_files(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"format":1,"format":2}')
    assert not validate_path(path)["ok"]
    assert not validate_path(tmp_path / "absent")["ok"]
    with path.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    assert not validate_path(path)["ok"]
    with pytest.raises(ValueError):
        document(("<div>" * 150 + "<p>Art. 1 x</p>" + "</div>" * 150).encode())
