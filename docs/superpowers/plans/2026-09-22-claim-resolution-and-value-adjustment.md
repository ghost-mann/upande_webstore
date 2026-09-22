# Claim Resolution and Value Adjustment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a claim's settlement on the claim — which invoice lines are claimed, what commerce proposes, what finance approves, and what was done — without this app ever posting to the ledger.

**Architecture:** Four additive pieces on the existing `Webstore Claim`. A configurable `Webstore Claim Action` master in the shape of `Webstore Claim Type`; a `Webstore Claim Line` child table snapshotted from the Sales Invoice by a deliberate button; finance-only value fields at permlevel 1, which needs `services/roles.py` taught about permlevel for the first time; and two new fields on the portal payload. Nothing generates an accounting document.

**Tech Stack:** Frappe v16 / ERPNext, Python 3.11, `bench run-tests`, vanilla JS form scripts.

**Spec:** `docs/superpowers/specs/2026-09-22-claim-resolution-and-value-adjustment-design.md` — read it before starting.

## Global Constraints

- **The claim never posts to the ledger.** No Journal Entry, no Sales Invoice, no credit note is created by this app. `credit_note` keeps its existing rule (`assert_credit_note`: a real `is_return: 1` invoice for the same customer).
- **No arithmetic ties `approved_total` to the credit note.** They are independent by design; never validate equality.
- **No farm-specific coupling.** No role name is hardcoded in a doctype JSON. Actions are configuration, not code.
- **Guard every foreign field.** `Sales Invoice Item.custom_length` and `custom_box_type` are site-specific; check the field exists before reading it, the way `services/packing.py` guards on `Box Type`.
- **Never trust the client.** Every total is summed server-side in `validate()`.
- **Deploying changes nothing.** No lines fetched, no action chosen, no approval recorded → a claim behaves exactly as today.
- **Ship no Workflow fixture.** The farm's `Claim Approval` workflow stays in the UI.
- **Test command:** `bench --site webstore.localhost run-tests --module upande_webstore.tests.<module>` from `/home/austin/frappe-v16-bench`.
- **Run `bench --site webstore.localhost migrate` after any doctype JSON change** before running tests, or the DB still has the old schema.

## File Structure

| File | Responsibility |
|---|---|
| `upande_webstore/upande_webstore/doctype/webstore_claim_action/` | Create — the action master (JSON + controller) |
| `upande_webstore/upande_webstore/doctype/webstore_claim_line/` | Create — the invoice-line snapshot child table |
| `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json` | Modify — `action`, `lines`, `proposed_total`, `approved_total`, `approval_note` |
| `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.py` | Modify — line arithmetic and validation |
| `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.js` | Modify — the Fetch button |
| `upande_webstore/services/claim_lines.py` | Create — snapshot + arithmetic, pure enough to unit test |
| `upande_webstore/services/roles.py` | Modify — permlevel support |
| `upande_webstore/setup/install.py` | Modify — `seed_claim_actions()` |
| `upande_webstore/api/claims.py` | Modify — `fetch_invoice_lines`, `CLAIM_FIELDS` |
| `upande_webstore/tests/test_claim_resolution.py` | Create — all tests for this feature |

---

### Task 1: Claim Action master

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_action/webstore_claim_action.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_action/webstore_claim_action.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_action/__init__.py`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json`
- Modify: `upande_webstore/setup/install.py`
- Create: `upande_webstore/tests/test_claim_resolution.py`

