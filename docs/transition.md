# Breaking contracts and consumer transition

Version 0.2.0.dev1 introduces observed-law-v1 / observed-jurisprudence-v1. Public
capture generation no longer supports legacy-blocks-v1, canonical-v1 or
jurisprudence-v1. Old fixtures and schemas remain historical evidence; they do not
justify creating synthetic legal content. No package, corpus or MCP service is
published by this change.

## Consumers inspected

| Consumer | Existing behavior | Required integration work |
|---|---|---|
| Data pipeline | Own `extrair_leis.py` still removes strike text, applies `known_issues.json` overrides and generates explanatory tombstones; ingestion expects Portuguese legacy fields | Replace acquisition/projection with a version-pinned adapter; reject unsupported formats and ambiguity; remove synthetic generation in its own reviewed change |
| Corpus repository | Raw captures and derived historical records with independent provenance | Preserve originals, add diagnostics with source hash/date/parser, never overwrite history to make counts pass |
| Backend | Searches `justina.legal_documents`, defaults semantic status to vigente, hydrates article parts using `(Parte N/M)` labels | Explicit identity/version/status adapter and retrieval policy; unknown observed validity must not become vigente; maintain component isolation and multipart provenance |

These repositories are not submodules. No database schema, production ingestion,
prompt, embedding model or retrieval threshold is changed by this public increment.
The public format is not a drop-in replacement for the backend's legacy row shape.
Passing it directly would lose fields or conflate old/new readings and ADCT/main.

## Integration acceptance

1. Pin the source document and structured revision. Map every old `(law, article,
   part)` to a public component/unit/occurrence, or report it unresolved.
2. Define how search handles multiple observations and unknown validity. Never
   select the longest/latest captured reading as legally effective by default.
3. Build consumer chunks as derivatives referencing the full occurrence. Recheck
   all 24 multipart articles / 62 historical parts and their overlap and citations.
4. In DEV, compare ingestion counts, identities, text hashes, note evidence and
   replay. Exercise semantic search, direct lookup and multipart hydration. Changes
   to data do not authorize paid embeddings/evals or production writes implicitly.
5. Gate deployment on a separate migration plan, validated snapshots, dependency
   invalidation and rollback. Package rollback alone does not restore data versions.

## Historical corruption audit and production remediation

A read-only backend diagnostic was used to compare the 15 historical tombstone
keys and source hashes against production. Sensitive operational artifacts and the
specific evidence/recovery plan belong in the private corpus repository, not here.
A matching legacy source hash establishes version correspondence, not an independent
byte-for-byte text comparison or a proof of every affected downstream artifact.

Required remediation is a separately approved operation: capture immutable before
state; verify actual stored texts and dependent synthetic questions/embeddings;
re-extract original official evidence; stage replacements without synthetic fillers;
review legal ambiguities; validate DEV retrieval and citations; activate append-only
versions through the supported workflow; retain an explicit rollback activation map.
Never delete historical rows or mutate production as a side effect of an audit.

## Public follow-up

Resolve structural discrepancies per source, then certify any completeness claims
against reviewed evidence. Licensing, MCP implementation and consumer migration
remain separate work. See [MCP proposal](mcp-contract.md) and [validation](validation.md).
