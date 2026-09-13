r"""GiAutoSubs - lado Python: transcricao + diarizacao + estilos -> legendas.json

O que este arquivo NAO faz
--------------------------
Ele nao fala com o Resolve. Ele so produz o `legendas.json` que o
`GiAutoSubs.lua` le de dentro do Resolve. A separacao existe porque o Resolve
roda Lua e nao tem as suas dependencias, e porque assim da' pra conferir o
resultado sem abrir o Resolve.

Por que nao usar o AutoSubs direto
----------------------------------
O AutoSubs refaz transcricao e diarizacao do zero. Voce ja tem as duas coisas,
e a diarizacao ja foi revisada na mao (`turnsManual.json`) - jogar isso fora
seria o passo mais caro do processo. Aqui a gente reaproveita.

A diferenca de verdade esta no destaque: o macro deles anima UM elemento do
Text+ por vez, entao a palavra falada pode ter bolha OU cor diferente, nunca
bolha COM sombra. O Text+ tem 8 elementos e o macro so usa 4, entao o
GiAutoSubs escreve tambem no elemento 5 e a bolha ganha sombra propria.

Uso
---
    python giautosubs.py <pasta_do_corte>
    python giautosubs.py <pasta_do_corte> --estilo limpo_sem_bolha
    python giautosubs.py <pasta_do_corte> --sem-words
"""

import argparse
import json
import os
import sys

from estilo_legenda import quebrar

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTILOS_PADRAO = os.path.join(_RAIZ, "estilos.json")

# Text+ desenha o elemento 1 na frente e os maiores atras. O AutoSubs usa
# 1..4; 5..8 ficam livres, e e' dai que sai a sombra da bolha.
ELEM_FILL, ELEM_OUTLINE, ELEM_SOMBRA = 1, 2, 3
ELEM_CX_DESTAQUE, ELEM_CX_DESTAQUE_SOMBRA = 4, 5   # caixa da palavra falada
ELEM_CX_BASE, ELEM_CX_BASE_SOMBRA = 6, 7           # caixa do texto todo
# 8 fica livre

# Level do Text+: em que granularidade o elemento e' desenhado. O macro do
# AutoSubs usa 2 pra bolha, com o comentario "character level looks bad" - e o
# `SelectElement = 1` do proprio macro, que seleciona o elemento 1, confirma
# que os combos do Text+ contam a partir de 1, nao de 0.
NIVEIS = {"caractere": 1, "palavra": 2, "linha": 3, "tudo": 4}

# `fonte.caixa_das_letras` do estilo -> o combo `TextCase` do macro. A ordem e'
# a mesma la e aqui, e a ordem E' o valor gravado - ver o `Level` invertido na
# secao 8 do ESTADO.md pra saber o que acontece quando as duas discordam.
CAIXA_DAS_LETRAS = {"normal": 0, "minusculas": 1, "maiusculas": 2}

# Nome do controle do macro que corresponde a cada caixa. Existe porque o
# estilo agora e' escrito em DOIS lugares: nos inputs crus do Text+ (quem
# desenha) e nos controles do Inspector (o que voce ve e edita depois). Manter
# os dois em sincronia e' o que impede o Inspector de mostrar uma cor e a tela
# outra - e e' tambem o que impede um clique em "Update Fill Color" de reverter
# o que o script acabou de escrever.
CTRL_CAIXA = {ELEM_CX_DESTAQUE: "Bubble", ELEM_CX_BASE: "TextBox"}

# Valor de `ElementShape` que significa "Border Fill".
#
# O Appearance do Text+ e' Text Fill / Text Outline / Border Fill / Border
# Outline, contando de ZERO. O mapeamento nao e' chute: saiu do dump dentro do
# Resolve, lendo os defaults de fabrica de volta -
#
#     elemento 1 "White Solid Fill" -> 0
#     elemento 2 "Red Outline"      -> 1
#     elemento 4 "Blue Border"      -> 3
#
# Uma caixa/bolha e' um retangulo PREENCHIDO, entao 2. (A versao anterior
# "calibrava" lendo o elemento 4 e pegava 3, que e' CONTORNO de caixa.)
FORMA_BORDA = 2

