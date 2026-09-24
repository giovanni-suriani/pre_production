# pre_production

Tudo que acontece **antes** de abrir o DaVinci Resolve, numa tela só.

```
run.bat            → http://127.0.0.1:8740
```

Na primeira execução o `run.bat` cria o `.venv` e instala as dependências.
Para parar: `Ctrl+C` na janela do servidor.

---

## As três etapas

| rota | etapa | o que faz | o que sai |
|---|---|---|---|
| `/` | **ProjectEditor** | escolhe o vídeo, dá nome, lista quem está na mesa | `project.json` + `media\<projeto>.wav` |
| `/cortes` | **CutsEditor** | marca o trecho na onda, diz qual track é de quem, escolhe o método e roda | `corte.json` + `audio.wav` + `turns*.json` |
| `/turnos` | **turnsEditor** | corrige os turnos ouvindo, lendo e arrastando | `turnsManual.json` |

Depois disso: `editor_proxy\SpeakerSwitch.py`, dentro do Resolve.

A barra de cima segue essa ordem, e etapa que ainda não tem o que mostrar fica
apagada. Não é enfeite: sem wav não há o que fatiar, e sem diarização não há
turno para corrigir.

---

## Um exemplo completo

Números reais, de uma passada de ponta a ponta no `EpisodioPiloto` — um corte
de 43:30 a 45:30.

### Etapa 1 — `project.json`

Vídeo escolhido, três participantes com suas cadeiras. O `ffprobe` lê a
especificação; o wav sai em ~50 s.

```json
{
  "slug": "EpisodioPiloto",
  "source_video": "D:\\CanalYtbe\\BatataQuente\\Raw_videos\\EpisodioPiloto.mkv",
  "fps": 60.0,
  "duration": 4165.9306875,
  "participants": [
    { "name": "Giovanni",  "seat": "left"   },
    { "name": "Cupertino", "seat": "center" },
    { "name": "Heitor",    "seat": "right"  }
  ],
  "off_camera": ["no_name"],
  "audio": "media/EpisodioPiloto.wav",
  "audio_info": { "sample_rate": 16000, "channels": 1, "duration": 4165.9306875 },
  "status": "pronto"
}
```

O wav gerado tem **o mesmo SHA-256** do `sourceMedia\EpisodioPiloto_full.wav`
que já existia — mesma receita de extração, byte a byte.

### Etapa 2a — `corte.json`

Trecho marcado na onda: 43:30 → 45:30.

```json
{
  "name": "corte_shorts1",
  "start": 2610.0, "end": 2730.0, "duration": 120.0,
  "fps": 60.0,
  "origin_frame": 156600,
  "time_base": "absolute",
  "audio": "audio.wav",
  "audio_offset": 2610.0,
  "track_map": { "Giovanni": 1, "Cupertino": 2, "Heitor": 3, "cut": 4 },
  "off_camera": ["no_name"],
  "speakers": 4,
  "status": "sem diarização"
}
```

`origin_frame: 156600` é `round(2610 × 60)` — o mesmo `clip_origin`
(`GetLeftOffset`) que a timeline-fonte já mostrava no Resolve. O `track_map`
saiu das cadeiras sozinho; `speakers: 4` é 3 pessoas + a voz fora de quadro.

### Etapa 2b — a rodada

`pyannote 3.1 (v3)`, 27 s na GPU. Três arquivos:

```
turnsPyannote_v3.json             16 turnos   2610.00 → 2730.00   ← canônico, ABSOLUTO
turnsPyannote_v3.raw.json         16 turnos      0.00 →  120.00   ← como o script cuspiu
turnsPyannote_v3.segmentos.json   75 turnos      1.28 →  119.98   ← antes da suavização
speaker_samples\                  12 wavs                          ← 3 amostras por voz
```

O mesmo primeiro turno nos dois primeiros:

```json
  raw:  { "start":    0.0, "end":    7.06667, "speaker": "SPEAKER_00" }
  json: { "start": 2610.0, "end": 2617.06667, "speaker": "SPEAKER_00" }
```

Repare no terceiro arquivo: 75 turnos com `3 curtos, 15 sobrepõem, 37 buracos`.
É a saída bruta do pyannote — a suavização da v3 é o que transforma isso em 16
planos contínuos, sem aviso nenhum. Vale olhar quando o corte sair estranho.

E a entrada gravada em `runs[]`:

