"""Secretaria → Agenda: compromissos do iCloud (CalDAV, com senha de app). O que muda aqui aparece no iPhone."""
import calendar as cal_mod
import uuid
from datetime import date, datetime, time, timedelta

import caldav
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils import timezone
from icalendar import Calendar as ICal
from icalendar import Event as IEvent

from .acesso import secretaria_obrigatoria

ICLOUD = "https://caldav.icloud.com/"
CACHE_SEG = 120


class ErroAgenda(Exception):
    pass


def _url_servidor():
    return getattr(settings, "SECRETARIA_CALDAV_URL", "") or ICLOUD


def _cliente(perfil):
    if not (perfil.icloud_usuario and perfil.icloud_senha_cifrada):
        raise ErroAgenda("Conecte sua agenda do iCloud em Secretaria → Configurações.")
    return caldav.DAVClient(url=_url_servidor(), username=perfil.icloud_usuario, password=perfil.icloud_senha, timeout=25)


def _erro(e):
    txt = str(e)
    if "401" in txt or "Unauthorized" in txt or "AuthorizationError" in type(e).__name__:
        return ErroAgenda("Apple ID ou senha de app recusados. Gere uma nova senha de app em appleid.apple.com.")
    return ErroAgenda(f"Falha ao falar com o iCloud ({type(e).__name__}).")


def calendarios(perfil):
    try:
        with _cliente(perfil) as c:
            out = []
            for k in c.principal().calendars():
                comps = []
                try:
                    comps = k.get_supported_components()
                except Exception:
                    comps = ["VEVENT"]
                if "VEVENT" in comps:
                    out.append(dict(url=str(k.url), nome=k.get_display_name() or "Calendário"))
            return out
    except ErroAgenda:
        raise
    except Exception as e:
        raise _erro(e) from e


def _tz():
    return timezone.get_current_timezone()


def _para_dt(v, fim=False):
    if isinstance(v, datetime):
        return timezone.localtime(v) if timezone.is_aware(v) else timezone.make_aware(v, _tz())
    return timezone.make_aware(datetime.combine(v, time.max if fim else time.min), _tz())


def eventos(perfil, inicio: date, fim: date, usar_cache=True):
    """Compromissos entre as datas, de todos os calendários escolhidos, em ordem."""
    chave = f"sec-agenda-{perfil.usuario_id}-v{cache.get(f'sec-agenda-v-{perfil.usuario_id}', 0)}-{inicio}-{fim}"
    if usar_cache and (v := cache.get(chave)) is not None:
        return v
    out = []
    nomes = {}
    try:
        with _cliente(perfil) as c:
            for k in c.principal().calendars():
                url = str(k.url)
                if perfil.agenda_calendarios and url not in perfil.agenda_calendarios:
                    continue
                nomes[url] = k.get_display_name() or "Calendário"
                ini = timezone.make_aware(datetime.combine(inicio, time.min), _tz())
                fi = timezone.make_aware(datetime.combine(fim, time.max), _tz())
                for obj in k.search(start=ini, end=fi, event=True, expand=True):
                    for comp in obj.icalendar_instance.walk("VEVENT"):
                        out.append(_evento(comp, url, nomes[url], obj))
    except ErroAgenda:
        raise
    except Exception as e:
        raise _erro(e) from e
    out.sort(key=lambda e: e["inicio"])
    cache.set(chave, out, CACHE_SEG)
    return out


def _evento(comp, url_cal, nome_cal, obj):
    ini = comp.get("dtstart").dt
    fim = comp.get("dtend").dt if comp.get("dtend") else (ini + (comp.get("duration").dt if comp.get("duration") else timedelta(hours=1)))
    dia_todo = not isinstance(ini, datetime)
    if dia_todo and not isinstance(fim, datetime):
        fim = fim - timedelta(days=1)  # DTEND de dia inteiro é exclusivo
    return dict(uid=str(comp.get("uid")), titulo=str(comp.get("summary") or "(sem título)"), local=str(comp.get("location") or ""),
                descricao=str(comp.get("description") or ""), inicio=_para_dt(ini), fim=_para_dt(fim, fim=True), dia_todo=dia_todo,
                recorrente=bool(comp.get("rrule") or comp.get("recurrence-id")), calendario=url_cal, calendario_nome=nome_cal,
                href=str(obj.url))


def _limpar_cache(perfil):
    """Troca a versão do cache do usuário: todas as janelas de datas guardadas deixam de valer."""
    k = f"sec-agenda-v-{perfil.usuario_id}"
    cache.set(k, cache.get(k, 0) + 1, None)


