# Upande Webstore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** E-commerce storefront + customer portal as a custom Frappe app (`upande_webstore`) on ERPNext v16 — quotation-first checkout, no online payments.

**Architecture:** Server-rendered Jinja portal pages (`www/`) + whitelisted API endpoints (`api/`) + thin service layer (`services/`) that wraps ERPNext pricing/stock. Four new DocTypes (Webstore Settings, Webstore Product, Webstore Cart, Webstore Wishlist); everything transactional stays in stock ERPNext DocTypes. Spec: `docs/superpowers/specs/2026-07-20-upande-webstore-design.md`.

**Tech Stack:** Frappe v16.27.0, ERPNext v16.27.0, Python 3.14 (bench env), Jinja, vanilla JS bundled by Frappe esbuild.

## Global Constraints

- Bench: `/home/austin/frappe-v16-bench` — all `bench` commands run from there.
- Site: `webstore.localhost` (dedicated dev site; created in Task 1).
- Canonical working copy: `/home/austin/frappe-v16-bench/apps/upande_webstore`. Git origin is `/home/austin/vscodeProjects/upande_webstore` (configured with `receive.denyCurrentBranch=updateInstead` in Task 1). **Every task ends with commit AND `git push origin main`.**
- All file paths in tasks are relative to `/home/austin/frappe-v16-bench/apps/upande_webstore/` unless absolute.
- Python module root inside the app: `upande_webstore/` (so e.g. `upande_webstore/services/pricing.py`).
- Module name for all DocTypes: `Upande Webstore`.
- **Prices and stock are NEVER trusted from the client** — every API mutation re-resolves server-side.
- **Every portal/API read is filtered by the session user's Customer** — enforced server-side, with isolation tests.
- Out-of-stock items are not orderable: rejected at add-to-cart API and re-validated at checkout.
- Tests: `frappe.tests.IntegrationTestCase`, run via `bench --site webstore.localhost run-tests --module <module>`. Site has `allow_tests: true`.
- Test naming: service/API tests live in `upande_webstore/tests/test_*.py` (package with `__init__.py`).
- Commit messages: conventional commits (`feat:`, `test:`, `chore:`), each ending with the line `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Manual page checks assume `bench start` is running (Task 1 Step 7); pages fetched with `curl -s -H "Host: webstore.localhost" http://127.0.0.1:8000/<route>`.

---

### Task 1: Site + app scaffold + git wiring

**Files:**
- Create: entire app skeleton via `bench new-app` (hooks.py, pyproject.toml, `upande_webstore/` package)
- Create: `upande_webstore/tests/__init__.py`, `upande_webstore/services/__init__.py`, `upande_webstore/api/__init__.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: installed app `upande_webstore` on site `webstore.localhost`; git origin wiring; package dirs `upande_webstore.services`, `upande_webstore.api`, `upande_webstore.tests` that all later tasks import from.

- [ ] **Step 1: Create the site**

```bash
cd /home/austin/frappe-v16-bench
bench new-site webstore.localhost --admin-password admin --install-app erpnext
```

This prompts for the MariaDB root password (ask the human operator if unknown). Expected: ends with site creation success and ERPNext installed.

Then complete ERPNext onboarding non-interactively:

```bash
bench --site webstore.localhost execute frappe.utils.install.complete_setup_wizard
bench --site webstore.localhost set-config allow_tests true
```

Verify a Company exists (setup wizard creates one):

```bash
bench --site webstore.localhost execute frappe.client.get_list --kwargs '{"doctype":"Company","fields":["name"]}'
```

Expected: JSON with at least one company name. Note it — tests use `frappe.defaults.get_global_default("company")` so the exact name doesn't matter.

- [ ] **Step 2: Scaffold the app**

```bash
cd /home/austin/frappe-v16-bench
bench new-app upande_webstore
```

Prompt answers: Title `Upande Webstore`, Description `E-commerce webstore and customer portal for ERPNext v16`, Publisher `Upande`, Email `james@upande.com`, License `mit`, branch `main`, no GitHub workflow.

- [ ] **Step 3: Wire git to the canonical repo**

```bash
git -C /home/austin/vscodeProjects/upande_webstore config receive.denyCurrentBranch updateInstead
cd /home/austin/frappe-v16-bench/apps/upande_webstore
rm -rf .git
git init -b main
git remote add origin /home/austin/vscodeProjects/upande_webstore
git pull origin main
```

Expected: `docs/` from the design repo now present alongside the scaffold. Run `git status` — scaffold files show as untracked.

- [ ] **Step 4: Add package dirs**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
mkdir -p upande_webstore/tests upande_webstore/services upande_webstore/api
touch upande_webstore/tests/__init__.py upande_webstore/services/__init__.py upande_webstore/api/__init__.py
```

- [ ] **Step 5: Install app on the site**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost install-app upande_webstore
bench --site webstore.localhost migrate
```

Expected: no traceback.

- [ ] **Step 6: Smoke test**

```bash
bench --site webstore.localhost execute frappe.get_installed_apps
```

Expected output includes `"upande_webstore"`.

- [ ] **Step 7: Start the dev server (leave running in background for page checks)**

```bash
cd /home/austin/frappe-v16-bench && nohup bench start > /tmp/bench-start.log 2>&1 &
sleep 15 && curl -s -o /dev/null -w "%{http_code}" -H "Host: webstore.localhost" http://127.0.0.1:8000/login
```

Expected: `200`.

- [ ] **Step 8: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "chore: scaffold upande_webstore frappe app

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 2: Webstore Settings DocType

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_settings/__init__.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_warehouse/__init__.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_warehouse/webstore_warehouse.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_warehouse/webstore_warehouse.py`
- Test: `upande_webstore/tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 package layout.
- Produces: Single DocType `Webstore Settings` with fields `company` (Link Company), `guest_price_list` (Link Price List), `warehouses` (Table of child `Webstore Warehouse` with field `warehouse`), `default_customer_group` (Link Customer Group), `default_territory` (Link Territory), `quotation_validity_days` (Int, default 14), `stock_display` (Select: `In/Out Badge`, `Exact Quantity`), `notification_emails` (Small Text). Helper `upande_webstore.services.settings.get_settings()` returning the cached single doc, and `upande_webstore.tests.utils.setup_webstore_settings()` used by every later test module.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/utils.py`:

```python
import frappe


def setup_webstore_settings():
	"""Point Webstore Settings at standard test-site records; return the doc."""
	settings = frappe.get_doc("Webstore Settings")
	settings.company = frappe.defaults.get_global_default("company")
	settings.guest_price_list = "Standard Selling"
	settings.default_customer_group = "Individual"
	settings.default_territory = "All Territories"
	settings.quotation_validity_days = 14
	settings.stock_display = "In/Out Badge"
	settings.set("warehouses", [])
	settings.append("warehouses", {"warehouse": get_default_warehouse()})
	settings.save(ignore_permissions=True)
	frappe.clear_cache()
	return settings


def get_default_warehouse():
	company = frappe.defaults.get_global_default("company")
	return frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "warehouse_name": "Stores"}, "name"
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
```

`upande_webstore/tests/test_settings.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestWebstoreSettings(IntegrationTestCase):
	def test_settings_roundtrip(self):
		settings = setup_webstore_settings()
		self.assertEqual(settings.quotation_validity_days, 14)
		from upande_webstore.services.settings import get_settings

		cached = get_settings()
		self.assertEqual(cached.guest_price_list, "Standard Selling")
		self.assertTrue(cached.warehouses)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_settings
```

Expected: ERROR — `Webstore Settings` DocType does not exist.

- [ ] **Step 3: Create the DocTypes**

`upande_webstore/upande_webstore/doctype/webstore_warehouse/webstore_warehouse.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Warehouse",
 "module": "Upande Webstore",
 "istable": 1,
 "engine": "InnoDB",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["warehouse"],
 "fields": [
  {"fieldname": "warehouse", "fieldtype": "Link", "label": "Warehouse", "options": "Warehouse", "reqd": 1, "in_list_view": 1}
 ],
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`upande_webstore/upande_webstore/doctype/webstore_warehouse/webstore_warehouse.py`:

```python
from frappe.model.document import Document


class WebstoreWarehouse(Document):
	pass
```

`upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Settings",
 "module": "Upande Webstore",
 "issingle": 1,
 "engine": "InnoDB",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["company", "guest_price_list", "default_customer_group", "default_territory", "quotation_validity_days", "stock_display", "notification_emails", "warehouses"],
 "fields": [
  {"fieldname": "company", "fieldtype": "Link", "label": "Company", "options": "Company", "reqd": 1},
  {"fieldname": "guest_price_list", "fieldtype": "Link", "label": "Guest Price List", "options": "Price List", "reqd": 1},
  {"fieldname": "default_customer_group", "fieldtype": "Link", "label": "Default Customer Group (Signups)", "options": "Customer Group"},
  {"fieldname": "default_territory", "fieldtype": "Link", "label": "Default Territory (Signups)", "options": "Territory"},
  {"fieldname": "quotation_validity_days", "fieldtype": "Int", "label": "Quotation Validity (Days)", "default": "14"},
  {"fieldname": "stock_display", "fieldtype": "Select", "label": "Stock Display", "options": "In/Out Badge\nExact Quantity", "default": "In/Out Badge"},
  {"fieldname": "notification_emails", "fieldtype": "Small Text", "label": "Sales Notification Emails (comma-separated)"},
  {"fieldname": "warehouses", "fieldtype": "Table", "label": "Stock Warehouses", "options": "Webstore Warehouse"}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py`:

```python
from frappe.model.document import Document


class WebstoreSettings(Document):
	pass
```

Add `__init__.py` (empty) in both doctype folders.

`upande_webstore/services/settings.py`:

```python
import frappe


def get_settings():
	return frappe.get_cached_doc("Webstore Settings")


def get_warehouses():
	return [row.warehouse for row in get_settings().warehouses]
```

Then migrate:

```bash
cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_settings
```

Expected: `OK` (1 test).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add Webstore Settings doctype and settings service

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 3: Webstore Product DocType (website generator)

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_product/__init__.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py`
- Create: `upande_webstore/templates/generators/webstore_product.html` (placeholder; real template in Task 12)
- Test: `upande_webstore/tests/test_product.py`

**Interfaces:**
- Consumes: `setup_webstore_settings` from Task 2.
- Produces: DocType `Webstore Product` (WebsiteGenerator) with fields `item` (Link Item, unique), `web_title` (Data, reqd), `published` (Check), `featured` (Check), `category` (Link Item Group), `short_description` (Small Text), `long_description` (Text Editor), `image` (Attach Image), `route` (Data). Routes are `store/<scrubbed-web-title>`. Test helper `upande_webstore.tests.utils.make_test_product(item_code, **kwargs)` that creates the Item (with `is_stock_item=1`, `stock_uom=Nos`) and a published Webstore Product — used by every later test module.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/utils.py`:

```python
def make_test_item(item_code, **kwargs):
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": kwargs.pop("item_group", "Products"),
		"stock_uom": "Nos",
		"is_stock_item": kwargs.pop("is_stock_item", 1),
		**kwargs,
	})
	item.insert(ignore_permissions=True)
	return item


def make_test_product(item_code, **kwargs):
	item = make_test_item(item_code, **{k: v for k, v in kwargs.items() if k in ("has_variants", "attributes", "item_group", "is_stock_item")})
	existing = frappe.db.get_value("Webstore Product", {"item": item.name})
	if existing:
		return frappe.get_doc("Webstore Product", existing)
	product = frappe.get_doc({
		"doctype": "Webstore Product",
		"item": item.name,
		"web_title": kwargs.get("web_title", item_code),
		"published": kwargs.get("published", 1),
		"featured": kwargs.get("featured", 0),
		"category": item.item_group,
		"short_description": kwargs.get("short_description", f"Short blurb for {item_code}"),
	})
	product.insert(ignore_permissions=True)
	return product
```

`upande_webstore/tests/test_product.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_test_product, setup_webstore_settings


