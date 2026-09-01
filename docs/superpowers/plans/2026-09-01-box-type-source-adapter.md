# Box Type Source Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the storefront read box types from whichever representation a farm actually runs — a populated `Box Type` doctype or Items flagged `custom_is_box` — and stop the installer from repointing a live field that already exists.

**Architecture:** `services/packing.py` grows a source resolver that answers, once per request, which doctype this site's box types live in. Every read inside the module goes through it; the module's public functions keep their signatures, so `api/cart.py`, `api/checkout.py` and the cart page do not move. Stored box values become `Autocomplete` rather than `Link`, because a Link cannot vary its target per site. Writes into ERPNext and custom-field creation both become conditional on what the site already has.

**Tech Stack:** Frappe v16 / ERPNext, Python 3.11, `bench run-tests`, vanilla JS in desk form scripts.

**Spec:** `docs/superpowers/specs/2026-08-11-flower-trading-model-design.md` — read the section *Box type source is site-dependent (amended 2026-09-01)* before starting.

## Global Constraints

- **No dependency on `upande_harvest` or `upande_webshop`.** Every read of a foreign doctype or custom field must guard on it existing first.
- **This app claims no doctype it did not create.** It reads `Box Type` where a farm has one; it never creates, migrates or takes ownership of it.
- **Deploying must change nothing.** Box packing is inert until `enable_box_packing` is switched on, and inert again when no source resolves.
- **Never trust the client.** Box counts stay server-derived on every cart mutation.
- **Never overwrite another app's field.** A `custom_` field that already exists with a different `fieldtype` or link target is left exactly as it is.
- **Test site:** `webstore.localhost`. Run tests with `bench --site webstore.localhost run-tests --app upande_webstore --module <module>`; run the whole suite with `--app upande_webstore` and no `--module`.
- **One pre-existing failure is expected:** `test_portal_orders.TestPortalOrders.test_invoice_pdf_for_own_invoice` fails with `wkhtmltopdf ... ConnectionRefusedError` because it needs the site's HTTP server up. It is unrelated to this work. Every other test must stay green.

## Before you start

The flower-trading box feature is present in the working tree but **uncommitted** — `services/packing.py`, `test_packing.py`, `test_cart_boxes.py`, `test_checkout_boxes.py` are untracked, and `docs/superpowers/plans/2026-08-11-flower-trading-model.md` has every checkbox unticked. Commit that work first, on its own, so the changes in this plan are reviewable against a clean base.

---

### Task 1: The installer stops rewriting fields it does not own

This is the safety fix and it stands alone. Karen Roses has `Sales Order Item.custom_box_type` as a Link to its own `Box Type` doctype, carrying 5,019 values. `create_custom_fields` updates existing fields rather than skipping them (`frappe/custom/doctype/custom_field/custom_field.py:363`), so installing this app there would repoint that field at `Item` and orphan every value.

**Files:**
- Modify: `upande_webstore/setup/install.py:160-161` (`create_webstore_custom_fields`) and the wrong comment at `:138`
- Test: `upande_webstore/tests/test_install_fields.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `setup.install.create_webstore_custom_fields()` — unchanged signature, now conflict-safe. Task 5 relies on the same conflict rule being true at runtime.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_install_fields.py`:

```python
"""The installer must never repoint a custom field another app owns.

Karen Roses runs `Sales Order Item.custom_box_type` as a Link to its own `Box
Type` doctype with 5,019 values on it. `create_custom_fields` updates existing
fields rather than skipping them, so shipping our definition unguarded would
rewrite the link target and orphan all of them.
"""

import frappe
from frappe.tests import IntegrationTestCase

FIELD = {"dt": "Sales Order Item", "fieldname": "custom_box_type"}


class TestInstallFieldConflicts(IntegrationTestCase):
	def setUp(self):
		self.existing = frappe.db.get_value("Custom Field", FIELD, "name")
		self.original = (
			frappe.db.get_value("Custom Field", self.existing, ["fieldtype", "options"], as_dict=True)
			if self.existing
			else None
		)

	def tearDown(self):
		if self.existing and self.original:
			frappe.db.set_value(
				"Custom Field",
				self.existing,
				{"fieldtype": self.original.fieldtype, "options": self.original.options},
			)
		frappe.clear_cache(doctype="Sales Order Item")
		frappe.db.commit()

	def _point_field_elsewhere(self):
		"""Stand in for Karen Roses: the same fieldname, a different target.

		`Item Group` is used rather than `Box Type` so this test needs no
		fixture doctype — only that the target differs from the `Item` we ship.
		"""
		if self.existing:
			frappe.db.set_value(
				"Custom Field", self.existing, {"fieldtype": "Link", "options": "Item Group"}
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Sales Order Item",
					"fieldname": "custom_box_type",
					"label": "Box Type",
					"fieldtype": "Link",
					"options": "Item Group",
					"insert_after": "qty",
				}
			).insert(ignore_permissions=True)
			self.existing = frappe.db.get_value("Custom Field", FIELD, "name")
		frappe.clear_cache(doctype="Sales Order Item")
		frappe.db.commit()

	def test_an_existing_field_with_another_link_target_is_left_alone(self):
		from upande_webstore.setup.install import create_webstore_custom_fields

		self._point_field_elsewhere()
		create_webstore_custom_fields()
		self.assertEqual(
			frappe.db.get_value("Custom Field", self.existing, "options"),
			"Item Group",
			"the installer repointed a field another app owns",
		)

	def test_conflicting_definitions_are_reported(self):
		from upande_webstore.setup.install import _without_conflicts, WEBSTORE_CUSTOM_FIELDS

		self._point_field_elsewhere()
		safe, skipped = _without_conflicts(WEBSTORE_CUSTOM_FIELDS)
		self.assertTrue(any("custom_box_type" in line for line in skipped))
		kept = [df["fieldname"] for df in safe.get("Sales Order Item", [])]
		self.assertNotIn("custom_box_type", kept)
		self.assertIn("custom_pack_rate", kept, "unrelated fields must still be ensured")

	def test_matching_definitions_are_still_ensured(self):
		from upande_webstore.setup.install import _without_conflicts, WEBSTORE_CUSTOM_FIELDS

		safe, skipped = _without_conflicts({"Item": WEBSTORE_CUSTOM_FIELDS["Item"]})
		self.assertEqual(skipped, [])
		self.assertEqual(len(safe["Item"]), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_install_fields`

