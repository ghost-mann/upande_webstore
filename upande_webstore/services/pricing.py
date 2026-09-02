import frappe

from upande_webstore.services.settings import get_settings


def get_customer(user=None):
	"""Customer linked to the user via their Contact, or None."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact_name:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
		"link_name",
	)


def get_price_list(user=None):
	customer = get_customer(user)
	if customer:
		price_list = frappe.db.get_value("Customer", customer, "default_price_list")
		if price_list:
			return price_list
	return get_settings().guest_price_list


def get_item_price(item_code, qty=1, user=None):
	"""Server-resolved price. Never trust client prices."""
	from erpnext.stock.get_item_details import get_item_details

	settings = get_settings()
	customer = get_customer(user)
	price_list = get_price_list(user)
	is_customer_price = bool(
		customer and frappe.db.get_value("Customer", customer, "default_price_list") == price_list
	)
	currency = frappe.db.get_value("Price List", price_list, "currency")
	args = frappe._dict({
		"doctype": "Quotation",
		"item_code": item_code,
		"qty": qty or 1,
		"transaction_type": "selling",
		"company": settings.company,
		"selling_price_list": price_list,
		"price_list": price_list,
		"customer": customer,
		"currency": currency,
		"price_list_currency": currency,
		"conversion_rate": 1,
		"plc_conversion_rate": 1,
		"ignore_pricing_rule": 0,
		"transaction_date": frappe.utils.nowdate(),
	})
	# ERPNext's get_item_details unconditionally loads the Item document
	# (frappe.get_cached_doc), which Item is not readable by Guest for on
	# newer frappe — and the storefront must not require exposing it. That
	# helper is out of this app's control, but it (like frappe's own
	# permission checks) honours frappe.flags.ignore_permissions, so this
	# only ever bypasses the Item read for the duration of the call, then
	# restores whatever the flag was before.
	previous_ignore_permissions = frappe.flags.ignore_permissions
	frappe.flags.ignore_permissions = True
	try:
		details = get_item_details(args)
	finally:
		frappe.flags.ignore_permissions = previous_ignore_permissions
	rate = details.get("rate") or details.get("price_list_rate") or 0.0
	return {
		"rate": float(rate),
		"currency": currency,
		"price_list": price_list,
		"is_customer_price": is_customer_price,
	}


def get_variant_price_range(template_item, user=None):
	"""Cheapest and dearest published variant of a template.

	A template has no price of its own, so a catalogue of templates showed no
	price at all — useless for a grower whose whole range is graded varieties.
	One query against the resolved price list rather than pricing each variant.
	"""
	variants = frappe.get_all(
		"Item", filters={"variant_of": template_item, "disabled": 0}, pluck="name"
	)
	if not variants:
		return None

	def rates_in(price_list):
		# deliberately not filtering on `selling`: the flag is derived from the
		# price list when ERPNext creates the row, but an imported or
		# scripted Item Price can arrive without it, and excluding those made
		# templates look priceless
		found = frappe.get_all(
			"Item Price",
			filters={"item_code": ["in", variants], "price_list": price_list},
			pluck="price_list_rate",
			ignore_permissions=True,
		)
		return [rate for rate in found if rate]

	price_list = get_price_list(user)
	rates = rates_in(price_list)
	if not rates:
		# a customer price list may cover only some items; showing the public
		# price beats showing none at all
		fallback = get_settings().guest_price_list
		if fallback and fallback != price_list:
			rates = rates_in(fallback)
			if rates:
				price_list = fallback
	if not rates:
		return None

	return {
		"min": min(rates),
		"max": max(rates),
		"currency": frappe.db.get_value("Price List", price_list, "currency"),
		"price_list": price_list,
		"variants": len(variants),
	}
