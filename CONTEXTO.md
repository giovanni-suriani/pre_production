# Contexto do pre_production — handoff

Estado em **26/08/2026**. Escrito para retomar numa sessão nova.
O manual está no `README.md`; aqui fica só o que uma sessão nova precisa saber
antes de mexer em qualquer coisa.

---

## O que é

App local que faz tudo que acontece **antes** do DaVinci Resolve, em três
rotas. Nasceu nesta sessão, do zero, em `D:\CanalYtbe\BatataQuente\pre_production\`.

```
run.bat  →  http://127.0.0.1:8740      (o turnsEditor original usa 8730; dá pra rodar os dois)

/          etapa 1  ProjectEditor   mp4/mkv → wav 16 kHz mono, nome, participantes
/cortes    etapa 2  CutsEditor      trecho na onda, tracks, métodos, rodada, legenda
/turnos    etapa 3  turnsEditor     corrigir os turnos (cópia literal do original)
editor_proxy\                       SpeakerSwitch.py — roda DENTRO do Resolve
```

---

## A decisão que sustenta o projeto

**Uma base de tempo só, escrita, derivada em vez de adivinhada.**

No pipeline antigo circulavam duas bases sem etiqueta: `turnsPyannote4.json`
começava em 1.13 s (relativo ao corte de 43:30) e `turnsGemini_3.5_Chunks.json`
em 2610 s (absoluto). Mesmo conteúdo, eixos diferentes, nada dizendo qual era
qual.

Aqui isso não existe:

- a saída crua do script fica em `turnsXxx.raw.json`, como ele cuspiu;
- o canônico `turnsXxx.json` é **sempre tempo absoluto da mídia** — a unidade
  que o próprio `SpeakerSwitch.py` documenta em `RANGE_START`/`RANGE_END`;
- `corte.json` grava `time_base` e `audio_offset` explicitamente;
- cada método declara `output_base` no `methods.py`; quem devolve relativo tem
  o offset somado uma vez, na gravação.

**Se for mexer em qualquer coisa de tempo, o `tests/smoke.py` é o guarda-costas**
— ele checa exatamente isso e `origin_frame == round(start * fps)`.

---

## scriptsPrimarios: o que foi e o que NÃO foi tocado

A regra da sessão era não mover nada de lá. Nada foi movido. Mas, **a pedido
explícito no fim da sessão**, três scripts foram *editados*:

| arquivo | mudança | linhas |
|---|---|---|
| `3_diarize_gemini.py` | ganhou `--model` | 6 |
| `3_diarize_gemini_video.py` | ganhou `--model` | 6 |
| `3c_diarize_gemini_chunks.py` | ganhou `--model` | 7 |
| `.env` | `GEMINI_MODEL` removido (sobrou só `GEMINI_API_KEY`) | — |

Backups completos em `backups_scriptsPrimarios\`. As edições são
retrocompatíveis: sem `--model`, o default é `gemini-3.1-flash-lite`.

**Pegadinha:** `default=MODEL` no argparse já é uma leitura de `MODEL` dentro da
função, então o `global MODEL` tem que ser a **primeira linha** de `main()` —
senão dá `SyntaxError: name 'MODEL' is used prior to global declaration`.

O resto de `scriptsPrimarios\` é chamado por caminho absoluto e nunca alterado.
Dois scripts montariam pastas de trabalho lá por conta própria
(`1_diarize_v3.py` cria `resultados\<title>\`, `3c_` recorta os `chunkNN.mp4`
em `utilitarios\<title>\`) — os dois recebem a **pasta do corte** em `--title`,
e como no Windows `os.path.join(raiz, absoluto)` devolve o absoluto, tudo cai
dentro do corte.

---

## Estado atual

```
projects\EpisodioPiloto\cortes\corte_shorts1        43:30→45:30, pyannote_v3 + Whisper, legenda .srt
projects\TestePiloto\cortes\corte_teste_mosquito    44:30→58:00, gemini_chunks + Whisper (recuperado)
config.json  ativo: EpisodioPiloto / corte_shorts1
             extra_turns_dirs: scriptsPrimarios\resultados\EpisodioPiloto
