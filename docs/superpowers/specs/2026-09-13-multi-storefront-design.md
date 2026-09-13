# Multiple Storefronts on One Site

Let one company run several storefronts from a single ERPNext — flowers at
`/flowers/store`, dairy at `/dairy/store` — sharing Customers, Items and
accounting, while each shop keeps its own branding, catalogue, pricing and
warehouses.

## Problem

The app assumes exactly one storefront per site, in three structural ways:

- **`Webstore Settings` is a Single** with 143 fields. Theme, branding, feature
  flags, categories, guest price lists, warehouses, box rules, checkout mode and
  portal behaviour all live in one row. 23 call sites read it via
  `services.settings.get_settings()`.
- **18 routes are hardcoded** as files under `www/` — `/store`, `/cart`,
  `/wishlist`, `/signup` and thirteen `/portal/*` pages.
- **No record carries a store dimension.** `Webstore Product`, `Webstore Cart`,
  `Webstore Wishlist`, `Webstore Category` and `Webstore Claim` are all
  site-wide.

Running a second shop today means a second Frappe site, which splits the
Customer list, the Item master and the books — unacceptable when it is one
company selling two ranges.

## Constraints

- **One ERPNext.** Customers, Items, Sales Orders, Quotations and accounting
  stay shared and untouched. A storefront is a presentation and pricing layer,
  never a second set of books.
- **Existing sites must not break.** A site running one storefront today keeps
  working at `/store` with its current settings, with no manual migration step.
- **No new route collisions.** The app already owns `/store` and `/portal`; it
  must not start claiming arbitrary top-level paths that another app may want.
- **The portal stays shared.** A customer has one account, one order history and
  one statement across both shops. Splitting it would mean two logins for one
  trading relationship.

## Decisions

| Decision | Choice |
|---|---|
| Store record | New **`Webstore`** doctype, one row per storefront |
| Per-store config | Moves onto `Webstore`; `Webstore Settings` keeps only what is genuinely site-wide |
| URLs | **Path prefix** — `/<slug>/store`, `/<slug>/cart` |
| Product to store | **Many-to-many** via a child table on `Webstore Product` |
| Cart | One open cart **per user per store** |
| Portal | **Shared**, unprefixed, at `/portal` |
| Existing sites | Migrated to a single store whose slug keeps `/store` working |

### What belongs to a store, and what stays site-wide

Per store, moving to the `Webstore` doctype: theme and branding fields, feature
flags, hero and category cards, categories, guest price lists, warehouses, box
packing rules, checkout mode, minimum order, lead days.

Site-wide, staying on `Webstore Settings`: company, the roles section (desk
access is not per shop), and anything about portal behaviour that a customer
experiences once rather than per shop.

The split is decided by one question: *would a customer notice this differing
between the two shops?* Theme yes, company no.

### Routing

Frappe resolves `www/` files before dynamic rules, so the existing files stay
and gain a sibling: a `website_route_rules` entry mapping
`/<slug>/<page>` to the same page controllers, with the resolved store placed on
`frappe.local` for the request.

`Webstore Product` is a `WebsiteGenerator` whose route is `store/<title>`. With
several stores a product may appear in more than one, so its canonical route
becomes `<primary-slug>/store/<title>`, and the same product is reachable under
any other store it belongs to through the dynamic rule.

A request for a slug that does not exist, or a store that is unpublished, is a
404 — not a fallback to the default store, which would silently show the wrong
catalogue.

### Store resolution

One function, `services.store.current_store()`, resolves the store for the
request from the path prefix, caches it on `frappe.local` like the box source
already does, and every consumer reads it rather than re-parsing the path.
`get_settings()` keeps its signature and returns the resolved store's config, so
most of the 23 call sites need no change — which is what makes this tractable.

### Cart and wishlist

`Webstore Cart` and `Webstore Wishlist` gain a `webstore` Link. The open-cart
lookup becomes `{user, status: Open, webstore}`, so a buyer can hold a basket of
roses and a basket of yoghurt at once without one clearing the other.

Checkout writes the store onto the Quotation or Sales Order in a custom field,
so the desk can tell which shop an order came from — the single most useful
thing this feature gives the sales team.

### Existing sites

A patch creates one `Webstore` row from the current `Webstore Settings`, with
slug `store`, copies the per-store fields onto it, and stamps every existing
`Webstore Product`, `Cart`, `Wishlist` and `Category` with it. `/store` keeps
working because the slug is `store` — the old URL and the new scheme coincide
rather than needing a redirect.

## Error handling

| Condition | Behaviour |
|---|---|
| Unknown slug | 404 |
| Store unpublished | 404 for guests; visible to System Manager for preview |
| Product not in the requested store | 404, not a cross-store leak |
| No stores configured | The migrated default store; a fresh install creates one |
| Two stores claiming a slug | Refused on save |
| Slug colliding with an app route (`portal`, `api`, `app`, `assets`) | Refused on save |

## Testing

- Resolution: a slug maps to its store; unknown 404s; unpublished 404s for a guest.
- Isolation: a product in store A is not reachable under store B's prefix; a cart
  in A is untouched by activity in B; categories and prices resolve per store.
- The shared portal shows orders from both shops under one account.
- Checkout stamps the originating store on the Quotation and Sales Order.
- The migration: a site with one storefront keeps `/store` working, keeps its
  theme, and its existing products, carts and categories all land in the default
  store.
- Inert path: a single-store site behaves exactly as it does today throughout.

## Non-goals

- **Per-store customers or books.** One ERPNext, one customer list.
- **Per-store portals.** One account, one order history.
- **Subdomains or separate domains.** Path prefix only; host-based routing can
  layer on later without changing the store model.
- **Per-store stock.** Warehouses are already configurable per store; the stock
  itself stays ERPNext's.
