/* Etapa 2 - CutsEditor.
 *
 * O trecho, o mapa de tracks, o método, a rodada.
 *
 * O que este arquivo resolve de verdade
 * -------------------------------------
 * O `start` que você marca na onda é UM número que responde a três perguntas
 * ao mesmo tempo:
 *
 *   1. onde o ffmpeg fatia o wav;
 *   2. quanto somar no tempo do wav para chegar no tempo dos turnos
 *      (`audio_offset` do editor);
 *   3. em que frame do episódio a timeline nova começa (`origin_frame` —
 *      43:30 dá 156600 em 60 fps, o mesmo `clip_origin` que o Resolve mostra).
 *
 * Antes esse número vivia sendo redescoberto: um json em tempo relativo, outro
 * em absoluto, e nada escrito em lugar nenhum dizendo qual era qual. Aqui ele
 * é marcado uma vez, na onda, e gravado no `corte.json`.
 */

const el = (id) => document.getElementById(id);

let STATE = null;
let PROJECTS = [];
let PROJ = null;          // projeto aberto
let CUTS = [];
let CUT = null;           // corte aberto (detalhe)
let METHODS = [];
let FILES = [];
// existe entire_transcribe.json (etapa 1) pra este projeto? controla a caixa
// "reaproveitar transcrição" no formulário de corte novo.
let ENTIRE_TRANSCRIBE_EXISTS = false;
// métodos marcados agora. Conjunto, não escolha única: o pedido é poder marcar
// Gemini + pyannote + Whisper e deixar rodando.
const CHOSEN = new Set();

// ---------------------------------------------------------------- onda

const W = {
  peaks: null, pps: 200, dur: 0, norm: 1,
  v0: 0, v1: 1,                 // janela visível, em segundos
  a: null, b: null,             // trecho marcado (in/out)
  play: 0,                      // playhead, em segundos do wav do projeto
  drag: null,                   // 'head' | 'a' | 'b' | 'pan'
  rate: 1,                      // shuttle J/K/L
  stopAt: null,                 // fim do "tocar trecho"
  cv: null, ctx: null, dpr: 1,
};

const RATES = [0.25, 0.5, 1, 2, 3, 4];

async function loadPeaks(slug) {
  const r = await fetch(`/api/projects/${encodeURIComponent(slug)}/peaks`);
  if (!r.ok) throw new Error(await r.text());
  W.pps = parseFloat(r.headers.get('X-Peaks-Per-Second')) || 200;
  W.dur = parseFloat(r.headers.get('X-Audio-Duration')) || 0;
  W.peaks = new Int8Array(await r.arrayBuffer());
  /* Ganho automático com curva sqrt, igual ao turnsEditor: é gravação de sala
     com mic distante, então a amplitude típica da fala fica lá embaixo. Linear,
     metade do episódio vira uma linha reta. Normaliza pelo p99 (não pelo pico,
     que é sempre um estouro isolado) e desenha em sqrt. */
  const n = W.peaks.length / 2;
  const step = Math.max(1, Math.floor(n / 20000));
  const sample = [];
  for (let i = 0; i < n; i += step) {
    sample.push(Math.max(Math.abs(W.peaks[i * 2]), Math.abs(W.peaks[i * 2 + 1])));
  }
  sample.sort((x, y) => x - y);
  W.norm = Math.max(8, sample[Math.floor(sample.length * 0.99)] || 127);
  W.v0 = 0; W.v1 = W.dur;
}

function fitCanvas() {
  const cv = W.cv;
  W.dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, hh = cv.clientHeight;
  if (cv.width !== Math.round(w * W.dpr) || cv.height !== Math.round(hh * W.dpr)) {
    cv.width = Math.round(w * W.dpr);
    cv.height = Math.round(hh * W.dpr);
  }
}

const t2x = (t) => ((t - W.v0) / (W.v1 - W.v0)) * W.cv.clientWidth;
const x2t = (x) => W.v0 + (x / W.cv.clientWidth) * (W.v1 - W.v0);

function drawWave() {
  if (!W.cv || !W.peaks) return;
  // o canvas mora numa seção que começa escondida; enquanto ela estiver
  // display:none a largura é 0 e toda conta de tempo↔pixel viraria NaN
  if (!W.cv.clientWidth) return;
  fitCanvas();
  const c = W.ctx, w = W.cv.clientWidth, hh = W.cv.clientHeight;
  c.setTransform(W.dpr, 0, 0, W.dpr, 0, 0);
  c.clearRect(0, 0, w, hh);

  const rulerH = 18, waveH = hh - rulerH, mid = rulerH + waveH / 2;

  // régua: um rótulo por marca, espaçamento que não vira sopa de números
  const span = W.v1 - W.v0;
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  const stepS = steps.find((s) => (span / s) < 12) || 3600;
  c.fillStyle = '#1a1c20'; c.fillRect(0, 0, w, rulerH);
  c.font = '10px "Cascadia Mono", monospace';
  c.textBaseline = 'middle';
  for (let t = Math.ceil(W.v0 / stepS) * stepS; t <= W.v1; t += stepS) {
    const x = t2x(t);
    c.fillStyle = '#2f333a'; c.fillRect(x, rulerH, 1, waveH);
    c.fillStyle = '#7e8695'; c.fillText(formatTime(t, 0), x + 4, rulerH / 2);
  }

  // onda cinza: aqui o sinal é sinal, não identidade de ninguém
  c.fillStyle = '#5a6270';
  const n = W.peaks.length / 2;
  for (let px = 0; px < w; px++) {
    const ta = x2t(px), tb = x2t(px + 1);
    let i0 = Math.max(0, Math.floor(ta * W.pps));
    const i1 = Math.min(n - 1, Math.ceil(tb * W.pps));
    let lo = 0, hi = 0;
    for (; i0 <= i1; i0++) {
      const a = W.peaks[i0 * 2], b = W.peaks[i0 * 2 + 1];
      if (a < lo) lo = a;
      if (b > hi) hi = b;
    }
    const g = (v) => Math.sqrt(Math.min(1, Math.abs(v) / W.norm)) * Math.sign(v)
      * (waveH / 2 - 2);
    const y0 = mid - g(hi), y1 = mid - g(lo);
    c.fillRect(px, y0, 1, Math.max(1, y1 - y0));
  }

  // seleção
  if (W.a !== null && W.b !== null) {
    const xa = t2x(Math.min(W.a, W.b)), xb = t2x(Math.max(W.a, W.b));
    c.fillStyle = 'rgba(236,238,241,.10)';
    c.fillRect(xa, rulerH, xb - xa, waveH);
    c.fillStyle = '#eceef1';
    c.fillRect(xa - 1, rulerH, 2, waveH);
    c.fillRect(xb - 1, rulerH, 2, waveH);
  }

  // playhead: existe sempre, não só durante a reprodução. É o cursor, e é
  // a partir dele que I e O marcam.
  const x = t2x(W.play);
  if (x >= -2 && x <= w + 2) {
    c.fillStyle = '#ff5d73';
    c.fillRect(x - 1, 0, 2, hh);
    c.beginPath();
    c.moveTo(x - 5, 0); c.lineTo(x + 5, 0); c.lineTo(x, 7);
    c.closePath(); c.fill();
  }
}

