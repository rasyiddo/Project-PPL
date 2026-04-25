from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Product, InventoryRequest, ProcurementRequest


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'w-full border rounded-lg px-3 py-2 mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500'
    }))

    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full border rounded-lg px-3 py-2 mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500'
    }))


class ProductForm(forms.ModelForm):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full border rounded-lg px-3 py-2 mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500',
            'rows': 2,
            'placeholder': 'Explain the reason for the stock change'
        }),
        label='Adjustment Notes'
    )

    class Meta:
        model = Product
        fields = ['name', 'stock']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full border rounded-lg px-3 py-2 mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'w-full border rounded-lg px-3 py-2 mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise forms.ValidationError("Name field is required.")
        # Sanitize to Upper Case
        name = name.upper().strip()

        # Check duplicates (case-insensitive)
        qs = Product.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Product with this name already exists.")
        return name

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is None:
            raise forms.ValidationError("Stock field is required.")
        if stock < 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock

    def clean(self):
        cleaned_data = super().clean()
        # On edit, notes are required if stock actually changes
        if self.instance.pk:
            new_stock = cleaned_data.get('stock')
            if new_stock is not None and new_stock != self.instance.stock:
                notes = (cleaned_data.get('notes') or '').strip()
                if not notes:
                    self.add_error('notes', 'Please provide a reason for the stock adjustment.')
        return cleaned_data


class InventoryRequestForm(forms.ModelForm):
    class Meta:
        model = InventoryRequest
        fields = [
            'product',
            'product_name',
            'quantity',
            'reason',
            'approved_by',
        ]

        widgets = {
            'product': forms.Select(attrs={
                'class': 'w-full border rounded-lg px-3 py-2'
            }),
            'product_name': forms.TextInput(attrs={
                'class': 'w-full border rounded-lg px-3 py-2',
                'placeholder': 'Enter product name manually'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full border rounded-lg px-3 py-2'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'w-full border rounded-lg px-3 py-2',
                'rows': 3,
                'placeholder': 'Reason for request'
            }),
        }

    use_manual_product = forms.BooleanField(
        required=False,
        label="Product not found? Enter manually"
    )

    def clean(self):
        cleaned_data = super().clean()

        use_manual = cleaned_data.get('use_manual_product')
        product_id = self.data.get('product')
        product_name = cleaned_data.get('product_name')
        quantity = cleaned_data.get('quantity')
        reason = cleaned_data.get('reason')

        if use_manual:
            if not product_name:
                raise forms.ValidationError("Please enter product name.")
            cleaned_data['product'] = None
            cleaned_data['product_name'] = product_name.upper().strip()
        else:
            if not product_id:
                raise forms.ValidationError("Please select a product.")
            cleaned_data['product'] = Product.objects.get(id=product_id)
            cleaned_data['product_name'] = None

        if quantity is None or quantity <= 0:
            raise forms.ValidationError("Quantity must be greater than 0.")

        if not reason:
            raise forms.ValidationError("Please provide a reason for the request.")

        return cleaned_data


class ProcurementRequestForm(forms.ModelForm):
    price = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'w-full rounded-r-lg border border-l-0 px-3 py-2',
        'inputmode': 'numeric',
        'autocomplete': 'off',
        'placeholder': '1.250.000'
    }))

    class Meta:
        model = ProcurementRequest
        fields = ['price', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={
                'class': 'w-full border rounded-lg px-3 py-2',
                'rows': 4,
                'placeholder': 'Add procurement notes'
            }),
        }

    def clean_price(self):
        raw_price = (self.cleaned_data.get('price') or '').strip().replace('Rp', '').replace('rp', '')
        normalized = ''.join(ch for ch in raw_price if ch.isdigit() or ch in '.,')

        if not normalized:
            raise forms.ValidationError("Price must be greater than 0.")

        if ',' in normalized:
            normalized = normalized.replace('.', '').replace(',', '.')
        elif normalized.count('.') == 1 and len(normalized.split('.')[-1]) <= 2:
            normalized = normalized
        else:
            normalized = normalized.replace('.', '')

        try:
            price = Decimal(normalized)
        except InvalidOperation as exc:
            raise forms.ValidationError("Enter a valid IDR amount.") from exc

        if price <= 0:
            raise forms.ValidationError("Price must be greater than 0.")
        return price


class StandaloneProcurementRequestForm(ProcurementRequestForm):
    use_manual_product = forms.BooleanField(
        required=False,
        label="Product not found? Enter manually"
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full border rounded-lg px-3 py-2'
        })
    )
    product_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full border rounded-lg px-3 py-2',
            'placeholder': 'Enter product name manually'
        })
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'w-full border rounded-lg px-3 py-2'
        })
    )

    class Meta(ProcurementRequestForm.Meta):
        fields = ['product', 'product_name', 'quantity', 'price', 'notes']

    def clean(self):
        cleaned_data = super().clean()
        use_manual = cleaned_data.get('use_manual_product')
        product = cleaned_data.get('product')
        product_name = (cleaned_data.get('product_name') or '').strip()

        if use_manual:
            if not product_name:
                raise forms.ValidationError("Please enter a product name.")
            cleaned_data['product'] = None
            cleaned_data['product_name'] = product_name.upper()
        else:
            if not product:
                raise forms.ValidationError("Please select a product.")
            cleaned_data['product_name'] = None

        return cleaned_data


class ProcurementFulfillmentForm(forms.Form):
    product_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full border rounded-lg px-3 py-2',
            'placeholder': 'Enter product name'
        })
    )
    received_quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'w-full border rounded-lg px-3 py-2',
            'placeholder': 'Enter received quantity'
        })
    )

    def __init__(self, *args, procurement_request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.procurement_request = procurement_request

        if procurement_request and procurement_request.product:
            self.fields['product_name'].initial = procurement_request.product.name
            self.fields['product_name'].widget.attrs.update({
                'readonly': 'readonly',
                'class': 'w-full border rounded-lg px-3 py-2 bg-gray-100 text-gray-500'
            })
        elif procurement_request and procurement_request.product_name:
            self.fields['product_name'].initial = procurement_request.product_name

    def clean_product_name(self):
        product_name = (self.cleaned_data.get('product_name') or '').strip()

        if self.procurement_request and self.procurement_request.product:
            return self.procurement_request.product.name

        if not product_name:
            raise forms.ValidationError("Product name is required.")

        product_name = product_name.upper()

        if Product.objects.filter(name__iexact=product_name).exists():
            raise forms.ValidationError("Product with this name already exists.")

        return product_name

    def clean_received_quantity(self):
        received_quantity = self.cleaned_data.get('received_quantity')

        if received_quantity is None or received_quantity <= 0:
            raise forms.ValidationError("Received quantity must be greater than 0.")

        if self.procurement_request and self.procurement_request.inventory_request:
            current_stock = self.procurement_request.product.stock if self.procurement_request.product else 0
            requested_quantity = self.procurement_request.inventory_request.quantity
            if current_stock + received_quantity < requested_quantity:
                raise forms.ValidationError(
                    f"Current stock ({current_stock}) + received quantity ({received_quantity}) "
                    f"must be at least {requested_quantity} to fulfill the request."
                )
        elif self.procurement_request and not self.procurement_request.inventory_request:
            if received_quantity < self.procurement_request.quantity:
                raise forms.ValidationError(
                    f"Received quantity must be at least {self.procurement_request.quantity}."
                )

        return received_quantity
