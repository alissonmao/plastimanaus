"""Faturamento → Pedidos (Omie): cópia só leitura dos pedidos de venda, atualizada de hora em hora."""
from decimal import Decimal

from django.db.models import Max, Q
from django.shortcuts import render
from django.utils import timezone

from . import calculos as C
from . import planilhas as P
from .models import PedidoOmie
from .views import _data, lista_get

COLS = [("numero", "Pedido"), ("data_previsao", "Previsão"), ("data_inclusao", "Incluído em"), ("cliente", "Cliente"),
        ("vendedor", "Vendedor"), ("situacao", "Situação"), ("qtd_itens", "Itens"), ("peso_liquido", "Peso líq. (kg)"),
        ("valor_total", "Valor")]
NUM = {"qtd_itens", "peso_liquido", "valor_total"}
POR_PAGINA = 50
Z = Decimal(0)


def em_aberto(p):
    return not (p.faturado or p.cancelado or p.devolvido)


def lista(request):
    todos = list(PedidoOmie.objects.all())
    de, ate = _data(request.GET.get("de"), None), _data(request.GET.get("ate"), None)
    sit_sel, vend = lista_get(request, "sit"), request.GET.get("vendedor", "")
    q = request.GET.get("q", "").strip().lower()
    rows = [p for p in todos
            if (not de or (p.data_previsao and p.data_previsao >= de)) and (not ate or (p.data_previsao and p.data_previsao <= ate))
            and (not sit_sel or p.situacao in sit_sel) and (not vend or p.vendedor == vend)
            and (not q or q in p.cliente.lower() or q == p.numero.lower() or q in (p.cnpj_cpf or ""))]
    ordem = request.GET.get("ord", "data_previsao")
    ordem = ordem if ordem in dict(COLS) else "data_previsao"
    asc = request.GET.get("asc") == "1"

    def chave(p):
        v = getattr(p, ordem)
        if ordem == "numero":
            return (1, int(v)) if v.isdigit() else (1, 10**12)
        if ordem in NUM:
            return (1, v or 0)
        return (0, "") if v in (None, "") else (1, C.sem_acento(v) if isinstance(v, str) else v)
    rows.sort(key=chave, reverse=not asc)

    if request.GET.get("exportar"):
        return P.xlsx_response([{t: (float(getattr(p, k)) if k in ("valor_total", "peso_liquido") else getattr(p, k)) for k, t in COLS}
                                | {"Desconto": float(p.valor_descontos), "Parcelas": p.parcelas, "CNPJ/CPF": p.cnpj_cpf} for p in rows],
                               "pedidos-omie")
    validos = [p for p in rows if not p.cancelado]
    abertos = [p for p in rows if em_aberto(p)]
    hoje = timezone.localdate()
    kpi = dict(
        abertos=len(abertos), abertos_valor=sum((p.valor_total for p in abertos), Z),
        faturar=sum(1 for p in abertos if p.etapa == "50"), faturar_valor=sum((p.valor_total for p in abertos if p.etapa == "50"), Z),
        faturados=sum(1 for p in rows if p.faturado and not p.cancelado),
        faturados_valor=sum((p.valor_total for p in rows if p.faturado and not p.cancelado), Z),
        cancelados=sum(1 for p in rows if p.cancelado), cancelados_valor=sum((p.valor_total for p in rows if p.cancelado), Z),
        ticket=(sum((p.valor_total for p in validos), Z) / len(validos)) if validos else None,
        atrasados=sum(1 for p in abertos if p.data_previsao and p.data_previsao < hoje))
    paginas = max(1, -(-len(rows) // POR_PAGINA))
    try:
        pag = min(max(int(request.GET.get("p", "1")), 1), paginas)
    except ValueError:
        pag = 1
    qs = request.GET.copy()
    for k in ("ord", "asc", "p", "exportar", "pedido"):
        qs.pop(k, None)
    base = qs.urlencode()
    cab = [dict(k=k, t=t, num=k in NUM, seta=("▲" if asc else "▼") if k == ordem else "",
                url=f"?{base}&ord={k}&asc={'0' if (k == ordem and asc) else '1'}") for k, t in COLS]
    detalhe = None
    cod = request.GET.get("pedido")
    if cod and cod.isdigit():
        detalhe = PedidoOmie.objects.filter(codigo=int(cod)).prefetch_related("itens").first()
    sinc = PedidoOmie.objects.aggregate(d=Max("sincronizado_em"))["d"]
    return render(request, "erp/pedidos.html", dict(
        titulo="Pedidos (Omie)", pedidos=rows[(pag - 1) * POR_PAGINA: pag * POR_PAGINA], n=len(rows), total=len(todos),
        kpi=kpi, cab=cab, pag=pag, paginas=paginas, qs_pag=f"{base}&ord={ordem}&asc={'1' if asc else '0'}", qs_base=base,
        de=de, ate=ate, sit_sel=sit_sel, vend=vend, q=request.GET.get("q", ""), detalhe=detalhe, hoje=hoje,
        op_sit=sorted({p.situacao for p in todos}), op_vend=sorted({p.vendedor for p in todos if p.vendedor}, key=C.sem_acento),
        sinc=timezone.localtime(sinc) if sinc else None))
