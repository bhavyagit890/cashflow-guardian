import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone

from core.agent.loop import (
    assess_invoice_risk,
    record_risk_action,
    process_overdue_invoice,
    run_agent_cycle,
    generate_cash_flow_snapshot,
    save_reminder_draft,
)
from core.models import (
    AgentAction,
    Client,
    Invoice,
    ReminderLog,
    WebhookEvent,
    Expense,
    CashFlowSnapshot,
)
from core.webhooks import (
    process_invoice_event,
    sync_paypal_invoice,
)


class PayPalWebhookBasicTests(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.url = "/api/webhooks/paypal/"

    def test_get_request_is_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_invalid_json_is_rejected(self):
        response = self.client.post(
            self.url,
            data="{invalid json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_json_array_is_rejected(self):
        response = self.client.post(
            self.url,
            data=json.dumps([]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_paypal_headers_is_rejected(self):
        response = self.client.post(
            self.url,
            data=json.dumps({
                "id": "TEST-EVENT-001",
                "event_type": "INVOICING.INVOICE.CREATED",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class InvoiceEventProcessingTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            name="Test Client",
            email="client@example.com",
        )
        self.invoice = Invoice.objects.create(
            paypal_invoice_id="TEST-INVOICE-001",
            client=self.client_record,
            amount=Decimal("100.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 11, 1),
            status=Invoice.Status.DRAFT,
        )

    def test_sent_event_updates_invoice_status(self):
        event = {"resource": {"id": "TEST-INVOICE-001"}}

        result = process_invoice_event(
            "INVOICING.INVOICE.SENT",
            event,
        )
        self.invoice.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.invoice.status, Invoice.Status.SENT)

    def test_paid_event_updates_invoice_status(self):
        event = {"resource": {"id": "TEST-INVOICE-001"}}

        result = process_invoice_event(
            "INVOICING.INVOICE.PAID",
            event,
        )
        self.invoice.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_unknown_invoice_id_is_not_processed(self):
        event = {"resource": {"id": "UNKNOWN-INVOICE"}}

        result = process_invoice_event(
            "INVOICING.INVOICE.PAID",
            event,
        )
        self.invoice.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.invoice.status, Invoice.Status.DRAFT)

    def test_created_event_does_not_downgrade_paid_invoice(self):
        self.invoice.status = Invoice.Status.PAID
        self.invoice.save(update_fields=["status"])

        event = {"resource": {"id": "TEST-INVOICE-001"}}

        result = process_invoice_event(
            "INVOICING.INVOICE.CREATED",
            event,
        )
        self.invoice.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)


class WebhookEventIdempotencyTests(TestCase):
    def test_duplicate_event_id_is_not_saved_twice(self):
        event_id = "TEST-EVENT-DUPLICATE-001"

        first_event, created_first = WebhookEvent.objects.get_or_create(
            paypal_event_id=event_id,
            defaults={
                "event_type": "INVOICING.INVOICE.CREATED",
                "payload": {
                    "id": event_id,
                    "event_type": "INVOICING.INVOICE.CREATED",
                },
            },
        )

        second_event, created_second = WebhookEvent.objects.get_or_create(
            paypal_event_id=event_id,
            defaults={
                "event_type": "INVOICING.INVOICE.PAID",
                "payload": {
                    "id": event_id,
                    "event_type": "INVOICING.INVOICE.PAID",
                },
            },
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first_event.pk, second_event.pk)
        self.assertEqual(
            WebhookEvent.objects.filter(
                paypal_event_id=event_id
            ).count(),
            1,
        )


class PayPalWebhookEndpointTests(TestCase):
    @patch("core.webhooks.verify_paypal_webhook", return_value=True)
    def test_verified_event_is_saved_and_returns_received(self, mock_verify):
        event = {
            "id": "TEST-ENDPOINT-EVENT-001",
            "event_type": "INVOICING.INVOICE.CREATED",
            "resource": {"id": "UNKNOWN-INVOICE-ENDPOINT-001"},
        }

        headers = {
            "HTTP_PAYPAL_TRANSMISSION_ID": "test-transmission-id",
            "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-10-20T10:00:00Z",
            "HTTP_PAYPAL_TRANSMISSION_SIG": "test-signature",
            "HTTP_PAYPAL_CERT_URL": "https://example.com/cert",
            "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
        }

        response = self.client.post(
            "/api/webhooks/paypal/",
            data=json.dumps(event),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "saved_pending_processing",
        )
        self.assertTrue(
            WebhookEvent.objects.filter(
                paypal_event_id=event["id"],
                event_type=event["event_type"],
                processed=False,
            ).exists()
        )
        mock_verify.assert_called_once()

    @patch("core.webhooks.verify_paypal_webhook", return_value=False)
    def test_invalid_signature_is_rejected(self, mock_verify):
        event = {
            "id": "TEST-INVALID-SIGNATURE-001",
            "event_type": "INVOICING.INVOICE.CREATED",
            "resource": {"id": "UNKNOWN-INVOICE-001"},
        }

        headers = {
            "HTTP_PAYPAL_TRANSMISSION_ID": "test-transmission-id",
            "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-10-20T10:00:00Z",
            "HTTP_PAYPAL_TRANSMISSION_SIG": "invalid-signature",
            "HTTP_PAYPAL_CERT_URL": "https://example.com/cert",
            "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
        }

        response = self.client.post(
            "/api/webhooks/paypal/",
            data=json.dumps(event),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            WebhookEvent.objects.filter(
                paypal_event_id=event["id"]
            ).exists()
        )
        mock_verify.assert_called_once()

    @patch(
        "core.webhooks.verify_paypal_webhook",
        side_effect=__import__(
            "requests"
        ).RequestException("PayPal verification unavailable"),
    )
    def test_verification_service_failure_is_rejected(
        self,
        mock_verify,
    ):
        event = {
            "id": "TEST-VERIFICATION-ERROR-001",
            "event_type": "INVOICING.INVOICE.CREATED",
            "resource": {"id": "UNKNOWN-INVOICE-002"},
        }

        headers = {
            "HTTP_PAYPAL_TRANSMISSION_ID": "test-transmission-id",
            "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-10-20T10:00:00Z",
            "HTTP_PAYPAL_TRANSMISSION_SIG": "test-signature",
            "HTTP_PAYPAL_CERT_URL": "https://example.com/cert",
            "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
        }

        response = self.client.post(
            "/api/webhooks/paypal/",
            data=json.dumps(event),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(
            WebhookEvent.objects.filter(
                paypal_event_id=event["id"]
            ).exists()
        )
        mock_verify.assert_called_once()
class WebhookRetryTests(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.url = "/api/webhooks/paypal/"
        self.event = {
            "id": "TEST-RETRY-EVENT-001",
            "event_type": "INVOICING.INVOICE.CREATED",
            "resource": {"id": "UNKNOWN-INVOICE-RETRY-001"},
        }
        self.headers = {
            "HTTP_PAYPAL_TRANSMISSION_ID": "retry-transmission",
            "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-10-20T10:00:00Z",
            "HTTP_PAYPAL_TRANSMISSION_SIG": "test-signature",
            "HTTP_PAYPAL_CERT_URL": "https://example.com/cert",
            "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
        }

    @patch("core.webhooks.verify_paypal_webhook", return_value=True)
    def test_pending_duplicate_is_retried(self, mock_verify):
        WebhookEvent.objects.create(
            paypal_event_id=self.event["id"],
            event_type=self.event["event_type"],
            payload=self.event,
            processed=False,
        )

        response = self.client.post(
            self.url,
            data=json.dumps(self.event),
            content_type="application/json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "saved_pending_processing",
        )
        self.assertEqual(
            WebhookEvent.objects.filter(
                paypal_event_id=self.event["id"]
            ).count(),
            1,
        )
        mock_verify.assert_called_once()

    @patch("core.webhooks.verify_paypal_webhook", return_value=True)
    def test_processed_duplicate_is_ignored(self, mock_verify):
        WebhookEvent.objects.create(
            paypal_event_id=self.event["id"],
            event_type=self.event["event_type"],
            payload=self.event,
            processed=True,
        )

        response = self.client.post(
            self.url,
            data=json.dumps(self.event),
            content_type="application/json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "duplicate ignored",
        )
        self.assertEqual(
            WebhookEvent.objects.filter(
                paypal_event_id=self.event["id"]
            ).count(),
            1,
        )
        mock_verify.assert_called_once()


class AgentRiskActionTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            name="Agent Test Client",
            email="agent-test@example.com",
            reliability_score=50,
        )
        self.invoice = Invoice.objects.create(
            paypal_invoice_id="AGENT-TEST-INVOICE-001",
            client=self.client_record,
            amount=Decimal("500.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 10, 1),
            status=Invoice.Status.SENT,
        )

    def test_duplicate_pending_assessment_reuses_action(self):
        risk = assess_invoice_risk(self.invoice)

        first_action = record_risk_action(self.invoice, risk)
        second_action = record_risk_action(self.invoice, risk)

        self.assertEqual(first_action.pk, second_action.pk)
        self.assertEqual(
            AgentAction.objects.filter(
                invoice=self.invoice,
                tool_name="assess_invoice_risk",
                approved__isnull=True,
            ).count(),
            1,
        )

    def test_paid_invoice_has_low_risk(self):
        self.invoice.status = Invoice.Status.PAID
        self.invoice.save(update_fields=["status"])

        risk = assess_invoice_risk(self.invoice)

        self.assertEqual(risk, Invoice.RiskLevel.LOW)

    def test_cancelled_invoice_has_low_risk(self):
        self.invoice.status = Invoice.Status.CANCELLED
        self.invoice.save(update_fields=["status"])

        risk = assess_invoice_risk(self.invoice)

        self.assertEqual(risk, Invoice.RiskLevel.LOW)


class ReminderApprovalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="approval_tester",
            password="TestPassword123!",
        )
        self.client.force_login(self.user)

        self.client_record = Client.objects.create(
            name="Approval Test Client",
            email="approval-test@example.com",
        )
        self.invoice = Invoice.objects.create(
            paypal_invoice_id="APPROVAL-TEST-INVOICE-001",
            client=self.client_record,
            amount=Decimal("250.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 10, 1),
            status=Invoice.Status.SENT,
        )
        self.reminder = ReminderLog.objects.create(
            invoice=self.invoice,
            tone=ReminderLog.Tone.FRIENDLY,
            subject="Payment reminder",
            body="Please confirm your expected payment date.",
            status=ReminderLog.Status.PENDING_APPROVAL,
        )

    def test_approve_pending_reminder(self):
        response = self.client.post(
            reverse("approve_reminder", args=[self.reminder.id])
        )

        self.assertEqual(response.status_code, 200)
        self.reminder.refresh_from_db()
        self.assertEqual(
            self.reminder.status,
            ReminderLog.Status.APPROVED,
        )
        self.assertIn("No message was sent", response.json()["message"])

    def test_reject_pending_reminder(self):
        response = self.client.post(
            reverse("reject_reminder", args=[self.reminder.id])
        )

        self.assertEqual(response.status_code, 200)
        self.reminder.refresh_from_db()
        self.assertEqual(
            self.reminder.status,
            ReminderLog.Status.REJECTED,
        )
        self.assertIn("No message was sent", response.json()["message"])

    def test_approving_already_approved_reminder_returns_409(self):
        self.reminder.status = ReminderLog.Status.APPROVED
        self.reminder.save(update_fields=["status"])

        response = self.client.post(
            reverse("approve_reminder", args=[self.reminder.id])
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"],
            "Only pending reminders can be approved.",
        )

    def test_rejecting_already_rejected_reminder_returns_409(self):
        self.reminder.status = ReminderLog.Status.REJECTED
        self.reminder.save(update_fields=["status"])

        response = self.client.post(
            reverse("reject_reminder", args=[self.reminder.id])
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"],
            "Only pending reminders can be rejected.",
        )

    def test_cannot_approve_rejected_reminder(self):
        self.reminder.status = ReminderLog.Status.REJECTED
        self.reminder.save(update_fields=["status"])

        response = self.client.post(
            reverse("approve_reminder", args=[self.reminder.id])
        )

        self.assertEqual(response.status_code, 409)

    def test_anonymous_user_cannot_approve_reminder(self):
        anonymous_client = TestClient()

        response = anonymous_client.post(
            reverse("approve_reminder", args=[self.reminder.id])
        )

        self.assertIn(response.status_code, [401, 403])

    def test_anonymous_user_cannot_reject_reminder(self):
        anonymous_client = TestClient()

        response = anonymous_client.post(
            reverse("reject_reminder", args=[self.reminder.id])
        )

        self.assertIn(response.status_code, [401, 403])
    def test_anonymous_user_cannot_access_invoice_list(self):
        anonymous_client = TestClient()

        response = anonymous_client.get("/api/invoices/")

        self.assertIn(response.status_code, [401, 403])
    def test_anonymous_user_cannot_access_reminder_list(self):
        anonymous_client = TestClient()

        response = anonymous_client.get("/api/reminders/")

        self.assertIn(response.status_code, [401, 403])

    def test_anonymous_user_cannot_access_expenses(self):
        anonymous_client = TestClient()

        response = anonymous_client.get("/api/expenses/")

        self.assertIn(response.status_code, [401, 403])

class CashFlowForecastTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="forecast_tester",
            password="TestPassword123!",
        )
        self.client.force_login(self.user)

        self.client_record = Client.objects.create(
            name="Forecast Test Client",
            email="forecast@example.com",
            reliability_score=75,
        )

        self.invoice = Invoice.objects.create(
            paypal_invoice_id="FORECAST-TEST-001",
            client=self.client_record,
            amount=Decimal("500.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 10, 12),
            status=Invoice.Status.SENT,
        )

        self.expense = Expense.objects.create(
            description="Forecast test subscription",
            amount=Decimal("200.00"),
            currency="USD",
            due_date=timezone.localdate() + timedelta(days=7),
            category=Expense.Category.SOFTWARE,
            is_paid=False,
        )

    def test_forecast_calculates_projected_gap(self):
        snapshot = generate_cash_flow_snapshot()

        self.assertEqual(snapshot.expected_inflow, Decimal("500.00"))
        self.assertEqual(
            snapshot.upcoming_obligations,
            Decimal("200.00"),
        )
        self.assertEqual(snapshot.projected_gap, Decimal("-300.00"))

    def test_paid_expense_is_excluded(self):
        self.expense.is_paid = True
        self.expense.save(update_fields=["is_paid"])

        snapshot = generate_cash_flow_snapshot()

        self.assertEqual(
            snapshot.upcoming_obligations,
            Decimal("0.00"),
        )

    def test_overdue_expense_is_excluded(self):
        self.expense.due_date = timezone.localdate() - timedelta(days=3)
        self.expense.save(update_fields=["due_date"])

        snapshot = generate_cash_flow_snapshot()

        self.assertEqual(
            snapshot.upcoming_obligations,
            Decimal("0.00"),
        )

    def test_expense_api_returns_expense(self):
        response = self.client.get("/api/expenses/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(
                item["description"] == "Forecast test subscription"
                for item in response.json()
            )
        )

    def test_snapshot_api_returns_snapshots(self):
        snapshot = generate_cash_flow_snapshot()

        response = self.client.get("/api/cash-flow-snapshots/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(
                item["id"] == snapshot.id
                for item in response.json()
            )
        )

    def test_overdue_invoice_is_included_in_expected_inflow(self):
        self.invoice.due_date = timezone.localdate() - timedelta(days=3)
        self.invoice.save(update_fields=["due_date"])

        snapshot = generate_cash_flow_snapshot()

        self.assertEqual(
            snapshot.expected_inflow,
            Decimal("500.00"),
        )


class RunCashflowAgentCommandTests(TestCase):
    @patch(
        "core.management.commands.run_cashflow_agent.run_agent_cycle",
        side_effect=RuntimeError("Simulated agent failure"),
    )
    def test_agent_failure_is_reported(self, mock_run_agent):
        output = StringIO()

        with self.assertRaises(RuntimeError):
            call_command(
                "run_cashflow_agent",
                stdout=output,
            )

        self.assertIn(
            "Starting Cash-Flow Guardian agent...",
            output.getvalue(),
        )

        mock_run_agent.assert_called_once()


class ProcessOverdueInvoiceTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            name="Reminder Test Client",
            email="reminder-test@example.com",
            reliability_score=75,
        )

        self.invoice = Invoice.objects.create(
            paypal_invoice_id="REMINDER-TEST-001",
            client=self.client_record,
            amount=Decimal("500.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 10, 1),
            status=Invoice.Status.SENT,
        )

    @patch("core.agent.loop.generate_reminder_draft")
    def test_approved_reminder_is_not_recreated(self, mock_generate_draft):
        existing_reminder = ReminderLog.objects.create(
            invoice=self.invoice,
            tone=ReminderLog.Tone.FRIENDLY,
            subject="Existing reminder",
            body="Already reviewed.",
            status=ReminderLog.Status.APPROVED,
        )

        result = process_overdue_invoice(self.invoice)

        self.assertEqual(result["reminder_id"], existing_reminder.id)
        self.assertEqual(
            result["reminder_status"],
            ReminderLog.Status.APPROVED,
        )
        self.assertFalse(result["draft_created"])
        mock_generate_draft.assert_not_called()

        self.assertEqual(
            ReminderLog.objects.filter(invoice=self.invoice).count(),
            1,
        )

    @patch("core.agent.loop.generate_reminder_draft")
    def test_rejected_reminder_is_not_recreated(self, mock_generate_draft):
        existing_reminder = ReminderLog.objects.create(
            invoice=self.invoice,
            tone=ReminderLog.Tone.FRIENDLY,
            subject="Rejected reminder",
            body="Previously rejected.",
            status=ReminderLog.Status.REJECTED,
        )

        result = process_overdue_invoice(self.invoice)

        self.assertEqual(result["reminder_id"], existing_reminder.id)
        self.assertEqual(
            result["reminder_status"],
            ReminderLog.Status.REJECTED,
        )
        self.assertFalse(result["draft_created"])
        mock_generate_draft.assert_not_called()

        self.assertEqual(
            ReminderLog.objects.filter(invoice=self.invoice).count(),
            1,
        )

    @patch("core.agent.loop.generate_reminder_draft")
    def test_pending_reminder_is_not_recreated(self, mock_generate_draft):
        existing_reminder = ReminderLog.objects.create(
            invoice=self.invoice,
            tone=ReminderLog.Tone.FRIENDLY,
            subject="Existing pending reminder",
            body="Awaiting owner review.",
            status=ReminderLog.Status.PENDING_APPROVAL,
        )

        result = process_overdue_invoice(self.invoice)

        self.assertEqual(result["reminder_id"], existing_reminder.id)
        self.assertEqual(
            result["reminder_status"],
            ReminderLog.Status.PENDING_APPROVAL,
        )
        self.assertFalse(result["draft_created"])
        mock_generate_draft.assert_not_called()

        self.assertEqual(
            ReminderLog.objects.filter(invoice=self.invoice).count(),
            1,
        )


class RunAgentCycleErrorLoggingTests(TestCase):
    @patch("core.agent.loop.process_overdue_invoice")
    @patch("core.agent.loop.find_overdue_invoices")
    def test_failed_invoice_is_logged_and_next_invoice_is_processed(
        self,
        mock_find_overdue,
        mock_process,
    ):
        first_invoice = SimpleNamespace(
            paypal_invoice_id="TEST-FAIL-001"
        )
        second_invoice = SimpleNamespace(
            paypal_invoice_id="TEST-SUCCESS-002"
        )

        mock_find_overdue.return_value = [
            first_invoice,
            second_invoice,
        ]

        mock_process.side_effect = [
            RuntimeError("Simulated Gemini failure"),
            {
                "invoice_id": "TEST-SUCCESS-002",
                "risk_level": "LOW",
                "action_id": 2,
                "reminder_id": 3,
                "reminder_status": "PENDING_APPROVAL",
                "draft_created": False,
            },
        ]

        with self.assertLogs(
            "core.agent.loop",
            level="ERROR",
        ) as captured_logs:
            results = run_agent_cycle()

        self.assertEqual(len(results), 2)
        self.assertFalse(results[0]["success"])
        self.assertEqual(results[0]["invoice_id"], "TEST-FAIL-001")
        self.assertEqual(
            results[0]["error"],
            "Simulated Gemini failure",
        )

        self.assertTrue(results[1]["success"])
        self.assertEqual(
            results[1]["invoice_id"],
            "TEST-SUCCESS-002",
        )

        self.assertEqual(mock_process.call_count, 2)

        log_output = "\n".join(captured_logs.output)
        self.assertIn("TEST-FAIL-001", log_output)
        self.assertIn("Simulated Gemini failure", log_output)
        self.assertIn("Traceback", log_output)


class PayPalInvoiceSyncTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            name="PayPal Sandbox Client",
            email="demo@example.com",
        )

        self.paypal_data = {
            "id": "INV2-TEST-SYNC-001",
            "status": "DRAFT",
            "detail": {
                "invoice_date": "2026-10-18",
                "payment_term": {
                    "term_type": "NO_DUE_DATE",
                },
                "metadata": {
                    "recipient_view_url": (
                        "https://www.sandbox.paypal.com/invoice/p/test"
                    ),
                },
            },
            "amount": {
                "value": "5.00",
                "currency_code": "USD",
            },
            "primary_recipients": [
                {
                    "billing_info": {
                        "email_address": "demo@example.com",
                    },
                },
            ],
        }

    @patch("core.webhooks.fetch_paypal_invoice")
    def test_syncs_draft_without_due_date(self, mock_fetch):
        mock_fetch.return_value = self.paypal_data

        invoice = sync_paypal_invoice("INV2-TEST-SYNC-001")

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.amount, Decimal("5.00"))
        self.assertEqual(invoice.currency, "USD")
        self.assertIsNone(invoice.due_date)
        self.assertFalse(invoice.is_overdue)
        self.assertEqual(invoice.client, self.client_record)

    @patch("core.webhooks.fetch_paypal_invoice")
    def test_syncing_same_invoice_does_not_duplicate(self, mock_fetch):
        mock_fetch.return_value = self.paypal_data

        first = sync_paypal_invoice("INV2-TEST-SYNC-001")
        second = sync_paypal_invoice("INV2-TEST-SYNC-001")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Invoice.objects.filter(
                paypal_invoice_id="INV2-TEST-SYNC-001"
            ).count(),
            1,
        )

    @patch("core.webhooks.fetch_paypal_invoice")
    def test_unknown_recipient_is_rejected(self, mock_fetch):
        data = {
            **self.paypal_data,
            "primary_recipients": [
                {
                    "billing_info": {
                        "email_address": "unknown@example.com",
                    },
                },
            ],
        }
        mock_fetch.return_value = data

        with self.assertRaisesMessage(
            ValueError,
            "No local client matches recipient",
        ):
            sync_paypal_invoice("INV2-TEST-SYNC-001")

        self.assertFalse(
            Invoice.objects.filter(
                paypal_invoice_id="INV2-TEST-SYNC-001"
            ).exists()
        )

    @patch("core.webhooks.fetch_paypal_invoice")
    def test_unsupported_status_is_rejected(self, mock_fetch):
        data = {
            **self.paypal_data,
            "status": "UNKNOWN_STATUS",
        }
        mock_fetch.return_value = data

        with self.assertRaisesMessage(
            ValueError,
            "Unsupported PayPal invoice status",
        ):
            sync_paypal_invoice("INV2-TEST-SYNC-001")

        self.assertFalse(
            Invoice.objects.filter(
                paypal_invoice_id="INV2-TEST-SYNC-001"
            ).exists()
        )
    @patch("core.webhooks.fetch_paypal_invoice")
    def test_mismatched_paypal_invoice_id_is_rejected(self, mock_fetch):
        mock_fetch.return_value = {
            **self.paypal_data,
            "id": "DIFFERENT-INVOICE-ID",
        }

        with self.assertRaisesMessage(
            ValueError,
            "PayPal returned an unexpected invoice ID.",
        ):
            sync_paypal_invoice("INV2-TEST-SYNC-001")

        self.assertFalse(
            Invoice.objects.filter(
                paypal_invoice_id="INV2-TEST-SYNC-001"
            ).exists()
        )

class ReminderPlaceholderValidationTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            name="Placeholder Test Client",
            email="placeholder-test@example.com",
        )

        self.invoice = Invoice.objects.create(
            paypal_invoice_id="INV-PLACEHOLDER-TEST",
            client=self.client_record,
            amount=Decimal("100.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=date(2026, 10, 20),
            status=Invoice.Status.SENT,
        )

    def test_placeholder_draft_is_rejected_before_saving(self):
        draft = (
            "Subject: Payment reminder\n\n"
            "Hello,\n"
            "Please confirm your expected payment date.\n\n"
            "[Your Name/Company Name]\n"
            "Accounts Receivable"
        )

        with self.assertRaisesRegex(
            ValueError,
            "unresolved placeholders",
        ):
            save_reminder_draft(self.invoice, draft)

        self.assertEqual(
            ReminderLog.objects.filter(invoice=self.invoice).count(),
            0,
        )

    def test_clean_draft_can_be_saved(self):
        draft = (
            "Subject: Payment reminder\n\n"
            "Hello,\n"
            "Please confirm your expected payment date.\n"
            "Thank you for your time."
        )

        reminder = save_reminder_draft(self.invoice, draft)

        self.assertEqual(reminder.subject, "Payment reminder")
        self.assertEqual(
            reminder.status,
            ReminderLog.Status.PENDING_APPROVAL,
        )
        self.assertNotIn("[", reminder.body)