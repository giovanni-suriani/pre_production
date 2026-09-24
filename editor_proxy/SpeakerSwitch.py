"""
PASSO 2 (v3) - Monta a timeline com um track por participante

Cada turno vira um segmento NA TRACK DO PROPRIO SPEAKER, na posicao real
da timeline. Onde a pessoa nao fala, a track fica vazia e a de baixo aparece.

    V3  ----
    V2              --------
    V1      ------            ------

Mudancas em relacao a v2:
  * build_spans avisa (em vez de engolir) quando um label da diarizacao nao
    esta em SPEAKER_TO_TRACK - antes caia silenciosamente na BASE_TRACK.
  * span curto demais (< MIN_SPAN_FRAMES) e absorvido pelo span anterior em
    vez de simplesmente descartado - descartar abria um buraco sem clipe em
    nenhuma track (flash preto), mesmo com SILENCE_MODE="preencher" (o buraco tambem
    ficava menor que MIN_SPAN_FRAMES e nao era preenchido).
  * SPLIT_AUDIO_BY_SPEAKER = False por padrao: todo audio vem do mesmo
    base["mpi"] (mixagem unica da gravacao wide-shot), entao espalhar por
    varias tracks de audio nao isola voz nenhuma, so multiplica pontos de
    emenda (risco de clique). Reavaliar se algum dia a midia tiver canais
    separados por microfone.
  * timelineInputResMismatchBehavior: trocado o loop de ~19 candidatos
    especulativos (que tambem escrevia no PROJECT como fallback a cada
    candidato rejeitado pela timeline, sem reverter isso no final) por uma
    constante explicita MISMATCH_BEHAVIOR = "scaleToCrop" - ja validada em
    producao por readback. None = herda o valor da timeline de ORIGEM, mas
    so faz sentido se a origem ja for TARGET_WIDTHxTARGET_HEIGHT (ver aviso
    abaixo).
  * apply_target_resolution agora sempre imprime a resolucao/mismatch da
    timeline de ORIGEM antes de tudo, e avisa se ela nao bater com
    TARGET_WIDTH/TARGET_HEIGHT: o Zoom/Pan/Tilt copiado de cada clipe-fonte
    foi autorado sobre a baseline de escala da timeline de origem (midia ==
    resolucao da timeline = escala 1.0 antes do Zoom manual); numa timeline
    de destino com resolucao/aspecto diferente essa baseline muda e o Zoom
    copiado multiplica em cima da baseline errada - nenhum valor de mismatch
    conserta isso, so decide de que jeito o enquadramento sai torto.
  * RANGE_START/RANGE_END (segundos): recorta um trecho da track-fonte em
    vez de sempre montar a gravacao inteira - pra gerar um Short a partir
    de so uma parte do episodio. A timeline nova comeca realinhada no frame
    0 (recordFrame = tl_start + (frame_do_trecho - inicio_do_recorte)), nao
    na posicao original dentro do episodio.

Instalacao:
    C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\Utility\\
    Workspace > Scripts > SpeakerSwitch   (funciona na versao Free)

Antes de rodar:
    - Abra a timeline com os layers ja enquadrados (V1..V4)
    - Cada track = UM clipe unico, sincronizado, cobrindo a gravacao inteira
    - Ao rodar, abre um dialogo com as configuracoes DESTA rodada: o json de
      diarizacao, o nome da timeline nova, o que copiar (comps Fusion, color
      grade, audio), preencher buracos, resolucao/encaixe e o recorte. As
      constantes abaixo sao so' o ponto de partida dele, e a ultima escolha
      fica guardada em `_speakerswitch_opcoes.json`, na pasta do corte.
    - Quem fica em qual track continua vindo do `speaker_switch.json` daquele
      corte (decidido na tela do pre_production), nao do dialogo: e' decisao do
      material, nao da rodada.
    - Pra corrigir um corte errado, use o turnsEditor
      (scriptsPrimarios\\turnsEditor\\run.bat) - ele mostra a onda, o texto
      falado e deixa trocar o falante no proprio bloco

Sobre "cut" (trecho JOGADO FORA):
    "cut" nao e' uma pessoa: e' a marca manual de "isto sai do corte final".
    Nenhum diarizador produz esse nome; ele so entra a mao, no turnsEditor,
    depois que os turnos ja estao corretos.

    O trecho marcado assim nao vira clipe nenhum, e o tempo dele NAO fica como
    buraco: tudo que vem depois anda pra tras (ripple), video e audio juntos.
    Da pra desligar isso na caixa "Remover os trechos marcados como cut" do
    dialogo - desligada, eles voltam a virar clipe na track do mapa (V4), que
    e' como se confere o corte com o material inteiro antes de jogar fora.

    Silencio DE VERDADE (ninguem falando) e' outra pergunta, com tres
    respostas - preencher com a V1, deixar o buraco, ou remover tambem. Ver
    SILENCE_MODE.

    Isso vale mesmo que o `speaker_switch.json`/`corte.json` do corte ainda
    mande "cut" pra uma track (o V4 herdado) - CUT_NAMES ganha do mapa, entao
    os cortes antigos continuam abrindo sem editar nada, e a V4 simplesmente
    nao chega a ser criada.
"""

import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- config
# Organizacao: cada video tem sua propria pasta em resultados\<VIDEO_TITLE>\
# com TODOS os arquivos relacionados (turnos, amostras, comps temporarios).
# Troque aqui quando processar um episodio novo.
VIDEO_TITLE = "EpisodioPiloto"

# Qual diarizacao usar por padrao (pre-preenche o dialogo de escolha do arquivo,
# que abre toda vez que o script roda): "pyannote", "gemini", "gemini_video"
# ou "gemini_chunks"
DIARIZATION_SOURCE = "gemini_video"

_RESULTADOS_ROOT = r"D:\CanalYtbe\BatataQuente\scriptsPrimarios\resultados"
_VIDEO_DIR = _RESULTADOS_ROOT + "\\" + VIDEO_TITLE
_TURNS_BY_SOURCE = {
    "pyannote": _VIDEO_DIR + r"\turnsPyannote4.json",
    "gemini": _VIDEO_DIR + r"\turnsGemini4.json",
    # pyannote conflou 2 pessoas em 1 label nesse trecho (mic unico, sala
    # inteira num so canal - ver NOTES_diarization_alternatives.md); Gemini
    # com VIDEO (nao so audio) resolveu de primeira usando pista visual.
    "gemini_video": _VIDEO_DIR + r"\turnsGeminiVideo4_shots.json",
    # 3c_diarize_gemini_chunks.py (video em pedacos de 3min, gemini-3.5-flash) -
    # cobre so 2610.0s-3330.0s por enquanto (4 chunks de teste), nao o episodio
    # inteiro. Ainda em avaliacao: deu mais tempo de fala ao Cupertino
    # (60.7% vs 41.1% no gemini_video) e blocos suspeitosamente longos perto
    # de 2849-2985s - conferir no Resolve antes de confiar cegamente.
    "gemini_chunks": _VIDEO_DIR + r"\turnsGemini_3.5_Chunks_shots.json",
}
_TURNS_ANTIGO = _TURNS_BY_SOURCE[DIARIZATION_SOURCE]

# Onde os cortes do pre_production moram. O caminho e' fixo (e nao relativo a
# este arquivo) porque o script tem duas copias e a que o Resolve executa fica
# em C:\ProgramData\...\Scripts\Utility - de la, "..\..\projects" nao existe.
_PREPROD_PROJECTS = r"D:\CanalYtbe\BatataQuente\pre_production\projects"
# O nome que o turnsEditor grava depois que voce corrige os falantes a mao.
# E' o unico arquivo de turnos que ja passou por revisao humana, e portanto o
# unico que faz sentido oferecer sozinho - as saidas cruas dos diarizadores
# (turnsGemini*, turnsWhisper*, *.raw.json) ficam pro botao "Procurar...".
_TURNS_REVISADO = "turnsManual.json"


def _turns_mais_recente():
    r"""O turnsManual.json mais novo entre os cortes do pre_production.

    Serve so' pra pre-preencher o dialogo. Quase sempre a resposta certa: o
    corte em que voce esta trabalhando e' o que acabou de ser salvo no editor
    de turnos. `_lixeira` fica de fora - projeto movido pra la e' justamente o
    que voce NAO quer que reapareca sugerido.
    """
    achados = []
    for raiz, pastas, arquivos in os.walk(_PREPROD_PROJECTS):
        pastas[:] = [p for p in pastas if not p.startswith("_")]
        if _TURNS_REVISADO in arquivos:
            p = os.path.join(raiz, _TURNS_REVISADO)
            try:
                achados.append((os.path.getmtime(p), p))
            except OSError:
                pass
    if not achados:
        return None
    return max(achados)[1]


def _midia_da_timeline():
    """Nome do arquivo de midia da primeira track com clipe da timeline aberta.

    Olhada barata e so'-leitura, feita ANTES do dialogo (o resto do script so'
    fala com o Resolve depois). Qualquer falha devolve None: isto e' conforto
    pra escolher o default, nunca motivo pra derrubar a rodada.
    """
    try:
        tl = get_resolve().GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        for idx in range(1, int(tl.GetTrackCount("video")) + 1):
            items = tl.GetItemListInTrack("video", idx)
            if not items:
                continue
            mpi = items[0].GetMediaPoolItem()
            if not mpi:
                continue
            nome = os.path.basename(str(mpi.GetName() or ""))
            if nome:
                return nome
    except Exception as e:
        print(f"[!] nao deu pra olhar a timeline aberta antes do dialogo ({e})")
    return None


def _turns_do_trecho(nome_midia):
    r"""turnsManual.json do corte que gerou `<corte>_<N>frames.mkv`.

    O default do dialogo tem que sair da TIMELINE ABERTA, nao do relogio: o
    trecho na timeline foi exportado pelo pre_production pra um corte
    especifico, e o `corte.json` desse corte e' quem diz qual arquivo e' o
    dele (`video`). Casar por ai' e' exato - nome de pasta e slug do arquivo
    nao sao a mesma coisa.

    O que motivou: `_turns_mais_recente()` oferecia o turnsManual mais NOVO de
    todos os cortes, que nao tem relacao nenhuma com a timeline aberta. Deu
    `Eu_Duvido_13frames.mkv` na timeline com o json do `Qual_mundo...` (turnos
    em 3183-3793s contra um range de 0-405s): zero segmentos, "Nada pra montar".
    """
    if not nome_midia or not re.match(r"(?i)^.+_\d+frames\.\w+$", nome_midia):
        return None
    for raiz, pastas, arquivos in os.walk(_PREPROD_PROJECTS):
        pastas[:] = [p for p in pastas if not p.startswith("_")]
        if "corte.json" not in arquivos:
            continue
        c = _le_json(os.path.join(raiz, "corte.json")) or {}
        v = c.get("video")
        if not v or os.path.basename(str(v)).lower() != nome_midia.lower():
            continue
        for p in (os.path.join(raiz, "turns", _TURNS_REVISADO),
                  os.path.join(raiz, _TURNS_REVISADO)):
            if os.path.isfile(p):
                print(f"[i] a timeline aberta e' o trecho do corte "
                      f"'{c.get('name')}' - default do dialogo veio dele")
                return p
        print(f"[!] a timeline aberta e' o trecho do corte '{c.get('name')}', "
              f"mas ele ainda nao tem {_TURNS_REVISADO} - revise os turnos no "
              f"turnsEditor (o dialogo abre com outro corte pre-selecionado)")
        return None
    print(f"[!] '{nome_midia}' parece um trecho exportado pelo pre_production, "
          f"mas nenhum corte.json em {_PREPROD_PROJECTS} aponta pra ele")
    return None


