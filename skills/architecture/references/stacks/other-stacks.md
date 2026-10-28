# Stack notes: other stacks

Apply the same rules in each stack's idiom. For Rails and React see `rails.md`, `frontend-react.md`, `frontend-structure.md` in this folder.

- **Backend services (Node, Java/Kotlin/Spring, .NET, Go, Python):** controllers/handlers translate transport ↔ use case and hold no domain rules; transactions are owned by the application layer; ORM entities stay out of the API contract; every remote call has a timeout.
- **Go:** small interfaces defined by the consumer; accept interfaces, return structs; packages by domain, not by layer type (`models/`, `utils/`).
- **Other UI frameworks (Vue, Svelte, Angular):** no fetch/SDK/storage calls in templates or component callbacks — they go through composables/services; derived values are computed, not mirrored into state; components stay presentational, containers/composables coordinate. FSD and feature-based layouts apply as in `frontend-structure.md`.
- **Mobile (iOS/Android/Flutter/React Native):** UI state in a view-model/store, data behind repositories, offline and sync logic in its own unit, never in screens.
- **Data pipelines:** each stage a pure transform with explicit input/output schemas; I/O only in sources and sinks; reruns idempotent.
- **Python / scripts / CLIs:** module-level code only wires; logic lives in functions that receive their I/O.
- **Infrastructure as code:** modules by environment-independent responsibility; environments differ by inputs, not copies; state and blast radius per stack; production changes only with explicit permission.
