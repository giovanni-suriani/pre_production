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
 ├─ participantes   Gi(3 vidas)  He(3)  Enzo(2)
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
Quem joga (nome + quantas vidas), quais jogos, em que ordem, e as notas de
fala. O botao **Jogar roteiro** vai direto pra partida — os jogadores ja estao
definidos aqui, entao nao ha mais tela de montar mesa.

Um jogo sem conteudo cadastrado aparece marcado (`sem lista importada`, `sem
palavras`, `sem quadros`) — melhor ver aqui do que na hora de jogar. Mas se
acontecer na hora de jogar, da pra resolver la mesmo: a aba 3 edita o conteudo
sem sair da tela (ver abaixo).

### 2. Jogos (`/jogo?roteiro=X&jogo=Y`)
Edita **um** jogo do roteiro — e onde o clique no jogo cai. Nao tem lista: a
lista de jogos e a propria aba Roteiro.

| tipo | atributos |
|---|---|
| **Adivinha rank em lista** | tema, **a lista do rank** (importada), revelados no inicio, aceitar nome parcial |
| **Impostor no quadro** | tema, **os quadros** (imagens subidas), o que o impostor recebe, nº de impostores |
| **Impostor na palavra** | tema, palavras, o que o impostor recebe, nº de impostores |

O formulario **nao conhece nenhum jogo**: e montado a partir de `jogos.TIPOS`,
servido em `/api/tipos`. Campo novo no dicionario aparece na tela sem tocar no
JS. Tipo novo entra do mesmo jeito (um `in_game` de `"rank"` ou `"impostor"`
diz qual painel a aba 3 usa).

**A lista do rank** entra pelo botao `Escolher lista_do_rank.txt` ou colada na
caixa. O arquivo e lido pelo navegador e mandado como texto (nao como upload):
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

**Os quadros** entram por `Escolher imagens…`: o servico **guarda uma copia** em
`dados\quadros\<roteiro>\` e serve por `/quadros/...`. Antes o jogo guardava o
caminho do arquivo no disco e a pagina nunca conseguia mostrar — o navegador
bloqueia `file://` dentro de uma pagina `http://`. Com a copia, a imagem
aparece no in-game, o roteiro fica autossuficiente (mover a pasta de origem
depois nao quebra a gravacao) e tirar um quadro da lista apaga o arquivo junto.
Endereco `http` da web tambem serve, pelo campo de colar.

O arquivo sobe em **base64 dentro do JSON**, como o `lista_do_rank.txt` sobe
como texto — assim o servico nao precisa de `python-multipart` num venv que so
tem fastapi/uvicorn/numpy. A extensao e decidida pelo **conteudo**, nao pelo
nome: o `.png` que na verdade e um JPEG e comum, e quem decide como servir e o
byte. SVG fica de fora de proposito (e documento que pode carregar script).

### 3. In-game (`/in-game?roteiro=X`)
A mesa jogando aquele roteiro. **Uma partida por roteiro**: abrir continua de
onde parou; **Reiniciar** devolve as vidas, fecha o gabarito e apaga os
sorteios, com os mesmos jogadores.

