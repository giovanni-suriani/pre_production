"""Registro dos metodos de diarizacao.

Os diarizadores NAO sao reimplementados aqui. Eles continuam morando em
`scriptsPrimarios\\` e sao chamados la, por caminho absoluto, com `--out`
apontando pra pasta do corte. Duplicar o codigo de diarizacao criaria duas
verdades sobre o mesmo assunto - e a que estivesse errada seria justamente a
que ninguem lembra de atualizar.

O que este arquivo faz e' descrever CADA metodo como dado:

    input        de que arquivo ele parte (wav do corte, video inteiro,
                 ou um trecho de video remuxado)
    output_base  em que base de tempo ele cospe o resultado - "relative" (0 =
                 inicio do corte) ou "absolute" (0 = inicio do episodio).
                 E' o campo que impede o problema das duas bases de voltar:
                 quem devolve relativo tem o offset somado pelo app antes de
                 virar arquivo canonico.
    label_style  que rotulo sai: SPEAKER_XX generico, nome por cadeira, ou
                 nenhum (o Whisper transcreve mas nao diariza).

Acrescentar um metodo novo e' acrescentar um dicionario aqui.
"""

import os
import re
from pathlib import Path

import config

# Os modelos do Gemini em uso. `id` e' o que a API recebe (e o que entra no
# nome do arquivo); `label` e' como eles aparecem no AI Studio, que e' como se
# pensa neles na hora de escolher.
#
# E' SUGESTAO, nao lista fechada: a tela tem um "outro modelo..." com campo
# livre, porque o catalogo e as cotas do Gemini mudam mais rapido do que este
# arquivo. Os ids conferem com os do comentario do .env de scriptsPrimarios\.
GEMINI_MODELS = [
    {"id": "gemini-3.6-flash",      "label": "Gemini 3.6 Flash"},
    {"id": "gemini-3.5-flash",      "label": "Gemini 3.5 Flash"},
    {"id": "gemini-3.7-flash",      "label": "Gemini 3.7 Flash"},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite"},
]

# Qual vem pre-selecionado na tela. E' uma constante, NAO "o primeiro da
# lista": a ordem da lista e a escolha do padrao sao decisoes diferentes - a
# lista segue a ordem em que voce pensa nos modelos, e o padrao e' o
# flash-lite, que tem a cota diaria bem maior (nota do proprio .env).
# O mesmo valor esta no topo dos scripts 3_/3c_, para que rodar pela tela e
# rodar pelo terminal sem --model deem o MESMO modelo.
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"

_GEMINI_MODEL_OPT = {
    "gemini_model": {"label": "modelo do Gemini",
                     "default": DEFAULT_GEMINI_MODEL,
                     "suggest": GEMINI_MODELS},
}
# O modelo vai como ARGUMENTO (`--model`), nao como variavel de ambiente.
# Antes era env porque os scripts nao tinham a flag; ela foi acrescentada aos
# tres (ver backups_scriptsPrimarios\). Argumento e' melhor: aparece no comando
# que o log imprime, entao da pra ler depois com que modelo aquela rodada saiu -
# uma variavel de ambiente some do registro.

# ---------------------------------------------------------------------------
# Notas de compatibilidade que valeram descoberta e nao estao obvias no codigo
# dos scripts:
#
#  * 1_diarize_v3.py faz `os.makedirs(resultados\<title>)` mesmo quando --out
#    aponta pra outro lugar. Como no Windows `os.path.join(raiz, caminho_
#    absoluto)` devolve o caminho absoluto, passar a PASTA DO CORTE em --title
#    faz o script gravar tudo (turnos, .raw.json, amostras) dentro do corte -
#    e nao cria pasta nenhuma dentro de scriptsPrimarios\resultados.
#
#  * Os tres metodos do Gemini recebem `--roster` (ver scriptsPrimarios\
#    roster.py): o elenco DESTE projeto, cadeira por cadeira. E' o que faz o
#    prompt dizer "duas pessoas, esquerda e direita, ninguem no centro" em vez
#    do texto fixo de tres cadeiras do EpisodioPiloto - que, num projeto de
#    dois, fazia o modelo inventar um falante no centro vazio.
#
#  * 3c_diarize_gemini_chunks.py tinha POSITION_TO_NAME fixo no codigo
#    (SPEAKER_LEFT->Giovanni, CENTER->Cupertino, RIGHT->Heitor,
#    OFFCAM->no_name). Com `--roster` ele ja escreve os nomes deste projeto;
#    o dict fixo so vale quando alguem roda o script na mao, sem elenco. O
#    label_style "seat" continua aqui porque, nesse caso, o app ainda renomeia
#    pela posicao.
#
#  * 3_diarize_gemini_video.py sobe o video inteiro pro Gemini; nao tem
#    --start/--end. Por isso ele recebe um trecho remuxado do corte, e nao o
#    episodio de 3 GB.
# ---------------------------------------------------------------------------

