import csv
import io
import json
import os
import re
import gzip
import tempfile
from pathlib import Path
import pytest
from leis_brasileiras.jurisprudence import extraction as parser
from leis_brasileiras.jurisprudence.extraction import (
    CAMPOS_TESES_ESPERADOS,
    COLUNAS_ESPERADAS,
    LayoutInvalidoError,
    TIPOS_PRECEDENTE,
    URL_STF_SV_INDICE,
    _finalizar_registro,
    chave_natural,
    colapsar_por_chave_natural,
    decodificar_bytes,
    decodificar_csv,
    parse_stf_sv_detalhe,
    parse_stf_sv_lista,
    parse_stf_teses_json,
    parse_stj_sumulas_html,
    parse_temas_csv
)

_TEMP = tempfile.TemporaryDirectory(prefix="juris-fixtures-")
_FIXTURES = _TEMP.name
for item in (Path(__file__).parent / "fixtures/jurisprudence").rglob("*.gz"):
    target = Path(_FIXTURES) / item.relative_to(Path(__file__).parent / "fixtures/jurisprudence").with_suffix("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.decompress(item.read_bytes()))

FIXTURE_TJPE_SUMULAS_DIR = os.path.join(_FIXTURES, "tjpe_sumulas_amostra")
FIXTURE_TJMG_SUMULAS = os.path.join(_FIXTURES, "tjmg_sumulas_amostra.pdf")
FIXTURE_TJPE_INDICE = os.path.join(_FIXTURES, "tjpe_sumulas_indice.html")
FIXTURE_TJMG_INDICE = os.path.join(_FIXTURES, "tjmg_sumulas_indice.html")
FIXTURE_STF_TESES_GOLDEN = os.path.join(_FIXTURES, "stf_teses_amostra_golden.json")
FIXTURE_STF_SV_DIR = os.path.join(_FIXTURES, "stf_sv_amostra")
FIXTURE_STF_SV_GOLDEN = os.path.join(_FIXTURES, "stf_sv_amostra_golden.json")
GOLDEN_EXTRACTED_AT = "2026-07-20"
GOLDEN_EXTRACTED_AT_J02 = "2026-07-21"

FIXTURE_CSV = os.path.join(_FIXTURES, "stj_temas_amostra.csv")
FIXTURE_GOLDEN = os.path.join(_FIXTURES, "stj_temas_amostra_golden.json")
FIXTURE_STJ_SUMULAS = os.path.join(_FIXTURES, "stj_sumulas_amostra.html")
FIXTURE_STJ_SUMULAS_GOLDEN = os.path.join(_FIXTURES, "stj_sumulas_amostra_golden.json")
FIXTURE_STF_TESES_DIR = os.path.join(_FIXTURES, "stf_teses_amostra")

def _fixture_texto() -> str:
    with open(FIXTURE_CSV, "rb") as f:
        raw = f.read()
    # git com core.autocrlf=true pode materializar a fixture com CRLF em checkout
    # Windows; o arquivo REAL do STJ usa LF (golden gerado assim). Normaliza para o
    # golden ser estavel em qualquer plataforma — producao le bytes direto da rede,
    # sem git no caminho.
    raw = raw.replace(b"\r\n", b"\n")
    texto, _ = decodificar_csv(raw)
    return texto

def _registros_fisicos(texto: str) -> list[str]:
    """Conta registros FISICOS do CSV (implementacao independente do csv module):
    um registro so fecha quando a paridade de aspas fecha — newline dentro de campo
    quotado NAO termina o registro."""
    regs, buf = [], ""
    for ln in texto.splitlines(keepends=True):
        buf += ln
        if buf.count('"') % 2 == 0:
            regs.append(buf)
            buf = ""
    assert not buf, "registro fisico nao fechado na fixture"
    return regs

def _csv_sintetico(colunas=COLUNAS_ESPERADAS, linhas=()) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(colunas)
    for linha in linhas:
        w.writerow(linha)
    return out.getvalue()

def _linha(colunas=COLUNAS_ESPERADAS, **valores) -> list[str]:
    base = {"tipoPrecedente": "Tema", "numeroPrecedente": "999", "situacao": "Afetado"}
    base.update(valores)
    return [base.get(c, "") for c in colunas]

class TestGolden:
    def test_golden_csv_para_json(self):
        registros = parse_temas_csv(_fixture_texto(), extracted_at=GOLDEN_EXTRACTED_AT)
        with open(FIXTURE_GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        assert len(registros) == len(golden)
        for reg, esperado in zip(registros, golden):
            assert reg == esperado, f"divergencia no registro {esperado.get('sequencial_precedente')}"

    def test_nenhum_tema_perdido(self):
        # n registros canonicos == n linhas de dados FISICAS da fixture (inclui os
        # sem tese — decisao locked: todo tema entra, filtro por tese e downstream)
        texto = _fixture_texto()
        fisicos = _registros_fisicos(texto)
        registros = parse_temas_csv(texto, extracted_at=GOLDEN_EXTRACTED_AT)
        assert len(registros) == len(fisicos) - 1  # -1 = header

    def test_campo_newline_interno(self):
        # A fixture tem registros com newline DENTRO de campo quotado (texto juridico
        # real). O parser precisa produzir 1 registro integro, nao 2 quebrados.
        registros = parse_temas_csv(_fixture_texto(), extracted_at=GOLDEN_EXTRACTED_AT)
        com_newline = [
            r for r in registros
            if any(isinstance(v, str) and "\n" in v for v in r.values())
        ]
        assert com_newline, "fixture deveria ter >=1 registro com newline interno"
        for r in com_newline:
            assert r["numero"] is not None  # registro integro, nao fatia orfa

    def test_golden_cobre_os_cinco_tipos_de_precedente(self):
        # temas.csv NAO e so tema repetitivo (Tema/Controvérsia/PUIL/IAC/SIRDR) —
        # o golden prova que o tipo canonico e derivado do tipoPrecedente REAL.
        with open(FIXTURE_GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        tipos = {r["tipo"] for r in golden}
        assert tipos == {"tema_repetitivo", "controversia", "puil", "iac", "sirdr"}

class TestLayout:
    def test_layout_coluna_faltando_tese(self):
        colunas = [c for c in COLUNAS_ESPERADAS if c != "teseFirmada"]
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_temas_csv(_csv_sintetico(colunas, [_linha(colunas)]))
        assert "teseFirmada" in str(exc.value)

    def test_layout_coluna_faltando_numero(self):
        colunas = [c for c in COLUNAS_ESPERADAS if c != "numeroPrecedente"]
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_temas_csv(_csv_sintetico(colunas, [_linha(colunas)]))
        assert "numeroPrecedente" in str(exc.value)

    def test_coluna_extra_tolerada(self):
        colunas = list(COLUNAS_ESPERADAS) + ["colunaNovaDoSTJ"]
        registros = parse_temas_csv(_csv_sintetico(colunas, [_linha(colunas)]))
        assert len(registros) == 1
        assert registros[0]["numero"] == "999"

class TestEncoding:
    CONTEUDO = _csv_sintetico(linhas=[_linha(
        questaoSubmetidaAJulgamento="Questão sobre prescrição e decisão judicial")])

    def test_utf8_puro(self):
        texto, enc = decodificar_csv(self.CONTEUDO.encode("utf-8"))
        assert enc == "utf-8"
        assert "Questão sobre prescrição" in texto

    def test_utf8_com_bom(self):
        texto, enc = decodificar_csv(b"\xef\xbb\xbf" + self.CONTEUDO.encode("utf-8"))
        assert enc == "utf-8-sig"
        assert not texto.startswith("﻿")
        assert "Questão sobre prescrição" in texto

    def test_cp1252(self):
        texto, enc = decodificar_csv(self.CONTEUDO.encode("cp1252"))
        assert enc == "cp1252"
        assert "Questão sobre prescrição" in texto

class TestDatas:
    def _um(self, **valores):
        registros = parse_temas_csv(_csv_sintetico(linhas=[_linha(**valores)]))
        return registros[0]

    def test_data_iso_parseavel(self):
        r = self._um(dataPrimeiraAfetacao="2017-02-13", dataJulgamento="2018-06-27")
        assert r["data_primeira_afetacao"] == "2017-02-13"
        assert r["data_julgamento"] == "2018-06-27"
        assert "data_primeira_afetacao_raw" not in r
        assert "data_julgamento_raw" not in r

    def test_data_ddmmyyyy_parseavel(self):
        r = self._um(dataJulgamento="27/06/2018")
        assert r["data_julgamento"] == "2018-06-27"
        assert "data_julgamento_raw" not in r

    def test_data_invalida_vira_null_com_raw(self):
        r = self._um(dataJulgamento="pendente de publicação")
        assert r["data_julgamento"] is None
        assert r["data_julgamento_raw"] == "pendente de publicação"

    def test_data_vazia_vira_null_sem_raw(self):
        r = self._um(dataJulgamento="")
        assert r["data_julgamento"] is None
        assert "data_julgamento_raw" not in r

class TestHasThesis:
    def _um(self, **valores):
        return parse_temas_csv(_csv_sintetico(linhas=[_linha(**valores)]))[0]

    def test_tese_preenchida(self):
        r = self._um(teseFirmada="Tese firmada pela Corte Especial.")
        assert r["has_thesis"] is True
        assert r["tese"] == "Tese firmada pela Corte Especial."

    def test_tese_vazia(self):
        r = self._um(teseFirmada="")
        assert r["has_thesis"] is False
        assert r["tese"] is None

    def test_tese_so_espacos(self):
        r = self._um(teseFirmada="   ")
        assert r["has_thesis"] is False
        assert r["tese"] is None

class TestHashEstavel:
    def test_mesmo_conteudo_mesmo_hash(self):
        texto = _fixture_texto()
        a = parse_temas_csv(texto, extracted_at=GOLDEN_EXTRACTED_AT)
        b = parse_temas_csv(texto, extracted_at=GOLDEN_EXTRACTED_AT)
        assert [r["hash"] for r in a] == [r["hash"] for r in b]

    def test_extracted_at_diferente_nao_muda_hash(self):
        texto = _fixture_texto()
        a = parse_temas_csv(texto, extracted_at="2026-07-20")
        b = parse_temas_csv(texto, extracted_at="2027-01-01")
        assert [r["hash"] for r in a] == [r["hash"] for r in b]
        assert a[0]["extracted_at"] != b[0]["extracted_at"]

    def test_mudar_um_char_da_tese_muda_hash(self):
        base = _linha(teseFirmada="Tese firmada.")
        mudada = _linha(teseFirmada="Tese firmadaX")
        r1 = parse_temas_csv(_csv_sintetico(linhas=[base]))[0]
        r2 = parse_temas_csv(_csv_sintetico(linhas=[mudada]))[0]
        assert r1["hash"] != r2["hash"]

class TestTipoPrecedente:
    def _um(self, **valores):
        return parse_temas_csv(_csv_sintetico(linhas=[_linha(**valores)]))[0]

    def test_mapeamento_dos_tipos_oficiais(self):
        assert TIPOS_PRECEDENTE == {
            "Tema": "tema_repetitivo",
            "Controvérsia": "controversia",
            "IAC": "iac",
            "PUIL": "puil",
            "SIRDR": "sirdr",
        }
        r = self._um(tipoPrecedente="Controvérsia")
        assert r["tipo"] == "controversia"
        assert r["tipo_precedente"] == "Controvérsia"

    def test_tipo_desconhecido_vira_slug_deterministico(self):
        # Fonte pode ampliar o dominio: nunca descarta, nunca inventa "tema_repetitivo"
        r = self._um(tipoPrecedente="Questão de Ordem")
        assert r["tipo"] == "questao_de_ordem"
        assert r["tipo_precedente"] == "Questão de Ordem"

class _RespostaFake:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass

class _SessaoFake:
    def __init__(self, content: bytes):
        self._content = content
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return _RespostaFake(self._content)

def _fixture_bytes(path: str) -> bytes:
    """Bytes da fixture com CRLF normalizado (mesmo racional de _fixture_texto:
    git com core.autocrlf pode materializar CRLF em checkout Windows; producao
    le bytes direto da rede, sem git no caminho)."""
    with open(path, "rb") as f:
        raw = f.read()
    return raw.replace(b"\r\n", b"\n")

def _stj_sumulas_texto() -> str:
    texto, encoding = decodificar_bytes(_fixture_bytes(FIXTURE_STJ_SUMULAS))
    assert encoding == "cp1252"  # encoding REAL do SCON — a fixture preserva
    return texto

def _teses_textos() -> tuple[str, str]:
    com = _fixture_bytes(os.path.join(FIXTURE_STF_TESES_DIR, "com.json")).decode("utf-8")
    sem = _fixture_bytes(os.path.join(FIXTURE_STF_TESES_DIR, "sem.json")).decode("utf-8")
    return com, sem

def _sv_lista_texto() -> str:
    return _fixture_bytes(os.path.join(FIXTURE_STF_SV_DIR, "lista.html")).decode("utf-8")

def _sv_detalhe_texto() -> str:
    return _fixture_bytes(os.path.join(FIXTURE_STF_SV_DIR, "sumula_1185.html")).decode("utf-8")

class TestGoldenStjSumulas:
    def _registros(self):
        return parse_stj_sumulas_html(
            _stj_sumulas_texto(), extracted_at=GOLDEN_EXTRACTED_AT_J02)

    def test_golden_html_para_json(self):
        registros = self._registros()
        with open(FIXTURE_STJ_SUMULAS_GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        assert len(registros) == len(golden)
        for reg, esperado in zip(registros, golden):
            assert reg == esperado, f"divergencia na sumula {esperado['numero']}"

    def test_nenhum_bloco_perdido(self):
        # n registros == n blocos gridSumula fisicos da fixture
        texto = _stj_sumulas_texto()
        assert len(self._registros()) == texto.count('<div class="gridSumula">')

    def test_cancelada_marcada_e_nunca_descartada(self):
        # Sumula 603 (cancelada via span.clsINDE) ENTRA no JSON com situacao correta
        por_numero = {r["numero"]: r for r in self._registros()}
        assert por_numero["603"]["situacao"] == "cancelada"
        assert por_numero["603"]["enunciado"]  # enunciado integro, nao descartado
        assert "CANCELAMENTO da Súmula 603" in por_numero["603"]["enunciado"]
        for numero in ("676", "654", "626", "615"):
            assert por_numero[numero]["situacao"] == "em_vigor"

    def test_entidades_e_acentos_resolvidos(self):
        registros = self._registros()
        serializado = json.dumps(registros, ensure_ascii=False)
        assert "&uacute;" not in serializado  # entidades HTML resolvidas pelo BS4
        assert "�" not in serializado          # sem mojibake do decode cp1252
        por_numero = {r["numero"]: r for r in registros}
        assert por_numero["676"]["ramo"] == "DIREITO PROCESSUAL PENAL - PRISÃO"
        assert "não é mais possível" in por_numero["676"]["enunciado"]

    def test_enunciado_verbatim_sem_ramo_com_parentetico(self):
        # enunciado = verbete SEM o ramo, mas COM o parentetico de julgamento
        por_numero = {r["numero"]: r for r in self._registros()}
        e676 = por_numero["676"]["enunciado"]
        assert not e676.startswith("DIREITO")
        assert "(TERCEIRA SEÇÃO, julgado em 11/12/2024, DJe de 17/12/2024)" in e676

    def test_best_effort_estruturado_vs_texto_puro(self):
        por_numero = {r["numero"]: r for r in self._registros()}
        # 654: parentetico estruturado com <b> -> orgao + datas ISO
        assert por_numero["654"]["orgao_julgador"] == "PRIMEIRA SEÇÃO"
        assert por_numero["654"]["data_julgamento"] == "2022-08-24"
        assert por_numero["654"]["data_publicacao"] == "2022-08-29"
        # 676: parentetico em TEXTO PURO -> best-effort fica None (nunca regex cega)
        assert por_numero["676"]["orgao_julgador"] is None
        assert por_numero["676"]["data_julgamento"] is None
        assert por_numero["676"]["data_publicacao"] is None

class TestLayoutStjSumulas:
    def test_pagina_sem_gridsumula_falha_com_mensagem_util(self):
        # Pagina de challenge sintetica (Cloudflare estendido ao host) = layout invalido
        challenge = "<html><body><h1>Just a moment...</h1></body></html>"
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_stj_sumulas_html(challenge)
        assert "Cloudflare" in str(exc.value)
        assert "PDF" in str(exc.value)  # fallback manual documentado na mensagem

    def test_bloco_sem_numero_sumula_falha(self):
        html = (
            '<html><body><div class="gridSumula">'
            '<div class="blocoVerbete">texto sem numero</div>'
            "</div></body></html>"
        )
        with pytest.raises(LayoutInvalidoError):
            parse_stj_sumulas_html(html)

    def test_bloco_sem_verbete_falha(self):
        html = (
            '<html><body><div class="gridSumula">'
            '<span class="numeroSumula">1</span>'
            "</div></body></html>"
        )
        with pytest.raises(LayoutInvalidoError):
            parse_stj_sumulas_html(html)

    def test_permitir_vazio_so_para_fim_de_paginacao(self):
        # permitir_vazio=True: pagina sem blocos -> [] (fim da paginacao, pagina > 1)
        assert parse_stj_sumulas_html("<html><body></body></html>", permitir_vazio=True) == []

class TestGoldenStfTeses:
    def _registros(self):
        com, sem = _teses_textos()
        return parse_stf_teses_json(com, sem, extracted_at=GOLDEN_EXTRACTED_AT_J02)

    def test_golden_json_para_registros(self):
        registros = self._registros()
        with open(FIXTURE_STF_TESES_GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        assert len(registros) == len(golden)
        for reg, esperado in zip(registros, golden):
            assert reg == esperado, f"divergencia no tema {esperado['numero']}"

    def test_has_thesis_vem_da_lista_nunca_do_texto(self):
        # GOTCHA travado: registros "sem" TEM descricaoTese preenchida (negativa de
        # RG / descricao do tema) — has_thesis e falso MESMO com texto presente.
        registros = self._registros()
        de_com = [r for r in registros if r["lista_origem"] == "com"]
        de_sem = [r for r in registros if r["lista_origem"] == "sem"]
        assert de_com and de_sem
        assert all(r["has_thesis"] is True for r in de_com)
        assert all(r["has_thesis"] is False for r in de_sem)
        assert all(r["tese"] for r in de_sem)  # texto presente, has_thesis False

    def test_datas_ddmmyyyy_viram_iso(self):
        import re
        for r in self._registros():
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["data_andamento"])
            assert "data_andamento_raw" not in r

    def test_tese_verbatim_da_fonte(self):
        com, _ = _teses_textos()
        bruto = json.loads(com)
        registros = self._registros()
        assert registros[0]["tese"] == bruto[0]["descricaoTese"].strip()

class TestLayoutStfTeses:
    PAYLOAD_OK = json.dumps([{c: "x" if c != "dataAndamento" else "01/01/2020"
                              for c in CAMPOS_TESES_ESPERADOS}])

    def test_campo_faltando_descricao_tese_falha(self):
        item = {c: "x" for c in CAMPOS_TESES_ESPERADOS if c != "descricaoTese"}
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_stf_teses_json(json.dumps([item]), self.PAYLOAD_OK)
        assert "descricaoTese" in str(exc.value)

    def test_payload_nao_lista_falha(self):
        with pytest.raises(LayoutInvalidoError):
            parse_stf_teses_json('{"erro": "pagina"}', self.PAYLOAD_OK)

    def test_payload_json_invalido_falha(self):
        with pytest.raises(LayoutInvalidoError):
            parse_stf_teses_json("<html>challenge</html>", self.PAYLOAD_OK)

    def test_campo_extra_tolerado(self):
        item = {c: "x" if c != "dataAndamento" else "01/01/2020"
                for c in CAMPOS_TESES_ESPERADOS}
        item["campoNovoDoSTF"] = "y"
        registros = parse_stf_teses_json(json.dumps([item]), "[]")
        assert len(registros) == 1
        assert registros[0]["lista_origem"] == "com"

class TestLayoutStfSv:
    def test_indice_sem_links_falha(self):
        with pytest.raises(LayoutInvalidoError):
            parse_stf_sv_lista("<html><body>nada aqui</body></html>")

    def test_detalhe_sem_titulo_sv_falha(self):
        html = '<html><body><div class="titulo">Outra coisa</div></body></html>'
        with pytest.raises(LayoutInvalidoError):
            parse_stf_sv_detalhe(html, url_fonte="http://exemplo/x")

    def test_detalhe_sem_parcom_falha(self):
        html = (
            '<html><body><div class="titulo">Súmula Vinculante 1</div>'
            '<div class="titulo">Precedente Representativo</div></body></html>'
        )
        with pytest.raises(LayoutInvalidoError):
            parse_stf_sv_detalhe(html, url_fonte="http://exemplo/x")

def _hash_regs_stj(extracted_at, mutado=False):
    texto = _stj_sumulas_texto()
    if mutado:
        texto = texto.replace("flagrante", "flagranteX", 1)  # 1 char no enunciado da 676
    return parse_stj_sumulas_html(texto, extracted_at=extracted_at)

def _hash_regs_teses(extracted_at, mutado=False):
    com, sem = _teses_textos()
    if mutado:
        com = com.replace("Justiça do Trabalho", "Justiça do TrabalhoX", 1)
    return parse_stf_teses_json(com, sem, extracted_at=extracted_at)

def _hash_regs_sv(extracted_at, mutado=False):
    html = _sv_detalhe_texto()
    if mutado:
        html = html.replace("jurídico perfeito", "jurídico perfeitoX", 1)
    return [parse_stf_sv_detalhe(
        html, url_fonte=f"{URL_STF_SV_INDICE}&sumula=1185",
        extracted_at=extracted_at, sumula_id="1185")]

@pytest.mark.parametrize("gerar", [_hash_regs_stj, _hash_regs_teses, _hash_regs_sv])
class TestHashEstavelNovasFontes:
    def test_mesmo_input_mesmo_hash(self, gerar):
        a = gerar("2026-07-21")
        b = gerar("2026-07-21")
        assert [r["hash"] for r in a] == [r["hash"] for r in b]

    def test_extracted_at_diferente_nao_muda_hash(self, gerar):
        a = gerar("2026-07-21")
        b = gerar("2027-01-01")
        assert [r["hash"] for r in a] == [r["hash"] for r in b]
        assert a[0]["extracted_at"] != b[0]["extracted_at"]

    def test_mudar_um_char_do_texto_muda_hash(self, gerar):
        a = gerar("2026-07-21")
        m = gerar("2026-07-21", mutado=True)
        assert [r["hash"] for r in a] != [r["hash"] for r in m]

GOLDEN_AT = "2026-07-20"

def _tema(numero="75", rg=None, **extra):
    """Registro de tema no shape do extrator, ja finalizado (hash + extracted_at)."""
    from leis_brasileiras.jurisprudence.extraction import _finalizar_registro
    registro = {
        "source": "STJ", "tipo": "controversia", "numero": numero,
        "sequencial_precedente": "2137", "situacao": "Vinculada a Tema",
        "questao_submetida": "Legitimidade passiva do banco X.", "tese": None,
        "has_thesis": False, "numero_repercussao_geral_stf": rg,
        "url_fonte": "https://dadosabertos.web.stj.jus.br/temas.csv",
    }
    registro.update(extra)
    return _finalizar_registro(registro, GOLDEN_AT)

class TestColapsoPorChaveNatural:
    def test_chave_natural_espelha_uq_jdv_current(self):
        assert chave_natural(_tema()) == ("STJ", "controversia", "75")

    def test_tres_linhas_do_mesmo_precedente_viram_um_registro(self):
        # O caso REAL: controversia 75 vinculada aos temas 284/285/587 do STF.
        linhas = [_tema(rg="284"), _tema(rg="285"), _tema(rg="587")]
        saida = colapsar_por_chave_natural(linhas, GOLDEN_AT)
        assert len(saida) == 1
        assert saida[0]["numero_repercussao_geral_stf"] == "284, 285, 587"

    def test_nada_se_perde_no_colapso(self):
        linhas = [_tema(rg="284"), _tema(rg="285")]
        saida = colapsar_por_chave_natural(linhas, GOLDEN_AT)[0]
        for linha in linhas:
            assert linha["numero_repercussao_geral_stf"] in \
                saida["numero_repercussao_geral_stf"]
        for campo in ("questao_submetida", "sequencial_precedente", "situacao"):
            assert saida[campo] == linhas[0][campo]

    def test_hash_do_colapsado_e_recomputado(self):
        # O hash tem de descrever o registro COLAPSADO: herdar o da 1a linha faria o
        # Portao 2 pular ("inalterado") quando um vinculo novo entrasse.
        linhas = [_tema(rg="284"), _tema(rg="285")]
        saida = colapsar_por_chave_natural(linhas, GOLDEN_AT)[0]
        assert saida["hash"] not in {linha["hash"] for linha in linhas}
        assert colapsar_por_chave_natural([_tema(rg="284"), _tema(rg="999")],
                                          GOLDEN_AT)[0]["hash"] != saida["hash"]

    def test_ordem_das_linhas_nao_muda_o_hash(self):
        # Determinismo: a ordem em que a fonte emite os vinculos nao pode virar
        # "conteudo mudou" na proxima extracao.
        a = colapsar_por_chave_natural([_tema(rg="587"), _tema(rg="284")], GOLDEN_AT)[0]
        b = colapsar_por_chave_natural([_tema(rg="284"), _tema(rg="587")], GOLDEN_AT)[0]
        assert a["hash"] == b["hash"]
        assert a["numero_repercussao_geral_stf"] == "284, 587"   # numerica, nao textual

    def test_ordenacao_e_numerica_nao_lexicografica(self):
        saida = colapsar_por_chave_natural(
            [_tema(rg="1011"), _tema(rg="96")], GOLDEN_AT)[0]
        assert saida["numero_repercussao_geral_stf"] == "96, 1011"

    def test_valor_repetido_nao_duplica(self):
        saida = colapsar_por_chave_natural(
            [_tema(rg="284"), _tema(rg="284")], GOLDEN_AT)[0]
        assert saida["numero_repercussao_geral_stf"] == "284"

    # --- CONTROLE NEGATIVO: sem colisao, o colapso e no-op byte a byte ---
    def test_chave_unica_sai_intacta_com_hash_identico(self):
        linhas = [_tema(numero="1", rg="284"), _tema(numero="2", rg="285"),
                  _tema(numero="3", rg=None)]
        antes = [dict(linha) for linha in linhas]
        saida = colapsar_por_chave_natural(linhas, GOLDEN_AT)
        assert len(saida) == 3
        assert saida == antes            # nenhum campo tocado, nenhum hash recomputado

    def test_lote_vazio_nao_explode(self):
        assert colapsar_por_chave_natural([], GOLDEN_AT) == []

    # --- O caso que NAO pode ser colapsado em silencio ---
    def test_divergencia_em_campo_nao_multivalorado_falha_alto(self):
        # Duas TESES diferentes sob a mesma chave nao sao vinculo N:N — sao registros
        # distintos, e funde-los inventaria dado juridico.
        linhas = [_tema(tese="Tese A", has_thesis=True),
                  _tema(tese="Tese B", has_thesis=True)]
        with pytest.raises(LayoutInvalidoError) as exc:
            colapsar_por_chave_natural(linhas, GOLDEN_AT)
        assert "tese" in str(exc.value)
        assert "NADA foi escrito" in str(exc.value)

    def test_mensagem_de_falha_nomeia_a_chave_e_o_campo(self):
        linhas = [_tema(situacao="Vinculada a Tema"), _tema(situacao="Cancelada")]
        with pytest.raises(LayoutInvalidoError) as exc:
            colapsar_por_chave_natural(linhas, GOLDEN_AT)
        assert "('STJ', 'controversia', '75')" in str(exc.value)
        assert "situacao" in str(exc.value)

    def test_hash_divergente_sozinho_nao_e_motivo_de_falha(self):
        # O hash SEMPRE diverge entre linhas de um vinculo N:N (ele e derivado do campo
        # multivalorado). Compara-lo acusaria todo grupo legitimo.
        linhas = [_tema(rg="284"), _tema(rg="285")]
        assert linhas[0]["hash"] != linhas[1]["hash"]
        assert len(colapsar_por_chave_natural(linhas, GOLDEN_AT)) == 1

from leis_brasileiras.jurisprudence.extraction import (
    parse_tjpe_sumulas_pdf, parse_tjmg_sumulas_pdf, numeracao_com_buraco,
    livros_tjpe_do_indice, consolidado_tjmg_do_indice, _validar_corpus_estadual,
    _links_de_pdf,
    MAIOR_TJMG_CONHECIDO, MIN_TJMG_SUMULAS, URL_TJMG_SUMULAS_INDICE, URL_TJPE_SUMULAS_INDICE,
)


def _texto_fixture_tjpe(nome):
    return Path(FIXTURE_TJPE_SUMULAS_DIR, nome + ".txt").read_text(encoding="utf-8")

def _texto_fixture_tjmg():
    return Path(FIXTURE_TJMG_SUMULAS + ".txt").read_text(encoding="utf-8")

def _lista_tjpe():
    """LISTA, nao dict: indexar por numero colapsaria duplicata entre livros e nenhuma
    assercao conseguiria ve-la."""
    registros = []
    for nome in sorted(os.listdir(FIXTURE_TJPE_SUMULAS_DIR)):
        if nome.lower().endswith(".pdf"):
            registros.extend(parse_tjpe_sumulas_pdf(
                _texto_fixture_tjpe(nome), GOLDEN_AT, url_fonte=nome, livro=nome))
    return registros

def _lista_tjmg():
    return parse_tjmg_sumulas_pdf(_texto_fixture_tjmg(), GOLDEN_AT, url_fonte="tjmg")

def _sumulas_tjpe():
    return {int(r["numero"]): r for r in _lista_tjpe()}

def _sumulas_tjmg():
    return {int(r["numero"]): r for r in _lista_tjmg()}

class TestSumulasTJPE:

    def test_amostra_rende_exatamente_os_registros_esperados(self):
        assert [int(r['numero']) for r in _lista_tjpe()] == [110, 111, 145, 93, 1, 2, 6]

    def test_sufixo_do_cabecalho_vira_situacao(self):
        regs = _sumulas_tjpe()
        assert regs[2]['situacao'] == 'revogada'
        assert regs[6]['situacao'] == 'revogada'
        assert regs[1]['situacao'] == 'em_vigor'

    def test_revogada_com_enunciado_continua_embeddavel(self):
        assert _sumulas_tjpe()[2]['has_thesis'] is True
        assert _sumulas_tjpe()[2]['enunciado']

    def test_layout_de_duas_colunas_pega_a_data_do_JULGAMENTO(self):
        regs = _sumulas_tjpe()
        assert regs[2]['data_julgamento'] == '2007-05-03'
        assert regs[2]['data_julgamento_raw'] is None

    def test_campos_canonicos_da_sumula_110(self):
        s110 = _sumulas_tjpe()[110]
        assert s110['source'] == 'TJPE'
        assert s110['tipo'] == 'sumula_tj'
        assert s110['orgao_julgador'] == 'ÓRGÃO ESPECIAL'
        assert s110['data_julgamento'] == '2017-04-24'
        assert s110['enunciado'].startswith('É permitida a capitalização de juros')
        assert s110['hash'] and s110['extracted_at'] == GOLDEN_AT

    @pytest.mark.parametrize('sufixo', ['suspensa', 'revogada parcialmente', 'revogada em parte'])
    def test_sufixo_fora_do_vocabulario_falha_alto(self, sufixo):
        texto = f'Súmula\n999 - {sufixo}\nÓrgão Julgador\nSEÇÃO CÍVEL\nEnunciado\nX.\n'
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_tjpe_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u', livro='l')
        assert 'situacao desconhecido' in str(exc.value)

    @pytest.mark.parametrize('traco', ['-', '–', '—'])
    def test_variacao_de_TRACO_e_a_mesma_situacao_nao_um_registro_perdido(self, traco):
        texto = f'Súmula\n006 {traco} revogada\nÓrgão Julgador\nSEÇÃO CÍVEL\nEnunciado\nX.\n'
        regs = parse_tjpe_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u', livro='l')
        assert [(r['numero'], r['situacao']) for r in regs] == [('6', 'revogada')]

    def test_numero_de_pagina_entre_a_cabeca_e_o_numero_nao_vira_a_sumula(self):
        texto = 'Súmula\n 24 \n003\nÓrgão Julgador\nSEÇÃO CÍVEL\nEnunciado\nTexto da sumula 3.\n'
        regs = parse_tjpe_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u', livro='l')
        assert [r['numero'] for r in regs] == ['3']
        assert regs[0]['enunciado'] == 'Texto da sumula 3.'

    def test_data_de_publicacao_e_de_revogacao_nao_se_perdem(self):
        s2 = _sumulas_tjpe()[2]
        assert s2['situacao'] == 'revogada'
        assert s2['data_publicacao_raw'] and 'DPJ 88' in s2['data_publicacao_raw']
        assert s2['data_revogacao_raw'] == '05/06/2009'
        assert s2['data_julgamento'] == '2007-05-03'

    def test_enunciado_sai_em_linha_unica_como_nas_fontes_J0(self):
        for reg in _lista_tjpe() + _lista_tjmg():
            assert '\n' not in reg['enunciado'], reg['numero']

    def test_hash_ignora_url_e_livro_mas_nao_ignora_conteudo(self):
        base = 'Súmula\n110\nÓrgão Julgador\nÓRGÃO ESPECIAL\nEnunciado\nMesmo conteudo.\n'
        a = parse_tjpe_sumulas_pdf(base, GOLDEN_AT, url_fonte='file://x', livro='l1')[0]
        b = parse_tjpe_sumulas_pdf(base, GOLDEN_AT, url_fonte='https://p/uuid', livro='l2')[0]
        outro = parse_tjpe_sumulas_pdf(base.replace('Mesmo', 'OUTRO'), GOLDEN_AT, url_fonte='file://x', livro='l1')[0]
        assert a['hash'] == b['hash']
        assert a['hash'] != outro['hash']

    def test_enunciado_ausente_falha_alto(self):
        texto = 'Súmula\n7\nÓrgão Julgador\nSEÇÃO CÍVEL\nPrecedentes\nAp 1.\n'
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_tjpe_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u', livro='l')
        assert 'Enunciado' in str(exc.value)

class TestSumulasTJMG:

    def test_amostra_rende_exatamente_os_registros_esperados(self):
        assert sorted(_sumulas_tjmg()) == [1, 49, 50]

    def test_as_tres_situacoes_do_vocabulario(self):
        regs = _sumulas_tjmg()
        assert regs[1]['situacao'] == 'cancelada'
        assert regs[49]['situacao'] == 'alterada'
        assert regs[50]['situacao'] == 'em_vigor'

    def test_enunciado_vem_entre_o_cabecalho_e_o_primeiro_rotulo(self):
        s1 = _sumulas_tjmg()[1]
        assert s1['enunciado'].startswith('É indevida a contribuição previdenciária')
        assert 'Órgão Julgador' not in s1['enunciado']
        assert s1['orgao_julgador'].startswith('Corte Superior')

    def test_ano_de_dois_digitos_vai_para_raw_e_nao_se_perde(self):
        texto = 'ENUNCIADO 58\nTexto do enunciado.\nÓrgão Julgador\nÓrgão Especial.\nData do Julgamento\n27/03/19\n'
        reg = parse_tjmg_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u')[0]
        assert reg['data_julgamento'] is None
        assert reg['data_julgamento_raw'] == '27/03/19'

    def test_linhas_do_sumario_nao_viram_registro(self):
        texto = 'ENUNCIADO 3 - CANCELADO ...........................\nENUNCIADO 4\nTexto real.\nÓrgão Julgador\nCorte.\n'
        regs = parse_tjmg_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u')
        assert [r['numero'] for r in regs] == ['4']

    def test_sufixo_fora_do_vocabulario_falha_alto(self):
        texto = 'ENUNCIADO 7 - SUSPENSO\nTexto.\nÓrgão Julgador\nCorte.\n'
        with pytest.raises(LayoutInvalidoError) as exc:
            parse_tjmg_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u')
        assert 'SUSPENSO' in str(exc.value)

    @pytest.mark.parametrize('grafia,esperado', [('CANCELADO', 'cancelada'), ('Cancelado', 'cancelada'), ('cancelado', 'cancelada')])
    def test_caixa_do_sufixo_nao_decide_se_o_registro_existe(self, grafia, esperado):
        texto = f'ENUNCIADO 1 - {grafia}\nTexto.\nÓrgão Julgador\nCorte.\n'
        regs = parse_tjmg_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u')
        assert [r['situacao'] for r in regs] == [esperado]

    def test_numero_de_pagina_DENTRO_do_enunciado_nao_entra_no_texto(self):
        texto = 'ENUNCIADO 7\nPrimeira parte do enunciado\n66\nsegunda parte.\nÓrgão Julgador\nCorte.\n'
        reg = parse_tjmg_sumulas_pdf(texto, GOLDEN_AT, url_fonte='u')[0]
        assert reg['enunciado'] == 'Primeira parte do enunciado segunda parte.'

    def test_nota_da_sumula_ALTERADA_e_capturada_e_nao_vaza_para_precedentes(self):
        s49 = _sumulas_tjmg()[49]
        assert s49['situacao'] == 'alterada'
        assert s49['nota_situacao'] and 'REDAÇÃO ANTERIOR' in s49['nota_situacao']
        assert 'REDAÇÃO ANTERIOR' not in (s49['precedentes'] or '')
        assert 'cancelado' in (_sumulas_tjmg()[1]['nota_situacao'] or '')

class TestGuardsDoCorpusEstadual:

    def test_numeracao_com_buraco_acusa(self):
        regs = [{'numero': '1'}, {'numero': '2'}, {'numero': '5'}]
        assert numeracao_com_buraco(regs) == [3, 4]

    def test_numeracao_integra_nao_acusa(self):
        regs = [{'numero': '1'}, {'numero': '2'}, {'numero': '3'}]
        assert numeracao_com_buraco(regs) == []

    def test_numero_de_pagina_do_pdf_nunca_vira_conteudo(self):
        campos = ('enunciado', 'orgao_julgador', 'referencia_legislativa', 'precedentes', 'nota_situacao')
        registros = list(_sumulas_tjpe().values()) + list(_sumulas_tjmg().values())
        assert registros
        sujos = []
        for reg in registros:
            for campo in campos:
                valor = reg.get(campo)
                if not valor:
                    continue
                ultima = [ln for ln in valor.splitlines() if ln.strip()][-1].strip()
                if ultima.isdigit():
                    sujos.append((reg['source'], reg['numero'], campo, ultima))
        assert sujos == []

    @pytest.mark.parametrize('perda,acusa', [(slice(0, 89), False), (slice(0, 88), True), (slice(1, 89), True)])
    def test_guard_de_rede_enxerga_perda_nas_BORDAS_da_faixa(self, perda, acusa):
        registros = [{'numero': str(n)} for n in range(1, 90)][perda]
        if acusa:
            with pytest.raises((LayoutInvalidoError, RuntimeError)):
                _validar_corpus_estadual(registros, 'TJMG', MIN_TJMG_SUMULAS, MAIOR_TJMG_CONHECIDO)
        else:
            _validar_corpus_estadual(registros, 'TJMG', MIN_TJMG_SUMULAS, MAIOR_TJMG_CONHECIDO)

    def test_indice_REAL_do_tjmg_resolve_o_consolidado(self):
        with open(FIXTURE_TJMG_INDICE, 'rb') as f:
            html, _ = decodificar_bytes(f.read())
        rotulo, url = consolidado_tjmg_do_indice(html)
        assert 'Todos%20os%20enunciados' in url
        assert url.startswith('https://www.tjmg.jus.br/data/files/')
        assert rotulo

    def test_pdf_a_mais_no_indice_do_tjmg_nao_zera_a_extracao(self):
        with open(FIXTURE_TJMG_INDICE, 'rb') as f:
            html, _ = decodificar_bytes(f.read())
        intruso = html.replace('</body>', '<a href="/x/manual.pdf">Manual do portal</a></body>')
        assert len(_links_de_pdf(intruso, URL_TJMG_SUMULAS_INDICE)) == 2
        _rotulo, url = consolidado_tjmg_do_indice(intruso)
        assert 'Todos%20os%20enunciados' in url

    def test_indice_do_tjmg_sem_o_consolidado_falha_alto(self):
        with pytest.raises(LayoutInvalidoError) as exc:
            consolidado_tjmg_do_indice('<a href="/x/manual.pdf">Manual do portal</a>')
        assert 'casaram o filtro' in str(exc.value)

    def test_indice_REAL_do_tjpe_resolve_os_tres_livros(self):
        with open(FIXTURE_TJPE_INDICE, 'rb') as f:
            html, _ = decodificar_bytes(f.read())
        livros = livros_tjpe_do_indice(html)
        assert len(livros) == 3
        assert len(_links_de_pdf(html, URL_TJPE_SUMULAS_INDICE)) > 3
        assert all((re.search('livro', rotulo, re.I) for rotulo, _ in livros))

    def test_indice_do_tjpe_com_menos_livros_falha_alto(self):
        with pytest.raises(LayoutInvalidoError) as exc:
            livros_tjpe_do_indice('<a href="/a.pdf">Livro Sumulas TJPE - ate 92.pdf</a>')
        assert 'casaram o filtro' in str(exc.value)

    def test_as_duas_fontes_estaduais_estao_no_registry(self):
        from leis_brasileiras.jurisprudence.catalog import SOURCE_IDS
        assert {'tjpe_sumulas', 'tjmg_sumulas'} <= set(SOURCE_IDS)
