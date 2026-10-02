"""O macro e' UNICO: a camada 3 e o spin vem sempre, e vem DESLIGADOS.

Ate' o macro 29 isto testava tres variantes que nao podiam se contaminar. O
macro 30 colapsou as quatro num Title so', entao o que sobrou pra provar e' o
oposto: que os dez controles antes exclusivos das variantes agora existem
SEMPRE, e que existir nao liga nada.

Continua gerando DUAS vezes no mesmo processo, de proposito: foi essa a forma
que ja quebrou uma vez (o antigo `_sem_camada3` filtrava as listas globais sem
volta, e o macro gerado depois nascia sem os proprios controles). A filtragem
por efeito colateral morreu junto com as variantes - este teste e' o que impede
ela de voltar.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import gerar_macro as G                                       # noqa: E402

falhas = []


def checa(cond, msg):
    print(("  ok   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def default(texto, controle):
    m = re.search(re.escape(controle) + r" = \{.*?INP_Default = ([-0-9.]+)",
                  texto, re.S)
    return float(m.group(1)) if m else None


tmp = tempfile.mkdtemp(prefix="gispin")
saidas = {}
for nome in ("primeira", "segunda"):
    fora = os.path.join(tmp, nome + ".setting")
    G.main(["--estilo", "capcut_bolha", "--out", fora, "--sem-validar"])
    with open(fora, encoding="utf-8") as fh:
        saidas[nome] = fh.read()

print()

# ------------------------------------------------ os controles existem sempre
for nome, texto in saidas.items():
    checa(texto.count("BoxLayer3") > 0,
          f"({nome}) o macro unico tem que publicar os controles da camada 3")
    checa("BoxSpinSpeed" in texto,
          f"({nome}) o macro unico tem que publicar o Spin Speed")

# Duas geracoes no mesmo processo tem que sair IGUAIS. Se um dia alguem voltar a
# filtrar lista global por efeito colateral, a segunda sai mais pobre que a
# primeira, e e' aqui que aparece.
checa(saidas["primeira"] == saidas["segunda"],
      "duas geracoes no mesmo processo tem que sair byte a byte iguais "
      "(estado global filtrado sem volta era o bug antigo)")

texto = saidas["primeira"]

# ---------------------------------------------------- e existir nao liga nada
# O default do Spin Speed e' ZERO, e este e' o teste que mais importa no macro
# unico. Enquanto o spin era um Title proprio, escolher aquele Title JA' era
# pedir o giro e o default 2 fazia sentido; agora todo clipe nasce com este
# controle, e um default 2 poria TODA legenda pra girar sem ninguem pedir.
v = default(texto, "BoxSpinSpeed")
checa(v == 0.0,
      f"o Spin Speed tem que nascer em 0 - senao toda legenda gira sem pedir (achei {v})")

v = default(texto, "BoxLayer3Enabled")
checa(v == 0.0,
      "um estilo sem camada3 (capcut_bolha) tem que nascer com a terceira cor "
      f"desligada (achei {v})")

# --------------------------------------------------------- a guarda do runtime
# A expressao EXISTE no chunk (e' codigo), mas so' e' escrita quando a
# velocidade nao e' zero. E' essa guarda que faz "custo zero pra quem nao usa"
# ser verdade POR FRAME, e nao so' no papel - sem ela, caixa parada pagaria uma
# expressao avaliada a cada frame.
checa("SetExpression" in texto,
      "o chunk carrega a escrita de expressao (o codigo do spin)")
checa('(ctl("BoxSpinSpeed", 0) ~= 0)' in texto,
      "a expressao so' pode ser escrita quando o Spin Speed nao e' zero - "
      "sem essa guarda, caixa parada pagaria expressao por frame")
# Limpar a expressao ANTES de escrever numero e' o que faz desligar o spin
# devolver a caixa pro lugar; sem isso ela gira pra sempre.
checa("SetExpression(nil)" in texto,
      "a expressao tem que ser limpa antes da escrita numerica, senao "
      "desligar o spin nao volta a caixa pro lugar")

print()
if falhas:
    print(f"{len(falhas)} FAILED")
    sys.exit(1)
print("ALL OK")