```

Testes: **`tests\smoke.py` 37 ok · `tests\ui.py` 35 ok**, zero falhas.
Rodar nesta ordem (o `ui.py` precisa de um corte pronto — ver `tests\README.md`).

---

## Coisas que custaram a descobrir nesta sessão

**O `shell.css` precisa ser escopado.** Na etapa 3 ele carrega *depois* do
`style.css` (a cópia literal do turnsEditor). Um `.card { padding }` global
inocente virou padding a mais no deck e `gap` a mais no ledger, sem erro em
lugar nenhum. Hoje só os tokens, a barra de etapas e a linha extra do grid são
globais; o resto vive sob `body.page`. O `ui.py` mede três valores do editor
justamente para pegar esse vazamento se voltar.

**Config com BOM zerava tudo em silêncio.** `Set-Content -Encoding utf8` do
PowerShell 5, Notepad e VS Code gravam BOM; lido como `utf-8` puro, o
`json.loads` falhava e o app voltava aos defaults sem nada explodir. Todos os
leitores de JSON usam `utf-8-sig` agora.

**Jobs vivem só em memória.** Reiniciar o servidor no meio de uma rodada perde
o acompanhamento mas **não mata** o processo do script — ele termina e grava o
`.raw.json` sem ninguém para convertê-lo. Aconteceu de verdade (91 min de CPU
de um Whisper `large-v3`). Hoje a tela para de perguntar no 404 e o corte
oferece **"finalizar rodada"**, que detecta a base de tempo e completa o
serviço. **Persistir os jobs em disco continua sendo o conserto de verdade.**

**`-c copy` não corta em qualquer frame.** Remuxar vídeo volta até o keyframe
anterior. O app **mede** onde ele está e grava `video_offset` separado do
`audio_offset`, em vez de supor que são iguais.

**`3c_` tem os nomes fixos por cadeira** (`SPEAKER_LEFT`→Giovanni etc.) e não
aceita nomes por parâmetro. O app trata a saída como rótulo de **posição** e
renomeia pelas cadeiras do projeto — por isso a cadeira é perguntada na etapa 1.

---

## A legenda do GiAutoSubs sai da etapa 2 (28/08)

A etapa 2 exporta em **dois formatos**: o `.srt` de sempre e o
`<corte>.giautosubs.json`, que é o que o `giautosubs.py` lê. Os dois saem juntos
no fim da rodada (duas caixas ao lado do **Rodar**) e o modal "Gerar legenda…"
faz o mesmo à mão.

A diferença que justifica o segundo formato é o `words` — o tempo por palavra do
Whisper. É ele que acende a palavra falada no macro, e o `.srt` não tem onde
guardá-lo: em `.srt` a informação se perde, e o sintoma só aparece com as
legendas já criadas dentro do Resolve.

E o arquivo exportado **vira a transcrição do corte**: é ele que a etapa 3 mostra
na coluna "o que foi dito". Um formato, um arquivo, dois leitores — dois arquivos
com a mesma forma só criariam a chance de divergirem.

Detalhes no `README.md` (etapa 2, "A legenda, em dois formatos") e no
`giautosubs\ESTADO.md`.

## O SpeakerSwitch pergunta antes de rodar (28/08)

`editor_proxy\SpeakerSwitch.py` abre um diálogo com as configurações **desta
rodada** antes de tocar no projeto: json de diarização, nome da timeline, comps
Fusion, color grade, áudio (e áudio por falante), preencher buracos, resolução,
encaixe e recorte. As constantes no topo viraram o **estado inicial** dele, e a
última escolha fica em `_speakerswitch_opcoes.json`, na pasta do corte.

Mesma mecânica do seletor de arquivo que já existia: tkinter **em processo
separado**, porque dentro do Resolve ele põe dois event loops no mesmo processo
e derruba o editor — e o `AskUser` do Fusion vem `None` fora da página Fusion.

Fica fora do diálogo, de propósito, o mapa de tracks: ele é decisão do material
(vem do `speaker_switch.json` do corte), não da rodada.

Coberto por `tests\dialogo_speakerswitch.py` (30 checagens, sem servidor e sem
Resolve). Para isso o `SpeakerSwitch.py` ganhou um guarda no fim
(`if __name__ != "SpeakerSwitch"`) — sem ele, `import SpeakerSwitch` **monta uma
timeline**; foi assim que o teste travou na primeira tentativa.

## Em aberto

- **Persistir os jobs** — hoje um reinício do servidor perde o acompanhamento.
  O "finalizar rodada" é curativo, não cura.
- **Vídeo no editor de turnos** — pedido e cancelado numa sessão anterior. O
  caminho de remux por corte já existe (`_ensure_video`), só falta a tela.
- **A pasta se chama `editor_proxy`** no disco, mas foi pedida como
  `editor_prox`. Os textos foram alinhados com o disco; renomear é decisão sua.
- **`3c_` sugere `--fps 30`** no passo de "planos" que ele imprime. Num projeto
  de 60 fps isso faria os cortes caírem só em frames pares. Não foi mexido.
- Um dos modelos aparecia com a cota diária estourada (23/20) no painel do
  Gemini. Se uma rodada falhar na API, é o primeiro lugar para olhar.

---

## Avisos para quem for continuar

- **Não reinicie o servidor sem perguntar** se pode haver rodada em andamento —
  foi assim que os 91 minutos de CPU quase foram perdidos.
- O `app.js` e o `style.css` de `src\static\` são **cópias literais** do
  `scriptsPrimarios\turnsEditor\`. O que o editor não faz é acrescentado **por
  fora** (a barra de etapas e o "importar transcrição" são scripts inline no
  `turnos.html`), porque o `app.js` declara `api` e `toast` no escopo global e
  carregar o `shell.js` junto quebraria o editor inteiro.
- **Cor é dado, nunca decoração.** Não existe verde de "status ok" — o verde da
  paleta pertence ao terceiro participante. O azul das checkboxes (`--check`) é
  o mesmo do primeiro participante e só pode ser usado onde não houver
  identidade de pessoa por perto.
