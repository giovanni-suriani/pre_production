r"""Legendas: escrever SRT para o Resolve e ler SRT de volta.

As duas metades ficam juntas de proposito - o formato e' um so, e o parser
existe justamente para poder IMPORTAR uma legenda como transcricao no editor.

A base de tempo, de novo
------------------------
Este e' o ponto onde a legenda erra silenciosamente. Os turnos deste projeto
sao gravados em tempo ABSOLUTO da midia (2610s = 43:30), mas a timeline que o
`SpeakerSwitch.py` cria no Resolve **comeca no frame 0**. Uma legenda exportada
em tempo absoluto entra no Resolve 43 minutos adiantada - e como o Resolve
aceita e mostra o texto normalmente, o erro so aparece quando alguem repara que
nada bate com a fala.

Por isso o default aqui e' `base="timeline"`: subtrai o inicio do corte e a
legenda cai em cima da timeline nova. `base="media"` existe para quem for
colocar a legenda sobre o episodio inteiro.

Os tempos saem encaixados no frame (mesma conta do `timecode.py`), entao o que
o editor mostra e' o que o Resolve recebe.
"""

import re

import timecode as tc

# 00:00:01,000 --> 00:00:04,000   (a virgula e' do SRT; o VTT usa ponto)
_TIME = r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
_CUE = re.compile(rf"^\s*{_TIME}\s*-->\s*{_TIME}", re.M)


def _stamp(seconds):
    """Segundos -> HH:MM:SS,mmm. Negativo vira zero: uma legenda antes do
    inicio da timeline o Resolve simplesmente nao mostra."""
    s = max(0.0, float(seconds))
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def to_srt(segments, offset=0.0, fps=None, min_gap=0.001):
    """Segmentos {start,end,text} -> texto SRT.

    `offset` e' SOMADO (use `-inicio_do_corte` para a base da timeline).
    Segmentos que caem inteiros antes do zero sao descartados; os que so
    comecam antes sao aparados.

    Legendas coladas/sobrepostas sao separadas por `min_gap`: o Resolve aceita
    sobreposicao, mas ela vira duas legendas na tela ao mesmo tempo.
    """
    # com fps, o afastamento minimo e' UM FRAME: somar 1 ms tiraria a legenda
    # do frame em que ela acabou de ser encaixada
    gap = (1.0 / fps) if fps else min_gap
    out, n = [], 0
    prev_end = None
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg["start"]) + offset
        end = float(seg["end"]) + offset
        if end <= 0:
            continue
        start = max(0.0, start)
        if fps:
            start, end = tc.snap_to_frame(start, fps), tc.snap_to_frame(end, fps)
        if prev_end is not None and start < prev_end:
            start = prev_end + gap
        if end <= start:
            end = start + gap
        prev_end = end
        n += 1
        out.append(f"{n}\n{_stamp(start)} --> {_stamp(end)}\n{text}\n")
    return "\n".join(out)


def parse_srt(text):
    """SRT (ou VTT simples) -> [{start, end, text}] em segundos.

    Tolerante de proposito: numero da legenda opcional, `WEBVTT` no topo
    ignorado, quebra de linha dentro do texto virando espaco. Uma legenda que
    veio de outra ferramenta nao deveria ser recusada por causa de formatacao.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues = list(_CUE.finditer(text))
    segs = []
    for i, m in enumerate(cues):
        def _s(g):
            return (int(m.group(g)) * 3600 + int(m.group(g + 1)) * 60
                    + int(m.group(g + 2)) + int(m.group(g + 3).ljust(3, "0")) / 1000)
        body_start = m.end()
        body_end = cues[i + 1].start() if i + 1 < len(cues) else len(text)
        body = text[body_start:body_end].strip()
        # a ultima linha antes do proximo cue costuma ser o numero dele
        lines = [ln for ln in body.split("\n") if ln.strip()]
        if lines and lines[-1].strip().isdigit() and i + 1 < len(cues):
            lines = lines[:-1]
        body = " ".join(ln.strip() for ln in lines).strip()
        if body:
            segs.append({"start": _s(1), "end": _s(5), "text": body})
    return segs


def with_speakers(segments, turns, label_key="name", sep=": "):
    """Poe o nome de quem fala na frente de cada legenda.

    O Whisper transcreve mas nao diariza; os turnos sabem quem fala mas nao o
    que foi dito. O falante de cada legenda e' quem cobre mais tempo dela -
    nao quem comeca junto, porque legenda que atravessa uma troca de falante
    ficaria com o nome errado por causa de 100 ms.
    """
    if not turns:
        return segments
    out = []
    for seg in segments:
        s, e = float(seg["start"]), float(seg["end"])
        best, best_ov = None, 0.0
        for t in turns:
            ov = min(e, float(t["end"])) - max(s, float(t["start"]))
            if ov > best_ov:
                best, best_ov = t.get(label_key), ov
        text = (seg.get("text") or "").strip()
        out.append({**seg, "text": f"{best}{sep}{text}" if best else text})
    return out
