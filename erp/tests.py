from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings

from erp import omie
from erp.models import FluxoCaixa, Venda

RESPOSTAS = {
    "ListarCategorias": {"total_de_paginas": 1, "categoria_cadastro": [
        {"codigo": "2.01", "descricao": "Despesas com Pessoal"},
        {"codigo": "2.01.01", "descricao": "Salários", "categoria_superior": "2.01"},
        {"codigo": "1.01", "descricao": "Receitas"},
        {"codigo": "1.01.01", "descricao": "Venda de produtos", "categoria_superior": "1.01"}]},
    "ListarClientes": {"total_de_paginas": 1, "clientes_cadastro": [
        {"codigo_cliente_omie": 10, "razao_social": "ATACADAO LTDA", "nome_fantasia": "Atacadão", "cnpj_cpf": "00.000/0001-00",
         "cidade": "MANAUS (AM)", "estado": "AM", "bairro": "Centro"},
        {"codigo_cliente_omie": 20, "razao_social": "FUNCIONARIO X", "nome_fantasia": ""}]},
    "ListarResumoContasCorrentes": {"total_de_paginas": 1, "conta_corrente_lista": [{"nCodCC": 5, "descricao": "Itaú"}, {"nCodCC": 6, "descricao": "Santander"}]},
    "ListarDepartamentos": {"total_de_paginas": 1, "departamentos": [{"codigo": "D1", "descricao": "Produção"}]},
    "ListarVendedores": {"total_de_paginas": 1, "cadastro": [{"codigo": 7, "nome": "JOÃO"}]},
    "ListarProdutos": {"total_de_paginas": 1, "produto_servico_cadastro": [
        {"codigo_produto": 99, "codigo": "SCRA22", "descricao_familia": "Sacola", "peso_liq": 0}]},
    "ListarMovimentos": {"nTotPaginas": 1, "movimentos": [
        {"detalhes": {"cNatureza": "R", "cStatus": "RECEBIDO", "nCodCliente": 10, "cCodCateg": "1.01.01", "dDtEmissao": "05/11/2026",
                      "dDtPagamento": "10/11/2026", "nValorTitulo": 1000, "nCodCC": 5, "cTipo": "BOL"},
         "resumo": {"nValPago": 1000}, "categorias": [], "departamentos": []},
        {"detalhes": {"cNatureza": "P", "cStatus": "ATRASADO", "nCodCliente": 20, "cCodCateg": "2.01.01", "dDtEmissao": "06/11/2026",
                      "nValorTitulo": 300}, "resumo": {"nValPago": 0},
         "categorias": [{"cCodCateg": "2.01.01", "nDistrValor": 300}], "departamentos": [{"cCodDepartamento": "D1", "nDistrValor": 300}]},
        {"detalhes": {"cNatureza": "P", "cStatus": "PAGO", "nCodCC": 6, "dDtEmissao": "06/11/2026", "nValorTitulo": 900}, "resumo": {"nValPago": 900}},
        {"detalhes": {"cNatureza": "P", "cStatus": "CANCELADO", "dDtEmissao": "06/11/2026", "nValorTitulo": 50}, "resumo": {}}]},
    "ListarNF": {"total_de_paginas": 1, "nfCadastro": [
        {"ide": {"dEmi": "07/11/2026", "nNF": 123, "finNFe": "1"}, "nfDestInt": {"nCodCli": 10, "cRazao": "ATACADAO LTDA"},
         "pedido": {"nIdVendedor": 7, "cNumPedido": "555"},
         "det": [{"prod": {"cProd": "SCRA22", "xProd": "SACOLA AZUL", "qCom": 10, "vUnCom": 12.5, "vTotItem": 125, "uCom": "PCT"},
                  "nfProdInt": {"nCodProd": 99}}]},
        {"ide": {"dEmi": "08/11/2026", "nNF": 124, "dCan": "08/11/2026"}, "det": [{"prod": {"cProd": "X", "vTotItem": 9}}]}]},
}


def falso(endpoint, call, param, tentativas=4):
    return RESPOSTAS[call]


@override_settings(OMIE_APP_KEY="k", OMIE_APP_SECRET="s")
class OmieTest(TestCase):
    def setUp(self):
        omie.limpar_cache()
        # histórico de planilha: define linha/grupo/cor e kg por unidade do SCRA22
        Venda.objects.create(data=date(2026, 9, 1), cliente="A", produto="SCRA22 - SACOLA AZUL", linha="Sacola", grupo="22 KG",
                             cor="AZUL", total=10, kg=Decimal("20"), quantidade=Decimal("10"))
        Venda.objects.create(data=date(2026, 11, 3), cliente="R", produto="P - x", linha="Sacola", total=5, tipo_documento="Recibo")
        Venda.objects.create(data=date(2026, 11, 4), cliente="NF velha", produto="P - x", linha="Sacola", total=5)

    @mock.patch("erp.omie.chamar", side_effect=falso)
    def test_sincroniza(self, _):
        omie.sincronizar(date(2026, 11, 1), date(2026, 11, 30), saida=lambda *_: None)
        rec = FluxoCaixa.objects.get(tipo=omie.TIPO_RECEBER)
        self.assertEqual((rec.fornecedor, rec.categoria, rec.grupo, rec.situacao, rec.valor_conta, rec.valor_pago, rec.conta_corrente),
                         ("Atacadão", "Venda de produtos", "Receitas", "Recebido", 1000, 1000, "Itaú"))
        pag = FluxoCaixa.objects.get(tipo=omie.TIPO_PAGAR)
        self.assertEqual((pag.fornecedor, pag.grupo, pag.situacao, pag.valor_conta, pag.departamento, pag.data_pagamento),
                         ("FUNCIONARIO X", "Despesas com Pessoal", "Atrasado", -300, "Produção", None))
        self.assertEqual(FluxoCaixa.objects.count(), 2)  # cancelado e Santander ignorados
        nov = Venda.objects.filter(data__month=11)
        self.assertEqual(sorted(nov.values_list("cliente", flat=True)), ["ATACADAO LTDA", "R"])  # recibo mantido, NF velha substituída
        v = nov.get(cliente="ATACADAO LTDA")
        self.assertEqual((v.linha, v.grupo, v.cor, v.kg, v.total, v.vendedor, v.cidade, v.nota_fiscal),
                         ("Sacola", "22 KG", "AZUL", Decimal("20.000"), 125, "JOÃO", "Manaus", "123"))