SEAT_ALIASES = {
    "left": "Giovanni", "center": "Cupertino",
    "right": "Heitor", "offcam": "no_name",
}

METHODS = [
    {
        "id": "pyannote_v3",
        "label": "pyannote 3.1 — planos limpos (v3)",
        "engine": "pyannote",
        "script": "1_diarize_v3.py",
        "input": "wav",
        "output_base": "relative",
        "label_style": "generic",         # SPEAKER_00, SPEAKER_01...
        "kind": "diarization",
        "out_name": "turnsPyannote_v3.json",
        "needs_packages": ["pyannote.audio", "torch"],
        "needs_env": ["HF_TOKEN"],
        "recommended": True,
        "note": "Roda na GPU, local, sem cota. Já aplica a suavização "
                "(junta turnos colados, descarta micro-turnos, padding) e "
                "fecha os buracos, então a saída já vem como PLANOS "
                "contínuos — que é o que o SpeakerSwitch quer. Grava "
                "amostras de áudio por voz na pasta do corte, para você "
                "descobrir quem é SPEAKER_00.",
        "args": ["{wav}",
                 "--speakers", "{speakers}",
                 "--out", "{out}",
                 "--title", "{cutdir}",
                 "--samples-dir", "{samples_dir}",
                 "--fps", "{fps}",
                 "--duration", "{duration}"],
        "extra_outputs": ["{out_stem}.raw.json"],
    },
    {
        "id": "pyannote",
        "label": "pyannote 3.1 — cru (v1)",
        "engine": "pyannote",
        "script": "1_diarize.py",
        "input": "wav",
        "output_base": "relative",
        "label_style": "generic",
        "kind": "diarization",
        "out_name": "turnsPyannote.json",
        "needs_packages": ["pyannote.audio", "torch"],
        "needs_env": ["HF_TOKEN"],
        "note": "A versão original, mais simples. Útil para comparar com a v3 "
                "quando ela suavizar demais.",
        "args": ["{wav}", "--speakers", "{speakers}", "--out", "{out}"],
    },
    {
        "id": "gemini_audio",
        "label": "Gemini — áudio inteiro",
        "engine": "gemini",
        "script": "3_diarize_gemini.py",
        "input": "wav",
        "output_base": "relative",
        "label_style": "generic",
        "kind": "diarization",
        "out_name": "turnsGemini.json",
        # o modelo entra no NOME do arquivo: rodar dois modelos no mesmo corte
        # gera dois arquivos comparaveis em vez de um sobrescrever o outro
        "out_name_template": "turns_{gemini_model}.audio.json",
        "options": dict(_GEMINI_MODEL_OPT),
        "needs_packages": ["google.genai", "dotenv"],
        "needs_env": ["GEMINI_API_KEY"],
        "note": "Manda o wav do corte inteiro de uma vez. Rápido e sem GPU, "
                "mas com mic único de sala ele confunde vozes próximas — foi "
                "onde o pyannote confundiu duas pessoas num rótulo só.",
        "args": ["{wav}", "--speakers", "{speakers}", "--out", "{out}",
                 "--model", "{gemini_model}", "--roster", "{roster}"],
    },
    {
        "id": "gemini_video",
        "label": "Gemini — com vídeo (lê a imagem)",
        "engine": "gemini",
        "script": "3_diarize_gemini_video.py",
        "input": "video_cut",
        "output_base": "absolute",        # o proprio script soma --offset
        "label_style": "generic",
        "kind": "diarization",
        "out_name": "turnsGeminiVideo.json",
        "out_name_template": "turns_{gemini_model}.video.json",
        "options": dict(_GEMINI_MODEL_OPT),
        "needs_packages": ["google.genai", "dotenv", "pydantic"],
        "needs_env": ["GEMINI_API_KEY"],
        "note": "Vê quem mexe a boca, não só quem soa parecido — foi o que "
                "resolveu a confusão de vozes que o áudio sozinho não "
                "resolvia. Precisa subir o trecho de vídeo para o Gemini, "
                "então corte curto sobe rápido e episódio inteiro não sobe.",
        "args": ["{video_cut}",
                 "--speakers", "{speakers}",
                 "--roster", "{roster}",
                 "--offset", "{video_offset}",
                 "--model", "{gemini_model}",
                 "--out", "{out}"],
    },
    {
        "id": "gemini_chunks",
        "label": "Gemini — vídeo em pedaços",
        "engine": "gemini",
        "script": "3c_diarize_gemini_chunks.py",
        "input": "video_src",
        "output_base": "absolute",        # ja trabalha em tempo absoluto
        "label_style": "seat",            # nomes fixos por cadeira
        "kind": "diarization",
        "out_name": "turnsGeminiChunks.json",
        "out_name_template": "turns_{gemini_model}.chunks.json",
        "needs_packages": ["google.genai", "dotenv", "pydantic"],
        "needs_env": ["GEMINI_API_KEY"],
        "note": "Fatia o episódio em pedaços do tamanho que você escolher e "
                "diariza um a um — dá conta de trecho longo sem estourar o "
                "upload. É o mais demorado (pausa entre pedaços para não bater "
                "no rate limit). Os nomes saem por cadeira e o app renomeia "
                "pelas posições do projeto.",
        # --title com a PASTA DO CORTE: o 3c_ monta duas pastas de trabalho a
        # partir dele (`resultados\<title>` e `utilitarios\<title>`, onde ele
        # recorta os chunkNN.mp4). Sem isto ele espalha pedaços de video de
        # varios MB dentro de scriptsPrimarios\utilitarios\, que nao e' pasta
        # deste app. Mesmo truque do os.path.join usado no pyannote v3.
        "args": ["{video_src}",
                 "--start", "{start}", "--end", "{end}",
                 "--speakers", "{speakers}",
                 "--roster", "{roster}",
                 "--chunk-seconds", "{chunk_seconds}",
                 "--model", "{gemini_model}",
                 "--title", "{cutdir}",
                 "--out", "{out}"],
        "progress_re": r"pedaco\s+(\d+)\s*/\s*(\d+)",
        "extra_outputs": ["{out_stem}_chunks_speakers_debug.json"],
        "options": dict(_GEMINI_MODEL_OPT,
                        chunk_seconds={"label": "segundos por pedaço",
                                       "default": 180, "min": 30, "max": 600}),
    },
    {
        "id": "gemini_transcribe",
        "label": "Gemini 3.5 Transcribe — diarização + transcrição",
        "engine": "gemini",
        "script": "3d_transcribe_gemini35.py",
        "input": "wav",
        "output_base": "relative",
        "label_style": "generic",         # SPEAKER_00, SPEAKER_01...
        "kind": "diarization",
        "out_name": "turnsGeminiTranscribe.json",
        "needs_packages": ["google.genai", "dotenv"],
        "needs_env": ["GEMINI_API_KEY"],
        "note": "Modelo dedicado de transcrição do Gemini (lançado "
                "2026-08-26): ~2.6% WER, bem acima dos modelos de chat "
                "usados nos outros métodos Gemini. Devolve diarização E "
                "texto com tempo por palavra na MESMA rodada — o turno já "
                "sai com \"words\", então serve tanto pra editar quem fala "
                "quanto pra encher a coluna \"o que foi dito\", sem precisar "
                "rodar o Whisper depois. Atribuição de falante é oficial "
                "até 3 pessoas; a 4ª (o off-camera, quase sempre) é "
                "experimental. Com diarização + palavra ligados, o áudio do "
                "corte precisa caber em 30 min.",
        "args": ["{wav}", "--speakers", "{speakers}", "--out", "{out}"],
    },
    {
        "id": "whisper",
        "label": "Whisper — transcrição apenas",
        "engine": "whisper",
        "script": "4_transcribe_whisper.py",
        "input": "wav",
        "output_base": "relative",
        "label_style": "none",
        "kind": "transcript",
        "out_name": "turnsWhisper.json",
        # o modelo entra no nome, mesma ideia do Gemini - e aqui pesa ate mais,
        # porque a diferenca entre `tiny` e `large-v3` esta no TEXTO: o tiny
        # devolve portugues quebrado que parece transcricao ruim de audio ruim.
        # Sem o modelo no nome nao da pra saber, olhando a pasta, se aquele
        # texto sofrivel merece uma rodada melhor ou se ja e' o melhor possivel.
        #
        # `turnsWhisper_medium.json`, e nao `turns_medium.whisper.json` como no
        # Gemini: os ids do Gemini ja comecam com "gemini-", entao la o motor
        # aparece sozinho: `tiny`/`medium`/`large-v3` nao dizem de quem sao.
        # Mantendo o prefixo, as transcricoes tambem continuam juntas na
        # listagem da pasta, ordenadas por nome.
        "out_name_template": "turnsWhisper_{whisper_model}.json",
        "needs_packages": ["faster_whisper"],
        "needs_env": [],
        "note": "Não diariza — só escreve o que foi dito e quando. É o que "
                "enche a coluna \"o que foi dito\" do editor, e é o que "
                "permite decidir um corte duvidoso lendo em vez de ouvindo "
                "três vezes. Vale rodar junto com qualquer diarizador.",
        # `--words` sempre ligado: custa uns 25% a mais de tempo e e' o que
        # torna possivel o destaque palavra a palavra do GiAutoSubs. Sem isso
        # a transcricao so' diz quando a FRASE comeca, e a legenda estilizada
        # nao tem como acender a palavra que esta sendo dita - o sintoma vira
        # "SEM DESTAQUE" no fim de uma rodada inteira no Resolve. Melhor pagar
        # os 25% aqui do que refazer a transcricao depois.
        "args": ["{wav}",
                 "--out", "{out}",
                 "--device", "{device}",
                 "--whisper-model", "{whisper_model}",
                 "--language", "{language}",
                 "--words"],
        "options": {
            # padrao 03/09: GPU + large-v3 - o que rodou de verdade no
            # EpisodioPiloto/Episodio1 (ver HANDOFF-20260903.md), nao cpu/medium
            "device": {"label": "onde rodar", "default": "cuda",
                       "choices": ["cpu", "cuda"]},
            "whisper_model": {"label": "modelo", "default": "large-v3",
                              "choices": ["tiny", "base", "small", "medium",
                                          "large-v3"]},
            "language": {"label": "idioma", "default": "pt"},
        },
    },
]

