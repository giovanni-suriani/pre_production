# O macro do GiAutoSubs por dentro

Como um `.setting` de título Fusion funciona, por que um valor escrito
"corretamente" não aparece na tela, e o que é preciso tocar para criar um
controle novo que realmente funcione.

Escrito depois de perder três rodadas no Resolve com o mesmo sintoma: *o log
diz que aplicou, a tela mostra outra coisa*. Quase tudo aqui é sobre isso.

---

## 1. As cinco camadas de um `.setting`

Um título Fusion é uma tabela Lua com um `MacroOperator` dentro. Ele tem cinco
partes independentes, e **é normal mexer numa e o resultado não mudar** — porque
quem manda naquilo é outra.

```
AutoSubs = MacroOperator {
    CustomData = { ... }          <- (5) rotinas Lua guardadas como string
    Tools = ordered() {           <- (1) o grafo que de fato renderiza
        Template   = TextPlus { Inputs = {...}, UserControls = {...} }   <- (2)
        Follower1  = StyledTextFollower { Inputs = {...} }
        CharacterLevelStyling1 = StyledTextCLS { ... }
        ...
    },
    UserControls = ordered() { ... ControlPage ... }   <- (4) as ABAS
    Inputs = ordered() { ... InstanceInput ... }       <- (3) o Inspector
    Outputs = { ... }
}
```

| # | Camada | O que é | Onde vive |
|---|---|---|---|
| 1 | **Tools** | o grafo real. É o único lugar que desenha pixel. | `Tools = ordered()` |
| 2 | **UserControls** | a *definição* de um controle: rótulo, tipo, faixa, default, callback. | dentro de `Template` |
| 3 | **InstanceInput** | *publica* um UserControl no Inspector do clipe. Sem isso o controle existe e é invisível. | `Inputs = ordered()` do macro |
| 4 | **ControlPage** | as abas do Inspector (`Text`, `Style`, `Controls`, `Settings`). | `UserControls` do **macro** |
| 5 | **CustomData** | funções Lua guardadas como texto, executadas via `loadstring(tool:GetData("Nome"))()`. | `CustomData` do macro |

Consequências práticas, todas já pagas em tempo:

- Criar um UserControl e não criar o InstanceInput → o controle **não aparece**.
- Mover todo mundo de `Page = "Style"` para `Page = "Text"` **não apaga a aba
  Style**: a aba é a camada 4, e continua ali, vazia. Some com
  `Style = ControlPage { CT_Visible = false }`.
- Um `INPS_ExecuteOnChange` errado só quebra na hora do clique — o Fusion
  compila aquela string tarde. É por isso que o `valida_macro.lua` compila as
  83 rotinas embutidas uma a uma.

---

## 2. Quem ganha: a cadeia de precedência

**Esta seção é o motivo do documento.** O outline ficou azul por três rodadas
porque o valor certo estava escrito no lugar certo — e outra coisa escrevia
por cima depois.

Para um mesmo atributo (digamos, a cor do outline = elemento 2), existem
**cinco** origens possíveis. Da mais fraca para a mais forte:

```
1. INP_Default do UserControl          "Template.UserControls.OutlineColorRed.INP_Default"
2. Default do InstanceInput            "Inputs.OutlineColorRed.Default"        <- vence o 1
3. Inputs do Text+                     "Template.Inputs.Red2"                  <- o que o tool tem
4. Inputs do Follower1                 "Follower1.Inputs.Red2"                 <- VENCE o 3 na tela
5. Array de keyframe do StyledText     spline -> CharacterLevelStyling         <- vence tudo, por caractere
```

E, atravessando tudo isso, as **rotinas do CustomData**, que reescrevem 3 e 4 a
partir de 1/2 sempre que alguém as chama.

### 2.1 O Follower1 sobrescreve o Text+

`Follower1` é um `StyledTextFollower`: um **modificador** conectado em
`Template.StyledText`. Ele não decora nada — ele *gera* o StyledText que o Text+
consome, e os inputs de elemento que **ele** tem viram overrides por caractere.

O macro do AutoSubs vem com isto dentro do Follower1:

```lua
Thickness2 = Input { Value = 0.8, },
Red2       = Input { Value = 0.9294117647059, },
Green2     = Input { Value = 0.0509803921569, },
Softness1..8 = Input { Value = 1, },
```

Ou seja: **pintar `Template.Red2` de preto não muda um pixel**, porque o
Follower reescreve. É exatamente por isso que o `UpdateAllStyleColors` deles faz

```lua
template:SetInput(key .. id, value)
follower:SetInput(key .. id, value)   -- <- a linha que faltava no GiAutoSubs
```

**Regra:** todo atributo de elemento que o Follower1 declara precisa ser escrito
nos dois tools. Hoje isso está em `CHAVES_DO_FOLLOWER`
(`giautosubs.py` e `GiAutoSubs.lua`): `Enabled`, `Red`, `Green`, `Blue`,
`Thickness`, `Softness`.

