
import logging
from datetime import timedelta
from decimal import Decimal

from decouple import config
from django.db.models import Sum
from django.utils import timezone
from google import genai

from core.models import (
    AgentAction,
    CashFlowSnapshot,
    Expense,
    Invoice,
    ReminderLog,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. FIND OVERDUE INVOICES
# --------------------------------------------------

def find_overdue_invoices():
    """
    Return invoices whose due dates have passed and whose
    statuses are SENT or PARTIALLY_PAID.
    """
    return list(
        Invoice.objects.select_related("client")
        .filter(
            status__in=[
                Invoice.Status.SENT,
                Invoice.Status.PARTIALLY_PAID,
            ],
            due_date__isnull=False,
            due_date__lt=timezone.localdate(),
        )
    )


# --------------------------------------------------
# 2. ASSESS INVOICE RISK
# --------------------------------------------------


def assess_invoice_risk(invoice):
    """
    Apply illustrative demo rules to classify invoice risk.
    These thresholds are not validated financial predictions.

    Only SENT and PARTIALLY_PAID invoices are assessed as
    active payment risks.
    """
    if invoice.status not in [
        Invoice.Status.SENT,
        Invoice.Status.PARTIALLY_PAID,
    ]:
        return Invoice.RiskLevel.LOW

    if invoice.due_date is None:
        return Invoice.RiskLevel.LOW

    today = timezone.localdate()
    days_overdue = (today - invoice.due_date).days

    if (
        days_overdue >= 30
        or invoice.client.reliability_score < 30
        or invoice.amount >= Decimal("10000")
    ):
        return Invoice.RiskLevel.HIGH

    if (
        days_overdue >= 7
        or invoice.client.reliability_score < 60
        or invoice.amount >= Decimal("1000")
    ):
        return Invoice.RiskLevel.MEDIUM

    return Invoice.RiskLevel.LOW


# --------------------------------------------------
# 3. RECORD RISK ASSESSMENT
# --------------------------------------------------

def record_risk_action(invoice, risk_level):
    """
    Update an existing unreviewed risk action where possible,
    rather than creating duplicate actions.
    """
    existing_action = (
        AgentAction.objects.filter(
            invoice=invoice,
            tool_name="assess_invoice_risk",
            approved__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )

    tool_output = {
        "risk_level": risk_level,
        "is_overdue": invoice.is_overdue,
    }

    if invoice.due_date is None:
        reasoning = (
            f"Invoice {invoice.paypal_invoice_id} has no due date. "
            "It cannot be classified as overdue."
        )
    else:
        reasoning = (
            f"Invoice {invoice.paypal_invoice_id} is overdue. "
            f"The current demo rules classify its risk as {risk_level}."
        )

    if existing_action:
        existing_action.tool_output = tool_output
        existing_action.reasoning = reasoning
        existing_action.save(
            update_fields=["tool_output", "reasoning"]
        )
        return existing_action

    return AgentAction.objects.create(
        invoice=invoice,
        trigger=AgentAction.Trigger.MANUAL,
        tool_name="assess_invoice_risk",
        tool_input={
            "invoice_id": invoice.paypal_invoice_id,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
        },
        tool_output=tool_output,
        reasoning=reasoning,
        requires_approval=True,
        approved=None,
    )


# --------------------------------------------------
# 4. GENERATE A GEMINI REMINDER DRAFT
# --------------------------------------------------

def generate_reminder_draft(invoice):
    """
    Generate an email draft with Gemini.
    This function does not send any messages.
    """
    if invoice.due_date is None:
        raise ValueError(
            f"Invoice {invoice.paypal_invoice_id} has no due date; "
            "cannot generate an overdue reminder."
        )

    api_key = config("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    today = timezone.localdate()
    days_overdue = (today - invoice.due_date).days

    prompt = f"""
You are a professional accounts receivable assistant helping a
freelancer or small business collect overdue payments.

Write a polite, professional, concise email reminder.

Invoice details:
- Client name: {invoice.client.name}
- Invoice ID: {invoice.paypal_invoice_id}
- Amount due: {invoice.amount} {invoice.currency}
- Due date: {invoice.due_date}
- Days overdue: {days_overdue}

Instructions:
- Greet the client by name.
- Mention the invoice ID and outstanding amount.
- Mention the due date naturally.
- Politely ask the client to confirm their expected payment date.
- Be respectful and understanding.
- Do not invent payment links, bank details, penalties, agreements,
  or other facts that were not provided.
- Do not claim the invoice has been paid.
- Do not invent a sender name, company name, job title, or signature.
- End with a simple closing such as "Thank you for your time."
- Put an email subject on the first line beginning with "Subject:"
- Put the email body on the following lines.
- Return only the subject and body, without markdown fences.

Do not include placeholder text such as [Your Name],
[Your Company], [Your Name/Company Name], or generic
signatures such as "Accounts Receivable".
Do not invent the sender's name, company, or signature.
End the reminder politely without a signature if sender
details are not available.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    draft_text = response.text

    if not draft_text or not draft_text.strip():
        raise ValueError("Gemini returned an empty reminder draft.")

    return draft_text.strip()


import re


def contains_placeholder(text):
    """Return True if reminder text contains unresolved placeholders."""
    patterns = [
        r"\[[^\]]+\]",
        r"\bYour Name/Company Name\b",
        r"\bYour Name\b",
        r"\bYour Company\b",
        r"\bAccounts Receivable\b",
    ]

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in patterns
    )

# --------------------------------------------------
# 5. SAVE A REMINDER FOR OWNER REVIEW
# --------------------------------------------------

def save_reminder_draft(invoice, draft_text):
    if contains_placeholder(draft_text):
        raise ValueError(
            "Reminder draft contains unresolved placeholders. "
            "Please review or regenerate it before saving."
        )
    """
    Save a reminder as PENDING_APPROVAL.
    Never sends an email or PayPal reminder.
    """
    if not draft_text or not draft_text.strip():
        raise ValueError("Reminder draft cannot be empty.")

    if invoice.due_date is None:
        raise ValueError(
            f"Invoice {invoice.paypal_invoice_id} has no due date; "
            "cannot save an overdue reminder."
        )

    lines = draft_text.strip().splitlines()

    subject_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower().startswith("subject:")
        ),
        None,
    )

    if subject_index is not None:
        subject = (
            lines[subject_index].strip().split(":", 1)[1].strip()
        )
        body = "\n".join(lines[subject_index + 1:]).strip()

        if not subject:
            raise ValueError("Gemini returned an empty email subject.")

        if not body:
            raise ValueError("Gemini returned an empty reminder body.")
    else:
        subject = (
            f"Payment reminder: Invoice {invoice.paypal_invoice_id}"
        )
        body = draft_text.strip()

    existing = (
        ReminderLog.objects.filter(
            invoice=invoice,
            status=ReminderLog.Status.PENDING_APPROVAL,
        )
        .order_by("-created_at")
        .first()
    )

    if existing:
        existing.subject = subject[:255]
        existing.body = body
        existing.save(update_fields=["subject", "body"])
        return existing

    return ReminderLog.objects.create(
        invoice=invoice,
        tone=ReminderLog.Tone.FRIENDLY,
        subject=subject[:255],
        body=body,
        status=ReminderLog.Status.PENDING_APPROVAL,
    )


# --------------------------------------------------
# 6. PROCESS ONE OVERDUE INVOICE
# --------------------------------------------------

def process_overdue_invoice(invoice):
    """
    Assess an overdue invoice and prepare a reminder draft
    only when appropriate.

    No customer-facing message is sent.
    """
    if not invoice.is_overdue:
        raise ValueError(
            f"Invoice {invoice.paypal_invoice_id} is not overdue."
        )

    risk_level = assess_invoice_risk(invoice)
    action = record_risk_action(invoice, risk_level)

    # Do not create a new reminder if any reminder already exists.
    existing_reminder = (
        ReminderLog.objects.filter(invoice=invoice)
        .order_by("-created_at")
        .first()
    )

    if existing_reminder:
        reminder = existing_reminder
        draft_created = False
    else:
        draft_text = generate_reminder_draft(invoice)
        reminder = save_reminder_draft(invoice, draft_text)
        draft_created = True

    return {
        "invoice_id": invoice.paypal_invoice_id,
        "risk_level": risk_level,
        "action_id": action.id,
        "reminder_id": reminder.id,
        "reminder_status": reminder.status,
        "draft_created": draft_created,
    }


# --------------------------------------------------
# 7. PROCESS ALL OVERDUE INVOICES
# --------------------------------------------------

def run_agent_cycle():
    """
    Process overdue invoices independently.
    A failure on one invoice does not stop the others.
    """
    results = []

    for invoice in find_overdue_invoices():
        try:
            results.append({
                "success": True,
                **process_overdue_invoice(invoice),
            })
        except Exception as error:
            logger.exception(
                "Failed to process overdue invoice %s",
                invoice.paypal_invoice_id,
            )

            results.append({
                "success": False,
                "invoice_id": invoice.paypal_invoice_id,
                "error": str(error),
            })

    return results


# --------------------------------------------------
# 8. GENERATE A CASH-FLOW SNAPSHOT
# --------------------------------------------------

def generate_cash_flow_snapshot(days_ahead=30):
    """
    Create a cash-flow snapshot for the next N days.

    Inflow:
        Full amounts of SENT and PARTIALLY_PAID invoices with
        a due date on or before the forecast end date.

    Obligations:
        Unpaid expenses due between today and the forecast end.

    Limitations:
        - Partial payments are not deducted because the model
          does not track the amount already paid.
        - Overdue expenses are excluded from this initial forecast.
        - Totals are meaningful only when records use a consistent
          currency. This version does not perform currency conversion.
        - Forecasts are estimates, not guarantees.
    """
    if days_ahead < 0:
        raise ValueError("days_ahead cannot be negative.")

    today = timezone.localdate()
    forecast_end = today + timedelta(days=days_ahead)

    expected_inflow = (
        Invoice.objects.filter(
            status__in=[
                Invoice.Status.SENT,
                Invoice.Status.PARTIALLY_PAID,
            ],
            due_date__isnull=False,
            due_date__lte=forecast_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    upcoming_obligations = (
        Expense.objects.filter(
            is_paid=False,
            due_date__gte=today,
            due_date__lte=forecast_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    # Positive = projected shortfall.
    # Negative = projected surplus.
    projected_gap = upcoming_obligations - expected_inflow

    return CashFlowSnapshot.objects.create(
        date=today,
        expected_inflow=expected_inflow,
        upcoming_obligations=upcoming_obligations,
        projected_gap=projected_gap,
    )
