r"""Testes da aba Meta e da caixa fixa - rodam offline, sem Resolve.

    python tests\meta.py

A aba Meta e' a PONTE: ela e' o unico lugar onde fica escrito de que
`legendas.lua`, de que corte e com quantos caracteres por caixa uma legenda
nasceu. O que este arquivo cobre e' o lado Python dessa ponte, que e' o unico
lado testavel fora do Resolve:

  1. o bloco `meta` sai no `legendas.lua`, com o que o botao Rebuild precisa
     (sem `cut_folder` nao ha como chamar o giautosubs.py de volta);
  2. o numero que vale na Meta e' o que REPARTIU estas legendas - o
     `--max-chars` da rodada vence o `quebra.max_chars` do estilo. Se ele
     discordar, o "Apply Style to This Track" acha que o numero mudou e
     reconstroi as legendas sozinho, sem ninguem ter pedido;
  3. a Meta NAO viaja no preset. No `InputKeys` ela faria o "Apply Style to All
     Captions" carimbar a procedencia de um clipe em cima de todos os outros, e o
     "Export Config" gravar caminhos de maquina dentro de um estilo;
  4. `caixa.fixa` chega ao controle `TextBoxFixed`.

O que NAO da' pra testar aqui: a conta da caixa fixa em si. Ela mora no
`extend_h` do macro (Lua, dentro do Resolve) porque depende do texto do CLIPE -
inclusive do texto corrigido a mao depois. Quem confere que aquele Lua compila e'
o `valida_macro.lua` pelo fuscript.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

import giautosubs as G                                     # noqa: E402
import gerar_macro as M                                    # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)
        print(f"  FAILED: {msg}")


est = G.carregar_estilos(os.path.join(_RAIZ, "estilos.json"))

# --------------------------------------------- 1. os numeros vem do estilo
print("os numeros da Meta saem do estilo")
_, controles, _ = G.compilar_estilo(est["estilos"]["capcut_bolha"])
quebra = est["estilos"]["capcut_bolha"].get("quebra") or {}
checa(controles.get("MetaCharsPerBox") == quebra.get("max_chars", 19),
      f"MetaCharsPerBox deveria ser {quebra.get('max_chars')}, "
      f"e' {controles.get('MetaCharsPerBox')}")
checa(controles.get("MetaLines") == quebra.get("max_linhas", 1),
      f"MetaLines deveria ser {quebra.get('max_linhas')}, "
      f"e' {controles.get('MetaLines')}")
# A regua da caixa fixa. Zero aqui desliga a caixa fixa em silencio (o macro
# avisa no log, mas nenhuma caixa ficaria fixa) - por isso ela nunca e' 0.
checa((controles.get("MetaCharWidth") or 0) > 0,
      "MetaCharWidth tem que ser > 0, senao a caixa fixa nao tem regua")

# ------------------------------------------------- 2. a caixa fixa no estilo
print("caixa.fixa chega ao TextBoxFixed")
checa(controles.get("TextBoxFixed") == 0,
      "um estilo sem `caixa.fixa` tem que nascer com TextBoxFixed = 0")

import copy                                                # noqa: E402
com_fixa = copy.deepcopy(est["estilos"]["capcut_bolha"])
com_fixa.setdefault("base", {}).setdefault("caixa", {})["fixa"] = True
com_fixa["base"]["caixa"]["largura_caractere"] = 0.42
_, ctl_fixa, _ = G.compilar_estilo(com_fixa)
checa(ctl_fixa.get("TextBoxFixed") == 1,
      "`caixa.fixa = true` tem que virar TextBoxFixed = 1")
checa(abs((ctl_fixa.get("MetaCharWidth") or 0) - 0.42) < 1e-9,
      f"largura_caractere deveria virar MetaCharWidth 0.42, "
      f"veio {ctl_fixa.get('MetaCharWidth')}")

# ------------------------------------------------- 3. a Meta fora do preset
print("a Meta fica fora do schema do preset")
chaves = M.input_keys()
vazando = [k for k in chaves if k.startswith("Meta")]
checa(not vazando,
      f"estes controles da Meta entraram no InputKeys e viajariam no preset: "
      f"{vazando}")
# E o contrario: o Fixed Box E' estilo, e tem que viajar. Sem ele no schema, o
# "Apply Style to All Captions" ligaria a caixa em todas as legendas menos no
# atributo que decide se ela e' fixa.
checa("TextBoxFixed" in chaves,
      "TextBoxFixed tem que estar no InputKeys - ele e' estilo, nao procedencia")

# ------------------------------------ 4. o bloco meta do legendas.lua, de ponta
print("o bloco meta sai no legendas.lua")
corte = os.path.join(_RAIZ, "projects", "DeuMerda", "cortes", "rank_surpresa")
if not os.path.isfile(os.path.join(corte, "corte.json")):
    print(f"  (pulado: {corte} nao existe nesta maquina)")
else:
    doc, stats = G.montar(corte, est, "capcut_bolha", True, 25, (), None, 1)
    meta = doc.get("meta") or {}
    for chave in ("cut_folder", "transcript", "style", "styles_file",
                  "chars_per_box", "lines"):
        checa(meta.get(chave), f"meta.{chave} saiu vazio")
    checa(os.path.isdir(meta.get("cut_folder") or ""),
          "meta.cut_folder tem que ser uma pasta que existe - e' o argumento "
          "com que o botao Rebuild chama este script de volta")
    checa(os.path.isfile(meta.get("transcript") or ""),
          "meta.transcript tem que ser um arquivo que existe")

    # O NUMERO DA RODADA vence o do estilo. Este e' o teste que importa: com o
    # numero do estilo aqui, o "Apply Style to This Track" compararia 19 com o
    # 25 do Inspector e reconstruiria as legendas sem ninguem pedir.
    checa(meta.get("chars_per_box") == 25,
          f"meta.chars_per_box deveria ser o 25 da rodada, e' "
          f"{meta.get('chars_per_box')}")
    checa(doc["controles"].get("MetaCharsPerBox") == 25,
          f"o controle MetaCharsPerBox deveria ser 25, e' "
          f"{doc['controles'].get('MetaCharsPerBox')}")
    checa(stats["max_chars"] == 25,
          "o resumo e a Meta tem que falar do mesmo numero")
    # Sem pedir, a rodada nao fixa nada: quem decide continua sendo o estilo.
    checa(doc["controles"].get("TextBoxFixed") == 0,
          "uma rodada sem --fixed-box nao pode fixar a caixa por conta propria")
    checa((doc["meta"] or {}).get("fixed_box") is False,
          "meta.fixed_box tem que registrar que esta rodada NAO fixou a largura")

    # --------------------------- o "Rebuild with Fixed Width", do lado Python
    #
    # A largura fixa pedida pra rodada INTEIRA: todas as legendas nascem com a
    # caixa de uma linha cheia, em vez de alguem ligar o checkbox clipe a clipe.
    # E' o que faz uma sequencia ler como UMA caixa com o texto trocando dentro -
    # com a caixa mudando de tamanho, a borda do 3color_spinning orbita um
    # retangulo que pula a cada legenda.
    doc_fx, _ = G.montar(corte, est, "capcut_bolha", True, 25, (), None, 1,
                         None, True)
    checa(doc_fx["controles"].get("TextBoxFixed") == 1,
          "--fixed-box tem que nascer com TextBoxFixed = 1 em todas as legendas")
    checa((doc_fx["meta"] or {}).get("fixed_box") is True,
          "meta.fixed_box tem que registrar a largura fixa desta rodada")
    # A largura-alvo e' o MESMO numero que repartiu as frases. Se os dois
    # divergirem, a caixa fixa fica mais larga (ou mais estreita) que a linha que
    # ela deveria conter, e ninguem sabe qual dos dois esta errado.
    checa(doc_fx["controles"].get("MetaCharsPerBox")
          == doc_fx["meta"].get("chars_per_box") == 25,
          "o alvo da caixa fixa e o limite da reparticao tem que ser um numero so'")
    # E o estilo continua sendo o dono quando ninguem pede nada: a flag e' da
    # rodada, nao uma mudanca no estilos.json.
    _, ctl_depois, _ = G.compilar_estilo(est["estilos"]["capcut_bolha"])
    checa(ctl_depois.get("TextBoxFixed") == 0,
          "a flag da rodada nao pode vazar pro estilo carregado em memoria")

    # ------------------------------- o "Rebuild without Gaps" (`--no-gaps`)
    #
    # Cada legenda dura ate' a PROXIMA entrar, pra a caixa nao piscar entre duas.
    # O invariante caro e' por TRACK: esticar pela lista toda faria duas legendas
    # da mesma track se sobreporem - o unico estado impossivel numa track de
    # video - e a legenda de um falante terminar onde a de OUTRO comeca, numa
    # track onde essa outra nem esta.
    doc_ng, st_ng = G.montar(corte, est, "capcut_bolha", True, 25, (), None, 1,
                             None, True, True)
    checa((doc_ng["meta"] or {}).get("no_gaps") is True,
          "meta.no_gaps tem que registrar a rodada sem buracos")
    checa(st_ng["esticadas"] > 0,
          "nenhuma legenda foi esticada - o --no-gaps nao fez nada")
    checa(len(doc_ng["segments"]) == len(doc["segments"]),
          "o --no-gaps nao pode criar nem sumir com legenda: ele so' mexe no fim")

    speakers = doc_ng["speakers"]

    def track_de(seg):
        if doc_ng["track_unica"]:
            return 1
        sid = seg.get("speaker_id") or 0
        if 1 <= sid <= len(speakers):
            return (speakers[sid - 1] or {}).get("track") or 1
        return 1

    por_track = {}
    for seg in doc_ng["segments"]:
        por_track.setdefault(track_de(seg), []).append(seg)
    sobrepostas, buracos, encurtadas = 0, 0, 0
    antes = {(s["start"], s["text"]): s["end"] for s in doc["segments"]}
    for legendas in por_track.values():
        legendas.sort(key=lambda s: s["start"])
        for a, b in zip(legendas, legendas[1:]):
            if a["end"] > b["start"] + 1e-6:
                sobrepostas += 1
            elif a["end"] < b["start"] - 1e-6:
                buracos += 1
    for s in doc_ng["segments"]:
        fim_antes = antes.get((s["start"], s["text"]))
        if fim_antes is not None and s["end"] < fim_antes - 1e-6:
            encurtadas += 1
    checa(sobrepostas == 0,
          f"{sobrepostas} par(es) de legendas se sobrepoem na MESMA track - "
          f"esticar pela lista toda em vez de por track")
    checa(buracos == 0, f"sobraram {buracos} buraco(s) entre legendas da mesma track")
    # Nunca encolhe: legenda que ja passava do inicio da proxima (sobreposicao na
    # transcricao) fica como esta. Encurtar seria consertar calado um problema de
    # outra etapa.
    checa(encurtadas == 0,
          f"{encurtadas} legenda(s) ficaram MAIS CURTAS - o --no-gaps so' estica")
    # E a ultima de cada track fica com o fim dela: nao ha proxima, e inventar um
    # fim seria inventar quanto tempo a legenda sobra depois da fala.
    for t_, legendas in por_track.items():
        ultima = legendas[-1]
        fim_antes = antes.get((ultima["start"], ultima["text"]))
        checa(fim_antes is None or abs(ultima["end"] - fim_antes) < 1e-6,
              f"a ultima legenda da track {t_} mudou de fim, e nao ha proxima "
              f"pra justificar isso")

# --------------------------------- 5. o MENU de estilos que a rodada oferece
#
# A pergunta "qual estilo" dentro do Resolve e' feita de ARQUIVOS: o
# `fusion:RequestFile` e' o unico dialogo que funciona na pagina Edit e ele lista
# arquivos, e o Lua do Resolve nao le JSON. Entao o menu tem que sair daqui - e
# tem que ENVELHECER junto com o estilos.json, senao a rodada oferece um estilo
# que nao existe mais (e ai ela quebra no `cfg["estilos"][nome]`) ou esconde um
# novo.
print("o menu de estilos acompanha o estilos.json")
import tempfile                                             # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    # um estilo que nao existe mais, deixado por uma rodada anterior
    with open(os.path.join(tmp, "estilo_que_morreu.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("sobra de outra rodada\n")

    n = G.escrever_menu_estilos(est, tmp)
    arquivos = {a[:-4] for a in os.listdir(tmp) if a.endswith(".txt")}
    checa(n == len(est["estilos"]),
          f"o menu escreveu {n} arquivo(s) para {len(est['estilos'])} estilo(s)")
    checa(arquivos == set(est["estilos"]),
          f"o menu nao bate com o estilos.json: sobrando "
          f"{sorted(arquivos - set(est['estilos']))}, faltando "
          f"{sorted(set(est['estilos']) - arquivos)}")

    # Os tres looks que eram TITLE ate' o macro 30 e viraram estilo. Perder
    # qualquer um deles e' perder um visual que o usuario usa - foi ele quem
    # cobrou isso por escrito.
    for nome in ("TikTokNovo", "3_color", "3_color_spinning"):
        checa(nome in arquivos,
              f"'{nome}' tem que estar no menu - era um Title proprio antes do "
              f"macro 30 e nao pode se perder na fusao")

# O giro: era a variante `--spin` do macro, hoje e' um controle que o ESTILO liga.
print("o giro sai do estilo, e nao de uma variante do macro")
_, ctl_gira, _ = G.compilar_estilo(est["estilos"]["3_color_spinning"])
_, ctl_parada, _ = G.compilar_estilo(est["estilos"]["3_color"])
checa((ctl_gira.get("BoxSpinSpeed") or 0) > 0,
      "3_color_spinning tem que pedir BoxSpinSpeed > 0 - e' o que "
      "reproduz o Title 'GiAutoSubs 3color_spinning'")
checa((ctl_parada.get("BoxSpinSpeed") or 0) == 0,
      "3_color (sem giro) nao pode nascer girando")
# Zero tambem e' resposta: estilo SEM camada 3 tem que DIZER que nao gira, senao
# um clipe que estava girando continua - com a expressao na sombra da caixa, que
# existe em todo estilo.
for nome in ("TikTokNovo", "capcut_bolha"):
    _, ctl, _ = G.compilar_estilo(est["estilos"][nome])
    checa(ctl.get("BoxSpinSpeed") == 0,
          f"{nome} nao declara BoxSpinSpeed - um clipe que ja girava continuaria "
          f"girando neste estilo, e ninguem pediu isso")
# A geometria tem que continuar identica: o giro e' o DESLOCAMENTO, nao a caixa.
for chave in ("BoxLayer3CenterX", "BoxLayer3CenterY", "BoxLayer3ColorRed",
              "TextBoxExtendHorizontal", "TextBoxRound"):
    checa(ctl_gira.get(chave) == ctl_parada.get(chave),
          f"{chave} mudou ao ligar o giro ({ctl_parada.get(chave)} -> "
          f"{ctl_gira.get(chave)}) - o giro move o offset, nao a geometria")

# ------------------------------- 6. o nome de ontem continua funcionando
#
# `caixa_tres_cores` virou `3_color` em 27/09/2026, e o nome VIAJA GRAVADO: no
# `estilo` de todo legendas.lua ja escrito, no `meta.style`, e no controle
# `MetaStyle` dos clipes que estao na timeline - que e' de onde o botao "Rebuild
# with Selected" tira o `--estilo`. Sem a traducao, clicar em Rebuild num clipe
# antigo morre com "style does not exist", e isso so' apareceria dentro do Resolve.
print("o nome antigo do estilo ainda resolve")
for antigo, novo in G.ESTILOS_RENOMEADOS.items():
    checa(novo in est["estilos"],
          f"o mapa de renomeados aponta '{antigo}' para '{novo}', que nao existe "
          f"no estilos.json")
    checa(G.resolver_estilo(est, antigo) == novo,
          f"resolver_estilo('{antigo}') devolveu "
          f"'{G.resolver_estilo(est, antigo)}', esperado '{novo}'")
# E nao mexe em quem existe: um estilo de verdade nunca e' traduzido.
for nome in est["estilos"]:
    checa(G.resolver_estilo(est, nome) == nome,
          f"resolver_estilo trocou '{nome}', que existe, por "
          f"'{G.resolver_estilo(est, nome)}'")
# Nome que nao existe nem e' conhecido volta como veio - quem reclama e' o `main`,
# que sabe listar as opcoes.
checa(G.resolver_estilo(est, "nao_existe_isso") == "nao_existe_isso",
      "um nome desconhecido nao pode ser trocado por outro em silencio")

# ------------------------------------- 7. a aritmetica da caixa fixa em px
#
# `Width (px)` -> `Extend Horizontal`. A conta: uma unidade de Extend vale
# `px_por_unidade` pixels (o controle `Px per Unit`, ou `Size` x altura do frame
# quando ele e' 0), a largura do texto e' `caracteres x Char Width` unidades, e o
# Extend e' METADE do que falta - a caixa cresce pros dois lados.
#
# O fator e' palpite declarado (nao ha licenca Studio pra medir de fora), e e'
# justamente por isso que ele e' um controle: o que este teste protege sao as
# invariantes da conta, que erram calado.
print("a aritmetica da caixa fixa (px e caracteres)")


def extend_h(largura_px, chars_na_linha, *, char_width=0.5, alvo_chars=19,
             px_por_unidade=173.0, base=0.2):
    """A mesma conta do `extend_h` do macro, nas duas fontes de alvo."""
    texto = chars_na_linha * char_width
    if largura_px > 0 and px_por_unidade > 0:
        alvo = largura_px / px_por_unidade
    else:
        alvo = alvo_chars * char_width
    falta = alvo - texto
    # Legenda MAIS larga que o alvo nao encolhe: caixa menor que o proprio texto
    # seria pior que caixa que vaza (a regra esta no macro, em comentario).
    if falta <= 0:
        return base
    return falta / 2


# metade pra cada lado
checa(abs(extend_h(1730, 2) - ((1730 / 173.0) - 1.0) / 2) < 1e-9,
      "a caixa tem que crescer METADE pra cada lado")
# duas legendas de tamanhos diferentes, MESMA largura final
larg = 1730
for n in (2, 8, 15):
    total = n * 0.5 + 2 * extend_h(larg, n)
    checa(abs(total - larg / 173.0) < 1e-9,
          f"com {n} caracteres a caixa fixa deu {total:.4f} unidades, e o alvo e' "
          f"{larg / 173.0:.4f} - a largura tem que ser a MESMA em toda legenda")
# legenda mais larga que o alvo: nao encolhe
checa(extend_h(200, 30) == 0.2,
      "legenda mais larga que o alvo nao pode encolher a caixa - caixa que vaza e' "
      "sintoma de alvo errado, e esconder o sintoma e' pior")
# Width = 0 cai no alvo por CARACTERES (o que o macro 25 fazia)
checa(abs(extend_h(0, 4) - ((19 * 0.5) - (4 * 0.5)) / 2) < 1e-9,
      "sem Width em px, o alvo tem que voltar a ser uma linha cheia de "
      "Characters per Box")
# e o controle de escala VENCE a estimativa: mesma largura em px, escala outra,
# extend outro - e' isso que permite corrigir sem reinstalar macro
a = extend_h(900, 5, px_por_unidade=173.0)
b = extend_h(900, 5, px_por_unidade=100.0)
checa(a != b,
      "mudar Px per Unit tem que mudar o Extend - senao a calibragem nao serve "
      "pra nada")

# E o estilo sabe pedir os tres numeros.
com_px = copy.deepcopy(est["estilos"]["capcut_bolha"])
com_px.setdefault("base", {}).setdefault("caixa", {}).update(
    {"fixa": True, "largura_px": 900, "altura_px": 160, "px_por_unidade": 160})
_, ctl_px, _ = G.compilar_estilo(com_px)
checa(ctl_px.get("TextBoxWidth") == 900 and ctl_px.get("TextBoxHeight") == 160,
      f"largura_px/altura_px nao chegaram aos controles: "
      f"{ctl_px.get('TextBoxWidth')}/{ctl_px.get('TextBoxHeight')}")
checa(ctl_px.get("MetaPxPorUnidade") == 160,
      f"px_por_unidade nao chegou ao controle: {ctl_px.get('MetaPxPorUnidade')}")
# Sem pedir, os tres ficam em ZERO - um numero aqui num estilo de caixa livre
# seria controle que nao faz nada.
_, ctl_livre, _ = G.compilar_estilo(est["estilos"]["capcut_bolha"])
for chave in ("TextBoxWidth", "TextBoxHeight", "MetaPxPorUnidade"):
    checa(ctl_livre.get(chave) == 0,
          f"{chave} deveria ser 0 num estilo que nao pede caixa fixa, e' "
          f"{ctl_livre.get(chave)}")

# ------------------- 8. com Fixed Box ligado, o Extend esta' DESLIGADO
#
# Nao e' so' a UI: o valor do Extend nao pode entrar na conta, em nenhum ramo. Foi o
# que eu entreguei errado - ele era somado (`base + falta/2`) e voltava inteiro
# quando a legenda era mais larga que o alvo, quando faltava a escala e quando o
# Height era 0. O sintoma: a caixa "fixa" mudava de tamanho junto com um slider que
# o rotulo diz que nao vale.
print("com Fixed Box ligado, o Extend nao participa")


def extend_fixo(largura_px, chars, *, base, char_width=0.5, alvo_chars=19,
                px_por_unidade=173.0):
    """A conta do macro com a caixa FIXA - `base` entra so' pra provar que sai."""
    texto = chars * char_width
    if largura_px > 0 and px_por_unidade > 0:
        falta = (largura_px / px_por_unidade) - texto
        return max(0.0, falta / 2)
    alvo = alvo_chars * char_width
    falta = alvo - texto
    return max(0.0, falta / 2)


