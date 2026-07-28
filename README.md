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

## Customisation

One branch serves many client projects: every visual and structural choice that
differs between clients lives in Webstore Settings, not in code.

| Tab | What it controls |
|---|---|
| Theme | 13 color seeds → the full `--ws-*` set, fonts, radii, custom CSS |
| Branding | Logo, favicon, wordmark, hero copy, hero stats, category cards, footer |
| Features | 19 checkboxes; off = hidden **and** 404 **and** API rejected |
| Transfer | Export/import theme JSON, apply a shipped preset |

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

Nineteen flags in one registry (`upande_webstore/theme/features.py`), all
defaulting on, enforced at three layers so a disabled feature is genuinely
unreachable: the UI is hidden, the route raises 404, and the whitelisted API
methods throw. Turning off *Cart & Checkout* leaves a browse-only catalog;
turning off *Signup* also swaps the hero's guest CTA to **Member login** so it
cannot point at a dead route.

### Transfer

*Theme → Export Theme* downloads every Theme, Branding and Features value as
JSON; *Import Theme* applies an attached file; *Apply Preset* loads one of the
shipped presets in `upande_webstore/theme/presets/` (`mona_flowers`, `upande`).

Import is a **replace**: fields absent from the payload reset to their defaults,
so switching presets leaves no residue. General settings — company, price list,
warehouses — are never touched.

Images travel as **file URLs, not embedded bytes**, so an import reports which
attachments do not exist on the target site and need re-uploading. A fresh
install seeds the default preset; a site that already has a configured theme is
never restyled by a deploy.

## Publish products

For each sellable Item, create a **Webstore Product**: link the Item (templates with variants are supported), set the web title, description, image, and category (Item Group), then tick **Published**. Out-of-stock products are shown but cannot be ordered.

## Order flow

1. Customer signs up at `/signup` (creates User + Contact + Customer) or an existing ERPNext Customer gets portal access by linking a website User to their Contact.
2. Customer builds a cart at `/store` and checks out at `/cart` → a submitted **Quotation** is created and the sales team is emailed.
3. Customer accepts/declines the quotation at `/portal/quotations`; the sales team converts accepted quotations to Sales Orders in the desk.
4. Orders, invoices (with PDF download), account statement, support tickets, and profile/addresses are all available under `/portal`.

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
