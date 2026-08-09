# Occasion Theme Overlays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship six seasonal theme overlays (Valentine's, Women's Day, Mother's Day, Easter, All Saints, Christmas) that recolour the storefront, add a cutoff banner and override hero copy, without ever writing to a farm's saved theme.

**Architecture:** Occasions are farm-agnostic JSON files in `theme/occasions/`. `theme/occasion.py` loads and validates one, `theme/tokens.py` merges its colour seeds *before* derivation, `theme/branding.py` merges its hero copy, and `theme/__init__.py` resolves it once per request. Activation writes nothing — deactivating is clearing a field.

**Tech Stack:** Frappe v16 / ERPNext v16, Python 3.11+, Jinja templates, SCSS bundled by `bench build`, TypeScript (`webstore.bundle.ts`).

**Spec:** `docs/superpowers/specs/2026-08-09-occasion-theme-overlays-design.md`

## Global Constraints

- Tabs for indentation in Python, matching every existing module in this app.
- Occasion files carry **no dates** — Mother's Day and Easter move by market and year.
- Occasions may set only `accent`, `accent_dark`, `accent_soft`, `canvas`, `wash`. Never `ink`, borders, fonts, radii, status colours or `custom_css`.
- Activating an occasion must never write to Webstore Settings.
- A missing or malformed occasion file must never raise to the storefront.
- Occasion fields must stay out of `transfer.all_fields()`.
- Run tests with:
  ```bash
  flatpak-spawn --host bash -lc 'rsync -a --delete --exclude .git ~/vscodeProjects/upande_webstore/upande_webstore/ ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/ && cd ~/frappe-v16-bench && bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_occasion'
  ```

---

### Task 1: `theme/occasion.py` — load, validate, whitelist

**Files:**
- Create: `upande_webstore/theme/occasion.py`
- Create: `upande_webstore/theme/occasions/valentines.json`
- Test: `upande_webstore/tests/test_occasion.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION: int`, `SEED_GROUPS: dict[str, tuple[str, ...]]`, `SEED_FIELDS: frozenset[str]`, `HERO_FIELDS: dict[str, str]`, `BANNER_OVERRIDES: dict[str, str]`, `list_names() -> list[str]`, `load(name: str) -> dict | None`

- [ ] **Step 1: Write the failing tests**

`upande_webstore/tests/test_occasion.py`:

```python
import unittest

from upande_webstore.theme import occasion


class TestLoad(unittest.TestCase):
	def test_loads_a_shipped_occasion(self):
		loaded = occasion.load("valentines")
		self.assertEqual(loaded["name"], "valentines")
		self.assertEqual(loaded["label"], "Valentine's Day")
		self.assertEqual(loaded["seeds"]["accent"], "#b3122d")

	def test_unknown_name_returns_none(self):
		self.assertIsNone(occasion.load("no_such_occasion"))

	def test_path_traversal_is_rejected(self):
		self.assertIsNone(occasion.load("../presets/mona_flowers"))
		self.assertIsNone(occasion.load("valentines.json"))

	def test_non_string_name_returns_none(self):
		self.assertIsNone(occasion.load(None))

	def test_list_names_includes_shipped(self):
		self.assertIn("valentines", occasion.list_names())
```

- [ ] **Step 2: Run to verify it fails**

Run the command in Global Constraints.
Expected: FAIL — `ModuleNotFoundError: upande_webstore.theme.occasion`

- [ ] **Step 3: Write `theme/occasion.py`**

