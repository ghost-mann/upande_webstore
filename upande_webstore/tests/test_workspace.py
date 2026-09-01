"""The desk entry point must survive a fresh install.

The apps screen sends people to /desk/upande-webstore. The desk router resolves
that route against public Workspace docs, so the app has to *ship* one — a
Workspace Sidebar is a different doctype and cannot answer the route. When the
workspace is missing, every deployed site shows "Page upande-webstore not found".

These tests pin the three things that have to line up: the route in hooks.py,
the workspace's name, and the sidebar keyed off that name.
"""

import json
import os

import frappe
from frappe.desk.utils import slug
from frappe.tests import IntegrationTestCase

import upande_webstore
from upande_webstore.patches.reclaim_orphan_webstore_workspace import (
	MODULE as PATCH_MODULE,
)
from upande_webstore.patches.reclaim_orphan_webstore_workspace import (
	WORKSPACE as PATCH_WORKSPACE,
)
from upande_webstore.patches.reclaim_orphan_webstore_workspace import (
	execute,
	reclaim_orphan,
)

APP_ROOT = os.path.dirname(upande_webstore.__file__)
SIDEBAR_JSON = os.path.join(APP_ROOT, "workspace_sidebar", "upande_webstore.json")
WORKSPACE_JSON = os.path.join(
	APP_ROOT, "upande_webstore", "workspace", "upande_webstore", "upande_webstore.json"
)

WORKSPACE = "Upande Webstore"
MODULE = "Upande Webstore"

# link types whose targets are real documents we can check exist
CHECKABLE_LINK_TYPES = ("DocType", "Report", "Page")


def _sidebar_json():
	with open(SIDEBAR_JSON) as f:
		return json.load(f)


class TestWorkspaceExists(IntegrationTestCase):
	def test_workspace_is_installed(self):
		"""Without this doc the apps-screen route 404s on every deployed site."""
		self.assertTrue(
			frappe.db.exists("Workspace", WORKSPACE),
			f"Workspace {WORKSPACE!r} is missing — /desk/upande-webstore will not resolve",
		)

	def test_workspace_is_public(self):
		"""frappe.workspaces only carries public workspaces, and the router reads it."""
		self.assertEqual(frappe.db.get_value("Workspace", WORKSPACE, "public"), 1)

	def test_workspace_belongs_to_this_app(self):
		"""boot.py joins Workspace.module -> Module Def.app_name to group the app's
		workspaces. A module-less workspace resolves its route but leaves the app
		showing no workspaces at all."""
		self.assertEqual(frappe.db.get_value("Workspace", WORKSPACE, "module"), MODULE)
		self.assertEqual(
			frappe.db.get_value("Module Def", MODULE, "app_name"),
			"upande_webstore",
		)

	def test_apps_screen_route_matches_the_workspace_slug(self):
		"""hooks.py hardcodes the route; the router derives it with slug(). If the
		workspace is ever renamed, this is what catches the broken link."""
		apps = frappe.get_hooks("add_to_apps_screen", app_name="upande_webstore")
		self.assertTrue(apps, "add_to_apps_screen is not set")
		route = apps[0]["route"]
		self.assertEqual(
			route,
			f"/desk/{slug(WORKSPACE)}",
			f"apps-screen route {route!r} does not point at the shipped workspace",
		)


class TestWorkspaceContent(IntegrationTestCase):
	def setUp(self):
		self.doc = frappe.get_doc("Workspace", WORKSPACE)

	def test_it_is_not_an_empty_shell(self):
		"""An empty workspace resolves the route but lands people on a blank page."""
		self.assertTrue(json.loads(self.doc.content or "[]"), "workspace has no content blocks")
		self.assertTrue(self.doc.links, "workspace has no links")
		self.assertTrue(self.doc.shortcuts, "workspace has no shortcuts")

	def test_every_link_target_exists(self):
		for link in self.doc.links:
			if link.type == "Card Break" or link.link_type not in CHECKABLE_LINK_TYPES:
				continue
			with self.subTest(link=link.label):
				self.assertTrue(
					frappe.db.exists(link.link_type, link.link_to),
					f"{link.link_type} {link.link_to!r} does not exist",
				)

	def test_every_shortcut_target_exists(self):
		for shortcut in self.doc.shortcuts:
			if shortcut.type not in CHECKABLE_LINK_TYPES:
				continue
			with self.subTest(shortcut=shortcut.label):
				self.assertTrue(
					frappe.db.exists(shortcut.type, shortcut.link_to),
					f"{shortcut.type} {shortcut.link_to!r} does not exist",
				)

	def test_content_blocks_reference_real_cards_and_shortcuts(self):
		"""A card/shortcut block naming something absent renders as a blank tile."""
		card_labels = {link.label for link in self.doc.links if link.type == "Card Break"}
		shortcut_labels = {s.label for s in self.doc.shortcuts}

		for block in json.loads(self.doc.content or "[]"):
			data = block.get("data") or {}
			if block.get("type") == "card":
				self.assertIn(data.get("card_name"), card_labels)
			elif block.get("type") == "shortcut":
				self.assertIn(data.get("shortcut_name"), shortcut_labels)


