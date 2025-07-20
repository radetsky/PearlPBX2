from django.contrib.auth.mixins import UserPassesTestMixin


class GroupCheckMixin(UserPassesTestMixin):
    group_allowed = []

    def test_func(self):
        return self.request.user.groups.filter(name__in=self.group_allowed).exists()
