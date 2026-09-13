"""Midia: ffprobe, extracao/fatiamento de wav e a waveform pre-calculada.

Divisao de trabalho com o jobs.py: aqui a gente MONTA o comando do ffmpeg e faz
as leituras baratas (probe, info do wav, picos); quem roda comando longo e
acompanha o progresso e' o jobs.py. Assim o comando fica testavel sem subir
processo nenhum.

O wav sai em 16 kHz mono PCM 16-bit porque e' o que o pyannote quer e o que os
wav que ja existem em sourceMedia\\ usam - mudar isso quebraria a comparacao
entre uma diarizacao nova e as antigas.
"""

import hashlib
import json
import re
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

import config

PEAKS_PER_SECOND = 200          # mesma resolucao do turnsEditor
CACHE_DIR = config.ROOT / ".cache"
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".avi", ".webm", ".mts", ".ts"}

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class MediaError(RuntimeError):
    pass


# ------------------------------------------------------------------ probe

def _run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW)
    except FileNotFoundError:
        raise MediaError(f"nao achei {cmd[0]!r} no PATH - instale o ffmpeg "
                         f"(winget install Gyan.FFmpeg) ou aponte o caminho "
                         f"completo no config.json")
    except subprocess.TimeoutExpired:
        raise MediaError(f"{cmd[0]} nao respondeu em {timeout}s")
    if r.returncode != 0:
        raise MediaError((r.stderr or r.stdout or "").strip()[-500:])
    return r.stdout


def _fps_from(rate):
    """'60/1' ou '30000/1001' -> float. Vem assim do ffprobe."""
    if not rate:
        return None
    if "/" in str(rate):
        num, den = str(rate).split("/", 1)
        try:
            num, den = float(num), float(den)
        except ValueError:
            return None
        return num / den if den else None
    try:
        return float(rate)
    except ValueError:
        return None


def probe(path):
    """Especificas do arquivo-fonte. Levanta MediaError se nao der pra ler.

    O `fps` sai daqui e vai pro project.json porque TODA a matematica de frame
    depende dele: `int(round(segundos * fps))` e' a mesma conta do
    SpeakerSwitch e do timecode.py. Chutar 60 num arquivo 30fps deslocaria
    todo corte pela metade.
    """
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"arquivo nao encontrado: {path}")
    out = _run([config.CONFIG["ffprobe"], "-v", "error", "-show_format",
                "-show_streams", "-of", "json", str(path)])
    data = json.loads(out)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    dur = float(data.get("format", {}).get("duration") or 0.0)
    info = {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "duration": dur,
        "container": (data.get("format", {}).get("format_name") or "").split(",")[0],
    }
    if v:
        info.update({
            "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "vcodec": v.get("codec_name"),
            # avg_frame_rate mente em VFR; r_frame_rate e' o nominal, que e' o
            # que o Resolve usa na timeline.
            "fps": _fps_from(v.get("r_frame_rate")) or _fps_from(v.get("avg_frame_rate")),
        })
    if a:
        info.update({
            "acodec": a.get("codec_name"),
            "sample_rate": int(a.get("sample_rate") or 0),
            "channels": int(a.get("channels") or 0),
        })
    info["has_audio"] = a is not None
    if not info["has_audio"]:
        raise MediaError(f"{path.name} nao tem faixa de audio - nao da pra "
                         f"diarizar")
    return info


