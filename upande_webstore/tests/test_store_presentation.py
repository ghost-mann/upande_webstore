"""Phase 2: two storefronts on one site can look and behave differently.

Phase 1 gave a store its own catalogue, cart and orders, but every shop still
rendered in one theme with one name — which is most of what makes two shops
two shops. These exercise the whole read path (`services.settings.get_settings`
-> `theme.get_theme`), because that is the path every page actually takes.

The acceptance bar is at the bottom: a store that overrides nothing must
render byte-for-byte what the site rendered before any of this existed.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.settings import get_settings
from upande_webstore.services.store import clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, setup_webstore_settings


class StoreCase(IntegrationTestCase):
	"""Two stores, and a helper to render as one of them."""

	def setUp(self):
		delete_all_webstores()
		self.settings = setup_webstore_settings()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		delete_all_webstores()
		frappe.clear_cache()

	def _as(self, slug):
		frappe.local.webstore_slug = slug
		clear_store_cache()
		frappe.local.webstore_merged_settings = None

	def _site(self, **values):
		for field, value in values.items():
			self.settings.set(field, value)
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()

	def _theme(self):
		from upande_webstore.theme import get_theme

		return get_theme(get_settings())


class TestThemePerStore(StoreCase):
	def test_two_stores_render_different_accents(self):
		self._site(accent="#111111")
		make_webstore("flowers", accent="#FF0066")
		make_webstore("dairy", accent="#0066FF")

		self._as("flowers")
		flowers = self._theme().tokens
		self._as("dairy")
		dairy = self._theme().tokens

		self.assertNotEqual(flowers, dairy)
		self.assertIn("#FF0066".lower(), str(flowers).lower())
		self.assertIn("#0066FF".lower(), str(dairy).lower())

	def test_a_store_that_sets_no_colour_inherits_the_sites(self):
		self._site(accent="#111111")
		make_webstore("flowers")
		make_webstore("dairy", accent="#0066FF")

		self._as("flowers")
		inherited = self._theme().tokens
		frappe.local.webstore_slug = None
		clear_store_cache()
		frappe.local.webstore_merged_settings = None
		delete_all_webstores()
		site_only = self._theme().tokens

		self.assertEqual(inherited, site_only)

	def test_custom_css_is_per_store(self):
		self._site(custom_css=".site{}")
		make_webstore("flowers", custom_css=".flowers{}")
		make_webstore("dairy")

		self._as("flowers")
		self.assertIn(".flowers{}", self._theme().custom_css)
		self._as("dairy")
		self.assertIn(".site{}", self._theme().custom_css)

	def test_fonts_are_per_store(self):
		make_webstore("flowers", font_display="Fraunces")
		make_webstore("dairy", font_display="Custom", font_display_name="Bodoni Moda")

		from upande_webstore.theme import fonts

		self._as("flowers")
		flowers = fonts.resolve(get_settings())["display"]
		self._as("dairy")
		dairy = fonts.resolve(get_settings())["display"]
		self.assertIn("Fraunces", flowers)
		self.assertIn("Bodoni Moda", dairy)


class TestBrandingPerStore(StoreCase):
	def test_each_store_has_its_own_name_and_wordmark(self):
		make_webstore("flowers", site_name="Karen Roses", wordmark="karen", wordmark_bold="roses")
		make_webstore("dairy", site_name="Kaitet Dairy", wordmark="kaitet", wordmark_bold="dairy")

		self._as("flowers")
		flowers = self._theme().branding
		self._as("dairy")
		dairy = self._theme().branding

		self.assertEqual(flowers.site_name, "Karen Roses")
		self.assertEqual(dairy.site_name, "Kaitet Dairy")
		self.assertEqual(flowers.wordmark_bold, "roses")
		self.assertEqual(dairy.wordmark_bold, "dairy")

	def test_hero_copy_is_per_store(self):
		self._site(hero_heading="Site heading")
		make_webstore("flowers", hero_heading="Roses, cut this morning")
		make_webstore("dairy")

		self._as("flowers")
		self.assertEqual(self._theme().branding.hero_heading, "Roses, cut this morning")
		self._as("dairy")
		self.assertEqual(self._theme().branding.hero_heading, "Site heading")

	def test_hero_stats_replace_wholesale_per_store(self):
		self.settings.set("hero_stats", [{"value": "1", "label": "site"}])
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()

		make_webstore(
			"flowers",
			hero_stats=[{"value": "40", "label": "varieties"}, {"value": "24h", "label": "to Schiphol"}],
		)
		make_webstore("dairy")

		self._as("flowers")
		flowers = self._theme().branding.hero_stats
		self._as("dairy")
		dairy = self._theme().branding.hero_stats

		# replaced, not spliced with the site's one row
		self.assertEqual([row["label"] for row in flowers], ["varieties", "to Schiphol"])
		self.assertEqual([row["label"] for row in dairy], ["site"])

	def test_footer_links_are_per_store(self):
		make_webstore(
			"flowers",
			footer_links=[{"column": "Shop", "label": "Growers", "url": "/growers"}],
		)
		make_webstore("dairy")

		self._as("flowers")
		columns = self._theme().branding.footer_columns
		self.assertEqual([link["label"] for column in columns for link in column["links"]], ["Growers"])
		self._as("dairy")
		self.assertEqual(self._theme().branding.footer_columns, [])


class TestFeaturesPerStore(StoreCase):
	def test_a_store_can_switch_a_storefront_feature_off_on_its_own(self):
		"""The reason the feature flags are three-state on a store: the dairy
		shop sells by the crate and wants no wishlist, while the flower shop
		keeps one."""
		self._site(enable_wishlist=1)
		make_webstore("flowers")
		make_webstore("dairy", enable_wishlist="Disabled")

		self._as("flowers")
		self.assertTrue(self._theme().features.wishlist)
		self._as("dairy")
		self.assertFalse(self._theme().features.wishlist)

	def test_a_store_can_switch_one_on_that_the_site_leaves_off(self):
		self._site(enable_signup=0)
		make_webstore("flowers", enable_signup="Enabled")
		make_webstore("dairy")

		self._as("flowers")
		self.assertTrue(self._theme().features.signup)
		self._as("dairy")
		self.assertFalse(self._theme().features.signup)

	def test_a_disabled_feature_refuses_its_api_in_that_store_only(self):
		"""A flag is not decoration: the guard has to refuse the call, not
		only hide the button."""
		from upande_webstore.api import wishlist

		self._site(enable_wishlist=1)
		make_webstore("flowers")
		make_webstore("dairy", enable_wishlist="Disabled")

		self._as("dairy")
		with self.assertRaises(frappe.PermissionError):
			wishlist.get_wishlisted_products()

		self._as("flowers")
		wishlist.get_wishlisted_products()  # must not raise

	def test_the_shared_portal_flags_are_not_per_store(self):
		"""One account, one order history — a store cannot close the portal
		for itself, because there is no per-store portal to close."""
		self._site(enable_invoices=1)
		make_webstore("flowers")
		self._as("flowers")
		self.assertTrue(self._theme().features.invoices)
		self.assertIsNone(frappe.get_meta("Webstore").get_field("enable_invoices"))


class TestCommercePerStore(StoreCase):
	def test_guest_price_list_is_per_store(self):
		self._site(guest_price_list="Standard Selling")
		make_webstore("flowers", guest_price_list="Standard Buying")
		make_webstore("dairy")

		self._as("flowers")
		self.assertEqual(get_settings().guest_price_list, "Standard Buying")
		self._as("dairy")
		self.assertEqual(get_settings().guest_price_list, "Standard Selling")

	def test_stock_display_is_per_store(self):
		self._site(stock_display="In/Out Badge")
		make_webstore("flowers", stock_display="Exact Quantity")
		make_webstore("dairy")

		self._as("flowers")
		self.assertEqual(get_settings().stock_display, "Exact Quantity")
		self._as("dairy")
		self.assertEqual(get_settings().stock_display, "In/Out Badge")


class TestStorefrontLinksFollowTheStore(StoreCase):
	def test_the_nav_links_carry_the_stores_prefix(self):
		make_webstore("flowers")
		self._as("flowers")
		context = frappe._dict()
		from upande_webstore.services.settings import update_website_context

		update_website_context(context)
		self.assertEqual(context.webstore_urls.store, "/flowers/store")
		self.assertEqual(context.webstore_urls.cart, "/flowers/cart")
		self.assertEqual(context.webstore_urls.wishlist, "/flowers/wishlist")

	def test_the_default_store_keeps_the_bare_paths(self):
		"""The acceptance bar for markup: nothing about a single-store site's
		links changes."""
		make_webstore("store", title="Default")
		clear_store_cache()
		context = frappe._dict()
		from upande_webstore.services.settings import update_website_context

		update_website_context(context)
		self.assertEqual(context.webstore_urls.store, "/store")
		self.assertEqual(context.webstore_urls.cart, "/cart")
		self.assertEqual(context.webstore_urls.wishlist, "/wishlist")


class TestSingleStoreSiteIsUnchanged(StoreCase):
	"""The acceptance bar: a store overriding nothing renders what the site
	rendered before multi-store existed."""

	def test_a_blank_store_renders_exactly_the_sites_own_theme(self):
		self._site(
			accent="#8C1D40",
			ink="#1A1A1A",
			site_name="Only Shop",
			hero_heading="One shop",
			custom_css=".only{}",
		)
		before = self._theme()

		make_webstore("store", title="Only Shop")
		clear_store_cache()
		frappe.local.webstore_merged_settings = None
		after = self._theme()

		self.assertEqual(after.tokens, before.tokens)
		self.assertEqual(after.custom_css, before.custom_css)
		self.assertEqual(after.branding, before.branding)
		self.assertEqual(after.features, before.features)
