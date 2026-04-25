from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=200)
    stock = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (Stock: {self.stock})"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_product_name')
        ]


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE = [
        ('IN', 'Incoming'),
        ('OUT', 'Outgoing'),
    ]

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    transaction_type = models.CharField(max_length=3, choices=TRANSACTION_TYPE)
    inventory_request = models.ForeignKey('InventoryRequest', on_delete=models.SET_NULL, null=True, blank=True)
    procurement_request = models.ForeignKey('ProcurementRequest', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryRequest(models.Model):
    class Meta:
        permissions = [
            ("approve_inventoryrequest", "Can approve inventory request"),
        ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('FULFILLED', 'Fulfilled'),
    ]

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=200, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    reason = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_inventory_request')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_inventory_request')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_inventory_request')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=200, null=True, blank=True)

    def clean(self):
        if not self.product and not self.product_name:
            raise ValidationError('Please provide either a product or a product name')


class ProcurementRequest(models.Model):
    class Meta:
        permissions = [
            ("approve_procurementrequest", "Can approve procurement request"),
        ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('FULFILLED', 'Received'),
    ]

    inventory_request = models.ForeignKey('InventoryRequest', on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=200, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_procurement_request')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_procurement_request')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_procurement_request')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=200, null=True, blank=True)

    def clean(self):
        if not self.product and not self.product_name:
            raise ValidationError('Please provide either a product or a product name')