class TestWebstoreProduct(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def test_route_generated_from_web_title(self):
		product = make_test_product("WS-TEST-WIDGET", web_title="Test Widget Pro")
		self.assertEqual(product.route, "store/test-widget-pro")

	def test_item_must_be_unique(self):
		make_test_product("WS-TEST-UNIQUE")
		duplicate = frappe.get_doc({
			"doctype": "Webstore Product",
			"item": "WS-TEST-UNIQUE",
			"web_title": "Duplicate",
			"published": 1,
		})
		self.assertRaises(frappe.UniqueValidationError, duplicate.insert)

	def test_unpublished_product_not_rendered(self):
		product = make_test_product("WS-TEST-HIDDEN", web_title="Hidden Item", published=0)
		from frappe.utils import get_html_for_route

		html = get_html_for_route(product.route)
		self.assertNotIn("Hidden Item price", html)
```

Note: the third test uses the placeholder generator template created below, which renders `{{ web_title }} price`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_product
```

Expected: ERROR — `Webstore Product` DocType does not exist.

- [ ] **Step 3: Create the DocType**

`upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Product",
 "module": "Upande Webstore",
 "engine": "InnoDB",
 "autoname": "field:web_title",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "has_web_view": 1,
 "allow_guest_to_view": 1,
 "is_published_field": "published",
 "field_order": ["item", "web_title", "published", "featured", "category", "route", "image", "short_description", "long_description"],
 "fields": [
  {"fieldname": "item", "fieldtype": "Link", "label": "Item", "options": "Item", "reqd": 1, "unique": 1, "in_list_view": 1},
  {"fieldname": "web_title", "fieldtype": "Data", "label": "Web Title", "reqd": 1, "unique": 1, "in_list_view": 1},
  {"fieldname": "published", "fieldtype": "Check", "label": "Published", "default": "0", "in_list_view": 1},
  {"fieldname": "featured", "fieldtype": "Check", "label": "Featured", "default": "0"},
  {"fieldname": "category", "fieldtype": "Link", "label": "Category", "options": "Item Group"},
  {"fieldname": "route", "fieldtype": "Data", "label": "Route", "read_only": 1, "no_copy": 1},
  {"fieldname": "image", "fieldtype": "Attach Image", "label": "Image"},
  {"fieldname": "short_description", "fieldtype": "Small Text", "label": "Short Description"},
  {"fieldname": "long_description", "fieldtype": "Text Editor", "label": "Long Description"}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
  {"role": "Sales Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py`:

```python
import frappe
from frappe.website.website_generator import WebsiteGenerator


class WebstoreProduct(WebsiteGenerator):
	website = frappe._dict(
		page_title_field="web_title",
		condition_field="published",
		template="templates/generators/webstore_product.html",
	)

	def make_route(self):
		return "store/" + self.scrub(self.web_title)

	def validate(self):
		if not self.image:
			self.image = frappe.db.get_value("Item", self.item, "image")

	def get_context(self, context):
		context.no_cache = 1
		context.item_doc = frappe.get_doc("Item", self.item)
		return context
```

`upande_webstore/templates/generators/webstore_product.html` (placeholder, replaced in Task 12):

```html
{% extends "templates/web.html" %}
{% block page_content %}
<h1>{{ web_title }} price</h1>
{% endblock %}
```

Migrate:

```bash
cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_product
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add Webstore Product website-generator doctype

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 4: Pricing service

**Files:**
- Create: `upande_webstore/services/pricing.py`
- Test: `upande_webstore/tests/test_pricing.py`

**Interfaces:**
- Consumes: `get_settings()` (Task 2), test utils (Tasks 2–3).
- Produces:
  - `upande_webstore.services.pricing.get_customer(user=None) -> str | None` — Customer name linked to the session (or given) user via Contact → Dynamic Link, else None.
  - `upande_webstore.services.pricing.get_price_list(user=None) -> str` — the Customer's `default_price_list` if set, else settings guest price list.
  - `upande_webstore.services.pricing.get_item_price(item_code, qty=1, user=None) -> dict` — `{"rate": float, "currency": str, "price_list": str, "is_customer_price": bool}` using ERPNext's `get_item_details` pipeline (pricing rules included). Rate 0.0 when no Item Price exists.
  - Test utils gain `make_portal_user(email, customer_name=None, price_list=None)` — creates User (role `Customer`), Customer, Contact linked to both; returns `(user, customer)` names. Used by all later tests.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/utils.py`:

```python
def make_portal_user(email, customer_name=None, price_list=None):
	customer_name = customer_name or email.split("@")[0].replace(".", " ").title()
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": customer_name,
			"send_welcome_email": 0,
			"user_type": "Website User",
		})
		user.flags.ignore_permissions = True
		user.insert()
		user.add_roles("Customer")
	if not frappe.db.exists("Customer", customer_name):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": "Individual",
			"customer_group": "Individual",
			"territory": "All Territories",
			"default_price_list": price_list,
		})
		customer.insert(ignore_permissions=True)
	elif price_list:
		frappe.db.set_value("Customer", customer_name, "default_price_list", price_list)
	contact_name = frappe.db.get_value("Contact", {"user": email})
	if not contact_name:
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": customer_name,
			"user": email,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer_name}],
		})
		contact.insert(ignore_permissions=True)
	return email, customer_name


def make_item_price(item_code, price_list, rate):
	existing = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if existing:
		frappe.db.set_value("Item Price", existing, "price_list_rate", rate)
		return
	frappe.get_doc({
		"doctype": "Item Price",
		"item_code": item_code,
		"price_list": price_list,
		"price_list_rate": rate,
	}).insert(ignore_permissions=True)


def make_price_list(name):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc({
			"doctype": "Price List",
			"price_list_name": name,
			"selling": 1,
			"currency": frappe.get_cached_value("Company", frappe.defaults.get_global_default("company"), "default_currency"),
		}).insert(ignore_permissions=True)
	return name
```

`upande_webstore/tests/test_pricing.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_price_list,
	make_test_product,
	setup_webstore_settings,
)


class TestPricing(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PRICE-ITEM")
		make_item_price("WS-PRICE-ITEM", "Standard Selling", 100)
		make_price_list("Webstore B2B")
		make_item_price("WS-PRICE-ITEM", "Webstore B2B", 80)
		make_portal_user("b2b.buyer@example.com", "B2B Buyer Ltd", price_list="Webstore B2B")
		make_portal_user("retail.buyer@example.com", "Retail Buyer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_gets_guest_price_list(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="Guest")
		self.assertEqual(price["rate"], 100)
		self.assertEqual(price["price_list"], "Standard Selling")
		self.assertFalse(price["is_customer_price"])

	def test_customer_price_list_wins(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="b2b.buyer@example.com")
		self.assertEqual(price["rate"], 80)
		self.assertEqual(price["price_list"], "Webstore B2B")
		self.assertTrue(price["is_customer_price"])

	def test_customer_without_price_list_falls_back_to_guest(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="retail.buyer@example.com")
		self.assertEqual(price["rate"], 100)
		self.assertFalse(price["is_customer_price"])

	def test_get_customer_resolution(self):
		from upande_webstore.services.pricing import get_customer

		self.assertEqual(get_customer("b2b.buyer@example.com"), "B2B Buyer Ltd")
		self.assertIsNone(get_customer("Guest"))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_pricing
```

Expected: ImportError — `upande_webstore.services.pricing` does not exist.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/pricing.py`:

```python
import frappe

from upande_webstore.services.settings import get_settings


def get_customer(user=None):
	"""Customer linked to the user via their Contact, or None."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact_name:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
		"link_name",
	)


def get_price_list(user=None):
	customer = get_customer(user)
	if customer:
		price_list = frappe.db.get_value("Customer", customer, "default_price_list")
		if price_list:
			return price_list
	return get_settings().guest_price_list


def get_item_price(item_code, qty=1, user=None):
	"""Server-resolved price. Never trust client prices."""
	from erpnext.stock.get_item_details import get_item_details

	settings = get_settings()
	customer = get_customer(user)
	price_list = get_price_list(user)
	is_customer_price = bool(
		customer and frappe.db.get_value("Customer", customer, "default_price_list") == price_list
	)
	currency = frappe.db.get_value("Price List", price_list, "currency")
	args = frappe._dict({
		"doctype": "Quotation",
		"item_code": item_code,
		"qty": qty or 1,
		"company": settings.company,
		"selling_price_list": price_list,
		"price_list": price_list,
		"customer": customer,
		"currency": currency,
		"price_list_currency": currency,
		"conversion_rate": 1,
		"plc_conversion_rate": 1,
		"ignore_pricing_rule": 0,
		"transaction_date": frappe.utils.nowdate(),
	})
	details = get_item_details(args)
	rate = details.get("rate") or details.get("price_list_rate") or 0.0
	return {
		"rate": float(rate),
		"currency": currency,
		"price_list": price_list,
		"is_customer_price": is_customer_price,
	}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_pricing
```

Expected: `OK` (4 tests). If `get_item_details` raises about a missing argument, add that key to `args` with a sane default rather than switching approach — it is the canonical ERPNext pricing entry point and applies Pricing Rules.

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add server-side pricing resolver

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 5: Stock availability service

**Files:**
- Create: `upande_webstore/services/stock.py`
- Test: `upande_webstore/tests/test_stock.py`

**Interfaces:**
- Consumes: `get_settings()`, `get_warehouses()` (Task 2), test utils.
- Produces:
  - `upande_webstore.services.stock.get_stock_qty(item_code) -> float` — sum of `Bin.actual_qty` across configured warehouses; for a variant-template Item, the max across its variants.
  - `upande_webstore.services.stock.get_stock_info(item_code) -> dict` — `{"in_stock": bool, "qty": float | None, "show_qty": bool}` respecting the settings display mode. Non-stock items (`is_stock_item=0`) always report `in_stock: True, qty: None`.
  - Test utils gain `set_stock(item_code, qty, warehouse=None)` (Stock Reconciliation-free: uses a submitted Stock Entry of type Material Receipt, or drains with Material Issue).

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/utils.py`:

```python
def set_stock(item_code, qty, warehouse=None):
	"""Set absolute stock via Stock Reconciliation (idempotent)."""
	from erpnext.stock.utils import get_stock_balance

	warehouse = warehouse or get_default_warehouse()
	current = get_stock_balance(item_code, warehouse)
	if current == qty:
		return
	recon = frappe.get_doc({
		"doctype": "Stock Reconciliation",
		"company": frappe.defaults.get_global_default("company"),
		"purpose": "Stock Reconciliation",
		"items": [{
			"item_code": item_code,
			"warehouse": warehouse,
			"qty": qty,
			"valuation_rate": 10,
		}],
	})
	recon.flags.ignore_permissions = True
	recon.insert()
	recon.submit()
```

`upande_webstore/tests/test_stock.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestStock(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-STOCK-ITEM")
		make_test_product("WS-NOSTOCK-ITEM")
		make_test_product("WS-SERVICE-ITEM", is_stock_item=0)

	def test_in_stock(self):
		from upande_webstore.services.stock import get_stock_info, get_stock_qty

		set_stock("WS-STOCK-ITEM", 5)
		self.assertEqual(get_stock_qty("WS-STOCK-ITEM"), 5)
		info = get_stock_info("WS-STOCK-ITEM")
		self.assertTrue(info["in_stock"])
		self.assertFalse(info["show_qty"])  # settings default is badge mode

	def test_out_of_stock(self):
		from upande_webstore.services.stock import get_stock_info

		set_stock("WS-NOSTOCK-ITEM", 0)
		self.assertFalse(get_stock_info("WS-NOSTOCK-ITEM")["in_stock"])

	def test_non_stock_item_always_available(self):
		from upande_webstore.services.stock import get_stock_info

		info = get_stock_info("WS-SERVICE-ITEM")
		self.assertTrue(info["in_stock"])
		self.assertIsNone(info["qty"])

	def test_exact_qty_mode(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.services.stock import get_stock_info

		settings = frappe.get_doc("Webstore Settings")
		settings.stock_display = "Exact Quantity"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			set_stock("WS-STOCK-ITEM", 5)
			info = get_stock_info("WS-STOCK-ITEM")
			self.assertTrue(info["show_qty"])
			self.assertEqual(info["qty"], 5)
		finally:
			settings.stock_display = "In/Out Badge"
			settings.save(ignore_permissions=True)
			frappe.clear_cache()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_stock
```

Expected: ImportError — `upande_webstore.services.stock` does not exist.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/stock.py`:

```python
import frappe

from upande_webstore.services.settings import get_settings, get_warehouses


def get_stock_qty(item_code):
	item = frappe.get_cached_doc("Item", item_code)
	if item.has_variants:
		variants = frappe.get_all("Item", filters={"variant_of": item_code}, pluck="name")
		return max((_bin_qty(v) for v in variants), default=0.0)
	return _bin_qty(item_code)


def _bin_qty(item_code):
	warehouses = get_warehouses()
	if not warehouses:
		return 0.0
	qty = frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": ["in", warehouses]},
		"sum(actual_qty)",
	)
	return float(qty or 0.0)


def get_stock_info(item_code):
	item = frappe.get_cached_doc("Item", item_code)
	settings = get_settings()
	show_qty = settings.stock_display == "Exact Quantity"
	if not item.is_stock_item:
		return {"in_stock": True, "qty": None, "show_qty": False}
	qty = get_stock_qty(item_code)
	return {
		"in_stock": qty > 0,
		"qty": qty if show_qty else None,
		"show_qty": show_qty,
	}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_stock
```

Expected: `OK` (4 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add stock availability service

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 6: Webstore Cart DocType + cart API

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_cart/__init__.py`, `webstore_cart.json`, `webstore_cart.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_cart_item/__init__.py`, `webstore_cart_item.json`, `webstore_cart_item.py`
- Create: `upande_webstore/api/cart.py`
- Test: `upande_webstore/tests/test_cart.py`

**Interfaces:**
- Consumes: pricing service (Task 4), stock service (Task 5), test utils.
- Produces:
  - DocType `Webstore Cart`: `user` (Link User, reqd), `status` (Select: Open/Ordered/Abandoned, default Open), `quotation` (Link Quotation), `items` (Table `Webstore Cart Item`), `total` (Currency, read-only). Child fields: `item_code` (Link Item), `item_name` (Data), `qty` (Float), `rate` (Currency), `amount` (Currency).
  - Whitelisted (login required): `upande_webstore.api.cart.get_cart()`, `add_item(item_code, qty=1)`, `update_qty(item_code, qty)`, `remove_item(item_code)`, `get_cart_count()`. All return the serialized cart: `{"name", "items": [{item_code, item_name, web_title, route, qty, rate, amount}], "total", "currency", "count"}` (`get_cart_count` returns just an int).
  - Module-internal helper `_get_open_cart(create=False)` and `_reprice(cart)` reused by checkout (Task 9 imports `upande_webstore.api.cart._get_open_cart` and `serialize_cart`).
  - Stock rule: `add_item`/`update_qty` throw `frappe.ValidationError` if requested qty exceeds `get_stock_qty` for stock items; guests get `frappe.PermissionError`.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_cart.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCart(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CART-ITEM")
		make_item_price("WS-CART-ITEM", "Standard Selling", 50)
		make_test_product("WS-CART-OOS")
		make_item_price("WS-CART-OOS", "Standard Selling", 20)
		make_portal_user("cart.user@example.com")
		set_stock("WS-CART-ITEM", 10)
		set_stock("WS-CART-OOS", 0)

	def setUp(self):
		frappe.set_user("cart.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "cart.user@example.com"})

	def test_add_and_reprice(self):
		from upande_webstore.api import cart

		result = cart.add_item("WS-CART-ITEM", 2)
		self.assertEqual(result["count"], 2)
		self.assertEqual(result["items"][0]["rate"], 50)
		self.assertEqual(result["total"], 100)

	def test_single_open_cart(self):
		from upande_webstore.api import cart

		cart.add_item("WS-CART-ITEM", 1)
		cart.add_item("WS-CART-ITEM", 1)
		open_carts = frappe.get_all(
			"Webstore Cart", {"user": "cart.user@example.com", "status": "Open"}
		)
		self.assertEqual(len(open_carts), 1)
		self.assertEqual(cart.get_cart()["items"][0]["qty"], 2)

	def test_out_of_stock_rejected(self):
		from upande_webstore.api import cart

		self.assertRaises(frappe.ValidationError, cart.add_item, "WS-CART-OOS", 1)

	def test_qty_above_stock_rejected(self):
		from upande_webstore.api import cart

		self.assertRaises(frappe.ValidationError, cart.add_item, "WS-CART-ITEM", 11)

	def test_update_and_remove(self):
		from upande_webstore.api import cart

		cart.add_item("WS-CART-ITEM", 2)
		result = cart.update_qty("WS-CART-ITEM", 5)
		self.assertEqual(result["items"][0]["qty"], 5)
		result = cart.remove_item("WS-CART-ITEM")
		self.assertEqual(result["count"], 0)

	def test_guest_rejected(self):
		from upande_webstore.api import cart

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, cart.add_item, "WS-CART-ITEM", 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_cart
```

Expected: ImportError / DocType missing.

- [ ] **Step 3: Create DocTypes and API**

`upande_webstore/upande_webstore/doctype/webstore_cart_item/webstore_cart_item.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Cart Item",
 "module": "Upande Webstore",
 "istable": 1,
 "engine": "InnoDB",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["item_code", "item_name", "qty", "rate", "amount"],
 "fields": [
  {"fieldname": "item_code", "fieldtype": "Link", "label": "Item", "options": "Item", "reqd": 1, "in_list_view": 1},
  {"fieldname": "item_name", "fieldtype": "Data", "label": "Item Name", "in_list_view": 1},
  {"fieldname": "qty", "fieldtype": "Float", "label": "Qty", "reqd": 1, "in_list_view": 1},
  {"fieldname": "rate", "fieldtype": "Currency", "label": "Rate", "read_only": 1, "in_list_view": 1},
  {"fieldname": "amount", "fieldtype": "Currency", "label": "Amount", "read_only": 1, "in_list_view": 1}
 ],
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`webstore_cart_item.py`: `class WebstoreCartItem(Document): pass` (with import).

`upande_webstore/upande_webstore/doctype/webstore_cart/webstore_cart.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Cart",
 "module": "Upande Webstore",
 "engine": "InnoDB",
 "autoname": "format:CART-{#####}",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["user", "status", "quotation", "items", "total"],
 "fields": [
  {"fieldname": "user", "fieldtype": "Link", "label": "User", "options": "User", "reqd": 1, "in_list_view": 1},
  {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\nOrdered\nAbandoned", "default": "Open", "in_list_view": 1},
  {"fieldname": "quotation", "fieldtype": "Link", "label": "Quotation", "options": "Quotation", "read_only": 1},
  {"fieldname": "items", "fieldtype": "Table", "label": "Items", "options": "Webstore Cart Item"},
  {"fieldname": "total", "fieldtype": "Currency", "label": "Total", "read_only": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`webstore_cart.py`:

```python
from frappe.model.document import Document


class WebstoreCart(Document):
	def validate(self):
		self.total = sum(row.amount or 0 for row in self.items)
```

`upande_webstore/api/cart.py`:

```python
import frappe
from frappe import _

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_qty


def _require_login():
	if frappe.session.user in (None, "", "Guest"):
		frappe.throw(_("Please log in to use the cart."), frappe.PermissionError)


def _get_open_cart(create=False):
	name = frappe.db.get_value(
		"Webstore Cart", {"user": frappe.session.user, "status": "Open"}
	)
	if name:
		return frappe.get_doc("Webstore Cart", name)
	if not create:
		return None
	cart = frappe.get_doc({"doctype": "Webstore Cart", "user": frappe.session.user, "status": "Open"})
	cart.insert(ignore_permissions=True)
	return cart


def _validate_stock(item_code, qty):
	item = frappe.get_cached_doc("Item", item_code)
	if not item.is_stock_item:
		return
	available = get_stock_qty(item_code)
	if qty > available:
		frappe.throw(
			_("{0} is not available in the requested quantity.").format(item.item_name),
			frappe.ValidationError,
		)


def _reprice(cart):
	"""Re-resolve every rate server-side; never trust stored/client prices."""
	for row in cart.items:
		price = get_item_price(row.item_code, qty=row.qty)
		row.rate = price["rate"]
		row.amount = row.rate * row.qty
		row.item_name = frappe.get_cached_value("Item", row.item_code, "item_name")


def serialize_cart(cart):
	if not cart:
		return {"name": None, "items": [], "total": 0, "currency": None, "count": 0}
	from upande_webstore.services.pricing import get_price_list

	product_map = {}
	item_codes = [row.item_code for row in cart.items]
	if item_codes:
		for p in frappe.get_all(
			"Webstore Product",
			filters={"item": ["in", item_codes]},
			fields=["item", "web_title", "route"],
		):
			product_map[p.item] = p
	return {
		"name": cart.name,
		"items": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"web_title": product_map.get(row.item_code, {}).get("web_title") or row.item_name,
				"route": product_map.get(row.item_code, {}).get("route"),
				"qty": row.qty,
				"rate": row.rate,
				"amount": row.amount,
			}
			for row in cart.items
		],
		"total": cart.total,
		"currency": frappe.db.get_value("Price List", get_price_list(), "currency"),
		"count": int(sum(row.qty for row in cart.items)),
	}


@frappe.whitelist()
def get_cart():
	_require_login()
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def get_cart_count():
	_require_login()
	cart = _get_open_cart()
	return int(sum(row.qty for row in cart.items)) if cart else 0


@frappe.whitelist()
def add_item(item_code, qty=1):
	_require_login()
	qty = frappe.utils.flt(qty) or 1
	if qty <= 0:
		frappe.throw(_("Quantity must be positive."), frappe.ValidationError)
	if not frappe.db.get_value("Webstore Product", {"item": item_code, "published": 1}):
		frappe.throw(_("This product is not available."), frappe.ValidationError)
	cart = _get_open_cart(create=True)
	existing = next((row for row in cart.items if row.item_code == item_code), None)
	new_qty = (existing.qty if existing else 0) + qty
	_validate_stock(item_code, new_qty)
	if existing:
		existing.qty = new_qty
	else:
		cart.append("items", {"item_code": item_code, "qty": qty})
	_reprice(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def update_qty(item_code, qty):
	_require_login()
	qty = frappe.utils.flt(qty)
	if qty <= 0:
		return remove_item(item_code)
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = next((r for r in cart.items if r.item_code == item_code), None)
	if not row:
		frappe.throw(_("Item not in cart."), frappe.ValidationError)
	_validate_stock(item_code, qty)
	row.qty = qty
	_reprice(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def remove_item(item_code):
	_require_login()
	cart = _get_open_cart()
	if not cart:
		return serialize_cart(None)
	cart.items = [r for r in cart.items if r.item_code != item_code]
	_reprice(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)
```

Migrate: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate`

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_cart
```

Expected: `OK` (6 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add Webstore Cart doctype and cart API

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 7: Signup API (auto-create User + Contact + Customer)

**Files:**
- Create: `upande_webstore/api/account.py`
- Test: `upande_webstore/tests/test_signup.py`

**Interfaces:**
- Consumes: `get_settings()` (Task 2).
- Produces: `upande_webstore.api.account.sign_up(email, full_name, phone, company_name=None)` — whitelisted, `allow_guest=True`. Creates: User (Website User, role `Customer`, welcome email), Customer (`customer_type` = Company if `company_name` given else Individual, name = company_name or full_name, group/territory from settings), Contact linking both. Returns `{"message": str}`. Throws `frappe.ValidationError` on existing email or invalid input. Task 20's account page and the login page link to `/signup` which calls this.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_signup.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestSignup(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _cleanup(self, email, customer_name):
		contact = frappe.db.get_value("Contact", {"user": email})
		if contact:
			frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
		if frappe.db.exists("Customer", customer_name):
			frappe.delete_doc("Customer", customer_name, force=True, ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_individual_signup_creates_linked_records(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("jane.doe@example.com", "Jane Doe")
		frappe.set_user("Guest")
		sign_up("jane.doe@example.com", "Jane Doe", "+254700000001")
		frappe.set_user("Administrator")

		user = frappe.get_doc("User", "jane.doe@example.com")
		self.assertEqual(user.user_type, "Website User")
		self.assertIn("Customer", [r.role for r in user.roles])

		customer = frappe.get_doc("Customer", "Jane Doe")
		self.assertEqual(customer.customer_type, "Individual")
		self.assertEqual(customer.customer_group, "Individual")

		contact_name = frappe.db.get_value("Contact", {"user": "jane.doe@example.com"})
		self.assertTrue(contact_name)
		link = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
			"link_name",
		)
		self.assertEqual(link, "Jane Doe")

	def test_company_signup(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("buyer@acme.example", "Acme Ltd")
		frappe.set_user("Guest")
		sign_up("buyer@acme.example", "Bob Buyer", "+254700000002", company_name="Acme Ltd")
		frappe.set_user("Administrator")
		customer = frappe.get_doc("Customer", "Acme Ltd")
		self.assertEqual(customer.customer_type, "Company")

	def test_duplicate_email_rejected(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("dup@example.com", "Dup User")
		frappe.set_user("Guest")
		sign_up("dup@example.com", "Dup User", "+254700000003")
		self.assertRaises(frappe.ValidationError, sign_up, "dup@example.com", "Dup User", "+254700000003")
		frappe.set_user("Administrator")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_signup
```

Expected: ImportError — `upande_webstore.api.account` does not exist.

- [ ] **Step 3: Write the implementation**

`upande_webstore/api/account.py`:

```python
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from upande_webstore.services.settings import get_settings


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def sign_up(email, full_name, phone, company_name=None):
	email = (email or "").strip().lower()
	full_name = (full_name or "").strip()
	company_name = (company_name or "").strip() or None
	validate_email_address(email, throw=True)
	if not full_name:
		frappe.throw(_("Full name is required."), frappe.ValidationError)
	if frappe.db.exists("User", email):
		frappe.throw(_("An account with this email already exists. Please log in."), frappe.ValidationError)

	customer_name = company_name or full_name
	if frappe.db.exists("Customer", customer_name):
		frappe.throw(
			_("A customer named {0} already exists. Contact us to get portal access.").format(customer_name),
			frappe.ValidationError,
		)

	settings = get_settings()
	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": full_name,
		"mobile_no": phone,
		"user_type": "Website User",
		"send_welcome_email": 1,
	})
	user.flags.ignore_permissions = True
	user.insert()
	user.add_roles("Customer")

	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": customer_name,
		"customer_type": "Company" if company_name else "Individual",
		"customer_group": settings.default_customer_group,
		"territory": settings.default_territory,
	})
	customer.flags.ignore_permissions = True
	customer.insert()

	contact = frappe.get_doc({
		"doctype": "Contact",
		"first_name": full_name,
		"user": email,
		"email_ids": [{"email_id": email, "is_primary": 1}],
		"phone_nos": [{"phone": phone, "is_primary_mobile_no": 1}] if phone else [],
		"links": [{"link_doctype": "Customer", "link_name": customer.name}],
	})
	contact.flags.ignore_permissions = True
	contact.insert()

	return {"message": _("Account created. Check your email to set your password.")}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_signup
```

Expected: `OK` (3 tests). If the `rate_limit` decorator errors when tests call the function directly (no HTTP request context), split the function: keep the decorated whitelisted `sign_up` as a thin wrapper that calls an undecorated `_sign_up` containing all the logic, and point the tests at `_sign_up`.

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add signup API creating User, Customer and Contact

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 8: Variant resolution API

**Files:**
- Create: `upande_webstore/api/variants.py`
- Test: `upande_webstore/tests/test_variants.py`

**Interfaces:**
- Consumes: pricing (Task 4), stock (Task 5) services.
- Produces (both whitelisted, `allow_guest=True` — read-only):
  - `upande_webstore.api.variants.get_attributes(template_item) -> list[{"attribute", "values": [str]}]` from the template's Item Variant Attributes.
  - `upande_webstore.api.variants.resolve_variant(template_item, attributes) -> dict` — `attributes` is a JSON string/dict of `{attribute: value}`; returns `{"item_code", "price": <get_item_price dict>, "stock": <get_stock_info dict>}` or `{"item_code": None}` when no variant matches. Uses `erpnext.controllers.item_variant.find_variant`.
  - Test utils gain `make_variant_template(template_code)` creating a template with attribute `WS Size` (values S/M/L) and two variants.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/utils.py`:

```python
def make_variant_template(template_code):
	if not frappe.db.exists("Item Attribute", "WS Size"):
		frappe.get_doc({
			"doctype": "Item Attribute",
			"attribute_name": "WS Size",
			"item_attribute_values": [
				{"attribute_value": "S", "abbr": "S"},
				{"attribute_value": "M", "abbr": "M"},
				{"attribute_value": "L", "abbr": "L"},
			],
		}).insert(ignore_permissions=True)
	template = make_test_item(
		template_code, has_variants=1, attributes=[{"attribute": "WS Size"}]
	)
	from erpnext.controllers.item_variant import create_variant

	for size in ("S", "M"):
		variant_code = f"{template_code}-{size}"
		if not frappe.db.exists("Item", variant_code):
			variant = create_variant(template_code, {"WS Size": size})
			variant.item_code = variant_code
			variant.insert(ignore_permissions=True)
	return template
```

`upande_webstore/tests/test_variants.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	set_stock,
	setup_webstore_settings,
)


class TestVariants(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_variant_template("WS-VAR-SHIRT")
		make_test_product("WS-VAR-SHIRT", web_title="Variant Shirt")
		make_item_price("WS-VAR-SHIRT-S", "Standard Selling", 30)
		set_stock("WS-VAR-SHIRT-S", 4)

	def test_get_attributes(self):
		from upande_webstore.api.variants import get_attributes

		attrs = get_attributes("WS-VAR-SHIRT")
		self.assertEqual(attrs[0]["attribute"], "WS Size")
		self.assertIn("S", attrs[0]["values"])

	def test_resolve_variant(self):
		from upande_webstore.api.variants import resolve_variant

		result = resolve_variant("WS-VAR-SHIRT", {"WS Size": "S"})
		self.assertEqual(result["item_code"], "WS-VAR-SHIRT-S")
		self.assertEqual(result["price"]["rate"], 30)
		self.assertTrue(result["stock"]["in_stock"])

	def test_resolve_missing_combination(self):
		from upande_webstore.api.variants import resolve_variant

		result = resolve_variant("WS-VAR-SHIRT", {"WS Size": "L"})
		self.assertIsNone(result["item_code"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_variants
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/api/variants.py`:

```python
import json

import frappe

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


@frappe.whitelist(allow_guest=True)
def get_attributes(template_item):
	template = frappe.get_cached_doc("Item", template_item)
	if not template.has_variants:
		return []
	result = []
	for row in template.attributes:
		values = frappe.get_all(
			"Item Attribute Value",
			filters={"parent": row.attribute},
			pluck="attribute_value",
			order_by="idx",
		)
		result.append({"attribute": row.attribute, "values": values})
	return result


@frappe.whitelist(allow_guest=True)
def resolve_variant(template_item, attributes):
	from erpnext.controllers.item_variant import find_variant

	if isinstance(attributes, str):
		attributes = json.loads(attributes)
	variant = find_variant(template_item, attributes)
	if not variant:
		return {"item_code": None}
	return {
		"item_code": variant,
		"price": get_item_price(variant),
		"stock": get_stock_info(variant),
	}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_variants
```

Expected: `OK` (3 tests). If `find_variant`'s signature differs in v16 (`find_variant(template, args, variant_item_code=None)`), match it — check `apps/erpnext/erpnext/controllers/item_variant.py`.

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add variant attribute listing and resolution API

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 9: Checkout API (cart → submitted Quotation)

**Files:**
- Create: `upande_webstore/api/checkout.py`
- Create: `upande_webstore/setup/__init__.py`, `upande_webstore/setup/install.py`
- Modify: `upande_webstore/hooks.py` (add `after_install`/`after_migrate` hook)
- Test: `upande_webstore/tests/test_checkout.py`

**Interfaces:**
- Consumes: `_get_open_cart`, `serialize_cart` (Task 6), pricing/stock services, `get_settings()`.
- Produces:
  - Custom fields on Quotation (created idempotently by `upande_webstore.setup.install.create_webstore_custom_fields`, wired to `after_install` + `after_migrate` hooks): `webstore_notes` (Small Text), `customer_po_reference` (Data), `webstore_portal_status` (Select: ``/Accepted/Declined, hidden in desk form is fine).
  - `upande_webstore.api.checkout.place_order(address_name=None, po_reference=None, notes=None) -> {"quotation": name}` — whitelisted, login required. Validates: open non-empty cart, user has a Customer, per-line stock (throws listing ALL failing lines), re-prices; creates a **submitted** Quotation (`quotation_to=Customer`, `party_name`, `contact_person`, `selling_price_list`, `valid_till` = today + settings days, `order_type="Shopping Cart"`, shipping/customer address if given); marks cart `Ordered` + links quotation; emails settings `notification_emails`.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_checkout.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCheckout(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CHK-ITEM")
		make_item_price("WS-CHK-ITEM", "Standard Selling", 75)
		make_portal_user("checkout.user@example.com", "Checkout Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "checkout.user@example.com"})
		set_stock("WS-CHK-ITEM", 10)
		frappe.set_user("checkout.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_place_order_creates_submitted_quotation(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		result = checkout.place_order(po_reference="PO-123", notes="Deliver Tuesday")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.docstatus, 1)
		self.assertEqual(quotation.party_name, "Checkout Buyer")
		self.assertEqual(quotation.items[0].item_code, "WS-CHK-ITEM")
		self.assertEqual(quotation.items[0].qty, 3)
		self.assertEqual(quotation.items[0].rate, 75)
		self.assertEqual(str(quotation.valid_till), add_days(nowdate(), 14))
		self.assertEqual(quotation.customer_po_reference, "PO-123")
		self.assertEqual(quotation.webstore_notes, "Deliver Tuesday")
		cart_doc = frappe.get_all(
			"Webstore Cart",
			{"user": "checkout.user@example.com"},
			["status", "quotation"],
		)[0]
		self.assertEqual(cart_doc.status, "Ordered")
		self.assertEqual(cart_doc.quotation, quotation.name)

	def test_empty_cart_rejected(self):
		from upande_webstore.api import checkout

		self.assertRaises(frappe.ValidationError, checkout.place_order)

	def test_stock_revalidated_at_checkout(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		frappe.set_user("Administrator")
		set_stock("WS-CHK-ITEM", 1)
		frappe.set_user("checkout.user@example.com")
		with self.assertRaises(frappe.ValidationError) as ctx:
			checkout.place_order()
		self.assertIn("no longer available", str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_checkout
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/setup/install.py`:

```python
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

WEBSTORE_CUSTOM_FIELDS = {
	"Quotation": [
		{
			"fieldname": "webstore_section",
			"fieldtype": "Section Break",
			"label": "Webstore",
			"insert_after": "order_type",
			"collapsible": 1,
		},
		{
			"fieldname": "customer_po_reference",
			"fieldtype": "Data",
			"label": "Customer PO Reference",
			"insert_after": "webstore_section",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_notes",
			"fieldtype": "Small Text",
			"label": "Webstore Notes",
			"insert_after": "customer_po_reference",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_portal_status",
			"fieldtype": "Select",
			"label": "Portal Status",
			"options": "\nAccepted\nDeclined",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
	]
}


def create_webstore_custom_fields():
	create_custom_fields(WEBSTORE_CUSTOM_FIELDS, ignore_validate=True)


def after_install():
	create_webstore_custom_fields()


def after_migrate():
	create_webstore_custom_fields()
```

In `upande_webstore/hooks.py` add:

```python
after_install = "upande_webstore.setup.install.after_install"
after_migrate = "upande_webstore.setup.install.after_migrate"
```

`upande_webstore/api/checkout.py`:

```python
import frappe
from frappe import _
from frappe.utils import add_days, flt, get_url_to_form, nowdate

from upande_webstore.api.cart import _get_open_cart, _require_login
from upande_webstore.services.pricing import get_customer, get_item_price, get_price_list
from upande_webstore.services.settings import get_settings
from upande_webstore.services.stock import get_stock_qty


@frappe.whitelist(methods=["POST"])
def place_order(address_name=None, po_reference=None, notes=None):
	_require_login()
	customer = get_customer()
	if not customer:
		frappe.throw(_("Your account is not linked to a customer. Please contact us."), frappe.ValidationError)
	cart = _get_open_cart()
	if not cart or not cart.items:
		frappe.throw(_("Your cart is empty."), frappe.ValidationError)

	unavailable = []
	for row in cart.items:
		item = frappe.get_cached_doc("Item", row.item_code)
		if item.is_stock_item and flt(row.qty) > get_stock_qty(row.item_code):
			unavailable.append(item.item_name)
	if unavailable:
		frappe.throw(
			_("These items are no longer available in the requested quantity: {0}. Please adjust your cart.").format(", ".join(unavailable)),
			frappe.ValidationError,
		)

	settings = get_settings()
	price_list = get_price_list()
	contact_name = frappe.db.get_value("Contact", {"user": frappe.session.user}, "name")

	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": customer,
		"order_type": "Shopping Cart",
		"company": settings.company,
		"selling_price_list": price_list,
		"valid_till": add_days(nowdate(), settings.quotation_validity_days or 14),
		"contact_person": contact_name,
		"customer_address": address_name,
		"shipping_address_name": address_name,
		"customer_po_reference": po_reference,
		"webstore_notes": notes,
		"items": [
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"rate": get_item_price(row.item_code, qty=row.qty)["rate"],
			}
			for row in cart.items
		],
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()

	cart.status = "Ordered"
	cart.quotation = quotation.name
	cart.save(ignore_permissions=True)

	_notify_sales_team(quotation)
	return {"quotation": quotation.name}


def _notify_sales_team(quotation):
	settings = get_settings()
	recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
	if not recipients:
		return
	frappe.sendmail(
		recipients=recipients,
		subject=_("New webstore quotation {0} from {1}").format(quotation.name, quotation.party_name),
		message=_("A new quotation request was placed on the webstore.<br>Review it here: {0}").format(
			get_url_to_form("Quotation", quotation.name)
		),
	)
```

Migrate (creates custom fields via after_migrate):

```bash
cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_checkout
```

Expected: `OK` (3 tests). Note: Quotation pricing runs server-side with `selling_price_list`, and we set `rate` explicitly from the resolver — if ERPNext's validate resets rates, set `quotation.flags.ignore_pricing_rule = False` and assert against `price_list_rate` instead; the invariant is that the rate comes from the server resolver, never the client.

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add checkout API creating submitted quotations

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 10: Wishlist DocType + API + page

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_wishlist/__init__.py`, `webstore_wishlist.json`, `webstore_wishlist.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_wishlist_item/__init__.py`, `webstore_wishlist_item.json`, `webstore_wishlist_item.py`
- Create: `upande_webstore/api/wishlist.py`
- Create: `upande_webstore/www/wishlist.py`, `upande_webstore/www/wishlist.html`
- Test: `upande_webstore/tests/test_wishlist.py`

**Interfaces:**
- Consumes: pricing/stock services, cart API patterns (Task 6).
- Produces:
  - DocType `Webstore Wishlist`: `user` (Link User, unique), `items` (Table `Webstore Wishlist Item` with `product` Link Webstore Product + `added_on` Date).
  - Whitelisted (login required): `upande_webstore.api.wishlist.toggle(product) -> {"wishlisted": bool, "count": int}`, `get_wishlist() -> {"items": [{product, web_title, route, image, item_code, price, stock}], "count"}`, `get_wishlisted_products() -> list[str]` (product names, for heart states).
  - Page `/wishlist` rendering the saved products with add-to-cart buttons (uses `webstore.js` from Task 13; the template just renders server-side data and hooks up `data-` attributes).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_wishlist.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestWishlist(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		cls.product = make_test_product("WS-WISH-ITEM", web_title="Wishable Widget")
		make_portal_user("wish.user@example.com")

	def setUp(self):
		frappe.set_user("wish.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Wishlist", {"user": "wish.user@example.com"})

	def test_toggle_on_off(self):
		from upande_webstore.api import wishlist

		result = wishlist.toggle(self.product.name)
		self.assertTrue(result["wishlisted"])
		self.assertEqual(result["count"], 1)
		result = wishlist.toggle(self.product.name)
		self.assertFalse(result["wishlisted"])
		self.assertEqual(result["count"], 0)

	def test_get_wishlist(self):
		from upande_webstore.api import wishlist

		wishlist.toggle(self.product.name)
		data = wishlist.get_wishlist()
		self.assertEqual(data["items"][0]["web_title"], "Wishable Widget")
		self.assertIn("price", data["items"][0])

	def test_guest_rejected(self):
		from upande_webstore.api import wishlist

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, wishlist.toggle, self.product.name)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_wishlist
```

Expected: ImportError / DocType missing.

- [ ] **Step 3: Create DocTypes, API, and page**

`webstore_wishlist_item.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Wishlist Item",
 "module": "Upande Webstore",
 "istable": 1,
 "engine": "InnoDB",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["product", "added_on"],
 "fields": [
  {"fieldname": "product", "fieldtype": "Link", "label": "Product", "options": "Webstore Product", "reqd": 1, "in_list_view": 1},
  {"fieldname": "added_on", "fieldtype": "Date", "label": "Added On", "in_list_view": 1}
 ],
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`webstore_wishlist.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Wishlist",
 "module": "Upande Webstore",
 "engine": "InnoDB",
 "autoname": "format:WISH-{#####}",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-20 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["user", "items"],
 "fields": [
  {"fieldname": "user", "fieldtype": "Link", "label": "User", "options": "User", "reqd": 1, "unique": 1},
  {"fieldname": "items", "fieldtype": "Table", "label": "Items", "options": "Webstore Wishlist Item"}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

Both `.py` controllers: `class WebstoreWishlist(Document): pass` / `class WebstoreWishlistItem(Document): pass`.

`upande_webstore/api/wishlist.py`:

```python
import frappe
from frappe import _
from frappe.utils import nowdate

from upande_webstore.api.cart import _require_login
from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


def _get_wishlist(create=False):
	name = frappe.db.get_value("Webstore Wishlist", {"user": frappe.session.user})
	if name:
		return frappe.get_doc("Webstore Wishlist", name)
	if not create:
		return None
	doc = frappe.get_doc({"doctype": "Webstore Wishlist", "user": frappe.session.user})
	doc.insert(ignore_permissions=True)
	return doc


@frappe.whitelist()
def toggle(product):
	_require_login()
	if not frappe.db.exists("Webstore Product", product):
		frappe.throw(_("Product not found."), frappe.ValidationError)
	doc = _get_wishlist(create=True)
	existing = next((row for row in doc.items if row.product == product), None)
	if existing:
		doc.items = [row for row in doc.items if row.product != product]
		wishlisted = False
	else:
		doc.append("items", {"product": product, "added_on": nowdate()})
		wishlisted = True
	doc.save(ignore_permissions=True)
	return {"wishlisted": wishlisted, "count": len(doc.items)}


@frappe.whitelist()
def get_wishlisted_products():
	_require_login()
	doc = _get_wishlist()
	return [row.product for row in doc.items] if doc else []


@frappe.whitelist()
def get_wishlist():
	_require_login()
	doc = _get_wishlist()
	if not doc:
		return {"items": [], "count": 0}
	items = []
	for row in doc.items:
		product = frappe.db.get_value(
			"Webstore Product",
			row.product,
			["name", "web_title", "route", "image", "item", "published"],
			as_dict=True,
		)
		if not product or not product.published:
			continue
		item_doc = frappe.get_cached_doc("Item", product.item)
		items.append({
			"product": product.name,
			"web_title": product.web_title,
			"route": product.route,
			"image": product.image,
			"item_code": product.item,
			"has_variants": item_doc.has_variants,
			"price": None if item_doc.has_variants else get_item_price(product.item),
			"stock": None if item_doc.has_variants else get_stock_info(product.item),
		})
	return {"items": items, "count": len(items)}
```

`upande_webstore/www/wishlist.py`:

```python
import frappe


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/wishlist"
		raise frappe.Redirect
	from upande_webstore.api.wishlist import get_wishlist

	context.no_cache = 1
	context.wishlist = get_wishlist()
	return context
```

`upande_webstore/www/wishlist.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("My Wishlist") }}{% endblock %}
{% block page_content %}
<h1 class="mb-4">{{ _("My Wishlist") }}</h1>
{% if not wishlist["items"] %}
<p class="text-muted">{{ _("Nothing saved yet.") }} <a href="/store">{{ _("Browse the store") }}</a></p>
{% else %}
<div class="row" id="wishlist-grid">
	{% for entry in wishlist["items"] %}
	<div class="col-md-4 mb-4">
		<div class="card h-100">
			{% if entry.image %}<img src="{{ entry.image }}" class="card-img-top" alt="{{ entry.web_title }}">{% endif %}
			<div class="card-body">
				<h5 class="card-title"><a href="/{{ entry.route }}">{{ entry.web_title }}</a></h5>
				{% if entry.price %}
				<p class="mb-1 font-weight-bold">{{ frappe.utils.fmt_money(entry.price.rate, currency=entry.price.currency) }}</p>
				{% endif %}
				{% if entry.stock and not entry.stock.in_stock %}
				<span class="badge badge-secondary">{{ _("Out of stock") }}</span>
				{% endif %}
			</div>
			<div class="card-footer d-flex justify-content-between">
				{% if entry.has_variants %}
				<a class="btn btn-sm btn-primary" href="/{{ entry.route }}">{{ _("Choose options") }}</a>
				{% elif entry.stock and entry.stock.in_stock %}
				<button class="btn btn-sm btn-primary" data-webstore-add-to-cart="{{ entry.item_code }}">{{ _("Add to cart") }}</button>
				{% else %}
				<button class="btn btn-sm btn-primary" disabled>{{ _("Out of stock") }}</button>
				{% endif %}
				<button class="btn btn-sm btn-outline-danger" data-webstore-wishlist-toggle="{{ entry.product }}">{{ _("Remove") }}</button>
			</div>
		</div>
	</div>
	{% endfor %}
</div>
{% endif %}
{% endblock %}
```

Migrate: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate`

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_wishlist
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Verify page renders**

```bash
curl -s -o /dev/null -w "%{http_code}" -H "Host: webstore.localhost" "http://127.0.0.1:8000/wishlist"
```

Expected: `200` (renders login redirect target for guests — a 200 on the login page after redirect is fine).

- [ ] **Step 6: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add wishlist doctype, API and page

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 11: Catalog service + `/store` page

**Files:**
- Create: `upande_webstore/services/catalog.py`
- Create: `upande_webstore/www/store.py`, `upande_webstore/www/store.html`
- Test: `upande_webstore/tests/test_catalog.py`

**Interfaces:**
- Consumes: pricing/stock services, `Webstore Product`.
- Produces:
  - `upande_webstore.services.catalog.get_products(search=None, category=None, featured_only=False, start=0, page_length=12) -> {"products": [...], "total": int}` — published products only; each product dict: `{name, web_title, route, image, short_description, item, has_variants, price (dict|None for variants), stock (dict|None for variants)}`. Search matches `web_title`, `short_description`, `item` (item code) via `like`.
  - `upande_webstore.services.catalog.get_categories() -> [{"name": item_group, "count": int}]` for published products.
  - Page `/store` with search box (`?q=`), category filter (`?category=`), pagination (`?page=`), featured strip on unfiltered page 1.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_catalog.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	setup_webstore_settings,
)


class TestCatalog(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CAT-ALPHA", web_title="Alpha Sensor", featured=1)
		make_test_product("WS-CAT-BETA", web_title="Beta Gateway")
		make_test_product("WS-CAT-HIDDEN", web_title="Hidden Product", published=0)
		make_item_price("WS-CAT-ALPHA", "Standard Selling", 10)

	def test_only_published_products_listed(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_search(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(search="Alpha")
		self.assertEqual(len(result["products"]), 1)
		self.assertEqual(result["products"][0]["web_title"], "Alpha Sensor")
		self.assertEqual(result["products"][0]["price"]["rate"], 10)

	def test_featured_filter(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(featured_only=True, page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Beta Gateway", titles)

	def test_categories(self):
		from upande_webstore.services.catalog import get_categories

		categories = get_categories()
		self.assertTrue(any(c["name"] == "Products" and c["count"] >= 2 for c in categories))

	def test_store_page_renders(self):
		from frappe.utils import get_html_for_route

		html = get_html_for_route("store")
		self.assertIn("Alpha Sensor", html)
		self.assertNotIn("Hidden Product", html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_catalog
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/catalog.py`:

```python
import frappe

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


def get_products(search=None, category=None, featured_only=False, start=0, page_length=12):
	filters = {"published": 1}
	if category:
		filters["category"] = category
	if featured_only:
		filters["featured"] = 1
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [
			["web_title", "like", like],
			["short_description", "like", like],
			["item", "like", like],
		]
	fields = ["name", "web_title", "route", "image", "short_description", "item", "category"]
	products = frappe.get_all(
		"Webstore Product",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="featured desc, web_title asc",
		start=start,
		page_length=page_length,
	)
	total = frappe.db.count("Webstore Product", filters)  # close enough for pagination without search
	if search:
		total = len(
			frappe.get_all("Webstore Product", filters=filters, or_filters=or_filters, pluck="name")
		)
	for product in products:
		has_variants = frappe.get_cached_value("Item", product["item"], "has_variants")
		product["has_variants"] = has_variants
		product["price"] = None if has_variants else get_item_price(product["item"])
		product["stock"] = None if has_variants else get_stock_info(product["item"])
	return {"products": products, "total": total}


def get_categories():
	rows = frappe.get_all(
		"Webstore Product",
		filters={"published": 1},
		fields=["category", "count(name) as count"],
		group_by="category",
	)
	return [{"name": r.category, "count": r.count} for r in rows if r.category]
```

`upande_webstore/www/store.py`:

```python
import frappe

from upande_webstore.services.catalog import get_categories, get_products

PAGE_LENGTH = 12


def get_context(context):
	context.no_cache = 1
	search = frappe.form_dict.get("q") or None
	category = frappe.form_dict.get("category") or None
	page = max(frappe.utils.cint(frappe.form_dict.get("page")) or 1, 1)
	result = get_products(
		search=search, category=category, start=(page - 1) * PAGE_LENGTH, page_length=PAGE_LENGTH
	)
	context.products = result["products"]
	context.total = result["total"]
	context.page = page
	context.total_pages = max((result["total"] + PAGE_LENGTH - 1) // PAGE_LENGTH, 1)
	context.search = search or ""
	context.category = category or ""
	context.categories = get_categories()
	context.featured = (
		get_products(featured_only=True, page_length=4)["products"]
		if not search and not category and page == 1
		else []
	)
	return context
```

`upande_webstore/www/store.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Store") }}{% endblock %}

{% macro product_card(p) %}
<div class="col-md-4 mb-4">
	<div class="card h-100">
		{% if p.image %}<img src="{{ p.image }}" class="card-img-top" alt="{{ p.web_title }}" style="object-fit:cover;height:180px;">{% endif %}
		<div class="card-body">
			<h5 class="card-title"><a href="/{{ p.route }}">{{ p.web_title }}</a></h5>
			<p class="small text-muted">{{ p.short_description or "" }}</p>
			{% if p.has_variants %}
			<p class="mb-1">{{ _("Multiple options") }}</p>
			{% elif p.price %}
			<p class="mb-1 font-weight-bold">
				{{ frappe.utils.fmt_money(p.price.rate, currency=p.price.currency) }}
				{% if p.price.is_customer_price %}<span class="badge badge-info">{{ _("Your price") }}</span>{% endif %}
			</p>
			{% endif %}
			{% if p.stock %}
				{% if p.stock.in_stock %}
				<span class="badge badge-success">{{ _("In stock") }}{% if p.stock.show_qty %}: {{ p.stock.qty }}{% endif %}</span>
				{% else %}
				<span class="badge badge-secondary">{{ _("Out of stock") }}</span>
				{% endif %}
			{% endif %}
		</div>
	</div>
</div>
{% endmacro %}

{% block page_content %}
<div class="row">
	<div class="col-md-3">
		<form method="get" action="/store" class="mb-3">
			<input type="text" class="form-control" name="q" value="{{ search }}" placeholder="{{ _('Search products…') }}">
		</form>
		<h6>{{ _("Categories") }}</h6>
		<ul class="list-unstyled">
			<li><a href="/store" class="{{ 'font-weight-bold' if not category else '' }}">{{ _("All") }}</a></li>
			{% for c in categories %}
			<li><a href="/store?category={{ c.name | urlencode }}" class="{{ 'font-weight-bold' if category == c.name else '' }}">{{ c.name }} ({{ c.count }})</a></li>
			{% endfor %}
		</ul>
	</div>
	<div class="col-md-9">
		{% if featured %}
		<h4>{{ _("Featured") }}</h4>
		<div class="row">{% for p in featured %}{{ product_card(p) }}{% endfor %}</div>
		<hr>
		{% endif %}
		<h4>{{ _("All products") }}{% if search %} — {{ _("results for") }} “{{ search }}”{% endif %}</h4>
		{% if not products %}<p class="text-muted">{{ _("No products found.") }}</p>{% endif %}
		<div class="row">{% for p in products %}{{ product_card(p) }}{% endfor %}</div>
		{% if total_pages > 1 %}
		<nav><ul class="pagination">
			{% for n in range(1, total_pages + 1) %}
			<li class="page-item {{ 'active' if n == page else '' }}">
				<a class="page-link" href="/store?page={{ n }}{% if search %}&q={{ search | urlencode }}{% endif %}{% if category %}&category={{ category | urlencode }}{% endif %}">{{ n }}</a>
			</li>
			{% endfor %}
		</ul></nav>
		{% endif %}
	</div>
</div>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_catalog
```

Expected: `OK` (5 tests).

- [ ] **Step 5: Manual page check**

```bash
curl -s -H "Host: webstore.localhost" "http://127.0.0.1:8000/store" | grep -c "card-title"
```

Expected: a number ≥ 1 (product cards rendered).

- [ ] **Step 6: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add catalog service and /store page

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 12: Product detail template + storefront JS bundle

**Files:**
- Modify: `upande_webstore/templates/generators/webstore_product.html` (replace placeholder)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py` (extend `get_context`)
- Create: `upande_webstore/public/js/webstore.bundle.js`
- Modify: `upande_webstore/hooks.py` (`web_include_js`)
- Test: `upande_webstore/tests/test_product_page.py`

**Interfaces:**
- Consumes: pricing/stock services (Tasks 4–5), variant API (Task 8), cart API (Task 6), wishlist API (Task 10).
- Produces:
  - Product page context: `price`, `stock`, `attributes` (for templates), `is_template`, `item_doc`.
  - Global JS behaviours (event-delegated, work on any page): `[data-webstore-add-to-cart="ITEM"]` buttons, `[data-webstore-wishlist-toggle="PRODUCT"]` hearts, variant `select.webstore-attribute` handling on product pages, `#webstore-cart-badge` count updater. Guests clicking add-to-cart/wishlist are redirected to `/login?redirect-to=<current>`.
  - `window.webstore = {addToCart, toggleWishlist, refreshCartBadge}` for reuse by cart page (Task 13).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_product_page.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_html_for_route

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	set_stock,
	setup_webstore_settings,
)


class TestProductPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		cls.simple = make_test_product("WS-PAGE-ITEM", web_title="Page Widget")
		make_item_price("WS-PAGE-ITEM", "Standard Selling", 42)
		set_stock("WS-PAGE-ITEM", 3)
		make_variant_template("WS-PAGE-TMPL")
		cls.template = make_test_product("WS-PAGE-TMPL", web_title="Page Template Product")
		cls.oos = make_test_product("WS-PAGE-OOS", web_title="Page OOS Widget")
		make_item_price("WS-PAGE-OOS", "Standard Selling", 9)
		set_stock("WS-PAGE-OOS", 0)

	def test_simple_product_shows_price_and_add_to_cart(self):
		html = get_html_for_route(self.simple.route)
		self.assertIn("Page Widget", html)
		self.assertIn("42", html)
		self.assertIn('data-webstore-add-to-cart="WS-PAGE-ITEM"', html)

	def test_template_product_shows_attribute_picker(self):
		html = get_html_for_route(self.template.route)
		self.assertIn("webstore-attribute", html)
		self.assertIn("WS Size", html)

	def test_out_of_stock_has_no_enabled_add_to_cart(self):
		html = get_html_for_route(self.oos.route)
		self.assertIn("Out of stock", html)
		self.assertNotIn('data-webstore-add-to-cart="WS-PAGE-OOS"', html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_product_page
```

Expected: FAIL (placeholder template has no price / picker / button).

- [ ] **Step 3: Write the implementation**

Replace `get_context` in `webstore_product.py`:

```python
	def get_context(self, context):
		from upande_webstore.api.variants import get_attributes
		from upande_webstore.services.pricing import get_item_price
		from upande_webstore.services.stock import get_stock_info

		context.no_cache = 1
		item_doc = frappe.get_cached_doc("Item", self.item)
		context.item_doc = item_doc
		context.is_template = bool(item_doc.has_variants)
		if context.is_template:
			context.attributes = get_attributes(self.item)
			context.price = None
			context.stock = None
		else:
			context.attributes = []
			context.price = get_item_price(self.item)
			context.stock = get_stock_info(self.item)
		return context
```

Replace `upande_webstore/templates/generators/webstore_product.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ web_title }}{% endblock %}
{% block page_content %}
<div class="row" id="webstore-product" data-product="{{ name }}" data-item="{{ item }}" data-is-template="{{ 1 if is_template else 0 }}">
	<div class="col-md-5">
		{% if image %}<img src="{{ image }}" class="img-fluid" alt="{{ web_title }}">{% endif %}
	</div>
	<div class="col-md-7">
		<h1>{{ web_title }}
			<button class="btn btn-sm btn-outline-danger" data-webstore-wishlist-toggle="{{ name }}" title="{{ _('Save to wishlist') }}">♥</button>
		</h1>
		<p class="text-muted">{{ short_description or "" }}</p>

		{% if is_template %}
		{% for attr in attributes %}
		<div class="form-group">
			<label>{{ attr.attribute }}</label>
			<select class="form-control webstore-attribute" data-attribute="{{ attr.attribute }}">
				<option value="">{{ _("Select") }} {{ attr.attribute }}</option>
				{% for value in attr["values"] %}<option value="{{ value }}">{{ value }}</option>{% endfor %}
			</select>
		</div>
		{% endfor %}
		<p id="webstore-variant-price" class="h4"></p>
		<p id="webstore-variant-stock"></p>
		<button class="btn btn-primary" id="webstore-variant-add" disabled>{{ _("Add to cart") }}</button>
		{% else %}
		<p class="h4">
			{{ frappe.utils.fmt_money(price.rate, currency=price.currency) }}
			{% if price.is_customer_price %}<span class="badge badge-info">{{ _("Your price") }}</span>{% endif %}
		</p>
		{% if stock.in_stock %}
		<p><span class="badge badge-success">{{ _("In stock") }}{% if stock.show_qty %}: {{ stock.qty }}{% endif %}</span></p>
		<div class="form-inline mb-3">
			<input type="number" min="1" value="1" class="form-control mr-2" id="webstore-qty" style="width:90px">
			<button class="btn btn-primary" data-webstore-add-to-cart="{{ item }}">{{ _("Add to cart") }}</button>
		</div>
		{% else %}
		<p><span class="badge badge-secondary">{{ _("Out of stock") }}</span></p>
		<button class="btn btn-primary" disabled>{{ _("Out of stock") }}</button>
		{% endif %}
		{% endif %}

		<hr>
		<div>{{ long_description or "" }}</div>
	</div>
</div>
{% endblock %}
```

`upande_webstore/public/js/webstore.bundle.js`:

```javascript
(() => {
	const call = (method, args) =>
		fetch(`/api/method/${method}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.frappe?.csrf_token || "",
			},
			body: JSON.stringify(args || {}),
		}).then(async (r) => {
			const data = await r.json();
			if (!r.ok) {
				const server = JSON.parse(data._server_messages || "[]").map((m) => {
					try { return JSON.parse(m).message; } catch { return m; }
				});
				throw new Error(server.join(" ") || "Request failed");
			}
			return data.message;
		});

	const isGuest = () => !window.frappe || frappe.session?.user === "Guest" || !frappe.csrf_token;
	const toLogin = () => (window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`);
	const toast = (message, error) => {
		const el = document.createElement("div");
		el.className = `alert ${error ? "alert-danger" : "alert-success"} webstore-toast`;
		el.style.cssText = "position:fixed;top:70px;right:20px;z-index:1050;max-width:320px;";
		el.textContent = message;
		document.body.appendChild(el);
		setTimeout(() => el.remove(), 4000);
	};

	async function refreshCartBadge() {
		const badge = document.getElementById("webstore-cart-badge");
		if (!badge || isGuest()) return;
		try {
			const count = await call("upande_webstore.api.cart.get_cart_count");
			badge.textContent = count > 0 ? count : "";
		} catch {}
	}

	async function addToCart(itemCode, qty) {
		if (isGuest()) return toLogin();
		try {
			await call("upande_webstore.api.cart.add_item", { item_code: itemCode, qty: qty || 1 });
			toast("Added to cart");
			refreshCartBadge();
		} catch (e) {
			toast(e.message, true);
		}
	}

	async function toggleWishlist(product, button) {
		if (isGuest()) return toLogin();
		try {
			const result = await call("upande_webstore.api.wishlist.toggle", { product });
			toast(result.wishlisted ? "Saved to wishlist" : "Removed from wishlist");
			if (button && document.getElementById("wishlist-grid")) {
				button.closest(".col-md-4")?.remove();
			}
		} catch (e) {
			toast(e.message, true);
		}
	}

	document.addEventListener("click", (event) => {
		const add = event.target.closest("[data-webstore-add-to-cart]");
		if (add) {
			const qty = parseFloat(document.getElementById("webstore-qty")?.value || "1");
			addToCart(add.dataset.webstoreAddToCart, qty);
			return;
		}
		const wish = event.target.closest("[data-webstore-wishlist-toggle]");
		if (wish) toggleWishlist(wish.dataset.webstoreWishlistToggle, wish);
	});

	// Variant picker
	const productRoot = () => document.getElementById("webstore-product");
	async function onAttributeChange() {
		const root = productRoot();
		if (!root || root.dataset.isTemplate !== "1") return;
		const selects = [...document.querySelectorAll("select.webstore-attribute")];
		const addBtn = document.getElementById("webstore-variant-add");
		if (selects.some((s) => !s.value)) { addBtn.disabled = true; return; }
		const attributes = Object.fromEntries(selects.map((s) => [s.dataset.attribute, s.value]));
		try {
			const result = await call("upande_webstore.api.variants.resolve_variant", {
				template_item: root.dataset.item,
				attributes,
			});
			const priceEl = document.getElementById("webstore-variant-price");
			const stockEl = document.getElementById("webstore-variant-stock");
			if (!result.item_code) {
				priceEl.textContent = "";
				stockEl.textContent = "This combination is not available.";
				addBtn.disabled = true;
				return;
			}
			priceEl.textContent = `${result.price.currency} ${result.price.rate.toFixed(2)}`;
			stockEl.textContent = result.stock.in_stock
				? result.stock.qty != null ? `In stock: ${result.stock.qty}` : "In stock"
				: "Out of stock";
			addBtn.disabled = !result.stock.in_stock;
			addBtn.dataset.variantItem = result.item_code;
		} catch (e) {
			toast(e.message, true);
		}
	}
	document.addEventListener("change", (event) => {
		if (event.target.matches("select.webstore-attribute")) onAttributeChange();
	});
	document.addEventListener("click", (event) => {
		if (event.target.id === "webstore-variant-add" && event.target.dataset.variantItem) {
			addToCart(event.target.dataset.variantItem, 1);
		}
	});

	document.addEventListener("DOMContentLoaded", refreshCartBadge);
	window.webstore = { addToCart, toggleWishlist, refreshCartBadge, call, toast };
})();
```

In `upande_webstore/hooks.py` set:

```python
web_include_js = "webstore.bundle.js"
```

Build and migrate:

```bash
cd /home/austin/frappe-v16-bench && bench build --app upande_webstore && bench --site webstore.localhost clear-website-cache
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_product_page
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Manual page check**

```bash
curl -s -H "Host: webstore.localhost" "http://127.0.0.1:8000/store/page-widget" | grep -o "data-webstore-add-to-cart=\"WS-PAGE-ITEM\""
```

Expected: the attribute string prints once.

- [ ] **Step 6: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add product detail page and storefront JS bundle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 13: Cart page, checkout UI, and signup page

**Files:**
- Create: `upande_webstore/www/cart.py`, `upande_webstore/www/cart.html`
- Create: `upande_webstore/www/signup.py`, `upande_webstore/www/signup.html`
- Test: `upande_webstore/tests/test_cart_page.py`

**Interfaces:**
- Consumes: cart API + `serialize_cart` (Task 6), checkout API (Task 9), signup API (Task 7), `window.webstore` JS (Task 12).
- Produces: `/cart` (login-required page: line items with qty inputs/remove, totals, address selector from the Customer's Addresses, notes + PO fields, Request Quotation button → confirmation state linking to `/portal/quotations`) and `/signup` (public form posting to `upande_webstore.api.account.sign_up`). Produces `get_customer_addresses(customer) -> list[dict]` in `upande_webstore/services/portal_data.py` (reused by Task 19's account page).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_cart_page.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestCartPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("cartpage.user@example.com", "Cartpage Buyer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_addresses_helper(self):
		from upande_webstore.services.portal_data import get_customer_addresses

		address = frappe.get_doc({
			"doctype": "Address",
			"address_title": "Cartpage Buyer HQ",
			"address_type": "Shipping",
			"address_line1": "1 Test Lane",
			"city": "Nairobi",
			"country": "Kenya",
			"links": [{"link_doctype": "Customer", "link_name": "Cartpage Buyer"}],
		})
		address.insert(ignore_permissions=True)
		rows = get_customer_addresses("Cartpage Buyer")
		self.assertTrue(any(r["name"] == address.name for r in rows))

	def test_cart_page_requires_login(self):
		frappe.set_user("Guest")
		from upande_webstore.www.cart import get_context

		context = frappe._dict()
		self.assertRaises(frappe.Redirect, get_context, context)

	def test_signup_page_renders(self):
		from frappe.utils import get_html_for_route

		html = get_html_for_route("signup")
		self.assertIn("webstore-signup-form", html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_cart_page
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/portal_data.py`:

```python
import frappe


def get_customer_addresses(customer):
	address_names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
		pluck="parent",
	)
	if not address_names:
		return []
	return frappe.get_all(
		"Address",
		filters={"name": ["in", address_names]},
		fields=["name", "address_title", "address_line1", "address_line2", "city", "country", "phone"],
		order_by="modified desc",
	)
```

`upande_webstore/www/cart.py`:

```python
import frappe

from upande_webstore.services.pricing import get_customer
from upande_webstore.services.portal_data import get_customer_addresses


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/cart"
		raise frappe.Redirect
	from upande_webstore.api.cart import _get_open_cart, _reprice, serialize_cart

	context.no_cache = 1
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		cart.save(ignore_permissions=True)
	context.cart = serialize_cart(cart)
	customer = get_customer()
	context.addresses = get_customer_addresses(customer) if customer else []
	return context
```

`upande_webstore/www/cart.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Cart") }}{% endblock %}
{% block page_content %}
<h1>{{ _("Your Cart") }}</h1>
<div id="webstore-checkout-done" class="d-none">
	<div class="alert alert-success">
		{{ _("Quotation requested! Our team will review it shortly.") }}
		<a id="webstore-quotation-link" href="/portal/quotations">{{ _("View your quotations") }}</a>
	</div>
</div>
<div id="webstore-cart-wrapper">
{% if not cart["items"] %}
<p class="text-muted">{{ _("Your cart is empty.") }} <a href="/store">{{ _("Browse the store") }}</a></p>
{% else %}
<table class="table">
	<thead><tr><th>{{ _("Item") }}</th><th style="width:130px">{{ _("Qty") }}</th><th class="text-right">{{ _("Rate") }}</th><th class="text-right">{{ _("Amount") }}</th><th></th></tr></thead>
	<tbody>
	{% for row in cart["items"] %}
	<tr data-cart-row="{{ row.item_code }}">
		<td>{% if row.route %}<a href="/{{ row.route }}">{{ row.web_title }}</a>{% else %}{{ row.item_name }}{% endif %}</td>
		<td><input type="number" min="0" class="form-control form-control-sm webstore-cart-qty" data-item="{{ row.item_code }}" value="{{ row.qty }}"></td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.rate, currency=cart.currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.amount, currency=cart.currency) }}</td>
		<td><button class="btn btn-sm btn-link text-danger webstore-cart-remove" data-item="{{ row.item_code }}">✕</button></td>
	</tr>
	{% endfor %}
	</tbody>
	<tfoot><tr><th colspan="3" class="text-right">{{ _("Total") }}</th><th class="text-right">{{ frappe.utils.fmt_money(cart.total, currency=cart.currency) }}</th><th></th></tr></tfoot>
</table>

<h4>{{ _("Checkout") }}</h4>
<form id="webstore-checkout-form" onsubmit="return false;">
	<div class="form-group">
		<label>{{ _("Delivery address") }}</label>
		<select class="form-control" id="webstore-address">
			<option value="">{{ _("No address / discuss with sales") }}</option>
			{% for a in addresses %}
			<option value="{{ a.name }}">{{ a.address_title }} — {{ a.address_line1 }}, {{ a.city }}</option>
			{% endfor %}
		</select>
		<small class="form-text text-muted">{{ _("Manage addresses in") }} <a href="/portal/account">{{ _("your account") }}</a>.</small>
	</div>
	<div class="form-group"><label>{{ _("Your PO reference (optional)") }}</label>
		<input type="text" class="form-control" id="webstore-po"></div>
	<div class="form-group"><label>{{ _("Notes (optional)") }}</label>
		<textarea class="form-control" id="webstore-notes" rows="2"></textarea></div>
	<button class="btn btn-primary" id="webstore-place-order">{{ _("Request Quotation") }}</button>
</form>
{% endif %}
</div>
<script>
document.addEventListener("change", async (e) => {
	if (!e.target.matches(".webstore-cart-qty")) return;
	try {
		await window.webstore.call("upande_webstore.api.cart.update_qty",
			{ item_code: e.target.dataset.item, qty: parseFloat(e.target.value || "0") });
		window.location.reload();
	} catch (err) { window.webstore.toast(err.message, true); }
});
document.addEventListener("click", async (e) => {
	if (e.target.matches(".webstore-cart-remove")) {
		await window.webstore.call("upande_webstore.api.cart.remove_item", { item_code: e.target.dataset.item });
		window.location.reload();
	}
	if (e.target.id === "webstore-place-order") {
		e.target.disabled = true;
		try {
			const result = await window.webstore.call("upande_webstore.api.checkout.place_order", {
				address_name: document.getElementById("webstore-address").value || null,
				po_reference: document.getElementById("webstore-po").value || null,
				notes: document.getElementById("webstore-notes").value || null,
			});
			document.getElementById("webstore-cart-wrapper").classList.add("d-none");
			document.getElementById("webstore-checkout-done").classList.remove("d-none");
			document.getElementById("webstore-quotation-link").href = "/portal/quotation?name=" + encodeURIComponent(result.quotation);
			window.webstore.refreshCartBadge();
		} catch (err) {
			window.webstore.toast(err.message, true);
			e.target.disabled = false;
		}
	}
});
</script>
{% endblock %}
```

`upande_webstore/www/signup.py`:

```python
import frappe


def get_context(context):
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/portal"
		raise frappe.Redirect
	context.no_cache = 1
	return context
```

`upande_webstore/www/signup.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Create Account") }}{% endblock %}
{% block page_content %}
<div class="row justify-content-center"><div class="col-md-6">
<h1>{{ _("Create Account") }}</h1>
<form id="webstore-signup-form" onsubmit="return false;">
	<div class="form-group"><label>{{ _("Full name") }}</label>
		<input class="form-control" id="signup-name" required></div>
	<div class="form-group"><label>{{ _("Email") }}</label>
		<input type="email" class="form-control" id="signup-email" required></div>
	<div class="form-group"><label>{{ _("Phone") }}</label>
		<input class="form-control" id="signup-phone" required></div>
	<div class="form-group"><label>{{ _("Company name (leave blank for personal account)") }}</label>
		<input class="form-control" id="signup-company"></div>
	<button class="btn btn-primary" id="signup-submit">{{ _("Sign up") }}</button>
	<p class="mt-3">{{ _("Already have an account?") }} <a href="/login">{{ _("Log in") }}</a></p>
	<div id="signup-result" class="alert d-none mt-3"></div>
</form>
<script>
document.getElementById("signup-submit").addEventListener("click", async () => {
	const result = document.getElementById("signup-result");
	try {
		const message = await window.webstore.call("upande_webstore.api.account.sign_up", {
			full_name: document.getElementById("signup-name").value,
			email: document.getElementById("signup-email").value,
			phone: document.getElementById("signup-phone").value,
			company_name: document.getElementById("signup-company").value || null,
		});
		result.className = "alert alert-success mt-3";
		result.textContent = message.message;
	} catch (err) {
		result.className = "alert alert-danger mt-3";
		result.textContent = err.message;
	}
});
</script>
</div></div>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_cart_page
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Manual page check**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: webstore.localhost" "http://127.0.0.1:8000/signup"
```

Expected: `200`.

- [ ] **Step 6: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add cart/checkout page and signup page

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 14: Portal scoping service + dashboard page

**Files:**
- Create: `upande_webstore/services/portal.py`
- Create: `upande_webstore/www/portal/__init__.py` (empty), `upande_webstore/www/portal/index.py`, `upande_webstore/www/portal/index.html`
- Test: `upande_webstore/tests/test_portal_scope.py`

**Interfaces:**
- Consumes: `get_customer` (Task 4).
- Produces — THE security kernel every portal page and API uses:
  - `upande_webstore.services.portal.get_current_customer() -> str` — session user's Customer or raises `frappe.PermissionError` (also for Guest).
  - `upande_webstore.services.portal.assert_customer_doc(doctype, name, party_field) -> doc` — loads the doc (ignore_permissions) and raises `frappe.PermissionError` unless `doc.get(party_field) == get_current_customer()`.
  - `upande_webstore.services.portal.get_customer_docs(doctype, fields, party_field, filters=None, limit=20, order_by="modified desc") -> list[dict]` — always injects `{party_field: current_customer}` into filters.
  - `upande_webstore.services.portal.get_outstanding_balance() -> float` via `erpnext.accounts.utils.get_balance_on(party_type="Customer", party=...)`.
  - Dashboard page `/portal` (login required): balance, open quotations count, recent 5 Sales Orders, links to all portal sections.
  - `upande_webstore/www/portal/__init__.py` marks the folder importable; every portal controller starts with the same guard: redirect Guest to `/login?redirect-to=<route>`.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_portal_scope.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def make_quotation_for(customer):
	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": customer,
		"company": frappe.defaults.get_global_default("company"),
		"items": [{"item_code": "WS-SCOPE-ITEM", "qty": 1, "rate": 10}],
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()
	return quotation


class TestPortalScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SCOPE-ITEM")
		make_item_price("WS-SCOPE-ITEM", "Standard Selling", 10)
		make_portal_user("scope.a@example.com", "Scope Customer A")
		make_portal_user("scope.b@example.com", "Scope Customer B")
		cls.quotation_a = make_quotation_for("Scope Customer A")
		cls.quotation_b = make_quotation_for("Scope Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_get_current_customer(self):
		from upande_webstore.services.portal import get_current_customer

		frappe.set_user("scope.a@example.com")
		self.assertEqual(get_current_customer(), "Scope Customer A")

	def test_guest_raises(self):
		from upande_webstore.services.portal import get_current_customer

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, get_current_customer)

	def test_docs_are_scoped_to_own_customer(self):
		from upande_webstore.services.portal import get_customer_docs

		frappe.set_user("scope.a@example.com")
		names = [q["name"] for q in get_customer_docs("Quotation", ["name"], "party_name", limit=100)]
		self.assertIn(self.quotation_a.name, names)
		self.assertNotIn(self.quotation_b.name, names)

	def test_assert_customer_doc_blocks_other_customer(self):
		from upande_webstore.services.portal import assert_customer_doc

		frappe.set_user("scope.a@example.com")
		doc = assert_customer_doc("Quotation", self.quotation_a.name, "party_name")
		self.assertEqual(doc.name, self.quotation_a.name)
		self.assertRaises(
			frappe.PermissionError,
			assert_customer_doc, "Quotation", self.quotation_b.name, "party_name",
		)

	def test_outstanding_balance_returns_number(self):
		from upande_webstore.services.portal import get_outstanding_balance

		frappe.set_user("scope.a@example.com")
		self.assertIsInstance(get_outstanding_balance(), float)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_scope
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/portal.py`:

```python
import frappe
from frappe import _

from upande_webstore.services.pricing import get_customer


def get_current_customer():
	customer = get_customer()
	if not customer:
		frappe.throw(_("Your account is not linked to a customer."), frappe.PermissionError)
	return customer


def assert_customer_doc(doctype, name, party_field):
	customer = get_current_customer()
	doc = frappe.get_doc(doctype, name)
	if doc.get(party_field) != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return doc


def get_customer_docs(doctype, fields, party_field, filters=None, limit=20, order_by="modified desc"):
	customer = get_current_customer()
	filters = dict(filters or {})
	filters[party_field] = customer
	return frappe.get_all(
		doctype, filters=filters, fields=fields, limit_page_length=limit, order_by=order_by
	)


def get_outstanding_balance():
	from erpnext.accounts.utils import get_balance_on

	customer = get_current_customer()
	return float(get_balance_on(party_type="Customer", party=customer) or 0.0)


def portal_guard(route):
	"""Redirect guests to login; returns the current customer."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={route}"
		raise frappe.Redirect
	return get_current_customer()
```

`upande_webstore/www/portal/index.py`:

```python
import frappe

from upande_webstore.services.portal import (
	get_customer_docs,
	get_outstanding_balance,
	portal_guard,
)


def get_context(context):
	customer = portal_guard("/portal")
	context.no_cache = 1
	context.customer = customer
	context.balance = get_outstanding_balance()
	context.currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	context.open_quotations = len(
		get_customer_docs(
			"Quotation", ["name"], "party_name",
			filters={"docstatus": 1, "status": ["not in", ["Lost", "Ordered", "Expired"]]},
			limit=100,
		)
	)
	context.recent_orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "grand_total", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=5,
		order_by="transaction_date desc",
	)
	return context
