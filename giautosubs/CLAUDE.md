# GiAutoSubs

Legendas **estilizadas** no DaVinci Resolve a partir de uma transcrição já
revisada, **sem re-transcrever**. É projeto próprio do usuário — o código ainda
mora dentro do `pre_production/`, mas separar continua pendente. O diferencial:
clicar num clipe de legenda e editar os atributos na aba **Inspector**
(bolha, outline, caixa, box shadow), como no AutoSubs — cujo grafo de animação
é reaproveitado.

## Não re-derivar por leitura de código

Estes dois arquivos são a fonte. Leia antes de investigar qualquer coisa:

| arquivo | o que responde |
|---|---|
| `../docs/arquitetura-giautosubs.md` | o desenho do fluxo inteiro, em duas fases (preparação / aplicação) — comece por aqui se a dúvida for "quem produz o quê" |
| `MACRO.md` | como um `.setting` funciona por dentro; §2 = a cadeia de precedência (por que um valor escrito "certo" não aparece na tela); §5 = receita de 6 passos pra criar um atributo novo; §7 = tabela sintoma→causa |
| `ESTADO.md` | o histórico das versões do macro e as caçadas já feitas |

Ver também a memória `project-giautosubs` e `feedback-resolve-scripting-gotchas`.

## As peças

| arquivo | papel |
|---|---|
| `vendor/autosubs-macro.setting` | macro original do AutoSubs, **intocado** |
| `../src/gerar_macro.py` | patcheia o vendor → `GiAutoSubs Caption.setting`; `--instalar` copia pra `%APPDATA%\...\Fusion\Templates\Edit\Titles` |
| `GiAutoSubs Caption.setting` | o resultado — **nunca editar na mão** |
| `valida_macro.lua` | valida o `.setting` fora do Resolve (via `fuscript`) |
| `GiAutoSubs.lua` | roda **dentro** do Resolve (Workspace > Scripts); cria e estiliza os clipes |
| `GiDiag.lua` | diagnóstico somente-leitura (Scripts/Utility) |
| `testes.lua` | roda o `main` contra um Resolve falso |
| `amostra_legendas.lua` | fixture com tempo por palavra |
| `../src/giautosubs.py` | estilo + pipeline → `legendas.lua` |
| `../estilos.json` | a configuração editável (padrão: `capcut_bolha`) |

Licença **não-Studio**: scripting externo não funciona. Tudo que toca o Resolve
roda de dentro dele.

## Fluxo de trabalho

```powershell
# 1. gerar+instalar+validar o macro (só quando mudar controle)
python ..\src\gerar_macro.py --estilo capcut_bolha --instalar

# 2. gerar as legendas
..\.venv\Scripts\python.exe ..\src\giautosubs.py "..\projects\<proj>\cortes\<corte>" --transcript <corte>.giautosubs.json

# 3. testar fora do Resolve
fuscript.exe -l lua testes.lua [<legendas.lua>]
```

Depois: **Workspace → Scripts → GiAutoSubs** dentro do Resolve. Ele pergunta
três coisas por rodada (legenda padrão / preset / arquivo de texto) e, se houver
legenda antiga na timeline, o `CONFLITO` (REPLACE / KEEP / NEW TRACK / **USE
THESE** = restilizar o que já está lá).

## Regras que não são opcionais

