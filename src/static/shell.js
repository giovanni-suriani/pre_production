/* pre_production - o que as tres etapas compartilham.
 *
 * A barra de etapas, o cliente de API, o aviso e a tela de trabalho em curso.
 * Sem framework e sem build, pela mesma razao do turnsEditor: isto roda em
 * 127.0.0.1 numa maquina so, e um passo de build seria uma peca a mais pra
 * quebrar entre voce e o arquivo que voce quer editar.
 *
 * parseTime/formatTime sao espelho de timecode.py - se mexer aqui, mexa la.
 */

// ------------------------------------------------------------------- api

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* corpo vazio */ }
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.status === 204 ? null : r.json();
}

const apiPost = (path, body) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

const apiPatch = (path, body) => api(path, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

const apiDelete = (path) => api(path, { method: 'DELETE' });

// ----------------------------------------------------------------- tempo

/* Aceita o que da vontade de digitar: "43:30.5", "1:03:30.1", "2610", vírgula
   decimal. Devolve segundos, ou NaN. Mesma regra do parse_time(). */
function parseTime(v) {
  if (typeof v === 'number') return v;
  const m = String(v).trim().match(/^(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d+)?)$/);
  if (!m) return NaN;
  let [, h, mi, s] = m;
  if (mi === undefined) { mi = h; h = undefined; }   // um só ':' = minutos
  return parseFloat(String(s).replace(',', '.'))
    + (parseInt(mi || 0, 10) * 60) + (parseInt(h || 0, 10) * 3600);
}

function formatTime(sec, dec = 3) {
  if (sec === null || sec === undefined || isNaN(sec)) return '';
  const neg = sec < 0; sec = Math.abs(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const w = dec ? 3 + dec : 2;
  const ss = s.toFixed(dec).padStart(w, '0');
  return (neg ? '-' : '') + (h ? `${h}:${String(m).padStart(2, '0')}:${ss}`
    : `${String(m).padStart(2, '0')}:${ss}`);
}

/* MESMA conta do SpeakerSwitch.py e do timecode.py. Tem que ser idêntica: o
   número de frame que a tela mostra é o que o Resolve vai receber. */
const toFrame = (sec, fps) => Math.round(sec * fps);

function humanBytes(n) {
  if (!n) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i ? n.toFixed(1) : Math.round(n)} ${u[i]}`;
}

function humanSecs(s) {
  s = Math.round(s || 0);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}min ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}min`;
}

// ------------------------------------------------------------------ aviso

let toastTimer = null;
function toast(msg, bad) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast'; el.className = 'toast hidden';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), bad ? 7000 : 3200);
}

const oops = (e) => toast(e && e.message ? e.message : String(e), true);

// ------------------------------------------------------------------- nav

/* As etapas seguintes ficam apagadas até existirem os arquivos que elas
   precisam - não é enfeite: cortar antes do wav, ou corrigir turnos antes de
   diarizar, simplesmente não tem o que mostrar. */
function renderNav(step, state) {
  const has = state && state.active;
  const proj = has ? state.active.project : null;
  const cut = has ? state.active.cut : null;
  const el = document.createElement('nav');
  el.className = 'nav';
  el.innerHTML = `
    <div class="brand">pre_<span>production</span></div>
    <div class="steps">
      <a class="step ${step === 1 ? 'on' : ''}" href="/"><span class="n">1</span>Projeto</a>
      <span class="sep">›</span>
      <a class="step ${step === 2 ? 'on' : ''}" href="/cortes"><span class="n">2</span>Cortes</a>
      <span class="sep">›</span>
      <a class="step ${step === 3 ? 'on' : ''} ${cut ? '' : 'off'}"
         href="${cut ? `/turnos?projeto=${encodeURIComponent(proj.slug)}&corte=${encodeURIComponent(cut.name)}` : '#'}"
         ><span class="n">3</span>Turnos</a>
    </div>
    <div class="ctx">${has
      ? `<b>${escapeHtml(proj.name)}</b> · <b>${escapeHtml(cut.name)}</b>
         <span>${formatTime(cut.start)} → ${formatTime(cut.end)}</span>`
      : '<span>nenhum corte ativo</span>'}</div>`;
  document.body.prepend(el);
  return el;
}

/* Liga a etapa 3 na barra assim que um corte é escolhido na etapa 2.
   Sem isto o link só acordava no próximo carregamento da página: você abria o
   corte, o botão "abrir no editor" funcionava, e a etapa 3 na barra continuava
   apagada — dois caminhos para a mesma coisa discordando na tela. */