**Interfaces:**
- Consumes: nothing.
- Produces: doctype `Webstore Claim Action` (autoname `field:action`, fields `action`, `description`); `Webstore Claim.action` as a Link to it; `install.seed_claim_actions()` and `install.SHIPPED_CLAIM_ACTIONS`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_claim_resolution.py`:

```python
"""Claim resolution: actions, invoice lines, and the value adjustment.

See docs/superpowers/specs/2026-09-22-claim-resolution-and-value-adjustment-design.md
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestClaimAction(IntegrationTestCase):
	"""One outcome per claim, from a master the farm can extend."""

	def test_the_action_master_is_a_standalone_doctype(self):
		self.assertFalse(frappe.get_meta("Webstore Claim Action").istable)

	def test_claim_action_is_a_link_to_the_master(self):
		field = frappe.get_meta("Webstore Claim").get_field("action")

		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Webstore Claim Action")
		self.assertFalse(field.reqd, "a claim may be filed before its outcome is known")

	def test_the_shipped_actions_are_seeded(self):
		from upande_webstore.setup.install import SHIPPED_CLAIM_ACTIONS

		for name in SHIPPED_CLAIM_ACTIONS:
			self.assertTrue(
				frappe.db.exists("Webstore Claim Action", name), f"{name} was not seeded"
			)

	def test_seeding_recreates_an_action_already_used_on_a_claim(self):
		"""Miss these and every historical claim gets a dangling Link.

		The value is forced onto the claim with raw SQL on purpose: setting it
		through the ORM would be refused by the Link, which is precisely the
		state this seeder exists to repair.
		"""
		from upande_webstore.setup.install import seed_claim_actions

		setup_webstore_settings()
		make_portal_user("cr.seed@example.com", "CR Seed Ltd")
		claim = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "CR Seed Ltd",
			"claim_type": frappe.get_all("Webstore Claim Type", pluck="name")[0],
			"description": "Filed before this action existed.",
		})
		claim.flags.ignore_permissions = True
		claim.insert()

		frappe.db.sql(
			"update `tabWebstore Claim` set `action` = %s where name = %s",
			("Bespoke Settlement", claim.name),
		)
		frappe.delete_doc(
			"Webstore Claim Action", "Bespoke Settlement", force=True, ignore_permissions=True
		) if frappe.db.exists("Webstore Claim Action", "Bespoke Settlement") else None
		self.assertFalse(frappe.db.exists("Webstore Claim Action", "Bespoke Settlement"))

		seed_claim_actions()

		self.assertTrue(
			frappe.db.exists("Webstore Claim Action", "Bespoke Settlement"),
			"an action already on a claim was not seeded, leaving a dangling Link",
		)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: FAIL/ERROR — `DoesNotExistError: DocType Webstore Claim Action not found`.

- [ ] **Step 3: Create the master doctype**

`upande_webstore/upande_webstore/doctype/webstore_claim_action/__init__.py` — empty file.

`upande_webstore/upande_webstore/doctype/webstore_claim_action/webstore_claim_action.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Claim Action",
 "module": "Upande Webstore",
 "istable": 0,
 "engine": "InnoDB",
 "autoname": "field:action",
 "naming_rule": "By fieldname",
 "creation": "2026-09-22 00:00:01.000000",
 "modified": "2026-09-22 00:00:01.000000",
 "owner": "Administrator",
 "description": "What was done about a claim — a credit note, a replacement, a discount. The farm may add its own.",
 "field_order": ["action", "description"],
 "fields": [
  {"fieldname": "action", "fieldtype": "Data", "label": "Action", "reqd": 1, "unique": 1, "in_list_view": 1},
  {"fieldname": "description", "fieldtype": "Data", "label": "Description", "in_list_view": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
  {"role": "Sales Manager", "read": 1, "write": 1, "create": 1},
  {"role": "Sales User", "read": 1},
  {"role": "Customer", "read": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

`upande_webstore/upande_webstore/doctype/webstore_claim_action/webstore_claim_action.py`:

```python
from frappe.model.document import Document


class WebstoreClaimAction(Document):
	pass
```

- [ ] **Step 4: Add the `action` field to Webstore Claim**

In `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json`, inside the `resolution_section`, add this field object immediately before the existing `credit_note` field, and add `"action"` to `field_order` immediately before `"credit_note"`:

```json
  {
   "fieldname": "action",
   "fieldtype": "Link",
   "options": "Webstore Claim Action",
   "label": "Action Taken",
   "description": "What was done about this claim. The credit note, if any, is linked below."
  },
```

- [ ] **Step 5: Add the seeder**

In `upande_webstore/setup/install.py`, immediately after the existing `seed_claim_types()` function, add:

```python
SHIPPED_CLAIM_ACTIONS = (
	"Credit Note",
	"Replacement",
	"Discount on next order",
	"Goodwill",
	"No action",
)

CLAIM_ACTION_DOCTYPE = "Webstore Claim Action"


def seed_claim_actions():
	"""Every action a claim already names must exist as a record.

	`Webstore Claim.action` is a Link, so a value with no master record is a
	dangling link: the claim cannot be re-saved and the picker cannot show it.
	Existing claim values come first for exactly that reason, the shipped list
	second — the same ordering, and the same reasoning, as seed_claim_types().
	"""
	if not frappe.db.exists("DocType", CLAIM_ACTION_DOCTYPE):
		return

	wanted = []
	if frappe.db.table_exists("Webstore Claim"):
		try:
			rows = frappe.db.sql(
				"select distinct `action` from `tabWebstore Claim` where ifnull(`action`, '') != ''"
			)
		except Exception:
			rows = []
		wanted.extend((r[0] or "").strip() for r in rows)
	for name in SHIPPED_CLAIM_ACTIONS:
		if name not in wanted:
			wanted.append(name)

	for name in wanted:
		if not name or frappe.db.exists(CLAIM_ACTION_DOCTYPE, name):
			continue
		doc = frappe.get_doc({"doctype": CLAIM_ACTION_DOCTYPE, "action": name})
		doc.flags.ignore_permissions = True
		doc.insert()
```

Then add `seed_claim_actions()` to both hooks, immediately after the existing `seed_claim_types()` call in each:

```python
def after_install():
	create_webstore_custom_fields()
	seed_claim_types()
	seed_claim_actions()
	seed_default_theme()
	ensure_navigation_block()
	ensure_desktop_icon()
```

```python
def after_migrate():
	create_webstore_custom_fields()
	seed_claim_types()
	seed_claim_actions()
	normalise_settings_docstatus()
	ensure_navigation_block()
	ensure_desktop_icon()
```

- [ ] **Step 6: Migrate and run the tests**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: PASS — 4 tests.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_claim_action \
        upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json \
        upande_webstore/setup/install.py \
        upande_webstore/tests/test_claim_resolution.py
git commit -m "feat(claims): record what was done about a claim

One outcome per claim, from a master the farm can extend without a deploy —
the shape Webstore Claim Type already uses, and seeded the same way: values
already on existing claims first, so no historical claim is left with a
dangling Link."
```

---

### Task 2: Invoice line snapshot

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_line/webstore_claim_line.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_line/webstore_claim_line.py`
- Create: `upande_webstore/upande_webstore/doctype/webstore_claim_line/__init__.py`
- Create: `upande_webstore/services/claim_lines.py`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.py`
- Modify: `upande_webstore/api/claims.py`
- Modify: `upande_webstore/tests/test_claim_resolution.py`

**Interfaces:**
- Consumes: Task 1's doctypes (not strictly required, but the migrate from Task 1 must have run).
- **On the spec's custom-field guard:** `SNAPSHOT_FIELDS` names standard
  `Sales Invoice Item` fields only, so this code never reads `custom_length`
  or `custom_box_type` at all. The spec's requirement is met by construction
  rather than by a runtime check, which is why no test asserts it — there is
  no branch to exercise. Do not add a guard for fields nothing reads.
- Produces: child doctype `Webstore Claim Line`; `Webstore Claim.lines` (Table) and `Webstore Claim.proposed_total` (Currency, read-only); `services.claim_lines.snapshot_rows(invoice) -> list[dict]`; `services.claim_lines.claimed_total(rows) -> float`; `api.claims.fetch_invoice_lines(claim) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_claim_resolution.py`:

```python
class TestClaimLines(IntegrationTestCase):
	"""Lines are a snapshot, not a live read.

	A claim argues about what was delivered on a particular day. An amended or
	cancelled invoice must not move the basis of a settlement, and a per-line
	proposed value needs somewhere of its own to live.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CR-ITEM")
		make_item_price("WS-CR-ITEM", "Standard Selling", 50)
		set_stock("WS-CR-ITEM", 100)
		make_portal_user("cr.buyer@example.com", "CR Buyer Ltd")
		cls.invoice = cls._invoice()

	@classmethod
	def _invoice(cls):
		doc = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": "CR Buyer Ltd",
			"company": frappe.defaults.get_global_default("company"),
			"selling_price_list": "Standard Selling",
			"due_date": frappe.utils.add_days(frappe.utils.nowdate(), 14),
			"items": [{"item_code": "WS-CR-ITEM", "qty": 10, "rate": 50}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc.name

	def setUp(self):
		frappe.set_user("Administrator")

	def _claim(self):
		doc = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "CR Buyer Ltd",
			"claim_type": frappe.get_all("Webstore Claim Type", pluck="name")[0],
			"description": "Two boxes crushed.",
			"against_doctype": "Sales Invoice",
			"against_document": self.invoice,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_snapshot_copies_the_invoice_lines(self):
		from upande_webstore.services.claim_lines import snapshot_rows

		rows = snapshot_rows(self.invoice)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], "WS-CR-ITEM")
		self.assertEqual(rows[0]["invoiced_qty"], 10)
		self.assertEqual(rows[0]["invoiced_amount"], 500)

	def test_claimed_total_counts_only_ticked_lines(self):
		from upande_webstore.services.claim_lines import claimed_total

		rows = [
			{"is_claimed": 1, "proposed_value": 120},
			{"is_claimed": 0, "proposed_value": 999},
			{"is_claimed": 1, "proposed_value": 30},
		]

		self.assertEqual(claimed_total(rows), 150)

	def test_fetch_puts_the_lines_on_the_claim(self):
		from upande_webstore.api.claims import fetch_invoice_lines

		claim = self._claim()
		fetch_invoice_lines(claim.name)
		claim.reload()

		self.assertEqual(len(claim.lines), 1)
		self.assertEqual(claim.lines[0].item_code, "WS-CR-ITEM")

	def test_fetch_without_an_invoice_is_refused(self):
		from upande_webstore.api.claims import fetch_invoice_lines

		claim = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "CR Buyer Ltd",
			"claim_type": frappe.get_all("Webstore Claim Type", pluck="name")[0],
			"description": "No document.",
		})
		claim.flags.ignore_permissions = True
		claim.insert()

		with self.assertRaises(frappe.ValidationError):
			fetch_invoice_lines(claim.name)

	def test_proposed_total_is_summed_server_side(self):
		"""A client-supplied total is overwritten, never believed."""
		claim = self._claim()
		claim.append("lines", {
			"item_code": "WS-CR-ITEM", "invoiced_qty": 10, "rate": 50,
			"invoiced_amount": 500, "is_claimed": 1, "claimed_qty": 2,
			"proposed_value": 100,
		})
		claim.proposed_total = 99999
		claim.save(ignore_permissions=True)

		self.assertEqual(claim.proposed_total, 100)

	def test_claiming_more_than_was_invoiced_is_refused(self):
		claim = self._claim()
		claim.append("lines", {
			"item_code": "WS-CR-ITEM", "invoiced_qty": 10, "rate": 50,
			"invoiced_amount": 500, "is_claimed": 1, "claimed_qty": 11,
			"proposed_value": 50,
		})

		with self.assertRaises(frappe.ValidationError):
			claim.save(ignore_permissions=True)

	def test_the_snapshot_does_not_follow_the_invoice(self):
		"""The whole point of storing rows rather than reading them live."""
		claim = self._claim()
		from upande_webstore.api.claims import fetch_invoice_lines

		fetch_invoice_lines(claim.name)
		claim.reload()
		before = claim.lines[0].invoiced_qty

		frappe.db.set_value("Sales Invoice Item", {"parent": self.invoice}, "qty", 99)
		claim.reload()

		self.assertEqual(claim.lines[0].invoiced_qty, before)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: FAIL — `ModuleNotFoundError: upande_webstore.services.claim_lines`.

