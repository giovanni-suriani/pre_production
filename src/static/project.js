/* Etapa 1 - ProjectEditor.
 *
 * Escolher o vídeo, dar nome, dizer quem está na mesa, extrair o wav.
 *
 * Duas decisões que valem explicar:
 *
 *  - O vídeo é escolhido por CAMINHO, não por upload. O `<input type=file>` do
 *    navegador entrega o conteúdo do arquivo; aqui o episódio tem 3 GB e já
 *    está no disco, então o que interessa é o caminho. Daí a lista da pasta de
 *    origem mais o diálogo nativo do Windows (aberto pelo servidor, num
 *    processo separado — mesmo truque que o SpeakerSwitch.py já usa).
 *
 *  - A cadeira de cada participante é perguntada agora, e não na etapa 2,
 *    porque ela é propriedade da PESSOA (onde ela senta), não do corte. Na
 *    etapa 2 ela vira o palpite de track.
 */

const SEATS = [
  ['left', 'esquerda'], ['center', 'centro'], ['right', 'direita'],
  ['none', 'sem cadeira fixa'],
];

let STATE = null;
let PROJECTS = [];
let NEW_SRC = null;         // {path, info} do vídeo escolhido
let SELECTED = null;        // projeto aberto no detalhe

const el = (id) => document.getElementById(id);

// ------------------------------------------------------- participantes

/* Uma linha = uma pessoa. `no_name` não aparece aqui: ele não é participante,
   é o rótulo do que sobra — a voz sem enquadramento. Deixá-lo editável
   convidaria a apagá-lo, e aí toda fala fora de quadro viraria erro de
   digitação em vez de cair na V1. */
/* Que cadeira cada pessoa ocupa quando você só disse QUANTAS são.
   Uma pessoa fica no centro (é onde a câmera única enquadra); duas ficam nas
   pontas e o centro fica VAZIO de propósito - e é justamente isso que agora é
   dito ao Gemini, em vez de deixá-lo supor uma mesa de três. A quarta pessoa
   entra sem cadeira fixa: só existem três enquadramentos (V1/V2/V3). */
const SEATS_BY_COUNT = {
  1: ['center'],
  2: ['left', 'right'],
  3: ['left', 'center', 'right'],
  4: ['left', 'center', 'right', 'none'],
};

/* Refaz a lista com N linhas, preservando o que já foi digitado. Mexer no
   número é decidir a mesa inteira - por isso as cadeiras voltam ao padrão
   daquele número, e não ao que sobrou do número anterior. */
function setPartCount(container, n) {
  const atuais = readParts(container);
  const cadeiras = SEATS_BY_COUNT[n] || SEATS_BY_COUNT[3];
  fillParts(container, cadeiras.map((seat, i) => ({
    name: (atuais[i] && atuais[i].name) || '', seat,
  })));
}

/* "3 pessoas na mesa + 1 fora de quadro = 4 vozes" - o mesmo número que a
   etapa 2 vai pedir ao diarizador (projects.default_speakers). Escrever isto
   na tela evita o caso que gerou tudo isto: rodar procurando 3 vozes numa
   conversa de 2. */
function voicesNote(container, offcamOn) {
  // conta LINHAS, não nomes preenchidos: no formulário novo os campos começam
  // vazios e a nota precisa dizer o tamanho da mesa desde antes de digitar.
  const n = container.querySelectorAll('.row').length;
  const off = offcamOn ? 1 : 0;
  const total = n + off;
  return `A diarização vai procurar <b>${total} ${total === 1 ? 'voz' : 'vozes'}</b>`
    + ` em todo corte deste projeto (${n} em quadro`
    + (off ? ' + 1 fora de quadro' : ', ninguém fora de quadro') + ').';
}

