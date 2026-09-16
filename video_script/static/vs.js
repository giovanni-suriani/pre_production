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
  } else if (c.kind === 'duplas' || c.kind === 'perguntas') {
    // duas colunas pareadas, e nao um textarea de linhas soltas: o que importa
    // nas duas e o PAR (quem ouve o que, que resposta e de que pergunta), e
    // uma lista de linhas soltas nao diz isso.
    wrap.appendChild((c.kind === 'duplas' ? duplasEditor : perguntasEditor)(
      valor, (v) => onChange(c.nome, v)));
    if (c.dica) wrap.appendChild(h('p', 'note', esc(c.dica)));
    return wrap;
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
    return input.value;
  };
  input.addEventListener('change', () => onChange(c.nome, ler()));
  return wrap;
}


/* ------------------------------------------- editor de duas colunas

   Uma linha = um par. As duplas do impostor sao `jogador | impostor`; as
   perguntas do "So resposta errada" sao `pergunta | resposta certa`. E a mesma
   tela, entao e a mesma funcao: `paresEditor` recebe como as duas colunas se
   chamam e o que dizer em volta.

   A coluna A e obrigatoria (linha sem ela nao e linha); a B pode ficar vazia,
   e no impostor isso quer dizer "o impostor nao recebe nada".

   Chama `onChange` com a lista inteira a cada mexida; quem usa decide se isso
   vai pro rascunho (aba Jogos) ou direto pro disco (in-game). */
function paresEditor(valor, onChange, cfg) {
  const A = cfg.a;                  // { chave, rotulo, nota, dica }
  const B = cfg.b;
  // o resto do objeto anda junto sem aparecer na tela: e por ali que o
  // `origem` (de qual .txt a linha veio) sobrevive a uma edicao
  let linhas = (valor || []).map((d) => (typeof d === 'string'
    ? { [A.chave]: d, [B.chave]: '' }
    : { ...d, [A.chave]: (d || {})[A.chave] || '',
        [B.chave]: (d || {})[B.chave] || '' }));

  const wrap = h('div', 'duplas' + (cfg.classe ? ` ${cfg.classe}` : ''));
  wrap.innerHTML = `
    ${cfg.cabecalho === false ? '' : `<div class="cab">
      <span>${esc(A.rotulo)} <i>— ${esc(A.nota)}</i></span>
      <span>${esc(B.rotulo)} <i>— ${esc(B.nota)}</i></span>
      <span></span>
    </div>`}
    <div class="linhas"></div>
    <div class="row">
      ${cfg.acrescentar === false ? ''
        : `<button type="button" class="btn add">+ ${esc(cfg.acrescentar)}</button>`}
      ${cfg.arquivo ? '<button type="button" class="btn imp">Importar .txt</button>'
        + `<input type="file" class="arq" accept="${esc(cfg.arquivo)}" hidden>` : ''}
      <span class="spacer"></span>
      ${cfg.contador === false ? '' : '<span class="note quantas"></span>'}
    </div>
    ${cfg.colar === false ? '' : `<details class="colar">
      <summary>…ou colar várias de uma vez</summary>
      <textarea rows="5" class="tudo"
        placeholder="uma por linha:&#10;${esc(cfg.exemplo)}"></textarea>
      <div class="row end">
        <button type="button" class="btn aplicar">${esc(cfg.substituir)}</button>
      </div>
    </details>`}`;

  const q = (sel) => wrap.querySelector(sel);
  const validas = () => linhas.filter((l) => (l[A.chave] || '').trim());
  const contar = () => {
    if (q('.quantas')) {
      q('.quantas').textContent = `${validas().length} ${cfg.plural}`;
    }
  };

  const avisar = () => {
    contar();
    onChange(linhas
      .map((l) => ({ ...l, [A.chave]: (l[A.chave] || '').trim(),
                     [B.chave]: (l[B.chave] || '').trim() }))
      .filter((l) => l[A.chave]));
  };

  const desenhar = () => {
    const box = q('.linhas');
    box.innerHTML = '';
    linhas.forEach((l, i) => {
      const ln = h('div', 'ln');
      ln.innerHTML = `
        <input type="text" class="a" placeholder="${esc(A.dica)}">
        <input type="text" class="b" placeholder="${esc(B.dica)}">
        <button type="button" class="x" title="tirar esta linha">×</button>`;
      const a = ln.querySelector('.a');
      const b = ln.querySelector('.b');
      a.value = l[A.chave];
      b.value = l[B.chave];
      a.oninput = () => { l[A.chave] = a.value; avisar(); };
      b.oninput = () => { l[B.chave] = b.value; avisar(); };
      ln.querySelector('.x').onclick = () => {
        linhas.splice(i, 1);
        desenhar();
        avisar();
      };
      box.appendChild(ln);
    });
    if (!linhas.length) box.appendChild(h('p', 'note', cfg.vazio));
    if (q('.tudo')) {
      q('.tudo').value = linhas
        .map((l) => `${l[A.chave]}${l[B.chave] ? ` | ${l[B.chave]}` : ''}`)
        .join('\n');
    }
    contar();
  };

  if (q('.add')) {
    q('.add').onclick = () => {
      linhas.push({ [A.chave]: '', [B.chave]: '' });
      desenhar();
      const todas = wrap.querySelectorAll('.ln .a');
      if (todas.length) todas[todas.length - 1].focus();
    };
  }

  const aplicarTexto = (texto, deOndeVeio) => {
    linhas = texto.split('\n').map((linha) => {
      const t = linha.trim();
      if (!t || t.startsWith('#')) return null;
      // TAB, "|" ou ";" separam as colunas — os tres aparecem em texto colado
      const m = t.split(/\t|\s*[|;]\s*/);
      const nova = { [A.chave]: (m[0] || '').trim(), [B.chave]: (m[1] || '').trim() };
      // de qual arquivo a linha veio, pra lixeira saber onde ela mora
      if (deOndeVeio) nova.origem = deOndeVeio;
      return nova;
    }).filter((l) => l && l[A.chave]);
    desenhar();
    avisar();
    toast(`${linhas.length} ${cfg.plural}`);
  };

  if (q('.aplicar')) q('.aplicar').onclick = () => aplicarTexto(q('.tudo').value);

  if (cfg.arquivo) {
    q('.imp').onclick = () => q('.arq').click();
    q('.arq').onchange = () => {
      const f = q('.arq').files[0];
      q('.arq').value = '';
      if (!f) return;
      const fr = new FileReader();
      // o arquivo e lido pelo NAVEGADOR e vira texto na caixa: o servico nao
      // precisa de upload, e da pra conferir o que entrou antes de aplicar
      fr.onload = () => {
        q('.colar').open = true;
        q('.tudo').value = fr.result;
        aplicarTexto(fr.result, f.name);
      };
      fr.onerror = () => toast(`não consegui ler ${f.name}`, true);
      fr.readAsText(f, 'utf-8');
    };
  }

  desenhar();
  return wrap;
}