```

`upande_webstore/www/portal/index.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("My Account") }}{% endblock %}
{% block page_content %}
<h1>{{ _("Welcome") }}, {{ customer }}</h1>
<div class="row my-4">
	<div class="col-md-4"><div class="card"><div class="card-body">
		<h6 class="text-muted">{{ _("Outstanding balance") }}</h6>
		<p class="h4">{{ frappe.utils.fmt_money(balance, currency=currency) }}</p>
		<a href="/portal/statement">{{ _("View statement") }}</a>
	</div></div></div>
	<div class="col-md-4"><div class="card"><div class="card-body">
		<h6 class="text-muted">{{ _("Open quotations") }}</h6>
		<p class="h4">{{ open_quotations }}</p>
		<a href="/portal/quotations">{{ _("View quotations") }}</a>
	</div></div></div>
	<div class="col-md-4"><div class="card"><div class="card-body">
		<h6 class="text-muted">{{ _("Quick links") }}</h6>
		<a href="/store">{{ _("Store") }}</a> · <a href="/wishlist">{{ _("Wishlist") }}</a> ·
		<a href="/portal/orders">{{ _("Orders") }}</a> · <a href="/portal/invoices">{{ _("Invoices") }}</a> ·
		<a href="/portal/support">{{ _("Support") }}</a> · <a href="/portal/account">{{ _("Account") }}</a>
	</div></div></div>
