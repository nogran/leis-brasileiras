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
import hashlib, re, json, sys, os

HASHES_FILE = os.path.join(os.path.dirname(__file__), "data", "hashes.json")


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
]

def extrair_alteracoes(texto: str) -> list[dict]:
    alteracoes, vistos = [], set()
    for pattern, tipo in ALTERACAO_PATTERNS:
        for match in pattern.finditer(texto):
            norma = re.sub(r'\s+', ' ', match.group(1).strip())
            chave = f"{tipo}:{norma}"
            if chave not in vistos:
                vistos.add(chave)
                alteracoes.append({"tipo": tipo, "norma": norma})
    return alteracoes


# --- Ruido legislativo ---
NOISE_PATTERNS = [
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)[^)]{0,200}\)',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)[^)]{0,200}\)',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]{0,200}\)',                    re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]{0,200}\)',                re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Nova\s+redação\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Renumerad[oa]s?\s+[^)]{0,200}\)',                  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Suprimid[oa]s?\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\)\s*[.;,]?',                         re.IGNORECASE),
    re.compile(r'\(Suprimid[oa]s?\)\s*[.;,]?',                        re.IGNORECASE),
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',                      re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\n\s*Vigência\s*\n',      re.IGNORECASE),
    re.compile(r'\(Vigência\)',             re.IGNORECASE),
    re.compile(r'\n\s*\(Vigência\)\s*\n',  re.IGNORECASE),
]

def limpar_ruido_legislativo(texto: str) -> str:
    for pattern in NOISE_PATTERNS:
        texto = pattern.sub('', texto)
    linhas = [l for l in texto.splitlines() if l.strip()]
    return '\n'.join(linhas).strip()


