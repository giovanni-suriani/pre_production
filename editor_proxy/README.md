# editor_proxy

O que roda **depois** do `pre_production` — e fora dele.

```
SpeakerSwitch.py    monta a timeline nova no DaVinci Resolve
```

Está fora de `src/` de propósito: nada aqui é servidor web. Este script roda
**dentro do Resolve** (Workspace → Scripts → Utility), no interpretador que o
Resolve embute, e não importa uma linha sequer do resto do projeto. Misturá-lo
com o `src/` sugeriria que o app o executa — ele não executa, e não pode: a
edição Free do Resolve não tem API de scripting externa.

---

## O que ele consome do pre_production

O `turns*.json` de um corte, em **tempo absoluto da mídia-fonte** — que é a
unidade que o próprio script documenta em `RANGE_START`/`RANGE_END`. O
`pre_production` grava sempre nessa base, então não há conversão a fazer no
meio do caminho.

Além do json, ele procura um `speaker_switch.json` na mesma pasta:

```json
{
  "turns": "…\\cortes\\corte_shorts1\\turnsManual.json",
  "name_to_track": { "Giovanni": 1, "Cupertino": 2, "Heitor": 3, "cut": 4 },
  "off_camera_names": ["no_name"],
  "range_start": 2610.0, "range_end": 4165.95,
  "fps": 60.0, "origin_frame": 156600
}
```

Se ele existir, o `NAME_TO_TRACK` e o `OFF_CAMERA_NAMES` daquele corte
substituem os dicionários fixos no topo do script.

**Por que isso importa:** o mapa de tracks é uma decisão *por corte* — num
short de duas pessoas a V3 nem existe —, mas vivia como constante no topo de um
script de mil linhas. Rodar dois cortes diferentes pedia editar o script no
meio do caminho, e esquecer disso produzia um corte errado sem nenhum aviso.
Agora a decisão é tomada na tela do corte (etapa 2) e lida daqui.

Sem o arquivo, o comportamento é exatamente o de antes.

---

## Instalar

O Resolve só executa scripts que estejam na pasta dele:

```
C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\
```

Copie o `SpeakerSwitch.py` para lá (Workspace → Scripts → SpeakerSwitch).
**Esta cópia e a de lá não se sincronizam sozinhas** — depois de mexer aqui,
copie de novo. É a mesma disciplina que o `scriptsPrimarios\` já pedia.

```powershell
Copy-Item .\SpeakerSwitch.py `
  "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\" -Force
```

---

## Rodar

1. Abra a timeline com os enquadramentos já feitos (V1…V4), **um clipe único
   por track**, cobrindo a gravação inteira.
2. Workspace → Scripts → Utility → **SpeakerSwitch**.
3. O diálogo de configurações abre. Aponte o `turns*.json` (botão
   **Procurar…**) e marque o que esta rodada deve fazer.
4. Confira, no Console, o mapa de tracks e o resumo das opções que ele imprime
   antes de montar.

Para o diálogo já abrir na pasta certa na primeira vez, preencha `PREPROD_CUT`
no topo do script com o caminho do corte.

### O diálogo de configurações

| campo | o que decide |
|---|---|
| Diarização | qual `turns*.json` monta o corte |
| Timeline nova | o nome (ganha `_2`, `_3`… se já existir) |
| Comps Fusion | exportar o comp de cada track-fonte e importar em cada clipe novo |
| Color grade | copiar os nodes da página Color (`CopyGrades`) |
| Áudio original | levar o áudio, span a span, nos mesmos frames do vídeo |
| Uma track de áudio por falante | só ajuda com microfone por pessoa — nesta gravação é mixagem única |
| Preencher buracos | cobre cabeça, cauda e vãos com a track base; sem isso, buraco = frame preto |
| Resolução | `1080x1920` para Shorts; **vazio mantém a da origem** |
| Encaixe do clipe | `scaleToCrop` (validado por readback), `scaleToFit`, ou vazio = herda da origem |
| Recorte início/fim | segundos absolutos na mídia; vazio = a timeline-fonte inteira |

**Por que um diálogo, e não constantes.** São as decisões que mudam *de uma
rodada para a outra* — “copiar os comps Fusion” e “copiar o grade” viviam sendo
desligados para isolar um problema e religados depois, editando um script de mil
linhas no meio do caminho. As constantes no topo continuam existindo: elas são o
**estado inicial** do diálogo.

O que **não** está lá é de propósito: `NAME_TO_TRACK` e `OFF_CAMERA_NAMES` (quem
fica em qual track) vêm do `speaker_switch.json` do corte, decidido na tela da
etapa 2. Oferecer os dois seria dar duas fontes para a mesma decisão.

A última escolha fica em **`_speakerswitch_opcoes.json`, na pasta do corte** —
não ao lado do script, porque a resposta certa muda por corte e porque o script
tem duas cópias (esta e a de `Scripts\Utility`), que discordariam.

O diálogo roda **num processo separado** (`python.exe` + tkinter), pelo mesmo
motivo do seletor de arquivo que já existia: tkinter dentro do Resolve põe dois
event loops (Qt e Tk) no mesmo processo e derruba o editor. E o `AskUser` do
Fusion não serve — ele existe como atributo e vem `None` fora da página Fusion,
que é o caso normal aqui. Sem `python.exe` externo, o script cai no caminho
antigo: pergunta só o arquivo, usa as opções gravadas e **imprime todas** no
Console.

---

## Duas armadilhas que continuam valendo

- **`MIN_SPAN_FRAMES = 2`.** Turno que vira menos de 2 frames o Resolve
  recusa; o `build_spans()` o absorve no vizinho e ele **some do corte final
  sem avisar**. A etapa 2 e o editor de turnos marcam esses casos como
  `curto` — vale olhar antes de rodar aqui.
- **A timeline de origem pode não começar no zero.** `clip_origin`
  (`GetLeftOffset`) é o frame absoluto onde o frame 0 dela cai. O
  `origin_frame` do corte é o valor que deveria bater com ele — se
  discordarem, os cortes saem deslocados.
