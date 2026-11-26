"""Dados da tela Entradas e Saídas base Omie (Financeiro → Visão geral), iguais às fórmulas do Lovable (src/lib/fluxo-caixa.ts)."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from . import calculos as C

f = C.f
LIMITE_DIARIO = 62
VERDE, VERMELHO = "#00b050", "#dc2626"
CORES_GASTO = [("pessoal", "#e11d48"), ("administrativ", "#f08c00"), ("diretas", "#13606e"), ("vendas", "#2f9e44"),
               ("marketing", "#2f9e44"), ("financeir", "#64748b"), ("banco", "#64748b"), ("imposto", "#7c3aed"),
               ("taxa", "#7c3aed"), ("investimento", "#0ea5e9"), ("outr", "#808000")]
CAT = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
CINZA = "#7a8794"


def cor_grupo(nome):
    n = C.sem_acento(nome or "").lower()
    return next((c for k, c in CORES_GASTO if k in n), CINZA)


def cor_situacao(s):
    t = (s or "").strip().lower()
    if "parcial" in t:
        return "#94d82d"
    if t.startswith(("pago", "recebido", "conciliado")):
        return "#2f9e44"
    if t.startswith("vence hoje"):
        return "#ffd43b" if "boleto" in t else "#f59f00"
    if t.startswith("a vencer"):
        return "#74c0fc" if "boleto" in t else "#1c7ed6"
    if t.startswith("atrasado"):
        return "#ff8787" if "boleto" in t else "#e03131"
    return CINZA


def quitado(s):
    return (s or "").strip() in ("Pago", "Recebido")


def _soma(m, r):
    pg = f(r.valor_pago)
    if pg > 0:
        m[0] += pg
    else:
        m[1] += -pg


def _acumular(chaves, m, rotulo):
    ae = ag = 0.0
    out = []
    for k in chaves:
        e, g = m[k]
        ae += e
        ag += g
        out.append(dict(chave=k, label=rotulo(k), entradas=round(e, 2), gastos=round(g, 2), saldo=round(e - g, 2),
                        entradasAcum=round(ae, 2), gastosAcum=round(ag, 2), saldoAcum=round(ae - ag, 2)))
    return out


def serie_periodo(rows, de, ate):
    """Período escolhido: até 62 dias → todos os dias; senão mês a mês (só os meses do intervalo). Acumulados começam em `de`."""
    diario = (ate - de).days + 1 <= LIMITE_DIARIO
    m = {}
    d = de
    while d <= ate:
        m.setdefault(d.isoformat() if diario else d.strftime("%Y-%m"), [0.0, 0.0])
        d += timedelta(days=1)
    for r in rows:
        dr = C.data_ref(r)
        if de <= dr <= ate:
            _soma(m[dr.isoformat() if diario else dr.strftime("%Y-%m")], r)
    return ("dia" if diario else "mes"), _acumular(sorted(m), m, (lambda k: f"{k[8:10]}/{k[5:7]}") if diario else C.rotulo_mes)


def serie_granularidade(rows, g, mes=None):
    """Sem período: agrupa por dia/semana/mês/trimestre/ano; em "dia" mostra todos os dias do `mes`."""
    m = {}
    if g == "dia" and mes:
        a, mm = int(mes[:4]), int(mes[5:7])
        for i in range(1, calendar.monthrange(a, mm)[1] + 1):
            m[f"{mes}-{i:02d}"] = [0.0, 0.0]
        rows = [r for r in rows if C.data_ref(r).strftime("%Y-%m") == mes]
    for r in rows:
        _soma(m.setdefault(C.chave_periodo(C.data_ref(r), g), [0.0, 0.0]), r)
    return _acumular(sorted(m), m, lambda k: C.rotulo_periodo(k, g))


def ranking(rows, chave, sinal):
    m = defaultdict(float)
    qtd = defaultdict(int)
    for r in rows:
        pg = f(r.valor_pago)
        if (sinal == 1 and pg <= 0) or (sinal == -1 and pg >= 0):
            continue
        k = chave(r) or "(sem)"
        m[k] += abs(pg)
        qtd[k] += 1
    tot = sum(m.values())
    return [dict(nome=k, valor=round(v, 2), pct=v / tot if tot else 0, qtd=qtd[k]) for k, v in sorted(m.items(), key=lambda x: -x[1])]


def gastos_por_periodo(rows, chave, top, g):
    principais = [x["nome"] for x in ranking(rows, chave, -1)[:top]]
    m = defaultdict(lambda: defaultdict(float))
    for r in rows:
        pg = f(r.valor_pago)
        if pg >= 0:
            continue
        k = chave(r)
        m[C.chave_periodo(C.data_ref(r), g)][k if k in principais else "Outros"] += -pg
    series = principais + (["Outros"] if any(o.get("Outros") for o in m.values()) else [])
    chaves = sorted(m)
    return dict(chaves=chaves, labels=[C.rotulo_periodo(k, g) for k in chaves], series=series,
                valores={s: [round(m[k].get(s, 0), 2) for k in chaves] for s in series},
                totais=[round(sum(m[k].values()), 2) for k in chaves])


def por_situacao_tipo(rows):
    def agrupa(tipo):
        m = defaultdict(lambda: [0.0, 0])
        for r in rows:
            if (r.tipo or "").strip() != tipo:
                continue
            m[r.situacao][0] += abs(f(r.valor_conta))
            m[r.situacao][1] += 1
        tot = sum(v for v, _ in m.values())
        fatias = sorted(({"situacao": s, "valor": round(v, 2), "qtd": q, "pct": v / tot if tot else 0, "cor": cor_situacao(s)}
                         for s, (v, q) in m.items()), key=lambda x: -x["valor"])
        return dict(total=round(tot, 2), fatias=fatias)
    return dict(receber=agrupa(C.TIPO_RECEBER), pagar=agrupa(C.TIPO_PAGAR))


def por_situacao(rows):
    m = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        s = m[r.situacao]
        s[0] += 1
        v = f(r.valor_conta)
        if v > 0:
            s[1] += v
        else:
            s[2] += -v
    return sorted(((k, *v) for k, v in m.items()), key=lambda x: -x[1])


def aberto_por_data(rows, modo, status=None, de=None, ate=None):
    """Contas em aberto (situação ≠ Pago/Recebido) por data de emissão e situação. Em "ambos", a pagar fica negativo."""
    dias = defaultdict(lambda: defaultdict(float))
    series = {}
    det = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0])))
    total = 0.0
    qtd = 0
    for r in rows:
        if quitado(r.situacao):
            continue
        tipo = (r.tipo or "").strip()
        rec, pag = tipo == C.TIPO_RECEBER, tipo == C.TIPO_PAGAR
        if not (rec if modo == "receber" else pag if modo == "pagar" else rec or pag):
            continue
        v = max(0.0, abs(f(r.valor_conta)) - abs(f(r.valor_pago)))
        if v <= 0:
            continue
        sit = (r.situacao or "").strip()
        if status and sit not in status:
            continue
        if (de and r.data_emissao < de) or (ate and r.data_emissao > ate):
            continue
        sinal = -1 if modo == "ambos" and pag else 1
        k = f"{'R' if rec else 'P'}|{sit}" if modo == "ambos" else sit
        series.setdefault(k, dict(key=k, situacao=sit, sinal=sinal, rotulo=(f"{'Receber' if rec else 'Pagar'} · {sit}" if modo == "ambos" else sit),
                                  cor=cor_situacao(sit)))
        dia = r.data_emissao.isoformat()
        dias[dia][k] += sinal * v
        it = det[dia][k][(r.fornecedor or "").strip() or "—"]
        it[0] += sinal * v
        it[1] += 1
        total += sinal * v
        qtd += 1
    chaves = sorted(dias)
    ser = sorted(series.values(), key=lambda s: (-s["sinal"], s["situacao"]))
    detalhe = {d: {k: sorted(([n, round(v, 2), q] for n, (v, q) in m.items()), key=lambda x: -abs(x[1]))[:8]
                   for k, m in det[d].items()} for d in chaves}
    return dict(dias=chaves, series=[dict(s, valores=[round(dias[d].get(s["key"], 0), 2) for d in chaves]) for s in ser],
                totais=[round(sum(dias[d].values()), 2) for d in chaves], total=round(total, 2), qtd=qtd, detalhe=detalhe)


def entradas_grupo_categoria(rows):
    m = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    total = 0.0
    for r in rows:
        pg = f(r.valor_pago)
        if pg <= 0:
            continue
        a = m[r.grupo or "(sem)"][r.categoria or "(sem)"]
        a[0] += pg
        a[1] += 1
        total += pg
    grupos = []
    for g, cats in m.items():
        v = sum(c[0] for c in cats.values())
        grupos.append(dict(nome=g, valor=round(v, 2), pct=v / total if total else 0, qtd=sum(c[1] for c in cats.values()),
                           categorias=sorted(({"nome": n, "valor": round(c[0], 2), "qtd": c[1], "pctTotal": c[0] / total if total else 0,
                                               "pctGrupo": c[0] / v if v else 0} for n, c in cats.items()), key=lambda x: -x["valor"])))
    return dict(total=round(total, 2), grupos=sorted(grupos, key=lambda x: -x["valor"]))


def em_aberto(todas):
    return [s for s in todas if not quitado(s)]


def realizadas(todas):
    return [s for s in todas if C.is_realizado(s)]