```python
"""Seasonal overlays applied on top of a site's own theme.

An occasion is a shipped file, never a per-site record: one app serves many
farms, so Valentine's is authored once and reused. Activating one writes
nothing to Webstore Settings — the overlay resolves at render time, so
switching it off is clearing a field and a campaign can never damage the base
theme it sits on.
"""

import json
import os
import re

import frappe

SCHEMA_VERSION = 1

OCCASION_DIR = os.path.join(os.path.dirname(__file__), "occasions")
NAME_RE = re.compile(r"^[a-z0-9_]+$")

# Seeds an occasion may set, grouped so a group is taken or left whole. Mona
# seeds accent_soft explicitly, and without atomic groups that blue tint would
# survive under an occasion's red accent.
SEED_GROUPS = {
	"accent": ("accent", "accent_dark", "accent_soft"),
	"surface": ("canvas", "wash"),
}

SEED_FIELDS = frozenset(field for group in SEED_GROUPS.values() for field in group)

# occasion hero key -> Webstore Settings branding field
HERO_FIELDS = {
	"eyebrow": "hero_eyebrow",
	"heading": "hero_heading",
	"heading_em": "hero_heading_em",
	"body": "hero_body",
	"cta_primary": "hero_cta_primary",
}

BANNER_FIELDS = ("text", "cta_label", "cta_url")

# farm override field -> the banner key it replaces
BANNER_OVERRIDES = {
	"occasion_banner_text": "text",
	"occasion_banner_cta_label": "cta_label",
	"occasion_banner_cta_url": "cta_url",
}


def list_names():
	if not os.path.isdir(OCCASION_DIR):
		return []
	return sorted(
		filename[: -len(".json")]
		for filename in os.listdir(OCCASION_DIR)
		if filename.endswith(".json")
	)


def load(name):
	"""The validated occasion, or None if it cannot be used.

	Returns None rather than raising at every failure: a storefront must not
	500 because a farm points at an occasion this app version stopped shipping.
	The caller decides whether a given None is worth logging.
	"""
	# the regex rejects '/', '.' and '%' outright, so no path can escape the dir
	if not isinstance(name, str) or not NAME_RE.match(name):
		return None
	path = os.path.join(OCCASION_DIR, f"{name}.json")
	if not os.path.isfile(path):
		return None
	try:
		with open(path, encoding="utf-8") as handle:
			raw = json.load(handle)
	except (OSError, ValueError):
		return None
	if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_VERSION:
		return None

	seeds = raw.get("seeds") or {}
	banner = raw.get("banner") or {}
	hero = raw.get("hero") or {}
	return {
		"name": name,
		"label": raw.get("label") or name,
		# the whitelist is what stops a shipped file reaching custom_css, the
		# status colours or the type scale on every farm running this app
		"seeds": {k: v for k, v in seeds.items() if k in SEED_FIELDS and v},
		"banner": {k: v for k, v in banner.items() if k in BANNER_FIELDS and v},
		"hero": {k: v for k, v in hero.items() if k in HERO_FIELDS and v},
	}
```

- [ ] **Step 4: Write `theme/occasions/valentines.json`**

```json
{
  "schema": 1,
  "label": "Valentine's Day",
  "seeds": {
    "accent": "#b3122d",
    "accent_dark": "#7d0c1f",
    "accent_soft": "#fdeef0"
  },
  "banner": {
    "text": "Valentine's — book your February allocation early",
    "cta_label": "Talk to us",
    "cta_url": "/portal/quotations"
  },
  "hero": {
    "eyebrow": "Valentine's · February allocation",
    "heading": "Red Naomi, graded and",
    "heading_em": "booked for February",
    "cta_primary": "Reserve stems"
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/theme/occasion.py upande_webstore/theme/occasions/ upande_webstore/tests/test_occasion.py
git commit -m "feat(theme): occasion file loading with a seed whitelist"
```

---

### Task 2: The remaining five occasion files + integrity and contrast gates

**Files:**
- Create: `upande_webstore/theme/occasions/{womens_day,mothers_day,easter,all_saints,christmas}.json`
- Modify: `upande_webstore/tests/test_occasion.py`

**Interfaces:**
- Consumes: `occasion.load`, `occasion.list_names`, `occasion.SEED_FIELDS` (Task 1)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occasion.py`:

```python
from upande_webstore.theme import color

STATUS_SEEDS = ("success", "warning", "danger", "info")


class TestShippedOccasions(unittest.TestCase):
	def loaded(self):
		return [occasion.load(name) for name in occasion.list_names()]

	def test_all_six_ship(self):
		self.assertEqual(
			set(occasion.list_names()),
			{"valentines", "womens_day", "mothers_day", "easter", "all_saints", "christmas"},
		)

	def test_every_file_parses_and_is_labelled(self):
		for loaded in self.loaded():
			self.assertIsNotNone(loaded)
			self.assertTrue(loaded["label"])
			self.assertNotEqual(loaded["label"], loaded["name"])

	def test_every_seed_is_whitelisted_and_valid_hex(self):
		for loaded in self.loaded():
			for field, value in loaded["seeds"].items():
				self.assertIn(field, occasion.SEED_FIELDS)
				self.assertIsNotNone(color.parse(value), f"{loaded['name']}.{field}")

	def test_no_occasion_touches_a_status_colour(self):
		for loaded in self.loaded():
			for seed in STATUS_SEEDS:
				self.assertNotIn(seed, loaded["seeds"])

	def test_every_accent_clears_wcag_aa(self):
		"""on-accent is contrast-picked across the CTA gradient, so a bad accent
		fails here rather than on a farm's live site."""
		for loaded in self.loaded():
			accent = color.parse(loaded["seeds"].get("accent"))
			if not accent:
				continue
			scale = color.accent_scale(
				accent,
				color.parse(loaded["seeds"].get("accent_dark")),
				color.parse(loaded["seeds"].get("accent_soft")),
			)
			deep = color.parse(scale["accent-deep"])
			chosen = color.best_contrast((deep, accent), (color.BLACK, color.WHITE))
			worst = min(color.contrast(bg, chosen) for bg in (deep, accent))
			self.assertGreaterEqual(worst, 4.5, f"{loaded['name']} accent fails AA")
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL on `test_all_six_ship` — only `valentines` exists.