# Versao do macro. Sobe a cada mudanca que o script precise "ver" no macro.
#
# Existe por causa de um dia inteiro perdido: o Resolve guarda uma COPIA do
# macro dentro do projeto quando o titulo entra no Media Pool. Reinstalar o
# .setting em Templates/Edit/Titles nao atualiza essa copia - o script continua
# criando clipes a partir do macro velho, e o sintoma e' "consertei e nao mudou
# nada". O numero e' gravado no macro e conferido pelo GiAutoSubs.lua, que para
# e diz o que fazer em vez de produzir 129 legendas erradas.
# 4: botoes "Update ..." removidos, aba Style escondida, keyframes de exemplo
#    apagados do spline. As duas primeiras SO existem no macro - nenhuma delas
#    da' pra consertar em tempo de execucao, entao aqui o carimbo tem que subir
#    e forcar a reimportacao. (Subir isso sem necessidade custa uma
#    reimportacao manual ao usuario; nao suba por mudanca que o script conserta
#    sozinho.)
# 5: ApplyGiStyle passa a escrever no Follower1 (sem isso o seletor de cor da
#    bolha nao mudava nada na tela), GiRebuildHighlight (refaz os keyframes pra
#    a cor alcancar um elemento animado), checkbox GiDebug, e o spline do
#    character-level styling volta a ter UM keyframe - com zero, o Fusion nao
#    conseguia avaliar o parametro e a legenda nao renderizava.
#    Tudo isso mora no macro; nada disso o script conserta em execucao.
# 6: log por atributo (cada controle diz seu nome e qual rotina rodou), e as
#    duas economias que tiraram a demora do Inspector: nao reescrever input que
#    ja esta com o valor certo, e so refazer o spline quando o controle mexido
#    realmente vive nele. Tambem: callback que nao acha a rotina agora RECLAMA
#    em vez de sair calado - o silencio custou uma sessao inteira de caca.
# 7: o log do macro tambem vai pra arquivo (`_gimacro.log`), porque o Console do
#    Resolve nao deixa copiar log longo - ele rola pra fora antes.
# 8: o par `GetInputValues`/`SetInputValues` volta a ser o contrato do macro, e
#    o `InputKeys` passa a listar os NOSSOS controles. Todo controle - os do
#    AutoSubs e os nossos - passa a chamar `SetInputValues`, que decide entre
#    animacao e estilo e termina em UpdateAllStyleColors -> ApplyGiStyle. Um
#    caminho de escrita so'. O schema do estilo deixa de estar espalhado entre
#    tres arquivos e passa a morar no macro: controle novo entra em `InputKeys`
#    e nada mais muda. Nada disso o script conserta em execucao - o carimbo sobe.
# 9: botao "Apply Style" no Inspector (dispara o MESMO SetInputValues a mao, pro
#    caso em que o callback nao roda), e os rotulos do Inspector passaram todos
#    pro ingles - a convencao do projeto e' comentario em portugues, UI em
#    ingles, e os controles novos tinham nascido fora dela. Controle e rotulo
#    moram no macro; o script nao poe um botao num clipe que ja existe.
# 10: conserto de um erro do 9. Ao fazer todo callback entrar pelo
#    SetInputValues, TODO controle passou a acordar o UpdateAllStyleColors -
#    inclusive BubbleRound e BoxShadowSoftness, que nao tocam em fill/outline/
#    shadow. Eram 26 comparacoes e uma linha de log por disparo, sempre
#    `0 written`, vezes ~40 disparos por arrasto. Agora a origem escolhe o dono
#    (mesmo raciocinio da NO_SPLINE, uma camada acima). Junto: o `_gimacro.log`
#    ganhou teto de 2 MB - ele tinha passado disso.
# 11: o Apply Style vira o UNICO caminho, e os callbacks por controle acabam.
#    Dois motivos, os dois medidos no log: (a) o `tool` que o Fusion entrega pro
#    callback e pro botao e' o Text+ interno, mas o codigo mora no CustomData do
#    MacroOperator - `tool:GetData("SetInputValues")` volta nil SEMPRE, e era
#    esse o "Apply Style: nothing was applied"; agora as rotinas sao procuradas
#    na comp inteira (`gi_chunk`). (b) `INPS_ExecuteOnChange` dispara a cada
#    valor intermediario de slider (~40 por ajuste), e metade dos disparos so'
#    sabia imprimir erro - o log ficava ilegivel. Sem callback, um clique = um
#    bloco de log. Saiu junto tudo que existia pra amortecer os 40 disparos
#    (tabelas ANIMACAO, ESTILO_BASE, NO_SPLINE) e o checkbox GiDebug. O grupo
#    Actions passa a abrir o Inspector.
# 12: os dois atributos que continuavam sem reagir ao Apply Style.
#    (a) O Inspector do CLIPE edita os `InstanceInput` do MacroOperator, nao os
#    UserControls do Text+. As rotinas liam so' do Text+, achavam o valor VELHO,
#    e reescreviam o velho por cima - `0 written` no log com o controle na tela
#    mostrando outra coisa. Agora leem na ordem macro -> tool -> Text+
#    (`gi_macro`), e o `SetInputValues` escreve nos dois pra ninguem mais
#    precisar adivinhar qual esta em dia.
#    (b) O checkbox da bolha nao desligava nada: `Enabled` de camada ANIMADA vem
#    do array do spline, que era refeito a partir do `on_base`/`on_ativo`
#    gravados no clipe quando ele nasceu. O array vence o input, entao o
#    `Enabled4 = 0` durava ate o keyframe seguinte. O `GiRebuildHighlight` agora
#    consulta os checkboxes (tabela `LIGA`).
#    Junto: o grupo Actions desceu pra logo abaixo do grupo "Text", e a bolha do
#    `capcut_bolha` virou preta com opacidade 0.3.
# 13: `BubbleOpacity` passa a valer, e a palavra falada ganha seletor de cor.
#    A opacidade nao funcionava porque `Opacity1..4` chegam no Follower1
#    CONECTADAS ao AnimationKeyframeStretcher (e' assim que o fade do AutoSubs e'
#    feito), e o Follower vence o Text+: o valor era escrito e ignorado. Agora a
#    bolha desconecta antes de escrever - o mesmo gesto do `RemoveFade` deles -
#    e volta pro fade se a opacidade voltar pra 1. Os elementos 1..3 continuam
#    conectados: la a conexao E' o fade do texto.
#    E o `WordFill*` (grupo "Spoken Word"): a cor da palavra falada era o unico
#    atributo do destaque sem controle no Inspector, porque o elemento 1 fica
#    fora do CONTROLE_DA_CAMADA - a cor BASE dele e' a do falante. O controle
#    entra so' pela cor ATIVA, entao a cor de cada pessoa continua valendo nas
#    outras palavras. Se o estilo nao tiver camada de fill (o `capcut_bolha` nao
#    tem), o GiRebuildHighlight cria uma, com a cor base lida do proprio Text+.
# 14: o "pop" da bolha - ela entra menor nos dois eixos e cresce, a cada palavra
#    (o efeito do CapCut). Rotina propria (`GiBubblePop`) porque nao existe
#    escala por elemento no Text+: quem faz o tamanho e' o par
#    ExtendHorizontal/ExtendVertical, que sao inputs GLOBAIS - e animar um input
#    global funciona aqui porque num instante qualquer so' existe UMA bolha na
#    tela (o array acende a da palavra falada e apaga as outras).
#    Separada do GiRebuildHighlight de proposito: o script escreve o array ele
#    mesmo e manda o rebuild pular, mas quer o pop do mesmo jeito.
# 15: `Case` (As typed / lowercase / UPPERCASE), no grupo "Text" logo abaixo de
#    `Style` - caixa das letras e' tipografia, irma de Font/Style/Size. Combo de
#    tres estados em vez de dois checkboxes: o estado "os dois marcados" nao
#    existe. A transformacao NAO e' destrutiva (o texto digitado fica em
#    `GiTextOriginal` e a caixa sai sempre dele), e um texto editado a mao no
#    Inspector vira o novo original - sem isso, clicar Apply Style depois de
#    corrigir uma palavra devolveria a legenda ao texto antigo.
#    `string.upper` do Lua e' ASCII: sem tratar o bloco Latin-1 do UTF-8,
#    "acao" com cedilha viraria "ACaO" com cedilha minusculo.
# 16: os combos nasciam VAZIOS - e' por isso que o `Case` "nao funcionava".
#    As opcoes (`{ CCS_AddString = ... }`) eram enfiadas com um `replace` na
#    linha do `INPS_ExecuteOnChange`; quando os callbacks sairam (macro 11) essa
#    linha deixou de existir, o replace parou de casar e nao reclamou. Os dois
#    `Level` estavam assim desde entao, sem ninguem notar. Agora as opcoes
#    entram na montagem do bloco e o validador recusa combo vazio.
#    Junto: botao "Display Config" (grupo Config, no fim do Inspector) - imprime
#    o estilo do clipe no Console e grava em `_giconfig.txt`, lendo pelo mesmo
#    `GetInputValues` que o script usa.
# 17: o `Case` mudava o campo Text e nao a tela. O que o Text+ RENDERIZA nao e'
#    o `Text` dele: o `StyledText` vem conectado ao Follower1, que vem do
#    CharacterLevelStyling1 - e o texto de verdade e' o `Text` do CLS1. O
#    `GiAutoSubs.lua` ja escrevia nos dois desde sempre; era o `GiApplyCase` que
#    estava a meio caminho. Junto: o Display Config imprimia `table: 0x...` nos
#    inputs de par (Position/Offset) - agora imprime `{ x, y }`.
# 18: editar o texto no campo `Text` do Inspector nao mudava a legenda. Mesma
#    raiz do 17, outro caminho: quem sincronizava o Text+ com o
#    CharacterLevelStyling1 era o `UpdateTextContent` do AutoSubs - uma das seis
#    rotinas que este macro DESARMA. Sem ela ninguem propagava, e o Apply Style
#    tambem nao, porque a rotina de texto comparava so' com o Text+ e concluia
#    "ja esta certo" enquanto o CLS1 seguia com o texto velho. Agora ela compara
#    POR ALVO (por isso virou `GiApplyText`), e avisa quando o texto editado tem
#    tamanho diferente do que o destaque por palavra foi montado pra cobrir.
# 19: animacao de entrada do AutoSubs desligada de fabrica - `AnimationLevel = 0`
#    ("Segment Level"; o combo e' 0-based e, ao contrario dos `Level` do Text+,
#    NAO esta invertido) e Fade/PopIn/SlideUp em 0. Os checkboxes sozinhos nao
#    apagavam nada: quem le eles e' o `SetAnimations`, que so' roda no botao
#    Apply Style, e o fade e' um SPLINE ligado nas `Opacity1..4` do Follower1.
#    Entao o `gerar_macro.py` achata esse spline em 1 constante - o mesmo estado
#    que o `SetAnimations` produz com o fade desligado, e sem cortar a conexao
#    (o `opacidade_da_bolha` do ApplyGiStyle precisa dela pra devolver a bolha
#    ao stretcher). Mora no macro; o script nao conserta clipe que ja existe.
MACRO_VERSAO = 19

