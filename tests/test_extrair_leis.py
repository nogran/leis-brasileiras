"""Testes unitários para as funções de parsing do extrair_leis.py."""

import sys
import os
import re

# Adiciona raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from extrair_leis import (
    REGEX_ARTIGO,
    REGEX_SECAO_HEADER,
    REGEX_CONTINUACAO_HEADER,
    INLINE_HEADER_RE,
    parse_art_num,
    classificar_linha_artigo,
    detectar_status_artigo,
    extrair_alteracoes,
    extrair_referencias,
    limpar_ruido_legislativo,
    split_com_overlap,
    split_inline_headers,
    hash_texto,
    decode_utf16,
    strip_padding_tail,
)


# ═══════════════════════════════════════════════════════════════════════════════
# REGEX_ARTIGO
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexArtigo:
    def test_artigo_simples(self):
        m = REGEX_ARTIGO.match("Art. 1° O presente...")
        assert m is not None
        assert m.group(1) == "1"

    def test_artigo_com_sufixo(self):
        m = REGEX_ARTIGO.match("Art. 42-A.")
        assert m is not None
        assert m.group(1) == "42"
        assert m.group(2) == "A"

    def test_artigo_fim_de_linha(self):
        """FIX 10: LC 123 declara artigo sozinho na linha."""
        m = REGEX_ARTIGO.match("Art. 1")
        assert m is not None

    def test_case_sensitive_nao_casa_minusculo(self):
        """FIX 8: 'art.' minúsculo é referência cruzada, não declaração."""
        m = REGEX_ARTIGO.match("art. 966 da Lei nº 10.406")
        assert m is None

    def test_artigo_numero_grande(self):
        m = REGEX_ARTIGO.match("Art. 1.000 Texto")
        assert m is not None
        assert m.group(1) == "1.000"

    def test_artigo_sem_ponto(self):
        m = REGEX_ARTIGO.match("Art 5° Todos são iguais")
        assert m is not None
        assert m.group(1) == "5"

    def test_sufixo_sem_hifen_nao_casa(self):
        """FIX 18: 'Art. 142 - O empregador' não deve capturar 'O' como sufixo."""
        m = REGEX_ARTIGO.match("Art. 142 - O empregador...")
        # Deve casar o artigo mas sem sufixo
        assert m is not None
        assert m.group(2) is None


# ═══════════════════════════════════════════════════════════════════════════════
# parse_art_num
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseArtNum:
    def test_simples(self):
        assert parse_art_num("999") == 999

    def test_com_ponto(self):
        assert parse_art_num("1.000") == 1000

    def test_um(self):
        assert parse_art_num("1") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# classificar_linha_artigo
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassificarLinhaArtigo:
    def test_progressao_normal(self):
        result = classificar_linha_artigo("Art. 2. Texto", 2, "", 1)
        assert result == "novo_artigo"

    def test_mesmo_numero_com_sufixo(self):
        result = classificar_linha_artigo("Art. 54-A. Texto", 54, "A", 54)
        assert result == "novo_artigo"

    def test_salto_grande_forward_eh_citacao(self):
        """FIX 9: salto > 200 sem marcador = citação."""
        result = classificar_linha_artigo("Art. 966.", 966, "", 12)
        assert result == "citacao"

    def test_backward_grande_eh_citacao(self):
        result = classificar_linha_artigo("Art. 5. texto", 5, "", 100)
        assert result == "citacao"

    def test_referencia_outra_lei_com_salto(self):
        """FIX 9: 'art. 966 da Lei nº 10.406' com salto = citação."""
        result = classificar_linha_artigo(
            "Art. 966 da Lei nº 10.406", 966, "", 12
        )
        assert result == "citacao"

    def test_artigo_real_que_menciona_outra_lei(self):
        """FIX 9: Art. 110 do CDC menciona outra lei mas é sequencial."""
        result = classificar_linha_artigo(
            "Art. 110. Acrescente-se... da Lei nº 7.347", 110, "", 109
        )
        assert result == "novo_artigo"


# ═══════════════════════════════════════════════════════════════════════════════
# detectar_status_artigo
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectarStatusArtigo:
    def test_artigo_vigente(self):
        status, vetos = detectar_status_artigo(
            "Art. 1° O presente código estabelece normas de proteção..."
        )
        assert status == "vigente"
        assert vetos == []

    def test_vetado_total(self):
        """FIX 1: artigo inteiramente vetado."""
        status, vetos = detectar_status_artigo("Art. 11. (Vetado).")
        assert status == "vetado_total"
        assert vetos == []

    def test_revogado(self):
        status, vetos = detectar_status_artigo("Art. 78. (REVOGADO)")
        assert status == "revogado"
        assert vetos == []

    def test_veto_parcial_inciso(self):
        """FIX 1: artigo vigente com inciso vetado."""
        texto = (
            "Art. 6° São direitos básicos do consumidor:\n"
            "I - proteção da vida;\n"
            "IX - (Vetado)\n"
            "X - prevenção e tratamento."
        )
        status, vetos = detectar_status_artigo(texto)
        assert status == "vigente"
        assert "IX" in vetos

    def test_veto_parcial_paragrafo(self):
        texto = (
            "Art. 5° Texto do artigo com bastante conteúdo para ultrapassar o "
            "limiar de 200 caracteres, incluindo incisos e parágrafos diversos "
            "que tornam este artigo suficientemente longo para o teste.\n"
            "§ 1° (Vetado).\n"
            "§ 2° (Vetado)."
        )
        status, vetos = detectar_status_artigo(texto)
        assert status == "vigente"
        assert len(vetos) == 2

    def test_vetado_com_marker_incluido(self):
        """FIX 11: strip de amendment markers antes da análise."""
        texto = "Art. 54-E. (VETADO).\n(Incluído pela Lei nº 14.181, de 2021)"
        status, vetos = detectar_status_artigo(texto)
        assert status == "vetado_total"

    def test_suprimido(self):
        texto = "Art. 686. (Suprimido pelo Decreto-Lei nº 8.737, de 1946)"
        status, vetos = detectar_status_artigo(texto)
        assert status == "revogado"


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_alteracoes
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtrairAlteracoes:
    def test_redacao_dada(self):
        texto = "Art. 6° (Redação dada pela Lei nº 12.741, de 2012)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "redacao_dada"
        assert "12.741" in result[0]["norma"]

    def test_incluido_feminino(self):
        """FIX 24: 'Incluída' (feminino) deve ser detectado."""
        texto = "(Incluída pela Lei nº 14.181, de 2021)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "incluido"

    def test_multiplas_alteracoes(self):
        texto = (
            "(Redação dada pela Lei nº 12.741, de 2012)\n"
            "(Incluído pela Lei nº 14.181, de 2021)"
        )
        result = extrair_alteracoes(texto)
        assert len(result) == 2

    def test_suprimido(self):
        """PL-19 B-04: marker (Suprimido pelo Decreto-Lei nº X) deve virar alteracao."""
        texto = "(Suprimido pelo Decreto-Lei nº 9.797, de 9.9.1946)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "suprimido"
        assert "9.797" in result[0]["norma"]

    def test_suprimido_feminino(self):
        texto = "(Suprimida pelo Decreto-lei nº 6.353, de 20.3.1944)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "suprimido"

    def test_restaurado(self):
        """PL-19 B-04: marker (Restaurado pelo Decreto-lei nº X) deve virar alteracao."""
        texto = "(Restaurado pelo Decreto-lei nº 5, de 4.4.1966)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "restaurado"
        assert "5" in result[0]["norma"]

    def test_expressao_substituida(self):
        """PL-19 B-04: marker (Expressão substituída pela Lei nº X) deve virar alteracao."""
        texto = "(Expressão substituída pela Lei nº 12.010, de 2009)"
        result = extrair_alteracoes(texto)
        assert len(result) == 1
        assert result[0]["tipo"] == "expressao_substituida"
        assert "12.010" in result[0]["norma"]

    def test_sem_duplicatas(self):
        texto = (
            "(Redação dada pela Lei nº 12.741, de 2012)\n"
            "(Redação dada pela Lei nº 12.741, de 2012)"
        )
        result = extrair_alteracoes(texto)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_referencias
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtrairReferencias:
    def test_sem_auto_referencia(self):
        """FIX 3: Art. 7 não deve referenciar a si mesmo."""
        texto = "Art. 7° O consumidor, nos termos do art. 7 e art. 14..."
        refs = extrair_referencias(texto, "Art. 7")
        assert "Art. 7" not in refs["internas"]
        assert "Art. 14" in refs["internas"]

    def test_referencia_externa(self):
        texto = "nos termos da Lei nº 13.146"
        refs = extrair_referencias(texto, "Art. 1")
        assert any("13.146" in lei for lei in refs["leis_externas"])

    def test_referencia_constituicao(self):
        texto = "conforme Constituição Federal, art. 5°"
        refs = extrair_referencias(texto, "Art. 1")
        assert refs["constituicao"] is True

    def test_sem_referencia_constituicao(self):
        texto = "Art. 1° O presente código..."
        refs = extrair_referencias(texto, "Art. 1")
        assert refs["constituicao"] is False

    def test_singular_art_dentro_da_lei(self):
        """Regex _arts_multi deve casar 'art.' singular (bug exposto pelo PL-11)."""
        texto = "Disposto no art. 14 desta Lei."
        refs = extrair_referencias(texto, "Art. 7")
        assert "Art. 14" in refs["internas"]

    def test_singular_art_externo_eh_filtrado(self):
        """'art. 14 da Lei nº X' deve ir pra leis_externas, nao internas."""
        texto = "Conforme art. 14 da Lei nº 8.078, de 1990, o consumidor..."
        refs = extrair_referencias(texto, "Art. 7")
        assert "Art. 14" not in refs["internas"]
        assert any("8.078" in lei for lei in refs["leis_externas"])

    def test_lei_sem_numero_nao_captura(self):
        """PL-19 B-05: 'Lei n.' (sem digito) NAO deve virar leis_externas."""
        texto = "Conforme Lei n. , o consumidor."
        refs = extrair_referencias(texto, "Art. 7")
        assert refs["leis_externas"] == [], f"capturou Lei sem numero: {refs['leis_externas']}"

    def test_lei_sem_espaco_apos_n_normaliza(self):
        """PL-19 B-05: 'Lei n°7.347' deve virar 'Lei nº 7.347' normalizado."""
        texto = "nos termos da Lei n°7.347 e tambem"
        refs = extrair_referencias(texto, "Art. 7")
        assert refs["leis_externas"] == ["Lei nº 7.347"], f"got {refs['leis_externas']}"

    def test_lei_no_normaliza_para_nº(self):
        """PL-19 B-05: 'Lei no 8.212' deve virar 'Lei nº 8.212'."""
        texto = "vide a Lei no 8.212 conforme."
        refs = extrair_referencias(texto, "Art. 7")
        assert refs["leis_externas"] == ["Lei nº 8.212"], f"got {refs['leis_externas']}"

    def test_lei_n_simples_normaliza(self):
        """PL-19 B-05: 'Lei n 8.212' deve virar 'Lei nº 8.212'."""
        texto = "vide a Lei n 8.212 conforme."
        refs = extrair_referencias(texto, "Art. 7")
        assert refs["leis_externas"] == ["Lei nº 8.212"], f"got {refs['leis_externas']}"

    def test_lei_dedupe_apos_normalizar(self):
        """PL-19 B-05: 'Lei n°7.347' e 'Lei nº 7.347' viram 1 entrada apos normalizar."""
        texto = "Lei n°7.347 e Lei nº 7.347 sao a mesma."
        refs = extrair_referencias(texto, "Art. 7")
        assert refs["leis_externas"] == ["Lei nº 7.347"]

    def test_decreto_lei_case_normalizacao(self):
        """PL-19 B-05: 'Decreto-lei nº 4.037' (lowercase) normaliza pra 'Decreto-Lei nº 4.037'."""
        texto = "Conforme Decreto-lei nº 4.037 e tambem."
        refs = extrair_referencias(texto, "Art. 7")
        assert "Decreto-Lei nº 4.037" in refs["leis_externas"], f"got {refs['leis_externas']}"


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_notas_legais (PL-19 B-10)
# ═══════════════════════════════════════════════════════════════════════════════

