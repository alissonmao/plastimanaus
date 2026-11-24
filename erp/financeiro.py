"""Telas do Financeiro: contas a receber/pagar, inadimplência, fluxo projetado, DRE e extrato."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from . import calculos as C
from . import planilhas as P
from .models import FluxoCaixa
from .views import GRANULARIDADES, _data, js, lista_get

Z = Decimal(0)
FAIXAS_VENCIDO = [(1, 30, "1–30 dias"), (31, 60, "31–60 dias"), (61, 90, "61–90 dias"), (91, 10**6, "Mais de 90 dias")]
FAIXAS_AVENCER = [(0, 0, "Vence hoje"), (1, 7, "1–7 dias"), (8, 30, "8–30 dias"), (31, 60, "31–60 dias"), (61, 10**6, "Mais de 60 dias")]


def _base():
    return FluxoCaixa.objects.filter(Q(data_pagamento__gte=C.DATA_MINIMA_FLUXO) | Q(data_pagamento=None, data_emissao__gte=C.DATA_MINIMA_FLUXO))


def _faixa(dias, faixas):
    for ini, fim, nome in faixas:
        if ini <= dias <= fim:
            return nome
    return faixas[-1][2]


def _status(r, hoje):
    if r.quitado:
        return "quitado"
    if r.saldo_aberto <= 0:
        return "quitado"
    v = r.vencimento
    if v < hoje or (r.situacao or "").startswith("Atrasado"):
        return "atrasado"
    if v == hoje:
        return "hoje"
    return "avencer"


# ===================================================================== Contas a receber / pagar
def contas(request, natureza):
    receber = natureza == "receber"
    hoje = date.today()
    qs = _base().filter(valor_conta__gt=0) if receber else _base().filter(valor_conta__lt=0)
    situacao = request.GET.get("situacao", "aberto")
    busca = request.GET.get("q", "").strip()
    cats, contas_sel = lista_get(request, "categoria"), lista_get(request, "conta")
    venc_de, venc_ate = _data(request.GET.get("de"), None), _data(request.GET.get("ate"), None)
    if busca:
        qs = qs.filter(Q(fornecedor__icontains=busca) | Q(numero_documento__icontains=busca) | Q(cnpj_cpf__icontains=busca))
    if cats:
        qs = qs.filter(categoria__in=cats)
    if contas_sel:
        qs = qs.filter(conta_corrente__in=contas_sel)
    todos = list(qs)
    for r in todos:
        r.st = _status(r, hoje)
        r.dias = (hoje - r.vencimento).days
    if venc_de or venc_ate:
        todos = [r for r in todos if (not venc_de or r.vencimento >= venc_de) and (not venc_ate or r.vencimento <= venc_ate)]
    filtro = {"aberto": lambda r: r.st != "quitado", "atrasado": lambda r: r.st == "atrasado", "hoje": lambda r: r.st == "hoje",
              "avencer": lambda r: r.st == "avencer", "quitado": lambda r: r.st == "quitado", "todos": lambda r: True}[situacao]
    rows = sorted((r for r in todos if filtro(r)), key=lambda r: (r.vencimento, r.fornecedor))
    if request.GET.get("exportar"):
        return P.xlsx_response([{
            "Vencimento": r.vencimento, "Emissão": r.data_emissao, "Pagamento": r.data_pagamento,
            "Cliente/Fornecedor": r.fornecedor, "CNPJ/CPF": r.cnpj_cpf, "Documento": r.numero_documento, "Parcela": r.parcela,
            "Categoria": r.categoria, "Grupo": r.grupo, "Conta": r.conta_corrente, "Situação": r.situacao,
            "Valor": abs(r.valor_conta), "Pago": abs(r.valor_pago), "Em aberto": r.saldo_aberto} for r in rows],
            "contas-a-receber" if receber else "contas-a-pagar")

    abertos = [r for r in todos if r.st != "quitado"]
    k = dict(aberto=sum((r.saldo_aberto for r in abertos), Z),
             atrasado=sum((r.saldo_aberto for r in abertos if r.st == "atrasado"), Z),
             qtd_atrasado=sum(1 for r in abertos if r.st == "atrasado"),
             hoje=sum((r.saldo_aberto for r in abertos if r.st == "hoje"), Z),
             prox7=sum((r.saldo_aberto for r in abertos if r.st == "avencer" and -7 <= r.dias < 0), Z),
             prox30=sum((r.saldo_aberto for r in abertos if r.st == "avencer" and -30 <= r.dias < 0), Z))
    mes_ini = hoje.replace(day=1)
    k["quitado_mes"] = sum((abs(r.valor_pago) for r in todos if r.data_pagamento and r.data_pagamento >= mes_ini), Z)
    k["qtd"] = len(rows)
    k["total_lista"] = sum((r.saldo_aberto if situacao != "quitado" else abs(r.valor_pago) for r in rows), Z)

    aging = defaultdict(lambda: [0, Z])
    for r in abertos:
        if r.st == "atrasado":
            nome = "Vencido " + _faixa(max(r.dias, 1), FAIXAS_VENCIDO)
        else:
            nome = "A vencer: " + _faixa(-r.dias, FAIXAS_AVENCER)
        aging[nome][0] += 1
        aging[nome][1] += r.saldo_aberto
    ordem = ["Vencido " + f[2] for f in reversed(FAIXAS_VENCIDO)] + ["A vencer: " + f[2] for f in FAIXAS_AVENCER]
    aging = [(n, *aging[n]) for n in ordem if n in aging]

    por_pessoa = defaultdict(lambda: [Z, Z, 0])
    for r in abertos:
        p = por_pessoa[r.fornecedor]
        p[0] += r.saldo_aberto
        p[2] += 1
        if r.st == "atrasado":
            p[1] += r.saldo_aberto
    top = sorted(por_pessoa.items(), key=lambda x: -x[1][0])[:15]

    # Vencimentos nos próximos 60 dias (por semana)
    sem = defaultdict(lambda: Z)
    for r in abertos:
        if r.st != "atrasado" and r.vencimento <= hoje + timedelta(days=60):
            sem[C.chave_periodo(r.vencimento, "semana")] += r.saldo_aberto
    chaves = sorted(sem)

    ctx = dict(titulo="Contas a receber" if receber else "Contas a pagar", receber=receber, k=k, rows=rows[:500],
               truncado=len(rows) > 500, situacao=situacao, q=busca, de=venc_de, ate=venc_ate, cats=cats, contas_sel=contas_sel,
               op_categorias=sorted({r.categoria for r in todos}), op_contas=sorted({r.conta_corrente for r in todos if r.conta_corrente}),
               aging=aging, top=top, hoje=hoje,
               sem_vencimento=not any(r.data_vencimento for r in todos),
               graf=js(dict(aging=dict(labels=[a[0] for a in aging], valores=[float(a[2]) for a in aging]),
                            semanas=dict(labels=[C.rotulo_periodo(c, "semana") for c in chaves], valores=[float(sem[c]) for c in chaves]))))
    return render(request, "erp/fin_contas.html", ctx)


def receber(request):
    return contas(request, "receber")


def pagar(request):
    return contas(request, "pagar")


def titulo(request, pk):
    r = get_object_or_404(FluxoCaixa, pk=pk)
    r.st = _status(r, date.today())
    outros = FluxoCaixa.objects.filter(fornecedor=r.fornecedor).exclude(pk=r.pk).order_by("-data_emissao")[:30]
    return render(request, "erp/fin_titulo.html", dict(titulo="Título", r=r, outros=outros))


def atrasados(request):
    """Inadimplência: títulos a receber vencidos por cliente e por faixa de atraso."""
    hoje = date.today()
    rows = [r for r in _base().filter(valor_conta__gt=0) if _status(r, hoje) == "atrasado"]
    for r in rows:
        r.dias = (hoje - r.vencimento).days
    por_cli = defaultdict(lambda: dict(valor=Z, qtd=0, mais_antigo=hoje, faixas=defaultdict(lambda: Z), cnpj=""))
    for r in rows:
        c = por_cli[r.fornecedor]
        c["valor"] += r.saldo_aberto
        c["qtd"] += 1
        c["mais_antigo"] = min(c["mais_antigo"], r.vencimento)
        c["faixas"][_faixa(max(r.dias, 1), FAIXAS_VENCIDO)] += r.saldo_aberto
        c["cnpj"] = r.cnpj_cpf or c["cnpj"]
    clientes = sorted(por_cli.items(), key=lambda x: -x[1]["valor"])
    total = sum((c["valor"] for _, c in clientes), Z)
    faixas = [f[2] for f in FAIXAS_VENCIDO]
    tot_faixa = {f: sum((c["faixas"][f] for _, c in clientes), Z) for f in faixas}
    # Taxa de inadimplência: vencido ÷ total a receber com vencimento até hoje (no ano)
    vencidos_total = sum((abs(r.valor_conta) for r in _base().filter(valor_conta__gt=0) if r.vencimento <= hoje), Z)
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Cliente": n, "CNPJ/CPF": c["cnpj"], "Títulos": c["qtd"], "Vencido": c["valor"],
                                 "Mais antigo": c["mais_antigo"], **{f: c["faixas"][f] for f in faixas}} for n, c in clientes],
                               "inadimplencia")
    return render(request, "erp/fin_atrasados.html", dict(
        titulo="Inadimplência", clientes=clientes, total=total, qtd=len(rows), faixas=faixas, tot_faixa=tot_faixa,
        taxa=(total / vencidos_total) if vencidos_total else None, hoje=hoje,
        graf=js(dict(labels=faixas, valores=[float(tot_faixa[f]) for f in faixas]))))


# ===================================================================== Fluxo de caixa projetado
def fluxo_projetado(request):
    hoje = date.today()
    g = request.GET.get("g", "semana")
    de = _data(request.GET.get("de"), hoje.replace(day=1) - timedelta(days=60))
    ate = _data(request.GET.get("ate"), hoje + timedelta(days=90))
    contas_sel = lista_get(request, "conta")
    qs = _base()
    if contas_sel:
        qs = qs.filter(conta_corrente__in=contas_sel)
    per = defaultdict(lambda: dict(ent=Z, sai=Z, ent_prev=Z, sai_prev=Z, atraso_rec=Z, atraso_pag=Z))
    for r in qs:
        if r.data_pagamento and de <= r.data_pagamento <= ate and r.valor_pago:
            e = per[C.chave_periodo(r.data_pagamento, g)]
            if r.valor_pago > 0:
                e["ent"] += r.valor_pago
            else:
                e["sai"] += -r.valor_pago
        aberto = r.saldo_aberto
        if aberto > 0:
            v = r.vencimento
            if v < hoje:  # atrasado: entra como previsto no período atual
                e = per[C.chave_periodo(hoje, g)]
                e["atraso_rec" if r.receber else "atraso_pag"] += aberto
            elif v <= ate:
                e = per[C.chave_periodo(v, g)]
                e["ent_prev" if r.receber else "sai_prev"] += aberto
    chaves = sorted(per)
    acc = Z
    linhas = []
    for c in chaves:
        e = per[c]
        saldo = e["ent"] + e["ent_prev"] - e["sai"] - e["sai_prev"]
        acc += saldo
        linhas.append(dict(chave=c, label=C.rotulo_periodo(c, g), saldo=saldo, acumulado=acc, **e))
    tot = {k: sum((l[k] for l in linhas), Z) for k in ["ent", "sai", "ent_prev", "sai_prev", "atraso_rec", "atraso_pag"]}
    return render(request, "erp/fin_fluxo.html", dict(
        titulo="Fluxo de caixa projetado", linhas=linhas, tot=tot, g=g, granularidades=GRANULARIDADES, de=de, ate=ate,
        contas_sel=contas_sel, op_contas=sorted(set(_base().exclude(conta_corrente=None).values_list("conta_corrente", flat=True))),
        graf=js(dict(labels=[l["label"] for l in linhas],
                     ent=[float(l["ent"]) for l in linhas], sai=[float(-l["sai"]) for l in linhas],
                     ent_prev=[float(l["ent_prev"]) for l in linhas], sai_prev=[float(-l["sai_prev"]) for l in linhas],
                     acumulado=[float(l["acumulado"]) for l in linhas]))))


# ===================================================================== DRE gerencial
def dre(request):
    """Receitas e despesas por grupo/categoria e mês. Caixa = valor pago na data do pagamento;
    competência = valor do título na data de emissão."""
    regime = request.GET.get("regime", "caixa")
    ano = int(request.GET.get("ano") or date.today().year)
    linhas = defaultdict(lambda: defaultdict(lambda: Z))  # (tipo, grupo, categoria) -> mes -> valor
    for r in _base():
        if regime == "caixa":
            d, v = r.data_pagamento, r.valor_pago
        else:
            d, v = r.data_emissao, r.valor_conta
        if not d or d.year != ano or not v:
            continue
        tipo = "Receitas" if r.valor_conta > 0 else "Despesas"
        linhas[(tipo, r.grupo or "(sem grupo)", r.categoria or "(sem)")][d.month] += v
    meses = sorted({m for v in linhas.values() for m in v})
    estrutura = []
    resultado = defaultdict(lambda: Z)
    for tipo in ["Receitas", "Despesas"]:
        grupos = defaultdict(list)
        for (t, g, c), vals in linhas.items():
            if t == tipo:
                grupos[g].append((c, vals))
        tot_tipo = defaultdict(lambda: Z)
        blocos = []
        for g, cats in grupos.items():
            tot_g = defaultdict(lambda: Z)
            for _, vals in cats:
                for m, v in vals.items():
                    tot_g[m] += v
            cats_fmt = sorted(([c, [vals.get(m, Z) for m in meses], sum(vals.values(), Z)] for c, vals in cats), key=lambda x: abs(x[2]), reverse=True)
            blocos.append([g, [tot_g.get(m, Z) for m in meses], sum(tot_g.values(), Z), cats_fmt])
            for m, v in tot_g.items():
                tot_tipo[m] += v
        blocos.sort(key=lambda b: abs(b[2]), reverse=True)
        for m, v in tot_tipo.items():
            resultado[m] += v
        estrutura.append(dict(tipo=tipo, blocos=blocos, totais=[tot_tipo.get(m, Z) for m in meses], total=sum(tot_tipo.values(), Z)))
    res = [resultado.get(m, Z) for m in meses]
    rec = estrutura[0]["totais"]
    margem = [(r / x) if x else None for r, x in zip(res, rec)]
    anos = sorted({d.year for d in _base().exclude(data_pagamento=None).values_list("data_pagamento", flat=True)} | {date.today().year})
    return render(request, "erp/fin_dre.html", dict(
        titulo="DRE gerencial", estrutura=estrutura, meses=[C.MESES[m - 1] for m in meses], res=res, res_total=sum(res, Z),
        margem=margem, regime=regime, ano=ano, anos=anos,
        graf=js(dict(labels=[C.MESES[m - 1] for m in meses], rec=[float(x) for x in rec],
                     desp=[float(x) for x in estrutura[1]["totais"]], res=[float(x) for x in res]))))


# ===================================================================== Extrato por conta corrente
def extrato(request):
    hoje = date.today()
    de = _data(request.GET.get("de"), hoje.replace(day=1))
    ate = _data(request.GET.get("ate"), hoje)
    conta = request.GET.get("conta", "")
    base = _base().exclude(data_pagamento=None).exclude(valor_pago=0)
    contas = sorted(set(base.exclude(conta_corrente=None).values_list("conta_corrente", flat=True)))
    resumo = []
    for c in contas:
        q = [r for r in base.filter(conta_corrente=c, data_pagamento__range=(de, ate))]
        ent = sum((r.valor_pago for r in q if r.valor_pago > 0), Z)
        sai = sum((-r.valor_pago for r in q if r.valor_pago < 0), Z)
        resumo.append(dict(conta=c, ent=ent, sai=sai, saldo=ent - sai, qtd=len(q)))
    movs = []
    if conta:
        acc = Z
        for r in base.filter(conta_corrente=conta, data_pagamento__range=(de, ate)).order_by("data_pagamento", "valor_pago"):
            acc += r.valor_pago
            movs.append((r, acc))
        if request.GET.get("exportar"):
            return P.xlsx_response([{"Data": r.data_pagamento, "Cliente/Fornecedor": r.fornecedor, "Categoria": r.categoria,
                                     "Documento": r.numero_documento, "Valor": r.valor_pago, "Acumulado": a} for r, a in movs],
                                   f"extrato-{conta}")
    return render(request, "erp/fin_extrato.html", dict(
        titulo="Extrato por conta", resumo=resumo, contas=contas, conta=conta, movs=movs, de=de, ate=ate,
        tot=dict(ent=sum((x["ent"] for x in resumo), Z), sai=sum((x["sai"] for x in resumo), Z))))
