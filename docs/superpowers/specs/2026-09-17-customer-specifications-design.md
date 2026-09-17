# Customer Specifications in the Storefront

Let a customer order against their own packing specifications — the agreed
recipes a farm packs for them — alongside the open variety catalogue, so a
repeat buyer picks `CM13 MIX 52CM` instead of reassembling six varieties by
hand, and the resulting Sales Order is one the packhouse can already read.

## Problem

Kaitet runs `Specifications` (module `Upande Packhouse`): 345 records across 33
customers, plus 15 carrying no customer at all, each naming approved varieties, cut stage, defoliation, rubber band
placement, box build and consumables. `Sales Order Item.custom_line` already
links to it and 123 of 597 order lines (21%) carry one. The storefront knows
none of this.

Three properties of the live data shape the whole design.

- **A spec is a product, not a rule about a variety.** `(customer, variety,
  length)` fails to identify a spec 28.7% of the time; adding box type makes it
  worse (29.8%), adding colour barely helps (26.8%). Fuchsiana appears inside
  nine different FLOWER HUB mixes. 198 of the ambiguous combinations have specs
  that disagree on `pack_rate`, so guessing silently produces wrong box maths.
  The spec cannot be derived from a line — it must be chosen.

- **A spec order is a group of variety lines, not one SKU.** Real orders explode
  into one line per variety sharing a `custom_line`, each priced at that
  variety's own rate. 121 of 123 spec lines (98.4%) carry an item_code that is
  an approved variety of their spec. 107 of the 113 spec varieties already have
  selling prices. No spec needs a price of its own.

- **Box Type does not resolve on Kaitet.** `services/packing.py` picks `Box
  Type` only when it has `custom_stem_capacity > 0`. Kaitet's `Box Type` has no
  such field — four rows, all dimensions zero — and zero Items carry
  `custom_is_box`. So `get_box_types()` returns `[]` and packing is inert
  there today.

## Constraints

- **Specs narrow, never gate.** 660 of 693 customers have no spec. No spec means
  exactly today's storefront: open catalogue, existing rules. Guests too.
- **No dependency on `upande_packhouse`.** Every read of `Specifications` guards
  on the doctype existing, as `packing.py` already guards on `Box Type`. The app
  must install and migrate on a site that has never heard of a specification.
- **This app claims no doctype it did not create.** It reads `Specifications`; it
  never creates, migrates, writes or takes ownership of it, and it mints no
  Items into the 16,797-row master.
- **Deploying must change nothing.** Inert until spec products are published.
- **Never trust the client.** Spec ownership and variety membership are enforced
  server-side on every mutation, not merely hidden in the catalogue.

## Decisions

| Decision | Choice |
|---|---|
| Catalogue unit | A spec is a **kit** — one card that expands into priced variety lines |
| Spec pricing | **None.** Each line prices at its variety's existing Item Price |
| Storefront model | **Both** — a per-customer spec catalogue beside the open variety catalogue |
| Spec reference | **Data/Autocomplete, never Link** — the target doctype may not exist |
| Cart key | `(item_code, specification)` |
| Order shape | One line per variety, all tagged `custom_line` — what Kaitet already does |
| No-spec customers | Unchanged behaviour |

### Data model

`Webstore Product` gains `specification` (Data/Autocomplete) and `source_kind`
(Select `Item` | `Specification`, default `Item`). Existing rows keep today's
meaning with no patch.

`Webstore Cart Item` gains `specification` (Data), blank on ordinary lines. A
spec line is a variety line that remembers which kit it came from — one line
shape, one extra field.

`services/specs.py` is the only module that touches `Specifications`. It answers
four questions: which specs belong to this customer (via the existing
`pricing.get_customer()` User → Contact → Customer chain), what varieties a spec
approves with their bunches-per-box and length, what pack rate applies to a spec
at a length, and whether a variety is approved under a spec.

### Catalogue

Store filtering is untouched: spec products are `Webstore Product` rows, so
`_store_product_names()`, `_apply_store_filter()` and `is_in_current_store()`
work unedited.

Visibility layers on top. Guests and customers without specs see only
`source_kind = Item`. A customer with specs additionally sees spec products
whose `specification` is one of theirs. A spec product is never visible — nor
addable — to a customer it does not belong to; a crafted `add_item` for another
customer's spec is refused, not merely hidden.

