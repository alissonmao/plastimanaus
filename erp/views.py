import json
from collections import defaultdict
from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Min
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from . import calculos as C
from . import planilhas as P
from .models import (Apontamento, Cliente, Cor, FluxoCaixa, Maquina, MetaVendedor, OrdemProducao, Produto,
                     Setor, TipoSacola, Turno, Venda, VendaPlasti)
from .cadastros import CADASTROS

GRANULARIDADES = [("dia", "Dia"), ("semana", "Semana"), ("mes", "Mês"), ("trimestre", "Trimestre"), ("ano", "Ano")]


def _data(s, padrao):
    try:
        return date.fromisoformat(s) if s else padrao
    except ValueError:
        return padrao


def periodo(request, modelo, campo, padrao_dias=None):
    """Lê ?de=&ate=; sem filtro usa o intervalo dos dados (ou os últimos N dias)."""
    agg = modelo.objects.aggregate(mn=Min(campo), mx=Max(campo))
    hoje = date.today()
    fim_padrao = agg["mx"] or hoje
    ini_padrao = (fim_padrao - timedelta(days=padrao_dias)) if padrao_dias else (agg["mn"] or hoje.replace(day=1))
    de = _data(request.GET.get("de"), ini_padrao)
    ate = _data(request.GET.get("ate"), fim_padrao)
    if de > ate:
        de, ate = ate, de
    return de, ate


def lista_get(request, nome):
    return [v for v in request.GET.getlist(nome) if v]


def js(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)


# ===================================================================== Produção
def _lookups():
    return dict(turnos=list(Turno.objects.all()),
                maquinas=list(Maquina.objects.select_related("familia__setor")),
                produtos=list(Produto.objects.all()), cores=list(Cor.objects.all()),
                tipos=list(TipoSacola.objects.all()))


def _op_cliente():
    return {o.numero.strip(): o.cliente.nome for o in OrdemProducao.objects.select_related("cliente")}


def _linhas_producao(request, padrao_dias=6):
    de, ate = periodo(request, Apontamento, "data", padrao_dias)
    qs = (Apontamento.objects.filter(data__range=(de, ate))
          .select_related("turno", "maquina__familia__setor", "produto", "cor", "tipo_sacola"))
    setores = lista_get(request, "setor")
    maquinas = lista_get(request, "maquina")
    turnos = lista_get(request, "turno")
    produtos = lista_get(request, "produto")
    if setores:
        qs = qs.filter(maquina__familia__setor_id__in=setores)
    if maquinas:
        qs = qs.filter(maquina_id__in=maquinas)
    if turnos:
        qs = qs.filter(turno_id__in=turnos)
    if produtos:
        qs = qs.filter(produto_id__in=produtos)
    linhas = C.enriquecer(qs, _op_cliente())
    filtros = dict(de=de, ate=ate, setores=setores, maquinas=maquinas, turnos=turnos, produtos=produtos,
                   op_setores=Setor.objects.filter(ativo=True), op_maquinas=Maquina.objects.filter(ativo=True),
                   op_turnos=Turno.objects.filter(ativo=True), op_produtos=Produto.objects.filter(ativo=True))
    return linhas, filtros


def dashboard(request):
    linhas, filtros = _linhas_producao(request)
    tot = C.totalizar(linhas)
    util = C.utilizacao_capacidade(linhas)

    # Produção diária por setor (kg OK)
    datas = sorted({l.a.data for l in linhas})
    setores = C.ordenar_setores({l.setor for l in linhas})
    por_dia_setor = defaultdict(float)
    for l in linhas:
        por_dia_setor[(l.a.data, l.setor)] += l.ok
    serie_setor = dict(labels=[f"{d:%d/%m} {C.DIAS_SEMANA[d.weekday()]}" for d in datas],
                       series=[dict(nome=s, valores=[round(por_dia_setor[(d, s)], 2) for d in datas]) for s in setores])

    # Perdas por tipo
    perdas = dict(labels=["Apara", "Alça", "Borra"], valores=[round(tot["apara"], 2), round(tot["alca"], 2), round(tot["borra"], 2)])

    def rosca(chave):
        g = sorted(C.agrupar(linhas, chave), key=lambda x: -x["ok"])
        return dict(labels=[x["grupo"] for x in g], valores=[round(x["ok"], 2) for x in g])

    por_maquina = sorted(C.agrupar(linhas, lambda l: l.maquina), key=lambda x: -x["total"])
    ctx = dict(
        titulo="Chão de Fábrica — Produção", filtros=filtros, tot=tot, util=util, por_maquina=por_maquina,
        graf=js(dict(setor=serie_setor, perdas=perdas, produto=rosca(lambda l: l.produto), cor=rosca(lambda l: l.cor),
                     tipo=rosca(lambda l: l.tipo if l.produto in ("Sacola", "Saco") else ""),
                     util=dict(labels=[m["maquina"] for m in util["maquinas"]],
                               valores=[round((m["util"] or 0) * 100, 1) for m in util["maquinas"]]))),
    )
    return render(request, "erp/dashboard.html", ctx)


