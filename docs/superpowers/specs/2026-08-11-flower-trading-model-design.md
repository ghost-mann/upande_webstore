# Flower Trading Model

Teach the storefront how flowers are actually traded: stems ordered against
**box types with pack rates**, a **minimum order quantity**, and a **requested
shipping date** that survives the trip from quotation to sales order. Built to
be inert until a farm configures it, so it can ship to a live site that has none
of the data yet.

## Problem

The app sells flowers as if they were any other catalogue item. Grep the repo
for `pack_rate`, `box_type` or `bunch` and you get nothing. A buyer can put
1,750 stems in the cart, check out, and hand the farm an order that cannot be
packed into whole boxes.

The ERP under it is not missing the concepts — it is drowning in half-finished
versions of them. An audit of Mona live and Mona staging on 2026-08-10 found:

- **Pack rate modelled in six places, populated in none** on live:
  `Box Type.pack_rate`, `Item.custom_pack_rate`, `Sales Order Item`,
  `Sales Invoice Item`, `Pack Box.pack_rate`, `Control Sheet Item.pack_rate`.
  Zero live Items have a rate above `0`. Staging has four:
  `PAC00004=300`, `PAC00007=500`, `PAC00008=300`, `PAC00009=200`.
- **Four competing representations of "box type".** A `Box Type` doctype in
  `Upande Harvest` on live (one field, `pack_rate`, 0 records); a different
  `Box Type` doctype in `Upande Webshop` on staging (`box_group`, `is_active`,
  and `packrate` as a **Select** whose options `240/204/192/180/144/120` do not
  contain the 300/500/200 staging actually uses); an abandoned `Box Type` **Item
  Attribute** on live with an empty value list; and seven Items flagged
  `custom_is_box`, which is what `Pack Box` genuinely links to.
- **`custom_box_type` pointing at two different doctypes.** `→ Box Type` on
  Website Item and Quotation, `→ Item` everywhere on the ops side. Because both
  `Box Type` doctypes are empty, the first pair can never resolve.
- **A `Delivery Point` doctype that does not exist on live**, while three Link
  fields on Customer, Quotation and Sales Order point at it. All null.
- **Dropoff kept as free text.** `Sales Order.custom_drop_off_point` is filled
  on 1,997 of 2,148 live orders, with onward routing baked into the string:
  `mitchell cotts c/o tradewinds`, `dhl c/o d olive roses`, and casing variants
  `AIRFLO` / `airflo` / `aiflo` / `Airflow`.
- **The requested shipping date is silently dropped.** `place_order` writes
  `webstore_shipping_date` on the Quotation, but ERPNext's quotation → sales
  order mapper does not carry custom fields, and nothing else copies it. The
  hardcoded `DEFAULT_DELIVERY_DAYS = 7` also contradicts observed practice,
  which is `delivery_date = transaction_date + 1` on every live order.

Two things are, happily, already solved. **Stem length is a working ERPNext
variant axis**: `Alicia` is a template with `variant_based_on = "Item
Attribute"` and nine variants `Alicia-40cm … Alicia-120cm`, and the `Stem
Length` attribute holds `40cm … 120cm`. This app already renders variants
(`api/variants.py`, `get_variant_price_range`, template handling in
`catalog.py`). Stem length therefore needs **no new modelling**.

## Constraints

- **One app, many farms.** No dependency on `upande_harvest` or
  `upande_webshop`. Today the repo has none, and this must not introduce one.
- **No new doctypes.** Box type already has four representations. A fifth is
  not a fix.
- **No name collisions.** `Box Type` and `Delivery Point` are both names other
  apps already own. This app claims neither.
- **Deploying must change nothing.** Every live pack rate is `0`. If a missing
  rate meant "block", enabling this would brick the storefront. The feature
  must be inert until deliberately configured and switched on.
- **Never trust the client.** Box counts are derived server-side on every cart
  mutation, exactly as `_reprice` already re-resolves rates.

## Decisions

