"""The app must not take over the site's front door.

This app is installed alongside the rest of ERPNext on sites that have their own
home page. Everything it serves lives under an explicit prefix — /store, /cart,
/wishlist, /signup, /portal — and the site root stays whatever the site owner
configured. These tests fail if a future change claims it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings

# every route this app is allowed to answer on
OWNED_PREFIXES = ("store", "cart", "wishlist", "signup", "portal")

STOREFRONT_MARKERS = ("ws-storefront-band", "ws-catalog-band", "ws-hero2-inner")


class TestAppDoesNotClaimSiteRoot(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_no_home_page_hook(self):
		"""A home_page hook would redirect the whole site to our page."""
		self.assertFalse(
			frappe.get_hooks("home_page", app_name="upande_webstore"),
			"upande_webstore must not set home_page",
		)

	def test_no_role_home_page_hook(self):
		self.assertFalse(
			frappe.get_hooks("role_home_page", app_name="upande_webstore"),
			"upande_webstore must not set role_home_page",
		)

	def test_no_route_rules_pointing_at_the_root(self):
		rules = frappe.get_hooks("website_route_rules", app_name="upande_webstore") or []
		for rule in rules:
			self.assertNotIn(
				(rule.get("from_route") or "").rstrip("/"),
				("", "/", "/home"),
				f"route rule claims the site root: {rule}",
			)

	def test_ships_no_index_or_home_page(self):
		"""A www/index.html or www/home.html would silently become the site root."""
		import os

		import upande_webstore

		www = os.path.join(os.path.dirname(upande_webstore.__file__), "www")
		for forbidden in ("index.html", "index.md", "home.html", "home.md"):
			self.assertFalse(
				os.path.exists(os.path.join(www, forbidden)),
				f"www/{forbidden} would take over the site root",
			)

	def test_every_page_lives_under_an_owned_prefix(self):
		"""Nothing the app serves may sit at the top level."""
		import os

		import upande_webstore

		www = os.path.join(os.path.dirname(upande_webstore.__file__), "www")
		for entry in os.listdir(www):
			if entry.startswith("__") or entry.endswith((".pyc",)):
				continue
			route = entry.rsplit(".", 1)[0]
			self.assertIn(
				route,
				OWNED_PREFIXES,
				f"www/{entry} is not under an owned prefix; it would add a top-level route",
			)

	def test_site_root_does_not_render_the_storefront(self):
		from frappe.website.serve import get_response_content

		content = get_response_content("/")
		for marker in STOREFRONT_MARKERS:
			self.assertNotIn(marker, content, f"the site root is rendering the storefront ({marker})")

	def test_storefront_is_still_reachable_at_its_own_route(self):
		"""The flip side: keeping off the root must not break /store."""
		from frappe.website.serve import get_response_content

		content = get_response_content("/store")
		self.assertIn("ws-catalog-band", content)