</div>
<h4>{{ _("Recent orders") }}</h4>
{% if not recent_orders %}<p class="text-muted">{{ _("No orders yet.") }}</p>{% else %}
<table class="table">
	<thead><tr><th>{{ _("Order") }}</th><th>{{ _("Date") }}</th><th>{{ _("Status") }}</th><th class="text-right">{{ _("Total") }}</th></tr></thead>
	<tbody>
	{% for order in recent_orders %}
	<tr>
		<td><a href="/portal/order?name={{ order.name | urlencode }}">{{ order.name }}</a></td>
		<td>{{ frappe.utils.formatdate(order.transaction_date) }}</td>
		<td>{{ order.status }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(order.grand_total, currency=order.currency) }}</td>
	</tr>
	{% endfor %}
	</tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_scope
```

Expected: `OK` (5 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add portal scoping service and dashboard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 15: Portal quotations (list, detail, accept/decline)

**Files:**
- Create: `upande_webstore/api/portal.py`
- Create: `upande_webstore/www/portal/quotations.py`, `quotations.html`, `quotation.py`, `quotation.html`
- Test: `upande_webstore/tests/test_portal_quotations.py`

**Interfaces:**
- Consumes: portal service (Task 14), custom fields `webstore_portal_status` (Task 9), settings notification emails.
- Produces:
  - Whitelisted `upande_webstore.api.portal.accept_quotation(name)` / `decline_quotation(name)` — ownership-checked via `assert_customer_doc("Quotation", name, "party_name")`; only for `docstatus=1` and empty `webstore_portal_status`; sets `webstore_portal_status` (db_set — doc is submitted), adds a Comment on the Quotation, and emails settings recipients. Returns `{"status": "Accepted"|"Declined"}`.
  - `/portal/quotations` list (name, date, valid till, status incl. portal status, total) and `/portal/quotation?name=X` detail (line items, totals, notes/PO ref, Accept & Decline buttons shown only when actionable).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_portal_quotations.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_portal_scope import make_quotation_for
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestPortalQuotations(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SCOPE-ITEM")
		make_item_price("WS-SCOPE-ITEM", "Standard Selling", 10)
		make_portal_user("pq.a@example.com", "PQ Customer A")
		make_portal_user("pq.b@example.com", "PQ Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_accept_sets_portal_status(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		result = accept_quotation(quotation.name)
		self.assertEqual(result["status"], "Accepted")
		self.assertEqual(
			frappe.db.get_value("Quotation", quotation.name, "webstore_portal_status"), "Accepted"
		)

	def test_decline_sets_portal_status(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import decline_quotation

		frappe.set_user("pq.a@example.com")
		result = decline_quotation(quotation.name)
		self.assertEqual(result["status"], "Declined")

	def test_cannot_act_on_other_customers_quotation(self):
		quotation = make_quotation_for("PQ Customer B")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		self.assertRaises(frappe.PermissionError, accept_quotation, quotation.name)

	def test_cannot_accept_twice(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		accept_quotation(quotation.name)
		self.assertRaises(frappe.ValidationError, accept_quotation, quotation.name)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_quotations
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/api/portal.py`:

