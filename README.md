# Upande Webstore

E-commerce webstore and customer portal for **ERPNext v16**, built as a single custom Frappe app. Serves both retail (B2C) and business (B2B) customers: a public catalog with guest pricing, and logged-in accounts with customer-specific price lists, carts, wishlists, and a full self-service portal.


There is no online payment at launch. Checkout is **quotation-first**: placing an order creates a submitted ERPNext Quotation which the sales team reviews and converts to a Sales Order; payment is handled offline (invoice, bank transfer, credit terms). Customers can accept or decline their quotations from the portal.

## Requirements

- Frappe v16.x and ERPNext v16.x installed on the bench

## Install

```bash
cd your-bench
bench get-app /home/austin/vscodeProjects/upande_webstore   # or your git remote for this repo
bench --site <site> install-app upande_webstore
bench --site <site> migrate
cd apps/upande_webstore && npm install && npx @tailwindcss/cli -i upande_webstore/public/tailwind/input.css -o upande_webstore/public/css/tailwind.css --minify && cd ../..
bench build --app upande_webstore
```

After changing any template or the Tailwind theme, re-run the `@tailwindcss/cli` command above (add `--watch` during development). The storefront runtime is TypeScript (`public/js/webstore.bundle.ts`), compiled by `bench build`.

## Configure

Open **Webstore Settings** (single doctype) in the desk and set:

- **Company** — the selling company
- **Guest Price List** — prices shown to visitors and customers without their own price list
- **Stock Warehouses** — warehouses summed for availability display
- **Default Customer Group / Territory** — applied to self-service signups
- **Quotation Validity (Days)** — validity applied to web quotations
- **Stock Display** — In/Out badge or exact quantity
- **Sales Notification Emails** — comma-separated recipients notified of new web quotations and portal accept/decline actions

### Modules

Business features that only some projects use are **modules** on the
Webstore Settings → Modules tab. Each ships **off**; while off it adds no UI,
no routes and no reads of another app's doctypes, and its settings stay
hidden. Each can also be switched per storefront.

