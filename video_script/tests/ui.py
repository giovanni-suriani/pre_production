"""Interface: dirige as tres abas do video_script num Chrome headless.

Precisa do servidor de pe (video_script\\run.bat). Monta um episodio pela tela,
do jeito que se monta de verdade — cria o roteiro, digita a mesa, adiciona os
jogos, importa a lista, joga — e no fim apaga o que criou. Ouve o console do
navegador: um erro de javascript derruba o teste, que e o jeito de descobrir
uma tela em branco que o servidor nunca ve.

As imagens de cada tela ficam em tests\\_telas\\.
"""
import json
import sys
import urllib.request as u
from pathlib import Path

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8741"
OUT = Path(__file__).parent / "_telas"
OUT.mkdir(exist_ok=True)


def req(m, p, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = u.Request(B + p, data=d, method=m,
                  headers={"Content-Type": "application/json"})
    with u.urlopen(r) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


PERGUNTAS = """# as linhas com # sao ignoradas
Capital do Japao | Toquio
Quem pintou a Mona Lisa | Da Vinci
Maior planeta do sistema solar | Jupiter

Quantas patas tem uma aranha | 8
Rio que corta o Egito | Nilo
Quem escreveu Dom Casmurro | Machado de Assis
"""

LISTA = "\n".join([
    "1. Neymar — 222 mi", "2. Mbappe — 180 mi", "3. Coutinho — 145 mi",
    "4. Dembele — 140 mi", "5. Cristiano Ronaldo — 117 mi", "6. Griezmann — 120 mi",
])

# A lixeira e do servico inteiro, e nao do roteiro: apagar o roteiro no fim nao
# a limpa. Entao o teste guarda o arquivo antes e devolve no fim — senao cada
# rodada sujaria a lixeira de verdade com "pergunta 3".
LIXEIRA = Path(__file__).resolve().parent.parent / "dados" / "lixeira_perguntas.json"
LIXEIRA_ANTES = LIXEIRA.read_bytes() if LIXEIRA.exists() else None


def devolver_lixeira():
    if LIXEIRA_ANTES is None:
        LIXEIRA.unlink(missing_ok=True)
    else:
        LIXEIRA.write_bytes(LIXEIRA_ANTES)


erros = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1500, "height": 1000})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}")
          if m.type == "error" else None)

    def foto(nome):
        pg.wait_for_timeout(350)
        pg.screenshot(path=str(OUT / nome), full_page=True)

    # ---------------------------------------------------------- aba 1: roteiro
    pg.goto(B + "/")
    assert pg.url.endswith("/roteiro"), pg.url          # a raiz leva ao roteiro
    pg.fill("#nName", "Ep 04 — rank e impostor")
    pg.click("#nCriar")
    pg.wait_for_selector("#det:not(.hidden)")
    slug = pg.evaluate("new URLSearchParams(location.search).get('roteiro')")
    print(f"[ok] raiz -> /roteiro; roteiro criado ({slug})")

    # a mesa mora no roteiro
    for nome in ("Gi", "He", "Enzo"):
        pg.click("#dAddPart")
        pg.locator("#dParts .part").last.locator(".nm").fill(nome)
    assert pg.locator("#dParts .part").count() == 3
    # as vidas sairam daqui: sao de cada jogo, nao da pessoa
    assert pg.locator("#dParts .vd").count() == 0, "voltou vida no participante"
    assert pg.locator("#dParts .vida").count() == 0
    print("[ok] aba Roteiro: 3 participantes, sem vida na pessoa")

    # os jogos entram pelos chips de tipo
    pg.click("#dTipos .chip:has-text('Adivinha rank em lista')")
    pg.wait_for_selector("#dJogos .jogo")
    pg.click("#dTipos .chip:has-text('Impostor na palavra')")
    pg.wait_for_timeout(500)
    assert pg.locator("#dJogos .jogo").count() == 2
    assert pg.locator("#dJogos .badge.warn").count() == 2   # sem conteudo ainda
    assert "Jogos do roteiro" in pg.inner_text("#det")
    print("[ok] aba Roteiro: 2 jogos dentro do roteiro, marcados como pendentes")

    pg.locator("#dJogos .jogo").first.locator(".dur").fill("14")
    pg.locator("#dJogos .jogo").first.locator(".dur").dispatch_event("change")
    pg.click("#dSalvar")
    pg.wait_for_timeout(800)
    foto("01_roteiro.png")

    # ------------------------------------------------------------ aba 2: jogo
    pg.locator("#dJogos .jogo").first.locator(".abrir").click()
    pg.wait_for_selector("#dRank:not(.hidden)")
    assert "/jogo?" in pg.url, pg.url
    print("[ok] clicar no jogo do roteiro leva pra aba Jogos daquele jogo")

    pg.fill("#dNomeIn", "Rank das transferencias")
    pg.fill("#dCola", LISTA)
    pg.click("#dParse")
    pg.wait_for_selector("#dPrev .linha")
    assert pg.locator("#dPrev .linha").count() == 6
    # os campos que sairam nao podem ter voltado
    txt = pg.inner_text("#dCampos")
    for morto in ("Regras", "Dica", "Discuss", "Vidas sugeridas"):
        assert morto not in txt, morto
    # as vidas deste jogo, que e onde elas moram agora
    vd = pg.locator("#dCampos .field:has-text('Vidas neste jogo') input")
    assert vd.input_value() == "2", vd.input_value()      # o padrao
    vd.fill("3")
    vd.dispatch_event("change")
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    foto("02_jogo_rank.png")
    print("[ok] aba Jogos: lista importada, 3 vidas neste jogo, sem regras/dica")

    # o outro jogo, pela volta ao roteiro
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.locator("#dJogos .jogo").nth(1).locator(".abrir").click()
    pg.wait_for_selector(".duplas")
    # a caixa de colar substitui a lista inteira — e como se cadastra em lote
    pg.click(".duplas .colar summary")
    pg.fill(".duplas .tudo", "pamonha | quentao\npe de moleque | canjica")
    pg.click(".duplas .aplicar")
    pg.wait_for_timeout(400)
    assert pg.locator(".duplas .ln").count() == 2
    # e a linha nova, digitada a mao, e o caso do dia a dia
    pg.click(".duplas .add")
    pg.locator(".duplas .ln").nth(2).locator(".a").fill("cural")
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    jid_pal = req("GET", f"/api/roteiros/{slug}")["jogos"][1]["id"]
    dup = req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]["duplas"]
    assert dup == [{"jogador": "pamonha", "impostor": "quentao"},
                   {"jogador": "pe de moleque", "impostor": "canjica"},
                   {"jogador": "cural", "impostor": ""}], dup
    print("[ok] aba Jogos: duplas do impostor coladas em lote e digitadas a mao")

    # --- terceiro jogo: impostor no quadro. Quadro aqui e o NOME do quadro,
    # texto como o resto — nao ha mais imagem nenhuma no servico.
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.click("#dTipos .chip:has-text('Impostor no quadro')")
    pg.wait_for_timeout(500)
    pg.locator("#dJogos .jogo").nth(2).locator(".abrir").click()
    pg.wait_for_selector(".duplas")
    assert pg.locator("input[type=file]").count() == 1,         "sobrou um seletor de imagem na aba Jogos (so o do lista_do_rank.txt fica)"
    pg.click(".duplas .colar summary")
    pg.fill(".duplas .tudo", "monalisa | guernica\no grito | girassois")
    pg.click(".duplas .aplicar")
    pg.wait_for_timeout(400)
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    foto("06_jogo_duplas.png")
    print("[ok] aba Jogos: o impostor no quadro e so texto — nenhuma imagem")

    # --- quarto jogo: discussao, so tema e relogio
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.click("#dTipos .chip:has-text('Discussao')")
    pg.wait_for_timeout(500)
    pg.locator("#dJogos .jogo").nth(3).locator(".abrir").click()
    pg.wait_for_selector("#dCampos textarea")
    campos = pg.inner_text("#dCampos")
    assert "Tema da discuss" in campos and "Tempo (minutos)" in campos, campos
    minutos_in = pg.locator("#dCampos .field:has-text('Tempo (minutos)') input")
    assert minutos_in.input_value() == "10", minutos_in.input_value()
    pg.locator("#dCampos textarea").first.fill("IA vai roubar o emprego de todo mundo?")
    pg.locator("#dCampos textarea").first.dispatch_event("change")
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    print("[ok] aba Jogos: discussao com tema e 10 min de padrao")

    # --- quinto jogo: so resposta errada, importando um .txt de verdade
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.click("#dTipos .chip:has-text('So resposta errada')")
    pg.wait_for_timeout(500)
    pg.locator("#dJogos .jogo").nth(4).locator(".abrir").click()
    pg.wait_for_selector(".duplas .imp")
    pg.set_input_files(".duplas .arq", {
        "name": "perguntas.txt", "mimeType": "text/plain",
        "buffer": PERGUNTAS.encode("utf-8")})
    pg.wait_for_timeout(700)
    assert pg.locator(".duplas .ln").count() == 6, pg.locator(".duplas .ln").count()
    # a linha comentada (#) e a vazia nao viraram pergunta
    assert pg.locator(".duplas .ln").nth(0).locator(".a").input_value()         == "Capital do Japao"
    assert pg.locator(".duplas .ln").nth(0).locator(".b").input_value() == "Toquio"
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    foto("11_jogo_perguntas.png")
    print("[ok] aba Jogos: 6 perguntas importadas de um .txt pelo navegador")

    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    assert pg.locator("#dJogos .badge.warn").count() == 0
    print("[ok] com conteudo cadastrado, as pendencias somem do roteiro")

    # -------------------------------------------------------- aba 3: in-game
    pg.click("#dJogar")
    pg.wait_for_selector("#jogo:not(.hidden)", timeout=8000)
    assert "/in-game?roteiro=" in pg.url, pg.url
    assert pg.locator(".jogador").count() == 3
    # 3 pessoas x 3 vidas do jogo 1 (o rank), que e o que abre primeiro
    assert pg.locator("#gMesa .vida").count() == 9
    assert "ponto" not in pg.inner_text("#gMesa").lower()   # pontuacao saiu
    assert "Jogos do roteiro" in pg.inner_text("#jogo")
    print("[ok] 'Jogar roteiro' abre a partida direto — sem tela de montar mesa")
    print("[ok] in-game: sem pontuacao, e 'Jogos do roteiro' no lugar de 'Passos'")

    caixa = pg.locator("#gMesa .vida").first.bounding_box()
    assert 43 <= caixa["width"] <= 47, caixa
    print(f"[ok] coracao com {round(caixa['width'])}px (era 30px — 1.5x)")

    gi = pg.locator(".jogador").first
    gi.locator(".vida").nth(2).click()
    pg.wait_for_timeout(600)
    assert "morta" in (gi.locator(".vida").nth(2).get_attribute("class") or "")
    disco = req("GET", f"/api/partidas/{slug}")
    jid_rank = disco["jogos"][0]["id"]
    pid_gi = disco["participantes"][0]["id"]
    assert disco["estado"][jid_rank]["vidas"][pid_gi] == [True, True, False]
    print("[ok] clique no coracao virou cinza E gravou no disco")

    # o placar e por jogo: o impostor tem as suas 2 vidas, todas cheias
    pg.locator("#gChips .chip").nth(1).click()
    pg.wait_for_timeout(700)
    assert pg.locator("#gMesa .vida").count() == 6, "o jogo 2 nao tem 2 vidas"
    assert pg.locator("#gMesa .vida.morta").count() == 0, "a vida gasta vazou"
    foto("09_ingame_vidas_por_jogo.png")
    pg.locator("#gChips .chip").first.click()
    pg.wait_for_timeout(700)
    assert pg.locator("#gMesa .vida.morta").count() == 1, "voltar perdeu o placar"
    print("[ok] cada jogo com o seu placar: 2 vidas no impostor, a gasta so no rank")

    pg.fill(".bNome", "neymar")
    pg.press(".bNome", "Enter")
    pg.wait_for_selector(".holofote")
    assert "Neymar" in pg.inner_text(".holofote")
    pg.fill(".bRank", "5")
    pg.press(".bRank", "Enter")
    pg.wait_for_timeout(700)
    assert "Cristiano Ronaldo" in pg.inner_text(".holofote")
    assert pg.locator(".linha.aberta").count() == 2
    assert pg.locator(".linha.fechada").count() == 4
    foto("03_ingame_rank.png")
    print("[ok] as duas buscas revelam; 4 posicoes seguem fechadas")

    # impostor + cronometro
    pg.locator("#gChips .chip").nth(1).click()
    pg.wait_for_timeout(600)
    assert pg.inner_text(".cron") == "02:00", pg.inner_text(".cron")
    pg.click(".mais")
    pg.wait_for_timeout(600)
    assert pg.inner_text(".cron") == "02:30", pg.inner_text(".cron")
    pg.click(".menos")
    pg.wait_for_timeout(500)
    pg.click(".menos")
    pg.wait_for_timeout(700)
    assert pg.inner_text(".cron") == "01:30", pg.inner_text(".cron")
    print("[ok] discussao comeca em 02:00 e anda de 30 em 30 (+30/-30)")
    jid = disco["jogos"][1]["id"]
    assert req("GET", f"/api/partidas/{slug}")["estado"][jid]["tempo"] == 90
    print("[ok] o ajuste do tempo fica gravado no disco")

    pg.click(".sortear")
    pg.wait_for_selector(".palco")
    # sortear ja mostra: o clique a mais pra descobrir quem era virava atrito
    assert pg.locator(".palco.fechado").count() == 0, "o sorteio nasceu tapado"
    assert pg.locator(".palco .par").is_visible()
    par = pg.inner_text(".palco .par")
    assert ("pamonha" in par and "quentao" in par)         or ("pe de moleque" in par and "canjica" in par)         or "cural" in par, par
    # a lista por pessoa: cada nome com o que ele ouviu, e so um impostor
    assert pg.locator(".cadaum .pessoa").count() == 3
    assert pg.locator(".cadaum .pessoa.imp").count() == 1
    foto("07_ingame_sorteio.png")
    imp = pg.inner_text(".cadaum .pessoa.imp")
    assert "(impostor)" in imp, imp
    # a mesa ja marca quem e, sem segundo botao: o sorteio e a revelacao
    assert pg.locator(".btn.revelar").count() == 0, "o botao Revelar voltou"
    assert pg.locator(".jogador.impostor").count() == 1
    foto("04_ingame_impostor.png")
    # a tampa continua existindo pra esconder DEPOIS, e o tapado sobrevive
    # ao redesenho que toda acao faz
    pg.click(".palco .tampa")
    pg.wait_for_timeout(300)
    assert not pg.locator(".palco .par").is_visible()
    pg.click(".mais")
    pg.wait_for_timeout(600)
    assert pg.locator(".palco.fechado").count() == 1, "o redesenho reabriu"
    pg.click(".palco .tampa")
    pg.wait_for_timeout(300)
    print(f"[ok] sortear ja mostra ({par.strip()}) e marca a mesa, sem botao "
          f"de revelar; a tampa esconde depois e sobrevive ao redesenho")

    # --- editar o conteudo DENTRO do in-game, sem sair da tela
    # impostor: acrescentar uma dupla sem sair do in-game
    pg.locator("#gChips .chip").nth(1).click()
    pg.wait_for_timeout(600)
    pg.click("button:has-text('Editar aqui')")
    pg.wait_for_selector(".duplas .add")
    antes = pg.locator(".duplas .ln").count()
    pg.click(".duplas .add")
    pg.locator(".duplas .ln").nth(antes).locator(".a").fill("bolo de fuba")
    pg.locator(".duplas .ln").nth(antes).locator(".b").fill("cuscuz")
    # as duplas so vao pro disco no clique: digitar nao grava sozinho
    jid_pal = disco["jogos"][1]["id"]
    assert len(req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]["duplas"]) == antes
    pg.click("button:has-text('Gravar as duplas')")
    pg.wait_for_timeout(900)
    assert "/jogo?" not in pg.url, "saiu da tela do in-game"
    dup = req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]["duplas"]
    assert dup[-1] == {"jogador": "bolo de fuba", "impostor": "cuscuz"}, dup
    print("[ok] in-game: dupla acrescentada ali mesmo, gravada no roteiro")

    # o numero de impostores, ao contrario das duplas, e um clique so e grava
    pg.locator(".nImp").fill("2")
    pg.locator(".nImp").dispatch_event("change")
    pg.wait_for_timeout(900)
    assert req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]["n_impostores"] == 2
    print("[ok] in-game: no de impostores grava sozinho")

    # o editor continua aberto depois de salvar (o redesenho nao pode fecha-lo)
    assert pg.locator(".duplas").count() == 1, "o editor fechou sozinho ao salvar"
    foto("08_ingame_editor.png")
    print("[ok] in-game: o editor segue aberto entre um cadastro e outro")

    # adivinha rank: acrescentar posicao abaixo do gabarito
    pg.locator("#gChips .chip").first.click()
    pg.wait_for_timeout(600)
    pg.click("button:has-text('Editar aqui')")
    pg.wait_for_selector(".aNome")
    pg.fill(".aPos", "7")
    pg.fill(".aNome", "Joao Felix")
    pg.fill(".aExtra", "126 mi")
    pg.click(".aAdd")
    pg.wait_for_timeout(900)
    assert pg.locator(".linha").count() == 7
    assert pg.locator(".linha.fechada").count() == 5      # entrou fechada
    jid_rank = disco["jogos"][0]["id"]
    lst = req("GET", f"/api/roteiros/{slug}/jogos/{jid_rank}")["attrs"]["lista"]
    assert lst[-1]["nome"] == "Joao Felix" and lst[-1]["extra"] == "126 mi"
    print("[ok] in-game: posicao acrescentada abaixo do gabarito, entra fechada")

    # --- a discussao no in-game: o tema aberto e o relogio nos 10 min
    pg.locator("#gChips .chip").nth(3).click()
    pg.wait_for_timeout(700)
    assert "IA vai roubar" in pg.inner_text(".holofote"), "o tema nao esta na tela"
    assert pg.inner_text(".cron") == "10:00", pg.inner_text(".cron")
    # sem gabarito e sem sorteio: nao ha nada tapado neste jogo
    assert pg.locator(".palco").count() == 0
    pg.click(".mais")
    pg.wait_for_timeout(700)
    assert pg.inner_text(".cron") == "10:30", pg.inner_text(".cron")
    foto("10_ingame_discussao.png")
    print("[ok] in-game: discussao com o tema aberto e o relogio em 10:00 (+30s)")

    # mudar os minutos ali mesmo volta o relogio junto
    pg.click("button:has-text('Editar aqui')")
    pg.wait_for_selector(".min")
    pg.locator(".min").fill("15")
    pg.locator(".min").dispatch_event("change")
    pg.wait_for_timeout(1000)
    assert pg.inner_text(".cron") == "15:00", pg.inner_text(".cron")
    jid_disc = req("GET", f"/api/partidas/{slug}")["jogos"][3]["id"]
    assert req("GET", f"/api/roteiros/{slug}/jogos/{jid_disc}")["attrs"]["tempo_min"] == 15
    print("[ok] in-game: mudar os minutos ali mesmo volta o relogio junto")

    # --- so resposta errada: as tres colunas, a bolinha e o embaralho
    pg.locator("#gChips .chip").nth(4).click()
    pg.wait_for_timeout(700)
    assert pg.locator(".pq").count() == 6
    # a resposta certa fica ABERTA: e a cola de quem apresenta, nao gabarito
    assert "Toquio" in pg.inner_text(".pq .certa"), pg.inner_text(".perguntas")
    antes = [x.strip() for x in pg.locator(".pq .pq-t").all_inner_texts()]

    pg.locator(".pq").nth(1).locator(".marca").click()
    pg.wait_for_timeout(800)
    marcada = antes[1]
    assert pg.locator(".pq.feita").count() == 1
    jid_err = req("GET", f"/api/partidas/{slug}")["jogos"][4]["id"]
    assert req("GET", f"/api/partidas/{slug}")["estado"][jid_err]["certas"]
    print("[ok] in-game: a bolinha marca a pergunta e grava no disco")

    # marcada = linha verde E bolinha com x: os dois sinais juntos, de proposito
    ln = pg.locator(".pq.feita").first
    verde = ln.locator(".pq-t").evaluate("e => getComputedStyle(e).color")
    normal = pg.locator(".pq:not(.feita) .pq-t").first.evaluate(
        "e => getComputedStyle(e).color")
    assert verde != normal, f"a linha marcada nao mudou de cor: {verde}"
    assert ln.locator(".marca").inner_text().strip() == "×", "a bolinha ficou sem o x"
    foto("12_ingame_errada.png")
    print(f"[ok] in-game: a marcada fica verde ({verde}) E ganha o x na bolinha")

    # clicar de novo desmarca, como o coracao
    pg.locator(".pq.feita .marca").first.click()
    pg.wait_for_timeout(800)
    assert pg.locator(".pq.feita").count() == 0
    print("[ok] in-game: clicar de novo na bolinha desmarca")

    # e o embaralho TIRA a marcada da tela, sem apagar do cadastro
    pg.locator(".pq").nth(1).locator(".marca").click()
    pg.wait_for_timeout(800)
    marcada = pg.locator(".pq.feita .pq-t").inner_text().strip()
    pg.click("button:has-text('Embaralhar')")
    pg.wait_for_timeout(900)
    depois = [x.strip() for x in pg.locator(".pq .pq-t").all_inner_texts()]
    assert len(depois) == 5, depois
    assert marcada not in depois, f"a marcada continua na tela: {depois}"
    assert sorted(depois + [marcada]) == sorted(antes), depois
    assert pg.locator(".pq.feita").count() == 0, "o embaralho manteve o verde"
    assert len(req("GET", f"/api/roteiros/{slug}/jogos/{jid_err}")
               ["attrs"]["perguntas"]) == 6, "o embaralho apagou do cadastro"
    print("[ok] in-game: embaralhar tira a marcada da tela e nao toca no cadastro")

    # e da pra trazer todas de volta
    pg.once("dialog", lambda d: d.accept())
    pg.click("button:has-text('Trazer todas de volta')")
    pg.wait_for_timeout(900)
    assert pg.locator(".pq").count() == 6
    print("[ok] in-game: 'Trazer todas de volta' devolve as que sairam")

    # --- o lixo: sai do jogo e vai pra lixeira com o .txt de onde veio
    alvo = pg.locator(".pq").first.locator(".pq-t").inner_text().strip()
    pg.once("dialog", lambda d: d.accept())
    pg.locator(".pq").first.locator(".lixo").click()
    pg.wait_for_timeout(1000)
    assert pg.locator(".pq").count() == 5
    restam = req("GET", f"/api/roteiros/{slug}/jogos/{jid_err}")["attrs"]["perguntas"]
    assert len(restam) == 5, "a pergunta nao saiu do cadastro"
    na_lixeira = [x for x in req("GET", "/api/lixeira")["itens"]
                  if x["pergunta"] == alvo]
    assert na_lixeira, f"{alvo!r} nao chegou na lixeira"
    # o arquivo de origem foi anotado no import, la na aba Jogos
    assert na_lixeira[0]["arquivo"] == "perguntas.txt", na_lixeira[0]
    assert na_lixeira[0]["roteiro"] == slug, na_lixeira[0]
    foto("13_ingame_lixo.png")
    devolver_lixeira()
    print(f"[ok] in-game: o lixo tirou {alvo!r} do jogo e anotou a origem "
          f"({na_lixeira[0]['arquivo']})")

    # F5 mantem o placar — que e do jogo aberto, entao volta no rank pra ver
    pg.reload()
    pg.wait_for_selector("#jogo:not(.hidden)", timeout=8000)
    pg.locator("#gChips .chip").first.click()
    pg.wait_for_timeout(800)
    assert pg.locator("#gMesa .vida.morta").count() >= 1
    print("[ok] F5 volta na mesma partida, no mesmo jogo, com o placar")

    # reinicio
    pg.on("dialog", lambda d: d.accept())
    pg.click("#gReiniciar")
    pg.wait_for_timeout(1000)
    assert pg.locator("#gMesa .vida.morta").count() == 0
    pg.locator("#gChips .chip").first.click()
    pg.wait_for_timeout(700)
    assert pg.locator(".linha.aberta").count() == 0
    # 7 e nao 6: o editor inline acrescentou o Joao Felix la em cima
    assert pg.locator(".linha.fechada").count() == 7
    foto("05_ingame_reiniciado.png")
    print("[ok] Reiniciar: vidas cheias e gabarito todo fechado de novo")

    br.close()

req("DELETE", f"/api/roteiros/{slug}")

if erros:
    print("\nERROS NO NAVEGADOR:")
    for e in erros:
        print("  ", e)
    sys.exit(1)
print("\nSEM ERRO DE JS. TUDO PASSOU.")
