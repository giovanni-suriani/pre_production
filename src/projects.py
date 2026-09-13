r"""Projetos e cortes - os dois manifestos que sustentam o app.

    projects\
      <projeto>\
        project.json           etapa 1: fonte, wav, participantes, fps
        media\<projeto>.wav    audio extraido, 16 kHz mono
        cortes\
          corte_shorts1\
            corte.json         etapa 2: trecho, offsets, tracks, rodadas.
                               E' tambem o que o editor_proxy\SpeakerSwitch.py
                               le pra saber quem vai em qual track.
            audio.wav          o trecho fatiado (comeca no zero)
            <corte>_<N>frames.mkv   trecho remuxado; N = frames de offset
            speaker_samples\   amostras por voz, pra descobrir quem e' quem
            speaker_switch.json  arquivo-ponte aposentado em 02/09; ainda lido
                               como fallback nos cortes que ja tem um
            turns\             etapa 2: turnsXxx.json (tempo ABSOLUTO),
                                turnsXxx.raw.json (saida crua do script),
                                backups .bak.json, importados transcricao_*.json
            legendas\          etapa 2: .srt/.vtt e .giautosubs.json gerados

        Midia, manifesto e amostras ficam soltos na raiz do corte de proposito
        - so o que uma RODADA de metodo produz (turnos e legendas) mora em
        subpasta. `turns_dir()`/`legendas_dir()` sao a fonte unica disso;
        `migrate_layout()` move o que sobrou de cortes criados antes desta
        organizacao (roda uma vez no boot, idempotente).

Por que manifesto e nao banco: o que importa aqui sao arquivos que outros
programas (Resolve, os scripts, o proprio usuario) vao abrir. Um json ao lado
dos arquivos que descreve continua legivel se este app sumir - um .db nao.

O campo que mais importa e' `audio_offset`. Ele e' o que faz "43:30" parar de
ser uma pegadinha: o wav do corte comeca no zero, os turnos ficam em tempo
absoluto, e a diferenca entre os dois esta ESCRITA, nao subentendida.
"""

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

import config
import timecode as tc

SCHEMA = 1
OFF_CAMERA_DEFAULT = "no_name"
MANUAL_TRACK_NAME = "cut"          # nao e' pessoa: e' a track do corte manual
SEATS = ["left", "center", "right", "offcam", "none"]


class ProjectError(ValueError):
    pass


class NotFound(ProjectError):
    """Separado pra virar 404 em vez de 400 - "nao existe" nao e' "pedido
    malformado", e a interface trata os dois de formas diferentes."""


# ------------------------------------------------------------------ nomes

def slugify(name):
    """Nome de pasta seguro, preservando o que da pra preservar.

    Vira nome de pasta e entra em linha de comando, entao acento/espaco saem;
    mas 'Episódio Piloto' deve continuar reconhecivel como 'Episodio_Piloto',
    nao virar um hash.
    """
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\-. ]+", "", s, flags=re.ASCII).strip()
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._-")
    if not s:
        raise ProjectError(f"nome invalido: {name!r}")
    return s[:80]


def _child(root, name):
    """Resolve `name` como filho direto de `root`. Barra '..' e caminho solto."""
    root = Path(root).resolve()
    p = (root / str(name)).resolve()
    if p.parent != root:
        raise ProjectError(f"nome fora da pasta permitida: {name!r}")
    return p


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read(path):
    # utf-8-sig: manifesto editado a mao no Windows costuma vir com BOM, e
    # utf-8 puro rejeitaria o arquivo inteiro por causa de 3 bytes invisiveis
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------- projeto

def project_dir(slug):
    return _child(config.projects_dir(), slug)


def list_projects():
    out = []
    root = config.projects_dir()
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        f = d / "project.json"
        if not f.is_file():
            continue
        try:
            p = _read(f)
        except Exception as e:
            out.append({"slug": d.name, "name": d.name, "broken": str(e)})
            continue
        p["cuts"] = [c["name"] for c in list_cuts(d.name)]
        out.append(p)
    return out


def load_project(slug):
    f = project_dir(slug) / "project.json"
    if not f.is_file():
        raise NotFound(f"projeto nao encontrado: {slug}")
    return _read(f)


def save_project(p):
    p["updated"] = _now()
    _write(project_dir(p["slug"]) / "project.json", p)
    return p


