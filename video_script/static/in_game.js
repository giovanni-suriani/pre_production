/* video_script — aba 3, in_game.
 *
 * Uma partida por roteiro: `/in-game?roteiro=X` continua a que existe ou
 * comeca uma com os participantes do roteiro. Nao ha mais tela de montar a
 * mesa — quem joga foi decidido na aba Roteiro. Recomecar e o botao Reiniciar,
 * que e explicito.
 *
 * Esta e a unica tela que roda com a camera ligada, e isso decide o desenho
 * dela em dois pontos:
 *
 *  - toda acao manda pro servidor e REDESENHA com a resposta. A tela nunca
 *    mostra um estado que o disco nao tem — durante a gravacao, um placar
 *    otimista errado e pior do que um clique perdido.
 *  - o gabarito do rank e o sorteio do impostor ficam fechados por padrao.
 *    Quem apresenta olha pra esta tela ao vivo: nada se abre sem alguem pedir.
 */

let P = null;
let CFG = { tempo_padrao: 120, tempo_passo: 30 };
let cron = null;                 // { timer, fim } do cronometro
const ROTEIRO = qs('roteiro');

const el = (id) => document.getElementById(id);

async function inicio() {
  CFG = await api('/api/tipos');
  if (!ROTEIRO) return semRoteiro();
  el('gVoltar').href = `/roteiro?roteiro=${encodeURIComponent(ROTEIRO)}`;
  P = await apiPost(`/api/partidas/${ROTEIRO}/abrir`);
  lembrar('roteiro', ROTEIRO);
  desenhar();
}

async function semRoteiro() {
  renderNav(3);
  el('semRoteiro').classList.remove('hidden');
  const box = el('rLista');
  box.innerHTML = '';
  try {
    for (const r of (await api('/api/roteiros')).roteiros) {
      const it = h('div', 'item');
      it.innerHTML = `
        <div class="t">${esc(r.nome)}</div>
        <div class="d">${r.n_participantes} na mesa · ${r.n_jogos} jogos</div>
        <div class="side"><span class="badge">jogar</span></div>`;
      it.onclick = () => {
        location.href = `/in-game?roteiro=${encodeURIComponent(r.slug)}`;
      };
      box.appendChild(it);
    }
  } catch (e) { oops(e); }
}

/* Todo botao passa por aqui: manda, recebe a partida inteira, redesenha. */
async function agir(rota, corpo) {
  try {
    const r = await apiPost(`/api/partidas/${ROTEIRO}/${rota}`, corpo);
    P = r.partida || r;
    desenhar();
    return r;
  } catch (e) { oops(e); return null; }
}

const jogoAtual = () => (P.jogos || [])[P.jogo_idx] || null;
const estado = (jid) => ((P.estado || {})[jid]) || {};

function desenhar() {
  el('semRoteiro').classList.add('hidden');
  el('jogo').classList.remove('hidden');
  el('gNome').textContent = P.roteiro_nome;
  const vivos = (P.participantes || []).filter((x) => (x.vidas || []).some(Boolean));
  el('gSub').innerHTML = `${vivos.length}/${(P.participantes || []).length} `
    + 'ainda com vida' + (P.notas_roteiro ? ` · ${esc(P.notas_roteiro)}` : '');
  document.querySelector('nav.nav')?.remove();
  renderNav(3, `<b>${esc(P.roteiro_nome)}</b>`, ROTEIRO);
  desenharMesa();
  desenharChips();
  desenharJogo();
}

// -------------------------------------------------------------------- a mesa

function desenharMesa() {
  const box = el('gMesa');
  box.innerHTML = '';
  const j = jogoAtual();
  const sort = j ? (estado(j.id).sorteio || null) : null;
  const mostrar = sort && sort.revelado;

  for (const x of P.participantes || []) {
    const vivo = (x.vidas || []).some(Boolean);
    const ehImpostor = mostrar && (sort.impostores || []).includes(x.id);
    const c = h('div', 'jogador' + (vivo ? '' : ' fora')
      + (ehImpostor ? ' impostor' : ''));
    c.innerHTML = `
      <div class="row">
        <span class="nome">${esc(x.nome)}</span>
        ${ehImpostor ? '<span class="badge err">impostor</span>' : ''}
      </div>
      <div class="vidas"></div>`;

    const vb = c.querySelector('.vidas');
    (x.vidas || []).forEach((v, i) => {
      const b = h('button', 'vida ' + (v ? 'viva' : 'morta'));
      b.title = v ? `vida ${i + 1} — clique para gastar`
        : `vida ${i + 1} gasta — clique para devolver`;
      b.onclick = () => agir('vida', { participante: x.id, indice: i });
      vb.appendChild(b);
    });
    if (!(x.vidas || []).length) vb.appendChild(h('span', 'note', 'sem vidas'));
    box.appendChild(c);
  }
}

