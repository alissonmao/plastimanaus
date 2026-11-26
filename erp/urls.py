from django.http import HttpResponse
from django.urls import path

from . import faturamento as fat
from . import financeiro as fin
from . import favoritos, pedidos, problemas_views, usuarios, views

from . import auditoria

urlpatterns = [
    path("favoritos/alternar/", favoritos.alternar, name="favorito_alternar"),
    path("problemas/", problemas_views.tela, name="problemas"),
    path("problemas/dispensar/", problemas_views.dispensar, name="problemas_dispensar"),
    path("problemas/desfazer/<int:pk>/", problemas_views.desfazer, name="problemas_desfazer"),
    path("sistema/auditoria-omie/", auditoria.tela, name="auditoria_omie"),
    path("", views.dashboard, name="dashboard"),
    path("apontamentos/", views.apontamentos, name="apontamentos"),
    path("apontamentos/novo/", views.apontamento_form, name="apontamento_novo"),
    path("apontamentos/importar/", views.apontamentos_importar, name="apontamentos_importar"),
    path("apontamentos/<uuid:pk>/", views.apontamento_form, name="apontamento_editar"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("vendas/", views.vendas, name="vendas"),
    path("vendas/importar/", views.vendas_importar, name="vendas_importar"),
    path("vendas-plasti/", views.vendas_plasti, name="vendas_plasti"),
    path("fluxo-caixa/", views.fluxo_caixa, name="fluxo_caixa"),
    path("fluxo-caixa/importar/", views.fluxo_importar, name="fluxo_importar"),
    path("financeiro/receber/", fin.receber, name="fin_receber"),
    path("financeiro/pagar/", fin.pagar, name="fin_pagar"),
    path("financeiro/titulo/<uuid:pk>/", fin.titulo, name="fin_titulo"),
    path("financeiro/inadimplencia/", fin.atrasados, name="fin_atrasados"),
    path("financeiro/fluxo-projetado/", fin.fluxo_projetado, name="fin_fluxo"),
    path("financeiro/dre/", fin.dre, name="fin_dre"),
    path("financeiro/extrato/", fin.extrato, name="fin_extrato"),
    path("faturamento/notas/", fat.notas, name="fat_notas"),
    path("faturamento/pedidos/", pedidos.lista, name="fat_pedidos"),
    path("faturamento/clientes/", fat.clientes, name="fat_clientes"),
    path("faturamento/vendedores/", fat.vendedores, name="fat_vendedores"),
    path("faturamento/produtos/", fat.produtos, name="fat_produtos"),
    path("cadastros/<slug:nome>/", views.cadastro_lista, name="cadastro"),
    path("cadastros/<slug:nome>/novo/", views.cadastro_form, name="cadastro_novo"),
    path("cadastros/<slug:nome>/<uuid:pk>/", views.cadastro_form, name="cadastro_editar"),
    path("usuarios/", usuarios.lista, name="usuarios"),
    path("usuarios/novo/", usuarios.form, name="usuario_novo"),
    path("usuarios/<int:pk>/", usuarios.form, name="usuario_editar"),
    path("omie/", views.omie_view, name="omie"),
    path("saude/", lambda r: HttpResponse("ok"), name="saude"),
]
