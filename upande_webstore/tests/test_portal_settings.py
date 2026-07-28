import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


def reset_portal_settings():
	doc = frappe.get_doc("Webstore Portal Settings")
	for fieldname in (
		"landing_page",
		"welcome_note",
		"support_note",
		"spend_months",
		"recent_orders_count",
		"top_items_count",
		"statement_default_days",
		"max_attachment_mb",
	):
		doc.set(fieldname, None)
	doc.quotation_accept_requires_po = 0
	doc.require_claim_document = 0
	doc.allow_invoice_pdf = 1
	doc.allow_claim_attachments = 1
	doc.allow_profile_edit = 1
	doc.allow_address_edit = 1
	doc.set("claim_types", [])
	doc.save(ignore_permissions=True)
	frappe.clear_cache()
	return doc


def set_portal(**values):
	doc = frappe.get_doc("Webstore Portal Settings")
	for key, value in values.items():
		doc.set(key, value)
	doc.save(ignore_permissions=True)
	frappe.clear_cache()
	return doc


class TestPortalSettingsDefaults(IntegrationTestCase):
	def setUp(self):
		reset_portal_settings()

	def test_unset_matches_what_the_pages_used_to_hardcode(self):
		"""An unconfigured site must behave exactly as before this doctype existed."""
		from upande_webstore.services import portal_settings as ps

		self.assertEqual(ps.get_int("spend_months"), 12)
		self.assertEqual(ps.get_int("recent_orders_count"), 6)
		self.assertEqual(ps.get_int("top_items_count"), 5)
		self.assertEqual(ps.get_int("statement_default_days"), 90)
		self.assertTrue(ps.is_on("allow_invoice_pdf"))
		self.assertTrue(ps.is_on("allow_profile_edit"))
		self.assertFalse(ps.is_on("require_claim_document"))

	def test_unknown_setting_is_a_programming_error(self):
		from upande_webstore.services import portal_settings as ps

		with self.assertRaises(ValueError):
			ps.get("no_such_setting")

	def test_zero_falls_back_rather_than_emptying_the_page(self):
		from upande_webstore.services import portal_settings as ps

		set_portal(recent_orders_count=0)
		self.assertEqual(ps.get_int("recent_orders_count"), 6)

	def test_configured_values_win(self):
		from upande_webstore.services import portal_settings as ps

		set_portal(spend_months=6, recent_orders_count=3, statement_default_days=30)
		self.assertEqual(ps.get_int("spend_months"), 6)
		self.assertEqual(ps.get_int("recent_orders_count"), 3)
		self.assertEqual(ps.get_int("statement_default_days"), 30)

	def test_out_of_range_rejected(self):
		doc = frappe.get_doc("Webstore Portal Settings")
		doc.spend_months = 99
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestPortalClaimTypes(IntegrationTestCase):
	def setUp(self):
		reset_portal_settings()

	def test_empty_table_uses_the_shipped_list(self):
		from upande_webstore.services.portal_settings import SHIPPED_CLAIM_TYPES, get_claim_types

		self.assertEqual(get_claim_types(), SHIPPED_CLAIM_TYPES)

	def test_configured_types_replace_the_shipped_list(self):
		from upande_webstore.services.portal_settings import get_claim_types

		doc = frappe.get_doc("Webstore Portal Settings")
		doc.append("claim_types", {"claim_type": "Stem length short"})
		doc.append("claim_types", {"claim_type": "Cold chain break"})
		doc.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(get_claim_types(), ("Stem length short", "Cold chain break"))

	def test_duplicate_types_rejected(self):
		doc = frappe.get_doc("Webstore Portal Settings")
		doc.append("claim_types", {"claim_type": "Damaged goods"})
		doc.append("claim_types", {"claim_type": "damaged goods"})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestPortalSettingsEnforcement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		from upande_webstore.tests.utils import make_portal_user

		make_portal_user("ps.buyer@example.com", "Portal Settings Buyer Ltd")

	def setUp(self):
		frappe.set_user("Administrator")
		reset_portal_settings()
		frappe.set_user("ps.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		reset_portal_settings()

	def test_claim_type_must_be_one_of_the_configured_types(self):
		from upande_webstore.api.claims import create_claim

		frappe.set_user("Administrator")
		doc = frappe.get_doc("Webstore Portal Settings")
		doc.append("claim_types", {"claim_type": "Cold chain break"})
		doc.save(ignore_permissions=True)
		frappe.clear_cache()
		frappe.set_user("ps.buyer@example.com")

		# the shipped type is no longer offered, so it must be refused
		with self.assertRaises(frappe.ValidationError):
			create_claim("Damaged goods", "Should be rejected.")
		result = create_claim("Cold chain break", "Arrived warm.")
		self.assertTrue(result["name"])

	def test_require_claim_document_is_enforced(self):
		from upande_webstore.api.claims import create_claim

		frappe.set_user("Administrator")
		set_portal(require_claim_document=1)
		frappe.set_user("ps.buyer@example.com")

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_claim("Other", "No document given.")
		self.assertIn("pick the order", str(ctx.exception))

	def test_claim_allowed_without_document_when_not_required(self):
		from upande_webstore.api.claims import create_claim

		self.assertTrue(create_claim("Other", "No document needed.")["name"])

	def test_invoice_pdf_can_be_switched_off(self):
		from upande_webstore.api.portal import download_invoice_pdf

		frappe.set_user("Administrator")
		set_portal(allow_invoice_pdf=0)
		frappe.set_user("ps.buyer@example.com")

		with self.assertRaises(frappe.PermissionError):
			download_invoice_pdf("ACC-SINV-DOES-NOT-MATTER")

	def test_profile_edit_can_be_switched_off(self):
		from upande_webstore.api.account import update_profile

		frappe.set_user("Administrator")
		set_portal(allow_profile_edit=0)
		frappe.set_user("ps.buyer@example.com")

		with self.assertRaises(frappe.PermissionError):
			update_profile("New Name", "0700000000")

	def test_address_edit_can_be_switched_off(self):
		from upande_webstore.api.account import add_address

		frappe.set_user("Administrator")
		set_portal(allow_address_edit=0)
		frappe.set_user("ps.buyer@example.com")

		with self.assertRaises(frappe.PermissionError):
			add_address("Depot", "Line 1", "Nairobi", "Kenya")


class TestPortalLanding(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		reset_portal_settings()

	def tearDown(self):
		reset_portal_settings()

	def test_dashboard_landing_does_not_redirect(self):
		from upande_webstore.services.portal_settings import get_landing_route

		set_portal(landing_page="Dashboard")
		self.assertIsNone(get_landing_route())

	def test_configured_landing_page_is_used(self):
		from upande_webstore.services.portal_settings import get_landing_route

		set_portal(landing_page="Orders")
		self.assertEqual(get_landing_route(), "/portal/orders")

	def test_landing_falls_back_when_that_page_is_switched_off(self):
		"""A stale landing setting must never send someone to a 404."""
		from upande_webstore.services.portal_settings import get_landing_route

		set_portal(landing_page="Statement")
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_statement = 0
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		self.assertEqual(get_landing_route(), "/portal")
