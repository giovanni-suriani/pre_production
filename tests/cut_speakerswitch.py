r"""Os trechos marcados como "cut" saem do corte, sem deixar buraco.

    python tests\cut_speakerswitch.py

Nao precisa de Resolve: exercita `build_spans` direto e refaz, aqui, a mesma
conta de `rec` que o `main()` faz - a geometria e' toda decidida antes de
qualquer chamada de API.

Por que isto existe: um erro aqui nao aparece como excecao, aparece como um
frame preto ou um audio fora de sincronia no meio de um corte de 4 minutos -
so' visivel abrindo a timeline montada e olhando.
"""
import os
import sys

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "editor_proxy")
sys.path.insert(0, RAIZ)
import SpeakerSwitch as S  # noqa: E402

ok_count, fail_count = 0, 0
FPS = 60.0


def check(cond, msg):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  [ok] {msg}")
    else:
        fail_count += 1
        print(f"  [FALHOU] {msg}")
    return cond


def monta(turns, layers=(1, 2, 3), silencio="preencher", corta=True, range_b=600):
    """spans + `rec`, do mesmo jeito que o main(). Devolve (kept, descartados)."""
    S.SILENCE_MODE = silencio
    S.REMOVE_CUT = corta
    spans = S.build_spans(turns, FPS, {i: {} for i in layers}, range_b, 0, range_b)
    descartado, kept = 0, []
    for s in spans:
        if s.get("drop"):
            descartado += s["b"] - s["a"]
            continue
        s["rec"] = (s["a"] - 0) - descartado
        kept.append(s)
    return kept, descartado


def contiguo(kept):
    """Cada span comeca exatamente onde o anterior acabou, na timeline nova."""
    return all(kept[i]["rec"] + (kept[i]["b"] - kept[i]["a"]) == kept[i + 1]["rec"]
               for i in range(len(kept) - 1))


print("\n1. o trecho de cut some e o resto anda pra tras")
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "cut"},
    {"start": 2.0, "end": 3.0, "name": "Cupertino"},
    {"start": 3.0, "end": 4.0, "name": "cut"},
    {"start": 4.0, "end": 5.0, "name": "Heitor"},
], range_b=300)
check(len(kept) == 3, f"3 spans sobraram (veio {len(kept)})")
check(desc == 120, f"120 frames descartados (veio {desc})")
check(contiguo(kept), "sem buraco entre os spans que sobraram")
check(kept[-1]["rec"] + (kept[-1]["b"] - kept[-1]["a"]) == 180,
      "timeline nova com 180 frames (5s - 2s cortados)")
check([s["track"] for s in kept] == [1, 2, 3], "cada um foi pra sua track")

print("\n2. CUT_NAMES ganha do NAME_TO_TRACK (cortes antigos com 'cut': 4)")
antes = dict(S.NAME_TO_TRACK)
S.NAME_TO_TRACK = {"Giovanni": 1, "Cupertino": 2, "Heitor": 3, "cut": 4}
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "cut"},
    {"start": 2.0, "end": 3.0, "name": "Heitor"},
], layers=(1, 2, 3, 4), range_b=180)
check(desc == 60, f"o trecho saiu mesmo mandado pra V4 (descartado={desc})")
check(4 not in [s["track"] for s in kept], "nenhum span sobrou na V4")
S.NAME_TO_TRACK = antes

print("\n3. silencio de verdade ainda vira clipe da BASE_TRACK")
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    # 1s-2s: ninguem falando (nao e' cut - e' buraco pra FILL_GAPS tapar)
    {"start": 2.0, "end": 3.0, "name": "cut"},
    {"start": 3.0, "end": 4.0, "name": "Heitor"},
], range_b=240)
check(desc == 60, f"so' o cut foi descartado (descartado={desc})")
check(any(s["track"] == S.BASE_TRACK and s["a"] <= 60 and s["b"] >= 120
          for s in kept), "o silencio 1s-2s ficou coberto pela BASE_TRACK "
                          "(aqui, colado no span do Giovanni, que ja e' V1)")
