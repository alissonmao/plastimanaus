"""Secretaria → Angel: conversa por voz no site, voz (TTS), briefing e histórico de avisos."""
import hashlib
import json

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import briefing as B
from . import cerebro, config, ia, servicos
from .acesso import secretaria_obrigatoria
from .models import Notificacao


def _json(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


@secretaria_obrigatoria
def tela(request):
    from .configuracoes import perfil_de
    if request.method == "POST" and request.POST.get("teste"):
        perfil = perfil_de(request.user)
        if not perfil.whatsapp:
            messages.error(request, "Cadastre seu WhatsApp em Secretaria → Configurações.")
        else:
            from django.utils import timezone
            Notificacao.objects.create(usuario=request.user, tipo="teste", chave=f"teste-{timezone.now().timestamp()}",
                                       texto="Oi! Aqui é a Angel. Se você recebeu esta mensagem, os avisos pelo WhatsApp estão funcionando. 👋")
            messages.success(request, "Mensagem de teste na fila. Chega em até 1 minuto se o WhatsApp do Angel estiver conectado.")
        return redirect("sec_angel")
    return render(request, "secretaria/angel.html", dict(
        titulo="Angel", ia=ia.disponivel(), voz_eleven=bool(config.obter("ELEVENLABS_API_KEY") and config.obter("ELEVENLABS_VOICE_ID")),
        whatsapp=servicos.whatsapp_disponivel(), perfil=perfil_de(request.user), numero=config.obter("ANGEL_WHATSAPP"),
        avisos=Notificacao.objects.filter(usuario=request.user)[:30], ui_url=getattr(settings, "OPENCLAW_UI_URL", "")))


@secretaria_obrigatoria
@require_POST
def conversar(request):
    d = _json(request)
    texto = (d.get("texto") or "").strip()[:2000]
    if not texto:
        return JsonResponse({"erro": "Não ouvi nada."}, status=400)
    resp = cerebro.conversar(request.user, texto, d.get("historico") or [], canal="site", voz=True)
    return JsonResponse({"resposta": resp})


@secretaria_obrigatoria
@require_POST
def audio(request):
    texto = (_json(request).get("texto") or "").strip()[:3000]
    if not texto:
        return HttpResponse(status=400)
    chave = "sec-tts-" + hashlib.sha256(texto.encode()).hexdigest()
    mp3 = cache.get(chave)
    if mp3 is None:
        try:
            mp3, _ = servicos.falar(texto)
        except servicos.ErroServico:
            return HttpResponse(status=503)  # o navegador usa a voz dele como último recurso
        cache.set(chave, mp3, 3600)
    r = HttpResponse(mp3, content_type="audio/mpeg")
    r["Cache-Control"] = "private, max-age=3600"
    return r


@secretaria_obrigatoria
def briefing(request):
    return JsonResponse({"texto": B.falado(request.user)})


@secretaria_obrigatoria
def avisos(request):
    return redirect("sec_angel")
