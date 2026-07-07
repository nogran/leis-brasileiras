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
    validate_artigos,
    validate_conteudo,
    validate_metadata,
    validate_rag,
    validate_cross_file,
    FileReport,
    REQUIRED_FIELDS,
    RAG_MAX_CHUNK_CHARS,
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

    def test_fires_when_60_chunks_share_same_path(self):
        chunks = [
            make_chunk(
                id=f"test_art_{i}", artigo=f"Art. {i}",
                capitulo="CAPÍTULO I", capitulo_nome="Disposições Gerais",
                path_hierarquico="CAPÍTULO I — Disposições Gerais",
            )
            for i in range(1, 61)
        ]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert issues_with_rule(report, "path_generico_em_massa"), \
            f"regra nao disparou. Issues: {[i.rule for i in report.issues]}"
        i = issues_with_rule(report, "path_generico_em_massa")[0]
        assert i.severity == "FAIL"

    def test_does_not_fire_with_45_chunks(self):
        """45 chunks = subsecoes legitimas profundas (CPC tem isso). Nao deve disparar."""
        chunks = [
            make_chunk(
                id=f"test_art_{i}", artigo=f"Art. {i}",
                path_hierarquico="LIVRO II > TÍTULO II > CAPÍTULO IV > Seção III — Da Penhora",
            )
            for i in range(1, 46)
        ]
        report = make_report()
        validate_hierarquia(chunks, report)
        assert not issues_with_rule(report, "path_generico_em_massa")

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


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEUDO — texto, encoding, HTML, label×texto (validate_conteudo)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateConteudo:
    def test_texto_vazio_fail(self):
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="   ")], r)
        assert issues_with_rule(r, "texto_vazio")

    def test_null_bytes_fail(self):
        # Regressao LMP: UTF-16 decodificado errado deixa \x00 no texto
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="Art. 1\x00 texto\x00")], r)
        assert issues_with_rule(r, "null_bytes")

    def test_caractere_substituicao_fffd_fail(self):
        # Regressao LMP Art. 46: byte truncado/invalido vira U+FFFD
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="texto do artigo " + chr(0xFFFD))], r)
        assert issues_with_rule(r, "caractere_substituicao")

    def test_mojibake_fail(self):
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="DisposiÃ§Ã£o do artigo")], r)
        assert issues_with_rule(r, "encoding_quebrado")

    def test_html_residual_fail(self):
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="Texto com <p>tag solta</p> aqui")], r)
        assert issues_with_rule(r, "html_residual")

    def test_entidade_html_warn(self):
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="Texto com &nbsp; espaco rigido")], r)
        assert issues_with_rule(r, "entidade_html")

    def test_encoding_silencioso_fail(self):
        # Vigente, >300 chars, SEM diacriticos PT -> provavel encoding errado
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="palavra sem acento " * 20)], r)
        assert issues_with_rule(r, "encoding_silencioso")

    def test_label_texto_mismatch_fail(self):
        r = make_report()
        validate_conteudo([make_chunk(artigo="Art. 5", texto_limpo="Art. 7 conteudo divergente")], r)
        assert issues_with_rule(r, "artigo_texto_mismatch")

    def test_texto_valido_sem_fail(self):
        r = make_report()
        validate_conteudo([make_chunk(texto_limpo="Art. 1 São direitos do consumidor a proteção efetiva.")], r)
        assert r.fails == 0


