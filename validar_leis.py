#!/usr/bin/env python3
"""
validar_leis.py — Validação automática de JSONs do pipeline de extração jurídica.

Uso:
    python validar_leis.py data/cdc_2026-04-03.json          # valida 1 arquivo
    python validar_leis.py data/                              # valida todos os .json do diretório
    python validar_leis.py data/ --strict                     # falha em WARNs (CI mode)
    python validar_leis.py data/ --json-report report.json    # exporta relatório JSON
    python validar_leis.py data/ --cross                      # habilita validações cross-file

Exit codes:
    0  — todos os arquivos passaram (0 FAIL)
    1  — pelo menos 1 FAIL encontrado
    2  — pelo menos 1 WARN encontrado (só com --strict)

Categorias (6):
    SCHEMA     — campos obrigatórios, tipos, valores válidos
    ARTIGO     — nomeação, sequência numérica, IDs, sufixos
    HIERARQUIA — título/capítulo/seção, off-by-one, contaminação, path
    CONTEUDO   — texto, encoding, tamanho, ruído, HTML residual
    METADATA   — status, vetos, alterações, referências, hashes
    RAG        — limites de chunk, densidade, qualidade para retrieval
"""

import json, re, sys, os, argparse
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict

# ═══════════════════════════════════════════════════════════════════════════════
# Configuração
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = [
    "id", "lei", "versao", "versao_consolidada", "artigo",
    "livro", "titulo", "titulo_nome", "subtitulo",
    "capitulo", "capitulo_nome", "secao", "secao_nome",
    "path_hierarquico", "texto_limpo", "status",
    "vetos_parciais", "alteracoes", "referencias",
    "hash_artigo", "url_fonte", "data_extracao",
    "parte_num", "total_partes",
]

VALID_STATUS = {"vigente", "vetado_total", "revogado"}

VALID_LEI_SIGLAS = {
    "CDC", "CLT", "CC", "CPC", "CF88", "CP", "LGPD",
    "ECA", "LI", "LMP", "MEI", "LT", "CP2",
}

# Limites para RAG
RAG_MAX_CHUNK_CHARS = 8000    # acima disso, embedding models truncam
RAG_WARN_CHUNK_CHARS = 6500   # zona de atenção
RAG_MIN_CONTENT_CHARS = 15    # abaixo disso, chunk é ruído


# ═══════════════════════════════════════════════════════════════════════════════
# Modelo de resultado
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Issue:
    severity: str          # FAIL | WARN | INFO
    category: str          # SCHEMA | ARTIGO | HIERARQUIA | CONTEUDO | METADATA | RAG
    rule: str              # identificador curto da regra
    message: str           # descrição legível
    artigo: str = ""       # artigo afetado

@dataclass
class FileReport:
    file: str
    lei: str = ""
    total_chunks: int = 0
    vigentes: int = 0
    vetados: int = 0
    revogados: int = 0
    issues: list = field(default_factory=list)

    @property
    def fails(self):
        return sum(1 for i in self.issues if i.severity == "FAIL")

    @property
    def warns(self):
        return sum(1 for i in self.issues if i.severity == "WARN")

    @property
    def passed(self):
        return self.fails == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _add(report, severity, category, rule, message, artigo=""):
    report.issues.append(Issue(severity, category, rule, message, artigo))

def _art_num(artigo_str: str) -> int | None:
    """Extrai número inteiro do label de artigo. Retorna None se não conseguir."""
    m = re.match(r'Art\.\s*([\d.]+)', artigo_str)
    if m:
        return int(m.group(1).replace('.', ''))
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

