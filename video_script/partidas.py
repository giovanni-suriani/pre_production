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

E o placar e **por jogo**: `estado[jogo]["vidas"][participante]`. Cada jogo diz
com quantos coracoes a mesa entra nele, e o que foi gasto num jogo nao segue
pro proximo — voltar pro jogo anterior no meio do episodio encontra o placar
dele exatamente como ficou. Antes as vidas eram do participante e valiam o
episodio inteiro; um rank de quarenta minutos e um impostor de cinco nao tem
por que ter o mesmo tanto de coracao.
"""

from __future__ import annotations

import random

import jogos
import lixeira
import roteiros
import store


# ------------------------------------------------------------------ leitura

def listar() -> list[dict]:
    out = []
    for p in store.listar(store.PARTIDAS):
        p["n_participantes"] = len(p.get("participantes") or [])
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
    # o placar so existe de verdade dentro de um jogo; montar aqui deixa a tela
    # desenhar sem uma segunda ida ao servidor, e nao grava nada
    if r is not None:
        _ajustar_vidas(p, r)
    return p


# ------------------------------------------------------------------ escrita

def _ajustar_vidas(p: dict, r: dict) -> None:
    """Garante, em cada jogo, um coracao por vida que aquele jogo pede.

    Roda em toda leitura e em toda escrita, e por isso e idempotente: preserva
    o que ja foi gasto, enche o que falta e corta o que sobra. E assim que
    mudar "Vidas neste jogo" no meio do episodio funciona sem reiniciar — quem
    ja gastou continua gastado, e os coracoes novos entram cheios no fim da
    fila, do mesmo jeito que acontece com quem entra na mesa depois.
    """
    ids = [x["id"] for x in p.get("participantes") or []]
    estado = p.setdefault("estado", {})
    for j in r.get("jogos") or []:
        n = jogos.vidas(j.get("attrs") or {})
        velho = (estado.setdefault(j["id"], {}).get("vidas") or {})
        novo = {}
        for pid in ids:
            v = list(velho.get(pid) or [])
            if len(v) < n:
                v += [True] * (n - len(v))
            elif len(v) > n:
                v = v[:n]
            novo[pid] = v
        estado[j["id"]]["vidas"] = novo


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
    p = {
        "roteiro": slug,
        "criado": store.agora(),
        "jogo_idx": 0,
        "participantes": [{"id": x["id"], "nome": x["nome"]}
                          for x in r.get("participantes") or []],
        "estado": _brindes(r),
    }
    _ajustar_vidas(p, r)
    store.gravar(store.PARTIDAS, slug, p)
    return ler(slug)


def sincronizar(slug: str) -> dict:
    """Traz do roteiro quem entrou, quem saiu e quem mudou de nome, SEM mexer
    nas vidas ja gastas.

    Sem isto, acrescentar alguem na mesa no meio do episodio obrigaria a
    reiniciar e perder o placar. Quem chega entra com as vidas cheias em cada
    jogo; quem ja estava continua com o que gastou, jogo por jogo.
    """
    r = roteiros.ler(slug)
    if r is None:
        raise KeyError(slug)
    p = store.ler(store.PARTIDAS, slug)
    if p is None:
        return reiniciar(slug)

    p["participantes"] = [{"id": x["id"], "nome": x["nome"]}
                          for x in r.get("participantes") or []]

    # estado de jogo que nao existe mais no roteiro nao serve pra nada
    vivos = {j["id"] for j in r.get("jogos") or []}
    p["estado"] = {k: v for k, v in (p.get("estado") or {}).items()
                   if k in vivos}
    _ajustar_vidas(p, r)
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


def tocar_vida(slug: str, jid: str, pid: str, i: int) -> dict:
    """O clique num coracao. Alterna cheio <-> cinza, naquele jogo e indice."""
    p = _abrir(slug)
    r = roteiros.ler(slug)
    if r is None:
        raise KeyError(slug)
    _ajustar_vidas(p, r)
    vidas = ((p.get("estado") or {}).get(jid) or {}).get("vidas") or {}
    if pid not in vidas:
        raise KeyError(pid)
    if 0 <= i < len(vidas[pid]):
        vidas[pid][i] = not vidas[pid][i]
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
    """Zera SO aquele jogo: gabarito fechado, sorteio apagado, vidas cheias de
    novo — e os outros jogos do episodio intactos."""
    p = _abrir(slug)
    p.setdefault("estado", {})[jid] = {}
    r = roteiros.ler(slug)
    if r is not None:
        _ajustar_vidas(p, r)
    return _salvar(slug, p)


# ------------------------------------------------ estado por jogo (impostor)

def sortear_impostor(slug: str, jid: str) -> dict:
    """Sorteia QUEM sao os impostores e reparte as palavras, e guarda.

    O conteudo ja vem pronto do cadastro, e o layout inteiro e a rodada: a
    palavra da mesa e a coluna Jogador da LINHA 1, e cada impostor sorteado
    leva a coluna Impostor da sua linha, na ordem (1o impostor -> linha 1, 2o
    -> linha 2). Dois impostores recebem, portanto, palavras diferentes.

    O sorteio so escolhe as PESSOAS. Guardar e o ponto — quem apresenta
    precisa poder reabrir a tela no meio da rodada sem sortear tudo de novo e
    perder quem era o impostor.
    """
    p = _abrir(slug)
    cheia = ler(slug)
    j = next((x for x in cheia["jogos"] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    a = j.get("attrs") or {}

    pool = jogos.duplas(a)
    if not pool:
        raise ValueError("este jogo nao tem nenhuma palavra cadastrada — "
                         "escreva a linha Mesa/Impostor no painel da rodada")

    est = _estado_jogo(p, jid)
    # A palavra da mesa vem SEMPRE da linha 1: o layout inteiro e a rodada, e
    # nao um banco de onde sortear uma linha. Quem troca a rodada e quem
    # reescreve as linhas antes de clicar em Sortear.
    principal = pool[0]["jogador"]

    # quem ja morreu NESTE jogo nao e sorteado impostor nele; se ninguem
    # sobrou, sorteia entre todos em vez de recusar o sorteio no meio da mesa
    vidas_aqui = ((p.get("estado") or {}).get(jid) or {}).get("vidas") or {}
    todos = p.get("participantes") or []
    vivos = [x for x in todos if any(vidas_aqui.get(x["id"]) or [])]
    alvo = vivos or todos
    n_cfg = a.get("n_impostores")
    n_cfg = 1 if n_cfg is None else int(n_cfg)
    n = max(0, min(n_cfg, len(alvo)))
    impostores = [x["id"] for x in random.sample(alvo, n)] if n else []
    palavras = {pid: (pool[k]["impostor"] if k < len(pool) else "")
                for k, pid in enumerate(impostores)}

    est["sorteio"] = {
        "principal": principal,
        # `impostor` continua aqui pelo par de cima da tela e por sorteio ja
        # gravado que so tinha esta chave: e a palavra do PRIMEIRO impostor.
        "impostor": pool[0]["impostor"],
        "impostores": impostores, "palavras": palavras,
        "em": store.agora(),
    }
    est.setdefault("log", []).append({"acao": "sortear", "em": store.agora()})
    return _salvar(slug, p)


def incrementar_rodada(slug: str, jid: str) -> dict:
    """+1 no contador manual de rodada do impostor_palavra.

    E o numero que quem apresenta bate na tela, de proposito manual — o clique
    e o unico jeito de mexer nele. O sorteio nao encosta aqui.
    """
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    est["rodada"] = int(est.get("rodada") or 0) + 1
    return _salvar(slug, p)


def tempo(slug: str, jid: str, segundos: int) -> dict:
    """O cronometro do impostor: comeca em TEMPO_PADRAO e anda de 30 em 30.

    O ajuste e gravado (o relogio correndo nao e) porque a mesa decide "esse
    aqui merece 3 minutos" e essa decisao tem que sobreviver ao F5.
    """
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    est["tempo"] = max(jogos.TEMPO_PASSO, min(int(segundos), jogos.TEMPO_TETO))
    return _salvar(slug, p)


# ------------------------------------------ estado por jogo (so resposta errada)

def _ordem_errada(est: dict, n: int) -> list[int]:
    """Quais perguntas aparecem, e em que ordem.

    As perguntas sao identificadas pelo indice na lista do jogo. Editar a lista
    no meio da partida (que a aba 3 deixa fazer) pode mexer nesses indices —
    e a mesma ressalva do rank, que guarda o revelado por numero de posicao.
    Por isso a ordem gravada e filtrada e completada aqui, toda vez: indice que
    nao existe mais cai fora, pergunta nova entra no fim.

    As `escondidas` (marcadas antes de um embaralho) ficam de fora da tela, mas
    NAO saem do cadastro: "Trazer todas de volta" devolve o jogo inteiro.
    """
    fora = {int(x) for x in (est.get("escondidas") or [])}
    vistos, ordem = set(), []
    for i in est.get("ordem") or []:
        i = int(i)
        if 0 <= i < n and i not in vistos and i not in fora:
            vistos.add(i)
            ordem.append(i)
    ordem += [i for i in range(n) if i not in vistos and i not in fora]
    return ordem


def marcar_errada(slug: str, jid: str, i: int) -> dict:
    """O clique na bolinha: liga/desliga "esta ja saiu certa".

    Alterna em vez de so marcar, pelo mesmo motivo do coracao: na gravacao se
    clica na linha errada, e desfazer tem que ser clicar de novo no mesmo
    lugar, nao procurar um botao de desfazer.
    """
    p = _abrir(slug)
    est = _estado_jogo(p, jid)
    certas = set(int(x) for x in (est.get("certas") or []))
    i = int(i)
    certas.symmetric_difference_update({i})
    est["certas"] = sorted(certas)
    return _salvar(slug, p)


def moeda_errada(slug: str, jid: str, i: int, participante: str) -> dict:
    """A moeda de UMA pessoa numa pergunta: liga/desliga.

    Guardado como `moedas[<i da pergunta>] = [ids das pessoas]`, e nao como um
    placar somado: assim da pra ver de quem foi cada ponto, desfazer o clique
    errado no lugar onde ele foi dado, e o total continua sendo uma conta
    (quantas vezes a pessoa aparece) em vez de um numero que pode divergir do
    que esta na tela.

    A pergunta jogada na lixeira leva as moedas dela junto — ver `lixo_errada`.
    """
    p = _abrir(slug)
    if not any(x.get("id") == participante for x in p.get("participantes") or []):
        raise KeyError(participante)
    est = _estado_jogo(p, jid)
    moedas = est.setdefault("moedas", {})
    chave = str(int(i))
    quem = [str(x) for x in (moedas.get(chave) or [])]
    if participante in quem:
        quem.remove(participante)
    else:
        quem.append(participante)
    if quem:
        moedas[chave] = quem
    else:
        moedas.pop(chave, None)
    return _salvar(slug, p)


def embaralhar_errada(slug: str, jid: str) -> dict:
    """Embaralha as que faltam e TIRA DA TELA as que foram marcadas.

    Marcada e a que tem check na mao OU moeda de alguem — dar a moeda ja diz
    que a pergunta saiu, e pedir os dois cliques seria pedir a mesma coisa
    duas vezes com a camera ligada.

    O embaralho e o fim de uma rodada: o que ja saiu sai da frente, e o que
    falta volta numa ordem nova. As marcadas vao para `escondidas` — some da
    tela, continua no cadastro do jogo — e a marcacao em si e limpa, porque a
    unica coisa verde na tela passa a ser o que foi marcado nesta rodada.

    Nada e apagado: "Trazer todas de volta" (o mesmo zerar_jogo) devolve tudo.
    Apagar pergunta de cadastro no meio da gravacao seria um caminho sem volta
    a um clique de distancia, e a tela roda com a camera ligada.
    """
    p = _abrir(slug)
    cheia = ler(slug)
    j = next((x for x in cheia["jogos"] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    n = len(jogos.perguntas(j.get("attrs") or {}))
    if not n:
        raise ValueError("este jogo nao tem pergunta cadastrada — "
                         "escreva ou importe no conteudo do jogo")

    est = _estado_jogo(p, jid)
    certas = {int(x) for x in (est.get("certas") or []) if 0 <= int(x) < n}
    certas |= {int(k) for k, quem in (est.get("moedas") or {}).items()
               if quem and 0 <= int(k) < n}
    escondidas = {int(x) for x in (est.get("escondidas") or []) if 0 <= int(x) < n}
    escondidas |= certas

    faltam = [i for i in range(n) if i not in escondidas]
    random.shuffle(faltam)
    est["ordem"] = faltam
    est["escondidas"] = sorted(escondidas)
    est["certas"] = []
    est.setdefault("log", []).append(
        {"acao": "embaralhar", "sairam": sorted(certas), "em": store.agora()})
    return _salvar(slug, p)


def _deslocar(est: dict, i: int) -> None:
    """Tira o indice `i` do estado e puxa todo mundo acima dele um pra tras.

    As perguntas sao identificadas pela posicao na lista, entao tirar uma do
    meio renumera as de baixo. Sem isto, jogar a 3ª no lixo faria a marcacao da
    4ª passar a apontar pra 5ª — e no meio da gravacao ninguem ia entender por
    que a linha errada ficou verde.
    """
    def mexer(nums):
        return sorted({(x - 1 if x > i else x)
                       for x in (int(n) for n in nums or []) if x != i})

    est["certas"] = mexer(est.get("certas"))
    est["escondidas"] = mexer(est.get("escondidas"))
    moedas = {}
    for k, quem in (est.get("moedas") or {}).items():
        k = int(k)
        if k == i:
            continue
        moedas[str(k - 1 if k > i else k)] = quem
    est["moedas"] = moedas
    vistos, ordem = set(), []
    for n in est.get("ordem") or []:
        n = int(n)
        if n == i:
            continue
        n = n - 1 if n > i else n
        if n not in vistos:
            vistos.add(n)
            ordem.append(n)
    est["ordem"] = ordem


def lixo_errada(slug: str, jid: str, i: int) -> dict:
    """Joga a pergunta na lixeira: sai do jogo e vai pro arquivo de descarte.

    E o unico caminho da tela que MEXE NO CADASTRO durante a gravacao, e por
    isso passa pela lixeira: a linha sai do roteiro, mas fica anotada com o
    .txt de onde veio — e assim da pra tirar ela da origem depois, em vez de
    reimportar o mesmo problema no proximo episodio.
    """
    cheia = ler(slug)
    if cheia is None:
        raise KeyError(slug)
    j = next((x for x in cheia["jogos"] if x.get("id") == jid), None)
    if j is None:
        raise KeyError(jid)
    lista = jogos.perguntas(j.get("attrs") or {})
    i = int(i)
    if not 0 <= i < len(lista):
        raise ValueError("essa pergunta nao existe mais neste jogo")

    alvo = lista[i]
    lixeira.jogar(alvo["pergunta"], alvo["resposta"], alvo["origem"],
                  roteiro=slug, jogo=j.get("nome") or "")
    roteiros.salvar_jogo(slug, jid, None,
                         {"perguntas": [x for k, x in enumerate(lista) if k != i]})

    p = _abrir(slug)
    _deslocar(_estado_jogo(p, jid), i)
    return _salvar(slug, p)


def apagar(slug: str) -> bool:
    return store.apagar(store.PARTIDAS, slug)