# ═══════════════════════════════════════════════════════════════════════════════
# METADATA — status, vetos, alteracoes, referencias, hash (validate_metadata)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateMetadata:
    def test_alteracao_malformada_fail(self):
        r = make_report()
        validate_metadata([make_chunk(alteracoes=[{"tipo": "redacao"}])], r)  # falta "norma"
        assert issues_with_rule(r, "alteracao_invalida")

    def test_referencia_campo_faltante_fail(self):
        r = make_report()
        validate_metadata([make_chunk(referencias={"internas": [], "leis_externas": []})], r)  # falta constituicao
        assert issues_with_rule(r, "ref_campo_faltante")

    def test_referencia_tipo_errado_fail(self):
        r = make_report()
        validate_metadata([make_chunk(
            referencias={"internas": "nao-e-lista", "leis_externas": [], "constituicao": False})], r)
        assert issues_with_rule(r, "ref_tipo_internas")

    def test_hash_invalido_fail(self):
        r = make_report()
        validate_metadata([make_chunk(hash_artigo="abc")], r)  # < 8 chars
        assert issues_with_rule(r, "hash_invalido")

    def test_url_invalida_warn(self):
        r = make_report()
        validate_metadata([make_chunk(url_fonte="nao-e-url")], r)
        assert issues_with_rule(r, "url_invalida")

    def test_veto_nao_detectado_warn(self):
        r = make_report()
        validate_metadata([make_chunk(texto_limpo="Este dispositivo (Vetado).", vetos_parciais=[])], r)
        assert issues_with_rule(r, "veto_nao_detectado")

    def test_status_divergente_entre_partes_warn(self):
        r = make_report()
        chunks = [
            make_chunk(artigo="Art. 5 (Parte 1/2)", status="vigente"),
            make_chunk(artigo="Art. 5 (Parte 2/2)", status="revogado"),
        ]
        validate_metadata(chunks, r)
        assert issues_with_rule(r, "status_divergente_partes")

    def test_metadata_valido_sem_fail(self):
        r = make_report()
        validate_metadata([make_chunk()], r)
        assert r.fails == 0


# ═══════════════════════════════════════════════════════════════════════════════
# RAG — tamanho de chunk e vigencia (validate_rag)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateRag:
    def test_chunk_grande_warn(self):
        r = make_report()
        r.total_chunks = 1
        validate_rag([make_chunk(texto_limpo="a" * (RAG_MAX_CHUNK_CHARS + 50))], r)
        assert issues_with_rule(r, "chunk_grande")

    def test_baixa_vigencia_warn(self):
        r = make_report()
        r.total_chunks, r.vigentes = 10, 1   # 10% vigentes -> abaixo de 30%
        validate_rag([make_chunk()], r)
        assert issues_with_rule(r, "baixa_vigencia")

    def test_token_estimate_sempre_info(self):
        r = make_report()
        r.total_chunks = 1
        validate_rag([make_chunk()], r)
        assert issues_with_rule(r, "token_estimate")

    def test_chunk_normal_sem_warn_de_tamanho(self):
        r = make_report()
        r.total_chunks, r.vigentes = 1, 1
        validate_rag([make_chunk(texto_limpo="Texto de tamanho normal para retrieval.")], r)
        assert not issues_with_rule(r, "chunk_grande")


# ═══════════════════════════════════════════════════════════════════════════════
# ARTIGO — ids, hashes, sufixos, sequencia, partes (validate_artigos)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateArtigos:
    def test_id_duplicado_fail(self):
        r = make_report()
        chunks = [make_chunk(id="test_art_1", artigo="Art. 1", hash_artigo="h1"),
                  make_chunk(id="test_art_1", artigo="Art. 2", hash_artigo="h2")]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "id_duplicado")

    def test_hash_duplicado_warn(self):
        r = make_report()
        chunks = [make_chunk(id="test_art_1", artigo="Art. 1", hash_artigo="mesmohash"),
                  make_chunk(id="test_art_2", artigo="Art. 2", hash_artigo="mesmohash")]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "hash_duplicado")

    def test_grau_como_sufixo_O_fail(self):
        # "Art. 5° O ..." nao pode virar sufixo -O
        r = make_report()
        chunks = [make_chunk(artigo="Art. 5-O", texto_limpo="Art. 5° O presente artigo dispoe sobre X")]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "grau_como_sufixo_O")

    def test_sufixo_espacado_fail(self):
        # "Art. 142 - O empregador" nao e sufixo -O (CLT)
        r = make_report()
        chunks = [make_chunk(artigo="Art. 142-O", texto_limpo="Art. 142 - O empregador e obrigado a")]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "sufixo_espacado")

    def test_artigos_faltantes_info(self):
        r = make_report()
        chunks = [make_chunk(id=f"test_art_{n}", artigo=f"Art. {n}", hash_artigo=f"h{n}")
                  for n in (1, 2, 5)]  # faltam 3 e 4
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "artigos_faltantes")

    def test_partes_descontinuas_warn(self):
        r = make_report()
        chunks = [
            make_chunk(id="test_art_1a", artigo="Art. 1 (Parte 1/2)", hash_artigo="h1", parte_num=1),
            make_chunk(id="test_art_1b", artigo="Art. 1 (Parte 2/2)", hash_artigo="h2", parte_num=3),  # deveria ser 2
        ]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "partes_descontinuas")

    def test_id_sem_sigla_warn(self):
        r = make_report(lei="CDC")
        chunks = [make_chunk(lei="CDC", id="errado_1", artigo="Art. 1")]
        validate_artigos(chunks, r)
        assert issues_with_rule(r, "id_sem_sigla")

    def test_artigos_validos_sem_fail(self):
        r = make_report()
        chunks = [make_chunk(id=f"test_art_{n}", artigo=f"Art. {n}", hash_artigo=f"h{n}")
                  for n in (1, 2, 3)]
        validate_artigos(chunks, r)
        assert r.fails == 0


