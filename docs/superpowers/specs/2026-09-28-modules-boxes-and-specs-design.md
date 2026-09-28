# Modules: Box Packing and Customer Specifications

Supersedes `2026-09-17-customer-specifications-design.md`, which was written
against an older `Specifications` schema (no header `box_type`, no primary /
substitute varieties, no validity dates) and was never built.

## Intent

The webstore ships to many projects. Farm-specific business features must be
**modules**: one switch each in Webstore Settings, off by default, and when off
they add nothing — no settings clutter, no UI, no routes, no reads of another
app's doctypes. Two modules now:

- **Box Packing** — the buyer picks a box per line from a table of boxes kept in
  Webstore Settings, sees box fill at checkout, and the Sales Order records it.
- **Customer Specifications** — a signed-in customer sees *their own* packing
  specs (the packhouse's `Specifications`) behind a "My specifications" switch on
  the store and orders against them. Nobody else sees them.

Success: on webstore.localhost, with both modules on, a spec customer can browse,
see their price, order a spec by the box, order a mixed spec by variety, pick a
box for a plain line, see the box summary at checkout, and place an order whose
Sales Order lines carry the spec, box type, pack rate and box count. With both
modules off the store behaves exactly as before.

## Decisions (made while the owner was away — review these)

| Question | Decision |
|---|---|
| Module default | **Off.** A fresh project gets a plain store; existing sites keep their current `enable_box_packing` value |
| Box list source | **Boxes table in Webstore Settings** when it has rows; otherwise the existing site auto-detection (Box Type / Is Box Items) so Mona and Karen keep working unchanged |
| Spec source | A **doctype name in settings** (default `Specifications`) read against the `upande_packhouse` field contract; the module stays inert if that doctype is missing |
| How a spec is ordered | **Both.** By the box when the spec resolves to one variety at one pack rate; by variety otherwise |
| Substitutes | Only the **primary** variety per slot is offered; the packhouse substitutes as today |
| Spec pricing | None of its own — each line prices at the customer's normal rate for that variety (Kaitet: customer default price list; no Customer Pricing or Pricing Rules in use) |
| Mixed-box fill | **Not enforced** — the data cannot state a reliable per-box capacity; colour count and approved varieties are enforced instead |
| Spec publishing | None — a customer's active, in-date specs appear automatically when the module is on |

## Module mechanism

`theme/features.py` gains a third group, `modules`, alongside `storefront` and
`portal`:

```
_f("box_packing", "Box Packing", "modules")      # existing field, now in the registry
_f("customer_specs", "Customer Specifications", "modules")  # new, default 0
```

Because they are registry features, `features.require()` 404s their routes,
`features.guard()` refuses their API, and `webstore_features.<key>` hides their
UI — the same three layers every other flag already has. Both are per-store
tri-state (`PER_STORE_TRISTATE`), so one storefront can run specs while another
on the same site does not. Their settings sit in a **Modules** section of the
Features tab and every module-specific field is `depends_on` its switch.

`packing_enabled()` stays the one packing gate but reads the switch through the
registry.

Test isolation: `tests/utils.setup_webstore_settings()` currently sets every
feature to 1; it will set every feature to its **DocType default**, so modules
are off unless a test turns them on.

## Box Packing module

### Boxes table

New child doctype **Webstore Box** on Webstore Settings (`boxes`):

| Field | Type | Meaning |
|---|---|---|
| `box_name` | Data, reqd | What the buyer sees, and the line's box identifier |
| `pack_rate` | Int, reqd | Stems per full box |
| `box_type` | Autocomplete | Optional: the site's own box record (Box Type name or box Item) to write to the Sales Order |
| `disabled` | Check | Hidden from buyers without deleting the row |

Validation: `box_name` unique within the table, `pack_rate > 0`.

A desk button **Load boxes from this site** fills the table from the existing
auto-detected source (Box Type with `custom_stem_capacity`, or Items with
`custom_is_box`), mapping each record to `box_type` so orders keep writing it.

### Resolution

`packing.get_box_source()` gets a new first branch: a non-empty `boxes` table is
the source (`kind = "table"`). In table mode `get_box_types`, `get_pack_rate`,
`box_label`, `is_usable_box` and `get_unusable_box_types` read the table rows
held on settings, not the database. Otherwise resolution is unchanged.

### Writing boxes to documents

`_cart_items()` writes `custom_box_type` only when the target field is a Link and
the value exists in that Link's doctype: in table mode the value is the row's
`box_type` mapping; in source mode it is the line's box as today. Pack rate and
box count follow the existing `_writable()` rules.

### Checkout

The cart already has a per-line Box select, a per-box-type summary and disabled
buttons until boxes are full. Added:

- the box summary is repeated in the **checkout panel** above the order
  buttons, so the buyer sees box types, box counts and problems at the point of
  committing;
- spec lines show their spec's box as fixed text, not a select.

## Customer Specifications module

### Source contract (read-only)

`services/specs.py` is the only module that touches the spec doctype. It reads:

- header: `name`, `spec_name`, `customer`, `status`, `valid_from`, `expiry_date`,
  `box_type`, `box_assortment`, `min_colours_per_box`, `max_colours_per_box`
- `Spec Box Item`: `length`, `stems_per_bunch`, `bunches_per_box`, `pack_rate`
- `Spec Approved Variety`: `bunch_id`, `colour`, `variety`, `is_primary`

It never writes. Every read guards on the doctype existing and on the fields it
needs; a mismatch makes the module report "not available" in the desk rather
than error on the store.

### Whose specs

`pricing.get_customer()` (User → Contact → Customer). Visible specs:
`customer = <that customer>`, `status = Active`, `valid_from` blank or ≤ today,
`expiry_date` blank or ≥ today, at least one primary variety. Guests and
customers with no specs never see the switch.

### Ordering mode

Computed per spec:

- **By box** — exactly one primary variety and every box row shares one
  `pack_rate`. The buyer enters a number of boxes; the cart line is that
  variety, `qty = boxes × pack_rate`, tagged with the spec. On Kaitet this
  covers the mono specs whose box rows are duplicated once per approved variety.
- **By variety** — everything else. The card lists one row per primary
  variety (colour, variety, rate); the buyer enters stems per row and adds them
  together. Rules:
  - Mono Box with one shared `pack_rate`: each variety line must be whole boxes
    at that rate (a mono box holds one variety).
  - Otherwise (Mixed Box, or mono with differing rates): box fill is not
    enforced; the number of distinct colours ordered under the spec must lie in
    `[min_colours_per_box, max_colours_per_box]` when those are set.

### Cart

`Webstore Cart Item` gains `specification` (Data). The line key becomes
`(item_code, specification)`; blank specification is today's line. The cart
endpoints (`update_qty`, `remove_item`, `set_box_type`) take an optional
`specification`, so existing callers are unchanged. New endpoints in
`api/specs.py`, all `guard("cart", "customer_specs")`:

- `get_my_specs()` — the customer's orderable specs with mode, box, rows, rates
- `add_spec(specification, boxes=None, lines=None)` — box mode takes `boxes`;
  variety mode takes `lines = [{item_code, qty}]`

Server-side on every add and at checkout: the spec belongs to the session's
customer, is visible (active, in date), and each `item_code` is a primary
variety of it. A crafted call for another customer's spec is refused with the
same "not available" message as an unknown spec.

Spec lines take their box from the spec (`box_type`, rate as above), never from
the buyer; `set_box_type` refuses a spec line. Spec varieties need not be
published Webstore Products — the spec is the authorisation — but must have a
price above zero in the customer's price list to be offered.

### Packing arithmetic

`group_by_box_type()` keys spec lines by `("spec", specification)` and plain
lines by box as today. A spec group carries its own rule: whole boxes per line
(mono, one rate), or no fill check plus the colour range. `find_problems()`
reports spec problems by spec name, e.g. *"CM13 MIX 52CM: choose between 4 and 4
colours; you have 3."*

### Checkout output

`_cart_items()` writes `specification` → `Sales Order Item.custom_line` (and the
Quotation Item equivalent when present) through `_writable()`; the spec's box
type → `custom_box_type` under the Link-exists rule; pack rate and box count
where known. `_has_mixed_boxes()` is 1 when any Mixed Box spec is ordered or a
plain line does not fill whole boxes.

### Store UI

When the module is on and the customer has specs, the catalogue header shows a
two-way switch **All products | My specifications (N)** (`?view=specs`). The specs
view lists one card per spec: name, box type, mode label ("by the box, 400 stems
per box" or "by variety, 4 colours"), and either a boxes input or a table of
primary varieties with stem inputs, plus one Add button.

## Error handling

| Case | Behaviour |
|---|---|
| Module on, spec doctype missing | Store shows no switch; desk shows "Specifications doctype not found" |
| Spec for another customer / expired / inactive | "This specification is not available." |
| Variety not a primary of the spec | "{spec}: {variety} is not an approved variety of this specification." |
| Variety has no price | Row not offered; spec hidden if no row remains |
| Box mode, boxes ≤ 0 | "Enter at least one box." |
| Colour count out of range | reported in the cart and blocks checkout |
| Box table row with pack rate 0 | Rejected on save |

## Testing

Unit (run anywhere; spec tests skip when the spec doctype is not installed):

- `test_modules.py` — both modules off by default; off ⇒ spec API refused and
  store shows no switch; per-store override.
- `test_box_table.py` — table beats auto-detection; disabled / zero rows
  excluded; labels and rates from the table; `box_type` mapping written to the
  Sales Order only when it exists in the Link target.
- `test_specs.py` — visibility (own, active, in date), ordering mode rule,
  cross-customer refusal, non-primary refusal, box-mode quantity, colour range,
  `custom_line` on the Sales Order.
- Existing packing / checkout / transfer suites stay green.

End to end on webstore.localhost, with `upande_packhouse` installed and a few
real specs copied from Kaitet: log in as a spec customer, toggle My
specifications, add a by-box spec, add a mixed spec by variety, add a plain
product and pick its box, check the checkout panel summary, place a Sales Order,
and inspect its lines.

## Non-goals

- Writing to `Specifications` or any packhouse doctype.
- Letting the buyer pick substitutes, cut stage, sleeves or other packhouse
  instructions.
- Inferring a Mixed Box's per-box composition from its rows.
- Per-store box tables (the table is site-wide; packing on/off is per store).
