from django.urls import path

from . import views
from .views import dashboard

urlpatterns = [
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('requests/', views.inventory_request_list, name='inventory_request_list'),
    path('requests/create/', views.inventory_request_create, name='inventory_request_create'),
    path('requests/approval/', views.inventory_request_approval_list, name='inventory_request_approval_list'),
    path('requests/<int:pk>/decision/', views.inventory_request_decide, name='inventory_request_decide'),
    path('requests/<int:pk>/', views.inventory_request_detail, name='inventory_request_detail'),
    path('warehouse/requests/', views.warehouse_inventory_request_list, name='warehouse_inventory_request_list'),
    path('warehouse/transactions/', views.warehouse_inventory_transaction_list, name='warehouse_inventory_transaction_list'),
    path('warehouse/requests/<int:pk>/fulfill/', views.warehouse_inventory_request_fulfill, name='warehouse_inventory_request_fulfill'),
    path('procurement/list/', views.procurement_request_list, name='procurement_request_list'),
    path('procurement/create/', views.procurement_request_create, name='procurement_request_create'),
    path('procurement/<int:pk>/create/', views.warehouse_procurement_request_create, name='warehouse_procurement_request_create'),
    path('procurement/<int:pk>/fulfill/', views.procurement_request_fulfill, name='procurement_request_fulfill'),
    path('procurement/<int:pk>/decision/', views.procurement_request_decide, name='procurement_request_decide'),
    path('procurement/<int:pk>/', views.procurement_request_detail, name='procurement_request_detail'),
    path('procurement/approval/', views.procurement_request_approval_list, name='procurement_request_approval_list'),
    path('export/', views.export_page, name='export_page'),
    path('export/inventory-requests/', views.export_inventory_requests, name='export_inventory_requests'),
    path('export/procurement-requests/', views.export_procurement_requests, name='export_procurement_requests'),
    path('export/transactions/', views.export_inventory_transactions, name='export_inventory_transactions'),
    path('', dashboard, name='dashboard'),
]
