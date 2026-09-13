"""API, ponta a ponta: roteiro -> participantes + jogos -> partida.

Precisa do servidor de pe (video_script\\run.bat). Apaga o que criou no fim.

O roteiro e o dono de tudo aqui: os jogos moram dentro dele e a partida tem o
mesmo slug. Boa parte do que este teste cobre e exatamente isso — que nao
sobrou nenhum caminho por onde um jogo exista sem roteiro.
"""
import json
import urllib.error as ue
import urllib.request as u
from pathlib import Path

B = "http://127.0.0.1:8741"


def req(m, p, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = u.Request(B + p, data=d, method=m,
                  headers={"Content-Type": "application/json"})
    with u.urlopen(r) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


def ok(t): print("[ok]", t)

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



# 1 --- roteiro com participantes
r = req("POST", "/api/roteiros", {"nome": "Ep teste"})
slug = r["slug"]
r = req("PUT", f"/api/roteiros/{slug}", {"participantes": [
    {"nome": "Gi"}, {"nome": "He"}]})
assert r["n_participantes"] == 2 and r["participantes"][0]["nome"] == "Gi"
# as vidas nao sao da pessoa: nao ha mais campo de vida no participante
assert "vidas_total" not in r["participantes"][0], r["participantes"][0]
gi = r["participantes"][0]["id"]
ok(f"roteiro {slug} com 2 participantes (sem vida na pessoa)")

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

# titulo e rodape nao podem virar posicao: e o formato dos top100 de verdade
com_capa = ("TOP 100 GOLEIROS\nFonte: Iconic Football\n\n"
            "  1. Lev Yashin — Russia\n  2. Gordon Banks — Inglaterra\n\n"
            "Nota: ranking subjetivo\n")
pc = req("POST", "/api/parse-lista-rank", {"texto": com_capa})
assert pc["n"] == 2, pc["itens"]
assert pc["itens"][0]["nome"] == "Lev Yashin", pc["itens"][0]
assert pc["itens"][0]["extra"] == "Russia", pc["itens"][0]
# mas num arquivo sem numero nenhum, a primeira linha E o primeiro item
sem_num = req("POST", "/api/parse-lista-rank", {"texto": "Neymar\nMbappe"})
assert [i["nome"] for i in sem_num["itens"]] == ["Neymar", "Mbappe"]
ok("titulo e rodape ficam fora do rank; lista sem numero continua inteira")

# ...mas a linha sem numero COLADA no fim da lista continua valendo (o Mbappe
# do caso acima): o que separa o rodape e a linha em branco, nao o numero
colado = req("POST", "/api/parse-lista-rank",
             {"texto": "1. Neymar\n2. Mbappe\nVini Jr"})
assert [i["pos"] for i in colado["itens"]] == [1, 2, 3], colado["itens"]
ok("linha sem numero colada no fim da lista ainda entra")

req("PUT", f"/api/roteiros/{slug}/jogos/{jr}",
    {"nome": "Rank das transferencias",
     "attrs": {"lista": pr["itens"], "tema": "mais caros",
               "aceita_parcial": True, "vidas": 3}})
req("PUT", f"/api/roteiros/{slug}/jogos/{ji}",
    {"attrs": {"duplas": [{"jogador": "pamonha", "impostor": "quentao"},
                          {"jogador": "pipoca", "impostor": ""}],
               "n_impostores": 1, "vidas": 2}})
r = req("GET", f"/api/roteiros/{slug}")
assert r["pendencias"] == [], r["pendencias"]
ok("conteudo cadastrado -> as pendencias somem")

# os atributos removidos nao voltaram pelo catalogo
campos = {c["nome"] for t in req("GET", "/api/tipos")["tipos"] for c in t["campos"]}
for morto in ("regras", "dica_impostor", "tempo_discussao", "vidas_sugeridas",
              "quadros", "palavras", "quadro_impostor", "palavra_impostor"):
    assert morto not in campos, morto
ok("regras, dica, tempo, vidas sugeridas e as imagens/listas soltas do "
   "impostor sairam da aba Jogos")

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
# o placar e por JOGO: 3 vidas no rank, 2 no impostor, no mesmo episodio
assert p["estado"][jr]["vidas"][gi] == [True] * 3, p["estado"][jr]
assert p["estado"][ji]["vidas"][gi] == [True] * 2, p["estado"][ji]
ok("'Jogar roteiro' cria a partida com um placar por jogo (3 no rank, 2 no impostor)")

p2 = req("POST", f"/api/partidas/{slug}/abrir")
assert p2["criado"] == p["criado"], "abrir de novo recriou a partida"
ok("abrir de novo CONTINUA a mesma partida (nao recomeca)")

p = req("POST", f"/api/partidas/{slug}/vida",
        {"jogo": jr, "participante": gi, "indice": 0})
assert p["estado"][jr]["vidas"][gi] == [False, True, True]
# e o coracao gasto num jogo nao encosta no outro
assert p["estado"][ji]["vidas"][gi] == [True, True], p["estado"][ji]
p = req("POST", f"/api/partidas/{slug}/vida",
        {"jogo": jr, "participante": gi, "indice": 0})
assert p["estado"][jr]["vidas"][gi] == [True, True, True]
ok("clique no coracao alterna cheio<->cinza, so naquele jogo, e desfaz")

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
# a dupla vem pronta do cadastro: o sorteio escolhe a linha, nao o par
assert (so["principal"], so["impostor"]) in (("pamonha", "quentao"),
                                             ("pipoca", "")), so
assert len(so["impostores"]) == 1
# nao ha mais etapa de revelar: sortear ja e a revelacao
assert "revelado" not in so, so
ok(f"sorteio: todos='{so['principal']}' impostor='{so['impostor']}'")

cfg = req("GET", "/api/tipos")
assert cfg["tempo_padrao"] == 120 and cfg["tempo_passo"] == 30
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": ji, "segundos": 150})
assert p["estado"][ji]["tempo"] == 150
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": ji, "segundos": 0})
assert p["estado"][ji]["tempo"] == 30, "o tempo desceu abaixo de um passo"
ok("discussao comeca em 2min, anda de 30 em 30 e nao desce de 30s")

# 5b --- discussao: so o tema e o relogio, que comeca nos 10 min do cadastro
r = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "discussao"})
jd = r["jogos"][-1]["id"]
assert r["jogos"][-1]["pendencia"] == "sem tema", r["jogos"][-1]
assert r["jogos"][-1]["attrs"]["tempo_min"] == 10, r["jogos"][-1]["attrs"]
req("PUT", f"/api/roteiros/{slug}/jogos/{jd}",
    {"attrs": {"tema": "IA vai roubar o emprego de todo mundo?"}})
