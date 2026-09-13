/* video_script — o que as tres abas compartilham.
 *
 * Sem framework e sem build, pela mesma razao do pre_production: isto roda em
 * 127.0.0.1 numa maquina so, e um passo de build seria uma peca a mais pra
 * quebrar entre voce e o arquivo que voce quer editar.
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

const apiPost = (p, b) => api(p, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(b || {}),
});
const apiPut = (p, b) => api(p, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(b || {}),
});
const apiDelete = (p) => api(p, { method: 'DELETE' });

// ----------------------------------------------------------------- basico

function esc(s) {
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

const qs = (k) => new URLSearchParams(location.search).get(k);

function minutos(n) {
  n = Math.round(n || 0);
  if (!n) return '—';
  return n < 60 ? `${n}min` : `${Math.floor(n / 60)}h ${n % 60}min`;
}

function mmss(s) {
  s = Math.max(0, Math.round(s || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/* Guarda o que estava aberto por aba, para o F5 no meio da gravacao nao
   devolver a tela em branco. So o ponteiro (qual slug) — o estado de verdade
   vive no servidor. */
const lembrar = (k, v) => { try { localStorage.setItem(`vs.${k}`, v); } catch (e) {} };
const lembrado = (k) => { try { return localStorage.getItem(`vs.${k}`); } catch (e) { return null; } };

// ------------------------------------------------------------------ aviso

let toastTimer = null;
function toast(msg, bad) {
  let el = document.getElementById('toast');
  if (!el) {
    el = h('div', 'toast hidden');
    el.id = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), bad ? 7000 : 3200);
}
const oops = (e) => toast(e && e.message ? e.message : String(e), true);

// ------------------------------------------------------------------- nav

/* A barra segue a ordem do trabalho: o roteiro primeiro, porque e ele que
   guarda quem joga e quais jogos existem. Jogos e In-game so fazem sentido
   COM um roteiro, entao ficam apagados enquanto nao houver um escolhido. */
function renderNav(aba, ctx, roteiro, jogoHref) {
  const el = h('nav', 'nav');
  const on = (n) => (aba === n ? 'on' : '');
  const q = roteiro ? `?roteiro=${encodeURIComponent(roteiro)}` : '';
  // "Jogos" so acende com um jogo escolhido — a aba edita UM jogo, e nao ha o
  // que mostrar antes de clicar num deles no roteiro.
  el.innerHTML = `
    <div class="brand">video_<span>script</span></div>
    <div class="steps">
      <a class="step ${on(1)}" href="/roteiro${q}"><span class="n">1</span>Roteiro</a>
      <span class="sep">›</span>
      <a class="step ${on(2)} ${jogoHref ? '' : 'off'}"
         href="${jogoHref || '#'}"><span class="n">2</span>Jogos</a>
      <span class="sep">›</span>
      <a class="step ${on(3)} ${roteiro ? '' : 'off'}"
         href="${roteiro ? `/in-game${q}` : '#'}"><span class="n">3</span>In-game</a>
    </div>
    <div class="ctx">${ctx || '<span>pre_production · 8740</span>'}</div>`;
  document.body.prepend(el);
  return el;
}

// -------------------------------------------------------------- formulario

/* Monta um campo a partir do descritor que vem de /api/tipos. A tela nao
   conhece os campos de cada jogo: quem sabe e o jogos.TIPOS do servidor, e um
   campo novo la aparece aqui sozinho. */
function campo(c, valor, onChange) {
  const wrap = h('div', 'field');
  wrap.appendChild(h('span', 'lbl', esc(c.rotulo)));

  let input;
  if (c.kind === 'area') {
    input = h('textarea');
    input.rows = 3;
    input.value = valor || '';
  } else if (c.kind === 'num') {
    input = h('input');
    input.type = 'number';
    input.min = '0';
    input.value = valor === undefined || valor === null ? '' : valor;
  } else if (c.kind === 'bool') {
    const lab = h('label', 'chk');
    input = h('input');
    input.type = 'checkbox';
    input.checked = !!valor;
    lab.appendChild(input);
    lab.appendChild(h('span', '', esc(c.dica || c.rotulo)));
    wrap.appendChild(lab);
  } else if (c.kind === 'escolha') {
    input = h('select');
    for (const o of c.opcoes || []) {
      const op = h('option', '', esc(o.r));
      op.value = o.v;
      input.appendChild(op);
    }
    input.value = valor || (c.opcoes && c.opcoes[0] && c.opcoes[0].v) || '';
  } else if (c.kind === 'imagens' || c.kind === 'palavras') {
    // lista simples: uma por linha. O textarea ganha do editor de linhas
    // porque colar 40 palavras de uma vez e o caso normal.
    input = h('textarea');
    input.rows = 5;
    input.value = (valor || []).join('\n');
  } else {
    input = h('input');
    input.type = 'text';
    input.value = valor || '';
    if (c.dica) input.placeholder = c.dica;
  }

  if (c.kind !== 'bool') wrap.appendChild(input);
  if (c.dica && c.kind !== 'bool' && c.kind !== 'texto') {
    wrap.appendChild(h('p', 'note', esc(c.dica)));
  }

  const ler = () => {
    if (c.kind === 'num') return parseInt(input.value || '0', 10) || 0;
    if (c.kind === 'bool') return input.checked;
    if (c.kind === 'imagens' || c.kind === 'palavras') {
      return input.value.split('\n').map((s) => s.trim()).filter(Boolean);
    }
    return input.value;
  };
  input.addEventListener('change', () => onChange(c.nome, ler()));
  return wrap;
}
