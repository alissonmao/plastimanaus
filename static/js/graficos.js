// Helpers de gráficos (Chart.js) usados pelas telas do ERP.
const PALETA = ["#9a7a1c","#3f8f4a","#2f80ed","#f2994a","#9b51e0","#eb5757","#27ae60","#56ccf2","#f2c94c","#d86dcd","#828282","#219653","#bb6bd9"];
const brl = v => v == null ? "" : v.toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const n2 = v => v == null ? "" : v.toLocaleString("pt-BR",{maximumFractionDigits:2});
const curto = v => { const a=Math.abs(v); return a>=1e6?(v/1e6).toLocaleString("pt-BR",{maximumFractionDigits:1})+" mi":a>=1e3?(v/1e3).toLocaleString("pt-BR",{maximumFractionDigits:1})+" mil":n2(v); };
Chart.defaults.font.family = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif";
Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#64746b";
Chart.defaults.maintainAspectRatio = false;

function barras(id, labels, series, opts = {}) {
  const fmt = opts.moeda ? brl : n2;
  return new Chart(document.getElementById(id), {
    type: opts.horizontal ? "bar" : "bar",
    data: { labels, datasets: series.map((s, i) => ({ label: s.nome, data: s.valores, backgroundColor: s.cor || PALETA[i % PALETA.length], stack: opts.empilhado ? "s" : undefined, type: s.tipo, yAxisID: s.eixo || "y", borderColor: s.cor || PALETA[i % PALETA.length], tension: .3 })) },
    options: { indexAxis: opts.horizontal ? "y" : "x", interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmt(c.raw)}` } }, legend: { display: series.length > 1 } },
      scales: { x: { stacked: !!opts.empilhado, ticks: opts.horizontal ? { callback: v => curto(v) } : {} },
                y: { stacked: !!opts.empilhado, ticks: opts.horizontal ? {} : { callback: v => curto(v) } },
                ...(opts.y2 ? { y2: { position: "right", grid: { drawOnChartArea: false }, ticks: { callback: v => n2(v) } } } : {}) } } });
}
function rosca(id, labels, valores, opts = {}) {
  const fmt = opts.moeda ? brl : n2;
  const tot = valores.reduce((a, b) => a + b, 0);
  return new Chart(document.getElementById(id), { type: "doughnut",
    data: { labels, datasets: [{ data: valores, backgroundColor: labels.map((_, i) => PALETA[i % PALETA.length]) }] },
    options: { cutout: "60%", plugins: { legend: { position: "right" }, tooltip: { callbacks: { label: c => `${c.label}: ${fmt(c.raw)} (${tot ? (c.raw / tot * 100).toFixed(1) : 0}%)` } } } } });
}
