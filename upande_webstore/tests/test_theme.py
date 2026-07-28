import unittest

from upande_webstore.theme import color


class TestColorPrimitives(unittest.TestCase):
	def test_parse_valid(self):
		self.assertEqual(color.parse("#166534"), (22, 101, 52))
		self.assertEqual(color.parse("  #FFFFFF  "), (255, 255, 255))

	def test_parse_rejects_invalid(self):
		for bad in (None, "", "#1f0", "green", "#16653g", 123, "#1665344"):
			self.assertIsNone(color.parse(bad), f"expected None for {bad!r}")

	def test_mix_returns_unrounded_floats(self):
		# chained mixes must not accumulate rounding error
		result = color.mix((0, 0, 0), (255, 255, 255), 0.5)
		self.assertEqual(result, (127.5, 127.5, 127.5))

	def test_to_hex_rounds_and_clamps(self):
		self.assertEqual(color.to_hex((127.5, 0, 255)), "#8000ff")
		self.assertEqual(color.to_hex((-10, 300, 128)), "#00ff80")

	def test_rgba(self):
		self.assertEqual(color.rgba((22, 101, 52), 0.35), "rgba(22, 101, 52, 0.35)")


class TestInkScale(unittest.TestCase):
	SHIPPED = {
		"ink": "#0a0a0a",
		"ink-1": "#1a1a18",
		"ink-2": "#2a2a26",
		"ink-3": "#3a3a34",
		"ink-4": "#5a5a52",
		"ink-mute": "#8a8780",
		"ink-faint": "#b8b6ae",
	}

	def test_collapses_to_single_ramp_without_muted(self):
		"""With muted unset the two segments must reduce EXACTLY to ink->canvas."""
		ink, canvas = (10, 10, 10), (244, 243, 239)
		scale = color.ink_scale(ink, None, canvas)
		expected = {}
		names = ("ink", "ink-1", "ink-2", "ink-3", "ink-4")
		for name, step in zip(names, color.INK_STEPS):
			expected[name] = color.to_hex(color.mix(ink, canvas, step))
		expected["ink-mute"] = color.to_hex(color.mix(ink, canvas, color.INK_MUTE))
		expected["ink-faint"] = color.to_hex(color.mix(ink, canvas, color.INK_FAINT))
		self.assertEqual(scale, expected)

	def test_within_regression_bound_of_shipped(self):
		"""Shipped scale was warm-shifted by eye; bound the divergence at 8."""
		scale = color.ink_scale((10, 10, 10), None, (244, 243, 239))
		for name, shipped_hex in self.SHIPPED.items():
			shipped = color.parse(shipped_hex)
			derived = color.parse(scale[name])
			worst = max(abs(a - b) for a, b in zip(shipped, derived))
			self.assertLessEqual(worst, 8, f"{name}: {shipped_hex} vs {scale[name]}")

	def test_muted_seed_survives_derivation(self):
		"""Mona's blue-shifted muted must be preserved exactly, not flattened."""
		scale = color.ink_scale((26, 26, 26), (135, 140, 156), (247, 248, 250))
		self.assertEqual(scale["ink-mute"], "#878c9c")
		self.assertEqual(scale["ink"], "#1a1a1a")
		# ink-4 sits between ink and muted, so it must be bluer than neutral gray
		r, g, b = color.parse(scale["ink-4"])
		self.assertGreater(b, r, "ink-4 should stay blue-shifted")

	def test_returns_empty_without_ink(self):
		self.assertEqual(color.ink_scale(None, None, (244, 243, 239)), {})


class TestAccentScale(unittest.TestCase):
	def test_backward_compatible_with_derive_brand_colors(self):
		"""These five values are pinned by the existing test_settings suite."""
		scale = color.accent_scale((22, 101, 52), None, None)
		self.assertEqual(scale["accent"], "#166534")
		self.assertEqual(scale["accent-hover"], "#13592e")
		self.assertEqual(scale["accent-soft"], "#ecf3ef")
		self.assertEqual(scale["accent-light"], "#508c67")
		self.assertEqual(scale["accent-deep"], "#104c27")
		self.assertEqual(scale["ring"], "rgba(22, 101, 52, 0.35)")

	def test_explicit_dark_and_soft_override_derivation(self):
		scale = color.accent_scale((30, 77, 140), (20, 53, 98), (232, 240, 251))
		self.assertEqual(scale["accent-deep"], "#143562")
		self.assertEqual(scale["accent-soft"], "#e8f0fb")

	def test_returns_empty_without_accent(self):
		self.assertEqual(color.accent_scale(None, None, None), {})


class TestSurfaceScale(unittest.TestCase):
	def test_opaque_hairlines_when_border_seeds_given(self):
		scale = color.surface_scale(
			(26, 26, 26), (247, 248, 250), (238, 240, 244), (226, 230, 237), (197, 203, 214)
		)
		self.assertEqual(scale["hairline"], "#e2e6ed")
		self.assertEqual(scale["hairline-strong"], "#c5cbd6")
		self.assertEqual(scale["wash"], "#eef0f4")
		self.assertEqual(scale["bg"], "#f7f8fa")

	def test_alpha_hairlines_when_border_seeds_absent(self):
		scale = color.surface_scale((10, 10, 10), (244, 243, 239), None, None, None)
		self.assertEqual(scale["hairline"], "rgba(10, 10, 10, 0.06)")
		self.assertEqual(scale["hairline-strong"], "rgba(10, 10, 10, 0.12)")
		self.assertEqual(scale["wash"], "rgba(10, 10, 10, 0.04)")

	def test_surface_is_a_lift_toward_white(self):
		"""--ws-surface must sit BETWEEN canvas and white, never below canvas."""
		canvas = (247, 248, 250)
		scale = color.surface_scale((26, 26, 26), canvas, None, None, None)
		# banker's rounding: 252.5 -> 252, hence fc not fd on the blue channel
		self.assertEqual(scale["surface"], "#fbfcfc")
		self.assertEqual(scale["card"], "#ffffff")
		# the property the literal above is standing in for
		for channel, base in zip(color.parse(scale["surface"]), canvas):
			self.assertGreaterEqual(channel, base)
			self.assertLessEqual(channel, 255)

	def test_wash_is_sunken_below_canvas(self):
		"""Mona's second surface is DARKER than the canvas: a fill, not a lift."""
		scale = color.surface_scale(
			(26, 26, 26), (247, 248, 250), (238, 240, 244), None, None
		)
		for channel, base in zip(color.parse(scale["wash"]), (247, 248, 250)):
			self.assertLess(channel, base)

	def test_shadows_use_ink_seed_not_hardcoded_black(self):
		scale = color.surface_scale((30, 77, 140), (247, 248, 250), None, None, None)
		self.assertIn("rgba(30, 77, 140", scale["shadow-card"])


class TestStatusScale(unittest.TestCase):
	def test_derives_deep_and_soft(self):
		scale = color.status_scale((45, 106, 79))
		self.assertEqual(scale["base"], "#2d6a4f")
		self.assertEqual(scale["deep"], "#285d46")
		self.assertEqual(scale["soft"], "rgba(45, 106, 79, 0.12)")

	def test_returns_empty_without_seed(self):
		self.assertEqual(color.status_scale(None), {})
