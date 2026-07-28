import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


def set_flag(fieldname, value):
	settings = frappe.get_doc("Webstore Settings")
	settings.set(fieldname, value)
	settings.save(ignore_permissions=True)
	frappe.clear_cache()


class TestFeatureRegistry(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_all_nineteen_registered(self):
		from upande_webstore.theme.features import FEATURES

		self.assertEqual(len(FEATURES), 19)
		keys = [feature.key for feature in FEATURES]
		self.assertEqual(len(keys), len(set(keys)), "duplicate feature keys")
		for expected in ("cart", "wishlist", "signup", "portal", "quotations", "claims"):
			self.assertIn(expected, keys)

	def test_groups_split_nine_and_ten(self):
		from upande_webstore.theme.features import FEATURES

		self.assertEqual(len([f for f in FEATURES if f.group == "storefront"]), 9)
		self.assertEqual(len([f for f in FEATURES if f.group == "portal"]), 10)

	def test_every_feature_has_a_real_field(self):
		"""A registry entry with no DocType field would silently never disable."""
		from upande_webstore.theme.features import FEATURES

		meta = frappe.get_meta("Webstore Settings")
		for feature in FEATURES:
			self.assertTrue(
				meta.get_field(feature.fieldname), f"missing field {feature.fieldname}"
			)

	def test_default_is_enabled(self):
		from upande_webstore.theme.features import enabled

		for key, value in enabled().items():
			self.assertTrue(value, f"{key} should default on")

	def test_unset_and_blank_count_as_enabled(self):
		from upande_webstore.theme.features import _is_on

		for unset in (None, ""):
			self.assertTrue(_is_on(unset))
		for off in (0, "0"):
			self.assertFalse(_is_on(off))
		for on in (1, "1"):
			self.assertTrue(_is_on(on))

	def test_disabling_reflects_in_enabled(self):
		from upande_webstore.theme.features import enabled

		set_flag("enable_wishlist", 0)
		self.assertFalse(enabled()["wishlist"])
		self.assertTrue(enabled()["cart"])


class TestRequire(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_passes_when_on(self):
		from upande_webstore.theme.features import require

		require("wishlist")  # must not raise

	def test_raises_when_off(self):
		from upande_webstore.theme.features import require

		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			require("wishlist")

	def test_master_gate_composes(self):
		from upande_webstore.theme.features import require

		set_flag("enable_portal", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			require("portal", "quotations")

	def test_unknown_key_raises_valueerror_not_404(self):
		"""A typo in a feature key is a bug, not a 404."""
		from upande_webstore.theme.features import require

		with self.assertRaises(ValueError):
			require("wishlst")


class TestGuard(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_allows_when_on(self):
		from upande_webstore.theme.features import guard

		@guard("wishlist")
		def handler():
			return "ok"

		self.assertEqual(handler(), "ok")

	def test_throws_permission_error_when_off(self):
		from upande_webstore.theme.features import guard

		@guard("wishlist")
		def handler():
			return "ok"

		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.PermissionError):
			handler()

	def test_preserves_function_metadata(self):
		from upande_webstore.theme.features import guard

		@guard("cart")
		def named_handler(a, b=2):
			"""docstring"""
			return a + b

		self.assertEqual(named_handler.__name__, "named_handler")
		self.assertEqual(named_handler.__doc__, "docstring")
		self.assertEqual(named_handler(1), 3)


class TestDependentFlags(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_cart_off_forces_drawer_off(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_cart = 0
		settings.enable_cart_drawer = 1
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(frappe.get_doc("Webstore Settings").enable_cart_drawer, 0)

	def test_drawer_kept_when_cart_on(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_cart = 1
		settings.enable_cart_drawer = 1
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(frappe.get_doc("Webstore Settings").enable_cart_drawer, 1)


class TestRouteEnforcement(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()
		self.original_user = frappe.session.user

	def tearDown(self):
		frappe.set_user(self.original_user)

	def _as_customer(self, email):
		from upande_webstore.tests.utils import make_portal_user

		make_portal_user(email)
		frappe.set_user(email)

	def test_portal_page_context_gates_on_master(self):
		from upande_webstore.services.portal import portal_page_context

		self._as_customer("flagtest1@example.com")
		set_flag("enable_portal", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			portal_page_context(frappe._dict(), "/portal/orders", "orders")

	def test_portal_page_context_gates_on_page_key(self):
		from upande_webstore.services.portal import portal_page_context

		self._as_customer("flagtest2@example.com")
		set_flag("enable_orders", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			portal_page_context(frappe._dict(), "/portal/orders", "orders")

	def test_portal_page_context_allows_when_on(self):
		from upande_webstore.services.portal import portal_page_context

		self._as_customer("flagtest3@example.com")
		context = frappe._dict()
		portal_page_context(context, "/portal/orders", "orders")
		self.assertEqual(context.portal_active, "orders")

	def test_gate_precedes_guest_login_redirect(self):
		"""A disabled page must 404 for guests, not bounce them to a login."""
		from upande_webstore.services.portal import portal_page_context

		set_flag("enable_orders", 0)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.DoesNotExistError):
			portal_page_context(frappe._dict(), "/portal/orders", "orders")

	def test_wishlist_page_gates(self):
		import upande_webstore.www.wishlist as wishlist_page

		self._as_customer("flagtest4@example.com")
		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			wishlist_page.get_context(frappe._dict())

	def test_cart_page_gates(self):
		import upande_webstore.www.cart as cart_page

		self._as_customer("flagtest5@example.com")
		set_flag("enable_cart", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			cart_page.get_context(frappe._dict())

	def test_signup_page_gates(self):
		import upande_webstore.www.signup as signup_page

		set_flag("enable_signup", 0)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.DoesNotExistError):
			signup_page.get_context(frappe._dict())


class TestApiEnforcement(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_search_api_gated_by_palette_flag(self):
		from upande_webstore.api.search import search_products

		set_flag("enable_search_palette", 0)
		with self.assertRaises(frappe.PermissionError):
			search_products("rose")

	def test_search_api_works_when_on(self):
		from upande_webstore.api.search import search_products

		self.assertIsNotNone(search_products("rose"))

	def test_claim_api_gated(self):
		from upande_webstore.api.support import create_claim

		set_flag("enable_claims", 0)
		with self.assertRaises(frappe.PermissionError):
			create_claim("Quality", "SO-0001", "damaged")

	def test_cart_api_gated(self):
		from upande_webstore.api.cart import get_cart_count

		set_flag("enable_cart", 0)
		with self.assertRaises(frappe.PermissionError):
			get_cart_count()

	def test_checkout_api_gated_by_cart_flag(self):
		from upande_webstore.api.checkout import place_order

		set_flag("enable_cart", 0)
		with self.assertRaises(frappe.PermissionError):
			place_order()

	def test_signup_api_gated(self):
		from upande_webstore.api.account import sign_up

		set_flag("enable_signup", 0)
		with self.assertRaises(frappe.PermissionError):
			sign_up("gated@example.com", "Gated User", "0700000000")

	def test_portal_master_gate_blocks_portal_api(self):
		from upande_webstore.api.portal import accept_quotation

		set_flag("enable_portal", 0)
		with self.assertRaises(frappe.PermissionError):
			accept_quotation("QTN-0001")
