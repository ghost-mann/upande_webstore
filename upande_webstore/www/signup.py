import frappe


def get_context(context):
	from upande_webstore.theme.features import require

	require("signup")
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/portal"
		raise frappe.Redirect
	context.no_cache = 1
	return context
