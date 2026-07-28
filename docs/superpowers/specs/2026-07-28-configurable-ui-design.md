# Configurable UI — Design

**Date:** 2026-07-28
**Status:** Approved

## Goal

The webstore and customer portal will serve several client projects. Maintain
**one branch**: every visual and structural choice that differs between clients
moves out of code and into `Webstore Settings`, so a new project is a
configuration exercise, not a fork.

Today the ink neutrals, fonts, radii, gradients, hero copy, the three hardcoded
category cards, the four footer columns, contact details and the full navigation
are baked into `webstore.bundle.scss` and five templates. Only five images and
one accent color are configurable (see `2026-07-21-appearance-settings-design.md`,
which this supersedes).

## Scope

In scope:

- **Full color system** — accent, ink/neutral scale, surfaces, borders and the
  four semantic status colors, all derived from optional seed fields.
- **Typography and shape** — sans/display/mono families from the shipped set or
  Google Fonts; three radius values.
- **All brand copy and identity** — wordmark, favicon, hero copy, hero stats,
  category cards, footer columns, contact lines, copyright.
- **Feature checkboxes** — 19 flags that hide UI, 404 the route, and reject the
  API.
- **Export/import** — theme JSON round-trip, plus shipped presets.

Out of scope:

- **Dark theme.** The system stays light-only. A project wanting dark can set a
  dark canvas seed and a light ink seed and the derivation follows, but there is
  no mode select, no `prefers-color-scheme` handling, and no second seed set.
- Per-user or per-role theming. One theme per site.
- Editable page *structure* beyond the three child tables — no page builder, no
  reorderable sections.

## Non-negotiable constraint

**A site with every new field blank must render byte-identically to today.**
Every field is optional and falls back to the value currently shipped in the
SCSS. This is what makes the change safe to migrate onto the live Upande site,
and it is asserted by test rather than assumed: with a blank settings doc
`get_tokens()` returns `{}`, so `webstore_base.html` emits no override block at
all.

## Architecture

### Delivery mechanism

Tokens are emitted as an inline `<style>` block in `<head>`, derived per request
from the cached settings doc. This widens the mechanism already in
`webstore_base.html`. ~2KB inline, gzips to little, applies the instant Save is
pressed, no files written, no build step, multi-site safe.

Rejected: compiling a CSS file on save (file writes, cache-busting, a stale-file
failure mode, for a payload smaller than one product photo); Frappe's
`Website Theme` doctype (recompiles SCSS on save, needs build tooling in
production, couples to Frappe internals, and covers none of the copy or
feature-toggle half of this work).

### Code organisation

`services/settings.py` is 67 lines today. This work adds color derivation, font
handling, branding resolution, feature guards and JSON transfer — enough to grow
one module past 600 lines. Instead, a new package with one purpose per file:

```
upande_webstore/theme/
  __init__.py     # get_theme() -> the single context payload
  color.py        # pure hex math + scale derivation; no frappe import
  tokens.py       # seeds + fonts + shape -> {--ws-*: value}
  fonts.py        # shipped families, Google Fonts link
  branding.py     # DEFAULTS + get_branding()
  features.py     # FEATURES registry, enabled(), require(), guard()
  transfer.py     # export_theme(), import_theme(), apply_preset()
  presets/
    mona_flowers.json
    upande.json
```

`services/settings.py` keeps `get_settings()` / `get_warehouses()`. Its
`update_website_context` delegates to `theme.get_theme()` and injects three
context keys: `webstore_tokens`, `webstore_branding`, `webstore_features`.
`webstore_appearance` is retained as an alias for one release so nothing breaks
mid-migration.

`color.py` imports nothing from Frappe, so its derivation is testable as plain
functions.

## Settings form layout

`Webstore Settings` becomes tabbed. Existing General fields are untouched.

| Tab | Sections |
|---|---|
| **General** | *(unchanged)* company, guest price list, signup defaults, quotation validity, stock display, notification emails, warehouses |
| **Theme** | Brand Colors · Status Colors · Typography · Shape · Advanced |
| **Branding** | Identity · Hero · Hero Stats *(table)* · Category Cards *(table)* · Footer *(+ Footer Links table)* |
| **Features** | Storefront · Portal |
| **Transfer** | Export / Import / Apply Preset |