function wireWave() {
  const cv = W.cv;
  const near = (x, t) => Math.abs(x - t2x(t)) < 6;

  /* Arrastar move o PLAYHEAD, como no turnsEditor — não cria seleção. Marcar
     o trecho é `I`/`O`, uma decisão explícita, em vez de um efeito colateral
     de arrastar o mouse na onda enquanto se escuta. A borda de um bloco
     continua arrastável, que é o gesto de ajuste fino. */
  cv.addEventListener('mousedown', (e) => {
    const x = e.offsetX;
    if (W.a !== null && near(x, W.a)) W.drag = 'a';
    else if (W.b !== null && near(x, W.b)) W.drag = 'b';
    else if (e.shiftKey) W.drag = 'pan';
    else { W.drag = 'head'; setPlayhead(x2t(x)); }
    W.panFrom = { x, v0: W.v0, v1: W.v1 };
    drawWave();
  });

  window.addEventListener('mousemove', (e) => {
    if (!W.drag) return;
    const rect = cv.getBoundingClientRect();
    const x = e.clientX - rect.left;
    if (W.drag === 'pan') {
      const dt = (W.panFrom.x - x) / cv.clientWidth * (W.v1 - W.v0);
      setView(W.panFrom.v0 + dt, W.panFrom.v1 + dt);
    } else if (W.drag === 'head') {
      setPlayhead(x2t(x));
    } else {
      const t = Math.max(0, Math.min(W.dur, x2t(x)));
      if (W.drag === 'a') W.a = t; else W.b = t;
      syncFields();
    }
    drawWave();
  });

  window.addEventListener('mouseup', () => {
    if (W.drag === 'a' || W.drag === 'b') {
      if (W.a > W.b) { const t = W.a; W.a = W.b; W.b = t; }
      syncFields();
    }
    W.drag = null;
  });

  cv.addEventListener('mousemove', (e) => {
    cv.style.cursor = (W.a !== null && (near(e.offsetX, W.a) || near(e.offsetX, W.b)))
      ? 'ew-resize' : 'text';
  });

  cv.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (e.shiftKey) {
      const dt = (e.deltaY / 400) * (W.v1 - W.v0);
      setView(W.v0 + dt, W.v1 + dt);
    } else {
      const t = x2t(e.offsetX);
      const k = e.deltaY > 0 ? 1.25 : 0.8;
      setView(t - (t - W.v0) * k, t + (W.v1 - t) * k);
    }
    drawWave();
  }, { passive: false });

  new ResizeObserver(drawWave).observe(cv);
}

function setView(v0, v1) {
  const minSpan = 0.5;
  if (v1 - v0 < minSpan) { const m = (v0 + v1) / 2; v0 = m - minSpan / 2; v1 = m + minSpan / 2; }
  if (v1 - v0 > W.dur) { v0 = 0; v1 = W.dur; }
  if (v0 < 0) { v1 -= v0; v0 = 0; }
  if (v1 > W.dur) { v0 -= (v1 - W.dur); v1 = W.dur; v0 = Math.max(0, v0); }
  W.v0 = v0; W.v1 = v1;
}

/* Move o cursor e mantém o áudio junto. Uma função só para os dois porque
   playhead e `currentTime` discordarem é o tipo de bug que só aparece depois
   de meia hora ouvindo o trecho errado. */
function setPlayhead(t, opts) {
  W.play = Math.max(0, Math.min(W.dur || 0, t));
  const au = el('preview');
  if (!(opts && opts.fromAudio)) au.currentTime = W.play;
  const fps = (PROJ && PROJ.fps) || 60;
  el('pClock').textContent = formatTime(W.play);
  el('pClockFrame').textContent = `frame ${toFrame(W.play, fps).toLocaleString('pt-BR')}`;
  if (opts && opts.follow) followPlayhead();
  drawWave();
}

/* Só desloca a janela quando o playhead sai dela — rolar a cada frame durante
   a reprodução deixaria a onda tremendo sem parar. */
function followPlayhead() {
  const span = W.v1 - W.v0;
  if (W.play >= W.v0 + span * 0.05 && W.play <= W.v1 - span * 0.05) return;
  setView(W.play - span * 0.3, W.play + span * 0.7);
}

function markIn() {
  if (W.a === null) return;
  W.a = W.play;
  if (W.b <= W.a) {           // início depois do fim: empurra o fim, com aviso
    W.b = Math.min(W.dur, W.a + 1);
    toast('o fim foi empurrado para o trecho continuar válido');
  }
  syncFields(); drawWave();
}

function markOut() {
  if (W.b === null) return;
  W.b = W.play;
  if (W.b <= W.a) {
    W.a = Math.max(0, W.b - 1);
    toast('o início foi puxado para o trecho continuar válido');
  }
  syncFields(); drawWave();
}

function setRate(r) {
  W.rate = Math.max(RATES[0], Math.min(RATES[RATES.length - 1], r));
  const au = el('preview');
  au.playbackRate = W.rate;
  au.preservesPitch = true;   // 3× continua inteligível
  const badge = el('pRate');
  badge.textContent = `${W.rate}×`;
  badge.classList.toggle('hidden', W.rate === 1 && au.paused);
}

function playPause(from) {
  const au = el('preview');
  if (!au.paused) { au.pause(); return; }
  if (from !== undefined) setPlayhead(from);
  au.currentTime = W.play;
  au.play().catch(() => {});
}

function syncFields() {
  if (W.a === null) return;
  const a = Math.min(W.a, W.b), b = Math.max(W.a, W.b);
  el('pStart').value = formatTime(a);
  el('pEnd').value = formatTime(b);
  el('pDur').textContent = formatTime(b - a, 1);
  const fps = (PROJ && PROJ.fps) || 60;
  el('pFrame').textContent = toFrame(a, fps).toLocaleString('pt-BR');
  el('pOriginNote').innerHTML = `Este corte começa em <b>${formatTime(a)}</b>,
    que é o frame <b>${toFrame(a, fps)}</b> a ${fps} fps. Esse mesmo número vira
    o <code>audio_offset</code> do editor e o <code>clip_origin</code> esperado
    da timeline de origem no Resolve — os três saem daqui, não de três contas
    separadas.`;
}

