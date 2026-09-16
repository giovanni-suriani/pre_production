"""video_script — os tipos de jogo.

Um jogo e um tipo mais os atributos daquele tipo. Os tipos sao fechados de
proposito: a aba in_game precisa saber o que desenhar, e um jogo com campos
totalmente livres nao daria pra jogar — daria so pra ler.

Este modulo nao grava nada. Os jogos **moram dentro do roteiro** que os usa
(ver roteiros.py): cada roteiro tem os seus, e apagar o roteiro leva os jogos
junto. Aqui fica so o catalogo (TIPOS), os padroes de um jogo novo e as contas
que a aba 3 faz em cima da lista do rank.

TIPOS descreve os campos de cada tipo. A tela monta o formulario a partir
disto, entao um campo novo aqui aparece na tela sem tocar no JS.
"""

from __future__ import annotations

import re

import store

# ---------------------------------------------------------------- os tipos

# tipo -> {rotulo, in_game, campos: [{nome, rotulo, kind, ...}]}
#   kind: texto | area | num | bool | escolha | lista_rank | duplas
#   in_game: como a aba 3 joga este tipo ("rank" tem as duas buscas;
#            "impostor" tem o sorteio e o cronometro).
#
# Os dois jogos de impostor tem a MESMA forma: uma lista de duplas
# `jogador / impostor`. O sorteio pega uma linha e da a coluna "jogador" pra
# mesa e a coluna "impostor" pra quem foi sorteado impostor. Antes o "Impostor
# no quadro" subia imagens e o "Impostor na palavra" tinha uma lista so (o
# impostor recebia outra palavra qualquer dela) — o par explicito substituiu os
# dois: e ele que decide o que cada lado ouve, em vez de um sorteio dentro do
# sorteio. Quadro aqui e o NOME do quadro ("Mona Lisa"), texto como o resto.
#
# O tempo de discussao NAO e atributo de jogo: e um botao na aba 3, que comeca
# em 2min e anda de 30 em 30. Era cadastro demais para uma coisa que so faz
# sentido decidir com a mesa na frente.

TIPOS: dict[str, dict] = {
    "rank_lista": {
        "rotulo": "Adivinha rank em lista",
        "in_game": "rank",
        "sub": "A mesa tenta adivinhar quem esta em cada posicao de um rank. "
               "A lista importada e o gabarito.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: 100 jogadores mais caros da historia"},
            {"nome": "lista", "rotulo": "Lista do rank", "kind": "lista_rank",
             "dica": "importe o lista_do_rank.txt ou cole o texto"},
            {"nome": "revelados_inicio", "rotulo": "Revelados no inicio",
             "kind": "num", "padrao": 0,
             "dica": "quantas posicoes ja comecam abertas, de brinde"},
            {"nome": "aceita_parcial", "rotulo": "Aceitar nome parcial",
             "kind": "bool", "padrao": True,
             "dica": "'ronaldo' acha 'Cristiano Ronaldo'"},
        ],
    },
    "impostor_quadro": {
        "rotulo": "Impostor no quadro",
        "in_game": "impostor",
        "sub": "Todos ouvem o mesmo quadro; o impostor ouve o outro da linha "
               "e tem que fingir.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: pinturas famosas"},
            {"nome": "duplas", "rotulo": "Quadros", "kind": "duplas",
             "dica": "uma por rodada: o quadro da mesa e o do impostor"},
            {"nome": "n_impostores", "rotulo": "Nº de impostores",
             "kind": "num", "padrao": 1},
        ],
    },
    "impostor_palavra": {
        "rotulo": "Impostor na palavra",
        "in_game": "impostor",
        "sub": "Todos recebem a mesma palavra; o impostor recebe a outra da "
               "linha e tem que descrever sem saber.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: comidas de festa junina"},
            {"nome": "duplas", "rotulo": "Palavras", "kind": "duplas",
             "dica": "uma por rodada: a palavra da mesa e a do impostor"},
            {"nome": "n_impostores", "rotulo": "Nº de impostores",
             "kind": "num", "padrao": 1},
        ],
    },
    "resposta_errada": {
        "rotulo": "So resposta errada",
        "in_game": "errada",
        "sub": "A mesa responde de proposito ERRADO. Quem apresenta le a "
               "pergunta e tem a resposta certa na mao — que e justamente a "
               "que nao vale.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: geografia basica"},
            {"nome": "perguntas", "rotulo": "Perguntas", "kind": "perguntas",
             "dica": "importe o .txt ou escreva: pergunta | resposta certa"},
        ],
    },
    "discussao": {
        "rotulo": "Discussao",
        "in_game": "discussao",
        "sub": "A mesa discute um tema pelo tempo que o relogio der. Sem "
               "gabarito e sem sorteio — so o tema e o cronometro.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema da discussao", "kind": "area",
             "dica": "o que vai na tela e na boca de quem apresenta"},
            {"nome": "tempo_min", "rotulo": "Tempo (minutos)", "kind": "num",
             "padrao": 10,
             "dica": "quanto o relogio marca ao abrir; da pra mexer na hora"},
        ],
    },
}