Expected: FAIL — `ImportError: cannot import name '_without_conflicts'`, and `test_an_existing_field_with_another_link_target_is_left_alone` reports `'Item' != 'Item Group'`.

- [ ] **Step 3: Write the implementation**

In `upande_webstore/setup/install.py`, replace `create_webstore_custom_fields`:

```python
def create_webstore_custom_fields():
	"""Ensure our fields, but never repoint one a site already defines.

	`create_custom_fields` updates existing fields rather than skipping them, so
	an unguarded install would rewrite the link target of a `custom_` field
	another app owns — Karen Roses' `Sales Order Item.custom_box_type` links to
	its own `Box Type` doctype and carries 5,019 values. Anything already
	defined differently is left exactly as it is, and logged.
	"""
	safe, skipped = _without_conflicts(WEBSTORE_CUSTOM_FIELDS)
	if skipped:
		frappe.log_error(
			title="Webstore custom fields skipped",
			message="This site already defines these fields differently:\n" + "\n".join(skipped),
		)
	create_custom_fields(safe, ignore_validate=True)


def _without_conflicts(definitions):
	"""Split our field definitions into (safe to ensure, skipped with reasons).

	Reads the doctype's meta rather than the Custom Field table so a standard
	field of the same name counts as a conflict too.
	"""
	safe = {}
	skipped = []
	for doctype, fields in definitions.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		keep = []
		for df in fields:
			existing = meta.get_field(df["fieldname"])
			if existing and _conflicts(existing, df):
				skipped.append(
					"{0}.{1}: site has {2}/{3}, we ship {4}/{5}".format(
						doctype,
						df["fieldname"],
						existing.fieldtype,
						existing.options or "-",
						df["fieldtype"],
						df.get("options") or "-",
					)
				)
				continue
			keep.append(df)
		if keep:
			safe[doctype] = keep
	return safe, skipped


def _conflicts(existing, ours):
	"""A different fieldtype, or a Link/Table pointing somewhere else."""
	if existing.fieldtype != ours["fieldtype"]:
		return True
	if ours["fieldtype"] in ("Link", "Table", "Table MultiSelect"):
		return (existing.options or "") != (ours.get("options") or "")
	return False
```

Then fix the wrong comment above the `Item` block (`install.py:138`), replacing the sentence *"create_custom_fields skips fields that already exist, so ensuring them is a no-op there and makes the feature usable on a farm that has no harvest app to create them"* with:

```python
	# usable on a farm that has no harvest app to create them.
	# create_custom_fields *updates* fields that already exist rather than
	# skipping them, so create_webstore_custom_fields filters out anything this
	# site defines with a different type or link target first.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_install_fields`
Expected: PASS, 3 tests.

- [ ] **Step 5: Check nothing else broke**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: only the known `test_invoice_pdf_for_own_invoice` failure.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/setup/install.py upande_webstore/tests/test_install_fields.py
git commit -m "fix(install): never repoint a custom field the site already owns"
```

---

### Task 2: Box types resolve from whichever source the site has

**Files:**
- Modify: `upande_webstore/services/packing.py` (whole read layer)
- Modify: `upande_webstore/tests/utils.py` (fixture helpers, and clear the cache in `setup_webstore_settings`)
- Modify: `upande_webstore/www/cart.py`, `upande_webstore/www/cart.html:36-37` (payload key rename)
- Test: `upande_webstore/tests/test_packing.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `packing.get_box_source() -> frappe._dict | None` with keys `doctype`, `rate_field`, `label_field`, `filters`, `candidate_filters`
  - `packing.clear_box_source_cache() -> None`
  - `packing.source_label() -> str` — human sentence naming the source
  - `packing.get_box_types() -> [{"box_type", "box_name", "pack_rate"}]` — **keys renamed** from `item_code`/`item_name`
  - `packing.get_unusable_box_types() -> [{"box_type", "box_name", "reasons": [str]}]`
  - `packing.get_pack_rate(box) -> int`, `is_usable_box(box) -> bool`, `box_label(box) -> str` — unchanged signatures
  - `tests.utils.make_box_type(name, capacity) -> str`, `tests.utils.drop_box_type_doctype() -> None`

- [ ] **Step 1: Add the test fixtures**

In `upande_webstore/tests/utils.py`, add near the other factories:

