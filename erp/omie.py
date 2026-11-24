"""Integração com a API do Omie (https://app.omie.com.br/api/v1/).

Traz para o ERP:
- Fluxo de caixa  ← financas/mf ListarMovimentos (contas a pagar e a receber)
- Faturamento     ← produtos/nfconsultar ListarNF (itens das NF-e de saída)

A sincronização substitui os registros do período, igual à importação por planilha.
Credenciais: OMIE_APP_KEY e OMIE_APP_SECRET no .env.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction

from .calculos import codigo_produto, sem_acento
from .models import FluxoCaixa, Venda

log = logging.getLogger(__name__)
URL = "https://app.omie.com.br/api/v1/"

TIPO_RECEBER = "1. Contas a Receber"
TIPO_PAGAR = "2. Contas a Pagar"


class OmieErro(Exception):
    pass


def configurado() -> bool:
    return bool(settings.OMIE_APP_KEY and settings.OMIE_APP_SECRET)


def chamar(endpoint: str, call: str, param: dict, tentativas: int = 4) -> dict:
    corpo = {"call": call, "app_key": settings.OMIE_APP_KEY, "app_secret": settings.OMIE_APP_SECRET, "param": [param]}
    for t in range(tentativas):
        r = requests.post(URL + endpoint, json=corpo, timeout=90)
        try:
            dados = r.json()
        except ValueError:
            dados = {}
        if r.status_code == 200 and "faultstring" not in dados:
            return dados
        msg = dados.get("faultstring") or r.text[:300]
        if "Não existem registros" in msg or "nao existem registros" in msg.lower():
            return {}
        # Limite de requisições / consumo redundante: espera e tenta de novo
        if r.status_code in (425, 429, 500, 502, 503) or "REDUNDANT" in msg or "bloqueada" in msg.lower():
            time.sleep(5 * (t + 1))
            continue
        raise OmieErro(f"{call}: {msg}")
    raise OmieErro(f"{call}: Omie não respondeu após {tentativas} tentativas")


def paginar(endpoint, call, lista, param=None, por_pagina=100, chave_pag="pagina", chave_qtd="registros_por_pagina",
            chave_total="total_de_paginas"):
    pagina = 1
    while True:
        p = dict(param or {}, **{chave_pag: pagina, chave_qtd: por_pagina})
        dados = chamar(endpoint, call, p)
        for item in dados.get(lista) or []:
            yield item
        total = dados.get(chave_total) or 1
        if pagina >= total:
            return
        pagina += 1


def br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def data_omie(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def dec(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal(0)


# --------------------------------------------------------------------- cadastros auxiliares
def mapa_categorias():
    cats = {c["codigo"]: c for c in paginar("geral/categorias/", "ListarCategorias", "categoria_cadastro")}
    out = {}
    for cod, c in cats.items():
        sup = cats.get(c.get("categoria_superior") or "")
        out[cod] = (c.get("descricao") or cod, (sup or {}).get("descricao") or c.get("descricao") or cod)
    return out  # codigo -> (categoria, grupo)


def mapa_clientes():
    return {c["codigo_cliente_omie"]: c for c in paginar("geral/clientes/", "ListarClientes", "clientes_cadastro",
                                                          {"apenas_importado_api": "N"}, por_pagina=50)}


def mapa_contas():
    return {c["nCodCC"]: c.get("descricao", "") for c in paginar(
        "geral/contacorrente/", "ListarResumoContasCorrentes", "conta_corrente_lista", {"apenas_importado_api": "N"})}


def mapa_departamentos():
    return {d["codigo"]: d.get("descricao", "") for d in paginar("geral/departamentos/", "ListarDepartamentos", "departamentos")}


def mapa_vendedores():
    return {v["codigo"]: v.get("nome", "") for v in paginar("geral/vendedores/", "ListarVendedores", "cadastro")}


def mapa_produtos():
    return {p["codigo_produto"]: p for p in paginar("geral/produtos/", "ListarProdutos", "produto_servico_cadastro",
                                                     {"apenas_importado_api": "N", "filtrar_apenas_omiepdv": "N"}, por_pagina=50)}


# --------------------------------------------------------------------- fluxo de caixa
FORMAS = {"BOL": "Boleto", "PIX": "PIX", "TRA": "Transferência", "DIN": "Dinheiro", "CRT": "Cartão de Crédito",
          "CRD": "Cartão de Crédito", "CHQ": "Cheque", "TAR": "Tarifa", "DEB": "Débito em conta"}


def situacao(status: str, natureza: str, boleto: bool) -> str | None:
    """Mesmos nomes da exportação de contas do Omie usada nas planilhas."""
    receber = natureza == "R"
    s = (status or "").upper().replace("_", "").replace(" ", "")
    if s == "CANCELADO":
        return None
    if s in ("RECEBIDO", "LIQUIDADO", "PAGO"):
        return "Recebido" if receber else "Pago"
    if s == "PAGTOPARCIAL":
        return "Recebido Parcialmente" if receber else "Pago Parcialmente"
    base = {"ATRASADO": "Atrasado", "VENCEHOJE": "Vence hoje", "AVENCER": "A vencer", "EMABERTO": "A vencer"}.get(s, (status or "").title())
    return f"{base} (boleto gerado)" if boleto else base


def buscar_fluxo(de: date, ate: date) -> list[dict]:
    cats, clis, contas, deps = mapa_categorias(), mapa_clientes(), mapa_contas(), mapa_departamentos()
    excluir = {sem_acento(c) for c in settings.OMIE_EXCLUIR_CONTAS}
    rows = []
    for mov in paginar("financas/mf/", "ListarMovimentos", "movimentos",
                       {"dDtEmisDe": br(de), "dDtEmisAte": br(ate), "cExibirDepartamentos": "S", "cTpLancamento": "CPCR"},
                       por_pagina=50, chave_pag="nPagina", chave_qtd="nRegPorPagina", chave_total="nTotPaginas"):
        d, r = mov.get("detalhes", {}), mov.get("resumo", {})
        if sem_acento(contas.get(d.get("nCodCC")) or "") in excluir:
            continue
        nat = d.get("cNatureza")
        if nat not in ("P", "R"):
            continue
        sit = situacao(d.get("cStatus"), nat, bool(d.get("cNumBoleto")))
        if sit is None:
            continue
        sinal = Decimal(1) if nat == "R" else Decimal(-1)
        cli = clis.get(d.get("nCodCliente")) or {}
        # Título com várias categorias/departamentos: usa a de maior valor
        cat_cod = max(mov.get("categorias") or [{"cCodCateg": d.get("cCodCateg"), "nDistrValor": 0}],
                      key=lambda c: c.get("nDistrValor") or 0).get("cCodCateg") or d.get("cCodCateg")
        categoria, grupo = cats.get(cat_cod, (cat_cod or "(sem)", cat_cod or "(sem)"))
        dep = max(mov.get("departamentos") or [{}], key=lambda x: x.get("nDistrValor") or 0).get("cCodDepartamento")
        pago = dec(r.get("nValPago"))
        rows.append(dict(
            fornecedor=cli.get("razao_social") or cli.get("nome_fantasia") or "—",
            categoria=categoria, grupo=grupo,
            data_emissao=data_omie(d.get("dDtEmissao")) or data_omie(d.get("dDtRegistro")) or de,
            data_pagamento=data_omie(d.get("dDtPagamento")) if pago else None,
            departamento=deps.get(dep) or "N/D", cnpj_cpf=d.get("cCPFCNPJCliente") or cli.get("cnpj_cpf") or None,
            forma_pagamento=FORMAS.get(d.get("cTipo") or "", "N/D"), situacao=sit, tipo=TIPO_RECEBER if nat == "R" else TIPO_PAGAR,
            valor_conta=sinal * dec(d.get("nValorTitulo")), valor_pago=sinal * pago,
            conta_corrente=contas.get(d.get("nCodCC")) or None,
        ))
    return rows


# --------------------------------------------------------------------- faturamento
def _historico_produtos():
    """Linha, grupo, cor, produto simplificado e kg/unidade já usados nas planilhas, por código do produto."""
    hist = {}
    kg = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for v in Venda.objects.order_by("data").only("produto", "linha", "grupo", "cor", "produto_simplificado", "familia", "kg", "quantidade"):
        cod = codigo_produto(v.produto)
        hist[cod] = (v.linha, v.grupo, v.cor, v.produto_simplificado, v.familia)
        if v.kg and v.quantidade:
            kg[cod][0] += v.kg; kg[cod][1] += v.quantidade
    return hist, {c: k / q for c, (k, q) in kg.items() if q}


def buscar_vendas(de: date, ate: date) -> list[dict]:
    clis, prods, vends = mapa_clientes(), mapa_produtos(), mapa_vendedores()
    hist, kg_un = _historico_produtos()
    rows = []
    for nf in paginar("produtos/nfconsultar/", "ListarNF", "nfCadastro",
                      {"dEmiInicial": br(de), "dEmiFinal": br(ate), "tpNF": "1", "filtrar_por_status": "N",
                       "apenas_importado_api": "N", "cDetalhesPedido": "S"}, por_pagina=50):
        ide = nf.get("ide", {})
        if ide.get("dCan") or ide.get("cDeneg") == "S" or ide.get("finNFe") in ("4",):  # cancelada/denegada/devolução
            continue
        dest = nf.get("nfDestInt", {})
        cli = clis.get(dest.get("nCodCli")) or {}
        ped = nf.get("pedido") or {}
        tit = (nf.get("titulos") or [{}])[0]
        vendedor = vends.get(ped.get("nIdVendedor") or tit.get("nCodVendedor"))
        data_nf = data_omie(ide.get("dEmi"))
        for item in nf.get("det") or []:
            p = item.get("prod", {})
            cod = (p.get("cProd") or "").strip()
            cad = prods.get((item.get("nfProdInt") or {}).get("nCodProd")) or {}
            linha, grupo, cor, simpl, familia = hist.get(cod, (None, None, None, None, None))
            qtd = dec(p.get("qCom"))
            peso = kg_un.get(cod) or (dec(cad.get("peso_liq")) or None)
            rows.append(dict(
                data=data_nf, cliente=cli.get("razao_social") or dest.get("cRazao") or "—",
                produto=f"{cod} - {p.get('xProd', '').strip()}", linha=linha or cad.get("descricao_familia") or "(sem linha)",
                quantidade=qtd, valor_unitario=dec(p.get("vUnCom")), total=dec(p.get("vTotItem") or p.get("vProd")),
                kg=(qtd * peso).quantize(Decimal("0.001")) if peso else None,
                familia=familia or cod, descricao=p.get("xProd") or None, grupo=grupo, cor=cor, produto_simplificado=simpl,
                nota_fiscal=str(ide.get("nNF") or "") or None, tipo_documento="Nota Fiscal",
                orcamento=str(ped.get("cNumPedido") or "") or None, bairro=cli.get("bairro") or None,
                cidade=(cli.get("cidade") or "").split(" (")[0].title() or None, estado=cli.get("estado") or None,
                vendedor=vendedor or None, cnpj_cpf=dest.get("cnpj_cpf") or cli.get("cnpj_cpf") or None,
                unidade=p.get("uCom") or None,
            ))
    return [r for r in rows if r["data"]]


# --------------------------------------------------------------------- gravação
def substituir(modelo, campo_data, de, ate, rows, manter=None):
    with transaction.atomic():
        qs = modelo.objects.filter(**{f"{campo_data}__range": (de, ate)})
        if manter:
            qs = qs.exclude(**manter)
        apagados, _ = qs.delete()
        modelo.objects.bulk_create([modelo(**r) for r in rows], batch_size=500)
    return apagados


def sincronizar(de: date, ate: date, fluxo=True, vendas=True, saida=print) -> str:
    if not configurado():
        raise OmieErro("Defina OMIE_APP_KEY e OMIE_APP_SECRET no .env do servidor")
    partes = []
    if fluxo:
        rows = buscar_fluxo(de, ate)
        ap = substituir(FluxoCaixa, "data_emissao", de, ate, rows)
        partes.append(f"Fluxo de caixa: {len(rows)} lançamentos ({ap} substituídos)")
        saida(partes[-1])
    if vendas:
        rows = buscar_vendas(de, ate)
        # Recibos não existem como NF no Omie: os que vieram de planilha são mantidos
        ap = substituir(Venda, "data", de, ate, rows, manter={"tipo_documento__icontains": "recibo"})
        partes.append(f"Faturamento: {len(rows)} itens de NF ({ap} substituídos)")
        saida(partes[-1])
    return "; ".join(partes)
