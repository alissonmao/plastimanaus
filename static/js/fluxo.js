// Entradas e Saídas base Omie — gráficos iguais ao Lovable (usa G, vindo da view, e os helpers de graficos.js).
(() => {
  const VERDE = "#00b050", VERMELHO = "#dc2626", TEAL = "#1f6f80", CINZA = G.cinza;
  const SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
  const rsCurto = v => (v < 0 ? "-R$ " : "R$ ") + curto(Math.abs(v));
  const pct = v => (v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
  const dma = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const diaSem = iso => SEMANA[new Date(iso + "T12:00:00").getDay()];
  const rotDia = iso => [`${iso.slice(8, 10)}/${iso.slice(5, 7)}`, diaSem(iso)];
  const el = id => document.getElementById(id);
  const grade = { color: "rgba(0,0,0,.07)", borderDash: [3, 3] };

  // Rótulos de valor (barras, pontos, fatias) e total no centro da rosca.
  Chart.register({
    id: "rotulos",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((ds, di) => {
        if (!ds.rotulo || !chart.isDatasetVisible(di)) return;
        chart.getDatasetMeta(di).data.forEach((e, i) => {
          const t = ds.rotulo(i, ds.data[i]);
          if (t == null || t === "") return;
          ctx.save();
          ctx.font = "10px system-ui,-apple-system,Segoe UI,Roboto,sans-serif";
          ctx.fillStyle = ds.corRotulo || "#1d1b18";
          if (e instanceof Chart.ArcElement) {
            const p = e.tooltipPosition(); ctx.fillStyle = "#fff"; ctx.font = "600 11px system-ui,sans-serif";
            ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(t, p.x, p.y);
          } else if (chart.options.indexAxis === "y") {
            ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(t, Math.max(e.x, e.base) + 4, e.y);
          } else if (ds.rotuloGirado) {
            ctx.translate(e.x, Math.min(e.y, e.base ?? e.y) - 4); ctx.rotate(-Math.PI / 2);
            ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(t, 0, 0);
          } else {
            ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(t, e.x, Math.min(e.y, e.base ?? e.y) - 6);
          }
          ctx.restore();
        });
      });
      const c = chart.options.plugins.centro;
      if (c) {
        const m = chart.getDatasetMeta(0).data[0]; if (!m) return;
        ctx.save(); ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillStyle = "#6f6a62"; ctx.font = "11px system-ui,sans-serif"; ctx.fillText(c[0], m.x, m.y - 9);
        ctx.fillStyle = "#1d1b18"; ctx.font = "600 13px system-ui,sans-serif"; ctx.fillText(c[1], m.x, m.y + 8);
        ctx.restore();
      }
    },
  });
  const eixoY = (extra = {}) => ({ grid: grade, ticks: { callback: v => rsCurto(v) }, ...extra });
  const largura = (wrap, n, px) => { if (wrap) wrap.style.width = `max(100%, ${n * px + 80}px)`; };

  // 1. Entradas x Gastos (barras + saldo tracejado + acumulados no eixo da direita)
  const S = G.serie, diario = G.modo === "dia";
  if (el("gSerie")) new Chart(el("gSerie"), {
    data: { labels: S.map(p => diario ? rotDia(p.chave) : p.label), datasets: [
      { type: "bar", label: "Entradas", data: S.map(p => p.entradas), backgroundColor: VERDE, yAxisID: "m", order: 3 },
      { type: "bar", label: "Gastos", data: S.map(p => p.gastos), backgroundColor: VERMELHO, yAxisID: "m", order: 3 },
      { type: "line", label: "Saldo", data: S.map(p => p.saldo), borderColor: "#7a8794", backgroundColor: "#7a8794", borderDash: [5, 4], borderWidth: 2, pointRadius: 2, yAxisID: "m", order: 1 },
      { type: "line", label: "Entradas acumuladas", data: S.map(p => p.entradasAcum), borderColor: VERDE, backgroundColor: VERDE, borderWidth: 2, pointRadius: 2, yAxisID: "a", order: 0 },
      { type: "line", label: "Gastos acumulados", data: S.map(p => p.gastosAcum), borderColor: VERMELHO, backgroundColor: VERMELHO, borderWidth: 2, pointRadius: 2, yAxisID: "a", order: 0 },
    ] },
    options: { interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { boxWidth: 12, font: { size: 12 }, sort: (a, b) => a.datasetIndex - b.datasetIndex } }, tooltip: { itemSort: (a, b) => a.datasetIndex - b.datasetIndex, callbacks: {
        title: it => diario ? dma(S[it[0].dataIndex].chave) : S[it[0].dataIndex].label,
        label: c => `${c.dataset.label === "Saldo" ? "Saldo do período" : c.dataset.label}: ${brl(c.raw)}`,
        afterBody: it => [`Saldo acumulado: ${brl(S[it[0].dataIndex].saldoAcum)}`] } } },
      scales: { x: { grid: grade, ticks: { autoSkip: false, maxRotation: 0, font: { size: diario ? 9 : 11 } } }, m: eixoY({ position: "left" }),
        a: eixoY({ position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Acumulado (R$)" } }) } },
  });

  // 2. Saldo acumulado (área). Diário: rótulos só no 1º, último, mínimo e máximo; mensal: todos se ≤ 16 pontos.
  const SA = G.saldo;
  if (el("gSaldo") && SA.length) {
    const vs = SA.map(p => p.v), mi = vs.indexOf(Math.min(...vs)), ma = vs.indexOf(Math.max(...vs));
    const marcar = G.saldoDia ? new Set([0, vs.length - 1, mi, ma]) : null;
    new Chart(el("gSaldo"), { type: "line",
      data: { labels: SA.map(p => G.saldoDia ? rotDia(p.chave) : p.label), datasets: [{ label: "Saldo acumulado", data: vs, borderColor: TEAL,
        backgroundColor: "rgba(31,111,128,.25)", fill: "origin", pointRadius: 2, tension: 0,
        rotulo: (i, v) => (marcar ? marcar.has(i) : vs.length <= 16) ? rsCurto(v) : null }] },
      options: { layout: { padding: { top: 22, right: 24 } }, plugins: { legend: { display: false }, tooltip: { callbacks: {
          title: it => G.saldoDia ? dma(SA[it[0].dataIndex].chave) : SA[it[0].dataIndex].label, label: c => `Saldo acumulado: ${brl(c.raw)}` } } },
        scales: { x: { grid: grade, ticks: { autoSkip: vs.length > 16, maxRotation: 0, font: { size: G.saldoDia ? 9 : 11 } } }, y: eixoY() } } });
  }

  // 3. Contas por situação (duas roscas)
  [["gSitRec", G.sitTipo.receber], ["gSitPag", G.sitTipo.pagar]].forEach(([id, d]) => {
    if (!el(id) || !d.fatias.length) return;
    new Chart(el(id), { type: "doughnut",
      data: { labels: d.fatias.map(x => x.situacao), datasets: [{ data: d.fatias.map(x => x.valor), backgroundColor: d.fatias.map(x => x.cor), borderColor: "#fff", borderWidth: 1,
        rotulo: i => d.fatias[i].pct >= 0.03 ? pct(d.fatias[i].pct) : null }] },
      options: { cutout: "52%", radius: "92%", plugins: { legend: { display: false }, centro: ["Total", rsCurto(d.total)],
        tooltip: { callbacks: { label: c => `${c.label}: ${brl(c.raw)} (${pct(d.fatias[c.dataIndex].pct)}) · ${d.fatias[c.dataIndex].qtd} contas` } } } } });
  });

  // 4. Contas em aberto por data de emissão, empilhado por situação (em "ambos", a pagar fica abaixo de zero)
  const AB = G.aberto;
  if (el("gAberto") && AB.dias.length) {
    largura(el("wAberto"), AB.dias.length, 56);
    new Chart(el("gAberto"), { type: "bar",
      data: { labels: AB.dias.map(rotDia), datasets: AB.series.map(s => ({ label: s.rotulo, data: s.valores, backgroundColor: s.cor, stack: "a", chave: s.key })) },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "top", align: "start", labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { filter: c => c.raw !== 0, callbacks: { title: it => `Emissão ${dma(AB.dias[it[0].dataIndex])}`,
            label: c => `${c.dataset.label}: ${brl(Math.abs(c.raw))}`,
            afterLabel: c => (AB.detalhe[AB.dias[c.dataIndex]][c.dataset.chave] || []).map(([n, v, q]) => `   ${n.slice(0, 40)}: ${brl(Math.abs(v))}${q > 1 ? ` (${q})` : ""}`),
            footer: it => `Total do dia: ${brl(AB.totais[it[0].dataIndex])}` } } },
        scales: { x: { stacked: true, grid: grade, ticks: { autoSkip: false, maxRotation: 0, font: { size: 9 } } }, y: eixoY({ stacked: true }) } } });
  }

  // 5. Gastos por grupo (barras horizontais coloridas por grupo)
  const barrasH = (id, wrap, d, cor, linha = 30, corte = 42) => {
    if (!el(id) || !d.length) return;
    el(wrap).style.height = Math.max(200, d.length * linha + 30) + "px";
    new Chart(el(id), { type: "bar",
      data: { labels: d.map(x => x.nome.length > corte ? x.nome.slice(0, corte - 1) + "…" : x.nome), datasets: [{ data: d.map(x => x.valor), backgroundColor: d.map(x => x.cor || cor),
        borderRadius: 3, rotulo: i => `${rsCurto(d[i].valor)} · ${pct(d[i].pct)}` }] },
      options: { indexAxis: "y", layout: { padding: { right: 110 } }, plugins: { legend: { display: false },
          tooltip: { callbacks: { title: it => d[it[0].dataIndex].nome, label: c => `${brl(c.raw)} (${pct(d[c.dataIndex].pct)})` } } },
        scales: { x: eixoY(), y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } } } } });
  };
  barrasH("gGastosGrupo", "wGastosGrupo", G.gastosGrupo, VERMELHO);

  // 6. Entradas por grupo → categoria (rosca em dois anéis: dentro grupos, fora categorias)
  const EG = G.entradas, PAL = ["#1f6f80", "#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#edc948", "#76b7b2", CINZA];
  if (el("gEntradas") && EG.grupos.length) {
    const corG = EG.grupos.map((_, i) => PAL[i % PAL.length]);
    const cats = EG.grupos.flatMap((g, gi) => g.categorias.map((c, ci) => ({ ...c, grupo: g.nome,
      cor: corG[gi] + ["ff", "cc", "99", "77", "55"][Math.min(ci, 4)] })));
    new Chart(el("gEntradas"), { type: "doughnut",
      data: { labels: cats.map(c => c.nome), datasets: [
        { data: cats.map(c => c.valor), backgroundColor: cats.map(c => c.cor), borderColor: "#fff", borderWidth: 1, nomes: cats, weight: 1,
          rotulo: i => cats[i].pctTotal >= 0.04 ? pct(cats[i].pctTotal) : null },
        { data: EG.grupos.map(g => g.valor), backgroundColor: corG, borderColor: "#fff", borderWidth: 2, nomes: EG.grupos, weight: 1.2,
          rotulo: i => EG.grupos[i].pct >= 0.05 ? pct(EG.grupos[i].pct) : null } ] },
      options: { cutout: "30%", plugins: { legend: { display: false }, centro: ["Total", rsCurto(EG.total)], tooltip: { callbacks: {
        label: c => { const x = c.dataset.nomes[c.dataIndex];
          return x.grupo ? [`${x.grupo} › ${x.nome}`, `${brl(x.valor)} · ${pct(x.pctGrupo)} do grupo · ${pct(x.pctTotal)} do total`]
                         : [`${x.nome}`, `${brl(x.valor)} · ${pct(x.pct)} · ${x.qtd} lançamentos`]; } } } } } });
    el("lEntradas").innerHTML = EG.grupos.map((g, gi) => `<li><i style="background:${corG[gi]}"></i><span><b>${g.nome}</b></span><b>${brl(g.valor)}</b><small>${pct(g.pct)}</small></li>` +
      g.categorias.slice(0, 6).map(c => `<li class="sub"><i></i><span>${c.nome}</span><span>${brl(c.valor)}</span><small>${pct(c.pctTotal)}</small></li>`).join("") +
      (g.categorias.length > 6 ? `<li class="sub"><i></i><span>+ ${g.categorias.length - 6} categorias</span></li>` : "")).join("") +
      `<li class="tot"><span>Total</span><b>${brl(EG.total)}</b><small>100%</small></li>`;
  }

  // 7 e 9. Evolução dos gastos (barras empilhadas)
  const diaEvo = G.gEvo === "dia";
  const empilhado = (id, E, cor, totalNoTopo) => {
    if (!el(id) || !E.labels.length) return;
    const labels = diaEvo ? E.labels.map((_, i) => E.chaves ? rotDia(E.chaves[i]) : E.labels[i]) : E.labels;
    new Chart(el(id), { type: "bar",
      data: { labels, datasets: E.series.map((s, i) => ({ label: s, data: E.valores[s], backgroundColor: cor(s, i), stack: "g",
        ...(totalNoTopo && i === E.series.length - 1 ? { rotulo: j => E.totais[j] ? rsCurto(E.totais[j]) : null } : {}) })) },
      options: { layout: { padding: { top: totalNoTopo ? 18 : 0 } }, interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } }, tooltip: { filter: c => c.raw > 0, itemSort: (a, b) => b.raw - a.raw, callbacks: {
          label: c => `${c.dataset.label}: ${brl(c.raw)} (${pct(E.totais[c.dataIndex] ? c.raw / E.totais[c.dataIndex] : 0)})`,
          footer: it => `Total: ${brl(E.totais[it[0].dataIndex])}` } } },
        scales: { x: { stacked: true, grid: grade, ticks: { autoSkip: E.labels.length > 16, maxRotation: 0, font: { size: diaEvo ? 9 : 11 } } }, y: eixoY({ stacked: true }) } } });
  };
  empilhado("gEvoGrupo", G.evoGrupo, s => G.corGrupo[s] || CINZA, false);
  empilhado("gEvoCat", G.evoCat, (s, i) => s === "Outros" ? CINZA : G.cat[i % G.cat.length], true);

  // 8. Categorias de gasto (colunas vermelhas, rolagem horizontal, rótulo girado)
  const CT = G.cats;
  if (el("gCats") && CT.length) {
    largura(el("wCats"), CT.length, 56);
    new Chart(el("gCats"), { type: "bar",
      data: { labels: CT.map(c => c.nome.length > 22 ? c.nome.slice(0, 21) + "…" : c.nome), datasets: [{ data: CT.map(c => c.valor), backgroundColor: VERMELHO, borderRadius: 3,
        rotuloGirado: true, rotulo: i => `${rsCurto(CT[i].valor)} · ${pct(CT[i].pct)}` }] },
      options: { layout: { padding: { top: 92 } }, plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => CT[it[0].dataIndex].nome,
          label: c => [`${brl(c.raw)} (${pct(CT[c.dataIndex].pct)})`, `${CT[c.dataIndex].qtd} lançamentos`] } } },
        scales: { x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 60, minRotation: 45, font: { size: 10 } } }, y: eixoY() } } });
  }

  // 10. Clientes e fornecedores (barras horizontais com rolagem)
  barrasH("gCli", "wCli", G.cli, VERDE, 26, 24);
  barrasH("gForn", "wForn", G.forn, VERMELHO, 26, 24);

  // Filtros: atalhos de período, envio automático, seleção múltipla
  const form = el("ff");
  document.querySelectorAll("select.auto").forEach(s => s.addEventListener("change", () => {
    if (s.id === "fAt" && s.value === "custom") return;
    if (s.id === "fAt") form.querySelectorAll("input.dt").forEach(i => i.value = "");
    form.requestSubmit();
  }));
  form.querySelectorAll("input.dt").forEach(i => i.addEventListener("change", () => { el("fAt").value = "custom"; }));
  document.querySelectorAll("details.multi").forEach(d => {
    const caixas = () => [...d.querySelectorAll(".lista input[type=checkbox]")];
    d.querySelector("[data-todos]")?.addEventListener("click", () => caixas().forEach(c => c.checked = false));
    d.querySelectorAll("[data-st]").forEach(b => b.addEventListener("click", () => {
      const v = b.dataset.st, lista = v === "todos" || v === "nenhum" ? [] : v.split("|");
      caixas().forEach(c => c.checked = lista.includes(c.value));
    }));
    d.querySelector(".filtra")?.addEventListener("input", e => { const q = e.target.value.toLowerCase();
      caixas().forEach(c => c.parentElement.hidden = q && !c.parentElement.textContent.toLowerCase().includes(q)); });
  });
  document.addEventListener("click", e => document.querySelectorAll("details.multi[open]").forEach(d => { if (!d.contains(e.target)) d.open = false; }));
})();
