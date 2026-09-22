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
