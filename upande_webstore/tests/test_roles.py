"""The Roles section on Webstore Settings, and the Custom DocPerm reconcile
behind it.

This is the security-sensitive half of the feature, so every test cleans up
on every path (setUp/tearDown, which unittest guarantees run even when an
assertion raises) and asserts against real `Custom DocPerm` rows rather than
trusting the settings doc's own bookkeeping.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services import roles
from upande_webstore.tests.utils import (
	drop_box_type_doctype,
	make_box_type,
	make_desk_user,
	setup_webstore_settings,
)


class TestRoles(IntegrationTestCase):
	MANAGED_DOCTYPES = (
		"Webstore Product",
		"Webstore Cart",
		"Webstore Wishlist",
		"Webstore Portal Settings",
		"Webstore Portal Access",
		"Webstore Claim",
		"Webstore Claim Type",
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	@classmethod
	def tearDownClass(cls):
		drop_box_type_doctype()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		drop_box_type_doctype()
		self._reset_permissions()
		self.settings = setup_webstore_settings()
		self._created_roles = []

	def tearDown(self):
		frappe.set_user("Administrator")
		self.settings.reload()
		self.settings.set("catalogue_manager_roles", [])
		self.settings.set("order_manager_roles", [])
		self.settings.set("portal_manager_roles", [])
		self.settings.save(ignore_permissions=True)
		self._reset_permissions()
		for role in self._created_roles:
			frappe.delete_doc("Role", role, force=True, ignore_permissions=True)

	def _reset_permissions(self):
		"""Wipe every Custom DocPerm this feature could possibly have touched,
		on every managed doctype plus whatever the box source resolves to —
		a hard backstop on top of the feature's own revoke path, so a test
		that fails partway through can never leak permissions into the next."""
		for doctype in self.MANAGED_DOCTYPES:
			frappe.permissions.reset_perms(doctype)
		box_source = roles._box_source_doctype()
		if box_source and frappe.db.exists("DocType", box_source):
			frappe.permissions.reset_perms(box_source)
		frappe.clear_cache()

	def _make_role(self, name):
		"""A throwaway Role with no permissions of its own on anything, so a
		test's assertions can never be confused by a shipped grant that role
		happens to already carry."""
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		self._created_roles.append(name)
		return name

	# -- the destructive-regression test: written and proven red first -------

	def test_hand_made_custom_docperm_survives_reconcile(self):
		"""A Custom DocPerm an admin created by hand, for a role this feature
		never mentions, must survive a reconcile untouched — granting and then
		revoking some other role on the same doctype must never disturb it."""
		role = self._make_role("WS Test Order Manager")
		frappe.permissions.add_permission("Webstore Wishlist", "Stock User", 0, "read")

		self.settings.set("order_manager_roles", [{"role": role}])
		self.settings.save(ignore_permissions=True)
		self.assertTrue(
			frappe.db.get_value(
				"Custom DocPerm", {"parent": "Webstore Wishlist", "role": "Stock User"}, "read"
			),
			"the hand-made grant must still be there right after an unrelated grant",
		)

		self.settings.set("order_manager_roles", [])
		self.settings.save(ignore_permissions=True)
		self.assertTrue(
			frappe.db.get_value(
				"Custom DocPerm", {"parent": "Webstore Wishlist", "role": "Stock User"}, "read"
			),
			"a hand-made permission for an unrelated role must survive a reconcile",
		)

	# -- rule 1: Webstore Settings is never a managed doctype -----------------

	def test_no_configuration_grants_permission_on_webstore_settings(self):
		"""Every field maxed out at once must still never touch Webstore
		Settings: only System Manager may write it, or a role granted through
		this panel could add itself to every other field and escalate out of
		the webstore into the whole site."""
		role = self._make_role("WS Test Escalate")
		self.settings.set("catalogue_manager_roles", [{"role": role}])
		self.settings.set("order_manager_roles", [{"role": role}])
		self.settings.set("portal_manager_roles", [{"role": role}])

		# exercised directly, with no settings.save() at all
		roles.reconcile(self.settings)

		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Webstore Settings"}))

		# defence in depth: even a direct call to the low-level grant refuses
		with self.assertRaises(ValueError):
			roles._grant("Webstore Settings", role, {"read"})
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Webstore Settings"}))

	# -- rule 2: System Manager is never removed -------------------------------

	def test_system_manager_is_never_removed_from_a_managed_doctype(self):
		role = self._make_role("WS Test Catalogue Manager")
		self.settings.set("catalogue_manager_roles", [{"role": role}])
		self.settings.save(ignore_permissions=True)
		self.assertTrue(
			frappe.db.get_value("Custom DocPerm", {"parent": "Webstore Product", "role": "System Manager"}, "read")
		)

		self.settings.set("catalogue_manager_roles", [])
		self.settings.save(ignore_permissions=True)
		self.assertTrue(
			frappe.db.get_value("Custom DocPerm", {"parent": "Webstore Product", "role": "System Manager"}, "read"),
			"System Manager must never be removed from a managed doctype",
		)

	# -- rule 3, and the grant/revoke behaviour itself -------------------------

	def test_catalogue_manager_role_grants_product_and_box_source_read(self):
		make_box_type("Xpol", 350)
		source_doctype = roles._box_source_doctype()
		role = self._make_role("WS Test Catalogue A")

		self.settings.set("catalogue_manager_roles", [{"role": role}])
		self.settings.save(ignore_permissions=True)

		for ptype in ("read", "write", "create", "delete"):
			self.assertTrue(
				frappe.db.get_value("Custom DocPerm", {"parent": "Webstore Product", "role": role}, ptype)
			)
		self.assertTrue(
			frappe.db.get_value("Custom DocPerm", {"parent": source_doctype, "role": role}, "read")
		)
		# only read: this reaches into the farm's item master, so nothing more
		for ptype in ("write", "create", "delete"):
			self.assertFalse(
				frappe.db.get_value("Custom DocPerm", {"parent": source_doctype, "role": role}, ptype)
			)

	def test_removing_a_role_revokes_exactly_those_permissions(self):
		make_box_type("Xpol", 350)
		source_doctype = roles._box_source_doctype()
		role_a = self._make_role("WS Test Catalogue A")
		role_b = self._make_role("WS Test Catalogue B")

		self.settings.set("catalogue_manager_roles", [{"role": role_a}, {"role": role_b}])
		self.settings.save(ignore_permissions=True)

		self.settings.set("catalogue_manager_roles", [{"role": role_b}])
		self.settings.save(ignore_permissions=True)

		for ptype in ("read", "write", "create", "delete"):
			self.assertFalse(
				frappe.db.get_value("Custom DocPerm", {"parent": "Webstore Product", "role": role_a}, ptype)
			)
			self.assertTrue(
				frappe.db.get_value("Custom DocPerm", {"parent": "Webstore Product", "role": role_b}, ptype)
			)
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": source_doctype, "role": role_a}))
		self.assertTrue(
			frappe.db.get_value("Custom DocPerm", {"parent": source_doctype, "role": role_b}, "read")
		)

	# -- idempotence and inertness ---------------------------------------------

	def test_saving_twice_is_a_noop(self):
		role = self._make_role("WS Test Portal Idem")
		self.settings.set("portal_manager_roles", [{"role": role}])
		self.settings.save(ignore_permissions=True)
		before = frappe.db.count("Custom DocPerm", {"parent": ["in", roles.PORTAL_DOCTYPES]})

		self.settings.reload()
		self.settings.set("portal_manager_roles", [{"role": role}])
		self.settings.save(ignore_permissions=True)
		after = frappe.db.count("Custom DocPerm", {"parent": ["in", roles.PORTAL_DOCTYPES]})

		self.assertEqual(before, after)

	def test_empty_configuration_writes_nothing(self):
		touched = ["Webstore Product", *roles.ORDER_DOCTYPES, *roles.PORTAL_DOCTYPES]
		box_source = roles._box_source_doctype()
		if box_source:
			touched.append(box_source)
		baseline = {dt: frappe.db.count("Custom DocPerm", {"parent": dt}) for dt in touched}

		self.settings.set("catalogue_manager_roles", [])
		self.settings.set("order_manager_roles", [])
		self.settings.set("portal_manager_roles", [])
		self.settings.save(ignore_permissions=True)

		self.assertEqual(self.settings.applied_role_permissions or "", "")
		for dt in touched:
			self.assertEqual(
				frappe.db.count("Custom DocPerm", {"parent": dt}),
				baseline[dt],
				f"an empty configuration must not touch {dt}",
			)

	# -- end to end: the reported bug -------------------------------------------

	def test_sales_manager_granted_via_settings_can_list_box_types(self):
		"""Regression for the reported bug, via the settings path this time
		rather than a hand-made grant: Webstore Product's form calls
		list_box_types on every refresh, and a Sales Manager could open the
		product list but not a single product until a role holding read on
		the box source existed. Ticking Sales Manager in Catalogue Managers
		must be enough — no code change, exactly like the box-api test that
		grants the same permission by hand.
		"""
		from upande_webstore.api.boxes import list_box_types

		make_box_type("Xpol", 350)
		self.settings.set("catalogue_manager_roles", [{"role": "Sales Manager"}])
		self.settings.save(ignore_permissions=True)

		email = make_desk_user("box.settings.manager@example.com", ["Sales Manager"])
		try:
			frappe.set_user(email)
			self.assertEqual(list_box_types(), ["Xpol"])
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
