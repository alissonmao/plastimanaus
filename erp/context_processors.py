from django.urls import reverse

from secretaria.acesso import tem_secretaria

from .cadastros import CADASTROS

# (seção, ícone, [(rota, rótulo, args/querystring)])
MENU = [
    ("Painel", "🏠", [("sec_painel", "Painel", None)]),
    ("Secretaria", "🗓️", [
        ("sec_caixa", "E-mail", None),
    ]),
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
    secretaria = tem_secretaria(request.user)
    for titulo, icone, itens in MENU:
        if titulo in ("Painel", "Secretaria") and not secretaria:
            continue
        if titulo == "Cadastros" and request.user.is_staff:
            itens = itens + [("usuarios", "Usuários", None)]
        links = []
        for rota, rotulo, args in itens:
            url = reverse(rota, args=args or [])
            links.append(dict(url=url, label=rotulo,
                              ativo=path == url or (titulo != "Painel" and url != "/" and path.startswith(url) and len(url) > 1)))
        # Só o mais específico fica ativo (ex.: /secretaria/email/ e /secretaria/email/contas/)
        ativos = [l for l in links if l["ativo"]]
        for l in ativos:
            l["ativo"] = len(l["url"]) == max(len(x["url"]) for x in ativos)
        secoes.append(dict(titulo=titulo, icone=icone, itens=links, aberta=any(l["ativo"] for l in links), direto=titulo == "Painel"))
    if request.user.is_staff:
        secoes[-1]["itens"].append(dict(url="/admin/", label="Administração", ativo=False))
    return {"menu": secoes}
