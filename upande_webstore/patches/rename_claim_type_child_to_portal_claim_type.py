"""Free the name `Webstore Claim Type` for the standalone master.

The claim type list used to be a child table of that name inside Portal
Settings. It is now a master doctype, so the child becomes `Webstore Portal
Claim Type` — a selector holding a Link to it.

This has to run in **pre_model_sync**: sync would otherwise try to create a
standalone doctype whose name the child still holds, and the two cannot
coexist. Renaming first leaves the name free, and the child's rows keep their
values because only the doctype is renamed, not its data.

Seeding the master from those values happens afterwards, in
install.seed_claim_types(), which after_migrate calls once the new doctype
exists.
"""

import frappe
from frappe.model.rename_doc import rename_doc

OLD = "Webstore Claim Type"
NEW = "Webstore Portal Claim Type"


def execute():
	if not frappe.db.exists("DocType", OLD):
		return
	if frappe.db.exists("DocType", NEW):
		# a re-run, or a site that already has both: nothing to free
		return
	if not frappe.db.get_value("DocType", OLD, "istable"):
		# already the master — this site was installed after the split
		return
	# frappe.rename_doc is the whitelisted wrapper and takes no
	# ignore_permissions; the model-level one does, and a patch has no user
	# session to check against.
	rename_doc("DocType", OLD, NEW, force=True, ignore_permissions=True)
	frappe.db.commit()
