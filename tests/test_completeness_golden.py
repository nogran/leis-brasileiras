"""Golden de COMPLETUDE: nenhum texto da página compilada do Planalto pode se perder.

Para cada lei (fixture de HTML cru): TODA linha de texto da página deve estar em
  chunks (texto_limpo)  ∪  metadados (alteracoes/notas/controle/hierarquia)
  ∪  redações riscadas (harvest)  ∪  descartes arquivados (dedup/dup_rotulo)
  ∪  whitelist DELIBERADA (documentada abaixo)
  ∪  resíduo CONHECIDO congelado (KNOWN_RESIDUE, com justificativa individual).

Linha fora disso = perda de dado jurídico = FAIL. Este teste nasceu da auditoria de
2026-07-07 que encontrou, em produção: CF88 Art. 92 sem o inciso I (STF!), Art. 109
sem o V, CC Art. 740 §3 mutilado, CLT férias coletivas (139-146) e LC123 licitações
(43-49) com buracos, SIGNATÁRIOS da CF88 inteiros perdidos, promulgação da CLT
descartada. Cada mecanismo corrigido está travado por teste unitário próprio; este
golden garante que NENHUM mecanismo novo de perda passe despercebido.

Whitelist deliberada (decisões de produto, não perdas):
  WL-A  anotações de emenda/vide — o wrapper literal é removido; a NORMA vira
        metadado estruturado (alteracoes/notas_legais). TestExtrairAlteracoes.
  WL-B  cabeçalho pré-ementa (Presidência/Subchefia/título da página) — navegação,
        não conteúdo legal. A identificação da norma vem de LEIS_CONFIG.versao.
  WL-C  boilerplate institucional ('Este texto não substitui...', 'Brasília, ...').
"""
import gzip
import os
import re
import sys
import unicodedata

import pytest

import extrair_leis as ex

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")

LAWS = {
    "cadastro_positivo": "CADPOS", "cdc": "CDC", "cf88": "CF88", "clt": "CLT",
    "codigo_civil": "CC", "cp": "CP", "cpc": "CPC", "eca": "ECA", "lc123": "LC123",
    "lei_inquilinato": "LI", "lei_maria_penha": "LMP", "lei_terceirizacao": "LT",
    "lgpd": "LGPD",
}

# Resíduo CONHECIDO congelado — cada entrada exige justificativa. Adicionar linha
# aqui SEM investigação = violação do princípio 'nada se perde'.
KNOWN_RESIDUE = {
    "CC": {
        # Conteúdo CAPTURADO, mas repartido entre secao_nome ('Do Penhor Rural
        # Subseção I') e o texto vizinho — o matcher por linha-de-página não
        # enxerga através da fronteira. Zero perda; limitação do comparador.
        "Subseção I Disposições Gerais",
        # Linha do ÍNDICE/sumário do Planalto com nome DESATUALIZADO do título
        # (o corpo usa o nome pós-Lei 13.146: '...E DA TOMADA DE DECISÃO APOIADA').
        # Índice é navegação; o header real do corpo está capturado.
        "TÍTULO IV DA TUTELA E DA CURATELA",
    },
}

_WL_ANOTACAO = re.compile(
    r'^\(?\s*(?:\w+\s+)?(?:dada|Incluíd\w*|Revogad\w*|Acrescentad\w*|Suprimid\w*|'
    r'Restaurad\w*|substituíd\w*|Renumerad\w*|Redação|Nova\s+redação|Vide|Vigência|'
    r'Regulamento|Produção|retificado|Retificad\w*|Expressão)\b.{0,110}$'
    r'|^.{0,30}(?:pela|pelo)\s+(?:Lei|Decreto|Emenda|Medida|Constituição).{0,80}$'
    r'|^.{0,60}n[ºo°]?\s*[\d.]+\s*,?\s*(?:de\s+)?[\d/.]+\s*\)\s*$',
    re.IGNORECASE)
_WL_BOILER = re.compile(
    r'(Este texto não substitui|Presidência da República|Casa Civil|'
    r'Subchefia|Texto compilado|Texto original|Diário Oficial|Brasília,?\s+\d|'
    r'^\*{1,3}$|Emendas Constitucionais de Revisão|Atos decorrentes do disposto)',
    re.IGNORECASE)
_EMENTA_KEY = re.compile(
    r'(Aprova|Institui|Dispõe|Estabelece|Regulamenta|O PRESIDENTE|'
    r'A PRESIDENTA|O CONGRESSO|PREÂMBULO|Faço saber)', re.IGNORECASE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    return re.sub(r'[^0-9a-zà-ÿ]', '', s)


def _fixture_html(base: str) -> bytes:
    with gzip.open(os.path.join(_FIX, "html", f"{base}.htm.gz"), "rb") as f:
        return f.read()


def _page_lines(raw: bytes, config: dict) -> list[str]:
    """Texto INTEGRAL da página: só lixo estrutural removido; riscados e kerning
    normalizados pra comparação (o kerning é desfeito igual ao extrator)."""
    soup = ex._make_soup(raw, config)
    for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                     "meta", "link", "img"]):
        tag.decompose()
    for t in soup.find_all(style=ex._RE_CSS_LETTER_SPACING):
        t.unwrap()
    soup.smooth()
    return [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]


@pytest.mark.parametrize("base", list(LAWS), ids=[LAWS[b] for b in LAWS])
def test_nenhum_texto_da_pagina_se_perde(base):
    sigla = LAWS[base]
    cfg = ex.LEIS_CONFIG[sigla]
    raw = _fixture_html(base)

    clean = ex.html_to_clean_text(raw, sigla, cfg)
    chunks, stats = ex.parse_law(clean, sigla, cfg["versao"], cfg["url"],
                                 "2026-07-07", cfg)

    parts = []
    for c in chunks:
        parts.append(c["texto_limpo"])
        for a in c.get("alteracoes") or []:
            parts.append(a.get("norma", ""))
        for n_ in c.get("notas_legais") or []:
            parts.append(n_.get("raw", ""))
        for cc_ in c.get("controle_constitucionalidade") or []:
            parts.append(cc_.get("raw", ""))
        for num, nome in [("livro", "livro_nome"), ("titulo", "titulo_nome"),
                          ("subtitulo", "subtitulo_nome"),
                          ("capitulo", "capitulo_nome"), ("secao", "secao_nome")]:
            parts.append(f"{c.get(num, '')} {c.get(nome, '')}")
    for items in stats.get("descartes", {}).values():
        for d in items:
            parts.append(d["texto"])
    for r in ex.harvest_redacoes_riscadas(raw, sigla, cfg):
        parts.append(r["texto"])
    hay = _norm(" ".join(parts))

    lines = _page_lines(raw, cfg)
    ementa_ix = next((i for i, l in enumerate(lines) if _EMENTA_KEY.search(l)), 0)
    known = KNOWN_RESIDUE.get(sigla, set())

    residuo = []
    for i, l in enumerate(lines):
        nl = _norm(l)
        if len(nl) < 25 or i < ementa_ix:
            continue
        if _WL_BOILER.search(l) or _WL_ANOTACAO.match(l):
            continue
        if l in known:
            continue
        if nl in hay:
            continue
        residuo.append(l)

    assert not residuo, (
        f"{sigla}: {len(residuo)} linha(s) da página compilada NÃO estão em "
        f"chunks/metadados/riscadas/descartes — PERDA DE DADO JURÍDICO. "
        f"Investigue cada uma antes de qualquer whitelist: {residuo[:5]}"
    )
