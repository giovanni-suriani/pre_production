r"""O dialogo de configuracoes do SpeakerSwitch, exercitado fora do Resolve.

Nao precisa de servidor nem de Resolve - so de um Python com tkinter:

    C:\Users\talco\AppData\Local\Programs\Python\Python312\python.exe tests\dialogo_speakerswitch.py

A janela e' construida DE VERDADE (o mesmo snippet, o mesmo processo separado,
os mesmos defaults por stdin); o que o teste faz por codigo e' apertar os
botoes. O que sobra sem cobertura e' o clique em si.

Por que isto existe: o dialogo e a unica porta de entrada das opcoes da rodada,
e ele roda dentro de um `python -c` que so' e' compilado quando alguem clica no
menu do Resolve. Um erro de sintaxe ali nao aparece em lugar nenhum ate a hora
de montar a timeline - que e' o pior momento possivel para descobrir.

Ele importa o `SpeakerSwitch.py`; o guarda no fim daquele arquivo
(`if __name__ != "SpeakerSwitch"`) e' o que impede o import de sair montando
timeline.
"""
import json
import os
import shutil
import subprocess
import sys

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


def roda_dialogo(defaults, auto="rodar"):
    """auto='rodar' aceita a janela; 'cancelar' fecha sem aceitar; 'barrado'
    tenta aceitar e fecha 900 ms depois - e' o caso em que a validacao recusa e
    a janela CONTINUA aberta (que e' o certo: o usuario corrige o campo). O
    texto do aviso sai no stderr, para dar para conferir qual foi."""
    gatilho = {
        "rodar": "root.after(300, rodar)",
        "cancelar": "root.after(300, root.destroy)",
        "barrado": ("root.after(300, rodar)\n"
                    "root.after(900, lambda: (sys.stderr.write(erro.cget('text')),"
                    " root.destroy()))"),
    }[auto]
    src = S._SETTINGS_DIALOG_SNIPPET.replace(
        "root.mainloop()", gatilho + "\nroot.mainloop()")
    try:
        return subprocess.run([sys.executable, "-c", src],
                              input=json.dumps(defaults), capture_output=True,
                              text=True, timeout=30)
    except subprocess.TimeoutExpired:
        # a janela ficou aberta: sem isso o teste travaria de vez, com um
        # dialogo orfao por cima de tudo (ele nasce -topmost)
        return subprocess.CompletedProcess([], 99, "", "TIMEOUT")


print("1. o codigo do dialogo compila")
try:
    compile(S._SETTINGS_DIALOG_SNIPPET, "<dialogo>", "exec")
    check(True, "o snippet compila")
except SyntaxError as e:
    check(False, f"o snippet NAO compila: {e}")

print("\n1b. geometria fora da tela, com os padroes pedidos")
p0 = S.opcoes_padrao()
check(p0["remove_cut"] is True and p0["silence_mode"] == "preencher",
      f"padrao: remover cut + preencher silencio ({p0['remove_cut']}, {p0['silence_mode']!r})")
check("silencio = escolha(" not in S._SETTINGS_DIALOG_SNIPPET.replace("# silencio", ""),
      "o radio de silencio nao e' mais montado")
check({"remove_cut", "silence_mode", "range_start", "range_end"} <= S._OPCOES_FIXAS,
      "opcoes gravadas do corte nao sobrescrevem os campos escondidos")

print("\n2. a janela monta e devolve o que recebeu")
padroes = S.opcoes_padrao()
padroes["turns"] = r"D:\um\caminho\turnsGeminiVideo4_shots.json"
r = roda_dialogo(padroes)
check(r.returncode == 0, f"o dialogo saiu com codigo {r.returncode}")
saida = json.loads(r.stdout) if r.stdout.strip() else None
check(saida is not None, "veio json de volta")
if saida:
    faltando = [k for k in S.opcoes_padrao() if k not in saida]
    check(not faltando, f"a resposta traz todas as opcoes (faltou: {faltando})")
    check(saida["turns"] == padroes["turns"], "o caminho do json atravessou")
    check(saida["resolution"] == "1080x1920",
          f"a resolucao voltou como {saida['resolution']!r}")
    check(saida["fusion"] is False and saida["copy_audio"] is True,
          "as caixas voltaram com o estado que entrou")

print("\n3. o que foi marcado atravessa")
p2 = dict(padroes, fusion=True, grade=True, split_audio=True, remove_cut=False,
          silence_mode="remover",
          resolution="", mismatch="", range_start="2610.5", range_end="2750",
          timeline_name="Short_01")
