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
  el('cont').textContent = ROTEIROS.length ? `${ROTEIROS.length} no total` : '';
  el('vazio').classList.toggle('hidden', ROTEIROS.length > 0);
  for (const r of ROTEIROS) {
    const it = h('div', 'item' + (atual && atual.slug === r.slug ? ' on' : ''));
    it.innerHTML = `
      <div class="t">${esc(r.nome)}</div>
      <div class="d">${r.n_participantes} na mesa · ${r.n_jogos}
        ${r.n_jogos === 1 ? 'jogo' : 'jogos'}
        ${r.duracao_prevista ? ` · ${minutos(r.duracao_prevista)}` : ''}</div>
      ${r.pendencias.length
        ? `<div class="side"><span class="badge warn">${r.pendencias.length} pendente(s)</span></div>`
        : ''}`;
    it.onclick = () => abrir(r.slug);
    box.appendChild(it);
  }
}

async function abrir(slug) {
  atual = await api(`/api/roteiros/${slug}`);
  lembrar('roteiro', slug);
  history.replaceState(null, '', `/roteiro?roteiro=${encodeURIComponent(slug)}`);
  document.querySelector('nav.nav').remove();
  renderNav(1, `<b>${esc(atual.nome)}</b>`, slug);
  desenharLista();
  desenharDetalhe();
}

function desenharDetalhe() {
  el('det').classList.remove('hidden');
  el('dNome').textContent = atual.nome;
  el('dNomeIn').value = atual.nome;
  el('dNotas').value = atual.notas || '';
  el('dResumo').textContent =
    `${atual.n_participantes} na mesa · ${atual.n_jogos} `
    + `${atual.n_jogos === 1 ? 'jogo' : 'jogos'}`
    + (atual.duracao_prevista ? ` · ${minutos(atual.duracao_prevista)} previstos` : '');
  desenharParts();
  desenharJogos();
  desenharTipos();
}

// --------------------------------------------------------- participantes

function desenharParts() {
  const parts = atual.participantes || [];
  const box = el('dParts');
  box.innerHTML = '';
  el('dPartVazio').classList.toggle('hidden', parts.length > 0);
  el('dPartSub').textContent = parts.length
    ? `${parts.length} na mesa` : '';

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
  el('dJogosSub').textContent = atual.pendencias.length
    ? `${atual.pendencias.length} sem conteúdo cadastrado` : '';

  js.forEach((j, idx) => {
    const p = h('div', 'jogo' + (j.pendencia ? ' pendente' : ''));
    p.innerHTML = `
      <div class="n">${idx + 1}</div>
      <div class="corpo">
        <a class="abrir" href="/jogo?roteiro=${encodeURIComponent(atual.slug)}&jogo=${encodeURIComponent(j.id)}">
          <span>${esc(j.nome)}</span>
          <span class="resumo">${esc(j.resumo || '')}</span>
          <span class="seta">editar →</span>
        </a>
        <div class="row">
          <span class="badge">${esc(j.tipo_rotulo)}</span>
          ${j.pendencia ? `<span class="badge warn">${esc(j.pendencia)}</span>` : ''}
          <span class="spacer"></span>
          <span class="note">duração</span>
          <input type="number" class="dur" min="0" style="width:78px"
                 value="${j.duracao_min || 0}"> <span class="note">min</span>
        </div>
        <textarea class="obs" rows="2" placeholder="notas de fala deste jogo">${esc(j.notas || '')}</textarea>
      </div>
      <div class="acoes">
        <button class="btn small up"   ${idx === 0 ? 'disabled' : ''}>↑</button>
        <button class="btn small down" ${idx === js.length - 1 ? 'disabled' : ''}>↓</button>
        <button class="btn small danger del">×</button>
      </div>`;

    const q = (s) => p.querySelector(s);
    q('.dur').onchange = () => {
      j.duracao_min = parseInt(q('.dur').value || '0', 10) || 0;
    };
    q('.obs').onchange = () => { j.notas = q('.obs').value; };
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
    const c = h('button', 'chip', `+ ${esc(t.rotulo)}`);
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
  atual.notas = el('dNotas').value;
  const limpos = (atual.participantes || []).filter((x) => (x.nome || '').trim());
  atual = await apiPut(`/api/roteiros/${atual.slug}`, {
    nome: atual.nome, notas: atual.notas,
    participantes: limpos,
    jogos: (atual.jogos || []).map((j) => ({
      id: j.id, nome: j.nome, duracao_min: j.duracao_min, notas: j.notas,
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
