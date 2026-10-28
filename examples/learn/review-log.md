# Review log: example-app

2026-09-01 | state-contrast-unchecked | promoted | - | REVIEW.md | 2 occurrences, 2026-08-11..2026-08-27
2026-09-03 | missing-docs-verify-stamp | review | feat/proj-101-order-export | docs/orders.md:12 | order export topic changed but its verified-on marker was not refreshed
2026-09-05 | excess-explanatory-comments | user | feat/proj-101-order-export | app/exporters/order_exporter/csv.rb:8 | comments restate each line of the row builder instead of explaining why
2026-09-10 | consumer-override-misses-states | post-done | enh/proj-112-card-variants | app/frontend/components/ProductCard.tsx:40 | consumer style override covers the default state only; hover and disabled keep the old colors
2026-09-16 | expected-state-reported-as-error | check | fix/proj-118-empty-search | app/services/product_search.rb:27 | an empty search result is logged and returned as an error instead of an empty list
2026-09-22 | symptom-patch-over-root-cause | user | fix/proj-124-total-rounding | app/models/order.rb:61 | rounded the displayed total instead of fixing the line-item sum that drifts
2026-09-29 | missing-docs-verify-stamp | review | enh/proj-131-order-filters | docs/orders.md:30 | filter section edited without refreshing the verified-on marker (second branch: rule candidate)
