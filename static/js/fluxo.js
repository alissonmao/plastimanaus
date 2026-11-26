// Entradas e Saídas base Omie — gráficos e filtros com o mesmo visual do projeto no Lovable (Recharts/shadcn).
// Usa G (dados vindos da view). Todos os filtros dos cartões mexem nos mesmos parâmetros da URL, como no Lovable.
(() => {
  const OK = "#00b050", GASTO = "#e7000b", MUTED = "#54676e", BORDA = "#e2e8f0", FG = "#020618", CH1 = "#186575";
  const SUN = ["#186575", "#d98a2e", "#934bc9", "#2f9e44", "#2563eb", "#948a54", "#7e90ae", "#54676e"];
  const SEM = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  const FONTE = '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif';
  const el = id => document.getElementById(id);
  const n1 = v => v.toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const V = v => { const a = Math.abs(v); return a >= 1e6 ? `${n1(v / 1e6)} mi` : a >= 1e3 ? `${n1(v / 1e3)} mil` : v.toLocaleString("pt-BR", { maximumFractionDigits: 0 }); };
  const H = v => v == null ? "" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const P = v => v == null ? "—" : (v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + "%";
  const N = v => v.toLocaleString("pt-BR");
  const dmy = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const dmyc = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(2, 4)}`;
  const ds = iso => SEM[new Date(iso + "T12:00:00").getDay()];
  const dia2 = iso => [`${iso.slice(8, 10)}/${iso.slice(5, 7)}`, ds(iso)];
  const corta = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const clarear = (hex, q) => { // mistura com branco (q = fração de branco)
    const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).map(x => Math.round(x + (255 - x) * q));
    return `rgb(${c.join(",")})`;
  };

  if (window.Chart) {
    Chart.defaults.font.family = FONTE; Chart.defaults.font.size = 11; Chart.defaults.color = MUTED;
    Chart.defaults.maintainAspectRatio = false; Chart.defaults.animation = false;
    Object.assign(Chart.defaults.plugins.tooltip, { backgroundColor: "#fff", borderColor: BORDA, borderWidth: 1, titleColor: FG, bodyColor: FG,
      footerColor: FG, padding: 8, cornerRadius: 6, boxPadding: 4, usePointStyle: true,
      titleFont: { family: FONTE, size: 12, weight: "600" }, bodyFont: { family: FONTE, size: 12 }, footerFont: { family: FONTE, size: 12, weight: "600" } });
    Object.assign(Chart.defaults.plugins.legend, { position: "bottom" });
    Chart.defaults.plugins.legend.labels = { ...Chart.defaults.plugins.legend.labels, boxWidth: 12, boxHeight: 10, font: { family: FONTE, size: 12 }, color: MUTED };
    // Rótulos de valor (barras, pontos e fatias)
    Chart.register({ id: "rotulos", afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((d, di) => {
        if (!d.rotulo || !chart.isDatasetVisible(di)) return;
        chart.getDatasetMeta(di).data.forEach((e, i) => {
          const t = d.rotulo(i, d.data[i]); if (t == null || t === "") return;
          ctx.save(); ctx.font = `${d.pesoRotulo || 400} ${d.tamRotulo || 10}px ${FONTE}`; ctx.fillStyle = d.corRotulo ? d.corRotulo(i) : FG;
          if (e instanceof Chart.ArcElement) {
            const r = d.rotuloFora ? e.outerRadius + 12 : (e.innerRadius + e.outerRadius) / 2, a = (e.startAngle + e.endAngle) / 2;
            ctx.textAlign = d.rotuloFora ? (Math.cos(a) >= 0 ? "left" : "right") : "center"; ctx.textBaseline = "middle";
            if (d.rotuloFora) ctx.textAlign = "center";
            ctx.fillText(t, e.x + Math.cos(a) * r, e.y + Math.sin(a) * r);
          } else if (chart.options.indexAxis === "y") {
            ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(t, Math.max(e.x, e.base) + 4, e.y + 1);
          } else if (d.rotuloGirado) {
            ctx.translate(e.x, Math.min(e.y, e.base) - 6); ctx.rotate(-Math.PI / 2); ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(t, 0, 0);
          } else {
            ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(t, e.x, Math.min(e.y, e.base ?? e.y) - (d.offRotulo ?? 6));
          }
          ctx.restore();
        });
      });
    } });
  }
  const grade = (extra = {}) => ({ color: c => c.tick && c.tick.value === 0 && extra.zero ? MUTED : BORDA, borderDash: [3, 3], drawTicks: false, ...extra });
  const eixoV = (extra = {}) => ({ grid: grade({ zero: true }), border: { color: MUTED }, ticks: { callback: v => V(v), padding: 6 }, ...extra });
  const eixoX = (diario, n, extra = {}) => ({ grid: grade(), border: { color: MUTED },
    ticks: { autoSkip: !diario && n > 16, maxRotation: 0, padding: 6, font: { size: diario ? 9 : 11 } }, ...extra });

  // 1. Entradas x Gastos
  const S = G.serie, diario = G.modo === "dia";
  if (el("gSerie") && S.length) new Chart(el("gSerie"), {
    data: { labels: S.map(p => diario ? dia2(p.chave) : p.label), datasets: [
      { type: "bar", label: "Entradas", data: S.map(p => p.entradas), backgroundColor: OK, yAxisID: "m", order: 3 },
      { type: "bar", label: "Gastos", data: S.map(p => p.gastos), backgroundColor: GASTO, yAxisID: "m", order: 3 },
      { type: "line", label: "Saldo", data: S.map(p => p.saldo), borderColor: MUTED, backgroundColor: "#fff", borderDash: [5, 4], borderWidth: 2, pointRadius: 2, pointBorderWidth: 1, yAxisID: "m", order: 1 },
      { type: "line", label: "Entradas acumuladas", data: S.map(p => p.entradasAcum), borderColor: OK, backgroundColor: "#fff", borderWidth: 2, pointRadius: 2, pointBorderWidth: 1, yAxisID: "a", order: 0 },
      { type: "line", label: "Gastos acumulados", data: S.map(p => p.gastosAcum), borderColor: GASTO, backgroundColor: "#fff", borderWidth: 2, pointRadius: 2, pointBorderWidth: 1, yAxisID: "a", order: 0 },
    ] },
    options: { interaction: { mode: "index", intersect: false }, layout: { padding: { top: 8 } },
      plugins: { legend: { labels: { sort: (a, b) => a.datasetIndex - b.datasetIndex } }, tooltip: { itemSort: (a, b) => a.datasetIndex - b.datasetIndex, callbacks: {
        title: it => diario ? dmy(S[it[0].dataIndex].chave) : S[it[0].dataIndex].label,
        label: c => `${c.dataset.label === "Saldo" ? "Saldo do período" : c.dataset.label}: ${H(c.raw)}`,
        labelTextColor: c => [OK, GASTO, FG, OK, GASTO][c.datasetIndex],
        afterBody: it => [`Saldo acumulado: ${H(S[it[0].dataIndex].saldoAcum)}`] } } },
      scales: { x: eixoX(diario, S.length, { ticks: { autoSkip: false, maxRotation: 0, padding: 6, font: { size: diario ? 9 : 11 } } }),
        m: eixoV({ position: "left" }),
        a: eixoV({ position: "right", grid: { display: false }, title: { display: true, text: "Acumulado (R$)", color: MUTED, font: { size: 11 } } }) } },
  });

  // 2. Saldo acumulado (área)
  const SA = G.saldo;
  if (el("gSaldo") && SA.length) {
    const vs = SA.map(p => p.v), mi = vs.indexOf(Math.min(...vs)), ma = vs.indexOf(Math.max(...vs));
    const marcar = G.saldoDia ? new Set([0, vs.length - 1, mi, ma]) : null;
    new Chart(el("gSaldo"), { type: "line",
      data: { labels: SA.map(p => G.saldoDia ? dia2(p.chave) : p.label), datasets: [{ label: "Saldo acumulado", data: vs, borderColor: CH1, borderWidth: 1,
        backgroundColor: "rgba(24,101,117,.25)", fill: "origin", pointRadius: 0, pointHoverRadius: 4, tension: 0, offRotulo: 8,
        rotulo: (i, v) => (marcar ? marcar.has(i) : vs.length <= 16) ? V(v) : null }] },
      options: { interaction: { mode: "index", intersect: false }, layout: { padding: { top: 20, right: 30 } },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          title: it => G.saldoDia ? dmy(SA[it[0].dataIndex].chave) : SA[it[0].dataIndex].label, label: c => `Saldo acumulado: ${H(c.raw)}` } } },
        scales: { x: eixoX(G.saldoDia, vs.length, G.saldoDia ? { ticks: { autoSkip: false, maxRotation: 0, font: { size: 9 } } } : {}), y: eixoV() } } });
  }

  // 3. Contas por situação (duas roscas)
  [["gSitRec", G.sitTipo.receber], ["gSitPag", G.sitTipo.pagar]].forEach(([id, d]) => {
    if (!el(id) || !d.fatias.length) return;
    new Chart(el(id), { type: "doughnut",
      data: { labels: d.fatias.map(x => x.situacao), datasets: [{ data: d.fatias.map(x => x.valor), backgroundColor: d.fatias.map(x => x.cor), borderColor: "#fff", borderWidth: 1,
        rotuloFora: true, tamRotulo: 11, corRotulo: i => d.fatias[i].cor, rotulo: i => d.fatias[i].pct >= 0.03 ? P(d.fatias[i].pct) : null }] },
      options: { cutout: "69%", radius: "75%", layout: { padding: 4 }, plugins: { legend: { display: false },
        tooltip: { callbacks: { label: c => `${c.label}: ${H(c.raw)} · ${P(d.fatias[c.dataIndex].pct)} · ${N(d.fatias[c.dataIndex].qtd)} lanç.` } } } } });
  });

  // 4. Contas em aberto por data de emissão (eixo Y fixo à esquerda, rolagem lateral)
  const AB = G.aberto;
  if (el("gAberto") && AB.dias.length) {
    const pos = AB.dias.map((_, i) => AB.series.reduce((s, x) => s + Math.max(0, x.valores[i]), 0));
    const neg = AB.dias.map((_, i) => AB.series.reduce((s, x) => s + Math.min(0, x.valores[i]), 0));
    const yMax = Math.max(0, ...pos), yMin = Math.min(0, ...neg);
    el("wAberto").style.width = `max(100%, ${Math.max(AB.dias.length * 56, 600)}px)`;
    const xAlto = { afterFit: s => { s.height = 36; } };
    const yAx = new Chart(el("gAbertoY"), { type: "bar", data: { labels: ["", ""], datasets: [{ data: [yMin, yMax * 1.08], backgroundColor: "transparent" }] },
      options: { layout: { padding: { top: 20, left: 4 } }, plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { ...xAlto, ticks: { display: false }, grid: { display: false }, border: { display: false } },
          y: { afterFit: s => { s.width = 60; }, ticks: { callback: v => V(v) }, grid: { display: false }, border: { color: MUTED } } } } });
    const ys = yAx.scales.y;
    new Chart(el("gAberto"), { type: "bar",
      data: { labels: AB.dias.map(d => [dmyc(d), ds(d)]), datasets: AB.series.map((s, i) => ({ label: s.rotulo, data: s.valores, backgroundColor: s.cor, stack: "a", chave: s.key,
        ...(i === AB.series.length - 1 && G.modoAb !== "ambos" ? { tamRotulo: 9, rotulo: j => AB.totais[j] ? V(AB.totais[j]) : null } : {}) })) },
      options: { interaction: { mode: "index", intersect: false }, layout: { padding: { top: 20, right: 8 } },
        plugins: { legend: { display: false }, tooltip: { position: "nearest", filter: c => c.raw !== 0, callbacks: {
          title: it => `${dmy(AB.dias[it[0].dataIndex])} · ${ds(AB.dias[it[0].dataIndex])}`,
          label: c => `${c.dataset.label}: ${H(c.raw)}`,
          labelColor: c => ({ borderColor: c.dataset.backgroundColor, backgroundColor: c.dataset.backgroundColor }),
          afterLabel: c => { const d = AB.dias[c.dataIndex], k = c.dataset.chave, l = (AB.detalhe[d][k] || []).map(([n, v, q]) => `   ${corta(n, 32)}${q > 1 ? ` (${q} títulos)` : ""}: ${H(v)}`);
            const o = (AB.outros[d] || {})[k]; if (o) l.push(`   + ${o[0]} outros: ${H(o[1])}`); return l; },
          footer: it => `Total do dia: ${H(AB.totais[it[0].dataIndex])}` } } },
        scales: { x: { ...xAlto, stacked: true, grid: grade(), border: { color: MUTED }, ticks: { autoSkip: false, maxRotation: 0, font: { size: 9 } } },
          y: { stacked: true, display: false, min: ys.min, max: ys.max, grid: grade({ zero: true }) } } } });
    const vistos = new Map(); AB.series.forEach(s => vistos.set(s.situacao, s.cor));
    el("lAberto").innerHTML = [...vistos].map(([s, c]) => `<span><i style="background:${c}"></i>${s}</span>`).join("");
    const p = new URLSearchParams(location.search), de = p.get("de"), ate = p.get("ate");
    el("pAberto").textContent = `${dmyc(de && p.get("at") !== "todos" ? de : AB.dias[0])} a ${dmyc(ate && p.get("at") !== "todos" ? ate : AB.dias[AB.dias.length - 1])}`;
  }

  // 5. Gastos por grupo (barras horizontais, cor fixa por grupo)
  const barrasH = (id, wrap, d, cor) => {
    if (!el(id)) return;
    if (!d.length) { el(wrap).hidden = true; const v = el("v" + id.slice(1)); if (v) v.hidden = false; return; }
    el(wrap).style.height = Math.max(200, d.length * 30 + 30) + "px";
    new Chart(el(id), { type: "bar",
      data: { labels: d.map(x => corta(x.nome, 30)), datasets: [{ data: d.map(x => x.valor), backgroundColor: d.map(x => x.cor || cor), borderRadius: { topRight: 3, bottomRight: 3 }, borderSkipped: "start",
        rotulo: i => `${V(d[i].valor)} · ${P(d[i].pct)}` }] },
      options: { indexAxis: "y", layout: { padding: { right: 130, left: 8 } }, plugins: { legend: { display: false },
          tooltip: { callbacks: { title: it => d[it[0].dataIndex].nome, label: c => `Valor: ${H(c.raw)} (${P(d[c.dataIndex].pct)})` } } },
        scales: { x: eixoV({ grid: grade() }), y: { afterFit: s => { s.width = 190; }, grid: { display: false }, border: { color: MUTED }, ticks: { autoSkip: false, font: { size: 11 } } } } } });
  };
  barrasH("gGastosGrupo", "wGastosGrupo", G.gastosGrupo, GASTO);

  // 6. Entradas por grupo → categoria (rosca em dois anéis + tabela; clicar foca um grupo)
  const EG = G.entradas;
  if (el("gEntradas") && EG.grupos.length) {
    const corG = i => SUN[i % SUN.length];
    let foco = null;
    document.querySelectorAll("#sun [data-sw]").forEach(s => s.style.background = corG(+s.dataset.sw));
    const fatiasCat = () => EG.grupos.flatMap((g, gi) => (foco !== null && foco !== gi) ? [] : g.categorias.map((c, ci) => ({ ...c, grupo: g.nome, gi,
      cor: clarear(corG(gi), Math.round(ci / Math.max(g.categorias.length, 1) * 55) / 100) })));
    const grafico = new Chart(el("gEntradas"), { type: "doughnut",
      data: { datasets: [
        { data: [], backgroundColor: [], borderColor: "#fff", borderWidth: 1, weight: 26, tamRotulo: 10, pesoRotulo: 600,
          rotulo: i => { const c = grafico.$cats[i]; const b = foco !== null ? c.pctGrupo : c.pctTotal; return b >= 0.03 ? P(b) : null; } },
        { data: [1], backgroundColor: ["transparent"], borderWidth: 0, weight: 2, hoverBackgroundColor: ["transparent"] },
        { data: EG.grupos.map(g => g.valor), backgroundColor: [], borderColor: "#fff", borderWidth: 1, weight: 24, tamRotulo: 10, pesoRotulo: 600,
          rotulo: i => EG.grupos[i].pct >= 0.03 ? P(EG.grupos[i].pct) : null } ] },
      options: { cutout: "39.5%", radius: "86%", plugins: { legend: { display: false }, tooltip: { filter: c => c.datasetIndex !== 1, callbacks: {
        title: it => { const c = it[0]; return c.datasetIndex === 0 ? `${grafico.$cats[c.dataIndex].grupo} › ${grafico.$cats[c.dataIndex].nome}` : EG.grupos[c.dataIndex].nome; },
        label: c => { const x = c.datasetIndex === 0 ? grafico.$cats[c.dataIndex] : EG.grupos[c.dataIndex];
          const l = [H(x.valor), `${P(c.datasetIndex === 0 ? x.pctTotal : x.pct)} do total de entradas`];
          if (c.datasetIndex === 0) l.push(`${P(x.pctGrupo)} dentro do grupo`); l.push(`${N(x.qtd)} lançamentos`); return l; } } } },
        onHover: (e, a) => { e.native.target.style.cursor = a.some(x => x.datasetIndex === 2) ? "pointer" : "default"; },
        onClick: (e, a) => { const x = a.find(x => x.datasetIndex === 2); if (x) alternar(x.index); } } });
    const desenhar = () => {
      const cats = fatiasCat(); grafico.$cats = cats;
      grafico.data.datasets[0].data = cats.map(c => c.valor); grafico.data.datasets[0].backgroundColor = cats.map(c => c.cor);
      grafico.data.datasets[2].backgroundColor = EG.grupos.map((_, i) => foco !== null && foco !== i ? clarear(corG(i), .7) : corG(i));
      grafico.update();
      const g = foco !== null ? EG.grupos[foco] : null;
      el("sunNome").textContent = g ? g.nome : "Entradas"; el("sunValor").textContent = V(g ? g.valor : EG.total);
      document.querySelectorAll("#sun tr.g").forEach(tr => { const i = +tr.dataset.g; tr.classList.toggle("on", foco === i); tr.classList.toggle("apagado", foco !== null && foco !== i); });
    };
    const alternar = i => { foco = foco === i ? null : i; desenhar(); };
    document.querySelectorAll("#sun tr.g").forEach(tr => {
      tr.addEventListener("click", () => alternar(+tr.dataset.g));
      tr.querySelector(".tg").addEventListener("click", e => { e.stopPropagation(); const b = e.currentTarget, aberto = b.textContent === "▾";
        b.textContent = aberto ? "▸" : "▾"; b.setAttribute("aria-label", aberto ? "Expandir" : "Recolher");
        document.querySelectorAll(`#sun tr.c[data-pai="${tr.dataset.g}"]`).forEach(c => c.hidden = aberto); });
    });
    desenhar();
  }

  // 7 e 9. Evolução dos gastos (barras empilhadas)
  const diaEvo = G.gEvo === "dia";
  const empilhado = (id, E, cor, totalNoTopo) => {
    if (!el(id)) return;
    if (!E.labels.length) { el(id).parentElement.outerHTML = '<p class="lv-vazio">Sem dados no filtro</p>'; return; }
    const labels = diaEvo ? E.chaves.map(dia2) : E.labels;
    new Chart(el(id), { type: "bar",
      data: { labels, datasets: E.series.map((s, i) => ({ label: s, data: E.valores[s], backgroundColor: cor(s, i), stack: "g",
        ...(totalNoTopo && i === E.series.length - 1 ? { rotulo: j => E.totais[j] ? V(E.totais[j]) : null } : {}) })) },
      options: { layout: { padding: { top: totalNoTopo ? 20 : 4 } }, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { filter: c => c.raw > 0, itemSort: (a, b) => b.raw - a.raw, callbacks: {
          title: it => diaEvo ? dmy(E.chaves[it[0].dataIndex]) : E.labels[it[0].dataIndex],
          label: c => `${c.dataset.label}: ${H(c.raw)} (${P(E.totais[c.dataIndex] ? c.raw / E.totais[c.dataIndex] : null)})`,
          labelColor: c => ({ borderColor: c.dataset.backgroundColor, backgroundColor: c.dataset.backgroundColor }),
          footer: totalNoTopo ? (it => `Total: ${H(E.totais[it[0].dataIndex])}`) : undefined } } },
        scales: { x: { ...eixoX(diaEvo, labels.length, diaEvo ? { ticks: { autoSkip: false, maxRotation: 0, font: { size: 9 } } } : {}), stacked: true }, y: { ...eixoV(), stacked: true } } } });
  };
  empilhado("gEvoGrupo", G.evoGrupo, s => G.corGrupo[s] || MUTED, false);
  empilhado("gEvoCat", G.evoCat, (s, i) => s === "Outros" ? MUTED : G.cat[i % G.cat.length], true);

  // 8. Categorias de gasto (colunas, eixo Y fixo, rolagem lateral, rótulo girado)
  const CT = G.cats;
  if (el("gCats")) {
    if (!CT.length) el("cCats").innerHTML = '<p class="lv-vazio">Sem dados no filtro</p>';
    else {
      const mx = Math.max(...CT.map(c => c.valor));
      el("wCats").style.width = `max(100%, ${CT.length * 56}px)`;
      const xAlto = { afterFit: s => { s.height = 120; } };
      new Chart(el("gCatsY"), { type: "bar", data: { labels: [""], datasets: [{ data: [0], backgroundColor: "transparent" }] },
        options: { layout: { padding: { top: 95, left: 4 } }, plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { ...xAlto, ticks: { display: false }, grid: { display: false }, border: { display: false } },
            y: { min: 0, max: mx, afterFit: s => { s.width = 60; }, ticks: { includeBounds: false, callback: v => V(v) }, grid: { display: false }, border: { color: MUTED } } } } });
      new Chart(el("gCats"), { type: "bar",
        data: { labels: CT.map(c => corta(c.nome, 22)), datasets: [{ data: CT.map(c => c.valor), backgroundColor: GASTO,
          rotuloGirado: true, rotulo: i => `${V(CT[i].valor)} · ${P(CT[i].pct)}` }] },
        options: { layout: { padding: { top: 95, right: 8 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => CT[it[0].dataIndex].nome,
            label: c => `${H(c.raw)} · ${P(CT[c.dataIndex].pct)} do total`, afterLabel: c => `${N(CT[c.dataIndex].qtd)} lançamento${CT[c.dataIndex].qtd === 1 ? "" : "s"}` } } },
          scales: { x: { ...xAlto, grid: { display: false }, border: { color: MUTED }, ticks: { autoSkip: false, maxRotation: 45, minRotation: 45, font: { size: 10 } } },
            y: { min: 0, max: mx, display: false, grid: grade() } } } });
    }
  }

  // 10. Clientes e fornecedores (lista rolável, 10 visíveis, eixo fixo embaixo) — em HTML, leve mesmo com centenas de nomes
  const rank = (id, d, cor) => {
    const box = el(id); if (!box) return;
    if (!d.length) { box.innerHTML = '<p class="lv-vazio">Sem dados no filtro</p>'; return; }
    const mx = Math.max(...d.map(x => x.valor)) || 1;
    const bruto = mx / 3, mag = Math.pow(10, Math.floor(Math.log10(bruto))), r = bruto / mag;
    const passo = (r > 5 ? 10 : r > 2 ? 5 : r > 1 ? 2 : 1) * mag;
    const ticks = []; for (let t = 0; t <= mx + passo * 0.999; t += passo) ticks.push(t);
    const top = ticks[ticks.length - 1] || mx;
    const linhas = d.map(x => `<div class="rk-l" title="${x.nome.replace(/"/g, "&quot;")}: ${H(x.valor)} (${P(x.pct)})"><span class="rk-n"><span>${corta(x.nome, 30)}</span></span>
      <span class="rk-b"><i style="width:${x.valor / top * 100}%;background:${cor}"></i><em style="left:calc(${x.valor / top * 100}% + 4px)">${V(x.valor)} · ${P(x.pct)}</em></span></div>`).join("");
    box.innerHTML = `<div class="rk"><div class="rk-scroll lv-thin">${linhas}</div>
      <div class="rk-eixo"><span class="rk-n"></span><span class="rk-b">${ticks.map(t => `<b style="left:${t / top * 100}%">${V(t)}</b>`).join("")}</span></div></div>`;
  };
  rank("rCli", G.cli, OK);
  rank("rForn", G.forn, GASTO);

  // ---------------- Filtros: todos os controles mexem nos parâmetros da URL (iguais em todos os cartões)
  const ir = mut => {
    const p = new URLSearchParams(location.search);
    mut(p); p.delete("p");
    try { sessionStorage.setItem("lvScroll", String(scrollY)); } catch (e) {}
    location.search = p.toString();
  };
  try { const y = sessionStorage.getItem("lvScroll"); if (y !== null && !location.hash) { sessionStorage.removeItem("lvScroll"); scrollTo(0, +y); } } catch (e) {}
  document.querySelectorAll("a[data-guarda]").forEach(a => a.addEventListener("click", () => { try { sessionStorage.setItem("lvScroll", String(scrollY)); } catch (e) {} }));
  const lista = (p, nome, vals) => { p.delete(nome); vals.forEach(v => p.append(nome, v)); };

  document.querySelectorAll("[data-campo]").forEach(s => s.addEventListener("change", () => ir(p => p.set(s.dataset.campo, s.value))));
  document.querySelectorAll("[data-busca]").forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") ir(p => { p.set("q", i.value.trim()); p.delete("lcat"); }); }));

  document.querySelectorAll("[data-periodo]").forEach(box => {
    const at = box.querySelector("[data-at]"), de = box.querySelector("[data-de]"), ate = box.querySelector("[data-ate]");
    at.addEventListener("change", () => ir(p => {
      if (at.value === "custom") { p.set("at", "custom"); p.set("de", de.value || box.dataset.min); p.set("ate", ate.value || box.dataset.max); p.delete("at"); return; }
      p.set("at", at.value); p.delete("de"); p.delete("ate");
    }));
    [de, ate].forEach(i => i.addEventListener("change", () => ir(p => { p.delete("at"); p.set("de", de.value); p.set("ate", ate.value); if (!de.value) p.delete("de"); if (!ate.value) p.delete("ate"); if (!de.value && !ate.value) p.set("at", "todos"); })));
    box.querySelector("[data-limpar-per]")?.addEventListener("click", () => ir(p => { p.set("at", "todos"); p.delete("de"); p.delete("ate"); }));
  });

  // Popovers: abre um por vez, fecha clicando fora ou com Esc; ao fechar, aplica se algo mudou
  const pops = [...document.querySelectorAll("details.lv-pop")];
  const fechar = d => { if (d.open) { d.open = false; d.dispatchEvent(new Event("fechou")); } };
  pops.forEach(d => d.addEventListener("toggle", () => {
    if (!d.open) return;
    pops.forEach(o => { if (o !== d && !o.contains(d)) fechar(o); });
    const c = d.querySelector(".lv-pop-c"); if (!c) return;   // não deixa o popover sair da tela
    const r = c.getBoundingClientRect();
    if (!d.classList.contains("dir") && r.right > document.documentElement.clientWidth - 8) d.classList.add("dir");
    else if (d.classList.contains("dir") && r.left < 8) d.classList.remove("dir");
  }));
  document.addEventListener("click", e => pops.forEach(d => { if (!d.contains(e.target)) fechar(d); }));
  document.addEventListener("keydown", e => { if (e.key === "Escape") pops.forEach(fechar); });

  document.querySelectorAll("[data-multi]").forEach(d => {
    const nome = d.dataset.multi, caixas = () => [...d.querySelectorAll(".lv-cmd input[type=checkbox]")];
    const inicial = caixas().filter(c => c.checked).map(c => c.value).join("|");
    d.querySelector("[data-limpa]").addEventListener("click", () => { caixas().forEach(c => c.checked = false); fechar(d); });
    d.querySelector("[data-filtra]").addEventListener("input", e => { const q = e.target.value.toLowerCase();
      caixas().forEach(c => c.parentElement.hidden = q && !c.parentElement.textContent.toLowerCase().includes(q)); });
    d.addEventListener("fechou", () => { const sel = caixas().filter(c => c.checked).map(c => c.value);
      if (sel.join("|") !== inicial) ir(p => { lista(p, nome, sel); if (nome === "cat") p.delete("lcat"); }); });
  });

  document.querySelectorAll("[data-status]").forEach(d => {
    const todas = d.dataset.todas ? d.dataset.todas.split("|") : [], restr = d.dataset.restringir ? d.dataset.restringir.split("|") : null;
    const caixas = () => [...d.querySelectorAll(".lv-lista input[type=checkbox]")];
    const atual = new URLSearchParams(location.search).getAll("st").filter(Boolean);
    const base = atual.length ? atual : todas.slice();   // "todos" = todas as situações
    const marcar = vals => caixas().forEach(c => c.checked = vals.includes(c.value));
    const selecao = () => { // junta o que está marcado com o que fica fora da lista (no filtro restrito)
      const marc = caixas().filter(c => c.checked).map(c => c.value);
      return restr ? [...new Set([...base.filter(s => !restr.includes(s)), ...marc])] : marc;
    };
    const inicial = JSON.stringify(selecao().sort());
    d.querySelector("[data-st-todos]").addEventListener("click", () => marcar(caixas().map(c => c.value)));
    d.querySelector("[data-st-limpar]").addEventListener("click", () => marcar([]));
    d.querySelectorAll("[data-st-lista]").forEach(b => b.addEventListener("click", () => marcar(b.dataset.stLista.split("|"))));
    d.addEventListener("fechou", () => { const sel = selecao();
      if (JSON.stringify([...sel].sort()) === inicial) return;
      ir(p => { const tudo = todas.every(s => sel.includes(s)); lista(p, "st", tudo ? [] : (sel.length ? sel : ["__nenhum__"])); }); });
  });
})();
