# React / TypeScript: code-level patterns

Prefer what the repo already uses: its component library (MUI, an in-house design system, Tailwind), data layer (react-query, redux), and form library (react-hook-form, formik). Don't introduce a second library for a solved problem. For folder structure (FSD, bulletproof-react, atomic design), see frontend-structure.md.

## Component API patterns: what → use when → don't when
- **Composition via `children` and slots:** the default for flexible layouts → instead of 10+ boolean or config props.
- **Compound components** (`<Tabs><Tabs.List/><Tabs.Panel/></Tabs>`, shared via context) → design-system components with related parts → overkill for a simple leaf component.
- **Controlled vs uncontrolled** (with `value`/`defaultValue` support) → reusable inputs → document which one a component is. Don't mix both silently.
- **Headless components / hooks** (behavior without styles: `useCombobox`, MUI Base) → the same behavior with different visuals → not for one-off UI.
- **Polymorphic `as` / `component` prop** → design-system primitives (Button as a link) → type it properly or skip it.
- **Prop getters / state reducer** (downshift-style) → highly customizable headless components → design-system level only.
- **Render props:** mostly replaced by hooks. Still fine for render-time injection (virtualized rows).
- **HOC:** legacy. Prefer hooks. Acceptable for cross-cutting wrappers required by libraries.
- **Container / presentational:** fetching and side effects in a container or hook, pure visual components separately → for Storybook-able, testable UI → don't apply it rigidly to tiny components.
- **Provider pattern (context):** shared, rarely changing values (theme, auth, feature flags, a compound component's internal state) → not for frequently changing data (re-renders). Split contexts by update frequency.
- **Error boundaries + Suspense boundaries:** placed per route or section → isolate failures and loading states.
- **Portals:** modals, tooltips, toasts. Handle focus trap and return focus.
- **Lazy loading / code splitting** (`React.lazy`, route-level) → heavy routes or widgets.

## Logic patterns
- **Custom hooks:** one concern each, with a typed and stable return (`useOrder(id)`, `useDebouncedValue`) → the deletion test applies (no pass-through hooks).
- **Query hooks + a query key factory** (`orderKeys.detail(id)`) → all react-query usage. Invalidation by key; optimistic updates with rollback for snappy mutations.
- **Form adapters:** a schema (zod or yup) is the single source of truth; field components wrap MUI via `Controller` → every form.
- **State machines** (useReducer with explicit states, or XState) → multi-step wizards and flows with guarded transitions → overkill for toggles.
- **Discriminated unions for async and UI state** (`{status:'loading'} | {status:'error', error} | {status:'success', data}`) → instead of several booleans.
- **Derived state:** compute during render. `useMemo` only when measured as expensive. Never sync derived data with `useEffect`.
- **Effects:** only to sync with external systems (subscriptions, DOM APIs). Not for fetching when react-query exists, and not for event-driven logic (put that in the handler).
- **Memoization** (`memo`, `useCallback`): only for measured re-render problems or referentially sensitive dependencies.

## State placement
| State kind | Where |
|---|---|
| Server data | **react-query**. Never copy it into redux or useState. |
| Form state | react-hook-form / formik with schema validation |
| URL-shareable UI state (filters, tab, page) | URL search params |
| Local UI state | `useState`/`useReducer` in the lowest common parent |
| Global client state (auth, flags, theme) | Context or the existing redux store, kept small. Zustand only if the repo already has it. |

## Principles applied to React
- **SRP:** if the name needs "And", split it. Watch components over ~200 lines.
- **ISP:** narrow props. Pass what is used, not whole objects "just in case".
- **Types:** no `any`, explicit props interfaces, `satisfies` for config objects. Parse API responses at the boundary (zod) when the contract is unreliable.
- **Accessibility is part of the design:** semantic elements, labels, roles, focus management, keyboard paths. jest-axe where the repo has it.

## Testing shape
- Testing Library through roles and labels, testing behavior. No implementation details, no whole-tree snapshots.
- Hooks via `renderHook`. Network mocked at the boundary (msw or fetch mocks, whatever the repo uses).
- Storybook stories for visual components where the repo uses Storybook (an in-house design system usually does).
- UI changes are verified visually (screenshot or browser) before being called done.

## Smells that justify a refactor
- Prop drilling more than 3 levels. Boolean props switching whole layouts.
- Server data duplicated in local or global state with a sync `useEffect`. `useEffect` chains.
- A component doing fetching, formatting and layout together, over ~300 lines.
- The same JSX copy-pasted 3+ times. Deep imports into another feature's internals.