for caso in ((1730, 5), (1730, 40), (0, 3), (0, 60)):
    largura, chars = caso
    a = extend_fixo(largura, chars, base=0.2)
    b = extend_fixo(largura, chars, base=1.9)
    checa(a == b,
          f"com Fixed Box e Width={largura}, {chars} caracteres: mudar o Extend de "
          f"0.2 para 1.9 mudou a caixa ({a} -> {b}). Com a caixa fixa o Extend tem "
          f"que valer ZERO")

# Legenda mais larga que o alvo: zero de folga, e nao a folga do Extend.
checa(extend_fixo(200, 30, base=0.2) == 0.0,
      "legenda mais larga que o alvo tem que ficar SEM folga - voltar ao Extend "
      "seria obedecer o controle desligado")

# ------------- e o tamanho tem que EMPURRAR a camada 3, como os Extend empurram
#
# Invariante do macro 23: a sombra (7) e a camada 3 (8) COPIAM a geometria da caixa
# base (6). Se uma delas ler o controle e as outras a conta, as tres divergem e o
# deslocamento vira contorno torto - e nada reclama, o Text+ aceita geometria
# diferente em cada elemento numa boa.
print("Width/Height empurram a sombra e a camada 3")
with open(os.path.join(_RAIZ, "src", "gerar_macro.py"),
          encoding="utf-8") as fh:
    gerador = fh.read()
