"""pre_production - servidor das tres etapas.

    /          etapa 1  ProjectEditor  mp4 -> wav, nome, participantes
    /cortes    etapa 2  CutsEditor     trecho, tracks, metodo, rodada
    /turnos    etapa 3  turnsEditor    corrigir os turnos na onda

A etapa 3 e' o turnsEditor: `static/app.js` e `static/style.css` sao copias
literais de `scriptsPrimarios\\turnsEditor\\` (copia, nao mudanca de lugar - o
original continua funcionando onde sempre esteve). Para que a copia continue
sendo literal, este servidor RESPONDE A MESMA API que o app.js ja chamava:
/api/config, /api/turns, /api/transcript, /api/peaks, /api/audio, com os
mesmos formatos. A diferenca e' de onde vem a resposta - la era um config.json
fixo, aqui e' o corte que voce escolheu na etapa 2. O app.js nao sabe disso e
nao precisa saber.

Consequencia pratica: o "corte ativo" mora no SERVIDOR, nao na URL - porque o
app.js chama /api/config sem parametro nenhum. A rota /turnos define o ativo
antes de entregar o HTML, entao entrar por link continua funcionando.
"""

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (FileResponse, JSONResponse, RedirectResponse,
                               Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import captions
import config
import jobs
import media
import methods
import projects as P
import timecode as tc
import turns as T

CFG = config.CONFIG
STATIC = Path(__file__).resolve().parent / "static"

# paleta dos participantes. As duas reservadas ficam no config: cinza pro
# fora-de-quadro (que e' ausencia de track) e violeta pro `cut` (que tem
# track mas nao e' pessoa) - ver o README.
PALETTE = ["#5b9cf8", "#f2a341", "#4ecb8f", "#e879b9", "#7dd3fc",
           "#c4b5fd", "#fca5a5", "#86efac", "#fcd34d"]

# Vozes fora de quadro ficam FORA da PALETTE de proposito: cinza e a cor de
# "nao tem ninguem na imagem". Mas com mais de uma voz sem enquadramento o
# cinza unico deixaria de distinguir quem e quem no editor - entao sao tons
# diferentes do mesmo cinza, ainda lidos como a mesma familia.
# (o #6b7280 reservado fica de fora: ele e o rotulo de SILENCIO, e um vazio
#  com a mesma cor da voz 1 e' um erro de leitura esperando pra acontecer)
OFF_CAMERA_SHADES = ["#9ca3af", "#4b5563", "#d1d5db", "#374151"]

app = FastAPI(title="pre_production")


def fail(code, msg):
    raise HTTPException(code, str(msg))


def _guard(fn, *a, **k):
    """Converte os erros de dominio em 400 com a mensagem legivel."""
    try:
        return fn(*a, **k)
    except P.NotFound as e:
        fail(404, e)
    except (P.ProjectError, T.TurnsError, media.MediaError, ValueError) as e:
        fail(400, e)
    except KeyError as e:
        fail(404, e)


# =========================================================== paginas

def _page(name):
    return FileResponse(STATIC / name, media_type="text/html; charset=utf-8")


@app.get("/")
def page_projects():
    return _page("index.html")


@app.get("/cortes")
def page_cuts():
    return _page("cortes.html")


@app.get("/turnos")
def page_turns(projeto: str | None = None, corte: str | None = None):
    """Define o corte ativo ANTES de servir o HTML.

    Tem que ser aqui: o app.js dispara /api/config assim que carrega, entao
    setar o ativo por javascript depois seria uma corrida - as vezes o editor
    abriria com o corte anterior.
    """
    if projeto and corte:
        _guard(P.load_cut, projeto, corte)
        CFG["active_project"], CFG["active_cut"] = projeto, corte
        config.save(CFG)
    # sem corte ativo nao ha o que editar - o editor abriria vazio, com todas
    # as chamadas dele voltando 409. Melhor mandar pra etapa 2, que e' onde a
    # escolha e' feita. Acontece de verdade: basta o corte ativo ter ido pra
    # lixeira desde a ultima visita.
    if not (CFG.get("active_project") and CFG.get("active_cut")):
        return RedirectResponse("/cortes", status_code=303)
    return _page("turnos.html")


# =========================================================== estado

@app.get("/api/state")
def api_state():
    active = None
    if CFG.get("active_project") and CFG.get("active_cut"):
        try:
            p = P.load_project(CFG["active_project"])
            c = P.load_cut(CFG["active_project"], CFG["active_cut"])
            active = {"project": p, "cut": c}
        except P.ProjectError:
            CFG["active_project"] = CFG["active_cut"] = None
    return {"active": active,
            "projects_dir": CFG["projects_dir"],
            "scripts_dir": CFG["scripts_dir"],
            "sources_dir": CFG["sources_dir"],
            "python_exe": CFG["python_exe"],
            "min_span_frames": CFG["min_span_frames"]}


class StateIn(BaseModel):
    project: str
    cut: str


@app.post("/api/state")
def api_state_set(body: StateIn):
    _guard(P.load_cut, body.project, body.cut)
    CFG["active_project"], CFG["active_cut"] = body.project, body.cut
    config.save(CFG)
    return {"ok": True}


@app.get("/api/doctor")
def api_doctor():
    """O que esta instalado e o que falta. Uma volta antes de gastar horas."""
    probe = config.probe_python(CFG["python_exe"])
    env = {k: bool(os.environ.get(k))
           for k in ("HF_TOKEN", "GEMINI_API_KEY", "GEMINI_MODEL")}
    tools = {}
    for t in ("ffmpeg", "ffprobe"):
        try:
            media._run([CFG[t], "-version"], timeout=20)
            tools[t] = True
        except Exception:
            tools[t] = False
    return {"python_exe": CFG["python_exe"], "packages": probe, "env": env,
            "tools": tools, "scripts_dir": CFG["scripts_dir"],
            "scripts_dir_ok": config.scripts_dir().is_dir(),
            "env_file": str(config.ENV_PATH),
            "env_file_exists": config.ENV_PATH.exists()}


# =========================================================== etapa 1

@app.get("/api/sources")
def api_sources(dir: str | None = None):
    folder = dir or CFG["sources_dir"]
    return {"dir": folder, "videos": media.list_videos(folder)}


_PICKER = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
p = filedialog.askopenfilename(
    parent=root, title="pre_production - escolha o video de origem",
    initialdir=sys.argv[1] if len(sys.argv) > 1 else "",
    filetypes=[("Video", "*.mp4 *.mkv *.mov *.m4v *.avi *.webm"),
               ("Todos os arquivos", "*.*")])
root.destroy(); sys.stdout.write(p or "")
"""


@app.post("/api/sources/pick")
def api_pick():
    """Abre o dialogo nativo do Windows num processo separado.

    Mesmo truque que o SpeakerSwitch.py ja usa, pelo mesmo motivo: tkinter no
    processo do servidor mistura event loops e trava. O `<input type=file>` do
    navegador nao serve aqui - ele entrega o CONTEUDO do arquivo, e o que
    precisamos e' o CAMINHO, pra ler os 3 GB de onde ja estao em vez de subir
    copia nenhuma. Como o servidor roda na mesma maquina, o dialogo abre na
    tela de quem esta usando.
    """
    try:
        r = subprocess.run([sys.executable, "-c", _PICKER, CFG["sources_dir"]],
                           capture_output=True, text=True, timeout=600,
                           creationflags=media.NO_WINDOW)
    except Exception as e:
        fail(500, f"nao consegui abrir o dialogo de arquivo: {e}")
    if r.returncode != 0:
        fail(500, (r.stderr or "").strip()[-300:] or "dialogo falhou")
    return {"path": r.stdout.strip()}


_PICKER_JSON = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
p = filedialog.askopenfilename(
    parent=root, title="pre_production - escolha o arquivo de turnos",
    initialdir=sys.argv[1] if len(sys.argv) > 1 else "",
    filetypes=[("Turnos (turns*.json)", "turns*.json"), ("JSON", "*.json"),
               ("Todos os arquivos", "*.*")])
root.destroy(); sys.stdout.write(p or "")
"""


_PICKER_TRANSCRIPT = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
p = filedialog.askopenfilename(
    parent=root, title="pre_production - escolha a transcricao",
    initialdir=sys.argv[1] if len(sys.argv) > 1 else "",
    filetypes=[("Transcricao (json, srt)", "*.json *.srt *.vtt"),
               ("JSON", "*.json"), ("Legenda", "*.srt *.vtt"),
               ("Todos os arquivos", "*.*")])
root.destroy(); sys.stdout.write(p or "")
"""


def _run_picker(snippet, initial):
    try:
        r = subprocess.run([sys.executable, "-c", snippet, str(initial)],
                           capture_output=True, text=True, timeout=600,
                           creationflags=media.NO_WINDOW)
    except Exception as e:
        fail(500, f"nao consegui abrir o dialogo de arquivo: {e}")
    if r.returncode != 0:
        fail(500, (r.stderr or "").strip()[-300:] or "dialogo falhou")
    return r.stdout.strip()


@app.post("/api/projects/{slug}/cuts/{name}/open-turns")
def api_open_turns(slug: str, name: str):
    """Escolhe QUALQUER turns*.json do disco e abre ele no editor.

    A pasta do arquivo entra em `extra_turns_dirs` (so leitura) e o arquivo
    vira o selecionado do corte. Serve pra comparar com os turnos antigos de
    `scriptsPrimarios\\resultados\\`, ou com o mesmo trecho de outro corte, sem
    copiar arquivo pra ca. Gravar continua caindo dentro do projeto - o editor
    salva na pasta do corte, nunca por cima do arquivo de origem.
    """
    cut = _guard(P.load_cut, slug, name)
    chosen = _run_picker(_PICKER_JSON, P.turns_dir(slug, name))
    if not chosen:
        return {"path": None}
    f = Path(chosen).resolve()
    if not f.is_file():
        fail(400, f"arquivo nao encontrado: {chosen}")
    try:
        raw = T.read_raw(f)
    except Exception as e:
        fail(400, f"{f.name}: nao consegui ler como JSON ({e})")
    if not T.is_turns_file(raw):
        fail(400, f"{f.name} nao parece uma lista de turnos "
                  f"(cada item precisa de start e end)")
    # o rotulo tem que ser O MESMO que o /api/config usa na listagem: nome
    # curto pra quem mora na pasta do corte, caminho inteiro pra quem veio de
    # fora. Guardar sempre o absoluto fazia o editor NAO reconhecer o arquivo
    # recem-escolhido quando ele era da propria pasta (a listagem o chama de
    # `turnsX.json`, o corte o guardava como `D:\...\turnsX.json`) e cair no
    # primeiro turns* da ordem alfabetica - escolher um arquivo e receber
    # outro. So aparecia agora, que o dialogo virou o caminho normal de trocar
    # de arquivo em vez de um atalho pra comparar com pasta de fora.
    cutdir = P.cut_dir(slug, name).resolve()
    turnsdir = P.turns_dir(slug, name).resolve()
    inside = f.parent in (cutdir, turnsdir)
    label = f.name if inside else str(f)
    if not inside:
        extras = CFG.setdefault("extra_turns_dirs", [])
        if str(f.parent) not in extras:
            extras.append(str(f.parent))
        config.save(CFG)
    cut["last_turns_file"] = label
    P.save_cut(slug, cut)
    return {"path": str(f), "file": label, "dir": str(f.parent),
            "inside": inside, "count": len(raw), "labels": T.labels_of(raw)}


@app.get("/api/probe")
def api_probe(path: str = Query(...)):
    info = _guard(media.probe, path)
    info["suggested_name"] = Path(path).stem
    return info


@app.get("/api/projects")
def api_projects():
    return {"projects": P.list_projects()}


class ParticipantIn(BaseModel):
    name: str
    seat: str = "none"


class ProjectIn(BaseModel):
    name: str
    source_video: str
    participants: list[ParticipantIn]
    off_camera: list[str] | None = None
    extract: bool = True


@app.post("/api/projects")
def api_project_new(body: ProjectIn):
    info = _guard(media.probe, body.source_video)
    p = _guard(P.new_project, body.name, body.source_video,
               [x.model_dump() for x in body.participants], info,
               body.off_camera)
    job = _extract_audio_job(p) if body.extract else None
    return {"project": p, "job": job.id if job else None}


def _count_json_list(path):
    """Tamanho de uma lista json, ou None se o arquivo nao existe/nao le -
    barato o bastante pra chamar toda vez que a tela do projeto abre."""
    if not path.is_file():
        return None
    try:
        return len(json.loads(path.read_text(encoding="utf-8-sig")))
    except Exception:
        return None


@app.get("/api/projects/{slug}")
def api_project(slug: str):
    p = _guard(P.load_project, slug)
    et = P.entire_transcript_path(slug)
    ss = P.suggested_shorts_path(slug)
    return {"project": p, "cuts": P.list_cuts(slug),
            "audio_exists": P.project_audio(p).is_file(),
            "entire_transcribe_exists": et.is_file(),
            "entire_transcribe_turns": _count_json_list(et),
            "suggested_shorts_exists": ss.is_file(),
            "suggested_shorts_clips": _count_json_list(ss)}


class ProjectPatch(BaseModel):
    name: str | None = None
    participants: list[ParticipantIn] | None = None
    off_camera: list[str] | None = None
    # tela dividida -> legenda de cada pessoa na propria track (giautosubs.py)
    split_screen: bool | None = None


@app.patch("/api/projects/{slug}")
def api_project_patch(slug: str, body: ProjectPatch):
    p = _guard(P.load_project, slug)
    if body.name:
        p["name"] = body.name.strip()      # a pasta (slug) nao muda de nome
    if body.participants is not None:
        seen = set()
        parts = []
        for x in body.participants:
            n = x.name.strip()
            if not n or n.lower() in seen:
                continue
            seen.add(n.lower())
            parts.append({"name": n, "seat": x.seat})
        if not parts:
            fail(400, "um projeto precisa de pelo menos um participante")
        p["participants"] = parts
    if body.off_camera is not None:
        try:
            p["off_camera"] = P.clean_off_camera(body.off_camera,
                                                 p["participants"])
        except P.ProjectError as e:
            fail(400, str(e))
    if body.split_screen is not None:
        p["split_screen"] = bool(body.split_screen)
    return {"project": P.save_project(p)}


@app.delete("/api/projects/{slug}")
def api_project_delete(slug: str):
    """Move pra lixeira em vez de apagar.

    Um clique nao deve poder destruir uma extracao de audio de 69 min e as
    diarizacoes que sairam dela. A pasta continua no disco, com data no nome;
    apagar de verdade e' decisao do Explorer.
    """
    d = _guard(P.project_dir, slug)
    if not d.is_dir():
        fail(404, f"projeto nao encontrado: {slug}")
    trash = config.projects_dir() / "_lixeira"
    trash.mkdir(exist_ok=True)
    dest = trash / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.move(str(d), str(dest))
    if CFG.get("active_project") == slug:
        CFG["active_project"] = CFG["active_cut"] = None
        config.save(CFG)
    return {"ok": True, "moved_to": str(dest)}


def _extract_audio_job(p):
    """mp4/mkv -> wav 16 kHz mono, o insumo de todo o resto."""
    dest = P.project_audio(p)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = media.extract_wav_cmd(p["source_video"], dest)
    p["status"] = "extraindo áudio"
    P.save_project(p)

    def after(job):
        info = media.wav_info(dest)
        proj = P.load_project(p["slug"])
        proj["audio_info"] = info
        proj["status"] = "pronto"
        P.save_project(proj)
        media.build_peaks(dest)          # ja deixa a onda pronta pra etapa 2
        return {"audio": info}

    return jobs.create(
        "audio", f"Extrair audio de {Path(p['source_video']).name}",
        [jobs.Step(label="ffmpeg: extraindo wav 16 kHz mono", cmd=cmd,
                   progress_kind="ffmpeg",
                   total_seconds=p.get("duration") or None)],
        meta={"project": p["slug"]}, after=after)


@app.post("/api/projects/{slug}/audio")
def api_project_audio(slug: str):
    p = _guard(P.load_project, slug)
    return {"job": _extract_audio_job(p).id}


# ================================== transcricao inteira / sugestoes de corte
#
# Duas acoes de PROJETO, nao de corte: a transcricao do audio inteiro e as
# sugestoes de corte que ela alimenta pro Gemini. Nascem na etapa 1 porque
# dependem so' do wav do PROJETO, antes de qualquer corte existir, e moram
# soltas em projects\<slug>\cortes\ (P.entire_transcript_path/
# suggested_shorts_path) - ao lado das pastas de corte, nao dentro de uma. Um
# corte novo pode reaproveitar a transcricao recortando por tempo, em vez de
# rodar o Whisper de novo - ver _crop_entire_transcript, na etapa 2 abaixo.

@app.get("/api/project-methods")
def api_project_methods():
    """Opcoes de tela pras duas acoes acima - mesmo formato que /api/methods
    ja usa (rotulo, default, choices/suggest), pro frontend desenhar os
    mesmos widgets (select de modelo do Gemini com "outro modelo…" incluso)."""
    probe = config.probe_python(CFG["python_exe"])
    env = {k: bool(os.environ.get(k)) for k in ("GEMINI_API_KEY",)}
    whisper = methods.get("whisper")
    shorts_script = Path(__file__).resolve().parent / "suggested_shorts.py"
    missing_pkg = [pk for pk in ("google.genai", "pydantic") if probe.get(pk) is False]
    return {
        "entire_transcribe": {
            "options": whisper["options"],
            "ready": probe.get("faster_whisper") is not False,
            "note": "Roda o mesmo Whisper da etapa 2, no wav do projeto inteiro "
                    "em vez do wav de um corte. Tempo por palavra sempre ligado.",
        },
        "suggested_shorts": {
            "options": {
                "gemini_model": {"label": "modelo do Gemini",
                                 "default": methods.DEFAULT_GEMINI_MODEL,
                                 "suggest": methods.GEMINI_MODELS},
                "min_duration": {"label": "duração mínima (s)", "default": 15, "min": 5, "max": 300},
                "max_duration": {"label": "duração máxima (s)", "default": 60, "min": 10, "max": 600},
            },
            "ready": shorts_script.is_file() and not missing_pkg and env["GEMINI_API_KEY"],
            "missing_packages": missing_pkg,
            "missing_env": [] if env["GEMINI_API_KEY"] else ["GEMINI_API_KEY"],
            "note": "Pede pro Gemini escolher trechos autocontidos na transcrição "
                    "do episódio inteiro, dentro da faixa de duração. Precisa da "
                    "transcrição gerada primeiro.",
        },
    }


class EntireTranscribeIn(BaseModel):
    options: dict = {}


def _entire_transcribe_job(p, options):
    """Mesmo script e' mesmas opcoes do metodo "whisper" da etapa 2
    (methods.py) - so' aponta pro wav do PROJETO em vez do wav de um corte.
    Sem offset nenhum pra somar depois: transcrever do frame 0 do episodio ja
    devolve tempo absoluto, que e' exatamente a base que este arquivo precisa
    ter pra ser recortavel por corte (ver turns.crop_absolute)."""
    m = methods.get("whisper")
    script = methods.script_path(m)
    if not script.is_file():
        fail(400, f"nao achei {script} - confira scripts_dir no config.json")
    opts = methods.options_with_defaults(m, options)
    out = P.entire_transcript_path(p["slug"])
    out.parent.mkdir(parents=True, exist_ok=True)
    ctx = {"wav": P.project_audio(p), "out": out}
    ctx.update(opts)
    cmd = [CFG["python_exe"], str(script)] + methods.build_args(m, ctx)

    def after(job):
        if not out.is_file():
            raise RuntimeError(f"o script terminou mas nao gravou {out.name}")
        n = len(json.loads(out.read_text(encoding="utf-8-sig")))
        # falha aqui nao derruba a transcricao, que ja esta gravada
        try:
            leg = _gerar_legendona(p["slug"], out)
        except Exception as e:
            leg = {"lua": None, "lua_erro": str(e)}
        return {"file": out.name, "turns": n, **leg}

    return jobs.create(
        "transcricao_projeto", f"Transcrição do episódio inteiro — {p['slug']}",
        [jobs.Step(label=m["label"], cmd=cmd, cwd=str(config.scripts_dir()),
                   env=methods.env_for(m, opts, config.subprocess_env()))],
        meta={"project": p["slug"]}, after=after)


@app.post("/api/projects/{slug}/entire-transcript")
def api_entire_transcript(slug: str, body: EntireTranscribeIn):
    p = _guard(P.load_project, slug)
    if not P.project_audio(p).is_file():
        fail(400, "o audio do projeto ainda nao foi extraido")
    job = _entire_transcribe_job(p, body.options)
    return {"job": job.id}


class SuggestedShortsIn(BaseModel):
    options: dict = {}
    min_duration: float = 15.0
    max_duration: float = 60.0


def _suggested_shorts_job(p, body):
    script = Path(__file__).resolve().parent / "suggested_shorts.py"
    if not script.is_file():
        fail(400, f"nao achei {script}")
    transcript = P.entire_transcript_path(p["slug"])
    if not transcript.is_file():
        fail(400, "gere a transcrição do episódio inteiro primeiro")
    out = P.suggested_shorts_path(p["slug"])
    model = (body.options or {}).get("gemini_model") or methods.DEFAULT_GEMINI_MODEL
    cmd = [CFG["python_exe"], str(script),
           "--transcript", str(transcript), "--out", str(out),
           "--model", model,
           "--min-duration", str(body.min_duration),
           "--max-duration", str(body.max_duration)]

    def after(job):
        if not out.is_file():
            raise RuntimeError(f"o script terminou mas nao gravou {out.name}")
        clips = json.loads(out.read_text(encoding="utf-8-sig"))
        return {"file": out.name, "clips": len(clips)}

    return jobs.create(
        "sugestoes_corte", f"Sugestões de corte — {p['slug']}",
        [jobs.Step(label=f"Gemini ({model}): escolhendo trechos", cmd=cmd,
                   cwd=str(config.scripts_dir()), env=config.subprocess_env())],
        meta={"project": p["slug"]}, after=after)


@app.post("/api/projects/{slug}/suggested-shorts")
def api_suggested_shorts(slug: str, body: SuggestedShortsIn):
    p = _guard(P.load_project, slug)
    job = _suggested_shorts_job(p, body)
    return {"job": job.id}


@app.get("/api/projects/{slug}/suggested-shorts")
def api_suggested_shorts_get(slug: str):
    _guard(P.load_project, slug)
    f = P.suggested_shorts_path(slug)
    if not f.is_file():
        return {"exists": False, "clips": []}
    return {"exists": True, "clips": json.loads(f.read_text(encoding="utf-8-sig"))}


# =========================================================== etapa 2

@app.get("/api/methods")
def api_methods():
    probe = config.probe_python(CFG["python_exe"])
    env = {k: bool(os.environ.get(k))
           for k in ("HF_TOKEN", "GEMINI_API_KEY")}
    return {"methods": methods.public(probe, env)}


class CutIn(BaseModel):
    name: str
    start: float
    end: float
    track_map: dict | None = None
    speakers: int | None = None
    # se True e existir entire_transcribe.json, o corte nasce com o trecho
    # recortado dele como transcricao - sem rodar o Whisper de novo. Ver
    # _crop_entire_transcript().
    reuse_transcript: bool = False


@app.post("/api/projects/{slug}/cuts")
def api_cut_new(slug: str, body: CutIn):
    p = _guard(P.load_project, slug)
    wav = P.project_audio(p)
    if not wav.is_file():
        fail(400, "o audio do projeto ainda nao foi extraido")
    cut = _guard(P.new_cut, p, body.name, body.start, body.end,
                 body.track_map, body.speakers)
    job = _slice_job(p, cut)
    reused = _crop_entire_transcript(p, cut) if body.reuse_transcript else None
    return {"cut": cut, "job": job.id, "reused_transcript": reused}



def _crop_entire_transcript(p, cut):
    """Reaproveita `entire_transcribe.json` no corte novo, recortando pelo
    tempo em vez de rodar o Whisper de novo.

    Os dois lados ja estao em tempo absoluto do episodio (a transcricao
    inteira nasce assim porque parte do wav do PROJETO, do frame 0; o corte
    tambem, ver o topo de turns.py) - entao nao ha offset pra somar, so'
    filtrar o que cai fora de [start, end). Silencioso quando nao ha o que
    reaproveitar: o corte continua utilizavel sem transcricao, igual a antes
    desta funcionalidade existir.
    """
    src = P.entire_transcript_path(p["slug"])
    if not src.is_file():
        return None
    items = T.crop_absolute(src, cut["start"], cut["end"])
    if not items:
        return None
    out_name = "turnsWhisperEpisodio.json"
    dest = P.turns_dir(p["slug"], cut["name"]) / out_name
    T.write(dest, items, backup=False)
    summary = T.summarize(dest, cut["fps"], CFG["min_span_frames"])
    c = P.load_cut(p["slug"], cut["name"])
    c.setdefault("runs", []).append({
        "method": "entire_transcribe_crop",
        "label": "Whisper (episódio inteiro, recortado)",
        "kind": "transcript", "out": out_name, "raw": None,
        "offset_applied": 0.0, "speakers": None, "options": {},
        "when": datetime.now().isoformat(timespec="seconds"),
        "seconds": 0.0, "turns": len(items),
        "labels": summary["labels"] if summary else [],
        "issues": summary["issues"] if summary else {}, "segments_raw": None,
    })
    c["transcript"] = out_name
    c["transcript_offset"] = 0.0
    P.save_cut(p["slug"], c)
    return {"file": out_name, "turns": len(items)}


def _slice_job(p, cut):
    d = P.cut_dir(p["slug"], cut["name"])
    dest = d / cut["audio"]
    cmd = media.extract_wav_cmd(P.project_audio(p), dest,
                               start=cut["start"], end=cut["end"])
    cut["status"] = "fatiando o wav"
    P.save_cut(p["slug"], cut)

    def after(job):
        info = media.wav_info(dest)
        c = P.load_cut(p["slug"], cut["name"])
        c["audio_info"] = info
        c["status"] = "sem diarização"
        P.save_cut(p["slug"], c)
        media.build_peaks(dest)
        # o trecho de video sai em JOB SEPARADO, nao como passo daqui: se o
        # remux falhar (fonte que nao e' video, keyframe que nao da pra
        # sondar), o corte ja esta gravado e utilizavel em vez de ficar preso
        # em "fatiando o wav" - e o erro aparece como job proprio, com log.
        vjob = _video_job(p, c)
        return {"audio": info, "video_job": vjob.id if vjob else None}

    return jobs.create(
        "corte", f"Fatiar {cut['name']} "
                 f"({tc.format_time(cut['start'])} → {tc.format_time(cut['end'])})",
        [jobs.Step(label="ffmpeg: fatiando o wav do corte", cmd=cmd,
                   progress_kind="ffmpeg", total_seconds=cut["duration"])],
        meta={"project": p["slug"], "cut": cut["name"]}, after=after)


@app.get("/api/projects/{slug}/cuts/{name}")
def api_cut(slug: str, name: str):
    p = _guard(P.load_project, slug)
    cut = _guard(P.load_cut, slug, name)
    d = P.cut_dir(slug, name)
    return {"project": p, "cut": cut,
            "files": P.cut_turns_files(slug, cut),
            "audio_exists": (d / cut["audio"]).is_file(),
            "video_exists": bool(cut.get("video")) and (d / cut["video"]).is_file(),
            "dir": str(d)}


class CutPatch(BaseModel):
    track_map: dict | None = None
    speakers: int | None = None
    start: float | None = None
    end: float | None = None


@app.patch("/api/projects/{slug}/cuts/{name}")
def api_cut_patch(slug: str, name: str, body: CutPatch):
    cut = _guard(P.load_cut, slug, name)
    if body.track_map is not None:
        cut["track_map"] = {str(k): int(v) for k, v in body.track_map.items()}
    if body.speakers is not None:
        cut["speakers"] = int(body.speakers)
    if body.start is not None or body.end is not None:
        # mexer no trecho invalida o audio ja fatiado - avisa em vez de
        # deixar o wav e os turnos discordarem em silencio
        cut["start"] = float(body.start if body.start is not None else cut["start"])
        cut["end"] = float(body.end if body.end is not None else cut["end"])
        cut["duration"] = round(cut["end"] - cut["start"], 5)
        cut["audio_offset"] = round(cut["start"], 5)
        cut["origin_frame"] = tc.seconds_to_frame(cut["start"], cut["fps"])
        cut["status"] = "trecho mudou — refatie o áudio"
        # o trecho de video e o offset dele foram medidos pro trecho ANTIGO:
        # mantê-los apontados seria o mesmo erro silencioso do keyframe, so'
        # que pior. O arquivo fica na pasta (nada some por um clique), mas o
        # manifesto larga a mão dele e o proximo remux mede de novo.
        cut["video"] = None
        cut["video_offset"] = None
        cut["video_offset_frames"] = None
    return {"cut": P.save_cut(slug, cut)}


@app.delete("/api/projects/{slug}/cuts/{name}")
def api_cut_delete(slug: str, name: str):
    d = _guard(P.cut_dir, slug, name)
    if not d.is_dir():
        fail(404, "corte nao encontrado")
    trash = config.projects_dir() / "_lixeira"
    trash.mkdir(exist_ok=True)
    dest = trash / f"{slug}-{name}-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.move(str(d), str(dest))
    if CFG.get("active_project") == slug and CFG.get("active_cut") == name:
        CFG["active_cut"] = None
        config.save(CFG)
    return {"ok": True, "moved_to": str(dest)}


class MethodRun(BaseModel):
    id: str
    options: dict = {}
    out_name: str | None = None


class RunIn(BaseModel):
    # varios metodos numa rodada so: marcar pyannote + Gemini + Whisper e
    # deixar rodando e' o uso real - sao horas de espera que nao deveriam
    # exigir voltar na tela entre uma e outra.
    methods: list[MethodRun] | None = None
    # forma antiga, de um metodo so - continua valendo
    method: str | None = None
    options: dict = {}
    out_name: str | None = None
    # roda o Whisper no mesmo trabalho, depois do metodo escolhido. E' um passo
    # a mais no MESMO job de proposito: transcrever e diarizar o mesmo corte e'
    # uma coisa so na cabeca de quem usa - duas barras de progresso para uma
    # decisao so seria ruido.
    transcribe: bool = False
    transcribe_options: dict = {}
    # o .srt sai junto da rodada, ligado por padrao. Era um segundo passo
    # manual (botao -> modal -> escolher os dois arquivos), e o passo manual
    # depois de uma espera de 20 minutos e' justamente o que se esquece de
    # fazer. Nada se perde ao gerar sempre: e' um arquivo de texto pequeno,
    # reescrito a cada rodada, e o modal continua ali para o caso especial
    # (outra base de tempo, outro nome, transcricao importada de fora).
    captions: bool = True
    captions_base: str = "timeline"
    # o json do GiAutoSubs sai junto tambem, pelo mesmo motivo do .srt: e' o
    # passo manual depois de uma espera de 20 minutos que se esquece de fazer.
    # Sao arquivos diferentes (`.srt` para o Resolve importar, `.giautosubs.json`
    # para o script das legendas estilizadas) e nenhum atropela o outro.
    captions_giautosubs: bool = True
    # caixa "Tracks de legenda separadas" do corte; None = o do projeto
    split_screen: bool | None = None


def _plan_run(slug, name, p, cut, m, options, out_name=None):
    """Passos + acao final de UMA rodada. Devolve tudo pronto para o job.

    Separado de `api_run` porque uma requisicao pode enfileirar mais de uma
    rodada (o metodo escolhido, e o Whisper junto).
    """
    d = P.cut_dir(slug, name)
    turnsd = P.turns_dir(slug, name)
    script = methods.script_path(m)
    if not script.is_file():
        fail(400, f"nao achei {script} - confira scripts_dir no config.json")

    opts = methods.options_with_defaults(m, options)
    out_name = out_name or methods.out_name_for(m, opts)
    if not re.fullmatch(r"[\w.\-]+\.json", out_name):
        fail(400, f"nome de saida invalido: {out_name!r}")
    # a saida CRUA do script vai pra .raw.json; o canonico e' escrito depois,
    # ja em tempo absoluto (ver turns.py). Os dois em turns\ - so audio/video
    # (que os scripts leem, nao escrevem) ficam na raiz do corte.
    raw_out = turnsd / (Path(out_name).stem + ".raw.json")
    final_out = turnsd / out_name

    steps = []
    video_offset = cut.get("video_offset")
    ctx = {
        "wav": d / cut["audio"], "out": raw_out, "cutdir": d,
        "samples_dir": d / "speaker_samples",
        "speakers": cut["speakers"],
        # o elenco do PROJETO (quantos e em que cadeira) - os metodos do
        # Gemini montam o prompt com ele, ver projects.roster_arg
        "roster": P.roster_arg(p),
        "start": cut["start"], "end": cut["end"],
        "duration": cut["duration"], "fps": cut["fps"],
        "video_src": p["source_video"],
    }
    ctx.update(opts)

    if m["input"] == "video_cut":
        vsteps, video_offset = _ensure_video(p, cut)
        steps += vsteps
        ctx["video_cut"] = d / cut["video"]
        ctx["video_offset"] = round(video_offset, 6)

    steps.append(jobs.Step(
        label=m["label"],
        cmd=[CFG["python_exe"], str(script)] + methods.build_args(m, ctx),
        cwd=str(config.scripts_dir()),      # os scripts leem o .env da pasta deles
        env=methods.env_for(m, opts, config.subprocess_env()),
        progress_re=m.get("progress_re")))

    started = time.time()

    def finalize():
        # 1. base de tempo: quem devolve relativo ganha o offset aqui, uma vez.
        offset = cut["start"] if m["output_base"] == "relative" else 0.0
        # 2. rotulo: o 3c_ nomeia por cadeira com nomes fixos no codigo dele -
        #    traduz pras pessoas deste projeto.
        label_map = None
        if m["label_style"] == "seat":
            seats = P.seat_map(p)
            label_map = {alias: seats[seat]
                         for seat, alias in methods.SEAT_ALIASES.items()
                         if seat in seats}
        if not raw_out.is_file():
            raise RuntimeError(f"o script terminou mas nao gravou {raw_out.name}")
        nested = _rename_nested_raw(raw_out)
        n = T.shift_file(raw_out, final_out, offset, label_map, fps=cut["fps"])
        summary = T.summarize(final_out, cut["fps"], CFG["min_span_frames"])

        c = P.load_cut(slug, name)
        c["runs"] = [r for r in c.get("runs", []) if r["out"] != out_name]
        c["runs"].append({
            "method": m["id"], "label": m["label"], "kind": m["kind"],
            "out": out_name, "raw": raw_out.name,
            "offset_applied": offset, "speakers": cut["speakers"],
            "options": opts,
            "when": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(time.time() - started, 1),
            "turns": n, "labels": summary["labels"] if summary else [],
            "issues": summary["issues"] if summary else {},
            "segments_raw": nested,
        })
        if m["kind"] == "transcript":
            c["transcript"] = out_name
            c["transcript_offset"] = 0.0     # ja convertido pra absoluto
        else:
            c["last_turns_file"] = out_name
            c["status"] = "diarizado"
        if video_offset is not None:
            c["video_offset"] = round(video_offset, 6)
        P.save_cut(slug, c)
        return {"file": out_name, "kind": m["kind"], "turns": n,
                "labels": summary["labels"] if summary else [],
                "issues": summary["issues"] if summary else {}}

    return {"steps": steps, "finalize": finalize, "out": out_name}


@app.post("/api/projects/{slug}/cuts/{name}/run")
def api_run(slug: str, name: str, body: RunIn):
    p = _guard(P.load_project, slug)
    cut = _guard(P.load_cut, slug, name)
    if not (P.cut_dir(slug, name) / cut["audio"]).is_file():
        fail(400, "o wav deste corte ainda nao foi gerado")

    wanted = list(body.methods or [])
    if not wanted and body.method:
        wanted = [MethodRun(id=body.method, options=body.options,
                            out_name=body.out_name)]
    if not wanted:
        fail(400, "escolha pelo menos um metodo")
    if body.transcribe and not any(
            methods.get(w.id)["kind"] == "transcript" for w in wanted):
        wanted.append(MethodRun(id="whisper", options=body.transcribe_options))

    seen = set()
    plans = []
    for w in wanted:
        if w.id in seen:
            continue
        seen.add(w.id)
        m = _guard(methods.get, w.id)
        # recarrega o corte a cada plano: o anterior pode ter gravado o
        # video_offset, e o proximo precisa enxergar isso
        plans.append(_plan_run(slug, name, p, P.load_cut(slug, name), m,
                               w.options, w.out_name))

    def after(job):
        out = {"files": []}
        for pl in plans:
            r = pl["finalize"]()
            out["files"].append(r)
            if r["kind"] == "transcript":
                out["transcript"] = r["file"]
            else:
                out.update({k: v for k, v in r.items() if k != "kind"})
        if body.captions:
            out["captions"] = _auto_captions(slug, name, out, body.captions_base)
        if body.captions_giautosubs:
            out["giautosubs"] = _auto_captions(slug, name, out, "media",
                                               fmt="giautosubs",
                                               split_screen=body.split_screen)
        return out

    title = " + ".join(methods.get(w.id)["label"].split(" — ")[0]
                       for w in wanted if w.id in seen)
    job = jobs.create("diarizacao", f"{title} — {slug}/{name}",
                      [s for pl in plans for s in pl["steps"]],
                      meta={"project": slug, "cut": name,
                            "methods": [w.id for w in wanted],
                            "out": plans[0]["out"]}, after=after)
    return {"job": job.id, "out": plans[0]["out"],
            "outs": [pl["out"] for pl in plans]}


# SPEAKER_00, SPEAKER_01... - rotulo que o diarizador inventou, nao nome de
# gente. O `re.I` cobre o `speaker_00` que sai de alguns modelos do Gemini.
_GENERIC_LABEL = re.compile(r"^SPEAKER[_\- ]?\d+$", re.I)


def _speakers_for_srt(slug, name, cut, result):
    """De qual arquivo saem os nomes na frente de cada fala - ou None.

    A regra e' uma so: **so entra nome que ja E' nome**. Enquanto a diarizacao
    esta em SPEAKER_00/SPEAKER_01, prefixar cada legenda com "SPEAKER_00: "
    deixa o .srt pior do que sem nome nenhum, e nesse momento o passo "quem e'
    quem" ainda nem aconteceu - o app estaria enfeitando a legenda com uma
    informacao que ele mesmo sabe que ainda nao vale. Depois de renomear, gerar
    de novo pelo botao traz os nomes.
    """
    cand = None
    # a diarizacao desta rodada tem preferencia sobre a que ja estava no corte
    for r in result["files"]:
        if r["kind"] != "transcript" and r.get("labels"):
            cand = (r["file"], r["labels"])
    if not cand and cut.get("last_turns_file"):
        f = P.turns_dir(slug, name) / cut["last_turns_file"]
        if f.is_file():
            try:
                cand = (cut["last_turns_file"], T.labels_of(T.read_raw(f)))
            except Exception:
                cand = None
    if not cand or not cand[1]:
        return None
    return None if all(_GENERIC_LABEL.match(str(x)) for x in cand[1]) else cand[0]


def _auto_captions(slug, name, result, base, fmt="srt", split_screen=None):
    """A legenda da rodada, gerada junto em vez de num segundo passo manual.

    Nunca derruba o job: a diarizacao ja terminou e ja esta no disco quando
    isto roda, entao uma legenda que nao saiu vira um recado no resultado, e
    nao uma rodada de 20 minutos marcada como falha.
    """
    cut = P.load_cut(slug, name)
    # o texto e' do Whisper; se esta rodada nao o produziu, serve o que o corte
    # ja tinha - rodar so o pyannote e ganhar a legenda com os nomes novos e'
    # exatamente o caso em que gerar junto vale a pena
    text_file = result.get("transcript") or cut.get("transcript")
    if not text_file:
        return {"skipped": "sem transcricao neste corte - o texto da legenda vem "
                           "do Whisper; marque-o na proxima rodada"}
    if fmt == "giautosubs":
        # sem nome de falante: quem sabe quem fala, do outro lado, e' o proprio
        # `giautosubs.py` (ele le o turns do corte.json e pinta a legenda com a
        # cor da pessoa). Colar "Giovanni: " no texto so' poria o nome dentro da
        # legenda estilizada.
        out_name = f"{P.slugify(name)}.giautosubs.json"
        speakers = None
    else:
        out_name = f"{P.slugify(name)}.srt"
        speakers = _speakers_for_srt(slug, name, cut, result)
    try:
        return _build_captions(slug, name, cut, text_file, speakers,
                               base, out_name, fmt, split_screen)
    except Exception as e:
        return {"erro": getattr(e, "detail", None) or str(e)}


def _rename_nested_raw(raw_out):
    """Desfaz o `.raw.raw.json` que aparece quando o script tambem grava um cru.

    O `1_diarize_v3.py` grava a diarizacao ANTES da suavizacao em
    `splitext(--out)[0] + ".raw.json"`. Como o nosso `--out` ja termina em
    `.raw.json`, o dele sai como `turnsX.raw.raw.json` - que parece defeito e
    esconde o que o arquivo e' de fato: os segmentos crus do pyannote, sem
    merge, sem descarte de micro-turno, sem padding. Vale guardar (o proprio
    v3 reprocessa com `--from-json`, sem gastar GPU de novo), so nao com esse
    nome.

    Regra generica, nao caso particular: se o script gravou um cru ao lado do
    nosso, ele vira `<nome>.segmentos.json`.
    """
    nested = Path(str(raw_out)[:-len(".raw.json")] + ".raw.raw.json")
    if not nested.is_file():
        return None
    dest = Path(str(raw_out)[:-len(".raw.json")] + ".segmentos.json")
    if dest.exists():
        dest.unlink()
    nested.replace(dest)
    return dest.name


def _ensure_video(p, cut):
    """Passos pra ter o trecho de video do corte, e o offset REAL dele.

    Remuxar com `-c copy` nao corta em qualquer frame: o ffmpeg volta ate o
    keyframe anterior. Em vez de fingir que o trecho comeca onde pedimos, a
    gente descobre onde o keyframe esta, corta exatamente ali e guarda esse
    valor - o diarizador recebe `--offset <keyframe>` e os turnos voltam no
    lugar certo. O trecho fica alguns segundos mais longo; o tempo continua
    exato, que e' o que importa.

    O offset tambem vai no NOME do arquivo (`<corte>_<N>frames.mkv`): os
    fontes gravam keyframe a cada 250 frames, entao esse N cai em qualquer
    lugar de 0 a 249 - ate ~8,3 s a 30 fps, ~4,2 s a 60. Quem abre a pasta ou
    arrasta o trecho pro Resolve precisa ver quanto aparar sem ir ler o
    manifesto.
    """
    d = P.cut_dir(p["slug"], cut["name"])
    atual = cut.get("video")
    if atual and (d / atual).is_file() and cut.get("video_offset") is not None:
        return [], float(cut["video_offset"])
    kf = media.keyframe_before(p["source_video"], cut["start"])
    if kf is None:
        kf = cut["start"]
    dur = cut["end"] - kf
    frames = max(0, tc.seconds_to_frame(cut["start"] - kf, cut["fps"]))
    dest = d / f"{_safe_stem(cut['name'])}_{frames}frames.mkv"
    cut["video"] = dest.name
    cut["video_offset"] = round(float(kf), 6)
    cut["video_offset_frames"] = frames
    P.save_cut(p["slug"], cut)
    label = (f"ffmpeg: remuxando o trecho de video "
             f"(keyframe em {tc.format_time(kf)}, {frames} frames antes do "
             f"corte, sem recodificar)")
    # O `-ss` vai no INICIO DO CORTE, nao no keyframe: pedir o tempo exato do
    # keyframe faz o ffmpeg voltar mais um GOP (ep4/impostor_fantasma: pediu
    # 3144.0, o mkv comecou em 3136 - legenda 8 s adiantada no Resolve, medido
    # por correlacao do audio). Entre `kf` e `start` nao ha outro keyframe,
    # entao buscar em `start` cai exatamente em `kf`. O `-t` conta a partir do
    # `-ss`, por isso a duracao e' a do corte; o preroll ate o kf vem de brinde.
    busca = max(float(kf), float(cut["start"]))
    return [jobs.Step(label=label,
                      cmd=media.cut_video_cmd(p["source_video"], dest, busca,
                                              cut["end"] - busca),
                      progress_kind="ffmpeg", total_seconds=dur)], float(kf)


def _safe_stem(name):
    """Nome do corte -> pedaco de nome de arquivo. Os cortes ja nascem com
    nome de pasta (`Eu_Duvido`); isto e' so o cinto de seguranca."""
    return re.sub(r"[^\w.\-]+", "_", str(name)).strip("_") or "corte"


def _video_job(p, cut):
    """Job do `<corte>_<N>frames.mkv`, ou None se ja existe / nao da pra fazer."""
    src = p.get("source_video")
    if not src or Path(src).suffix.lower() not in media.VIDEO_EXTS:
        return None
    steps, _ = _ensure_video(p, cut)
    if not steps:
        return None
    return jobs.create("video",
                       f"Trecho de video — {p['slug']}/{cut['name']}", steps,
                       meta={"project": p["slug"], "cut": cut["name"]})


@app.post("/api/projects/{slug}/cuts/{name}/video")
def api_cut_video(slug: str, name: str):
    p = _guard(P.load_project, slug)
    cut = _guard(P.load_cut, slug, name)
    job = _video_job(p, cut)
    off = P.load_cut(slug, name).get("video_offset")
    return {"job": job.id if job else None,
            "video_offset": None if off is None else float(off)}


class FinalizeIn(BaseModel):
    raw_file: str


@app.post("/api/projects/{slug}/cuts/{name}/finalize")
def api_finalize(slug: str, name: str):
    """Termina uma rodada que ficou pela metade.

    Os jobs vivem em memoria: reiniciar o servidor no meio de uma diarizacao
    perde o acompanhamento, mas NAO mata o processo do script - ele continua e
    grava o `.raw.json`. So que a conversao pra base absoluta acontecia no fim
    do job, entao o arquivo ficava ali, cru, sem nada apontando pra ele.

    Isto pega qualquer `.raw.json` sem o canonico ao lado e termina o servico.
    A base de tempo e' DETECTADA (comparando o trecho do arquivo com o do
    corte) em vez de assumida - quem sabia qual metodo tinha rodado era o job
    que se perdeu.
    """
    return _finalize_orphans(slug, name)


def _finalize_orphans(slug, name, only=None):
    cut = _guard(P.load_cut, slug, name)
    d = P.turns_dir(slug, name)
    done = []
    for raw in sorted(d.glob("*.raw.json")):
        if only and raw.name != only:
            continue
        final = d / (raw.name[:-len(".raw.json")] + ".json")
        if final.exists():
            continue
        try:
            items = T.read_raw(raw)
        except Exception as e:
            done.append({"file": raw.name, "erro": str(e)})
            continue
        if not T.is_turns_file(items):
            continue
        a = min(float(x["start"]) for x in items)
        b = max(float(x["end"]) for x in items)
        # ja em tempo absoluto? entao nao soma nada
        inside = (b >= cut["start"] - 5 and a <= cut["end"] + 5)
        offset = 0.0 if inside else float(cut["start"])
        n = T.shift_file(raw, final, offset, None, fps=cut["fps"])
        summary = T.summarize(final, cut["fps"], CFG["min_span_frames"])
        has_text = any((x.get("text") or "").strip() for x in items)
        kind = "transcript" if (has_text and not summary["labels"]) else "diarization"
        c = P.load_cut(slug, name)
        c["runs"] = [r for r in c.get("runs", []) if r["out"] != final.name]
        c["runs"].append({
            "method": "recuperado", "label": "rodada interrompida, finalizada a mao",
            "kind": kind, "out": final.name, "raw": raw.name,
            "offset_applied": offset,
            "when": datetime.now().isoformat(timespec="seconds"),
            "turns": n, "labels": summary["labels"] if summary else [],
            "issues": summary["issues"] if summary else {},
        })
        if kind == "transcript":
            c["transcript"] = final.name
            c["transcript_offset"] = 0.0
        else:
            c["last_turns_file"] = final.name
            c["status"] = "diarizado"
        P.save_cut(slug, c)
        done.append({"file": final.name, "turns": n, "offset_applied": offset,
                     "kind": kind, "base_detectada":
                     "absoluta" if inside else "relativa ao corte"})
    if not done:
        fail(400, "nao achei nenhum .raw.json sem o arquivo final ao lado")
    return {"finalizados": done}


def _cut_file(slug, name, rel):
    """Resolve um arquivo DESTE corte (o da URL), nao o do corte ativo.

    O `_safe_path` da etapa 3 responde sempre sobre o corte ativo - usar ele
    aqui faria "gerar legenda do corte X" ler o arquivo do corte Y sem
    reclamar de nada.
    """
    d = P.cut_dir(slug, name).resolve()
    allowed = [d, P.turns_dir(slug, name).resolve(),
              P.legendas_dir(slug, name).resolve()] + _extra_dirs()
    q = Path(rel)
    # `rel` normalmente e' nome solto (turnsFoo.json) - tenta em cada pasta
    # do corte (turns\, legendas\, raiz) ate achar; absoluto passa direto.
    cands = [q] if q.is_absolute() else [r / q for r in allowed]
    for c in cands:
        try:
            c = c.resolve()
        except OSError:
            continue
        if not any(c == r or r in c.parents for r in allowed):
            continue
        if c.is_file():
            return c
    fail(404, f"arquivo nao encontrado: {rel}")


class CaptionsIn(BaseModel):
    file: str                       # de onde sai o texto (json com "text" ou .srt)
    speakers_file: str | None = None  # opcional: de onde sai QUEM fala
    base: str = "timeline"          # "timeline" (frame 0) | "media" (absoluto)
    out_name: str | None = None
    # "srt"        -> a legenda que o Resolve importa em Timeline > Import
    # "giautosubs" -> o json que o GiAutoSubs le, com o tempo por palavra
    format: str = "srt"
    # uma track de legenda por pessoa; None = o split_screen do projeto
    split_screen: bool | None = None


def _gerar_legendas_lua(slug, name, transcript, split_screen=None):
    """Roda o `giautosubs.py` do corte logo depois de gravar o json dele.

    Era um passo manual (a tela so' mostrava o comando), e esquecer dele nao
    dava erro nenhum: o corte ficava com `.srt` e `.giautosubs.json`, e o
    GiAutoSubs.lua dentro do Resolve simplesmente nao tinha o que abrir. Falha
    aqui nao derruba a legenda ja gravada - vira `lua_erro` no resultado.
    """
    # sempre explicito: o nome do arquivo depende disto, e o caminho devolvido
    # aqui tem que ser o mesmo que o giautosubs.py escolhe
    if split_screen is None:
        split_screen = bool(P.load_project(slug).get("split_screen"))
    argv = [str(P.cut_dir(slug, name)), "--transcript", transcript,
            "--split-screen" if split_screen else "--single-track"]
    lua = "legenda_por_track.lua" if split_screen else "legendas.lua"
    return _rodar_giautosubs(argv, P.legendas_dir(slug, name) / lua)


def _rodar_giautosubs(argv, lua):
    """`giautosubs.main` em processo, com a saida capturada. Devolve
    {"lua": caminho, "lua_erro": None} ou {"lua": None, "lua_erro": motivo}."""
    import contextlib
    import io
    import giautosubs as G
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            rc = G.main(argv)
    except (Exception, SystemExit) as e:
        return {"lua": None, "lua_erro": f"giautosubs.py: {e}"}
    if rc:
        return {"lua": None, "lua_erro": saida.getvalue().strip()[-500:]}
    return {"lua": str(lua), "lua_erro": None}


CORTE_COMPLETO = P.CORTE_COMPLETO   # o nome mora no projects.py, com o list_cuts que o esconde


def _gerar_legendona(slug, transcript):
    """Legenda do EPISODIO inteiro: `cortes\\Completo\\legendas\\Legendona.lua`.

    O giautosubs.py so' sabe ler uma pasta de corte, entao o episodio inteiro
    ganha um corte `Completo` (0 ate o fim, sem diarizacao) - o mesmo que antes
    era montado a mao. O nome `Legendona` separa este arquivo do `legendas.lua`
    dos cortes, pra nao escolher um pelo outro no dialogo do GiAutoSubs.
    """
    turns = json.loads(Path(transcript).read_text(encoding="utf-8-sig"))
    fim = max((float(t.get("end") or 0) for t in turns), default=0.0)
    d = P.cut_dir(slug, CORTE_COMPLETO)
    d.mkdir(parents=True, exist_ok=True)
    try:
        cut = P.load_cut(slug, CORTE_COMPLETO)
    except P.NotFound:
        cut = {"schema": 1, "name": CORTE_COMPLETO, "project": slug,
               "time_base": "absolute",
               "note": "video inteiro, sem corte e sem diarizacao - so para o GiAutoSubs"}
    cut.update({"start": 0.0, "end": fim, "duration": fim,
                "transcript": str(transcript), "transcript_offset": 0.0})
    P.save_cut(slug, cut)
    out = P.legendas_dir(slug, CORTE_COMPLETO) / "Legendona.json"
    return _rodar_giautosubs([str(d), "--out", str(out)], out.with_suffix(".lua"))


def _write_giautosubs(slug, name, cut, file, segs, out_name, split_screen=None):
    """Grava o json que o GiAutoSubs reconhece, e aponta o editor pra ele.

    Duas coisas num passo so', de proposito. O arquivo que o GiAutoSubs le e o
    arquivo que a coluna "o que foi dito" mostra tem exatamente a mesma forma -
    entao serem DOIS arquivos so' criava a chance de divergirem, e a pergunta
    "qual dos dois e' o que vai pro Resolve" nao tem resposta boa. Depois desta
    gravacao ha um so, e o editor mostra o que a legenda vai dizer.

    O offset: tudo neste projeto e' gravado em tempo absoluto da midia, e
    `transcript_offset` so e' diferente de zero quando a transcricao foi
    IMPORTADA de fora em tempo relativo (ver `api_import_transcript`). Nesse
    caso o offset entra aqui, uma vez, e o arquivo novo ja nasce absoluto - com
    `transcript_offset = 0` no manifesto para ninguem soma-lo de novo.
    """
    offset = (float(cut.get("transcript_offset") or 0.0)
              if file == cut.get("transcript") else 0.0)
    itens = captions.to_giautosubs(segs, offset=offset)

    out_name = out_name or f"{P.slugify(name)}.giautosubs.json"
    if not re.fullmatch(r"[\w.\-]+\.json", out_name):
        fail(400, "nome de saida invalido (use algo como legenda.giautosubs.json)")
    dest = P.legendas_dir(slug, name) / out_name
    T.write(dest, itens, backup=False)

    com_words = sum(1 for i in itens if i.get("words"))
    c = P.load_cut(slug, name)
    c["transcript"] = out_name
    c["transcript_offset"] = 0.0
    P.save_cut(slug, c)
    lua = _gerar_legendas_lua(slug, name, out_name, split_screen)

    return {"ok": True, "path": str(dest), "file": out_name,
            "count": len(itens), "base": "media", "format": "giautosubs",
            "with_words": com_words, "offset_applied": offset,
            "transcript": out_name, **lua,
            "note": None if com_words else
                    "nenhum trecho tem tempo por palavra: o destaque da palavra "
                    "falada vai ficar desligado. Rode o Whisper com a opcao "
                    "'tempo por palavra'."}


def _build_captions(slug, name, cut, file, speakers_file, base, out_name,
                    fmt="srt", split_screen=None):
    """O corpo da geracao de legenda, sem HTTP em volta.

    Separado do endpoint porque agora ha DOIS caminhos ate aqui: o botao
    "Gerar legenda" (escolha a escolha, no modal) e o final de uma rodada, que
    gera o .srt junto sem perguntar nada. Os dois tem que produzir o mesmo
    arquivo - se a conta do offset morasse dentro do endpoint, a versao
    automatica seria uma segunda implementacao da mesma coisa, e a que
    estivesse errada seria a que ninguem confere.

    `fmt="giautosubs"` grava o json do GiAutoSubs em vez do `.srt`. E' o mesmo
    texto, com duas diferencas que importam: o tempo por palavra sobrevive (o
    `.srt` nao tem onde guarda-lo, e e' ele que acende a palavra falada), e o
    tempo fica ABSOLUTO - quem desconta o inicio do corte, do outro lado, e' o
    proprio `giautosubs.py`, lendo o `corte.json`.
    """
    if base not in ("timeline", "media"):
        fail(400, "base tem que ser 'timeline' ou 'media'")
    if fmt not in ("srt", "giautosubs"):
        fail(400, "format tem que ser 'srt' ou 'giautosubs'")

    src = _cut_file(slug, name, file)
    if src.suffix.lower() in (".srt", ".vtt"):
        segs = captions.parse_srt(src.read_text(encoding="utf-8-sig"))
    else:
        raw = T.read_raw(src)
        # `words` viaja junto: ele nao serve pro .srt, mas e' o que faz o
        # destaque por palavra existir do lado do GiAutoSubs. Descartar aqui
        # seria descartar sem ninguem pedir - e o sintoma, la na frente, e'
        # "as legendas entraram e a bolha nao acende".
        segs = [{"start": float(x["start"]), "end": float(x["end"]),
                 "text": (x.get("text") or "").strip(),
                 "words": x.get("words")}
                for x in raw if isinstance(x, dict) and "start" in x
                and (x.get("text") or "").strip()]
    if not segs:
        fail(400, f"{src.name} nao tem texto - escolha a transcricao "
                  f"(o arquivo do Whisper), nao a diarizacao")

    if fmt == "giautosubs":
        return _write_giautosubs(slug, name, cut, file, segs, out_name,
                                 split_screen)

    if speakers_file:
        turns = T.read_raw(_cut_file(slug, name, speakers_file))
        key = T.detect_label_key(turns)
        if not key:
            fail(400, f"{speakers_file} nao tem rotulo de falante")
        segs = captions.with_speakers(segs, turns, key)

    offset = -float(cut["start"]) if base == "timeline" else 0.0
    text = captions.to_srt(segs, offset=offset, fps=cut["fps"])
    out_name = out_name or f"{Path(file).stem}.srt"
    if not re.fullmatch(r"[\w.\-]+\.(srt|vtt)", out_name):
        fail(400, "nome de saida invalido (use algo como legendas.srt)")
    dest = P.legendas_dir(slug, name) / out_name
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)
    return {"ok": True, "path": str(dest), "file": out_name,
            "count": text.count("-->"), "base": base,
            "speakers_file": speakers_file, "offset_applied": offset}


