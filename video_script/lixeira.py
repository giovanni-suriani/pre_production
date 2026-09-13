r"""video_script — a lixeira das perguntas descartadas.

Um arquivo so, do servico inteiro: `dados\lixeira_perguntas.json`. Nao e por
roteiro de proposito — as perguntas vem dos mesmos .txt em `listas\`, e uma
pergunta que nao funcionou num episodio nao funciona no proximo. A lixeira e a
memoria disso entre gravacoes, e por isso guarda **de qual arquivo veio**: e
por ali que se acha a linha pra tirar do .txt de origem.

Isto nao apaga nada de ninguem: quem tira a pergunta do jogo e o roteiro (ver
roteiros.salvar_jogo). Aqui so se anota o que foi descartado, e quando.
"""

from __future__ import annotations

import json
import os

import store

ARQUIVO = store.DADOS / "lixeira_perguntas.json"


def _chave(pergunta: str, resposta: str) -> str:
    """Duas perguntas iguais vindas de roteiros diferentes sao a mesma coisa.

    Sem isto a lixeira viraria um log de cliques, e o que interessa e a lista
    do que nao presta — que nao pode ter a mesma linha tres vezes.
    """
    return f"{store.slugify(pergunta)}|{store.slugify(resposta)}"


def listar() -> list[dict]:
    if not ARQUIVO.exists():
        return []
    try:
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []                       # arquivo editado a mao e quebrado
    return dados if isinstance(dados, list) else []


def jogar(pergunta: str, resposta: str = "", arquivo: str = "",
          roteiro: str = "", jogo: str = "") -> dict:
    """Anota uma pergunta descartada. Devolve o item gravado."""
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise ValueError("pergunta vazia")

    itens = listar()
    chave = _chave(pergunta, resposta)
    for x in itens:
        if _chave(x.get("pergunta", ""), x.get("resposta", "")) == chave:
            return x                    # ja estava na lixeira

    item = {
        "pergunta": pergunta,
        "resposta": (resposta or "").strip(),
        "arquivo": (arquivo or "").strip(),   # de qual .txt a linha veio
        "roteiro": roteiro,
        "jogo": jogo,
        "em": store.agora(),
    }
    itens.append(item)

    # mesma escrita atomica do store: a lixeira nao pode virar meio JSON se o
    # disco engasgar no meio de uma gravacao
    store.DADOS.mkdir(parents=True, exist_ok=True)
    tmp = ARQUIVO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, ARQUIVO)
    return item