Three new child doctypes:

| DocType | Fields |
|---|---|
| `Webstore Hero Stat` | `value` (Data), `label` (Data) |
| `Webstore Category Card` | `label` (Data), `subtitle` (Data), `image` (Attach Image), `category` (Data), `url` (Data) |
| `Webstore Footer Link` | `column` (Data — the column heading), `label` (Data), `url` (Data) |

`Webstore Footer Link` carries its column heading on each row, so one table
drives all footer columns: rows are grouped by `column` in table order, and the
number of columns follows the data. An empty table hides the footer link area
entirely.

## Theme engine

### Color seeds

Thirteen optional Color fields. Each blank seed contributes nothing and its SCSS
default stands.

| Field | Drives | Fallback when blank |
|---|---|---|
| `accent` | `--ws-accent` | shipped gold |
| `accent_dark` | `--ws-accent-deep` | `mix(accent, black, 0.25)` |
| `accent_soft` | `--ws-accent-soft` | `mix(accent, white, 0.92)` |
| `ink` | `--ws-ink` + scale | shipped `#0a0a0a` |
| `ink_muted` | `--ws-ink-mute`, anchors the scale | derived from ink→canvas |
| `canvas` | `--ws-bg` | shipped `#f4f3ef` |
| `wash` | `--ws-wash` | `rgba(ink, 0.04)` |
| `border` | `--ws-hairline` | `rgba(ink, 0.06)` |
| `border_strong` | `--ws-hairline-strong` | `rgba(ink, 0.12)` |
| `success` `warning` `danger` `info` | the four status families | shipped values |

### `color.py`

Pure functions:

- `parse(hex) -> (r,g,b) | None` — strict `#rrggbb`; shorthand and invalid
  values return `None` and are treated as unset rather than raising. (Promoted
  from the existing `_parse_hex`.)
- `mix(rgb, target, amount)`, `to_hex(rgb)`, `rgba(rgb, alpha)`.
- `ink_scale(ink, muted, canvas)` — see below.
- `surface_scale(ink, canvas, wash, border, border_strong)` — surfaces,
  hairlines and the three shadow strings. Shadows use the **ink seed** at the
  alphas currently hardcoded, replacing the literal `rgba(10,10,10,…)`.
- `accent_scale(accent, dark, soft)` — the existing six tokens.
- `status_scale(seed)` — `-deep` at `mix(seed, black, 0.12)` and `-soft` at
  `rgba(seed, 0.12)`, for each of the four.

### Ink scale derivation

The seven ink steps sit at roughly these fractions along ink→canvas:

```
STEPS = (0.000, 0.068, 0.137, 0.205, 0.342)   # ink, ink-1..ink-4
MUTE  = 0.547                                  # ink-mute
FAINT = 0.744                                  # ink-faint
```

The scale is a **two-segment** interpolation rather than a single mix so that
`ink_muted` anchors the `MUTE` position: the temperature of the most-visible gray
is then set directly instead of falling out of the arithmetic. This is what lets
Mona's deliberately blue-shifted `#878c9c` survive derivation, where a plain
ink→canvas ramp would flatten it to `#949495`.

- `ink`, `ink-1..ink-4` = `mix(ink, muted, s / MUTE)` for each `s` in `STEPS`
- `ink-mute` = `muted` exactly
- `ink-faint` = `mix(muted, canvas, (FAINT - MUTE) / (1 - MUTE))`

The `t` values are written as expressions over the constants rather than
precomputed decimals, so there is one place to change and no hand-arithmetic to
get wrong.

Without a `muted` seed, `muted` defaults to `mix(ink, canvas, MUTE)`. The two
segments then algebraically collapse back to the single ink→canvas ramp:
`mix(ink, mix(ink, canvas, MUTE), s/MUTE) == mix(ink, canvas, s)`.

**The shipped ink values are hand-picked and do not sit on a clean ramp.**
`--ws-ink-1` is `#1a1a18`, whose blue channel (24) implies a fraction of 0.061
where its red and green channels imply 0.068 — the shipped scale was nudged
warmer by eye. So feeding today's `#0a0a0a` / `#f4f3ef` back through the
derivation **approximates** the shipped values within about one 8-bit step; it
does not reproduce them bit-for-bit. That is fine and invisible in practice,
because a site that wants today's look leaves the seeds blank and no override is
emitted at all. The test asserts the approximation within a tolerance of 2 per
channel, not equality.

