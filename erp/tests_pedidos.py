"""Pedidos do Omie: leitura (Omie simulado), tela e regra de pedido parado."""
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from . import omie
from . import problemas as PB
from .models import PedidoOmie


def ped(cod, num, etapa="50", faturado="N", cancelado="N", dalt="20/11/2026", total=1000):
    return {"cabecalho": {"codigo_pedido": cod, "numero_pedido": num, "codigo_cliente": 10, "etapa": etapa, "data_previsao": "21/11/2026"},
            "infoCadastro": {"faturado": faturado, "cancelado": cancelado, "devolvido": "N", "dInc": "19/11/2026", "dAlt": dalt},
            "informacoes_adicionais": {"codVend": 7}, "total_pedido": {"valor_total_pedido": total, "valor_mercadorias": total},
            "frete": {"peso_liquido": 55.5}, "lista_parcelas": {"parcela": [{"data_vencimento": "10/12/2026", "valor": total}]},
            "det": [{"produto": {"codigo": "SCRA23", "descricao": "SACOLA AZUL", "unidade": "MH", "quantidade": 10,
                                 "valor_unitario": total / 10, "valor_total": total}}]}


@override_settings(OMIE_APP_KEY="k", OMIE_APP_SECRET="s")
class PedidosTest(TestCase):
    def sinc(self, lista):
        with mock.patch("erp.omie.mapa_clientes", return_value={10: {"razao_social": "MERCADO X", "cnpj_cpf": "00.000"}}), \
                mock.patch("erp.omie.mapa_vendedores", return_value={7: "Ana"}), \
                mock.patch("erp.omie.paginar", return_value=iter(lista)):
            return omie.sincronizar_pedidos(saida=lambda *a: None)

    def test_sincroniza_substitui_e_protege(self):
        self.assertEqual(self.sinc([ped(1, "100"), ped(2, "101", "60", faturado="S"), ped(3, "102", "60", "S", "S")]), 3)
        p = PedidoOmie.objects.get(codigo=1)
        self.assertEqual((p.cliente, p.vendedor, p.situacao, p.qtd_itens), ("MERCADO X", "Ana", "Faturar", 1))
        self.assertEqual(PedidoOmie.objects.get(codigo=3).situacao, "Cancelado")
        self.sinc([ped(1, "100", "60", faturado="S")])
        self.assertEqual(PedidoOmie.objects.count(), 1)
        self.assertEqual(PedidoOmie.objects.get().situacao, "Faturado")
        for i in range(25):
            self.sinc([ped(j, str(j)) for j in range(1, 26)]) if i == 0 else None
        with self.assertRaises(omie.OmieErro):
            self.sinc([])
        self.assertEqual(PedidoOmie.objects.count(), 25)

    def test_tela_e_regra(self):
        self.sinc([ped(1, "100", dalt="10/11/2026", total=5000), ped(2, "101", dalt=date.today().strftime("%d/%m/%Y")),
                   ped(3, "102", "60", faturado="S")])
        self.client.force_login(User.objects.create_superuser("adm", "", "x"))
        r = self.client.get("/faturamento/pedidos/")
        self.assertContains(r, "MERCADO X")
        self.assertContains(r, "Pedidos · 3")
        r = self.client.get("/faturamento/pedidos/?pedido=1&sit=Faturar&ord=valor_total&asc=1")
        self.assertContains(r, "SACOLA AZUL")
        self.assertContains(r, "Pedidos · 2 de 3")
        self.assertIn("spreadsheetml", self.client.get("/faturamento/pedidos/?exportar=1")["Content-Type"])
        res = {x.regra.id: x for x in PB.conferir(None, hoje=date(2026, 11, 26))[0]}
        self.assertEqual([i["numero"] for i in res["pedido_parado_faturar"].itens], ["100"])
