# Source observation contracts

The default public formats are `observed-law-v1` and `observed-jurisprudence-v1`.
Both declare `source-observation-v1`. This is a breaking change from canonical-v1,
legacy-blocks-v1 and jurisprudence-v1. Historical schemas and fixtures remain evidence;
public capture APIs reject generation of the historical formats.

## Shared semantics

| Value | Meaning |
|---|---|
| Identity | Catalog law/component/article or source collection/official number; never a text hash |
| Reading | An occurrence in captured evidence, not a legally selected effective version |
| `source_text` | Exact concatenation of referenced decoded text fragments, CSV thesis field, JSON thesis field or PDF text span |
| `text_sha256` | SHA-256 of that UTF-8 transcript; not the raw file hash |
| `raw_sha256` | SHA-256 of captured bytes; null when only historical derived text exists |
| `structured_sha256` | SHA-256 of sorted compact UTF-8 JSON excluding provenance, reconciliation and revision hashes |
| `revision` | SHA-256 of the document with provenance and reconciliation, excluding only itself |
| Observation | Actual capture date/instant with precision; never an invented publication or effective date |
| Source statements | Literal mentions and offsets; unknown target is null, not an inferred article status |
| `legal_validity` | Always unknown in this implementation |
| `complete` | Independent structural acceptance; currently false for all reference sources |

Raw files, decoded evidence and structured data have different hashes. Hashes and
replay prove consistency against supplied bytes, not authenticity of a compromised
publisher. Acquire through a trusted channel and pin hashes.

## Legislation

`law` contains the fixed catalog ID and alias. Components distinguish main, ADCT and
observed annexes. Articles use component + normalized number, preserving suffixes.
Heading, annex and unclassified locators derived from source paths are capture-local;
they are not stable cross-capture legal identifiers.

Each unit has ordered `readings`, referenced `evidence_ids`, observed hierarchy and
literal source statements. Repeated labels preserve every occurrence. Mixed struck
and unstruck fragments have `text=null`; their `source_text` is a source-order
transcript, never a consolidated current wording. An ambiguous unit also has null
text. Clients retrieve occurrences and fragments explicitly.

`evidence` retains element paths, attributes (including links, row/column spans),
text paths, exact decoded text, text hashes, strike ancestors, block/table paths and
classification as content, page chrome, comment or active content. Active material
is inert evidence. No script, link, stylesheet or embedded action is executed.
Inline strike recognition is not a CSS rendering engine; external styles are not
fetched. Undecodable trailing bytes remain recorded and prevent completeness.

Hierarchy extraction currently records the observed heading context; it does not
certify all parent levels. Subparagraphs and clauses are not individually identified.
Tables retain their DOM evidence, without inferring row meanings. Unclassified
material is preserved and reported. No minimum text length discards short articles.
No overlap, chunking, tombstone or editorial registry is part of the new export.

An independent stdlib HTMLParser traversal counts article candidates at explicit
block and `br` boundaries, including multiple labels in one paragraph and labels
outside paragraphs. Soft line breaks and inline tags do not terminate a label.
This traversal does not import the BeautifulSoup segmenter. The reconciliation lists missing/extra identities,
source occurrences, unmapped fragments and unclassified units. Equal article counts
do not certify boundaries, note targets or table semantics. `complete=false` remains
mandatory while these reviews are unresolved. L9099's historical clean text cannot
be promoted to raw evidence with a detached hash.

`observed-legislation@3` keeps closed, wholly bold runs that precede a label inside
the article of that label, in source order, ahead of the label and its notes. The
article is created from the captured `Art.` label. A bold run with no following
label does not receive an invented number. A single orphan label, ordinary bold
paragraphs, inline emphasis, open bold wrappers, and table cells do not trigger
this join. Multi-line named headings keep their context. `legal_validity` stays
`unknown`.
The evidence map remains `html-evidence@1`, unchanged; only segmentation and the
independent census (`stdlib-htmlparser-block-break-labels@2`) have new revisions.
Reprocessing produces a new document revision; it never overwrites old captures.

## Jurisprudence

Identity is `br:<collection>:<official-number>`. STJ CSV uses `sequencialPrecedente`,
without inferring a precedent type. Missing numbers use an explicit unclassified
source locator. Repeated numbers preserve occurrences instead of choosing a winner.

CSV retains all headers and row cells; JSON retains all original keys and values;
HTML retains the full evidence map; PDF retains every extracted page and offsets in
the page transcript. A missing thesis remains an empty thesis with the original other
fields, never a generated replacement. The STF with/without-thesis lists are explicit
source evidence. HTML/PDF thesis presence remains unknown. `situation` is only the
literal `situacao` field where supplied; it is otherwise null. Cancellation mentions
and linked STF index evidence remain available without inventing legal dates.

Date fields are retained literally, with parsed value and precision null when no
source-specific event parser exists. Observation precision is separate. PDF text is
a derived extraction, not byte-exact source text, and needs visual/boundary review.

## Captures and archives

Legislation captures use manifest version 3 and `observed-law-v1`, with exactly
`canonical.json`, `clean.txt`, `source.html`, `manifest.json`. `clean.txt` is a decoded
source-order transcript, despite its historical filename. Verification reads bytes
without newline conversion and replays the parser. Corpus manifests use version 3.

Jurisprudence captures use `jurisprudence-capture-v2`; archives use
`jurisprudence-corpus-v2`. Raw files and request descriptors are retained. Every
archive exposes completeness, selection and hashes. `source_snapshot` describes
the requested acquisition, not certified exhaustive coverage. Samples require an
explicit option and remain samples. Packaging an incomplete diagnostic observation
never makes it a production-ready legal corpus.

Historical reference archives are distinct from fresh capture directories. They
preserve original date precision and missing evidence. Files named
`*-historical.schema.json` describe earlier contracts only. Old validation helpers
are diagnostic; new public exporters do not call their lossy transformations.

## Inventory summary and full audit report

The versioned `docs/source-inventory.json` is a summary, not a corpus document.
It keeps counts, source provenance, parser version, all reported differences and
`report_sha256` of the full reconciliation object (excluding that hash field).
Exhaustive source/structured identity and occurrence lists remain in the generated
`dist/source-fidelity-report.json`, available as a CI artifact for 14 days or
reproducible from the same commit. `--check --report PATH` verifies the committed
summary/READMEs while exporting the full report even if those files are stale.
The observation/capture formats and their embedded reconciliation are unchanged.
