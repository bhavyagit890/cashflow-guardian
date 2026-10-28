
import json
import logging

import requests
from decouple import config
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core.models import Invoice, WebhookEvent
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from core.models import Client, Invoice, WebhookEvent

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 1. GET PAYPAL ACCESS TOKEN
# --------------------------------------------------

def get_paypal_access_token():
    base_url = config("PAYPAL_BASE_URL").rstrip("/")
    client_id = config("PAYPAL_CLIENT_ID")
    client_secret = config("PAYPAL_CLIENT_SECRET")

    response = requests.post(
        f"{base_url}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    response.raise_for_status()

    return response.json()["access_token"]


def fetch_paypal_invoice(paypal_invoice_id):
    """
    Fetch invoice details from the configured PayPal environment.
    Does not create or modify local database records.
    """
    if not paypal_invoice_id:
        raise ValueError("PayPal invoice ID is required.")

    access_token = get_paypal_access_token()
    base_url = config("PAYPAL_BASE_URL").rstrip("/")

    response = requests.get(
        f"{base_url}/v2/invoicing/invoices/{paypal_invoice_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    response.raise_for_status()

    invoice_data = response.json()

    if invoice_data.get("id") != paypal_invoice_id:
        raise ValueError(
            "PayPal returned an invoice with an unexpected ID."
        )

    return invoice_data


def sync_paypal_invoice(paypal_invoice_id):
    """
    Fetch a PayPal invoice and create or update its local record.

    The invoice is saved only when its recipient matches an existing
    local client. Missing due dates remain None.
    """
    data = fetch_paypal_invoice(paypal_invoice_id)

    detail = data.get("detail") or {}
    amount_data = data.get("amount") or {}
    metadata = detail.get("metadata") or {}

    returned_id = data.get("id")
    if not returned_id or returned_id != paypal_invoice_id:
        raise ValueError("PayPal returned an unexpected invoice ID.")

    recipient_list = data.get("primary_recipients") or []
    recipient_email = None

    if recipient_list:
        billing_info = recipient_list[0].get("billing_info") or {}
        recipient_email = billing_info.get("email_address")

    if not recipient_email:
        raise ValueError(
            f"PayPal invoice {paypal_invoice_id} has no recipient email."
        )

    try:
        client = Client.objects.get(email__iexact=recipient_email)
    except Client.DoesNotExist as exc:
        raise ValueError(
            f"No local client matches recipient {recipient_email}. "
            "Create or reconcile the client before syncing this invoice."
        ) from exc

    try:
        amount = Decimal(str(amount_data["value"]))
        currency = amount_data["currency_code"]
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError(
            f"PayPal invoice {paypal_invoice_id} has invalid amount data."
        ) from exc

    invoice_date_value = detail.get("invoice_date")
    if not invoice_date_value:
        raise ValueError(
            f"PayPal invoice {paypal_invoice_id} has no invoice date."
        )

    issued_date = date.fromisoformat(invoice_date_value)
    issued_at = timezone.make_aware(
        timezone.datetime.combine(
            issued_date,
            timezone.datetime.min.time(),
        )
    )

    payment_term = detail.get("payment_term") or {}
    due_date = None

    # Only assign a due date if PayPal actually provides one.
    # NO_DUE_DATE must not be converted into an invented deadline.
    if payment_term.get("term_type") != "NO_DUE_DATE":
        due_date_value = detail.get("due_date")
        if due_date_value:
            due_date = date.fromisoformat(due_date_value)

    status_mapping = {
        "DRAFT": Invoice.Status.DRAFT,
        "SENT": Invoice.Status.SENT,
        "PARTIALLY_PAID": Invoice.Status.PARTIALLY_PAID,
        "PAID": Invoice.Status.PAID,
        "CANCELLED": Invoice.Status.CANCELLED,
    }

    paypal_status = data.get("status")
    local_status = status_mapping.get(paypal_status)

    if local_status is None:
        raise ValueError(
            f"Unsupported PayPal invoice status: {paypal_status!r}"
        )

    payment_link = metadata.get("recipient_view_url") or ""

    invoice, created = Invoice.objects.update_or_create(
        paypal_invoice_id=returned_id,
        defaults={
            "client": client,
            "amount": amount,
            "currency": currency,
            "issued_at": issued_at,
            "due_date": due_date,
            "status": local_status,
            "payment_link": payment_link,
            "last_synced_at": timezone.now(),
        },
    )

    logger.info(
        "%s local invoice %s from PayPal.",
        "Created" if created else "Updated",
        returned_id,
    )

    return invoice

# --------------------------------------------------
# 2. VERIFY PAYPAL WEBHOOK SIGNATURE
# --------------------------------------------------

def verify_paypal_webhook(request, event):
    access_token = get_paypal_access_token()
    base_url = config("PAYPAL_BASE_URL").rstrip("/")
    webhook_id = config("PAYPAL_WEBHOOK_ID")

    verification_data = {
        "transmission_id": request.headers.get(
            "PAYPAL-TRANSMISSION-ID"
        ),
        "transmission_time": request.headers.get(
            "PAYPAL-TRANSMISSION-TIME"
        ),
        "transmission_sig": request.headers.get(
            "PAYPAL-TRANSMISSION-SIG"
        ),
        "cert_url": request.headers.get("PAYPAL-CERT-URL"),
        "auth_algo": request.headers.get("PAYPAL-AUTH-ALGO"),
        "webhook_id": webhook_id,
        "webhook_event": event,
    }

    response = requests.post(
        f"{base_url}/v1/notifications/verify-webhook-signature",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=verification_data,
        timeout=15,
    )
    response.raise_for_status()

    result = response.json()
    return result.get("verification_status") == "SUCCESS"


# --------------------------------------------------
# 3. PROCESS ONE PAYPAL INVOICE EVENT
# --------------------------------------------------


def process_invoice_event(event_type, event):
    resource = event.get("resource", {})

    if not isinstance(resource, dict):
        return False

    # PayPal invoice events may nest the invoice inside resource.invoice.
    invoice_resource = resource.get("invoice", resource)

    if not isinstance(invoice_resource, dict):
        return False

    paypal_invoice_id = invoice_resource.get("id")

    if not paypal_invoice_id:
        logger.warning(
            "PayPal event %s has no invoice ID.",
            event_type,
        )
        return False

    status_mapping = {
        "INVOICING.INVOICE.CREATED": Invoice.Status.DRAFT,
        "INVOICING.INVOICE.SENT": Invoice.Status.SENT,
        "INVOICING.INVOICE.PAID": Invoice.Status.PAID,
        "INVOICING.INVOICE.CANCELLED": Invoice.Status.CANCELLED,
    }

    new_status = status_mapping.get(event_type)

    if new_status is None:
        logger.info(
            "Unsupported PayPal invoice event type: %s",
            event_type,
        )
        return False

    try:
        invoice = Invoice.objects.get(
            paypal_invoice_id=paypal_invoice_id
        )
    except Invoice.DoesNotExist:
        logger.warning(
            "No local invoice found for PayPal ID: %s",
            paypal_invoice_id,
        )
        return False

    # Don't downgrade invoices already in a terminal state.
    if invoice.status in [
        Invoice.Status.PAID,
        Invoice.Status.CANCELLED,
    ]:
        return True

    invoice.status = new_status
    invoice.save(update_fields=["status"])

    return True



# --------------------------------------------------
# 4. RETRY SAVED PENDING WEBHOOK EVENTS
# --------------------------------------------------

def retry_pending_webhook_events(limit=100):
    """
    Retry saved webhook events that have not been processed.

    This function processes only events already stored after
    webhook verification. It does not bypass signature verification
    for incoming events.

    Returns counts of successfully processed and still-pending events.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    pending_events = (
        WebhookEvent.objects.filter(processed=False)
        .order_by("received_at")[:limit]
    )

    processed_count = 0
    pending_count = 0
    error_count = 0

    for saved_event in pending_events:
        try:
            with transaction.atomic():
                # Lock and reload the record to avoid concurrent retries.
                webhook_event = (
                    WebhookEvent.objects.select_for_update()
                    .get(pk=saved_event.pk)
                )

                if webhook_event.processed:
                    continue

                processed = process_invoice_event(
                    webhook_event.event_type,
                    webhook_event.payload,
                )

                if processed:
                    webhook_event.processed = True
                    webhook_event.save(update_fields=["processed"])
                    processed_count += 1
                else:
                    pending_count += 1

        except Exception:
            error_count += 1
            logger.exception(
                "Failed to retry PayPal webhook event %s",
                saved_event.paypal_event_id,
            )

    logger.info(
        "Webhook retry finished: processed=%s pending=%s errors=%s",
        processed_count,
        pending_count,
        error_count,
    )

    return {
        "processed": processed_count,
        "pending": pending_count,
        "errors": error_count,
    }


# --------------------------------------------------
# 5. RECEIVE PAYPAL WEBHOOKS
# --------------------------------------------------

@csrf_exempt
def paypal_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed"},
            status=405,
        )

    try:
        event = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400,
        )

    if not isinstance(event, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )

    required_headers = [
        "PAYPAL-TRANSMISSION-ID",
        "PAYPAL-TRANSMISSION-TIME",
        "PAYPAL-TRANSMISSION-SIG",
        "PAYPAL-CERT-URL",
        "PAYPAL-AUTH-ALGO",
    ]

    missing_headers = [
        header
        for header in required_headers
        if not request.headers.get(header)
    ]

    if missing_headers:
        return JsonResponse(
            {"error": "Missing required PayPal headers"},
            status=400,
        )

    try:
        is_verified = verify_paypal_webhook(request, event)
    except (
        requests.RequestException,
        KeyError,
        ValueError,
    ):
        logger.exception("PayPal webhook verification failed.")
        return JsonResponse(
            {"error": "Webhook verification failed"},
            status=502,
        )

    if not is_verified:
        return JsonResponse(
            {"error": "Invalid webhook signature"},
            status=401,
        )

    event_id = event.get("id")
    event_type = event.get("event_type")

    if not isinstance(event_id, str) or not event_id.strip():
        return JsonResponse(
            {"error": "Missing or invalid event ID"},
            status=400,
        )

    if not isinstance(event_type, str) or not event_type.strip():
        return JsonResponse(
            {"error": "Missing or invalid event type"},
            status=400,
        )

    try:
        with transaction.atomic():
            webhook_event, created = WebhookEvent.objects.get_or_create(
                paypal_event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "payload": event,
                },
            )
    except IntegrityError:
        logger.info("PayPal event %s was already received.", event_id)
        return JsonResponse({"status": "already received"})

    if not created and webhook_event.processed:
        return JsonResponse({"status": "duplicate ignored"})

    # Always process the saved payload, including for pending retries.
    event_type = webhook_event.event_type
    event = webhook_event.payload

    try:
        with transaction.atomic():
            webhook_event = (
                WebhookEvent.objects.select_for_update()
                .get(pk=webhook_event.pk)
            )

            if webhook_event.processed:
                return JsonResponse({"status": "duplicate ignored"})

            processed = process_invoice_event(
                webhook_event.event_type,
                webhook_event.payload,
            )

            if processed:
                webhook_event.processed = True
                webhook_event.save(update_fields=["processed"])

    except Exception:
        logger.exception(
            "PayPal invoice processing failed for event %s",
            event_id,
        )
        return JsonResponse(
            {"error": "Event processing failed"},
            status=500,
        )

    if not processed:
        logger.warning(
            "Event saved but not processed: %s",
            event_type,
        )
        return JsonResponse({
            "status": "saved_pending_processing"
        })

    return JsonResponse({"status": "processed"})