```json
{
  "method": "pyannote_v3",
  "out": "turnsPyannote_v3.json",
  "raw": "turnsPyannote_v3.raw.json",
  "offset_applied": 2610.0,
  "seconds": 26.7, "turns": 16,
  "labels": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02", "SPEAKER_03"],
  "issues": {},
  "segments_raw": "turnsPyannote_v3.segmentos.json"
}
```

### Etapa 2c — quem é quem

Ouvindo as amostras: `SPEAKER_03`→Giovanni, `01`→Cupertino, `00`→Heitor,
`02`→no_name. Um clique renomeia os 16 turnos e **troca a chave** de `speaker`
para `name`, que é o que o SpeakerSwitch lê:

```json
{ "changed": 16, "backup": "turnsPyannote_v3.20260825-163808.bak.json", "label_key": "name" }
```

```json
 { "start": 2610.00000, "end": 2617.06667, "name": "Heitor"    },
 { "start": 2617.06667, "end": 2631.00000, "name": "Cupertino" },
 { "start": 2631.00000, "end": 2634.76667, "name": "Giovanni"  },
 { "start": 2634.76667, "end": 2637.30000, "name": "no_name"   }
```

Rodando também o Whisper (`small`, 49 s) saem 68 trechos de texto, já em tempo
absoluto — é o que enche a coluna “o que foi dito”.

### Etapa 3 — o que o editor recebe

```json
{
  "results_dir": "…\\cortes\\corte_shorts1",
  "fps": 60.0,
  "min_span_frames": 2,
  "audio_file": "audio.wav",
  "audio_offset": 2610.0,
  "transcript_file": "turnsWhisper.json",
  "transcript_offset": 0.0,
  "speaker_colors": { "Giovanni": "#5b9cf8", "Cupertino": "#f2a341",
                      "Heitor": "#4ecb8f", "no_name": "#6b7280", "cut": "#a78bfa" },
  "speaker_order": ["Giovanni","Cupertino","Heitor","no_name","cut"],
  "off_camera_names": ["no_name"]
}
```

Nada disso foi digitado: o offset é o início do corte, o fps veio do arquivo,
as cores e a ordem das teclas `1`–`5` vieram dos participantes. Na tela: relógio
em `00:00.000` com `mídia 43:30.000` embaixo, e o rodapé dizendo
**0 curtos · 0 sobrepõem · 0 buracos**.

### Depois — `speaker_switch.json`

```json
{
  "turns": "…\\cortes\\corte_shorts1\\turnsPyannote_v3.json",
  "time_base": "absolute",
  "name_to_track": { "Giovanni": 1, "Cupertino": 2, "Heitor": 3, "cut": 4 },
  "off_camera_names": ["no_name"],
  "range_start": 2610.0, "range_end": 2730.0,
  "fps": 60.0, "origin_frame": 156600
}
```

O `editor_proxy\SpeakerSwitch.py` lê esse arquivo e imprime o mapa antes de
montar a timeline.

---

## O problema que este projeto resolve

O pipeline funcionava, mas espalhado: um script para diarizar, outro para
nomear, um editor para corrigir, e **um monte de decisão morando na cabeça de
quem rodava**. Três dessas decisões eram armadilha:

**1. Duas bases de tempo circulando sem etiqueta.** `turnsPyannote4.json`
começava em 1.13 s (relativo ao corte de 43:30) e `turnsGemini_3.5_Chunks.json`
em 2610 s (absoluto, do início do episódio). Mesmo conteúdo, eixos diferentes, e
nada no arquivo dizendo qual era qual.

Aqui a ambiguidade não chega a existir. Quem roda a diarização num wav fatiado
**sabe** quanto vale o offset — é o início do corte. Então:

- a saída crua do script fica preservada em `turnsXxx.raw.json`, como ele
  cuspiu;
- o arquivo canônico `turnsXxx.json` é escrito **sempre em tempo absoluto da
  mídia-fonte** — a unidade que o próprio `SpeakerSwitch.py` documenta em
  `RANGE_START`/`RANGE_END`;
- o `corte.json` grava `time_base: "absolute"` e `audio_offset`, em vez de
  deixar isso subentendido.

Uma base só, escrita, derivada em vez de adivinhada.