- **O LOOK é o estilo, não o Title.** Desde o macro 30 há um macro só; o que era
  `3color` / `3color_spinning` / `TikTokNovo` vive no `estilos.json` como
  `3_color` / `3_color_spinning` / `TikTokNovo` (os dois primeiros se chamavam
  `caixa_tres_cores*` até 27/09; `ESTILOS_RENOMEADOS` traduz o nome antigo, que
  está gravado nos arquivos e nos clipes, e avisa ao traduzir). A rodada
  pergunta qual estilo (menu em `giautosubs\menu_estilos\`, mantido pelo
  `giautosubs.py`) e REGENERA o `legendas.lua` quando você troca.
- **`camada3.giro` liga o spin** (graus por frame). Todo estilo declara
  `BoxSpinSpeed`, inclusive com 0: sem isso um clipe que já girava continua, e a
  expressão vai pra sombra da caixa. E o script NÃO escreve `Offset7`/`Offset8`
  quando há giro — número em cima de expressão mata a expressão.
- **A aba Meta não é estilo.** Ela diz de onde o clipe veio (qual
  `legendas.lua`, qual corte, quantos caracteres por caixa) e fica **fora do
  `InputKeys`**: no preset, o "Apply Style to All Captions" carimbaria a
  procedência de um clipe em cima de todos. Quem a escreve é o `escrever_meta`.
- **Mudar `Characters per Box` é REFAZER as legendas, não restilizar** — o número
  reparte as frases, então muda quantas legendas existem. Quem faz é o chunk
  `GiRebuild` (botão Rebuild Captions, e o Apply Style to This Track quando o
  número mudou); ele grava um `.lua` de nome novo (`legendas_c25.lua`) e só
  destrói clipe depois que o arquivo novo existe.
- **Botão de macro NÃO mexe na timeline.** Ele roda dentro da comp do clipe
  clicado; apagar clipes de lá (o REPLACE apaga esse clipe também) derruba o
  Resolve sem mensagem. O `Rebuild with Selected` PREPARA — gera o `.lua`,
  relinka e escreve o `_gipedido.txt`; a rodada é em Workspace > Scripts >
  GiAutoSubs, e ela não pergunta nada. Idem `io.popen`: use `os.execute` com
  redirecionamento.
- **O rebuild é checkbox + submit.** As opções (`Fixed Width`, `No Gaps`) são
  controles que ficam visíveis, e o `Rebuild with Selected` roda uma vez com o
  que está marcado. `Fixed Width` é o MESMO `TextBoxFixed` do grupo Text Box,
  exposto duas vezes — nunca um segundo checkbox.
- **O REPLACE volta na track DOMINANTE** (a que tinha mais legendas), não na
  menor ocupada: um clipe perdido numa track de baixo mudava a track de todas as
  outras. Com uma track por falante a base é a menor, porque as faixas sobem a
  partir dela.
- **`endFrame` é INCLUSIVO.** `recordFrame = f0` + `endFrame = f1 - f0` ocupa
  f0..f1, então a legenda dura um frame mais do que a transcrição diz. Com
  buraco entre as legendas isso nunca esbarrou em nada; com "sem buracos" todo
  par vizinho se sobrepõe em um frame, e dois clipes num frame da mesma track
  DERRUBAM o Resolve. O clamp por track, na criação, é o que impede.
- **"Sem buracos" é por TRACK.** Esticar pela lista toda sobrepõe duas legendas
  da mesma track (impossível num vídeo) e termina a legenda de um falante onde a
  de outro começa. Nunca encolhe, e a última de cada track fica como está.
- **Legenda por legenda, nunca um clipe só.** O Text+ faz o layout de todo o
  texto que está nele de uma vez, e o array por caractere é quadrático nas
  palavras. "Um clipe com as legendas trocando dentro" se faz com `Rebuild with
  Fixed Width`: a caixa para de mudar de tamanho e a órbita do spin (que já lê o
  tempo da TIMELINE) atravessa as legendas.
- **Diálogo dentro do macro é `fusion:RequestFile`, nunca `AskUser`.** O AskUser
  vem nil fora da página Fusion E não tem como ser posicionado na tela (saiu no
  macro 31). O RequestFile é a caixa nativa: centralizada e lembra a pasta.
- **Diga sempre se a feature custa PLAYBACK.** É por esse número que o usuário
  decide (ver `MACRO.md` §5, passo 0): o que custa é entrar no array de estilo por
  caractere, que é quadrático nas palavras. Custo por clique ou por arrasto é o
  barato — diga o número, mas diga que é o barato.
- **Com `Fixed Box` ligado, o Extend vale ZERO em todos os ramos** — inclusive
  quando a legenda é mais larga que o alvo ou quando `Height` é 0. "Desabilitado"
  é de função, não de aparência.
- **Três controles reagem sozinhos, e são uma lista fechada:** `Fixed Box`,
  `Width`, `Height` (o preview da caixa fixa, macro 32). O validador exige
  exatamente esses três, que o corpo passe por `ApplyGiStyle` e que passe
  `("preview", false, true)` — sem isso o preview reconstruiria o array por
  caractere a cada valor de slider, que é o que matou os callbacks no macro 11.
- **Não existe controle condicional no Inspector de um macro.** Não dá para cinzar
  o `Extend` quando o `Fixed Box` está ligado — dependia dos callbacks que saíram
  no macro 11. O rótulo e o log é que carregam a regra.
- **A caixa fixa usa a largura MEDIDA do texto** (`GiTextEm`, medido com Pillow na
  fonte instalada, em em). É o que faz toda caixa sair do mesmo tamanho. Sem o
  carimbo, o macro cai no palpite `caracteres × Char Width` e avisa — e aí as
  larguras divergem. A fonte é procurada TAMBÉM em
  `%LOCALAPPDATA%\Microsoft\Windows\Fonts` (é onde a Open Sans deste projeto está).
- **Legenda mais larga que o `Width` não encolhe.** O resumo da rodada imprime a
  maior legenda medida: é o mínimo que o `Width` pode pedir para todas saírem
  iguais.
- **`Width (px)`/`Height (px)` vs `Px per Unit`:** uma unidade de `Extend` é a
  altura da fonte (`Size` × altura do frame). Esse fator é ESTIMADO e corrigível
  no Inspector (`Meta > Px per Unit`, 0 = estimar) porque ninguém consegue medi-lo
  fora do Resolve. `Width = 0` volta ao alvo por `Characters per Box`.
- **`Fixed Box` não é um input do Text+.** Não existe largura fixa lá: o macro
  COMPENSA no `Extend Horizontal` o que falta pra chegar à largura de uma linha
  cheia (`Characters per Box` × `Char Width`). Legenda mais larga que o alvo não
  encolhe de propósito.
- **Nenhum controle reage sozinho.** Os callbacks por controle saíram no macro
  11. Ajuste o que quiser no Inspector e clique **Apply Style**.
- **`Enabled{n}` primeiro.** Os inputs de um elemento do Text+ só existem depois
  dele; escrever `Red6` antes de `Enabled6` é aceito e descartado em silêncio.
- **`ElementShape{n}` decide se é texto ou borda.** `2` = Border Fill (caixa
  cheia). `Level`/`ExtendH`/`ExtendV`/`Round` **só valem em forma de borda**.
- **Escreva no Text+ E no Follower1** para tudo em `CHAVES_DO_FOLLOWER`
  (`Enabled`, `Red`, `Green`, `Blue`, `Thickness`, `Softness`) — o Follower
  vence o Text+ na tela. `Opacity{n}` fica **de fora**: vem conectada ao fade.
- **Nunca escreva número num input com `SourceOp`** (mata a conexão, sem erro).
- **O array de estilo por caractere vence tudo.** Se o Inspector diz uma coisa e
  a tela mostra outra, o suspeito é o spline (`GiRebuildHighlight`).
- **Cor por falante NÃO existe mais** (saiu no macro 22): quem manda no fill é o
  `Fill Color` do Inspector. `falantes[].cor`/`aplicar_em` do `estilos.json` são
  ignorados — falante decide **track**, só isso.
- **Convenção:** comentário em **português**; UI e log em **inglês**, com o
  vocabulário do AutoSubs (`Enabled`, `Fill Color`, `Extend Horizontal`,
  `Round`) em vez de sinônimos novos.
- **Depois de instalar macro novo: reiniciar o Resolve** (o Fusion varre
  `Templates/Edit/Titles` só no boot) **e recriar os clipes** (cada clipe carrega
  a própria cópia do macro; ver `MACRO.md` §2.4 e o carimbo `GiAutoSubsVersao`).
- **O `fuscript` sai 0 mesmo com erro.** Quem decide é o texto `MACRO OK` na
  saída — foi assim que um macro que não compila chegou a ser instalado.

## Mapa dos 8 elementos do Text+

```
1 fill  ·  2 outline  ·  3 sombra do texto
4 bolha do destaque   ·  5 sombra da bolha
6 caixa do texto todo ·  7 sombra dessa caixa / 2ª cor
8 terceira cor da caixa
```

A **caixa de tres cores** faz parte do macro desde o **30**: há um Title só
(`GiAutoSubs Caption`) e ele traz o grupo `Box Layer 3`, a rotina `camada3` e o
`LIGA[8]` sempre. Um estilo sem `base.camada3` escreve `BoxLayer3Enabled = 0` e
o elemento 8 fica apagado — **custo zero por frame** pra quem não usa (o
elemento 8 está fora do fade, e o custo medido do projeto é o array por
caractere). Não há mais Title certo ou errado a escolher.

O efeito e' a mesma caixa desenhada tres vezes,
**deslocada** — nao tres bordas concentricas. Por isso o elemento 7 vira a
segunda cor sem perder nada (ele ja' e' Border Fill com cor e Offset proprios) e
so' a terceira precisou de slot. Geometria copiada da caixa base nos tres,
offsets em lados opostos, transparencia por `Alpha8` e nunca `Opacity8`. Ver
`MACRO.md` §3.4 e `tests\camada3.py`.

O aviso **`WRONG TITLE`** existiu entre 05/09 e 27/09 e **saiu no macro 30**:
ele cobria o buraco de o carimbo `GiAutoSubsVersao` ser um número só para quatro
variantes, o que tornava silenciosa a escolha do Title errado. Com um Title só
não há escolha errada a fazer, e o `testes.lua` agora exige o contrário — que um
preset pedindo `BoxLayer3Enabled` **chegue** ao clipe, sem queixa nenhuma.

### O spin (`Spin Speed`)

Gira o **deslocamento**, não a geometria: as três caixas ficam alinhadas e o
vetor de offset percorre um círculo, então a borda colorida **orbita** o texto.
Rotacionar o retângulo deixaria a caixa base reta e as coloridas em losango — lê
como defeito, não como estilo.

Um controle só, **`Spin Speed`** (graus por frame): raio e fase saem do offset
que já está no Inspector, porque `(x,y)` é um vetor e traz os dois dentro. O
default é **0**, e em 0 `deslocar()` cai em `pin()`: nenhuma expressão é escrita
e a caixa fica parada, exatamente como antes de o spin existir. (Enquanto o spin
era um Title próprio o default era 2 — escolher aquele Title já era pedir o giro.
No macro único isso poria toda legenda pra girar sem ninguém pedir.) Os 180° entre a 2ª e a 3ª cor vêm
de graça — os offsets já nascem em lados opostos, então meia volta *é* as duas
cores trocando de lado.

Escrito como **expressão** em `Offset7`/`Offset8`, nos dois tools (o Follower1
vence o Text+). `SetExpression(nil)` **antes** de qualquer escrita numérica — sem
isso, desligar o spin não devolve a caixa ao lugar. O elemento 5 (sombra da
bolha) **não** gira: ele acompanha a palavra falada e viraria ruído.

Os marcadores do spin moram **dentro** do bloco `__CAMADA3_DEF__`, então em
`_apply_gi()` os recortes do spin rodam **antes** dos da camada 3 — tirar a
camada 3 primeiro leva os marcadores junto e o `_recortar` levanta na geração do
próprio Caption. Marcador aninhado se resolve de dentro pra fora.

`Level` é **0-based**: `0 Text · 1 Line · 2 Word · 3 Character` (estava
invertido até o macro 22).

## Performance

O array de estilo por caractere é **quadrático nas palavras**. Alavancas, em
ordem de ganho: `quebra.max_linhas = 1` + `max_chars` curto (mais legendas, cada
uma com menos palavras) e `destaque.fill.ativo = false` (a camada mais cara).
Do corte inteiro: 47.328 → 9.216 entradas.

**Como o usuário define esse tipo de limite:** ele dá uma **frase de exemplo**,
não um número. Conte os caracteres dela e confirme o número na resposta.

## Em aberto

- **O mais grave:** as legendas não sabem do ripple do SpeakerSwitch. O
  `giautosubs.py` converte tempo absoluto com uma **subtração constante**, mas
  desde 02/09 o SpeakerSwitch remove trechos (`cut` e silêncio) e puxa tudo pra
  trás. Erro mediano medido: 14,7 s. Conserto identificado: o SpeakerSwitch
  gravar o mapa (`a`, `b`, `rec`) por span na pasta do corte, e o
  `giautosubs.py` consultar em vez de subtrair.
- `testes.lua` falha em `Offset3 from the config was overwritten` contra um
  `legendas.lua` real (passa contra a amostra). Já descartado o
  `fundir_preset`; está no passo 6 do `estilizar` ou na captura de `offsets`.
- Piso de duração da legenda: 7 legendas com duração **zero** (palavras que o
  Whisper carimba com `start == end`). Aguardando o usuário dar uma legenda de
  exemplo no limite do aceitável.
- `refazer_tempos` interpola posicionalmente: apagar palavra estica o resto.
  Conserto = guardar a palavra no `GiWordTiming` e casar por LCS (custa recriar
  os clipes).
- Os três diálogos (`fusion:RequestFile`) nunca rodaram dentro do Resolve; a
  exportação do `.drb` também não.
- Separar o GiAutoSubs do `pre_production` (pedido antigo).
