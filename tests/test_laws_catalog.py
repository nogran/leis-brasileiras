"""Trava o catálogo único (laws.yml) e a invariante do SSOT.

Objetivo: garantir que TODOS os "pontos de registro" do pipeline (extrair/validar/ingerir/
gerar_perguntas/auditar/golden) DERIVAM do catálogo — nenhum re-hardcoda a sigla. Se um dia
alguém regredir um ponto para um literal que diverge do catálogo, este teste fica VERMELHO
antes do commit. É o antídoto ao bug que a ingestão da Lei 9.099 revelou (a mesma sigla vivia
em ~11 lugares e 4 escaparam).
"""
import auditar_ingestao
import extrair_leis
import gerar_perguntas
import ingerir_leis
import laws
import validar_leis
from tests import test_extraction_golden


def test_catalogo_schema_e_unicidade():
    assert laws.LAWS, "laws.yml vazio"
    siglas = [l["sigla"] for l in laws.LAWS]
    bases = [l["nome_base"] for l in laws.LAWS]
    assert len(siglas) == len(set(siglas)), "sigla duplicada no laws.yml"
    assert len(bases) == len(set(bases)), "nome_base duplicado no laws.yml"
    for l in laws.LAWS:
        for campo in ("sigla", "nome_base", "nome", "numero", "url"):
            assert l.get(campo), f"{l.get('sigla')}: campo obrigatorio ausente: {campo}"
        assert l["url"].startswith("http"), f"{l['sigla']}: url invalida"


def test_extrair_leis_config_deriva_do_catalogo():
    cfg = extrair_leis.LEIS_CONFIG
    assert set(cfg) == set(laws.SIGLAS), "LEIS_CONFIG diverge das siglas do catalogo"
    for l in laws.LAWS:
        c = cfg[l["sigla"]]
        assert c["versao"] == l["numero"], f"{l['sigla']}: versao != numero do catalogo"
        assert c["url"] == l["url"], f"{l['sigla']}: url != catalogo"
        assert c["nome_base"] == l["nome_base"], f"{l['sigla']}: nome_base != catalogo"
        # flags de parse do yaml refletidas no cfg
        for k, v in l.get("parse", {}).items():
            assert c.get(k) == v, f"{l['sigla']}: flag {k} != catalogo"


def test_todos_os_pontos_de_registro_batem_com_o_catalogo():
    # Se qualquer um destes divergir, um "ponto de registro" foi re-hardcodado e saiu do SSOT.
    assert validar_leis.VALID_LEI_SIGLAS == set(laws.SIGLAS)
    assert ingerir_leis.SIGLA_PREFIXO == laws.SIGLA_PREFIXO
    assert gerar_perguntas.SIGLA_PARA_PREFIXO == laws.SIGLA_PREFIXO
    assert set(auditar_ingestao.LEIS) == set(laws.SIGLAS)
    assert test_extraction_golden.LAWS == laws.NOME_BASE_PARA_SIGLA


def test_views_derivadas_coerentes_entre_si():
    assert set(laws.SIGLA_PREFIXO) == set(laws.SIGLAS)
    assert set(laws.SIGLA_PREFIXO.values()) == set(laws.NOME_BASE_PARA_SIGLA)
    # ida-e-volta sigla <-> nome_base
    for sigla, base in laws.SIGLA_PREFIXO.items():
        assert laws.NOME_BASE_PARA_SIGLA[base] == sigla
