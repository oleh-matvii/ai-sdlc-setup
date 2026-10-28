**Type:** enh
**Size:** M
**Status:** Approved (team lead, 2026-09-14)

# Order export: CSV format

> Illustrative spec-lite (M) for an invented example app. File paths and line numbers are made up.

## Current behavior
`OrdersController#export` (`app/controllers/orders_controller.rb:24`) accepts `format=pdf|xlsx` and delegates to `OrderExporter::Pdf` / `OrderExporter::Xlsx` (`app/exporters/order_exporter/`). Both take the store's orders filtered by `date_from`/`date_to` and render the columns number, customer, status, total, created at. Any other `format` returns `422` with `unsupported format`.

## Target behavior
`format=csv` returns a CSV file with the same columns and the same date filter as the other two formats. The other formats are unchanged.

## Acceptance criteria (EARS)
- AC1. WHEN a manager requests an export with `format=csv`, THE SYSTEM SHALL respond with `text/csv` and an attachment named `orders-<YYYY-MM-DD>.csv`.
- AC2. WHEN a CSV export is generated, THE SYSTEM SHALL write a header row and one row per order, with the columns in the same order as the XLSX export.
- AC3. WHEN `date_from` and/or `date_to` are given, THE SYSTEM SHALL include only orders created within that range, as the PDF and XLSX exports do.
- AC4. IF the filtered set is empty, THEN THE SYSTEM SHALL return a CSV with the header row only (not an error).

## Code paths
- `app/exporters/order_exporter/csv.rb` (new) — mirrors `OrderExporter::Xlsx`: `#call(orders)` returns the file body; uses Ruby's `CSV`.
- `app/controllers/orders_controller.rb` — add `csv` to the format map; no logic in the controller.
- Existing pattern: one class per format under `OrderExporter::`, selected by `OrderExporter.for(format)`.

## Tests
- Pin first: `spec/requests/orders_export_spec.rb` — current PDF/XLSX responses, date filter and `422` for an unknown format.
- New: `spec/exporters/order_exporter/csv_spec.rb` (AC2, AC4); request specs for `format=csv` (AC1, AC3).

## Tasks
- [ ] 1. Current-behavior request specs for PDF/XLSX export and the unknown-format `422` (covers: baseline)
- [ ] 2. `OrderExporter::Csv` with header and rows, empty set gives header only (covers: AC2, AC4)
- [ ] 3. Register `csv` in `OrderExporter.for` and the controller format map, content type and filename (covers: AC1, AC3, depends on: 2)
