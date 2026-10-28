"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from core.views import agent_action_list, health_check, invoice_list, payment_plan_list, reminder_list

from core.webhooks import paypal_webhook
from core.views import approve_reminder, reject_reminder,client_list,expense_list, cash_flow_snapshot_list
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/clients/', client_list, name='client_list'),
    path("api/invoices/", invoice_list, name="invoice_list"),
    path("api/reminders/", reminder_list, name="reminder_list"),
    path(
    "api/payment-plans/",
    payment_plan_list,
    name="payment_plan_list",
),
path(
    "api/agent-actions/",
    agent_action_list,
    name="agent_action_list",
),
path(
    "api/webhooks/paypal/",
    paypal_webhook,
    name="paypal_webhook",
),
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
]