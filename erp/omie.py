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
from datetime import date, datetime, timedelta
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
        # Consumo redundante (mesma chamada em < 60 s): o Omie exige esperar 1 minuto
        if "REDUNDANT" in msg or "redundante" in msg.lower():
            time.sleep(62)
            continue
        # Limite de requisições / instabilidade: espera e tenta de novo
        if r.status_code in (425, 429, 500, 502, 503) or "bloqueada" in msg.lower():
            time.sleep(10 * (t + 1))
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
_CACHE: dict = {}


def em_cache(func):
    """Guarda o resultado durante o processo (o Omie recusa a mesma consulta repetida em < 60 s)."""
    def wrap():
        if func.__name__ not in _CACHE:
            _CACHE[func.__name__] = func()
        return _CACHE[func.__name__]
    wrap.__name__ = func.__name__
    return wrap


def limpar_cache():
    _CACHE.clear()


@em_cache
def mapa_categorias():
    cats = {c["codigo"]: c for c in paginar("geral/categorias/", "ListarCategorias", "categoria_cadastro")}
    out = {}
    for cod, c in cats.items():
        sup = cats.get(c.get("categoria_superior") or "")
        out[cod] = (c.get("descricao") or cod, (sup or {}).get("descricao") or c.get("descricao") or cod)
    return out  # codigo -> (categoria, grupo)


@em_cache
def mapa_clientes():
    return {c["codigo_cliente_omie"]: c for c in paginar("geral/clientes/", "ListarClientes", "clientes_cadastro",
                                                          {"apenas_importado_api": "N"}, por_pagina=50)}


@em_cache
def mapa_contas():
    return {c["nCodCC"]: c.get("descricao", "") for c in paginar(
        "geral/contacorrente/", "ListarResumoContasCorrentes", "conta_corrente_lista", {"apenas_importado_api": "N"})}


@em_cache
def mapa_departamentos():
    return {d["codigo"]: d.get("descricao", "") for d in paginar("geral/departamentos/", "ListarDepartamentos", "departamentos")}


@em_cache
def mapa_vendedores():
    return {v["codigo"]: v.get("nome", "") for v in paginar("geral/vendedores/", "ListarVendedores", "cadastro")}


@em_cache
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
            fornecedor=cli.get("nome_fantasia") or cli.get("razao_social") or "—",  # igual à exportação do Omie
            categoria=categoria, grupo=grupo,
            data_emissao=data_omie(d.get("dDtEmissao")) or data_omie(d.get("dDtRegistro")) or de,
            data_pagamento=data_omie(d.get("dDtPagamento")) if pago else None,
            departamento=deps.get(dep) or "N/D", cnpj_cpf=d.get("cCPFCNPJCliente") or cli.get("cnpj_cpf") or None,
            forma_pagamento=FORMAS.get(d.get("cTipo") or "", "N/D"), situacao=sit, tipo=TIPO_RECEBER if nat == "R" else TIPO_PAGAR,
            valor_conta=sinal * dec(d.get("nValorTitulo")), valor_pago=sinal * pago,
            conta_corrente=contas.get(d.get("nCodCC")) or None,
            data_vencimento=data_omie(d.get("dDtVenc")), data_previsao=data_omie(d.get("dDtPrevisao")),
            numero_documento=(d.get("cNumDocFiscal") or d.get("cNumTitulo") or "").strip() or None,
            parcela=(d.get("cNumParcela") or "").strip() or None, omie_codigo=d.get("nCodTitulo"),
            observacao=(d.get("observacao") or "").strip() or None,
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


def sincronizar(de: date, ate: date, fluxo=True, vendas=True, saida=print, registro=None) -> str:
    if not configurado():
        raise OmieErro("Defina OMIE_APP_KEY e OMIE_APP_SECRET no .env do servidor")
    limpar_cache()
    partes = []
    if fluxo:
        from . import auditoria
        rows = buscar_fluxo(de, ate)
        antes = auditoria.foto(de, ate)
        if not rows and len(antes) > 20:  # proteção: resposta vazia do Omie não apaga o ERP nem gera "exclusões" falsas
            raise OmieErro(f"O Omie não devolveu lançamentos para {br(de)} a {br(ate)}, mas o ERP tem {len(antes)}. Nada foi alterado.")
        mudancas = auditoria.comparar(antes, rows, registro)
        with transaction.atomic():
            ap = substituir(FluxoCaixa, "data_emissao", de, ate, rows)
        n = auditoria.gravar(mudancas) if antes else 0  # primeira leitura do período: só guarda a "foto"
        partes.append(f"Fluxo de caixa: {len(rows)} lançamentos ({ap} substituídos); auditoria: {n} mudança{'s' if n != 1 else ''}")
        saida(partes[-1])
    if vendas:
        rows = buscar_vendas(de, ate)
        # Recibos não existem como NF no Omie: os que vieram de planilha são mantidos
        ap = substituir(Venda, "data", de, ate, rows, manter={"tipo_documento__icontains": "recibo"})
        partes.append(f"Faturamento: {len(rows)} itens de NF ({ap} substituídos)")
        saida(partes[-1])
    return "; ".join(partes)


