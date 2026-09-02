import frappe

from upande_webstore.services.settings import get_settings

# Name matches what it holds: the resolved Price List, not the currency the
# picker displays. The picker offers currencies, but resolution needs a price
# list, and the table's own uniqueness rule (at most one row per currency)
# means the two are interchangeable — storing the price list saves every
# reader a currency->price-list lookup on top of the cookie read.
GUEST_PRICE_LIST_COOKIE = "webstore_price_list"


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


def get_offered_price_lists(settings=None):
	"""Configured guest price lists that are still valid right now.

	Re-checked live rather than trusting validate-time checks alone: a price
	list can be disabled, or flipped to buying-only, after it was added to the
	table, and a stale row must stop being offered rather than silently keep
	resolving. Order follows the table (a farm's own row order), except that
	callers needing the default should look at `is_default`, not position.
	"""
	settings = settings or get_settings()
	rows = []
	for row in settings.guest_price_lists or []:
		info = frappe.db.get_value(
			"Price List", row.price_list, ["enabled", "selling", "currency"], as_dict=True
		)
		if not info or not info.enabled or not info.selling:
			continue
		rows.append(
			frappe._dict(
				price_list=row.price_list,
				label=row.label or info.currency,
				currency=info.currency,
				is_default=bool(row.is_default),
			)
		)
	return rows


def _cookie_price_list():
	# A cookie just set on the outgoing response is not yet the incoming
	# request's cookie — the browser only sends it back on the *next*
	# request, after the reload the picker triggers. Without this override,
	# api.pricing.set_price_list's own call to _reprice(cart) would still
	# resolve against the price list the visitor is switching *away* from,
	# because request.cookies still holds whatever it arrived with. The
	# override is frappe.local, so it lives only for the current request/job
	# and never leaks into the next one.
	override = getattr(frappe.local, "webstore_guest_price_list_override", None)
	if override:
		return override
	request = getattr(frappe.local, "request", None)
	if not request:
		return None
	return request.cookies.get(GUEST_PRICE_LIST_COOKIE) or None


def _remember_price_list(price_list):
	"""Write the resolved choice back to the cookie, when there is a response
	to carry it on (a real request; not a console session or a background job).

	Only ever called to correct a cookie that failed to resolve, so a forged
	or stale value does not keep failing the same check on every request —
	the next one starts from a value that is actually valid.
	"""
	manager = getattr(frappe.local, "cookie_manager", None)
	if manager:
		manager.set_cookie(GUEST_PRICE_LIST_COOKIE, price_list)


def resolve_guest_price_list(settings=None):
	"""The guest-facing half of get_price_list's resolution order: cookie
	choice, if it names an offered row, else the row marked default, else the
	first row. Returns None when the table is empty — the caller falls back
	to the legacy single `guest_price_list`.

	The cookie is never trusted on its own: a value naming a price list not
	(or no longer) in the table is exactly the same as no cookie at all. That
	is what stops a visitor reading an unpublished price list by setting a
	cookie by hand — this function is the one place that check happens, so
	every caller gets it for free.
	"""
	offered = get_offered_price_lists(settings)
	if not offered:
		return None
	by_name = {row.price_list: row for row in offered}
	cookie_value = _cookie_price_list()
	if cookie_value and cookie_value in by_name:
		return cookie_value
	default_row = next((row for row in offered if row.is_default), offered[0])
	if cookie_value:
		# the cookie named something no longer offered; heal it now rather
		# than re-failing this same check on every request until it changes
		_remember_price_list(default_row.price_list)
	return default_row.price_list


def get_price_list(user=None):
	customer = get_customer(user)
	if customer:
		price_list = frappe.db.get_value("Customer", customer, "default_price_list")
		if price_list:
			return price_list
	resolved = resolve_guest_price_list()
	if resolved:
		return resolved
	return get_settings().guest_price_list


def get_guest_currency_picker(user=None):
	"""Storefront picker payload, or None when there is nothing to pick.

	None covers three cases: fewer than two price lists offered (nothing to
	choose between), and a visitor whose linked customer already has a
	negotiated price list — their price is not theirs to change, and a
	control that would do nothing is worse than no control.
	"""
	customer = get_customer(user)
	if customer and frappe.db.get_value("Customer", customer, "default_price_list"):
		return None
	offered = get_offered_price_lists()
	if len(offered) < 2:
		return None
	return {
		"options": [
			{"price_list": row.price_list, "label": row.label, "currency": row.currency}
			for row in offered
		],
		"current": resolve_guest_price_list(),
	}


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
