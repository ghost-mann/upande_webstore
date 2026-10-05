import json

import frappe

from upande_webstore.services.pricing import get_item_price, get_priced_variants
from upande_webstore.services.stock import get_stock_info


@frappe.whitelist(allow_guest=True)
def get_attributes(template_item):
	# Item is not readable by Guest/Customer on newer frappe; the storefront
	# must not require exposing it, so read only has_variants directly and
	# pull the attribute rows via frappe.get_all (also permission-independent)
	# rather than loading the Item document for its child table.
	if not frappe.db.get_value("Item", template_item, "has_variants"):
		return []
	# offer only values a customer can buy: an attribute like Stem Length lists
	# every grade the farm could cut, but a variety is priced at a few. A
	# template priced on no variant (not priced yet, or priced by length on
	# the template) keeps the values its enabled variants carry.
	variants = frappe.get_all(
		"Item", filters={"variant_of": template_item, "disabled": 0}, pluck="name"
	)
	offered = (get_priced_variants(variants) or set(variants)) if variants else set()
	carried = {}
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", list(offered) or [""]], "parenttype": "Item"},
		fields=["attribute", "attribute_value"],
	):
		carried.setdefault(row.attribute, set()).add(row.attribute_value)

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
		result.append({
			"attribute": row.attribute,
			"values": [v for v in values if v in carried.get(row.attribute, ())],
		})
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
