# Occasion Theme Overlays

Seasonal reskins for flower-farm trading peaks — Valentine's, Mother's Day and
four others — applied as a **temporary overlay** on top of whatever base theme a
site already has, from files shipped once in the app and reused across every
farm.

## Problem

A flower farm's year is shaped by a handful of trading peaks. The storefront
should be able to say so: red for Valentine's, a cutoff date a trade buyer can
act on, hero copy about February allocation rather than the evergreen pitch.

The app already ships a preset system (`theme/transfer.py`), but presets cannot
carry occasions. `import_theme` is wholesale by design — any field absent from
the payload is reset to its DocType default, so switching presets leaves no
residue. That makes two bad options and no good one:

- A **thin** Valentine's preset (just reds) wipes the farm's logo, hero copy,
  footer links and feature flags.
- A **fat** one (farm identity + Valentine's reds) needs N farms × M occasions
  files, and each drifts out of sync the moment a farm edits its footer.

Occasions are a *layer*, not a theme.

## Constraints

- **One app, many farms.** Occasion files are farm-agnostic and ship in the
  repo. Adding an occasion is dropping a file in a folder — no code, no
  per-site records, no fixtures.
- **Temporary.** Activating an occasion never writes to Webstore Settings.
  Deactivating is clearing a field, so there is no snapshot/restore step that
  can lose an edit made during the campaign.
- **No baked calendar.** Mother's Day is the 2nd Sunday of May in the US and
  Kenya but the 4th Sunday of Lent in the UK, and Easter moves every year.
  Shipped files carry **no dates**; the farm supplies its own end date.
- **A bad occasion file must never take a storefront down.**

## Decisions

| Decision | Choice |
|---|---|
| Composition | Render-time overlay over base settings; nothing written |
| Distribution | JSON files in `theme/occasions/`, shipped in the app |
| Scope | Colour seeds, a banner, and hero copy. No imagery. |
| Activation | Manual pick + farm-entered "Runs until" date |
| Farm customisation | Four override fields (banner text, CTA label, CTA URL, end date) |
| Portal reach | Colours and banner yes, hero no (the portal has no hero) |
| First cut | Valentine's, Women's Day, Mother's Day, Easter, All Saints, Christmas |

### Why no imagery

An occasion could ship a hero image, but a generic stock rose would look worse
than the farm's own crop, and shipped assets are exactly what would stop
occasion files being farm-agnostic. The hero image always stays the farm's.

### Rejected alternatives

- **Occasion as a DocType.** Farms could author their own in the desk, but it
  means fixtures and migrations, occasions stop being swappable files, and it
  reintroduces per-site records across every farm.
- **Apply-and-snapshot.** Write occasion values into settings after snapshotting
  the base, restore on revert. Keeps the render path untouched, but any edit
  made during the campaign is silently destroyed on revert.

## Architecture

```
theme/occasions/*.json        6 shipped files, farm-agnostic
theme/occasion.py             load, validate, resolve
theme/tokens.py               accepts occasion=, merges seeds before derivation
theme/branding.py             accepts occasion=, merges hero copy
theme/__init__.py             resolves the occasion once per request
services/settings.py          exposes context.webstore_occasion
templates/webstore_base.html  banner slot above {% block navbar %}
public/scss/webstore.bundle.scss   .ws-occasion-bar
public/js/webstore.bundle.ts       dismissal, keyed by occasion name
Webstore Settings             5 new fields on the Theme tab
```

No new DocType, no fixtures, no migrations.

### Seed-layer merge

This is the load-bearing detail. Every `--ws-*` token is *derived from seeds*:
`color.accent_scale()` builds hover, light, deep and ring off the accent seed,
and `on-accent` is WCAG-contrast-picked against both ends of the CTA gradient
(`theme/color.py:131`, `theme/tokens.py:95`).

An occasion that set `--ws-accent` directly would leave `accent-hover`,
`accent-deep` and `ring` on the farm's colour and compute `on-accent` against
the wrong background. So the overlay merges **seeds**, before derivation:

```
settings seeds → [occasion seeds] → get_tokens() → derivation → --ws-*
```

A Valentine's file therefore carries one hex and gets a correct,
contrast-checked ramp for free.

### Atomic seed groups

```python
SEED_GROUPS = {
    "accent":  ("accent", "accent_dark", "accent_soft"),
    "surface": ("canvas", "wash"),
}
```

An occasion that sets *any* member of a group owns the *whole* group; members it
omits are blanked so they re-derive. Without this, a farm's explicit
`accent_soft` survives under an occasion's accent — Mona sets
`accent_soft: #e8f0fb` (`theme/presets/mona_flowers.json:6`), which under a red
accent is a visible blue clash.

### Whitelist

Only the keys in `SEED_GROUPS` are honoured; anything else in a `seeds` block is
dropped on load. Deliberately excluded:

- **`ink` and the border seeds** — an occasion shifting text colour risks
  contrast failures against a canvas it cannot see.
- **Fonts and radii** — brand identity, not season.
- **Status colours** (`success`, `warning`, `danger`, `info`) — these carry
  meaning. A reddened `success` makes confirmations read as errors.
- **`custom_css`** — an occasion file shipping arbitrary CSS to every farm on
  the app is an unbounded blast radius. This one stays excluded permanently.

## File format

`theme/occasions/valentines.json`:

```json
{
  "schema": 1,
  "label": "Valentine's Day",
  "seeds": { "accent": "#b3122d", "accent_dark": "#7d0c1f", "accent_soft": "#fdeef0" },
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

`OCCASION_SCHEMA_VERSION = 1`, separate from `transfer.SCHEMA_VERSION` —
occasion files and theme exports version independently.

`label` exists so the desk picker reads "Valentine's Day" rather than
`valentines`. The `occasion` field is an **Autocomplete** fed
`{value, label, description}`, unlike the existing `preset` Select which shows
raw filenames — tolerable for a once-per-site action, not for something farm
staff touch six times a year.

`banner` and `hero` are both optional. `hero` keys map onto branding fields by
prefix: `eyebrow` → `hero_eyebrow`, `heading_em` → `hero_heading_em`,
`cta_primary` → `hero_cta_primary`, and so on. Only the keys present are
overridden.

## Resolution order

**Colours** — occasion over settings, at the seed layer, per atomic group.

**Hero copy** — occasion wins, because that is what an overlay is for:

```
branding.DEFAULTS → farm's settings → occasion.hero
```

**Banner** — farm wins, because the cutoff date is farm-specific:

```
occasion.banner → farm's override fields (blank = keep the occasion's default)
```

`get_theme()` resolves the occasion **once** per request and passes it into both
`tokens.get_tokens(settings, occasion=None)` and
`branding.get_branding(settings, occasion=None)`. Both parameters default to
`None`, so every existing caller and test keeps working unchanged.

Occasion files are read per request, not cached: six files at ~1KB is roughly
50µs against a millisecond-scale render. Caching buys nothing here and adds an
invalidation surface. Revisit only if profiling disagrees.

## Activation and lifetime

`occasion.active(settings)` returns the resolved occasion or `None`. It returns
`None` when:

- `occasion` is blank
- the named file does not exist, or does not parse
- `occasion_runs_until` is set and is earlier than today (site timezone, via
  `frappe.utils.getdate` / `nowdate`)

Activating writes nothing. Deactivating is clearing the `occasion` field.

Changing `occasion` in the desk clears the four override fields client-side,
immediately and visibly — that is what stops last year's cutoff date leaking
into next year's campaign.

**Occasion fields stay out of `transfer.all_fields()`.** Campaign state is not
theme state: importing a base theme mid-February must not kill a running
Valentine's campaign, and exporting a theme to another farm must not carry one
farm's cutoff date along with it. Because `import_theme` only resets fields it
knows about, excluding them from the list gives exactly this behaviour.

## The banner

A block in `webstore_base.html` immediately above `{% block navbar %}`. Because
`webstore_portal_base.html:1` extends the base, the banner and the recoloured
tokens reach the portal for free — which is where signed-in trade buyers
actually book, and so the audience that most needs a cutoff date.

`.ws-navbar` is `position: sticky; top: 0; z-index: 1030`
(`public/scss/webstore.bundle.scss:175`). A banner in normal flow above it
scrolls away, and the navbar then sticks to the top on its own — no z-index or
offset work needed.

```html
{% if webstore_occasion and webstore_occasion.banner %}
<div class="ws-occasion-bar" data-ws-occasion="{{ webstore_occasion.name }}">
  <div class="container">
    <span>{{ webstore_occasion.banner.text }}</span>
    {% if webstore_occasion.banner.cta_url %}
    <a href="{{ webstore_occasion.banner.cta_url }}">{{ webstore_occasion.banner.cta_label }}</a>
    {% endif %}
    <button type="button" data-ws-occasion-close aria-label="{{ _('Dismiss') }}">✕</button>
  </div>