| Decision | Choice |
|---|---|
| Unit of sale | **Stems**, unchanged; box count is derived |
| Pack rate source | **Items** with `custom_is_box=1` and `custom_pack_rate` |
| Box type scope | **Per cart line**, seeded from a farm default |
| Whole-box check | Per **box-type group**, not per line |
| Minimum order | **Order total in stems**, configurable |
| Bunches | **Out of scope** for v1 |
| Dropoff | Consume `Delivery Point` **if present**, else free text |
| Shipping date | Configurable lead time, enforced server-side, carried on conversion |
| Rollout | Feature flag, **default off** |

### Why Items rather than a doctype

`Pack Box.box_type` links to `Item` on both sites, and `Sales Order Item`
already carries `custom_box_type` (→ Item), `custom_number_of_boxes` and
`custom_pack_rate`. Reading Items means the storefront and the packing floor
share one source, with no new doctype, no fixtures and no migration. The cost
is honest: someone has to enter rates on the seven live box Items, and that is
a prerequisite for switching the flag on rather than a code problem.

### Why the whole-box check is per group

Real line quantities are small. A sample of 40 recent orders / 309 lines:

| Observation | Figure |
|---|---|
| Lines under 1,000 stems | 283 / 309 (92%) |
| Lines that are a multiple of 300 | 66 / 309 (21%) |
| Order totals that are a multiple of 300 | 19 / 40 |
| Smallest order total | 200 stems |

The commonest line quantities are 20, 50, 100, 200, 250 and 300. A 50-stem line
is not a partial box — it shares a box with other varieties, which is what
`custom_has_mixed_boxes` and `Sales Order Mixed Box Group` exist for. Checking
per line would reject 79% of realistic lines and force every variety to
300/600/900. Summing each box-type group and checking *that* total honours
mixed boxes while still refusing genuinely unpackable orders.

### Rejected alternatives

- **A new `Webstore Box Type` doctype.** Self-contained, but a fifth
  representation that immediately drifts from what packing reads.
- **A `Webstore Settings` child table of box types.** No new doctype, but
  invisible to ops and re-typed per farm.
- **Adopting Harvest's `Box Type`.** Introduces a hard dependency on
  `upande_harvest` and breaks the standalone requirement.
- **Boxes as the unit of sale.** "6 boxes of Athena" cannot express a mixed box
  holding three varieties, and would need a separate mixed-box builder.
- **Auto-snapping quantities.** Silently changing a buyer's typed number on a
  priced order is a trust problem.
- **Modelling bunches now.** Live has 0 `Bunch QR Code` records, no bunch UOM
  and `custom_stems_per_bunch = 0` everywhere. Staging's 280,714 records belong
  to a different app, carry `stem_length` on only 24 of them, and sit behind
  UOMs with trailing-space names (`5 stems `, `7 stems `). There is nothing here
  to build against yet.

## Architecture

```
services/packing.py        NEW  pure box math, no doc mutation
services/conversion.py     NEW  quotation -> sales order carry-through
api/cart.py                     recompute boxes on every mutation
api/checkout.py                 assert packable, resolve delivery date
setup/install.py                ensure Quotation Item box fields
```

`services/packing.py` holds no document state:

```
get_box_types()               -> [{item_code, item_name, pack_rate}]
      Items where custom_is_box=1, not disabled, pack_rate > 0
get_pack_rate(box_item)       -> int          0 when unusable
compute_boxes(qty, pack_rate) -> {boxes, remainder, is_full,
                                  nearest_down, nearest_up}
group_by_box_type(lines)      -> {box_item: {stems, lines, ...}}
```

`compute_boxes` returns `is_full = True` whenever `pack_rate` is `0`, so an
unconfigured box can never block. `nearest_down` is `0` when `qty` is below one
box, and the caller offers only round-up in that case.

### Settings

Added to `Webstore Settings`:

| Field | Type | Default | Note |
|---|---|---|---|
| `enable_box_packing` | Check | `0` | Master switch; off means fully inert |
| `default_box_type` | Link → Item | — | Seeds each new cart line |
| `minimum_order_stems` | Int | `0` | `0` means no minimum. Mona sets `1000` |
| `default_lead_days` | Int | `7` | Preserves today's fallback |

`enable_box_packing` is deliberately **not** added to the `FEATURES` registry in
`theme/features.py`. Every flag in that registry drives `require()` and
`guard()`, which *deny access* — a 404 on a route or a `PermissionError` on an
API. Box packing needs the opposite behaviour: when off, the cart and checkout
must work normally with validation skipped. So it is a plain Check on
`Webstore Settings`, read directly by `services/packing.py`.

