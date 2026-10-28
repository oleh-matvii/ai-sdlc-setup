# Design patterns by force

Languages with first-class functions, blocks and duck typing (Ruby, TS/JS, Python, Kotlin, Swift) collapse many GoF patterns into a lambda, a hash of lambdas or a module — prefer the lightest form the language offers.

Pick a pattern only for the force in its row. **Overuse sign** is what the pattern looks like when it was added without that force — a review finding of `possible speculative generality`.

## Structural

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Facade** | callers need one simple entry into a complex subsystem or several collaborating units | a facade that forwards 1:1 to a single class (pass-through; fails the deletion test) |
| **Adapter** | an external API/SDK/legacy shape differs from the interface your core owns | adapter for an interface only one thing will ever implement and nothing tests through |
| **Anti-corruption layer** | another bounded context's model would leak its language into yours | translating between two models that are the same |
| **Decorator** | add cross-cutting behavior (caching, retry, logging, auth) without editing the wrapped unit | stacks of decorators where one plain function would do |
| **Proxy** | control access to an object: lazy load, remote, permission check | proxy with no control logic |
| **Composite** | treat a tree of parts and the whole uniformly | a tree that is always one level deep |

## Behavioral

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Strategy** | an algorithm varies by context or configuration and new variants keep arriving | one strategy, or a strategy object for a two-branch `if` that will not grow |
| **State / state machine** | behavior depends on a lifecycle with legal and illegal transitions | a "machine" with two states and no forbidden transitions |
| **Command** | an action must be queued, logged, retried, undone or sent elsewhere | commands that are only ever called synchronously once |
| **Observer / pub-sub / domain events** | several independent reactions to one occurrence; the emitter must not know them | one subscriber, or ordering between subscribers that matters (hidden coupling) |
| **Template method** | a fixed sequence with varying steps, inside one inheritance-safe family | prefer Strategy or passing functions when the family is open |
| **Chain of responsibility / middleware** | a request passes through an ordered, configurable set of handlers | a chain with one fixed handler |
| **Specification** | business rules combined and reused across queries and validation | specifications used in one place |

## Creational

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Factory / factory function** | creation needs a decision (which variant) or hides construction details | `createX()` that only calls `new X()` |
| **Builder** | many optional parameters or a stepwise, validated construction | a builder for a 2-field object |
| **Dependency injection (constructor/param)** | the unit must run against fakes in tests or swap implementations | a DI container in a small script; plain parameters do it |
| **Singleton** | almost never — prefer one instance created at the composition root and injected | global mutable state reached from anywhere |

## Application / data

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Repository** | domain code needs collection-like access to aggregates without knowing storage | a repository per table re-exposing the ORM |
| **Unit of work / transaction script boundary** | several changes must commit or roll back together | wrapping single writes |
| **Service layer / use case (interactor)** | one place per use case coordinates domain objects, transactions and ports | "services" that hold all the domain logic while entities are bags of fields (anemic model) |
| **DTO / mapper** | the transport or storage shape must not leak into the domain | mapping identical shapes field by field |
| **Result / Either over exceptions** | expected failures are part of the domain contract | wrapping truly exceptional failures |
| **Optimistic locking (version column)** | concurrent writers to one record; conflicts are rare | used where a single writer is guaranteed |

## Integration and distributed systems

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Timeout + retry with backoff and jitter** | transient failures of a remote call | retrying non-idempotent calls, or retries stacked at every layer |
| **Circuit breaker** | a failing dependency must not exhaust callers' threads/connections | wrapping in-process calls |
| **Bulkhead** | one slow dependency must not starve the others | isolating a single dependency |
| **Idempotency key / inbox dedup** | at-least-once delivery or client retries must not apply an effect twice | naturally idempotent operations (PUT of full state) |
| **Transactional outbox** | publish an event exactly when the DB transaction commits | used with no message broker |
| **Saga (orchestration / choreography)** | a business transaction spans services with no shared DB transaction | inside one database — use a transaction |
| **API gateway / BFF** | many clients need tailored, aggregated access to several services | one client and one service |
| **Cache-aside / read-through** | repeated expensive reads with tolerable staleness | caching without an invalidation rule |
| **Rate limiter / token bucket** | protect a resource or honor a provider's quota | — |
| **Strangler fig** | replace a legacy system incrementally behind a routing seam | a rewrite small enough to swap at once |
| **Competing consumers / work queue** | spread background work across workers and absorb bursts | ordering-dependent work without partitioning |
| **Sharding / partition key** | data or load exceeds one node; access is keyed | before a single node is measured as insufficient |

## Concurrency

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Producer–consumer with a bounded queue** | decouple production rate from processing rate with backpressure | unbounded queues |
| **Actor / single-owner state** | mutable state accessed by many concurrent tasks | actors around immutable data |
| **Immutable snapshots / copy-on-write** | readers must never see half-written state | large state copied on every small write |
| **Structured concurrency (task groups, cancellation scopes)** | child tasks must not outlive or leak past their parent | — |

## Frontend

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Container / presentational (hooks + components)** | keep rendering separate from data fetching and state | splitting components that have no data logic |
| **Custom hook / composable** | stateful logic shared by several components, or isolated for tests | a hook used once with no logic |
| **Compound components** | a flexible component API whose parts share implicit state | for a component with no variants |
| **Server state cache (query library)** | remote data with caching, refetch and invalidation | duplicating it into a global client store |
| **Global store** | genuinely app-wide client state touched by distant components | local or server state moved into it |

## Testing (TDD)

- **Seams are planned, not discovered**: choose where tests attach (module interface) at design time; red-green-refactor then runs there (`superpowers:test-driven-development`).
- **Fakes over mocks** at port seams: an in-memory adapter is a second implementation, which also makes the seam real.
- **Test pyramid by style**: hexagonal/clean → most tests on the core with fake adapters, few adapter integration tests; FSD → model/lib unit tests per slice, UI tests on widgets/pages; vertical slice → one integration test per slice handler.

## More patterns (lighter-weight or domain-level)

| Pattern | Force it resolves | Overuse sign |
| --- | --- | --- |
| **Value object** (Money, DateRange, Address) | a domain value with its own validation and equality, passed around as primitives today | wrapping a value that has no rules |
| **Special case / Null object** | the same `if x.nil?` / `x == null` branch repeated across callers | one call site |
| **Registry (key → handler lookup)** | per-type behavior selected by a key (payment provider, product type); the lightweight factory | a registry with one entry |
| **Gateway / client** | an external system needs timeouts, retries, error mapping in one place | a gateway around your own in-process code |
| **Mediator** | many UI parts or objects coordinate (wizard, complex form) | a mediator that becomes the god object |
| **Pipeline** | an ordered list of small steps (import, enrichment) | a pipeline with one step |
| **Feature toggle** | release independently of deploy, gradual rollout | a toggle with no removal plan |

## Change and migration patterns

- **Strangler fig:** route traffic gradually from the old implementation to the new one → replacing a legacy module.
- **Branch by abstraction:** introduce a seam, build the new version behind it, switch, delete the old one → large refactors on trunk.
- **Parallel change (expand/contract):** add the new form, migrate callers, remove the old one → renamed columns, API fields, zero downtime.
- **Mikado method:** try the goal change, note the prerequisites, revert, do the prerequisites first → tangled refactors.
