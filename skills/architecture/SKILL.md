---
name: architecture
description: Use when designing a new feature, module, service or system (size L/XL), planning a refactor, introducing a new abstraction, or reviewing a change for design quality - in any stack (backend, frontend, mobile, data, infrastructure). Stack-agnostic, codebase-first guidance at four zoom levels (system, style, modules and files, code) with catalogs of styles and patterns by force, a research method for finding the best-fitting architecture, trade-off scoring and anti-over-engineering rules; stack notes for Rails, React and others.
---

# Architecture: choosing structure and patterns

Read this before you propose a design. Use it to judge a design in review.

## Four zoom levels
Architecture is decided top down; each level constrains the one below. Work at the level the decision lives on and go up one level only to check the fit.
1. **System** — the parts (apps, services, stores, queues), how they talk, who owns which data, the quality attributes that drive the shape → [system.md](references/system.md).
2. **Style** — inside one part: which layers or slices exist and which way dependencies point → [styles.md](references/styles.md).
3. **Modules and files** — modules/packages/folders, what each owns, public surfaces, coupling, cycles, stability → [coupling.md](references/coupling.md).
4. **Code** — classes and functions: principles and the patterns that resolve a named force → [principles.md](references/principles.md), [patterns.md](references/patterns.md).

A new service is a System decision; a new feature in an existing app usually starts at Modules; a refactor of one class stays at Code.

## Core rules
1. **Codebase first.** Before proposing anything, read how this repository already solves similar problems: directory layout, the dependency graph, sibling features, base classes, ADRs (`docs/adr/`), `GLOSSARY.md`, change hotspots. Name the current style (or say it is mixed/absent, with evidence). The existing approach is the default; deviating requires naming the concrete problem it removes and why the existing approach fails here.
2. **Research the best fit.** Name the problem class and research how it is best solved today — canonical sources, current framework guidance, real codebases — scaled to how reversible the decision is ([research.md](references/research.md)). The catalogs here are a shortlist, never the limit; every claim a decision rests on has a link or is labeled as judgement.
3. **Name the force before the pattern.** "We branch on payment provider type in 4 places" justifies a strategy or registry; "it is more SOLID" justifies nothing. Every style, layer, module, interface or pattern resolves a force the system actually has.
4. **Simple ≠ simplistic.** The best design needs the fewest concepts to do the job correctly and keeps the next likely change cheap. No abstraction for a single implementation (a test fake counts as a second); duplication across 2 places is fine, at 3 consider extracting — unless it is the same domain rule.
5. **Options, not a verdict.** Always include **Option 0: the simplest thing** (extend the existing code in place, or the existing pattern as-is), plus 1–2 genuinely different alternatives ("design it twice"). Score them against the forces ([tradeoffs.md](references/tradeoffs.md)), recommend one with a confidence and its reversibility. The user decides.
6. **Make irreversible decisions explicit.** DB schema, public API and event contracts, data ownership, new infrastructure or a style change get an ADR (`docs/adr/NNNN-title.md`); a reversible choice goes in the design's decisions section.
7. **Keep it true.** Every boundary-level decision gets a fitness function in the repo's stack (dependency rules, contract tests, budgets).
8. **Over-engineering is a defect too.** In review, flag patterns that add indirection without removing a named force.

## Design-time checklist
Run the steps for the levels the decision touches.
- **Ground:** current style and shape with evidence; constraining ADRs; hot spots; the stack and its versions.
- **Forces:** quality attribute scenarios (measurable), what is likely to change (evidence, not speculation), what is volatile, what must be tested in isolation, team constraints.
- **System:** parts and data ownership, sync vs async, consistency boundaries; a C4 context/container diagram when parts are added or changed.
- **Style:** the layers/slices and the dependency rule; domain logic depends on abstractions it owns, I/O and frameworks sit behind adapters.
- **Modules and files:** module map (responsibility · public surface · depends on), package by feature/domain, no cycles, dependencies toward stability, only weak connascence across seams, the resulting file tree in the repo's idiom.
- **Code:** single responsibility per unit, ownership by GRASP, each pattern with its force; name things in the domain's vocabulary, not pattern names (`ShippingCostCalculator`, not `PricingStrategyFactory`).
- **Verification:** test seams, which collaborators get fakes, the first red test; the fitness function.