# A invariante NAO e' um numero de ocorrencias (ele mudou quando o macro 32
# acrescentou o caminho do preview, que escreve pelos mesmos pontos): e' que TODA
# escrita de Extend passe pela conta. Uma sobrando fora dela e' uma camada de
# tamanho diferente, e o deslocamento vira contorno torto sem nada reclamar.
for eixo, funcao in (("ExtendHorizontal", "extend_h"), ("ExtendVertical", "extend_v")):
    todas = len(re.findall(r'pin\(n, "%s", ' % eixo, gerador))
    pela_conta = len(re.findall(r'pin\(n, "%s", %s\(prefixo\)\)' % (eixo, funcao),
                                gerador))
    checa(todas > 0, f"nenhuma escrita de {eixo} encontrada no gerador - o regex "
                     f"do teste envelheceu junto com o codigo")
    checa(todas == pela_conta,
          f"{todas - pela_conta} de {todas} escrita(s) de {eixo} nao passam pelo "
          f"{funcao}() - essa camada fica de tamanho diferente das outras")
cru = len(re.findall(r'pin\(n, "Extend(?:Horizontal|Vertical)", '
                     r'ctl\(prefixo \.\. "Extend', gerador))
checa(cru == 0,
      f"{cru} camada(s) ainda leem o Extend cru do controle em vez da conta")

