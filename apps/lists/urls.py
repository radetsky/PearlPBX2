from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListsIndexView.as_view(), name="lists_index"),
    path("blocklist/", views.BlocklistView.as_view(), name="blocklist"),
    path("blocklist/<uuid:pk>/delete/", views.BlocklistDeleteView.as_view(), name="blocklist_delete"),
    path("allowlist/", views.AllowlistView.as_view(), name="allowlist"),
    path("allowlist/<uuid:pk>/delete/", views.AllowlistDeleteView.as_view(), name="allowlist_delete"),
    path("contacts/", views.ContactsView.as_view(), name="contacts_list"),
    path("contacts/<uuid:pk>/delete/", views.ContactsDeleteView.as_view(), name="contacts_delete"),
]
