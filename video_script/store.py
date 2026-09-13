"""video_script — leitura e escrita dos arquivos em dados/.

Um arquivo JSON por coisa (jogo, roteiro, partida), como o pre_production faz
com projects/. Sem banco: isto roda em 127.0.0.1 numa maquina so, e um banco
seria uma peca a mais entre voce e o arquivo que voce quer abrir no editor.

Toda escrita passa por gravar(): escreve num .tmp e renomeia. A partida e
salva a cada clique num coracao durante a gravacao do episodio — se o disco
engasgar no meio, o que estava la antes continua inteiro em vez de virar meio
JSON.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
ROTEIROS = DADOS / "roteiros"
PARTIDAS = DADOS / "partidas"
# Nao ha pasta de jogos: os jogos moram dentro do roteiro que os usa
# (ver roteiros.py). A partida tem o mesmo slug do roteiro — uma por roteiro.


def preparar() -> None:
    for d in (ROTEIROS, PARTIDAS):
        d.mkdir(parents=True, exist_ok=True)


def agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def slugify(texto: str) -> str:
    """Nome digitado -> nome de arquivo. Sem acento, sem espaco, minusculo."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "sem_nome"


def slug_livre(pasta: Path, base: str) -> str:
    """slug que ainda nao existe em pasta — acrescenta _2, _3... se precisar."""
    s = slugify(base)
    if not (pasta / f"{s}.json").exists():
        return s
    n = 2
    while (pasta / f"{s}_{n}.json").exists():
        n += 1
    return f"{s}_{n}"


def ler(pasta: Path, slug: str) -> dict | None:
    f = pasta / f"{slug}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def gravar(pasta: Path, slug: str, dados: dict) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    dados = dict(dados)
    dados["slug"] = slug
    dados["alterado"] = agora()
    f = pasta / f"{slug}.json"
    tmp = pasta / f"{slug}.json.tmp"
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, f)
    return dados


def apagar(pasta: Path, slug: str) -> bool:
    f = pasta / f"{slug}.json"
    if not f.exists():
        return False
    f.unlink()
    return True


def listar(pasta: Path) -> list[dict]:
    """Todos os JSON da pasta, mais recente primeiro. Ignora o que nao parseia
    em vez de derrubar a tela inteira por causa de um arquivo editado a mao."""
    pasta.mkdir(parents=True, exist_ok=True)
    out = []
    for f in pasta.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        d["slug"] = f.stem
        out.append(d)
    out.sort(key=lambda d: d.get("alterado") or d.get("criado") or "",
             reverse=True)
    return out
