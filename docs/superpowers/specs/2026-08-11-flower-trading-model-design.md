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
  apps already own. This app claims neither — it *reads* them where a farm
  already has them, and never creates, migrates or takes ownership of either.
- **Deploying must change nothing.** Every live pack rate is `0`. If a missing
  rate meant "block", enabling this would brick the storefront. The feature
  must be inert until deliberately configured and switched on.
- **Never trust the client.** Box counts are derived server-side on every cart
  mutation, exactly as `_reprice` already re-resolves rates.

## Decisions

| Decision | Choice |
|---|---|
| Unit of sale | **Stems**, unchanged; box count is derived |
| Pack rate source | **Resolved per site**: `Box Type` records when populated, else Items with `custom_is_box=1` |
| Box type | **Product supplies the default; buyer may override per line** |
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

**Amended during implementation.** This section originally assumed
`Item.custom_is_box` and `Item.custom_pack_rate` simply existed, because Mona
live has them. They are `upande_harvest`'s fields, and on a site with only this
app installed they are absent — so there was no way to mark an Item as a box and
the feature could never work standalone. `install.py` therefore *ensures* both,
alongside the fields it already ensures on Quotation and Sales Order.
**Amended again 2026-09-01.** Two claims here were wrong, and both are corrected
in *Box type source is site-dependent* below. Items are no longer the only
source, and `create_custom_fields` does **not** skip fields that already exist —
it updates them, so the installer filters conflicts out first and now only ever
creates fields that are absent.

### Why the whole-box check is not per line

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
300/600/900. Checking the **cart total** honours mixed boxes while still
refusing genuinely unpackable orders, and 19 of 40 sampled order totals were
already whole multiples of 300 against only 21% of individual lines.

**Amended twice after review.** This began as a per-line box *choice*, then
briefly became a single order-level choice at checkout. Both were wrong for the
same reason: **the buyer should not be choosing at all.** A 120cm stem physically
will not fit a 100x33x20 box, so the box is determined by the product. Mona
already models exactly this as `Website Item.custom_box_type`.

**Settled shape.** The product supplies the default via
`Webstore Product.box_type` — it knows a 120cm stem needs a tall box — and the
buyer may override it per basket line. Removing the choice entirely went too far:
a customer who wants everything in jumbos for their own handling has a legitimate
reason to say so. An order therefore spans as many box types as its lines call
for, and whole-box fill is checked per box-type group.

Only the box *count* is never a client input. A buyer's override survives
quantity changes; recompute reseeds from the product only when a line has no
usable box.

### Box type source is site-dependent (amended 2026-09-01)

An audit of **Karen Roses (`kaitet`)** on 2026-09-01 — a farm this design had
never been checked against — falsified the premise above. The original audit
covered Mona live and Mona staging only, and concluded the `Box Type` doctypes
were empty everywhere. On Karen Roses it is the *populated* one.

**What is actually there.** `Box Type` holds 12 records with real commercial
data, richer than a pack rate:

| Box Type | Stem capacity | L×W×H cm | Weight | CBM | Equiv. standard |
|---|---|---|---|---|---|
| Xpol | 350 | 99×40×20 | 23.4 kg | 0.0792 | 1.20 |
| Standard | 400 | 100×33×20 | 19.8 kg | 0.0660 | **1.00** |
| Flower Pack Pro | 300 | 100×39×25 | 28.3 kg | 0.0975 | 1.48 |
| Large | 550 | 120×40×25 | 34.4 kg | 0.1200 | 1.82 |
| Quarter Box | 100 | 82×22×16 | 9.8 kg | 0.0289 | 0.44 |

`custom_equivalent_standard` is a freight-equivalence multiplier against
Standard — how the farm costs airfreight. `custom_stem_capacity` is the column
that corresponds to a pack rate.

**Boxes as Items mean something else here.** A physical box is stocked as
*packaging material components*, not as a sales concept. The Xpol box is three
Items in item group `PACKAGING MATERIALS`: `1212100451` "Xpol Box
100x38.5x20.5cm - Bottom", `1212100450` "- 2 Tops Covers" and `1212100381` "-
complete". Cardboard that is bought and consumed. No `custom_is_box` or
`custom_pack_rate` exists on Item on that site at all, and a capacity of 350
could not sensibly live on the bottom *and* the lid.

**The field points somewhere else too.** `Sales Order Item.custom_box_type` on
Karen Roses is a Link to **`Box Type`**, not to Item, and carries 5,019 live
values: Flower Pack Pro 2,403, Standard 1,418, Large 812, Small 386.
`Loading Plan Item.custom_box_type` is the same Link. A third representation,
the `Packrate` doctype (`box_type` as Data, `packrate` as Int), also exists.

