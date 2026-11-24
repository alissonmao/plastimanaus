from django.urls import reverse

from .cadastros import CADASTROS

PRODUCAO = [
    ("fluxo_caixa", "Entradas e Saídas base Omie", "💰"),
    ("vendas_plasti", "Vendas base Plasti Manaus", "🛒"),
    ("vendas", "Faturamento base Omie", "📈"),
    ("dashboard", "Chão de Fábrica - Produção", "🏭"),
    ("apontamentos", "Apontamentos", "📋"),
    ("relatorios", "Relatórios", "📊"),
    ("omie", "Integração Omie", "🔄"),
]


def menu(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    path = request.path
    prod = [dict(url=reverse(n), label=l, icone=i) for n, l, i in PRODUCAO]
    cad = [dict(url=reverse("cadastro", args=[k]), label=v["titulo"], icone="•") for k, v in CADASTROS.items()]
    for it in prod + cad:
        it["ativo"] = path == it["url"] or (it["url"] != "/" and path.startswith(it["url"]))
    return {"menu_producao": prod, "menu_cadastros": cad}
