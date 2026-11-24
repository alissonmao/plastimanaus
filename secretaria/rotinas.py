"""Rotinas da Secretaria (rodam a cada minuto pelo timer do servidor):
lembretes na hora, aviso 1h antes dos compromissos, triagem de e-mail (8h–18h), briefing da manhã,
análise semanal (segunda 8h) e envio da fila de avisos pelo WhatsApp do Angel."""
import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import EstadoTriagem, Lembrete, Notificacao

log = logging.getLogger(__name__)
VALIDADE = timedelta(hours=2)   # aviso não enviado em 2h expira (não chega uma enxurrada atrasada)


def usuarios():
    from .acesso import tem_secretaria
    return [u for u in get_user_model().objects.filter(is_active=True) if tem_secretaria(u)]


def avisar(usuario, tipo, chave, texto, audio=False):
    obj, criado = Notificacao.objects.get_or_create(usuario=usuario, chave=chave[:200], defaults=dict(tipo=tipo, texto=texto, audio=audio))
    return obj if criado else None


def lembretes_na_hora(agora):
    for l in Lembrete.objects.filter(concluido_em=None, avisado_em=None, quando__lte=agora).select_related("usuario"):
        perfil = getattr(l.usuario, "perfil_secretaria", None)
        if agora - l.quando < VALIDADE and perfil and perfil.avisos_whatsapp:
            txt = f"⏰ *Lembrete:* {l.titulo}" + (f"\n{l.notas}" if l.notas else "") + f"\n({timezone.localtime(l.quando):%d/%m %H:%M})"
            avisar(l.usuario, "lembrete", f"lemb-{l.pk}-{l.quando:%Y%m%d%H%M}", txt)
        l.avisado_em = agora
        l.save(update_fields=["avisado_em"])


def agenda_uma_hora_antes(usuario, perfil, agora):
    from . import agenda
    if not (perfil.avisos_whatsapp and perfil.icloud_usuario and perfil.icloud_senha_cifrada):
        return
    hoje = timezone.localdate()
    try:
        evs = agenda.eventos(perfil, hoje, hoje + timedelta(days=1))
    except agenda.ErroAgenda as e:
        log.info("Agenda de %s indisponível: %s", usuario, e)
        return
    for e in evs:
        if e["dia_todo"] or not (agora < e["inicio"] <= agora + timedelta(minutes=60)):
            continue
        falta = int((e["inicio"] - agora).total_seconds() // 60)
        txt = f"📅 Em {falta} min: *{e['titulo']}* às {timezone.localtime(e['inicio']):%H:%M}" + (f"\n📍 {e['local']}" if e["local"] else "")
        avisar(usuario, "agenda", f"ag-{e['uid']}-{e['inicio']:%Y%m%d%H%M}", txt)


def triagem_da_hora(usuario, perfil, agora):
    from . import triagem
    from .models import ContaEmail
    local = timezone.localtime(agora)
    if not perfil.triagem_ativa or not (8 <= local.hour <= 18) or local.weekday() == 6:
        return
    inicio_hora = local.replace(minute=0, second=0, microsecond=0)
    contas = ContaEmail.objects.filter(usuario=usuario, ativa=True)
    if not contas.exists():
        return
    feitas = EstadoTriagem.objects.filter(conta__in=contas, executado_em__gte=inicio_hora).count()
    if feitas >= contas.count():
        return
    triagem.rodar(usuario, avisar=perfil.avisos_whatsapp)


def briefing_da_manha(usuario, perfil, agora):
    from . import briefing
    local = timezone.localtime(agora)
    hora = perfil.briefing_hora
    if isinstance(hora, str):
        hora = datetime.strptime(hora, "%H:%M").time()
    alvo = local.replace(hour=hora.hour, minute=hora.minute, second=0, microsecond=0)
    if not perfil.briefing_ativo or not (alvo <= local < alvo + timedelta(hours=2)):
        return
    chave = f"briefing-{local:%Y%m%d}"
    if Notificacao.objects.filter(usuario=usuario, chave=chave).exists():
        return
    avisar(usuario, "briefing", chave, "☀️ *Briefing da manhã*\n" + briefing.montar(usuario), audio=True)


def analise_da_semana(usuario, perfil, agora):
    from . import diario, ia
    local = timezone.localtime(agora)
    if not perfil.analise_semanal or local.weekday() != 0 or local.hour < 8 or not ia.disponivel():
        return
    inicio = local.date() - timedelta(days=7)
    chave = f"analise-{inicio:%Y%m%d}"
    if Notificacao.objects.filter(usuario=usuario, chave=chave).exists():
        return
    try:
        obj = diario.gerar_analise(usuario, inicio)
    except ia.ErroIA as e:
        log.warning("Análise semanal falhou: %s", e)
        return
    avisar(usuario, "analise", chave, f"📓 *Análise da semana* ({inicio:%d/%m} a {inicio + timedelta(days=6):%d/%m})\n\n" + obj.texto
           if obj else "📓 Semana sem registros no diário.")


def enviar_fila(agora):
    from . import briefing, servicos
    canal = servicos.whatsapp_disponivel()
    for n in Notificacao.objects.filter(situacao="pendente").select_related("usuario").order_by("criada_em"):
        if agora - n.criada_em > VALIDADE:
            n.situacao = "expirada"
            n.save(update_fields=["situacao"])
            continue
        perfil = getattr(n.usuario, "perfil_secretaria", None)
        if not perfil or not perfil.whatsapp:
            n.situacao = "sem_canal"
            n.save(update_fields=["situacao"])
            continue
        if not canal:
            continue   # fica na fila até o Angel conectar (ou expirar)
        try:
            mp3 = None
            if n.audio:
                try:
                    mp3, _ = servicos.falar(briefing.falado(n.usuario) if n.tipo == "briefing" else n.texto)
                except servicos.ErroServico:
                    mp3 = None
            servicos.enviar_whatsapp(perfil.whatsapp_e164, n.texto, mp3)
            n.situacao, n.enviada_em, n.erro = "enviada", timezone.now(), ""
        except servicos.ErroServico as e:
            n.situacao, n.erro = "erro", str(e)[:500]
        n.save()


def rodar(agora=None, so=None):
    agora = agora or timezone.now()
    passos = []

    def passo(nome, f, *a):
        if so and nome not in so:
            return
        try:
            f(*a)
            passos.append(nome)
        except Exception:
            log.exception("Rotina %s falhou", nome)

    from .configuracoes import perfil_de
    passo("lembretes", lembretes_na_hora, agora)
    for u in usuarios():
        perfil = perfil_de(u)
        if timezone.localtime(agora).minute % 5 == 0 or so:
            passo("agenda", agenda_uma_hora_antes, u, perfil, agora)
        passo("briefing", briefing_da_manha, u, perfil, agora)
        passo("analise", analise_da_semana, u, perfil, agora)
    passo("enviar", enviar_fila, agora)
    for u in usuarios():  # a triagem é a mais lenta: por último
        passo("triagem", triagem_da_hora, u, perfil_de(u), agora)
    passo("enviar", enviar_fila, timezone.now())
    return passos