class TestValidateCrossFile:
    def test_id_global_duplicado_entre_arquivos(self):
        all_data = {"f1": [make_chunk(id="dup", lei="CDC")],
                    "f2": [make_chunk(id="dup", lei="CP")]}
        rep = validate_cross_file([], all_data)
        assert issues_with_rule(rep, "id_global_duplicado")

    def test_mesma_lei_em_varios_arquivos(self):
        all_data = {"f1": [make_chunk(id="a", lei="CDC")],
                    "f2": [make_chunk(id="b", lei="CDC")]}
        rep = validate_cross_file([], all_data)
        assert issues_with_rule(rep, "lei_duplicada_files")

    def test_sem_problemas(self):
        all_data = {"f1": [make_chunk(id="a", lei="CDC")],
                    "f2": [make_chunk(id="b", lei="CP")]}
        assert validate_cross_file([], all_data).fails == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ruido_residual — M1-aware (dispositivos órfãos preservados não são vazamento)
# ═══════════════════════════════════════════════════════════════════════════════

from validar_leis import _e_linha_orfa_m1


class TestERotuloOrfaoM1:
    def test_rotulo_mais_so_anotacao_e_orfao(self):
        assert _e_linha_orfa_m1("a) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)")
        assert _e_linha_orfa_m1("I - (revogado); (Redação dada pela Lei nº 13.874, de 2019)")
        assert _e_linha_orfa_m1("Parágrafo único. (Revogado). (Redação dada pela Lei nº 13.874, de 2019)")

    def test_dispositivo_com_texto_real_nao_e_orfao(self):
        assert not _e_linha_orfa_m1("II - a educação e divulgação (Redação dada pela Lei nº 12.741, de 2012)")
        assert not _e_linha_orfa_m1("Art. 7º São direitos dos trabalhadores urbanos e rurais.")

    def test_linha_sem_rotulo_nao_e_orfao(self):
        assert not _e_linha_orfa_m1("(Redação dada pela Lei nº 12.741, de 2012)")


