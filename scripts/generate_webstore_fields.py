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


def build(source):
	"""The doctype's fields, laid out the way someone setting up a shop works:
	who it is, what it looks like, what it says, what it sells, what it offers."""
	scalars = {name: copy_field(source[name], name) for name in registry.PER_STORE_SCALARS}
	tables = {name: copy_field(source[name], name) for name in registry.PER_STORE_TABLES}
	tristates = {name: tristate_field(source[name], name) for name in registry.PER_STORE_TRISTATE}

	features = [
		tristates[name]
		for name in registry.PER_STORE_TRISTATE
		if name not in ("accent_drives_primary", "enable_box_packing")
	]

	groups = (
		(section("identity_section", "Identity"), IDENTITY),
		(
			section("theme_section", "Theme", f"Colour, type and shape seeds for this store. {INHERIT}"),
			[scalars[name] for name in registry.THEME_SEEDS] + [tristates["accent_drives_primary"]],
		),
		(
			section("occasion_section", "Occasion", f"A seasonal campaign for this store alone. {INHERIT}"),
			[scalars[name] for name in registry.OCCASION_FIELDS],
		),
		(
			section("branding_section", "Branding & Copy", f"What this shop calls itself and says. {INHERIT}"),
			[
				scalars[name]
				for name in registry.IDENTITY_FIELDS + registry.HERO_FIELDS + registry.COPY_FIELDS
			]
			+ [tables[name] for name in registry.BRANDING_TABLES],
		),
		(
			section("commerce_section", "Catalogue & Pricing", f"What this shop sells and for how much. {INHERIT}"),
			[scalars[name] for name in registry.COMMERCE_FIELDS]
			+ [tables[name] for name in registry.COMMERCE_TABLES]
			+ [tristates["enable_box_packing"]],
		),
		(
			section(
				"features_section",
				"Features",
				"Turn a storefront feature on or off for this store alone. "
				f"{INHERIT} The portal is shared across every store, so its own "
				"features are not listed here.",
			),
			features,
		),
	)

	fields = []
	for header, members in groups:
		fields.append(header)
		fields.extend(members)
	return fields


def main():
	with open(SETTINGS) as handle:
		source = {field["fieldname"]: field for field in json.load(handle)["fields"]}

	missing = [name for name in registry.ALL_PER_STORE_FIELDS if name not in source]
	if missing:
		raise SystemExit(f"not on Webstore Settings: {', '.join(missing)}")

	with open(WEBSTORE) as handle:
		doctype = json.load(handle)

	fields = build(source)
	doctype["fields"] = fields
	doctype["field_order"] = [field["fieldname"] for field in fields]

	with open(WEBSTORE, "w") as handle:
		json.dump(doctype, handle, indent=1, sort_keys=True)
		handle.write("\n")
	print(f"wrote {len(fields)} fields to {os.path.relpath(WEBSTORE, APP)}")


if __name__ == "__main__":
	main()
