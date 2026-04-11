from django.contrib import admin

from inventory.models import Product, InventoryRequest, ProcurementRequest, InventoryTransaction

admin.site.register(Product)
admin.site.register(InventoryTransaction)
admin.site.register(ProcurementRequest)
admin.site.register(InventoryRequest)
