"""video_script — o roteiro (aba 2), que e o centro de tudo.

Um roteiro guarda as tres coisas de um episodio:

  - **quem joga** (participantes e quantas vidas cada um tem),
  - **o que se joga** (os jogos, na ordem, com os atributos de cada um),
  - as notas de fala.

Os jogos moram DENTRO do roteiro, nao num banco a parte. Foi uma escolha:
com um banco global existia o jogo orfao e existia o item de roteiro apontando
pra um jogo apagado — dois estados que so davam trabalho. Aqui, apagar o
roteiro leva os jogos junto, e nao ha como um jogo do roteiro nao existir.

A aba 1 (Jogos) e a tela de edicao de UM jogo deste roteiro, e nao um cadastro
separado: clicar no jogo aqui leva pra la.
"""

from __future__ import annotations

import random
import time

import jogos
import quadros
import store


def _novo_id(pref: str) -> str:
    return f"{pref}{int(time.time() * 1000):x}{random.randint(0, 255):02x}"


# ------------------------------------------------------------------ leitura

def _enriquecer(r: dict) -> dict:
    """Acrescenta o que a tela mostra mas nao e gravado: rotulo do tipo, a
    linha de resumo e o que falta pro jogo poder ser jogado."""
    for j in r.get("jogos") or []:
        a = j.get("attrs") or {}
        j["tipo_rotulo"] = jogos.rotulo(j.get("tipo"))
        j["in_game"] = jogos.in_game(j.get("tipo"))
        j["resumo"] = jogos.resumo(j.get("tipo"), a)
        j["pendencia"] = jogos.pendencia(j.get("tipo"), a)
    r["n_jogos"] = len(r.get("jogos") or [])
    r["n_participantes"] = len(r.get("participantes") or [])
    r["duracao_prevista"] = sum(int(j.get("duracao_min") or 0)
                                for j in r.get("jogos") or [])
    r["pendencias"] = [f"{j['nome']}: {j['pendencia']}"
                       for j in r.get("jogos") or [] if j.get("pendencia")]
    return r


def listar() -> list[dict]:
    return [_enriquecer(r) for r in store.listar(store.ROTEIROS)]


def ler(slug: str) -> dict | None:
    r = store.ler(store.ROTEIROS, slug)
    return None if r is None else _enriquecer(r)


# ------------------------------------------------------------------ escrita

def criar(nome: str) -> dict:
    slug = store.slug_livre(store.ROTEIROS, nome or "roteiro")
    return store.gravar(store.ROTEIROS, slug, {
        "nome": (nome or "").strip() or "Roteiro sem nome",
        "criado": store.agora(),
        "notas": "",
        "participantes": [],
        "jogos": [],
    })


def _abrir(slug: str) -> dict:
    r = store.ler(store.ROTEIROS, slug)
    if r is None:
        raise KeyError(slug)
    return r


def _participante(x: dict) -> dict:
    return {
        "id": x.get("id") or _novo_id("p"),
        "nome": (x.get("nome") or "").strip() or "sem nome",
        "vidas_total": max(0, min(int(x.get("vidas_total") or 0), 12)),
    }


def salvar(slug: str, campos: dict) -> dict:
    """Atualiza nome/notas/participantes e a ORDEM + metadados dos jogos.

    Os jogos vem inteiros, na ordem da tela — reordenar e mandar a lista nova,
    sem verbo de 'mover'. Os `attrs` NAO sao tocados aqui: quem edita atributo
    e a aba 1, por `salvar_jogo()`. Assim, salvar o roteiro com um jogo aberto
    noutra aba nao apaga o que foi feito la.
    """
    r = _abrir(slug)
    for k in ("nome", "notas"):
        if k in campos and campos[k] is not None:
            r[k] = campos[k]

    if campos.get("participantes") is not None:
        r["participantes"] = [_participante(x) for x in campos["participantes"]]

    if campos.get("jogos") is not None:
        antigos = {j["id"]: j for j in r.get("jogos") or []}
        novos = []
        for j in campos["jogos"]:
            base = antigos.get(j.get("id"))
            if base is None:
                continue                      # jogo que nao e deste roteiro
            base["nome"] = (j.get("nome") or "").strip() or base["nome"]
            base["duracao_min"] = int(j.get("duracao_min") or 0)
            base["notas"] = j.get("notas") or ""
            novos.append(base)
        r["jogos"] = novos

    store.gravar(store.ROTEIROS, slug, r)
    return ler(slug)