def limpar_marker_hierarquia(nome: str) -> str:
    """Remove markers de alteracao legislativa de nomes hierarquicos
    (livro_nome, titulo_nome, capitulo_nome, secao_nome).
    Aplica os mesmos padroes de NOISE_PATTERNS e normaliza espacos."""
    if not nome:
        return ""
    for pattern in NOISE_PATTERNS:
        nome = pattern.sub('', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome


# --- Hashes ---
def carregar_hashes():
    if os.path.exists(HASHES_FILE):
        with open(HASHES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_hashes(hashes):
    os.makedirs(os.path.dirname(HASHES_FILE), exist_ok=True)
    with open(HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)

def hash_conteudo(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


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
INLINE_HEADER_RE = re.compile(
    r'^((?:LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)'
    r'\s+(?:[IVXLCDM]+(?:\s*-\s*[A-Z])?|[ÚU]NIC[OA]|PRELIMINAR|COMPLEMENTAR|ESPECIAL))'
    # PL-13: primeira letra do nome precisa ser MAIUSCULA. Inline flag (?-i:...)
    # desabilita IGNORECASE so nesse grupo, evitando casar citacoes inline
    # tipo "Livro II da Parte Especial deste Código" onde 'da' e lowercase.
    r'\s+((?-i:[A-ZÀ-Ú]).+)$',
    re.MULTILINE | re.IGNORECASE
)


def split_inline_headers(text: str) -> str:
    """Quebra headers de hierarquia em formato inline em duas linhas.
    Ex: 'CAPÍTULO I Da Personalidade' → 'CAPÍTULO I\\nDa Personalidade'.
    Aplicado linha-a-linha via re.MULTILINE — linhas que nao casam ficam intactas."""
    return INLINE_HEADER_RE.sub(r'\1\n\2', text)


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
    padrao_lei = re.compile(
        r'(?:Lei|Decreto(?:-Lei)?|Lei Complementar|Medida Provisória|Emenda Constitucional)\s+'
        r'n[°ºo]?\s*[\d\.]+(?:/\d+)?',
        re.IGNORECASE
    )
    leis_externas = sorted(set(
        re.sub(r'\s+', ' ', m.group(0)).strip()
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
        alteracoes = extrair_alteracoes(texto_raw)
        status, vetos_parciais = detectar_status_artigo(texto_raw)
        texto_limpo = limpar_ruido_legislativo(texto_raw)
        if not texto_limpo:
            buffer = []; return

        # Strip trailing section headers que sangraram do buffer
        # (último artigo antes de TÍTULO/CAPÍTULO/SEÇÃO absorve o header seguinte)
        texto_limpo = re.sub(
            r'\n(?:LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)\s+.*$',
            '', texto_limpo, flags=re.IGNORECASE
        ).strip()

        if not texto_limpo:
            buffer = []; return
        if len(texto_limpo) < 30 and status == 'vigente':
            buffer = []; return

        refs = extrair_referencias(texto_limpo, artigo_label)
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
            alteracoes = [{"tipo": "vetado", "norma": f"Veto na sanção — {versao}"}]

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
                "referencias": refs, "hash_artigo": hash_texto(parte),
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
                esperando_nome_secao = "livro"
            elif "SUBTÍTULO" in u or "SUBTITULO" in u:
                subtitulo = linha_clean; capitulo = secao = ""
                subtitulo_nome = capitulo_nome = secao_nome = ""
                esperando_nome_secao = "subtitulo"
            elif "TÍTULO" in u or "TITULO" in u:
                titulo = linha_clean; subtitulo = capitulo = secao = ""
                titulo_nome = subtitulo_nome = capitulo_nome = secao_nome = ""
                esperando_nome_secao = "titulo"
            elif "CAPÍTULO" in u or "CAPITULO" in u:
                capitulo = linha_clean; secao = ""
                capitulo_nome = secao_nome = ""; esperando_nome_secao = "capitulo"
            elif "SEÇÃO" in u or "SECAO" in u:
                secao = linha_clean; secao_nome = ""; esperando_nome_secao = "secao"
            continue

        # -- Nomes descritivos de secao --
        is_nome_secao = REGEX_NOME_SECAO.match(linha_clean) and len(linha_clean) < 200
        is_nome_permissivo = (
            esperando_nome_secao and len(linha_clean) < 200
            and not REGEX_ARTIGO.match(linha_clean)
            and not REGEX_SECAO_HEADER.match(linha_clean)
            and not REGEX_CONTINUACAO_HEADER.match(linha_clean)
            and re.match(r'^[A-ZÀ-Ú]', linha_clean)
        )

        if is_nome_secao or is_nome_permissivo:
            if esperando_nome_secao:
                m_num = re.match(r'^([IVXLCDM]+(?:-[A-Z])?)\s+(.*)', linha_clean)
                if m_num:
                    numeral_extra, nome_parte = m_num.group(1), m_num.group(2)
                else:
                    numeral_extra, nome_parte = None, linha_clean
                # PL-13 Bug D: remove markers de alteracao do nome capturado
                nome_parte = limpar_marker_hierarquia(nome_parte)

                if esperando_nome_secao == "livro":
                    if numeral_extra: livro = f"{livro} {numeral_extra}"
                    livro_nome = nome_parte
                elif esperando_nome_secao == "titulo":
                    if numeral_extra: titulo = f"{titulo} {numeral_extra}"
                    titulo_nome = nome_parte
                elif esperando_nome_secao == "subtitulo":
                    if numeral_extra: subtitulo = f"{subtitulo} {numeral_extra}"
                    subtitulo_nome = nome_parte
                elif esperando_nome_secao == "capitulo":
                    if numeral_extra: capitulo = f"{capitulo} {numeral_extra}"
                    capitulo_nome = nome_parte
                elif esperando_nome_secao == "secao":
                    if numeral_extra: secao = f"{secao} {numeral_extra}"
                    secao_nome = nome_parte
                esperando_nome_secao = None
                continue
            elif is_nome_secao:
                # PL-13 Bug D: remove markers de alteracao do nome capturado
                nome_secao = limpar_marker_hierarquia(linha_clean)
                if titulo and not titulo_nome: titulo_nome = nome_secao
                elif capitulo and not capitulo_nome: capitulo_nome = nome_secao
                elif secao and not secao_nome: secao_nome = nome_secao
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

def extrair_lei(session, sigla, hashes, force=False):
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

    # Hash check preliminar (HTML bruto) — pula processamento se identico
    hash_html = hash_conteudo(response.content)
    hash_anterior = hashes.get(sigla, {}).get("hash")

    # Encoding
    if encoding == "utf-16" or response.content.startswith((b'\xff\xfe', b'\xfe\xff')):
        soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf-16")
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

    # -- text_transforms da config (extension point pra casos especiais por lei) --
    for tx in config.get("text_transforms", []):
        clean_text = re.sub(tx["pattern"], tx["replace"], clean_text, flags=re.IGNORECASE | re.MULTILINE)

    # -- PL-13 sub-bloco 2e: split de inline headers (default ON) --
    # "LIVRO I DAS PESSOAS" → "LIVRO I\nDAS PESSOAS" pra que o parser de
    # extrair_estrutura possa capturar como header standalone. Leis sem
    # hierarquia interna desabilitam via "inline_headers": False na config.
    if config.get("inline_headers", True):
        clean_text = split_inline_headers(clean_text)

    # Hash check definitivo: compara texto limpo (ignora mudancas cosmeticas no HTML)
    hash_atual = hash_conteudo(clean_text.encode("utf-8"))
    if hash_atual == hash_anterior and not force:
        print(f"⏭  {sigla} sem alterações desde {hashes[sigla]['data']} — pulando (use --force)")
        return False
    if hash_anterior and hash_atual != hash_anterior:
        print(f"🔄 {sigla} ATUALIZADO desde {hashes[sigla]['data']} — re-extraindo")
    elif not hash_anterior:
        print(f"🆕 {sigla} — primeira extração")

    os.makedirs("data", exist_ok=True)
    with open(f"data/{nome_base}_{data_ext}_clean.txt", "w", encoding="utf-8") as f:
        f.write(clean_text)

    blocos = extrair_estrutura(clean_text, sigla, versao, url, data_ext, config)

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
            "alteracoes": [{"tipo": "revogado", "norma": motivo.split("(")[0].strip()}] if motivo else [],
            "referencias": {"internas": [], "leis_externas": [], "constituicao": False},
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

    with open(f"data/{nome_base}_{data_ext}.json", "w", encoding="utf-8") as f:
        json.dump(blocos, f, ensure_ascii=False, indent=2)

    hashes[sigla] = {"hash": hash_atual, "data": data_ext, "blocos": len(blocos), "url": url}

    vet = sum(1 for b in blocos if b["status"] == "vetado_total")
    rev = sum(1 for b in blocos if b["status"] == "revogado")
    vig = sum(1 for b in blocos if b["status"] == "vigente")
    print(f"✅ {sigla} → {len(blocos)} blocos")
    print(f"   vigentes={vig}  vetados_total={vet}  revogados={rev}  lápides={lapides_count}  dedup={dedup_count}")
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

    os.makedirs("data", exist_ok=True)
    args = sys.argv[1:]
    force = "--force" in args
    siglas_args = [a for a in args if a != "--force"]
    arg = siglas_args[0].upper() if siglas_args else "ALL"

    session = criar_sessao()
    hashes = carregar_hashes()

    if arg == "ALL":
        for sigla in LEIS_CONFIG:
            extrair_lei(session, sigla, hashes, force)
    elif arg in LEIS_CONFIG:
        extrair_lei(session, arg, hashes, force)
    else:
        print(f"❌ Argumento inválido: {arg}")
        print(f"   Siglas disponíveis: {', '.join(LEIS_CONFIG.keys())} ou ALL")
        sys.exit(1)

    salvar_hashes(hashes)
    print("\n🏁 Operação concluída.")