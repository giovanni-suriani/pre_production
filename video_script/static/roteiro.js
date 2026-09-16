/* video_script — aba 1, o roteiro. E a tela inicial.
 *
 * O roteiro e o dono de tudo: os participantes e os jogos moram nele. Esta
 * tela edita as duas coisas e leva pras outras duas abas — clicar num jogo
 * abre a aba Jogos naquele jogo, "Jogar roteiro" abre a partida.
 *
 * Participantes e a ORDEM/metadado dos jogos sao mandados inteiros no Salvar.
 * Os `attrs` de cada jogo NAO vao junto: quem edita atributo e a aba Jogos.
 * Assim, salvar aqui com um jogo aberto noutra aba nao apaga o trabalho de la.
 */

let ROTEIROS = [];
let TIPOS = [];
let atual = null;

const el = (id) => document.getElementById(id);

async function carregar() {
  const [r, t] = await Promise.all([api('/api/roteiros'), api('/api/tipos')]);
  ROTEIROS = r.roteiros;
  TIPOS = t.tipos;
  desenharLista();
}

function desenharLista() {
  const box = el('lista');
  box.innerHTML = '';
  el('vazio').classList.toggle('hidden', ROTEIROS.length > 0);
  for (const r of ROTEIROS) {
    const it = h('div', 'item' + (atual && atual.slug === r.slug ? ' on' : ''));
    it.innerHTML = `
      <div class="t">${esc(r.nome)}</div>`;
    it.onclick = () => abrir(r.slug);
    box.appendChild(it);
  }
}

async function abrir(slug) {
  atual = await api(`/api/roteiros/${slug}`);
  lembrar('roteiro', slug);
  history.replaceState(null, '', `/roteiro?roteiro=${encodeURIComponent(slug)}`);
  document.querySelector('nav.nav').remove();
  renderNav(1, null, slug);
  desenharLista();
  desenharDetalhe();
}

function desenharDetalhe() {
  el('det').classList.remove('hidden');
  el('dNome').textContent = atual.nome;
  el('dNomeIn').value = atual.nome;
  desenharParts();
  desenharJogos();
  desenharTipos();
}

// --------------------------------------------------------- participantes

function desenharParts() {
  const parts = atual.participantes || [];
  const box = el('dParts');
  box.innerHTML = '';

  parts.forEach((x, i) => {
    const linha = h('div', 'part');
    linha.innerHTML = `
      <input type="text" class="nm" placeholder="nome" value="${esc(x.nome)}">
      <button class="btn small danger del">×</button>`;
    const q = (s) => linha.querySelector(s);
    q('.nm').oninput = () => { x.nome = q('.nm').value; };
    q('.del').onclick = () => { parts.splice(i, 1); desenharParts(); };
    box.appendChild(linha);
  });
}

el('dAddPart').onclick = () => {
  // so o nome: com quantas vidas cada um entra e decisao de cada JOGO
  (atual.participantes = atual.participantes || []).push({ nome: '' });
  desenharParts();
};

// ------------------------------------------------------------------ jogos

function desenharJogos() {
  const js = atual.jogos || [];
  const box = el('dJogos');
  box.innerHTML = '';
  el('dJogosVazio').classList.toggle('hidden', js.length > 0);

  js.forEach((j, idx) => {
    const p = h('div', `jogo t-${j.tipo}`);
    p.innerHTML = `
      <div class="n">${idx + 1}</div>
      <div class="corpo">
        <div class="abrir"><span>${esc(j.nome)}</span></div>
        <div class="acoes">
          <button class="btn small up" title="mover para cima"
                  aria-label="mover para cima" ${idx === 0 ? 'disabled' : ''}>↑</button>
          <button class="btn small down" title="mover para baixo"
                  aria-label="mover para baixo" ${idx === js.length - 1 ? 'disabled' : ''}>↓</button>
        </div>
      </div>
      <button class="btn small danger del">×</button>`;

    // O card inteiro abre o editor, e nao so o nome. Os botoes vivem dentro
    // dele, entao o clique neles subiria ate aqui e navegaria no meio de um
    // "mover" ou de um "remover" — por isso o closest('button') sai fora.
    p.onclick = (ev) => {
      if (ev.target.closest('button')) return;
      location.href = `/jogo?roteiro=${encodeURIComponent(atual.slug)}`
        + `&jogo=${encodeURIComponent(j.id)}`;
    };

    const q = (s) => p.querySelector(s);
    q('.up').onclick = () => mover(idx, -1);
    q('.down').onclick = () => mover(idx, +1);
    q('.del').onclick = async () => {
      if (!confirm(`Tirar "${j.nome}" do roteiro?\n\nO jogo mora dentro deste`
        + ' roteiro, então isto apaga os atributos dele também.')) return;
      try {
        // Salva antes: apagar recarrega do disco, e o que estivesse digitado
        // nos outros jogos se perderia.
        await salvar({ silencioso: true });
        atual = await apiDelete(`/api/roteiros/${atual.slug}/jogos/${j.id}`);
        desenharDetalhe();
        await carregar();
        toast('jogo removido');
      } catch (e) { oops(e); }
    };
    box.appendChild(p);
  });
}