BY_ID = {m["id"]: m for m in METHODS}


def get(method_id):
    m = BY_ID.get(method_id)
    if not m:
        raise KeyError(f"metodo desconhecido: {method_id!r}")
    return m


def script_path(method):
    return config.scripts_dir() / method["script"]


def public(probe=None, env_present=None):
    """Lista pra interface, ja dizendo o que falta pra cada metodo rodar.

    Descobrir que falta o HF_TOKEN depois de 20 minutos de espera e' o tipo de
    coisa que da pra evitar com uma checagem de 1 segundo.
    """
    probe = probe or {}
    env_present = env_present or {}
    out = []
    for m in METHODS:
        missing = [p for p in m["needs_packages"] if probe.get(p) is False]
        missing_env = [e for e in m["needs_env"] if not env_present.get(e)]
        exists = script_path(m).is_file()
        out.append({
            "id": m["id"], "label": m["label"], "engine": m["engine"],
            "kind": m["kind"], "input": m["input"],
            "output_base": m["output_base"], "label_style": m["label_style"],
            "out_name": m["out_name"], "note": m["note"],
            "out_name_template": m.get("out_name_template"),
            "recommended": m.get("recommended", False),
            "options": m.get("options", {}),
            "script": str(script_path(m)),
            "ready": exists and not missing and not missing_env,
            "missing_packages": missing,
            "missing_env": missing_env,
            "script_missing": not exists,
        })
    return out


