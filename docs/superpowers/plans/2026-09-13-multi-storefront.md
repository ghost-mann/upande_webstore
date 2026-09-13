# Multiple Storefronts — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-09-13-multi-storefront-design.md`

**Scoping decision (made without the user, who is away):** the spec's full field
migration moves ~100 fields off a 143-field Single. That is too much surgery to
do unattended in one pass. This plan delivers the spine and the isolation, and
leaves a documented Phase 2 for moving the remaining presentation fields.

**Phase 1 — what gets built here**

A `Webstore` doctype owning store identity and the config that most obviously
differs per shop. `Webstore Settings` remains the site-wide default; a store row
overrides what it sets and falls back for everything else, so no field is
duplicated and no existing call site breaks.

## Task 1 — the spine

- `Webstore` doctype: `slug` (unique, lowercase, reserved-word checked),
  `title`, `published`, `theme_preset`, plus per-store `categories`,
  `guest_price_lists`, `warehouses` child tables and `checkout_mode`,
  `enable_box_packing`, `default_box_type`, `minimum_order_stems`,
  `default_lead_days`.
- `services/store.py::current_store()` — resolves from the path prefix, caches
  on `frappe.local`, exposes `clear_store_cache()` for tests.
- `services/settings.get_settings()` returns a merged view: the resolved store's
  non-empty values over the Single's. Signature unchanged, so the 23 call sites
  keep working.
- Slug validation: unique; refuses `portal`, `api`, `app`, `assets`, `files`,
  `login`, `signup`, `desk`, `private`.
- Patch `create_default_webstore`: one row, slug `store`, copying the current
  per-store values, so `/store` keeps working unchanged.

## Task 2 — routing and isolation

- `website_route_rules` mapping `/<slug>/store`, `/<slug>/cart`,
  `/<slug>/wishlist` and `/<slug>/store/<product>` onto the existing controllers.
- `webstore` Link on `Webstore Product` (child table for multi-store),
  `Webstore Cart`, `Webstore Wishlist`.
- Open-cart lookup keyed on `{user, status, webstore}`.
- Catalogue filtered by the resolved store.
- Checkout stamps the store on Quotation and Sales Order via a custom field.
- Patch stamps existing products, carts, wishlists with the default store.

## Task 3 — verification

Full suite green; a single-store site behaves exactly as today; two stores are
isolated in catalogue, cart and pricing; the shared portal shows both.

---

## Phase 1 status

**Task 1 — the spine.** Done, `71db0ca`.

**Task 2 — routing and isolation.** Done, `26e970c` plus review fixes.

### Decisions taken while the user was away

- **The default store keeps the bare paths.** `/store`, `/cart`, `/wishlist` and
  `store/<product>` are unchanged for the migrated default store; only a
  non-default store gets a `/<slug>/` prefix. No existing URL changes and
  nothing redirects, which is what makes the upgrade invisible to a
  single-store site.
- **One product, one canonical URL.** `Webstore Product.item` and `web_title`
  are unique site-wide, and a `WebsiteGenerator` has exactly one `route`, so a
  product gets a `primary_store` that decides its URL and a `stores` child
  table that decides which catalogues list it. An empty table falls back to the
  primary store; a blank primary store means the default.
- **Box packing is a tri-state, not a checkbox.** A `Webstore` row has to be
  able to say "off" as well as "inherit", or a dairy store is stuck with the
  flower store's box maths. Blank inherits `Webstore Settings`.
- **Store membership is enforced on write, not only on read.** The listing
  filters the catalogue, but `cart.add_item` and `wishlist.toggle` name a
  product directly, so both check membership too — otherwise a crafted call
  puts a dairy line into a flower order stamped with the wrong shop.
- **The back-fill patch only stamps documents a cart produced.** A blanket
  update would stamp every quotation a sales rep ever raised in the desk, and
  `custom_webstore` would stop meaning "this came from a shop" on its first
  migration.

### Known gaps, deliberately left for Phase 2

- **Presentation fields are still site-wide.** Branding, theme seeds, hero,
  occasion, process steps and footer links live on `Webstore Settings` and are
  shared by every store. Moving them is the spec's full field migration — ~100
  fields off a 143-field Single — and is the whole of Phase 2.
- **API calls infer their store from the `Referer` header.** A storefront page
  carries its slug in its own path, but the JS it runs calls
  `/api/method/...`, which does not. Referer is the only place the slug still
  is, and a browser may withhold it. The fix is for the storefront JS to send
  the slug explicitly and for the server to prefer that argument; until then a
  missing Referer falls back to the single-store/default resolution.
- **The catalogue filter materialises product names.** `_store_product_names`
  pulls every visible product name back and passes it as an `in` filter.
  Correct, and fine at the scale these farms run, but it should become a join
  before any catalogue grows into the thousands.

---

## Phase 2 — the field migration

Phase 1 made a store a real thing with its own catalogue, cart and orders, but
every shop still rendered in one theme under one name, which is most of what
makes two shops two shops. Phase 2 moves the presentation surface.

### What moved, and how

Not by copying ~60 field definitions by hand — that is how options, labels and
link targets drift apart. `services/store_fields.py` is the one list of which
fields a store may override, and `scripts/generate_webstore_fields.py` builds
the `Webstore` doctype's fields from `Webstore Settings`' own definitions.
`tests/test_store_field_parity.py` fails if the committed result stops
matching, and names the script in its failure message.

Per store: theme seeds (colour, type, shape, custom CSS), the occasion
campaign, identity and wordmark, hero, all the marketing copy and its four
tables, guest price list, stock display, and the ten storefront feature flags.

Site-wide: company, customer group, territory, quotation validity, the
notification list, the role grants, and the ten **portal** feature flags — the
portal is shared, so switching Invoices off for one shop and not the other
would describe a customer experience that does not exist.

### Two mechanisms, one rule

Blank inherits. A store fills in what differs and leaves the rest alone, which
is why a site with one storefront needed **no data migration at all**: its
store row is blank and it renders exactly what it always did.

Checkboxes are the exception, because a Check cannot say "off" and "inherit"
at the same time. Every per-store checkbox is a blank/Enabled/Disabled Select
on the store — twelve of them, listed in `PER_STORE_TRISTATE`.

### Navigation

Every storefront link in the templates was the literal string `/store`,
`/cart` or `/wishlist`, which on `/flowers/store` navigates the shopper into
the default store. They now read `webstore_urls`, set per request from the
resolved store. The default store's values are the bare paths, so a
single-store site's markup is unchanged.

### Transfer

`apply_preset`, `export_theme` and `import_theme` take an optional `webstore`.
Export returns a store's *effective* look — its overrides on top of what it
inherits — because "copy this shop's appearance" means the appearance a
visitor sees, not the half of it the shop happens to state itself. Import
resets absent fields to blank on a store (inherit) rather than to the DocType
default (what it means on the Single). The `Webstore` form carries the same
three Theme buttons, scoped to the one shop.

### Still deliberately out

- **Per-store portals, customers or books.** Non-goals in the spec and
  unchanged here.
- **Subdomains.** Path prefix only; host-based routing can layer on later
  without changing the store model.
- The two Phase 1 gaps above (Referer-derived store for API calls, and the
  catalogue filter's `IN` clause) are untouched by Phase 2 and still stand.