function mover(idx, d) {
  const a = atual.jogos;
  const j = idx + d;
  if (j < 0 || j >= a.length) return;
  [a[idx], a[j]] = [a[j], a[idx]];
  desenharJogos();
}

function desenharTipos() {
  const box = el('dTipos');
  box.innerHTML = '';
  for (const t of TIPOS) {
    const c = h('button', `chip t-${t.tipo}`, `+ ${esc(t.rotulo)}`);
    c.title = t.sub;
    c.onclick = async () => {
      try {
        await salvar({ silencioso: true });
        atual = await apiPost(`/api/roteiros/${atual.slug}/jogos`, { tipo: t.tipo });
        desenharDetalhe();
        await carregar();
        toast(`"${t.rotulo}" entrou como jogo ${atual.jogos.length}`);
      } catch (e) { oops(e); }
    };
    box.appendChild(c);
  }
}

// ----------------------------------------------------------------- acoes

el('nCriar').onclick = async () => {
  try {
    const r = await apiPost('/api/roteiros', { nome: el('nName').value });
    el('nName').value = '';
    await carregar();
    await abrir(r.slug);
  } catch (e) { oops(e); }
};

async function salvar(opts) {
  opts = opts || {};
  atual.nome = el('dNomeIn').value;
  const limpos = (atual.participantes || []).filter((x) => (x.nome || '').trim());
  atual = await apiPut(`/api/roteiros/${atual.slug}`, {
    nome: atual.nome,
    participantes: limpos,
    jogos: (atual.jogos || []).map((j) => ({
      id: j.id, nome: j.nome,
    })),
  });
  if (!opts.silencioso) {
    desenharDetalhe();
    await carregar();
  }
  return atual;
}

el('dSalvar').onclick = async () => {
  try { await salvar(); toast('salvo'); } catch (e) { oops(e); }
};

/* Salva antes de jogar: entrar na partida com um participante digitado e nao
   gravado faria a mesa aparecer sem ele. */
el('dJogar').onclick = async () => {
  try {
    await salvar({ silencioso: true });
    if (!(atual.participantes || []).length) {
      toast('defina quem joga antes de jogar o roteiro', true);
      await carregar(); desenharDetalhe();
      return;
    }
    location.href = `/in-game?roteiro=${encodeURIComponent(atual.slug)}`;
  } catch (e) { oops(e); }
};

el('dApagar').onclick = async () => {
  if (!confirm(`Apagar o roteiro "${atual.nome}"?\n\nOs jogos dele e a partida`
    + ' em andamento vão junto — eles moram dentro do roteiro.')) return;
  try {
    await apiDelete(`/api/roteiros/${atual.slug}`);
    atual = null;
    el('det').classList.add('hidden');
    await carregar();
    toast('apagado');
  } catch (e) { oops(e); }
};

(async () => {
  renderNav(1);
  try {
    await carregar();
    const alvo = qs('roteiro') || lembrado('roteiro');
    if (alvo && ROTEIROS.some((r) => r.slug === alvo)) await abrir(alvo);
  } catch (e) { oops(e); }
})();
