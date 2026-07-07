# -*- coding: utf-8 -*-
"""Integridade dos artigos MULTI-PARTE na extração mais recente de cada lei.

Nasceu do incidente 2026-07-08 (auditoria pós-"finalizado"): o completeness golden
prova que NADA SE PERDE, mas não provava que nada é servido ERRADO — o ANEXO da CLT
tinha 35 partes-fantasma (janela do split degenerada, chunks de até 1 char) e o
LC123 Art. 18 servia fragmento de redação VELHA como vigente (dedup por-parte
depois do split deixava escapar par duplicado que caísse em partes diferentes).

Invariantes (qualquer extração futura que os viole FALHA a suíte):
  D1  nenhum par de chunks com texto idêntico
  D2  nenhuma fatia deslizante (parte i+1 = parte i deslocada por poucos chars)
  D4  numeração de partes completa e consistente (1..N, N único, sem repetição)
  D5  partes consecutivas se ENCADEIAM (o início da parte i+1 existe no fim da
      parte i — o overlap do split é íntegro; como o dedup roda ANTES do split,
      nada edita as partes depois do corte)
  D6  nenhuma parte minúscula (fatia inútil)

Ratchet: roda só na extração MAIS RECENTE de cada lei — snapshots históricos
congelados (04-08, 07-02, 07-06) contêm os bugs da época por design.
"""
import json
import os
import re
import sys
import unicodedata
from glob import glob

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validar_leis import arquivos_mais_recentes
from verificar_integridade import eh_arquivo_de_lei

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PART_RE = re.compile(r"^(.*?)\s*\(Parte (\d+)/(\d+)\)\s*$")

MIN_PARTE_CHARS = 100        # D6: fatia menor que isso é inútil no RAG
JANELA_DESLIZANTE_MAX = 12   # D2: deslocamentos de 1..12 chars = janela degenerada


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip()


def _arquivos_atuais():
    files = [f for f in glob(os.path.join(DATA_DIR, "*.json"))
             if eh_arquivo_de_lei(os.path.basename(f))]
    return sorted(arquivos_mais_recentes(files))


def _carregar(fp):
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("fp", _arquivos_atuais(),
                         ids=lambda p: os.path.basename(p))
class TestMultipartIntegrity:

    def test_d1_sem_chunks_de_texto_identico(self, fp):
        vistos = {}
        for c in _carregar(fp):
            n = _norm(c["texto_limpo"])
            if len(n) <= 40:
                continue
            assert n not in vistos, \
                f"{c['artigo']} tem texto idêntico a {vistos[n]}"
            vistos[n] = c["artigo"]

    def test_d2_sem_fatia_deslizante(self, fp):
        partes = {}
        for c in _carregar(fp):
            m = PART_RE.match(c["artigo"])
            if m:
                partes.setdefault(m.group(1), {})[int(m.group(2))] = _norm(c["texto_limpo"])
        for base, ps in partes.items():
            plist = sorted(ps.items())
            for (i, a), (j, b) in zip(plist, plist[1:]):
                w = min(120, len(a) - JANELA_DESLIZANTE_MAX, len(b))
                if w <= 40:
                    continue
                for off in range(1, JANELA_DESLIZANTE_MAX + 1):
                    assert a[off:off + w] != b[:w], \
                        f"{base}: Parte {j} = Parte {i} deslocada {off} chars (janela degenerada)"

    def test_d4_numeracao_de_partes_completa(self, fp):
        partes = {}
        for c in _carregar(fp):
            m = PART_RE.match(c["artigo"])
            if m:
                base, i, n = m.group(1), int(m.group(2)), int(m.group(3))
                partes.setdefault(base, []).append((i, n))
        for base, lst in partes.items():
            ns = {n for _, n in lst}
            assert len(ns) == 1, f"{base}: totais divergentes {sorted(ns)}"
            n = ns.pop()
            idx = sorted(i for i, _ in lst)
            assert idx == list(range(1, n + 1)), \
                f"{base}: partes {idx} não cobrem 1..{n}"

    def test_d5_partes_se_encadeiam_pelo_overlap(self, fp):
        partes = {}
        for c in _carregar(fp):
            m = PART_RE.match(c["artigo"])
            if m:
                partes.setdefault(m.group(1), {})[int(m.group(2))] = _norm(c["texto_limpo"])
        for base, ps in partes.items():
            plist = sorted(ps.items())
            for (i, a), (j, b) in zip(plist, plist[1:]):
                if len(b) <= 60 or len(a) <= 60:
                    continue
                assert b[:60] in a, \
                    f"{base}: Parte {j} não continua a Parte {i} — overlap quebrado " \
                    f"(algo editou as partes DEPOIS do split?)"

    def test_d6_sem_parte_minuscula(self, fp):
        for c in _carregar(fp):
            m = PART_RE.match(c["artigo"])
            if m:
                n = _norm(c["texto_limpo"])
                assert len(n) >= MIN_PARTE_CHARS, \
                    f"{c['artigo']}: fatia inútil de {len(n)} chars: {n[:80]!r}"
