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
    # The old snapshots intentionally retain prohibited editorial interventions.
    # Compare unaffected source fields; the new evidence tests reconcile raw HTML.
    previous = {record["artigo"]: record for record in expected}
    assert all("Artigo ausente da versão compilada do Planalto" not in r["texto_limpo"] for r in result)
    for record in result:
        old = previous[record["artigo"]]
        assert record["texto_limpo"] == old["texto_limpo"]
        assert record["hash_artigo"] == old["hash_artigo"]
    missing = set(previous) - {r["artigo"] for r in result}
    assert all("Artigo ausente da versão compilada do Planalto" in previous[key]["texto_limpo"] for key in missing)


def test_no_articles_fails():
    cfg=LEIS_CONFIG["CDC"]
    with pytest.raises(RuntimeError):
        parse_law("No legislative structure", "CDC",cfg["versao"],cfg["url"],"2026-07-07",cfg)
