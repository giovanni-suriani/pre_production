"""Leitura, escrita e normalizacao dos turns*.json.

Herdado do turnsEditor (mesmo schema flexivel, mesma analise de problemas) e
com o que este projeto acrescenta: **normalizar a base de tempo**.

O problema que isto resolve
---------------------------
Nos arquivos antigos deste pipeline circulavam DUAS bases de tempo ao mesmo
tempo, e nada no arquivo dizia qual era qual: `turnsPyannote4.json` comeca em
1.13s (relativo ao corte de 43:30) e `turnsGemini_3.5_Chunks.json` comeca em
2610s (absoluto, do inicio do episodio). Sao o mesmo conteudo em eixos
diferentes. Descobrir isso custou caro.

Aqui a ambiguidade nao chega a existir: quem roda a diarizacao num wav fatiado
sabe exatamente quanto vale o offset (e' o inicio do corte), entao a saida crua
fica gravada como `*.raw.json` e o arquivo canonico e' escrito **sempre em
tempo absoluto da midia-fonte** - que e' a unidade que o proprio
SpeakerSwitch.py documenta para RANGE_START/RANGE_END ("segundos absolutos na
midia-fonte, mesma unidade que os start/end do json de diarizacao").

Uma base so, escrita no manifesto, derivada em vez de adivinhada.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import timecode as tc

LABEL_KEYS = ("name", "speaker", "label")
TIME_KEYS = ("start", "end")


class TurnsError(ValueError):
    pass


def detect_label_key(items):
    """Qual chave carrega o rotulo do falante NESTE arquivo.

    Nao da pra fixar em "name": o 1_diarize.py escreve "speaker", o
    3c_diarize_gemini_chunks.py escreve "name" e o turnsWhisper nao tem rotulo
    nenhum (so "text").
    """
    present = set()
    for it in items:
        if isinstance(it, dict):
            present |= set(it)
    for k in LABEL_KEYS:
        if k in present:
            return k
    return None


def read_raw(path):
    # utf-8-sig: json gerado por outra ferramenta no Windows pode vir com BOM
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise TurnsError(f"{Path(path).name}: esperava uma lista de turnos, "
                         f"veio {type(raw).__name__}")
    return raw


def is_turns_file(raw):
    return (isinstance(raw, list) and raw
            and all(isinstance(x, dict) and "start" in x and "end" in x
                    for x in raw))


def crop_absolute(src, start, end):
    """Recorta os turnos de `src` (ja em tempo absoluto) para [start, end).

    So filtra por sobreposicao - nao corta uma fala no meio nem realinha
    `words`, porque texto nao e' audio: nao ha keyframe a respeitar aqui, so'
    o trecho que interessa. Pensado pra reaproveitar `entire_transcribe.json`
    (a transcricao do episodio inteiro, ja absoluta) num corte novo, sem rodar
    o Whisper de novo - os dois lados ja compartilham a mesma base de tempo,
    entao nao ha offset pra somar.
    """
    raw = read_raw(src)
    return [dict(it) for it in raw
            if float(it["start"]) < end and float(it["end"]) > start]


def load(path):
    """Normaliza pro formato do frontend, preservando chaves desconhecidas.

    `extra` guarda tudo que nao e' start/end/rotulo para que salvar devolva o
    arquivo com a mesma forma que entrou - inclusive campos que este editor nao
    sabe o que sao (`text`, `title`, `talk_start`...).
    """
    path = Path(path)
    raw = read_raw(path)
    label_key = detect_label_key(raw)
    turns, extra_keys = [], []
    for i, it in enumerate(raw):
        if not isinstance(it, dict):
            raise TurnsError(f"{path.name}: item #{i} nao e' um objeto")
        if "start" not in it or "end" not in it:
            raise TurnsError(f"{path.name}: item #{i} sem start/end")
        extra = {k: v for k, v in it.items()
                 if k not in TIME_KEYS and k != label_key}
        for k in extra:
            if k not in extra_keys:
                extra_keys.append(k)
        turns.append({"id": i, "start": float(it["start"]),
                      "end": float(it["end"]),
                      "label": it.get(label_key) if label_key else None,
                      "extra": extra})
    return {"label_key": label_key, "extra_keys": extra_keys, "turns": turns}


def span(turns):
    if not turns:
        return None
    return [min(t["start"] for t in turns), max(t["end"] for t in turns)]


def labels_of(raw):
    k = detect_label_key(raw)
    if not k:
        return []
    return sorted({str(x[k]) for x in raw if x.get(k) is not None})


def analyze(turns, fps, min_frames):
    """Problemas que so apareceriam la no Resolve, ditos aqui.

    Nada disso bloqueia salvar: buraco as vezes e' de proposito. Mas "curto"
    e' o que mais dói - o build_spans() do SpeakerSwitch absorve o turno no
    vizinho e ele SOME do corte final sem aviso nenhum.
    """
    issues = []
    ordered = sorted(range(len(turns)), key=lambda i: turns[i]["start"])
    for i in ordered:
        t = turns[i]
        if t["end"] <= t["start"]:
            issues.append({"turn": t["id"], "kind": "invalid",
                           "msg": "end <= start"})
        elif tc.is_too_short(t["start"], t["end"], fps, min_frames):
            n = tc.span_frames(t["start"], t["end"], fps)
            issues.append({"turn": t["id"], "kind": "short",
                           "msg": f"vira {n} frame(s) - o Resolve descarta "
                                  f"(minimo {min_frames}); o vizinho engole"})
    for a, b in zip(ordered, ordered[1:]):
        ta, tb = turns[a], turns[b]
        fa_end = tc.seconds_to_frame(ta["end"], fps)
        fb_start = tc.seconds_to_frame(tb["start"], fps)
        if fb_start < fa_end:
            issues.append({"turn": tb["id"], "kind": "overlap",
                           "msg": f"sobrepoe o anterior em "
                                  f"{fa_end - fb_start} frame(s)"})
        elif fb_start > fa_end:
            gap = tb["start"] - ta["end"]
            issues.append({"turn": tb["id"], "kind": "gap",
                           "msg": f"buraco de {tc.humanize_duration(gap)} "
                                  f"({fb_start - fa_end} frames) antes deste"})
    return issues


def summarize(path, fps, min_frames):
    """Resumo barato pra listar arquivos numa tela sem carregar tudo."""
    raw = read_raw(path)
    if not is_turns_file(raw):
        return None
    key = detect_label_key(raw)
    turns = [{"id": i, "start": float(x["start"]), "end": float(x["end"])}
             for i, x in enumerate(raw)]
    issues = analyze(turns, fps, min_frames)
    counts = {}
    for k in ("short", "overlap", "gap", "invalid"):
        n = sum(1 for i in issues if i["kind"] == k)
        if n:
            counts[k] = n
    return {"count": len(raw), "label_key": key, "labels": labels_of(raw),
            "span": span(turns), "issues": counts,
            "keys": sorted({k for x in raw for k in x})}


# ------------------------------------------------------------- escrita

def write(dest, items, backup=True):
    """Escrita atomica com .bak datado.

    Sobrescrever um json de diarizacao que levou 20 min de GPU ou de cota de
    API merece rede de seguranca; e o `.tmp` + replace garante que uma queda no
    meio nao deixe um json pela metade (que o SpeakerSwitch leria como erro de
    parse muito depois, dentro do Resolve).
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    bak = None
    if dest.exists() and backup:
        bak = dest.with_suffix(f".{datetime.now():%Y%m%d-%H%M%S}.bak.json")
        shutil.copy2(dest, bak)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(dest)
    return bak