- **Vidas**: uma lista de booleanos, **nao um contador** — o clique e sempre
  "este coracao aqui", e desfazer e clicar de novo no mesmo lugar. Cheio =
  `Image_stocks\pixel-heart-2779422_960_720.png`, cinza =
  `Image_stocks\pixel_heart_cinza.png` (copiados em `static\img\`).
- **Adivinha rank**: duas caixas — **por nome** (aceita parcial se o jogo
  permitir: "ronaldo" acha "Cristiano Ronaldo") e **por rank** (o numero da
  posicao). As duas revelam a linha e mostram no holofote. Chute que nao esta
  na lista vira "chute perdido" no log — material de edicao.
- **Impostor**: sorteia a palavra/quadro e quem sao os impostores, **e grava** —
  reabrir a tela no meio da rodada nao re-sorteia nem perde quem era. Fica
  tapado ate clicar — inclusive o quadro, que so aparece no clique da tampa.
  A discussao comeca em **2min** e anda de 30 em 30 (`+30s`/`-30s`); o ajuste
  fica gravado, o relogio correndo nao.
- Trocar a mesa no roteiro no meio do episodio **nao** zera o placar: quem
  chega entra com vidas cheias, quem ja gastou continua gastado.
- **Conteudo do jogo, editavel aqui mesmo** (`Editar aqui`, no fim do painel):
  acrescentar/tirar palavra, subir/tirar quadro, acrescentar posicao no rank ou
  substituir a lista inteira — sem ir pra aba Jogos e voltar. Descobrir que
  faltou cadastrar alguma coisa e coisa que acontece com a camera ligada, e a
  resposta certa e digitar ali, nao navegar. Grava no jogo do roteiro na hora.
  Num jogo ainda vazio o editor ja abre sozinho.

> **Toda acao grava em disco na hora e redesenha com a resposta do servidor.**
> A tela nunca mostra um estado que o disco nao tem: durante a gravacao, um
> placar otimista errado e pior do que um clique perdido. Um F5 no meio do
> episodio volta na mesma partida, com o placar.

O **gabarito nasce fechado** e so abre no que foi revelado; vale pro sorteio do
impostor tambem. Nao e enfeite: quem apresenta olha pra esta tela ao vivo.

## Arquivos

```
video_script\
  run.bat          sobe na 8741 (usa o venv do pre_production)
  app.py           FastAPI: as 3 telas + /api
  roteiros.py      participantes + os jogos que moram dentro do roteiro
  jogos.py         TIPOS (o catalogo) + parse do lista_do_rank.txt + as buscas
  partidas.py      vidas, revelacoes e sorteios de uma gravacao
  store.py         um JSON por coisa, escrita atomica (.tmp + rename)
  quadros.py       guarda/serve/apaga as imagens do "Impostor no quadro"
  static\          3 telas, vs.js (comum), vs.css (so o que o shell nao tem)
  dados\roteiros|partidas\<slug>.json
  dados\quadros\<roteiro>\        as imagens, servidas em /quadros/...
```

`dados\` fica fora do git, como `projects\` do 8740.

## Detalhes que custam tempo se esquecidos

- **O gabarito nao pode vazar na tela.** Linha fechada mostra `— — —`, nunca o
  nome; o sorteio do impostor fica tapado ate o clique. Se mexer no
  `painelRank`/`painelImpostor`, mantenha isso.
- **Salvar o roteiro nao toca nos `attrs` dos jogos**, so no nome/ordem/duracao
  /notas. Quem edita atributo e a aba Jogos. Sem essa separacao, salvar o
  roteiro com um jogo aberto noutra aba apagaria a lista importada la.
- **`revelados_inicio` e sorteado uma vez, na criacao da partida**, e gravado.
  Sortear na hora de desenhar faria o rank mudar sozinho a cada F5.
- **Cuidado com `or` em numero que pode ser zero.** `body.get("segundos") or
  PADRAO` transformava o `-30s` que chega em zero no tempo padrao, em vez de
  bater no piso. Ja mordeu uma vez.
- **Nunca guarde caminho de disco de imagem.** O navegador bloqueia `file://`
  dentro de uma pagina `http://`, entao a imagem simplesmente nao aparece. Por
  isso o upload copia o arquivo pra `dados\quadros\` e devolve uma URL. Um
  cadastro antigo com caminho de disco continua no JSON e o in-game explica o
  que fazer, em vez de mostrar um retangulo quebrado.
- **Estado de tela que precisa sobreviver ao redesenho** vai numa variavel de
  modulo, nao no DOM. Toda acao do in-game redesenha a tela inteira: sem o
  `editorAberto`, cadastrar uma palavra fecharia o editor na cara de quem esta
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
- **`.hidden` do shell tem `!important`**, entao um `style="display:grid"`
  inline convive com ele sem estragar o esconde/mostra.
