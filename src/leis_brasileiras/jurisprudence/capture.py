"""Atomic capture directories and exact replay of bounded official-source responses."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import tempfile

from bs4 import BeautifulSoup

from . import extraction as parser
from .catalog import source
from .models import MAX_BYTES, MAX_TOTAL_BYTES, MAX_FILES, digest, document, json_bytes
from .pdf import extract_pages
from .transport import SourceClient, secure_pdf_url, validate_url
from .validation import load_json, validate_document

MAX_PDF_TEXT_BYTES = 32 * 1024 * 1024


class Batch:
    """Collect or replay the same request sequence without arbitrary file/URL resolution."""

    def __init__(self, identifier, client=None, replay=None):
        self.identifier = identifier
        self.client = client
        self.replay = replay
        self.items = []
        self.total = 0

    def get(self, url, kind, form=None):
        validate_url(self.identifier, url, kind)
        index = len(self.items)
        if index >= MAX_FILES:
            raise ValueError("Capture file limit exceeded")
        name = f"raw/{index:03d}.{kind}"
        request = {"name": name, "url": url, "kind": kind, "form": form}
        if self.replay is not None:
            if index >= len(self.replay):
                raise ValueError("Missing raw response")
            saved, raw = self.replay[index]
            if any(saved.get(key) != value for key, value in request.items()):
                raise ValueError("Raw response does not match the expected source request")
        else:
            raw = self.client.fetch(url, kind, form)
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
            raise ValueError("Invalid raw response size")
        self.total += len(raw)
        if self.total > MAX_TOTAL_BYTES:
            raise ValueError("Capture byte limit exceeded")
        self.items.append(({**request, "sha256": digest(raw), "bytes": len(raw)}, raw))
        return raw


def parse_batch(batch: Batch, observed_at: str, scanner=None, *, sample=False):
    identifier = batch.identifier
    url = source(identifier)["official_url"]
    day = observed_at[:10]
    decode = lambda raw: parser.decodificar_bytes(raw)[0]
    records = []
    if identifier == "stj_temas":
        records = parser.parse_temas_csv(decode(batch.get(url, "csv")), day)
        records = parser.colapsar_por_chave_natural(records, day)
    elif identifier == "stj_sumulas":
        for offset in range(1, 1502, 50):
            address = url.format(i=offset)
            page = parser.parse_stj_sumulas_html(decode(batch.get(address, "html")), day,
                                                url_fonte=address)
            records.extend(page)
            if len(page) < 50:
                break
        else:
            raise ValueError("SCON pagination did not terminate")
    elif identifier == "stf_teses_rg":
        texts = [decode(batch.get(url, "json", form)) for form in ("com", "sem")]
        records = parser.parse_stf_teses_json(*texts, day)
        if not sample and (sum(r["lista_origem"] == "com" for r in records) < 700
                           or sum(r["lista_origem"] == "sem" for r in records) < 400):
            raise ValueError("STF thesis lists appear incomplete")
    elif identifier == "stf_sumulas_vinculantes":
        index = decode(batch.get(url, "html"))
        # Cancellation is tied to this indexed entry, never a keyword elsewhere on the page.
        labels = {}
        for link in BeautifulSoup(index, "html.parser").find_all("a", href=True):
            match = parser._RE_SV_LINK.search(link["href"])
            if match:
                labels.setdefault(match.group(1), []).append(link.get_text(" ").replace("\u200b", ""))
        for identity in parser.parse_stf_sv_lista(index):
            address = f"{url}&sumula={identity}"
            record = parser.parse_stf_sv_detalhe(decode(batch.get(address, "html")), address, day, identity)
            indexed_numbers = {match.group(1) for label in labels.get(identity, [])
                               if (match := parser._RE_SV_TITULO.search(label))}
            if indexed_numbers != {record["numero"]}:
                raise ValueError("STF index identity does not match the detail page")
            if any(re.search(r"cancelad", label, re.I) for label in labels.get(identity, [])):
                record["situacao"] = "cancelada"
                content = {k: v for k, v in record.items() if k not in {"hash", "extracted_at"}}
                record = parser._finalizar_registro(content, day)
            records.append(record)
    else:
        index = decode(batch.get(url, "html"))
        links = (parser.livros_tjpe_do_indice(index) if identifier == "tjpe_sumulas"
                 else [parser.consolidado_tjmg_do_indice(index)])
        text_bytes = 0
        for label, address in links:
            address = secure_pdf_url(identifier, address)
            pages = extract_pages(batch.get(address, "pdf"), scanner)
            text_bytes += sum(len(page.encode("utf-8")) for page in pages)
            if text_bytes > MAX_PDF_TEXT_BYTES:
                raise ValueError("PDF batch text limit exceeded")
            text = "\n".join(pages)
            if identifier == "tjpe_sumulas":
                records.extend(parser.parse_tjpe_sumulas_pdf(text, day, address, parser._slug_de_livro(label)))
            else:
                records.extend(parser.parse_tjmg_sumulas_pdf(text, day, address))
        if not sample:
            court = "TJPE" if identifier == "tjpe_sumulas" else "TJMG"
            parser._validar_corpus_estadual(records, court, 160 if court == "TJPE" else 80,
                                           172 if court == "TJPE" else 89)
    if batch.replay is not None and len(batch.items) != len(batch.replay):
        raise ValueError("Unexpected extra raw responses")
    if not sample:
        minimum = source(identifier)["historical_minimum_total"]
        if len(records) < minimum:
            raise ValueError("Source fell below historical coverage; review evidence before changing catalog")
    result = document(identifier, records, observed_at, "sample" if sample else "source_snapshot")
    validate_document(result)
    return result


def capture(identifier: str, output: Path, *, scanner=None, ca_bundle=None) -> Path:
    observed = datetime.now(timezone.utc).isoformat()
    batch = Batch(identifier, SourceClient(identifier, ca_bundle))
    result = parse_batch(batch, observed, scanner)
    return write_capture(result, batch.items, output)


def write_capture(result: dict, items: list, output: Path) -> Path:
    validate_document(result)
    raw_document = json_bytes(result)
    manifest = {"format": "jurisprudence-capture-v1", "source": result["source"],
                "observed_at": result["observed_at"], "coverage": result["coverage"],
                "document_sha256": digest(raw_document), "files": [entry for entry, raw in items]}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{result['source']}-{digest(json_bytes(manifest))[:20]}"
    if target.exists():
        raise FileExistsError("Capture already exists; it will not be overwritten")
    temporary = Path(tempfile.mkdtemp(prefix=".juris-", dir=output))
    try:
        (temporary / "raw").mkdir()
        for index, (entry, raw) in enumerate(items):
            if entry["name"] != f"raw/{index:03d}.{entry['kind']}" or entry["kind"] not in {"csv", "html", "json", "pdf"}:
                raise ValueError("Invalid raw artifact name")
            (temporary / entry["name"]).write_bytes(raw)
        (temporary / "document.json").write_bytes(raw_document)
        (temporary / "capture.json").write_bytes(json_bytes(manifest))
        temporary.rename(target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target


def verify_capture(folder: Path, *, scanner=None) -> dict:
    folder = Path(folder)
    if folder.is_symlink() or (folder / "raw").is_symlink():
        raise ValueError("Symlink capture refused")
    manifest = load_json(folder / "capture.json")
    expected_keys = {"format", "source", "observed_at", "coverage", "document_sha256", "files"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys or manifest["format"] != "jurisprudence-capture-v1":
        raise ValueError("Unsupported capture manifest")
    entries = manifest["files"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
        raise ValueError("Invalid raw artifact count")
    replay, total = [], 0
    expected_files = {"capture.json", "document.json"}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"name", "url", "kind", "form", "sha256", "bytes"}:
            raise ValueError("Invalid raw descriptor")
        if entry["kind"] not in {"csv", "html", "json", "pdf"} or entry["name"] != f"raw/{index:03d}.{entry['kind']}":
            raise ValueError("Unsafe raw artifact path")
        path = folder / entry["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid raw file")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        total += len(raw)
        if total > MAX_TOTAL_BYTES or len(raw) != entry["bytes"] or digest(raw) != entry["sha256"]:
            raise ValueError("Raw integrity mismatch")
        expected_files.add(entry["name"])
        replay.append((entry, raw))
    actual = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}
    if actual != expected_files:
        raise ValueError("Unexpected capture files")
    value = load_json(folder / "document.json")
    validate_document(value)
    if digest((folder / "document.json").read_bytes()) != manifest["document_sha256"]:
        raise ValueError("Document integrity mismatch")
    for key in ("source", "observed_at", "coverage"):
        if value[key] != manifest[key]:
            raise ValueError("Capture metadata mismatch")
    replayed = parse_batch(Batch(manifest["source"], replay=replay), manifest["observed_at"], scanner,
                          sample=manifest["coverage"] == "sample")
    if replayed != value:
        raise ValueError("Source replay does not reproduce the document")
    return {**validate_document(value), "files": len(entries), "document_sha256": manifest["document_sha256"]}