function readFields() {
  const a = parseTime(el('pStart').value), b = parseTime(el('pEnd').value);
  if (isNaN(a) || isNaN(b)) return null;
  W.a = a; W.b = b;
  syncFields(); drawWave();
  return [a, b];
}

// -------------------------------------------------------------- tracks

/* Uma linha por rótulo possível: as pessoas, `cut`, e quem está fora de
   quadro. Fora de quadro aparece SEM seletor — é ausência de track, não a
   track zero, e mostrá-lo como opção convidaria a dar V4 pra ele. */
function renderTracks(container, tmap) {
  container.innerHTML = '';
  const rows = [];
  for (const p of PROJ.participants) rows.push({ name: p.name, kind: 'pessoa' });
  rows.push({ name: 'cut', kind: 'corte manual' });
  for (const n of (PROJ.off_camera || [])) rows.push({ name: n, kind: 'fora de quadro' });

  for (const r of rows) {
    const row = h('div', 'item');
    row.style.cursor = 'default';
    const off = r.kind === 'fora de quadro';
    const desc = off ? 'sem track própria — cai na V1 (BASE_TRACK)'
      : r.name === 'cut' ? 'enquadramento alternativo, marcado à mão na etapa 3'
        : '';
    row.innerHTML = `
      <div class="t row" style="gap:9px">
        <span class="dot ${off ? 'hollow' : ''}" style="background:${
  colorFor(r.name)}"></span>
        ${escapeHtml(r.name)}
        <span class="badge">${r.kind}</span>
      </div>
      ${desc ? `<div class="d">${desc}</div>` : ''}
      <div class="side"></div>`;
    if (!off) {
      const sel = h('select');
      sel.style.width = '110px';
      sel.dataset.name = r.name;
      sel.innerHTML = [1, 2, 3, 4, 5, 6, 7, 8].map((v) =>
        `<option value="${v}">V${v}</option>`).join('');
      sel.value = (tmap && tmap[r.name]) || 1;
      row.querySelector('.side').appendChild(sel);
    }
    container.appendChild(row);
  }
  return rows;
}

const PALETTE = ['#5b9cf8', '#f2a341', '#4ecb8f', '#e879b9', '#7dd3fc',
  '#c4b5fd', '#fca5a5', '#86efac', '#fcd34d'];

function colorFor(name) {
  if (name === 'cut') return '#a78bfa';
  const i = PROJ ? PROJ.participants.findIndex((p) => p.name === name) : -1;
  return i >= 0 ? PALETTE[i % PALETTE.length] : '#6b7280';
}

function readTracks(container) {
  const out = {};
  for (const s of container.querySelectorAll('select[data-name]')) {
    out[s.dataset.name] = parseInt(s.value, 10);
  }
  return out;
}

// ------------------------------------------------------------- projeto

async function loadProjects(preferred) {
  const d = await api('/api/projects');
  PROJECTS = d.projects.filter((p) => !p.broken);
  const sel = el('projSelect');
  sel.innerHTML = PROJECTS.map((p) =>
    `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`).join('');
  if (!PROJECTS.length) {
    el('pInfo').innerHTML = 'nenhum projeto — <a href="/">crie um na etapa 1</a>';
    return null;
  }
  const pick = preferred && PROJECTS.some((p) => p.slug === preferred)
    ? preferred : PROJECTS[0].slug;
  sel.value = pick;
  return pick;
}

async function openProject(slug) {
  const d = await api(`/api/projects/${encodeURIComponent(slug)}`);
  PROJ = d.project;
  CUTS = d.cuts;
  ENTIRE_TRANSCRIBE_EXISTS = !!d.entire_transcribe_exists;
  el('pInfo').innerHTML = `${escapeHtml(PROJ.participants.map((p) => p.name).join(' · '))}
    · ${formatTime(PROJ.duration, 0)} · ${PROJ.fps} fps`;
  if (!d.audio_exists) {
    el('pInfo').innerHTML += ' — <b style="color:var(--caution)">sem áudio extraído</b>';
  }
  renderCuts();
  el('newCut').classList.add('hidden');
  el('cutDetail').classList.add('hidden');
  if (d.audio_exists) {
    try { await loadPeaks(slug); drawWave(); } catch (e) { oops(e); }
  }
  el('preview').src = `/api/projects/${encodeURIComponent(slug)}/audio`;
}

function renderCuts() {
  const list = el('cutList');
  list.innerHTML = '';
  el('cutEmpty').classList.toggle('hidden', CUTS.length > 0);
  for (const c of CUTS) {
    const item = h('div', 'item');
    const runs = (c.runs || []).length;
    item.innerHTML = `
      <div class="t">${escapeHtml(c.name)}</div>
      <div class="d num">${formatTime(c.start)} → ${formatTime(c.end)}
        · ${formatTime(c.duration, 0)} · frame ${c.origin_frame}</div>
      <div class="side">
        ${runs ? `<span class="badge ok">${runs} rodada${runs > 1 ? 's' : ''}</span>` : ''}
        <span class="badge">${escapeHtml(c.status || '')}</span>
      </div>`;
    item.onclick = () => openCut(c.name);
    if (CUT && CUT.name === c.name) item.classList.add('on');
    list.appendChild(item);
  }
}

// ------------------------------------------------------------ novo corte

