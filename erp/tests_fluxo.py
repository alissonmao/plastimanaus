"""Visão geral Entradas e Saídas base Omie: cálculos iguais ao Lovable e a tela."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as L

from django.contrib.auth.models import User
from django.test import TestCase

from . import calculos as C
from . import fluxo_visao as V
from .models import FluxoCaixa

R, P = C.TIPO_RECEBER, C.TIPO_PAGAR


def lanc(emi, pg, vc, vp, sit, tipo, grupo="G", cat="C", forn="F"):
    return L(data_emissao=emi, data_pagamento=pg, valor_conta=Decimal(vc), valor_pago=Decimal(vp), situacao=sit, tipo=tipo,
             grupo=grupo, categoria=cat, fornecedor=forn, conta_corrente="Itaú")


ROWS = [
    lanc(date(2026, 3, 1), date(2026, 3, 5), "1000", "1000", "Recebido", R, "Receitas", "Venda", "Cliente A"),
    lanc(date(2026, 3, 2), date(2026, 3, 6), "-300", "-300", "Pago", P, "Despesas com Pessoal", "Salário", "Func"),
    lanc(date(2026, 3, 3), None, "-200", "0", "Atrasado", P, "Despesas Administrativas", "Aluguel", "Dono"),
    lanc(date(2026, 4, 3), None, "500", "100", "Recebido Parcialmente", R, "Receitas", "Serviço", "Cliente B"),
    lanc(date(2026, 4, 4), None, "800", "0", "A vencer", R, "Receitas", "Venda", "Cliente B"),
]


class CalculosTest(TestCase):
    def test_serie_periodo_curto_e_diaria_com_acumulado(self):
        modo, pts = V.serie_periodo(ROWS, date(2026, 3, 1), date(2026, 3, 10))
        self.assertEqual(modo, "dia")
        self.assertEqual(len(pts), 10)
        self.assertEqual(pts[-1]["entradasAcum"], 1000)
        self.assertEqual(pts[-1]["gastosAcum"], 300)
        self.assertEqual(pts[-1]["saldoAcum"], 700)
        modo, pts = V.serie_periodo(ROWS, date(2026, 1, 1), date(2026, 6, 30))
        self.assertEqual((modo, len(pts)), ("mes", 6))

    def test_serie_dia_mostra_todos_os_dias_do_mes(self):
        pts = V.serie_granularidade(ROWS, "dia", "2026-04")
        self.assertEqual(len(pts), 30)
        self.assertEqual(pts[-1]["entradasAcum"], 100)

    def test_aberto_exclui_quitados_e_usa_saldo(self):
        a = V.aberto_por_data(ROWS, "receber")
        self.assertEqual(a["total"], 400 + 800)
        a = V.aberto_por_data(ROWS, "ambos")
        self.assertEqual(a["total"], 1200 - 200)
        self.assertTrue(any(s["key"] == "P|Atrasado" and s["valores"] == [-200, 0, 0] for s in a["series"]))

    def test_situacao_tipo_e_cores(self):
        st = V.por_situacao_tipo(ROWS)
        self.assertEqual(st["receber"]["total"], 2300)
        self.assertEqual(V.cor_situacao("Atrasado com boleto gerado"), "#ff8787")
        self.assertEqual(V.cor_situacao("Recebido Parcialmente"), "#94d82d")
        self.assertEqual(V.cor_grupo("Despesas com Pessoal"), "#e11d48")

    def test_entradas_grupo_categoria_e_evolucao(self):
        e = V.entradas_grupo_categoria(ROWS)
        self.assertEqual(e["total"], 1100)
        self.assertEqual([c["nome"] for c in e["grupos"][0]["categorias"]], ["Venda", "Serviço"])
        evo = V.gastos_por_periodo(ROWS, lambda r: r.grupo, 6, "mes")
        self.assertEqual(evo["series"], ["Despesas com Pessoal"])
        self.assertEqual(evo["totais"], [300])


class TelaTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("adm", "", "x"))
        for r in ROWS:
            FluxoCaixa.objects.create(**{k: v for k, v in vars(r).items()})

    def test_tela_e_filtros(self):
        for qs in ["", "?at=m:2026-03", "?at=u3", "?de=2026-03-01&ate=2026-03-31&g=dia", "?g=dia&mes=2026-04", "?ab=ambos&st=Atrasado",
                   "?tipo=gastos&q=alug&ord=valor_conta&asc=1", "?cat=Salário&lcat=Venda&p=9"]:
            r = self.client.get("/fluxo-caixa/" + qs)
            self.assertEqual(r.status_code, 200, qs)
        r = self.client.get("/fluxo-caixa/?tipo=gastos")
        self.assertContains(r, "Lançamentos — Gastos · 2")

    def test_baixar(self):
        r = self.client.get("/fluxo-caixa/?baixar=xlsx")
        self.assertIn("spreadsheetml", r["Content-Type"])
        r = self.client.get("/fluxo-caixa/?baixar=pdf&tipo=entradas")
        self.assertContains(r, "Salvar como PDF")
        self.assertContains(r, "3 lançamentos")
