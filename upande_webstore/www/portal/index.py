from upande_webstore.services import charts
from upande_webstore.services.portal import get_customer_docs, portal_page_context
from upande_webstore.services.portal_data import (
	get_monthly_spend,
	get_quotation_mix,
	get_spend_totals,
	get_top_items,
)

CHART_W, CHART_H = 600, 280
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 46, 12, 16, 40

MIX_SEGMENTS = (
	("Open", "ws-donut-open"),
	("Accepted", "ws-donut-accepted"),
	("Declined", "ws-donut-declined"),
	("Expired", "ws-donut-expired"),
)


def _axis_label(value):
	if value >= 1_000_000:
		return f"{value / 1_000_000:g}M"
	if value >= 1_000:
		return f"{value / 1_000:g}k"
	return f"{value:g}"


def _spend_chart(spend):
	invoiced = [month["invoiced"] for month in spend]
	paid = [month["paid"] for month in spend]
	vmax = charts.nice_ceiling(max(invoiced + paid))
	pads = dict(
		pad_left=PAD_LEFT, pad_right=PAD_RIGHT, pad_top=PAD_TOP, pad_bottom=PAD_BOTTOM, vmax=vmax
	)
	invoiced_pts = charts.scale_points(invoiced, CHART_W, CHART_H, **pads)
	paid_pts = charts.scale_points(paid, CHART_W, CHART_H, **pads)
	plot_h = CHART_H - PAD_TOP - PAD_BOTTOM
	ticks = [
		{"value": _axis_label(vmax), "y": PAD_TOP},
		{"value": _axis_label(vmax / 2), "y": PAD_TOP + plot_h / 2},
	]
	marks = []
	for i, month in enumerate(spend):
		marks.append({
			"label": month["label"],
			"x": invoiced_pts[i][0],
			"y_invoiced": invoiced_pts[i][1],
			"y_paid": paid_pts[i][1],
			"invoiced": month["invoiced"],
			"paid": month["paid"],
			"show_label": i % 2 == 1,
		})
	return {
		"width": CHART_W,
		"height": CHART_H,
		"baseline": CHART_H - PAD_BOTTOM,
		"pad_left": PAD_LEFT,
		"has_data": any(invoiced) or any(paid),
		"invoiced_points": charts.points_attr(invoiced_pts),
		"invoiced_area": charts.area_path(invoiced_pts, CHART_H, PAD_BOTTOM),
		"paid_points": charts.points_attr(paid_pts),
		"ticks": ticks,
		"marks": marks,
	}


def get_context(context):
	portal_page_context(context, "/portal", "dashboard")
	context.balance = context.portal_balance
	context.currency = context.portal_currency

	spend = get_monthly_spend(12)
	context.spend_chart = _spend_chart(spend)
	context.spend_spark = charts.spark_points([month["invoiced"] for month in spend])
	context.spend_totals = get_spend_totals(12)

	mix = get_quotation_mix()
	context.quotation_mix = [
		{"label": label, "value": mix.get(label, 0), "css": css} for label, css in MIX_SEGMENTS
	]
	context.quotation_total = sum(mix.values())
	context.quotation_donut = charts.donut_segments(
		[dict(segment) for segment in context.quotation_mix], radius=80
	)

	context.top_items = get_top_items(5)
	context.recent_orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "grand_total", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=6,
		order_by="transaction_date desc",
	)
	return context