def list_videos(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            out.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
    return out


# ---------------------------------------------------------------- ffmpeg

def extract_wav_cmd(src, dest, start=None, end=None):
    """Comando de extracao do wav. `-progress pipe:1` e' o que da a barra.

    `-ss` ANTES do `-i` faz o ffmpeg pular por keyframe e so entao decodificar
    (rapido); como a saida e' audio PCM re-encodado, o corte sai preciso do
    mesmo jeito - o keyframe so afeta video.
    """
    cfg = config.CONFIG
    cmd = [cfg["ffmpeg"], "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if start is not None:
        cmd += ["-ss", f"{float(start):.6f}"]
    if end is not None:
        cmd += ["-to", f"{float(end):.6f}"]
    cmd += ["-i", str(src),
            "-vn",
            "-ac", str(cfg["wav_channels"]),
            "-ar", str(cfg["wav_sample_rate"]),
            "-c:a", "pcm_s16le",
            "-progress", "pipe:1", "-nostats",
            str(dest)]
    return cmd


def keyframe_before(video, t, look_back=20.0):
    """Maior keyframe <= t, em segundos. Devolve None se nao der pra saber.

    Existe por causa de um erro silencioso: remuxar video com `-c copy` NAO
    corta em qualquer frame - o ffmpeg volta ate o keyframe anterior, que pode
    estar varios segundos antes do que voce pediu. Se a gente entregasse esse
    trecho pro diarizador dizendo "isto comeca em 43:30", todo turno voltaria
    deslocado, e o deslocamento so apareceria no corte final, dentro do
    Resolve - o pior lugar possivel pra descobrir.

    Entao, em vez de fingir precisao: descobre onde o keyframe realmente esta,
    corta exatamente ali e ANOTA esse valor como o offset daquele video. O
    trecho fica um pouco mais longo do que o pedido; o tempo continua certo.

    `-read_intervals` limita a decodificacao a uma janela de ~20 s em volta do
    ponto - varrer os keyframes de um arquivo de 3 GB levaria minutos.

    A janela e' `inicio%FIM` (ponto absoluto), NAO `inicio%+duracao`: a forma
    com `+` conta a duracao a partir de onde o ffmpeg conseguiu buscar, e ele
    busca pro keyframe ANTERIOR ao inicio pedido. No Episodio1, procurando o
    keyframe antes de 6941.785, a janela `6921.785%+21` foi lida a partir de
    6916.367 e fechou em ~6937 - o keyframe certo (6941.367, a 0.4 s do corte)
    ficou de fora e sobrou o 6933.033, um GOP inteiro mais atras. Nao dava
    erro nenhum: so' um trecho 8,3 s mais longo do que precisava.
    """
    t = float(t)
    if t <= 0:
        return 0.0
    start = max(0.0, t - look_back)
    try:
        out = _run([config.CONFIG["ffprobe"], "-v", "error",
                    "-select_streams", "v:0", "-skip_frame", "nokey",
                    "-read_intervals", f"{start:.3f}%{t + 1.0:.3f}",
                    "-show_entries", "frame=pts_time,pkt_pts_time,best_effort_timestamp_time",
                    "-of", "json", str(video)], timeout=180)
        frames = json.loads(out).get("frames", [])
    except Exception:
        return None
    times = []
    for fr in frames:
        for k in ("pts_time", "pkt_pts_time", "best_effort_timestamp_time"):
            v = fr.get(k)
            if v not in (None, "N/A"):
                try:
                    times.append(float(v))
                except ValueError:
                    pass
                break
    before = [x for x in times if x <= t + 1e-6]
    if before:
        return max(before)
    return min(times) if times else None


def cut_video_cmd(src, dest, start, duration):
    """Remuxa um trecho sem recodificar (`-c copy`) - segundos, nao minutos.

    `-ss` antes do `-i` (busca rapida) e `-t` DEPOIS do `-i` (duracao da
    saida): assim nao depende de como esta versao do ffmpeg interpreta um
    `-to` de entrada. `-movflags +faststart` so' vale pra mp4 - num .mkv o
    ffmpeg reclama da opcao desconhecida e o passo morre.
    """
    cfg = config.CONFIG
    cmd = [cfg["ffmpeg"], "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-ss", f"{float(start):.6f}",
           "-i", str(src),
           "-t", f"{float(duration):.6f}",
           "-c", "copy", "-avoid_negative_ts", "make_zero"]
    if Path(dest).suffix.lower() in (".mp4", ".m4v", ".mov"):
        cmd += ["-movflags", "+faststart"]
    return cmd + ["-progress", "pipe:1", "-nostats", str(dest)]


_PROGRESS_RE = re.compile(r"^(out_time_us|out_time_ms|progress)=(.+)$")


def ffmpeg_progress(line, total_seconds):
    """Le uma linha de `-progress pipe:1` e devolve 0..1, ou None.

    out_time_us e' microssegundos; o `out_time_ms` do ffmpeg tambem vem em
    MICROssegundos (nome historico errado) - por isso os dois dividem por 1e6.
    """
    m = _PROGRESS_RE.match(line.strip())
    if not m or not total_seconds:
        return None
    key, val = m.group(1), m.group(2).strip()
    if key == "progress":
        return 1.0 if val == "end" else None
    try:
        return max(0.0, min(1.0, (int(val) / 1e6) / float(total_seconds)))
    except ValueError:
        return None


# -------------------------------------------------------------- waveform

def wav_info(path):
    path = Path(path)
    with wave.open(str(path), "rb") as w:
        n, sr = w.getnframes(), w.getframerate()
        return {"name": path.name, "path": str(path), "sample_rate": sr,
                "channels": w.getnchannels(), "duration": (n / sr) if sr else 0.0}


def _peaks_path(wav_path):
    """Cache fora das pastas de projeto: e' derivado, da pra apagar sem dó.

    A chave inclui um hash do caminho absoluto porque dois projetos diferentes
    podem ter um `audio.wav` cada - so o stem colidiria.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    h = hashlib.sha1(str(Path(wav_path).resolve()).encode()).hexdigest()[:10]
    return CACHE_DIR / f"{Path(wav_path).stem}-{h}.peaks{PEAKS_PER_SECOND}.bin"


def build_peaks(wav_path, pps=PEAKS_PER_SECOND):
    """Min/max por bucket em int8 - 2 bytes por bucket, gravados num .bin.

    Le em pedacos: um wav de 69 min tem ~66M amostras e carregar tudo na RAM
    so pra desenhar uma onda de 1200 px de largura nao paga.
    """
    wav_path = Path(wav_path)
    out = _peaks_path(wav_path)
    if out.exists() and out.stat().st_mtime >= wav_path.stat().st_mtime:
        return out
    t0 = time.time()
    with wave.open(str(wav_path), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if sw != 2:
            raise MediaError(f"{wav_path.name}: so leio WAV PCM 16-bit "
                             f"(esse tem {sw * 8}-bit)")
        per_bucket = max(1, int(round(sr / pps)))
        buf = bytearray()
        leftover = np.empty(0, dtype=np.int16)
        while True:
            data = w.readframes(per_bucket * 4096)
            if not data:
                break
            a = np.frombuffer(data, dtype="<i2")
            if ch > 1:
                a = a.reshape(-1, ch).mean(axis=1).astype(np.int16)
            a = np.concatenate([leftover, a]) if leftover.size else a
            usable = (a.size // per_bucket) * per_bucket
            leftover = a[usable:].copy()
            if not usable:
                continue
            b = a[:usable].reshape(-1, per_bucket)
            lo = (b.min(axis=1) >> 8).astype(np.int8)
            hi = (b.max(axis=1) >> 8).astype(np.int8)
            buf += np.stack([lo, hi], axis=1).tobytes()
        if leftover.size:
            buf += bytes([np.int8(leftover.min() >> 8).tobytes()[0],
                          np.int8(leftover.max() >> 8).tobytes()[0]])
    out.write_bytes(bytes(buf))
    print(f"[i] waveform de {wav_path.name} em {time.time() - t0:.1f}s "
          f"-> {len(buf) // 2} buckets @ {pps}/s")
    return out
