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
#   kind: texto | area | num | bool | escolha | lista_rank | imagens | palavras
#   in_game: como a aba 3 joga este tipo ("rank" tem as duas buscas;
#            "impostor" tem o sorteio e o cronometro).
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
        "sub": "Todos veem o mesmo quadro; o impostor ve outro (ou nenhum) e "
               "tem que fingir.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: pinturas famosas"},
            {"nome": "quadros", "rotulo": "Quadros", "kind": "imagens",
             "dica": "um caminho ou URL por linha"},
            {"nome": "quadro_impostor", "rotulo": "O impostor recebe",
             "kind": "escolha", "padrao": "outro",
             "opcoes": [
                 {"v": "outro", "r": "outro quadro da lista"},
                 {"v": "nenhum", "r": "nenhum quadro"},
             ]},
            {"nome": "n_impostores", "rotulo": "Nº de impostores",
             "kind": "num", "padrao": 1},
        ],
    },
    "impostor_palavra": {
        "rotulo": "Impostor na palavra",
        "in_game": "impostor",
        "sub": "Todos recebem a mesma palavra; o impostor recebe outra (ou "
               "nenhuma) e tem que descrever sem saber.",
        "campos": [
            {"nome": "tema", "rotulo": "Tema", "kind": "texto",
             "dica": "ex.: comidas de festa junina"},
            {"nome": "palavras", "rotulo": "Palavras", "kind": "palavras",
             "dica": "uma por linha; o in_game sorteia uma"},
            {"nome": "palavra_impostor", "rotulo": "O impostor recebe",
             "kind": "escolha", "padrao": "outra",
             "opcoes": [
                 {"v": "outra", "r": "outra palavra da lista"},
                 {"v": "nenhuma", "r": "nenhuma palavra"},
             ]},
            {"nome": "n_impostores", "rotulo": "Nº de impostores",
             "kind": "num", "padrao": 1},
        ],
    },
}

# O cronometro do impostor, em segundos. Fica aqui e nao no jogo porque vale
# para todos eles, e a mesa mexe nele na hora.
TEMPO_PADRAO = 120
TEMPO_PASSO = 30


def padroes(tipo: str) -> dict:
    """Os atributos de um jogo novo daquele tipo, com os padroes de TIPOS."""
    attrs: dict = {}
    for c in TIPOS[tipo]["campos"]:
        if "padrao" in c:
            attrs[c["nome"]] = c["padrao"]
        elif c["kind"] in ("imagens", "palavras", "lista_rank"):
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
    elif tipo == "impostor_palavra":
        corpo = f"{len(a.get('palavras') or [])} palavras"
    elif tipo == "impostor_quadro":
        corpo = f"{len(a.get('quadros') or [])} quadros"
    else:
        return tema
    return f"{tema} · {corpo}" if tema else corpo


def pendencia(tipo: str | None, a: dict) -> str:
    """O que falta para este jogo poder ser jogado — '' se esta pronto.

    A aba 3 e a hora errada de descobrir que a lista nunca foi importada, entao
    o roteiro avisa antes, na aba 2.
    """
    if tipo == "rank_lista" and not (a.get("lista") or []):
        return "sem lista importada"
    if tipo == "impostor_palavra" and not (a.get("palavras") or []):
        return "sem palavras"
    if tipo == "impostor_quadro" and not (a.get("quadros") or []):
        return "sem quadros"
    return ""


# ------------------------------------------------------ lista_do_rank.txt

# "1. Nome", "1 - Nome", "1) Nome", "01 Nome", ou so "Nome".
_POS = re.compile(r"^\s*(\d{1,4})\s*[.)\-:–]?\s+(.*)$")


def parse_lista_rank(texto: str) -> list[dict]:
    """lista_do_rank.txt -> [{pos, nome, extra}].

    A posicao vem do numero no comeco da linha quando existe; quando nao
    existe, vem da ordem das linhas. As duas formas convivem no mesmo arquivo
    porque listas copiadas da web vem dos dois jeitos, e recusar o arquivo por
    causa disso so faria voce editar o txt a mao antes de cada gravacao.

    Um campo depois de TAB, ' | ' ou ' — ' vira `extra` (o valor do rank:
    "R$ 222 mi", "1.4 bi de views"), e aparece na revelacao.
    """
    itens: list[dict] = []
    for linha in (texto or "").splitlines():
        linha = linha.strip().lstrip("﻿")
        if not linha or linha.startswith("#"):
            continue
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
