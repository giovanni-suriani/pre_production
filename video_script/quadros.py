"""video_script — as imagens do "Impostor no quadro".

O servico guarda uma copia de cada quadro em `dados\\quadros\\<roteiro>\\` e
serve por `/quadros/...`. Antes o jogo guardava o caminho do arquivo no disco,
e a pagina nunca conseguia mostrar: o navegador bloqueia `file://` dentro de
uma pagina `http://`. Guardar a copia resolve isso de vez e, de quebra, deixa o
roteiro autossuficiente — mover ou renomear a pasta de origem depois nao quebra
a gravacao.

O arquivo sobe em **base64 dentro do JSON**, e nao como multipart. E o mesmo
caminho do `lista_do_rank.txt` (o navegador le, manda o conteudo) e evita uma
dependencia a mais (`python-multipart`) num venv que hoje so tem
fastapi/uvicorn/numpy. Custa 33% de tamanho no envio, o que em 127.0.0.1 nao
significa nada.
"""

from __future__ import annotations

import base64
import binascii
import re
import shutil
import time
from pathlib import Path

import store

# So o que o navegador desenha sozinho. SVG fica de fora de proposito: e um
# documento que pode carregar script, e nao ha por que abrir essa porta aqui.
EXTENSOES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
}
LIMITE_BYTES = 16 * 1024 * 1024        # 16 MB por imagem

# assinatura do arquivo -> extensao. O nome mente com frequencia (o ".png" que
# na verdade e um JPEG salvo pelo navegador), e quem decide como a imagem e
# servida e o conteudo.
_MAGICOS = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
]


def _pasta(roteiro: str) -> Path:
    p = store.QUADROS / store.slugify(roteiro)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _tipo_real(dados: bytes) -> str | None:
    for assinatura, ext in _MAGICOS:
        if dados.startswith(assinatura):
            return ext
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


def guardar(roteiro: str, nome_original: str, conteudo_b64: str) -> str:
    """Grava a imagem e devolve a URL por onde ela passa a ser servida.

    Devolve uma URL (`/quadros/<roteiro>/<arquivo>`) e nao um caminho de disco:
    e isso que vai para `attrs.quadros`, e e o que a pagina consegue mostrar.
    """
    # o navegador manda "data:image/png;base64,AAAA..." — o prefixo sai aqui
    if "," in conteudo_b64[:120] and conteudo_b64.lstrip().startswith("data:"):
        conteudo_b64 = conteudo_b64.split(",", 1)[1]
    try:
        dados = base64.b64decode(conteudo_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("o conteudo da imagem chegou corrompido")
    if not dados:
        raise ValueError("imagem vazia")
    if len(dados) > LIMITE_BYTES:
        raise ValueError(f"imagem de {len(dados) // 1024 // 1024} MB — "
                         f"o limite e {LIMITE_BYTES // 1024 // 1024} MB")

    ext = _tipo_real(dados)
    if ext is None:
        raise ValueError("isto nao parece uma imagem PNG/JPG/GIF/WEBP/BMP")

    base = store.slugify(Path(nome_original or "quadro").stem)[:40] or "quadro"
    # sufixo de tempo: dois arquivos com o mesmo nome vindos de pastas
    # diferentes nao podem se sobrescrever sem avisar
    arquivo = f"{base}-{int(time.time() * 1000):x}.{ext}"
    (_pasta(roteiro) / arquivo).write_bytes(dados)
    return f"/quadros/{store.slugify(roteiro)}/{arquivo}"


_NOSSA = re.compile(r"^/quadros/([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-.]+)$")


def apagar(url: str) -> bool:
    """Apaga o arquivo de um quadro que nos guardamos.

    URL de fora (http://...) devolve False sem fazer nada: nao e nossa para
    apagar. O regex tambem e a barreira contra `..` no caminho.
    """
    m = _NOSSA.match(str(url or ""))
    if not m:
        return False
    f = store.QUADROS / m.group(1) / m.group(2)
    try:
        f = f.resolve()
        f.relative_to(store.QUADROS.resolve())    # nada fora da pasta
    except (ValueError, OSError):
        return False
    if not f.is_file():
        return False
    f.unlink()
    return True


def apagar_do_roteiro(roteiro: str) -> None:
    """Some com a pasta inteira — chamado quando o roteiro e apagado."""
    shutil.rmtree(store.QUADROS / store.slugify(roteiro), ignore_errors=True)


def limpar_orfaos(roteiro: str, em_uso: set[str]) -> int:
    """Apaga arquivos que nenhum jogo do roteiro referencia mais.

    Um quadro tirado da lista deixaria o arquivo para tras para sempre; como a
    pasta e por roteiro e a fonte da verdade e o proprio roteiro, da para
    varrer com seguranca a cada gravacao dele.
    """
    pasta = store.QUADROS / store.slugify(roteiro)
    if not pasta.is_dir():
        return 0
    usados = {Path(u).name for u in em_uso if _NOSSA.match(str(u or ""))}
    n = 0
    for f in pasta.iterdir():
        if f.is_file() and f.name not in usados:
            f.unlink()
            n += 1
    return n
