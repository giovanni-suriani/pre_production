"""Conversoes de tempo entre segundos, timecode legivel e frames.

Por que isso existe: os arquivos turns*.json guardam SEGUNDOS (float), mas o
SpeakerSwitch.py converte pra FRAMES com `int(round(segundos * fps))` e o
Resolve rejeita clipe com menos de MIN_SPAN_FRAMES frames. Editar segundos
"crus" na mao e' desconfortavel e ainda deixa passar trecho curto demais que
so quebra la na frente, dentro do Resolve. Aqui a gente centraliza as duas
coisas: formatar pra MM:SS.mmm (o jeito que da pra pensar) e checar o que vira
frame no fim das contas.

Espelhado em static/app.js (parseTime/formatTime) - se mexer aqui, mexa la.
"""

import math
import re

# fps do projeto. O SpeakerSwitch le o fps real da timeline do Resolve; aqui e'
# so pra dizer quantos frames um trecho VAI virar, entao fica configuravel.
DEFAULT_FPS = 60.0
# Resolve rejeita clipe com startFrame == endFrame; o SpeakerSwitch usa 2.
MIN_SPAN_FRAMES = 2

_TIME_RE = re.compile(
    r"""^\s*
    (?:(?P<h>\d+):)?          # horas, opcional
    (?:(?P<m>\d+):)?          # minutos, opcional
    (?P<s>\d+(?:[.,]\d+)?)    # segundos, com decimais opcionais
    \s*$""",
    re.VERBOSE,
)


def parse_time(value):
    """Aceita os formatos que da vontade de digitar e devolve segundos (float).

    "2610"          -> 2610.0      (segundos crus, como esta no json)
    "43:30"         -> 2610.0
    "43:30.5"       -> 2610.5
    "1:03:30.100"   -> 3810.1
    "43:30,5"       -> 2610.5      (virgula decimal, teclado BR)

    Levanta ValueError se nao der pra entender - o chamador decide o que fazer.
    """
    if isinstance(value, (int, float)):
        return float(value)
    m = _TIME_RE.match(str(value))
    if not m:
        raise ValueError(f"tempo invalido: {value!r}")
    h, mi, s = m.group("h"), m.group("m"), m.group("s")
    # "43:30" cai como h=43, m=None pelo regex (o primeiro grupo casa primeiro),
    # entao quando so tem UM ':' o numero da frente e' MINUTO, nao hora.
    if mi is None:
        h, mi = None, h
    total = float(s.replace(",", "."))
    total += int(mi or 0) * 60
    total += int(h or 0) * 3600
    return total


def format_time(seconds, decimals=3):
    """Segundos -> "MM:SS.mmm", ou "HH:MM:SS.mmm" quando passa de uma hora.

    Formato escolhido pra bater com o que o Resolve mostra no visor de tempo,
    menos os frames (que aparecem separados via seconds_to_frame).
    """
    if seconds is None:
        return ""
    neg = seconds < 0
    seconds = abs(float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    # sem decimais o campo dos segundos tem 2 digitos ("05"), nao 3 - com
    # 3+decimals sairia "05:000" no lugar de "05:00"
    w = 3 + decimals if decimals else 2
    if h:
        out = f"{h:d}:{m:02d}:{s:0{w}.{decimals}f}"
    else:
        out = f"{m:02d}:{s:0{w}.{decimals}f}"
    return ("-" + out) if neg else out


def seconds_to_frame(seconds, fps=DEFAULT_FPS):
    """MESMA conta do SpeakerSwitch.py (`int(round(t["start"] * fps))`).

    Tem que ser identica, senao o editor mostra um numero de frame e o Resolve
    usa outro - o erro apareceria so no corte final, que e' o pior lugar.
    """
    return int(round(float(seconds) * fps))


def frame_to_seconds(frame, fps=DEFAULT_FPS):
    return float(frame) / fps


def snap_to_frame(seconds, fps=DEFAULT_FPS):
    """Arredonda pro instante exato de um frame.

    Serve pra 'o que voce ve e' o que o Resolve recebe': sem snap, dois turnos
    com end/start diferentes por 3ms viram o MESMO frame la na frente, e o
    editor mostraria um buraco que nao existe (ou esconderia um que existe).
    """
    return seconds_to_frame(seconds, fps) / fps


def format_timecode(seconds, fps=DEFAULT_FPS):
    """"HH:MM:SS:FF" - o timecode do jeito que o Resolve mostra na timeline."""
    total_frames = seconds_to_frame(seconds, fps)
    fps_i = int(round(fps))
    f = total_frames % fps_i
    total_s = total_frames // fps_i
    return f"{total_s // 3600:02d}:{(total_s % 3600) // 60:02d}:{total_s % 60:02d}:{f:02d}"


def span_frames(start, end, fps=DEFAULT_FPS):
    """Quantos frames esse turno vira no Resolve (pode ser 0 ou negativo)."""
    return seconds_to_frame(end, fps) - seconds_to_frame(start, fps)


def is_too_short(start, end, fps=DEFAULT_FPS, min_frames=MIN_SPAN_FRAMES):
    """True se o Resolve vai recusar/engolir esse trecho.

    Nao e' frescura: no SpeakerSwitch, span abaixo do minimo nao vira clipe -
    ele e' absorvido pelo vizinho (build_spans), entao o turno simplesmente
    SOME do corte final sem aviso nenhum.
    """
    return span_frames(start, end, fps) < min_frames


def min_span_seconds(fps=DEFAULT_FPS, min_frames=MIN_SPAN_FRAMES):
    return min_frames / fps


def humanize_duration(seconds):
    """Duracao curta legivel: "1.234s" ou "12.3s" ou "2:05.4"."""
    seconds = float(seconds)
    if seconds < 10:
        return f"{seconds:.3f}s"
    if seconds < 60:
        return f"{seconds:.2f}s"
    return format_time(seconds, decimals=1)


def nearest_frame_delta(seconds, fps=DEFAULT_FPS):
    """Quanto esse tempo esta longe do frame mais proximo, em ms.

    Usado pra avisar 'esse valor nao cai num frame' sem forcar o snap.
    """
    return abs(seconds - snap_to_frame(seconds, fps)) * 1000.0


__all__ = [
    "DEFAULT_FPS", "MIN_SPAN_FRAMES", "parse_time", "format_time",
    "seconds_to_frame", "frame_to_seconds", "snap_to_frame", "format_timecode",
    "span_frames", "is_too_short", "min_span_seconds", "humanize_duration",
    "nearest_frame_delta",
]


if __name__ == "__main__":
    # sanity check rapido: python timecode.py
    casos = ["2610", "43:30", "43:30.5", "1:03:30.100", "43:30,5", "0:00.016"]
    for c in casos:
        s = parse_time(c)
        print(f"{c:>14s} -> {s:12.4f}s  {format_time(s)}  "
              f"tc={format_timecode(s)}  frame={seconds_to_frame(s)}")
    assert parse_time("43:30") == 2610.0
    assert parse_time("2610") == 2610.0
    assert parse_time("1:03:30.100") == 3810.1
    assert format_time(2610.5) == "43:30.500"
    assert format_time(3810.1) == "1:03:30.100"
    assert seconds_to_frame(2610.0) == 156600
    assert span_frames(2610.0, 2610.05) == 3
    assert is_too_short(2610.0, 2610.01)          # 0.6 frame
    assert not is_too_short(2610.0, 2610.05)      # 3 frames
    print("\nOK - todas as assercoes passaram")
