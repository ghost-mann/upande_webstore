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

from upande_webstore.services.access import require_permission
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



def _target(webstore=None):
	"""The document a transfer reads from or writes to.

	Without a store this is the site-wide Single, exactly as before multi-store
	existed. With one it is that `Webstore` row, so a preset can dress the
	flower shop without touching the dairy one beside it.
	"""
	if not webstore:
		return frappe.get_doc("Webstore Settings")
	if not frappe.db.exists("Webstore", webstore):
		frappe.throw(_("No storefront with slug {0}.").format(webstore))
	return frappe.get_doc("Webstore", webstore)



def _effective(webstore):
	"""`get_settings()` as the given store would see it, resolved off to one
	side so exporting one shop's look never changes what the current request
	is rendering."""
	from upande_webstore.services.settings import get_settings
	from upande_webstore.services.store import clear_store_cache

	previous_slug = getattr(frappe.local, "webstore_slug", None)
	previous_merged = getattr(frappe.local, "webstore_merged_settings", None)
	frappe.local.webstore_slug = webstore
	frappe.local.webstore_merged_settings = None
	clear_store_cache()
	try:
		return get_settings()
	finally:
		frappe.local.webstore_slug = previous_slug
		frappe.local.webstore_merged_settings = previous_merged
		clear_store_cache()


def _permission_doctype(webstore=None):
	return "Webstore" if webstore else "Webstore Settings"


def _writable_fields(target):
	"""The transfer's own field list, narrowed to what this target actually
	has. A `Webstore` carries no portal feature flags — the portal is shared
	across every store — so a payload naming one has nothing to write it to."""
	meta = frappe.get_meta(target.doctype)
	return tuple(name for name in all_fields() if meta.get_field(name))


def _to_target_value(target, fieldname, value):
	"""A checkbox on the Single is a three-state Select on a store, so 1 and 0
	have to become Enabled and Disabled on the way in — see
	services/store_fields.py for why a store needs the third state at all."""
	from upande_webstore.services.store_fields import PER_STORE_TRISTATE

	if target.doctype == "Webstore" and fieldname in PER_STORE_TRISTATE:
		if value in (None, ""):
			return ""
		return "Enabled" if str(value) not in ("0", "False") else "Disabled"
	return value


def _reset_value(target, meta, fieldname):
	"""What a field absent from the payload becomes.

	On the Single: the DocType default, so "reset" means what it does on a
	fresh record. On a store: blank, which is how a store says "inherit the
	site" — a preset that sets no hero heading should leave the shop showing
	the site's, not an empty one.
	"""
	if target.doctype == "Webstore":
		return ""
	return _field_default(meta, fieldname)

@frappe.whitelist()
def export_theme(webstore=None):
	"""The theme as a storefront actually renders it.

	With a store, that is its *effective* look — its own overrides on top of
	whatever it inherits — because "copy this shop's appearance" means the
	appearance a visitor sees, not the half of it the shop happens to state
	itself.
	"""
	require_permission(_permission_doctype(webstore))
	if webstore:
		_target(webstore)  # 404s an unknown slug before anything is read
		settings = _effective(webstore)
	else:
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
def import_theme(payload, webstore=None):
	"""Replace the theme wholesale, site-wide or for one storefront.

	Fields and tables absent from the payload are reset rather than left as
	they were — otherwise switching presets would leave residue from the
	previous one, and the desk button promises this overwrites every Theme,
	Branding and Features value. "Reset" means the DocType default on the
	Single and blank on a store, blank being how a store inherits.
	"""
	require_permission(_permission_doctype(webstore), "write")
	payload = _resolve_payload(payload)

	settings = _target(webstore)
	meta = frappe.get_meta(settings.doctype)
	incoming = payload.get("fields") or {}
	applied_fields = []

	for fieldname in _writable_fields(settings):
		if fieldname in incoming:
			settings.set(fieldname, _to_target_value(settings, fieldname, incoming[fieldname]))
			applied_fields.append(fieldname)
		else:
			settings.set(fieldname, _reset_value(settings, meta, fieldname))

	incoming_tables = payload.get("tables") or {}
	for table in TABLE_FIELDS:
		if not meta.get_field(table):
			continue
		settings.set(table, [])
		for row in incoming_tables.get(table) or []:
			settings.append(table, {k: v for k, v in row.items() if k not in ROW_META_FIELDS})

	settings.flags.ignore_permissions = True
	# A theme write touches only Theme, Branding and Features fields — whether
	# the farm has chosen a company or a guest price list is none of its
	# business, and both are reqd. Without this, apply_preset on a fresh
	# install (seed_default_theme, before either is ever set) throws
	# MandatoryError and after_install aborts partway: the app registers and
	# its custom fields land, but the site never gets its default theme.
	settings.flags.ignore_mandatory = True
	settings.save()
	frappe.clear_cache()
	# the resolved store is cached on frappe.local for the request, so a write
	# to it has to be re-read or the page rendering next still shows the old look
	from upande_webstore.services.store import clear_store_cache

	clear_store_cache()
	frappe.local.webstore_merged_settings = None

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
def apply_preset(name, webstore=None):
	require_permission(_permission_doctype(webstore), "write")
	# the regex rejects '/', '.' and '%' outright, so no path can escape PRESET_DIR
	if not isinstance(name, str) or not PRESET_NAME_RE.match(name):
		frappe.throw(_("Invalid preset name."))
	path = os.path.join(PRESET_DIR, f"{name}.json")
	if not os.path.isfile(path):
		frappe.throw(_("No shipped preset named {0}.").format(name))
	with open(path, encoding="utf-8") as handle:
		result = import_theme(json.load(handle), webstore=webstore)
	if webstore:
		# recorded on the store so the desk can say which preset a shop is
		# wearing — import_theme resets theme_preset along with everything else
		frappe.db.set_value("Webstore", webstore, "theme_preset", name)
		frappe.clear_cache()
	return result
