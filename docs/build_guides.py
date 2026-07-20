"""Generate the Upande Webstore user and developer guides as .docx.

Run: /usr/bin/python3 docs/build_guides.py  (needs python-docx)
"""
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))


def new_doc(title, subtitle):
	doc = Document()
	style = doc.styles["Normal"]
	style.font.name = "Calibri"
	style.font.size = Pt(11)
	doc.add_heading(title, level=0)
	p = doc.add_paragraph()
	p.alignment = WD_ALIGN_PARAGRAPH.LEFT
	r = p.add_run(subtitle)
	r.font.size = Pt(13)
	r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
	meta = doc.add_paragraph()
	r = meta.add_run("Upande Webstore for ERPNext v16  |  20 July 2026")
	r.font.size = Pt(9)
	r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
	return doc


def h(doc, text, level=1):
	doc.add_heading(text, level=level)


def p(doc, text, bold_lead=None):
	par = doc.add_paragraph()
	if bold_lead:
		r = par.add_run(bold_lead)
		r.bold = True
	par.add_run(text)
	return par


def bullet(doc, text, bold_lead=None):
	par = doc.add_paragraph(style="List Bullet")
	if bold_lead:
		r = par.add_run(bold_lead)
		r.bold = True
	par.add_run(text)
	return par


def num(doc, text, bold_lead=None):
	par = doc.add_paragraph(style="List Number")
	if bold_lead:
		r = par.add_run(bold_lead)
		r.bold = True
	par.add_run(text)
	return par


def code(doc, text):
	par = doc.add_paragraph()
	r = par.add_run(text)
	r.font.name = "Consolas"
	r.font.size = Pt(9)
	return par


# ======================================================================
# USER GUIDE
# ======================================================================
doc = new_doc("Upande Webstore — User Guide", "For customers and for the Upande sales & operations team")

h(doc, "Part 1 — For Customers", 1)

h(doc, "1. Creating your account", 2)
num(doc, "Open the store and click Sign up (or the Member login button if you already have credentials).")
num(doc, "Fill in your name, email and phone. If you are buying for a company, enter the company name — your account and all documents will be registered to it.")
num(doc, "You will receive an email to set your password. If it does not arrive, contact the sales team — they can set portal access for you directly.")
p(doc, "If your company already trades with Upande, ask the sales team to link a portal login to your existing customer account — your agreed price list, credit terms and full document history apply automatically.", bold_lead="Existing customers: ")

h(doc, "2. Browsing and searching the catalog", 2)
bullet(doc, "The Store page lists all published products with live prices and stock availability. Filter by category (Flowers, Coffee, Fresh Produce) in the sidebar, or use the search box.")
bullet(doc, "Press Ctrl+K (⌘K on Mac) or the search field in the top bar from any page to open the quick search — type at least two letters, use the arrow keys, and press Enter to open a product.")
bullet(doc, "A green dot means the item is in stock; a grey dot means it is currently unavailable and cannot be ordered. Products with options (e.g. sizes) show the price after you select a combination.")
bullet(doc, "If you are logged in and your company has an agreed price list, you will see your prices, marked “Your price”.")

h(doc, "3. Basket and requesting a quotation", 2)
num(doc, "On a product page choose a quantity and click Add to cart. The Basket in the top bar opens a side panel where you can adjust quantities or remove lines at any time.")
num(doc, "When ready, open the Basket and click “Review & request quotation”. On the checkout page choose a delivery address, optionally add your PO reference and notes, and click Request Quotation.")
num(doc, "Nothing is charged and no stock is committed at this point: your request creates a quotation which the sales team reviews and confirms — usually within one working day.")
p(doc, "Prices shown in the basket are always re-confirmed by the server when the quotation is created; quantities are checked against live stock at that moment.", bold_lead="Good to know: ")

