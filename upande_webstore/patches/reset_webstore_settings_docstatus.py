"""Repair a settings Single left with docstatus 2 (Cancelled).

The logic lives in setup/install.py because it also has to run from
after_migrate: tabSingles persists the value, so a site that already ran this
patch before the repair covered Webstore Portal Settings needs the migrate
hook to reach it. Both Singles are covered now — see
install.NON_SUBMITTABLE_SINGLES.
"""

from upande_webstore.setup.install import normalise_settings_docstatus


def execute():
	normalise_settings_docstatus()
