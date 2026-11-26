// Chão de Fábrica - Produção — mesma tela do Lovable, calculada no navegador (o período vem da URL).
(() => {
  const { C, fmt, chave: chP, rotulo: rotP, esc, corta, semAcento, vazio, chev, panel, kpi, canvas, novo, destruir, grade, eixo, eixoX, bolinha, misturar, hachura, roscaTabela, tabela } = LV;
  const D0 = JSON.parse(document.getElementById("dados-producao").textContent);
  const L = D0.look, TODAS = LV.desempacotar(D0.rows);
  const c2 = v => fmt.num(v, 2, 2), n0 = v => fmt.num(v, 0), i1 = v => fmt.num(v, 2);
  const pctS = (a, b) => b > 0 ? `${fmt.num(a / b * 100, 2, 2)}%` : "";
  const U1 = (a, b) => b > 0 ? `${fmt.num(a / b * 100, 1, 1)}%` : "—";
  const K = v => fmt.num(v, v >= 100 ? 0 : 2);
  const X = C.chart, OK = "#00b050", CORTE = "#d86dcd", EXT_MP = "#0067b4", LOSS = C.loss;
  const ORDEM = ["Extrusão Carnevalli", "Extrusão Plastar", "Extrusão Gr", "Corte"];
  const ordenar = l => [...l].sort((a, b) => { const i = x => { const k = ORDEM.indexOf(x); return k < 0 ? ORDEM.length : k; }; return i(a) - i(b) || a.localeCompare(b); });
  const SETORES_FIXOS = ["Extrusão Plastar", "Extrusão Carnevalli", "Corte"];
  const hash = s => [...s].reduce((e, t) => (e * 31 + t.charCodeAt(0)) >>> 0, 0);
  const VAR = { "chart-extrusao-mp": "#0067b4", "chart-extrusao-mp-light": "#5fa8e0", "stack-ext-final-1": "#d9822b", "stack-ext-final-2": "#f2b872",
    "stack-corte-1": "#a83d99", "stack-corte-2": "#d86dcd", "stack-corte-3": "#edb3e6", "stack-corte-4": "#c25bb5", "stack-corte-5": "#f3cdee", "stack-blocadeira": "#934bc9",
    "chart-extrusao-mp-variant-1": "#3787c4", "chart-extrusao-mp-variant-2": "#7fbce8", "chart-extrusao-mp-variant-3": "#2483c9",
    "chart-turno-1": "#00b0f0", "chart-turno-2": "#ffc000", "chart-turno-3": "#00b050", "chart-turno-corte-1": "#e59edd", "chart-turno-corte-2": "#8d99ae" };
  const MAQ = { "Extrusão Plastar": { "EXT-001-93": "chart-extrusao-mp", "EXT-002-16": "chart-extrusao-mp-light" }, "Extrusão Carnevalli": { "EXT-003-25": "stack-ext-final-1", "EXT-004-25": "stack-ext-final-2" },
    Corte: { "SAC-001-21": "stack-corte-1", "SAC-002-26": "stack-corte-2", "BLO-001-14": "stack-blocadeira", "CSF-001-09": "stack-corte-4", "CSL-001-09": "stack-corte-5" } };
  const corMaquina = (setor, cod) => { const n = MAQ[setor]?.[cod]; if (n) return VAR[n]; const r = hash(cod);
    return setor === "Extrusão Plastar" ? VAR[`stack-ext-final-${r % 2 + 1}`] : setor === "Corte" ? VAR[`stack-corte-${r % 5 + 1}`] : VAR[`chart-extrusao-mp-variant-${r % 3 + 1}`]; };
  const TURNO = { "1ºTE": "chart-turno-1", "2ºTE": "chart-turno-2", "3ºTE": "chart-turno-3", "1ºTC": "chart-turno-corte-1", "2ºTC": "chart-turno-corte-2" };
  const corTurno = t => VAR[TURNO[t] ?? `chart-turno-${hash(t) % 3 + 1}`];
  const ordTurno = e => [+!!/TC/i.test(e), parseInt(e, 10) || 99, e];
  const cmpTurno = (a, b) => { const n = ordTurno(a), r = ordTurno(b); return n[0] - r[0] || n[1] - r[1] || n[2].localeCompare(r[2]); };
  const UTIL = [{ max: 20, label: "0–20%" }, { max: 50, label: "20–50%" }, { max: 70, label: "50–70%" }, { max: 80, label: "70–80%" }, { max: 100, label: "80–100%" }, { max: 120, label: "100–120%" }, { max: Infinity, label: ">120%" }]
    .map((e, i) => ({ ...e, cor: ["#808080", "#e03131", "#f08c00", "#ffd43b", "#2f9e44", "#1c7ed6", "#000000"][i] }));
  const faixa = e => { const t = Math.round(e * 100 * 100) / 100; return UTIL.findIndex(x => t <= x.max); };
  const corUtil = e => e == null ? C.muted : UTIL[faixa(e)]?.cor ?? "#000";

  // ---------- regras (portadas do Lovable)
  function tot(rs) { const t = { n: rs.length, ok: 0, apara: 0, alca: 0, borra: 0, perdas: 0, total: 0, milheiro: 0, parados: 0, horasDisp: 0, horasOk: 0, horasPerdas: 0, horasTrab: 0, util: null };
    for (const n of rs) { t.ok += n.ok; t.apara += n.apara; t.alca += n.alca; t.borra += n.borra; t.perdas += n.perdas; t.total += n.total; t.milheiro += n.qtd_milheiro ?? 0;
      if (n.total === 0) t.parados++; if (n.cap) { t.horasDisp += n.horasDisp ?? 0; t.horasOk += n.horasOk ?? 0; t.horasPerdas += n.horasPerdas ?? 0; t.horasTrab += n.horasTrab ?? 0; } }
    t.util = t.horasDisp ? t.horasTrab / t.horasDisp : null; return t; }
  function agrupar(rs, f) { const m = new Map(); for (const r of rs) { const k = f(r) || "(vazio)", i = m.get(k); i ? i.push(r) : m.set(k, [r]); } return [...m.entries()].map(([g, t]) => ({ grupo: g, ...tot(t) })); }
  const horasTurno = id => L.turnos.find(t => t.id === id)?.horas ?? null;
  function utilizacao(rs) { const m = new Map();
    for (const r of rs) { const cap = L.maquinas.find(x => x.id === r.maquina_id)?.cap; if (cap == null || +cap <= 0) continue; (m.get(r.maquina_id) ?? m.set(r.maquina_id, []).get(r.maquina_id)).push(r); }
    const lst = [...m.entries()].map(([id, n]) => { const cap = +L.maquinas.find(x => x.id === id).cap, tt = new Map(); for (const e of n) tt.set(`${e.data}|${e.turno_id}`, e.turno_id);
      let h = 0, sem = 0; for (const t of tt.values()) { const x = horasTurno(t); x == null ? sem++ : h += x; }
      const s = tot(n), disp = cap * h; return { maquina: n[0].maquina, capacidade: cap, turnos: tt.size, semHorario: sem, horas: h, disponivel: disp, total: s.total, ok: s.ok, util: disp ? s.total / disp : null, utilOk: disp ? s.ok / disp : null }; })
      .sort((a, b) => (b.util ?? -1) - (a.util ?? -1) || a.maquina.localeCompare(b.maquina));
    const d = lst.reduce((a, b) => a + b.disponivel, 0), t = lst.reduce((a, b) => a + b.total, 0);
    return { maquinas: lst, disponivel: d, total: t, util: d ? t / d : null, semHorario: lst.reduce((a, b) => a + b.semHorario, 0) }; }
  const porPeriodo = (rs, g) => g === "dia" ? rs : rs.map(e => ({ ...e, data: chP(e.data, g) }));
  function pivo(rs, dias, dim = "maquina", metr = "kg", rot) {
    if (metr === "horas") rs = rs.filter(e => e.cap != null && e.cap > 0);
    const nomes = [...new Set(rs.map(e => e[dim]))].sort(dim === "turno" ? cmpTurno : undefined);
    return { machines: nomes.map(n => { const i = rs.filter(e => e[dim] === n); return { name: n, code: dim === "turno" ? n : i[0]?.maquinaCodigo ?? "", total: tot(i), days: Object.fromEntries(dias.map(d => [d, tot(i.filter(t => t.data === d))])) }; }),
      total: tot(rs), days: dias.map(d => ({ day: d, name: rot(d), total: tot(rs.filter(e => e.data === d)) })) }; }
  function serieDias(p, perdas, media, metr) {
    const ch = metr === "horas" ? (perdas ? "horasPerdas" : "horasOk") : perdas ? "perdas" : "ok", geral = e => metr === "horas" ? e.horasOk + e.horasPerdas : e.total, chP2 = metr === "horas" ? "horasPerdas" : "perdas";
    const o = p.days.map(t => ({ day: t.day, name: t.name, totalKg: t.total[ch], totalGeral: geral(t.total), totalLoss: t.total[chP2], isAverage: false, dayCount: p.days.length,
      values: Object.fromEntries(p.machines.map(m => [m.name, m.days[t.day]?.[ch] ?? 0])), lossValues: Object.fromEntries(p.machines.map(m => [m.name, m.days[t.day]?.[chP2] ?? 0])),
      geralValues: Object.fromEntries(p.machines.map(m => [m.name, m.days[t.day] ? geral(m.days[t.day]) : 0])) }));
    if (!media || !o.length || !p.machines.length) return o; const s = o.length, med = k => Object.fromEntries(p.machines.map(m => [m.name, o.reduce((a, n) => a + (n[k][m.name] ?? 0), 0) / s]));
    return [...o, { day: "average", name: "Média/dia", isAverage: true, dayCount: s, totalKg: o.reduce((a, t) => a + t.totalKg, 0) / s, totalGeral: o.reduce((a, t) => a + t.totalGeral, 0) / s,
      totalLoss: o.reduce((a, t) => a + t.totalLoss, 0) / s, values: med("values"), lossValues: med("lossValues"), geralValues: med("geralValues") }]; }
  function gruposMaquinas(proc, setor, pred = () => true) { const m = new Map();
    for (const a of L.maquinas) { if (!a.ativo || !pred(a) || !a.setor || (proc !== "__all" && a.processo !== proc) || (setor !== "__all" && a.setor !== setor)) continue; (m.get(a.setor) ?? m.set(a.setor, []).get(a.setor)).push(a); }
    return ordenar([...m.keys()]).map(n => ({ name: n, machines: m.get(n).sort((a, b) => a.descricao.localeCompare(b.descricao)) })); }
  const daSelecao = (sel, gs) => { const ids = new Set(gs.flatMap(g => g.machines.map(m => m.id))); return sel.filter(i => ids.has(i)); };
  const alterna = (sel, ids) => ids.every(i => sel.includes(i)) ? sel.filter(i => !ids.includes(i)) : [...new Set([...sel, ...ids])];
  const porMaquinas = (rs, sel, vazioTudo = true) => { const s = new Set(sel); return s.size === 0 && vazioTudo ? rs : rs.filter(e => s.has(e.maquina_id)); };
  const serieOK = e => ({ name: e.grupo, OK: e.ok, Perdas: e.perdas, total: e.total, pctPerdas: e.total === 0 ? "" : `${fmt.num(e.perdas / e.total * 100, 1, 1)}%`, apara: e.apara, alca: e.alca, borra: e.borra });
  const kgPct = (e, t) => { const n = t === 0 ? "" : `${fmt.num(e / t * 100, 1, 1)}%`; return `${e === 0 ? "0" : c2(e)} kg${n ? ` (${n})` : ""}`; };
  // por produto (rosca)
  function porProduto(rs, f, g = e => e.produto) { const m = new Map();
    for (const i of rs) { const e = g(i) || "(vazio)", a = m.get(e) ?? new Map(), o = f(i); a.set(o, (a.get(o) ?? 0) + i.ok); m.set(e, a); }
    return [...m].map(([n, t]) => { const s = [...t].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]), r = s.reduce((a, [, v]) => a + v, 0);
      return { name: n, total: r, slices: s.map(([k, v]) => ({ name: k, value: v, percent: v / r * 100 })) }; }).filter(e => e.total > 0).sort((a, b) => b.total - a.total || a.name.localeCompare(b.name)); }
  const corPaleta = (e, lst) => { const n = lst.indexOf(e); return X[(n >= 0 ? n : hash(e)) % X.length]; };
  const MATERIAL = { AZUL: { fill: "#2563eb", label: "#ffffff" }, BRANCA: { fill: "#f8fafc", label: "#0f172a" }, LEITOSA: { fill: "#e7e2d3", label: "#0f172a" }, TRANSP: { fill: "#94a3b8", label: C.fg }, VERDE: { fill: "#16a34a", label: "#ffffff" } };
  function corLargura(e, lst) { const r = [...new Set(lst)].sort((a, b) => a - b).map(v => `${fmt.num(v, 2)} mm`), i = r.indexOf(e), a = hash(e), o = i >= 0 ? i : r.length + a, s = X[o % X.length], c = Math.floor(o / X.length);
    if (c === 0) return s; const l = i >= 0 ? Math.ceil(c / 2) : 1 + a % 1e4 / 1e3, u = 65 * l / (l + 4) / 100; return misturar(s, u, c % 2 ? 248 : 27); }

  // ---------- estado / filtros
  const st = { proc: "__all", setor: "__all", turno: "__all", cli: "__all", g: "mes", selPizza: [], selHoras: null };
  const app = document.getElementById("app");
  const campo = (rot, h) => `<div class="lv-campo"><span class="lbl">${rot}</span>${h}</div>`;
  const opt = (v, t, s) => `<option value="${esc(v)}" ${s ? "selected" : ""}>${esc(t)}</option>`;
  app.innerHTML = `<div class="lv-fgrid p7">${campo("De", `<input type="date" id="fDe" value="${D0.de}">`)}${campo("Até", `<input type="date" id="fAte" value="${D0.ate}">`)}
    ${campo("Processo", `<select id="fProc">${opt("__all", "Todos")}${opt("extrusao", "Extrusão")}${opt("corte", "Corte")}</select>`)}
    ${campo("Setor", `<select id="fSetor">${opt("__all", "Todos")}${L.setores.map(s => opt(s.nome, s.nome)).join("")}</select>`)}
    ${campo("Turno", `<select id="fTurno">${opt("__all", "Todos")}${L.turnos.map(t => opt(t.id, t.codigo)).join("")}</select>`)}
    ${campo("Cliente", `<select id="fCli">${opt("__all", "Todos")}${L.clientes.map(c => opt(c, c)).join("")}</select>`)}
    ${campo("Agrupar por", `<select id="fG">${[["dia", "Dia"], ["semana", "Semana"], ["mes", "Mês"], ["trimestre", "Trimestre"], ["ano", "Ano"]].map(([v, t]) => opt(v, t, v === "mes")).join("")}</select>`)}</div>
    <div id="corpo" class="lv-stack"></div>`;
  const recarregar = () => { const p = new URLSearchParams(location.search); p.set("de", document.getElementById("fDe").value); p.set("ate", document.getElementById("fAte").value); location.search = p.toString(); };
  document.getElementById("fDe").addEventListener("change", recarregar); document.getElementById("fAte").addEventListener("change", recarregar);
  [["fProc", "proc"], ["fSetor", "setor"], ["fTurno", "turno"], ["fCli", "cli"], ["fG", "g"]].forEach(([id, k]) => document.getElementById(id).addEventListener("change", e => { st[k] = e.target.value; render(); }));

  // ---------- gráfico por máquina/turno × dia
  function grafDias(id, setor, p, perdas, dim, metr) {
    const cor = t => dim === "turno" ? corTurno(t) : corMaquina(setor, t), dados = serieDias(p, perdas, true, metr);
    if (!p.machines.length) return;
    const horas = metr === "horas", topo = horas ? Math.max(24, ...dados.map(e => e.totalGeral)) * 1.15 : Math.max(1, ...dados.map(e => e.totalKg)) * 1.15;
    const ds = p.machines.map((m, i) => ({ label: m.name, data: dados.map(d => d.values[m.name] ?? 0), stack: "m", maxBarThickness: 64,
      backgroundColor: dados.map(d => d.isAverage ? misturar(cor(m.code), .3) : cor(m.code)), borderColor: dados.map(d => d.isAverage ? cor(m.code) : dim === "turno" ? "#fff" : "transparent"),
      borderWidth: dados.map(d => d.isAverage ? 1.5 : dim === "turno" ? 1 : 0),
      ...(!horas && i === p.machines.length - 1 ? { tamRotulo: 11, offRotulo: 6, corRotulo: () => perdas ? LOSS : C.fg, rotulo: j => perdas ? [`${K(dados[j].totalKg)} kg`, U1(dados[j].totalKg, dados[j].totalGeral)] : K(dados[j].totalKg) } : {}) }));
    if (horas) p.machines.forEach((m, i) => ds.push({ label: `Perdas ${m.name}`, data: dados.map(d => d.lossValues[m.name] ?? 0), stack: "m", maxBarThickness: 64,
      backgroundColor: dados.map(d => hachura(cor(m.code), "#d24c49", d.isAverage ? .7 : 1)), borderColor: dados.map(d => d.isAverage ? cor(m.code) : "#fff"), borderWidth: dados.map(d => d.isAverage ? 1.5 : 1),
      ...(i === p.machines.length - 1 ? { tamRotulo: 11, corRotulo: () => LOSS, rotulo: j => `${fmt.num(dados[j].totalLoss, 1, 1)} h` } : {}) }));
    const un = horas ? "h" : null, f = v => horas ? fmt.num(v, 1, 1) : c2(v);
    novo(id, { type: "bar", data: { labels: dados.map(d => d.name), datasets: ds },
      options: { interaction: { mode: "index", intersect: false }, layout: { padding: { top: perdas ? 38 : 26, right: 12, bottom: 8 } },
        plugins: { legend: horas ? { display: false } : { display: true }, lvRef: { linhas: [{ x: "Média/dia", inicio: true }, ...(horas ? [8, 16, 24].map(y => ({ y, alpha: .7, rot: `${y} h`, rotAbaixo: true })) : [])] },
          tooltip: { filter: c => !horas || c.datasetIndex < p.machines.length, itemSort: () => 0, callbacks: {
            title: it => { const d = dados[it[0].dataIndex]; return d.isAverage ? `Média/dia (${d.dayCount} dias)` : d.name; },
            beforeBody: () => horas ? ["OK"] : [],
            label: c => { const d = dados[c.dataIndex], m = p.machines[c.datasetIndex].name, u = horas ? "h" : d.isAverage ? "kg/dia" : "kg", v = d.values[m] ?? 0;
              return `${m}: ${f(v)} ${u}${perdas && !horas ? ` · ${U1(v, d.geralValues[m] ?? 0)}` : d.totalKg > 0 ? ` (${fmt.num(v / d.totalKg * 100, 1, 1)}%)` : ""}`; },
            labelColor: bolinha,
            footer: it => { const d = dados[it[0].dataIndex], u = horas ? "h" : d.isAverage ? "kg/dia" : "kg"; const l = [`${horas ? "Total OK" : "Total"}: ${f(d.totalKg)} ${u}${perdas && !horas ? ` · ${U1(d.totalKg, d.totalGeral)}` : ""}`];
              if (horas) { l.push("", "Perdas por turno"); p.machines.forEach(m => l.push(`${m.name}: ${f(d.lossValues[m.name] ?? 0)} h${d.totalLoss > 0 ? ` (${fmt.num((d.lossValues[m.name] ?? 0) / d.totalLoss * 100, 1, 1)}%)` : ""}`));
                l.push(`Total perdas: ${f(d.totalLoss)} h`, `Total geral: ${f(d.totalGeral)} h`, `% horas de perdas: ${d.totalGeral > 0 ? `${fmt.num(d.totalLoss / d.totalGeral * 100, 1, 1)}%` : "—"}`); }
              return l; } } } },
        scales: { x: { ...eixoX({ ticks: { autoSkip: true, maxRotation: 0, font: { size: 11 } } }), stacked: true },
          y: { stacked: true, min: 0, max: topo, grid: grade(), border: { color: C.muted }, afterFit: s => { s.width = 48; },
            ...(horas ? { afterBuildTicks: s => { s.ticks = Array.from({ length: Math.floor(topo / 8) + 1 }, (_, i) => ({ value: i * 8 })); } } : {}),
            ticks: { callback: v => fmt.num(v, horas ? 1 : 0), font: { size: 11 } } } } } });
  }
  function cardDias(setor, p, perdas, dim, metr, id) {
    const titulo = metr === "horas" ? `Horas ${perdas ? "Perdas TTL" : "Prod OK"} por turno × dia (h)` : `${perdas ? "Perdas" : "OK"} kg por ${dim === "turno" ? "turno" : "máquina"} × dia — ${setor}`;
    const leg = metr === "horas" && p.machines.length ? `<div class="lv-leg-c" style="color:var(--lv-fg)">${[false, true].flatMap(perd => p.machines.map((m, i) =>
      `<span><canvas width="14" height="10" data-hl="${perd ? 1 : 0}" data-cor="${corTurno(m.code)}"></canvas>${perd ? `Perdas ${esc(m.name)}` : esc(m.name)}</span>`)).join("")}</div>` : "";
    return panel(titulo, p.machines.length ? canvas(id, 320) + leg : `<div style="height:320px;display:flex;align-items:center;justify-content:center" class="lv-vazio">Sem dados no filtro</div>`);
  }
  // barras verticais OK/Perdas com % de perdas
  function grafOKPerdas(id, d) { if (!d.length) return;
    novo(id, { type: "bar", data: { labels: d.map(e => e.name), datasets: [{ label: "OK", data: d.map(e => e.OK), backgroundColor: OK, stack: "a" },
      { label: "Perdas", data: d.map(e => e.Perdas), backgroundColor: X[2], stack: "a", tamRotulo: 11, corRotulo: () => LOSS, rotulo: i => d[i].pctPerdas }] },
      options: { interaction: { mode: "index", intersect: false }, layout: { padding: { top: 24, right: 16 } }, plugins: { tooltip: tipOK(d) },
        scales: { x: { ...eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), stacked: true }, y: { ...eixo(n0), stacked: true, afterFit: s => { s.width = 50; } } } } }); }
  const tipOK = (d, comp) => ({ callbacks: { title: it => d[it[0].dataIndex].name, label: c => `${c.dataset.label}: ${kgPct(c.raw, d[c.dataIndex].total)}`, labelColor: bolinha,
    footer: comp ? (it => `Total perdas: ${kgPct(d[it[0].dataIndex].Perdas, d[it[0].dataIndex].total)}`) : undefined } });

  // seletor de máquinas (grupos por setor, busca, "Filtrando:" com chips)
  function seletorMaquinas(boxId, { grupos, sel, label, vazioTudo = true, onChange }) {
    const box = document.getElementById(boxId);
    const todas = grupos.flatMap(g => g.machines), escolhidas = todas.filter(m => sel.includes(m.id)), tudo = vazioTudo ? sel.length === 0 : todas.length > 0 && escolhidas.length === todas.length;
    const txt = tudo ? "Todas" : sel.length === 0 ? "Nenhuma" : sel.length === 1 ? escolhidas[0]?.descricao : `${sel.length} máquinas`;
    box.innerHTML = `<div style="display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px"><div class="lv-campo" style="width:min(320px,100%)"><span class="lbl">${label}</span>
      <details class="lv-pop" style="display:block"><summary class="lv-btn lg w-full" style="font-size:14px;font-weight:400"><span class="trunc">${esc(txt)}</span>${chev}</summary>
      <div class="lv-pop-c p0" style="width:384px"><input type="search" class="lv-busca" placeholder="Buscar nome ou código…" data-f><div class="lv-cmd lv-thin">
        <label><input type="checkbox" data-todas ${tudo ? "checked" : ""}>Todas</label>${vazioTudo ? "" : '<div class="todos" data-limpa>Limpar todas</div>'}
        ${grupos.map(g => { const n = g.machines.filter(m => sel.includes(m.id)).length;
          return `<div data-grupo><label style="font-size:12px;font-weight:500;color:var(--lv-muted-fg)"><input type="checkbox" data-g="${esc(g.name)}" ${n === g.machines.length ? "checked" : ""}>${esc(g.name)}</label>
          ${g.machines.map(m => `<label data-busca="${esc(semAcento(m.descricao + " " + m.codigo))}"><input type="checkbox" data-m="${m.id}" ${sel.includes(m.id) ? "checked" : ""}><span style="min-width:0"><span style="display:block;overflow-wrap:anywhere">${esc(m.descricao)}</span><span style="display:block;font-size:12px;color:var(--lv-muted-fg)">${esc(m.codigo)}</span></span></label>`).join("")}</div>`; }).join("")}
      </div></div></details></div>
      ${escolhidas.length ? `<div class="lv-chips"><span style="font-size:12px;color:var(--lv-muted-fg)">Filtrando:</span>${escolhidas.map(m => `<button class="lv-btn sec" data-tira="${m.id}">${esc(m.descricao)} ✕</button>`).join("")}<button class="lv-btn ghost" data-limpa2>Limpar</button></div>` : ""}</div>`;
    const reabrir = n => { const y = scrollY; onChange(n); const nd = document.getElementById(boxId)?.querySelector("details"); if (nd) nd.open = true; scrollTo(0, y); };
    box.querySelector("[data-todas]").addEventListener("change", () => reabrir(vazioTudo ? [] : todas.map(m => m.id)));
    box.querySelector("[data-limpa]")?.addEventListener("click", () => reabrir([]));
    box.querySelectorAll("[data-g]").forEach(c => c.addEventListener("change", () => reabrir(alterna(sel, grupos.find(g => g.name === c.dataset.g).machines.map(m => m.id)))));
    box.querySelectorAll("[data-m]").forEach(c => c.addEventListener("change", () => { const id = c.dataset.m; reabrir(sel.includes(id) ? sel.filter(x => x !== id) : [...sel, id]); }));
    box.querySelectorAll("[data-tira]").forEach(b => b.addEventListener("click", () => onChange(sel.filter(x => x !== b.dataset.tira))));
    box.querySelector("[data-limpa2]")?.addEventListener("click", () => onChange([]));
    box.querySelector("[data-f]").addEventListener("input", e => { const q = semAcento(e.target.value); box.querySelectorAll("[data-busca]").forEach(l => l.hidden = q && !l.dataset.busca.includes(q)); });
  }

  // ---------- desenho
  function render() {
    destruir();
    const corpo = document.getElementById("corpo"), g = st.g, rot = d => g === "dia" ? `${fmt.sem(d)} ${fmt.dia(d)}` : rotP(d, g);
    const j = TODAS.filter(e => (st.proc === "__all" || e.processo === st.proc) && (st.setor === "__all" || e.setor === st.setor) && (st.turno === "__all" || e.turno_id === st.turno) && (st.cli === "__all" || e.cliente === st.cli));
    const W = tot(j), Gu = utilizacao(j), Kp = porPeriodo(j, g), dias = [...new Set(Kp.map(e => e.data))].sort(), J = ordenar([...new Set(j.map(e => e.setor))]);
    const pivM = new Map(J.map(s => [s, pivo(Kp.filter(t => t.setor === s), dias, "maquina", "kg", rot)])), pivT = new Map(J.map(s => [s, pivo(Kp.filter(t => t.setor === s), dias, "turno", "kg", rot)]));
    const vazioP = pivo([], dias, "maquina", "kg", rot);
    const Ke = ordenar(L.setores.map(s => s.nome)), proc = new Map(L.setores.map(s => [s.nome, s.processo ?? ""])), ehCorte = s => (proc.get(s) || (s === "Corte" ? "corte" : "")) === "corte";
    const corSetor = s => s === "Extrusão Carnevalli" ? EXT_MP : ehCorte(s) ? CORTE : X[Ke.indexOf(s) % X.length] ?? X[0];
    const pm = agrupar(j, e => e.maquina).sort((a, b) => b.total - a.total).map(serieOK);
    const linhasSetor = dias.map(d => { const t = Kp.filter(x => x.data === d); return { name: rot(d), ...Object.fromEntries(J.map(s => [s, tot(t.filter(x => x.setor === s)).ok])) }; });
    const pt = agrupar(j, e => e.turno).sort((a, b) => a.grupo.localeCompare(b.grupo)).map(serieOK), pf = agrupar(j, e => e.familia).sort((a, b) => b.ok - a.ok).map(serieOK);
    const ps = agrupar(j, e => e.setor).sort((a, b) => J.indexOf(a.grupo) - J.indexOf(b.grupo)).map(serieOK), pc = agrupar(j, e => e.cliente).sort((a, b) => b.total - a.total).map(serieOK);
    const rkProd = agrupar(j.filter(e => e.total > 0), e => e.descricao).sort((a, b) => b.ok - a.ok).slice(0, 10);
    const opCli = op => { const m = (op ?? "").trim(); return m ? (TODAS.find(e => (e.op ?? "").trim() === m && e.cliente)?.cliente ?? "") : ""; };
    const rkOP = agrupar(j.filter(e => e.total > 0), e => e.op ?? "").sort((a, b) => b.ok - a.ok).slice(0, 10).map(t => ({ ...t, cliente: t.grupo !== "(vazio)" ? opCli(t.grupo) : "" }));
    document.getElementById("subtitulo").textContent = `${W.n} apontamento(s) no período`;
    let n = 0; const id = () => `g${++n}`;
    const blocosSetor = (dim) => SETORES_FIXOS.map(s => { const p = (dim === "turno" ? pivT : pivM).get(s) ?? vazioP, a = id(), b = id();
      return { html: `<div class="lv-g xl2">${cardDias(s, p, false, dim, "kg", a)}${cardDias(s, p, true, dim, "kg", b)}</div>`, draw: () => { grafDias(a, s, p, false, dim, "kg"); grafDias(b, s, p, true, dim, "kg"); } }; });
    const bM = blocosSetor("maquina"), bT = blocosSetor("turno");
    const ids = { pm: id(), ls: id(), pt: id(), pf: id(), pc: id(), comp: id(), ut: id() };
    corpo.innerHTML = `<div class="lv-kg g3 md7">${kpi("Produzido OK", c2(W.ok), { sub: "kg" })}${kpi("Perdas", c2(W.perdas), { tom: "loss", sub: "kg (apara + alça + borra)" })}
        ${kpi("% Perdas", pctS(W.perdas, W.total) || "—", { tom: "loss", sub: "sobre total geral" })}${kpi("Total geral", c2(W.total), { sub: "kg" })}
        ${kpi("Milheiros", i1(W.milheiro), { sub: "produzidos (corte)" })}${kpi("Máquinas paradas", String(W.parados), { sub: "apontamentos com 0 kg", tom: W.parados ? "danger" : "" })}
        ${kpi("Utilização da capacidade", Gu.util == null ? "—" : `${fmt.num(Gu.util * 100, 1, 1)}%`, { sub: "ponderada (máquinas com capacidade)" })}</div>
      ${bM.map(b => b.html).join("")}${bT.map(b => b.html).join("")}
      <div class="lv-g xl2">${panel("OK × perdas por máquina (kg e %)", pm.length ? canvas(ids.pm, Math.max(220, pm.length * 30)) : vazio())}
        ${panel("Produção OK por dia e setor (kg)", canvas(ids.ls, 280))}
        ${panel("Produção por turno (kg e %)", canvas(ids.pt, 240))}${panel("Produção por família (kg e %)", canvas(ids.pf, 240))}
        ${panel("Produção por cliente (kg e %)", canvas(ids.pc, 240), { classe: "span2" })}
        ${panel("Composição das perdas por setor (kg e %)", canvas(ids.comp, Math.max(180, ps.length * 45 + 60)), { classe: "span2" })}</div>
      ${Gu.maquinas.length ? panel("Utilização da capacidade por máquina", canvas(ids.ut, Math.max(140, Gu.maquinas.length * 40 + 40))
        + `<div class="lv-leg-c"><span style="font-weight:500">Escala de utilização:</span>${UTIL.map(u => `<span><i style="background:${u.cor}"></i>${u.label}</span>`).join("")}</div>`
        + (Gu.semHorario > 0 ? `<p style="margin:4px 0 0;font-size:12px;color:var(--lv-muted-fg)">${Gu.semHorario} turno(s) sem horário cadastrado não entram nas horas disponíveis.</p>` : "")) : ""}
      <div id="selHoras"></div><div id="horas"></div><div id="selPizza"></div><div id="pizzas" class="lv-stack"></div>
      <div class="lv-g xl2">${J.map(s => panel(`OK kg por máquina × dia — ${s}`, tabPivo(pivM.get(s), dias, rot, false)) + panel(`Perdas kg por máquina × dia — ${s}`, tabPivo(pivM.get(s), dias, rot, true))).join("")}</div>
      <div class="lv-g xl2">${panel("Ranking de produtos (top 10)", tabRank(rkProd, "Produto"))}${panel("Ranking por OP (top 10)", tabRank(rkOP, "OP", "Cliente"))}</div>`;
    [...bM, ...bT].forEach(b => b.draw());
    // OK × perdas por máquina
    if (pm.length) novo(ids.pm, { type: "bar", data: { labels: pm.map(e => e.name), datasets: [{ label: "OK", data: pm.map(e => e.OK), backgroundColor: OK, stack: "a" },
        { label: "Perdas", data: pm.map(e => e.Perdas), backgroundColor: X[2], stack: "a", tamRotulo: 11, corRotulo: () => LOSS, rotulo: i => pm[i].pctPerdas }] },
      options: { indexAxis: "y", interaction: { mode: "index", axis: "y", intersect: false }, layout: { padding: { left: 10, right: 64 } }, plugins: { tooltip: tipOK(pm) },
        scales: { x: { ...eixo(n0), stacked: true }, y: { stacked: true, afterFit: s => { s.width = 170; }, grid: grade(), border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 11 } } } } } });
    // linhas por setor
    novo(ids.ls, { type: "line", data: { labels: linhasSetor.map(e => e.name), datasets: J.map(s => ({ label: s, data: linhasSetor.map(e => e[s]), borderColor: corSetor(s), backgroundColor: corSetor(s), borderWidth: 2, pointRadius: 3, pointBackgroundColor: "#fff" })) },
      options: { interaction: { mode: "index", intersect: false }, plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c2(c.raw)} kg`, labelColor: bolinha } } },
        scales: { x: eixoX(), y: eixo(n0, { afterFit: s => { s.width = 50; } }) } } });
    grafOKPerdas(ids.pt, pt); grafOKPerdas(ids.pf, pf); grafOKPerdas(ids.pc, pc);
    if (ps.length) novo(ids.comp, { type: "bar", data: { labels: ps.map(e => e.name), datasets: [{ label: "Apara", data: ps.map(e => e.apara), backgroundColor: X[2], stack: "p" }, { label: "Alça", data: ps.map(e => e.alca), backgroundColor: X[1], stack: "p" },
        { label: "Borra", data: ps.map(e => e.borra), backgroundColor: X[4], stack: "p", tamRotulo: 11, corRotulo: () => LOSS, rotulo: i => ps[i].pctPerdas }] },
      options: { indexAxis: "y", interaction: { mode: "index", axis: "y", intersect: false }, layout: { padding: { right: 64 } }, plugins: { tooltip: tipOK(ps, true) },
        scales: { x: { ...eixo(n0), stacked: true }, y: { stacked: true, afterFit: s => { s.width = 110; }, grid: grade(), border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 11 } } } } } });
    // utilização
    if (Gu.maquinas.length) { const d = Gu.maquinas, mx = Math.max(100, Math.ceil(Math.max(...d.map(e => (e.util ?? 0) * 100)) / 10) * 10);
      novo(ids.ut, { type: "bar", data: { labels: d.map(e => e.maquina), datasets: [{ label: "Utilização", data: d.map(e => (e.util ?? 0) * 100), backgroundColor: d.map(e => corUtil(e.util)), rotulo: i => d[i].util == null ? "—" : `${fmt.num(d[i].util * 100, 1, 1)}%`, tamRotulo: 11 }] },
        options: { indexAxis: "y", layout: { padding: { left: 10, right: 56, top: 14 } }, plugins: { legend: { display: false }, lvRef: { linhas: [{ xv: 85, cor: "#25984d", rot: "85%" }] },
          tooltip: { callbacks: { title: it => d[it[0].dataIndex].maquina, label: c => { const e = d[c.dataIndex], pu = v => v == null ? "—" : `${fmt.num(v * 100, 1, 1)}%`;
            return [`Turnos: ${e.turnos}${e.semHorario ? ` (${e.semHorario} sem horário)` : ""} · ${fmt.num(e.horas, 1)} h`, `Capacidade: ${fmt.num(e.capacidade, 2)} kg/h · disponível ${c2(e.disponivel)} kg`,
              `Total: ${c2(e.total)} kg · OK: ${c2(e.ok)} kg`, `Utilização: ${pu(e.util)} · OK: ${pu(e.utilOk)}`]; } } } },
          scales: { x: { min: 0, max: mx, grid: grade(), border: { color: C.muted }, ticks: { callback: v => `${v}%` } }, y: { afterFit: s => { s.width = 170; }, grid: grade(), border: { color: C.muted }, ticks: { autoSkip: false } } } } }); }
    // horas (seletor de máquinas com capacidade; padrão: todas)
    const gV = gruposMaquinas(st.proc, st.setor, e => +e.cap > 0), todasV = gV.flatMap(g2 => g2.machines.map(m => m.id));
    const selH = daSelecao(st.selHoras ?? todasV, gV);
    seletorMaquinas("selHoras", { grupos: gV, sel: selH, label: "Máquina (gráficos de horas)", vazioTudo: false, onChange: s => { st.selHoras = s; render(); } });
    const jeH = porPeriodo(porMaquinas(j, selH, false), g), diasH = [...new Set(jeH.map(e => e.data))].sort(), pivH = pivo(jeH, diasH, "turno", "horas", rot), idH = id();
    document.getElementById("horas").innerHTML = cardDias("", pivH, false, "turno", "horas", idH);
    grafDias(idH, "", pivH, false, "turno", "horas");
    document.querySelectorAll("#horas canvas[data-hl]").forEach(cv => { const x = cv.getContext("2d"); x.fillStyle = cv.dataset.hl === "1" ? hachura(cv.dataset.cor, "#d24c49") : cv.dataset.cor; x.fillRect(0, 0, 14, 10); });
    // pizzas (seletor de máquinas; vazio = todas)
    const gL = gruposMaquinas(st.proc, st.setor), selP = daSelecao(st.selPizza, gL);
    seletorMaquinas("selPizza", { grupos: gL, sel: selP, label: "Máquina (gráficos de pizza)", onChange: s => { st.selPizza = s; render(); } });
    pizzas(porMaquinas(j, selP));
  }

  function pizzas(rs) {
    const box = document.getElementById("pizzas"), coresOrd = [...new Set(L.cores)].sort(), mp = new Map(coresOrd.map((e, i) => [e, X[i % X.length]]));
    const fv = v => fmt.num(v, 2);
    const secao = (titulo, prods, pres, colunas = 4) => { const rs2 = prods.map((p, i) => roscaTabela(`pz${titulo.length}_${i}`, p, { ...pres, fmtValor: fv }));
      return { html: `<section style="min-width:0"><h2 class="lv-h2" ${colunas === 2 ? 'style="min-height:48px"' : ""}>${esc(titulo)}</h2>${prods.length ? `<div class="lv-g ${colunas === 2 ? "md2" : "md2 xl4"}">${rs2.map(r => r.html).join("")}</div>` : '<p style="font-size:14px;color:var(--lv-muted-fg)">Sem produção OK no período selecionado.</p>'}</section>`, draw: () => rs2.forEach(r => r.desenhar()) }; };
    const porCor = porProduto(rs, e => e.cor || "(vazio)");
    const a = porCor.length ? secao("Produção por cor em cada produto", porCor, { coluna: "Cor", subtitulo: "OK kg por cor", unidade: "kg OK", outline: "#64748b",
      colorFor: e => { const k = e.trim().toUpperCase(); return { ...(MATERIAL[k] ?? { fill: mp.get(e) ?? corPaleta(e, []), label: C.fg }), hatch: k === "TRANSP", halo: k === "TRANSP" }; } }) : { html: "", draw: () => {} };
    const bob = porProduto(rs.filter(e => e.produto === "Bobina"), e => e.largura_mm == null ? "(sem largura)" : `${fmt.num(e.largura_mm, 2)} mm`, e => e.familia);
    const tipo = porProduto(rs.filter(e => e.produto === "Sacola" || e.produto === "Saco"), e => (e.tipo || "").trim() || "(sem tipo)");
    const b = bob.length ? secao("Bobina — produção por largura em cada família", bob, { coluna: "Largura", subtitulo: "Bobina · OK kg por largura", unidade: "kg OK", colorFor: e => ({ fill: corLargura(e, L.larguras), label: C.fg, halo: true }) }, 2) : null;
    const t = tipo.length ? secao("Produção por tipo de sacola", tipo, { coluna: "Tipo", subtitulo: "OK kg por tipo de sacola", unidade: "kg OK", colorFor: e => ({ fill: corPaleta(e, L.tipos), label: C.fg, halo: true }) }, 2) : null;
    box.innerHTML = a.html + (b || t ? `<div class="lv-g ${b && t ? "xl2" : ""}" style="align-items:start">${b ? b.html : ""}${t ? t.html : ""}</div>` : "");
    a.draw(); b?.draw(); t?.draw();
  }
  function tabPivo(p, dias, rot, perdas) {
    if (!p || !p.machines.length) return '<p style="font-size:14px;color:var(--lv-muted-fg)">Sem dados.</p>';
    const ch = perdas ? "perdas" : "ok", fTot = e => perdas ? kgPct(e.perdas, e.total).replace(" kg", "") : c2(e.ok);
    return tabela([{ t: "Máquina" }, ...dias.map(d => ({ t: esc(rot(d)), r: 1 })), { t: "Total", r: 1 }],
      p.machines.map(m => `<tr><td>${esc(m.name)}</td>${dias.map(d => { const v = m.days[d]?.[ch] ?? 0; return `<td class="r ${v === 0 ? "mut" : perdas ? "los" : ""}">${c2(v)}${perdas && v > 0 ? `<span style="margin-left:4px;font-size:10px;opacity:.8">(${U1(v, m.days[d]?.total ?? 0)})</span>` : ""}</td>`; }).join("")}<td class="r ${perdas ? "los" : ""}" style="font-weight:600">${fTot(m.total)}</td></tr>`),
      { maxH: "360px", total: `<tr class="tot"><td>Total</td>${p.days.map(d => `<td class="r ${perdas ? "los" : ""}">${c2(d.total[ch])}${perdas && d.total.perdas > 0 ? `<span style="margin-left:4px;font-size:10px;opacity:.8">(${U1(d.total.perdas, d.total.total)})</span>` : ""}</td>`).join("")}<td class="r ${perdas ? "los" : ""}">${fTot(p.total)}</td></tr>` });
  }
  function tabRank(d, rot, extra) {
    if (!d.length) return '<p style="font-size:14px;color:var(--lv-muted-fg)">Sem dados.</p>';
    return tabela([{ t: "#" }, { t: rot }, ...(extra ? [{ t: extra }] : []), { t: "OK kg", r: 1 }, { t: "Total kg", r: 1 }, { t: "%Perdas", r: 1 }],
      d.map((e, i) => `<tr><td class="num">${i + 1}</td><td>${esc(e.grupo)}</td>${extra ? `<td>${esc(e.cliente)}</td>` : ""}<td class="r">${c2(e.ok)}</td><td class="r">${c2(e.total)}</td><td class="r">${pctS(e.perdas, e.total)}</td></tr>`), { maxH: "360px" });
  }

  render();
})();
