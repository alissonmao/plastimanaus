"""Problemas para resolver: regras, dispensa e permissões."""
from datetime import date, datetime, timedelta, timezone as tz
from decimal import Decimal as D

from django.contrib.auth.models import Group, User
from django.test import TestCase

from . import problemas as PB
from .models import DispensaProblema, FluxoCaixa, PerfilUsuario, SaldoContaOmie, Venda

HOJE = date(2026, 11, 26)


def tit(venc, vc, sit="A vencer", vp="0", cat="Resina", forn="F", pg=None, cnpj="1"):
    return FluxoCaixa.objects.create(fornecedor=forn, categoria=cat, grupo="G", data_emissao=venc - timedelta(days=10), data_pagamento=pg,
                                     situacao=sit, tipo="2. Contas a Pagar" if D(vc) < 0 else "1. Contas a Receber",
                                     valor_conta=D(vc), valor_pago=D(vp), data_vencimento=venc, cnpj_cpf=cnpj)


def por_id(res):
    return {r.regra.id: r for r in res}


class RegrasTest(TestCase):
    def rodar(self, user=None):
        return por_id(PB.conferir(user, hoje=HOJE, agora=datetime(2026, 11, 26, 10, tzinfo=tz.utc))[0])

    def test_financeiro(self):
        tit(date(2026, 11, 1), "-1000", "Atrasado")
        tit(date(2026, 11, 20), "-500", "Atrasado")
        tit(date(2026, 11, 1), "-999", "Atrasado", cat="Rendimentos de Aplicações")   # fica fora
        tit(date(2026, 11, 10), "-700", "Pago", vp="-700", pg=date(2026, 11, 10))     # pago: fora
        tit(date(2026, 11, 5), "3000", "Atrasado", forn="Cliente A")
        tit(date(2026, 11, 6), "200", "Atrasado", forn="Cliente B")
        tit(HOJE, "-50", "Vence hoje")
        r = self.rodar()
        self.assertEqual(r["pagar_vencidas"].n, 2)
        self.assertEqual(r["pagar_vencidas"].valor, D("1500"))
        self.assertIn("25 dias", r["pagar_vencidas"].descricao)
        self.assertEqual([i["cliente"] for i in r["receber_vencidas"].itens], ["Cliente A", "Cliente B"])
        self.assertEqual(r["vence_hoje"].valor, D("50"))
        # sem saldo lido → aviso na área Sistema, as outras regras continuam
        self.assertIn("erro_caixa_negativo", r)
        SaldoContaOmie.objects.create(codigo=1, descricao="Itaú", saldo=D("100"))
        self.assertNotIn("caixa_negativo", self.rodar())        # 100 + 3.200 − 1.550 ainda positivo
        tit(HOJE + timedelta(days=10), "-5000")
        r = self.rodar()
        self.assertIn("06/12/2026", r["caixa_negativo"].titulo)
        self.assertEqual(r["caixa_negativo"].valor, D("3250"))

    def test_categoria_acima(self):
        for m in (8, 9, 10):
            tit(date(2026, m, 10), "-1000", "Pago", vp="-1000", pg=date(2026, m, 10), cat="Energia")
        tit(date(2026, 11, 10), "-2500", "Pago", vp="-2500", pg=date(2026, 11, 10), cat="Energia")
        r = self.rodar()
        self.assertEqual(r["categoria_acima"].itens[0]["categoria"], "Energia")
        self.assertEqual(r["categoria_acima"].valor, D("1500"))

    def test_cliente_parado_e_preco(self):
        for d in (date(2026, 6, 5), date(2026, 7, 5), date(2026, 8, 5)):
            Venda.objects.create(data=d, cliente="Mercado X", produto="P1", linha="Sacola", total=D("1000"), quantidade=10,
                                 valor_unitario=D("100"), vendedor="Ana")
        Venda.objects.create(data=date(2026, 11, 20), cliente="Mercado Y", produto="P1", linha="Sacola", total=D("500"), quantidade=10,
                             valor_unitario=D("50"), vendedor="Bia")
        Venda.objects.create(data=date(2026, 11, 1), cliente="Mercado Y", produto="P1", linha="Sacola", total=D("1000"), quantidade=10,
                             valor_unitario=D("100"), vendedor="Bia")
        Venda.objects.create(data=date(2026, 9, 1), cliente="Mercado Y", produto="P1", linha="Sacola", total=D("1000"), quantidade=10,
                             valor_unitario=D("100"), vendedor="Bia")
        Venda.objects.create(data=date(2026, 10, 1), cliente="Mercado Y", produto="P1", linha="Sacola", total=D("1000"), quantidade=10,
                             valor_unitario=D("100"), vendedor="Bia")
        r = self.rodar()
        self.assertEqual(r["cliente_parado"].itens[0]["cliente"], "Mercado X")
        self.assertEqual(r["preco_baixo"].valor, D("500"))
        self.assertIn("meta_sem_cadastro", r)
        self.assertIn("sem_apontamento", r)

    def test_dispensa_e_volta(self):
        tit(date(2026, 11, 1), "-1000", "Atrasado")
        u = User.objects.create_superuser("adm", "", "x")
        DispensaProblema.objects.create(regra="pagar_vencidas", volta_em=HOJE + timedelta(days=1), usuario=u)
        res, disp = PB.conferir(u, hoje=HOJE)
        self.assertNotIn("pagar_vencidas", por_id(res))
        self.assertEqual(disp[0].regra.id, "pagar_vencidas")
        res, _ = PB.conferir(u, hoje=HOJE + timedelta(days=1))
        self.assertIn("pagar_vencidas", por_id(res))

    def test_permissoes(self):
        tit(date(2026, 11, 1), "-1000", "Atrasado")
        Venda.objects.create(data=date(2026, 11, 20), cliente="C", produto="P", linha="Sacola", total=D("1"), vendedor="")
        fin = User.objects.create_user("fin", password="x")
        fin.groups.add(Group.objects.get_or_create(name="Financeiro")[0])
        r = self.rodar(fin)
        self.assertTrue(all(x.regra.area == "Financeiro" for x in r.values()))
        for d in (date(2026, 6, 5), date(2026, 7, 5), date(2026, 8, 5)):
            Venda.objects.create(data=d, cliente="Mercado X", produto="P1", linha="Sacola", total=D("10"), vendedor="Ana")
            Venda.objects.create(data=d, cliente="Mercado Z", produto="P1", linha="Sacola", total=D("10"), vendedor="Bia")
        ven = User.objects.create_user("ven", password="x")
        PerfilUsuario.objects.create(usuario=ven, vendedor="Ana")
        r = self.rodar(ven)
        self.assertTrue(r and all(x.regra.area == "Vendas" for x in r.values()))
        self.assertEqual([i["cliente"] for i in r["cliente_parado"].itens], ["Mercado X"])   # só a carteira da Ana


class TelaTest(TestCase):
    def test_tela_dispensar_desfazer(self):
        u = User.objects.create_superuser("adm", "", "x")
        self.client.force_login(u)
        tit(date.today() - timedelta(days=5), "-1000", "Atrasado")
        r = self.client.get("/problemas/")
        self.assertContains(r, "conta a pagar vencida")
        self.assertContains(r, "Como corrigir")
        r = self.client.post("/problemas/dispensar/", dict(regra="pagar_vencidas", dias="7"), follow=True)
        self.assertContains(r, "dispensado")
        d = DispensaProblema.objects.get()
        self.assertEqual(d.volta_em, date.today() + timedelta(days=7))
        self.assertContains(self.client.get("/problemas/?ver=dispensados"), "Desfazer dispensa")
        self.client.post(f"/problemas/desfazer/{d.pk}/")
        self.assertFalse(DispensaProblema.objects.exists())
        self.assertContains(self.client.get("/problemas/?area=Financeiro"), "badge")
