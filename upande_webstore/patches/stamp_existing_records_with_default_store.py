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

	# Only documents a cart actually produced. A blanket update would stamp
	# every quotation and order on the site — including ones a sales rep
	# raised in the desk that never touched a storefront — and custom_webstore
	# would stop meaning "this came from a shop" on its very first migration.
	# The cart's own webstore is used rather than the default, so this stays
	# correct if it ever runs on a site that already has several stores.
	for doctype, link_field in (("Quotation", "quotation"), ("Sales Order", "sales_order")):
		if not frappe.get_meta(doctype).get_field("custom_webstore"):
			continue
		frappe.db.sql(
			f"""
			update `tab{doctype}` doc
			join `tabWebstore Cart` cart on cart.{link_field} = doc.name
			set doc.custom_webstore = cart.webstore
			where ifnull(doc.custom_webstore, '') = '' and ifnull(cart.webstore, '') != ''
			"""
		)
