"""Testes para as regras de validacao do validar_leis.py.

Foco: regras novas adicionadas no PL-13 sub-bloco 4 que detectam
hierarquia colapsada, marker leak, livro ausente em lei longa, etc.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validar_leis import (
    validate_hierarquia,
    validate_schema,
    FileReport,
    REQUIRED_FIELDS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def make_chunk(**overrides):
    """Build minimal chunk dict completo (todos os REQUIRED_FIELDS)."""
    base = {
        "id": "test_art_1",
        "lei": "TEST",
        "versao": "Lei Test",
        "versao_consolidada": True,
        "artigo": "Art. 1",
        "livro": "",
        "livro_nome": "",
        "titulo": "",
        "titulo_nome": "",
        "subtitulo": "",
        "subtitulo_nome": "",
        "capitulo": "",
        "capitulo_nome": "",
        "secao": "",
        "secao_nome": "",
        "path_hierarquico": "",
        "texto_limpo": "Texto do artigo de teste com mais de trinta caracteres aqui.",
        "status": "vigente",
        "vetos_parciais": [],
        "alteracoes": [],
        "referencias": {"internas": [], "leis_externas": [], "constituicao": False},
        "hash_artigo": "abc123def456",
        "url_fonte": "http://test",
        "data_extracao": "2026-01-01",
        "parte_num": None,
        "total_partes": None,
    }
    base.update(overrides)
    return base


def make_report(lei="TEST"):
    return FileReport(file="test.json", lei=lei)


def issues_with_rule(report, rule):
    return [i for i in report.issues if i.rule == rule]


# ═══════════════════════════════════════════════════════════════════════════════
# REGRA NOVA 1: path_generico_em_massa
# ═══════════════════════════════════════════════════════════════════════════════

class TestPathGenericoEmMassa:
    """PL-13: detecta hierarquia colapsada — muitos artigos com o mesmo path."""

    def test_fires_when_50_chunks_share_same_path(self):
        chunks = [
            make_chunk(
                id=f"test_art_{i}", artigo=f"Art. {i}",
                capitulo="CAPÍTULO I", capitulo_nome="Disposições Gerais",
                path_hierarquico="CAPÍTULO I — Disposições Gerais",
            )
            for i in range(1, 51)
        ]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "path_generico_em_massa"), \
            f"regra nao disparou. Issues: {[i.rule for i in report.issues]}"
        i = issues_with_rule(report, "path_generico_em_massa")[0]
        assert i.severity == "FAIL"

    def test_does_not_fire_with_diverse_paths(self):
        chunks = [
            make_chunk(
                id=f"test_art_{i}", artigo=f"Art. {i}",
                capitulo=f"CAPÍTULO {i}", capitulo_nome=f"Tema {i}",
                path_hierarquico=f"CAPÍTULO {i} — Tema {i}",
            )
            for i in range(1, 51)
        ]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "path_generico_em_massa")

    def test_does_not_fire_when_path_empty(self):
        """Path vazio nao conta — e tratado por outra regra (path_vazio)."""
        chunks = [make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}", path_hierarquico="") for i in range(1, 51)]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "path_generico_em_massa")


# ═══════════════════════════════════════════════════════════════════════════════
# REGRA NOVA 2: livro_ausente_em_lei_longa
# ═══════════════════════════════════════════════════════════════════════════════

class TestLivroAusenteEmLeiLonga:
    """PL-13: leis estruturadas com Livros (CC, CPC, CLT, CF88) precisam ter livro populado."""

    def test_fires_for_cc_without_livro(self):
        chunks = [make_chunk(lei="CC", id=f"cc_art_{i}", artigo=f"Art. {i}", livro="") for i in range(1, 11)]
        report = make_report(lei="CC")
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "livro_ausente_em_lei_longa"), \
            f"regra nao disparou. Issues: {[i.rule for i in report.issues]}"
        i = issues_with_rule(report, "livro_ausente_em_lei_longa")[0]
        assert i.severity == "FAIL"

    def test_fires_for_cpc_without_livro(self):
        chunks = [make_chunk(lei="CPC", id=f"cpc_art_{i}", artigo=f"Art. {i}", livro="") for i in range(1, 11)]
        report = make_report(lei="CPC")
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "livro_ausente_em_lei_longa")

    def test_does_not_fire_for_cdc(self):
        """CDC nao tem LIVRO — nao deve disparar."""
        chunks = [make_chunk(lei="CDC", id=f"cdc_art_{i}", artigo=f"Art. {i}", livro="") for i in range(1, 11)]
        report = make_report(lei="CDC")
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "livro_ausente_em_lei_longa")

    def test_does_not_fire_when_cc_has_livro(self):
        chunks = [
            make_chunk(lei="CC", id=f"cc_art_{i}", artigo=f"Art. {i}", livro="LIVRO I", livro_nome="Das Pessoas")
            for i in range(1, 11)
        ]
        report = make_report(lei="CC")
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "livro_ausente_em_lei_longa")


# ═══════════════════════════════════════════════════════════════════════════════
# REGRA NOVA 3: marker_no_nome_hierarquia
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarkerNoNomeHierarquia:
    """PL-13: marker de alteracao legislativa em qualquer *_nome e bug certo."""

    def test_fires_capitulo_nome_com_incluido(self):
        chunks = [make_chunk(
            capitulo="CAPÍTULO VII-A",
            capitulo_nome="(Incluído pela Lei nº 13.777, de 2018) (Vigência) DO CONDOMÍNIO EM MULTIPROPRIEDADE",
        )]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "marker_no_nome_hierarquia"), \
            f"regra nao disparou. Issues: {[i.rule for i in report.issues]}"
        i = issues_with_rule(report, "marker_no_nome_hierarquia")[0]
        assert i.severity == "FAIL"

    def test_fires_titulo_nome_com_redacao_dada(self):
        chunks = [make_chunk(titulo="TÍTULO I", titulo_nome="(Redação dada pela Lei nº X) Dos Direitos")]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "marker_no_nome_hierarquia")

    def test_fires_secao_nome_com_vigencia(self):
        chunks = [make_chunk(secao="Seção I", secao_nome="(Vigência) Disposições Gerais")]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "marker_no_nome_hierarquia")

    def test_does_not_fire_for_clean_names(self):
        chunks = [make_chunk(
            capitulo="CAPÍTULO I", capitulo_nome="Da Personalidade",
            titulo="TÍTULO I", titulo_nome="Das Pessoas Naturais",
            secao="Seção I", secao_nome="Disposições Gerais",
        )]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "marker_no_nome_hierarquia")


# ═══════════════════════════════════════════════════════════════════════════════
# REGRA NOVA 4: path_hierarquico_vazio (INFO com skip pra leis sem hierarquia)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPathHierarquicoVazio:
    """PL-13: path vazio gera INFO. CADPOS e LT sao isentas (sem hierarquia interna)."""

    def test_fires_info_when_chunks_have_empty_path(self):
        chunks = [make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}", path_hierarquico="") for i in range(1, 11)]
        report = make_report(lei="CC")
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "path_hierarquico_vazio")

    def test_does_not_fire_for_cadpos(self):
        chunks = [
            make_chunk(lei="CADPOS", id=f"cadpos_art_{i}", artigo=f"Art. {i}", path_hierarquico="")
            for i in range(1, 11)
        ]
        report = make_report(lei="CADPOS")
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "path_hierarquico_vazio")

    def test_does_not_fire_for_lt(self):
        chunks = [
            make_chunk(lei="LT", id=f"lt_art_{i}", artigo=f"Art. {i}", path_hierarquico="")
            for i in range(1, 11)
        ]
        report = make_report(lei="LT")
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "path_hierarquico_vazio")


# ═══════════════════════════════════════════════════════════════════════════════
# REGRA NOVA 5: livro_sem_nome
# ═══════════════════════════════════════════════════════════════════════════════

class TestLivroSemNome:
    """PL-13: simetrico ao titulo_sem_nome existente — livro setado mas livro_nome vazio."""

    def test_fires_when_livro_set_but_nome_empty(self):
        chunks = [make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}", livro="LIVRO I", livro_nome="") for i in range(1, 11)]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "livro_sem_nome")

    def test_does_not_fire_when_both_set(self):
        chunks = [make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}", livro="LIVRO I", livro_nome="Das Pessoas") for i in range(1, 11)]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "livro_sem_nome")

    def test_does_not_fire_when_livro_empty(self):
        chunks = [make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}", livro="", livro_nome="") for i in range(1, 11)]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "livro_sem_nome")


# ═══════════════════════════════════════════════════════════════════════════════
# Schema: REQUIRED_FIELDS deve incluir livro_nome e subtitulo_nome
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequiredFields:
    def test_required_fields_inclui_livro_nome(self):
        assert "livro_nome" in REQUIRED_FIELDS

    def test_required_fields_inclui_subtitulo_nome(self):
        assert "subtitulo_nome" in REQUIRED_FIELDS

    def test_schema_dedupes_missing_fields(self):
        """Quando varios chunks tem o mesmo missing-set, reporta UMA mensagem com count."""
        # 100 chunks todos sem livro_nome
        chunks = []
        for i in range(1, 101):
            c = make_chunk(id=f"test_art_{i}", artigo=f"Art. {i}")
            del c["livro_nome"]
            chunks.append(c)
        report = make_report()
        validate_schema(chunks, report)
        msgs_obrigatorio = issues_with_rule(report, "campo_obrigatorio")
        # Deve ser 1 mensagem (deduplicada) com count, nao 100
        assert len(msgs_obrigatorio) == 1, \
            f"esperava 1 mensagem deduplicada, recebeu {len(msgs_obrigatorio)}"
        assert "100" in msgs_obrigatorio[0].message
        assert "livro_nome" in msgs_obrigatorio[0].message
