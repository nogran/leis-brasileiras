"""Testes unitários para as funções de parsing do extrair_leis.py."""

import sys
import os
import re

# Adiciona raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from extrair_leis import (
    REGEX_ARTIGO,
    parse_art_num,
    classificar_linha_artigo,
    detectar_status_artigo,
    extrair_alteracoes,
    extrair_referencias,
    limpar_ruido_legislativo,
    split_com_overlap,
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
