from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Sum, Value, When
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ProductForm, InventoryRequestForm, ProcurementRequestForm, StandaloneProcurementRequestForm, ProcurementFulfillmentForm
from .models import Product, InventoryRequest, InventoryTransaction, ProcurementRequest


LOW_STOCK_THRESHOLD = 10


def _build_ir_timeline(ir):
    """Build a list of timeline event dicts for an InventoryRequest."""
    events = []
    events.append({
        'label': 'Request Submitted',
        'actor': ir.created_by,
        'time': ir.created_at,
        'color': 'blue',
        'note': ir.reason,
        'note_label': 'Reason',
    })

    if ir.status in ('APPROVED', 'FULFILLED') and ir.approved_at:
        events.append({
            'label': 'Request Approved',
            'actor': ir.approved_by,
            'time': ir.approved_at,
            'color': 'emerald',
            'note': None,
            'note_label': None,
        })
    elif ir.status == 'REJECTED' and ir.rejected_at:
        events.append({
            'label': 'Request Rejected',
            'actor': ir.rejected_by,
            'time': ir.rejected_at,
            'color': 'red',
            'note': ir.rejected_reason,
            'note_label': 'Reason',
        })

    if ir.status == 'FULFILLED':
        fulfill_tx = (
            InventoryTransaction.objects
            .filter(inventory_request=ir, transaction_type='OUT')
            .select_related('created_by')
            .order_by('created_at')
            .first()
        )
        if fulfill_tx:
            events.append({
                'label': 'Request Fulfilled',
                'actor': fulfill_tx.created_by,
                'time': fulfill_tx.created_at,
                'color': 'violet',
                'note': f"−{ir.quantity} units dispatched from stock",
                'note_label': 'Transaction',
            })

    for i, event in enumerate(events):
        if i > 0 and events[i - 1]['time'] and event['time']:
            event['duration_since_prev'] = event['time'] - events[i - 1]['time']
        else:
            event['duration_since_prev'] = None

    total_duration = None
    if ir.status in ('FULFILLED', 'REJECTED') and len(events) >= 2:
        first_time = events[0]['time']
        last_time = events[-1]['time']
        if first_time and last_time:
            total_duration = last_time - first_time

    return events, total_duration


def _build_pr_timeline(pr):
    """Build a list of timeline event dicts for a ProcurementRequest."""
    events = []
    events.append({
        'label': 'Procurement Submitted',
        'actor': pr.created_by,
        'time': pr.created_at,
        'color': 'blue',
        'note': pr.notes,
        'note_label': 'Notes',
    })

    if pr.status in ('APPROVED', 'ORDERED', 'FULFILLED') and pr.approved_at:
        events.append({
            'label': 'Procurement Approved',
            'actor': pr.approved_by,
            'time': pr.approved_at,
            'color': 'emerald',
            'note': None,
            'note_label': None,
        })
    elif pr.status == 'REJECTED' and pr.rejected_at:
        events.append({
            'label': 'Procurement Rejected',
            'actor': pr.rejected_by,
            'time': pr.rejected_at,
            'color': 'red',
            'note': pr.rejected_reason,
            'note_label': 'Reason',
        })

    if pr.status == 'ORDERED':
        events.append({
            'label': 'Order Placed / Awaiting Delivery',
            'actor': None,
            'time': None,
            'color': 'amber',
            'note': None,
            'note_label': None,
        })

    if pr.status == 'FULFILLED':
        in_tx = (
            InventoryTransaction.objects
            .filter(procurement_request=pr, transaction_type='IN')
            .select_related('created_by')
            .order_by('created_at')
            .first()
        )
        if in_tx:
            events.append({
                'label': 'Stock Received',
                'actor': in_tx.created_by,
                'time': in_tx.created_at,
                'color': 'violet',
                'note': f"+{pr.quantity} units added to stock",
                'note_label': 'Transaction',
            })

    for i, event in enumerate(events):
        if i > 0 and events[i - 1]['time'] and event['time']:
            event['duration_since_prev'] = event['time'] - events[i - 1]['time']
        else:
            event['duration_since_prev'] = None

    total_duration = None
    if pr.status in ('FULFILLED', 'REJECTED') and len(events) >= 2:
        first_time = events[0]['time']
        last_time = events[-1]['time']
        if first_time and last_time:
            total_duration = last_time - first_time

    return events, total_duration
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


