# Researching architecture and patterns

Every non-trivial design decision starts with research. The catalogs in this skill are a starting shortlist and a summary, never the limit and never the final word: a pattern or style found in research competes on the same forces, and a catalog entry that a decision hinges on is checked against its canonical source.

## 1. Name the problem class
Turn the task into a class that others have solved before: "multi-tenant billing", "offline-first mobile sync", "high-volume event ingestion", "plugin system", "large frontend with many features", "per-provider integrations with divergent APIs", "long-running workflow with compensations". The class, not the feature name, is what you search for.

## 2. Scale the depth to the decision
| Decision | Depth |
|---|---|
| Unit-level pattern inside an existing style (strategy vs registry, a value object) | 1–2 sources; the codebase's own precedent counts as one |
| Module boundaries, a new seam, a new library for a core concern | the 2–3 strongest candidates, each sourced, compared on the forces |
| Style change, a one-way door (schema, public API/events, data ownership, new infrastructure) | the alternatives compared from several independent sources, including at least one real codebase or case study, plus "don't use when" for each |

Stop when the options and their trade-offs are clear; more sources are not better past that point.

## 3. Sources, in order of trust
1. **Canonical source of the pattern or style** — its own documentation or the original author: e.g. feature-sliced.design, microservices.io (Richardson), martinfowler.com (Fowler, PoEAA, refactoring), Alistair Cockburn (hexagonal), Eric Evans / DDD reference, Michael Feathers, Ousterhout (deep modules).
2. **Official framework / library docs at the repo's versions** — Context7 (`resolve-library-id`, then the docs query) first; WebFetch on the official docs otherwise. Note the version or date: methodologies and frameworks change (e.g. FSD v2.0 → v2.1).
3. **Architecture centers** — AWS Architecture Center / Well-Architected, Azure Architecture Center (cloud design patterns), Google Cloud Architecture Framework; refactoring.guru for GoF shapes.
4. **Real codebases of a comparable scale and stack** — read them with `gh api` (repository tree, key files): how they lay out modules, where the seam sits, what they enforce. Prefer mature, maintained projects.
5. **Experience reports** — conference talks and engineering blogs from teams that ran the pattern in production; use them for failure modes, not as primary definitions.

## 4. What to extract (only what the decision needs)
For each candidate:
- the **rules** that constrain the design (dependency rule, ownership, what may import what);
- the **forces** it resolves and the **cost** it adds;
- **known failure modes** and the **"don't use when"** conditions;
- how it **maps onto this repo**: its folders, vocabulary, existing building blocks, and what would have to change;
- the **enforcement** tool for this stack (fitness function).

## 5. Record it
- Cite a URL for every external claim the decision rests on; anything without a source is labeled as your judgement.
- Separate confirmed facts from assumptions; list open uncertainties.
- Write the findings to a research notes file next to the task's other artifacts (`research.md` in the spec's folder `docs/specs/<YYYY-MM-DD-topic>/`, or where the repo keeps such notes) so the spec's `## Design` links to it and the implementer reads the file instead of a retelling.
- Library *behavior* questions (how a gem/package/API works at a version, breaking changes) belong to the `api-researcher` agent's kind of research; architecture research is about which structure and patterns fit.