> **`Opacity{n}` fica de fora de propósito.** No Follower1 as opacidades 1..4
> estão **conectadas** ao `AnimationKeyframeStretcher`. Escrever um número por
> cima troca a conexão por um valor fixo e mata o fade — sem erro nenhum.
> Regra geral: nunca escreva valor num input que tem `SourceOp`.

### 2.2 Os keyframes de exemplo do spline — a camada 5

Esta é a **mais forte de todas** e foi a última a ser encontrada. O macro do
AutoSubs vem com keyframes de demonstração no spline de character-level styling
(`CharacterLevelStyling1RightclickHereto...`):

```lua
{ 2401, 8, 15, Index = 1 },              -- Red   = 0
{ 2402, 8, 15, Index = 1, Value = 0.35 } -- Green = 0.35
{ 2403, 8, 15, Index = 1, Value = 1 },   -- Blue  = 1
```

`Index = 1` é o elemento 2, o outline; `rgb(0, 0.35, 1)` é azul. Estilo por
caractere vence tanto o Text+ quanto o Follower1 — então **não importava o que
se escrevesse nos dois, nem que cor se escolhesse no Inspector**.

No AutoSubs quem limpava isso era o `RemoveHighlight`. Como ele foi desarmado
(ele também apagava os *nossos* keyframes), a limpeza passou para dois lugares:

- `gerar_macro.py` apaga os keyframes de exemplo do arquivo;
- `GiAutoSubs.lua` reescreve o spline em **toda** legenda — com as palavras, ou
  com um array vazio. Um clipe criado a partir de um macro velho também fica
  correto.

### 2.3 As rotinas que reescrevem sozinhas

No macro original, mexer no input `Text` disparava:

```
Text (INPS_ExecuteOnChange)
  -> UpdateTextContent          -- reestima o tempo de cada palavra pelo TEXTO
  -> ApplyWordTiming
  -> UpdateHighlight -> ApplyHighlight
       -> UpdateAllStyleColors  -- repinta Red2/Green2/Blue2 com OutlineColor*
       -> get_current_style     -- FORÇA Enabled4 = 0 (mata a bolha)
       -> spline:SetKeyFrames   -- apaga os keyframes por palavra
```

E os defaults do AutoSubs são `OutlineColorRed = 0, Green = 0.35, Blue = 1.0`
— **isso é azul**. O script escrevia preto e o macro repintava de azul meio
segundo depois, sozinho.

O `gerar_macro.py` desarma seis rotinas (`UpdateTextContent`, `ApplyWordTiming`,
`ApplyHighlight`, `RemoveHighlight`, `ToggleHighlight`, `UpdateHighlight`): o
tempo por palavra aqui vem do Whisper, medido — o cronômetro deles só tinha como
discordar.

### 2.4 A cópia no Media Pool

Quando um título Fusion entra no Media Pool, o Resolve **guarda uma cópia dele
dentro do projeto**. Reinstalar o `.setting` em `Templates/Edit/Titles` não mexe
nessa cópia: o script continua criando clipes a partir do macro velho, e o
sintoma é *"consertei e não mudou nada"*.

Por isso existe o `GiAutoSubsVersao`, um controle invisível gravado pelo
`gerar_macro.py` e conferido pelo `GiAutoSubs.lua` antes de estilizar.

**Não existe API para pôr um Fusion Title no Media Pool.**
`timeline:InsertFusionTitleIntoTimeline` põe o título na **timeline**, e título
na timeline não vira item de Media Pool — igual a arrastar com o mouse para a
timeline, que também não cria nada lá. No Resolve 21 o item devolvido não expõe
`GetMediaPoolItem`.

O que existe é `mediaPool:ImportFolderFromFile`, que importa um bin `.drb`. É
assim que o AutoSubs resolve, distribuindo um `caption-bin.drb`.

E existe o caminho de volta: **`mediaPool:ExportFolder`**. Então o `.drb` não
precisa mais ser exportado à mão. Na primeira rodada em que o template estiver
no Media Pool **e o carimbo bater**, o script exporta o bin sozinho — e o
próximo projeto importa sem ninguém arrastar nada. O passo manual passa a ser
uma vez na vida em vez de uma vez por projeto.

Três cuidados, todos no `GiAutoSubs.lua`:

- **Depois da conferência de carimbo, nunca antes.** Exportar um template
  defasado congelaria um macro velho num arquivo que os projetos seguintes
  importariam de olhos fechados.
- **Numa pasta só dele.** `ExportFolder` exporta uma *pasta*; exportar a pasta
  onde o template estava levaria junto o que houvesse lá — e na raiz isso é o
  Media Pool inteiro. O template é **copiado** (`CopyClips`, não `MoveClips`)
  para um bin temporário, que é apagado depois. O Media Pool do usuário sai como
  entrou.