```python
import frappe
from frappe import _
from frappe.utils import get_url_to_form

from upande_webstore.services.portal import assert_customer_doc
from upande_webstore.services.settings import get_settings


def _act_on_quotation(name, status):
	quotation = assert_customer_doc("Quotation", name, "party_name")
	if quotation.docstatus != 1:
		frappe.throw(_("This quotation is not open."), frappe.ValidationError)
	if quotation.webstore_portal_status:
		frappe.throw(
			_("You have already responded to this quotation."), frappe.ValidationError
		)
	quotation.db_set("webstore_portal_status", status)
	quotation.add_comment(
		"Comment", _("Customer {0} this quotation via the webstore portal.").format(status.lower())
	)
	_notify(quotation, status)
	return {"status": status}


def _notify(quotation, status):
	settings = get_settings()
	recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
	if not recipients:
		return
	frappe.sendmail(
		recipients=recipients,
		subject=_("Quotation {0} {1} by customer").format(quotation.name, status.lower()),
		message=_("Quotation {0} was {1} by {2} on the portal.<br>{3}").format(
			quotation.name, status.lower(), quotation.party_name,
			get_url_to_form("Quotation", quotation.name),
		),
	)


@frappe.whitelist(methods=["POST"])
def accept_quotation(name):
	return _act_on_quotation(name, "Accepted")


@frappe.whitelist(methods=["POST"])
def decline_quotation(name):
	return _act_on_quotation(name, "Declined")
```

