r"""Testes da quebra de legenda - rodam offline, sem servidor e sem Resolve.

    python tests\quebra.py

Cobrem o que erra em SILENCIO: uma legenda que nao cabe na caixa, e a
repartição dela em duas. O invariante caro e' o ultimo daqui - o texto da
legenda tem que continuar sendo, caractere a caractere, a concatenacao dos
tokens de `words`. E' por indice de caractere que o `GiWordTiming` acende a
palavra falada; um caractere fora do lugar acende a palavra errada no video
inteiro, e nada reclama.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from estilo_legenda import cabe, quebrar_linhas          # noqa: E402
from giautosubs import repartir                          # noqa: E402

falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)
        print(f"  FAILED: {msg}")


def palavras(texto, inicio, fim):
    """Tokens no formato do Whisper: o espaco separador pertence a palavra
    SEGUINTE, e a concatenacao e' exatamente o texto."""
    partes = texto.split(" ")
    passo = (fim - inicio) / len(partes)
    return [{"word": (p if i == 0 else " " + p),
             "start": round(inicio + i * passo, 3),
             "end": round(inicio + (i + 1) * passo, 3)}
            for i, p in enumerate(partes)]


# ------------------------------------------------------------------ quebra
print("quebra em linhas")
# A frase de referencia do limite, dada pelo usuario. Era
# "ELES SÓ SÃO MEIO TÍMIDOS." (25) ate' 01/09/2026.
REF = "que já amarrou uma."
checa(len(REF) == 19, f"a frase de referencia tem 19 caracteres, tem {len(REF)}")
checa(quebrar_linhas(REF, 19, 2) == [REF],
      "a frase de referencia cabe numa linha so no proprio limite")
checa(cabe(REF, 19, 2), "e cabe na caixa")
checa(len(quebrar_linhas("ELES SÓ SÃO MEIO TÍMIDOS.", 19, 2)) == 2,
      "a referencia ANTIGA (25 chars) agora ocupa DUAS linhas de 19 "
      "(ainda cabe na caixa - `cabe` olha a caixa inteira, nao a linha)")
checa(not cabe("Eles só são meio tímidos do frio, mas eu ficaria com uma "
               "coleira, pô.", 25, 2),
      "a frase de 69 caracteres NAO cabe em 2 linhas de 25")
checa(cabe("", 25, 2) or True, "texto vazio nao explode")
checa(not cabe("IMPRESSIONANTEMENTEGRANDE", 10, 2),
      "uma palavra maior que a linha nao cabe, e nenhuma quebra resolve")

# ------------------------------------------------------------- repartição
print("repartição em duas legendas")

texto = ("Imagina você poder chegar e soltar um mosquito da dengue na casa "
         "de alguém que te beija.")
ws = palavras(texto, 125.17, 128.60)
pedacos = repartir(texto, 125.17, 128.60, ws, 25, 2)

checa(len(pedacos) > 1, "a legenda de 88 caracteres vira mais de uma")
checa(all(cabe(t, 25, 2) for t, _, _, _ in pedacos),
      "todo pedaco cabe em 2 linhas de 25")
checa(pedacos[0][1] == 125.17 and pedacos[-1][2] == 128.60,
      "as PONTAS ficam com o tempo original do segmento - o Whisper abre antes "
      "da primeira palavra e estica depois da ultima, e encolher aqui faria a "
      "legenda piscar onde ela nao piscava")
checa(all(a[2] <= b[1] + 1e-9 for a, b in zip(pedacos, pedacos[1:])),
      "os pedacos nao se sobrepoem no tempo")

# o invariante caro
junto = []
for t, _, _, w in pedacos:
    checa(w is not None, "pedaco com tempo por palavra preservado")
    checa("".join(x["word"] for x in w) == t,
          f"o texto do pedaco e' a concatenacao dos tokens: {t!r}")
    checa(not t.startswith(" ") and not t.endswith(" "),
          f"o pedaco nao comeca nem termina com espaco: {t!r}")
    junto.append(t)
# junta com espaco, e nao cru: o token que ABRE um pedaco perde o espaco
# separador de proposito (ele deixou de ter vizinho a esquerda)
checa(" ".join(junto) == texto,
      "nenhuma palavra some nem se duplica na repartição")
checa(sum(len(w) for _, _, _, w in pedacos) == len(ws),
      f"os {len(ws)} tokens continuam sendo {len(ws)}")

# ------------------------------------- o pedaco de UMA palavra (bug de 01/09)
print("pedaco de um token so")
# Com uma linha de 19 caracteres, um pedaco de UM token so' virou comum - e ali
# a aparagem das pontas estava escrita como `toks[0], toks[-1] = ...`, em que os
# dois indices sao o MESMO elemento: o lado direito e' avaliado antes, e a
# segunda atribuicao desfazia a primeira. O token voltava com o espaco da frente,
# e o texto ficava um caractere fora dos tokens - o destaque acenderia a letra
# errada na legenda inteira. Foram 17 legendas num corte so'.
t2 = "Eu coloquei mosquito hoje."
w2 = palavras(t2, 0.0, 3.0)
for txt, _, _, w in repartir(t2, 0.0, 3.0, w2, 19, 1):
    checa(w and "".join(x["word"] for x in w) == txt,
          f"texto e tokens tem que casar caractere a caractere: {txt!r} vs "
          f"{''.join(x['word'] for x in (w or []))!r}")
    checa(not txt.startswith(" "), f"pedaco nao pode comecar com espaco: {txt!r}")
    checa(len(quebrar_linhas(txt, 19, 1)) == 1,
          f"com max_linhas = 1 nenhum pedaco pode ter duas linhas: {txt!r}")

# ------------------------------------------------------ casos que nao partem
print("o que NAO deve ser partido")
curta = "Pode ir."
checa(repartir(curta, 0.9, 1.45, palavras(curta, 0.9, 1.45), 25, 2)
      == [(curta, 0.9, 1.45, palavras(curta, 0.9, 1.45))],
      "o que ja cabe volta intacto, com a mesma tupla")

uma_so = "IMPRESSIONANTEMENTEGRANDE"
p = repartir(uma_so, 0.0, 1.0, palavras(uma_so, 0.0, 1.0), 10, 2)
checa(len(p) == 1 and p[0][0] == uma_so,
      "uma palavra sozinha maior que a linha volta inteira (partir nao ajuda) "
      "- quem reclama disso e' o resumo do giautosubs.py")

# ------------------------------------------------------------- sem `words`
print("sem tempo por palavra")
p = repartir(texto, 10.0, 20.0, None, 25, 2)
checa(len(p) > 1, "reparte tambem sem tempo por palavra")
checa(all(cabe(t, 25, 2) for t, _, _, _ in p), "e todo pedaco cabe")
checa(all(w is None for _, _, _, w in p), "sem words entra, sem words sai")
checa(p[0][1] == 10.0 and p[-1][2] == 20.0, "as pontas continuam originais")
checa(all(a[2] <= b[1] + 1e-9 for a, b in zip(p, p[1:])),
      "o tempo estimado por comprimento nao se sobrepoe")

print(f"\n{len(falhas)} failure(s)" if falhas else "\nALL OK")
raise SystemExit(1 if falhas else 0)
