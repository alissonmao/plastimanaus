from django.urls import path

from . import painel, views

urlpatterns = [
    path("", painel.painel, name="sec_painel"),
    path("inicio/", painel.inicio, name="inicio"),
    path("email/", views.caixa, name="sec_caixa"),
    path("email/escrever/", views.escrever, name="sec_escrever"),
    path("email/sugerir/", views.sugerir, name="sec_sugerir"),
    path("email/contas/", views.contas, name="sec_contas"),
    path("email/contas/nova/", views.conta_form, name="sec_conta_nova"),
    path("email/contas/<uuid:pk>/", views.conta_form, name="sec_conta_editar"),
    path("email/<uuid:pk>/<int:uid>/", views.ler, name="sec_ler"),
    path("email/<uuid:pk>/<int:uid>/anexo/<int:n>/", views.anexo, name="sec_anexo"),
    path("email/<uuid:pk>/<int:uid>/acao/", views.acao, name="sec_acao"),
]
