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
 *  - o gabarito do rank nasce fechado: quem apresenta olha pra esta tela ao
 *    vivo, e o que e premio nao se abre sem alguem pedir. O sorteio do
 *    impostor e a excecao — sortear ja mostra o resultado (dar o clique e
 *    pedir), e a tampa serve pra esconder DEPOIS.
 */

let P = null;
let CFG = { tempo_padrao: 120, tempo_passo: 30 };
let cron = null;                 // { timer, fim } do cronometro
const ROTEIRO = qs('roteiro');

/* Quais editores de conteudo estao abertos, por jogo. Fica fora do desenho
   porque TODA acao redesenha a tela inteira: sem isto, cadastrar uma palavra
   fecharia o editor na cara de quem esta cadastrando a segunda. */
const editorAberto = {};

/* Quais sorteios de impostor estao TAPADOS, por jogo. Nasce vazio: sortear ja
   mostra quem e, sem um segundo clique — na gravacao o passo a mais era so
   atrito. A tampa continua existindo pra esconder de novo (reflexo, alguem
   passando atras da tela), e por isso o estado fica aqui: toda acao redesenha,
   e sem isto a tela reabriria o sorteio que acabaram de tapar. */
const sorteioFechado = {};

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

/* O placar e por jogo: os coracoes que a mesa mostra sao os do jogo aberto.
   Sem jogo aberto nao ha placar nenhum — e o caso do roteiro sem jogos. */
/* O relogio deste jogo: o ajuste gravado ganha do cadastro, que ganha do
   padrao da casa. So a Discussao cadastra `tempo_min` — no impostor o tempo e
   decisao de quem esta com a mesa na frente. */
const segundosDe = (j) => estado(j.id).tempo
  || ((j.attrs || {}).tempo_min ? (j.attrs || {}).tempo_min * 60 : CFG.tempo_padrao);

const vidasDe = (x) => {
  const j = jogoAtual();
  return (j && (estado(j.id).vidas || {})[x.id]) || [];
};

