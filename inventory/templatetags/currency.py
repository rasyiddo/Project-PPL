from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def duration_human(td):
    """Format a timedelta as a human-readable string like '2d 3h 15m'."""
    if td is None:
        return ''
    total_seconds = int(abs(td.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return ' '.join(parts)


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