DEFAULT_TURNS_JSON = _turns_mais_recente() or _TURNS_ANTIGO

# ------------------------------------------------------------ pre_production
# Pasta de um corte gerado pelo pre_production. Preenchida, o dialogo de
# arquivo ja abre nela; e o `corte.json` que mora la passa a mandar no
# NAME_TO_TRACK e no OFF_CAMERA_NAMES, em vez dos dicts fixos abaixo.
#
# Por que: o mapa "quem fica em qual track" e' uma decisao POR CORTE (num short
# de duas pessoas a V3 nao existe), mas vivia como constante no topo deste
# script - entao rodar dois cortes diferentes pedia editar o script no meio do
# caminho, e esquecer disso produzia um corte errado sem nenhum aviso. Agora a
# decisao e' tomada na tela do corte e lida daqui.
#
# Le o `corte.json` DIRETO desde 02/09. Antes lia um `speaker_switch.json`, um
# arquivo-ponte que a tela gravava por botao com uma copia dos mesmos campos -
# copia que so' existia enquanto alguem lembrasse de clicar. Nao lembrar nao
# dava erro: o script caia calado no NAME_TO_TRACK fixo daqui, que e' de outro
# episodio. Aconteceu, e so' apareceu porque os nomes daquele corte eram
# diferentes; com os mesmos nomes em cadeiras trocadas, a timeline sairia toda
# errada sem um aviso sequer. O `speaker_switch.json` continua sendo lido como
# fallback, pros cortes que ainda tem um.
#
# Deixe em None pra usar exatamente o comportamento antigo. O arquivo tambem e'
# detectado sozinho quando o json escolhido no dialogo estiver dentro de uma
# pasta de corte.
PREPROD_CUT = None
# ex: r"D:\CanalYtbe\BatataQuente\pre_production\projects\Episodio\cortes\corte_shorts1"


def _pasta_do_corte(turns_json):
    """Pasta do corte a partir do caminho de um turns*.json.

    Desde a reorganizacao em subpastas do pre_production, turns*.json mora em
    `<corte>\\turns\\`, nao direto em `<corte>\\`. `speaker_switch.json` e
    `_speakerswitch_opcoes.json` continuam na RAIZ do corte - por isso quem
    precisa da pasta do corte nao pode usar `os.path.dirname(turns_json)` cru:
    isso devolveria `turns\\`, e o `speaker_switch.json` de la nunca seria
    achado (o NAME_TO_TRACK fixo deste script entraria no lugar, calado).
    """
    d = os.path.dirname(turns_json)
    if os.path.basename(d).lower() in ("turns", "legendas"):
        return os.path.dirname(d)
    return d


def _parece_corte(turns_json):
    """O json escolhido veio de um corte do pre_production?

    Serve pra separar "corte sem configuracao" (erro, tem que parar) de
    "rodando fora do pre_production" (legitimo, usa o mapa fixo). Sem essa
    distincao, exigir o corte.json quebraria o fluxo antigo do
    scriptsPrimarios\\resultados, e nao exigir deixa de volta o fallback
    calado que ja montou timeline errada.
    """
    partes = [p.lower() for p in
              os.path.normpath(turns_json).replace("/", "\\").split("\\")]
    return "cortes" in partes or partes[-2:-1] in (["turns"], ["legendas"])


def _le_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] {path} ilegivel ({e})")
        return None


def _fonte_do_projeto(folder):
    """Nome do arquivo do episodio, do project.json duas pastas acima.

    `projects\\<proj>\\cortes\\<corte>\\` -> `projects\\<proj>\\project.json`.
    Devolve None se nao achar - e' informacao de conveniencia, nao contrato.
    """
    p = _le_json(os.path.join(folder, "..", "..", "project.json"))
    fonte = (p or {}).get("source_video")
    return os.path.basename(str(fonte)) if fonte else None


def _read_preprod(folder):
    """Configuracao de um corte do pre_production, normalizada.

    Fonte de verdade e' o `corte.json` - o mesmo arquivo que a tela edita, sem
    copia no meio. O `speaker_switch.json` (arquivo-ponte, aposentado em 02/09)
    ainda e' aceito depois dele, pros cortes gravados antes da mudanca.
    Devolve None se a pasta nao for de um corte.
    """
    if not folder:
        return None
    c = _le_json(os.path.join(folder, "corte.json"))
    if c and c.get("track_map"):
        return {
            "fonte": "corte.json",
            "projeto": c.get("project"),
            "corte": c.get("name"),
            "name_to_track": c["track_map"],
            "off_camera_names": c.get("off_camera"),
            "fps": c.get("fps"),
            "range_start": c.get("start"),
            "range_end": c.get("end"),
            "origin_frame": c.get("origin_frame"),
            # o trecho remuxado (`<corte>_<N>frames.mkv`) e o frame do EPISODIO
            # onde o frame 0 DELE cai - ver media_base() la embaixo
            "video": c.get("video"),
            "video_origin_frame": (
                int(round(c["video_offset"] * c["fps"]))
                if c.get("video_offset") is not None and c.get("fps") else None),
            # o episodio: so' pra reconhecer a midia legitima e nao acusar
            # arquivo renomeado onde nao ha nenhum - ver media_base()
            "episodio": _fonte_do_projeto(folder),
            "turns": (os.path.join(folder, "turns", c["last_turns_file"])
                      if c.get("last_turns_file") else None),
        }
    ss = _le_json(os.path.join(folder, "speaker_switch.json"))
    if ss:
        ss["fonte"] = "speaker_switch.json (formato antigo)"
        return ss
    return None


if PREPROD_CUT:
    _pp = _read_preprod(PREPROD_CUT)
    if _pp and _pp.get("turns"):
        DEFAULT_TURNS_JSON = _pp["turns"]

# nome da pessoa (campo "name" do json, preenchido pelo 5_name_speakers.py)
# -> numero da track. Usa NOME em vez do label abstrato SPEAKER_XX de proposito:
# assim, pra corrigir um corte errado manualmente, basta abrir o
# turnsGeminiVideo4_shots.json e trocar o "name" daquele turno - nao precisa
# saber/lembrar qual SPEAKER_XX era quem. no_name (fora de quadro, so audio)
# fica de fora de proposito - cai na BASE_TRACK (V1).
NAME_TO_TRACK = {
    "Giovanni": 1,   # V1 - esquerda
    "Cupertino": 2,  # V2 - centro
    "Heitor": 3,     # V3 - direita
    # "cut" nao entra aqui: nao e' uma track, e' descarte - ver CUT_NAMES.
}
# nomes que significam "este trecho SAI do corte final". Nao viram clipe, e o
# tempo deles nao fica como buraco: o que vem depois anda pra tras (ripple).
#
# Tem precedencia sobre o NAME_TO_TRACK de proposito: os cortes ja gravados
# (corte.json/speaker_switch.json do pre_production) trazem "cut": 4 no
# track_map, herdado de quando "cut" era o enquadramento alternativo da V4.
# Obedecer aquele mapa hoje faria o trecho aparecer na timeline em vez de sair
# dela - exatamente o contrario do que a marca quer dizer.
CUT_NAMES = {"cut"}
# nomes que ficam de fora DE PROPOSITO (nao tem V-track, cai na BASE_TRACK) -
# qualquer outro nome fora dessa lista + NAME_TO_TRACK e' tratado como erro de
# digitacao na edicao manual do json, nao like BASE_TRACK silencioso.
OFF_CAMERA_NAMES = {"no_name"}

NEW_TIMELINE_NAME = "AutoSpeakerSwitch"
# Recorta [RANGE_START, RANGE_END) EM SEGUNDOS ABSOLUTOS NA MIDIA-FONTE
# (mesma unidade que os "start"/"end" do json de diarizacao) - None = usa a
# timeline-fonte INTEIRA (default, e o caso normal). So mexa nisso se quiser
# um recorte ADICIONAL, menor do que o que a timeline-fonte ja contem.
#
# Descoberto na pratica: a timeline-fonte (Claude_test) pode ja ser, ela
# mesma, so um TRECHO da gravacao original (GetLeftOffset != 0) - nesse caso
# o frame 0 dela NAO corresponde ao segundo 0 do episodio. O script agora
# detecta isso sozinho (clip_origin = GetLeftOffset), entao normalmente nao
# precisa configurar nada aqui - so preencha se quiser recortar AINDA MAIS
# dentro do que a timeline-fonte ja tem.
RANGE_START = None    # segundos absolutos na midia-fonte
RANGE_END = None      # segundos absolutos na midia-fonte
BASE_TRACK = 1             # track que preenche silencio / labels desconhecidos

# O que fazer com SILENCIO DE VERDADE - o tempo em que ninguem que tem track
# esta falando (pausa, ou o `no_name` fora de quadro). Nada a ver com os
# trechos marcados como `cut`, que sao decisao manual (ver REMOVE_CUT).
#
#   "preencher" cobre com um clipe da BASE_TRACK (o comportamento de sempre)
#   "buraco"    deixa o vazio - vira frame preto na timeline
#   "remover"   tira o tempo e puxa o resto pra tras (ripple), igual ao `cut`
#
# "remover" corta TODA pausa, inclusive as respiradas entre frases: e o efeito
# jump-cut, e e' bem mais agressivo do que parece na descricao. Provavelmente
# so' vale a pena junto de um PAD_OUT generoso na diarizacao.
SILENCE_MODE = "preencher"
# Estado inicial da caixa no dialogo. Desligado, os trechos de `cut` voltam a
# virar clipe na track que o mapa do corte mandar (V4, tipicamente) - serve pra
# CONFERIR o corte com o material inteiro na timeline antes de jogar fora.
REMOVE_CUT = True
COPY_AUDIO = True          # leva o audio original pra timeline, 1 span por vez (mesmos frames do video)
SPLIT_AUDIO_BY_SPEAKER = False  # True: 1 track de audio por speaker (A1/A2/A3). False: 1 clipe continuo em A1
# False porque todo audio vem do mesmo base["mpi"] (mixagem unica da gravacao
# wide-shot) - separar em varias tracks nao isola voz nenhuma, so multiplica
# pontos de emenda (risco de clique) sem ganho. Reavaliar se algum dia a
# midia tiver canais separados por microfone de fato.

# Resolucao da timeline nova (formato vertical, ex: Shorts). None = mantem a
# resolucao copiada do original.
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
# Comportamento de mismatch (clipe nao bate com a resolucao da timeline).
# "scaleToCrop" e o valor validado em producao por readback (preenche
# cortando o excesso, sem barra preta). None = herda o valor que a timeline
# de ORIGEM ja tinha, em vez de forcar um.
#
# So faca sentido usar None se Claude_test ja for 1080x1920: o Zoom/Pan/Tilt
# que a gente COPIA de cada clipe-fonte foi autorado sobre a baseline da
# timeline de origem (midia == resolucao da timeline = escala 1.0 antes do
# Zoom manual). Numa timeline com resolucao diferente essa baseline muda
# (~0.5625x em scaleToFit, ~1.777x em scaleToCrop) e o Zoom copiado multiplica
# em cima da baseline errada - nenhum valor de mismatch conserta isso, so o
# enum decide de que jeito fica torto. apply_target_resolution() imprime a
# resolucao/mismatch da origem em toda rodada pra confirmar isso.
MISMATCH_BEHAVIOR = "scaleToCrop"

# Enquadramento: TODAS as propriedades que it.GetProperty() reportar sao
# copiadas (nao so uma lista fixa de Zoom/Pan/Tilt/Crop).