| Module | What it does |
|---|---|
| **Box Packing** | Buyers pick a box per line, the cart and the checkout panel show box fill, checkout refuses part-filled boxes and the order minimum, and Quotation / Sales Order lines record box type, pack rate and box count |
| **Customer Specifications** | A signed-in customer with packing specifications (upande_packhouse's `Specifications`) gets a **My specifications** switch on the store and orders against them; nobody else sees them |

### Where boxes come from

1. The **Boxes** table on the Modules tab, when it has rows: box name, stems
   per box, and optionally the site's own box record (a `Box Type` or box Item)
   to write to the order line. *Load boxes from this site* fills it from 2 or 3.
2. Otherwise **`Box Type` records** with a stem capacity above zero, if your
   site has that doctype and has filled it in.
3. Otherwise **Items** with *Is Box* ticked and a *Pack Rate* above zero.
4. Otherwise nothing — box packing stays inert, whatever the settings say.

The panel under the table names which source is in use, lists the usable boxes,
and lists the ones being hidden with the reason. This app never creates,
migrates or takes ownership of a `Box Type` doctype; it only reads one.

### Customer specifications

Read-only against the doctype named in settings (default `Specifications`); a
site without it keeps the module inert. A customer sees their own specs that
are Active, in date and have a primary variety. Each is ordered one of two ways:

- **By the box** — one primary variety and one pack rate: "3 boxes" becomes
  3 × pack rate stems of that variety.
- **By variety** — everything else: stems per primary variety. A mono box with
  one pack rate must be whole boxes per variety; a mixed box is checked for its
  colour count instead, and the packhouse confirms its box count.

Substitute varieties are not offered; the packhouse substitutes as it does now.
Lines price at the customer's rate for the spec's stem length where Item Price
carries `custom_length`, and reach the Sales Order as one line per variety with
`custom_line` (the spec), `custom_length`, and the spec's box type — the shape
the packhouse already reads. Where Selling Settings does not allow an item on
several lines, a variety ordered under two specs is refused with a basket
message.

### What install adds, and what it never touches

Install and every migrate are **create-only** for custom fields: a field the
site already has — whatever its type, link target or read-only flag — is left
exactly as it is and logged under *Error Log → Webstore custom fields skipped*.
Nothing this app installs can repoint `Sales Order Item.custom_box_type` away
from a farm's own `Box Type` doctype, or take an editable field away from the
staff who use it. The trade-off is that changing one of *our own* shipped field
definitions no longer rides along on `migrate`; it needs an explicit patch.

The `custom_box_type` fields on Quotation Item and Sales Order Item are Links
whose target is resolved per site from the box source above, so a farm running
`Box Type` records gets a Link to `Box Type`, not to `Item`. On a site with no
box source at all the field is not created — there is nothing to link to and
packing is inert.

Installing on a farm that has no box fields on `Item` **adds two columns to
`tabItem`** — `custom_is_box` and `custom_pack_rate` — the first of them
indexed. On a large item master that is a table alter worth scheduling.

## Customisation

One branch serves many client projects: every visual and structural choice that
differs between clients lives in Webstore Settings, not in code.

| Tab | What it controls |
|---|---|
| Theme | 13 color seeds → the full `--ws-*` set, fonts, radii, custom CSS |
| Branding | Logo, favicon, wordmark, hero copy, hero stats, category cards, footer |
| Features | 20 checkboxes; off = hidden **and** 404 **and** API rejected |
| Modules | Optional business modules (box packing, customer specifications), off by default |
| Transfer | Export/import theme JSON |

**Every field is optional and blank means "use the shipped default".** A site
with nothing filled in emits no CSS override block at all and renders exactly as
the shipped Ink & Gold design — so adopting this on an existing site changes
nothing until you start filling fields in.

### Theme

Set a few seeds and the rest is derived (`upande_webstore/theme/color.py`):

| Seed | Derives |
|---|---|
| **Accent** (+ optional Dark, Soft) | hover, light, deep, focus ring, accent gradient |
| **Ink / Neutral** | the seven-step ink scale, plus ink-tinted shadows |
| **Muted Text** | anchors the gray temperature — set this to keep cool or warm greys through derivation |
| **Page Canvas** | page background and the lifted surface tone |
| **Muted Fill**, **Border**, **Border (strong)** | sunken fills and hairlines; opaque when set, alpha-on-ink when blank |
| **Success / Warning / Danger / Info** | each fills its whole family (deep or brighter fill, plus a 12% soft tint) |

**Accent Drives Primary Actions** is the switch that matters for a non-black
brand. Off (shipped) the accent is decorative trim and ink paints buttons, active
nav pills and avatars. On, those action surfaces use the accent instead, while
ink keeps painting headings and body text.

Fonts: pick a bundled family (Poppins / Fraunces / IBM Plex Mono) or choose
*Custom*, name the family, and supply a Google Fonts URL. Only
`https://fonts.googleapis.com` is accepted, so the field cannot inject an
arbitrary remote origin into every page. Shape is three radius values, and
**Custom CSS** is emitted last inside `:root` as the escape hatch for anything
the seeds do not reach.

### Branding

Wordmark, subtitle, logo, favicon, all hero copy, and every footer string are
fields. Three child tables drive the repeating lists — **Hero Stats**,
**Category Cards** (label, subtitle, image, category or custom URL) and **Footer
Links** (rows group by their `Column` heading, in table order, so the number of
footer columns follows the data). An empty table omits its section rather than
rendering an empty shell. Defaults all live in one place,
`upande_webstore/theme/branding.py`.

### Features

Twenty flags in one registry (`upande_webstore/theme/features.py`), all
defaulting on (the two modules share the registry but default off), enforced at three layers so a disabled feature is genuinely
unreachable: the UI is hidden, the route raises 404, and the whitelisted API
methods throw. Turning off *Cart & Checkout* leaves a browse-only catalog;
turning off *Signup* also swaps the hero's guest CTA to **Member login** so it
cannot point at a dead route.

### Transfer

*Theme → Export Theme* downloads every Theme, Branding and Features value as
JSON; *Import Theme* applies an attached file. There are no shipped presets —
each project sets its own palette on the Theme tab, and an exported file is how
a look is carried to another site.

Import is a **replace**: fields absent from the payload reset to their defaults,
so importing one theme over another leaves no residue. General settings — company, price list,
warehouses — are never touched.

Images travel as **file URLs, not embedded bytes**, so an import reports which
attachments do not exist on the target site and need re-uploading. A fresh
install applies no theme, so it renders the shipped defaults until configured;
a deploy never restyles an existing site.

## Publish products

For each sellable Item, create a **Webstore Product**: link the Item (templates with variants are supported), set the web title, description, image, and category (Item Group), then tick **Published**. Out-of-stock products are shown but cannot be ordered.

## Order flow

1. Customer signs up at `/signup` (creates User + Contact + Customer) or an existing ERPNext Customer gets portal access by linking a website User to their Contact.
2. Customer builds a cart at `/store` and checks out at `/cart` → a submitted **Quotation** is created and the sales team is emailed.
3. Customer accepts/declines the quotation at `/portal/quotations`; the sales team converts accepted quotations to Sales Orders in the desk.
4. Orders, invoices (with PDF download), account statement, support tickets, and profile/addresses are all available under `/portal`.

Quotations and Sales Orders are created in the currency of the price list the
buyer was shown, at the buyer's own rates (resolved before the document is
built as Administrator). A direct Sales Order is a draft: freight fields other
apps make mandatory (upande_packhouse's delivery point, shipping agent,
consignee, truck) are left for the sales team, and submitting still enforces
them.

## Run tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app upande_webstore
```

## Development notes

- All prices and stock checks are resolved **server-side**; client values are never trusted.
- Every portal query is scoped to the session user's Customer (`upande_webstore/services/portal.py`) with isolation tests in `upande_webstore/tests/`.
- Frontend is server-rendered Jinja + Tailwind CSS v4 utilities + a bespoke component layer (`public/scss/webstore.bundle.scss`), with one TypeScript runtime bundle (`public/js/webstore.bundle.ts`) — no SPA.

## Contributing

This app uses `pre-commit` (ruff, eslint, prettier, pyupgrade):

```bash
cd apps/upande_webstore
pre-commit install
```

## License

MIT
