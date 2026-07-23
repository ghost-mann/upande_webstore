"""Pure SVG geometry for the portal's server-rendered charts.

Templates stay declarative: controllers call these helpers and pass
ready-made point strings / segment lists into the Jinja context. No frappe
imports — everything here is unit-testable without a site.
"""

import math


def nice_ceiling(value):
	"""Smallest 'nice' number (1 / 2 / 2.5 / 5 x 10^k) >= value; 1 for <= 0."""
	if value <= 0:
		return 1
	exponent = math.floor(math.log10(value))
	magnitude = 10**exponent
	for factor in (1, 2, 2.5, 5, 10):
		if factor * magnitude >= value:
			return factor * magnitude
	return 10 * magnitude


def scale_points(values, width, height, pad_left=0, pad_right=0, pad_top=0, pad_bottom=0, vmax=None):
	"""Scale a series into plot coordinates. Returns a list of (x, y) floats.

	Empty -> []. A single value renders as a flat two-point segment so a
	polyline is still visible. All-zero series sit on the baseline.
	"""
	values = [float(v or 0) for v in values]
	if not values:
		return []
	if len(values) == 1:
		values = values * 2
	if vmax is None:
		vmax = max(values)
	vmax = max(float(vmax), 1e-9)
	plot_w = width - pad_left - pad_right
	plot_h = height - pad_top - pad_bottom
	step = plot_w / (len(values) - 1)
	return [
		(
			round(pad_left + i * step, 1),
			round(pad_top + plot_h * (1 - min(v, vmax) / vmax), 1),
		)
		for i, v in enumerate(values)
	]


def _fmt(value):
	return f"{value:g}"


def points_attr(points):
	"""(x, y) list -> SVG points attribute string."""
	return " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)


def area_path(points, height, pad_bottom=0):
	"""Close a scaled point list down to the baseline as an SVG path."""
	if not points:
		return ""
	baseline = _fmt(height - pad_bottom)
	steps = " L".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
	return f"M{_fmt(points[0][0])},{baseline} L{steps} L{_fmt(points[-1][0])},{baseline} Z"


def spark_points(values, width=80, height=30, pad=3):
	"""Corner-sparkline points attribute for a KPI card."""
	return points_attr(scale_points(values, width, height, pad, pad, pad, pad))


def donut_segments(items, radius=80, gap=2.5):
	"""Ring segments for the template's stroke-dasharray donut technique.

	items: [{"label", "value", "color"}, ...]; zero-value items are dropped.
	Returns segments with dasharray/dashoffset for a circle of `radius`
	rotated -90deg, keeping a `gap`-length spacer between segments (none
	when a single segment fills the ring).
	"""
	circumference = 2 * math.pi * radius
	kept = [dict(item) for item in items if (item.get("value") or 0) > 0]
	total = sum(item["value"] for item in kept)
	if not total:
		return []
	if len(kept) == 1:
		gap = 0
	start = 0.0
	segments = []
	for item in kept:
		raw = item["value"] / total * circumference
		item["length"] = round(max(raw - gap, 0.5), 2)
		item["offset"] = round(-(start + gap / 2), 2)
		item["circumference"] = round(circumference, 2)
		start += raw
		segments.append(item)
	return segments