def options_with_defaults(method, given):
    """As opcoes escolhidas, completadas com o default de cada uma."""
    given = given or {}
    return {k: (given.get(k) if given.get(k) not in (None, "") else spec.get("default"))
            for k, spec in method.get("options", {}).items()}


def _token(v):
    """Valor de opcao -> pedaco de nome de arquivo. `gemini-3.5-flash` passa
    inteiro; qualquer coisa com barra ou espaco vira hifen."""
    return re.sub(r"[^\w.\-]+", "-", str(v)).strip("-.") or "x"


def out_name_for(method, options):
    """Nome do arquivo de saida - com o modelo dentro, quando o metodo pede.

    `turns_gemini-3.5-flash.chunks.json` em vez de `turnsGeminiChunks.json`:
    rodar dois modelos no mesmo corte passa a gerar dois arquivos comparaveis
    lado a lado, em vez de um sobrescrever o outro (e gerar um .bak que
    ninguem vai abrir).
    """
    tpl = method.get("out_name_template")
    if not tpl:
        return method["out_name"]
    vals = {k: _token(v) for k, v in options_with_defaults(method, options).items()}
    try:
        return tpl.format(**vals)
    except KeyError:
        return method["out_name"]


def env_for(method, options, base):
    """Env do subprocesso: o do app mais as opcoes que viram variavel."""
    env = dict(base)
    chosen = options_with_defaults(method, options)
    for opt, var in method.get("env_from_options", {}).items():
        v = chosen.get(opt)
        if v:
            env[var] = str(v)
    return env


def build_args(method, ctx):
    """Substitui os {placeholders} do template pelos caminhos deste corte."""
    out = []
    for a in method["args"]:
        s = str(a)
        for k, v in ctx.items():
            s = s.replace("{" + k + "}", str(v))
        if "{" in s and "}" in s:
            raise ValueError(f"argumento com placeholder nao resolvido: {s!r} "
                             f"(metodo {method['id']})")
        out.append(s)
    return out


def extra_outputs(method, out_path):
    stem = str(Path(out_path).with_suffix(""))
    return [e.replace("{out_stem}", stem) for e in method.get("extra_outputs", [])]
