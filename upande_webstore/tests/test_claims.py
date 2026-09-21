import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def make_submitted_invoice(customer, item_code):
	company = frappe.defaults.get_global_default("company")
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": company,
			"selling_price_list": "Standard Selling",
			"due_date": frappe.utils.add_days(frappe.utils.nowdate(), 14),
			"items": [{"item_code": item_code, "qty": 1, "rate": 50}],
		}
	)
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


def offered_invoices():
	"""The Sales Invoice rows the claim picker would render for the session user."""
	from upande_webstore.api.claims import get_claim_options

	return get_claim_options()["documents"].get("Sales Invoice", [])


def offered_names():
	return [row["name"] for row in offered_invoices()]


def offered_row(name):
	return next((row for row in offered_invoices() if row["name"] == name), None)


class TestClaimScoping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CLM-ITEM")
		make_item_price("WS-CLM-ITEM", "Standard Selling", 50)
		set_stock("WS-CLM-ITEM", 50)
		make_portal_user("claim.mine@example.com", "Claim Mine Ltd")
		make_portal_user("claim.other@example.com", "Claim Other Ltd")
		cls.mine_invoice = make_submitted_invoice("Claim Mine Ltd", "WS-CLM-ITEM").name
		cls.other_invoice = make_submitted_invoice("Claim Other Ltd", "WS-CLM-ITEM").name

	def setUp(self):
		frappe.set_user("claim.mine@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_files_a_claim_against_own_invoice(self):
		from upande_webstore.api.claims import create_claim

		result = create_claim(
			"Damaged goods", "Two boxes crushed.", "Sales Invoice", self.mine_invoice
		)
		claim = frappe.get_doc("Webstore Claim", result["name"])
		self.assertEqual(claim.customer, "Claim Mine Ltd")
		self.assertEqual(claim.against_doctype, "Sales Invoice")
		self.assertEqual(claim.against_document, self.mine_invoice)
		self.assertEqual(claim.status, "Open")
		self.assertEqual(claim.raised_by, "claim.mine@example.com")

	def test_cannot_claim_against_another_customers_invoice(self):
		"""The reference used to be free text, so this was possible."""
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError):
			create_claim("Billing error", "Not mine.", "Sales Invoice", self.other_invoice)

	def test_error_does_not_confirm_the_other_document_exists(self):
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_claim("Billing error", "Not mine.", "Sales Invoice", self.other_invoice)
		self.assertIn("does not exist", str(ctx.exception))

	def test_nonexistent_document_rejected(self):
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError):
			create_claim("Other", "Ghost.", "Sales Invoice", "ACC-SINV-DOES-NOT-EXIST")

	def test_non_claimable_doctype_rejected(self):
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError):
			create_claim("Other", "Wrong type.", "Webstore Settings", "Webstore Settings")

	def test_claim_without_a_document_is_allowed(self):
		from upande_webstore.api.claims import create_claim

		result = create_claim("Other", "General complaint, no document.")
		claim = frappe.get_doc("Webstore Claim", result["name"])
		self.assertFalse(claim.against_document)

	def test_unknown_claim_type_rejected(self):
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError):
			create_claim("Nonsense type", "Body.")

	def test_description_required(self):
		from upande_webstore.api.claims import create_claim

		with self.assertRaises(frappe.ValidationError):
			create_claim("Other", "   ")

	def test_offered_documents_are_only_the_customers_own(self):
		invoices = offered_names()
		self.assertIn(self.mine_invoice, invoices)
		self.assertNotIn(self.other_invoice, invoices)

	def test_claim_list_is_scoped_to_the_customer(self):
		from upande_webstore.api.claims import create_claim, get_claims

		mine = create_claim("Short delivery", "One carton missing.")["name"]

		frappe.set_user("claim.other@example.com")
		other = create_claim("Short delivery", "Different customer.")["name"]
		other_names = [c["name"] for c in get_claims()]
		self.assertIn(other, other_names)
		self.assertNotIn(mine, other_names)

	def test_cannot_open_another_customers_claim(self):
		from upande_webstore.api.claims import create_claim, get_claim

		mine = create_claim("Other", "Private detail.")["name"]
		frappe.set_user("claim.other@example.com")
		with self.assertRaises(frappe.PermissionError):
			get_claim(mine)

	def test_validation_holds_when_written_from_the_desk(self):
		"""Scoping lives on the controller, so a desk edit cannot bypass it."""
		frappe.set_user("Administrator")
		claim = frappe.get_doc(
			{
				"doctype": "Webstore Claim",
				"customer": "Claim Mine Ltd",
				"claim_type": "Other",
				"description": "Written directly in the desk.",
				"against_doctype": "Sales Invoice",
				"against_document": self.other_invoice,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			claim.insert(ignore_permissions=True)


class TestClaimCreditNote(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CN-ITEM")
		make_item_price("WS-CN-ITEM", "Standard Selling", 60)
		set_stock("WS-CN-ITEM", 30)
		make_portal_user("cn.buyer@example.com", "Credit Note Buyer Ltd")
		make_portal_user("cn.other@example.com", "Credit Note Other Ltd")
		cls.invoice = make_submitted_invoice("Credit Note Buyer Ltd", "WS-CN-ITEM")

	def _credit_note(self, customer, return_against):
		note = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": customer,
				"company": frappe.defaults.get_global_default("company"),
				"selling_price_list": "Standard Selling",
				"is_return": 1,
				"return_against": return_against,
				"due_date": frappe.utils.add_days(frappe.utils.nowdate(), 14),
				"items": [{"item_code": "WS-CN-ITEM", "qty": -1, "rate": 60}],
			}
		)
		note.flags.ignore_permissions = True
		note.insert()
		note.submit()
		return note

	def _claim(self, customer="Credit Note Buyer Ltd"):
		claim = frappe.get_doc(
			{
				"doctype": "Webstore Claim",
				"customer": customer,
				"claim_type": "Short delivery",
				"description": "One carton short.",
			}
		)
		claim.flags.ignore_permissions = True
		claim.insert()
		return claim

	def test_team_can_link_a_credit_note(self):
		note = self._credit_note("Credit Note Buyer Ltd", self.invoice.name)
		claim = self._claim()
		claim.credit_note = note.name
		claim.status = "Resolved"
		claim.save(ignore_permissions=True)
		self.assertEqual(frappe.get_doc("Webstore Claim", claim.name).credit_note, note.name)

	def test_a_normal_invoice_is_not_accepted_as_a_credit_note(self):
		claim = self._claim()
		claim.credit_note = self.invoice.name
		with self.assertRaises(frappe.ValidationError) as ctx:
			claim.save(ignore_permissions=True)
		self.assertIn("not a credit note", str(ctx.exception))

	def test_credit_note_must_belong_to_the_same_customer(self):
		other_invoice = make_submitted_invoice("Credit Note Other Ltd", "WS-CN-ITEM")
		note = self._credit_note("Credit Note Other Ltd", other_invoice.name)
		claim = self._claim()
		claim.credit_note = note.name
		with self.assertRaises(frappe.ValidationError) as ctx:
			claim.save(ignore_permissions=True)
		self.assertIn("different customer", str(ctx.exception))

	def test_customer_sees_the_credit_note_on_their_claim(self):
		note = self._credit_note("Credit Note Buyer Ltd", self.invoice.name)
		claim = self._claim()
		claim.credit_note = note.name
		claim.resolution = "Credited in full."
		claim.save(ignore_permissions=True)

		frappe.set_user("cn.buyer@example.com")
		try:
			from upande_webstore.api.claims import get_claim

			seen = get_claim(claim.name)
			self.assertEqual(seen.credit_note, note.name)
			self.assertEqual(seen.resolution, "Credited in full.")
		finally:
			frappe.set_user("Administrator")


class TestClaimWindow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-WIN-ITEM")
		make_item_price("WS-WIN-ITEM", "Standard Selling", 30)
		set_stock("WS-WIN-ITEM", 40)
		make_portal_user("window.buyer@example.com", "Claim Window Ltd")

	def _invoice_dated(self, days_ago):
		"""Invoices must be created as Administrator: a Website User has no
		permission on accounts, which is the whole point of the portal."""
		previous = frappe.session.user
		frappe.set_user("Administrator")
		try:
			invoice = make_submitted_invoice("Claim Window Ltd", "WS-WIN-ITEM")
			frappe.db.set_value(
				"Sales Invoice", invoice.name, "posting_date",
				frappe.utils.add_days(frappe.utils.nowdate(), -days_ago),
			)
			frappe.db.commit()
			return invoice.name
		finally:
			frappe.set_user(previous)

	def setUp(self):
		frappe.set_user("window.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_only_sales_invoices_are_claimable(self):
		from upande_webstore.services.claims import CLAIMABLE_DOCTYPES

		self.assertEqual(list(CLAIMABLE_DOCTYPES), ["Sales Invoice"])

	def test_a_recent_invoice_is_offered_and_accepted(self):
		from upande_webstore.api.claims import create_claim

		recent = self._invoice_dated(2)
		self.assertTrue(offered_row(recent)["claimable"])
		result = create_claim("Damaged goods", "Two boxes crushed.", "Sales Invoice", recent)
		self.assertTrue(result["name"])

	def test_an_invoice_past_the_window_is_listed_but_not_claimable(self):
		"""Hiding it left the customer unable to tell an expired invoice from a
		missing one; it stays on the list, marked."""
		old = self._invoice_dated(20)
		row = offered_row(old)
		self.assertIsNotNone(row, "an out-of-window invoice must still be listed")
		self.assertFalse(row["claimable"])
		self.assertEqual(str(row["date"]), frappe.utils.add_days(frappe.utils.nowdate(), -20))

	def test_the_window_length_is_offered_to_the_page(self):
		from upande_webstore.api.claims import get_claim_options

		self.assertEqual(get_claim_options()["claim_window_days"], 14)

	def test_an_invoice_past_the_window_is_refused_if_submitted_anyway(self):
		from upande_webstore.api.claims import create_claim

		old = self._invoice_dated(20)
		with self.assertRaises(frappe.ValidationError) as ctx:
			create_claim("Billing error", "Too late.", "Sales Invoice", old)
		self.assertIn("claim window", str(ctx.exception))

	def test_the_window_is_configurable(self):
		from upande_webstore.api.claims import get_claim_options

		old = self._invoice_dated(20)
		frappe.set_user("Administrator")
		settings = frappe.get_doc("Webstore Portal Settings")
		settings.claim_window_days = 30
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		frappe.set_user("window.buyer@example.com")
		try:
			self.assertTrue(offered_row(old)["claimable"])
			self.assertEqual(get_claim_options()["claim_window_days"], 30)
		finally:
			frappe.set_user("Administrator")
			from upande_webstore.tests.utils import reset_portal_settings

			reset_portal_settings()


class TestClaimDeskEntry(IntegrationTestCase):
	"""A claim can be raised in the desk, not only from the portal.

	`customer` shipped as read_only AND reqd with no default and no fetch_from.
	Frappe's read_only is a form-level restriction, so the portal API and every
	test here — all of which insert server-side — were unaffected, while the
	desk's New Webstore Claim form had no way to fill the one field it could not
	save without. `raised_by` was read_only for the same reason.

	Both are set_only_once instead: supplied when the claim is created, fixed
	afterwards, so a portal-filed claim cannot have its customer or its origin
	rewritten later.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CLM-DESK-ITEM")
		make_item_price("WS-CLM-DESK-ITEM", "Standard Selling", 50)
		set_stock("WS-CLM-DESK-ITEM", 50)
		make_portal_user("claim.desk@example.com", "Claim Desk Ltd")
		cls.invoice = make_submitted_invoice("Claim Desk Ltd", "WS-CLM-DESK-ITEM").name

	def setUp(self):
		frappe.set_user("Administrator")

	def _claim_type(self):
		from upande_webstore.services.portal_settings import get_claim_types

		return get_claim_types()[0]

	def _new_claim(self, **overrides):
		doc = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "Claim Desk Ltd",
			"claim_type": self._claim_type(),
			"description": "Filed at the counter.",
			"against_doctype": "Sales Invoice",
			"against_document": self.invoice,
			**overrides,
		})
		doc.insert(ignore_permissions=True)
		return doc

	def test_customer_is_fillable_on_the_desk_form(self):
		"""read_only would leave the desk with a required field it cannot set."""
		field = frappe.get_meta("Webstore Claim").get_field("customer")
		self.assertTrue(field.reqd, "customer is still required")
		self.assertFalse(field.read_only, "customer cannot be filled in the desk")

	def test_raised_by_is_fillable_on_the_desk_form(self):
		field = frappe.get_meta("Webstore Claim").get_field("raised_by")
		self.assertFalse(field.read_only, "raised_by cannot be filled in the desk")

	def test_customer_cannot_be_switched_after_creation(self):
		field = frappe.get_meta("Webstore Claim").get_field("customer")
		self.assertTrue(field.set_only_once, "customer must be fixed once set")

	def test_raised_by_cannot_be_switched_after_creation(self):
		field = frappe.get_meta("Webstore Claim").get_field("raised_by")
		self.assertTrue(field.set_only_once, "raised_by must be fixed once set")

	def test_a_desk_claim_saves_and_keeps_its_customer(self):
		claim = self._new_claim()

		self.assertEqual(claim.customer, "Claim Desk Ltd")
		self.assertEqual(claim.status, "Open")
		self.assertTrue(claim.posting_date, "posting_date is still server-filled")

	def test_raised_by_still_defaults_to_the_session_user_when_left_blank(self):
		"""set_only_once must not stop validate() filling a blank raised_by."""
		claim = self._new_claim()

		self.assertEqual(claim.raised_by, "Administrator")

	def test_raised_by_is_honoured_when_supplied(self):
		claim = self._new_claim(raised_by="claim.desk@example.com")

		self.assertEqual(claim.raised_by, "claim.desk@example.com")

	def test_switching_the_customer_afterwards_is_refused(self):
		"""Deliberately a claim with no document reference.

		With one, validate_references() would refuse the switch anyway and the
		test would pass whether or not set_only_once is set. Without one, the
		only thing that can refuse it is set_only_once itself.
		"""
		claim = self._new_claim(against_doctype=None, against_document=None)
		make_portal_user("claim.desk2@example.com", "Claim Desk Two Ltd")

		claim.customer = "Claim Desk Two Ltd"

		with self.assertRaises(frappe.exceptions.ValidationError):
			claim.save(ignore_permissions=True)


class TestClaimTypeMaster(IntegrationTestCase):
	"""claim_type is a Link to a real master, so the desk gets a picker.

	It used to be Data: the list lived in Portal Settings and only the portal
	page rendered it as a <select>, so the desk form was a free-text box that
	could not show the configured types at all — the only feedback was the
	validation error after saving. A Select could not fix that, because its
	options are fixed in the doctype JSON while the list has to stay
	configurable.

	The Portal Settings table is now a selector over that master, and it gates
	the portal picker only. Validation asks whether the type exists, not
	whether it is currently offered, so narrowing the portal list cannot block
	the sales team from filing that type in the desk, nor stop an old claim of
	a retired type being re-saved.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CLM-TYPE-ITEM")
		make_item_price("WS-CLM-TYPE-ITEM", "Standard Selling", 50)
		set_stock("WS-CLM-TYPE-ITEM", 50)
		make_portal_user("claim.type@example.com", "Claim Type Ltd")
		cls.invoice = make_submitted_invoice("Claim Type Ltd", "WS-CLM-TYPE-ITEM").name

	def setUp(self):
		frappe.set_user("Administrator")
		from upande_webstore.tests.utils import reset_portal_settings

		reset_portal_settings()

	def _make_type(self, name, description=None):
		if not frappe.db.exists("Webstore Claim Type", name):
			frappe.get_doc({
				"doctype": "Webstore Claim Type",
				"claim_type": name,
				"description": description,
			}).insert(ignore_permissions=True)
		return name

	def _offer(self, *names):
		settings = frappe.get_doc("Webstore Portal Settings")
		settings.set("claim_types", [])
		for n in names:
			settings.append("claim_types", {"claim_type": n})
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

	def test_the_master_is_a_standalone_doctype(self):
		meta = frappe.get_meta("Webstore Claim Type")
		self.assertFalse(meta.istable, "the Link target cannot be a child table")

	def test_the_portal_selector_is_a_child_table_linking_to_the_master(self):
		meta = frappe.get_meta("Webstore Portal Claim Type")
		self.assertTrue(meta.istable)
		field = meta.get_field("claim_type")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Webstore Claim Type")

	def test_portal_settings_points_at_the_selector_not_the_master(self):
		field = frappe.get_meta("Webstore Portal Settings").get_field("claim_types")
		self.assertEqual(field.options, "Webstore Portal Claim Type")

	def test_claim_type_is_a_link_so_the_desk_can_offer_a_picker(self):
		"""The whole point: a Data field can never render a dropdown."""
		field = frappe.get_meta("Webstore Claim").get_field("claim_type")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Webstore Claim Type")
		self.assertTrue(field.reqd)

	def test_an_empty_selector_offers_every_master_record(self):
		from upande_webstore.services.portal_settings import get_claim_types

		self._make_type("WS Spoilage")
		self._offer()

		self.assertIn("WS Spoilage", get_claim_types())

	def test_a_populated_selector_narrows_the_offer(self):
		from upande_webstore.services.portal_settings import get_claim_types

		self._make_type("WS Offered")
		self._make_type("WS Retired")
		self._offer("WS Offered")

		offered = get_claim_types()
		self.assertIn("WS Offered", offered)
		self.assertNotIn("WS Retired", offered)

	def test_a_desk_claim_may_use_a_type_the_portal_no_longer_offers(self):
		"""Retiring a type from the portal must not block the sales team."""
		self._make_type("WS Offered")
		self._make_type("WS Retired")
		self._offer("WS Offered")

		claim = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "Claim Type Ltd",
			"claim_type": "WS Retired",
			"description": "Filed at the counter against a retired type.",
			"against_doctype": "Sales Invoice",
			"against_document": self.invoice,
		})
		claim.insert(ignore_permissions=True)

		self.assertEqual(claim.claim_type, "WS Retired")

	def test_a_type_that_does_not_exist_is_still_refused(self):
		claim = frappe.get_doc({
			"doctype": "Webstore Claim",
			"customer": "Claim Type Ltd",
			"claim_type": "WS Nonsense Type",
			"description": "Body.",
		})
		with self.assertRaises(frappe.exceptions.ValidationError):
			claim.insert(ignore_permissions=True)

	def test_the_shipped_types_are_seeded_as_master_records(self):
		from upande_webstore.services.portal_settings import SHIPPED_CLAIM_TYPES

		for name in SHIPPED_CLAIM_TYPES:
			self.assertTrue(
				frappe.db.exists("Webstore Claim Type", name),
				f"{name} was not seeded into the master",
			)
