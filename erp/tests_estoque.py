"""Estoque do Omie: leitura (Omie simulado), telas e avisos em Problemas para resolver."""
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from . import omie
from . import problemas as PB
from .estoque import calcular_cobertura
from .models import EstoqueOmie, MovEstoqueOmie, PedidoItemOmie, PedidoOmie, ProdutoOmie

HOJE = date(2026, 11, 26)
PA, MP = 11, 22


def prod(cod, codigo, desc, fam="SACOLAS", minimo=0, inativo="N"):
    return {"codigo_produto": cod, "codigo": codigo, "descricao": desc, "descricao_familia": fam, "unidade": "MH", "tipoItem": "04",
            "ncm": "3923.21.90", "estoque_minimo": minimo, "valor_unitario": 100, "inativo": inativo, "info": {"dAlt": "01/11/2026"}}


def pos(cod, codigo, desc, saldo, cmc=50, minimo=0):
    return {"nCodProd": cod, "cCodigo": codigo, "cDescricao": desc, "nSaldo": saldo, "fisico": saldo, "reservado": 0,
            "nPendente": 0, "estoque_minimo": minimo, "nCMC": cmc, "nPrecoUnitario": 100}


def mov(i, cod, desc, data, qtde, origem="VEN", local=PA, cancel="N"):
    return {"idMov": i, "idProd": cod, "descricao": desc, "dtMov": data, "qtde": qtde, "saldo": 0, "cmc": 50, "codOrigem": origem,
            "desOrigem": {"VEN": "Venda de Produto", "OPE": "Entrada da Ordem de Produção"}.get(origem, origem),
            "tipo": "saida" if qtde < 0 else "entrada", "codigo_local_estoque": local, "cancelamento": cancel, "numDoc": f"N{i}"}


DADOS = {
    "ListarProdutos": {"produto_servico_cadastro": [prod(1, "A1", "SACOLA AZUL", minimo=500), prod(2, "B2", "SACOLA BRANCA"),
                                                    prod(3, "C3", "SACOLA VELHA"), prod(4, "R4", "RESINA", fam="RESINAS", inativo="S"),
                                                    dict(prod(5, "MAQ5", "EXTRUSORA", fam="ATIVO"), tipoItem="08")]},
    "ListarLocaisEstoque": {"locaisEncontrados": [{"codigo_local_estoque": PA, "codigo": "PA", "descricao": "Produto Acabado"},
                                                  {"codigo_local_estoque": MP, "codigo": "MP", "descricao": "Matéria-Prima"}]},
    "ListarPosEstoque": {PA: [pos(1, "A1", "SACOLA AZUL", 100), pos(2, "B2", "SACOLA BRANCA", 900, cmc=0.0003),
                              pos(3, "C3", "SACOLA VELHA", 40), pos(5, "MAQ5", "EXTRUSORA", 1, cmc=340000)],
                         MP: [pos(4, "R4", "RESINA", -5)]},
    "ListarMovimentoEstoque": {"movProdutoListar": [
        mov(1, 1, "SACOLA AZUL", "20/11/2026", -90), mov(2, 1, "SACOLA AZUL", "01/11/2026", 200, "OPE"),
        mov(3, 2, "SACOLA BRANCA", "25/11/2026", -30), mov(4, 2, "SACOLA BRANCA", "24/11/2026", -999, cancel="S"),
        mov(5, 3, "SACOLA VELHA", "01/06/2026", -10), mov(5, 3, "SACOLA VELHA", "01/06/2026", -10),
        mov(6, 2, "SACOLA BRANCA", "25/11/2026", 10, "CVP")]},
}


def falso_chamar(endpoint, call, param, tentativas=4):
    d = DADOS[call]
    if call == "ListarPosEstoque":
        return {"produtos": d[param["codigo_local_estoque"]], "nTotPaginas": 1}
    return dict(d, nTotPaginas=1, total_de_paginas=1)


