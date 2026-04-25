from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404

from .forms import ProductForm, InventoryRequestForm
from .models import Product, InventoryRequest


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
