# Testes do pre_production

Não são unitários. Os dois dirigem o app de verdade — um pela API, outro por um
Chrome headless — porque é assim que este app quebra: um ffmpeg que não corta
onde se pediu, um offset somado duas vezes, uma página que fica em branco por
causa de um erro de javascript que o servidor nunca vê.

O servidor precisa estar de pé (`run.bat`).

```powershell
# 1. API, ponta a ponta: cria projeto, extrai wav, fatia, roda, confere o disco
.\.venv\Scripts\python.exe tests\smoke.py --keep

# 2. interface: abre as três rotas num Chrome headless e ouve o console
C:\Users\talco\AppData\Local\Programs\Python\Python312\python.exe tests\ui.py

# 3. o diálogo do SpeakerSwitch (não precisa de servidor nem de Resolve)
C:\Users\talco\AppData\Local\Programs\Python\Python312\python.exe tests\dialogo_speakerswitch.py
```

Nesta ordem: o `ui.py` precisa de um projeto com um corte já pronto, e é o
`smoke.py --keep` que deixa um. Sem o `--keep`, o `smoke.py` manda o projeto de
teste para `projects\_lixeira` no fim.

| arquivo | roda com | cobre |
|---|---|---|
| `smoke.py` | o venv do app | ffprobe, extração do wav, fatiamento, subprocesso do método, **conversão de base de tempo**, manifestos, config do editor, travas de caminho, ponte com o SpeakerSwitch, os **dois formatos de legenda** (`.srt` e o json do GiAutoSubs, com o tempo por palavra) |
| `ui.py` | Python 3.12 do sistema (precisa de `websocket-client`) | as três rotas carregam, a onda desenha, os métodos listam, o editor abre com o corte ativo, **nenhum erro de console** |
| `dialogo_speakerswitch.py` | Python 3.12 do sistema (precisa de `tkinter`) | o diálogo de configurações do `editor_proxy\SpeakerSwitch.py`: a janela monta, os padrões atravessam, cancelar não devolve nada, campo inválido não deixa rodar, e as escolhas viram os globais que o script lê |

**Por que o terceiro existe.** O diálogo mora num `python -c` dentro do
`SpeakerSwitch.py` — texto, não código importado. Ele só é compilado quando
alguém clica no menu do Resolve, então um erro de sintaxe ali não aparece em
lugar nenhum até a hora de montar a timeline. O teste constrói a janela de
verdade e aperta os botões por código; o que fica sem cobertura é só o clique.

## O que o smoke.py checa com mais cuidado

As duas coisas que custaram caro no pipeline antigo:

1. **A base de tempo.** O `turnsXxx.json` tem que sair em tempo **absoluto** e o
   `turnsXxx.raw.json` ao lado tem que continuar **relativo** ao corte. Se
   alguém um dia somar o offset duas vezes, ou esquecer de somar, é aqui que
   aparece — e não três semanas depois, dentro do Resolve.
2. **`origin_frame == round(start * fps)`** — a mesma conta do
   `SpeakerSwitch.py` e do `timecode.py`. Três lugares, uma conta só.

## Por que o método padrão é o Whisper

`--method whisper` com o modelo `tiny` é o único que roda **sem GPU, sem
`HF_TOKEN` e sem gastar cota de API**. Rodar o teste não deveria custar nada.
Os outros métodos passam pelo mesmo caminho de código — o que muda é o comando.

Para exercitar outro:

```powershell
.\.venv\Scripts\python.exe tests\smoke.py --method pyannote_v3 --keep
```

Ele pula sozinho, sem falhar, se o método estiver indisponível.

## Autoteste do timecode

```powershell
.\.venv\Scripts\python.exe src\timecode.py
```

Confere as conversões (`43:30` → 2610 s → frame 156600) sem precisar de
servidor nenhum.
