"""Webstore doctype: slug validation.

Slug is the only thing a store's URL prefix will be built from (Task 2), so
every rule here exists to stop a slug that would make a storefront
unreachable or shadow an existing route.
"""

import frappe
from frappe.tests import IntegrationTestCase
from upande_webstore.tests.utils import delete_all_webstores


def make_webstore(slug, title=None, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Webstore",
			"slug": slug,
			"title": title or slug,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestWebstoreSlugValidation(IntegrationTestCase):
	def setUp(self):
		# patches.create_default_webstore has already run on the site under
		# test, so clear its row rather than let it collide with these slugs.
		delete_all_webstores()

	def tearDown(self):
		delete_all_webstores()

	def test_accepts_a_plain_lowercase_slug(self):
		doc = make_webstore("flowers")
		self.assertEqual(doc.name, "flowers")

	def test_accepts_a_hyphenated_slug(self):
		doc = make_webstore("dairy-fresh")
		self.assertEqual(doc.name, "dairy-fresh")

	def test_rejects_uppercase(self):
		with self.assertRaises(frappe.ValidationError):
			make_webstore("Flowers")

	def test_rejects_spaces(self):
		with self.assertRaises(frappe.ValidationError):
			make_webstore("flower shop")

	def test_rejects_a_leading_hyphen(self):
		with self.assertRaises(frappe.ValidationError):
			make_webstore("-flowers")

	def test_rejects_a_duplicate_slug(self):
		make_webstore("flowers")
		with self.assertRaises(frappe.ValidationError):
			make_webstore("flowers", title="Second Flowers")

	def test_rejects_each_reserved_word(self):
		from upande_webstore.upande_webstore.doctype.webstore.webstore import RESERVED_SLUGS

		for reserved in RESERVED_SLUGS:
			with self.assertRaises(frappe.ValidationError, msg=reserved):
				make_webstore(reserved)
