# video_script — o roteiro dos episodios

Servico web para **montar e conduzir** os episodios do BatataQuente.

```
video_script\run.bat        ->  http://127.0.0.1:8741
```

Separado do `pre_production` (8740) de proposito: aquele cuida do episodio
**ja gravado** (corte, diarizacao, legenda); este cuida do episodio que **ainda
vai ser gravado**. Os dois compartilham o venv (`..\.venv`) e a aparencia (o
`shell.css` do 8740 vem montado em `/shared`, sem copia), e nada mais.

## O roteiro e o dono de tudo

```
roteiro Ep04
 ├─ participantes   Gi  He  Enzo
 └─ jogos           1. Rank das transferencias   ← clicar abre a aba Jogos
                    2. Quem e o impostor?        ← clicar abre a aba Jogos

dados\roteiros\ep04.json    o roteiro inteiro, jogos dentro
dados\partidas\ep04.json    a partida daquele roteiro (mesmo slug, uma so)
```

Os jogos **moram dentro do roteiro**. Nao ha banco de jogos: com um banco
global existia o jogo orfao e existia o item de roteiro apontando pra um jogo
apagado — dois estados que so davam trabalho. Aqui, apagar o roteiro leva os
jogos e a partida junto, e nao ha como um jogo do roteiro nao existir.

## As tres abas

### 1. Roteiro (`/roteiro`) — a tela inicial
Quem joga (so o nome), quais jogos, em que ordem, e as notas de fala. O botao **Jogar roteiro** vai direto pra partida — os jogadores ja estao
definidos aqui, entao nao ha mais tela de montar mesa.

Um jogo sem conteudo cadastrado aparece marcado (`sem lista importada`,
`sem duplas`) — melhor ver aqui do que na hora de jogar. Mas se
acontecer na hora de jogar, da pra resolver la mesmo: a aba 3 edita o conteudo
sem sair da tela (ver abaixo).

### 2. Jogos (`/jogo?roteiro=X&jogo=Y`)
Edita **um** jogo do roteiro — e onde o clique no jogo cai. Nao tem lista: a
lista de jogos e a propria aba Roteiro.

| tipo | atributos |
|---|---|
| **Adivinha rank em lista** | tema, **a lista do rank** (importada), revelados no inicio, aceitar nome parcial |
| **Impostor no quadro** | tema, **as duplas** jogador/impostor, nº de impostores |
| **Impostor na palavra** | tema, **as duplas** jogador/impostor, nº de impostores |
| **So resposta errada** | tema e a lista **pergunta / resposta certa** |
| **Discussao** | o tema (caixa de texto) e o tempo em minutos |

O **So resposta errada** e um caso raro nesta casa: a resposta certa fica
**aberta** na tela. Nos outros jogos o gabarito e o premio e por isso nasce
tapado; aqui ele e a cola de quem apresenta, que precisa saber na hora o que
NAO pode aceitar — a graca e responder errado de proposito. A tela sao tres
colunas: a bolinha de "ja saiu", a resposta certa e a pergunta, nessa ordem
porque e a resposta que o olho procura enquanto a boca le a pergunta.

Marcada, a linha inteira fica **verde** e a bolinha ganha um **×** dentro. Os
dois dizem a mesma coisa de proposito: com a camera ligada quem apresenta olha
de raspao, e um sinal so — so a cor, ou so a marca — se perde.

O `Embaralhar` fecha a rodada: as marcadas **saem da tela** e o que falta volta
numa ordem nova. Elas vao pra `escondidas` no estado da partida, nao sao
apagadas do cadastro — `Trazer todas de volta` (o mesmo `zerar-jogo`) devolve o
jogo inteiro. Apagar pergunta do cadastro a um clique de distancia, numa tela
que roda com a camera ligada, seria um caminho sem volta. A bolinha alterna
(clicar de novo desmarca), como o coracao, porque na gravacao se clica na linha
errada e desfazer tem que ser clicar de novo no mesmo lugar. As perguntas sao
identificadas pelo **indice** na lista: editar a lista no meio da partida pode
mexer nos indices, a mesma ressalva do rank — `_ordem_errada` filtra e completa
a ordem a cada leitura, entao nada quebra, mas confira o que ficou marcado.

