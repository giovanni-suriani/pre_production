"""As TRES variantes do macro nao podem se contaminar.

Roda os tres `main()` no MESMO processo, de proposito: e' a forma que ja quebrou
uma vez (`_sem_camada3` filtrava as listas globais sem volta, e a variante
gerada depois nascia sem os proprios controles). Aqui a ordem e' a pior
possivel - a mais pobre primeiro, a mais rica por ultimo.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import gerar_macro as G                                       # noqa: E402

falhas = []


def checa(cond, msg):
    print(("  ok   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


tmp = tempfile.mkdtemp(prefix="gispin")
saidas = {}
for nome, args in (("caption", []),
                   ("3color", ["--camada3"]),
                   ("spinning", ["--spin"])):
    fora = os.path.join(tmp, nome + ".setting")
    G.main(args + ["--estilo", "capcut_bolha", "--out", fora])
    with open(fora, encoding="utf-8") as fh:
        saidas[nome] = fh.read()

print()

# O Caption e' o macro de sempre: nada da camada 3, nada do spin.
checa("BoxLayer3" not in saidas["caption"],
      "o Caption nao pode carregar controle da camada 3")
checa("BoxSpinSpeed" not in saidas["caption"],
      "o Caption nao pode carregar o controle de spin")

# O 3color tem a camada 3 e NAO tem o spin - girar e' a outra variante.
checa(saidas["3color"].count("BoxLayer3") > 0,
      "o 3color tem que publicar os controles da camada 3 "
      "(era o sintoma do bug de estado global: nascia vazio)")
checa("BoxSpinSpeed" not in saidas["3color"],
      "o 3color e' a caixa PARADA; o controle de spin nao pertence a ele")
checa("SetExpression" not in saidas["3color"],
      "sem spin nao pode haver expressao: o offset e' numero escrito por pin()")

# E o spinning tem os dois.
checa(saidas["spinning"].count("BoxLayer3") > 0,
      "o spinning implica a camada 3 - girar UMA cor nao e' o efeito")
checa("BoxSpinSpeed" in saidas["spinning"],
      "o spinning tem que publicar o Spin Speed")
checa("SetExpression" in saidas["spinning"],
      "o spinning escreve o offset como EXPRESSAO, nao como numero")
# Limpar a expressao ANTES de escrever numero e' o que faz desligar o spin
# devolver a caixa pro lugar; sem isso ela gira pra sempre.
checa("SetExpression(nil)" in saidas["spinning"],
      "a expressao tem que ser limpa antes da escrita numerica, senao "
      "desligar o spin nao volta a caixa pro lugar")

print()
if falhas:
    print(f"{len(falhas)} FAILED")
    sys.exit(1)
print("ALL OK")
