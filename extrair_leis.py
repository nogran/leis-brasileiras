"""
Extrator de leis brasileiras - v6.0 (config-driven)

Arquitetura:
  LEIS_CONFIG  -> config por lei (url, encoding, boundaries)
  Engine       -> parsing generico de artigos, hierarquia, status, vetos
  Boundaries   -> comportamentos especificos declarados na config

Para adicionar uma lei nova: crie entrada em LEIS_CONFIG com url e boundaries.
Para corrigir um bug de parsing: altere o engine - vale para todas as leis.
"""

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
import argparse
import hashlib, re, json, sys, os
import unicodedata

import db

# Versao do parser gravada em raw_captures.parser_version (permite re-parse historico).
PARSER_VERSION = "extrair_leis@3"


# =====================================================================
#  CONFIGURACAO POR LEI
#  Cada lei declara so o que e diferente. O engine cuida do resto.
#
#  Campos opcionais:
#    encoding   - forca encoding (ex: "utf-16" para LMP)
#    boundaries - lista de regras de boundary:
#      pattern    - regex (match no inicio da linha)
#      action     - "transitorias" | "flush_section" | "anexo"
#      condition  - (opcional) "em_transitorias" - so dispara se estiver no ADCT
#      label      - (opcional) label para flush_section
# =====================================================================

LEIS_CONFIG = {
    "CF88": {
        "versao": "Constituição Federal 1988",
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        "nome_base": "cf88",
        "dedup_redacoes": True,
        "boundaries": [
            {
                # Signatários do corpo principal (ANTES do ADCT)
                # Pattern específico com data para não casar "Brasília" em texto de artigo
                "pattern": r"^Brasília\s*,\s*\d+\s+de\s+\w+\s+de\s+\d{4}",
                "action": "flush_section",
                "label": "SIGNATÁRIOS",
            },
            {
                "pattern": r"^ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS",
                "action": "transitorias",
            },
            {
                # Signatários do ADCT (DEPOIS do ADCT)
                "pattern": r"^Brasília\s*,",
                "condition": "em_transitorias",
                "action": "flush_section",
                "label": "SIGNATÁRIOS (ADCT)",
            },
        ],
    },
    "CDC": {
        "versao": "Lei 8.078/1990",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
        "nome_base": "cdc",
        # Headers inline (TÍTULO I Dos Direitos...) sao tratados pelo
        # split_inline_headers do engine (PL-13 sub-bloco 2e).
    },
    "CLT": {
        "versao": "Decreto-Lei 5.452/1943",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm",
        "nome_base": "clt",
        "dedup_redacoes": True,
        "boundaries": [
            {"pattern": r"^ANEXO\b", "action": "anexo"},
        ],
    },
    "CC": {
        "versao": "Lei 10.406/2002",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
        "nome_base": "codigo_civil",
    },
    "CPC": {
        "versao": "Lei 13.105/2015",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/L13105compilada.htm",
        "nome_base": "cpc",
        "dedup_redacoes": True,
    },
    "CP": {
        "versao": "Decreto-Lei 2.848/1940",
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",
        "nome_base": "cp",
    },
    "LGPD": {
        "versao": "Lei 13.709/2018",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm",
        "nome_base": "lgpd",
    },
    "ECA": {
        "versao": "Lei 8.069/1990",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/L8069Compilado.htm",
        "nome_base": "eca",
        "dedup_redacoes": True,
    },
    "LI": {
        "versao": "Lei 8.245/1991",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/L8245compilado.htm",
        "nome_base": "lei_inquilinato",
    },
    "LMP": {
        "versao": "Lei 11.340/2006",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm",
        "nome_base": "lei_maria_penha",
        "encoding": "utf-16",
    },
    "LC123": {
        "versao": "Lei Complementar 123/2006",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm",
        "nome_base": "lc123",
        "dedup_redacoes": True,
        "boundaries": [
            {"pattern": r"^ANEXO(?:\s+[IVXLCDM]+(?:-[A-Z])?|\s+[ÚU]NICO|\s+\d+)?\s*$", "action": "anexo"},
        ],
    },
    "LT": {
        "versao": "Lei 6.019/1974",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l6019compilado.htm",
        "nome_base": "lei_terceirizacao",
        # Lei sem hierarquia interna (sem LIVRO/TÍTULO/CAPÍTULO/SEÇÃO).
        "inline_headers": False,
    },
    "CADPOS": {
        "versao": "Lei 12.414/2011",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12414.htm",
        "nome_base": "cadastro_positivo",
        "dedup_redacoes": True,
        # Lei sem hierarquia interna (sem LIVRO/TÍTULO/CAPÍTULO/SEÇÃO).
        "inline_headers": False,
    },
}


# =====================================================================
#  ENGINE — Funcoes de parsing genericas
# =====================================================================

# --- Alteracoes legislativas ---
ALTERACAO_PATTERNS = [
    (re.compile(r'\(Redação dada (?:pela|pelo|ao)\s+(.+?)\)',       re.IGNORECASE | re.DOTALL), "redacao_dada"),
    (re.compile(r'\(Incluíd[oa]s? (?:pela|pelo|ao)\s+(.+?)\)',     re.IGNORECASE | re.DOTALL), "incluido"),
    (re.compile(r'\(Renumerad[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "renumerado"),
    (re.compile(r'\(Acrescentad[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "acrescentado"),
    (re.compile(r'\(Nova redação\s+(?:pela|pelo|ao)\s+(.+?)\)',     re.IGNORECASE | re.DOTALL), "nova_redacao"),
    # PL-19 B-04: 3 markers que estavam perdidos no texto mas nao eram capturados
    (re.compile(r'\(Suprimid[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)',  re.IGNORECASE | re.DOTALL), "suprimido"),
    (re.compile(r'\(Restaurad[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "restaurado"),
    (re.compile(r'\(Express[ãa]o\s+substitu[ií]d[oa]\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "expressao_substituida"),
]

def extrair_alteracoes(texto: str, escopo: str = "artigo") -> list[dict]:
    """Extrai markers de alteracao legislativa do texto.
    PL-19 Estagio 2: campo `escopo` indica de qual nivel hierarquico veio
    a alteracao ('artigo' por default; 'livro'/'titulo'/'subtitulo'/'capitulo'/
    'secao' quando capturado de header)."""
    alteracoes, vistos = [], set()
    for pattern, tipo in ALTERACAO_PATTERNS:
        for match in pattern.finditer(texto):
            norma = re.sub(r'\s+', ' ', match.group(1).strip())
            chave = f"{tipo}:{norma}:{escopo}"
            if chave not in vistos:
                vistos.add(chave)
                alteracoes.append({"tipo": tipo, "norma": norma, "escopo": escopo})
    return alteracoes


def _dedup_alteracoes(alts):
    """Dedup alteracoes por (tipo, norma, escopo)."""
    seen = set()
    out = []
    for a in alts:
        chave = (a.get("tipo"), a.get("norma"), a.get("escopo", "artigo"))
        if chave in seen:
            continue
        seen.add(chave)
        out.append(a)
    return out


# --- Ruido legislativo ---
NOISE_PATTERNS = [
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)[^)]{0,200}\)',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)[^)]{0,200}\)',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]{0,200}\)',                    re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]{0,200}\)',                re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Nova\s+redação\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Renumerad[oa]s?\s+[^)]{0,200}\)',                  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Suprimid[oa]s?\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Restaurad[oa]s?\s+[^)]{0,200}\)',                  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Express[ãa]o\s+substitu[ií]d[oa]\s+[^)]{0,200}\)', re.IGNORECASE | re.DOTALL),
    # 2026-07-07 bug A (LC123 Art. 17): o sufixo destes padroes NUNCA pode consumir
    # '\n' — engolir a quebra cola o rotulo orfao na linha seguinte, a linha mesclada
    # deixa de ser "rotulo nu" e o M1 nao restaura o literal (perda de (REVOGADO)).
    # Por isso whitespace HORIZONTAL ([^\S\n]) em todos os sufixos abaixo.
    re.compile(r'\(Revogad[oa]s?\)[^\S\n]*[.;,]?',                    re.IGNORECASE),
    re.compile(r'\(Suprimid[oa]s?\)[^\S\n]*[.;,]?',                   re.IGNORECASE),
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}(?:[:.]|[^\S\n])*',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}(?:[:.]|[^\S\n])*',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}(?:[:.]|[^\S\n])*',                      re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}(?:[:.]|[^\S\n])*',                   re.IGNORECASE | re.DOTALL),
    # Linha standalone 'Vigência': remover SEM consumir as quebras (lookaround) — o
    # sub de '\n...\n' por '' colava a linha anterior com a seguinte (mesma familia A).
    re.compile(r'(?<=\n)[^\S\n]*Vigência[^\S\n]*(?=\n)',      re.IGNORECASE),
    re.compile(r'\(Vigência\)',             re.IGNORECASE),
    re.compile(r'(?<=\n)[^\S\n]*\(Vigência\)[^\S\n]*(?=\n)',  re.IGNORECASE),
    # PL-19 B-07: markers cross-reference que pollunavam *_nome (CDC Art. 60, CLT etc)
    re.compile(r'\(Vide\s+[^)]{0,200}\)',                  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Regulamento[^)]{0,100}\)',              re.IGNORECASE),
    re.compile(r'\(\s?Produ[çc][ãa]o\s+de\s+efeitos?[^\S\n]*\)', re.IGNORECASE),
    # 2026-07-07 bug B: marker 'Produção de efeito' SEM parenteses no fim da linha
    # (padrao LC 155/2016: '...de 2016)      Produção de efeito'). 218 ocorrencias
    # vazavam pro texto_limpo (LC123 182, CF88 18, CC 14, CLT 4).
    re.compile(r'[^\S\n]*Produ[çc][ãa]o[^\S\n]+de[^\S\n]+efeitos?\.?[^\S\n]*$', re.IGNORECASE | re.MULTILINE),
]

def limpar_ruido_legislativo(texto: str) -> str:
    for pattern in NOISE_PATTERNS:
        texto = pattern.sub('', texto)
    linhas = [l for l in texto.splitlines() if l.strip()]
    return '\n'.join(linhas).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Reparo de dispositivos órfãos — rótulo sem conteúdo (bug CF88 Art. 7º XXVIII/XXIX)
