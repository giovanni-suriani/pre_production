"""
Sugere candidatos a corte (Shorts) a partir de uma transcricao do EPISODIO
INTEIRO ja pronta - o `entire_transcribe.json` que a etapa 1 do
pre_production gera com o Whisper. Este script NAO transcreve nada: so' pede
pro Gemini escolher os melhores trechos, dado o texto com timestamps.

Irmao do `scriptsPrimarios\\suggested_shorts.py` (mesma ideia: Gemini escolhe
um intervalo de "turns" numerados para cada clipe), mas sem duplicar a
transcricao - aqui ela e' sempre um arquivo que ja existe, porque este
projeto so' tem uma verdade de transcricao por projeto (ver turns.py).

Uso:
    python suggested_shorts.py --transcript entire_transcribe.json \
        --out suggested_shorts.json --model gemini-3.1-flash-lite
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

DEFAULT_MODEL = "gemini-3.1-flash-lite"


class Clip(BaseModel):
    start_turn: int
    end_turn: int
    title: str


class ClipList(BaseModel):
    clips: list[Clip]


SYSTEM_PROMPT = """Você edita vídeos de um canal de jogos sociais presenciais entre amigos \
(tipo Impostor / jogos de dedução em grupo). Sua tarefa é ler a transcrição com timestamps \
de um episódio e escolher os melhores trechos para virarem cortes/Shorts.

Procure por: acusações, discussões acaloradas, revelações ("eu era o impostor"), piadas, \
reviravoltas, risadas, reações de surpresa. Cada clipe precisa:
- Fazer sentido sozinho, sem contexto anterior (um espectador que nunca viu o episódio \
precisa entender o que está rolando).
- Ter começo e fim marcantes (não cortar no meio de uma frase ou pensamento).
- Ter duração dentro da faixa pedida.
- Não se sobrepor a outro clipe escolhido.

Você recebe os "turns" numerados (cada um é uma fala contínua, já cortada nas pausas \
naturais). Escolha um intervalo contíguo de turns (start_turn até end_turn, inclusive) \
para cada clipe."""


def read_turns(path: Path) -> list[dict]:
    # utf-8-sig: json gerado no Windows por outra ferramenta pode vir com BOM
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        sys.exit(f"{path}: esperava uma lista de turnos, veio {type(raw).__name__}")
    turns = [t for t in raw if isinstance(t, dict) and (t.get("text") or "").strip()]
    if not turns:
        sys.exit(f"{path}: nenhum turno com texto")
    return turns


def build_transcript_block(turns: list[dict]) -> str:
    return "\n".join(
        f"[{i}] {t['start']:.2f}-{t['end']:.2f}: {t['text']}"
        for i, t in enumerate(turns)
    )


def select_clips(client: genai.Client, turns: list[dict], model: str,
                  min_duration: float, max_duration: float) -> list[dict]:
    user_message = (
        f"Duração alvo de cada clipe: entre {min_duration:.0f} e {max_duration:.0f} segundos.\n\n"
        f"Transcrição ({len(turns)} turns):\n{build_transcript_block(turns)}"
    )

    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ClipList,
                    temperature=0.4,
                ),
            )
            break
        except errors.APIError as e:
            if e.code in (401, 403):
                sys.exit("Credenciais inválidas: defina GEMINI_API_KEY (https://aistudio.google.com/apikey).")
            if e.code == 429:
                sys.exit("Rate limit atingido na API do Gemini. Tente novamente em alguns instantes.")
            if e.code == 503 and attempt < max_attempts:
                wait = 2 ** attempt
                print(f"Modelo sobrecarregado (503), tentando de novo em {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"Erro da API do Gemini ({e.code}): {e.message}")

    return json.loads(response.text)["clips"]


def build_output(turns: list[dict], raw_clips: list[dict], min_duration: float, max_duration: float) -> list[dict]:
    clips = []
    for clip in raw_clips:
        i, j = clip["start_turn"], clip["end_turn"]
        if not (0 <= i <= j < len(turns)):
            print(f"Aviso: clipe com índices inválidos ignorado: {clip}", file=sys.stderr)
            continue
        start = turns[i]["start"]
        end = turns[j]["end"]
        duration = end - start
        if duration < min_duration or duration > max_duration:
            print(
                f"Aviso: clipe '{clip['title']}' fora da faixa de duração "
                f"({duration:.1f}s) — mantido, revise manualmente.",
                file=sys.stderr,
            )
        clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(duration, 2),
            "title": clip["title"],
            "transcript": " ".join(turns[k]["text"] for k in range(i, j + 1)),
        })
    clips.sort(key=lambda c: c["start"])
    return clips


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sugere candidatos a corte a partir de uma transcrição já pronta.")
    parser.add_argument("--transcript", type=Path, required=True,
                         help="entire_transcribe.json - turns {start,end,text}, tempo absoluto")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-duration", type=float, default=15.0)
    parser.add_argument("--max-duration", type=float, default=60.0)
    args = parser.parse_args()

    if not args.transcript.exists():
        sys.exit(f"transcrição não encontrada: {args.transcript}")

    turns = read_turns(args.transcript)
    print(f"{len(turns)} turnos lidos de {args.transcript.name}. "
          f"Pedindo pro Gemini ({args.model}) escolher os melhores trechos...")

    client = genai.Client()
    raw_clips = select_clips(client, turns, args.model, args.min_duration, args.max_duration)
    clips = build_output(turns, raw_clips, args.min_duration, args.max_duration)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(clips)} clipes salvos em {args.out}")


if __name__ == "__main__":
    main()
