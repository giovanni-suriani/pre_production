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
import zlib
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


def png(cor):
    """Um PNG 2x2 de verdade, montado na mao — sem Pillow no venv."""
    linha = b"\x00" + bytes(cor) * 2
    dados = zlib.compress(linha * 2)

    def bloco(tipo, corpo):
        return (len(corpo).to_bytes(4, "big") + tipo + corpo
                + zlib.crc32(tipo + corpo).to_bytes(4, "big"))

    cab = (2).to_bytes(4, "big") * 2 + bytes([8, 2, 0, 0, 0])
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cab)
            + bloco(b"IDAT", dados) + bloco(b"IEND", b""))


LISTA = "\n".join([
    "1. Neymar — 222 mi", "2. Mbappe — 180 mi", "3. Coutinho — 145 mi",
    "4. Dembele — 140 mi", "5. Cristiano Ronaldo — 117 mi", "6. Griezmann — 120 mi",
])

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
    for nome, vidas in (("Gi", 3), ("He", 3), ("Enzo", 2)):
        pg.click("#dAddPart")
        linha = pg.locator("#dParts .part").last
        linha.locator(".nm").fill(nome)
        linha.locator(".vd").fill(str(vidas))
        linha.locator(".vd").dispatch_event("change")
    assert pg.locator("#dParts .part").count() == 3
    assert pg.locator("#dParts .vida").count() == 8      # 3+3+2 coracoes de previa
    print("[ok] aba Roteiro: 3 participantes com as vidas, previa dos coracoes")

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
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    foto("02_jogo_rank.png")
    print("[ok] aba Jogos: lista importada, sem regras/dica/discussao/vidas")

    # o outro jogo, pela volta ao roteiro
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.locator("#dJogos .jogo").nth(1).locator(".abrir").click()
    pg.wait_for_selector("#dCampos textarea")
    pg.locator("#dCampos textarea").first.fill("pamonha\nquentao\npe de moleque\ncanjica")
    pg.locator("#dCampos textarea").first.dispatch_event("change")
    pg.click("#dSalvar")
    pg.wait_for_timeout(700)
    print("[ok] aba Jogos: palavras do impostor cadastradas")

    # --- terceiro jogo: impostor no quadro, com imagem subida pela tela
    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    pg.click("#dTipos .chip:has-text('Impostor no quadro')")
    pg.wait_for_timeout(500)
    pg.locator("#dJogos .jogo").nth(2).locator(".abrir").click()
    pg.wait_for_selector("#dQuadros:not(.hidden)")
    pg.set_input_files("#qFile", [
        {"name": "Mona Lisa.png", "mimeType": "image/png", "buffer": png((200, 30, 30))},
        {"name": "O Grito.png", "mimeType": "image/png", "buffer": png((20, 60, 200))},
    ])
    pg.wait_for_selector("#qLista .thumb")
    pg.wait_for_timeout(900)
    assert pg.locator("#qLista .thumb").count() == 2, pg.locator("#qLista .thumb").count()
    assert pg.locator("#qLista .thumb.quebrado").count() == 0, "a miniatura nao carregou"
    # a miniatura tem que estar realmente desenhada, nao so no HTML
    assert pg.locator("#qLista .thumb img").first.evaluate("i => i.naturalWidth") == 2
    foto("06_jogo_quadros.png")
    print("[ok] aba Jogos: 2 quadros subiram e as miniaturas carregam de verdade")

    pg.locator("#qLista .thumb .x").first.click()
    pg.wait_for_timeout(800)
    assert pg.locator("#qLista .thumb").count() == 1
    pg.set_input_files("#qFile", [
        {"name": "girassois.png", "mimeType": "image/png", "buffer": png((230, 180, 20))},
    ])
    pg.wait_for_timeout(900)
    assert pg.locator("#qLista .thumb").count() == 2
    print("[ok] aba Jogos: tirar e por quadro de volta")

    pg.click("#dVoltar")
    pg.wait_for_selector("#dJogos .jogo")
    assert pg.locator("#dJogos .badge.warn").count() == 0
    print("[ok] com conteudo cadastrado, as pendencias somem do roteiro")

    # -------------------------------------------------------- aba 3: in-game
    pg.click("#dJogar")
    pg.wait_for_selector("#jogo:not(.hidden)", timeout=8000)
    assert "/in-game?roteiro=" in pg.url, pg.url
    assert pg.locator(".jogador").count() == 3
    assert pg.locator("#gMesa .vida").count() == 8
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
    assert disco["participantes"][0]["vidas"] == [True, True, False]
    print("[ok] clique no coracao virou cinza E gravou no disco")

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
    pg.wait_for_selector(".segredo")
    assert "clique para ver" in pg.inner_text(".segredo")
    pg.locator(".segredo").first.click()
    aberto = pg.locator(".segredo").first.inner_text()
    assert any(w in aberto for w in ("pamonha", "quentao", "pe de moleque", "canjica")), aberto
    pg.click(".revelar")
    pg.wait_for_timeout(600)
    assert pg.locator(".jogador.impostor").count() == 1
    foto("04_ingame_impostor.png")
    print(f"[ok] sorteio tapado, abre no clique ({aberto}); revelar marca a mesa")

    # --- o quadro no in-game: tapado, e aparece de verdade no clique
    pg.locator("#gChips .chip").nth(2).click()
    pg.wait_for_timeout(600)
    pg.click(".sortear")
    pg.wait_for_selector(".palco")
    assert pg.locator(".palco.fechado").count() == 1, "o quadro nasceu aberto"
    assert not pg.locator(".palco .quadro").is_visible()
    pg.click(".palco .tampa")
    pg.wait_for_timeout(400)
    assert pg.locator(".palco .quadro").is_visible()
    assert pg.locator(".palco .quadro").evaluate("i => i.naturalWidth") == 2, \
        "a imagem esta no HTML mas nao carregou"
    src = pg.locator(".palco .quadro").get_attribute("src")
    assert src.startswith("/quadros/"), src
    foto("07_ingame_quadro.png")
    print(f"[ok] in-game: quadro tapado, abre no clique e RENDERIZA ({src})")

    # --- editar o conteudo DENTRO do in-game, sem sair da tela
    # impostor na palavra
    pg.locator("#gChips .chip").nth(1).click()
    pg.wait_for_timeout(600)
    pg.click("button:has-text('Editar aqui')")
    pg.wait_for_selector(".nova")
    pg.fill(".nova", "bolo de fuba")
    pg.press(".nova", "Enter")
    pg.wait_for_timeout(900)
    assert "bolo de fuba" in pg.inner_text(".lista"), pg.inner_text(".lista")
    assert "/jogo?" not in pg.url, "saiu da tela do in-game"
    jid_pal = disco["jogos"][1]["id"]
    attrs = req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]
    assert "bolo de fuba" in attrs["palavras"], attrs["palavras"]
    print("[ok] in-game: palavra acrescentada ali mesmo, gravada no roteiro")

    pg.locator(".lista .chip .x").first.click()
    pg.wait_for_timeout(900)
    assert len(req("GET", f"/api/roteiros/{slug}/jogos/{jid_pal}")["attrs"]["palavras"]) == 4
    print("[ok] in-game: tirar palavra ali mesmo")

    # o editor continua aberto depois de salvar (o redesenho nao pode fecha-lo)
    assert pg.locator(".nova").count() == 1, "o editor fechou sozinho ao salvar"
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

    # impostor no quadro: subir imagem ali mesmo
    pg.locator("#gChips .chip").nth(2).click()
    pg.wait_for_timeout(600)
    pg.click("button:has-text('Editar aqui')")
    pg.wait_for_selector(".galeria")
    pg.set_input_files(".arq", [
        {"name": "noite estrelada.png", "mimeType": "image/png",
         "buffer": png((40, 40, 120))},
    ])
    pg.wait_for_timeout(1200)
    jid_q = disco["jogos"][2]["id"]
    assert len(req("GET", f"/api/roteiros/{slug}/jogos/{jid_q}")["attrs"]["quadros"]) == 3
    assert pg.locator(".galeria .thumb").count() == 3
    assert pg.locator(".galeria .thumb.quebrado").count() == 0
    foto("08_ingame_editor.png")
    print("[ok] in-game: quadro subido ali mesmo, miniatura carrega")

    # F5 mantem o placar
    pg.reload()
    pg.wait_for_selector("#jogo:not(.hidden)", timeout=8000)
    assert pg.locator("#gMesa .vida.morta").count() >= 1
    print("[ok] F5 volta na mesma partida, com o placar")

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