**Known approximation:** with Mona's seeds the derived `--ws-ink-4` is `#5d616a`
against the CRM's `#54586b` — a few percent lighter and less saturated. Same for
`--ws-ink-faint` (`#b7bbc5`). These are close enough that the difference is not
visible in body text; if an exact match is ever wanted, the Advanced CSS field
pins them. Recorded here so it is a known trade rather than a surprise.

### Surface ladder direction

Today's ladder ascends: `bg #f4f3ef` → `surface #fafaf6` → `card #ffffff`.
`--ws-surface` is a *lift* above the canvas.

Mona's palette descends: `#f7f8fa` is the canvas and `#eef0f4` is **darker**, so
it is a sunken fill, not a lift. It maps to `--ws-wash`, not `--ws-surface`.
Getting this backwards would make every muted fill glow instead of recede.
`--ws-surface` is therefore derived as `mix(canvas, white, 0.5)` when unset, and
`--ws-card` stays white.

### Accent drives primary actions

A checkbox on the Theme tab. In the shipped design `--ws-ink` paints primary
buttons, active nav pills, avatars and the member button, while `--ws-accent` is
decorative trim. A brand whose primary color is not near-black needs the former.

When on, `tokens.py` remaps:

```
--ws-primary       -> var(--ws-accent)
--ws-primary-hover -> var(--ws-accent-hover)
--ws-primary-soft  -> var(--ws-accent-soft)
--ws-grad-ink      -> linear-gradient(135deg, accent-deep 0%, accent 100%)
```

This requires an SCSS sweep, because the rules that use `var(--ws-ink)` as an
**action surface** must switch to `var(--ws-primary)`, while the rules that use
it as **text or a heading color** must not. The sweep must distinguish the two;
mechanically replacing every occurrence would turn body text navy.

Action-surface rules to convert (verify by grep during implementation):
`.btn-primary`, `.ws-nav > a.active`, `.ws-member-btn`, `.ws-avatar`,
`.ws-side-link.on`, `.pagination .active .page-link`, `::selection`,
`:focus-visible` outline, and `--ws-grad-ink` consumers.

Mona's preset ships with this on. Upande's ships off, so gold stays trim.

### Typography

`sans`, `display`, `mono` are Selects listing the bundled families (Poppins,
Fraunces, IBM Plex Mono) plus `Custom`. Choosing `Custom` reveals a Data field
for the family name and relies on `google_fonts_url` — a Data field holding a
`fonts.googleapis.com` link, emitted as a `<link>` before the token block.

`fonts.py` validates the URL's host is `fonts.googleapis.com` and rejects
anything else, so the field cannot be used to inject an arbitrary remote origin
into every page's `<head>`.

The bundled `@font-face` rules stay in the SCSS unconditionally — they cost
nothing when unused because `font-display: swap` only fetches referenced
families.

### Shape and Advanced

`radius`, `radius_card`, `radius_panel` — Data fields taking any CSS length,
mapping to the three existing variables.

`custom_css` — a Code field appended **verbatim after** the generated token
block, so it wins on cascade order. This is the escape hatch for any token the
seed model does not reach.

## Feature checkboxes

One registry in `features.py` drives all three enforcement layers, so a flag
cannot be enforced in one place and forgotten in another.

**Storefront:** Cart & Checkout · Wishlist · Signup · Search Palette ·
Cart Drawer · Hero · Hero Stats · Category Cards · Footer

**Portal:** Portal (master) · Dashboard · Quotations · Orders · Invoices ·
Statement · Support · Claims · Account · Sidebar Stats

All default **on**, so existing behaviour is unchanged.

### Enforcement

1. **UI** — `features.enabled()` returns `{key: bool}` into context as
   `webstore_features`; templates wrap sections and nav entries in
   `{% if webstore_features.wishlist %}`. Sidebar and navbar markup stays as
   written (each item keeps its inline SVG) wrapped in conditionals, rather than
   being rewritten as a data-driven loop — the icons stay legible in the
   template and the diff stays reviewable.