function partRow(container, value) {
  const row = h('div', 'row');
  row.style.gap = '8px';
  const name = h('input');
  name.type = 'text';
  name.placeholder = 'nome';
  name.value = value ? value.name : '';
  name.style.flex = '1';
  const seat = h('select');
  seat.innerHTML = SEATS.map(([v, t]) =>
    `<option value="${v}">${t}</option>`).join('');
  seat.value = (value && value.seat) || 'none';
  seat.style.width = '170px';
  const del = h('button', 'btn small danger', '×');
  del.title = 'remover';
  del.onclick = () => { row.remove(); syncVoices(container.id[0]); };
  row.append(name, seat, del);
  container.appendChild(row);
  return row;
}

function readParts(container) {
  return [...container.querySelectorAll('.row')].map((r) => ({
    name: r.querySelector('input').value.trim(),
    seat: r.querySelector('select').value,
  })).filter((p) => p.name);
}

/* `pref` é 'n' (novo projeto) ou 'd' (detalhe) - os dois formulários têm os
   mesmos campos com prefixo diferente. */
function syncVoices(pref) {
  const nota = el(pref + 'Voices');
  if (!nota) return;
  nota.innerHTML = voicesNote(el(pref + 'Parts'), el(pref + 'Offcam').checked);
  const sel = el(pref + 'Count');
  const n = el(pref + 'Parts').querySelectorAll('.row').length;
  if (sel && n >= 1 && n <= 4) sel.value = String(n);
}

function fillParts(container, list) {
  container.innerHTML = '';
  (list && list.length ? list : [{ name: '', seat: 'left' },
    { name: '', seat: 'center' }, { name: '', seat: 'right' }])
    .forEach((p) => partRow(container, p));
}

// ------------------------------------------------------------ projetos

function specCard(label, value, hint) {
  return `<div class="field"><span class="lbl">${label}</span>
    <div class="num">${escapeHtml(value)}</div>
    ${hint ? `<div class="sub" style="font-size:11.5px">${escapeHtml(hint)}</div>` : ''}
  </div>`;
}

function specsHtml(info) {
  const fps = info.fps ? info.fps.toFixed(3).replace(/\.?0+$/, '') : '?';
  return [
    specCard('duração', formatTime(info.duration || 0, 1),
      `${toFrame(info.duration || 0, info.fps || 60)} frames`),
    specCard('imagem', `${info.width || '?'}×${info.height || '?'} · ${fps} fps`,
      info.vcodec || ''),
    specCard('áudio', `${info.acodec || '?'} · ${info.sample_rate || '?'} Hz · ${
      info.channels === 1 ? 'mono' : `${info.channels} canais`}`,
    humanBytes(info.size)),
  ].join('');
}

function renderProjects() {
  const list = el('projList');
  list.innerHTML = '';
  el('projCount').textContent = PROJECTS.length
    ? `${PROJECTS.length} projeto${PROJECTS.length > 1 ? 's' : ''}` : '';
  el('projEmpty').classList.toggle('hidden', PROJECTS.length > 0);
  for (const p of PROJECTS) {
    const item = h('div', 'item');
    const cuts = (p.cuts || []).length;
    const ready = p.status === 'pronto';
    item.innerHTML = `
      <div class="t">${escapeHtml(p.name)}</div>
      <div class="d">${escapeHtml((p.participants || []).map((x) => x.name).join(' · '))}
        ${cuts ? ` — ${cuts} corte${cuts > 1 ? 's' : ''}` : ''}</div>
      <div class="side">
        <span class="num sub">${formatTime(p.duration || 0, 0)}</span>
        <span class="badge ${ready ? 'ok' : 'warn'}">${escapeHtml(p.status || '')}</span>
      </div>`;
    item.onclick = () => openDetail(p.slug);
    if (SELECTED && SELECTED.slug === p.slug) item.classList.add('on');
    list.appendChild(item);
  }
}