@app.post("/api/projects/{slug}/cuts/{name}/captions")
def api_captions(slug: str, name: str, body: CaptionsIn):
    """Gera o .srt que o Resolve importa (Timeline > Import > Subtitle).

    `base="timeline"` (padrao) subtrai o inicio do corte, porque a timeline que
    o SpeakerSwitch cria comeca no frame 0 - legenda em tempo absoluto entraria
    43 minutos adiantada, e o Resolve aceitaria sem reclamar. `base="media"`
    para legendar o episodio inteiro.
    """
    _guard(P.load_project, slug)
    cut = _guard(P.load_cut, slug, name)
    return _build_captions(slug, name, cut, body.file, body.speakers_file,
                           body.base, body.out_name, body.format,
                           body.split_screen)


@app.post("/api/projects/{slug}/cuts/{name}/transcript")
def api_import_transcript(slug: str, name: str):
    """Escolhe qualquer transcricao do disco (.json ou .srt) para a coluna
    "o que foi dito" do editor.

    Aceita SRT porque legenda ja pronta e' transcricao: o `EpisodioPiloto.srt`
    que ja existe em resultados\\ serve, sem converter nada antes.

    O offset e' DETECTADO, nao perguntado: se os tempos do arquivo nao caem
    dentro do corte mas caem depois de somar o inicio dele, e' porque a
    transcricao esta em tempo relativo - e o app soma. E' o mesmo engano das
    duas bases, so que agora resolvido na hora de importar.
    """
    cut = _guard(P.load_cut, slug, name)
    d = P.cut_dir(slug, name)
    turnsd = P.turns_dir(slug, name)
    chosen = _run_picker(_PICKER_TRANSCRIPT, d)
    if not chosen:
        return {"path": None}
    f = Path(chosen).resolve()
    if not f.is_file():
        fail(400, f"arquivo nao encontrado: {chosen}")
    try:
        if f.suffix.lower() in (".srt", ".vtt"):
            segs = captions.parse_srt(f.read_text(encoding="utf-8-sig"))
        else:
            raw = T.read_raw(f)
            segs = [{"start": float(x["start"]), "end": float(x["end"]),
                     "text": (x.get("text") or "").strip()}
                    for x in raw if isinstance(x, dict) and "start" in x
                    and "end" in x and (x.get("text") or "").strip()]
    except Exception as e:
        fail(400, f"{f.name}: nao consegui ler ({e})")
    if not segs:
        fail(400, f"{f.name} nao tem nenhum trecho com texto")

    a, b = min(s["start"] for s in segs), max(s["end"] for s in segs)
    inside = (b >= cut["start"] - 5 and a <= cut["end"] + 5)
    offset = 0.0 if inside else float(cut["start"])
    if not inside:
        shifted_a, shifted_b = a + offset, b + offset
        if not (shifted_b >= cut["start"] - 5 and shifted_a <= cut["end"] + 5):
            offset = 0.0        # nao bate de jeito nenhum: nao inventa offset

    # SRT vira json na pasta do corte - o editor le json, e assim o arquivo
    # importado fica junto do resto do corte em vez de virar um link solto
    if f.suffix.lower() in (".srt", ".vtt") or f.parent not in (d, turnsd):
        dest = turnsd / f"transcricao_{P.slugify(f.stem)}.json"
        T.write(dest, [{"start": round(s["start"], 5), "end": round(s["end"], 5),
                        "text": s["text"]} for s in segs], backup=False)
        rel = dest.name
    else:
        rel = f.name

    cut["transcript"] = rel
    cut["transcript_offset"] = offset
    P.save_cut(slug, cut)
    return {"path": str(f), "file": rel, "count": len(segs),
            "offset": offset, "span": [a, b],
            "detected": "relativo ao corte" if offset else "absoluto"}


