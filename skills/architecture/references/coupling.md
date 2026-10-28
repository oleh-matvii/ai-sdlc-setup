# Relationships and abstractions

How units relate (coupling, dependency direction, cycles) and when an abstraction earns its place. Use at every zoom level: between services, packages, folders, classes, functions.

## Dependency rules between packages/modules (Robert C. Martin)

- **ADP — Acyclic Dependencies**: the module graph has no cycles. A cycle means the modules release, test and change as one; break it with dependency inversion (move the interface to the depending side) or by extracting the shared part.
- **SDP — Stable Dependencies**: depend in the direction of stability. A module many others depend on (high fan-in) must change rarely; a volatile module depends on stable ones, never the reverse. Instability I = fan-out / (fan-in + fan-out).
- **SAP — Stable Abstractions**: the more stable a module, the more abstract it is (interfaces, types, policies); concrete, volatile detail lives in unstable leaf modules.
- **CCP — Common Closure**: things that change together for the same reason live together (SRP for modules).
- **CRP — Common Reuse**: things not used together don't live together; a caller should not depend on what it doesn't use (ISP for modules).
- **REP — Reuse/Release Equivalence**: what is reused is released and versioned as one unit.

## Connascence — the strength of a relationship

Two units are connascent when changing one forces a change in the other. From weakest to strongest; refactor toward the weaker forms, and keep strong forms local (inside one unit).

- **Static**: name → type → meaning (magic values shared by convention) → position (argument order) → algorithm (both sides must hash/encode the same way).
- **Dynamic**: execution order → timing → value (values must change together) → identity (must reference the same instance).
- **Rules**: strength × distance × degree. Strong connascence across a module seam is a defect; the same inside one function is fine. Positional → named parameters/objects; meaning → named constants/enums; algorithm → one shared implementation.

## Coupling smells across seams

- **Shared database / shared tables** between modules or services — integration through storage, the strongest cross-module coupling.
- **Leaky abstraction** — callers must know implementation details (ORM entities in API responses, SQL errors in domain code, provider error codes in UI).
- **Chatty interface** — many fine-grained calls to do one thing; often a missing facade or a wrong seam.
- **Temporal coupling** — callers must call `init()` before `run()`; encode the order in the interface (constructor, builder, state machine).
- **Control coupling** — a flag parameter that switches behavior inside the callee; split into two operations or use Strategy.
- **Stamp coupling** — passing a whole object where two fields are used; narrows ISP.
- **Distributed monolith** — services that must deploy together or call each other synchronously in chains.

## Abstractions

- **An abstraction earns its place** when it hides a decision that is likely to change (information hiding, Parnas), concentrates complexity (deep module, `principles.md`), or gives a second implementation a home (a test fake counts). Otherwise inline it.
- **Rule of three**: duplicate once, abstract on the third occurrence — unless the duplicates encode the same domain rule (then extract immediately; DRY is about knowledge, not text).
- **Wrong abstraction costs more than duplication** (Sandi Metz): an abstraction that grows flags and special cases per caller is re-inlined and re-extracted along the real seam.
- **One level of abstraction per unit**: a module speaks either domain language or mechanism language (HTTP, SQL, files); mixing them is a missing layer.
- **Name abstractions after the domain**, from `GLOSSARY.md` when it exists — never `Manager`, `Helper`, `Util`, `Base`, `Common`, `Handler` alone.
- **Interfaces are owned by their consumer** (DIP): the domain defines `PaymentGateway`; the Stripe adapter implements it.

## File and folder organization

- **Package by feature/domain, not by technical type** for anything beyond a small app: `orders/` (with its handler, service, repository, tests) beats `controllers/`, `services/`, `repositories/` spread across the tree. Technical-type folders are fine inside a feature.
- **Public surface per folder**: each module folder exposes an entry point (`index.ts`, `__init__.py`, Go package API, Java package-private by default) and keeps internals private; callers never deep-import.
- **Co-locate** tests, fixtures, styles and types with the code they belong to.
- **No dumping grounds**: `utils/`, `common/`, `shared/`, `helpers/` hold only code with no domain meaning and no dependencies upward; domain logic that drifted there moves to its owner.
- **File = one concept**: one primary export/class per file, named after it; a file with unrelated exports is two files.
- **Depth over breadth**: a folder whose files are all tiny pass-throughs is a shallow module; merge them.

## Reading an existing codebase's structure

- **Dependency graph**: dependency-cruiser / madge (JS/TS), pydeps / import-linter (Python), `go mod graph` + `go list -deps` (Go), jdeps / ArchUnit (JVM), NDepend (.NET). Look for cycles, wrong-direction edges and god modules (very high fan-in and fan-out).
- **Change hotspots**: `git log --format= --name-only | sort | uniq -c | sort -rn | head` — files that change most are where structure pays off first; files that always change together (change coupling) belong together or behind one seam.
- **Size and complexity outliers**: the largest files and functions are candidates for split by responsibility.