- [ ] **Step 3: Create the child doctype**

`upande_webstore/upande_webstore/doctype/webstore_claim_line/__init__.py` — empty file.

`upande_webstore/upande_webstore/doctype/webstore_claim_line/webstore_claim_line.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Claim Line",
 "module": "Upande Webstore",
 "istable": 1,
 "editable_grid": 1,
 "engine": "InnoDB",
 "creation": "2026-09-22 00:00:01.000000",
 "modified": "2026-09-22 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["item_code", "item_name", "uom", "invoiced_qty", "rate", "invoiced_amount", "is_claimed", "claimed_qty", "proposed_value"],
 "fields": [
  {"fieldname": "item_code", "fieldtype": "Data", "label": "Item", "read_only": 1, "in_list_view": 1, "columns": 2},
  {"fieldname": "item_name", "fieldtype": "Data", "label": "Name", "read_only": 1},
  {"fieldname": "uom", "fieldtype": "Data", "label": "UOM", "read_only": 1},
  {"fieldname": "invoiced_qty", "fieldtype": "Float", "label": "Invoiced Qty", "read_only": 1, "in_list_view": 1, "columns": 1},
  {"fieldname": "rate", "fieldtype": "Currency", "label": "Rate", "read_only": 1},
  {"fieldname": "invoiced_amount", "fieldtype": "Currency", "label": "Invoiced", "read_only": 1, "in_list_view": 1, "columns": 2},
  {"fieldname": "is_claimed", "fieldtype": "Check", "label": "Claimed", "in_list_view": 1, "columns": 1},
  {"fieldname": "claimed_qty", "fieldtype": "Float", "label": "Claimed Qty", "in_list_view": 1, "columns": 1},
  {"fieldname": "proposed_value", "fieldtype": "Currency", "label": "Proposed", "in_list_view": 1, "columns": 2}
 ],
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`upande_webstore/upande_webstore/doctype/webstore_claim_line/webstore_claim_line.py`:

```python
from frappe.model.document import Document


