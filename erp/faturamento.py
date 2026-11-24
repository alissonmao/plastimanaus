"""Telas do Faturamento: notas fiscais, clientes, vendedores e produtos (base Venda)."""
from collections import defaultdict
from datetime import date

from django.db.models import Q
from django.shortcuts import render

from . import calculos as C
from . import planilhas as P
from .financeiro import _base as base_fluxo
from .models import Venda
from .views import GRANULARIDADES, js, lista_get, periodo


def _filtrar(request):
    de, ate = periodo(request, Venda, "data")
    qs = Venda.objects.filter(data__range=(de, ate))
    linhas_sel, vend_sel = lista_get(request, "linha"), lista_get(request, "vendedor")
    if linhas_sel:
        qs = qs.filter(linha__in=linhas_sel)
    if vend_sel:
        qs = qs.filter(vendedor__in=vend_sel)
    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(Q(cliente__icontains=busca) | Q(produto__icontains=busca) | Q(nota_fiscal__icontains=busca) | Q(cnpj_cpf__icontains=busca))
    ctx = dict(de=de, ate=ate, q=busca, linhas_sel=linhas_sel, vend_sel=vend_sel, g=request.GET.get("g", "mes"),
               granularidades=GRANULARIDADES,
               op_linhas=Venda.objects.values_list("linha", flat=True).distinct().order_by("linha"),
               op_vendedores=Venda.objects.exclude(vendedor=None).values_list("vendedor", flat=True).distinct().order_by("vendedor"))
    return list(qs.order_by("data")), ctx


def _doc(r):
    if r.nota_fiscal:
        return f"NF {r.nota_fiscal}"
    return f"{r.tipo_documento or 'Doc'} {r.orcamento or ''}".strip()


def _kg(r):
    return C.f(r.kg) if C.linha_com_kg(r.linha) and r.kg else 0.0


# ===================================================================== Notas fiscais
def notas(request):
    rows, ctx = _filtrar(request)
    nf = request.GET.get("nf")
    notas = {}
    for r in rows:
        k = (_doc(r), r.cliente)
        n = notas.setdefault(k, dict(doc=k[0], nf=r.nota_fiscal or "", cliente=r.cliente, data=r.data, vendedor=r.vendedor or "",
                                     cidade=r.cidade or "", uf=r.estado or "", itens=0, total=0.0, kg=0.0, linhas=set(), rows=[]))
        n["itens"] += 1
        n["total"] += C.f(r.total)
        n["kg"] += _kg(r)
        n["linhas"].add(r.linha)
        n["rows"].append(r)
    lista = sorted(notas.values(), key=lambda n: (n["data"], n["doc"]), reverse=True)
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Data": n["data"], "Documento": n["doc"], "Cliente": n["cliente"], "Vendedor": n["vendedor"],
                                 "Cidade": n["cidade"], "UF": n["uf"], "Itens": n["itens"], "Kg": n["kg"], "Total": n["total"]}
                                for n in lista], "notas-fiscais")
    detalhe = next((n for n in lista if n["doc"] == nf), None) if nf else None
    tot = dict(qtd=len(lista), total=sum(n["total"] for n in lista), nfs=sum(1 for n in lista if n["nf"]))
    tot["ticket"] = tot["total"] / tot["qtd"] if tot["qtd"] else None
    por_dia = defaultdict(lambda: [0, 0.0])
    for n in lista:
        c = C.chave_periodo(n["data"], ctx["g"])
        por_dia[c][0] += 1
        por_dia[c][1] += n["total"]
    ch = sorted(por_dia)
    ctx.update(titulo="Notas fiscais", notas=lista[:500], truncado=len(lista) > 500, detalhe=detalhe, tot=tot,
               graf=js(dict(labels=[C.rotulo_periodo(c, ctx["g"]) for c in ch], qtd=[por_dia[c][0] for c in ch],
                            valores=[round(por_dia[c][1], 2) for c in ch])))
    return render(request, "erp/fat_notas.html", ctx)