Cada linha tem um **lixo** do lado direito, apagado ate o mouse passar. Ele e o
unico botao da tela que mexe no CADASTRO no meio da gravacao, e por isso
pergunta antes e por isso a lixeira existe: a pergunta sai do jogo e vai pra
`dados\lixeira_perguntas.json` com a resposta e **o .txt de onde veio**. A
lixeira e do servico inteiro, nao do roteiro — as perguntas vem dos mesmos
arquivos em `listas\`, e uma que nao funcionou num episodio nao vai funcionar
no proximo; e por ali que se acha a linha pra tirar da origem. Pergunta repetida
nao vira linha repetida la. Nao ha tela pra isso de proposito: e consulta de
depois da gravacao (`GET /api/lixeira`, ou o proprio arquivo).

A lista entra por `Importar .txt` (o navegador le, como no `lista_do_rank.txt`;
os arquivos ficam em `listas\so_resposta_errada\`) ou colada na caixa: uma por linha, `pergunta | resposta certa`, com TAB, `|` ou
`;` separando; linha vazia e linha com `#` sao ignoradas.

A **Discussao** e o jogo mais simples da casa: o tema na tela e o relogio
embaixo, sem gabarito e sem sorteio — entao nada fica tapado nela. O relogio
comeca no `tempo_min` do cadastro (**10 min** de padrao) e continua ajustavel
de 30 em 30 na hora, como o do impostor. E o unico tipo que cadastra tempo: no
impostor isso continua sendo decisao de quem esta com a mesa na frente.

Mais **Vidas neste jogo** (padrao 2), que todo tipo tem: o campo e acrescentado
a TODOS os tipos de uma vez, no fim de `jogos.py`, entao um tipo novo ja nasce
com ele.

As duplas do impostor e as perguntas do "So resposta errada" sao a **mesma
tela** — duas colunas pareadas, uma linha por item (`paresEditor` no `vs.js`,
que recebe como as colunas se chamam). O que importa nas duas e o par, e uma
lista de linhas soltas nao diz quem vai com quem.

O formulario **nao conhece nenhum jogo**: e montado a partir de `jogos.TIPOS`,
servido em `/api/tipos`. Campo novo no dicionario aparece na tela sem tocar no
JS. Tipo novo entra do mesmo jeito (um `in_game` de `"rank"` ou `"impostor"`
diz qual painel a aba 3 usa).