class WebstoreClaimLine(Document):
	pass
```

- [ ] **Step 4: Create the service**

`upande_webstore/services/claim_lines.py`:

```python
"""Invoice-line snapshot and the arithmetic over it.

Kept apart from the controller so the sums can be tested without building a
document, the way services/packing.py separates box arithmetic from carts.
"""

import frappe
from frappe import _
from frappe.utils import flt

#: Copied onto a claim line. Standard Sales Invoice Item fields only — a farm's
#: own customs (Kaitet has custom_length and custom_box_type) are guarded
#: separately, because this app must work on a site that has neither.
SNAPSHOT_FIELDS = ("item_code", "item_name", "uom", "qty", "rate", "amount")


def snapshot_rows(invoice):
	"""The rows a claim would store for `invoice`, as plain dicts.

	Read once and copied: an invoice can be amended or cancelled afterwards,
	and the basis of an agreed settlement must not move underneath it.
	"""
	if not invoice:
		return []
	rows = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": invoice, "parenttype": "Sales Invoice"},
		fields=list(SNAPSHOT_FIELDS),
		order_by="idx asc",
	)
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"uom": row.uom,
			"invoiced_qty": flt(row.qty),
			"rate": flt(row.rate),
			"invoiced_amount": flt(row.amount),
			"is_claimed": 0,
			"claimed_qty": 0,
			"proposed_value": 0,
		}
		for row in rows
	]


