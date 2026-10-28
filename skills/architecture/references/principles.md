# Design principles: what → use when → don't when

Principles are **reasoning aids** for justifying an option. They are not deliverables. Never write "applied SOLID". Name the concrete force instead.

## SOLID
- **SRP** (single responsibility): one reason to change, meaning one actor or stakeholder → splitting god objects and mixed concerns → don't split code that always changes together (that creates shotgun surgery).
- **OCP** (open/closed): extend by adding code at seams that *actually* vary → a second or third variant exists or is scheduled → don't add plugin points with one variant.
- **LSP** (Liskov): subtypes honor the parent's contract (pre/postconditions, no surprise exceptions) → STI, polymorphic components, duck-typed collaborators → when it's violated, use composition instead of inheritance.
- **ISP** (interface segregation): small, client-specific interfaces (narrow props, narrow service APIs) → a "fat" object is passed where 1–2 methods are used → don't split an interface with one client.
- **DIP** (dependency inversion): high-level policy depends on abstractions; details plug in → real seams (payment gateway, shipping provider APIs, clock, external queues) → don't wrap ActiveRecord, MUI or the framework "just in case".

## GRASP (assigning responsibilities)
- **Information Expert:** give the responsibility to whoever has the data → the default choice for where a method goes → but don't make models god objects. Orchestration across many experts goes to a Controller/service.
- **Creator:** A creates B if A contains, aggregates or closely uses B → building child records → use a factory when creation logic is complex or varies.
- **Controller** (use-case controller): a non-UI object handles a system operation → Rails service/interactor per use case → not one per CRUD action.
- **Low Coupling / High Cohesion:** the main yardsticks for comparing any two options.
- **Polymorphism:** replace type conditionals with polymorphic objects → the same `case type` appears in 3+ places → not for one conditional.
- **Pure Fabrication:** invent a non-domain class to keep cohesion (repository, client, presenter) → when the expert would become incoherent → don't fabricate layers with no behavior.
- **Indirection:** put an intermediary between two parts to decouple them → integration seams → every indirection must earn its keep (see "deep modules").
- **Protected Variations:** wrap a predicted point of change behind a stable interface → known volatility (vendor APIs, pricing rules) → not for speculative volatility.

## Simplicity
- **KISS / YAGNI:** build for requirements that exist now. This is the default tie-breaker between options.
- **DRY:** one source per piece of *knowledge*, not per piece of identical-looking code → business rules, constants, schemas → rule of three; a wrong abstraction costs more than duplication.
- **Rule of three:** extract on the third occurrence, not the second.
- **Deep modules** (Ousterhout): a small interface over lots of behavior → evaluating new classes and hooks → reject shallow pass-through layers. **Deletion test:** if deleting the module and inlining it makes callers simpler, it should not exist.
- **Make the change easy, then make the easy change** (Beck): refactor first, in a separate commit or PR.

## Coupling and dependencies
- **Law of Demeter:** talk to immediate collaborators, no `a.b.c.d` across boundaries → domain code and services → fine inside views, presenters, query chains and value objects.
- **Tell, don't ask:** ask objects to do things instead of pulling their data to decide → domain logic leaking into callers → not for pure data structures and DTOs.
- **CQS** (command-query separation): a method either changes state or returns data, not both → domain APIs → pragmatic exceptions like `stack.pop` or `save` returning a boolean.
- **Composition over inheritance:** concerns used sparingly, hooks and components over HOCs and class trees → inheritance is fine for framework base classes (ApplicationRecord) and true is-a hierarchies.
- **Connascence** (weak → strong): name < type < meaning (magic values) < position (arg order) < algorithm < execution order < timing < values < identity → rank coupling, and push strong connascence inside module boundaries. Across modules, keep it to name/type.
- **Package principles** (for engines, packs, npm packages): REP/CCP/CRP decide what goes together (things that change together ship together). ADP: no cycles. SDP: depend toward stability. SAP: stable packages should be abstract → use when splitting a monolith into packwerk packs or a monorepo.
- **Separation of concerns / dependency rule:** source dependencies point inward, toward policy and domain, never from domain to UI, HTTP or DB details.

## Robustness
- **Fail fast:** validate at boundaries and raise early with context → inputs, config, external responses → don't fail fast inside user-facing flows that need graceful degradation.
- **Postel (robustness):** be liberal in what you accept and strict in what you send → external integrations → careful: being liberal hides contract drift. Log the deviations.
- **Idempotency:** the same operation applied twice has the same effect → jobs, webhooks, payment and order-placement calls → always for at-least-once delivery.
- **Principle of least astonishment:** names and behavior match expectations → API design, props naming.
- **Explicit over implicit:** explicit calls over callbacks and metaprogramming in business flows.