# ===================================================================== Clientes
def clientes(request):
    rows, ctx = _filtrar(request)
    nome = request.GET.get("cliente")
    if nome:
        return _cliente(request, nome, ctx)
    m = {}
    for r in rows:
        c = m.setdefault(r.cliente, dict(nome=r.cliente, total=0.0, kg=0.0, docs=set(), ultima=r.data, primeira=r.data,
                                          cidade=r.cidade or "", uf=r.estado or "", vendedor=r.vendedor or "", cnpj=r.cnpj_cpf or ""))
        c["total"] += C.f(r.total)
        c["kg"] += _kg(r)
        c["docs"].add(_doc(r))
        c["ultima"] = max(c["ultima"], r.data)
        c["primeira"] = min(c["primeira"], r.data)
    tot = sum(c["total"] for c in m.values())
    hoje = date.today()
    lista = sorted(m.values(), key=lambda c: -c["total"])
    acc = 0.0
    for i, c in enumerate(lista, 1):
        c["compras"] = len(c["docs"])
        c["ticket"] = c["total"] / c["compras"] if c["compras"] else None
        c["pct"] = c["total"] / tot if tot else 0
        acc += c["total"]
        c["abc"] = "A" if tot and acc / tot <= .8 else ("B" if tot and acc / tot <= .95 else "C")
        c["dias"] = (hoje - c["ultima"]).days
        c["pos"] = i
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Cliente": c["nome"], "CNPJ/CPF": c["cnpj"], "Cidade": c["cidade"], "UF": c["uf"], "Vendedor": c["vendedor"],
                                 "Faturamento": c["total"], "%": c["pct"], "Curva": c["abc"], "Compras": c["compras"], "Kg": c["kg"],
                                 "Ticket": c["ticket"], "Primeira": c["primeira"], "Última": c["ultima"]} for c in lista], "clientes")
    abc = {k: dict(qtd=sum(1 for c in lista if c["abc"] == k), total=sum(c["total"] for c in lista if c["abc"] == k)) for k in "ABC"}
    antigos = set(Venda.objects.filter(data__lt=ctx["de"]).values_list("cliente", flat=True).distinct())
    novos = sum(1 for c in lista if c["nome"] not in antigos)
    ctx.update(titulo="Clientes", clientes=lista, total=tot, abc=abc, novos=novos,
               graf=js(dict(labels=[c["nome"][:28] for c in lista[:15]], valores=[round(c["total"], 2) for c in lista[:15]])))
    return render(request, "erp/fat_clientes.html", ctx)


def _cliente(request, nome, ctx):
    rows = list(Venda.objects.filter(cliente=nome).order_by("data"))
    g = ctx["g"]
    serie = defaultdict(float)
    for r in rows:
        serie[C.chave_periodo(r.data, g)] += C.f(r.total)
    ch = sorted(serie)
    no_periodo = [r for r in rows if ctx["de"] <= r.data <= ctx["ate"]]
    prods = C.ranking(no_periodo, lambda r: P.texto(r.produto_simplificado) or C.codigo_produto(r.produto))
    docs = {}
    for r in no_periodo:
        d = docs.setdefault(_doc(r), dict(doc=_doc(r), data=r.data, total=0.0, itens=0))
        d["total"] += C.f(r.total)
        d["itens"] += 1
    cnpj = next((r.cnpj_cpf for r in reversed(rows) if r.cnpj_cpf), "")
    hoje = date.today()
    titulos = base_fluxo().filter(valor_conta__gt=0).filter(Q(fornecedor__iexact=nome) | (Q(cnpj_cpf=cnpj) if cnpj else Q(pk=None)))
    abertos = [t for t in titulos if not t.quitado and t.saldo_aberto > 0]
    for t in abertos:
        t.atrasado = t.vencimento < hoje
    info = rows[-1] if rows else None
    ctx.update(titulo=nome, nome=nome, info=info, cnpj=cnpj, tot=C.totais_vendas(no_periodo), tot_geral=sum(C.f(r.total) for r in rows),
               primeira=rows[0].data if rows else None, ultima=rows[-1].data if rows else None,
               prods=prods[:30], docs=sorted(docs.values(), key=lambda d: d["data"], reverse=True), abertos=sorted(abertos, key=lambda t: t.vencimento),
               aberto=sum(t.saldo_aberto for t in abertos), atrasado=sum(t.saldo_aberto for t in abertos if t.atrasado),
               graf=js(dict(labels=[C.rotulo_periodo(c, g) for c in ch], valores=[round(serie[c], 2) for c in ch])))
    return render(request, "erp/fat_cliente.html", ctx)


