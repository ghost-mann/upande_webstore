# Stock Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per variety+length stock allocations in Webstore Settings that cap what the webstore sells and are used up by webstore quotations/orders, plus a Low Stock Warning display mode.

**Architecture:** Allocation rows live on the Webstore Settings Single; consumption is an Entry log (one row per document+item) that is the source of truth for Taken. `services/stock.get_stock_qty` becomes allocation-aware, so the existing cart/checkout checks enforce it. doc_events on Quotation/Sales Order keep Entries in step with each document.

**Tech Stack:** Frappe v16, ERPNext v16, Python, Jinja, TypeScript bundle.

**Spec:** `docs/superpowers/specs/2026-11-18-stock-allocation-design.md`

## Global Constraints

- Default off; with `enable_stock_allocation = 0` every code path returns exactly what it returns today.
- Webstore documents = Quotation / Sales Order with `order_type = "Shopping Cart"`.
- Taken = sum of `Webstore Allocation Entry.qty` per item_code; never read Taken from the cached Single.
- Desk sync never throws; only customer checkout refuses.
- Tests run on `webstore-test.localhost`: `bench --site webstore-test.localhost run-tests --app upande_webstore --module <module>`.
- Commits: author/committer ghost-mann, no Claude co-author line.

## Review Focus

- Saving Webstore Settings from a form opened before an order was placed must not reset Taken (test: `test_settings_save_does_not_reset_taken`).
- Draft Sales Order made from a webstore quotation must not double count (test: `test_sales_order_from_quotation_moves_hold`).
- Quotation declared Lost via `db_set` releases (test: `test_lost_quotation_releases`).
- Template / spec line while switch on is not sellable (test: `test_template_not_sellable_when_on`).
- Allocation exceeding physical stock offers only the physical figure (test: `test_available_is_min_of_remaining_and_warehouse`).

---

### Task 1: Doctypes and settings fields

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_stock_allocation/` (child: `variety` Link Item reqd, `length` Data reqd, `item_code` Link Item read-only, `allocated` Float reqd, `taken` Float read-only, `remaining` Float read-only)
- Create: `upande_webstore/upande_webstore/doctype/webstore_allocation_entry/` (`reference_doctype` Link DocType, `reference_name` Dynamic Link, `item_code` Link Item, `qty` Float; System Manager perms; index on item_code and reference_name)
- Modify: `webstore_settings.json` — Modules tab, new section `stock_allocation_section` after `spec_source_summary`: `enable_stock_allocation` Check, `low_stock_threshold` Int, `stock_allocations` Table; `stock_display` options add `Low Stock Warning`. Same option on `webstore/webstore.json`.
- Modify: `webstore_settings.py` — `validate_stock_allocations()`: resolve item_code (variant of `variety` with any attribute value == `length`; throw listing valid lengths if none; throw if duplicate item_code), refresh taken/remaining from Entries. `on_update`: if switch turned on → `allocation.recount()`.

### Task 2: services/allocation.py + availability

**Interfaces (produces):**
- `enabled() -> bool`
- `row_for(item_code) -> frappe._dict | None` (fresh DB read: name, allocated)
- `taken(item_code) -> float`
- `remaining(item_code) -> float | None` (None = item has no row)
- `lock_and_check(lines: list[tuple[item_code, qty]]) -> None` (throws ValidationError "Only N left of X")
- `sync(doc) -> None`, `recount() -> None`, `reset() -> None`, `daily() -> None`
- `on_change(doc, method=None)`, `on_trash(doc, method=None)` hooks

`stock.get_stock_qty`: when enabled — template → 0; variant without row → 0; else `max(0, min(remaining, warehouse qty))`.
`stock.get_stock_info`: Low Stock Warning → `qty` and `show_qty` only when `0 < qty <= threshold`, plus `low: bool`.

Tests `tests/test_stock_allocation.py`: off = unchanged; no row = 0; min of remaining & warehouse; template 0; checkout takes; second checkout over remaining refused; desk edit of quotation qty re-syncs; cancel releases; Lost releases; SO from quotation moves hold; SO cancel restores quotation hold; settings save keeps Taken; recount picks up pre-existing open quotation; reset clears; low-stock display.

### Task 3: Wire checkout, hooks, scheduler, UI

- `api/checkout.place_order`: after `_assert_available`, call `allocation.lock_and_check([(row.item_code, row.qty) ...])` when enabled.
- `hooks.py`: doc_events Quotation/Sales Order `on_change` + `on_trash`; `scheduler_events.daily` → `allocation.daily`.
- Templates (`store.html`, `webstore_product.html`) and `webstore.bundle.ts`: when `stock.low` show "Only N left".
- `webstore_settings.js`: buttons Recount / Reset taken under the allocations grid (whitelisted `recount_allocations`, `reset_allocations`, System Manager).
- Build assets, run full module tests, commit.
