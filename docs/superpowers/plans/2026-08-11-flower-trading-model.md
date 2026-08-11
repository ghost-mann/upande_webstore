# Flower Trading Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the storefront sell stems against box types with pack rates, enforce a minimum order, and stop the requested shipping date being lost between quotation and sales order.

**Architecture:** A new pure-function module `services/packing.py` does all box arithmetic and knows nothing about documents. `api/cart.py` recomputes box counts on every mutation (mirroring how `_reprice` re-resolves rates) and `api/checkout.py` calls one assert before building the document. A `before_insert` hook on Sales Order carries webstore fields across ERPNext's quotation → sales order mapper, which drops custom fields. Box types are read from existing Items flagged `custom_is_box`; no new doctypes.

**Tech Stack:** Frappe v16 / ERPNext v16, Python 3, `frappe.tests.IntegrationTestCase`, hand-written doctype JSON, server-rendered Jinja templates with vanilla JS.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-11-flower-trading-model-design.md`. Read it before starting.
- **No new doctypes.** Box type already has four representations in the wild; do not add a fifth.
- **No dependency on `upande_harvest` or `upande_webshop`.** The app must work on a farm that has neither. Every read of `custom_is_box` / `custom_pack_rate` / `custom_delivery_point` must first check the field exists via `frappe.get_meta(...).get_field(...)`, because on a bare site those columns are absent and `frappe.get_all` would raise.
- **Never claim the names `Box Type` or `Delivery Point`** for a doctype. Other apps own them.
- **Inert by default.** `enable_box_packing` ships as `0`. With the flag off, or with every pack rate `0`, cart and checkout must behave exactly as they do today. This is what makes the feature deployable to Mona live, where all seven box Items have `custom_pack_rate = 0`.
- **Derive server-side.** `number_of_boxes` is computed on save and never read from the client, exactly like `rate` and `amount`.
- **Naming exception:** fields written onto Quotation Item / Sales Order Item / Sales Order use the `custom_` prefix, not this app's usual `webstore_` prefix, because ops already reads those exact names. Do not rename them.
- **Never write** `Quotation.custom_box_type` (links to an empty `Box Type` doctype) or the order-level `Sales Order.custom_box_type` (box type is per line here).
- **Test command**, run from the bench directory (`frappe-v16-bench`), site `webstore.localhost`:
  ```bash
  bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing
  ```
  Redis must be running on the ports in `common_site_config.json` first. Whole-suite run: drop `--module`.
- **Currency/units:** all quantities are stems (Float on documents, but always whole numbers in practice). Pack rates are whole numbers; treat as `int`.

---

### Task 1: Settings fields and deterministic test resets

Four settings fields, plus resets in the shared test helper so a test that switches packing on cannot leak into the next module. `setup_webstore_settings` already does exactly this for theme seeds and feature flags — follow that pattern.

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/tests/utils.py`
- Test: `upande_webstore/tests/test_packing.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: settings fields `enable_box_packing` (Check, default `"0"`), `default_box_type` (Link → Item), `minimum_order_stems` (Int, default `"0"`), `default_lead_days` (Int, default `"7"`). After this task `setup_webstore_settings()` resets all four.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_packing.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestPackingSettings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def test_packing_fields_exist_with_inert_defaults(self):
		meta = frappe.get_meta("Webstore Settings")
		self.assertEqual(meta.get_field("enable_box_packing").default, "0")
		self.assertEqual(meta.get_field("minimum_order_stems").default, "0")
		self.assertEqual(meta.get_field("default_lead_days").default, "7")
		self.assertEqual(meta.get_field("default_box_type").options, "Item")

	def test_setup_helper_resets_packing_config(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_box_packing = 1
		settings.minimum_order_stems = 5000
		settings.save(ignore_permissions=True)
		setup_webstore_settings()
		settings = frappe.get_doc("Webstore Settings")
		self.assertFalse(int(settings.enable_box_packing or 0))
		self.assertEqual(int(settings.minimum_order_stems or 0), 0)
		self.assertEqual(int(settings.default_lead_days or 0), 7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'default'`, because `enable_box_packing` does not exist yet.

- [ ] **Step 3: Add the settings fields**

In `webstore_settings.json`, add these four entries to the `fields` array:

```json
  {"fieldname": "packing_section", "fieldtype": "Section Break", "label": "Boxes & Order Rules"},
  {"fieldname": "enable_box_packing", "fieldtype": "Check", "label": "Box Packing Rules", "default": "0", "description": "Off = no box maths and no order minimum. Turn on only after pack rates are entered on your box Items."},
  {"fieldname": "default_box_type", "fieldtype": "Link", "label": "Default Box Type", "options": "Item", "description": "Seeds each new cart line. Must be an Item flagged Is Box with a pack rate."},
  {"fieldname": "minimum_order_stems", "fieldtype": "Int", "label": "Minimum Order (Stems)", "default": "0", "description": "0 = no minimum. Checked against the whole cart, not per line."},
  {"fieldname": "default_lead_days", "fieldtype": "Int", "label": "Delivery Lead Time (Days)", "default": "7", "description": "Earliest shipping date a buyer may request, and the fallback when none is given."},
```

And insert the five fieldnames into `field_order` immediately after `"warehouses"`:

```json
  "warehouses",
  "packing_section",
  "enable_box_packing",
  "default_box_type",
  "minimum_order_stems",
  "default_lead_days",
  "theme_tab",
```

- [ ] **Step 4: Reset the new fields in the test helper**

In `upande_webstore/tests/utils.py`, inside `setup_webstore_settings()`, add immediately after the `settings.quotation_validity_days = 14` line:

```python
	# Packing config is not in the FEATURES registry, so the feature-flag loop
	# below does not cover it. Reset explicitly or a module that enables box
	# packing breaks whichever module runs next.
	settings.enable_box_packing = 0
	settings.default_box_type = ""
	settings.minimum_order_stems = 0
	settings.default_lead_days = 7
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json \
        upande_webstore/tests/utils.py upande_webstore/tests/test_packing.py
git commit -m "feat(packing): box packing settings, off by default"
```

---

### Task 2: `services/packing.py` — box arithmetic

All the maths, none of the documents. `compute_boxes` is pure; the readers are thin and guard against absent custom fields.

**Files:**
- Create: `upande_webstore/services/packing.py`
- Test: `upande_webstore/tests/test_packing.py` (extend)