r2 = roda_dialogo(p2)
s2 = json.loads(r2.stdout) if r2.stdout.strip() else {}
check(s2.get("fusion") is True and s2.get("grade") is True,
      "Fusion e grade ligados")
check(s2.get("remove_cut") is False, "remover 'cut' desligado")
check(s2.get("silence_mode") == "remover", "silencio no modo remover")
check(s2.get("resolution") == "" and s2.get("mismatch") == "",
      "resolucao/encaixe vazios sobrevivem (= herdar da origem)")
check(s2.get("range_start") == "2610.5" and s2.get("range_end") == "2750",
      "o recorte atravessou")
check(s2.get("timeline_name") == "Short_01", "o nome da timeline atravessou")

print("\n4. cancelar nao devolve nada")
r3 = roda_dialogo(padroes, auto="cancelar")
check(r3.returncode == 0 and r3.stdout.strip() == "",
      "fechar a janela devolve string vazia (= cancelado)")

print("\n5. campo invalido nao deixa rodar, e a janela diz por que")
# resolucao e recorte sairam da tela em 10/09 - so' sobrou a diarizacao
for campo, valores, esperado in [
        ("sem diarizacao", {"turns": ""}, "json de diarizacao")]:
    rv = roda_dialogo(dict(padroes, **valores), auto="barrado")
    check(rv.returncode == 0 and rv.stdout.strip() == "",
          f"{campo}: o dialogo NAO devolve escolha")
    check(esperado in (rv.stderr or ""),
          f"{campo}: o aviso explica ({(rv.stderr or '').strip()[:50]!r})")

print("\n6. as escolhas viram os globais que o script le")
S.aplicar_opcoes(s2)
check(S.COPY_FUSION_COMPS is True and S.COPY_COLOR_GRADE is True,
      "Fusion e grade ligados nos globais")
check(S.REMOVE_CUT is False and S.SILENCE_MODE == "remover"
      and S.SPLIT_AUDIO_BY_SPEAKER is True,
      "cut, silencio e audio por falante")
S.aplicar_opcoes(dict(s2, silence_mode="ziguezague"))
check(S.SILENCE_MODE == "remover",
      "silence_mode invalido nao muda nada calado (mantem o anterior + avisa)")
check(S.TARGET_WIDTH is None and S.TARGET_HEIGHT is None,
      "resolucao vazia -> None (mantem a da origem)")
check(S.MISMATCH_BEHAVIOR is None, "encaixe vazio -> None (herda da origem)")
check(S.RANGE_START == 2610.5 and S.RANGE_END == 2750.0,
      f"recorte virou float ({S.RANGE_START}, {S.RANGE_END})")
check(S.NEW_TIMELINE_NAME == "Short_01", "nome da timeline nova")
S.aplicar_opcoes(dict(s2, resolution="1080x1920", mismatch="scaleToCrop",
                      range_start="", range_end=""))
check(S.TARGET_WIDTH == 1080 and S.TARGET_HEIGHT == 1920, "1080x1920 volta")
check(S.RANGE_START is None and S.RANGE_END is None, "recorte vazio -> None")

print("\n7. as opcoes ficam guardadas na pasta do corte")
tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_corte_falso")
os.makedirs(tmp, exist_ok=True)
try:
    S._gravar_opcoes(tmp, s2)
    lidas = S._ler_opcoes(tmp)
    check(lidas.get("fusion") is True and lidas.get("timeline_name") == "Short_01",
          "gravou e leu de volta")
    check(S._ler_opcoes(os.path.join(tmp, "nao_existe")) == {},
          "pasta sem arquivo devolve {}")
    # o arquivo tem que caber de volta no dialogo: uma chave a mais aqui seria
    # uma opcao que ninguem ve e ninguem edita
    check(set(lidas) <= set(S.opcoes_padrao()),
          f"so' guarda chaves que o dialogo conhece ({sorted(lidas)})")
    # opcoes gravadas antes de 02/09 tem `fill_gaps` (bool) e nenhum
    # `silence_mode`; ignorar isso reabriria o dialogo com "preencher" marcado
    # pra quem tinha desmarcado, sem explicacao
    S._gravar_opcoes(tmp, {"fill_gaps": False, "fusion": True})
    velhas = S._ler_opcoes(tmp)
    check(velhas.get("silence_mode") == "buraco" and "fill_gaps" not in velhas,
          "fill_gaps=False antigo vira silence_mode='buraco'")
    S._gravar_opcoes(tmp, {"fill_gaps": True})
    check(S._ler_opcoes(tmp).get("silence_mode") == "preencher",
          "fill_gaps=True antigo vira silence_mode='preencher'")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{ok_count} ok, {fail_count} falharam")
sys.exit(1 if fail_count else 0)
