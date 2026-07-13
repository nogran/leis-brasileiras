"""Golden/snapshot da extração: trava o PARSER contra regressão silenciosa.

Para cada lei, roda `parse_law(clean.txt_commitado)` e exige que o resultado seja IGUAL ao
JSON commitado (exceto `capture_id`, que é injetado depois com base na captura). Como o
clean.txt e o JSON foram gerados pela MESMA extração, qualquer mudança de comportamento do
parser (estrutura, status, vetos, referências, hierarquia, hashes, overrides, lápides,
dedup) quebra este teste ANTES do commit.

Cobertura: parser determinístico (clean.txt -> JSON). NÃO cobre o decode (raw HTML ->
clean.txt) — isso fica nos unit tests de decode_utf16/strip_padding_tail e nas invariantes
sem-NUL/sem-FFFD. Um golden raw-HTML->JSON completo exige fixtures de HTML cru (futuro).

Lê a extração MAIS RECENTE de cada lei (glob por data), então sobrevive a re-extrações.
"""
import glob
import json
import os
import re

import pytest

import extrair_leis
import laws

_ROOT = os.path.dirname(os.path.dirname(__file__))
_DATA = os.path.join(_ROOT, "data")
_DATE = re.compile(r'_(\d{4}-\d{2}-\d{2})\.json$')

# base do arquivo -> sigla, derivado do catálogo único (laws.yml). NUNCA re-hardcodar.
LAWS = laws.NOME_BASE_PARA_SIGLA


def _latest_pair(base):
    """(data, json_path, clean_path) da extração mais recente com AMBOS os arquivos."""
    dates = {}
    for f in glob.glob(os.path.join(_DATA, f"{base}_*.json")):
        m = _DATE.search(f)
        if m:
            dates.setdefault(m.group(1), {})["json"] = f
    for f in glob.glob(os.path.join(_DATA, f"{base}_*_clean.txt")):
        m = re.search(r'_(\d{4}-\d{2}-\d{2})_clean\.txt$', f)
        if m and m.group(1) in dates:
            dates[m.group(1)]["clean"] = f
    completos = {d: v for d, v in dates.items() if "json" in v and "clean" in v}
    if not completos:
        return None
    d = max(completos)
    return d, completos[d]["json"], completos[d]["clean"]


def _sem_capture_id(blocos):
    return [{k: v for k, v in b.items() if k != "capture_id"} for b in blocos]


@pytest.mark.parametrize("base", list(LAWS), ids=[LAWS[b] for b in LAWS])
def test_parser_reproduz_json_commitado(base):
    par = _latest_pair(base)
    if not par:
        pytest.skip(f"sem par clean.txt+json commitado para {base}")
    data_ext, json_path, clean_path = par
    sigla = LAWS[base]
    cfg = extrair_leis.LEIS_CONFIG[sigla]

    clean_text = open(clean_path, encoding="utf-8").read()
    esperado = json.load(open(json_path, encoding="utf-8"))
    obtido, _stats = extrair_leis.parse_law(
        clean_text, sigla, cfg["versao"], cfg["url"], data_ext, cfg)

    assert _sem_capture_id(obtido) == _sem_capture_id(esperado), (
        f"{sigla}: parse_law divergiu do JSON commitado — regressao no parser "
        f"(got {len(obtido)} blocos, esperado {len(esperado)})")


# ═══════════════════════════════════════════════════════════════════════════════
# Smoke do extrair_lei COMPLETO (session+db+arquivos mockados). Cobre o fluxo fora do
# parse_law (capture, writes, print de resumo) — teria pego o NameError 'lapides_count'
# que o refactor deixou no print e o golden (que so testa parse_law) nao alcanca.
# ═══════════════════════════════════════════════════════════════════════════════

class _Resp:
    status_code = 200

    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, content):
        self._content = content

    def get(self, url, timeout=None):
        return _Resp(self._content)


class _Tx:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


def test_extrair_lei_fluxo_completo_nao_quebra(monkeypatch, tmp_path):
    html = ("<html><body>O PRESIDENTE Dispõe sobre teste. "
            "Art. 1 Primeiro artigo do teste com conteudo. "
            "Art. 2 Segundo artigo do teste com conteudo.</body></html>")
    monkeypatch.setattr(extrair_leis.db, "transaction", lambda *a, **k: _Tx())
    monkeypatch.setattr(extrair_leis.db, "get_latest_capture_hash", lambda cur, sigla: None)
    monkeypatch.setattr(extrair_leis.db, "insert_capture", lambda cur, **k: "cap-1")
    monkeypatch.chdir(tmp_path)

    ok = extrair_leis.extrair_lei(_Session(html.encode("utf-8")), "CDC", force=True)
    assert ok is True   # nao levanta (ex: NameError no print de resumo)

    # JSON principal = a LISTA de artigos. Filtra o sidecar _riscadas (um dict) que o glob
    # "cdc_*.json" tambem casa — senao escritos[0] fica nao-deterministico e as vezes carregava
    # o dict, quebrando o assert com TypeError. Regra do repo: consumidores de {lei}_*.json
    # DEVEM filtrar _riscadas.
    principais = [f for f in glob.glob(str(tmp_path / "data" / "cdc_*.json"))
                  if "_riscadas" not in f]
    assert principais, "extrair_lei deveria ter escrito o JSON principal"
    data = json.load(open(principais[0], encoding="utf-8"))
    assert any(b["artigo"].startswith("Art.") for b in data)

    # Sidecar _riscadas: smoke ESTRUTURAL — foi escrito e e um dict bem-formado (historico de
    # redacoes). Aqui o HTML nao tem riscados, entao `riscadas` fica vazio — so a forma importa;
    # o CONTEUDO do riscado e travado pelo test_completeness_golden ("nada da pagina se perde").
    riscadas = glob.glob(str(tmp_path / "data" / "cdc_*_riscadas.json"))
    assert riscadas, "extrair_lei deveria ter escrito o sidecar _riscadas"
    risc = json.load(open(riscadas[0], encoding="utf-8"))
    assert isinstance(risc, dict) and isinstance(risc.get("riscadas"), list)
    assert risc.get("lei") == "CDC" and risc["total"] == len(risc["riscadas"])


def test_parse_law_aborta_sem_artigo():
    # guardrail: parser sem nenhum "Art. N" (encoding/HTML corrompido) -> raise
    cfg = extrair_leis.LEIS_CONFIG["CDC"]
    with pytest.raises(RuntimeError, match=r"sem nenhum 'Art\. N'|estrutura"):
        extrair_leis.parse_law(
            "Dispoe sobre teste. Texto sem qualquer estrutura de dispositivo aqui.",
            "CDC", cfg["versao"], cfg["url"], "2026-07-02", cfg)


def test_extrair_lei_aborta_nul_em_massa(monkeypatch, tmp_path):
    # guardrail: NUL em massa (>0.5%) -> aborta ANTES de persistir/ingerir
    content = b"Dispoe sobre teste. " + b"\x00" * 300 + b" Art. 1 texto"
    monkeypatch.setattr(extrair_leis.db, "transaction", lambda *a, **k: _Tx())
    monkeypatch.setattr(extrair_leis.db, "get_latest_capture_hash", lambda cur, sigla: None)
    monkeypatch.setattr(extrair_leis.db, "insert_capture", lambda cur, **k: "cap-1")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match=r"corrompida|NUL"):
        extrair_leis.extrair_lei(_Session(content), "CDC", force=True)