- **O bin envelhece.** Ele é uma cópia congelada do macro, igualzinha à do
  projeto. Por isso o carimbo mora ao lado, num `.drb.versao`: um bin mais velho
  que a rodada **não é importado** — importá-lo seria reimportar exatamente o
  problema que o carimbo existe para detectar.

Mais a trava do AutoSubs: **uma tentativa de importação por projeto** (chaveada
por projeto + versão do bin, em `_bin_importado.txt`). Sem ela, uma importação
que falha é repetida a cada rodada, e cada tentativa pode deixar mais um bin no
projeto — metade da confusão das cópias nasce daí. Bin novo destrava sozinho,
que é o único caso em que tentar de novo faz sentido.

Sem o `.drb` — primeira vez de todas — o passo manual continua: arrastar
`GiAutoSubs Caption` de `Effects > Titles` **para o Media Pool** (não para a
timeline). Da segunda vez em diante não existe mais.

**Ordem ao trocar um template defasado:** semear o novo → conferir que veio →
só então apagar os velhos. A versão anterior apagava primeiro, e como semear
falha nesta build, o usuário ficava sem template nenhum — e o run seguinte
parava com "no template available". Apagar antes de ter o substituto na mão é o
tipo de erro que só aparece no dia em que o outro passo falha.

E apaga **todas** as cópias obsoletas, não só a que `achar_template` devolveu:
duas trocas seguidas deixavam duas defasadas no pool, e a busca seguinte podia
acertar qualquer uma delas.

`AUTO_ATUALIZAR_TEMPLATE = false` desliga a troca automática;
`AUTO_EXPORTAR_BIN = false` desliga a exportação.

### O item do Media Pool é só o molde

Cada clipe da timeline carrega a **própria comp**. O item do Media Pool serve
para instanciar clipes novos e mais nada:

- editar uma legenda na timeline afeta só ela;
- editar o item do Media Pool afeta só legendas criadas **depois**;
- editar o `.setting` no disco afeta só o que entrar no Media Pool depois.

É daí que vem o problema do macro defasado — o macro está *dentro* do clipe, e é
de lá que `conferir_macro` lê o carimbo.

Consequência: apagar o item do Media Pool **não** deveria derrubar legendas já
na timeline. Um título arrastado direto de `Effects > Titles` para a timeline
funciona sem existir item nenhum no pool, o que reforça isso. *Não verificado na
marra* — se algum dia aparecer clipe offline depois de uma troca automática, o
interruptor acima é a saída.

Sobra um caso que o script não resolve: o Fusion varre `Templates/Edit/Titles`
**quando o Resolve inicia**. Se você instalou um `.setting` novo com o Resolve
aberto, `Effects > Titles` ainda serve o antigo, e nem a troca automática
adianta. O script detecta isso (a segunda passada continua defasada) e pede o
reinício — que aí é o único passo manual, e só depois de instalar um macro novo.

### Por que Media Pool, e não inserir o título direto

`mediaPool:AppendToTimeline(clipes)` é a única chamada que cria as N legendas de
uma vez, cada uma com track, frame de entrada e duração exatos — e ela recebe
`MediaPoolItem`. `InsertFusionTitleIntoTimeline` insere **um** título no
playhead, sem aceitar track nem frame: 129 legendas seriam 129 operações de UI
mais mover e aparar cada uma. Ele é usado só para semear o item, uma vez.

---

## 3. Os atributos do Text+ (elementos de sombreamento)

O Text+ tem **8 elementos de sombreamento**. O 1 desenha na frente, o 8 no
fundo. Cada um tem inputs com sufixo numérico: `Red1`, `Enabled4`, `Round6`...

### 3.1 A regra que mais custou tempo

> **Os inputs de um elemento só existem depois de `Enabled{n} = 1`.**

Dump real: com o elemento 1 ligado ele tem 61 inputs; os elementos 6/7/8
desligados têm dois (`Enabled` e `Name`). Escrever `Red6` antes de `Enabled6`
é **aceito e descartado, em silêncio**. Sempre `Enabled{n}` primeiro.

### 3.2 `ElementShape{n}` — o input que faltava

`ElementShape` é o "Appearance" do Inspector. Quatro formas, contando de **zero**:

| Valor | Appearance |
|---|---|
| 0 | Text Fill |
| 1 | Text Outline |
| **2** | **Border Fill** — é este que faz uma caixa |
| 3 | Border Outline |

