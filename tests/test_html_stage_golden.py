"""Golden do estágio HTML → clean.txt: fecha o ÚNICO buraco de teste do pipeline.

O golden existente (test_extraction_golden.py) cobre parse_law (clean.txt → JSON).
Este cobre o estágio ANTERIOR — html_to_clean_text (bytes crus do Planalto →
clean.txt) — onde moraram TODOS os bugs silenciosos de 2026-07: <strike> comendo
rótulo (CF88 Art. 7º a/b), kerning fatiando palavra ("O v alor d e vido"), redação
riscada via CSS line-through vazando como vigente e boundary de ANEXO da LC123.

Fixtures (tests/fixtures/, gzip):
  html/{base}.htm.gz    — HTML CRU capturado do Planalto (bytes originais, 2026-07-07,
                          provado byte-idêntico à captura de produção 2026-07-06)
  clean/{base}_clean.txt.gz — clean.txt esperado, CONGELADO junto com o HTML

Qualquer mudança no estágio HTML (decompose, get_text, merge, normalização...)
quebra este teste na hora. Mudança INTENCIONAL = regenerar as fixtures de clean
conscientemente — o diff da regeneração é o artefato de revisão da mudança.

Encoding: fixtures são BYTES crus (a LMP é UTF-16 — nunca reencodar).
"""
import gzip
import os

import pytest

from leis_brasileiras import extraction as extrair_leis

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# base do arquivo -> sigla no LEIS_CONFIG (mesmo mapa do golden de parse_law)
LAWS = {
    "cadastro_positivo": "CADPOS", "cdc": "CDC", "cf88": "CF88", "clt": "CLT",
    "codigo_civil": "CC", "cp": "CP", "cpc": "CPC", "eca": "ECA", "lc123": "LC123",
    "lei_inquilinato": "LI", "lei_maria_penha": "LMP", "lei_terceirizacao": "LT",
    "lgpd": "LGPD", "lei_execucao_penal": "LEP",
}


def _read_gz(path: str) -> bytes:
    with gzip.open(path, "rb") as f:
        return f.read()


@pytest.mark.parametrize("base", list(LAWS), ids=[LAWS[b] for b in LAWS])
def test_html_stage_reproduz_clean_txt(base):
    html_path = os.path.join(_FIX, "html", f"{base}.htm.gz")
    clean_path = os.path.join(_FIX, "clean", f"{base}_clean.txt.gz")
    if not (os.path.exists(html_path) and os.path.exists(clean_path)):
        pytest.fail(f"fixture ausente para {base} — golden do estágio HTML é obrigatório")

    sigla = LAWS[base]
    raw = _read_gz(html_path)
    esperado = _read_gz(clean_path).decode("utf-8")

    obtido = extrair_leis.html_to_clean_text(raw, sigla, extrair_leis.LEIS_CONFIG[sigla])

    assert obtido == esperado, (
        f"{sigla}: html_to_clean_text divergiu da fixture congelada — mudança no estágio "
        f"HTML (len {len(obtido)} vs {len(esperado)}). Se INTENCIONAL, regenere "
        f"tests/fixtures/clean/ e revise o diff."
    )


@pytest.mark.parametrize("base", list(LAWS), ids=[LAWS[b] for b in LAWS])
def test_html_stage_clean_alimenta_parse_law(base):
    """End-to-end leve: o clean.txt da fixture passa no parse_law sem estourar o
    guardrail (tem 'Art. N', estrutura reconhecida). Não compara JSON — isso é
    papel do golden de parse_law sobre data/ — só garante que os dois estágios
    se encaixam."""
    clean_path = os.path.join(_FIX, "clean", f"{base}_clean.txt.gz")
    if not os.path.exists(clean_path):
        pytest.fail(f"fixture ausente para {base}")

    sigla = LAWS[base]
    cfg = extrair_leis.LEIS_CONFIG[sigla]
    clean = _read_gz(clean_path).decode("utf-8")
    blocos, _stats = extrair_leis.parse_law(
        clean, sigla, cfg["versao"], cfg["url"], "2026-07-06", cfg)
    assert len(blocos) > 0
