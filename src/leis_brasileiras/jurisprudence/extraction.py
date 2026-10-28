"""Pure source parsers adapted from Justina; transport and persistence are separate.

Original parser names and source record fields are retained for traceable regression.
"""
import csv
import hashlib
import io
import json
import logging
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL_TEMAS_CSV = (
    "https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf/"
    "resource/df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv"
)

URL_STJ_SUMULAS_TPL = (
    "https://processo.stj.jus.br/SCON/pesquisar.jsp"
    "?livre=%40docn&b=SUMU&p=true&numDocsPagina=50&i={i}"
)

URL_STF_TESES = "https://portal.stf.jus.br/repercussaogeral/retornartesesrepercussaogeral.asp"

REFERER_STF_TESES = "https://portal.stf.jus.br/repercussaogeral/teses.asp"

URL_STF_SV_INDICE = "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26"

URL_TJPE_SUMULAS_INDICE = "https://portal.tjpe.jus.br/servicos/consulta/sumulas"

URL_TJMG_SUMULAS_INDICE = ("https://www.tjmg.jus.br/portal-tjmg/jurisprudencia/"
                           "consulta-de-jurisprudencia/lista-de-sumulas.htm")

RE_TJPE_LIVRO = re.compile(r"livro\s+s[uú]mulas?\s+tjpe", re.I)

RE_TJMG_CONSOLIDADO = re.compile(r"todos\s+os\s+enunciados|enunciados?\s+de\s+s[uú]mula"
                                 r"|vers[aã]o\s+para\s+impress[aã]o", re.I)

SITUACAO_TJPE = {None: "em_vigor", "revogada": "revogada"}

SITUACAO_TJMG = {None: "em_vigor", "cancelado": "cancelada", "alterado": "alterada"}

ROTULOS_SUMULA_TJ = (
    "Órgão Julgador", "Data do Julgamento", "Data de julgamento",
    "Data da Publicação/Fonte", "Data da publicação/Fonte", "Enunciado",
    "Referência Legislativa", "Referência legislativa", "Referências",
    "Precedentes", "Nota de cancelamento", "Nota de atualização",
)

RE_CABECA_SUMULA_TJPE = re.compile(r"^\s*S[úÚ]mula\s*$")

RE_NUMERO_SUMULA_TJPE = re.compile(r"^\s*0*(\d{1,3})\s*(?:[-–—]\s*(.+?))?\s*$")

RE_CABECA_SUMULA_TJMG = re.compile(r"^\s*ENUNCIADO\s+0*(\d{1,3})\s*(?:[-–—]\s*(.+?))?\s*$")

RE_DATA_BR = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")

RE_LINHA_SO_DIGITOS = re.compile(r"^\s*\d{1,3}\s*$")

RE_DOT_LEADERS = re.compile(r"\.{4,}")

MIN_CHARS_PDF = 200

UA_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

COLUNAS_ESPERADAS = (
    "sequencialPrecedente",
    "tipoPrecedente",
    "numeroPrecedente",
    "dataPrimeiraAfetacao",
    "dataJulgamento",
    "situacao",
    "informacoesComplementares",
    "questaoSubmetidaAJulgamento",
    "teseFirmada",
    "anotacoesNUGEPNAC",
    "delimitacaoJulgado",
    "entendimentoAnterior",
    "referenciaLegislativa",
    "referenciaSumular",
    "sumulaOriginada",
    "audienciaPublica",
    "dataAudienciaPublica",
    "orgaoJulgador",
    "Assuntos",
    "numeroRepercussaoGeralSTF",
    "descricaoRepercussaoGeral",
)

CAMPOS_TESES_ESPERADOS = (
    "numeroTema",
    "incidente",
    "siglaClasse",
    "numeroProcesso",
    "descricaoTese",
    "dataAndamento",
)

FIELD_SIZE_LIMIT = 10_000_000

MAX_PAGINAS_SCON = 30

SLEEP_ENTRE_REQUISICOES = 1.0

MIN_STJ_SUMULAS = 600

MIN_STF_TESES_COM = 700

MIN_STF_TESES_SEM = 400

MIN_STF_SVS = 60

MIN_TJPE_SUMULAS = 160

MIN_TJMG_SUMULAS = 80

MIN_TJPE_LIVROS = 3

MAIOR_TJPE_CONHECIDO = 172

MAIOR_TJMG_CONHECIDO = 89

_FORMATOS_DATA = (
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)

TIPOS_PRECEDENTE = {
    "Tema": "tema_repetitivo",
    "Controvérsia": "controversia",
    "IAC": "iac",
    "PUIL": "puil",
    "SIRDR": "sirdr",
}

def _tipo_canonico(tipo_precedente: str | None) -> str | None:
    """tipoPrecedente verbatim -> tipo canonico. Valor desconhecido (fonte mudou o
    dominio) vira slug deterministico (sem acento, lowercase) — nunca descarta."""
    if tipo_precedente is None:
        return None
    if tipo_precedente in TIPOS_PRECEDENTE:
        return TIPOS_PRECEDENTE[tipo_precedente]
    slug = unicodedata.normalize("NFKD", tipo_precedente)
    slug = "".join(c for c in slug if not unicodedata.combining(c))
    return slug.lower().replace(" ", "_")

class LayoutInvalidoError(ValueError):
    """Layout da fonte divergiu do esperado (coluna/estrutura obrigatoria faltando).

    O extrator NUNCA prossegue com layout invalido: mudanca silenciosa da fonte
    produziria JSON canonico corrompido que fluiria para embeddings/prompts."""

