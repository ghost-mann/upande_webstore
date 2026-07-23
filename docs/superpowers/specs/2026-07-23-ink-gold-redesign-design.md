# Ink & Gold Redesign — Design

**Date:** 2026-07-23
**Status:** Approved

## Goal

Restyle the whole app — storefront and customer portal — to the "Mona Flowers"
dashboard design language supplied by the user: cream canvas, ink-black
neutrals, Poppins type, pill navigation, rounded white cards with soft
shadows, KPI cards with sparklines, and inline-SVG data visualizations.
The portal becomes a real app dashboard (sidebar shell); the storefront gets
the full app treatment with the same shell and components.

Decisions made with the user:

1. **Portal layout:** sidebar app shell (sticky sidebar card + main column).
2. **Color:** ink/cream neutrals are fixed; the Webstore Settings
   `primary_color` now drives the *accent* (default gold `#d9a514`).
3. **Storefront:** full app treatment (topbar, cream canvas, tile cards,
   filter sidebar card, inset rounded hero).
4. **Portal data:** real charts backed by new server-side aggregates.

## 1. Design system (tokens)

Expressed through the existing `--ws-*` variable layer in
`public/scss/webstore.bundle.scss`; templates never hardcode hex.

- **Neutrals (fixed):** ink scale `#0a0a0a`, `#1a1a18`, `#2a2a26`,
  `#3a3a34`, `#5a5a52`, `#8a8780`, `#b8b6ae`; canvas `#f4f3ef`; surface
  `#fafaf6`; card `#ffffff`; hairline `rgba(10,10,10,.06)`; template card
  and hover shadows.
- **Accent (configurable):** default gold `#d9a514`. `services/settings.py`
  derivation extends to also emit `accent_light` (mix toward white ~25%)
  and `accent_deep` (mix toward black ~25%) so the template's gold gradient
  (`#edc23c → #a87d0d`) is reproducible from any configured hue. Emitted
  vars: `--ws-accent`, `--ws-accent-hover`, `--ws-accent-soft`,
  `--ws-accent-light`, `--ws-accent-deep`, `--ws-ring`.
  The old `--ws-primary*` names remain as aliases of accent during the
  transition so nothing breaks mid-migration.
- **Semantic:** green `#3f8f4f`, amber `#d9962e`, red `#c4302b`, teal
  `#228883` (+ soft tints for chips).
- **Type:** Poppins 400–700 self-hosted (replacing IBM Plex Sans);
  Fraunces stays for storefront display headings; existing mono stack for
  SKUs/tabular amounts.
- **Shape:** cards radius 20–24px; pills 999px for nav/tabs/chips/buttons;
  primary buttons ink-filled (`--grad-ink` gradient), secondary ghost pills.
- `public/tailwind/input.css` shadcn/basecoat variable block remapped to
  the new values (drawer, palette, toasts inherit for free).

## 2. Shared shell (`templates/webstore_base.html`)

- Topbar per template: logo · hairline divider · wordmark
  ("upandestore" + small-caps subtitle "Store & Customer Portal"); pill nav
  (Store, Wishlist, Portal; active pill ink-filled); right: ⌘K search
  trigger, cart pill with badge, gradient-ink avatar with user initials
  (guest: Sign up / Member login pills).
- Footer, cart drawer, command palette keep structure; re-skinned (cream
  footer, hairline top, radius-24 panels).

## 3. Portal app shell (new `templates/webstore_portal_base.html`)

All portal pages extend a new intermediate base rendering the template's
two-column grid (264px sidebar / main, collapsing under 1100px):

- **Sidebar card (sticky, radius 24):** nav — Dashboard, Quotations
  (count badge), Orders, Invoices (count badge), Statement, Support,
  Claims, Account — with inline-SVG icons; active link gets `--grad-ink`.
  Below: "At a glance" stats (Outstanding balance, Open quotations,
  Orders in progress) and a user card (avatar, customer name,
  "Customer since YYYY", gear → /portal/account).