Isso não é dedução: saiu do `PROPERTY DUMP` dentro do Resolve, lendo de volta os
presets de fábrica — elemento 1 ("White Solid Fill") dá `0`, elemento 2 ("Red
Outline") dá `1`, elemento 4 ("Blue Border") dá `3`.

> Cuidado: o elemento 4 nasce em **3 = Border Outline**, só o contorno do
> retângulo. Uma bolha é um retângulo **preenchido** → `2`. Uma versão anterior
> deste projeto "calibrava" lendo o elemento 4 e herdava o contorno.

**`Level`, `ExtendHorizontal`, `ExtendVertical` e `Round` só valem para as
formas de BORDA.** Num elemento de texto o Text+ aceita todos eles e não desenha
caixa nenhuma. Era esse o "box shadow não funciona".

Os elementos 1–4 nascem dos presets de fábrica da biblioteca de sombreamento:

| Elemento | Preset | Forma |
|---|---|---|
| 1 | White Solid Fill | texto |
| 2 | Red Outline | texto (outline) |
| 3 | Black Shadow | texto, com offset |
| 4 | **Blue Border** | **borda** |
| 5–8 | vazios | **texto** |

É por isso que a bolha do AutoSubs (elemento 4) funciona sem ninguém tocar em
`ElementShape` — e por isso que os elementos 5, 6 e 7 precisam ser trocados
explicitamente.

Quando um número desses estiver em dúvida, o `PROPERTY DUMP` do
`GiAutoSubs.lua` (`DEBUG_PROPRIEDADES = true`) imprime o valor de todos os 8
elementos lado a lado, no Text+ **e** no Follower1 — e é assim que o mapeamento
acima foi descoberto, em vez de por tentativa.

### 3.3 Tabela de inputs

Nomes de tool (`Xxx{n}`) e o atributo interno correspondente do StyledText:

| Input | Atributo interno | Vale para | Observação |
|---|---|---|---|
| `Enabled{n}` | `ElementEnabled` | tudo | **primeiro de todos** |
| `Name{n}` | — | tudo | só o rótulo no Inspector |
| `ElementShape{n}` | `ElementShape` | tudo | texto vs borda (ver 3.2) |
| `Level{n}` | `BorderLevel` | **borda** | 1 caractere, 2 palavra, 3 linha |
| `ExtendHorizontal{n}` | `BorderExtendLeft` | **borda** | fração da tela |
| `ExtendVertical{n}` | `BorderExtendTop` | **borda** | |
| `Round{n}` | `BorderRound` | **borda** | 0..1 |
| `Red/Green/Blue/Alpha{n}` | `ElementColorR/G/B/A` | tudo | 0..1, não 0..255 |
| `Opacity{n}` | `ElementOpacity` | tudo | cuidado com conexões |
| `Softness{n}` | `ElementSoftnessX/Y` | tudo | borrão |
| `Thickness{n}` | `OutlineThickness` | outline | |
| `Offset{n}` | `ElementOffsetX/Y` | tudo | **deslocamento relativo** |
| `Position{n}` | — | tudo | **posição ABSOLUTA** |

> **`Offset` ≠ `Position`.** Os dois existem. `Position` é coordenada absoluta:
> usá-lo com `(0,0)` joga o elemento para o canto da tela. Para sombra, sempre
> `Offset`. Ambos recebem um **ponto** (`{x, y}`), não dois números.

Fonte: a tabela de atributos do `fusionsystem.dll` e a lista de controles do
`Plugins\text.plugin` do Resolve. O mapeamento input→atributo é inferido dos
nomes e confere com o comportamento observado.

### 3.4 Mapa de elementos deste projeto

```
1 fill  ·  2 outline  ·  3 sombra do texto
4 bolha do destaque   ·  5 sombra da bolha
6 caixa do texto todo ·  7 sombra dessa caixa
8 livre
```

---

## 4. O destaque palavra a palavra

A cadeia:

```
BezierSpline -> CharacterLevelStyling1 -> Follower1 -> Template.StyledText
```

Cada keyframe do spline carrega um objeto `StyledText` cujo `Array` descreve o
estado de **todas** as palavras naquele instante. Trocar de palavra é trocar de
keyframe.

```lua
{ codigo, startIndex, endIndex, Value = v, __flags = 256, Index = elemento - 1 }
```

- `codigo`: `Enabled = 2000`, `Red = 2401`, `Green = 2402`, `Blue = 2403`.
  (`Opacity = 2600` existe, e o AutoSubs evita de propósito: briga com o fade.)
- `startIndex`/`endIndex`: posição em **caracteres** (0-based, UTF-8 contado por
  codepoint), dentro do texto da legenda inteira.
- `Index`: o elemento, **0-based** — o elemento 4 do Text+ é `Index = 3`.

Duas armadilhas:

1. **O elemento tem que estar habilitado no Text+** para o styling por caractere
   valer. O comentário do próprio AutoSubs: *"Bubble must be enabled at the
   template level or will not work with character-level styling"*. Quem apaga a
   bolha nas palavras não faladas é o array, não o `Enabled4`.
2. **O texto vai em `Text`, não em `StyledText`.** No macro animado o
   `StyledText` do Text+ está *conectado* ao Follower1; escrever nele arrebenta a
   cadeia. E o `CharacterLevelStyling1.Text` precisa ser sincronizado junto.

---

## 4b. O contrato: `InputKeys` + `GetInputValues` / `SetInputValues`

O macro do AutoSubs já trazia esse par, e o GiAutoSubs voltou a usá-lo. É o que
faz o estilo ser uma **tabela opaca**: quem a carrega — o `legendas.lua`, ou um
clipe lido de volta — não precisa saber o que tem dentro.

```
InputKeys        (CustomData, tabela)   a LISTA de controles = o schema
GetInputValues   (CustomData, chunk)    tool -> tabela com essas chaves
SetInputValues   (CustomData, chunk)    tabela -> tool, e refaz o que deriva
```

**O schema pertence ao macro.** É por isso que acrescentar um controle deixou de
exigir código novo em três arquivos: ele entra na lista e passa a viajar junto.

`SetInputValues` é o **único caminho de escrita**, e a partir da versão 11 são
só **duas** as portas: o botão **Apply Style** e o `GiAutoSubs.lua`.

```
botão Apply Style ─┐
legendas.lua    ───┴─→ SetInputValues ─┬─→ SetAnimations        (só pelo botão)
                                       └─→ UpdateAllStyleColors  (elementos 1..3)
                                              └─→ ApplyGiStyle   (elementos 4..7)
                                                     └─→ GiRebuildHighlight (o spline)
```

> **Nenhum controle reage sozinho.** Os 43 callbacks por controle saíram na
> versão 11 — inclusive os que vinham do macro do AutoSubs. Dois motivos, os dois
> medidos: `INPS_ExecuteOnChange` dispara a cada valor intermediário de um
> arrasto de slider (~40 por ajuste), e o `tool` que ele recebe é o Text+, onde o
> código não mora (§6) — metade dos disparos só sabia imprimir "nothing was
> applied". Ajuste o que quiser no Inspector e clique **Apply Style**: um clique,
> um bloco de log.
>
> **Botão executa `BTNCS_Execute`, não `INPS_ExecuteOnChange`.** Um
> `ButtonControl` declarado com o atributo dos outros controles aparece no
> Inspector, aceita o clique e não faz nada — e o Fusion não reclama. O
> validador recusa isso, e recusa também qualquer `INPS_ExecuteOnChange`
> sobrevivente.

Três coisas que a assinatura carrega, e o porquê de cada uma:

| argumento | para quê |
|---|---|
| `settings` | a tabela opaca. `nil` = "não mudou valor, só refaça o que deriva" — é o caso do botão, já que cada controle gravou o próprio valor ao ser mexido |
| `origem` | `"button"` ou `"script"`. Decide se o `SetAnimations` roda, e é o que aparece no log |
| `spline` | a palavra final: `false` = "não refaça, eu reescrevo o array em seguida". É o que o script passa nas 128 legendas |

> **Achar os chunks: varra a comp, tool a tool.** Eles moram no `CustomData` do
> MacroOperator (§6). `tool:GetData` no Text+ volta nil, e `comp:GetData` também
> — a comp não é dona de nada disso. Quem responde é **algum tool** da
> `comp:GetToolList(false)`. É o que o `gi_chunk` (dentro do macro) e o
> `dado_do_macro` (no `GiAutoSubs.lua`) fazem. Antes disso o botão dizia "nothing
> was applied" e o resumo do run dizia `one by one (the chunks are not reachable
> from a script)` — os dois pela mesma causa. O `GiAutoSubs.lua` ainda cai pro
> caminho longo (controle por controle) se ninguém responder; a linha
> `style applied via ...` no resumo diz qual dos dois aconteceu.

O que o par **não** faz: rearmar as seis rotinas desarmadas. O
`SetInputValues` do AutoSubs terminava chamando `SetAnimations` e
`UpdateHighlight` — e o `UpdateHighlight` é justamente uma das seis. Apontar
para as nossas foi o que impediu o contrato de compilar, rodar e não fazer nada.

---

## 5. Receita: criar um atributo novo que funciona

Seis lugares. Pular qualquer um deles produz um controle que existe e não faz
nada — que é pior que não ter controle.

### Passo 1 — UserControl (a definição)

Dentro de `Template.UserControls`, **no fim da lista**:

```lua
MeuControle = {
    LINKS_Name = "Rótulo visível",
    LINKID_DataType = "Number",
    INPID_InputControl = "SliderControl",   -- ou Checkbox/Combo/ColorControl
    INP_Default = 0.5,
    INP_MinScale = 0, INP_MaxScale = 1,
    INP_External = false,
    INP_Passive = false,
},
```

- **Sem `INPS_ExecuteOnChange`.** Quem aplica é o botão Apply Style; um callback
  aqui seria um segundo caminho, disparado ~40 vezes por arrasto de slider, e o
  validador recusa o macro.

- **`LINKS_Name` em inglês.** A convenção do projeto é comentário em português,
  UI e log em inglês — o Inspector é do Resolve, e o vocabulário dele já é o do
  AutoSubs (`Enabled`, `Fill Color`, `Extend Horizontal`, `Round`). Fique nesse
  vocabulário em vez de inventar sinônimos.
- **No fim, nunca no começo.** Um `LabelControl` engole os `LBLC_NumInputs`
  controles **seguintes**; inserir no topo faz um grupo adotar os controles do
  outro. (No `gerar_macro.py`, `_recontar_grupos` recalcula esses números
  sozinho depois de todas as mudanças — não os mantenha na mão.) É por isso que
  o botão `Apply Style` tem um `ApplyStyleLabel` só dele: solto, ele cairia
  dentro do grupo "Box Shadow".
- **Onde ele aparece na tela não se decide aqui.** A ordem do Inspector do clipe
  é a ordem dos `InstanceInput` no bloco `Inputs` do macro (passo 4). É por isso
  que o grupo "Actions" mora no fim dos UserControls e no **começo** dos
  InstanceInputs: `_abrir_instance_inputs` o insere lá, acima até dos controles
  do AutoSubs.
- **Vírgula.** Vários controles do AutoSubs terminam o último campo sem vírgula
  (`LINKS_Name = "Duration (seconds)"`). Inserir algo depois disso sem pôr a
  vírgula quebra o arquivo inteiro, e o Resolve só diz "o título não carrega".

### Passo 2 — Seletor de cor

Três sliders soltos não viram um seletor. O que junta R/G/B num widget com roda
de cor é `INPID_InputControl = "ColorControl"` + o **mesmo** `IC_ControlGroup`
nos três + `IC_ControlID` 0/1/2, e `CLRC_ShowWheel = true` só no primeiro:

```lua
MinhaCorRed   = { LINKS_Name = "Minha cor", INPID_InputControl = "ColorControl",
                  IC_ControlID = 0, IC_ControlGroup = 24, CLRC_ShowWheel = true,
                  ICS_ControlPage = "Controls", ... },