# --------------------------------------------------------------------- saldos das contas
def atualizar_saldos(saida=print) -> int:
    """Lê o saldo atual de cada conta corrente (ListarExtrato). Só leitura no Omie."""
    from .models import SaldoContaOmie
    hoje = date.today()
    n = 0
    for c in paginar("geral/contacorrente/", "ListarResumoContasCorrentes", "conta_corrente_lista", {"apenas_importado_api": "N"}):
        r = chamar("financas/extrato/", "ListarExtrato", {"nCodCC": c["nCodCC"], "dPeriodoInicial": br(hoje - timedelta(days=1)),
                                                          "dPeriodoFinal": br(hoje)})
        if "nSaldoAtual" not in r:
            continue
        SaldoContaOmie.objects.update_or_create(codigo=c["nCodCC"], defaults=dict(
            descricao=(r.get("cDescricao") or c.get("descricao") or "").strip(), saldo=dec(r["nSaldoAtual"]),
            fluxo_caixa=r.get("cFluxoCaixa", "S") == "S"))
        n += 1
    saida(f"Saldos de {n} contas atualizados")
    return n


# --------------------------------------------------------------------- pedidos de venda
ETAPAS_PEDIDO = {"00": "Proposta/Orçamento", "10": "Pedido de venda", "20": "Separar estoque", "30": "Em separação",
                 "40": "Separado", "50": "Faturar", "60": "Faturado", "70": "Entregue", "80": "Concluído"}


def _pedido(p, clientes, vendedores):
    cab, info = p.get("cabecalho") or {}, p.get("infoCadastro") or {}
    tot, adic = p.get("total_pedido") or {}, p.get("informacoes_adicionais") or {}
    cli = clientes.get(cab.get("codigo_cliente")) or {}
    etapa = str(cab.get("etapa") or "")
    cancelado, devolvido, faturado = info.get("cancelado") == "S", info.get("devolvido") == "S", info.get("faturado") == "S"
    situacao = ("Cancelado" if cancelado else "Devolvido" if devolvido else "Faturado" if faturado
                else ETAPAS_PEDIDO.get(etapa, f"Etapa {etapa}"))
    parcelas = (p.get("lista_parcelas") or {}).get("parcela") or []
    itens = []
    for d in p.get("det") or []:
        pr = d.get("produto") or {}
        itens.append(dict(codigo_produto=str(pr.get("codigo") or ""), descricao=(pr.get("descricao") or "")[:300],
                          unidade=(pr.get("unidade") or "")[:10], quantidade=dec(pr.get("quantidade")),
                          valor_unitario=dec(pr.get("valor_unitario")), valor_desconto=dec(pr.get("valor_desconto")),
                          valor_total=dec(pr.get("valor_total"))))
    return dict(
        codigo=cab.get("codigo_pedido"), numero=str(cab.get("numero_pedido") or ""), data_previsao=data_omie(cab.get("data_previsao")),
        data_inclusao=data_omie(info.get("dInc")), data_alteracao=data_omie(info.get("dAlt")),
        cliente=(cli.get("razao_social") or cli.get("nome_fantasia") or str(cab.get("codigo_cliente") or ""))[:300],
        cnpj_cpf=(cli.get("cnpj_cpf") or "")[:30], vendedor=(vendedores.get(adic.get("codVend")) or "")[:200],
        etapa=etapa[:4], situacao=situacao, faturado=faturado, cancelado=cancelado, devolvido=devolvido,
        valor_mercadorias=dec(tot.get("valor_mercadorias")), valor_descontos=dec(tot.get("valor_descontos")),
        valor_total=dec(tot.get("valor_total_pedido")), qtd_itens=len(itens),
        peso_liquido=dec((p.get("frete") or {}).get("peso_liquido")),
        parcelas=", ".join(f"{x.get('data_vencimento', '')} R$ {x.get('valor', 0)}" for x in parcelas)[:300],
        observacao=((p.get("observacoes") or {}).get("obs_venda") or "")), itens