```python
BOX_TYPE_DOCTYPE = "Box Type"


def make_box_type_doctype():
	"""A stand-in for the `Box Type` doctype Karen Roses runs.

	Created as a Custom DocType so this app owns no file for it, exactly as on
	live where another app defines it. Tests that create it MUST drop it in
	tearDownClass: a lingering Box Type flips the source for every other module.
	"""
	if frappe.db.exists("DocType", BOX_TYPE_DOCTYPE):
		return BOX_TYPE_DOCTYPE
	frappe.get_doc({
		"doctype": "DocType",
		"name": BOX_TYPE_DOCTYPE,
		"module": "Upande Webstore",
		"custom": 1,
		"autoname": "field:box_type",
		"fields": [
			{"fieldname": "box_type", "fieldtype": "Data", "label": "Box Type", "unique": 1, "reqd": 1},
			{"fieldname": "custom_stem_capacity", "fieldtype": "Int", "label": "Stem Capacity"},
		],
		"permissions": [
			{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
		],
	}).insert(ignore_permissions=True)
	frappe.clear_cache()
	return BOX_TYPE_DOCTYPE


def make_box_type(name, capacity):
	"""One Box Type record, e.g. make_box_type("Xpol", 350)."""
	from upande_webstore.services.packing import clear_box_source_cache

	make_box_type_doctype()
	if frappe.db.exists(BOX_TYPE_DOCTYPE, name):
		frappe.db.set_value(BOX_TYPE_DOCTYPE, name, "custom_stem_capacity", capacity)
	else:
		frappe.get_doc({
			"doctype": BOX_TYPE_DOCTYPE,
			"box_type": name,
			"custom_stem_capacity": capacity,
		}).insert(ignore_permissions=True)
	clear_box_source_cache()
	return name


def drop_box_type_doctype():
	from upande_webstore.services.packing import clear_box_source_cache

	if frappe.db.exists("DocType", BOX_TYPE_DOCTYPE):
		frappe.delete_doc("DocType", BOX_TYPE_DOCTYPE, force=1, ignore_permissions=True)
	frappe.clear_cache()
	clear_box_source_cache()
```

And in `setup_webstore_settings`, immediately before `frappe.clear_cache()` near the end, add:

```python
	from upande_webstore.services.packing import clear_box_source_cache

	clear_box_source_cache()
```

- [ ] **Step 2: Write the failing tests**

Append to `upande_webstore/tests/test_packing.py`:

```python
class TestBoxSource(IntegrationTestCase):
	"""Which representation a farm runs decides where box types come from.

	Mona has Items flagged custom_is_box. Karen Roses has a populated `Box Type`
	doctype and no box fields on Item at all. Both must work.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	@classmethod
	def tearDownClass(cls):
		from upande_webstore.tests.utils import drop_box_type_doctype

		drop_box_type_doctype()
		super().tearDownClass()

	def setUp(self):
		from upande_webstore.tests.utils import drop_box_type_doctype

		drop_box_type_doctype()

	def test_items_are_the_source_when_no_box_type_doctype_exists(self):
		from upande_webstore.services.packing import get_box_source

		source = get_box_source()
		self.assertEqual(source.doctype, "Item")
		self.assertEqual(source.rate_field, "custom_pack_rate")

	def test_a_populated_box_type_doctype_wins(self):
		from upande_webstore.services.packing import get_box_source
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		source = get_box_source()
		self.assertEqual(source.doctype, "Box Type")
		self.assertEqual(source.rate_field, "custom_stem_capacity")

	def test_an_empty_box_type_doctype_falls_through_to_items(self):
		"""Mona has an empty one. An empty source must not disable packing."""
		from upande_webstore.services.packing import clear_box_source_cache, get_box_source
		from upande_webstore.tests.utils import make_box_type_doctype

		make_box_type_doctype()
		clear_box_source_cache()
		self.assertEqual(get_box_source().doctype, "Item")

	def test_a_box_type_with_no_capacity_falls_through_to_items(self):
		from upande_webstore.services.packing import clear_box_source_cache, get_box_source
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Unrated", 0)
		clear_box_source_cache()
		self.assertEqual(get_box_source().doctype, "Item")

	def test_box_types_come_back_from_the_box_type_doctype(self):
		from upande_webstore.services.packing import get_box_types, get_pack_rate
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		make_box_type("Standard", 400)
		names = {b["box_type"]: b["pack_rate"] for b in get_box_types()}
		self.assertEqual(names["Xpol"], 350)
		self.assertEqual(names["Standard"], 400)
		self.assertEqual(get_pack_rate("Xpol"), 350)

	def test_an_unrated_box_type_is_reported_as_unusable_not_hidden(self):
		from upande_webstore.services.packing import get_box_types, get_unusable_box_types
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		make_box_type("Unrated", 0)
		self.assertNotIn("Unrated", [b["box_type"] for b in get_box_types()])
		unusable = {b["box_type"]: b["reasons"] for b in get_unusable_box_types()}
		self.assertIn("Unrated", unusable)
		self.assertTrue(unusable["Unrated"])

	def test_the_source_is_named_in_plain_words(self):
		from upande_webstore.services.packing import source_label
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		self.assertIn("Box Type", source_label())
```

Leave `TestPackingSettings.test_packing_fields_exist_with_inert_defaults` alone for now — its `default_box_type` assertion changes in Task 3, along with the field itself.

- [ ] **Step 3: Run tests to verify they fail**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: FAIL — `ImportError: cannot import name 'get_box_source' from 'upande_webstore.services.packing'`.

- [ ] **Step 4: Write the resolver**

Rewrite the read layer of `upande_webstore/services/packing.py`. Replace the module docstring and everything from `BOX_FLAG` down to and including `box_label`:

```python
"""Box arithmetic for stem orders.

Pure maths plus a few thin reads. Deliberately knows nothing about carts or
documents, so the arithmetic can be tested without building either.

Where box types live differs per farm, so one resolver answers it once per
request and every read goes through it. Karen Roses runs a populated `Box Type`
doctype whose `custom_stem_capacity` is the pack rate; Mona flags Items with
`custom_is_box` and `custom_pack_rate`. Both are other apps' schema, so every
read guards on the doctype and the field actually existing: this app must work
on a farm that has neither.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_webstore.services.settings import get_settings

BOX_FLAG = "custom_is_box"
BOX_RATE = "custom_pack_rate"
BOX_TYPE_DOCTYPE = "Box Type"
BOX_TYPE_CAPACITY = "custom_stem_capacity"

_UNSET = object()


def packing_enabled():
	return bool(int(flt(get_settings().get("enable_box_packing"))))


def get_default_box_type():
	return get_settings().get("default_box_type") or None


def get_minimum_order_stems():
	return int(flt(get_settings().get("minimum_order_stems")))


def get_box_source():
	"""Which doctype this site's box types live in, or None.

	Resolved once per request: it is a property of the site's schema, not of the
	cart being priced.
	"""
	if getattr(frappe.local, "webstore_box_source", _UNSET) is _UNSET:
		frappe.local.webstore_box_source = _resolve_box_source()
	return frappe.local.webstore_box_source


def clear_box_source_cache():
	"""Tests flip the source within one request; production never does."""
	frappe.local.webstore_box_source = _UNSET


def _resolve_box_source():
	if _box_type_doctype_populated():
		return frappe._dict(
			doctype=BOX_TYPE_DOCTYPE,
			rate_field=BOX_TYPE_CAPACITY,
			label_field="box_type",
			filters={},
			candidate_filters={},
		)
	if _item_has_box_fields():
		return frappe._dict(
			doctype="Item",
			rate_field=BOX_RATE,
			label_field="item_name",
			filters={BOX_FLAG: 1, "disabled": 0},
			candidate_filters={BOX_FLAG: 1},
		)
	return None


def _box_type_doctype_populated():
	"""A `Box Type` that exists but holds no usable capacity falls through.

	Mona has an empty one; treating that as the source would silently disable
	packing on a farm whose real rates are on Items.
	"""
	if not frappe.db.exists("DocType", BOX_TYPE_DOCTYPE):
		return False
	if not frappe.get_meta(BOX_TYPE_DOCTYPE).get_field(BOX_TYPE_CAPACITY):
		return False
	return bool(
		frappe.get_all(BOX_TYPE_DOCTYPE, filters={BOX_TYPE_CAPACITY: [">", 0]}, limit=1)
	)


def _item_has_box_fields():
	meta = frappe.get_meta("Item")
	return bool(meta.get_field(BOX_FLAG)) and bool(meta.get_field(BOX_RATE))


def source_label():
	"""Plain words for the desk panel and validation messages."""
	source = get_box_source()
	if not source:
		return _("no box type source on this site")
	if source.doctype == BOX_TYPE_DOCTYPE:
		return _("Box Type records with a stem capacity above zero")
	return _("Items flagged Is Box with a pack rate above zero")


def _source_fields(source):
	return [
		"name",
		f"{source.label_field} as box_name",
		f"{source.rate_field} as pack_rate",
	]


def get_box_types():
	"""Boxes the farm can actually pack into: usable, rate above zero."""
	source = get_box_source()
	if not source:
		return []
	rows = frappe.get_all(
		source.doctype,
		filters=source.filters,
		fields=_source_fields(source),
		order_by=f"{source.label_field} asc",
	)
	return [
		{
			"box_type": row.name,
			"box_name": row.box_name or row.name,
			"pack_rate": int(flt(row.pack_rate)),
		}
		for row in rows
		if flt(row.pack_rate) > 0
	]


def get_unusable_box_types():
	"""Boxes the site defines that the storefront ignores, and why.

	Invisible otherwise: `get_box_types` simply returns a shorter list, which
	reads as a setting being ignored rather than a rate being missing.
	"""
	source = get_box_source()
	if not source:
		return []
	rows = frappe.get_all(
		source.doctype,
		filters=source.candidate_filters,
		fields=_source_fields(source) + list(source.filters),
	)
	out = []
	for row in rows:
		reasons = []
		if flt(row.pack_rate) <= 0:
			reasons.append(_("no pack rate entered"))
		for field, expected in source.filters.items():
			if int(flt(row.get(field))) != int(flt(expected)):
				reasons.append(_("disabled") if field == "disabled" else _("not flagged as a box"))
		if reasons:
			out.append(
				{
					"box_type": row.name,
					"box_name": row.box_name or row.name,
					"reasons": reasons,
				}
			)
	return out


def get_pack_rate(box):
	"""Stems per box, or 0 when the box is missing, unusable, or has no rate.
	0 always means 'do not validate'."""
	source = get_box_source()
	if not box or not source:
		return 0
	row = frappe.db.get_value(
		source.doctype, box, [source.rate_field] + list(source.filters), as_dict=True
	)
	if not row:
		return 0
	for field, expected in source.filters.items():
		if int(flt(row.get(field))) != int(flt(expected)):
			return 0
	rate = flt(row.get(source.rate_field))
	return int(rate) if rate > 0 else 0


def get_product_box_type(item_code):
	"""The box a product ships in, falling back to the farm default.

	The product supplies the default — it knows a 120cm stem will not fit a
	100x33x20 box — and the buyer may override it per basket line. Mirrors
	`Website Item.custom_box_type`, which is how Mona already models this.
	"""
	box = frappe.db.get_value("Webstore Product", {"item": item_code}, "box_type")
	if box and is_usable_box(box):
		return box
	default = get_default_box_type()
	return default if default and is_usable_box(default) else None


def is_usable_box(box):
	return get_pack_rate(box) > 0


def box_label(box):
	if not box:
		return _("no box type")
	source = get_box_source()
	if not source:
		return box
	return frappe.db.get_value(source.doctype, box, source.label_field) or box
```

Everything from `compute_boxes` down stays exactly as it is.

- [ ] **Step 5: Update the three consumers that still assume Items**

`upande_webstore/api/cart.py:135-138` builds a line's box label with a hardcoded Item read, which returns nothing under a `Box Type` source. Replace it:

```python
				"box_name": (
					packing.box_label(row.box_type) if row.get("box_type") else None
				),
```