class RenameIn(BaseModel):
    file: str
    mapping: dict
    label_key: str = "name"


@app.post("/api/projects/{slug}/cuts/{name}/labels")
def api_rename(slug: str, name: str, body: RenameIn):
    """SPEAKER_00 -> Giovanni, de uma vez, no arquivo inteiro.

    O SpeakerSwitch mapeia track por NOME. Sem isto, a ponte entre "o
    diarizador achou 4 vozes" e "quem e' quem" seria trocar o rotulo turno a
    turno no editor - centenas de vezes.
    """
    _guard(P.load_cut, slug, name)
    f = P.turns_dir(slug, name) / body.file
    if not f.is_file():
        fail(404, f"arquivo nao encontrado no corte: {body.file}")
    return _guard(T.rename_labels, f, body.mapping, body.label_key)


@app.get("/api/projects/{slug}/cuts/{name}/samples")
def api_samples(slug: str, name: str):
    """Amostras de audio por voz (o 1_diarize_v3.py grava essas)."""
    d = P.cut_dir(slug, name) / "speaker_samples"
    if not d.is_dir():
        return {"samples": []}
    out = []
    for f in sorted(d.glob("*.wav")):
        # os nomes saem como SPEAKER_00_1.wav
        m = re.match(r"(.+?)_(\d+)\.wav$", f.name)
        out.append({"file": f.name, "label": m.group(1) if m else f.stem,
                    "url": f"/api/projects/{slug}/cuts/{name}/samples/{f.name}"})
    return {"samples": out}


