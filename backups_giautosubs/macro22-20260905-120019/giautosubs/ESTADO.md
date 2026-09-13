# GiAutoSubs — onde estamos

Resumo da investigação inteira, do estado do projeto e do que falta.
Atualizado com o relatório de `cannot get Parameter`.

---

## 1. O que o projeto faz

Gera legendas estilizadas no DaVinci Resolve a partir da **sua** transcrição e
diarização já revisadas — sem re-transcrever, como o AutoSubs faz.

Duas metades:

| Lado | Arquivo | Papel |
|---|---|---|
| Python | `src/giautosubs.py` | estilo + pipeline → `legendas.lua` |
| Python | `src/gerar_macro.py` | patcheia o macro do AutoSubs → `.setting` |
| Lua | `giautosubs/GiAutoSubs.lua` | roda dentro do Resolve, cria/estiliza os clipes |

O grafo de animação (`Follower1 → CharacterLevelStyling → BezierSpline`) é
reaproveitado do AutoSubs. Reconstruí-lo do zero seria a parte mais cara e não
traria nada.

---

## 2. A chave para entender todos os bugs

Um valor — digamos, a cor do outline — tem **cinco origens possíveis**, e vence
a última:

```
1. INP_Default do UserControl
2. Default do InstanceInput
3. Inputs do Text+                 (Template)
4. Inputs do Follower1             ← vence o 3 na tela
5. Array do keyframe do spline     ← vence tudo, caractere a caractere
```

**Praticamente todo bug desta conversa foi escrever numa camada e outra
vencer.** É por isso que "o log diz que aplicou, a tela mostra outra coisa" foi
o sintoma recorrente. O detalhamento está em `MACRO.md`.

---

## 3. Os problemas e suas causas, em ordem de descoberta

### 3.1 Rotinas do macro reescrevendo o Text+ sozinhas

`SetInput("Text", ...)` disparava, via `INPS_ExecuteOnChange`:

```
UpdateTextContent → ApplyWordTiming → UpdateHighlight → ApplyHighlight
   → UpdateAllStyleColors   repinta Red2/Green2/Blue2
   → get_current_style      força Enabled4 = 0 (mata a bolha)
   → spline:SetKeyFrames    apaga os keyframes por palavra
```

Seis rotinas desarmadas no `gerar_macro.py`. Também era a origem do
`[string "..."]:55: attempt to index a nil value`.

### 3.2 `ElementShape` faltando — o box shadow invisível

`Level`, `ExtendHorizontal`, `ExtendVertical` e `Round` só valem para formas de
**borda**. Num elemento de texto o Text+ aceita todos e não desenha caixa
nenhuma. Elementos 1–4 nascem dos presets de fábrica; 5–8 nascem como texto.

Mapeamento (lido do dump, contando de zero):
`0` Text Fill · `1` Text Outline · **`2` Border Fill** · `3` Border Outline.

O elemento 4 nasce em `3` — só o contorno do retângulo, não serve para bolha.

### 3.3 O Follower1 sobrescreve o Text+

Ele traz `Red2 = 0.929`, `Thickness2 = 0.8`, `Softness1..8 = 1` embutidos.
Pintar só o Text+ não muda um pixel. É por isso que o `UpdateStyleColor` do
AutoSubs escreve nos **dois** tools.

### 3.4 Keyframes de exemplo no spline — o outline azul

O macro vem com keyframes de demonstração que pintam o elemento 2 de
`rgb(0, 0.35, 1)` caractere a caractere. Como estilo por caractere vence tudo,
**nenhuma cor escolhida no Inspector mudava nada**.

### 3.5 `ipairs` parando no primeiro `nil`

`AppendToTimeline` devolve `nil` no lugar de cada clipe recusado. Com um buraco
no índice 10, `ipairs` entregava 9 tarefas. Era o "129 criados, 9 estilizados" —
e as legendas caíam nas tracks de vídeo do SpeakerSwitch, que já tinham clipe.

### 3.6 A cópia do macro no Media Pool

O Resolve guarda uma cópia do título dentro do projeto. Reinstalar o `.setting`
não a atualiza. Daí o carimbo `GiAutoSubsVersao`.

---

## 4. Erros meus que custaram rodadas

Registrados porque são o tipo de coisa que volta.

1. **Afirmei que `InsertFusionTitleIntoTimeline` semeava o Media Pool.** Não
   semeia — título na timeline não vira item de pool. Eu só tinha testado no
   mock, onde eu mesmo fiz o método existir.
2. **`atualizar_template` apagava o template velho antes de semear o novo.**
   Como semear falha, ele deletou seu template e não repôs. **É por isso que o
   Media Pool está vazio agora.** Ordem corrigida: semeia → confere → só então
   apaga.
3. **Deixei o spline com `KeyFrames = { }`.** É a causa do relatório mais
   recente (abaixo).
4. Afirmei que apagar o item do Media Pool deixaria legendas offline. Era
   cautela apresentada como fato; a evidência aponta o contrário.
5. **Deixei todo callback falhar em silêncio** (`if f then ... end` sem `else`).
   É a raiz do item 5.3: o Inspector parecia inerte e nada no Console explicava.
6. **Li `GetData` do tool errado e anunciei o diagnóstico** — o `Template` não é
   o `tool` do callback (5.4). Duas hipóteses seguidas, as duas desmentidas pelo
   log do usuário. A lição: medir dentro do Resolve antes de nomear a causa.

---

## 5. Sessão 27/08 — "mexo no Inspector e não muda nada"

O sintoma anterior (spline com zero keyframes → `cannot get Parameter` → legenda
não renderiza) está **resolvido**: o gerador escreve um keyframe com array vazio,
como o `RemoveHighlight` do AutoSubs, e o `valida_macro.lua` recusa spline vazio.

O que essa sessão descobriu, medindo em vez de deduzir:

**5.1 — Duas hipóteses minhas, as duas erradas.** Achei que fosse macro velho no
clipe, e depois que fosse o Follower1 vencendo. O `GiDiag` derrubou as duas: os
129 clipes carimbados `5`, spline com keyframes, e Template/Follower1 idênticos
em todos os inputs.

**5.2 — O que o log provou.** Num clipe editado à mão: `OutlineEnabled = 0` e
`OutlineThickness = 0.1071` (valores do usuário), mas `Enabled2 = 1` e
`Thickness2 = 0.15` (o que desenha). O controle guardava; o desenho não recebia.

**5.3 — O culpado real.** Todo callback terminava em `if f then ... end`, sem
`else`. Quando `GetData` voltava nil, o controle não fazia nada **e não dizia
nada**. Um `else` de três linhas teria encurtado a caça inteira. Hoje ele
reclama.

**5.4 — Os chunks moram no MacroOperator, e ninguém mais é dono deles.**
`comp:FindTool("Template"):GetData("ApplyGiStyle")` volta nil, e `comp:GetData`
também. Isto foi lido como "só de fora engana, de dentro funciona" — e estava
errado pela metade: o `tool` que o Fusion entrega ao callback **e ao botão** é o
Text+, então de dentro também volta nil. Quem acha é `comp:GetToolList(false)`,
tool a tool. Ver `MACRO.md` §6 e §8e.

**5.5 — A demora tinha causa, não era "normal".** Um único ajuste disparava ~40
pares `GiRebuildHighlight` + `ApplyGiStyle`, cada par com ~80 `SetInput` e um
spline refeito inteiro — porque o Fusion dispara o callback a cada valor
intermediário do slider. Amortecido na hora (não reescrever input que já está
certo, `comp:Lock()`), e resolvido na raiz em §8e: sem callback, não há 40
disparos.

**5.6 — Log por atributo, sempre.** Cada mudança imprime uma linha dizendo o
controle, a rotina que rodou, quantas escritas foram feitas, quantas eram
redundantes, e o que aconteceu com o spline. É a régua para saber se uma
mudança futura melhorou ou piorou.

**Macro carimbado `6`.** Como cada clipe carrega a própria cópia do macro, os
clipes criados antes disso continuam com o comportamento velho — o carimbo é
como o `GiDiag` distingue.

---

## 6. Estado atual

### Funciona e está coberto por teste

- Transcrição com tempo por palavra: **128/128 legendas, 601 palavras**, texto
  batendo exatamente com a concatenação dos tokens.
- `legendas.lua` regerado; o teste contra o Resolve falso exercita
  `128 clips with per-word keyframes`.
- Outline preto, forma de borda correta, bolha e box shadow.
- Aba Style eliminada; botões "Update ..." removidos. Quem aplica é o **Apply
  Style**, no topo do Inspector — nenhum controle reage sozinho (§8e).
- Uma track só para todas as legendas.
- `MODO = "atualizar"`: restiliza o que já está na timeline sem recriar,
  preservando texto corrigido à mão, posição e aparas. Não toca no Media Pool.
- `ApplyGiStyle` escreve nos dois tools; `GiRebuildHighlight` refaz os keyframes
  para a cor alcançar um elemento animado.
- Criação de 128 legendas numa rodada: **128 criadas, 128 estilizadas, 0 falhas**
  (confirmado no Console do usuário, 27/08).
- `GiDiag.lua` — diagnóstico somente-leitura, instalado em
  `Scripts/Utility`. Lista carimbo de macro por clipe, legendas por track,
  controles presentes, e Template vs Follower1 lado a lado.
