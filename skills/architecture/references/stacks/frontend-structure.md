# Frontend project structure (files and folders)

First detect what the repo uses (`src/` layout, ESLint import rules, path aliases) and follow it. Propose a structural migration only as a separate, phased effort with an ADR.

| Approach | Shape | Use when | Don't when |
|---|---|---|---|
| **Type-based** (`components/ containers/ hooks/ services/ utils/`) | Grouped by technical kind | Small apps (most current repos look like this) | 20+ features: features get scattered across folders |
| **Feature-based / bulletproof-react** | `features/<name>/{api,components,hooks,types}` plus shared `components/ hooks/ lib/`, with one-way imports `shared → features → app` enforced by ESLint | Medium to large apps. The simplest step up from type-based. | A tiny app |
| **Feature-Sliced Design (FSD v2.1)** | Layers `app > pages > widgets > features > entities > shared`; slices by domain; segments `ui/ model/ api/ lib/ config`; public API via `index.ts`; imports only to strictly lower layers; no cross-imports between slices on one layer (narrow `@x` exception) | Large apps, several devs, a need for enforced boundaries (Steiger linter) | Small apps, or a team without buy-in. **Start with `pages/` + `shared/`, and extract to features/entities only when code is (1) used in several places now, (2) has its own reason to change, and (3) has a focused boundary.** The widgets layer is discouraged. Canonical guide: fsd.how (check the current version before relying on details). |
| **Atomic design** (atoms → molecules → organisms → templates → pages) | Component taxonomy | **Inside a design system / Storybook** (e.g. an in-house component kit) | As the folder structure of an app: it splits features across levels |
| **Colocation** | Component, hook, test, story and styles side by side | Always, within any of the above | n/a. Promote code to shared only when it gets a second consumer. |
| **Monorepo packages** (design system, shared config, API client) | `packages/*` with explicit versions and boundaries | Several apps share UI or clients | One app |

## Boundary enforcement (fitness functions)
- `eslint-plugin-boundaries`, `eslint-plugin-import` (`no-restricted-paths`, `no-cycle`), `dependency-cruiser`, Steiger (FSD).
- Path aliases (`@/features/...`) together with a "public API only" rule: no deep imports into another feature's internals.