def new_project(name, source_video, participants, info, off_camera=None):
    """Cria a pasta e o manifesto. O wav vem depois, num job.

    `fps` sai do ffprobe e fica gravado aqui porque TUDO depende dele:
    `int(round(segundos * fps))` e' a mesma conta do SpeakerSwitch, do
    timecode.py e do aviso de "turno curto demais". Um projeto 30 fps com fps
    60 gravado erraria todo corte pela metade, silenciosamente.
    """
    slug = slugify(name)
    d = project_dir(slug)
    if d.exists():
        raise ProjectError(f"ja existe um projeto chamado {slug!r}")
    seen = set()
    parts = []
    for p in participants:
        pname = str(p.get("name", "")).strip()
        if not pname:
            continue
        if pname.lower() in seen:
            raise ProjectError(f"participante repetido: {pname}")
        seen.add(pname.lower())
        seat = p.get("seat") or "none"
        if seat not in SEATS:
            raise ProjectError(f"posicao invalida: {seat!r}")
        parts.append({"name": pname, "seat": seat})
    if not parts:
        raise ProjectError("um projeto precisa de pelo menos um participante")
    # `[]` e' uma resposta legitima ("nao tem ninguem falando fora de quadro")
    # e precisa sobreviver: `or` a transformaria de volta no default e o
    # projeto voltaria a procurar uma voz a mais do que existe.
    off = [OFF_CAMERA_DEFAULT] if off_camera is None else list(off_camera)

    (d / "media").mkdir(parents=True, exist_ok=True)
    (d / "cortes").mkdir(parents=True, exist_ok=True)
    proj = {
        "schema": SCHEMA,
        "slug": slug,
        "name": str(name).strip(),
        "created": _now(),
        "updated": _now(),
        "source_video": str(source_video),
        "media": info,
        "fps": float(info.get("fps") or config.CONFIG["fps_fallback"]),
        "duration": float(info.get("duration") or 0.0),
        # nomes que NAO tem track propria - caem na BASE_TRACK (V1) no
        # SpeakerSwitch. Espelha OFF_CAMERA_NAMES la.
        "off_camera": off,
        "participants": parts,
        "audio": f"media/{slug}.wav",
        "audio_info": None,
        "status": "sem áudio",
    }
    save_project(proj)
    return proj


def project_audio(p):
    return project_dir(p["slug"]) / p["audio"].replace("/", "\\")


def speaker_names(p):
    """Todo mundo que pode aparecer como rotulo: pessoas + fora de quadro."""
    return [x["name"] for x in p["participants"]] + list(p.get("off_camera", []))


def roster(p):
    """O elenco do projeto: cadeira + nome, gente em quadro primeiro.

    E' o que os metodos do Gemini recebem em `--roster` para montar o prompt
    daquele projeto - "duas pessoas, uma na esquerda e uma na direita, nao tem
    ninguem no centro" em vez do texto fixo de tres cadeiras que existia
    quando so havia o EpisodioPiloto. Ver `scriptsPrimarios\roster.py`.
    """
    out = [{"seat": x.get("seat") or "none", "name": x["name"]}
           for x in p["participants"]]
    out += [{"seat": "offcam", "name": n} for n in p.get("off_camera", [])]
    return out


def roster_arg(p):
    """O elenco em uma linha: `left=Giovanni;right=Heitor;offcam=no_name`."""
    return ";".join(f"{x['seat']}={x['name']}" for x in roster(p))


def seat_map(p):
    """cadeira -> nome do participante. Usado pra traduzir a saida do 3c_,
    que rotula por posicao com nomes fixos no codigo dele."""
    out = {}
    for x in p["participants"]:
        if x.get("seat") and x["seat"] not in ("none",):
            out[x["seat"]] = x["name"]
    for name in p.get("off_camera", []):
        out.setdefault("offcam", name)
    return out


# ------------------------------------------------------------------ corte

def cuts_dir(slug):
    return project_dir(slug) / "cortes"


def entire_transcript_path(slug):
    """`entire_transcribe.json` - a transcricao do EPISODIO inteiro, solta em
    cortes\\, ao lado das pastas de corte (nao dentro de uma). Nasce do wav do
    PROJETO, na etapa 1, antes de qualquer corte existir; um corte novo pode
    reaproveita-la recortando por tempo em vez de rodar o Whisper de novo (ver
    turns.crop_absolute)."""
    return cuts_dir(slug) / "entire_transcribe.json"


def suggested_shorts_path(slug):
    """`suggested_shorts.json` - os trechos que o Gemini sugere a partir de
    `entire_transcript_path`, no mesmo lugar e pela mesma razao."""
    return cuts_dir(slug) / "suggested_shorts.json"


def cut_dir(slug, cut_name):
    return _child(cuts_dir(slug), cut_name)


