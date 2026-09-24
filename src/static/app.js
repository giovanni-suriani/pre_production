/* turnsEditor - frontend.
 *
 * Eixo de tempo: TUDO na interface esta em "tempo de turno" = segundos
 * absolutos na midia-fonte, a mesma unidade que esta no json e que o
 * SpeakerSwitch.py espera. O audio pode estar noutra base (o
 * _4330-end.wav comeca no segundo 2610 do episodio), entao existe um so
 * ponto de traducao:
 *
 *     tempoDeTurno = audio.currentTime + audioOffset
 *
 * Nunca misture os dois fora de toTurnTime()/toAudioTime().
 */

'use strict';

// ============================================================ tempo

const T = {
  /* Aceita "43:30.500", "1:03:30.1", "2610", "43:30,5". null se nao entender. */
  parse(str) {
    if (typeof str === 'number') return str;
    const s = String(str).trim().replace(',', '.');
    if (!s) return null;
    const m = s.match(/^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$/);
    if (!m) return null;
    let [, h, mi, sec] = m;
    // com um so ':' o numero da frente e' MINUTO (o regex casa no grupo de hora)
    if (mi === undefined) { mi = h; h = undefined; }
    return (+h || 0) * 3600 + (+mi || 0) * 60 + parseFloat(sec);
  },

  /* Espelha timecode.py:format_time - MM:SS.mmm, com hora so quando precisa. */
  format(sec, decimals = 3) {
    if (sec == null || !isFinite(sec)) return '';
    const neg = sec < 0; sec = Math.abs(sec);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    // sem decimais o campo tem 2 digitos ("05"), nao 3 - com 3+decimals a
    // regua saia escrevendo "05:000" no lugar de "05:00"
    const ss = s.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, '0');
    return (neg ? '-' : '') + (h ? `${h}:${String(m).padStart(2, '0')}:${ss}`
                                 : `${String(m).padStart(2, '0')}:${ss}`);
  },

  /* MESMA conta do SpeakerSwitch.py: int(round(segundos * fps)). */
  toFrame(sec, fps) { return Math.round(sec * fps); },
  snap(sec, fps)    { return Math.round(sec * fps) / fps; },
  spanFrames(a, b, fps) { return Math.round(b * fps) - Math.round(a * fps); },

  timecode(sec, fps) {
    const f = Math.round(sec * fps), fi = Math.round(fps);
    const tot = Math.floor(f / fi), fr = f % fi;
    const p = n => String(n).padStart(2, '0');
    return `${p(Math.floor(tot / 3600))}:${p(Math.floor(tot % 3600 / 60))}:${p(tot % 60)}:${p(fr)}`;
  },

  dur(sec) {
    return sec < 10 ? sec.toFixed(3) + 's'
         : sec < 60 ? sec.toFixed(2) + 's'
         : T.format(sec, 1);
  },
};

// ============================================================ estado

const S = {
  config: null,
  file: null,
  turnFiles: [],      // nomes ja existentes na pasta de resultados
  labelKey: 'name',
  turns: [],          // {uid, start, end, label, extra}
  labels: [],
  transcript: [],
  peaks: null,        // Int8Array de pares [lo,hi]
  gain: 1,            // auto-ganho da waveform (ver computeGain)
  pps: 200,
  audioDuration: 0,
  view: { a: 0, b: 60 },
  sel: null,          // uid selecionado
  dirty: false,
  baseline: '[]',     // snapshot() do estado como veio do disco
  baseRel: true,      // mostrar tempo contado do zero (ver zeroRef/disp)
  zero: 0,            // segundo absoluto que a interface chama de 00:00.000
  undo: [], redo: [],
  hidden: new Set(),  // falantes ocultos no filtro
  query: '',
  playUntil: null,    // tocar so ate aqui (modo "tocar turno")
  rate: 1,            // velocidade do shuttle J/K/L
  drag: null,         // arraste de borda de turno em andamento
  scrub: null,        // arraste do playhead em andamento
  rev: 0,             // muda a cada edicao; invalida o cache da waveform
  cache: null,        // canvas offscreen com waveform + blocos ja desenhados
  _uid: 1,
};

/* Marca que algo mudou e o desenho em cache nao vale mais. */
function touch() { S.rev++; }

const $ = id => document.getElementById(id);
const el = {};
['fileSelect','audioSelect','audioOffset','transcriptOffset','fps','dirty',
 'saveBtn','undoBtn','redoBtn','helpBtn','cfgBtn','playBtn','playTurnBtn',
 'clock','clockTc','clockAbs','rate','baseRel','baseAbs','zeroAt','zeroReset',
 'snapChk','linkChk','followChk','zoomIn','zoomOut','zoomFit','wave','search',
 'speakerFilter','stats','turnsBody','toast','audio','thStart','thEnd',
 'speakerMenu',
 'cfgModal','cfgClose','saveModal','saveName','saveSnap','saveOverwrite',
 'saveLabelKey','saveHint','saveCancel','saveConfirm','helpModal','helpClose']
  .forEach(k => el[k] = $(k));

const fps = () => S.config ? S.config.fps : 60;
const minFrames = () => S.config ? S.config.min_span_frames : 2;
const audioOffset = () => S.config ? S.config.audio_offset : 0;
const toTurnTime  = at => at + audioOffset();
const toAudioTime = tt => tt - audioOffset();

/* ---- base de tempo mostrada na interface -------------------------------
 *
 * Internamente TUDO e' segundo absoluto na midia-fonte (o que esta no json e o
 * que o SpeakerSwitch espera). Mas os turnos deste projeto comecam em 43:30, e
 * a timeline que o SpeakerSwitch cria no Resolve comeca no frame 0 - ou seja,
 * o que voce ve no Resolve nao bate com o numero do json.
 *
 * Entao a interface mostra, por padrao, o tempo CONTADO DO ZERO a partir de
 * S.zero (normalmente o primeiro turno). disp() so existe pra mostrar e
 * undisp() pra ler de volta o que foi digitado - o dado nunca e' alterado.
 */
const zeroRef = () => (S.baseRel ? S.zero : 0);
const disp    = t => t - zeroRef();
const undisp  = x => x + zeroRef();

const firstStart = () =>
  S.turns.length ? Math.min(...S.turns.map(t => t.start)) : 0;

/* Reflete a base escolhida em tudo que mostra tempo. Os cabecalhos dizem em
   que base a coluna esta - sem isso da' pra digitar 43:30 numa coluna que
   conta do zero e mover o turno 43 minutos sem perceber. */
function applyBase() {
  el.baseRel.classList.toggle('on', S.baseRel);
  el.baseAbs.classList.toggle('on', !S.baseRel);
  const suf = S.baseRel ? ' · do zero' : ' · da mídia';
  el.thStart.textContent = 'início' + suf;
  el.thEnd.textContent = 'fim' + suf;
  el.zeroAt.value = T.format(S.zero);
  el.zeroAt.disabled = !S.baseRel;
  renderTable();
  draw();
}

// ============================================================ util

function toast(msg, kind = '') {
  el.toast.textContent = msg;
  el.toast.className = 'toast ' + kind;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.toast.classList.add('hidden'), 3800);
}

/* Quem nao tem track propria no SpeakerSwitch (cai na BASE_TRACK). Desenhado
   como ausencia, nao como mais um falante - ver off_camera_names na config. */
function offCamera(name) {
  const list = S.config?.off_camera_names || ['no_name'];
  return !name || list.includes(name);
}

/* Rotulos que nenhum diarizador produz - "cut" e' o caso: nao e' uma pessoa
   detectada, e a decisao manual de cortar pra V4. A interface separa os dois
   porque sao coisas diferentes: um veio da maquina, o outro e' seu. */
function manualOnly(name) {
  return (S.config?.manual_only_names || []).includes(name);
}

function colorFor(name) {
  if (name == null) name = '';
  // sem rotulo nao e' "um falante chamado string-vazia": o hash de '' cairia em
  // hsl(0) e pintaria tudo de vermelho, cor que a interface usa pra problema
  if (!name) return '#7e8695';
  const fixed = S.config?.speaker_colors || {};
  if (fixed[name]) return fixed[name];
  // cor estavel derivada do nome: o mesmo falante mantem a cor entre sessoes
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return `hsl(${Math.abs(h) % 360} 58% 58%)`;
}

function sorted() { return [...S.turns].sort((x, y) => x.start - y.start); }
function byUid(uid) { return S.turns.find(t => t.uid === uid); }

