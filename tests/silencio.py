r"""Vazio (ninguem falando) virando turno `no_name`.

    .venv\Scripts\python.exe tests\silencio.py

Nao precisa de Resolve nem de servidor. Cobre o `turns.fill_gaps()`: o buraco
no meio, a cabeca, a cauda, o limiar que deixa a respiracao passar, e a regra
que protege transcricao (sem rotulo, nao mexe).
"""
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src")
sys.path.insert(0, RAIZ)
import turns as T  # noqa: E402

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


def grava(d, nome, itens):
    p = os.path.join(d, nome)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(itens, f)
    return p


def le(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


tmp = tempfile.mkdtemp(prefix="silencio_")
try:
    print("\n1. o buraco no meio vira no_name")
    # corte de 100s a 120s; fala 100-105, buraco de 5s, fala 110-120
    p = grava(tmp, "a.json", [{"start": 100.0, "end": 105.0, "name": "Ana"},
                              {"start": 110.0, "end": 120.0, "name": "Bia"}])
    n = T.fill_gaps(p, 100.0, 120.0, fps=30.0, minimo=0.5)
    itens = le(p)
    check(n == 1, f"1 vazio criado (veio {n})")
    check(len(itens) == 3, "o arquivo tem 3 turnos agora")
    check(itens[1] == {"start": 105.0, "end": 110.0, "name": "no_name"},
          "o buraco 105-110 virou no_name, no lugar certo da lista")

    print("\n2. cabeca e cauda tambem sao vazios")
    p = grava(tmp, "b.json", [{"start": 105.0, "end": 110.0, "name": "Ana"}])
    n = T.fill_gaps(p, 100.0, 120.0, fps=30.0, minimo=0.5)
    itens = le(p)
    check(n == 2, f"2 vazios (cabeca e cauda) (veio {n})")
    check(itens[0]["start"] == 100.0 and itens[0]["end"] == 105.0,
          "cabeca: do inicio do corte ate a primeira fala")
    check(itens[-1]["start"] == 110.0 and itens[-1]["end"] == 120.0,
          "cauda: da ultima fala ate o fim do corte")
    check(all(x["name"] == "no_name" for x in (itens[0], itens[-1])),
          "as duas pontas com o rotulo de silencio")

    print("\n3. o limiar deixa a respiracao passar")
    p = grava(tmp, "c.json", [{"start": 100.0, "end": 105.0, "name": "Ana"},
                              {"start": 105.3, "end": 110.0, "name": "Bia"}])
    n = T.fill_gaps(p, 100.0, 110.0, fps=30.0, minimo=0.5)
    check(n == 0, "buraco de 0,3s nao vira turno (< 0,5s)")
    check(len(le(p)) == 2, "e o arquivo continua com 2 turnos")

    print("\n4. sobreposicao nao inventa vazio")
    # o segundo comeca ANTES do primeiro terminar - o cursor nao pode voltar
    p = grava(tmp, "d.json", [{"start": 100.0, "end": 110.0, "name": "Ana"},
                              {"start": 105.0, "end": 108.0, "name": "Bia"}])
    n = T.fill_gaps(p, 100.0, 110.0, fps=30.0, minimo=0.5)
    check(n == 0, "turno dentro do outro nao vira vazio depois dele")

    print("\n5. transcricao (sem rotulo) nao e' tocada")
    p = grava(tmp, "e.json", [{"start": 100.0, "end": 105.0, "text": "oi"},
                              {"start": 110.0, "end": 120.0, "text": "tudo bem"}])
    antes = le(p)
    n = T.fill_gaps(p, 100.0, 120.0, fps=30.0, minimo=0.5)
    check(n == 0, "sem chave de rotulo, devolve 0")
    check(le(p) == antes, "e o arquivo continua byte a byte o mesmo")

    print("\n6. os tempos saem encaixados no frame")
    p = grava(tmp, "f.json", [{"start": 100.01, "end": 105.017, "name": "Ana"},
                              {"start": 110.004, "end": 120.0, "name": "Bia"}])
    T.fill_gaps(p, 100.0, 120.0, fps=30.0, minimo=0.5)
    vazio = [x for x in le(p) if x["name"] == "no_name"][0]
    # tolerancia em MILESIMO de frame: o arquivo grava com round(_, 5), igual
    # ao shift_file, entao 105.03333 vale 3150.9999 frames e nao 3151 cravado
    check(abs(vazio["start"] * 30 - round(vazio["start"] * 30)) < 1e-3
          and abs(vazio["end"] * 30 - round(vazio["end"] * 30)) < 1e-3,
          f"o vazio ({vazio['start']} -> {vazio['end']}) cai em frame inteiro")

    print("\n7. a chave do rotulo do arquivo e' respeitada")
    p = grava(tmp, "g.json", [{"start": 100.0, "end": 105.0, "speaker": "SPEAKER_00"},
                              {"start": 110.0, "end": 120.0, "speaker": "SPEAKER_01"}])
    T.fill_gaps(p, 100.0, 120.0, fps=30.0, minimo=0.5)
    vazio = [x for x in le(p) if "speaker" in x and x["speaker"] == "no_name"]
    check(len(vazio) == 1, "arquivo com `speaker` recebe o vazio em `speaker`, nao em `name`")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{ok_count} ok, {fail_count} falharam")
sys.exit(1 if fail_count else 0)
