# Trade-offs, decisions and refactoring strategy

## Forces first
Before options, write down:
1. **What varies, and how likely is it?** List real, scheduled or historically frequent changes (`git log --format= --name-only | sort | uniq -c | sort -rn | head` for hot spots). Hypothetical reuse doesn't count.
2. **Top 2–3 quality attributes** the change stresses. Pick from the ISO 25010 list: maintainability (changeability, testability), performance, reliability, security, usability/accessibility, compatibility, portability.
3. **Constraints:** deadline, team familiarity, existing patterns, data volume, external contracts.

## ATAM-lite (comparing options)
For each top quality attribute, write one concrete scenario ("add a new payment provider in under 1 day touching 1 module", "the checkout page p95 stays under 1.5s at 3x load"). Score each option against each scenario (+/0/−) and note the risks and sensitivity points. Always include **Option 0: the simplest thing** (do nothing, or extend the existing code in place).

## Confidence of a recommendation
- **Strong:** clear current forces, a precedent in the codebase, low risk.
- **Worth exploring:** plausible, but it needs a spike or prototype first.
- **Speculative:** depends on predicted change. Default to not doing it now. Record it as a follow-up.

## Reversibility
- **Two-way door** (easy to undo: internal structure, naming, a private module): decide fast and keep moving.
- **One-way door** (schema, public API or events, data ownership, new infrastructure, a vendor lock-in): slow down, consider at least two options, write an ADR, and plan a migration or rollback path.

## ADR: write or skip
| Write an ADR | Skip it |
|---|---|
| One-way-door decisions, new architectural styles or boundaries, a new core library or framework, deviation from an established codebase pattern, decisions likely to be re-argued | Local refactors, naming, choices fully covered by existing conventions, easily reversible experiments |

Format (`docs/adr/NNNN-title.md`): Status (Proposed / Accepted / Superseded by NNNN), Context, Decision, Options considered (with why rejected), Consequences (positive, negative, follow-ups). One-line alternative: *Y-statement*, "In the context of X, facing Y, we decided Z to achieve Q, accepting D." Respect existing ADRs. Don't relitigate them without new friction.

## Fitness functions (make the decision enforceable)
Propose at least one for every boundary-level decision; otherwise the boundary erodes. Pick the tool of the repo's stack (more in `system.md` → "Fitness functions"):
- Ruby/Rails: packwerk (pack boundaries), ArchSpec (layer rules), custom RuboCop cops, `strong_migrations`.
- JS/TS: `eslint-plugin-boundaries`, `import/no-restricted-paths`, `import/no-cycle`, dependency-cruiser, Steiger (FSD), bundle-size budgets.
- Python: import-linter · JVM: ArchUnit · .NET: NetArchTest · Go: depguard / custom analyzers.
- Any stack: contract tests for external APIs and between services, performance budgets on critical paths.

## Refactoring strategy
- **Characterization tests first** (Feathers): pin the current behavior, including odd behavior, before changing the structure.
- **Seams:** find or create places to substitute behavior (injected collaborators, wrapper methods) to get legacy code under test.
- **Small steps, always green:** each step is behavior-preserving, committed and reviewable. The step list has "stop here if…" exits after each phase.
- **Techniques:**
  - Strangler Fig (gradual replacement);
  - Branch by Abstraction (a seam, then switch);
  - Parallel Change / expand-contract (zero-downtime schema and API changes);
  - Mikado Method (discover prerequisites by trying and reverting).
- **Fowler's catalog** (common moves): Extract Function/Class, Move Function, Replace Conditional with Polymorphism, Introduce Parameter Object, Replace Primitive with Object, Split Phase, Encapsulate Collection, Replace Temp with Query, Inline (to remove shallow layers).
- **Smells to look for:** long method, large class, long parameter list, divergent change, shotgun surgery, feature envy, data clumps, primitive obsession, repeated switches, speculative generality, message chains, middle man.
- **Scope by pain:** refactor hot spots (frequently changed and complex) first. Leave stable, ugly code alone unless the task touches it.