function setDirty(v) {
  S.dirty = v;
  el.dirty.classList.toggle('hidden', !v);
}

/* Pilha de undo: estado COMPLETO (com uid, pra selecao sobreviver ao desfazer).
   Barato: 200-600 turnos = alguns KB por passo. */
function pushUndo() {
  S.undo.push(JSON.stringify(S.turns));
  if (S.undo.length > 120) S.undo.shift();
  S.redo.length = 0;
  setDirty(true);
}
function undo() {
  if (!S.undo.length) return;
  S.redo.push(JSON.stringify(S.turns));
  S.turns = JSON.parse(S.undo.pop());
  refresh();
  checkDirty();
}
function redo() {
  if (!S.redo.length) return;
  S.undo.push(JSON.stringify(S.turns));
  S.turns = JSON.parse(S.redo.pop());
  refresh();
  checkDirty();
}

/* Assinatura pra comparar com o estado carregado: so o que vai pro arquivo -
   sem uid (interno) e em ordem, pra reordenar sozinho nao contar como edicao. */
function snapshot() {
  return JSON.stringify(sorted().map(t => [t.start, t.end, t.label, t.extra]));
}

/* Depois de desfazer ate voltar ao estado carregado, nao ha mais "alteracoes
   nao salvas" - sem isso o aviso ficava ligado pra sempre e o navegador
   perguntava se voce queria mesmo sair de uma pagina que nao mudou nada. */
function checkDirty() { setDirty(snapshot() !== S.baseline); }

// ============================================================ analise

/* Espelha analyze() do app.py, mas roda a cada tecla pra dar retorno na hora.
   Devolve um Map uid -> [{kind, msg}]. */
function computeIssues() {
  const f = fps(), mf = minFrames(), out = new Map();
  const add = (uid, kind, msg) => {
    if (!out.has(uid)) out.set(uid, []);
    out.get(uid).push({ kind, msg });
  };
  const list = sorted();
  for (const t of list) {
    if (!(t.end > t.start)) {
      add(t.uid, 'invalid', 'fim menor ou igual ao início');
    } else if (T.spanFrames(t.start, t.end, f) < mf) {
      const n = T.spanFrames(t.start, t.end, f);
      add(t.uid, 'short', `vira ${n} frame(s) — abaixo do mínimo de ${mf}; ` +
                          `o SpeakerSwitch descarta e o vizinho engole este trecho`);
    }
  }
  for (let i = 0; i + 1 < list.length; i++) {
    const a = list[i], b = list[i + 1];
    const fa = T.toFrame(a.end, f), fb = T.toFrame(b.start, f);
    if (fb < fa) add(b.uid, 'overlap', `sobrepõe o anterior em ${fa - fb} frame(s)`);
    else if (fb > fa) add(b.uid, 'gap',
      `buraco de ${T.dur(b.start - a.end)} (${fb - fa} frames) antes deste — ` +
      `o SpeakerSwitch preenche com a track base`);
  }
  return out;
}

// ============================================================ transcricao

/* Junta o texto do Whisper que cai dentro do turno. Busca binaria porque isso
   roda pra cada linha a cada re-render. */
function textFor(t) {
  const segs = S.transcript;
  if (!segs.length) return '';
  let lo = 0, hi = segs.length - 1, first = segs.length;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (segs[m].end > t.start) { first = m; hi = m - 1; } else lo = m + 1;
  }
  const parts = [];
  for (let i = first; i < segs.length && segs[i].start < t.end; i++) {
    parts.push(segs[i].text);
    if (parts.length > 14) { parts.push('…'); break; }
  }
  return parts.join(' ');
}

// ============================================================ rede

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r;
}
const apiJson = (p, o) => api(p, o).then(r => r.json());

async function patchConfig(patch) {
  const r = await apiJson('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  S.config = r.config;
  return r.config;
}

// ============================================================ carga

async function boot() {
  const info = await apiJson('/api/config');
  S.config = info.config;
  S.baseRel = info.config.time_base !== 'absolute';
  el.fps.value = info.config.fps;
  el.audioOffset.value = info.config.audio_offset;
  el.transcriptOffset.value = info.config.transcript_offset;

  S.turnFiles = info.turn_files.map(f => f.name);
  el.fileSelect.innerHTML = info.turn_files.map(f =>
    `<option value="${f.name}">${f.name} — ${f.count} turnos, ` +
    `${T.format(f.span[0], 0)}→${T.format(f.span[1], 0)}</option>`).join('');
  el.audioSelect.innerHTML = info.audio_files.map(a =>
    `<option value="${a.name}">${a.name} — ${T.format(a.duration, 0)}</option>`).join('');

  // o ultimo aberto pode ter sido renomeado/apagado desde a sessao passada;
  // nesse caso cai num turns*.json de verdade, nao no primeiro da ordem
  // alfabetica (que e' o EpisodioPiloto_transcript.json, 1690 segmentos)
  const want = info.config.last_turns_file;
  const fallback = info.turn_files.find(f => /^turns/i.test(f.name));
  el.fileSelect.value = info.turn_files.some(f => f.name === want) ? want
                      : fallback ? fallback.name
                      : el.fileSelect.value;
  el.audioSelect.value = info.config.audio_file;

  await Promise.all([loadTurns(el.fileSelect.value), loadAudio(), loadTranscript()]);
  zoomFit();
  goToStart();
  wireEvents();
  requestAnimationFrame(tick);
}

/* Posiciona no primeiro turno em vez do segundo 0 do arquivo.
   Os turnos deste projeto comecam em 43:30 - deixar o playhead no zero faria
   o Espaco tocar 43 minutos de audio antes do primeiro turno. */
function goToStart() {
  if (!S.turns.length) return;
  const first = sorted()[0];
  const at = toAudioTime(first.start);
  if (at >= 0 && (!S.audioDuration || at < S.audioDuration)) {
    el.audio.currentTime = at;
  }
  select(first.uid);
}

async function loadTurns(name) {
  const d = await apiJson('/api/turns?file=' + encodeURIComponent(name));
  S.file = d.file;
  S.labelKey = d.label_key || 'name';
  S.turns = d.turns.map(t => ({
    uid: S._uid++, start: t.start, end: t.end,
    label: t.label, extra: t.extra || {},
  }));
  S.labels = d.labels || [];
  S.sel = null;
  S.hidden.clear();
  S.undo.length = 0; S.redo.length = 0;
  S.baseline = snapshot();   // referencia pra saber se ainda ha edicoes
  setDirty(false);
  // display_zero null = automatico: o zero e' o primeiro turno DESTE arquivo,
  // recalculado a cada troca. Se voce fixou um valor, ele manda.
  S.zero = S.config.display_zero != null ? S.config.display_zero : firstStart();
  applyBase();
  el.saveLabelKey.value = S.labelKey === 'speaker' ? 'speaker' : 'name';
  await patchConfig({ last_turns_file: name });
  refresh();

  const span = d.span;
  if (span) {
    const aSpan = [audioOffset(), audioOffset() + S.audioDuration];
    if (S.audioDuration && (span[1] < aSpan[0] || span[0] > aSpan[1])) {
      const sug = (span[0] - 0).toFixed(0);
      toast(`Atenção: os turnos vão de ${T.format(span[0], 0)} a ${T.format(span[1], 0)}, ` +
            `mas o áudio cobre ${T.format(aSpan[0], 0)}–${T.format(aSpan[1], 0)}. ` +
            `Bases de tempo diferentes? Ajuste o offset (talvez ${sug}s).`, 'err');
    }
  }
}

async function loadAudio() {
  const name = el.audioSelect.value;
  el.audio.src = '/api/audio?file=' + encodeURIComponent(name);
  // trocar o src zera o playbackRate, entao o shuttle e' reaplicado quando a
  // midia nova termina de carregar
  el.audio.addEventListener('loadedmetadata', () => setRate(S.rate), { once: true });
  const r = await api('/api/peaks?file=' + encodeURIComponent(name));
  S.pps = +r.headers.get('X-Peaks-Per-Second') || 200;
  S.audioDuration = +r.headers.get('X-Audio-Duration') || 0;
  S.peaks = new Int8Array(await r.arrayBuffer());
  S.gain = computeGain(S.peaks);
  draw();
}

/* Auto-ganho da waveform, calibrado com o audio real deste episodio.
 *
 * O problema: e' gravacao de sala com microfone distante. Medido nos peaks do
 * EpisodioPiloto_full.wav, a amplitude nos trechos com fala tem p50=9, p90=36,
 * p99=104 (de 127) - uma faixa dinamica de ~15dB. Desenhado linear, metade da
 * fala vira uma linha de 4px: inutil justamente pra tarefa que a waveform
 * existe aqui, que e' enxergar ONDE alguem fala.
 *
 * Ganho linear sozinho nao resolve (ou a fala baixa some, ou os picos saturam
 * em massa). A saida e' a mesma dos editores de audio: normalizar pelo
 * percentil 99 e desenhar numa curva perceptual - aqui sqrt (gamma 0.5), que
 * nas medidas deu o melhor contraste silencio->fala (2.1x) e mantem so ~1% dos
 * buckets saturando.
 *
 * Histograma em vez de sort: sao 833k buckets, isso e' O(n) e exato.
 */
function computeGain(peaks) {
  const hist = new Int32Array(129);
  let n = 0;
  for (let i = 0; i < peaks.length; i += 2) {
    const a = Math.abs(peaks[i]), b = Math.abs(peaks[i + 1]);
    const amp = a > b ? a : b;
    if (amp <= 2) continue;          // silencio/ruido de fundo nao conta
    hist[amp]++; n++;
  }
  if (!n) return 1;
  const alvo = n * 0.99;
  let acc = 0, p99 = 127;
  for (let v = 0; v <= 128; v++) {
    acc += hist[v];
    if (acc >= alvo) { p99 = v || 1; break; }
  }
  return Math.min(20, Math.max(1, 127 / p99));
}

/* amplitude (-127..127) -> fracao da meia-altura (-1..1), ja com ganho+curva */
function ampToUnit(v, gain) {
  const u = Math.min(1, Math.abs(v) * gain / 127);
  return Math.sign(v) * Math.sqrt(u);
}

async function loadTranscript() {
  try {
    const d = await apiJson('/api/transcript');
    S.transcript = d.segments || [];
    if (d.error) console.warn(d.error);
  } catch (e) {
    S.transcript = [];
    console.warn('transcricao indisponivel:', e.message);
  }
}

// ============================================================ waveform

const RULER_H = 20;
const LANE_H = 46;

function waveMetrics() {
  const c = el.wave, dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  }
  return { w, h, dpr, ctx: c.getContext('2d') };
}

