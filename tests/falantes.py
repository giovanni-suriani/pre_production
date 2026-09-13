r"""Testes do falante da legenda - rodam offline, sem servidor e sem Resolve.

    python tests\falantes.py

Cobrem os dois defeitos que deixaram o `legenda_por_track.lua` do corte
`rank_surpresa` (DeuMerda) com TODAS as legendas numa track so, sem nenhum
erro no caminho:

1. base de tempo decidida pelo MENOR tempo do arquivo - uma legenda que comeca
   2,3 s antes do corte fazia a transcricao ficar em absoluto enquanto os
   turnos viravam relativos. Sobreposicao zero, todo falante `None`.
2. lista de falantes vinda do estilos.json (o episodio anterior) em vez do
   `track_map` do corte - quem nao estava na lista caia na track 1 calado.

Os dois erram em silencio: a legenda sai, entra no Resolve e so' na tela se ve
que todo mundo ficou na mesma track.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from giautosubs import montar, para_relativo                # noqa: E402

falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)
        print(f"  FAILED: {msg}")


# ------------------------------------------------------------- base de tempo
print("base de tempo")
INICIO = 2055.901

# o caso real: 281 legendas dentro do corte e UMA comecando antes da borda
absolutos = [{"start": 2053.59, "end": 2061.03, "text": "borda"}]
absolutos += [{"start": INICIO + i, "end": INICIO + i + 0.5, "text": str(i)}
              for i in range(1, 60)]
rel, off = para_relativo(absolutos, INICIO)
checa(off == INICIO, f"arquivo absoluto e' convertido mesmo com um item antes "
                     f"da borda (offset {off})")
checa(rel[1]["start"] == 1.0, f"o primeiro item de dentro cai em 1,0s, caiu em "
                              f"{rel[1]['start']}")

relativos = [{"start": i, "end": i + 0.5, "text": str(i)} for i in range(60)]
intocado, off2 = para_relativo(relativos, INICIO)
checa(off2 == 0.0, "arquivo ja relativo nao e' convertido de novo")
checa(intocado[0]["start"] == 0, "e continua comecando em zero")


# ----------------------------------------------------------------- falantes
print("falante por track")


def _corte(pasta, **extra):
    c = {"schema": 1, "name": "corte_teste", "project": "P", "fps": 30.0,
         "start": INICIO, "end": INICIO + 10, "time_base": "absolute",
         "transcript": "fala.json", "last_turns_file": "turnos.json"}
    c.update(extra)
    with open(os.path.join(pasta, "corte.json"), "w", encoding="utf-8") as fh:
        json.dump(c, fh)


def _escreve(pasta, nome, dados):
    with open(os.path.join(pasta, nome), "w", encoding="utf-8") as fh:
        json.dump(dados, fh)


RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(RAIZ, "estilos.json"), encoding="utf-8-sig") as fh:
    CFG = json.load(fh)
ESTILO = CFG.get("padrao") or "capcut_bolha"

with tempfile.TemporaryDirectory() as pasta:
    # Heitor fala no comeco, Pedro no fim - os dois em tempo ABSOLUTO, como
    # tudo neste projeto
    _corte(pasta, track_map={"Heitor": 1, "Pedro": 3, "cut": 4},
           off_camera=["no_name"])
    _escreve(pasta, "fala.json", [
        {"start": INICIO + 0.0, "end": INICIO + 2.0, "text": "oi"},
        {"start": INICIO + 5.0, "end": INICIO + 7.0, "text": "tudo bem"},
    ])
    _escreve(pasta, "turnos.json", [
        {"start": INICIO + 0.0, "end": INICIO + 3.0, "name": "Heitor"},
        {"start": INICIO + 4.0, "end": INICIO + 9.0, "name": "Pedro"},
    ])

    doc, stats = montar(pasta, CFG, ESTILO, tela_dividida=True)

    nomes = {s["nome"]: s["track"] for s in doc["speakers"]}
    checa(nomes == {"Heitor": 1, "Pedro": 3},
          f"os falantes saem do track_map do corte, sairam {nomes}")
    checa("cut" not in nomes, "`cut` nao e' falante - e' trecho jogado fora")
    checa(doc["track_unica"] is False, "tela dividida = uma track por falante")

    ordem = {s["nome"]: i + 1 for i, s in enumerate(doc["speakers"])}
    ids = [s["speaker_id"] for s in doc["segments"]]
    checa(all(i != 0 for i in ids),
          f"nenhuma legenda fica sem falante, ficaram {ids.count(0)}")
    checa(ids[0] == ordem["Heitor"], "a primeira legenda e' do Heitor")
    checa(ids[-1] == ordem["Pedro"], "a ultima e' do Pedro")
    checa(stats["contagem"].get(None) is None,
          f"a contagem por falante nao tem None: {stats['contagem']}")

with tempfile.TemporaryDirectory() as pasta:
    # corte SEM track_map (os antigos): vale a lista global do estilos.json
    _corte(pasta)
    _escreve(pasta, "fala.json",
             [{"start": INICIO, "end": INICIO + 1.0, "text": "oi"}])
    _escreve(pasta, "turnos.json",
             [{"start": INICIO, "end": INICIO + 1.0, "name": "Heitor"}])
    doc, _ = montar(pasta, CFG, ESTILO, tela_dividida=True)
    nomes = {s["nome"] for s in doc["speakers"]}
    checa(nomes == set(CFG.get("falantes") or {}),
          f"sem track_map, a lista global continua valendo ({nomes})")


print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    raise SystemExit(1)
print("ALL OK")