**A lista do rank** entra pelo botao `Escolher lista_do_rank.txt` ou colada na
caixa (os arquivos ficam em `listasdivinha_rank\`). O arquivo e lido pelo navegador e mandado como texto (nao como upload):
assim o servico nao precisa de `python-multipart`, e colar da web funciona
igual. O parser aceita, no mesmo arquivo:

```
1. Cristiano Ronaldo — 222 mi     posicao + nome + valor
2) Lionel Messi | 180 mi          outro separador
3 - Neymar                        sem valor
Mbappe                            sem posicao (vira a 4a)
# linha ignorada
```

O valor depois de TAB, ` | `, ` — ` ou `;` vira o campo `extra`, e aparece
junto na hora da revelacao.

**As duplas do impostor** sao duas colunas pareadas, uma linha por rodada:

```
JOGADOR          IMPOSTOR
arara            bacon
monalisa         guernica
cural                        <- vazio: o impostor nao recebe nada
```

O sorteio escolhe **a linha** e **as pessoas**, e nada mais: quem nao e
impostor ouve a coluna da esquerda, quem e ouve a da direita. Os dois tipos de
impostor tem exatamente esta forma — "quadro" aqui e o **nome** do quadro
("Mona Lisa"), texto como o resto.

Antes nao era assim, e as duas formas anteriores morreram pelo mesmo motivo. O
"Impostor no quadro" subia **imagens** (copiadas pra `dados\quadros\`, servidas
por `/quadros/...`) e o "Impostor na palavra" tinha uma lista unica, de onde o
impostor recebia outra palavra qualquer — um sorteio dentro do sorteio, que
podia dar o par sem graca. Com a dupla explicita, quem monta o episodio decide
o contraste ("arara" x "bacon") em vez de torcer. E o servico inteiro nao lida
mais com arquivo de imagem: sem upload, sem `/quadros`, sem pasta.

Uma linha sem o lado do **jogador** nao e rodada e e ignorada; o lado do
**impostor** vazio e de proposito — e o caso "o impostor nao recebe nada". A
caixa `…ou colar varias de uma vez` aceita `jogador | impostor` por linha, com
TAB, `|` ou `;` separando as colunas.

### 3. In-game (`/in-game?roteiro=X`)
A mesa jogando aquele roteiro. **Uma partida por roteiro**: abrir continua de
onde parou; **Reiniciar** devolve as vidas, fecha o gabarito e apaga os
sorteios, com os mesmos jogadores.

- **Vidas**: sao **de cada jogo**, nao da pessoa — `estado[jogo].vidas[pessoa]`.
  Cada jogo diz com quantos coracoes a mesa entra nele (um rank de quarenta
  minutos nao precisa do mesmo tanto que um impostor de cinco), e o gasto num
  jogo nao segue pro proximo: voltar no chip do jogo anterior encontra o placar
  dele como ficou. Mudar "Vidas neste jogo" no meio do episodio nao zera nada —
  quem gastou continua gastado, e coracao novo entra cheio no fim da fila.
  Cada vida e um booleano numa lista, **nao um contador** — o clique e sempre
  "este coracao aqui", e desfazer e clicar de novo no mesmo lugar. Cheio =
  `Image_stocks\pixel-heart-2779422_960_720.png`, cinza =
  `Image_stocks\pixel_heart_cinza.png` (copiados em `static\img\`).
- **Adivinha rank**: duas caixas — **por nome** (aceita parcial se o jogo
  permitir: "ronaldo" acha "Cristiano Ronaldo") e **por rank** (o numero da
  posicao). As duas revelam a linha e mostram no holofote. Chute que nao esta
  na lista vira "chute perdido" no log — material de edicao.
- **Impostor**: sorteia a dupla da rodada e quem sao os impostores, **e grava** —
  reabrir a tela no meio da rodada nao re-sorteia nem perde quem era. O
  resultado **abre junto com o sorteio**: quem clicou em Sortear quer ler quem
  e, e o clique a mais pra destapar so atrapalhava com a camera ligada. A tampa
  continua ali pra esconder DEPOIS (reflexo, alguem passando atras da tela), e
  o que foi tapado sobrevive ao redesenho. A lista e **por pessoa** (`He
  (impostor) — canjica`), porque e assim que quem apresenta le: um nome de cada
  vez, sem cruzar duas colunas de cabeca.
  A discussao comeca em **2min** e anda de 30 em 30 (`+30s`/`-30s`); o ajuste
  fica gravado, o relogio correndo nao.
- **So resposta errada**: as tres colunas, a bolinha e o `Embaralhar`. Nada
  fica tapado neste jogo (ver acima).
- **Discussao**: o tema aberto no holofote e o mesmo cronometro, comecando nos
  minutos do cadastro. Mudar os minutos no editor daqui devolve o relogio pro
  numero novo — senao a tela continuaria marcando o ajuste de um cadastro que
  nao existe mais.
- Trocar a mesa no roteiro no meio do episodio **nao** zera o placar: quem
  chega entra com vidas cheias em cada jogo, quem ja gastou continua gastado.
  `Zerar este jogo` enche as vidas **daquele** jogo e deixa os outros em paz;
  `Reiniciar partida` zera o episodio inteiro.
- **Conteudo do jogo, editavel aqui mesmo** (`Editar aqui`, no fim do painel):
  acrescentar/tirar dupla, mudar o nº de impostores, escrever o tema da
  discussao, importar as perguntas do .txt, acrescentar posicao no rank ou
  substituir a lista inteira — sem ir pra aba Jogos e voltar. Descobrir que
  faltou cadastrar alguma coisa e coisa que acontece com a camera ligada, e a
  resposta certa e digitar ali, nao navegar. Grava no jogo do roteiro na hora.
  Num jogo ainda vazio o editor ja abre sozinho.

> **Toda acao grava em disco na hora e redesenha com a resposta do servidor.**
> A tela nunca mostra um estado que o disco nao tem: durante a gravacao, um
> placar otimista errado e pior do que um clique perdido. Um F5 no meio do
> episodio volta na mesma partida, com o placar.

O **gabarito do rank nasce fechado** e so abre no que foi revelado. Nao e
enfeite: quem apresenta olha pra esta tela ao vivo. O sorteio do impostor nao
segue essa regra — la o clique em Sortear ja e o pedido, e o resultado abre com
ele.

## Arquivos

```
video_script\
  run.bat          sobe na 8741 (usa o venv do pre_production)
  app.py           FastAPI: as 3 telas + /api
  roteiros.py      participantes + os jogos que moram dentro do roteiro
  jogos.py         TIPOS (o catalogo) + parse do lista_do_rank.txt + as buscas
  partidas.py      vidas, revelacoes e sorteios de uma gravacao
  store.py         um JSON por coisa, escrita atomica (.tmp + rename)
  lixeira.py       as perguntas descartadas, com o .txt de origem
  static\          3 telas, vs.js (comum), vs.css (so o que o shell nao tem)
  listas\          o material que se importa, uma pasta por jogo (ver o README de la)
  dados\roteiros|partidas\<slug>.json
  dados\lixeira_perguntas.json   o que foi jogado fora, do servico inteiro