const xToTime = (x, w) => S.view.a + (x / w) * (S.view.b - S.view.a);
const timeToX = (t, w) => ((t - S.view.a) / (S.view.b - S.view.a)) * w;

/* Desenho em duas camadas.
 *
 * Camada cara (regua + waveform + blocos) vai pra um canvas offscreen e so e'
 * refeita quando view/zoom/edicoes mudam. Camada barata (playhead) e' redesenhada
 * a cada frame por cima.
 *
 * Sem isso, tocar o audio custava re-escanear os peaks a cada frame: no zoom
 * "tudo" sao ~520 buckets por pixel x 1600px = 830 mil leituras por frame, 60x
 * por segundo. Com o cache, tocar so custa um drawImage + uma linha.
 */
function draw() {
  const { w, h, dpr, ctx } = waveMetrics();
  const key = [w, h, dpr, S.view.a, S.view.b, S.gain, S.rev, S.sel,
               zeroRef(), [...S.hidden].join(',')].join('|');
  if (!S.cache || S.cache.key !== key) renderCache(key, w, h, dpr);

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, el.wave.width, el.wave.height);
  ctx.drawImage(S.cache.canvas, 0, 0);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // --- playhead (unica coisa que muda durante a reproducao) ---
  const ph = toTurnTime(el.audio.currentTime || 0);
  if (ph >= S.view.a && ph <= S.view.b) {
    const x = timeToX(ph, w);
    ctx.strokeStyle = '#ff5c7a';
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    ctx.fillStyle = '#ff5c7a';
    ctx.beginPath();
    ctx.moveTo(x - 5, 0); ctx.lineTo(x + 5, 0); ctx.lineTo(x, 7); ctx.fill();
  }
}

function renderCache(key, w, h, dpr) {
  const off = (S.cache && S.cache.canvas) || document.createElement('canvas');
  off.width = el.wave.width; off.height = el.wave.height;
  const ctx = off.getContext('2d');
  S.cache = { key, canvas: off };

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const bodyTop = RULER_H, bodyH = h - RULER_H - LANE_H;
  const mid = bodyTop + bodyH / 2;

  drawRuler(ctx, w);

  // --- waveform ---
  if (S.peaks) {
    const n = S.peaks.length / 2;
    // onda em cinza de proposito: se ela fosse azul competiria com o Giovanni.
    // Na faixa de baixo, cor = quem fala; aqui em cima, cinza = so o sinal.
    ctx.fillStyle = '#575f6c';
    for (let x = 0; x < w; x++) {
      // tempo de TURNO -> tempo de AUDIO -> indice do bucket
      const t0 = toAudioTime(xToTime(x, w)), t1 = toAudioTime(xToTime(x + 1, w));
      let i0 = Math.floor(t0 * S.pps), i1 = Math.ceil(t1 * S.pps);
      if (i1 <= 0 || i0 >= n) continue;
      i0 = Math.max(0, i0); i1 = Math.min(n, Math.max(i1, i0 + 1));
      let lo = 127, hi = -128;
      for (let i = i0; i < i1; i++) {
        const a = S.peaks[i * 2], b = S.peaks[i * 2 + 1];
        if (a < lo) lo = a;
        if (b > hi) hi = b;
      }
      if (hi < lo) continue;
      const half = bodyH / 2;
      const yA = mid - ampToUnit(hi, S.gain) * half;
      const yB = mid - ampToUnit(lo, S.gain) * half;
      ctx.fillRect(x, yA, 1, Math.max(1, yB - yA));
    }
  }

  // --- blocos de turno ---
  const laneY = h - LANE_H;
  ctx.save();
  ctx.beginPath(); ctx.rect(0, laneY, w, LANE_H); ctx.clip();
  for (const t of sorted()) {
    if (t.end < S.view.a || t.start > S.view.b) continue;
    if (S.hidden.has(t.label ?? '')) continue;
    const x0 = timeToX(t.start, w), x1 = timeToX(t.end, w);
    const bw = Math.max(1, x1 - x0);
    const col = colorFor(t.label);
    const isSel = t.uid === S.sel;

    const top = laneY + 5, hh = LANE_H - 14;
    const fora = offCamera(t.label);

    if (fora) {
      // fora de camera nao e' "mais um falante": e' ausencia de track. Bloco
      // vazado e hachurado diz isso de longe, sem precisar ler o rotulo.
      ctx.fillStyle = 'rgba(126,134,149,.14)';
      ctx.fillRect(x0, top, bw, hh);
      ctx.save();
      ctx.beginPath(); ctx.rect(x0, top, bw, hh); ctx.clip();
      ctx.strokeStyle = 'rgba(126,134,149,.4)';
      ctx.lineWidth = 1;
      for (let hx = x0 - hh; hx < x0 + bw; hx += 7) {
        ctx.beginPath();
        ctx.moveTo(hx, top + hh); ctx.lineTo(hx + hh, top);
        ctx.stroke();
      }
      ctx.restore();
    } else {
      ctx.fillStyle = col;
      ctx.globalAlpha = isSel ? 1 : .82;
      ctx.fillRect(x0, top, bw, hh);
      ctx.globalAlpha = 1;
    }

    // selecao marcada com branco (acromatico): nao compete com nenhum falante
    ctx.strokeStyle = isSel ? '#eceef1' : 'rgba(18,19,22,.75)';
    ctx.lineWidth = isSel ? 2 : 1;
    ctx.strokeRect(x0 + .5, top + .5, Math.max(1, bw - 1), hh - 1);

    // largura VISIVEL, nao a largura total: um bloco que comeca antes da borda
    // esquerda tinha o rotulo desenhado fora da tela e ficava anonimo
    const vis = Math.min(x1, w) - Math.max(x0, 0);
    if (vis > 42) {
      ctx.save();
      ctx.beginPath(); ctx.rect(x0 + 4, laneY, bw - 8, LANE_H); ctx.clip();
      ctx.font = '600 11px "Segoe UI Variable Small", "Segoe UI", system-ui, sans-serif';
      // texto escuro sobre o bloco cheio, claro sobre o hachurado
      ctx.fillStyle = fora ? '#aeb4c0' : 'rgba(12,14,17,.86)';
      ctx.fillText(t.label ?? '—', Math.max(x0, 0) + 7, top + hh / 2 + 4);
      ctx.restore();
    }
  }
  ctx.restore();
}