# ──────────────────────────────────────────────────────────────────────────────
# Três mecanismos produziam um rótulo nu (alínea/inciso/§) sem texto:
#   M1: dispositivo revogado/vetado cujo ÚNICO conteúdo é a anotação
#       (ex: "a) (Revogada). (Redação dada pela EC nº 28, de 2000)"). O
#       limpar_ruido_legislativo removia a anotação e sobrava "a)".
#       -> Fix: PRESERVAR a linha LITERAL (fonte fiel; nunca compor/parafrasear).
#   M2: resíduo de redação ANTERIOR riscada (<strike>) cujo rótulo ficou FORA do
#       strike e vazou como "a)"/"b)" nus, sem anotação. A redação atual do mesmo
#       dispositivo já existe logo abaixo. -> Fix: DROPAR o rótulo exatamente vazio.
#   M3: referência cruzada quebrada em duas linhas ("...art. 165," + "§ 9º. (...)").
#       Não é dispositivo — é continuação do caput. -> Fix: RE-JUNTAR à linha anterior.
# NUNCA tocar "rótulo + dot-leaders" ("I - .........."): é elisão legislativa real
# em blocos de emenda (LC123, LMP) — o teste negativo trava isso permanentemente.

# Rótulo EXATAMENTE vazio: label seguido de nada (ou só de uma pontuação isolada).
# Dot-leaders (múltiplos '.') NÃO casam -> preservados.
_ROTULO_VAZIO_RE = re.compile(
    r'^(?:'
    r'[a-z]\)'                              # alínea: a) b) c)
    r'|[IVXLCDM]{1,7}\s*[-–—]'             # inciso com traço: I - II -
    r'|[IVXLCDM]{1,7}'                      # inciso romano isolado: I
    r'|§\s*\d+\s*[º°o]?(?:-[A-Z])?'         # parágrafo: § 1º § 9º-A
    r'|Parágrafo\s+único'                   # parágrafo único
    r')\s*[.;,)\-–—]?\s*$',
    re.IGNORECASE,
)

# M1-CAPUT (2026-07-06): caput de artigo cujo único conteúdo é a anotação de
# revogação (ex: "Art. 384 - (Revogado pela Lei nº 13.467, de 2017)"). O strip
# comia a anotação e sobrava o caput nu ("Art. 384 -") — 261 revogados na base
# (ver known_issues.json > caput_revogado_nu). Mesmo tratamento M1: preservar a
# linha LITERAL. NUNCA dropar caput (M2 não se aplica: o artigo precisa existir).
# Pontuação residual limitada a {0,2} -> dot-leaders de elisão ("Art. 2º ....")
# NÃO casam, mesma garantia permanente do M2.
_CAPUT_NU_RE = re.compile(
    r'^Art\.?\s*[\d.]*\d\s*[º°o]?(?:-[A-Z])?'   # rótulo: Art. 384 / Art. 130-A / Art. 5º
    r'(?:\s*\.?\s*a\s*[\d.]*\d\.?)?'             # range de revogação em bloco: "Art. 1.620. a 1.629."
    r'\s*[-–—.;,:]{0,2}\s*$'
)


def _e_caput_nu(s: str) -> bool:
    return bool(_CAPUT_NU_RE.match(s.strip()))

# Linha anterior termina numa REFERÊNCIA + vírgula (continuação de xref, não fim de frase).
_XREF_PREV_RE = re.compile(
    r'(?:art\.?\s*[\d.]+|§\s*\d+\s*[º°o]?|inciso\s+[IVXLCDM]+|al[íi]nea\s+[a-z])\s*,\s*$',
    re.IGNORECASE,
)
# Linha atual começa com marcador de dispositivo (candidata a ser a cauda da xref).
_XREF_CONT_START_RE = re.compile(r'^(?:§\s*\d+|[IVXLCDM]{1,7}\s*[-–—]|[a-z]\))')


def _e_rotulo_vazio(s: str) -> bool:
    return bool(_ROTULO_VAZIO_RE.match(s.strip()))


def _merge_xref_continuation(linhas: list[str]) -> list[str]:
    """M3: re-junta uma linha iniciada por marcador (§/inciso/alínea) à anterior
    quando esta termina numa referência + vírgula (ex: '...art. 165,' + '§ 9º. (...)').
    É continuação de referência cruzada, não um dispositivo novo."""
    out: list[str] = []
    for ln in linhas:
        s = ln.strip()
        if out and s and _XREF_CONT_START_RE.match(s) and _XREF_PREV_RE.search(out[-1]):
            out[-1] = out[-1].rstrip() + " " + s
        else:
            out.append(ln)
    return out


def reparar_dispositivos_orfaos(texto_raw: str) -> str:
    """Substitui limpar_ruido_legislativo no fluxo de artigo, reparando dispositivos
    que virariam rótulo nu. Para artigos SEM órfão o resultado é IDÊNTICO a
    limpar_ruido_legislativo (nada muda). Ver M1/M2/M3 acima.

    Passo isolado e testável: recebe o texto BRUTO do buffer (anotações presentes) e
    devolve o texto_limpo já reparado."""
    linhas = _merge_xref_continuation(texto_raw.split("\n"))   # M3 primeiro

    linhas_para_strip: list[str] = []
    m1_literais: list[str] = []
    for ln in linhas:
        s = ln.strip()
        if not s:
            linhas_para_strip.append(ln)
            continue
        if _e_rotulo_vazio(s):
            continue                                # M2: rótulo exatamente vazio -> drop
        # M1: se o strip colapsaria a linha para um rótulo nu, a anotação removida era
        # o único conteúdo (revogado/vetado) -> guardar o LITERAL para restaurar depois.
        # M1-CAPUT: idem para caput de artigo revogado ("Art. 384 - (Revogado pela...)");
        # o guard `not _e_caput_nu(s)` deixa caputs JÁ nus no bruto (sem anotação, ou
        # dot-leaders de elisão) passarem intactos — nada a preservar.
        cl_linha = limpar_ruido_legislativo(s)
        if _e_rotulo_vazio(cl_linha) or (_e_caput_nu(cl_linha) and not _e_caput_nu(s)):
            m1_literais.append(s)
        linhas_para_strip.append(ln)

    texto_limpo = limpar_ruido_legislativo("\n".join(linhas_para_strip))

    if m1_literais:
        # Restaura os literais M1 nos rótulos nus resultantes (mesma ordem — o strip
        # preserva a ordem das linhas e M2 já foi removido, então dispositivo é 1:1).
        # Caput: restaura SÓ se o literal pendente colapsa exatamente para a linha nua
        # (caput nu sem literal capturado — ex: dot-leaders — fica como está).
        pend = list(m1_literais)
        restauradas = []
        for cl in texto_limpo.split("\n"):
            if pend and _e_rotulo_vazio(cl):
                restauradas.append(pend.pop(0))
            elif pend and _e_caput_nu(cl) \
                    and limpar_ruido_legislativo(pend[0]).strip() == cl.strip():
                restauradas.append(pend.pop(0))
            else:
                restauradas.append(cl)
        texto_limpo = "\n".join(restauradas)

    return texto_limpo