- [ ] **Step 3: Write the five files**

`womens_day.json`:
```json
{
  "schema": 1,
  "label": "Women's Day",
  "seeds": { "accent": "#a86b00", "accent_dark": "#7a4d00", "accent_soft": "#fdf3e0" },
  "banner": { "text": "International Women's Day — 8 March. Reserve your mixed and yellow lines now.", "cta_label": "Request a quotation", "cta_url": "/portal/quotations" },
  "hero": { "eyebrow": "Women's Day · 8 March", "heading": "Yellow and mixed,", "heading_em": "graded for the March peak", "cta_primary": "Browse varieties" }
}
```

`mothers_day.json`:
```json
{
  "schema": 1,
  "label": "Mother's Day",
  "seeds": { "accent": "#a8386a", "accent_dark": "#7a2850", "accent_soft": "#fceef4" },
  "banner": { "text": "Mother's Day — pastel and soft-pink lines are booking now.", "cta_label": "Request a quotation", "cta_url": "/portal/quotations" },
  "hero": { "eyebrow": "Mother's Day · spring allocation", "heading": "Soft pinks and creams,", "heading_em": "cut for Mother's Day", "cta_primary": "Browse varieties" }
}
```

`easter.json`:
```json
{
  "schema": 1,
  "label": "Easter",
  "seeds": { "accent": "#2f7d5c", "accent_dark": "#205740", "accent_soft": "#e9f5ef" },
  "banner": { "text": "Easter — whites, greens and pastels available for spring programmes.", "cta_label": "Request a quotation", "cta_url": "/portal/quotations" },
  "hero": { "eyebrow": "Easter · spring programme", "heading": "Whites and fresh greens,", "heading_em": "cut for the spring table", "cta_primary": "Browse varieties" }
}
```

`all_saints.json`:
```json
{
  "schema": 1,
  "label": "All Saints / Toussaint",
  "seeds": { "accent": "#5c4c72", "accent_dark": "#3f3450", "accent_soft": "#f1eef6" },
  "banner": { "text": "All Saints — 1 November. Book your Toussaint volumes with us.", "cta_label": "Request a quotation", "cta_url": "/portal/quotations" },
  "hero": { "eyebrow": "All Saints · 1 November", "heading": "Muted tones and whites,", "heading_em": "shipped for Toussaint", "cta_primary": "Browse varieties" }
}
```

`christmas.json`:
```json
{
  "schema": 1,
  "label": "Christmas",
  "seeds": { "accent": "#8f1a25", "accent_dark": "#63111a", "accent_soft": "#f8ebec", "canvas": "#faf7f2", "wash": "#f0ebe3" },
  "banner": { "text": "Christmas — December volumes are allocating now.", "cta_label": "Request a quotation", "cta_url": "/portal/quotations" },
  "hero": { "eyebrow": "Christmas · December allocation", "heading": "Deep reds and evergreen,", "heading_em": "allocated for December", "cta_primary": "Browse varieties" }
}
```

- [ ] **Step 4: Run tests to verify they pass**

If `test_every_accent_clears_wcag_aa` fails for a palette, darken that accent until the worst-case ratio clears 4.5 — do not lower the threshold.

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/occasions/ upande_webstore/tests/test_occasion.py
git commit -m "feat(theme): five more occasions, with a WCAG gate on every accent"
```

---

### Task 3: Merge occasion seeds in `tokens.get_tokens`

**Files:**
- Modify: `upande_webstore/theme/tokens.py:61-129`
- Modify: `upande_webstore/tests/test_occasion.py`

**Interfaces:**
- Consumes: `occasion.SEED_GROUPS` (Task 1)
- Produces: `tokens.get_tokens(settings, occasion=None) -> dict`, `tokens.COLOR_FIELDS: tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occasion.py`:

```python
from upande_webstore.theme import tokens

