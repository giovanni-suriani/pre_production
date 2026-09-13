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
| `MACRO.md` | como um `.setting` funciona por dentro; §2 = a cadeia de precedência (por que um valor escrito "certo" não aparece na tela); §5 = receita de 6 passos pra criar um atributo novo; §7 = tabela sintoma→causa |
| `ESTADO.md` | o histórico das versões do macro e as caçadas já feitas |

Ver também a memória `project-giautosubs` e `feedback-resolve-scripting-gotchas`.

## As peças

| arquivo | papel |
|---|---|
| `vendor/autosubs-macro.setting` | macro original do AutoSubs, **intocado** |
| `../src/gerar_macro.py` | patcheia o vendor → `GiAutoSubs Caption.setting`; `--instalar` copia pra `%APPDATA%\...\Fusion\Templates\Edit\Titles` |
| `GiAutoSubs Caption.setting` | o resultado — **nunca editar na mão** |
| `GiAutoSubs TikTokNovo.setting` | Title alternativo, importado de um estilo exportado pelo usuário |
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
6 caixa do texto todo ·  7 sombra dessa caixa
8 LIVRE
```

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