# Exporta o(s) comp(s) Fusion de cada track-fonte pra um .comp temporario e
# importa em cada clipe novo daquela track (export uma vez por track, import
# em todos os clipes - os clipes novos sao a mesma media, so mudam de posicao).
# O comp original foi feito pro clipe fonte inteiro (93358 frames); importado
# cru num clipe novo bem menor (so o trecho do turno) causava "MediaOut1
# failed at time 0" no RENDER (fora do nosso script) - frame preto, com o
# audio tocando normal por baixo (parecia desync). Fix: logo apos o import,
# realinhamos COMPN_GlobalStart/End e RenderStart/End pro range local do
# clipe novo (ver passo FUSION COMPS mais abaixo).
#
# Isto aqui e' so' o estado INICIAL da caixa no dialogo (ver `ask_settings`) -
# desligado porque e' o passo mais caro e o mais fragil, e porque o normal e'
# querer ver a timeline montada antes de pagar por ele.
COPY_FUSION_COMPS = False
_FUSION_TMP_DIR = _VIDEO_DIR + r"\_fusion_comps_tmp"

# Copia o grade da pagina Color (nodes/rodas/curvas) do clipe-fonte de cada
# track pros clipes novos, via CopyGrades - diferente do "clip color" (label)
# que ja e copiado sempre.
COPY_COLOR_GRADE = False  # idem: estado inicial da caixa, marcavel no dialogo
# -----------------------------------------------------------------------


def banner(ok, msg):
    line = "=" * 50
    tag = "SUCESSO" if ok else "FALHOU"
    print(f"\n{line}\n[{tag}] {msg}\n{line}\n")


def get_resolve():
    r = globals().get("resolve")
    if r:
        return r
    try:
        return bmd.scriptapp("Resolve")  # noqa: F821
    except NameError:
        pass
    import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


# Codigo do dialogo nativo, rodado num processo separado (ver
# _ask_file_external). Escreve o caminho escolhido no stdout; string vazia =
# cancelado. Fica como texto pra ser passado com `python -c`.
_FILE_DIALOG_SNIPPET = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askopenfilename(
    parent=root,
    title="SpeakerSwitch - escolha o JSON de diarizacao",
    initialdir=sys.argv[1],
    initialfile=sys.argv[2],
    filetypes=[("Diarizacao (turns*.json)", "turns*.json"),
               ("JSON", "*.json"),
               ("Todos os arquivos", "*.*")])
root.destroy()
sys.stdout.write(path or "")
"""


def _python_exe():
    """Acha um python.exe de verdade pra rodar o dialogo. Dentro do Resolve,
    sys.executable aponta pro Resolve.exe (interpretador embutido), mas
    sys.base_prefix continua apontando pra instalacao do Python que forneceu a
    python3xx.dll - e de la que sai o tkinter."""
    import shutil
    cands = [
        os.path.join(sys.base_prefix, "python.exe"),
        os.path.join(sys.prefix, "python.exe"),
        shutil.which("python"),
        shutil.which("python3"),
    ]
    for c in cands:
        if c and os.path.isfile(c) and "Resolve" not in c:
            return c
    return None


def _ask_file_external(default_path):
    """Abre o dialogo de arquivo do Windows num processo separado (python +
    tkinter). Em processo separado de proposito: rodar tkinter dentro do
    Resolve mistura dois event loops Qt/Tk no mesmo processo e trava/derruba o
    Resolve. Retorna o caminho, "" se o usuario cancelou, ou None se nem deu
    pra abrir o dialogo (ai o chamador cai pro default)."""
    exe = _python_exe()
    if not exe:
        print("[!] nao achei um python.exe externo pro dialogo de arquivo "
              f"(sys.base_prefix={sys.base_prefix!r})")
        return None
    init_dir = _pasta_do_corte(default_path) or _VIDEO_DIR
    init_file = os.path.basename(default_path)
    try:
        r = subprocess.run(
            [exe, "-c", _FILE_DIALOG_SNIPPET, init_dir, init_file],
            capture_output=True, text=True, timeout=300,
            creationflags=0x08000000)  # CREATE_NO_WINDOW: sem flash de console
    except Exception as e:
        print(f"[!] dialogo de arquivo externo falhou ({e})")
        return None
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        print(f"[!] dialogo de arquivo externo saiu com codigo {r.returncode}"
              + (f": {err[-1]}" if err else ""))
        return None
    return r.stdout.strip()


def ask_turns_file(default_path):
    """Escolhe o arquivo turns*.json na hora de rodar. Se o dialogo nao
    estiver disponivel ou falhar, cai pro default_path (troque
    DIARIZATION_SOURCE/_TURNS_BY_SOURCE no topo do script pra mudar esse
    default). Retorna None se o usuario cancelar explicitamente.

    Ordem: dialogo nativo do Windows num processo separado (funciona em
    qualquer pagina do Resolve) > AskUser do Fusion > default. O AskUser
    sozinho nao bastava: ele existe como atributo mas vem None (nao callable)
    quando o script roda via Workspace > Scripts fora da pagina Fusion, que e
    o nosso caso normal (script de timeline, rodado da pagina Edit/Cut)."""
    chosen = _ask_file_external(default_path)
    if chosen == "":
        return None            # cancelou no dialogo
    if chosen:
        return chosen

    fu = globals().get("fusion") or globals().get("fu")
    if fu is not None and callable(getattr(fu, "AskUser", None)):
        try:
            itm = {1: {1: "TurnsFile",
                       "Name": "Arquivo de diarizacao (turnsPyannote*.json / turnsGemini*.json)",
                       "Type": "File", "Default": default_path}}
            ui = fu.AskUser("Escolher diarizacao para o SpeakerSwitch", itm)
            if ui is None:
                return None
            return ui.get("TurnsFile") or default_path
        except Exception as e:
            print(f"[!] AskUser do Fusion falhou ({e})")

    print(f"[i] nenhum dialogo de arquivo disponivel - usando DIARIZATION_SOURCE "
          f"atual: {default_path}")
    return default_path


# ------------------------------------------------- configuracoes da rodada
#
# O que era constante no topo deste arquivo e agora e' pergunta: as decisoes
# que mudam DE UMA RODADA PRA OUTRA. "Copiar os comps Fusion" e "copiar o color
# grade" sao o caso obvio - os dois vivem sendo desligados pra isolar um
# problema e religados depois -, mas a lista inteira tem a mesma natureza:
# nenhuma delas e' propriedade do script, todas sao escolha de quem roda.
#
# Fica FORA daqui, de proposito, o que e' propriedade do MATERIAL e nao da
# rodada: NAME_TO_TRACK e OFF_CAMERA_NAMES (quem fica em qual track) vem do
# `speaker_switch.json` do corte, que foi decidido na tela do pre_production, e
# BASE_TRACK, que e' consequencia daquele mapa. Oferecer os dois aqui seria dar
# duas fontes pra mesma decisao.
_OPCOES_ARQUIVO = "_speakerswitch_opcoes.json"

# O dialogo, de novo em PROCESSO SEPARADO. Mesma razao do dialogo de arquivo:
# tkinter dentro do Resolve poe dois event loops (Qt e Tk) no mesmo processo e
# trava/derruba o editor. Os padroes entram por stdin (json) e a escolha sai
# por stdout (json); string vazia = cancelado.
_SETTINGS_DIALOG_SNIPPET = r"""
import json, sys
import tkinter as tk
from tkinter import filedialog

d = json.loads(sys.stdin.read() or "{}")

root = tk.Tk()
root.title("SpeakerSwitch - configuracoes desta rodada")
root.attributes("-topmost", True)
root.resizable(False, False)
root.columnconfigure(1, weight=1)

estado = {"linha": 0, "ok": False}


def _grid(w, **kw):
    w.grid(row=estado["linha"], **kw)


def titulo(txt):
    _grid(tk.Label(root, text=txt, font=("Segoe UI", 9, "bold")),
          column=0, columnspan=3, sticky="w", padx=10, pady=(12, 2))
    estado["linha"] += 1


def campo(rotulo, valor, largura=48, dica=""):
    v = tk.StringVar(value="" if valor is None else str(valor))
    _grid(tk.Label(root, text=rotulo), column=0, sticky="w", padx=10, pady=3)
    _grid(tk.Entry(root, textvariable=v, width=largura), column=1,
          sticky="we", padx=6, pady=3)
    if dica:
        _grid(tk.Label(root, text=dica, fg="#777"), column=2, sticky="w", padx=10)
    estado["linha"] += 1
    return v


def caixa(rotulo, valor, dica=""):
    v = tk.BooleanVar(value=bool(valor))
    _grid(tk.Checkbutton(root, text=rotulo, variable=v), column=0,
          columnspan=2, sticky="w", padx=6)
    if dica:
        _grid(tk.Label(root, text=dica, fg="#777"), column=2, sticky="w", padx=10)
    estado["linha"] += 1
    return v


# Radio numa linha so'. Existe porque o silencio tem TRES saidas e nao duas -
# preencher, deixar o buraco, ou remover puxando o resto pra tras. Como duas
# caixas independentes, 'preencher' e 'remover' marcados juntos seria um estado
# sem significado que alguem teria que resolver depois.
# (comentario, e nao docstring, porque isto vive dentro do r-string do dialogo:
#  tres aspas aqui fechariam o snippet no meio - nem dentro de comentario da,
#  o interpretador fecha a string antes de existir comentario nenhum.)
def escolha(rotulo, opcoes, valor, dica=""):
    v = tk.StringVar(value=valor if valor in opcoes else opcoes[0])
    _grid(tk.Label(root, text=rotulo), column=0, sticky="w", padx=10, pady=3)
    linha = tk.Frame(root)
    _grid(linha, column=1, sticky="w", padx=6, pady=3)
    for o in opcoes:
        tk.Radiobutton(linha, text=o, variable=v, value=o).pack(side="left")
    if dica:
        _grid(tk.Label(root, text=dica, fg="#777"), column=2, sticky="w", padx=10)
    estado["linha"] += 1
    return v


titulo("De onde vem o corte")
turns = campo("Diarizacao", d.get("turns", ""))
linha_turns = estado["linha"] - 1


def procurar():
    atual = turns.get()
    p = filedialog.askopenfilename(
        parent=root, title="SpeakerSwitch - escolha o JSON de diarizacao",
        initialdir=(atual and __import__("os").path.dirname(atual)) or "",
        initialfile=(atual and __import__("os").path.basename(atual)) or "",
        filetypes=[("Diarizacao (turns*.json)", "turns*.json"),
                   ("JSON", "*.json"), ("Todos os arquivos", "*.*")])
    if p:
        turns.set(p)


tk.Button(root, text="Procurar...", command=procurar).grid(
    row=linha_turns, column=2, sticky="w", padx=10)
nome = campo("Timeline nova", d.get("timeline_name", ""), dica="ganha _2, _3... se ja existir")

titulo("O que copiar dos clipes-fonte")
fusion = caixa("Comps Fusion", d.get("fusion"),
               "o passo mais caro e o mais fragil")
grade = caixa("Color grade (pagina Color)", d.get("grade"))
audio = caixa("Audio original", d.get("copy_audio"),
              "mesmos frames do video - sync por construcao")
split = caixa("Uma track de audio por falante", d.get("split_audio"),
              "so ajuda com microfone por pessoa")

