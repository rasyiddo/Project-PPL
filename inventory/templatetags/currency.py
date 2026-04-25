from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def idr_currency(value):
    if value in (None, ''):
        return '-'

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    amount = amount.quantize(Decimal('1'))
    formatted = f"{int(amount):,}".replace(',', '.')
    return f"Rp {formatted}"
