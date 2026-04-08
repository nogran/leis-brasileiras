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
