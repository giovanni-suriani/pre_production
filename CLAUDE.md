# pre_production

Tudo que acontece **antes** de abrir o DaVinci Resolve, numa tela só (FastAPI +
HTML estático). Substitui o fluxo de scripts soltos do `scriptsPrimarios\`.

```
run.bat  →  http://127.0.0.1:8740     (cria o .venv na 1ª execução)
```

`README.md` é a documentação completa (as três etapas, um exemplo ponta a ponta
com números reais, o `config.json`, chaves/ambiente). Este arquivo é só o que um
agente precisa saber antes de mexer.

## As três etapas

| rota | etapa | sai |
|---|---|---|
| `/` | **ProjectEditor** — vídeo, nome, quantas pessoas (1–4) na mesa, cadeira de cada uma e quantas vozes há fora de quadro | `project.json` + `media\<projeto>.wav` |
| `/cortes` | **CutsEditor** — trecho na onda, mapa de tracks, método, rodar | `corte.json` + `audio.wav` + `turns*.json` |
| `/turnos` | **turnsEditor** — corrigir turnos ouvindo/lendo/arrastando | `turnsManual.json` |

Depois: `editor_proxy\SpeakerSwitch.py` e o GiAutoSubs, dentro do Resolve.

## Estrutura

```
src\app.py         rotas e API          src\methods.py    métodos de diarização (dados, não código)
src\config.py      caminhos, .env       src\turns.py      ler/gravar turns*.json, converter base de tempo
src\projects.py    project.json/corte.json   src\timecode.py  segundos ↔ MM:SS.mmm ↔ frames
src\media.py       ffprobe/ffmpeg/waveform  src\jobs.py    trabalhos longos com log e progresso
src\giautosubs.py + src\gerar_macro.py + src\estilo_legenda.py   → ver giautosubs\CLAUDE.md
editor_proxy\SpeakerSwitch.py            a cópia ATIVA (a de scriptsPrimarios está congelada)
docs\arquitetura-giautosubs.md           o desenho do fluxo GiAutoSubs em duas fases
tests\                                    testes que dirigem o app de verdade
projects\<proj>\cortes\<corte>\           os dados (manifesto, não banco)
video_script\                             OUTRO serviço (8741) → video_script\README.md
```

`video_script\` não faz parte deste app: é um serviço separado, na porta 8741,
para o episódio que **ainda vai ser gravado**. Lá o **roteiro é o dono de
tudo** — ele guarda quem joga (só o nome) e os jogos, com os atributos dentro;
não há banco de jogos solto. Três abas: Roteiro (inicial), Jogos (edita UM jogo
do roteiro) e In-game (conduz a mesa), com uma partida por roteiro. Cinco tipos
de jogo: adivinha rank em lista, impostor no quadro, impostor na palavra,
discussão e só resposta errada. Compartilha só o venv (`.venv`) e o
`src\static\shell.css` (montado lá em `/shared`, sem cópia) — subir ou derrubar
um não afeta o outro. Sobe com `video_script\run.bat`.

O que decidiu o desenho de lá, e que não se adivinha lendo o código:

- **As vidas são de cada JOGO**, não do participante
  (`estado[jogo].vidas[pessoa]`, campo "Vidas neste jogo", padrão 2). Um rank
  de quarenta minutos não precisa do mesmo tanto de coração que um impostor de
  cinco, e o gasto num jogo não segue pro próximo.
- **Os dois jogos de impostor são duplas `jogador | impostor`** — o sorteio só
  escolhe a linha e as pessoas, o par já vem decidido no cadastro. Não há
  imagem nenhuma no serviço: "quadro" ali é o NOME do quadro, texto.
- **O que se importa mora em `video_script\listas\<jogo>\`** (os top100 do
  rank, o .txt de perguntas). Quem lê é o navegador, no clique do import; o
  conteúdo passa a morar no JSON do roteiro, e mexer no .txt depois não muda
  jogo já cadastrado.
- **A tela do desktop fica virada para quem COMANDA, nunca para a mesa.** Os
  jogadores nao enxergam o monitor: o que esta nele e a cola de quem apresenta.
  Por isso a palavra de cada pessoa pode aparecer aberta na mesa do In-game, e
  por isso a tampa do sorteio serve contra reflexo e gente passando atras — nao
  contra os jogadores, que nunca teriam visto de qualquer jeito. Ao desenhar
  qualquer tela deste servico, assuma UM leitor: quem conduz.
- **Impostor: o layout inteiro e a rodada.** A palavra da mesa e a coluna
  Jogador da LINHA 1; cada impostor sorteado leva a coluna Impostor da sua
  linha, na ordem (1o impostor -> linha 1, 2o -> linha 2), entao dois
  impostores recebem palavras DIFERENTES. O sorteio escolhe so as pessoas —
  nao escolhe linha. Trocar de rodada e reescrever as linhas.

- **O padrao visual do video_script e "limpo, com cor so no que distingue".**
  Decisao do usuario para o projeto INTEIRO, nao so para a tela de Roteiro:
  - **Texto que so explica sai.** Subtitulo de cabecalho, nota de rodape de
    campo, aviso de estado vazio, contagem de status ("3 na mesa", "2 sem
    conteudo"), cracha de pendencia. A tela e lida de relance com a camera
    ligada; quem esta gravando ja sabe o que a tela faz.
  - **Campo que ninguem preenche sai** — nao nasce "por completude".
  - **A cor serve para DISTINGUIR, nunca para decorar.** Hoje sao cinco, uma
    por tipo de jogo (ver a paleta no `video_script/static/vs.css`): azul,
    roxo, rosa, verde e prata. A mesma cor tem que significar a mesma coisa em
    todo lugar onde aparecer — o card na lista e o chip que cria aquele jogo
    dividem o token `--t` justamente por isso.
  - **Um portador de cor por elemento.** No card do jogo a cor esta na BORDA e
    no numero; o fundo fica neutro. Pintar borda e fundo juntos vira cerca de
    cores com cinco itens na tela.
  - **Tons na clareza da casa** (a faixa do `--info`/`--caution` do
    `shell.css`), nunca as cores puras: sobre o `--riser` escuro, verde e rosa
    saturados vibram.

- **Como o usuario itera em tela, e o que ele quer de volta.** Aprendido na
  faxina de 14-15/09/2026, quando ele reviu as tres telas uma a uma:
  - **Ele cola o HTML renderizado e diz o que esta errado.** O pedido e sobre
    AQUELE elemento. Mude so ele, verifique, e diga o que mudou — nao
    aproveite a visita para "melhorar junto" o que esta em volta.
  - **"Gostei, nao mexa aqui" e definitivo.** A mesa do In-game (`.mesa` /
    `.jogador` / `.vidas`) e o botao Sortear foram congelados assim. Quando
    ele quis a palavra no card do jogador, ele mesmo abriu a excecao.
  - **Sem botao de Gravar.** "O que estiver nesse layout vai ser o que vai ser
    considerado" — a tela E o dado. Se tirar o botao, grave sozinho: com pausa
    na digitacao e SEM redesenhar (redesenhar leva o foco e o cursor junto,
    ver `salvarAttrsQuieto`).
  - **O alvo do clique e o card inteiro**, nao um link dentro dele. Os botoes
    que vivem dentro precisam de `closest('button')` para nao navegarem junto.
  - **Rotulo e valor do mesmo mostrador tem o mesmo tamanho** ("Rodada" saiu de
    10.5px para os 40px do numero). Rotulo pequeno ao lado de numero grande ele
    le como ruido, nao como legenda.
  - **Selecionado nao pode perder a identidade.** O chip do jogo aberto
    continua na cor do tipo (borda cheia + texto claro); virar branco fazia do
    unico jogo que importa o unico sem cor.
  - **Ele nao pede tudo de uma vez, e isso e de proposito.** Botao virou
    horizontal, depois ganhou texto, depois perdeu o texto, depois mudou de
    lugar. Nao antecipe os proximos passos — faca o pedido e espere.

- **0 e um valor de verdade neste servico, nao "vazio".** `n_impostores: 0` e
  uma rodada sem impostor nenhum, e `segundos: 0` e o piso do cronometro.
  Todo `x or padrao` em cima desses campos e bug esperando o dia em que alguem
  escolher zero — foi assim no `app.py` (tempo) e no `partidas.py`
  (impostores). Use `None if x is None else x`.

- **A lista de jogos do Roteiro e so a lista.** Cada item mostra o numero, o
  nome e os tres botoes (subir, descer, remover); o card INTEIRO abre o editor,
  e a cor do tipo vive na borda. Nao ha resumo, seta de "editar", cracha de
  tipo nem aviso de pendencia — tudo isso foi removido a pedido do usuario.
  **Nao acrescente campo de duracao, caixa de "notas de fala", nem cracha
  repetindo o tipo do jogo**: o tipo ja esta no nome, e os outros dois
  eram campos que ninguem preenchia ocupando altura numa tela que se le de
  relance com a camera ligada. Isso vale para **todo tipo de jogo novo**. As
  chaves `duracao_min` e `notas` continuam no JSON e o `atualizar()` so grava a
  que VEM no corpo — quem nao manda, preserva.

- **Pergunta jogada fora vai pra `dados\lixeira_perguntas.json`** com a
  resposta e o .txt de origem — lixeira única do serviço, porque as perguntas
  vêm dos mesmos arquivos e o descarte vale pro próximo episódio.
- **Gabarito fechado é a regra, com exceções de propósito**: a Discussão e o Só
  resposta errada mostram tema e resposta abertos — ali não é prêmio, é a cola
  de quem apresenta. E o **sorteio do impostor abre junto com o clique em
  Sortear**: o clique já foi o pedido, e exigir um segundo pra destapar era só
  atrito com a câmera ligada. A tampa esconde depois, não antes.
- **`/static` vai com `Cache-Control: no-store`.** Sem isso o Chrome guarda o
  `.js` e a correção não aparece na tela — e você depura um conserto que já
  estava certo.

Se for mexer no CSS de lá — ou criar qualquer tela nova que herde o
`shell.css` — a régua de contraste é o `turnsEditor`: cada nível de caixa sobe
de superfície (`--void` < `--slab` < `--riser` < `--lift`), dentro de uma caixa
o texto é `--chalk` ou `--ash` (nunca `--smoke`), e nada abaixo de 12.5px
carrega informação, rótulo incluído. Os `.lbl` de 10.5px em caixa alta do
`shell.css` funcionam onde são quatro; numa tela com dezenas viram chiado.

## Invariantes — quebrar qualquer uma produz erro silencioso

- **Uma base de tempo só.** `turnsXxx.json` é **sempre tempo absoluto da
  mídia-fonte**; a saída crua do script fica em `turnsXxx.raw.json`. O
  `corte.json` grava `time_base: "absolute"` e `audio_offset` explicitamente.
  Foi a ambiguidade que motivou o projeto inteiro — não reintroduzir.
- **O `fps` vem do ffprobe e mora no manifesto.** `int(round(segundos * fps))` é
  a mesma conta em quatro lugares; um fps errado erra todo corte, em silêncio.
- **O mapa de tracks é decisão POR CORTE**, mora no `corte.json` (`track_map` /
  `off_camera`), nunca numa constante de script. O `speaker_switch.json` foi
  **aposentado** em 02/09 — o `SpeakerSwitch.py` lê o `corte.json` direto
  (fallback pro arquivo antigo só pros cortes velhos).
- **`origin_frame`** = `round(início × fps)` = o `clip_origin` esperado da
  timeline de origem no Resolve. Divergiu → os turnos do começo são clampados e
  somem calados. `clip_origin` = `GetLeftOffset` **+ o offset da própria
  mídia** (`media_base()`): editando do episódio inteiro isso é 0, mas editando
  do `<corte>_<N>frames.mkv` o frame 0 do arquivo já é o frame
  `video_offset × fps` do episódio. Aí o script apara os N frames sozinho — a
  timeline nova nasce no corte planejado, que é o que o `.srt` (base timeline)
  assume.
- **`MIN_SPAN_FRAMES = 2`.** Turno menor que isso é absorvido no vizinho e
  **some do corte final sem avisar**. A tabela de resultados marca como `curto`.
- **`-c copy` não corta em qualquer frame** — o app mede onde caiu o keyframe e
  grava `video_offset` separado do `audio_offset`. O mesmo valor **em frames**
  vai no nome do arquivo: `<corte>_<N>frames.mkv`. Os fontes têm GOP de 250
  frames, então N cai em qualquer lugar de 0 a 249 (~8,3 s a 30 fps, ~4,2 s a
  60) — é quanto aparar ao levar o trecho pro Resolve. Mexer no trecho
  (`PATCH`) larga a mão do vídeo antigo, que foi medido pro trecho anterior.
- **Nada é apagado por um clique**: excluir move pra `projects\_lixeira\`;
  salvar por cima gera `.bak` datado; escrita atômica.
- **`shell.css` é escopado sob `body.page`.** Ele carrega DEPOIS do `style.css`
  na etapa 3; qualquer seletor global vaza no editor sem erro nenhum.
  `tests\ui.py` existe pra pegar isso.
- **Cor é dado, nunca decoração.** Não existe verde de "status ok" — ausência de
  aviso já é a boa notícia, e `#4ecb8f` pertence ao terceiro participante.