and add the import at the top of `serialize_cart`:

```python
	from upande_webstore.services import packing
```

`get_box_types()` now returns `box_type`/`box_name` instead of `item_code`/`item_name`. In `upande_webstore/www/cart.html:36-37`, replace the option loop:

```html
						{% for box in box_types %}
						<option value="{{ box.box_type }}" {% if box.box_type == row.box_type %}selected{% endif %}>{{ box.box_name }} ({{ box.pack_rate }})</option>
						{% endfor %}
```

Then confirm nothing else resolves a box through Item:

```bash
grep -rn '"Item"' upande_webstore/api/cart.py upande_webstore/www/cart.py | grep -i box
grep -rn "box\." upande_webstore/www/cart.html | grep "item_"
```

Expected: no output from either.

- [ ] **Step 6: Run tests to verify they pass**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: PASS.

- [ ] **Step 7: Check nothing else broke**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: only the known PDF failure. Pay attention to `test_cart_boxes`, `test_checkout_boxes` and `test_cart_page` — they exercise the Item source through the new resolver.

- [ ] **Step 8: Commit**

```bash
git add upande_webstore/services/packing.py upande_webstore/tests/utils.py \
        upande_webstore/tests/test_packing.py upande_webstore/www/cart.html
git commit -m "feat(packing): resolve box types from Box Type records or Items"
```

---

### Task 3: Stored box values become Autocomplete

A Link cannot vary its target per site. Both fieldtypes store the same string, so there is **no data migration** — only the field definition changes.

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.json` (`box_type`)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_cart_item/webstore_cart_item.json` (`box_type`)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json` (`default_box_type`)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py:21-36` (`validate_box_type`)
- Test: `upande_webstore/tests/test_packing.py`

**Interfaces:**
- Consumes: `packing.source_label()`, `packing.is_usable_box()` from Task 2.
- Produces: three `Autocomplete` fields named `box_type`, `box_type`, `default_box_type`. Task 4 populates their suggestions.

- [ ] **Step 1: Write the failing test**

Append to `TestBoxSource` in `upande_webstore/tests/test_packing.py`:

```python
	def test_box_fields_are_autocomplete_not_links(self):
		"""A Link cannot vary its target per site; these must not have one."""
		for doctype, fieldname in (
			("Webstore Product", "box_type"),
			("Webstore Cart Item", "box_type"),
			("Webstore Settings", "default_box_type"),
		):
			field = frappe.get_meta(doctype).get_field(fieldname)
			self.assertEqual(field.fieldtype, "Autocomplete", f"{doctype}.{fieldname}")
			self.assertFalse(field.options, f"{doctype}.{fieldname} still names a target")

	def test_a_product_rejects_a_box_the_source_does_not_know(self):
		from upande_webstore.tests.utils import make_box_type, make_test_product

		make_box_type("Xpol", 350)
		product = make_test_product("WS-SRC-PROD")
		product.box_type = "Not A Box"
		with self.assertRaises(frappe.ValidationError) as ctx:
			product.save(ignore_permissions=True)
		self.assertIn("Box Type", str(ctx.exception))

	def test_a_product_accepts_a_box_from_the_resolved_source(self):
		from upande_webstore.tests.utils import make_box_type, make_test_product

		make_box_type("Xpol", 350)
		product = make_test_product("WS-SRC-PROD2")
		product.box_type = "Xpol"
		product.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Webstore Product", product.name, "box_type"), "Xpol"
		)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing`
Expected: FAIL — `'Link' != 'Autocomplete'`.

- [ ] **Step 3: Update the assertion that named the old fieldtype**

In `TestPackingSettings.test_packing_fields_exist_with_inert_defaults`, replace:

```python
		self.assertEqual(meta.get_field("default_box_type").options, "Item")
```

with:

```python
		self.assertEqual(meta.get_field("default_box_type").fieldtype, "Autocomplete")
```

- [ ] **Step 4: Change the three field definitions**

`webstore_product.json` — replace the `box_type` field object with:

```json
  {
   "fieldname": "box_type",
   "fieldtype": "Autocomplete",
   "label": "Box Type",
   "description": "The box this product ships in. Blank falls back to the farm default. Suggestions come from whichever box source this site runs — see Webstore Settings."
  },
```

`webstore_cart_item.json` — replace its `box_type` field object with:

```json
  {
   "fieldname": "box_type",
   "fieldtype": "Autocomplete",
   "label": "Box Type",
   "in_list_view": 1
  },
```

`webstore_settings.json` — replace the `default_box_type` field object with:

```json
  {
   "fieldname": "default_box_type",
   "fieldtype": "Autocomplete",
   "label": "Default Box Type",
   "description": "Seeds each new cart line. Must be a usable box from this site's box source."
  },
```

Note both `options` and `link_filters` are dropped in every case — `link_filters` named `custom_is_box`, which does not exist on a `Box Type` source.

- [ ] **Step 5: Make the validation message name the source**

In `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py`, replace `validate_box_type`:

```python
	def validate_box_type(self):
		"""A box that is not a box would silently fall back to the farm default,
		which looks like the setting being ignored. Say so, and name where box
		types come from on this site — it differs per farm."""
		from frappe import _

		if not self.box_type:
			return
		from upande_webstore.services.packing import is_usable_box, source_label

		if not is_usable_box(self.box_type):
			frappe.throw(
				_("{0} is not a usable box type on this site. Box types come from {1}.").format(
					self.box_type, source_label()
				),
				frappe.ValidationError,
			)
```

- [ ] **Step 6: Apply the schema change and run the tests**

```bash
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_packing
```

Expected: PASS.

- [ ] **Step 7: Check nothing else broke**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: only the known PDF failure.

