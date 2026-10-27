"""Frozen legacy segmentation; not the public legislative identity or validation policy."""
import re

LEGACY_FORMAT = "legacy-blocks-v1"


def split_com_overlap(texto: str, max_chars: int = 6000, overlap_chars: int = 400) -> list[str]:
    if len(texto) <= max_chars:
        return [texto]
    # 2026-07-08 (2ª rodada do ANEXO da CLT): cortar num '\n' que esta perto demais
    # do INICIO da janela produz fatia inutil (a parte 1 ficou com 30 chars, 'ANEXO
    # Quadro a que se refere o'). '\n' util e perto do FIM; senao, corta em ESPACO —
    # nunca no meio de palavra.
    min_parte = max(overlap_chars * 2, 800)
    partes, inicio = [], 0
    while inicio < len(texto):
        fim = inicio + max_chars
        if fim >= len(texto):
            partes.append(texto[inicio:].strip())
            break
        corte = texto.rfind('\n', inicio, fim)
        if corte - inicio < min_parte:
            corte_espaco = texto.rfind(' ', inicio, fim)
            if corte_espaco - inicio > corte - inicio:
                corte = corte_espaco
        if corte <= inicio:
            corte = fim
        partes.append(texto[inicio:corte].strip())
        # 2026-07-08: overlap so quando ha avanco real. Quando o unico '\n' fica
        # perto do INICIO, `corte - overlap` recuava e a janela avancava 1 char por
        # iteracao — 30 partes-fantasma deslizantes ('ANEXO Quadro...' perdendo uma
        # letra por parte) no ANEXO da CLT. Sem avanco: pula direto pro corte.
        proximo = corte - overlap_chars
        inicio = proximo if proximo > inicio else corte + 1
    return [p for p in partes if p]


def parse_legacy(clean_text, law, version, source_url, observed_date, config):
    """Compatibility facade over the shared parser, preserving the historical payload."""
    from .extraction import parse_law

    return parse_law(clean_text, law, version, source_url, observed_date, config)


def measure_records(records: list[dict]) -> dict:
    """Count records and multipart groups by kind, without claiming canonical coverage."""
    parts = [record for record in records if record.get("parte_num") is not None]
    groups = {re.sub(r" \(Parte \d+/\d+\)$", "", record["artigo"]) for record in parts}
    return {"records": len(records),
            "article_records": sum(record["artigo"].startswith("Art.") for record in records),
            "other_records": sum(not record["artigo"].startswith("Art.") for record in records),
            "multipart_records": len(parts), "multipart_units": len(groups),
            "multipart_articles": sum(label.startswith("Art.") for label in groups),
            "multipart_other_units": sum(not label.startswith("Art.") for label in groups)}
