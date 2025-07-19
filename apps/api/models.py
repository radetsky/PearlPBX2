from uuid import uuid4
from django.db import models
import django.db.models.deletion as deletion

from core.models import AuditFields


class CustomListNames(AuditFields):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Name of the custom list",
        verbose_name="Custom List Name",
    )

    class Meta:
        db_table = "custom_list_names"
        verbose_name_plural = "Custom List Names"

    def __str__(self):
        return self.name


class CustomListEntries(AuditFields):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    list_name = models.ForeignKey(
        CustomListNames,
        related_name="entries",
        on_delete=deletion.CASCADE,
        help_text="Custom list name",
        verbose_name="Custom List Name",
    )
    callerid = models.CharField(
        max_length=64,
        unique=False,
        help_text="Value of the custom list entry",
        verbose_name="Custom List Entry Value",
    )
    destination = models.CharField(
        max_length=64,
        help_text="Destination number where calls must be detected. Default="
        " for whole system detection.",
        verbose_name="Destination",
        default="",
        blank=True,
        null=False,
    )
    reason = models.CharField(
        max_length=64,
        help_text="Reason for detecting the caller ID",
        verbose_name="Reason",
        default="",
    )
    expiration_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Expiration date for the custom list entry. If not set, the entry is permanent.",
        verbose_name="Expiration Date",
    )

    class Meta:
        db_table = "custom_list_entries"
        verbose_name_plural = "Custom List Entries"

    def __str__(self):
        return f"{self.list_name.name} - {self.callerid}"