```

`dados\` fica fora do git, como `projects\` do 8740.

## Detalhes que custam tempo se esquecidos

- **O gabarito nao pode vazar na tela.** Linha fechada mostra `— — —`, nunca o
  nome. Se mexer no `painelRank`, mantenha isso. As excecoes sao de proposito,
  e nao esquecimento: a Discussao e o So resposta errada nao tem gabarito
  nenhum a guardar (o tema e a resposta certa sao a cola de quem apresenta), e
  o **sorteio do impostor abre junto com o clique em Sortear** — ali o clique
  JA foi o pedido; exigir um segundo era atrito no meio da gravacao. A tampa
  do `painelImpostor` esconde depois, nao antes.
- **Salvar o roteiro nao toca nos `attrs` dos jogos**, so no nome/ordem/duracao
  /notas. Quem edita atributo e a aba Jogos. Sem essa separacao, salvar o
  roteiro com um jogo aberto noutra aba apagaria a lista importada la.
- **Tirar uma pergunta do meio renumera as de baixo.** As perguntas sao
  identificadas pela posicao na lista, entao o lixo chama `_deslocar()`, que
  puxa marcacao e ordem junto. Sem isso, jogar a 3ª fora faria a marcacao da 4ª
  passar a apontar pra 5ª — e ao vivo ninguem ia entender por que a linha errada
  ficou verde.
- **`_ajustar_vidas` roda na leitura E na escrita, e e idempotente.** E ele que
  faz o placar caber no que o jogo pede sem nunca apagar o que foi gasto. Se
  voce mexer nele, mantenha isso: e a unica coisa entre "mudei o numero de
  vidas" e "perdi o placar no meio da gravacao".
- **`revelados_inicio` e sorteado uma vez, na criacao da partida**, e gravado.
  Sortear na hora de desenhar faria o rank mudar sozinho a cada F5.
- **Cuidado com `or` em numero que pode ser zero.** `body.get("segundos") or
  PADRAO` transformava o `-30s` que chega em zero no tempo padrao, em vez de
  bater no piso. Ja mordeu uma vez.
- **Se um dia voltar imagem aqui, nunca guarde caminho de disco.** O navegador
  bloqueia `file://` dentro de uma pagina `http://`, entao a imagem simplesmente
  nao aparece — o caminho e copiar o arquivo pra dentro do projeto e servir por
  URL. O "Impostor no quadro" ja foi assim; virou texto porque o nome do quadro
  bastava. O `jogos.migrar()` limpa o que sobrou dos cadastros antigos.
- **Estado de tela que precisa sobreviver ao redesenho** vai numa variavel de
  modulo, nao no DOM. Toda acao do in-game redesenha a tela inteira: sem o
  `editorAberto`, cadastrar uma dupla fecharia o editor na cara de quem esta
  cadastrando a segunda.
- **Substituir a lista do rank no meio da partida** nao mexe no que ja foi
  revelado: os revelados sao guardados por numero de posicao. Mudar a ordem da
  lista faz aquele numero apontar pra outro nome — o editor avisa, e "Zerar
  este jogo" resolve.
- **Contraste** — a regra desta casa, na regua do `turnsEditor`: cada nivel de
  caixa sobe de superficie (`--void` < `--slab` < `--riser` < `--lift`), e
  dentro de uma caixa o texto e `--chalk` ou `--ash`, nunca `--smoke`. Nada
  abaixo de 12.5px carrega informacao. O `vs.css` sobrescreve os rotulos do
  `shell.css` por isso.
- **O `/static` vai com `Cache-Control: no-store`.** Sem isso o Chrome guarda o
  `.js` e a correcao que voce acabou de fazer nao aparece na tela — e voce passa
  a depurar um conserto que ja estava certo. Custa zero em 127.0.0.1.
- **`.hidden` do shell tem `!important`**, entao um `style="display:grid"`
  inline convive com ele sem estragar o esconde/mostra.
