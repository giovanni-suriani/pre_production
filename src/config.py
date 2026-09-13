"""Config do pre_production - caminhos, interpretadores e estado ativo.

O app inteiro so escreve dentro de `projects_dir`. Tudo que fica fora dele
(`sources_dir`, `scripts_dir`) e' so LEITURA: os videos-fonte sao do usuario e
os scripts de diarizacao vivem em scriptsPrimarios\\, que este projeto nao
toca - ele chama os scripts la onde eles ja estao, por caminho absoluto, em
vez de duplicar diarizador nenhum.

Dois interpretadores diferentes rodam neste sistema, de proposito:

  * o do `.venv` deste projeto - so fastapi/uvicorn/numpy, sobe em segundos;
  * `python_exe` - o Python 3.12 do sistema, onde moram torch+pyannote+
    faster-whisper+google-genai, cujas versoes estao presas umas as outras
    (ver CLAUDE.md). Instalar esse mundo dentro do venv de um servidor web so
    pra chamar um script seria arrastar a fragilidade pra dentro daqui.

Por isso `python_exe` e' config, nao `sys.executable`.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # pre_production\
CONFIG_PATH = ROOT / "config.json"
ENV_PATH = ROOT / ".env"

# pacotes que cada familia de metodo precisa - usado pelo /api/doctor pra dizer
# "esse metodo nao vai rodar" ANTES de gastar 20 minutos descobrindo isso.
PROBE_PACKAGES = ["pyannote.audio", "torch", "faster_whisper", "google.genai",
                  "dotenv", "pydantic"]

DEFAULT_CONFIG = {
    # onde os projetos deste app vivem (unica pasta com escrita)
    "projects_dir": str(ROOT / "projects"),
    # onde procurar mp4/mkv/mov ao criar um projeto (so leitura)
    "sources_dir": r"D:\CanalYtbe\BatataQuente\Raw_videos",
    # onde estao 1_diarize.py, 3c_diarize_gemini_chunks.py etc (so leitura)
    "scripts_dir": r"D:\CanalYtbe\BatataQuente\scriptsPrimarios",
    # Python com torch/pyannote/genai - NAO e' o do venv deste app.
    # null = detectar sozinho no primeiro boot.
    "python_exe": None,
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    # 16 kHz mono: o que o pyannote quer e o que os wav ja existentes usam.
    "wav_sample_rate": 16000,
    "wav_channels": 1,
    # fps padrao quando o ffprobe nao souber dizer. 60 e' o do EpisodioPiloto.
    "fps_fallback": 60.0,
    # minimo que o Resolve aceita num clipe - espelha MIN_SPAN_FRAMES do
    # SpeakerSwitch.py. Turno abaixo disso SOME do corte final sem avisar.
    "min_span_frames": 2,
    # Vazio (ninguem falando) >= isto vira um turno com o rotulo abaixo, ao
    # gravar o arquivo canonico de DIARIZACAO - ver turns.fill_gaps(). Menos
    # que isso e' pausa de respiracao entre frases, nao silencio. 0 desliga.
    "silence_min_seconds": 0.5,
    "silence_label": "no_name",
    # Pastas EXTRAS de turns*.json que a etapa 3 pode abrir, alem da pasta do
    # corte. So leitura - gravar continua acontecendo dentro do projeto.
    # Serve pra abrir um arquivo de fora (os turnos antigos em
    # scriptsPrimarios\resultados\, ou o corte de outro projeto) sem ter que
    # copiar arquivo pra ca. A tela da etapa 2 acrescenta pasta aqui sozinha
    # quando voce escolhe um arquivo no dialogo.
    "extra_turns_dirs": [],
    # qual projeto/corte a etapa 3 (turnsEditor) esta olhando agora. Fica no
    # servidor porque o app.js copiado do turnsEditor chama /api/config sem
    # parametro nenhum - quem sabe o contexto e' o servidor, nao a pagina.
    "active_project": None,
    "active_cut": None,
    "port": 8740,
    # cores por participante sao geradas do nome; estas duas sao fixas porque
    # significam coisas, nao pessoas (ver README).
    "reserved_colors": {"no_name": "#6b7280", "cut": "#a78bfa"},
}


def _detect_python():
    """Acha um python.exe que tenha pyannote/torch instalados.

    Ordem: o Python 3.12 per-user que a CLAUDE.md registra > qualquer
    Python3xx em Programs\\Python > `py -3` > PATH. Descarta o interpretador
    do proprio venv (sys.prefix), que de proposito nao tem esse mundo.
    """
    cands = []
    home = Path.home()
    known = home / "AppData/Local/Programs/Python/Python312/python.exe"
    if known.is_file():
        cands.append(str(known))
    progs = home / "AppData/Local/Programs/Python"
    if progs.is_dir():
        cands += [str(p / "python.exe") for p in sorted(progs.iterdir(),
                                                        reverse=True)
                  if (p / "python.exe").is_file()]
    try:
        r = subprocess.run(["py", "-3", "-c", "import sys;print(sys.executable)"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            cands.append(r.stdout.strip())
    except Exception:
        pass
    for name in ("python", "python3"):
        w = shutil.which(name)
        if w:
            cands.append(w)

    venv = Path(sys.prefix).resolve()
    seen, fallback = set(), None
    for c in cands:
        try:
            p = Path(c).resolve()
        except OSError:
            continue
        if str(p) in seen or not p.is_file():
            continue
        seen.add(str(p))
        if venv in p.parents:          # o proprio venv deste app
            continue
        if fallback is None:
            fallback = str(p)
        if _has_package(str(p), "pyannote.audio"):
            return str(p)
    return fallback or sys.executable


def _has_package(exe, mod):
    try:
        r = subprocess.run(
            [exe, "-c", f"import importlib.util as u;"
                        f"raise SystemExit(0 if u.find_spec({mod!r}) else 1)"],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


def probe_python(exe):
    """Diz quais dos PROBE_PACKAGES esse interpretador tem. Uma chamada so."""
    code = ("import importlib.util as u,json,sys;"
            f"print(json.dumps({{n: u.find_spec(n) is not None "
            f"for n in {PROBE_PACKAGES!r}}}))")
    try:
        r = subprocess.run([exe, "-c", code], capture_output=True, text=True,
                           timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"_error": str(e)}
    return {"_error": (r.stderr or "").strip()[-300:]}


def _read_env_file(path):
    """Le um .env pro os.environ sem sobrescrever o que ja existe."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def load_env(scripts_dir=None):
    """Carrega o .env deste projeto e tambem o de scriptsPrimarios\\.

    O daqui serve pro HF_TOKEN, que o pyannote exige e que (checado) nao esta
    setado como variavel de usuario nesta maquina.

    O de la e' lido so pra CHECAGEM. Os scripts de Gemini ja carregam esse
    arquivo sozinhos (`load_dotenv` na pasta deles), entao eles funcionariam
    de qualquer jeito - mas sem ler o mesmo arquivo, a tela diria "falta
    GEMINI_API_KEY" pra um metodo que rodaria numa boa. Um falso alarme desses
    faz a pessoa parar de acreditar nos alarmes de verdade.

    Nenhum dos dois sobrescreve variavel ja existente no ambiente.
    """
    _read_env_file(ENV_PATH)
    base = scripts_dir or DEFAULT_CONFIG["scripts_dir"]
    _read_env_file(Path(base) / ".env")