function drawRuler(ctx, w) {
  const span = S.view.b - S.view.a;
  // passo "redondo" mais proximo que ainda deixa os rotulos legiveis
  const steps = [.01, .05, .1, .25, .5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900];
  const step = steps.find(s => (span / s) < (w / 86)) || 1800;
  ctx.fillStyle = '#1a1c20';
  ctx.fillRect(0, 0, w, RULER_H);
  ctx.strokeStyle = '#2f333a'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, RULER_H - .5); ctx.lineTo(w, RULER_H - .5); ctx.stroke();
  ctx.font = '10.5px "Cascadia Mono", Consolas, ui-monospace, monospace';
  // as marcas caem em multiplos redondos do ZERO mostrado, nao do zero da
  // midia - senao, contando do zero, a regua marcaria 0:59, 1:59, 2:59...
  const z = zeroRef();
  for (let t = Math.ceil((S.view.a - z) / step) * step + z; t <= S.view.b; t += step) {
    const x = Math.round(timeToX(t, w)) + .5;
    ctx.strokeStyle = '#3c424c';
    ctx.beginPath(); ctx.moveTo(x, RULER_H - 7); ctx.lineTo(x, RULER_H); ctx.stroke();
    ctx.fillStyle = '#7e8695';
    ctx.fillText(T.format(disp(t), step < 1 ? 2 : 0), x + 5, 12);
  }
}

// ---- zoom / pan ----

function clampView() {
  const lo = 0, hi = Math.max(S.audioDuration + audioOffset(),
                              ...S.turns.map(t => t.end), 60);
  let span = Math.min(S.view.b - S.view.a, hi - lo);
  span = Math.max(span, 4 / fps());          // nao passa de ~4 frames de largura
  if (S.view.a < lo) S.view.a = lo;
  S.view.b = S.view.a + span;
  if (S.view.b > hi) { S.view.b = hi; S.view.a = hi - span; }
  if (S.view.a < lo) S.view.a = lo;
}

function zoomAt(factor, pivotTime) {
  const span = (S.view.b - S.view.a) * factor;
  const frac = (pivotTime - S.view.a) / (S.view.b - S.view.a);
  S.view.a = pivotTime - span * frac;
  S.view.b = S.view.a + span;
  clampView(); draw();
}

function zoomFit() {
  if (S.turns.length) {
    const a = Math.min(...S.turns.map(t => t.start));
    const b = Math.max(...S.turns.map(t => t.end));
    const pad = (b - a) * .02;
    S.view = { a: a - pad, b: b + pad };
  } else {
    S.view = { a: audioOffset(), b: audioOffset() + S.audioDuration };
  }
  clampView(); draw();
}

function centerOn(t) {
  const span = S.view.b - S.view.a;
  S.view.a = t - span / 2; S.view.b = S.view.a + span;
  clampView(); draw();
}

function ensureVisible(t) {
  if (t < S.view.a || t > S.view.b) centerOn(t);
}

// ---- interacao na waveform ----

const EDGE_PX = 6;

function hitTest(x, y, w, h) {
  const laneY = h - LANE_H;
  const list = sorted();
  if (y >= laneY) {
    for (const t of list) {
      if (S.hidden.has(t.label ?? '')) continue;
      const x0 = timeToX(t.start, w), x1 = timeToX(t.end, w);
      if (Math.abs(x - x0) <= EDGE_PX) return { turn: t, edge: 'start' };
      if (Math.abs(x - x1) <= EDGE_PX) return { turn: t, edge: 'end' };
      if (x > x0 && x < x1) return { turn: t, edge: null };
    }
  }
  return null;
}

/* Move uma borda. Se "bordas coladas" estiver ligado e o vizinho compartilhar
   exatamente esse instante, os dois andam juntos - que e' o comportamento util
   pra diarizacao: mover o corte, nao abrir buraco. */
function moveEdge(turn, edge, time) {
  const f = fps();
  if (el.snapChk.checked) time = T.snap(time, f);
  const list = sorted();
  const i = list.indexOf(turn);
  const prev = list[i - 1], next = list[i + 1];
  const EPS = 1e-6;
  const minLen = minFrames() / f;

  if (edge === 'start') {
    let lo = prev ? prev.start + minLen : -Infinity;
    time = Math.min(Math.max(time, lo), turn.end - minLen);
    if (el.linkChk.checked && prev && Math.abs(prev.end - turn.start) < EPS) prev.end = time;
    turn.start = time;
  } else {
    let hi = next ? next.end - minLen : Infinity;
    time = Math.max(Math.min(time, hi), turn.start + minLen);
    if (el.linkChk.checked && next && Math.abs(next.start - turn.end) < EPS) next.start = time;
    turn.end = time;
  }
}

function wireWave() {
  const c = el.wave;

  c.addEventListener('wheel', ev => {
    ev.preventDefault();
    const { w } = waveMetrics();
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    // Shift e ctrl deslocam a timeline. O preventDefault la em cima e' o que
    // impede o ctrl+roda de virar zoom DA PAGINA no navegador.
    if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
      const d = (S.view.b - S.view.a) * (ev.deltaY > 0 ? .12 : -.12);
      S.view.a += d; S.view.b += d; clampView(); draw();
    } else {
      zoomAt(ev.deltaY > 0 ? 1.22 : 1 / 1.22, xToTime(x, w));
    }
  }, { passive: false });

  // Arrastes correm na WINDOW, nao no canvas: puxar o playhead ou uma borda
  // pra fora da area do canvas e' normal no meio do gesto, e ouvindo so o
  // canvas o arraste congelava assim que o ponteiro saia dele.
  window.addEventListener('mousemove', ev => {
    if (!S.drag && !S.scrub) return;
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const { w } = waveMetrics();

    if (S.drag) {
      moveEdge(S.drag.turn, S.drag.edge, xToTime(x, w));
      // NAO chamar renderTable() aqui: com 1690 turnos isso reconstruiria a
      // tabela inteira a cada mousemove. So os campos das linhas realmente
      // afetadas sao atualizados; o resto se ajeita no mouseup (refresh).
      touch();
      patchRowTimes(S.drag.turn);
      const viz = sorted();
      const i = viz.indexOf(S.drag.turn);
      patchRowTimes(viz[i - 1]); patchRowTimes(viz[i + 1]);
      draw();
    } else {
      scrubTo(xToTime(x, w));
    }
  });

  c.addEventListener('mousemove', ev => {
    if (S.drag || S.scrub) return;             // cursor ja definido no gesto
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    const { w, h } = waveMetrics();
    const hit = hitTest(x, y, w, h);
    c.style.cursor = hit && hit.edge ? 'ew-resize' : 'grab';
  });

  c.addEventListener('mousedown', ev => {
    // so o botao esquerdo: sem isso o botao direito tambem movia o playhead e
    // podia comecar um arraste de borda por baixo do menu
    if (ev.button !== 0) return;
    ev.preventDefault();                       // nao selecionar texto no arraste
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    const { w, h } = waveMetrics();
    const hit = hitTest(x, y, w, h);
    if (hit && hit.edge) {
      pushUndo();
      S.drag = hit;
      select(hit.turn.uid, false);   // sem rolar: atrapalharia o arraste
      c.style.cursor = 'ew-resize';
      return;
    }
    if (hit) select(hit.turn.uid);   // rola a lista ate a linha do bloco
    startScrub(xToTime(x, w));
  });

  window.addEventListener('mouseup', () => {
    if (S.drag) { S.drag = null; refresh(); }
    if (S.scrub) endScrub();
    c.style.cursor = 'grab';
  });

  c.addEventListener('contextmenu', ev => {
    ev.preventDefault();
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    const { w, h } = waveMetrics();
    const hit = hitTest(x, y, w, h);
    if (!hit) { closeSpeakerMenu(); return; }
    select(hit.turn.uid);          // rola a lista ate a linha correspondente
    openSpeakerMenu(hit.turn, ev.clientX, ev.clientY);
  });

  // Duplo clique abre o menu de falante, igual ao botao direito.
  //
  // Antes ele CORTAVA o turno no ponto clicado, e isso era perigoso: um duplo
  // clique acidental enquanto se navega partia um turno em dois sem nada de
  // evidente na tela, e o estrago so aparecia depois. Dividir continua no B e
  // no botao ⋮ da linha - lugares onde a intencao e' explicita.
  c.addEventListener('dblclick', ev => {
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    const { w, h } = waveMetrics();
    const hit = hitTest(x, y, w, h);
    if (!hit) return;
    select(hit.turn.uid);
    openSpeakerMenu(hit.turn, ev.clientX, ev.clientY);
  });

  new ResizeObserver(() => draw()).observe(c);
}

