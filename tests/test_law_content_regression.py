"""Regressao de CONTEUDO das leis extraidas (data/*.json).

Trava o que ja conhecemos pra nao voltar a bugs de extracao/encoding:
- INVARIANTES por lei: sem NUL, contagem de artigos-base nao regride, ha 'Art. N' real.
  (Se o encoding quebrar de novo, o parser perde artigos -> contagem cai -> falha aqui.)
- EMENDAS 2026-07 conhecidas (comparacao abril x julho): artigos novos e marcadores de
  conteudo que uma extracao futura NAO pode perder silenciosamente.

Le sempre a versao MAIS RECENTE de cada lei (glob por data no nome), entao sobrevive a
re-extracoes futuras. FFFD nao e checado aqui de proposito — o trim de byte truncado ja
e travado no nivel de codigo por TestDecodeUtf16.test_stream_truncado_nao_explode.
"""
import glob
import json
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(__file__))
_DATA = os.path.join(_ROOT, "data")
_PARTE = re.compile(r'\s*\(Parte \d+/\d+\)')
_DATED = re.compile(r'_(\d{4}-\d{2}-\d{2})\.json$')

# base do arquivo -> (sigla, piso de artigos-base). Piso = contagem atual; artigos so
# crescem com emendas. Se cair, e perda de dados (bug) -> teste falha. Subir se emenda
# legitima adicionar artigos.
LAWS = {
    "cadastro_positivo": ("CADPOS", 21),
    "cdc": ("CDC", 131),
    "cf88": ("CF88", 416),
    "clt": ("CLT", 1027),
    "codigo_civil": ("CC", 2093),
    "cp": ("CP", 435),
    "cpc": ("CPC", 1074),
    "eca": ("ECA", 326),
    "lc123": ("LC123", 132),
    "lei_inquilinato": ("LI", 92),
    "lei_maria_penha": ("LMP", 58),
    "lei_terceirizacao": ("LT", 31),
    "lgpd": ("LGPD", 81),
}


def _latest_file(base):
    """Arquivo de dados mais recente da lei (exclui _questions/_clean)."""
    cands = [f for f in glob.glob(os.path.join(_DATA, f"{base}_*.json")) if _DATED.search(f)]
    return max(cands, key=lambda f: _DATED.search(f).group(1)) if cands else None


def _load(base):
    path = _latest_file(base)
    if not path:
        pytest.skip(f"sem arquivo de dados para {base}")
    return json.load(open(path, encoding="utf-8"))


def _base_articles(blocks):
    return {_PARTE.sub('', b['artigo']).strip() for b in blocks}


# ═══════════════════════════════════════════════════════════════════════════════
# Invariantes por lei
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("base", list(LAWS), ids=[v[0] for v in LAWS.values()])
class TestLawInvariants:
    def test_sem_nul_bytes(self, base):
        blocks = _load(base)
        com_nul = [b['artigo'] for b in blocks if '\x00' in (b.get('texto_limpo') or '')]
        assert not com_nul, f"{LAWS[base][0]}: NUL em {com_nul[:5]} (encoding quebrado)"

    def test_sem_caractere_substituicao(self, base):
        # U+FFFD = corrupcao de decode (byte truncado/invalido). Ex.: LMP Art. 46 pre-fix.
        blocks = _load(base)
        com_fffd = [b['artigo'] for b in blocks if chr(0xFFFD) in (b.get('texto_limpo') or '')]
        assert not com_fffd, f"{LAWS[base][0]}: U+FFFD em {com_fffd[:5]} (corrupcao de decode)"

    def test_contagem_nao_regride(self, base):
        blocks = _load(base)
        n = len(_base_articles(blocks))
        floor = LAWS[base][1]
        assert n >= floor, f"{LAWS[base][0]}: {n} artigos-base < piso {floor} — perda de dados?"

    def test_tem_artigo_real(self, base):
        blocks = _load(base)
        assert any(re.match(r'Art\.\s*\d', b['artigo']) for b in blocks), \
            f"{LAWS[base][0]}: nenhum 'Art. N' — parser nao achou estrutura"


# ═══════════════════════════════════════════════════════════════════════════════
# Emendas 2026-07 conhecidas (abril -> julho) — nao podem sumir numa extracao futura
# ═══════════════════════════════════════════════════════════════════════════════