# -------------------------------------------------------- os jogos do roteiro

def add_jogo(slug: str, tipo: str, nome: str = "") -> dict:
    if tipo not in jogos.TIPOS:
        raise ValueError(f"tipo desconhecido: {tipo}")
    r = _abrir(slug)
    r.setdefault("jogos", []).append({
        "id": _novo_id("j"),
        "tipo": tipo,
        "nome": (nome or "").strip() or jogos.TIPOS[tipo]["rotulo"],
        "duracao_min": 0,
        "notas": "",
        "attrs": jogos.padroes(tipo),
    })
    store.gravar(store.ROTEIROS, slug, r)
    return ler(slug)


def ler_jogo(slug: str, jid: str) -> dict | None:
    r = ler(slug)
    if r is None:
        return None
    j = next((x for x in r["jogos"] if x.get("id") == jid), None)
    if j is None:
        return None
    return {**j, "roteiro": slug, "roteiro_nome": r["nome"]}


def _quadros_em_uso(r: dict) -> set[str]:
    """Todo quadro citado por qualquer jogo do roteiro.

    E o roteiro inteiro, e nao so o jogo que acabou de ser salvo: a pasta de
    imagens e por roteiro, e dois jogos de quadro nela compartilham o mesmo
    espaco — varrer olhando so um deles apagaria os arquivos do outro.
    """
    uso: set[str] = set()
    for j in r.get("jogos") or []:
        uso.update(str(x) for x in ((j.get("attrs") or {}).get("quadros") or []))
    return uso


def salvar_jogo(slug: str, jid: str, nome: str | None,
                attrs: dict | None) -> dict:
    r = _abrir(slug)
    j = next((x for x in r.get("jogos") or [] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    if nome is not None and nome.strip():
        j["nome"] = nome.strip()
    if attrs is not None:
        j["attrs"] = {**(j.get("attrs") or {}), **attrs}
    store.gravar(store.ROTEIROS, slug, r)
    # tirar um quadro da lista tem que levar o arquivo junto, ou a pasta so
    # cresce com imagens que ninguem mais usa
    quadros.limpar_orfaos(slug, _quadros_em_uso(r))
    return ler_jogo(slug, jid)


def add_quadro(slug: str, jid: str, nome_arquivo: str, conteudo_b64: str) -> dict:
    """Sobe uma imagem e acrescenta ela aos quadros daquele jogo."""
    r = _abrir(slug)
    j = next((x for x in r.get("jogos") or [] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    if j.get("tipo") != "impostor_quadro":
        raise ValueError("so o 'Impostor no quadro' tem quadros")
    url = quadros.guardar(slug, nome_arquivo, conteudo_b64)
    j.setdefault("attrs", {}).setdefault("quadros", []).append(url)
    store.gravar(store.ROTEIROS, slug, r)
    return ler_jogo(slug, jid)


def apagar_jogo(slug: str, jid: str) -> dict:
    r = _abrir(slug)
    antes = len(r.get("jogos") or [])
    r["jogos"] = [x for x in r.get("jogos") or [] if x.get("id") != jid]
    if len(r["jogos"]) == antes:
        raise KeyError(jid)
    store.gravar(store.ROTEIROS, slug, r)
    quadros.limpar_orfaos(slug, _quadros_em_uso(r))
    return ler(slug)


def apagar(slug: str) -> bool:
    """Apaga o roteiro, os jogos dele (moram dentro), os quadros que subiram e a
    partida em andamento — sem isso, a partida ficaria apontando pra um roteiro
    que nao existe mais, e as imagens ficariam ocupando disco para sempre."""
    store.apagar(store.PARTIDAS, slug)
    quadros.apagar_do_roteiro(slug)
    return store.apagar(store.ROTEIROS, slug)