check(contiguo(kept), "sem buraco depois do corte")

print("\n4. o cut nao gruda no preenchimento vizinho da mesma track")
# cut cai na BASE_TRACK quando o mapa manda pra uma track que nao existe no
# stack: sem o `drop` na comparacao do merge, ele viraria um clipe so' com o
# preenchimento colado nele - e o trecho cortado voltaria pra timeline.
antes = dict(S.NAME_TO_TRACK)
S.NAME_TO_TRACK = {"Giovanni": 1, "Heitor": 3, "cut": 9}
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "cut"},
    {"start": 2.0, "end": 3.0, "name": "Heitor"},
], range_b=180)
check(desc == 60, f"cut com track inexistente ainda e' descartado (={desc})")
check(sum(s["b"] - s["a"] for s in kept) == 120,
      "sobraram 120 frames, nao 180 (o cut nao voltou grudado)")
S.NAME_TO_TRACK = antes

print("\n5. a caixa desligada devolve o cut pra track do mapa")
antes = dict(S.NAME_TO_TRACK)
S.NAME_TO_TRACK = {"Giovanni": 1, "Heitor": 3, "cut": 4}
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "cut"},
    {"start": 2.0, "end": 3.0, "name": "Heitor"},
], layers=(1, 2, 3, 4), corta=False, range_b=180)
check(desc == 0, "nada descartado")
check(any(s["track"] == 4 for s in kept), "o trecho virou clipe na V4")
check(all(s["rec"] == s["a"] for s in kept), "sem ripple - da pra conferir "
                                             "contra o material original")
S.NAME_TO_TRACK = antes

print("\n6. silencio no modo 'remover'")
kept, desc = monta([
    # 0s-1s: silencio de cabeca. 2s-3s: silencio no meio. cauda ate 4s.
    {"start": 1.0, "end": 2.0, "name": "Giovanni"},
    {"start": 3.0, "end": 3.5, "name": "Heitor"},
], silencio="remover", range_b=240)
check(desc == 150, f"cabeca+meio+cauda removidos: 150 frames (veio {desc})")
check(len(kept) == 2, f"so' as duas falas sobraram (veio {len(kept)})")
check(kept[0]["rec"] == 0, "a timeline nova comeca na primeira fala")
check(contiguo(kept), "as falas ficaram coladas")

print("\n7. silencio no modo 'buraco' preserva o vazio")
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 2.0, "end": 3.0, "name": "Heitor"},
], silencio="buraco", range_b=180)
check(desc == 0, "nada descartado")
check(not contiguo(kept), "o buraco de 1s continua la (intencional)")
check(kept[1]["rec"] == 120, "e o Heitor nao andou pra tras")

print("\n8. 'buraco' + cut: o cut ripa, o buraco fica")
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "cut"},
    # 2s-3s: silencio de verdade, pra deixar como esta
    {"start": 3.0, "end": 4.0, "name": "Heitor"},
], silencio="buraco", range_b=240)
check(desc == 60, "so' o cut saiu")
check(kept[-1]["rec"] == 120,
      f"Heitor em 120 = 180 original - 60 do cut (veio {kept[-1]['rec']}), "
      f"com o buraco de 1s preservado")

print("\n9. sem nenhum cut, nada muda")
kept, desc = monta([
    {"start": 0.0, "end": 1.0, "name": "Giovanni"},
    {"start": 1.0, "end": 2.0, "name": "Heitor"},
], range_b=120)
check(desc == 0, "nada descartado")
check(all(s["rec"] == s["a"] for s in kept),
      "rec == posicao original (o caminho de audio em clipe unico continua valendo)")

print(f"\n{ok_count} ok, {fail_count} falharam")
sys.exit(1 if fail_count else 0)
