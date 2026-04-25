from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ProductForm, InventoryRequestForm
from .models import Product, InventoryRequest


def get_inventory_request_approval_queryset(user):
    return (
        InventoryRequest.objects
        .exclude(created_by=user)
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
    inventory_requests = InventoryRequest.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'inventory/inventory_request_list.html', {
        'inventory_requests': inventory_requests
    })


@login_required
@permission_required('inventory.approve_inventoryrequest', raise_exception=True)
def inventory_request_approval_list(request):
    inventory_requests = get_inventory_request_approval_queryset(request.user)
    return render(request, 'inventory/inventory_request_approval_list.html', {
        'inventory_requests': inventory_requests
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
            return render(request, 'inventory/inventory_request_approval_list.html', {
                'inventory_requests': get_inventory_request_approval_queryset(request.user),
                'rejection_error_for_id': inventory_request.id,
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
@permission_required('inventory.add_inventoryrequest', raise_exception=True)
def inventory_request_create(request):
    if request.method == 'POST':
        form = InventoryRequestForm(request.POST)
        if form.is_valid():
            inventory_request = form.save(commit=False)
            inventory_request.created_by = request.user
            inventory_request.save()
            return redirect('inventory_request_list')
    else:
        initial = {}
        product_id = request.GET.get('product')
        if product_id and Product.objects.filter(pk=product_id).exists():
            initial['product'] = product_id
        form = InventoryRequestForm(initial=initial)

    return render(request, 'inventory/inventory_request_form.html', {
        'form': form,
        'products': Product.objects.all()
    })