### Cart schema

`Webstore Cart Item` gains `box_type` (Link → Item) and `number_of_boxes` (Int,
read-only). `number_of_boxes` is derived on every save and never read from the
client.

### Mapping into ERPNext

The point of sourcing box types from Items is that ops already reads these
fields, so this writes the names ops consumes rather than `webstore_`-prefixed
ones. That is a deliberate, scoped exception to the app's naming convention.

| Target | Field | On live |
|---|---|---|
| Sales Order Item | `custom_box_type` (→ Item) | exists |
| Sales Order Item | `custom_pack_rate` | exists |
| Sales Order Item | `custom_number_of_boxes` | exists |
| Sales Order | `custom_has_mixed_boxes` | exists |
| Quotation Item | the same three box fields | **created by `install.py`** |

`create_custom_fields` skips fields that already exist, so ensuring these is
safe on a farm that already has them.

Two fields are deliberately **never written**: `Quotation.custom_box_type`,
because it links to the empty `Box Type` doctype, and the order-level
`Sales Order.custom_box_type`, because box type is per line here.

Because a line sharing a mixed box has no whole-box count of its own:

- `custom_pack_rate` — the line's box type rate. Always well-defined.
- `custom_number_of_boxes` — the line's own whole boxes when
  `qty % pack_rate == 0`, otherwise `0`.
- `Sales Order.custom_has_mixed_boxes` — `1` when any box-type group holds more
  than one line, which tells the desk this order needs mixed-box handling
  without this app composing recipes.

## Box grouping

Lines are grouped by their box type; each group's stem total must be a whole
multiple of that box's pack rate.

```
CART
  Athena 60cm    50   ZIM
  Reflex 60cm   250   ZIM
  Alicia 60cm   300   ZIM
  Snow Flakes   500   JUMBO

GROUPS
  ZIM     600 stems / 300 = 2 boxes   full
  JUMBO   500 stems / 500 = 1 box     full
  order total 1,100 stems >= 1,000    ok
  -> checkout enabled
```

A group that does not divide cleanly blocks checkout and names both neighbours:

```
ZIM boxes: 550 stems across 3 lines does not fill whole
boxes (300 per box). Use 300 (1 box) or 600 (2 boxes).
```

Groups whose box type has no usable pack rate are skipped entirely, which is
every group on live until rates are entered.

## Minimum order quantity

`minimum_order_stems` is checked against the **cart total in stems** at
checkout, independent of box grouping. `0` disables it.

It is measured per order, not per line, because 92% of real lines fall below
1,000 stems — a per-line minimum would reject almost every genuine line. Note
that 16 of the 40 sampled historic orders also fall below 1,000; those are
sales-team ERP entries, and the MOQ is a policy for self-service buyers rather
than a description of past trade.

The two blocks compose, and the composition is stricter than either alone. With
a 1,000-stem minimum and a single 300-stem box type, 1,000 is not a whole number
of boxes, so the smallest acceptable order is **1,200 stems (4 boxes)**. The
checks are reported together rather than one at a time, so a buyer is never sent
to fix the minimum only to be blocked again on box fill.

## Shipping dates

`DEFAULT_DELIVERY_DAYS = 7` becomes the fallback for `default_lead_days`, so
behaviour is unchanged until a farm sets it. Mona would set `1`, matching the
`transaction_date + 1` convention on all 2,148 live orders.

Server-side, in `place_order`:

| Input | Result |
|---|---|
| Omitted | `today + default_lead_days` |
| Earlier than today | Rejected |
| Inside the lead window | Rejected, stating the earliest acceptable date |

The `min=` attribute on the cart's date input stays, but is now backed by a
server check rather than being the only one.

### Carrying the date across conversion

`services/conversion.py` registers a `before_insert` hook on Sales Order via
`hooks.py` `doc_events`. When the first line's `prevdoc_docname` resolves to a
Quotation, it copies:

- `webstore_shipping_date` → `delivery_date` **and every item's**
  `delivery_date`, which ERPNext requires separately
- `webstore_dropoff_points` → the same field on the Sales Order
- `custom_delivery_point` → the same field, **only when the `Delivery Point`
  doctype exists**

