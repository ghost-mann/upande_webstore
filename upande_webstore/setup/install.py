import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DEFAULT_PRESET = "mona_flowers"

WEBSTORE_CUSTOM_FIELDS = {
	"Quotation": [
		{
			"fieldname": "webstore_section",
			"fieldtype": "Section Break",
			"label": "Webstore",
			"insert_after": "order_type",
			"collapsible": 1,
		},
		{
			"fieldname": "customer_po_reference",
			"fieldtype": "Data",
			"label": "Customer PO Reference",
			"insert_after": "webstore_section",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_notes",
			"fieldtype": "Small Text",
			"label": "Webstore Notes",
			"insert_after": "customer_po_reference",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_shipping_date",
			"fieldtype": "Date",
			"label": "Requested Shipping Date",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_dropoff_points",
			"fieldtype": "Small Text",
			"label": "Dropoff Points",
			"insert_after": "webstore_shipping_date",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_portal_status",
			"fieldtype": "Select",
			"label": "Portal Status",
			"options": "\nAccepted\nDeclined",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
	],
	# Direct webstore orders carry the customer's notes too. The PO reference
	# uses Sales Order's own standard po_no field rather than a custom one.
	"Sales Order": [
		{
			"fieldname": "webstore_section",
			"fieldtype": "Section Break",
			"label": "Webstore",
			"insert_after": "order_type",
			"collapsible": 1,
		},
		{
			"fieldname": "webstore_notes",
			"fieldtype": "Small Text",
			"label": "Webstore Notes",
			"insert_after": "webstore_section",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_dropoff_points",
			"fieldtype": "Small Text",
			"label": "Dropoff Points",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
		{
			"fieldname": "custom_has_mixed_boxes",
			"fieldtype": "Check",
			"label": "Mixed Box Grading",
			"insert_after": "webstore_dropoff_points",
			"default": "0",
		},
	],
	# Line-level box detail, on both the quotation and the order. `custom_`
	# rather than `webstore_` because these are the names ops already reads on
	# live; matching them is the point of sourcing box types from Items.
	"Quotation Item": [
		{
			# options is resolved per site by _resolved_fields(): the doctype a
			# farm keeps its box types in differs, and a Link cannot be shipped
			# pointing at one of them.
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	"Sales Order Item": [
		{
			# options is resolved per site by _resolved_fields(): the doctype a
			# farm keeps its box types in differs, and a Link cannot be shipped
			# pointing at one of them.
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	# Box types are Items, so the storefront and the packing floor share one
	# source. These two are `custom_`-prefixed rather than `webstore_` on
	# purpose: they are the field names ops already reads on live, where
	# upande_harvest created them. This is also what makes the feature
	# usable on a farm that has no harvest app to create them.
	# create_custom_fields *updates* fields that already exist rather than
	# skipping them, so create_webstore_custom_fields filters out everything the
	# site already has, whatever shape it is in.
	"Item": [
		{
			"fieldname": "custom_is_box",
			"fieldtype": "Check",
			"label": "Is Box",
			"insert_after": "stock_uom",
			"default": "0",
			"search_index": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_is_box",
			"description": "Stems this box holds. Leave at 0 and the storefront will not box-validate orders using it.",
		},
	],
}


def create_webstore_custom_fields():
	"""Create the fields this site is missing, and touch nothing it already has.

	`create_custom_fields` updates *every* changed property of an existing field,
	not only the ones we would think to compare. On Karen Roses that would repoint
	`Sales Order Item.custom_box_type` away from its own `Box Type` doctype and
	orphan 5,019 values, and flip `custom_number_of_boxes` and `Quotation
	Item.custom_pack_rate` to read-only under the staff who edit them today.
	None of those fields is ours, so the installer is create-only: existing means
	untouched, whatever shape it is in. Fields the site models differently are
	logged; ones matching our own definition are not, or every migrate of every
	site would file an Error Log entry nobody needs to read.

	Run twice on purpose. On a fresh site no box source resolves yet, so the
	first pass creates `Item.custom_is_box` and `Item.custom_pack_rate` and
	skips `custom_box_type` for want of anything to link to — and creating those
	two Item fields is itself what makes Items a box source. Re-resolving and
	running again lands `custom_box_type` now rather than at the next migrate.
	The second pass creates nothing on a site whose source already resolved.
	"""
	from upande_webstore.services import packing

	_create_missing_fields()
	packing.clear_box_source_cache()
	notable = _create_missing_fields()
	if notable:
		frappe.log_error(
			title="Webstore custom fields skipped",
			message=(
				"This site models these fields differently; left untouched:\n" + "\n".join(notable)
			),
		)


def _create_missing_fields():
	missing, notable = _only_missing(_resolved_fields())
	create_custom_fields(missing, ignore_validate=True)
	return notable


def _resolved_fields():
	"""Our definitions with `custom_box_type` pointed at this site's box source.

	The doctype box types live in is a property of the farm, so a `custom_box_type`
	we are about to create must Link to whatever `packing.get_box_source()`
	resolved — `Box Type` on Karen Roses, `Item` on Mona. Shipping a hardcoded
	`Item` here is how a site whose box source is `Box Type` ends up with a
	quotation field the checkout can never write to.

	With no source at all there is nothing to link to and packing is inert, so
	the field is not created. The other box fields are unconditional: they hold
	plain numbers and cost nothing on a site that never fills them.
	"""
	# deferred: services.packing pulls in the settings/doctype stack, which is
	# not importable at the point hooks load install.py during app installation
	from upande_webstore.services import packing

	source = packing.get_box_source()
	resolved = {}
	for doctype, fields in WEBSTORE_CUSTOM_FIELDS.items():
		keep = []
		for df in fields:
			if df["fieldname"] == "custom_box_type" and df["fieldtype"] == "Link":
				if not source:
					continue
				df = dict(df, options=source.doctype)
			keep.append(df)
		resolved[doctype] = keep
	return resolved


def _only_missing(definitions):
	"""Split our field definitions into (to create, existing and worth reporting).

	Reads the doctype's meta rather than the Custom Field table so a standard
	field of the same name counts as present too.

	Every existing field is skipped, but only the ones shaped differently from
	ours are returned for the log. A steady-state site skips all fifteen on every
	migrate; reporting those would put an Error Log entry on every migrate of
	every site and teach operators to ignore the one that matters.

	Consequence of being create-only: changing one of our *own* shipped field
	definitions no longer rides along on `migrate`. A site that already has the
	old shape keeps it until an explicit patch alters it.
	"""
	missing = {}
	notable = []
	for doctype, fields in definitions.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		keep = []
		for df in fields:
			existing = meta.get_field(df["fieldname"])
			if existing:
				if _differs(existing, df):
					notable.append(
						"{0}.{1}: site has {2}/{3}, we ship {4}/{5}".format(
							doctype,
							df["fieldname"],
							existing.fieldtype,
							existing.options or "-",
							df["fieldtype"],
							df.get("options") or "-",
						)
					)
				continue
			keep.append(df)
		if keep:
			missing[doctype] = keep
	return missing, notable


def _differs(existing, ours):
	"""A different fieldtype, or a Link/Table pointing somewhere else.

	No longer decides anything — the installer skips every existing field — but
	it is what makes the skip log worth reading: a field that matches our shape
	is uninteresting, one that does not is a farm modelling boxes its own way.
	"""
	if existing.fieldtype != ours["fieldtype"]:
		return True
	if ours["fieldtype"] in ("Link", "Table", "Table MultiSelect"):
		return (existing.options or "") != (ours.get("options") or "")
	return False


def seed_default_theme():
	"""Fresh installs get the default preset.

	A site whose theme is already configured is never touched, so deploying to
	an existing site cannot restyle it. Deliberately not called from
	after_migrate for that reason.
	"""
	if frappe.db.get_single_value("Webstore Settings", "accent"):
		return
	if frappe.get_all("Webstore Category Card", limit=1):
		return
	from upande_webstore.theme.transfer import apply_preset

	apply_preset(DEFAULT_PRESET)


def after_install():
	create_webstore_custom_fields()
	seed_default_theme()


def normalise_settings_docstatus():
	"""Force Webstore Settings' docstatus back to 0.

	The doctype is not submittable, but a stray docstatus of 2 in tabSingles
	makes the desk treat the record as a cancelled document and offer Amend
	instead of a plain Save. Something in the migrate path keeps re-setting it,
	so this runs on every migrate rather than as a one-time patch.
	"""
	if not frappe.db.exists("DocType", "Webstore Settings"):
		return
	current = frappe.db.sql(
		"select value from tabSingles where doctype = %s and field = 'docstatus'",
		"Webstore Settings",
	)
	if not current or str(current[0][0]) == "0":
		return
	frappe.db.sql(
		"update tabSingles set value = '0' where doctype = %s and field = 'docstatus'",
		"Webstore Settings",
	)
	frappe.clear_cache(doctype="Webstore Settings")


def after_migrate():
	create_webstore_custom_fields()
	normalise_settings_docstatus()
