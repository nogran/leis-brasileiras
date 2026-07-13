# -*- coding: utf-8 -*-
"""Captura de epígrafe (rubrica por artigo) — ver docs/design/epigrafe-capture.md.

Nas leis de heading CAIXA-ALTA COM rubrica marginal (CP/CLT — config `capture_epigrafe`)
a rubrica Title-case de cada artigo vem MAL-ATRIBUÍDA na página do Planalto: colada no fim
do nome do capítulo/seção (1º artigo) ou no fim do texto do artigo ANTERIOR (demais).

Estratégia (decisão do dev, 2026-07-12): PEEK — LER a rubrica pro campo `epigrafe` SEM
remover nada de `texto_limpo`/`capitulo_nome` (zero truncação de dispositivo; o ruído colado
é pré-existente e continua no texto). Fonte = clean_text (uniforme). Cobertura ~94% no CP;
o gap conhecido são rubricas coladas SEM terminador antes (ex: Art. 121-A 'Feminicídio', com
o §7º revogado/vazio) — não capturadas, mas o texto segue íntegro (nada se perde).

CF88 NÃO entra: a Constituição não tem rubrica marginal por artigo (o que parecia rubrica é
header de hierarquia — 'Subseção I ...', 'Dos Princípios Fundamentais').
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import extrair_leis as ex


# ─────────────────────────────────────────────────────────────────────────────
#  _split_heading_rubrica — separa "<HEADER CAIXA-ALTA> <rubrica Title-case>"
# ─────────────────────────────────────────────────────────────────────────────
class TestSplitHeadingRubrica:

    def test_separa_header_de_rubrica(self):
        assert ex._split_heading_rubrica("DAS LESÕES CORPORAIS Lesão corporal") == (
            "DAS LESÕES CORPORAIS", "Lesão corporal")

    def test_rubrica_de_varias_palavras(self):
        assert ex._split_heading_rubrica("DOS CRIMES CONTRA A VIDA Homicídio simples") == (
            "DOS CRIMES CONTRA A VIDA", "Homicídio simples")

    def test_header_puro_sem_rubrica(self):
        assert ex._split_heading_rubrica("DAS LESÕES CORPORAIS") == ("DAS LESÕES CORPORAIS", "")

    def test_nome_title_case_legitimo_nao_e_split(self):
        assert ex._split_heading_rubrica("Da Personalidade e da Capacidade") == (
            "Da Personalidade e da Capacidade", "")

    def test_vazio(self):
        assert ex._split_heading_rubrica("") == ("", "")

    def test_subsecao_grudada_nao_e_split_como_rubrica(self):
        # Falso positivo REAL da CF88: a subseção (nível não modelado) gruda no secao_nome.
        # 'Subseção I ...' é HEADER, não rubrica — o nome fica INTEIRO, sem fabricar epígrafe.
        nome = "DO PROCESSO LEGISLATIVO Subseção I Disposição Geral"
        assert ex._split_heading_rubrica(nome) == (nome, "")
        nome2 = "DO CONSELHO DA REPÚBLICA Subseção I Do Conselho da República"
        assert ex._split_heading_rubrica(nome2) == (nome2, "")

    def test_rubrica_longa_separada_sem_teto_de_tamanho(self):
        # CP Art. 306: rubrica genuína de 113 chars. O split do nome de capítulo NÃO aplica o
        # teto de 80 do is_rubrica_candidate (o sufixo Title-case É estruturalmente a rubrica).
        nome = ("DE OUTRAS FALSIDADES Falsificação do sinal empregado no contraste de "
                "metal precioso ou na fiscalização alfandegária, ou para outros fins")
        header, rub = ex._split_heading_rubrica(nome)
        assert header == "DE OUTRAS FALSIDADES"
        assert rub.startswith("Falsificação do sinal empregado")
        assert len(rub) > 80


# ─────────────────────────────────────────────────────────────────────────────
#  is_rubrica_candidate — Title-case CURTA que precede um `Art. N`
# ─────────────────────────────────────────────────────────────────────────────
class TestIsRubricaCandidate:

    @pytest.mark.parametrize("linha", [
        "Lesão corporal", "Feminicídio", "Furto de coisa comum", "Diminuição de pena",
    ])
    def test_rubricas_validas(self, linha):
        assert ex.is_rubrica_candidate(linha) is True

    @pytest.mark.parametrize("linha", [
        "DAS LESÕES CORPORAIS",                       # CAIXA-ALTA = header
        "Art. 129. Ofender a integridade corporal",   # é artigo
        "§ 1º Se resulta lesão grave",                # dispositivo
        "Pena - detenção, de 3 meses a 1 ano",        # tem 'Pena' + número
        "Ofender a integridade corporal de outrem.",  # termina em ponto (frase/caput)
        "(Redação dada pela Lei nº 14.994, de 2024)", # marker de alteração
        "Art. 5º",                                    # rótulo de artigo
        "Subseção I Disposição Geral",                # header de hierarquia (subseção)
        "Seção II Do Trabalho Noturno",               # header de hierarquia (seção)
        "Título III Das Garantias",                   # header de hierarquia (título)
        "",                                           # vazio
    ])
    def test_nao_rubricas(self, linha):
        assert ex.is_rubrica_candidate(linha) is False

    def test_pena_no_meio_da_rubrica_nao_rejeita(self):
        # 'pena' só rejeita ANCORADA no início ('Pena - ...'); no meio é rubrica legítima.
        assert ex.is_rubrica_candidate("Diminuição de pena") is True
        assert ex.is_rubrica_candidate("Penas restritivas de direitos") is True


# ─────────────────────────────────────────────────────────────────────────────
#  _extract_trailing_rubrica — PEEK do rabo colado no fim da linha (não remove)
# ─────────────────────────────────────────────────────────────────────────────
class TestExtractTrailingRubrica:

    def test_linha_inteira_e_rubrica(self):
        assert ex._extract_trailing_rubrica("Disposições comuns") == "Disposições comuns"

    def test_rabo_apos_ponto_final(self):
        linha = ("§ 9º A pena é de reclusão ... previstas no art. 2º da lei que institui o "
                 "marco legal do combate ao crime organizado no Brasil.  Furto de coisa comum")
        assert ex._extract_trailing_rubrica(linha) == "Furto de coisa comum"

    def test_rabo_apos_fecho_de_marcador(self):
        linha = ("Art. 1 º - Não há crime sem lei anterior que o defina. (Redação dada pela "
                 "Lei nº 7.209, de 11.7.1984) Lei penal no tempo")
        assert ex._extract_trailing_rubrica(linha) == "Lei penal no tempo"

    @pytest.mark.parametrize("linha", [
        "Pena - reclusão, de 2 (dois) a 5 (cinco) anos.",   # termina em ponto, sem rabo
        "§ 2º Aplica-se o disposto no art. 121 deste Código.",
        "...nos termos da Lei nº 8.666, de 1993.  Lei 8.112",  # rabo com dígito -> não rubrica
        "...conforme o disposto adiante.  Seção II",          # rabo = header de hierarquia
        "",
    ])
    def test_sem_rubrica_no_fim(self, linha):
        assert ex._extract_trailing_rubrica(linha) == ""

    def test_rabo_sem_terminador_nao_e_pego_gap_conhecido(self):
        # Limitação documentada: '§ 7º Feminicídio' (com o § revogado/vazio) não tem
        # terminador antes da rubrica -> NÃO capturado (mas o texto segue íntegro).
        assert ex._extract_trailing_rubrica("§ 7 o  Feminicídio") == ""


# ─────────────────────────────────────────────────────────────────────────────
#  Integração: extrair_estrutura com capture_epigrafe — captura SEM truncar
# ─────────────────────────────────────────────────────────────────────────────
_CFG_ON = {"versao": "Decreto-Lei nº 2.848, de 1940", "url": "http://t",
           "nome_base": "cp", "capture_epigrafe": True}
_CFG_OFF = {"versao": "Lei nº 10.406, de 2002", "url": "http://t", "nome_base": "cc"}

# Mimetiza o clean_text: nome do capítulo COM a rubrica do 1º artigo colada; rubrica dos
# demais artigos colada como fim de linha antes do `Art. N` seguinte.
_TEXTO_CP = "\n".join([
    "CAPÍTULO II",
    "DAS LESÕES CORPORAIS Lesão corporal",
    "Art. 129. Ofender a integridade corporal ou a saúde de outrem, causando dano.",
    "Diminuição de pena",
    "§ 4º Se o agente comete o crime impelido por motivo de relevante valor moral.",
    "Homicídio simples",
    "Art. 121. Matar alguém, ceifando a vida de outra pessoa dolosamente aqui.",
    "Feminicídio",
    "Art. 121-A. Matar mulher por razões da condição do sexo feminino, com dolo.",
])


def _extrair(texto, cfg):
    blocos = ex.extrair_estrutura(texto, "TEST", cfg["versao"], cfg["url"], "2026-07-12", cfg)
    return {b["artigo"]: b for b in blocos}


class TestEpigrafeExtraction:

    def test_rubrica_do_primeiro_artigo_vem_do_nome_do_capitulo(self):
        b = _extrair(_TEXTO_CP, _CFG_ON)
        assert b["Art. 129"]["epigrafe"] == "Lesão corporal"

    def test_rubrica_dos_demais_artigos_vem_do_fim_do_texto_anterior(self):
        b = _extrair(_TEXTO_CP, _CFG_ON)
        assert b["Art. 121"]["epigrafe"] == "Homicídio simples"
        assert b["Art. 121-A"]["epigrafe"] == "Feminicídio"

    def test_PEEK_nao_trunca_nem_o_texto_nem_o_nome_do_capitulo(self):
        # Invariante central da abordagem escolhida: capturar a rubrica NÃO remove nada.
        b = _extrair(_TEXTO_CP, _CFG_ON)
        # nome do capítulo continua com a rubrica colada (não foi cortado)
        assert "Lesão corporal" in b["Art. 129"]["capitulo_nome"]
        # o texto do artigo anterior continua com a rubrica do próximo colada no fim
        assert "Homicídio simples" in b["Art. 129"]["texto_limpo"]
        assert "Feminicídio" in b["Art. 121"]["texto_limpo"]

    def test_sub_rubrica_dentro_do_artigo_permanece_no_texto(self):
        # 'Diminuição de pena' precede um `§`, não um `Art. N` — sub-rubrica interna, fica
        # no texto e NÃO vira epígrafe (só o rabo, última linha do buffer, é lido).
        b = _extrair(_TEXTO_CP, _CFG_ON)
        assert "Diminuição de pena" in b["Art. 129"]["texto_limpo"]
        assert b["Art. 129"]["epigrafe"] == "Lesão corporal"

    def test_lei_sem_capture_epigrafe_nao_ganha_o_campo(self):
        # Sem capture_epigrafe, o campo é OMITIDO (não "" ) — o JSON dessas leis fica
        # byte-idêntico ao anterior; a ingestão trata a ausência com g("epigrafe", "").
        b = _extrair(_TEXTO_CP, _CFG_OFF)
        for art, bloco in b.items():
            assert "epigrafe" not in bloco, f"{art} não deveria ter o campo epígrafe"
