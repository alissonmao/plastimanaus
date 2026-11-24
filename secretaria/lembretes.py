"""Secretaria → Lembretes (próprios do ERP; aviso na hora pelo WhatsApp do Angel)."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from .acesso import secretaria_obrigatoria
from .models import Lembrete


class LembreteForm(forms.ModelForm):
    class Meta:
        model = Lembrete
        fields = ["titulo", "quando", "repeticao", "notas"]
        widgets = {"quando": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "notas": forms.Textarea(attrs={"rows": 3}), "titulo": forms.TextInput(attrs={"autofocus": True, "style": "width:100%"})}


def _voltar(request, padrao="sec_lembretes"):
    v = request.POST.get("voltar") or ""
    return redirect(v if v and url_has_allowed_host_and_scheme(v, {request.get_host()}) and v.startswith("/") else padrao)


def situacao(lembretes, agora=None):
    agora = agora or timezone.now()
    fim_dia = timezone.localtime(agora).replace(hour=23, minute=59, second=59)
    for l in lembretes:
        l.atrasado = not l.concluido_em and l.quando < agora
        l.hoje = not l.concluido_em and agora <= l.quando <= fim_dia
    return lembretes


def resumo(usuario):
    """Para o Painel: pendentes de hoje e atrasados."""
    agora = timezone.now()
    fim_dia = timezone.localtime(agora).replace(hour=23, minute=59, second=59)
    pend = list(Lembrete.objects.filter(usuario=usuario, concluido_em=None, quando__lte=fim_dia).order_by("quando")[:20])
    situacao(pend, agora)
    return dict(lista=pend, hoje=sum(1 for l in pend if l.hoje), atrasados=sum(1 for l in pend if l.atrasado))


@secretaria_obrigatoria
def lista(request):
    ver = request.GET.get("ver", "pendentes")
    qs = Lembrete.objects.filter(usuario=request.user)
    qs = qs.exclude(concluido_em=None).order_by("-concluido_em")[:100] if ver == "concluidos" else qs.filter(concluido_em=None).order_by("quando")
    agora = timezone.localtime()
    inicial = {"quando": (agora + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)}
    return render(request, "secretaria/lembretes.html", dict(
        titulo="Lembretes", lembretes=situacao(list(qs)), ver=ver, form=LembreteForm(initial=inicial)))


@secretaria_obrigatoria
def form(request, pk=None):
    obj = get_object_or_404(Lembrete, pk=pk, usuario=request.user) if pk else None
    f = LembreteForm(request.POST or None, instance=obj)
    if request.method == "POST":
        if request.POST.get("excluir") and obj:
            obj.delete()
            messages.success(request, "Lembrete apagado.")
            return redirect("sec_lembretes")
        if f.is_valid():
            l = f.save(commit=False)
            l.usuario = request.user
            if obj and "quando" in f.changed_data:
                l.avisado_em = None
            l.save()
            messages.success(request, "Lembrete salvo.")
            return _voltar(request)
    return render(request, "erp/form.html", dict(titulo="Editar lembrete" if obj else "Novo lembrete", form=f, obj=obj,
                                                  voltar="/secretaria/lembretes/"))


@secretaria_obrigatoria
@require_POST
def concluir(request, pk):
    l = get_object_or_404(Lembrete, pk=pk, usuario=request.user)
    l.concluir()
    messages.success(request, "Concluído." + (f" Próximo: {timezone.localtime(l.quando):%d/%m %H:%M}." if l.repeticao else ""))
    return _voltar(request)


@secretaria_obrigatoria
@require_POST
def adiar(request, pk):
    l = get_object_or_404(Lembrete, pk=pk, usuario=request.user)
    minutos = int(request.POST.get("minutos", 60))
    l.quando = max(l.quando, timezone.now()) + timedelta(minutes=minutos)
    l.avisado_em = None
    l.save()
    messages.success(request, f"Adiado para {timezone.localtime(l.quando):%d/%m %H:%M}.")
    return _voltar(request)


def criar(usuario, titulo, quando, repeticao="", origem="site", notas=""):
    return Lembrete.objects.create(usuario=usuario, titulo=titulo[:300], quando=quando, repeticao=repeticao or "", origem=origem, notas=notas)
