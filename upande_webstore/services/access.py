"""Shared desk-endpoint permission guard.

Whitelisted endpoints used to hardcode `frappe.only_for(role)`, which meant a
farm had to grant that exact role name to reach a feature no matter what its
own DocPerms said — Webstore Product grants Sales Manager full access, but
`api/boxes.py`'s `frappe.only_for("System Manager")` still blocked a Sales
Manager from opening any product, because list_box_types is called on every
form refresh. Checking permission against the doctype an operation is
actually about, instead, means access follows that doctype's own DocPerms:
adding a role in the desk works with no code change.
"""

import frappe
from frappe import _


def require_permission(doctype, ptype="read"):
	"""Raise frappe.PermissionError unless the session user has `ptype` on `doctype`."""
	if not frappe.has_permission(doctype, ptype):
		frappe.throw(
			_("You do not have {0} permission for {1}").format(ptype, doctype),
			frappe.PermissionError,
		)
