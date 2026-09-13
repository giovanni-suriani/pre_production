"""video_script — a partida (aba 3, in_game).

O estado do que esta acontecendo na mesa AGORA: quantas vidas cada um ainda
tem, qual jogo do roteiro esta rolando, e o que ja foi revelado/sorteado em
cada um.

**Uma partida por roteiro**, com o mesmo slug dele. "Jogar roteiro" abre a que
existe (continuando de onde parou) ou cria a partir dos participantes do
roteiro; o botao Reinicio devolve as vidas e fecha tudo, sem perguntar nada.
Nao ha mais tela de montar a mesa: quem joga ja foi decidido no roteiro.

Isto grava em disco a cada clique de proposito. E a unica aba que roda com a
camera ligada: um F5 sem querer, ou o navegador fechando, nao pode custar o
placar de quarenta minutos de gravacao.

As vidas sao uma lista de booleanos, uma por coracao, nao um contador. Assim o
clique na tela e sempre "este coracao aqui", e nao "descer o numero" — e
desfazer e clicar de novo no mesmo lugar.
"""

from __future__ import annotations

import random

import jogos
import roteiros
import store


# ------------------------------------------------------------------ leitura

def listar() -> list[dict]:
    out = []
    for p in store.listar(store.PARTIDAS):
        parts = p.get("participantes") or []
        p["n_participantes"] = len(parts)
        p["vivos"] = sum(1 for x in parts if any(x.get("vidas") or []))
        out.append(p)
    return out


def ler(slug: str) -> dict | None:
    """A partida mais o roteiro resolvido, para a tela desenhar o jogo atual
    sem uma segunda ida ao servidor."""
    p = store.ler(store.PARTIDAS, slug)
    if p is None:
        return None
    r = roteiros.ler(slug)
    p["roteiro_existe"] = r is not None
    p["roteiro_nome"] = r["nome"] if r else slug
    p["notas_roteiro"] = (r or {}).get("notas") or ""
    p["jogos"] = (r or {}).get("jogos") or []
    idx = int(p.get("jogo_idx") or 0)
    p["jogo_idx"] = max(0, min(idx, max(0, len(p["jogos"]) - 1)))
    return p


# ------------------------------------------------------------------ escrita

def _vidas_iniciais(r: dict) -> list[dict]:
    return [{"id": x["id"], "nome": x["nome"],
             "vidas_total": int(x.get("vidas_total") or 0),
             "vidas": [True] * int(x.get("vidas_total") or 0)}
            for x in r.get("participantes") or []]


def _brindes(r: dict) -> dict:
    """As posicoes de brinde (`revelados_inicio`) de cada jogo de rank.

    Sorteadas UMA vez, aqui, e gravadas com o resto. Sortear na hora de
    desenhar a tela daria posicoes diferentes a cada F5 — no meio da gravacao,
    o rank mudaria sozinho.
    """
    estado: dict = {}
    for j in r.get("jogos") or []:
        if j.get("tipo") != "rank_lista":
            continue
        a = j.get("attrs") or {}
        lista = a.get("lista") or []
        n = min(int(a.get("revelados_inicio") or 0), len(lista))
        if n <= 0:
            continue
        estado[j["id"]] = {"revelados": {
            str(pos): {"quem": "", "termo": "de brinde", "em": store.agora()}
            for pos in random.sample([int(x["pos"]) for x in lista], n)}}
    return estado


def abrir(slug: str) -> dict:
    """O que o botao "Jogar roteiro" faz: continua a partida, ou comeca uma.

    Continuar e o padrao porque o caso comum e voltar pra mesma gravacao — o
    F5, o navegador que fechou, o intervalo pro almoco. Comecar de novo e o
    botao Reinicio, que e explicito.
    """
    r = roteiros.ler(slug)
    if r is None:
        raise KeyError(slug)
    if not (r.get("participantes") or []):
        raise ValueError("este roteiro ainda nao tem participantes — "
                         "defina quem joga na aba Roteiro")
    p = store.ler(store.PARTIDAS, slug)
    if p is None:
        return reiniciar(slug)
    return sincronizar(slug)


