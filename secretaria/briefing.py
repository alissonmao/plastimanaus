"""Briefing da manhã: compromissos, lembretes, e-mails importantes e pendências do diário."""
from datetime import timedelta

from django.utils import timezone

from . import ia

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def dados(usuario):
    from . import agenda, diario, lembretes
    from .configuracoes import perfil_de
    from .triagem import importantes
    perfil = perfil_de(usuario)
    ag = agenda.resumo_hoje(perfil)
    lb = lembretes.resumo(usuario)
    try:
        emails = importantes(usuario, dias=1)
    except Exception:
        emails = []
    return dict(agenda=ag, lembretes=lb, emails=emails, pendencias=diario.pendencias(usuario, 5))


def montar(usuario, d=None):
    """Texto simples (sem IA) — serve de base e de reserva."""
    d = d or dados(usuario)
    agora = timezone.localtime()
    nome = usuario.first_name or usuario.username
    saud = "Bom dia" if agora.hour < 12 else ("Boa tarde" if agora.hour < 18 else "Boa noite")
    p = [f"{saud}, {nome}! Hoje é {DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}."]
    evs = d["agenda"]["lista"]
    if evs:
        p.append(f"Você tem {len(evs)} compromisso{'s' if len(evs) > 1 else ''} hoje: " + "; ".join(
            ("o dia todo: " if e["dia_todo"] else f"às {timezone.localtime(e['inicio']):%H:%M}, ") + e["titulo"] for e in evs[:8]) + ".")
    elif d["agenda"]["conectado"]:
        p.append("Nenhum compromisso na agenda hoje.")
    lb = d["lembretes"]
    if lb["lista"]:
        txt = []
        if lb["atrasados"]:
            txt.append(f"{lb['atrasados']} lembrete{'s' if lb['atrasados'] > 1 else ''} atrasado{'s' if lb['atrasados'] > 1 else ''}")
        hoje = [l for l in lb["lista"] if l.hoje]
        if hoje:
            txt.append("para hoje: " + "; ".join(f"{l.titulo} às {timezone.localtime(l.quando):%H:%M}" for l in hoje[:6]))
        p.append("Lembretes: " + ", ".join(txt) + ".")
    em = d["emails"]
    if em:
        crit = [e for e in em if e.get("categoria") in ("critico", "Crítico")]
        p.append(f"E-mails importantes: {len(em)}" + (f", sendo {len(crit)} crítico{'s' if len(crit) > 1 else ''}" if crit else "") + ". "
                 + "; ".join(f"{e['empresa']}: {e['assunto'][:70]}" for e in em[:4]) + ".")
    if d["pendencias"]:
        p.append("No diário, em aberto: " + "; ".join((r.resumo or r.texto[:80]) for r in d["pendencias"][:3]) + ".")
    if len(p) == 1:
        p.append("Nada pendente por enquanto. Bom trabalho!")
    return "\n".join(p)


def falado(usuario):
    """Versão para ouvir: a IA deixa o texto natural (se houver chave)."""
    base = montar(usuario)
    if not ia.disponivel():
        return base
    try:
        return ia.texto_ia("Você é a Angel, secretaria executiva. Reescreva o briefing abaixo para ser falado em voz alta, em português do Brasil: "
                           "natural, caloroso e objetivo, no máximo 120 palavras, sem listas, sem emojis, sem markdown. Não acrescente fatos.",
                           base, 800)
    except ia.ErroIA:
        return base
