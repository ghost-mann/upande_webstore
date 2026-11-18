# Stock Allocation — design

Date: 2026-11-18 · Status: draft for approval · Branch: `main`

## Why

Mona Flowers' coldstore holds tens of thousands of stems per variety
(Ever-Red ~30.7k, Athena ~28.7k across 9 lengths on 2026-11-18). Mona does
not want the webstore to sell from the whole coldstore. Staff decide how many
stems of each variety **at each length** the webstore may sell, and webstore
orders use that allocation up.

It is built as a general, default-off setting in upande_webstore, so other
sites (Kaitet etc.) are unaffected until they switch it on.

## Goals

- A table in Webstore Settings: variety + length → allocated stems.
- When the switch is on, a length is sellable on the webstore only up to
  what remains of its allocation (and never more than is physically in the
  configured webstore warehouses).
- Webstore checkouts use the allocation up. Taken follows each webstore
  document as it currently stands (staff edits, cancel, Lost, Expired,
  delete all adjust it). Staff on the desk may exceed the allocation.
- A new stock display mode, **Low Stock Warning**: "In stock" above a
  threshold, "Only N left" at or below it, "Out of stock" at zero — so buyers
  see scarcity without ever seeing coldstore totals.

## Non-goals

- No per-customer or per-customer-group allocations.
- No time-boxed allocations / automatic period rollover (staff top up or reset).
- No change to how desk-created quotations or orders behave; only documents
  created by webstore checkout consume allocation.
- No per-store (multi-storefront) allocation: switch, threshold and table are
  site-wide on the Single and apply to every store on the site.
  `stock_display` remains per-store overridable.

## Anti-goals

- The storefront must never show more than the allocation's remaining
  figure while the switch is on (not on the page, not in API responses).
- Two simultaneous checkouts must not both take the same last stems.
- With the switch off, behaviour is byte-for-byte what it is today.

## Approaches considered

- **A. Running counter per row (chosen by the user).** Each row keeps
  Allocated / Taken / Remaining. Checkout adds to Taken under a row lock;
  cancel / Lost / Expired releases. A "Recount" button rebuilds Taken from
  open webstore documents to repair any drift.
- **B. Compute live.** Store Allocated + a "counts from" date and sum webstore
  documents on every check. No drift, but a sum query per page view, no lock
  to stop overselling, and staff can't see Taken at a glance.

## Design

### Settings (Webstore Settings, new "Stock Allocation" section)

- `enable_stock_allocation` (Check, default 0).
- `low_stock_threshold` (Int, default 0) — used by the Low Stock Warning mode.
- `stock_display` gains a third option: `Low Stock Warning`
  (existing: `In/Out Badge`, `Exact Quantity`).
