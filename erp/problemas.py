"""Problemas para resolver: regras que leem os dados da empresa e apontam o que alguém precisa corrigir.

Só leitura. A lista é montada do zero a cada conferência: regra sem itens não aparece, e o problema some sozinho
quando é corrigido na origem. Para criar uma regra nova, escreva uma função com o decorador @regra.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import cached_property

from django.db.models import Max
from django.utils import timezone

from . import calculos as C
from .models import (Apontamento, EstoqueOmie, FluxoCaixa, Maquina, MetaVendedor, PedidoOmie, ProdutoOmie, SaldoContaOmie,
                     SincronizacaoOmie, Venda)

log = logging.getLogger(__name__)
Z = Decimal(0)
CRITICO, ATENCAO, SABER = "critico", "atencao", "saber"
GRAVIDADES = {CRITICO: ("Crítico", "resolver hoje"), ATENCAO: ("Atenção", "resolver nesta semana"), SABER: ("Para saber", "acompanhar")}
ORDEM_GRAV = {CRITICO: 0, ATENCAO: 1, SABER: 2}
AREAS = ["Financeiro", "Vendas", "Produção", "Estoque", "Compras", "Cadastro", "Sistema"]
AREAS_SO_ADMIN = {"Sistema"}

# Parâmetros (ajuste aqui)
PERDA_MAXIMA = 0.15            # regra 10: perda acima de 15% nos últimos 7 dias
PERDA_KG_MINIMO = 100          # ...com pelo menos 100 kg processados
CATEGORIAS_FORA = {"rendimentos de aplicacoes", "estorno"}   # não são despesa nem receita


@dataclass
class Regra:
    id: str
    nome: str
    area: str
    gravidade: str
    como_corrigir: str
    fn: callable
    fonte: str = ""          # financeiro | vendas | producao | cadastro | sistema
    link: str = ""           # rota do ERP onde corrigir/ver


REGRAS: list[Regra] = []


def regra(id, nome, area, gravidade, como_corrigir, fonte="", link=""):
    def deco(fn):
        REGRAS.append(Regra(id, nome, area, gravidade, como_corrigir, fn, fonte, link))
        return fn
    return deco


@dataclass
class Resultado:
    titulo: str
    descricao: str
    itens: list
    colunas: list                      # [(chave, rótulo, tipo)] tipo: txt|data|brl|int|pct|kg
    valor: Decimal | None = None
    qtd: int | None = None
    regra: Regra | None = None
    fonte_txt: str = ""
    dispensa: object = None
    erro: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def n(self):
        return self.qtd if self.qtd is not None else len(self.itens)


def brl(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {s}"


def dma(d):
    return d.strftime("%d/%m/%Y") if d else "—"


def plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"


def dias_uteis_antes(d, n):
    """Os n dias úteis anteriores a d (sem contar d)."""
    out = []
    while len(out) < n:
        d -= timedelta(days=1)
        if C.eh_dia_util(d):
            out.append(d)
    return out


# ===================================================================== contexto (dados lidos uma vez por conferência)
class Contexto:
    def __init__(self, hoje=None, vendedor=None, agora=None):
        self.hoje = hoje or date.today()
        self.agora = agora or timezone.localtime()
        self.vendedor = vendedor            # None = todos; senão só a carteira deste vendedor

    @cached_property
    def titulos(self):
        """Contas do Omie, sem rendimento de aplicação, estorno, transferência entre contas e cancelados."""
        out = []
        for r in FluxoCaixa.objects.all():
            cat = C.sem_acento(r.categoria)
            sit = C.sem_acento(r.situacao)
            if cat in CATEGORIAS_FORA or "transfer" in cat or "cancel" in sit or "estorn" in sit:
                continue
            out.append(r)
        return out

    @cached_property
    def pendentes(self):
        return [r for r in self.titulos if not r.quitado and r.saldo_aberto > 0]

    @cached_property
    def vendas(self):
        q = Venda.objects.all()
        if self.vendedor:
            q = q.filter(vendedor=self.vendedor)
        return list(q)

    @cached_property
    def fontes(self):
        s = SincronizacaoOmie.objects.filter(status="ok").order_by("-fim").first()
        ven = Venda.objects.aggregate(d=Max("data"), c=Max("created_at"))
        ap = Apontamento.objects.aggregate(d=Max("data"), c=Max("created_at"))
        loc = lambda x: timezone.localtime(x).strftime("%d/%m/%Y %H:%M") if x else "nunca"
        return dict(
            financeiro=f"Dados do Omie · última sincronização {loc(s.fim if s else None)}",
            vendas=f"Vendas do Omie até {dma(ven['d'])} · carregadas em {loc(ven['c'])}",
            producao=f"Apontamentos até {dma(ap['d'])} · último lançado em {loc(ap['c'])}",
            cadastro="Cadastros do ERP e títulos do Omie",
            pedidos=f"Pedidos do Omie · atualizados em {loc(PedidoOmie.objects.aggregate(d=Max('sincronizado_em'))['d'])}",
            estoque=f"Estoque do Omie · atualizado em {loc(EstoqueOmie.objects.aggregate(d=Max('sincronizado_em'))['d'])}",
            sistema="Integrações e importações",
        )


# ===================================================================== Financeiro
COL_TITULO = [("parte", "Fornecedor/Cliente", "txt"), ("documento", "Documento", "txt"), ("categoria", "Categoria", "txt"),
              ("vencimento", "Vencimento", "data"), ("dias", "Dias vencido", "int"), ("valor", "Em aberto", "brl")]


def _item_titulo(r, hoje):
    doc = " ".join(x for x in [r.numero_documento or "", f"({r.parcela})" if r.parcela else ""] if x).strip()
    return dict(parte=r.fornecedor, documento=doc or "—", categoria=r.categoria, vencimento=r.vencimento,
                dias=(hoje - r.vencimento).days, valor=r.saldo_aberto)


@regra("pagar_vencidas", "Contas a pagar vencidas sem baixa", "Financeiro", CRITICO,
       "Pague ou renegocie com o fornecedor. Se a conta já foi paga, dê a baixa no Omie (Finanças → Contas a Pagar → "
       "Baixar); o ERP atualiza sozinho em até 1 hora.", fonte="financeiro", link="fin_pagar")
def r_pagar_vencidas(ctx):
    rows = [r for r in ctx.pendentes if not r.receber and r.vencimento < ctx.hoje]
    if not rows:
        return None
    itens = sorted((_item_titulo(r, ctx.hoje) for r in rows), key=lambda x: (-x["dias"], -x["valor"]))
    total = sum(i["valor"] for i in itens)
    velho = itens[0]
    return Resultado(f"{plural(len(itens), 'conta a pagar vencida', 'contas a pagar vencidas')} sem baixa — {brl(total)}",
                     f"A mais antiga venceu há {velho['dias']} dias ({dma(velho['vencimento'])}, {velho['parte']}, {brl(velho['valor'])}).",
                     itens, COL_TITULO, total)


@regra("receber_vencidas", "Contas a receber vencidas", "Financeiro", CRITICO,
       "Cobre o cliente (telefone, WhatsApp ou e-mail com o boleto atualizado). Se o cliente já pagou, dê a baixa no "
       "Omie (Finanças → Contas a Receber → Baixar).", fonte="financeiro", link="fin_atrasados")
def r_receber_vencidas(ctx):
    por = defaultdict(lambda: dict(qtd=0, valor=Z, venc=None))
    for r in ctx.pendentes:
        if r.receber and r.vencimento < ctx.hoje:
            c = por[r.fornecedor]
            c["qtd"] += 1
            c["valor"] += r.saldo_aberto
            c["venc"] = min(c["venc"] or r.vencimento, r.vencimento)
    if not por:
        return None
    itens = sorted((dict(cliente=k, qtd=v["qtd"], vencimento=v["venc"], dias=(ctx.hoje - v["venc"]).days, valor=v["valor"])
                    for k, v in por.items()), key=lambda x: -x["valor"])
    total = sum(i["valor"] for i in itens)
    qtd = sum(i["qtd"] for i in itens)
    velho = max(itens, key=lambda x: x["dias"])
    return Resultado(f"{plural(len(itens), 'cliente', 'clientes')} com contas vencidas — {brl(total)}",
                     f"{plural(qtd, 'título', 'títulos')} em atraso. Maior devedor: {itens[0]['cliente']} ({brl(itens[0]['valor'])}). "
                     f"O mais antigo venceu há {velho['dias']} dias ({dma(velho['vencimento'])}).",
                     itens, [("cliente", "Cliente", "txt"), ("qtd", "Títulos", "int"), ("vencimento", "Mais antigo", "data"),
                             ("dias", "Dias", "int"), ("valor", "Em aberto", "brl")], total, qtd=qtd)


@regra("vence_hoje", "Contas que vencem hoje", "Financeiro", ATENCAO,
       "Confira se há saldo para pagar as de hoje e se os clientes de hoje foram lembrados. Depois de pagar ou receber, "
       "dê a baixa no Omie.", fonte="financeiro", link="fin_pagar")
def r_vence_hoje(ctx):
    rows = [r for r in ctx.pendentes if r.vencimento == ctx.hoje]
    if not rows:
        return None
    itens = sorted((dict(tipo="A receber" if r.receber else "A pagar", **_item_titulo(r, ctx.hoje)) for r in rows),
                   key=lambda x: (x["tipo"], -x["valor"]))
    rec = sum(i["valor"] for i in itens if i["tipo"] == "A receber")
    pag = sum(i["valor"] for i in itens if i["tipo"] == "A pagar")
    return Resultado(f"{plural(len(itens), 'conta vence', 'contas vencem')} hoje — {brl(rec + pag)}",
                     f"A pagar: {brl(pag)} · A receber: {brl(rec)}.", itens,
                     [("tipo", "Tipo", "txt")] + [c for c in COL_TITULO if c[0] != "dias"], rec + pag)


@regra("caixa_negativo", "Saldo de caixa projetado negativo em 30 dias", "Financeiro", CRITICO,
       "Antecipe recebimentos, negocie prazos com fornecedores ou reserve crédito antes da data indicada. "
       "Confira também se há contas lançadas em duplicidade no Omie.", fonte="financeiro", link="fin_fluxo")
def r_caixa_negativo(ctx):
    contas = list(SaldoContaOmie.objects.filter(fluxo_caixa=True))
    if not contas:
        raise RuntimeError("saldo atual das contas ainda não foi lido do Omie (roda na próxima sincronização)")
    saldo = sum((c.saldo for c in contas), Z)
    fim = ctx.hoje + timedelta(days=30)
    mov = defaultdict(lambda: [Z, Z])
    for r in ctx.pendentes:
        d = max(r.vencimento, ctx.hoje)          # vencidas entram como se fossem hoje
        if d <= fim:
            mov[d][0 if r.receber else 1] += r.saldo_aberto
    itens, acc, primeiro, menor = [], saldo, None, None
    for d in C.dias(ctx.hoje, fim):
        e, s = mov.get(d, (Z, Z))
        acc += e - s
        if e or s or d == ctx.hoje:
            itens.append(dict(data=d, entradas=e, saidas=s, saldo=acc))
        if acc < 0 and not primeiro:
            primeiro = (d, acc)
        if menor is None or acc < menor[1]:
            menor = (d, acc)
    if not primeiro:
        return None
    return Resultado(f"Caixa fica negativo em {dma(primeiro[0])} ({brl(primeiro[1])})",
                     f"Saldo atual nas contas: {brl(saldo)}. Somando o que há a receber e a pagar (vencidas contam como hoje), "
                     f"o menor saldo nos próximos 30 dias é {brl(menor[1])} em {dma(menor[0])}.",
                     itens, [("data", "Data", "data"), ("entradas", "A receber", "brl"), ("saidas", "A pagar", "brl"),
                             ("saldo", "Saldo projetado", "brl")], -menor[1], qtd=len(itens), extra=dict(sem_qtd=True))


def _mes(d):
    return d.year * 12 + d.month - 1


@regra("categoria_acima", "Despesa de categoria acima da média", "Financeiro", ATENCAO,
       "Abra os lançamentos da categoria no mês e confira se o gasto era esperado (compra pontual, reajuste) ou se há "
       "lançamento duplicado ou na categoria errada. Corrija a categoria no Omie, se for o caso.",
       fonte="financeiro", link="fluxo_caixa")
def r_categoria_acima(ctx):
    atual = _mes(ctx.hoje)
    soma = defaultdict(lambda: defaultdict(lambda: Z))
    for r in ctx.titulos:
        if r.receber:
            continue
        # pago conta pela data de pagamento; o que falta pagar, pelo vencimento
        if r.valor_pago and (r.data_pagamento or r.quitado):
            m = _mes(r.data_pagamento or r.vencimento)
            if atual - 3 <= m <= atual:
                soma[r.categoria][m] += abs(r.valor_pago)
        if r.saldo_aberto:
            m = _mes(r.vencimento)
            if atual - 3 <= m <= atual:
                soma[r.categoria][m] += r.saldo_aberto
    itens = []
    for cat, ms in soma.items():
        media = sum(ms.get(atual - k, Z) for k in (1, 2, 3)) / 3
        v = ms.get(atual, Z)
        if v > 2000 and v > media * Decimal("1.3"):
            itens.append(dict(categoria=cat, atual=v, media=media, pct=float(v / media - 1) if media else None, excesso=v - media))
    if not itens:
        return None
    itens.sort(key=lambda x: -x["excesso"])
    total = sum(i["excesso"] for i in itens)
    return Resultado(f"{plural(len(itens), 'categoria de despesa', 'categorias de despesa')} acima da média — {brl(total)} a mais",
                     f"Gasto deste mês (pagos pela data de pagamento, pendentes pelo vencimento) mais de 30% acima da média "
                     f"dos 3 meses anteriores e acima de R$ 2.000. Maior: {itens[0]['categoria']} ({brl(itens[0]['atual'])}).",
                     itens, [("categoria", "Categoria", "txt"), ("atual", "Este mês", "brl"), ("media", "Média 3 meses", "brl"),
                             ("pct", "Acima da média", "pct"), ("excesso", "Diferença", "brl")], total)


# ===================================================================== Vendas
@regra("cliente_parado", "Cliente frequente sem comprar", "Vendas", SABER,
       "Ligue ou visite o cliente: pergunte se houve problema de preço, prazo ou qualidade e ofereça o pedido de "
       "reposição. Registre o retorno com o vendedor da carteira.", fonte="vendas", link="fat_clientes")
def r_cliente_parado(ctx):
    atual = _mes(ctx.hoje)
    por = defaultdict(lambda: dict(meses=set(), ultima=None, total=Z, vendedor=""))
    for v in ctx.vendas:
        c = por[v.cliente]
        if v.data > (c["ultima"] or date.min):
            c["ultima"], c["vendedor"] = v.data, v.vendedor or ""
        if atual - 5 <= _mes(v.data) <= atual:
            c["meses"].add(_mes(v.data))
            c["total"] += v.total
    itens = [dict(cliente=k, vendedor=c["vendedor"], ultima=c["ultima"], dias=(ctx.hoje - c["ultima"]).days,
                  meses=len(c["meses"]), total=c["total"])
             for k, c in por.items() if len(c["meses"]) >= 3 and (ctx.hoje - c["ultima"]).days > 45]
    if not itens:
        return None
    itens.sort(key=lambda x: -x["total"])
    total = sum(i["total"] for i in itens)
    return Resultado(f"{plural(len(itens), 'cliente frequente', 'clientes frequentes')} há mais de 45 dias sem comprar",
                     f"Compraram em pelo menos 3 dos últimos 6 meses e pararam. Juntos compraram {brl(total)} nesses 6 meses. "
                     f"Maior: {itens[0]['cliente']} ({brl(itens[0]['total'])}, última compra em {dma(itens[0]['ultima'])}).",
                     itens, [("cliente", "Cliente", "txt"), ("vendedor", "Vendedor", "txt"), ("ultima", "Última compra", "data"),
                             ("dias", "Dias sem comprar", "int"), ("meses", "Meses com compra (de 6)", "int"),
                             ("total", "Comprou em 6 meses", "brl")], total)


def _casa_vendedor(nome_meta, nomes_omie):
    """Liga o nome da meta (ex.: AURICELIO) ao vendedor do Omie (ex.: Francisco Auricelio) por palavra igual."""
    alvo = set(C.sem_acento(nome_meta).split())
    achados = [n for n in nomes_omie if alvo & set(C.sem_acento(n).replace("(", " ").replace(")", " ").split())]
    return achados[0] if len(achados) == 1 else None


@regra("meta_ritmo", "Vendedor abaixo do ritmo da meta", "Vendas", ATENCAO,
       "Converse com o vendedor sobre os pedidos em negociação e a carteira parada; defina a meta das próximas semanas. "
       "As metas ficam em Faturamento → Pedidos e metas.", fonte="vendas", link="vendas_plasti")
def r_meta_ritmo(ctx):
    ini = ctx.hoje.replace(day=1)
    metas = list(MetaVendedor.objects.filter(mes=ini))
    if not metas:
        return None
    nomes = {v.vendedor for v in Venda.objects.filter(data__gte=ini - timedelta(days=120)).exclude(vendedor=None).only("vendedor")}
    uteis = C.dias_uteis_no_mes(ini.year, ini.month)
    passados = sum(1 for d in C.dias(ini, ctx.hoje) if C.eh_dia_util(d))
    fracao = Decimal(passados) / Decimal(uteis or 1)
    vendido = defaultdict(lambda: Z)
    for v in Venda.objects.filter(data__gte=ini, data__lte=ctx.hoje):
        vendido[v.vendedor] += v.total
    itens = []
    for m in metas:
        omie = _casa_vendedor(m.vendedor, nomes)
        if ctx.vendedor and omie != ctx.vendedor:
            continue
        esperado = m.meta * fracao
        real = vendido.get(omie, Z) if omie else Z
        if real < esperado * Decimal("0.9"):
            itens.append(dict(vendedor=f"{m.vendedor} ({omie})" if omie else f"{m.vendedor} (sem vendas no Omie com esse nome)",
                              meta=m.meta, esperado=esperado, real=real, pct=float(real / esperado) if esperado else None,
                              falta=esperado - real))
    if not itens:
        return None
    itens.sort(key=lambda x: -x["falta"])
    total = sum(i["falta"] for i in itens)
    return Resultado(f"{plural(len(itens), 'vendedor abaixo', 'vendedores abaixo')} do ritmo da meta — faltam {brl(total)}",
                     f"Até hoje passaram {passados} de {uteis} dias úteis do mês; o esperado é {int(fracao * 100)}% da meta "
                     f"(com 10% de folga).", itens,
                     [("vendedor", "Vendedor", "txt"), ("meta", "Meta do mês", "brl"), ("esperado", "Esperado até hoje", "brl"),
                      ("real", "Vendido", "brl"), ("pct", "Do ritmo", "pct"), ("falta", "Falta para o ritmo", "brl")], total)


@regra("meta_sem_cadastro", "Meta do mês não cadastrada", "Vendas", ATENCAO,
       "Cadastre a meta de cada vendedor para este mês em Faturamento → Pedidos e metas (Plasti). Sem meta, o sistema "
       "não consegue avisar quem está abaixo do ritmo.", fonte="vendas", link="vendas_plasti")
def r_meta_sem_cadastro(ctx):
    ini = ctx.hoje.replace(day=1)
    if ctx.vendedor or MetaVendedor.objects.filter(mes=ini).exists():
        return None
    ant = (ini - timedelta(days=1)).replace(day=1)
    por = defaultdict(lambda: Z)
    for v in Venda.objects.filter(data__gte=ant, data__lt=ini):
        por[v.vendedor or "(sem vendedor)"] += v.total
    itens = sorted((dict(vendedor=k, total=v) for k, v in por.items()), key=lambda x: -x["total"])
    if not itens:
        return None
    return Resultado(f"Metas de {C.rotulo_mes(ini.strftime('%Y-%m'))} não cadastradas",
                     f"Nenhum vendedor tem meta para este mês. A lista mostra quem vendeu no mês anterior.",
                     itens, [("vendedor", "Vendedor (Omie)", "txt"), ("total", "Vendeu no mês anterior", "brl")],
                     qtd=len(itens), extra=dict(sem_valor=True))


@regra("preco_baixo", "Venda com preço abaixo da média", "Vendas", ATENCAO,
       "Confira com o vendedor se o desconto foi autorizado. Se foi erro de digitação, corrija a nota/pedido; se foi "
       "negociação, registre o motivo para não virar o preço padrão do cliente.", fonte="vendas", link="fat_notas")
def r_preco_baixo(ctx):
    base = sorted((v for v in ctx.vendas if v.valor_unitario and v.valor_unitario > 0 and v.quantidade), key=lambda v: v.data)
    if ctx.vendedor:
        base = sorted((v for v in Venda.objects.filter(data__gte=ctx.hoje - timedelta(days=130))
                       if v.valor_unitario and v.valor_unitario > 0 and v.quantidade), key=lambda v: v.data)
    por_prod = defaultdict(list)
    for v in base:
        por_prod[v.produto].append(v)
    itens = []
    desde = ctx.hoje - timedelta(days=30)
    for prod, vs in por_prod.items():
        for v in vs:
            if v.data < desde or (ctx.vendedor and v.vendedor != ctx.vendedor):
                continue
            ant = [x.valor_unitario for x in vs if v.data - timedelta(days=90) <= x.data < v.data]
            if len(ant) < 3:
                continue
            media = sum(ant) / len(ant)
            if v.valor_unitario < media * Decimal("0.8"):
                itens.append(dict(data=v.data, nota=v.nota_fiscal or "—", cliente=v.cliente, vendedor=v.vendedor or "",
                                  produto=prod, preco=v.valor_unitario, media=media, pct=float(1 - v.valor_unitario / media),
                                  perda=(media - v.valor_unitario) * v.quantidade))
    if not itens:
        return None
    itens.sort(key=lambda x: -x["perda"])
    total = sum(i["perda"] for i in itens)
    return Resultado(f"{plural(len(itens), 'venda', 'vendas')} com preço 20% abaixo da média — {brl(total)} a menos",
                     f"Vendas dos últimos 30 dias comparadas com a média do mesmo produto nos 3 meses anteriores. "
                     f"Maior diferença: {itens[0]['produto']} para {itens[0]['cliente']} em {dma(itens[0]['data'])}.",
                     itens, [("data", "Data", "data"), ("nota", "Nota", "txt"), ("cliente", "Cliente", "txt"),
                             ("vendedor", "Vendedor", "txt"), ("produto", "Produto", "txt"), ("preco", "Preço", "brl"),
                             ("media", "Média 3 meses", "brl"), ("pct", "Abaixo", "pct"), ("perda", "Diferença no total", "brl")], total)


@regra("pedido_parado_faturar", "Pedido parado na etapa Faturar", "Vendas", ATENCAO,
       "Confira com o faturamento por que a nota não saiu (estoque, cadastro do cliente, crédito ou erro fiscal) e emita a "
       "nota no Omie (Vendas → Pedidos → Faturar). Se o pedido não vai mais sair, cancele-o no Omie.",
       fonte="pedidos", link="fat_pedidos")
def r_pedido_parado_faturar(ctx):
    q = PedidoOmie.objects.filter(etapa="50", faturado=False, cancelado=False, devolvido=False)
    if ctx.vendedor:
        q = q.filter(vendedor=ctx.vendedor)
    itens = []
    for p in q:
        desde = p.data_alteracao or p.data_inclusao
        if desde and (ctx.hoje - desde).days > 3:
            itens.append(dict(numero=p.numero, cliente=p.cliente, vendedor=p.vendedor, previsao=p.data_previsao, desde=desde,
                              dias=(ctx.hoje - desde).days, valor=p.valor_total))
    if not itens:
        return None
    itens.sort(key=lambda x: (-x["dias"], -x["valor"]))
    total = sum(i["valor"] for i in itens)
    return Resultado(f"{plural(len(itens), 'pedido parado', 'pedidos parados')} na etapa Faturar há mais de 3 dias — {brl(total)}",
                     f"O mais antigo é o pedido {itens[0]['numero']} ({itens[0]['cliente']}), sem mudança há {itens[0]['dias']} dias.",
                     itens, [("numero", "Pedido", "txt"), ("cliente", "Cliente", "txt"), ("vendedor", "Vendedor", "txt"),
                             ("previsao", "Previsão", "data"), ("desde", "Última mudança", "data"), ("dias", "Dias parado", "int"),
                             ("valor", "Valor", "brl")], total)


# ===================================================================== Estoque
def _q(v):
    return int(round(v or 0))


@regra("estoque_falta_pedidos", "Pedido a faturar sem estoque suficiente", "Estoque", CRITICO,
       "Programe a produção desses produtos (ou transfira de outro local no Omie) antes de faturar. Se o saldo do Omie estiver "
       "errado, faça o ajuste de estoque lá. Veja tudo em Estoque → Cobertura.",
       fonte="estoque", link="est_cobertura")
def r_estoque_falta_pedidos(ctx):
    from .estoque import calcular_cobertura
    itens = [dict(codigo=r["codigo"], produto=r["descricao"], saldo=_q(r["saldo"]), pedidos=_q(r["em_pedidos"]), falta=_q(r["falta"]))
             for r in calcular_cobertura(ctx.hoje) if r["falta"] > 0]
    if not itens:
        return None
    itens.sort(key=lambda x: -x["falta"])
    return Resultado(f"{plural(len(itens), 'produto', 'produtos')} sem estoque para os pedidos na etapa Faturar",
                     f"Maior falta: {itens[0]['produto']} — pedidos pedem {itens[0]['pedidos']}, há {itens[0]['saldo']} no Produto Acabado.",
                     itens, [("codigo", "Código", "txt"), ("produto", "Produto", "txt"), ("saldo", "Saldo", "int"),
                             ("pedidos", "Em pedidos a faturar", "int"), ("falta", "Falta", "int")],
                     qtd=len(itens), extra=dict(sem_valor=True, rot_qtd="produtos"))


@regra("estoque_negativo", "Estoque negativo", "Estoque", CRITICO,
       "Saldo negativo indica saída lançada sem a entrada correspondente. Confira as movimentações do produto no Omie e lance "
       "a entrada da ordem de produção ou o ajuste de estoque que faltou.",
       fonte="estoque", link="est_posicao")
def r_estoque_negativo(ctx):
    itens = [dict(codigo=e.codigo, produto=e.descricao, local=e.local, saldo=_q(e.saldo))
             for e in EstoqueOmie.objects.filter(saldo__lt=0)]
    if not itens:
        return None
    itens.sort(key=lambda x: x["saldo"])
    return Resultado(f"{plural(len(itens), 'produto', 'produtos')} com estoque negativo",
                     f"Menor saldo: {itens[0]['produto']} ({itens[0]['saldo']}) em {itens[0]['local']}.",
                     itens, [("codigo", "Código", "txt"), ("produto", "Produto", "txt"), ("local", "Local", "txt"), ("saldo", "Saldo", "int")],
                     qtd=len(itens), extra=dict(sem_valor=True, rot_qtd="produtos"))


@regra("estoque_abaixo_minimo", "Produto abaixo do estoque mínimo", "Estoque", ATENCAO,
       "Programe a produção (ou a compra) para repor o estoque. Se o mínimo cadastrado no Omie estiver errado, ajuste-o no "
       "cadastro do produto (Estoque → Produtos no Omie).",
       fonte="estoque", link="est_posicao")
def r_estoque_abaixo_minimo(ctx):
    saldos = {}
    for cod, sd in EstoqueOmie.objects.values_list("codigo_produto", "saldo"):
        saldos[cod] = saldos.get(cod, 0) + sd
    itens = []
    for p in ProdutoOmie.objects.filter(inativo=False, estoque_minimo__gt=0):
        sd = saldos.get(p.codigo_produto, 0)
        if sd < p.estoque_minimo:
            itens.append(dict(codigo=p.codigo, produto=p.descricao, saldo=_q(sd), minimo=_q(p.estoque_minimo), falta=_q(p.estoque_minimo - sd)))
    if not itens:
        return None
    itens.sort(key=lambda x: -x["falta"])
    return Resultado(f"{plural(len(itens), 'produto', 'produtos')} abaixo do estoque mínimo",
                     f"Maior falta: {itens[0]['produto']} — tem {itens[0]['saldo']}, mínimo {itens[0]['minimo']}.",
                     itens, [("codigo", "Código", "txt"), ("produto", "Produto", "txt"), ("saldo", "Saldo", "int"),
                             ("minimo", "Mínimo", "int"), ("falta", "Falta", "int")],
                     qtd=len(itens), extra=dict(sem_valor=True, rot_qtd="produtos"))


@regra("estoque_parado", "Produto acabado parado", "Estoque", SABER,
       "Estoque sem saída há mais de 90 dias prende dinheiro. Avalie promoção com os vendedores, ofereça aos clientes que "
       "já compraram o produto ou reaproveite o material. Veja a lista em Estoque → Cobertura (situação Parado).",
       fonte="estoque", link="est_cobertura")
def r_estoque_parado(ctx):
    from .estoque import calcular_cobertura
    custo = {e.codigo_produto: e.custo_medio for e in EstoqueOmie.objects.filter(local_codigo="PA")}
    itens = [dict(codigo=r["codigo"], produto=r["descricao"], saldo=_q(r["saldo"]), ultima=r["ultima"], dias=r["sem_saida"],
                  valor=round(r["saldo"] * custo.get(r["codigo_produto"], 0), 2))
             for r in calcular_cobertura(ctx.hoje) if r["situacao"] == "Parado"]
    if not itens:
        return None
    itens.sort(key=lambda x: -x["valor"])
    total = sum(i["valor"] for i in itens)
    return Resultado(f"{plural(len(itens), 'produto parado', 'produtos parados')} há mais de 90 dias — {brl(total)} em estoque",
                     f"Maior valor parado: {itens[0]['produto']} ({brl(itens[0]['valor'])}).",
                     itens, [("codigo", "Código", "txt"), ("produto", "Produto", "txt"), ("saldo", "Saldo", "int"),
                             ("ultima", "Última saída", "data"), ("dias", "Dias sem saída", "int"), ("valor", "Valor (custo)", "brl")],
                     total)


@regra("estoque_custo_suspeito", "Custo médio do estoque suspeito", "Estoque", SABER,
       "No Omie, confira o custo do produto (entradas de ordem de produção sem custo ou ajuste inicial com valor errado) e "
       "corrija com um ajuste de custo. Enquanto isso o valor do estoque fica errado.",
       fonte="estoque", link="est_posicao")
def r_estoque_custo_suspeito(ctx):
    from .estoque import custo_suspeito
    itens = [dict(codigo=e.codigo, produto=e.descricao, local=e.local, saldo=_q(e.saldo), custo=e.custo_medio, preco=e.preco)
             for e in EstoqueOmie.objects.filter(saldo__gt=0) if custo_suspeito(e)]
    if not itens:
        return None
    return Resultado(f"{plural(len(itens), 'produto', 'produtos')} com custo médio zerado ou muito baixo",
                     "Custo médio menor que 2% do preço de venda (ou zerado) — o valor em estoque desses itens está errado.",
                     itens, [("codigo", "Código", "txt"), ("produto", "Produto", "txt"), ("local", "Local", "txt"), ("saldo", "Saldo", "int"),
                             ("custo", "Custo médio", "brl"), ("preco", "Preço de venda", "brl")],
                     qtd=len(itens), extra=dict(sem_valor=True, rot_qtd="produtos"))


# ===================================================================== Produção
@regra("sem_apontamento", "Produção sem apontamento", "Produção", CRITICO,
       "Peça aos líderes de turno para lançar os apontamentos em Produção → Apontamentos (ou importar a planilha). "
       "Sem eles, os relatórios de produção e perda ficam errados.", fonte="producao", link="apontamentos")
def r_sem_apontamento(ctx):
    dias = dias_uteis_antes(ctx.hoje, 2)
    if Apontamento.objects.filter(data__in=dias).exists():
        return None
    ult = Apontamento.objects.aggregate(d=Max("data"))["d"]
    sem = sum(1 for d in C.dias(ult + timedelta(days=1), ctx.hoje - timedelta(days=1)) if C.eh_dia_util(d)) if ult else None
    itens = [dict(data=d, dia=C.DIAS_SEMANA[d.weekday()]) for d in sorted(dias)]
    return Resultado(f"Nenhum apontamento de produção nos últimos 2 dias úteis",
                     (f"O último apontamento é de {dma(ult)} — {plural(sem, 'dia útil', 'dias úteis')} sem lançamento." if ult
                      else "Ainda não há nenhum apontamento lançado."),
                     itens, [("data", "Dia útil sem apontamento", "data"), ("dia", "Dia", "txt")],
                     qtd=sem if sem is not None else len(itens), extra=dict(sem_valor=True, rot_qtd="dias úteis"))


@regra("perda_maquina", "Máquina com perda alta", "Produção", ATENCAO,
       "Verifique na máquina a regulagem, a matéria-prima e o operador do período. Confira também se a apara, alça e "
       "borra foram apontadas no campo certo.", fonte="producao", link="relatorios")
def r_perda_maquina(ctx):
    de = ctx.hoje - timedelta(days=7)
    por = defaultdict(lambda: [Z, Z])
    for a in Apontamento.objects.filter(data__gte=de, data__lt=ctx.hoje).select_related("maquina"):
        perda = (a.apara_kg or Z) + (a.alca_kg or Z) + (a.borra_kg or Z)
        k = f"{a.maquina.codigo} — {a.maquina.descricao}"
        por[k][0] += (a.ok_kg or Z) + perda
        por[k][1] += perda
    itens = [dict(maquina=k, total=t, perda=p, pct=float(p / t)) for k, (t, p) in por.items()
             if t >= PERDA_KG_MINIMO and p / t > Decimal(str(PERDA_MAXIMA))]
    if not itens:
        return None
    itens.sort(key=lambda x: -x["pct"])
    kg = sum(i["perda"] for i in itens)
    return Resultado(f"{plural(len(itens), 'máquina', 'máquinas')} com perda acima de {int(PERDA_MAXIMA * 100)}% nos últimos 7 dias",
                     f"{kg:,.0f} kg de perda. Maior: {itens[0]['maquina']} ({itens[0]['pct'] * 100:.1f}%).".replace(",", "."),
                     itens, [("maquina", "Máquina", "txt"), ("total", "Processado", "kg"), ("perda", "Perda", "kg"),
                             ("pct", "Perda %", "pct")], qtd=len(itens), extra=dict(sem_valor=True))


# ===================================================================== Cadastro
@regra("titulo_sem_cnpj", "Fornecedor/cliente sem CNPJ ou CPF", "Cadastro", ATENCAO,
       "Complete o CNPJ/CPF no cadastro do cliente ou fornecedor no Omie (Geral → Clientes e Fornecedores). Sem ele "
       "não dá para emitir boleto, nota ou conferir duplicidade.", fonte="cadastro")
def r_titulo_sem_cnpj(ctx):
    desde = ctx.hoje - timedelta(days=90)
    por = defaultdict(lambda: [0, Z])
    for r in ctx.titulos:
        if "natureza de operacao" in C.sem_acento(r.fornecedor):   # lançamento interno do Omie, não é cadastro
            continue
        if (r.data_pagamento or r.vencimento) >= desde and not (r.cnpj_cpf or "").strip():
            por[r.fornecedor][0] += 1
            por[r.fornecedor][1] += abs(r.valor_conta)
    if not por:
        return None
    itens = sorted((dict(parte=k, qtd=q, valor=v) for k, (q, v) in por.items()), key=lambda x: -x["valor"])
    return Resultado(f"{plural(len(itens), 'cadastro', 'cadastros')} sem CNPJ/CPF com contas nos últimos 90 dias",
                     f"{plural(sum(i['qtd'] for i in itens), 'título', 'títulos')} no total. Maior: {itens[0]['parte']}.",
                     itens, [("parte", "Fornecedor/Cliente (Omie)", "txt"), ("qtd", "Títulos", "int"), ("valor", "Valor", "brl")],
                     sum(i["valor"] for i in itens))


@regra("venda_sem_vendedor", "Venda sem vendedor", "Cadastro", ATENCAO,
       "Informe o vendedor no cadastro do cliente no Omie (aba Vendedor) e nos pedidos. Sem vendedor a venda não "
       "conta para meta nem comissão.", fonte="vendas", link="fat_notas")
def r_venda_sem_vendedor(ctx):
    if ctx.vendedor:
        return None
    desde = ctx.hoje - timedelta(days=90)
    por = defaultdict(lambda: [0, Z, None])
    for v in Venda.objects.filter(data__gte=desde):
        if not (v.vendedor or "").strip():
            c = por[v.cliente]
            c[0] += 1
            c[1] += v.total
            c[2] = max(c[2] or v.data, v.data)
    if not por:
        return None
    itens = sorted((dict(cliente=k, qtd=q, ultima=u, valor=t) for k, (q, t, u) in por.items()), key=lambda x: -x["valor"])
    return Resultado(f"{plural(sum(i['qtd'] for i in itens), 'item de venda', 'itens de venda')} sem vendedor nos últimos 90 dias",
                     f"{plural(len(itens), 'cliente', 'clientes')}. Maior: {itens[0]['cliente']} ({brl(itens[0]['valor'])}).",
                     itens, [("cliente", "Cliente", "txt"), ("qtd", "Itens", "int"), ("ultima", "Última venda", "data"),
                             ("valor", "Valor", "brl")], sum(i["valor"] for i in itens), qtd=sum(i["qtd"] for i in itens))


@regra("maquina_sem_capacidade", "Máquina sem capacidade cadastrada", "Cadastro", ATENCAO,
       "Informe a capacidade (kg/h) da máquina em Cadastros → Máquinas. Ela é usada no cálculo de utilização.",
       fonte="cadastro", link="cadastro:maquinas")
def r_maquina_sem_capacidade(ctx):
    ms = list(Maquina.objects.filter(ativo=True, capacidade_kg_h=None).select_related("familia__setor"))
    if not ms:
        return None
    itens = [dict(codigo=m.codigo, descricao=m.descricao, setor=m.familia.setor.nome) for m in ms]
    return Resultado(f"{plural(len(itens), 'máquina ativa', 'máquinas ativas')} sem capacidade cadastrada", "Sem a capacidade, o painel "
                     "de chão de fábrica não calcula a utilização dessas máquinas.", itens,
                     [("codigo", "Código", "txt"), ("descricao", "Descrição", "txt"), ("setor", "Setor", "txt")],
                     extra=dict(sem_valor=True))


@regra("apontamento_sem_op", "Apontamento sem OP", "Cadastro", ATENCAO,
       "Abra o apontamento em Produção → Apontamentos e informe o número da OP. Sem OP não dá para saber de qual "
       "cliente/pedido foi a produção.", fonte="producao", link="apontamentos")
def r_apontamento_sem_op(ctx):
    desde = ctx.hoje - timedelta(days=30)
    aps = list(Apontamento.objects.filter(data__gte=desde).select_related("maquina", "turno").order_by("-data"))
    aps = [a for a in aps if not (a.op or "").strip() and (a.ok_kg or 0) > 0]   # parada sem produção não precisa de OP
    if not aps:
        return None
    itens = [dict(data=a.data, turno=a.turno.codigo, maquina=a.maquina.codigo, kg=a.ok_kg) for a in aps]
    return Resultado(f"{plural(len(itens), 'apontamento', 'apontamentos')} sem OP nos últimos 30 dias",
                     f"{sum(i['kg'] for i in itens):,.0f} kg produzidos sem OP informada.".replace(",", "."),
                     itens, [("data", "Data", "data"), ("turno", "Turno", "txt"), ("maquina", "Máquina", "txt"), ("kg", "Produzido OK", "kg")],
                     extra=dict(sem_valor=True))


# ===================================================================== Sistema
def _horario_comercial(agora):
    return agora.weekday() < 5 and 8 <= agora.hour < 19


@regra("omie_atrasado", "Integração com o Omie atrasada", "Sistema", ATENCAO,
       "Abra Sistema → Integração Omie e veja a mensagem da última tentativa. Se for chave vencida, troque em "
       "Sistema → Integrações (chaves). Se o erro continuar, avise o suporte.", fonte="sistema", link="omie")
def r_omie_atrasado(ctx):
    ult = SincronizacaoOmie.objects.order_by("-inicio").first()
    ok = SincronizacaoOmie.objects.filter(status="ok").order_by("-fim").first()
    horas = (ctx.agora - ok.fim).total_seconds() / 3600 if ok and ok.fim else None
    problema_erro = ult and ult.status == "erro"
    atrasado = horas is None or (horas > 2 and _horario_comercial(ctx.agora)) or horas > 16
    if not (problema_erro or atrasado):
        return None
    itens = [dict(inicio=timezone.localtime(s.inicio).strftime("%d/%m/%Y %H:%M"), status=s.status,
                  mensagem=(s.mensagem or "")[:160]) for s in SincronizacaoOmie.objects.order_by("-inicio")[:5]]
    desc = (f"A última sincronização certa foi em {timezone.localtime(ok.fim).strftime('%d/%m/%Y %H:%M')} (há {horas:.0f} h)."
            if ok and ok.fim else "Nenhuma sincronização terminou certo ainda.")
    if problema_erro:
        desc += f" A última tentativa deu erro: {(ult.mensagem or '')[:160]}"
    return Resultado("Dados do Omie desatualizados" if atrasado else "Última sincronização com o Omie deu erro", desc, itens,
                     [("inicio", "Início", "txt"), ("status", "Situação", "txt"), ("mensagem", "Mensagem", "txt")],
                     qtd=1, extra=dict(sem_valor=True, sem_qtd=True))


@regra("vendas_atrasadas", "Dados de vendas atrasados", "Sistema", ATENCAO,
       "Importe a planilha de vendas em Faturamento → Visão geral (Omie) → Importar, ou peça a sincronização de vendas "
       "com o Omie (está pausada até resolver a questão das NFs de Bobina).", fonte="vendas", link="vendas")
def r_vendas_atrasadas(ctx):
    ult = Venda.objects.aggregate(d=Max("data"))["d"]
    if ult and len([d for d in C.dias(ult + timedelta(days=1), ctx.hoje - timedelta(days=1)) if C.eh_dia_util(d)]) <= 3:
        return None
    uteis = sum(1 for d in C.dias(ult + timedelta(days=1), ctx.hoje - timedelta(days=1)) if C.eh_dia_util(d)) if ult else 0
    return Resultado("Vendas sem dados há mais de 3 dias úteis",
                     f"A venda mais recente no ERP é de {dma(ult)} ({plural(uteis, 'dia útil', 'dias úteis')})." if ult
                     else "Nenhuma venda carregada.", [dict(ultima=ult)], [("ultima", "Venda mais recente", "data")],
                     qtd=1, extra=dict(sem_valor=True, sem_qtd=True))


@regra("saldo_atrasado", "Saldo das contas desatualizado", "Sistema", ATENCAO,
       "O saldo das contas é lido do Omie a cada sincronização. Confira em Sistema → Integração Omie se a "
       "sincronização está rodando.", fonte="sistema", link="omie")
def r_saldo_atrasado(ctx):
    ult = SaldoContaOmie.objects.aggregate(d=Max("atualizado_em"))["d"]
    if ult and (ctx.agora - ult).total_seconds() < 6 * 3600:
        return None
    if not ult:
        return None          # ainda não foi lido: a regra do caixa já avisa
    return Resultado("Saldo das contas não é atualizado há mais de 6 horas",
                     f"Última leitura em {timezone.localtime(ult).strftime('%d/%m/%Y %H:%M')}.",
                     [dict(conta=c.descricao, saldo=c.saldo) for c in SaldoContaOmie.objects.all()],
                     [("conta", "Conta", "txt"), ("saldo", "Saldo lido", "brl")], qtd=1, extra=dict(sem_valor=True, sem_qtd=True))


# ===================================================================== motor
def areas_do_usuario(user):
    if user.is_superuser or user.is_staff:
        return set(AREAS)
    grupos = set(user.groups.values_list("name", flat=True))
    areas = {a for a in AREAS if a in grupos}
    if vendedor_do_usuario(user):
        areas.add("Vendas")
    return areas


def vendedor_do_usuario(user):
    if user.is_superuser or user.is_staff:
        return None
    p = getattr(user, "perfil_erp", None)
    if not p:
        return None
    return (p.vendedor or "").strip() or None


def conferir(user=None, hoje=None, agora=None, regras=None):
    """Roda as regras visíveis para o usuário. Devolve (resultados, dispensados)."""
    from .models import DispensaProblema
    areas = areas_do_usuario(user) if user else set(AREAS)
    ctx = Contexto(hoje=hoje, vendedor=vendedor_do_usuario(user) if user else None, agora=agora)
    dispensas = {}
    for d in DispensaProblema.objects.filter(volta_em__gt=ctx.hoje).select_related("usuario"):
        dispensas.setdefault(d.regra, d)
    resultados, dispensados = [], []
    for rg in regras or REGRAS:
        if rg.area not in areas:
            continue
        try:
            res = rg.fn(ctx)
        except Exception as e:  # uma regra com erro não derruba as outras
            log.exception("Regra %s falhou", rg.id)
            if "Sistema" in areas:
                res = Resultado(f"Não foi possível conferir: {rg.nome}", f"Erro: {str(e)[:200]}", [], [], erro=True,
                                extra=dict(sem_valor=True, sem_qtd=True))
                res.regra = Regra(f"erro_{rg.id}", rg.nome, "Sistema", ATENCAO,
                                  "Se o aviso continuar nas próximas conferências, avise o suporte com o texto do erro.", None, "sistema")
                resultados.append(res)
            continue
        if not res:
            continue
        res.regra = rg
        res.fonte_txt = ctx.fontes.get(rg.fonte, "")
        if rg.id in dispensas:
            res.dispensa = dispensas[rg.id]
            dispensados.append(res)
        else:
            resultados.append(res)
    chave = lambda r: (ORDEM_GRAV[r.regra.gravidade], -(r.valor or 0))
    resultados.sort(key=chave)
    dispensados.sort(key=chave)
    return resultados, dispensados
