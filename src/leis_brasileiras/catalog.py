"""Load the packaged law catalog and derive identity views for extraction/validation.

Missing fields or duplicate codes/file prefixes fail at import time. Keep public
identities stable: downstream applications use these exact values as contract keys.
"""
import os

import yaml

_PATH = os.path.join(os.path.dirname(__file__), "laws.yml")

with open(_PATH, encoding="utf-8") as _f:
    _DOC = yaml.safe_load(_f)

LAWS = _DOC["laws"]  # list[dict] — ordem do yaml preservada

# --- guarda de integridade do catálogo (fail-fast no import) ---
_REQUIRED = ("sigla", "nome_base", "nome", "numero", "url")
_siglas_vistas: set[str] = set()
_bases_vistas: set[str] = set()
for _l in LAWS:
    _faltando = [k for k in _REQUIRED if not _l.get(k)]
    if _faltando:
        raise ValueError(
            f"laws.yml: entrada '{_l.get('sigla', '???')}' sem campos obrigatorios: {_faltando}")
    if _l["sigla"] in _siglas_vistas:
        raise ValueError(f"laws.yml: sigla duplicada: {_l['sigla']}")
    if _l["nome_base"] in _bases_vistas:
        raise ValueError(f"laws.yml: nome_base duplicado: {_l['nome_base']}")
    _siglas_vistas.add(_l["sigla"])
    _bases_vistas.add(_l["nome_base"])

# --- views derivadas (o que os consumidores importam) ---
SIGLAS = [l["sigla"] for l in LAWS]                                # ordem do yaml
SIGLA_PREFIXO = {l["sigla"]: l["nome_base"] for l in LAWS}         # sigla -> nome_base
NOME_BASE_PARA_SIGLA = {l["nome_base"]: l["sigla"] for l in LAWS}  # nome_base -> sigla (golden)
NOME = {l["sigla"]: l["nome"] for l in LAWS}                       # sigla -> nome canônico


def by_sigla(sigla: str) -> dict | None:
    """Entrada bruta do catálogo para a sigla (ou None se não existir)."""
    for l in LAWS:
        if l["sigla"] == sigla:
            return l
    return None