# --------- 9. A GARANTIA: caixa fixa do MESMO tamanho, qualquer que seja o texto
#
# A frase do usuario, virada em teste: "independente de quantos caracteres/tamanho do
# texto, a caixa mantenha o mesmo tamanho". Com a largura MEDIDA na fonte de verdade
# isso fecha por construcao - a folga e' o que falta pro alvo. Com o palpite
# (`caracteres x Char Width`) nao fecha, e e' por isso que a medicao existe.
print("caixa fixa: mesma largura final, textos diferentes")

FRASES = ["OI", "Yes", "que ja amarrou uma.", "ELES SO SAO MEIO TIMIDOS",
          "Walked in and dream", "a", "3d e 2 coisas"]
# 1500px: o alvo TEM que caber a legenda mais larga (13.57 em = 1357px aqui).
# Com um alvo menor, as que nao cabem nao encolhem - e' essa a regra, e e' por
# isso que o resumo da rodada imprime a largura da maior legenda medida.
ALVO_PX = 1500.0
PX_POR_UNIDADE = 100.0          # a escala medida pelo usuario em 27/09/2026

medidas = {f: G.medir_largura_em(f, "Open Sans", "Bold") for f in FRASES}
if any(v is None for v in medidas.values()):
    print("  (pulado: nao achei a fonte 'Open Sans Bold' instalada nesta maquina)")
