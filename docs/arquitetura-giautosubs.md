# Arquitetura do GiAutoSubs — o desenho

Do arquivo plano da legenda até os clipes na timeline, em duas fases.

**Página publicada:**
<https://claude.ai/code/artifact/4c097c14-a90e-4385-85f7-484217225a65>

Fonte ao lado: [`arquitetura-giautosubs.html`](arquitetura-giautosubs.html).

---

## O que o desenho mostra

**PREPARAÇÃO** — monta as peças, muda raramente. Quatro linhas paralelas, cada
uma produzindo uma peça:

| origem | passa por | produz |
|---|---|---|
| `audio.wav` do corte | Whisper large-v3 `--words` | `<corte>.giautosubs.json` — o arquivo plano: texto + tempo por palavra |
| diarização (pyannote / Gemini) | turnsEditor | `turnsManual.json` — quem fala, decide a track |
| você edita (ou exporta do clipe) | — | `estilos.json` — os atributos de cada clipe |
| `vendor/autosubs-macro.setting` | `gerar_macro.py` | `GiAutoSubs Caption.setting`, instalado em `Templates/Edit/Titles` |

**APLICAÇÃO** — a cada corte. As **três entradas** (em vermelho no desenho)
descem até o `giautosubs.py`, que as funde em `legendas.lua`. Dentro do Resolve,
o `GiAutoSubs.lua` lê o `legendas.lua` **e** o `Caption.setting`, e produz todos
os clipes.

E a volta tracejada: **Generate Caption Style** lê um clipe ajustado e escreve um
estilo novo no `estilos.json` — da aplicação de volta para a preparação.

## As duas cores do desenho não são enfeite

- **Vermelho** — as três entradas que passam pelo `giautosubs.py`.
- **Ciano** — o `Caption.setting`, que **não** passa por ele e vai direto ao
  `GiAutoSubs.lua`.

Esse contraste é o ponto da arquitetura: o `giautosubs.py` nunca lê o
`.setting`, e o `gerar_macro.py` nunca lê o `legendas.lua`. A única amarra entre
as duas trilhas é o carimbo `MACRO_VERSAO`, que existe para o script recusar a
combinação errada.

## A consequência que sempre volta

Quando um Title vira clipe, o Resolve **copia o macro inteiro para dentro dele** —
N legendas são N cópias independentes. Refazer a preparação não conserta clipes
que já existem:

- mudou o **macro** → reinicie o Resolve e **recrie os clipes**;
- mudou só o **estilo** → regere o `legendas.lua`, ou ajuste no Inspector e
  clique **Apply Style**, que é o único caminho para uma legenda que já está na
  timeline.

---

## Para atualizar a página

O arquivo aqui é a **fonte do artifact** — sem `<html>`, `<head>` e `<body>`,
que são adicionados na publicação. Abre num navegador assim mesmo.

Publicando a partir deste caminho, passe a **URL acima** como `url`, senão sai um
artifact novo em vez de atualizar este.

Detalhe por dentro: [`../giautosubs/MACRO.md`](../giautosubs/MACRO.md)
(precedência dos valores, atributos do Text+, receita para um controle novo) e
[`../giautosubs/ESTADO.md`](../giautosubs/ESTADO.md) (histórico das versões).
