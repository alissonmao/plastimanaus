from django.urls import path

from . import agenda, angel_api, configuracoes, diario, lembretes, painel, views, voz

urlpatterns = [
    path("", painel.painel, name="sec_painel"),
    path("inicio/", painel.inicio, name="inicio"),
    # E-mail
    path("email/", views.caixa, name="sec_caixa"),
    path("email/escrever/", views.escrever, name="sec_escrever"),
    path("email/sugerir/", views.sugerir, name="sec_sugerir"),
    path("email/contas/", views.contas, name="sec_contas"),
    path("email/contas/nova/", views.conta_form, name="sec_conta_nova"),
    path("email/contas/<uuid:pk>/", views.conta_form, name="sec_conta_editar"),
    path("email/<uuid:pk>/<int:uid>/", views.ler, name="sec_ler"),
    path("email/<uuid:pk>/<int:uid>/anexo/<int:n>/", views.anexo, name="sec_anexo"),
    path("email/<uuid:pk>/<int:uid>/acao/", views.acao, name="sec_acao"),
    # Agenda
    path("agenda/", agenda.tela, name="sec_agenda"),
    path("agenda/salvar/", agenda.salvar, name="sec_agenda_salvar"),
    # Lembretes
    path("lembretes/", lembretes.lista, name="sec_lembretes"),
    path("lembretes/novo/", lembretes.form, name="sec_lembrete_novo"),
    path("lembretes/<uuid:pk>/", lembretes.form, name="sec_lembrete_editar"),
    path("lembretes/<uuid:pk>/concluir/", lembretes.concluir, name="sec_lembrete_concluir"),
    path("lembretes/<uuid:pk>/adiar/", lembretes.adiar, name="sec_lembrete_adiar"),
    # Diário
    path("diario/", diario.tela, name="sec_diario"),
    path("diario/analisar/", diario.analisar, name="sec_diario_analisar"),
    path("diario/<uuid:pk>/", diario.acao, name="sec_diario_acao"),
    # Voz e Angel
    path("angel/", voz.tela, name="sec_angel"),
    path("angel/falar/", voz.conversar, name="sec_angel_falar"),
    path("angel/voz/", voz.audio, name="sec_angel_voz"),
    path("angel/briefing/", voz.briefing, name="sec_briefing"),
    path("angel/avisos/", voz.avisos, name="sec_avisos"),
    # Configurações
    path("configuracoes/", configuracoes.preferencias, name="sec_preferencias"),
    path("integracoes/", configuracoes.integracoes, name="sec_integracoes"),
    # API usada pelo Angel no servidor (token)
    path("api/angel/<str:acao>/", angel_api.api, name="sec_angel_api"),
]
