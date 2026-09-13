/* video_script — aba 2, o jogo.
 *
 * Edita UM jogo de UM roteiro (`/jogo?roteiro=X&jogo=Y`) — e onde o clique no
 * jogo, la no roteiro, cai. Nao existe lista de jogos: eles moram dentro do
 * roteiro que os usa, entao a lista deles e a propria aba Roteiro.
 *
 * O formulario nao conhece nenhum jogo: e montado a partir do descritor que
 * vem de /api/tipos (jogos.TIPOS no servidor). Campo novo la aparece aqui sem
 * tocar neste arquivo — e o que impede a tela e o servidor de discordarem
 * sobre o que um jogo tem.
 */

let TIPOS = [];
let jogo = null;
let rascunho = {};
const ROTEIRO = qs('roteiro');
const JOGO = qs('jogo');

const el = (id) => document.getElementById(id);

async function carregar() {
  TIPOS = (await api('/api/tipos')).tipos;
  if (!ROTEIRO || !JOGO) {
    el('semJogo').classList.remove('hidden');
    el('topo').textContent = 'Cada jogo pertence a um roteiro.';
    renderNav(2);
    return;
  }
  jogo = await api(`/api/roteiros/${ROTEIRO}/jogos/${JOGO}`);
  rascunho = { ...(jogo.attrs || {}) };
  const volta = `/roteiro?roteiro=${encodeURIComponent(ROTEIRO)}`;
  el('dVoltar').href = volta;
  el('topo').innerHTML = `jogo do roteiro <a href="${volta}">${esc(jogo.roteiro_nome)}</a>`;
  renderNav(2, `<b>${esc(jogo.roteiro_nome)}</b> · ${esc(jogo.nome)}`,
    ROTEIRO, location.pathname + location.search);
  desenhar();
}

function desenhar() {
  const tp = TIPOS.find((x) => x.tipo === jogo.tipo);
  el('det').classList.remove('hidden');
  el('dNome').textContent = jogo.nome;
  el('dTipo').textContent = tp ? tp.sub : jogo.tipo;
  el('dNomeIn').value = jogo.nome;

  const box = el('dCampos');
  box.innerHTML = '';
  for (const c of (tp ? tp.campos : [])) {
    // a lista do rank tem editor proprio embaixo: um textarea nao serve pra
    // importar 200 linhas de gabarito
    if (c.kind === 'lista_rank') continue;
    box.appendChild(campo(c, rascunho[c.nome], (nome, v) => { rascunho[nome] = v; }));
  }

  const ehRank = !!(tp && tp.campos.some((c) => c.kind === 'lista_rank'));
  el('dRank').classList.toggle('hidden', !ehRank);
  if (ehRank) desenharRank();
}

// ------------------------------------------------------------- lista do rank

function desenharRank() {
  const itens = rascunho.lista || [];
  el('dRankN').textContent = itens.length
    ? `${itens.length} posições carregadas` : 'nenhuma posição ainda';
  const prev = el('dPrev');
  prev.innerHTML = '';
  // Prévia só das 30 primeiras: a lista pode ter 500 linhas, e desenhar as 500
  // aqui deixa o formulário pesado sem dizer nada de novo — o que se confere
  // na prévia é se o parse pegou posição e nome certos.
  for (const i of itens.slice(0, 30)) {
    prev.appendChild(h('div', 'linha aberta', `
      <span class="pos">${i.pos}</span>
      <span class="nome">${esc(i.nome)}</span>
      <span class="extra">${esc(i.extra || '')}</span>`));
  }
  if (itens.length > 30) {
    prev.appendChild(h('p', 'note', `…e mais ${itens.length - 30}.`));
  }
}

el('dPick').onclick = () => el('dFile').click();
el('dFile').onchange = () => {
  const f = el('dFile').files[0];
  if (!f) return;
  const fr = new FileReader();
  fr.onload = () => { el('dCola').value = fr.result; parsear(fr.result, f.name); };
  // UTF-8 primeiro; se o txt vier de um Bloco de Notas antigo em ANSI, os
  // acentos aparecem quebrados na prévia — dá pra corrigir na caixa e reler.
  fr.readAsText(f, 'utf-8');
  el('dFile').value = '';
};

el('dParse').onclick = () => parsear(el('dCola').value, 'texto colado');

async function parsear(texto, de) {
  try {
    const r = await apiPost('/api/parse-lista-rank', { texto });
    if (!r.n) { toast('não achei nenhuma linha útil nesse texto', true); return; }
    rascunho.lista = r.itens;
    desenharRank();
    toast(`${r.n} posições lidas de ${de}`);
  } catch (e) { oops(e); }
}

// ----------------------------------------------------------------- acoes

el('dSalvar').onclick = async () => {
  try {
    jogo = await apiPut(`/api/roteiros/${ROTEIRO}/jogos/${JOGO}`, {
      nome: el('dNomeIn').value, attrs: rascunho,
    });
    rascunho = { ...(jogo.attrs || {}) };
    desenhar();
    toast('salvo');
  } catch (e) { oops(e); }
};

(async () => {
  try { await carregar(); } catch (e) {
    oops(e);
    el('semJogo').classList.remove('hidden');
    renderNav(2);
  }
})();
