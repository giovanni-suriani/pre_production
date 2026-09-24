r"""Roda a suite inteira com um comando.

    .venv\Scripts\python.exe tests\todos.py            # tudo (~65s)
    .venv\Scripts\python.exe tests\todos.py --rapido   # so' offline (~11s)

Por que existe
--------------
Os testes ja existiam e sao bons -- o que faltava era um comando. Com cinco
invocacoes diferentes, dois interpretadores e um servidor pra subir na mao,
rodar a suite era uma decisao; e teste que e' decisao nao roda na hora que
importa, que e' logo depois de mexer.

Duas coisas que este arquivo resolve, e que eram o atrito de verdade:

- **Sobe e derruba o servidor sozinho** quando o `smoke.py`/`ui.py` precisam.
  Se ja houver um de pe na 8740, usa o que esta la e NAO derruba no fim -- e'
  provavelmente o seu, com uma aba aberta.
- **Chama cada teste com o interpretador certo.** O `ui.py` e o
  `dialogo_speakerswitch.py` rodam no Python 3.12 do sistema (precisam de
  `websocket-client` e `tkinter`); o resto roda no venv do app.

Ordem: os offline primeiro, do mais rapido pro mais lento. Quebrou em 300ms,
voce sabe antes de o Chrome abrir.

`--rapido` pula os dois que precisam de servidor. Serve pro laco curto de
edicao; antes de commitar, rode a suite inteira.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# O console do Windows abre em cp1252 e a saida dos testes tem acento, seta
# (->) e texto de ffmpeg. Sem isto o runner morre com UnicodeEncodeError
# justamente ao imprimir a falha que voce precisa ler -- aconteceu na
# primeira rodada deste arquivo.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

RAIZ = Path(__file__).resolve().parent.parent
VENV = RAIZ / ".venv" / "Scripts" / "python.exe"
BASE = "http://127.0.0.1:8740"

# O Python 3.12 do sistema: tem websocket-client e tkinter, que o venv do app
# de proposito nao tem. Mesma deteccao do config.py, simplificada.
SISTEMA = Path(os.path.expandvars(
    r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"))

# O `ui.py` precisa de um projeto com um corte pronto pra exercitar a etapa 3;
# quem deixa um e' o `smoke.py --keep`. Sem isso ele ainda passa, mas com duas
# verificacoes a menos (47 em vez de 49) -- e um teste que passa cobrindo menos
# do que voce pensa e' pior do que um que falha. Por isso o smoke roda com
# --keep quando o ui esta na suite, e a limpeza fica com o runner, no fim.
SMOKE_NOME = "_smoke"

# (arquivo, interpretador, precisa_servidor)
SUITE = [
    ("camada3.py",               VENV,    False),
    ("quebra.py",                VENV,    False),
    ("falantes.py",              VENV,    False),
    ("cut_speakerswitch.py",     VENV,    False),
    ("preprod_speakerswitch.py", VENV,    False),
    ("dialogo_speakerswitch.py", SISTEMA, False),
    ("spin.py",                  VENV,    False),
    ("smoke.py",                 VENV,    True),
    ("ui.py",                    SISTEMA, True),
]


def no_ar():
    try:
        with socket.create_connection(("127.0.0.1", 8740), timeout=0.5):
            return True
    except OSError:
        return False


def sobe_servidor():
    """Sobe o app e espera responder. Devolve o processo, ou None se ja havia
    um de pe (nesse caso nao e' nosso pra derrubar)."""
    if no_ar():
        print("[i] servidor ja esta de pe na 8740 - usando esse, "
              "e NAO vou derrubar no fim")
        return None
    print("[i] subindo o servidor...")
    p = subprocess.Popen([str(VENV), "app.py"], cwd=str(RAIZ / "src"),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.5)
        if p.poll() is not None:
            raise SystemExit("[X] o servidor morreu ao subir - rode "
                             "`start_run.bat` na mao pra ver o erro")
        try:
            urllib.request.urlopen(BASE + "/api/state", timeout=1).read()
            return p
        except (urllib.error.URLError, OSError):
            continue
    p.terminate()
    raise SystemExit("[X] o servidor nao respondeu em 30s")


def limpa_smoke():
    """Manda o projeto do smoke pra _lixeira - o mesmo que ele faz sozinho
    quando roda sem --keep.

    O slug e' PERGUNTADO, nao adivinhado a partir do --name: quem decide como
    o nome vira slug e' o projects.py, e chutar aqui deixaria lixo no disco
    calado no dia em que essa regra mudar.
    """
    try:
        with urllib.request.urlopen(BASE + "/api/projects", timeout=10) as r:
            projetos = json.load(r).get("projects", [])
    except Exception as e:
        print(f"[!] nao consegui listar projetos pra limpar o smoke: {e}")
        return
    alvos = [p["slug"] for p in projetos
             if p.get("name") == SMOKE_NOME or p.get("slug") == SMOKE_NOME]
    for slug in alvos:
        req = urllib.request.Request(f"{BASE}/api/projects/{slug}",
                                     method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=30).read()
            print(f"[i] projeto {slug} movido pra projects/_lixeira")
        except Exception as e:
            print(f"[!] nao consegui limpar o projeto {slug}: {e}")


def roda(arquivo, exe, env, extra=()):
    t0 = time.time()
    r = subprocess.run([str(exe), str(RAIZ / "tests" / arquivo), *extra],
                       cwd=str(RAIZ), env=env,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, time.time() - t0, (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rapido", action="store_true",
                    help="so' os testes que nao precisam de servidor (~11s)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="mostra a saida de todos, nao so' a dos que falharam")
    args = ap.parse_args()

    if not VENV.is_file():
        raise SystemExit(f"[X] venv nao encontrado em {VENV} - rode o "
                         f"start_run.bat uma vez")

    suite = [s for s in SUITE if not (args.rapido and s[2])]
    mantem = any(a == "ui.py" for a, _, _ in suite)
    faltando = {exe for _, exe, _ in suite if not Path(exe).is_file()}
    for exe in faltando:
        print(f"[!] interpretador ausente: {exe} - os testes dele serao "
              f"PULADOS, nao contados como ok")

    # UTF-8 na saida dos filhos: varios imprimem acento e saida de ffmpeg, e no
    # console cp1252 do Windows isso vira UnicodeEncodeError NO TESTE, nao no
    # codigo testado - um falso negativo que custa tempo pra entender.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    proc = None
    if any(precisa for _, _, precisa in suite):
        proc = sobe_servidor()

    try:
        print()
        linhas, falhas, pulados = [], [], 0
        for arquivo, exe, _ in suite:
            if not Path(exe).is_file():
                linhas.append(("--", arquivo, 0.0, "interpretador ausente"))
                pulados += 1
                continue
            extra = ("--keep",) if (arquivo == "smoke.py" and mantem) else ()
            rc, dt, saida = roda(arquivo, exe, env, extra)
            resumo = ""
            for l in reversed(saida.strip().split("\n")):
                if l.strip():
                    resumo = l.strip()[:44]
                    break
            marca = "ok" if rc == 0 else "X"
            linhas.append((marca, arquivo, dt, resumo))
            print(f"  [{marca:>2}] {arquivo:<26} {dt:5.1f}s  {resumo}")
            if rc != 0:
                falhas.append((arquivo, saida))

        print()
        for arquivo, saida in falhas:
            print(f"{'=' * 70}\n{arquivo}\n{'=' * 70}")
            print(saida.strip()[-3000:])
            print()
        if args.verbose and not falhas:
            print("(tudo passou; --verbose so' mostra saida de quem falha)")

        total = sum(dt for _, _, dt, _ in linhas)
        if falhas:
            print(f"[X] {len(falhas)} de {len(suite)} FALHARAM "
                  f"({total:.0f}s): {', '.join(a for a, _ in falhas)}")
        else:
            extra = f", {pulados} pulado(s)" if pulados else ""
            print(f"[ok] {len(suite) - pulados} testes passaram "
                  f"({total:.0f}s{extra})")
        return 1 if falhas else 0
    finally:
        if mantem and no_ar():
            limpa_smoke()
        if proc is not None:
            proc.terminate()
            print("[i] servidor de teste encerrado")


if __name__ == "__main__":
    sys.exit(main())