# As vidas sao de cada JOGO, e nao do participante: um jogo de rank longo
# merece mais coracao que um impostor de cinco minutos, e quem monta o episodio
# decide isso junto com o resto do jogo. Por isso este campo entra em TODOS os
# tipos — inclusive num tipo novo, sem ninguem lembrar de repetir a linha.
VIDAS_PADRAO = 2

for _t in TIPOS.values():
    _t["campos"].append({
        "nome": "vidas", "rotulo": "Vidas neste jogo", "kind": "num",
        "padrao": VIDAS_PADRAO,
        "dica": "todo mundo na mesa comeca este jogo com este tanto",
    })


def vidas(a: dict) -> int:
    """Quantos coracoes cada um tem neste jogo. Teto de 12, como era no
    participante — acima disso a mesa vira um mural de coracao."""
    return max(0, min(int(a.get("vidas") or 0), 12))


# O cronometro, em segundos. Fica aqui e nao no jogo porque vale
# para todos eles, e a mesa mexe nele na hora.
TEMPO_PADRAO = 120
TEMPO_PASSO = 30
TEMPO_TETO = 3600


def tempo_inicial(a: dict) -> int:
    """Quanto o relogio marca ao abrir o jogo, antes de qualquer ajuste.

    So a Discussao cadastra isso (`tempo_min`), porque nela o relogio E o jogo.
    No impostor o tempo continua sendo decisao de quem esta com a mesa na
    frente: comeca em TEMPO_PADRAO e anda de 30 em 30 na propria aba 3.
    """
    m = int(a.get("tempo_min") or 0)
    return min(max(m * 60, TEMPO_PASSO), TEMPO_TETO) if m else TEMPO_PADRAO


def padroes(tipo: str) -> dict:
    """Os atributos de um jogo novo daquele tipo, com os padroes de TIPOS."""
    attrs: dict = {}
    for c in TIPOS[tipo]["campos"]:
        if "padrao" in c:
            attrs[c["nome"]] = c["padrao"]
        elif c["kind"] in ("duplas", "perguntas", "lista_rank"):
            attrs[c["nome"]] = []
        elif c["kind"] == "num":
            attrs[c["nome"]] = 0
        elif c["kind"] == "bool":
            attrs[c["nome"]] = False
        else:
            attrs[c["nome"]] = ""
    return attrs


def rotulo(tipo: str | None) -> str:
    t = TIPOS.get(tipo or "")
    return t["rotulo"] if t else (tipo or "?")


def in_game(tipo: str | None) -> str | None:
    t = TIPOS.get(tipo or "")
    return t["in_game"] if t else None


