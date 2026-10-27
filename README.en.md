# Brazilian Laws — Leis Brasileiras

[Português](README.md) · [Data format](docs/format.md) · [Transition plan](docs/transition.md)

Python extraction, catalog and validation of Brazilian legislation from official
sources. Basic usage needs neither a database nor an OpenAI key. This extraction core
is under review; no package, dataset release or MCP server has been published.

The catalog supports 15 federal laws. The historical reference contains 6,276 blocks,
including preambles, annexes and signatures, observed in July/August 2026. It contains
24 multipart provisions split into 54 chunks. It does **not** cover all Brazilian law
or determine present legal validity. [Measured inventory](docs/source-inventory.json).

## Relationship with Justina

**Justina** is an AI assistant for consulting Brazilian legislation through WhatsApp.
Visit **[www.justina.com.br](https://www.justina.com.br)**.

Its knowledge base is built from legislative texts extracted from official sources,
organized and validated by its data pipeline. When a question arrives, Justina retrieves
relevant passages from that base to ground its answer, using retrieval-augmented
generation (RAG).

**Leis Brasileiras** grew out of that extraction work. This repository contains the
extraction and validation core and tools to build a versioned corpus with source and
capture-date provenance. Justina's integration with this package is in transition;
the original extractor remains active. See the [integration plan](docs/transition.md).

## Run locally

You need **Git and Python 3.14 or newer**. Installation downloads dependencies, and
fresh extraction accesses official sources over the internet. Basic usage does not
require PostgreSQL, Docker or an OpenAI key.

### 1. Get the code

The core described here is on the `codex/extraction-core` review branch:

```bash
git clone --branch codex/extraction-core https://github.com/nogran/leis-brasileiras.git
cd leis-brasileiras
```

If you already have this branch locally, enter the existing directory.

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
leis-brasileiras extract CDC --output corpus/captures
```

A successful result includes `law`, `capture` (the newly created directory) and
`status: "validated"`. The directory contains article JSON, cleaned text, a separate
prior-redactions file, source HTML and `manifest.json` with provenance and hashes.
These files are stored locally.

To extract every law in the catalog:

```bash
leis-brasileiras extract ALL --force --output corpus/captures
```

### 4. Check the capture

Replace `PATH_TO_CAPTURE` with the `capture` value from the extraction output. Use that
specific capture directory, not the parent `corpus/captures` directory:

```bash
leis-brasileiras verify-capture "PATH_TO_CAPTURE"
leis-brasileiras validate "PATH_TO_CAPTURE" --strict
leis-brasileiras integrity "PATH_TO_CAPTURE"
```

`verify-capture` checks the complete capture, including hashes and reproduction from
HTML; `validate` checks article JSONs; `integrity` checks data integrity, including
multipart articles. Discover options with:

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
                      "2026-07-07T12:00:00-03:00")  # actual observation time
print(result.articles[0]["artigo"])
```

The pure parser returns articles, cleaned text and archived prior redactions. Application
database IDs are not part of the public corpus.

## Try the historical corpus offline

After installation, build a reference archive without accessing external sources,
using the legislative fixtures included in this repository:

```bash
python tools/build_reference.py --version reference-2026-08 --output dist/reference.zip
```

The result is `dist/reference.zip`, containing historical reference data rather than a
fresh extraction. The destination must be new; choose another ZIP name for a repeat run.

## Tests

```bash
python -m pip install -r requirements-dev.lock .
python -m pytest -q --cov=leis_brasileiras
python -m build
```

The reference builder validates all 15 frozen article snapshots. Fourteen laws also
have raw HTML fixtures; L9099 currently has only cleaned text and structured output.
Historical dates have day precision. Capture date, observed text and legal effective
date are separate concepts. Struck-out text is not a complete amendment history.

Licensing is **pending**: Apache-2.0 was proposed but has not been granted. Statutory
texts are distinct from original software and dataset organization; no ownership over
the laws is claimed. See [licensing review](docs/licensing.md).

The original Justina extractor remains in use during transition. The proposal branch
includes the reviewed history and preserves the existing destination commits. See
[PR #1](https://github.com/nogran/leis-brasileiras/pull/1) for the current review status.
Next stages are a pinned-version private adapter, compatibility checks
and then a read-only MCP interface over the same validated corpus.
