"""API, ponta a ponta: roteiro -> participantes + jogos -> partida.

Precisa do servidor de pe (video_script\\run.bat). Apaga o que criou no fim.

O roteiro e o dono de tudo aqui: os jogos moram dentro dele e a partida tem o
mesmo slug. Boa parte do que este teste cobre e exatamente isso — que nao
sobrou nenhum caminho por onde um jogo exista sem roteiro.
"""
import json
import urllib.error as ue
import urllib.request as u

B = "http://127.0.0.1:8741"


def req(m, p, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = u.Request(B + p, data=d, method=m,
                  headers={"Content-Type": "application/json"})
    with u.urlopen(r) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


def ok(t): print("[ok]", t)


# 1 --- roteiro com participantes
r = req("POST", "/api/roteiros", {"nome": "Ep teste"})
slug = r["slug"]
r = req("PUT", f"/api/roteiros/{slug}", {"participantes": [
    {"nome": "Gi", "vidas_total": 3}, {"nome": "He", "vidas_total": 2}]})
assert r["n_participantes"] == 2 and r["participantes"][0]["vidas_total"] == 3
gi = r["participantes"][0]["id"]
ok(f"roteiro {slug} com 2 participantes (as vidas moram no roteiro)")

# 2 --- os jogos moram dentro do roteiro
r = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "rank_lista"})
r = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "impostor_palavra"})
assert len(r["jogos"]) == 2, r["jogos"]
jr, ji = r["jogos"][0]["id"], r["jogos"][1]["id"]
assert r["jogos"][0]["pendencia"] == "sem lista importada", r["jogos"][0]
ok("2 jogos criados dentro do roteiro, marcados como pendentes")

txt = "1. Cristiano Ronaldo — 222 mi\n2) Lionel Messi | 180 mi\n3 - Neymar\nMbappe\n# comentario\n\n"
pr = req("POST", "/api/parse-lista-rank", {"texto": txt})
assert pr["n"] == 4 and pr["itens"][3]["pos"] == 4 and pr["itens"][0]["extra"] == "222 mi"
ok("parse do lista_do_rank.txt (4 formatos de linha na mesma lista)")

req("PUT", f"/api/roteiros/{slug}/jogos/{jr}",
    {"nome": "Rank das transferencias",
     "attrs": {"lista": pr["itens"], "tema": "mais caros", "aceita_parcial": True}})
req("PUT", f"/api/roteiros/{slug}/jogos/{ji}",
    {"attrs": {"palavras": ["pamonha", "quentao", "pipoca"], "n_impostores": 1,
               "palavra_impostor": "outra"}})
r = req("GET", f"/api/roteiros/{slug}")
assert r["pendencias"] == [], r["pendencias"]
ok("conteudo cadastrado -> as pendencias somem")

# os atributos removidos nao voltaram pelo catalogo
campos = {c["nome"] for t in req("GET", "/api/tipos")["tipos"] for c in t["campos"]}
for morto in ("regras", "dica_impostor", "tempo_discussao", "vidas_sugeridas"):
    assert morto not in campos, morto
ok("regras, dica do impostor, tempo de discussao e vidas sugeridas sairam da aba Jogos")

# salvar o roteiro NAO pode apagar os attrs (a aba Jogos e quem mexe neles)
r = req("PUT", f"/api/roteiros/{slug}", {"jogos": [
    {"id": jr, "nome": "Rank das transferencias", "duracao_min": 14},
    {"id": ji, "nome": "Quem e o impostor?", "duracao_min": 9}]})
assert len(r["jogos"][0]["attrs"]["lista"]) == 4, "salvar o roteiro comeu a lista"
assert r["duracao_prevista"] == 23
ok("salvar o roteiro preserva os attrs dos jogos (edicao em duas abas)")

# reordenar
r = req("PUT", f"/api/roteiros/{slug}", {"jogos": [
    {"id": ji, "nome": "Quem e o impostor?"}, {"id": jr, "nome": "Rank"}]})
assert [j["id"] for j in r["jogos"]] == [ji, jr]
req("PUT", f"/api/roteiros/{slug}", {"jogos": [{"id": jr}, {"id": ji}]})
ok("reordenar os jogos e mandar a lista na ordem nova")

# 3 --- a partida: uma por roteiro, mesmo slug
p = req("POST", f"/api/partidas/{slug}/abrir")
assert p["slug"] == slug, p["slug"]
assert p["participantes"][0]["vidas"] == [True] * 3
ok("'Jogar roteiro' cria a partida com os jogadores do roteiro")

p2 = req("POST", f"/api/partidas/{slug}/abrir")
assert p2["criado"] == p["criado"], "abrir de novo recriou a partida"
ok("abrir de novo CONTINUA a mesma partida (nao recomeca)")

p = req("POST", f"/api/partidas/{slug}/vida", {"participante": gi, "indice": 0})
assert p["participantes"][0]["vidas"] == [False, True, True]
p = req("POST", f"/api/partidas/{slug}/vida", {"participante": gi, "indice": 0})
assert p["participantes"][0]["vidas"] == [True, True, True]
ok("clique no coracao alterna cheio<->cinza e volta (desfazer)")

