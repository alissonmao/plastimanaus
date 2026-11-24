"""Leitura e exportação de planilhas (portado de planilha.ts e vendas.ts)."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook

from .calculos import codigo_produto, sem_acento
from .models import PROCESSO_EXTRUSAO, PRODUTO_BOBINA


def norm(s) -> str:
    s = sem_acento(s)
    s = re.sub(r"[\r\n.()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def texto(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def numero(v):
    """Aceita número ou texto no formato brasileiro (1.234,56)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        if v < 1:
            return None
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    return None


def abrir(arquivo) -> dict[str, list[list]]:
    """Retorna {nome_aba: matriz}. Aceita .xlsx/.xlsm e .csv."""
    nome = getattr(arquivo, "name", "")
    if re.search(r"\.(csv|txt)$", nome, re.I):
        txt = arquivo.read().decode("utf-8-sig", errors="replace")
        sep = ";" if ";" in txt.split("\n", 1)[0] else ","
        return {"csv": [row for row in csv.reader(io.StringIO(txt), delimiter=sep)]}
    wb = load_workbook(arquivo, read_only=True, data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def _mapear(cab, aliases):
    col = {}
    for j, h in enumerate(cab):
        nk = norm(h)
        for k, opts in aliases.items():
            if nk in opts and k not in col:
                col[k] = j
    return col


# ------------------------------------------------------------------ Apontamentos
ALIASES_AP = {
    "data": ["data"], "turno": ["turno"], "maquina": ["maquina", "maq"],
    "codmaq": ["cod maq", "codigo maquina", "cod maquina", "codigo"], "produto": ["produto"], "cor": ["cor"],
    "tipo": ["tipo", "tipo sacola", "tipo_sacola", "tipos de sacolas", "tipo de sacola"],
    "lar": ["lar", "largura", "largura mm", "lar mm"], "comp": ["comp", "comprimento", "comprimento mm", "comp mm"],
    "esp": ["esp", "espessura", "espessura mm", "espess mm"], "op": ["op", "ordem de producao", "ordem de producao op"],
    "ok_kg": ["ok_kg", "ok", "produzido ok kg", "produzido ok"], "apara": ["apara", "apara kg"],
    "alca": ["alca", "alca kg"], "borra": ["borra", "borra kg"],
    "qtd_milheiro": ["qtd_milheiro", "quantidade", "qtd milheiro", "milheiro", "quant milheiro"],
    "obs": ["obs", "observacao"], "cliente": ["cliente"],
}


def _vazio(v):
    return v is None or str(v).strip() == "" or v == 0


def ler_apontamentos(arquivo, L) -> tuple[list[dict], list[str], list[tuple[str, str]]]:
    """Lê a aba "Input" (ou a primeira). Retorna (linhas, erros, ops[(op, cliente)])."""
    abas = abrir(arquivo)
    nome = next((n for n in abas if norm(n) == "input"), next(iter(abas), None))
    erros, rows, ops = [], [], []
    mat = abas.get(nome) or []
    h = next((i for i, r in enumerate(mat) if "data" in [norm(x) for x in r]
              and any(norm(x) in ("maquina", "maq") for x in r)), -1)
    if h < 0:
        return rows, ["Cabeçalho com DATA e Máquina não encontrado"], ops
    col = _mapear(mat[h], ALIASES_AP)
    turnos = {norm(t.codigo): t for t in L["turnos"]}
    maq_cod = {norm(m.codigo): m for m in L["maquinas"]}
    maq_desc = {norm(m.descricao): m for m in L["maquinas"]}
    find = lambda arr, v: next((x for x in arr if norm(x.nome) == norm(v)), None)  # noqa: E731
    for i in range(h + 1, len(mat)):
        rec = mat[i]
        g = lambda k: (rec[col[k]] if k in col and col[k] < len(rec) else "")  # noqa: E731
        n_linha = i + 1
        if _vazio(g("data")):
            continue
        d = parse_data(g("data"))
        if not d:
            erros.append(f"Linha {n_linha}: data inválida"); continue
        turno = turnos.get(norm(g("turno")))
        maq = maq_cod.get(norm(g("codmaq"))) or maq_desc.get(norm(g("maquina"))) or maq_cod.get(norm(g("maquina")))
        if not turno:
            erros.append(f'Linha {n_linha}: turno "{g("turno")}" não cadastrado'); continue
        if not maq:
            erros.append(f'Linha {n_linha}: máquina "{g("codmaq") or g("maquina")}" não cadastrada'); continue
        pv, cv, tv = g("produto"), g("cor"), g("tipo")
        produto = find(L["produtos"], pv) if not _vazio(pv) else None
        cor = find(L["cores"], cv) if not _vazio(cv) else None
        ext = maq.familia.setor.processo == PROCESSO_EXTRUSAO
        tipo = find(L["tipos"], tv) if (not ext and not _vazio(tv)) else None
        if not _vazio(pv) and not produto:
            erros.append(f'Linha {n_linha}: produto "{pv}" não cadastrado'); continue
        if not _vazio(cv) and not cor:
            erros.append(f'Linha {n_linha}: cor "{cv}" não cadastrada'); continue
        if not ext and not _vazio(tv) and not tipo:
            erros.append(f'Linha {n_linha}: tipo "{tv}" não cadastrado'); continue
        op = texto(g("op")) or None
        cliente = texto(g("cliente"))
        if op and cliente:
            ops.append((op, cliente))
        rows.append(dict(
            data=d, turno=turno, maquina=maq, produto=produto, cor=cor, tipo_sacola=tipo,
            largura_mm=numero(g("lar")),
            comprimento_mm=None if (produto and produto.nome == PRODUTO_BOBINA) else numero(g("comp")),
            espessura_mm=numero(g("esp")), op=op,
            ok_kg=numero(g("ok_kg")) or 0, apara_kg=numero(g("apara")) or 0,
            alca_kg=0 if ext else (numero(g("alca")) or 0), borra_kg=numero(g("borra")) or 0,
            qtd_milheiro=None if ext else numero(g("qtd_milheiro")), observacao=texto(g("obs")) or None,
        ))
    return rows, erros, ops


# ------------------------------------------------------------------ Vendas (Omie)
ALIASES_VENDAS = {
    "data": ["data"], "cliente": ["cliente"], "produto": ["produto"], "linha": ["linha"],
    "quantidade": ["quantidade", "qtd"], "valor_unitario": ["valor unitario", "vlr unitario", "unitario"],
    "total": ["total", "valor total"], "kg": ["kg sacola/bobina", "kg"], "familia": ["falilia", "familia"],
    "descricao": ["descricao"], "grupo": ["grupo"], "cor": ["cor"], "produto_simplificado": ["produto simplificado"],
    "nota_fiscal": ["nota fiscal", "nf", "numero nf", "n nf"],
    "tipo_documento": ["tipo documento", "tipo de documento", "tipo doc", "documento"],
    "orcamento": ["orcamento", "pedido", "n orcamento"], "bairro": ["bairro"], "cidade": ["cidade", "municipio"],
    "estado": ["estado", "uf"], "vendedor": ["vendedor", "representante"],
    "cnpj_cpf": ["cnpj/cpf", "cnpj cpf", "cnpj", "cpf"], "unidade": ["unidade", "un"],
}
TEXTOS_VENDAS = ["nota_fiscal", "tipo_documento", "orcamento", "bairro", "cidade", "estado", "vendedor", "cnpj_cpf", "unidade"]


def normalizar_grupo(v):
    s = texto(v)
    if not s or re.search(r"planejamento de vendas", s, re.I):
        return None
    return re.sub(r"(\d)([a-zA-Z])", r"\1 \2", s)


def ler_vendas(arquivo):
    abas = abrir(arquivo)
    nome = next((n for n in abas if norm(n) == "base de dados"), None)
    if not nome:
        return [], ['Aba "Base de Dados" não encontrada']
    mat, rows, erros = abas[nome], [], []
    h = next((i for i, r in enumerate(mat) if {"data", "cliente", "total"} <= {norm(x) for x in r}), -1)
    if h < 0:
        return [], ["Cabeçalho com Data, Cliente e Total não encontrado"]
    col = _mapear(mat[h], ALIASES_VENDAS)
    for i in range(h + 1, len(mat)):
        r = mat[i]
        g = lambda k: (r[col[k]] if k in col and col[k] < len(r) else "")  # noqa: E731
        if texto(g("data")) == "":
            continue
        d, total = parse_data(g("data")), numero(g("total"))
        cliente, produto, linha = texto(g("cliente")), texto(g("produto")), texto(g("linha"))
        if not d:
            erros.append(f"Linha {i + 1}: data inválida"); continue
        if total is None:
            erros.append(f"Linha {i + 1}: total inválido"); continue
        if not (cliente and produto and linha):
            erros.append(f"Linha {i + 1}: cliente/produto/linha vazio"); continue
        rows.append(dict(
            data=d, cliente=cliente, produto=produto, linha=linha, quantidade=numero(g("quantidade")),
            valor_unitario=numero(g("valor_unitario")), total=total, kg=numero(g("kg")),
            familia=texto(g("familia")) or codigo_produto(produto), descricao=texto(g("descricao")) or None,
            grupo=normalizar_grupo(g("grupo")), cor=texto(g("cor")) or None,
            produto_simplificado=texto(g("produto_simplificado")) or None,
            **{k: texto(g(k)) or None for k in TEXTOS_VENDAS},
        ))
    return rows, erros


# ------------------------------------------------------------------ Fluxo de caixa (Omie)
ALIASES_FLUXO = {
    "fornecedor": ["fornecedor", "cliente / fornecedor", "cliente/fornecedor", "cliente fornecedor", "fornecedor/cliente"],
    "categoria": ["categoria"], "data_emissao": ["data emissao", "emissao", "data de emissao"],
    "data_pagamento": ["data pagamento", "data de pagamento", "pagamento", "data recebimento", "data pagamento/recebimento", "data de pagamento/recebimento"],
    "departamento": ["departamento"], "cnpj_cpf": ["cnpj/cpf", "cnpj cpf", "cnpj", "cpf"], "grupo": ["grupo"],
    "forma_pagamento": ["forma pagamento", "forma de pagamento", "tipo documento"], "situacao": ["situacao", "status"],
    "tipo": ["tipo"], "valor_conta": ["valor conta", "valor da conta", "valor"],
    "valor_pago": ["valor pago", "valor pago/recebido", "valor recebido", "pago"],
    "conta_corrente": ["conta corrente", "conta"],
}


def ler_fluxo(arquivo):
    abas = abrir(arquivo)
    mat = next(iter(abas.values()), [])
    h = next((i for i, r in enumerate(mat) if {"categoria", "grupo"} <= {norm(x) for x in r}), -1)
    if h < 0:
        return [], ["Cabeçalho com Categoria e Grupo não encontrado"]
    col = _mapear(mat[h], ALIASES_FLUXO)
    rows, erros = [], []
    for i in range(h + 1, len(mat)):
        r = mat[i]
        g = lambda k: (r[col[k]] if k in col and col[k] < len(r) else "")  # noqa: E731
        if not any(texto(x) for x in r):
            continue
        de = parse_data(g("data_emissao"))
        vc = numero(g("valor_conta"))
        if not de or vc is None:
            erros.append(f"Linha {i + 1}: data de emissão ou valor inválido"); continue
        rows.append(dict(
            fornecedor=texto(g("fornecedor")) or "—", categoria=texto(g("categoria")) or "(sem)", data_emissao=de,
            data_pagamento=parse_data(g("data_pagamento")), departamento=texto(g("departamento")) or None,
            cnpj_cpf=texto(g("cnpj_cpf")) or None, grupo=texto(g("grupo")) or "(sem)",
            forma_pagamento=texto(g("forma_pagamento")) or None, situacao=texto(g("situacao")) or "",
            tipo=texto(g("tipo")) or "", valor_conta=vc, valor_pago=numero(g("valor_pago")) or 0,
            conta_corrente=texto(g("conta_corrente")) or None,
        ))
    return rows, erros


# ------------------------------------------------------------------ Exportação
def xlsx_response(linhas: list[dict], nome: str):
    from django.http import HttpResponse
    wb = Workbook()
    ws = wb.active
    ws.title = "Dados"
    if linhas:
        ws.append(list(linhas[0].keys()))
        for l in linhas:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in l.values()])
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{nome}.xlsx"'
    return resp
