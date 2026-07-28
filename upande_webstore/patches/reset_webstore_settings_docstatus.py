"""Repair a Webstore Settings record left with docstatus 2 (Cancelled).

The logic lives in setup/install.py because it also has to run from
after_migrate — a one-time patch was not enough, since something in the migrate
path keeps re-setting the value.
"""

from upande_webstore.setup.install import normalise_settings_docstatus


def execute():
	normalise_settings_docstatus()
