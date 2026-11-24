"""Auditoria Omie: mudanças detectadas entre leituras (Omie simulado)."""
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from . import omie
from .models import AuditoriaOmie, FluxoCaixa


def titulo(cod, **kw):
    r = dict(fornecedor="Fornecedor A", categoria="Resina", grupo="Insumos", data_emissao=date(2026, 11, 10), data_pagamento=None,
             departamento="N/D", cnpj_cpf="00.000.000/0001-00", forma_pagamento="Boleto", situacao="A vencer", tipo="Contas a pagar",
             valor_conta=Decimal("-1000.00"), valor_pago=Decimal("0"), conta_corrente="Itaú", data_vencimento=date(2026, 12, 1),
             data_previsao=date(2026, 12, 1), numero_documento="123", parcela="1/1", omie_codigo=cod, observacao=None)
    r.update(kw)
    return r


@override_settings(OMIE_APP_KEY="k", OMIE_APP_SECRET="s")
class AuditoriaTest(TestCase):
    def sinc(self, rows):
        with mock.patch("erp.omie.buscar_fluxo", return_value=rows), \
                mock.patch("erp.omie.chamar", return_value={"info": {"uAlt": "P001", "dAlt": "24/11/2026", "hAlt": "10:00:00",
                                                                     "uInc": "P002", "dInc": "24/11/2026", "hInc": "09:00:00"}}):
            return omie.sincronizar(date(2026, 1, 1), date(2026, 11, 24), fluxo=True, vendas=False, saida=lambda *a: None)

    def test_primeira_leitura_so_guarda_foto_depois_registra(self):
        self.sinc([titulo(1), titulo(2), titulo(3, situacao="Pago", valor_pago=Decimal("-500"))])
        self.assertEqual(AuditoriaOmie.objects.count(), 0)
        msg = self.sinc([
            titulo(1, valor_conta=Decimal("-1500.00"), data_vencimento=date(2026, 12, 20)),   # valor e vencimento
            titulo(3, situacao="A vencer", valor_pago=Decimal("0")),                         # estorno
            titulo(4, data_emissao=date(2026, 9, 1)),                                        # novo retroativo
        ])                                                                                   # 2 sumiu
        self.assertIn("auditoria", msg)
        a = AuditoriaOmie.objects
        self.assertTrue(a.filter(chave="1", campo="valor_conta", antes="1.000,00", depois="1.500,00", sensivel=True).exists())
        self.assertTrue(a.filter(chave="1", campo="data_vencimento", motivo="Vencimento adiado").exists())
        self.assertTrue(a.filter(chave="3", campo="situacao", sensivel=True, usuario_omie="P001").exists())
        self.assertTrue(a.filter(chave="2", tipo="excluido", sensivel=True).exists())
        self.assertTrue(a.filter(chave="4", tipo="novo", sensivel=True, usuario_omie="P002").exists())
        self.assertEqual(FluxoCaixa.objects.count(), 3)
        # sem mudanças: nada novo
        n = a.count()
        self.sinc([titulo(1, valor_conta=Decimal("-1500.00"), data_vencimento=date(2026, 12, 20)),
                   titulo(3, situacao="A vencer", valor_pago=Decimal("0")), titulo(4, data_emissao=date(2026, 9, 1))])
        self.assertEqual(a.count(), n)

    def test_resposta_vazia_nao_apaga(self):
        self.sinc([titulo(i) for i in range(1, 30)])
        with self.assertRaises(omie.OmieErro):
            self.sinc([])
        self.assertEqual(FluxoCaixa.objects.count(), 29)
        self.assertEqual(AuditoriaOmie.objects.count(), 0)

    def test_tela_so_admin_e_excel(self):
        self.sinc([titulo(1)])
        self.sinc([titulo(1, valor_conta=Decimal("-2000"))])
        u = User.objects.create_user("x", password="x")
        self.client.force_login(u)
        self.assertEqual(self.client.get("/sistema/auditoria-omie/").status_code, 403)
        u.is_staff = True
        u.save()
        r = self.client.get("/sistema/auditoria-omie/")
        self.assertContains(r, "Valor do título alterado")
        self.client.post("/sistema/auditoria-omie/", {"codigo": "P001", "nome": "Maria Financeiro"})
        self.assertContains(self.client.get("/sistema/auditoria-omie/"), "Maria Financeiro")
        x = self.client.get("/sistema/auditoria-omie/?exportar=1")
        self.assertEqual(x["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
