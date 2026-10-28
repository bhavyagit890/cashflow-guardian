from django.contrib import admin
from .models import (
    Client,
    Invoice,
    ReminderLog,
    PaymentPlan,
    AgentAction,
    WebhookEvent,
    CashFlowSnapshot,
)

admin.site.register(Client)
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "paypal_invoice_id",
        "client",
        "amount",
        "currency",
        "due_date",
        "status",
        "is_overdue",
    )
admin.site.register(ReminderLog)
admin.site.register(PaymentPlan)
admin.site.register(AgentAction)
admin.site.register(WebhookEvent)
admin.site.register(CashFlowSnapshot)