def _base_text_map(base):
    blocks = _load(base)
    g = {}
    for b in blocks:
        k = _PARTE.sub('', b['artigo']).strip()
        g.setdefault(k, []).append((b.get('parte_num') or 0, b.get('texto_limpo') or ''))
    return {k: ' '.join(t for _, t in sorted(v)) for k, v in g.items()}


class TestKnownAmendmentsLMP:
    """Lei Maria da Penha: +2 artigos e 3 emendas de conteudo (incidente da LMP)."""

    def test_artigos_novos_presentes(self):
        arts = _base_articles(_load("lei_maria_penha"))
        assert {"Art. 12-D", "Art. 16-A"} <= arts

    def test_art7_violencia_vicaria(self):
        assert "vicária" in _base_text_map("lei_maria_penha")["Art. 7"].lower()

    def test_art22_monitoracao_eletronica(self):
        assert "monitora" in _base_text_map("lei_maria_penha")["Art. 22"].lower()

    def test_art39_paragrafo_unico(self):
        assert "parágrafo único" in _base_text_map("lei_maria_penha")["Art. 39"].lower()


class TestKnownAmendmentsCP:
    """Codigo Penal: +3 artigos (Lei 14.994/2024 e crimes contra o Estado Democratico)."""

    def test_artigos_novos_presentes(self):
        arts = _base_articles(_load("cp"))
        assert {"Art. 121-B", "Art. 359-M-A", "Art. 359-M-B"} <= arts


class TestKnownAmendmentsECA:
    """ECA: +2 artigos."""

    def test_artigos_novos_presentes(self):
        arts = _base_articles(_load("eca"))
        assert {"Art. 11-A", "Art. 89-A"} <= arts


# ═══════════════════════════════════════════════════════════════════════════════
# Caput-nu (artigo sem conteudo) — familia do reparo de dispositivos orfaos
# ═══════════════════════════════════════════════════════════════════════════════

# Texto que e SO o rotulo do artigo + pontuacao residual (ex: "Art. 384 -"), sem
# conteudo nem anotacao de revogacao. Ver known_issues.json > caput_revogado_nu:
# 261 REVOGADOS pre-existentes perderam a anotacao na limpeza (a redacao original
# riscada do Planalto nao e capturada — backlog nivel 2 dos dispositivos orfaos).
# Para vigente/vetado o mesmo padrao seria PERDA DE CONTEUDO — nunca tolerado.
_RE_CAPUT_NU = re.compile(r'^Art\.\s*[\d.]+(?:-[A-Z])?\s*(?:[-–—.:°º]|a\s+[\d.]+\.?)*\s*$')

# Ratchet: contagem ATUAL de revogados-nus por lei (extracao 2026-07-02, pos-fix
# dos orfaos). Extracao futura pode DIMINUIR (anotacao recuperada), nunca crescer —
# crescer significa que a limpeza passou a comer anotacao de artigo com conteudo.
# Se um reparo legitimo reduzir a contagem, ABAIXE o teto correspondente.
_CAPUT_NU_TETO = {
    "cadastro_positivo": 0, "cdc": 0, "cf88": 0, "clt": 179, "codigo_civil": 65,
    "cp": 11, "cpc": 1, "eca": 2, "lc123": 2, "lei_inquilinato": 0,
    "lei_maria_penha": 0, "lei_terceirizacao": 0, "lgpd": 1,
}


def _caputs_nus(blocks, statuses):
    return [b['artigo'] for b in blocks
            if b.get('status') in statuses
            and _RE_CAPUT_NU.match((b.get('texto_limpo') or '').strip())]


@pytest.mark.parametrize("base", list(LAWS), ids=[v[0] for v in LAWS.values()])
class TestCaputNu:
    def test_vigente_ou_vetado_nunca_nu(self, base):
        # HARD: artigo vigente/vetado cujo texto e so o rotulo = extracao perdeu
        # o conteudo (mesma familia do bug CF88 Art. 7 XXVIII/XXIX de 2026-07-02).
        nus = _caputs_nus(_load(base), ('vigente', 'vetado'))
        assert not nus, (f"{LAWS[base][0]}: artigo vigente/vetado sem conteudo {nus[:5]}"
                         f" — extracao perdeu o texto")

    def test_revogado_nu_nao_cresce(self, base):
        n = len(_caputs_nus(_load(base), ('revogado',)))
        teto = _CAPUT_NU_TETO[base]
        assert n <= teto, (f"{LAWS[base][0]}: {n} revogados-nus > teto {teto} — nova perda"
                           f" de anotacao de revogacao na limpeza")