- **Main column:** template pagehead — eyebrow
  ("Upande Store · Customer Portal"), 44px title, sub-line, right tools
  slot.
- Sidebar counts come from `get_sidebar_counts()` injected by each portal
  controller via one shared helper (single cheap query set per request).
- `webstore_portal_nav.html` and `webstore_portal_hero.html` are deleted.

## 4. Portal dashboard (`/portal`)

- **KPI row (4 template `.kpi` cards with corner sparklines):**
  Outstanding balance, Open quotations (with "N expiring soon" pill),
  Orders in progress, Spend last 12 months (with % vs prior-period pill).
- **Row 2 (2fr/1fr):** 12-month spend trend SVG area chart (accent
  gradient fill = invoiced, ink line = paid) built exactly like the
  template chart (grid lines, axis labels, end dots); Top items ranked
  list (`.list__row`, gold lead chip) linking to product pages.
- **Row 3 (1fr/1fr):** Quotation mix donut (ring-segment dasharray
  technique, center total); Recent orders as list rows with status chips.
- Empty states for new customers on every card; charts never render broken
  with zero/one data point.

## 5. Portal list & detail pages

- Lists (quotations, orders, invoices, claims, support): card with
  `card__head` (title + count meta) and `.list__row` rows — chip, name +
  meta line, right-aligned amount with sub-label, status `sev` pill.
  Existing filters become pill chips above the list.
- Details (quotation, order, invoice, issue): `backbtn` pill, pagehead
  with doc name, `tile__stats` facts grid, hairline items table,
  accept/decline as ink/ghost pills, invoice PDF pill.
- Statement: table in a card + running-balance mini-chart in card head.
- Account: profile + addresses as `.tile` cards in a `tilegrid`.

## 6. Storefront

- **/store:** photographic hero inset (rounded-24, framed on cream canvas);
  Fraunces headline kept. Category photo cards with template hover-lift.
  Catalog: filter sidebar card (search + category chips with count badges,
  `side__chip` style); product grid of `.tile` cards (image, mono SKU,
  title, price with accent "Your price" chip, stock LED chip); pill
  pagination. Process band as three ink tiles with ghost numerals.
- **Product page:** two-column cards (gallery + details); variant pills;
  qty stepper + ink "Add to basket"; stock/price chips.
- **Cart:** items card with list rows + sticky summary card (subtotal,
  quotation-first note, PO reference field, ink "Request quotation").
- **Wishlist / signup:** same card treatment; signup as centered card.

## 7. Data layer (`services/portal_data.py` + new `services/charts.py`)

New read-only, customer-scoped functions using the existing
`portal_guard`/`get_customer_docs` scoping pattern:

- `get_monthly_spend(months=12)` → `[{month, invoiced, paid}]` from
  submitted Sales Invoices (paid = invoiced − outstanding per invoice).
- `get_quotation_mix()` → counts by bucket (Open, Accepted/Ordered,
  Declined/Lost, Expired).
- `get_orders_in_progress_count()` → submitted SOs not
  Completed/Closed/Cancelled.
- `get_top_items(limit=5)` → Sales Order Item qty sums joined to
  Webstore Product for routes.
- `get_sidebar_counts()` → open quotations + unpaid invoices.

`services/charts.py` computes SVG geometry (area-chart path points, donut
dasharrays, sparkline points) so templates stay declarative.

**Tests:** isolation tests (customer A never sees customer B) and shape
tests per function, mirroring `test_portal_scope.py`; geometry unit tests
for `charts.py` (empty series, single point, all-zero).

## 8. Unchanged

Controller context contracts (additive only), API endpoints, TS runtime
(`data-ws-*` hooks keep names), quotation-first flow, appearance image
fields. Only `primary_color` *meaning* shifts to accent — README updated.

## Verification

Tailwind + SCSS rebuild, `bench build`, full app test suite, and a
real-screenshot QA pass on webstore.localhost:8003 (store, product, cart,
portal dashboard, quotations list, invoice detail) against the template.