class TestRuidoResidualM1Aware:
    """ruido_residual NÃO deve disparar quando o marcador está só numa linha órfã M1
    (rótulo + anotação preservada de propósito), mas DEVE disparar em texto substantivo."""

    def test_nao_dispara_em_dispositivo_orfao_preservado(self):
        chunk = make_chunk(
            artigo="Art. 7",
            texto_limpo=(
                "Art. 7º São direitos dos trabalhadores urbanos e rurais, além de outros.\n"
                "XXIX - ação, quanto aos créditos resultantes das relações de trabalho.\n"
                "a) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)\n"
                "b) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)"
            ),
        )
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "ruido_residual"), (
            "M1 (rótulo órfão + anotação literal) não é vazamento de ruído"
        )

    def test_dispara_em_texto_substantivo_com_marcador(self):
        """Regressão: marcador vazado em texto real (não-órfão) AINDA deve disparar."""
        chunk = make_chunk(
            artigo="Art. 99",
            texto_limpo=(
                "Art. 99. O fornecedor deve prestar informação adequada e clara "
                "(Redação dada pela Lei nº 12.741, de 2012) sobre os produtos."
            ),
        )
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert issues_with_rule(rep, "ruido_residual"), (
            "marcador em texto substantivo continua sendo vazamento (não pode ser suprimido)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# standalone_e_partes_coexistem — captura duplicada (caso real LC123 Art. 18)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStandalonePartesCoexistem:
    def test_dispara_quando_base_e_partes_coexistem(self):
        """Caso real LC123 Art. 18: 'Art. 18' standalone E 'Art. 18 (Parte N/6)'
        no mesmo JSON = captura duplicada (Planalto repete o artigo no HTML)."""
        chunks = [
            make_chunk(id="lc123_art_18", artigo="Art. 18",
                       texto_limpo="Art. 18. O valor devido mensalmente pela microempresa."),
            make_chunk(id="lc123_art_18_p1", artigo="Art. 18 (Parte 1/2)", parte_num=1,
                       total_partes=2, texto_limpo="Art. 18. Conteudo completo parte um."),
            make_chunk(id="lc123_art_18_p2", artigo="Art. 18 (Parte 2/2)", parte_num=2,
                       total_partes=2, texto_limpo="Continuacao do conteudo parte dois."),
        ]
        rep = make_report()
        validate_artigos(chunks, rep)
        assert issues_with_rule(rep, "standalone_e_partes_coexistem")

    def test_nao_dispara_so_partes(self):
        """Multi-parte normal (só partes, sem standalone) é legítimo — 24 artigos na base."""
        chunks = [
            make_chunk(id="cc_art_5_p1", artigo="Art. 5 (Parte 1/2)", parte_num=1,
                       total_partes=2, texto_limpo="Art. 5. Primeira parte do texto."),
            make_chunk(id="cc_art_5_p2", artigo="Art. 5 (Parte 2/2)", parte_num=2,
                       total_partes=2, texto_limpo="Segunda parte do texto."),
        ]
        rep = make_report()
        validate_artigos(chunks, rep)
        assert not issues_with_rule(rep, "standalone_e_partes_coexistem")

    def test_nao_dispara_so_standalone(self):
        chunks = [make_chunk(artigo="Art. 18",
                             texto_limpo="Art. 18. Texto normal de artigo unico.")]
        rep = make_report()
        validate_artigos(chunks, rep)
        assert not issues_with_rule(rep, "standalone_e_partes_coexistem")


# ═══════════════════════════════════════════════════════════════════════════════
# texto_quebrado_letra_a_letra — kerning do Planalto (caso real LC123, 28 chunks)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTextoQuebradoLetraALetra:
    def test_dispara_no_texto_corrompido_real(self):
        """Amostra REAL da LC123 Art. 18 (Parte 1/6): espaços intra-palavra."""
        corrompido = (
            "Art. 18. O v alor d e vido m ensa l mente p e la micro e m p r esa ou "
            "empresa de pequ e no porte optante p e lo Simples Na c ional s e r a "
            "d e t e rminado m ediante apli c a c a o das ali q uotas."
        )
        chunk = make_chunk(artigo="Art. 18 (Parte 1/6)", parte_num=1, total_partes=6,
                           texto_limpo=corrompido)
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert issues_with_rule(rep, "texto_quebrado_letra_a_letra")

    def test_nao_dispara_em_texto_legitimo_com_palavras_curtas(self):
        """Português legítimo é cheio de palavras de 1-2 letras (a, e, o, de, da) —
        vogais e bigramas NÃO contam; só consoante minúscula isolada."""
        chunk = make_chunk(texto_limpo=(
            "Art. 1º A lei é a norma e o juiz a aplica de ofício, e a parte a invoca "
            "em juízo, e o réu a contesta, e o autor a defende, e a corte a confirma "
            "de modo que a regra se impõe a todos e a ninguém escapa a sua força."
        ))
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "texto_quebrado_letra_a_letra")

    def test_nao_dispara_em_citacao_de_alineas_entre_aspas(self):
        """Falso-positivo real calibrado: CLT Art. 334 cita alíneas entre aspas."""
        chunk = make_chunk(texto_limpo=(
            'Art. 334. As atividades definidas nas alíneas "a" e "b" do art. 325, '
            'e nos itens "a", "b" e "c" deste artigo, sendo privativa a do item "d", '
            'e ainda "b" e "c" quando repetidas, e "d" de novo, e "b" mais uma vez.'
        ))
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "texto_quebrado_letra_a_letra")

    def test_nao_dispara_em_abreviacao_de_numero(self):
        """Falso-positivo real calibrado: LI Art. 90 lista 'Lei n° X' repetidas."""
        chunk = make_chunk(texto_limpo=(
            "Art. 90. Revogam-se: I - o Decreto n° 24.150; II - a Lei n° 6.239; "
            "III - a Lei n° 6.649; IV - a Lei n° 6.698; V - a Lei n° 7.077; "
            "VI - a Lei n° 7.612; VII - o Decreto n° 20.111; VIII - a Lei n° 1.300."
        ))
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "texto_quebrado_letra_a_letra")

    def test_nao_dispara_em_incisos_romanos(self):
        """Numerais romanos de inciso são MAIÚSCULOS — fora do match."""
        chunk = make_chunk(texto_limpo=(
            "Art. 5. São direitos: I - vida; V - lazer; X - honra; L - transporte; "
            "C - cultura; D - dignidade; M - moradia; b) alínea normal; c) outra."
        ))
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "texto_quebrado_letra_a_letra")


