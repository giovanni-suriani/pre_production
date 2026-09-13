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
| **`Level` está trocado** — validado 27/08, não é mais suspeita | o dump mostra que os valores do Text+ são **0-based** (elemento 1, um *Text Fill*, lê `ElementShape=0`). A lista real do `Level` é `[Text, Line, Word, Character]` → `0=Text 1=Line 2=Word 3=Character`. O combo "Envolve" do macro declara `1=Caractere 2=Palavra 3=Linha`: **Caractere e Linha estão invertidos**. "Palavra" acerta por coincidência, e é o único que o estilo usa — por isso nunca apareceu. Corrigir `NIVEIS` no `giautosubs.py` e os `CCS_AddString` no `gerar_macro.py` **juntos**, senão o Inspector e o script discordam |
| O ganho de velocidade da §5.5 não foi medido depois do conserto | o log traz os números; comparar antes/depois é o próximo passo |
| Reinício do Resolve + recriar clipes a cada mudança de macro | não tem contorno; ver §6, "o laço de edição" |
| A exportação do `.drb` (§8c) nunca rodou dentro do Resolve | `ExportFolder` / `CopyClips` / `DeleteFolders` estão testados contra o Resolve falso, não contra o de verdade. Se a build recusar algum deles, o script diz e segue — o passo manual continua valendo |
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

### O botão "Display Config"

Grupo `Config`, no fim do Inspector — é ferramenta, não estilo: você não passa
por ele ajustando uma legenda, você vai até ele quando quer guardar ou mandar a
configuração.

Ele imprime no Console e grava em `giautosubs\_giconfig.txt` (o Console não
deixa copiar ~60 linhas: elas rolam para fora antes). Lê pelo mesmo
`GetInputValues`/`InputKeys` que o script usa — então um controle novo aparece
no dump sozinho, sem lista para manter em dia — e imprime junto a **versão do
macro dentro daquele clipe** e o texto original guardado, que são as duas coisas
que explicam a maioria dos "não funcionou".

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