def shift_file(src, dest, offset, label_map=None, fps=None):
    """Le `src`, soma `offset` em todo start/end e grava em `dest`.

    E' a conversao relativo -> absoluto que fecha o buraco descrito no topo
    deste arquivo. `label_map` renomeia rotulos no mesmo passo (SPEAKER_00 ->
    Giovanni), porque o SpeakerSwitch mapeia track por NOME.

    Com `fps`, os tempos ja saem encaixados no frame: assim o que o editor
    mostra e' exatamente o que o Resolve recebe, sem um erro de 3 ms virando
    um frame de diferenca la na frente.
    """
    raw = read_raw(src)
    key = detect_label_key(raw)
    out = []
    for it in raw:
        item = dict(it)
        s = float(it["start"]) + offset
        e = float(it["end"]) + offset
        if fps:
            s, e = tc.snap_to_frame(s, fps), tc.snap_to_frame(e, fps)
        item["start"] = round(s, 5)
        item["end"] = round(e, 5)
        # `words` (o tempo por palavra que o Whisper devolve com --words) esta
        # na MESMA base do turno. Sem deslocar junto, o turno vira absoluto e
        # as palavras ficam relativas: o destaque do GiAutoSubs acenderia
        # contando do inicio do episodio, nao do corte. E como o `dict(it)`
        # copiava a lista inteira sem tocar nela, a inconsistencia atravessava
        # calada ate virar legenda errada na tela.
        if isinstance(it.get("words"), list):
            palavras = []
            for w in it["words"]:
                nw = dict(w)
                ws = float(w["start"]) + offset
                we = float(w["end"]) + offset
                if fps:
                    ws, we = tc.snap_to_frame(ws, fps), tc.snap_to_frame(we, fps)
                nw["start"], nw["end"] = round(ws, 5), round(we, 5)
                palavras.append(nw)
            item["words"] = palavras
        if label_map and key and item.get(key) in label_map:
            item[key] = label_map[item[key]]
        out.append(item)
    write(dest, out, backup=False)
    return len(out)