def sincronizar_pedidos(saida=print) -> int:
    """Traz todos os pedidos de venda do Omie e substitui a cópia local. Só leitura no Omie."""
    from django.db import transaction
    from .models import PedidoItemOmie, PedidoOmie
    clientes, vendedores = mapa_clientes(), mapa_vendedores()
    lidos = [_pedido(p, clientes, vendedores) for p in paginar("produtos/pedido/", "ListarPedidos", "pedido_venda_produto",
                                                               {"apenas_importado_api": "N"}, por_pagina=50)]
    lidos = [x for x in lidos if x[0]["codigo"]]
    if not lidos and PedidoOmie.objects.count() > 20:
        raise OmieErro("Omie não devolveu nenhum pedido; a cópia local foi mantida")
    with transaction.atomic():
        PedidoOmie.objects.all().delete()
        objs = PedidoOmie.objects.bulk_create([PedidoOmie(**cab) for cab, _ in lidos], batch_size=500)
        PedidoItemOmie.objects.bulk_create([PedidoItemOmie(pedido=o, **it) for o, (_, itens) in zip(objs, lidos) for it in itens],
                                           batch_size=1000)
    saida(f"{len(lidos)} pedidos do Omie atualizados")
    return len(lidos)


# ===================================================================== Estoque (só leitura)
TIPOS_ITEM = {"00": "Revenda", "01": "Matéria-prima", "02": "Embalagem", "03": "Produto em processo", "04": "Produto acabado",
              "05": "Subproduto", "06": "Produto intermediário", "07": "Uso e consumo", "08": "Ativo imobilizado",
              "09": "Serviço", "10": "Outros insumos", "99": "Outros"}
MOV_INICIO = date(2025, 12, 1)   # início do uso do estoque no Omie
HORA_COMPLETA = 3                # de madrugada traz o histórico inteiro; nas outras horas só os 2 últimos meses


def _pag_estoque(endpoint, call, lista, param):
    # o Omie devolve no máximo 100 por página nessas listas
    return paginar(endpoint, call, lista, param, por_pagina=100, chave_pag="nPagina", chave_qtd="nRegPorPagina",
                   chave_total="nTotPaginas")


def _meses(ini, fim):
    d = ini.replace(day=1)
    while d <= fim:
        prox = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(d, ini), min(prox - timedelta(days=1), fim)
        d = prox


def _produto(p):
    info = p.get("info") or {}
    return dict(codigo_produto=p.get("codigo_produto"), codigo=str(p.get("codigo") or "")[:60], descricao=(p.get("descricao") or "")[:300],
                familia=(p.get("descricao_familia") or "")[:120], unidade=(p.get("unidade") or "")[:10],
                tipo_item=TIPOS_ITEM.get(str(p.get("tipoItem") or ""), str(p.get("tipoItem") or ""))[:40],
                ncm=(p.get("ncm") or "")[:20], ean=(p.get("ean") or "")[:30], peso_liquido=dec(p.get("peso_liq")),
                peso_bruto=dec(p.get("peso_bruto")), estoque_minimo=dec(p.get("estoque_minimo")), preco=dec(p.get("valor_unitario")),
                inativo=p.get("inativo") == "S", alterado_em=data_omie(info.get("dAlt")))


