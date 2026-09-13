r"""Legenda estilizada: tira o nome do falante e gera o ASS colorido.

Por que dois arquivos
---------------------
O SRT com "Nome: texto" e' otimo pra revisar no editor e pessimo na tela: o
espectador do short nao quer ler "Cupertino:" trinta vezes em cinco minutos.
Mas o nome e' justamente a informacao que faz a legenda ficar bonita - ele
vira COR. Entao o nome sai do texto e entra no estilo.

Saem dois arquivos ao lado do SRT de entrada:

  <nome>.limpo.srt  - so o texto, pra importar no Resolve/CapCut/YouTube
  <nome>.ass        - Poppins, uma cor por falante, caixa de fundo, ja
                      enquadrado em 1080x1920

O .ass e' o que da o resultado "CapCut Pro". Ele nao entra no Resolve como
legenda (o Resolve importa SRT), mas o ffmpeg queima ele no video com libass
exatamente como esta - veja `--ajuda-queimar`.

O limite honesto
----------------
Aqui a legenda troca no TURNO, porque e' isso que o Whisper deste projeto
entrega (`turnsWhisper_*.json` nao tem timestamp por palavra). O CapCut pinta
palavra por palavra porque tem tempo por palavra. Pra chegar la, a
transcricao precisa rodar com `word_timestamps=True` - o resto deste arquivo
ja esta pronto pra receber isso.

Uso
---
    python estilo_legenda.py <arquivo.srt>
    python estilo_legenda.py <arquivo.srt> --tam 92 --fundo contorno
    python estilo_legenda.py <arquivo.srt> --cor Heitor=#FF6B6B
"""

import argparse
import os
import re
import sys

# Cor por falante. A ideia e' contraste alto entre elas E contra a caixa
# escura - cor pastel some no celular do espectador.
CORES_PADRAO = {
    "Cupertino": "#FFD84D",   # amarelo
    "Heitor": "#4DE1FF",      # ciano
    "Giovanni": "#A8FF4D",    # verde-limao
}
# pra qualquer nome que apareca e nao esteja no mapa acima
CORES_RESERVA = ["#FF7AD9", "#FFA24D", "#9B8CFF", "#5CFFC8"]
COR_SEM_NOME = "#FFFFFF"

# 00:00:01,000 --> 00:00:04,000
_TIME = r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
_CUE = re.compile(rf"^\s*{_TIME}\s*-->\s*{_TIME}", re.M)

# "Cupertino: texto" - exige inicial maiuscula pra nao comer uma fala que so
# tem dois pontos no meio ("olha so:")
_PREFIXO = re.compile(r"^([A-ZÀ-ÝŽ][^\s:]{0,23}):\s+")


# ---------------------------------------------------------------- leitura

def ler_srt(caminho):
    """SRT -> [{start, end, text}] em segundos. Quebra de linha vira espaco."""
    with open(caminho, "r", encoding="utf-8-sig") as fh:
        texto = fh.read()
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    cues = list(_CUE.finditer(texto))
    segs = []
    for i, m in enumerate(cues):
        def _s(g):
            return (int(m.group(g)) * 3600 + int(m.group(g + 1)) * 60
                    + int(m.group(g + 2)) + int(m.group(g + 3).ljust(3, "0")) / 1000)
        corpo = texto[m.end():cues[i + 1].start() if i + 1 < len(cues) else len(texto)]
        linhas = [ln.strip() for ln in corpo.split("\n") if ln.strip()]
        # a ultima linha antes do proximo cue e' o numero dele
        if linhas and linhas[-1].isdigit() and i + 1 < len(cues):
            linhas = linhas[:-1]
        corpo = " ".join(linhas).strip()
        if corpo:
            segs.append({"start": _s(1), "end": _s(5), "text": corpo})
    return segs


def separar_falante(segs):
    """Tira "Nome: " da frente e devolve o nome num campo proprio.

    Um prefixo so conta como falante se aparecer em pelo menos duas legendas.
    Nome de gente se repete; frase que por acaso comeca com dois pontos, nao.
    """
    contagem = {}
    for seg in segs:
        m = _PREFIXO.match(seg["text"])
        if m:
            contagem[m.group(1)] = contagem.get(m.group(1), 0) + 1
    nomes = {n for n, c in contagem.items() if c >= 2}

    out = []
    for seg in segs:
        m = _PREFIXO.match(seg["text"])
        if m and m.group(1) in nomes:
            out.append({**seg, "text": seg["text"][m.end():].strip(), "name": m.group(1)})
        else:
            out.append({**seg, "name": None})
    return out, sorted(nomes)


# ---------------------------------------------------------------- escrita

