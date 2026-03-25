from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.reports.mixins import ReportViewPermissionMixin
from core.models import Blacklist, Contact, Whitelist

from .forms import AllowlistForm, BlocklistForm, ContactForm

_LISTS_PERMISSIONS = ["edit_blocklist", "edit_allowlist", "edit_contacts"]


class ListCRUDView(ReportViewPermissionMixin, View):
    model = None
    form_class = None
    template_name = None
    order_by_field = "callerid"
    success_url_name = None
    search_fields = []
    page_size = 100

    def get_queryset(self, q=""):
        qs = self.model.objects.order_by(self.order_by_field)
        if q and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": q})
            qs = qs.filter(query)
        return qs

    def get(self, request):
        q = request.GET.get("q", "").strip()
        form = self.form_class()
        qs = self.get_queryset(q)
        paginator = Paginator(qs, self.page_size)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)
        return render(
            request, self.template_name, {"page_obj": page_obj, "form": form, "q": q}
        )

    def post(self, request):
        pk = request.POST.get("pk")
        if pk:
            obj = get_object_or_404(self.model, pk=pk)
            form = self.form_class(request.POST, instance=obj)
        else:
            form = self.form_class(request.POST)
        if form.is_valid():
            form.save()
            return redirect(self.success_url_name)
        qs = self.get_queryset()
        paginator = Paginator(qs, self.page_size)
        page_obj = paginator.get_page(1)
        return render(
            request, self.template_name, {"page_obj": page_obj, "form": form, "q": ""}
        )


class ListDeleteView(ReportViewPermissionMixin, View):
    model = None
    success_url_name = None

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk)
        obj.delete()
        return redirect(self.success_url_name)


class ListsIndexView(ReportViewPermissionMixin, View):
    def has_permission(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return any(self.request.user.has_perm(f"auth.{p}") for p in _LISTS_PERMISSIONS)

    def get(self, request):
        return render(request, "lists/index.html")


class BlocklistView(ListCRUDView):
    required_permission = "edit_blocklist"
    model = Blacklist
    form_class = BlocklistForm
    template_name = "lists/blocklist.html"
    success_url_name = "blocklist"
    search_fields = ["callerid", "destination", "reason"]


class BlocklistDeleteView(ListDeleteView):
    required_permission = "edit_blocklist"
    model = Blacklist
    success_url_name = "blocklist"


class AllowlistView(ListCRUDView):
    required_permission = "edit_allowlist"
    model = Whitelist
    form_class = AllowlistForm
    template_name = "lists/allowlist.html"
    success_url_name = "allowlist"
    search_fields = ["callerid", "destination", "reason"]


class AllowlistDeleteView(ListDeleteView):
    required_permission = "edit_allowlist"
    model = Whitelist
    success_url_name = "allowlist"


class ContactsView(ListCRUDView):
    required_permission = "edit_contacts"
    model = Contact
    form_class = ContactForm
    template_name = "lists/contacts.html"
    success_url_name = "contacts_list"
    search_fields = ["callerid", "name"]


class ContactsDeleteView(ListDeleteView):
    required_permission = "edit_contacts"
    model = Contact
    success_url_name = "contacts_list"
