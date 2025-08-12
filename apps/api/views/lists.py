import json

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.api.models import CustomListNames, CustomListEntries
from apps.api.mixins import AllowedHostsIPMixin

from core.models import Blacklist, Whitelist, Contact

# TODO: Add security Mixins to allow access only to authorized IP addresses


@method_decorator(csrf_exempt, name="dispatch")
class ListsView(AllowedHostsIPMixin, View):
    def get(self, request):
        lists = CustomListNames.objects.all().values("id", "name")
        return JsonResponse(list(lists), safe=False)


@method_decorator(csrf_exempt, name="dispatch")
class ListAddView(AllowedHostsIPMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            name = data.get("name", "").strip()
            if not name:
                return JsonResponse({"error": 'Missing "name"'}, status=400)
            item = CustomListNames.objects.create(name=name)
            return JsonResponse({"id": str(item.id), "name": item.name}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ListUpdateView(AllowedHostsIPMixin, View):
    def post(self, request, pk):
        try:
            obj = CustomListNames.objects.get(pk=pk)
        except CustomListNames.DoesNotExist:
            return JsonResponse({"error": "List not found"}, status=404)

        try:
            data = json.loads(request.body)
            name = data.get("name", "").strip()
            if not name:
                return JsonResponse({"error": 'Missing "name"'}, status=400)
            obj.name = name
            obj.save()
            return JsonResponse({"id": str(obj.id), "name": obj.name})
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ListRevokeView(AllowedHostsIPMixin, View):
    def delete(self, request, pk):
        try:
            obj = CustomListNames.objects.get(pk=pk)
            obj.delete()
            return JsonResponse({"status": "deleted", "id": str(pk)})
        except CustomListNames.DoesNotExist:
            return JsonResponse({"error": "List not found"}, status=404)


# Custom List Entries View -----------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class ListEntriesView(AllowedHostsIPMixin, View):
    def get(self, request, pk):
        try:
            obj = CustomListEntries.objects.filter(list_name__id=pk).values(
                "id", "callerid", "destination", "reason", "expiration_date"
            )
            return JsonResponse(list(obj), safe=False)
        except CustomListEntries.DoesNotExist:
            return JsonResponse({"error": "List entries not found"}, status=404)


@method_decorator(csrf_exempt, name="dispatch")
class ListEntryAddView(AllowedHostsIPMixin, View):
    def post(self, request, pk):
        try:
            list_name = CustomListNames.objects.get(pk=pk)
        except CustomListNames.DoesNotExist:
            return JsonResponse({"error": "List not found"}, status=404)

        try:
            data = json.loads(request.body)
            callerid = data.get("callerid", "").strip()
            destination = data.get("destination", "").strip()
            reason = data.get("reason", "").strip()
            expiration_date = data.get("expiration_date")

            if not callerid:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            entry = CustomListEntries.objects.create(
                list_name=list_name,
                callerid=callerid,
                destination=destination,
                reason=reason,
                expiration_date=expiration_date,
            )
            return JsonResponse(
                {
                    "id": str(entry.id),
                    "callerid": entry.callerid,
                    "destination": entry.destination,
                    "reason": entry.reason,
                    "expiration_date": entry.expiration_date,
                },
                status=201,
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ListEntryRevokeView(AllowedHostsIPMixin, View):
    def delete(self, request, pk, entry_pk):
        try:
            entry = CustomListEntries.objects.get(pk=entry_pk, list_name__id=pk)
            entry.delete()
            return JsonResponse({"status": "deleted", "id": str(entry_pk)})
        except CustomListEntries.DoesNotExist:
            return JsonResponse({"error": "Entry not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class BlackListView(AllowedHostsIPMixin, View):
    def get(self, request):
        blacklist = Blacklist.objects.all().values(
            "id", "callerid", "destination", "reason", "expiration_date"
        )
        return JsonResponse(list(blacklist), safe=False)

    def post(self, request):
        try:
            data = json.loads(request.body)
            callerid = data.get("callerid", "").strip()
            destination = data.get("destination", "").strip()
            reason = data.get("reason", "").strip()
            expiration_date = data.get("expiration_date")

            if not callerid:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            entry, created = Blacklist.objects.update_or_create(
                callerid=callerid,
                destination=destination,
                defaults={"reason": reason, "expiration_date": expiration_date},
            )
            return JsonResponse(
                {
                    "id": str(entry.id),
                    "callerid": entry.callerid,
                    "destination": entry.destination,
                    "reason": entry.reason,
                    "expiration_date": entry.expiration_date,
                    "created": created,
                },
                status=201 if created else 200,
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    def delete(self, request, pk):
        try:
            entry = Blacklist.objects.get(pk=pk)
            entry.delete()
            return JsonResponse({"status": "deleted", "id": str(pk)})
        except Blacklist.DoesNotExist:
            return JsonResponse({"error": "Blacklist entry not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class WhiteListView(AllowedHostsIPMixin, View):
    def get(self, request):
        whitelist = Whitelist.objects.all().values(
            "id", "callerid", "destination", "reason", "expiration_date"
        )
        return JsonResponse(list(whitelist), safe=False)

    def post(self, request):
        try:
            data = json.loads(request.body)
            callerid = data.get("callerid", "").strip()
            destination = data.get("destination", "").strip()
            reason = data.get("reason", "").strip()
            expiration_date = data.get("expiration_date")

            if not callerid:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            entry, created = Whitelist.objects.update_or_create(
                callerid=callerid,
                destination=destination,
                defaults={"reason": reason, "expiration_date": expiration_date},
            )
            return JsonResponse(
                {
                    "id": str(entry.id),
                    "callerid": entry.callerid,
                    "destination": entry.destination,
                    "reason": entry.reason,
                    "expiration_date": entry.expiration_date,
                    "created": created,
                },
                status=201 if created else 200,
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    def delete(self, request, pk):
        try:
            entry = Whitelist.objects.get(pk=pk)
            entry.delete()
            return JsonResponse({"status": "deleted", "id": str(pk)})
        except Whitelist.DoesNotExist:
            return JsonResponse({"error": "Whitelist entry not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class ContactsView(AllowedHostsIPMixin, View):
    def get(self, request):
        contacts = Contact.objects.all().values(
            "id", "callerid", "name"
        )
        return JsonResponse(list(contacts), safe=False)

    def post(self, request):
        try:
            data = json.loads(request.body)
            callerid = data.get("callerid", "").strip()
            name = data.get("name", "").strip()

            if not callerid or not name:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            contact, created = Contact.objects.update_or_create(
                callerid=callerid,
                defaults={"name": name},
            )
            return JsonResponse(
                {
                    "id": str(contact.id),
                    "callerid": contact.callerid,
                    "name": contact.name,
                    "created": created,
                },
                status=201 if created else 200,
            )
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    def delete(self, request, pk):
        try:
            contact = Contact.objects.get(pk=pk)
            contact.delete()
            return JsonResponse({"status": "deleted", "id": str(pk)})
        except Contact.DoesNotExist:
            return JsonResponse({"error": "Contact not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
