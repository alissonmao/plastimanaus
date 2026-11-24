/* Voz da Secretaria: ditado (Diário) e a Angel no site.
   Fase 1: aperta e fala. Fase 2: modo conversa — escuta "Angel", responde em voz e pode ser interrompida falando. */
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANG = 'pt-BR';

  // ---------- Ditado num campo de texto
  window.Ditado = function (botao, campo, aoUsar) {
    if (!botao) return;
    if (!SR) { botao.title = 'Este navegador não reconhece voz (use Chrome, Edge ou Safari)'; botao.disabled = true; return; }
    let rec = null, base = '';
    botao.addEventListener('click', () => {
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = LANG; rec.interimResults = true; rec.continuous = true;
      base = campo.value ? campo.value.replace(/\s*$/, ' ') : '';
      rec.onresult = (e) => { let t = ''; for (const r of e.results) t += r[0].transcript; campo.value = base + t; if (aoUsar) aoUsar(); };
      rec.onend = () => { rec = null; botao.classList.remove('ouvindo'); botao.textContent = '🎙️ Ditar'; };
      rec.onerror = () => {};
      rec.start(); botao.classList.add('ouvindo'); botao.textContent = '⏹ Parar';
    });
  };

  // ---------- Angel
  document.addEventListener('DOMContentLoaded', () => {
    const fab = document.getElementById('angel-fab');
    if (!fab) return;
    const mic = fab.querySelector('.angel-mic'), balao = fab.querySelector('.angel-balao'), log = fab.querySelector('.angel-log'),
      status = fab.querySelector('.angel-status'), chkConversa = fab.querySelector('.angel-conversa');
    let historico = JSON.parse(sessionStorage.getItem('angel-hist') || '[]');
    let audio = null, ouvindo = null, conversa = sessionStorage.getItem('angel-conversa') === '1', ocupado = false;
    chkConversa.checked = conversa;

    function mostrar(quem, texto) {
      const d = document.createElement('div'); d.className = 'angel-msg ' + quem; d.textContent = texto; log.appendChild(d); log.scrollTop = log.scrollHeight;
    }
    historico.slice(-6).forEach(m => mostrar(m.role === 'user' ? 'eu' : 'ela', m.content));
    function abrir() { balao.hidden = false; }
    fab.querySelector('.angel-fechar').onclick = () => { balao.hidden = true; pararTudo(); setConversa(false); };
    function st(t) { status.textContent = t || ''; }

    function pararFala() { if (audio) { audio.pause(); audio = null; } if (window.speechSynthesis) speechSynthesis.cancel(); }
    function pararTudo() { pararFala(); if (ouvindo) { try { ouvindo.abort(); } catch (e) {} ouvindo = null; } mic.classList.remove('ouvindo'); }

    async function falar(texto) {
      pararFala();
      try {
        const r = await fetch(fab.dataset.voz, { method: 'POST', headers: { 'X-CSRFToken': fab.dataset.csrf, 'Content-Type': 'application/json' }, body: JSON.stringify({ texto }) });
        if (!r.ok) throw new Error('sem voz');
        const url = URL.createObjectURL(await r.blob());
        audio = new Audio(url);
        await new Promise((ok) => { audio.onended = ok; audio.onerror = ok; audio.onpause = ok; audio.play().catch(ok); });
      } catch (e) {
        if (!window.speechSynthesis) return;   // último recurso: voz do próprio navegador
        await new Promise((ok) => { const u = new SpeechSynthesisUtterance(texto); u.lang = LANG; u.onend = ok; u.onerror = ok; speechSynthesis.speak(u); });
      }
      audio = null;
    }

    async function enviar(texto) {
      if (!texto.trim()) return;
      abrir(); mostrar('eu', texto); historico.push({ role: 'user', content: texto }); ocupado = true; st('Pensando…');
      try {
        const r = await fetch(fab.dataset.url, { method: 'POST', headers: { 'X-CSRFToken': fab.dataset.csrf, 'Content-Type': 'application/json' },
          body: JSON.stringify({ texto, historico: historico.slice(-10, -1) }) });
        const j = await r.json();
        const resp = j.resposta || j.erro || 'Não consegui responder.';
        mostrar('ela', resp); historico.push({ role: 'assistant', content: resp });
        sessionStorage.setItem('angel-hist', JSON.stringify(historico.slice(-20)));
        st(conversa ? 'Falando… (fale para interromper)' : 'Falando…');
        if (conversa) escutarInterrupcao();
        await falar(j.falar || resp);
        if (j.recarregar) setTimeout(() => location.reload(), 300);
      } catch (e) { mostrar('ela', 'Falha de conexão.'); }
      ocupado = false; st('');
      if (conversa) escutar(false);
    }

    // Fase 1: aperta e fala
    function escutar(clicado) {
      if (!SR) { abrir(); st('Este navegador não reconhece voz. Use Chrome, Edge ou Safari.'); return; }
      if (ouvindo) { ouvindo.stop(); return; }
      pararFala();
      const rec = new SR(); rec.lang = LANG; rec.interimResults = true; rec.continuous = conversa && !clicado;
      let final = '', acordou = !conversa || clicado, inicio = 0;
      const WAKE = /\b(angel|anjo|ângel|êngel|enjoy|ângela)\b[\s,.!]*/i;
      rec.onresult = (e) => {
        let parcial = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) final += e.results[i][0].transcript + ' '; else parcial += e.results[i][0].transcript;
        }
        const tudo = final + parcial;
        if (!acordou) {   // Fase 2: palavra de ativação "Angel"
          const m = tudo.match(WAKE);
          if (!m) { if (final.length > 300) final = ''; return; }
          acordou = true; inicio = m.index + m[0].length; abrir(); st('Ouvindo…');
        }
        st('🎙️ ' + tudo.slice(inicio).trim());
        if (conversa && !clicado && e.results[e.results.length - 1].isFinal && final.slice(inicio).trim()) rec.stop();
      };
      rec.onend = () => {
        ouvindo = null; mic.classList.remove('ouvindo');
        const pedido = final.slice(inicio).trim();
        if (acordou && pedido) enviar(pedido);
        else if (conversa && !ocupado) setTimeout(() => escutar(false), 250);
        else st('');
      };
      rec.onerror = (e) => { if (e.error === 'not-allowed') { setConversa(false); st('Libere o microfone no navegador.'); } };
      ouvindo = rec; rec.start(); mic.classList.add('ouvindo');
      st(acordou ? 'Ouvindo…' : 'Modo conversa: diga “Angel…”');
    }

    // Fase 2: interromper falando enquanto a Angel fala
    function escutarInterrupcao() {
      if (!SR) return;
      const rec = new SR(); rec.lang = LANG; rec.interimResults = true; rec.continuous = true;
      let falou = '';
      rec.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) falou = e.results[i][0].transcript;
        if (falou.trim().split(/\s+/).length >= 2 && (audio || (window.speechSynthesis && speechSynthesis.speaking))) { pararFala(); rec.stop(); }
      };
      rec.onend = () => {};
      rec.onerror = () => {};
      try { rec.start(); } catch (e) {}
      const parar = setInterval(() => { if (!audio && !(window.speechSynthesis && speechSynthesis.speaking)) { try { rec.stop(); } catch (e) {} clearInterval(parar); } }, 400);
    }

    function setConversa(v) {
      conversa = v; chkConversa.checked = v; sessionStorage.setItem('angel-conversa', v ? '1' : '0');
      fab.classList.toggle('conversa', v);
      if (v) { abrir(); if (!ouvindo && !ocupado) escutar(false); } else if (ouvindo) { ouvindo.abort(); }
    }
    chkConversa.onchange = () => setConversa(chkConversa.checked);
    mic.onclick = () => { abrir(); if (ouvindo && conversa) { ouvindo.stop(); return; } escutar(true); };

    // segurar espaço (fora de campos de texto) = aperta e fala
    document.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && !e.repeat && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !document.activeElement.isContentEditable) {
        e.preventDefault(); if (!ouvindo) { abrir(); escutar(true); }
      }
    });
    document.addEventListener('keyup', (e) => { if (e.code === 'Space' && ouvindo && !conversa) ouvindo.stop(); });

    if (conversa) setConversa(true);
    window.AngelFalar = falar;  // usado pelo botão "Ouvir briefing"
    window.AngelPerguntar = enviar;
  });
})();
