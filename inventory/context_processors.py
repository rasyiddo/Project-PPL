from .models import InventoryRequest, ProcurementRequest


def sidebar_counts(request):
    if not request.user.is_authenticated:
        return {}

    ctx = {}

    if request.user.has_perm('inventory.approve_inventoryrequest'):
        ctx['sidebar_ir_pending'] = (
            InventoryRequest.objects
            .exclude(created_by=request.user)
            .filter(status='PENDING')
            .count()
        )

    if request.user.has_perm('inventory.approve_procurementrequest'):
        ctx['sidebar_pr_pending'] = (
            ProcurementRequest.objects
            .filter(status='PENDING')
            .count()
        )

    if request.user.has_perm('inventory.add_inventorytransaction'):
        ctx['sidebar_fulfillment_pending'] = (
            InventoryRequest.objects
            .filter(status='APPROVED')
            .exclude(procurementrequest__status__in=['PENDING', 'APPROVED', 'ORDERED', 'FULFILLED'])
            .count()
        )

    return ctx
