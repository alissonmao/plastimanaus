from django.contrib import admin

from . import models as m


@admin.register(m.Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ["data", "cliente", "produto", "linha", "total", "kg", "vendedor"]
    list_filter = ["linha", "estado"]
    search_fields = ["cliente", "produto", "vendedor"]
    date_hierarchy = "data"


@admin.register(m.VendaPlasti)
class VendaPlastiAdmin(admin.ModelAdmin):
    list_display = ["data_pedido", "numero_pedido", "cliente", "vendedor", "valor", "forma_pagamento", "status"]
    list_filter = ["vendedor", "forma_pagamento"]
    search_fields = ["cliente", "numero_pedido"]
    date_hierarchy = "data_pedido"


@admin.register(m.MetaVendedor)
class MetaAdmin(admin.ModelAdmin):
    list_display = ["vendedor", "mes", "meta"]
    list_filter = ["vendedor"]
    list_editable = ["meta"]


@admin.register(m.FluxoCaixa)
class FluxoAdmin(admin.ModelAdmin):
    list_display = ["data_emissao", "data_pagamento", "fornecedor", "grupo", "categoria", "situacao", "valor_conta", "valor_pago"]
    list_filter = ["tipo", "grupo", "situacao"]
    search_fields = ["fornecedor", "categoria"]
    date_hierarchy = "data_emissao"


@admin.register(m.Apontamento)
class ApontamentoAdmin(admin.ModelAdmin):
    list_display = ["data", "turno", "maquina", "produto", "cor", "op", "ok_kg", "apara_kg", "alca_kg", "borra_kg"]
    list_filter = ["turno", "maquina", "produto"]
    date_hierarchy = "data"


for modelo in [m.Setor, m.Familia, m.Maquina, m.Turno, m.Produto, m.Cor, m.TipoSacola, m.Medida, m.Cliente, m.OrdemProducao]:
    admin.site.register(modelo)


@admin.register(m.AuditoriaOmie)
class AuditoriaOmieAdmin(admin.ModelAdmin):
    """Só leitura: a auditoria não pode ser alterada nem apagada."""
    list_display = ("detectado_em", "tipo", "parte", "documento", "valor", "campo", "antes", "depois", "sensivel", "usuario_omie")
    list_filter = ("tipo", "sensivel", "natureza", "campo")
    search_fields = ("parte", "documento", "chave")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