function setNavCut(projectSlug, cutName) {
  const step = [...document.querySelectorAll('.nav .step')]
    .find((a) => a.textContent.includes('Turnos'));
  if (!step) return;
  step.classList.remove('off');
  step.href = `/turnos?projeto=${encodeURIComponent(projectSlug)}`
    + `&corte=${encodeURIComponent(cutName)}`;
}

function escapeHtml(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const h = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

// -------------------------------------------------------- trabalho em curso

/* Uma tela só para todo trabalho longo (extrair, fatiar, remuxar, diarizar).
 * Mostra passo, barra e LOG. O log fica visível o tempo todo de propósito: é
 * o único lugar onde aparece "faltou o HF_TOKEN" ou "cota do dia estourou", e
 * esconder isso atrás de um spinner transformaria 20 minutos de espera em 20
 * minutos de espera SEM explicação.
 */
function watchJob(jobId, opts) {
  opts = opts || {};
  return new Promise((resolve, reject) => {
    const wrap = h('div', 'jobwrap');
    wrap.innerHTML = `
      <div class="jobbox">
        <h2 class="jtitle">…</h2>
        <div class="stepline"><span class="jstep"></span><span class="el jel"></span></div>
        <div class="bar indet"><i></i></div>
        <div class="log jlog"></div>
        <div class="foot row end">
          <button class="btn danger jcancel">Cancelar</button>
          <button class="btn primary jclose hidden">Fechar</button>
        </div>
      </div>`;
    document.body.appendChild(wrap);
    const q = (s) => wrap.querySelector(s);
    const logEl = q('.jlog');
    let since = 0, done = false, timer = null;

    q('.jcancel').onclick = async () => {
      try { await apiPost(`/api/jobs/${jobId}/cancel`); } catch (e) { oops(e); }
    };
    const close = () => { clearTimeout(timer); wrap.remove(); };
    q('.jclose').onclick = () => { close(); (done === 'ok' ? resolve : reject)(lastSnap); };

    let lastSnap = null;
    async function tick() {
      let s;
      try {
        s = await api(`/api/jobs/${jobId}?since=${since}`);
      } catch (e) {
        /* 404 = o servidor não conhece mais este job. Os jobs vivem em
           memória, então reiniciar o servidor apaga o acompanhamento — e
           insistir só produziria "job desconhecido" para sempre. Para de
           perguntar e diz o que aconteceu, incluindo o que fazer com o
           trabalho que pode ter ficado pela metade. */
        if (e.status === 404) {
          logEl.appendChild(h('div', 'err',
            'O servidor não conhece mais este trabalho — ele provavelmente foi '
            + 'reiniciado no meio.'));
          logEl.appendChild(h('div', '',
            'O processo do script pode ter continuado rodando por fora, mas '
            + 'ninguém vai converter a saída dele. Volte ao corte: se aparecer '
            + 'um .raw.json sem o arquivo final ao lado, use "finalizar rodada".'));
          done = 'error';
          q('.jcancel').classList.add('hidden');
          q('.jclose').classList.remove('hidden');
          q('.bar').classList.remove('indet');
          q('.jstep').textContent = 'acompanhamento perdido';
          return;
        }
        logEl.appendChild(h('div', 'err', escapeHtml(e.message)));
        timer = setTimeout(tick, 2000);
        return;
      }
      lastSnap = s;
      q('.jtitle').textContent = s.title;
      q('.jstep').textContent = `passo ${s.step}/${s.steps} · ${s.step_label}`;
      q('.jel').textContent = humanSecs(s.elapsed);
      const bar = q('.bar');
      if (s.progress === null || s.progress === undefined) {
        bar.classList.add('indet');
        bar.firstElementChild.style.width = '';
      } else {
        bar.classList.remove('indet');
        bar.firstElementChild.style.width = `${(s.progress * 100).toFixed(1)}%`;
      }
      if (s.log.length) {
        const stick = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 24;
        for (const line of s.log) {
          const cls = line.startsWith('[erro') || line.startsWith('[!') ? 'err'
            : line.startsWith('[ok') ? 'ok'
              : line.startsWith('$ ') ? 'cmd'
                : line.startsWith('──') ? 'head' : '';
          logEl.appendChild(h('div', cls, escapeHtml(line)));
        }
        since = s.log_next;
        if (stick) logEl.scrollTop = logEl.scrollHeight;
      }
      if (s.status === 'running' || s.status === 'queued') {
        timer = setTimeout(tick, 600);
        return;
      }
      done = s.status;
      q('.jcancel').classList.add('hidden');
      q('.jclose').classList.remove('hidden');
      if (s.status === 'ok') {
        q('.bar').classList.remove('indet');
        q('.bar').firstElementChild.style.width = '100%';
        if (!opts.keepOpen) { close(); resolve(s); }
      }
    }
    tick();
  });
}