2. **Route** — `features.require("portal", "quotations")` as the first line of
   the page's `get_context`. Variadic, so the master gate composes. Raises
   `frappe.DoesNotExistError`, which Frappe renders as a 404.
3. **API** — `@features.guard("wishlist")` on whitelisted methods, throwing
   `frappe.PermissionError`. Covers the case of JS on a cached page calling a
   method after the flag was turned off.

### Dependent flags

Handled in `webstore_settings.validate` and in the templates, not left to be
discovered as bugs:

- **Cart off forces Cart Drawer off.** The drawer has nothing to show.
- **Signup off changes the hero's secondary CTA.** It currently reads
  "Open a trade account" → `/signup` for guests, which with Signup off is a link
  to a 404. It falls back to "Member login" → `/login`. Mona's preset has Signup
  off (their live site sets `disable_signup: 1`), so this path is live on day
  one, not hypothetical.
- **Cart off** also hides the basket link, the cart badge and every add-to-cart
  control, leaving a browse-only catalog — a real configuration for a client who
  takes orders by phone.

Portal children are not forced off when the master is off; `require()` composing
both keys already makes them unreachable, and preserving their values means
flipping the master back on restores the previous configuration.

## Branding

`branding.py` holds a single `DEFAULTS` dict — every fallback string in one
readable place, replacing the `or '…'` literals currently scattered across five
templates — and `get_branding()` resolves setting-or-default plus the three
child tables into `webstore_branding`.

| Section | Fields |
|---|---|
| Identity | `brand_logo`, `favicon`, `wordmark`, `wordmark_bold`, `wordmark_subtitle`, `site_name` |
| Hero | `hero_image`, `hero_eyebrow`, `hero_heading`, `hero_heading_em`, `hero_body`, `hero_cta_primary`, `hero_cta_secondary_guest`, `hero_cta_secondary_member` |
| Hero Stats | child table |
| Category Cards | child table |
| Footer | `footer_tagline`, Footer Links table, `footer_contact_email`, `footer_hours`, `footer_location`, `footer_website`, `footer_copyright`, `footer_note` |
| Portal | `portal_eyebrow` |

### Migration

`Webstore Category Card` replaces `flowers_category_image`,
`coffee_category_image` and `produce_category_image`. A patch registered in
`patches.txt` (`post_model_sync`) copies any uploaded value into a card row —
with the label and subtitle the template currently hardcodes — before the old
fields are removed. An existing site keeps its images and its cards.

The patch is idempotent: it no-ops when the child table already has rows.

## Transfer

`transfer.py`:

- `export_theme()` — serialises every Theme, Branding and Features field plus
  the three child tables to JSON with a `"schema": 1` key. Exposed as a button
  that downloads the file client-side.
- `import_theme()` — validates the schema key, applies scalar fields, replaces
  child tables wholesale.
- `apply_preset(name)` — the same code path over `theme/presets/*.json`, offered
  as a Select of the shipped presets.

**Images export as file URLs, not embedded bytes.** Embedding base64 would bloat
the JSON past usefulness. The consequence is that a URL may not resolve on the
target site, so `import_theme` checks each one and **reports the unresolvable
ones** rather than silently rendering broken images.

`"schema": 1` exists so a future field rename can migrate old exports instead of
failing on them.

## Shipped presets

Real export files, same schema the Transfer tab reads.

### `mona_flowers.json`

Data pulled from their live site (Company, Website Settings, Item Group, Item,
Address). The **navy palette is supplied by the user** from prior CRM rebrand
work (`mona_crm.html`, "Version B") — those files are not in this repo or on
this bench, so the values are recorded here as authoritative-by-supply, not as
read from source.

Version B was chosen over Version A (`#1a3a6e`) because it is the brighter navy
and reads better on white surfaces, and the brightness costs nothing in
accessibility: white-on-`#1e4d8c` measures **8.42:1**, clearing WCAG AAA (7:1)
with room to spare, against **11.20:1** for A. Version B also collapses
`--navy-dark` and `--navy-text` into one value.

```
accent                #1e4d8c    accent_dark    #143562
accent_soft           #e8f0fb
ink                   #1a1a1a    ink_muted      #878c9c
canvas                #f7f8fa    wash           #eef0f4
border                #e2e6ed    border_strong  #c5cbd6
success  #2d6a4f   warning #9a6700   danger #b42318   info #175cd3
accent_drives_primary  on
```