def get_warehouse_fulfillment_queryset(user=None):
    qs = (
        InventoryRequest.objects
        .filter(status__in=['APPROVED', 'FULFILLED'])
        .exclude(
            status='APPROVED',
            procurementrequest__status__in=['PENDING', 'APPROVED', 'ORDERED', 'FULFILLED']
        )
        .select_related('product', 'created_by', 'approved_by')
        .annotate(
            fulfillment_priority=Case(
                When(status='APPROVED', then=Value(0)),
                When(status='FULFILLED', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by('fulfillment_priority', '-approved_at', '-created_at')
    )
    if user is not None:
        qs = qs.exclude(created_by=user)
    return qs


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
    ctx = {}

    if request.user.has_perm('inventory.view_product'):
        ctx['total_products'] = Product.objects.count()
        ctx['low_stock_count'] = Product.objects.filter(stock__lt=LOW_STOCK_THRESHOLD, stock__gt=0).count()
        ctx['out_of_stock_count'] = Product.objects.filter(stock=0).count()
        ctx['low_stock_products'] = (
            Product.objects.filter(stock__lt=LOW_STOCK_THRESHOLD)
            .order_by('stock')[:10]
        )

    if request.user.has_perm('inventory.approve_inventoryrequest'):
        qs = InventoryRequest.objects
        ctx['ir_pending'] = qs.filter(status='PENDING').count()
        ctx['ir_approved'] = qs.filter(status='APPROVED').count()
        ctx['ir_fulfilled'] = qs.filter(status='FULFILLED').count()
        ctx['ir_rejected'] = qs.filter(status='REJECTED').count()
    elif request.user.has_perm('inventory.view_inventoryrequest'):
        qs = InventoryRequest.objects.filter(created_by=request.user)
        ctx['ir_pending'] = qs.filter(status='PENDING').count()
        ctx['ir_approved'] = qs.filter(status='APPROVED').count()
        ctx['ir_fulfilled'] = qs.filter(status='FULFILLED').count()
        ctx['ir_rejected'] = qs.filter(status='REJECTED').count()

    if request.user.has_perm('inventory.approve_procurementrequest'):
        qs = ProcurementRequest.objects
        ctx['pr_pending'] = qs.filter(status='PENDING').count()
        ctx['pr_approved'] = qs.filter(status='APPROVED').count()
        ctx['pr_ordered'] = qs.filter(status='ORDERED').count()
        ctx['pr_fulfilled'] = qs.filter(status='FULFILLED').count()
    elif request.user.has_perm('inventory.view_procurementrequest'):
        qs = ProcurementRequest.objects.filter(created_by=request.user)
        ctx['pr_pending'] = qs.filter(status='PENDING').count()
        ctx['pr_approved'] = qs.filter(status='APPROVED').count()
        ctx['pr_ordered'] = qs.filter(status='ORDERED').count()
        ctx['pr_fulfilled'] = qs.filter(status='FULFILLED').count()

    if request.user.has_perm('inventory.view_inventorytransaction'):
        ctx['recent_transactions'] = (
            InventoryTransaction.objects
            .select_related('product', 'created_by', 'inventory_request', 'procurement_request')
            .order_by('-created_at')[:10]
        )

    return render(request, 'inventory/dashboard.html', ctx)


@login_required
def inventory_request_detail(request, pk):
    ir = get_object_or_404(
        InventoryRequest.objects.select_related(
            'product', 'created_by', 'approved_by', 'rejected_by'
        ),
        pk=pk,
    )
    can_view = (
        ir.created_by == request.user
        or request.user.has_perm('inventory.approve_inventoryrequest')
        or request.user.has_perm('inventory.add_inventorytransaction')
    )
    if not can_view:
        raise PermissionDenied

    timeline, total_duration = _build_ir_timeline(ir)

    linked_procurements = (
        ProcurementRequest.objects
        .filter(inventory_request=ir)
        .select_related('product', 'created_by', 'approved_by', 'rejected_by')
        .order_by('-created_at')
    )

    return render(request, 'inventory/inventory_request_detail.html', {
        'ir': ir,
        'timeline': timeline,
        'total_duration': total_duration,
        'linked_procurements': linked_procurements,
    })


@login_required
def procurement_request_detail(request, pk):
    pr = get_object_or_404(
        ProcurementRequest.objects.select_related(
            'product', 'inventory_request', 'created_by', 'approved_by', 'rejected_by',
            'inventory_request__product', 'inventory_request__created_by',
        ),
        pk=pk,
    )
    can_view = (
        pr.created_by == request.user
        or request.user.has_perm('inventory.approve_procurementrequest')
        or request.user.has_perm('inventory.add_inventorytransaction')
    )
    if not can_view:
        raise PermissionDenied

    timeline, total_duration = _build_pr_timeline(pr)

    return render(request, 'inventory/procurement_request_detail.html', {
        'pr': pr,
        'timeline': timeline,
        'total_duration': total_duration,
    })


@login_required
@permission_required('inventory.view_product', raise_exception=True)
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('created_by'), pk=pk)

    ctx = {'product': product}

    if request.user.has_perm('inventory.view_inventoryrequest') or request.user.has_perm('inventory.approve_inventoryrequest'):
        ctx['ir_count'] = InventoryRequest.objects.filter(product=product).count()
        ctx['ir_fulfilled_count'] = InventoryRequest.objects.filter(product=product, status='FULFILLED').count()
        ctx['ir_pending_count'] = InventoryRequest.objects.filter(product=product, status='PENDING').count()

    if request.user.has_perm('inventory.view_procurementrequest') or request.user.has_perm('inventory.approve_procurementrequest'):
        ctx['pr_count'] = ProcurementRequest.objects.filter(product=product).count()
        ctx['pr_fulfilled_count'] = ProcurementRequest.objects.filter(product=product, status='FULFILLED').count()

    if request.user.has_perm('inventory.view_inventorytransaction'):
        txs = (
            InventoryTransaction.objects
            .filter(product=product)
            .select_related('created_by', 'inventory_request', 'procurement_request')
            .order_by('-created_at')
        )
        in_total = txs.filter(transaction_type='IN').aggregate(total=Sum('quantity'))['total'] or 0
        out_total = txs.filter(transaction_type='OUT').aggregate(total=Sum('quantity'))['total'] or 0
        ctx['transactions'] = txs
        ctx['in_total'] = in_total
        ctx['out_total'] = out_total

    return render(request, 'inventory/product_detail.html', ctx)


@login_required
@permission_required('inventory.view_product', raise_exception=True)
def product_list(request):
    q = request.GET.get('q', '').strip()
    products = Product.objects.all()
    if q:
        products = products.filter(name__icontains=q)
    return render(request, 'inventory/product_list.html', {
        'products': products,
        'q': q,
    })


@login_required
@permission_required('inventory.add_product', raise_exception=True)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)
                product.created_by = request.user
                product.save()
                if product.stock > 0:
                    InventoryTransaction.objects.create(
                        product=product,
                        quantity=product.stock,
                        transaction_type='IN',
                        manual=True,
                        notes='Initial stock on product creation',
                        created_by=request.user,
                    )
            return redirect(request.POST.get('next') or 'product_list')
    else:
        form = ProductForm()

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'is_edit': False,
        'next': request.GET.get('next', ''),
    })