function startNewCut() {
  if (!PROJ) return;
  el('newCut').classList.remove('hidden');
  el('cutDetail').classList.add('hidden');
  el('cName').value = `corte_${CUTS.length + 1}`;
  el('cSpeakers').value = PROJ.participants.length + (PROJ.off_camera || []).length;
  renderTracks(el('cTracks'), defaultTracks());
  el('cReuseRow').classList.toggle('hidden', !ENTIRE_TRANSCRIBE_EXISTS);
  el('cReuseTranscript').checked = ENTIRE_TRANSCRIBE_EXISTS;
  if (W.a === null) { W.a = 0; W.b = Math.min(W.dur, 120); }
  syncFields();
  setPlayhead(Math.min(W.a, W.b));
  el('newCut').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function defaultTracks() {
  const order = { left: 1, center: 2, right: 3 };
  const map = {}; const used = new Set();
  PROJ.participants.forEach((p) => {
    const t = order[p.seat];
    if (t && !used.has(t)) { map[p.name] = t; used.add(t); }
  });
  let n = 1;
  PROJ.participants.forEach((p) => {
    if (map[p.name]) return;
    while (used.has(n)) n++;
    map[p.name] = n; used.add(n);
  });
  map.cut = Math.max(0, ...used) + 1;
  return map;
}

async function createCut() {
  const r = readFields();
  if (!r) return toast('marque o trecho na onda ou digite os tempos', true);
  const [a, b] = r;
  if (b - a < 1) return toast('o trecho está curto demais', true);
  const name = el('cName').value.trim();
  if (!name) return toast('dê um nome ao corte', true);
  const btn = el('cCreate');
  btn.disabled = true;
  try {
    const d = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts`, {
      name, start: a, end: b,
      track_map: readTracks(el('cTracks')),
      speakers: parseInt(el('cSpeakers').value, 10),
      reuse_transcript: ENTIRE_TRANSCRIBE_EXISTS && el('cReuseTranscript').checked,
    });
    await watchJob(d.job);
    toast(`corte ${d.cut.name} criado`
      + (d.reused_transcript ? ` · transcrição reaproveitada (${d.reused_transcript.turns} turnos)` : ''));
    await openProject(PROJ.slug);
    await openCut(d.cut.name);
  } catch (e) { oops(e); } finally { btn.disabled = false; }
}

// -------------------------------------------------------------- detalhe

async function openCut(name) {
  const d = await api(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
    encodeURIComponent(name)}`);
  CUT = d.cut;
  FILES = d.files;
  el('newCut').classList.add('hidden');
  el('cutDetail').classList.remove('hidden');
  el('dCut').textContent = CUT.name;
  el('dRange').textContent = `${formatTime(CUT.start)} → ${formatTime(CUT.end)}`;

  const fact = (l, v, s) => `<div class="field"><span class="lbl">${l}</span>
    <div class="num">${escapeHtml(v)}</div>
    ${s ? `<div class="sub" style="font-size:11.5px">${s}</div>` : ''}</div>`;
  el('dFacts').innerHTML = [
    fact('duração', formatTime(CUT.duration, 1),
      `${toFrame(CUT.duration, CUT.fps)} frames a ${CUT.fps} fps`),
    fact('offset do áudio', `${CUT.audio_offset}s`,
      'somado ao tempo do wav para chegar no tempo dos turnos'),
    fact('frame de origem', String(CUT.origin_frame),
      'o <code>clip_origin</code> esperado no Resolve'),
  ].join('');

  renderTracks(el('dTracks'), CUT.track_map);
  renderFiles();
  el('goEditor').disabled = !FILES.some((f) => !f.raw && !f.backup);
  // cortes anteriores ao nome com frames nao tem o campo: a conta e' a mesma
  const offFrames = CUT.video_offset_frames ?? (CUT.video_offset == null ? null
    : toFrame(CUT.start - CUT.video_offset, CUT.fps));
  el('ssNote').innerHTML = CUT.video
    ? `Trecho de vídeo remuxado: <code>${escapeHtml(CUT.video)}</code>, começando
       em <b>${formatTime(CUT.video_offset)}</b> —
       <b>${offFrames} frames</b> antes do corte. O
       <code>-c copy</code> não corta em qualquer frame: ele volta até o
       keyframe anterior, então o offset é medido (e vai no nome do arquivo)
       em vez de suposto. Apare esses ${offFrames} frames ao
       levar o arquivo pro Resolve.`
    : '';
  renderMethods();
  el('runSplit').checked = !!PROJ.split_screen;
  el('runSplit').disabled = !el('runGi').checked;
  setNavCut(PROJ.slug, CUT.name);
  el('cutDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  renderCuts();
}

function renderFiles() {
  const body = el('filesBody');
  body.innerHTML = '';
  const show = FILES.filter((f) => !f.backup);

  /* `.raw.json` sem o canônico ao lado = rodada que não chegou ao fim (quase
     sempre o servidor reiniciado no meio). O script terminou e gravou; só
     faltou a conversão de base. Oferece terminar em vez de deixar o arquivo
     órfão sem nada apontando para ele. */
  const orphans = show.filter((f) => f.raw
    && !show.some((g) => g.name === f.name.replace(/\.raw\.json$/, '.json')));
  const warn = el('orphanWarn');
  warn.classList.toggle('hidden', !orphans.length);
  if (orphans.length) {
    warn.innerHTML = `<b>Rodada interrompida.</b>
      ${orphans.map((f) => `<code>${escapeHtml(f.name)}</code>`).join(', ')}
      ${orphans.length > 1 ? 'existem' : 'existe'} sem o arquivo final ao lado —
      o script terminou mas ninguém converteu a base de tempo.
      <button class="linkbtn" id="finBtn">finalizar agora</button>`;
    el('finBtn').onclick = async () => {
      try {
        const r = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
          encodeURIComponent(CUT.name)}/finalize`);
        toast(r.finalizados.map((x) => `${x.file}: ${x.turns} turnos `
          + `(base ${x.base_detectada})`).join(' · '));
        await openCut(CUT.name);
      } catch (e) { oops(e); }
    };
  }
  el('filesEmpty').classList.toggle('hidden', show.length > 0);
  for (const f of show) {
    const tr = h('tr');
    const iss = Object.entries(f.issues || {});
    const generic = (f.labels || []).some((l) => /^SPEAKER_\d+$/i.test(l));
    tr.innerHTML = `
      <td class="mono">${escapeHtml(f.name)}
        ${f.raw ? '<span class="badge">cru</span>' : ''}</td>
      <td class="num">${f.count}</td>
      <td class="num">${f.span ? `${formatTime(f.span[0], 0)} → ${formatTime(f.span[1], 0)}` : '—'}</td>
      <td>${(f.labels || []).map((l) =>
    `<span class="badge" style="background:${colorFor(l)}22;color:${colorFor(l)}">${
      escapeHtml(l)}</span>`).join(' ') || '<span class="sub">sem rótulo</span>'}</td>
      <td>${iss.map(([k, v]) =>
    `<span class="badge ${k === 'short' || k === 'invalid' ? 'err' : 'warn'}"
       title="${k === 'short'
    ? 'turno abaixo de 2 frames: o SpeakerSwitch descarta e o vizinho engole'
    : k === 'overlap' ? 'dois turnos no mesmo frame'
      : k === 'gap' ? 'trecho sem turno nenhum: a V1 preenche' : ''}"
     >${v} ${k}</span>`).join(' ') || '<span class="badge">limpo</span>'}</td>
      <td class="row" style="gap:6px;border:0">
        ${generic ? '<button class="btn small" data-act="name">quem é quem</button>' : ''}
        <button class="btn small" data-act="editor">editar</button>
      </td>`;
    tr.querySelectorAll('button').forEach((b) => {
      b.onclick = () => (b.dataset.act === 'name' ? openNameModal(f) : goEditor(f.name));
    });
    body.appendChild(tr);
  }
}

// -------------------------------------------------------------- métodos

/* Escondidos do seletor a pedido do usuário (03/09/2026): redundantes com o
   gemini_chunks pra diarização com vídeo (que dá conta de corte curto E
   longo, então cobre o caso do gemini_video/gemini_audio/pyannote sozinho)
   e com o Whisper pra transcrição (o gemini_transcribe é pior pro QUANDO -
   ver HANDOFF-20260903.md). Continuam existindo em methods.py - só não
   aparecem aqui. Só o gemini_transcribe_live saiu do backend também (pedido
   à parte), então nem chega a existir pra filtrar. */
const HIDDEN_METHODS = new Set([
  'gemini_audio', 'gemini_video', 'pyannote', 'pyannote_v3', 'gemini_transcribe',
]);

/* Vários métodos numa rodada só. Antes era escolha única e cada rodada exigia
   voltar na tela — mas o uso real é marcar pyannote + Gemini + Whisper e
   deixar rodando, porque são dezenas de minutos que não deveriam pedir
   supervisão entre um e outro. As opções de cada método ficam DENTRO do item
   dele: separadas, elas não teriam a quem pertencer. */
async function renderMethods() {
  if (!METHODS.length) {
    try {
      METHODS = (await api('/api/methods')).methods
        .filter((m) => !HIDDEN_METHODS.has(m.id));
    } catch (e) { return oops(e); }
  }
  const list = el('methodList');
  const opened = new Set([...list.querySelectorAll('.mopts')]
    .filter((o) => !o.classList.contains('hidden'))
    .map((o) => o.dataset.for));
  const keep = {};
  for (const i of list.querySelectorAll('[data-opt]')) {
    keep[`${i.closest('.mopts').dataset.for}.${i.dataset.opt}`] = i.value;
  }
  list.innerHTML = '';

  for (const m of METHODS) {
    const item = h('div', 'item');
    const why = [];
    if (m.script_missing) why.push('script não encontrado');
    if (m.missing_packages.length) why.push(`falta ${m.missing_packages.join(', ')}`);
    if (m.missing_env.length) why.push(`falta ${m.missing_env.join(', ')}`);
    const on = CHOSEN.has(m.id);
    item.innerHTML = `
      <div class="t row" style="gap:9px">
        <label class="chk" style="gap:9px">
          <input type="checkbox" data-m="${escapeHtml(m.id)}" ${on ? 'checked' : ''}
            ${m.ready ? '' : 'disabled'}>
          <span>${escapeHtml(m.label)}</span>
        </label>
        ${m.recommended ? '<span class="badge ok">sugerido</span>' : ''}
        ${m.kind === 'transcript' ? '<span class="badge">transcrição</span>' : ''}
        ${m.output_base === 'absolute'
    ? '<span class="badge" title="já sai em tempo absoluto">absoluto</span>'
    : '<span class="badge" title="sai relativo ao corte; o app soma o offset">relativo</span>'}
      </div>
      <div class="d">${escapeHtml(m.note)}</div>
      <div class="side">${m.ready ? ''
    : `<span class="badge warn" title="${escapeHtml(why.join(' · '))}">indisponível</span>`}</div>
      <div class="mopts row hidden" data-for="${escapeHtml(m.id)}"
           style="grid-column:1/-1;margin-top:4px"></div>`;
    if (!m.ready) item.style.opacity = '.55';
    if (on) item.classList.add('on');

    const box = item.querySelector('.mopts');
    buildOpts(m, box, keep);
    box.classList.toggle('hidden', !on && !opened.has(m.id));

    const cb = item.querySelector('input[data-m]');
    const apply = () => {
      if (cb.checked) CHOSEN.add(m.id); else CHOSEN.delete(m.id);
      item.classList.toggle('on', cb.checked);
      box.classList.toggle('hidden', !cb.checked);
      syncRunBtn();
    };
    cb.onchange = apply;
    /* A linha inteira liga/desliga o método. Só o quadradinho respondia, e as
       opções (o modelo do Gemini, por exemplo) ficavam escondidas para quem
       clicava no nome — que é o alvo óbvio. Ignora cliques dentro das opções
       e no próprio label, que já alterna sozinho. */
    item.onclick = (e) => {
      if (!m.ready) return;
      if (e.target.closest('.mopts') || e.target.closest('.chk')) return;
      cb.checked = !cb.checked;
      apply();
    };
    list.appendChild(item);
  }
  syncRunBtn();
}

const OUTRO = '__outro__';   // sentinela: jamais e' um nome de modelo real

/* Modelo é `<select>`, não campo de texto com datalist.
   O datalist parecia flexível mas não tinha afordância nenhuma: um campo com
   um valor escrito e nenhuma seta — não dava para descobrir que ali havia uma
   lista. Agora a lista é visível e clicável, e "outro modelo…" abre o campo
   livre para quando o catálogo do Gemini andar na frente deste código. */
function buildSuggestField(m, k, spec, f, kept) {
  const cur = kept !== undefined ? kept : spec.default;
  // cada sugestão é {id, label} ou uma string solta
  const norm = spec.suggest.map((s) => (typeof s === 'string'
    ? { id: s, label: s } : s));
  // um modelo que veio do .env mas não está na lista não pode sumir do select
  const known = norm.some((s) => s.id === cur)
    ? norm : [{ id: cur, label: cur }, ...norm];
  const sel = h('select');
  sel.innerHTML = known.map((s) =>
    `<option value="${escapeHtml(s.id)}">${escapeHtml(s.label)}</option>`).join('')
    + `<option value="${OUTRO}">outro modelo…</option>`;
  sel.value = cur;

  const free = h('input');
  free.type = 'text';
  free.placeholder = 'nome exato do modelo';
  free.className = 'hidden';
  free.style.marginTop = '6px';

  // o valor que conta fica num campo escondido: assim `readOptsOf` continua
  // lendo um `[data-opt]` só, sem saber que existem dois controles aqui
  const hold = h('input');
  hold.type = 'hidden';
  hold.dataset.opt = k;
  hold.value = cur;

  const sync = () => {
    const outro = sel.value === OUTRO;
    free.classList.toggle('hidden', !outro);
    if (outro && !free.value) free.value = cur;
    hold.value = outro ? free.value.trim() : sel.value;
    syncOutName(m, f.closest('.mopts'));
  };
  sel.onchange = () => { sync(); if (sel.value === OUTRO) free.focus(); };
  free.oninput = sync;
  f.append(sel, free, hold);
}

function buildOpts(m, box, keep) {
  box.innerHTML = '';
  for (const [k, spec] of Object.entries(m.options || {})) {
    const f = h('div', 'field');
    f.style.width = spec.suggest ? '240px' : '200px';
    if (spec.suggest) {
      f.insertAdjacentHTML('afterbegin',
        `<span class="lbl">${escapeHtml(spec.label)}</span>`);
      buildSuggestField(m, k, spec, f, keep && keep[`${m.id}.${k}`]);
      box.appendChild(f);
      continue;
    }
    const input = spec.choices ? h('select') : h('input');
    if (spec.choices) {
      input.innerHTML = spec.choices.map((c) =>
        `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    } else if (typeof spec.default === 'number') {
      input.type = 'number';
      if (spec.min !== undefined) input.min = spec.min;
      if (spec.max !== undefined) input.max = spec.max;
    } else {
      input.type = 'text';
    }
    const kept = keep && keep[`${m.id}.${k}`];
    input.value = kept !== undefined ? kept : spec.default;
    input.dataset.opt = k;
    input.oninput = () => syncOutName(m, box);
    f.insertAdjacentHTML('afterbegin',
      `<span class="lbl">${escapeHtml(spec.label)}</span>`);
    f.appendChild(input);
    box.appendChild(f);
  }
  const out = h('p', 'note outname', '');
  out.style.flexBasis = '100%';
  box.appendChild(out);
  if (m.input === 'video_cut' && CUT && !CUT.video) {
    const n = h('p', 'note',
      'Lê a imagem: o trecho de vídeo será remuxado antes '
      + '(<code>-c copy</code>, sem recodificar) — soma um passo.');
    n.style.flexBasis = '100%';
    box.appendChild(n);
  }
  syncOutName(m, box);
}

function readOptsOf(id) {
  const box = el('methodList').querySelector(`.mopts[data-for="${id}"]`);
  const out = {};
  if (!box) return out;
  for (const i of box.querySelectorAll('[data-opt]')) {
    out[i.dataset.opt] = i.type === 'number' ? parseFloat(i.value) : i.value;
  }
  return out;
}

function syncRunBtn() {
  const n = CHOSEN.size;
  const btn = el('runBtn');
  btn.disabled = n === 0;
  btn.textContent = n <= 1 ? 'Rodar' : `Rodar os ${n}`;
  const box = el('methodOpts');
  if (!box) return;
  const list = [...CHOSEN].map((id) => {
    const m = METHODS.find((x) => x.id === id);
    return `<code>${escapeHtml(outNameFor(m, readOptsOf(id)))}</code>`;
  });
  box.innerHTML = n
    ? `<p class="note" style="flex-basis:100%">Vai rodar em sequência, no mesmo
       trabalho, e gravar ${list.join(' · ')}.</p>`
    : '';
}

/* Mesma regra do `_token()` do methods.py: o valor da opção vira pedaço de
   nome de arquivo. Espelhado aqui só para a tela poder mostrar o nome ANTES
   de rodar — quem decide o nome de verdade continua sendo o servidor. */
const optToken = (v) => String(v).replace(/[^\w.\-]+/g, '-')
  .replace(/^[-.]+|[-.]+$/g, '') || 'x';

function outNameFor(m, opts) {
  if (!m.out_name_template) return m.out_name;
  return m.out_name_template.replace(/\{(\w+)\}/g,
    (_, k) => optToken(opts[k] !== undefined && opts[k] !== ''
      ? opts[k] : (m.options[k] || {}).default));
}

function syncOutName(m, box) {
  const p = box.querySelector('.note.outname');
  if (!p) return;
  const name = outNameFor(m, readOptsOf(m.id));
  p.innerHTML = m.out_name_template
    ? `Grava <code>${escapeHtml(name)}</code> — o modelo entra no nome, então
       rodar dois modelos no mesmo corte deixa os dois lado a lado em vez de um
       sobrescrever o outro.`
    : `Grava <code>${escapeHtml(name)}</code>.`;
  syncRunBtn();
}

async function run() {
  if (!CHOSEN.size || !CUT) return;
  const btn = el('runBtn');
  btn.disabled = true;
  try {
    const d = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
      encodeURIComponent(CUT.name)}/run`, {
      methods: [...CHOSEN].map((id) => ({ id, options: readOptsOf(id) })),
      captions: el('runSrt').checked,
      captions_giautosubs: el('runGi').checked,
      split_screen: el('runSplit').checked,
    });
    const s = await watchJob(d.job, { keepOpen: true });
    const r = s.result || {};
    const c = r.captions || {};
    const g = r.giautosubs || {};
    toast(`${r.turns || 0} turnos em ${escapeHtml(r.file || d.out)}`
      + (r.transcript ? ` · transcrição em ${escapeHtml(r.transcript)}` : '')
      + (c.file ? ` · legenda em ${escapeHtml(c.file)}` : '')
      + (g.file ? ` · GiAutoSubs em ${escapeHtml(g.file)}` : ''));
    /* O porquê da legenda vai para a nota, não para o toast: "saiu sem nomes
       porque a diarização ainda está em SPEAKER_00" é uma frase que se lê, e
       o toast some sozinho antes disso. */
    if (c.file) {
      el('ssNote').innerHTML = `Legenda gravada em <code>${escapeHtml(c.path)}</code>
        (${c.count} trechos, base <b>${escapeHtml(c.base)}</b>${c.speakers_file
    ? `, nomes de <code>${escapeHtml(c.speakers_file)}</code>`
    : ', <b>sem nomes</b> — a diarização ainda está em SPEAKER_00; diga quem é '
      + 'quem e gere de novo'}). No Resolve:
        <b>Timeline → Import → Subtitle</b>.`;
    } else if (c.skipped || c.erro) {
      el('ssNote').textContent = `Legenda não gerada: ${c.skipped || c.erro}`;
    }
    if (g.file) {
      el('ssNote').innerHTML += `<br>${giNote(g)}`;
    } else if (g.erro) {
      el('ssNote').innerHTML += `<br>Legenda do GiAutoSubs não gerada: ${escapeHtml(g.erro)}`;
    }
    await openCut(CUT.name);
  } catch (e) {
    if (e && e.status !== undefined) oops(e);
    else if (e && e.error) toast(e.error, true);
  } finally { btn.disabled = false; }
}

// ---------------------------------------------------------- quem é quem

let NAME_FILE = null;

async function openNameModal(f) {
  NAME_FILE = f;
  const rows = el('nameRows');
  rows.innerHTML = '';
  let samples = [];
  try {
    samples = (await api(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
      encodeURIComponent(CUT.name)}/samples`)).samples;
  } catch (e) { /* sem amostras: dá pra mapear ouvindo no editor */ }

  const options = [...PROJ.participants.map((p) => p.name),
    ...(PROJ.off_camera || []), 'cut'];
  for (const label of f.labels) {
    const row = h('div', 'item');
    row.style.cursor = 'default';
    row.innerHTML = `<div class="t mono">${escapeHtml(label)}</div>
      <div class="d"></div><div class="side"></div>`;
    const side = row.querySelector('.side');
    const mine = samples.filter((s) => s.label === label).slice(0, 3);
    for (const s of mine) {
      const b = h('button', 'btn small', '▶');
      b.title = s.file;
      b.onclick = () => { const a = new Audio(s.url); a.play(); };
      side.appendChild(b);
    }
    const sel = h('select');
    sel.style.width = '180px';
    sel.dataset.from = label;
    sel.innerHTML = `<option value="">— manter ${escapeHtml(label)} —</option>`
      + options.map((o) => `<option value="${escapeHtml(o)}">${escapeHtml(o)}</option>`).join('');
    side.appendChild(sel);
    row.querySelector('.d').textContent = mine.length
      ? `${mine.length} amostra${mine.length > 1 ? 's' : ''} de áudio`
      : 'sem amostra — ouça no editor de turnos se estiver em dúvida';
    rows.appendChild(row);
  }
  el('nameModal').classList.remove('hidden');
}