// ============================================================ edicoes

/* Atualiza so os campos de tempo/duracao de uma linha, sem recriar a tabela.
   Usado durante o arraste, onde recriar tudo custaria caro por evento. */
function patchRowTimes(turn) {
  if (!turn) return;
  const row = el.turnsBody.querySelector(`tr[data-uid="${turn.uid}"]`);
  if (!row) return;
  const [a, b] = row.querySelectorAll('input.time');
  if (a) a.value = T.format(disp(turn.start));
  if (b) b.value = T.format(disp(turn.end));
  const dur = row.querySelector('.c-dur');
  if (dur) dur.textContent = T.dur(Math.max(0, turn.end - turn.start));
  const fr = row.querySelector('.c-frames');
  if (fr) fr.textContent = T.spanFrames(turn.start, turn.end, fps()) + 'f';
}

/* Selecionar NAO pode reconstruir a tabela.
 *
 * Antes isso chamava renderTable(), que troca o <tbody> inteiro - entao clicar
 * no campo do falante destruia o proprio campo no meio do clique: o foco se
 * perdia e a lista nem chegava a abrir. Trocar de falante, que e' a funcao
 * principal, era impossivel pelo mouse. Aqui so a classe .sel se move. */
function select(uid, scroll = true) {
  S.sel = uid;
  el.turnsBody.querySelectorAll('tr.sel').forEach(r => r.classList.remove('sel'));
  const row = el.turnsBody.querySelector(`tr[data-uid="${uid}"]`);
  if (row) {
    row.classList.add('sel');
    if (scroll) row.scrollIntoView({ block: 'nearest' });
  }
  draw();
}

/* Leva o playhead e a janela da waveform pro turno. */
function goToTurn(t) {
  const at = toAudioTime(t.start);
  if (at < 0 || (S.audioDuration && at > S.audioDuration)) {
    toast('esse turno está fora do áudio carregado — confira o offset em Ajustes', 'err');
    return;
  }
  el.audio.currentTime = at;
  S.playUntil = null;
  const span = S.view.b - S.view.a;
  // so mexe na janela se o turno nao estiver visivel por inteiro - rolar a
  // waveform a cada clique numa linha ja visivel seria desorientador
  if (t.start < S.view.a || t.end > S.view.b) {
    if (t.end - t.start > span * .9) {
      const pad = (t.end - t.start) * .08;
      S.view = { a: t.start - pad, b: t.end + pad };
    } else {
      const mid = (t.start + t.end) / 2;
      S.view = { a: mid - span / 2, b: mid + span / 2 };
    }
    clampView();
  }
  draw();
}

/* ---- menu de falante na faixa ------------------------------------------
 *
 * Trocar quem fala e' a razao de existir deste editor, e ate agora so dava
 * pra fazer na tabela (ou sabendo o atalho 1-9). Mas quem esta ouvindo tem o
 * mouse na waveform, olhando os blocos - obrigar a descer pra lista quebra o
 * ritmo. Botao direito no bloco resolve onde a atencao ja esta.
 */
function openSpeakerMenu(turn, x, y) {
  const m = el.speakerMenu;
  const atual = turn.label ?? '';
  const nomes = labelChoices();
  const ordem = S.config?.speaker_order || [];

  const item = n => {
    const i = ordem.indexOf(n);
    return `<button class="mitem${n === atual ? ' on' : ''}" data-n="${escapeHtml(n)}">` +
           `<i class="sw${offCamera(n) ? ' ghost' : ''}" style="background:${colorFor(n)}"></i>` +
           `${escapeHtml(n)}` +
           `<span class="kb">${i >= 0 && i < 9 ? i + 1 : ''}</span></button>`;
  };
  // detectados em cima, decisao editorial embaixo: "cut" nao sai de nenhum
  // diarizador, entao listar junto com as pessoas confundiria as duas coisas
  const pessoas = nomes.filter(n => !manualOnly(n));
  const manuais = nomes.filter(manualOnly);

  m.innerHTML =
    `<div class="mhead">${T.format(disp(turn.start))} — <b>${
      escapeHtml(atual || 'sem falante')}</b></div>` +
    pessoas.map(item).join('') +
    (manuais.length
      ? `<div class="msep"></div><div class="mlabel">corte manual</div>` +
        manuais.map(item).join('')
      : '') +
    `<div class="msep"></div>` +
    `<button class="mitem novo" data-n="${NEW_LABEL}">＋ novo nome…</button>`;

  // posiciona no cursor, virando pra dentro quando esbarra na borda da janela
  m.classList.remove('hidden');
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, window.innerWidth - r.width - 8) + 'px';
  m.style.top = Math.min(y, window.innerHeight - r.height - 8) + 'px';
  m.dataset.uid = turn.uid;
  m.querySelector('.mitem')?.focus();
}

function closeSpeakerMenu() {
  el.speakerMenu.classList.add('hidden');
  el.speakerMenu.removeAttribute('data-uid');
}

function wireSpeakerMenu() {
  el.speakerMenu.addEventListener('click', ev => {
    const btn = ev.target.closest('.mitem');
    if (!btn) return;
    const turn = byUid(+el.speakerMenu.dataset.uid);
    closeSpeakerMenu();
    if (!turn) return;
    let n = btn.dataset.n;
    if (n === NEW_LABEL) {
      n = (prompt('Nome do falante:', '') || '').trim();
      if (!n) return;
    }
    setLabel(turn, n || null);
  });

  // fecha no primeiro clique/rolagem fora dele
  document.addEventListener('mousedown', ev => {
    if (!el.speakerMenu.classList.contains('hidden') &&
        !ev.target.closest('#speakerMenu')) closeSpeakerMenu();
  }, true);
  window.addEventListener('blur', closeSpeakerMenu);
  el.wave.addEventListener('wheel', closeSpeakerMenu, { passive: true });
}

function splitTurn(turn, at) {
  const f = fps();
  if (el.snapChk.checked) at = T.snap(at, f);
  const minLen = minFrames() / f;
  if (at <= turn.start + minLen || at >= turn.end - minLen) {
    toast('ponto de corte perto demais da borda — os dois lados ficariam ' +
          `abaixo de ${minFrames()} frames`, 'err');
    return;
  }
  pushUndo();
  const novo = {
    uid: S._uid++, start: at, end: turn.end,
    label: turn.label, extra: JSON.parse(JSON.stringify(turn.extra || {})),
  };
  turn.end = at;
  S.turns.push(novo);
  refresh();
  select(novo.uid);
}

function mergeWithNext(turn) {
  const list = sorted();
  const next = list[list.indexOf(turn) + 1];
  if (!next) { toast('não há turno seguinte pra juntar', 'err'); return; }
  pushUndo();
  turn.end = Math.max(turn.end, next.end);
  S.turns = S.turns.filter(t => t.uid !== next.uid);
  refresh();
  select(turn.uid);
}

function deleteTurn(turn) {
  pushUndo();
  S.turns = S.turns.filter(t => t.uid !== turn.uid);
  if (S.sel === turn.uid) S.sel = null;
  refresh();
}

/* Novo turno no buraco depois deste (ou 1s a partir do fim, se nao houver). */
function insertAfter(turn) {
  const list = sorted();
  const next = list[list.indexOf(turn) + 1];
  const start = turn.end;
  const end = next ? next.start : turn.end + 1;
  if (T.spanFrames(start, end, fps()) < minFrames()) {
    toast('não há espaço aqui — não existe buraco entre este turno e o ' +
          'seguinte. Use “dividir” pra criar um trecho novo.', 'err');
    return;
  }
  pushUndo();
  const novo = { uid: S._uid++, start, end, label: turn.label, extra: {} };
  S.turns.push(novo);
  refresh();
  select(novo.uid);
}

function setLabel(turn, label) {
  if (turn.label === label) return;
  pushUndo();
  turn.label = label;
  if (label && !S.labels.includes(label)) { S.labels.push(label); S.labels.sort(); }
  refresh();
}

function markIn()  {
  const t = byUid(S.sel); if (!t) return;
  pushUndo(); moveEdge(t, 'start', toTurnTime(el.audio.currentTime)); refresh();
}
function markOut() {
  const t = byUid(S.sel); if (!t) return;
  pushUndo(); moveEdge(t, 'end', toTurnTime(el.audio.currentTime)); refresh();
}