## Review-time checklist
- **Responsibilities:** one reason to change per unit; no business logic in controllers, views, callbacks or components.
- **Dependency direction:** no domain/core unit imports a framework, SDK, ORM, HTTP client or UI; no import the project's style forbids (an FSD layer importing a higher layer, a slice importing a sibling's internals, a pack reaching into another's private constants).
- **Relationships:** no new cycles; no deep import past a module's public surface; no shared tables, leaked implementation types or flag parameters across a seam; no `a.b.c.d` reach-through.
- **Placement:** new code lives where the codebase puts that kind of thing, in the module that owns its concept — not in `utils/`/`common/`/`helpers/`.
- **Interfaces:** explicit inputs and outputs; no hidden reliance on globals or context it does not need.
- **Change cost:** the next likely change (new payment provider, new field, new step) touches one place, not many.
- **Pattern fit:** every pattern resolves a force present in the code; an interface with a single implementation and no test double is a hypothetical seam; abstractions that grow per-caller flags are the wrong abstraction.
- **Design drift:** when the spec has a `## Design`, units, boundaries and patterns match it (or the Design was updated in the same change).

## References (load lazily: only what the decision needs)
| File | Covers |
|---|---|
| [references/research.md](references/research.md) | How to research the best-fitting style or pattern: problem class, depth by reversibility, source order, what to extract, recording |
| [references/system.md](references/system.md) | Quality attribute scenarios, C4, sync vs async integration, data ownership, architecture anti-patterns, fitness functions |
| [references/styles.md](references/styles.md) | Layered, hexagonal, clean, FSD, vertical slice, modular monolith, DDD, event-driven/CQRS/ES, MVC/MVVM, pipes and filters, microkernel, serverless, microservices, BFF, micro-frontends, choosing a style |
| [references/coupling.md](references/coupling.md) | Package principles, connascence, coupling smells, when abstractions earn their place, file/folder organization, reading a codebase's structure |
| [references/patterns.md](references/patterns.md) | Patterns by force with overuse signs: structural, behavioral, creational, application/data, distributed, concurrency, frontend, testing, change and migration |
| [references/principles.md](references/principles.md) | SOLID, GRASP, KISS/YAGNI/DRY, deep modules and the deletion test, LoD, CQS, robustness |
| [references/tradeoffs.md](references/tradeoffs.md) | Forces, ATAM-lite, confidence, reversibility, ADR write/skip, fitness functions per stack, refactoring strategy |

**Stack notes** — read only the ones for the repo's stack:
| File | Covers |
|---|---|
| [references/stacks/rails.md](references/stacks/rails.md) | Rails building blocks, "when NOT to abstract", layering, data and migrations; deeper: the `layered-rails` skill |
| [references/stacks/frontend-react.md](references/stacks/frontend-react.md) | React component and logic patterns, state placement, testing shape |
| [references/stacks/frontend-structure.md](references/stacks/frontend-structure.md) | Frontend folder structure: type-based, feature-based, FSD, atomic design, boundary enforcement |
| [references/stacks/other-stacks.md](references/stacks/other-stacks.md) | Backend services, Go, other UI frameworks, mobile, data pipelines, Python/CLIs, infrastructure as code |

## Output for a design proposal
1. Problem, forces and constraints (from the spec)
2. How the codebase does this today (`path:line`)
3. Research: problem class, candidates with sources
4. Options (Option 0 + 1–2) with the +/0/− table
5. Recommendation: why, confidence, reversibility
6. Resulting structure per zoom level touched: files, responsibilities, interfaces, data flow
7. Testing shape and fitness functions
8. Risks: data, migration, performance, security, rollout
9. ADR needed? (yes/no + draft if yes)