MinhaCorGreen = { ... IC_ControlID = 1, IC_ControlGroup = 24, ... },
MinhaCorBlue  = { ... IC_ControlID = 2, IC_ControlGroup = 24, ... },
```

Grupos em uso: AutoSubs 20–23 (UserControl) e 120–123 (InstanceInput);
GiAutoSubs 24–26 e 124–126. Colidir junta dois seletores num widget só.

### Passo 3 — InstanceInput (publicar no Inspector)

No `Inputs = ordered()` do macro, **na mesma ordem** dos UserControls:

```lua
MeuControle = InstanceInput {
    SourceOp = "Template",
    Source = "MeuControle",
    Name = "Rótulo",        -- opcional; só no primeiro canal de uma cor
    ControlGroup = 124,     -- só para cores
    Page = "Text",          -- SEMPRE explícito
},
```

O **nome** do InstanceInput não precisa ser o do UserControl (`TextLabel` aponta
para `SubtitleLabel`). Quem manda é o `Source`.

### Passo 4 — A rotina que escreve no Text+

Um controle só guarda um número. Quem empurra o valor para o grafo é uma rotina
do `CustomData`. Neste macro é o **`ApplyGiStyle`**, dona única dos elementos
4–7 — um caminho só, para que "o checkbox não surte efeito" deixe de ser
possível.

Dentro dela, três cuidados:

```lua
local template = comp:FindTool("Template") or tool

