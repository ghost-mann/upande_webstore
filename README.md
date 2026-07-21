# Upande Webstore

E-commerce webstore and customer portal for **ERPNext v16**, built as a single custom Frappe app. Serves both retail (B2C) and business (B2B) customers: a public catalog with guest pricing, and logged-in accounts with customer-specific price lists, carts, wishlists, and a full self-service portal.

There is no online payment at launch. Checkout is **quotation-first**: placing an order creates a submitted ERPNext Quotation which the sales team reviews and converts to a Sales Order; payment is handled offline (invoice, bank transfer, credit terms). Customers can accept or decline their quotations from the portal.

## Requirements

- Frappe v16.x and ERPNext v16.x installed on the bench

## Instal

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
