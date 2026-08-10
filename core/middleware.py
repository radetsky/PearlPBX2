from django.utils import translation


class ForceEnglishAPIMiddleware:
    """Force English for API requests, regardless of Accept-Language or session locale."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            translation.activate("en")
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)