// ------------------------------------------------------------------- jogos

function desenharChips() {
  const box = el('gChips');
  box.innerHTML = '';
  (P.jogos || []).forEach((j, i) => {
    const c = h('button', 'chip' + (i === P.jogo_idx ? ' on' : ''),
      `${i + 1}. ${esc(j.nome)}`);
    c.onclick = () => agir('jogo', { idx: i });
    box.appendChild(c);
  });
  if (!(P.jogos || []).length) {
    box.appendChild(h('span', 'note', 'este roteiro não tem jogos ainda.'));
  }
}

function desenharJogo() {
  pararCron();
  const box = el('gItem');
  box.innerHTML = '';
  const j = jogoAtual();
  if (!j) return;

  const cab = h('section', 'card');
  cab.innerHTML = `
    <header>
      <h2>${esc(j.nome)}</h2>
      <p class="sub">
        <span class="badge">${esc(j.tipo_rotulo || '—')}</span>
        ${esc((j.attrs || {}).tema || '')}
        ${j.duracao_min ? ` · ${minutos(j.duracao_min)} previstos` : ''}
      </p>
    </header>`;
  if (j.notas) cab.appendChild(h('p', 'note', esc(j.notas)));
  box.appendChild(cab);

  if (j.pendencia) {
    const av = h('section', 'card');
    av.innerHTML = `<p class="note"><b>${esc(j.pendencia)}</b> — abra o jogo na
      <a href="/jogo?roteiro=${encodeURIComponent(ROTEIRO)}&jogo=${encodeURIComponent(j.id)}">aba Jogos</a>
      e cadastre o conteúdo.</p>`;
    box.appendChild(av);
    return;
  }
  if (j.in_game === 'rank') box.appendChild(painelRank(j));
  else if (j.in_game === 'impostor') box.appendChild(painelImpostor(j));
}

// ----------------------------------------------------------- painel do rank

function painelRank(j) {
  const est = estado(j.id);
  const rev = est.revelados || {};
  const lista = (j.attrs || {}).lista || [];
  const card = h('section', 'card');

  card.innerHTML = `
    <header>
      <h2>Adivinhar</h2>
      <p class="sub">${Object.keys(rev).length}/${lista.length} posições abertas</p>
    </header>

    <div class="cols2">
      <div class="field">
        <span class="lbl">Buscar por nome</span>
        <input type="text" class="bNome" placeholder="o que a mesa chutou — Enter para buscar">
        <p class="note">${(j.attrs || {}).aceita_parcial
          ? 'aceita nome parcial: "ronaldo" acha "Cristiano Ronaldo"'
          : 'exige o nome exato'}</p>
      </div>
      <div class="field">
        <span class="lbl">Buscar por rank (posição)</span>
        <input type="number" min="1" class="bRank" placeholder="ex.: 7 — Enter para abrir">
        <p class="note">abre direto aquela posição do gabarito</p>
      </div>
    </div>

    <div class="field">
      <span class="lbl">De quem foi o chute <span class="note">(opcional, entra no log)</span></span>
      <select class="quem">
        <option value="">— ninguém em especial —</option>
        ${(P.participantes || []).map((x) =>
          `<option value="${esc(x.nome)}">${esc(x.nome)}</option>`).join('')}
      </select>
    </div>

    <div class="holo"></div>

    <div class="field">
      <span class="lbl">Gabarito</span>
      <div class="rank"></div>
    </div>

    <div class="row end">
      <button class="btn danger zerar">Zerar este jogo</button>
    </div>`;

  const q = (s) => card.querySelector(s);

  const buscar = async (por, input) => {
    const termo = input.value.trim();
    if (!termo) return;
    const quem = q('.quem').value;
    const r = await agir('buscar', { jogo: j.id, por, termo, quem });
    if (!r) return;
    // O redesenho recriou o painel; o holofote é escrito no novo.
    mostrarHolofote(r.achados, termo, quem);
  };

  q('.bNome').onkeydown = (e) => { if (e.key === 'Enter') buscar('nome', q('.bNome')); };
  q('.bRank').onkeydown = (e) => { if (e.key === 'Enter') buscar('rank', q('.bRank')); };
  q('.zerar').onclick = () => {
    if (confirm('Zerar tudo que foi revelado neste jogo?')) {
      agir('zerar-jogo', { jogo: j.id });
    }
  };

  const grade = q('.rank');
  for (const i of lista) {
    const aberta = rev[String(i.pos)];
    const linha = h('div', 'linha ' + (aberta ? 'aberta' : 'fechada'));
    linha.innerHTML = `
      <span class="pos">${i.pos}</span>
      <span class="nome">${aberta ? esc(i.nome) : '— — —'}</span>
      ${aberta && aberta.quem ? `<span class="quem">${esc(aberta.quem)}</span>` : ''}
      <span class="extra">${aberta ? esc(i.extra || '') : ''}</span>`;
    if (aberta) {
      const x = h('button', 'x', '×');
      x.title = 'fechar de novo (revelei sem querer)';
      x.onclick = () => agir('esconder', { jogo: j.id, pos: i.pos });
      linha.appendChild(x);
    }
    grade.appendChild(linha);
  }

  if ((est.erros || []).length) {
    const f = h('div', 'field');
    f.appendChild(h('span', 'lbl',
      `Chutes que não estavam na lista (${est.erros.length})`));
    f.appendChild(h('p', 'note', est.erros.map((e) =>
      esc(e.termo) + (e.quem ? ` (${esc(e.quem)})` : '')).join(' · ')));
    card.appendChild(f);
  }
  return card;
}