r = req("GET", f"/api/roteiros/{slug}")
assert r["pendencias"] == [], r["pendencias"]
assert "10 min de relogio" in r["jogos"][-1]["resumo"], r["jogos"][-1]["resumo"]
# o ajuste na hora continua valendo, e nao desce de um passo
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": jd, "segundos": 630})
assert p["estado"][jd]["tempo"] == 630
p = req("POST", f"/api/partidas/{slug}/tempo", {"jogo": jd, "segundos": 10})
assert p["estado"][jd]["tempo"] == 30
req("DELETE", f"/api/roteiros/{slug}/jogos/{jd}")
ok("discussao: 10 min de padrao, 'sem tema' ate cadastrar, relogio ajustavel")

# 5c --- so resposta errada: marcar, desmarcar e o embaralho jogando pro fim
r = req("POST", f"/api/roteiros/{slug}/jogos", {"tipo": "resposta_errada"})
je = r["jogos"][-1]["id"]
assert r["jogos"][-1]["pendencia"] == "sem perguntas"
req("PUT", f"/api/roteiros/{slug}/jogos/{je}", {"attrs": {"perguntas": [
    {"pergunta": f"pergunta {k}", "resposta": f"certa {k}"} for k in range(8)]}})
r = req("GET", f"/api/roteiros/{slug}")
assert "8 perguntas" in r["jogos"][-1]["resumo"], r["jogos"][-1]["resumo"]

p = req("POST", f"/api/partidas/{slug}/errada-marcar", {"jogo": je, "i": 2})
p = req("POST", f"/api/partidas/{slug}/errada-marcar", {"jogo": je, "i": 5})
assert p["estado"][je]["certas"] == [2, 5], p["estado"][je]
p = req("POST", f"/api/partidas/{slug}/errada-marcar", {"jogo": je, "i": 5})
assert p["estado"][je]["certas"] == [2], "clicar de novo nao desmarcou"

p = req("POST", f"/api/partidas/{slug}/errada-embaralhar", {"jogo": je})
est = p["estado"][je]
# a marcada sai da tela e a marcacao e limpa; as outras 7 voltam embaralhadas
assert est["escondidas"] == [2], est
assert sorted(est["ordem"]) == [0, 1, 3, 4, 5, 6, 7], est["ordem"]
assert est["certas"] == [], est
ok("so resposta errada: marcar alterna, e o embaralho tira as marcadas da tela")

