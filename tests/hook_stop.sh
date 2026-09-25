#!/usr/bin/env bash
# Roda a suite rapida quando o Claude termina um turno.
#
# Ligado pelo hook Stop em ~/.claude/settings.json. Dois guardas, nessa ordem:
#
#   1. o arquivo `.testes-auto` na raiz do projeto            <- o liga/desliga
#   2. `git status` sujo                                       <- teve mudanca
#
# O segundo e' o que impede o hook de incomodar: numa sessao sobre macros do
# Resolve, ou logo depois de um commit, a arvore esta limpa e ele sai em
# milissegundos sem rodar nada.
#
# NAO bloqueia o turno. So' imprime o resultado como systemMessage -- quem
# decide o que fazer com uma falha e' voce, nao o hook.
#
# Ligar:    touch  /d/CanalYtbe/BatataQuente/pre_production/.testes-auto
# Desligar: rm     /d/CanalYtbe/BatataQuente/pre_production/.testes-auto

P="/d/CanalYtbe/BatataQuente/pre_production"

[ -f "$P/.testes-auto" ] || exit 0
[ -d "$P/.git" ] || exit 0
[ -n "$(git -C "$P" status --porcelain 2>/dev/null)" ] || exit 0
[ -x "$P/.venv/Scripts/python.exe" ] || exit 0

saida=$(cd "$P" && ./.venv/Scripts/python.exe tests/todos.py --rapido 2>&1)
rc=$?

# a ultima linha de resumo do runner ("[ok] 7 testes passaram (9s)")
resumo=$(printf '%s' "$saida" | grep -E '^\[(ok|X)\]' | tail -1)
[ -n "$resumo" ] || resumo="tests/todos.py --rapido terminou com codigo $rc"

if [ "$rc" -eq 0 ]; then
  msg="testes rapidos: $resumo"
else
  quebrou=$(printf '%s' "$saida" | grep -E '^ *\[ X\]' | sed 's/^ *//' | tr '\n' ' ')
  msg="TESTES FALHARAM -- $resumo${quebrou:+ | $quebrou}"
fi

# O JSON sai do Python. Escapar aspas e barras com sed e' o tipo de coisa que
# quebra calada -- e quebrou: a primeira versao deste arquivo imprimia
# systemMessage VAZIO toda vez que o sed reclamava.
MSG="$msg" "$P/.venv/Scripts/python.exe" -c 'import json,os; print(json.dumps({"systemMessage": os.environ["MSG"], "suppressOutput": True}))'
exit 0