@app.get("/api/projects/{slug}/cuts/{name}/samples/{file}")
def api_sample(slug: str, name: str, file: str):
    d = P.cut_dir(slug, name) / "speaker_samples"
    f = _guard(P._child, d, file)
    if not f.is_file():
        fail(404, "amostra nao encontrada")
    return FileResponse(f, media_type="audio/wav")


# Aqui morava POST /cuts/{name}/speaker-switch, que gravava o arquivo-ponte
# `speaker_switch.json`. Aposentado em 02/09: o editor_proxy\SpeakerSwitch.py
# le o corte.json direto, entao a ponte era uma copia dos mesmos campos que
# dependia de alguem lembrar de clicar num botao.


# ------------------------------------------------ onda/audio do projeto

def _project_file(slug, rel):
    d = P.project_dir(slug).resolve()
    f = (d / str(rel).replace("/", os.sep)).resolve()
    if not (f == d or d in f.parents) or not f.is_file():
        fail(404, f"arquivo fora do projeto ou inexistente: {rel}")
    return f


@app.get("/api/projects/{slug}/peaks")
def api_project_peaks(slug: str, file: str | None = None):
    p = _guard(P.load_project, slug)
    wav = _project_file(slug, file or p["audio"])
    return _peaks_response(wav)


@app.api_route("/api/projects/{slug}/audio", methods=["GET", "HEAD"])
def api_project_audio_stream(slug: str, request: Request, file: str | None = None):
    p = _guard(P.load_project, slug)
    return _audio_response(request, _project_file(slug, file or p["audio"]))


