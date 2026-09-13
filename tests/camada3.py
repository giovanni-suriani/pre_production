r"""Testes da caixa de tres cores - rodam offline, sem servidor e sem Resolve.

    python tests\camada3.py

O efeito e' a MESMA caixa desenhada tres vezes, DESLOCADA - nao tres bordas
concentricas. Por isso o invariante caro daqui e' a geometria: no instante em
que `Level`, os dois `Extend` ou o `Round` divergirem entre os elementos 6, 7 e
8, o que aparece na tela deixa de ser tres cores e vira um contorno torto. Nada
reclama - o Text+ aceita geometria diferente em cada elemento numa boa.

O segundo invariante e' o sinal dos offsets: as duas camadas coloridas tem que
cair em lados OPOSTOS. Iguais, elas empilham no mesmo canto e a de baixo some.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

import giautosubs as G                                     # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)
        print(f"  FAILED: {msg}")


est = G.carregar_estilos(os.path.join(_RAIZ, "estilos.json"))
inputs, controles, _ = G.compilar_estilo(est["estilos"]["caixa_tres_cores"])

CAIXA, CIANO, ROSA = (G.ELEM_CX_BASE, G.ELEM_CX_BASE_SOMBRA,
                      G.ELEM_CX_BASE_CAMADA3)

# ------------------------------------------------------- os tres existem
print("os tres elementos ligados")
for n in (CAIXA, CIANO, ROSA):
    checa(inputs.get(f"Enabled{n}") == 1, f"Enabled{n} deveria ser 1")
    # Elementos 5..8 nascem em forma de TEXTO. Sem a troca pra borda o Text+
    # aceita Level/Extend/Round e nao desenha caixa nenhuma - era essa a caixa
    # que "nao aparecia".
    checa(inputs.get(f"_borda{n}") is True,
          f"elemento {n} tem que virar Border Fill (_borda{n})")

# --------------------------------------------------- a geometria e' UMA so
print("geometria identica nos tres")
for chave in ("Level", "ExtendHorizontal", "ExtendVertical", "Round"):
    vals = [inputs.get(f"{chave}{n}") for n in (CAIXA, CIANO, ROSA)]
    checa(len(set(map(repr, vals))) == 1,
          f"{chave} diverge entre os elementos {CAIXA}/{CIANO}/{ROSA}: {vals}"
          f" - o deslocamento vira contorno torto")

# ------------------------------------------------------- lados opostos
print("as duas cores caem em lados opostos")
oc, orr = inputs.get(f"_offset{CIANO}"), inputs.get(f"_offset{ROSA}")
checa(oc is not None, f"_offset{CIANO} (a segunda cor) nao foi escrito")
checa(orr is not None, f"_offset{ROSA} (a terceira cor) nao foi escrito")
if oc and orr:
    for eixo, nome in ((0, "x"), (1, "y")):
        checa(oc[eixo] * orr[eixo] < 0,
              f"as duas camadas deslocam pro MESMO lado em {nome} "
              f"({oc[eixo]} e {orr[eixo]}) - uma cobre a outra")

# --------------------------------------- transparencia por Alpha, nao Opacity
# `Opacity1..4` do Follower1 sao o fade do AutoSubs; os elementos 5..8 nao estao
# ligados nele. Escrever `Opacity8` gastaria o input por onde o fade entraria.
print("a terceira cor usa Alpha, nao Opacity")
checa(f"Alpha{ROSA}" in inputs, f"Alpha{ROSA} deveria existir")
checa(f"Opacity{ROSA}" not in inputs,
      f"Opacity{ROSA} nao deve ser escrito (e' por onde o fade entraria)")

# ------------------------------------------------- o Inspector conta o mesmo
# Um controle que existe no Inspector e nao no estilo (ou o contrario) e' o
# "mexi, rodei o script, e voltou ao que era".
print("os controles do Inspector batem com os inputs")
checa(controles.get("BoxLayer3Enabled") == 1, "BoxLayer3Enabled deveria ser 1")
for canal, chave in (("Red", "BoxLayer3ColorRed"),
                     ("Green", "BoxLayer3ColorGreen"),
                     ("Blue", "BoxLayer3ColorBlue")):
    checa(abs(controles.get(chave, -1) - inputs.get(f"{canal}{ROSA}", -2)) < 1e-9,
          f"{chave} nao bate com {canal}{ROSA}")
checa([controles.get("BoxLayer3CenterX"), controles.get("BoxLayer3CenterY")]
      == list(orr or []), "BoxLayer3Center X/Y nao batem com o offset escrito")

# ------------------------------------------------------------ ida e volta
# O `Generate Caption Style` le o clipe de volta pro estilos.json. Um campo que
# nao sobrevive a volta some do estilo exportado sem avisar.
print("ida e volta (Generate Caption Style)")
volta = G.estilo_de_controles(controles, inputs)["base"]["camada3"]
checa(volta["ativo"] is True, "camada3.ativo nao sobreviveu a volta")
checa(volta["cor"].upper() == "#FF4DA6", f"cor voltou como {volta['cor']}")
checa(volta["direcao"]["x"] == orr[0] and volta["direcao"]["y"] == orr[1],
      "a direcao nao sobreviveu a volta")

# ----------------------------------- desligada nao custa nada a quem nao usa
print("estilo sem camada3 nao liga o elemento 8")
inputs2, controles2, _ = G.compilar_estilo(est["estilos"]["capcut_bolha"])
checa(inputs2.get(f"Enabled{ROSA}") == 0,
      "o capcut_bolha nao pede terceira cor; o elemento 8 tem que ficar off")
# E nao pode escrever CONTROLE nenhum: os `BoxLayer3*` so' existem na variante
# `--camada3` do macro. Um estilo sem `camada3` que os escrevesse quebraria a
# geracao do macro PADRAO - "the style asks for it, but there is nowhere to
# store it". O `Enabled8` cru continua indo, porque e' input do Text+.
checa(not [k for k in controles2 if k.startswith("BoxLayer3")],
      "um estilo sem camada3 nao pode escrever controles BoxLayer3*: "
      "o macro padrao nao tem onde guardar")

# ... e a exportacao segue a mesma regra, senao um estilo lido de um clipe comum
# passaria a exigir um controle que o macro dele nao tem.
volta2 = G.estilo_de_controles(controles2, inputs2)
checa("camada3" not in volta2["base"],
      "a volta nao pode inventar um bloco camada3 num clipe sem esses controles")

print()
if falhas:
    print(f"{len(falhas)} FAILED")
    sys.exit(1)
print("ALL OK")
