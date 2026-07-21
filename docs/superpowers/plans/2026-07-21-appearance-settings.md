# Appearance Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the storefront's images (logo, hero, 3 category cards) and brand color editable from the Webstore Settings doctype, with shipped assets as fallbacks.

**Architecture:** New optional fields on the `Webstore Settings` single DocType (Appearance tab). A `get_appearance()` service reads them via the existing cached doc and derives hover/soft/ring color variants from one primary color. An `update_website_context` hook exposes the dict to all website templates; `webstore_base.html` injects `--ws-*` CSS variable overrides and templates fall back to current asset paths.

**Tech Stack:** Frappe v16 (DocType JSON, Jinja website templates, `update_website_context` hook), Python, `frappe.tests.IntegrationTestCase`.

## Global Constraints

- Dev repo: `/home/austin/vscodeProjects/upande_webstore` (commit here). Bench copy: `~/frappe-v16-bench/apps/upande_webstore` (pulls from the dev repo; tests/migrate run in the bench).
- Site for tests/verification: `webstore.localhost`; bench root `~/frappe-v16-bench`.
- All appearance fields are optional; blank/invalid values must fall back to shipped defaults (`/assets/upande_webstore/images/...`, SCSS `--ws-*` values in `public/scss/webstore.bundle.scss:42-66`).
- Only `primary`, `primary_hover`, `primary_soft`, `ring` CSS variables are overridden. No other palette tokens.
- Python indentation in this repo is TABS (see `.editorconfig`/ruff config: `indent-style = "tab"`); templates also use tabs.
- Sync pattern after every local commit: `git -C ~/frappe-v16-bench/apps/upande_webstore pull`.

---

