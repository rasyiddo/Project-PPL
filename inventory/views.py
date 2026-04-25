from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ProductForm, InventoryRequestForm, ProcurementRequestForm, StandaloneProcurementRequestForm, ProcurementFulfillmentForm
from .models import Product, InventoryRequest, InventoryTransaction, ProcurementRequest


def get_inventory_request_approval_queryset(user):
    return (
        InventoryRequest.objects
        .exclude(created_by=user)
        .select_related('product', 'created_by', 'approved_by', 'rejected_by')
        .annotate(
            approval_priority=Case(
                When(status='PENDING', then=Value(0)),
                When(status='APPROVED', then=Value(1)),
                When(status='REJECTED', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by('approval_priority', '-created_at')
    )


def get_warehouse_fulfillment_queryset():
    return (
        InventoryRequest.objects
        .filter(status='APPROVED')
        .exclude(procurementrequest__status__in=['PENDING', 'APPROVED', 'ORDERED', 'FULFILLED'])
        .select_related('product', 'created_by', 'approved_by')
        .order_by('-approved_at', '-created_at')
    )


def get_procurement_request_approval_queryset():
    return (
        ProcurementRequest.objects
        .select_related('product', 'inventory_request', 'created_by')
        .annotate(
            approval_priority=Case(
                When(status='PENDING', then=Value(0)),
                When(status='APPROVED', then=Value(1)),
                When(status='REJECTED', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by('approval_priority', '-created_at')
    )


@login_required
def dashboard(request):
    return render(request, 'inventory/dashboard.html')


@login_required
@permission_required('inventory.view_product', raise_exception=True)
def product_list(request):
    products = Product.objects.all()
    return render(request, 'inventory/product_list.html', {
        'products': products
    })


@login_required
@permission_required('inventory.add_product', raise_exception=True)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm()

    return render(request, 'inventory/product_form.html', {
        'form': form
    })


@login_required
@permission_required('inventory.change_product', raise_exception=True)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)

    return render(request, 'inventory/product_form.html', {
        'form': form
    })


@login_required
@permission_required('inventory.view_inventoryrequest', raise_exception=True)
def inventory_request_list(request):
    inventory_requests = InventoryRequest.objects.filter(
        created_by=request.user
    ).select_related('product', 'approved_by', 'rejected_by').order_by('-created_at')
    return render(request, 'inventory/inventory_request_list.html', {
        'inventory_requests': inventory_requests,
        'mode': 'owner',
    })


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def inventory_request_approval_list(request):
    inventory_requests = get_inventory_request_approval_queryset(request.user)
    return render(request, 'inventory/inventory_request_list.html', {
        'inventory_requests': inventory_requests,
        'mode': 'approver',
    })


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def inventory_request_decide(request, pk):
    if request.method != 'POST':
        return redirect('inventory_request_approval_list')

    inventory_request = get_object_or_404(InventoryRequest, pk=pk)
    decision = request.POST.get('decision')

    if inventory_request.status != 'PENDING':
        return redirect('inventory_request_approval_list')

    if inventory_request.created_by_id == request.user.id:
        return redirect('inventory_request_approval_list')

    if decision == 'approve':
        inventory_request.status = 'APPROVED'
        inventory_request.approved_by = request.user
        inventory_request.approved_at = timezone.now()
        inventory_request.rejected_by = None
        inventory_request.rejected_at = None
        inventory_request.rejected_reason = None
        inventory_request.save()
    elif decision == 'reject':
        rejected_reason = (request.POST.get('rejected_reason') or '').strip()
        if not rejected_reason:
            return render(request, 'inventory/inventory_request_list.html', {
                'inventory_requests': get_inventory_request_approval_queryset(request.user),
                'rejection_error_for_id': inventory_request.id,
                'mode': 'approver',
            })

        inventory_request.status = 'REJECTED'
        inventory_request.rejected_by = request.user
        inventory_request.rejected_at = timezone.now()
        inventory_request.rejected_reason = rejected_reason
        inventory_request.approved_by = None
        inventory_request.approved_at = None
        inventory_request.save()

    return redirect('inventory_request_approval_list')


@login_required
@permission_required('inventory.add_inventorytransaction', raise_exception=True)
def warehouse_inventory_request_list(request):
    inventory_requests = get_warehouse_fulfillment_queryset()
    return render(request, 'inventory/warehouse_inventory_request_list.html', {
        'inventory_requests': inventory_requests
    })


@login_required
@permission_required('inventory.view_inventorytransaction', raise_exception=True)
def warehouse_inventory_transaction_list(request):
    transactions = (
        InventoryTransaction.objects
        .select_related('product', 'created_by', 'inventory_request')
        .order_by('-created_at')
    )
    return render(request, 'inventory/warehouse_inventory_transaction_list.html', {
        'transactions': transactions
    })


@login_required
@permission_required('inventory.add_procurementrequest', raise_exception=True)
def procurement_request_create(request):
    rejected_request = None

    if request.method == 'POST':
        form = StandaloneProcurementRequestForm(request.POST)
        if form.is_valid():
            procurement_request = form.save(commit=False)
            procurement_request.created_by = request.user
            procurement_request.save()
            return redirect('procurement_request_list')
    else:
        initial = {}
        from_id = request.GET.get('from')
        if from_id:
            try:
                rejected_request = ProcurementRequest.objects.get(
                    pk=from_id,
                    created_by=request.user,
                    status='REJECTED',
                    inventory_request__isnull=True,
                )
                initial['use_manual_product'] = bool(rejected_request.product_name and not rejected_request.product)
                initial['product'] = rejected_request.product
                initial['product_name'] = rejected_request.product_name
                initial['quantity'] = rejected_request.quantity
                initial['price'] = str(rejected_request.price) if rejected_request.price else ''
                initial['notes'] = rejected_request.notes
            except ProcurementRequest.DoesNotExist:
                pass
        form = StandaloneProcurementRequestForm(initial=initial)

    return render(request, 'inventory/procurement_request_create_form.html', {
        'form': form,
        'products': Product.objects.all(),
        'rejected_request': rejected_request,
    })


@login_required
@permission_required('inventory.view_procurementrequest', raise_exception=True)
def procurement_request_list(request):
    procurement_requests = (
        ProcurementRequest.objects
        .filter(created_by=request.user)
        .select_related('product', 'inventory_request', 'approved_by', 'rejected_by')
        .order_by('-created_at')
    )
    return render(request, 'inventory/procurement_request_list.html', {
        'procurement_requests': procurement_requests
    })


@login_required
@permission_required('inventory.add_procurementrequest', raise_exception=True)
def warehouse_procurement_request_create(request, pk):
    inventory_request = get_object_or_404(
        InventoryRequest.objects.select_related('product'),
        pk=pk,
        status='APPROVED',
    )

    existing_procurement_request = ProcurementRequest.objects.filter(
        inventory_request=inventory_request
    ).exclude(status='REJECTED').first()
    if existing_procurement_request:
        return redirect('procurement_request_list')

    if inventory_request.product and inventory_request.product.stock >= inventory_request.quantity:
        return redirect('warehouse_inventory_request_list')

    procurement_request = ProcurementRequest(
        inventory_request=inventory_request,
        product=inventory_request.product,
        product_name=inventory_request.product_name or (
            inventory_request.product.name if inventory_request.product else None
        ),
        quantity=inventory_request.quantity,
        created_by=request.user,
    )

    if request.method == 'POST':
        form = ProcurementRequestForm(request.POST, instance=procurement_request)
        if form.is_valid():
            procurement_request = form.save(commit=False)
            procurement_request.save()
            return redirect('procurement_request_list')
    else:
        form = ProcurementRequestForm(instance=procurement_request)

    return render(request, 'inventory/procurement_request_form.html', {
        'form': form,
        'inventory_request': inventory_request,
    })


@login_required
@permission_required('inventory.add_inventorytransaction', raise_exception=True)
def procurement_request_fulfill(request, pk):
    procurement_request = get_object_or_404(
        ProcurementRequest.objects.select_related('product', 'inventory_request'),
        pk=pk,
        created_by=request.user,
    )

    if procurement_request.status != 'APPROVED':
        return redirect('procurement_request_list')

    if request.method == 'POST':
        form = ProcurementFulfillmentForm(
            request.POST,
            procurement_request=procurement_request,
        )

        if form.is_valid():
            received_quantity = form.cleaned_data['received_quantity']
            product_name = form.cleaned_data['product_name']

            with transaction.atomic():
                inventory_request = procurement_request.inventory_request
                product = procurement_request.product

                if product:
                    product = Product.objects.select_for_update().get(pk=product.pk)
                else:
                    product = Product.objects.create(
                        name=product_name,
                        stock=0,
                        created_by=request.user,
                    )

                product.stock += received_quantity

                InventoryTransaction.objects.create(
                    product=product,
                    quantity=received_quantity,
                    transaction_type='IN',
                    procurement_request=procurement_request,
                    created_by=request.user,
                )

                if inventory_request:
                    inventory_request = InventoryRequest.objects.select_for_update().get(pk=inventory_request.pk)
                    product.stock -= inventory_request.quantity

                    InventoryTransaction.objects.create(
                        product=product,
                        quantity=inventory_request.quantity,
                        transaction_type='OUT',
                        inventory_request=inventory_request,
                        created_by=request.user,
                    )

                    inventory_request.product = product
                    inventory_request.product_name = None
                    inventory_request.status = 'FULFILLED'
                    inventory_request.save(update_fields=['product', 'product_name', 'status'])

                product.save(update_fields=['stock'])

                procurement_request.product = product
                procurement_request.product_name = product.name
                procurement_request.status = 'FULFILLED'
                procurement_request.save(update_fields=['product', 'product_name', 'status'])

            return redirect('procurement_request_list')
    else:
        form = ProcurementFulfillmentForm(procurement_request=procurement_request)

    return render(request, 'inventory/procurement_request_fulfillment_form.html', {
        'form': form,
        'procurement_request': procurement_request,
        'inventory_request': procurement_request.inventory_request,
    })


@login_required
@permission_required('inventory.approve_procurementrequest', raise_exception=True)
def procurement_request_approval_list(request):
    procurement_requests = get_procurement_request_approval_queryset()
    return render(request, 'inventory/procurement_request_approval_list.html', {
        'procurement_requests': procurement_requests
    })


@login_required
@permission_required('inventory.approve_procurementrequest', raise_exception=True)
def procurement_request_decide(request, pk):
    if request.method != 'POST':
        return redirect('procurement_request_approval_list')

    procurement_request = get_object_or_404(ProcurementRequest, pk=pk)
    decision = request.POST.get('decision')

    if procurement_request.status != 'PENDING':
        return redirect('procurement_request_approval_list')

    if decision == 'approve':
        procurement_request.status = 'APPROVED'
        procurement_request.approved_by = request.user
        procurement_request.approved_at = timezone.now()
        procurement_request.rejected_by = None
        procurement_request.rejected_at = None
        procurement_request.rejected_reason = None
        procurement_request.save()
    elif decision == 'reject':
        rejected_reason = (request.POST.get('rejected_reason') or '').strip()
        if not rejected_reason:
            return render(request, 'inventory/procurement_request_approval_list.html', {
                'procurement_requests': get_procurement_request_approval_queryset(),
                'rejection_error_for_id': procurement_request.id,
            })

        procurement_request.status = 'REJECTED'
        procurement_request.rejected_by = request.user
        procurement_request.rejected_at = timezone.now()
        procurement_request.rejected_reason = rejected_reason
        procurement_request.approved_by = None
        procurement_request.approved_at = None
        procurement_request.save()

    return redirect('procurement_request_approval_list')


@login_required
@permission_required('inventory.add_inventorytransaction', raise_exception=True)
def warehouse_inventory_request_fulfill(request, pk):
    if request.method != 'POST':
        return redirect('warehouse_inventory_request_list')

    with transaction.atomic():
        inventory_request = get_object_or_404(
            InventoryRequest.objects.select_for_update().select_related('product'),
            pk=pk,
        )

        if inventory_request.status != 'APPROVED':
            return redirect('warehouse_inventory_request_list')

        if (
            not inventory_request.product
            or inventory_request.product.stock < inventory_request.quantity
        ):
            return redirect('warehouse_procurement_request_create', pk=inventory_request.pk)

        product = inventory_request.product
        product.stock -= inventory_request.quantity
        product.save(update_fields=['stock'])

        InventoryTransaction.objects.create(
            product=product,
            quantity=inventory_request.quantity,
            transaction_type='OUT',
            inventory_request=inventory_request,
            created_by=request.user,
        )

        inventory_request.status = 'FULFILLED'
        inventory_request.save(update_fields=['status'])

    return redirect('warehouse_inventory_request_list')


@login_required
@permission_required('inventory.add_inventoryrequest', raise_exception=True)
def inventory_request_create(request):
    rejected_request = None

    if request.method == 'POST':
        form = InventoryRequestForm(request.POST)
        if form.is_valid():
            inventory_request = form.save(commit=False)
            inventory_request.created_by = request.user
            inventory_request.save()
            return redirect('inventory_request_list')
    else:
        initial = {}
        from_id = request.GET.get('from')
        if from_id:
            try:
                rejected_request = InventoryRequest.objects.get(
                    pk=from_id,
                    created_by=request.user,
                    status='REJECTED',
                )
                initial['use_manual_product'] = bool(rejected_request.product_name)
                initial['product'] = rejected_request.product
                initial['product_name'] = rejected_request.product_name
                initial['quantity'] = rejected_request.quantity
                initial['reason'] = rejected_request.reason
            except InventoryRequest.DoesNotExist:
                pass
        else:
            product_id = request.GET.get('product')
            if product_id and Product.objects.filter(pk=product_id).exists():
                initial['product'] = product_id
        form = InventoryRequestForm(initial=initial)

    return render(request, 'inventory/inventory_request_form.html', {
        'form': form,
        'products': Product.objects.all(),
        'rejected_request': rejected_request,
    })
