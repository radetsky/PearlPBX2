from rest_framework import serializers

from apps.api.models import CustomListNames, CustomListEntries
from core.models import Blacklist, Whitelist, Contact


class CustomListNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomListNames
        fields = ["id", "name"]
        read_only_fields = ["id"]


class CustomListEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomListEntries
        fields = ["id", "callerid", "destination", "reason", "expiration_date"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "destination": {"required": False, "allow_blank": True, "default": ""},
            "reason": {"required": False, "allow_blank": True, "default": ""},
            "expiration_date": {"required": False, "allow_null": True},
        }


class _CallerListSerializer(serializers.ModelSerializer):
    """Shared base for Blacklist/Whitelist (identical fields)."""

    class Meta:
        fields = ["id", "callerid", "destination", "reason", "expiration_date"]
        read_only_fields = ["id"]
        validators = []
        extra_kwargs = {
            "destination": {"required": False, "allow_blank": True, "default": ""},
            "reason": {"required": False, "allow_blank": True, "default": ""},
            "expiration_date": {"required": False, "allow_null": True},
        }


class BlacklistSerializer(_CallerListSerializer):
    class Meta(_CallerListSerializer.Meta):
        model = Blacklist


class WhitelistSerializer(_CallerListSerializer):
    class Meta(_CallerListSerializer.Meta):
        model = Whitelist


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "callerid", "name"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "callerid": {"validators": []},
        }


class OriginateSerializer(serializers.Serializer):
    channel = serializers.CharField(
        max_length=256,
        help_text="First leg to dial, e.g. 'Local/0503856087@default' or 'PJSIP/101'.",
    )
    exten = serializers.CharField(
        max_length=128,
        help_text="Extension/number the first leg is connected to, e.g. '0675653380'.",
    )
    context = serializers.CharField(
        max_length=128,
        default="default",
        help_text="Dialplan context. Defaults to 'default'.",
    )
    priority = serializers.IntegerField(
        default=1, min_value=1, help_text="Dialplan priority."
    )
    callerid = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        help_text="Caller ID, format 'name<number>', e.g. '380443333333<0675653380>'.",
    )
    variable = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        help_text='Channel variables, e.g. {"userId": "0"}.',
    )
    timeout_ms = serializers.IntegerField(
        default=30000,
        min_value=1000,
        max_value=120000,
        help_text="Max time to wait for the originate in milliseconds.",
    )

    def to_ami_kwargs(self):
        data = self.validated_data
        kwargs = {
            "channel": data["channel"],
            "exten": data["exten"],
            "context": data["context"],
            "priority": data["priority"],
            "timeout_ms": data["timeout_ms"],
            "variables": data.get("variable") or {},
        }
        callerid = data.get("callerid")
        if callerid:
            kwargs["callerid"] = callerid
        return kwargs
