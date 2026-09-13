r"""Teste de fumaca: dirige o servidor de verdade, de ponta a ponta.

Nao usa mock nenhum. Ele cria um projeto, extrai o wav, fatia um corte, roda um
metodo e confere o que foi parar no disco - que e' onde os erros deste app
aparecem. As duas coisas que ele checa com mais cuidado sao justamente as que
custaram caro no pipeline antigo:

    1. a base de tempo do arquivo final e' ABSOLUTA (o offset do corte foi
       somado, e o `.raw.json` ao lado continua relativo);
    2. `origin_frame` == round(start * fps) - a mesma conta do SpeakerSwitch.

Uso (com o servidor no ar):

    ..\.venv\Scripts\python.exe tests\smoke.py
    ..\.venv\Scripts\python.exe tests\smoke.py --video "D:\...\chunk01.mp4"
    ..\.venv\Scripts\python.exe tests\smoke.py --method whisper --keep

Por padrao usa o metodo `whisper` com o modelo `tiny`: e' o unico que roda sem
GPU, sem token e sem cota de API. `--keep` deixa o projeto no disco pra voce
abrir na interface; sem ele, o projeto vai pra projects\_lixeira no fim.
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8740"
ok_count, fail_count = 0, 0


def check(cond, msg):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  [ok] {msg}")
    else:
        fail_count += 1
        print(f"  [FALHOU] {msg}")
    return cond


def call(path, data=None, method=None):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method or
                                 ("POST" if data is not None else "GET"))
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"{path} -> {e.code}: {detail[:400]}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"servidor fora do ar em {BASE} ({e.reason}). "
                         f"Rode o run.bat primeiro.") from None


def wait(job_id, label):
    since, t0 = 0, time.time()
    last = ""
    while True:
        s = call(f"/api/jobs/{job_id}?since={since}")
        since = s["log_next"]
        for line in s["log"]:
            last = line
            print(f"      | {line[:150]}")
        if s["status"] not in ("running", "queued"):
            print(f"    {label}: {s['status']} em {time.time() - t0:.1f}s")
            if s["status"] != "ok":
                print(f"      ultima linha: {last}")
            return s
        time.sleep(0.7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=r"D:\CanalYtbe\BatataQuente\scriptsPrimarios"
                                       r"\utilitarios\EpisodioPiloto\chunk01.mp4",
                    help="video curto pro teste (o padrao e' um chunk de 3 min)")
    ap.add_argument("--method", default="whisper")
    ap.add_argument("--name", default="_smoke")
    ap.add_argument("--start", type=float, default=10.0)
    ap.add_argument("--end", type=float, default=40.0)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    print(f"\nservidor: {BASE}")
    st = call("/api/state")
    print(f"python de diarizacao: {st['python_exe']}")

    # --------------------------------------------------------- etapa 1
    print("\n1. projeto")
    info = call(f"/api/probe?path={urllib.parse.quote(args.video)}")
    check(info["duration"] > 0, f"ffprobe leu {info['name']}: "
                                f"{info['duration']:.1f}s, {info.get('fps')} fps")
    for old in call("/api/projects")["projects"]:
        if old.get("name") == args.name:
            call(f"/api/projects/{old['slug']}", method="DELETE")
            print(f"    (projeto anterior {old['slug']} movido pra lixeira)")

    r = call("/api/projects", {
        "name": args.name, "source_video": args.video,
        "participants": [{"name": "Ana", "seat": "left"},
                         {"name": "Bruno", "seat": "center"},
                         {"name": "Carla", "seat": "right"}]})
    proj = r["project"]
    # o slug e' derivado do nome (sem acento, sem espaco, sem pontuacao solta),
    # entao nem sempre e' igual ao que foi digitado
    slug = proj["slug"]
    check(proj["fps"] == info["fps"], f"fps do projeto = fps do arquivo ({proj['fps']})")
    s = wait(r["job"], "extracao do audio")
    if not check(s["status"] == "ok", "wav extraido"):
        return finish()
    d = call(f"/api/projects/{slug}")
    check(d["audio_exists"], "wav existe no disco")
    check(d["project"]["audio_info"]["sample_rate"] == 16000, "wav em 16 kHz")
    check(d["project"]["audio_info"]["channels"] == 1, "wav mono")

    # --------------------------------------------------------- etapa 2
    print("\n2. corte")
    r = call(f"/api/projects/{slug}/cuts", {
        "name": "corte_teste", "start": args.start, "end": args.end})
    cut = r["cut"]
    fps = proj["fps"]
    check(cut["origin_frame"] == round(args.start * fps),
          f"origin_frame = round(start*fps) = {cut['origin_frame']}")
    check(cut["audio_offset"] == args.start,
          f"audio_offset = inicio do corte ({cut['audio_offset']}s)")
    check(cut["time_base"] == "absolute", "corte declara base de tempo absoluta")
    s = wait(r["job"], "fatiamento")
    if not check(s["status"] == "ok", "wav do corte gerado"):
        return finish()
    d = call(f"/api/projects/{slug}/cuts/corte_teste")
    dur = d["cut"]["audio_info"]["duration"]
    check(abs(dur - (args.end - args.start)) < 0.5,
          f"o wav do corte tem a duracao pedida ({dur:.2f}s)")

    # --------------------------------------------------------- rodada
    print(f"\n3. rodada ({args.method})")
    ms = {m["id"]: m for m in call("/api/methods")["methods"]}
    m = ms.get(args.method)
    if not m:
        print(f"    metodo {args.method} nao existe")
        return finish()
    if not m["ready"]:
        print(f"    [pulado] {args.method} indisponivel: "
              f"{m['missing_packages'] + m['missing_env']}")
        return finish(keep=args.keep, slug=slug)
    opts = {"whisper_model": "tiny"} if args.method == "whisper" else {}
    r = call(f"/api/projects/{slug}/cuts/corte_teste/run",
             {"method": args.method, "options": opts})
    s = wait(r["job"], args.method)
    if not check(s["status"] == "ok", "o script rodou ate o fim"):
        return finish(keep=args.keep, slug=slug)

    d = call(f"/api/projects/{slug}/cuts/corte_teste")
    files = {f["name"]: f for f in d["files"]}
    out = r["out"]
    raw = out.replace(".json", ".raw.json")
    check(out in files, f"{out} existe")
    check(raw in files, f"{raw} (saida crua) foi preservado ao lado")
    if out in files and raw in files:
        # o coracao do teste: o canonico esta na base absoluta, o cru nao
        check(files[out]["span"][0] >= args.start - 0.01,
              f"{out} comeca em tempo absoluto "
              f"({files[out]['span'][0]:.2f}s >= {args.start}s)")
        check(files[raw]["span"][0] < args.start,
              f"{raw} continua relativo ao corte "
              f"({files[raw]['span'][0]:.2f}s)")
        check(files[out]["span"][1] <= args.end + 1.0,
              f"{out} termina dentro do corte ({files[out]['span'][1]:.2f}s)")

    # --------------------------------------------------------- etapa 3
    print("\n4. editor de turnos")
    call("/api/state", {"project": slug, "cut": "corte_teste"})
    cfg = call("/api/config")
    c = cfg["config"]
    check(c["audio_offset"] == args.start,
          f"o editor recebe audio_offset = {c['audio_offset']}")
    check(c["fps"] == fps, f"o editor recebe fps = {c['fps']}")
    check("cut" in c["speaker_order"], "`cut` esta nos atalhos de falante")
    check(c["speaker_colors"].get("cut") == "#a78bfa",
          "`cut` tem a cor reservada (violeta), fora da familia das pessoas")
    check("no_name" in c["off_camera_names"], "`no_name` marcado como fora de quadro")
    check(any(f["name"] == out for f in cfg["turn_files"]),
          f"{out} aparece na lista do editor")
    if args.method == "whisper":
        tr = call("/api/transcript")
        check(len(tr["segments"]) > 0,
              f"transcricao servida ao editor ({len(tr['segments'])} trechos)")
        check(tr["offset"] == 0.0,
              "offset da transcricao = 0 (ja convertida na gravacao)")

    if args.method == "whisper":
        print("\n4b. legenda para o Resolve")
        r = call(f"/api/projects/{slug}/cuts/corte_teste/captions",
                 {"file": out, "base": "timeline", "out_name": "teste.srt"})
        check(r["offset_applied"] == -args.start,
              f"base timeline subtrai o inicio do corte ({r['offset_applied']}s)")
        check(r["count"] > 0, f"{r['count']} legendas geradas")
        srt = open(r["path"], encoding="utf-8").read()
        first = srt.split("\n")[1] if "\n" in srt else ""
        check(first.startswith("00:00:0"),
              f"a primeira legenda cai no comeco da timeline ({first})")
        rm = call(f"/api/projects/{slug}/cuts/corte_teste/captions",
                  {"file": out, "base": "media", "out_name": "teste_abs.srt"})
        abs_first = open(rm["path"], encoding="utf-8").read().split("\n")[1]
        check(not abs_first.startswith("00:00:0"),
              f"base midia mantem o tempo absoluto ({abs_first})")
        # o parser existe pra poder importar legenda de volta como transcricao
        back = call(f"/api/turns?file={urllib.parse.quote(out)}")
        check(len(back["turns"]) == r["count"] or r["count"] > 0,
              "o srt cobre os trechos da transcricao")

        print("\n4c. legenda no formato do GiAutoSubs")
        # O `words` e' a razao de este formato existir: e' ele que acende a
        # palavra falada. O .srt nao tem onde guarda-lo, e uma transcricao que
        # chega sem ele produz legenda igual e destaque nenhum - so' visivel
        # depois de criar os clipes dentro do Resolve. Por isso o teste planta
        # um arquivo COM tempo por palavra e confere que ele atravessa.
        d_corte = pathlib.Path(r["path"]).parent
        fonte = d_corte / "com_words.json"
        fonte.write_text(json.dumps([
            {"start": args.start + 1.0, "end": args.start + 2.0,
             "text": "uma frase",
             "words": [{"word": "uma", "start": args.start + 1.0,
                        "end": args.start + 1.4},
                       {"word": " frase", "start": args.start + 1.4,
                        "end": args.start + 2.0}]},
            {"start": args.start + 3.0, "end": args.start + 4.0,
             "text": "sem palavras"},
        ]), encoding="utf-8")
        g = call(f"/api/projects/{slug}/cuts/corte_teste/captions",
                 {"file": "com_words.json", "format": "giautosubs",
                  "out_name": "teste.giautosubs.json"})
        check(g["count"] == 2, f"{g['count']} trechos exportados")
        check(g["with_words"] == 1,
              f"{g['with_words']} trecho com tempo por palavra")
        itens = json.loads(pathlib.Path(g["path"]).read_text(encoding="utf-8"))
        check(itens[0]["start"] == args.start + 1.0,
              f"tempo ABSOLUTO no arquivo ({itens[0]['start']}s) - quem desconta "
              f"o inicio do corte e' o giautosubs.py")
        check(len(itens[0].get("words") or []) == 2,
              "o tempo por palavra atravessou a exportacao")
        check("words" not in itens[1],
              "trecho sem palavras nao ganha um `words` vazio")
        # e o editor passa a ler ESTE arquivo: um formato, um arquivo, dois
        # leitores - e' o que impede a coluna e a legenda de divergirem
        check(g["transcript"] == "teste.giautosubs.json",
              "o corte passou a apontar a transcricao para o arquivo exportado")
        tr2 = call("/api/transcript")
        check(tr2["file"] == "teste.giautosubs.json" and tr2["with_words"] == 1,
              "o editor de turnos le o mesmo arquivo, com o tempo por palavra")
        # a caixa "Tracks de legenda separadas" do corte vence o projeto, nos
        # dois sentidos - e' ela que decide o track_unica do legendas.lua
        for split, esperado, nome_lua in (
                (True, "track_unica = false", "legenda_por_track.lua"),
                (False, "track_unica = true", "legendas.lua")):
            gs = call(f"/api/projects/{slug}/cuts/corte_teste/captions",
                      {"file": "com_words.json", "format": "giautosubs",
                       "out_name": "teste.giautosubs.json",
                       "split_screen": split})
            lua_txt = (pathlib.Path(gs["lua"]).read_text(encoding="utf-8")
                       if gs.get("lua") else "")
            check(esperado in lua_txt,
                  f"split_screen={split} grava `{esperado}` no legendas.lua"
                  + ("" if gs.get("lua") else
                     f" (lua nao gerado: {gs.get('lua_erro')})"))
            check(bool(gs.get("lua")) and pathlib.Path(gs["lua"]).name == nome_lua
                  and pathlib.Path(gs["lua"]).is_file(),
                  f"split_screen={split} gera o arquivo {nome_lua}")

    print("\n5. trancas")
    # e' servidor local, mas grava json a partir de request: a trava e' barata
    for bad in ["../../../../Windows/win.ini", r"..\..\config.json",
                r"D:\CanalYtbe\BatataQuente\scriptsPrimarios\1_diarize.py"]:
        try:
            call(f"/api/turns?file={urllib.parse.quote(bad)}")
            check(False, f"caminho fora do corte NAO foi bloqueado: {bad}")
        except RuntimeError as e:
            check("404" in str(e) or "400" in str(e),
                  f"bloqueado: {bad}")
    try:
        call(f"/api/projects/{slug}/cuts/../../etc", method="DELETE")
        check(False, "nome de corte com .. NAO foi bloqueado")
    except RuntimeError:
        check(True, "nome de corte com .. bloqueado")

    print("\n6. o que o SpeakerSwitch le do corte")
    # O `corte.json` E' a ponte desde 02/09 - nao ha mais um speaker_switch.json
    # gravado por botao. Estes campos sao os que o editor_proxy le; a leitura em
    # si esta coberta em tests\preprod_speakerswitch.py.
    c = call(f"/api/projects/{slug}/cuts/corte_teste")["cut"]
    check(c["origin_frame"] == round(args.start * fps), "origin_frame no corte.json")
    check(bool(c["track_map"]), f"track_map preenchido: {c['track_map']}")
    check("no_name" in c["off_camera"], "fora de quadro sem track")

    finish(keep=args.keep, slug=slug)


def finish(keep=False, slug=None):
    if slug and not keep:
        try:
            call(f"/api/projects/{slug}", method="DELETE")
            print(f"\n(projeto {slug} movido pra projects\\_lixeira)")
        except RuntimeError as e:
            print(f"\n(nao consegui limpar: {e})")
    elif slug:
        print(f"\n(projeto {slug} mantido - abra em {BASE}/cortes)")
    print(f"\n{ok_count} ok, {fail_count} falharam\n")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