It fires once per document, and the buyer's explicit request beats the mapper's
derived default. This closes the data loss whether conversion happens from the
portal or the desk.

## Dropoff points

`Delivery Point` is detected at runtime rather than created:

| Doctype present | Cart control | Written to |
|---|---|---|
| Yes | Picker of enabled points | `custom_delivery_point` (Link) |
| No | Today's textarea | `webstore_dropoff_points` (Small Text) |

Writing a Link value while its target doctype is absent fails validation, which
is exactly the state live is in — hence the detection. This also avoids
repeating the `Box Type` collision for a second doctype name, and the storefront
upgrades itself the day ops ships `Delivery Point`.

Normalising the 1,997 existing free-text strings is out of scope; the `c/o`
pattern means it wants two fields, carrier and onward handler, which is an ops
data-modelling decision rather than a storefront one.

## Error handling

Everything degrades toward letting the order through, except the box-fill and
minimum-order checks. When both fail, both are reported in one response.

| Condition | Behaviour |
|---|---|
| `enable_box_packing` off | Fully inert |
| No box Items, or pack rate `0` | Group not validated — today's behaviour |
| Box type disabled or no longer a box | Reseed from default; skip if none |
| Box-type group not a whole multiple | **Block**, naming both neighbours |
| Group total below one box | **Block**, stating the one-box minimum |
| Cart total below `minimum_order_stems` | **Block**, stating the shortfall |
| `minimum_order_stems` is `0` | No minimum enforced |
| Date past, or inside lead window | Reject, stating earliest acceptable date |
| `Delivery Point` absent | Fall back to free text |

Blocking messages carry the remedy, not just the complaint, because a hard block
with no stated way forward is a dead end for a buyer who cannot see the farm's
pack rates.

## Testing

Pure functions first, since that is where the logic lives and none of it needs a
database:

- `compute_boxes`: exact multiple, remainder, `qty` below one box, `pack_rate`
  of `0`, `qty` of `0`, and `nearest_down == 0`
- `group_by_box_type`: several lines to one box, several groups, one line each
- `get_box_types`: excludes `custom_is_box=0`, disabled Items, and rate `0`

Then against the cart and checkout:

- `add_item` seeds `default_box_type`; `set_box_type` recomputes and regroups
- `serialize_cart` exposes the group summary and a `packable` flag
- checkout blocks a non-whole group; blocks a total below the MOQ; allows when
  both pass
- field mapping onto Quotation Item and Sales Order Item, including
  `number_of_boxes = 0` for a line inside a mixed box, and
  `custom_has_mixed_boxes` when a group holds several lines
- dates: past rejected, inside-lead rejected, omitted defaults, written to the
  Sales Order and every item
- conversion hook carries date and dropoff, and skips `custom_delivery_point`
  when the doctype is absent

**Inert-path tests matter most**, because they are what make this safe to merge
and deploy to Mona before a single pack rate exists:

- flag off — cart and checkout behave exactly as they do now
- flag on but every pack rate `0` — no blocking
- `minimum_order_stems` of `0` — no minimum

`test_cart.py`, `test_checkout.py` and `test_cart_page.py` need updating. The
rest of the suite stays green.

## Non-goals

- **Bunches.** Deferred, with the reasoning recorded above.
- **Creating `Delivery Point`**, or normalising the free-text dropoff strings.
- **Stem length ↔ box compatibility.** A 120cm stem will not physically fit a
  100×33×20 box, and this design does not model it. The storefront will let a
  buyer put 120cm stems in a standard box. Named here because it is a real gap,
  not an oversight.
- **Mixed-box recipes.** This flags a mixed order; it does not compose one.
- **Resolving the four `Box Type` representations.** Sidestepped by reading
  Items. The collision remains, and is worth settling before either doctype
  gains records.
- **Populating pack rates on live.** Data entry, and a prerequisite for
  switching the flag on.

## Prerequisites before enabling

1. Enter `custom_pack_rate` on the seven `custom_is_box` Items on live — all
   are `0` today.
2. Set `default_box_type`, `minimum_order_stems` (1000) and `default_lead_days`
   (1) in Webstore Settings.
3. Switch on `enable_box_packing`.

Until step 3, the storefront behaves exactly as it does now.
