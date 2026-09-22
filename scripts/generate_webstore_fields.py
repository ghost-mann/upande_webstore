"""Regenerate the `Webstore` doctype's per-store fields from `Webstore Settings`.

Run from the app root:

    python3 scripts/generate_webstore_fields.py

Every per-store field is a copy of the same field on `Webstore Settings`, so a
store's Checkout Mode offers exactly the options the site-wide one does and a
colour seed is the same Color control. Copying ~60 fields by hand is how
options, labels and link targets drift apart; this reads the source of truth
instead, and `tests/test_store_field_parity.py` fails if the committed result
stops matching.

Check fields become a blank/Enabled/Disabled Select, because a store has to be
able to say "off" as well as "inherit" — see services/store_fields.py.

The store's own identity fields (slug, title, published, theme_preset) have no
counterpart on the Single, so they are written out here rather than copied.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upande_webstore.services import store_fields as registry  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCTYPES = os.path.join(APP, "upande_webstore", "upande_webstore", "doctype")
SETTINGS = os.path.join(DOCTYPES, "webstore_settings", "webstore_settings.json")
WEBSTORE = os.path.join(DOCTYPES, "webstore", "webstore.json")

INHERIT = "Blank inherits Webstore Settings."

# Properties worth carrying across. Deliberately omits `reqd` and `default`:
# nothing a store overrides is mandatory, because blank is how it inherits.
COPIED = ("fieldtype", "label", "options", "precision")


def copy_field(source, fieldname):
	field = {"fieldname": fieldname}
	for key in COPIED:
		if source.get(key):
			field[key] = source[key]
	description = source.get("description")
	field["description"] = f"{description} {INHERIT}" if description else INHERIT
	return field


def tristate_field(source, fieldname):
	description = source.get("description")
	return {
		"fieldname": fieldname,
		"fieldtype": "Select",
		"label": source.get("label") or fieldname,
		"options": "\nEnabled\nDisabled",
		"description": (
			(f"{description} " if description else "")
			+ "Blank inherits Webstore Settings; Disabled turns this off for this "
			"store even when the site-wide setting is on."
		),
	}


def section(fieldname, label, description=None):
	field = {"fieldname": fieldname, "fieldtype": "Section Break", "label": label}
	if description:
		field["description"] = description
	return field


IDENTITY = [
	{
		"fieldname": "slug",
		"fieldtype": "Data",
		"label": "Slug",
		"reqd": 1,
		"unique": 1,
		"description": (
			"Lowercase URL prefix for this storefront — <code>flowers</code> serves "
			"/flowers/store. The default store's slug is <code>store</code>, which is "
			"what keeps /store working unchanged."
		),
	},
	{"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1},
	{
		"fieldname": "published",
		"fieldtype": "Check",
		"label": "Published",
		"default": "1",
		"description": "An unpublished store 404s for everyone but a System Manager, who can preview it.",
	},
	{
		"fieldname": "theme_preset",
		"fieldtype": "Data",
		"label": "Theme Preset",
		"read_only": 1,
		"description": "The last shipped preset applied to this store, if any.",
	},
]


def build(fields):
	"""The store's fields, laid out the way `Webstore Settings` lays out its own.

	Derived from the Single's field order rather than a layout invented here:
	walk its tabs, sections and columns, keep the per-store fields and drop
	everything else, then drop any section or tab left empty. An admin
	configuring a shop then sees the same tabs in the same order with the same
	headings as the site-wide form, minus the parts that cannot differ per
	shop — which is the whole reason the two forms should not be laid out
	independently.
	"""
	per_store = set(registry.ALL_PER_STORE_FIELDS)
	tristate = set(registry.PER_STORE_TRISTATE)
	source = {field["fieldname"]: field for field in fields}

	out = []
	for field in fields:
		kind = field["fieldtype"]
		if kind in ("Tab Break", "Section Break", "Column Break"):
			# structure is copied verbatim, then pruned below if nothing
			# per-store ended up inside it
			carried = {"fieldname": field["fieldname"], "fieldtype": kind}
			if field.get("label"):
				carried["label"] = field["label"]
			if field.get("description") and kind != "Column Break":
				carried["description"] = field["description"]
			out.append(carried)
		elif field["fieldname"] in per_store:
			name = field["fieldname"]
			out.append(
				tristate_field(source[name], name) if name in tristate else copy_field(source[name], name)
			)

	# An explicit first tab, so the store's own identity reads as a tab beside
	# the inherited ones rather than as a stray block above them.
	identity_tab = {"fieldname": "storefront_tab", "fieldtype": "Tab Break", "label": "Storefront"}
	return [identity_tab] + IDENTITY + _prune(out)


def _prune(fields):
	"""Drop structure that ends up holding nothing.

	Repeated until nothing more drops, because emptying a section can leave the
	tab above it empty in turn.
	"""
	def once(items):
		kept, changed = [], False
		for index, field in enumerate(items):
			kind = field["fieldtype"]
			if kind in ("Tab Break", "Section Break", "Column Break"):
				rest = items[index + 1 :]
				# what follows before the next break of the same or wider scope
				wider = {
					"Column Break": ("Column Break", "Section Break", "Tab Break"),
					"Section Break": ("Section Break", "Tab Break"),
					"Tab Break": ("Tab Break",),
				}[kind]
				holds = False
				for later in rest:
					if later["fieldtype"] in wider:
						break
					if later["fieldtype"] not in ("Tab Break", "Section Break", "Column Break"):
						holds = True
						break
				if not holds:
					changed = True
					continue
			kept.append(field)
		return kept, changed

	while True:
		fields, changed = once(fields)
		if not changed:
			return fields


def main():
	with open(SETTINGS) as handle:
		settings_fields = json.load(handle)["fields"]

	source = {field["fieldname"]: field for field in settings_fields}
	missing = [name for name in registry.ALL_PER_STORE_FIELDS if name not in source]
	if missing:
		raise SystemExit(f"not on Webstore Settings: {', '.join(missing)}")

	with open(WEBSTORE) as handle:
		doctype = json.load(handle)

	fields = build(settings_fields)
	doctype["fields"] = fields
	doctype["field_order"] = [field["fieldname"] for field in fields]

	with open(WEBSTORE, "w") as handle:
		json.dump(doctype, handle, indent=1, sort_keys=True)
		handle.write("\n")
	print(f"wrote {len(fields)} fields to {os.path.relpath(WEBSTORE, APP)}")


if __name__ == "__main__":
	main()