- [ ] **Step 8: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.json \
        upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.py \
        upande_webstore/upande_webstore/doctype/webstore_cart_item/webstore_cart_item.json \
        upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json \
        upande_webstore/tests/test_packing.py
git commit -m "feat(packing): box fields are Autocomplete, not site-specific Links"
```

---

### Task 4: Desk endpoints and autocomplete suggestions

`api/cart.py`'s box endpoints are wrapped in `@guard("cart")`, so a farm with the cart feature switched off could not open its own settings form. These are separate.

**Files:**
- Create: `upande_webstore/api/boxes.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.js`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js` (`refresh`)
- Test: `upande_webstore/tests/test_boxes_api.py` (create)

**Interfaces:**
- Consumes: `packing.get_box_types()`, `packing.get_unusable_box_types()`, `packing.get_box_source()`, `packing.source_label()`, `packing.get_default_box_type()` from Task 2.
- Produces: `upande_webstore.api.boxes.list_box_types()` and `upande_webstore.api.boxes.describe_source()`. Task 6 renders `describe_source()`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_boxes_api.py`:

```python
"""Desk box endpoints.

Deliberately not in `api/cart.py`: those are wrapped in `@guard("cart")`, so a
farm with the cart feature off could not open Webstore Settings.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	drop_box_type_doctype,
	make_box_type,
	setup_webstore_settings,
)


class TestBoxesApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	@classmethod
	def tearDownClass(cls):
		drop_box_type_doctype()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		drop_box_type_doctype()

	def test_list_box_types_returns_plain_names(self):
		from upande_webstore.api.boxes import list_box_types

		make_box_type("Xpol", 350)
		make_box_type("Standard", 400)
		self.assertEqual(sorted(list_box_types()), ["Standard", "Xpol"])

	def test_describe_source_names_the_doctype_and_splits_usable_from_not(self):
		from upande_webstore.api.boxes import describe_source

		make_box_type("Xpol", 350)
		make_box_type("Unrated", 0)
		result = describe_source()
		self.assertEqual(result["doctype"], "Box Type")
		self.assertIn("Box Type", result["label"])
		self.assertEqual([b["box_type"] for b in result["usable"]], ["Xpol"])
		self.assertEqual([b["box_type"] for b in result["unusable"]], ["Unrated"])

	def test_describe_source_is_honest_when_there_is_no_source(self):
		"""A farm with neither representation must be told so, not shown
		an empty list that reads like a loading failure."""
		from upande_webstore.api.boxes import describe_source
		from unittest.mock import patch

		with patch("upande_webstore.services.packing._item_has_box_fields", return_value=False):
			from upande_webstore.services.packing import clear_box_source_cache

			clear_box_source_cache()
			result = describe_source()
		clear_box_source_cache()
		self.assertIsNone(result["doctype"])
		self.assertEqual(result["usable"], [])

	def test_a_website_user_cannot_read_the_desk_endpoints(self):
		from upande_webstore.api.boxes import list_box_types
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("box.reader@example.com", "Box Reader Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				list_box_types()
		finally:
			frappe.set_user("Administrator")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_boxes_api`
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.api.boxes'`.

- [ ] **Step 3: Write the endpoints**

Create `upande_webstore/api/boxes.py`:

```python
"""Desk-side box type reads.

Separate from `api/cart.py` because those endpoints are wrapped in
`@guard("cart")` — a farm with the cart feature switched off must still be able
to open Webstore Settings and see how its boxes are configured.
"""

import frappe

from upande_webstore.services import packing


@frappe.whitelist()
def list_box_types():
	"""Usable box type names, for desk autocompletes."""
	frappe.only_for("System Manager")
	return [box["box_type"] for box in packing.get_box_types()]


@frappe.whitelist()
def describe_source():
	"""Everything the Webstore Settings box panel renders."""
	frappe.only_for("System Manager")
	source = packing.get_box_source()
	return {
		"doctype": source.doctype if source else None,
		"label": packing.source_label(),
		"usable": packing.get_box_types(),
		"unusable": packing.get_unusable_box_types(),
		"default_box_type": packing.get_default_box_type(),
	}
```

- [ ] **Step 4: Feed the autocompletes**

Create `upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.js`:

```javascript
frappe.ui.form.on("Webstore Product", {
	refresh(frm) {
		// Box types come from whichever source this site runs, so the list is
		// fetched rather than declared as link options on the field.
		frappe.call("upande_webstore.api.boxes.list_box_types").then((r) => {
			const options = r.message || [];
			frm.set_df_property("box_type", "options", options);
			frm.fields_dict.box_type?.set_data(options);
		});
	},
});
```

In `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js`, add inside `refresh(frm)`, just after the existing `list_presets` call:

```javascript
		frappe.call("upande_webstore.api.boxes.list_box_types").then((r) => {
			const options = r.message || [];
			// set_data as well as the property: an Autocomplete reads df.options
			// only in make_input(), which has already run by the time this
			// resolves — the same reason the occasion field below does it.
			frm.set_df_property("default_box_type", "options", options);
			frm.fields_dict.default_box_type?.set_data(options);
		});
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_boxes_api`
Expected: PASS, 4 tests.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/api/boxes.py upande_webstore/tests/test_boxes_api.py \
        upande_webstore/upande_webstore/doctype/webstore_product/webstore_product.js \
        upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js
git commit -m "feat(desk): box type suggestions from the resolved source"
```

---

### Task 5: Checkout writes box fields only where they fit

**Files:**
- Modify: `upande_webstore/api/checkout.py:152-205` (`_present` → `_writable`, `_cart_items`), `:205-275` (both creators)
- Test: `upande_webstore/tests/test_checkout_boxes.py`

**Interfaces:**
- Consumes: `packing.get_box_source()` from Task 2.
- Produces: `checkout._writable(doctype, fieldname, expect_options=None) -> bool`; `_cart_items(cart, target_doctype)` — **signature change**, both callers updated in this task.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_checkout_boxes.py`:

```python
class TestBoxFieldTargetMismatch(IntegrationTestCase):
	"""Karen Roses' `Sales Order Item.custom_box_type` links to its own `Box
	Type` doctype. Writing an Item code there would fail validation and corrupt
	a field ops reads, so we write nothing at all."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def setUp(self):
		self.field = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
		)
		self.original = frappe.db.get_value("Custom Field", self.field, "options")

	def tearDown(self):
		frappe.db.set_value("Custom Field", self.field, "options", self.original)
		frappe.clear_cache(doctype="Quotation Item")
		frappe.db.commit()

	def test_a_mismatched_target_is_skipped_not_written(self):
		from upande_webstore.api.checkout import _writable

		frappe.db.set_value("Custom Field", self.field, "options", "Item Group")
		frappe.clear_cache(doctype="Quotation Item")
		self.assertFalse(_writable("Quotation Item", "custom_box_type", "Item"))
		self.assertTrue(_writable("Quotation Item", "custom_pack_rate"))

	def test_a_matching_target_is_written(self):
		from upande_webstore.api.checkout import _writable

		self.assertTrue(_writable("Quotation Item", "custom_box_type", "Item"))

	def test_an_absent_field_is_never_written(self):
		from upande_webstore.api.checkout import _writable

		self.assertFalse(_writable("Quotation Item", "custom_not_a_real_field"))
```