`upande_webstore/www/portal/quotations.py`:

```python
import frappe

from upande_webstore.services.portal import get_customer_docs, portal_guard


def get_context(context):
	portal_guard("/portal/quotations")
	context.no_cache = 1
	context.quotations = get_customer_docs(
		"Quotation",
		["name", "transaction_date", "valid_till", "status", "webstore_portal_status", "grand_total", "currency"],
		"party_name",
		filters={"docstatus": 1},
		limit=50,
		order_by="transaction_date desc",
	)
	return context
```

`upande_webstore/www/portal/quotations.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("My Quotations") }}{% endblock %}
{% block page_content %}
<h1>{{ _("My Quotations") }}</h1>
{% if not quotations %}<p class="text-muted">{{ _("No quotations yet.") }}</p>{% else %}
<table class="table">
	<thead><tr><th>{{ _("Quotation") }}</th><th>{{ _("Date") }}</th><th>{{ _("Valid till") }}</th><th>{{ _("Status") }}</th><th class="text-right">{{ _("Total") }}</th></tr></thead>
	<tbody>
	{% for q in quotations %}
	<tr>
		<td><a href="/portal/quotation?name={{ q.name | urlencode }}">{{ q.name }}</a></td>
		<td>{{ frappe.utils.formatdate(q.transaction_date) }}</td>
		<td>{{ frappe.utils.formatdate(q.valid_till) if q.valid_till else "" }}</td>
		<td>{{ q.webstore_portal_status or q.status }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(q.grand_total, currency=q.currency) }}</td>
	</tr>
	{% endfor %}
	</tbody>
</table>
{% endif %}
{% endblock %}
```

`upande_webstore/www/portal/quotation.py`:

```python
import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_guard


def get_context(context):
	portal_guard("/portal/quotations")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/quotations"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = assert_customer_doc("Quotation", name, "party_name")
	context.actionable = context.doc.docstatus == 1 and not context.doc.webstore_portal_status
	return context
```