# um segundo embaralho acumula, sem devolver a primeira
p = req("POST", f"/api/partidas/{slug}/errada-marcar", {"jogo": je, "i": 0})
p = req("POST", f"/api/partidas/{slug}/errada-embaralhar", {"jogo": je})
assert p["estado"][je]["escondidas"] == [0, 2], p["estado"][je]
assert 2 not in p["estado"][je]["ordem"] and 0 not in p["estado"][je]["ordem"]

# nada foi apagado do cadastro, e "trazer de volta" devolve o jogo inteiro
assert len(req("GET", f"/api/roteiros/{slug}/jogos/{je}")["attrs"]["perguntas"]) == 8
p = req("POST", f"/api/partidas/{slug}/zerar-jogo", {"jogo": je})
assert not p["estado"][je].get("escondidas"), p["estado"][je]
ok("as escondidas nao saem do cadastro, e 'trazer de volta' devolve todas")

# --- a lixeira: sai do jogo, fica anotada com o arquivo de origem
req("PUT", f"/api/roteiros/{slug}/jogos/{je}", {"attrs": {"perguntas": [
    {"pergunta": f"pergunta {k}", "resposta": f"certa {k}",
     "origem": "perguntas_exemplo.txt"} for k in range(8)]}})
req("POST", f"/api/partidas/{slug}/errada-marcar", {"jogo": je, "i": 7})
p = req("POST", f"/api/partidas/{slug}/errada-lixo", {"jogo": je, "i": 3})
restam = req("GET", f"/api/roteiros/{slug}/jogos/{je}")["attrs"]["perguntas"]
assert len(restam) == 7 and all(x["pergunta"] != "pergunta 3" for x in restam)
# a marcacao das de baixo acompanha: a 7 virou a 6, e nao a marcacao da 7
assert p["estado"][je]["certas"] == [6], p["estado"][je]
lx = req("GET", "/api/lixeira")["itens"]
achou = [x for x in lx if x["pergunta"] == "pergunta 3"]
assert achou and achou[0]["arquivo"] == "perguntas_exemplo.txt", lx[-3:]
assert achou[0]["roteiro"] == slug, achou[0]
# jogar a mesma pergunta fora de novo nao duplica a linha na lixeira
antes = len(lx)
req("PUT", f"/api/roteiros/{slug}/jogos/{je}", {"attrs": {"perguntas": [
    {"pergunta": "pergunta 3", "resposta": "certa 3", "origem": "outro.txt"}]}})
req("POST", f"/api/partidas/{slug}/errada-lixo", {"jogo": je, "i": 0})
assert len(req("GET", "/api/lixeira")["itens"]) == antes
devolver_lixeira()
ok("lixeira: sai do jogo com pergunta/resposta/arquivo, e nao duplica")
req("DELETE", f"/api/roteiros/{slug}/jogos/{je}")

# 6 --- trocar a mesa no meio NAO zera o placar; Reiniciar zera
p = req("POST", f"/api/partidas/{slug}/vida",
        {"jogo": jr, "participante": gi, "indice": 2})
r = req("GET", f"/api/roteiros/{slug}")
novos = r["participantes"] + [{"nome": "Enzo"}]
req("PUT", f"/api/roteiros/{slug}", {"participantes": novos})
p = req("POST", f"/api/partidas/{slug}/abrir")
assert len(p["participantes"]) == 3, p["participantes"]
enzo = p["participantes"][2]["id"]
assert p["estado"][jr]["vidas"][gi] == [True, True, False], "perdeu a vida gasta"
assert p["estado"][jr]["vidas"][enzo] == [True] * 3, "quem chega entra cheio"
ok("entrar alguem na mesa no meio nao devolve as vidas ja gastas")

# mudar quantas vidas o jogo tem, no meio do episodio, tambem nao zera o placar
req("PUT", f"/api/roteiros/{slug}/jogos/{jr}", {"attrs": {"vidas": 4}})
p = req("POST", f"/api/partidas/{slug}/abrir")
assert p["estado"][jr]["vidas"][gi] == [True, True, False, True], p["estado"][jr]
req("PUT", f"/api/roteiros/{slug}/jogos/{jr}", {"attrs": {"vidas": 3}})
ok("subir as vidas do jogo no meio da partida acrescenta coracao cheio no fim")

p = req("POST", f"/api/partidas/{slug}/reiniciar")
assert all(all(v) for v in p["estado"][jr]["vidas"].values())
# so as vidas sobram no estado: gabarito e sorteio foram zerados
assert set(p["estado"][jr]) == {"vidas"}, p["estado"][jr]
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
