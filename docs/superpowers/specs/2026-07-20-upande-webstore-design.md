# Upande Webstore — Design Spec

**Date:** 2026-07-20
**Status:** Approved in design review
**Companion document:** `docs/01-architecture-description.docx` (architecture description)

## 1. Summary

A combined e-commerce storefront and customer portal built as a single custom Frappe app
(`upande_webstore`) installed on an ERPNext v16 bench. Serves both B2C and B2B customers.
No online payment at launch: checkout produces an ERPNext **Quotation** which the sales team
reviews and converts to a Sales Order; payment is handled offline.

## 2. Key decisions

| Decision | Choice |
|---|---|
| Platform | Custom Frappe app on the ERPNext v16 bench |
| Frontend | Server-rendered Jinja portal pages + lightweight JS modules (no SPA) |
| Audience | B2C and B2B; browsing is public, ordering requires an account |
| Order flow | Quotation-first: web checkout creates a Quotation |
| Payments | None at launch (offline payment) |
| Out-of-stock items | **Not orderable** — blocked at UI and API level |
| Signup | Auto-creates ERPNext Customer + Contact + portal User |

## 3. Application structure

One Frappe app `upande_webstore`:

- `www/` — storefront and portal routes (Jinja templates + Python page controllers)
- `upande_webstore/api/` — whitelisted REST endpoints (cart, wishlist, variant resolution,
  stock/price lookups, checkout, signup, support)
- Public JS/CSS bundled via Frappe's build system (`upande_webstore.bundle.js`)

## 4. Data model

### 4.1 New DocTypes (minimal — ERPNext is the system of record for everything transactional)

1. **Webstore Settings** (Single)
   - guest/default price list
   - warehouses used for stock display (child table or multiselect)
   - default Customer Group and Territory for signups
   - quotation validity days
   - stock display mode: exact quantity vs. in-stock/out-of-stock badge
   - sales notification recipient(s) for new web quotations
2. **Webstore Product** — the published-item record
   - link to ERPNext `Item` (template or standalone), unique
   - slug/route (unique), web title, short description, long description (rich text)
   - images (attach; first image is the card image)
   - published flag, featured flag
   - category (link to Item Group) used for filtering
3. **Webstore Cart**
   - owner (User), status: Open / Ordered / Abandoned
   - child table: Item, qty, resolved rate
   - invariant: at most one Open cart per user
4. **Webstore Wishlist**
   - one per user (owner = User)
   - child table of Webstore Product links with added-on date

### 4.2 Stock ERPNext DocTypes used as-is

Customer, Contact, Address, Item + Item variants + Item Attributes, Price List, Item Price,
Pricing Rule, Bin (stock), Quotation, Sales Order, Sales Invoice, Payment Entry, GL Entry
(statement), Issue.

## 5. Pricing resolution

One shared server-side function used by product pages, cart, wishlist, and checkout:

1. If the session user's Contact links to a Customer with a default price list → use it, then
   apply Pricing Rules via ERPNext's own pricing machinery (`get_price_list_rate` and related
   utilities).
2. Otherwise → guest price list from Webstore Settings.

**Security invariant:** prices are never trusted from the client. Every add-to-cart, cart
mutation, and checkout re-resolves prices server-side. Cart re-prices on every load.

## 6. Storefront

### Routes

- `/store` — catalog: paginated grid of published Webstore Products; search box (web title,
  item name, item code, description); category sidebar from the Item Group tree; featured
  section on page one.
- `/store/<slug>` — product detail page.
- `/cart` — cart review + checkout.
- `/wishlist` — saved products (login required).

### Product page

- Images, descriptions, price, stock badge.
- Variant templates render attribute pickers from ERPNext Item Attributes; selecting a
  combination calls a whitelisted endpoint that resolves the concrete variant Item and returns
  its price and stock. Add-to-cart disabled until a valid variant is selected.
- Wishlist heart toggle on product cards and product pages.

### Pricing display

Guests see the guest price list. Logged-in users with a Customer price list see their prices
with a "Your price" indicator.

### Stock display and out-of-stock policy

- Availability = sum of `Bin.actual_qty` across the warehouses configured in Webstore
  Settings; shown as exact qty or in/out badge per settings.
- **Out-of-stock items are not orderable:** add-to-cart is disabled in the UI *and* rejected
  by the add-to-cart endpoint. Checkout re-validates stock for every line and blocks
  submission with per-line messages ("X is no longer available") until the customer removes
  or adjusts those lines.

### Cart

- Navbar cart icon with item count.
- Add / change qty / remove are JS calls to whitelisted endpoints mutating the user's single
  Open Webstore Cart; responses return re-priced totals.
- Anonymous visitors browsing: add-to-cart prompts login/signup.

### Checkout (single page)

Cart summary; delivery address (pick from the Customer's Addresses or add new); optional
notes / PO reference; "Request Quotation" button. On submit, server-side:

1. Re-validate stock and re-resolve prices for every line.
2. Create a **submitted Quotation** against the user's Customer: validity days from settings,
   notes/PO reference carried into the quotation, linked to the Contact so it appears in the
   portal.
3. Mark the cart Ordered; show confirmation page linking to the quotation.
4. Notify the sales team (recipients from Webstore Settings) via email.

## 7. Customer portal

### Signup & auth

- `/signup`: name, email, phone, optional company name (given → Customer type Company, else
  Individual). Creates linked Frappe User (Website User), Contact, Customer (defaults from
  Webstore Settings). Standard Frappe email verification.
- Existing ERPNext customers get portal access by linking a portal User to their Contact —
  existing price list, credit terms, and history apply automatically.
- Frappe's built-in login and sessions. Every portal route resolves the session user's
  Customer via the Contact link and filters all queries by it, **enforced server-side**.

### Portal pages (`/portal`)

| Page | Content |
|---|---|
| Dashboard | Outstanding balance, open quotation count, recent orders, quick links |
| Quotations | List + detail; line items and totals; **Accept** (ERPNext portal acceptance → status Ordered) and **Decline** |
| Orders | Sales Orders list + detail; status, % delivered / % billed |
| Invoices | List + detail; PDF download via standard print format; paid/unpaid/overdue badges |
| Statement | Outstanding total; date-filtered account statement from GL entries; PDF download |
| Support | Issues list; raise new (subject, description, optional attachment); status and replies |
| Account | Profile details, addresses add/edit, change password |

## 8. Error handling

- All whitelisted endpoints validate inputs and permissions explicitly and return structured
  errors; the JS layer surfaces them as user-friendly messages.
- No behaviour relies on client-side checks alone (pricing, stock, cart ownership, customer
  scoping are all re-checked server-side).

## 9. Testing

Frappe test framework, server-side:

- Pricing resolver (guest vs. customer price list vs. pricing rules).
- Cart operations (add/update/remove, single-open-cart invariant, re-pricing).
- Stock validation (add-to-cart rejection, checkout re-validation).
- Checkout → Quotation creation (fields, validity, contact linkage, cart state transition).
- Signup record creation (User + Contact + Customer linkage, defaults).
- Wishlist operations.
- **Portal data isolation:** user A must never see user B's quotations, orders, invoices,
  statement, or issues.

## 10. Out of scope (launch)

- Online payments (M-Pesa/cards) — deferred; the quotation-first flow leaves a clean seam to
  add payment against invoices later.
- Guest checkout.
- Shipping rate calculation, coupon codes, product reviews.
