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
	details = get_item_details(args)
	rate = details.get("rate") or details.get("price_list_rate") or 0.0
	return {
		"rate": float(rate),
		"currency": currency,
		"price_list": price_list,
		"is_customer_price": is_customer_price,
	}