/* ------------------------------------------------- as duplas do impostor

   Uma linha = uma rodada: a coluna "jogador" e o que a mesa inteira ouve, a
   coluna "impostor" e o que quem foi sorteado impostor ouve no lugar. O
   sorteio so escolhe a linha e as pessoas — o par ja vem decidido aqui. */
function duplasEditor(valor, onChange) {
  return paresEditor(valor, onChange, {
    a: { chave: 'jogador', rotulo: 'Jogador', nota: 'todo mundo ouve',
         dica: 'Mesa' },
    b: { chave: 'impostor', rotulo: 'Impostor', nota: 'vazio: não recebe nada',
         dica: 'Impostor' },
    cabecalho: false,
    contador: false,
    classe: 'impostor',
    acrescentar: 'Acrescentar palavra',
    colar: false,
    substituir: 'Substituir as palavras',
    plural: 'palavras',
    exemplo: 'arara | bacon\nmonalisa | guernica',
    vazio: 'nenhuma palavra ainda — o sorteio precisa de pelo menos uma.',
  });
}

/* ------------------------------------ as perguntas do "So resposta errada"

   A resposta certa nao e gabarito escondido: e a cola de quem apresenta, que
   precisa dela na mao pra saber o que NAO pode ser aceito. */
function perguntasEditor(valor, onChange) {
  return paresEditor(valor, onChange, {
    a: { chave: 'pergunta', rotulo: 'Pergunta', nota: 'o que se pergunta',
         dica: 'Pergunta' },
    b: { chave: 'resposta', rotulo: 'Resposta certa',
         nota: 'a que NÃO vale', dica: 'Resposta certa' },
    cabecalho: false,
    acrescentar: 'Acrescentar pergunta',
    substituir: 'Substituir as perguntas',
    plural: 'perguntas',
    exemplo: 'Capital do Japão | Tóquio\nQuem pintou a Mona Lisa | Da Vinci',
    vazio: 'nenhuma pergunta ainda — importe o .txt ou escreva aqui.',
    arquivo: '.txt,.csv,.md,text/plain',
  });
}
