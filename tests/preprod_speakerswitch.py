r"""De onde o SpeakerSwitch tira "quem vai em qual track".

    python tests\preprod_speakerswitch.py

Nao precisa de Resolve nem de servidor. Cobre a leitura do `corte.json`, o
fallback pro `speaker_switch.json` antigo, e o caso que motivou tudo: uma pasta
de corte SEM configuracao nenhuma tem que PARAR, nao cair calado no
NAME_TO_TRACK fixo do topo do script - que e' de outro episodio.
"""
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "editor_proxy")
sys.path.insert(0, RAIZ)
import SpeakerSwitch as S  # noqa: E402

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


def corte_falso(base, nome, corte=None, ss=None):
    """Monta <base>\\projects\\P\\cortes\\<nome>\\turns\\turnsManual.json."""
    d = os.path.join(base, "projects", "P", "cortes", nome)
    os.makedirs(os.path.join(d, "turns"), exist_ok=True)
    with open(os.path.join(d, "turns", "turnsManual.json"), "w") as f:
        json.dump([], f)
    for arq, dados in (("corte.json", corte), ("speaker_switch.json", ss)):
        if dados is not None:
            with open(os.path.join(d, arq), "w", encoding="utf-8") as f:
                json.dump(dados, f)
    return os.path.join(d, "turns", "turnsManual.json")


