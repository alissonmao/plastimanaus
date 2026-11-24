from django.http import HttpResponse
from django.urls import path

from . import views

urlpatterns = [
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
    path("cadastros/<slug:nome>/", views.cadastro_lista, name="cadastro"),
    path("cadastros/<slug:nome>/novo/", views.cadastro_form, name="cadastro_novo"),
    path("cadastros/<slug:nome>/<uuid:pk>/", views.cadastro_form, name="cadastro_editar"),
    path("saude/", lambda r: HttpResponse("ok"), name="saude"),
]