@login_required
@permission_required('inventory.change_product', raise_exception=True)
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            with transaction.atomic():
                # Lock row to get accurate old_stock before saving
                locked = Product.objects.select_for_update().get(pk=pk)
                old_stock = locked.stock
                updated = form.save()
                new_stock = updated.stock
                delta = new_stock - old_stock
                if delta != 0:
                    InventoryTransaction.objects.create(
                        product=updated,
                        quantity=abs(delta),
                        transaction_type='IN' if delta > 0 else 'OUT',
                        manual=True,
                        notes=form.cleaned_data.get('notes', ''),
                        created_by=request.user,
                    )
            return redirect(request.POST.get('next') or 'product_list')
    else:
        form = ProductForm(instance=product)

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'is_edit': True,
        'product': product,
        'next': request.GET.get('next', request.POST.get('next', '')),
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
    inventory_requests = get_warehouse_fulfillment_queryset(user=request.user)
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
        'procurement_requests': procurement_requests,
        'mode': 'owner',
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
            return redirect(request.POST.get('next') or 'procurement_request_list')
    else:
        form = ProcurementRequestForm(instance=procurement_request)

    return render(request, 'inventory/procurement_request_form.html', {
        'form': form,
        'inventory_request': inventory_request,
        'next': request.GET.get('next', ''),
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
    return render(request, 'inventory/procurement_request_list.html', {
        'procurement_requests': procurement_requests,
        'mode': 'approver',
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
            return render(request, 'inventory/procurement_request_list.html', {
                'procurement_requests': get_procurement_request_approval_queryset(),
                'rejection_error_for_id': procurement_request.id,
                'mode': 'approver',
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
            InventoryRequest.objects.select_for_update(of=('self',)),
            pk=pk,
        )

        if inventory_request.status != 'APPROVED':
            return redirect('warehouse_inventory_request_list')

        if not inventory_request.product_id:
            return redirect('warehouse_procurement_request_create', pk=inventory_request.pk)

        product = Product.objects.select_for_update().get(pk=inventory_request.product_id)

        if product.stock < inventory_request.quantity:
            return redirect('warehouse_procurement_request_create', pk=inventory_request.pk)
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
                if rejected_request.product_name:
                    # If the manually-entered product has since been created, use dropdown
                    existing = Product.objects.filter(name__iexact=rejected_request.product_name).first()
                    if existing:
                        initial['use_manual_product'] = False
                        initial['product'] = existing
                        initial['product_name'] = None
                    else:
                        initial['use_manual_product'] = True
                        initial['product_name'] = rejected_request.product_name
                else:
                    initial['use_manual_product'] = False
                    initial['product'] = rejected_request.product
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


# ─── CSV Exports ────────────────────────────────────────────────────────────

import csv
from datetime import date

from django.http import HttpResponse


def _parse_month(request):
    """Return (year, month) from ?month=YYYY-MM, defaulting to current month."""
    raw = request.GET.get('month', '')
    try:
        parts = raw.split('-')
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, IndexError):
        today = date.today()
        year, month = today.year, today.month
    return year, month


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def export_inventory_requests(request):
    year, month = _parse_month(request)
    rows = (
        InventoryRequest.objects
        .filter(created_at__year=year, created_at__month=month)
        .select_related('product', 'created_by', 'approved_by', 'rejected_by')
        .order_by('created_at')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventory_requests_{year}_{month:02d}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Product', 'Quantity', 'Reason', 'Status',
        'Requested By', 'Requested At',
        'Approved By', 'Approved At',
        'Rejected By', 'Rejected At', 'Rejection Reason',
    ])
    for r in rows:
        writer.writerow([
            f'IR-{r.id:05d}',
            r.product.name if r.product else r.product_name or '',
            r.quantity,
            r.reason or '',
            r.get_status_display(),
            str(r.created_by) if r.created_by else '',
            r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
            str(r.approved_by) if r.approved_by else '',
            r.approved_at.strftime('%Y-%m-%d %H:%M') if r.approved_at else '',
            str(r.rejected_by) if r.rejected_by else '',
            r.rejected_at.strftime('%Y-%m-%d %H:%M') if r.rejected_at else '',
            r.rejected_reason or '',
        ])
    return response


@login_required
@permission_required('inventory.approve_procurementrequest', raise_exception=True)
def export_procurement_requests(request):
    year, month = _parse_month(request)
    rows = (
        ProcurementRequest.objects
        .filter(created_at__year=year, created_at__month=month)
        .select_related('product', 'inventory_request', 'created_by', 'approved_by', 'rejected_by')
        .order_by('created_at')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="procurement_requests_{year}_{month:02d}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Linked IR', 'Product', 'Quantity', 'Price', 'Notes', 'Status',
        'Requested By', 'Requested At',
        'Approved By', 'Approved At',
        'Rejected By', 'Rejected At', 'Rejection Reason',
    ])
    for r in rows:
        writer.writerow([
            f'PR-{r.id:05d}',
            f'IR-{r.inventory_request.id:05d}' if r.inventory_request else '',
            r.product.name if r.product else r.product_name or '',
            r.quantity,
            str(r.price) if r.price else '',
            r.notes or '',
            r.get_status_display(),
            str(r.created_by) if r.created_by else '',
            r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
            str(r.approved_by) if r.approved_by else '',
            r.approved_at.strftime('%Y-%m-%d %H:%M') if r.approved_at else '',
            str(r.rejected_by) if r.rejected_by else '',
            r.rejected_at.strftime('%Y-%m-%d %H:%M') if r.rejected_at else '',
            r.rejected_reason or '',
        ])
    return response


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def export_inventory_transactions(request):
    year, month = _parse_month(request)
    rows = (
        InventoryTransaction.objects
        .filter(created_at__year=year, created_at__month=month)
        .select_related('product', 'created_by', 'inventory_request', 'procurement_request')
        .order_by('created_at')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventory_transactions_{year}_{month:02d}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Time', 'Product', 'Type', 'Quantity', 'Reference', 'Manual', 'Notes', 'Recorded By',
    ])
    for t in rows:
        if t.inventory_request:
            ref = f'IR-{t.inventory_request.id:05d}'
        elif t.procurement_request:
            ref = f'PR-{t.procurement_request.id:05d}'
        else:
            ref = ''
        writer.writerow([
            t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            t.product.name if t.product else '',
            t.get_transaction_type_display(),
            t.quantity,
            ref,
            'Yes' if t.manual else 'No',
            t.notes or '',
            str(t.created_by) if t.created_by else '',
        ])
    return response


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def export_page(request):
    today = date.today()
    months = []
    for i in range(12):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append({'value': f'{y}-{m:02d}', 'label': date(y, m, 1).strftime('%B %Y')})
    return render(request, 'inventory/export.html', {
        'months': months,
        'selected': request.GET.get('month', today.strftime('%Y-%m')),
    })
