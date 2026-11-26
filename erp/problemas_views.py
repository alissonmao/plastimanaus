"""Tela Problemas para resolver (só lê os dados; dispensar apenas esconde por um tempo)."""
from datetime import timedelta

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import problemas as PB
from .models import DispensaProblema

CACHE_SEG = 300


def _chave(user):
    return f"problemas-criticos-{user.pk}"


def criticos(user):
    """Contagem de críticos para o menu (guardada por 5 minutos)."""
    n = cache.get(_chave(user))
    if n is None:
        res, _ = PB.conferir(user)
        n = sum(1 for r in res if r.regra.gravidade == PB.CRITICO)
        cache.set(_chave(user), n, CACHE_SEG)
    return n


def _link(rg):
    if not rg.link:
        return ""
    rota, _, arg = rg.link.partition(":")
    try:
        return reverse(rota, args=[arg] if arg else [])
    except NoReverseMatch:
        return ""


def tela(request):
    res, disp = PB.conferir(request.user)
    cache.set(_chave(request.user), sum(1 for r in res if r.regra.gravidade == PB.CRITICO), CACHE_SEG)
    areas_user = PB.areas_do_usuario(request.user)
    area = request.GET.get("area", "")
    com_regra = {rg.area for rg in PB.REGRAS}
    por_area = {a: sum(1 for r in res if r.regra.area == a) for a in PB.AREAS if a in areas_user and a in com_regra}
    ver_disp = request.GET.get("ver") == "dispensados"
    lista = disp if ver_disp else [r for r in res if not area or r.regra.area == area]
    for r in lista:
        r.grav_rotulo, r.grav_prazo = PB.GRAVIDADES[r.regra.gravidade]
        r.url = _link(r.regra)
        r.itens_vis = r.itens[:300]
    cont = {g: sum(1 for r in res if r.regra.gravidade == g) for g in PB.GRAVIDADES}
    return render(request, "erp/problemas.html", dict(
        titulo="Problemas para resolver", lista=lista, cont=cont, n_disp=len(disp), por_area=por_area, area=area,
        ver_disp=ver_disp, total=len(res), conferido=timezone.localtime(), vendedor=PB.vendedor_do_usuario(request.user)))


def _voltar(request):
    v = request.POST.get("voltar", "")
    return redirect(v if v.startswith("/problemas/") else "problemas")


@require_POST
def dispensar(request):
    regra = request.POST.get("regra", "")
    rg = next((r for r in PB.REGRAS if r.id == regra), None)
    if not rg or rg.area not in PB.areas_do_usuario(request.user):
        raise Http404
    dias = 7 if request.POST.get("dias") == "7" else 1
    volta = timezone.localdate() + timedelta(days=dias)
    DispensaProblema.objects.filter(regra=regra, volta_em__gt=timezone.localdate()).delete()
    DispensaProblema.objects.create(regra=regra, volta_em=volta, usuario=request.user)
    cache.delete(_chave(request.user))
    messages.success(request, f"“{rg.nome}” dispensado. Volta em {volta:%d/%m/%Y} se o problema continuar.")
    return _voltar(request)


@require_POST
def desfazer(request, pk):
    d = get_object_or_404(DispensaProblema, pk=pk)
    rg = next((r for r in PB.REGRAS if r.id == d.regra), None)
    if not rg or rg.area not in PB.areas_do_usuario(request.user):
        raise Http404
    d.delete()
    cache.delete(_chave(request.user))
    messages.success(request, f"“{rg.nome}” voltou para a lista.")
    return _voltar(request)