def validate_schema(data: list[dict], report: FileReport):
    """Campos obrigatórios, tipos, valores permitidos, consistência interna."""

    # ── Consistência global: lei/versao/url iguais em todos os chunks ──
    leis = set(c.get("lei") for c in data)
    if len(leis) > 1:
        _add(report, "FAIL", "SCHEMA", "lei_inconsistente",
             f"Múltiplas siglas no mesmo arquivo: {leis}")

    versoes = set(c.get("versao") for c in data)
    if len(versoes) > 1:
        _add(report, "WARN", "SCHEMA", "versao_inconsistente",
             f"Múltiplas versões no mesmo arquivo: {versoes}")

    urls = set(c.get("url_fonte") for c in data)
    if len(urls) > 1:
        _add(report, "WARN", "SCHEMA", "url_inconsistente",
             f"Múltiplas URLs fonte no mesmo arquivo: {urls}")

    # ── Sigla conhecida ──
    lei = data[0].get("lei", "")
    if lei and lei not in VALID_LEI_SIGLAS:
        _add(report, "WARN", "SCHEMA", "sigla_desconhecida",
             f"lei='{lei}' — adicionar a VALID_LEI_SIGLAS se for nova lei")

    # ── data_extracao formato (checa 1 vez) ──
    dt = data[0].get("data_extracao", "")
    if dt and not re.match(r'^\d{4}-\d{2}-\d{2}$', dt):
        _add(report, "FAIL", "SCHEMA", "data_formato",
             f"data_extracao='{dt}' formato inválido (esperado YYYY-MM-DD)")

    for i, chunk in enumerate(data):
        art = chunk.get("artigo", f"chunk[{i}]")

        # ── Campos obrigatórios ──
        missing = [f for f in REQUIRED_FIELDS if f not in chunk]
        if missing:
            _add(report, "FAIL", "SCHEMA", "campo_obrigatorio",
                 f"Campos faltando: {missing}", art)

        # ── Tipos ──
        if not isinstance(chunk.get("referencias", {}), dict):
            _add(report, "FAIL", "SCHEMA", "tipo_referencias",
                 "'referencias' deveria ser dict", art)

        if chunk.get("alteracoes") is not None and not isinstance(chunk["alteracoes"], list):
            _add(report, "FAIL", "SCHEMA", "tipo_alteracoes",
                 "'alteracoes' deveria ser list ou null", art)

        if chunk.get("vetos_parciais") is not None and not isinstance(chunk["vetos_parciais"], list):
            _add(report, "FAIL", "SCHEMA", "tipo_vetos",
                 "'vetos_parciais' deveria ser list ou null", art)

        # ── Status válido ──
        if chunk.get("status", "") not in VALID_STATUS:
            _add(report, "FAIL", "SCHEMA", "status_invalido",
                 f"status='{chunk.get('status')}'", art)

        # ── versao_consolidada ──
        if chunk.get("versao_consolidada") is not True:
            _add(report, "WARN", "SCHEMA", "versao_consolidada",
                 "versao_consolidada deveria ser true", art)

        # ── parte_num / total_partes ──
        pn, tp = chunk.get("parte_num"), chunk.get("total_partes")
        if (pn is None) != (tp is None):
            _add(report, "WARN", "SCHEMA", "partes_inconsistente",
                 f"parte_num={pn} total_partes={tp}", art)
        if pn is not None and tp is not None and (pn < 1 or pn > tp):
            _add(report, "FAIL", "SCHEMA", "partes_range",
                 f"parte_num={pn} fora de 1..{tp}", art)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ARTIGO
# ═══════════════════════════════════════════════════════════════════════════════

