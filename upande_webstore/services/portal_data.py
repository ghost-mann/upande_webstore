import frappe


def get_customer_addresses(customer):
	address_names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
		pluck="parent",
	)
	if not address_names:
		return []
	return frappe.get_all(
		"Address",
		filters={"name": ["in", address_names]},
		fields=["name", "address_title", "address_line1", "address_line2", "city", "country", "phone"],
		order_by="modified desc",
	)
