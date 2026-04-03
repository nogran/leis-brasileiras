import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
import hashlib, re, json, sys, os

HASHES_FILE = os.path.join(os.path.dirname(__file__), "data", "hashes.json")

# ─── v3 CHANGELOG ────────────────────────────────────────────────────────────
# FIX 1: detectar_status_artigo → distingue veto total vs parcial
# FIX 2: title bleed → detecta e remove nomes de seção do buffer
# FIX 3: referencias_cruzadas → remove auto-referência, separa internas/externas
# FIX 4: alteracoes → extrai markers ANTES de limpar, preserva histórico legislativo
# FIX 5: artigos totalmente vetados incluídos (threshold < 30 chars removido p/ vetados)
# FIX 6: IDs normalizados (sem duplo underscore)
# FIX 7: path_hierarquico semântico (nomes dos títulos/capítulos, não só números)
# ─── v4 CHANGELOG ────────────────────────────────────────────────────────────
# FIX 18: REGEX_ARTIGO → sufixo EXIGE hífen; "Art. 1° O ..." não gera mais "-O"
# FIX 19: off-by-one → flush_buffer ANTES de atualizar título/capítulo/seção
# FIX 20: REGEX_SECAO_HEADER → strict end-of-line; impede contaminação por texto
#         ("título respectivo.", "Capítulo, nos termos..." não casam mais)
# FIX 21: headers partidos ("CAPÍTULO\nVI-A") → concatenação de linhas de continuação
# FIX 22: REGEX_NOME_SECAO → aceita ALL-CAPS ("DA PREVENÇÃO E DO TRATAMENTO...")
# FIX 23: normaliza "SeçãoI" → "Seção I" (espaço faltante no Planalto)
# FIX 24: regex feminino/plural — (?:a)? → [oa]s? em TODOS os padrões de marcador
#         "Incluído(?:a)?" casava "Incluídoa" mas NÃO "Incluída" — 26+ artigos afetados
# FIX 25: vetos parciais — handle multi-line, Parágrafo único, alíneas
# FIX 26: "Art. . 154" → "Art. 154" (ponto duplo residual após cleanup)
# ─────────────────────────────────────────────────────────────────────────────


# ─── FIX 4 + FIX 24: Padrões de alteração legislativa ────────────────────────
# FIX 24: (?:a)? → [oa]s? — "Incluído(?:a)?" casava "Incluído"/"Incluídoa"
# mas NÃO "Incluída". Afetava 25+ artigos em 8 leis.
ALTERACAO_PATTERNS = [
    (re.compile(r'\(Redação dada (?:pela|pelo|ao)\s+(.+?)\)',       re.IGNORECASE | re.DOTALL), "redacao_dada"),
    (re.compile(r'\(Incluíd[oa]s? (?:pela|pelo|ao)\s+(.+?)\)',     re.IGNORECASE | re.DOTALL), "incluido"),
    (re.compile(r'\(Renumerad[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "renumerado"),
    (re.compile(r'\(Acrescentad[oa]s?\s+(?:pela|pelo|ao)\s+(.+?)\)', re.IGNORECASE | re.DOTALL), "acrescentado"),
    (re.compile(r'\(Nova redação\s+(?:pela|pelo|ao)\s+(.+?)\)',     re.IGNORECASE | re.DOTALL), "nova_redacao"),
]

def extrair_alteracoes(texto: str) -> list[dict]:
    """
    FIX 4: Extrai markers de alteração legislativa ANTES de limpar o texto.
    Retorna lista de {"tipo": "redacao_dada", "norma": "Lei nº 14.181, de 2021"}.
    """
    alteracoes = []
    vistos = set()
    for pattern, tipo in ALTERACAO_PATTERNS:
        for match in pattern.finditer(texto):
            norma = re.sub(r'\s+', ' ', match.group(1).strip())
            chave = f"{tipo}:{norma}"
            if chave not in vistos:
                vistos.add(chave)
                alteracoes.append({"tipo": tipo, "norma": norma})
    return alteracoes


# ─── Ruído legislativo a remover do texto (aplicado APÓS extração de alterações)
# FIX 24: [oa]s? para casar feminino e plural
# FIX 27: Duas passadas — (1) marcadores com ) dentro de 200 chars,
#         (2) fallback para parênteses não fechados (para até o ano "de YYYY")
#         Também usa \s+ em vez de espaço literal (Planalto quebra linhas no meio)
NOISE_PATTERNS = [
    # ── Passada 1: marcadores com ) fechado dentro de 200 chars ──
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)[^)]{0,200}\)',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)[^)]{0,200}\)',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]{0,200}\)',                    re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]{0,200}\)',                re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Nova\s+redação\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Renumerad[oa]s?\s+[^)]{0,200}\)',                  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Suprimid[oa]s?\s+[^)]{0,200}\)',                   re.IGNORECASE | re.DOTALL),
    # ── Formas curtas com pontuação após ) ──
    re.compile(r'\(Revogad[oa]s?\)\s*[.;,]?',                         re.IGNORECASE),
    re.compile(r'\(Suprimid[oa]s?\)\s*[.;,]?',                        re.IGNORECASE),
    # ── Passada 2: fallback para ) não fechado (para no ano "de YYYY") ──
    re.compile(r'\(Redação\s+dada\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',  re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Incluíd[oa]s?\s+(?:pela|pelo|ao)\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',   re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Revogad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',                      re.IGNORECASE | re.DOTALL),
    re.compile(r'\(Acrescentad[oa]s?\s+[^)]*?\bde\s+[\d./]*\d{4}[:\s.]*',                   re.IGNORECASE | re.DOTALL),
    # ── Vigência ──
    re.compile(r'\n\s*Vigência\s*\n',      re.IGNORECASE),
    re.compile(r'\(Vigência\)',             re.IGNORECASE),
    re.compile(r'\n\s*\(Vigência\)\s*\n',  re.IGNORECASE),
]

