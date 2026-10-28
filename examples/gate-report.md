# Example: review gate output

Illustrative output of `hooks/ai-sdlc/review_gate.py` for an invented branch (paths and findings are made up).

The hook's deny message starts with the chain line (also shown by `chain-status`):

```text
ai-sdlc [enh/proj-140-order-csv-export @ 3f9c2a1] enh/M: ✓spec ✓tests ✗review(1) ✓acceptance
```

The full report is written to `~/.claude/state/ai-sdlc/chain/<sha1 of repo root>/<branch>.report.md`:

````markdown
# ai-sdlc review: enh/proj-140-order-csv-export @ 3f9c2a1 (base 8b04d7e)

### code-reviewer: changes_requested
The CSV exporter follows the existing per-format pattern; the export action is missing the store scope.
- **major** `app/controllers/orders_controller.rb:31` [missing-authz-scope]: `Order.where(...)` is not scoped to the current store, so a manager can export another store's orders → use `current_store.orders` as the PDF/XLSX branches do
- **minor** `app/exporters/order_exporter/csv.rb:14` [inconsistent-date-format]: `created_at` is written with `to_s` while XLSX uses ISO 8601 → use `iso8601`

### acceptance-checker: ready_with_followups (criteria: docs/specs/2026-09-14-order-csv-export/spec.md, design: no_spec)
All four criteria are covered by request and exporter specs; the authorization gap is the reviewer's finding.
- [done] AC1: `spec/requests/orders_export_spec.rb:58` checks `text/csv` and the attachment filename
- [done] AC2: `spec/exporters/order_exporter/csv_spec.rb:12` checks the header and column order
- [done] AC3: `spec/requests/orders_export_spec.rb:74` checks the date range
- [done] AC4: `spec/exporters/order_exporter/csv_spec.rb:30` checks the header-only file
- verify: open the exported file in a spreadsheet app once to confirm the encoding of non-ASCII customer names
````