def reiniciar(slug: str) -> dict:
    """Vidas cheias, gabarito fechado, nada sorteado — os mesmos jogadores."""
    r = roteiros.ler(slug)
    if r is None:
        raise KeyError(slug)
    store.gravar(store.PARTIDAS, slug, {
        "roteiro": slug,
        "criado": store.agora(),
        "jogo_idx": 0,
        "participantes": _vidas_iniciais(r),
        "estado": _brindes(r),
    })
    return ler(slug)


def sincronizar(slug: str) -> dict:
    """Traz do roteiro quem entrou, quem saiu e quem mudou de nome, SEM mexer
    nas vidas ja gastas.

    Sem isto, acrescentar alguem na mesa no meio do episodio obrigaria a
    reiniciar e perder o placar. Quem chega entra com as vidas cheias; quem
    ganhou mais vidas no roteiro ganha corac oes novos no fim da fila.
    """
    r = roteiros.ler(slug)
    if r is None:
        raise KeyError(slug)
    p = store.ler(store.PARTIDAS, slug)
    if p is None:
        return reiniciar(slug)

    antigos = {x["id"]: x for x in p.get("participantes") or []}
    novos = []
    for x in r.get("participantes") or []:
        total = int(x.get("vidas_total") or 0)
        velho = antigos.get(x["id"])
        if velho is None:
            vidas = [True] * total
        else:
            vidas = list(velho.get("vidas") or [])
            if len(vidas) < total:
                vidas += [True] * (total - len(vidas))
            elif len(vidas) > total:
                vidas = vidas[:total]
        novos.append({"id": x["id"], "nome": x["nome"],
                      "vidas_total": total, "vidas": vidas})
    p["participantes"] = novos

    # estado de jogo que nao existe mais no roteiro nao serve pra nada
    vivos = {j["id"] for j in r.get("jogos") or []}
    p["estado"] = {k: v for k, v in (p.get("estado") or {}).items()
                   if k in vivos}
    store.gravar(store.PARTIDAS, slug, p)
    return ler(slug)


def _abrir(slug: str) -> dict:
    p = store.ler(store.PARTIDAS, slug)
    if p is None:
        raise KeyError(slug)
    return p


def _salvar(slug: str, p: dict) -> dict:
    store.gravar(store.PARTIDAS, slug, p)
    return ler(slug)


def tocar_vida(slug: str, pid: str, i: int) -> dict:
    """O clique num coracao. Alterna cheio <-> cinza, sempre naquele indice."""
    p = _abrir(slug)
    for x in p.get("participantes") or []:
        if x.get("id") == pid:
            vidas = x.setdefault("vidas", [])
            if 0 <= i < len(vidas):
                vidas[i] = not vidas[i]
            break
    else:
        raise KeyError(pid)
    return _salvar(slug, p)


def ir_para(slug: str, idx: int) -> dict:
    p = _abrir(slug)
    p["jogo_idx"] = max(0, int(idx))
    return _salvar(slug, p)


# ---------------------------------------------------- estado por jogo (rank)

def _estado_jogo(p: dict, jid: str) -> dict:
    return p.setdefault("estado", {}).setdefault(jid, {})


def revelar(slug: str, jid: str, posicoes: list[int], quem: str = "",
            termo: str = "") -> dict:
    """Marca posicoes do rank como reveladas. Guarda quem acertou e o que foi
    digitado — e disso que sai a legenda/overlay depois da gravacao."""
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    rev = est.setdefault("revelados", {})
    for pos in posicoes:
        rev.setdefault(str(int(pos)), {"quem": quem or "", "termo": termo or "",
                                       "em": store.agora()})
    est.setdefault("log", []).append({
        "acao": "revelar", "posicoes": [int(x) for x in posicoes],
        "quem": quem or "", "termo": termo or "", "em": store.agora()})
    return _salvar(slug, p)