def load():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            # utf-8-SIG, nao utf-8: no Windows quase tudo que edita texto
            # (Notepad, VS Code, `Set-Content -Encoding utf8` do PowerShell 5)
            # grava BOM. Lido como utf-8 puro, o BOM quebra o json.loads e a
            # config INTEIRA voltava pros defaults sem nada explodir - dava pra
            # editar o arquivo, salvar, e nada mudar. utf-8-sig le os dois.
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
        except Exception as e:
            print(f"[!] config.json ilegivel ({e}) - SEGUINDO COM OS DEFAULTS; "
                  f"o que estiver no arquivo esta sendo ignorado")
    if not cfg.get("python_exe"):
        cfg["python_exe"] = _detect_python()
        print(f"[i] python de diarizacao detectado: {cfg['python_exe']}")
    Path(cfg["projects_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg


def save(cfg):
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(CONFIG_PATH)


CONFIG = load()
load_env(CONFIG["scripts_dir"])   # depois do load: respeita scripts_dir do config


def projects_dir():
    return Path(CONFIG["projects_dir"]).resolve()


def scripts_dir():
    return Path(CONFIG["scripts_dir"]).resolve()


def subprocess_env():
    """Env pros subprocessos: o do app + o .env daqui, ja carregado."""
    return dict(os.environ)