- `stock_allocations` (Table → new child doctype **Webstore Stock Allocation**):
  - `variety` (Link Item, template items only — `has_variants=1`)
  - `length` (Data/Link to the variant's length attribute value, e.g. `60cm`)
  - `item_code` (Link Item, read-only, resolved from variety + length on save;
    save is refused if no variant matches)
  - `allocated` (Float, stems)
  - `taken` (Float, read-only)
  - `remaining` (Float, read-only = allocated − taken, may be shown negative
    if staff lower Allocated below Taken)
  - Duplicate item_code rows refused on save.
- Buttons: **Recount** (rebuild Taken from open webstore documents) and
  **Reset taken** (zero all Taken, for a new allocation period; confirm dialog).

Length resolution: the variant whose attribute value for the length attribute
equals `length`. Mona's attribute is `Stem Length`; the code finds the length
attribute the same way the store's existing length picker does.

### Availability

`services/stock.get_stock_qty(item_code)` is the single source of "available"
already used by the product page, cart (`api/cart.py` `_validate_stock`) and
checkout (`api/checkout.py`). With the switch on:

- variant with an allocation row → `min(remaining, warehouse qty)`, floored at 0
- variant without a row → 0 (not for sale; table is the full list of what sells)
- template → max over its variants (unchanged rule)

Because cart and checkout already refuse qty > available, the limit is
enforced with no new checks there.

### Consumption (Taken) — follows each document as it stands

New doctype **Webstore Allocation Entry** (log, not in a workspace):
`reference_doctype`, `reference_name`, `item_code`, `qty`. One Entry per
(document, item). Taken on a row = sum of Entry qty for its item_code.

**Which documents count** ("webstore documents"):
- Quotations and Sales Orders with `custom_webstore` set.
- A Sales Order made from a webstore quotation also counts:
  `services/conversion.carry_webstore_fields` additionally carries
  `custom_webstore` across (today it is dropped by the mapper).

**What a document holds** (its "wanted" qty per item_code, summed over lines):
- Quotation: its lines while docstatus ≤ 1 and status not in
  Ordered / Lost / Expired / Cancelled; otherwise nothing (once Ordered, its
  Sales Order holds the stems instead). Partially Ordered keeps holding its
  full lines (conservative; may over-count briefly).
- Sales Order: its lines while not cancelled and status not Closed;
  otherwise nothing.
- Deleted document: nothing.

**Sync(doc)** — runs on checkout and on every on_update / on_submit /
on_cancel / on_trash / on_update_after_submit of a webstore document, and
for quotations whose status changes (Lost via declare_enquiry_lost,
Expired via ERPNext's daily job — a daily task here syncs newly expired
quotations). It diffs wanted vs the document's existing Entries, and for each
changed item_code locks the allocation row (`SELECT … FOR UPDATE`), applies
the difference to Taken and upserts/deletes the Entry. Only items that have
an allocation row are tracked.

- **Checkout (customer):** before creating the document, for each line lock
  the row and refuse checkout with "Only N left of Athena 60cm" if
  remaining < qty; then insert the document and Sync it — same transaction,
  so the lock holds until commit.
- **Desk (staff):** Sync never refuses. Staff may raise quantities or add
  lines past the allocation; Remaining goes negative and the storefront shows
  that length as out of stock until topped up.
- Delivery does not touch allocation; stock leaving the warehouse already
  reduces the physical figure.

**Recount** (button, also run automatically when the switch is turned on):
rebuild every Entry by running Sync over all open webstore documents — so
orders already open when the switch goes on are counted from day one — then
recompute Taken per row.

**Reset taken:** deletes all Entries and zeroes Taken (new allocation period;
already-open orders stop counting). Confirm dialog says so.

### Display

`get_stock_info` with `stock_display = Low Stock Warning` returns
`{in_stock, qty: N only when 0 < N ≤ threshold, low: bool}`. Templates show
"Only N left" / "In stock" / "Out of stock" accordingly. API responses never
carry qty above the threshold in this mode.

## Decided with the user

- General default-off setting, built on `main` (not a client branch).
- Allocation per variety **and length**; a length without a row is not sold.
- Display: new Low Stock Warning mode.
- Orders use up the allocation (approach A, running counter + Recount).
- Taken follows the document as it currently stands; staff may exceed.

## Builder's calls (not discussed with the user)

- Customer-specification lines (`enable_customer_specs`) use the row of the
  spec's `price_length` variant; while allocation is on, a spec with no single
  length cannot be ordered ("this specification can't be ordered online").
  Mona has specs off.
- Exact Quantity mode with the switch on shows min(remaining, warehouse) —
  never more than the allocation.
- Switch, threshold and table are site-wide (see Non-goals).

- Length is chosen per row from the variety's existing lengths (no free text).
- Allocation and Taken are in stems (stock UOM).
- Lowering Allocated below Taken is allowed; Remaining shows negative and
  the length is out of stock.
- Tests on webstore-test.localhost; run against erpnext ≥ 16.51 behaviour
  where pricing is touched (live is 16.51).
