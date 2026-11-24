from django.urls import reverse

from .cadastros import CADASTROS

# (seção, ícone, [(rota, rótulo, args/querystring)])
MENU = [
    ("Financeiro", "💰", [
        ("fluxo_caixa", "Visão geral", None),
        ("fin_receber", "Contas a receber", None),
        ("fin_pagar", "Contas a pagar", None),
        ("fin_atrasados", "Inadimplência", None),
        ("fin_fluxo", "Fluxo de caixa projetado", None),
        ("fin_dre", "DRE gerencial", None),
        ("fin_extrato", "Extrato por conta", None),
    ]),
    ("Faturamento", "📈", [
        ("vendas", "Visão geral (Omie)", None),
        ("fat_notas", "Notas fiscais", None),
        ("fat_clientes", "Clientes", None),
        ("fat_vendedores", "Vendedores", None),
        ("fat_produtos", "Produtos", None),
        ("vendas_plasti", "Pedidos e metas (Plasti)", None),
    ]),
    ("Produção", "🏭", [
        ("dashboard", "Chão de fábrica", None),
        ("apontamentos", "Apontamentos", None),
        ("relatorios", "Relatórios", None),
    ]),
    ("Cadastros", "🗂️", [("cadastro", v["titulo"], [k]) for k, v in CADASTROS.items()]),
    ("Sistema", "⚙️", [
        ("omie", "Integração Omie", None),
    ]),
]


def menu(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    path = request.path
    secoes = []
    for titulo, icone, itens in MENU:
        links = []
        for rota, rotulo, args in itens:
            url = reverse(rota, args=args or [])
            links.append(dict(url=url, label=rotulo,
                              ativo=path == url or (url != "/" and path.startswith(url) and len(url) > 1)))
        # Só o mais específico fica ativo (ex.: /financeiro/receber/ e /financeiro/receber/123/)
        secoes.append(dict(titulo=titulo, icone=icone, itens=links, aberta=any(l["ativo"] for l in links)))
    if request.user.is_staff:
        secoes[-1]["itens"].append(dict(url="/admin/", label="Administração", ativo=False))
    return {"menu": secoes}