def _calendario(c, perfil, url=None):
    url = url or perfil.agenda_padrao
    for k in c.principal().calendars():
        if not url or str(k.url) == url:
            return k
    raise ErroAgenda("Calendário não encontrado; escolha outro em Configurações.")


def _ical(uid, titulo, inicio, fim, local, descricao, dia_todo):
    ic = ICal()
    ic.add("prodid", "-//ERP Plasti Manaus//Secretaria//PT")
    ic.add("version", "2.0")
    ev = IEvent()
    ev.add("uid", uid)
    ev.add("summary", titulo)
    ev.add("dtstamp", timezone.now())
    if dia_todo:
        ev.add("dtstart", inicio.date())
        ev.add("dtend", fim.date() + timedelta(days=1))
    else:
        ev.add("dtstart", inicio)
        ev.add("dtend", fim)
    if local:
        ev.add("location", local)
    if descricao:
        ev.add("description", descricao)
    ic.add_component(ev)
    return ic.to_ical().decode()


def criar(perfil, titulo, inicio, fim=None, local="", descricao="", dia_todo=False, calendario=None):
    fim = fim or (inicio + timedelta(hours=1))
    uid = f"{uuid.uuid4()}@erp-secretaria"
    try:
        with _cliente(perfil) as c:
            _calendario(c, perfil, calendario).add_event(_ical(uid, titulo, inicio, fim, local, descricao, dia_todo))
    except ErroAgenda:
        raise
    except Exception as e:
        raise _erro(e) from e
    _limpar_cache(perfil)
    return uid


def _objeto(c, perfil, calendario, uid):
    for k in c.principal().calendars():
        if str(k.url) == calendario:
            return k.event_by_uid(uid)
    raise ErroAgenda("Compromisso não encontrado.")


def editar(perfil, calendario, uid, titulo, inicio, fim, local="", descricao="", dia_todo=False):
    try:
        with _cliente(perfil) as c:
            obj = _objeto(c, perfil, calendario, uid)
            comp = obj.icalendar_component
            if comp.get("rrule"):
                raise ErroAgenda("Compromisso repetitivo: edite pelo iPhone para não alterar a série inteira.")
            obj.data = _ical(uid, titulo, inicio, fim, local, descricao, dia_todo)
            obj.save()
    except ErroAgenda:
        raise
    except Exception as e:
        raise _erro(e) from e
    _limpar_cache(perfil)


def apagar(perfil, calendario, uid):
    try:
        with _cliente(perfil) as c:
            obj = _objeto(c, perfil, calendario, uid)
            if obj.icalendar_component.get("rrule"):
                raise ErroAgenda("Compromisso repetitivo: apague pelo iPhone para escolher se é só este ou a série.")
            obj.delete()
    except ErroAgenda:
        raise
    except Exception as e:
        raise _erro(e) from e
    _limpar_cache(perfil)