from extrair_leis import extrair_notas_legais, extrair_controle_constitucionalidade


class TestExtrairNotasLegais:
    def test_vide_lei(self):
        notas = extrair_notas_legais("Art. 60. (Vide Lei nº 8.656, de 1993)")
        assert len(notas) == 1
        assert notas[0]["tipo"] == "vide_lei"
        assert "8.656" in notas[0]["referencia"]
        assert notas[0]["raw"] == "(Vide Lei nº 8.656, de 1993)"

    def test_vide_lei_complementar(self):
        notas = extrair_notas_legais("(Vide Lei Complementar nº 95, de 1998)")
        assert notas[0]["tipo"] == "vide_lei_complementar"

    def test_vide_decreto_lei(self):
        notas = extrair_notas_legais("(Vide Decreto-Lei nº 5.452, de 1943)")
        assert notas[0]["tipo"] == "vide_decreto_lei"

    def test_vide_emenda_constitucional(self):
        notas = extrair_notas_legais("(Vide Emenda constitucional nº 106, de 2020)")
        assert notas[0]["tipo"] == "vide_emenda"

    def test_vide_medida_provisoria(self):
        notas = extrair_notas_legais("(Vide Medida Provisória nº 526, de 2011)")
        assert notas[0]["tipo"] == "vide_medida_provisoria"

    def test_regulamento(self):
        notas = extrair_notas_legais("garantido no artigo. (Regulamento)")
        assert notas[0]["tipo"] == "regulamento"
        assert notas[0]["referencia"] is None

    def test_producao_de_efeito(self):
        notas = extrair_notas_legais("(Produção de efeito)")
        assert notas[0]["tipo"] == "producao_de_efeito"

    def test_dedup_raw_identico(self):
        notas = extrair_notas_legais("(Vide Lei nº 8.656, de 1993) (Vide Lei nº 8.656, de 1993)")
        assert len(notas) == 1

    def test_vazio(self):
        assert extrair_notas_legais("") == []
        assert extrair_notas_legais("texto sem markers") == []

    def test_adi_nao_vai_pra_notas_legais(self):
        """ADI/ADPF/ADC vao pro campo controle_constitucionalidade separado.
        Pass: extrair_notas_legais NAO retorna eles."""
        texto = "(Vide ADI nº 2.135) (Vide ADPF 672)"
        notas = extrair_notas_legais(texto)
        assert notas == [], f"ADI vazou pra notas_legais: {notas}"

    def test_vide_outros_fallback(self):
        """Vide nao listado vira vide_outros — mas SO se nao for ADI/ADPF/ADC."""
        notas = extrair_notas_legais("(Vide algo super exotico)")
        assert len(notas) == 1
        assert notas[0]["tipo"] == "vide_outros"
        assert notas[0]["referencia"] == "algo super exotico"


class TestExtrairControleConstitucionalidade:
    def test_adi(self):
        out = extrair_controle_constitucionalidade("(Vide ADI nº 2.135)")
        assert out == [{"tipo": "ADI", "numero": "2.135", "tribunal": "STF", "raw": "(Vide ADI nº 2.135)"}]

    def test_adin(self):
        out = extrair_controle_constitucionalidade("(Vide ADIN 3392)")
        assert out[0]["tipo"] == "ADI"
        assert out[0]["numero"] == "3392"

    def test_adpf(self):
        out = extrair_controle_constitucionalidade("(Vide ADPF 672)")
        assert out[0]["tipo"] == "ADPF"
        assert out[0]["numero"] == "672"

    def test_adc(self):
        out = extrair_controle_constitucionalidade("(Vide ADC 58)")
        assert out[0]["tipo"] == "ADC"

    def test_mi(self):
        out = extrair_controle_constitucionalidade("(Vide MI 7300)")
        assert out[0]["tipo"] == "MI"

    def test_ar(self):
        out = extrair_controle_constitucionalidade("(Vide AR 2876)")
        assert out[0]["tipo"] == "AR"

    def test_multiplos(self):
        texto = "(Vide ADI nº 2.135) e tambem (Vide ADPF 672)"
        out = extrair_controle_constitucionalidade(texto)
        assert len(out) == 2

    def test_dedup(self):
        texto = "(Vide ADI nº 2.135) outras coisas (Vide ADI nº 2.135)"
        out = extrair_controle_constitucionalidade(texto)
        assert len(out) == 1

    def test_vazio(self):
        assert extrair_controle_constitucionalidade("") == []
        assert extrair_controle_constitucionalidade("texto sem ADI") == []

    def test_lei_nao_e_controle_const(self):
        out = extrair_controle_constitucionalidade("(Vide Lei nº 8.656, de 1993)")
        assert out == []


# ═══════════════════════════════════════════════════════════════════════════════
# limpar_ruido_legislativo
# ═══════════════════════════════════════════════════════════════════════════════

class TestLimparRuidoLegislativo:
    def test_remove_redacao_dada(self):
        texto = "Texto do artigo. (Redação dada pela Lei nº 12.741, de 2012)"
        resultado = limpar_ruido_legislativo(texto)
        assert "(Redação dada" not in resultado
        assert "Texto do artigo" in resultado

    def test_remove_incluido(self):
        texto = "Texto. (Incluído pela Lei nº 14.181, de 2021)"
        resultado = limpar_ruido_legislativo(texto)
        assert "(Incluído" not in resultado

    def test_remove_vigencia(self):
        texto = "Texto do artigo.\n Vigência \nOutro texto."
        resultado = limpar_ruido_legislativo(texto)
        assert "Vigência" not in resultado

    def test_preserva_texto_real(self):
        texto = "Art. 1° O presente código estabelece normas."
        resultado = limpar_ruido_legislativo(texto)
        assert resultado == texto


# ═══════════════════════════════════════════════════════════════════════════════
# split_com_overlap
# ═══════════════════════════════════════════════════════════════════════════════

class TestSplitComOverlap:
    def test_texto_curto_nao_divide(self):
        texto = "Artigo curto."
        partes = split_com_overlap(texto, max_chars=6000)
        assert len(partes) == 1
        assert partes[0] == texto

    def test_texto_longo_divide(self):
        texto = "A" * 7000
        partes = split_com_overlap(texto, max_chars=6000, overlap_chars=400)
        assert len(partes) >= 2

    def test_overlap_existe(self):
        # Cria texto com quebras de linha para facilitar corte
        linhas = [f"Linha {i:04d} " + "x" * 50 for i in range(120)]
        texto = "\n".join(linhas)
        partes = split_com_overlap(texto, max_chars=3000, overlap_chars=400)
        assert len(partes) >= 2
        # O início da parte 2 deve conter texto do fim da parte 1
        fim_parte1 = partes[0][-200:]
        inicio_parte2 = partes[1][:400]
        # Deve haver alguma sobreposição
        assert any(
            linha in inicio_parte2
            for linha in fim_parte1.split("\n")
            if linha.strip()
        )

    def test_nenhuma_parte_vazia(self):
        texto = "A\n" * 5000
        partes = split_com_overlap(texto, max_chars=3000)
        assert all(p.strip() for p in partes)


# ═══════════════════════════════════════════════════════════════════════════════
# hash_texto
# ═══════════════════════════════════════════════════════════════════════════════