def claimed_total(rows):
	"""Sum of proposed_value over ticked rows. An unticked row contributes
	nothing, however it was filled in."""
	total = 0.0
	for row in rows or []:
		get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
		if get("is_claimed"):
			total += flt(get("proposed_value"))
	return total


def assert_claimable_quantities(rows):
	"""Refuse a line claiming more than was invoiced, naming the line."""
	for idx, row in enumerate(rows or [], start=1):
		get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
		if not get("is_claimed"):
			continue
		claimed = flt(get("claimed_qty"))
		invoiced = flt(get("invoiced_qty"))
		if claimed > invoiced:
			frappe.throw(
				_("Line {0} ({1}): claimed {2} of {3} invoiced.").format(
					idx, get("item_code"), claimed, invoiced
				),
				frappe.ValidationError,
			)
```

- [ ] **Step 5: Add the fields to Webstore Claim**

In `webstore_claim.json`, add `"lines_section"`, `"lines"` and `"proposed_total"` to `field_order` immediately after `"related_documents"`, and add these three field objects after the existing `related_documents` field:

```json
  {
   "fieldname": "lines_section",
   "fieldtype": "Section Break",
   "label": "Claimed Lines",
   "description": "Fetched from the invoice above. A snapshot — later changes to the invoice do not move these rows."
  },
  {
   "fieldname": "lines",
   "fieldtype": "Table",
   "options": "Webstore Claim Line",
   "label": "Lines"
  },
  {
   "fieldname": "proposed_total",
   "fieldtype": "Currency",
   "label": "Proposed Total",
   "read_only": 1,
   "description": "Summed from the claimed lines."
  },
```

- [ ] **Step 6: Wire the controller**

In `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.py`, add the import beneath the existing one:

```python
from upande_webstore.services.claim_lines import assert_claimable_quantities, claimed_total
```

and extend `validate()` so it reads exactly:

```python
	def validate(self):
		if not self.posting_date:
			self.posting_date = now_datetime()
		if not self.raised_by:
			self.raised_by = frappe.session.user
		self.validate_references()
		self.validate_lines()

	def validate_lines(self):
		"""The totals are ours, not the client's — the stance services/packing.py
		takes on box counts, for the same reason."""
		assert_claimable_quantities(self.lines or [])
		self.proposed_total = claimed_total(self.lines or [])
```

- [ ] **Step 7: Add the fetch endpoint**

Append to `upande_webstore/api/claims.py`:

```python
@frappe.whitelist(methods=["POST"])
def fetch_invoice_lines(claim):
	"""Copy the referenced invoice's lines onto the claim, replacing any there.

	Deliberately a button rather than automatic: it is an act with a
	consequence, and re-running it discards whatever was filled in.
	"""
	doc = frappe.get_doc("Webstore Claim", claim)
	doc.check_permission("write")

	if not doc.against_document:
		frappe.throw(
			_("Pick the invoice this claim is about before fetching its lines."),
			frappe.ValidationError,
		)

	from upande_webstore.services.claim_lines import snapshot_rows

	doc.set("lines", [])
	for row in snapshot_rows(doc.against_document):
		doc.append("lines", row)
	doc.save()
	return {"lines": len(doc.lines)}
