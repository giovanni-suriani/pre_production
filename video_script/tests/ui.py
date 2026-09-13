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
    assert pg.locator(".linha.fechada").count() == 6
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
