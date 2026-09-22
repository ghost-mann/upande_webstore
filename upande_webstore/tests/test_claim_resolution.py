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

	def test_fetch_is_refused_once_finance_has_approved(self):
		"""Otherwise an approval silently detaches from the lines it was for."""
		from upande_webstore.api.claims import fetch_invoice_lines

		claim = self._claim()
		fetch_invoice_lines(claim.name)
		frappe.db.set_value("Webstore Claim", claim.name, "approved_total", 250)

		with self.assertRaises(frappe.ValidationError):
			fetch_invoice_lines(claim.name)

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