// ============================================================ audio

/* ---- arrastar o playhead (scrub) ---------------------------------------
 *
 * Segurar o botao em qualquer ponto da onda e puxar move o playhead junto.
 * Se estava tocando, pausa durante o arraste e volta a tocar ao soltar: sem
 * isso o <audio> recebe dezenas de seeks por segundo e o som vira picote.
 */
function startScrub(turnTime) {
  S.scrub = { tocava: !el.audio.paused };
  if (S.scrub.tocava) el.audio.pause();
  scrubTo(turnTime);
  el.wave.style.cursor = 'grabbing';
}

function endScrub() {
  const tocava = S.scrub.tocava;
  S.scrub = null;
  el.wave.style.cursor = 'grab';
  if (tocava) el.audio.play().catch(() => {});
}

/* Como seek(), mas silencioso: durante um arraste passar do fim do audio e'
   normal, e avisar em toast a cada quadro seria ruido. So limita e segue. */
function scrubTo(turnTime) {
  const max = S.audioDuration || Infinity;
  el.audio.currentTime = Math.min(Math.max(toAudioTime(turnTime), 0), max);
  S.playUntil = null;
  draw();
  // a linha da tabela acompanha o arraste, entao da' pra ler quem fala e o
  // texto do trecho enquanto voce procura o ponto
  highlightPlaying(toTurnTime(el.audio.currentTime));
}

function seek(turnTime) {
  const at = toAudioTime(turnTime);
  if (at < 0 || (S.audioDuration && at > S.audioDuration)) {
    toast(`${T.format(turnTime)} está fora do áudio carregado ` +
          `(${T.format(audioOffset(), 0)}–${T.format(audioOffset() + S.audioDuration, 0)}). ` +
          `Confira o offset ou escolha outro arquivo de áudio.`, 'err');
    return;
  }
  el.audio.currentTime = at;
  S.playUntil = null;
  draw();
}

/* ---- shuttle J/K/L, como em qualquer ilha de edicao ---------------------
 *
 * L sobe a escada, J desce. Abaixo de 1x entra de proposito: pra achar o
 * instante exato em que alguem comeca a falar, desacelerar ajuda mais do que
 * acelerar. O navegador mantem o tom (preservesPitch), entao a fala continua
 * inteligivel em 2-3x.
 *
 * Nao ha reproducao para tras: playbackRate negativo nao existe no <audio> do
 * navegador. J desce ate 1/4 e para ali.
 */
const RATES = [0.25, 0.5, 1, 2, 3, 4];

function setRate(r, andPlay = false) {
  S.rate = r;
  el.audio.preservesPitch = true;   // sem isso 3x vira voz de esquilo
  el.audio.playbackRate = r;
  el.rate.textContent = (r === Math.trunc(r) ? r : r === .5 ? '½' : '¼') + '×';
  el.rate.classList.toggle('hidden', r === 1);   // 1x nao merece selo
  if (andPlay && el.audio.paused) {
    el.audio.play().catch(e => toast(e.message, 'err'));
  }
}

function shuttle(dir) {
  let i = RATES.indexOf(S.rate);
  if (i < 0) i = RATES.indexOf(1);
  const j = Math.min(RATES.length - 1, Math.max(0, i + dir));
  if (j === i && !el.audio.paused) return;   // ja esta na ponta da escada
  S.playUntil = null;                        // shuttle sai do modo "tocar turno"
  setRate(RATES[j], true);
}

function togglePlay() {
  if (el.audio.paused) {
    S.playUntil = null;
    setRate(1);                              // Espaco sempre volta pra 1x
    el.audio.play().catch(e => toast(e.message, 'err'));
  } else {
    el.audio.pause();
  }
  el.playBtn.textContent = el.audio.paused ? '▶' : '❚❚';
}

function playTurn() {
  const t = byUid(S.sel);
  if (!t) { toast('selecione um turno primeiro'); return; }
  const at = toAudioTime(t.start);
  if (at < 0 || (S.audioDuration && at > S.audioDuration)) {
    toast('esse turno está fora do áudio carregado — confira o offset', 'err');
    return;
  }
  el.audio.currentTime = at;
  S.playUntil = t.end;
  el.audio.play().catch(e => toast(e.message, 'err'));
  el.playBtn.textContent = '❚❚';
}

/* Loop de UI: relogio, playhead, parar no fim do turno, seguir a reproducao. */
function tick() {
  const tt = toTurnTime(el.audio.currentTime || 0);
  el.clock.textContent = T.format(disp(tt));
  el.clockTc.textContent = T.timecode(Math.max(0, disp(tt)), fps());
  // o tempo absoluto continua visivel embaixo: e' o que esta gravado no json,
  // e some-lo de vista seria trocar uma confusao por outra
  el.clockAbs.textContent = S.baseRel ? `mídia ${T.format(tt)}` : '';

  if (S.playUntil != null && tt >= S.playUntil) {
    el.audio.pause();
    el.playBtn.textContent = '▶';
    S.playUntil = null;
  }
  if (!el.audio.paused) {
    if (el.followChk.checked) {
      const span = S.view.b - S.view.a;
      if (tt < S.view.a + span * .1 || tt > S.view.b - span * .1) centerOn(tt);
    }
    draw();
    highlightPlaying(tt);
  }
  requestAnimationFrame(tick);
}

function highlightPlaying(tt) {
  const cur = sorted().find(t => tt >= t.start && tt < t.end);
  const uid = cur ? cur.uid : null;
  if (uid === highlightPlaying._last) return;
  highlightPlaying._last = uid;
  el.turnsBody.querySelectorAll('tr.playing').forEach(r => r.classList.remove('playing'));
  if (uid != null) {
    const row = el.turnsBody.querySelector(`tr[data-uid="${uid}"]`);
    if (row) row.classList.add('playing');
  }
}

// ============================================================ tabela

function refresh() {
  touch();
  renderFilters();
  renderTable();
  renderStats();
  draw();
}

function renderFilters() {
  const names = [...new Set(S.turns.map(t => t.label ?? ''))].sort();
  el.speakerFilter.innerHTML = names.map(n => {
    const off = S.hidden.has(n) ? ' off' : '';
    const count = S.turns.filter(t => (t.label ?? '') === n).length;
    return `<span class="chip${off}" data-name="${escapeHtml(n)}" ` +
           `title="${count} turno(s) — clique para mostrar ou esconder">` +
           `<i class="sw${offCamera(n) ? ' ghost' : ''}" ` +
           `style="background:${colorFor(n)}"></i>` +
           `${escapeHtml(n) || '—'}<span class="n">${count}</span></span>`;
  }).join('');
  el.speakerFilter.querySelectorAll('.chip').forEach(c => {
    c.onclick = () => {
      const n = c.dataset.name;
      S.hidden.has(n) ? S.hidden.delete(n) : S.hidden.add(n);
      refresh();
    };
  });
}

function renderStats() {
  const f = fps();
  const total = S.turns.reduce((a, t) => a + Math.max(0, t.end - t.start), 0);
  const per = {};
  for (const t of S.turns) {
    const k = t.label ?? '—';
    per[k] = (per[k] || 0) + Math.max(0, t.end - t.start);
  }
  const share = Object.entries(per).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => {
      const nome = k === '—' ? '' : k;
      return `<span title="${escapeHtml(k)}: ${T.dur(v)}">` +
        `<i class="sw dot${offCamera(nome) ? ' ghost' : ''}" ` +
        `style="background:${colorFor(nome)}"></i>` +
        `<span class="num">${(v / total * 100).toFixed(1)}%</span></span>`;
    }).join(' ');

  const issues = computeIssues();
  let short = 0, over = 0, gaps = 0;
  for (const arr of issues.values()) for (const i of arr) {
    if (i.kind === 'short' || i.kind === 'invalid') short++;
    else if (i.kind === 'overlap') over++;
    else if (i.kind === 'gap') gaps++;
  }
  // so acende quando ha o que olhar - zero problema nao merece cor nem destaque
  const flag = (n, txt, cls) =>
    `<span class="${n ? cls : ''}" title="${txt}">` +
    `<span class="num">${n}</span> ${txt}</span>`;

  el.stats.innerHTML =
    `<span><span class="num">${S.turns.length}</span> turnos</span>` +
    `<span class="sep">|</span>` +
    `<span><span class="num">${T.dur(total)}</span> de fala</span>` +
    `<span class="sep">|</span>${share}` +
    `<span class="sep">|</span>` +
    flag(short, 'curtos', 'bad') +
    flag(over, 'sobrepõem', 'warn') +
    flag(gaps, 'buracos', '');
}