h(doc, "4. Your portal", 2)
p(doc, "Click My Portal (or Member login) to reach your dashboard. It shows your outstanding balance, open quotations, and recent orders. The tabs along the top take you to:")
bullet(doc, "list of your quotations with status. Open one to review line items and totals, then Accept or Decline it. Accepting notifies the sales team, who convert it into a confirmed order.", bold_lead="Quotations — ")
bullet(doc, "confirmed sales orders with delivery and billing progress.", bold_lead="Orders — ")
bullet(doc, "all invoices with due dates and status (paid / unpaid / overdue). Each invoice can be downloaded as a PDF.", bold_lead="Invoices — ")
bullet(doc, "a date-filtered account statement with running balance, printable to PDF.", bold_lead="Statement — ")
bullet(doc, "raise general support tickets and follow the team's replies.", bold_lead="Support — ")
bullet(doc, "report a problem with a delivery: choose the type (damaged goods, short delivery, quality below grade, billing error, other), reference the order or invoice concerned, describe what happened and attach photos. Claims are tracked separately from support tickets.", bold_lead="Claims — ")
bullet(doc, "update your name and phone, manage delivery addresses, change your password, and log out.", bold_lead="Account — ")

h(doc, "Part 2 — For the Upande Sales & Operations Team", 1)

h(doc, "5. One-time configuration", 2)
p(doc, "In the desk, open Webstore Settings and set:")
bullet(doc, "Company, Guest Price List (what visitors see), and the warehouses whose stock counts toward availability.")
bullet(doc, "Default Customer Group and Territory applied to self-service signups.")
bullet(doc, "Quotation validity in days, stock display mode (badge or exact quantity), and the notification email(s) that receive new webstore quotations, acceptances, declines and claims.")

h(doc, "6. Publishing products", 2)
num(doc, "Create the Item in ERPNext as usual (templates with variants are supported), with an Item Price on the guest price list and any customer price lists.")
num(doc, "Create a Webstore Product: link the Item, write the web title and descriptions, attach a photo, set the category (Item Group), and tick Published.")
num(doc, "Tick Featured to place the product in the “Available this week” card on the store homepage.")
p(doc, "Products with zero stock across the configured warehouses remain visible but cannot be ordered. Customer-specific pricing needs no extra setup — the store reads the customer's default price list and ERPNext pricing rules.", bold_lead="Notes: ")

h(doc, "7. Handling webstore documents", 2)
bullet(doc, "arrive as submitted Quotations (order type “Shopping Cart”) with the customer's PO reference and notes in the Webstore section. You are notified by email. Review, adjust if needed, and use Create > Sales Order once agreed.", bold_lead="New quotation requests ")
bullet(doc, "set the quotation's Portal Status field and add a comment; you are notified. Convert accepted quotations promptly.", bold_lead="Customer accept/decline ")
bullet(doc, "appear as Issues with type “Claim”; ordinary support tickets have no type. Replies you send on the Issue are visible to the customer in their portal.", bold_lead="Claims ")
bullet(doc, "to give an existing ERPNext customer portal access, open one of their Contacts, set its User field to a website user with the Customer role.", bold_lead="Portal access ")

doc.save(os.path.join(HERE, "02-user-guide.docx"))
print("saved 02-user-guide.docx")

# ======================================================================
# DEVELOPER GUIDE
# ======================================================================
doc = new_doc("Upande Webstore — Developer Guide", "Architecture, stack, environment and maintenance handbook")

h(doc, "1. What this app is", 1)
p(doc, "upande_webstore is a single custom Frappe app for ERPNext v16 providing a B2B/B2C storefront and customer portal. Checkout is quotation-first (no online payments): the cart becomes a submitted ERPNext Quotation which the sales team converts to a Sales Order. ERPNext remains the system of record; the app adds four DocTypes and a thin service/API layer. See docs/01-architecture-description.docx and docs/superpowers/specs/ for the original design.")