@override_settings(OMIE_APP_KEY="k", OMIE_APP_SECRET="s")
class EstoqueTest(TestCase):
    def sinc(self, completo=None):
        with mock.patch("erp.omie.chamar", side_effect=falso_chamar) as ch:
            msg = omie.sincronizar_estoque(saida=lambda *a: None, hoje=HOJE, completo=completo)
        self.chamadas = [c.args[2] for c in ch.call_args_list if c.args[1] == "ListarMovimentoEstoque"]
        return msg

    def test_sincroniza(self):
        self.assertIn("5 produtos, 5 saldos em 2 locais, 6 movimentações", self.sinc())
        e = EstoqueOmie.objects.get(codigo="A1")
        self.assertEqual((e.local, e.local_codigo, e.saldo, e.valor), ("Produto Acabado", "PA", 100, 5000))
        self.assertEqual(MovEstoqueOmie.objects.get(id_mov=2).local, "Produto Acabado")
        self.assertTrue(ProdutoOmie.objects.get(codigo="R4").inativo)
        # mês a mês (dez/25 a nov/26 = 12 meses) e local por local
        self.assertEqual(len(self.chamadas), 24)
        self.assertTrue(all("codigo_local_estoque" in c for c in self.chamadas))
        MovEstoqueOmie.objects.filter(id_mov=5).update(descricao="ANTIGA")
        self.assertIn("desde 01/10/2026", self.sinc(completo=False))  # hora a hora: só os 2 últimos meses
        self.assertEqual(len(self.chamadas), 4)
        self.assertEqual(EstoqueOmie.objects.count(), 5)
        self.assertEqual(MovEstoqueOmie.objects.count(), 6)
        self.assertEqual(MovEstoqueOmie.objects.get(id_mov=5).descricao, "SACOLA VELHA")  # veio de novo no lote e foi trocada

    def test_cobertura_e_avisos(self):
        self.sinc()
        ped = PedidoOmie.objects.create(codigo=9, numero="900", cliente="X", etapa="50", situacao="Faturar")
        PedidoItemOmie.objects.create(pedido=ped, codigo_produto="A1", descricao="SACOLA AZUL", quantidade=150)
        cob = {r["codigo"]: r for r in calcular_cobertura(HOJE)}
        self.assertEqual(cob["A1"]["vendido"], 90)
        self.assertEqual(cob["A1"]["dias"], 100)       # 100 ÷ (90/90)
        self.assertEqual(cob["A1"]["falta"], 50)
        self.assertEqual(cob["B2"]["vendido"], 20)     # 30 vendidos − 10 do cancelamento; o movimento cancelado não conta
        self.assertNotIn("MAQ5", cob)                  # máquina no local Produto Acabado fica de fora
        self.assertEqual(cob["C3"]["situacao"], "Parado")
        res = {x.regra.id: x for x in PB.conferir(None, hoje=HOJE)[0]}
        self.assertEqual([i["codigo"] for i in res["estoque_falta_pedidos"].itens], ["A1"])
        self.assertEqual([i["codigo"] for i in res["estoque_negativo"].itens], ["R4"])
        self.assertEqual([i["codigo"] for i in res["estoque_abaixo_minimo"].itens], ["A1"])
        self.assertEqual([i["codigo"] for i in res["estoque_parado"].itens], ["C3"])
        self.assertEqual([i["codigo"] for i in res["estoque_custo_suspeito"].itens], ["B2"])

    def test_telas(self):
        self.sinc()
        self.client.force_login(User.objects.create_superuser("adm", "", "x"))
        r = self.client.get("/estoque/")
        self.assertContains(r, "SACOLA AZUL")
        self.assertContains(r, "custo?")
        self.assertContains(r, "não é para venda")
        self.assertContains(self.client.get("/estoque/?local=Matéria-Prima"), "Saldos · 1 de 5")
        self.assertContains(self.client.get("/estoque/movimentacoes/?de=2026-01-01&ate=2026-11-30&tipo=saida"), "Movimentações · 4")
        self.assertContains(self.client.get("/estoque/produtos/"), "Produtos · 4 de 5")
        self.assertContains(self.client.get("/estoque/produtos/?sit=todos&q=resina"), "RESINA")
        self.assertContains(self.client.get("/estoque/cobertura/?sit=Parado"), "SACOLA VELHA")
        for u in ("/estoque/", "/estoque/movimentacoes/", "/estoque/produtos/", "/estoque/cobertura/"):
            self.assertIn("spreadsheetml", self.client.get(u + "?exportar=1")["Content-Type"])
        self.assertContains(self.client.get("/estoque/cobertura/"), "Posição de estoque")  # menu
