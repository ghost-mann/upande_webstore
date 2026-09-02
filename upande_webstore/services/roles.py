"""Reconciles the Roles section on Webstore Settings against real DocPerms.

Webstore Product ships to System Manager and Sales Manager only; Webstore
Cart and Webstore Wishlist ship to System Manager alone; and stock ERPNext
grants Item read to Sales User but not Sales Manager (this app's box-type
reads go through `services/access.py::require_permission`, which defers to
`frappe.has_permission`, so a farm that wants a different role in has nowhere
to say so short of the Role Permission Manager). This module is that "where":
three role multi-selects on Webstore Settings, reconciled to Custom DocPerms
on save.

Three rules shape every function here:

1. Webstore Settings itself is never touched. Only System Manager may write
   it — letting this feature grant write on it would let anyone holding a
   managed role add themselves to every other field, i.e. escalate out of the
   webstore into the whole site. `_grant` refuses it even if a caller's own
   bug ever tried, on top of the doctype list below never naming it.
2. System Manager is never removed. `_revoke` only ever clears the exact
   ptypes this feature itself set for a role (tracked in
   `applied_role_permissions`), so a shipped System Manager grant — or a
   System Manager row `add_permission` copies into Custom DocPerm the first
   time a doctype is touched — is never something this feature considers
   "ours" to take back.
3. Only what this feature added is ever removed. Reconciling walks the
   *previously applied* record, not "whatever Custom DocPerms currently
   exist" — a Custom DocPerm an admin created by hand for some other role is
   never in that record, so it is never inspected, let alone changed.
"""

import json

import frappe

#: This doctype must never appear on either side of a grant. Enforced twice:
#: it is simply never named in desired_grants() below, and _grant refuses it
#: outright as a second, independent line of defence.
FORBIDDEN_DOCTYPE = "Webstore Settings"

CATALOGUE_FIELD = "catalogue_manager_roles"
ORDER_FIELD = "order_manager_roles"
PORTAL_FIELD = "portal_manager_roles"

CATALOGUE_PTYPES = ("read", "write", "create", "delete")
ORDER_DOCTYPES = ("Webstore Cart", "Webstore Wishlist")
ORDER_PTYPES = ("read",)
PORTAL_DOCTYPES = (
	"Webstore Portal Settings",
	"Webstore Portal Access",
	"Webstore Claim",
	"Webstore Claim Type",
)
PORTAL_PTYPES = ("read", "write", "create")

# Every flag a Custom DocPerm row can carry. Used only to tell whether a row
# this feature has just cleared its own flags on is now carrying nothing else
# an admin set by hand — if so it is deleted; if not, it is left alone.
_PTYPE_FLAGS = (
	"read", "write", "create", "delete", "submit", "cancel", "amend", "mask",
	"report", "export", "import", "share", "print", "email", "select",
)


def _box_source_doctype():
	"""Which doctype box types live on for this site, or None.

	Guarded like every other read of it in this app (packing.py): a farm may
	have neither `Box Type` nor Item-based box fields, and that is not this
	feature's problem to raise about.
	"""
	from upande_webstore.services.packing import get_box_source

	source = get_box_source()
	return source.doctype if source else None


def _roles_of(settings, fieldname):
	return [row.role for row in (settings.get(fieldname) or []) if row.role]


def desired_grants(settings):
	"""doctype -> role -> sorted list of ptypes the Roles section wants applied.

	`settings` need only support `.get(fieldname)` returning a list of rows
	with a `.role` attribute — a real Webstore Settings doc works, and so does
	a plain `frappe._dict` built for a test, which is what keeps this
	testable without ever calling `.save()`.
	"""
	grants = {}

	def add(doctype, roles, ptypes):
		if not doctype or doctype == FORBIDDEN_DOCTYPE:
			return
		if not frappe.db.exists("DocType", doctype):
			return
		for role in roles:
			grants.setdefault(doctype, {}).setdefault(role, set()).update(ptypes)

	catalogue_roles = _roles_of(settings, CATALOGUE_FIELD)
	add("Webstore Product", catalogue_roles, CATALOGUE_PTYPES)
	add(_box_source_doctype(), catalogue_roles, ("read",))

	order_roles = _roles_of(settings, ORDER_FIELD)
	for doctype in ORDER_DOCTYPES:
		add(doctype, order_roles, ORDER_PTYPES)

	portal_roles = _roles_of(settings, PORTAL_FIELD)
	for doctype in PORTAL_DOCTYPES:
		add(doctype, portal_roles, PORTAL_PTYPES)

	return {
		doctype: {role: sorted(ptypes) for role, ptypes in roles.items()}
		for doctype, roles in grants.items()
	}