h(doc, "2. Repository layout", 1)
code(doc, "upande_webstore/\n"
	"  api/        whitelisted endpoints: cart, checkout, account (signup/profile/address),\n"
	"              variants, wishlist, portal (accept/decline/invoice PDF), support (+claims), search\n"
	"  services/   business logic: settings, pricing, stock, catalog, portal (scoping),\n"
	"              portal_data, statement\n"
	"  upande_webstore/doctype/   Webstore Settings, Webstore Product, Webstore Cart(+Item),\n"
	"              Webstore Wishlist(+Item), Webstore Warehouse\n"
	"  www/        store, cart, signup, wishlist + www/portal/* pages (Jinja + controllers)\n"
	"  templates/  webstore_base.html (navbar/footer/dialogs), includes (portal hero/nav/macros),\n"
	"              generators/webstore_product.html\n"
	"  public/     js/webstore.bundle.ts, scss/webstore.bundle.scss, tailwind/input.css,\n"
	"              css/tailwind.css (built), fonts/, images/\n"
	"  tests/      integration tests + shared fixtures in tests/utils.py\n"
	"  setup/install.py   Quotation custom fields (after_install/after_migrate)")

h(doc, "3. Development environment", 1)
bullet(doc, "bench at ~/frappe-v16-bench (frappe & erpnext v16.27.0); dev site webstore.localhost (Administrator/admin).", bold_lead="Bench: ")
bullet(doc, "the bench has serve_default_site=kaitet.local on port 8002, so the webstore is served by a dedicated process: bench --site webstore.localhost serve --port 8003. Restart it after reboots; do not change the bench default.", bold_lead="Port 8003: ")
bullet(doc, "canonical working copy is ~/frappe-v16-bench/apps/upande_webstore; git origin is /home/austin/vscodeProjects/upande_webstore (receive.denyCurrentBranch=updateInstead, so pushing updates that checkout).", bold_lead="Git: ")
bullet(doc, "if working from a Flatpak-sandboxed editor, bench/DB commands must run on the host: flatpak-spawn --host bash -lc '<command>'. Also note bash -lc does not source nvm — source ~/.nvm/nvm.sh before bench build.", bold_lead="Sandbox: ")
bullet(doc, "demo portal login demo@upande.com / Upande!Demo#2026; MariaDB root password on this dev machine is 'root'.", bold_lead="Dev credentials: ")

h(doc, "4. Frontend stack and build", 1)
bullet(doc, "shadcn/ui visual spec: white background, zinc neutrals (border #e4e4e7, muted #71717a), primary green #166534, Inter, radius 0.625rem, shadow-xs/sm. No emoji, no gradients.", bold_lead="Design system: ")
bullet(doc, "tokens and shadcn variables live in public/tailwind/input.css (imports tailwind theme+utilities and basecoat-css). Rebuild after template/theme changes:", bold_lead="Tailwind v4: ")
code(doc, "cd apps/upande_webstore   # npm install (first time)\nnpx @tailwindcss/cli -i upande_webstore/public/tailwind/input.css \\\n    -o upande_webstore/public/css/tailwind.css --minify   # add --watch in dev")
bullet(doc, "bespoke components (ws-* classes: cards, tables, hero, portal tabs, drawer, palette, toasts) live in public/scss/webstore.bundle.scss, compiled by bench build.", bold_lead="Component layer: ")
bullet(doc, "public/js/webstore.bundle.ts (frappe esbuild compiles .bundle.ts natively). Exposes window.webstore = { addToCart, toggleWishlist, refreshCartBadge, openCart, openPalette, call, toast }. Interactive components: ⌘K command palette (api.search.search_products), slide-over basket drawer, sonner-style toasts. Native <dialog> elements; Esc/backdrop close; prefers-reduced-motion respected.", bold_lead="TypeScript runtime: ")
code(doc, "bench build --app upande_webstore && bench --site webstore.localhost clear-website-cache")
bullet(doc, "hooks.py: web_include_css = [webstore.bundle.css, /assets/upande_webstore/css/tailwind.css], web_include_js = webstore.bundle.js. These load on ALL website pages of the site.", bold_lead="Includes: ")

