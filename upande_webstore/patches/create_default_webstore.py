"""Give every existing single-store site a `Webstore` row before Task 2 ever
asks `current_store()` to resolve one from a path.

The new slug is deliberately "store": the existing `/store` URL and the new
per-store scheme then coincide, so nothing needs redirecting and a
single-store site keeps working with no manual step. The per-store fields and
child tables are copied off `Webstore Settings` as it stands right now, so the
merge in `services.settings.get_settings()` sees the same values it always
did — see that module's acceptance test.
"""

import frappe

DEFAULT_SLUG = "store"

#: Mirrors settings._OVERLAY_SCALARS — the same fields the merge treats as
#: per-store, copied verbatim so the migrated store overrides nothing new.
SCALAR_FIELDS = (
	"checkout_mode",
	"default_box_type",
	"minimum_order_stems",
)

#: `enable_box_packing` is deliberately not copied. On the Webstore row it is a
#: tri-state whose blank means inherit, so leaving it blank reproduces today's
#: behaviour exactly and keeps following Webstore Settings if an admin flips the
#: site-wide checkbox after migrating — copying it would silently freeze the
#: migrated store at whatever it happened to be on the day of the upgrade.
#:
#: `default_lead_days` is left out for the same reason, but for a plainer
#: cause: Webstore Settings ships it defaulting to 7, not 0/blank, so unlike
#: the fields above, "the current value" is essentially never the unset
#: state — copying it would freeze every migrated store at 7 (or whatever the
#: site had) and silently stop a later edit to Webstore Settings from ever
#: reaching checkout again. Leaving it blank keeps it inheriting indefinitely,
#: exactly like today.
TABLE_FIELDS = ("categories", "guest_price_lists", "warehouses")


def execute():
	if frappe.db.exists("DocType", "Webstore") and frappe.get_all("Webstore", limit=1):
		return
	if not frappe.db.exists("DocType", "Webstore Settings"):
		return

	settings = frappe.get_cached_doc("Webstore Settings")
	store = frappe.new_doc("Webstore")
	store.slug = DEFAULT_SLUG
	store.title = (settings.get("site_name") or "").strip() or "Store"
	store.published = 1
	for field in SCALAR_FIELDS:
		store.set(field, settings.get(field))
	for field in TABLE_FIELDS:
		for row in settings.get(field) or []:
			# no_default_fields, or the copy carries the source row's own name and
			# parent across and two child rows in the same table end up sharing a
			# primary key.
			store.append(field, row.as_dict(no_default_fields=True))
	store.flags.ignore_permissions = True
	store.insert()