# ===================================================================== telas
class EventoForm(forms.Form):
    titulo = forms.CharField(label="Compromisso", max_length=300, widget=forms.TextInput(attrs={"style": "width:100%"}))
    data = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    dia_todo = forms.BooleanField(label="Dia inteiro", required=False)
    hora_inicio = forms.TimeField(label="Início", required=False, widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    hora_fim = forms.TimeField(label="Fim", required=False, widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    local = forms.CharField(required=False, max_length=300)
    descricao = forms.CharField(label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    calendario = forms.ChoiceField(label="Calendário", required=False)

    def clean(self):
        d = super().clean()
        if not d.get("dia_todo") and not d.get("hora_inicio"):
            self.add_error("hora_inicio", "Informe a hora ou marque Dia inteiro.")
        return d

    def datas(self):
        d = self.cleaned_data
        if d["dia_todo"]:
            ini = timezone.make_aware(datetime.combine(d["data"], time.min), _tz())
            return ini, ini, True
        ini = timezone.make_aware(datetime.combine(d["data"], d["hora_inicio"]), _tz())
        fim = timezone.make_aware(datetime.combine(d["data"], d["hora_fim"]), _tz()) if d.get("hora_fim") else ini + timedelta(hours=1)
        if fim <= ini:
            fim = ini + timedelta(hours=1)
        return ini, fim, False


def _mini_calendario(ano, mes, dias_com):
    semanas = cal_mod.Calendar(firstweekday=6).monthdatescalendar(ano, mes)
    hoje = date.today()
    return [[dict(d=d, fora=d.month != mes, hoje=d == hoje, tem=d in dias_com) for d in s] for s in semanas]


@secretaria_obrigatoria
def tela(request):
    from .configuracoes import perfil_de
    perfil = perfil_de(request.user)
    conectado = bool(perfil.icloud_usuario and perfil.icloud_senha_cifrada)
    hoje = timezone.localdate()
    try:
        ref = date.fromisoformat(request.GET["mes"] + "-01") if request.GET.get("mes") else hoje.replace(day=1)
    except ValueError:
        ref = hoje.replace(day=1)
    evs, erro, cals = [], "", []
    if conectado:
        try:
            if request.GET.get("atualizar"):
                _limpar_cache(perfil)
            ini_mes = ref - timedelta(days=7)
            fim_janela = max(hoje + timedelta(days=30), (ref + timedelta(days=42)))
            evs_todos = eventos(perfil, min(ini_mes, hoje), fim_janela)
            cals = calendarios(perfil)
        except ErroAgenda as e:
            erro, evs_todos = str(e), []
        prox = [e for e in evs_todos if e["fim"].date() >= hoje and e["inicio"].date() <= hoje + timedelta(days=30)]
        dias_com = set()
        for e in evs_todos:
            d = e["inicio"].date()
            while d <= e["fim"].date():
                dias_com.add(d)
                d += timedelta(days=1)
        dia_sel = None
        if request.GET.get("dia"):
            try:
                dia_sel = date.fromisoformat(request.GET["dia"])
                prox = [e for e in evs_todos if e["inicio"].date() <= dia_sel <= e["fim"].date()]
            except ValueError:
                pass
        grupos = {}
        for e in prox:
            grupos.setdefault(max(e["inicio"].date(), hoje) if not dia_sel else dia_sel, []).append(e)
        evs = sorted(grupos.items())
    else:
        dias_com, dia_sel = set(), None
    form = EventoForm(initial={"data": request.GET.get("dia") or hoje, "hora_inicio": "09:00", "hora_fim": "10:00"})
    form.fields["calendario"].choices = [(c["url"], c["nome"]) for c in cals]
    form.initial["calendario"] = perfil.agenda_padrao
    mes_ant = (ref - timedelta(days=1)).replace(day=1)
    mes_prox = (ref + timedelta(days=32)).replace(day=1)
    return render(request, "secretaria/agenda.html", dict(
        titulo="Agenda", conectado=conectado, erro=erro, grupos=evs, form=form, ref=ref, hoje=hoje, dia_sel=dia_sel,
        semanas=_mini_calendario(ref.year, ref.month, dias_com), mes_ant=mes_ant.strftime("%Y-%m"), mes_prox=mes_prox.strftime("%Y-%m")))


@secretaria_obrigatoria
def salvar(request):
    from .configuracoes import perfil_de
    perfil = perfil_de(request.user)
    if request.method != "POST":
        return redirect("sec_agenda")
    form = EventoForm(request.POST)
    form.fields["calendario"].choices = [(request.POST.get("calendario", ""), "")]
    if not form.is_valid():
        messages.error(request, "Confira os campos: " + "; ".join(f"{k}: {v[0]}" for k, v in form.errors.items()))
        return redirect("sec_agenda")
    ini, fim, todo = form.datas()
    d = form.cleaned_data
    try:
        if request.POST.get("uid"):
            if request.POST.get("excluir"):
                apagar(perfil, request.POST["cal_origem"], request.POST["uid"])
                messages.success(request, "Compromisso apagado (também some do iPhone).")
            else:
                editar(perfil, request.POST["cal_origem"], request.POST["uid"], d["titulo"], ini, fim, d["local"], d["descricao"], todo)
                messages.success(request, "Compromisso atualizado.")
        else:
            criar(perfil, d["titulo"], ini, fim, d["local"], d["descricao"], todo, d.get("calendario") or None)
            messages.success(request, "Compromisso criado. Em instantes aparece no iPhone.")
    except ErroAgenda as e:
        messages.error(request, str(e))
    return redirect(f"/secretaria/agenda/?dia={ini.date()}")


def resumo_hoje(perfil):
    """Para o Painel e o briefing: compromissos de hoje (sem levantar erro)."""
    if not (perfil.icloud_usuario and perfil.icloud_senha_cifrada):
        return dict(conectado=False, lista=[], erro="")
    hoje = timezone.localdate()
    try:
        evs = [e for e in eventos(perfil, hoje, hoje + timedelta(days=1)) if e["inicio"].date() <= hoje <= e["fim"].date()]
        return dict(conectado=True, lista=evs, erro="")
    except ErroAgenda as e:
        return dict(conectado=True, lista=[], erro=str(e))