MONA = {
	"accent": "#1e4d8c",
	"accent_dark": "#143562",
	"accent_soft": "#e8f0fb",
	"ink": "#1a1a1a",
	"ink_muted": "#878c9c",
	"canvas": "#f7f8fa",
	"wash": "#eef0f4",
	"success": "#2d6a4f",
	"danger": "#b42318",
}


class TestSeedMerge(unittest.TestCase):
	def test_no_occasion_leaves_tokens_untouched(self):
		self.assertEqual(tokens.get_tokens(MONA), tokens.get_tokens(MONA, None))

	def test_occasion_accent_drives_the_whole_derived_ramp(self):
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["accent"], "#b3122d")
		self.assertEqual(out["accent-deep"], "#7d0c1f")
		# the derived tokens must follow the occasion, not stay Mona-blue
		self.assertNotEqual(out["accent-hover"], tokens.get_tokens(MONA)["accent-hover"])
		self.assertIn("179, 18, 45", out["ring"])

	def test_farm_accent_soft_does_not_survive_an_occasion_accent(self):
		"""Mona seeds a blue accent_soft; under a red accent that would clash."""
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["accent-soft"], "#fdeef0")
		self.assertNotEqual(out["accent-soft"], "#e8f0fb")

	def test_group_omitted_by_the_occasion_keeps_the_farm_value(self):
		"""valentines sets no surface group, so Mona's canvas survives."""
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["bg"], "#f7f8fa")

	def test_occasion_surface_group_replaces_the_farm_canvas(self):
		out = tokens.get_tokens(MONA, occasion.load("christmas"))
		self.assertEqual(out["bg"], "#faf7f2")

	def test_status_colours_are_never_touched(self):
		base = tokens.get_tokens(MONA)
		for name in occasion.list_names():
			out = tokens.get_tokens(MONA, occasion.load(name))
			for token in ("success", "destructive"):
				self.assertEqual(out[token], base[token], f"{name} moved {token}")
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `get_tokens() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Modify `theme/tokens.py`**

Add after the `THEME_FIELDS` tuple:

```python
# the colour subset of THEME_FIELDS — the only seeds an occasion can move
COLOR_FIELDS = (
	"accent",
	"accent_dark",
	"accent_soft",
	"ink",
	"ink_muted",
	"canvas",
	"wash",
	"border",
	"border_strong",
	"success",
	"warning",
	"danger",
	"info",
)
```

Replace `_seed` and the head of `get_tokens`:

```python
def _seed(values, field):
	return color.parse(values.get(field))


def _seed_values(settings, active_occasion):
	"""Colour seeds after the occasion overlay.

	Groups are replaced whole: an occasion that sets `accent` owns accent_dark
	and accent_soft too, blank meaning re-derive. Merging here rather than over
	the finished tokens is what makes the derived ramp — hover, deep, ring and
	the contrast-picked on-accent — follow the occasion instead of the farm.
	"""
	values = {field: settings.get(field) for field in COLOR_FIELDS}
	if not active_occasion:
		return values

	from upande_webstore.theme.occasion import SEED_GROUPS

	seeds = active_occasion.get("seeds") or {}
	for group in SEED_GROUPS.values():
		if any(seeds.get(field) for field in group):
			for field in group:
				values[field] = seeds.get(field) or ""
	return values


def get_tokens(settings, occasion=None):
	out = {}
	values = _seed_values(settings, occasion)

	ink = _seed(values, "ink")
	canvas = _seed(values, "canvas")
	muted = _seed(values, "ink_muted")
```

Then update every remaining `_seed(settings, ...)` call in `get_tokens` to `_seed(values, ...)` — there are seven: `wash`, `border`, `border_strong`, `accent`, `accent_dark`, `accent_soft`, and the `field` inside the `STATUS_TOKENS` loop.

`settings.get(...)` calls for the shape fields, `accent_drives_primary` and fonts stay as they are — occasions cannot touch those.

- [ ] **Step 4: Run tests to verify they pass**

Also run the existing theme suite to confirm nothing regressed:
```bash
flatpak-spawn --host bash -lc 'cd ~/frappe-v16-bench && bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_theme'
```

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/tokens.py upande_webstore/tests/test_occasion.py
git commit -m "feat(theme): merge occasion seeds before derivation, per atomic group"
```

---

### Task 4: Hero copy overlay in `branding.get_branding`