# Secao escondida a pedido (10/09): os valores saem das constantes do topo
# (REMOVE_CUT, SILENCE_MODE, TARGET_WIDTH/HEIGHT, MISMATCH_BEHAVIOR,
# RANGE_START/END) e o ask_settings nao deixa o _speakerswitch_opcoes.json
# sobrescreve-los - ver _OPCOES_FIXAS. Pra voltar, descomente e troque o
# `estado["saida"]` do rodar() de volta pros widgets.
# titulo("Geometria da timeline nova")
# corta = caixa("Remover os trechos marcados como cut", d.get("remove_cut"),
#               "desligado, viram clipe na track do mapa (V4) - pra conferir")
# silencio = escolha("Silencio (ninguem falando)",
#                    ["preencher", "buraco", "remover"], d.get("silence_mode"),
#                    "remover = jump-cut, corta ate as respiradas")
# res = campo("Resolucao", d.get("resolution", ""), largura=14,
#             dica="ex: 1080x1920 - vazio mantem a da origem")
# mismatch = campo("Encaixe do clipe", d.get("mismatch", ""), largura=14,
#                  dica="scaleToCrop | scaleToFit | vazio = herda da origem")
# ini = campo("Recorte - inicio (s)", d.get("range_start", ""), largura=14,
#             dica="segundos absolutos na midia; vazio = a timeline inteira")
# fim = campo("Recorte - fim (s)", d.get("range_end", ""), largura=14)

erro = tk.Label(root, text="", fg="#b00")
erro.grid(row=estado["linha"], column=0, columnspan=3, sticky="w", padx=10)
estado["linha"] += 1


def num(txt, rotulo):
    txt = txt.strip()
    if not txt:
        return None
    return float(txt.replace(",", "."))


def rodar():
    # validacao de resolucao/recorte comentada junto com os campos escondidos
    # try:
    #     r = res.get().strip().lower().replace(" ", "")
    #     if r:
    #         w, h = r.split("x")
    #         largura, altura = int(w), int(h)
    #     else:
    #         largura = altura = None
    #     a, b = num(ini.get(), "inicio"), num(fim.get(), "fim")
    # except ValueError:
    #     erro.config(text="Resolucao tem que ser LARGURAxALTURA (ex: 1080x1920) "
    #                      "e os recortes, numeros em segundos.")
    #     return
    # if a is not None and b is not None and b <= a:
    #     erro.config(text="O fim do recorte tem que ser depois do inicio.")
    #     return
    if not turns.get().strip():
        erro.config(text="Escolha o json de diarizacao.")
        return
    estado["ok"] = True
    estado["saida"] = {
        "turns": turns.get().strip(), "timeline_name": nome.get().strip(),
        "fusion": fusion.get(), "grade": grade.get(),
        "copy_audio": audio.get(), "split_audio": split.get(),
        # campos escondidos: voltam como chegaram (constantes do topo)
        "remove_cut": d.get("remove_cut"), "silence_mode": d.get("silence_mode"),
        "resolution": d.get("resolution", ""), "mismatch": d.get("mismatch", ""),
        "range_start": d.get("range_start", ""), "range_end": d.get("range_end", ""),
    }
    root.destroy()


rodape = tk.Frame(root)
rodape.grid(row=estado["linha"], column=0, columnspan=3, sticky="e",
            padx=10, pady=12)
tk.Button(rodape, text="Cancelar", width=12, command=root.destroy).pack(side="left", padx=4)
tk.Button(rodape, text="Rodar", width=12, default="active", command=rodar).pack(side="left")
root.bind("<Return>", lambda _e: rodar())
root.bind("<Escape>", lambda _e: root.destroy())

