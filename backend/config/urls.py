
from django.conf import settings
from django.http import Http404, HttpResponse
from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

from core.views import (
    agent_action_list,
    health_check,
    invoice_list,
    payment_plan_list,
    reminder_list,
    approve_reminder,
    reject_reminder,
    client_list,
    expense_list,
    cash_flow_snapshot_list,
  
)

from core.webhooks import paypal_webhook


def frontend_app(request):
    index_file = settings.FRONTEND_DIST_DIR / "index.html"

    if not index_file.is_file():
        raise Http404("Frontend build not found. Run npm run build.")

    return HttpResponse(
        index_file.read_text(encoding="utf-8"),
        content_type="text/html",
    )


urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/health/", health_check, name="health_check"),
    path("api/clients/", client_list, name="client_list"),
    path("api/invoices/", invoice_list, name="invoice_list"),
    path("api/reminders/", reminder_list, name="reminder_list"),
    path("api/payment-plans/", payment_plan_list, name="payment_plan_list"),
    path("api/agent-actions/", agent_action_list, name="agent_action_list"),
    path("api/webhooks/paypal/", paypal_webhook, name="paypal_webhook"),
    path("api/auth/login/", obtain_auth_token, name="api_login"),

    path(
        "api/reminders/<int:reminder_id>/approve/",
        approve_reminder,
        name="approve_reminder",
    ),
    path(
        "api/reminders/<int:reminder_id>/reject/",
        reject_reminder,
        name="reject_reminder",
    ),

    path("api/expenses/", expense_list, name="expense_list"),
    path(
        "api/cash-flow-snapshots/",
        cash_flow_snapshot_list,
        name="cash_flow_snapshot_list",
    ),

    path("api-auth/", include("rest_framework.urls")),

    # Keep the frontend route last.
    path("", frontend_app, name="frontend"),
]
