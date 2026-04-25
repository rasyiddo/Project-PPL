from django.db import IntegrityError
from django.test import TestCase
from inventory.forms import ProductForm
from inventory.models import Product


class ProductModelTest(TestCase):

    def test_name_is_uppercase_on_save(self):
        product = Product.objects.create(name='  laptop  ', stock=10)
        self.assertEqual(product.name, 'LAPTOP')

    def test_unique_name_constraint(self):
        Product.objects.create(name='LAPTOP', stock=5)

        with self.assertRaises(IntegrityError):
            Product.objects.create(name='LAPTOP', stock=10)


class ProductFormTest(TestCase):

    def test_name_is_uppercase_and_trimmed(self):
        form = ProductForm(data={
            'name': '  laptop  ',
            'stock': 10
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['name'], 'LAPTOP')

    def test_duplicate_name_case_insensitive(self):
        Product.objects.create(name='LAPTOP', stock=5)

        form = ProductForm(data={
            'name': 'laptop',
            'stock': 10
        })

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_stock_cannot_be_negative(self):
        form = ProductForm(data={
            'name': 'Mouse',
            'stock': -1
        })

        self.assertFalse(form.is_valid())
        self.assertIn('stock', form.errors)
