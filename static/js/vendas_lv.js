// Faturamento base Omie — mesma tela do Lovable (filtros, KPIs com comparação, ~25 gráficos e tabelas), calculada no navegador.
(() => {
  const { C, fmt, chave: chP, rotulo: rotP, esc, corta, semAcento, vazio, chev, panel, kpi, canvas, novo, destruir, grade, eixo, eixoX, bolinha, misturar, multi, rank, roscaTabela, tabela, excel } = LV;
  const H = fmt.brl, Z = fmt.curto, P = fmt.pct, N0 = v => v == null ? "" : fmt.num(v, 0);
  const TODAS = LV.desempacotar(JSON.parse(document.getElementById("dados-vendas").textContent))
    .map((r, i) => ({ ...r, id: i, total: Number(r.total) || 0 }));

  // ---------- cores (iguais às variáveis CSS do Lovable)
  const COR_LINHA = { Sacola: "#2563eb", "Saco de lixo": "#2f9e44", "Outros sacos": "#868e96", Bobina: "#d98a2e", Masterbatch: "#7048e8", "Resinas e compostos": "#c2255c", "Não recorrente": "#d24c49" };
  const Q = l => COR_LINHA[l] ?? C.muted;
  const MAP_COR = { AZUL: "blue", LEITOSA: "milky", BRANCA: "white", PRETO: "black", "PRETO REFORÇADO": "black", VERDE: "green", "REFORÇADO": "reinforced" };
  const SALES_COR = { blue: "#1c7ed6", milky: "#e9ecef", white: "#ffffff", black: "#212529", green: "#2f9e44", reinforced: "#868e96", unknown: "#ced4da" };
  const OUTLINE = "#868e96";
  const corDe = n => SALES_COR[MAP_COR[String(n).toUpperCase()] ?? "unknown"];
  const corPadrao = n => { const k = MAP_COR[String(n).toUpperCase()] ?? "unknown"; return { fill: SALES_COR[k], label: ["milky", "white", "unknown"].includes(k) ? "#0f172a" : "#ffffff", hatch: !MAP_COR[String(n).toUpperCase()] }; };
  const DOC = { "Nota Fiscal": "#1971c2", Recibo: "#e8590c" }, GEO = { Manaus: "#2b8a3e", Interior: "#a07c1e" };
  const CLI_ATIVOS = "#948a54", VENDEDOR = "#0c8599", TOTAL_RSKG = "#000000";
  const PROD = ["#2563eb", "#e8590c", "#2f9e44", "#c2255c", "#7048e8", "#0c8599", "#d4a20b", "#a0522d"];
  const corProd = i => i < 8 ? PROD[i] : `hsl(${i * 47 % 360} 65% 50%)`;
  const corCli = i => i < 5 ? C.chart[i] : `hsl(${i * 47 % 360} 62% 45%)`;
  const corVend = i => [...C.chart, "#d98a2e", "#2f9e44"][i] ?? `hsl(${i * 47 % 360} 62% 48%)`;
  const UF_COR = ["#d98a2e", "#2563eb", "#dc2626", "#948a54", "#934bc9", "#868e96"];

  // ---------- regras (portadas do Lovable)
  const S = e => String(e ?? "").trim().replace(/\s+/g, " ");
  const codigo = p => { const t = p.indexOf(" - "); return (t >= 0 ? p.slice(0, t) : p).trim(); };
  const ehKg = l => ["sacola", "bobina"].includes(String(l).trim().toLowerCase());
  const familia = e => S(e.familia) || codigo(e.produto);
  const descr = e => S(e.descricao) || e.produto.split(" - ").slice(1).join(" - ") || e.produto;
  const grupoT = e => { const t = S(e); return !t || /planejamento de vendas/i.test(t) ? null : t.replace(/(\d)([a-zA-Z])/g, "$1 $2"); };
  const grupoK = e => S(e.grupo) || "(sem grupo)", corK = e => S(e.cor) || "(sem cor)";
  const buscaProd = (e, t) => [e.produto, familia(e), descr(e)].some(x => x.toLocaleLowerCase("pt-BR").includes(t.toLocaleLowerCase("pt-BR")));
  const prodSimpl = e => { const t = S(e.produto_simplificado); if (t) return t.replace(/(\d)([a-zA-Z])/g, "$1 $2");
    const n = grupoT(e.grupo), r = S(e.cor); return n || r ? [S(e.linha), n, r].filter(Boolean).join(" - ") : familia(e); };
  const vendK = e => S(e.vendedor) || "(sem vendedor)", cidK = e => S(e.cidade) || "(sem cidade)", ufK = e => S(e.estado).toUpperCase() || "(sem UF)";
  const bairroK = e => S(e.bairro) || "(sem bairro)", manaus = e => semAcento(S(e.cidade)) === "manaus", docK = e => /recibo/i.test(S(e.tipo_documento)) ? "Recibo" : "Nota Fiscal";
  const meses = rs => [...new Set(rs.map(e => chP(e.data, "mes")))].sort();
  function totais(rs) { let t = 0, kg = 0, fk = 0; const cli = new Set(), pr = new Set();
    for (const o of rs) { const v = o.total; t += v; cli.add(o.cliente); pr.add(codigo(o.produto)); if (ehKg(o.linha) && o.kg != null) { kg += +o.kg; fk += v; } }
    return { faturamento: t, kg, rsKg: kg ? fk / kg : null, clientes: cli.size, produtos: pr.size, itens: rs.length, ticket: cli.size ? t / cli.size : null }; }
  function porPeriodo(rs, g) { const m = new Map();
    for (const r of rs) { const k = chP(r.data, g); let i = m.get(k); if (!i) m.set(k, i = { total: 0, linhas: {}, cli: new Set(), sacKg: 0, sacR: 0, kgL: {}, fatL: {} });
      const a = r.total; i.total += a; i.linhas[r.linha] = (i.linhas[r.linha] ?? 0) + a; i.cli.add(r.cliente);
      const o = r.linha.trim().toLowerCase(); if (ehKg(o) && r.kg != null && +r.kg !== 0) { i.sacKg += +r.kg; i.sacR += a; i.kgL[o] = (i.kgL[o] ?? 0) + +r.kg; i.fatL[o] = (i.fatL[o] ?? 0) + a; } }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, n]) => ({ chave: k, label: rotP(k, g), total: n.total, clientes: n.cli.size,
      rsKgSacolaBobina: n.sacKg ? n.sacR / n.sacKg : null, linhas: n.linhas, rsKgSacola: n.kgL.sacola ? (n.fatL.sacola ?? 0) / n.kgL.sacola : null,
      rsKgBobina: n.kgL.bobina ? (n.fatL.bobina ?? 0) / n.kgL.bobina : null })); }
  const NOME_G = { dia: ["dia", "dias"], semana: ["semana", "semanas"], mes: ["mês", "meses"], trimestre: ["trimestre", "trimestres"], ano: ["ano", "anos"] };
  const rotMedia = g => g === "mes" ? "Média/Ano" : `Média/${NOME_G[g][0]}`;
  const tituloMedia = (g, n) => `Média por ${NOME_G[g][0]} (${n} ${NOME_G[g][n === 1 ? 0 : 1]})`;
  function comMedia(s, g) { if (!s.length) return s; const n = s.length, ls = [...new Set(s.flatMap(p => Object.keys(p.linhas)))];
    return [...s, { chave: "__media__", label: rotMedia(g), total: s.reduce((a, p) => a + p.total, 0) / n, isMedia: true, nPeriodos: n,
      linhas: Object.fromEntries(ls.map(l => [l, s.reduce((a, p) => a + (p.linhas[l] || 0), 0) / n])) }]; }
  function rsKgProduto(rs, g, prods) { const ix = new Map(prods.map((p, i) => [p, i])), m = new Map();
    for (const a of rs) { if (!ehKg(a.linha) || a.kg == null || +a.kg === 0) continue; const k = chP(a.data, g); let o = m.get(k);
      if (!o) m.set(k, o = { kg: 0, fat: 0, pk: prods.map(() => 0), pf: prods.map(() => 0) });
      const s = a.total, c = +a.kg; o.kg += c; o.fat += s; const l = ix.get(prodSimpl(a)); if (l != null) { o.pk[l] += c; o.pf[l] += s; } }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, n]) => ({ chave: k, label: rotP(k, g), total: n.kg ? n.fat / n.kg : null, valores: n.pk.map((e, i) => e ? n.pf[i] / e : null) })); }
  const produtosKg = rs => ranking(rs.filter(e => ehKg(e.linha) && e.kg != null && +e.kg !== 0), prodSimpl).map(e => e.nome);
  function evolCliente(rs, cs) { const ms = meses(rs), ix = new Map(ms.map((m, i) => [m, i])), nomes = cs.length ? cs : ["Total"], ic = new Map(nomes.map((n, i) => [n, i]));
    const v = nomes.map(() => ms.map(() => 0));
    for (const r of rs) { const e = ix.get(chP(r.data, "mes")); if (e == null) continue; const i = cs.length ? ic.get(r.cliente) : 0; if (i != null) v[i][e] += r.total; }
    return { meses: ms.map(k => ({ chave: k, label: rotP(k, "mes") })), series: nomes.map((n, i) => ({ nome: n, valores: v[i] })) }; }
  function ranking(rs, f) { const tot = rs.reduce((a, r) => a + r.total, 0), m = new Map();
    for (const r of rs) { const k = f(r); let i = m.get(k); if (!i) m.set(k, i = { total: 0, kg: 0, compras: 0, dias: new Set(), ultima: "" });
      i.total += r.total; i.kg += +r.kg || 0; i.compras++; i.dias.add(r.data); if (r.data > i.ultima) i.ultima = r.data; }
    return [...m.entries()].map(([n, t]) => ({ nome: n, total: t.total, kg: t.kg, pct: tot ? t.total / tot : 0, compras: t.compras, dias: t.dias.size, ultima: t.ultima })).sort((a, b) => b.total - a.total); }
  const cores = rs => ranking(rs, corK);
  function grupos(rs) { const m = new Map(); for (const r of rs) { const k = grupoK(r), o = m.get(k) ?? {}; o[r.linha] = (o[r.linha] ?? 0) + r.total; m.set(k, o); }
    return ranking(rs, grupoK).map(e => ({ ...e, linhas: m.get(e.nome) ?? {} })); }
  function linhasCores(rs) { const t = new Set(rs.filter(e => S(e.cor)).map(e => e.linha)); return ranking(rs, e => e.linha).filter(e => t.has(e.nome)).map(l => ({ ...l, cores: cores(rs.filter(e => e.linha === l.nome)) })); }
  function produtos(rs) { const m = new Map(); for (const r of rs) { const k = prodSimpl(r), o = m.get(k) ?? new Map(); o.set(r.linha, (o.get(r.linha) ?? 0) + r.total); m.set(k, o); }
    return ranking(rs, prodSimpl).map(e => { const n = m.get(e.nome); return { ...e, linha: n ? [...n.entries()].sort((a, b) => b[1] - a[1])[0][0] : "" }; }); }
  function anterior(ini, fim) { const d = s => Date.UTC(+s.slice(0, 4), s.slice(5, 7) - 1, +s.slice(8, 10)), n = Math.round((d(fim) - d(ini)) / 864e5) + 1;
    return { ini: new Date(d(ini) - n * 864e5).toISOString().slice(0, 10), fim: new Date(d(ini) - 864e5).toISOString().slice(0, 10) }; }
  const variacao = (a, b) => a == null || b == null || !b ? null : (a - b) / b;
  function serieChave(rs, g, f, cats) { const set = cats ? new Set(cats) : null, m = new Map();
    for (const o of rs) { const k = chP(o.data, g), s = f(o); let c = m.get(k); if (!c) { c = {}; m.set(k, c); for (const x of cats ?? []) c[x] = 0; }
      if (set && !set.has(s)) continue; c[s] = (c[s] ?? 0) + o.total; }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => ({ chave: k, label: rotP(k, g), total: Object.values(v).reduce((a, b) => a + b, 0), v })); }
  function vendedores(rs) { const m = new Map(); rs.forEach((e, n) => { const k = vendK(e), i = m.get(k) ?? { cli: new Set(), ped: new Set() }; i.cli.add(e.cliente); i.ped.add(S(e.orcamento) || `__item${n}`); m.set(k, i); });
    return ranking(rs, vendK).map(e => { const n = m.get(e.nome); return { ...e, clientes: n.cli.size, pedidos: n.ped.size, ticketPedido: n.ped.size ? e.total / n.ped.size : null }; }); }
  function comClientes(rs, f) { const m = new Map(); for (const r of rs) { const k = f(r); (m.get(k) ?? m.set(k, new Set()).get(k)).add(r.cliente); } return ranking(rs, f).map(e => ({ ...e, clientes: m.get(e.nome)?.size ?? 0 })); }
  function topN(e, t, n = "Outras") { if (e.length <= t) return e; const r = e.slice(t); return [...e.slice(0, t), { nome: n, total: r.reduce((a, b) => a + b.total, 0), kg: r.reduce((a, b) => a + b.kg, 0), pct: r.reduce((a, b) => a + b.pct, 0), compras: 0, dias: 0, ultima: "" }]; }
  function estados(rs) { const m = new Map(); rs.forEach((e, n) => { const k = ufK(e); let i = m.get(k); if (!i) m.set(k, i = { cli: new Set(), ped: new Set(), cid: new Set(), rs: 0, kg: 0, linhas: {} });
      i.cli.add(e.cliente); i.ped.add(S(e.orcamento) || `__item${n}`); i.cid.add(cidK(e)); i.linhas[e.linha] = (i.linhas[e.linha] ?? 0) + e.total;
      if (ehKg(e.linha) && e.kg != null && +e.kg !== 0) { i.rs += e.total; i.kg += +e.kg; } });
    return ranking(rs, ufK).map(e => { const n = m.get(e.nome); return { ...e, clientes: n.cli.size, pedidos: n.ped.size, ticketPedido: n.ped.size ? e.total / n.ped.size : null, rsKg: n.kg ? n.rs / n.kg : null, cidades: n.cid.size, linhas: n.linhas }; }); }
  function categoriasUF(es, t = 6) { const n = es.map(e => e.nome).filter(e => e !== "AM"), r = n.slice(0, n.length > t ? t : n.length), set = new Set(r), mais = n.length > t;
    return { categorias: [...(es.some(e => e.nome === "AM") ? ["AM"] : []), ...r, ...(mais ? ["Outras UFs"] : [])], chave: e => { const k = ufK(e); return k === "AM" || set.has(k) ? k : "Outras UFs"; } }; }
  function matriz(rs) { const t = ranking(rs, vendK), ls = ranking(rs, e => e.linha).map(e => e.nome), m = new Map();
    for (const r of rs) { const k = vendK(r), o = m.get(k) ?? {}; o[r.linha] = (o[r.linha] ?? 0) + r.total; m.set(k, o); }
    return { linhas: ls, linhasMatriz: t.map(e => ({ nome: e.nome, total: e.total, valores: m.get(e.nome) ?? {} })) }; }

  // ---------- estado e filtros
  const ultima = TODAS.length ? TODAS[TODAS.length - 1].data : new Date().toISOString().slice(0, 10);
  const st = { de: `${ultima.slice(0, 4)}-01-01`, ate: ultima, linhas: [], grupos: [], cores: [], vend: [], cid: [], uf: [], doc: "", cli: "", prod: "", g: "mes",
    mesesSel: null, prodSel: null, prodMexeu: false, cliEvo: [], vendSel: null };
  const ordemLinhas = Object.keys(COR_LINHA);
  const opLinhas = [...new Set(TODAS.map(e => e.linha))].sort((a, b) => { const i = x => { const k = ordemLinhas.indexOf(x); return k < 0 ? ordemLinhas.length : k; }; return i(a) - i(b) || a.localeCompare(b, "pt-BR"); });
  const opGrupos = [...new Set(TODAS.map(grupoK))].sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }));
  const opCores = [...new Set(TODAS.map(corK))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  const opVend = ranking(TODAS, vendK).map(e => e.nome), opCid = ranking(TODAS, cidK).map(e => e.nome), opUF = ranking(TODAS, ufK).map(e => e.nome);
  const passa = e => (!st.linhas.length || st.linhas.includes(e.linha)) && (!st.grupos.length || st.grupos.includes(grupoK(e))) && (!st.cores.length || st.cores.includes(corK(e)))
    && (!st.vend.length || st.vend.includes(vendK(e))) && (!st.cid.length || st.cid.includes(cidK(e))) && (!st.uf.length || st.uf.includes(ufK(e)))
    && (!st.doc || docK(e) === st.doc) && (!st.cli || e.cliente.toLowerCase().includes(st.cli.toLowerCase())) && (!st.prod || buscaProd(e, st.prod));

  const app = document.getElementById("app");
  const txtMulti = (plural, vazioTxt = "Todos") => s => s.length ? (s.length === 1 ? s[0] : `${s.length} ${plural}`) : vazioTxt;
  const fLinha = multi({ opcoes: opLinhas.map(v => ({ v, cor: Q(v) })), sel: st.linhas, texto: txtMulti("linhas", "Todas"), busca: false, limpar: false, todosTxt: "Todas", largura: 224,
    onChange: s => { st.linhas = s; render(); } });
  const fGrupo = multi({ opcoes: opGrupos.map(v => ({ v })), sel: st.grupos, texto: txtMulti("grupos", "Todas"), busca: false, limpar: false, todosTxt: "Todas", largura: 224, onChange: s => { st.grupos = s; render(); } });
  const fCor = multi({ opcoes: opCores.map(v => ({ v, cor: corDe(v) })), sel: st.cores, texto: txtMulti("cores", "Todas"), busca: false, limpar: false, todosTxt: "Todas", largura: 224, onChange: s => { st.cores = s; render(); } });
  const fVend = multi({ opcoes: opVend.map(v => ({ v })), sel: st.vend, texto: txtMulti("vendedores"), onChange: s => { st.vend = s; render(); } });
  const fCid = multi({ opcoes: opCid.map(v => ({ v })), sel: st.cid, texto: txtMulti("cidades"), onChange: s => { st.cid = s; render(); } });
  const fUF = multi({ opcoes: opUF.map(v => ({ v })), sel: st.uf, texto: txtMulti("UFs"), onChange: s => { st.uf = s; render(); } });
  // "Todas" no filtro de linha/grupo/cor do Lovable limpa a seleção
  [fLinha, fGrupo, fCor].forEach(f => { const ligar = f.ligar; f.ligar = () => { ligar(); }; });
  const campo = (rot, html) => `<div class="lv-campo"><span class="lbl">${rot}</span>${html}</div>`;
  app.innerHTML = `<div class="lv-fgrid">
    ${campo("De", `<input type="date" id="fDe" value="${st.de}">`)}${campo("Até", `<input type="date" id="fAte" value="${st.ate}">`)}
    ${campo("Linha", fLinha.html)}${campo("Grupo", fGrupo.html)}${campo("Cor", fCor.html)}${campo("Vendedor", fVend.html)}
    ${campo("Cidade", fCid.html)}${campo("Estado (UF)", fUF.html)}
    ${campo("Tipo de documento", `<select id="fDoc"><option value="">Todos</option><option>Nota Fiscal</option><option>Recibo</option></select>`)}
    ${campo("Cliente", `<input type="text" id="fCli" placeholder="Buscar cliente">`)}${campo("Produto", `<input type="text" id="fProd" placeholder="Código ou nome">`)}
    ${campo("Agrupar por", `<select id="fG"><option value="dia">Dia</option><option value="semana">Semana</option><option value="mes" selected>Mês</option><option value="trimestre">Trimestre</option><option value="ano">Ano</option></select>`)}
  </div>${TODAS.length ? "" : '<p class="lv-art" style="padding:24px;text-align:center;color:var(--lv-muted-fg)">Nenhuma venda carregada ainda. Use “Importar planilha”.</p>'}<div id="corpo" class="lv-stack"></div>`;
  // Linha/Grupo/Cor: no Lovable o item "Todas" limpa (= todas); trocar o comportamento do botão
  [fLinha, fGrupo, fCor].forEach(f => f.ligar());
  [fVend, fCid, fUF].forEach(f => f.ligar());
  app.querySelectorAll(".lv-fgrid [data-t]").forEach((b, i) => { if (i < 3) { const nb = b.cloneNode(true); b.replaceWith(nb);
    nb.addEventListener("click", () => { const d = nb.closest("details"); d.querySelectorAll("input[data-i]").forEach(c => c.checked = false); d.querySelector("summary .trunc").textContent = "Todas";
      [() => st.linhas = [], () => st.grupos = [], () => st.cores = []][i](); render(); }); } });
  const deb = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  document.getElementById("fDe").addEventListener("change", e => { st.de = e.target.value; render(); });
  document.getElementById("fAte").addEventListener("change", e => { st.ate = e.target.value; render(); });
  document.getElementById("fDoc").addEventListener("change", e => { st.doc = e.target.value; render(); });
  document.getElementById("fG").addEventListener("change", e => { st.g = e.target.value; render(); });
  document.getElementById("fCli").addEventListener("input", deb(e => { st.cli = e.target.value; render(); }));
  document.getElementById("fProd").addEventListener("input", deb(e => { st.prod = e.target.value; render(); }));

  // ---------- gráficos genéricos
  const opts = (extra = {}) => ({ interaction: { mode: "index", intersect: false }, ...extra });
  const tipLinhas = () => ({ callbacks: { label: c => `${c.dataset.label}: ${H(c.raw)}`, labelColor: bolinha } });
  function barrasEmpilhadas(id, dados, series, cor, { altura = 280 } = {}) {
    if (!dados.length) return;
    novo(id, { type: "bar", data: { labels: dados.map(d => d.label), datasets: series.map((s, i) => ({ label: s, data: dados.map(d => d.v[s] ?? 0), backgroundColor: cor(s, i),
      borderColor: "#fff", borderWidth: .5, stack: "a", ...(i === series.length - 1 ? { rotulo: j => Z(dados[j].total) } : {}) })) },
      options: opts({ layout: { padding: { top: 20 } }, plugins: { tooltip: { filter: c => c.raw !== 0, callbacks: { label: c => { const t = dados[c.dataIndex].total; return `${c.dataset.label}: ${H(c.raw)}${t ? ` (${P(c.raw / t)})` : ""}`; }, labelColor: bolinha } } },
        scales: { x: { ...eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), stacked: true }, y: { ...eixo(), stacked: true, afterFit: s => { s.width = 60; } } } }) });
  }
  // barras horizontais com rótulo à direita (St do Lovable)
  function barrasH(id, d, { cor = C.chart[0], corItem, extra, largura = 170, rotH = 26 }) {
    if (!d.length) return;
    const rot = e => `${Z(e.total)} · ${P(e.pct)}${extra ? extra(e) : ""}`;
    document.getElementById(id).parentElement.style.height = Math.max(200, d.length * rotH + 20) + "px";
    novo(id, { type: "bar", data: { labels: d.map(e => corta(e.nome, 28)), datasets: [{ data: d.map(e => e.total), backgroundColor: d.map(e => corItem ? corItem(e) : cor), rotulo: i => rot(d[i]) }] },
      options: { indexAxis: "y", layout: { padding: { right: extra ? 200 : 110, left: 4 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => d[it[0].dataIndex].nome,
        label: c => { const r = d[c.dataIndex]; return `Faturamento: ${H(r.total)} (${P(r.pct)})${r.kg ? ` · ${N0(r.kg)} kg` : ""}${r.clientes == null ? "" : ` · ${r.clientes} clientes`}${r.ticketPedido == null ? "" : ` · ticket ${H(r.ticketPedido)}`}`; } } } },
        scales: { x: { display: false, min: Math.min(0, ...d.map(e => e.total)), max: Math.max(0, ...d.map(e => e.total)) || 1 }, y: { afterFit: s => { s.width = largura; }, grid: { display: false }, border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 10 } } } } } });
  }
  // rosca + tabela por dimensão (qe do Lovable)
  function rosca(id, titulo, dimensao, dados, colorFor = corPadrao) {
    const tot = dados.reduce((a, e) => a + e.total, 0), neg = dados.some(e => e.total < 0);
    const r = roscaTabela(id, { name: titulo, total: tot, slices: dados.map(e => ({ name: e.nome, value: e.total, percent: e.pct * 100 })) },
      { coluna: dimensao.charAt(0).toUpperCase() + dimensao.slice(1), subtitulo: `Faturamento por ${dimensao}`, fmtValor: H, colunaValor: "R$", unidade: "Faturamento",
        minPct: 3, rotulosValor: true, outline: OUTLINE, vazio: "Sem dados no filtro", colorFor,
        alternativo: neg ? `<div class="lv-chart" style="height:${Math.max(260, dados.length * 32)}px"><canvas id="${id}"></canvas></div>` : null });
    const desenhar = () => { if (!neg) return r.desenhar();
      novo(id, { type: "bar", data: { labels: dados.map(e => e.nome), datasets: [{ data: dados.map(e => e.total), backgroundColor: dados.map(e => colorFor(e.nome).fill), borderColor: OUTLINE, borderWidth: 1 }] },
        options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${H(c.raw)} (${P(dados[c.dataIndex].pct)})` } } },
          scales: { x: eixo(Z, { ticks: { font: { size: 10 }, callback: v => Z(v) } }), y: { afterFit: s => { s.width = 120; }, grid: { display: false }, ticks: { font: { size: 10 } } } } } }); };
    return { html: r.html, desenhar };
  }
  const linhaDs = (rot, dados, cor, extra = {}) => ({ type: "line", label: rot, data: dados, borderColor: cor, backgroundColor: cor, borderWidth: 2, pointRadius: 3, pointBackgroundColor: "#fff", pointBorderWidth: 1, spanGaps: false, ...extra });

  // ---------- desenho
  let cache = {};
  function render() {
    destruir();
    const corpo = document.getElementById("corpo");
    const B = TODAS.filter(e => (!st.de || e.data >= st.de) && (!st.ate || e.data <= st.ate) && passa(e));
    const V = st.de && st.ate ? anterior(st.de, st.ate) : null;
    const ant = V ? TODAS.filter(e => e.data >= V.ini && e.data <= V.fim && passa(e)) : [];
    const U = totais(B), W = totais(ant);
    const G = porPeriodo(B, st.g), Me = comMedia(G, st.g), media = G.length ? U.faturamento / G.length : 0;
    const Pe = opLinhas.filter(l => G.some(p => p.linhas[l] != null));
    const K = meses(B);
    if (st.mesesSel === null) { /* todos */ } else st.mesesSel = st.mesesSel.filter(m => K.includes(m));
    const Ie = st.mesesSel === null ? K : st.mesesSel;
    const q = B.filter(e => Ie.includes(chP(e.data, "mes")));
    const He = ranking(q, e => e.linha), We = ranking(B, e => e.cliente), Ge = ranking(q, e => e.cliente), Ke = produtos(q), Ye = grupos(q), Qe = cores(q);
    cache = { B, q, G };
    const varK = (rot, val, v) => kpi(rot, val, { grande: false, sub: v == null ? "sem base anterior" : `${v >= 0 ? "▲" : "▼"} ${fmt.num(Math.abs(v) * 100, 1, 1)}% vs anterior`, subCor: v == null ? "var(--lv-muted-fg)" : v >= 0 ? C.ok : C.loss });
    const rLinha = rosca("dLinha", "Faturamento por linha", "linha", He, n => ({ fill: Q(n), label: C.fg, halo: true }));
    const rCor = rosca("dCor", "Faturamento por cor", "cor", Qe);
    const lc = linhasCores(q), rLC = lc.map((l, i) => rosca("dLC" + i, `Linha — ${l.nome}`, "cor", l.cores));
    const meses0 = multi({ opcoes: K.map(m => ({ v: m, t: rotP(m, "mes") })), sel: Ie, busca: false, largura: 320, texto: s => K.length && s.length === K.length ? "Todos" : s.length ? (s.length === 1 ? rotP(s[0], "mes") : `${s.length} meses`) : "Nenhum",
      onChange: s => { st.mesesSel = s.length === K.length ? null : s; render(); } });
    corpo.innerHTML = `
      <div class="lv-kg md3 x6">${varK("Faturamento", H(U.faturamento), variacao(U.faturamento, W.faturamento))}${varK("Volume (sacola+bobina)", `${N0(U.kg)} kg`, variacao(U.kg, W.kg))}
        ${varK("R$/kg médio", U.rsKg == null ? "—" : H(U.rsKg), variacao(U.rsKg, W.rsKg))}${varK("Clientes ativos", fmt.num(U.clientes, 0), variacao(U.clientes, W.clientes))}
        ${varK("Itens faturados", fmt.num(U.itens, 0), variacao(U.itens, W.itens))}${varK("Ticket médio/cliente", U.ticket == null ? "—" : H(U.ticket), variacao(U.ticket, W.ticket))}</div>
      ${V ? `<p class="lv-nota">Comparação com ${fmt.data(V.ini)} a ${fmt.data(V.fim)} (mesma duração).</p>` : ""}
      <div class="lv-g xl3">${panel("Faturamento por período (R$)", canvas("gPer", 320), { classe: "span2" })}</div>
      <div class="lv-g lg2">${panel("R$/kg da sacola/bobina por período", canvas("gRsKg", 240))}${panel("Clientes ativos por período", canvas("gCliP", 240))}</div>
      <div id="cardProd"></div>
      <div class="lv-campo" style="width:min(320px,100%)"><span class="lbl">Mês (gráficos abaixo)</span>${meses0.html}</div>
      ${panel("Faturamento por grupo", Ye.length ? canvas("gGrupo", 220) : vazio())}
      <div class="lv-g lg2">${rLinha.html}${rCor.html}</div>
      <section><h2 class="lv-h2">Faturamento por cor em cada linha</h2>${lc.length ? `<div class="lv-g lg2">${rLC.map(r => r.html).join("")}</div>` : vazio()}</section>
      <div class="lv-g lg2">${panel(`Clientes (R$ e %) · ${fmt.num(Ge.length, 0)}`, rank(Ge.map(e => ({ ...e, valor: e.total })), { cor: CLI_ATIVOS, rowH: 24, visivel: 15, yW: 160, maxC: 28, direita: 110,
          rotulo: e => `${Z(e.total)} · ${P(e.pct)}`, titulo: e => `${e.nome}\nFaturamento: ${H(e.total)} (${P(e.pct)})` }))}
        ${panel(`Produtos (R$, kg e %) · ${fmt.num(Ke.length, 0)}`, rank(Ke.map(e => ({ ...e, valor: e.total })), { cor: C.chart[0], rowH: 24, visivel: 15, yW: 210, maxC: 38, direita: 160, corItem: e => Q(e.linha ?? ""),
          rotulo: e => `${Z(e.total)} · ${P(e.pct)}${e.kg ? ` · ${N0(e.kg)} kg` : ""}`, titulo: e => `${e.nome}\nFaturamento: ${H(e.total)} (${P(e.pct)})${e.kg ? ` · ${N0(e.kg)} kg` : ""}` })
          + (Ke.length ? `<div class="lv-leg-c" style="justify-content:flex-start">${[...new Set(Ke.map(e => e.linha).filter(Boolean))].map(l => `<span><i style="background:${Q(l)}"></i>${esc(l)}</span>`).join("")}</div>` : ""))}</div>
      <div id="cardEvoCli"></div>
      <div id="secoes" class="lv-stack" style="--g:24px"></div>
      <div id="cardResumo"></div>
      <div id="cardDet"></div>`;
    meses0.ligar();
    // Faturamento por período (empilhado por linha, coluna de média e linha da média)
    if (Me.length) novo("gPer", { type: "bar", data: { labels: Me.map(p => p.label), datasets: Pe.map((l, i) => ({ label: l, data: Me.map(p => p.linhas[l] ?? 0), stack: "a",
        backgroundColor: Me.map(p => p.isMedia ? misturar(Q(l).startsWith("#") ? Q(l) : "#54676e", .3) : Q(l)), borderColor: Me.map(p => p.isMedia ? Q(l) : "#fff"), borderWidth: Me.map(p => p.isMedia ? 1.5 : .5),
        ...(i === Pe.length - 1 ? { rotulo: j => Z(Me[j].total) } : {}) })) },
      options: opts({ layout: { padding: { top: 20 } }, plugins: { lvRef: { linhas: [...(media ? [{ y: media, dash: [5, 4], rot: `Média ${Z(media)}`, rotAbaixo: false }] : []), ...(G.length ? [{ x: rotMedia(st.g), inicio: true }] : [])] },
        tooltip: { filter: c => true, itemSort: () => 0, callbacks: { title: it => { const p = Me[it[0].dataIndex]; return p.isMedia ? tituloMedia(st.g, p.nPeriodos) : p.label; },
          label: c => { const p = Me[c.dataIndex], t = +p.linhas[c.dataset.label] || 0; return `${c.dataset.label}: ${H(t)}${p.total ? ` (${fmt.num(t / p.total * 100, 1, 1)}%)` : ""}`; },
          labelColor: bolinha, footer: it => `Total: ${H(Me[it[0].dataIndex].total)}` } } },
        scales: { x: { ...eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), stacked: true }, y: { ...eixo(), stacked: true, afterFit: s => { s.width = 60; } } } }) });
    // R$/kg sacola/bobina
    const rk = [{ name: "Sacola", key: "rsKgSacola" }, { name: "Bobina", key: "rsKgBobina" }].filter(e => Pe.includes(e.name));
    if (G.length) { const vals = G.flatMap(e => [e.rsKgSacolaBobina, ...rk.map(t => e[t.key])]).filter(v => typeof v === "number");
      const amp = vals.length ? Math.max(1, Math.max(...vals) - Math.min(...vals)) : 1, perto = amp * .16;
      novo("gRsKg", { type: "line", data: { labels: G.map(p => p.label), datasets: [
        ...rk.map(t => linhaDs(t.name, G.map(p => p[t.key]), Q(t.name), { halo: true, corRotulo: () => Q(t.name), rotuloAbaixo: t.name === "Sacola", offRotulo: t.name === "Sacola" ? 10 : 8,
          rotulo: (i, v) => v == null || (t.name === "Bobina" && G[i].rsKgSacolaBobina != null && Math.abs(v - G[i].rsKgSacolaBobina) < perto) ? null : fmt.num(v, 2, 2) })),
        linhaDs("Total", G.map(p => p.rsKgSacolaBobina), TOTAL_RSKG, { borderWidth: 3, halo: true, offRotulo: 12, rotulo: (i, v) => v == null ? null : fmt.num(v, 2, 2) })] },
        options: opts({ layout: { padding: { top: 24, right: 22 } }, plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label === "Total" ? "Total (sacola + bobina)" : c.dataset.label}: ${c.raw == null ? "—" : `${H(c.raw)}/kg`}`, labelColor: bolinha } } },
          scales: { x: eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), y: eixo(v => fmt.num(v, 2, 2), { suggestedMin: Math.min(...vals) - amp * .3, suggestedMax: Math.max(...vals) + amp * .12 }) } }) }); }
    // Clientes ativos
    if (G.length) novo("gCliP", { type: "bar", data: { labels: G.map(p => p.label), datasets: [{ label: "Clientes", data: G.map(p => p.clientes), backgroundColor: CLI_ATIVOS, rotulo: (i, v) => v }] },
      options: { layout: { padding: { top: 16 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `Clientes: ${fmt.num(c.raw, 0)}` } } },
        scales: { x: eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), y: eixo(v => fmt.num(v, 0), { ticks: { precision: 0, callback: v => fmt.num(v, 0) } }) } } });
    cardProduto(B);
    // Faturamento por grupo (barras horizontais empilhadas por linha)
    if (Ye.length) { const ls = [...new Set(Ye.flatMap(e => Object.keys(e.linhas)))].sort((a, b) => Ye.reduce((s, t) => s + (t.linhas[b] ?? 0), 0) - Ye.reduce((s, t) => s + (t.linhas[a] ?? 0), 0));
      document.getElementById("gGrupo").parentElement.style.height = Math.max(220, Ye.length * 30 + 40) + "px";
      novo("gGrupo", { type: "bar", data: { labels: Ye.map(e => corta(e.nome, 26)), datasets: ls.map((l, i) => ({ label: l, data: Ye.map(e => e.linhas[l] ?? 0), backgroundColor: Q(l), stack: "a", categoryPercentage: .7, barPercentage: 1,
          ...(i === ls.length - 1 ? { rotulo: j => `${Z(Ye[j].total)} · ${P(Ye[j].pct)}${Ye[j].kg ? ` · ${N0(Ye[j].kg)} kg` : ""}` } : {}) })) },
        options: { indexAxis: "y", interaction: { mode: "index", axis: "y", intersect: false }, layout: { padding: { right: 170, left: 4 } },
          plugins: { tooltip: { filter: c => c.raw !== 0, callbacks: { title: it => Ye[it[0].dataIndex].nome, label: c => { const n = Ye[c.dataIndex]; return `${c.dataset.label}: ${H(c.raw)} (${P(n.total ? c.raw / n.total : 0)})`; },
            labelColor: bolinha, footer: it => { const n = Ye[it[0].dataIndex]; return `Total: ${H(n.total)} (${P(n.pct)})${n.kg ? ` · ${N0(n.kg)} kg` : ""}`; } } } },
          scales: { x: { display: false, stacked: true }, y: { stacked: true, afterFit: s => { s.width = 170; }, grid: { display: false }, border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 10 } } } } } }); }
    rLinha.desenhar(); rCor.desenhar(); rLC.forEach(r => r.desenhar());
    cardEvoCli(B);
    secoes(B);
    cardResumo(We);
    cardDetalhe(B);
  }

  // R$/kg por produto simplificado (seletor próprio; por padrão os 5 primeiros)
  function cardProduto(B) {
    const box = document.getElementById("cardProd"), n = produtosKg(B);
    if (!st.prodMexeu || st.prodSel === null) st.prodSel = n.slice(0, 5); else st.prodSel = st.prodSel.filter(p => n.includes(p));
    const sel = () => n.filter(p => st.prodSel.includes(p));
    const m = multi({ opcoes: n.map(v => ({ v })), sel: st.prodSel, largura: 384, todosTxt: "Todos", texto: s => s.length ? (s.length === n.length ? "Todos" : s.length === 1 ? s[0] : `${s.length} produtos`) : "Nenhum",
      onChange: s => { st.prodMexeu = true; st.prodSel = s; desenhar(); } });
    box.innerHTML = panel("R$/kg por produto simplificado por período", `<div class="lv-campo" style="width:min(384px,100%);margin-bottom:12px"><span class="lbl">Produto</span>${m.html}</div><div id="gProdBox"></div>`);
    m.ligar();
    function desenhar() {
      const y = sel(), pts = rsKgProduto(B, st.g, y), poucos = y.length <= 3, alvo = document.getElementById("gProdBox");
      if (!pts.length) { alvo.innerHTML = vazio(); return; }
      alvo.innerHTML = canvas("gProd", 320);
      novo("gProd", { type: "line", data: { labels: pts.map(p => p.label), datasets: [
        ...y.map((p, i) => linhaDs(p, pts.map(x => x.valores[i]), corProd(i), poucos ? { halo: true, corRotulo: () => corProd(i), rotuloAbaixo: true, offRotulo: 8, rotulo: (j, v) => v == null ? "" : fmt.num(v, 2, 2) } : {})),
        linhaDs("Total", pts.map(p => p.total), TOTAL_RSKG, { borderWidth: 3, halo: true, offRotulo: 12, rotulo: (j, v) => v == null ? null : fmt.num(v, 2, 2) })] },
        options: opts({ layout: { padding: { top: 24, right: 22 } }, plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.raw == null ? "—" : `${H(c.raw)}/kg`}`, labelColor: bolinha } } },
          scales: { x: eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), y: eixo(v => fmt.num(v, 2, 2)) } }) });
    }
    desenhar();
  }

  // Evolução mensal de vendas (seletor de cliente; sem seleção = total)
  function cardEvoCli(B) {
    const box = document.getElementById("cardEvoCli"), op = ranking(B, e => e.cliente).map(e => e.nome);
    st.cliEvo = st.cliEvo.filter(c => op.includes(c));
    const m = multi({ opcoes: op.map(v => ({ v })), sel: st.cliEvo, largura: 320, texto: s => s.length ? (s.length === 1 ? s[0] : `${s.length} clientes`) : "Todos",
      onChange: s => { st.cliEvo = s; desenhar(); } });
    box.innerHTML = panel("Evolução mensal de vendas (R$)", `<div class="lv-campo" style="width:min(320px,100%);margin-bottom:12px"><span class="lbl">Cliente</span>${m.html}</div><div id="gEvoCliBox"></div>`);
    m.ligar();
    function desenhar() {
      const a = evolCliente(B, st.cliEvo), alvo = document.getElementById("gEvoCliBox"), poucos = a.series.length <= 3;
      if (!a.meses.length) { alvo.innerHTML = vazio(); return; }
      alvo.innerHTML = canvas("gEvoCli", 300);
      novo("gEvoCli", { type: "line", data: { labels: a.meses.map(x => x.label), datasets: a.series.map((s, i) => linhaDs(s.nome, s.valores, st.cliEvo.length ? corCli(i) : CLI_ATIVOS,
        { tension: .35, borderWidth: st.cliEvo.length ? 2 : 2.5, ...(poucos ? { rotulo: (j, v) => Z(v) } : {}) })) },
        options: opts({ layout: { padding: { top: 20, right: 16 } }, plugins: { legend: { display: !!st.cliEvo.length }, tooltip: tipLinhas() },
          scales: { x: eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), y: eixo(Z, { afterFit: s => { s.width = 60; } }) } }) });
    }
    desenhar();
  }

  // Canal de documento, Vendedores, Geografia e Estados
  function secoes(B) {
    const box = document.getElementById("secoes"), tot = B.reduce((a, e) => a + e.total, 0);
    const docs = ranking(B, docK), serieDoc = serieChave(B, st.g, docK, ["Nota Fiscal", "Recibo"]), rec = docs.find(e => e.nome === "Recibo");
    const vs = vendedores(B), opV = vs.map(e => e.nome);
    if (st.vendSel !== null) st.vendSel = st.vendSel.filter(v => opV.includes(v));
    const selV = st.vendSel ?? opV.slice(0, 5);
    const mtz = matriz(B), maxM = Math.max(1, ...mtz.linhasMatriz.flatMap(e => Object.values(e.valores)));
    const cid = topN(comClientes(B, cidK), 15), reg = ranking(B, e => manaus(e) ? "Manaus" : "Interior"), noAM = B.filter(manaus);
    const bairros = comClientes(noAM, bairroK).map(e => ({ ...e, valor: e.total, pct: tot ? e.total / tot : 0 })), interior = reg.find(e => e.nome === "Interior");
    const rDoc = rosca("dDoc", "Nota Fiscal x Recibo", "documento", docs, n => ({ fill: DOC[n] ?? C.muted, label: C.fg, halo: true }));
    const rReg = rosca("dReg", "Manaus x Interior", "região", reg, n => ({ fill: GEO[n] ?? C.muted, label: C.fg, halo: true }));
    const mV = multi({ opcoes: opV.map(v => ({ v })), sel: selV, texto: s => s.length ? (s.length === 1 ? s[0] : `${s.length} vendedores`) : "Nenhum", onChange: s => { st.vendSel = s; evoVend(); } });
    const es = estados(B), { categorias, chave } = categoriasUF(es), serieUF = serieChave(B, st.g, chave, categorias);
    const linhasUF = [...new Set(B.map(e => e.linha))].sort((a, b) => es.reduce((s, n) => s + (n.linhas[b] ?? 0), 0) - es.reduce((s, n) => s + (n.linhas[a] ?? 0), 0));
    const mix = es.map(e => { const t = Object.values(e.linhas).reduce((s, v) => s + Math.max(0, v), 0); return { nome: e.nome, total: e.total, pcts: Object.fromEntries(linhasUF.map(l => [l, t ? Math.max(0, e.linhas[l] ?? 0) / t : 0])), rs: e.linhas }; });
    const totUF = es.reduce((a, e) => a + e.total, 0), am = es.find(e => e.nome === "AM"), lider = es.find(e => e.nome !== "AM");
    const idxUF = new Map(categorias.filter(e => e !== "AM" && e !== "Outras UFs").map((e, i) => [e, i]));
    const corUF = e => e === "AM" ? GEO.Manaus : e === "Outras UFs" ? C.muted : UF_COR[(idxUF.get(e) ?? 0) % UF_COR.length];
    const secao = (t, h) => `<section class="lv-secao">${`<h2>${t}</h2>`}${h}</section>`;
    const kk = (r, v, s) => kpi(r, v, { grande: false, sub: s });
    box.innerHTML = secao("Canal de documento", `<div class="lv-kg md4">${kk("% vendido por recibo", rec ? P(rec.pct) : "0,0%", rec ? H(rec.total) : "")}${kk("Nota Fiscal", H(docs.find(e => e.nome === "Nota Fiscal")?.total ?? 0))}</div>
        <div class="lv-g lg2">${rDoc.html}${panel("Nota Fiscal x Recibo por período (R$)", serieDoc.length ? canvas("gDocP", 280) : vazio())}</div>`)
      + secao("Vendedores", panel("Faturamento por vendedor (R$, %, clientes e ticket/pedido)", vs.length ? canvas("gVend", 200) : vazio())
        + panel("Evolução por vendedor (R$)", `<div class="lv-campo" style="width:min(320px,100%);margin-bottom:12px"><span class="lbl">Vendedores</span>${mV.html}</div><div id="gEvoVendBox"></div>`)
        + panel("Matriz vendedor × linha (R$)", mtz.linhasMatriz.length ? tabela([{ t: "Vendedor" }, ...mtz.linhas.map(l => ({ t: `<span class="lv-sq" style="background:${Q(l)};margin-right:4px"></span>${esc(l)}`, r: 1 })), { t: "Total", r: 1 }],
          mtz.linhasMatriz.map(e => `<tr><td>${esc(e.nome)}</td>${mtz.linhas.map(l => { const n = e.valores[l] ?? 0, r = Math.max(0, Math.min(1, n / maxM));
            return `<td class="r" ${r ? `style="background:rgba(24,101,117,${(r * .45).toFixed(3)})"` : ""}>${n ? H(n) : ""}</td>`; }).join("")}<td class="r" style="font-weight:600">${H(e.total)}</td></tr>`), { maxH: "460px" }) : vazio()))
      + secao("Geografia", `<div class="lv-kg md4">${kk("Manaus", H(reg.find(e => e.nome === "Manaus")?.total ?? 0), P(reg.find(e => e.nome === "Manaus")?.pct ?? 0))}${kk("Interior", H(interior?.total ?? 0), P(interior?.pct ?? 0))}</div>
        <div class="lv-g lg3">${panel("Faturamento por cidade (top 15 + Outras)", cid.length ? canvas("gCid", 200) : vazio(), { classe: "span2" })}${rReg.html}</div>
        <div class="lv-g">${panel(`Bairros de Manaus (R$, % e clientes) · ${fmt.num(bairros.length, 0)}`, rank(bairros, { cor: GEO.Manaus, rowH: 26, visivel: 20, yW: 170, maxC: 28, direita: 170,
          rotulo: e => `${Z(e.total)} · ${P(e.pct)} · ${e.clientes} cli`, titulo: e => `${e.nome}\nFaturamento: ${H(e.total)} (${P(e.pct)}) · ${e.clientes} clientes` }))}</div>
        <div class="lv-stack"><h3 style="margin:0;font:600 14px/20px var(--lv-sans);color:var(--lv-muted-fg)">Estados</h3>
          <div class="lv-kg md4">${kk("UFs atendidas", fmt.num(es.filter(e => e.nome !== "(sem UF)").length, 0))}${kk("% faturamento no AM", P(am?.pct ?? 0), H(am?.total ?? 0))}
            ${kk("% fora do AM", P(totUF ? (totUF - (am?.total ?? 0)) / totUF : 0), H(totUF - (am?.total ?? 0)))}${kk("UF líder fora do AM", esc(lider?.nome ?? "—"), lider ? `${H(lider.total)} · ${P(lider.pct)}` : "")}</div>
          <div class="lv-g lg2">${panel("Faturamento por UF (R$, %, kg e clientes)", es.length ? canvas("gUF", 200) : vazio())}${panel("Mix de linhas por UF (%)", mix.length ? canvas("gMix", 220) : vazio())}</div>
          ${panel("Evolução por UF por período (R$) — AM x demais UFs", serieUF.length ? canvas("gUFP", 300) : vazio())}
          ${panel("Resumo por UF", es.length ? '<div id="tUF"></div>' : vazio())}</div>`);
    rDoc.desenhar(); rReg.desenhar(); mV.ligar();
    barrasEmpilhadas("gDocP", serieDoc, ["Nota Fiscal", "Recibo"], s => DOC[s]);
    barrasH("gVend", vs, { cor: VENDEDOR, extra: e => ` · ${e.clientes} cli · ticket ${e.ticketPedido == null ? "—" : Z(e.ticketPedido)}` });
    function evoVend() {
      const g = st.vendSel ?? opV.slice(0, 5), s = serieChave(B, st.g, vendK, g), alvo = document.getElementById("gEvoVendBox");
      if (!s.length || !g.length) { alvo.innerHTML = vazio(); return; }
      alvo.innerHTML = canvas("gEvoVend", 300);
      novo("gEvoVend", { type: "line", data: { labels: s.map(p => p.label), datasets: g.map((v, i) => linhaDs(v, s.map(p => p.v[v] ?? 0), corVend(i), g.length <= 3 ? { corRotulo: () => corVend(i), rotulo: (j, x) => Z(x) } : {})) },
        options: opts({ layout: { padding: { top: 16, right: 16 } }, plugins: { tooltip: tipLinhas() }, scales: { x: eixoX({ ticks: { autoSkip: false, maxRotation: 0 } }), y: eixo(Z, { afterFit: s => { s.width = 60; } }) } }) });
    }
    evoVend();
    barrasH("gCid", cid, { cor: GEO.Interior, corItem: e => e.nome.toLowerCase() === "manaus" ? GEO.Manaus : e.nome === "Outras" ? C.muted : GEO.Interior });
    // UF (barras com rótulo longo)
    if (es.length) { document.getElementById("gUF").parentElement.style.height = Math.max(200, es.length * 30 + 20) + "px";
      novo("gUF", { type: "bar", data: { labels: es.map(e => e.nome), datasets: [{ data: es.map(e => e.total), backgroundColor: es.map(e => e.nome === "AM" ? GEO.Manaus : GEO.Interior),
          rotulo: i => { const c = es[i]; return `${Z(c.total)} · ${P(c.pct)}${c.kg ? ` · ${N0(c.kg)} kg` : ""} · ${c.clientes} cli`; } }] },
        options: { indexAxis: "y", layout: { padding: { right: 230, left: 4 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => { const r = es[c.dataIndex]; return `Faturamento: ${H(r.total)} (${P(r.pct)})${r.kg ? ` · ${N0(r.kg)} kg` : ""} · ${r.clientes} clientes`; } } } },
          scales: { x: { display: false, min: Math.min(0, ...es.map(e => e.total)) }, y: { afterFit: s => { s.width = 70; }, grid: { display: false }, border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 11 } } } } } }); }
    if (mix.length) { document.getElementById("gMix").parentElement.style.height = Math.max(220, mix.length * 34 + 60) + "px";
      novo("gMix", { type: "bar", data: { labels: mix.map(e => e.nome), datasets: linhasUF.map(l => ({ label: l, data: mix.map(e => e.pcts[l]), backgroundColor: Q(l), borderColor: "#fff", borderWidth: .5, stack: "m" })) },
        options: { indexAxis: "y", interaction: { mode: "index", axis: "y", intersect: false }, layout: { padding: { right: 12, left: 4 } },
          plugins: { tooltip: { filter: c => c.raw > 0, callbacks: { label: c => `${c.dataset.label}: ${P(c.raw)} · ${H(mix[c.dataIndex].rs[c.dataset.label] ?? 0)}`, labelColor: bolinha } } },
          scales: { x: { stacked: true, min: 0, max: 1, grid: grade(), border: { color: C.muted }, ticks: { callback: v => `${Math.round(v * 100)}%`, font: { size: 10 } } },
            y: { stacked: true, afterFit: s => { s.width = 70; }, grid: { display: false }, border: { color: C.muted }, ticks: { autoSkip: false, font: { size: 11 } } } } } }); }
    barrasEmpilhadas("gUFP", serieUF, categorias, corUF);
    if (es.length) tabelaUF(B, es);
  }

  // Resumo por UF (ordenável, com linha de total)
  const COLS_UF = [{ k: "nome", t: "UF", f: e => esc(e.nome), v: e => e.nome }, { k: "total", t: "Faturamento", f: e => H(e.total), v: e => e.total }, { k: "pct", t: "%", f: e => P(e.pct), v: e => e.pct },
    { k: "clientes", t: "Clientes", f: e => fmt.num(e.clientes, 0), v: e => e.clientes }, { k: "pedidos", t: "Pedidos", f: e => fmt.num(e.pedidos, 0), v: e => e.pedidos },
    { k: "ticketPedido", t: "Ticket/pedido", f: e => H(e.ticketPedido), v: e => e.ticketPedido ?? -Infinity }, { k: "kg", t: "Kg", f: e => e.kg ? fmt.num(e.kg, 0) : "—", v: e => e.kg },
    { k: "rsKg", t: "R$/kg", f: e => e.rsKg == null ? "—" : fmt.num(e.rsKg, 2, 2), v: e => e.rsKg ?? -Infinity }, { k: "cidades", t: "Cidades", f: e => fmt.num(e.cidades, 0), v: e => e.cidades },
    { k: "ultima", t: "Última compra", f: e => fmt.data(e.ultima), v: e => e.ultima }];
  let ordUF = { k: "total", asc: false };
  function tabelaUF(B, es) {
    const box = document.getElementById("tUF"); if (!box) return;
    const col = COLS_UF.find(c => c.k === ordUF.k), lst = [...es].sort((a, b) => { const x = col.v(a), y = col.v(b), o = x < y ? -1 : +(x > y); return ordUF.asc ? o : -o; });
    const [t] = estados(B.map(e => ({ ...e, estado: "Total" }))), ult = es.reduce((a, e) => e.ultima > a ? e.ultima : a, "");
    box.innerHTML = tabela(COLS_UF.map(c => ({ t: `<button type="button" data-k="${c.k}">${c.t}${ordUF.k === c.k ? (ordUF.asc ? " ▲" : " ▼") : ""}</button>`, r: c.k !== "nome" })),
      lst.map(e => `<tr>${COLS_UF.map(c => `<td class="${c.k === "nome" ? "" : "r"}">${c.f(e)}</td>`).join("")}</tr>`),
      { maxH: "420px", total: t ? `<tr style="font-weight:600">${COLS_UF.map(c => `<td class="${c.k === "nome" ? "" : "r"}">${c.k === "nome" ? "Total" : c.k === "ultima" ? fmt.data(ult) : c.f(t)}</td>`).join("")}</tr>` : "" });
    box.querySelectorAll("th button").forEach(b => b.addEventListener("click", () => { const k = b.dataset.k; ordUF = { k, asc: ordUF.k === k ? !ordUF.asc : k === "nome" }; tabelaUF(B, es); }));
  }

  // Resumo por cliente
  function cardResumo(We) {
    const box = document.getElementById("cardResumo");
    box.innerHTML = panel("Resumo por cliente", tabela([{ t: "Cliente" }, { t: "Faturamento", r: 1 }, { t: "Kg", r: 1 }, { t: "Compras", r: 1 }, { t: "Dias", r: 1 }, { t: "Última compra" }, { t: "% total", r: 1 }],
      We.map(e => `<tr><td>${esc(e.nome)}</td><td class="r">${H(e.total)}</td><td class="r">${N0(e.kg)}</td><td class="r">${e.compras}</td><td class="r">${e.dias}</td><td>${fmt.data(e.ultima)}</td><td class="r">${P(e.pct)}</td></tr>`), { maxH: "420px" }),
      { acoes: `<button class="lv-btn" id="xResumo">${ICONE_DL} Excel</button>` });
    document.getElementById("xResumo").addEventListener("click", () => excel(We.map(e => ({ Cliente: e.nome, "Faturamento R$": e.total, Kg: e.kg, "Nº compras": e.compras, "Dias com compra": e.dias, "Última compra": fmt.data(e.ultima), "% do total": e.pct })), "vendas-resumo-clientes"));
  }
  const ICONE_DL = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/></svg>';

  // Vendas detalhadas (busca, ordenação, 50 por página, Excel)
  const COLS_DET = [{ k: "data", l: "Data", v: e => e.data, f: e => fmt.data(e.data) }, { k: "cliente", l: "Cliente", v: e => e.cliente }, { k: "familia", l: "Família", v: familia },
    { k: "descricao", l: "Descrição", v: e => e.descricao ?? "" }, { k: "grupo", l: "Grupo", v: grupoK }, { k: "cor", l: "Cor", v: corK }, { k: "produto", l: "Produto", v: e => e.produto },
    { k: "linha", l: "Linha", v: e => e.linha }, { k: "tipo_documento", l: "Documento", v: docK }, { k: "nota_fiscal", l: "NF", v: e => e.nota_fiscal ?? "" }, { k: "vendedor", l: "Vendedor", v: e => e.vendedor ?? "" },
    { k: "cidade", l: "Cidade", v: e => e.cidade ?? "" }, { k: "bairro", l: "Bairro", v: e => e.bairro ?? "" }, { k: "estado", l: "UF", v: e => e.estado ?? "" },
    { k: "quantidade", l: "Quantidade", v: e => +(e.quantidade ?? 0), num: 1, f: e => fmt.num(e.quantidade, 2) }, { k: "valor_unitario", l: "Valor unit.", v: e => +(e.valor_unitario ?? 0), num: 1, f: e => H(e.valor_unitario) },
    { k: "total", l: "Total", v: e => e.total, num: 1, f: e => H(e.total) }, { k: "kg", l: "Kg", v: e => +(e.kg ?? 0), num: 1, f: e => N0(e.kg) }];
  const det = { q: "", ord: { k: "data", asc: false }, pag: 0 };
  function cardDetalhe(B) {
    const box = document.getElementById("cardDet");
    box.innerHTML = `<section class="lv-panel"><header><h2 id="tDet"></h2><div style="display:flex;gap:8px"><input type="search" id="qDet" placeholder="Buscar…" style="width:192px" value="${esc(det.q)}"><button class="lv-btn" id="xDet">${ICONE_DL} Excel</button></div></header><div class="corpo" id="cDet"></div></section>`;
    const lista = () => { const t = det.q.trim().toLowerCase();
      const r = t ? B.filter(e => `${e.cliente} ${e.produto} ${familia(e)} ${e.descricao ?? ""} ${grupoK(e)} ${corK(e)} ${e.linha} ${e.vendedor ?? ""} ${e.cidade ?? ""} ${e.bairro ?? ""}`.toLowerCase().includes(t)) : B;
      const c = COLS_DET.find(x => x.k === det.ord.k) ?? COLS_DET[0];
      return [...r].sort((a, b) => { const x = c.v(a), y = c.v(b), o = typeof x === "number" ? x - y : String(x).localeCompare(String(y)); return det.ord.asc ? o : -o; }); };
    const desenhar = () => {
      const f = lista(), pags = Math.max(1, Math.ceil(f.length / 50)); det.pag = Math.min(det.pag, pags - 1);
      document.getElementById("tDet").textContent = `Vendas detalhadas (${fmt.num(f.length, 0)} itens)`;
      document.getElementById("cDet").innerHTML = tabela(COLS_DET.map(c => ({ t: `<button type="button" data-k="${c.k}">${c.l}${det.ord.k === c.k ? (det.ord.asc ? " ▲" : " ▼") : ""}</button>`, r: c.num })),
        f.slice(det.pag * 50, det.pag * 50 + 50).map(e => `<tr>${COLS_DET.map(c => `<td class="${c.num ? "r" : ""}">${esc(c.f ? c.f(e) : c.v(e))}</td>`).join("")}</tr>`), { maxH: "560px" })
        + `<div class="lv-paginas" style="font-size:12px"><button class="lv-btn" data-p="-1" ${det.pag === 0 ? "disabled" : ""}>Anterior</button><span>Página ${det.pag + 1} de ${pags}</span><button class="lv-btn" data-p="1" ${det.pag >= pags - 1 ? "disabled" : ""}>Próxima</button></div>`;
      box.querySelectorAll("th button").forEach(b => b.addEventListener("click", () => { const k = b.dataset.k; det.ord = { k, asc: det.ord.k !== k || !det.ord.asc }; desenhar(); }));
      box.querySelectorAll("[data-p]").forEach(b => b.addEventListener("click", () => { det.pag += +b.dataset.p; desenhar(); }));
      document.getElementById("xDet").onclick = () => excel(f.map(e => ({ Data: fmt.data(e.data), Cliente: e.cliente, "Família": familia(e), "Descrição": e.descricao, Grupo: e.grupo, Cor: e.cor, Produto: e.produto, Linha: e.linha,
        Quantidade: e.quantidade, "Valor unitário": e.valor_unitario, Total: e.total, Kg: e.kg, "Tipo documento": e.tipo_documento, "Nota fiscal": e.nota_fiscal, "Orçamento": e.orcamento, Vendedor: e.vendedor,
        Bairro: e.bairro, Cidade: e.cidade, Estado: e.estado, "CNPJ/CPF": e.cnpj_cpf, Unidade: e.unidade })), `vendas-${st.de}-a-${st.ate}`);
    };
    document.getElementById("qDet").addEventListener("input", deb(e => { det.q = e.target.value; det.pag = 0; desenhar(); }, 200));
    det.pag = 0; desenhar();
  }

  render();
})();