`upande_webstore/www/portal/quotation.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ doc.name }}{% endblock %}
{% block page_content %}
<a href="/portal/quotations">← {{ _("All quotations") }}</a>
<h1>{{ doc.name }}</h1>
<p>
	{{ _("Status") }}: <strong>{{ doc.webstore_portal_status or doc.status }}</strong>
	{% if doc.valid_till %} · {{ _("Valid till") }} {{ frappe.utils.formatdate(doc.valid_till) }}{% endif %}
	{% if doc.customer_po_reference %} · {{ _("PO Ref") }}: {{ doc.customer_po_reference }}{% endif %}
</p>
{% if doc.webstore_notes %}<p class="text-muted">{{ _("Notes") }}: {{ doc.webstore_notes }}</p>{% endif %}
<table class="table">
	<thead><tr><th>{{ _("Item") }}</th><th class="text-right">{{ _("Qty") }}</th><th class="text-right">{{ _("Rate") }}</th><th class="text-right">{{ _("Amount") }}</th></tr></thead>
	<tbody>
	{% for row in doc.items %}
	<tr><td>{{ row.item_name }}</td><td class="text-right">{{ row.qty }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td></tr>
	{% endfor %}
	</tbody>
	<tfoot><tr><th colspan="3" class="text-right">{{ _("Grand Total") }}</th>
		<th class="text-right">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</th></tr></tfoot>
</table>
{% if actionable %}
<button class="btn btn-success" id="quotation-accept">{{ _("Accept Quotation") }}</button>
<button class="btn btn-outline-danger" id="quotation-decline">{{ _("Decline") }}</button>
<script>
["accept", "decline"].forEach((action) => {
	document.getElementById(`quotation-${action}`).addEventListener("click", async () => {
		if (!confirm(`${action === "accept" ? "Accept" : "Decline"} this quotation?`)) return;
		try {
			await window.webstore.call(`upande_webstore.api.portal.${action}_quotation`,
				{ name: {{ doc.name | tojson }} });
			window.location.reload();
		} catch (err) { window.webstore.toast(err.message, true); }
	});
});
</script>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_quotations
```

Expected: `OK` (4 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add portal quotations with accept/decline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 16: Portal orders + invoices (with PDF download)

**Files:**
- Create: `upande_webstore/www/portal/orders.py`, `orders.html`, `order.py`, `order.html`
- Create: `upande_webstore/www/portal/invoices.py`, `invoices.html`, `invoice.py`, `invoice.html`
- Modify: `upande_webstore/api/portal.py` (add `download_invoice_pdf`)
- Test: `upande_webstore/tests/test_portal_orders.py`

**Interfaces:**
- Consumes: portal service (Task 14).
- Produces:
  - `/portal/orders` + `/portal/order?name=X`: submitted Sales Orders — status, `per_delivered`, `per_billed`, line items.
  - `/portal/invoices` + `/portal/invoice?name=X`: submitted Sales Invoices — status badge (Paid / Unpaid / Overdue from `status`), outstanding, line items, Download PDF button.
  - Whitelisted `upande_webstore.api.portal.download_invoice_pdf(name)` — ownership-checked, then renders default print format as PDF (`frappe.get_print(..., as_pdf=True)` with `doc` passed explicitly to bypass desk read permission after our own check) and returns it as a file response.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_portal_orders.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


def make_sales_invoice_for(customer):
	invoice = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": frappe.defaults.get_global_default("company"),
		"items": [{"item_code": "WS-ORD-ITEM", "qty": 1, "rate": 10}],
	})
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


class TestPortalOrders(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-ORD-ITEM", is_stock_item=0)
		make_item_price("WS-ORD-ITEM", "Standard Selling", 10)
		make_portal_user("ord.a@example.com", "Ord Customer A")
		make_portal_user("ord.b@example.com", "Ord Customer B")
		cls.invoice_a = make_sales_invoice_for("Ord Customer A")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_invoice_pdf_for_own_invoice(self):
		from upande_webstore.api.portal import download_invoice_pdf

		frappe.set_user("ord.a@example.com")
		download_invoice_pdf(self.invoice_a.name)
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertTrue(frappe.local.response.filecontent[:4] == b"%PDF")

	def test_invoice_pdf_blocked_for_other_customer(self):
		from upande_webstore.api.portal import download_invoice_pdf

		frappe.set_user("ord.b@example.com")
		self.assertRaises(frappe.PermissionError, download_invoice_pdf, self.invoice_a.name)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_orders
```

Expected: ImportError (`download_invoice_pdf` missing).

- [ ] **Step 3: Write the implementation**

Append to `upande_webstore/api/portal.py`:

```python
@frappe.whitelist()
def download_invoice_pdf(name):
	invoice = assert_customer_doc("Sales Invoice", name, "customer")
	# Ownership verified above; pass doc explicitly so printview does not
	# re-run desk permission checks for the website user.
	pdf = frappe.get_print("Sales Invoice", name, doc=invoice, as_pdf=True)
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
```

(If `frappe.get_print` still enforces read permission in v16, wrap the call in `frappe.flags.ignore_permissions`—style guard: temporarily `frappe.set_user("Administrator")` in a `try/finally` that restores the session user. The ownership check above is the real gate.)

`upande_webstore/www/portal/orders.py`:

```python
import frappe

from upande_webstore.services.portal import get_customer_docs, portal_guard


def get_context(context):
	portal_guard("/portal/orders")
	context.no_cache = 1
	context.orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "per_delivered", "per_billed", "grand_total", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=50,
		order_by="transaction_date desc",
	)
	return context
```

`upande_webstore/www/portal/orders.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("My Orders") }}{% endblock %}
{% block page_content %}
<h1>{{ _("My Orders") }}</h1>
{% if not orders %}<p class="text-muted">{{ _("No orders yet.") }}</p>{% else %}
<table class="table">
	<thead><tr><th>{{ _("Order") }}</th><th>{{ _("Date") }}</th><th>{{ _("Status") }}</th><th>{{ _("Delivered") }}</th><th>{{ _("Billed") }}</th><th class="text-right">{{ _("Total") }}</th></tr></thead>
	<tbody>
	{% for o in orders %}
	<tr>
		<td><a href="/portal/order?name={{ o.name | urlencode }}">{{ o.name }}</a></td>
		<td>{{ frappe.utils.formatdate(o.transaction_date) }}</td>
		<td>{{ o.status }}</td>
		<td>{{ o.per_delivered | int }}%</td>
		<td>{{ o.per_billed | int }}%</td>
		<td class="text-right">{{ frappe.utils.fmt_money(o.grand_total, currency=o.currency) }}</td>
	</tr>
	{% endfor %}
	</tbody>
</table>
{% endif %}
{% endblock %}
```

`upande_webstore/www/portal/order.py`:

```python
import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_guard


def get_context(context):
	portal_guard("/portal/orders")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/orders"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = assert_customer_doc("Sales Order", name, "customer")
	return context
```

`upande_webstore/www/portal/order.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ doc.name }}{% endblock %}
{% block page_content %}
<a href="/portal/orders">← {{ _("All orders") }}</a>
<h1>{{ doc.name }}</h1>
<p>{{ _("Status") }}: <strong>{{ doc.status }}</strong> ·
	{{ _("Delivered") }}: {{ doc.per_delivered | int }}% · {{ _("Billed") }}: {{ doc.per_billed | int }}%</p>
<table class="table">
	<thead><tr><th>{{ _("Item") }}</th><th class="text-right">{{ _("Qty") }}</th><th class="text-right">{{ _("Rate") }}</th><th class="text-right">{{ _("Amount") }}</th></tr></thead>
	<tbody>
	{% for row in doc.items %}
	<tr><td>{{ row.item_name }}</td><td class="text-right">{{ row.qty }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td></tr>
	{% endfor %}
	</tbody>
	<tfoot><tr><th colspan="3" class="text-right">{{ _("Grand Total") }}</th>
		<th class="text-right">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</th></tr></tfoot>
</table>
{% endblock %}
```

`upande_webstore/www/portal/invoices.py`:

```python
import frappe

from upande_webstore.services.portal import get_customer_docs, portal_guard


def get_context(context):
	portal_guard("/portal/invoices")
	context.no_cache = 1
	context.invoices = get_customer_docs(
		"Sales Invoice",
		["name", "posting_date", "due_date", "status", "grand_total", "outstanding_amount", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=50,
		order_by="posting_date desc",
	)
	return context
```

`upande_webstore/www/portal/invoices.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("My Invoices") }}{% endblock %}
{% block page_content %}
<h1>{{ _("My Invoices") }}</h1>
{% if not invoices %}<p class="text-muted">{{ _("No invoices yet.") }}</p>{% else %}
<table class="table">
	<thead><tr><th>{{ _("Invoice") }}</th><th>{{ _("Date") }}</th><th>{{ _("Due") }}</th><th>{{ _("Status") }}</th><th class="text-right">{{ _("Total") }}</th><th class="text-right">{{ _("Outstanding") }}</th><th></th></tr></thead>
	<tbody>
	{% for inv in invoices %}
	<tr>
		<td><a href="/portal/invoice?name={{ inv.name | urlencode }}">{{ inv.name }}</a></td>
		<td>{{ frappe.utils.formatdate(inv.posting_date) }}</td>
		<td>{{ frappe.utils.formatdate(inv.due_date) if inv.due_date else "" }}</td>
		<td><span class="badge badge-{{ 'success' if inv.status == 'Paid' else ('danger' if inv.status == 'Overdue' else 'warning') }}">{{ inv.status }}</span></td>
		<td class="text-right">{{ frappe.utils.fmt_money(inv.grand_total, currency=inv.currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(inv.outstanding_amount, currency=inv.currency) }}</td>
		<td><a class="btn btn-sm btn-outline-secondary" href="/api/method/upande_webstore.api.portal.download_invoice_pdf?name={{ inv.name | urlencode }}">{{ _("PDF") }}</a></td>
	</tr>
	{% endfor %}
	</tbody>
</table>
{% endif %}
{% endblock %}
```

`upande_webstore/www/portal/invoice.py`:

```python
import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_guard


def get_context(context):
	portal_guard("/portal/invoices")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/invoices"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = assert_customer_doc("Sales Invoice", name, "customer")
	return context
```

`upande_webstore/www/portal/invoice.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ doc.name }}{% endblock %}
{% block page_content %}
<a href="/portal/invoices">← {{ _("All invoices") }}</a>
<h1>{{ doc.name }}
	<a class="btn btn-sm btn-outline-secondary" href="/api/method/upande_webstore.api.portal.download_invoice_pdf?name={{ doc.name | urlencode }}">{{ _("Download PDF") }}</a>
</h1>
<p>{{ _("Status") }}: <strong>{{ doc.status }}</strong> ·
	{{ _("Outstanding") }}: {{ frappe.utils.fmt_money(doc.outstanding_amount, currency=doc.currency) }}</p>
