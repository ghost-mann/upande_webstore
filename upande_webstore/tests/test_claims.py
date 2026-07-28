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
		from upande_webstore.api.claims import get_claim_options

		documents = get_claim_options()["documents"]
		invoices = documents.get("Sales Invoice", [])
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