# =========================================================== etapa 3
# API identica a do turnsEditor - o app.js copiado chama exatamente estes
# endpoints, com estes formatos. O que muda e' a origem: o "config" abaixo e'
# derivado do corte ativo, nao lido de um arquivo fixo.

def _active():
    slug, name = CFG.get("active_project"), CFG.get("active_cut")
    if not slug or not name:
        fail(409, "nenhum corte ativo - escolha um na etapa 2 (Cortes)")
    return _guard(P.load_project, slug), _guard(P.load_cut, slug, name)


def _editor_prefs():
    return CFG.setdefault("editor_prefs", {
        "time_base": "relative", "display_zero": None,
        "speaker_colors": {}, "speaker_order": None,
        "manual_only_names": [P.MANUAL_TRACK_NAME],
    })


def _off_camera_names(p):
    """Quem cai na BASE_TRACK: as vozes fora de quadro + o rotulo de silencio."""
    out = list(p.get("off_camera", []))
    silencio = CFG.get("silence_label")
    if silencio and silencio not in out:
        out.append(silencio)
    return out


def _colors_for(p, prefs):
    cols = dict(CFG["reserved_colors"])
    for i, x in enumerate(p["participants"]):
        cols[x["name"]] = PALETTE[i % len(PALETTE)]
    for i, n in enumerate(p.get("off_camera", [])):
        cols.setdefault(n, OFF_CAMERA_SHADES[i % len(OFF_CAMERA_SHADES)])
    cols.update(prefs.get("speaker_colors") or {})
    return cols