- **`static\app.js` e `static\style.css` são cópias LITERAIS** do
  `scriptsPrimarios\turnsEditor\`. Por isso este servidor responde à mesma API
  (`/api/config`, `/api/turns`, `/api/transcript`, `/api/peaks`, `/api/audio`) —
  o corte ativo mora no servidor, não na URL.
- **Dois Pythons, de propósito.** O `.venv` daqui tem só fastapi/uvicorn/numpy.
  O `python_exe` do `config.json` aponta pro Python 3.12 do sistema, com
  torch/pyannote/faster-whisper/google-genai — versões **presas umas às
  outras**, ver o `CLAUDE.md` da raiz do BatataQuente. Não misturar.
- **Os diarizadores não são reimplementados aqui**: continuam em
  `scriptsPrimarios\` e são chamados por caminho absoluto, com `--title`
  recebendo a **pasta do corte** (no Windows `os.path.join(raiz, absoluto)`
  devolve o absoluto). Nenhum arquivo de lá é movido ou alterado.

## Escolha de método (medido, não opinião)

**Whisper large-v3 decide QUANDO, Gemini(vídeo) decide QUEM.** O
`gemini_transcribe` é ruim para o tempo: 100% dos timestamps em múltiplos de
0,1 s, 114 sobreposições em 313 segmentos, 136 palavras com `start == end`
(palavra de duração zero = o destaque da legenda nunca acende). Ver a memória
`project-giautosubs`.

Diarização acústica pura **não separa vozes em áudio mono de mic única** — é
limite estrutural, não bug do pyannote (5 abordagens falharam num benchmark).
Não trocar pyannote por NeMo/WeSpeaker esperando conserto.

## A legenda, em dois formatos

`.srt` (tempo da **timeline**, pro Import → Subtitle nativo) e
`<corte>.giautosubs.json` (tempo **absoluto**, com `words`). São dois destinos,
**um texto só**. O `words` é o que acende a palavra falada — o `.srt` não tem
onde guardá-lo e o sintoma só aparece lá na frente, no Resolve. O
`.giautosubs.json` vira o `transcript` do corte.

## Testes

```powershell
.venv\Scripts\python.exe tests\smoke.py    # ponta a ponta, dirige o app
```

Também: `ui.py` (vazamento de CSS), `quebra.py` (repartição de legenda offline),
`cut_speakerswitch.py`, `preprod_speakerswitch.py`, `dialogo_speakerswitch.py`.

## Ponta solta conhecida

`projects.py:333 default_track_map` ainda aloca track pro `cut` e a tela mostra
"cut → V4" — enganoso: `cut` significa **jogar fora o trecho**, e o
`SpeakerSwitch.py` ignora esse mapeamento.