<table class="table">
	<thead><tr><th>{{ _("Item") }}</th><th class="text-right">{{ _("Qty") }}</th><th class="text-right">{{ _("Rate") }}</th><th class="text-right">{{ _("Amount") }}</th></tr></thead>
	<tbody>
	{% for row in doc.items %}
	<tr><td>{{ row.item_name }}</td><td class="text-right">{{ row.qty }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.rate, currency=doc.currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.amount, currency=doc.currency) }}</td></tr>
	{% endfor %}
	</tbody>
	<tfoot><tr><th colspan="3" class="text-right">{{ _("Grand Total") }}</th>
		<th class="text-right">{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</th></tr></tfoot>
</table>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_portal_orders
```

Expected: `OK` (2 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add portal orders and invoices with PDF download

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 17: Portal statement & balance

**Files:**
- Create: `upande_webstore/services/statement.py`
- Create: `upande_webstore/www/portal/statement.py`, `statement.html`
- Test: `upande_webstore/tests/test_statement.py`

**Interfaces:**
- Consumes: portal service (Task 14), invoice fixture pattern from Task 16.
- Produces: `upande_webstore.services.statement.get_statement(from_date, to_date) -> dict` — `{"opening": float, "closing": float, "rows": [{posting_date, voucher_type, voucher_no, debit, credit, balance}]}` from GL Entries of the current customer (running balance; opening = sum of debit-credit before `from_date`). Page `/portal/statement` with date filters (`?from=&to=`, default last 90 days) and a print button (`window.print()`).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_statement.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.test_portal_orders import make_sales_invoice_for
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestStatement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-ORD-ITEM", is_stock_item=0)
		make_item_price("WS-ORD-ITEM", "Standard Selling", 10)
		make_portal_user("stmt.a@example.com", "Stmt Customer A")
		make_portal_user("stmt.b@example.com", "Stmt Customer B")
		cls.invoice = make_sales_invoice_for("Stmt Customer A")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_statement_includes_own_invoice(self):
		from upande_webstore.services.statement import get_statement

		frappe.set_user("stmt.a@example.com")
		result = get_statement(add_days(nowdate(), -30), nowdate())
		vouchers = [r["voucher_no"] for r in result["rows"]]
		self.assertIn(self.invoice.name, vouchers)
		self.assertEqual(result["closing"], result["opening"] + sum(r["debit"] - r["credit"] for r in result["rows"]))

	def test_statement_excludes_other_customer(self):
		from upande_webstore.services.statement import get_statement

		frappe.set_user("stmt.b@example.com")
		result = get_statement(add_days(nowdate(), -30), nowdate())
		vouchers = [r["voucher_no"] for r in result["rows"]]
		self.assertNotIn(self.invoice.name, vouchers)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_statement
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/services/statement.py`:

```python
import frappe

from upande_webstore.services.portal import get_current_customer


def get_statement(from_date, to_date):
	customer = get_current_customer()
	base_filters = {
		"party_type": "Customer",
		"party": customer,
		"is_cancelled": 0,
	}
	opening = frappe.db.get_value(
		"GL Entry",
		{**base_filters, "posting_date": ["<", from_date]},
		"sum(debit) - sum(credit)",
	) or 0.0
	entries = frappe.get_all(
		"GL Entry",
		filters={**base_filters, "posting_date": ["between", [from_date, to_date]]},
		fields=["posting_date", "voucher_type", "voucher_no", "debit", "credit"],
		order_by="posting_date asc, creation asc",
	)
	balance = float(opening)
	rows = []
	for entry in entries:
		balance += float(entry.debit) - float(entry.credit)
		rows.append({
			"posting_date": entry.posting_date,
			"voucher_type": entry.voucher_type,
			"voucher_no": entry.voucher_no,
			"debit": float(entry.debit),
			"credit": float(entry.credit),
			"balance": balance,
		})
	return {"opening": float(opening), "closing": balance, "rows": rows}
```

`upande_webstore/www/portal/statement.py`:

```python
import frappe
from frappe.utils import add_days, getdate, nowdate

from upande_webstore.services.portal import portal_guard
from upande_webstore.services.statement import get_statement


def get_context(context):
	portal_guard("/portal/statement")
	context.no_cache = 1
	context.from_date = getdate(frappe.form_dict.get("from") or add_days(nowdate(), -90))
	context.to_date = getdate(frappe.form_dict.get("to") or nowdate())
	context.statement = get_statement(context.from_date, context.to_date)
	context.currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	return context
```

`upande_webstore/www/portal/statement.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Account Statement") }}{% endblock %}
{% block page_content %}
<h1>{{ _("Account Statement") }}
	<button class="btn btn-sm btn-outline-secondary" onclick="window.print()">{{ _("Print / PDF") }}</button>
</h1>
<form method="get" action="/portal/statement" class="form-inline mb-3">
	<label class="mr-2">{{ _("From") }}</label>
	<input type="date" name="from" class="form-control mr-3" value="{{ from_date }}">
	<label class="mr-2">{{ _("To") }}</label>
	<input type="date" name="to" class="form-control mr-3" value="{{ to_date }}">
	<button class="btn btn-secondary">{{ _("Apply") }}</button>
</form>
<table class="table table-sm">
	<thead><tr><th>{{ _("Date") }}</th><th>{{ _("Document") }}</th><th class="text-right">{{ _("Debit") }}</th><th class="text-right">{{ _("Credit") }}</th><th class="text-right">{{ _("Balance") }}</th></tr></thead>
	<tbody>
	<tr><td colspan="4"><em>{{ _("Opening balance") }}</em></td>
		<td class="text-right">{{ frappe.utils.fmt_money(statement.opening, currency=currency) }}</td></tr>
	{% for row in statement.rows %}
	<tr>
		<td>{{ frappe.utils.formatdate(row.posting_date) }}</td>
		<td>{{ row.voucher_type }} {{ row.voucher_no }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.debit, currency=currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.credit, currency=currency) }}</td>
		<td class="text-right">{{ frappe.utils.fmt_money(row.balance, currency=currency) }}</td>
	</tr>
	{% endfor %}
	<tr><td colspan="4"><strong>{{ _("Closing balance") }}</strong></td>
		<td class="text-right"><strong>{{ frappe.utils.fmt_money(statement.closing, currency=currency) }}</strong></td></tr>
	</tbody>
</table>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_statement
```

Expected: `OK` (2 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add portal account statement

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 18: Portal support (Issues)

**Files:**
- Create: `upande_webstore/api/support.py`
- Create: `upande_webstore/www/portal/support.py`, `support.html`, `issue.py`, `issue.html`
- Test: `upande_webstore/tests/test_support.py`

**Interfaces:**
- Consumes: portal service (Task 14).
- Produces:
  - Whitelisted `upande_webstore.api.support.create_issue(subject, description) -> {"name": str}` — login required; creates an Issue with `raised_by = session user`, `customer = current customer`. (Attachments: the page uploads via the standard `/api/method/upload_file` with `doctype=Issue&docname=<name>` after creation.)
  - `/portal/support` — list of the customer's Issues (subject, status, date) + a "New issue" form; `/portal/issue?name=X` — detail with description, status, and replies (Communications referencing the Issue, sorted oldest first).
  - Ownership for issues: `Issue.customer == current customer` OR `raised_by == session user` (covers issues created before Contact/Customer linkage).

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_support.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestSupport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("sup.a@example.com", "Sup Customer A")
		make_portal_user("sup.b@example.com", "Sup Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_create_and_list_issue(self):
		from upande_webstore.api.support import create_issue, get_issues

		frappe.set_user("sup.a@example.com")
		result = create_issue("Broken sensor", "It stopped reporting data.")
		issue = frappe.get_doc("Issue", result["name"])
		self.assertEqual(issue.customer, "Sup Customer A")
		self.assertEqual(issue.raised_by, "sup.a@example.com")
		names = [i["name"] for i in get_issues()]
		self.assertIn(result["name"], names)

	def test_other_customer_cannot_see_issue(self):
		from upande_webstore.api.support import create_issue, get_issue_or_throw, get_issues

		frappe.set_user("sup.a@example.com")
		result = create_issue("Private issue", "Details")
		frappe.set_user("sup.b@example.com")
		names = [i["name"] for i in get_issues()]
		self.assertNotIn(result["name"], names)
		self.assertRaises(frappe.PermissionError, get_issue_or_throw, result["name"])

	def test_empty_subject_rejected(self):
		from upande_webstore.api.support import create_issue

		frappe.set_user("sup.a@example.com")
		self.assertRaises(frappe.ValidationError, create_issue, "", "no subject")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_support
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

`upande_webstore/api/support.py`:

```python
import frappe
from frappe import _

from upande_webstore.api.cart import _require_login
from upande_webstore.services.portal import get_current_customer


@frappe.whitelist(methods=["POST"])
def create_issue(subject, description):
	_require_login()
	customer = get_current_customer()
	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required."), frappe.ValidationError)
	issue = frappe.get_doc({
		"doctype": "Issue",
		"subject": subject,
		"description": description,
		"raised_by": frappe.session.user,
		"customer": customer,
	})
	issue.flags.ignore_permissions = True
	issue.insert()
	return {"name": issue.name}


def get_issues(limit=50):
	_require_login()
	customer = get_current_customer()
	return frappe.get_all(
		"Issue",
		or_filters=[["customer", "=", customer], ["raised_by", "=", frappe.session.user]],
		fields=["name", "subject", "status", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)


def get_issue_or_throw(name):
	_require_login()
	customer = get_current_customer()
	issue = frappe.get_doc("Issue", name)
	if issue.customer != customer and issue.raised_by != frappe.session.user:
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return issue


def get_replies(issue_name):
	return frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Issue", "reference_name": issue_name},
		fields=["sender", "content", "communication_date", "sent_or_received"],
		order_by="communication_date asc",
	)
```

`upande_webstore/www/portal/support.py`:

```python
import frappe

from upande_webstore.api.support import get_issues
from upande_webstore.services.portal import portal_guard


def get_context(context):
	portal_guard("/portal/support")
	context.no_cache = 1
	context.issues = get_issues()
	return context
```

`upande_webstore/www/portal/support.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Support") }}{% endblock %}
{% block page_content %}
<h1>{{ _("Support") }}</h1>
<div class="card mb-4"><div class="card-body">
	<h5>{{ _("Raise a new issue") }}</h5>
	<form id="webstore-issue-form" onsubmit="return false;">
		<div class="form-group"><input class="form-control" id="issue-subject" placeholder="{{ _('Subject') }}"></div>
		<div class="form-group"><textarea class="form-control" id="issue-description" rows="3" placeholder="{{ _('Describe the problem…') }}"></textarea></div>
		<div class="form-group"><input type="file" id="issue-attachment"></div>
		<button class="btn btn-primary" id="issue-submit">{{ _("Submit") }}</button>
	</form>
</div></div>
<h4>{{ _("Your issues") }}</h4>
{% if not issues %}<p class="text-muted">{{ _("No issues raised.") }}</p>{% else %}
<table class="table">
	<thead><tr><th>{{ _("Subject") }}</th><th>{{ _("Status") }}</th><th>{{ _("Raised on") }}</th></tr></thead>
	<tbody>
	{% for issue in issues %}
	<tr>
		<td><a href="/portal/issue?name={{ issue.name | urlencode }}">{{ issue.subject }}</a></td>
		<td>{{ issue.status }}</td>
		<td>{{ frappe.utils.formatdate(issue.creation) }}</td>
	</tr>
	{% endfor %}
	</tbody>
</table>
{% endif %}
<script>
document.getElementById("issue-submit").addEventListener("click", async () => {
	try {
		const result = await window.webstore.call("upande_webstore.api.support.create_issue", {
			subject: document.getElementById("issue-subject").value,
			description: document.getElementById("issue-description").value,
		});
		const file = document.getElementById("issue-attachment").files[0];
		if (file) {
			const form = new FormData();
			form.append("file", file);
			form.append("doctype", "Issue");
			form.append("docname", result.name);
			await fetch("/api/method/upload_file", {
				method: "POST",
				headers: { "X-Frappe-CSRF-Token": window.frappe?.csrf_token || "" },
				body: form,
			});
		}
		window.location.href = "/portal/issue?name=" + encodeURIComponent(result.name);
	} catch (err) { window.webstore.toast(err.message, true); }
});
</script>
{% endblock %}
```

`upande_webstore/www/portal/issue.py`:

```python
import frappe

from upande_webstore.api.support import get_issue_or_throw, get_replies
from upande_webstore.services.portal import portal_guard


def get_context(context):
	portal_guard("/portal/support")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/support"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = get_issue_or_throw(name)
	context.replies = get_replies(name)
	return context
```

`upande_webstore/www/portal/issue.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ doc.subject }}{% endblock %}
{% block page_content %}
<a href="/portal/support">← {{ _("All issues") }}</a>
<h1>{{ doc.subject }} <span class="badge badge-info">{{ doc.status }}</span></h1>
<div class="card mb-3"><div class="card-body">{{ doc.description or "" }}</div></div>
<h4>{{ _("Replies") }}</h4>
{% if not replies %}<p class="text-muted">{{ _("No replies yet.") }}</p>{% endif %}
{% for reply in replies %}
<div class="card mb-2"><div class="card-body">
	<p class="small text-muted mb-1">{{ reply.sender }} — {{ frappe.utils.format_datetime(reply.communication_date) }}</p>
	<div>{{ reply.content }}</div>
</div></div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_support
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add portal support pages backed by Issues

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 19: Account page, navbar/menu integration, README, full run

**Files:**
- Create: `upande_webstore/www/portal/account.py`, `account.html`
- Modify: `upande_webstore/api/account.py` (add `update_profile`, `add_address`)
- Modify: `upande_webstore/hooks.py` (portal menu items, website route rules if needed)
- Create/Modify: `README.md`
- Test: `upande_webstore/tests/test_account.py`

**Interfaces:**
- Consumes: `get_customer_addresses` (Task 13), portal service, signup API module (Task 7).
- Produces:
  - Whitelisted `upande_webstore.api.account.update_profile(full_name, phone) -> {"message"}` — updates the session User (+ Contact first_name/phone).
  - Whitelisted `upande_webstore.api.account.add_address(address_title, address_line1, city, country, phone=None) -> {"name"}` — creates an Address linked to the current customer.
  - `/portal/account`: profile form, address list + add-address form, link to `/update-password`.
  - `hooks.py` `standard_portal_menu_items` entries for Store, Cart, Wishlist, Quotations, Orders, Invoices, Statement, Support, Account (so they appear in the standard `/me` menu too).
  - `README.md`: what the app is, install steps (`bench get-app /home/austin/vscodeProjects/upande_webstore && bench --site <site> install-app upande_webstore`), Webstore Settings configuration checklist, publishing products, and the quotation-first order flow.

- [ ] **Step 1: Write the failing test**

`upande_webstore/tests/test_account.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestAccount(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("acct.user@example.com", "Acct Customer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_update_profile(self):
		from upande_webstore.api.account import update_profile

		frappe.set_user("acct.user@example.com")
		update_profile("Updated Name", "+254711111111")
		self.assertEqual(
			frappe.db.get_value("User", "acct.user@example.com", "first_name"), "Updated Name"
		)

	def test_add_address_links_to_customer(self):
		from upande_webstore.api.account import add_address
		from upande_webstore.services.portal_data import get_customer_addresses

		frappe.set_user("acct.user@example.com")
		result = add_address("Acct HQ", "5 Portal Road", "Nairobi", "Kenya")
		rows = get_customer_addresses("Acct Customer")
		self.assertIn(result["name"], [r["name"] for r in rows])

	def test_guest_cannot_update_profile(self):
		from upande_webstore.api.account import update_profile

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, update_profile, "X", "1")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_account
```

Expected: ImportError (`update_profile` missing).

- [ ] **Step 3: Write the implementation**

Append to `upande_webstore/api/account.py`:

```python
@frappe.whitelist(methods=["POST"])
def update_profile(full_name, phone):
	from upande_webstore.api.cart import _require_login

	_require_login()
	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Name is required."), frappe.ValidationError)
	user = frappe.get_doc("User", frappe.session.user)
	user.first_name = full_name
	user.mobile_no = phone
	user.flags.ignore_permissions = True
	user.save()
	contact_name = frappe.db.get_value("Contact", {"user": frappe.session.user})
	if contact_name:
		frappe.db.set_value("Contact", contact_name, {"first_name": full_name})
	return {"message": _("Profile updated.")}


@frappe.whitelist(methods=["POST"])
def add_address(address_title, address_line1, city, country, phone=None):
	from upande_webstore.api.cart import _require_login
	from upande_webstore.services.portal import get_current_customer

	_require_login()
	customer = get_current_customer()
	if not (address_title and address_line1 and city and country):
		frappe.throw(_("All address fields except phone are required."), frappe.ValidationError)
	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": address_title,
		"address_type": "Shipping",
		"address_line1": address_line1,
		"city": city,
		"country": country,
		"phone": phone,
		"links": [{"link_doctype": "Customer", "link_name": customer}],
	})
	address.flags.ignore_permissions = True
	address.insert()
	return {"name": address.name}
```

`upande_webstore/www/portal/account.py`:

```python
import frappe

from upande_webstore.services.portal import portal_guard
from upande_webstore.services.portal_data import get_customer_addresses


def get_context(context):
	customer = portal_guard("/portal/account")
	context.no_cache = 1
	context.user_doc = frappe.get_doc("User", frappe.session.user)
	context.customer = customer
	context.addresses = get_customer_addresses(customer)
	return context
```

`upande_webstore/www/portal/account.html`:

```html
{% extends "templates/web.html" %}
{% block title %}{{ _("Account") }}{% endblock %}
{% block page_content %}
<h1>{{ _("Account") }}</h1>
<p class="text-muted">{{ _("Customer") }}: {{ customer }} · <a href="/update-password">{{ _("Change password") }}</a></p>
<div class="row">
	<div class="col-md-6">
		<h4>{{ _("Profile") }}</h4>
		<form onsubmit="return false;">
			<div class="form-group"><label>{{ _("Full name") }}</label>
				<input class="form-control" id="profile-name" value="{{ user_doc.first_name }}"></div>
			<div class="form-group"><label>{{ _("Phone") }}</label>
				<input class="form-control" id="profile-phone" value="{{ user_doc.mobile_no or '' }}"></div>
			<button class="btn btn-primary" id="profile-save">{{ _("Save") }}</button>
		</form>
	</div>
	<div class="col-md-6">
		<h4>{{ _("Addresses") }}</h4>
		<ul class="list-group mb-3">
			{% for a in addresses %}
			<li class="list-group-item">{{ a.address_title }} — {{ a.address_line1 }}, {{ a.city }}, {{ a.country }}</li>
			{% else %}
			<li class="list-group-item text-muted">{{ _("No addresses yet.") }}</li>
			{% endfor %}
		</ul>
		<h6>{{ _("Add address") }}</h6>
		<form onsubmit="return false;">
			<div class="form-group"><input class="form-control" id="addr-title" placeholder="{{ _('Label (e.g. Head Office)') }}"></div>
			<div class="form-group"><input class="form-control" id="addr-line1" placeholder="{{ _('Street / building') }}"></div>
			<div class="form-row">
				<div class="col form-group"><input class="form-control" id="addr-city" placeholder="{{ _('City') }}"></div>
				<div class="col form-group"><input class="form-control" id="addr-country" placeholder="{{ _('Country') }}" value="Kenya"></div>
			</div>
			<button class="btn btn-secondary" id="addr-add">{{ _("Add") }}</button>
		</form>
	</div>
</div>
<script>
document.getElementById("profile-save").addEventListener("click", async () => {
	try {
		const result = await window.webstore.call("upande_webstore.api.account.update_profile", {
			full_name: document.getElementById("profile-name").value,
			phone: document.getElementById("profile-phone").value,
		});
		window.webstore.toast(result.message);
	} catch (err) { window.webstore.toast(err.message, true); }
});
document.getElementById("addr-add").addEventListener("click", async () => {
	try {
		await window.webstore.call("upande_webstore.api.account.add_address", {
			address_title: document.getElementById("addr-title").value,
			address_line1: document.getElementById("addr-line1").value,
			city: document.getElementById("addr-city").value,
			country: document.getElementById("addr-country").value,
		});
		window.location.reload();
	} catch (err) { window.webstore.toast(err.message, true); }
});
</script>
{% endblock %}
```

In `upande_webstore/hooks.py` add:

```python
standard_portal_menu_items = [
	{"title": "Store", "route": "/store", "role": "Customer"},
	{"title": "Cart", "route": "/cart", "role": "Customer"},
	{"title": "Wishlist", "route": "/wishlist", "role": "Customer"},
	{"title": "My Dashboard", "route": "/portal", "role": "Customer"},
	{"title": "Quotations", "route": "/portal/quotations", "role": "Customer"},
	{"title": "Orders", "route": "/portal/orders", "role": "Customer"},
	{"title": "Invoices", "route": "/portal/invoices", "role": "Customer"},
	{"title": "Statement", "route": "/portal/statement", "role": "Customer"},
	{"title": "Support", "route": "/portal/support", "role": "Customer"},
	{"title": "Account", "route": "/portal/account", "role": "Customer"},
]
```

`README.md` — write these sections with real content (no placeholders): **What this is** (two paragraphs from the spec summary); **Requirements** (Frappe/ERPNext v16); **Install** (`bench get-app /home/austin/vscodeProjects/upande_webstore`, `bench --site <site> install-app upande_webstore`, `bench --site <site> migrate`); **Configure** (fill Webstore Settings: company, guest price list, warehouses, signup defaults, notification emails); **Publish products** (create Webstore Product per Item, tick Published); **Order flow** (cart → Quotation → sales team converts to Sales Order; accept/decline from portal); **Run tests** (`bench --site <site> run-tests --app upande_webstore`).

- [ ] **Step 4: Run test to verify it passes**

```bash
bench --site webstore.localhost run-tests --module upande_webstore.tests.test_account
```

Expected: `OK` (3 tests).

- [ ] **Step 5: Full app test run + page sweep**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost migrate && bench build --app upande_webstore
bench --site webstore.localhost run-tests --app upande_webstore
for route in store signup login cart wishlist portal portal/quotations portal/orders portal/invoices portal/statement portal/support portal/account; do
  printf "%-22s %s\n" "$route" "$(curl -s -o /dev/null -w "%{http_code}" -H "Host: webstore.localhost" "http://127.0.0.1:8000/$route")"
done
```

Expected: all tests `OK`; every route returns `200` (login-guarded routes 200 after redirect-to-login).

- [ ] **Step 6: Commit and push**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
git add -A
git commit -m "feat: add account page, portal menu items and README

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

## Post-plan verification checklist (manual, by the human)

1. Log in to `webstore.localhost` desk as Administrator → fill **Webstore Settings**.
2. Create an Item + Webstore Product, publish, set an Item Price and stock.
3. Visit `/store` as guest → see product and guest price; sign up via `/signup`.
4. Add to cart, checkout → confirm Quotation appears in desk and in `/portal/quotations`.
5. Accept the quotation from the portal → confirm the sales team email and portal status.
6. Create a Sales Invoice for the customer in desk → confirm it appears in `/portal/invoices` with a working PDF download, and in `/portal/statement`.





