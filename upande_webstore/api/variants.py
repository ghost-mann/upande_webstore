import json

import frappe

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


@frappe.whitelist(allow_guest=True)
def get_attributes(template_item):
	# Item is not readable by Guest/Customer on newer frappe; the storefront
	# must not require exposing it, so read only has_variants directly and
	# pull the attribute rows via frappe.get_all (also permission-independent)
	# rather than loading the Item document for its child table.
	if not frappe.db.get_value("Item", template_item, "has_variants"):
		return []
	result = []
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": template_item, "parenttype": "Item"},
		fields=["attribute"],
		order_by="idx",
	):
		values = frappe.get_all(
			"Item Attribute Value",
			filters={"parent": row.attribute},
			pluck="attribute_value",
			order_by="idx",
		)
		result.append({"attribute": row.attribute, "values": values})
	return result


@frappe.whitelist(allow_guest=True)
def resolve_variant(template_item, attributes):
	from erpnext.controllers.item_variant import find_variant

	if isinstance(attributes, str):
		attributes = json.loads(attributes)
	variant = find_variant(template_item, attributes)
	if not variant:
		return {"item_code": None}
	return {
		"item_code": variant,
		"price": get_item_price(variant),
		"stock": get_stock_info(variant),
	}