def _stamp_srt(s):
    ms = int(round(max(0.0, s) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def _stamp_ass(s):
    cs = int(round(max(0.0, s) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    seg, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{seg:02d}.{cs:02d}"


def escrever_srt(segs, caminho):
    blocos = []
    for i, seg in enumerate(segs, 1):
        blocos.append(f"{i}\n{_stamp_srt(seg['start'])} --> {_stamp_srt(seg['end'])}\n{seg['text']}\n")
    with open(caminho, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(blocos))


def quebrar(texto, max_chars, max_linhas=3):
    """Quebra em linhas curtas e EQUILIBRADAS.

    Quebra gulosa deixa a ultima linha com uma palavra sozinha, que no vertical
    fica visivelmente torto. Entao primeiro descobrimos em quantas linhas o
    texto cabe, depois dividimos o comprimento por esse numero.
    """
    palavras = texto.split()
    if not palavras:
        return texto

    def montar(n):
        alvo = -(-len(texto) // n)
        linhas, atual = [], ""
        for p in palavras:
            cand = f"{atual} {p}".strip()
            # quebra quando a palavra estoura o limite duro OU quando ela
            # AFASTA a linha do alvo mais do que fecha-la agora afastaria. So
            # testar `> alvo` deixava "quem vai" sozinho em cima de
            # "comecar mostrando eu?"
            estoura = len(cand) > max_chars
            piora = abs(len(cand) - alvo) > abs(len(atual) - alvo)
            if atual and len(linhas) < n - 1 and (estoura or piora):
                linhas.append(atual)
                atual = p
            else:
                atual = cand
        if atual:
            linhas.append(atual)
        return linhas

    # a ULTIMA linha nao tem pra onde quebrar, entao ela e' quem estoura o
    # limite. Se estourou, tenta com uma linha a mais antes de desistir.
    # o minimo TEM que caber em max_linhas, senao o range abaixo sai vazio e a
    # funcao devolve None. Texto que nao cabe estoura o limite de largura de
    # proposito - melhor uma linha longa do que legenda sumida.
    minimo = max(1, min(max_linhas, -(-len(texto) // max_chars)))
    melhor = None
    for n in range(minimo, max_linhas + 1):
        linhas = montar(n)
        melhor = melhor or linhas
        if max(len(x) for x in linhas) <= max_chars:
            melhor = linhas
            break
    return "\\N".join(melhor)


def _ass_cor(hexa, alfa="00"):
    """#RRGGBB -> &HAABBGGRR. O ASS inverte os canais e alfa e' TRANSPARENCIA."""
    h = hexa.lstrip("#")
    return f"&H{alfa}{h[4:6]}{h[2:4]}{h[0:2]}"


def escrever_ass(segs, caminho, nomes, cores, fonte, tam, largura, altura,
                 margem_v, margem_h, max_chars, fundo, opacidade_fundo, dur_max):
    # BorderStyle 3 desenha uma caixa POR LINHA: com linhas de larguras
    # diferentes o bloco fica serrilhado, nada a ver com o CapCut. O 4
    # (extensao do libass) pinta um retangulo unico atras do bloco inteiro -
    # e ai a BackColour e' a caixa e a OutlineColour vira o contorno da letra.
    if fundo == "caixa":
        border_style, contorno, sombra = 4, 3, 0
        cor_caixa = _ass_cor("#000000", opacidade_fundo)
    elif fundo == "contorno":
        # no BorderStyle 1 a BackColour deixa de ser caixa e vira a SOMBRA
        border_style, contorno, sombra = 1, 7, 4
        cor_caixa = _ass_cor("#000000", "40")
    else:  # nenhum - so o contorno segurando a letra
        border_style, contorno, sombra = 1, 7, 0
        cor_caixa = _ass_cor("#000000", "FF")

    cab = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {largura}",
        f"PlayResY: {altura}",
        # 0 = o \N manda, e o libass ainda quebra sozinho se sobrar linha
        # comprida. Rede de seguranca: nome longo demais nao vaza da tela.
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,"
        " OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,"
        " ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,"
        " Alignment, MarginL, MarginR, MarginV, Encoding",
    ]

    estilos = list(nomes) + ["_"]
    for nome in estilos:
        cor = cores.get(nome, COR_SEM_NOME)
        # ordem: Primary(texto), Secondary, Outline(contorno), Back(caixa)
        cab.append(
            f"Style: {nome},{fonte},{tam},{_ass_cor(cor)},{_ass_cor(cor)},"
            f"{_ass_cor('#000000')},{cor_caixa},0,0,0,0,"
            f"100,100,0,0,{border_style},{contorno},{sombra},"
            f"2,{margem_h},{margem_h},{margem_v},1"
        )

    cab += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    cortadas = 0
    for seg in segs:
        estilo = seg["name"] if seg["name"] in nomes else "_"
        texto = quebrar(seg["text"], max_chars)
        fim = seg["end"]
        # o Whisper estica a ultima legenda ate a proxima fala: "honesto" fica
        # 16 s parado na tela. Cortar deixa a tela limpa no silencio, que e' o
        # que o silencio pede.
        if dur_max and fim - seg["start"] > dur_max:
            fim = seg["start"] + dur_max
            cortadas += 1
        cab.append(
            f"Dialogue: 0,{_stamp_ass(seg['start'])},{_stamp_ass(fim)},"
            f"{estilo},,0,0,0,,{{\\fad(70,70)}}{texto}"
        )

    with open(caminho, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(cab) + "\n")
    return cortadas


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="Tira o nome do falante do SRT e gera o ASS colorido.")
    ap.add_argument("srt", help="arquivo .srt de entrada (com 'Nome: texto')")
    ap.add_argument("--fonte", default="Poppins SemiBold")
    ap.add_argument("--tam", type=int, default=84, help="corpo da fonte em px de PlayRes (padrao 84)")
    ap.add_argument("--largura", type=int, default=1080)
    ap.add_argument("--altura", type=int, default=1920)
    ap.add_argument("--margem-v", type=int, default=420,
                    help="distancia do rodape; 420 tira a legenda de cima da UI do app")
    ap.add_argument("--margem-h", type=int, default=90)
    ap.add_argument("--max-chars", type=int, default=20, help="caracteres por linha")
    ap.add_argument("--fundo", choices=["caixa", "contorno", "nenhum"], default="caixa")
    ap.add_argument("--dur-max", type=float, default=5.0,
                    help="segundos maximos por legenda no .ass; 0 desliga (padrao 5)")
    ap.add_argument("--opacidade-fundo", default="80",
                    help="transparencia da caixa em hex, 00=solida FF=invisivel (padrao 80)")
    ap.add_argument("--cor", action="append", default=[], metavar="Nome=#RRGGBB",
                    help="sobrescreve a cor de um falante (pode repetir)")
    ap.add_argument("--so-limpo", action="store_true", help="gera so o .limpo.srt")
    ap.add_argument("--ajuda-queimar", action="store_true",
                    help="mostra o comando ffmpeg pra queimar o .ass no video")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.srt):
        print(f"nao encontrei: {args.srt}", file=sys.stderr)
        return 1

    segs = ler_srt(args.srt)
    if not segs:
        print("nenhuma legenda lida - o arquivo esta vazio ou nao e' SRT", file=sys.stderr)
        return 1
    segs, nomes = separar_falante(segs)

    cores = dict(CORES_PADRAO)
    reserva = iter(CORES_RESERVA)
    for nome in nomes:
        if nome not in cores:
            cores[nome] = next(reserva, COR_SEM_NOME)
    for par in args.cor:
        nome, _, hexa = par.partition("=")
        cores[nome.strip()] = hexa.strip()

    base = os.path.splitext(args.srt)[0]
    saida_srt = f"{base}.limpo.srt"
    escrever_srt(segs, saida_srt)

    com_nome = sum(1 for s in segs if s["name"])
    print(f"{len(segs)} legendas | falantes: {', '.join(nomes) or '(nenhum)'}"
          f" | {com_nome} com nome removido")
    print(f"-> {saida_srt}")

    if not args.so_limpo:
        saida_ass = f"{base}.ass"
        cortadas = escrever_ass(
            segs, saida_ass, nomes, cores, args.fonte, args.tam,
            args.largura, args.altura, args.margem_v, args.margem_h,
            args.max_chars, args.fundo, args.opacidade_fundo, args.dur_max)
        print(f"-> {saida_ass}"
              + (f"  ({cortadas} legendas encurtadas p/ {args.dur_max:g}s)" if cortadas else ""))
        for nome in nomes:
            print(f"   {nome}: {cores.get(nome)}")
        if args.ajuda_queimar:
            print(ajuda_queimar(saida_ass, args.largura, args.altura))
    return 0


def ajuda_queimar(caminho_ass, largura, altura):
    """O filtro `ass` do ffmpeg le o caminho como se fosse uma expressao: no
    Windows a barra invertida e' escape e o `:` separa opcao. Trocar por `/` e
    escapar o `:` do drive resolve - e' o passo que quase sempre erra."""
    p = os.path.abspath(caminho_ass).replace("\\", "/").replace(":", "\\:", 1)
    return (
        "\nqueimar no video (o .ass ja traz cor, fonte e posicao):\n\n"
        f"  ffmpeg -i ENTRADA.mp4 \\\n"
        f"    -vf \"crop=ih*9/16:ih,scale={largura}:{altura},ass='{p}'\" \\\n"
        "    -c:v libx264 -crf 18 -preset slow -c:a copy SAIDA.mp4\n\n"
        "se o video ja for vertical, tire o crop/scale e deixe so o ass=.\n"
        "a fonte precisa estar INSTALADA no Windows - o libass nao le .ttf solto."
    )


if __name__ == "__main__":
    raise SystemExit(main())
