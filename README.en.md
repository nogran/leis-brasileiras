# Leis Brasileiras — Brazilian legislation and jurisprudence in JSON with Python

[Português](README.md) · [Data format](docs/format.md) · [Validation](docs/validation.md) · [Transition plan](docs/transition.md) · [Licensing pending](docs/licensing.md)

**Leis Brasileiras** is a Python project for extracting and validating **15 Brazilian
federal legal instruments** from official Planalto sources and **six jurisprudence
sources from STJ, STF, TJPE and TJMG**. It produces JSON files
and a versioned Brazilian legal corpus with source URLs, capture dates and integrity
checks for legislation and case-law research and lookup. The project aims to provide an **MCP
server for structured lookup and text search in Brazilian legislation**, with
provision identifiers, official sources and a versioned corpus.

It is intended for legaltech developers, researchers and teams that need Brazilian
legislation and case law as structured data. Basic usage requires no database, Docker or OpenAI key.

**Project status:** legislative core and official jurisprudence integrated; the library and CLI include both.
No package or corpus release, hosted API or MCP server is available in this delivery.
Licensing is pending; see the [current licensing review](docs/licensing.md).

## Use cases: structured data and legal research

- **Brazilian legislation in JSON:** extract Planalto texts with provision identifiers,
  hierarchy, source URLs and observation dates.
- **Jurisprudence in JSON:** extract precedents and súmulas from supported courts,
  preserving the source, observed status and evidence for each capture.
- **Brazilian legal corpus for NLP:** prepare a reproducible reference for text analysis
  and experiments, retaining its coverage and date limitations.
- **Planned MCP access:** locate laws, retrieve identified articles and search words
  or phrases in an explicitly selected corpus revision.
- **Capture validation:** check format, hashes and integrity, including multipart
  articles, before integrating the data into another system.

## Planned MCP: structured lookup and text search

The Model Context Protocol (MCP) server will provide read-only access to the validated
corpus. **It is not implemented in this delivery.** The approved first-version scope is:

| Planned capability | Example request |
|---|---|
| Query the catalog by law identifiers | Which laws are available? Find Law 8.078/1990 |
| Retrieve an identified provision | Show article 18 of the Consumer Protection Code (CDC) |
| Search words or phrases, with filters and pagination | Search for “dados pessoais sensíveis” in the LGPD |
| Retrieve metadata and provenance | What are this text's source, observation date and revision? |

Each result must identify the law, the provision where applicable, the official source,
observation date and corpus revision. Missing coverage, ambiguous identities and
unsupported granularity must be explicit. Individual paragraph or clause lookup
requires dedicated extraction and identities, which are not available yet; the server
must not infer that structure.

Pagination limits the text returned per call; it does not define RAG chunks or overlap
in the corpus. Embeddings, vector search, size/token-based chunking and RAG strategies
are the responsibility of consumers, including the private Justina application.
The planned MCP provides text and metadata; the consuming AI application interprets
the question and generates the answer. Corpus extraction and update commands remain
separate from query tools.

## Supported Brazilian legislation and official sources

The catalog covers the instruments below, not all Brazilian law. This table is derived
from [`laws.yml`](src/leis_brasileiras/laws.yml), the catalog's source of truth. Official
Portuguese names and identifiers are preserved; links point to the Planalto pages used
by the extractor. The catalog includes the Constitution, Consumer Protection Code,
Labor Laws, Civil Code, Civil Procedure Code, Penal Code and General Data Protection
Law (LGPD).

