# Brazilian Laws — Leis Brasileiras

[Português](README.md) · [Data format](docs/format.md) · [Transition plan](docs/transition.md)

Python extraction, catalog and validation of Brazilian legislation from official
sources. Basic usage needs neither a database nor an OpenAI key. This extraction core
is under review; no package, dataset release or MCP server has been published.

The catalog supports 15 federal laws. The historical reference contains 6,276 blocks,
including preambles, annexes and signatures, observed in July/August 2026. It contains
24 multipart provisions split into 54 chunks. It does **not** cover all Brazilian law
or determine present legal validity. [Measured inventory](docs/source-inventory.json).

## Install and use

Python 3.14+. From the repository checkout:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock .
leis-brasileiras catalog
leis-brasileiras extract ALL --force --output corpus/captures
leis-brasileiras verify-capture PATH_TO_CAPTURE
leis-brasileiras validate DIRECTORY_WITH_ARTICLE_JSONS --strict
leis-brasileiras integrity DIRECTORY_WITH_ARTICLE_JSONS
```

Every capture records its source, observation timestamp, parser/package versions and
SHA-256 checksums. Existing captures are never overwritten. Extraction fails if any
selected law cannot be downloaded, parsed or validated. Raw HTML is untrusted data;
scripts and browser actions are never executed. Failed captures cannot enter a validated
release. No silent fallback substitutes historical text for a fresh fetch.

```python
from pathlib import Path
from leis_brasileiras.capture import extract_html

result = extract_html(Path("official-source.html").read_bytes(), "CDC",
                      "2026-07-07T12:00:00-03:00")  # actual observation time
print(result.articles[0]["artigo"])
```

The pure parser returns articles, cleaned text and archived prior redactions. Application
database IDs are not part of the public corpus. Prepare a local reference archive:

```bash
python tools/build_reference.py --version reference-2026-08 --output dist/reference.zip
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
includes the reviewed history and preserves the existing destination commits. The PR
remains a draft. Next stages are a pinned-version private adapter, compatibility checks
and then a read-only MCP interface over the same validated corpus.
