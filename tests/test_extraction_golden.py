"""All 15 catalog laws must reproduce frozen reference article payloads."""
import json
import re

import pytest

from leis_brasileiras.catalog import LAWS
from leis_brasileiras.extraction import LEIS_CONFIG, parse_law
from tests.fixture_data import DATA_DIR


@pytest.mark.parametrize("law",LAWS,ids=lambda law:law["sigla"])
def test_parser_reproduces_original_contract(law):
    paths=sorted(p for p in DATA_DIR.glob(law["nome_base"]+"_*.json") if re.search(r'_\d{4}-\d{2}-\d{2}\.json$',p.name))
    assert paths, f"Missing frozen reference for {law['sigla']}"
    path=paths[-1]
    expected=json.loads(path.read_text(encoding="utf-8"))
    clean=path.with_name(path.stem+"_clean.txt").read_text(encoding="utf-8")
    cfg=LEIS_CONFIG[law["sigla"]]
    result,_=parse_law(clean,law["sigla"],cfg["versao"],cfg["url"],expected[0]["data_extracao"],cfg)
    assert result == expected


def test_no_articles_fails():
    cfg=LEIS_CONFIG["CDC"]
    with pytest.raises(RuntimeError):
        parse_law("No legislative structure", "CDC",cfg["versao"],cfg["url"],"2026-07-07",cfg)
