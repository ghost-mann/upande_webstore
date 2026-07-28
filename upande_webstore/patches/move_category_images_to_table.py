"""Move the three fixed category-image fields into the Webstore Category Card
child table, preserving the labels and subtitles the template hardcoded."""

import frappe

LEGACY_CARDS = (
	("flowers_category_image", "Flowers", "Roses, lilies & fillers", "Flowers"),
	("coffee_category_image", "Coffee", "AA & specialty grades", "Coffee"),
	("produce_category_image", "Fresh Produce", "Avocado & vegetables", "Fresh Produce"),
)


def execute():
	if not frappe.db.exists("DocType", "Webstore Category Card"):
		return
	if not frappe.db.exists("DocType", "Webstore Settings"):
		return

	settings = frappe.get_doc("Webstore Settings")

	# already migrated, or the admin has built their own cards — leave alone
	if settings.get("category_cards"):
		return

	legacy = {field: settings.get(field) for field, _label, _sub, _cat in LEGACY_CARDS}
	if not any(legacy.values()):
		# a site that never uploaded category images should not gain cards
		return

	for field, label, subtitle, category in LEGACY_CARDS:
		settings.append(
			"category_cards",
			{
				"label": label,
				"subtitle": subtitle,
				"image": legacy.get(field) or None,
				"category": category,
			},
		)
	settings.flags.ignore_permissions = True
	settings.flags.ignore_validate = True
	settings.save()
	frappe.clear_cache()
