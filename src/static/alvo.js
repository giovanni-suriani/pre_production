/* Qual corte a etapa 3 esta editando.

   Vem da URL da pagina (`/turnos?projeto=X&corte=Y`, montado pelo `goEditor`
   do cortes.js e pela barra do shell.js), NAO de um "corte ativo" guardado no
   servidor. Enquanto o alvo morava no config.json havia um so por SERVIDOR:
   abrir dois cortes em duas abas fazia a segunda roubar a primeira.

   Mora num arquivo proprio porque tem DOIS consumidores em ordens diferentes:
   os blocos inline do turnos.html (cabecalho do corte, painel da transcricao),
   que rodam durante o parse, e o app.js, que carrega no fim. Definir no app.js
   deixava os blocos inline sem o helper - e o sintoma era mudo: o fetch
   voltava 409, o catch engolia, e o cabecalho dizia "nenhum corte ativo" com
   o corte aberto na tela. Quem pegou isso foi o tests/ui.py. */

const ALVO = (() => {
  const q = new URLSearchParams(location.search);
  return { projeto: q.get('projeto') || '', corte: q.get('corte') || '' };
})();

/* Acrescenta projeto/corte a uma URL da API, preservando o que ja estiver la
   (?file=..., ?clear=...). So' mexe em /api/ - caminho de pagina passa
   intacto. */
function comAlvo(path) {
  if (!path.startsWith('/api/')) return path;
  const u = new URL(path, location.origin);
  if (ALVO.projeto) u.searchParams.set('projeto', ALVO.projeto);
  if (ALVO.corte) u.searchParams.set('corte', ALVO.corte);
  return u.pathname + u.search;
}