**2. O mapa de tracks era uma constante no topo de um script de mil linhas.**
`NAME_TO_TRACK` é uma decisão *por corte* — num short de duas pessoas a V3 nem
existe. Rodar dois cortes diferentes pedia editar o `SpeakerSwitch.py` no meio
do caminho, e esquecer disso produzia um corte errado sem nenhum aviso. Agora a
decisão é tomada na tela do corte e gravada num `speaker_switch.json` que o
script lê.

**3. Descobrir tarde que faltava uma chave.** Uma diarização do Gemini em
pedaços leva vinte e tantos minutos. Descobrir no fim que faltava o `HF_TOKEN`,
ou que o modelo tinha estourado a cota, é caro. A lista de métodos mostra
**antes** o que falta para cada um, e a tela de trabalho em curso deixa o log
visível o tempo todo — é lá que essas coisas aparecem.

---

## Estrutura

```
pre_production\
  run.bat              sobe o servidor (cria o venv na primeira vez)
  config.json          caminhos, interpretadores, preferências (criado no 1º boot)
  .env                 opcional: HF_TOKEN (veja "chaves" abaixo)

  src\                 o app
    app.py             as rotas e a API
    config.py          caminhos, detecção do Python de diarização, .env
    projects.py        os manifestos project.json / corte.json
    media.py           ffprobe, ffmpeg, waveform
    jobs.py            trabalhos longos em segundo plano, com log e progresso
    methods.py         registro dos métodos de diarização (dados, não código)
    turns.py           ler/gravar turns*.json e converter a base de tempo
    timecode.py        segundos ↔ MM:SS.mmm ↔ frames (roda como autoteste)
    static\            as três páginas; app.js e style.css são cópias do turnsEditor

  editor_proxy\         o que roda DEPOIS, e fora daqui
    SpeakerSwitch.py   monta a timeline nova, dentro do Resolve
    README.md

  tests\               dois testes que dirigem o app de verdade
  projects\            os dados (uma pasta por projeto)
  .cache\              waveforms pré-calculadas — descartável
```

E, dentro de `projects\`:

```
projects\<projeto>\
  project.json                   fonte, wav, participantes, fps
  media\<projeto>.wav            áudio extraído, 16 kHz mono
  cortes\corte_shorts1\
    corte.json                   trecho, offsets, mapa de tracks, rodadas
    audio.wav                    o trecho fatiado (começa no zero)
    corte_shorts1_137frames.mkv  trecho de vídeo remuxado; 137 = os frames
                                 de offset (keyframe) a aparar no Resolve
    turnsPyannote_v3.json           saída canônica, em tempo ABSOLUTO
    turnsPyannote_v3.raw.json       a saída do script, como ele cuspiu (relativa)
    turnsPyannote_v3.segmentos.json os segmentos crus, antes da suavização
    speaker_samples\             amostras por voz, para descobrir quem é quem
    speaker_switch.json          o que o editor_proxy lê