async function openDetail(slug) {
  const d = await api(`/api/projects/${encodeURIComponent(slug)}`);
  SELECTED = d.project;
  const p = d.project;
  el('detail').classList.remove('hidden');
  el('dName').textContent = p.name;
  el('dPath').textContent = p.source_video;
  el('dSpecs').innerHTML = specsHtml(p.media || {});
  el('dTitle').value = p.name;
  fillParts(el('dParts'), p.participants);
  el('dOffcam').checked = (p.off_camera || []).length > 0;
  el('dSplit').checked = !!p.split_screen;
  syncVoices('d');
  const note = el('dAudioNote');
  if (d.audio_exists && p.audio_info) {
    note.innerHTML = `Áudio pronto: <code>${escapeHtml(p.audio)}</code> —
      ${p.audio_info.sample_rate} Hz, ${p.audio_info.channels === 1 ? 'mono' : 'estéreo'},
      ${formatTime(p.audio_info.duration, 1)}.`;
  } else {
    note.innerHTML = 'O áudio ainda não foi extraído — sem ele a etapa 2 não '
      + 'tem o que fatiar.';
  }
  el('dGoCuts').disabled = !d.audio_exists;
  renderProjects();
  await renderTranscribeSection(d);
  el('detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ---------------------------------- transcrição inteira / sugestões de corte

let PROJECT_METHODS = null;

async function loadProjectMethods() {
  if (!PROJECT_METHODS) {
    try { PROJECT_METHODS = await api('/api/project-methods'); } catch (e) { oops(e); return null; }
  }
  return PROJECT_METHODS;
}

const SHORTS_OUTRO = '__outro__';   // sentinela: jamais é um nome de modelo real

/* Mesmo padrão do seletor de modelo do Gemini na etapa 2 (cortes.js,
   buildSuggestField): select visível + "outro modelo…" com campo livre,
   porque o catálogo do Gemini muda mais rápido do que este código. Duplicado
   aqui (em vez de importado) porque `cortes.js` só carrega em `/cortes`. */
function buildModelField(box, k, spec) {
  const cur = spec.default;
  const norm = spec.suggest.map((s) => (typeof s === 'string' ? { id: s, label: s } : s));
  const known = norm.some((s) => s.id === cur) ? norm : [{ id: cur, label: cur }, ...norm];
  const f = h('div', 'field');
  f.style.width = '240px';
  f.insertAdjacentHTML('afterbegin', `<span class="lbl">${escapeHtml(spec.label)}</span>`);
  const sel = h('select');
  sel.innerHTML = known.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.label)}</option>`).join('')
    + `<option value="${SHORTS_OUTRO}">outro modelo…</option>`;
  sel.value = cur;
  const free = h('input');
  free.type = 'text';
  free.placeholder = 'nome exato do modelo';
  free.className = 'hidden';
  free.style.marginTop = '6px';
  const hold = h('input');
  hold.type = 'hidden';
  hold.dataset.opt = k;
  hold.value = cur;
  const sync = () => {
    const outro = sel.value === SHORTS_OUTRO;
    free.classList.toggle('hidden', !outro);
    if (outro && !free.value) free.value = cur;
    hold.value = outro ? free.value.trim() : sel.value;
  };
  sel.onchange = () => { sync(); if (sel.value === SHORTS_OUTRO) free.focus(); };
  free.oninput = sync;
  f.append(sel, free, hold);
  box.appendChild(f);
}

function buildOptFields(box, options) {
  box.innerHTML = '';
  for (const [k, spec] of Object.entries(options || {})) {
    if (spec.suggest) { buildModelField(box, k, spec); continue; }
    const f = h('div', 'field');
    f.style.width = '160px';
    const input = spec.choices ? h('select') : h('input');
    if (spec.choices) {
      input.innerHTML = spec.choices.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    } else if (typeof spec.default === 'number') {
      input.type = 'number';
      if (spec.min !== undefined) input.min = spec.min;
      if (spec.max !== undefined) input.max = spec.max;
    } else {
      input.type = 'text';
    }
    input.value = spec.default;
    input.dataset.opt = k;
    f.insertAdjacentHTML('afterbegin', `<span class="lbl">${escapeHtml(spec.label)}</span>`);
    f.appendChild(input);
    box.appendChild(f);
  }
}

function readOptFields(box) {
  const out = {};
  for (const i of box.querySelectorAll('[data-opt]')) {
    out[i.dataset.opt] = i.type === 'number' ? parseFloat(i.value) : i.value;
  }
  return out;
}

async function renderShortsList(slug) {
  const box = el('dShortsList');
  try {
    const d = await api(`/api/projects/${encodeURIComponent(slug)}/suggested-shorts`);
    box.innerHTML = d.clips.map((c) => `
      <div class="item" style="cursor:default">
        <div class="t">${escapeHtml(c.title)}</div>
        <div class="d">${escapeHtml((c.transcript || '').slice(0, 140))}${
    (c.transcript || '').length > 140 ? '…' : ''}</div>
        <div class="side"><span class="num sub">${formatTime(c.start)} → ${formatTime(c.end)}
          (${formatTime(c.duration, 0)})</span></div>
      </div>`).join('');
  } catch (e) { oops(e); }
}

async function renderTranscribeSection(d) {
  const pm = await loadProjectMethods();
  const etOpts = el('dTranscriptOpts');
  const ssOpts = el('dShortsOpts');
  if (pm) {
    buildOptFields(etOpts, pm.entire_transcribe.options);
    buildOptFields(ssOpts, pm.suggested_shorts.options);
  }

  const hasAudio = !!d.audio_exists;
  el('dTranscribeAll').disabled = !hasAudio;
  el('dTranscriptNote').innerHTML = d.entire_transcribe_exists
    ? `Já existe: <code>entire_transcribe.json</code>`
      + (d.entire_transcribe_turns != null ? ` — ${d.entire_transcribe_turns} turnos.` : '.')
      + ' Um corte novo pode reaproveitar isto (a caixa aparece na etapa 2). Gerar de novo substitui.'
    : (hasAudio
      ? 'Roda o Whisper no wav do projeto inteiro. Um corte novo pode reaproveitar '
        + 'o resultado — recortando pelo tempo — em vez de transcrever de novo.'
      : 'Extraia o áudio do projeto primeiro.');

  const hasTranscript = !!d.entire_transcribe_exists;
  const missing = (pm && pm.suggested_shorts.missing_env) || [];
  el('dSuggestShorts').disabled = !hasTranscript || !!missing.length;
  el('dShortsNote').innerHTML = !hasTranscript
    ? 'Gere a transcrição do episódio inteiro primeiro.'
    : missing.length
      ? `Falta <code>${escapeHtml(missing.join(', '))}</code>.`
      : (d.suggested_shorts_exists
        ? `Já existe: <code>suggested_shorts.json</code>`
          + (d.suggested_shorts_clips != null ? ` — ${d.suggested_shorts_clips} sugestões.` : '.')
          + ' Gerar de novo substitui.'
        : 'Pede pro Gemini escolher trechos autocontidos, dentro da faixa de duração.');

  if (d.suggested_shorts_exists) await renderShortsList(SELECTED.slug);
  else el('dShortsList').innerHTML = '';
}

// ------------------------------------------------------------- origem

async function loadSources() {
  const d = await api('/api/sources');
  const sel = el('srcSelect');
  sel.innerHTML = `<option value="">— vídeos em ${escapeHtml(d.dir)} —</option>`
    + d.videos.map((v) =>
      `<option value="${escapeHtml(v.path)}">${escapeHtml(v.name)} · ${humanBytes(v.size)}</option>`).join('');
}

async function useSource(path) {
  if (!path) { NEW_SRC = null; el('nSpecs').classList.add('hidden'); return; }
  try {
    const info = await api(`/api/probe?path=${encodeURIComponent(path)}`);
    NEW_SRC = { path, info };
    el('nSpecs').innerHTML = specsHtml(info);
    el('nSpecs').classList.remove('hidden');
    if (!el('nName').value.trim()) {
      el('nName').value = info.suggested_name;
      syncSlug();
    }
    /* 60 fps constante é o caso deste pipeline. Se vier outra coisa, avisa
       agora: todo cálculo de frame (inclusive o mínimo de 2 frames que o
       Resolve exige) sai do fps gravado no projeto. */
    const warn = el('nWarn');
    const msgs = [];
    if (!info.fps) msgs.push('não consegui ler o fps deste arquivo — vai valer o padrão do config.');
    if (info.fps && Math.abs(info.fps - Math.round(info.fps)) > 0.001) {
      msgs.push(`fps fracionário (${info.fps.toFixed(3)}) — confira se a timeline do Resolve usa o mesmo.`);
    }
    warn.innerHTML = msgs.join(' ');
    warn.classList.toggle('hidden', !msgs.length);
    el('nCreate').disabled = false;
  } catch (e) { oops(e); }
}

function syncSlug() {
  const v = el('nName').value.trim();
  el('nSlug').value = v.normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\-. ]+/g, '').trim().replace(/\s+/g, '_')
    .replace(/^[._-]+|[._-]+$/g, '').slice(0, 80);
}

// -------------------------------------------------------------- ações

async function createProject() {
  if (!NEW_SRC) return toast('escolha o vídeo de origem primeiro', true);
  const name = el('nName').value.trim();
  if (!name) return toast('dê um nome ao projeto', true);
  const participants = readParts(el('nParts'));
  if (!participants.length) return toast('adicione pelo menos um participante', true);
  const btn = el('nCreate');
  btn.disabled = true;
  try {
    const r = await apiPost('/api/projects', {
      name, source_video: NEW_SRC.path, participants,
      off_camera: el('nOffcam').checked ? ['no_name'] : [],
    });
    toast(`projeto ${r.project.slug} criado — extraindo o áudio`);
    if (r.job) {
      await watchJob(r.job);
      toast('áudio pronto');
    }
    await refresh();
    await openDetail(r.project.slug);
    el('nName').value = '';
    el('nSlug').value = '';
    NEW_SRC = null;
    el('nSpecs').classList.add('hidden');
    el('srcSelect').value = '';
    fillParts(el('nParts'), null);
  } catch (e) {
    oops(e);
  } finally {
    btn.disabled = false;
  }
}

async function refresh() {
  const [state, list] = await Promise.all([
    api('/api/state'), api('/api/projects'),
  ]);
  STATE = state;
  PROJECTS = list.projects;
  renderProjects();
  return state;
}

// -------------------------------------------------------------- doctor

function ynTag(ok) {
  return `<span class="badge ${ok ? 'ok' : 'err'}">${ok ? 'ok' : 'falta'}</span>`;
}

async function doctor() {
  el('docOut').textContent = 'verificando…';
  try {
    const d = await api('/api/doctor');
    const pkg = d.packages || {};
    const rows = [
      ['ffmpeg', d.tools.ffmpeg], ['ffprobe', d.tools.ffprobe],
      ['scripts de diarização', d.scripts_dir_ok],
      ...Object.entries(pkg).filter(([k]) => !k.startsWith('_')),
      ...Object.entries(d.env),
    ];
    el('docOut').innerHTML = `
      <p class="sub" style="margin-bottom:10px">Python da diarização:
        <code>${escapeHtml(d.python_exe)}</code></p>
      <table class="plain"><tbody>${rows.map(([k, v]) =>
    `<tr><td class="mono">${escapeHtml(k)}</td><td>${ynTag(!!v)}</td></tr>`).join('')}
      </tbody></table>
      ${d.env.HF_TOKEN ? '' : `<p class="note" style="margin-top:12px">
        Sem <code>HF_TOKEN</code> os métodos pyannote não rodam. Crie
        <code>${escapeHtml(d.env_file)}</code> com a linha
        <code>HF_TOKEN=hf_xxx</code> e reinicie o servidor — o token sai de
        huggingface.co e precisa dos termos aceitos em
        <code>pyannote/speaker-diarization-3.1</code> e
        <code>pyannote/segmentation-3.0</code>.</p>`}`;
  } catch (e) { oops(e); el('docOut').textContent = 'falhou'; }
}

// --------------------------------------------------------------- boot

(async function boot() {
  try {
    const state = await refresh();
    renderNav(1, state);
    await loadSources();
    fillParts(el('nParts'), null);
  } catch (e) { oops(e); }

  el('srcSelect').onchange = (e) => useSource(e.target.value);
  el('srcPick').onclick = async () => {
    const b = el('srcPick');
    b.disabled = true; b.textContent = 'aguardando o diálogo…';
    try {
      const r = await apiPost('/api/sources/pick');
      if (r.path) await useSource(r.path);
    } catch (e) { oops(e); } finally {
      b.disabled = false; b.textContent = 'Escolher no disco…';
    }
  };
  el('nName').oninput = syncSlug;
  el('nAddPart').onclick = () => { partRow(el('nParts'), null); syncVoices('n'); };
  el('nCount').onchange = () => {
    setPartCount(el('nParts'), parseInt(el('nCount').value, 10));
    syncVoices('n');
  };
  el('nOffcam').onchange = () => syncVoices('n');
  syncVoices('n');
  el('nCreate').onclick = createProject;
  el('docBtn').onclick = doctor;

  el('dAddPart').onclick = () => { partRow(el('dParts'), null); syncVoices('d'); };
  el('dOffcam').onchange = () => syncVoices('d');
  el('dSave').onclick = async () => {
    try {
      await apiPatch(`/api/projects/${encodeURIComponent(SELECTED.slug)}`, {
        name: el('dTitle').value.trim(),
        participants: readParts(el('dParts')),
        off_camera: el('dOffcam').checked ? ['no_name'] : [],
        split_screen: el('dSplit').checked,
      });
      toast('projeto salvo');
      await refresh();
      await openDetail(SELECTED.slug);
    } catch (e) { oops(e); }
  };
  el('dAudio').onclick = async () => {
    try {
      const r = await apiPost(`/api/projects/${encodeURIComponent(SELECTED.slug)}/audio`);
      await watchJob(r.job);
      toast('áudio extraído');
      await refresh();
      await openDetail(SELECTED.slug);
    } catch (e) { oops(e); }
  };
  el('dGoCuts').onclick = () => {
    location.href = `/cortes?projeto=${encodeURIComponent(SELECTED.slug)}`;
  };
  el('dTranscribeAll').onclick = async () => {
    const btn = el('dTranscribeAll');
    btn.disabled = true;
    try {
      const opts = readOptFields(el('dTranscriptOpts'));
      const r = await apiPost(
        `/api/projects/${encodeURIComponent(SELECTED.slug)}/entire-transcript`,
        { options: opts },
      );
      const s = await watchJob(r.job, { keepOpen: true });
      const res = s.result || {};
      toast(`transcrição pronta: ${res.turns || 0} turnos`
        + (res.lua ? ' — Legendona.lua gerada em cortes\\Completo\\legendas'
                   : ` — Legendona.lua NÃO gerada: ${res.lua_erro || '?'}`), !res.lua);
      await openDetail(SELECTED.slug);
    } catch (e) { oops(e); } finally { btn.disabled = false; }
  };
  el('dSuggestShorts').onclick = async () => {
    const btn = el('dSuggestShorts');
    btn.disabled = true;
    try {
      const { gemini_model, ...rest } = readOptFields(el('dShortsOpts'));
      const r = await apiPost(
        `/api/projects/${encodeURIComponent(SELECTED.slug)}/suggested-shorts`,
        { options: { gemini_model }, min_duration: rest.min_duration, max_duration: rest.max_duration },
      );
      const s = await watchJob(r.job, { keepOpen: true });
      toast(`${(s.result || {}).clips || 0} sugestões geradas`);
      await openDetail(SELECTED.slug);
    } catch (e) { oops(e); } finally { btn.disabled = false; }
  };
  el('dDelete').onclick = async () => {
    if (!confirm(`Mover "${SELECTED.name}" para projects\\_lixeira?\n\n`
      + 'Nada é apagado — a pasta continua no disco, com data no nome.')) return;
    try {
      const r = await apiDelete(`/api/projects/${encodeURIComponent(SELECTED.slug)}`);
      toast(`movido para ${r.moved_to}`);
      SELECTED = null;
      el('detail').classList.add('hidden');
      await refresh();
    } catch (e) { oops(e); }
  };
}());
