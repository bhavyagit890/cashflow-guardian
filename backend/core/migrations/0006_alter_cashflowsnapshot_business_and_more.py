
from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models
from django.contrib.auth.hashers import make_password


def backfill_business_ownership(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Business = apps.get_model("core", "Business")
    Client = apps.get_model("core", "Client")
    Expense = apps.get_model("core", "Expense")
    CashFlowSnapshot = apps.get_model("core", "CashFlowSnapshot")

    # Create or reuse the demo account.
    user, created = User.objects.get_or_create(
        username="cashflow_demo",
        defaults={"email": "demo@cashflowguardian.local"},
    )

    # A newly created migration user must receive its password
    # through the seed command, not through this migration.
    if created:
        user.password = make_password(None)
        user.save(update_fields=["password"])
    # Create or reuse the demo business.
    business, _ = Business.objects.get_or_create(
        owner_id=user.pk,
        defaults={"name": "Cash-Flow Guardian"},
    )

    # Assign all existing unowned records to this business.
    Client.objects.filter(business__isnull=True).update(
        business_id=business.pk
    )

    Expense.objects.filter(business__isnull=True).update(
        business_id=business.pk
    )

    CashFlowSnapshot.objects.filter(business__isnull=True).update(
        business_id=business.pk
    )


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0005_business_cashflowsnapshot_business_client_business_and_more",
        ),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            backfill_business_ownership,
            migrations.RunPython.noop,
        ),

        migrations.AlterField(
            model_name="cashflowsnapshot",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cash_flow_snapshots",
                to="core.business",
            ),
        ),

        migrations.AlterField(
            model_name="client",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="clients",
                to="core.business",
            ),
        ),

        migrations.AlterField(
            model_name="expense",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="expenses",
                to="core.business",
            ),
        ),
    ]