function desenhar() {
  el('semRoteiro').classList.add('hidden');
  el('jogo').classList.remove('hidden');
  el('gNome').textContent = P.roteiro_nome;
  const j0 = jogoAtual();
  const vivos = (P.participantes || []).filter((x) => vidasDe(x).some(Boolean));
  el('gSub').innerHTML = (j0
    ? `${vivos.length}/${(P.participantes || []).length} ainda com vida `
      + `em <b>${esc(j0.nome)}</b>`
    : `${(P.participantes || []).length} na mesa`)
    + (P.notas_roteiro ? ` · ${esc(P.notas_roteiro)}` : '');
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
  const mostrar = !!(sort && (sort.impostores || []).length);

  for (const x of P.participantes || []) {
    const vidas = vidasDe(x);
    const vivo = vidas.some(Boolean);
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
    vidas.forEach((v, i) => {
      const b = h('button', 'vida ' + (v ? 'viva' : 'morta'));
      b.title = v ? `vida ${i + 1} — clique para gastar`
        : `vida ${i + 1} gasta — clique para devolver`;
      b.onclick = () => agir('vida', { jogo: j.id, participante: x.id, indice: i });
      vb.appendChild(b);
    });
    if (!vidas.length) {
      vb.appendChild(h('span', 'note',
        j ? 'este jogo está com 0 vidas' : 'sem jogo aberto'));
    }
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

  /* Jogo sem conteudo NAO manda mais ninguem pra outra aba: o editor abre
     sozinho aqui embaixo. Descobrir que faltou cadastrar a palavra e coisa que
     acontece com a camera ligada, e a resposta certa e digitar ali mesmo, nao
     navegar pra outra tela e voltar. */
  if (j.pendencia && editorAberto[j.id] === undefined) editorAberto[j.id] = true;

  if (j.in_game === 'rank') box.appendChild(painelRank(j));
  else if (j.in_game === 'impostor') box.appendChild(painelImpostor(j));
  else if (j.in_game === 'discussao') box.appendChild(painelDiscussao(j));
  else if (j.in_game === 'errada') box.appendChild(painelErrada(j));
  box.appendChild(editorConteudo(j));
}

// ------------------------------------------------- editar o jogo aqui mesmo

/* Grava os atributos no jogo do roteiro e recarrega a partida.
   Os `attrs` vivem no roteiro, mas a partida os carrega junto — entao depois
   de salvar e preciso reler a partida, ou a tela continuaria desenhando a
   lista velha. */
async function salvarAttrs(j, attrs) {
  await apiPut(`/api/roteiros/${ROTEIRO}/jogos/${j.id}`,
    { attrs: { ...(j.attrs || {}), ...attrs } });
  P = await api(`/api/partidas/${ROTEIRO}`);
  desenhar();
}

function editorConteudo(j) {
  const card = h('section', 'card');
  const aberto = !!editorAberto[j.id];
  const quantos = j.in_game === 'rank'
    ? `${((j.attrs || {}).lista || []).length} posições`
    : j.in_game === 'discussao'
      ? `${mmss(segundosDe(j))} de relógio`
      : j.in_game === 'errada'
        ? `${((j.attrs || {}).perguntas || []).length} perguntas`
        : `${((j.attrs || {}).duplas || []).length} duplas`;

  const cab = h('header');
  cab.innerHTML = `
    <h2>Conteúdo do jogo</h2>
    <p class="sub">${esc(quantos)}${j.pendencia
      ? ' · <b>cadastre antes de jogar</b>' : ''}</p>`;
  card.appendChild(cab);

  const alterna = h('button', 'btn', aberto ? 'Fechar o editor' : 'Editar aqui');
  alterna.onclick = () => {
    editorAberto[j.id] = !aberto;
    desenharJogo();
  };
  const linha = h('div', 'row');
  linha.appendChild(alterna);
  linha.appendChild(h('span', 'note',
    'muda o jogo no roteiro — sem sair desta tela'));
  card.appendChild(linha);

  if (!aberto) return card;
  if (j.in_game === 'rank') card.appendChild(editorLista(j));
  else if (j.in_game === 'impostor') card.appendChild(editorDuplas(j));
  else if (j.in_game === 'discussao') card.appendChild(editorTema(j));
  else if (j.in_game === 'errada') card.appendChild(editorPerguntas(j));
  return card;
}

// --- adivinha rank: a lista, abaixo do gabarito

function editorLista(j) {
  const lista = (j.attrs || {}).lista || [];
  const wrap = h('div', 'pilha');
  wrap.innerHTML = `
    <div class="field">
      <span class="lbl">Acrescentar uma posição</span>
      <div class="row">
        <input type="number" class="aPos" min="1" placeholder="#"
               style="width:80px" value="${lista.length + 1}">
        <input type="text" class="aNome" placeholder="nome" style="flex:2;min-width:160px">
        <input type="text" class="aExtra" placeholder="valor (opcional)" style="flex:1;min-width:120px">
        <button class="btn primary aAdd">Acrescentar</button>
      </div>
      <p class="note">entra fechada no gabarito, como as outras</p>
    </div>

    <div class="field">
      <span class="lbl">A lista inteira</span>
      <textarea class="tudo" rows="8"></textarea>
      <p class="note">uma por linha: <code>1. Nome — valor</code>. Aplicar
        <b>substitui</b> a lista. As posições já reveladas continuam reveladas
        pelo número — se você mudar a ordem, confira o gabarito, ou use
        "Zerar este jogo" acima.</p>
      <div class="row">
        <input type="file" class="arq" accept=".txt,.csv,.md,text/plain" hidden>
        <button class="btn impArq">Importar lista_do_rank.txt</button>
        <span class="spacer"></span>
        <button class="btn primary aplicar">Aplicar a lista</button>
      </div>
    </div>`;

  const q = (s) => wrap.querySelector(s);
  const texto = lista.map((i) =>
    `${i.pos}. ${i.nome}${i.extra ? ` — ${i.extra}` : ''}`).join('\n');
  q('.tudo').value = texto;

  q('.aAdd').onclick = async () => {
    const nome = q('.aNome').value.trim();
    if (!nome) { toast('digite o nome', true); return; }
    const pos = parseInt(q('.aPos').value || '0', 10) || (lista.length + 1);
    if (lista.some((i) => Number(i.pos) === pos)) {
      toast(`a posição ${pos} já existe na lista`, true);
      return;
    }
    const novo = [...lista, { pos, nome, extra: q('.aExtra').value.trim() }]
      .sort((a, b) => a.pos - b.pos);
    try { await salvarAttrs(j, { lista: novo }); toast(`#${pos} ${nome} entrou`); }
    catch (e) { oops(e); }
  };

  q('.aplicar').onclick = async () => aplicarTexto(q('.tudo').value, 'a lista');
  q('.impArq').onclick = () => q('.arq').click();
  q('.arq').onchange = () => {
    const f = q('.arq').files[0];
    if (!f) return;
    const fr = new FileReader();
    fr.onload = () => { q('.tudo').value = fr.result; aplicarTexto(fr.result, f.name); };
    fr.readAsText(f, 'utf-8');
  };

  async function aplicarTexto(txt, de) {
    try {
      const r = await apiPost('/api/parse-lista-rank', { texto: txt });
      if (!r.n) { toast('não achei nenhuma linha útil nesse texto', true); return; }
      await salvarAttrs(j, { lista: r.itens });
      toast(`${r.n} posições lidas de ${de}`);
    } catch (e) { oops(e); }
  }
  return wrap;
}

// --- discussao: o tema e quantos minutos

/* Como as duplas, o tema so vai pro disco no botao: e texto sendo digitado, e
   gravar no meio da frase encheria o disco de rascunho. Os minutos, que sao um
   clique so, gravam sozinhos — e zeram o ajuste do relogio, ou mudar o
   cadastro para 15min deixaria a tela marcando os 10 de antes. */
function editorTema(j) {
  const a = j.attrs || {};
  const wrap = h('div', 'pilha');
  wrap.innerHTML = `
    <div class="field">
      <span class="lbl">Tema da discussão</span>
      <textarea class="tema" rows="3"
        placeholder="o que a mesa vai discutir"></textarea>
      <div class="row">
        <button class="btn primary gravar">Gravar o tema</button>
        <span class="note">o tema só vai pro disco no clique</span>
      </div>
    </div>
    <div class="field">
      <span class="lbl">Tempo (minutos)</span>
      <div class="row">
        <input type="number" class="min" min="1" max="60" style="width:90px"
               value="${Number(a.tempo_min || 10)}">
        <span class="note">volta o relógio para este tanto</span>
      </div>
    </div>`;

  const q = (sel) => wrap.querySelector(sel);
  q('.tema').value = a.tema || '';
  q('.gravar').onclick = async () => {
    try { await salvarAttrs(j, { tema: q('.tema').value.trim() }); toast('tema gravado'); }
    catch (e) { oops(e); }
  };
  q('.min').onchange = async (e) => {
    const m = Math.max(1, Math.min(parseInt(e.target.value || '10', 10) || 10, 60));
    try {
      await salvarAttrs(j, { tempo_min: m });
      // o ajuste antigo apontava pro cadastro velho; sai junto
      await agir('tempo', { jogo: j.id, segundos: m * 60 });
    } catch (err) { oops(err); }
  };
  return wrap;
}

// --- so resposta errada: as perguntas

function editorPerguntas(j) {
  const wrap = h('div', 'pilha');
  let rascunho = ((j.attrs || {}).perguntas || []).map((x) => ({ ...x }));
  const campo = h('div', 'field');
  campo.appendChild(h('span', 'lbl', 'Perguntas e respostas certas'));
  campo.appendChild(perguntasEditor(rascunho, (v) => { rascunho = v; }));
  wrap.appendChild(campo);

  const linha = h('div', 'row');
  const gravar = h('button', 'btn primary', 'Gravar as perguntas');
  gravar.onclick = async () => {
    try {
      await salvarAttrs(j, { perguntas: rascunho });
      toast(`${rascunho.length} perguntas`);
    } catch (e) { oops(e); }
  };
  linha.appendChild(gravar);
  linha.appendChild(h('span', 'note',
    'como as duplas, só vão pro disco no clique'));
  wrap.appendChild(linha);
  return wrap;
}

// --- impostor: as duplas e quantos impostores

/* As duas colunas mais o numero de impostores — o cadastro inteiro do jogo,
   aqui mesmo. Ao contrario do resto da tela, as duplas NAO gravam a cada
   tecla: sao caixas de texto que a pessoa esta digitando, e gravar no meio da
   palavra encheria o disco de rascunho. O botao grava; o numero de impostores,
   que e um clique so, grava sozinho. */
function editorDuplas(j) {
  const a = j.attrs || {};
  const wrap = h('div', 'pilha');
  let rascunho = (a.duplas || []).map((d) => ({ ...d }));

  const campoDuplas = h('div', 'field');
  campoDuplas.appendChild(h('span', 'lbl', 'Duplas da rodada'));
  campoDuplas.appendChild(duplasEditor(rascunho, (v) => { rascunho = v; }));
  wrap.appendChild(campoDuplas);

  const linha = h('div', 'row');
  const gravar = h('button', 'btn primary', 'Gravar as duplas');
  gravar.onclick = async () => {
    try { await salvarAttrs(j, { duplas: rascunho }); toast(`${rascunho.length} duplas`); }
    catch (e) { oops(e); }
  };
  linha.appendChild(gravar);
  linha.appendChild(h('span', 'note', 'as duplas só vão pro disco no clique'));
  wrap.appendChild(linha);

  const nImp = h('div', 'field');
  nImp.innerHTML = `
    <span class="lbl">Nº de impostores</span>
    <div class="row">
      <input type="number" class="nImp" min="0" max="12" style="width:90px"
             value="${Number(a.n_impostores || 1)}">
      <span class="note">vale no próximo sorteio</span>
    </div>`;
  nImp.querySelector('.nImp').onchange = async (e) => {
    try { await salvarAttrs(j, { n_impostores: parseInt(e.target.value || '1', 10) || 0 }); }
    catch (err) { oops(err); }
  };
  wrap.appendChild(nImp);
  return wrap;
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
  if (!lista.length) {
    grade.appendChild(h('p', 'note',
      'sem gabarito ainda — cadastre a lista no editor logo abaixo.'));
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
  const card = h('section', 'card');

  card.innerHTML = `
    <header>
      <h2>${ehQuadro ? 'Quadro' : 'Palavra'} da rodada</h2>
      <p class="sub">${a.n_impostores || 1} impostor(es)</p>
    </header>
    <div class="sorteio"></div>
    <div class="row">
      <button class="btn primary sortear">${s ? 'Sortear de novo' : 'Sortear'}</button>
    </div>`;

  /* O contador manual de rodada, so na palavra: quem apresenta bate o proprio
     numero, sem relacao nenhuma com o sorteio por baixo dos panos. */
  if (!ehQuadro) {
    const campoRodada = h('div', 'row');
    campoRodada.innerHTML = `
      <span class="lbl">Rodada</span>
      <span class="cron">${Number(est.rodada || 0)}</span>
      <button class="btn maisRodada">+1 rodada</button>`;
    card.appendChild(campoRodada);
    campoRodada.querySelector('.maisRodada').onclick = () =>
      agir('rodada', { jogo: j.id });
  }

  const q = (s2) => card.querySelector(s2);
  const box = q('.sorteio');

  if (!s) {
    box.appendChild(h('div', 'holofote vazio',
      'nada sorteado ainda neste jogo — clique em Sortear.'));
  } else {
    /* O sorteio nasce ABERTO: quem clicou em Sortear quer ler o resultado, e
       o clique a mais so atrapalhava com a camera ligada. A tampa continua
       ali pra tapar depois (reflexo, alguem passando atras da tela). Dentro,
       a lista e por pessoa — "joao (impostor) — bacon" — porque e assim que
       quem apresenta le, uma pessoa de cada vez, e nao cruzando duas colunas
       de cabeca. */
    const impostores = new Set(s.impostores || []);
    const tapado = !!sorteioFechado[j.id];
    const palco = h('div', 'palco' + (tapado ? ' fechado' : ''));
    const tampa = h('button', 'tampa', tapado
      ? 'o sorteio: clique para mostrar' : 'esconder o sorteio');
    tampa.onclick = () => {
      const fechado = palco.classList.toggle('fechado');
      sorteioFechado[j.id] = fechado;
      tampa.textContent = fechado
        ? 'o sorteio: clique para mostrar' : 'esconder o sorteio';
    };
    palco.appendChild(tampa);

    const dentro = h('div', 'aberto');
    dentro.appendChild(h('div', 'par', `
      <span><i>jogador</i> ${esc(s.principal || '—')}</span>
      <span><i>impostor</i> ${esc(s.impostor || '(nada)')}</span>`));
    const quemE = h('div', 'cadaum');
    for (const x of P.participantes || []) {
      const eh = impostores.has(x.id);
      quemE.appendChild(h('div', eh ? 'pessoa imp' : 'pessoa', `
        <span class="quem">${esc(x.nome)}${eh ? ' <b>(impostor)</b>' : ''}</span>
        <span class="oque">${esc(eh ? (s.impostor || '(nada)') : s.principal)}</span>`));
    }
    dentro.appendChild(quemE);
    palco.appendChild(dentro);
    box.appendChild(palco);

    const quem = (s.impostores || []).map((id) =>
      ((P.participantes || []).find((x) => x.id === id) || {}).nome || id);
    box.appendChild(h('p', 'note',
      `<b>impostor(es):</b> ${esc(quem.join(', ')) || '—'} `
      + `(marcado na mesa acima) — sorteado às `
      + `${esc((s.em || '').replace('T', ' '))}`));
  }

  /* Sortear abre o resultado junto: quem apresenta clica uma vez e ja le. */
  q('.sortear').onclick = () => {
    sorteioFechado[j.id] = false;
    return agir('sortear', { jogo: j.id });
  };

  card.appendChild(blocoCronometro(j, 'Discussão'));
  return card;
}

/* O cronometro, que a Discussao e o impostor dividem.

   O ajuste (±30s) e gravado no jogo porque a mesa decide "esse aqui merece 3
   minutos" e essa decisao tem que sobreviver ao F5. O relogio CORRENDO nao e
   gravado: e o relogio de quem apresenta, nao um dado do episodio, e gravar
   isso a cada segundo seria escrita em disco de graca. */
function blocoCronometro(j, rotulo) {
  const segundos = segundosDe(j);
  const inicial = (j.attrs || {}).tempo_min
    ? (j.attrs || {}).tempo_min * 60 : CFG.tempo_padrao;
  const campo = h('div', 'field');
  campo.innerHTML = `
    <span class="lbl">${esc(rotulo)}</span>
    <div class="row">
      <span class="cron">${mmss(segundos)}</span>
      <button class="btn menos">−30s</button>
      <button class="btn mais">+30s</button>
      <span class="spacer"></span>
      <button class="btn start">Iniciar</button>
      <button class="btn parar" disabled>Parar</button>
      <button class="btn zerarCron">Voltar ao início</button>
    </div>
    <p class="note">começa em ${mmss(inicial)}; o ajuste fica gravado neste
      jogo, o relógio correndo não.</p>`;

  const q = (sel) => campo.querySelector(sel);
  const passo = CFG.tempo_passo;
  q('.mais').onclick = () => agir('tempo', { jogo: j.id, segundos: segundos + passo });
  q('.menos').onclick = () => agir('tempo', { jogo: j.id, segundos: segundos - passo });
  q('.zerarCron').onclick = () => agir('tempo', { jogo: j.id, segundos: inicial });

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
  return campo;
}

// ------------------------------------------- painel do so resposta errada

/* Tres colunas: a bolinha de "ja saiu certa", a resposta certa e a pergunta.

   A resposta certa fica ABERTA, ao contrario do gabarito do rank e da palavra
   do impostor: aqui ela nao e o premio, e a cola de quem apresenta — a graca
   do jogo e responder errado de proposito, e quem conduz precisa saber na hora
   o que NAO pode passar.

   O `Embaralhar` sorteia as que faltam e empurra as marcadas pro fim: o que ja
   saiu nao reaparece no meio das que faltam, mas continua na tela. */
function painelErrada(j) {
  const est = estado(j.id);
  const lista = ((j.attrs || {}).perguntas || []).filter(
    (x) => (x && x.pergunta || '').trim());
  const certas = new Set((est.certas || []).map(Number));
  const fora = new Set((est.escondidas || []).map(Number));

  // a ordem gravada, filtrada pela lista de agora (editar a lista no meio da
  // partida pode ter mexido nos indices), sem as que ja sairam num embaralho,
  // e completada com o que entrou depois
  const vistos = new Set();
  const ordem = [];
  for (const i of est.ordem || []) {
    const k = Number(i);
    if (k >= 0 && k < lista.length && !vistos.has(k) && !fora.has(k)) {
      vistos.add(k);
      ordem.push(k);
    }
  }
  lista.forEach((_, i) => { if (!vistos.has(i) && !fora.has(i)) ordem.push(i); });

  const sairam = [...fora].filter((i) => i < lista.length).length;
  const card = h('section', 'card');
  card.innerHTML = `
    <header>
      <h2>Só resposta errada</h2>
      <p class="sub">${ordem.length} na tela${sairam
        ? ` · ${sairam} já saíram` : ''}</p>
    </header>
    <div class="row">
      <button class="btn primary shuffle">Embaralhar</button>
      <span class="note">as marcadas saem da tela; o resto volta em ordem nova</span>
      <span class="spacer"></span>
      ${sairam ? '<button class="btn voltar">Trazer todas de volta</button>' : ''}
    </div>
    <div class="perguntas"></div>`;

  const box = card.querySelector('.perguntas');
  if (!lista.length) {
    box.appendChild(h('div', 'holofote vazio',
      'nenhuma pergunta ainda — importe o .txt no "Conteúdo do jogo" abaixo.'));
  } else if (!ordem.length) {
    box.appendChild(h('div', 'holofote vazio',
      'todas já saíram — "Trazer todas de volta" recomeça o jogo.'));
  }
  for (const i of ordem) {
    const x = lista[i];
    const feita = certas.has(i);
    const ln = h('div', 'pq' + (feita ? ' feita' : ''));
    /* A bolinha e a cor dizem a MESMA coisa de proposito: com a camera ligada
       quem apresenta olha de raspao, e um sinal so (a cor, ou so a marca) se
       perde. Por isso a linha inteira fica verde e a bolinha ganha o ×. */
    ln.innerHTML = `
      <button class="marca" title="${feita ? 'ainda não saiu' : 'já saiu certa'}"
        aria-pressed="${feita}">${feita ? '×' : ''}</button>
      <span class="certa">${esc(x.resposta || '—')}</span>
      <span class="pq-t">${esc(x.pergunta)}</span>
      <button class="lixo" title="jogar na lixeira${x.origem
        ? ` (veio de ${esc(x.origem)})` : ''}">🗑</button>`;
    ln.querySelector('.marca').onclick = () => agir('errada-marcar', { jogo: j.id, i });
    /* O lixo e o unico botao da tela que tira coisa do CADASTRO no meio da
       gravacao — por isso pergunta antes, e por isso existe a lixeira: a
       pergunta sai do jogo mas fica anotada, com o .txt de onde veio. */
    ln.querySelector('.lixo').onclick = () => {
      if (!confirm(`Jogar na lixeira?\n\n"${x.pergunta}"\n\nSai deste jogo `
        + 'e fica anotada em dados\\lixeira_perguntas.json'
        + `${x.origem ? `, junto com o arquivo de origem (${x.origem})` : ''}.`)) return;
      agir('errada-lixo', { jogo: j.id, i });
    };
    box.appendChild(ln);
  }

  card.querySelector('.shuffle').onclick = () =>
    agir('errada-embaralhar', { jogo: j.id });
  const voltar = card.querySelector('.voltar');
  if (voltar) {
    voltar.onclick = () => {
      if (!confirm('Trazer todas as perguntas de volta?\n\nAs que já saíram '
        + 'voltam para a tela, desmarcadas. Nada foi apagado do cadastro.')) return;
      agir('zerar-jogo', { jogo: j.id });
    };
  }
  return card;
}

// ---------------------------------------------------- painel da discussao

/* O jogo mais simples da casa: o tema na tela e o relogio embaixo. Nao ha
   gabarito nem sorteio, entao nao ha nada a esconder — o tema aparece aberto,
   ao contrario da palavra do impostor. */
function painelDiscussao(j) {
  const tema = ((j.attrs || {}).tema || '').trim();
  const card = h('section', 'card');
  card.innerHTML = `
    <header>
      <h2>Discussão</h2>
      <p class="sub">o tema fica na tela enquanto o relógio corre</p>
    </header>`;
  card.appendChild(tema
    ? h('div', 'holofote', `<div class="grande">${esc(tema)}</div>`)
    : h('div', 'holofote vazio',
      'sem tema ainda — escreva no "Conteúdo do jogo", aqui embaixo.'));
  card.appendChild(blocoCronometro(j, 'Relógio'));
  return card;
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