def fill_gaps(path, inicio, fim, fps=None, minimo=0.5, nome="no_name"):
    """Vazio de >= `minimo` segundos vira um turno `no_name`, in-place.

    Por que existe: onde ninguem fala o arquivo simplesmente NAO tem turno, e
    o vazio aparece em branco no editor. `no_name` ja e' o rotulo de "voz sem
    cara na tela" (fora de camera, cai na BASE_TRACK igual) - entao dizer
    "ninguem falando" com ele cobre o corte inteiro sem inventar conceito
    novo, e o editor passa a mostrar bloco em vez de buraco.

    Cobre tambem a cabeca (`inicio` -> primeiro turno) e a cauda (ultimo ->
    `fim`), que sao vazios como qualquer outro.

    So mexe em arquivo de DIARIZACAO: sem chave de rotulo (transcricao pura)
    devolve 0 sem tocar em nada - encher uma transcricao de turnos mudos
    quebraria a legenda.

    Consequencia que NAO e' bug: o "silencio: remover" do SpeakerSwitch acha o
    silencio pelo vazio ENTRE turnos. Preenchido, nao ha mais vazio - aqueles
    trechos viram clipe da BASE_TRACK em vez de sumir. Trocar de ideia e' so
    apagar os turnos `no_name` no editor.
    """
    raw = read_raw(path)
    key = detect_label_key(raw)
    if not key or not raw:
        return 0
    ordenados = sorted(raw, key=lambda x: float(x["start"]))
    out, cursor, criados = [], float(inicio), 0

    def _vazio(a, b):
        if fps:
            a, b = tc.snap_to_frame(a, fps), tc.snap_to_frame(b, fps)
        return {"start": round(a, 5), "end": round(b, 5), key: nome}

    for it in ordenados:
        s, e = float(it["start"]), float(it["end"])
        if s - cursor >= minimo:
            out.append(_vazio(cursor, s))
            criados += 1
        out.append(it)
        cursor = max(cursor, e)
    if float(fim) - cursor >= minimo:
        out.append(_vazio(cursor, float(fim)))
        criados += 1
    if criados:
        write(path, out, backup=False)
    return criados


def rename_labels(path, mapping, label_key="name"):
    """Renomeia rotulos in-place, com backup, e opcionalmente troca a chave.

    Renomear em massa e' o que falta entre "o diarizador cuspiu SPEAKER_01" e
    "o SpeakerSwitch quer 'Heitor' na chave 'name'". Da pra fazer turno a turno
    no editor, mas sao centenas.
    """
    raw = read_raw(path)
    key = detect_label_key(raw)
    if not key:
        raise TurnsError(f"{Path(path).name} nao tem rotulo de falante "
                         f"(nenhuma das chaves {LABEL_KEYS})")
    out = []
    changed = 0
    for it in raw:
        item = {k: v for k, v in it.items() if k != key}
        val = it.get(key)
        new = mapping.get(val, val)
        if new != val:
            changed += 1
        # a chave do rotulo passa a ser label_key ("name" e' o que o
        # SpeakerSwitch le), mantendo a ordem start/end/rotulo/resto
        ordered = {"start": item.pop("start"), "end": item.pop("end"),
                   label_key: new}
        ordered.update(item)
        out.append(ordered)
    bak = write(path, out, backup=True)
    return {"changed": changed, "backup": bak.name if bak else None,
            "label_key": label_key}