# Inputs de elemento que precisam ser escritos TAMBEM no Follower1.
#
# O StyledTextFollower e' um modificador que gera o StyledText do Text+, e os
# inputs de elemento que ELE tem sobrescrevem os do Text+ caractere a
# caractere. O macro do AutoSubs vem com `Red2 = 0.929, Green2 = 0.051,
# Thickness2 = 0.8, Softness1..8 = 1` la dentro - entao escrever a cor do
# outline so' no Text+ nao muda nada na tela. E' por isso que o
# UpdateAllStyleColors deles escreve nos DOIS tools.
#
# `Opacity{n}` fica de fora de proposito: no Follower1 as opacidades 1..4 estao
# CONECTADAS ao AnimationKeyframeStretcher, e escrever um valor por cima
# arrebentaria o fade.
CHAVES_DO_FOLLOWER = ("Enabled", "Red", "Green", "Blue", "Thickness", "Softness")


# ------------------------------------------------------------------ estilos

def _merge(base, novo):
    """Merge recursivo - `herda` precisa juntar dicionarios aninhados, senao
    um estilo que so quer trocar a cor perderia o resto do bloco."""
    out = dict(base)
    for k, v in novo.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def carregar_estilos(caminho):
    with open(caminho, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    estilos = cfg.get("estilos") or {}
    # resolve `herda` uma vez, na carga, pra ninguem precisar pensar nisso depois
    resolvidos = {}
    for nome in estilos:
        cadeia, atual, visto = [], nome, set()
        while atual and atual not in visto:
            visto.add(atual)
            cadeia.append(estilos[atual])
            atual = estilos[atual].get("herda")
        acc = {}
        for parte in reversed(cadeia):
            acc = _merge(acc, parte)
        acc.pop("herda", None)
        resolvidos[nome] = acc
    cfg["estilos"] = resolvidos
    return cfg


def _rgb(hexa):
    h = (hexa or "#FFFFFF").lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _direcao(bloco):
    """{"direcao": {"x":.., "y":..}} -> (x, y). Aceita tambem a forma antiga
    "offset": [x, y]."""
    d = bloco.get("direcao")
    if isinstance(d, dict):
        return (d.get("x", 0.0), d.get("y", 0.0))
    off = bloco.get("offset")
    if isinstance(off, (list, tuple)) and len(off) >= 2:
        return (off[0], off[1])
    return None


def _geometria(inputs, n, extend_h, extend_v, round_):
    """Forma da caixa. Sombra e caixa precisam da MESMA geometria, senao a
    sombra sai de tamanho diferente e denuncia o truque.

    Nada disto vale para um elemento de TEXTO: `Level`, `ExtendHorizontal`,
    `ExtendVertical` e `Round` sao propriedades de BORDA. Quem troca a forma e'
    a chave `_borda{n}` (ver `_elemento`) - sem ela o Text+ aceita estes
    inputs e nao desenha caixa nenhuma.
    """
    inputs[f"ExtendHorizontal{n}"] = extend_h
    inputs[f"ExtendVertical{n}"] = extend_v
    inputs[f"Round{n}"] = round_


def _elemento(inputs, n, cor=None, opacidade=None, suavidade=None,
              espessura=None, offset=None, nivel=None, ativo=True,
              borda=False):
    """Escreve um elemento de sombreamento do Text+ com sufixo numerico."""
    inputs[f"Enabled{n}"] = 1 if ativo else 0
    if not ativo:
        return
    if borda:
        # O input e' `ElementShape{n}` ("Appearance" no Inspector: Text Fill /
        # Text Outline / Border Fill / Border Outline). Os elementos 1..4 do
        # Text+ nascem dos presets de fabrica - o 4 e' "Blue Border", que ja e'
        # borda, e e' por isso que a bolha do AutoSubs funciona sem ninguem
        # tocar nisso. Os elementos 5..8 nascem como TEXTO: era essa a caixa
        # que nunca aparecia.
        #
        # O VALOR nao vai daqui. Quem resolve e' o Lua, lendo a forma do
        # elemento 4 dentro do Resolve - chutar o numero ja custou tres
        # rodadas nesta historia, e o Text+ aceita numero errado calado.
        inputs[f"_borda{n}"] = True
    if cor is not None:
        r, g, b = _rgb(cor)
        inputs[f"Red{n}"], inputs[f"Green{n}"], inputs[f"Blue{n}"] = r, g, b
    if opacidade is not None:
        inputs[f"Opacity{n}"] = opacidade
    if suavidade is not None:
        inputs[f"Softness{n}"] = suavidade
    if espessura is not None:
        inputs[f"Thickness{n}"] = espessura
    if nivel is not None:
        inputs[f"Level{n}"] = nivel
    # Deslocamento zero e' o mesmo que nao deslocar, e escrever mesmo assim
    # nao e' inofensivo: foi tocando nesse input a toa que o outline com
    # (0,0) foi parar no canto da tela. Se nao ha o que mover, nao mexe.
    if offset and (abs(offset[0]) > 1e-9 or abs(offset[1]) > 1e-9):
        # Nao ha input separado de X e Y: o Text+ recebe um ponto. O nome do
        # input varia entre versoes, entao quem resolve isso e' o Lua - aqui
        # so vai o par, com a chave marcada pra ele achar.
        inputs[f"_offset{n}"] = [offset[0], offset[1]]


def _caixa_e_sombra(inputs, controles, n_caixa, n_sombra, caixa, box_shadow,
                    nivel_padrao, geo_padrao, cor_padrao):
    """Uma caixa e a sombra dela - os dois elementos sempre juntos.

    Bolha (4+5) e caixa do texto (6+7) sao a MESMA coisa em posicoes
    diferentes da pilha, entao a regra mora num lugar so. As duas escrevem
    tambem no controle do Inspector correspondente ("Bubble" / "TextBox"),
    pra o painel nao mostrar uma coisa e a tela outra.

    Devolve (caixa_ligada, sombra_ligada).
    """
    pref = CTRL_CAIXA[n_caixa]
    on = bool(caixa.get("ativo"))
    controles[f"{pref}Enabled"] = 1 if on else 0

    # O "pop" (a bolha entra menor e cresce) so' existe na BOLHA: ele acontece a
    # cada palavra, e a caixa do texto fica ligada o tempo todo - nao ha entrada
    # pra animar. Fica fora do `if not on` pra o controle existir no macro mesmo
    # com a bolha desligada, senao nao daria pra ligar as duas coisas pelo
    # Inspector.
    if n_caixa == ELEM_CX_DESTAQUE:
        pop = caixa.get("pop") or {}
        controles.update({
            "BubblePopEnabled": 1 if pop.get("ativo") else 0,
            "BubblePopAmount": pop.get("quantidade", 0.15),
            "BubblePopFrames": pop.get("frames", 3),
        })

    if not on:
        inputs[f"Enabled{n_caixa}"] = 0
        inputs[f"Enabled{n_sombra}"] = 0
        controles["BoxShadowOnHighlight" if n_caixa == ELEM_CX_DESTAQUE
                  else "BoxShadowOnNormal"] = 0
        return False, False

    nivel = NIVEIS.get(caixa.get("nivel", nivel_padrao), 2)
    geo = (caixa.get("extend_h", geo_padrao[0]),
           caixa.get("extend_v", geo_padrao[1]),
           caixa.get("round", geo_padrao[2]))
    cor = caixa.get("cor", cor_padrao)
    opac = caixa.get("opacidade", 1)

    # `borda=True`: sem trocar a forma do elemento, Level/Extend/Round sao
    # aceitos e ignorados - e' o motivo de a caixa nunca ter aparecido.
    _elemento(inputs, n_caixa, cor=cor, opacidade=opac, nivel=nivel, borda=True)
    _geometria(inputs, n_caixa, *geo)

    r, g, b = _rgb(cor)
    controles.update({
        f"{pref}ColorRed": r, f"{pref}ColorGreen": g, f"{pref}ColorBlue": b,
        f"{pref}Opacity": opac, f"{pref}Level": nivel,
        f"{pref}ExtendHorizontal": geo[0], f"{pref}ExtendVertical": geo[1],
        f"{pref}Round": geo[2],
    })

    bs = box_shadow or {}
    sombra_on = bool(bs.get("ativo"))
    controles["BoxShadowOnHighlight" if n_caixa == ELEM_CX_DESTAQUE
              else "BoxShadowOnNormal"] = 1 if sombra_on else 0
    if not sombra_on:
        inputs[f"Enabled{n_sombra}"] = 0
        return True, False

    direcao = _direcao(bs) or (0.005, -0.007)
    _elemento(inputs, n_sombra, cor=bs.get("cor", "#000000"),
              opacidade=bs.get("opacidade", 0.55),
              suavidade=bs.get("suavidade", 2),
              offset=direcao, nivel=nivel, borda=True)
    # mesma geometria da caixa, senao a sombra nao encaixa nela
    _geometria(inputs, n_sombra, *geo)

    sr, sg, sb = _rgb(bs.get("cor", "#000000"))
    controles.update({
        "BoxShadowColorRed": sr, "BoxShadowColorGreen": sg,
        "BoxShadowColorBlue": sb,
        "BoxShadowOpacity": bs.get("opacidade", 0.55),
        "BoxShadowSoftness": bs.get("suavidade", 2),
        "BoxShadowCenterX": direcao[0], "BoxShadowCenterY": direcao[1],
    })
    return True, True


def compilar_estilo(estilo):
    """Estilo do JSON -> inputs do Text+ + controles do Inspector + destaque.

    Sao tres saidas porque sao tres consumidores diferentes:

      inputs      os inputs crus do Text+, que e' quem de fato desenha
      controles   os controles do macro, que e' o que voce ve e mexe depois
      destaque    o que so existe como keyframe por palavra, resolvido no Lua

    Os dois primeiros dizem a mesma coisa de proposito. O macro do AutoSubs
    tem rotinas que reescrevem o Text+ a partir dos controles; enquanto os
    dois nao contavam a mesma historia, quem escrevesse por ultimo ganhava - e
    quem escrevia por ultimo era o macro, com as cores de exemplo dele.
    """
    fonte = estilo.get("fonte") or {}
    base = estilo.get("base") or {}
    dest = estilo.get("destaque") or {}

    inputs = {
        "Font": fonte.get("familia", "Poppins"),
        "Style": fonte.get("estilo", "SemiBold"),
        "Size": fonte.get("tamanho", 0.09),
        "Center": list((estilo.get("posicao") or {}).get("centro", [0.5, 0.22])),
    }
    # A caixa das letras e' aplicada pelo MACRO (`GiApplyCase`), nao aqui: assim
    # ela vale tambem pro titulo arrastado da aba Effects, e continua reversivel
    # - o texto original fica guardado no clipe.
    controles = {"TextCase": CAIXA_DAS_LETRAS.get(
        str(fonte.get("caixa_das_letras", "normal")).lower(), 0)}

    f = base.get("fill") or {}
    _elemento(inputs, ELEM_FILL, cor=f.get("cor", "#FFFFFF"),
              ativo=f.get("ativo", True))
    fr, fg, fb = _rgb(f.get("cor", "#FFFFFF"))
    controles.update({"FillEnabled": 1 if f.get("ativo", True) else 0,
                      "FillColorRed": fr, "FillColorGreen": fg,
                      "FillColorBlue": fb})

    o = base.get("outline") or {}
    _elemento(inputs, ELEM_OUTLINE, cor=o.get("cor", "#000000"),
              espessura=o.get("espessura", 0.08), suavidade=o.get("suavidade", 1),
              offset=_direcao(o), ativo=o.get("ativo", True))
    or_, og, ob = _rgb(o.get("cor", "#000000"))
    controles.update({"OutlineEnabled": 1 if o.get("ativo", True) else 0,
                      "OutlineThickness": o.get("espessura", 0.08),
                      "OutlineColorRed": or_, "OutlineColorGreen": og,
                      "OutlineColorBlue": ob})

    s = base.get("sombra") or {}
    _elemento(inputs, ELEM_SOMBRA, cor=s.get("cor", "#000000"),
              opacidade=s.get("opacidade", 0.5), suavidade=s.get("suavidade", 1),
              offset=_direcao(s), ativo=s.get("ativo", False))
    sr, sg, sb = _rgb(s.get("cor", "#000000"))
    controles.update({"ShadowEnabled": 1 if s.get("ativo", False) else 0,
                      "ShadowColorRed": sr, "ShadowColorGreen": sg,
                      "ShadowColorBlue": sb})

    # ---- caixa do texto todo (fora do destaque): elementos 6 e 7 ----------
    # Estatica: fica ligada o tempo inteiro, sem keyframe nenhum.
    _caixa_e_sombra(inputs, controles, ELEM_CX_BASE, ELEM_CX_BASE_SOMBRA,
                    base.get("caixa") or {}, base.get("box_shadow"),
                    "linha", (0.2, 0.12, 0.25), "#000000")

    # ---- destaque: uma LISTA de camadas, nao um elemento so ---------------
    # Antes o destaque animava um unico elemento, entao "fill rosa" e "caixa
    # atras da palavra" eram mutuamente exclusivos. Cada camada carrega o
    # estado ativo E o inativo, e o Lua monta o keyframe com todas juntas.
    camadas = []
    # A cor da palavra falada tambem vira CONTROLE (`WordFill*`), e nao so'
    # keyframe: sem isso ela era o unico atributo do destaque sem seletor no
    # Inspector - dava pra mudar a bolha clicando, mas a cor da palavra so'
    # editando o JSON e rodando o script de novo.
    #
    # Ele fica fora do laco de camadas de proposito: mesmo com o fill do
    # destaque desligado (o `capcut_bolha` e' assim), o controle tem que existir
    # no macro pra voce poder LIGAR pelo Inspector. Quem cria a camada nesse
    # caso e' o `GiRebuildHighlight`.
    cor_palavra = _rgb((dest.get("fill") or {}).get("cor")
                       or dest.get("cor", "#FF4DA6"))
    fill_dest_on = (dest.get("ativo", True)
                    and (dest.get("fill") is None
                         or (dest.get("fill") or {}).get("ativo", True)))
    controles.update({
        "WordFillEnabled": 1 if fill_dest_on else 0,
        "WordFillColorRed": cor_palavra[0],
        "WordFillColorGreen": cor_palavra[1],
        "WordFillColorBlue": cor_palavra[2],
    })

    if dest.get("ativo", True):
        if fill_dest_on:
            camadas.append({
                "elemento": ELEM_FILL,
                "cor_ativa": cor_palavra,
                "cor_base": _rgb(f.get("cor", "#FFFFFF")),
                # o fill fica aceso sempre: o que muda na palavra falada e' a cor
                "on_ativo": 1, "on_base": 1,
            })

        cxd = dest.get("caixa") or {}
        # LIGADA no template de proposito: o Text+ so aceita styling por
        # caractere em elemento habilitado. Quem apaga a caixa nas palavras
        # nao faladas e' o array de keyframes. Deixar 0 aqui = caixa que
        # nunca aparece. (E' a mesma observacao que esta no ApplyHighlight do
        # AutoSubs: "Bubble must be enabled at the template level".)
        caixa_on, sombra_on = _caixa_e_sombra(
            inputs, controles, ELEM_CX_DESTAQUE, ELEM_CX_DESTAQUE_SOMBRA,
            cxd, dest.get("box_shadow"), "palavra", (0.15, 0.1, 0.4), "#FFD84D")

        if caixa_on:
            camadas.append({
                "elemento": ELEM_CX_DESTAQUE,
                "cor_ativa": _rgb(cxd.get("cor", "#FFD84D")),
                "cor_base": _rgb(cxd.get("cor", "#FFD84D")),
                "on_ativo": 1, "on_base": 0,
            })
        if sombra_on:
            cor_bs = (dest.get("box_shadow") or {}).get("cor", "#000000")
            camadas.append({
                "elemento": ELEM_CX_DESTAQUE_SOMBRA,
                "cor_ativa": _rgb(cor_bs),
                "cor_base": _rgb(cor_bs),
                "on_ativo": 1, "on_base": 0,
            })

    return inputs, controles, ({"camadas": camadas} if camadas else None)


# ------------------------------------------------------- transcricao/turnos

def pasta_dos_scripts():
    """Onde moram 4_transcribe_whisper.py e companhia.

    Sai do config.json em vez de vir escrito aqui: e' a mesma pasta que o app
    usa, e uma copia divergente vira uma instrucao que nao roda.
    """
    padrao = r"D:\CanalYtbe\BatataQuente\scriptsPrimarios"
    try:
        with open(os.path.join(_RAIZ, "config.json"), encoding="utf-8-sig") as fh:
            return json.load(fh).get("scripts_dir") or padrao
    except (OSError, ValueError):
        return padrao


def _ler_json(caminho):
    # utf-8-sig: JSON escrito por ferramenta da Microsoft costuma vir com BOM,
    # e o parser padrao recusa
    with open(caminho, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def falante_de(seg, turnos):
    """Quem cobre mais tempo do segmento - mesma regra do captions.py.

    Nao e' quem comeca junto: uma legenda que atravessa a troca de falante
    ficaria com o nome errado por causa de 100 ms.
    """
    s, e = float(seg["start"]), float(seg["end"])
    melhor, melhor_ov = None, 0.0
    for t in turnos:
        ov = min(e, float(t["end"])) - max(s, float(t["start"]))
        if ov > melhor_ov:
            melhor, melhor_ov = t.get("name"), ov
    return melhor


def _hexa(bloco, padrao="#FFFFFF"):
    return (bloco or {}).get("cor", padrao)


def _fmt_dir(bloco):
    d = _direcao(bloco or {})
    return f"x={d[0]:+.4f} y={d[1]:+.4f}" if d else "no offset"


def resumo_estilo(nome, estilo, inputs, destaque):
    """Imprime o estilo item a item, com o numero do elemento do Text+ ao lado.

    Existe porque "aplicou o estilo" nao e' informacao: quando a legenda sai
    errada, o que se quer saber e' QUAL item nao entrou e em qual elemento ele
    deveria ter entrado. O numero do elemento e' o que liga este relatorio ao
    log do Resolve.
    """
    base = estilo.get("base") or {}
    dest = estilo.get("destaque") or {}
    fonte = estilo.get("fonte") or {}
    q = estilo.get("quebra") or {}
    centro = (estilo.get("posicao") or {}).get("centro", [0.5, 0.22])

    def liga(b, sempre=False):
        return "ON " if (sempre or (b or {}).get("ativo")) else "off"

    L = []
    L.append(f"style '{nome}'")
    L.append(f"  font          {fonte.get('familia')} {fonte.get('estilo')}"
             f"  size {fonte.get('tamanho')}")
    L.append(f"  position      centre ({centro[0]:.3f}, {centro[1]:.3f})")
    L.append(f"  wrapping      {q.get('max_chars', 20)} chars, up to "
             f"{q.get('max_linhas', 2)} lines")

    L.append("  -- normal text --")
    f = base.get("fill") or {}
    L.append(f"    [el 1] fill        {liga(f, True)}  {_hexa(f)}")
    o = base.get("outline") or {}
    L.append(f"    [el 2] outline     {liga(o)}  {_hexa(o, '#000000')}"
             f"  thickness {o.get('espessura')}  {_fmt_dir(o)}")
    s = base.get("sombra") or {}
    L.append(f"    [el 3] shadow      {liga(s)}  {_hexa(s, '#000000')}"
             f"  op {s.get('opacidade')}  soft {s.get('suavidade')}  {_fmt_dir(s)}")
    cx = base.get("caixa") or {}
    L.append(f"    [el 6] text box    {liga(cx)}  {_hexa(cx, '#000000')}"
             f"  op {cx.get('opacidade')}  level {cx.get('nivel')}")
    cxs = base.get("box_shadow") or {}
    L.append(f"    [el 7] box shadow  {liga(cxs)}  {_hexa(cxs, '#000000')}"
             f"  {_fmt_dir(cxs)}")

    L.append("  -- spoken word --")
    fd = dest.get("fill") or {}
    on_d = dest.get("ativo", True)
    L.append(f"    [el 1] fill        {liga(fd, False) if 'ativo' in fd else 'ON '}"
             f"  {_hexa(fd, dest.get('cor', '#FF4DA6'))}   (changes colour, "
             f"does not switch on)")
    cd = dest.get("caixa") or {}
    L.append(f"    [el 4] bubble      {liga(cd)}  {_hexa(cd, '#FFD84D')}"
             f"  level {cd.get('nivel')}")
    bd = dest.get("box_shadow") or {}
    L.append(f"    [el 5] box shadow  {liga(bd)}  {_hexa(bd, '#000000')}"
             f"  {_fmt_dir(bd)}")
    if not on_d:
        L.append("    (highlight is OFF in this style)")

    camadas = (destaque or {}).get("camadas") or []
    L.append(f"  animated layers:  {len(camadas)}"
             + (" -> " + ", ".join(f"el {c['elemento']}" for c in camadas)
                if camadas else "  (none: no highlight)"))

    # "a caixa nao aparece" tem duas causas muito diferentes: ou o Text+ nao
    # desenhou, ou ninguem pediu. Quando e' a segunda, dizer isso aqui evita
    # uma rodada inteira dentro do Resolve procurando um bug que nao existe.
    caixas = [n for n in (ELEM_CX_DESTAQUE, ELEM_CX_DESTAQUE_SOMBRA,
                          ELEM_CX_BASE, ELEM_CX_BASE_SOMBRA)
              if inputs.get(f"Enabled{n}") == 1]
    if caixas:
        L.append("  boxes enabled:    " + ", ".join(f"el {n}" for n in caixas)
                 + "   (switched to Border Fill inside Resolve)")
    else:
        L.append("  boxes enabled:    none")
        L.append("    -> this style asks for no box and no box shadow. If you")
        L.append("       wanted one, turn on base.caixa.ativo /")
        L.append("       destaque.caixa.ativo in estilos.json, or run with")
        L.append("       --estilo capcut_bolha (bubble on the spoken word).")

    # A bolha SO aparece quando ha tempo por palavra: ela marca a palavra
    # falada, e sem saber qual e' o Text+ desenharia uma caixa em cada palavra.
    # Dizer isso aqui evita a surpresa depois de 129 clipes criados.
    if any(c.get("on_base") == 0 for c in camadas):
        L.append("    note: the bubble only shows on captions that carry word")
        L.append("          timings - without them there is no spoken word to")
        L.append("          mark, so it stays off for that caption.")
    return "\n".join(L)


def para_relativo(itens, inicio):
    """Normaliza os tempos para o inicio do corte (timeline comecando em 0).

    Os arquivos deste projeto as vezes estao em tempo ABSOLUTO da midia
    (2570s = 42:50) e as vezes ja relativos ao corte - depende de qual etapa
    gerou. Assumir um dos dois joga a legenda 42 minutos fora de lugar e o
    Resolve aceita calado. Entao a base e' detectada, nao assumida: tempo
    relativo comeca perto de zero, absoluto comeca perto do inicio do corte.

    Devolve (itens_relativos, offset_descontado).
    """
    if not itens or inicio <= 0:
        return itens, 0.0
    menor = min(float(i["start"]) for i in itens)
    if menor < inicio - 1.0:
        return itens, 0.0  # ja estava relativo

    def _shift(d):
        novo = dict(d)
        novo["start"] = float(d["start"]) - inicio
        novo["end"] = float(d["end"]) - inicio
        if d.get("words"):
            novo["words"] = [{**w,
                              "start": float(w["start"]) - inicio,
                              "end": float(w["end"]) - inicio} for w in d["words"]]
        return novo

    return [_shift(i) for i in itens], inicio


def achar_arquivos(pasta, transcricao=None):
    """Descobre transcricao e diarizacao dentro da pasta do corte.

    `transcricao` sobrescreve o que o corte.json aponta. Serve pro caso do
    destaque: o tempo por palavra so existe se o Whisper rodou com `--words`,
    e essa rodada normalmente sai num arquivo ao lado em vez de substituir a
    transcricao canonica do corte.
    """
    corte = _ler_json(os.path.join(pasta, "corte.json"))
    transcript = transcricao or corte.get("transcript") or "turnsWhisper.json"
    turnos = corte.get("last_turns_file") or "turnsManual.json"
    return (transcript if os.path.isabs(transcript)
            else os.path.join(pasta, transcript),
            os.path.join(pasta, turnos),
            corte)


# ------------------------------------------------------------------- saida

def montar(pasta, cfg, nome_estilo, usar_words=True, max_chars=None, pular=(),
           transcricao=None):
    p_trans, p_turnos, corte = achar_arquivos(pasta, transcricao)
    segmentos = _ler_json(p_trans)
    turnos = _ler_json(p_turnos) if os.path.isfile(p_turnos) else []

    inicio = float(corte.get("start") or 0.0)
    segmentos, off_seg = para_relativo(segmentos, inicio)
    turnos_rel, off_tur = para_relativo(turnos, inicio)

    estilo = cfg["estilos"][nome_estilo]
    inputs, controles, destaque = compilar_estilo(estilo)
    quebra = estilo.get("quebra") or {}
    limite = max_chars or quebra.get("max_chars", 20)
    linhas = quebra.get("max_linhas", 2)

    cfg_falantes = cfg.get("falantes") or {}
    aplicar_em = cfg.get("aplicar_em", "fill")

    ordem, speakers = {}, []
    for nome, dados in cfg_falantes.items():
        ordem[nome] = len(speakers) + 1  # 1-based: o Lua indexa direto
        speakers.append({
            "nome": nome,
            "cor": _rgb(dados.get("cor", "#FFFFFF")),
            "aplicar_em": dados.get("aplicar_em", aplicar_em),
            "track": dados.get("track"),
        })

    saida, com_words, pulados = [], 0, 0
    contagem = {}
    for seg in segmentos:
        texto = (seg.get("text") or "").strip()
        if not texto:
            continue
        nome = falante_de(seg, turnos_rel)
        contagem[nome] = contagem.get(nome, 0) + 1
        if nome in pular:
            pulados += 1
            continue

        item = {
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "text": quebrar(texto, limite, linhas).replace("\\N", "\n"),
            "speaker_id": ordem.get(nome, 0),
        }

        words = seg.get("words") if usar_words else None
        if words:
            # o Lua conta CARACTERE dentro da frase; a quebra em linhas troca
            # espaco por \n e mantem o comprimento, entao os indices seguem
            # validos. O que nao pode e' o texto deixar de casar com os tokens.
            item["words"] = [{"word": w["word"], "start": round(w["start"], 3),
                              "end": round(w["end"], 3)} for w in words]
            com_words += 1
        saida.append(item)

    return {
        "versao": 2,
        "macro_versao": MACRO_VERSAO,
        "estilo": nome_estilo,
        "inputs": inputs,
        "controles": controles,
        "destaque": destaque,
        "speakers": speakers,
        "segments": saida,
    }, {"contagem": contagem, "com_words": com_words, "pulados": pulados,
        "off_seg": off_seg, "off_tur": off_tur}


_LUA_RESERVADAS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "goto", "if", "in", "local", "nil", "not", "or", "repeat", "return",
    "then", "true", "until", "while",
}


def para_lua(valor, ident=0):
    """Serializa em tabela Lua.

    O Resolve roda Lua e nao tem parser de JSON embutido - o AutoSubs carrega
    um dkjson junto so pra isso. Escrevendo um arquivo .lua o script do Resolve
    le com `loadstring` e nao depende de nada. O .json continua saindo, pra
    conferencia e pra qualquer outro consumidor.
    """
    esp = "  " * ident
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if valor is None:
        return "nil"
    if isinstance(valor, (int, float)):
        return repr(round(valor, 6) if isinstance(valor, float) else valor)
    if isinstance(valor, str):
        return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') \
                          .replace("\n", "\\n").replace("\r", "") + '"'
    if isinstance(valor, (list, tuple)):
        itens = [para_lua(v, ident + 1) for v in valor]
        return "{ " + ", ".join(itens) + " }" if len(itens) <= 6 else (
            "{\n" + ",\n".join(f"{esp}  {i}" for i in itens) + f"\n{esp}}}")
    if isinstance(valor, dict):
        partes = []
        for k, v in valor.items():
            # "end" e' identificador valido em Python e palavra reservada em
            # Lua - `end = 3.6` nao compila. Por isso a lista abaixo.
            chave = k if (str(k).isidentifier() and k not in _LUA_RESERVADAS) \
                else f'["{k}"]'
            partes.append(f"{esp}  {chave} = {para_lua(v, ident + 1)}")
        return "{\n" + ",\n".join(partes) + f"\n{esp}}}"
    raise TypeError(f"do not know how to serialise {type(valor)}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build legendas.json/.lua for GiAutoSubs.lua")
    ap.add_argument("pasta", metavar="folder",
                    help="the cut folder (the one holding corte.json)")
    ap.add_argument("--estilos", "--styles", dest="estilos",
                    default=ESTILOS_PADRAO, help="path to estilos.json")
    ap.add_argument("--estilo", "--style", dest="estilo", default=None,
                    help="style name (default: the JSON's 'padrao')")
    ap.add_argument("--max-chars", type=int, default=None)
    ap.add_argument("--sem-words", "--no-words", dest="sem_words",
                    action="store_true",
                    help="ignore word timings (turns the highlight off)")
    ap.add_argument("--transcricao", "--transcript", dest="transcricao",
                    default=None, metavar="file.json",
                    help="use this transcript instead of the one corte.json "
                         "points at (that is where the --words run lands)")
    ap.add_argument("--pular", "--skip", dest="pular", default=None,
                    metavar="cut,no_name",
                    help="drop captions whose speaker is one of these names")
    ap.add_argument("--out", default=None, help="default: <folder>/legendas.json")
    args = ap.parse_args(argv)

    if not os.path.isfile(os.path.join(args.pasta, "corte.json")):
        print(f"no corte.json found in {args.pasta}", file=sys.stderr)
        return 1

    cfg = carregar_estilos(args.estilos)
    nome = args.estilo or cfg.get("padrao") or next(iter(cfg["estilos"]))
    if nome not in cfg["estilos"]:
        print(f"style '{nome}' does not exist. available: "
              f"{', '.join(cfg['estilos'])}", file=sys.stderr)
        return 1

    pular = {p.strip() for p in (args.pular or "").split(",") if p.strip()}
    doc, stats = montar(args.pasta, cfg, nome, not args.sem_words,
                        args.max_chars, pular, args.transcricao)
    out = args.out or os.path.join(args.pasta, "legendas.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    out_lua = os.path.splitext(out)[0] + ".lua"
    with open(out_lua, "w", encoding="utf-8") as fh:
        fh.write("-- generated by giautosubs.py - do not edit by hand\nreturn "
                 + para_lua(doc) + "\n")

    print(resumo_estilo(nome, cfg["estilos"][nome], doc["inputs"], doc["destaque"]))
    print(f"\n  {len(doc['segments'])} captions | "
          f"{stats['com_words']} with word timings")
    if stats["off_seg"] or stats["off_tur"]:
        print(f"[i] absolute timestamps detected, subtracted "
              f"{stats['off_seg'] or stats['off_tur']:.1f}s "
              f"(the timeline starts at 0)")
    conhecidos = set(cfg.get("falantes") or {})
    linha = []
    for n, q in sorted(stats["contagem"].items(), key=lambda kv: -kv[1]):
        marca = "" if n in conhecidos else "  <- base style"
        linha.append(f"   {str(n):12} {q}{marca}")
    print("\n".join(linha))
    if stats["pulados"]:
        print(f"[i] {stats['pulados']} captions dropped by --skip")
    if not doc["destaque"]:
        print("[i] highlight is off in this style")
    elif not stats["com_words"]:
        wav = os.path.join(args.pasta, "audio.wav")
        alvo = os.path.join(args.pasta, "turnsWhisper_words.json")
        print("[!] NO caption has word timings. The highlight cannot light up -")
        print("    it needs to know when each word is spoken, and the current")
        print("    transcript only has the start and end of each sentence.")
        print("    The bubble stays off on those captions on purpose: without a")
        print("    spoken word to mark, it would be drawn on every word.")
        print("    The run with word timings (costs about 25% more time):")
        print(f"      python \"{os.path.join(pasta_dos_scripts(), '4_transcribe_whisper.py')}\""
              f" \"{wav}\" --words --whisper-model medium --out \"{alvo}\"")
        print(f"      python giautosubs.py \"{args.pasta}\" "
              f"--transcript turnsWhisper_words.json")
    print(f"-> {out}")
    print(f"-> {out_lua}   (this is the one GiAutoSubs.lua reads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
