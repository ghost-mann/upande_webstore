import json

import frappe

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


@frappe.whitelist(allow_guest=True)
def get_attributes(template_item):
	template = frappe.get_cached_doc("Item", template_item)
	if not template.has_variants:
		return []
	result = []
	for row in template.attributes:
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
