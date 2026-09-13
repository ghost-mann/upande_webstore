"""Which of `Webstore Settings`' fields a `Webstore` row may override.

One list, read by three things that would otherwise drift apart: the merge in
`services.settings`, the `Webstore` doctype's own field set (generated from
these names — see `scripts/generate_webstore_fields.py`), and the test that
asserts the two doctypes still agree.

The split is decided by one question, from the spec: *would a customer notice
this differing between the two shops?* Theme yes, company no. So everything a
visitor sees — colours, type, copy, hero, footer, categories, prices, the
storefront features themselves — is per store, and the ledger-facing defaults,
the desk role grants and the shared customer portal are not.

`Webstore Settings` keeps every one of these fields and stays the site-wide
default. A store overrides what it fills in and inherits the rest, which is
why a site with one storefront needs no data migration at all: its store row
is blank and it renders exactly as it always did.
"""

# Colour, type and shape seeds, plus the free-form CSS escape hatch. Mirrors
# theme.tokens.THEME_FIELDS, minus accent_drives_primary — that one is a
# checkbox and so lives in PER_STORE_TRISTATE below.
THEME_SEEDS = (
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
	"font_sans",
	"font_sans_name",
	"font_display",
	"font_display_name",
	"font_mono",
	"font_mono_name",
	"google_fonts_url",
	"radius",
	"radius_card",
	"radius_panel",
	"custom_css",
	"primary_color",
)

# A seasonal campaign is per shop: a Valentine's overlay on the flower store
# has nothing to say on the dairy one.
OCCASION_FIELDS = (
	"occasion",
	"occasion_runs_until",
	"occasion_banner_text",
	"occasion_banner_cta_label",
	"occasion_banner_cta_url",
)

# Name, wordmark and marks. The most visible thing that must differ — two
# shops sharing a logo are not two shops.
IDENTITY_FIELDS = (
	"site_name",
	"wordmark",
	"wordmark_bold",
	"wordmark_subtitle",
	"brand_logo",
	"favicon",
)

HERO_FIELDS = (
	"hero_image",
	"hero_eyebrow",
	"hero_heading",
	"hero_heading_em",
	"hero_body",
	"hero_cta_primary",
	"hero_cta_secondary_guest",
	"hero_cta_secondary_member",
)

COPY_FIELDS = (
	"process_eyebrow",
	"process_heading",
	"process_heading_em",
	"footer_tagline",
	"footer_contact_email",
	"footer_hours",
	"footer_location",
	"footer_website",
	"footer_copyright",
	"footer_note",
	"portal_eyebrow",
	# superseded by the category_cards table, but still read where a farm set
	# them, so they follow their shop rather than stranding it on the Single
	"flowers_category_image",
	"coffee_category_image",
	"produce_category_image",
)

# What the storefront sells and for how much. guest_price_list is the single
# fallback; guest_price_lists is the multi-currency table beside it.
COMMERCE_FIELDS = (
	"guest_price_list",
	"stock_display",
	"default_box_type",
	"minimum_order_stems",
	"default_lead_days",
	"checkout_mode",
)

#: Plain fields a store may override. Blank (or 0, for the numeric ones)
#: inherits `Webstore Settings`.
PER_STORE_SCALARS = (
	THEME_SEEDS + OCCASION_FIELDS + IDENTITY_FIELDS + HERO_FIELDS + COPY_FIELDS + COMMERCE_FIELDS
)

#: Child tables a store may override. Replaced wholesale when the store has
#: any rows — a half-merged warehouse list or a category list spliced from two
#: shops would be incoherent.
COMMERCE_TABLES = ("categories", "guest_price_lists", "warehouses")
BRANDING_TABLES = ("category_cards", "hero_stats", "process_steps", "footer_links")

PER_STORE_TABLES = COMMERCE_TABLES + BRANDING_TABLES

#: Checkbox-valued overrides need three states, not two: a dairy store must be
#: able to turn the wishlist off while the flower store on the same site
#: leaves it on, and a Check field cannot express "off" and "inherit" at once.
#: Each of these is a Select on `Webstore` whose blank option means inherit.
#:
#: The ten portal flags are deliberately absent. The portal is shared — one
#: account, one order history across both shops — so switching Invoices off
#: for one storefront and not the other would describe a customer experience
#: that does not exist.
TRISTATE_OPTIONS = {"Enabled": 1, "Disabled": 0}

PER_STORE_TRISTATE = (
	"accent_drives_primary",
	"enable_box_packing",
	"enable_cart",
	"enable_direct_order",
	"enable_wishlist",
	"enable_signup",
	"enable_search_palette",
	"enable_cart_drawer",
	"enable_hero",
	"enable_hero_stats",
	"enable_category_cards",
	"enable_footer",
)

#: Everything a store may override, in one tuple, for callers that do not care
#: which mechanism carries it.
ALL_PER_STORE_FIELDS = PER_STORE_SCALARS + PER_STORE_TABLES + PER_STORE_TRISTATE