async function applyNames() {
  const mapping = {};
  for (const s of el('nameRows').querySelectorAll('select[data-from]')) {
    if (s.value) mapping[s.dataset.from] = s.value;
  }
  if (!Object.keys(mapping).length) { el('nameModal').classList.add('hidden'); return; }
  try {
    const r = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
      encodeURIComponent(CUT.name)}/labels`, { file: NAME_FILE.name, mapping });
    toast(`${r.changed} turnos renomeados${r.backup ? ` (backup ${r.backup})` : ''}`);
    el('nameModal').classList.add('hidden');
    await openCut(CUT.name);
  } catch (e) { oops(e); }
}

// --------------------------------------------------------------- legenda

/* O texto vem de um arquivo com `text` (o Whisper); os nomes, de um com
   rótulo de falante (a diarização corrigida). São dois arquivos porque são
   duas informações que este pipeline produz separadas — o Whisper não sabe
   quem fala, e o diarizador não sabe o que foi dito. */
function openSrt() {
  const withText = FILES.filter((f) => !f.backup && f.keys.includes('text'));
  const withNames = FILES.filter((f) => !f.backup && !f.raw
    && ['name', 'speaker'].includes(f.label_key));
  if (!withText.length) {
    return toast('este corte não tem transcrição — rode o Whisper primeiro', true);
  }
  const opt = (f) => `<option value="${escapeHtml(f.name)}">${escapeHtml(f.name)}
    — ${f.count} trechos</option>`;
  el('srtText').innerHTML = withText.map(opt).join('');
  el('srtSpeakers').innerHTML = '<option value="">— sem nomes —</option>'
    + withNames.map(opt).join('');
  if (CUT.transcript) el('srtText').value = CUT.transcript;
  if (CUT.last_turns_file) el('srtSpeakers').value = CUT.last_turns_file;
  el('srtSplit').checked = !!PROJ.split_screen;
  srtFormat();
  el('srtModal').classList.remove('hidden');
}

/* O formato decide o resto do modal, porque as duas perguntas de baixo só
   existem para o .srt: o GiAutoSubs pega o falante do próprio turns (pinta a
   legenda com a cor da pessoa em vez de escrever o nome dentro dela), e lê
   sempre em tempo absoluto — quem desconta o início do corte, lá, é o
   giautosubs.py, com o corte.json na mão. Perguntar as duas coisas aqui seria
   oferecer uma escolha que o outro lado ignora. */
function srtFormat() {
  const gi = el('srtFormat').value === 'giautosubs';
  el('srtSpeakersField').classList.toggle('hidden', gi);
  el('srtBaseField').classList.toggle('hidden', gi);
  el('srtSplitField').classList.toggle('hidden', !gi);
  el('srtSub').innerHTML = gi
    ? `O json que o <code>giautosubs.py</code> lê — o mesmo texto, com o
       <b>tempo por palavra</b> preservado (é ele que acende a palavra falada) e
       em tempo absoluto. Vira também a coluna “o que foi dito” do editor.`
    : 'O <code>.srt</code> que o Resolve importa em '
      + '<b>Timeline → Import → Subtitle</b>.';
  el('srtName').value = gi ? `${CUT.name}.giautosubs.json` : `${CUT.name}.srt`;
  srtNote();
}

function srtNote() {
  if (el('srtFormat').value === 'giautosubs') {
    el('srtNote').innerHTML = `Depois de gerar, este arquivo passa a ser a
      transcrição do corte — é ele que o editor de turnos mostra na coluna
      “o que foi dito”, e é ele que você aponta no
      <code>giautosubs.py</code>.`;
    return;
  }
  const tl = el('srtBase').value === 'timeline';
  el('srtNote').innerHTML = tl
    ? `Subtrai <b>${formatTime(CUT.start)}</b> de cada legenda, porque a timeline
       que o SpeakerSwitch cria começa no <b>frame 0</b>. Em tempo absoluto ela
       entraria ${formatTime(CUT.start, 0)} adiantada — e o Resolve aceitaria
       sem reclamar.`
    : 'Mantém os segundos absolutos do episódio. Só serve se você for colocar a '
      + 'legenda sobre a gravação inteira, não sobre a timeline nova.';
}

async function genSrt() {
  const btn = el('srtGo');
  const gi = el('srtFormat').value === 'giautosubs';
  btn.disabled = true;
  try {
    const r = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
      encodeURIComponent(CUT.name)}/captions`, {
      file: el('srtText').value,
      speakers_file: gi ? null : (el('srtSpeakers').value || null),
      base: gi ? 'media' : el('srtBase').value,
      out_name: el('srtName').value.trim(),
      format: gi ? 'giautosubs' : 'srt',
      split_screen: gi ? el('srtSplit').checked : null,
    });
    el('srtModal').classList.add('hidden');
    toast(`${r.count} legendas em ${escapeHtml(r.file)}`);
    el('ssNote').innerHTML = gi ? giNote(r)
      : `Legenda gravada em <code>${escapeHtml(r.path)}</code>
         (${r.count} trechos, base <b>${escapeHtml(r.base)}</b>). No Resolve:
         <b>Timeline → Import → Subtitle</b>.`;
    await openCut(CUT.name);
  } catch (e) { oops(e); } finally { btn.disabled = false; }
}

