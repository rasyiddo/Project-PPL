from django.urls import path

from . import views
from .views import dashboard

urlpatterns = [
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('requests/', views.inventory_request_list, name='inventory_request_list'),
    path('requests/create/', views.inventory_request_create, name='inventory_request_create'),
    path('', dashboard, name='dashboard'),
]
