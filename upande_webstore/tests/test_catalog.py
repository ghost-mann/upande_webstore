import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	setup_webstore_settings,
)


def _card_html(search):
	"""Render /store scoped to one product by search term.

	get_html_for_route builds its request from a bare path — a "?q=" suffix
	never reaches frappe.form_dict (that parsing happens earlier in the real
	request lifecycle, which this helper bypasses) — so the query param is set
	directly instead.
	"""
	from frappe.utils import get_html_for_route

	frappe.local.form_dict = frappe._dict({"q": search})
	try:
		return get_html_for_route("store")
	finally:
		frappe.local.form_dict = frappe._dict()


class TestCatalog(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CAT-ALPHA", web_title="Alpha Sensor", featured=1)
		make_test_product("WS-CAT-BETA", web_title="Beta Gateway")
		make_test_product("WS-CAT-HIDDEN", web_title="Hidden Product", published=0)
		make_item_price("WS-CAT-ALPHA", "Standard Selling", 10)

	def test_only_published_products_listed(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_search(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(search="Alpha")
		self.assertEqual(len(result["products"]), 1)
		self.assertEqual(result["products"][0]["web_title"], "Alpha Sensor")
		self.assertEqual(result["products"][0]["price"]["rate"], 10)

	def test_featured_filter(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(featured_only=True, page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Beta Gateway", titles)

	def test_categories(self):
		from upande_webstore.services.catalog import get_categories

		categories = get_categories()
		self.assertTrue(any(c["value"] == "Products" and c["count"] >= 2 for c in categories))

	def test_store_page_renders(self):
		from frappe.utils import get_html_for_route

		html = get_html_for_route("store")
		self.assertIn("Alpha Sensor", html)
		self.assertNotIn("Hidden Product", html)

	def test_guest_can_browse_products(self):
		"""Regression guard once the bench is upgraded past frappe 16.27.

		Unpatched, this passes on both 16.27 (where get_cached_doc/value do not
		enforce role permissions) and 16.32+ (where the source fix reads Item
		fields via frappe.db.get_value, which never checks permissions). It is
		not, on its own, proof the bug is fixed — see
		test_guest_browsing_survives_item_permission_enforcement below, which
		simulates the 16.32 behaviour this bench cannot reproduce natively.
		"""
		from upande_webstore.services.catalog import get_products

		frappe.set_user("Guest")
		try:
			result = get_products(page_length=100)
		finally:
			frappe.set_user("Administrator")
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_guest_browsing_survives_item_permission_enforcement(self):
		"""Reproduce the frappe 16.32 storefront 403, on this 16.27 bench.

		On a live 16.32 site, Guest gets 403 on /store and /store/<product>
		because frappe.get_cached_doc/get_cached_value there enforce role
		permission on Item — and the app never grants Guest read on Item (Item
		carries cost/valuation data). On this 16.27 bench that enforcement does
		not happen, so a plain guest test (see above) passes before and after a
		fix and proves nothing.

		Monkeypatching get_cached_doc/get_cached_value to raise for Item, while
		passing every other doctype through unchanged, reproduces the 16.32
		behaviour here. This must fail before the source fix (which replaced
		those permission-checked reads with frappe.db.get_value, a
		permission-independent field read) and pass after it.

		The fakes below only raise when frappe.flags.ignore_permissions is
		falsy — real permission checks in frappe return early once that flag
		is set, so an unconditional raise here would be stricter than the
		framework and could hide a fix (or push toward the wrong one) that
		relies on the flag, the way services/pricing.get_item_price now does
		for its ERPNext price lookup.
		"""
		real_get_cached_doc = frappe.get_cached_doc
		real_get_cached_value = frappe.get_cached_value

		def fake_get_cached_doc(doctype, *args, **kwargs):
			if doctype == "Item" and not frappe.flags.ignore_permissions:
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_doc(doctype, *args, **kwargs)

		def fake_get_cached_value(doctype, *args, **kwargs):
			if doctype == "Item" and not frappe.flags.ignore_permissions:
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_value(doctype, *args, **kwargs)

		# A template item: its listing price comes from get_variant_price_range
		# (plain frappe.get_all queries), not get_item_price — which calls
		# into ERPNext's own get_item_details, itself unconditionally calling
		# frappe.get_cached_doc("Item", ...) and so out of this app's control.
		# Isolating on a template keeps this test to what upande_webstore is
		# responsible for fixing.
		make_variant_template("WS-CAT-GUESTPERM")
		make_test_product("WS-CAT-GUESTPERM", web_title="Guest Perm Template")

		frappe.get_cached_doc = fake_get_cached_doc
		frappe.get_cached_value = fake_get_cached_value
		try:
			frappe.set_user("Guest")
			from upande_webstore.services.catalog import get_products
			from upande_webstore.services.stock import get_stock_info

			result = get_products(search="Guest Perm Template")
			titles = [p["web_title"] for p in result["products"]]
			self.assertIn("Guest Perm Template", titles)
			product = next(p for p in result["products"] if p["web_title"] == "Guest Perm Template")
			self.assertTrue(product["has_variants"])

			info = get_stock_info("WS-CAT-ALPHA")
			self.assertIn("in_stock", info)

			# A non-template product: get_item_price's ERPNext price lookup
			# is the call site the template case above deliberately avoids.
			# WS-CAT-ALPHA has a seeded Item Price (see setUpClass), so a rate
			# of 0 would mean pricing silently failed rather than resolved.
			alpha_result = get_products(search="Alpha Sensor")
			alpha_titles = [p["web_title"] for p in alpha_result["products"]]
			self.assertIn("Alpha Sensor", alpha_titles)
			alpha_product = next(
				p for p in alpha_result["products"] if p["web_title"] == "Alpha Sensor"
			)
			self.assertIsNotNone(alpha_product["price"])
			self.assertGreater(alpha_product["price"]["rate"], 0)
		finally:
			frappe.get_cached_doc = real_get_cached_doc
			frappe.get_cached_value = real_get_cached_value
			frappe.set_user("Administrator")


class TestListingAddToCart(IntegrationTestCase):
	"""The listing grid lets a buyer add straight from a card — but only when
	the product needs no choice first, and only when the cart is switched on."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-LIST-QTY", web_title="Listing Qty Rose")
		make_item_price("WS-LIST-QTY", "Standard Selling", 48)
		make_variant_template("WS-LIST-TPL")
		make_test_product("WS-LIST-TPL", web_title="Listing Template Rose", has_variants=1)

	def setUp(self):
		setup_webstore_settings()

	def test_non_template_card_has_qty_input_and_add_button(self):
		html = _card_html("WS-LIST-QTY")
		self.assertIn('data-webstore-add-to-cart="WS-LIST-QTY"', html)
		self.assertIn("data-webstore-qty", html)

	def test_template_card_has_choose_length_link_and_no_add_button(self):
		"""A template needs a stem length picked on its own page first, so the
		card offers a link there instead of an add-straight-from-the-grid button."""
		html = _card_html("WS-LIST-TPL")
		self.assertNotIn('data-webstore-add-to-cart="WS-LIST-TPL"', html)
		self.assertNotIn("data-webstore-qty", html)
		self.assertIn("Choose length", html)

	def test_cart_controls_hidden_when_cart_feature_disabled(self):
		frappe.db.set_single_value("Webstore Settings", "enable_cart", 0)
		frappe.clear_cache()
		try:
			html = _card_html("WS-LIST-QTY")
			self.assertNotIn("data-webstore-add-to-cart", html)
			self.assertNotIn("data-webstore-qty", html)
		finally:
			frappe.db.set_single_value("Webstore Settings", "enable_cart", 1)
			frappe.clear_cache()


class TestCategories(IntegrationTestCase):
	"""The curated `categories` table on Webstore Settings, once populated,
	replaces the derived category list — but stays completely inert until an
	operator adds a row (see TestCatalog.test_categories for the untouched,
	derived path)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		for group in ("WS Cat Rose", "WS Cat Aster", "WS Cat Zinnia", "WS Cat Herb"):
			if not frappe.db.exists("Item Group", group):
				frappe.get_doc({
					"doctype": "Item Group",
					"item_group_name": group,
					"parent_item_group": "All Item Groups",
				}).insert(ignore_permissions=True)
		make_test_product("WS-CATTBL-ROSE", web_title="Rose Bunch", item_group="WS Cat Rose")
		make_test_product("WS-CATTBL-ASTER", web_title="Aster Bunch", item_group="WS Cat Aster")
		make_test_product("WS-CATTBL-ZINNIA", web_title="Zinnia Bunch", item_group="WS Cat Zinnia")
		# WS Cat Herb deliberately gets no product: it exists so a configured
		# row for it proves out the zero-published-products omission below.

	def setUp(self):
		# The class-wide rollback only fires once every test in this class has
		# run, so a table one test configures would otherwise still be sitting
		# there for the next test in this class — reset it before each one.
		setup_webstore_settings()

	def _set_categories(self, rows):
		settings = frappe.get_doc("Webstore Settings")
		settings.set("categories", [])
		for row in rows:
			settings.append("categories", row)
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

	def test_empty_table_keeps_derived_behaviour(self):
		"""The inert path: no rows configured, so behaviour is unchanged from
		before curated categories existed — derived, alphabetical, value==label."""
		from upande_webstore.services.catalog import get_categories

		entry = next(c for c in get_categories() if c["value"] == "WS Cat Rose")
		self.assertEqual(entry["label"], "WS Cat Rose")
		self.assertGreaterEqual(entry["count"], 1)

	def test_configured_table_used_in_table_order_not_alphabetical(self):
		"""Proves curation actually curates: Zinnia, Rose, Aster is the table
		order and must come back exactly that way, not resorted to Aster,
		Rose, Zinnia the way the derived path would."""
		from upande_webstore.services.catalog import get_categories

		self._set_categories([
			{"item_group": "WS Cat Zinnia", "published": 1},
			{"item_group": "WS Cat Rose", "published": 1},
			{"item_group": "WS Cat Aster", "published": 1},
		])
		self.assertEqual(
			[c["value"] for c in get_categories()],
			["WS Cat Zinnia", "WS Cat Rose", "WS Cat Aster"],
		)

	def test_unpublished_row_hidden(self):
		from upande_webstore.services.catalog import get_categories

		self._set_categories([
			{"item_group": "WS Cat Rose", "published": 1},
			{"item_group": "WS Cat Aster", "published": 0},
		])
		values = [c["value"] for c in get_categories()]
		self.assertIn("WS Cat Rose", values)
		self.assertNotIn("WS Cat Aster", values)

	def test_label_used_for_display_while_value_stays_the_item_group(self):
		"""The href/filter value must stay the Item Group name so a bookmark or
		the /store?category= filter itself survives a display rename."""
		from upande_webstore.services.catalog import get_categories, get_products

		self._set_categories([
			{"item_group": "WS Cat Rose", "label": "Fresh Roses", "published": 1},
		])
		entry = get_categories()[0]
		self.assertEqual(entry["value"], "WS Cat Rose")
		self.assertEqual(entry["label"], "Fresh Roses")

		result = get_products(category="WS Cat Rose", page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Rose Bunch", titles)

	def test_configured_row_with_no_published_products_omitted(self):
		"""A configured category with nothing published behind it would just
		be a link to an empty page, same as the derived list already avoids."""
		from upande_webstore.services.catalog import get_categories

		self._set_categories([
			{"item_group": "WS Cat Rose", "published": 1},
			{"item_group": "WS Cat Herb", "published": 1},
		])
		values = [c["value"] for c in get_categories()]
		self.assertIn("WS Cat Rose", values)
		self.assertNotIn("WS Cat Herb", values)

	def test_rendered_store_page_shows_the_label(self):
		from frappe.utils import get_html_for_route

		self._set_categories([
			{"item_group": "WS Cat Rose", "label": "Fresh Roses", "published": 1},
		])
		html = get_html_for_route("store")
		self.assertIn("Fresh Roses", html)
		self.assertIn("category=WS%20Cat%20Rose", html)
