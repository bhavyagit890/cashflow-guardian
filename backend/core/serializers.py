#a serializer converts django models into json format and vice versa


from rest_framework import serializers
from .models import Client
from .models import Invoice
from .models import ReminderLog
from .models import PaymentPlan
from .models import AgentAction
from core.models import Expense, CashFlowSnapshot

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"

class InvoiceSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = "__all__"

class ReminderLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReminderLog
        fields = "__all__"


class PaymentPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentPlan
        fields = "__all__"


class AgentActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentAction
        fields = "__all__"


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"


class CashFlowSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowSnapshot
        fields = "__all__"