```

Manifesto e não banco de dados de propósito: o que importa aqui são arquivos que
outros programas — o Resolve, os scripts, você — vão abrir. Um json ao lado dos
arquivos continua legível se este app sumir.

---

## Etapa 1 — Projeto

O vídeo é escolhido **por caminho**, não por upload: o episódio tem 3 GB e já
está no disco. A tela lista o que houver em `sources_dir` e o botão “Escolher no
disco…” abre o diálogo nativo do Windows — num processo separado, o mesmo truque
que o `SpeakerSwitch.py` já usa (tkinter no processo do servidor mistura event
loops e trava).

O `ffprobe` lê a especificação e o **fps vai para o manifesto**. Isso importa
mais do que parece: `int(round(segundos * fps))` é a mesma conta do
`SpeakerSwitch.py`, do `timecode.py` e do aviso de “turno curto demais”. Um
projeto de 30 fps com 60 gravado erraria todo corte pela metade, em silêncio.

O wav sai em **16 kHz mono PCM 16-bit** — o que o pyannote quer e o que os wav
já existentes em `sourceMedia\` usam.

**Participantes.** A tela pergunta **quantas pessoas** (1 a 4) e, para cada
uma, a **cadeira** (esquerda / centro / direita / sem cadeira fixa). Escolher o
número já monta as cadeiras do jeito que faz sentido para aquele tamanho de
mesa: 1 fica no centro, 2 ficam nas pontas com o **centro vazio**, 3 ocupam as
três, e a 4ª entra sem cadeira fixa (só existem três enquadramentos).

A cadeira não é enfeite: ela vira o palpite de track na etapa 2, traduz a saída
do método “Gemini em pedaços” (que rotula por posição) e — junto com o número de
pessoas — é o que os três métodos do Gemini recebem em `--roster` para montar o
prompt **deste** projeto. Numa mesa de dois, o prompt passa a dizer “duas vozes,
uma na esquerda e uma na direita, **não existe ninguém no centro**”. Antes o
texto era fixo, escrito para as três cadeiras do `EpisodioPiloto`: num projeto
de duas pessoas ele oferecia uma cadeira vazia e ainda dizia “N pessoas, uma
delas pode estar fora de quadro” — e o modelo inventava um falante no centro.

**Vozes fora de quadro (`no_name1`, `no_name2`…).** É um seletor de
quantidade, de 0 a 4, começando em 1. Cada voz escolhida entra na lista que a
diarização vai procurar (o `EpisodioPiloto` é 3 na câmera + 1 fora; uma mesa com
dois produtores falando atrás da câmera é + 2). Nenhuma delas **ganha track
própria** — todas caem na V1, igual ao `OFF_CAMERA_NAMES` do SpeakerSwitch. Não
são editáveis na lista de participantes de propósito: apagar uma por engano
faria toda fala fora de quadro virar erro de digitação em vez de cair onde deve.

Os rótulos são numerados **desde o primeiro**. Acrescentar uma segunda voz não
pode renomear a que já estava (`no_name` → `no_name1`), senão todo `turns.json`
já rotulado do projeto viraria "nome desconhecido" no SpeakerSwitch — por isso
`clean_off_camera` aceita o nome que já veio em vez de renumerar, e um projeto
antigo continua guardando `no_name` puro.

**Marcar silêncio não existe mais** (removido em 16/09/2026). Havia um
`turns.fill_gaps()` que transformava todo vazio de ≥ 0,5 s num turno `no_name`,
para o editor mostrar bloco em vez de buraco. Na prática era o contrário do que
se quer: enchia a diarização de turnos mudos para apagar à mão, e tirava do
SpeakerSwitch o "silêncio: remover", que acha o silêncio justamente pelo vazio
ENTRE turnos. Agora onde ninguém fala simplesmente não há turno.

O que ficou: `config.silence_label` (`no_name`), porque **arquivo já rodado tem
esses turnos gravados** e eles precisam continuar sendo reconhecidos. Ele entra
sempre em `off_camera_names` — sem isso o SpeakerSwitch aborta o corte inteiro
com "nome desconhecido no json" no primeiro turno mudo antigo. E é por isso que
ele tem cinza próprio (`#6b7280`), separado dos tons das vozes fora de quadro.

O número total (pessoas + vozes fora de quadro) é o `speakers` que a etapa 2 já traz
preenchido em **todo** corte novo do projeto — a tela mostra a conta escrita,
para não se rodar procurando 3 vozes numa conversa de 2.

---

## Etapa 2 — Cortes

**O trecho.** Arraste na onda ou digite os tempos (`43:30`, `1:03:30.1`, ou
segundos crus). O número que você marca responde a três perguntas de uma vez —
e a tela diz isso enquanto você arrasta:

1. onde o ffmpeg fatia o wav;
2. o `audio_offset` que o editor soma para alinhar onda e turnos;
3. o `origin_frame` — o `clip_origin` (`GetLeftOffset`) esperado da timeline de
   origem no Resolve. **43:30 → frame 156600** a 60 fps, que é exatamente o que
   a timeline do EpisodioPiloto já mostrava.

**O playhead e as teclas.** Arrastar na onda move o **cursor**, não cria
seleção — o mesmo gesto do editor de turnos. Marcar o trecho é `I` e `O`, uma
decisão explícita, em vez de efeito colateral de arrastar o mouse enquanto se
escuta. Arrastar a **borda** do trecho continua ajustando o corte.

| tecla | faz |
|---|---|
| `Espaço` | tocar / pausar a partir do playhead |
| `Enter` | tocar só o trecho marcado |
| `I` / `O` | marcar início / fim no playhead |
| `←` `→` | um frame (com `shift`, um segundo) |
| `Home` / `End` | ir ao início / fim do trecho |
| `J` `K` `L` | shuttle ¼×…4×, igual ao Resolve |

Marcar um início depois do fim empurra o outro extremo e avisa, em vez de
recusar em silêncio. As teclas não disparam com o foco num campo de tempo —
digitar `43:30` no início não pode marcar o fim.

