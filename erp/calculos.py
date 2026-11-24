"""Regras de cálculo portadas do ERP Lovable (src/lib/producao.ts, vendas.ts,
fluxo-caixa.ts e vendas-plasti.ts)."""
from __future__ import annotations

import calendar
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import PROCESSO_CORTE, Apontamento

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
ORDEM_SETORES = ["Extrusão Carnevalli", "Extrusão Plastar", "Extrusão Gr", "Corte"]


def f(v) -> float:
    return float(v) if v is not None else 0.0


def sem_acento(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def rotulo_mes(chave: str) -> str:
    return f"{MESES[int(chave[5:7]) - 1]}/{chave[2:4]}"


def chave_periodo(d: date, g: str) -> str:
    if g == "dia":
        return d.isoformat()
    if g == "semana":
        seg = d - timedelta(days=d.weekday())
        return seg.isoformat()
    if g == "trimestre":
        return f"{d.year}-T{(d.month - 1) // 3 + 1}"
    if g == "ano":
        return str(d.year)
    return d.strftime("%Y-%m")


def rotulo_periodo(chave: str, g: str) -> str:
    if g == "dia":
        return f"{chave[8:10]}/{chave[5:7]}"
    if g == "semana":
        return f"sem {chave[8:10]}/{chave[5:7]}"
    if g == "trimestre":
        return f"{chave[5:]}/{chave[2:4]}"
    if g == "ano":
        return chave
    return rotulo_mes(chave)


def ordenar_setores(nomes):
    def ordem(n):
        return ORDEM_SETORES.index(n) if n in ORDEM_SETORES else len(ORDEM_SETORES)
    return sorted(nomes, key=lambda n: (ordem(n), n))


# ================================================================ Produção
@dataclass
class Linha:
    a: Apontamento
    ok: float
    apara: float
    alca: float
    borra: float
    perdas: float
    total: float
    kg_milheiro: float | None
    cap: float | None
    horas_disp: float | None
    horas_ok: float | None
    horas_perdas: float | None
    horas_trab: float | None
    util: float | None
    maquina: str
    maquina_codigo: str
    familia: str
    setor: str
    processo: str
    turno: str
    produto: str
    cor: str
    tipo: str
    cliente: str
    descricao: str


def _fmt_medida(v, casas):
    if v is None:
        return ""
    s = f"{float(v):.{casas}f}".rstrip("0").rstrip(".") if casas else f"{float(v):.0f}"
    return s.replace(".", ",")


def enriquecer(apontamentos, op_cliente: dict[str, str]) -> list[Linha]:
    out = []
    for a in apontamentos:
        m = a.maquina
        setor = m.familia.setor
        ok, apara, alca, borra = f(a.ok_kg), f(a.apara_kg), f(a.alca_kg), f(a.borra_kg)
        perdas = apara + alca + borra
        total = ok + perdas
        kgm = None
        if setor.processo == PROCESSO_CORTE and a.largura_mm and a.comprimento_mm and a.espessura_mm:
            kgm = f(a.largura_mm) * f(a.comprimento_mm) * f(a.espessura_mm) / 1000
        cap = f(m.capacidade_kg_h) if m.capacidade_kg_h else 0
        hd = a.turno.horas
        if cap > 0:
            ht = total / cap
            horas = (cap, hd, ok / cap, perdas / cap, ht, (ht / hd) if hd else None)
        else:
            horas = (None,) * 6
        produto = a.produto.nome if a.produto else ""
        cor = a.cor.nome if a.cor else ""
        tipo = a.tipo_sacola.nome if a.tipo_sacola else ""
        desc = "-".join(x for x in [produto, cor, tipo, _fmt_medida(a.largura_mm, 0),
                                    _fmt_medida(a.comprimento_mm, 0), _fmt_medida(a.espessura_mm, 4)] if x)
        out.append(Linha(
            a, ok, apara, alca, borra, perdas, total, kgm, *horas,
            maquina=m.descricao, maquina_codigo=m.codigo, familia=m.familia.nome, setor=setor.nome,
            processo=setor.processo, turno=a.turno.codigo, produto=produto, cor=cor, tipo=tipo,
            cliente=op_cliente.get((a.op or "").strip(), ""), descricao=desc,
        ))
    return out


def totalizar(rows: list[Linha]) -> dict:
    t = dict(n=len(rows), ok=0.0, apara=0.0, alca=0.0, borra=0.0, perdas=0.0, total=0.0, milheiro=0.0,
             parados=0, horas_disp=0.0, horas_ok=0.0, horas_perdas=0.0, horas_trab=0.0)
    for r in rows:
        t["ok"] += r.ok; t["apara"] += r.apara; t["alca"] += r.alca; t["borra"] += r.borra
        t["perdas"] += r.perdas; t["total"] += r.total; t["milheiro"] += f(r.a.qtd_milheiro)
        if r.total == 0:
            t["parados"] += 1
        if r.cap:
            t["horas_disp"] += r.horas_disp or 0; t["horas_ok"] += r.horas_ok or 0
            t["horas_perdas"] += r.horas_perdas or 0; t["horas_trab"] += r.horas_trab or 0
    t["util"] = t["horas_trab"] / t["horas_disp"] if t["horas_disp"] else None
    t["pct_ok"] = t["ok"] / t["total"] if t["total"] else None
    t["pct_perdas"] = t["perdas"] / t["total"] if t["total"] else None
    return t


def agrupar(rows: list[Linha], chave) -> list[dict]:
    m: dict[str, list[Linha]] = defaultdict(list)
    for r in rows:
        m[chave(r) or "(vazio)"].append(r)
    return [{"grupo": k, **totalizar(v)} for k, v in m.items()]


def utilizacao_capacidade(rows: list[Linha]) -> dict:
    por_maq: dict = defaultdict(list)
    for r in rows:
        if r.cap:
            por_maq[r.a.maquina_id].append(r)
    maquinas = []
    for rs in por_maq.values():
        cap = rs[0].cap
        turnos = {(r.a.data, r.a.turno_id): r.a.turno for r in rs}
        horas, sem_horario = 0.0, 0
        for t in turnos.values():
            h = t.horas
            if h is None:
                sem_horario += 1
            else:
                horas += h
        tt = totalizar(rs)
        disp = cap * horas
        maquinas.append(dict(maquina=rs[0].maquina, capacidade=cap, turnos=len(turnos), sem_horario=sem_horario,
                             horas=horas, disponivel=disp, total=tt["total"], ok=tt["ok"],
                             util=tt["total"] / disp if disp else None, util_ok=tt["ok"] / disp if disp else None))
    maquinas.sort(key=lambda m: (-(m["util"] or -1), m["maquina"]))
    disp = sum(m["disponivel"] for m in maquinas)
    total = sum(m["total"] for m in maquinas)
    return dict(maquinas=maquinas, disponivel=disp, total=total, util=total / disp if disp else None)


# ================================================================ Vendas (Omie)
LINHAS_KG = {"sacola", "bobina"}


def linha_com_kg(linha: str) -> bool:
    return (linha or "").strip().lower() in LINHAS_KG


def codigo_produto(produto: str) -> str:
    i = produto.find(" - ")
    return (produto[:i] if i >= 0 else produto).strip()


def totais_vendas(rows) -> dict:
    fat = kg = fat_kg = 0.0
    cli, prod = set(), set()
    for r in rows:
        t = f(r.total)
        fat += t
        cli.add(r.cliente); prod.add(codigo_produto(r.produto))
        if linha_com_kg(r.linha) and r.kg is not None:
            kg += f(r.kg); fat_kg += t
    return dict(faturamento=fat, kg=kg, rs_kg=fat_kg / kg if kg else None, clientes=len(cli),
                produtos=len(prod), itens=len(rows), ticket=fat / len(cli) if cli else None)


def ranking(rows, chave, valor=lambda r: f(r.total)) -> list[dict]:
    tot = sum(valor(r) for r in rows)
    m: dict = {}
    for r in rows:
        k = chave(r) or "(vazio)"
        e = m.setdefault(k, dict(nome=k, total=0.0, kg=0.0, compras=0))
        e["total"] += valor(r); e["kg"] += f(getattr(r, "kg", 0)); e["compras"] += 1
    out = sorted(m.values(), key=lambda e: -e["total"])
    for e in out:
        e["pct"] = e["total"] / tot if tot else 0
    return out


def serie_vendas_periodo(rows, g: str):
    m: dict = {}
    linhas = set()
    for r in rows:
        k = chave_periodo(r.data, g)
        e = m.setdefault(k, dict(total=0.0, linhas=defaultdict(float), kg=0.0, fat_kg=0.0))
        t = f(r.total)
        e["total"] += t
        e["linhas"][r.linha] += t
        linhas.add(r.linha)
        if linha_com_kg(r.linha) and r.kg:
            e["kg"] += f(r.kg); e["fat_kg"] += t
    chaves = sorted(m)
    linhas = sorted(linhas, key=lambda l: -sum(m[k]["linhas"].get(l, 0) for k in chaves))
    return dict(
        labels=[rotulo_periodo(k, g) for k in chaves],
        series=[dict(nome=l, valores=[round(m[k]["linhas"].get(l, 0), 2) for k in chaves]) for l in linhas],
        rs_kg=[round(m[k]["fat_kg"] / m[k]["kg"], 2) if m[k]["kg"] else None for k in chaves],
    )


# ================================================================ Fluxo de caixa
SITUACOES_REALIZADAS = {"Pago", "Recebido", "Conciliado", "Pago Parcialmente", "Recebido Parcialmente"}
TIPO_RECEBER = "1. Contas a Receber"
TIPO_PAGAR = "2. Contas a Pagar"
DATA_MINIMA_FLUXO = date(2026, 1, 1)


def data_ref(r) -> date:
    return r.data_pagamento or r.data_emissao


def is_realizado(s: str) -> bool:
    return (s or "").strip() in SITUACOES_REALIZADAS


def kpis_fluxo(rows) -> dict:
    k = dict(entradas=0.0, gastos=0.0, aberto_receber=0.0, aberto_pagar=0.0,
             atrasados_receber=0.0, qtd_atrasados_receber=0, atrasados_pagar=0.0, qtd_atrasados_pagar=0)
    for r in rows:
        v, pg = f(r.valor_conta), f(r.valor_pago)
        if pg > 0:
            k["entradas"] += pg
        elif pg < 0:
            k["gastos"] += -pg
        if not is_realizado(r.situacao):
            resto = max(0.0, abs(v) - abs(pg))
            if v > 0:
                k["aberto_receber"] += resto
            elif v < 0:
                k["aberto_pagar"] += resto
        if (r.situacao or "").strip().startswith("Atrasado"):
            if v > 0:
                k["atrasados_receber"] += abs(v); k["qtd_atrasados_receber"] += 1
            elif v < 0:
                k["atrasados_pagar"] += abs(v); k["qtd_atrasados_pagar"] += 1
    k["saldo"] = k["entradas"] - k["gastos"]
    k["margem"] = k["saldo"] / k["entradas"] if k["entradas"] else None
    return k


def serie_fluxo(rows, g: str = "mes"):
    m: dict = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        k = chave_periodo(data_ref(r), g)
        pg = f(r.valor_pago)
        if pg > 0:
            m[k][0] += pg
        else:
            m[k][1] += -pg
    chaves = sorted(m)
    acc, acum = 0.0, []
    for c in chaves:
        acc += m[c][0] - m[c][1]
        acum.append(round(acc, 2))
    return dict(labels=[rotulo_periodo(c, g) for c in chaves],
                entradas=[round(m[c][0], 2) for c in chaves],
                gastos=[round(m[c][1], 2) for c in chaves], acumulado=acum)


def ranking_fluxo(rows, chave, sinal: int):
    m: dict = defaultdict(float)
    for r in rows:
        pg = f(r.valor_pago)
        if (sinal == 1 and pg <= 0) or (sinal == -1 and pg >= 0):
            continue
        m[chave(r) or "(sem)"] += abs(pg)
    tot = sum(m.values())
    return [dict(nome=k, valor=v, total=v, pct=v / tot if tot else 0) for k, v in sorted(m.items(), key=lambda x: -x[1])]


# ================================================================ Vendas Plasti
FERIADOS_NACIONAIS = {date.fromisoformat(d) for d in [
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21", "2026-05-01", "2026-06-04",
    "2026-09-07", "2026-10-12", "2026-11-02", "2026-11-15", "2026-11-20", "2026-12-25"]}


def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in FERIADOS_NACIONAIS


def dias_uteis_no_mes(ano: int, mes: int) -> int:
    return sum(1 for i in range(1, calendar.monthrange(ano, mes)[1] + 1) if eh_dia_util(date(ano, mes, i)))


def dias(de: date, ate: date):
    d = de
    while d <= ate:
        yield d
        d += timedelta(days=1)


def serie_plasti(pedidos, metas, de: date, ate: date, g: str):
    meta_mes: dict = defaultdict(float)
    for m in metas:
        meta_mes[(m.mes.year, m.mes.month)] += f(m.meta)
    b: dict = {}
    for d in dias(de, ate):
        k = chave_periodo(d, g)
        e = b.setdefault(k, [0.0, 0.0])
        if eh_dia_util(d):
            n = dias_uteis_no_mes(d.year, d.month)
            e[1] += meta_mes.get((d.year, d.month), 0) / n if n else 0
    for p in pedidos:
        k = chave_periodo(p.data_pedido, g)
        if k in b:
            b[k][0] += f(p.valor)
    chaves = sorted(b)
    acc = acc_meta = 0.0
    ac, am = [], []
    for c in chaves:
        acc += b[c][0]; acc_meta += b[c][1]
        ac.append(round(acc, 2)); am.append(round(acc_meta, 2))
    return dict(labels=[rotulo_periodo(c, g) for c in chaves], valor=[round(b[c][0], 2) for c in chaves],
                meta=[round(b[c][1], 2) for c in chaves], acumulado=ac, meta_acumulada=am)


def meses_no_intervalo(de: date, ate: date):
    y, m = de.year, de.month
    while (y, m) <= (ate.year, ate.month):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1
