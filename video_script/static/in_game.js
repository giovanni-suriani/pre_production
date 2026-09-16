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
 *  - o gabarito do rank nasce fechado: o que e premio nao se abre sem alguem
 *    pedir. O sorteio do impostor nao tem tampa nenhuma: o resultado vai
 *    direto pro card de cada pessoa na mesa, que e onde se le uma de cada vez.
 */

let P = null;
let CFG = { tempo_padrao: 120, tempo_passo: 30 };
let cron = null;                 // { timer, fim } do cronometro
const ROTEIRO = qs('roteiro');

/* Quantas linhas EM BRANCO o editor de duplas mostra alem das ja cadastradas,
   por jogo. Quem enche isso e o "Sortear nº de impostores": sorteou 2, a mesa
   precisa de 2 palavras de impostor, entao nascem 2 linhas prontas para
   digitar. Linha em branco nao vai pro disco (o editor filtra), entao isto e
   estado de TELA e morre no F5 — o que ja foi digitado, nao. */
const linhasVazias = {};

/* A cor de cada participante — a ordem na mesa decide qual. E a paleta do
   pre_production (8740, `src/app.py`) com uma troca: o laranja do segundo
   virou o prata da casa, a pedido do usuario. */
const CORES = ['#5b9cf8', '#c9ced6', '#4ecb8f', '#e879b9', '#7dd3fc',
               '#c4b5fd', '#fca5a5', '#86efac', '#fcd34d'];

const corDe = (id) => {
  const i = (P.participantes || []).findIndex((x) => x.id === id);
  return i < 0 ? 'var(--smoke)' : CORES[i % CORES.length];
};

/* Quantas moedas cada um tem NESTE jogo. O placar nao e guardado: e a conta
   de quantas vezes a pessoa aparece em `moedas`, entao ele nunca diverge do
   que esta desenhado nas linhas. */
function pontosDe(jid) {
  const moedas = (estado(jid).moedas) || {};
  const conta = {};
  for (const quem of Object.values(moedas)) {
    for (const id of quem || []) conta[id] = (conta[id] || 0) + 1;
  }
  return conta;
}

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
  document.querySelector('nav.nav')?.remove();
  renderNav(3, null, ROTEIRO);
  desenharMesa();
  desenharChips();
  desenharJogo();
}

// -------------------------------------------------------------------- a mesa

/* O que uma pessoa recebeu no sorteio. Impostor le a coluna da linha DELE
   (`palavras`); sorteio antigo, gravado antes das palavras por pessoa, ainda
   so tem a chave `impostor` — dai o segundo termo. */
function palavraDe(sort, id, ehImpostor) {
  if (!ehImpostor) return sort.principal || '—';
  const p = (sort.palavras || {})[id];
  return (p === undefined ? sort.impostor : p) || '(nada)';
}

const usaVidas = (j) => !!(j && j.in_game === 'rank');

function desenharMesa() {
  const box = el('gMesa');
  box.innerHTML = '';
  const j = jogoAtual();
  const sort = j ? (estado(j.id).sorteio || null) : null;
  const mostrar = !!(sort && (sort.impostores || []).length);
  const comVidas = usaVidas(j);

  const pontos = j && j.in_game === 'errada' ? pontosDe(j.id) : {};

  for (const x of P.participantes || []) {
    const vidas = comVidas ? vidasDe(x) : [];
    const vivo = !comVidas || vidas.some(Boolean);
    const ehImpostor = mostrar && (sort.impostores || []).includes(x.id);
    const c = h('div', 'jogador' + (vivo ? '' : ' fora')
      + (ehImpostor ? ' impostor' : ''));
    c.innerHTML = `
      <div class="row">
        <span class="nome">${esc(x.nome)}</span>
        ${ehImpostor ? '<span class="badge err">impostor</span>' : ''}
      </div>
      ${comVidas ? '<div class="vidas"></div>' : ''}
      ${mostrar ? `<div class="palavra">
        <span class="badge">${esc(palavraDe(sort, x.id, ehImpostor))}</span>
      </div>` : ''}
      ${pontos[x.id] ? `<div class="pontos" style="--cor: ${corDe(x.id)}">
        <span class="moeda ganha"></span>${pontos[x.id]}
      </div>` : ''}`;

    const vb = c.querySelector('.vidas');
    if (vb) {
      vidas.forEach((v, i) => {
        const b = h('button', 'vida ' + (v ? 'viva' : 'morta'));
        b.title = v ? `vida ${i + 1} — clique para gastar`
          : `vida ${i + 1} gasta — clique para devolver`;
        b.onclick = () => agir('vida', { jogo: j.id, participante: x.id, indice: i });
        vb.appendChild(b);
      });
    }
    box.appendChild(c);
  }
}