**O mapa de tracks.** Uma linha por rótulo possível: as pessoas, o `cut`, e quem
está fora de quadro — este último sem seletor, porque é ausência de track e não
a track zero.

`cut` **não é uma pessoa**: é a decisão manual de cortar para o enquadramento
alternativo. Nenhum diarizador produz esse nome; ele só entra à mão, na etapa 3.
Se nenhum turno estiver marcado como `cut`, o SpeakerSwitch nem cria aquela
track.

**O método.** Cada um mostra o que faz, o que precisa, e em que base de tempo
ele devolve o resultado:

| método | parte de | devolve | precisa |
|---|---|---|---|
| **pyannote v3** (sugerido) | wav do corte | relativo | GPU, `HF_TOKEN` |
| pyannote v1 | wav do corte | relativo | GPU, `HF_TOKEN` |
| Gemini — áudio | wav do corte | relativo | `GEMINI_API_KEY` |
| Gemini — com vídeo | trecho remuxado | absoluto | `GEMINI_API_KEY` |
| Gemini — em pedaços | vídeo original | absoluto | `GEMINI_API_KEY` |
| Whisper — transcrição | wav do corte | relativo | — |

Quem devolve relativo tem o offset somado pelo app, uma vez, na gravação. Quem
já devolve absoluto passa direto. É a coluna que impede o problema das duas
bases de voltar.

**O modelo do Gemini é escolhido na tela**, e entra no **nome do arquivo**:
`turns_gemini-3.5-flash.chunks.json`. Assim rodar dois modelos no mesmo corte
deixa os dois lado a lado para comparar, em vez de um sobrescrever o outro. O
campo sugere os modelos conhecidos mas aceita qualquer texto — o catálogo do
Gemini muda mais rápido do que este código. Os scripts não têm `--model`: eles
leem `GEMINI_MODEL` do ambiente, e como o `load_dotenv` deles não sobrescreve
variável existente, a escolha vai pelo env do subprocesso e ganha do `.env`
sem editar arquivo nenhum.

**A caixa “transcrever o áudio junto”** roda o Whisper num passo a mais do
*mesmo* trabalho — transcrever e diarizar o mesmo corte é uma decisão só, e
duas barras de progresso para uma decisão seriam ruído. Vem marcada quando o
corte ainda não tem transcrição, desmarcada quando já tem.

Os diarizadores **não são reimplementados aqui**: continuam morando em
`scriptsPrimarios\` e são chamados lá, por caminho absoluto, com `--out`
apontando para a pasta do corte. Nenhum arquivo de lá é movido ou alterado.

Dois deles montariam pastas de trabalho dentro de `scriptsPrimarios\` por
conta própria — o `1_diarize_v3.py` cria `resultados\<title>\`, e o
`3c_diarize_gemini_chunks.py` ainda recorta os `chunkNN.mp4` em
`utilitarios\<title>\`. Como no Windows `os.path.join(raiz, caminho_absoluto)`
devolve o caminho absoluto, os dois recebem a **pasta do corte** em `--title`
e gravam tudo lá. Os `chunkNN.mp4` são arquivos de trabalho: dá para apagar
depois que a rodada termina.

**Vale rodar o Whisper junto com qualquer diarizador**: ele não separa falantes,
mas é o que enche a coluna “o que foi dito” na etapa 3 — e ler um trecho duvidoso
resolve mais rápido do que ouvi-lo três vezes.

**Quem é quem.** O pyannote nomeia as vozes de `SPEAKER_00` em diante; o
SpeakerSwitch escolhe a track pelo **nome**. O botão “quem é quem” renomeia o
arquivo inteiro de uma vez, tocando as amostras de áudio que o próprio
diarizador gravou. Dá para fazer turno a turno no editor — são centenas.

### A legenda, em dois formatos

O botão **“Gerar legenda…”** (e as duas caixas ao lado do **Rodar**, que fazem o
mesmo no fim da rodada, sem um segundo passo manual) escreve:

| formato | arquivo | para quê |
|---|---|---|
| `.srt` | `<corte>.srt` | **Timeline → Import → Subtitle** no Resolve. Tempo da **timeline** (o início do corte é subtraído, porque a timeline nova começa no frame 0) |
| GiAutoSubs | `<corte>.giautosubs.json` | o `giautosubs.py`, que monta as legendas **estilizadas** dentro do Resolve. Tempo **absoluto** |

São dois arquivos porque são dois destinos, mas **um texto só**. A diferença que
importa é o `words`: o tempo por palavra que o Whisper devolve com “tempo por
palavra” marcado. É ele que acende a palavra falada no macro do GiAutoSubs, e o
`.srt` não tem onde guardá-lo — em `.srt` a informação simplesmente se perde, e
o sintoma aparece só lá na frente, com as legendas já criadas no Resolve e o
destaque nunca acendendo. A tela diz, ao gerar, quantos trechos têm `words`.

Por que absoluto: quem desconta o início do corte, do outro lado, é o próprio
`giautosubs.py` — ele lê o `corte.json` e detecta a base. Mandar tempo de
timeline daqui seria descontar duas vezes.

E por que **não** tem “nomes na frente de cada fala” (que o `.srt` tem): no
GiAutoSubs quem fala vira **cor**, não texto — o `giautosubs.py` lê o turns do
corte e pinta a legenda com a cor da pessoa. Escrever “Giovanni: ” dentro da
legenda estilizada seria o contrário do que aquele lado faz.

**O arquivo exportado vira a transcrição do corte** (`transcript` no
`corte.json`), então é ele que a etapa 3 mostra na coluna “o que foi dito”. Um
formato, um arquivo, dois leitores: a alternativa — dois arquivos com a mesma
forma — só criava a chance de divergirem e a pergunta “qual dos dois vai para o
Resolve”, que não tem resposta boa.

No Resolve, depois:

```powershell
.\.venv\Scripts\python.exe src\giautosubs.py "projects\<projeto>\cortes\<corte>" ^
    --transcript <corte>.giautosubs.json