**Interfaces:**
- Consumes: settings fields from Task 1.
- Produces:
  - `packing_enabled() -> bool`
  - `get_default_box_type() -> str | None`
  - `get_minimum_order_stems() -> int`
  - `get_box_types() -> list[dict]` with keys `item_code`, `item_name`, `pack_rate`
  - `get_pack_rate(box_item) -> int` — `0` when unusable
  - `is_usable_box(box_item) -> bool`
  - `box_label(box_item) -> str`
  - `compute_boxes(qty, pack_rate) -> dict` with keys `pack_rate`, `boxes`, `remainder`, `is_full`, `nearest_down`, `nearest_up`
  - `group_by_box_type(lines) -> dict` keyed by box item code; `lines` is a list of dicts with `item_code`, `qty`, `box_type`
  - `find_problems(groups, total_stems, minimum_stems) -> list[str]`

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_packing.py`:

```python
class TestBoxMaths(IntegrationTestCase):
	def test_exact_multiple_is_full(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1800, 300)
		self.assertEqual(result["boxes"], 6)
		self.assertEqual(result["remainder"], 0)
		self.assertTrue(result["is_full"])

	def test_remainder_reports_both_neighbours(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1750, 300)
		self.assertEqual(result["boxes"], 5)
		self.assertEqual(result["remainder"], 250)
		self.assertFalse(result["is_full"])
		self.assertEqual(result["nearest_down"], 1500)
		self.assertEqual(result["nearest_up"], 1800)

	def test_below_one_box_has_no_round_down(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(50, 300)
		self.assertEqual(result["boxes"], 0)
		self.assertEqual(result["nearest_down"], 0)
		self.assertEqual(result["nearest_up"], 300)
		self.assertFalse(result["is_full"])

	def test_zero_pack_rate_never_blocks(self):
		"""Every pack rate on Mona live is 0. If that blocked, enabling the
		feature would take the storefront down."""
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1750, 0)
		self.assertTrue(result["is_full"])
		self.assertEqual(result["pack_rate"], 0)
		self.assertIsNone(result["nearest_up"])

	def test_zero_qty_is_full(self):
		from upande_webstore.services.packing import compute_boxes

		self.assertTrue(compute_boxes(0, 300)["is_full"])

	def test_grouping_sums_stems_across_lines(self):
		from upande_webstore.services.packing import group_by_box_type

		groups = group_by_box_type([
			{"item_code": "A", "qty": 50, "box_type": "ZIM"},
			{"item_code": "B", "qty": 250, "box_type": "ZIM"},
			{"item_code": "C", "qty": 500, "box_type": "JUMBO"},
		])
		self.assertEqual(groups["ZIM"]["stems"], 300)
		self.assertEqual(groups["JUMBO"]["stems"], 500)
		self.assertEqual(sorted(groups["ZIM"]["item_codes"]), ["A", "B"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.services.packing'`

- [ ] **Step 3: Write the implementation**

Create `upande_webstore/services/packing.py`:

```python
"""Box arithmetic for stem orders.

Pure maths plus a few thin reads. Deliberately knows nothing about carts or
documents, so the arithmetic can be tested without building either.

Box types are Items flagged `custom_is_box` carrying `custom_pack_rate` —
the same records `Pack Box.box_type` links to — rather than a doctype of our
own. Those are another app's custom fields, so every read guards on the field
actually existing: this app must work on a farm that has neither
upande_harvest nor upande_webshop installed.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_webstore.services.settings import get_settings

BOX_FLAG = "custom_is_box"
BOX_RATE = "custom_pack_rate"


def packing_enabled():
	return bool(int(get_settings().get("enable_box_packing") or 0))


def get_default_box_type():
	return get_settings().get("default_box_type") or None


def get_minimum_order_stems():
	return int(flt(get_settings().get("minimum_order_stems")))


def _item_has_box_fields():
	meta = frappe.get_meta("Item")
	return bool(meta.get_field(BOX_FLAG)) and bool(meta.get_field(BOX_RATE))


def get_box_types():
	"""Boxes the farm can actually pack into: flagged, enabled, rate above zero."""
	if not _item_has_box_fields():
		return []
	rows = frappe.get_all(
		"Item",
		filters={BOX_FLAG: 1, "disabled": 0},
		fields=["name as item_code", "item_name", f"{BOX_RATE} as pack_rate"],
		order_by="item_name asc",
	)
	return [
		{"item_code": r.item_code, "item_name": r.item_name, "pack_rate": int(flt(r.pack_rate))}
		for r in rows
		if flt(r.pack_rate) > 0
	]


def get_pack_rate(box_item):
	"""Stems per box, or 0 when the box is missing, disabled, no longer a box,
	or has no rate entered. 0 always means 'do not validate'."""
	if not box_item or not _item_has_box_fields():
		return 0
	row = frappe.db.get_value(
		"Item", box_item, [BOX_FLAG, BOX_RATE, "disabled"], as_dict=True
	)
	if not row or not int(flt(row.get(BOX_FLAG))) or int(flt(row.get("disabled"))):
		return 0
	rate = flt(row.get(BOX_RATE))
	return int(rate) if rate > 0 else 0


def is_usable_box(box_item):
	return get_pack_rate(box_item) > 0


def box_label(box_item):
	if not box_item:
		return _("no box type")
	return frappe.db.get_value("Item", box_item, "item_name") or box_item


def compute_boxes(qty, pack_rate):
	"""How a stem quantity divides into whole boxes.

	A pack_rate of 0 reports is_full=True on purpose: an unconfigured box must
	never block an order.
	"""
	qty = flt(qty)
	pack_rate = int(flt(pack_rate))
	if pack_rate <= 0:
		return {
			"pack_rate": 0,
			"boxes": 0,
			"remainder": 0,
			"is_full": True,
			"nearest_down": None,
			"nearest_up": None,
		}
	boxes = int(qty // pack_rate)
	remainder = qty - boxes * pack_rate
	return {
		"pack_rate": pack_rate,
		"boxes": boxes,
		"remainder": remainder,
		"is_full": remainder == 0,
		"nearest_down": boxes * pack_rate,
		"nearest_up": (boxes + 1) * pack_rate,
	}


def group_by_box_type(lines):
	"""Sum stems per box type.

	Boxes are mixed in practice — a 50-stem line shares a box with other
	varieties — so whole-box fill is a property of the group, not the line.

	lines: [{"item_code": str, "qty": float, "box_type": str | None}]
	"""
	groups = {}
	for line in lines:
		box_type = line.get("box_type") or None
		group = groups.setdefault(
			box_type, {"box_type": box_type, "stems": 0, "item_codes": []}
		)
		group["stems"] = flt(group["stems"]) + flt(line.get("qty"))
		group["item_codes"].append(line.get("item_code"))
	for group in groups.values():
		group.update(compute_boxes(group["stems"], get_pack_rate(group["box_type"])))
	return groups


def find_problems(groups, total_stems, minimum_stems):
	"""Human-readable reasons this cart cannot be ordered. Empty means it can.

	Both checks are collected rather than raised one at a time, so a buyer is
	never sent to fix the minimum only to be blocked again on box fill.
	"""
	problems = []
	for group in sorted(groups.values(), key=lambda g: (g["box_type"] or "")):
		if group["pack_rate"] <= 0 or group["is_full"]:
			continue
		label = box_label(group["box_type"])
		if group["boxes"] == 0:
			problems.append(
				_("{0}: {1} stems is less than one full box ({2} per box). Order at least {2}.").format(
					label, int(group["stems"]), group["pack_rate"]
				)
			)
		else:
			problems.append(
				_("{0}: {1} stems across {2} lines does not fill whole boxes ({3} per box). Use {4} ({5} boxes) or {6} ({7} boxes).").format(
					label,
					int(group["stems"]),
					len(group["item_codes"]),
					group["pack_rate"],
					int(group["nearest_down"]),
					group["boxes"],
					int(group["nearest_up"]),
					group["boxes"] + 1,
				)
			)
	if minimum_stems and flt(total_stems) < minimum_stems:
		problems.append(
			_("Minimum order is {0} stems; your cart has {1}.").format(
				minimum_stems, int(flt(total_stems))
			)
		)
	return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/services/packing.py upande_webstore/tests/test_packing.py
git commit -m "feat(packing): box arithmetic grouped by box type"
```

---

### Task 3: Cart carries a box type per line

Cart lines gain a box type and a derived box count, recomputed on every mutation next to `_reprice`. Two new endpoints let the buyer change a line's box and populate the dropdown.

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_cart_item/webstore_cart_item.json`
- Modify: `upande_webstore/api/cart.py`
- Test: `upande_webstore/tests/test_cart_boxes.py` (create)

**Interfaces:**
- Consumes: `services.packing` (all functions from Task 2).
- Produces:
  - `Webstore Cart Item.box_type` (Link → Item), `Webstore Cart Item.number_of_boxes` (Int, read-only)
  - `cart.add_item(item_code, qty=1, box_type=None)` — extra optional third argument
  - `cart.set_box_type(item_code, box_type)` — whitelisted, `@guard("cart")`
  - `cart.get_box_types()` — whitelisted, `@guard("cart")`, returns Task 2's `get_box_types()`
  - `cart._recompute_boxes(cart)` — internal
  - `serialize_cart` output gains a per-line `box` key and a top-level `boxes` key (`None` when packing is off, else `{groups, problems, packable, total_stems}`)

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_cart_boxes.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_item,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def make_box_item(item_code, pack_rate):
	item = make_test_item(item_code, item_group="Products", is_stock_item=0)
	frappe.db.set_value(
		"Item", item.name, {"custom_is_box": 1, "custom_pack_rate": pack_rate}
	)
	frappe.clear_cache(doctype="Item")
	return item.name


class TestCartBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-BOX-ITEM")
		make_item_price("WS-BOX-ITEM", "Standard Selling", 10)
		make_portal_user("box.buyer@example.com", "Box Buyer")
		cls.zim = make_box_item("WS-BOX-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "box.buyer@example.com"})
		set_stock("WS-BOX-ITEM", 5000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.clear_cache()
		frappe.set_user("box.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_new_line_is_seeded_with_the_default_box(self):
		from upande_webstore.api import cart

		result = cart.add_item("WS-BOX-ITEM", 600)
		self.assertEqual(result["items"][0]["box"]["box_type"], self.zim)
		self.assertEqual(result["items"][0]["box"]["number_of_boxes"], 2)

	def test_partial_line_reports_zero_boxes_but_no_problem_alone(self):
		"""A 50-stem line shares a box; the group total is what matters."""
		from upande_webstore.api import cart

		result = cart.add_item("WS-BOX-ITEM", 50)
		self.assertEqual(result["items"][0]["box"]["number_of_boxes"], 0)
		self.assertFalse(result["boxes"]["packable"])

	def test_group_of_two_lines_fills_whole_boxes(self):
		from upande_webstore.api import cart

		make_test_product("WS-BOX-ITEM-2")
		make_item_price("WS-BOX-ITEM-2", "Standard Selling", 10)
		frappe.set_user("Administrator")
		set_stock("WS-BOX-ITEM-2", 5000)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 50)
		result = cart.add_item("WS-BOX-ITEM-2", 250)
		self.assertEqual(result["boxes"]["total_stems"], 300)
		self.assertTrue(result["boxes"]["packable"])

	def test_packing_off_leaves_cart_untouched(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 1750)
		self.assertIsNone(result["boxes"])

	def test_zero_pack_rate_does_not_block(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		unrated = make_box_item("WS-BOX-NORATE", 0)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", unrated)
		frappe.clear_cache()
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 1750)
		self.assertTrue(result["boxes"]["packable"])

	def test_set_box_type_regroups(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-BOX-JUMBO", 500)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 500)
		result = cart.set_box_type("WS-BOX-ITEM", jumbo)
		self.assertEqual(result["items"][0]["box"]["box_type"], jumbo)
		self.assertTrue(result["boxes"]["packable"])

	def test_disabled_box_falls_back_to_the_default(self):
		"""A farm disabling a box Item must not brick carts already holding it."""
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		retired = make_box_item("WS-BOX-RETIRED", 400)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 600, box_type=retired)
		frappe.set_user("Administrator")
		frappe.db.set_value("Item", retired, "disabled", 1)
		frappe.clear_cache(doctype="Item")
		frappe.set_user("box.buyer@example.com")
		result = cart.get_cart()
		self.assertEqual(result["items"][0]["box"]["box_type"], self.zim)
		self.assertEqual(result["items"][0]["box"]["number_of_boxes"], 2)

	def test_get_box_types_excludes_unrated_boxes(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		make_box_item("WS-BOX-HIDDEN", 0)
		frappe.set_user("box.buyer@example.com")
		codes = [row["item_code"] for row in cart.get_box_types()]
		self.assertIn(self.zim, codes)
		self.assertNotIn("WS-BOX-HIDDEN", codes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_cart_boxes`
Expected: FAIL — `KeyError: 'box'`, and `AttributeError: module 'upande_webstore.api.cart' has no attribute 'set_box_type'`

- [ ] **Step 3: Add the cart item fields**

In `webstore_cart_item.json`, set `field_order` to:

```json
 "field_order": ["item_code", "item_name", "qty", "box_type", "number_of_boxes", "rate", "amount"],
```

and add these two entries to `fields`, after the `qty` entry:

```json
  {"fieldname": "box_type", "fieldtype": "Link", "label": "Box Type", "options": "Item", "in_list_view": 1},
  {"fieldname": "number_of_boxes", "fieldtype": "Int", "label": "Boxes", "read_only": 1},
```

- [ ] **Step 4: Wire the cart**

In `upande_webstore/api/cart.py`, add after `_reprice`:

```python
def _recompute_boxes(cart):
	"""Derive each line's box count, exactly as _reprice re-resolves rates:
	the client never supplies either."""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return
	default_box = packing.get_default_box_type()
	for row in cart.items:
		# a box that was disabled or had its rate cleared falls back to the default
		if row.box_type and not packing.is_usable_box(row.box_type):
			row.box_type = None
		if not row.box_type:
			row.box_type = default_box or None
		info = packing.compute_boxes(row.qty, packing.get_pack_rate(row.box_type))
		row.number_of_boxes = info["boxes"] if info["pack_rate"] and info["is_full"] else 0


def _box_view(cart):
	"""Group summary for the cart page, or None when packing is off."""
	from upande_webstore.services import packing

	if not cart or not packing.packing_enabled():
		return None
	lines = [
		{"item_code": row.item_code, "qty": row.qty, "box_type": row.box_type}
		for row in cart.items
	]
	groups = packing.group_by_box_type(lines)
	total_stems = sum(frappe.utils.flt(row.qty) for row in cart.items)
	problems = packing.find_problems(
		groups, total_stems, packing.get_minimum_order_stems()
	)
	return {
		"groups": [
			{
				"box_type": group["box_type"],
				"box_name": packing.box_label(group["box_type"]),
				"pack_rate": group["pack_rate"],
				"stems": group["stems"],
				"boxes": group["boxes"],
				"is_full": group["is_full"],
				"nearest_down": group["nearest_down"],
				"nearest_up": group["nearest_up"],
			}
			for group in sorted(groups.values(), key=lambda g: (g["box_type"] or ""))
		],
		"problems": problems,
		"packable": not problems,
		"total_stems": total_stems,
	}
```

In `serialize_cart`, add `"box"` to each item dict and `"boxes"` to the returned dict. Replace the `return {` block with:

```python
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
				"box": {
					"box_type": row.get("box_type"),
					"number_of_boxes": row.get("number_of_boxes") or 0,
				},
			}
			for row in cart.items
		],
		"total": cart.total,
		"currency": frappe.db.get_value("Price List", get_price_list(), "currency"),
		"count": int(sum(row.qty for row in cart.items)),
		"boxes": _box_view(cart),
	}
```

Then call `_recompute_boxes(cart)` immediately after each existing `_reprice(cart)` call inside `get_cart`, `add_item`, `update_qty` and `remove_item`, and give `add_item` the new argument. `add_item`'s signature and its append become:

```python
def add_item(item_code, qty=1, box_type=None):
```

```python
	if existing:
		existing.qty = new_qty
		if box_type:
			existing.box_type = box_type
	else:
		cart.append("items", {"item_code": item_code, "qty": qty, "box_type": box_type or None})
```

Add the two new endpoints at the end of the file:

```python
@frappe.whitelist()
@guard("cart")
def get_box_types():
	from upande_webstore.services.packing import get_box_types as _box_types

	return _box_types()


@frappe.whitelist()
@guard("cart")
def set_box_type(item_code, box_type):
	from upande_webstore.services import packing

	_require_login()
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = next((r for r in cart.items if r.item_code == item_code), None)
	if not row:
		frappe.throw(_("Item not in cart."), frappe.ValidationError)
	if box_type and not packing.is_usable_box(box_type):
		frappe.throw(_("That box type is not available."), frappe.ValidationError)
	row.box_type = box_type or None
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_cart_boxes`
Expected: PASS (8 tests)

- [ ] **Step 6: Check nothing else broke**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_cart`
Expected: PASS — packing is off in those tests, so `boxes` is `None` and behaviour is unchanged.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_cart_item/webstore_cart_item.json \
        upande_webstore/api/cart.py upande_webstore/tests/test_cart_boxes.py
git commit -m "feat(cart): per-line box type with derived box count"
```

---

### Task 4: Checkout blocks unpackable carts

One assert beside the existing availability check.

**Files:**
- Modify: `upande_webstore/api/checkout.py`
- Test: `upande_webstore/tests/test_checkout_boxes.py` (create)

**Interfaces:**
- Consumes: `services.packing`, `cart._box_view` semantics from Task 3.
- Produces: `checkout._assert_packable(cart)` — raises `frappe.ValidationError` listing every problem, or returns `None`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_checkout_boxes.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_cart_boxes import make_box_item
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCheckoutBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CB-ITEM")
		make_item_price("WS-CB-ITEM", "Standard Selling", 10)
		make_portal_user("cb.buyer@example.com", "CB Buyer")
		cls.zim = make_box_item("WS-CB-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "cb.buyer@example.com"})
		set_stock("WS-CB-ITEM", 20000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 1000)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_partial_group_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1750)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1500", str(caught.exception))
		self.assertIn("1800", str(caught.exception))

	def test_below_minimum_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 600)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1000", str(caught.exception))

	def test_both_problems_reported_together(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 550)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		message = str(caught.exception)
		self.assertIn("whole boxes", message)
		self.assertIn("Minimum order", message)

	def test_whole_boxes_above_minimum_passes(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1200)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_packing_disabled(self):
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_pack_rate_is_zero(self):
		"""Mona live's state today: seven box Items, every rate 0."""
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		unrated = make_box_item("WS-CB-NORATE", 0)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", unrated)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: FAIL — no exception raised; `place_order` currently accepts 1750 stems.

- [ ] **Step 3: Write the implementation**

In `upande_webstore/api/checkout.py`, add after `_assert_available`:

```python
def _assert_packable(cart):
	"""Whole-box fill and the order minimum. Inert unless the farm has switched
	packing on AND entered pack rates, so this cannot break a site that has
	neither."""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return
	lines = [
		{"item_code": row.item_code, "qty": row.qty, "box_type": row.box_type}
		for row in cart.items
	]
	groups = packing.group_by_box_type(lines)
	total_stems = sum(flt(row.qty) for row in cart.items)
	problems = packing.find_problems(
		groups, total_stems, packing.get_minimum_order_stems()
	)
	if problems:
		frappe.throw("<br>".join(problems), frappe.ValidationError)
```

Then call it in `place_order` immediately after the existing `_assert_available(cart)` line:

```python
	_assert_available(cart)
	_assert_packable(cart)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/api/checkout.py upande_webstore/tests/test_checkout_boxes.py
git commit -m "feat(checkout): block partial boxes and sub-minimum orders"
```

---

### Task 5: Write box fields onto the documents

Quotation Item needs three custom fields created; Sales Order Item already has them on live but must be ensured for farms that do not.

**Files:**
- Modify: `upande_webstore/setup/install.py`
- Modify: `upande_webstore/api/checkout.py`
- Test: `upande_webstore/tests/test_checkout_boxes.py` (extend)

**Interfaces:**
- Consumes: `services.packing`, `_cart_items` from `checkout.py`.
- Produces: custom fields `custom_box_type`, `custom_pack_rate`, `custom_number_of_boxes` on both Quotation Item and Sales Order Item; `Sales Order.custom_has_mixed_boxes`. `_cart_items(cart)` gains those three keys per row when packing is enabled.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_checkout_boxes.py`:

```python
class TestBoxFieldMapping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-MAP-A")
		make_test_product("WS-MAP-B")
		make_item_price("WS-MAP-A", "Standard Selling", 10)
		make_item_price("WS-MAP-B", "Standard Selling", 10)
		make_portal_user("map.buyer@example.com", "Map Buyer")
		cls.zim = make_box_item("WS-MAP-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "map.buyer@example.com"})
		set_stock("WS-MAP-A", 20000)
		set_stock("WS-MAP-B", 20000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.clear_cache()
		frappe.set_user("map.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_item_carries_box_fields(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		result = checkout.place_order()
		row = frappe.get_doc("Quotation", result["quotation"]).items[0]
		self.assertEqual(row.custom_box_type, self.zim)
		self.assertEqual(int(row.custom_pack_rate), 300)
		self.assertEqual(row.custom_number_of_boxes, 2)

	def test_partial_line_records_zero_boxes(self):
		"""A line inside a mixed box has no whole-box count of its own."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order()
		rows = frappe.get_doc("Quotation", result["quotation"]).items
		self.assertEqual([r.custom_number_of_boxes for r in rows], [0, 0])

	def test_sales_order_flags_mixed_boxes(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes), 1)

	def test_single_line_group_is_not_mixed(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 300)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes or 0), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: FAIL — `AttributeError: 'QuotationItem' object has no attribute 'custom_box_type'`

- [ ] **Step 3: Ensure the custom fields exist**

In `upande_webstore/setup/install.py`, add these three keys to `WEBSTORE_CUSTOM_FIELDS`. Note the `custom_` prefix is deliberate — ops already reads these exact names, and `create_custom_fields` skips any that already exist:

```python
	# Deliberately `custom_`-prefixed rather than `webstore_`: these are the
	# field names the packing floor already reads on live, and sharing them is
	# the whole point of sourcing box types from Items.
	"Quotation Item": [
		{
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"options": "Item",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	"Sales Order Item": [
		{
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"options": "Item",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	"Sales Order": [
		# NOTE: this key already exists in the dict — append these two entries to
		# the existing list rather than adding a second "Sales Order" key.
		{
			"fieldname": "custom_has_mixed_boxes",
			"fieldtype": "Check",
			"label": "Mixed Box Grading",
			"insert_after": "webstore_dropoff_points",
			"default": "0",
		},
	],
```

- [ ] **Step 4: Populate the fields at checkout**

In `upande_webstore/api/checkout.py`, replace `_cart_items` with:

```python
def _cart_items(cart):
	from upande_webstore.services import packing

	include_boxes = packing.packing_enabled()
	rows = []
	for row in cart.items:
		line = {
			"item_code": row.item_code,
			"qty": row.qty,
			"rate": get_item_price(row.item_code, qty=row.qty)["rate"],
		}
		if include_boxes and row.box_type:
			line["custom_box_type"] = row.box_type
			line["custom_pack_rate"] = packing.get_pack_rate(row.box_type)
			line["custom_number_of_boxes"] = row.number_of_boxes or 0
		rows.append(line)
	return rows


def _has_mixed_boxes(cart):
	"""True when any box type carries more than one line, which is what tells
	the desk this order needs mixed-box handling."""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return 0
	lines = [
		{"item_code": row.item_code, "qty": row.qty, "box_type": row.box_type}
		for row in cart.items
	]
	groups = packing.group_by_box_type(lines)
	return int(any(len(g["item_codes"]) > 1 for g in groups.values()))
```

In `_create_sales_order`, add to the document dict, next to `webstore_dropoff_points`:

```python
		"custom_has_mixed_boxes": _has_mixed_boxes(cart),
```

- [ ] **Step 5: Apply the new custom fields to the test site**

Run: `bench --site webstore.localhost migrate`
Expected: completes without error; `after_migrate` calls `create_webstore_custom_fields()`.

- [ ] **Step 6: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: PASS (10 tests)

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/setup/install.py upande_webstore/api/checkout.py \
        upande_webstore/tests/test_checkout_boxes.py
git commit -m "feat(checkout): record box type, pack rate and box count on documents"
```

---

### Task 6: Configurable lead time, enforced server-side

The date input's `min=` attribute is client-side only today. This backs it with a server check and makes the hardcoded 7 days a setting.

**Files:**
- Modify: `upande_webstore/api/checkout.py`
- Modify: `upande_webstore/tests/test_checkout.py:248-256`
- Test: `upande_webstore/tests/test_checkout_dates.py` (create)

**Interfaces:**
- Consumes: `default_lead_days` from Task 1.
- Produces: `checkout._resolve_delivery_date(shipping_date) -> str` — returns the date to use, or raises `frappe.ValidationError`. `DEFAULT_DELIVERY_DAYS` stays as the fallback when the setting is unset.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_checkout_dates.py`:

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


class TestCheckoutDates(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-DATE-ITEM")
		make_item_price("WS-DATE-ITEM", "Standard Selling", 10)
		make_portal_user("date.buyer@example.com", "Date Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "date.buyer@example.com"})
		set_stock("WS-DATE-ITEM", 500)
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 3)
		frappe.clear_cache()
		frappe.set_user("date.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_past_date_rejected(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		self.assertRaises(
			frappe.ValidationError,
			checkout.place_order,
			shipping_date=add_days(nowdate(), -1),
		)

	def test_date_inside_lead_window_rejected(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		self.assertRaises(
			frappe.ValidationError,
			checkout.place_order,
			shipping_date=add_days(nowdate(), 1),
		)

	def test_date_on_the_lead_boundary_accepted(self):
		from upande_webstore.api import cart, checkout

		when = add_days(nowdate(), 3)
		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order", shipping_date=when)
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), when)
		self.assertEqual(str(order.items[0].delivery_date), when)

	def test_omitted_date_uses_configured_lead(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), add_days(nowdate(), 3))

	def test_unset_setting_falls_back_to_default_constant(self):
		from upande_webstore.api import cart, checkout
		from upande_webstore.api.checkout import DEFAULT_DELIVERY_DAYS

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 0)
		frappe.clear_cache()
		frappe.set_user("date.buyer@example.com")
		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(
			str(order.delivery_date), add_days(nowdate(), DEFAULT_DELIVERY_DAYS)
		)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_dates`
Expected: FAIL — no exception for a past date; `test_omitted_date_uses_configured_lead` gets `+7` instead of `+3`.

- [ ] **Step 3: Write the implementation**

In `upande_webstore/api/checkout.py`, add the import `getdate` and `formatdate` to the existing `frappe.utils` import line so it reads:

```python
from frappe.utils import add_days, flt, formatdate, get_url_to_form, getdate, nowdate
```

Add after `_assert_packable`:

```python
def _resolve_delivery_date(shipping_date):
	"""The buyer's requested date, or the farm's lead time when none is given.

	The cart's date input carries a min= attribute, but that is client-side
	only; this is the check that actually holds. A past date is necessarily
	inside the lead window, so one comparison covers both.
	"""
	from upande_webstore.services.settings import get_settings

	lead_days = int(flt(get_settings().get("default_lead_days"))) or DEFAULT_DELIVERY_DAYS
	earliest = add_days(nowdate(), lead_days)
	if not shipping_date:
		return earliest
	if getdate(shipping_date) < getdate(earliest):
		frappe.throw(
			_("The earliest shipping date we can accept is {0}.").format(
				formatdate(earliest)
			),
			frappe.ValidationError,
		)
	return shipping_date
```

In `place_order`, validate once for both modes by adding immediately after `_assert_packable(cart)`:

```python
	shipping_date = _resolve_delivery_date(shipping_date)
```

In `_create_sales_order`, replace the delivery-date line with the already-resolved value:

```python
	delivery_date = shipping_date
```

- [ ] **Step 4: Update the two existing tests that predate the lead check**

`setup_webstore_settings` now sets `default_lead_days = 7`, so a requested date 5 days out is inside the lead window. In `upande_webstore/tests/test_checkout.py`, in `test_quotation_stores_shipping_date_and_dropoff`, change:

```python
		when = add_days(nowdate(), 5)
```

to:

```python
		when = add_days(nowdate(), 8)
```

`test_sales_order_uses_shipping_date_as_delivery_date` already uses 9 days and needs no change.

- [ ] **Step 5: Run tests to verify they pass**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_dates`
Expected: PASS (5 tests)

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/api/checkout.py upande_webstore/tests/test_checkout.py \
        upande_webstore/tests/test_checkout_dates.py
git commit -m "feat(checkout): configurable lead time enforced server-side"
```

---

### Task 7: Carry webstore fields across quotation → sales order

ERPNext's mapper copies only what its `table_maps` declare, so the buyer's requested date and dropoff are lost when a quotation is converted. This fixes it for portal and desk conversions alike.

**Files:**
- Create: `upande_webstore/services/conversion.py`
- Modify: `upande_webstore/hooks.py:149-155`
- Test: `upande_webstore/tests/test_conversion.py` (create)

**Interfaces:**
- Consumes: the `webstore_shipping_date` / `webstore_dropoff_points` fields the app already creates on Quotation.
- Produces: `conversion.carry_webstore_fields(doc, method=None)`, registered as a Sales Order `before_insert` hook.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_conversion.py`:

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


class TestQuotationConversion(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CONV-ITEM")
		make_item_price("WS-CONV-ITEM", "Standard Selling", 10)
		make_portal_user("conv.buyer@example.com", "Conv Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "conv.buyer@example.com"})
		set_stock("WS-CONV-ITEM", 500)
		frappe.clear_cache()

	def _quotation_with(self, when, dropoff):
		frappe.set_user("conv.buyer@example.com")
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CONV-ITEM", 2)
		result = checkout.place_order(shipping_date=when, dropoff_points=dropoff)
		frappe.set_user("Administrator")
		return result["quotation"]

	def test_conversion_carries_date_and_dropoff(self):
		"""The whole point: ERPNext's mapper drops custom fields, so without
		the hook the buyer's requested date silently vanishes."""
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		when = add_days(nowdate(), 10)
		name = self._quotation_with(when, "Gate 3\nDepot B")
		order = make_sales_order(name)
		order.insert(ignore_permissions=True)
		self.assertEqual(str(order.delivery_date), when)
		self.assertEqual(str(order.items[0].delivery_date), when)
		self.assertIn("Gate 3", order.webstore_dropoff_points)

	def test_conversion_without_webstore_date_is_untouched(self):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		name = self._quotation_with(None, None)
		order = make_sales_order(name)
		order.insert(ignore_permissions=True)
		self.assertTrue(order.delivery_date)

	def test_plain_sales_order_is_untouched(self):
		"""No prevdoc_docname means nothing to carry; the hook must no-op."""
		order = frappe.get_doc({
			"doctype": "Sales Order",
			"customer": "Conv Buyer",
			"company": frappe.defaults.get_global_default("company"),
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 4),
			"items": [{
				"item_code": "WS-CONV-ITEM",
				"qty": 1,
				"rate": 10,
				"delivery_date": add_days(nowdate(), 4),
				"warehouse": frappe.db.get_value(
					"Webstore Warehouse",
					{"parent": "Webstore Settings"},
					"warehouse",
				),
			}],
		})
		order.insert(ignore_permissions=True)
		self.assertEqual(str(order.delivery_date), add_days(nowdate(), 4))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_conversion`
Expected: FAIL on `test_conversion_carries_date_and_dropoff` — `delivery_date` is not the requested date, and `webstore_dropoff_points` is empty.

- [ ] **Step 3: Write the implementation**

Create `upande_webstore/services/conversion.py`:

```python
"""Keep webstore fields alive across quotation -> sales order.

ERPNext's `make_sales_order` copies only the fields its table_maps declare, so
a custom field set by the storefront is silently dropped. That lost the buyer's
requested shipping date and their dropoff instructions on every conversion,
whether done from the portal or the desk.
"""

import frappe

CARRIED = ("webstore_shipping_date", "webstore_dropoff_points", "custom_delivery_point")


def _present(doctype, fieldname):
	return bool(frappe.get_meta(doctype).get_field(fieldname))


def _source_quotation(doc):
	for row in doc.get("items") or []:
		if row.get("prevdoc_docname"):
			return row.get("prevdoc_docname")
	return None


def carry_webstore_fields(doc, method=None):
	if doc.doctype != "Sales Order":
		return
	source = _source_quotation(doc)
	if not source or not frappe.db.exists("Quotation", source):
		return

	# custom_delivery_point comes from another app and may not exist on either
	# doctype; Delivery Point itself is missing on some sites, and writing a
	# Link whose target doctype is absent fails validation.
	readable = [f for f in CARRIED if _present("Quotation", f)]
	if "custom_delivery_point" in readable and not frappe.db.exists(
		"DocType", "Delivery Point"
	):
		readable.remove("custom_delivery_point")
	if not readable:
		return

	values = frappe.db.get_value("Quotation", source, readable, as_dict=True) or {}

	requested = values.get("webstore_shipping_date")
	if requested:
		# the buyer's explicit request beats whatever the mapper derived
		doc.delivery_date = requested
		for row in doc.get("items") or []:
			row.delivery_date = requested

	for field in ("webstore_dropoff_points", "custom_delivery_point"):
		value = values.get(field)
		if value and _present("Sales Order", field) and not doc.get(field):
			doc.set(field, value)
```

In `upande_webstore/hooks.py`, replace the commented-out `doc_events` block with:

```python
doc_events = {
	"Sales Order": {
		"before_insert": "upande_webstore.services.conversion.carry_webstore_fields",
	}
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_conversion`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/services/conversion.py upande_webstore/hooks.py \
        upande_webstore/tests/test_conversion.py
git commit -m "fix(checkout): stop losing shipping date and dropoff on conversion"
```

---

### Task 8: Delivery Point picker when the doctype exists

**Files:**
- Create: `upande_webstore/services/dropoff.py`
- Modify: `upande_webstore/api/checkout.py`
- Modify: `upande_webstore/www/cart.py`
- Test: `upande_webstore/tests/test_dropoff.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `dropoff.delivery_points_available() -> bool`
  - `dropoff.get_delivery_points() -> list[str]`
  - `checkout.place_order(..., delivery_point=None)` — extra keyword argument
  - `www/cart.py` context gains `delivery_points` (list) and `delivery_points_available` (bool)

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_dropoff.py`:

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


class TestDropoff(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-DROP-ITEM")
		make_item_price("WS-DROP-ITEM", "Standard Selling", 10)
		make_portal_user("drop.buyer@example.com", "Drop Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "drop.buyer@example.com"})
		set_stock("WS-DROP-ITEM", 500)
		frappe.set_user("drop.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_absent_doctype_reports_unavailable(self):
		"""Mona live's state: three Link fields point at a Delivery Point
		doctype that does not exist."""
		from upande_webstore.services import dropoff

		if frappe.db.exists("DocType", "Delivery Point"):
			self.skipTest("site has Delivery Point installed")
		self.assertFalse(dropoff.delivery_points_available())
		self.assertEqual(dropoff.get_delivery_points(), [])

	def test_free_text_dropoff_still_stored(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DROP-ITEM", 1)
		result = checkout.place_order(dropoff_points="Gate 3")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.webstore_dropoff_points, "Gate 3")

	def test_delivery_point_ignored_when_doctype_absent(self):
		"""Passing one must not raise — it is simply not stored."""
		from upande_webstore.api import cart, checkout

		if frappe.db.exists("DocType", "Delivery Point"):
			self.skipTest("site has Delivery Point installed")
		cart.add_item("WS-DROP-ITEM", 1)
		result = checkout.place_order(delivery_point="AIRFLO")
		self.assertTrue(result["quotation"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_dropoff`
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.services.dropoff'`

- [ ] **Step 3: Write the implementation**

Create `upande_webstore/services/dropoff.py`:

```python
"""Dropoff points, detected rather than owned.

`Delivery Point` is a doctype another app ships — it exists on some sites and
not others, while Link fields pointing at it exist regardless. So this app
never defines it: when the doctype is present the storefront offers a picker
and writes the Link, and when it is absent the buyer types free text exactly
as before.
"""

import frappe

DOCTYPE = "Delivery Point"


def delivery_points_available():
	return bool(frappe.db.exists("DocType", DOCTYPE))


def get_delivery_points():
	if not delivery_points_available():
		return []
	filters = {}
	if frappe.get_meta(DOCTYPE).get_field("disabled"):
		filters["disabled"] = 0
	return frappe.get_all(DOCTYPE, filters=filters, pluck="name", order_by="name asc")


def resolve(delivery_point):
	"""The value to store, or None when it cannot be stored on this site."""
	if not delivery_point or not delivery_points_available():
		return None
	if not frappe.db.exists(DOCTYPE, delivery_point):
		return None
	return delivery_point
```

In `upande_webstore/api/checkout.py`, add the import at the top of the module:

```python
from upande_webstore.services import dropoff
```

Add `delivery_point=None` to `place_order`'s signature, after `dropoff_points`.
The builders are called positionally through `build(...)`, so append the new
argument to that call — it becomes:

```python
		doc = build(
			cart, customer, settings, price_list, contact_name, address_name,
			po_reference, notes, shipping_date, dropoff_points, delivery_point,
		)
```

Add `delivery_point=None` as the final keyword argument to **both**
`_create_quotation` and `_create_sales_order`.

Then set the field only when this site can store it. `_create_quotation`'s local
is `quotation` and `_create_sales_order`'s is `order`, so add to each builder
immediately before its `return`, using the matching local name:

```python
	# in _create_quotation, after quotation.submit()
	stored_point = dropoff.resolve(delivery_point)
	if stored_point and frappe.get_meta("Quotation").get_field("custom_delivery_point"):
		quotation.db_set("custom_delivery_point", stored_point)
```

```python
	# in _create_sales_order, after order.insert()
	stored_point = dropoff.resolve(delivery_point)
	if stored_point and frappe.get_meta("Sales Order").get_field("custom_delivery_point"):
		order.db_set("custom_delivery_point", stored_point)
```

`db_set` rather than assignment-before-insert, because the Quotation is already
submitted and the Sales Order already inserted at that point, and this field is
metadata the buyer chose rather than anything the totals depend on.

In `upande_webstore/www/cart.py`, before `return context`:

```python
	from upande_webstore.services import dropoff

	context.delivery_points_available = dropoff.delivery_points_available()
	context.delivery_points = dropoff.get_delivery_points()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_dropoff`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/services/dropoff.py upande_webstore/api/checkout.py \
        upande_webstore/www/cart.py upande_webstore/tests/test_dropoff.py
git commit -m "feat(cart): use Delivery Point when the site has it"
```

---

### Task 9: Cart page shows boxes and the reason it is blocked

The page reloads after every quantity change, so the box summary is server-rendered from `serialize_cart` — no client-side maths.

**Files:**
- Modify: `upande_webstore/www/cart.html`
- Test: `upande_webstore/tests/test_cart_page.py` (extend)

**Interfaces:**
- Consumes: `cart.boxes` and per-line `cart.items[].box` from Task 3; `delivery_points` from Task 8; `cart.set_box_type` and `cart.get_box_types` endpoints.
- Produces: no new Python interfaces.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_cart_page.py`. This module renders pages
through `get_html_for_route` and reads context through `get_context` — do not
call `frappe.render_template` on `cart.html` directly, because it extends
`templates/webstore_base.html` and would need the whole theme context built by
hand.

Add these imports at the top of the file, joining the existing
`from upande_webstore.tests.utils import ...` line:

```python
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)
```

```python
class TestCartPageBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from upande_webstore.tests.test_cart_boxes import make_box_item

		setup_webstore_settings()
		make_test_product("WS-PAGE-BOX")
		make_item_price("WS-PAGE-BOX", "Standard Selling", 10)
		make_portal_user("page.box@example.com", "Page Box Buyer")
		cls.zim = make_box_item("WS-PAGE-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "page.box@example.com"})
		set_stock("WS-PAGE-BOX", 5000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.clear_cache()
		frappe.set_user("page.box@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_context_carries_box_types_and_dropoff_mode(self):
		from upande_webstore.www.cart import get_context

		context = frappe._dict()
		get_context(context)
		self.assertIn(self.zim, [box["item_code"] for box in context.box_types])
		self.assertIn("delivery_points_available", context)

	def test_page_shows_box_select_and_the_block_reason(self):
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		html = get_html_for_route("cart")
		self.assertIn("webstore-cart-box", html)
		self.assertIn("whole boxes", html)

	def test_box_column_absent_when_packing_off(self):
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("page.box@example.com")
		html = get_html_for_route("cart")
		self.assertNotIn("webstore-cart-box", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_cart_page`
Expected: FAIL — `AttributeError: 'dict' object has no attribute 'box_types'` on the context test, and `AssertionError: 'webstore-cart-box' not found in ...` on the render test.

- [ ] **Step 3: Render the box column, the group summary and the blocks**

In `upande_webstore/www/cart.html`, add a Box header cell to the items table `<thead>`, after the Qty header:

```html
{% if cart.boxes %}<th style="width:160px">{{ _("Box") }}</th>{% endif %}
```

Add the matching cell in the row loop, after the qty cell:

```html
{% if cart.boxes %}
<td>
	<select class="form-control form-control-sm webstore-cart-box" data-item="{{ row.item_code }}">
		{% for box in box_types %}
		<option value="{{ box.item_code }}" {% if box.item_code == row.box.box_type %}selected{% endif %}>{{ box.item_name }} ({{ box.pack_rate }})</option>
		{% endfor %}
	</select>
	{% if row.box.number_of_boxes %}<small class="text-muted">{{ row.box.number_of_boxes }} {{ _("boxes") }}</small>{% endif %}
</td>
{% endif %}
```

Add `colspan` awareness to the existing `<tfoot>` Total row by changing `colspan="3"` to `colspan="{{ 4 if cart.boxes else 3 }}"`.

Immediately after the items table's closing `</table>`, add the group summary and problem list:

```html
{% if cart.boxes %}
<div class="ws-box-summary" style="margin-top:1rem">
	{% for group in cart.boxes.groups %}
	{% if group.pack_rate %}
	<div style="font-size:.8rem" class="text-muted">
		{{ group.box_name }}: {{ group.stems | int }} {{ _("stems") }} —
		{% if group.is_full %}{{ group.boxes }} {{ _("boxes, all full") }}{% else %}{{ _("does not fill whole boxes") }}{% endif %}
	</div>
	{% endif %}
	{% endfor %}
	{% if cart.boxes.problems %}
	<div class="alert alert-warning" style="margin-top:.6rem;font-size:.8rem">
		{% for problem in cart.boxes.problems %}<div>{{ problem }}</div>{% endfor %}
	</div>
	{% endif %}
</div>
{% endif %}
```

Disable the checkout buttons when the cart cannot be ordered, by adding to both button tags:

```html
{% if cart.boxes and not cart.boxes.packable %}disabled{% endif %}
```

Replace the dropoff form group with the picker-or-textarea pair:

```html
<div class="form-group">
	<label>{{ _("Dropoff points (optional)") }}</label>
	{% if delivery_points_available %}
	<select class="form-control" id="webstore-delivery-point">
		<option value="">{{ _("Discuss with sales") }}</option>
		{% for point in delivery_points %}<option value="{{ point }}">{{ point }}</option>{% endfor %}
	</select>
	{% else %}
	<textarea class="form-control" id="webstore-dropoff" rows="2" placeholder="{{ _('e.g. Gate 3 cold room, then Depot B — one per line') }}"></textarea>
	{% endif %}
</div>
```

In the `<script>` block, add a handler for the box select alongside the qty handler:

```javascript
document.addEventListener("change", async (e) => {
	if (!e.target.matches(".webstore-cart-box")) return;
	try {
		await window.webstore.call("upande_webstore.api.cart.set_box_type",
			{ item_code: e.target.dataset.item, box_type: e.target.value });
		window.location.reload();
	} catch (err) { window.webstore.toast(err.message, true); }
});
```

and make the `place_order` payload read whichever dropoff control exists:

```javascript
				dropoff_points: (document.getElementById("webstore-dropoff") || {}).value || null,
				delivery_point: (document.getElementById("webstore-delivery-point") || {}).value || null,
```

- [ ] **Step 4: Supply `box_types` to the template**

In `upande_webstore/www/cart.py`, before `return context`:

```python
	from upande_webstore.services.packing import get_box_types, packing_enabled

	context.box_types = get_box_types() if packing_enabled() else []
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_cart_page`
Expected: PASS

- [ ] **Step 6: Run the whole suite**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: PASS — no regressions across the existing test modules.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/www/cart.html upande_webstore/www/cart.py \
        upande_webstore/tests/test_cart_page.py
git commit -m "feat(cart): show box breakdown and why checkout is blocked"
```

---

## Enabling on Mona live

Code alone changes nothing. After deploying:

1. Enter `custom_pack_rate` on the seven `custom_is_box` Items (all `0` today). Staging's values are a starting point: `PAC00004` 300, `PAC00007` 500, `PAC00008` 300, `PAC00009` 200.
2. Set `default_box_type`, `minimum_order_stems` = `1000`, `default_lead_days` = `1`.
3. Switch on `enable_box_packing`.

Until step 3 the storefront behaves exactly as it does now.
