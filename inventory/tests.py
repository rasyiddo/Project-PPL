from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone
from inventory.forms import ProductForm, InventoryRequestForm, StandaloneProcurementRequestForm
from inventory.models import Product, InventoryRequest, InventoryTransaction, ProcurementRequest


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
        self.assertLess(
            content.index(f'IR-{pending_request.id:05d}'),
            content.index(f'IR-{approved_request.id:05d}'),
        )

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

    def test_approval_list_shows_stock_and_procurement_label(self):
        low_stock_product = Product.objects.create(name='PRINTER', stock=1)
        InventoryRequest.objects.create(
            product=low_stock_product,
            quantity=3,
            reason='Replace broken unit',
            status='PENDING',
        )
        InventoryRequest.objects.create(
            product_name='NEW TABLET',
            quantity=2,
            reason='New joiners',
            status='PENDING',
        )

        response = self.client.get(reverse('inventory_request_approval_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current<br/>Stock')
        self.assertContains(response, 'Needs Procurement')
        self.assertContains(response, str(low_stock_product.stock))
        self.assertContains(response, 'NEW TABLET')


# endregion

# region Warehouse Inventory

class WarehouseInventoryRequestViewTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='warehouse', password='secret')
        add_transaction_permission = Permission.objects.get(codename='add_inventorytransaction')
        add_procurement_permission = Permission.objects.get(codename='add_procurementrequest')
        view_procurement_permission = Permission.objects.get(codename='view_procurementrequest')
        view_transaction_permission = Permission.objects.get(codename='view_inventorytransaction')
        self.staff.user_permissions.add(
            add_transaction_permission,
            add_procurement_permission,
            view_procurement_permission,
            view_transaction_permission,
        )
        self.client.force_login(self.staff)

    def test_fulfillment_list_shows_approved_requests_without_procurement_request(self):
        ready_product = Product.objects.create(name='MOUSE', stock=10)
        not_enough_stock_product = Product.objects.create(name='PRINTER', stock=1)

        ready_request = InventoryRequest.objects.create(
            product=ready_product,
            quantity=3,
            reason='Office use',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        InventoryRequest.objects.create(
            product=not_enough_stock_product,
            quantity=2,
            reason='Needs procurement',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        InventoryRequest.objects.create(
            product=ready_product,
            quantity=1,
            reason='Still pending',
            status='PENDING',
        )

        response = self.client.get(reverse('warehouse_inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ready_request.product.name)
        self.assertContains(response, not_enough_stock_product.name)
        self.assertContains(response, reverse('warehouse_inventory_request_fulfill', args=[ready_request.id]))
        self.assertNotContains(response, 'Still pending')

    def test_fulfill_action_updates_stock_request_and_transaction(self):
        product = Product.objects.create(name='KEYBOARD', stock=8)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=3,
            reason='Replacement',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('warehouse_inventory_request_fulfill', args=[inventory_request.id]))

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        inventory_request.refresh_from_db()
        self.assertEqual(product.stock, 5)
        self.assertEqual(inventory_request.status, 'FULFILLED')

        transaction = InventoryTransaction.objects.get(inventory_request=inventory_request)
        self.assertEqual(transaction.product, product)
        self.assertEqual(transaction.quantity, 3)
        self.assertEqual(transaction.transaction_type, 'OUT')
        self.assertEqual(transaction.created_by, self.staff)

    def test_fulfill_action_does_not_process_when_stock_is_insufficient(self):
        product = Product.objects.create(name='LAPTOP', stock=1)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=3,
            reason='Replacement',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('warehouse_inventory_request_fulfill', args=[inventory_request.id]))

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        inventory_request.refresh_from_db()
        self.assertEqual(product.stock, 1)
        self.assertEqual(inventory_request.status, 'APPROVED')
        self.assertFalse(InventoryTransaction.objects.filter(inventory_request=inventory_request).exists())

    def test_transaction_history_shows_stock_movements(self):
        product = Product.objects.create(name='MONITOR', stock=6)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=2,
            reason='Replacement',
            status='FULFILLED',
        )
        incoming = InventoryTransaction.objects.create(
            product=product,
            quantity=5,
            transaction_type='IN',
            created_by=self.staff,
        )
        outgoing = InventoryTransaction.objects.create(
            product=product,
            quantity=2,
            transaction_type='OUT',
            inventory_request=inventory_request,
            created_by=self.staff,
        )

        response = self.client.get(reverse('warehouse_inventory_transaction_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incoming')
        self.assertContains(response, 'Outgoing')
        self.assertContains(response, product.name)
        self.assertContains(response, f'#{outgoing.inventory_request.id}')
        self.assertContains(response, date_filter(timezone.localtime(incoming.created_at), "M d, Y H:i"))

    def test_procurement_queue_shows_approved_requests_needing_procurement(self):
        missing_product_request = InventoryRequest.objects.create(
            product_name='NEW TABLET',
            quantity=2,
            reason='New joiners',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        available_product = Product.objects.create(name='MOUSE', stock=10)
        InventoryRequest.objects.create(
            product=available_product,
            quantity=3,
            reason='Can be fulfilled directly',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.get(reverse('warehouse_inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, missing_product_request.product_name)
        self.assertContains(response, available_product.name)

    def test_non_fulfillable_request_redirects_to_procurement_form(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='NEW MONITOR',
            quantity=2,
            reason='Expansion',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('warehouse_inventory_request_fulfill', args=[inventory_request.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers['Location'],
            reverse('warehouse_procurement_request_create', args=[inventory_request.id]),
        )

    def test_procurement_request_can_be_created_from_procurement_form(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='NEW MONITOR',
            quantity=2,
            reason='Expansion',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('warehouse_procurement_request_create', args=[inventory_request.id]), {
            'price': '1.250.000',
            'notes': 'Need supplier quotation and delivery estimate.',
        })

        self.assertEqual(response.status_code, 302)
        procurement_request = ProcurementRequest.objects.get()
        self.assertEqual(procurement_request.inventory_request, inventory_request)
        self.assertEqual(procurement_request.product_name, 'NEW MONITOR')
        self.assertEqual(procurement_request.quantity, 2)
        self.assertEqual(procurement_request.created_by, self.staff)
        self.assertEqual(procurement_request.status, 'PENDING')
        self.assertEqual(str(procurement_request.price), '1250000.00')
        self.assertEqual(procurement_request.notes, 'Need supplier quotation and delivery estimate.')

    def test_procurement_request_is_not_created_for_fulfillable_inventory_request(self):
        product = Product.objects.create(name='KEYBOARD', stock=10)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=2,
            reason='Can be fulfilled',
            status='APPROVED',
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('warehouse_procurement_request_create', args=[inventory_request.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProcurementRequest.objects.filter(inventory_request=inventory_request).exists())

    def test_existing_product_procurement_fulfillment_records_incoming_and_outgoing(self):
        product = Product.objects.create(name='HEADSET', stock=1)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=3,
            reason='Replacement',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        procurement_request = ProcurementRequest.objects.create(
            inventory_request=inventory_request,
            product=product,
            product_name=product.name,
            quantity=3,
            price='300000.00',
            notes='Approved vendor quote',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('procurement_request_fulfill', args=[procurement_request.id]), {
            'product_name': product.name,
            'received_quantity': 5,
        })

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        inventory_request.refresh_from_db()
        procurement_request.refresh_from_db()
        self.assertEqual(product.stock, 3)
        self.assertEqual(inventory_request.status, 'FULFILLED')
        self.assertEqual(procurement_request.status, 'FULFILLED')
        self.assertEqual(
            InventoryTransaction.objects.filter(procurement_request=procurement_request, transaction_type='IN').count(),
            1,
        )
        self.assertEqual(
            InventoryTransaction.objects.filter(inventory_request=inventory_request, transaction_type='OUT').count(),
            1,
        )

    def test_new_product_procurement_fulfillment_creates_product_and_fulfills_request(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='TABLET',
            quantity=2,
            reason='New joiners',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        procurement_request = ProcurementRequest.objects.create(
            inventory_request=inventory_request,
            product_name='TABLET',
            quantity=2,
            price='5000000.00',
            notes='Approved purchase',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('procurement_request_fulfill', args=[procurement_request.id]), {
            'product_name': 'Tablet Pro',
            'received_quantity': 3,
        })

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='TABLET PRO')
        inventory_request.refresh_from_db()
        procurement_request.refresh_from_db()
        self.assertEqual(product.stock, 1)
        self.assertEqual(inventory_request.product, product)
        self.assertEqual(inventory_request.status, 'FULFILLED')
        self.assertEqual(procurement_request.product, product)
        self.assertEqual(procurement_request.status, 'FULFILLED')

    def test_procurement_fulfillment_requires_received_quantity_to_cover_inventory_request(self):
        inventory_request = InventoryRequest.objects.create(
            product_name='MONITOR ARM',
            quantity=4,
            reason='Expansion',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        procurement_request = ProcurementRequest.objects.create(
            inventory_request=inventory_request,
            product_name='MONITOR ARM',
            quantity=4,
            price='750000.00',
            notes='Approved purchase',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('procurement_request_fulfill', args=[procurement_request.id]), {
            'product_name': 'MONITOR ARM',
            'received_quantity': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current stock (0) + received quantity (2) must be at least 4 to fulfill the request.')
        procurement_request.refresh_from_db()
        inventory_request.refresh_from_db()
        self.assertEqual(procurement_request.status, 'APPROVED')
        self.assertEqual(inventory_request.status, 'APPROVED')

    def test_procurement_fulfillment_requires_received_quantity_to_cover_inventory_request_but_compare_to_current_stock(self):
        product = Product.objects.create(name='MONITOR ARM', stock=2)
        inventory_request = InventoryRequest.objects.create(
            product=product,
            quantity=4,
            reason='Expansion',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        procurement_request = ProcurementRequest.objects.create(
            inventory_request=inventory_request,
            product=product,
            quantity=4,
            price='750000.00',
            notes='Approved purchase',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )

        response = self.client.post(reverse('procurement_request_fulfill', args=[procurement_request.id]), {
            'product_name': 'MONITOR ARM',
            'received_quantity': 2,
        })

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        inventory_request.refresh_from_db()
        procurement_request.refresh_from_db()
        self.assertEqual(product.stock, 0)
        self.assertEqual(inventory_request.status, 'FULFILLED')
        self.assertEqual(procurement_request.status, 'FULFILLED')
        self.assertEqual(
            InventoryTransaction.objects.filter(procurement_request=procurement_request, transaction_type='IN').count(),
            1,
        )
        self.assertEqual(
            InventoryTransaction.objects.filter(inventory_request=inventory_request, transaction_type='OUT').count(),
            1,
        )

    def test_my_procurement_list_only_shows_current_staff_requests(self):
        own_request = ProcurementRequest.objects.create(
            product_name='MOUSEPAD',
            quantity=4,
            price='20.00',
            notes='Bulk order',
            created_by=self.staff,
        )
        other_staff = User.objects.create_user(username='other-warehouse', password='secret')
        ProcurementRequest.objects.create(
            product_name='CHAIR',
            quantity=2,
            price='50.00',
            notes='Other staff order',
            created_by=other_staff,
        )

        response = self.client.get(reverse('procurement_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_request.product_name)
        self.assertNotContains(response, 'CHAIR')
        self.assertContains(response, 'Rp 20')


# endregion

# region Procurement Request

class ProcurementRequestApprovalViewTest(TestCase):

    def setUp(self):
        self.manager = User.objects.create_user(username='proc-manager', password='secret')
        approve_permission = Permission.objects.get(codename='approve_procurementrequest')
        self.manager.user_permissions.add(approve_permission)
        self.client.force_login(self.manager)

    def test_procurement_request_appears_in_manager_approval_list(self):
        procurement_request = ProcurementRequest.objects.create(
            product_name='DOCKING STATION',
            quantity=4,
            price='149.00',
            notes='Needed for onboarding.',
            created_by=User.objects.create_user(username='warehouse-maker', password='secret'),
        )

        response = self.client.get(reverse('procurement_request_approval_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, procurement_request.product_name)
        self.assertContains(response, 'Rp 149')
        self.assertContains(response, procurement_request.notes)

    def test_procurement_approve_action_updates_request(self):
        procurement_request = ProcurementRequest.objects.create(
            product_name='WEBCAM',
            quantity=1,
            price='89.00',
        )

        response = self.client.post(reverse('procurement_request_decide', args=[procurement_request.id]), {
            'decision': 'approve',
        })

        self.assertEqual(response.status_code, 302)
        procurement_request.refresh_from_db()
        self.assertEqual(procurement_request.status, 'APPROVED')
        self.assertEqual(procurement_request.approved_by, self.manager)
        self.assertIsNotNone(procurement_request.approved_at)

# endregion


# region Approval list ID format

class InventoryRequestApprovalListIdFormatTest(TestCase):

    def setUp(self):
        self.manager = User.objects.create_user(username='manager-fmt', password='secret')
        approve_permission = Permission.objects.get(codename='approve_inventoryrequest')
        self.manager.user_permissions.add(approve_permission)
        self.client.force_login(self.manager)

    def test_id_is_displayed_with_ir_prefix_and_zero_padding(self):
        req = InventoryRequest.objects.create(product_name='CABLE', quantity=1, reason='Test')
        response = self.client.get(reverse('inventory_request_approval_list'))
        self.assertContains(response, f'IR-{req.id:05d}')

    def test_rejected_request_shown_as_single_row_with_reason(self):
        req = InventoryRequest.objects.create(
            product_name='CABLE',
            quantity=1,
            reason='Test',
            status='REJECTED',
            rejected_reason='Out of budget',
            rejected_by=self.manager,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('inventory_request_approval_list'))
        self.assertContains(response, 'Out of budget')
        self.assertContains(response, f'IR-{req.id:05d}')

    def test_approved_request_shows_approved_by(self):
        approver = User.objects.create_user(username='approver', password='secret')
        req = InventoryRequest.objects.create(
            product_name='DESK',
            quantity=1,
            reason='Test',
            status='APPROVED',
            approved_by=approver,
            approved_at=timezone.now(),
        )
        response = self.client.get(reverse('inventory_request_approval_list'))
        self.assertContains(response, approver.username)
        self.assertContains(response, f'IR-{req.id:05d}')

# endregion


# region Re-submit from rejected

class InventoryRequestResubmitTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='requester', password='secret')
        self.user.user_permissions.add(
            Permission.objects.get(codename='add_inventoryrequest'),
            Permission.objects.get(codename='view_inventoryrequest'),
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(name='MOUSE', stock=5)

    def _make_rejected(self, **kwargs):
        defaults = dict(
            product=self.product,
            quantity=3,
            reason='Office use',
            status='REJECTED',
            rejected_reason='Budget frozen',
            created_by=self.user,
            rejected_at=timezone.now(),
        )
        defaults.update(kwargs)
        return InventoryRequest.objects.create(**defaults)

    def test_resubmit_link_shown_for_rejected_request(self):
        req = self._make_rejected()
        response = self.client.get(reverse('inventory_request_list'))
        self.assertContains(response, reverse('inventory_request_create') + f'?from={req.id}')

    def test_resubmit_link_not_shown_for_pending_request(self):
        req = InventoryRequest.objects.create(
            product=self.product, quantity=1, reason='Test',
            status='PENDING', created_by=self.user,
        )
        response = self.client.get(reverse('inventory_request_list'))
        self.assertNotContains(response, f'?from={req.id}')

    def test_from_param_prepopulates_form_with_rejected_request_fields(self):
        req = self._make_rejected()
        response = self.client.get(reverse('inventory_request_create'), {'from': req.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Budget frozen')
        self.assertContains(response, f'Re-submitting based on rejected request #{req.id}')
        form = response.context['form']
        self.assertEqual(form.initial.get('quantity'), 3)
        self.assertEqual(form.initial.get('reason'), 'Office use')

    def test_from_param_prepopulates_manual_product_fields(self):
        req = InventoryRequest.objects.create(
            product_name='CUSTOM ITEM',
            quantity=2,
            reason='Special order',
            status='REJECTED',
            rejected_reason='Wrong vendor',
            created_by=self.user,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('inventory_request_create'), {'from': req.id})
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial.get('product_name'), 'CUSTOM ITEM')
        self.assertTrue(form.initial.get('use_manual_product'))

    def test_from_param_ignored_for_non_rejected_request(self):
        pending = InventoryRequest.objects.create(
            product=self.product, quantity=1, reason='Test',
            status='PENDING', created_by=self.user,
        )
        response = self.client.get(reverse('inventory_request_create'), {'from': pending.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('rejected_request'))

    def test_from_param_ignored_for_other_users_rejected_request(self):
        other = User.objects.create_user(username='other', password='secret')
        req = InventoryRequest.objects.create(
            product=self.product, quantity=1, reason='Test',
            status='REJECTED', rejected_reason='No budget',
            created_by=other, rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('inventory_request_create'), {'from': req.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('rejected_request'))


# endregion


# region Standalone Procurement Request

class StandaloneProcurementRequestFormTest(TestCase):

    def setUp(self):
        self.product = Product.objects.create(name='KEYBOARD', stock=10)

    def test_valid_with_existing_product(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': False,
            'product': self.product.id,
            'quantity': 2,
            'price': '500.000',
            'notes': 'Restock',
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['product'], self.product)
        self.assertIsNone(form.cleaned_data['product_name'])

    def test_valid_with_manual_product(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': True,
            'product_name': 'new widget',
            'quantity': 5,
            'price': '200.000',
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['product_name'], 'NEW WIDGET')
        self.assertIsNone(form.cleaned_data['product'])

    def test_requires_product_when_not_manual(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': False,
            'quantity': 2,
            'price': '100.000',
        })
        self.assertFalse(form.is_valid())

    def test_requires_product_name_when_manual(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': True,
            'product_name': '',
            'quantity': 2,
            'price': '100.000',
        })
        self.assertFalse(form.is_valid())

    def test_price_must_be_positive(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': False,
            'product': self.product.id,
            'quantity': 1,
            'price': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_quantity_must_be_at_least_one(self):
        form = StandaloneProcurementRequestForm(data={
            'use_manual_product': False,
            'product': self.product.id,
            'quantity': 0,
            'price': '100.000',
        })
        self.assertFalse(form.is_valid())


class StandaloneProcurementRequestCreateViewTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='warehouse', password='secret')
        self.staff.user_permissions.add(
            Permission.objects.get(codename='add_procurementrequest'),
            Permission.objects.get(codename='view_procurementrequest'),
        )
        self.client.force_login(self.staff)
        self.product = Product.objects.create(name='HEADSET', stock=3)

    def test_create_standalone_with_existing_product(self):
        response = self.client.post(reverse('procurement_request_create'), {
            'use_manual_product': False,
            'product': self.product.id,
            'quantity': 5,
            'price': '1.500.000',
            'notes': 'Restock run',
        })
        self.assertEqual(response.status_code, 302)
        pr = ProcurementRequest.objects.get()
        self.assertEqual(pr.product, self.product)
        self.assertIsNone(pr.inventory_request)
        self.assertEqual(pr.quantity, 5)
        self.assertEqual(pr.created_by, self.staff)
        self.assertEqual(pr.status, 'PENDING')

    def test_create_standalone_with_manual_product(self):
        response = self.client.post(reverse('procurement_request_create'), {
            'use_manual_product': True,
            'product_name': 'brand new item',
            'quantity': 2,
            'price': '300.000',
        })
        self.assertEqual(response.status_code, 302)
        pr = ProcurementRequest.objects.get()
        self.assertIsNone(pr.product)
        self.assertEqual(pr.product_name, 'BRAND NEW ITEM')
        self.assertIsNone(pr.inventory_request)

    def test_resubmit_link_shown_for_rejected_standalone(self):
        rejected = ProcurementRequest.objects.create(
            product=self.product,
            quantity=4,
            price='200.00',
            status='REJECTED',
            rejected_reason='Wrong specification',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('procurement_request_list'))
        self.assertContains(response, reverse('procurement_request_create') + f'?from={rejected.id}')

    def test_resubmit_link_not_shown_for_linked_rejected_procurement(self):
        inv_req = InventoryRequest.objects.create(
            product=self.product, quantity=2, reason='Test', status='REJECTED',
        )
        linked_rejected = ProcurementRequest.objects.create(
            inventory_request=inv_req,
            product=self.product,
            quantity=2,
            price='100.00',
            status='REJECTED',
            rejected_reason='No budget',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('procurement_request_list'))
        self.assertNotContains(response, f'?from={linked_rejected.id}')

    def test_from_param_prepopulates_form_with_rejected_standalone(self):
        rejected = ProcurementRequest.objects.create(
            product=self.product,
            quantity=4,
            price='200.00',
            notes='Previous attempt',
            status='REJECTED',
            rejected_reason='Wrong specification',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('procurement_request_create'), {'from': rejected.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Wrong specification')
        self.assertContains(response, f'Re-submitting based on rejected request #{rejected.id}')
        form = response.context['form']
        self.assertEqual(form.initial.get('quantity'), 4)
        self.assertEqual(form.initial.get('notes'), 'Previous attempt')

    def test_from_param_ignored_if_request_has_inventory_request(self):
        inv_req = InventoryRequest.objects.create(
            product=self.product, quantity=2, reason='Test', status='REJECTED',
        )
        linked = ProcurementRequest.objects.create(
            inventory_request=inv_req,
            product=self.product,
            quantity=2,
            price='100.00',
            status='REJECTED',
            rejected_reason='No budget',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('procurement_request_create'), {'from': linked.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('rejected_request'))

    def test_from_param_ignored_for_other_users_rejected_request(self):
        other = User.objects.create_user(username='other-staff', password='secret')
        rejected = ProcurementRequest.objects.create(
            product=self.product,
            quantity=3,
            price='150.00',
            status='REJECTED',
            rejected_reason='Wrong vendor',
            created_by=other,
            rejected_at=timezone.now(),
        )
        response = self.client.get(reverse('procurement_request_create'), {'from': rejected.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get('rejected_request'))


class StandaloneProcurementFulfillmentValidationTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='warehouse', password='secret')
        self.staff.user_permissions.add(
            Permission.objects.get(codename='add_inventorytransaction'),
            Permission.objects.get(codename='view_procurementrequest'),
        )
        self.client.force_login(self.staff)

    def test_standalone_fulfillment_rejects_quantity_below_requested(self):
        product = Product.objects.create(name='CABLE', stock=0)
        pr = ProcurementRequest.objects.create(
            product=product,
            product_name=product.name,
            quantity=5,
            price='100.00',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )
        response = self.client.post(reverse('procurement_request_fulfill', args=[pr.id]), {
            'product_name': product.name,
            'received_quantity': 3,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Received quantity must be at least 5')
        pr.refresh_from_db()
        self.assertEqual(pr.status, 'APPROVED')

    def test_standalone_fulfillment_accepts_exact_requested_quantity(self):
        product = Product.objects.create(name='CABLE', stock=0)
        pr = ProcurementRequest.objects.create(
            product=product,
            product_name=product.name,
            quantity=5,
            price='100.00',
            status='APPROVED',
            created_by=self.staff,
            approved_at=timezone.now(),
        )
        response = self.client.post(reverse('procurement_request_fulfill', args=[pr.id]), {
            'product_name': product.name,
            'received_quantity': 5,
        })
        self.assertEqual(response.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, 'FULFILLED')


class WarehouseQueueAfterProcurementRejectionTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='warehouse', password='secret')
        self.staff.user_permissions.add(
            Permission.objects.get(codename='add_inventorytransaction'),
            Permission.objects.get(codename='add_procurementrequest'),
            Permission.objects.get(codename='view_procurementrequest'),
        )
        self.client.force_login(self.staff)

    def test_approved_inventory_request_reappears_after_procurement_rejection(self):
        product = Product.objects.create(name='SCANNER', stock=0)
        inv_req = InventoryRequest.objects.create(
            product=product,
            quantity=3,
            reason='Replacement',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        ProcurementRequest.objects.create(
            inventory_request=inv_req,
            product=product,
            quantity=3,
            price='500.00',
            status='REJECTED',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )

        response = self.client.get(reverse('warehouse_inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)

    def test_approved_inventory_request_hidden_when_active_procurement_exists(self):
        product = Product.objects.create(name='PROJECTOR', stock=0)
        inv_req = InventoryRequest.objects.create(
            product=product,
            quantity=1,
            reason='Meeting room',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        ProcurementRequest.objects.create(
            inventory_request=inv_req,
            product=product,
            quantity=1,
            price='2000.00',
            status='PENDING',
            created_by=self.staff,
        )

        response = self.client.get(reverse('warehouse_inventory_request_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, product.name)

    def test_new_procurement_can_be_created_after_rejection(self):
        product = Product.objects.create(name='MONITOR', stock=0)
        inv_req = InventoryRequest.objects.create(
            product=product,
            quantity=2,
            reason='Expansion',
            status='APPROVED',
            approved_at=timezone.now(),
        )
        ProcurementRequest.objects.create(
            inventory_request=inv_req,
            product=product,
            quantity=2,
            price='800.00',
            status='REJECTED',
            created_by=self.staff,
            rejected_at=timezone.now(),
        )

        response = self.client.post(
            reverse('warehouse_procurement_request_create', args=[inv_req.id]),
            {'price': '900.000', 'notes': 'Second attempt'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProcurementRequest.objects.filter(inventory_request=inv_req).count(), 2)
        new_pr = ProcurementRequest.objects.filter(inventory_request=inv_req, status='PENDING').first()
        self.assertIsNotNone(new_pr)

# endregion