- **O contrato do macro** (§8c): o `testes.lua` roda o `main` com os chunks ao
  alcance e prova que o preset chega inteiro, opaco, numa chamada só — e que a
  bolha chega desligada na legenda sem tempo por palavra.
- **Os três modos de conflito** (§8c), cada um com o seu teste: `substituir`
  apaga e reaproveita a track; `contornar` não apaga nada e não cria nada onde
  já existe; `track_nova` empilha.
- **A exportação do bin**, contra o Resolve falso: copia para uma pasta só do
  template, exporta, apaga a pasta temporária e grava o carimbo.

### Onde ler o log (o Console não serve)

O Console do Resolve não deixa copiar log longo — uma rodada de 128 legendas
passa de trezentas linhas e rola para fora antes de dar para selecionar. Por
isso tudo grava em arquivo, em `giautosubs\`:

| arquivo | quem escreve | quando zera |
|---|---|---|
| `_giautosubs.log` | `GiAutoSubs.lua` (a rodada de criação) | a cada execução |
| `_gimacro.log` | as rotinas **de dentro do macro** — um bloco por clique em Apply Style | ao passar de 2 MB |
| `_gidiag.log` | `GiDiag.lua` | a cada execução |
| `_bin_importado.txt` | a trava de importação do `.drb`, por projeto + versão do bin | nunca (apague para forçar nova tentativa) |
| `giautosubs-bin.drb.versao` | o carimbo do bin exportado | reescrito a cada exportação |

O `_gimacro.log` é o mais importante: é o único jeito de ver o que acontece
quando se mexe no Inspector. `io` pode não existir no sandbox de um callback,
então a escrita é protegida por `pcall` — se o arquivo não aparecer, o `print`
continua valendo e a causa é essa.

### O laço de edição do macro (custo real)

Mexer no macro é caro, e vale saber antes de propor mudança:

1. Subir `MACRO_VERSAO` no `giautosubs.py`.
2. `gerar_macro.py --instalar` regera e instala (com `.bak`).
3. **Regerar o `legendas.lua`** (`giautosubs.py <pasta_do_corte>`) — ele carrega
   o `macro_versao` que o Lua exige. Sem esse passo o `conferir_macro` compara a
   versão velha com a velha, conclui "está em dia" e **nunca troca a cópia do
   Media Pool**: você recria as legendas e elas saem com o macro antigo, sem
   nenhum aviso. Foi exatamente o que aconteceu na primeira tentativa do 27/08.
   Cuidado com os argumentos: `--estilo` e `--transcript` precisam ser os mesmos
   da geração anterior, senão a legenda muda de cara (ou perde o tempo por
   palavra) sem ninguém pedir.
4. **Reiniciar o Resolve** — o Fusion só varre `Templates/Edit/Titles` no boot.
5. **Recriar as legendas** — cada clipe carrega a própria cópia do macro; clipe
   que já existe continua com o comportamento antigo.

Ou seja: nenhuma mudança de macro chega numa legenda existente. Só mudança de
*valor* (Inspector, ou `MODO = "atualizar"`) chega.

---

## 7. O que fazer, em ordem

O macro está carimbado `10` e o `legendas.lua` já foi regerado com esse número.
Falta instalar e reiniciar — os dois passos que só você pode dar.

1. **Instalar o macro:** `python gerar_macro.py --instalar` (guarda um `.bak`
   do anterior sozinho).
2. **Fechar e abrir o Resolve** — o Fusion varre `Templates/Edit/Titles` no
   boot, então um `.setting` instalado com o Resolve aberto não existe ainda.
3. **Rodar com `MODO = "criar"`.** Não precisa apagar as legendas antes: o
   `CONFLITO = "substituir"` faz isso, e ainda reaproveita a track delas. As
   atuais são do macro `7` e não entendem o contrato novo.
4. Mexer no Inspector do clipe. Cada ajuste imprime uma linha no Console
   dizendo qual controle, qual rotina, quantas escritas e o que houve com o
   spline. Se algum não surtir efeito, **Actions > Apply Style** força a
   aplicação — e o Console diz o que aconteceu.

Duas linhas novas no resumo dizem se o caminho novo pegou:

```
  conflict mode     substituir
  style applied     via SetInputValues (the macro's own contract)
```

Se a segunda disser `one by one (...)`, o estilo entrou igual — só pelo caminho
antigo, porque o script não alcançou os chunks do `CustomData` (`MACRO.md` §4b).
Não é erro, é a diferença entre um caminho e dois.

Se um controle não surtir efeito, o Console responde sozinho: sem linha
`ApplyGiStyle`, o callback não rodou; com linha e `0 written`, o valor já
estava aplicado; `spline: rebuilt` diz que os keyframes foram refeitos.

---

## 8. Em aberto

| Item | Risco |
|---|---|
| ~~**`Level` está trocado**~~ — **corrigido no macro 22** | ver abaixo |
| O ganho de velocidade da §5.5 não foi medido depois do conserto | o log traz os números; comparar antes/depois é o próximo passo |
| Reinício do Resolve + recriar clipes a cada mudança de macro | não tem contorno; ver §6, "o laço de edição" |
| A exportação do `.drb` (§8c) nunca rodou dentro do Resolve | `ExportFolder` / `CopyClips` / `DeleteFolders` estão testados contra o Resolve falso, não contra o de verdade. Se a build recusar algum deles, o script diz e segue — o passo manual continua valendo |
| **`testes.lua` falha em `Offset3` contra um `legendas.lua` real** | `FAILED: Offset3 from the config was overwritten by the style's own offset`. Passa contra o `amostra_legendas.lua` e falha contra o do `Corte_Mosquito` — e falha igual num `legendas.lua` gerado **antes** do macro 22, então não veio de lá. O caminho é `fundir_preset` → `dados.inputs._offset{n}` → passo 6 do `estilizar`; a diferença entre os dois arquivos que ainda não foi isolada é o `Enabled3 = 0` do `capcut_bolha` (a sombra do texto desligada). Enquanto não for resolvido, **um `Offset` vindo de um preset exportado pode não chegar ao clipe** |
| **`refazer_tempos` estica ao APAGAR palavra, e transborda em legenda curta** | medido em 01/09: `"i love potato"` (frames 0/30/90) → `"i love"` dá 0/90, e o `" love"` dito no 30 passa a acender no 90; e frames 0/1/2 com duas palavras a mais viram 0..4, além do fim. A interpolação é posicional e não sabe **qual** palavra saiu. O conserto das duas é o mesmo: guardar a **palavra** no `GiWordTiming` e casar palavra a palavra, mantendo o frame exato das que não mudaram. Custa um campo na escrita e **uma recriação** dos clipes. Adiado a pedido do usuário, que quis testar o que está feito antes |
| **O array de estilo por caractere é quadrático nas palavras** | é a causa medida do travamento no playback. O corte (duas faixas por keyframe em vez de uma por palavra) está descrito no fim da §8 e depende de confirmar, dentro do Resolve, que faixa posterior vence faixa anterior |
| Custom `ControlPage` ("Extras") nunca foi visto dentro do Resolve | o `.setting` compila e o validador aprova, mas quem desenha a aba é o Fusion. Se ela não aparecer, os controles caem na primeira página visível (a `Text`) — feio, não quebrado |
| Licença do AutoSubs para redistribuir | ver `DISTRIBUICAO.md`, seção 0 |
| GiAutoSubs mora dentro do `pre_production` | foi pedido como script local independente; a separação ainda não foi feita |

---

## 8b. O AutoSubs faz isso em 19 linhas (leitura de 27/08)

Lido do `autosubs_core.lua` (87 KB) instalado em `%LOCALAPPDATA%\AutoSubs`. A
forma dele é outra, e é menor:

- **O Resolve é o servidor.** O stub de 6 linhas carrega o núcleo, que abre um
  servidor HTTP sobre FFI na porta **56002** e *depois* lança o app. Responde a
  pergunta que ficou em aberto na primeira jornada: a ponte automática é viável
  sem Studio, e é assim que se faz.
- **O estilo é editado num clipe descartável.** `StartPresetEdit` cria track
  temporária + clipe de 5 s, você mexe no Inspector do Resolve, e
  `CapturePresetSettings` lê os valores de volta e apaga tudo. Não existe
  propagação porque não existe divergência.
- **O contrato do macro são duas funções**, `GetInputValues` (8 linhas) e
  `SetInputValues` (9 linhas). O app guarda uma **tabela opaca** — o schema
  pertence ao macro, então controle novo não muda código em lugar nenhum.
- **`SetInputValues` termina chamando `SetAnimations` e `UpdateHighlight`** — as
  rotinas do próprio macro. São exatamente as que este projeto desarmou, e é
  dessa decisão que nasce a guerra das cinco camadas.
- **Preview é frame renderizado**: `comp:AddTool("Saver")` + `comp:Render` de um
  frame → PNG.
- **`caption-bin.drb` + `ImportFolderFromFile`**, com trava de uma tentativa por
  projeto, mata o passo manual do Media Pool.
- **`conflictMode`** (substituir / contornar / track nova) resolve, por decisão
  declarada, o problema das 129 legendas achadas contra 128 criadas.

Ordem recomendada para adotar: o par Get/SetInputValues, o `.drb` e o
`conflictMode` primeiro (ganho quase sem risco, um ciclo de macro); o clipe
descartável depois (muda a jornada); rearmar as seis rotinas por último — é o
de maior retorno e o único que pode reabrir bugs já fechados.

**Não copiar:** o AutoSubs re-transcreve e re-diariza do zero, anima um
elemento por vez (bolha OU cor, nunca bolha com sombra própria) e não tem cor
por falante. Adotar a forma dele sem abrir mão dessas três coisas.

---

## 8c. Os três primeiros, feitos (macro 8)

Um ciclo de macro, como previsto. O quarto (clipe descartável) continua de fora
porque muda a jornada, e rearmar as seis rotinas continua por último.

### O contrato do macro voltou a ser o par Get/SetInputValues

O macro vendorado **já trazia** `InputKeys`, `GetInputValues` e
`SetInputValues` — não foi preciso escrever nenhum dos três. O que mudou:

- `InputKeys` passou a listar os **nossos** 50 controles (os `Highlight*` do
  AutoSubs saíram: foram desarmados e escondidos, e uma chave que lê nil todo
  dia é pior que chave nenhuma). A lista sai do `NOVOS` do `gerar_macro.py`, não
  é mantida à mão.
- `SetInputValues` aponta para `UpdateAllStyleColors` → `ApplyGiStyle` em vez de
  `SetAnimations` + `UpdateHighlight`. O `UpdateHighlight` é **uma das seis
  desarmadas**: sem essa troca o contrato compilaria, rodaria e não faria nada.
- Os **43 callbacks** do Inspector passaram a entrar por ele — os nossos e os do
  AutoSubs. Antes eram três portas (`ApplyGiStyle`, `UpdateAllStyleColors`,
  `SetAnimations`); "esse controle não faz nada" tinha três causas possíveis, e
  agora tem uma.
- O `GiAutoSubs.lua` entrega o preset em **uma chamada** por legenda em vez de
  escrever controle por controle.

O detalhamento está em `MACRO.md` §4b. O que **não** mudou: as economias da
§5.5 (comparar antes de escrever, `NO_SPLINE`, `comp:Lock()`) continuam — elas
só ficam desnecessárias com o clipe descartável, que é o item 3.

Duas coisas que essa mudança obrigou a acertar:

1. **`spline = false` na chamada do script.** Sem isso o array por palavra seria
   refeito duas vezes por legenda — a metade cara do callback, 128 vezes à toa.
2. **A bolha desligada tem que estar no PRESET.** Numa legenda sem tempo por
   palavra a bolha nasce apagada; antes bastava não escrever `Enabled4`, mas
   agora quem escreve o estilo é o macro, lendo `BubbleEnabled`. Se o preset
   dissesse 1, o `ApplyGiStyle` reacenderia — e voltaria a caixinha em cada
   palavra. De quebra, o Inspector passou a dizer a verdade sobre essas legendas.

### O `.drb` é exportado pelo próprio script

`mediaPool:ExportFolder` existe. Então o "arraste o título para o Media Pool"
virou um passo **de uma vez na vida** em vez de um por projeto: assim que o
carimbo do macro bate, o script exporta o bin sozinho, e o projeto seguinte
importa sem ninguém arrastar nada.

Detalhes que não são opcionais (`MACRO.md` §2.4): exportar só **depois** da
conferência de carimbo, exportar de uma pasta **só do template** (senão vai
junto o Media Pool inteiro), e recusar a importação de um bin mais velho que a
rodada. Mais a trava de uma tentativa por projeto, e a limpeza que apaga
**todas** as cópias obsoletas em vez de só a primeira encontrada.

### A rodada declara o que fazer com o que já existe

`CONFLITO`, no topo do `GiAutoSubs.lua`, com os três valores do AutoSubs:

| valor | o que faz |
|---|---|
| `substituir` (padrão) | apaga as legendas da rodada anterior e **reaproveita a track delas**. Só toca em clipe que carrega o carimbo `GiAutoSubsVersao` — vídeo, áudio e título de outra gente não são tocados |
| `contornar` | não apaga nada e não cria legenda onde já existe uma. É o modo para completar uma rodada interrompida |
| `track_nova` | o comportamento antigo, agora por escolha: empilha a rodada nova acima |

É o conserto do **"129 achadas contra 128 criadas"**: aquilo não era um bug, era
uma decisão que ninguém tinha tomado. O `reaproveita a track` importa mais do
que parece — sem ele cada rodada subia uma track e a timeline virava escada.

Uma armadilha que apareceu ao implementar: `contornar` faz `clipes` deixar de
ser cópia 1-pra-1 de `segments`, e o resto do arquivo indexa `segmentos[i]`.
O índice do segmento agora **viaja junto** com o pedido — sem isso, pular uma
legenda faria as seguintes receberem o texto da vizinha, em silêncio.

---

## 8d. O botão "Apply Style", e o Inspector em inglês (macro 9)

### O botão

Um `ButtonControl` no grupo **Actions**, criado como caminho *adicional* ao dos
callbacks.

> **Superado pela §8e.** No macro 11 o botão virou o único caminho, subiu para o
> topo do Inspector, e o `nothing was applied` desta versão ganhou explicação: o
> `tool:GetData` aqui embaixo nunca podia funcionar. O resto desta seção é o
> registro de por que a decisão foi outra na época — inclusive a medição.

**Botão executa `BTNCS_Execute`, não `INPS_ExecuteOnChange`** — lido do
`UpdateAnimationButton` do AutoSubs, não deduzido. Um `ButtonControl` declarado
com o atributo dos outros controles aparece, aceita o clique e não faz nada, e o
Fusion não reclama. O `valida_macro.lua` agora recusa exatamente isso (testado
recriando a armadilha de propósito).

Ele foi feito aditivo de propósito. O que o `_gimacro.log` mediu nos macros 6 e
7 (7.196 disparos vindos do Inspector) diz por quê:

| | |
|---|---|
| escritas por disparo | **6,3** em média (máx. 17) |
| escritas puladas por já estarem certas | 40,7 por disparo |
| disparos que **refazem o spline inteiro** | **52%** |

A economia de escrita já resolveu a metade dela — 87% das escritas são puladas.
O que sobrou caro é o spline, e ele só é refeito em metade dos disparos (a
tabela `NO_SPLINE`). Trocar os outros 48% por dois gestos seria pagar ergonomia
por um problema que eles não têm.

**Se ainda ficar lento**, o corte seguinte é cirúrgico e está identificado:
tirar as cores animadas do `NO_SPLINE` e deixar o spline por conta do botão.
Numa camada animada a cor mora no keyframe, então não existe preview barato —
o clique passa a ser o "fim do arrasto" que o Fusion não oferece como evento. O
preço, explícito: a cor da bolha só aparece ao clicar. Não foi feito agora
porque o ganho ainda não foi medido **depois** do conserto da §5.5.

### O log que não parava (macro 10)

Um erro meu no 9, achado pelo usuário lendo o `_gimacro.log`. Ao fazer **todo**
callback entrar pelo `SetInputValues`, todo controle passou a acordar o
`UpdateAllStyleColors` — inclusive `BubbleRound`, `BoxShadowSoftness`,
`TextBoxEnabled`, que não tocam em fill/outline/shadow. O sintoma no log:

```
[GiAutoSubs] fill/outline/shadow -> UpdateAllStyleColors: 0 written, 26 already ok
[GiAutoSubs] BubbleRound -> ApplyGiStyle: 6 written, 41 already ok; spline: skipped
```

26 comparações e uma linha de log por disparo, sempre `0 written`, vezes ~40
disparos por arrasto de slider. O arquivo passou de 651 KB para 2,1 MB.

**A lição:** uma porta de entrada única não quer dizer um caminho único lá
dentro. O princípio certo já estava escrito no comentário ao lado — *"um
controle só precisa refazer o que ELE alcança"* — e tinha sido aplicado só ao
spline (`NO_SPLINE`). Agora a `origem` também escolhe o dono: animação →
`SetAnimations`; fill/outline/shadow → `UpdateAllStyleColors`; bolha, caixa e
sombras → `ApplyGiStyle` direto. A porta continua uma só.

Junto veio um teto de **2 MB** no `_gimacro.log`: ele é append-only de
propósito (um callback não tem "início de rodada" para zerar), mas "uma linha
por ajuste" era otimismo. Ao cruzar o teto ele recomeça. O log anterior foi
guardado em `_gimacro.anterior.log` — é onde estão as medições da §8d.

### Os rótulos

O Inspector inteiro passou para o inglês, que é a convenção declarada no topo do
`GiAutoSubs.lua` ("COMENTARIOS em portugues; MENSAGENS e UI em ingles") e que os
controles novos tinham nascido fora dela. O vocabulário segue o do AutoSubs em
vez de inventar sinônimos: `Bubble`, `Enabled`, `Bubble Color`, `Opacity`,
`Level`, `Extend Horizontal`, `Extend Vertical`, `Round`, `Text Box`,
`Box Shadow`, `Shadow on Bubble`, `Offset X/Y`, `Softness`, `Actions`.

> **O combo `Level` continua com o defeito da §8.** As quatro opções foram
> traduzidas na **mesma ordem** — o que agora se chama "Character" desenha por
> linha e vice-versa. Consertar exige mexer no `NIVEIS` do `giautosubs.py`
> junto, senão o Inspector e o script passam a discordar; traduzir na ordem
> mantém o comportamento idêntico ao de antes.

---

## 8e. O Apply Style vira o único caminho (macro 11)

Partiu do log do usuário, que dizia as duas coisas ao mesmo tempo:

```
[GiAutoSubs] Apply Style: ... nothing was applied
[GiAutoSubs] OutlineColorRed changed, but SetInputValues was not found on this tool - nothing was applied
[GiAutoSubs] fill/outline/shadow -> UpdateAllStyleColors: 0 written, 26 already ok
[GiAutoSubs] OutlineColorRed -> ApplyGiStyle: 6 written, 41 already ok
```

### A causa: `tool` não é quem a gente pensava

`tool:GetData("SetInputValues")` volta **nil** no callback e no botão. O código
mora no `CustomData` do **MacroOperator**; os controles moram no Text+
(`Template`), e é o Text+ que o Fusion entrega às duas coisas. A §5.4 registrava
metade disso ("de fora engana, de dentro funciona") — a metade errada.

O conserto é o mesmo dos dois lados: **varrer a comp tool a tool**
(`comp:GetToolList(false)`) até achar quem responde pelo nome. `gi_chunk` no
macro, `dado_do_macro` no `GiAutoSubs.lua`. O mesmo bug fazia o resumo do run
dizer `style applied via one by one (the chunks are not reachable from a
script)` — e ninguém tinha ligado uma coisa à outra.

O `testes.lua` passou a modelar isso: o Resolve falso agora tem um MacroOperator
separado carregando os chunks, e `comp:GetData` devolve nil como na vida real. O
mock antigo entregava o chunk pela comp, ou seja, testava um caminho que não
existe.

### A decisão: sem callback nenhum

Os 43 callbacks por controle saíram — e os 10 que vinham do macro do AutoSubs
junto (`_desautomatizar`). Dois motivos, ambos no log acima: `INPS_ExecuteOnChange`
dispara a cada valor intermediário de um arrasto (~40 por ajuste), e metade dos
disparos só sabia imprimir erro. **Um clique = um bloco de log** que se consegue
ler; era isso que faltava para diagnosticar qualquer coisa.

O que saiu junto, por ter existido só para amortecer aqueles 40 disparos:

| saiu | era |
|---|---|
| `ANIMACAO` / `ESTILO_BASE` (no `SetInputValues`) | rotear cada controle para a rotina que ele alcança |
| `NO_SPLINE` (no `ApplyGiStyle`) | pular o spline quando o atributo não vive nele |
| checkbox `GiDebug` + grupo `Diagnostics` | detalhe extra no Console |
| `GiWatch.lua` | a muleta do callback que não disparava |

Agora: `origem` é `"button"` ou `"script"`; o botão roda `SetAnimations` +
`UpdateAllStyleColors` → `ApplyGiStyle` e refaz o spline sempre; o script segue
mandando `spline = false` nas 128 legendas, que é a única economia que ainda paga.

O validador virou do avesso na mesma medida: onde exigia que seis controles
tivessem `INPS_ExecuteOnChange`, agora exige que **nenhum** tenha.

### Actions no topo

O grupo `Actions` passou a ser o primeiro `InstanceInput` do bloco `Inputs`,
acima até dos controles do AutoSubs (`_abrir_instance_inputs`). A ordem do
Inspector é a ordem desse bloco — e um botão que fecha todo ajuste não pode
morar depois de 40 controles e uma rolagem.

### Limpeza

Apagados: `GiWatch.lua`, `_gimacro.anterior.log`, `_gimacro.log` (2,5 MB cada) e
os 20 `.bak` acumulados em `Templates/Edit/Titles` (1,9 MB). O macro caiu de 86
para 33 rotinas Lua embutidas — o resto eram os callbacks.

### Os dois que continuavam mudos (macro 12)

Com o botão funcionando, sobraram dois atributos que o Apply Style não mexia:
**bolha** e **outline stroke**. Duas causas diferentes, nenhuma delas no botão.

**(a) O Inspector do clipe não edita o Text+.** Ele edita os `InstanceInput` do
**MacroOperator**. As rotinas liam o valor com `tool:GetInput(nome)` — e `tool` é
o Text+, onde o valor ainda era o antigo. Resultado: leem velho, escrevem velho
por cima, e o log diz `0 written` com o Inspector mostrando outra coisa. É o que
o log do usuário já mostrava no macro 9, e que passou batido:

```
OutlineColorRed -> ApplyGiStyle: 6 written, 41 already ok    <- mexeu na cor
fill/outline/shadow -> UpdateAllStyleColors: 0 written, 26 already ok
```

`0 written` **logo depois de mudar um valor** é a assinatura desse bug.

Conserto: `ctl()` lê na ordem **macro → tool → Text+** (`gi_macro`, que acha o
MacroOperator pelo que ele é — o dono do `InputKeys` — e não pelo nome), e o
`SetInputValues` passou a escrever nos **dois**, para ninguém mais precisar
decidir qual está em dia.

**(b) `Enabled` de camada animada mora no spline.** O array do character-level
styling era refeito a partir do `on_base`/`on_ativo` gravados no clipe quando ele
nasceu, e o array vence o input: desmarcar `Bubble > Enabled` escrevia
`Enabled4 = 0` no Text+ e no Follower1, e o keyframe da palavra falada devolvia
`1` em seguida. Agora o `GiRebuildHighlight` consulta os checkboxes (tabela
`LIGA`: bolha → `BubbleEnabled`; sombra da bolha → também `BoxShadowOnHighlight`;
caixa → `TextBoxEnabled`; sombra da caixa → também `BoxShadowOnNormal`), resolvido
uma vez por camada e não por palavra — o laço é N×N×camadas.

A **cor** da bolha já vinha do Inspector desde o macro 5 (`CONTROLE_DA_CAMADA`);
era só o liga/desliga que faltava.

### A opacidade da bolha, e a cor da palavra falada (macro 13)

**`BubbleOpacity` era escrita e ignorada.** No Follower1, `Opacity1..4` chegam
**conectadas** ao `AnimationKeyframeStretcher` — é assim que o fade do AutoSubs é
feito — e o Follower vence o Text+. Escrever `Opacity4` no Text+ nunca teve
chance. (O código já sabia da conexão: ele *pulava* o Follower para as opacidades
1..4, o que evitava matar o fade e, sem que ninguém notasse, tornava aquelas
quatro opacidades incontroláveis.)

Agora a bolha desconecta antes de escrever — `follower.Opacity4 = nil` e só então
`SetInput`, o mesmo gesto do `RemoveFade` deles — e **volta para o fade** se a
opacidade voltar a 1. Os elementos 1..3 continuam conectados: ali a conexão é o
fade do texto.

> Consequência aceita: com opacidade < 1, a bolha não acompanha o fade in/out.
> Voltar o slider para 1 devolve a conexão.

**A palavra falada ganhou seletor de cor** (grupo `Spoken Word`:
`WordFillEnabled` + `WordFillColor*`). Era o único atributo do destaque que só
existia no JSON: o elemento 1 fica fora do `CONTROLE_DA_CAMADA` porque a cor
**base** dele é a do falante, e um seletor único apagaria isso nas 128 legendas.
O controle entra só pela cor **ativa** — a palavra sendo dita — e a cor de cada
pessoa continua valendo em todas as outras.

Se o estilo não tiver camada de fill (o `capcut_bolha` não tem: lá o destaque é
só a bolha), o `GiRebuildHighlight` **cria** a camada, com a cor base lida do
próprio Text+ — que é onde a cor do falante já está. Por isso ligar o checkbox e
clicar em Apply Style basta, sem regerar nada.

### O pop da bolha (macro 14)

O efeito do CapCut: a bolha entra menor nos dois eixos e cresce até o tamanho
normal, a cada palavra. Controles `Pop`, `Pop Amount` e `Pop Frames`, no grupo
Bubble; no JSON, `destaque.caixa.pop`.

**Por que dá para fazer com um input global.** Não existe "escala" por elemento
no Text+ — quem faz o tamanho da bolha é o par `ExtendHorizontal4` /
`ExtendVertical4`, e esses são inputs globais, não por caractere. O que torna a
coisa possível é que **num instante qualquer só existe uma bolha na tela**: o
array do spline acende a da palavra falada e apaga as outras. Animar o input
global anima exatamente a bolha que se vê.

Por palavra, três keyframes em cada eixo:

```
[início]            extend − amount     ← entra menor
[início + frames]   extend              ← cresce
[próximo início−1]  extend              ← SEGURA até a próxima palavra
```

O terceiro não é detalhe: sem ele a interpolação entre o fim do pop e a palavra
seguinte é uma rampa longa, e a bolha encolheria devagar durante a palavra
inteira — o oposto de um pop.

**Rotina própria (`GiBubblePop`), não dentro do `GiRebuildHighlight`.** O pop é
geometria; o rebuild é o array de estilo por caractere. E as duas são pedidas em
momentos diferentes: o `GiAutoSubs.lua` escreve o array ele mesmo nas 128
legendas e manda o rebuild **pular** — se o pop morasse lá, ele simplesmente não
aconteceria em nenhuma legenda criada pelo script, e isso só apareceria olhando
quadro a quadro. O `testes.lua` cobre exatamente isso (`_pop_chamado`).

Com o pop ligado, o `ApplyGiStyle` **não** escreve os dois Extend: eles estão
conectados a um `BezierSpline`, e escrever número em input conectado é aceito e
ignorado (ou derruba a conexão). Desmarcar o Pop desfaz a conexão e devolve o
valor fixo — mesma simetria da opacidade.

### `Case`: onde ele mora, e por quê (macro 15)

Combo `As typed / lowercase / UPPERCASE`, **dentro do grupo "Text"**, entre
`Style` e `Size`. No JSON: `fonte.caixa_das_letras`.

- **No grupo Text, não num grupo novo.** Caixa das letras é tipografia — irmã de
  Font, Style e Size, não de cor nem de animação. Quem quer "tudo em maiúsculas"
  procura onde escolheu a fonte, que é onde todo editor põe isso. Um grupo
  "Text Options" seria um lugar a mais para procurar.
- **Logo abaixo de `Style`.** Font → Style → Case são a *forma* da letra; Size e
  Position são métrica e lugar. O corte natural fica entre Case e Size.
- **Combo, não dois checkboxes.** Com dois checkboxes existe o estado "os dois
  marcados", que não quer dizer nada e obriga alguém a decidir quem ganha. Num
  combo o estado inválido não é expressável, e o padrão diz por escrito que não
  mexe em nada (`As typed`) — dois checkboxes desmarcados dizem isso por
  ausência.

Duas coisas que valem mais que o código:

**Não é destrutivo.** O texto digitado fica em `GiTextOriginal` e a
transformação sai sempre dele; sem isso, alternar `UPPERCASE → lowercase`
perderia a capitalização original para sempre. E se o texto foi **editado à mão**
no Inspector — hábito deste projeto, é para isso que existe o `MODO =
"atualizar"` — o texto novo vira o original. Sem essa regra, clicar Apply Style
depois de corrigir uma palavra devolveria a legenda ao texto antigo.

**Acento.** `string.upper` do Lua é ASCII: "ação" viraria "AÇãO" — com o til
minúsculo, bem visível numa legenda. As letras que o português usa estão no bloco
Latin-1 do UTF-8, onde a minúscula é a maiúscula + `0x20` e as duas ocupam os
mesmos dois bytes; daí o `gsub` no byte de continuação. **O comprimento em
caracteres não muda**, e isso não é detalhe: o array de estilo por caractere
endereça as palavras por `startIndex`/`endIndex`. Verificado no `fuscript`:
`ação e coração` → `AÇÃO E CORAÇÃO`, 18 bytes nos dois.

### Os combos estavam vazios (macro 16)

O `Case` "não funcionava" porque **não dava para escolher nada**: o combo abria
sem opção nenhuma. As `{ CCS_AddString = "..." }` eram enfiadas com um
`str.replace` na linha do `INPS_ExecuteOnChange`, e quando os callbacks saíram
(macro 11) essa linha deixou de existir — o replace parou de casar, não achou
nada, e não reclamou.

Os dois `Level` (bolha e caixa) estavam assim **desde o macro 11**, e ninguém
notou: são controles que raramente se mexe, e um combo vazio parece um combo
qualquer até você abrir.

Agora as opções entram na montagem do bloco (não dependem de mais nada estar
presente) e o `valida_macro.lua` recusa combo sem opção — e recusa também
`INP_MaxAllowed` maior que a lista, que deixaria escolher um valor sem rótulo.

> É o terceiro `replace`/`find` silencioso desta série (o primeiro foi o
> `if f then ... end` sem `else`; o segundo, o regex de callback que exigia
> vírgula). O padrão vale como regra: **transformação de texto que não casa tem
> que reclamar**, ou vira um controle que existe e não faz nada.

### O texto que aparece na tela não é o `Text` do Text+ (macro 17)

O `Case` mudava o campo `Text` no Inspector e **não mudava a legenda**. A cadeia
real é esta:

```
Template (Text+)
   Text        = "..."                        ← o que o Inspector mostra
   StyledText  ← Follower1.StyledText         ← o que ele RENDERIZA
Follower1
   Text        ← CharacterLevelStyling1.StyledText
CharacterLevelStyling1
   Text        = "..."                        ← o texto de verdade
```

Com o `StyledText` conectado, o `Text` do Text+ vira só um campo de Inspector.
Quem desenha lê do **CharacterLevelStyling1**.

O `GiAutoSubs.lua` já escrevia nos dois desde sempre — está lá no comentário do
passo do texto, e é por isso que as legendas criadas pelo script sempre
apareceram certas. Era a rotina do macro que estava a meio caminho.

**E editar o texto à mão tinha o mesmo problema, por outro caminho (macro 18).**
Digitar no campo `Text` do Inspector escreve só no Text+. Quem sincronizava os
dois no AutoSubs era o `UpdateTextContent` — **uma das seis rotinas que este
macro desarma** (ela vinha junto com a cadeia que repintava o estilo inteiro).
Sem ela ninguém propagava; e o Apply Style também não, porque a rotina comparava
o texto só com o Text+ e concluía "já está certo" enquanto o CLS1 seguia com o
texto velho.

Agora ela compara **por alvo** — daí o nome ter virado `GiApplyText`: ela não
aplica só a caixa das letras, ela é a dona do texto. Um caso fechou o outro.

> Editar o texto muda o **número de caracteres**, e o destaque por palavra
> endereça o texto por índice (`GiWordTiming`). Realinhar palavra a palavra só o
> script sabe fazer; o macro avisa no log quando os dois discordam, em vez de
> deixar o destaque errar calado.

### O botão "Display Config" (macro 16) → **"Export Config"** (macro 21)

Grupo `Config`, no fim do Inspector — é ferramenta, não estilo: você não passa
por ele ajustando uma legenda, você vai até ele quando quer guardar ou mandar a
configuração.

O `Display Config` imprimia o estilo do clipe no Console e num
`giautosubs\_giconfig.txt`. Dava para **ler** o ajuste e não dava para **usar**:
para o ajuste voltar à rodada era preciso traduzi-lo à mão para o `estilos.json`.

Hoje ele **exporta**. Pergunta um nome (`comp:AskUser`; na página Edit o diálogo
não existe, e aí o arquivo sai carimbado com a hora — melhor um nome feio que
uma exportação recusada) e grava
`giautosubs\presets\<nome>.txt`. É a pasta que o `GiAutoSubs.lua` lista na
**pergunta 2** da rodada ("qual configuração de legenda"), e o preset escolhido
entra por cima do estilo assado no `legendas.lua`.

O formato é `chave<TAB>valor`, o **mesmo** do `Generate Caption Style` — os dois
botões compartilham o corpo (`_EXPORTAR`, dois destinos) e o mesmo leitor
(`ler_estilo_exportado`). Duas serializações do mesmo estilo seriam duas chances
de divergir, e a que divergisse seria a que ninguém confere. De quebra, um preset
serve direto ao `gerar_macro.py --importar-estilo giautosubs\presets\<nome>.txt`
quando você quiser promovê-lo a estilo nomeado do `estilos.json`.

Lê pelo mesmo `GetInputValues`/`InputKeys` que o script usa — então um controle
novo entra no preset sozinho, sem lista para manter em dia — mais os cinco
inputs que o `InputKeys` não carrega (`EXTRAS`: suavidade do outline e a sombra
do texto inteira) e o `Center`, sem os quais o estilo exportado não renderizaria
igual ao clipe de onde saiu.

### As três perguntas da rodada (macro 21)

O `GiAutoSubs.lua` deixou de ser "edite a constante no topo para trocar de
corte". Toda rodada pergunta, nesta ordem:

| # | pergunta | onde procura | escape |
|---|---|---|---|
| 1 | qual **legenda padrão** (Title) | `Templates\Edit\Titles\GiAutoSubs*.setting` | `ESTILO_FIXO` |
| 2 | qual **configuração** (preset) | `giautosubs\presets\*.txt` | `PRESET_FIXO` |
| 3 | qual **arquivo** com o texto | onde estava o da rodada anterior | `ARQUIVO` |

Três decisões, três diálogos — nenhuma delas o script tem como adivinhar, e as
três mudam de uma rodada para a outra.

Detalhes que custam quando faltam:

- O diálogo é `fusion:RequestFile` nos três casos, **não `AskUser`** (ele existe
  como atributo e vem `nil` fora da página Fusion — ver `SpeakerSwitch.py`).
- **Cancelar nunca é erro**: cai no que valia antes (o Title padrão, nenhum
  preset, e — na pergunta 3 — nada, que aí sim para com uma mensagem). O log diz
  qual foi usado; sem isso "cancelei e veio outra coisa" vira bug.
- As respostas ficam em `giautosubs\_giescolhas.txt` só para o diálogo **abrir
  no lugar certo** na próxima vez. É conveniência: apagar o arquivo não muda
  nada além disso.
- As três respostas viajam na tabela `respostas` entre as duas passadas do
  `main` — sem isso, a segunda passada (a que roda depois de o template ser
  atualizado) reabriria os três diálogos.
- A pergunta 1 passou a acontecer **também com um único Title instalado**. Antes
  o script só perguntava com dois ou mais ("um diálogo de um botão só é um passo
  a mais entre você e as legendas"), e o preço era não ter onde dizer "hoje quero
  o outro".

O preset entra em `dados.controles` (é por ali que o macro escreve o estilo,
via `SetInputValues`), com **uma exceção**: `Offset{n}` também é copiado para
`dados.inputs._offset{n}`, porque esses o script escreve direto, num passo
*posterior* ao preset — um offset que ficasse só nos controles seria reescrito
pelo estilo logo em seguida, calado. É `fundir_preset`, e o `testes.lua` cobre
exatamente isso.

> **Esse teste está FALHANDO** contra um `legendas.lua` de verdade (não contra o
> `amostra_legendas.lua`, onde passa): `Offset3 from the config was overwritten
> by the style's own offset`. Reproduz igual num `legendas.lua` gerado **antes**
> do macro 22, então não veio de lá — é anterior, e continua em aberto (§8).

---

### Duas abas, e o Fill Color voltando a mandar (macro 22)

Quatro queixas na mesma frase, e três delas com a **mesma raiz**: o array de
estilo por caractere vence os inputs (§2 do `MACRO.md`), e o que o array trazia
era o que foi congelado em `GiCamadas` quando o clipe nasceu — não o que o
Inspector mostrava.

| queixa | o que estava acontecendo |
|---|---|
| "o Fill Color está bugado, variando de legenda a legenda" | quem pintava o elemento 1 era a **cor do falante**, escrita clipe a clipe; o controle `Fill Color` ficava parado no valor do estilo e mexer nele não mudava um pixel |
| "desmarcar Spoken Word > Enabled não muda nada" | o checkbox só trocava **de onde a cor ativa vinha**; desmarcado, ela voltava ao `cor_ativa` gravado — que era exatamente o amarelo do destaque |
| "mudei `vale` para `valendo` e só `vale` recebeu a cor" | `GiWordTiming` endereça o texto por **posição de caractere**, e editar no Inspector não movia essas posições |
| "Apply Style fica longe do que eu acabei de ajustar" | um botão só, no topo de uma lista de 40 controles |

**A cor por falante saiu do projeto** (decisão do usuário, perguntada e
respondida). Ela era a causa da primeira queixa e o motivo pelo qual o elemento 1
ficava fora do `CONTROLE_DA_CAMADA`: a cor base dele "pertencia" ao falante, não
ao Inspector. Sem ela, o elemento 1 lê como todos os outros — base do
`Fill Color`, ativa do `Word Color` enquanto `Spoken Word > Enabled` estiver
marcado, e **a mesma base** quando não estiver, que é literalmente "a palavra
falada não muda de cor". Os falantes continuam decidindo **track**;
`falantes[].cor` no `estilos.json` deixou de ser lido.

O realinhamento do texto editado é o que dava para fazer honestamente: enquanto
o número de **palavras** não muda, cada uma continua começando no mesmo frame e o
único dado defasado é onde ela começa e acaba no texto — o `GiApplyText` refaz a
repartição com a mesma regra do pipeline (o espaço separador pertence à palavra
seguinte). Palavra a mais ou a menos continua sendo caso de rodar o script, agora
**com aviso** em vez de um destaque errando calado.

E o Inspector virou **duas abas**:

```
Text     Text · [Actions] · Animation · Fill · Outline · Config
Extras   Text Box · Bubble · Spoken Word · Box Shadow · Shadow / Glow
```

Duas coisas que essa mudança ensinou:

- **A aba é uma camada à parte.** `Page = "Extras"` num InstanceInput só diz onde
  o controle mora; sem um `Extras = ControlPage {}` no `UserControls` do macro,
  todo mundo cai calado na primeira página visível. É a mesma regra pela qual a
  aba "Style" continuava aparecendo depois de esvaziada — lida ao contrário.
- **Ordem e aba são a mesma decisão.** O Inspector segue a ordem do bloco
  `Inputs`, e um `LabelControl` engole os controles *seguintes*. Isso estava
  repartido em três inserções posicionais ("depois do grupo Text", "depois de
  `Style`", "no fim") e a ordem final só dava para saber lendo as três. Agora é
  uma lista só, o `LAYOUT` do `gerar_macro.py`, e um `_reordenar_inputs` que
  reclama de quem não estiver nela.

Cada grupo de atributos ganhou um **`Apply Style` de rodapé** — instância do
mesmo botão (`Source = "ApplyStyle"`), não um botão novo: um segundo corpo de
código seria um segundo lugar para divergir. O grupo `Actions` continua abrindo a
aba Text, e `Apply Style to All Captions` / `Generate Caption Style` ficam só lá
— repetir em nove lugares um botão que mexe em **todas** as legendas é pedir para
ele ser clicado sem querer.

### O `Level` invertido, finalmente (ainda no macro 22)

Estava em "Em aberto" desde 27/08. A lista real do Text+, lida do `PROPERTY
DUMP`, conta a partir de **zero** — igual ao `ElementShape`, onde `Border Fill =
2` é o valor que de fato desenha a caixa:

| valor | Text+ | o projeto chamava de |
|---|---|---|
| 0 | Text (a legenda inteira) | *não existia um nome* |
| 1 | Line | `caractere` ✗ |
| 2 | Word | `palavra` ✓ |
| 3 | Character | `linha` ✗ |

O que o trouxe à tona: um estilo exportado pelo Inspector trazia
`TextBoxLevel 0` — uma caixa envolvendo a frase. Não havia nome para o 0 no
`NIVEIS`, então o `_NIVEIS_INV.get(0, "palavra")` caiu no *fallback* e a
reimportação virou uma caixa **por palavra**. Terceira vez nesta série em que um
`.get(chave, padrão)` sobre uma tabela incompleta troca um valor sem dizer nada.

Corrigido nos dois lugares ao mesmo tempo, como o item pedia: `NIVEIS` /
`_NIVEIS_INV` no `giautosubs.py` e os `CCS_AddString` (`_NIVEIS`) no
`gerar_macro.py`. O `_NIVEIS_INV` passou a ser escrito à mão — a compreensão de
dicionário devolvia `"tudo"` para o 0, e o nome canônico é `"texto"`.

**O que muda em estilo que já existe:** `nivel: "palavra"` continua igual (era o
único valor em uso, e acertava por coincidência). `nivel: "linha"` desenhava por
**letra** e agora desenha por linha — só o `batata_shorts` usa, com a caixa
desligada. O default do combo `TextBoxLevel` no macro foi de `3` (Character) para
`1` (Line).

---

### A legenda que não cabe vira duas (31/08/2026, só no Python)

Não é mudança de macro: **não precisa reinstalar, reiniciar nem recriar clipe.**
Basta rodar o `giautosubs.py` de novo e recriar as legendas.

O `quebrar` do `estilo_legenda.py` sempre teve uma saída de emergência declarada
em comentário — *"texto que não cabe estoura o limite de propósito: melhor uma
linha longa do que legenda sumida"*. Ela nunca foi medida. No `Corte_Mosquito`,
com `quebra = 20 chars / 2 linhas`, **25 das 156 legendas estouravam a largura**,
e a pior tinha uma linha de **69 caracteres** ("...chegar e soltar um mosquito da
dengue na casa de alguém que te beija.") — num vertical 1080, saindo da tela
pelos dois lados. O `quebrar` não tinha como fazer melhor: partir o texto exige
partir o **tempo** junto, e ele não tem o tempo na mão.

Agora tem quem tenha. `repartir()`, no `giautosubs.py`, corta em fronteira de
palavra e reparte o tempo por palavra junto. `quebra.max_chars` passou de 20 para
**25** — a largura de `"ELES SÓ SÃO MEIO TÍMIDOS."`, que por acaso é a primeira
linha da legenda de 69. Resultado medido no mesmo corte: **156 → 175 legendas,
19 partidas, 0 estourando a largura**, e os `testes.lua` seguem dizendo
`0 index errors` contra o arquivo novo.

Três decisões que valem mais que o código:

- **As pontas ficam com o tempo ORIGINAL do segmento**, não com o da primeira/
  última palavra. O Whisper abre o segmento antes da primeira palavra e o estica
  depois da última; encolher aqui faria a legenda piscar num lugar onde ela não
  piscava antes.
- **O corte cai onde uma palavra começa**, lido do `words` — nunca no meio de uma
  palavra, nem no texto nem no tempo. Sem `words` (rodada `--sem-words`) o tempo
  é estimado por comprimento, que é a única coisa honesta que dá pra fazer.
- **O token que ABRE um pedaço perde o espaço separador.** O invariante do
  projeto é que o texto da legenda é, caractere a caractere, a concatenação dos
  tokens — é assim que o `GiWordTiming` endereça a palavra falada. Se o espaço
  ficasse, a quebra de linha o apagaria depois e todos os índices andariam um
  caractere, acendendo a palavra errada no vídeo inteiro, calado.

> **01/09/2026 — uma linha só** (`max_linhas = 1`), a pedido. 156 → **293
> legendas**, 89 partidas, e o array do corte em **9.216** entradas (era 47.328
> antes de tudo). A pior legenda passou a ter 5 palavras: **20 entradas por
> frame**, contra 136 no começo.
>
> **O preço, e ele é editorial:** legendas com 3+ palavras em menos de 0,35 s
> foram de **3 para 16**, e a pior tem **0,02 s** — um frame. A causa não é a
> repartição, é o Whisper: nesses segmentos ele carimba várias palavras no mesmo
> instante, e a fronteira do pedaço sai do `end` da última palavra do grupo. Com
> capacidade de 38 caracteres isso quase não aparecia; com 19 aparece. O conserto
> sem efeito colateral existe (quando a fronteira por palavra der um pedaço
> abaixo de um piso, calcular a fronteira **proporcional ao comprimento** dentro
> do vão do segmento), mas o piso é escolha de quem edita — não foi feito.
>
> **Um bug meu que essa mudança expôs**, e que a guarda de dessincronia pegou:
> num pedaço de **um token só**, a aparagem das pontas estava escrita como
> `toks[0], toks[-1] = toks[0].lstrip(), toks[-1].rstrip()`. Os dois índices são
> o mesmo elemento, o lado direito é avaliado antes, e a segunda atribuição
> desfaz a primeira — o token voltava com o espaço da frente e o texto ficava um
> caractere fora dos tokens, em 17 legendas. Pedaço de um token só era raro com
> duas linhas e virou comum com uma. A regra estava escrita **duas vezes**; agora
> é uma função só (`_tokens_do`), e tem teste.

> **01/09/2026 — o limite virou 19**, a largura de `"que já amarrou uma."` (o
> usuário deu a nova frase de referência). No mesmo corte: **156 → 191 legendas,
> 31 partidas, 0 estourando**. Linha mais curta é menos palavra por legenda, e o
> array cresce com o quadrado das palavras — então encurtar a linha alivia o
> playback junto: a pior legenda caiu de **44 → 32** entradas por frame.

E o `montar` passou a **reclamar**, que é a regra da casa para transformação de
texto: diz quantas legendas foram partidas, quantas ainda estouram (uma palavra
sozinha maior que a linha — partir não resolve) e quantas deixaram de casar com
os próprios tokens. Coberto por `tests\quebra.py` (offline, sem servidor e sem
Resolve).

> `estilo_de_controles` (o *Generate Caption Style*) passou a escrever
> `quebra: 25/2` explícito. Não existe controle de quebra no Inspector — ela
> acontece antes de o clipe existir —, então a exportação não tem de onde ler; e
> um estilo **sem** `quebra` cairia no mesmo 25/2 calado. Escrito é melhor que
> calado.

### A pergunta que faltava: o que fazer com a rodada anterior (31/08/2026)

Reclamação do usuário, e ele tinha razão: **`CONFLITO` nunca foi pergunta.** Era
uma constante no topo do `GiAutoSubs.lua`, fixa em `"substituir"` — e
`"substituir"` chama `timeline:DeleteClips`. Ou seja: a **única decisão
destrutiva da rodada** era a única que ninguém tomava. Você descobria lendo
`conflict mode substituir` no resumo, com as legendas antigas já apagadas.

Agora ele pergunta — **só quando há o que perguntar**. Com a timeline limpa a
resposta não muda nada, e um diálogo que não muda nada é um passo a mais entre
você e as legendas (é o mesmo argumento com que a pergunta 1 justificava não
existir quando só havia um Title). O diálogo diz quantas achou e em que tracks.

**O menu é feito de arquivos, e isso é de propósito.** O único diálogo que
comprovadamente funciona daqui é o `fusion:RequestFile` — o `AskUser` vem `nil`
fora da página Fusion, e este script roda em Workspace > Scripts, da página Edit.
As perguntas 1 e 2 já são exatamente isso (escolha o `.setting`, escolha o
preset); aqui as opções não eram arquivos, então passaram a ser: a pasta
`giautosubs\conflito\` é semeada a cada rodada com

```
1 - REPLACE - delete the previous run.txt
2 - KEEP - only fill in what is missing.txt
3 - NEW TRACK - stack this run above the old one.txt
```

O número que abre o nome é o que a leitura casa, **ancorado no nome do arquivo**
e não no caminho: procurar "dígito seguido de tracinho" no caminho inteiro
casaria com uma pasta `my-stuff` antes de chegar no arquivo, e a escolha viraria
outra sem uma linha de aviso — o quarto `match` silencioso desta série se tivesse
passado.

> **O caminho mais bonito não foi tomado, e é uma decisão, não esquecimento.**
> `fu.UIManager` faria um diálogo de verdade, com três botões — e não é a
> armadilha do tkinter registrada nas gotchas (aquilo é o event loop do Tk
> brigando com o Qt no mesmo processo; o UIManager *é* o Qt do Fusion). O
> problema é que eu não tenho como testá-lo: sem licença Studio não há scripting
> externo, e um `disp:RunLoop()` que não consiga abrir a janela **trava o
> Resolve**. Entre um diálogo feio que funciona e um bonito que pode congelar o
> editor no meio de uma rodada, ficou o feio. Se for testado dentro do Resolve,
> a troca é local: só o corpo do `escolher_conflito`.

Três coisas que o conserto obrigou a acertar:

- **A resposta viaja no `respostas`**, como as outras três. O `main` roda duas
  vezes quando o template precisa ser atualizado; sem isso a segunda passada
  reabriria o diálogo — e agora contando as legendas que a primeira acabou de
  criar.
- **`CONFLITO` continua existindo** como o padrão de quando não há o que
  perguntar e de quando se cancela, e ganhou o escape `CONFLITO_FIXO`, irmão do
  `ESTILO_FIXO`/`PRESET_FIXO`.
- **O resumo passou a dizer de onde veio a resposta**: `substituir (you chose
  it)`, `substituir (default - the dialog was cancelled or unavailable)` ou
  `substituir (nothing from a previous run was here)`. Sem isso, "cancelei e ele
  apagou mesmo assim" continuaria sem explicação no log.

`MODO` e `TRACK_UNICA` continuam constantes pelo mesmo padrão — não foram
mexidos porque não foram pedidos, mas são a mesma classe de decisão escondida.

### O `Spoken Word` desligado por padrão, e o preset alcançando as camadas (31/08/2026)

**O que ele é:** a **cor da letra na palavra falada** — o elemento 1 (fill). Não
é a bolha. São dois destaques independentes, e o `capcut_bolha`/`TikTokNovo`
usavam só a bolha; o `Spoken Word` estava ligado no estilo e desligado no preset.

**Por que ele "continuava preenchendo mesmo estando errado".** Ordem de escrita,
não lógica. Na criação de cada clipe:

```
passo 5   aplicar_preset(...) → SetInputValues(..., spline = false)
          escreve os CONTROLES (WordFillEnabled = 0) e manda NÃO refazer o array
passo 8   montar_keyframes(tempos, dados.destaque, fps)
          escreve o ARRAY a partir do ESTILO — que dizia amarelo
```

O array é escrito depois e o array vence os inputs (§2). O clipe nascia com o
Inspector dizendo *off* e o spline pintando amarelo, até alguém clicar em Apply
Style — que aí sim roda o `GiRebuildHighlight` lendo o checkbox.

A raiz é que **o preset não tinha caminho até as camadas**: o `fundir_preset`
copiava tudo para `dados.controles`, e o array vem de `dados.destaque.camadas`.
É a **mesma forma da exceção do `Offset{n}`** que já estava documentada aqui
("o script os escreve num passo posterior e sobrescreveriam o preset calado") —
segunda ocorrência do mesmo padrão, e agora ele tem nome: *o que o passo 8
reescreve não pode ficar só nos controles.*

O conserto, nos dois lados:

- **Padrão.** `destaque.fill.ativo` passou a `false` no `batata_shorts` e no
  `capcut_bolha`. A **cor continua guardada** (`#FFE900`), então marcar
  `Spoken Word > Enabled` no Inspector e clicar em Apply Style acende no amarelo
  certo, sem regerar nada — o `GiRebuildHighlight` já sabia **criar** a camada do
  fill quando ela não existe (foi feito no macro 13).
- **Caminho.** `fundir_preset` passou a mexer nas camadas: uma camada cujo
  controle de liga/desliga o preset zerou é **removida** (`CONTROLE_QUE_LIGA`:
  1 → `WordFillEnabled`, 4 → `BubbleEnabled`, 5 → `BoxShadowOnHighlight`), e
  `WordFillEnabled = 1` **cria** a do elemento 1 se faltar. Criar só vale para o
  1 de propósito: é a única sem geometria para montar — a mesma regra do macro.

Isso obrigou a acertar um `nil` latente no passo 8: `montar_keyframes` recebia
`dados.destaque` sem checagem, e um estilo sem camada nenhuma (agora alcançável
por preset) quebraria ali — ou, pior, devolveria `{}` e escreveria um **spline
vazio**, que é o `cannot get Parameter` da §5. Agora o passo 8 só chama
`montar_keyframes` com camadas de verdade e cai no `keyframes_vazios()` caso
contrário. O contador `comDestaque` passou a olhar o array, não o `tempos`.

**O ganho medido**, no `Corte_Mosquito`: de 2 camadas para 1 — array do corte de
**34.816 → 17.408** entradas, e a pior legenda de 2 linhas de **88 → 44** por
frame. Somado com a repartição, a pior legenda saiu de **136 → 44**, três vezes
menos por frame.

> **A opção não custa nada a quem não usa.** A camada só existe no array se
> estiver em `GiCamadas`; desligada, ela contribui zero entradas. O checkbox é um
> input lido uma vez por rebuild, não por palavra. O custo aparece **só na
> legenda em que você ligar**, e lá ele dobra o array daquele clipe.

Coberto por seis asserções novas no `testes.lua` (`fundir_preset`), incluindo a
que garante que o `Offset{n}` continua chegando em `dados.inputs._offset{n}`.

> Um fio solto que essa cobertura expôs: o `Offset3` **chega** ao
> `dados.inputs._offset3` (o teste novo prova). Então a falha antiga
> `Offset3 from the config was overwritten` é **depois** disso — no passo 6, ou
> na hora em que `offsets` é capturado. Continua aberta, mas o lado do
> `fundir_preset` está descartado.

### "USE THESE": rodar a partir da track que já existe (01/09/2026)

Quarta opção do diálogo de conflito. Não cria e não apaga nada: **restiliza as
legendas que já estão na timeline**, mantendo posição, aparas, o texto corrigido
à mão e o tempo por palavra de cada clipe.

Metade disso já existia como `MODO = "atualizar"` — escondido numa constante, e
com um defeito no pareamento. As três decisões foram perguntadas ao usuário:

| pergunta | resposta |
|---|---|
| o que fazer com o tempo por palavra (o bubble) | **manter o do clipe, não tocar** |
| como casar clipe com segmento | **por frame de início** |
| legenda do arquivo sem clipe na track | **ignorar, mas listar no log** |

**O pareamento por ordem era o defeito, e agora é por frame.** Primeira com
primeira, segunda com segunda: bastava a contagem divergir — e ela diverge assim
que uma legenda é repartida em duas — para tudo depois daquele ponto casar com o
vizinho. Texto de uma legenda no clipe da outra, calado. O aviso existia, mas
*avisar não é parear*. Agora cada clipe procura o segmento que começa onde ele
começa, com tolerância de `fps/4` (~250 ms); quem não achar par fica de fora dos
dois lados, e o log diz quais. Isso sobrevive a clipe movido, clipe aparado e
contagem diferente — e vale também para o `MODO = "atualizar"` de sempre, porque
era bug nos dois.

**"Não tocar" tem duas leituras, e só uma serve.** O que fica intocado é o
`GiWordTiming` — é ele que sincroniza a bolha. O **array** é refeito, e tem que
ser: é lá que mora a cor, e sem refazê-lo uma mudança de aparência não chegaria à
tela (você teria que clicar Apply Style em 156 clipes). Como o macro reconstrói o
array a partir do `GiWordTiming` **do próprio clipe**, a sincronia sai idêntica.
Daí a inversão: no caminho normal o script escreve o array e manda o macro pular
(`spline = false`); aqui o passo 8 não escreve nada e o macro é quem refaz
(`aplicar_preset(..., manterTempos)`).

> **O que este modo NÃO conserta:** o `GiCamadas` congelado no clipe. Uma camada
> que deixou de ser usada (o `Spoken Word`, agora desligado por padrão) continua
> na lista e continua custando 4 entradas por palavra — inerte na tela, viva no
> array. Aparência este modo conserta; **performance, não**. Para o ganho de
> performance é preciso recriar.

Duas coisas que a implementação obrigou:

- **A pergunta subiu para antes do passo 3.** A opção 4 não usa o template do
  Media Pool, e o passo 3 pode reimportar o bin, trocar o item do pool e até
  reiniciar o `main` inteiro. Perguntar depois seria pagar o passo caro para
  descobrir que ele não era necessário. O `conferir_conflitos` roda **duas
  vezes** de propósito: cedo, só para decidir o `MODO`; e no passo 4, para
  decidir o que apagar — porque entre um e outro o passo 3 pode ter inserido o
  Title na timeline para semear o pool, e esse clipe também carrega o carimbo.
- **`MODO` virou `modo`, local do `main`**, carregado no `respostas` entre as
  duas passadas. A constante continua sendo o padrão.

**O fixture do teste é que estava mentindo.** O Resolve falso inventava o frame
de início de cada legenda (`k * 100`), e o pareamento por ordem passava sem olhar
frame nenhum — o bloco do `contornar` já montava os frames de verdade, o do
`atualizar` não. Corrigido, e com um teste novo que remove a **primeira** legenda
da timeline: por ordem, tudo deslocaria; por frame, **174 de 174** casaram e cada
clipe ficou com o seu próprio texto.

### Corrigir o texto acrescentando uma palavra (01/09/2026)

`"i love potato"` → `"i love the potato"`. O `GiWordTiming` endereça por
**índice de caractere**: `" potato"` ocupava 6..12, e no texto novo 6..12 é
`" the po"` — a bolha acenderia no meio da palavra errada, no vídeo inteiro. O
`GiApplyText` do macro só realinha enquanto o **número de palavras não muda**
(`"vale"` → `"valendo"` funciona); mudou, ele avisava e reconstruía com os
índices velhos assim mesmo.

`refazer_tempos` (no `GiAutoSubs.lua`, **sem macro**) reparte o texto atual do
clipe em palavras e dá a cada uma um frame por **interpolação linear sobre os
frames já gravados**. A primeira e a última palavra ficam exatamente onde
estavam; as do meio se redistribuem. É estimativa, e é declarada como tal — o
tempo da palavra nova não existe em lugar nenhum. Em troca a bolha anda na ordem
certa e nos caracteres certos.

Decisões que valem mais que o código:

- **Não usa a duração do clipe nem o segmento da transcrição.** Os frames
  gravados são o único dado que pertence ao clipe, e este é o modo que promete
  não re-sincronizar pela transcrição.
- **Roda antes do passo 5, não no 8.** Nesse modo quem reconstrói o array é o
  macro, chamado pelo `aplicar_preset`; consertar o `GiWordTiming` depois
  deixaria o array com o errado até o próximo Apply Style.
- **Só no `manterTempos`** (a opção *USE THESE*). O `atualizar` clássico
  re-sincroniza pela transcrição e já tem regra própria para texto editado — ele
  **desliga** o destaque ("melhor não animar do que animar errado"). São duas
  respostas para a mesma pergunta, e cada modo tem a sua.
- **Frames estritamente crescentes**, como no `montar_keyframes`: duas palavras
  no mesmo frame fazem uma nunca acender. Aqui é mais provável, porque a
  interpolação amontoa palavras quando o texto cresce muito.

O resumo passou a contar: `RE-TIMED n caption(s) had words added or removed by
hand`. Coberto no `testes.lua` com o caso exato, incluindo palavra a menos e o
caso "mesmo número de palavras → não é comigo, é do macro".

### Por que legenda grande trava no playback (medido em 31/08/2026)

Não é "legenda grande é pesada". É o **encoding do array de estilo por
caractere, que é quadrático no número de palavras**. O `montar_keyframes`
(`GiAutoSubs.lua`) escreve um keyframe por palavra, e *cada* keyframe descreve o
estado de **todas** as palavras: `palavras × camadas × 4` entradas. Com 2
camadas, no `Corte_Mosquito`:

| legenda | keyframes | entradas por FRAME | total |
|---|---|---|---|
| 2 palavras | 2 | 16 | 32 |
| 17 palavras (a de 88 caracteres) | 17 | **136** | **2312** |

A cada frame o Fusion reaplica 136 sobrescritas de estilo sobre 88 caracteres em
vez de 16 sobre 8. Partir as legendas já derrubou a pior de **136 → 88** entradas
por frame (e o total do corte de 47.328 → 34.816), mas o termo quadrático
continua lá.

**O corte seguinte está identificado e não foi feito.** O keyframe guarda estado
*absoluto*, e o estado base já mora nos inputs — então bastariam **duas faixas**:
uma `[0, fim]` apagando tudo e uma `[startIndex, endIndex]` acendendo a palavra
ativa. Isso deixa o array em `camadas × 4 × 2` entradas — **constante**, ~16 por
keyframe em vez de 136, independente do tamanho da legenda. O que falta é medir
dentro do Resolve se, em faixas sobrepostas do array do `StyledText`, **a entrada
posterior vence a anterior**. Se vencer, o custo por frame deixa de crescer com a
legenda.

Antes disso, o remédio barato é o do Resolve, não o nosso: **Playback > Render
Cache > Smart** — um Title do Fusion é recomposto a cada frame enquanto não
estiver em cache.

---

## 9. Os outros documentos

- **`MACRO.md`** — como o `.setting` funciona por dentro, a cadeia de
  precedência, a tabela de atributos do Text+, receita para criar controles
  novos, o custo de um callback (§6) e uma tabela sintoma → causa.
- **`DISTRIBUICAO.md`** — o que falta para virar script para outras pessoas.
- **`GiDiag.lua`** (em `Scripts/Utility`) — diagnóstico somente-leitura, para
  rodar dentro do Resolve antes de formular qualquer hipótese.

> **`GiWatch.lua` foi apagado** (macro 11). Era um laço de 1 s que vigiava o
> clipe sob o playhead e aplicava o estilo sozinho — muleta para o callback que
> não disparava. Com o callback fora e o botão funcionando, ele passaria a ser o
> que acabou de ser eliminado: um segundo caminho de aplicação, invisível e
> disparado sem ninguém pedir.
