from django.http import JsonResponse
from django.views.decorators.http import require_safe
from django.views.generic import TemplateView


@require_safe
def healthz(request):
    return JsonResponse({"status": "ok"})


class HomeView(TemplateView):
    template_name = "storefront/home.html"