// ------------------------------------------------------------------- jogos

function desenharChips() {
  const box = el('gChips');
  box.innerHTML = '';
  (P.jogos || []).forEach((j, i) => {
    const c = h('button',
      `chip t-${j.tipo}` + (i === P.jogo_idx ? ' on' : ''),
      `${i + 1}. ${esc(j.nome)}`);
    c.onclick = () => agir('jogo', { idx: i });
    box.appendChild(c);
  });
  if (!(P.jogos || []).length) {
    box.appendChild(h('span', 'note', 'este roteiro não tem jogos ainda.'));
  }
}

/* Quem esta na frente nas moedas — ou "Empate", enquanto houver mais de um. */
function desenharVencedor(j) {
  const pontos = pontosDe(j.id);
  const maior = Math.max(0, ...Object.values(pontos));
  if (!maior) return;
  const lideres = (P.participantes || []).filter((x) => pontos[x.id] === maior);

  const faixa = h('div', 'row vencedor');
  if (lideres.length > 1) {
    faixa.appendChild(h('span', 'quem empate', 'Empate'));
  } else {
    faixa.appendChild(h('span', 'lbl', 'Vencedor'));
    const n = h('span', 'quem', `${esc(lideres[0].nome)} ${maior}`);
    n.style.setProperty('--cor', corDe(lideres[0].id));
    faixa.appendChild(n);
  }
  el('gRodada').appendChild(faixa);
}

function desenharJogo() {
  pararCron();
  el('gRodada').innerHTML = '';
  const box = el('gItem');
  box.innerHTML = '';
  const j = jogoAtual();
  if (!j) return;

  if (j.in_game === 'rank') box.appendChild(painelRank(j));
  else if (j.in_game === 'impostor') box.appendChild(painelImpostor(j));
  else if (j.in_game === 'discussao') box.appendChild(painelDiscussao(j));
  else if (j.in_game === 'errada') {
    box.appendChild(painelErrada(j));
    desenharVencedor(j);
  }
}

// ------------------------------------------------- editar o jogo aqui mesmo

/* Grava os atributos no jogo do roteiro e recarrega a partida.
   Os `attrs` vivem no roteiro, mas a partida os carrega junto — entao depois
   de salvar e preciso reler a partida, ou a tela continuaria desenhando a
   lista velha. */
async function salvarAttrs(j, attrs) {
  await salvarAttrsQuieto(j, attrs);
  desenhar();
}

let salvandoAttrs = Promise.resolve();