| CLI code | Official Portuguese name | Legal identifier and Planalto source |
|---|---|---|
| `CF88` | Constituição Federal de 1988 | [Constituição Federal 1988](https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm) |
| `CDC` | Código de Defesa do Consumidor | [Lei 8.078/1990](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm) |
| `CLT` | Consolidação das Leis do Trabalho | [Decreto-Lei 5.452/1943](https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm) |
| `CC` | Código Civil | [Lei 10.406/2002](https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm) |
| `CPC` | Código de Processo Civil | [Lei 13.105/2015](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/L13105compilada.htm) |
| `CP` | Código Penal | [Decreto-Lei 2.848/1940](https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm) |
| `LGPD` | Lei Geral de Proteção de Dados | [Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm) |
| `ECA` | Estatuto da Criança e do Adolescente | [Lei 8.069/1990](https://www.planalto.gov.br/ccivil_03/leis/L8069Compilado.htm) |
| `LI` | Lei do Inquilinato | [Lei 8.245/1991](https://www.planalto.gov.br/ccivil_03/leis/L8245compilado.htm) |
| `LMP` | Lei Maria da Penha | [Lei 11.340/2006](https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm) |
| `LC123` | Estatuto Nacional da Microempresa e da Empresa de Pequeno Porte | [Lei Complementar 123/2006](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) |
| `LT` | Lei do Trabalho Temporário e Terceirização | [Lei 6.019/1974](https://www.planalto.gov.br/ccivil_03/leis/l6019compilado.htm) |
| `CADPOS` | Lei do Cadastro Positivo | [Lei 12.414/2011](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12414.htm) |
| `L9099` | Lei dos Juizados Especiais Cíveis e Criminais | [Lei 9.099/1995](https://www.planalto.gov.br/ccivil_03/leis/l9099.htm) |
| `LEP` | Lei de Execução Penal | [Lei 7.210/1984](https://www.planalto.gov.br/ccivil_03/leis/l7210compilado.htm) |

## Supported jurisprudence and official sources

The catalog covers six sources from four courts, not all Brazilian case law.
This table is derived from [`sources.json`](src/leis_brasileiras/jurisprudence/sources.json),
the catalog’s source of truth. Official Portuguese court names are preserved; links
point to endpoints and pages used by the extractors. The paginated STJ search link
opens the first page.

| CLI identifier | Court | Covered content | Official source |
|---|---|---|---|
| `stj_temas` | STJ — Superior Tribunal de Justiça | Repetitive themes, controversies, IAC, PUIL and SIRDR; includes records without a thesis | [Open data — precedents CSV](https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf/resource/df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv) |
| `stj_sumulas` | STJ — Superior Tribunal de Justiça | Súmulas, including cancelled entries | [SCON — súmula search](https://processo.stj.jus.br/SCON/pesquisar.jsp?livre=%40docn&b=SUMU&p=true&numDocsPagina=50&i=1) |
| `stf_teses_rg` | STF — Supremo Tribunal Federal | General repercussion: lists with and without a thesis | [Portal — general-repercussion theses](https://portal.stf.jus.br/repercussaogeral/retornartesesrepercussaogeral.asp) |
| `stf_sumulas_vinculantes` | STF — Supremo Tribunal Federal | Binding súmulas: index and statements | [Portal — binding súmulas](https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26) |
| `tjpe_sumulas` | TJPE — Tribunal de Justiça de Pernambuco | Súmulas from the court’s official books (PDF) | [Portal — súmula books](https://portal.tjpe.jus.br/servicos/consulta/sumulas) |
| `tjmg_sumulas` | TJMG — Tribunal de Justiça do Estado de Minas Gerais | Súmula statements in the court’s consolidated PDF | [Portal — súmula list](https://www.tjmg.jus.br/portal-tjmg/jurisprudencia/consulta-de-jurisprudencia/lista-de-sumulas.htm) |

The historical reference contains **4,631 records**, observed between July and August
2026; this total does not establish current coverage or legal validity. Each capture
preserves raw evidence, provenance and observed status. Individual judgments have
a validation contract but no bulk collection. PDFs require ClamAV or Windows Defender.

```bash
leis-brasileiras jurisprudence catalog
leis-brasileiras jurisprudence extract stj_temas --output corpus/jurisprudence
leis-brasileiras jurisprudence verify-capture "CAPTURE_PATH"
```

See [commands, formats, source observation dates and limitations](docs/jurisprudence.md).
The MCP server remains planned.

## Public formats

`observed-law-v1` is the library and CLI default. It reads preserved HTML and
identifies articles by law and component, including ADCT. Occurrences, markings,
official notes, tables and evidence references remain available. Ambiguous wording
is never silently selected; struck fragments remain retrievable.

`observed-jurisprudence-v1` retains original records, unknown fields, records without
holdings and repeated occurrences from all six sources. Both formats share
`source-observation-v1`, defining provenance, date precision and hash semantics.
Legal validity stays unknown; literal source mentions are not legal conclusions.

Public capture generation of `legacy-blocks-v1`, `canonical-v1` and
`jurisprudence-v1` is disabled. Historical files remain evidence. New exports contain
no synthetic tombstones or editorial legal annotations. This is a breaking change;
consumers need an adapter. See [formats](docs/format.md) and [transition](docs/transition.md).

Documents and diagnostic archives carry `complete=false`. Successful validation
establishes consistency and replay, not structural completeness or legal validity.

## Historical compatibility JSON example

Selected fields from an actual CDC record in the
[July 7, 2026 historical fixture](tests/fixtures/baseline/cdc_2026-07-07.json.gz).
A law's JSON contains a list of blocks; this object shows one block with additional
fields omitted for readability. Field names and statutory text remain in Portuguese.

```json
{
  "lei": "CDC",
  "artigo": "Art. 1",
  "texto_limpo": "Art. 1° O presente código estabelece normas de proteção e defesa do consumidor, de ordem pública e interesse social, nos termos dos arts. 5°, inciso XXXII, 170, inciso V, da Constituição Federal e art. 48 de suas Disposições Transitórias.",
  "url_fonte": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
  "data_extracao": "2026-07-07",
  "parte_num": null,
  "total_partes": null
}
```

`lei` and `artigo` identify the provision; `texto_limpo` contains extracted text;
`url_fonte` and `data_extracao` record its source and observation date. Null values in
`parte_num` and `total_partes` mean this block was not split. The example is historical
and does not establish current legal validity. See the [full data contract](docs/format.md).

## Quick start: extract Brazilian legislation

You need **Git and Python 3.14 or newer**. Installation downloads dependencies, and
fresh extraction accesses official sources over the internet. Basic usage does not
require PostgreSQL, Docker or an OpenAI key.

### 1. Get the code

The legislation and jurisprudence library and CLI are on the `main` branch:

```bash
git clone --branch main https://github.com/nogran/leis-brasileiras.git
cd leis-brasileiras
```

If you already have the repository locally, enter the existing directory and update the `main` branch (`git pull`).

### 2. Create the environment and install

**Windows (PowerShell):** these commands use the environment directly, without shell
activation scripts.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock .
.\.venv\Scripts\leis-brasileiras.exe catalog
```

**Linux/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock .
leis-brasileiras catalog
```

`catalog` lists supported law codes and their sources. In the following examples,
PowerShell users should replace `leis-brasileiras` with
`.\.venv\Scripts\leis-brasileiras.exe` and `python` with `.\.venv\Scripts\python.exe`.
On Linux/macOS, keep the environment activated. The lock file pins verified dependency
versions; `pyproject.toml` declares compatible ranges.

### 3. Extract a law

Start with the Consumer Protection Code (`CDC`):

```bash
leis-brasileiras extract CDC --format observed-law-v1 --output corpus/captures
```

A successful result includes `law`, `capture` (the newly created directory) and
`status: "validated"`. The directory contains `canonical.json`, `clean.txt`,
`source.html` and `manifest.json` with provenance and hashes. Struck markings remain on evidence fragments linked to occurrences.
The manifest exposes `complete=false`.
These files are stored locally.

To extract every law in the catalog:

```bash
leis-brasileiras extract ALL --force --format observed-law-v1 --output corpus/captures
```

### 4. Check the capture

Replace `PATH_TO_CAPTURE` with the `capture` value from the extraction output. Use that
specific capture directory, not the parent `corpus/captures` directory:

```bash
leis-brasileiras verify-capture "PATH_TO_CAPTURE"
leis-brasileiras validate "PATH_TO_CAPTURE" --format observed-law-v1
```

`verify-capture` checks the complete capture, including hashes and reproduction from
HTML; `validate --format observed-law-v1` checks document identities, relationships,
readings and revisions. `integrity` only handles the historical format. Discover options with:

```bash
leis-brasileiras --help
leis-brasileiras extract --help
```

Every capture records its source, observation timestamp, parser/package versions and
SHA-256 checksums. Each run creates a fresh capture; `--force` makes that intent explicit.
Existing captures are never overwritten. Extraction fails if any
selected law cannot be downloaded, parsed or validated. Raw HTML is untrusted data;
scripts and browser actions are never executed. Failed captures cannot enter a validated
release. No silent fallback substitutes historical text for a fresh fetch.

### Use from Python

```python
from pathlib import Path
from leis_brasileiras.capture import extract_html

result = extract_html(Path("official-source.html").read_bytes(), "CDC",
                      "2026-07-07T12:00:00-03:00",  # actual observation time
                      format="observed-law-v1")
print(result.canonical["units"][0]["id"])
```

`extract_html` performs no network access or persistence. It returns the document in
`result.canonical`, a source-order transcript and original HTML. `write_capture` is the filesystem adapter; a database
integration can consume the same result without duplicating the parser. Application
database IDs are not part of the public corpus.

## Versioned Brazilian legal corpus

Build a new local release by passing **one validated capture per law explicitly**:

```bash
leis-brasileiras bundle PATH_CF88 PATH_CDC OTHER_13_CAPTURES --version 2026-10-26.1 --output dist/corpus.zip
```

A subset requires an explicit selection, recorded in the manifest:

```bash
leis-brasileiras bundle PATH_CDC --laws CDC --version 2026-10-27.1 --output dist/cdc.zip
```

Do not mix formats in the same corpus.

To try the historical reference **without accessing external sources after
installation**, use the legislative fixtures included in this repository:

```bash
python -m tools.build_reference --format observed-law-v1 --version reference-2026-08 --output dist/reference.zip
```

The result is `dist/reference.zip`, containing historical reference data rather than a
fresh extraction. The destination must be new; choose another ZIP name for a repeat run.

Archives include a manifest, SHA-256 hashes, sources, dates and package/parser versions.
The historical reference records date precision and missing raw HTML for L9099. Large
corpora should be attached to releases only after publication approval; these commands
**do not publish** anything. Do not copy private data directories into the repository.

## Quality, updates and limitations

<!-- article-inventory:start -->

Diagnostic counts from historical captures. **No law has certified structural completeness.**

Articles count one identity per component; occurrences include repeats and observed wording. The independent HTML census finds candidates; it does not establish validity or prove every boundary.

| Law | Observation | HTML candidates | Structured articles | Occurrences | Discrepancies |
|---|---|---:|---:|---:|---:|
| CF88 | 2026-07-07 | 424 | 424 | 514 | 2 |
| CDC | 2026-07-07 | 130 | 130 | 130 | 2 |
| CLT | 2026-07-07 | 1022 | 1022 | 1029 | 2 |
| CC | 2026-07-07 | 2083 | 2083 | 2083 | 2 |
| CPC | 2026-07-07 | 1073 | 1073 | 1073 | 2 |
| CP | 2026-07-07 | 422 | 432 | 434 | 3 |
| LGPD | 2026-07-07 | 79 | 79 | 80 | 2 |
| ECA | 2026-07-07 | 324 | 324 | 325 | 2 |
| LI | 2026-07-07 | 91 | 91 | 91 | 2 |
| LMP | 2026-07-07 | 57 | 57 | 60 | 3 |
| LC123 | 2026-07-07 | 132 | 132 | 158 | 2 |
| LT | 2026-07-07 | 23 | 23 | 30 | 2 |
| CADPOS | 2026-07-07 | 19 | 19 | 25 | 2 |
| L9099 | 2026-07-13 | — | 99 | 99 | 3 |
| LEP | 2026-08-18 | 218 | 218 | 219 | 2 |

L9099 has no historical HTML in this reference. A new capture cannot recreate that evidence. Retrieval parts are not articles or readings; the new corpus does not generate overlapping parts.

[Inventory summary / Resumo](docs/source-inventory.json) · [Full report / Relatório completo](docs/validation.md#reprodução)

<!-- article-inventory:end -->

- **Provenance:** manifests record sources, dates, parser versions and hashes.
  Fresh captures and historical references are separate distributions.
- **Updates:** a fresh extraction accesses Planalto; there are no automatic updates.
  A current capture of all 15 instruments remains pending because of connection
  failures recorded in the [validation report](docs/validation.md). Offline tests
  do not establish current access to the sources.
- **Historical coverage:** 14 instruments have raw HTML fixtures; L9099 has cleaned
  text and JSON. Struck-out fragments retain their evidence links and are not a complete amendment
  or legal-validity history.
- **Multipart compatibility:** in the historical format, preserve identifiers and account for overlap when assembling
  text; concatenating parts directly repeats passages. See [format and limits](docs/format.md).
- **Validation meaning:** `validated` describes technical checks on a capture.
  Capture date, parser-observed status and legal effective date are distinct concepts.
  The data does not replace checking official publications.

## Frequently asked questions

### Can I download a ready-made Brazilian laws dataset?

No corpus release has been published yet. After installation, generate a historical
ZIP locally with `tools/build_reference.py` as shown above, or prepare a corpus from
fresh validated captures.

### Do I need OpenAI, PostgreSQL or Docker?

No. The core requires Python 3.14+ and its declared dependencies. Installation downloads
dependencies; fresh extraction requires access to official sources. Historical
reference builds work offline after installation.

### Is there a Brazilian legislation API or MCP server?

This delivery provides a Python library and CLI. It does not provide a hosted HTTP API
or Model Context Protocol (MCP) server. The read-only structured lookup and text
search described above are planned in the
[proposed MCP contract](docs/mcp-contract.md); it is not implemented yet.

### Can I use the corpus in an AI application?

Yes. The project supplies legislative data; each consumer defines its application,
including RAG strategies, embeddings and chunks when needed. Preserve identities,
sources and dates, and follow the consumed format conventions, including parts in
the historical contract. Treat retrieved text as untrusted data, never as system
instructions. See [security](docs/security-and-resilience.md) and resolve licensing
before adopting or redistributing code and original dataset elements.

### What is the license?

Licensing is pending the owner's decision. Public repository access does not grant
a license to the code or original dataset elements. See the
[licensing review](docs/licensing.md).

## Relationship with Justina

**Justina** is an AI assistant for consulting Brazilian legislation through WhatsApp.
Visit **[www.justina.com.br](https://www.justina.com.br)**.

**Leis Brasileiras** grew out of that extraction work. This repository contains the
public legislative core, independent of Justina's RAG policies and infrastructure.
Adapting the private repositories will be a later step after this public core is
complete. See the [transition roadmap](docs/transition.md).

## Tests and contributions

```bash
python -m pip install -r requirements-dev.lock .
python -m pytest -q --cov=leis_brasileiras
python -m tools.build_inventory --check
python -m tools.build_reference --version test-reference --output dist/test-reference.zip
python -m tools.build_reference --format observed-law-v1 --version test-reference --output dist/test-canonical.zip
python -m build
```

The suite preserves all 15 historical references and reconciles candidates in the 14 available
sources, and tests numbering, overlap, duplicates and part sizes. Abuse tests cover
external URLs, exfiltration attempts, active content, malicious instructions treated
as text, malformed input, volume and capture isolation. Tests make no paid calls and
do not access a database.

To contribute, describe the problem or improvement in an
[issue](https://github.com/nogran/leis-brasileiras/issues), including the law, source
and reproduction steps. Extraction changes should preserve identifiers and include
a relevant regression test. Do not submit personal data, credentials or private
system captures.

## Origin and transition

Derived from the Justina legislative pipeline core. The selected history preserves
human authors, dates and attribution; message bodies with private context were omitted.
See the [history review](docs/history-review.json) and [integration plan](docs/transition.md).
This delivery does not change private repositories or complete Justina's migration.
