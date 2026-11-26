// Biblioteca comum das telas com visual do Lovable (Faturamento base Omie e Chão de Fábrica - Produção).
// Formatação, períodos, componentes de filtro (popover com busca), painéis e gráficos Chart.js com o estilo do Recharts.
const LV = (() => {
  const FONTE = '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif';
  const C = {
    ok: "#00b050", loss: "#dc2626", destr: "#e7000b", muted: "#54676e", border: "#e2e8f0", fg: "#020618", card: "#fff",
    chart: ["#186575", "#d98a2e", "#d24c49", "#428252", "#7e90ae"],   // --chart-1..5
    saldo: "#1d4ed8",
  };
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const SEM = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  const n1 = v => v.toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const fmt = {
    curto: v => { const a = Math.abs(v); return a >= 1e6 ? `${n1(v / 1e6)} mi` : a >= 1e3 ? `${n1(v / 1e3)} mil` : v.toLocaleString("pt-BR", { maximumFractionDigits: 0 }); },
    brl: v => v == null ? "" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    num: (v, a = 2, b) => v == null || isNaN(v) ? "" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: a, minimumFractionDigits: b ?? 0 }),
    pct: v => v == null || isNaN(v) ? "—" : (v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + "%",
    data: iso => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "",
    dia: iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`,
    sem: iso => SEM[new Date(iso + "T12:00:00").getDay()],
  };
  // Períodos (iguais ao Lovable)
  const chave = (d, g) => {
    if (g === "dia") return d.slice(0, 10); if (g === "mes") return d.slice(0, 7); if (g === "ano") return d.slice(0, 4);
    if (g === "trimestre") return `${d.slice(0, 4)}-T${Math.floor((+d.slice(5, 7) - 1) / 3) + 1}`;
    const [a, m, dd] = d.slice(0, 10).split("-").map(Number), x = new Date(Date.UTC(a, m - 1, dd));
    x.setUTCDate(x.getUTCDate() - (x.getUTCDay() + 6) % 7); return x.toISOString().slice(0, 10);
  };
  const rotulo = (k, g) => g === "mes" ? `${MESES[+k.slice(5, 7) - 1]}/${k.slice(2, 4)}` : g === "ano" ? k.slice(0, 4)
    : g === "trimestre" ? `${k.slice(6)}º tri/${k.slice(2, 4)}` : g === "semana" ? `Sem ${fmt.data(k)}` : fmt.data(k);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const corta = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const semAcento = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const vazio = (t = "Sem dados no filtro") => `<p class="lv-vazio">${t}</p>`;
  const chev = '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg>';
  const panel = (titulo, corpo, { acoes = "", classe = "", id = "" } = {}) =>
    `<section class="lv-panel ${classe}" ${id ? `id="${id}"` : ""}><header><h2>${esc(titulo)}</h2>${acoes}</header><div class="corpo">${corpo}</div></section>`;
  const kpi = (rot, val, { sub = "", tom = "", grande = true, subCor = "" } = {}) =>
    `<div class="lv-kpi"><div class="rot">${esc(rot)}</div><div class="val ${tom} ${grande ? "" : "lg"}">${val}</div>${sub ? `<div class="sub" ${subCor ? `style="color:${subCor}"` : ""}>${sub}</div>` : ""}</div>`;
  const canvas = (id, h) => `<div class="lv-chart" style="height:${h}px"><canvas id="${id}"></canvas></div>`;

  // ---- Chart.js com o visual do Recharts
  const graficos = new Map();
  const destruir = prefixo => { for (const [k, g] of graficos) if (!prefixo || k.startsWith(prefixo)) { g.destroy(); graficos.delete(k); } };
  const novo = (id, cfg) => { const el = document.getElementById(id); if (!el) return null; graficos.get(id)?.destroy(); const g = new Chart(el, cfg); graficos.set(id, g); return g; };
  if (window.Chart) {
    Chart.defaults.font.family = FONTE; Chart.defaults.font.size = 11; Chart.defaults.color = C.muted;
    Chart.defaults.maintainAspectRatio = false; Chart.defaults.animation = false;
    Object.assign(Chart.defaults.plugins.tooltip, { backgroundColor: "#fff", borderColor: C.border, borderWidth: 1, titleColor: C.fg, bodyColor: C.fg,
      footerColor: C.fg, padding: 10, cornerRadius: 6, boxPadding: 4, usePointStyle: true,
      titleFont: { family: FONTE, size: 12, weight: "600" }, bodyFont: { family: FONTE, size: 12 }, footerFont: { family: FONTE, size: 12, weight: "600" } });
    Chart.defaults.plugins.legend.position = "bottom";
    Chart.defaults.plugins.legend.labels = { ...Chart.defaults.plugins.legend.labels, boxWidth: 12, boxHeight: 10, font: { family: FONTE, size: 11 }, color: C.muted };
    Chart.register({ id: "lvRotulos", afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((d, di) => {
        if (!d.rotulo || !chart.isDatasetVisible(di)) return;
        chart.getDatasetMeta(di).data.forEach((e, i) => {
          const t = d.rotulo(i, d.data[i]); if (t == null || t === "") return;
          ctx.save(); ctx.font = `${d.pesoRotulo || 400} ${d.tamRotulo || 10}px ${FONTE}`; ctx.fillStyle = d.corRotulo ? d.corRotulo(i) : C.fg;
          const halo = typeof d.halo === "function" ? d.halo(i) : d.halo;
          if (halo) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 3; ctx.lineJoin = "round"; }
          const escreve = (s, x, y) => { if (halo) ctx.strokeText(s, x, y); ctx.fillText(s, x, y); };
          const linhas = Array.isArray(t) ? t : [t];
          if (e instanceof Chart.ArcElement) {
            const r = d.raioRotulo ? d.raioRotulo(i, e) : (e.innerRadius + e.outerRadius) / 2, a = (e.startAngle + e.endAngle) / 2;
            ctx.textAlign = "center"; ctx.textBaseline = "middle";
            linhas.forEach((s, k) => escreve(s, e.x + Math.cos(a) * r, e.y + Math.sin(a) * r + (k - (linhas.length - 1) / 2) * 12));
          } else if (chart.options.indexAxis === "y") {
            ctx.textAlign = "left"; ctx.textBaseline = "middle"; escreve(linhas[0], Math.max(e.x, e.base) + 4, e.y + 1);
          } else if (d.rotuloAbaixo) {
            ctx.textAlign = "center"; ctx.textBaseline = "top"; escreve(linhas[0], e.x, e.y + (d.offRotulo ?? 8));
          } else {
            ctx.textAlign = "center"; ctx.textBaseline = "bottom";
            const topo = e.base != null ? Math.min(e.y, e.base) : e.y;
            linhas.forEach((s, k) => escreve(s, e.x, topo - (d.offRotulo ?? 6) - (linhas.length - 1 - k) * 12));
          }
          ctx.restore();
        });
      });
    } });
    // linhas de referência (x por rótulo, y por valor)
    Chart.register({ id: "lvRef", afterDatasetsDraw(chart, _a, o) {
      const refs = chart.options.plugins.lvRef?.linhas || []; if (!refs.length) return;
      const { ctx, chartArea: ca } = chart;
      refs.forEach(r => {
        ctx.save(); ctx.setLineDash(r.dash || [4, 4]); ctx.strokeStyle = r.cor || C.muted; ctx.globalAlpha = r.alpha ?? 1; ctx.lineWidth = 1;
        if (r.x != null) {
          const sx = chart.scales.x, i = typeof r.x === "number" ? r.x : chart.data.labels.findIndex(l => (Array.isArray(l) ? l.join(" ") : l) === r.x);
          if (i < 0) { ctx.restore(); return; }
          const px = i - (r.inicio ? .5 : 0); const x = sx.getPixelForValue(px >= 0 ? px : 0) - (r.inicio && i === 0 ? sx.width / chart.data.labels.length / 2 : 0);
          ctx.beginPath(); ctx.moveTo(x, ca.top); ctx.lineTo(x, ca.bottom); ctx.stroke();
        } else if (r.xv != null) {
          const x = chart.scales.x.getPixelForValue(r.xv); ctx.beginPath(); ctx.moveTo(x, ca.top); ctx.lineTo(x, ca.bottom); ctx.stroke();
          if (r.rot) { ctx.setLineDash([]); ctx.fillStyle = C.muted; ctx.font = `11px ${FONTE}`; ctx.textAlign = "center"; ctx.fillText(r.rot, x, ca.top - 4); }
        } else {
          const y = chart.scales[r.eixo || "y"].getPixelForValue(r.y); ctx.beginPath(); ctx.moveTo(ca.left, y); ctx.lineTo(ca.right, y); ctx.stroke();
          if (r.rot) { ctx.setLineDash([]); ctx.globalAlpha = r.alphaRot ?? 1; ctx.fillStyle = C.muted; ctx.font = `10px ${FONTE}`; ctx.textAlign = "left";
            ctx.strokeStyle = "#fff"; ctx.lineWidth = 3; const yy = r.rotAbaixo ? y - 4 : y + 12; ctx.strokeText(r.rot, ca.left + 4, yy); ctx.fillText(r.rot, ca.left + 4, yy); }
        }
        ctx.restore();
      });
    } });
  }
  const grade = (extra = {}) => ({ color: C.border, borderDash: [3, 3], drawTicks: false, ...extra });
  const eixo = (fmtTick = fmt.curto, extra = {}) => ({ grid: grade(), border: { color: C.muted }, ticks: { callback: v => fmtTick(v), padding: 6 }, ...extra });
  const eixoX = (extra = {}) => ({ grid: grade(), border: { color: C.muted }, ticks: { maxRotation: 0, padding: 6, autoSkip: true }, ...extra });
  const bolinha = c => ({ borderColor: c.dataset.borderColor && c.dataset.type === "line" ? c.dataset.borderColor : c.dataset.backgroundColor, backgroundColor: c.dataset.type === "line" ? c.dataset.borderColor : c.dataset.backgroundColor });
  // mistura cor hex com branco ou preto (para tons de categoria)
  const misturar = (hex, q, com = 255) => { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).map(x => Math.round(x + (com - x) * q)); return `rgb(${c.join(",")})`; };
  const hsl = (h, s, l) => `hsl(${h} ${s}% ${l}%)`;
  // padrão hachurado (para "perdas" e cores desconhecidas)
  const hachura = (fundo, risco, alpha = 1) => {
    const c = document.createElement("canvas"); c.width = c.height = 8; const x = c.getContext("2d");
    x.globalAlpha = alpha; x.fillStyle = fundo; x.fillRect(0, 0, 8, 8); x.globalAlpha = 1; x.strokeStyle = risco; x.lineWidth = 2;
    x.beginPath(); x.moveTo(-2, 2); x.lineTo(2, -2); x.moveTo(0, 8); x.lineTo(8, 0); x.moveTo(6, 10); x.lineTo(10, 6); x.stroke();
    return x.createPattern(c, "repeat");
  };

  // ---- Seleção múltipla com busca (popover). opcoes: [{v, t, cor}] ; onChange(listaSelecionada)
  // modo "barra": botão largo com o texto da seleção; "mini": "Rótulo: N"
  let seq = 0;
  const multi = ({ opcoes, sel, onChange, texto, busca = true, todos = true, limpar = true, largura = 288, todosTxt = "Todos", limparTxt = "Limpar", alinhar = "" }) => {
    const id = "lvm" + (++seq);
    const html = `<details class="lv-pop ${alinhar}" id="${id}" style="display:block"><summary class="lv-btn lg w-full"><span class="trunc">${esc(texto(sel))}</span>${chev}</summary>
      <div class="lv-pop-c p0" style="width:${largura}px">${busca ? '<input type="search" class="lv-busca" placeholder="Buscar..." data-f>' : ""}
      <div class="lv-cmd lv-thin">${todos ? `<div class="todos" data-t>${todosTxt}</div>` : ""}${limpar ? `<div class="todos" data-l>${limparTxt}</div>` : ""}
      ${opcoes.map((o, i) => `<label><input type="checkbox" data-i="${i}" ${sel.includes(o.v) ? "checked" : ""}>${o.cor ? `<span class="lv-sq" style="background:${o.cor}"></span>` : ""}<span>${esc(o.t ?? o.v)}</span></label>`).join("")}
      ${opcoes.length ? "" : vazio()}</div></div></details>`;
    const ligar = () => {
      const d = document.getElementById(id); if (!d) return;
      const caixas = () => [...d.querySelectorAll("input[data-i]")];
      const atual = () => caixas().filter(c => c.checked).map(c => opcoes[+c.dataset.i].v);
      const mudou = () => { d.querySelector("summary .trunc").textContent = texto(atual()); onChange(atual()); };
      caixas().forEach(c => c.addEventListener("change", mudou));
      d.querySelector("[data-t]")?.addEventListener("click", () => { caixas().forEach(c => c.checked = true); mudou(); });
      d.querySelector("[data-l]")?.addEventListener("click", () => { caixas().forEach(c => c.checked = false); mudou(); });
      d.querySelector("[data-f]")?.addEventListener("input", e => { const q = semAcento(e.target.value);
        caixas().forEach(c => c.parentElement.hidden = q && !semAcento(c.parentElement.textContent).includes(q)); });
    };
    return { html, ligar };
  };
  // Popovers: um aberto por vez, fecha clicando fora / Esc; ajusta para não sair da tela
  document.addEventListener("click", e => document.querySelectorAll("details.lv-pop[open]").forEach(d => { if (!d.contains(e.target)) d.open = false; }));
  document.addEventListener("keydown", e => { if (e.key === "Escape") document.querySelectorAll("details.lv-pop[open]").forEach(d => d.open = false); });
  document.addEventListener("toggle", e => {
    const d = e.target; if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("lv-pop") || !d.open) return;
    document.querySelectorAll("details.lv-pop[open]").forEach(o => { if (o !== d && !o.contains(d)) o.open = false; });
    const c = d.querySelector(".lv-pop-c"); if (!c) return; const r = c.getBoundingClientRect();
    if (!d.classList.contains("dir") && r.right > document.documentElement.clientWidth - 8) d.classList.add("dir");
    else if (d.classList.contains("dir") && r.left < 8) d.classList.remove("dir");
  }, true);

  // ---- Lista rolável com barras (ScrollRankBar do Lovable), em HTML
  const rank = (d, { cor, rowH = 30, visivel = 10, yW = 190, maxC = 30, direita = 130, rotulo, corItem, titulo }) => {
    if (!d.length) return vazio();
    const vals = d.map(x => x.valor), mx = Math.max(0, ...vals) || 1, mn = Math.min(0, ...vals), amp = mx - mn || 1;
    const bruto = amp / 3, mag = Math.pow(10, Math.floor(Math.log10(bruto))), r = bruto / mag, passo = (r > 5 ? 10 : r > 2 ? 5 : r > 1 ? 2 : 1) * mag;
    const ticks = []; for (let t = Math.floor(mn / passo) * passo; t <= mx + 1e-9; t += passo) ticks.push(t);
    const lo = Math.min(mn, ticks[0]), hi = Math.max(mx, ticks[ticks.length - 1]), sp = hi - lo || 1, x0 = (0 - lo) / sp * 100;
    const linhas = d.map(x => { const w = Math.abs(x.valor) / sp * 100, left = x.valor >= 0 ? x0 : x0 - w;
      return `<div class="rk-l" style="height:${rowH}px;grid-template-columns:${yW}px minmax(0,1fr)" title="${esc(titulo ? titulo(x) : `${x.nome}: ${fmt.brl(x.valor)}`)}"><span class="rk-n"><span>${esc(corta(x.nome, maxC))}</span></span>
      <span class="rk-b" style="margin-right:${direita}px"><i style="left:${left}%;width:${w}%;background:${corItem ? corItem(x) : cor}"></i><em style="left:calc(${left + w}% + 4px)">${esc(rotulo(x))}</em></span></div>`; }).join("");
    return `<div class="rk"><div class="rk-scroll lv-thin" style="max-height:${visivel * rowH + 10}px">${linhas}</div>
      <div class="rk-eixo" style="grid-template-columns:${yW}px minmax(0,1fr)"><span class="rk-n"></span><span class="rk-b" style="margin-right:${direita}px">${ticks.map(t => `<b style="left:${(t - lo) / sp * 100}%">${fmt.curto(t)}</b>`).join("")}</span></div></div>`;
  };

  // ---- Rosca com tabela (ProductColorCharts do Lovable)
  // produto: {name, total, slices:[{name,value,percent}]}, p: {subtitulo, coluna, colunaValor, unidade, fmtValor, colorFor(nome)->{fill,label,halo,hatch}, rotulosValor, minPct, outline}
  const roscaTabela = (id, produto, p) => {
    const fv = p.fmtValor || (v => fmt.num(v, 0));
    const tem = produto.slices.some(s => s.value !== 0);
    const corpo = tem ? `<div class="lv-chart" style="height:${p.rotulosValor ? 320 : 240}px"><canvas id="${id}"></canvas>
      <div class="lv-centro"><span class="num" style="font-size:${p.rotulosValor ? 11 : 14}px;font-weight:600">${esc(fv(produto.total))}</span><span style="font-size:11px;color:var(--lv-muted-fg)">${esc(p.unidade || "kg OK")}</span><span style="font-size:12px;font-weight:500;max-width:112px;text-align:center;overflow-wrap:anywhere">${esc(produto.name)}</span></div></div>`
      : `<p class="lv-vazio" style="height:240px;display:flex;align-items:center;justify-content:center">${p.vazio || "Sem produção OK no período selecionado."}</p>`;
    const tabela = `<table class="lv-mini"><thead><tr><th>${esc(p.coluna)}</th><th class="r">${esc(p.colunaValor || "kg OK")}</th><th class="r">%</th></tr></thead><tbody>
      ${produto.slices.map(s => { const c = p.colorFor(s.name); return `<tr><td><span class="lv-bol" style="background:${c.fill};opacity:${c.hatch ? .5 : 1};border-color:${p.outline || "#64748b"}"></span>${esc(s.name)}</td><td class="r num">${esc(fv(s.value))}</td><td class="r num">${fmt.pct(s.percent / 100)}</td></tr>`; }).join("")}</tbody>
      <tfoot><tr><td>Total</td><td class="r num">${esc(fv(produto.total))}</td><td class="r num">${produto.total ? "100,0%" : "—"}</td></tr></tfoot></table>`;
    const html = `<article class="lv-art"><h3>${esc(produto.name)}</h3><p class="sub">${esc(p.subtitulo)}</p>${p.alternativo || corpo}${tabela}</article>`;
    const desenhar = () => {
      if (!tem || p.alternativo) return;
      const fat = produto.slices.filter(s => s.value > 0);
      const el = document.getElementById(id); if (!el) return;
      novo(id, { type: "doughnut", data: { labels: fat.map(s => s.name), datasets: [{ data: fat.map(s => s.value),
        backgroundColor: fat.map(s => { const c = p.colorFor(s.name); return c.hatch ? hachura(c.fill, p.outline || "#94a3b8", .5) : c.fill; }),
        borderColor: p.outline || "#64748b", borderWidth: 1.5, halo: i => !!p.colorFor(fat[i].name).halo, tamRotulo: p.rotulosValor ? 9 : 11, pesoRotulo: 600,
        corRotulo: i => p.colorFor(fat[i].name).label || C.fg,
        raioRotulo: (i, e) => { const k = (e.outerRadius) / (p.rotulosValor ? 140 : 96); const pc = fat[i].percent;
          return (p.rotulosValor ? (pc < 8 ? (i % 2 ? 130 : 82) : 106) : 79) * k; },
        rotulo: i => fat[i].percent < (p.minPct ?? 4) ? null : (p.rotulosValor ? [fv(fat[i].value), fmt.pct(fat[i].percent / 100)] : fmt.pct(fat[i].percent / 100)) }] },
        options: { rotation: 0, cutout: p.rotulosValor ? "44%" : "64%", radius: p.rotulosValor ? 140 : 96, layout: { padding: 0 },
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${fv(c.raw)}${p.fmtValor ? "" : " kg"} (${fmt.pct(fat[c.dataIndex].percent / 100)})` } } } } });
    };
    return { html, desenhar };
  };

  // ---- Tabela (erp-table)
  const tabela = (cab, linhas, { maxH = "70vh", total } = {}) =>
    `<div class="lv-tabela lv-thin" style="max-height:${maxH}"><table><thead><tr>${cab.map(c => `<th class="${c.r ? "r" : ""}">${c.t}</th>`).join("")}</tr></thead><tbody>${linhas.join("")}${total || ""}</tbody></table></div>`;

  // ---- Excel (SheetJS sob demanda)
  const excel = async (linhas, nome) => {
    if (!window.XLSX) await new Promise((ok, erro) => { const s = document.createElement("script"); s.src = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"; s.onload = ok; s.onerror = erro; document.head.appendChild(s); });
    const ws = XLSX.utils.json_to_sheet(linhas), wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, "Dados"); XLSX.writeFile(wb, `${nome}.xlsx`);
  };
  // desempacota colunas {cols:[...], dic:[...], strs:[idx de colunas texto], rows:[[...]]}
  const desempacotar = P => P.rows.map(r => { const o = {}; P.cols.forEach((c, i) => { const v = r[i]; o[c] = P.strs.includes(i) ? (v == null ? null : P.dic[v]) : v; }); return o; });
  return { C, fmt, chave, rotulo, esc, corta, semAcento, vazio, chev, panel, kpi, canvas, destruir, novo, grade, eixo, eixoX, bolinha, misturar, hsl, hachura, multi, rank, roscaTabela, tabela, excel, desempacotar, MESES };
})();
