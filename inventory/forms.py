from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Product


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