-- `tool` ora é o macro, ora é o Text+ de dentro, dependendo de quem disparou
local function ctl(nome, padrao)
    local v = tool:GetInput(nome)
    if v == nil and template ~= tool then v = template:GetInput(nome) end
    if v == nil then return padrao end
    return v
end

-- e a ordem: Enabled -> ElementShape -> geometria
template:SetInput("Enabled6", 1)
template:SetInput("ElementShape6", BORDA)
template:SetInput("Round6", ctl("TextBoxRound", 0.2))
```

E, se o atributo estiver em `CHAVES_DO_FOLLOWER`, escreva **também no
Follower1** (seção 2.1).

### Passo 5 — Entrar no `InputKeys`

Uma linha no `_INPUT_KEYS_BASE` (controle do AutoSubs) ou nada a fazer (controle
nosso: a lista sai do `NOVOS` sozinha, menos os `*Label`, o `ApplyStyle` e o
carimbo de versão).

Sem isso o controle funciona no Inspector e **some do preset**: o
`legendas.lua` não escreve nele e o `GetInputValues` não o lê. O sintoma é
"mexi, rodei o script, e voltou ao que era" — e o validador agora recusa o
macro antes de chegar lá.

### Passo 6 — Validar antes de abrir o Resolve

```
python gerar_macro.py --estilo <estilo> --instalar
```

Ele roda sozinho o `valida_macro.lua` no `fuscript` (o mesmo interpretador do
Resolve) e **se recusa a dizer que deu certo** se o arquivo não compilar. O
validador confere: a tabela fecha, as 83 rotinas embutidas compilam, cada
controle novo existe como UserControl **e** como InstanceInput, os grupos de cor
estão coerentes, nenhum botão sobrou, todo mundo está na aba `Text`, e os
defaults batem com o estilo pedido.

E `testes.lua` roda o `GiAutoSubs.lua` inteiro contra um **Resolve de mentira**
— incluindo a regra de materialização do passo 3.1 e as cores do Follower1.

```
fuscript.exe -l lua testes.lua [<legendas.lua>]
```

---

## 6. Onde mora o código, e por que o callback foi embora

Uma aplicação de estilo custa isto:

| trecho | escritas |
|---|---|
| bolha + sombra da bolha + caixa + sombra da caixa | ~40 `SetInput` |
| × 2 tools (Text+ e Follower1) | ~80 |
| `GiRebuildHighlight` | N palavras × N palavras × camadas × 4 códigos |

Pagar isso uma vez, quando você clica, é barato. Pagar por **valor intermediário
de slider** não é: o Fusion dispara `INPS_ExecuteOnChange` a cada um deles —
medido no Console, ~40 pares `GiRebuildHighlight` + `ApplyGiStyle` num único
ajuste. As versões 6 a 10 gastaram muita engenharia amortecendo esses 40
disparos (comparar antes de escrever, tabelas `NO_SPLINE`/`ESTILO_BASE` para
acordar só o dono do atributo). Na 11 os callbacks saíram e essa engenharia toda
saiu junto — sobrou o que continua valendo em qualquer caminho:

- **Não reescrever o que já está certo.** `SetInput` com o valor que o input já
  tem custa o mesmo que mudar de verdade — invalida o cache e re-renderiza. Cada
  escrita compara antes, e o log diz quantas passaram.
- **`comp:Lock()`** em volta do bloco de escrita, com `Unlock` garantido por
  `pcall` — sem ele o Fusion re-avalia a árvore a cada `SetInput`.

### O `tool` que chega ao callback não é o dono do código

Os chunks (`UpdateTextContent`, do AutoSubs; `ApplyGiStyle`, `SetInputValues` e
`GiRebuildHighlight`, nossos) ficam no `CustomData` do **MacroOperator**. Os
controles que os chamam ficam no Text+ (`Template`). São tools **diferentes**, e
o que o Fusion entrega ao `INPS_ExecuteOnChange` e ao `BTNCS_Execute` é o Text+.

Consequência, medida no log e não deduzida:

```
tool:GetData("SetInputValues")   -> nil     (Text+: não é dono)
comp:GetData("SetInputValues")   -> nil     (a comp também não)
comp:GetToolList(false)          -> algum tool responde
```

Era essa a causa de `Apply Style: nothing was applied` e, do lado do script, de
`style applied via one by one (the chunks are not reachable from a script)`. O
conserto é o mesmo dos dois lados: **varrer a comp tool a tool** (`gi_chunk` no
macro, `dado_do_macro` no `GiAutoSubs.lua`).

### E o VALOR do controle também não está onde parece

O Inspector de um clipe mostra os `InstanceInput` do **MacroOperator** — é lá que
ele grava quando você mexe num slider. O `UserControl` correspondente, no Text+,
pode continuar com o valor antigo.

Consequência para quem **lê**: `tool:GetInput("OutlineThickness")` com `tool` =
Text+ devolve o valor velho, a rotina reescreve o velho por cima, e o log diz
`0 written` logo depois de você ter mudado o controle. Essa combinação —
*mudei o valor* + `0 written` — é a assinatura do problema.

Por isso o `ctl()` das rotinas lê na ordem **macro → tool → Text+**, com
`gi_macro` achando o MacroOperator pelo dono do `InputKeys`, e o
`SetInputValues` escreve **nos dois**.

### O log é a régua

Um clique em **Apply Style** imprime um bloco, sempre, no Console e no
`_gimacro.log`:

```
[GiAutoSubs] --- Apply Style 14:32:07 ---
[GiAutoSubs] fill/outline/shadow -> UpdateAllStyleColors: 3 written, 23 already ok
[GiAutoSubs] button -> ApplyGiStyle: 4 written, 76 already ok; spline: rebuilt 4 keyframes (4 words x 2 layers)
[GiAutoSubs] button -> SetInputValues: 0 written, 0 already ok (0 keys)
```

Nenhuma linha depois do cabeçalho = o clique não achou as rotinas (macro velho
no clipe — veja o carimbo). `written` alto num clique sem mudança = a comparação
parou de funcionar. E `0 keys` no `SetInputValues` é o normal quando vem do
botão: os valores já estão nos controles, o que ele faz é propagar.

---

## 7. Lista de armadilhas

| Sintoma | Causa |
|---|---|
| Mexo no Inspector e a tela não muda | desde a v11 é assim: nenhum controle aplica sozinho, clique **Apply Style** |
| Cliquei em Apply Style e nada | leia o log: sem o bloco, o clique não achou as rotinas (clipe com macro velho); com `0 written` em tudo, o valor já estava lá |
| Escrevi `[[ ]]` dentro de um chunk e o macro parou de carregar | o chunk **já mora** num `[[ ]]` do `.setting`; um `]]` no meio fecha a string cedo. Dentro de chunk, string vai entre aspas com `\\` dobrado |
| O gerador disse "instalado" e o macro não carrega | o `os.exit(1)` do `valida_macro.lua` **não chega** ao Python: o `fuscript` sai 0 de qualquer jeito. Quem decide é o texto `MACRO OK` na saída — foi assim que um macro que não compila chegou a ser instalado |
| `GetData` volta nil | o dono dos chunks é o MacroOperator, não o `Template` nem a comp (6) — varra `comp:GetToolList(false)` |
| Cada ajuste demora | escrita redundante (6) — ou um `INPS_ExecuteOnChange` que voltou |
| Escrevi a cor e a tela mostra outra | o `Follower1` sobrescreve (2.1), ou os keyframes de exemplo do spline (2.2) |
| Escrevi `Opacity1..4` e não muda nada | no `Follower1` elas vêm **conectadas** ao `AnimationKeyframeStretcher` (o fade), e o Follower vence. Desconecte antes (`follower.Opacity4 = nil`, depois `SetInput`) — mas saiba que aquele elemento sai do fade |
| Liguei/desliguei uma camada animada e o array desfez | `Enabled` de camada animada mora no keyframe; quem decide é o `GiRebuildHighlight` (tabela `LIGA`), não o input |
| Um slider parou de fazer efeito depois de eu ligar outra coisa | o input virou **animado** (o Pop conecta um `BezierSpline` aos dois Extend da bolha). Número em input conectado é ignorado; desligue o Pop para devolver o valor fixo |
| A cor do Inspector não muda nada | os keyframes de exemplo do spline (2.2) — eles vencem tudo |
| Caixa em cada letra, não na palavra falada | a bolha marca a palavra falada; sem tempo por palavra ela é desligada (3.2) |
| Consertei o macro e nada mudou | cópia velha no Media Pool (2.4) |
| A caixa/box shadow não aparece | falta `ElementShape{n}` de borda (3.2) |
| `Red6` não pega | `Enabled6` não foi escrito antes (3.1) |
| O outline foi para o canto da tela | usou `Position` em vez de `Offset` (3.3) |
| O controle não aparece no Inspector | falta o `InstanceInput` (passo 3) |
| Mexo no controle, rodo o script, e volta ao que era | ele não está no `InputKeys` (4b): o preset não o carrega |
| Duas legendas empilhadas, a contagem não bate | é o `CONFLITO` (`GiAutoSubs.lua`): em `track_nova` a rodada nova fica em cima da anterior, viva |
| A aba Style continua lá, vazia | o `ControlPage` é uma camada à parte (1) |
| Um grupo adotou o controle do grupo de baixo | `LBLC_NumInputs` desatualizado (passo 1) |
| O **botão** não faz nada | botão executa `BTNCS_Execute`; `INPS_ExecuteOnChange` num `ButtonControl` é aceito e nunca dispara (4b) |
| O combo abre e não tem o que escolher | faltam as `{ CCS_AddString = "..." }` dentro do bloco do controle — o validador recusa isso agora |
| Mudei o `Text` e a legenda não mudou | com o `StyledText` conectado ao Follower1, quem desenha lê do `CharacterLevelStyling1`. Escreva `Text` nos **dois** tools |
| O título não carrega | vírgula faltando, ou `]]` a mais — rode o validador |
| O fade sumiu | escreveu valor num input que tinha `SourceOp` |
| `attempt to index a nil value` no Console | rotina do `CustomData` — a linha do erro é do *chunk*, não do arquivo |

### Achando a linha de um erro de `CustomData`

O Console mostra `[string "..."]:55:`. Esse 55 é a linha **dentro da string**,
contando a partir da linha logo após o `[[`. Para achar no arquivo:

```
linha_no_arquivo = linha_da_abertura_do_[[ + numero_do_erro
```

Foi assim que o `:55` virou `UpdateTextContent`, linha 560:
`wordTiming[oldWordCount].endFrame`.

---

## 8. Onde está cada coisa

| Arquivo | Papel |
|---|---|
| `giautosubs/vendor/autosubs-macro.setting` | o macro original do AutoSubs, intocado |
| `src/gerar_macro.py` | aplica os patches e gera o nosso |
| `giautosubs/GiAutoSubs Caption.setting` | o resultado (não editar na mão) |
| `giautosubs/valida_macro.lua` | valida o `.setting` fora do Resolve |
| `giautosubs/GiAutoSubs.lua` | roda dentro do Resolve |
| `giautosubs/testes.lua` | roda o `main` contra um Resolve falso |
| `giautosubs/amostra_legendas.lua` | fixture com tempo por palavra |
| `src/giautosubs.py` | estilo + pipeline â†’ `legendas.lua` |
| `estilos.json` | a configuração editável |

Regenerar o macro quando o AutoSubs lançar versão nova: trocar o arquivo em
`vendor/` e rodar `gerar_macro.py`. Os patches são declarativos; se um deles não
achar seu alvo, ele avisa em vez de gerar algo errado calado.