def resumo(tipo: str | None, a: dict) -> str:
    """Uma linha sobre o jogo, para a lista do roteiro."""
    tema = (a.get("tema") or "").strip()
    if tipo == "rank_lista":
        n = len(a.get("lista") or [])
        corpo = f"{n} posicoes"
    elif in_game(tipo) == "impostor":
        corpo = f"{len(duplas(a))} palavras"
    elif in_game(tipo) == "errada":
        corpo = f"{len(perguntas(a))} perguntas"
    elif in_game(tipo) == "discussao":
        corpo = f"{tempo_inicial(a) // 60} min de relogio"
    else:
        return tema
    # as vidas so se editam na aba Jogos, mas aparecem aqui: e a linha que se
    # le pra saber se o episodio inteiro esta do tamanho certo
    corpo += f" · {vidas(a)} vidas"
    return f"{tema} · {corpo}" if tema else corpo


def pendencia(tipo: str | None, a: dict) -> str:
    """O que falta para este jogo poder ser jogado — '' se esta pronto.

    A aba 3 e a hora errada de descobrir que a lista nunca foi importada, entao
    o roteiro avisa antes, na aba 2.
    """
    if tipo == "rank_lista" and not (a.get("lista") or []):
        return "sem lista importada"
    if in_game(tipo) == "impostor" and not duplas(a):
        return "sem palavras"
    if in_game(tipo) == "errada" and not perguntas(a):
        return "sem perguntas"
    if in_game(tipo) == "discussao" and not (a.get("tema") or "").strip():
        return "sem tema"
    return ""


def perguntas(a: dict) -> list[dict]:
    """As perguntas de um "So resposta errada", ja limpas.

    Linha sem pergunta nao e pergunta. A resposta pode faltar (quem apresenta
    sabe de cabeca), e a tela mostra o lugar dela vazio em vez de sumir com a
    linha — melhor ver o buraco do que nao ver a pergunta.

    O `origem` (de qual .txt a linha veio) anda junto e nao aparece na tela:
    quem usa e a lixeira, pra dizer depois em que arquivo esta a linha ruim.
    """
    out = []
    for x in (a.get("perguntas") or []):
        if isinstance(x, str):
            x = {"pergunta": x, "resposta": ""}
        q = str((x or {}).get("pergunta") or "").strip()
        if not q:
            continue
        out.append({"pergunta": q,
                    "resposta": str((x or {}).get("resposta") or "").strip(),
                    "origem": str((x or {}).get("origem") or "").strip()})
    return out


# ------------------------------------------------------- as duplas do impostor

def duplas(a: dict) -> list[dict]:
    """As duplas jogador/impostor de um jogo, ja limpas.

    Linha sem o lado do jogador nao e rodada: e uma linha em branco que alguem
    deixou no meio da caixa. O lado do impostor pode ficar vazio de proposito —
    e o caso "o impostor nao recebe nada".
    """
    out = []
    for d in (a.get("duplas") or []):
        if isinstance(d, str):
            d = {"jogador": d, "impostor": ""}
        jog = str((d or {}).get("jogador") or "").strip()
        if not jog:
            continue
        out.append({"jogador": jog,
                    "impostor": str((d or {}).get("impostor") or "").strip()})
    return out


def migrar(tipo: str | None, a: dict) -> dict:
    """Traz um jogo de impostor antigo para as duplas.

    Os jogos gravados antes tinham `palavras` (lista unica, o impostor recebia
    outra qualquer) ou `quadros` (URLs de imagem subida). A palavra vira o lado
    do jogador e o do impostor fica em branco, para ser preenchido — adivinhar
    o par seria inventar conteudo do episodio. Quadro era imagem, e imagem nao
    existe mais aqui, entao so o resto sai.
    """
    if in_game(tipo) != "impostor":
        return a
    if "duplas" not in a and (a.get("palavras") or a.get("quadros")):
        antigas = a.get("palavras") or []
        a["duplas"] = [{"jogador": str(x), "impostor": ""} for x in antigas
                       if str(x).strip()]
    a.setdefault("duplas", [])
    for morto in ("palavras", "quadros", "palavra_impostor", "quadro_impostor"):
        a.pop(morto, None)
    return a


