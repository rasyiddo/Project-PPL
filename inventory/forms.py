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
        if not stock:
            raise forms.ValidationError("Stock field is required.")
        if stock <= 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock


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