function mostrarHolofote(achados, termo, quem) {
  const holo = document.querySelector('#gItem .holo');
  if (!holo) return;
  if (!achados.length) {
    holo.innerHTML = `<div class="holofote erro">
      <div class="grande">${esc(termo)} não está na lista</div>
      <div class="sub">registrado como chute perdido${quem ? ` de ${esc(quem)}` : ''}</div>
    </div>`;
    return;
  }
  holo.innerHTML = `<div class="holofote">
    ${achados.map((i) => `
      <div class="grande">#${i.pos} — ${esc(i.nome)}</div>
      ${i.extra ? `<div class="sub">${esc(i.extra)}</div>` : ''}`).join('')}
    <div class="sub">buscado como "${esc(termo)}"${quem ? ` · ${esc(quem)}` : ''}</div>
  </div>`;
}

// ------------------------------------------------------- painel do impostor

function painelImpostor(j) {
  const est = estado(j.id);
  const s = est.sorteio || null;
  const a = j.attrs || {};
  const ehQuadro = j.tipo === 'impostor_quadro';
  const segundos = est.tempo || CFG.tempo_padrao;
  const card = h('section', 'card');

  card.innerHTML = `
    <header>
      <h2>${ehQuadro ? 'Quadro' : 'Palavra'} da rodada</h2>
      <p class="sub">${a.n_impostores || 1} impostor(es)</p>
    </header>
    <div class="sorteio"></div>
    <div class="row">
      <button class="btn primary sortear">${s ? 'Sortear de novo' : 'Sortear'}</button>
      ${s ? `<button class="btn revelar">${s.revelado
        ? 'Esconder quem era' : 'Revelar quem era o impostor'}</button>` : ''}
    </div>

    <div class="field">
      <span class="lbl">Discussão</span>
      <div class="row">
        <span class="cron">${mmss(segundos)}</span>
        <button class="btn menos">−30s</button>
        <button class="btn mais">+30s</button>
        <span class="spacer"></span>
        <button class="btn start">Iniciar</button>
        <button class="btn parar" disabled>Parar</button>
        <button class="btn zerarCron">Voltar ao início</button>
      </div>
      <p class="note">começa em ${mmss(CFG.tempo_padrao)}; o ajuste fica gravado
        neste jogo, o relógio correndo não.</p>
    </div>`;

  const q = (s2) => card.querySelector(s2);
  const box = q('.sorteio');

  if (!s) {
    box.appendChild(h('div', 'holofote vazio',
      'nada sorteado ainda neste jogo — clique em Sortear.'));
  } else {
    // Os dois segredos ficam tapados e abrem no clique: esta tela fica virada
    // pra quem apresenta, e a palavra nao pode aparecer de graca no reflexo.
    const seg = (rot, valor) => {
      const d = h('div', 'segredo', `${rot}: clique para ver`);
      d.onclick = () => {
        d.classList.toggle('aberto');
        d.textContent = d.classList.contains('aberto')
          ? `${rot}: ${valor || '(nada)'}` : `${rot}: clique para ver`;
      };
      return d;
    };
    const g = h('div', 'pilha');
    g.appendChild(seg(ehQuadro ? 'quadro de todos' : 'palavra de todos', s.principal));
    g.appendChild(seg('o impostor recebe', s.impostor));
    box.appendChild(g);

    if (ehQuadro && s.principal) box.appendChild(caixaQuadro(s.principal));

    const quem = (s.impostores || []).map((id) =>
      ((P.participantes || []).find((x) => x.id === id) || {}).nome || id);
    box.appendChild(h('p', 'note', s.revelado
      ? `<b>impostor(es):</b> ${esc(quem.join(', ')) || '—'} (marcado na mesa acima)`
      : `sorteado às ${esc((s.em || '').replace('T', ' '))} — `
        + `${quem.length} impostor(es) escolhido(s), escondidos.`));
  }

  q('.sortear').onclick = () => agir('sortear', { jogo: j.id });
  if (s) {
    q('.revelar').onclick = () => agir('revelar-impostor',
      { jogo: j.id, revelado: !s.revelado });
  }

  // --- cronometro
  const passo = CFG.tempo_passo;
  q('.mais').onclick = () => agir('tempo', { jogo: j.id, segundos: segundos + passo });
  q('.menos').onclick = () => agir('tempo', { jogo: j.id, segundos: segundos - passo });
  q('.zerarCron').onclick = () => agir('tempo', { jogo: j.id, segundos: CFG.tempo_padrao });

  // O relogio correndo so vive na tela: se recarregar no meio da discussao o
  // tempo se perde. E o relogio de quem apresenta, nao um dado do episodio, e
  // gravar isso a cada segundo seria escrita em disco de graca.
  const mostrador = q('.cron');
  q('.start').onclick = () => {
    pararCron();
    const fim = Date.now() + segundos * 1000;
    q('.parar').disabled = false;
    cron = setInterval(() => {
      const resta = (fim - Date.now()) / 1000;
      mostrador.textContent = mmss(resta);
      mostrador.classList.toggle('acabou', resta <= 0);
      if (resta <= 0) { pararCron(); toast('tempo!'); }
    }, 250);
  };
  q('.parar').onclick = () => { pararCron(); q('.parar').disabled = true; };
  return card;
}