# 4 --- buscas do rank
b = req("POST", f"/api/partidas/{slug}/buscar",
        {"jogo": jr, "por": "nome", "termo": "ronaldo", "quem": "Gi"})
assert [x["pos"] for x in b["achados"]] == [1]
assert "1" in b["partida"]["estado"][jr]["revelados"]
ok("busca por nome parcial ('ronaldo' -> #1) e revelou")
b = req("POST", f"/api/partidas/{slug}/buscar", {"jogo": jr, "por": "rank", "termo": "3"})
assert b["achados"][0]["nome"] == "Neymar"
ok("busca por rank ('3' -> Neymar)")
b = req("POST", f"/api/partidas/{slug}/buscar",
        {"jogo": jr, "por": "nome", "termo": "Pele", "quem": "He"})
assert b["achados"] == [] and b["partida"]["estado"][jr]["erros"][0]["termo"] == "Pele"
ok("chute que nao esta na lista entra no log de erros")
p = req("POST", f"/api/partidas/{slug}/esconder", {"jogo": jr, "pos": 1})
assert "1" not in p["estado"][jr]["revelados"]
ok("esconder desfaz a revelacao")

# 5 --- impostor + o cronometro que fica gravado
p = req("POST", f"/api/partidas/{slug}/sortear", {"jogo": ji})
so = p["estado"][ji]["sorteio"]
assert so["principal"] in ("pamonha", "quentao", "pipoca")
assert so["impostor"] != so["principal"] and len(so["impostores"]) == 1
assert so["revelado"] is False
ok(f"sorteio: todos='{so['principal']}' impostor='{so['impostor']}', escondido")
p = req("POST", f"/api/partidas/{slug}/revelar-impostor", {"jogo": ji, "revelado": True})
assert p["estado"][ji]["sorteio"]["revelado"] is True
ok("revelar impostor")

cfg = req("GET", "/api/tipos")
assert cfg["tempo_padrao"] == 120 and cfg["tempo_passo"] == 30
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": ji, "segundos": 150})
assert p["estado"][ji]["tempo"] == 150
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": ji, "segundos": 0})
assert p["estado"][ji]["tempo"] == 30, "o tempo desceu abaixo de um passo"
ok("discussao comeca em 2min, anda de 30 em 30 e nao desce de 30s")

# 6 --- trocar a mesa no meio NAO zera o placar; Reiniciar zera
p = req("POST", f"/api/partidas/{slug}/vida", {"participante": gi, "indice": 2})
r = req("GET", f"/api/roteiros/{slug}")
novos = r["participantes"] + [{"nome": "Enzo", "vidas_total": 2}]
req("PUT", f"/api/roteiros/{slug}", {"participantes": novos})
p = req("POST", f"/api/partidas/{slug}/abrir")
assert len(p["participantes"]) == 3, p["participantes"]
assert p["participantes"][0]["vidas"] == [True, True, False], "perdeu a vida gasta"
assert p["participantes"][2]["vidas"] == [True, True]
ok("entrar alguem na mesa no meio nao devolve as vidas ja gastas")

p = req("POST", f"/api/partidas/{slug}/reiniciar")
assert all(all(x["vidas"]) for x in p["participantes"])
assert p["estado"] == {}, p["estado"]
ok("Reiniciar: vidas cheias, gabarito fechado, sorteios apagados")

# 7 --- erros esperados
vazio = req("POST", "/api/roteiros", {"nome": "Sem gente"})
for m, path, body, esperado in [
    ("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "nao_existe"}, 400),
    ("GET", "/api/roteiros/fantasma", None, 404),
    ("GET", f"/api/roteiros/{slug}/jogos/fantasma", None, 404),
    ("POST", f"/api/partidas/{vazio['slug']}/abrir", None, 400),
    ("POST", f"/api/partidas/{slug}/buscar", {"jogo": ji, "por": "nome", "termo": "x"}, 400),
    ("POST", f"/api/partidas/{slug}/buscar", {"jogo": jr, "por": "rank", "termo": "abc"}, 400),
]:
    try:
        req(m, path, body)
        print("  !! era esperado", esperado, "em", path)
        raise SystemExit(1)
    except ue.HTTPError as e:
        assert e.code == esperado, (path, e.code)
ok("erros: tipo invalido 400, roteiro/jogo inexistente 404, jogar sem gente 400,"
   " busca no jogo errado 400, rank nao-numerico 400")

# 8 --- apagar o roteiro leva jogos e partida junto
req("DELETE", f"/api/roteiros/{slug}")
for path in (f"/api/roteiros/{slug}", f"/api/partidas/{slug}"):
    try:
        req("GET", path)
        print("  !! sobrou", path)
        raise SystemExit(1)
    except ue.HTTPError as e:
        assert e.code == 404
ok("apagar o roteiro leva os jogos e a partida junto")

req("DELETE", f"/api/roteiros/{vazio['slug']}")
print("\nTUDO PASSOU")
