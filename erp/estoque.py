"""Menu Estoque: cópia só leitura do estoque do Omie (posição, movimentações, produtos e cobertura)."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone

from . import calculos as C
from . import planilhas as P
from .models import EstoqueOmie, MovEstoqueOmie, PedidoItemOmie, ProdutoOmie
from .views import _data

Z = Decimal(0)
DIAS_VENDA = 90          # janela para a média de saídas por venda
COBERTURA_CURTA = 15     # dias: "acaba logo"
DIAS_PARADO = 90         # sem saída há mais que isso: "parado"
ORIGENS_VENDA = ("VEN", "CVP", "DVP")   # venda, cancelamento de venda e devolução de venda (líquido)
TIPOS_VENDA = {"Produto acabado", "Revenda", "Subproduto"}


def custo_suspeito(e) -> bool:
    """Custo médio zerado ou muito abaixo do preço de venda: o valor em estoque sai errado."""
    if e.saldo <= 0:
        return False
    return e.custo_medio <= Decimal("0.01") or (e.preco > 0 and e.custo_medio < e.preco * Decimal("0.02"))


def abaixo_minimo(e) -> bool:
    return e.minimo > 0 and e.saldo < e.minimo


def _sinc(modelo):
    d = modelo.objects.aggregate(d=Max("sincronizado_em"))["d"]
    return timezone.localtime(d) if d else None


def _paginar(request, rows, por_pagina):
    paginas = max(1, -(-len(rows) // por_pagina))
    try:
        pag = min(max(int(request.GET.get("p", "1")), 1), paginas)
    except ValueError:
        pag = 1
    return rows[(pag - 1) * por_pagina: pag * por_pagina], pag, paginas


def _qs(request, *tirar):
    qs = request.GET.copy()
    for k in ("p", "exportar", "ord", "asc") + tirar:
        qs.pop(k, None)
    return qs.urlencode()


def _ordenar(request, rows, cols, padrao, desc_padrao=True):
    """Ordena por ?ord= (uma das colunas) e devolve o cabeçalho com links."""
    ordem = request.GET.get("ord", padrao)
    ordem = ordem if ordem in dict(cols) else padrao
    asc = request.GET.get("asc") == "1" if "asc" in request.GET else not desc_padrao

    def chave(r):
        v = r[ordem] if isinstance(r, dict) else getattr(r, ordem)
        if v is None or v == "":
            return (2, "") if asc else (0, "")  # vazios sempre no fim
        return (1, C.sem_acento(v) if isinstance(v, str) else v)
    rows.sort(key=chave, reverse=not asc)
    base = _qs(request)
    cab = [dict(k=k, t=t, seta=("▲" if asc else "▼") if k == ordem else "",
                url=f"?{base}&ord={k}&asc={'0' if (k == ordem and asc) else '1'}") for k, t in cols]
    return cab, f"{base}&ord={ordem}&asc={'1' if asc else '0'}"


def _familias():
    return {p.codigo_produto: p for p in ProdutoOmie.objects.all()}


# ===================================================================== Posição
POS_COLS = [("codigo", "Código"), ("descricao", "Produto"), ("familia", "Família"), ("local", "Local"), ("saldo", "Saldo"),
            ("reservado", "Reservado"), ("pendente", "Em pedidos"), ("minimo", "Mínimo"), ("custo_medio", "Custo médio"),
            ("valor", "Valor em estoque")]


def posicao(request):
    prods = _familias()
    todos = list(EstoqueOmie.objects.all())
    for e in todos:
        p = prods.get(e.codigo_produto)
        e.familia = p.familia if p else ""
        e.unidade = p.unidade if p else ""
        e.suspeito, e.abaixo = custo_suspeito(e), abaixo_minimo(e)
    local, fam, q, alerta = (request.GET.get(k, "") for k in ("local", "familia", "q", "alerta"))
    ql = q.strip().lower()
    rows = [e for e in todos if (not local or e.local == local) and (not fam or e.familia == fam)
            and (not ql or ql in e.descricao.lower() or ql in e.codigo.lower())
            and (alerta != "minimo" or e.abaixo) and (alerta != "custo" or e.suspeito)]
    cab, qs_pag = _ordenar(request, rows, POS_COLS, "valor")
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Código": e.codigo, "Produto": e.descricao, "Família": e.familia, "Local": e.local, "Un.": e.unidade,
                                 "Saldo": float(e.saldo), "Físico": float(e.fisico), "Reservado": float(e.reservado),
                                 "Em pedidos": float(e.pendente), "Mínimo": float(e.minimo), "Custo médio": float(e.custo_medio),
                                 "Valor em estoque": float(e.valor), "Custo suspeito": "sim" if e.suspeito else ""} for e in rows],
                               "estoque-posicao")
    por_local = defaultdict(lambda: dict(valor=Z, n=0))
    for e in todos:
        por_local[e.local]["valor"] += e.valor
        por_local[e.local]["n"] += 1
    locais = sorted(por_local.items(), key=lambda x: -x[1]["valor"])
    ja_vendeu = set(MovEstoqueOmie.objects.filter(origem="VEN").values_list("codigo_produto", flat=True).distinct())
    fora = [e for e in todos if e.local_codigo == "PA" and e.saldo > 0 and e.codigo_produto not in ja_vendeu
            and not (prods.get(e.codigo_produto) and prods[e.codigo_produto].tipo_item in TIPOS_VENDA)]
    fora.sort(key=lambda e: -e.valor)
    pagina, pag, paginas = _paginar(request, rows, 100)
    return render(request, "erp/estoque_posicao.html", dict(
        titulo="Posição de estoque", itens=pagina, n=len(rows), total=len(todos), cab=cab, qs_pag=qs_pag, pag=pag, paginas=paginas,
        qs_base=_qs(request), locais=locais, valor_total=sum((e.valor for e in todos), Z), valor_filtro=sum((e.valor for e in rows), Z),
        fora=fora, fora_valor=sum((e.valor for e in fora), Z), n_suspeito=sum(1 for e in todos if e.suspeito), n_abaixo=sum(1 for e in todos if e.abaixo),
        op_local=[l for l, _ in locais], op_fam=sorted({e.familia for e in todos if e.familia}, key=C.sem_acento),
        local=local, familia=fam, q=q, alerta=alerta, sinc=_sinc(EstoqueOmie)))


# ===================================================================== Movimentações
def movimentos(request):
    hoje = timezone.localdate()
    de = _data(request.GET.get("de"), hoje - timedelta(days=30))
    ate = _data(request.GET.get("ate"), hoje)
    local, origem, tipo, q = (request.GET.get(k, "") for k in ("local", "origem", "tipo", "q"))
    base = MovEstoqueOmie.objects.filter(data__range=(de, ate))
    if local:
        base = base.filter(local=local)
    if origem:
        base = base.filter(origem_desc=origem)
    if tipo:
        base = base.filter(tipo=tipo)
    rows = list(base)
    ql = q.strip().lower()
    if ql:
        rows = [m for m in rows if ql in m.descricao.lower() or ql in m.documento.lower() or ql in m.pedido.lower()]
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Data": m.data, "Produto": m.descricao, "Local": m.local, "Tipo": m.tipo, "Origem": m.origem_desc,
                                 "Documento": m.documento, "Pedido/OP": m.pedido, "Quantidade": float(m.quantidade),
                                 "Saldo depois": float(m.saldo), "Custo médio": float(m.custo_medio),
                                 "Cancelado": "sim" if m.cancelado else ""} for m in rows], "estoque-movimentacoes")
    validos = [m for m in rows if not m.cancelado]
    por_origem = defaultdict(lambda: dict(ent=Z, sai=Z, n=0))
    for m in validos:
        o = por_origem[m.origem_desc or "—"]
        o["n"] += 1
        if m.quantidade > 0:
            o["ent"] += m.quantidade
        else:
            o["sai"] -= m.quantidade
    pagina, pag, paginas = _paginar(request, rows, 100)
    todos = MovEstoqueOmie.objects
    return render(request, "erp/estoque_movimentos.html", dict(
        titulo="Movimentações de estoque", movs=pagina, n=len(rows), pag=pag, paginas=paginas, qs_pag=_qs(request), qs_base=_qs(request),
        de=de, ate=ate, local=local, origem=origem, tipo=tipo, q=q,
        entradas=sum((m.quantidade for m in validos if m.quantidade > 0), Z),
        saidas=-sum((m.quantidade for m in validos if m.quantidade < 0), Z),
        n_cancelados=len(rows) - len(validos), por_origem=sorted(por_origem.items(), key=lambda x: -x[1]["n"]),
        op_local=sorted(set(todos.exclude(local="").values_list("local", flat=True))),
        op_origem=sorted(set(todos.exclude(origem_desc="").values_list("origem_desc", flat=True))),
        sinc=_sinc(EstoqueOmie)))


# ===================================================================== Produtos
PROD_COLS = [("codigo", "Código"), ("descricao", "Descrição"), ("familia", "Família"), ("tipo_item", "Tipo"), ("unidade", "Un."),
             ("ncm", "NCM"), ("peso_liquido", "Peso líq."), ("estoque_minimo", "Mínimo"), ("preco", "Preço"), ("saldo", "Saldo total")]


def produtos(request):
    saldos = defaultdict(lambda: Z)
    for cod, s in EstoqueOmie.objects.values_list("codigo_produto", "saldo"):
        saldos[cod] += s
    todos = list(ProdutoOmie.objects.all())
    for p in todos:
        p.saldo = saldos.get(p.codigo_produto, Z)
    fam, tipo, sit, q = (request.GET.get(k, "") for k in ("familia", "tipo", "sit", "q"))
    sit = sit or "ativos"
    ql = q.strip().lower()
    rows = [p for p in todos if (not fam or p.familia == fam) and (not tipo or p.tipo_item == tipo)
            and (sit == "todos" or (sit == "ativos") != p.inativo)
            and (not ql or ql in p.descricao.lower() or ql in p.codigo.lower() or ql in p.ean)]
    cab, qs_pag = _ordenar(request, rows, PROD_COLS, "descricao", desc_padrao=False)
    if request.GET.get("exportar"):
        return P.xlsx_response([{"Código": p.codigo, "Descrição": p.descricao, "Família": p.familia, "Tipo": p.tipo_item,
                                 "Un.": p.unidade, "NCM": p.ncm, "EAN": p.ean, "Peso líquido": float(p.peso_liquido),
                                 "Peso bruto": float(p.peso_bruto), "Estoque mínimo": float(p.estoque_minimo), "Preço": float(p.preco),
                                 "Saldo total": float(p.saldo), "Situação": "inativo" if p.inativo else "ativo"} for p in rows],
                               "produtos-omie")
    pagina, pag, paginas = _paginar(request, rows, 100)
    return render(request, "erp/estoque_produtos.html", dict(
        titulo="Produtos (Omie)", prods=pagina, n=len(rows), total=len(todos), cab=cab, qs_pag=qs_pag, pag=pag, paginas=paginas,
        qs_base=_qs(request), familia=fam, tipo=tipo, sit=sit, q=q,
        n_ativos=sum(1 for p in todos if not p.inativo), n_sem_minimo=sum(1 for p in todos if not p.inativo and not p.estoque_minimo),
        op_fam=sorted({p.familia for p in todos if p.familia}, key=C.sem_acento),
        op_tipo=sorted({p.tipo_item for p in todos if p.tipo_item}), sinc=_sinc(ProdutoOmie)))


# ===================================================================== Cobertura
def calcular_cobertura(hoje=None):
    """Por produto do Produto Acabado: saldo, saídas por venda nos últimos 90 dias, dias de cobertura,
    última saída e quanto os pedidos na etapa Faturar pedem."""
    hoje = hoje or timezone.localdate()
    desde = hoje - timedelta(days=DIAS_VENDA)
    saldo, nome, codigo = defaultdict(lambda: Z), {}, {}
    for e in EstoqueOmie.objects.filter(local_codigo="PA"):
        saldo[e.codigo_produto] += e.saldo
        nome[e.codigo_produto], codigo[e.codigo_produto] = e.descricao, e.codigo
    vendido, ultima, ja_vendeu = defaultdict(lambda: Z), {}, set()
    for m in MovEstoqueOmie.objects.filter(cancelado=False):
        if m.origem == "VEN":
            ja_vendeu.add(m.codigo_produto)
        if m.quantidade < 0 and m.data > ultima.get(m.codigo_produto, m.data - timedelta(days=1)):
            ultima[m.codigo_produto] = m.data
        if m.origem in ORIGENS_VENDA and m.data >= desde:
            vendido[m.codigo_produto] -= m.quantidade   # saída de venda soma, cancelamento/devolução desconta
            nome.setdefault(m.codigo_produto, m.descricao)
    prods = _familias()
    # Só o que é para vender: máquinas, equipamentos e aparas lançados no local Produto Acabado ficam de fora
    candidatos = {c for c in set(saldo) | set(vendido)
                  if c in ja_vendeu or (prods.get(c) and prods[c].tipo_item in TIPOS_VENDA)}
    for cod in candidatos:
        if cod not in codigo and cod in prods:
            codigo[cod] = prods[cod].codigo
    em_pedidos = defaultdict(lambda: Z)
    for c, qtd in PedidoItemOmie.objects.filter(pedido__etapa="50", pedido__faturado=False, pedido__cancelado=False,
                                                 pedido__devolvido=False).values_list("codigo_produto", "quantidade"):
        em_pedidos[c] += qtd
    rows = []
    for cod in candidatos:
        s, v = saldo.get(cod, Z), max(vendido.get(cod, Z), Z)
        media = v / DIAS_VENDA
        dias = int(s / media) if media > 0 else None
        ult = ultima.get(cod)
        parado = s > 0 and (not ult or (hoje - ult).days > DIAS_PARADO)
        ped = em_pedidos.get(codigo.get(cod, ""), Z)
        p = prods.get(cod)
        if parado:
            sit = "Parado"
        elif s <= 0:
            sit = "Sem estoque"
        elif dias is not None and dias < COBERTURA_CURTA:
            sit = "Acaba logo"
        elif dias is None:
            sit = "Sem venda em 90 dias"
        else:
            sit = "Ok"
        rows.append(dict(codigo_produto=cod, codigo=codigo.get(cod, ""), descricao=nome.get(cod, ""), familia=p.familia if p else "",
                         unidade=p.unidade if p else "", saldo=s, vendido=v, media=media, dias=dias, ultima=ult,
                         sem_saida=(hoje - ult).days if ult else None, em_pedidos=ped, falta=max(ped - s, Z), situacao=sit))
    return rows


COB_COLS = [("codigo", "Código"), ("descricao", "Produto"), ("saldo", "Saldo"), ("vendido", "Vendido 90d"),
            ("media", "Média/dia"), ("dias", "Dura (dias)"), ("ultima", "Última saída"), ("em_pedidos", "A faturar"),
            ("falta", "Falta"), ("situacao", "Situação")]


def cobertura(request):
    todos = calcular_cobertura()
    sit, q = request.GET.get("sit", ""), request.GET.get("q", "").strip().lower()
    rows = [r for r in todos if (not sit or r["situacao"] == sit) and (not q or q in r["descricao"].lower() or q in r["codigo"].lower())]
    cab, qs_pag = _ordenar(request, rows, COB_COLS, "dias", desc_padrao=False)
    if request.GET.get("exportar"):
        return P.xlsx_response([{t: (float(r[k]) if isinstance(r[k], Decimal) else r[k]) for k, t in COB_COLS} | {"Família": r["familia"]}
                                for r in rows],
                               "estoque-cobertura")
    cont = defaultdict(int)
    for r in todos:
        cont[r["situacao"]] += 1
    return render(request, "erp/estoque_cobertura.html", dict(
        titulo="Cobertura de estoque", itens=rows, n=len(rows), total=len(todos), cab=cab, qs_pag=qs_pag, qs_base=_qs(request),
        sit=sit, q=request.GET.get("q", ""), cont=dict(cont), n_falta=sum(1 for r in todos if r["falta"] > 0),
        situacoes=["Acaba logo", "Sem estoque", "Ok", "Sem venda em 90 dias", "Parado"],
        dias_venda=DIAS_VENDA, curta=COBERTURA_CURTA, parado=DIAS_PARADO, sinc=_sinc(EstoqueOmie)))