function salvarAttrsQuieto(j, attrs) {
  // em fila: duas gravacoes da mesma caixa saindo juntas fariam a segunda
  // escrever por cima do que a primeira ainda nem tinha lido de volta
  salvandoAttrs = salvandoAttrs.catch(() => {}).then(async () => {
    j.attrs = { ...(j.attrs || {}), ...attrs };
    await apiPut(`/api/roteiros/${ROTEIRO}/jogos/${j.id}`, { attrs: j.attrs });
    P = await api(`/api/partidas/${ROTEIRO}`);
  });
  return salvandoAttrs;
}

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
        <input type="text" class="aExtra" placeholder="valor" style="flex:1;min-width:120px">
        <button class="btn primary aAdd">Acrescentar</button>
      </div>
    </div>

    <div class="field">
      <span class="lbl">A lista inteira</span>
      <textarea class="tudo" rows="5"></textarea>
      <div class="row">
        <input type="file" class="arq" accept=".txt,.csv,.md,text/plain" hidden>
        <button class="btn impArq">Importar .txt</button>
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
  const wrap = h('div', 'ladoalado');
  wrap.innerHTML = `
    <div class="field">
      <span class="lbl">Tema da discussão</span>
      <textarea class="tema" rows="3" placeholder="Tema"></textarea>
    </div>
    <div class="field">
      <span class="lbl">Tempo (minutos)</span>
      <input type="number" class="min" min="1" max="60" style="width:90px"
             value="${Number(a.tempo_min || 10)}">
    </div>`;

  const q = (sel) => wrap.querySelector(sel);
  q('.tema').value = a.tema || '';

  /* O que esta na caixa E o tema, e a caixa e tambem o que fica na tela pra
     ler: nao ha botao de gravar nem copia em destaque. O disco espera meio
     segundo de pausa e usa o `salvarAttrsQuieto`, que nao redesenha — senao o
     cursor pularia no meio da frase. */
  let pendente = null;
  q('.tema').oninput = () => {
    const texto = q('.tema').value;
    clearTimeout(pendente);
    pendente = setTimeout(() => {
      salvarAttrsQuieto(j, { tema: texto.trim() }).catch(oops);
    }, 500);
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
  const wrap = h('div', 'field');
  wrap.appendChild(h('span', 'lbl', 'Perguntas e respostas certas'));

  let pendente = null;
  const gravar = (perguntas) => {
    clearTimeout(pendente);
    pendente = setTimeout(() => {
      salvarAttrsQuieto(j, { perguntas }).catch(oops);
    }, 500);
  };

  wrap.appendChild(perguntasEditor((j.attrs || {}).perguntas || [], gravar));
  return wrap;
}

// --- impostor: as duplas e quantos impostores

/* As duas colunas mais o numero de impostores, no mesmo card do Sortear: o
   que estiver nas caixas E o que o sorteio usa, sem botao de gravar no meio.

   A gravacao espera meio segundo de pausa na digitacao, em vez de sair a cada
   tecla, e passa pelo `salvarAttrsQuieto` — redesenhar a tela a cada letra
   levaria o foco e o cursor junto. */
function editorDuplas(j) {
  const a = j.attrs || {};
  const wrap = h('div', 'pilha');

  let pendente = null;
  const gravar = (duplas) => {
    clearTimeout(pendente);
    pendente = setTimeout(() => {
      salvarAttrsQuieto(j, { duplas }).catch(oops);
    }, 500);
  };

  const vazias = Array.from({ length: linhasVazias[j.id] || 0 },
    () => ({ jogador: '', impostor: '' }));

  const campoDuplas = h('div', 'field');
  campoDuplas.appendChild(h('span', 'lbl', 'Palavras da rodada'));
  campoDuplas.appendChild(duplasEditor((a.duplas || []).concat(vazias), gravar));

  const lado = h('div', 'ladoalado');
  lado.appendChild(campoDuplas);
  wrap.appendChild(lado);

  const nImp = h('div', 'field');
  nImp.innerHTML = `
    <span class="lbl">Nº de impostores</span>
    <input type="number" class="nImp" min="0" max="12" style="width:90px"
           value="${a.n_impostores === undefined ? 1 : Number(a.n_impostores)}">`;
  nImp.querySelector('.nImp').onchange = async (e) => {
    try { await salvarAttrs(j, { n_impostores: parseInt(e.target.value || '1', 10) || 0 }); }
    catch (err) { oops(err); }
  };
  lado.appendChild(nImp);
  return wrap;
}

// ----------------------------------------------------------- painel do rank

