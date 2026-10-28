# Public roadmap and consumer compatibility

PR #1 has been merged. The legislative increment established the public corpus
model alongside the historical export. It does not migrate any consumer, publish a
package/dataset, or provide an MCP server.

## Current delivery

- Python >=3.14 library/CLI, packaged catalog and bounded source capture.
- Canonical article-level units, complete readings, explicit ambiguity and provenance.
- Editorial assertions separated from observed text and legal validity.
- Historical compatibility projection, frozen fixtures and deterministic local archives.
- Public contract and limits for a future read-only MCP.

The reviewed extraction history and attribution remain preserved. See
[history-review.json](history-review.json). No additional history rewrite is needed.

## Consumer integration, later

A consumer can use the Python package, pin a corpus release, or use the future MCP.
Sharing data does not require sharing a production database or making an MCP call
for every question. Search segmentation, embeddings, indexing and business decisions
are owned by the consumer unless offered as a documented generic public capability.

The Justina project originated the extraction work and is an example of a consumer.
Its original extractor remains active. Its adaptation will happen after the public
project is finalized, in its own repositories and with its own approval/testing flow.
No private repositories or systems are modified by this increment.

A safe integration pins an exact package/corpus version and artifact hash, compares
historical identifiers/text/hashes/metadata/parts/redactions, and exercises the actual
consumer in an isolated environment before rollout. Use `legacy-blocks-v1` where the
consumer still depends on historical fields. Do not inject application database IDs
into the public corpus or assume canonical and historical counts are equal.

Rollback before integration means retaining the existing consumer. After data changes,
rollback must account for activated data revisions as well as package versions.
Migration-specific deployment and persistence instructions belong with each consumer.

## Next public increments

1. Resolve licensing and review source evidence/collection failures.
2. Implement read-only MCP against the canonical corpus, independent of consumer migration.
3. Validate installation, transport interoperability and bounded textual search.
4. Decide hosted operation, access policy and service objectives before deployment.
5. Extend finer legislative structure and evidence-backed temporal metadata as separately
   tested capabilities; do not infer them from the current parser status.

See [MCP contract](mcp-contract.md). Stdio first is the recommended implementation path;
hosting or both distributions remain a product decision, not an implemented capability.

## Jurisprudence incorporation

The public package now owns standalone capture/validation/archiving for six official
jurisprudence sources, plus the validation contract for individual judgments.
The extraction and ingestion used by existing consumers remain independent until
a separately tested integration. Source JSON fields are preserved for comparison;
consumer thresholds, embeddings and production tables are not exported as public policy.
See [the capability and limitations](jurisprudence.md).