function visibleTurns() {
  const q = S.query.toLowerCase();
  return sorted().filter(t => {
    if (S.hidden.has(t.label ?? '')) return false;
    if (!q) return true;
    return (t.label || '').toLowerCase().includes(q) ||
           textFor(t).toLowerCase().includes(q);
  });
}

function renderTable() {
  const f = fps(), issues = computeIssues();
  const rows = visibleTurns();
  const frag = document.createDocumentFragment();
  const idxOf = new Map(sorted().map((t, i) => [t.uid, i]));

  for (const t of rows) {
    const tr = document.createElement('tr');
    tr.dataset.uid = t.uid;
    if (t.uid === S.sel) tr.className = 'sel';

    const iss = issues.get(t.uid) || [];
    const flags = iss.map(i =>
      `<span class="flag ${i.kind}" title="${i.msg.replace(/"/g, '&quot;')}">` +
      `${{short:'curto',overlap:'sobrepõe',gap:'buraco',invalid:'inválido'}[i.kind]}</span>`).join('');

    const extras = Object.entries(t.extra || {})
      .map(([k, v]) => `<span class="extra" title="campo extra preservado no salvamento">${k}=${
        String(v).slice(0, 40)}</span>`).join('');

    const dur = t.end - t.start;
    const nf = T.spanFrames(t.start, t.end, f);

    tr.innerHTML = `
      <td class="c-idx">${idxOf.get(t.uid) + 1}</td>
      <td class="c-time"><input class="time" data-k="start" value="${T.format(disp(t.start))}"></td>
      <td class="c-time"><input class="time" data-k="end" value="${T.format(disp(t.end))}"></td>
      <td class="c-dur">${T.dur(Math.max(0, dur))}</td>
      <td class="c-frames">${nf}f</td>
      <td class="c-name">
        <div class="namecell">
          <i class="sw${offCamera(t.label) ? ' ghost' : ''}"
             style="background:${colorFor(t.label)}"></i>
          ${labelSelect(t.label)}
        </div>
      </td>
      <td class="c-text">${escapeHtml(textFor(t))}${flags ? ' <span class="flags">' + flags + '</span>' : ''}${extras}</td>
      <td class="c-act">
        <button class="iconbtn" data-a="play"   title="Tocar este turno">▶</button>
        <button class="iconbtn" data-a="split"  title="Dividir no meio">⋮</button>
        <button class="iconbtn" data-a="merge"  title="Juntar com o seguinte">⇥</button>
        <button class="iconbtn" data-a="insert" title="Inserir turno no buraco seguinte">+</button>
        <button class="iconbtn warnish" data-a="del" title="Apagar">✕</button>
      </td>`;
    frag.appendChild(tr);
  }

  el.turnsBody.replaceChildren(frag);
  highlightPlaying._last = undefined;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/* Sentinela da opcao "novo nome...". Precisa ser algo que nunca seja um nome
   de verdade; ASCII explicito de proposito - a primeira versao disto acabou
   com um U+0000 literal no meio do fonte, que funcionava por acidente. */
const NEW_LABEL = '__novo__';

/* Nomes oferecidos na lista: os do speaker_order primeiro (assim a ordem bate
   com as teclas 1-9), depois qualquer outro que apareca no arquivo. */
function labelChoices() {
  const out = [];
  for (const n of (S.config?.speaker_order || [])) if (!out.includes(n)) out.push(n);
  for (const n of S.labels) if (n && !out.includes(n)) out.push(n);
  return out;
}

/* <select> nativo em vez de input+datalist: um clique abre, outro escolhe.
   O datalist so abria se voce acertasse a setinha de 10px - pra funcao que
   mais se usa neste editor, isso era o caminho errado. */
function labelSelect(label) {
  const cur = label ?? '';
  const opts = labelChoices();
  if (cur && !opts.includes(cur)) opts.unshift(cur);
  // sem sufixo de atalho no texto: o <select> fechado mostra o texto da opcao
  // escolhida, e "Giovanni ·1" em 200 linhas so atrapalha a leitura
  const linhas = opts.map(n =>
    `<option value="${escapeHtml(n)}"${n === cur ? ' selected' : ''}>` +
    `${escapeHtml(n)}</option>`).join('');
  const vazio = cur ? '' : '<option value="" selected>—</option>';
  return `<select class="name" aria-label="Falante">${vazio}${linhas}` +
         `<option value="${NEW_LABEL}">＋ novo nome…</option></select>`;
}

/* Delegacao: a tabela e' recriada a cada edicao, entao prender listener em
   cada linha seria desperdicio (e fonte de listener vazado). */
function wireTable() {
  el.turnsBody.addEventListener('click', ev => {
    const tr = ev.target.closest('tr');
    if (!tr) return;
    const t = byUid(+tr.dataset.uid);
    if (!t) return;
    const btn = ev.target.closest('.iconbtn');
    if (!btn) {
      select(t.uid, false);
      // clicar na linha leva a timeline pra ela. Nao vale quando o clique foi
      // num controle: abrir a lista de falante ou editar um tempo nao deve
      // arrastar o playhead junto.
      if (!ev.target.closest('select, input, button')) goToTurn(t);
      return;
    }
    switch (btn.dataset.a) {
      case 'play':   select(t.uid, false); playTurn(); break;
      case 'split':  splitTurn(t, (t.start + t.end) / 2); break;
      case 'merge':  mergeWithNext(t); break;
      case 'insert': insertAfter(t); break;
      case 'del':    deleteTurn(t); break;
    }
  });

  el.turnsBody.addEventListener('focusin', ev => {
    const tr = ev.target.closest('tr');
    if (tr) { S.sel = +tr.dataset.uid;
      el.turnsBody.querySelectorAll('tr.sel').forEach(r => r.classList.remove('sel'));
      tr.classList.add('sel'); draw(); }
  });

  el.turnsBody.addEventListener('change', ev => {
    const tr = ev.target.closest('tr');
    if (!tr) return;
    const t = byUid(+tr.dataset.uid);
    if (!t) return;

    if (ev.target.classList.contains('name')) {
      let v = ev.target.value;
      if (v === NEW_LABEL) {
        v = (prompt('Nome do falante:', '') || '').trim();
        if (!v) { ev.target.value = t.label ?? ''; return; }  // cancelou
      }
      setLabel(t, v.trim() || null);
      return;
    }
    if (ev.target.classList.contains('time')) {
      const v = T.parse(ev.target.value);
      if (v == null) {
        ev.target.classList.add('bad');
        toast('não entendi esse tempo. Use 43:30.500, 1:03:30.1 ou 2610', 'err');
        return;
      }
      ev.target.classList.remove('bad');
      pushUndo();
      const k = ev.target.dataset.k;
      // o campo esta na base mostrada; o dado guardado e' sempre absoluto
      const abs = undisp(v);
      t[k] = el.snapChk.checked ? T.snap(abs, fps()) : abs;
      refresh();
      ensureVisible(t[k]);
    }
  });

  el.turnsBody.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && ev.target.tagName === 'INPUT') ev.target.blur();
  });
}

// ============================================================ salvar

function openSave() {
  // Sempre o mesmo destino: o trabalho manual vai todo pra um arquivo so,
  // independente de qual diarizacao serviu de base. Antes o nome era derivado
  // do arquivo aberto, entao salvar duas vezes seguidas gerava
  // turnsManual_edit.json - e a correcao acabava espalhada por varios arquivos.
  const nome = S.config?.default_save_name || 'turnsManual.json';
  el.saveName.value = nome;
  // como o destino se repete, ja deixa a sobrescrita marcada quando o arquivo
  // existe: o fluxo vira Ctrl+S -> Enter, e o .bak continua sendo gerado
  el.saveOverwrite.checked = S.turnFiles.includes(nome);
  updateSaveHint();
  el.saveModal.classList.remove('hidden');
  el.saveName.focus();
  el.saveName.select();
}

function updateSaveHint() {
  const issues = computeIssues();
  let bad = 0;
  for (const arr of issues.values())
    for (const i of arr) if (i.kind === 'short' || i.kind === 'invalid') bad++;
  el.saveHint.innerHTML = bad
    ? `⚠ ${bad} turno(s) ficariam abaixo de ${minFrames()} frames e sumiriam no ` +
      `SpeakerSwitch. Dá pra salvar assim mesmo, mas confira antes.`
    : `Salva em <code>${S.config.results_dir}</code>. Os originais nunca são ` +
      `apagados: sobrescrever gera um <code>.bak</code> com data e hora.`;
}

