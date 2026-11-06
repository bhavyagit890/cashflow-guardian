
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from .models import (
    AgentAction,
    Client,
    Invoice,
    PaymentPlan,
    ReminderLog,
    Expense,
    CashFlowSnapshot,
)

from .serializers import (
    AgentActionSerializer,
    ClientSerializer,
    InvoiceSerializer,
    PaymentPlanSerializer,
    ReminderLogSerializer,
    ExpenseSerializer,
    CashFlowSnapshotSerializer,
)


def health_check(request):
    return JsonResponse({"status": "ok"})


@api_view(["GET"])
def client_list(request):
    clients = Client.objects.filter(
        business=request.user.business
    )
    serializer = ClientSerializer(clients, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def invoice_list(request):
    invoices = Invoice.objects.select_related("client").filter(
        client__business=request.user.business
    )
    serializer = InvoiceSerializer(invoices, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def reminder_list(request):
    reminders = ReminderLog.objects.select_related("invoice").filter(
        invoice__client__business=request.user.business
    )
    serializer = ReminderLogSerializer(reminders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def payment_plan_list(request):
    plans = PaymentPlan.objects.select_related("invoice").filter(
        invoice__client__business=request.user.business
    )
    serializer = PaymentPlanSerializer(plans, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def agent_action_list(request):
    actions = AgentAction.objects.select_related("invoice").filter(
        invoice__client__business=request.user.business
    )
    serializer = AgentActionSerializer(actions, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_reminder(request, reminder_id):
    reminder = get_object_or_404(
        ReminderLog.objects.filter(
            invoice__client__business=request.user.business
        ),
        pk=reminder_id,
    )

    if reminder.status != ReminderLog.Status.PENDING_APPROVAL:
        return Response(
            {"error": "Only pending reminders can be approved."},
            status=status.HTTP_409_CONFLICT,
        )

    if reminder.invoice.status in [
        Invoice.Status.PAID,
        Invoice.Status.CANCELLED,
    ]:
        return Response(
            {
                "error": "Cannot approve a reminder for a paid or cancelled invoice."
            },
            status=status.HTTP_409_CONFLICT,
        )

    reminder.status = ReminderLog.Status.APPROVED
    reminder.save(update_fields=["status"])

    return Response({
        "message": "Reminder approved. No message was sent.",
        "reminder_id": reminder.id,
        "status": reminder.status,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_reminder(request, reminder_id):
    reminder = get_object_or_404(
        ReminderLog.objects.filter(
            invoice__client__business=request.user.business
        ),
        pk=reminder_id,
    )

    if reminder.status != ReminderLog.Status.PENDING_APPROVAL:
        return Response(
            {"error": "Only pending reminders can be rejected."},
            status=status.HTTP_409_CONFLICT,
        )

    reminder.status = ReminderLog.Status.REJECTED
    reminder.save(update_fields=["status"])

    return Response({
        "message": "Reminder rejected. No message was sent.",
        "reminder_id": reminder.id,
        "status": reminder.status,
    })


@api_view(["GET"])
def expense_list(request):
    expenses = Expense.objects.filter(
        business=request.user.business
    ).order_by("due_date")
    serializer = ExpenseSerializer(expenses, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def cash_flow_snapshot_list(request):
    snapshots = CashFlowSnapshot.objects.filter(
        business=request.user.business
    ).order_by("-date", "-id")

    serializer = CashFlowSnapshotSerializer(snapshots, many=True)
    return Response(serializer.data)


    process_overdue_invoice(invoice)

    reminder = (
        ReminderLog.objects.filter(invoice=invoice)
        .order_by("-id")
        .first()
    )

    if reminder is None:
        return Response(
            {"error": "Agent finished, but no reminder draft was created."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "message": "Reminder draft created successfully.",
        "invoice_id": invoice.paypal_invoice_id,
        "reminder_id": reminder.id,
        "reminder_status": reminder.status,
        "draft_created": True,
    })