/* O aviso que importa não é "gravei": é quantos trechos têm tempo por palavra.
   Sem ele o macro cria a legenda igual e a palavra falada nunca acende — e
   descobrir isso custa uma rodada inteira dentro do Resolve. */
function giNote(r) {
  return `Legenda do GiAutoSubs em <code>${escapeHtml(r.path)}</code>
    (${r.count} trechos, ${r.with_words} com tempo por palavra).
    ${r.note ? `<b>${escapeHtml(r.note)}</b> ` : ''}
    ${r.lua
      ? `<code>${escapeHtml(r.lua)}</code> gerado. No Resolve:
         <b>Workspace → Scripts → GiAutoSubs</b>.`
      : `<b>O .lua do GiAutoSubs não foi gerado:</b> ${escapeHtml(r.lua_erro || '?')}.
         Rode <code>giautosubs.py &lt;pasta do corte&gt; --transcript
         ${escapeHtml(r.file)}</code> na mão.`}`;
}

// ----------------------------------------------------------------- ações

function goEditor(file) {
  const q = `projeto=${encodeURIComponent(PROJ.slug)}&corte=${encodeURIComponent(CUT.name)}`;
  location.href = `/turnos?${q}${file ? `#${encodeURIComponent(file)}` : ''}`;
}

// ------------------------------------------------------------------ boot