class TestHashTexto:
    def test_deterministic(self):
        assert hash_texto("teste") == hash_texto("teste")

    def test_different_inputs(self):
        assert hash_texto("a") != hash_texto("b")

    def test_length_16(self):
        assert len(hash_texto("qualquer coisa")) == 16


# ═══════════════════════════════════════════════════════════════════════════════
# REGEX_SECAO_HEADER — header de hierarquia em linha unica
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegexSecaoHeader:
    """Garante que o regex que detecta headers (LIVRO/TÍTULO/etc) funciona pros casos
    canonicos do Planalto. Forma standalone: numeral sem nome na mesma linha."""

    def test_livro_simples(self):
        assert REGEX_SECAO_HEADER.match("LIVRO")

    def test_livro_com_numeral(self):
        assert REGEX_SECAO_HEADER.match("LIVRO I")

    def test_livro_unico(self):
        assert REGEX_SECAO_HEADER.match("LIVRO ÚNICO")

    def test_titulo_com_numeral(self):
        assert REGEX_SECAO_HEADER.match("TÍTULO XIV")

    def test_subtitulo_com_numeral(self):
        assert REGEX_SECAO_HEADER.match("SUBTÍTULO II")

    def test_capitulo_simples(self):
        assert REGEX_SECAO_HEADER.match("CAPÍTULO")

    def test_capitulo_numeral_grande(self):
        assert REGEX_SECAO_HEADER.match("CAPÍTULO XXXVII")

    def test_capitulo_com_sufixo(self):
        assert REGEX_SECAO_HEADER.match("CAPÍTULO VII-A")

    def test_secao_preliminar(self):
        assert REGEX_SECAO_HEADER.match("SEÇÃO PRELIMINAR")

    def test_secao_complementar(self):
        assert REGEX_SECAO_HEADER.match("SEÇÃO COMPLEMENTAR")

    # Casos negativos — nao devem casar (vao virar buffer de artigo se nao filtrados)

    def test_nao_casa_header_inline_com_nome(self):
        """O regex NAO casa quando ha texto descritivo apos o numeral.
        Esse caso e tratado pelo INLINE_HEADER split (sub-bloco 2e)."""
        assert not REGEX_SECAO_HEADER.match("CAPÍTULO VII-A — DO CONDOMÍNIO EM MULTIPROPRIEDADE")
        assert not REGEX_SECAO_HEADER.match("LIVRO I DAS PESSOAS")
        assert not REGEX_SECAO_HEADER.match("CAPÍTULO XIV — DAS DISPOSIÇÕES FINAIS E TRANSITÓRIAS")

    def test_nao_casa_artigo(self):
        assert not REGEX_SECAO_HEADER.match("Art. 1° Toda pessoa")

    def test_nao_casa_paragrafo(self):
        assert not REGEX_SECAO_HEADER.match("§ 1° Quando ocorrer")

    def test_nao_casa_palavra_avulsa(self):
        assert not REGEX_SECAO_HEADER.match("livro contabil deste estabelecimento")


class TestRegexContinuacaoHeader:
    """Garante que o regex de continuacao casa numeral isolado em linha (caso de header
    quebrado em 2 linhas no clean.txt)."""

    def test_numeral_romano_simples(self):
        assert REGEX_CONTINUACAO_HEADER.match("I")

    def test_numeral_romano_com_sufixo(self):
        assert REGEX_CONTINUACAO_HEADER.match("VII-A")

    def test_unico(self):
        assert REGEX_CONTINUACAO_HEADER.match("ÚNICO")

    def test_preliminar(self):
        assert REGEX_CONTINUACAO_HEADER.match("PRELIMINAR")

    def test_nao_casa_com_texto(self):
        assert not REGEX_CONTINUACAO_HEADER.match("I — Disposições Gerais")

    def test_nao_casa_palavra(self):
        assert not REGEX_CONTINUACAO_HEADER.match("Disposições")


# ═══════════════════════════════════════════════════════════════════════════════
# split_inline_headers — PL-13 sub-bloco 2e
# ═══════════════════════════════════════════════════════════════════════════════

class TestSplitInlineHeaders:
    """Garante que split_inline_headers separa numeral+nome inline em 2 linhas
    pra que o parser possa capturar como header standalone."""

    def test_livro_inline_maiusculo(self):
        assert split_inline_headers("LIVRO I DAS PESSOAS") == "LIVRO I\nDAS PESSOAS"

    def test_livro_inline_title_case(self):
        assert split_inline_headers("LIVRO III Dos Fatos Jurídicos") == "LIVRO III\nDos Fatos Jurídicos"

    def test_titulo_inline(self):
        assert (
            split_inline_headers("TÍTULO I DAS PESSOAS NATURAIS")
            == "TÍTULO I\nDAS PESSOAS NATURAIS"
        )

    def test_subtitulo_inline(self):
        assert (
            split_inline_headers("SUBTÍTULO I Da Sociedade Não Personificada")
            == "SUBTÍTULO I\nDa Sociedade Não Personificada"
        )

    def test_capitulo_inline(self):
        assert (
            split_inline_headers("CAPÍTULO I Da Personalidade e da Capacidade")
            == "CAPÍTULO I\nDa Personalidade e da Capacidade"
        )

    def test_capitulo_com_sufixo_inline(self):
        assert (
            split_inline_headers("CAPÍTULO VII-A Do Condomínio em Multipropriedade")
            == "CAPÍTULO VII-A\nDo Condomínio em Multipropriedade"
        )

    def test_secao_inline(self):
        assert (
            split_inline_headers("Seção I Da Curadoria dos Bens do Ausente")
            == "Seção I\nDa Curadoria dos Bens do Ausente"
        )

    def test_titulo_unico_inline(self):
        assert (
            split_inline_headers("TÍTULO ÚNICO Das Diferentes Classes de Bens")
            == "TÍTULO ÚNICO\nDas Diferentes Classes de Bens"
        )

    # Casos negativos: nao deve mexer

    def test_header_standalone_intacto(self):
        assert split_inline_headers("LIVRO I") == "LIVRO I"

    def test_header_so_marcador_intacto(self):
        assert split_inline_headers("CAPÍTULO") == "CAPÍTULO"

    def test_artigo_intacto(self):
        assert (
            split_inline_headers("Art. 1° Toda pessoa é capaz de direitos e deveres")
            == "Art. 1° Toda pessoa é capaz de direitos e deveres"
        )

    def test_paragrafo_intacto(self):
        assert split_inline_headers("§ 1° Quando ocorrer") == "§ 1° Quando ocorrer"

    def test_texto_arbitrario_intacto(self):
        assert split_inline_headers("texto sem header") == "texto sem header"

    def test_multiplas_linhas(self):
        entrada = (
            "LIVRO I DAS PESSOAS\n"
            "TÍTULO I DAS PESSOAS NATURAIS\n"
            "Art. 1° Toda pessoa\n"
        )
        esperado = (
            "LIVRO I\n"
            "DAS PESSOAS\n"
            "TÍTULO I\n"
            "DAS PESSOAS NATURAIS\n"
            "Art. 1° Toda pessoa\n"
        )
        assert split_inline_headers(entrada) == esperado

    def test_idempotente(self):
        """Aplicar 2x da mesmo resultado (linhas ja split nao sao re-split)."""
        entrada = "CAPÍTULO I Da Personalidade"
        once = split_inline_headers(entrada)
        twice = split_inline_headers(once)
        assert once == twice == "CAPÍTULO I\nDa Personalidade"

    def test_nao_quebra_citacao_inline_lowercase(self):
        """PL-13 Estagio 6: 'Livro II da Parte Especial deste Código' e citacao
        inline dentro de uma frase, NAO header. O 'da' lowercase deve impedir o split.
        Bug encontrado em CC (36 chunks) e CPC (260 chunks)."""
        entrada = "Livro II da Parte Especial deste Código"
        assert split_inline_headers(entrada) == entrada

    def test_nao_quebra_referencia_outra_lei(self):
        """'Livro II, Título IV, da Lei nº 5.869' e referencia a outra lei.
        Tem virgula apos 'II' que ja impede match, mas vale documentar."""
        entrada = "Livro II, Título IV, da Lei nº 5.869, de 11 de janeiro de 1973"
        assert split_inline_headers(entrada) == entrada


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_estrutura — hierarquia (PL-13)
# ═══════════════════════════════════════════════════════════════════════════════

from extrair_leis import extrair_estrutura


