# Public legislative corpus architecture

Leis Brasileiras is a public legislative data project with planned MCP access.
The Python library and CLI currently extract, validate and package official-source
observations. No MCP server, hosted API, search index or package release is delivered.
Consumers choose their own retrieval, storage and application policies.

## Data flow

Official HTML → bounded transport → shared HTML normalization and structural parser →
complete observed occurrences → canonical units OR historical compatibility export.

`extraction.py` emits complete occurrences before the historical size filter,
redaction deduplication, overlap and per-label winner selection. `canonical.py`
uses these occurrences; `compatibility.py` retains segmentation and the legacy facade.
There is one structural parser. Canonical parsing never reconstructs text by joining
historical parts. The historical export is not a conversion of the canonical JSON:
it is another projection of the shared parser and its preserved compatibility rules.

The canonical representation keeps source wording, cleaned text, observed metadata,
components, hierarchy and all duplicate readings. It does not silently choose the
longest reading. Curated corrections and assertions from `known_issues.json` appear
separately as editorial annotations pending evidence review. Synthetic tombstones
remain in the historical export only. HTML/CSS struck text is separately available;
heuristic dedup removals are not automatically classified as historical legal text.

## Boundaries

- Canonical corpus: law and unit identities, observed text, provenance and revisions.
- Compatibility export: historical Portuguese fields, IDs, labels, hashes and parts.
- Optional future search derivatives: segments/indexes linked to canonical revisions.
- Future MCP: bounded read-only projection over a validated corpus release.
- Consumer integrations: persistence, embeddings, ranking and business rules.

The 6,000/400 segmentation is a frozen compatibility profile, not a legal data model.
Canonical validation has no embedding-size threshold, token estimate or minimum
proportion of provisions classified as current. Historical retrieval diagnostics
remain an opt-in library function, outside capture/release acceptance.

## Implemented granularity and limitations

Articles and existing non-article units are addressable. Paragraphs, clauses,
subsections and tables are not universally parsed as nodes. Hierarchy is an ordered
path on each reading; the addressable parent is the main/ADCT/annex component.
Subsection text may remain embedded in a heading. `EMENTA` is conservatively typed
`preamble_or_summary`; the existing parser does not reliably distinguish every kind.

A repeated label within a component is an ambiguous unit with multiple readings,
not a merged text. This includes source structures the parser cannot yet distinguish
(e.g. enactment versus consolidated-text occurrences). Clients must not present
an ambiguous unit as a single authoritative text. Addressing finer components needs
source-specific evidence and tests; it is not inferred from text length.

Source metadata is observed, not legal advice or an effective-date determination.
Unresolved editorial assertions do not block publication of the observation as data,
but they cannot establish legal validity. `quality=ambiguous` explicitly limits use.

## Dependency resilience

Runtime dependencies remain Requests, BeautifulSoup4 and PyYAML. See
[security-and-resilience.md](security-and-resilience.md) for network limits and failures.
The standard-library canonical model has no database, LLM or remote-schema dependency.
JSON Schema validation uses jsonschema 4.26 in development/CI only, with locked
transitives; packaged schemas contain no remote references requiring network access.
If development dependencies cannot install, schema/build checks stay failed or pending;
no runtime fallback disables checks. They can be replaced without changing the corpus.

The planned MCP SDK will be introduced only with its own interoperability tests,
timeouts, concurrency bounds, observability and upgrade/rollback plan.
