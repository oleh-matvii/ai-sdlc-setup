# System level

Decisions above the code: what the parts of the system are, how they talk, who owns which data, and which quality attributes drive the shape.

## Quality attributes (non-functional forces)

Name the ones that matter for this system as **scenarios**, each measurable: source → stimulus → response → measure. "At 500 req/s, a checkout completes in < 300 ms p95." A quality attribute with no scenario is not a force.

- **Performance / scalability** — throughput, latency percentiles, data volume growth.
- **Availability / resilience** — uptime target, behavior when a dependency is down, recovery time and data loss tolerance (RTO/RPO).
- **Consistency** — where strong consistency is required and where eventual is acceptable.
- **Security / privacy** — trust boundaries, authn/authz model, sensitive data and where it may flow.
- **Modifiability** — which changes must be cheap (new payment provider, new tenant, new UI).
- **Testability, deployability, operability / observability** — independent deploys, logs/metrics/traces, debuggability.
- **Cost** and **team** — budget, team size and skills, Conway's law (the structure will mirror the team boundaries).

Trade-offs between them are explicit: name what each option gives up (ATAM-style).

## Parts and their seams (C4)

Describe the system at the zoom level the decision needs, as Mermaid diagrams in the design output (and the spec's `## Design`); stop at the level that adds no information. Keep each diagram under ~20 elements and label every relationship with a verb and the technology.

1. **Context** — the system, its users and external systems.
2. **Container** — deployable/runnable parts (apps, services, databases, queues, functions) and how they communicate.
3. **Component** — the modules inside one container and their dependencies.
4. **Code** — classes/functions only for a tricky core; usually skipped.

## Integration between parts

- **Synchronous (HTTP/gRPC)** when the caller needs the answer now; add timeouts, retries with backoff on idempotent calls, and a circuit breaker for remote dependencies.
- **Asynchronous (queue/stream/events)** when the work can happen later, has several consumers, or must survive the consumer being down; design for at-least-once delivery (idempotency, ordering per key, dead-letter handling).
- **Contracts** are versioned and owned by the provider (or consumer-driven contract tests); a breaking change ships as a new version alongside the old.
- **API style** by force: REST for resource-oriented public APIs, gRPC for internal low-latency service calls, GraphQL/BFF when clients need varied aggregated shapes, events for facts others react to.

## Data

- **Each piece of data has one owner** (module or service) that alone writes it; others read through its interface or a replicated read model.
- **Storage by access pattern**: relational for transactional integrity and ad-hoc queries; document/key-value for aggregate-shaped access at scale; search engines for full text; time-series for metrics; object storage for blobs.
- **Consistency boundaries** match aggregates/transactions; anything spanning them is a saga or eventual consistency, decided explicitly.
- **Schema evolution**: expand → migrate → contract; never a breaking change in one deploy.

## Architecture anti-patterns

- **Big ball of mud** — no recognizable structure; start by drawing the real dependency graph and cutting one seam at a time (strangler fig).
- **Distributed monolith** — services that must deploy together or chain synchronous calls; merge them or make the seam asynchronous.
- **Shared database integration** — several modules/services writing the same tables.
- **God module / service** — owns most of the domain; split by bounded context.
- **Anemic domain model** — entities are bags of fields and all rules sit in services (acceptable for CRUD, a defect for rule-heavy domains).
- **Golden hammer** — one style or tool for every problem (microservices, event sourcing, a framework) regardless of forces.
- **Résumé-driven architecture** — technology chosen for novelty; every choice traces to a force or is dropped.

## Fitness functions — keeping the architecture true

An automated check that fails when the architecture drifts. Pick at least one for the chosen style:

- **Dependency rules and cycles** — dependency-cruiser, eslint-plugin-boundaries, steiger (FSD), import-linter (Python), ArchUnit (JVM), NetArchTest (.NET), `go vet` + custom analyzers / depguard (Go).
- **Size and complexity budgets** — max file/function length, cyclomatic complexity, via the linter.
- **Contract tests** — Pact or schema checks between services.
- **Performance budgets** — a benchmark or load-test threshold in CI for the quality attribute scenarios above.