class TestExtrairEstruturaHierarquia:
    def test_bloco_tem_livro_nome_e_subtitulo_nome(self):
        """PL-13 Bug A: dict do bloco precisa ter livro_nome e subtitulo_nome (sub-bloco 2a)."""
        texto = (
            "LIVRO I\n"
            "Das Pessoas\n"
            "SUBTÍTULO I\n"
            "Disposições Preliminares\n"
            "Art. 1° Toda pessoa é capaz de direitos e deveres na ordem civil, "
            "e tem personalidade desde o nascimento com vida.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        assert len(blocos) >= 1, f"esperava ao menos 1 bloco, recebi {len(blocos)}"
        bloco = blocos[0]
        assert "livro_nome" in bloco, f"livro_nome ausente do dict: {sorted(bloco.keys())}"
        assert "subtitulo_nome" in bloco, f"subtitulo_nome ausente do dict: {sorted(bloco.keys())}"
        assert bloco["livro"] == "LIVRO I"
        assert bloco["livro_nome"] == "Das Pessoas"
        assert bloco["subtitulo"] == "SUBTÍTULO I"
        assert bloco["subtitulo_nome"] == "Disposições Preliminares"

    def test_capitulo_nome_strip_marker_alteracao(self):
        """PL-13 Bug D: nome de capitulo nao pode conter marker de alteracao (sub-bloco 2c)."""
        texto = (
            "CAPÍTULO\n"
            "VII-A (Incluído pela Lei nº 13.777, de 2018) (Vigência) DO CONDOMÍNIO EM MULTIPROPRIEDADE\n"
            "Art. 1.358-B. A multipropriedade reger-se-á pelo disposto neste Capítulo e, "
            "de forma supletiva e subsidiária, pelas demais disposições deste Código.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        bloco = blocos[0]
        assert bloco["capitulo"] == "CAPÍTULO VII-A", f"capitulo errado: {bloco['capitulo']!r}"
        assert "Incluído" not in bloco["capitulo_nome"], (
            f"capitulo_nome ainda tem marker: {bloco['capitulo_nome']!r}"
        )
        assert "Vigência" not in bloco["capitulo_nome"]
        assert "DO CONDOMÍNIO EM MULTIPROPRIEDADE" in bloco["capitulo_nome"]
        assert "Incluído" not in bloco["path_hierarquico"]
        assert "Vigência" not in bloco["path_hierarquico"]

    def test_limpar_marker_hierarquia(self):
        """Unit test: helper que remove markers de alteracao de nomes hierarquicos."""
        from extrair_leis import limpar_marker_hierarquia
        # Marker no inicio
        assert limpar_marker_hierarquia(
            "(Incluído pela Lei nº 13.777, de 2018) (Vigência) DO CONDOMÍNIO EM MULTIPROPRIEDADE"
        ) == "DO CONDOMÍNIO EM MULTIPROPRIEDADE"
        # Marker no meio
        assert limpar_marker_hierarquia(
            "Dos Direitos (Redação dada pela Lei nº 14.181, de 2021) Básicos"
        ) == "Dos Direitos Básicos"
        # Sem marker
        assert limpar_marker_hierarquia("Da Personalidade") == "Da Personalidade"
        # Apenas marker
        assert limpar_marker_hierarquia("(Vigência)") == ""
        # Vazio
        assert limpar_marker_hierarquia("") == ""

    def test_limpar_marker_hierarquia_vide(self):
        """PL-19 B-07: limpar_marker_hierarquia deve cobrir Vide tambem."""
        from extrair_leis import limpar_marker_hierarquia
        # Caso real do CDC Art. 60: 'Das Sanções Administrativas (Vide Lei nº 8.656, de 1993)'
        assert limpar_marker_hierarquia(
            "Das Sanções Administrativas (Vide Lei nº 8.656, de 1993)"
        ) == "Das Sanções Administrativas"
        # Caso real CLT: 'CONVENÇÕES COLETIVAS DE TRABALHO (Vide Medida Provisória nº 1.046, de 2021)'
        assert limpar_marker_hierarquia(
            "CONVENÇÕES COLETIVAS DE TRABALHO (Vide Medida Provisória nº 1.046, de 2021)"
        ) == "CONVENÇÕES COLETIVAS DE TRABALHO"

    def test_limpar_marker_hierarquia_regulamento(self):
        """PL-19 B-07: limpar_marker_hierarquia deve cobrir Regulamento."""
        from extrair_leis import limpar_marker_hierarquia
        assert limpar_marker_hierarquia(
            "Dos Direitos Fundamentais (Regulamento)"
        ) == "Dos Direitos Fundamentais"

    def test_bloco_tem_notas_legais_e_controle_const(self):
        """PL-19 B-10/B-11: dict do bloco precisa ter notas_legais e controle_constitucionalidade."""
        texto = (
            "Art. 1° Toda pessoa é capaz de direitos e deveres na ordem civil. "
            "(Vide Lei nº 8.656, de 1993) (Vide ADI nº 2.135) (Regulamento)\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        assert len(blocos) >= 1
        bloco = blocos[0]
        assert "notas_legais" in bloco
        assert "controle_constitucionalidade" in bloco
        # notas_legais deve ter vide_lei e regulamento (ADI vai pro outro campo)
        tipos_notas = [n["tipo"] for n in bloco["notas_legais"]]
        assert "vide_lei" in tipos_notas
        assert "regulamento" in tipos_notas
        # controle_constitucionalidade deve ter ADI
        assert len(bloco["controle_constitucionalidade"]) == 1
        assert bloco["controle_constitucionalidade"][0]["tipo"] == "ADI"

    def test_notas_herdadas_de_capitulo_nome(self):
        """PL-19 Estagio 2: notas_legais do nome do capitulo devem ser herdadas
        pelos artigos sob aquele capitulo. Reproduz caso CDC Art. 60 onde
        '(Vide Lei nº 8.656, de 1993)' estava no nome do capitulo VII."""
        texto = (
            "CAPÍTULO VII\n"
            "Das Sanções Administrativas (Vide Lei nº 8.656, de 1993)\n"
            "Art. 55. A União, os Estados e o Distrito Federal, em caráter concorrente "
            "e nas suas respectivas áreas de atuação administrativa, baixarão normas "
            "relativas à produção, industrialização, distribuição e consumo.\n"
            "Art. 60. A imposição de contrapropaganda será cominada quando o fornecedor "
            "incorrer na prática de publicidade enganosa ou abusiva, nos termos do art. 36.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        # Pelo menos 2 blocos: Art. 55 e Art. 60
        assert len(blocos) >= 2
        # Capitulo_nome deve estar LIMPO (sem o Vide)
        for b in blocos:
            assert "Vide" not in b["capitulo_nome"], f"capitulo_nome ainda tem Vide: {b['capitulo_nome']}"
            assert b["capitulo_nome"] == "Das Sanções Administrativas"
        # AMBOS os artigos devem ter notas_legais com vide_lei (herdado do capitulo)
        for b in blocos:
            tipos = [n["tipo"] for n in b["notas_legais"]]
            assert "vide_lei" in tipos, f"{b['artigo']} sem vide_lei: {b['notas_legais']}"
            # E a referencia deve ser 8.656
            vide_leis = [n for n in b["notas_legais"] if n["tipo"] == "vide_lei"]
            assert any("8.656" in n["referencia"] for n in vide_leis)

    def test_controle_const_herdado_de_titulo(self):
        """PL-19 Estagio 2: ADI no titulo_nome herda pros artigos."""
        texto = (
            "TÍTULO IV\n"
            "Da Tributação (Vide ADI nº 2.135)\n"
            "Art. 145. A União, os Estados, o Distrito Federal e os Municípios poderão "
            "instituir os seguintes tributos.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        bloco = blocos[0]
        assert bloco["titulo_nome"] == "Da Tributação"  # limpo
        # ADI herdado
        assert len(bloco["controle_constitucionalidade"]) == 1
        assert bloco["controle_constitucionalidade"][0]["tipo"] == "ADI"
        assert bloco["controle_constitucionalidade"][0]["numero"] == "2.135"

    def test_alteracao_em_capitulo_nome_captura_com_escopo(self):
        """PL-19 Estagio 2: '(Incluído pela Lei nº X)' em capitulo_nome
        deve virar alteracao no artigo com escopo='capitulo'."""
        texto = (
            "CAPÍTULO V-A\n"
            "DA PREVENÇÃO E DO TRATAMENTO DO SUPERENDIVIDAMENTO (Incluído pela Lei nº 14.181, de 2021)\n"
            "Art. 54-A. Esta Seção dispõe sobre a prevenção do superendividamento da pessoa natural.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        bloco = blocos[0]
        # Capitulo_nome deve estar limpo
        assert bloco["capitulo_nome"] == "DA PREVENÇÃO E DO TRATAMENTO DO SUPERENDIVIDAMENTO"
        # Alteracoes deve incluir o "incluido" com escopo capitulo
        cap_alts = [a for a in bloco["alteracoes"] if a.get("escopo") == "capitulo"]
        assert len(cap_alts) == 1
        assert cap_alts[0]["tipo"] == "incluido"
        assert "14.181" in cap_alts[0]["norma"]

    def test_alteracao_artigo_tem_escopo_default(self):
        """PL-19 Estagio 2: alteracoes capturadas do texto do artigo tem escopo='artigo' por default."""
        texto = (
            "Art. 6° (Redação dada pela Lei nº 12.741, de 2012) São direitos básicos do consumidor.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        bloco = blocos[0]
        assert all(a.get("escopo") == "artigo" for a in bloco["alteracoes"])

    def test_notas_resetam_em_novo_capitulo(self):
        """Quando novo CAPITULO comeca, notas_legais do antigo NAO devem
        herdar pros artigos do novo capitulo."""
        texto = (
            "CAPÍTULO I\n"
            "Das Sanções (Vide Lei nº 8.656, de 1993)\n"
            "Art. 1. Texto suficiente longo do artigo 1 com mais de trinta caracteres.\n"
            "CAPÍTULO II\n"
            "Da Outra Coisa\n"
            "Art. 2. Texto suficiente longo do artigo 2 com mais de trinta caracteres.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        # Art. 1 deve ter vide_lei
        art1 = next(b for b in blocos if b["artigo"] == "Art. 1")
        assert any(n["tipo"] == "vide_lei" for n in art1["notas_legais"])
        # Art. 2 NAO deve ter vide_lei (novo capitulo, reset)
        art2 = next(b for b in blocos if b["artigo"] == "Art. 2")
        assert all(n["tipo"] != "vide_lei" for n in art2["notas_legais"]), \
            f"Art. 2 herdou notas do cap I: {art2['notas_legais']}"

    def test_inline_headers_split_e_parser_produzem_path_completo(self):
        """PL-13 Bug C (sub-bloco 2e): texto com headers inline (formato Planalto)
        passa pelo split_inline_headers e o parser captura hierarquia 4-niveis.
        Reproduz mini-CC com LIVRO + TÍTULO + CAPÍTULO inline."""
        # Input em formato Planalto (numeral e nome inline, como vem do clean.txt
        # apos a etapa de merge em extrair_lei). Uso Art. 1 pra evitar o filtro
        # de salto > 200 do classificar_linha_artigo.
        texto_planalto = (
            "LIVRO I DAS PESSOAS\n"
            "TÍTULO I DAS PESSOAS NATURAIS\n"
            "CAPÍTULO I Da Personalidade e da Capacidade\n"
            "Art. 1° Toda pessoa é capaz de direitos e deveres na ordem civil, "
            "e tem personalidade desde o nascimento com vida.\n"
        )
        # Aplicar o split (e o que extrair_lei faz antes de chamar extrair_estrutura)
        texto_split = split_inline_headers(texto_planalto)
        blocos = extrair_estrutura(texto_split, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        assert len(blocos) >= 1
        bloco = blocos[0]
        assert bloco["artigo"] == "Art. 1", f"artigo errado: {bloco['artigo']!r}"
        assert bloco["livro"] == "LIVRO I"
        assert bloco["livro_nome"] == "DAS PESSOAS"
        assert bloco["titulo"] == "TÍTULO I"
        assert bloco["titulo_nome"] == "DAS PESSOAS NATURAIS"
        assert bloco["capitulo"] == "CAPÍTULO I"
        assert bloco["capitulo_nome"] == "Da Personalidade e da Capacidade"
        # Path completo na ordem certa
        path = bloco["path_hierarquico"]
        parts = path.split(" > ")
        labels = [p.split(" — ")[0] for p in parts]
        assert labels == ["LIVRO I", "TÍTULO I", "CAPÍTULO I"], f"path: {path!r}"
        assert "DAS PESSOAS" in path
        assert "DAS PESSOAS NATURAIS" in path
        assert "Da Personalidade e da Capacidade" in path

    def test_path_hierarquico_inclui_livro_e_subtitulo(self):
        """PL-13 Bug B: path_hierarquico deve incluir livro e subtitulo na ordem correta (sub-bloco 2b)."""
        texto = (
            "LIVRO I\n"
            "Das Pessoas\n"
            "TÍTULO I\n"
            "Das Pessoas Naturais\n"
            "SUBTÍTULO I\n"
            "Disposições Preliminares\n"
            "CAPÍTULO I\n"
            "Da Personalidade\n"
            "Art. 1° Toda pessoa é capaz de direitos e deveres na ordem civil, "
            "e tem personalidade desde o nascimento com vida.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Test", "http://test", "2026-01-01", {})
        bloco = blocos[0]
        path = bloco["path_hierarquico"]
        # Path deve quebrar em 4 partes na ordem: LIVRO > TITULO > SUBTITULO > CAPITULO
        parts = path.split(" > ")
        labels = [p.split(" — ")[0] for p in parts]
        assert labels == ["LIVRO I", "TÍTULO I", "SUBTÍTULO I", "CAPÍTULO I"], (
            f"path errado: {path!r}"
        )
        assert "Das Pessoas" in path
        assert "Das Pessoas Naturais" in path
        assert "Disposições Preliminares" in path
        assert "Da Personalidade" in path


# ═══════════════════════════════════════════════════════════════════════════════
# Fixes 2026-04-08 — bugs descobertos na auditoria pre-liberacao
# ═══════════════════════════════════════════════════════════════════════════════

from extrair_leis import limpar_marker_hierarquia


class TestParserFixes20260408:
    """Regressao guard pros 4 fixes do parser feitos em 2026-04-08:
    1. INLINE_HEADER_RE aceita markers entre numeral e nome (LGPD CAP IX)
    2. is_nome_secao/permissivo strip markers antes do length check (CF88 TIT IX)
    3. limpar_marker_hierarquia strip trailing smart-quotes
    4. titulo_nome em overrides_pos_extracao (defesa em profundidade)
    """

    def test_inline_header_aceita_marker_entre_numeral_e_nome(self):
        """Bug LGPD CAPÍTULO IX: linha tinha marker (Redação dada...) entre
        o numeral e o nome do capitulo. Antes do fix, o split nao acontecia
        e o capitulo inteiro era perdido."""
        entrada = "CAPÍTULO IX (Redação dada pela Lei nº 15.352, de 2026) DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS"
        out = split_inline_headers(entrada)
        # Deve splittar em 2 linhas, mantendo o marker junto com o nome (linha 2)
        assert "\n" in out, f"split nao aconteceu: {out!r}"
        linhas = out.split("\n")
        assert linhas[0] == "CAPÍTULO IX"
        assert "(Redação dada pela Lei nº 15.352, de 2026)" in linhas[1]
        assert "DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS" in linhas[1]

    def test_inline_header_multiplos_markers(self):
        """Edge case: header com 2 markers consecutivos."""
        entrada = "CAPÍTULO V (Vide Lei nº 9.999) (Incluído pela Lei nº 8.888) Das Disposições"
        out = split_inline_headers(entrada)
        assert out.startswith("CAPÍTULO V\n")
        assert "(Vide Lei nº 9.999)" in out
        assert "(Incluído pela Lei nº 8.888)" in out
        assert "Das Disposições" in out

    def test_inline_header_sem_marker_continua_funcionando(self):
        """Regressao: o caso simples (sem markers) ainda deve funcionar igual."""
        assert (
            split_inline_headers("CAPÍTULO I Da Personalidade")
            == "CAPÍTULO I\nDa Personalidade"
        )

    def test_extrair_estrutura_recupera_capitulo_com_marker_inline(self):
        """Integration: confirma que o fluxo completo (split + extrair_estrutura)
        recupera capitulo_nome quando o input tem marker entre numeral e nome.
        Bug real do LGPD CAPÍTULO IX."""
        texto = (
            "CAPÍTULO IX (Redação dada pela Lei nº 15.352, de 2026) DA AGÊNCIA NACIONAL\n"
            "Art. 55-A. Fica criada a Agência Nacional de Proteção de Dados.\n"
        )
        # Simula o pipeline: split inline → extrair_estrutura
        texto_split = split_inline_headers(texto)
        blocos = extrair_estrutura(texto_split, "TEST", "Lei Teste", "http://test", "2026-04-08", config={})
        assert len(blocos) >= 1
        bloco = blocos[0]
        assert bloco["capitulo"] == "CAPÍTULO IX", f"capitulo errado: {bloco['capitulo']!r}"
        assert "AGÊNCIA NACIONAL" in bloco["capitulo_nome"], (
            f"capitulo_nome nao capturado: {bloco['capitulo_nome']!r}"
        )

    def test_is_nome_permissivo_aceita_linha_longa_apos_strip_markers(self):
        """Bug CF88 TÍTULO IX: linha "Das Disposições Constitucionais Gerais"
        seguida de 4x marker (Revogado pela EC nº 28...) repetidos — total
        > 200 chars. Antes do fix, o length check rejeitava a linha.

        Usa Art. 1 + Art. 2 (sequencia normal) pra evitar que o parser
        classifique como citacao por salto numerico."""
        texto = (
            "TÍTULO IX\n"
            "Das Disposições Constitucionais Gerais (Revogado pela Emenda Constitucional nº 28, de 25/05/2000) (Revogado pela Emenda Constitucional nº 28, de 25/05/2000) (Revogado pela Emenda Constitucional nº 28, de 25/05/2000) (Revogado pela Emenda Constitucional nº 28, de 25/05/2000)\n"
            "Art. 1° Disposicao primeira do titulo IX.\n"
            "Art. 2° Disposicao segunda do titulo IX.\n"
        )
        blocos = extrair_estrutura(texto, "TEST", "Lei Teste", "http://test", "2026-04-08", config={})
        assert len(blocos) >= 1, f"esperava ao menos 1 bloco, recebi {len(blocos)}"
        bloco = blocos[0]
        assert bloco["titulo"] == "TÍTULO IX", f"titulo errado: {bloco['titulo']!r}"
        assert bloco["titulo_nome"] == "Das Disposições Constitucionais Gerais", (
            f"titulo_nome errado: {bloco['titulo_nome']!r}"
        )

    def test_limpar_marker_strip_trailing_smart_quote(self):
        """Bug LGPD CAP IX: nome terminava com smart quote U+2019."""
        entrada = "DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS\u2019"
        assert limpar_marker_hierarquia(entrada) == "DA AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS"

    def test_limpar_marker_strip_trailing_aspas_normais(self):
        entrada = 'Nome Do Capitulo"'
        assert limpar_marker_hierarquia(entrada) == "Nome Do Capitulo"

    def test_limpar_marker_strip_multiplas_aspas(self):
        entrada = "Nome\u2019\u2018'\""
        assert limpar_marker_hierarquia(entrada) == "Nome"

    def test_limpar_marker_preserva_aspas_meio_do_nome(self):
        """Aspas no meio do nome NAO devem ser removidas, so trailing."""
        entrada = "Disposições \"Especiais\" do Código"
        out = limpar_marker_hierarquia(entrada)
        # Aspas no meio sao preservadas
        assert "Especiais" in out

    def test_limpar_marker_remove_marker_e_smart_quote(self):
        """Caso real LGPD: nome com marker no meio E smart quote no fim."""
        entrada = "(Redação dada pela Lei nº 15.352, de 2026) DA AGÊNCIA NACIONAL\u2019"
        out = limpar_marker_hierarquia(entrada)
        assert out == "DA AGÊNCIA NACIONAL"

    def test_titulo_nome_override_aplicado(self):
        """Defesa em profundidade: confirma que titulo_nome em
        overrides_pos_extracao funciona quando o parser nao captura
        o nome (caso real CF88 TÍTULO IX antes do fix do parser)."""
        import os, json, tempfile, shutil
        # Cria diretorio temporario com extrair_leis copiado pra simular
        # known_issues isolado
        # Mais simples: importa o ki do projeto e verifica que CF88 TÍTULO IX
        # tem override registrado
        ki_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "known_issues.json"
        )
        with open(ki_path, encoding='utf-8') as f:
            ki = json.load(f)
        ovr = ki.get("overrides_pos_extracao", {}).get("titulo_nome", {})
        assert "CF88" in ovr, "override titulo_nome.CF88 ausente"
        assert "TÍTULO IX" in ovr["CF88"], "override TÍTULO IX ausente"
        assert "Disposições Constitucionais Gerais" in ovr["CF88"]["TÍTULO IX"]


class TestNotasLegaisOverride:
    """Override de notas_legais (introduzido 2026-04-08 pra CLT 554-575
    nao recepcionados pela CF88). Confirma que o parser injeta as notas
    sem alterar texto_limpo nem status do artigo."""

    def test_known_issues_tem_clt_nao_recepcionados(self):
        """Confirma que known_issues.json tem as 5 entradas pra CLT."""
        import os, json
        ki_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "known_issues.json"
        )
        with open(ki_path, encoding='utf-8') as f:
            ki = json.load(f)
        notas = ki.get("overrides_pos_extracao", {}).get("notas_legais", {}).get("CLT", {})
        for art in ["Art. 554", "Art. 555", "Art. 571", "Art. 572", "Art. 575"]:
            assert art in notas, f"{art} ausente em notas_legais override CLT"
            assert len(notas[art]) >= 1
            assert notas[art][0]["tipo"] == "nao_recepcionado_cf88"
            assert "CF88" in notas[art][0]["referencia"]

    def test_clt_extracted_tem_notas_legais_nao_recepcionado(self):
        """Confirma que apos a re-extracao da CLT, os 5 artigos tem
        a nota injetada via override pos-extracao."""
        import os, json, glob
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data"
        )
        clt_files = sorted(glob.glob(os.path.join(data_dir, "clt_*.json")))
        if not clt_files:
            import pytest
            pytest.skip("CLT JSON nao extraido — pular teste")
        # Pega o mais recente
        with open(clt_files[-1], encoding='utf-8') as f:
            chunks = json.load(f)
        for art_alvo in ["Art. 554", "Art. 555", "Art. 571", "Art. 572", "Art. 575"]:
            matches = [c for c in chunks if c.get("artigo") == art_alvo]
            assert matches, f"{art_alvo} nao encontrado no CLT extraido"
            c = matches[0]
            notas = c.get("notas_legais", []) or []
            tipos = [n.get("tipo") for n in notas]
            assert "nao_recepcionado_cf88" in tipos, (
                f"{art_alvo}: nota nao_recepcionado_cf88 ausente. Notas: {tipos}"
            )
            # Confirma que status nao mudou (ainda vigente conforme Planalto)
            assert c.get("status") == "vigente", (
                f"{art_alvo}: status mudou de vigente — esperado preservar texto original"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# decode_utf16 — regressao LMP (2026-07): Planalto passou a servir UTF-16BE SEM BOM.
# from_encoding="utf-16" sem BOM assumia Little-Endian -> embaralhava os bytes, o texto
# virava lixo/NUL e o parser nao achava nenhum "Art." (tudo caia como EMENTA).
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecodeUtf16:
    _HTML = "<html><body>Dispõe sobre. Art. 1 Primeiro. Art. 2 Notificação.</body></html>"

    def test_be_sem_bom_recupera_texto(self):
        # Caso exato de julho: UTF-16 Big-Endian, sem BOM (byte alto 0x00 primeiro).
        raw = self._HTML.encode("utf-16-be")
        assert raw[:1] == b"\x00"           # sanidade: e mesmo BE sem BOM
        out = decode_utf16(raw)
        assert "\x00" not in out            # sem NUL residual
        assert "Art. 1" in out and "Art. 2" in out
        assert "Dispõe" in out and "Notificação" in out

    def test_le_sem_bom_recupera_texto(self):
        raw = self._HTML.encode("utf-16-le")
        assert raw[:1] != b"\x00"
        out = decode_utf16(raw)
        assert "\x00" not in out
        assert "Art. 1" in out and "Notificação" in out

    def test_com_bom_le_remove_bom(self):
        raw = self._HTML.encode("utf-16")   # inclui BOM (LE nesta plataforma)
        assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")
        out = decode_utf16(raw)
        assert out[:1] != chr(0xFEFF)          # BOM removido do inicio
        assert "Art. 1" in out

    def test_com_bom_be_remove_bom(self):
        raw = b"\xfe\xff" + self._HTML.encode("utf-16-be")  # BOM BE explicito
        out = decode_utf16(raw)
        assert out[:1] != chr(0xFEFF)
        assert "Art. 1" in out and "Dispõe" in out

    def test_stream_truncado_nao_explode(self):
        # Planalto as vezes manda o UTF-16 truncado (numero impar de bytes). O decode
        # estrito explodiria ('truncated data'); errors='replace' recupera o texto.
        raw = b"\xff\xfe" + self._HTML.encode("utf-16-le") + b"\x20"  # 1 byte extra -> impar
        assert len(raw) % 2 == 1
        out = decode_utf16(raw)  # nao deve levantar UnicodeDecodeError
        assert "Art. 1" in out and "Art. 2" in out
        assert "Notificação" in out and "\x00" not in out
        assert chr(0xFFFD) not in out  # byte truncado descartado, sem char de substituicao


# ═══════════════════════════════════════════════════════════════════════════════
# strip_padding_tail — cauda de padding corrompido (regressao LMP Art. 46: 779x U+2020)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStripPaddingTail:
    def test_remove_cauda_de_simbolos(self):
        txt = "Este texto nao substitui o publicado no DOU de 8.8.2006 * " + chr(0x2020) * 779 + chr(0xFFFD)
        out = strip_padding_tail(txt)
        assert chr(0x2020) not in out and chr(0xFFFD) not in out
        assert out.endswith("8.8.2006 *")   # conteudo real (footnote *) preservado

    def test_preserva_texto_normal(self):
        t = "Art. 1 O consumidor tem direito à informação adequada."
        assert strip_padding_tail(t) == t

    def test_preserva_dot_leader_no_meio(self):
        # dot leaders de tabela (CLT/CPC) sao legitimos e ficam no MEIO, nao no fim
        t = "Contribuicao: item ..................... valor final devido"
        assert strip_padding_tail(t) == t

    def test_noop_com_pontuacao_curta_no_fim(self):
        assert strip_padding_tail("continua a leitura ...") == "continua a leitura ..."


# ═══════════════════════════════════════════════════════════════════════════════
# reparar_dispositivos_orfaos — bug CF88 Art. 7º XXVIII/XXIX (rótulo sem conteúdo)
# M1: revogado/vetado só-anotação -> preserva LITERAL do Planalto
# M2: resíduo de <strike> (rótulo nu, sem anotação) -> dropa
# M3: xref quebrada ("...art. 165," + "§ 9º. (...)") -> re-junta
# NUNCA tocar dot-leaders ("I - ...") = elisão legislativa real (LC123/LMP)
# ═══════════════════════════════════════════════════════════════════════════════

from bs4 import BeautifulSoup

from extrair_leis import (
    reparar_dispositivos_orfaos,
    _e_rotulo_vazio,
    _merge_xref_continuation,
)


class TestERotuloVazio:
    def test_alinea_vazia(self):
        assert _e_rotulo_vazio("a)")
        assert _e_rotulo_vazio("b)")

    def test_inciso_vazio(self):
        assert _e_rotulo_vazio("I -")
        assert _e_rotulo_vazio("XXIX -")

    def test_paragrafo_vazio(self):
        assert _e_rotulo_vazio("§ 2º")
        assert _e_rotulo_vazio("§ 9º.")
        assert _e_rotulo_vazio("§ 1º -")

    def test_paragrafo_unico_vazio(self):
        assert _e_rotulo_vazio("Parágrafo único")
        assert _e_rotulo_vazio("Parágrafo único -")

    def test_com_conteudo_nao_e_vazio(self):
        assert not _e_rotulo_vazio("a) alguma coisa")
        assert not _e_rotulo_vazio("I - a proteção da vida")
        assert not _e_rotulo_vazio("§ 1º É vedada a transferência")

    def test_dot_leaders_nao_e_vazio(self):
        """CRÍTICO: rótulo + dot-leaders (elisão legislativa) NÃO é rótulo vazio."""
        assert not _e_rotulo_vazio("I - ..............................")
        assert not _e_rotulo_vazio("II - ........... ...........")


class TestReparoM1PreservaLiteral:
    """M1: dispositivo revogado cujo único conteúdo é a anotação -> LITERAL do Planalto,
    nunca paráfrase (decisão do dev 2026-07-02; ver known_issues.json)."""

    def test_art7_xxix_alineas_preservam_literal(self):
        # Texto REAL do clean.txt do CF88 (Art. 7º XXIX + alíneas revogadas por EC28)
        raw = (
            "XXIX - ação, quanto aos créditos resultantes das relações de trabalho, "
            "com prazo prescricional de cinco anos para os trabalhadores urbanos e rurais, "
            "até o limite de dois anos após a extinção do contrato de trabalho; "
            "(Redação dada pela Emenda Constitucional nº 28, de 2000)\n"
            "a) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)\n"
            "b) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)\n"
            "XXX - proibição de diferença de salários, de exercício de funções e de "
            "critério de admissão por motivo de sexo, idade, cor ou estado civil;"
        )
        out = reparar_dispositivos_orfaos(raw)
        # Alíneas preservadas LITERAIS (não viram "a)"/"b)" nus)
        assert "a) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)" in out
        assert "b) (Revogada). (Redação dada pela Emenda Constitucional nº 28, de 2000)" in out
        # Nenhum rótulo nu remanescente
        linhas = [l.strip() for l in out.split("\n")]
        assert "a)" not in linhas and "b)" not in linhas

    def test_clt_art16_incisos_revogados_preservam_literal(self):
        raw = (
            "Art. 16.  A CTPS terá como identificação única do empregado o número de "
            "inscrição no Cadastro de Pessoas Físicas (CPF). (Redação dada pela Lei nº 13.874, de 2019)\n"
            "I - (revogado); (Redação dada pela Lei nº 13.874, de 2019)\n"
            "II - (revogado); (Redação dada pela Lei nº 13.874, de 2019)\n"
            "Parágrafo único. (Revogado). (Redação dada pela Lei nº 13.874, de 2019)"
        )
        out = reparar_dispositivos_orfaos(raw)
        assert "I - (revogado);" in out
        assert "II - (revogado);" in out
        assert "Parágrafo único. (Revogado)." in out
        # e NÃO sobra rótulo nu
        linhas = [l.strip() for l in out.split("\n")]
        assert "I -" not in linhas and "II -" not in linhas


class TestReparoM1CaputRevogado:
    """M1-CAPUT (2026-07-06): caput de artigo revogado cujo único conteúdo é a
    anotação -> LITERAL do Planalto preservado (família caput_revogado_nu, 261
    artigos; ver known_issues.json). Caput NUNCA é dropado (M2 não se aplica)."""

    def test_caput_revogado_preserva_anotacao_literal(self):
        # Texto REAL do clean.txt da CLT (Art. 384, revogado pela Reforma Trabalhista)
        raw = (
            "Art. 383 - Durante a jornada de trabalho, será concedido à empregada um "
            "período de descanso não inferior a 1 (uma) hora nem superior a 2 (duas) horas.\n"
            "Art. 384 - (Revogado pela Lei nº 13.467, de 2017)\n"
            "Art. 385 - O descanso semanal será de 24 (vinte e quatro) horas consecutivas."
        )
        out = reparar_dispositivos_orfaos(raw)
        assert "Art. 384 - (Revogado pela Lei nº 13.467, de 2017)" in out
        linhas = [l.strip() for l in out.split("\n")]
        assert "Art. 384 -" not in linhas          # caput nu não sobra
        assert any(l.startswith("Art. 383") for l in linhas)   # vizinhos intactos
        assert any(l.startswith("Art. 385") for l in linhas)

    def test_caput_sem_anotacao_fica_como_esta(self):
        # Caput JÁ nu no bruto (sem anotação nenhuma): nada a preservar, nada a dropar.
        raw = (
            "Art. 100\n"
            "Art. 101 - Texto vigente normal do artigo seguinte."
        )
        out = reparar_dispositivos_orfaos(raw)
        linhas = [l.strip() for l in out.split("\n")]
        assert "Art. 100" in linhas                 # caput continua existindo
        assert any(l.startswith("Art. 101") for l in linhas)

    def test_caput_range_revogacao_em_bloco(self):
        # CC "Art. 1.620. a 1.629." — revogação em bloco pela Lei 12.010/2009
        raw = "Art. 1.620. a 1.629. (Revogados pela Lei nº 12.010, de 2009)"
        out = reparar_dispositivos_orfaos(raw)
        assert "(Revogados pela Lei nº 12.010, de 2009)" in out

    def test_caput_vigente_com_anotacao_no_meio_nao_vira_literal(self):
        # Artigo vigente: anotação removida normalmente, conteúdo fica.
        raw = ("Art. 59.  A duração diária do trabalho poderá ser acrescida de horas "
               "extras. (Redação dada pela Lei nº 13.467, de 2017)")
        out = reparar_dispositivos_orfaos(raw)
        assert "(Redação dada" not in out
        assert "horas extras" in out.lower()

    def test_caput_dot_leaders_de_elisao_intocado(self):
        # Elisão legislativa em bloco de emenda (LC123/LMP): NUNCA tratar como nu.
        raw = "Art. 2º ..............................."
        out = reparar_dispositivos_orfaos(raw)
        assert out.strip() == raw.strip()


class TestNoisePreservaQuebraDeLinha:
    """Bug A (2026-07-07, LC123 Art. 17): sufixo de NOISE_PATTERN consumia o '\\n'
    apos a anotacao nua, colando o rotulo orfao na linha seguinte — a linha mesclada
    ('I - II - III - ...') nao e mais rotulo nu e o M1 descartava os literais em
    silencio. Os padroes de ruido NUNCA podem consumir quebra de linha."""

    def test_bloco_de_incisos_revogados_preserva_literais(self):
        # Trecho REAL do clean.txt da LC123 (Art. 17: 26 incisos revogados em bloco)
        raw = (
            "§ 1 As vedações relativas a exercício de atividades previstas no caput.\n"
            "I - (REVOGADO)\n"
            "II - (REVOGADO)\n"
            "III - (REVOGADO)\n"
            "XXII - (VETADO);\n"
            "XXIII - (REVOGADO)\n"
            "XXVIII - (VETADO).\n"
            "§ 2 o Também poderá optar pelo Simples Nacional."
        )
        out = reparar_dispositivos_orfaos(raw)
        linhas = [l.strip() for l in out.split("\n")]
        assert "I - (REVOGADO)" in linhas
        assert "II - (REVOGADO)" in linhas
        assert "III - (REVOGADO)" in linhas
        assert "XXIII - (REVOGADO)" in linhas
        assert "XXII - (VETADO);" in linhas          # veto fica intacto
        # nenhuma linha com rotulos mesclados
        assert not any(re.search(r'(?:\b[IVXL]{1,6} - ){2,}', l) for l in linhas)

    def test_vigencia_standalone_nao_cola_linhas(self):
        raw = ("Art. 10. Texto do artigo.\n"
               "Vigência\n"
               "Parágrafo único. Continuação normal.")
        out = limpar_ruido_legislativo(raw)
        linhas = [l.strip() for l in out.split("\n")]
        assert "Art. 10. Texto do artigo." in linhas
        assert any(l.startswith("Parágrafo único.") for l in linhas)
        assert not any("artigo. Parágrafo" in l for l in linhas)   # nao mesclou


class TestNoiseProducaoDeEfeito:
    """Bug B (2026-07-07): marker 'Produção de efeito' SEM parenteses (padrao
    LC 155/2016) vazava pro texto_limpo — 218 ocorrencias na base."""

    def test_marker_no_fim_da_linha_removido(self):
        raw = ("§ 1 o -B. Os percentuais efetivos de cada tributo serão calculados. "
               "(Incluído pela Lei Complementar nº 155, de 2016)      Produção de efeito\n"
               "I - o percentual efetivo máximo destinado ao ISS será de 5%;")
        out = limpar_ruido_legislativo(raw)
        assert "Produção de efeito" not in out
        assert "percentuais efetivos" in out
        assert "ISS" in out

    def test_frase_normativa_com_produzira_efeitos_intacta(self):
        # Texto normativo legitimo (verbo no meio da frase) nao pode ser tocado.
        raw = "Art. 5. A decisão produzirá efeitos a partir da publicação."
        assert limpar_ruido_legislativo(raw) == raw


class TestReparoM2DropaOrfao:
    """M2: rótulo exatamente vazio (resíduo de <strike>) -> removido."""

    def test_art7_xxviii_orfaos_removidos(self):
        # No clean.txt real, "a)"/"b)" nus aparecem após XXVIII (redação antiga riscada)
        raw = (
            "XXVIII - seguro contra acidentes de trabalho, a cargo do empregador, sem "
            "excluir a indenização a que este está obrigado, quando incorrer em dolo ou culpa;\n"
            "a)\n"
            "b)\n"
            "XXIX - ação, quanto aos créditos resultantes das relações de trabalho, com "
            "prazo prescricional de cinco anos para os trabalhadores urbanos e rurais."
        )
        out = reparar_dispositivos_orfaos(raw)
        linhas = [l.strip() for l in out.split("\n")]
        assert "a)" not in linhas and "b)" not in linhas
        # o conteúdo real (incisos) permanece
        assert any(l.startswith("XXVIII - seguro contra acidentes") for l in linhas)
        assert any(l.startswith("XXIX - ação") for l in linhas)


class TestReparoM2NegativoDotLeaders:
    """PERMANENTE: blocos de emenda com dot-leaders (elisão legislativa real) passam
    INTACTOS pelo reparo. Trava contra alguém 'limpar' isso no futuro (LC123/LMP)."""

    def test_lmp_emenda_cp61_dot_leaders_intactos(self):
        raw = (
            "“Art. 61. .................................................. .........\n"
            "II - ............................................................ .........\n"
            "f) com abuso de autoridade ou prevalecendo-se de relações domésticas, "
            "de coabitação ou de hospitalidade;"
        )
        out = reparar_dispositivos_orfaos(raw)
        # A linha "II - ......" NÃO pode ser removida nem alterada
        assert any(l.strip().startswith("II -") and "...." in l for l in out.split("\n"))

    def test_lc123_dot_leaders_intactos(self):
        raw = (
            "§ 2 o do art. 21 da Lei n o 8.212, de 24 de julho de 1991 . ..........\n"
            "I - .................................................................. ......\n"
            "c) aposentadoria por tempo de contribuição; ..........."
        )
        out = reparar_dispositivos_orfaos(raw)
        assert any(l.strip().startswith("I -") and "...." in l for l in out.split("\n"))


class TestReparoM3XrefMerge:
    """M3: referência cruzada quebrada em duas linhas -> re-juntada (não é dispositivo)."""

    def test_art168_xref_paragrafo_rejuntada(self):
        raw = (
            "Art. 168. Os recursos correspondentes às dotações orçamentárias, "
            "destinados aos órgãos dos Poderes Legislativo e Judiciário, do Ministério "
            "Público e da Defensoria Pública, ser-lhes-ão entregues até o dia 20 de cada "
            "mês, em duodécimos, na forma da lei complementar a que se refere o art. 165,\n"
            "§ 9º. (Redação dada pela Emenda Constitucional nº 45, de 2004)\n"
            "§ 1º É vedada a transferência a fundos de recursos financeiros oriundos de "
            "repasses duodecimais. (Incluído pela Emenda Constitucional nº 109, de 2021)"
        )
        out = reparar_dispositivos_orfaos(raw)
        # xref re-juntada ao caput ("art. 165, § 9º.") — não sobra "§ 9º." isolado
        assert "art. 165, § 9º." in out
        assert "§ 9º." not in [l.strip() for l in out.split("\n")]
        # o § 1º REAL permanece como dispositivo
        assert any(l.strip().startswith("§ 1º É vedada") for l in out.split("\n"))

    def test_nao_junta_paragrafo_normal(self):
        """Não deve juntar um § que segue fim de frase normal (ponto/dois-pontos)."""
        raw = (
            "Art. 5º Todos são iguais perante a lei, sem distinção de qualquer natureza.\n"
            "§ 1º As normas definidoras dos direitos e garantias fundamentais têm "
            "aplicação imediata."
        )
        out = reparar_dispositivos_orfaos(raw)
        linhas = out.split("\n")
        assert any(l.strip().startswith("§ 1º As normas") for l in linhas)
        # o caput NÃO absorveu o § 1º
        assert not any("aplicação imediata" in l and l.strip().startswith("Art. 5º") for l in linhas)


class TestReparoNaoAlteraArtigoNormal:
    """Invariante: para artigo SEM dispositivo órfão, reparar == limpar_ruido (nada muda).
    Garante que os ~130 dispositivos afetados são os ÚNICOS que mudam de hash."""

    def test_idempotente_vs_limpar_ruido(self):
        raw = (
            "Art. 6º São direitos básicos do consumidor:\n"
            "I - a proteção da vida, da saúde e da segurança;\n"
            "II - a educação e divulgação sobre o consumo adequado dos produtos e "
            "serviços. (Redação dada pela Lei nº 12.741, de 2012)\n"
            "III - a informação adequada e clara sobre os diferentes produtos."
        )
        assert reparar_dispositivos_orfaos(raw) == limpar_ruido_legislativo(raw)


import extrair_leis as _ex


class TestHtmlStageFixesLc123:
    """Camada 2 (2026-07-07): os 3 mecanismos do HTML do Planalto que corrompiam a
    LC123 (e, em dose menor, CF88/LGPD/CADPOS/CLT/CPC). Snippets REAIS do HTML."""

    def test_kerning_letter_spacing_nao_fatia_palavra(self):
        """Spans de letter-spacing cortam palavras no meio; get_text(separator)
        virava 'v alor d e vido'. Snippet real do caput do Art. 18 da LC123."""
        html = (
            '<p><font size="2"><a name="art18.."></a>'
            'Art. 18. &nbsp;O <span style="letter-spacing:.1pt">v</span>alor '
            'd<span style="letter-spacing:.1pt">e</span>vido'
            '<span style="letter-spacing:1.15pt">\n</span>'
            '<span style="letter-spacing:-.1pt">m</span>ensalmente pela microempresa'
            '</font></p>'
        )
        out = _ex.html_to_clean_text(html.encode("utf-8"), "LC123",
                                     _ex.LEIS_CONFIG["LC123"])
        assert "valor devido mensalmente" in out, f"palavras fatiadas: {out!r}"
        assert "v alor" not in out and "d e vido" not in out

    def test_riscado_via_css_line_through_e_removido(self):
        """Redação antiga riscada via CSS (text-decoration:line-through) tem a MESMA
        semântica do <strike> e deve ser removida igual — era ela que vazava como
        'Art. 18 standalone limpo' (texto SUPERADO servido como vigente no RAG)."""
        html = (
            '<p><span style="text-decoration:line-through"><font size="2">'
            '<a name="art18."></a>Art.&nbsp;18.&nbsp; O valor devido mensalmente pela '
            'microempresa ou empresa de pequeno porte, optante pelo Simples Nacional, '
            'sera determinado mediante aplicacao das aliquotas constantes da tabela'
            '</font></span></p>'
            '<p><font size="2">Art. 19. Texto vigente que deve permanecer no resultado '
            'porque nao esta riscado de forma alguma.</font></p>'
        )
        out = _ex.html_to_clean_text(html.encode("utf-8"), "LC123",
                                     _ex.LEIS_CONFIG["LC123"])
        assert "aliquotas constantes da tabela" not in out, "redacao riscada por CSS vazou"
        assert "Texto vigente que deve permanecer" in out

    def test_strike_tag_continua_removido(self):
        """Regressão: o decompose de <strike> (tag) continua funcionando junto."""
        html = ('<p><strike>Art. 17. Redacao velha em tag strike.</strike></p>'
                '<p>Art. 18. Redacao atual em paragrafo normal.</p>')
        out = _ex.html_to_clean_text(html.encode("utf-8"), "LC123",
                                     _ex.LEIS_CONFIG["LC123"])
        assert "Redacao velha" not in out
        assert "Redacao atual" in out

    @staticmethod
    def _anexo_pats():
        """Compila os boundaries de anexo EXATAMENTE como o engine (flags da config)."""
        cfg = _ex.LEIS_CONFIG["LC123"]
        return [re.compile(b["pattern"], re.IGNORECASE if b.get("ignorecase", True) else 0)
                for b in cfg["boundaries"] if b["action"] == "anexo"]

    def test_boundary_anexo_lc123_casa_header_com_cauda(self):
        """Headers de anexo da LC123 têm cauda ('ANEXO I DA LEI COMPLEMENTAR Nº...')
        e o boundary antigo exigia fim-de-linha após o numeral — nunca casava e as
        tabelas de alíquotas caíam DENTRO do Art. 89."""
        pats = self._anexo_pats()
        assert pats, "LC123 sem boundary de anexo"
        # headers REAIS do clean.txt (o 'Nº' vira 'N o' na extração)
        for header in [
            "ANEXO I DA LEI COMPLEMENTAR N o 123, DE 14 DE DEZEMBRO DE 2006 (Redação dada...)",
            "ANEXO IV DA LEI COMPLEMENTAR N o 123, DE 14 DE DEZEMBRO DE 2006",
        ]:
            assert any(p.match(header) for p in pats), f"não casou header real: {header!r}"

    def test_boundary_anexo_nao_dispara_em_referencia_do_corpo(self):
        """PERMANENTE (bug encontrado na calibração com dado real): o corpo da LC123
        tem 12 linhas iniciando com 'Anexo(s) ... desta Lei Complementar' (referências,
        case misto). Um boundary IGNORECASE dispararia ali e ENGOLIRIA artigos inteiros
        (Art. 28/56/77 caíram dentro de chunks 'ANEXO V')."""
        pats = self._anexo_pats()
        for ref in [
            "Anexos I a V desta Lei Complementar, sobre a base de cálculo",
            "Anexo II desta Lei Complementar. .",
            "Anexo III desta Lei Complementar as seguintes atividades",
            "Anexos I, II, III, IV e V desta Lei Complementar. (Redação dada...)",
            "anexo iv da lei complementar",
        ]:
            assert not any(p.match(ref) for p in pats), f"referência disparou boundary: {ref!r}"

    def test_anexo_vira_chunk_proprio_e_preserva_conteudo_da_linha(self):
        """Com o boundary correto: anexo NÃO fica dentro do último artigo E o conteúdo
        colado na linha do header (efeito do merge) é PRESERVADO no chunk do anexo."""
        texto = (
            "Art. 89. Terao sua vigencia iniciada conforme disposto nesta Lei "
            "Complementar, respeitados os prazos regulamentares aplicaveis.\n"
            "ANEXO I DA LEI COMPLEMENTAR N o 123, DE 14 DE DEZEMBRO DE 2006 "
            "Aliquotas e Partilha do Simples Nacional com receita bruta anual de "
            "1a Faixa ate 180.000,00 4,00%\n"
        )
        cfg = _ex.LEIS_CONFIG["LC123"]
        blocos = _ex.extrair_estrutura(texto, "LC123", "LC 123/2006",
                                       "http://t", "2026-07-07", cfg)
        art89 = next(b for b in blocos if b["artigo"].startswith("Art. 89"))
        assert "Aliquotas e Partilha" not in art89["texto_limpo"], (
            "anexo continua engolido pelo Art. 89"
        )
        anexo = next((b for b in blocos if b["artigo"].startswith("ANEXO I")), None)
        assert anexo is not None, "chunk ANEXO I não foi criado"
        assert "1a Faixa ate 180.000,00" in anexo["texto_limpo"], (
            "conteúdo colado na linha do header foi descartado"
        )


class TestGuardaUpstreamHtmlStrikeReal:
    """Guarda upstream: HTML REAL do Planalto (Art. 7º XXIX, alíneas antigas riscadas).
    O strike.decompose apaga o conteúdo mas o rótulo 'a)'/'b)' vaza -> a guarda M2 dropa."""

    def test_strike_orphan_vaza_e_guarda_dropa(self):
        html = (
            '<p><a name="art7xxixa."></a>a) '
            '<strike>cinco anos para o trabalhador urbano, até o limite de dois anos '
            'após a extinção do contrato;</strike><br/>&nbsp;'
            '<a name="art7xxixb."></a>b) '
            '<strike>até dois anos após a extinção do contrato, para o trabalhador rural;'
            '</strike></p>'
        )
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["s", "del", "strike"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        # documenta o LEAK: rótulos a)/b) sobrevivem ao strike (conteúdo apagado)
        leak = [l.strip() for l in text.split("\n") if l.strip()]
        assert "a)" in leak and "b)" in leak
        # a guarda upstream (M3 merge + M2 drop) remove os rótulos vazios
        reparado = "\n".join(
            l for l in _merge_xref_continuation(text.split("\n")) if not _e_rotulo_vazio(l)
        )
        restantes = [l.strip() for l in reparado.split("\n") if l.strip()]
        assert "a)" not in restantes and "b)" not in restantes
