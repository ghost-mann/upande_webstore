app_name = "upande_webstore"
app_title = "Upande Webstore"
app_publisher = "Upande"
app_description = "E-commerce webstore and customer portal for ERPNext v16"
app_email = "james@upande.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "upande_webstore",
# 		"logo": "/assets/upande_webstore/logo.png",
# 		"title": "Upande Webstore",
# 		"route": "/upande_webstore",
# 		"has_permission": "upande_webstore.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/upande_webstore/css/upande_webstore.css"
# app_include_js = "/assets/upande_webstore/js/upande_webstore.js"

# include js, css files in header of web template
# web_include_css = "/assets/upande_webstore/css/upande_webstore.css"
web_include_css = ["/assets/upande_webstore/css/tailwind.css", "webstore.bundle.css"]
web_include_js = "webstore.bundle.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "upande_webstore/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "upande_webstore/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "upande_webstore.utils.jinja_methods",
# 	"filters": "upande_webstore.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "upande_webstore.install.before_install"
# after_install = "upande_webstore.install.after_install"
after_install = "upande_webstore.setup.install.after_install"
after_migrate = "upande_webstore.setup.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "upande_webstore.uninstall.before_uninstall"
# after_uninstall = "upande_webstore.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "upande_webstore.utils.before_app_install"
# after_app_install = "upande_webstore.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "upande_webstore.utils.before_app_uninstall"
# after_app_uninstall = "upande_webstore.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "upande_webstore.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "upande_webstore.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"upande_webstore.tasks.all"
# 	],
# 	"daily": [
# 		"upande_webstore.tasks.daily"
# 	],
# 	"hourly": [
# 		"upande_webstore.tasks.hourly"
# 	],
# 	"weekly": [
# 		"upande_webstore.tasks.weekly"
# 	],
# 	"monthly": [
# 		"upande_webstore.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "upande_webstore.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "upande_webstore.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "upande_webstore.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "upande_webstore.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["upande_webstore.utils.before_request"]
# after_request = ["upande_webstore.utils.after_request"]

# Job Events
# ----------
# before_job = ["upande_webstore.utils.before_job"]
# after_job = ["upande_webstore.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"upande_webstore.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


standard_portal_menu_items = [
	{"title": "Store", "route": "/store", "role": "Customer"},
	{"title": "Cart", "route": "/cart", "role": "Customer"},
	{"title": "Wishlist", "route": "/wishlist", "role": "Customer"},
	{"title": "My Dashboard", "route": "/portal", "role": "Customer"},
	{"title": "Quotations", "route": "/portal/quotations", "role": "Customer"},
	{"title": "Orders", "route": "/portal/orders", "role": "Customer"},
	{"title": "Invoices", "route": "/portal/invoices", "role": "Customer"},
	{"title": "Statement", "route": "/portal/statement", "role": "Customer"},
	{"title": "Support", "route": "/portal/support", "role": "Customer"},
	{"title": "Account", "route": "/portal/account", "role": "Customer"},
]
