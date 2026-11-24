"""API interna usada pelo Angel (OpenClaw, no mesmo servidor). Autenticação por token (Sistema → Integrações → Token do Angel).

O Angel só atende o número cadastrado em Secretaria → Configurações (com ou sem o nono dígito).
Nada aqui apaga coisas ou envia e-mail."""
import base64
import hmac
import logging
import os
import tempfile

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import config

log = logging.getLogger(__name__)


def _token_ok(request):
    esperado = config.obter("ANGEL_TOKEN")
    recebido = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(esperado) and hmac.compare_digest(esperado, recebido)


def usuario_do_numero(numero: str):
    from .models import PerfilSecretaria
    d = "".join(ch for ch in (numero or "") if ch.isdigit())
    if not d:
        return None
    alvo = "+" + d
    for p in PerfilSecretaria.objects.exclude(whatsapp="").select_related("usuario"):
        if alvo in p.whatsapp_variantes() and p.usuario.is_active:
            from .acesso import tem_secretaria
            return p.usuario if tem_secretaria(p.usuario) else None
    return None


@csrf_exempt
@require_POST
def api(request, acao):
    if not _token_ok(request):
        return JsonResponse({"erro": "não autorizado"}, status=401)
    import json
    try:
        d = json.loads(request.body or b"{}") if request.content_type == "application/json" else request.POST.dict()
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    u = usuario_do_numero(d.get("de", ""))
    if not u:
        log.info("Angel: mensagem de número não autorizado ignorada.")
        return JsonResponse({"ignorar": True, "motivo": "número não autorizado"}, status=403)

    if acao == "mensagem":
        from . import cerebro, servicos
        texto = (d.get("texto") or "").strip()
        veio_audio = False
        arquivo = request.FILES.get("audio")
        caminho = d.get("audio_arquivo")
        if arquivo or caminho or d.get("audio_base64"):
            from . import transcricao
            tmp = None
            try:
                if arquivo or d.get("audio_base64"):
                    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
                    tmp.write(arquivo.read() if arquivo else base64.b64decode(d["audio_base64"]))
                    tmp.close()
                    caminho = tmp.name
                texto = (texto + " " + transcricao.transcrever(caminho)).strip()
                veio_audio = True
            except transcricao.ErroTranscricao as e:
                return JsonResponse({"resposta": f"Recebi seu áudio, mas não consegui ouvir: {e}"})
            finally:
                if tmp:
                    os.unlink(tmp.name)
        if not texto:
            return JsonResponse({"resposta": "Não entendi. Pode repetir?"})
        resp = cerebro.conversar(u, texto, d.get("historico") or [], canal="whatsapp", voz=veio_audio)
        out = {"resposta": resp, "transcricao": texto if veio_audio else ""}
        if veio_audio:  # áudio pede resposta em áudio, com a mesma voz
            try:
                mp3, prov = servicos.falar(resp)
                f = tempfile.NamedTemporaryFile(prefix="angel-", suffix=".mp3", delete=False, dir=_pasta_audio())
                f.write(mp3)
                f.close()
                out.update(audio_arquivo=f.name, voz=prov)
            except servicos.ErroServico:
                pass
        return JsonResponse(out)
    if acao == "briefing":
        from .briefing import montar
        return JsonResponse({"resposta": montar(u)})
    return JsonResponse({"erro": "ação desconhecida"}, status=404)


def _pasta_audio():
    p = os.path.join(tempfile.gettempdir(), "angel-audio")
    os.makedirs(p, exist_ok=True)
    return p
