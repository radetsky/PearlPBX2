"""Send the daily "longest calls" report by email."""

import datetime

from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.reports.services.longest_calls import build_longest_calls, external_filter_available


def _clean_recipients(values):
    """Flatten --to occurrences and comma-separated lists, stripping whitespace."""
    return [address.strip() for chunk in values for address in chunk.split(",") if address.strip()]


class Command(BaseCommand):
    help = "Email the top longest calls of a day (with recording links) to configured recipients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            help="Report day as YYYY-MM-DD (default: yesterday, in TIME_ZONE)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=1,
            help="Number of days ending on --date, inclusive (default: 1)",
        )
        parser.add_argument(
            "--to",
            action="append",
            default=[],
            help="Recipient address; repeat the flag or comma-separate. "
            "Overrides MAIL_REPORT_RECIPIENTS.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Number of calls in the table (default: MAIL_REPORT_LIMIT)",
        )
        parser.add_argument(
            "--include-unanswered",
            action="store_true",
            help="Include calls that were not answered (default: ANSWERED only)",
        )
        parser.add_argument(
            "--external-only",
            action="store_true",
            help="Only calls involving a SIP trunk; ignored if no trunks are configured",
        )
        parser.add_argument(
            "--language",
            default=None,
            help="Language of the email (default: LANGUAGE_CODE)",
        )
        parser.add_argument(
            "--send-empty",
            action="store_true",
            help="Send the report even when no calls match (default: skip)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print recipients, subject and the plain-text body; do not send",
        )
        parser.add_argument(
            "--print-html",
            action="store_true",
            help="Also print the rendered HTML body",
        )

    def handle(self, *args, **options):
        report_date = self._parse_date(options["date"])
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        limit = options["limit"] if options["limit"] is not None else settings.MAIL_REPORT_LIMIT
        if limit < 1:
            raise CommandError("--limit must be at least 1")

        language = options["language"] or settings.LANGUAGE_CODE
        if language not in dict(settings.LANGUAGES):
            raise CommandError(f"Unknown --language {language!r}")

        recipients = _clean_recipients(options["to"]) or _clean_recipients(
            settings.MAIL_REPORT_RECIPIENTS
        )
        if options["to"] and not recipients:
            raise CommandError("--to did not yield any recipient addresses")
        if not recipients:
            self.stdout.write(
                self.style.WARNING("MAIL_REPORT_RECIPIENTS is not configured; nothing to send.")
            )
            return

        if options["external_only"] and not external_filter_available():
            self.stdout.write(
                self.style.WARNING("--external-only ignored: no SIP trunks configured.")
            )

        rows = build_longest_calls(
            report_date,
            days=days,
            limit=limit,
            answered_only=not options["include_unanswered"],
            external_only=options["external_only"],
        )

        if not rows and not options["send_empty"]:
            self.stdout.write(self.style.WARNING(f"No calls found for {report_date}; nothing sent."))
            return

        with translation.override(language):
            subject = _("Longest calls report for %(date)s") % {
                "date": report_date.strftime("%d.%m.%Y")
            }
            context = {
                "rows": rows,
                "report_date": report_date,
                "days": days,
                "public_url": settings.PEARLPBX_PUBLIC_URL.rstrip("/"),
            }
            text_body = render_to_string("emails/longest_calls_report.txt", context)
            html_body = render_to_string("emails/longest_calls_report.html", context)

        if options["dry_run"]:
            self.stdout.write(f"Subject: {subject}")
            self.stdout.write(f"To: {', '.join(recipients)}")
            self.stdout.write(text_body)
            if options["print_html"]:
                self.stdout.write(html_body)
            self.stdout.write(self.style.SUCCESS("Dry run: nothing sent."))
            return

        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        message.attach_alternative(html_body, "text/html")
        if options["print_html"]:
            self.stdout.write(html_body)

        try:
            sent = message.send()
        except Exception as exc:
            raise CommandError(f"Failed to send the report: {exc}")
        if not sent:
            raise CommandError("The mail backend reported 0 messages sent.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Summary: date {report_date}, rows {len(rows)}, "
                f"recipients {len(recipients)}, sent 1"
            )
        )

    @staticmethod
    def _parse_date(value):
        if not value:
            return timezone.localdate() - datetime.timedelta(days=1)
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            raise CommandError(f"Invalid --date {value!r}, expected YYYY-MM-DD")
