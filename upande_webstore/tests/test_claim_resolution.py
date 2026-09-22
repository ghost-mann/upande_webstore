"""Claim resolution: actions, invoice lines, and the value adjustment.

See docs/superpowers/specs/2026-09-22-claim-resolution-and-value-adjustment-design.md
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services import roles as roles_service
from upande_webstore.tests.utils import (
	make_desk_user,
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
	silently restores the stored value (see
	`Document.validate_higher_perm_levels`). Asserting an exception would fail
	against correct behaviour.
	"""

	COMMERCE_ROLE = "WS Test Claim Commerce"
	FINANCE_ROLE = "WS Test Claim Finance"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("fa.buyer@example.com", "FA Buyer Ltd")

	def setUp(self):
		frappe.set_user("Administrator")
		self._users = []
		self._roles = []
		self._reconciled = False

	def tearDown(self):
		"""Unconditional, on every path: a leaked session user or a leaked
		Custom DocPerm would silently change the meaning of every test that
		runs after this one.

		The permission reset is skipped unless a test actually reconciled, and
		`_reconciled` is set *before* reconcile() is called so a half-finished
		grant is still cleaned up. It is the expensive half of this teardown and
		most tests in this class never touch a permission.
		"""
		frappe.set_user("Administrator")
		if self._reconciled:
			for doctype in ("Webstore Claim", *roles_service.PORTAL_DOCTYPES):
				frappe.permissions.reset_perms(doctype)
		for email in self._users:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		for role in self._roles:
			frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
		if self._reconciled or self._users or self._roles:
			frappe.clear_cache()

	def _role(self, name):
		"""A throwaway Role carrying nothing of its own, so the assertions can
		only be explained by what this feature granted it."""
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		self._roles.append(name)
		return name

	def _user(self, email, role):
		self._users.append(email)
		return make_desk_user(email, [role])

	def _reconcile(self, **role_lists):
		"""Drive the real grant path — reconcile() against an unsaved settings
		dict — rather than hand-writing a Custom DocPerm, so this test fails if
		the permlevel ever stops reaching the database."""
		settings = frappe._dict({
			field: [frappe._dict({"role": role}) for role in names]
			for field, names in role_lists.items()
		})
		self._reconciled = True
		roles_service.reconcile(settings)
		frappe.clear_cache()

	def _claim(self):
		"""No referenced invoice: this test is about the permlevel, and a
		reference would drag Sales Invoice read permissions into it."""
		claim_type = frappe.get_all("Webstore Claim Type", pluck="name")[0]
		doc = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "FA Buyer Ltd",
			"claim_type": claim_type,
			"description": "Short delivery.",
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

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
		self.assertEqual(grants["Webstore Claim#1"]["Accounts Manager"], ["read", "write"])

	def test_a_portal_role_reads_permlevel_1_but_never_writes_it(self):
		"""Commerce has to be able to see what finance decided.

		Frappe strips every permlevel-1 field from a user without permlevel-1
		read, so without this grant a Portal Manager opens a claim and finds
		Approved Total blank — which reads as "not approved yet" rather than
		"you may not see this". Read is not authority; write is.
		"""
		from upande_webstore.services.roles import desired_grants

		settings = frappe._dict({
			"portal_manager_roles": [frappe._dict({"role": "Sales User"})],
		})

		grants = desired_grants(settings)

		self.assertEqual(grants["Webstore Claim"]["Sales User"], ["create", "read", "write"])
		self.assertEqual(grants["Webstore Claim#1"]["Sales User"], ["read"])

	def test_no_other_role_list_grants_write_at_permlevel_1(self):
		"""The constraint that actually matters: widening any other list must
		never hand out the authority to change an approved value."""
		from upande_webstore.services.roles import desired_grants

		for field in ("catalogue_manager_roles", "order_manager_roles", "portal_manager_roles"):
			grants = desired_grants(frappe._dict({field: [frappe._dict({"role": "Sales User"})]}))
			self.assertNotIn(
				"write",
				grants.get("Webstore Claim#1", {}).get("Sales User", []),
				f"{field} must never grant write at permlevel 1",
			)

	def test_only_a_finance_role_can_change_the_approved_value(self):
		"""The end-to-end proof, and the only test here that reaches the
		database. The metadata and grant-shape tests above say the permlevel is
		declared and asked for; this one says Frappe actually enforces it on a
		real save, by a real user, through a Custom DocPerm this feature wrote.
		It is also the test that will notice if a future Frappe changes how a
		permlevel above 0 on a Custom DocPerm behaves.
		"""
		claim = self._claim()
		frappe.db.set_value("Webstore Claim", claim.name, "approved_total", 250)

		# Commerce: permlevel 0 on the claim through Portal Managers, and
		# nothing at permlevel 1.
		commerce_role = self._role(self.COMMERCE_ROLE)
		self._reconcile(portal_manager_roles=[commerce_role])
		commerce = self._user("fa.commerce@example.com", commerce_role)

		frappe.set_user(commerce)
		doc = frappe.get_doc("Webstore Claim", claim.name)
		doc.description = "Short delivery, three boxes."
		doc.approved_total = 9999
		doc.save()
		frappe.set_user("Administrator")

		self.assertEqual(
			frappe.db.get_value("Webstore Claim", claim.name, "approved_total"),
			250,
			"a role without permlevel 1 must not be able to move the approved value",
		)
		self.assertEqual(
			frappe.db.get_value("Webstore Claim", claim.name, "description"),
			"Short delivery, three boxes.",
			"and its permlevel 0 edit in the same save must still have gone through",
		)

		# Finance: permlevel 1 as well. It needs permlevel 0 too — a role
		# granted only permlevel 1 cannot open the claim at all — which is
		# exactly what the field's description tells an administrator.
		finance_role = self._role(self.FINANCE_ROLE)
		self._reconcile(
			portal_manager_roles=[commerce_role, finance_role],
			claim_finance_roles=[finance_role],
		)
		finance = self._user("fa.finance@example.com", finance_role)

		frappe.set_user(finance)
		doc = frappe.get_doc("Webstore Claim", claim.name)
		doc.approved_total = 400
		doc.save()
		frappe.set_user("Administrator")

		self.assertEqual(
			frappe.db.get_value("Webstore Claim", claim.name, "approved_total"),
			400,
			"the finance role must be able to set the value it is there to set",
		)

		# The other half of the same rule, and the one a permlevel makes easy
		# to get wrong: commerce must be able to *read* what finance decided.
		# apply_fieldlevel_read_permissions is what the desk form calls
		# (frappe/desk/form/load.py), and it deletes every permlevel-1 field
		# from a user without permlevel-1 read — leaving a blank that reads as
		# "not approved yet" rather than "not yours to see".
		frappe.set_user(commerce)
		seen = frappe.get_doc("Webstore Claim", claim.name)
		seen.apply_fieldlevel_read_permissions()
		seen_total = seen.get("approved_total")
		frappe.set_user("Administrator")

		self.assertEqual(
			seen_total,
			400,
			"commerce must see the approved value, not a field stripped to blank",
		)

	def test_the_portal_never_sees_the_approval_note(self):
		"""get_claim returns a projection, not the document.

		Frappe's own field-level read filtering does not run for a custom
		whitelisted method, so returning the Document would hand a logged-in
		buyer the internal finance commentary on their own claim.
		"""
		from upande_webstore.api.claims import CLAIM_FIELDS, get_claim

		claim = self._claim()
		frappe.db.set_value("Webstore Claim", claim.name, {
			"approved_total": 250,
			"approval_note": "Settle at 250; the third box turned up in the cold room.",
		})

		frappe.set_user("fa.buyer@example.com")
		try:
			seen = get_claim(claim.name)
		finally:
			frappe.set_user("Administrator")

		# Checked first, and deliberately: a Document is not a container, so
		# without this a regression to `return claim` fails with an opaque
		# TypeError from assertNotIn rather than saying what went wrong.
		self.assertIsInstance(seen, dict, "get_claim must return a projection, not the Document")
		self.assertNotIn("approval_note", CLAIM_FIELDS)
		self.assertNotIn("approval_note", seen)
		# and the projection is still the page's payload, not an empty shell
		self.assertEqual(seen.name, claim.name)
		self.assertEqual(seen.description, "Short delivery.")
