from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse

# Rutas que se pueden abrir sin iniciar sesión
RUTAS_LIBRES = ("/login/", "/logout/", "/admin/", "/static/")


class LoginRequeridoMiddleware:
    """Exige iniciar sesión en todo el sistema, salvo en RUTAS_LIBRES."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(RUTAS_LIBRES):
            if request.path.startswith("/buscar-escuelas/"):
                return JsonResponse([], safe=False, status=401)
            return redirect_to_login(request.get_full_path())
        return self.get_response(request)