tmp = tempfile.mkdtemp(prefix="ss_preprod_")
try:
    print("\n1. corte.json e' a fonte de verdade")
    tj = corte_falso(tmp, "com_corte", corte={
        "name": "com_corte", "project": "P", "start": 10.0, "end": 20.0,
        "origin_frame": 300, "last_turns_file": "turnsManual.json",
        "track_map": {"Nicolas": 1, "Cuper": 2, "Heitor": 3, "cut": 4},
        "off_camera": ["no_name"]})
    pp = S._read_preprod(S._pasta_do_corte(tj))
    check(pp and pp["fonte"] == "corte.json", "leu do corte.json")
    check(pp["name_to_track"] == {"Nicolas": 1, "Cuper": 2, "Heitor": 3, "cut": 4},
          "track_map -> name_to_track")
    check(pp["off_camera_names"] == ["no_name"], "off_camera -> off_camera_names")
    check(pp["origin_frame"] == 300, "origin_frame vem junto (pro aviso de origem)")
    check(os.path.isfile(pp["turns"] or ""), "last_turns_file vira caminho em turns\\")

    print("\n2. speaker_switch.json ainda funciona (cortes antigos)")
    tj = corte_falso(tmp, "so_ponte", ss={
        "projeto": "P", "corte": "so_ponte",
        "name_to_track": {"Ana": 1, "Bia": 2}, "off_camera_names": []})
    pp = S._read_preprod(S._pasta_do_corte(tj))
    check(pp and pp["fonte"].startswith("speaker_switch.json"),
          "caiu no fallback e diz de onde veio")
    check(pp["name_to_track"] == {"Ana": 1, "Bia": 2}, "mapa lido do arquivo antigo")

    print("\n3. corte.json ganha do speaker_switch.json quando os dois existem")
    tj = corte_falso(tmp, "os_dois",
                     corte={"name": "os_dois", "project": "P",
                            "track_map": {"Novo": 1}, "off_camera": []},
                     ss={"name_to_track": {"Velho": 1}, "off_camera_names": []})
    pp = S._read_preprod(S._pasta_do_corte(tj))
    check(pp["name_to_track"] == {"Novo": 1},
          "o mapa vem do corte.json, nao da copia velha")

    print("\n4. pasta de corte sem configuracao nenhuma")
    tj = corte_falso(tmp, "vazio")
    check(S._read_preprod(S._pasta_do_corte(tj)) is None, "_read_preprod devolve None")
    check(S._parece_corte(tj), "mas _parece_corte reconhece que e' um corte "
                               "(o main() para com [FALHOU] em vez de usar o mapa fixo)")

    print("\n5. fora do pre_production continua valendo o mapa fixo")
    antigo = os.path.join(tmp, "resultados", "EpisodioPiloto",
                          "turnsGeminiVideo4_shots.json")
    os.makedirs(os.path.dirname(antigo), exist_ok=True)
    open(antigo, "w").close()
    check(not S._parece_corte(antigo),
          "resultados\\<video>\\turns*.json nao e' corte - roda com o mapa do script")
    check(S._parece_corte(tj.replace("\\", "/")),
          "caminho com barra normal (o que o dialogo devolve) tambem e' reconhecido")

    print("\n6. o arquivo que o dialogo ja vem preenchido")
    novo = corte_falso(tmp, "recente", corte={
        "name": "recente", "project": "P", "track_map": {"A": 1},
        "off_camera": []})
    velho = corte_falso(tmp, "antigo", corte={
        "name": "antigo", "project": "P", "track_map": {"A": 1},
        "off_camera": []})
    os.utime(velho, (1, 1))                       # ano de 1970
    # o mesmo arquivo dentro da lixeira, e o MAIS NOVO de todos - se aparecesse,
    # o dialogo abriria sugerindo um corte que voce jogou fora
    lixo = os.path.join(tmp, "projects", "_lixeira", "P-20260101", "cortes",
                        "jogado_fora", "turns", _TM := "turnsManual.json")
    os.makedirs(os.path.dirname(lixo), exist_ok=True)
    with open(lixo, "w") as f:
        json.dump([], f)
    raiz_real = S._PREPROD_PROJECTS
    try:
        S._PREPROD_PROJECTS = os.path.join(tmp, "projects")
        achado = S._turns_mais_recente()
        check(achado == novo, "pega o turnsManual.json mais novo")
        check(achado != lixo, "o da _lixeira nao entra, mesmo sendo o mais novo")
        S._PREPROD_PROJECTS = os.path.join(tmp, "nao_existe")
        check(S._turns_mais_recente() is None,
              "sem nenhum corte devolve None (o script cai no default antigo)")
    finally:
        S._PREPROD_PROJECTS = raiz_real
    check(os.path.isfile(lixo), "(o corte da lixeira existe mesmo, so' e' ignorado)")

    print("\n7. os cortes de verdade que estao no disco")
    reais = [
        r"D:\CanalYtbe\BatataQuente\pre_production\projects\Episodio1\cortes"
        r"\Qual_mundo_de_video_game_viver\turns\turnsManual.json",
        r"D:\CanalYtbe\BatataQuente\pre_production\projects\EpisodioPiloto\cortes"
        r"\Corte_Mosquito\turns\turnsManual.json",
    ]
    for r in reais:
        if not os.path.isfile(r):
            print(f"  [--] {os.path.basename(os.path.dirname(os.path.dirname(r)))}"
                  f": nao esta no disco, pulando")
            continue
        pp = S._read_preprod(S._pasta_do_corte(r))
        check(pp is not None and bool(pp.get("name_to_track")),
              f"{pp and pp['corte']}: mapa {pp and pp['name_to_track']} "
              f"(de {pp and pp['fonte']})")

    print("\n8. editando a partir do trecho remuxado do corte")
    # corte em 2610.0s a 30 fps (frame 78300); o keyframe caiu 137 frames
    # antes (2605.4333s), entao o arquivo comeca no frame 78163 do episodio.
    tj = corte_falso(tmp, "com_video", corte={
        "name": "com_video", "project": "P", "start": 2610.0, "end": 2640.0,
        "fps": 30.0, "origin_frame": 78300, "last_turns_file": "turnsManual.json",
        "video": "com_video_137frames.mkv",
        "video_offset": 78163 / 30.0, "video_offset_frames": 137,
        "track_map": {"Ana": 1, "Bia": 2}})
    pp = S._read_preprod(S._pasta_do_corte(tj))
    check(pp["video"] == "com_video_137frames.mkv", "o nome do trecho vem junto")
    check(pp["video_origin_frame"] == 78163,
          "video_offset x fps = o frame do episodio onde o arquivo comeca")

    class MPI:                       # so' o GetName() importa aqui
        def __init__(self, nome): self.nome = nome
        def GetName(self): return self.nome

    # o clipe inteiro na timeline: GetLeftOffset = 0
    base, nome = S.media_base(pp, {"mpi": MPI("com_video_137frames.mkv")})
    check((base, nome) == (78163, "com_video_137frames.mkv"),
          "midia do corte -> soma o offset do arquivo")
    check(0 + base == 78163, "clip_origin = 78163 (e nao 0, que perderia todo turno)")
    # aparado a mao: GetLeftOffset = 137, e o absoluto bate com o planejado
    check(137 + base == 78300, "aparando os 137, o absoluto e' o origin_frame")

    # editando do episodio inteiro: nada muda, o GetLeftOffset ja e' absoluto
    check(S.media_base(pp, {"mpi": MPI("episodio.mkv")}) == (0, None),
          "midia diferente -> nao soma nada")
    check(S.media_base({"origin_frame": 78300}, {"mpi": MPI("x.mkv")}) == (0, None),
          "corte sem video remuxado -> nao soma nada")

    # o trecho renomeado: o nome nao casa, o offset nao e' somado - e o script
    # tem que dizer ISSO, nao "reposicione o clipe"
    os.makedirs(os.path.join(tmp, "projects", "P"), exist_ok=True)
    with open(os.path.join(tmp, "projects", "P", "project.json"), "w") as f:
        json.dump({"source_video": r"D:\Raw\episodio.mkv"}, f)
    pp2 = S._read_preprod(S._pasta_do_corte(tj))
    check(pp2["episodio"] == "episodio.mkv", "o nome do episodio vem do project.json")
    check(S.media_base(pp2, {"mpi": MPI("episodio.mkv")}) == (0, None),
          "o episodio inteiro nao vira aviso de renomeado")
    check(S.media_base(pp2, {"mpi": MPI("short_final.mkv")}) == (0, None),
          "midia estranha: nao soma (e avisa com os dois nomes, acima)")

    # o caso real: timeline de um corte, json de outro. Tem que acusar CORTE
    # TROCADO, nao mandar reposicionar o clipe.
    check(S.media_base(pp2, {"mpi": MPI("Eu_Duvido_13frames.mkv")}) == (0, None),
          "trecho de OUTRO corte: nao soma, e diz que os cortes sao diferentes")
    # e o corte sem remux proprio (video=None) tambem reconhece o trecho alheio
    pp3 = dict(pp2, video=None, video_origin_frame=None, corte="Qual_mundo")
    check(S.media_base(pp3, {"mpi": MPI("Eu_Duvido_13frames.mkv")}) == (0, None),
          "corte sem remux proprio ainda acusa o trecho de outro corte")

    class MPIRuim:
        def GetName(self): raise RuntimeError("bridge caiu")
    check(S.media_base(pp, {"mpi": MPIRuim()}) == (0, None),
          "GetName que explode nao derruba a rodada (assume episodio inteiro)")

    print("\n9. default do dialogo sai da timeline aberta, nao do relogio")
    projetos_reais = S._PREPROD_PROJECTS
    S._PREPROD_PROJECTS = os.path.join(tmp, "projects")
    try:
        # `com_video` foi criado acima com video="com_video_137frames.mkv"
        esperado = os.path.join(tmp, "projects", "P", "cortes", "com_video",
                                "turns", "turnsManual.json")
        check(S._turns_do_trecho("com_video_137frames.mkv") == esperado,
              "trecho na timeline -> turnsManual do corte que o gerou")
        check(S._turns_do_trecho("COM_VIDEO_137FRAMES.MKV") == esperado,
              "casa sem ligar pra caixa do nome")
        check(S._turns_do_trecho("episodio.mkv") is None,
              "episodio inteiro nao e' trecho: cai no default antigo")
        check(S._turns_do_trecho(None) is None,
              "sem midia legivel: cai no default antigo")
        # o caso real desta sessao: o trecho de um corte que nao esta em
        # nenhum corte.json (ou de outro projeto) nao pode chutar um corte
        check(S._turns_do_trecho("Eu_Duvido_13frames.mkv") is None,
              "trecho sem corte.json apontando pra ele: avisa e nao chuta")
        # corte que tem video mas ainda nao foi revisado no turnsEditor
        sem_revisao = os.path.join(tmp, "projects", "P", "cortes", "cru")
        os.makedirs(sem_revisao)
        with open(os.path.join(sem_revisao, "corte.json"), "w") as f:
            json.dump({"name": "cru", "video": "cru_9frames.mkv"}, f)
        check(S._turns_do_trecho("cru_9frames.mkv") is None,
              "corte sem turnsManual: avisa em vez de devolver caminho torto")
    finally:
        S._PREPROD_PROJECTS = projetos_reais

    # a olhada na timeline e' conforto, nunca motivo pra derrubar a rodada
    class ResolveRuim:
        def GetProjectManager(self): raise RuntimeError("bridge caiu")
    get_resolve_real = S.get_resolve
    S.get_resolve = lambda: ResolveRuim()
    try:
        check(S._midia_da_timeline() is None,
              "Resolve inacessivel: devolve None em vez de explodir")
    finally:
        S.get_resolve = get_resolve_real

    class TL:
        def __init__(self, tracks): self.tracks = tracks
        def GetTrackCount(self, _): return len(self.tracks)
        def GetItemListInTrack(self, _, idx):
            n = self.tracks[idx - 1]
            if n is None:
                return []
            class It:
                def GetMediaPoolItem(self): return MPI(n)
            return [It()]

    class ResolveFake:
        def __init__(self, tl): self.tl = tl
        def GetProjectManager(self): return self
        def GetCurrentProject(self): return self
        def GetCurrentTimeline(self): return self.tl

    S.get_resolve = lambda: ResolveFake(TL([None, "com_video_137frames.mkv"]))
    try:
        check(S._midia_da_timeline() == "com_video_137frames.mkv",
              "V1 vazia nao para a busca - pega a primeira track com clipe")
    finally:
        S.get_resolve = get_resolve_real
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{ok_count} ok, {fail_count} falharam")
sys.exit(1 if fail_count else 0)
