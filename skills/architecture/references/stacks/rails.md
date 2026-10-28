# Rails / Ruby backend patterns

Prefer the building blocks the repo already has (for example `interactors/`, `builders/`, `event_handlers/`, `workers/`). The list below is for choosing when nothing in the repo fits, and for judging a design in review.

## Where logic goes
| Need | Use | Avoid |
|---|---|---|
| One business operation with steps (place order, issue refund) | **Service / interactor**: a PORO with one public method (`call`) that returns a result object or success/failure. Inject collaborators via `initialize` with defaults. | Fat models, fat controllers, logic in callbacks |
| Validating input that does not map 1:1 to a model (multi-model form, API payload) | **Form object** (`ActiveModel::Model` + validations) | `accepts_nested_attributes_for` chains, validations depending on context flags |
| Reusable or complex query | **Query object** or a named scope. Keep it chainable (return a relation). | Raw SQL interpolation, query logic duplicated in controllers |
| Domain concept with value semantics (Money, Address, DateRange) | **Value object**: immutable, compared by value | Passing hashes or primitives around (primitive obsession) |
| Permission rules | **Policy** (Pundit-style, or the repo's own) checked in the controller, with scoping for index queries | `if current_user.admin?` scattered through the code |
| Building a complex object or payload (API request, document) | **Builder** | 100-line `to_h` methods on models |
| Behavior that varies by type (payment provider, product, state) | **Strategy plus registry/factory**: a hash from key to class, or a `case` in one place only | The same `case type` repeated in several places |
| Lifecycle with explicit states | **State machine** (AASM or the repo's gem), with guarded transitions | Status strings mutated from anywhere |
| Reacting to domain events | **Event handler / subscriber** (the repo's mechanism) | `after_commit` chains that call external APIs |
| Async work | **Job/worker**: idempotent, retry-safe, takes IDs not objects, small payload | Jobs that are not re-runnable, enqueued inside transactions that may roll back |
| External API | **Client/adapter class** wrapping HTTP, with timeouts, error mapping to domain errors, and VCR-tested | HTTP calls inline in services or models |

## Principles applied to Rails
- **SRP:** a model holds persistence, associations, validations of its own invariants and simple domain methods. Orchestration goes to services.
- **Dependency inversion, in practice:** services take collaborators as keyword args with defaults (`def initialize(client: PaymentClient.new)`). Tests inject fakes without global stubbing.
- **Open/closed:** adding a new variant (payment provider, product) should mean adding a class and registering it, not editing 5 conditionals.
- **Callbacks:** only for the record's own data integrity (normalizing a field). No side effects: no emails, jobs or external calls in `before_*`/`after_*`. Use `after_commit` only for enqueueing, and only when the repo does this already.
- **Transactions:** wrap multi-record writes, and keep external calls outside them. Enqueue jobs after commit.
- **Concerns:** only for truly shared, cohesive behavior. They are not a place to hide a fat model.

## Data and migrations
- Migrations must be production-safe: add columns without volatile defaults on big tables, add indexes concurrently (Postgres), and backfill in batches as a separate step or job. Migrations must be reversible.
- New lookups need an index. Uniqueness needs both a DB constraint and a validation.
- Watch for N+1: `includes`/`preload` for collections rendered or serialized.

## Testing shape
- Services, query objects and value objects get unit specs, which are fast and the main coverage.
- Request specs test the HTTP contract and authorization. They should not re-test business branches.
- Use VCR cassettes for external APIs. Cassettes must not contain real customer data or real auth headers (filter them).

## Smells that justify a refactor
- A god model (more than ~500 lines, or many unrelated public methods).
- A controller action longer than ~15 lines, or with business branching.
- The same `case`/`if` on type in 3 or more places.
- Callbacks with side effects. Services calling services 4 levels deep with shared mutable state.
- Methods taking more than 4 positional params, or boolean flag params that switch behavior.

## When NOT to abstract (keep it simple)
| Situation | Keep | Don't extract |
|---|---|---|
| CRUD action under ~10 lines | in the controller | a service object |
| A query with 1–2 conditions | a scope | a query object |
| A single-model form | `form_with model:` plus model validations | a form object |
| Display formatting used once | a helper or view | a presenter class |
| One variant of a behavior | a method | strategy, factory or registry |
| Logic that belongs to one model's data | a model method (avoid anemic models) | a "ModelNameService" |

## Layering rules (from palkan's *Layered Design for Rails*; full guide in the `layered-rails` skill)
- Layers: Presentation (controllers, views, channels, forms, presenters, serializers) → Application (services, policies, mailers, deliveries) → Domain (models, value objects, domain services) → Infrastructure (adapters, clients, DB).
- Data flows one way. A lower layer never depends on a higher one. For example, no `Current` and no `request` in models or services: pass explicit arguments.
- **Specification test:** if an object's spec has to cover concerns outside its layer's job, extract.
- Use the plugin's commands for deeper work: `/layered-rails:analyze`, `:analyze-callbacks`, `:analyze-gods`, `:review`, `:plan`.

## Ecosystem choices (use what the Gemfile already has)
- Read `Gemfile.lock` first: Rails version, Sidekiq/GoodJob, Pundit/ActionPolicy, dry-rb, ViewComponent, AASM, serializers (Alba, Blueprinter, jbuilder).
- **Modular monolith:** packwerk packs (`packs/<name>` with `package.yml` and public APIs) or Rails engines → for a growing app with tangled dependencies.
- **dry-rb** (dry-validation contracts, dry-monads Result): only if it is already adopted. Don't mix it with another result convention.
- **ViewComponent:** reusable server-rendered UI with tests. **Trailblazer:** heavy, don't introduce it.
- **strong_migrations:** catches unsafe migrations. A good fitness function.