# ═══════════════════════════════════════════════════════════════════════════════
# Ratchet (2026-07-07): FAIL na extração mais recente, WARN no histórico
# ═══════════════════════════════════════════════════════════════════════════════

from validar_leis import arquivos_mais_recentes, aplicar_ratchet, RATCHET_FAIL_RULES, Issue


class TestRatchetMaisRecente:
    def test_arquivos_mais_recentes_por_base(self):
        files = ["data/lc123_2026-04-08.json", "data/lc123_2026-07-07.json",
                 "data/cdc_2026-07-02.json", "data/cdc_2026-07-07.json",
                 "data/sem_data_padrao.json"]
        rec = arquivos_mais_recentes(files)
        assert "data/lc123_2026-07-07.json" in rec
        assert "data/lc123_2026-04-08.json" not in rec
        assert "data/cdc_2026-07-07.json" in rec
        assert "data/sem_data_padrao.json" in rec   # fora do padrão => ratchet vale

    def test_ratchet_eleva_warn_para_fail_no_mais_recente(self):
        rep = make_report()
        rep.issues.append(Issue("WARN", "CONTEUDO", "texto_quebrado_letra_a_letra", "x", "Art. 1"))
        rep.issues.append(Issue("WARN", "ARTIGO", "standalone_e_partes_coexistem", "x", "Art. 2"))
        rep.issues.append(Issue("WARN", "CONTEUDO", "texto_curto", "x", "Art. 3"))  # fora do ratchet
        aplicar_ratchet(rep, is_latest=True)
        sev = {i.rule: i.severity for i in rep.issues}
        assert sev["texto_quebrado_letra_a_letra"] == "FAIL"
        assert sev["standalone_e_partes_coexistem"] == "FAIL"
        assert sev["texto_curto"] == "WARN"           # regras fora do ratchet intactas

    def test_ratchet_nao_toca_historico(self):
        """Snapshot antigo (não-mais-recente) mantém WARN — histórico legítimo
        não pode reprovar o CI pra sempre."""
        rep = make_report()
        rep.issues.append(Issue("WARN", "CONTEUDO", "texto_quebrado_letra_a_letra", "x", "Art. 1"))
        aplicar_ratchet(rep, is_latest=False)
        assert rep.issues[0].severity == "WARN"


class TestLinhaOrfaM1ComMarkerSolto:
    """CF88 Art. 76 (ADCT): linha M1 restaurada LITERAL termina com marker sem
    parênteses ('... de 2016) Produção de efeitos'). É anotação, não conteúdo —
    a linha continua órfã-M1 e ruido_residual NÃO pode disparar nela."""

    def test_producao_de_efeitos_solto_e_anotacao(self):
        from validar_leis import _e_linha_orfa_m1
        assert _e_linha_orfa_m1(
            "§ 1º (Revogado). (Redação dada pela Emenda constitucional nº 93, "
            "de 2016) Produção de efeitos")
        assert _e_linha_orfa_m1(
            "§ 3º (Revogado). (Redação dada pela Emenda constitucional nº 93, "
            "de 2016) Produção de efeitos")

    def test_conteudo_real_apos_anotacao_nao_e_orfa(self):
        from validar_leis import _e_linha_orfa_m1
        assert not _e_linha_orfa_m1(
            "§ 1º O benefício será revisto. (Redação dada pela Lei nº 9.999, de 2020)")

    def test_ruido_residual_nao_dispara_no_art76_adct(self):
        chunk = make_chunk(artigo="Art. 76 (ADCT)", texto_limpo=(
            "Art. 76. São desvinculados de órgão, fundo ou despesa.\n"
            "§ 1º (Revogado). (Redação dada pela Emenda constitucional nº 93, "
            "de 2016) Produção de efeitos\n"
            "§ 2º Texto vigente do parágrafo segundo aqui presente normal."
        ))
        rep = make_report()
        validate_conteudo([chunk], rep)
        assert not issues_with_rule(rep, "ruido_residual")
