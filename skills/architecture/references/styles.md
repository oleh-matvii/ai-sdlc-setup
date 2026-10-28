# Architectural styles

Each entry: what it is, the **dependency rule** that defines it, when it fits, when it doesn't, and how to enforce it. Pick by forces; the project's existing style wins unless an ADR changes it. Styles combine: FSD on the frontend with hexagonal services behind it, a modular monolith whose modules are vertical slices.

## Layered (n-tier)
- **Rule:** presentation → application → domain → infrastructure; each layer calls only the one below.
- **Fits:** CRUD-heavy apps, small teams, simple domains.
- **Doesn't:** rich domain logic (domain ends up depending on infrastructure); features that change every layer at once.
- **Enforce with:** import rules per folder (dependency-cruiser, eslint `no-restricted-imports`, Python `import-linter` layers contract, ArchUnit).

## Hexagonal (ports & adapters)
- **Rule:** the core (domain + use cases) defines **ports** (interfaces it needs or offers); **adapters** (HTTP, DB, queue, SDK, CLI) implement them outside. Nothing in the core imports an adapter.
- **Fits:** several delivery channels or storages, volatile third-party APIs, core logic that must be tested without I/O.
- **Doesn't:** thin CRUD with one DB and one UI — ports then have a single adapter and are hypothetical seams.
- **Enforce with:** core package with no imports of framework/driver packages; adapters depend on core, never the reverse.

## Clean / Onion
- **Rule:** concentric rings — entities → use cases → interface adapters → frameworks; source dependencies point inward only. Hexagonal with explicit use-case and entity rings.
- **Fits:** long-lived systems with complex business rules and many integrations.
- **Doesn't:** prototypes and small services — ring ceremony outweighs the change it absorbs.
- **Enforce with:** the same inward-only import rules as hexagonal, one per ring.

## Feature-Sliced Design (FSD) — frontend
- **Layers (top → bottom):** `app` → `pages` → `widgets` → `features` → `entities` → `shared`. **Rule:** a module imports only from layers strictly below it; slices on the same layer never import each other; every slice exposes a public API (`index`) and its segments (`ui`, `model`, `api`, `lib`, `config`) stay private.
- **Fits:** medium-to-large frontends (React, Vue, Svelte, Angular) with many features and several developers.
- **Doesn't:** tiny apps; cross-feature logic is then forced down into `entities`/`shared` or up into `widgets` — decide which before writing.
- **Enforce with:** `@feature-sliced/steiger` or `eslint-plugin-boundaries`; public-API-only imports.
- **Source:** https://feature-sliced.design

## Vertical slice
- **Rule:** code is grouped by feature/use case end-to-end (request → handler → data); slices share little, coupling is within a slice.
- **Fits:** many independent use cases, CQRS-flavoured backends, teams owning features.
- **Doesn't:** heavy shared domain invariants across slices — they get duplicated.
- **Enforce with:** no cross-slice imports except through a shared kernel.

## Modular monolith
- **Rule:** one deployable, split into modules with explicit public interfaces and owned data; modules talk through those interfaces or events, never each other's tables or internals.
- **Fits:** the default for a growing product before microservices; keeps the option to extract a module later.
- **Doesn't:** independently scaled or deployed parts with separate teams — then services.
- **Enforce with:** entry-point-only imports (packwerk for Rails, dependency-cruiser, Spring Modulith, import-linter independence contract).

## DDD (tactical + strategic)
- **Strategic:** bounded contexts with their own ubiquitous language (`GLOSSARY.md`); an **anti-corruption layer** translates at context borders.
- **Tactical:** entities (identity), value objects (immutable, compared by value), aggregates (consistency boundary, one root, transaction = one aggregate), domain services, domain events, repositories per aggregate.
- **Fits:** complex, rule-heavy domains with domain experts to talk to.
- **Doesn't:** data-in/data-out apps — tactical patterns become ceremony.
- **Enforce with:** aggregates modified only through their root; repositories return aggregates, not rows; per-context packages.

## Event-driven / CQRS / event sourcing
- **Event-driven:** units react to published events instead of calling each other — decoupling in time and ownership, at the cost of traceability and eventual consistency.
- **CQRS:** separate write model (commands, invariants) from read models (queries, projections). Fits when reads and writes differ sharply in shape or load.
- **Event sourcing:** state = fold over stored events. Fits audit-heavy domains; costly to migrate — always an ADR.
- **Enforce with:** schema'd events, idempotent handlers, an outbox for publish-after-commit.

## MVC / MVP / MVVM
- **Rule:** the view renders and forwards input; the controller/presenter/view-model holds presentation logic; the model holds domain state. Domain rules stay out of the view and out of the controller.
- **Fits:** UI layers on any platform; it describes the presentation tier only — combine with a style above for the rest.

## Pipes and filters
- **Rule:** independent stages, each a transform with a defined input and output schema, connected by queues or streams; stages share nothing else.
- **Fits:** data/ETL pipelines, media processing, compilers, stream processing.
- **Doesn't:** interactive request/response logic with shared state.
- **Enforce with:** schema contracts between stages; each stage testable with fixture input → expected output.

## Microkernel (plugin)
- **Rule:** a minimal core with a stable extension interface; features ship as plugins that depend on the core, never on each other.
- **Fits:** IDEs, CLIs, build tools, products with third-party or per-customer extensions.
- **Doesn't:** a fixed feature set with no external extenders — the plugin interface is a hypothetical seam.
- **Enforce with:** plugins import only the core's public extension package.

## Serverless / function-per-use-case
- **Rule:** each function is one handler with no in-memory state between calls; state lives in managed services.
- **Fits:** spiky or low traffic, event-triggered work, glue between managed services.
- **Doesn't:** long-running, latency-critical or chatty workloads; shared domain logic still belongs in a library the functions import.

## Microservices
- **Rule:** independently deployable services, each owning its data, communicating over the network.
- **Fits:** independent scaling/deploy cadence, separate teams, proven module boundaries.
- **Doesn't:** a single team or unproven boundaries — start as a modular monolith.

## BFF / API gateway
- **BFF:** an API shaped per client (web, mobile, widget) when client needs diverge. **API gateway:** one entry point for cross-cutting concerns (auth, rate limits, routing).
- **Doesn't:** one client and one service.

## Micro-frontends
- **Rule:** independently built and deployed frontend parts owned by separate teams, composed at runtime or build time.
- **Fits:** several teams shipping separate parts of one UI on their own cadence.
- **Doesn't:** one team — the cost (bundle size, UX consistency, shared state) is high; a shared design system plus a monorepo with package boundaries is usually enough.

## Workflow: orchestration vs choreography
- **Orchestration** (a saga / process manager owns the flow) when there are many steps and compensations; **choreography** (events) for few, independent reactions.

## DDD strategic extras
- **Context map relations:** shared kernel, customer/supplier, conformist, anti-corruption layer, open host service + published language, separate ways, partnership — pick how two contexts integrate.
- **Core / supporting / generic subdomains:** invest design effort in the core; buy or keep the generic ones simple.

## Choosing a style
1. Start from the repo's existing style and the team's ability to maintain it.
2. Name the top 2–3 quality attributes the change stresses (`system.md`, `tradeoffs.md`).
3. Prefer the least distributed, least abstract option that meets them.
4. A style change gets an ADR and a migration path (strangler fig or branch by abstraction).
5. The catalog is a shortlist, not the limit: research the problem class (`research.md`) and let any well-sourced candidate compete on the same forces.