**Files:**
- Modify: `upande_webstore/theme/branding.py:90-135`
- Modify: `upande_webstore/tests/test_occasion.py`

**Interfaces:**
- Consumes: `occasion.HERO_FIELDS` (Task 1)
- Produces: `branding.get_branding(settings=None, occasion=None) -> frappe._dict`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occasion.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestHeroOverlay(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_occasion_hero_beats_the_farms_own_copy(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.hero_heading = "Graded roses,"
		settings.hero_eyebrow = "Mona Flowers · Eldoret, Kenya"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		resolved = get_branding(settings, occasion.load("valentines"))
		self.assertEqual(resolved["hero_heading"], "Red Naomi, graded and")
		self.assertEqual(resolved["hero_eyebrow"], "Valentine's · February allocation")

	def test_farm_copy_survives_keys_the_occasion_omits(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.hero_body = "Export-grade roses from our Eldoret farm."
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		# valentines.json carries no hero body
		resolved = get_branding(settings, occasion.load("valentines"))
		self.assertEqual(resolved["hero_body"], "Export-grade roses from our Eldoret farm.")

	def test_no_occasion_is_unchanged(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(
			get_branding(settings)["hero_heading"], get_branding(settings, None)["hero_heading"]
		)
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `get_branding() takes from 0 to 1 positional arguments but 2 were given`

- [ ] **Step 3: Modify `theme/branding.py`**

Change the signature and append the overlay just before `return resolved`:

```python
def get_branding(settings=None, occasion=None):
```

```python
	# the occasion speaks last: an overlay whose whole purpose is seasonal copy
	# has to beat the evergreen hero a farm keeps the rest of the year
	if occasion:
		from upande_webstore.theme.occasion import HERO_FIELDS

		hero = occasion.get("hero") or {}
		for key, field in HERO_FIELDS.items():
			if hero.get(key):
				resolved[field] = hero[key]

	return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/branding.py upande_webstore/tests/test_occasion.py
git commit -m "feat(theme): occasion hero copy overrides the farm's evergreen hero"
```

---

### Task 5: `active()`, request wiring, and the Settings fields

**Files:**
- Modify: `upande_webstore/theme/occasion.py`
- Modify: `upande_webstore/theme/__init__.py:10-24`
- Modify: `upande_webstore/services/settings.py:65-76`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py:9-15`
- Modify: `upande_webstore/tests/utils.py:30-38`
- Modify: `upande_webstore/tests/test_occasion.py`

**Interfaces:**
- Consumes: `occasion.load`, `occasion.BANNER_OVERRIDES` (Task 1)
- Produces: `occasion.active(settings=None) -> frappe._dict | None`, `occasion.list_occasions() -> list[dict]`, `context.webstore_occasion`

- [ ] **Step 1: Add the five DocType fields**

In `webstore_settings.json`, insert into `field_order` immediately after `radius_panel` and before `advanced_section`:

```
"occasion_section", "occasion", "occasion_runs_until", "occasion_cb",
"occasion_banner_text", "occasion_banner_cta_label", "occasion_banner_cta_url",
```

And add the matching entries to `fields`, placed after the `radius_panel` field object:

```json
{ "fieldname": "occasion_section", "fieldtype": "Section Break", "label": "Occasion" },
{ "fieldname": "occasion", "fieldtype": "Autocomplete", "label": "Active Occasion", "description": "Seasonal overlay on top of the theme above. Blank means none." },
{ "fieldname": "occasion_runs_until", "fieldtype": "Date", "label": "Runs Until", "description": "After this date the overlay stops applying. Nothing is written back." },
{ "fieldname": "occasion_cb", "fieldtype": "Column Break" },
{ "fieldname": "occasion_banner_text", "fieldtype": "Data", "label": "Banner Text", "description": "Overrides the occasion's own wording — put your cutoff date here." },
{ "fieldname": "occasion_banner_cta_label", "fieldtype": "Data", "label": "Banner CTA Label" },
{ "fieldname": "occasion_banner_cta_url", "fieldtype": "Data", "label": "Banner CTA Link" }
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_occasion.py`:

```python
from frappe.utils import add_days, nowdate


class TestActive(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def set_occasion(self, **values):
		settings = frappe.get_doc("Webstore Settings")
		for field, value in values.items():
			settings.set(field, value)
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		return settings

	def test_blank_is_none(self):
		self.assertIsNone(occasion.active(self.set_occasion(occasion="")))

	def test_named_occasion_resolves(self):
		active = occasion.active(self.set_occasion(occasion="valentines"))
		self.assertEqual(active.name, "valentines")
		self.assertEqual(active.banner["cta_label"], "Talk to us")

	def test_future_end_date_still_resolves(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_runs_until=add_days(nowdate(), 3)
		)
		self.assertIsNotNone(occasion.active(settings))

	def test_todays_end_date_still_resolves(self):
		settings = self.set_occasion(occasion="valentines", occasion_runs_until=nowdate())
		self.assertIsNotNone(occasion.active(settings))

	def test_past_end_date_stops_the_overlay(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_runs_until=add_days(nowdate(), -1)
		)
		self.assertIsNone(occasion.active(settings))

	def test_farm_banner_text_beats_the_file(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_banner_text="Cutoff 20 January — order now"
		)
		self.assertEqual(occasion.active(settings).banner["text"], "Cutoff 20 January — order now")

	def test_blank_override_falls_back_to_the_file(self):
		settings = self.set_occasion(occasion="valentines", occasion_banner_text="   ")
		self.assertIn("February allocation", occasion.active(settings).banner["text"])

	def test_activation_writes_nothing(self):
		"""The overlay is resolved, never persisted — that is what makes it safe
		to switch off without a restore step."""
		self.set_occasion(occasion="valentines")
		occasion.active()
		self.assertEqual(frappe.db.get_single_value("Webstore Settings", "accent") or "", "")

	def test_unknown_name_does_not_raise(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.occasion = "no_such_occasion"
		settings.flags.ignore_validate = True
		settings.db_set("occasion", "no_such_occasion")
		frappe.clear_cache()
		self.assertIsNone(occasion.active(frappe.get_doc("Webstore Settings")))

	def test_validate_rejects_an_unknown_occasion(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.occasion = "no_such_occasion"
		self.assertRaises(frappe.ValidationError, settings.save)


class TestIsolationFromTransfer(unittest.TestCase):
	def test_occasion_fields_are_not_theme_fields(self):
		"""Campaign state is not theme state: importing a base theme must not
		kill a running campaign, and exporting must not carry a farm's date."""
		from upande_webstore.theme.transfer import all_fields

		fields = set(all_fields())
		for field in ("occasion", "occasion_runs_until", *occasion.BANNER_OVERRIDES):
			self.assertNotIn(field, fields)


class TestContext(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_theme_exposes_the_occasion(self):
		from upande_webstore.theme import get_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.occasion = "valentines"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		theme = get_theme()
		self.assertEqual(theme.occasion.name, "valentines")
		self.assertEqual(theme.tokens["accent"], "#b3122d")
		self.assertEqual(theme.branding["hero_heading"], "Red Naomi, graded and")
```

- [ ] **Step 3: Run to verify it fails**

Expected: FAIL — `module 'upande_webstore.theme.occasion' has no attribute 'active'`

- [ ] **Step 4: Add `active()` and `list_occasions()` to `theme/occasion.py`**

```python
def _expired(settings):
	runs_until = settings.get("occasion_runs_until")
	if not runs_until:
		return False
	# inclusive: an occasion set to run until today is still live today
	return frappe.utils.getdate(runs_until) < frappe.utils.getdate(frappe.utils.nowdate())


def active(settings=None):
	"""The occasion in force, or None. Never raises."""
	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	name = (settings.get("occasion") or "").strip()
	if not name or _expired(settings):
		return None

	occasion = load(name)
	if occasion is None:
		# named but unusable, which is worth a log — unlike a blank field
		frappe.log_error(
			f"Webstore occasion {name!r} could not be loaded", "Webstore Occasion"
		)
		return None

	banner = dict(occasion["banner"])
	for field, key in BANNER_OVERRIDES.items():
		value = (settings.get(field) or "").strip()
		if value:
			banner[key] = value
	# a CTA needs both halves — a bare URL renders a link with no words
	if not (banner.get("cta_url") and banner.get("cta_label")):
		banner.pop("cta_url", None)
		banner.pop("cta_label", None)
	# wording is the banner; a CTA alone has nothing to sit beside
	occasion["banner"] = banner if banner.get("text") else {}
	return frappe._dict(occasion)


@frappe.whitelist()
def list_occasions():
	"""[{value, label}] for the desk Autocomplete."""
	frappe.only_for("System Manager")
	return [
		{"value": name, "label": (load(name) or {}).get("label") or name}
		for name in list_names()
	]
```

- [ ] **Step 5: Wire it into the request**

`theme/__init__.py`:

```python
def get_theme(settings=None):
	from upande_webstore.theme import branding, features, fonts, occasion, tokens

	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	# resolved once and shared, so a page costs one file read rather than two
	current = occasion.active(settings)

	return frappe._dict(
		tokens=tokens.get_tokens(settings, current),
		custom_css=tokens.get_custom_css(settings),
		font_link=fonts.resolve(settings)["link"],
		branding=branding.get_branding(settings, current),
		features=features.enabled(),
		occasion=current,
	)
```

`services/settings.py`, in `update_website_context`:

```python
	context.webstore_occasion = theme.occasion
```

`webstore_settings.py`, add to `validate` and define the method:

```python
		self.validate_occasion()
```

```python
	def validate_occasion(self):
		if not self.occasion:
			return
		from upande_webstore.theme import occasion

		if self.occasion not in occasion.list_names():
			frappe.throw(_("No shipped occasion named {0}.").format(self.occasion))
```

- [ ] **Step 6: Reset occasion fields between tests**

`tests/utils.py`, inside `setup_webstore_settings` after the `THEME_FIELDS` loop:

```python
	# occasion state is deliberately outside THEME_FIELDS, so it needs its own
	# reset or a campaign set by one test module leaks into the next
	for field in (
		"occasion",
		"occasion_runs_until",
		"occasion_banner_text",
		"occasion_banner_cta_label",
		"occasion_banner_cta_url",
	):
		settings.set(field, None if field == "occasion_runs_until" else "")
```

- [ ] **Step 7: Migrate, then run the tests**

```bash
flatpak-spawn --host bash -lc 'rsync -a --delete --exclude .git ~/vscodeProjects/upande_webstore/upande_webstore/ ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/ && cd ~/frappe-v16-bench && bench --site webstore.localhost migrate && bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_occasion'
```

- [ ] **Step 8: Commit**

```bash
git add upande_webstore/theme/ upande_webstore/services/settings.py upande_webstore/upande_webstore/doctype/webstore_settings/ upande_webstore/tests/
git commit -m "feat(theme): resolve the active occasion per request, never persisting it"
```

---

### Task 6: The banner — template, styles, dismissal

**Files:**
- Modify: `upande_webstore/templates/webstore_base.html:26`
- Modify: `upande_webstore/public/scss/webstore.bundle.scss:175`
- Modify: `upande_webstore/public/js/webstore.bundle.ts:344`

**Interfaces:**
- Consumes: `context.webstore_occasion` (Task 5)

- [ ] **Step 1: Add the banner block above the navbar**

In `webstore_base.html`, immediately before `{% block navbar %}`:

```html
{% block occasion_bar %}
{%- if webstore_occasion and webstore_occasion.banner %}
<div class="ws-occasion-bar" data-ws-occasion="{{ webstore_occasion.name }}">
	<div class="container">
		<p>{{ webstore_occasion.banner.text }}</p>
		{%- if webstore_occasion.banner.cta_url %}
		<a href="{{ webstore_occasion.banner.cta_url }}">{{ webstore_occasion.banner.cta_label }}</a>
		{%- endif %}
		<button type="button" data-ws-occasion-close aria-label="{{ _('Dismiss') }}">✕</button>
	</div>
</div>
{%- endif %}
{% endblock %}
```

The portal inherits this for free — `webstore_portal_base.html` extends this template, and signed-in trade buyers are the audience that most needs a cutoff date.

- [ ] **Step 2: Add the styles**

In `webstore.bundle.scss`, immediately before `.ws-navbar`:

```scss
/* Occasion banner. Sits above the sticky navbar in normal flow, so it scrolls
   away and the navbar then pins to the top on its own — no offset needed.
   Coloured from the accent tokens, so it follows whichever occasion is live. */
.ws-occasion-bar {
	background: var(--ws-accent-soft);
	color: var(--ws-accent-deep);
	border-bottom: 1px solid var(--ws-hairline);
	font-size: 0.85rem;
}
.ws-occasion-bar .container {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding-top: 0.55rem;
	padding-bottom: 0.55rem;
}
.ws-occasion-bar p { margin: 0; }
.ws-occasion-bar a {
	color: inherit !important;
	font-weight: 600;
	text-decoration: underline;
	white-space: nowrap;
}
.ws-occasion-bar button {
	margin-left: auto;
	background: none;
	border: 0;
	color: inherit;
	opacity: 0.6;
	cursor: pointer;
	line-height: 1;
	padding: 0.25rem;
}
.ws-occasion-bar button:hover { opacity: 1; }
```

And inside the existing `@media` block near line 322, beside the navbar rule:

```scss
	.ws-occasion-bar .container { flex-wrap: wrap; gap: 0.4rem; }
```

- [ ] **Step 3: Add dismissal**

In `webstore.bundle.ts`, before the `DOMContentLoaded` listener:

```typescript
	// Dismissal is keyed by occasion, so closing Valentine's does not
	// pre-dismiss Mother's Day nine weeks later.
	function initOccasionBar(): void {
		const bar = document.querySelector<HTMLElement>(".ws-occasion-bar");
		if (!bar) return;
		const key = `ws-occasion-dismissed:${bar.dataset.wsOccasion || ""}`;
		try {
			if (localStorage.getItem(key)) {
				bar.remove();
				return;
			}
		} catch {
			// private browsing or storage disabled — show the banner rather than hide it
		}
		bar.querySelector("[data-ws-occasion-close]")?.addEventListener("click", () => {
			bar.remove();
			try {
				localStorage.setItem(key, "1");
			} catch {
				/* nothing to do; it reappears next load */
			}
		});
	}
```

And call it from the init block:

```typescript
	document.addEventListener("DOMContentLoaded", () => {
		refreshCartBadge();
		initReveals();
		initOccasionBar();
	});
```

- [ ] **Step 4: Build and check it renders**

```bash
flatpak-spawn --host bash -lc 'rsync -a --delete --exclude .git ~/vscodeProjects/upande_webstore/upande_webstore/ ~/frappe-v16-bench/apps/upande_webstore/upande_webstore/ && cd ~/frappe-v16-bench && bench build --app upande_webstore && bench --site webstore.localhost clear-website-cache'
```

Set the occasion to `valentines`, then screenshot `http://webstore.localhost:8003/store` per the visual-QA note in memory and confirm: banner present above the navbar, buttons red, hero reading "Red Naomi, graded and".

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/templates/ upande_webstore/public/
git commit -m "feat(storefront): occasion banner above the navbar, dismissible per occasion"
```

---

### Task 7: Desk picker and override clearing

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js:1-6`

**Interfaces:**
- Consumes: `occasion.list_occasions()` (Task 5)

- [ ] **Step 1: Fill the autocomplete and clear overrides on change**

In `webstore_settings.js`, inside `refresh(frm)` beside the existing `list_presets` call:

```javascript
		frappe.call("upande_webstore.theme.occasion.list_occasions").then((r) => {
			frm.set_df_property("occasion", "options", r.message || []);
		});
```

And add a second handler beside `refresh`:

```javascript
	occasion(frm) {
		// Clear the previous campaign's wording and cutoff date — otherwise last
		// year's "book by 20 January" rides along into the next occasion.
		if (frm.doc.occasion === frm.__ws_last_occasion) return;
		frm.__ws_last_occasion = frm.doc.occasion;
		["occasion_banner_text", "occasion_banner_cta_label", "occasion_banner_cta_url",
			"occasion_runs_until"].forEach((field) => frm.set_value(field, ""));
	},
```

- [ ] **Step 2: Verify in the desk**

Reload Webstore Settings, confirm the Occasion picker lists all six by label ("Valentine's Day", not `valentines`), pick one, type a banner override, switch occasions, and confirm the override cleared.

- [ ] **Step 3: Run the full suite**

```bash
flatpak-spawn --host bash -lc 'cd ~/frappe-v16-bench && bench --site webstore.localhost run-tests --app upande_webstore'
```

- [ ] **Step 4: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js
git commit -m "feat(desk): occasion picker by label, clearing overrides on switch"
```

---

## Self-Review

**Spec coverage:** file format → Task 1; six occasions → Task 2; seed-layer merge and atomic groups → Task 3; hero overlay → Task 4; `active()`, lifetime, desk fields, transfer isolation, error handling → Task 5; banner and portal reach → Task 6; desk surface → Task 7. Every testing bullet in the spec maps to a named test.

**Type consistency:** `occasion.load` returns a plain `dict`; `occasion.active` returns `frappe._dict` so templates can use dotted access (`webstore_occasion.banner`). `get_tokens(settings, occasion=None)` and `get_branding(settings=None, occasion=None)` both keep the occasion as the trailing optional argument.

**Known gap accepted:** `test_unknown_name_does_not_raise` writes via `db_set` to bypass the new `validate`, since `validate` is precisely what prevents that state through the desk. The test exists because the state is still reachable — an occasion removed from a later app version while a site still names it.