class ApontamentoForm(forms.ModelForm):
    class Meta:
        model = Apontamento
        exclude = ["created_by"]
        widgets = {"data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "observacao": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["maquina"].queryset = Maquina.objects.filter(ativo=True)
        self.fields["turno"].queryset = Turno.objects.filter(ativo=True)


def apontamentos(request):
    linhas, filtros = _linhas_producao(request)
    if request.GET.get("exportar"):
        return P.xlsx_response([_exportar_ap(l) for l in linhas], "apontamentos")
    return render(request, "erp/apontamentos.html", dict(
        titulo="Apontamentos", linhas=list(reversed(linhas)), tot=C.totalizar(linhas), filtros=filtros))


def _exportar_ap(r):
    pct = lambda n: (n / r.total) if r.total else None  # noqa: E731
    a = r.a
    return {"Data": a.data, "Dia Semana": C.DIAS_SEMANA[a.data.weekday()], "Turno": r.turno, "Setor": r.setor,
            "Família": r.familia, "Código máquina": r.maquina_codigo, "Máquina": r.maquina, "Produto": r.produto,
            "Cor": r.cor, "Tipo": r.tipo, "Largura mm": a.largura_mm, "Comprimento mm": a.comprimento_mm,
            "Espessura mm": a.espessura_mm, "OP": a.op or "", "Cliente": r.cliente, "Produzido OK kg": r.ok,
            "Apara kg": r.apara, "Alça kg": r.alca, "Borra kg": r.borra, "Total perdas kg": r.perdas,
            "Total geral kg": r.total, "KG por milheiro": r.kg_milheiro, "Qtd milheiro": a.qtd_milheiro,
            "%OK": pct(r.ok), "%Perdas": pct(r.perdas), "Cap. kg/h": r.cap, "Horas disp.": r.horas_disp,
            "Horas trab.": r.horas_trab, "Utilização %": r.util, "Descrição": r.descricao, "Observação": a.observacao or ""}


def apontamento_form(request, pk=None):
    obj = get_object_or_404(Apontamento, pk=pk) if pk else None
    form = ApontamentoForm(request.POST or None, instance=obj, initial={} if obj else {"data": date.today()})
    if request.method == "POST":
        if "excluir" in request.POST and obj:
            obj.delete()
            messages.success(request, "Apontamento excluído.")
            return redirect("apontamentos")
        if form.is_valid():
            ap = form.save(commit=False)
            if not obj:
                ap.created_by = request.user
            ap.save()
            messages.success(request, "Apontamento salvo.")
            return redirect("apontamentos")
    return render(request, "erp/form.html", dict(titulo="Apontamento", form=form, obj=obj, voltar=reverse("apontamentos")))


def apontamentos_importar(request):
    """Importa a planilha de produção: novos entram, existentes (data+turno+máquina+produto+OP) são atualizados."""
    ctx = dict(titulo="Importar apontamentos", modelo="Aba Input com colunas DATA, Turno, Máquina/Cód. máq., Produto, Cor, Tipo, Lar, Comp, Esp, OP, OK, Apara, Alça, Borra, Qtd milheiro, Obs, Cliente.")
    if request.method == "POST" and request.FILES.get("arquivo"):
        rows, erros, ops = P.ler_apontamentos(request.FILES["arquivo"], _lookups())
        novos = atualizados = 0
        with transaction.atomic():
            for op, cli in ops:
                if not OrdemProducao.objects.filter(numero=op).exists():
                    c, _ = Cliente.objects.get_or_create(nome=cli)
                    OrdemProducao.objects.create(numero=op, cliente=c)
            usados = set()
            for r in rows:
                cand = (Apontamento.objects.filter(data=r["data"], turno=r["turno"], maquina=r["maquina"],
                                                   produto=r["produto"], op=r["op"]).exclude(pk__in=usados).first())
                if cand:
                    for k, v in r.items():
                        setattr(cand, k, v)
                    cand.save(); usados.add(cand.pk); atualizados += 1
                else:
                    ap = Apontamento.objects.create(created_by=request.user, **r)
                    usados.add(ap.pk); novos += 1
        messages.success(request, f"{novos} novos, {atualizados} atualizados.")
        ctx["erros"] = erros
    return render(request, "erp/importar.html", ctx)


def relatorios(request):
    linhas, filtros = _linhas_producao(request, padrao_dias=30)
    opcoes = {"setor": "Setor", "maquina": "Máquina", "turno": "Turno", "produto": "Produto", "cor": "Cor",
              "tipo": "Tipo de sacola", "cliente": "Cliente", "dia": "Dia", "dia_semana": "Dia da semana", "op": "OP"}
    por = request.GET.get("por", "maquina")
    chaves = {"dia": lambda l: l.a.data.strftime("%Y-%m-%d"),
              "dia_semana": lambda l: f"{l.a.data.weekday()} {C.DIAS_SEMANA[l.a.data.weekday()]}",
              "op": lambda l: l.a.op or ""}
    chave = chaves.get(por, lambda l: getattr(l, por, ""))
    grupos = sorted(C.agrupar(linhas, chave), key=lambda g: g["grupo"] if por in ("dia", "dia_semana") else -g["total"])
    if request.GET.get("exportar"):
        return P.xlsx_response([{opcoes.get(por, por): g["grupo"], "OK kg": g["ok"], "Apara kg": g["apara"],
                                 "Alça kg": g["alca"], "Borra kg": g["borra"], "Perdas kg": g["perdas"],
                                 "Total kg": g["total"], "% Perdas": g["pct_perdas"], "Utilização": g["util"],
                                 "Apontamentos": g["n"]} for g in grupos], f"relatorio-{por}")
    return render(request, "erp/relatorios.html", dict(titulo="Relatórios", filtros=filtros, grupos=grupos,
                                                       tot=C.totalizar(linhas), opcoes=opcoes, por=por))


# ===================================================================== Vendas Omie
def vendas(request):
    de, ate = periodo(request, Venda, "data")
    qs = Venda.objects.filter(data__range=(de, ate))
    linhas_sel, vend_sel = lista_get(request, "linha"), lista_get(request, "vendedor")
    if linhas_sel:
        qs = qs.filter(linha__in=linhas_sel)
    if vend_sel:
        qs = qs.filter(vendedor__in=vend_sel)
    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(cliente__icontains=busca) | qs.filter(produto__icontains=busca)
    rows = list(qs)
    if request.GET.get("exportar"):
        campos = [f.name for f in Venda._meta.fields if f.name not in ("id", "created_at")]
        return P.xlsx_response([{c: getattr(r, c) for c in campos} for r in rows], "vendas")
    g = request.GET.get("g", "mes")
    tot = C.totais_vendas(rows)
    rk_cli = C.ranking(rows, lambda r: r.cliente)
    rk_linha = C.ranking(rows, lambda r: r.linha)
    rk_vend = C.ranking(rows, lambda r: P.texto(r.vendedor) or "(sem vendedor)")
    rk_uf = C.ranking(rows, lambda r: P.texto(r.estado).upper() or "(sem UF)")
    rk_cor = C.ranking(rows, lambda r: P.texto(r.cor) or "(sem cor)")
    rk_prod = C.ranking(rows, lambda r: P.texto(r.produto_simplificado) or C.codigo_produto(r.produto))
    serie = C.serie_vendas_periodo(rows, g)
    ctx = dict(
        titulo="Faturamento base Omie", de=de, ate=ate, g=g, granularidades=GRANULARIDADES, tot=tot,
        rk_cli=rk_cli[:20], rk_vend=rk_vend, rk_uf=rk_uf[:15], rk_prod=rk_prod[:20], rk_linha=rk_linha,
        op_linhas=Venda.objects.values_list("linha", flat=True).distinct().order_by("linha"),
        op_vendedores=Venda.objects.exclude(vendedor=None).values_list("vendedor", flat=True).distinct().order_by("vendedor"),
        linhas_sel=linhas_sel, vend_sel=vend_sel, q=busca, itens=rows[-200:][::-1],
        graf=js(dict(serie=serie, linha=dict(labels=[x["nome"] for x in rk_linha], valores=[round(x["total"], 2) for x in rk_linha]),
                     cor=dict(labels=[x["nome"] for x in rk_cor[:12]], valores=[round(x["total"], 2) for x in rk_cor[:12]]))),
    )
    return render(request, "erp/vendas.html", ctx)


def _importar_substituindo(request, modelo, campo_data, leitor, titulo, modelo_txt, voltar):
    """Substitui todos os registros no intervalo de datas coberto pela planilha (como no Lovable)."""
    ctx = dict(titulo=titulo, modelo=modelo_txt, voltar=voltar)
    if request.method == "POST" and request.FILES.get("arquivo"):
        rows, erros = leitor(request.FILES["arquivo"])
        if rows:
            datas = sorted(r[campo_data] for r in rows)
            with transaction.atomic():
                apagados, _ = modelo.objects.filter(**{f"{campo_data}__range": (datas[0], datas[-1])}).delete()
                modelo.objects.bulk_create([modelo(**r) for r in rows], batch_size=500)
            messages.success(request, f"{len(rows)} registros importados de {datas[0]:%d/%m/%Y} a {datas[-1]:%d/%m/%Y} "
                                      f"({apagados} anteriores do mesmo período substituídos).")
        else:
            messages.error(request, "Nenhuma linha válida encontrada.")
        ctx["erros"] = erros
    return render(request, "erp/importar.html", ctx)


def vendas_importar(request):
    return _importar_substituindo(request, Venda, "data", P.ler_vendas, "Importar faturamento Omie",
                                  'Planilha com a aba "Base de Dados" (Data, Cliente, Produto, Linha, Quantidade, Valor unitário, Total, Kg…). '
                                  "Os registros existentes no mesmo período são substituídos.", reverse("vendas"))


# ===================================================================== Vendas Plasti
def vendas_plasti(request):
    agg = VendaPlasti.objects.aggregate(mx=Max("data_pedido"))
    ref = agg["mx"] or date.today()
    de = _data(request.GET.get("de"), ref.replace(day=1))
    ate = _data(request.GET.get("ate"), ref)
    vend_sel = lista_get(request, "vendedor")
    pagamento = request.GET.get("pagamento", "")
    qs = VendaPlasti.objects.filter(data_pedido__range=(de, ate))
    if vend_sel:
        qs = qs.filter(vendedor__in=vend_sel)
    if pagamento:
        qs = qs.filter(forma_pagamento=pagamento)
    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(cliente__icontains=busca)
    pedidos = list(qs)
    metas = [m for m in MetaVendedor.objects.all() if not vend_sel or m.vendedor in vend_sel]
    meses = set(C.meses_no_intervalo(de, ate))
    metas_per = [m for m in metas if (m.mes.year, m.mes.month) in meses]
    meta = sum(C.f(m.meta) for m in metas_per)
    total = sum(C.f(p.valor) for p in pedidos)
    vista = sum(C.f(p.valor) for p in pedidos if "vista" in p.forma_pagamento.lower())
    kpis = dict(total=total, pedidos=len(pedidos), ticket=total / len(pedidos) if pedidos else None,
                clientes=len({p.cliente for p in pedidos}), meta=meta, atingimento=total / meta if meta else None,
                pct_vista=vista / total if total else None)
    real_meta = defaultdict(lambda: [0.0, 0.0])
    for m in metas_per:
        real_meta[m.vendedor][1] += C.f(m.meta)
    for p in pedidos:
        real_meta[p.vendedor][0] += C.f(p.valor)
    vendedores = sorted(([v, r, mt, r / mt if mt else None] for v, (r, mt) in real_meta.items()), key=lambda x: -x[1])
    g = request.GET.get("g", "dia")
    serie = C.serie_plasti(pedidos, metas, de, ate, g)
    rk_cli = C.ranking(pedidos, lambda p: p.cliente, valor=lambda p: C.f(p.valor))[:15]
    rk_pag = C.ranking(pedidos, lambda p: p.forma_pagamento, valor=lambda p: C.f(p.valor))
    ctx = dict(titulo="Vendas base Plasti Manaus", de=de, ate=ate, g=g, granularidades=GRANULARIDADES, kpis=kpis,
               vendedores=vendedores, rk_cli=rk_cli, pedidos=pedidos[::-1][:200], vend_sel=vend_sel, pagamento=pagamento, q=busca,
               op_vendedores=VendaPlasti.objects.values_list("vendedor", flat=True).distinct().order_by("vendedor"),
               op_pagamentos=VendaPlasti.objects.values_list("forma_pagamento", flat=True).distinct().order_by("forma_pagamento"),
               graf=js(dict(serie=serie, pag=dict(labels=[x["nome"] for x in rk_pag], valores=[round(x["total"], 2) for x in rk_pag]))))
    return render(request, "erp/vendas_plasti.html", ctx)


# ===================================================================== Fluxo de caixa
LANC_COLS = [("data_emissao", "Emissão"), ("data_pagamento", "Data pagto/receb."), ("fornecedor", "Cliente/Fornecedor"),
             ("categoria", "Categoria"), ("grupo", "Grupo"), ("situacao", "Situação"), ("tipo", "Tipo"),
             ("valor_conta", "Valor da conta"), ("valor_pago", "Pago/Recebido")]
LANC_POR_PAGINA = 50


def _somar_meses(mes, n):
    a, m = divmod(int(mes[:4]) * 12 + int(mes[5:7]) - 1 + n, 12)
    return f"{a}-{m + 1:02d}"


def _limites_mes(mes):
    import calendar
    a, m = int(mes[:4]), int(mes[5:7])
    return date(a, m, 1), date(a, m, calendar.monthrange(a, m)[1])


def _periodo_fluxo(request, meses):
    """Atalhos do Lovable: todo período, um mês, últimos 3/6 meses, ano atual ou datas livres. Vazio = todo período."""
    at = request.GET.get("at", "")
    ult = meses[-1] if meses else date.today().strftime("%Y-%m")
    if at.startswith("m:") and len(at) == 9:
        return (*_limites_mes(at[2:]), at)
    if at in ("u3", "u6"):
        return _limites_mes(_somar_meses(ult, -2 if at == "u3" else -5))[0], _limites_mes(ult)[1], at
    if at == "ano":
        y = date.today().year
        return date(y, 1, 1), date(y, 12, 31), at
    if at == "todos":
        return None, None, at
    de, ate = _data(request.GET.get("de"), None), _data(request.GET.get("ate"), None)
    if de and ate and de > ate:
        de, ate = ate, de
    if de and de < C.DATA_MINIMA_FLUXO:
        de = C.DATA_MINIMA_FLUXO
    return de, ate, ("custom" if de or ate else "todos")


def _rot_periodo(de, ate):
    if not (de or ate):
        return ""
    if de and ate and de.day == 1 and _limites_mes(de.strftime("%Y-%m"))[1] == ate:
        return C.rotulo_mes(de.strftime("%Y-%m"))
    return f"{de.strftime('%d/%m/%y') if de else 'início'} a {ate.strftime('%d/%m/%y') if ate else 'fim'}"


def fluxo_caixa(request):
    from . import fluxo_visao as V
    todos = [r for r in FluxoCaixa.objects.all() if C.data_ref(r) >= C.DATA_MINIMA_FLUXO]
    meses = sorted({C.data_ref(r).strftime("%Y-%m") for r in todos})
    de, ate, atalho = _periodo_fluxo(request, meses)
    grupos_sel, contas_sel, status_sel = lista_get(request, "grupo"), lista_get(request, "conta"), lista_get(request, "st")
    todas_sit = sorted({r.situacao for r in todos})

    def base(r, com_periodo=True, com_status=True):
        d = C.data_ref(r)
        return not ((com_periodo and ((de and d < de) or (ate and d > ate)))
                    or (grupos_sel and r.grupo not in grupos_sel)
                    or (contas_sel and (r.conta_corrente or "") not in contas_sel)
                    or (com_status and status_sel and r.situacao not in status_sel))
    rows = [r for r in todos if base(r)]
    if request.GET.get("exportar"):
        campos = [f.name for f in FluxoCaixa._meta.fields if f.name not in ("id", "created_at")]
        return P.xlsx_response([{c: getattr(r, c) for c in campos} for r in rows], "fluxo-caixa")

    # ---- Lançamentos (tabela com filtros próprios)
    l_tipo, l_cats, busca = request.GET.get("tipo", "todos"), lista_get(request, "lcat"), request.GET.get("q", "").strip()
    ordem = request.GET.get("ord", "data_emissao")
    ordem = ordem if ordem in dict(LANC_COLS) else "data_emissao"
    asc = request.GET.get("asc") == "1"
    tabela = [r for r in rows if (not l_cats or r.categoria in l_cats)
              and (l_tipo == "todos" or (l_tipo == "entradas" and C.f(r.valor_conta) > 0) or (l_tipo == "gastos" and C.f(r.valor_conta) < 0))
              and (not busca or busca.lower() in (r.fornecedor or "").lower() or busca.lower() in (r.categoria or "").lower())]
    def chave_ord(r):
        v = getattr(r, ordem)
        if ordem.startswith("valor"):
            return (1, C.f(v))
        return (0, "") if v in (None, "") else (1, C.sem_acento(v) if isinstance(v, str) else v)
    tabela.sort(key=chave_ord, reverse=not asc)
    filtros_txt = dict(periodo=_rot_periodo(de, ate) or "Todo período", status=", ".join(status_sel) or "Todos",
                       conta=", ".join(contas_sel) or "Todas", grupo=", ".join(grupos_sel) or "Todos",
                       categoria=", ".join(l_cats) or "Todas", busca=busca,
                       tipo={"entradas": "Entradas", "gastos": "Gastos"}.get(l_tipo, "Todos"))
    baixar = request.GET.get("baixar")
    if baixar == "xlsx":
        return P.xlsx_response([{t: (C.f(getattr(r, k)) if k.startswith("valor") else getattr(r, k)) for k, t in LANC_COLS} for r in tabela],
                               "lancamentos")
    if baixar == "pdf":
        return render(request, "erp/fluxo_lancamentos_pdf.html", dict(
            colunas=LANC_COLS, linhas=tabela, filtros=filtros_txt, total_conta=sum(C.f(r.valor_conta) for r in tabela),
            total_pago=sum(C.f(r.valor_pago) for r in tabela), gerado=timezone.localtime()))
    paginas = max(1, -(-len(tabela) // LANC_POR_PAGINA))
    try:
        pag = min(max(int(request.GET.get("p", "1")), 1), paginas)
    except ValueError:
        pag = 1

    # ---- Gráficos
    g = request.GET.get("g", "mes")
    g = g if g in dict(GRANULARIDADES) else "mes"
    meses_rows = sorted({C.data_ref(r).strftime("%Y-%m") for r in rows})
    mes = request.GET.get("mes")
    mes = mes if mes in meses_rows else (meses_rows[-1] if meses_rows else "")
    datas = sorted(C.data_ref(r) for r in rows)
    per = None
    if (de or ate) and datas:
        modo, pontos = V.serie_periodo(rows, de or datas[0], ate or datas[-1])
        per = dict(modo=modo, rotulo=_rot_periodo(de or datas[0], ate or datas[-1]))
    else:
        modo = "dia" if g == "dia" else "mes"
        pontos = V.serie_granularidade(rows, g, mes if g == "dia" else None)
    g_evo = (per["modo"] if per else g)
    rot_g = {"dia": "dia", "semana": "semana", "trimestre": "trimestre", "ano": "ano"}.get(g, "mês")
    if per:
        t_serie = f"Entradas x Gastos por {'dia' if per['modo'] == 'dia' else 'mês'} — {per['rotulo']} (R$)"
    elif g == "dia":
        t_serie = f"Entradas x Gastos por dia — {C.rotulo_mes(mes) if mes else ''} (R$)"
    else:
        t_serie = f"Entradas x Gastos por {rot_g} (R$)"
    if per:
        saldo = [dict(chave=p["chave"], label=p["label"], v=p["saldoAcum"]) for p in pontos]
    else:
        saldo = [dict(chave=p["chave"], label=p["label"], v=p["saldoAcum"]) for p in V.serie_granularidade(rows, g)]
    modo_ab = request.GET.get("ab", "receber")
    modo_ab = modo_ab if modo_ab in ("receber", "pagar", "ambos") else "receber"
    rows_aberto = [r for r in todos if base(r, com_periodo=False, com_status=False)]
    aberto = V.aberto_por_data(rows_aberto, modo_ab, status_sel or None, de, ate)
    gastos_grupo = V.ranking(rows, lambda r: r.grupo, -1)
    for x in gastos_grupo:
        x["cor"] = V.cor_grupo(x["nome"])
    cat_op = sorted({r.categoria for r in rows if C.f(r.valor_pago) < 0}, key=C.sem_acento)
    cats_sel = [c for c in lista_get(request, "cat") if c in cat_op]
    rows_cat = [r for r in rows if r.categoria in cats_sel] if cats_sel else rows
    evo_grupo = V.gastos_por_periodo(rows, lambda r: r.grupo, 6, g_evo)
    evo_cat = V.gastos_por_periodo(rows_cat, lambda r: r.categoria, 10, g_evo)
    top_cat = V.ranking(rows, lambda r: r.categoria, -1)
    top_cli = V.ranking(rows, lambda r: r.fornecedor, 1)
    top_forn = V.ranking(rows, lambda r: r.fornecedor, -1)
    sit_tipo = V.por_situacao_tipo(rows)
    sufixo = f" — {per['rotulo']}" if per else ""
    qs = request.GET.copy()
    for k in ("ord", "asc", "p", "baixar", "exportar"):
        qs.pop(k, None)
    qs_base = qs.urlencode()
    cab = [dict(k=k, t=t, num=k.startswith("valor"), seta=("▲" if asc else "▼") if k == ordem else "",
                url=f"?{qs_base}&ord={k}&asc={'0' if (k == ordem and asc) else '1'}") for k, t in LANC_COLS]
    qs_pag = f"{qs_base}&ord={ordem}&asc={'1' if asc else '0'}"

    ctx = dict(titulo="Entradas e Saídas base Omie", kpis=C.kpis_fluxo(rows), de=de, ate=ate, atalho=atalho, meses=meses,
               rot_meses=[(m, C.rotulo_mes(m)) for m in meses], g=g, granularidades=GRANULARIDADES,
               mes=mes, rot_meses_rows=[(m, C.rotulo_mes(m)) for m in meses_rows], mostrar_mes=(not per and g == "dia"),
               grupos_sel=grupos_sel, contas_sel=contas_sel, status_sel=status_sel,
               op_grupos=sorted({r.grupo for r in todos}, key=C.sem_acento),
               op_contas=sorted({r.conta_corrente for r in todos if r.conta_corrente}, key=C.sem_acento),
               op_status=[(s, V.cor_situacao(s)) for s in todas_sit],
               st_realizados=V.realizadas(todas_sit), st_aberto=V.em_aberto(todas_sit),
               t_serie=t_serie, sufixo=sufixo, modo_ab=modo_ab, aberto=aberto, cat_op=cat_op, cats_sel=cats_sel,
               n_cat=len(top_cat), n_cli=len(top_cli), n_forn=len(top_forn), sit_tipo=sit_tipo, sit_pares=[("Rec", "Contas a Receber por situação", sit_tipo["receber"]), ("Pag", "Contas a Pagar por situação", sit_tipo["pagar"])],
               situacoes=V.por_situacao(rows),
               lanc_cab=cab, qs_pag=qs_pag, lancamentos=tabela[(pag - 1) * LANC_POR_PAGINA: pag * LANC_POR_PAGINA], n_lanc=len(tabela),
               pag=pag, paginas=paginas, ordem=ordem, asc=asc, l_tipo=l_tipo, l_cats=l_cats, busca=busca,
               l_cat_op=sorted({r.categoria for r in rows}, key=C.sem_acento),
               graf=js(dict(modo=modo, serie=pontos, saldo=saldo, saldoDia=bool(per and per["modo"] == "dia"),
                            gastosGrupo=gastos_grupo, entradas=V.entradas_grupo_categoria(rows), evoGrupo=evo_grupo,
                            corGrupo={s: V.cor_grupo(s) for s in evo_grupo["series"]}, evoCat=evo_cat, gEvo=g_evo,
                            cats=top_cat, cli=top_cli, forn=top_forn, sitTipo=sit_tipo, aberto=aberto, modoAb=modo_ab,
                            cat=V.CAT, cinza=V.CINZA)))
    return render(request, "erp/fluxo_caixa.html", ctx)


def fluxo_importar(request):
    return _importar_substituindo(request, FluxoCaixa, "data_emissao", P.ler_fluxo, "Importar entradas e saídas Omie",
                                  "Exportação de contas a pagar/receber do Omie com Fornecedor/Cliente, Categoria, Data emissão, "
                                  "Data pagamento, Grupo, Situação, Tipo, Valor conta, Valor pago, Conta corrente. "
                                  "Os lançamentos com emissão no mesmo período são substituídos.", reverse("fluxo_caixa"))


# ===================================================================== Cadastros genéricos
def cadastro_lista(request, nome):
    cfg = CADASTROS[nome]
    objs = cfg["model"].objects.all()
    for rel in cfg.get("select", []):
        objs = objs.select_related(rel)
    linhas = [[c(o) if callable(c) else getattr(o, c) for _, c in cfg["colunas"]] for o in objs]
    return render(request, "erp/cadastro_lista.html", dict(
        titulo=cfg["titulo"], nome=nome, colunas=[t for t, _ in cfg["colunas"]], itens=list(zip(objs, linhas))))


def cadastro_form(request, nome, pk=None):
    cfg = CADASTROS[nome]
    Form = forms.modelform_factory(cfg["model"], fields=cfg["campos"], widgets=cfg.get("widgets"))
    obj = get_object_or_404(cfg["model"], pk=pk) if pk else None
    form = Form(request.POST or None, instance=obj)
    voltar = reverse("cadastro", args=[nome])
    if request.method == "POST":
        if "excluir" in request.POST and obj:
            try:
                obj.delete()
                messages.success(request, "Registro excluído.")
            except Exception:
                messages.error(request, "Não é possível excluir: o registro está em uso. Desative-o.")
            return redirect(voltar)
        if form.is_valid():
            form.save()
            messages.success(request, "Registro salvo.")
            return redirect(voltar)
    return render(request, "erp/form.html", dict(titulo=cfg["titulo"], form=form, obj=obj, voltar=voltar))


# ===================================================================== Integração Omie
def omie_view(request):
    import subprocess
    import sys

    from django.conf import settings as cfg
    from django.utils import timezone

    from . import omie
    from .models import SincronizacaoOmie

    hoje = date.today()
    de_pad = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
    if request.method == "POST":
        de, ate = _data(request.POST.get("de"), de_pad), _data(request.POST.get("ate"), hoje)
        so = request.POST.get("so", "")
        if not omie.configurado():
            messages.error(request, "Chaves do Omie não configuradas no servidor.")
        elif SincronizacaoOmie.objects.filter(status="rodando", inicio__gte=timezone.now() - timedelta(hours=1)).exists():
            messages.error(request, "Já existe uma sincronização em andamento.")
        else:
            reg = SincronizacaoOmie.objects.create(de=min(de, ate), ate=max(de, ate), usuario=request.user.username)
            cmd = [sys.executable, str(cfg.BASE_DIR / "manage.py"), "sincronizar_omie", "--registro", str(reg.pk),
                   "--de", reg.de.isoformat(), "--ate", reg.ate.isoformat()] + (["--so", so] if so else [])
            subprocess.Popen(cmd, cwd=cfg.BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            messages.success(request, "Sincronização iniciada. Atualize a página em alguns minutos.")
        return redirect("omie")
    ultimas = SincronizacaoOmie.objects.all()[:20]
    return render(request, "erp/omie.html", dict(titulo="Integração Omie", configurado=omie.configurado(),
                                                 de=de_pad, ate=hoje, ultimas=ultimas,
                                                 rodando=any(u.status == "rodando" for u in ultimas)))
