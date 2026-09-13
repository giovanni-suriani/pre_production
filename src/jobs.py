"""Trabalhos longos em segundo plano - extrair wav, fatiar, diarizar.

Por que existe: extrair o wav de 69 min leva ~1 min e uma diarizacao do Gemini
em pedacos leva 20+. Uma requisicao HTTP que segura tudo isso da timeout no
navegador e some com o log quando da erro. Aqui o POST devolve um `job_id` na
hora e a tela fica perguntando o que aconteceu.

Um job tem PASSOS. "Rodar diarizacao" e' na verdade fatiar o wav e depois
chamar o script - a tela mostra "passo 2 de 3" em vez de ficar parada num
spinner mudo. Se um passo falha os seguintes nem comecam, e o log fica: o log
E' o produto quando algo da errado.

`after` roda no fim, no mesmo thread: e' o pos-processamento em Python (somar o
offset nos turnos, gravar o manifesto). Fica dentro do job de proposito - se
gravar o manifesto falhar, o job falha, em vez de mentir "ok" pro usuario.
"""

import itertools
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_LOG_LINES = 4000

_counter = itertools.count(1)
_lock = threading.Lock()
_jobs = {}

# linhas `chave=valor` do `-progress pipe:1` do ffmpeg: viram barra, nao log
_KV_LINE = re.compile(r"^\w+=\S*$")


@dataclass
class Step:
    label: str
    cmd: list
    cwd: str | None = None
    env: dict | None = None
    # "ffmpeg" le out_time_us; "regex" usa progress_re com grupos (n, total);
    # None = indeterminado (a tela mostra o log correndo)
    progress_kind: str | None = None
    progress_re: str | None = None
    total_seconds: float | None = None


@dataclass
class Job:
    id: str
    kind: str
    title: str
    steps: list
    meta: dict = field(default_factory=dict)
    after: object = None
    status: str = "queued"        # queued | running | ok | error | cancelled
    step_index: int = 0
    progress: float | None = None
    log: list = field(default_factory=list)
    dropped: int = 0
    error: str | None = None
    result: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    started: float | None = None
    ended: float | None = None
    _proc: object = None
    _cancel: bool = False

    # ------------------------------------------------------------- log
    def say(self, line):
        with _lock:
            self.log.append(line.rstrip())
            if len(self.log) > MAX_LOG_LINES:
                # corta pela frente: o fim do log e' onde esta o erro
                cut = len(self.log) - MAX_LOG_LINES
                del self.log[:cut]
                self.dropped += cut

    def snapshot(self, since=0):
        with _lock:
            first = self.dropped
            start = max(0, since - first)
            lines = self.log[start:]
            return {
                "id": self.id, "kind": self.kind, "title": self.title,
                "status": self.status, "progress": self.progress,
                "step": self.step_index + 1, "steps": len(self.steps),
                "step_label": (self.steps[self.step_index].label
                               if self.step_index < len(self.steps) else ""),
                "error": self.error, "result": self.result, "meta": self.meta,
                "elapsed": (self.ended or time.time()) - (self.started or self.created),
                "log": lines,
                "log_next": first + len(self.log),
            }


def create(kind, title, steps, meta=None, after=None):
    job = Job(id=f"j{next(_counter)}", kind=kind, title=title, steps=steps,
              meta=meta or {}, after=after)
    _jobs[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def get(job_id):
    return _jobs.get(job_id)


def listing(limit=30):
    js = sorted(_jobs.values(), key=lambda j: j.created, reverse=True)[:limit]
    return [{"id": j.id, "kind": j.kind, "title": j.title, "status": j.status,
             "progress": j.progress, "meta": j.meta,
             "created": j.created, "ended": j.ended} for j in js]


def cancel(job_id):
    job = _jobs.get(job_id)
    if not job or job.status not in ("queued", "running"):
        return False
    job._cancel = True
    p = job._proc
    if p and p.poll() is None:
        # taskkill /T: o script de diarizacao pode ter aberto um filho (o
        # 3c_ chama outro python). terminate() sozinho deixaria o neto vivo.
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, creationflags=NO_WINDOW)
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    return True


def _run(job):
    job.status = "running"
    job.started = time.time()
    try:
        for i, step in enumerate(job.steps):
            if job._cancel:
                raise _Cancelled()
            job.step_index = i
            job.progress = None
            job.say(f"── {i + 1}/{len(job.steps)}  {step.label}")
            job.say("$ " + " ".join(
                f'"{a}"' if " " in str(a) else str(a) for a in step.cmd))
            _run_step(job, step)
        if job.after:
            job.step_index = len(job.steps) - 1
            job.progress = None
            job.say("── finalizando")
            out = job.after(job)
            if isinstance(out, dict):
                job.result.update(out)
        job.status = "ok"
        job.progress = 1.0
        job.say(f"[ok] concluido em {time.time() - job.started:.1f}s")
    except _Cancelled:
        job.status = "cancelled"
        job.error = "cancelado"
        job.say("[!] cancelado")
    except Exception as e:
        job.status = "error"
        job.error = str(e)[:2000]
        job.say(f"[erro] {e}")
    finally:
        job.ended = time.time()
        job._proc = None


class _Cancelled(Exception):
    pass


def _run_step(job, step):
    rx = re.compile(step.progress_re) if step.progress_re else None
    try:
        p = subprocess.Popen(
            [str(a) for a in step.cmd], cwd=step.cwd, env=step.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=NO_WINDOW)
    except FileNotFoundError as e:
        raise RuntimeError(f"nao consegui executar {step.cmd[0]!r}: {e}")
    job._proc = p

    for line in p.stdout:
        if job._cancel:
            break
        line = line.rstrip("\n")
        if step.progress_kind == "ffmpeg" and _KV_LINE.match(line):
            import media                      # local: evita ciclo no import
            v = media.ffmpeg_progress(line, step.total_seconds)
            if v is not None:
                job.progress = v
            continue                          # nao polui o log
        if rx:
            m = rx.search(line)
            if m:
                try:
                    n, tot = float(m.group(1)), float(m.group(2))
                    job.progress = max(0.0, min(1.0, n / tot)) if tot else None
                except (ValueError, IndexError):
                    pass
        if line.strip():
            job.say(line)
    code = p.wait()
    if job._cancel:
        raise _Cancelled()
    if code != 0:
        tail = " | ".join(job.log[-3:])
        raise RuntimeError(f"{step.label}: saiu com codigo {code}. {tail}")