| | |
|---|---|
| Company | Mona Flowers Kenya Limited (MFK) · Eldoret, Kenya · P.O. Box 2707-30100 |
| Currency | KES |
| Logo | `/files/Mona-Flowers-Main-Logo.png` |
| Wordmark | `mona` + **`flowers`** |
| Eyebrow | Mona Flowers · Eldoret, Kenya |
| Heading | Graded roses, *cut to order, cooled in hours* |
| Body | Export-grade roses and eucalyptus from our Eldoret farm — 45+ varieties, 40 to 120cm, quotation-first ordering with cold chain to Nairobi, the Gulf and beyond. |
| Hero stats | `45+` rose varieties · `40–120cm` stem grades · `3` continents shipped |
| Category cards | **Roses** — 45+ varieties, 40–120cm · **Eucalyptus** — Silver Dollar & Baby Blue |
| Copyright | 2026 Mona Flowers Kenya Limited |
| Footer note | Powered by Upande |
| Signup | **off** |

Their catalogue backs those numbers: ~45 rose varieties (Julietta, Summer rose,
Giselle!, Madam Red, Deep Purple, Snow Flakes, Athena, Wild Fox, Gold Finch,
Paloma and more), two eucalyptus lines, sold in `Stem(s)` graded 40–120cm in
10cm steps, shipping to Kenya, Saudi Arabia (Jeddah, Riyadh, Makkah) and
Australia (Adelaide).

### `upande.json`

Today's copy and the ink & gold palette, so the current design is a preset
rather than something only recoverable from git history.
`accent_drives_primary` off.

### Install behaviour

A **fresh** install seeds `mona_flowers.json`. `after_migrate` never touches a
site that already has a `Webstore Settings` record, so the live Upande site is
unaffected by a deploy.

## Error handling

| Condition | Behaviour |
|---|---|
| Blank field | Shipped default. No conditional gap in the page. |
| Malformed hex | Treated as unset; that token's default stands. Never raises. |
| Deleted image attachment | Image 404s; no server error. |
| Non-Google font URL | Rejected on validate, with a message. |
| Import of unknown schema version | Rejected with a message naming the version. |
| Import referencing missing images | Applied, and the unresolvable URLs reported. |
| Feature off, route hit directly | 404 via `DoesNotExistError`. |
| Feature off, API called directly | `PermissionError`. |

## Tests

`tests/test_theme.py`
- `color.py` as pure functions: ink scale with and without a muted seed, the
  descending surface ladder, opaque vs `rgba` hairlines, invalid and shorthand
  hex ignored, status derivation.
- **Regression guard:** a blank settings doc yields `get_tokens() == {}`, so no
  override block is emitted and existing sites are provably untouched.
- Mona's seeds produce the documented token values, including the
  `accent_drives_primary` remap.
- Today's ink and canvas seeds, with no muted seed, land within 2 per channel of
  the seven shipped ink values — a tolerance assertion, not equality, for the
  reason given under *Ink scale derivation*.
- The two-segment scale collapses to the single ramp when `muted` is unset:
  `ink_scale(ink, None, canvas) == ink_scale_single_ramp(ink, canvas)` exactly.

`tests/test_features.py`
- `require()` raises `DoesNotExistError` when off, passes when on, and composes
  the master gate.
- `guard()` throws `PermissionError` when off.
- Cart off forces Cart Drawer off on validate.
- Hero secondary CTA falls back to `/login` when Signup is off.

`tests/test_transfer.py`
- Export → import round-trips every field and child table identically.
- Every shipped preset loads and validates.
- Unknown schema version is rejected.
- Import reports unresolvable image URLs.

`tests/test_branding.py`
- Blank fields resolve to the shipped defaults.
- Empty child tables omit their sections rather than rendering empty shells.

`tests/test_settings.py` — extended for the category-image migration patch,
asserted against a doc with the three old fields set, and for patch idempotency.

## Result

A new client project is: open `Webstore Settings`, apply a preset or import a
JSON, adjust seeds and copy, tick the features they bought, save. The storefront
and portal restyle on the next page load, because every component already
consumes `--ws-*` variables and every string already reads from
`webstore_branding`.

One branch, one codebase, N clients.
