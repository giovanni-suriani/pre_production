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
    // estes dois tem editor proprio embaixo: um textarea nao serve pra
    // importar 200 linhas de gabarito nem pra escolher imagem
    if (c.kind === 'lista_rank' || c.kind === 'imagens') continue;
    box.appendChild(campo(c, rascunho[c.nome], (nome, v) => { rascunho[nome] = v; }));
  }

  const ehRank = !!(tp && tp.campos.some((c) => c.kind === 'lista_rank'));
  el('dRank').classList.toggle('hidden', !ehRank);
  if (ehRank) desenharRank();

  const ehQuadro = !!(tp && tp.campos.some((c) => c.kind === 'imagens'));
  el('dQuadros').classList.toggle('hidden', !ehQuadro);
  if (ehQuadro) desenharQuadros();
}

// ---------------------------------------------------------------- quadros

/* Os quadros sao gravados na hora, direto no servidor — nao esperam o Salvar.
   E um arquivo, nao um campo de texto: segurar ele no rascunho ate alguem
   lembrar de salvar so criaria a chance de perder o upload. */
function desenharQuadros() {
  const qs2 = rascunho.quadros || [];
  el('qN').textContent = qs2.length
    ? `${qs2.length} ${qs2.length === 1 ? 'quadro' : 'quadros'}`
    : 'nenhum quadro ainda';
  const box = el('qLista');
  box.innerHTML = '';
  qs2.forEach((src, i) => {
    const c = h('div', 'thumb');
    c.innerHTML = `
      <img src="${esc(src)}" alt="quadro ${i + 1}">
      <div class="cap">${esc(src.startsWith('/quadros/')
        ? src.split('/').pop() : src)}</div>
      <button class="x" title="tirar este quadro">×</button>`;
    // caminho de disco antigo (file://) e URL quebrada caem aqui
    c.querySelector('img').onerror = () => {
      c.classList.add('quebrado');
      c.querySelector('img').replaceWith(h('div', 'ruim', 'não carrega'));
    };
    c.querySelector('.x').onclick = async () => {
      const novos = qs2.filter((_, k) => k !== i);
      try {
        // salva na hora: o arquivo so e apagado do disco quando o servidor ve
        // que ninguem mais aponta pra ele
        jogo = await apiPut(`/api/roteiros/${ROTEIRO}/jogos/${JOGO}`,
          { attrs: { ...rascunho, quadros: novos } });
        rascunho = { ...(jogo.attrs || {}) };
        desenharQuadros();
        toast('quadro removido');
      } catch (e) { oops(e); }
    };
    box.appendChild(c);
  });
}

el('qPick').onclick = () => el('qFile').click();
el('qFile').onchange = async () => {
  const arquivos = [...el('qFile').files];
  el('qFile').value = '';
  for (const f of arquivos) {
    try {
      const conteudo = await new Promise((ok, fail) => {
        const fr = new FileReader();
        fr.onload = () => ok(fr.result);        // data:image/png;base64,...
        fr.onerror = () => fail(new Error(`não consegui ler ${f.name}`));
        fr.readAsDataURL(f);
      });
      jogo = await apiPost(`/api/roteiros/${ROTEIRO}/jogos/${JOGO}/quadros`,
        { nome: f.name, conteudo });
      rascunho = { ...(jogo.attrs || {}) };
      desenharQuadros();
    } catch (e) { oops(e); }
  }
  toast(`${(rascunho.quadros || []).length} quadro(s) no jogo`);
};

el('qAddUrl').onclick = async () => {
  const url = el('qUrl').value.trim();
  if (!/^https?:\/\//i.test(url)) {
    toast('cole um endereço começando com http:// ou https://', true);
    return;
  }
  try {
    jogo = await apiPut(`/api/roteiros/${ROTEIRO}/jogos/${JOGO}`, {
      attrs: { ...rascunho, quadros: [...(rascunho.quadros || []), url] },
    });
    rascunho = { ...(jogo.attrs || {}) };
    el('qUrl').value = '';
    desenharQuadros();
  } catch (e) { oops(e); }
};

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