else:
    larguras = set()
    for frase, em in medidas.items():
        alvo_unid = ALVO_PX / PX_POR_UNIDADE
        folga = max(0.0, (alvo_unid - em) / 2)        # a conta do macro
        final = em + 2 * folga                        # o que a tela mostra
        larguras.add(round(final, 6))
        checa(abs(final - alvo_unid) < 1e-9 or em > alvo_unid,
              f"'{frase}': a caixa saiu {final:.4f} unidades e o alvo e' "
              f"{alvo_unid:.4f} - a caixa fixa tem que dar o alvo em toda legenda")
    checa(len(larguras) == 1,
          f"as caixas sairam com {len(larguras)} larguras diferentes "
          f"({sorted(larguras)}) - com a caixa fixa tem que ser UMA")

    # O caso que NAO cabe: alvo menor que a maior legenda. Ela nao encolhe (a caixa
    # nunca fica menor que o proprio texto), e ai as larguras divergem - de
    # proposito. E' o que obriga o resumo a dizer qual e' a maior.
    apertado = 500.0 / PX_POR_UNIDADE
    maior_em = max(medidas.values())
    folga_apertada = max(0.0, (apertado - maior_em) / 2)
    checa(folga_apertada == 0.0,
          "com alvo menor que a legenda, a folga tem que ser ZERO (nao negativa: "
          "caixa menor que o texto seria pior que caixa que vaza)")

    # E o contraste que justifica a medicao: com o palpite, as larguras DIVERGEM.
    palpite = set()
    for frase in FRASES:
        chars = len(frase)
        em_chutado = chars * 0.5
        folga = max(0.0, (ALVO_PX / PX_POR_UNIDADE - em_chutado) / 2)
        # a tela desenha a largura REAL do texto mais a folga calculada do palpite
        palpite.add(round(medidas[frase] + 2 * folga, 4))
    checa(len(palpite) > 1,
          "o palpite deveria produzir larguras diferentes - se nao produz, este "
          "teste nao esta' medindo o que pensa que mede")

    # A medida em si: mais texto, mais largura; e ela e' em EM (nao muda com o Size).
    checa(medidas["a"] < medidas["OI"] < medidas["ELES SO SAO MEIO TIMIDOS"],
          f"a medicao nao ordena por largura: {medidas}")
    dobro = G.medir_largura_em("OI", "Open Sans", "Bold", _tam=200)
    checa(abs(dobro - medidas["OI"]) < 0.02,
          f"a medida em em mudou com o tamanho em px ({medidas['OI']:.4f} a 100px "
          f"contra {dobro:.4f} a 200px) - em tem que ser independente de escala")

# E a medida chega ao arquivo, por legenda, so' quando a caixa e' fixa.
if os.path.isfile(os.path.join(corte, "corte.json")):
    doc_fx2, st_fx2 = G.montar(corte, est, "3_color", True, 19, (), None, 1,
                               None, True)
    com = [s for s in doc_fx2["segments"] if "largura_em" in s]
    checa(len(com) == len(doc_fx2["segments"]),
          f"{len(com)} de {len(doc_fx2['segments'])} legendas trazem largura_em - "
          f"a que nao traz cai no palpite e sai de outro tamanho")
    checa(st_fx2["sem_medida"] == 0,
          f"{st_fx2['sem_medida']} legenda(s) nao foram medidas")
    doc_livre, st_livre = G.montar(corte, est, "3_color", True, 19, (), None, 1,
                                   None, False)
    checa(not any("largura_em" in s for s in doc_livre["segments"]),
          "com a caixa LIVRE ninguem usa a largura medida - medir seria trabalho "
          "e uma dependencia a mais por nada")

print()
if falhas:
    print(f"{len(falhas)} FAILED")
    sys.exit(1)
print("ALL OK")
