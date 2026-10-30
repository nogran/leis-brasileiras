"""Reproducible diagnostics from captured sources, never a completeness claim."""
import argparse
import json
from pathlib import Path

from leis_brasileiras.catalog import LAWS
from tools.build_reference import reference

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- article-inventory:start -->"
END = "<!-- article-inventory:end -->"


def inventory():
    rows = []
    for law in LAWS:
        document, filename, raw = reference(law)
        report = document["reconciliation"]
        articles = [u for u in document["units"] if u["kind"] == "article"]
        components = {}
        for unit in articles:
            component = unit["locator"].split("/", 1)[0]
            components[component] = components.get(component, 0) + 1
        rows.append({"law": law["sigla"], "observation": document["provenance"]["observation"],
            "raw_sha256": document["provenance"]["raw_sha256"],
            "evidence_basis": document["provenance"]["basis"],
            "evidence_file": filename, "parser_version": document["provenance"]["parser_version"],
            "source_article_candidates": len(report["source_identities"]) if report["source_identities"] is not None else None,
            "structured_articles": len(articles), "articles_by_component": components,
            "observed_occurrences": sum(len(u["readings"]) for u in articles),
            "source_statement_mentions": sum(len(r["source_statements"]) for u in articles for r in u["readings"]),
            "unclassified_units": len(report["unclassified_units"]),
            "tables": sum(e["tag"] == "table" for e in document["evidence"]["elements"]),
            "text_fragments": len(document["evidence"]["texts"]),
            "blocks_or_parts": None, "complete": report["complete"],
            "reconciliation": report})
    return rows


def summarize_inventory(rows):
    """Keep actionable differences and the full reconciliation hash, not repeated lists."""
    exhaustive_lists = {"source_identities", "structured_identities", "source_occurrences"}
    return [{**row, "reconciliation": {
        **{key: value for key, value in row["reconciliation"].items() if key not in exhaustive_lists},
        "source_occurrence_count": (len(row["reconciliation"]["source_occurrences"])
                                    if row["reconciliation"]["source_occurrences"] is not None else None),
    }} for row in rows]


def readme_inventory(rows, language):
    pt = language == "pt"
    lines = [START, "",
        ("Contagens diagnósticas das capturas históricas. **Nenhuma norma tem completude estrutural certificada.**"
         if pt else "Diagnostic counts from historical captures. **No law has certified structural completeness.**"), "",
        ("Artigos contam uma identidade por componente; ocorrências incluem repetições e redações observadas. "
         "O censo independente encontra candidatos no HTML, não determina vigência nem prova todas as delimitações."
         if pt else "Articles count one identity per component; occurrences include repeats and observed wording. "
         "The independent HTML census finds candidates; it does not establish validity or prove every boundary."), "",
        ("| Lei | Observação | Candidatos no HTML | Artigos estruturados | Ocorrências | Divergências |"
         if pt else "| Law | Observation | HTML candidates | Structured articles | Occurrences | Discrepancies |"),
        "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        census = row["source_article_candidates"]
        lines.append(f"| {row['law']} | {row['observation']['value']} | {census if census is not None else '—'} | "
                     f"{row['structured_articles']} | {row['observed_occurrences']} | {len(row['reconciliation']['discrepancies'])} |")
    lines.extend(["",
        ("A L9099 tem HTML capturado em 2026-10-30. Esse arquivo não reescreve o texto derivado de 2026-07-13. "
         "Partes de recuperação não são artigos ou redações; o novo corpus não gera partes com overlap."
         if pt else "L9099 has HTML captured on 2026-10-30. That file does not rewrite the derived text from 2026-07-13. "
         "Retrieval parts are not articles or readings; the new corpus does not generate overlapping parts."),
        "", "[Inventory summary / Resumo](docs/source-inventory.json) · "
        "[Full report / Relatório completo](docs/validation.md#reprodução)", "", END])
    return "\n".join(lines)


def replace_readme_inventory(text, block):
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) >= text.index(END):
        raise ValueError("Expected exactly one bounded article inventory section")
    return text[:text.index(START)] + block + text[text.index(END) + len(END):]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path, help="Write the full diagnostic report (normally under dist/)")
    args = parser.parse_args(argv)
    rows = inventory()
    outputs = {ROOT / "docs/source-inventory.json": json.dumps(summarize_inventory(rows), ensure_ascii=False, indent=2) + "\n"}
    for name, language in (("README.md", "pt"), ("README.en.md", "en")):
        path = ROOT / name
        outputs[path] = replace_readme_inventory(path.read_text(encoding="utf-8"), readme_inventory(rows, language))
    if args.report:
        if args.report.resolve() in {path.resolve() for path in outputs}:
            parser.error("Report destination must not replace the versioned summary or READMEs")
        report = {"kind": "source-fidelity-report", "format_version": 1,
                  "complete": all(row["complete"] for row in rows), "laws": rows}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.check:
        return 0 if all(path.read_text(encoding="utf-8") == text for path, text in outputs.items()) else 1
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