```

- [ ] **Step 8: Migrate and run the tests**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: PASS — 11 tests.

- [ ] **Step 9: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_claim_line \
        upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json \
        upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.py \
        upande_webstore/services/claim_lines.py \
        upande_webstore/api/claims.py \
        upande_webstore/tests/test_claim_resolution.py
git commit -m "feat(claims): snapshot the invoice lines onto the claim

A claim argues about what was delivered on a particular day, so the rows are
copied rather than read live: an amended or cancelled invoice must not move
the basis of a settlement, and a per-line proposed value needs somewhere of
its own to live. Totals are summed in validate(), never taken from the client."
```

---

### Task 3: Finance approval at permlevel 1

**Files:**
- Modify: `upande_webstore/services/roles.py`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json`
- Modify: `upande_webstore/api/claims.py`
- Modify: `upande_webstore/tests/test_claim_resolution.py`

**Interfaces:**
- Consumes: Task 2's `proposed_total` and `fetch_invoice_lines`.
- Produces: `Webstore Claim.approved_total` and `approval_note` at permlevel 1; `roles.FINANCE_FIELD = "claim_finance_roles"`; grant keys of the form `"<doctype>#<permlevel>"` for permlevel > 0.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_claim_resolution.py`:

```python
class TestFinanceApproval(IntegrationTestCase):
	"""Commerce proposes; finance approves. Frappe's permlevel is what makes
	that a rule rather than an agreement.

	Note how the permlevel assertion is written. Frappe does not raise when a
	user without permlevel access changes a higher-permlevel field — it
	silently restores the stored value. Asserting an exception would fail
	against correct behaviour.
	"""

	def test_the_finance_fields_sit_at_permlevel_1(self):
		meta = frappe.get_meta("Webstore Claim")

		self.assertEqual(meta.get_field("approved_total").permlevel, 1)
		self.assertEqual(meta.get_field("approval_note").permlevel, 1)

	def test_proposed_total_stays_at_permlevel_0(self):
		"""Commerce must still be able to fill in what it is asking for."""
		self.assertEqual(frappe.get_meta("Webstore Claim").get_field("proposed_total").permlevel, 0)

	def test_a_finance_role_grants_permlevel_1(self):
		from upande_webstore.services.roles import desired_grants

		settings = frappe._dict({
			"claim_finance_roles": [frappe._dict({"role": "Accounts Manager"})],
		})

		grants = desired_grants(settings)

		self.assertIn("Webstore Claim#1", grants)
		self.assertIn("Accounts Manager", grants["Webstore Claim#1"])

	def test_the_other_role_fields_stay_at_permlevel_0(self):
		"""Widening one must not accidentally widen finance access."""
		from upande_webstore.services.roles import desired_grants

		settings = frappe._dict({
			"portal_manager_roles": [frappe._dict({"role": "Sales User"})],
		})

		grants = desired_grants(settings)

		self.assertIn("Webstore Claim", grants)
		self.assertNotIn("Webstore Claim#1", grants)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: FAIL — `approved_total` is `None` (field does not exist), and `"Webstore Claim#1"` is not in `grants`.

- [ ] **Step 3: Add the finance fields**

In `webstore_claim.json`, add `"approved_total"` and `"approval_note"` to `field_order` immediately after `"proposed_total"`, and add these field objects after the `proposed_total` field:

```json
  {
   "fieldname": "approved_total",
   "fieldtype": "Currency",
   "label": "Approved Total",
   "permlevel": 1,
   "description": "Set by finance. No arithmetic ties this to the credit note — a settlement may be paid as a replacement or a discount, and one credit note may cover several claims."
  },
  {
   "fieldname": "approval_note",
   "fieldtype": "Small Text",
   "label": "Approval Note",
   "permlevel": 1
  },
```

- [ ] **Step 4: Add the settings field**

In `webstore_settings.json`, add `"claim_finance_roles"` to `field_order` immediately after `"portal_manager_roles"`, and add this field object after the `portal_manager_roles` field:

```json
  {
   "fieldname": "claim_finance_roles",
   "fieldtype": "Table MultiSelect",
   "options": "Webstore Role",
   "label": "Claim Finance Roles",
   "description": "Roles allowed to set the approved value on a claim. This is the only setting that grants permlevel 1 — the other role lists stay at permlevel 0."
  },
