from django.urls import path
from apps.api.views import lists

urlpatterns = [
    path('lists/', lists.ListsView.as_view(), name='lists_list'), # List all lists
    path('lists/add/', lists.ListAddView.as_view(), name='lists_add'), # Add a new list
    path('lists/update/<uuid:pk>/',
         lists.ListUpdateView.as_view(), name='lists_update'), # Update the name of an existing list
    path('lists/revoke/<uuid:pk>/', lists.ListRevokeView.as_view(), # Revoke a list
         name='lists_revoke'),
    # List entries in a specific list
    path('lists/<uuid:pk>/',
         lists.ListEntriesView.as_view(), name='lists_page'),  # View a specific list
    path('lists/<uuid:pk>/add/',
         lists.ListEntryAddView.as_view(), name='lists_entry_add'),  # Add an entry to a specific list
    path('lists/<uuid:pk>/revoke/<uuid:entry_pk>/',
         lists.ListEntryRevokeView.as_view(), name='lists_entry_revoke'),  # Revoke an entry from a specific list

]