def limpar_ruido_legislativo(texto: str) -> str:
    for pattern in NOISE_PATTERNS:
        texto = pattern.sub('', texto)
    linhas = [l for l in texto.splitlines() if l.strip()]
    return '\n'.join(linhas).strip()


# ─── Hashes ──────────────────────────────────────────────────────────────────
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


# ─── HTTP ─────────────────────────────────────────────────────────────────────
def criar_sessao():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LegalBot/2.0)"})
    return session


# ─── Configuração das leis ────────────────────────────────────────────────────
LEIS_CONFIG = {
    "CDC":  ("Lei 8.078/1990",            "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",                     "cdc"),
    "CLT":  ("Decreto-Lei 5.452/1943",    "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm",            "clt"),
    "CC":   ("Lei 10.406/2002",           "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",               "codigo_civil"),
    "CPC":  ("Lei 13.105/2015",           "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/L13105compilada.htm",  "cpc"),
    "CF88": ("Constituição Federal 1988", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",               "cf88"),
    "CP":   ("Decreto-Lei 2.848/1940",    "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",            "cp"),
    "LGPD": ("Lei 13.709/2018",           "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm",  "lgpd"),
    "ECA":  ("Lei 8.069/1990",            "https://www.planalto.gov.br/ccivil_03/leis/L8069Compilado.htm",                     "eca"),
    "LI":   ("Lei 8.245/1991",            "https://www.planalto.gov.br/ccivil_03/leis/L8245compilado.htm",                     "lei_inquilinato"),
    "LMP":  ("Lei 11.340/2006",           "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm",           "lei_maria_penha"),
    "MEI":  ("Lei Complementar 123/2006", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm",                        "mei"),
    "LT":   ("Lei 6.019/1974",            "https://www.planalto.gov.br/ccivil_03/leis/l6019compilado.htm",                    "lei_terceirizacao"),
    "CP2":  ("Lei 12.414/2011",           "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12414.htm",           "cadastro_positivo"),
}


# ─── Chunking com overlap ────────────────────────────────────────────────────
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


# ─── Regex de artigo ─────────────────────────────────────────────────────────
# FIX 8 + 10 + 13 + 17 + 18: Case-sensitive, end-of-line, dotted numbers, ordinal before suffix
# FIX 18: sufixo EXIGE hífen COLADO. "Art. 42-A" casa, "Art. 142 - O" não casa.
# v4.1: removeu \s* ao redor do hífen — CLT usa "Art. 142 - O empregador..."
# que com \s*-\s* ainda capturava "O" como sufixo.
REGEX_ARTIGO = re.compile(
    r'^Art\.?\s*(\d[\d.]*\d|\d+)'       # "1.000" ou "999" ou "7"
    r'(?:[°ºo])?'                        # ordinal pode vir ANTES do sufixo
    r'(?:-([A-Z](?:-[A-Z])*))?'         # sufixo REQUER hífen colado: "-A", "-B"
    r'(?:[°ºo])?'                        # ordinal pode vir DEPOIS também
    r'(?:[\.\s]|$)'                      # separador ou fim de linha
)

def parse_art_num(num_str: str) -> int:
    """Converte '1.000' → 1000, '999' → 999."""
    return int(num_str.replace('.', ''))

# ─── FIX 2 + FIX 22: Regex para nomes descritivos de seção ──────────────────
# Linhas como "Dos Direitos do Consumidor", "DA PROTEÇÃO À SAÚDE E SEGURANÇA"
# FIX 22: IGNORECASE no prefixo para aceitar ALL-CAPS do Planalto em leis recentes
REGEX_NOME_SECAO = re.compile(
    r'^(Dos?|Das?|Disposições)\s+[A-ZÀ-Ú][\w\sÀ-ú,()áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]+$',
    re.IGNORECASE
)


# ─── Classificação de linha de artigo ────────────────────────────────────────
def classificar_linha_artigo(linha: str, num_atual: int, sufixo: str, ultimo_num: int) -> str:
    MARCADORES_CITACAO_CONFIAVEIS = [
        r'da lei n[°º]?\s*\d',
        r'do decreto n[°º]?\s*\d',
        r'da lei complementar n',
        r'do código civil',
        r'desta lei',                    # FIX 9: "art. 12 desta Lei Complementar"
        r'da constituição',              # FIX 9: "art. 5° da Constituição Federal"
    ]
    linha_lower = linha[:120].lower()
    
    # FIX 9: Se a linha contém marcador de referência a outra norma,
    # trata como citação SOMENTE se o número também for suspeito.
    # "art. 966 da Lei nº 10.406" (salto +954) → citação ✅
    # "Art. 110. ... da Lei nº 7.347" (sequência +1) → novo artigo ✅
    for marcador in MARCADORES_CITACAO_CONFIAVEIS:
        if re.search(marcador, linha_lower):
            if num_atual > ultimo_num + 200 or num_atual < ultimo_num - 10:
                return 'citacao'

    # FIX 9: Salto forward absurdo (ex: Art. 12 → Art. 966)
    # Nenhuma lei brasileira tem gaps > 200 entre artigos consecutivos.
    if num_atual > ultimo_num + 200:
        return 'citacao'

    # Backward jump grande → provável citação
    if num_atual < ultimo_num - 15:
        return 'citacao'

    if num_atual == ultimo_num and sufixo:
        return 'novo_artigo'

    if num_atual >= ultimo_num:
        return 'novo_artigo'

    return 'novo_artigo'


# ─── FIX 1: Detecção de status corrigida ────────────────────────────────────
def detectar_status_artigo(texto_artigo: str) -> tuple[str, list[str]]:
    """
    Retorna (status, vetos_parciais).
    
    FIX 1:  Distingue veto total vs parcial.
    FIX 11: Roda no texto RAW (antes de limpar).
            - Artigos curtos (< 200 chars): checa texto completo
              → "Art. 11.\\n(Vetado)\\n." → vetado_total ✅
            - Artigos longos (>= 200 chars): checa só primeira linha
              → Art. 5 com §1° Vetado → NÃO marca artigo inteiro ✅
    """
    t = texto_artigo.strip()
    
    # Strip amendment markers before analysis — they pollute corpo detection.
    # "Art. 54-E. (VETADO).\n(Incluído pela Lei nº 14.181)" → "Art. 54-E. (VETADO)."
    # FIX 24: [oa]s? para casar feminino/plural
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
    
    # ── Para artigos curtos, analisa o corpo completo ──
    # Para longos, analisa só a primeira linha (evita falso positivo do Art. 5/6)
    if len(t) < 200:
        corpo_ref = t_lower
    else:
        corpo_ref = t_lower.split('\n')[0].strip()
    
    corpo = re.sub(r'^art\.\s*[\d.]+[\w-]*[°º]?\s*\.?\s*', '', corpo_ref, count=1).strip()
    corpo_limpo = re.sub(r'[\s.\-–—()]', '', corpo)
    
    # ── Artigo INTEIRAMENTE vetado ──
    if corpo_limpo.startswith('vetado'):
        return ('vetado_total', [])
    
    # ── Artigo INTEIRAMENTE revogado/suprimido ──
    if corpo_limpo.startswith(('revogado', 'revogada', 'revogados', 'suprimido', 'suprimida')):
        return ('revogado', [])
    
    # ── FIX 14: Fallback para artigos curtos com marcador em qualquer posição ──
    # Cobre edge cases como "Art. 1.620. a 1.629. (Revogados pela Lei...)"
    # e "Art. 686. (Suprimido pelo Decreto-Lei...)"
    # NÃO inclui vetado aqui — artigos curtos podem ter vetos PARCIAIS como
    # "IX - (Vetado)" que devem ser tratados pelo detector de vetos parciais abaixo.
    if len(t) < 200:
        t_lower_full = t.lower()
        if re.search(r'\(suprimid', t_lower_full):
            return ('revogado', [])
        if re.search(r'\(revogad', t_lower_full):
            return ('revogado', [])
    
    # ── Dispositivos vetados internamente (sempre checa texto completo) ──
    # FIX 25: Normaliza newlines para veto detection (Planalto quebra linhas entre
    # o dispositivo e "(Vetado)"). Também adiciona "Parágrafo único" e alíneas.
    t_veto = re.sub(r'\s*\n\s*', ' ', t)  # colapsa newlines para detecção
    # FIX 25.1: Normaliza ordinal solto "§ 2 o" → "§ 2°" (Planalto gera "§ 2\no\n")
    t_veto = re.sub(r'(§\s*\d+)\s+o\b', r'\1°', t_veto)
    
    vetos_parciais = []
    seen_vetos = set()
    
    # Parágrafos: "§ 1° (Vetado)" / "§ 2o (VETADO)"
    for m in re.finditer(
        r'(§\s*\d+[°ºo]?)\s*[-–—.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?',
        t_veto
    ):
        label = m.group(1).strip()
        if label not in seen_vetos:
            seen_vetos.add(label)
            vetos_parciais.append(label)
    
    # Parágrafo único: "Parágrafo único. (Vetado)"
    for m in re.finditer(
        r'(Parágrafo\s+único)\s*[.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?',
        t_veto, re.IGNORECASE
    ):
        label = "Parágrafo único"
        if label not in seen_vetos:
            seen_vetos.add(label)
            vetos_parciais.append(label)

    # Incisos romanos: "IX - (Vetado)" / "V (VETADO)"
    for m in re.finditer(
        r'([IVXLCDM]+)\s*[-–—.\s]+\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?',
        t_veto
    ):
        label = m.group(1).strip()
        if label not in seen_vetos:
            seen_vetos.add(label)
            vetos_parciais.append(label)
    
    # Alíneas: "a) (Vetado)" / "c) (VETADO)"
    for m in re.finditer(
        r'\b([a-z]\))\s*[-–—.\s]*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?',
        t_veto
    ):
        label = m.group(1).strip()
        if label not in seen_vetos:
            seen_vetos.add(label)
            vetos_parciais.append(label)

    # FIX 28: Sub-artigos sem hífen: "Art. 401A. (VETADO)" (CLT)
    for m in re.finditer(
        r'(Art\.\s*\d+[A-Z])\s*\.\s*\(?\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)?',
        t_veto
    ):
        label = m.group(1).strip()
        if label not in seen_vetos:
            seen_vetos.add(label)
            vetos_parciais.append(label)

    # FIX 28: Fallback — qualquer (VETADO) restante não capturado acima
    # Conta ocorrências totais de (VETADO) vs já capturadas
    total_vetados_no_texto = len(re.findall(
        r'\(\s*[Vv][Ee][Tt][Aa][Dd][Oo]\s*\)', t_veto
    ))
    if total_vetados_no_texto > len(vetos_parciais):
        # Há vetos não capturados — adicionar como genéricos
        faltam = total_vetados_no_texto - len(vetos_parciais)
        for i in range(faltam):
            label = f"dispositivo vetado {len(vetos_parciais)+1}"
            vetos_parciais.append(label)
    
    if vetos_parciais:
        return ('vigente', vetos_parciais)
    
    # ── Revogado/Suprimido em qualquer parte do texto (usa texto original) ──
    # Fallback para artigos longos que não foram pegos acima
    if re.search(r'\((?:revogad|suprimid)', t.lower()):
        return ('revogado', [])
    
    return ('vigente', [])


# ─── FIX 3: Extração de referências cruzadas ────────────────────────────────
def extrair_referencias(texto: str, artigo_atual: str) -> dict:
    """
    v2 BUG: incluía auto-referência (Art. 7 → ["Art. 7"]).
            73% dos chunks tinham apenas self-ref → campo inútil.
    
    FIX: filtra auto-ref, separa internas/externas/CF.
    """
    art_num_atual = re.sub(r'^Art\.\s*', '', artigo_atual)
    
    # Referências internas
    padrao_interno = re.compile(
        r'arts?\.\s*(\d+(?:-[A-Z])?)'
        r'(?:\s*,\s*(?:§\s*\d+|inciso\s+[IVXLCDM]+|parágrafo\s+único))?',
        re.IGNORECASE
    )
    internas = set()
    for m in padrao_interno.finditer(texto):
        num = m.group(1)
        if num != art_num_atual:
            internas.add(f"Art. {num}")
    
    # Referências a leis externas
    padrao_lei = re.compile(
        r'(?:Lei|Decreto(?:-Lei)?|Lei Complementar|Medida Provisória)\s+'
        r'n[°º]?\s*([\d\.]+(?:/\d+)?)',
        re.IGNORECASE
    )
    leis_externas = sorted(set(m.group(0).strip() for m in padrao_lei.finditer(texto)))
    
    # Referência à CF
    ref_cf = bool(re.search(r'Constitui[çc][ãa]o\s+Federal', texto, re.IGNORECASE))
    
    return {
        "internas": sorted(internas),
        "leis_externas": leis_externas,
        "constituicao": ref_cf,
    }


# ─── Extração de estrutura ───────────────────────────────────────────────────
def extrair_estrutura(texto: str, sigla: str, versao: str, url: str, data_ext: str) -> list[dict]:
    livro, titulo, subtitulo, capitulo, secao = "", "", "", "", ""
    # FIX 7: nomes semânticos
    livro_nome, titulo_nome, capitulo_nome, secao_nome = "", "", "", ""
    artigo_label_atual = "EMENTA"
    ultimo_num_artigo = 0
    ultimo_sufixo = ""
    em_transitorias = False
    blocos, buffer = [], []
    esperando_nome_secao = None

    def flush_buffer(artigo_label: str):
        nonlocal buffer
        if not buffer:
            return

        texto_raw = "\n".join(buffer).strip()
        
        # FIX 4: extrai alterações ANTES de limpar
        alteracoes = extrair_alteracoes(texto_raw)
        
        # FIX 11: detecta status no texto RAW, antes da limpeza.
        # limpar_ruido_legislativo remove "(Revogado...)" dos NOISE_PATTERNS,
        # então se rodar status detection depois, "Art. 78. (REVOGADO)" vira
        # "Art. 78." → detecta como 'vigente' → filtrado por tamanho < 30.
        status, vetos_parciais = detectar_status_artigo(texto_raw)
        
        texto_limpo = limpar_ruido_legislativo(texto_raw)
        
        if not texto_limpo:
            buffer = []
            return

        # FIX 5: só filtra por tamanho se NÃO for vetado/revogado
        if len(texto_limpo) < 30 and status == 'vigente':
            buffer = []
            return

        # FIX 3: referências sem auto-ref
        refs = extrair_referencias(texto_limpo, artigo_label)

        # FIX 7: path hierárquico semântico
        path_partes = []
        for num, nome in [(titulo, titulo_nome), (capitulo, capitulo_nome), (secao, secao_nome)]:
            if num:
                label = f"{num} — {nome}" if nome else num
                path_partes.append(label)
        path = " > ".join(path_partes) if path_partes else ""

        partes = split_com_overlap(texto_limpo)

        for i, parte in enumerate(partes):
            suffix_label = f" (Parte {i+1}/{len(partes)})" if len(partes) > 1 else ""
            
            # FIX 6: ID normalizado, sem duplo underscore
            # Remove "Art. " do slug para evitar "cdc_art_art_1"
            art_clean = re.sub(r'^Art\.?\s*', '', artigo_label)
            art_slug = re.sub(r'[^\w]', '_', art_clean).strip('_').lower()
            part_slug = f"_p{i+1}" if len(partes) > 1 else ""
            artigo_id = re.sub(r'_+', '_', f"{sigla.lower()}_art_{art_slug}{part_slug}")

            blocos.append({
                "id":                   artigo_id,
                "lei":                  sigla,
                "versao":               versao,
                "versao_consolidada":   True,
                "artigo":               f"{artigo_label}{suffix_label}",
                "livro":                livro,
                "titulo":               titulo,
                "titulo_nome":          titulo_nome,
                "subtitulo":            subtitulo,
                "capitulo":             capitulo,
                "capitulo_nome":        capitulo_nome,
                "secao":                secao,
                "secao_nome":           secao_nome,
                "path_hierarquico":     path,
                "texto_limpo":          parte,
                "status":               status,
                "vetos_parciais":       vetos_parciais if vetos_parciais else None,
                "alteracoes":           alteracoes if alteracoes else None,
                "referencias":          refs,
                "hash_artigo":          hash_texto(parte),
                "url_fonte":            url,
                "data_extracao":        data_ext,
                "parte_num":            i + 1 if len(partes) > 1 else None,
                "total_partes":         len(partes) if len(partes) > 1 else None,
            })

        buffer = []

    # FIX 20: Strict header regex — exige fim de linha após keyword + numeral opcional.
    # Impede contaminação por texto de artigo que começa com "título", "capítulo" etc.
    # Exemplos que NÃO casam mais:
    #   "título respectivo."  /  "Capítulo, nos termos do art. 201."
    #   "títulos de bolsa, mercadorias ou valores..."
    REGEX_SECAO_HEADER = re.compile(
        r'^(LIVRO|SUBT[IÍ]TULO|T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)\s*'
        r'([IVXLCDM]+(?:\s*-\s*[A-Z])?|[ÚU]NIC[OA]|PRELIMINAR|COMPLEMENTAR|ESPECIAL)?\s*$',
        re.IGNORECASE
    )

    # FIX 21+29: Continuação de header partido.
    # Detecta numerais romanos E qualificadores (COMPLEMENTAR, PRELIMINAR, etc.)
    REGEX_CONTINUACAO_HEADER = re.compile(
        r'^([IVXLCDM]+(?:\s*-\s*[A-Z])?|COMPLEMENTAR|PRELIMINAR|ESPECIAL|[ÚU]NIC[OA])\s*$',
        re.IGNORECASE
    )

    for linha in texto.split("\n"):
        linha_clean = linha.replace('\xa0', ' ').strip()
        if not linha_clean:
            continue

        # FIX 23: normaliza "SeçãoI" → "Seção I" (espaço faltante no HTML do Planalto)
        linha_clean = re.sub(
            r'^(Se[çc][ãa]o)([IVXLCDM])',
            r'\1 \2',
            linha_clean,
            flags=re.IGNORECASE,
        )

        # Detecta ADCT (Constituição)
        # FIX 15: só dispara se a linha COMEÇA com "ATO DAS DISPOSIÇÕES" (o header real).
        if linha_clean.upper().startswith("ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"):
            if ultimo_num_artigo > 0:
                flush_buffer(artigo_label_atual)  # FIX 19: flush antes de mudar contexto
                em_transitorias = True
                ultimo_num_artigo = 0

        # ── FIX 21: Continuação de header partido ("CAPÍTULO\nVI-A") ──
        # Se estamos esperando nome de seção e a linha é um numeral romano,
        # ela é a continuação do header, não o nome.
        if esperando_nome_secao and REGEX_CONTINUACAO_HEADER.match(linha_clean):
            numeral = linha_clean.strip()
            if esperando_nome_secao == "livro":
                livro = f"{livro} {numeral}"
            elif esperando_nome_secao == "subtitulo":
                subtitulo = f"{subtitulo} {numeral}"
            elif esperando_nome_secao == "titulo":
                titulo = f"{titulo} {numeral}"
            elif esperando_nome_secao == "capitulo":
                capitulo = f"{capitulo} {numeral}"
            elif esperando_nome_secao == "secao":
                secao = f"{secao} {numeral}"
            # Continua esperando o nome descritivo
            continue

        # ── Headers de estrutura numerados ──
        if REGEX_SECAO_HEADER.match(linha_clean) and len(linha_clean) < 80:
            # FIX 19: flush buffer ANTES de atualizar hierarquia.
            # Sem isso, o último artigo da seção anterior herdava a hierarquia da
            # seção SEGUINTE (off-by-one que afetava TODAS as 13 leis).
            flush_buffer(artigo_label_atual)

            u = linha_clean.upper()
            if "LIVRO" in u:
                livro = linha_clean
                titulo = subtitulo = capitulo = secao = ""
                livro_nome = titulo_nome = capitulo_nome = secao_nome = ""
                esperando_nome_secao = "livro"
            elif "SUBTÍTULO" in u or "SUBTITULO" in u:
                subtitulo = linha_clean
                capitulo = secao = ""
                capitulo_nome = secao_nome = ""
                esperando_nome_secao = "subtitulo"
            elif "TÍTULO" in u or "TITULO" in u:
                titulo = linha_clean
                subtitulo = capitulo = secao = ""
                titulo_nome = capitulo_nome = secao_nome = ""
                esperando_nome_secao = "titulo"
            elif "CAPÍTULO" in u or "CAPITULO" in u:
                capitulo = linha_clean
                secao = ""
                capitulo_nome = secao_nome = ""
                esperando_nome_secao = "capitulo"
            elif "SEÇÃO" in u or "SECAO" in u:
                secao = linha_clean
                secao_nome = ""
                esperando_nome_secao = "secao"
            continue

        # ── FIX 2 + FIX 7 + FIX 29: Nomes descritivos de seção ──
        # Quando esperando_nome_secao está ativo, aceita qualquer linha curta que
        # não seja artigo ou header (captura "Introdução", "Normas Gerais", etc.)
        is_nome_secao = REGEX_NOME_SECAO.match(linha_clean) and len(linha_clean) < 120
        is_nome_permissivo = (
            esperando_nome_secao
            and len(linha_clean) < 120
            and not REGEX_ARTIGO.match(linha_clean)
            and not REGEX_SECAO_HEADER.match(linha_clean)
            and not REGEX_CONTINUACAO_HEADER.match(linha_clean)
            and re.match(r'^[A-ZÀ-Ú]', linha_clean)  # começa com maiúscula
        )

        if is_nome_secao or is_nome_permissivo:
            if esperando_nome_secao:
                if esperando_nome_secao == "livro":
                    livro_nome = linha_clean
                elif esperando_nome_secao == "titulo":
                    titulo_nome = linha_clean
                elif esperando_nome_secao == "capitulo":
                    capitulo_nome = linha_clean
                elif esperando_nome_secao == "secao":
                    secao_nome = linha_clean
                esperando_nome_secao = None
                continue
            elif is_nome_secao:
                # Nome de seção sem header precedente — associa ao nível sem nome
                if titulo and not titulo_nome:
                    titulo_nome = linha_clean
                elif capitulo and not capitulo_nome:
                    capitulo_nome = linha_clean
                elif secao and not secao_nome:
                    secao_nome = linha_clean
                continue

        esperando_nome_secao = None

        # ── Detecta início de artigo ──
        match_art = REGEX_ARTIGO.match(linha_clean)
        if match_art:
            num_str = match_art.group(1)
            sufixo = (match_art.group(2) or "").strip()

            # FIX 13: num_str pode ser "1.000" (CC) ou "999" (CDC)
            num_limpo = num_str.replace('.', '')
            if num_limpo.isdigit():
                num_atual = int(num_limpo)
                classificacao = classificar_linha_artigo(
                    linha_clean, num_atual, sufixo, ultimo_num_artigo
                )

                if classificacao == 'novo_artigo':
                    flush_buffer(artigo_label_atual)

                    sufixo_norm = f"-{sufixo}" if sufixo else ""
                    artigo_label_atual = f"Art. {num_str}{sufixo_norm}"
                    if em_transitorias:
                        artigo_label_atual += " (ADCT)"

                    ultimo_num_artigo = num_atual
                    ultimo_sufixo = sufixo

        buffer.append(linha_clean)

    flush_buffer(artigo_label_atual)

    # ── Dedup ──
    vistos: dict[str, dict] = {}
    for b in blocos:
        chave = b["artigo"]
        if chave not in vistos or len(b["texto_limpo"]) > len(vistos[chave]["texto_limpo"]):
            vistos[chave] = b

    return list(vistos.values())


# ─── Extração principal ───────────────────────────────────────────────────────
def extrair_lei(session, sigla: str, hashes: dict, force: bool = False) -> bool:
    if sigla not in LEIS_CONFIG:
        print(f"❌ Sigla desconhecida: {sigla}")
        return False

    versao, url, nome_base = LEIS_CONFIG[sigla]
    print(f"\n📥 Processando {sigla}...")

    try:
        response = session.get(url, timeout=120)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

    hash_atual = hash_conteudo(response.content)
    hash_anterior = hashes.get(sigla, {}).get("hash")

    if hash_atual == hash_anterior and not force:
        print(f"⏭  {sigla} sem alterações desde {hashes[sigla]['data']} — pulando (use --force para re-extrair)")
        return False

    if hash_anterior and hash_atual != hash_anterior:
        print(f"🔄 {sigla} ATUALIZADO desde {hashes[sigla]['data']} — re-extraindo")

    if response.content.startswith(b'\xff\xfe') or response.content.startswith(b'\xfe\xff'):
        soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf-16")
    else:
        soup = BeautifulSoup(response.content, "html.parser")
        if soup.original_encoding and soup.original_encoding.lower() in ('utf-8', 'windows-1252', 'iso-8859-1', 'latin-1'):
            detected_enc = soup.original_encoding
        else:
            detected_enc = "windows-1252"
        soup = BeautifulSoup(response.content, "html.parser", from_encoding=detected_enc)

    data_ext = datetime.now().strftime("%Y-%m-%d")

    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "meta", "link", "img"]):
        tag.decompose()

    for tag in soup.find_all(["s", "del", "strike"]):
        tag.decompose()

    for tag in soup.find_all("a"):
        texto_link = tag.get_text(strip=True)
        if texto_link in ("Vigência", "Regulamento", "Vide", "Nota", "Ver", ""):
            tag.decompose()

    text = soup.get_text(separator="\n")

    text_limpo = re.sub(
        r'^.*?(Aprova|Institui|Dispõe|O PRESIDENTE|A PRESIDENTA|'
        r'O CONGRESSO|PREÂMBULO|Faço saber|Estabelece|Regulamenta)',
        r'\1', text, flags=re.DOTALL | re.IGNORECASE
    )

    clean_text = "\n".join([
        linha.replace('\xa0', ' ').strip()
        for linha in text_limpo.splitlines()
        if linha.replace('\xa0', ' ').strip()
    ])

    clean_text = re.sub(r'(Art\.)\s*\n\s*(\d)', r'\1 \2', clean_text, flags=re.IGNORECASE)

    # ── FIX 26: Remove pontos extras entre "Art." e o número ──
    # CLT Art. 153 gera "Art. . 154" (ponto duplo) após cleanup de revogados.
    # Também cobre "Art. .\n154" e variações com whitespace.
    clean_text = re.sub(r'(Art\.)\s*\.\s*(\d)', r'\1 \2', clean_text, flags=re.IGNORECASE)

    # ── FIX 16: Unifica sufixo de artigo quebrado em 3 linhas ──
    # Planalto às vezes gera: "Art. 4\no\n-A.  Texto..." (3 linhas)
    # quando o HTML é: Art. 4<sup>o</sup>-A.
    # Afeta: LT (Art. 4-A, 4-B, 4-C, 5-A, 5-B), MEI (Art. 3-A, 3-B), CLT, ECA, CP
    clean_text = re.sub(
        r'(Art\.\s*\d[\d.]*)\s*\n\s*o\s*\n\s*(-[A-Z])',
        r'\1\2',
        clean_text
    )

    os.makedirs("data", exist_ok=True)
    txt_path = f"data/{nome_base}_{data_ext}_clean.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(clean_text)

    blocos = extrair_estrutura(clean_text, sigla, versao, url, data_ext)

    json_path = f"data/{nome_base}_{data_ext}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(blocos, f, ensure_ascii=False, indent=2)

    hashes[sigla] = {
        "hash": hash_atual,
        "data": data_ext,
        "blocos": len(blocos),
        "url": url,
    }

    vetados   = sum(1 for b in blocos if b["status"] == "vetado_total")
    revogados = sum(1 for b in blocos if b["status"] == "revogado")
    vigentes  = sum(1 for b in blocos if b["status"] == "vigente")
    com_vetos = sum(1 for b in blocos if b.get("vetos_parciais"))
    com_alter = sum(1 for b in blocos if b.get("alteracoes"))
    
    print(f"✅ {sigla} → {len(blocos)} blocos")
    print(f"   vigentes={vigentes}  vetados_total={vetados}  revogados={revogados}")
    print(f"   com_vetos_parciais={com_vetos}  com_alteracoes={com_alter}")
    return True


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    args        = sys.argv[1:]
    force       = "--force" in args
    siglas_args = [a for a in args if a != "--force"]
    arg         = siglas_args[0].upper() if siglas_args else "ALL"

    session = criar_sessao()
    hashes  = carregar_hashes()

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