/* O quadro da rodada: nasce tapado como os outros segredos, e abre no clique.
   E a mesma regra da palavra — esta tela fica virada pra quem apresenta, e o
   quadro e justamente o que a mesa nao pode ver antes da hora. */
function caixaQuadro(src) {
  const wrap = h('div', 'palco fechado');
  const servido = src.startsWith('/quadros/') || /^https?:\/\//i.test(src);

  if (!servido) {
    // caminho de disco de um cadastro antigo: o navegador bloqueia file://
    // dentro de uma pagina http, entao nao adianta tentar
    return h('p', 'note',
      `este quadro ainda é um caminho de disco (<code>${esc(src)}</code>), que a `
      + 'página não consegue abrir. Abra o jogo na aba Jogos e suba a imagem — '
      + 'ela passa a ser servida pelo próprio serviço.');
  }

  const img = h('img', 'quadro');
  img.src = src;
  img.alt = 'quadro da rodada';
  img.onerror = () => {
    wrap.innerHTML = '';
    wrap.appendChild(h('p', 'note',
      `não consegui carregar <code>${esc(src)}</code> — se for um endereço da `
      + 'web, confira se ele ainda existe.'));
  };

  const tampa = h('button', 'tampa', 'quadro da rodada: clique para mostrar');
  tampa.onclick = () => {
    const aberto = wrap.classList.toggle('fechado');
    tampa.textContent = aberto
      ? 'quadro da rodada: clique para mostrar' : 'esconder o quadro';
  };
  wrap.appendChild(tampa);
  wrap.appendChild(img);
  return wrap;
}

function pararCron() {
  if (cron) { clearInterval(cron); cron = null; }
}

// ------------------------------------------------------------------- rodape

el('gReiniciar').onclick = async () => {
  if (!confirm('Reiniciar a partida?\n\nTodas as vidas voltam, o gabarito fecha'
    + ' e os sorteios somem. Os mesmos jogadores continuam na mesa.')) return;
  try {
    pararCron();
    P = await apiPost(`/api/partidas/${ROTEIRO}/reiniciar`);
    desenhar();
    toast('partida reiniciada');
  } catch (e) { oops(e); }
};

(async () => {
  renderNav(3, null, ROTEIRO);
  try { await inicio(); } catch (e) {
    oops(e);
    await semRoteiro();
  }
})();