```

e então **Workspace → Scripts → GiAutoSubs** (ver `giautosubs\ESTADO.md`).

---

## Etapa 3 — Turnos

É o `turnsEditor`, com a mesma tela e os mesmos atalhos. `static\app.js` e
`static\style.css` são **cópias literais** de `scriptsPrimarios\turnsEditor\`
(cópia, não mudança de lugar — o original continua funcionando onde sempre
esteve).

Para que a cópia continue sendo literal, este servidor **responde à mesma API**
que aquele `app.js` já chamava: `/api/config`, `/api/turns`, `/api/transcript`,
`/api/peaks`, `/api/audio`, nos mesmos formatos. O que muda é a origem da
resposta — lá era um `config.json` fixo, aqui é o corte que você escolheu na
etapa 2:

| o editor recebe | vem de |
|---|---|
| `audio_file` / `audio_offset` | o wav do corte e o início dele |
| `fps` | o projeto (lido do arquivo pelo ffprobe) |
| `transcript_file` / `transcript_offset` | o Whisper daquele corte, offset **0** (já convertido) |
| `speaker_colors` / `speaker_order` | os participantes do projeto |
| `off_camera_names` | quem não tem track |

Consequência prática: o **corte ativo mora no servidor**, não na URL — porque o
`app.js` chama `/api/config` sem parâmetro nenhum. A rota `/turnos?projeto=…&corte=…`
define o ativo antes de entregar o HTML, então entrar por link continua
funcionando.

Os atalhos, os avisos (`curto`, `sobrepõe`, `buraco`) e o comportamento de
salvar são os mesmos — veja `scriptsPrimarios\turnsEditor\README.md`.

**Abrir um arquivo de fora.** O botão **“Abrir outro arquivo…”** na etapa 2
escolhe qualquer `turns*.json` do disco — os turnos antigos em
`scriptsPrimarios\resultados\`, ou o mesmo trecho de outro corte — e abre no
editor, sem copiar nada. A pasta entra em `extra_turns_dirs` (só leitura) e os
arquivos dela passam a aparecer no seletor, com o **caminho inteiro** no nome:
dois cortes podem ter um `turnsManual.json` cada, e duas linhas iguais que
abrem arquivos diferentes seria pior do que uma linha comprida. Gravar
continua caindo dentro do projeto — o editor salva na pasta do corte, nunca
por cima do arquivo de origem.

Ao terminar: **Gravar speaker_switch.json** na etapa 2, e rodar o
`editor_proxy\SpeakerSwitch.py` dentro do Resolve. Ele abre um **diálogo de
configurações** antes de montar qualquer coisa — o json de diarização, o que
copiar (comps Fusion, color grade, áudio), preencher buracos,
resolução/encaixe, recorte. O que fica de fora do diálogo é o mapa de tracks:
esse vem do `speaker_switch.json` deste corte, decidido aqui na etapa 2. Ver
`editor_proxy\README.md`.

### O `shell.css` é escopado, e isso não é detalhe

Na etapa 3 o `shell.css` carrega **depois** do `style.css`. Qualquer seletor
global dele com o mesmo peso ganharia do editor em silêncio — e foi o que
aconteceu na primeira versão: um `.card { padding }` inocente virou padding a
mais no deck e `gap` a mais no ledger, sem erro em lugar nenhum.

Por isso, no `shell.css`: global só o que as três rotas dividem — os tokens
(valores idênticos aos do `style.css`), a barra de etapas, e a linha a mais que
ela pede no grid do `body`. Todo o resto vive sob `body.page`, que só as etapas
1 e 2 usam. O `tests\ui.py` mede três valores do editor (padding do deck, gap
do ledger, tamanho dos botões de ícone) justamente para pegar esse vazamento
se ele voltar.

A mesma regra de cor do `turnsEditor` vale aqui: **cor é dado, nunca
decoração**. Não existe verde de "status ok" — ausência de aviso já é a boa
notícia, e inventar um verde custaria uma cor que pertence a uma pessoa
(`#4ecb8f` é o terceiro participante da paleta). Só carregam cor a identidade
de cada participante, o `cut` em violeta, e os avisos — estes sempre tingidos a
partir do token com `color-mix`, para que mudar `--caution` mude a pilula
junto.