def turns_dir(slug, cut_name):
    """Onde moram os turnsXxx.json (diarizacao/transcricao) deste corte -
    tudo que uma rodada de metodo produz, mais o que o editor de turnos salva
    a mao e o que vem importado de fora. Nao inclui `corte.json` (manifesto),
    midia, nem `speaker_samples\\` (essas continuam soltas na raiz do corte -
    ver MEMORY/plano da reorganizacao)."""
    d = cut_dir(slug, cut_name) / "turns"
    d.mkdir(parents=True, exist_ok=True)
    return d


def legendas_dir(slug, cut_name):
    """Onde moram os .srt/.vtt/.giautosubs.json gerados pra este corte."""
    d = cut_dir(slug, cut_name) / "legendas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_cuts(slug):
    out = []
    d = cuts_dir(slug)
    if not d.is_dir():
        return out
    for c in sorted(d.iterdir()):
        f = c / "corte.json"
        if f.is_file():
            try:
                out.append(_read(f))
            except Exception as e:
                out.append({"name": c.name, "broken": str(e)})
    return out


def load_cut(slug, cut_name):
    f = cut_dir(slug, cut_name) / "corte.json"
    if not f.is_file():
        raise NotFound(f"corte nao encontrado: {slug}/{cut_name}")
    return _read(f)


def save_cut(slug, cut):
    cut["updated"] = _now()
    _write(cut_dir(slug, cut["name"]) / "corte.json", cut)
    return cut


def new_cut(p, name, start, end, track_map=None, speakers=None):
    """Cria o corte. O offset nasce aqui, e e' o coracao do projeto.

    `start` vira, ao mesmo tempo:
      * o ponto onde o ffmpeg fatia o wav;
      * o `audio_offset` que o editor soma pra alinhar onda e turnos;
      * o `origin_frame`, que e' o `clip_origin` (GetLeftOffset) esperado da
        timeline-fonte no Resolve - 43:30 da 156600 em 60 fps, o mesmo numero
        que ja aparecia na timeline do EpisodioPiloto.

    Tres coisas, um numero so, escrito num lugar so.
    """
    slug = p["slug"]
    cname = slugify(name)
    d = cut_dir(slug, cname)
    if d.exists():
        raise ProjectError(f"ja existe um corte chamado {cname!r}")
    start, end = float(start), float(end)
    dur_total = float(p.get("duration") or 0.0)
    if end <= start:
        raise ProjectError("o fim do corte tem que ser depois do inicio")
    if start < 0 or (dur_total and end > dur_total + 0.5):
        raise ProjectError(f"o corte tem que caber no episodio "
                           f"(0 - {tc.format_time(dur_total)})")
    fps = float(p["fps"])
    d.mkdir(parents=True, exist_ok=True)
    cut = {
        "schema": SCHEMA,
        "name": cname,
        "project": slug,
        "created": _now(),
        "updated": _now(),
        "start": round(start, 5),
        "end": round(end, 5),
        "duration": round(end - start, 5),
        "fps": fps,
        # o frame do episodio onde este corte comeca - mesma conta do
        # SpeakerSwitch: int(round(segundos * fps))
        "origin_frame": tc.seconds_to_frame(start, fps),
        # base de tempo dos turns*.json canonicos deste corte. Sempre absoluta:
        # ver o topo de turns.py.
        "time_base": "absolute",
        "audio": "audio.wav",
        # segundos a somar no tempo do wav pra chegar no tempo dos turnos
        "audio_offset": round(start, 5),
        "video": None,
        # o video remuxado pode comecar ANTES do corte (keyframe) - por isso
        # tem offset proprio, medido, em vez de assumir que e' o mesmo. O
        # mesmo valor em frames vai no NOME do arquivo (`_<N>frames.mkv`)
        "video_offset": None,
        "video_offset_frames": None,
        "track_map": dict(track_map or default_track_map(p)),
        "off_camera": list(p.get("off_camera", [])),
        "speakers": int(speakers or default_speakers(p)),
        "runs": [],
        "status": "sem áudio",
    }
    save_cut(slug, cut)
    return cut


def default_track_map(p):
    """Cadeira vira track: esquerda V1, centro V2, direita V3, `cut` V4.

    E' a ordem que ja estava no NAME_TO_TRACK do SpeakerSwitch. Quem esta fora
    de quadro NAO entra: sem track propria, cai na BASE_TRACK de proposito.
    """
    order = {"left": 1, "center": 2, "right": 3}
    used, tmap = set(), {}
    for x in p["participants"]:
        t = order.get(x.get("seat"))
        if t and t not in used:
            tmap[x["name"]] = t
            used.add(t)
    nxt = 1
    for x in p["participants"]:
        if x["name"] in tmap:
            continue
        while nxt in used:
            nxt += 1
        tmap[x["name"]] = nxt
        used.add(nxt)
    nxt = max(used, default=0) + 1
    tmap[MANUAL_TRACK_NAME] = nxt
    return tmap