Add an end-to-end assertion to the existing box mapping test class in the same file — a quotation placed while the field points elsewhere must still submit, with the box field left empty:

```python
	def test_an_order_still_places_when_the_box_field_points_elsewhere(self):
		field = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
		)
		original = frappe.db.get_value("Custom Field", field, "options")
		frappe.db.set_value("Custom Field", field, "options", "Item Group")
		frappe.clear_cache(doctype="Quotation Item")
		try:
			result = checkout.place_order(mode="quotation")
			quotation = frappe.get_doc("Quotation", result["quotation"])
			self.assertFalse(quotation.items[0].get("custom_box_type"))
			self.assertTrue(flt(quotation.items[0].get("custom_pack_rate")) > 0)
		finally:
			frappe.db.set_value("Custom Field", field, "options", original)
			frappe.clear_cache(doctype="Quotation Item")
			frappe.db.commit()
```

Add that last test to the existing `TestBoxFieldMapping` class in the same file (`test_checkout_boxes.py:100`), which already builds a priced, boxed cart in `setUpClass`. That class calls checkout as `checkout.place_order(...)` via `from upande_webstore.api import checkout`, and `flt` comes from `frappe.utils` — match both rather than adding new imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: FAIL — `ImportError: cannot import name '_writable'`.

- [ ] **Step 3: Write the implementation**

In `upande_webstore/api/checkout.py`, replace `_present` with:

```python
def _writable(doctype, fieldname, expect_options=None):
	"""True when we may write this field on this site.

	A field of the same name may point somewhere else entirely: Karen Roses'
	`Sales Order Item.custom_box_type` links to its own `Box Type` doctype, and
	writing an Item code there would fail validation and corrupt a field ops
	reads. Skipping is always safe — the order still places, just without the
	box detail.
	"""
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field:
		return False
	if expect_options is None:
		return True
	return (field.options or "") == expect_options
```

Update its existing caller in `_store_delivery_point`:

```python
	if stored and _writable(doc.doctype, "custom_delivery_point"):
```

Then give `_cart_items` a target and make each box field conditional:

```python
def _cart_items(cart, target_doctype):
	"""Cart lines as document rows.

	`target_doctype` decides which box fields are safe to write — Quotation Item
	and Sales Order Item are not guaranteed to model box type the same way.
	"""
	from upande_webstore.services import packing

	include_boxes = packing.packing_enabled()
	source = packing.get_box_source()
	box_doctype = source.doctype if source else None
	write_box = (
		include_boxes
		and box_doctype
		and _writable(target_doctype, "custom_box_type", box_doctype)
	)
	write_rate = include_boxes and _writable(target_doctype, "custom_pack_rate")
	write_count = include_boxes and _writable(target_doctype, "custom_number_of_boxes")
```

Keep the body of the existing loop, replacing the box block with:

```python
		if include_boxes and row.box_type:
			if write_box:
				line["custom_box_type"] = row.box_type
			if write_rate:
				line["custom_pack_rate"] = packing.get_pack_rate(row.box_type)
			if write_count:
				# a line sharing a mixed box has no whole-box count of its own
				line["custom_number_of_boxes"] = row.number_of_boxes or 0
```

Update both callers — in `_create_quotation`:

```python
		"items": _cart_items(cart, "Quotation Item"),
```

and in `_create_sales_order`:

```python
		"items": [
			dict(row, delivery_date=delivery_date, warehouse=get_source_warehouse(row["item_code"]))
			for row in _cart_items(cart, "Sales Order Item")
		],
```

Finally guard the order-level flag in `_create_sales_order`, replacing the `custom_has_mixed_boxes` entry:

```python
		**(
			{"custom_has_mixed_boxes": _has_mixed_boxes(cart)}
			if _writable("Sales Order", "custom_has_mixed_boxes")
			else {}
		),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_checkout_boxes`
Expected: PASS.

