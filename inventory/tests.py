from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone
from inventory.forms import ProductForm, InventoryRequestForm
from inventory.models import Product, InventoryRequest


# region Product
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


class ProductListInventoryRequestActionTest(TestCase):

    def setUp(self):
        self.product = Product.objects.create(name='MONITOR', stock=5)
        self.user = User.objects.create_user(username='staff', password='secret')
        view_permission = Permission.objects.get(codename='view_product')
        self.user.user_permissions.add(view_permission)
        self.client.force_login(self.user)

    def test_create_request_action_is_hidden_without_permission(self):
        response = self.client.get(reverse('product_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('inventory_request_create') + f'?product={self.product.id}')

    def test_create_request_action_is_visible_with_permission(self):
        create_request_permission = Permission.objects.get(codename='add_inventoryrequest')
        self.user.user_permissions.add(create_request_permission)

        response = self.client.get(reverse('product_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('inventory_request_create') + f'?product={self.product.id}')


# endregion

# region Inventory Request
# noinspection PyMethodMayBeStatic
class InventoryRequestModelTest(TestCase):

    def test_requires_product_or_product_name(self):
        req = InventoryRequest(quantity=1)

        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_valid_with_product(self):
        product = Product.objects.create(name='KEYBOARD', stock=10)

        req = InventoryRequest(
            product=product,
            quantity=1
        )

        # should not raise
        req.full_clean()

    def test_valid_with_product_name(self):
        req = InventoryRequest(
            product_name='Mouse',
            quantity=1
        )

        req.full_clean()


class InventoryRequestFormTest(TestCase):

    def setUp(self):
        self.product = Product.objects.create(name='KEYBOARD', stock=10)

    def test_valid_with_existing_product(self):
        form = InventoryRequestForm(data={
            'product': self.product.id,
            'quantity': 2,
            'reason': 'Need for office',
            'use_manual_product': False
        })

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['product'], self.product)
        self.assertIsNone(form.cleaned_data['product_name'])

    def test_valid_with_manual_product(self):
        form = InventoryRequestForm(data={
            'use_manual_product': True,
            'product_name': 'mouse',
            'quantity': 3,
            'reason': 'New item'
        })

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['product_name'], 'MOUSE')
        self.assertIsNone(form.cleaned_data['product'])

    def test_manual_product_requires_name(self):
        form = InventoryRequestForm(data={
            'use_manual_product': True,
            'quantity': 3,
            'reason': 'New item'
        })

        self.assertFalse(form.is_valid())

    def test_product_required_if_not_manual(self):
        form = InventoryRequestForm(data={
            'use_manual_product': False,
            'quantity': 3,
            'reason': 'New item'
        })

        self.assertFalse(form.is_valid())

    def test_quantity_must_be_positive(self):
        form = InventoryRequestForm(data={
            'product': self.product.id,
            'quantity': 0,
            'reason': 'Invalid'
        })

        self.assertFalse(form.is_valid())

    def test_reason_is_required(self):
        form = InventoryRequestForm(data={
            'product': self.product.id,
            'quantity': 1,
        })

        self.assertFalse(form.is_valid())


class InventoryRequestCreateViewTest(TestCase):

    def setUp(self):
        self.product = Product.objects.create(name='MOUSE', stock=12)
        self.user = User.objects.create_user(username='requester', password='secret')
        add_permission = Permission.objects.get(codename='add_inventoryrequest')
        self.user.user_permissions.add(add_permission)
        self.client.force_login(self.user)

    def test_prefills_selected_product_from_query_param(self):
        response = self.client.get(reverse('inventory_request_create'), {'product': self.product.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<option value="{self.product.id}" data-stock="{self.product.stock}" selected>',
            html=False,
        )

    def test_sets_created_by_to_current_user(self):
        response = self.client.post(reverse('inventory_request_create'), {
            'product': self.product.id,
            'quantity': 2,
            'reason': 'Need replacement',
            'approved_by': '',
        })

        self.assertEqual(response.status_code, 302)
        inventory_request = InventoryRequest.objects.get()
        self.assertEqual(inventory_request.created_by, self.user)


class InventoryRequestListViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='viewer', password='secret')
        view_permission = Permission.objects.get(codename='view_inventoryrequest')
        self.user.user_permissions.add(view_permission)
        self.client.force_login(self.user)

    def test_status_uses_choice_display_label(self):
        request = InventoryRequest.objects.create(
            product_name='CABLE',
            quantity=1,
            reason='Replacement',
            status='PENDING',
            created_by=self.user,
        )

        response = self.client.get(reverse('inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pending Approval')
        self.assertNotContains(response, f'<td class="p-2">{request.status}</td>', html=False)
        self.assertContains(response, 'bg-amber-100 text-amber-800')

    def test_only_shows_requests_owned_by_current_user(self):
        other_user = User.objects.create_user(username='other-user', password='secret')
        own_request = InventoryRequest.objects.create(
            product_name='MOUSE',
            quantity=1,
            reason='Own request',
            status='PENDING',
            created_by=self.user,
        )
        other_request = InventoryRequest.objects.create(
            product_name='KEYBOARD',
            quantity=1,
            reason='Other user request',
            status='APPROVED',
            created_by=other_user,
        )

        response = self.client.get(reverse('inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_request.product_name)
        self.assertNotContains(response, other_request.product_name)

    def test_displays_request_and_decision_timestamps(self):
        approved_at = timezone.now()
        inventory_request = InventoryRequest.objects.create(
            product_name='LAPTOP',
            quantity=1,
            reason='Team usage',
            status='APPROVED',
            created_by=self.user,
            approved_at=approved_at,
        )

        response = self.client.get(reverse('inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Requested At')
        self.assertContains(response, 'Approved / Rejected At')
        self.assertContains(response, date_filter(timezone.localtime(inventory_request.created_at), "M d, Y H:i"))
        self.assertContains(response, date_filter(timezone.localtime(approved_at), "M d, Y H:i"))


class InventoryRequestApprovalViewTest(TestCase):

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='secret')
        approve_permission = Permission.objects.get(codename='approve_inventoryrequest')
        self.manager.user_permissions.add(approve_permission)
        self.client.force_login(self.manager)

    def test_approval_list_sorts_pending_before_approved(self):
        approved_request = InventoryRequest.objects.create(
            product_name='PRINTER',
            quantity=1,
            reason='Replacement',
            status='APPROVED',
        )
        pending_request = InventoryRequest.objects.create(
            product_name='PAPER',
            quantity=3,
            reason='Office use',
            status='PENDING',
        )

        response = self.client.get(reverse('inventory_request_approval_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index(f'>{pending_request.id}</td>'), content.index(f'>{approved_request.id}</td>'))

    def test_approval_list_excludes_manager_own_request(self):
        own_request = InventoryRequest.objects.create(
            product_name='HEADSET',
            quantity=1,
            reason='Need for meeting room',
            status='PENDING',
            created_by=self.manager,
        )
        visible_request = InventoryRequest.objects.create(
            product_name='DOCK',
            quantity=1,
            reason='Replacement',
            status='PENDING',
        )

        response = self.client.get(reverse('inventory_request_approval_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, visible_request.product_name)
        self.assertNotContains(response, own_request.product_name)

    def test_approve_action_updates_request(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='INK',
            quantity=2,
            reason='Low stock',
            status='PENDING',
        )

        response = self.client.post(reverse('inventory_request_decide', args=[inventory_request.id]), {
            'decision': 'approve',
        })

        self.assertEqual(response.status_code, 302)
        inventory_request.refresh_from_db()
        self.assertEqual(inventory_request.status, 'APPROVED')
        self.assertEqual(inventory_request.approved_by, self.manager)
        self.assertIsNotNone(inventory_request.approved_at)

    def test_reject_action_requires_reason(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='TABLET',
            quantity=1,
            reason='Experiment',
            status='PENDING',
        )

        response = self.client.post(reverse('inventory_request_decide', args=[inventory_request.id]), {
            'decision': 'reject',
            'rejected_reason': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rejection reason is required.')
        inventory_request.refresh_from_db()
        self.assertEqual(inventory_request.status, 'PENDING')

    def test_reject_action_sets_reason_and_actor(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='SCANNER',
            quantity=1,
            reason='Not needed',
            status='PENDING',
        )

        response = self.client.post(reverse('inventory_request_decide', args=[inventory_request.id]), {
            'decision': 'reject',
            'rejected_reason': 'Budget not approved',
        })

        self.assertEqual(response.status_code, 302)
        inventory_request.refresh_from_db()
        self.assertEqual(inventory_request.status, 'REJECTED')
        self.assertEqual(inventory_request.rejected_reason, 'Budget not approved')
        self.assertEqual(inventory_request.rejected_by, self.manager)

    def test_manager_cannot_approve_own_request(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='HEADSET',
            quantity=1,
            reason='Need for meeting room',
            status='PENDING',
            created_by=self.manager,
        )

        response = self.client.post(reverse('inventory_request_decide', args=[inventory_request.id]), {
            'decision': 'approve',
        })

        self.assertEqual(response.status_code, 302)
        inventory_request.refresh_from_db()
        self.assertEqual(inventory_request.status, 'PENDING')
        self.assertIsNone(inventory_request.approved_by)

# endregion