### Task 1: Appearance fields on Webstore Settings DocType

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`

**Interfaces:**
- Produces: DocType fields `brand_logo`, `hero_image`, `flowers_category_image`, `coffee_category_image`, `produce_category_image` (all Attach Image) and `primary_color` (Color) on single doctype "Webstore Settings". Task 2's service reads exactly these fieldnames.

- [ ] **Step 1: Add fields to the DocType JSON**

Replace the `field_order` line and the `fields` array in `webstore_settings.json` so the file becomes:

```json
{
 "doctype": "DocType",
 "name": "Webstore Settings",
 "module": "Upande Webstore",
 "issingle": 1,
 "engine": "InnoDB",
 "creation": "2026-07-20 00:00:01.000000",
 "modified": "2026-07-21 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["company", "guest_price_list", "default_customer_group", "default_territory", "quotation_validity_days", "stock_display", "notification_emails", "warehouses", "appearance_tab", "brand_logo", "hero_image", "category_images_section", "flowers_category_image", "coffee_category_image", "produce_category_image", "brand_colors_section", "primary_color"],
 "fields": [
  {"fieldname": "company", "fieldtype": "Link", "label": "Company", "options": "Company", "reqd": 1},
  {"fieldname": "guest_price_list", "fieldtype": "Link", "label": "Guest Price List", "options": "Price List", "reqd": 1},
  {"fieldname": "default_customer_group", "fieldtype": "Link", "label": "Default Customer Group (Signups)", "options": "Customer Group"},
  {"fieldname": "default_territory", "fieldtype": "Link", "label": "Default Territory (Signups)", "options": "Territory"},
  {"fieldname": "quotation_validity_days", "fieldtype": "Int", "label": "Quotation Validity (Days)", "default": "14"},
  {"fieldname": "stock_display", "fieldtype": "Select", "label": "Stock Display", "options": "In/Out Badge\nExact Quantity", "default": "In/Out Badge"},
  {"fieldname": "notification_emails", "fieldtype": "Small Text", "label": "Sales Notification Emails (comma-separated)"},
  {"fieldname": "warehouses", "fieldtype": "Table", "label": "Stock Warehouses", "options": "Webstore Warehouse"},
  {"fieldname": "appearance_tab", "fieldtype": "Tab Break", "label": "Appearance"},
  {"fieldname": "brand_logo", "fieldtype": "Attach Image", "label": "Brand Logo", "description": "Navbar logo. Blank = shipped Upande logo."},
  {"fieldname": "hero_image", "fieldtype": "Attach Image", "label": "Hero Image", "description": "Storefront hero photo. Blank = shipped default."},
  {"fieldname": "category_images_section", "fieldtype": "Section Break", "label": "Category Card Images"},
  {"fieldname": "flowers_category_image", "fieldtype": "Attach Image", "label": "Flowers Card Image"},
  {"fieldname": "coffee_category_image", "fieldtype": "Attach Image", "label": "Coffee Card Image"},
  {"fieldname": "produce_category_image", "fieldtype": "Attach Image", "label": "Fresh Produce Card Image"},
  {"fieldname": "brand_colors_section", "fieldtype": "Section Break", "label": "Brand Colors"},
  {"fieldname": "primary_color", "fieldtype": "Color", "label": "Primary Color", "description": "Buttons, links and accents. Hover and tint shades are derived automatically. Blank = shipped green."}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

- [ ] **Step 2: Commit locally, pull into bench, migrate**

```bash
cd /home/austin/vscodeProjects/upande_webstore
git add upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json
git commit -m "feat: add appearance fields to Webstore Settings"
git -C ~/frappe-v16-bench/apps/upande_webstore pull
cd ~/frappe-v16-bench && bench --site webstore.localhost migrate
```

Expected: migrate completes without error.

- [ ] **Step 3: Verify fields exist**

```bash
cd ~/frappe-v16-bench && bench --site webstore.localhost console <<'EOF'
doc = frappe.get_doc("Webstore Settings")
print([f for f in ("brand_logo","hero_image","flowers_category_image","coffee_category_image","produce_category_image","primary_color") if doc.meta.has_field(f)])
EOF
```

Expected: prints all six fieldnames.

---

### Task 2: `get_appearance()` service with color derivation

**Files:**
- Modify: `upande_webstore/services/settings.py`
- Modify: `upande_webstore/tests/utils.py` (reset appearance fields in `setup_webstore_settings`)
- Test: `upande_webstore/tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1's fieldnames on "Webstore Settings"; existing `get_settings()` in the same module.
- Produces:
  - `derive_brand_colors(primary: str | None) -> dict` — `{}` for blank/invalid input; else keys `primary`, `primary_hover`, `primary_soft` (hex strings) and `ring` (`rgba(r, g, b, 0.35)` string).
  - `get_appearance() -> dict` — keys `brand_logo`, `hero_image`, `flowers_category_image`, `coffee_category_image`, `produce_category_image` (str or None) and `colors` (the `derive_brand_colors` dict).
  - `update_website_context(context) -> None` — sets `context.webstore_appearance = get_appearance()`. Task 3's hook and templates use these exact names.

- [ ] **Step 1: Make `setup_webstore_settings` reset appearance fields**

In `upande_webstore/tests/utils.py`, inside `setup_webstore_settings()`, after `settings.stock_display = "In/Out Badge"` add:

```python
	for field in (
		"brand_logo",
		"hero_image",
		"flowers_category_image",
		"coffee_category_image",
		"produce_category_image",
		"primary_color",
	):
		settings.set(field, "")
```

- [ ] **Step 2: Write the failing tests**

Append to `upande_webstore/tests/test_settings.py`:

```python
class TestAppearance(IntegrationTestCase):
	def test_derive_brand_colors(self):
		from upande_webstore.services.settings import derive_brand_colors

		colors = derive_brand_colors("#166534")
		self.assertEqual(colors["primary"], "#166534")
		self.assertEqual(colors["primary_hover"], "#13592e")
		self.assertEqual(colors["primary_soft"], "#ecf3ef")
		self.assertEqual(colors["ring"], "rgba(22, 101, 52, 0.35)")

	def test_derive_brand_colors_rejects_invalid(self):
		from upande_webstore.services.settings import derive_brand_colors

		for bad in (None, "", "#1f0", "green", "#16653g"):
			self.assertEqual(derive_brand_colors(bad), {})

	def test_get_appearance_defaults(self):
		setup_webstore_settings()
		from upande_webstore.services.settings import get_appearance

		appearance = get_appearance()
		self.assertIsNone(appearance["hero_image"])
		self.assertIsNone(appearance["brand_logo"])
		self.assertEqual(appearance["colors"], {})

	def test_get_appearance_with_values(self):
		settings = setup_webstore_settings()
		settings.hero_image = "/files/custom-hero.jpg"
		settings.primary_color = "#1e3a64"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		from upande_webstore.services.settings import get_appearance

		appearance = get_appearance()
		self.assertEqual(appearance["hero_image"], "/files/custom-hero.jpg")
		self.assertEqual(appearance["colors"]["primary"], "#1e3a64")
		self.assertIn("primary_hover", appearance["colors"])

	def test_update_website_context(self):
		setup_webstore_settings()
		from upande_webstore.services.settings import update_website_context

		context = frappe._dict()
		update_website_context(context)
		self.assertIn("colors", context.webstore_appearance)
```

- [ ] **Step 3: Run tests to verify they fail**

Tests run against the bench copy; copy the edited files there without committing:

```bash
cp /home/austin/vscodeProjects/upande_webstore/upande_webstore/tests/test_settings.py ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/tests/test_settings.py
cp /home/austin/vscodeProjects/upande_webstore/upande_webstore/tests/utils.py ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/tests/utils.py
cd ~/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_settings
```

Expected: FAIL — `ImportError: cannot import name 'derive_brand_colors'`.

- [ ] **Step 4: Implement the service**

Append to `upande_webstore/services/settings.py` (keep existing `get_settings`/`get_warehouses`):

```python
APPEARANCE_IMAGE_FIELDS = (
	"brand_logo",
	"hero_image",
	"flowers_category_image",
	"coffee_category_image",
	"produce_category_image",
)


def _parse_hex(value):
	"""'#rrggbb' -> (r, g, b), else None. Shorthand/invalid values are rejected."""
	if not isinstance(value, str):
		return None
	value = value.strip()
	if len(value) != 7 or not value.startswith("#"):
		return None
	try:
		return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
	except ValueError:
		return None


def _mix(rgb, target, amount):
	return tuple(round(channel + (t - channel) * amount) for channel, t in zip(rgb, target))


def _to_hex(rgb):
	return "#%02x%02x%02x" % rgb


def derive_brand_colors(primary):
	rgb = _parse_hex(primary)
	if not rgb:
		return {}
	return {
		"primary": _to_hex(rgb),
		"primary_hover": _to_hex(_mix(rgb, (0, 0, 0), 0.12)),
		"primary_soft": _to_hex(_mix(rgb, (255, 255, 255), 0.92)),
		"ring": "rgba({}, {}, {}, 0.35)".format(*rgb),
	}


def get_appearance():
	settings = get_settings()
	appearance = {field: settings.get(field) or None for field in APPEARANCE_IMAGE_FIELDS}
	appearance["colors"] = derive_brand_colors(settings.get("primary_color"))
	return appearance


def update_website_context(context):
	context.webstore_appearance = get_appearance()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cp /home/austin/vscodeProjects/upande_webstore/upande_webstore/services/settings.py ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/services/settings.py
cd ~/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_settings
```

Expected: PASS (6 tests: 1 existing + 5 new).

- [ ] **Step 6: Commit and sync**

```bash
cd /home/austin/vscodeProjects/upande_webstore
git add upande_webstore/services/settings.py upande_webstore/tests/test_settings.py upande_webstore/tests/utils.py
git commit -m "feat: appearance service with derived brand colors"
git -C ~/frappe-v16-bench/apps/upande_webstore checkout -- . && git -C ~/frappe-v16-bench/apps/upande_webstore pull
```

---

### Task 3: Hook registration and template wiring

**Files:**
- Modify: `upande_webstore/hooks.py`
- Modify: `upande_webstore/templates/webstore_base.html:1-9`
- Modify: `upande_webstore/www/store.html:37,66,73,80`

**Interfaces:**
- Consumes: `upande_webstore.services.settings.update_website_context` (Task 2); template variable `webstore_appearance` with keys `brand_logo`, `hero_image`, `flowers_category_image`, `coffee_category_image`, `produce_category_image`, `colors.{primary,primary_hover,primary_soft,ring}`.
- Produces: user-visible behavior; nothing consumed downstream.

- [ ] **Step 1: Register the hook**

In `upande_webstore/hooks.py`, directly after the line `web_include_js = "webstore.bundle.ts"`, add:

```python

# inject webstore appearance (images, brand colors) into every website page context
update_website_context = ["upande_webstore.services.settings.update_website_context"]
```

- [ ] **Step 2: Inject CSS variable overrides and configurable logo in the base template**

In `upande_webstore/templates/webstore_base.html`, after line 1 (`{% extends "templates/web.html" %}`) insert:

```jinja
{% block style %}
{{ super() }}
{%- if webstore_appearance and webstore_appearance.colors %}
<style>
	:root {
		--ws-primary: {{ webstore_appearance.colors.primary }};
		--ws-primary-hover: {{ webstore_appearance.colors.primary_hover }};
		--ws-primary-soft: {{ webstore_appearance.colors.primary_soft }};
		--ws-ring: {{ webstore_appearance.colors.ring }};
	}
</style>
{%- endif %}
{% endblock %}
```

Then change the navbar logo line

```jinja
			<img src="/assets/upande_webstore/images/upande-logo.png" alt="Upande">
```

to

```jinja
			<img src="{{ webstore_appearance.brand_logo or '/assets/upande_webstore/images/upande-logo.png' }}" alt="Upande">
```

- [ ] **Step 3: Configurable hero and category images in store.html**

In `upande_webstore/www/store.html` replace the four hardcoded `<img src=...>` values:

Line 37:
```jinja
	<div class="ws-hero2-bg"><img src="{{ webstore_appearance.hero_image or '/assets/upande_webstore/images/site/hero.jpg' }}" alt=""></div>
```

Line 66 (Flowers card):
```jinja
					<img src="{{ webstore_appearance.flowers_category_image or '/assets/upande_webstore/images/site/cat-flowers.jpg' }}" alt="{{ _('Flowers') }}" loading="lazy">
```

Line 73 (Coffee card):
```jinja
					<img src="{{ webstore_appearance.coffee_category_image or '/assets/upande_webstore/images/site/cat-coffee.jpg' }}" alt="{{ _('Coffee') }}" loading="lazy">
```

Line 80 (Fresh Produce card):
```jinja
					<img src="{{ webstore_appearance.produce_category_image or '/assets/upande_webstore/images/site/cat-produce.jpg' }}" alt="{{ _('Fresh Produce') }}" loading="lazy">
```

- [ ] **Step 4: Commit, sync, clear cache**

```bash
cd /home/austin/vscodeProjects/upande_webstore
git add upande_webstore/hooks.py upande_webstore/templates/webstore_base.html upande_webstore/www/store.html
git commit -m "feat: wire appearance settings into storefront templates"
git -C ~/frappe-v16-bench/apps/upande_webstore pull
cd ~/frappe-v16-bench && bench --site webstore.localhost clear-website-cache && bench restart 2>/dev/null || true
```

Note: `bench restart` only applies under supervisor; with `bench start` the dev server reloads hooks.py automatically. If the hook doesn't take effect, restart the `bench start` process.

- [ ] **Step 5: End-to-end verify — defaults unchanged**

```bash
curl -s -H 'Host: webstore.localhost' http://127.0.0.1:8003/store | grep -c 'images/site/hero.jpg'
```

Expected: `1` (fallback still used; no `--ws-primary` inline override present:
`curl -s -H 'Host: webstore.localhost' http://127.0.0.1:8003/store | grep -c 'ws-primary:'` prints `0`).

- [ ] **Step 6: End-to-end verify — overrides apply**

```bash
cd ~/frappe-v16-bench && bench --site webstore.localhost console <<'EOF'
doc = frappe.get_doc("Webstore Settings")
doc.primary_color = "#1e3a64"
doc.hero_image = "/files/test-hero.jpg"
doc.save()
frappe.db.commit()
EOF
bench --site webstore.localhost clear-website-cache
curl -s -H 'Host: webstore.localhost' http://127.0.0.1:8003/store | grep -oE -- '--ws-primary: #1e3a64|/files/test-hero.jpg'
```

Expected: both strings printed.

- [ ] **Step 7: Revert the test overrides**

```bash
cd ~/frappe-v16-bench && bench --site webstore.localhost console <<'EOF'
doc = frappe.get_doc("Webstore Settings")
doc.primary_color = ""
doc.hero_image = ""
doc.save()
frappe.db.commit()
EOF
bench --site webstore.localhost clear-website-cache
```

Expected: `/store` renders with shipped defaults again.
