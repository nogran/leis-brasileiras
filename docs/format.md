# Data contracts, provenance and limits

Two explicit representations are available. Use `--format canonical-v1` for the public
legislative model. Existing Python/CLI calls default to `legacy-blocks-v1` to preserve
compatibility; the historical format is not the canonical MCP response contract.
Schemas ship inside `leis_brasileiras/schemas/`.

## Canonical document (`canonical-v1`)

| Field | Contract |
|---|---|
| `law.id` | Stable catalog identity, e.g. `br-federal:law:1990:8078`; not a URL, content hash, database key or asserted LexML URN |
| `law.aliases` | Historical catalog codes, e.g. `CDC` |
| `law.name`, `designation`, `jurisdiction` | Catalog metadata; unknown authority/issue date remain null; external identifiers remain empty until verified |
| `components` | Main body, ADCT and recognized annexes; each has the law as parent |
| `units[].id` | Law + component + normalized label; independent of chapter title, text hash and segmentation |
| `units[].parent_id`, `order`, `kind`, `label` | Component parent, source order, typed unit and observed label |
| `units[].readings` | All observed occurrences, each with whole text, SHA-256, source wording, hierarchy, rubric, observed status and source metadata |
| `units[].text`, `text_sha256` | Single observed reading, or null when ambiguous |
| `units[].quality` | `observed` or `ambiguous`; does not certify legal completeness |
| `units[].legacy_aliases` | Historical IDs/labels for correspondence, not a claim of identical text or metadata |
| `units[].legal_validity` | `unknown`, null effective dates, empty evidence; current implementation does not determine legal validity |
| `editorial_annotations` | Separate registry assertions, each `origin=editorial`, `review_status=pending`, with no independently verified evidence claimed |
| `prior_redactions` | HTML/CSS struck text observed in available source HTML; not a complete amendment timeline |
| `structure_depth`, `limitations` | Article-level extraction and explicit unresolved limitations |

Kinds: `article`, `annex`, `signatories`, `preamble_or_summary`, `other`.
Hierarchy entries have `level`, `number` and `title`; recognized levels are book,
title, subtitle, chapter and section. Paragraphs/clauses remain text. The law registry
fixes public IDs explicitly; changing a catalog alias must not create a new law identity.
Renumbering a provision is a change of locator requiring an explicit future relation,
not something inferred from similar wording.

`source_text` is the normalized source buffer before unit-level cleaning, not byte-exact
HTML. Only the retained raw source is byte evidence. The canonical cleaned reading is
captured before historical deduplication, overlap and short-text filters. Repeated
labels are not silently resolved. Missing provisions do not acquire invented text.

## Observation, revisions and validity

`provenance` records source URL, observation time/precision, raw and clean SHA-256,
parser revision and curation revision. A historical day stays a day; no time is invented.
`basis=historical-clean-text` means raw source evidence is unavailable.

`content_revision` hashes law/components/units/redactions using deterministic JSON;
`revision` also covers observation/provenance/curation. The content revision includes
compatibility aliases; it is a version of the structured payload, not only prose.
Permanent IDs never use either revision hash. Capture manifests separately record
`recorded_at`, the timestamp of writing that immutable capture. Recording, observation,
source publication and legal effectiveness are different events.

Names, status labels and amendment notes extracted from a compiled page cannot establish
that a provision is legally effective today. Raw HTML/CSS redactions and dedup discards
are not a complete history of legal validity. Editorial claims require independent review.

## Capture and corpus manifests

Canonical captures use `format_version=2`, `format=canonical-v1` and contain exactly
`canonical.json`, `clean.txt`, `source.html` and `manifest.json`. Verification checks
bounded files, exact file selection, hashes, provenance and reproduction from source.
Legacy capture version 1 remains supported without reinterpreting its payload.

Fresh corpus manifests use version 2, an explicit representation, selected law codes,
`coverage=full-catalog|selected-laws`, package/parser versions and file hashes.
`bundle --laws CDC LI` requires exactly those captures; omitting `--laws` still requires
all catalog laws. Duplicates, absent/unknown selections and mixed formats are rejected.

Historical references use `kind=historical-reference`, version 2 and an explicit format.
Canonical historical archives contain per-law documents, clean text, raw HTML where
available and `legacy_redactions.json` as compatibility evidence. They are not fresh
capture directories. L9099 has no historical raw HTML; its canonical prior-redaction
list cannot claim evidence from HTML, while its original sidecar remains preserved.
Inventory counts are explicitly `legacy_counts`; `canonical_units` counts canonical nodes.

Manifest hashes establish internal consistency, not authenticity against an attacker
able to replace all files. Obtain distributions through a trusted channel and pin their
hash. ZIP entries are deterministic. This release creates ZIPs; it does not implement
an untrusted ZIP importer. Never extract untrusted paths without bounds and traversal checks.

## Historical compatibility (`legacy-blocks-v1`)

The original Portuguese fields remain unchanged: `id`, `lei`, `versao`,
`versao_consolidada`, `artigo`, hierarchy fields, `epigrafe` where present,
`path_hierarquico`, `texto_limpo`, `status`, `vetos_parciais`, `alteracoes`,
`referencias`, `notas_legais`, `controle_constitucionalidade`, `hash_artigo`,
`url_fonte`, `data_extracao`, `parte_num`, `total_partes`.

`parse_legacy` is the explicit facade; `parse_law` remains compatible. The historical
split uses up to 6,000 characters and overlap of 400, with guards against degenerate
slices. Preserve `(Parte N/M)` and `(ADCT)` labels. Never concatenate parts blindly.
`hash_artigo` retains its short historical algorithm, including tombstone particulars;
it must not be substituted with a recomposed-text or artifact hash.

Historical `_riscadas.json` contains source redactions AND heuristic discards; it is
not an article list. Runtime application foreign keys are absent from public payloads.
Consumer-specific mappings belong to adapters, not this format specification.

## Reproducible inventory

`python tools/build_inventory.py --check` verifies `docs/source-inventory.json` against
frozen fixtures. `records` counts blocks, not embeddings or unique articles.
The baseline has 15 laws, 6,276 records and 23 multipart groups in 54 parts:
21 article groups plus one annex and one signatory group. LI has 92 records:
91 article records and one introductory block. Counts do not describe production systems.

References: [LexML identities](https://projeto.lexml.gov.br/documentacao/Parte-2-LexML-URN.pdf),
[JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation).