def esconder(slug: str, jid: str, pos: int) -> dict:
    """Desfaz uma revelacao — errei de linha, ou revelei sem querer."""
    p = _abrir(slug)
    _estado_jogo(p, jid).get("revelados", {}).pop(str(int(pos)), None)
    return _salvar(slug, p)


def errou(slug: str, jid: str, termo: str, quem: str = "") -> dict:
    """Busca que nao achou nada, registrada. Aparece na lista de chutes
    perdidos do jogo — e material de piada na edicao."""
    p = _abrir(slug)
    _estado_jogo(p, jid).setdefault("erros", []).append(
        {"termo": termo or "", "quem": quem or "", "em": store.agora()})
    return _salvar(slug, p)


def zerar_jogo(slug: str, jid: str) -> dict:
    p = _abrir(slug)
    p.setdefault("estado", {})[jid] = {}
    return _salvar(slug, p)


# ------------------------------------------------ estado por jogo (impostor)

def sortear_impostor(slug: str, jid: str) -> dict:
    """Sorteia a palavra/quadro e quem sao os impostores, e guarda. Guardar e o
    ponto: quem apresenta precisa poder reabrir a tela no meio da rodada sem
    sortear tudo de novo e perder quem era o impostor."""
    p = _abrir(slug)
    cheia = ler(slug)
    j = next((x for x in cheia["jogos"] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    a = j.get("attrs") or {}

    if j.get("tipo") == "impostor_palavra":
        pool = [x for x in (a.get("palavras") or []) if str(x).strip()]
        modo = a.get("palavra_impostor") or "outra"
    else:
        pool = [x for x in (a.get("quadros") or []) if str(x).strip()]
        modo = a.get("quadro_impostor") or "outro"
    if not pool:
        raise ValueError("este jogo nao tem palavra/quadro cadastrado — "
                         "abra ele na aba Jogos")

    principal = random.choice(pool)
    if modo in ("outra", "outro"):
        resto = [x for x in pool if x != principal]
        do_impostor = random.choice(resto) if resto else ""
    else:
        do_impostor = ""

    vivos = [x for x in (p.get("participantes") or []) if any(x.get("vidas") or [])]
    alvo = vivos or (p.get("participantes") or [])
    n = max(0, min(int(a.get("n_impostores") or 1), len(alvo)))
    impostores = [x["id"] for x in random.sample(alvo, n)] if n else []

    est = _estado_jogo(p, jid)
    est["sorteio"] = {
        "principal": principal, "impostor": do_impostor, "modo": modo,
        "impostores": impostores, "em": store.agora(), "revelado": False,
    }
    est.setdefault("log", []).append({"acao": "sortear", "em": store.agora()})
    return _salvar(slug, p)


def revelar_impostor(slug: str, jid: str, revelado: bool = True) -> dict:
    """Abre (ou fecha) na tela quem era o impostor — o fim da rodada."""
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    if not est.get("sorteio"):
        raise ValueError("nada sorteado ainda neste jogo")
    est["sorteio"]["revelado"] = bool(revelado)
    return _salvar(slug, p)


def tempo(slug: str, jid: str, segundos: int) -> dict:
    """O cronometro do impostor: comeca em TEMPO_PADRAO e anda de 30 em 30.

    O ajuste e gravado (o relogio correndo nao e) porque a mesa decide "esse
    aqui merece 3 minutos" e essa decisao tem que sobreviver ao F5.
    """
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    est["tempo"] = max(jogos.TEMPO_PASSO, min(int(segundos), 3600))
    return _salvar(slug, p)


def apagar(slug: str) -> bool:
    return store.apagar(store.PARTIDAS, slug)