</div>
{% endif %}
```

Styled from `--ws-accent-soft` with `--ws-accent-deep` text, so it inherits the
occasion's palette without hardcoding a colour.

Dismissal is `localStorage`, **keyed by occasion name** — dismissing Valentine's
does not pre-dismiss Mother's Day.

## Desk surface

A new "Occasion" section on the **Theme** tab:

| Field | Type | Purpose |
|---|---|---|
| `occasion` | Autocomplete | Which occasion is live; blank = none |
| `occasion_runs_until` | Date | Overlay stops resolving after this date |
| `occasion_banner_text` | Data | Overrides the file's banner text |
| `occasion_banner_cta_label` | Data | Overrides the file's CTA label |
| `occasion_banner_cta_url` | Data | Overrides the file's CTA URL |

`webstore_settings.js` fills the autocomplete from a whitelisted
`occasion.list_occasions()`, mirroring how `refresh()` already fills `preset`
from `transfer.list_presets()`.

Server-side `validate` throws if `occasion` names a file that does not exist — a
typo should fail at save, not silently render nothing.

## Error handling

The governing rule: **a bad occasion file must never take the storefront down.**

| Failure | Behaviour |
|---|---|
| File missing | `active()` → `None`, logged once via `frappe.log_error`; base theme renders |
| Malformed JSON | Same |
| Wrong `schema` version | Same |
| Unknown key in `seeds` | Dropped by the whitelist |
| Invalid hex | Falls through `color.parse` to `None` and re-derives — existing behaviour |
| Path traversal in name | Rejected by `^[a-z0-9_]+$`, as `apply_preset` already does |

The filename guard is defence in depth — the value comes from settings rather
than a request — but it costs one line.

## Shipped occasions

| File | Label | Accent direction |
|---|---|---|
| `valentines` | Valentine's Day | deep red, blush tint |
| `womens_day` | Women's Day | warm gold |
| `mothers_day` | Mother's Day | soft pink, cream |
| `easter` | Easter | fresh green |
| `all_saints` | All Saints / Toussaint | muted plum, stone |
| `christmas` | Christmas | deep red, warm cream canvas |

Every palette must clear the contrast gate below before it ships.

## Testing

New `tests/test_occasion.py`, alongside the existing `test_theme`,
`test_transfer`, `test_branding` and `test_features` suites.

**Shipped-file integrity**
- Every file parses, matches `OCCASION_SCHEMA_VERSION`, and carries a `label`
- Only whitelisted seed keys survive load
- Every hex is a valid 7-character value
- No shipped occasion touches a status colour

**Contrast gate**
- For each of the six, the resolved `on-accent` clears WCAG AA (4.5:1) against
  both `accent` and `accent-deep`. `color.best_contrast` already does the work
  (`tests/test_theme.py:122`); this catches a bad palette in CI rather than on a
  farm's live site.

**Resolution**
- Group atomicity: a farm with blue `accent_soft` plus an occasion setting
  `accent` resolves to a non-blue `accent-soft`
- Occasion hero copy beats farm branding; a file with no `hero` block leaves
  farm copy intact
- Farm banner overrides beat the file; blank overrides fall back to it
- `get_tokens` and `get_branding` are unchanged when `occasion=None`

**Lifetime**
- `active()` returns `None` for blank, unknown name, malformed file, and a
  `runs_until` in the past
- `active()` returns the occasion when `runs_until` is today or in the future

**Isolation**
- Occasion fields are absent from `transfer.all_fields()`, so `import_theme`
  neither exports nor resets them
