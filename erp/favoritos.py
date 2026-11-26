"""Menu Rotina: cada usuário favorita as telas que usa no dia a dia (estrela no título)."""
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import Favorito


def _url_segura(u):
    return u if u.startswith("/") and not u.startswith("//") and "\\" not in u else "/"


@require_POST
def alternar(request):
    url = _url_segura(request.POST.get("url", ""))
    fav = Favorito.objects.filter(usuario=request.user, url=url)
    if fav.exists():
        fav.delete()
    elif url != "/":
        titulo = (request.POST.get("titulo") or url).strip()[:200]
        Favorito.objects.create(usuario=request.user, url=url, titulo=titulo)
    return redirect(url)
