"""video_script — servico do roteiro dos episodios (porta 8741).

Tres abas. O **roteiro** e o centro: ele guarda quem joga, quais jogos, e em
que ordem.

  1. /roteiro   Roteiro  — participantes + os jogos do episodio  (tela inicial)
  2. /jogo      Jogos    — edita UM jogo do roteiro (o clique no jogo leva aqui)
  3. /in-game   In-game  — a mesa jogando aquele roteiro

Servico separado do pre_production (8740) de proposito: aquele app cuida do
corte e da legenda de um episodio JA gravado, este cuida do episodio que ainda
vai ser gravado. Compartilham a aparencia (o shell.css vem montado em /shared)
e o venv, nada mais.

Roda com:  video_script\\run.bat
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

import jogos          # noqa: E402
import lixeira       # noqa: E402
import partidas       # noqa: E402
import roteiros       # noqa: E402
import store          # noqa: E402

STATIC = RAIZ / "static"
COMPARTILHADO = RAIZ.parent / "src" / "static"   # shell.css/shell.js do 8740
PORTA = 8741

app = FastAPI(title="video_script")
store.preparar()


@app.middleware("http")
async def sem_cache(request, call_next):
    """O navegador nao pode guardar o .js/.css desta casa.

    Isto roda na rede de casa e muda o dia inteiro: com o cache normal do Chrome,
    uma correcao no `roteiro.js` so aparecia depois de um Ctrl+F5 — e o jeito
    de descobrir isso e achar que o conserto nao funcionou. Em rede local nao
    ha nada a economizar aqui.
    """
    resp = await call_next(request)
    if request.url.path.startswith(("/static/", "/shared/")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def pagina(nome: str) -> FileResponse:
    return FileResponse(STATIC / nome, media_type="text/html; charset=utf-8")


def achar(valor, oque: str):
    """404 com o nome do que faltou, em vez de um 500 mudo la na frente."""
    if valor is None:
        raise HTTPException(404, f"{oque} nao encontrado")
    return valor


def _acao(fn, *a, **kw):
    """KeyError -> 404, ValueError -> 400. Sem isto, um jogo que nao existe
    vira 500 e a tela mostra 'Internal Server Error' no meio da gravacao."""
    try:
        return fn(*a, **kw)
    except KeyError as e:
        raise HTTPException(404, f"{e.args[0]!r} nao encontrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ telas

@app.get("/")
def raiz():
    # O roteiro e a porta de entrada: sem ele nao ha jogo nem partida.
    return RedirectResponse("/roteiro")


@app.get("/roteiro")
def tela_roteiro():
    return pagina("roteiro.html")


@app.get("/jogo")
def tela_jogo():
    return pagina("jogo.html")


@app.get("/in-game")
def tela_in_game():
    return pagina("in_game.html")


# ------------------------------------------------------------------- tipos

@app.get("/api/tipos")
def api_tipos():
    """O catalogo de tipos com os campos de cada um. A tela monta o formulario
    a partir disto, entao campo novo em jogos.TIPOS aparece sozinho la."""
    return {"tipos": [{"tipo": t, **d} for t, d in jogos.TIPOS.items()],
            "tempo_padrao": jogos.TEMPO_PADRAO, "tempo_passo": jogos.TEMPO_PASSO}


@app.get("/api/lixeira")
def api_lixeira():
    """O que foi jogado fora, com o .txt de origem de cada linha.

    Nao ha tela pra isto de proposito: a lixeira e pra consultar depois da
    gravacao, na hora de limpar o arquivo de origem — e uma tela a mais seria
    uma tela a mais pra manter.
    """
    return {"itens": lixeira.listar()}


@app.post("/api/parse-lista-rank")
def api_parse_lista(body: dict = Body(...)):
    """O conteudo do lista_do_rank.txt -> itens do rank.

    O arquivo e lido pelo navegador (FileReader) e chega aqui como texto, nao
    como upload: sem multipart o servico nao precisa do python-multipart, e
    funciona igual com voce colando a lista da web direto na caixa.
    """
    itens = jogos.parse_lista_rank(body.get("texto") or "")
    return {"itens": itens, "n": len(itens)}


# ---------------------------------------------------------------- roteiros

@app.get("/api/roteiros")
def api_roteiros():
    return {"roteiros": roteiros.listar()}


@app.post("/api/roteiros")
def api_roteiro_criar(body: dict = Body(...)):
    return roteiros.criar(body.get("nome") or "")


@app.get("/api/roteiros/{slug}")
def api_roteiro(slug: str):
    return achar(roteiros.ler(slug), f"roteiro {slug!r}")


@app.put("/api/roteiros/{slug}")
def api_roteiro_salvar(slug: str, body: dict = Body(...)):
    return _acao(roteiros.salvar, slug, body)


@app.delete("/api/roteiros/{slug}")
def api_roteiro_apagar(slug: str):
    if not roteiros.apagar(slug):
        raise HTTPException(404, f"roteiro {slug!r} nao encontrado")
    return JSONResponse(status_code=204, content=None)


# ------------------------------------------------------ os jogos do roteiro

@app.post("/api/roteiros/{slug}/jogos")
def api_jogo_criar(slug: str, body: dict = Body(...)):
    return _acao(roteiros.add_jogo, slug, body.get("tipo") or "",
                 body.get("nome") or "")


@app.get("/api/roteiros/{slug}/jogos/{jid}")
def api_jogo(slug: str, jid: str):
    return achar(roteiros.ler_jogo(slug, jid), f"jogo {jid!r}")


@app.put("/api/roteiros/{slug}/jogos/{jid}")
def api_jogo_salvar(slug: str, jid: str, body: dict = Body(...)):
    return _acao(roteiros.salvar_jogo, slug, jid, body.get("nome"),
                 body.get("attrs"))


@app.delete("/api/roteiros/{slug}/jogos/{jid}")
def api_jogo_apagar(slug: str, jid: str):
    return _acao(roteiros.apagar_jogo, slug, jid)


# ---------------------------------------------------------------- partidas

@app.get("/api/partidas")
def api_partidas():
    return {"partidas": partidas.listar()}


@app.post("/api/partidas/{slug}/abrir")
def api_partida_abrir(slug: str):
    """O botao "Jogar roteiro": continua a partida daquele roteiro, ou comeca
    uma com os participantes dele."""
    return _acao(partidas.abrir, slug)


@app.get("/api/partidas/{slug}")
def api_partida(slug: str):
    return achar(partidas.ler(slug), f"partida de {slug!r}")


@app.post("/api/partidas/{slug}/reiniciar")
def api_partida_reiniciar(slug: str):
    return _acao(partidas.reiniciar, slug)


@app.delete("/api/partidas/{slug}")
def api_partida_apagar(slug: str):
    if not partidas.apagar(slug):
        raise HTTPException(404, f"partida de {slug!r} nao encontrada")
    return JSONResponse(status_code=204, content=None)


@app.post("/api/partidas/{slug}/vida")
def api_partida_vida(slug: str, body: dict = Body(...)):
    return _acao(partidas.tocar_vida, slug, body.get("jogo") or "",
                 body.get("participante") or "",
                 int(body.get("indice") or 0))


@app.post("/api/partidas/{slug}/jogo")
def api_partida_jogo(slug: str, body: dict = Body(...)):
    return _acao(partidas.ir_para, slug, int(body.get("idx") or 0))


@app.post("/api/partidas/{slug}/buscar")
def api_partida_buscar(slug: str, body: dict = Body(...)):
    """As duas caixas de busca do adivinha-rank: por nome ou por posicao.

    Uma rota so para as duas porque as duas fazem a mesma coisa com a mesma
    consequencia (revelar aquela linha do gabarito) — o que muda e so como a
    linha foi achada.
    """
    p = achar(partidas.ler(slug), f"partida de {slug!r}")
    jid = body.get("jogo") or ""
    j = next((x for x in p["jogos"] if x.get("id") == jid), None)
    if j is None:
        raise HTTPException(404, f"jogo {jid!r} nao esta neste roteiro")
    if j.get("in_game") != "rank":
        raise HTTPException(400, "busca so vale no adivinha rank em lista")

    a = j.get("attrs") or {}
    lista = a.get("lista") or []
    por = (body.get("por") or "nome").lower()
    termo = str(body.get("termo") or "").strip()
    if not termo:
        raise HTTPException(400, "digite algo para buscar")

    if por == "rank":
        try:
            pos = int(termo)
        except ValueError:
            raise HTTPException(400, f"{termo!r} nao e um numero de posicao")
        achados = [i for i in lista if int(i.get("pos") or 0) == pos]
    else:
        achados = jogos.buscar_na_lista(lista, termo,
                                        bool(a.get("aceita_parcial", True)))

    quem = body.get("quem") or ""
    if not achados:
        return {"achados": [], "partida": partidas.errou(slug, jid, termo, quem)}
    return {"achados": achados,
            "partida": partidas.revelar(slug, jid, [i["pos"] for i in achados],
                                        quem, termo)}


@app.post("/api/partidas/{slug}/esconder")
def api_partida_esconder(slug: str, body: dict = Body(...)):
    return _acao(partidas.esconder, slug, body.get("jogo") or "",
                 int(body.get("pos") or 0))


@app.post("/api/partidas/{slug}/zerar-jogo")
def api_partida_zerar(slug: str, body: dict = Body(...)):
    return _acao(partidas.zerar_jogo, slug, body.get("jogo") or "")


@app.post("/api/partidas/{slug}/sortear")
def api_partida_sortear(slug: str, body: dict = Body(...)):
    return _acao(partidas.sortear_impostor, slug, body.get("jogo") or "")


@app.post("/api/partidas/{slug}/errada-marcar")
def api_partida_errada_marcar(slug: str, body: dict = Body(...)):
    """A bolinha do "So resposta errada": liga/desliga aquela pergunta."""
    return _acao(partidas.marcar_errada, slug, body.get("jogo") or "",
                 int(body.get("i") or 0))


@app.post("/api/partidas/{slug}/errada-moeda")
def api_partida_errada_moeda(slug: str, body: dict = Body(...)):
    """A moeda de uma pessoa numa pergunta do "So resposta errada"."""
    return _acao(partidas.moeda_errada, slug, body.get("jogo") or "",
                 body.get("i"), body.get("participante") or "")


@app.post("/api/partidas/{slug}/errada-lixo")
def api_partida_errada_lixo(slug: str, body: dict = Body(...)):
    """Tira a pergunta do jogo e anota na lixeira (com o .txt de origem)."""
    return _acao(partidas.lixo_errada, slug, body.get("jogo") or "",
                 int(body.get("i") or 0))


@app.post("/api/partidas/{slug}/errada-embaralhar")
def api_partida_errada_shuffle(slug: str, body: dict = Body(...)):
    return _acao(partidas.embaralhar_errada, slug, body.get("jogo") or "")


@app.post("/api/partidas/{slug}/rodada")
def api_partida_rodada(slug: str, body: dict = Body(...)):
    return _acao(partidas.incrementar_rodada, slug, body.get("jogo") or "")


@app.post("/api/partidas/{slug}/tempo")
def api_partida_tempo(slug: str, body: dict = Body(...)):
    # `or` aqui seria errado: 0 e falso, e um "-30s" que chega em zero viraria
    # o tempo padrao em vez de bater no piso de 30s.
    seg = body.get("segundos")
    seg = jogos.TEMPO_PADRAO if seg is None else int(seg)
    return _acao(partidas.tempo, slug, body.get("jogo") or "", seg)


# ------------------------------------------------------------------ estatico

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
if COMPARTILHADO.is_dir():
    # o shell.css e o shell.js do pre_production, sem copia: uma mudanca de
    # aparencia la aparece aqui, e nao existe versao deste arquivo divergindo.
    app.mount("/shared", StaticFiles(directory=str(COMPARTILHADO)),
              name="shared")


def ip_da_lan() -> str:
    """O IP desta maquina na rede de casa, pra imprimir o link do notebook.

    O truque do socket UDP nao manda pacote nenhum: o `connect` so faz o
    sistema escolher qual interface usaria pra falar com a internet, e e a
    unica forma confiavel de saber isso numa maquina com WSL/VPN/Docker, onde
    `gethostbyname(hostname)` devolve o adaptador errado na metade das vezes.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"          # sem rede: o link local ainda serve
    finally:
        s.close()


def main() -> None:
    import uvicorn
    porta = PORTA
    argv = sys.argv[1:]
    if "--port" in argv:
        porta = int(argv[argv.index("--port") + 1])

    # `0.0.0.0` = qualquer interface, e nao um endereco: sem isto o kernel
    # recusa (RST) quem chega pela placa de rede antes de o pedido virar
    # request, e o notebook leva "conexao recusada" com o firewall liberado.
    # `--local` volta ao loopback pra quando o servico rodar fora de casa.
    host = "127.0.0.1" if "--local" in argv else "0.0.0.0"

    print(f"video_script em http://127.0.0.1:{porta}  (dados em {store.DADOS})")
    if host != "127.0.0.1":
        print(f"            no notebook:  http://{ip_da_lan()}:{porta}")
    uvicorn.run(app, host=host, port=porta, log_level="warning")


if __name__ == "__main__":
    main()
