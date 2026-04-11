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