def _load_applied(settings):
	"""The record of what a previous reconcile applied — never what currently
	exists in Custom DocPerm, which may hold rows this feature never touched."""
	raw = settings.get("applied_role_permissions")
	if not raw:
		return {}
	try:
		data = json.loads(raw)
	except (TypeError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}


def _dump(grants):
	return json.dumps(grants, sort_keys=True) if grants else ""


def _custom_docperm_name(doctype, role):
	return frappe.db.get_value(
		"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	)


def _grant(doctype, role, ptypes):
	"""Ensure every ptype in `ptypes` is set on `role`'s Custom DocPerm for
	`doctype`, using frappe's own Role Permission Manager helpers so this
	behaves exactly as if an admin had ticked the same boxes by hand."""
	if doctype == FORBIDDEN_DOCTYPE:
		# Belt and braces: desired_grants() never names this doctype, so this
		# only fires if a future change to this module's wiring gets it wrong.
		raise ValueError("Refusing to grant any permission on Webstore Settings.")
	ptypes = set(ptypes)
	existed_before = bool(_custom_docperm_name(doctype, role))
	if not existed_before:
		frappe.permissions.add_permission(doctype, role, permlevel=0, ptype=sorted(ptypes)[0])
	# add_permission may also have no-opped (a Custom DocPerm for this role
	# already existed, copied from a shipped DocPerm when the doctype was
	# touched for the first time) — set every ptype explicitly regardless, so
	# the result never depends on what that copy happened to already carry.
	for ptype in sorted(ptypes):
		frappe.permissions.update_permission_property(doctype, role, 0, ptype, 1)
	if not existed_before:
		# A row add_permission just created carries its own shipped Custom
		# DocPerm defaults — notably `export`, which defaults to 1 however the
		# row was created — regardless of which single ptype was asked for.
		# Zero anything this call did not actually want, but only on a row
		# this call just created: a pre-existing row may carry flags an admin
		# set by hand, and those must never be touched here.
		for ptype in set(_PTYPE_FLAGS) - ptypes:
			frappe.permissions.update_permission_property(doctype, role, 0, ptype, 0)


def _revoke(doctype, role, ptypes):
	"""Clear exactly `ptypes` on the Custom DocPerm this feature previously
	set for `role` on `doctype`. The row itself is deleted only once nothing
	but this feature's flags are left on it — anything an admin set on the
	same row by hand keeps the row alive and untouched."""
	docperm_name = _custom_docperm_name(doctype, role)
	if not docperm_name:
		# an admin may already have removed it by hand; nothing to do
		return
	for ptype in ptypes:
		frappe.permissions.update_permission_property(doctype, role, 0, ptype, 0)
	remaining = frappe.db.get_value("Custom DocPerm", docperm_name, list(_PTYPE_FLAGS), as_dict=True)
	if remaining and not any(remaining.values()):
		frappe.delete_doc("Custom DocPerm", docperm_name, ignore_permissions=True, force=True)


def reconcile(settings):
	"""Apply the Roles section on `settings` to real Custom DocPerms.

	Diffs `desired_grants(settings)` against the record of what the previous
	reconcile applied (`settings.applied_role_permissions`) — never against
	whatever Custom DocPerms currently exist, which may include rows an admin
	added by hand that this feature must never touch. Returns the new record,
	as a JSON string, for the caller to persist.

	Pure enough to call directly on an unsaved doc: every side effect goes
	through `frappe.permissions`/`frappe.delete_doc` against the database, not
	through `settings.save()`, so a test can call this without ever saving
	Webstore Settings itself.
	"""
	desired = desired_grants(settings)
	applied = _load_applied(settings)

	if desired == applied:
		return _dump(applied)

	touched_doctypes = set()

	# Revoke first: anything the previous reconcile applied that the current
	# configuration no longer wants, for exactly the roles/ptypes it added.
	for doctype, roles_map in applied.items():
		for role, ptypes in roles_map.items():
			gone = set(ptypes) - set(desired.get(doctype, {}).get(role, []))
			if gone:
				_revoke(doctype, role, gone)
				touched_doctypes.add(doctype)

	# Then grant whatever is newly wanted.
	for doctype, roles_map in desired.items():
		for role, ptypes in roles_map.items():
			previously = set(applied.get(doctype, {}).get(role, []))
			if set(ptypes) - previously:
				_grant(doctype, role, ptypes)
				touched_doctypes.add(doctype)

	for doctype in touched_doctypes:
		frappe.clear_cache(doctype=doctype)

	return _dump(desired)