def limpar_marker_hierarquia(nome: str) -> str:
    """Remove markers de alteracao legislativa de nomes hierarquicos
    (livro_nome, titulo_nome, capitulo_nome, secao_nome).
    Aplica os mesmos padroes de NOISE_PATTERNS e normaliza espacos.
    2026-04-08: tambem strip de smart-quotes/aspas trailing (ex LGPD CAP IX
    que termina com ' U+2019)."""
    if not nome:
        return ""
    for pattern in NOISE_PATTERNS:
        nome = pattern.sub('', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    # Strip trailing smart-quotes / aspas / pontuacao residual
    nome = re.sub(r'[\u2019\u2018\u201C\u201D\'"`]+$', '', nome).strip()
    return nome


# ──────────────────────────────────────────────────────────────────────────────
# PL-19 B-10 / B-11 — notas_legais e controle_constitucionalidade
# ──────────────────────────────────────────────────────────────────────────────
# Markers cross-reference que ate PL-19 estavam perdidos ou polluindo *_nome.
# Auditoria 2.0 (2026-04-08) achou 632 ocorrencias na base. Agora cada uma
# vira entry estruturada em notas_legais (cross-refs) ou
# controle_constitucionalidade (ADI/ADIN/ADPF/ADC/MI — risco juridico maior).

# Patterns ordenados — mais especificos PRIMEIRO. Os tipos especificos do
# controle constitucional sao verificados antes do fallback `vide_outros`.
NOTA_LEGAL_PATTERNS = [
    (re.compile(r'\(Vide\s+Lei\s+Complementar\s+n[ºo°.]?\s*([^)]+)\)', re.IGNORECASE), 'vide_lei_complementar'),
    (re.compile(r'\(Vide\s+Lei\s+n[ºo°.]?\s*([^)]+)\)',                 re.IGNORECASE), 'vide_lei'),
    (re.compile(r'\(Vide\s+Decreto-Lei\s+n[ºo°.]?\s*([^)]+)\)',          re.IGNORECASE), 'vide_decreto_lei'),
    (re.compile(r'\(Vide\s+Decreto\s+n[ºo°.]?\s*([^)]+)\)',              re.IGNORECASE), 'vide_decreto'),
    (re.compile(r'\(Vide\s+Emenda\s+[Cc]onstitucional\s+n[ºo°.]?\s*([^)]+)\)', re.IGNORECASE), 'vide_emenda'),
    (re.compile(r'\(Vide\s+Medida\s+Provis[óo]ria\s+n[ºo°.]?\s*([^)]+)\)', re.IGNORECASE), 'vide_medida_provisoria'),
    (re.compile(r'\(Vide\s+Constitui[çc][ãa]o\s+([^)]+)\)',              re.IGNORECASE), 'vide_constituicao'),
    (re.compile(r'\(Vide\s+Recurso\s+Extraordin[áa]rio\s+(?:n[ºo°.]?\s*)?([^)]+)\)', re.IGNORECASE), 'vide_recurso_extraordinario'),
    (re.compile(r'\(Vide\s+Processo\s+([^)]+)\)',                        re.IGNORECASE), 'vide_processo'),
    (re.compile(r'\(Regulamento\)',                                      re.IGNORECASE), 'regulamento'),
    (re.compile(r'\(Produ[çc][ãa]o\s+de\s+efeitos?\)',                  re.IGNORECASE), 'producao_de_efeito'),
    # Fallback generico — DEVE ser ultimo (e tambem captura tipos nao listados)
    (re.compile(r'\(Vide\s+([^)]+)\)',                                   re.IGNORECASE), 'vide_outros'),
]

# Controle de constitucionalidade — entradas separadas porque sao mais criticas
CONTROLE_CONST_PATTERNS = [
    (re.compile(r'\(Vide\s+(ADIN?)\s+(?:n[ºo°.]?\s*)?([\d.,/-]+)[^)]*\)', re.IGNORECASE), 'ADI'),
    (re.compile(r'\(Vide\s+(ADPF)\s+(?:n[ºo°.]?\s*)?([\d.,/-]+)[^)]*\)', re.IGNORECASE), 'ADPF'),
    (re.compile(r'\(Vide\s+(ADC)\s+(?:n[ºo°.]?\s*)?([\d.,/-]+)[^)]*\)',  re.IGNORECASE), 'ADC'),
    (re.compile(r'\(Vide\s+(MI)\s+(?:n[ºo°.]?\s*)?([\d.,/-]+)[^)]*\)',   re.IGNORECASE), 'MI'),
    (re.compile(r'\(Vide\s+(AR)\s+(?:n[ºo°.]?\s*)?([\d.,/-]+)[^)]*\)',   re.IGNORECASE), 'AR'),
]


def extrair_notas_legais(texto: str) -> list[dict]:
    """Extrai markers cross-reference (Vide Lei, Regulamento, Producao de efeito, etc).
    NAO inclui controle de constitucionalidade (ADI/ADPF/ADC/MI/AR) — esses vao
    pro campo `controle_constitucionalidade` separado.

    Retorna lista de dicts com tipo, referencia (norma alvo), raw (string completa)."""
    if not texto:
        return []

    # Tracking de posicoes ja matchadas pra evitar dupla captura
    # (1) Posicoes matched por controle constitucional — nao re-capturar como vide
    # (2) Posicoes matched por patterns especificos — fallback `vide_outros` so
    #     captura o que sobrou
    matched_ranges = []
    for pattern, _ in CONTROLE_CONST_PATTERNS:
        for m in pattern.finditer(texto):
            matched_ranges.append((m.start(), m.end()))

    def _in_matched(start):
        return any(s <= start < e for s, e in matched_ranges)

    notas = []
    seen = set()

    # Pass 1 — patterns especificos (skip o generico vide_outros)
    for pattern, tipo in NOTA_LEGAL_PATTERNS:
        if tipo == 'vide_outros':
            continue
        for m in pattern.finditer(texto):
            if _in_matched(m.start()):
                continue
            # SEMPRE registra no matched_ranges (mesmo se for dedupado abaixo)
            # pra que vide_outros nao re-capture na Pass 2
            matched_ranges.append((m.start(), m.end()))
            ref = m.group(1).strip() if m.lastindex else None
            if ref:
                ref = re.sub(r'\s+', ' ', ref).strip()
            raw = m.group(0)
            chave = f"{tipo}:{raw}"
            if chave in seen:
                continue
            seen.add(chave)
            notas.append({
                "tipo": tipo,
                "referencia": ref if ref else None,
                "raw": raw,
            })

    # Pass 2 — fallback vide_outros so pra Vide nao classificado nos especificos
    pattern_outros = next(p for p, t in NOTA_LEGAL_PATTERNS if t == 'vide_outros')
    for m in pattern_outros.finditer(texto):
        if _in_matched(m.start()):
            continue
        ref = m.group(1).strip() if m.lastindex else None
        if ref:
            ref = re.sub(r'\s+', ' ', ref).strip()
        raw = m.group(0)
        chave = f"vide_outros:{raw}"
        if chave in seen:
            continue
        seen.add(chave)
        notas.append({
            "tipo": "vide_outros",
            "referencia": ref if ref else None,
            "raw": raw,
        })

    return notas


def _dedup_notas(notas_list):
    """Dedup notas_legais por raw, preservando ordem."""
    seen = set()
    out = []
    for n in notas_list:
        if n["raw"] in seen:
            continue
        seen.add(n["raw"])
        out.append(n)
    return out


def _dedup_controle(controle_list):
    """Dedup controle_constitucionalidade por (tipo, numero)."""
    seen = set()
    out = []
    for c in controle_list:
        chave = (c["tipo"], c["numero"])
        if chave in seen:
            continue
        seen.add(chave)
        out.append(c)
    return out


def extrair_controle_constitucionalidade(texto: str) -> list[dict]:
    """Extrai referencias a controle constitucional do STF (ADI/ADIN/ADPF/ADC/MI/AR).
    Severidade juridica maior — pode indicar inconstitucionalidade ou andamento
    processual relevante.

    Retorna lista de dicts com tipo, numero, tribunal (sempre STF), raw."""
    if not texto:
        return []
    out = []
    seen = set()
    for pattern, tipo_normalizado in CONTROLE_CONST_PATTERNS:
        for m in pattern.finditer(texto):
            numero = m.group(2).strip().rstrip('.,;')
            if not numero:
                continue
            chave = f"{tipo_normalizado}:{numero}"
            if chave in seen:
                continue
            seen.add(chave)
            out.append({
                "tipo": tipo_normalizado,
                "numero": numero,
                "tribunal": "STF",
                "raw": m.group(0),
            })
    return out


# --- Hashes ---
# O estado de idempotencia agora vive no banco (raw_captures.content_hash, Portao 1 /
# ADR 0002). O hashes.json local foi aposentado.
def hash_conteudo(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


_BOM = chr(0xFEFF)  # Byte Order Mark; removido do inicio do texto UTF-16


def decode_utf16(raw: bytes) -> str:
    """Decodifica bytes UTF-16 -> str resolvendo o endianness de forma DETERMINISTICA.

    O Planalto ora serve com BOM, ora UTF-16 Big-Endian SEM BOM (mudou em 2026-07).
    Deixar o codec 'utf-16' adivinhar sem BOM assume Little-Endian -> embaralha os bytes,
    o texto vira lixo/NUL e o parser nao acha nenhum 'Art.' (regressao da LMP). Sem BOM:
    caractere ASCII em UTF-16 tem o byte alto 0x00, entao BE se o 1o byte e 0x00, senao LE.
    Sempre remove o BOM (U+FEFF) residual do inicio."""
    # Planalto as vezes manda o stream UTF-16 truncado (numero impar de bytes). O ultimo
    # byte e meia-unidade — nao forma caractere valido —, entao descarta antes de decodar
    # pra nao virar U+FFFD no fim do texto (blemish num texto juridico). O decode estrito
    # explodiria; errors='replace' fica como cinto pra qualquer outra corrupcao (que os
    # guardrails a jusante pegam).
    if len(raw) % 2:
        raw = raw[:-1]
    if raw.startswith(b'\xff\xfe'):
        return raw.decode('utf-16-le', errors='replace').lstrip(_BOM)
    if raw.startswith(b'\xfe\xff'):
        return raw.decode('utf-16-be', errors='replace').lstrip(_BOM)
    variant = 'utf-16-be' if raw[:1] == b'\x00' else 'utf-16-le'
    return raw.decode(variant, errors='replace').lstrip(_BOM)


def strip_padding_tail(text: str) -> str:
    """Remove cauda de padding corrompido: run de 10+ simbolos (nao-letra/digito/espaco)
    no FIM do texto — texto juridico nunca tem isso; e artefato de decode de padding de
    espacos do Planalto. Ex.: LMP Art. 46 vinha com '...8.8.2006 *' seguido de 779x U+2020
    + U+FFFD. Ancorado no fim: dot leaders legitimos (no meio) nao sao afetados."""
    return re.sub(r'[^\w\s]{10,}\s*$', '', text).rstrip()


def normalizar_texto(text: str) -> str:
    """Normalizacao DETERMINISTICA e segura (camada 1 do radar de mudancas):
      - NFC: forma canonica Unicode (mesmo texto, bytes canonicos) -> hash estavel;
      - colapsa espaco/tab HORIZONTAIS em 1 espaco e remove espaco colado na quebra.
    PRESERVA '\\n' (estrutura de artigo/paragrafo que o parser usa). NAO unifica traco
    (– vs -) nem \\n-vs-espaco: sao potencialmente semanticos. A fonte fiel (bytes brutos)
    fica em raw_captures; aqui so canonicaliza o texto ja limpo, cortando ruido cosmetico
    que geraria versao espuria (falso alerta no radar)."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[^\S\n]+", " ", text)   # espaco/tab horizontais -> 1 espaco
    text = re.sub(r" ?\n ?", "\n", text)    # tira espaco colado na quebra de linha
    return text


# --- HTTP ---
def criar_sessao():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LegalBot/2.0)"})
    return session


# --- Chunking ---
def split_com_overlap(texto: str, max_chars: int = 6000, overlap_chars: int = 400) -> list[str]:
    if len(texto) <= max_chars:
        return [texto]
    partes, inicio = [], 0
    while inicio < len(texto):
        fim = inicio + max_chars
        if fim >= len(texto):
            partes.append(texto[inicio:].strip())
            break
        corte = texto.rfind('\n', inicio, fim)
        if corte <= inicio:
            corte = fim
        partes.append(texto[inicio:corte].strip())
        inicio = max(inicio + 1, corte - overlap_chars)
    return [p for p in partes if p]


# --- Regex de artigo ---
REGEX_ARTIGO = re.compile(
    r'^Art\.?\s*(\d[\d.]*\d|\d+)'
    r'(?:[°ºo])?'
    r'(?:-([A-Z](?:-[A-Z])*))?'
    r'(?:[°ºo])?'
    r'(?:[\.\s]|$)'
)

REGEX_NOME_SECAO = re.compile(
    r'^(Dos?|Das?|Disposições)\s+[A-ZÀ-Ú][\w\sÀ-ú,()áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]+$',
    re.IGNORECASE
)

REGEX_SECAO_HEADER = re.compile(
    r'^(LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)\s*'
    r'([IVXLCDM]+(?:\s*-\s*[A-Z])?|[ÚU]NIC[OA]|PRELIMINAR|COMPLEMENTAR|ESPECIAL)?\s*$',
    re.IGNORECASE
)

REGEX_CONTINUACAO_HEADER = re.compile(
    r'^([IVXLCDM]+(?:\s*-\s*[A-Z])?|COMPLEMENTAR|PRELIMINAR|ESPECIAL|[ÚU]NIC[OA])\s*$',
    re.IGNORECASE
)

# PL-13 sub-bloco 2e: header de hierarquia em formato inline (numeral e nome
# na mesma linha). Ex: "LIVRO I DAS PESSOAS", "CAPÍTULO I Da Personalidade".
# split_inline_headers reescreve essas linhas em duas (numeral + nome) pra que
# o parser de extrair_estrutura possa capturar como header standalone.
#
# 2026-04-08 fix: aceita markers de alteracao opcionais entre o numeral e o
# nome. Ex LGPD: "CAPÍTULO IX (Redação dada pela Lei nº 15.352, de 2026) DA
# AGÊNCIA NACIONAL..." — antes desse fix, o parser perdia o capitulo inteiro.
INLINE_HEADER_RE = re.compile(
    r'^((?:LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)'
    r'\s+(?:[IVXLCDM]+(?:\s*-\s*[A-Z])?|[ÚU]NIC[OA]|PRELIMINAR|COMPLEMENTAR|ESPECIAL))'
    r'((?:\s*\([^)]+\))*)'  # markers opcionais entre numeral e nome (capturado em \2)
    # PL-13: primeira letra do nome precisa ser MAIUSCULA. Inline flag (?-i:...)
    # desabilita IGNORECASE so nesse grupo, evitando casar citacoes inline
    # tipo "Livro II da Parte Especial deste Código" onde 'da' e lowercase.
    r'\s+((?-i:[A-ZÀ-Ú]).+)$',
    re.MULTILINE | re.IGNORECASE
)


def _split_inline_repl(m: re.Match) -> str:
    header_part = m.group(1)
    marker_part = (m.group(2) or '').strip()
    name_part = m.group(3)
    # Markers vao pra linha 2 (junto com o nome) pra que extrair_alteracoes /
    # extrair_notas_legais consigam captura-los como pertencentes ao escopo do
    # capitulo/titulo, e limpar_marker_hierarquia depois remova do nome final.
    if marker_part:
        return f"{header_part}\n{marker_part} {name_part}"
    return f"{header_part}\n{name_part}"


def split_inline_headers(text: str) -> str:
    """Quebra headers de hierarquia em formato inline em duas linhas.
    Ex: 'CAPÍTULO I Da Personalidade' → 'CAPÍTULO I\\nDa Personalidade'.
    Aceita markers opcionais entre o numeral e o nome (preservando-os na
    linha 2 pra que extrair_alteracoes/notas_legais possa capturar).
    Aplicado linha-a-linha via re.MULTILINE — linhas que nao casam ficam intactas."""
    return INLINE_HEADER_RE.sub(_split_inline_repl, text)


def parse_art_num(num_str: str) -> int:
    """Converte string de numero de artigo para int.
    Aceita '999', '1.000', '1.337'. Lanca ValueError se invalido."""
    num_limpo = num_str.replace('.', '')
    if not num_limpo.isdigit():
        raise ValueError(f"Numero de artigo invalido: {num_str!r}")
    return int(num_limpo)


# --- Classificacao artigo vs citacao ---
def classificar_linha_artigo(linha: str, num_atual: int, sufixo: str, ultimo_num: int) -> str:
    MARCADORES_CITACAO = [
        r'da lei n[°º]?\s*\d', r'do decreto n[°º]?\s*\d',
        r'da lei complementar n', r'do código civil',
        r'desta lei', r'da constituição',
    ]
    linha_lower = linha[:120].lower()
    for marcador in MARCADORES_CITACAO:
        if re.search(marcador, linha_lower):
            if num_atual > ultimo_num + 200 or num_atual < ultimo_num - 10:
                return 'citacao'
    if num_atual > ultimo_num + 200:
        return 'citacao'
    if num_atual < ultimo_num - 15:
        return 'citacao'
    return 'novo_artigo'


# --- Status / vetos ---
# Enum de status (3 valores possíveis):
#   "vigente"      — artigo em vigor (pode ter vetos_parciais em dispositivos internos)
#   "vetado_total"  — artigo integralmente vetado na sanção da lei
#   "revogado"      — artigo revogado ou suprimido por lei posterior
def detectar_status_artigo(texto_artigo: str) -> tuple[str, list[str]]:
    t = texto_artigo.strip()

    t_for_status = t
    for pattern in [
        re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao).*?\)',  re.IGNORECASE | re.DOTALL),
        re.compile(r'\(Redação dada\s+(?:pela|pelo|ao).*?\)',    re.IGNORECASE | re.DOTALL),
        re.compile(r'\(Acrescentad[oa]s?\s+(?:pela|pelo|ao).*?\)', re.IGNORECASE | re.DOTALL),
        re.compile(r'\(Nova redação\s+(?:pela|pelo|ao).*?\)',    re.IGNORECASE | re.DOTALL),
    ]:
        t_for_status = pattern.sub('', t_for_status)
    t_for_status = t_for_status.strip()
    t_lower = t_for_status.lower()

    corpo_ref = t_lower if len(t) < 200 else t_lower.split('\n')[0].strip()
    corpo = re.sub(r'^art\.\s*[\d.]+[\w-]*[°º]?\s*\.?\s*', '', corpo_ref, count=1).strip()
    corpo_limpo = re.sub(r'[\s.\-–—()]', '', corpo)

    if corpo_limpo.startswith('vetado'):
        return ('vetado_total', [])
    if corpo_limpo.startswith(('revogado', 'revogada', 'revogados', 'suprimido', 'suprimida')):
        return ('revogado', [])

    if len(t) < 200:
        t_lower_full = t.lower()
        if re.search(r'\(suprimid', t_lower_full):
            return ('revogado', [])
        if re.search(r'\(revogad', t_lower_full):
            return ('revogado', [])

    # Vetos parciais
    t_veto = re.sub(r'\s*\n\s*', ' ', t)
    t_veto = re.sub(r'(§\s*\d+)\s+o\b', r'\1°', t_veto)
    vetos_parciais, seen = [], set()

    for m in re.finditer(r'(§\s*\d+[°ºo]?)\s*[-–—.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?', t_veto):
        label = m.group(1).strip()
        if label not in seen: seen.add(label); vetos_parciais.append(label)

    for m in re.finditer(r'(Parágrafo\s+único)\s*[.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?', t_veto, re.IGNORECASE):
        label = "Parágrafo único"
        if label not in seen: seen.add(label); vetos_parciais.append(label)

    for m in re.finditer(r'([IVXLCDM]+)\s*[-–—.\s]+\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?', t_veto):
        inciso = m.group(1).strip()
        texto_antes = t_veto[:m.start()]
        pm = re.findall(r'§\s*\d+[°ºo]?', texto_antes)
        pu = re.findall(r'Parágrafo\s+único', texto_antes, re.IGNORECASE)
        if pu and (not pm or texto_antes.rfind(pu[-1]) > texto_antes.rfind(pm[-1])):
            label = f"Parágrafo único, {inciso}"
        elif pm:
            label = f"{pm[-1].strip()}, {inciso}"
        else:
            label = inciso
        if label not in seen: seen.add(label); vetos_parciais.append(label)

    for m in re.finditer(r'\b([a-z]\))\s*[-–—.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?', t_veto):
        alinea = m.group(1).strip()
        texto_antes = t_veto[:m.start()]
        pm = re.findall(r'§\s*\d+[°ºo]?', texto_antes)
        pu = re.findall(r'Parágrafo\s+único', texto_antes, re.IGNORECASE)
        if pu and (not pm or texto_antes.rfind(pu[-1]) > texto_antes.rfind(pm[-1])):
            label = f"Parágrafo único, {alinea}"
        elif pm:
            label = f"{pm[-1].strip()}, {alinea}"
        else:
            label = alinea
        if label not in seen: seen.add(label); vetos_parciais.append(label)

    for m in re.finditer(r'(Art\.\s*\d+[A-Z])\s*\.\s*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?', t_veto):
        label = m.group(1).strip()
        if label not in seen: seen.add(label); vetos_parciais.append(label)

    total_vet = len(re.findall(r'\(\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)', t_veto))
    if total_vet > len(vetos_parciais):
        for i in range(total_vet - len(vetos_parciais)):
            vetos_parciais.append(f"dispositivo vetado {len(vetos_parciais)+1}")

    if vetos_parciais:
        return ('vigente', vetos_parciais)

    if re.search(r'\((?:revogad|suprimid)', t.lower()):
        if not re.search(r'\((?:Redação dada|Nova redação|Incluíd[oa]s?)\s+(?:pela|pelo)', t, re.IGNORECASE):
            return ('revogado', [])

    return ('vigente', [])


# --- Referencias cruzadas ---

def _normalizar_referencia_lei(raw: str) -> str:
    """PL-19 B-05: normaliza formatos variantes pra 'Lei nº X' canonico.

    Casos cobertos:
        'Lei n°7.347'      -> 'Lei nº 7.347'
        'Lei n° 4.380'     -> 'Lei nº 4.380'
        'Lei no 8.212'     -> 'Lei nº 8.212'
        'Lei n 8.212'      -> 'Lei nº 8.212'
        'Decreto-lei nº X' -> 'Decreto-Lei nº X'
    """
    s = raw.strip()
    # Decreto-lei -> Decreto-Lei
    s = re.sub(r'\bDecreto-lei\b', 'Decreto-Lei', s)
    # n°/no -> nº
    s = s.replace('n°', 'nº')
    s = re.sub(r'\bno(\s*\d)', r'nº\1', s)
    # 'n ' alone (sem simbolo, espaco entre n e digito) -> 'nº '
    s = re.sub(r'\bn\s+(\d)', r'nº \1', s)
    # Garante espaco apos 'nº'
    s = re.sub(r'nº\s*(\d)', r'nº \1', s)
    # Normaliza espacos
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# FIX 34: Contexto que indica referencia externa (nao interna)
_REF_EXT_CONTEXT = re.compile(
    r'\s*(?:da\s+Lei|do\s+Decreto|da\s+Constitui[cç]|do\s+C[oó]digo|'
    r'da\s+Medida|da\s+Emenda|da\s+Lei\s+Complementar|deste\s+Ato)',
    re.IGNORECASE
)

# FIX 33b: Padroes reais de referencia a CF/88 (sem falsos positivos)
_REF_CF_REAL = re.compile(
    r'(?:'
    r'art(?:igo)?s?\.\s*\d+.*?(?:da|desta)\s+Constitui[cç][aã]o'
    r'|nos\s+termos\s+(?:da|desta)\s+Constitui[cç][aã]o\s+(?:Federal|da\s+Rep[uú]blica)'
    r'|(?:garantid|previst|estabelecid|assegurad|definid|protegid)[oa]s?\s+(?:na|pela)\s+Constitui[cç][aã]o'
    r'|Constitui[cç][aã]o\s+(?:Federal|da\s+Rep[uú]blica\s+Federativa)'
    r')',
    re.IGNORECASE
)
_REF_CF_FALSE = re.compile(
    r'Constitui[cç][aã]o\s+de\s+\d{4}|Constitui[cç][aã]o\s+de\s+mil[ií]cia'
    r'|Da\s+Constitui[cç][aã]o\s+do\s+Penhor',
    re.IGNORECASE
)

def extrair_referencias(texto: str, artigo_atual: str) -> dict:
    art_num_atual = re.sub(r'^Art\.\s*', '', artigo_atual)

    # FIX 35: Captura multi-artigo: "arts. X, Y e Z" / "arts. X e Y" / "arts. X a Y"
    _num_re = re.compile(r'([\d\.]+(?:-[A-Z])?)')
    _arts_multi = re.compile(
        r'\bart(?:s|igos?)?\.\s*((?:[\d\.]+(?:-[A-Z])?\s*[,ea]\s*)*[\d\.]+(?:-[A-Z])?)',
        re.IGNORECASE
    )

    internas = set()
    for m in _arts_multi.finditer(texto):
        # FIX 34: Checa se o contexto apos o match indica ref externa ou CF
        after = texto[m.end():m.end()+60]
        if _REF_EXT_CONTEXT.match(after):
            continue
        nums = _num_re.findall(m.group(1))
        for num in nums:
            num = num.rstrip('.')  # remove pontos finais (ellipsis, fim de frase)
            if num and num != art_num_atual:
                internas.add(f"Art. {num}")

    # Leis externas (inclui Emenda Constitucional)
    # PL-19 B-05: exige digito no numero (evita 'Lei n.' vazio)
    padrao_lei = re.compile(
        r'(?:Lei|Decreto(?:-Lei)?|Lei Complementar|Medida Provisória|Emenda Constitucional)\s+'
        r'n(?:[°ºo]|\.)?\s*\d[\d\.]*(?:/\d+)?',
        re.IGNORECASE
    )
    leis_externas = sorted(set(
        _normalizar_referencia_lei(m.group(0))
        for m in padrao_lei.finditer(texto)
    ))

    # FIX 33b: Deteccao robusta de ref a CF/88
    ref_cf = bool(_REF_CF_REAL.search(texto) and not _REF_CF_FALSE.search(texto))

    return {"internas": sorted(internas), "leis_externas": leis_externas, "constituicao": ref_cf}


# --- Dedup de redações (config-driven, roda pós-extração) ---
_DEDUP_PREFIX_RE = re.compile(
    r'^(\s*(?:[IVXLCDM]+(?:-[A-Z])?\s*[-–—]|§\s*\d+\s*[°ºo]?(?:-[A-Z])?\s*[-–—.\s]|Parágrafo\s+único|[a-z]\)))'
)
_DEDUP_HIERARCHY_RE = re.compile(r'^\s*(§\s*\d+|Parágrafo\s+único)', re.IGNORECASE)
_DEDUP_PARA_RE = re.compile(r'^§\s*\d+')
# "§ 15 do art. 18" é referência a outro artigo, não header de parágrafo
_DEDUP_REF_RE = re.compile(r'^§\s*\d+\s+(?:do|da|de|ao|dos|das|deste|desta|desse|dessa)\b', re.IGNORECASE)
# Normaliza "§ 1 o", "§ 1º", "§ 1°" → "§1" para comparação
_DEDUP_NORM_RE = re.compile(r'[°ºo\s.\-–—]')

def _norm_prefix(prefix: str) -> str:
    """Normaliza prefixo para comparação: '§ 1 o' == '§ 1º' == '§ 1°'."""
    return _DEDUP_NORM_RE.sub('', prefix)

def dedup_redacoes_bloco(texto: str) -> str:
    """Remove redações antigas de texto_limpo.
    Regra: mesmo prefixo na mesma hierarquia → última ocorrência é vigente."""
    lines = texto.split('\n')
    if len(lines) < 2:
        return texto
    prefixes = [None] * len(lines)
    norm_prefixes = [None] * len(lines)
    for i, line in enumerate(lines):
        m = _DEDUP_PREFIX_RE.match(line)
        if m and not _DEDUP_REF_RE.match(line):
            prefixes[i] = m.group(1).strip()
            norm_prefixes[i] = _norm_prefix(prefixes[i])
    to_remove = set()
    for i in range(len(lines)):
        if norm_prefixes[i] is None:
            continue
        nprefix = norm_prefixes[i]
        is_para = bool(_DEDUP_PARA_RE.match(prefixes[i]))
        window = 12 if is_para else 4
        for j in range(i + 1, min(i + window, len(lines))):
            if any(_DEDUP_HIERARCHY_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            if norm_prefixes[j] is None:
                continue
            if norm_prefixes[j] == nprefix:
                to_remove.add(i)
                break
            if not is_para:
                break
    if not to_remove:
        return texto
    return '\n'.join(line for idx, line in enumerate(lines) if idx not in to_remove)


# =====================================================================
#  EXTRACAO DE ESTRUTURA (config-driven)
# =====================================================================

def extrair_estrutura(texto, sigla, versao, url, data_ext, config):
    livro = titulo = subtitulo = capitulo = secao = ""
    livro_nome = titulo_nome = subtitulo_nome = capitulo_nome = secao_nome = ""
    # PL-19 Estagio 2: notas_legais, controle_const e alteracoes por nivel
    # hierarquico. Sao captados ANTES do limpar_marker_hierarquia e
    # PROPAGADOS pros artigos filhos via flush_buffer. Resetam junto com
    # o respectivo *_nome.
    livro_notas = titulo_notas = subtitulo_notas = capitulo_notas = secao_notas = []
    livro_const = titulo_const = subtitulo_const = capitulo_const = secao_const = []
    livro_alt = titulo_alt = subtitulo_alt = capitulo_alt = secao_alt = []
    artigo_label_atual = "EMENTA"
    ultimo_num_artigo = 0
    em_transitorias = False
    blocos, buffer = [], []
    esperando_nome_secao = None

    # Compila boundaries da config
    boundaries = []
    for b in config.get("boundaries", []):
        boundaries.append({**b, "_re": re.compile(b["pattern"], re.IGNORECASE)})

    def flush_buffer(artigo_label):
        nonlocal buffer
        if not buffer:
            return
        texto_raw = "\n".join(buffer).strip()
        # PL-19 Estagio 2: alteracoes/notas/controle herdadas dos headers + do texto
        alteracoes_artigo = extrair_alteracoes(texto_raw, escopo="artigo")
        alteracoes = _dedup_alteracoes(
            livro_alt + titulo_alt + subtitulo_alt
            + capitulo_alt + secao_alt + alteracoes_artigo
        )
        notas_artigo = extrair_notas_legais(texto_raw)
        controle_artigo = extrair_controle_constitucionalidade(texto_raw)
        notas_legais = _dedup_notas(
            livro_notas + titulo_notas + subtitulo_notas
            + capitulo_notas + secao_notas + notas_artigo
        )
        controle_const = _dedup_controle(
            livro_const + titulo_const + subtitulo_const
            + capitulo_const + secao_const + controle_artigo
        )
        status, vetos_parciais = detectar_status_artigo(texto_raw)
        # reparar_dispositivos_orfaos = limpar_ruido_legislativo + reparo M1/M2/M3
        # (idêntico ao limpar_ruido para artigos sem dispositivo órfão).
        texto_limpo = reparar_dispositivos_orfaos(texto_raw)
        if not texto_limpo:
            buffer = []; return

        # Strip trailing section headers que sangraram do buffer
        # (último artigo antes de TÍTULO/CAPÍTULO/SEÇÃO absorve o header seguinte)
        def _strip_headers(t):
            return re.sub(
                r'\n(?:LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)\s+.*$',
                '', t, flags=re.IGNORECASE
            ).strip()
        texto_limpo = _strip_headers(texto_limpo)

        if not texto_limpo:
            buffer = []; return
        if len(texto_limpo) < 30 and status == 'vigente':
            buffer = []; return

        # Referências extraídas do texto SEM a anotação literal preservada pelo M1.
        # A norma emendadora/revogadora já vive em `alteracoes` (extraída de texto_raw);
        # deixá-la vazar para `referencias.leis_externas` criaria inconsistência com os
        # dispositivos normais (onde a anotação é removida). Mantém `referencias`
        # idêntico ao comportamento pré-fix — a mudança fica cirúrgica em texto_limpo/hash.
        refs = extrair_referencias(_strip_headers(limpar_ruido_legislativo(texto_raw)), artigo_label)
        path_partes = []
        for num, nome in [
            (livro, livro_nome),
            (titulo, titulo_nome),
            (subtitulo, subtitulo_nome),
            (capitulo, capitulo_nome),
            (secao, secao_nome),
        ]:
            if num:
                path_partes.append(f"{num} — {nome}" if nome else num)
        path = " > ".join(path_partes) if path_partes else ""

        # Enriquece vetado_total: se alteracoes está vazio, registra a norma de origem.
        # Se já tem (ex: "Incluído pela Lei 14.181" + vetado), o veto foi nessa lei.
        if status == 'vetado_total' and not alteracoes:
            alteracoes = [{"tipo": "vetado", "norma": f"Veto na sanção — {versao}", "escopo": "artigo"}]

        partes = split_com_overlap(texto_limpo)
        for i, parte in enumerate(partes):
            suffix_label = f" (Parte {i+1}/{len(partes)})" if len(partes) > 1 else ""
            art_clean = re.sub(r'^Art\.?\s*', '', artigo_label)
            art_slug = re.sub(r'[^\w]', '_', art_clean).strip('_').lower()
            part_slug = f"_p{i+1}" if len(partes) > 1 else ""
            artigo_id = re.sub(r'_+', '_', f"{sigla.lower()}_art_{art_slug}{part_slug}")

            blocos.append({
                "id": artigo_id, "lei": sigla, "versao": versao,
                "versao_consolidada": True,
                "artigo": f"{artigo_label}{suffix_label}",
                "livro": livro, "livro_nome": livro_nome,
                "titulo": titulo, "titulo_nome": titulo_nome,
                "subtitulo": subtitulo, "subtitulo_nome": subtitulo_nome,
                "capitulo": capitulo, "capitulo_nome": capitulo_nome,
                "secao": secao, "secao_nome": secao_nome,
                "path_hierarquico": path, "texto_limpo": parte,
                "status": status,
                "vetos_parciais": vetos_parciais if vetos_parciais else [],
                "alteracoes": alteracoes if alteracoes else [],
                "referencias": refs,
                "notas_legais": notas_legais,
                "controle_constitucionalidade": controle_const,
                "hash_artigo": hash_texto(parte),
                "url_fonte": url, "data_extracao": data_ext,
                "parte_num": i + 1 if len(partes) > 1 else None,
                "total_partes": len(partes) if len(partes) > 1 else None,
            })
        buffer = []

    for linha in texto.split("\n"):
        linha_clean = linha.replace('\xa0', ' ').strip()
        if not linha_clean:
            continue
        linha_clean = re.sub(r'^(Se[çc][ãa]o)([IVXLCDM])', r'\1 \2', linha_clean, flags=re.IGNORECASE)

        # -- Boundaries da config --
        boundary_matched = False
        for b in boundaries:
            if not b["_re"].match(linha_clean):
                continue
            cond = b.get("condition")
            if cond == "em_transitorias" and not em_transitorias:
                continue

            action = b["action"]
            if action == "transitorias":
                if ultimo_num_artigo > 0:
                    flush_buffer(artigo_label_atual)
                    em_transitorias = True
                    ultimo_num_artigo = 0
                    livro = titulo = subtitulo = capitulo = secao = ""
                    livro_nome = titulo_nome = subtitulo_nome = capitulo_nome = secao_nome = ""
                    # PL-19 Estagio 2: reset notas/controle/alteracoes ao entrar em transitorias
                    livro_notas = titulo_notas = subtitulo_notas = capitulo_notas = secao_notas = []
                    livro_const = titulo_const = subtitulo_const = capitulo_const = secao_const = []
                    livro_alt = titulo_alt = subtitulo_alt = capitulo_alt = secao_alt = []
                boundary_matched = True
            elif action == "flush_section":
                flush_buffer(artigo_label_atual)
                artigo_label_atual = b.get("label", "SEÇÃO")
                buffer = []
                boundary_matched = True
            elif action == "anexo":
                if ultimo_num_artigo > 0:
                    flush_buffer(artigo_label_atual)
                    m_anexo = re.match(
                        r'^(ANEXO(?:\s+[IVXLCDM]+(?:-[A-Z])?|\s+[ÚU]NICO|\s+\d+)?)',
                        linha_clean, re.IGNORECASE
                    )
                    artigo_label_atual = m_anexo.group(1).strip().upper() if m_anexo else "ANEXO"
                    ultimo_num_artigo = 999999
                    buffer = []
                    boundary_matched = True
            if boundary_matched:
                break
        if boundary_matched:
            continue

        # -- Continuacao de header partido --
        if esperando_nome_secao and REGEX_CONTINUACAO_HEADER.match(linha_clean):
            numeral = linha_clean.strip()
            if esperando_nome_secao == "livro": livro = f"{livro} {numeral}"
            elif esperando_nome_secao == "subtitulo": subtitulo = f"{subtitulo} {numeral}"
            elif esperando_nome_secao == "titulo": titulo = f"{titulo} {numeral}"
            elif esperando_nome_secao == "capitulo": capitulo = f"{capitulo} {numeral}"
            elif esperando_nome_secao == "secao": secao = f"{secao} {numeral}"
            continue

        # -- Headers de estrutura --
        if REGEX_SECAO_HEADER.match(linha_clean) and len(linha_clean) < 80:
            flush_buffer(artigo_label_atual)
            u = linha_clean.upper()
            if "LIVRO" in u:
                livro = linha_clean; titulo = subtitulo = capitulo = secao = ""
                livro_nome = titulo_nome = subtitulo_nome = capitulo_nome = secao_nome = ""
                # PL-19 Estagio 2: reset notas_legais, controle e alteracoes por nivel
                livro_notas = titulo_notas = subtitulo_notas = capitulo_notas = secao_notas = []
                livro_const = titulo_const = subtitulo_const = capitulo_const = secao_const = []
                livro_alt = titulo_alt = subtitulo_alt = capitulo_alt = secao_alt = []
                esperando_nome_secao = "livro"
            elif "SUBTÍTULO" in u or "SUBTITULO" in u:
                subtitulo = linha_clean; capitulo = secao = ""
                subtitulo_nome = capitulo_nome = secao_nome = ""
                subtitulo_notas = capitulo_notas = secao_notas = []
                subtitulo_const = capitulo_const = secao_const = []
                subtitulo_alt = capitulo_alt = secao_alt = []
                esperando_nome_secao = "subtitulo"
            elif "TÍTULO" in u or "TITULO" in u:
                titulo = linha_clean; subtitulo = capitulo = secao = ""
                titulo_nome = subtitulo_nome = capitulo_nome = secao_nome = ""
                titulo_notas = subtitulo_notas = capitulo_notas = secao_notas = []
                titulo_const = subtitulo_const = capitulo_const = secao_const = []
                titulo_alt = subtitulo_alt = capitulo_alt = secao_alt = []
                esperando_nome_secao = "titulo"
            elif "CAPÍTULO" in u or "CAPITULO" in u:
                capitulo = linha_clean; secao = ""
                capitulo_nome = secao_nome = ""
                capitulo_notas = secao_notas = []
                capitulo_const = secao_const = []
                capitulo_alt = secao_alt = []
                esperando_nome_secao = "capitulo"
            elif "SEÇÃO" in u or "SECAO" in u:
                secao = linha_clean; secao_nome = ""
                secao_notas = []; secao_const = []; secao_alt = []
                esperando_nome_secao = "secao"
            continue

        # -- Nomes descritivos de secao --
        # 2026-04-08 fix: linha_for_match strip markers (...) ANTES do length
        # check + first-letter check. Resolve dois bugs:
        # 1) CF88 TÍTULO IX: nome "Das Disposições Constitucionais Gerais"
        #    seguido de 4x "(Revogado pela EC nº 28...)" repetidos — linha
        #    original > 200 chars, falhava o length check;
        # 2) LGPD CAPÍTULO IX (apos split_inline_headers): linha comeca com
        #    "(Redação dada...)" entao falha o `^[A-ZÀ-Ú]` check.
        # Os markers ainda sao capturados via extrair_alteracoes/notas_legais
        # que rodam sobre nome_parte (linha_clean original).
        linha_for_match = re.sub(r'\s*\([^)]+\)', '', linha_clean).strip()
        is_nome_secao = REGEX_NOME_SECAO.match(linha_for_match) and len(linha_for_match) < 200
        is_nome_permissivo = (
            esperando_nome_secao and len(linha_for_match) < 200
            and not REGEX_ARTIGO.match(linha_clean)
            and not REGEX_SECAO_HEADER.match(linha_clean)
            and not REGEX_CONTINUACAO_HEADER.match(linha_clean)
            and re.match(r'^[A-ZÀ-Ú]', linha_for_match)
        )

        if is_nome_secao or is_nome_permissivo:
            if esperando_nome_secao:
                m_num = re.match(r'^([IVXLCDM]+(?:-[A-Z])?)\s+(.*)', linha_clean)
                if m_num:
                    numeral_extra, nome_parte = m_num.group(1), m_num.group(2)
                else:
                    numeral_extra, nome_parte = None, linha_clean
                # PL-19 Estagio 2: capturar notas/controle/alteracoes ANTES de limpar
                _notas_aqui = extrair_notas_legais(nome_parte)
                _controle_aqui = extrair_controle_constitucionalidade(nome_parte)
                _alt_aqui = extrair_alteracoes(nome_parte, escopo=esperando_nome_secao)
                # PL-13 Bug D: remove markers de alteracao do nome capturado
                nome_parte = limpar_marker_hierarquia(nome_parte)

                if esperando_nome_secao == "livro":
                    if numeral_extra: livro = f"{livro} {numeral_extra}"
                    livro_nome = nome_parte
                    livro_notas = _notas_aqui
                    livro_const = _controle_aqui
                    livro_alt = _alt_aqui
                elif esperando_nome_secao == "titulo":
                    if numeral_extra: titulo = f"{titulo} {numeral_extra}"
                    titulo_nome = nome_parte
                    titulo_notas = _notas_aqui
                    titulo_const = _controle_aqui
                    titulo_alt = _alt_aqui
                elif esperando_nome_secao == "subtitulo":
                    if numeral_extra: subtitulo = f"{subtitulo} {numeral_extra}"
                    subtitulo_nome = nome_parte
                    subtitulo_notas = _notas_aqui
                    subtitulo_const = _controle_aqui
                    subtitulo_alt = _alt_aqui
                elif esperando_nome_secao == "capitulo":
                    if numeral_extra: capitulo = f"{capitulo} {numeral_extra}"
                    capitulo_nome = nome_parte
                    capitulo_notas = _notas_aqui
                    capitulo_const = _controle_aqui
                    capitulo_alt = _alt_aqui
                elif esperando_nome_secao == "secao":
                    if numeral_extra: secao = f"{secao} {numeral_extra}"
                    secao_nome = nome_parte
                    secao_notas = _notas_aqui
                    secao_const = _controle_aqui
                    secao_alt = _alt_aqui
                esperando_nome_secao = None
                continue
            elif is_nome_secao:
                # PL-19 Estagio 2: capturar antes de limpar
                _notas_aqui = extrair_notas_legais(linha_clean)
                _controle_aqui = extrair_controle_constitucionalidade(linha_clean)
                # PL-13 Bug D: remove markers de alteracao do nome capturado
                nome_secao = limpar_marker_hierarquia(linha_clean)
                if titulo and not titulo_nome:
                    titulo_nome = nome_secao
                    titulo_notas = _notas_aqui
                    titulo_const = _controle_aqui
                    titulo_alt = extrair_alteracoes(linha_clean, escopo="titulo")
                elif capitulo and not capitulo_nome:
                    capitulo_nome = nome_secao
                    capitulo_notas = _notas_aqui
                    capitulo_const = _controle_aqui
                    capitulo_alt = extrair_alteracoes(linha_clean, escopo="capitulo")
                elif secao and not secao_nome:
                    secao_nome = nome_secao
                    secao_notas = _notas_aqui
                    secao_const = _controle_aqui
                    secao_alt = extrair_alteracoes(linha_clean, escopo="secao")
                continue

        esperando_nome_secao = None

        # -- Detecta inicio de artigo --
        match_art = REGEX_ARTIGO.match(linha_clean)
        if match_art:
            num_str = match_art.group(1)
            sufixo = (match_art.group(2) or "").strip()
            try:
                num_atual = parse_art_num(num_str)
            except ValueError:
                num_atual = None
            if num_atual is not None:
                classificacao = classificar_linha_artigo(linha_clean, num_atual, sufixo, ultimo_num_artigo)
                if classificacao == 'novo_artigo':
                    flush_buffer(artigo_label_atual)
                    # Normaliza separador de milhar: "1337" → "1.337" (Planalto CC Art. 1337)
                    if '.' not in num_str and num_atual >= 1000:
                        num_str_novo = f"{num_atual:,}".replace(',', '.')
                        linha_clean = linha_clean.replace(f"Art. {num_str}", f"Art. {num_str_novo}", 1)
                        num_str = num_str_novo
                    sufixo_norm = f"-{sufixo}" if sufixo else ""
                    artigo_label_atual = f"Art. {num_str}{sufixo_norm}"
                    if em_transitorias:
                        artigo_label_atual += " (ADCT)"
                    ultimo_num_artigo = num_atual

        buffer.append(linha_clean)

    flush_buffer(artigo_label_atual)

    # Dedup
    vistos = {}
    for b in blocos:
        chave = b["artigo"]
        if chave not in vistos or len(b["texto_limpo"]) > len(vistos[chave]["texto_limpo"]):
            vistos[chave] = b
    return list(vistos.values())


# =====================================================================
#  EXTRACAO PRINCIPAL
# =====================================================================

def parse_law(clean_text, sigla, versao, url, data_ext, config):
    """clean_text -> blocos enriquecidos (extrair_estrutura + guardrail + overrides
    do known_issues + lapides + dedup). PURA/deterministica: sem HTTP/DB/capture_id.
    Extraida de extrair_lei pra permitir o golden test (clean.txt commitado -> JSON)."""
    blocos = extrair_estrutura(clean_text, sigla, versao, url, data_ext, config)

    # Guardrail: sem NENHUM artigo real "Art. N", o parser não enxergou a estrutura
    # (ex: tudo caiu como EMENTA) — sinal de encoding/HTML corrompido. Aborta antes de
    # gerar JSON e antes de qualquer ingestão/embedding.
    if not any(re.match(r"Art\.\s*\d", (b.get("artigo") or "")) for b in blocos):
        raise RuntimeError(
            f"{sigla}: extração sem nenhum 'Art. N' ({len(blocos)} blocos) — parser não achou "
            f"estrutura (provável encoding/HTML corrompido). JSON não foi gerado.")

    # Overrides manuais
    ki_path = os.path.join(os.path.dirname(__file__), "known_issues.json")
    ki = {}
    if os.path.exists(ki_path):
        with open(ki_path, encoding="utf-8") as f:
            ki = json.load(f)
        cap_nomes = ki.get("overrides_pos_extracao", {}).get("capitulo_nome", {}).get(sigla, {})
        if cap_nomes:
            for bloco in blocos:
                cap = bloco.get("capitulo", "")
                if cap in cap_nomes and not bloco.get("capitulo_nome"):
                    bloco["capitulo_nome"] = cap_nomes[cap]
                    pp = []
                    for n, nf in [("titulo","titulo_nome"),("capitulo","capitulo_nome"),("secao","secao_nome")]:
                        v = bloco.get(n, ""); nm = bloco.get(nf, "")
                        if v: pp.append(f"{v} — {nm}" if nm else v)
                    bloco["path_hierarquico"] = " > ".join(pp)

        # Override titulo_nome (mesmo padrao do capitulo_nome). Necessario quando
        # o parser nao captura o nome do titulo (ex: CF88 TÍTULO IX onde o nome
        # vem em linha seguinte com markers de revogacao repetidos).
        tit_nomes = ki.get("overrides_pos_extracao", {}).get("titulo_nome", {}).get(sigla, {})
        if tit_nomes:
            for bloco in blocos:
                tit = bloco.get("titulo", "")
                if tit in tit_nomes and not bloco.get("titulo_nome"):
                    bloco["titulo_nome"] = tit_nomes[tit]
                    pp = []
                    for n, nf in [("livro","livro_nome"),("titulo","titulo_nome"),("subtitulo","subtitulo_nome"),("capitulo","capitulo_nome"),("secao","secao_nome")]:
                        v = bloco.get(n, ""); nm = bloco.get(nf, "")
                        if v: pp.append(f"{v} — {nm}" if nm else v)
                    bloco["path_hierarquico"] = " > ".join(pp)

        # Override notas_legais — adiciona notas_legais especificas a artigos
        # selecionados (ex: CLT 554-575 nao recepcionados pela CF88 Art. 8°).
        # Reusa estrutura existente sem alterar texto_limpo nem status. As notas
        # ficam disponiveis pro Justina renderizar como aviso doutrinario.
        notas_overrides = ki.get("overrides_pos_extracao", {}).get("notas_legais", {}).get(sigla, {})
        if notas_overrides:
            for bloco in blocos:
                art = bloco.get("artigo", "")
                if art.startswith("_"):
                    continue
                if art in notas_overrides:
                    existing = bloco.get("notas_legais", []) or []
                    existing_keys = {(n.get("tipo"), n.get("referencia")) for n in existing}
                    for nova in notas_overrides[art]:
                        chave = (nova.get("tipo"), nova.get("referencia"))
                        if chave not in existing_keys:
                            existing.append(nova)
                            existing_keys.add(chave)
                    bloco["notas_legais"] = existing

        # FIX 36: Override remover_alteracao — remove markers incorretamente atribuídos
        rem_alt = ki.get("overrides_pos_extracao", {}).get("remover_alteracao", {}).get(sigla, {})
        if rem_alt:
            for bloco in blocos:
                art = bloco.get("artigo", "")
                if art in rem_alt:
                    normas_remover = rem_alt[art]
                    antes = len(bloco.get("alteracoes", []))
                    bloco["alteracoes"] = [
                        a for a in bloco.get("alteracoes", [])
                        if a.get("norma") not in normas_remover
                    ]
                    if len(bloco["alteracoes"]) < antes:
                        print(f"    [override] {art}: removidas {antes - len(bloco['alteracoes'])} alteracoes incorretas")

    # -- Lápides: chunks para artigos revogados ausentes do Planalto --
    faltantes = ki.get("artigos_faltantes_verificados", {}).get(sigla, {})
    artigos_existentes = {b["artigo"] for b in blocos}
    lapides_count = 0
    for art_num, motivo in faltantes.items():
        if art_num.startswith("_"):
            continue
        artigo_label = f"Art. {art_num}"
        if artigo_label in artigos_existentes:
            continue
        art_slug = re.sub(r'[^\w]', '_', art_num).strip('_').lower()
        artigo_id = re.sub(r'_+', '_', f"{sigla.lower()}_art_{art_slug}")
        blocos.append({
            "id": artigo_id, "lei": sigla, "versao": versao,
            "versao_consolidada": True,
            "artigo": artigo_label,
            "livro": "", "livro_nome": "",
            "titulo": "", "titulo_nome": "",
            "subtitulo": "", "subtitulo_nome": "",
            "capitulo": "", "capitulo_nome": "",
            "secao": "", "secao_nome": "",
            "path_hierarquico": "",
            "texto_limpo": f"{artigo_label} — {motivo}. Artigo ausente da versão compilada do Planalto.",
            "status": "revogado",
            "vetos_parciais": [],
            "alteracoes": [{"tipo": "revogado", "norma": motivo.split("(")[0].strip(), "escopo": "artigo"}] if motivo else [],
            "referencias": {"internas": [], "leis_externas": [], "constituicao": False},
            "notas_legais": [],
            "controle_constitucionalidade": [],
            "hash_artigo": hash_texto(f"{artigo_label} — {motivo}"),
            "url_fonte": url,
            "data_extracao": data_ext,
            "parte_num": None,
            "total_partes": None,
        })
        lapides_count += 1

    # -- Dedup redações (config-driven) --
    dedup_count = 0
    _SUFIXO_RE = re.compile(r'§\s*\d+[°ºo]?-[A-Z]|[IVXLCDM]+-[A-Z]\s*[-–—]')
    if config.get("dedup_redacoes"):
        for bloco in blocos:
            texto_orig = bloco["texto_limpo"]
            texto_limpo = dedup_redacoes_bloco(texto_orig)
            if texto_limpo != texto_orig:
                # Sanity check: nenhum dispositivo com sufixo-letra pode sumir
                sufixos_antes = set(_SUFIXO_RE.findall(texto_orig))
                sufixos_depois = set(_SUFIXO_RE.findall(texto_limpo))
                perdidos = sufixos_antes - sufixos_depois
                if perdidos:
                    print(f"  ⚠️  DEDUP ABORTADO {bloco['artigo']}: perderia {perdidos}")
                    continue  # não aplica o dedup neste bloco
                if len(texto_limpo.strip()) < 20:
                    print(f"  ⚠️  DEDUP ABORTADO {bloco['artigo']}: texto ficaria muito curto")
                    continue
                bloco["texto_limpo"] = texto_limpo
                bloco["hash_artigo"] = hash_texto(texto_limpo)
                dedup_count += 1
    return blocos, {"lapides": lapides_count, "dedup": dedup_count}


def extrair_lei(session, sigla, force=False):
    config = LEIS_CONFIG.get(sigla)
    if not config:
        print(f"❌ Sigla desconhecida: {sigla}"); return False

    versao, url, nome_base = config["versao"], config["url"], config["nome_base"]
    encoding = config.get("encoding")
    print(f"\n📥 Processando {sigla}...")

    try:
        response = session.get(url, timeout=120)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Erro na requisição: {e}"); return False

    # Encoding
    if encoding == "utf-16" or response.content.startswith((b'\xff\xfe', b'\xfe\xff')):
        # decode_utf16 resolve o endianness deterministicamente (BOM ou BE/LE sem BOM) e
        # entrega STR pro BS4 — nunca deixar o UnicodeDammit adivinhar em UTF-16.
        soup = BeautifulSoup(decode_utf16(response.content), "html.parser")
    elif encoding:
        soup = BeautifulSoup(response.content, "html.parser", from_encoding=encoding)
    else:
        soup = BeautifulSoup(response.content, "html.parser")
        det = soup.original_encoding
        det = det if det and det.lower() in ('utf-8','windows-1252','iso-8859-1','latin-1') else "windows-1252"
        soup = BeautifulSoup(response.content, "html.parser", from_encoding=det)

    data_ext = datetime.now().strftime("%Y-%m-%d")

    for tag in soup(["script","style","nav","header","footer","aside","meta","link","img"]):
        tag.decompose()
    for tag in soup.find_all(["s","del","strike"]):
        tag.decompose()
    for tag in soup.find_all("a"):
        if tag.get_text(strip=True) in ("Vigência","Regulamento","Vide","Nota","Ver",""):
            tag.decompose()

    text = soup.get_text(separator="\n")
    text_limpo = re.sub(
        r'^.*?(Aprova|Institui|Dispõe|O PRESIDENTE|A PRESIDENTA|'
        r'O CONGRESSO|PREÂMBULO|Faço saber|Estabelece|Regulamenta)',
        r'\1', text, flags=re.DOTALL | re.IGNORECASE
    )

    clean_text = "\n".join([
        l.replace('\xa0',' ').strip() for l in text_limpo.splitlines()
        if l.replace('\xa0',' ').strip()
    ])

    # Normaliza Art. quebrados
    clean_text = re.sub(r'(Art\.)\s*\n\s*(\d)', r'\1 \2', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\bA\s*\n\s*rt\.\s*(\d)', r'Art. \1', clean_text)
    clean_text = re.sub(r'(Art\.\s*\d+)\s*\n\s*(\d+)\s*\.', r'\1\2.', clean_text)
    clean_text = re.sub(r'(Art\.)\s*\.\s*(\d)', r'\1 \2', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'(Art\.\s*\d[\d.]*)\s*\n\s*o\s*\n\s*(-[A-Z])', r'\1\2', clean_text)
    # "Art 1.636" (sem ponto) → "Art. 1.636" — Planalto CC omite o ponto em alguns artigos
    clean_text = re.sub(r'\bArt\s+(\d)', r'Art. \1', clean_text)
    # Quebra artigos inline: "...artigo 1.638. Art. 1.636. O pai..." → duas linhas
    # Só capital "Art." (início de artigo), não lowercase "art." (referência)
    clean_text = re.sub(r'(\S)\s+(Art\.\s*\d)', r'\1\n\2', clean_text)

    # Merge de linhas falsas — marcadores base + boundary patterns da config
    extra_markers = []
    for b in config.get("boundaries", []):
        m = re.match(r'\^?(\w+)', b["pattern"])
        if m: extra_markers.append(m.group(1))
    extra_pat = "|".join(extra_markers) + "|" if extra_markers else ""

    linhas = clean_text.split('\n')
    merged = []
    for linha in linhas:
        stripped = linha.strip()
        if not stripped: continue
        is_marker = bool(re.match(
            r'^(Art\.|§|[IVXLCDM]+\s*[-–—]|[a-z]\)|'
            r'\d+[\.\)]\s|Parágrafo\s+único|LIVRO|T[IÍ]TULO|'
            r'CAP[IÍ]TULO|SE[CÇ][AÃ]O|SUBT[IÍ]TULO|'
            r'PARTE\s|DISPOSIÇÕES|' + extra_pat + r'Pena\s)',
            stripped, re.IGNORECASE
        ))
        if merged and not is_marker and not merged[-1].endswith((':',)):
            merged[-1] = merged[-1] + ' ' + stripped
        else:
            merged.append(stripped)
    clean_text = '\n'.join(merged)

    # -- Guarda upstream (defesa em profundidade): impede que o órfão nasça no
    # clean.txt novo. Mesmas regras M2/M3 do parse_law, aplicadas na origem:
    #   M3: re-junta cauda de xref ("...art. 165," + "§ 9º. (...)").
    #   M2: dropa rótulo EXATAMENTE vazio (resíduo de <strike> cujo rótulo vazou).
    # NÃO faz strip nem M1 aqui: o clean.txt PRECISA manter a anotação literal
    # ("a) (Revogada)...") pra que o parse_law preserve M1 depois. Dot-leaders
    # ("I - .....") não são vazios -> preservados.
    _linhas_guard = _merge_xref_continuation(clean_text.split('\n'))
    clean_text = '\n'.join(l for l in _linhas_guard if not _e_rotulo_vazio(l))

    # -- text_transforms da config (extension point pra casos especiais por lei) --
    for tx in config.get("text_transforms", []):
        clean_text = re.sub(tx["pattern"], tx["replace"], clean_text, flags=re.IGNORECASE | re.MULTILINE)

    # -- PL-13 sub-bloco 2e: split de inline headers (default ON) --
    # "LIVRO I DAS PESSOAS" → "LIVRO I\nDAS PESSOAS" pra que o parser de
    # extrair_estrutura possa capturar como header standalone. Leis sem
    # hierarquia interna desabilitam via "inline_headers": False na config.
    if config.get("inline_headers", True):
        clean_text = split_inline_headers(clean_text)

    # Remove cauda de padding corrompido (run longo de simbolos no fim — artefato de decode
    # de padding de espacos do Planalto; ex: 779x U+2020 no Art. 46 da LMP).
    clean_text = strip_padding_tail(clean_text)

    # Normalizacao deterministica (NFC + whitespace horizontal) — corta ruido cosmetico que
    # geraria versao espuria. Fonte fiel = raw_captures; aqui e o texto ja limpo (camada 1
    # do radar de mudancas). Nao unifica traco nem \n-vs-espaco (potencialmente semanticos).
    clean_text = normalizar_texto(clean_text)

    # PORTAO 1 (ADR 0002): content_hash = hash do TEXTO LIMPO (identidade estavel do
    # conteudo, robusta a mudancas cosmeticas no HTML). Corta custo zero se nao mudou;
    # senao grava a captura BRUTA (raw_html = bytes originais) e segue o parse.
    # Guardrail: NUL (0x00) em massa == encoding decodificado errado (o texto real vira
    # \x00+char). Abortar ALTO antes de persistir/ingerir, em vez de deixar lixo passar.
    n_nul = clean_text.count("\x00")
    if n_nul and n_nul / (len(clean_text) or 1) > 0.005:
        raise RuntimeError(
            f"{sigla}: extração corrompida — {n_nul} NUL (0x00) em {len(clean_text)} chars "
            f"({n_nul / len(clean_text):.0%}). Encoding provavelmente errado; nada foi persistido. "
            f"Revise decode_utf16/LEIS_CONFIG['{sigla}'] e re-extraia.")
    if n_nul:  # poucos NUL cosméticos: limpa e segue (Postgres rejeita NUL em text)
        clean_text = clean_text.replace("\x00", "")
    hash_atual = hash_conteudo(clean_text.encode("utf-8"))
    with db.transaction() as cur:
        hash_anterior = db.get_latest_capture_hash(cur, sigla)
        if hash_atual == hash_anterior and not force:
            print(f"⏭  {sigla} sem alterações (content_hash igual no banco) — pulando (use --force)")
            return False
        print(f"🔄 {sigla} ATUALIZADO — nova captura + re-extração" if hash_anterior
              else f"🆕 {sigla} — primeira captura")
        capture_id = db.insert_capture(
            cur, law=sigla, source_url=url, http_status=response.status_code,
            content_hash=hash_atual, raw_html=response.content,
            encoding=encoding, parser_version=PARSER_VERSION,
        )

    os.makedirs("data", exist_ok=True)
    with open(f"data/{nome_base}_{data_ext}_clean.txt", "w", encoding="utf-8") as f:
        f.write(clean_text)

    blocos, _stats = parse_law(clean_text, sigla, versao, url, data_ext, config)

    # Anota o capture_id em cada bloco -> Portao 2 liga a versao a captura bruta.
    for b in blocos:
        b["capture_id"] = str(capture_id)

    with open(f"data/{nome_base}_{data_ext}.json", "w", encoding="utf-8") as f:
        json.dump(blocos, f, ensure_ascii=False, indent=2)

    vet = sum(1 for b in blocos if b["status"] == "vetado_total")
    rev = sum(1 for b in blocos if b["status"] == "revogado")
    vig = sum(1 for b in blocos if b["status"] == "vigente")
    print(f"✅ {sigla} → {len(blocos)} blocos")
    print(f"   vigentes={vig}  vetados_total={vet}  revogados={rev}  lápides={_stats['lapides']}  dedup={_stats['dedup']}")
    print(f"   com_vetos_parciais={sum(1 for b in blocos if b.get('vetos_parciais'))}"
          f"  com_alteracoes={sum(1 for b in blocos if b.get('alteracoes'))}")
    return True


# =====================================================================
#  CLI
# =====================================================================

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass  # Python < 3.7

    parser = argparse.ArgumentParser(
        prog="extrair_leis.py",
        description="Portao 1 (ADR 0002): extrai + captura leis do Planalto (raw_captures + JSON).")
    parser.add_argument("sigla", nargs="*", metavar="SIGLA",
                        help="Uma ou mais siglas (ex: CDC CLT) ou ALL. Vazio = todas.")
    parser.add_argument("--force", action="store_true",
                        help="Re-captura mesmo com content_hash igual ao ultimo em raw_captures.")
    args = parser.parse_args()

    entradas = [s.upper() for s in args.sigla]
    if not entradas or "ALL" in entradas:
        siglas = list(LEIS_CONFIG)
    else:
        invalidas = [s for s in entradas if s not in LEIS_CONFIG]
        if invalidas:
            print(f"❌ Sigla(s) inválida(s): {', '.join(invalidas)}")
            print(f"   Siglas disponíveis: {', '.join(LEIS_CONFIG.keys())} ou ALL")
            sys.exit(1)
        siglas = list(dict.fromkeys(entradas))   # dedup preservando ordem

    os.makedirs("data", exist_ok=True)
    session = criar_sessao()
    for sigla in siglas:
        extrair_lei(session, sigla, args.force)

    print("\n🏁 Operação concluída.")