**The installer hazard this exposed.** `install.py` claimed
`create_custom_fields` "skips fields that already exist". It does not:
`update=True` is the default and `custom_field.py:363` saves any changed
property. Installing this app on Karen Roses would rewrite
`Sales Order Item.custom_box_type` from `options: Box Type` to `options: Item`,
mark it read-only, and orphan all 5,019 values — "Flower Pack Pro" is not an
Item code — while breaking the Loading Plan flow that reads the same field.

#### Decision: resolve the source, do not impose one

`services/packing.py` gains a resolver that decides site-wide, once per request,
where box types come from:

```
Box Type doctype exists, has custom_stem_capacity,
and has >= 1 row with capacity > 0
  -> source = Box Type   (name, custom_stem_capacity)
Item has both custom_is_box and custom_pack_rate
  -> source = Item       (custom_is_box=1, disabled=0, custom_pack_rate > 0)
neither
  -> source = None       (packing inert, exactly as before)
```

*Populated* is load-bearing: the original audit found empty `Box Type` doctypes
on Mona, and an empty one must fall through to Items rather than silently
disable packing.

The module's public surface is unchanged — `get_box_types`, `get_pack_rate`,
`is_usable_box`, `box_label`, `compute_boxes`, `group_by_box_type`,
`find_problems` keep their signatures — so `api/cart.py`, `api/checkout.py` and
the cart page do not move. Only the reads inside change.

#### The stored value is an Autocomplete, not a Link

`Webstore Product.box_type`, `Webstore Cart Item.box_type` and
`Webstore Settings.default_box_type` become **Autocomplete**, suggested from
`get_box_types()` and validated by the resolver on save. A Link cannot vary its
target per site, and a Dynamic Link would need a companion `box_doctype` column
on every row to name a target that is a site-wide fact — redundant data to keep
in sync. `Webstore Settings.occasion` already uses this pattern.

A value that stops resolving — a farm switching source, a box being disabled —
is treated exactly as an unusable box already is: the line reseeds from the
product default, and packing skips the group when nothing resolves.

#### Writing to ERPNext becomes conditional

`api/checkout._present(doctype, fieldname)` becomes
`_writable(doctype, fieldname, expect_options)`. `custom_box_type` is written
only when the field exists **and** its `options` match the resolved source
doctype. Karen Roses (source `Box Type`, field → `Box Type`) writes correctly;
Mona (source `Item`, field → `Item`) writes; a mismatch is skipped silently,
which is how `_store_delivery_point` already handles Mona's absent
`Delivery Point`.

#### The installer stops rewriting

`create_webstore_custom_fields` filters out any field that already exists with a
different `options` or `fieldtype`, and logs what it skipped. Every other field
still updates, so genuine property fixes keep landing. This is the guard that
protects the 5,019 lines, and it protects any other farm whose `custom_` field
names collide with ours for the same reason.

#### What this does not change

The rest of the design stands. Stems remain the unit of sale, the product still
supplies the default box with a per-line buyer override, whole-box fill is still
checked per box-type group, and the feature is still inert until
`enable_box_packing` is switched on. Freight equivalence, weight and CBM are
read but **not used** — noted as available, not modelled.

### Rejected alternatives

- **A new `Webstore Box Type` doctype.** Self-contained, but a fifth
  representation that immediately drifts from what packing reads.
- **A `Webstore Settings` child table of box types.** No new doctype, but
  invisible to ops and re-typed per farm.
- **Adopting Harvest's `Box Type`** as the app's own doctype, shipped and
  migrated. Introduces a hard dependency on `upande_harvest` and breaks the
  standalone requirement. Reading a farm's existing `Box Type` records when they
  happen to be there — which the 2026-09-01 amendment adds — is a different
  thing: opportunistic, guarded at every read, and inert when absent.
- **Boxes as the unit of sale.** "6 boxes of Athena" cannot express a mixed box
  holding three varieties, and would need a separate mixed-box builder.
- **A single order-level box chosen at checkout.** Tried and removed: it cannot
  express an order whose long-stem lines need a taller box than the rest, and it
  invited
  buyers to mix box sizes in one order, which the packing floor does not do.
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
get_box_source()              -> Source | None    resolved once per request
get_box_types()               -> [{box_type, box_name, pack_rate}]
      from the resolved source; [] when there is none