h(doc, "5. Backend invariants", 1)
bullet(doc, "prices are NEVER trusted from the client. services/pricing.get_item_price() resolves via erpnext get_item_details (price list + pricing rules); the cart re-prices on every read/mutation; checkout re-resolves again.", bold_lead="Pricing: ")
bullet(doc, "out-of-stock items are not orderable — enforced in api/cart.add_item/update_qty AND re-validated in api/checkout.place_order (services/stock sums Bin.actual_qty over configured warehouses).", bold_lead="Stock: ")
bullet(doc, "every portal read goes through services/portal.py: get_current_customer() (session user → Contact → Customer), get_customer_docs() (always injects the customer filter) and assert_customer_doc() (403 on other customers' documents). Never query transactional doctypes in a portal page without these.", bold_lead="Isolation: ")
bullet(doc, "checkout and invoice-PDF rendering run under temporarily elevated context (frappe.set_user Administrator in try/finally) AFTER ownership checks, because ERPNext's account/print permission checks have no website-user path.", bold_lead="Elevation pattern: ")
bullet(doc, "claims are Issues with issue_type='Claim' (created idempotently); support lists exclude them in Python because SQL != misses NULL issue_type.", bold_lead="Claims: ")

h(doc, "6. ERPNext v16 gotchas (hard-won)", 1)
bullet(doc, "frappe.get_all rejects SQL strings like sum(x) or count(x) in fields — aggregate in Python or use query builder.")
bullet(doc, "WebsiteGenerator.autoname sets the scrubbed route name; combined with autoname='field:web_title' the field itself gets overwritten by _sync_autoname_field — do not add field: autoname to website generator doctypes.")
bullet(doc, "Override validate() with super().validate() in WebsiteGenerator subclasses or routes never get set.")
bullet(doc, "GET /?cmd=web_logout returns 403 (POST-only since v16) — log out via POST /api/method/logout with CSRF token.")
bullet(doc, "erpnext get_balance_on requires desk permissions — the portal computes balances/statements directly from GL Entry.")
bullet(doc, "@rate_limit decorates sign_up (20/hour/IP); frappe.rate_limiter.apply_for does not exist.")
bullet(doc, "Fresh sites: if erpnext's after_install did not complete, Customer role may keep desk_access=1 (breaking website-user creation) and Contact custom fields may be missing — re-run erpnext.setup.install.after_install.")
bullet(doc, "Stock Reconciliation on an empty site trips opening-entry account validation — test fixtures use Material Receipt/Issue Stock Entries instead.")
bullet(doc, "wkhtmltopdf needs a resolvable host for assets — site_config host_name is set to http://127.0.0.1:8003.")

h(doc, "7. Testing", 1)
code(doc, "bench --site webstore.localhost set-config allow_tests true   # once\nbench --site webstore.localhost run-tests --app upande_webstore  # full suite (62 tests)\nbench --site webstore.localhost run-tests --module upande_webstore.tests.test_cart")
p(doc, "Shared fixtures live in upande_webstore/tests/utils.py (setup_webstore_settings, make_test_product, make_portal_user, make_item_price, set_stock, make_variant_template). Every portal feature has cross-customer isolation tests — keep that bar when adding endpoints.")

h(doc, "8. Common tasks", 1)
bullet(doc, "add the page under www/portal/ (controller calls portal_guard(route) first), set portal_active/portal_title in a hero block including webstore_portal_hero.html, add the tab in templates/includes/webstore_portal_nav.html, write an isolation test.", bold_lead="New portal page: ")
bullet(doc, "add a function in api/, decorate @frappe.whitelist (methods=['POST'] for mutations), call _require_login()/get_current_customer() as appropriate, never trust client prices/quantities beyond validation.", bold_lead="New API: ")
bullet(doc, "change tokens in ONE of two places: shadcn/tailwind vars in public/tailwind/input.css, ws-* component vars in public/scss/webstore.bundle.scss (:root block). Rebuild both pipelines.", bold_lead="Theme change: ")
bullet(doc, "payments (M-Pesa/cards) were deliberately deferred: the seam is after invoice creation — add a payment gateway integration against Sales Invoice outstanding amounts; nothing in checkout needs to change.", bold_lead="Adding payments later: ")

doc.save(os.path.join(HERE, "03-developer-guide.docx"))
print("saved 03-developer-guide.docx")
