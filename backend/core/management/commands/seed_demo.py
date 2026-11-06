
from datetime import timedelta

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Business,
    Client,
    Invoice,
    Expense,
    CashFlowSnapshot,
)


class Command(BaseCommand):
    help = "Create or verify the Cash-Flow Guardian demo data."

    @transaction.atomic
    def handle(self, *args, **options):
        username = config("DEMO_USERNAME")
        password = config("DEMO_PASSWORD")
        business_name = config(
            "DEMO_BUSINESS_NAME",
            default="Cash-Flow Guardian",
        )

        User = get_user_model()

        # 1. Create or reuse the demo user.
        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": "demo@cashflowguardian.local",
            },
        )

        if  user_created or not user.has_usable_password():
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write("Demo user password configured.")
        else:
            self.stdout.write("Demo user already exists.")
        # 2. Create or reuse the demo business.
        business, business_created = Business.objects.get_or_create(
            owner=user,
            defaults={"name": business_name},
        )

        if business_created:
            self.stdout.write("Demo business created.")
        else:
            self.stdout.write("Demo business already exists.")

        today = timezone.localdate()

        # 3. Create or reuse a demo client.
        client, client_created = Client.objects.get_or_create(
            business=business,
            email="seed-demo@example.com",
            defaults={
                "name": "Seed Demo Client",
                "reliability_score": 75,
                "avg_days_late": 3,
                "notes": "Sample client created by seed_demo.",
            },
        )

        if client_created:
            self.stdout.write("Sample client created.")

        # 4. Create or reuse an overdue demo invoice.
        invoice, invoice_created = Invoice.objects.get_or_create(
            paypal_invoice_id="CFG-SEED-OVERDUE-001",
            defaults={
                "client": client,
                "amount": "500.00",
                "currency": "USD",
                "issued_at": timezone.now(),
                "due_date": today - timedelta(days=5),
                "status": Invoice.Status.SENT,
                "risk_level": Invoice.RiskLevel.MEDIUM,
            },
        )

        # Ensure this unique invoice ID does not belong to another business.
        if invoice.client.business_id != business.id:
            raise CommandError(
                "The seed invoice ID already belongs to another business."
            )

        if invoice_created:
            self.stdout.write("Sample overdue invoice created.")

        # 5. Create or reuse a demo expense.
        expense, expense_created = Expense.objects.get_or_create(
            business=business,
            description="Seed demo software subscription",
            defaults={
                "amount": "200.00",
                "currency": "USD",
                "due_date": today + timedelta(days=5),
                "category": Expense.Category.SOFTWARE,
                "is_paid": False,
            },
        )

        if expense_created:
            self.stdout.write("Sample expense created.")

        # 6. Create today's cash-flow snapshot if one doesn't exist.
        snapshot_exists = CashFlowSnapshot.objects.filter(
            business=business,
            date=today,
        ).exists()

        if not snapshot_exists:
            CashFlowSnapshot.objects.create(
                business=business,
                date=today,
                expected_inflow="500.00",
                upcoming_obligations="200.00",
                projected_gap="300.00",
            )
            self.stdout.write("Cash-flow snapshot created.")

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data setup completed successfully."
            )
        )