get_pack_rate(box)            -> int          0 when unusable
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
| `default_box_type` | Autocomplete | — | Seeds each new cart line; validated against the resolved source on save |
| `minimum_order_stems` | Int | `0` | `0` means no minimum. Mona sets `1000` |
| `default_lead_days` | Int | `7` | Preserves today's fallback |

`enable_box_packing` is deliberately **not** added to the `FEATURES` registry in
`theme/features.py`. Every flag in that registry drives `require()` and
`guard()`, which *deny access* — a 404 on a route or a `PermissionError` on an
API. Box packing needs the opposite behaviour: when off, the cart and checkout
must work normally with validation skipped. So it is a plain Check on
`Webstore Settings`, read directly by `services/packing.py`.

### Schema

`Webstore Product` gains `box_type` (Autocomplete) — the box that product ships
in, mirroring `Website Item.custom_box_type` on live. The desk picker is fed from
the resolved source, and a product refuses to save with anything that source does
not know.

`Webstore Cart Item` gains `box_type` (Autocomplete) and `number_of_boxes` (Int,
read-only). The line's box is seeded from its product and may be changed by the
buyer; `number_of_boxes` is derived on every save and never read from the client.
A buyer's override survives quantity changes — recompute reseeds from the product
only when a line has no usable box.

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
| Item | `custom_is_box`, `custom_pack_rate` | exists; **ensured by `install.py`** |

Ensuring these is **not** unconditionally safe: `create_custom_fields` updates
existing fields rather than skipping them. The installer is therefore
create-only — see *Box type source is site-dependent*.

Two fields are deliberately **never written**: `Quotation.custom_box_type`,
because it links to the empty `Box Type` doctype, and the order-level
`Sales Order.custom_box_type`, because box type is per line here.

Because a line sharing a mixed box has no whole-box count of its own:

- `custom_pack_rate` — the line's box type rate. Always well-defined.
- `custom_number_of_boxes` — the line's own whole boxes when
  `qty % pack_rate == 0`, otherwise `0`.
- `Sales Order.custom_has_mixed_boxes` — `1` when some line must share a box.
  A line whose quantity is a whole number of boxes packs on its own, so two
  lines of 600 at 300/box are *not* mixed while 150 + 150 are. This tells the
  desk an order needs mixed-box handling without this app composing recipes.

## Box grouping

Lines are grouped by their box type; each group's stem total must be a whole
multiple of that box's pack rate.

```
BASKET
  Athena 60cm     600   [ ZIM Box (300)      v ]   2 boxes
  Madam Red 70cm 1000   [ Jumbo Box (500)    v ]   2 boxes
  Fireworks 40cm  400   [ Standard Box (200) v ]   2 boxes
  ------------------
  total          2000

  Jumbo Box       1000 stems - 2 boxes, all full
  Standard Box     400 stems - 2 boxes, all full
  ZIM Box          600 stems - 2 boxes, all full
  total 2,000 >= 1,000 minimum
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
| Omitted | Sales Order `delivery_date` = `today + default_lead_days` |
| Earlier than today | Rejected |
| Inside the lead window | Rejected, stating the earliest acceptable date |

The requested date and the resolved delivery date stay **distinct**.
`webstore_shipping_date` records what the buyer asked for, so when they ask for
nothing it stays empty; only the Sales Order's `delivery_date` takes the lead-time
default. Collapsing the two would stamp a derived date into a field that claims
to be a customer request — and `test_both_are_optional` already encoded that,
which is how the mistake was caught.

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
- `get_box_source`: prefers a populated `Box Type`; falls through to Items when
  that doctype is absent, has no capacity field, or has no row with a capacity
  above `0`; returns `None` when neither source exists
- `get_pack_rate`: reads `custom_stem_capacity` under a `Box Type` source and
  `custom_pack_rate` under an Item source
- `create_webstore_custom_fields`: a pre-existing `custom_box_type` pointing at
  `Box Type` survives unchanged — the regression that would otherwise orphan
  5,019 Karen Roses order lines

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

1. Confirm which source the farm resolves to — the Webstore Settings box panel
   names it. On Karen Roses that is `Box Type`, already populated, so nothing
   needs entering. On Mona it is Items, and `custom_pack_rate` must be entered
   on the seven `custom_is_box` Items — all are `0` today.
2. Set `default_box_type`, `minimum_order_stems` (1000) and `default_lead_days`
   (1) in Webstore Settings.
3. Switch on `enable_box_packing`.

Until step 3, the storefront behaves exactly as it does now.