class TestWorkspaceSidebar(IntegrationTestCase):
	"""The sidebar is keyed by the workspace title, lowercased (boot.get_sidebar_items
	stores it that way and sidebar.js looks it up that way)."""

	def test_sidebar_is_installed(self):
		self.assertTrue(frappe.db.exists("Workspace Sidebar", WORKSPACE))

	def test_sidebar_title_matches_the_workspace(self):
		"""Different names means landing on the workspace shows someone else's sidebar."""
		self.assertEqual(_sidebar_json()["title"], WORKSPACE)

	def test_sidebar_is_owned_by_this_app(self):
		"""sidebar.js filters sidebars by app when building the app switcher."""
		row = frappe.db.get_value(
			"Workspace Sidebar", WORKSPACE, ["app", "module", "standard"], as_dict=True
		)
		self.assertEqual(row.app, "upande_webstore")
		self.assertEqual(row.module, MODULE)
		self.assertEqual(row.standard, 1)

	def test_every_sidebar_link_target_exists(self):
		doc = frappe.get_doc("Workspace Sidebar", WORKSPACE)
		for item in doc.items:
			if item.type == "Section Break" or item.link_type not in CHECKABLE_LINK_TYPES:
				continue
			with self.subTest(item=item.label):
				self.assertTrue(
					frappe.db.exists(item.link_type, item.link_to),
					f"{item.link_type} {item.link_to!r} does not exist",
				)

	def test_sidebar_shows_at_least_one_real_item(self):
		"""boot.get_sidebar_items drops any sidebar whose items are all Section
		Breaks — it would vanish from the desk entirely."""
		doc = frappe.get_doc("Workspace Sidebar", WORKSPACE)
		self.assertTrue(any(item.type != "Section Break" for item in doc.items))




class TestOrphanWorkspacePatch(IntegrationTestCase):
	"""The repair for sites that created the workspace by hand while it was missing.

	It runs against a throwaway workspace, never the shipped one. Deleting a Workspace
	fires hooks in both directions — on_trash takes the same-titled Workspace Sidebar
	when the module is unset, after_delete takes the source folder off disk when it is
	set — so these tests would destroy the app's own files if pointed at the real doc.
	"""

	ORPHAN = "Upande Webstore Patch Fixture"

	def tearDown(self):
		# leave nothing that a later run could mistake for a real orphan
		frappe.db.set_value("Workspace", self.ORPHAN, "module", MODULE, update_modified=False)
		frappe.delete_doc_if_exists("Workspace", self.ORPHAN, force=True)
		frappe.delete_doc_if_exists("Workspace Sidebar", self.ORPHAN, force=True)

	def _make_orphan(self, with_links=False):
		"""A public, module-less workspace: the shape the desk UI leaves behind."""
		doc = frappe.get_doc(
			{
				"doctype": "Workspace",
				"title": self.ORPHAN,
				"label": self.ORPHAN,
				"public": 1,
				"module": None,
				"content": "[]",
				"type": "Workspace",
			}
		)
		if with_links:
			doc.append("links", {"type": "Card Break", "label": "Hand-built"})
		doc.insert(ignore_permissions=True)
		return doc

	def test_it_claims_a_module_less_empty_workspace(self):
		self._make_orphan()
		self.assertTrue(reclaim_orphan(self.ORPHAN, MODULE))
		self.assertEqual(
			frappe.db.get_value("Workspace", self.ORPHAN, "module"),
			MODULE,
			"an unclaimed workspace stays outside the app's boot join",
		)

	def test_it_backdates_so_the_shipped_file_can_overwrite(self):
		"""import_file_by_path skips a file older than the row in the database."""
		from frappe.utils import get_datetime

		self._make_orphan()
		reclaim_orphan(self.ORPHAN, MODULE)

		modified = get_datetime(frappe.db.get_value("Workspace", self.ORPHAN, "modified"))
		shipped = get_datetime(json.load(open(WORKSPACE_JSON))["modified"])
		self.assertLess(
			modified, shipped, "the row still out-dates the shipped file, so sync_all will skip it"
		)

	def test_it_keeps_the_workspace_rather_than_deleting_it(self):
		"""Deleting is what destroys the sidebar and the source folder."""
		self._make_orphan()
		reclaim_orphan(self.ORPHAN, MODULE)
		self.assertTrue(frappe.db.exists("Workspace", self.ORPHAN))

	def test_it_leaves_a_workspace_someone_built_content_in(self):
		self._make_orphan(with_links=True)
		self.assertFalse(reclaim_orphan(self.ORPHAN, MODULE))
		self.assertIsNone(
			frappe.db.get_value("Workspace", self.ORPHAN, "module"),
			"a workspace with real links must not be claimed automatically",
		)

	def test_it_is_a_no_op_on_a_fresh_site(self):
		"""Nothing to repair before the app has ever been installed."""
		self.assertFalse(reclaim_orphan("Workspace That Does Not Exist", MODULE))

	def test_it_leaves_the_standard_workspace_alone(self):
		"""The shipped workspace already names the module, so execute() returns early."""
		before = frappe.db.get_value("Workspace", WORKSPACE, "modified")
		execute()
		self.assertEqual(frappe.db.get_value("Workspace", WORKSPACE, "module"), MODULE)
		self.assertEqual(frappe.db.get_value("Workspace", WORKSPACE, "modified"), before)

	def test_execute_targets_the_shipped_workspace(self):
		self.assertEqual(PATCH_WORKSPACE, WORKSPACE)
		self.assertEqual(PATCH_MODULE, MODULE)

	def test_the_patch_runs_before_model_sync(self):
		"""In post_model_sync it would land after the import it exists to unblock."""
		with open(os.path.join(APP_ROOT, "patches.txt")) as f:
			body = f.read()
		pre, _, post = body.partition("[post_model_sync]")
		entry = "upande_webstore.patches.reclaim_orphan_webstore_workspace"
		self.assertIn(entry, pre, "patch must be listed under [pre_model_sync]")
		self.assertNotIn(entry, post)
