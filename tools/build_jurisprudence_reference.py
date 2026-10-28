"""Reprocess an explicitly supplied historical raw archive; never contact a database.

The dated directory layout is documented in docs/jurisprudence.md. Raw archives are
inputs, not runtime dependencies of the package. PDFs use the normal antivirus gate.
"""
import argparse
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from leis_brasileiras.jurisprudence import extraction as parser
from leis_brasileiras.jurisprudence.capture import Batch, parse_batch, write_capture
from leis_brasileiras.jurisprudence.catalog import SOURCE_IDS
from leis_brasileiras.jurisprudence.corpus import build_release

HISTORICAL = {
    "stj_temas": ("stj-temas", "2026-07-20"),
    "stj_sumulas": ("stj-sumulas", "2026-07-21"),
    "stf_teses_rg": ("stf-teses", "2026-07-21"),
    "stf_sumulas_vinculantes": ("stf-sumulas-vinculantes", "2026-07-21"),
    "tjpe_sumulas": ("tjpe-sumulas", "2026-08-17"),
    "tjmg_sumulas": ("tjmg-sumulas", "2026-08-17"),
}


class HistoricalClient:
    def __init__(self, identifier, raw_root):
        self.identifier = identifier
        directory, self.observed_at = HISTORICAL[identifier]
        self.folder = Path(raw_root) / directory / self.observed_at

    def fetch(self, url, kind, form=None):
        identifier = self.identifier
        if identifier == "stj_temas":
            name = "jurisprudencia_stj_temas_2026-07-20_raw.csv"
        elif identifier == "stj_sumulas":
            offset = int(parse_qs(urlsplit(url).query)["i"][0])
            name = f"pagina_{offset:04d}.html"
        elif identifier == "stf_teses_rg":
            name = f"{form}.json"
        elif identifier == "stf_sumulas_vinculantes":
            identity = parse_qs(urlsplit(url).query).get("sumula", [None])[0]
            name = f"sumula_{identity}.html" if identity else "lista.html"
        elif kind == "html":
            name = "indice.html"
        elif identifier == "tjmg_sumulas":
            name = "sumulas.pdf"
        else:
            index = (self.folder / "indice.html").read_text(encoding="utf-8")
            links = parser.livros_tjpe_do_indice(index)
            names = ("livro_sumulas_tjpe_ate_92.pdf", "livro_sumulas_tjpe_de_93_a_109.pdf",
                     "livro_sumulas_tjpe_de_110_a_172.pdf")
            matches = [names[i] for i, (_, address) in enumerate(links) if address == url and i < len(names)]
            if len(matches) != 1:
                raise ValueError("Historical PDF mapping is ambiguous")
            name = matches[0]
        return (self.folder / name).read_bytes()


def main():
    argument = argparse.ArgumentParser(description=__doc__)
    argument.add_argument("--raw-root", type=Path, required=True)
    argument.add_argument("--output", type=Path, required=True)
    argument.add_argument("--version", required=True)
    argument.add_argument("--scanner", type=Path)
    args = argument.parse_args()
    captures = []
    for identifier in SOURCE_IDS:
        client = HistoricalClient(identifier, args.raw_root)
        batch = Batch(identifier, client)
        value = parse_batch(batch, client.observed_at, args.scanner)
        folder = write_capture(value, batch.items, args.output.parent / (args.output.stem + "-captures"))
        captures.append(folder)
        print(f"{identifier}: {len(value['records'])} historical records ({client.observed_at})", flush=True)
    print(build_release(captures, args.output, args.version, scanner=args.scanner))


if __name__ == "__main__":
    main()