def decodificar_bytes(raw: bytes) -> tuple[str, str]:
    """bytes -> (texto, encoding_usado). UTF-8 com BOM -> utf-8-sig; UTF-8 estrito;
    fallback cp1252 (fontes gov.br servem cp1252 com frequencia — o SCON, por
    exemplo, e cp1252 real; o portal STF e UTF-8)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"

decodificar_csv = decodificar_bytes

def hash_texto(texto: str) -> str:
    # Mesmo padrao de extrair_leis.hash_texto (replicado — sem importar o modulo
    # de scraping inteiro so por uma linha).
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]

def _limpar(valor) -> str | None:
    """strip + vazios consistentes: campo textual vazio -> None (nunca "")."""
    if valor is None:
        return None
    valor = valor.strip()
    return valor if valor else None

def _normalizar_espacos(texto: str) -> str:
    """Colapsa qualquer whitespace (incl. \\xa0 e newlines de HTML) em espaco unico."""
    return re.sub(r"\s+", " ", texto).strip()

def _parse_data(valor: str | None) -> tuple[str | None, str | None]:
    """-> (iso, raw_nao_parseavel). Parseavel -> (YYYY-MM-DD, None);
    nao-parseavel e nao-vazio -> (None, original); vazio -> (None, None)."""
    valor = _limpar(valor)
    if valor is None:
        return None, None
    for fmt in _FORMATOS_DATA:
        try:
            return datetime.strptime(valor, fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, valor

def _finalizar_registro(registro: dict, extracted_at: str,
                        ignorar: tuple = ()) -> dict:
    """Hash estavel + extracted_at (padrao J0.1): hash = sha256[:16] da serializacao
    canonica dos campos de CONTEUDO; extracted_at entra DEPOIS (fora do hash).

    `ignorar` tira campos VOLATEIS do hash. Default vazio: as 4 fontes J0 sao byte-identicas
    ao que sempre foram, e mudar o hash delas re-versionaria o corpus inteiro. As fontes
    estaduais passam ("url_fonte", "livro") porque o href do TJPE e um UUID do Liferay que
    muda sozinho — com ele dentro, uma troca de UUID mandava os 172 registros para o
    supersede com re-embedding PAGO sem uma virgula de conteudo juridico ter mudado (e
    reprocessar a mesma captura por --from-file dava hash diferente da rede)."""
    canonico = json.dumps({k: v for k, v in registro.items() if k not in ignorar},
                          sort_keys=True, ensure_ascii=False)
    registro["hash"] = hash_texto(canonico)
    registro["extracted_at"] = extracted_at
    return registro

CAMPOS_VOLATEIS_ESTADUAL = ("url_fonte", "livro")

CAMPOS_MULTIVALORADOS = ("numero_repercussao_geral_stf",)

CAMPOS_DERIVADOS = ("hash", "extracted_at")

def chave_natural(registro: dict) -> tuple:
    """Identidade do registro no banco — espelha uq_jdv_current (court, doc_type, number)."""
    return (registro.get("source"), registro.get("tipo"), registro.get("numero"))

def _ordenar_valores(valores) -> list[str]:
    """Ordem DETERMINISTICA (numerica quando da, lexicografica senao). Sem isto o hash do
    registro colapsado dependeria da ordem em que as linhas vieram da fonte."""
    return sorted(set(valores),
                  key=lambda v: (0, int(v), "") if str(v).isdigit() else (1, 0, str(v)))

def colapsar_por_chave_natural(registros: list[dict], extracted_at: str) -> list[dict]:
    """N linhas da mesma chave natural -> 1 registro, agregando os campos multivalorados.

    Espelha o que o Portao 1 de LEIS ja faz (dedup-por-rotulo) e o dedup entre paginas do
    fluxo de sumulas: a unicidade da chave natural se garante na ORIGEM, nunca descoberta
    no INSERT. Sem isto, um precedente vinculado a N temas de repercussao geral vira N
    INSERTs que colidem em uq_jdv_current (V15) — medido no corpus de 2026-07-20: 34
    chaves, 37 linhas excedentes, 26 delas pagando embedding por tese IDENTICA.

    Registro de chave UNICA sai INTACTO — mesmo objeto, mesmo hash. So o colapsado e
    re-finalizado, porque so nele o conteudo mudou.

    Divergencia em campo NAO declarado multivalorado NAO e colapsavel: sao registros
    DISTINTOS disputando a mesma chave, e funde-los inventaria dado. Falha alto, como
    toda quirk nova de fonte neste pipeline — nunca whitelist silenciosa.
    """
    grupos: dict[tuple, list[dict]] = {}
    for registro in registros:
        grupos.setdefault(chave_natural(registro), []).append(registro)

    saida, colapsadas, absorvidas = [], 0, 0
    for chave, linhas in grupos.items():
        if len(linhas) == 1:
            saida.append(linhas[0])
            continue

        todos_campos = set().union(*(set(linha) for linha in linhas))
        divergentes = sorted(
            campo for campo in todos_campos
            if campo not in CAMPOS_DERIVADOS
            and len({json.dumps(linha.get(campo), sort_keys=True, ensure_ascii=False)
                     for linha in linhas}) > 1
        )
        nao_colapsaveis = [c for c in divergentes if c not in CAMPOS_MULTIVALORADOS]
        if nao_colapsaveis:
            raise LayoutInvalidoError(
                f"Chave natural {chave} repetida em {len(linhas)} linhas que divergem em "
                f"campo NAO multivalorado: {nao_colapsaveis}. Isto nao e vinculo N:N — sao "
                f"registros distintos com a mesma chave, e o banco (uq_jdv_current) so "
                f"aceita um vigente. Investigue a fonte antes de prosseguir; NADA foi escrito."
            )

        base = dict(linhas[0])
        for campo in CAMPOS_MULTIVALORADOS:
            valores = [linha.get(campo) for linha in linhas if linha.get(campo)]
            if valores:
                base[campo] = ", ".join(_ordenar_valores(valores))
        base.pop("hash", None)
        base.pop("extracted_at", None)
        saida.append(_finalizar_registro(base, extracted_at))
        colapsadas += 1
        absorvidas += len(linhas) - 1

    if colapsadas:
        logging.getLogger(__name__).info("Merged %d multi-valued identities", colapsadas)
    return saida

def normalizar_registro(row: dict, extracted_at: str, url_fonte: str = URL_TEMAS_CSV) -> dict:
    """Linha crua do CSV -> registro canonico J0.1 (schema locked).

    - situacao/referencias sao mantidas VERBATIM (apos strip) — parsing estruturado
      de lei+artigo e refinamento posterior, nao deste extrator.
    - has_thesis: teseFirmada nao-vazia apos strip. TODO tema entra no JSON.
    - hash: sha256[:16] da serializacao canonica dos campos de CONTEUDO
      (extracted_at fora do hash -> estavel entre execucoes)."""
    tese = _limpar(row.get("teseFirmada"))
    tipo_precedente = _limpar(row.get("tipoPrecedente"))
    data_afetacao, data_afetacao_raw = _parse_data(row.get("dataPrimeiraAfetacao"))
    data_julgamento, data_julgamento_raw = _parse_data(row.get("dataJulgamento"))

    registro = {
        "source": "STJ",
        "tipo": _tipo_canonico(tipo_precedente),
        "tipo_precedente": tipo_precedente,
        "numero": _limpar(row.get("numeroPrecedente")),
        "sequencial_precedente": _limpar(row.get("sequencialPrecedente")),
        "situacao": _limpar(row.get("situacao")),
        "orgao_julgador": _limpar(row.get("orgaoJulgador")),
        "questao_submetida": _limpar(row.get("questaoSubmetidaAJulgamento")),
        "tese": tese,
        "delimitacao_julgado": _limpar(row.get("delimitacaoJulgado")),
        "entendimento_anterior": _limpar(row.get("entendimentoAnterior")),
        "informacoes_complementares": _limpar(row.get("informacoesComplementares")),
        "referencia_legislativa": _limpar(row.get("referenciaLegislativa")),
        "referencia_sumular": _limpar(row.get("referenciaSumular")),
        "sumula_originada": _limpar(row.get("sumulaOriginada")),
        "data_primeira_afetacao": data_afetacao,
        "data_julgamento": data_julgamento,
        "numero_repercussao_geral_stf": _limpar(row.get("numeroRepercussaoGeralSTF")),
        "assuntos": _limpar(row.get("Assuntos")),
        "has_thesis": tese is not None,
        "url_fonte": url_fonte,
    }
    if data_afetacao_raw is not None:
        registro["data_primeira_afetacao_raw"] = data_afetacao_raw
    if data_julgamento_raw is not None:
        registro["data_julgamento_raw"] = data_julgamento_raw
    return _finalizar_registro(registro, extracted_at)

def parse_temas_csv(texto: str, extracted_at: str | None = None) -> list[dict]:
    """CSV oficial (texto ja decodificado) -> lista de registros canonicos.

    Valida o header ANTES de iterar: coluna esperada faltando -> LayoutInvalidoError
    (NUNCA prossegue). Colunas extras: toleradas com warning. NENHUM tema e descartado."""
    if extracted_at is None:
        extracted_at = date.today().isoformat()

    csv.field_size_limit(FIELD_SIZE_LIMIT)
    reader = csv.DictReader(io.StringIO(texto))
    fieldnames = reader.fieldnames or []

    faltando = [c for c in COLUNAS_ESPERADAS if c not in fieldnames]
    if faltando:
        raise LayoutInvalidoError(
            "Layout do temas.csv divergiu do esperado — colunas FALTANDO: "
            f"{faltando}. A fonte mudou; revisar COLUNAS_ESPERADAS e o schema "
            "canonico antes de prosseguir."
        )
    extras = [c for c in fieldnames if c not in COLUNAS_ESPERADAS]
    if extras:
        logging.getLogger(__name__).warning("Source has %d extra CSV columns; raw evidence retained", len(extras))

    return [normalizar_registro(row, extracted_at) for row in reader]

_RE_CANCELADA = re.compile(r"CANCELAD[AO]", re.IGNORECASE)

def parse_stj_sumulas_html(html: str, extracted_at: str | None = None,
                           url_fonte: str | None = None,
                           permitir_vazio: bool = False) -> list[dict]:
    """Pagina de listagem do SCON -> registros canonicos de sumula (VERBATIM).

    - enunciado = texto do div.blocoVerbete SEM o span.ramoSumula, whitespace
      normalizado — inclui o parentetico de julgamento e eventuais notas de
      cancelamento (nada se descarta; refinamento e downstream).
    - orgao_julgador/datas sao BEST-EFFORT (b.clsOrgaoJulgador / b.clsData): a
      estrutura varia entre sumulas (as recentes vem com o parentetico em texto
      puro) — ausencia NAO e erro.
    - permitir_vazio=True: pagina sem gridSumula retorna [] (fim da paginacao no
      fluxo de rede). Na pagina 1 (default) e SEMPRE LayoutInvalidoError."""
    if extracted_at is None:
        extracted_at = date.today().isoformat()
    if url_fonte is None:
        url_fonte = URL_STJ_SUMULAS_TPL.format(i=1)

    soup = BeautifulSoup(html, "html.parser")
    blocos = soup.find_all("div", class_="gridSumula")
    if not blocos:
        if permitir_vazio:
            return []
        raise LayoutInvalidoError(
            "Nenhum div.gridSumula na pagina do SCON — o layout mudou OU o host "
            "processo.stj.jus.br passou a servir challenge (Cloudflare, como o host "
            "canonico scon.stj.jus.br). Fallback manual documentado (NAO "
            "implementado): PDF oficial compilado de sumulas do STJ (~40MB) — ver "
            "docs/dicionario-fontes-juridicas.md §2.7."
        )

    registros = []
    for bloco in blocos:
        num_span = bloco.find("span", class_="numeroSumula")
        verbete = bloco.find("div", class_="blocoVerbete")
        if num_span is None or verbete is None:
            raise LayoutInvalidoError(
                "gridSumula sem span.numeroSumula e/ou div.blocoVerbete — "
                "layout da listagem do SCON mudou."
            )
        numero = _normalizar_espacos(num_span.get_text())
        if not numero:
            raise LayoutInvalidoError("span.numeroSumula vazio — layout do SCON mudou.")

        # Sinal primario de cancelamento: span.clsINDE no blocoNumSumula.
        inde = bloco.find("span", class_="clsINDE")
        cancelada = bool(inde is not None and _RE_CANCELADA.search(inde.get_text()))

        ramo = None
        ramo_span = verbete.find("span", class_="ramoSumula")
        if ramo_span is not None:
            ramo = _limpar(_normalizar_espacos(ramo_span.get_text()))
            ramo_span.extract()

        # Best-effort: presentes so quando o SCON estrutura o parentetico com <b>.
        orgao_b = verbete.find("b", class_="clsOrgaoJulgador")
        orgao = _limpar(_normalizar_espacos(orgao_b.get_text())) if orgao_b else None
        datas = verbete.find_all("b", class_="clsData")
        data_julgamento = data_publicacao = None
        data_julgamento_raw = data_publicacao_raw = None
        if len(datas) >= 1:
            data_julgamento, data_julgamento_raw = _parse_data(datas[0].get_text())
        if len(datas) >= 2:
            data_publicacao, data_publicacao_raw = _parse_data(datas[1].get_text())

        enunciado = _normalizar_espacos(verbete.get_text())
        if not enunciado:
            raise LayoutInvalidoError(
                f"Sumula {numero}: enunciado vazio no blocoVerbete — layout do SCON mudou."
            )
        # Fallback textual (variacao futura de marcador inline no verbete).
        if not cancelada and _RE_CANCELADA.search(enunciado):
            cancelada = True

        registro = {
            "source": "STJ",
            "tipo": "sumula",
            "numero": numero,
            "ramo": ramo,
            "enunciado": enunciado,
            "situacao": "cancelada" if cancelada else "em_vigor",
            "orgao_julgador": orgao,
            "data_julgamento": data_julgamento,
            "data_publicacao": data_publicacao,
            "has_thesis": bool(enunciado),
            "url_fonte": url_fonte,
        }
        if data_julgamento_raw is not None:
            registro["data_julgamento_raw"] = data_julgamento_raw
        if data_publicacao_raw is not None:
            registro["data_publicacao_raw"] = data_publicacao_raw
        registros.append(_finalizar_registro(registro, extracted_at))
    return registros

def parse_stf_teses_json(texto_com: str, texto_sem: str,
                         extracted_at: str | None = None) -> list[dict]:
    """Payloads JSON (listas "com" e "sem" tese) -> registros canonicos.

    has_thesis vem da LISTA DE ORIGEM (com/sem), NUNCA do texto: os registros "sem"
    TAMBEM tem descricaoTese preenchida (negativa de repercussao geral / descricao
    do tema — texto da fonte, nao tese vinculante). Filtro downstream usa has_thesis.
    Campo esperado faltando em qualquer item = LayoutInvalidoError; extras tolerados."""
    if extracted_at is None:
        extracted_at = date.today().isoformat()

    registros = []
    for origem, texto in (("com", texto_com), ("sem", texto_sem)):
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError as e:
            raise LayoutInvalidoError(
                f"Payload de teses '{origem}' nao e JSON valido ({e}) — o endpoint "
                "interno do STF mudou de formato."
            ) from e
        if not isinstance(payload, list):
            raise LayoutInvalidoError(
                f"Payload de teses '{origem}' nao e uma lista JSON "
                f"(veio {type(payload).__name__}) — o endpoint do STF mudou."
            )
        extras_vistos = set()
        for item in payload:
            if not isinstance(item, dict):
                raise LayoutInvalidoError(
                    f"Item nao-objeto no payload de teses '{origem}' — endpoint mudou."
                )
            faltando = [c for c in CAMPOS_TESES_ESPERADOS if c not in item]
            if faltando:
                raise LayoutInvalidoError(
                    f"Layout das teses '{origem}' divergiu — campos FALTANDO: "
                    f"{faltando}. Revisar CAMPOS_TESES_ESPERADOS e o schema canonico."
                )
            extras_vistos.update(k for k in item if k not in CAMPOS_TESES_ESPERADOS)

            data_andamento, data_andamento_raw = _parse_data(item.get("dataAndamento"))
            registro = {
                "source": "STF",
                "tipo": "tese_repercussao_geral",
                "numero": _limpar(item.get("numeroTema")),
                "numero_tema": item.get("numeroTema"),
                "incidente": _limpar(item.get("incidente")),
                "classe_processo": _limpar(item.get("siglaClasse")),
                "numero_processo": _limpar(item.get("numeroProcesso")),
                "tese": _limpar(item.get("descricaoTese")),
                "lista_origem": origem,
                "situacao": None,
                "data_andamento": data_andamento,
                "has_thesis": origem == "com",
                "url_fonte": URL_STF_TESES,
            }
            if data_andamento_raw is not None:
                registro["data_andamento_raw"] = data_andamento_raw
            registros.append(_finalizar_registro(registro, extracted_at))
        if extras_vistos:
            logging.getLogger(__name__).warning("Source has %d extra JSON fields; raw evidence retained", len(extras_vistos))
    return registros

_RE_SV_LINK = re.compile(r"sumariosumulas\.asp\?base=26&(?:amp;)?sumula=(\d+)")

_RE_SV_TITULO = re.compile(r"S[úu]mula Vinculante\s*(\d+)", re.IGNORECASE)

def parse_stf_sv_lista(html: str) -> list[str]:
    """Indice (base=26) -> lista de ids internos (strings numericas), dedup
    preservando ordem. 0 links = LayoutInvalidoError."""
    ids, vistos = [], set()
    for m in _RE_SV_LINK.finditer(html):
        sv_id = m.group(1)
        if sv_id not in vistos:
            vistos.add(sv_id)
            ids.append(sv_id)
    if not ids:
        raise LayoutInvalidoError(
            "Nenhum link sumariosumulas.asp?base=26&sumula=<id> no indice de "
            "sumulas vinculantes — o layout do portal STF mudou."
        )
    return ids

def parse_stf_sv_detalhe(html: str, url_fonte: str,
                         extracted_at: str | None = None,
                         sumula_id: str | None = None) -> dict:
    """Pagina de detalhe -> registro canonico da SV.

    enunciado = texto do PRIMEIRO div.parCOM apos o div.titulo "Súmula Vinculante N"
    (o proximo div.titulo e "Precedente Representativo" — delimitador; precedentes
    sao refinamento futuro). Titulo ausente ou enunciado vazio = LayoutInvalidoError."""
    if extracted_at is None:
        extracted_at = date.today().isoformat()
    if sumula_id is None:
        m = _RE_SV_LINK.search(url_fonte or "")
        sumula_id = m.group(1) if m else None

    soup = BeautifulSoup(html, "html.parser")
    titulo_sv, numero = None, None
    for div in soup.find_all("div", class_="titulo"):
        m = _RE_SV_TITULO.search(_normalizar_espacos(div.get_text()))
        if m:
            titulo_sv, numero = div, m.group(1)
            break
    if titulo_sv is None:
        raise LayoutInvalidoError(
            f"Detalhe sem div.titulo 'Súmula Vinculante N' — layout do portal STF "
            f"mudou ({url_fonte})."
        )

    enunciado = None
    for irmao in titulo_sv.find_next_siblings("div"):
        classes = irmao.get("class") or []
        if "titulo" in classes:
            break  # chegou no "Precedente Representativo" sem achar parCOM
        if "parCOM" in classes:
            enunciado = _normalizar_espacos(irmao.get_text())
            break
    if not enunciado:
        raise LayoutInvalidoError(
            f"SV {numero}: div.parCOM do enunciado ausente ou vazio — layout do "
            f"portal STF mudou ({url_fonte})."
        )

    registro = {
        "source": "STF",
        "tipo": "sumula_vinculante",
        "numero": numero,
        "sumula_id": sumula_id,
        "enunciado": enunciado,
        # Absence of a cancellation marker is not evidence of current legal validity.
        "situacao": "cancelada" if re.search(r"cancelad", titulo_sv.get_text().replace("\u200b", ""), re.I) else None,
        "has_thesis": bool(enunciado),
        "url_fonte": url_fonte,
    }
    return _finalizar_registro(registro, extracted_at)

def _rotulo_da_linha(linha: str) -> str | None:
    """A linha ABRE um campo? Devolve o rotulo canonico, ou None.

    Casa por PREFIXO normalizado, nao por igualdade: o livro TJPE ate-92 usa layout de DUAS
    COLUNAS, e 'Data do Julgamento          Data da Revogacao' e UMA linha com dois rotulos.
    Exigir igualdade fazia o rotulo vazar para dentro do valor do campo anterior (medido)."""
    limpa = _normalizar_espacos(linha)
    for rotulo in ROTULOS_SUMULA_TJ:
        if limpa == rotulo or limpa.startswith(rotulo + " "):
            return rotulo
    return None

def _fatiar_por_rotulo(linhas: list[str]) -> dict:
    """[linha] -> {rotulo: bloco}. Primeira ocorrencia de cada rotulo vence.

    Linha so-digito e numero de pagina do PDF, nunca conteudo: ela cai no meio do texto
    quando um registro atravessa a quebra de pagina."""
    campos: dict[str, str] = {}
    atual, buffer = None, []
    for linha in linhas:
        rotulo = _rotulo_da_linha(linha)
        if rotulo:
            if atual and atual not in campos:
                campos[atual] = "\n".join(buffer).strip()
            atual, buffer = rotulo, []
            continue
        if RE_LINHA_SO_DIGITOS.match(linha):
            continue
        buffer.append(linha.rstrip())
    if atual and atual not in campos:
        campos[atual] = "\n".join(buffer).strip()
    return campos

def _primeiro_valor(campos: dict, *rotulos: str) -> str | None:
    """Primeiro rotulo presente entre as grafias aceitas (elas variam entre livros)."""
    for rotulo in rotulos:
        if campos.get(rotulo):
            return campos[rotulo]
    return None

def _primeira_linha_util(bloco: str | None) -> str | None:
    if not bloco:
        return None
    for linha in bloco.splitlines():
        if linha.strip():
            return _normalizar_espacos(linha)
    return None

def _bloco_limpo(bloco: str | None) -> str | None:
    """Preserva a quebra de linha (o enunciado e citavel verbatim) e colapsa so o
    espacamento horizontal do PDF."""
    if not bloco:
        return None
    limpo = re.sub(r"[ \t]+", " ", bloco).strip()
    return limpo or None

def _texto_corrido(bloco: str | None) -> str | None:
    """Igual a `_bloco_limpo`, mas COLAPSA a quebra de linha.

    Usado so no `enunciado`, e a diferenca importa: a quebra de um PDF e largura de coluna,
    nao semantica, e este campo vira o `thesis_text` que e EMBEDDADO e renderizado no
    WhatsApp. As 4 fontes J0 ja emitem o enunciado em linha unica
    (`parse_stj_sumulas_html` faz `_normalizar_espacos`); manter os `\\n` duros aqui
    deixava as fontes estaduais fora do padrao no campo mais importante."""
    if not bloco:
        return None
    limpo = _normalizar_espacos(bloco)
    return limpo or None

def _segunda_data(bloco: str | None) -> str | None:
    """2a data dd/mm/aaaa do bloco, se houver. No layout de duas colunas do TJPE ela e a
    data da REVOGACAO ('Data do Julgamento    Data da Revogacao' numa linha so)."""
    if not bloco:
        return None
    achados = RE_DATA_BR.findall(bloco)
    if len(achados) < 2:
        return None
    dia, mes, ano = achados[1]
    return f"{dia}/{mes}/{ano}"

def _data_de_julgamento(bloco: str | None) -> tuple[str | None, str | None]:
    """-> (iso, raw_nao_parseavel), mesmo contrato de _parse_data.

    Duas particularidades MEDIDAS, e nenhuma descarta dado: (1) no layout de duas colunas
    do TJPE a linha de valores traz julgamento e revogacao — a PRIMEIRA data e a do
    julgamento (coluna da esquerda); (2) o Enunciado 58 do TJMG traz '27/03/19', com ano de
    DOIS digitos (erro da fonte: o vizinho 57 traz 2019), entao ele vai inteiro para
    data_julgamento_raw em vez de virar None silencioso."""
    if not bloco:
        return None, None
    achado = RE_DATA_BR.search(bloco)
    if achado:
        dia, mes, ano = achado.groups()
        return f"{ano}-{mes}-{dia}", None
    return None, _primeira_linha_util(bloco)

def _linha_do_numero_tjpe(linhas: list[str], cabeca: int) -> tuple | None:
    """Acha a linha do NUMERO depois da cabeca 'Sumula'. -> (indice, numero, sufixo).

    Duas armadilhas, as duas medidas:
      - o numero pode vir depois de linha(s) EM BRANCO (sumulas 145/153/156 do livro
        110-172), entao casamento adjacente nao serve;
      - quando a quebra de pagina cai entre a cabeca e o numero, o NUMERO DA PAGINA entra
        primeiro e e indistinguivel do numero da sumula pela forma. O que os separa e o
        que vem DEPOIS: o numero de verdade e seguido por um rotulo de campo
        ('Orgao Julgador', ...); o da pagina e seguido por outro numero. Sem isto, a
        entrada 'Sumula' / '24' / '003' emitia uma sumula 24 com o texto da 3."""
    candidato = None
    j = cabeca + 1
    while j < len(linhas):
        if not linhas[j].strip():
            j += 1
            continue
        achado = RE_NUMERO_SUMULA_TJPE.match(linhas[j])
        if not achado:
            break
        candidato = (j, int(achado.group(1)), achado.group(2))
        # olha o proximo nao-vazio: rotulo confirma, outro numero descarta este
        k = j + 1
        while k < len(linhas) and not linhas[k].strip():
            k += 1
        if k < len(linhas) and _rotulo_da_linha(linhas[k]):
            return candidato
        j = k if k > j else j + 1
    return candidato

def parse_tjpe_sumulas_pdf(texto: str, extracted_at: str, url_fonte: str,
                           livro: str) -> list[dict]:
    """Texto de UM livro de sumulas do TJPE -> registros canonicos."""
    linhas = texto.splitlines()
    inicios = []
    for i, linha in enumerate(linhas):
        if not RE_CABECA_SUMULA_TJPE.match(linha):
            continue
        achado = _linha_do_numero_tjpe(linhas, i)
        if achado:
            j, numero, sufixo = achado
            inicios.append((i, j, numero, sufixo))

    registros = []
    for k, (_cabeca, j, numero, sufixo) in enumerate(inicios):
        fim = inicios[k + 1][0] if k + 1 < len(inicios) else len(linhas)
        chave = _normalizar_espacos(sufixo).lower() if sufixo else None
        if chave not in SITUACAO_TJPE:
            raise LayoutInvalidoError(
                f"Sumula TJPE {numero}: sufixo de situacao desconhecido {sufixo!r} "
                f"(conhecidos: {sorted(x for x in SITUACAO_TJPE if x)}) — vocabulario da "
                f"fonte mudou ({url_fonte})."
            )
        campos = _fatiar_por_rotulo(linhas[j + 1:fim])
        enunciado = _texto_corrido(campos.get("Enunciado"))
        if not enunciado:
            raise LayoutInvalidoError(
                f"Sumula TJPE {numero}: campo 'Enunciado' ausente ou vazio — layout do "
                f"livro mudou ({url_fonte})."
            )
        bloco_julgamento = _primeiro_valor(campos, "Data do Julgamento", "Data de julgamento")
        iso, bruto = _data_de_julgamento(bloco_julgamento)
        pub_iso, pub_raw = _data_de_julgamento(_primeiro_valor(
            campos, "Data da Publicação/Fonte", "Data da publicação/Fonte"))
        registro = {
            "source": "TJPE",
            "tipo": "sumula_tj",
            "numero": str(numero),
            "enunciado": enunciado,
            # Cancelada/revogada COM enunciado continua embeddavel: o gate e PURAMENTE
            # has_thesis, e a situacao e servida como bandeira (mesma regra do J0).
            "has_thesis": True,
            "situacao": SITUACAO_TJPE[chave],
            "orgao_julgador": _primeira_linha_util(campos.get("Órgão Julgador")),
            "data_julgamento": iso,
            "data_julgamento_raw": bruto,
            "data_publicacao": pub_iso,
            "data_publicacao_raw": pub_raw,
            # 2a data do bloco de duas colunas: e a da REVOGACAO, e e justamente o dado que
            # qualifica a bandeira `revogada`. Sem isto ela era lida e jogada fora.
            "data_revogacao_raw": _segunda_data(bloco_julgamento),
            "referencia_legislativa": _bloco_limpo(_primeiro_valor(
                campos, "Referência Legislativa", "Referência legislativa", "Referências")),
            "precedentes": _bloco_limpo(campos.get("Precedentes")),
            "livro": livro,
            "url_fonte": url_fonte,
        }
        registros.append(_finalizar_registro(
            registro, extracted_at, ignorar=CAMPOS_VOLATEIS_ESTADUAL))
    return registros

def parse_tjmg_sumulas_pdf(texto: str, extracted_at: str, url_fonte: str) -> list[dict]:
    """Texto do PDF de sumulas do TJMG -> registros canonicos."""
    linhas = texto.splitlines()
    inicios = []
    for i, linha in enumerate(linhas):
        # As 89 entradas do SUMARIO tem a MESMA cabeca do corpo, com dot leaders no fim
        # ('ENUNCIADO 12 - CANCELADO ........'). Este guard chegou a ser removido em
        # 2026-08-16 por ser inalcancavel sob a regex ESTREITA de entao — e voltou no mesmo
        # dia: com o sufixo guloso (que o achado do verificador obrigou) a regex passou a
        # casar as 89, e o guard virou LOAD-BEARING. Sem ele o sumario inteiro vira
        # registro. Mutacao trava os dois lados.
        if RE_DOT_LEADERS.search(linha):
            continue
        achado = RE_CABECA_SUMULA_TJMG.match(linha)
        if achado:
            inicios.append((i, int(achado.group(1)), achado.group(2)))

    registros = []
    for k, (i, numero, sufixo) in enumerate(inicios):
        fim = inicios[k + 1][0] if k + 1 < len(inicios) else len(linhas)
        chave = _normalizar_espacos(sufixo).lower() if sufixo else None
        if chave not in SITUACAO_TJMG:
            raise LayoutInvalidoError(
                f"Enunciado TJMG {numero}: sufixo de situacao desconhecido {sufixo!r} "
                f"(conhecidos: {sorted(x for x in SITUACAO_TJMG if x)}) — vocabulario da "
                f"fonte mudou ({url_fonte})."
            )
        bloco = linhas[i + 1:fim]
        # O enunciado do TJMG nao tem rotulo proprio: e tudo entre a cabeca e o 1o rotulo.
        corte = len(bloco)
        for idx, linha in enumerate(bloco):
            if _rotulo_da_linha(linha):
                corte = idx
                break
        enunciado = _texto_corrido("\n".join(
            x for x in bloco[:corte] if not RE_LINHA_SO_DIGITOS.match(x)))
        if not enunciado:
            raise LayoutInvalidoError(
                f"Enunciado TJMG {numero}: texto ausente entre o cabecalho e o primeiro "
                f"rotulo — layout do PDF mudou ({url_fonte})."
            )
        campos = _fatiar_por_rotulo(bloco[corte:])
        iso, bruto = _data_de_julgamento(campos.get("Data do Julgamento"))
        pub_iso, pub_raw = _data_de_julgamento(_primeiro_valor(
            campos, "Data da Publicação/Fonte", "Data da publicação/Fonte"))
        registro = {
            "source": "TJMG",
            "tipo": "sumula_tj",
            "numero": str(numero),
            "enunciado": enunciado,
            "has_thesis": True,
            "situacao": SITUACAO_TJMG[chave],
            "orgao_julgador": _primeira_linha_util(campos.get("Órgão Julgador")),
            "data_julgamento": iso,
            "data_julgamento_raw": bruto,
            "data_publicacao": pub_iso,
            "data_publicacao_raw": pub_raw,
            "referencia_legislativa": _bloco_limpo(_primeiro_valor(
                campos, "Referência legislativa", "Referência Legislativa")),
            "precedentes": _bloco_limpo(campos.get("Precedentes")),
            "nota_situacao": _bloco_limpo(_primeiro_valor(
                campos, "Nota de cancelamento", "Nota de atualização")),
            "url_fonte": url_fonte,
        }
        registros.append(_finalizar_registro(
            registro, extracted_at, ignorar=CAMPOS_VOLATEIS_ESTADUAL))
    return registros

def numeracao_com_buraco(registros: list[dict]) -> list[int]:
    """Numeros ausentes na faixa min..max. Sumula nao pula numero: um buraco e sinal de
    que o parser perdeu um bloco, nao de que a fonte encolheu. So o fluxo de REDE cobra
    isso — amostra local tem buraco por construcao."""
    numeros = sorted(int(r["numero"]) for r in registros)
    if not numeros:
        return []
    return [n for n in range(numeros[0], numeros[-1] + 1) if n not in set(numeros)]

def _links_de_pdf(html: str, url_base: str, filtro: re.Pattern | None = None) -> list[tuple]:
    """[(rotulo, url_absoluta)] dos <a> que apontam PDF.

    urljoin e obrigatorio: o href do TJMG e relativo (../../../data/files/...) e montar a
    URL a mao devolve 404 (medido). `filtro` casa contra o ROTULO do link — no TJPE a mesma
    pagina linka documentos de outros orgaos, que nao sao sumula do tribunal."""
    soup = BeautifulSoup(html, "html.parser")
    achados, vistos = [], set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        rotulo = _normalizar_espacos(tag.get_text(" "))
        if ".pdf" not in href.lower() and ".pdf" not in rotulo.lower():
            continue
        if filtro and not filtro.search(rotulo):
            continue
        url = urljoin(url_base, href)
        if url in vistos:
            continue
        vistos.add(url)
        achados.append((rotulo, url))
    return achados

def livros_tjpe_do_indice(html: str) -> list[tuple]:
    """HTML do indice do TJPE -> [(rotulo, url)] dos LIVROS de sumula.

    Funcao pura de proposito: o fluxo so faz IO. Enquanto a resolucao do indice vivia
    dentro do fluxo, o filtro de rotulo nao tinha como ser exercitado por teste — e
    mutacao que sobrevive e defeito do teste, nao robustez do codigo."""
    livros = _links_de_pdf(html, URL_TJPE_SUMULAS_INDICE, filtro=RE_TJPE_LIVRO)
    if len(livros) < MIN_TJPE_LIVROS:
        todos = _links_de_pdf(html, URL_TJPE_SUMULAS_INDICE)
        raise LayoutInvalidoError(
            f"Indice do TJPE: {len(livros)} livro(s) casaram o filtro "
            f"{RE_TJPE_LIVRO.pattern!r} (min {MIN_TJPE_LIVROS}) — a pagina mudou ou o "
            f"rotulo deixou de casar. PDFs na pagina: {[r for r, _ in todos][:8]}. "
            "NAO gravando JSON canonico."
        )
    return livros

def consolidado_tjmg_do_indice(html: str) -> tuple:
    """HTML do indice do TJMG -> (rotulo, url) do UNICO PDF consolidado.

    O filtro de rotulo vem ANTES da cobranca de unicidade: cobrar `len == 1` sobre todos
    os <a> com .pdf fazia qualquer arquivo acrescentado a pagina (manual, formulario)
    zerar a extracao do tribunal inteiro."""
    pdfs = _links_de_pdf(html, URL_TJMG_SUMULAS_INDICE, filtro=RE_TJMG_CONSOLIDADO)
    if len(pdfs) != 1:
        todos = _links_de_pdf(html, URL_TJMG_SUMULAS_INDICE)
        raise LayoutInvalidoError(
            f"Indice do TJMG: {len(pdfs)} PDF(s) casaram o filtro "
            f"{RE_TJMG_CONSOLIDADO.pattern!r}; esperado exatamente 1 (o consolidado). "
            f"Rotulos que casaram: {[r for r, _ in pdfs][:5]}; PDFs na pagina: "
            f"{[r for r, _ in todos][:8]}. NAO gravando JSON canonico."
        )
    return pdfs[0]

def _slug_de_livro(rotulo: str) -> str:
    """Rotulo do link -> identificador estavel do livro, para o campo residual `livro`."""
    slug = unicodedata.normalize("NFKD", rotulo).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").lower()
    return re.sub(r"_?pdf$", "", slug) or "livro"

def _validar_corpus_estadual(registros: list[dict], tribunal: str, minimo: int,
                             maior_conhecido: int) -> None:
    """Guards do fluxo de REDE (amostra local NAO valida). Truncamento silencioso do PDF
    vira falha explicita em vez de JSON canonico menor sobrescrevendo o bom.

    Sao TRES cobrancas, e a terceira existe porque as duas primeiras sao cegas nas BORDAS:
    perder o maior ou o menor numero da faixa nao abre buraco e nao derruba a contagem
    minima (cabem 9 e 12 perdas nos pisos medidos) — e a borda de cima e exatamente onde a
    sumula NOVA, de layout ainda nao visto, aparece."""
    if len(registros) < minimo:
        raise RuntimeError(
            f"Contagem suspeita: {len(registros)} sumulas do {tribunal} (min {minimo}). "
            "PDF truncado ou layout mudou — NAO gravando JSON canonico."
        )
    buracos = numeracao_com_buraco(registros)
    if buracos:
        raise LayoutInvalidoError(
            f"Numeracao do {tribunal} com buraco em {buracos} — sumula nao pula numero, "
            "entao o parser perdeu bloco(s). NAO gravando JSON canonico."
        )
    numeros = sorted(int(r["numero"]) for r in registros)
    if numeros[0] != 1:
        raise LayoutInvalidoError(
            f"Faixa do {tribunal} comeca em {numeros[0]}, nao em 1 — o parser perdeu o "
            "inicio, e perda de borda nao abre buraco. NAO gravando JSON canonico."
        )
    if numeros[-1] < maior_conhecido:
        raise LayoutInvalidoError(
            f"Faixa do {tribunal} termina em {numeros[-1]}, abaixo do maior ja medido "
            f"({maior_conhecido}) — sumula nao e revogada do catalogo, entao ou o parser "
            "perdeu o fim ou o documento encolheu. NAO gravando JSON canonico."
        )
