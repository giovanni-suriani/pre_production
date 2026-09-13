"""Os quadros do "Impostor no quadro": subir, servir, trocar e apagar.

Precisa do servidor de pe (video_script\\run.bat). Apaga o que criou no fim.

O que este teste guarda e o motivo de tudo isto existir: o cadastro por caminho
de disco NUNCA aparecia na tela (o navegador bloqueia file:// dentro de uma
pagina http). Agora o servico guarda uma copia e serve por /quadros/... — e e
isso que precisa continuar valendo.
"""
import base64
import json
import urllib.error as ue
import urllib.request as u
import zlib

B = "http://127.0.0.1:8741"


def req(m, p, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = u.Request(B + p, data=d, method=m,
                  headers={"Content-Type": "application/json"})
    with u.urlopen(r) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


def baixar(caminho):
    with u.urlopen(B + caminho) as f:
        return f.status, f.headers.get("content-type"), f.read()


def ok(t): print("[ok]", t)


def png(cor=(200, 30, 30)):
    """Um PNG 2x2 de verdade, montado na mao — sem Pillow no venv."""
    linha = b"\x00" + bytes(cor) * 2
    dados = zlib.compress(linha * 2)

    def bloco(tipo, corpo):
        return (len(corpo).to_bytes(4, "big") + tipo + corpo
                + zlib.crc32(tipo + corpo).to_bytes(4, "big"))

    cab = (2).to_bytes(4, "big") * 2 + bytes([8, 2, 0, 0, 0])
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cab)
            + bloco(b"IDAT", dados) + bloco(b"IEND", b""))


b64 = lambda raw: base64.b64encode(raw).decode()

# --- roteiro com um jogo de quadro
r = req("POST", "/api/roteiros", {"nome": "Quadros teste"})
slug = r["slug"]
r = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "impostor_quadro"})
jid = r["jogos"][0]["id"]
assert r["jogos"][0]["pendencia"] == "sem quadros"
ok("jogo de quadro criado, pendente")

# --- subir, e conferir que a imagem e SERVIDA (o ponto de tudo isto)
j = req("POST", f"/api/roteiros/{slug}/jogos/{jid}/quadros",
        {"nome": "Mona Lisa.png", "conteudo": b64(png())})
url = j["attrs"]["quadros"][0]
assert url.startswith(f"/quadros/{slug}/"), url
assert url.endswith(".png") and "mona_lisa" in url, url
status, tipo, corpo = baixar(url)
assert status == 200 and tipo == "image/png" and corpo == png()
ok(f"upload -> {url} servido como image/png, byte a byte igual")

# o data: URL que o FileReader produz tambem entra
j = req("POST", f"/api/roteiros/{slug}/jogos/{jid}/quadros",
        {"nome": "o grito.jpg", "conteudo": "data:image/png;base64," + b64(png((20, 60, 200)))})
assert len(j["attrs"]["quadros"]) == 2
u2 = j["attrs"]["quadros"][1]
# o nome mentia (.jpg num PNG): quem decide a extensao e o conteudo
assert u2.endswith(".png"), u2
assert baixar(u2)[0] == 200
ok("aceita o 'data:image/...;base64,' do FileReader e corrige a extensao pelo conteudo")

r = req("GET", f"/api/roteiros/{slug}")
assert r["jogos"][0]["pendencia"] == "", r["jogos"][0]
ok("com quadros, a pendencia some do roteiro")

# --- sortear no in-game devolve um dos quadros servidos
req("PUT", f"/api/roteiros/{slug}", {"participantes": [
    {"nome": "Gi", "vidas_total": 2}, {"nome": "He", "vidas_total": 2}]})
req("POST", f"/api/partidas/{slug}/abrir")
p = req("POST", f"/api/partidas/{slug}/sortear", {"jogo": jid})
so = p["estado"][jid]["sorteio"]
assert so["principal"].startswith("/quadros/"), so
assert so["impostor"] != so["principal"]
assert baixar(so["principal"])[0] == 200
ok("o sorteio do in-game devolve um quadro que a pagina consegue mostrar")

# --- tirar um quadro leva o arquivo junto
j = req("PUT", f"/api/roteiros/{slug}/jogos/{jid}",
        {"attrs": {"quadros": [url]}})
assert j["attrs"]["quadros"] == [url]
try:
    baixar(u2)
    print("  !! o arquivo do quadro removido continua servido")
    raise SystemExit(1)
except ue.HTTPError as e:
    assert e.code == 404
assert baixar(url)[0] == 200, "apagou o arquivo errado"
ok("tirar o quadro da lista apaga o arquivo — e so ele")

# --- o que nao pode entrar
for corpo, esperado, porque in [
    ({"nome": "x.png", "conteudo": b64(b"isto nao e uma imagem")}, 400, "nao e imagem"),
    ({"nome": "x.png", "conteudo": "%%% nao e base64 %%%"}, 400, "base64 quebrado"),
    ({"nome": "x.png", "conteudo": ""}, 400, "vazio"),
]:
    try:
        req("POST", f"/api/roteiros/{slug}/jogos/{jid}/quadros", corpo)
        print("  !! passou:", porque)
        raise SystemExit(1)
    except ue.HTTPError as e:
        assert e.code == esperado, (porque, e.code)
ok("recusa arquivo que nao e imagem, base64 quebrado e conteudo vazio")

# jogo que nao e de quadro nao aceita
r2 = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "rank_lista"})
jrank = r2["jogos"][-1]["id"]
try:
    req("POST", f"/api/roteiros/{slug}/jogos/{jrank}/quadros",
        {"nome": "x.png", "conteudo": b64(png())})
    print("  !! o adivinha-rank aceitou um quadro")
    raise SystemExit(1)
except ue.HTTPError as e:
    assert e.code == 400
ok("so o 'Impostor no quadro' aceita quadro")

# --- apagar o roteiro leva as imagens
req("DELETE", f"/api/roteiros/{slug}")
try:
    baixar(url)
    print("  !! as imagens sobreviveram ao roteiro")
    raise SystemExit(1)
except ue.HTTPError as e:
    assert e.code == 404
ok("apagar o roteiro apaga a pasta de quadros dele")

print("\nTUDO PASSOU")