def validate_artigos(data: list[dict], report: FileReport):
    """Nomeação, IDs, sufixos, sequência numérica."""

    ids = Counter(c["id"] for c in data)
    hashes = Counter(c["hash_artigo"] for c in data)

    # ── IDs duplicados ──
    dupes = {k: v for k, v in ids.items() if v > 1}
    if dupes:
        _add(report, "FAIL", "ARTIGO", "id_duplicado",
             f"{len(dupes)} IDs duplicados: {list(dupes.keys())[:5]}")

    # ── Hashes duplicados ──
    for h, cnt in hashes.items():
        if cnt > 1:
            arts = [c["artigo"] for c in data if c["hash_artigo"] == h]
            _add(report, "WARN", "ARTIGO", "hash_duplicado",
                 f"Hash {h} compartilhado: {arts}")

    # ── Bug °→sufixo ──
    for chunk in data:
        art, texto = chunk["artigo"], chunk["texto_limpo"][:80]

        if re.search(r'-O\b', art) and re.match(r'Art\.\s*\d+[°º]\s+O\s', texto):
            _add(report, "FAIL", "ARTIGO", "grau_como_sufixo_O",
                 "° parseado como sufixo -O", art)

        if re.search(r'-A\b', art) and re.match(r'Art\.\s*\d+[°ºo]?\s+A\s+[A-ZÁÉÍÓÚ]', texto):
            _add(report, "FAIL", "ARTIGO", "grau_como_sufixo_A",
                 "° + artigo 'A' parseado como sufixo -A", art)

        # ── Sufixo com espaço (CLT: "Art. 142 - O") ──
        if re.search(r'-[A-Z]\b', art):
            suf = re.search(r'-([A-Z])\b', art).group(1)
            if re.match(rf'Art\.\s*\d+\s+[-–]\s+{suf}\s', texto):
                _add(report, "FAIL", "ARTIGO", "sufixo_espacado",
                     f"Sufixo -{suf} provavelmente falso (espaço antes do hífen no texto)", art)

    # ── Sequência numérica ──
    nums = sorted(set(filter(None, (_art_num(c["artigo"]) for c in data))))
    if len(nums) >= 2:
        expected = set(range(nums[0], nums[-1] + 1))
        missing = sorted(expected - set(nums))
        if 0 < len(missing) <= 30:
            _add(report, "INFO", "ARTIGO", "artigos_faltantes",
                 f"{len(missing)} faltantes: {missing[:15]}{'...' if len(missing)>15 else ''}")

    # ── Ordem monotônica dos artigos ──
    prev_num = 0
    backward_jumps = 0
    for chunk in data:
        n = _art_num(chunk["artigo"])
        if n is not None:
            if n < prev_num - 5 and "(ADCT)" not in chunk["artigo"]:
                backward_jumps += 1
            prev_num = n
    if backward_jumps > 3:
        _add(report, "WARN", "ARTIGO", "ordem_nao_monotonica",
             f"{backward_jumps} saltos para trás na numeração (possível desordem)")

    # ── Partes do mesmo artigo devem ser sequenciais ──
    partes_por_art = defaultdict(list)
    for chunk in data:
        if chunk.get("parte_num"):
            base = re.sub(r'\s*\(Parte \d+/\d+\)', '', chunk["artigo"])
            partes_por_art[base].append(chunk["parte_num"])
    for art_base, partes in partes_por_art.items():
        expected_seq = list(range(1, len(partes) + 1))
        if sorted(partes) != expected_seq:
            _add(report, "WARN", "ARTIGO", "partes_descontinuas",
                 f"Partes {sorted(partes)} (esperado {expected_seq})", art_base)

    # ── ID prefixo ──
    lei_lower = data[0].get("lei", "").lower()
    if lei_lower and data:
        sample = data[0]
        if not sample["id"].startswith(lei_lower + "_"):
            _add(report, "WARN", "ARTIGO", "id_sem_sigla",
                 f"ID '{sample['id']}' não começa com '{lei_lower}_'", sample["artigo"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. HIERARQUIA
# ═══════════════════════════════════════════════════════════════════════════════

_RE_TITULO_VALIDO = re.compile(
    r'^T[IÍí]TULO\s*([IVXLCDM]+(-[A-Z])?\s*|[ÚU]NIC[OA]\s*|PRELIMINAR\s*)?$',
    re.IGNORECASE
)
_RE_CAPITULO_VALIDO = re.compile(
    r'^CAP[IÍí]TULO\s*([IVXLCDM]+(-[A-Z])?\s*|[ÚU]NIC[OA]\s*)?$',
    re.IGNORECASE
)
_RE_SECAO_VALIDA = re.compile(
    r'^SE[ÇCçc][ÃAãa]O\s*([IVXLCDM]+(-[A-Z])?\s*|[ÚU]NIC[Aa]\s*)?$',
    re.IGNORECASE
)

def validate_hierarquia(data: list[dict], report: FileReport):
    """Título/capítulo/seção: contaminação, off-by-one, completude, path."""

    for chunk in data:
        art = chunk["artigo"]
        titulo = chunk.get("titulo", "")
        capitulo = chunk.get("capitulo", "")
        secao = chunk.get("secao", "")
        path = chunk.get("path_hierarquico", "")

        # ── Contaminação: header contém texto de artigo ──
        if titulo and not _RE_TITULO_VALIDO.match(titulo) and len(titulo) > 20:
            _add(report, "FAIL", "HIERARQUIA", "titulo_contaminado",
                 f'titulo="{titulo[:60]}..." parece texto', art)
            break

        if capitulo and not _RE_CAPITULO_VALIDO.match(capitulo) and len(capitulo) > 25:
            _add(report, "FAIL", "HIERARQUIA", "capitulo_contaminado",
                 f'capitulo="{capitulo[:60]}" parece texto', art)
            break

        if secao and not _RE_SECAO_VALIDA.match(secao) and len(secao) > 20:
            _add(report, "FAIL", "HIERARQUIA", "secao_contaminada",
                 f'secao="{secao[:60]}" parece texto', art)
            break

        # ── Header partido (sem número) ──
        if capitulo and re.match(r'^CAPÍTULO\s*$', capitulo.strip(), re.I):
            _add(report, "WARN", "HIERARQUIA", "capitulo_sem_numero",
                 f'capitulo="{capitulo}" sem numeral', art)

        if secao and re.match(r'^SE[ÇC][ÃA]O\s*$', secao.strip(), re.I):
            _add(report, "WARN", "HIERARQUIA", "secao_sem_numero",
                 f'secao="{secao}" sem numeral', art)

        # ── Seção colada ──
        if secao and re.match(r'^Se[çc][ãa]o[IVXLCDM]', secao, re.I):
            _add(report, "WARN", "HIERARQUIA", "secao_colada",
                 f'secao="{secao}" sem espaço', art)

        # ── path contém capitulo ──
        if capitulo and len(capitulo) > 3 and capitulo not in path:
            _add(report, "WARN", "HIERARQUIA", "path_inconsistente",
                 f'capitulo="{capitulo}" ausente do path', art)
            break

    # ── Artigos sem titulo quando outros têm ──
    has_titulo = any(c["titulo"] for c in data if c["artigo"] != "EMENTA")
    if has_titulo:
        no_titulo = [c["artigo"] for c in data
                     if not c["titulo"] and c["artigo"] != "EMENTA"]
        if no_titulo:
            _add(report, "INFO", "HIERARQUIA", "artigo_sem_titulo",
                 f"{len(no_titulo)} artigos sem titulo (ex: {no_titulo[:3]})")

    # ── titulo_nome / capitulo_nome vazios ──
    for field_name, label in [("titulo", "titulo_nome"), ("capitulo", "capitulo_nome")]:
        sem_nome = defaultdict(int)
        for c in data:
            val = c[field_name]
            if val and not c[label] and c["artigo"] != "EMENTA" and val.strip().upper() != "CAPÍTULO":
                sem_nome[val] += 1
        severity = "WARN" if field_name == "titulo" else "INFO"
        for val, count in list(sem_nome.items())[:5]:
            _add(report, severity, "HIERARQUIA", f"{field_name}_sem_nome",
                 f'{field_name}="{val}" sem {label} ({count} artigos)')

    # ── Off-by-one heurística ──
    transitions = []
    for i in range(1, len(data)):
        p, c = data[i-1], data[i]
        if p["capitulo"] != c["capitulo"] and p["capitulo"] and c["capitulo"]:
            transitions.append(i)
        if p["secao"] != c["secao"] and p["secao"] and c["secao"]:
            transitions.append(i)

    if len(transitions) > 5:
        singletons = 0
        for t in transitions[:30]:
            if t >= 2:
                bp, p, c = data[t-2], data[t-1], data[t]
                if bp["capitulo"] == c["capitulo"] and p["capitulo"] != c["capitulo"]:
                    singletons += 1
        if singletons > 3:
            _add(report, "FAIL", "HIERARQUIA", "off_by_one",
                 f"Off-by-one detectado: {singletons} artigos isolados entre transições")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONTEUDO
# ═══════════════════════════════════════════════════════════════════════════════

def validate_conteudo(data: list[dict], report: FileReport):
    """Texto, encoding, tamanho, ruído, HTML, label×texto match."""

    for chunk in data:
        art = chunk["artigo"]
        texto = chunk.get("texto_limpo", "")
        status = chunk.get("status", "")

        # ── Texto vazio ──
        if not texto or not texto.strip():
            _add(report, "FAIL", "CONTEUDO", "texto_vazio", "texto_limpo vazio", art)
            continue

        # ── Mojibake / encoding ──
        for bad in ['Ã£','Ã¡','Ã©','Ã³','Ã§','Ãº','Â°','Â§','\ufffd']:
            if bad in texto:
                _add(report, "FAIL", "CONTEUDO", "encoding_quebrado",
                     f"Mojibake: '{bad}'", art)
                break

        # ── HTML residual ──
        if re.search(r'<(?:p|br|div|span|table|tr|td|font|b|i|u|a|em|strong)\b', texto, re.I):
            _add(report, "FAIL", "CONTEUDO", "html_residual",
                 "Tags HTML no texto_limpo", art)

        # ── Entidades HTML ──
        if re.search(r'&(?:nbsp|amp|lt|gt|quot|#\d+);', texto):
            _add(report, "WARN", "CONTEUDO", "entidade_html",
                 "Entidade HTML não resolvida no texto", art)

        # ── Texto curto para vigente ──
        if status == "vigente" and len(texto) < RAG_MIN_CONTENT_CHARS:
            _add(report, "WARN", "CONTEUDO", "texto_curto",
                 f"Vigente com {len(texto)} chars", art)

        # ── Whitespace excessivo ──
        if '\n\n\n' in texto:
            _add(report, "WARN", "CONTEUDO", "whitespace_excessivo",
                 "3+ newlines consecutivas no texto", art)

        # ── Ruído legislativo residual ──
        for marker in [
            r'\(Redação dada (?:pela|pelo)',
            r'\(Incluíd[oa] (?:pela|pelo)',
            r'\(Revogad[oa]',
            r'\(Vigência\)',
            r'\(Acrescentad[oa]',
        ]:
            if re.search(marker, texto, re.I):
                _add(report, "WARN", "CONTEUDO", "ruido_residual",
                     f"Marcador não removido: {marker[:30]}", art)
                break

        # ── Label × texto mismatch ──
        if art.startswith("Art."):
            m_label = re.match(r'Art\.\s*([\d.]+)', art)
            m_texto = re.match(r'Art\.\s*([\d.]+)', texto)
            if m_label and m_texto:
                nl = m_label.group(1).rstrip('.')
                nt = m_texto.group(1).rstrip('.')
                if nl != nt:
                    _add(report, "FAIL", "CONTEUDO", "artigo_texto_mismatch",
                         f"Label Art. {nl} vs texto Art. {nt}", art)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. METADATA
# ═══════════════════════════════════════════════════════════════════════════════

def validate_metadata(data: list[dict], report: FileReport):
    """Status, vetos, alterações, referências, hashes."""

    for chunk in data:
        art = chunk["artigo"]
        status = chunk.get("status", "")
        texto = chunk.get("texto_limpo", "")

        # ── Vetado total com texto substancial ──
        if status == "vetado_total" and len(texto) > 300:
            _add(report, "WARN", "METADATA", "vetado_texto_longo",
                 f"vetado_total com {len(texto)} chars", art)

        # ── Vigente com "(Vetado)" no texto mas sem vetos_parciais ──
        if status == "vigente" and not chunk.get("vetos_parciais"):
            if re.search(r'\(Vetado\)', texto, re.I):
                _add(report, "WARN", "METADATA", "veto_nao_detectado",
                     "Texto contém '(Vetado)' mas vetos_parciais é null", art)

        # ── Vetos parciais formato ──
        if chunk.get("vetos_parciais"):
            for v in chunk["vetos_parciais"]:
                if not re.match(
                    r'^(§\s*\d+[°ºo]?|[IVXLCDM]+|Parágrafo\s+único|[a-z]\)|Art\.\s*\d+[A-Z]|dispositivo vetado \d+)$',
                    v.strip(), re.IGNORECASE
                ):
                    _add(report, "WARN", "METADATA", "veto_formato",
                         f"Veto parcial '{v}' formato inesperado", art)

        # ── Alterações ──
        if chunk.get("alteracoes"):
            for alt in chunk["alteracoes"]:
                if not isinstance(alt, dict) or "tipo" not in alt or "norma" not in alt:
                    _add(report, "FAIL", "METADATA", "alteracao_invalida",
                         f"Alteração mal-formada: {alt}", art)

        # ── Referências ──
        refs = chunk.get("referencias", {})
        if isinstance(refs, dict):
            for key in ("internas", "leis_externas", "constituicao"):
                if key not in refs:
                    _add(report, "FAIL", "METADATA", "ref_campo_faltante",
                         f"Falta '{key}' em referencias", art)
                    break
            # Tipo dos subcampos
            if not isinstance(refs.get("internas", []), list):
                _add(report, "FAIL", "METADATA", "ref_tipo_internas",
                     "referencias.internas deveria ser list", art)
            if not isinstance(refs.get("leis_externas", []), list):
                _add(report, "FAIL", "METADATA", "ref_tipo_externas",
                     "referencias.leis_externas deveria ser list", art)
            if not isinstance(refs.get("constituicao", False), bool):
                _add(report, "FAIL", "METADATA", "ref_tipo_cf",
                     "referencias.constituicao deveria ser bool", art)

        # ── Hash ──
        h = chunk.get("hash_artigo", "")
        if not h or len(h) < 8:
            _add(report, "FAIL", "METADATA", "hash_invalido",
                 f"hash_artigo='{h}'", art)

    # ── URL fonte (checa 1 vez) ──
    url = data[0].get("url_fonte", "")
    if not url or not url.startswith("http"):
        _add(report, "WARN", "METADATA", "url_invalida",
             f"url_fonte='{url}'")

    # ── Todas as partes do mesmo artigo devem ter mesmo status ──
    partes_status = defaultdict(set)
    for c in data:
        base = re.sub(r'\s*\(Parte \d+/\d+\)', '', c["artigo"])
        partes_status[base].add(c["status"])
    for art_base, statuses in partes_status.items():
        if len(statuses) > 1:
            _add(report, "WARN", "METADATA", "status_divergente_partes",
                 f"Partes com status diferentes: {statuses}", art_base)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RAG (qualidade para retrieval)
# ═══════════════════════════════════════════════════════════════════════════════

def validate_rag(data: list[dict], report: FileReport):
    """Limites de chunk, densidade, qualidade para embedding/retrieval."""

    oversized = 0
    warn_sized = 0
    total_chars = 0

    for chunk in data:
        art = chunk["artigo"]
        texto = chunk.get("texto_limpo", "")
        size = len(texto)
        total_chars += size

        # ── Chunk muito grande ──
        if size > RAG_MAX_CHUNK_CHARS:
            oversized += 1
            if oversized <= 3:
                _add(report, "WARN", "RAG", "chunk_grande",
                     f"{size} chars (limite={RAG_MAX_CHUNK_CHARS})", art)
        elif size > RAG_WARN_CHUNK_CHARS:
            warn_sized += 1

    if oversized > 3:
        _add(report, "WARN", "RAG", "chunk_grande",
             f"... +{oversized-3} chunks acima de {RAG_MAX_CHUNK_CHARS} chars")

    if oversized > 0:
        _add(report, "INFO", "RAG", "chunk_grande_total",
             f"{oversized} chunks > {RAG_MAX_CHUNK_CHARS} chars, {warn_sized} entre {RAG_WARN_CHUNK_CHARS}-{RAG_MAX_CHUNK_CHARS}")

    # ── Proporção de artigos vigentes (sanidade) ──
    if report.total_chunks > 0:
        ratio = report.vigentes / report.total_chunks
        if ratio < 0.3:
            _add(report, "WARN", "RAG", "baixa_vigencia",
                 f"Apenas {ratio:.0%} dos chunks são vigentes — verificar se revogações estão corretas")

    # ── Estimativa de tokens (1 token ≈ 4 chars em PT-BR) ──
    est_tokens = total_chars // 4
    avg_tokens = est_tokens // max(report.total_chunks, 1)
    _add(report, "INFO", "RAG", "token_estimate",
         f"~{est_tokens:,} tokens total, ~{avg_tokens:,} média/chunk ({report.total_chunks} chunks)")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CROSS-FILE (opcional)
# ═══════════════════════════════════════════════════════════════════════════════

def validate_cross_file(reports: list[FileReport], all_data: dict[str, list[dict]]):
    """Validações entre arquivos."""

    cross_report = FileReport(file="[CROSS-FILE]", lei="ALL")

    # ── IDs globalmente únicos ──
    global_ids = Counter()
    for lei, data in all_data.items():
        for c in data:
            global_ids[c["id"]] += 1
    dupes = {k: v for k, v in global_ids.items() if v > 1}
    if dupes:
        _add(cross_report, "FAIL", "SCHEMA", "id_global_duplicado",
             f"{len(dupes)} IDs duplicados entre arquivos: {list(dupes.keys())[:5]}")

    # ── Mesma lei em múltiplos arquivos ──
    leis_per_file = defaultdict(list)
    for lei, data in all_data.items():
        sigla = data[0]["lei"] if data else "?"
        leis_per_file[sigla].append(lei)
    for sigla, files in leis_per_file.items():
        if len(files) > 1:
            _add(cross_report, "WARN", "SCHEMA", "lei_duplicada_files",
                 f"'{sigla}' presente em {len(files)} arquivos: {files}")

    cross_report.total_chunks = sum(len(d) for d in all_data.values())
    return cross_report


# ═══════════════════════════════════════════════════════════════════════════════
# Orquestrador
# ═══════════════════════════════════════════════════════════════════════════════

def validate_file(filepath: str) -> FileReport:
    report = FileReport(file=os.path.basename(filepath))

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        _add(report, "FAIL", "SCHEMA", "json_invalido", str(e))
        return report

    if not isinstance(data, list) or not data:
        _add(report, "FAIL", "SCHEMA", "json_vazio", "Array vazio ou tipo errado")
        return report

    report.lei = data[0].get("lei", "?")
    report.total_chunks = len(data)
    report.vigentes = sum(1 for d in data if d.get("status") == "vigente")
    report.vetados = sum(1 for d in data if d.get("status") == "vetado_total")
    report.revogados = sum(1 for d in data if d.get("status") == "revogado")

    validate_schema(data, report)
    validate_artigos(data, report)
    validate_hierarquia(data, report)
    validate_conteudo(data, report)
    validate_metadata(data, report)
    validate_rag(data, report)

    # Dedup
    seen = Counter()
    deduped = []
    for issue in report.issues:
        key = f"{issue.rule}:{issue.severity}"
        seen[key] += 1
        if seen[key] <= 5:
            deduped.append(issue)
        elif seen[key] == 6:
            deduped.append(Issue(
                issue.severity, issue.category, issue.rule,
                f"... +{seen[key]-5} suprimidas"
            ))
    for issue in deduped:
        if issue.message.startswith("... +"):
            key = f"{issue.rule}:{issue.severity}"
            issue.message = f"... +{seen[key]-5} ocorrências suprimidas"
    report.issues = deduped

    return report, data


# ═══════════════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════════════

ICONS = {"FAIL": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}
COLORS = {"FAIL": "\033[91m", "WARN": "\033[93m", "INFO": "\033[96m"}
RESET = "\033[0m"

def print_report(report: FileReport, color=True):
    icon = "✅" if report.passed else "❌"
    print(f"\n{'─'*70}")
    print(f"{icon}  {report.lei:6s}  {report.file}")
    print(f"   chunks={report.total_chunks}  vig={report.vigentes}  vet={report.vetados}  rev={report.revogados}")

    if not report.issues:
        print(f"   Nenhum problema encontrado.")
        return

    f = sum(1 for i in report.issues if i.severity == "FAIL")
    w = sum(1 for i in report.issues if i.severity == "WARN")
    n = sum(1 for i in report.issues if i.severity == "INFO")
    print(f"   FAIL={f}  WARN={w}  INFO={n}")

    for issue in report.issues:
        ic = ICONS.get(issue.severity, "?")
        c = COLORS.get(issue.severity, "") if color else ""
        r = RESET if color else ""
        tag = f" [{issue.artigo}]" if issue.artigo else ""
        print(f"   {c}{ic} {issue.category}/{issue.rule}{tag}: {issue.message}{r}")


def export_json_report(reports: list[FileReport], filepath: str):
    output = {
        "total_files": len(reports),
        "total_pass": sum(1 for r in reports if r.passed),
        "total_fail": sum(1 for r in reports if not r.passed),
        "total_chunks": sum(r.total_chunks for r in reports),
        "files": [{
            "file": r.file, "lei": r.lei, "total_chunks": r.total_chunks,
            "passed": r.passed, "fails": r.fails, "warns": r.warns,
            "issues": [asdict(i) for i in r.issues],
        } for r in reports]
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Relatório salvo: {filepath}")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def load_known_issues(path: str) -> dict:
    """Carrega known_issues.json para suprimir INFOs verificados."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def suppress_known_issues(report: FileReport, ki: dict):
    """Remove INFOs que constam no registro de known_issues."""
    if not ki:
        return
    
    lei = report.lei
    suppressed = 0
    filtered = []
    
    # Artigos faltantes verificados
    known_missing = set(ki.get("artigos_faltantes_verificados", {}).get(lei, {}).keys())
    
    # Artigos sem titulo verificados
    known_no_titulo = set(
        ki.get("artigos_sem_titulo_verificados", {}).get(lei, {}).get("artigos", [])
    )
    
    # Capítulos sem nome verificados
    known_cap_no_nome = ki.get("capitulo_sem_nome_verificados", {}).get(lei, {})
    
    for issue in report.issues:
        suppress = False
        
        # Suprimir artigos_faltantes que são revogados conhecidos
        if issue.rule == "artigos_faltantes" and known_missing:
            # Extrai números do message "N faltantes: [x, y, z]"
            m = re.search(r'\[([^\]]+)\]', issue.message)
            if m:
                nums = [n.strip() for n in m.group(1).split(',')]
                remaining = [n for n in nums if n not in known_missing]
                if not remaining:
                    suppress = True
                elif len(remaining) < len(nums):
                    issue.message = f"{len(remaining)} faltantes: [{', '.join(remaining)}]"
        
        # Suprimir artigo_sem_titulo conhecidos
        if issue.rule == "artigo_sem_titulo" and known_no_titulo:
            suppress = True
        
        # Suprimir capitulo_sem_nome conhecidos
        if issue.rule == "capitulo_sem_nome" and known_cap_no_nome:
            for cap_key in known_cap_no_nome:
                if cap_key in issue.message:
                    suppress = True
                    break
        
        if suppress:
            suppressed += 1
        else:
            filtered.append(issue)
    
    report.issues = filtered
    return suppressed


def main():
    parser = argparse.ArgumentParser(description="Validação de JSONs jurídicos")
    parser.add_argument("path", help="Arquivo .json ou diretório")
    parser.add_argument("--strict", action="store_true", help="Exit 2 em WARNs")
    parser.add_argument("--cross", action="store_true", help="Validação cross-file")
    parser.add_argument("--json-report", metavar="FILE", help="Exporta JSON")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--known-issues", metavar="FILE",
                        help="JSON de issues verificados (default: data/known_issues.json)")
    args = parser.parse_args()

    # Carrega known_issues
    ki_path = args.known_issues
    if not ki_path:
        # Auto-detect: mesmo diretório do path, ou data/
        for candidate in [
            os.path.join(args.path, "known_issues.json"),
            os.path.join("data", "known_issues.json"),
            "known_issues.json",
        ]:
            if os.path.exists(candidate):
                ki_path = candidate
                break
    ki = load_known_issues(ki_path) if ki_path else {}
    if ki:
        print(f"📋 Known issues: {ki_path}")

    if os.path.isdir(args.path):
        files = sorted(os.path.join(args.path, f)
                       for f in os.listdir(args.path)
                       if f.endswith(".json") and not f.startswith("hashes")
                       and f != "known_issues.json")
    elif os.path.isfile(args.path):
        files = [args.path]
    else:
        print(f"❌ Não encontrado: {args.path}")
        sys.exit(1)

    if not files:
        print(f"❌ Nenhum .json em {args.path}")
        sys.exit(1)

    reports, all_data = [], {}
    total_suppressed = 0
    for fp in files:
        result = validate_file(fp)
        if isinstance(result, tuple):
            report, data = result
            all_data[os.path.basename(fp)] = data
        else:
            report = result
        if ki:
            s = suppress_known_issues(report, ki)
            if s:
                total_suppressed += s
        reports.append(report)
        print_report(report, color=not args.no_color)

    # Cross-file
    if args.cross and len(all_data) > 1:
        cross = validate_cross_file(reports, all_data)
        reports.append(cross)
        print_report(cross, color=not args.no_color)

    # Sumário
    tp = sum(1 for r in reports if r.passed)
    tf = sum(1 for r in reports if not r.passed)
    ti = sum(len(r.issues) for r in reports)
    tfc = sum(r.fails for r in reports)
    twc = sum(r.warns for r in reports)
    tc = sum(r.total_chunks for r in reports)

    print(f"\n{'═'*70}")
    print(f"SUMÁRIO: {len(files)} arquivos · {tc:,} chunks")
    print(f"  ✅ {tp} passaram  ❌ {tf} falharam")
    print(f"  {tfc} FAILs · {twc} WARNs · {ti} issues total")
    if total_suppressed:
        print(f"  📋 {total_suppressed} INFOs suprimidos (known_issues)")
    print(f"{'═'*70}")

    if args.json_report:
        export_json_report(reports, args.json_report)

    sys.exit(1 if tfc > 0 else (2 if args.strict and twc > 0 else 0))


if __name__ == "__main__":
    main()