(async function boot() {
  W.cv = el('wave');
  W.ctx = W.cv.getContext('2d');
  wireWave();
  /* Enquanto toca, o playhead vem do áudio (fonte única da verdade) e o
     "tocar trecho" pára no fim marcado. 60 ms é o suficiente para a linha
     parecer contínua sem redesenhar à toa. */
  setInterval(() => {
    const a = el('preview');
    if (a.paused) return;
    if (W.stopAt !== null && a.currentTime >= W.stopAt) { a.pause(); return; }
    setPlayhead(a.currentTime, { fromAudio: true, follow: true });
  }, 60);

  try {
    STATE = await api('/api/state');
    renderNav(2, STATE);
    const want = new URLSearchParams(location.search).get('projeto')
      || (STATE.active ? STATE.active.project.slug : null);
    const slug = await loadProjects(want);
    if (slug) await openProject(slug);
    if (STATE.active && STATE.active.project.slug === slug) {
      await openCut(STATE.active.cut.name).catch(() => {});
    }
  } catch (e) { oops(e); }

  el('projSelect').onchange = (e) => openProject(e.target.value).catch(oops);
  el('newCutBtn').onclick = startNewCut;
  el('cCancel').onclick = () => el('newCut').classList.add('hidden');
  el('cCreate').onclick = createCut;
  el('pStart').onchange = readFields;
  el('pEnd').onchange = readFields;
  el('pAll').onclick = () => { setView(0, W.dur); drawWave(); };
  el('pZoomSel').onclick = () => {
    if (W.a === null) return;
    const a = Math.min(W.a, W.b), b = Math.max(W.a, W.b), pad = (b - a) * 0.08;
    setView(a - pad, b + pad); drawWave();
  };
  el('pPlay').onclick = () => playPause();
  el('pPlaySel').onclick = () => {
    if (W.a === null) return;
    W.stopAt = Math.max(W.a, W.b);
    playPause(Math.min(W.a, W.b));
  };
  el('pIn').onclick = markIn;
  el('pOut').onclick = markOut;

  const au = el('preview');
  au.onplay = () => { el('pPlay').textContent = '⏸'; setRate(W.rate); };
  au.onpause = () => { el('pPlay').textContent = '▶'; W.stopAt = null; setRate(W.rate); };

  /* Teclado da etapa 2. Mesmas teclas do turnsEditor de propósito: quem passou
     a tarde na etapa 3 não deveria ter que aprender outro conjunto aqui.
     Ignora quando o foco está num campo — digitar "43:30" no início não pode
     disparar o marcador de fim. */
  document.addEventListener('keydown', (e) => {
    if (el('newCut').classList.contains('hidden')) return;
    if (document.querySelector('.jobwrap, .modal:not(.hidden)')) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const fps = (PROJ && PROJ.fps) || 60;
    const step = e.shiftKey ? 1 : 1 / fps;
    const k = e.key.toLowerCase();
    let hit = true;
    if (e.key === ' ') { setRate(1); playPause(); }
    else if (e.key === 'Enter') { el('pPlaySel').click(); }
    else if (k === 'i') markIn();
    else if (k === 'o') markOut();
    else if (e.key === 'ArrowLeft') setPlayhead(W.play - step, { follow: true });
    else if (e.key === 'ArrowRight') setPlayhead(W.play + step, { follow: true });
    else if (e.key === 'Home') setPlayhead(Math.min(W.a, W.b), { follow: true });
    else if (e.key === 'End') setPlayhead(Math.max(W.a, W.b), { follow: true });
    else if (k === 'l') setRate(RATES[Math.min(RATES.length - 1, RATES.indexOf(W.rate) + 1)]);
    else if (k === 'j') setRate(RATES[Math.max(0, RATES.indexOf(W.rate) - 1)]);
    else if (k === 'k') { el('preview').pause(); setRate(1); }
    else hit = false;
    if (hit) e.preventDefault();
  });

  el('runBtn').onclick = run;
  el('runGi').onchange = () => { el('runSplit').disabled = !el('runGi').checked; };
  el('dSaveTracks').onclick = async () => {
    try {
      await apiPatch(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
        encodeURIComponent(CUT.name)}`, { track_map: readTracks(el('dTracks')) });
      toast('mapa de tracks salvo');
      await openCut(CUT.name);
    } catch (e) { oops(e); }
  };
  el('goEditor').onclick = () => goEditor(null);
  el('openOther').onclick = async () => {
    const b = el('openOther');
    b.disabled = true; b.textContent = 'aguardando o diálogo…';
    try {
      const r = await apiPost(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
        encodeURIComponent(CUT.name)}/open-turns`);
      if (r.path) {
        toast(`${r.count} turnos — abrindo no editor`);
        goEditor(null);
        return;
      }
    } catch (e) { oops(e); } finally {
      b.disabled = false; b.textContent = 'Abrir outro arquivo…';
    }
  };
  el('delCut').onclick = async () => {
    if (!confirm(`Mover o corte "${CUT.name}" para projects\\_lixeira?\n\n`
      + 'Nada é apagado — a pasta continua no disco, com data no nome.')) return;
    try {
      await apiDelete(`/api/projects/${encodeURIComponent(PROJ.slug)}/cuts/${
        encodeURIComponent(CUT.name)}`);
      CUT = null;
      el('cutDetail').classList.add('hidden');
      await openProject(PROJ.slug);
    } catch (e) { oops(e); }
  };
  el('srtBtn').onclick = openSrt;
  el('srtCancel').onclick = () => el('srtModal').classList.add('hidden');
  el('srtBase').onchange = srtNote;
  el('srtFormat').onchange = srtFormat;
  el('srtGo').onclick = genSrt;
  el('nameCancel').onclick = () => el('nameModal').classList.add('hidden');
  el('nameApply').onclick = applyNames;
}());