async function doSave() {
  const body = {
    file: S.file,
    save_as: el.saveName.value.trim(),
    label_key: el.saveLabelKey.value,
    overwrite: el.saveOverwrite.checked,
    snap_to_frames: el.saveSnap.checked,
    turns: sorted().map(t => ({
      start: t.start, end: t.end, label: t.label, extra: t.extra || {},
    })),
  };
  try {
    const r = await apiJson('/api/turns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    el.saveModal.classList.add('hidden');
    S.baseline = snapshot();   // o que esta em disco agora e' este estado
    setDirty(false);
    toast(`Salvo: ${body.save_as} (${r.count} turnos)` +
          (r.backup ? ` · backup em ${r.backup}` : ''), 'ok');
    const info = await apiJson('/api/config');
    const cur = el.fileSelect.value;
    S.turnFiles = info.turn_files.map(f => f.name);
    el.fileSelect.innerHTML = info.turn_files.map(f =>
      `<option value="${f.name}">${f.name} — ${f.count} turnos, ` +
      `${T.format(f.span[0], 0)}→${T.format(f.span[1], 0)}</option>`).join('');
    el.fileSelect.value = info.turn_files.some(f => f.name === body.save_as)
      ? body.save_as : cur;
    S.file = el.fileSelect.value;
  } catch (e) {
    if (/ja existe/.test(e.message)) {
      el.saveOverwrite.checked = true;
      toast(e.message + ' — marque "sobrescrever" e confirme.', 'err');
    } else {
      toast('Falhou ao salvar: ' + e.message, 'err');
    }
  }
}

// ============================================================ eventos

function wireEvents() {
  wireWave();
  wireTable();
  wireSpeakerMenu();

  el.fileSelect.onchange = async () => {
    if (S.dirty && !confirm('Há alterações não salvas. Trocar de arquivo mesmo assim?')) {
      el.fileSelect.value = S.file; return;
    }
    await loadTurns(el.fileSelect.value);
    zoomFit();
    goToStart();
  };

  el.audioSelect.onchange = async () => {
    await patchConfig({ audio_file: el.audioSelect.value });
    await loadAudio();
    toast(`Áudio: ${el.audioSelect.value}. Confira o offset — ` +
          `arquivos recortados começam depois do zero do episódio.`);
  };

  el.audioOffset.onchange = async () => {
    await patchConfig({ audio_offset: parseFloat(el.audioOffset.value) || 0 });
    draw();
  };

  el.transcriptOffset.onchange = async () => {
    await patchConfig({ transcript_offset: parseFloat(el.transcriptOffset.value) || 0 });
    await loadTranscript();
    renderTable();
  };

  el.fps.onchange = async () => {
    await patchConfig({ fps: parseFloat(el.fps.value) || 60 });
    refresh();
  };

  // ---- base de tempo ----
  const setBase = async rel => {
    S.baseRel = rel;
    await patchConfig({ time_base: rel ? 'relative' : 'absolute' });
    applyBase();
  };
  el.baseRel.onclick = () => setBase(true);
  el.baseAbs.onclick = () => setBase(false);

  el.zeroAt.onchange = async () => {
    const v = T.parse(el.zeroAt.value);
    if (v == null) {
      toast('não entendi esse tempo. Use 43:30.000 ou 2610', 'err');
      el.zeroAt.value = T.format(S.zero);
      return;
    }
    S.zero = v;
    await patchConfig({ display_zero: v });
    applyBase();
  };

  el.zeroReset.onclick = async () => {
    S.zero = firstStart();
    // display_zero volta pra null (automatico): o zero passa a acompanhar o
    // primeiro turno de cada arquivo que voce abrir
    await apiJson('/api/config?clear=display_zero', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then(r => { S.config = r.config; });
    applyBase();
    toast(`Zero em ${T.format(S.zero)} — o primeiro turno deste arquivo.`);
  };

  // ---- ajustes ----
  el.cfgBtn.onclick = () => {
    el.audioOffset.value = S.config.audio_offset;
    el.transcriptOffset.value = S.config.transcript_offset;
    el.fps.value = S.config.fps;
    el.zeroAt.value = T.format(S.zero);
    el.cfgModal.classList.remove('hidden');
  };
  el.cfgClose.onclick = () => el.cfgModal.classList.add('hidden');
  el.cfgModal.onclick = ev => {
    if (ev.target === el.cfgModal) el.cfgModal.classList.add('hidden');
  };

  el.playBtn.onclick = togglePlay;
  el.playTurnBtn.onclick = playTurn;
  el.zoomIn.onclick = () => zoomAt(1 / 1.5, (S.view.a + S.view.b) / 2);
  el.zoomOut.onclick = () => zoomAt(1.5, (S.view.a + S.view.b) / 2);
  el.zoomFit.onclick = zoomFit;
  el.undoBtn.onclick = undo;
  el.redoBtn.onclick = redo;
  el.saveBtn.onclick = openSave;
  el.saveCancel.onclick = () => el.saveModal.classList.add('hidden');
  el.saveConfirm.onclick = doSave;
  el.helpBtn.onclick = () => el.helpModal.classList.remove('hidden');
  el.helpClose.onclick = () => el.helpModal.classList.add('hidden');
  el.search.oninput = () => { S.query = el.search.value; renderTable(); };

  el.audio.addEventListener('pause', () => el.playBtn.textContent = '▶');
  el.audio.addEventListener('play',  () => el.playBtn.textContent = '❚❚');
  el.audio.addEventListener('error', () => toast(
    'não consegui carregar o áudio. O arquivo está na pasta de mídia configurada?', 'err'));

  window.addEventListener('beforeunload', ev => {
    if (S.dirty) { ev.preventDefault(); ev.returnValue = ''; }
  });

  document.addEventListener('keydown', ev => {
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName);

    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
      ev.preventDefault(); openSave(); return;
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
      ev.preventDefault(); ev.shiftKey ? redo() : undo(); return;
    }
    if (ev.key === 'Escape') {
      closeSpeakerMenu();
      el.saveModal.classList.add('hidden');
      el.helpModal.classList.add('hidden');
      el.cfgModal.classList.add('hidden');
      if (typing) ev.target.blur();
      return;
    }
    if (typing) return;

    const list = visibleTurns();
    const i = list.findIndex(t => t.uid === S.sel);
    const cur = byUid(S.sel);

    switch (ev.key) {
      case ' ':
        ev.preventDefault(); togglePlay(); break;
      case 'l': case 'L':
        ev.preventDefault(); shuttle(+1); break;
      case 'j': case 'J':
        ev.preventDefault(); shuttle(-1); break;
      case 'k': case 'K':
        ev.preventDefault();
        el.audio.pause(); setRate(1); el.playBtn.textContent = '▶'; break;
      case 'Enter':
        ev.preventDefault(); playTurn(); break;
      case 'ArrowDown':
        ev.preventDefault();
        if (list.length) { const n = list[Math.min(i + 1, list.length - 1)];
          select(n.uid); ensureVisible(n.start); } break;
      case 'ArrowUp':
        ev.preventDefault();
        if (list.length) { const n = list[Math.max(i - 1, 0)];
          select(n.uid); ensureVisible(n.start); } break;
      // B de "blade", a mesma tecla de lamina do Resolve
      case 'b': case 'B':
        if (cur) splitTurn(cur, toTurnTime(el.audio.currentTime)); break;
      case 'm': case 'M':
        if (cur) mergeWithNext(cur); break;
      case 'i': case 'I': markIn(); break;
      case 'o': case 'O': markOut(); break;
      case 'Delete': case 'Backspace':
        if (cur) deleteTurn(cur); break;
      case '?': el.helpModal.classList.remove('hidden'); break;
      default:
        if (/^[1-9]$/.test(ev.key) && cur) {
          const order = S.config.speaker_order || S.labels;
          const name = order[+ev.key - 1];
          if (name) setLabel(cur, name);
        }
    }
  });
}

boot().catch(e => {
  document.body.innerHTML =
    `<div style="padding:40px;font-family:system-ui;color:#dbe3ec">
       <h2 style="color:#f2685b">Não consegui iniciar</h2>
       <p>${escapeHtml(e.message)}</p>
       <p style="color:#8a97a8">Confira <code>config.json</code> — as pastas
       <code>results_dir</code> e <code>media_dir</code> precisam existir.</p>
     </div>`;
});