- [ ] **Step 5: Check nothing else broke**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: only the known PDF failure. `test_checkout.py` and `test_conversion.py` both exercise `_cart_items`.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/api/checkout.py upande_webstore/tests/test_checkout_boxes.py
git commit -m "fix(checkout): write box fields only where the site models them the same way"
```

---

### Task 6: Webstore Settings shows which source is in use

Three things silently exclude a box today and none of them say so: no rate, disabled, or never flagged. `get_box_types()` just returns a shorter list.

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json` (add `box_source_summary` to `field_order` after `default_lead_days`, and the field object)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js` (`refresh`)
- Test: `upande_webstore/tests/test_boxes_api.py`

**Interfaces:**
- Consumes: `api.boxes.describe_source()` from Task 4.
- Produces: an HTML field `box_source_summary` on Webstore Settings.

- [ ] **Step 1: Write the failing test**

Append to `TestBoxesApi` in `upande_webstore/tests/test_boxes_api.py`:

```python
	def test_the_settings_form_has_somewhere_to_render_the_summary(self):
		field = frappe.get_meta("Webstore Settings").get_field("box_source_summary")
		self.assertIsNotNone(field, "Webstore Settings has no box source panel")
		self.assertEqual(field.fieldtype, "HTML")

	def test_the_default_box_type_is_reported_so_the_panel_can_mark_it(self):
		from upande_webstore.api.boxes import describe_source

		make_box_type("Xpol", 350)
		settings = frappe.get_doc("Webstore Settings")
		settings.default_box_type = "Xpol"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			self.assertEqual(describe_source()["default_box_type"], "Xpol")
		finally:
			settings.default_box_type = ""
			settings.save(ignore_permissions=True)
			frappe.clear_cache()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_boxes_api`
Expected: FAIL — `Webstore Settings has no box source panel`.

- [ ] **Step 3: Add the field**

In `webstore_settings.json`, add `"box_source_summary"` to `field_order` immediately after `"default_lead_days"`, and add the field object next to the other packing fields:

```json
  {
   "fieldname": "box_source_summary",
   "fieldtype": "HTML",
   "label": "Box Types On This Site"
  },
```

- [ ] **Step 4: Render it**

In `webstore_settings.js`, add inside `refresh(frm)`:

```javascript
		frappe.call("upande_webstore.api.boxes.describe_source").then((r) => {
			frm.get_field("box_source_summary").$wrapper.html(boxSummary(r.message));
		});
```

And add this function alongside `report` at the bottom of the file:

```javascript
function boxSummary(data) {
	if (!data) return "";
	if (!data.doctype) {
		return `<div class="text-muted">${__(
			"This site has no box type source. Box packing stays inert until one exists — either Box Type records with a stem capacity, or Items with Is Box ticked and a pack rate."
		)}</div>`;
	}
	const rows = (data.usable || [])
		.map(
			(box) =>
				`<tr><td>${frappe.utils.escape_html(box.box_name)}</td>` +
				`<td class="text-right">${box.pack_rate}</td>` +
				`<td>${box.box_type === data.default_box_type ? __("default") : ""}</td></tr>`
		)
		.join("");
	const problems = (data.unusable || [])
		.map(
			(box) =>
				`<tr><td>${frappe.utils.escape_html(box.box_name)}</td>` +
				`<td colspan="2" class="text-muted">${box.reasons.join(", ")}</td></tr>`
		)
		.join("");
	return `
		<div class="text-muted" style="margin-bottom:.5rem">
			${__("Box types come from")} <b>${frappe.utils.escape_html(data.label)}</b>
		</div>
		<table class="table table-bordered table-sm">
			<thead><tr><th>${__("Box")}</th><th class="text-right">${__("Stems")}</th><th></th></tr></thead>
			<tbody>${rows || `<tr><td colspan="3" class="text-muted">${__("None usable yet.")}</td></tr>`}</tbody>
			${problems ? `<tbody><tr><th colspan="3">${__("Hidden from the storefront")}</th></tr>${problems}</tbody>` : ""}
		</table>`;
}
```

- [ ] **Step 5: Apply and run**

```bash
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_boxes_api
```

Expected: PASS.

- [ ] **Step 6: Look at it**

```bash
bench --site webstore.localhost browse /app/webstore-settings
```

Confirm the panel names the source and lists the boxes. This step is a real check, not a formality — the field renders only if `field_order` was edited correctly.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json \
        upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js \
        upande_webstore/tests/test_boxes_api.py
git commit -m "feat(desk): Webstore Settings names the box source and what it hides"
```

---

### Task 7: Documentation

**Files:**
- Modify: `README.md` (box packing section)
- Modify: `docs/superpowers/plans/2026-08-11-flower-trading-model.md` (tick what is done)

- [ ] **Step 1: Document the source resolution in the README**

Find the box packing section (`grep -n "box" README.md`) and add:

```markdown
### Where box types come from

The storefront reads box types from whichever representation your ERP already
runs, resolved per site:

1. **`Box Type` records** with a stem capacity above zero, if your site has that
   doctype and has filled it in. The capacity is the pack rate.
2. Otherwise **Items** with *Is Box* ticked and a *Pack Rate* above zero.
3. Otherwise nothing — box packing stays inert, whatever the settings say.

Webstore Settings → Boxes & Order Rules names which source is in use, lists the
usable boxes, and lists the ones being hidden with the reason (no rate entered,
disabled). This app never creates, migrates or takes ownership of a `Box Type`
doctype; it only reads one where a farm already has it.
```

- [ ] **Step 2: Tick the completed steps in the older plan**

`docs/superpowers/plans/2026-08-11-flower-trading-model.md` has every checkbox unticked despite the work being done. Tick the tasks whose code is now committed, so the next reader is not misled.

- [ ] **Step 3: Run the full suite one last time**

Run: `bench --site webstore.localhost run-tests --app upande_webstore`
Expected: only the known `test_invoice_pdf_for_own_invoice` failure.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-08-11-flower-trading-model.md
git commit -m "docs: box type source resolution"
```