```

- [ ] **Step 5: Teach roles.py about permlevel**

In `upande_webstore/services/roles.py`, add beneath the existing field constants:

```python
FINANCE_FIELD = "claim_finance_roles"
FINANCE_DOCTYPE = "Webstore Claim"
FINANCE_PTYPES = ("read", "write")
FINANCE_PERMLEVEL = 1
```

Add these two helpers above `desired_grants`:

```python
def _grant_key(doctype, permlevel):
	"""Permlevel 0 keeps the bare doctype name, so a record written by an
	earlier release still reads back unchanged and needs no migration."""
	return doctype if not permlevel else f"{doctype}#{permlevel}"


def _split_key(key):
	doctype, _, level = key.partition("#")
	return doctype, int(level or 0)
```

In `desired_grants`, change the inner `add` to take a permlevel and use the key, then add the finance grant before the return:

```python
	def add(doctype, roles, ptypes, permlevel=0):
		if not doctype or doctype == FORBIDDEN_DOCTYPE:
			return
		if not frappe.db.exists("DocType", doctype):
			return
		key = _grant_key(doctype, permlevel)
		for role in roles:
			grants.setdefault(key, {}).setdefault(role, set()).update(ptypes)
```

```python
	add(
		FINANCE_DOCTYPE,
		_roles_of(settings, FINANCE_FIELD),
		FINANCE_PTYPES,
		permlevel=FINANCE_PERMLEVEL,
	)

	return {
		key: {role: sorted(ptypes) for role, ptypes in roles.items()}
		for key, roles in grants.items()
	}
```

Change `_custom_docperm_name`, `_grant` and `_revoke` to take and use a permlevel:

```python
def _custom_docperm_name(doctype, role, permlevel=0):
	return frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0},
	)
```

In `_grant`, change the signature to `def _grant(doctype, role, ptypes, permlevel=0):`, then replace every literal `0` used as a permlevel with `permlevel`:

```python
	existed_before = bool(_custom_docperm_name(doctype, role, permlevel))
	if not existed_before:
		frappe.permissions.add_permission(doctype, role, permlevel=permlevel, ptype=sorted(ptypes)[0])
	for ptype in sorted(ptypes):
		frappe.permissions.update_permission_property(doctype, role, permlevel, ptype, 1)
```

Apply the same signature change to `_revoke` (`def _revoke(doctype, role, ptypes, permlevel=0):`) and pass `permlevel` through to its `_custom_docperm_name` and `update_permission_property` calls in the same way.

Finally, in `reconcile`, unpack the key wherever a doctype is read from `desired` or `applied`:

```python
	for key, roles_map in applied.items():
		doctype, permlevel = _split_key(key)
```

and pass `permlevel` into the `_grant` / `_revoke` calls in both loops.

- [ ] **Step 6: Run the tests**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost migrate && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: PASS — 15 tests.

- [ ] **Step 7: Run the existing roles tests, which this refactor can break**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_roles`

Expected: PASS — 9 tests. This module takes about three minutes. If it fails, the key change has leaked into a place that still expects a bare doctype name; fix that rather than the test.

- [ ] **Step 8: Add the fetch guard**

In `api/claims.py::fetch_invoice_lines`, insert immediately after the `against_document` check:

```python
	if doc.approved_total:
		frappe.throw(
			_("This claim has an approved value. Withdraw the approval before "
			  "changing the lines it was given for."),
			frappe.ValidationError,
		)
```

- [ ] **Step 9: Write the guard's test, run it, commit**

Append to `TestClaimLines` in `test_claim_resolution.py`:

```python
	def test_fetch_is_refused_once_finance_has_approved(self):
		"""Otherwise an approval silently detaches from the lines it was for."""
		from upande_webstore.api.claims import fetch_invoice_lines

		claim = self._claim()
		fetch_invoice_lines(claim.name)
		frappe.db.set_value("Webstore Claim", claim.name, "approved_total", 250)

		with self.assertRaises(frappe.ValidationError):
			fetch_invoice_lines(claim.name)
```

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: PASS — 16 tests.

