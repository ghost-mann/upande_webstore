import frappe

from upande_webstore.services.catalog import get_products
from upande_webstore.theme.features import guard


@frappe.whitelist(allow_guest=True)
@guard("search_palette")
def search_products(q=None):
	"""Lightweight product search for the command palette (top 8 matches)."""
	q = (q or "").strip()
	if len(q) < 2:
		return []
	result = get_products(search=q, page_length=8)
	return [
		{
			"web_title": p["web_title"],
			"route": p["route"],
			"item": p["item"],
			"image": p["image"],
			"category": p["category"],
			"rate": (p["price"] or {}).get("rate"),
			"currency": (p["price"] or {}).get("currency"),
			"in_stock": (p["stock"] or {}).get("in_stock", True),
			"has_variants": p["has_variants"],
		}
		for p in result["products"]
	]