def default_speakers(p):
    """Quantas vozes o diarizador deve procurar: gente na mesa + fora de quadro.

    Foi exatamente o caso do EpisodioPiloto - 3 na camera e uma quarta voz sem
    enquadramento. Pedir 3 fazia o pyannote enfiar duas pessoas num label so.
    """
    return len(p["participants"]) + len(p.get("off_camera", []))


def cut_audio(slug, cut):
    return cut_dir(slug, cut["name"]) / cut["audio"]


def cut_turns_files(slug, cut, fps=None, min_frames=None):
    """Os turns*.json deste corte (pasta `turns\\`), com um resumo de cada."""
    import turns as T
    d = turns_dir(slug, cut["name"])
    fps = fps or cut["fps"]
    min_frames = min_frames or config.CONFIG["min_span_frames"]
    out = []
    for f in sorted(d.glob("*.json")):
        if f.name in ("corte.json", "speaker_switch.json"):
            continue
        try:
            s = T.summarize(f, fps, min_frames)
        except Exception:
            continue
        if not s:
            continue
        s.update({"name": f.name, "mtime": f.stat().st_mtime,
                  "raw": f.name.endswith(".raw.json"),
                  "backup": ".bak." in f.name})
        out.append(s)
    return out


# ------------------------------------------- ponte com o editor_proxy
#
# Aqui morava write_speaker_switch(), que gravava um `speaker_switch.json` com
# uma copia de `track_map`, `off_camera`, `start`/`end`, `fps` e `origin_frame`
# pro editor_proxy\SpeakerSwitch.py ler. Aposentado em 02/09: aquele script le
# o `corte.json` direto agora.
#
# O que a copia custava: ela so' existia se alguem clicasse no botao da tela, e
# nao clicar nao dava erro - o SpeakerSwitch caia calado no NAME_TO_TRACK fixo
# do topo dele, que e' de outro episodio. Aconteceu num corte do Episodio1, e
# so' apareceu porque os nomes eram outros; com os mesmos nomes em cadeiras
# trocadas, teria montado a timeline inteira errada sem um aviso.


# --------------------------------------------------- migracao turns/legendas

def _migrate_cut_layout(d):
    """Move os arquivos de UM corte pra `turns\\`/`legendas\\`, se ainda
    estiverem soltos na raiz (de antes desta organizacao existir).

    So MOVE - nunca sobrescreve nem apaga. Arquivo que este app nao reconhece
    (.ass, chunk*.mp4, legendas_sem_cut.json e afins) fica onde esta: nao e'
    turns nem legenda por definicao deste app, e' de outra ferramenta. O
    `.lua` e' excecao - roda junto de legenda (Aegisub), entao conta.
    """
    moved = []
    for f in sorted(d.iterdir()):
        if not f.is_file():
            continue
        dest_root = None
        if f.name.startswith("turns") or f.name.startswith("transcricao_"):
            dest_root = turns_dir(*_slug_and_cut_from_dir(d))
        elif (f.suffix.lower() in (".srt", ".vtt", ".lua")
              or f.name.endswith(".giautosubs.json")):
            dest_root = legendas_dir(*_slug_and_cut_from_dir(d))
        if dest_root is None:
            continue
        dest = dest_root / f.name
        if dest.exists():
            print(f"[!] migracao: {dest} ja existe, deixando {f} onde esta")
            continue
        shutil.move(str(f), str(dest))
        moved.append(str(dest))
    return moved


def _slug_and_cut_from_dir(d):
    # cortes\<projeto>\cortes\<corte> - so usado pela migracao, pra reusar
    # turns_dir()/legendas_dir() (que recriam o Path a partir do slug) em vez
    # de duplicar a regra de onde a subpasta fica.
    return d.parent.parent.name, d.name


def migrate_layout():
    """Roda a migracao em TODOS os cortes de TODOS os projetos. Idempotente -
    seguro chamar toda subida do servidor (e' o que app.py faz)."""
    moved = []
    root = config.projects_dir()
    if not root.is_dir():
        return moved
    for proj_dir in sorted(root.iterdir()):
        cortes = proj_dir / "cortes"
        if not cortes.is_dir():
            continue
        for cut_d in sorted(cortes.iterdir()):
            if cut_d.is_dir() and (cut_d / "corte.json").is_file():
                moved += _migrate_cut_layout(cut_d)
    return moved
