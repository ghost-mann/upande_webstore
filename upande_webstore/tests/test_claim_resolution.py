"""Claim resolution: actions, invoice lines, and the value adjustment.

See docs/superpowers/specs/2026-09-22-claim-resolution-and-value-adjustment-design.md
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services import roles as roles_service
from upande_webstore.tests.utils import (
	get_default_warehouse,
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

	def test_claimed_total_is_quantity_times_rate(self):
		"""A credit-note-style claim: 200 claimed at the invoice rate."""
		from upande_webstore.services.claim_lines import claimed_total

		rows = [
			{"claimed_qty": 200, "rate": 0.5},
			{"claimed_qty": 0, "rate": 999},
			{"claimed_qty": 3, "rate": 10},
		]

		self.assertEqual(claimed_total(rows), 130)

	def test_a_price_adjustment_totals_the_difference(self):
		"""Claimed Quantity × (Rate − New Unit Value): what was overpaid."""
		from upande_webstore.services.claim_lines import claimed_total

		rows = [
			{"claimed_qty": 200, "rate": 0.5, "new_rate": 0.3},
			{"claimed_qty": 0, "rate": 10, "new_rate": 1},
		]

		self.assertAlmostEqual(claimed_total(rows, price_adjustment=True), 40)

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

	def _line(self, **values):
		return {
			"item_code": "WS-CR-ITEM", "invoiced_qty": 10, "rate": 50,
			"invoiced_amount": 500, **values,
		}

	def test_proposed_total_is_summed_server_side(self):
		"""A client-supplied total is overwritten, never believed."""
		claim = self._claim()
		claim.append("lines", self._line(claimed_qty=2, claim_amount=77))
		claim.proposed_total = 99999
		claim.save(ignore_permissions=True)

		self.assertEqual(claim.proposed_total, 100)
		self.assertEqual(claim.lines[0].claim_amount, 100)

	def test_claiming_more_than_was_invoiced_is_refused(self):
		"""The reported bug: with the old "Claimed" tick left off, 11 of 10
		saved without complaint. There is no tick now; any quantity counts."""
		claim = self._claim()
		claim.append("lines", self._line(claimed_qty=11))

		with self.assertRaises(frappe.ValidationError):
			claim.save(ignore_permissions=True)

	def test_a_negative_quantity_is_refused(self):
		claim = self._claim()
		claim.append("lines", self._line(claimed_qty=-1))

		with self.assertRaises(frappe.ValidationError):
			claim.save(ignore_permissions=True)

	def test_a_price_adjustment_claim_totals_the_difference(self):
		claim = self._claim()
		claim.action = "Price Adjustment"
		claim.append("lines", self._line(claimed_qty=4, new_rate=30))
		claim.save(ignore_permissions=True)

		self.assertTrue(claim.is_price_adjustment)
		self.assertEqual(claim.proposed_total, 80)

	def test_a_new_unit_value_above_the_rate_is_refused(self):
		claim = self._claim()
		claim.action = "Price Adjustment"
		claim.append("lines", self._line(claimed_qty=4, new_rate=60))

		with self.assertRaises(frappe.ValidationError):
			claim.save(ignore_permissions=True)

	def test_a_new_unit_value_is_ignored_outside_a_price_adjustment(self):
		"""Credit Note is quantity-based: a stray unit value must neither count
		nor linger on the line looking as if it did."""
		claim = self._claim()
		claim.action = "Credit Note"
		claim.append("lines", self._line(claimed_qty=4, new_rate=30))
		claim.save(ignore_permissions=True)

		self.assertFalse(claim.is_price_adjustment)
		self.assertTrue(claim.requires_credit_note)
		self.assertEqual(claim.lines[0].new_rate, 0)
		self.assertEqual(claim.proposed_total, 200)

	def test_the_action_markers_are_not_taken_from_the_client(self):
		claim = self._claim()
		claim.action = "Replacement"
		claim.is_price_adjustment = 1
		claim.append("lines", self._line(claimed_qty=1, new_rate=10))
		claim.save(ignore_permissions=True)

		self.assertFalse(claim.is_price_adjustment)
		self.assertEqual(claim.proposed_total, 50)

	def test_lines_can_be_fetched_before_the_claim_is_saved(self):
		from upande_webstore.api.claims import get_document_lines

		rows = get_document_lines("CR Buyer Ltd", "Sales Invoice", self.invoice)

		self.assertEqual([r["item_code"] for r in rows], ["WS-CR-ITEM"])
		self.assertEqual(rows[0]["claimed_qty"], 0)

	def test_fetching_another_customers_lines_is_refused(self):
		from upande_webstore.api.claims import get_document_lines

		make_portal_user("cr.stranger@example.com", "CR Stranger Ltd")
		with self.assertRaises(frappe.ValidationError):
			get_document_lines("CR Stranger Ltd", "Sales Invoice", self.invoice)

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


class TestClaimActionMarkers(IntegrationTestCase):
	def test_the_markers_exist_on_the_action_master(self):
		meta = frappe.get_meta("Webstore Claim Action")

		self.assertEqual(meta.get_field("is_price_adjustment").fieldtype, "Check")
		self.assertEqual(meta.get_field("requires_credit_note").fieldtype, "Check")

	def test_the_shipped_actions_carry_their_markers(self):
		get = lambda name, field: frappe.db.get_value("Webstore Claim Action", name, field)

		self.assertEqual(get("Price Adjustment", "is_price_adjustment"), 1)
		self.assertEqual(get("Credit Note", "requires_credit_note"), 1)
		self.assertEqual(get("Credit Note", "is_price_adjustment"), 0)
		self.assertEqual(get("Replacement", "requires_credit_note"), 0)

	def test_new_unit_value_is_locked_unless_the_action_is_a_price_adjustment(self):
		field = frappe.get_meta("Webstore Claim Line").get_field("new_rate")

		self.assertEqual(field.label, "New Unit Value")
		self.assertIn("parent.is_price_adjustment", field.read_only_depends_on)

	def test_the_credit_note_field_shows_only_when_the_action_needs_it(self):
		field = frappe.get_meta("Webstore Claim").get_field("credit_note")

		self.assertIn("requires_credit_note", field.depends_on)


class TestDeliveryNoteClaims(IntegrationTestCase):
	"""Flowers rejected at delivery: the claim is about the delivery note."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CR-DN-ITEM")
		make_item_price("WS-CR-DN-ITEM", "Standard Selling", 50)
		set_stock("WS-CR-DN-ITEM", 100)
		make_portal_user("cr.dn@example.com", "CR DN Ltd")
		make_portal_user("cr.dn.other@example.com", "CR DN Other Ltd")
		cls.note = cls._delivery_note("CR DN Ltd")
		cls.theirs = cls._delivery_note("CR DN Other Ltd")

	@classmethod
	def _delivery_note(cls, customer):
		doc = frappe.get_doc({
			"doctype": "Delivery Note",
			"customer": customer,
			"company": frappe.defaults.get_global_default("company"),
			"selling_price_list": "Standard Selling",
			"items": [{
				"item_code": "WS-CR-DN-ITEM", "qty": 6, "rate": 50,
				"warehouse": get_default_warehouse(),
			}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc.name

	def setUp(self):
		frappe.set_user("Administrator")

	def _claim(self, note):
		doc = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "CR DN Ltd",
			"claim_type": frappe.get_all("Webstore Claim Type", pluck="name")[0],
			"description": "Rejected at the door.",
			"against_doctype": "Delivery Note",
			"against_document": note,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_a_claim_against_the_customers_delivery_note_saves(self):
		self.assertEqual(self._claim(self.note).against_doctype, "Delivery Note")

	def test_another_customers_delivery_note_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._claim(self.theirs)

	def test_fetch_copies_the_delivery_note_lines(self):
		from upande_webstore.api.claims import fetch_invoice_lines

		claim = self._claim(self.note)
		fetch_invoice_lines(claim.name)
		claim.reload()

		self.assertEqual(claim.lines[0].item_code, "WS-CR-DN-ITEM")
		self.assertEqual(claim.lines[0].invoiced_qty, 6)

	def test_the_claims_page_renders_for_a_customer_with_documents(self):
		"""The picker's rows are embedded with `tojson`; a raw date in them made
		/portal/claims a 500 for every customer with an invoice or delivery note.
		The claim-page tests only ever rendered /portal/claim, singular."""
		from frappe.app import make_form_dict
		from frappe.utils import set_request
		from frappe.website.serve import get_response

		frappe.set_user("cr.dn@example.com")
		try:
			set_request(method="GET", path="portal/claims")
			make_form_dict(frappe.local.request)
			response = get_response()
			html = frappe.safe_decode(response.get_data())
		finally:
			frappe.set_user("Administrator")

		self.assertEqual(response.status_code, 200)
		self.assertIn(self.note, html, "the delivery note should be offered in the picker")

	def test_the_desk_picker_offers_the_customers_delivery_notes(self):
		from upande_webstore.api.claims import claimable_document_query

		names = [r[0] for r in claimable_document_query(
			"Delivery Note", "", "name", 0, 20, {"customer": "CR DN Ltd"}
		)]

		self.assertIn(self.note, names)
		self.assertNotIn(self.theirs, names)


class TestClaimConnections(IntegrationTestCase):
	def _items(self, doctype):
		data = frappe.get_meta(doctype).get_dashboard_data()
		return data, [i for group in data.transactions for i in group["items"]]

	def test_claims_show_on_the_documents_they_point_at(self):
		for doctype, fieldname in (
			("Customer", "customer"),
			("Sales Invoice", "against_document"),
			("Delivery Note", "against_document"),
			("Contact", "contact_person"),
		):
			data, items = self._items(doctype)
			self.assertIn("Webstore Claim", items, f"no Claims connection on {doctype}")
			self.assertEqual(data.non_standard_fieldnames["Webstore Claim"], fieldname)

	def test_the_invoice_count_is_scoped_by_the_dynamic_link(self):
		data, _ = self._items("Sales Invoice")

		self.assertEqual(data.dynamic_links["against_document"], ["Sales Invoice", "against_doctype"])


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


class TestClaimPortalRender(IntegrationTestCase):
	"""The membership tests above only prove the field names are on the
	payload — they would keep passing even if the template never printed
	them, which is exactly how the missing render survived four reviews.
	These render the real /portal/claim route end to end and assert on the
	HTML the customer actually receives.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("cr.render@example.com", "CR Render Ltd")

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _claim(self, customer="CR Render Ltd"):
		claim_type = frappe.get_all("Webstore Claim Type", pluck="name")[0]
		doc = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": customer,
			"claim_type": claim_type,
			"description": "Two boxes crushed in transit.",
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def _render(self, claim_name):
		"""Render the real /portal/claim route, query string and all.

		`get_html_for_route` builds the request but never calls
		`make_form_dict`, so `frappe.form_dict` — what `claim.py` reads the
		`name` argument from — stays empty and the page 301s to
		/portal/claims before the template runs at all. Reproduce the same
		two-step pipeline the real WSGI app performs instead.
		"""
		from frappe.app import make_form_dict
		from frappe.utils import set_request
		from frappe.website.serve import get_response

		frappe.set_user("cr.render@example.com")
		try:
			set_request(method="GET", path=f"portal/claim?name={claim_name}")
			make_form_dict(frappe.local.request)
			response = get_response()
			self.assertEqual(
				response.status_code, 200,
				f"expected the claim page to render, got {response.status_code}",
			)
			return frappe.safe_decode(response.get_data())
		finally:
			frappe.set_user("Administrator")

	def test_a_non_credit_note_outcome_is_rendered(self):
		"""A claim settled as Replacement, with no credit note and no
		free-text resolution, must not fall back to "reviewing" — that was
		the whole bug: action and approved_total were fetched but never
		printed, so the only two other signals the template checked were
		both blank."""
		claim = self._claim()
		frappe.db.set_value(
			"Webstore Claim", claim.name,
			{"action": "Replacement", "approved_total": 400},
		)

		html = self._render(claim.name)

		self.assertIn("Replacement", html)
		expected = frappe.utils.fmt_money(400, currency=self._currency())
		self.assertIn(expected, html, "the approved total must be currency-formatted, not a bare float")
		self.assertNotIn("400.0<", html)
		self.assertNotIn(
			"reviewing this claim", html,
			"a settled claim with a non-credit-note action must not show the pending message",
		)

	def test_an_approved_total_of_zero_is_not_dropped(self):
		"""approved_total may legitimately be settled at zero (Goodwill, No
		action). A bare truthiness check on approved_total would make that
		figure disappear even though the claim was in fact decided."""
		claim = self._claim()
		frappe.db.set_value(
			"Webstore Claim", claim.name,
			{"action": "No action", "approved_total": 0},
		)

		html = self._render(claim.name)

		self.assertIn("No action", html)
		zero = frappe.utils.fmt_money(0, currency=self._currency())
		self.assertIn(zero, html, "an approved total of zero must still be rendered")
		self.assertNotIn("reviewing this claim", html)

	def test_the_description_renders_as_sanitised_html(self):
		"""A Text Editor, so tables pasted from Word survive — scripts do not."""
		claim = self._claim()
		frappe.db.set_value(
			"Webstore Claim", claim.name, "description",
			"<table><tr><td>Box 7</td></tr></table><script>alert(1)</script>",
		)

		html = self._render(claim.name)

		self.assertIn("<td>Box 7</td>", html)
		self.assertNotIn("alert(1)", html)

	def test_a_plain_text_description_keeps_its_line_breaks(self):
		"""Claims written before Description became a Text Editor."""
		claim = self._claim()
		frappe.db.set_value("Webstore Claim", claim.name, "description", "Line one\nLine two")

		html = self._render(claim.name)

		self.assertIn("Line one<br>Line two", html)

	def test_an_unresolved_claim_still_shows_the_pending_message(self):
		"""No regression: a claim with no action, no approved figure, no
		credit note and no resolution must still read as pending."""
		claim = self._claim()

		html = self._render(claim.name)

		self.assertIn("reviewing this claim", html)

	def test_the_internal_fields_are_never_rendered(self):
		"""proposed_total, the lines table and approval_note are not in the
		portal payload at all, and must never reach the customer's page."""
		claim = self._claim()
		frappe.db.set_value(
			"Webstore Claim", claim.name,
			{
				"action": "Discount on next order",
				"approved_total": 250,
				"proposed_total": 999,
				"approval_note": "Internal-only: settle low, buyer overstated damage.",
			},
		)

		html = self._render(claim.name)

		self.assertNotIn("999", html)
		self.assertNotIn("Internal-only", html)
		self.assertNotIn("overstated", html)

	def _currency(self):
		return frappe.get_cached_value(
			"Company", frappe.defaults.get_global_default("company"), "default_currency"
		)
