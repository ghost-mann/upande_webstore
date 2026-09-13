"""Give every record from before Task 2 a `webstore` value, so isolation
starts from "everything is the default store" rather than from "nothing is
any store" - the same reasoning patches.create_default_webstore used for the
store row itself.

Requires create_default_webstore to have already run - if the default store
does not exist, there is nothing to stamp records with, and this is a no-op
exactly like that patch's own guard.

Quotation/Sales Order need `custom_webstore` before they can be stamped, and
that field is created by the installer's after_migrate hook, which runs
*after* post_model_sync patches - so this calls the installer itself first.
create_webstore_custom_fields() is idempotent and create-only (see
setup/install.py), so calling it early here is safe and is what lets a single
migrate both create the field and back-fill it, rather than needing a second
migrate to catch up.
"""

import frappe

from upande_webstore.services.store import DEFAULT_SLUG


def execute():
	if not frappe.db.exists("Webstore", DEFAULT_SLUG):
		return

	frappe.db.sql(
		"update `tabWebstore Product` set primary_store = %s where ifnull(primary_store, '') = ''",
		DEFAULT_SLUG,
	)
	frappe.db.sql(
		"update `tabWebstore Cart` set webstore = %s where ifnull(webstore, '') = ''",
		DEFAULT_SLUG,
	)
	frappe.db.sql(
		"update `tabWebstore Wishlist` set webstore = %s where ifnull(webstore, '') = ''",
		DEFAULT_SLUG,
	)

	from upande_webstore.setup.install import create_webstore_custom_fields

	create_webstore_custom_fields()

	for doctype in ("Quotation", "Sales Order"):
		if not frappe.get_meta(doctype).get_field("custom_webstore"):
			continue
		frappe.db.sql(
			f"update `tab{doctype}` set custom_webstore = %s where ifnull(custom_webstore, '') = ''",
			DEFAULT_SLUG,
		)
