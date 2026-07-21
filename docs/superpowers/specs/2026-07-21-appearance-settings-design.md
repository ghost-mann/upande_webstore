# Appearance Settings — Design

**Date:** 2026-07-21
**Status:** Approved

## Goal

Let a store manager change the storefront's images and brand color from the desk
(`/app/webstore-settings`) without a code change or redeploy. Today the hero photo,
category card images, navbar logo, and all brand colors are hardcoded in templates
and `webstore.bundle.scss`.

## Scope

In scope (per user decision — "Images + brand colors"):

- Navbar logo, hero image, and the three category card images configurable via
  Attach Image fields.
- One brand color (`primary`) configurable via a Color field; hover, soft-tint,
  and focus-ring variants derived automatically.

Out of scope:

- Editable hero copy or dynamic category cards (names/links/subtitles stay in code).
- Any other palette tokens (background, foreground, semantic colors).

## Design

### 1. DocType: new "Appearance" tab in `Webstore Settings`

All fields optional; blank means "use the shipped default".

| Field | Type |
|---|---|
| `brand_logo` | Attach Image |
| `hero_image` | Attach Image |
| `flowers_category_image` | Attach Image |
| `coffee_category_image` | Attach Image |
| `produce_category_image` | Attach Image |
| `primary_color` | Color |

### 2. Service: `services/settings.py`

- `get_appearance() -> dict` — reads the cached single doc and returns:
  - the six field values (falsy → `None`),
  - when `primary_color` is set, derived tokens:
    - `primary_hover` — primary darkened ~12%,
    - `primary_soft` — near-white tint of primary,
    - `ring` — primary at 35% alpha (`rgba(...)`).
- Hex manipulation lives in a small private helper in the same module
  (parse `#rrggbb`, mix toward black/white, format back). Invalid or shorthand
  hex values are ignored (treated as unset) rather than raising.
- Uses `frappe.get_cached_doc`, matching `get_settings()`; the cache invalidates
  on save so changes apply on the next request.

### 3. Context wiring: `hooks.py`

- `update_website_context` hook adds `webstore_appearance = get_appearance()`
  to every website page's context. Cheap (cached doc), and makes the value
  available to `webstore_base.html` regardless of which page is rendering.

### 4. Templates

- `templates/webstore_base.html`:
  - navbar logo `src` becomes `webstore_appearance.brand_logo or
    '/assets/upande_webstore/images/upande-logo.png'`;
  - when `webstore_appearance.primary_color` is set, emit before `</head>`
    (via the existing head block):
    ```html
    <style>
      :root {
        --ws-primary: …; --ws-primary-hover: …;
        --ws-primary-soft: …; --ws-ring: …;
      }
    </style>
    ```
    Nothing is emitted when unset, so the SCSS defaults stand.
- `www/store.html`: hero `<img>` and the three category card `<img>` tags use
  the corresponding appearance value with the current asset path as fallback.

### 5. Error handling

- Missing/blank fields → shipped defaults (no conditional gaps in the page).
- Malformed color value → ignored, defaults used.
- Deleted File attachments simply 404 the image; no server error. Acceptable.

### 6. Tests (`tests/test_settings.py`)

- Derivation: a known hex produces expected hover/soft/ring values.
- Fallbacks: empty appearance fields → `get_appearance()` returns `None`s and
  no derived colors.
- Invalid hex → treated as unset.

## Result

On the live site, Webstore Settings → Appearance: upload images, pick a color,
save. The storefront and portal (both extend `webstore_base.html`) restyle on
the next page load. Colors change everywhere because all components consume the
`--ws-*` CSS variables.
