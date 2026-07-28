"""Webstore theme: seed-driven tokens, brand copy and feature flags.

One entry point, so every website page gets the same payload from a single
cached settings read.
"""

import frappe


def get_theme(settings=None):
	from upande_webstore.theme import branding, features, fonts, tokens

	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	return frappe._dict(
		tokens=tokens.get_tokens(settings),
		custom_css=tokens.get_custom_css(settings),
		font_link=fonts.resolve(settings)["link"],
		branding=branding.get_branding(settings),
		features=features.enabled(),
	)