def editor_config():
    """O config.json do turnsEditor, montado a partir do corte ativo.

    `audio_offset` = inicio do corte: o wav fatiado comeca no zero e os turnos
    estao em tempo absoluto, entao a soma alinha os dois. Era exatamente esse
    numero que antes vivia sendo redescoberto a mao.
    """
    p, cut = _active()
    d = P.cut_dir(p["slug"], cut["name"])
    prefs = _editor_prefs()
    order = ([x["name"] for x in p["participants"]]
             + list(p.get("off_camera", [])) + [P.MANUAL_TRACK_NAME])
    return {
        # os turns*.json moram em turns\ ; audio/video continuam na raiz do
        # corte - por isso os dois nao sao mais o mesmo caminho.
        "results_dir": str(P.turns_dir(p["slug"], cut["name"])),
        "media_dir": str(d),
        "fps": float(cut["fps"]),
        "min_span_frames": int(CFG["min_span_frames"]),
        "audio_file": cut["audio"],
        "audio_offset": float(cut["audio_offset"]),
        "transcript_file": cut.get("transcript") or "",
        "transcript_offset": float(cut.get("transcript_offset") or 0.0),
        "last_turns_file": cut.get("last_turns_file") or "",
        "default_save_name": cut.get("default_save_name", "turnsManual.json"),
        "time_base": prefs.get("time_base", "relative"),
        "display_zero": prefs.get("display_zero"),
        "speaker_colors": _colors_for(p, prefs),
        "speaker_order": prefs.get("speaker_order") or order,
        "manual_only_names": prefs.get("manual_only_names",
                                       [P.MANUAL_TRACK_NAME]),
        # o rotulo de silencio entra SEMPRE, mesmo que nao seja um dos
        # nomes do projeto: rodada ANTIGA carimbou `no_name` nos vazios (o
        # fill_gaps ja saiu), e com as vozes numeradas esse `no_name`
        # nao estaria em lista nenhuma - o SpeakerSwitch aborta o corte
        # inteiro com "nome desconhecido no json". Silencio nao tem track
        # por definicao, entao o lugar dele eh aqui.
        "off_camera_names": _off_camera_names(p),
    }


