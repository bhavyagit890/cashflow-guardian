
from django.db import models
from django.utils import timezone


class Client(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    reliability_score = models.PositiveSmallIntegerField(default=50)
    avg_days_late = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    class RiskLevel(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    paypal_invoice_id = models.CharField(max_length=100, unique=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    issued_at = models.DateTimeField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    payment_link = models.URLField(blank=True)
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_overdue(self):
        return (
            self.due_date is not None
            and self.status in [
                self.Status.SENT,
                self.Status.PARTIALLY_PAID,
            ]
            and self.due_date < timezone.localdate()
        )

    def __str__(self):
        return f"Invoice {self.paypal_invoice_id}"


class ReminderLog(models.Model):
    class Tone(models.TextChoices):
        FRIENDLY = "FRIENDLY", "Friendly"
        FIRM = "FIRM", "Firm"
        FINAL = "FINAL", "Final"

    class Status(models.TextChoices):
        DRAFTED = "DRAFTED", "Drafted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        SENT = "SENT", "Sent"
        REJECTED = "REJECTED", "Rejected"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    tone = models.CharField(
        max_length=10,
        choices=Tone.choices,
        default=Tone.FRIENDLY,
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tone} reminder for {self.invoice}"


class PaymentPlan(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposed"
        APPROVED = "APPROVED", "Approved"
        ACTIVE = "ACTIVE", "Active"
        REJECTED = "REJECTED", "Rejected"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payment_plans",
    )
    installments = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PROPOSED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment plan for {self.invoice}"


class AgentAction(models.Model):
    class Trigger(models.TextChoices):
        WEBHOOK = "WEBHOOK", "Webhook"
        SCHEDULE = "SCHEDULE", "Scheduled Task"
        MANUAL = "MANUAL", "Manual"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_actions",
    )
    trigger = models.CharField(
        max_length=10,
        choices=Trigger.choices,
    )
    tool_name = models.CharField(max_length=100)
    tool_input = models.JSONField(default=dict)
    tool_output = models.JSONField(default=dict)
    reasoning = models.TextField(blank=True)
    requires_approval = models.BooleanField(default=True)
    approved = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tool_name} - {self.trigger}"


class WebhookEvent(models.Model):
    paypal_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.paypal_event_id}"


class CashFlowSnapshot(models.Model):
    date = models.DateField()
    expected_inflow = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    upcoming_obligations = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    projected_gap = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    def __str__(self):
        return f"Cash flow snapshot for {self.date}"


class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = "RENT", "Rent"
        SOFTWARE = "SOFTWARE", "Software"
        PAYROLL = "PAYROLL", "Payroll"
        UTILITIES = "UTILITIES", "Utilities"
        OTHER = "OTHER", "Other"

    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    currency = models.CharField(max_length=3, default="USD")
    due_date = models.DateField()
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - {self.amount} {self.currency}"
