# MCP contract proposal — not implemented

This document specifies the next increment. No server module, executable MCP command,
hosted endpoint, search engine or MCP dependency is included in the current package.
The service will read a validated, explicitly selected corpus release, not live web
pages or a consumer's operational database. Consumer migration is not a prerequisite.

## Operations

| Tool | Inputs | Output |
|---|---|---|
| `list_laws` | Filters, limit, opaque cursor | Available norms, coverage and resolved corpus revision |
| `get_law_metadata` | Public norm ID or unambiguous alias, optional corpus revision | Identity, sources, observation dates, available revisions and limitations |
| `get_provision` | Norm and unit locator, optional corpus revision | Whole reading or paginated text, hierarchy, provenance and observed classification |
| `search_legislation` | Text, norm/component/type filters, limit and cursor | Deterministically ordered matches, excerpts and canonical unit references |

Every result must identify the corpus/document revision, source, observation precision
and limitations. Ambiguous units return their readings and an explicit ambiguity state;
no longest/last-reading guess. Unknown validity remains unknown. Paragraph lookup must
return unsupported-granularity until paragraph extraction is implemented and validated.

Errors distinguish unknown law/unit, ambiguous alias, unsupported granularity, unavailable
revision, invalid corpus, malformed cursor, limit exceeded and cancelled/timed-out work.
Use typed input/output schemas and MCP structured content. Versioned resource URIs can
complement tools for addressable documents; responses must not expose local filesystem paths.

## Proposed bounds

- Query: 1–1,000 characters; default page 20, maximum 100 results.
- Serialized result budget: 256 KiB; explicit continuation for larger texts, no silent truncation.
- Cursor bound to normalized query/filters, authorization scope and corpus revision.
- Read-only operations: no shell, uploads, arbitrary URL fetch, corpus update or external writes.
- Initial search: deterministic text search; ranking/index revision disclosed.
- Semantic search remains possible later as a generic, versioned derivative; no inherited
  consumer-specific model, dimension or threshold is part of the public contract.

Exact deadlines/concurrency quotas must be established with corpus-scale measurements
before the server is enabled. No external inference calls are needed for this initial scope.

## Distribution alternatives

| Choice | Responsibility |
|---|---|
| Installable/stdin-stdout (recommended first) | Versioned package and local corpus; offline queries; logs on stderr; client owns process lifecycle |
| Hosted/Streamable HTTP | Deployment, TLS, access policy/authentication, Origin validation, quotas, metrics, availability and corpus update operations |
| Both | Same read service and schemas, two transport adapters and interoperability matrix |

Protocol reference checked on 2026-10-27: specification 2026-07-28 and official Python
SDK v2 documentation. Pin a tested stable SDK release when implementation begins;
Python >=3.14 remains the project requirement. Verify legacy-client compatibility through
the SDK rather than copying earlier session/handshake examples. Hosting is not decided.

## Abuse, failure and resilience acceptance

Test prompt injection in every textual/metadata field, tool-name poisoning, SSRF and
file traversal, exfiltration, command requests, malformed JSON, regex/query abuse,
large/deep payloads, tampered cursors, concurrency, cancellation and cross-user/state leakage.
Annotations such as read-only hints are not authorization controls. Source text is data,
never an instruction to the service or the consuming agent. Use synthetic secrets as canaries.

Reject missing/corrupt corpus without substituting another revision. Load approved releases
atomically; retain the prior validated release for operator rollback. Bounded local queries
need no network retry. Remote deployment needs quotas, per-request deadlines, safe metrics,
redacted logs and a failure/upgrade strategy for SDK, authentication and hosting dependencies.
Health checks must distinguish serving an old explicitly identified release from a failed update.

## Official references

- [Specification](https://modelcontextprotocol.io/specification/2026-07-28)
- [Tools and structured output](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- [Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [HTTP security](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Security practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)
- [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
