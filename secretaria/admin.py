from django.contrib import admin

from .models import ContaEmail


@admin.register(ContaEmail)
class ContaEmailAdmin(admin.ModelAdmin):
    list_display = ("empresa", "email", "usuario", "ativa", "verificada_em")
    list_filter = ("ativa", "usuario")
    readonly_fields = ("ultimo_erro", "verificada_em", "pasta_arquivo", "pasta_lixeira", "pasta_enviados")
