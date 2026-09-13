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