# ===================================================================== Vendedores
def vendedores(request):
    rows, ctx = _filtrar(request)
    nome_v = lambda r: P.texto(r.vendedor) or "(sem vendedor)"
    m = {}
    for r in rows:
        v = m.setdefault(nome_v(r), dict(nome=nome_v(r), total=0.0, kg=0.0, fat_kg=0.0, clientes=set(), docs=set()))
        t = C.f(r.total)
        v["total"] += t
        v["clientes"].add(r.cliente)
        v["docs"].add(_doc(r))
        if C.linha_com_kg(r.linha) and r.kg:
            v["kg"] += C.f(r.kg)
            v["fat_kg"] += t
    tot = sum(v["total"] for v in m.values())
    lista = sorted(m.values(), key=lambda v: -v["total"])
    for v in lista:
        v["n_clientes"], v["n_docs"] = len(v["clientes"]), len(v["docs"])
        v["ticket"] = v["total"] / v["n_docs"] if v["n_docs"] else None
        v["rs_kg"] = v["fat_kg"] / v["kg"] if v["kg"] else None
        v["pct"] = v["total"] / tot if tot else 0
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Vendedor": v["nome"], "Faturamento": v["total"], "%": v["pct"], "Clientes": v["n_clientes"],
                                 "Documentos": v["n_docs"], "Ticket": v["ticket"], "Kg": v["kg"], "R$/kg": v["rs_kg"]} for v in lista], "vendedores")
    g = ctx["g"]
    per = defaultdict(lambda: defaultdict(float))
    for r in rows:
        per[C.chave_periodo(r.data, g)][nome_v(r)] += C.f(r.total)
    ch = sorted(per)
    sel = request.GET.get("vendedor_det")
    det = None
    if sel:
        dr = [r for r in rows if nome_v(r) == sel]
        det = dict(nome=sel, clientes=C.ranking(dr, lambda r: r.cliente)[:20], linhas=C.ranking(dr, lambda r: r.linha))
    ctx.update(titulo="Vendedores", vendedores=lista, total=tot, det=det,
               graf=js(dict(labels=[C.rotulo_periodo(c, g) for c in ch],
                            series=[dict(nome=v["nome"], valores=[round(per[c].get(v["nome"], 0), 2) for c in ch]) for v in lista[:10]])))
    return render(request, "erp/fat_vendedores.html", ctx)


# ===================================================================== Produtos
def produtos(request):
    rows, ctx = _filtrar(request)
    chave = request.GET.get("por", "produto")
    fun = {"produto": lambda r: P.texto(r.produto_simplificado) or C.codigo_produto(r.produto),
           "codigo": lambda r: r.produto, "linha": lambda r: r.linha or "(sem linha)",
           "grupo": lambda r: P.texto(r.grupo) or "(sem grupo)", "cor": lambda r: P.texto(r.cor) or "(sem cor)"}.get(chave)
    m = {}
    for r in rows:
        k = fun(r)
        p = m.setdefault(k, dict(nome=k, linha=r.linha, total=0.0, qtd=0.0, unidade=r.unidade or "", kg=0.0, fat_kg=0.0, clientes=set(), itens=0))
        t = C.f(r.total)
        p["total"] += t
        p["qtd"] += C.f(r.quantidade)
        p["itens"] += 1
        p["clientes"].add(r.cliente)
        if C.linha_com_kg(r.linha) and r.kg:
            p["kg"] += C.f(r.kg)
            p["fat_kg"] += t
    tot = sum(p["total"] for p in m.values())
    lista = sorted(m.values(), key=lambda p: -p["total"])
    for p in lista:
        p["n_clientes"] = len(p["clientes"])
        p["preco"] = p["total"] / p["qtd"] if p["qtd"] else None
        p["rs_kg"] = p["fat_kg"] / p["kg"] if p["kg"] else None
        p["pct"] = p["total"] / tot if tot else 0
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Produto": p["nome"], "Linha": p["linha"], "Faturamento": p["total"], "%": p["pct"], "Quantidade": p["qtd"],
                                 "Un": p["unidade"], "Preço médio": p["preco"], "Kg": p["kg"], "R$/kg": p["rs_kg"], "Clientes": p["n_clientes"]}
                                for p in lista], "produtos")
    ctx.update(titulo="Produtos", produtos=lista[:500], total=tot, por=chave, qtd=len(lista),
               opcoes_por=[("produto", "Produto"), ("codigo", "Código completo"), ("linha", "Linha"), ("grupo", "Grupo"), ("cor", "Cor")],
               tot=C.totais_vendas(rows),
               graf=js(dict(labels=[p["nome"][:30] for p in lista[:15]], valores=[round(p["total"], 2) for p in lista[:15]])))
    return render(request, "erp/fat_produtos.html", ctx)