The store page renders a **Your specifications** section above the open
catalogue, only when that list is non-empty. A spec card expands into its
approved varieties with each one's bunches-per-box, length and rate; the buyer
sets quantities per variety and adding to cart creates N tagged lines.

### Cart

The cart key becomes `(item_code, specification)`, because the same variety may
sit in the cart both plain and under a spec. The five whitelisted endpoints in
`api/cart.py` take an optional `specification` defaulting to blank, so every
existing caller is unaffected.

Hard constraints on a spec line: its `item_code` must be an approved variety of
its spec, and its box type and length come from the spec, not the buyer.
Untagged lines keep today's behaviour. A cart may mix both kinds; they validate
under different rules.

### Packing arithmetic

`services/packing.py` gains a third resolution path ahead of the existing two: a
line carrying a `specification` takes its pack rate from the spec. Untagged
lines fall through to `get_box_source()` unchanged — which on Kaitet resolves to
nothing, so plain variety lines stay unpacked and no Box Type data fix is
needed.

The spec rate follows `box_assortment`, confirmed against the data:

| | single row | summed per length |
|---|---|---|
| Mono Box | median 300 stems/box, max 1200 | median 500, max 7020 — implausible |
| Mixed Box | median 50 — a component | median 448, max 3720 |

**Mono:** each row is a box, so the variety's own `pack_rate`. **Mixed:** the
rows compose one box, so sum `pack_rate` across rows for that length. Both are
already stems (`stems_per_bunch × bunches_per_box`), so `compute_boxes()` needs
no unit change; quantities entered in bunches convert at `stems_per_bunch`
first. `group_by_box_type()` groups spec lines by `(specification, length)`.

Whole-box fill is checked at box level, not per variety. Strict per-variety
enforcement would reject real orders — `GRD TASHA WHITE 62CM` was ordered
24/24/24 against spec rows 24/24/24/30 — so `bunches_per_box` is a default
quantity and a suggestion, while the existing `find_problems()` check runs on
the group total.

### Checkout

`_cart_items()` maps `specification` → `Sales Order Item.custom_line`, guarded
by the existing `_writable()` helper so a site lacking that field omits it.
Lines stay one-per-variety, which is already Kaitet's shape, so the packhouse
reads these orders with no change on their side. `_assert_packable()` validates
spec groups and box-type groups separately; `_has_mixed_boxes()` treats a spec
group as one box.

## Error handling

Messages name the spec and the fix: *"CM13 MIX 52CM: Nightingale is not an
approved variety of this specification."* A spec that cannot be ordered
coherently — no box items, no approved varieties, no priced varieties — is not
published rather than published and broken, which excludes the 31 specs with no
approved varieties, the 12 with no box items and the 20 with a blank
`box_assortment` automatically. Where a
customer's spec list is empty for any reason, the storefront falls back to the
open catalogue rather than showing an empty section.

## Testing

- `test_specs.py` (new): customer resolution, spec ownership, variety
  membership, the mono/mixed rate rule, absent-doctype guards.
- `test_packing.py`: spec rate ahead of box source, bunch→stem conversion,
  grouping by `(specification, length)`, untagged lines unchanged.
- `test_catalog.py`: per-customer visibility, guest visibility, and refusal of a
  cross-customer spec add.
- `test_checkout_boxes.py`: `custom_line` written, omitted when the field is
  absent, spec and box groups validated separately.
- The `(item_code, specification)` cart key is tested before anything is built
  on it — it is the one change that can break existing behaviour silently.

## Non-goals

- Writing to `Specifications`, or any packhouse doctype, ever.
- Fixing the packhouse data: the duplicate Cut Stage spellings (`2-2.5` vs
  `2.0-2.5`), the `57` / `57cm` Stem Length pair, `Box Type`'s zero dimensions,
  the unused `valid_from`/`expiry_date`, the empty `Customer pricing` table, the
  `custom_item_name` duplicate on `Spec Consumable`. Worth doing, separately.
- Joining `Spec Approved Variety` to `Spec Box Item` beyond row order. The
  alignment breaks in 29 of 314 specs and no reliable key exists; the design
  avoids depending on it.
- Surfacing cut stage, defoliation, rubber band placement or consumables to the
  buyer. They are packhouse instructions, not purchasing decisions.
- Spec-level pricing, and the 15 customerless specs.