# ------------------------------------------------------ lista_do_rank.txt

# "1. Nome", "1 - Nome", "1) Nome", "01 Nome", ou so "Nome".
_POS = re.compile(r"^\s*(\d{1,4})\s*[.)\-:–]?\s+(.*)$")


def parse_lista_rank(texto: str) -> list[dict]:
    """lista_do_rank.txt -> [{pos, nome, extra}].

    A posicao vem do numero no comeco da linha quando existe; quando nao
    existe, vem da ordem das linhas. As duas formas convivem no mesmo arquivo
    porque listas copiadas da web vem dos dois jeitos, e recusar o arquivo por
    causa disso so faria voce editar o txt a mao antes de cada gravacao.

    **Cabecalho e rodape sao jogados fora**: num arquivo com linhas numeradas,
    a lista comeca na primeira delas — o que vem antes e titulo e fonte ("TOP
    100 GOLEIROS", "Fonte: ...") — e termina na ultima, mais o que estiver
    colado nela sem numero. O que separa o rodape da lista e a LINHA EM BRANCO:
    nos arquivos de verdade o "Fonte:"/"Nota:" do fim sempre vem depois de uma,
    e o "Mbappe" sem posicao vem grudado na linha anterior. Sem isso o titulo
    virava o primeiro colocado e empurrava o rank inteiro, e a nota final
    entrava como a posicao 101 — e so na hora de jogar se via. Numa lista sem
    numero nenhum nada disso vale: ali a primeira linha E o primeiro item.

    Um campo depois de TAB, ' | ' ou ' — ' vira `extra` (o valor do rank:
    "R$ 222 mi", "1.4 bi de views"), e aparece na revelacao.
    """
    linhas = [l.strip().lstrip("﻿") for l in (texto or "").splitlines()]
    uteis = [i for i, l in enumerate(linhas) if l and not l.startswith("#")]
    com_num = [i for i in uteis if _POS.match(linhas[i])]
    if com_num:
        # a lista comeca na primeira linha numerada — o que vem antes e titulo
        # e fonte. E acaba na ultima, mas so depois de engolir o que vier
        # colado nela sem numero: e a linha "Mbappe" solta no fim de uma lista
        # numerada, que continua valendo. O que separa o rodape da lista e a
        # LINHA EM BRANCO — nos arquivos de verdade, "Fonte:" e "Nota:" vem
        # sempre depois de uma.
        fim = com_num[-1]
        j = fim + 1
        while j < len(linhas) and linhas[j] and not linhas[j].startswith("#"):
            fim = j
            j += 1
        dentro = range(com_num[0], fim + 1)
    else:
        dentro = range(len(linhas))    # sem numero nenhum: tudo e lista

    itens: list[dict] = []
    for i in uteis:
        if i not in dentro:
            continue
        linha = linhas[i]
        m = _POS.match(linha)
        if m:
            pos, resto = int(m.group(1)), m.group(2).strip()
        else:
            pos, resto = len(itens) + 1, linha
        extra = ""
        for sep in ("\t", " | ", " — ", " – ", ";"):
            if sep in resto:
                resto, _, extra = resto.partition(sep)
                break
        nome = resto.strip()
        if not nome:
            continue
        itens.append({"pos": pos, "nome": nome, "extra": extra.strip()})
    return itens


def normalizar(s: str) -> str:
    """Para comparar busca com gabarito: sem acento, sem pontuacao, minusculo."""
    return store.slugify(s).replace("_", " ").strip()


def buscar_na_lista(itens: list[dict], termo: str,
                    parcial: bool = True) -> list[dict]:
    """Acha na lista por nome. Devolve os itens que casam, na ordem do rank."""
    t = normalizar(termo)
    if not t:
        return []
    exatos = [i for i in itens if normalizar(i.get("nome", "")) == t]
    if exatos or not parcial:
        return exatos
    return [i for i in itens if t in normalizar(i.get("nome", ""))]
