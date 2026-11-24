"""Painel do dia: e-mails por empresa e prioridade, lembretes, agenda de hoje e pendências do diário.

A prioridade vem da triagem por IA; sem ela (ou antes de rodar), das palavras-chave no assunto e no remetente.
"""
from datetime import datetime

from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils import timezone

from erp.calculos import sem_acento

from . import correio as M
from .acesso import secretaria_obrigatoria, tem_secretaria
from .models import ContaEmail

DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

CATEGORIAS = [  # (chave, ícone, título)
    ("critico", "🔴", "Crítico / ação imediata"),
    ("financeiro", "💰", "Financeiro"),
    ("responder", "✉️", "Aguardando resposta"),
    ("outros", "📨", "Outros"),
]
PALAVRAS = {
    "critico": ["urgente", "sentenca", "processo n", "intimacao", "citacao", "prazo", "audiencia", "notificacao extrajudicial",
                "bloqueio", "protesto", "penhora", "mandado", "embargo", "liminar", "acao judicial", "multa", "auto de infracao"],
    "financeiro": ["boleto", "nf-e", "nfs-e", "nfe", "nota fiscal", "fatura", "pagamento", "cobranca", "pix", "comprovante",
                   "duplicata", "transferencia", "extrato", "recibo", "vencimento", "remessa", "titulo", "orcamento", "pedido"],
    "propaganda": ["newsletter", "promocao", "oferta", "desconto", "black friday", "webinar", "cupom", "liquidacao",
                   "aproveite", "ultimas vagas", "frete gratis", "% off"],
}
REMETENTE_AUTOMATICO = ["noreply", "no-reply", "naoresponda", "nao-responda", "nao_responda", "mailer", "news", "marketing",
                        "mkt", "info@", "contato@", "notificacao", "notification", "bounce"]
CACHE_SEG = 180


def classificar(r):
    texto = sem_acento(f"{r.assunto} {r.de_nome}").lower()
    remetente = (r.de_email or "").lower()
    automatico = any(p in remetente for p in REMETENTE_AUTOMATICO)
    if any(p in texto for p in PALAVRAS["critico"]):
        return "critico"
    if any(p in texto for p in PALAVRAS["financeiro"]):
        return "financeiro"
    if any(p in texto for p in PALAVRAS["propaganda"]) or automatico:
        return "propaganda"
    if not r.respondido:
        return "responder"
    return "outros"


def _coletar(usuario, contas):
    from .triagem import categorias_do_painel
    empresas, erros, nao_lidos = {}, [], 0
    por_ia = categorias_do_painel(usuario)
    for c in contas:
        try:
            with M.Caixa(c) as cx:
                itens = cx.recentes(dias=2)
                n = cx.nao_lidos("INBOX")
                cache.set(f"sec-naolidos-{c.pk}", n, 60)
                nao_lidos += n
        except M.ErroCorreio as e:
            erros.append(f"{c.empresa}: {e}")
            continue
        emp = empresas.setdefault(c.empresa, dict(nome=c.empresa, cats={k: [] for k, *_ in CATEGORIAS}, propaganda=[]))
        for r in itens:
            k = por_ia.get((str(c.pk), str(r.uid))) or classificar(r)
            item = dict(conta=str(c.pk), uid=r.uid, assunto=r.assunto, de=r.de_nome, de_email=r.de_email,
                        data=r.data, lido=r.lido, empresa=c.empresa)
            (emp["propaganda"] if k == "propaganda" else emp["cats"][k]).append(item)
    return dict(empresas=list(empresas.values()), erros=erros, nao_lidos=nao_lidos, lido_em=timezone.now())


@secretaria_obrigatoria
def painel(request):
    contas = list(ContaEmail.objects.filter(usuario=request.user, ativa=True))
    chave = f"sec-painel-{request.user.pk}"
    dados = None if request.GET.get("atualizar") else cache.get(chave)
    if dados is None:
        dados = _coletar(request.user, contas)
        cache.set(chave, dados, CACHE_SEG)
        if request.GET.get("atualizar"):
            return redirect("sec_painel")
    agora = timezone.localtime()
    saud = "Bom dia" if agora.hour < 12 else ("Boa tarde" if agora.hour < 18 else "Boa noite")
    tot = {k: 0 for k, *_ in CATEGORIAS}
    for e in dados["empresas"]:
        e["grupos"] = [dict(chave=k, icone=i, titulo=t, itens=e["cats"][k]) for k, i, t in CATEGORIAS if e["cats"][k]]
        for k in tot:
            tot[k] += len(e["cats"][k])
        e["sigla"] = "".join(p[0] for p in e["nome"].split()[:2]).upper()
    from . import agenda, diario, lembretes
    from .configuracoes import perfil_de
    perfil = perfil_de(request.user)
    return render(request, "secretaria/painel.html", dict(
        lemb=lembretes.resumo(request.user), ag=agenda.resumo_hoje(perfil), pendencias=diario.pendencias(request.user, 5),
        titulo="Painel", saudacao=f"{saud}, {request.user.first_name or request.user.username}",
        data_extenso=f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}",
        tot=tot, sem_contas=not contas, **dados))


def inicio(request):
    """Para onde o usuário vai depois do login."""
    return redirect("sec_painel" if tem_secretaria(request.user) else "dashboard")