def _extra_dirs():
    out = []
    raw = CFG.get("extra_turns_dirs") or []
    # config editada a mao pode virar string em vez de lista; sem isto o loop
    # iteraria LETRA por letra e a pasta sumiria sem aviso
    if isinstance(raw, str):
        raw = [raw]
    for x in raw:
        try:
            d = Path(x).resolve()
        except OSError:
            continue
        if d.is_dir():
            out.append(d)
    return out


def _roots():
    p, cut = _active()
    return [P.cut_dir(p["slug"], cut["name"]).resolve(),
            P.turns_dir(p["slug"], cut["name"]).resolve(),
            P.legendas_dir(p["slug"], cut["name"]).resolve(),
            (P.project_dir(p["slug"]) / "media").resolve()] + _extra_dirs()


def _safe_path(name, must_exist=True):
    if not name:
        fail(400, "nome de arquivo vazio")
    roots = _roots()
    q = Path(name)
    cands = [q] if q.is_absolute() else [r / name for r in roots]
    for c in cands:
        try:
            c = c.resolve()
        except OSError:
            continue
        if not any(c == r or r in c.parents for r in roots):
            continue
        if must_exist and not c.is_file():
            continue
        return c
    fail(404 if must_exist else 400,
         f"arquivo fora das pastas permitidas ou inexistente: {name}")


