import math
import unittest

from upande_webstore.services.charts import (
	area_path,
	donut_segments,
	nice_ceiling,
	points_attr,
	scale_points,
	spark_points,
)


class TestCharts(unittest.TestCase):
	def test_nice_ceiling(self):
		self.assertEqual(nice_ceiling(0), 1)
		self.assertEqual(nice_ceiling(-5), 1)
		self.assertEqual(nice_ceiling(7), 10)
		self.assertEqual(nice_ceiling(19), 20)
		self.assertEqual(nice_ceiling(23), 25)
		self.assertEqual(nice_ceiling(4200), 5000)
		self.assertEqual(nice_ceiling(100), 100)

	def test_scale_points_empty(self):
		self.assertEqual(scale_points([], 600, 280), [])

	def test_scale_points_single_value_renders_flat_segment(self):
		points = scale_points([50], 100, 100, vmax=100)
		self.assertEqual(len(points), 2)
		self.assertEqual(points[0][1], points[1][1])
		self.assertEqual(points[0][0], 0)
		self.assertEqual(points[1][0], 100)

	def test_scale_points_all_zero_sits_on_baseline(self):
		points = scale_points([0, 0, 0], 300, 100, pad_bottom=10)
		self.assertTrue(all(y == 90 for _x, y in points))

	def test_scale_points_scales_to_vmax(self):
		points = scale_points([0, 100], 100, 100, vmax=100)
		self.assertEqual(points[0][1], 100)
		self.assertEqual(points[1][1], 0)

	def test_points_attr(self):
		self.assertEqual(points_attr([(0, 1.5), (2, 3)]), "0,1.5 2,3")

	def test_area_path_closes_to_baseline(self):
		points = scale_points([10, 20], 100, 100, pad_bottom=20)
		path = area_path(points, 100, pad_bottom=20)
		self.assertTrue(path.startswith("M0,80 L"))
		self.assertTrue(path.endswith("L100,80 Z"))
		self.assertEqual(area_path([], 100), "")

	def test_spark_points_is_svg_attr(self):
		attr = spark_points([1, 2, 3])
		self.assertRegex(attr, r"^[\d.,]+ [\d.,]+ [\d.,]+$")

	def test_donut_segments_empty_and_zero(self):
		self.assertEqual(donut_segments([]), [])
		self.assertEqual(donut_segments([{"label": "Open", "value": 0, "color": "#000"}]), [])

	def test_donut_single_segment_fills_ring(self):
		segments = donut_segments([{"label": "Open", "value": 4, "color": "#000"}], radius=80)
		self.assertEqual(len(segments), 1)
		self.assertAlmostEqual(segments[0]["length"], 2 * math.pi * 80, delta=0.1)

	def test_donut_segments_sum_to_circumference(self):
		gap = 2.5
		segments = donut_segments(
			[
				{"label": "Open", "value": 5, "color": "#d9a514"},
				{"label": "Accepted", "value": 3, "color": "#3f8f4f"},
				{"label": "Expired", "value": 0, "color": "#8a8780"},
				{"label": "Declined", "value": 2, "color": "#c4302b"},
			],
			radius=80,
			gap=gap,
		)
		self.assertEqual(len(segments), 3)  # zero-value dropped
		total = sum(segment["length"] + gap for segment in segments)
		self.assertAlmostEqual(total, 2 * math.pi * 80, delta=0.1)
		self.assertEqual(segments[0]["offset"], -gap / 2)
