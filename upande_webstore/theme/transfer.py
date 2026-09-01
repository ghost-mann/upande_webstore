"""Theme JSON export/import and shipped presets.

Images travel as file URLs, not embedded bytes — embedding base64 would bloat
the payload past usefulness. import_theme therefore reports URLs that do not
resolve on the target site rather than silently rendering broken images.
"""

import json
import os
import re

import frappe
from frappe import _

from upande_webstore.theme.branding import DEFAULTS as BRANDING_DEFAULTS
from upande_webstore.theme.tokens import THEME_FIELDS

SCHEMA_VERSION = 1

PRESET_DIR = os.path.join(os.path.dirname(__file__), "presets")
PRESET_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# every branding scalar, plus the attachments which are not in DEFAULTS
BRANDING_FIELDS = tuple(BRANDING_DEFAULTS) + ("brand_logo", "favicon", "hero_image")

TABLE_FIELDS = ("hero_stats", "category_cards", "process_steps", "footer_links")

IMAGE_FIELDS = ("brand_logo", "favicon", "hero_image")

# child-table bookkeeping columns that must never travel in an export
ROW_META_FIELDS = frozenset(
	{
		"name",
		"parent",
		"parenttype",
		"parentfield",
		"idx",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"doctype",
	}
)


def _feature_fields():
	from upande_webstore.theme.features import FEATURES

	return tuple(feature.fieldname for feature in FEATURES)


def all_fields():
	return THEME_FIELDS + BRANDING_FIELDS + _feature_fields()


@frappe.whitelist()
def export_theme():
	frappe.only_for("System Manager")
	settings = frappe.get_doc("Webstore Settings")

	fields = {}
	for fieldname in all_fields():
		value = settings.get(fieldname)
		if value not in (None, ""):
			fields[fieldname] = value

	tables = {}
	for table in TABLE_FIELDS:
		rows = []
		for row in settings.get(table) or []:
			rows.append(
				{
					key: value
					for key, value in row.as_dict().items()
					if key not in ROW_META_FIELDS and value not in (None, "")
				}
			)
		tables[table] = rows

	return {"schema": SCHEMA_VERSION, "fields": fields, "tables": tables}


def _resolve_payload(payload):
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw(_("Theme payload is not valid JSON."))
	if not isinstance(payload, dict):
		frappe.throw(_("Theme payload must be a JSON object."))
	version = payload.get("schema")
	if version != SCHEMA_VERSION:
		frappe.throw(
			_("Unsupported theme schema version {0}; this site reads version {1}.").format(
				version, SCHEMA_VERSION
			)
		)
	return payload


def _field_default(meta, fieldname):
	"""The DocType's own default, so 'reset' means the same thing here as it does
	on a fresh record — feature checks back to 1, everything else to blank."""
	field = meta.get_field(fieldname)
	default = field.default if field else None
	if default in (None, ""):
		return 0 if field and field.fieldtype == "Check" else ""
	return default


@frappe.whitelist()
def import_theme(payload):
	"""Replace the theme wholesale.

	Fields and tables absent from the payload are reset to their DocType
	defaults rather than left as they were — otherwise switching presets would
	leave residue from the previous one, and the desk button promises this
	overwrites every Theme, Branding and Features value.
	"""
	frappe.only_for("System Manager")
	payload = _resolve_payload(payload)

	settings = frappe.get_doc("Webstore Settings")
	meta = frappe.get_meta("Webstore Settings")
	incoming = payload.get("fields") or {}
	applied_fields = []

	for fieldname in all_fields():
		if fieldname in incoming:
			settings.set(fieldname, incoming[fieldname])
			applied_fields.append(fieldname)
		else:
			settings.set(fieldname, _field_default(meta, fieldname))

	incoming_tables = payload.get("tables") or {}
	for table in TABLE_FIELDS:
		settings.set(table, [])
		for row in incoming_tables.get(table) or []:
			settings.append(table, {k: v for k, v in row.items() if k not in ROW_META_FIELDS})

	settings.flags.ignore_permissions = True
	settings.save()
	frappe.clear_cache()

	return {
		"applied": len(applied_fields),
		"applied_fields": applied_fields,
		"missing_images": missing_images(settings),
	}


def missing_images(settings=None):
	"""File URLs referenced by the theme that do not exist on this site."""
	if settings is None:
		settings = frappe.get_doc("Webstore Settings")
	candidates = [settings.get(field) for field in IMAGE_FIELDS]
	candidates += [row.image for row in settings.get("category_cards") or []]

	missing = []
	for url in candidates:
		if not url or not str(url).startswith(("/files/", "/private/files/")):
			continue
		if not frappe.db.exists("File", {"file_url": url}) and url not in missing:
			missing.append(url)
	return missing


@frappe.whitelist()
def list_presets():
	if not os.path.isdir(PRESET_DIR):
		return []
	return sorted(
		filename[: -len(".json")]
		for filename in os.listdir(PRESET_DIR)
		if filename.endswith(".json")
	)


@frappe.whitelist()
def apply_preset(name):
	frappe.only_for("System Manager")
	# the regex rejects '/', '.' and '%' outright, so no path can escape PRESET_DIR
	if not isinstance(name, str) or not PRESET_NAME_RE.match(name):
		frappe.throw(_("Invalid preset name."))
	path = os.path.join(PRESET_DIR, f"{name}.json")
	if not os.path.isfile(path):
		frappe.throw(_("No shipped preset named {0}.").format(name))
	with open(path, encoding="utf-8") as handle:
		return import_theme(json.load(handle))