@app.get("/api/config")
def api_config():
    cfg = editor_config()
    p, cut = _active()
    results = Path(cfg["results_dir"])
    turn_files = []
    # a pasta do corte primeiro (nome curto), depois as pastas extras. Nas
    # extras o "nome" e' o CAMINHO INTEIRO de proposito: dois cortes podem ter
    # um `turnsManual.json` cada, e um dropdown com dois itens iguais que
    # abrem arquivos diferentes seria pior do que uma linha comprida.
    listing = ([(f, f.name) for f in sorted(results.glob("*.json"))]
               + [(f, str(f)) for d in _extra_dirs()
                  for f in sorted(d.glob("*.json")) if d != results])
    for f, label in listing:
        if f.name in ("corte.json", "speaker_switch.json"):
            continue
        # backups ficam fora do seletor: cada salvamento gera um, e em duas
        # tardes eles seriam a maioria da lista. Continuam no disco - recuperar
        # um e' trabalho do Explorer, nao de um dropdown onde da pra abri-lo
        # por engano e salvar por cima.
        if ".bak." in f.name:
            continue
        try:
            raw = T.read_raw(f)
        except Exception:
            continue
        if not T.is_turns_file(raw):
            continue
        turn_files.append({
            "name": label, "count": len(raw),
            "label_key": T.detect_label_key(raw),
            "span": [float(min(x["start"] for x in raw)),
                     float(max(x["end"] for x in raw))],
            "keys": sorted({k for x in raw for k in x}),
            "mtime": f.stat().st_mtime,
        })
    audios = []
    for folder in _roots():
        for f in sorted(folder.glob("*.wav")):
            try:
                audios.append(media.wav_info(f))
            except Exception as e:
                print(f"[!] {f.name}: {e}")
    return {"config": cfg, "turn_files": turn_files, "audio_files": audios,
            "min_span_seconds": tc.min_span_seconds(cfg["fps"],
                                                    cfg["min_span_frames"]),
            "context": {"project": p["slug"], "project_name": p["name"],
                        "cut": cut["name"], "start": cut["start"],
                        "end": cut["end"], "origin_frame": cut["origin_frame"]}}


class ConfigPatch(BaseModel):
    fps: float | None = None
    min_span_frames: int | None = None
    audio_file: str | None = None
    audio_offset: float | None = None
    transcript_file: str | None = None
    transcript_offset: float | None = None
    last_turns_file: str | None = None
    default_save_name: str | None = None
    time_base: str | None = None
    display_zero: float | None = None
    speaker_colors: dict | None = None
    speaker_order: list | None = None
    manual_only_names: list | None = None


# o que e' do corte vai pro manifesto do corte; o que e' gosto do editor vai
# pras preferencias globais. Sem isso, mudar a cor de alguem num corte mudaria
# o offset de outro.
_CUT_KEYS = {
    "fps": "fps",
    "audio_file": "audio",
    "audio_offset": "audio_offset",
    "transcript_file": "transcript",
    "transcript_offset": "transcript_offset",
    "last_turns_file": "last_turns_file",
    "default_save_name": "default_save_name",
}
_PREF_KEYS = {"time_base", "display_zero", "speaker_colors", "speaker_order",
              "manual_only_names"}


@app.post("/api/config")
def api_config_set(patch: ConfigPatch, clear: str = ""):
    p, cut = _active()
    prefs = _editor_prefs()
    data = patch.model_dump(exclude_none=True)
    touched_cut = False
    for k, v in data.items():
        if k in _CUT_KEYS:
            cut[_CUT_KEYS[k]] = v
            touched_cut = True
        elif k in _PREF_KEYS:
            prefs[k] = v
        elif k == "min_span_frames":
            CFG["min_span_frames"] = int(v)
    # `clear` existe porque exclude_none nao distingue "nao mandei" de "quero
    # None" - e' assim que o botao "usar o primeiro turno" zera o display_zero
    for k in filter(None, clear.split(",")):
        if k in _PREF_KEYS:
            prefs[k] = None
    if touched_cut:
        if "fps" in data:
            cut["origin_frame"] = tc.seconds_to_frame(cut["start"], cut["fps"])
        P.save_cut(p["slug"], cut)
    config.save(CFG)
    return {"ok": True, "config": editor_config()}


@app.get("/api/turns")
def api_turns(file: str = Query(...)):
    path = _safe_path(file)
    cfg = editor_config()
    data = _guard(T.load, path)
    data["issues"] = T.analyze(data["turns"], cfg["fps"], cfg["min_span_frames"])
    data["file"] = path.name
    data["path"] = str(path)
    data["span"] = T.span(data["turns"])
    data["labels"] = sorted({t["label"] for t in data["turns"]
                             if t["label"] is not None})
    return data


class TurnIn(BaseModel):
    start: float
    end: float
    label: str | None = None
    extra: dict = {}


class SaveIn(BaseModel):
    file: str
    save_as: str
    label_key: str | None = "name"
    turns: list[TurnIn]
    overwrite: bool = False
    snap_to_frames: bool = False


@app.post("/api/turns")
def api_save(body: SaveIn):
    if not re.fullmatch(r"[\w.\-]+\.json", body.save_as):
        fail(400, "nome de destino invalido (algo como turnsMeuCorte.json, "
                  "sem barras)")
    p, cut = _active()
    dest = P.turns_dir(p["slug"], cut["name"]) / body.save_as
    if dest.exists() and not body.overwrite:
        fail(409, f"{dest.name} ja existe - confirme a sobrescrita "
                  f"(um .bak sera criado)")
    fps = float(cut["fps"])
    out = []
    for t in sorted(body.turns, key=lambda t: t.start):
        s, e = t.start, t.end
        if body.snap_to_frames:
            s, e = tc.snap_to_frame(s, fps), tc.snap_to_frame(e, fps)
        item = {"start": round(s, 5), "end": round(e, 5)}
        if body.label_key:
            item[body.label_key] = t.label
        item.update(t.extra or {})
        out.append(item)
    bak = T.write(dest, out, backup=True)
    cut["last_turns_file"] = dest.name
    P.save_cut(p["slug"], cut)
    return {"ok": True, "path": str(dest), "count": len(out),
            "backup": bak.name if bak else None}


@app.get("/api/transcript")
def api_transcript(file: str | None = None, offset: float | None = None):
    cfg = editor_config()
    name = file or cfg["transcript_file"]
    off = cfg["transcript_offset"] if offset is None else offset
    if not name:
        return {"segments": [], "file": "", "offset": off,
                "error": "este corte ainda nao tem transcricao - rode o "
                         "metodo Whisper na etapa 2"}
    try:
        path = _safe_path(name)
    except HTTPException:
        return {"segments": [], "file": name, "offset": off,
                "error": f"transcricao nao encontrada: {name}"}
    raw = T.read_raw(path)
    segs = [{"start": float(x["start"]) + off, "end": float(x["end"]) + off,
             "text": (x.get("text") or "").strip()}
            for x in raw
            if isinstance(x, dict) and "start" in x and "end" in x
            and (x.get("text") or "").strip()]
    # `with_words` nao entra em `segments` de proposito: o editor so' mostra o
    # texto, e o app.js e' copia literal do turnsEditor. Ele existe para a tela
    # poder dizer se este arquivo e' o formato completo do GiAutoSubs (com tempo
    # por palavra) ou so' o texto - a diferenca entre a palavra falada acender
    # ou nao, la no Resolve.
    com_words = sum(1 for x in raw
                    if isinstance(x, dict) and isinstance(x.get("words"), list)
                    and x["words"])
    return {"segments": segs, "file": path.name, "offset": off,
            "with_words": com_words,
            "span": [segs[0]["start"], segs[-1]["end"]] if segs else None}


def _peaks_response(wav):
    p = _guard(media.build_peaks, wav)
    info = media.wav_info(wav)
    return Response(content=p.read_bytes(),
                    media_type="application/octet-stream",
                    headers={"X-Peaks-Per-Second": str(media.PEAKS_PER_SECOND),
                             "X-Audio-Duration": f"{info['duration']:.6f}",
                             "Cache-Control": "no-cache"})


@app.get("/api/peaks")
def api_peaks(file: str | None = None):
    cfg = editor_config()
    return _peaks_response(_safe_path(file or cfg["audio_file"]))


def _audio_response(request, path):
    """Serve wav com Range - sem isso o <audio> baixaria 130 MB antes de tocar
    o segundo 2600. HEAD entra explicito porque o APIRoute do FastAPI (ao
    contrario do Route do Starlette) nao adiciona HEAD junto com GET."""
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "audio/wav"
    if request.method == "HEAD":
        return Response(status_code=200, media_type=mime,
                        headers={"Accept-Ranges": "bytes",
                                 "Content-Length": str(size)})
    rng = request.headers.get("range")
    if not rng:
        return FileResponse(path, media_type=mime,
                            headers={"Accept-Ranges": "bytes"})
    m = re.match(r"bytes=(\d*)-(\d*)", rng)
    if not m:
        fail(416, "Range malformado")
    start = int(m.group(1)) if m.group(1) else 0
    end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
    if start > end:
        fail(416, "Range fora do arquivo")
    length = end - start + 1

    def stream():
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                block = f.read(min(256 * 1024, left))
                if not block:
                    break
                left -= len(block)
                yield block

    return StreamingResponse(
        stream(), status_code=206, media_type=mime,
        headers={"Content-Range": f"bytes {start}-{end}/{size}",
                 "Accept-Ranges": "bytes", "Content-Length": str(length)})


@app.api_route("/api/audio", methods=["GET", "HEAD"])
def api_audio(request: Request, file: str | None = None):
    cfg = editor_config()
    return _audio_response(request, _safe_path(file or cfg["audio_file"]))


# =========================================================== jobs

@app.get("/api/jobs")
def api_jobs():
    return {"jobs": jobs.listing()}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str, since: int = 0):
    j = jobs.get(job_id)
    if not j:
        fail(404, f"job desconhecido: {job_id}")
    return j.snapshot(since)


@app.post("/api/jobs/{job_id}/cancel")
def api_job_cancel(job_id: str):
    return {"ok": jobs.cancel(job_id)}


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    # cortes de antes da organizacao turns\/legendas\ - move o que sobrou
    # solto na raiz. Idempotente: nao acha nada pra mover depois da primeira vez.
    _moved = P.migrate_layout()
    if _moved:
        print(f"[i] migracao turns/legendas: {len(_moved)} arquivo(s) movido(s)")
        for _m in _moved:
            print(f"    -> {_m}")
    port = int(os.environ.get("PREPROD_PORT", CFG.get("port", 8740)))
    print(f"\n  pre_production  ->  http://127.0.0.1:{port}\n")
    print(f"  projetos : {CFG['projects_dir']}")
    print(f"  fontes   : {CFG['sources_dir']}")
    print(f"  scripts  : {CFG['scripts_dir']}")
    print(f"  python   : {CFG['python_exe']}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