function painelRank(j) {
  const est = estado(j.id);
  const rev = est.revelados || {};
  const lista = (j.attrs || {}).lista || [];
  const card = h('section', 'card');

  card.innerHTML = `
    <header><h2>Adivinhar</h2></header>

    <div class="cols2">
      <div class="field">
        <span class="lbl">Buscar por nome</span>
        <input type="text" class="bNome" placeholder="Nome">
      </div>
      <div class="field">
        <span class="lbl">Buscar por posição</span>
        <input type="number" min="1" class="bRank" placeholder="Posição">
      </div>
    </div>

    <div class="field">
      <span class="lbl">De quem foi o chute</span>
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
    f.appendChild(h('span', 'lbl', 'Chutes fora da lista'));
    f.appendChild(h('p', 'note', est.erros.map((e) =>
      esc(e.termo) + (e.quem ? ` (${esc(e.quem)})` : '')).join(' · ')));
    card.appendChild(f);
  }

  // o cadastro da lista mora no proprio painel, como as palavras do impostor
  // e o tema da discussao — nao ha mais card "Conteudo do jogo" para o rank
  card.appendChild(editorLista(j));
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
    </header>
    <div class="sorteio"></div>
    <div class="row">
      <button class="btn sortearN">Sortear nº de impostores</button>
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
    el('gRodada').appendChild(campoRodada);
    campoRodada.querySelector('.maisRodada').onclick = () =>
      agir('rodada', { jogo: j.id });
  }

  const q = (s2) => card.querySelector(s2);
  const box = q('.sorteio');

  q('.sortearN').onclick = async () => {
    const n = Math.floor(Math.random() * ((P.participantes || []).length + 1));
    // uma linha em branco por impostor sorteado: cada um precisa da palavra
    // dele, e abrir as linhas aqui poupa o clique em "Acrescentar" n vezes
    linhasVazias[j.id] = n;
    try {
      await salvarAttrs(j, { n_impostores: n });
      toast(n === 1 ? '1 impostor' : `${n} impostores`);
    } catch (e) { oops(e); }
  };

  q('.sortear').onclick = () => agir('sortear', { jogo: j.id });

  card.insertBefore(editorDuplas(j), box);

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
    </div>`;

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
    <header><h2>Só resposta errada</h2></header>
    <div class="row">
      <button class="btn primary shuffle">Embaralhar</button>
      <span class="spacer"></span>
      ${sairam ? '<button class="btn voltar">Trazer todas de volta</button>' : ''}
    </div>
    <div class="perguntas"></div>`;

  const box = card.querySelector('.perguntas');
  ordem.forEach((i, pos) => {
    const x = lista[i];
    const comMoeda = (((est.moedas) || {})[String(i)] || []).length > 0;
    // moeda dada equivale a pergunta marcada — ver `embaralhar_errada`
    const feita = certas.has(i) || comMoeda;
    const ln = h('div', 'pq' + (feita ? ' feita' : '') + (comMoeda ? ' porMoeda' : ''));
    /* A bolinha e a cor dizem a MESMA coisa de proposito: com a camera ligada
       quem apresenta olha de raspao, e um sinal so (a cor, ou so a marca) se
       perde. Por isso a linha inteira fica verde e a bolinha ganha o ×. */
    const quem = new Set((((est.moedas) || {})[String(i)]) || []);
    ln.innerHTML = `
      <span class="n">${pos + 1}</span>
      <span class="certa">${esc(x.resposta || '—')}</span>
      <span class="pq-t">${esc(x.pergunta)}</span>
      <span class="moedas">${(P.participantes || []).map((pa) => `
        <button class="moeda${quem.has(pa.id) ? ' ganha' : ''}"
                style="--cor: ${corDe(pa.id)}"
                title="${esc(pa.nome)}"
                aria-pressed="${quem.has(pa.id)}">●</button>`).join('')}</span>
      <button class="lixo" title="jogar na lixeira${x.origem
        ? ` (veio de ${esc(x.origem)})` : ''}">🗑</button>`;

    ln.querySelectorAll('.moeda').forEach((b, k) => {
      const pa = (P.participantes || [])[k];
      b.onclick = () => agir('errada-moeda',
        { jogo: j.id, i, participante: pa.id });
    });
    ln.onclick = (ev) => {
      if (ev.target.closest('button') || comMoeda) return;
      agir('errada-marcar', { jogo: j.id, i });
    };
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
  });

  const marcadas = ordem.filter((i) => certas.has(i)
    || (((est.moedas) || {})[String(i)] || []).length).length;
  if (ordem.length) {
    const conta = h('div', 'row marcadas');
    conta.appendChild(h('span', 'lbl', 'Marcadas'));
    conta.appendChild(h('span', 'quanto', `${marcadas} / ${ordem.length}`));
    card.appendChild(conta);
  }

  // o cadastro mora no proprio painel, como nos outros quatro tipos
  card.appendChild(editorPerguntas(j));

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
  const card = h('section', 'card');
  card.innerHTML = '<header><h2>Discussão</h2></header>';

  card.appendChild(editorTema(j));
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