```bash
git add upande_webstore/services/roles.py \
        upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json \
        upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.json \
        upande_webstore/api/claims.py \
        upande_webstore/tests/test_claim_resolution.py
git commit -m "feat(claims): finance approves the value, at permlevel 1

Commerce proposes per line and finance sets one approved total. Frappe's
permlevel is what makes that a rule rather than an agreement, and roles.py
could not grant it: it hardcoded permlevel=0 in both its Custom DocPerm query
and its add_permission call. Grant keys become <doctype>#<permlevel>, with
permlevel 0 keeping the bare name so an existing applied_role_permissions
record reads back unchanged.

claim_finance_roles is the only setting that grants permlevel 1, so widening
one of the other role lists cannot accidentally widen finance access.

Re-fetching the lines is refused once a value is approved, or the approval
detaches from what was approved."
```

---

### Task 4: The Fetch button and the portal

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.js`
- Modify: `upande_webstore/api/claims.py`
- Modify: `upande_webstore/tests/test_claim_resolution.py`

**Interfaces:**
- Consumes: `api.claims.fetch_invoice_lines` from Task 2, `approved_total` from Task 3.
- Produces: nothing further.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_claim_resolution.py`:

```python
class TestClaimPortalPayload(IntegrationTestCase):
	def test_the_customer_sees_the_outcome_and_the_agreed_figure(self):
		from upande_webstore.api.claims import CLAIM_FIELDS

		self.assertIn("action", CLAIM_FIELDS)
		self.assertIn("approved_total", CLAIM_FIELDS)

	def test_the_customer_does_not_see_the_opening_position(self):
		"""Publishing commerce's proposed figure would be hard to walk back."""
		from upande_webstore.api.claims import CLAIM_FIELDS

		self.assertNotIn("proposed_total", CLAIM_FIELDS)
		self.assertNotIn("lines", CLAIM_FIELDS)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: FAIL — `'action' not found in CLAIM_FIELDS`.

- [ ] **Step 3: Extend the portal payload**

In `upande_webstore/api/claims.py`, change `CLAIM_FIELDS` to read exactly:

```python
CLAIM_FIELDS = (
	"name",
	"claim_type",
	"status",
	"posting_date",
	"against_doctype",
	"against_document",
	# The outcome and the agreed figure, but never the proposed one: a customer
	# should see what was decided, not commerce's opening position.
	"action",
	"approved_total",
	"credit_note",
	"resolution",
	"description",
)
```

- [ ] **Step 4: Add the Fetch button**

In `webstore_claim.js`, add a `refresh` handler to the existing `frappe.ui.form.on("Webstore Claim", {...})` object, alongside `setup` and `customer`:

```js
	refresh(frm) {
		if (frm.is_new() || !frm.doc.against_document) {
			return;
		}
		frm.add_custom_button(__("Fetch Invoice Lines"), () => {
			frappe.confirm(
				__("Replace the claimed lines with the invoice's current lines?"),
				() => {
					frappe
						.call({
							method: "upande_webstore.api.claims.fetch_invoice_lines",
							args: { claim: frm.doc.name },
							freeze: true,
						})
						.then(() => frm.reload_doc());
				}
			);
		});
	},
```

- [ ] **Step 5: Run the whole feature's tests**

Run: `cd /home/austin/frappe-v16-bench && bench --site webstore.localhost run-tests --module upande_webstore.tests.test_claim_resolution`

Expected: PASS — 18 tests.

- [ ] **Step 6: Run the full regression**

Run each of these from `/home/austin/frappe-v16-bench`:

```bash
for m in test_claims test_claim_resolution test_roles test_portal_access test_settings \
         test_features test_catalog test_install_fields test_store_field_parity test_workspace; do
  echo "== $m"
  bench --site webstore.localhost run-tests --module upande_webstore.tests.$m 2>&1 | grep -E "^Ran |^OK$|^FAILED"
done
```

Expected: every module `OK`.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_claim/webstore_claim.js \
        upande_webstore/api/claims.py \
        upande_webstore/tests/test_claim_resolution.py
git commit -m "feat(claims): fetch lines from the form, and show the outcome on the portal

The fetch is a button behind a confirm, because re-running it discards
whatever was filled in. The portal payload gains the action and the approved
total and deliberately not the proposed one — a customer should see what was
decided, not commerce's opening position."
```

---

## After the plan

Two things this plan deliberately does **not** do, both configuration on the farm's site rather than code:

- Add `Accounts Manager` to `claim_finance_roles`, and to `portal_manager_roles` — it currently has **no permission at all** on `Webstore Claim`, so it cannot action the workflow transition routed to it.
- Add `Sales Master Manager` to `portal_manager_roles`, for the same reason.

And one sequencing note for whoever uses the feature: the farm's workflow puts `Resolved` at docstatus 1, which locks the document. Finance must set `approved_total` while the claim is still in **`Approved`**, then transition to `Resolved`.