root.eval("tk::PlaceWindow . center")
root.mainloop()
sys.stdout.write(json.dumps(estado["saida"]) if estado["ok"] else "")
"""


# Opcoes escondidas do dialogo (10/09): valem sempre as constantes do topo.
_OPCOES_FIXAS = {"remove_cut", "silence_mode", "resolution", "mismatch",
                 "range_start", "range_end"}


def opcoes_padrao():
    """As constantes do topo, na forma que o dialogo entende."""
    return {
        "turns": DEFAULT_TURNS_JSON,
        "timeline_name": NEW_TIMELINE_NAME,
        "fusion": COPY_FUSION_COMPS,
        "grade": COPY_COLOR_GRADE,
        "copy_audio": COPY_AUDIO,
        "split_audio": SPLIT_AUDIO_BY_SPEAKER,
        "remove_cut": REMOVE_CUT,
        "silence_mode": SILENCE_MODE,
        "resolution": (f"{TARGET_WIDTH}x{TARGET_HEIGHT}"
                       if TARGET_WIDTH and TARGET_HEIGHT else ""),
        "mismatch": MISMATCH_BEHAVIOR or "",
        "range_start": "" if RANGE_START is None else str(RANGE_START),
        "range_end": "" if RANGE_END is None else str(RANGE_END),
    }


def _ler_opcoes(folder):
    """As opcoes da ultima rodada daquele corte. {} se nao houver.

    Ficam NA PASTA DO JSON de diarizacao, e nao ao lado do script, porque a
    resposta certa muda por corte: um short de dois minutos e o episodio
    inteiro nao querem as mesmas caixas marcadas. E porque o script tem duas
    copias (esta e a de `Scripts\\Utility`) - guardar estado ao lado dele faria
    as duas discordarem.
    """
    if not folder:
        return {}
    path = os.path.join(folder, _OPCOES_ARQUIVO)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            salvo = json.load(f)
        if not isinstance(salvo, dict):
            return {}
        # `fill_gaps` (bool) virou `silence_mode` (tres estados) em 02/09.
        # Traduz o que ja esta gravado nos cortes em vez de ignorar: ignorar
        # abriria o dialogo com o padrao do script, e quem tinha desmarcado
        # "preencher buracos" veria a caixa marcada de novo sem entender por que.
        if "silence_mode" not in salvo and "fill_gaps" in salvo:
            salvo["silence_mode"] = "preencher" if salvo["fill_gaps"] else "buraco"
        salvo.pop("fill_gaps", None)
        return salvo
    except Exception as e:
        print(f"[!] {path} ilegivel ({e}) - seguindo com os padroes do script")
        return {}


def _gravar_opcoes(folder, opcoes):
    if not folder or not os.path.isdir(folder):
        return
    try:
        with open(os.path.join(folder, _OPCOES_ARQUIVO), "w",
                  encoding="utf-8") as f:
            json.dump(opcoes, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[!] nao consegui guardar as opcoes ({e}) - a proxima rodada "
              f"vai abrir o dialogo com os padroes do script")


def ask_settings(default_path):
    """Pergunta as configuracoes da rodada. Devolve o dict, ou None se
    cancelado.

    Os padroes sao, nesta ordem: as constantes do topo, o que foi rodado da
    ultima vez naquele corte, e o arquivo de diarizacao que o chamador sugeriu.

    Sem dialogo disponivel (nenhum python.exe externo, ou ele falhou), cai no
    caminho antigo: pergunta so' o arquivo e usa as opcoes gravadas - que ai
    sao IMPRESSAS inteiras, porque uma opcao que ninguem viu na tela e ninguem
    leu no log e' exatamente como se descobre, depois de 200 clipes, que o
    Fusion estava ligado.
    """
    padroes = opcoes_padrao()
    salvas = _ler_opcoes(_pasta_do_corte(default_path))
    # campo fora da tela nao pode herdar a ultima rodada: um corte que rodou
    # com silencio "remover" continuaria removendo sem ninguem ver a opcao
    padroes.update({k: v for k, v in salvas.items()
                    if k in padroes and k not in _OPCOES_FIXAS})
    if not os.path.isfile(padroes.get("turns") or ""):
        padroes["turns"] = default_path

    escolhido = _ask_settings_external(padroes)
    if escolhido == "":
        return None                     # cancelou no dialogo
    if escolhido is None:
        print("[i] dialogo de configuracoes indisponivel - perguntando so' o "
              "arquivo, com as opcoes da ultima rodada")
        turns = ask_turns_file(padroes["turns"])
        if turns is None:
            return None
        padroes["turns"] = turns
        return padroes

    _gravar_opcoes(_pasta_do_corte(escolhido["turns"]), escolhido)
    return escolhido


def _ask_settings_external(padroes):
    """Roda o dialogo num processo separado. Devolve o dict, "" se cancelou,
    ou None se nem deu pra abrir (ai o chamador cai pro caminho antigo)."""
    exe = _python_exe()
    if not exe:
        print("[!] nao achei um python.exe externo pro dialogo de "
              f"configuracoes (sys.base_prefix={sys.base_prefix!r})")
        return None
    try:
        r = subprocess.run(
            [exe, "-c", _SETTINGS_DIALOG_SNIPPET],
            input=json.dumps(padroes), capture_output=True, text=True,
            timeout=1800, creationflags=0x08000000)  # CREATE_NO_WINDOW
    except Exception as e:
        print(f"[!] dialogo de configuracoes falhou ({e})")
        return None
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        print(f"[!] dialogo de configuracoes saiu com codigo {r.returncode}"
              + (f": {err[-1]}" if err else ""))
        return None
    saida = (r.stdout or "").strip()
    if not saida:
        return ""
    try:
        return json.loads(saida)
    except ValueError as e:
        print(f"[!] resposta do dialogo ilegivel ({e})")
        return None


def aplicar_opcoes(o):
    """Escreve as escolhas nos globais e IMPRIME o que ficou valendo.

    Imprimir nao e' enfeite: com as opcoes vindo de um dialogo, o log deixa de
    ser a unica testemunha do que rodou - e continua sendo a unica que sobra
    depois, quando a pergunta for "por que este corte saiu sem grade".
    """
    global NEW_TIMELINE_NAME, COPY_AUDIO, SPLIT_AUDIO_BY_SPEAKER
    global SILENCE_MODE, REMOVE_CUT
    global COPY_FUSION_COMPS, COPY_COLOR_GRADE, TARGET_WIDTH, TARGET_HEIGHT
    global MISMATCH_BEHAVIOR, RANGE_START, RANGE_END

    def _f(chave):
        txt = str(o.get(chave) or "").strip().replace(",", ".")
        return float(txt) if txt else None

    NEW_TIMELINE_NAME = (o.get("timeline_name") or "").strip() or NEW_TIMELINE_NAME
    COPY_FUSION_COMPS = bool(o.get("fusion"))
    COPY_COLOR_GRADE = bool(o.get("grade"))
    COPY_AUDIO = bool(o.get("copy_audio"))
    SPLIT_AUDIO_BY_SPEAKER = bool(o.get("split_audio"))
    REMOVE_CUT = bool(o.get("remove_cut"))
    modo = (o.get("silence_mode") or "").strip().lower()
    if modo not in ("preencher", "buraco", "remover"):
        # Nao adivinha: um valor estranho aqui vem de um json editado a mao, e
        # escolher por conta propria seria decidir calado o que vira frame preto.
        if modo:
            print(f"[!] silence_mode {modo!r} desconhecido - usando "
                  f"{SILENCE_MODE!r}")
        modo = SILENCE_MODE
    SILENCE_MODE = modo
    res = (o.get("resolution") or "").strip().lower().replace(" ", "")
    if res:
        largura, altura = res.split("x")
        TARGET_WIDTH, TARGET_HEIGHT = int(largura), int(altura)
    else:
        TARGET_WIDTH = TARGET_HEIGHT = None
    MISMATCH_BEHAVIOR = (o.get("mismatch") or "").strip() or None
    RANGE_START, RANGE_END = _f("range_start"), _f("range_end")

    def sn(v):
        return "sim" if v else "nao"

    print("[i] configuracoes desta rodada:")
    print(f"      timeline nova     {NEW_TIMELINE_NAME}")
    print(f"      comps Fusion      {sn(COPY_FUSION_COMPS)}"
          f"      color grade   {sn(COPY_COLOR_GRADE)}")
    print(f"      audio             {sn(COPY_AUDIO)}"
          f"      por falante   {sn(SPLIT_AUDIO_BY_SPEAKER)}")
    print(f"      remover 'cut'     {sn(REMOVE_CUT)}"
          f"      silencio      {SILENCE_MODE}")
    print(f"      resolucao         "
          + (f"{TARGET_WIDTH}x{TARGET_HEIGHT}" if TARGET_WIDTH
             else "a da timeline de origem")
          + f"      encaixe   {MISMATCH_BEHAVIOR or 'herdado da origem'}")
    if RANGE_START is not None or RANGE_END is not None:
        print(f"      recorte           {RANGE_START}s -> {RANGE_END}s "
              f"(segundos absolutos na midia)")


def append_in_batches(mp, clips, batch_size=40, _base_index=0):
    """AppendToTimeline falha silenciosamente (retorna nada) em lotes muito
    grandes ou com um clipe invalido no meio. Quando um lote falha, subdivide
    recursivamente ate isolar o(s) clipe(s) problematico(s) e imprime o motivo
    (frame invalido) em vez de so reportar a contagem."""
    total = 0
    for i in range(0, len(clips), batch_size):
        chunk = clips[i:i + batch_size]
        added = mp.AppendToTimeline(chunk)
        got = len(added) if added else 0
        if got == len(chunk):
            total += got
            continue
        if got > 0:
            # sucesso parcial: nao da pra saber QUAIS tiveram sucesso, entao
            # nao reenviamos o lote (evita duplicar clipe) - so contamos e avisamos.
            total += got
            print(f"[!] lote {_base_index + i}-{_base_index + i + len(chunk)}: "
                  f"{got}/{len(chunk)} adicionados (sucesso parcial, nao reenviado "
                  f"pra evitar duplicar clipes)")
            continue
        if len(chunk) == 1:
            c = chunk[0]
            motivo = "startFrame >= endFrame" if c["startFrame"] >= c["endFrame"] else "motivo desconhecido"
            print(f"[!] clipe #{_base_index + i} falhou (track={c['trackIndex']} "
                  f"start={c['startFrame']} end={c['endFrame']} record={c['recordFrame']}) - {motivo}")
            continue
        # falha total (0 adicionados): seguro re-tentar subdividido
        print(f"[!] lote {_base_index + i}-{_base_index + i + len(chunk)}: "
              f"0/{len(chunk)} adicionados, subdividindo...")
        total += append_in_batches(mp, chunk, max(1, batch_size // 4), _base_index + i)
    return total


def copy_grades_in_batches(src_item, dest_items, batch_size=40):
    """CopyGrades(lista) so retorna Bool (sem dizer qual item falhou). Se um
    lote falhar, subdivide recursivamente ate isolar - mesma logica do
    append_in_batches, so que aqui e 1 chamada por LOTE em vez de por item
    (bem menos chamadas totais que o Fusion import, risco bem menor)."""
    total_ok = 0
    for i in range(0, len(dest_items), batch_size):
        chunk = dest_items[i:i + batch_size]
        try:
            ok = src_item.CopyGrades(chunk)
        except Exception as e:
            ok = False
            print(f"    [!] CopyGrades falhou ({e})")
        if ok:
            total_ok += len(chunk)
        elif len(chunk) > 1:
            total_ok += copy_grades_in_batches(src_item, chunk, max(1, batch_size // 4))
    return total_ok


def copy_timeline_settings(src_tl, dst_tl):
    """Copia resolucao, frame rate e demais settings da timeline original."""
    settings = src_tl.GetSetting() or {}
    if "useCustomSettings" in settings:
        try:
            dst_tl.SetSetting("useCustomSettings", settings["useCustomSettings"])
        except Exception:
            pass
    for key, val in settings.items():
        if key == "useCustomSettings":
            continue
        try:
            dst_tl.SetSetting(key, val)
        except Exception:
            pass


def apply_target_resolution(project, dst_tl, src_tl):
    """Forca resolucao vertical (TARGET_WIDTH x TARGET_HEIGHT) e aplica
    MISMATCH_BEHAVIOR. Sempre imprime a resolucao/mismatch da timeline de
    ORIGEM primeiro - se Claude_test nao for ja 1080x1920, o enquadramento
    (Zoom/Pan/Tilt) copiado dos clipes-fonte fica errado independente do
    mismatch escolhido (ver comentario em MISMATCH_BEHAVIOR)."""
    key = "timelineInputResMismatchBehavior"
    print(f"[i] origem '{src_tl.GetName()}': "
          f"{src_tl.GetSetting('timelineResolutionWidth')}x"
          f"{src_tl.GetSetting('timelineResolutionHeight')}  "
          f"mismatch={src_tl.GetSetting(key)!r}")
    # O aviso so' cabe quando ha uma resolucao FORCADA: sem ela a timeline nova
    # herda a da origem (copy_timeline_settings), a baseline de escala e' a
    # mesma, e o Zoom/Pan/Tilt copiado cai certo. Antes esta comparacao rodava
    # com TARGET_WIDTH = None e avisava "origem NAO e Nonexnone" - ruido no
    # unico caso em que nao havia nada a avisar.
    if TARGET_WIDTH and TARGET_HEIGHT and (
            src_tl.GetSetting("timelineResolutionWidth") != str(TARGET_WIDTH) or
            src_tl.GetSetting("timelineResolutionHeight") != str(TARGET_HEIGHT)):
        print(f"    [!] origem NAO e {TARGET_WIDTH}x{TARGET_HEIGHT} - o Zoom/Pan/Tilt "
              "copiado dos clipes-fonte foi autorado sobre outra baseline e vai sair "
              "errado nesta timeline, confira visualmente antes de confiar no resultado")

    if TARGET_WIDTH and TARGET_HEIGHT:
        try:
            dst_tl.SetSetting("useCustomSettings", "1")
            ok_w = dst_tl.SetSetting("timelineResolutionWidth", str(TARGET_WIDTH))
            ok_h = dst_tl.SetSetting("timelineResolutionHeight", str(TARGET_HEIGHT))
            if ok_w and ok_h:
                print(f"[i] resolucao da timeline nova: {TARGET_WIDTH}x{TARGET_HEIGHT}")
            else:
                print(f"[!] SetSetting nao confirmou {TARGET_WIDTH}x{TARGET_HEIGHT}, confira manualmente")
        except Exception as e:
            print(f"[!] falhou ao setar resolucao ({e}), confira manualmente em Project Settings")

    value = MISMATCH_BEHAVIOR if MISMATCH_BEHAVIOR is not None else src_tl.GetSetting(key)
    if not value:
        print(f"[!] MISMATCH_BEHAVIOR=None mas a origem nao tinha '{key}' setado, nada a herdar")
        return
    origem = "MISMATCH_BEHAVIOR" if MISMATCH_BEHAVIOR is not None else "herdado da timeline de origem"
    try:
        dst_tl.SetSetting(key, value)
        readback = dst_tl.GetSetting(key)
    except Exception as e:
        print(f"[!] falhou ao setar {key} ({e})")
        return
    if readback == value:
        print(f"[i] {key}={value!r} ({origem}), confirmado por readback")
    else:
        print(f"[!] {key} pedido={value!r} ({origem}) mas readback={readback!r} - nao colou, "
              "ajuste manualmente em Project Settings > Master Settings > Input Sizing Preset")


def copy_track_attrs(src_tl, dst_tl, track_type, count):
    """Copia nome, enable e lock de cada track (melhor esforco, ignora o que
    a API/edicao nao suportar)."""
    for idx in range(1, count + 1):
        try:
            name = src_tl.GetTrackName(track_type, idx)
            if name:
                dst_tl.SetTrackName(track_type, idx, name)
        except Exception:
            pass
        try:
            dst_tl.SetTrackEnable(track_type, idx, src_tl.GetIsTrackEnabled(track_type, idx))
        except Exception:
            pass
        try:
            dst_tl.SetTrackLock(track_type, idx, src_tl.GetIsTrackLocked(track_type, idx))
        except Exception:
            pass


def read_layers(src_tl):
    """Le cada track de video da timeline atual: media, offset e enquadramento."""
    layers = {}
    for idx in range(1, int(src_tl.GetTrackCount("video")) + 1):
        items = src_tl.GetItemListInTrack("video", idx)
        if not items:
            continue
        it = items[0]
        mpi = it.GetMediaPoolItem()
        if not mpi:
            print(f"[!] V{idx} sem media pool item, ignorando")
            continue

        props = it.GetProperty() or {}

        clip_color = None
        try:
            clip_color = it.GetClipColor()
        except Exception as e:
            print(f"[!] V{idx}: GetClipColor falhou ({e})")

        fusion_count = None
        try:
            fusion_count = it.GetFusionCompCount()
        except Exception as e:
            print(f"[!] V{idx}: GetFusionCompCount falhou ({e})")

        enabled = None
        try:
            enabled = it.GetClipEnabled()
        except Exception as e:
            print(f"[!] V{idx}: GetClipEnabled falhou ({e})")

        # export do(s) comp(s) Fusion NAO acontece aqui de proposito: rodar
        # ExportFusionComp nessa fase (antes da timeline nova existir) foi o
        # que causava a bridge de scripting corromper chamadas subsequentes
        # (V2/V3 inteiros zerados depois). Guardamos so a referencia do item
        # fonte pra exportar depois, isolado, no passo final de fusion.
        layers[idx] = {
            "mpi": mpi,
            "left_offset": int(it.GetLeftOffset()),
            "duration": int(it.GetDuration()),
            "props": props,
            "clip_color": clip_color,
            "fusion_count": fusion_count,
            "src_item": it,
            "enabled": enabled,
        }
        print(f"[i] V{idx}: {mpi.GetName()}  offset={layers[idx]['left_offset']}  "
              f"dur={layers[idx]['duration']}  props={len(props)}  "
              f"clip_color={clip_color!r}  fusion_comps={fusion_count}  "
              f"enabled={enabled}  Scaling={props.get('Scaling')!r}")
    return layers


def audio_source(src_tl, vlayer, clip_origin):
    """De onde tirar o audio: (layer com "mpi", frame_do_arquivo(x_absoluto)).

    Normalmente e' a propria midia da V1. Mas quando a V1 e' um compound clip
    (trecho + texto por jogador mesclados), o compound nao carrega o audio - o
    AppendToTimeline "da certo", sai [SUCESSO] e a A1 fica sem som (ep4,
    impostor_fantasma). Nesse caso o audio vem do clipe na A1 da
    timeline-fonte, alinhado pela posicao na timeline.
    """
    def pelo_video(x):
        return vlayer["left_offset"] + (x - clip_origin)
    try:
        nome = str(vlayer["mpi"].GetName() or "")
    except Exception:
        nome = ""
    if not nome.lower().startswith("compound clip"):
        return vlayer, pelo_video
    try:
        itens = src_tl.GetItemListInTrack("audio", 1) or []
    except Exception as e:
        print(f"[!] nao consegui ler a A1 da timeline-fonte ({e})")
        itens = []
    it = next((i for i in itens if i.GetMediaPoolItem()), None)
    if not it:
        print("[!] V1 e' compound clip e a A1 da timeline-fonte esta vazia - "
              "usando o audio do compound (pode sair mudo)")
        return vlayer, pelo_video
    mpi = it.GetMediaPoolItem()
    left_a, start_a = int(it.GetLeftOffset()), int(it.GetStart())
    start_v = int(vlayer["src_item"].GetStart())

    # x absoluto -> posicao na timeline-fonte -> frame do arquivo de audio
    def pelo_audio(x):
        return left_a + (start_v + (x - clip_origin) - start_a)
    print(f"[i] V1 e' compound clip - audio tirado da A1 da timeline-fonte "
          f"('{mpi.GetName()}', offset={left_a}, inicio={start_a})")
    return {"mpi": mpi}, pelo_audio


def media_base(pp, layer):
    """Frame do EPISODIO onde o frame 0 DA MIDIA da timeline-fonte cai.

    Editar direto do `episodio.mkv` da 0: o frame 0 do arquivo E' o frame 0 do
    episodio, e o `GetLeftOffset` sozinho ja e' o frame absoluto.

    Editar do trecho remuxado (`<corte>_<N>frames.mkv`) NAO da 0: aquele
    arquivo comeca no keyframe anterior ao corte, entao o frame 0 dele e' o
    frame `video_offset x fps` do episodio. Sem somar isso, um clipe inteiro
    na timeline reporta `GetLeftOffset = 0` e o script leria "este trecho
    comeca no segundo 0 do episodio" - todo turno cairia fora do range e
    sumiria calado. Aparar os N frames a mao tambem nao resolvia: daria
    offset N, nao o frame absoluto.

    Devolve (frames, nome) - `frames` e' 0 quando a midia nao e' o trecho do
    corte, que e' o caso normal.
    """
    esperado = (pp or {}).get("video")
    base = (pp or {}).get("video_origin_frame")
    try:
        nome = layer["mpi"].GetName()
    except Exception as e:
        print(f"[!] GetName do media pool item falhou ({e}) - "
              f"assumindo midia do episodio inteiro")
        return 0, None
    nome = os.path.basename(str(nome or ""))
    if esperado and base is not None and nome.lower() == esperado.lower():
        return int(base), nome
    # A midia e' o trecho de ALGUM corte (`<corte>_<N>frames.mkv`), mas nao o
    # deste. Quase sempre e' corte trocado: a timeline de um, o json de outro.
    # Foi o que aconteceu de verdade - `Eu_Duvido_13frames.mkv` na timeline com
    # os turnos do `Qual_mundo...`, 0 segmentos e o aviso generico mandando
    # "reposicione o clipe", que nao conserta nada.
    outro = re.match(r"(?i)^(.+)_(\d+)frames\.\w+$", nome)
    if outro and (not esperado or nome.lower() != esperado.lower()):
        print(f"[!] a midia da timeline e' o trecho do corte '{outro.group(1)}'"
              f", mas o json de diarizacao e' do corte "
              f"'{(pp or {}).get('corte')}'")
        print(f"[!] cortes diferentes: ou abra a timeline do outro corte, ou "
              f"escolha o json deste. Nao adianta reposicionar o clipe.")
        return 0, None
    # Compound clip: o nome ("Compound Clip 3") nao diz de que arquivo veio.
    # Se o trecho do corte cabe exatamente nele (a partir do frame 0 do trecho
    # o corte planejado inteiro fica dentro do compound), e' o trecho
    # embrulhado - caso real do ep4/impostor_fantasma, 0 segmentos sem isto.
    # Com base 0 os turnos (segundos absolutos do episodio) caem todos fora.
    if base is not None and nome.lower().startswith("compound clip"):
        try:
            frames = int(layer["mpi"].GetClipProperty("Frames") or 0)
        except Exception:
            frames = 0
        frames = frames or layer.get("duration") or 0
        ini = (pp or {}).get("origin_frame")
        dur = None
        if pp and pp.get("range_start") is not None and pp.get("range_end") is not None:
            dur = (float(pp["range_end"]) - float(pp["range_start"]))
        fps_c = (pp or {}).get("fps")
        cabe = (ini is not None and int(ini) >= int(base) and frames and
                (dur is None or not fps_c or
                 int(ini) + dur * float(fps_c) <= int(base) + frames + 1))
        if cabe:
            print(f"[!] a midia da timeline e' '{nome}' (compound clip) - "
                  f"assumindo que embrulha o trecho do corte ('{esperado}', "
                  f"comeca no frame {base} do episodio): o corte planejado "
                  f"cabe nos {frames} frames dele")
            return int(base), nome
    # nem o trecho do corte, nem o episodio: quase sempre e' o trecho
    # RENOMEADO (ou copiado pra outra pasta), e sem casar o nome o offset nao
    # e' compensado. Dizer isso aqui, com os dois nomes, em vez de deixar o
    # aviso generico de origem culpar o posicionamento do clipe.
    ep = (pp or {}).get("episodio")
    if esperado and base is not None and ep and nome.lower() != ep.lower():
        print(f"[!] a midia da timeline e' '{nome}', que nao e' o episodio "
              f"('{ep}') nem o trecho do corte ('{esperado}')")
        print(f"[!] se voce renomeou o trecho, o offset dele ({base} frames) "
              f"NAO esta sendo somado - renomeie de volta ou edite do episodio")
    return 0, None


MIN_SPAN_FRAMES = 2  # Resolve rejeita clipe com startFrame==endFrame (span de 1 frame)


def build_spans(turns, fps, layers, total_frames, range_a=0, range_b=None):
    """Converte turnos em spans (track, frame_ini, frame_fim) sem sobreposicao,
    dentro do intervalo [range_a, range_b) da track-fonte."""
    if range_b is None:
        range_b = total_frames

    spans = []
    for t in turns:
        nome = t.get("name")
        # descarte: marcado ANTES de consultar o NAME_TO_TRACK, porque os cortes
        # antigos ainda mandam "cut" pra V4 e obedecer aquilo traria de volta o
        # trecho que a marca pede pra tirar. O span segue vivo ate o fim desta
        # funcao (com drop=True) so' pra que o preenchimento de buracos saiba
        # que aquele tempo esta ocupado - senao a BASE_TRACK entraria tapando
        # justamente o que foi cortado.
        drop = REMOVE_CUT and nome in CUT_NAMES
        track = NAME_TO_TRACK.get(nome, BASE_TRACK)
        if track not in layers:
            track = BASE_TRACK
        a = max(range_a, int(round(t["start"] * fps)))
        b = min(range_b, int(round(t["end"] * fps)))
        if b > a:
            spans.append({"track": track, "a": a, "b": b, "drop": drop,
                          "motivo": "cut" if drop else None})

    spans.sort(key=lambda s: s["a"])

    # corta sobreposicoes: quem comeca depois manda
    for i in range(len(spans) - 1):
        if spans[i]["b"] > spans[i + 1]["a"]:
            spans[i]["b"] = spans[i + 1]["a"]

    # descarta span curto demais SEM abrir buraco: estende o anterior por cima
    # dele em vez de so filtrar (um span de 1-7 frames descartado vira flash
    # preto visivel no meio do corte, nao e "imperceptivel")
    limpos = []
    for s in spans:
        if s["b"] - s["a"] < MIN_SPAN_FRAMES:
            if limpos:
                limpos[-1]["b"] = max(limpos[-1]["b"], s["b"])
            continue
        limpos.append(s)
    spans = limpos

    if SILENCE_MODE == "buraco" or not spans:
        return spans

    # Cabeca, buracos e cauda - o SILENCIO. Duas saidas, e a diferenca entre
    # elas e' so' o que o buraco vira:
    #
    #   "preencher" -> clipe da BASE_TRACK cobrindo o tempo
    #   "remover"   -> span drop=True, que o main() tira e ripa pra tras
    #
    # Buraco >= MIN_SPAN_FRAMES vira span proprio; menor que isso NAO pode
    # virar CLIPE (o Resolve rejeita span < MIN_SPAN_FRAMES), entao no modo
    # "preencher" o vizinho estica pra cobrir - descartar deixava literalmente
    # 1 frame sem nenhuma track, bug confirmado nas pontas da timeline. No modo
    # "remover" esse limite nao existe: um span drop nunca vira clipe, entao
    # qualquer buraco, ate de 1 frame, pode ser marcado e sumir.
    remover = SILENCE_MODE == "remover"

    def _vazio(a, b):
        return {"track": BASE_TRACK, "a": a, "b": b, "drop": remover,
                "motivo": "silencio" if remover else None}

    filled, cursor = [], range_a
    for s in spans:
        gap = s["a"] - cursor
        if gap >= MIN_SPAN_FRAMES or (remover and gap > 0):
            filled.append(_vazio(cursor, s["a"]))
        elif gap > 0:
            if filled:
                filled[-1]["b"] = s["a"]
            else:
                s = {**s, "a": cursor}
        filled.append(s)
        cursor = s["b"]
    tail_gap = range_b - cursor
    if tail_gap >= MIN_SPAN_FRAMES or (remover and tail_gap > 0):
        filled.append(_vazio(cursor, range_b))
    elif tail_gap > 0 and filled:
        filled[-1]["b"] = range_b

    # junta preenchimentos vizinhos na mesma track. O drop entra na comparacao
    # porque um span descartado pode ter caido na BASE_TRACK (quando o mapa do
    # corte manda "cut" pra uma track que este stack nao tem) - sem isso ele
    # grudaria num preenchimento vizinho e um dos dois venceria calado.
    merged = [filled[0]]
    for s in filled[1:]:
        if (s["track"] == merged[-1]["track"] and s["a"] == merged[-1]["b"]
                and s["drop"] == merged[-1]["drop"]):
            merged[-1]["b"] = s["b"]
        else:
            merged.append(s)
    return merged


def main():
    # Tudo que muda de uma rodada pra outra e' perguntado ANTES de tocar no
    # projeto: escolher no meio do caminho significaria descobrir a escolha
    # errada com metade da timeline montada.
    # O corte da TIMELINE ABERTA manda no default; o turnsManual mais recente
    # so' entra quando a timeline nao e' um trecho exportado (episodio inteiro,
    # ou fluxo antigo do scriptsPrimarios).
    opcoes = ask_settings(_turns_do_trecho(_midia_da_timeline())
                          or DEFAULT_TURNS_JSON)
    if opcoes is None:
        banner(False, "Cancelado - nada foi criado.")
        return
    aplicar_opcoes(opcoes)
    turns_json = opcoes["turns"]
    print(f"[i] arquivo de diarizacao escolhido: {turns_json}")

    # se o json escolhido veio de um corte do pre_production, o mapa de tracks
    # daquele corte manda - e' a decisao que foi tomada na tela, sobre este
    # trecho especifico
    pasta = _pasta_do_corte(turns_json)
    pp = _read_preprod(pasta)
    if not pp and _parece_corte(turns_json):
        # Parar aqui e' o ponto: o mapa fixo la de cima e' de OUTRO episodio, e
        # usa-lo calado ja montou uma timeline inteira com as tracks trocadas.
        banner(False, f"Este json parece ser de um corte do pre_production, mas nao achei "
                       f"corte.json (nem speaker_switch.json) em {pasta} - sem isso nao da "
                       f"pra saber quem vai em qual track. Abra o corte na tela do "
                       f"pre_production pra ele ser gravado.")
        return
    if pp:
        global NAME_TO_TRACK, OFF_CAMERA_NAMES
        if pp.get("name_to_track"):
            NAME_TO_TRACK = {k: int(v) for k, v in pp["name_to_track"].items()}
        if pp.get("off_camera_names") is not None:
            # o `no_name` puro entra sempre, igual ao _off_camera_names() do
            # app.py: e' o rotulo de silencio que rodadas antigas carimbaram,
            # e com as vozes numeradas (no_name1..N) ele nao estaria na lista.
            OFF_CAMERA_NAMES = set(pp["off_camera_names"]) | {"no_name"}
        print(f"[i] pre_production: corte '{pp.get('corte')}' do projeto "
              f"'{pp.get('projeto')}'")
        print(f"[i] mapa de tracks vindo do {pp['fonte']}: {NAME_TO_TRACK}"
              f"  (fora de camera: {sorted(OFF_CAMERA_NAMES)})")
        print(f"[i] trecho {pp.get('range_start')}s - {pp.get('range_end')}s, "
              f"frame de origem esperado: {pp.get('origin_frame')}")
    else:
        print(f"[i] fora do pre_production (nenhuma pasta de corte no caminho) - "
              f"usando o mapa fixo do script: {NAME_TO_TRACK}")

    resolve = get_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    src_tl = project.GetCurrentTimeline()
    if not src_tl:
        banner(False, "Nenhuma timeline aberta.")
        return

    fps = float(src_tl.GetSetting("timelineFrameRate") or
                project.GetSetting("timelineFrameRate"))
    tl_start = int(src_tl.GetStartFrame())
    print(f"[i] '{src_tl.GetName()}' @ {fps} fps, start frame {tl_start}")

    layers = read_layers(src_tl)
    if not layers:
        banner(False, "Nenhum layer valido encontrado.")
        return
    if BASE_TRACK not in layers:
        banner(False, f"BASE_TRACK V{BASE_TRACK} nao existe no stack.")
        return

    if not os.path.exists(turns_json):
        banner(False, f"Nao achei {turns_json}")
        return
    with open(turns_json, encoding="utf-8") as f:
        turns = json.load(f)

    sem_nome = [i for i, t in enumerate(turns) if not t.get("name")]
    if sem_nome:
        banner(False, f"{len(sem_nome)} turno(s) sem campo \"name\" preenchido "
                       f"(indices {sem_nome[:10]}{'...' if len(sem_nome) > 10 else ''}). "
                       f"Rode o 5_name_speakers.py --turns de novo pra preencher.")
        return
    nomes_no_json = {t["name"] for t in turns}
    desconhecidos = nomes_no_json - set(NAME_TO_TRACK) - OFF_CAMERA_NAMES - CUT_NAMES
    if desconhecidos:
        banner(False, f"Nome(s) desconhecido(s) no json, nao estao em NAME_TO_TRACK, "
                       f"em OFF_CAMERA_NAMES nem em CUT_NAMES (provavel erro de digitacao "
                       f"numa edicao manual): {sorted(desconhecidos)}")
        return
    print(f"[i] nomes no json: {sorted(nomes_no_json)} - todos reconhecidos "
          f"({sorted((set(NAME_TO_TRACK) & nomes_no_json) - CUT_NAMES)} com track, "
          f"{sorted(OFF_CAMERA_NAMES & nomes_no_json)} fora de camera, "
          f"{sorted(CUT_NAMES & nomes_no_json)} descartado)")

    # Quem tem track no mapa mas a track nao existe na timeline aberta caia
    # calado na BASE_TRACK (build_spans) - com um so' falante de camera sobrando,
    # tudo virava UM clipe e a rodada terminava em [SUCESSO] sem corte nenhum
    # (caso real: corte 300x61, Cuper -> V3 numa timeline so' com V1/V2).
    sem_track = {n: NAME_TO_TRACK[n] for n in nomes_no_json
                 if n in NAME_TO_TRACK and n not in OFF_CAMERA_NAMES
                 and not (REMOVE_CUT and n in CUT_NAMES)
                 and NAME_TO_TRACK[n] not in layers}
    if sem_track:
        banner(False, f"O mapa de tracks manda {', '.join(f'{n} -> V{v}' for n, v in sorted(sem_track.items()))}, "
                       f"mas a timeline aberta '{src_tl.GetName()}' so' tem "
                       f"{', '.join(f'V{i}' for i in sorted(layers))}. Crie o enquadramento "
                       f"que falta na timeline ou corrija o track_map do corte.")
        return

    used_tracks = set(NAME_TO_TRACK.values()) | {BASE_TRACK}
    total_frames = min(l["duration"] for idx, l in layers.items() if idx in used_tracks)
    # clip_origin = frame ABSOLUTO na midia-fonte onde o frame 0 da timeline-fonte
    # comeca (GetLeftOffset). Os turnos do JSON de diarizacao usam segundos
    # ABSOLUTOS na midia-fonte (ex: 2610.0s pro trecho 43:30-fim) - entao o
    # range valido pra essa timeline e' [clip_origin, clip_origin+total_frames),
    # nao [0, total_frames). Descoberto na pratica: uma timeline-fonte que ja
    # so contem um TRECHO da gravacao (nao o episodio inteiro) tem left_offset
    # != 0, e usar RANGE_START em segundos "desde o inicio do episodio" contra
    # o frame 0 da timeline dava um range invalido (a bem maior que o total).
    # ...e a midia pode, ela mesma, ja comecar depois do frame 0 do episodio
    # (o trecho remuxado do corte). Nesse caso o GetLeftOffset e' relativo AO
    # ARQUIVO, e o frame absoluto e' a soma dos dois.
    mbase, mnome = media_base(pp, layers[BASE_TRACK])
    clip_origin = layers[BASE_TRACK]["left_offset"] + mbase
    # O corte foi PLANEJADO a partir de um frame (origin_frame) que a timeline
    # aberta no Resolve pode nao respeitar - se o clipe estiver posicionado
    # depois disso, os turnos do comeco caem fora do range e somem calados
    # (max(range_a, ...) os clampa). Nao da pra consertar daqui: a midia que
    # falta nao esta na timeline. So' avisar, com o numero, pra nao confundir
    # "comeco faltando" com bug do script.
    esperado = (pp or {}).get("origin_frame")
    if mbase:
        print(f"[i] a timeline-fonte usa o trecho do corte ({mnome}), que "
              f"comeca no frame {mbase} do episodio - somado ao offset do "
              f"clipe ({layers[BASE_TRACK]['left_offset']}), o frame absoluto "
              f"e' {clip_origin}")
    # Os N frames de sobra do trecho remuxado sao lixo de keyframe, nao
    # material escolhido: a timeline nova comeca no frame PLANEJADO, nao no
    # comeco do arquivo. Isso e' o que faz o `.srt` bater - ele e' gerado em
    # base timeline, descontando o inicio do corte, e assume que o frame 0 da
    # timeline E' o inicio do corte. Sem isto, toda legenda entraria N frames
    # adiantada. Nao vale pro episodio inteiro (mbase=0), onde a timeline-fonte
    # inteira e' escolha do editor.
    apara = (mbase and esperado is not None and not RANGE_START
             and clip_origin < int(esperado) < clip_origin + total_frames)
    if apara:
        print(f"[i] aparando os {int(esperado) - clip_origin} frames de sobra "
              f"do keyframe - a timeline nova comeca no corte planejado "
              f"(frame {esperado})")
    elif esperado is not None and int(esperado) != clip_origin:
        d = clip_origin - int(esperado)
        print(f"[!] o corte foi planejado a partir do frame {esperado}, mas a "
              f"timeline-fonte comeca no {clip_origin} ({d:+d} frames, "
              f"{d / fps:+.1f}s)")
        print(f"[!] {'os turnos antes disso serao cortados fora' if d > 0 else 'a timeline tem material antes do corte planejado'}"
              f" - reposicione o clipe na timeline se o comeco sair errado")
    if RANGE_START:
        range_a = max(clip_origin, int(round(RANGE_START * fps)))
    elif apara:
        range_a = int(esperado)
    else:
        range_a = clip_origin
    fim_arquivo = clip_origin + total_frames
    if RANGE_END:
        range_b = min(fim_arquivo, int(round(RANGE_END * fps)))
    elif apara and (pp or {}).get("range_end"):
        # a mesma logica da cabeca, do outro lado: o `-c copy` tambem estica a
        # CAUDA ate o fim do GOP (medido: 253 frames a mais no Eu_Duvido, os
        # dois remuxes). Sem cortar aqui, o preenchimento de silencio levaria
        # esse rabo pra timeline nova.
        range_b = min(fim_arquivo, int(round(float(pp["range_end"]) * fps)))
        if range_b < fim_arquivo:
            print(f"[i] e {fim_arquivo - range_b} frames de sobra no fim "
                  f"(cauda do GOP) - a timeline nova termina no corte planejado")
    else:
        range_b = fim_arquivo
    if range_a >= range_b:
        banner(False, f"RANGE_START/RANGE_END invalido (a={range_a} >= b={range_b} frames, "
                       f"clip_origin={clip_origin}, total={total_frames}).")
        return
    if range_a != clip_origin or range_b != clip_origin + total_frames:
        print(f"[i] recorte adicional: frames {range_a}-{range_b} de "
              f"{clip_origin}-{clip_origin + total_frames} disponiveis "
              f"({range_a / fps:.1f}s-{range_b / fps:.1f}s) - timeline nova comeca no frame 0")
    else:
        print(f"[i] sem recorte adicional - usando a timeline-fonte inteira "
              f"({clip_origin}-{clip_origin + total_frames} frames, "
              f"{clip_origin / fps:.1f}s-{(clip_origin + total_frames) / fps:.1f}s na midia-fonte)")
    spans = build_spans(turns, fps, layers, total_frames, range_a, range_b)

    # --- descarte dos trechos marcados (ripple) --------------------------
    # `rec` = onde o span comeca NA TIMELINE NOVA. Nao da pra usar
    # `s["a"] - range_a` como antes: com trechos removidos, isso deixaria o
    # buraco do trecho removido no lugar. Cada span anda pra tras o total ja
    # descartado ANTES dele. Descontar so' o descartado (em vez de um cursor
    # que soma as duracoes) preserva os buracos legitimos de quem roda com
    # SILENCE_MODE="buraco" - la o vazio e' intencional.
    tirado = {"cut": [0, 0], "silencio": [0, 0]}   # motivo -> [quantos, frames]
    descartados, descartado_frames, kept = 0, 0, []
    for s in spans:
        dur = s["b"] - s["a"]
        if s.get("drop"):
            descartados += 1
            descartado_frames += dur
            conta = tirado.setdefault(s.get("motivo") or "?", [0, 0])
            conta[0] += 1
            conta[1] += dur
            continue
        s["rec"] = tl_start + (s["a"] - range_a) - descartado_frames
        kept.append(s)
    spans = kept
    for motivo, (n, frames) in tirado.items():
        if n:
            print(f"[i] {motivo}: {n} trecho(s) removido(s), {frames} frames "
                  f"({frames / fps:.1f}s)")
    if descartados:
        print(f"[i] total removido: {descartado_frames} frames "
              f"({descartado_frames / fps:.1f}s) a menos na timeline nova")
    if not spans:
        banner(False, "Nada pra montar (0 segmentos calculados).")
        return

    per_track = {}
    for s in spans:
        per_track[s["track"]] = per_track.get(s["track"], 0) + 1
    print(f"[i] {len(turns)} turnos -> {len(spans)} segmentos {per_track}")

    # --- timeline nova, com tracks suficientes -------------------------
    mp = project.GetMediaPool()
    name = NEW_TIMELINE_NAME
    existing = {tl.GetName() for tl in [
        project.GetTimelineByIndex(i) for i in range(1, project.GetTimelineCount() + 1)
    ] if tl}
    n = 2
    while name in existing:
        name = f"{NEW_TIMELINE_NAME}_{n}"
        n += 1
    new_tl = mp.CreateEmptyTimeline(name)
    if not new_tl:
        banner(False, "Falhou ao criar a timeline.")
        return
    project.SetCurrentTimeline(new_tl)

    print("\n----- TIMELINE (resolucao / fill+crop) -----")
    copy_timeline_settings(src_tl, new_tl)
    print("[i] settings da timeline (resolucao/fps/etc) copiados do original")
    apply_target_resolution(project, new_tl, src_tl)

    needed = max(s["track"] for s in spans)
    while int(new_tl.GetTrackCount("video")) < needed:
        new_tl.AddTrack("video")
    copy_track_attrs(src_tl, new_tl, "video", needed)
    print(f"[i] tracks de video na timeline nova: {int(new_tl.GetTrackCount('video'))}")

    # --- monta a lista de clipes ---------------------------------------
    clips = []
    for s in spans:
        layer = layers[s["track"]]
        clips.append({
            "mediaPoolItem": layer["mpi"],
            "startFrame": layer["left_offset"] + (s["a"] - clip_origin),
            "endFrame": layer["left_offset"] + (s["b"] - clip_origin),
            "trackIndex": s["track"],
            "recordFrame": s["rec"],
            "mediaType": 1,          # video only
        })

    total_added = append_in_batches(mp, clips)
    print(f"[i] {total_added}/{len(clips)} segmentos de video adicionados")

    # --- reaplica o enquadramento, track por track (props/color/enabled) ---
    # IMPORTANTE: fusion import fica de FORA desse loop, num passo separado
    # rodado por ultimo (ver abaixo). ImportFusionComp chamado em massa
    # dentro do mesmo loop corrompeu a bridge de scripting: um clipe no meio
    # do V1 comecou a falhar em tudo (color/enabled/fusion) e V2/V3 inteiros
    # vieram zerados depois disso - a corrupcao e cumulativa/permanente pro
    # resto da execucao, entao isolamos o fusion pra nao arriscar o resto.
    print("\n----- CLIP PROPERTIES (transform / color) -----")
    items_by_track = {}
    for idx, layer in layers.items():
        if idx > needed or not layer["props"]:
            continue
        items_here = new_tl.GetItemListInTrack("video", idx) or []
        items_by_track[idx] = items_here
        applied, skipped = 0, 0
        skipped_keys = set()
        color_ok, color_fail = 0, 0
        enabled_ok, enabled_fail = 0, 0
        for item in items_here:
            for key, val in layer["props"].items():
                try:
                    ok_prop = item.SetProperty(key, val)
                except Exception:
                    ok_prop = False
                if ok_prop:
                    applied += 1
                else:
                    skipped += 1
                    skipped_keys.add(key)

            # clip color
            if layer["clip_color"] is not None:
                try:
                    if item.SetClipColor(layer["clip_color"]):
                        color_ok += 1
                    else:
                        color_fail += 1
                except Exception as e:
                    color_fail += 1
                    print(f"    [!] SetClipColor falhou: {e}")

            # enable clip (o "checkbox")
            if layer["enabled"] is not None:
                try:
                    if item.SetClipEnabled(layer["enabled"]):
                        enabled_ok += 1
                    else:
                        enabled_fail += 1
                except Exception as e:
                    enabled_fail += 1
                    print(f"    [!] SetClipEnabled falhou: {e}")

        if items_here:
            print(f"[i] enquadramento reaplicado em V{idx} ({len(items_here)} clipes, "
                  f"{applied} propriedades aplicadas, {skipped} ignoradas/read-only)")
            if skipped_keys:
                print(f"    propriedades ignoradas: {sorted(skipped_keys)}")
            print(f"    clip color: {color_ok} ok / {color_fail} falhas "
                  f"(original={layer['clip_color']!r})")
            print(f"    clip enabled: {enabled_ok} ok / {enabled_fail} falhas "
                  f"(original={layer['enabled']})")

    # --- color grade (Color page: nodes/wheels/curves), passo separado ---
    # CopyGrades(lista) copia da fonte pra varios clipes numa chamada so (nao
    # e feito no loop de props porque e uma chamada por TRACK, nao por item -
    # mais barato e mais seguro chamar isolado). Isso e o grade real da
    # pagina Color, diferente do "clip color" (label/tag) que ja e copiado
    # no passo de CLIP PROPERTIES acima.
    print("\n----- COLOR GRADE -----")
    if not COPY_COLOR_GRADE:
        print("[i] COPY_COLOR_GRADE=False, pulando")
    for idx, layer in layers.items():
        if idx > needed or not COPY_COLOR_GRADE:
            continue
        items_here = items_by_track.get(idx) or []
        if not items_here:
            continue
        grade_ok = copy_grades_in_batches(layer["src_item"], items_here)
        print(f"[i] color grade em V{idx}: {grade_ok}/{len(items_here)} clipes ok")

    # --- fusion comps: passo separado, por ultimo -----------------------
    # export TAMBEM fica aqui (nao mais em read_layers): exportar la, antes
    # da timeline nova existir, foi o que corrompia chamadas subsequentes.
    # Isolando export+import inteiramente no ultimo passo, mesmo se ainda
    # corromper algo, ja e depois de props/color/enabled terem rodado 100%.
    print("\n----- FUSION COMPS -----")
    if COPY_FUSION_COMPS:
        try:
            os.makedirs(_FUSION_TMP_DIR, exist_ok=True)
        except Exception as e:
            print(f"[!] falhou ao criar {_FUSION_TMP_DIR} ({e})")
    for idx, layer in layers.items():
        if idx > needed or not COPY_FUSION_COMPS or not layer["fusion_count"]:
            continue
        fusion_paths = []
        for comp_idx in range(1, layer["fusion_count"] + 1):
            path = os.path.join(_FUSION_TMP_DIR, f"V{idx}_comp{comp_idx}.comp")
            try:
                ok_export = layer["src_item"].ExportFusionComp(path, comp_idx)
            except Exception as e:
                ok_export = False
                print(f"[!] V{idx}: ExportFusionComp #{comp_idx} falhou ({e})")
            if ok_export and os.path.exists(path) and os.path.getsize(path) > 0:
                fusion_paths.append(path)
            else:
                print(f"[!] V{idx}: ExportFusionComp #{comp_idx} nao gerou arquivo valido")
        if not fusion_paths:
            continue

        items_here = items_by_track.get(idx) or []
        fusion_ok, fusion_fail = 0, 0
        range_ok, range_fail = 0, 0
        sample_printed = False
        for item in items_here:
            for path in fusion_paths:
                try:
                    comp = item.ImportFusionComp(path)
                except Exception as e:
                    comp = None
                    print(f"    [!] ImportFusionComp falhou: {e}")
                if not comp:
                    fusion_fail += 1
                    continue
                fusion_ok += 1
                # o comp foi exportado do clipe fonte (93358 frames inteiros)
                # e importado num clipe novo bem mais curto (so o trecho do
                # turno) - sem realinhar o range, o Resolve pede o frame local
                # 0 do clipe novo mas o comp espera o range antigo, e o
                # MediaOut1 falha no render ("MediaOut1 failed at time 0",
                # fora do nosso script). Realinha pro range local do clipe.
                new_len = int(item.GetDuration())
                before = None
                if not sample_printed:
                    try:
                        a = comp.GetAttrs()
                        before = (a.get("COMPN_GlobalStart"), a.get("COMPN_GlobalEnd"),
                                  a.get("COMPN_RenderStart"), a.get("COMPN_RenderEnd"))
                    except Exception as e:
                        print(f"    [!] GetAttrs (antes) falhou: {e}")
                try:
                    comp.SetAttrs({
                        "COMPN_GlobalStart": 0,
                        "COMPN_GlobalEnd": new_len - 1,
                        "COMPN_RenderStart": 0,
                        "COMPN_RenderEnd": new_len - 1,
                    })
                    range_ok += 1
                except Exception as e:
                    range_fail += 1
                    print(f"    [!] SetAttrs (range) falhou: {e}")
                if not sample_printed:
                    sample_printed = True
                    after = None
                    try:
                        a = comp.GetAttrs()
                        after = (a.get("COMPN_GlobalStart"), a.get("COMPN_GlobalEnd"),
                                 a.get("COMPN_RenderStart"), a.get("COMPN_RenderEnd"))
                    except Exception as e:
                        print(f"    [!] GetAttrs (depois) falhou: {e}")
                    print(f"    amostra (1o clipe, duracao={new_len}): "
                          f"antes(Global/RenderStart/End)={before}  "
                          f"pedido=(0, {new_len - 1}, 0, {new_len - 1})  "
                          f"depois(readback)={after}")
        if items_here:
            print(f"[i] fusion comp em V{idx}: {fusion_ok} ok / {fusion_fail} falhas "
                  f"(original tinha {layer['fusion_count']} comp(s), "
                  f"{len(fusion_paths)} exportado(s) da fonte)")
            print(f"    range realinhado (COMPN_Global/RenderStart/End): "
                  f"{range_ok} ok / {range_fail} falhas")

    # --- audio ----------------------------------------------------------
    total_audio = None
    audio_expected = 0
    if COPY_AUDIO:
        print("\n----- AUDIO -----")
        base, af = audio_source(src_tl, layers[BASE_TRACK], clip_origin)
        if SPLIT_AUDIO_BY_SPEAKER:
            while int(new_tl.GetTrackCount("audio")) < needed:
                new_tl.AddTrack("audio")
            copy_track_attrs(src_tl, new_tl, "audio", min(needed, int(src_tl.GetTrackCount("audio"))))
            audio_clips = [{
                "mediaPoolItem": base["mpi"],
                "startFrame": af(s["a"]),
                "endFrame": af(s["b"]),
                "trackIndex": s["track"],
                "recordFrame": s["rec"],
                "mediaType": 2,          # audio only
            } for s in spans]
            audio_expected = len(audio_clips)
            total_audio = append_in_batches(mp, audio_clips)
            print(f"[i] {total_audio}/{audio_expected} clipes de audio, "
                  f"1 track por speaker (A1..A{needed})")
        elif descartados:
            # Com trecho removido nao da pra usar o clipe unico abaixo: o video
            # encurtou e o audio nao, entao TUDO depois do primeiro corte sai
            # fora de sincronia. Aqui o audio e' fatiado nos mesmos spans do
            # video (mesmos frames, mesmo `rec`), o que garante a sincronia por
            # construcao - ao preco de uma emenda por corte (risco de clique,
            # o motivo de o caminho de clipe unico existir).
            audio_clips = [{
                "mediaPoolItem": base["mpi"],
                "startFrame": af(s["a"]),
                "endFrame": af(s["b"]),
                "trackIndex": 1,
                "recordFrame": s["rec"],
                "mediaType": 2,          # audio only
            } for s in spans]
            audio_expected = len(audio_clips)
            total_audio = append_in_batches(mp, audio_clips)
            print(f"[i] {total_audio}/{audio_expected} clipes de audio em A1, "
                  f"fatiado nos mesmos spans do video (por causa dos "
                  f"{descartados} trecho(s) removido(s))")
        else:
            audio_expected = 1
            added = mp.AppendToTimeline([{
                "mediaPoolItem": base["mpi"],
                "startFrame": af(range_a),
                "endFrame": af(range_b),
                "trackIndex": 1,
                "recordFrame": tl_start,
                "mediaType": 2,          # audio only
            }])
            total_audio = len(added) if added else 0
            print("[i] audio original em A1" if total_audio else "[!] falhou ao adicionar audio em A1")

    ok = total_added == len(clips) and (total_audio is None or total_audio == audio_expected)
    if ok:
        resumo = f"'{name}' pronta ({total_added} segmentos de video"
        if total_audio is not None:
            resumo += f", {total_audio} clipes de audio"
        resumo += ")."
        banner(True, resumo)
    else:
        banner(False, f"'{name}' criada mas incompleta: "
                       f"{total_added}/{len(clips)} video, "
                       f"{total_audio}/{audio_expected} audio. Veja os avisos [!] acima.")


# Roda ao ser EXECUTADO - e' assim que o Resolve chama este arquivo (ele
# executa o .py; nao importa).
#
# O guarda nao e' o `__name__ == "__main__"` de sempre de proposito: nao esta
# garantido que o host de scripts do Resolve execute isto como `__main__`, e um
# guarda que erre ai vira o pior sintoma que este projeto conhece - "rodei e nao
# aconteceu nada". Escrito ao contrario, ele so' se cala no unico caso em que
# tem que se calar: `import SpeakerSwitch`, que e' como o teste do dialogo
# alcanca as funcoes sem montar timeline nenhuma.
if __name__ != "SpeakerSwitch":
    try:
        main()
    except Exception as e:
        banner(False, f"Erro inesperado: {e}")
        raise