def sincronizar_estoque(saida=print, hoje=None, completo=None) -> str:
    """Traz do Omie o cadastro de produtos, a posição de estoque de cada local e as movimentações,
    e substitui a cópia local. Só leitura no Omie.
    As movimentações vêm mês a mês e local por local: com período longo ou sem local o Omie corta registros.
    Sem `completo`, refaz só os 2 últimos meses (exceto de madrugada ou com a cópia vazia)."""
    from django.db import transaction
    from .models import EstoqueOmie, MovEstoqueOmie, ProdutoOmie
    hoje = hoje or date.today()
    if completo is None:
        completo = datetime.now().hour == HORA_COMPLETA or not MovEstoqueOmie.objects.exists()
    inicio = MOV_INICIO if completo else max(MOV_INICIO, (hoje.replace(day=1) - timedelta(days=1)).replace(day=1))
    produtos = [_produto(p) for p in paginar("geral/produtos/", "ListarProdutos", "produto_servico_cadastro",
                                             {"apenas_importado_api": "N", "filtrar_apenas_omiepdv": "N"}, por_pagina=100)]
    produtos = [p for p in produtos if p["codigo_produto"]]
    locais = list(_pag_estoque("estoque/local/", "ListarLocaisEstoque", "locaisEncontrados", {}))
    nome_local = {l["codigo_local_estoque"]: (l.get("descricao") or l.get("codigo") or "")[:80] for l in locais}
    posicao = []
    for l in locais:
        if l.get("inativo") == "S":
            continue
        for p in _pag_estoque("estoque/consulta/", "ListarPosEstoque", "produtos",
                              {"dDataPosicao": br(hoje), "cExibeTodos": "N", "codigo_local_estoque": l["codigo_local_estoque"]}):
            saldo, cmc = dec(p.get("nSaldo")), dec(p.get("nCMC"))
            posicao.append(dict(local=nome_local[l["codigo_local_estoque"]], local_codigo=(l.get("codigo") or "")[:10],
                                codigo_produto=p.get("nCodProd"), codigo=str(p.get("cCodigo") or "")[:60],
                                descricao=(p.get("cDescricao") or "")[:300], saldo=saldo, fisico=dec(p.get("fisico")),
                                reservado=dec(p.get("reservado")), pendente=dec(p.get("nPendente")), minimo=dec(p.get("estoque_minimo")),
                                custo_medio=cmc, preco=dec(p.get("nPrecoUnitario")), valor=round(saldo * cmc, 2)))
    movs = {}
    ativos = [l for l in locais if l.get("inativo") != "S"]
    lista_movs = (m for a, b in _meses(inicio, hoje) for l in ativos
                  for m in _pag_estoque("estoque/consulta/", "ListarMovimentoEstoque", "movProdutoListar",
                                        {"dDtInicial": br(a), "dDtFinal": br(b), "codigo_local_estoque": l["codigo_local_estoque"]}))
    for m in lista_movs:
        d = data_omie(m.get("dtMov"))
        if not m.get("idMov") or not d:
            continue
        movs[m["idMov"]] = dict(id_mov=m["idMov"], data=d, local=nome_local.get(m.get("codigo_local_estoque"), "")[:80],
                                codigo_produto=m.get("idProd") or 0, descricao=(m.get("descricao") or "")[:300],
                                tipo=(m.get("tipo") or "")[:10], origem=(m.get("codOrigem") or "")[:10],
                                origem_desc=(m.get("desOrigem") or "")[:120], documento=str(m.get("numDoc") or "")[:60],
                                pedido=str(m.get("numPedido") or "")[:120], quantidade=dec(m.get("qtde")), saldo=dec(m.get("saldo")),
                                custo_medio=dec(m.get("cmc")), cancelado=m.get("cancelamento") == "S", devolucao=m.get("devolucao") == "S")
    if not produtos and ProdutoOmie.objects.count() > 20:
        raise OmieErro("Omie não devolveu nenhum produto; a cópia local do estoque foi mantida")
    vistos = set()
    posicao = [p for p in posicao if p["codigo_produto"] and (p["local"], p["codigo_produto"]) not in vistos
               and not vistos.add((p["local"], p["codigo_produto"]))]
    with transaction.atomic():
        ProdutoOmie.objects.all().delete()
        ProdutoOmie.objects.bulk_create([ProdutoOmie(**p) for p in produtos], batch_size=500)
        EstoqueOmie.objects.all().delete()
        EstoqueOmie.objects.bulk_create([EstoqueOmie(**p) for p in posicao], batch_size=500)
        MovEstoqueOmie.objects.filter(data__gte=inicio).delete()
        MovEstoqueOmie.objects.filter(id_mov__in=list(movs)).delete()
        MovEstoqueOmie.objects.bulk_create([MovEstoqueOmie(**m) for m in movs.values()], batch_size=1000)
    msg = (f"Estoque: {len(produtos)} produtos, {len(posicao)} saldos em {len(nome_local)} locais, {len(movs)} movimentações "
           f"desde {inicio:%d/%m/%Y}" + (" (histórico completo)" if completo else ""))
    saida(msg)
    return msg