---

## Chaves e ambiente

O botão **verificar**, na etapa 1, confere tudo de uma vez: ffmpeg, o Python da
diarização, os pacotes e as chaves.

- **`GEMINI_API_KEY`** já vem do `.env` de `scriptsPrimarios\` — os scripts de
  Gemini leem aquele arquivo sozinhos. Este app lê o mesmo arquivo **só para a
  checagem**, para não dizer “falta a chave” sobre um método que rodaria numa
  boa.
- **`HF_TOKEN`** não está setado nesta máquina. Sem ele os métodos pyannote não
  rodam. Crie `pre_production\.env` com:

  ```
  HF_TOKEN=hf_xxxxxxxxxxxxxxxx
  ```

  O token sai do huggingface.co e precisa dos termos aceitos em
  `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0`.

**Dois Pythons, de propósito.** O `.venv` deste projeto tem só
fastapi/uvicorn/numpy e sobe em segundos. O `python_exe` do `config.json` aponta
para o Python 3.12 do sistema, onde moram torch, pyannote, faster-whisper e
google-genai — cujas versões estão presas umas às outras (ver `CLAUDE.md`).
Instalar aquele mundo dentro do venv de um servidor web arrastaria a fragilidade
dele para cá. O caminho é detectado no primeiro boot procurando quem tem
`pyannote.audio` instalado.

---

## config.json

Criado no primeiro boot.

| chave | o quê |
|---|---|
| `projects_dir` | onde os projetos vivem — **a única pasta com escrita** |
| `sources_dir` | onde procurar vídeos ao criar um projeto (só leitura) |
| `scripts_dir` | onde estão os diarizadores (só leitura) |
| `python_exe` | o Python com torch/pyannote/genai; `null` = detectar |
| `ffmpeg` / `ffprobe` | caminho ou nome no PATH |
| `wav_sample_rate` / `wav_channels` | 16000 / 1 |
| `min_span_frames` | 2 — o mínimo que o Resolve aceita num clipe |
| `fps_fallback` | usado só quando o ffprobe não souber dizer |
| `active_project` / `active_cut` | qual corte a etapa 3 está olhando |
| `port` | 8740 (o turnsEditor original usa 8730 — dá para rodar os dois) |

---

## Coisas que continuam valendo a pena saber

**`MIN_SPAN_FRAMES = 2`.** Turno que vira menos de 2 frames o Resolve recusa; o
`build_spans()` do SpeakerSwitch o absorve no vizinho e ele **some do corte
final sem avisar**. A tabela de resultados marca esses como `curto` — vale olhar
antes de ir para o Resolve. (O `turnsGemini_3.5_Chunks.json` antigo tem 18.)

**`-c copy` não corta em qualquer frame.** Remuxar um trecho de vídeo faz o
ffmpeg voltar até o keyframe anterior, que pode estar segundos antes do pedido.
Entregar esse trecho ao diarizador dizendo “isto começa em 43:30” deslocaria
todo turno — e o deslocamento só apareceria no corte final. Então o app
**mede** onde o keyframe está, corta exatamente ali e grava esse valor em
`video_offset`, separado do `audio_offset`. O trecho fica alguns segundos mais
longo; o tempo continua exato.

O mesmo offset, **em frames**, vai no nome do arquivo: `<corte>_<N>frames.mkv`
(e em `video_offset_frames`, no manifesto). Os fontes são gravados com GOP de
250 frames — medido com `ffprobe -skip_frame nokey` no `Episodio1.mkv` (8,333 s
a 30 fps) e no `EpisodioPiloto.mkv` (4,167 s a 60 fps) — então N cai em
qualquer ponto de **0 a 249**, uniforme: em média ~125 frames, no pior caso
~8,3 s ou ~4,2 s. Não é detalhe de máquina, é quanto aparar na frente ao
arrastar o arquivo pro Resolve — por isso está no nome, e não só no manifesto.
O `.mkv` sai sozinho, num job próprio, assim que o corte é criado; mudar o
trecho depois (`PATCH`) desliga o vídeo do manifesto, porque ele foi medido
para o trecho antigo.

**E dá pra editar a partir dele.** O `GetLeftOffset` que o Resolve reporta é
relativo ao ARQUIVO da timeline-fonte, não ao episódio — então um clipe inteiro
do `<corte>_<N>frames.mkv` reportaria `0`, o script leria "este trecho começa no
segundo 0 do episódio" e todo turno cairia fora do range, calado. O
`media_base()` do SpeakerSwitch fecha isso: se a mídia da timeline-fonte é o
trecho do corte (bate o nome com `video` do manifesto), ele soma
`video_offset × fps` ao `GetLeftOffset`. Editando do episódio inteiro a soma é
zero e nada muda.

Com isso **você não apara nada à mão**: o script sabe que os N frames da frente
são sobra de keyframe e começa a timeline nova no `origin_frame`. Aparar
manualmente também funciona (o absoluto continua batendo), só é trabalho à toa.

**Três arquivos por rodada, e cada um serve pra uma coisa.** O `.json` é o
canônico (absoluto, é o que vai pro editor e pro Resolve); o `.raw.json` é o que
o script cuspiu, na base dele, guardado para quando você desconfiar da
conversão; e o `.segmentos.json` — só nos métodos pyannote — é a diarização
**antes** da suavização, que o `1_diarize_v3.py` reprocessa com `--from-json`
sem gastar GPU de novo.

**Nada é apagado por um clique.** Excluir um projeto ou um corte move a pasta
para `projects\_lixeira\<nome>-<data>`. Salvar por cima de um `turns*.json` gera
um `.bak` datado, e a escrita é atômica.

**`3c_diarize_gemini_chunks.py` tinha os nomes fixos no código** (`SPEAKER_LEFT`
→ Giovanni, `CENTER` → Cupertino, `RIGHT` → Heitor, `OFFCAM` → no_name). Com
`--roster` — que o app sempre manda — ele já escreve os nomes deste projeto e só
classifica nas cadeiras que existem aqui; o dicionário fixo vale apenas para
quem roda o script na mão, sem elenco, e aí o app continua renomeando pela
posição. A descrição que cai numa cadeira que o projeto não tem (o modelo dizer
“centro” numa mesa de dois) vai para a única cadeira em quadro compatível
quando não há dúvida, e é descartada **com aviso** quando há.
Ele também sugere, mas não roda, o passo de “planos” do `1_diarize_v3.py`, e a
sugestão vem com `--fps 30` fixo; num projeto de 60 fps isso faria os cortes
caírem só em frames pares.

---

## O que ficou de fora

- **Vídeo no editor de turnos.** Pedido e cancelado na sessão anterior; nada foi
  implementado. O levantamento continua valendo: o Chrome não toca MKV, mas o
  vídeo é H.264, então dá para remuxar sem recodificar — e agora existe o
  caminho pronto (`ensure_video`), por corte em vez do episódio inteiro.
- **Importar o trabalho que já existe** em `scriptsPrimarios\resultados\`. Os
  turnos antigos continuam onde estão; nada aqui os move nem os lê.
- **`5_name_speakers.py`** não é chamado. O “quem é quem” da etapa 2 faz a parte
  que faltava (renomear em massa); o resto daquele script — descrições e
  amostras — o `1_diarize_v3.py` já cobre.
