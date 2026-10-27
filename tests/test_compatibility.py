import json

import pytest

from leis_brasileiras.catalog import LAWS
from leis_brasileiras.compatibility import parse_legacy
from leis_brasileiras.extraction import LEIS_CONFIG
from leis_brasileiras.validation import validate_file
from tests.fixture_data import DATA_DIR


@pytest.mark.parametrize("law", LAWS, ids=lambda row: row["sigla"])
def test_explicit_legacy_facade_preserves_frozen_records(law):
    clean = next(DATA_DIR.glob(law["nome_base"] + "_*_clean.txt"))
    payload = clean.with_name(clean.name.replace("_clean.txt", ".json"))
    expected = json.loads(payload.read_text(encoding="utf-8"))
    cfg = LEIS_CONFIG[law["sigla"]]
    actual, _ = parse_legacy(clean.read_text(encoding="utf-8"), law["sigla"], cfg["versao"],
                             cfg["url"], expected[0]["data_extracao"], cfg)
    assert actual == expected


def test_retrieval_diagnostics_are_opt_in():
    path = DATA_DIR / "cdc_2026-07-07.json"
    report, _ = validate_file(str(path))
    assert not any(issue.category == "RAG" for issue in report.issues)
    diagnostic, _ = validate_file(str(path), retrieval_diagnostics=True)
    assert any(issue.category == "RAG" for issue in diagnostic.issues)
