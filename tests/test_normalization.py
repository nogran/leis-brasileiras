"""Testes da normalizacao deterministica (NFC + colapso de whitespace horizontal).
Test-first: definem o contrato ANTES da implementacao. Regra de ouro: PRESERVAR '\\n'
(estrutura de artigo/paragrafo que o parser usa) — so colapsa espaco/tab horizontais."""
import os
import sys
import unicodedata


from leis_brasileiras.extraction import normalizar_texto


class TestNormalizarTexto:
    def test_nfc_compoe_acento(self):
        # 'e' + acento combinante (NFD) -> 'é' composto (NFC)
        nfd = "café"
        assert unicodedata.normalize("NFD", "café") == nfd   # sanidade do fixture
        assert normalizar_texto(nfd) == "café"
        assert unicodedata.is_normalized("NFC", normalizar_texto(nfd))

    def test_colapsa_espacos_horizontais(self):
        assert normalizar_texto("Art. 1  texto   com    espacos") == "Art. 1 texto com espacos"

    def test_colapsa_tabs(self):
        assert normalizar_texto("a\t\tb") == "a b"

    def test_preserva_newline(self):
        # '\n' e estrutura (o parser separa artigos/paragrafos por linha) -> NAO colapsar
        assert normalizar_texto("Art. 1\ntexto\n§ 1 outro") == "Art. 1\ntexto\n§ 1 outro"

    def test_espaco_antes_de_newline_vira_newline(self):
        # espaco horizontal colapsa; a quebra de linha permanece
        assert normalizar_texto("Art. 1  \ntexto") == "Art. 1\ntexto"

    def test_no_op_em_texto_limpo(self):
        t = "Art. 5 São direitos básicos do consumidor a proteção da vida."
        assert normalizar_texto(t) == t

    def test_preserva_acentos(self):
        assert normalizar_texto("ação e proteção") == "ação e proteção"
