# Evidence-first corpus architecture

Official bytes -> bounded inert decoding/evidence map -> source-bound occurrences ->
independent reconciliation -> immutable capture/replay -> local diagnostic archive.

`source_map.py` records text and markup before any cleanup. `canonical.py` identifies
legislative units from that evidence. `reconciliation.py` independently enumerates
article candidates with stdlib HTMLParser; it does not import the segmenter.
`canonical_validation.py` checks bounded relationships, projections, seals and reports.
`capture.py` and `corpus.py` bind documents back to raw bytes through replay.

`jurisprudence/observed.py` projects original CSV/JSON/HTML/PDF evidence without the
historical parsers' default status, field filtering or deduplication. Acquisition
remains in `jurisprudence/capture.py`; its existing bounded source-policy helpers
only discover approved endpoints and records. PDF quarantine, antimalware and
isolated page extraction remain mandatory. Unknown fields and duplicate occurrences
are retained. The common `evidence.py` defines hashes and observation precision.

Historical extraction and validation modules remain for regression diagnostics.
They are not an alternate public export path. New captures never load editorial
curation, create tombstones, choose a current reading or join RAG parts.

## Boundaries and incomplete structure

Preservation of all decoded fragments is measurable independently of article counts.
A complete evidence map does not prove correct attachment of a footer, note or table
to a legal unit. Reconciliation therefore keeps structure incomplete and lists the
unresolved reviews. Article labels are candidates, not assertions of legal effect.

Consumers must distinguish source transcript, ambiguous reading, explicit source
statement and legal validity. The package does not determine validity. Capture-local
heading/annex paths are not guaranteed stable across page revisions. Full hierarchy,
subparagraph identity, CSS rendering and effective-date reasoning are not implemented.

The corpus has no database, embeddings, LLM, hosted API or MCP server dependency.
Retrieval/chunking and production migrations belong to consumers. See
[transition](transition.md) for concrete compatibility risks.

## Dependency and failure policy

No external dependency was added. Requests, BeautifulSoup4, PyYAML and pypdf remain
pinned through lock files. JSON Schema is a development check; runtime consistency
checks do not fetch schemas. Transport bounds, deadlines, TLS, allowlisted hosts,
PDF scanning and failure behavior are documented in
[security-and-resilience.md](security-and-resilience.md). Failed decoding, malformed
records, missing scanner or failed replay stop capture; no invented fallback text
is substituted. Reports retain incomplete evidence as incomplete.

References: [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/),
[pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
[PROV-DM](https://www.w3.org/TR/prov-dm/) and
[Akoma Ntoso vocabulary](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html).
These inform separation of source and interpretation; no compliance certification is claimed.
