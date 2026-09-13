r"""Teste de interface: abre as tres paginas num Chrome de verdade.

Nao e' teste unitario. Ele sobe um Chrome headless, navega pelas rotas e ouve o
console - porque o modo como uma pagina sem build quebra e' com um erro de
javascript que deixa a tela em branco e nao aparece em lugar nenhum do
servidor. Um `console.error` aqui vale mais do que uma assercao sobre uma
funcao que ninguem chamou.

Depende de `websocket-client`, que ja esta no Python 3.12 do sistema (e' o que
a suite do turnsEditor usa). Roda com o servidor no ar:

    C:\Users\talco\AppData\Local\Programs\Python\Python312\python.exe tests\ui.py

Precisa de um projeto com pelo menos um corte pra testar a etapa 3 - rode o
`tests\smoke.py --keep` antes.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

BASE = "http://127.0.0.1:8740"
PORT = 9351
ok_count, fail_count = 0, 0


def check(cond, msg):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  [ok] {msg}")
    else:
        fail_count += 1
        print(f"  [FALHOU] {msg}")
    return cond


def find_chrome():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")):
        if os.path.isfile(p):
            return p
    return shutil.which("chrome") or shutil.which("msedge")


class Page:
    """Um Chrome headless dirigido por CDP. So o que este teste precisa."""

    def __init__(self, chrome, profile):
        self.proc = subprocess.Popen(
            [chrome, f"--remote-debugging-port={PORT}", "--headless=new",
             "--disable-gpu", "--no-first-run", "--window-size=1600,1000",
             # sem isto o Chrome recusa o handshake do CDP com 403
             "--remote-allow-origins=*",
             f"--user-data-dir={profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
                    tabs = json.load(r)
                url = next((t["webSocketDebuggerUrl"] for t in tabs
                            if t["type"] == "page"), None)
                if url:
                    break
            except Exception:
                time.sleep(0.4)
        if not url:
            raise SystemExit("nao consegui falar com o Chrome via CDP")
        self.ws = websocket.create_connection(url, timeout=40)
        self.id = 0
        self.logs = []
        self.send("Runtime.enable")
        self.send("Page.enable")
        # O perfil e' reaproveitado entre execucoes, entao o Chrome servia
        # app.js/cortes.js do cache e o teste media a versao ANTERIOR do
        # arquivo - falha (ou aprovacao) que nao tem nada a ver com o codigo
        # em disco. Sem cache, o que roda e' o que esta salvo.
        self.send("Network.enable")
        self.send("Network.setCacheDisabled", cacheDisabled=True)

    def send(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method,
                                 "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                return msg.get("result", {})
            self._event(msg)

    def _event(self, msg):
        m = msg.get("method")
        if m == "Runtime.consoleAPICalled" and msg["params"]["type"] in (
                "error", "warning"):
            txt = " ".join(str(a.get("value", a.get("description", "")))
                           for a in msg["params"]["args"])
            self.logs.append(("console." + msg["params"]["type"], txt))
        elif m == "Runtime.exceptionThrown":
            d = msg["params"]["exceptionDetails"]
            self.logs.append(("exception", d.get("text", "") + " " + str(
                d.get("exception", {}).get("description", ""))[:300]))

    def pump(self, seconds):
        """Drena eventos por N segundos (é onde os erros chegam)."""
        end = time.time() + seconds
        self.ws.settimeout(0.35)
        while time.time() < end:
            try:
                self._event(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(40)

    def goto(self, path, settle=2.5):
        self.logs.clear()
        self.send("Page.navigate", url=BASE + path)
        self.pump(settle)

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        if "exceptionDetails" in r:
            return {"__erro__": r["exceptionDetails"].get("text")}
        return r.get("result", {}).get("value")

    def key(self, k, code, vk):
        """Tecla DE VERDADE, via CDP - nao `onkeydown(...)` na mao.

        E' a diferenca que a suite do turnsEditor ja tinha mostrado: chamada de
        funcao nao passa pelo `e.target`, entao nao pega o caso de a tecla ser
        engolida (ou nao) por um campo em foco.
        """
        for t in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", type=t, key=k, code=code,
                      windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def errors(page):
    """Erros de verdade. O aviso do Chrome sobre autoplay nao conta."""
    skip = ("favicon", "autoplay", "AudioContext", "play() failed",
            "Failed to load resource: net::ERR_ABORTED",
            # corte sem Whisper e' estado normal, nao defeito: o editor avisa
            # que a coluna "o que foi dito" vai ficar vazia e segue funcionando
            "ainda nao tem transcricao")
    return [f"{k}: {v}" for k, v in page.logs
            if not any(s in v for s in skip)]


def main():
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("Chrome nao encontrado")
    try:
        with urllib.request.urlopen(BASE + "/api/state", timeout=10) as r:
            state = json.load(r)
    except Exception:
        raise SystemExit(f"servidor fora do ar em {BASE} - rode o run.bat")

    profile = os.path.join(os.environ.get("TEMP", "."), "preprod_ui_profile")
    page = Page(chrome, profile)
    try:
        print("\n1. etapa 1 — /")
        page.goto("/", 3.0)
        check(page.js("document.querySelectorAll('nav.steps, nav .steps').length > 0"),
              "barra de etapas desenhada")
        check(page.js("document.querySelectorAll('#srcSelect option').length > 0"),
              "lista de videos da pasta de origem carregou")
        check(page.js("document.querySelectorAll('#nParts .row').length >= 3"),
              "linhas de participante criadas")
        # o tamanho da mesa: escolher 2 tem que reescrever as cadeiras (pontas,
        # centro VAZIO) - e' o que vai no --roster do Gemini, entao uma cadeira
        # a mais aqui e' um falante inventado la
        page.js("(() => { const s = document.getElementById('nCount');"
                " s.value = '2'; s.onchange(); })()")
        page.pump(0.4)
        assentos = page.js("[...document.querySelectorAll('#nParts .row select')]"
                           ".map(x => x.value).join(',')")
        check(assentos == "left,right", f"2 participantes = esquerda e direita ({assentos})")
        check("3 vozes" in (page.js("document.getElementById('nVoices').textContent") or ""),
              "2 na mesa + a voz fora de quadro (ligada por padrao) = 3 vozes")
        page.js("(() => { const c = document.getElementById('nOffcam');"
                " c.checked = false; c.onchange(); })()")
        page.pump(0.3)
        check("2 vozes" in (page.js("document.getElementById('nVoices').textContent") or ""),
              "desligar a voz fora de quadro tira uma voz da conta")
        page.js("(() => { const s = document.getElementById('nCount');"
                " s.value = '3'; s.onchange(); })()")
        page.pump(0.3)
        check(page.js("document.querySelectorAll('#nParts .row').length") == 3,
              "voltar para 3 reconstroi a lista")
        check(page.js("!!document.getElementById('projList')"), "lista de projetos existe")
        errs = errors(page)
        check(not errs, f"sem erro de console{': ' + ' | '.join(errs[:3]) if errs else ''}")

        print("\n2. ambiente (doctor)")
        page.js("document.getElementById('docBtn').click()")
        page.pump(6)
        check("ffmpeg" in (page.js("document.getElementById('docOut').textContent") or ""),
              "verificacao de ambiente respondeu")

        print("\n3. etapa 2 — /cortes")
        page.goto("/cortes", 4.0)
        check(page.js("document.querySelectorAll('#projSelect option').length > 0"),
              "seletor de projeto preenchido")
        check(page.js("document.querySelectorAll('#cutList .item').length > 0"),
              "cortes do projeto listados")
        # o titulo tem que ficar na coluna 1. Ja ficou na 2 uma vez: o `.side`
        # tinha grid-row definido e coluna automatica, entao era colocado antes
        # e agarrava a coluna 1 - a lista inteira saiu espelhada.
        check(page.js("getComputedStyle(document.querySelector('#cutList .item .t'))"
                      ".gridColumnStart === '1'"),
              "o nome do corte fica na coluna da esquerda")
        # cartao encolhido derrama conteudo por cima do cartao seguinte
        over = page.js("[...document.querySelectorAll('main > section.card')]"
                       ".filter(c => c.scrollHeight > c.clientHeight + 1)"
                       ".map(c => c.id || c.querySelector('h2').textContent)")
        check(not over, f"nenhum cartao com conteudo vazando{': ' + str(over) if over else ''}")
        # a onda so tem largura depois que a secao de novo corte aparece -
        # antes disso ela esta display:none e o canvas mede 0
        page.js("document.getElementById('newCutBtn').click()")
        page.pump(1.5)
        w = page.js("(function(){const c=document.getElementById('wave');"
                    "const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
                    "let n=0;for(let i=3;i<x.length;i+=4)if(x[i]>0)n++;return n;})()")
        check(isinstance(w, int) and w > 1000,
              f"a onda foi desenhada no canvas ({w} pixels pintados)")
        check(page.js("document.getElementById('pStart').value.length > 0"),
              "o trecho ja vem pre-marcado nos campos de tempo")
        check((page.js("document.getElementById('pFrame').textContent") or "") not in ("", "—"),
              "o frame de origem aparece junto com o tempo")

        # playhead + I/O: o pedido e' marcar o trecho pelo cursor, com as
        # mesmas teclas do editor de turnos
        page.js("(function(){const c=document.getElementById('wave');"
                "const r=c.getBoundingClientRect();"
                "c.dispatchEvent(new MouseEvent('mousedown',"
                "{clientX:r.left+600,clientY:r.top+80,bubbles:true}));"
                "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));})()")
        page.pump(0.8)
        head = page.js("W.play")
        check(isinstance(head, (int, float)) and head > 0,
              f"clicar na onda move o playhead ({head and round(head, 2)}s)")
        check((page.js("document.getElementById('pClock').textContent") or "") != "00:00.000",
              "o relogio acompanha o playhead")
        page.key("i", "KeyI", 73)
        page.pump(0.5)
        check(abs((page.js("W.a") or -1) - head) < 0.05, "`I` marca o inicio no playhead")
        page.js("setPlayhead(W.play + 30)")
        page.pump(0.3)
        page.key("o", "KeyO", 79)
        page.pump(0.5)
        check(abs((page.js("W.b") or -1) - (head + 30)) < 0.2, "`O` marca o fim no playhead")
        before = page.js("W.play")
        page.key("ArrowRight", "ArrowRight", 39)
        page.pump(0.3)
        fps = page.js("PROJ.fps") or 60
        check(abs((page.js("W.play") - before) - 1 / fps) < 0.002,
              "seta anda exatamente um frame")
        # digitar num campo nao pode disparar atalho
        page.js("document.getElementById('pStart').focus()")
        mark = page.js("W.a")
        page.key("i", "KeyI", 73)
        page.pump(0.3)
        check(page.js("W.a") == mark, "`I` nao dispara com o foco num campo de tempo")
        page.js("document.getElementById('pStart').blur()")
        errs = errors(page)
        check(not errs, f"sem erro de console{': ' + ' | '.join(errs[:3]) if errs else ''}")

        print("\n4. abrir o corte e ver os metodos")
        page.js("document.querySelector('#cutList .item').click()")
        page.pump(3.5)
        check(page.js("!document.getElementById('cutDetail').classList.contains('hidden')"),
              "detalhe do corte abriu")
        # 2, nao 5: a tela esconde os metodos que sairam de uso (HIDDEN_METHODS
        # em cortes.js) e mostra so o que se roda de verdade hoje - o Gemini em
        # pedacos e o Whisper. O numero antigo era de quando todos apareciam.
        check(page.js("document.querySelectorAll('#methodList .item').length >= 2"),
              "metodos de diarizacao listados")
        # uma linha por pessoa COM cadeira, mais o `cut`. Quem esta fora de
        # quadro nao tem seletor (nao ganha track), e a mesa nao tem tamanho
        # fixo: um projeto de dois da 3, um de tres da 4.
        n_partic = page.js("(PROJ.participants||[]).length")
        check(page.js("document.querySelectorAll('#dTracks select[data-name]').length")
              == n_partic + 1,
              f"mapa de tracks tem uma linha por pessoa + cut ({n_partic} + 1)")
        check(page.js("document.querySelectorAll('#filesBody tr').length > 0"),
              "resultados do corte listados")
        # fora de quadro nao pode ter seletor de track: ele e' ausencia de track
        check(page.js("![...document.querySelectorAll('#dTracks select[data-name]')]"
                      ".some(s=>s.dataset.name==='no_name')"),
              "`no_name` aparece sem seletor de track")
        errs = errors(page)
        check(not errs, f"sem erro de console{': ' + ' | '.join(errs[:3]) if errs else ''}")

        print("\n5. etapa 3 — /turnos")
        # entra pelo link explicito, como o botao da etapa 2 faz - e nao
        # confiando no corte ativo que sobrou de outra sessao (que pode ter
        # ido pra lixeira no meio do caminho)
        alvo = page.js("(function(){const a=[...document.querySelectorAll('.step')]"
                       ".find(x=>x.textContent.includes('Turnos'));"
                       "return a ? a.getAttribute('href') : ''})()")
        check(alvo and "projeto=" in alvo,
              f"a etapa 2 monta o link do editor com projeto e corte ({alvo})")
        page.goto(alvo or "/turnos", 5.0)
        check(page.js("document.querySelectorAll('#fileSelect option').length > 0"),
              "o editor listou os arquivos de turnos do corte")
        check(page.js("document.querySelectorAll('#turnsBody tr').length > 0"),
              "tabela de turnos preenchida")

        # O <select> saiu de vista mas TEM que continuar no DOM: o app.js e'
        # copia literal do turnsEditor, le e escreve `fileSelect.value` e
        # pendura o carregamento no `change` dele. Se alguem "limpar" o HTML
        # tirando o select, o editor para de carregar - e o teste acima, que so
        # conta `option`, continuaria passando.
        check(page.js("getComputedStyle(document.getElementById('fileSelect')"
                      ".closest('label')).display === 'none'"),
              "o seletor de arquivos saiu de vista")
        check(page.js("!!document.getElementById('openTurnsBtn')"),
              "o botao que abre o dialogo esta no lugar dele")
        # o cabecalho tem que dizer em que corte estamos e que arquivo esta
        # aberto - era o que faltava quando isso era so um dropdown de nomes
        # o projeto e o corte vem do LINK, nao escritos aqui: o corte ativo
        # muda conforme quem esta usando o app, e um nome fixo no teste
        # falharia por motivo nenhum na primeira vez que voce criasse outro
        alvo_q = urllib.parse.parse_qs(urllib.parse.urlparse(alvo or "").query)
        quer_proj = (alvo_q.get("projeto") or [""])[0]
        quer_cut = (alvo_q.get("corte") or [""])[0]
        ctx = page.js("(document.querySelector('.openturns .lbl')||{}).textContent")
        check(ctx and quer_proj and quer_proj in ctx and quer_cut in ctx,
              f"o cabecalho nomeia projeto e corte ({(ctx or '').strip()[:60]})")
        fname = page.js("(document.querySelector('.openrow .fname')||{}).textContent")
        sel_v = page.js("document.getElementById('fileSelect').value")
        check(fname and fname == (sel_v or "").split("\\")[-1],
              f"o nome do arquivo aberto bate com o do editor ({fname})")
        meta = page.js("(document.querySelector('.openrow .fmeta')||{}).textContent")
        check(meta and "turnos" in meta,
              f"e vem com os numeros do arquivo ({' '.join((meta or '').split())[:50]})")

        # clicar num turno leva ele pro topo da lista. So da pra afirmar isso
        # se a lista rolar: num corte de poucos turnos ela cabe inteira na
        # tela, nao ha pra onde rolar, e cobrar scroll seria cobrar o
        # impossivel.
        rolavel = page.js("(function(){const w=document.querySelector('.tablewrap');"
                          "return w.scrollHeight - w.clientHeight})()")
        if (rolavel or 0) > 120:
            page.js("(function(){const rs=document.querySelectorAll('#turnsBody tr');"
                    "rs[Math.min(rs.length-1,10)].querySelector('.c-idx').click()})()")
            page.pump(1.5)
            d = page.js("(function(){const w=document.querySelector('.tablewrap');"
                        "const rs=document.querySelectorAll('#turnsBody tr');"
                        "const tr=rs[Math.min(rs.length-1,10)];"
                        "const h=w.querySelector('thead').getBoundingClientRect().height;"
                        "return {d:Math.round(tr.getBoundingClientRect().top"
                        " - w.getBoundingClientRect().top - h),"
                        "s:Math.round(w.scrollTop),sel:tr.classList.contains('sel')}})()")
            check(d and abs(d["d"]) <= 3 and d["s"] > 0,
                  f"o turno clicado sobe pro topo da lista (sobra {d and d['d']}px, "
                  f"scrollTop {d and d['s']})")
            check(d and d["sel"], "e continua sendo o turno selecionado")

            # o mesmo pela TIMELINE: clicar num bloco tem que trazer a linha
            # dele pro topo. O clique vai como MouseEvent porque clientX/
            # clientY e' tudo que os dois handlers leem do evento.
            r = page.js("""(function(){
              const wave=document.getElementById('wave');
              const b=wave.getBoundingClientRect(), m=waveMetrics();
              const list=sorted();
              if (list.length < 3) return {erro:'poucos turnos'};
              const t=list[Math.min(list.length-1,14)];
              const x=timeToX((t.start+t.end)/2, m.w);
              if (x < 2 || x > m.w-2) return {erro:'turno fora da janela da onda'};
              let y=null;
              for (let yy=m.h-3; yy>m.h-80; yy--) {
                const h=hitTest(x,yy,m.w,m.h);
                if (h && !h.edge && h.turn.uid===t.uid) { y=yy; break; }
              }
              if (y===null) return {erro:'nao achei ponto dentro do bloco'};
              wave.dispatchEvent(new MouseEvent('mousedown',
                {clientX:b.left+x, clientY:b.top+y, button:0, bubbles:true}));
              window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
              return {uid:t.uid};
            }())""")
            if r and not r.get("erro"):
                page.pump(1.5)
                w = page.js("(function(){const w=document.querySelector('.tablewrap');"
                            "const tr=document.querySelector('#turnsBody tr.sel');"
                            "if(!tr) return null;"
                            "const h=w.querySelector('thead').getBoundingClientRect().height;"
                            "return {uid:+tr.dataset.uid,"
                            "d:Math.round(tr.getBoundingClientRect().top"
                            " - w.getBoundingClientRect().top - h)}})()")
                check(w and w["uid"] == r["uid"] and abs(w["d"]) <= 3,
                      f"clicar no bloco da timeline sobe a linha dele pro topo "
                      f"(sobra {w and w['d']}px)")
                # clique no vazio nao tem "linha em questao" - nao pode rolar
                antes = page.js("Math.round(document.querySelector"
                                "('.tablewrap').scrollTop)")
                page.js("(function(){const wave=document.getElementById('wave');"
                        "const b=wave.getBoundingClientRect();"
                        "wave.dispatchEvent(new MouseEvent('mousedown',"
                        "{clientX:b.left+40,clientY:b.top+6,button:0,bubbles:true}));"
                        "window.dispatchEvent(new MouseEvent('mouseup',"
                        "{bubbles:true}))}())")
                page.pump(1.2)
                dep = page.js("Math.round(document.querySelector"
                              "('.tablewrap').scrollTop)")
                check(antes == dep,
                      f"clique fora dos blocos nao mexe na lista ({antes} -> {dep})")
            else:
                print(f"  [--] nao deu pra mirar num bloco da onda "
                      f"({r and r.get('erro')}) - clique na timeline nao verificado")
        else:
            print(f"  [--] lista curta demais pra rolar ({rolavel}px) - "
                  f"scroll do clique nao verificado")

        check(page.js("!!document.querySelector('nav.nav')"),
              "barra de etapas tambem no editor")
        check(page.js("getComputedStyle(document.body).gridTemplateRows.split(' ').length === 3"),
              "o grid do body abriu espaco pra barra (3 linhas)")

        # O shell.css carrega DEPOIS do style.css aqui. Todo seletor global que
        # escapar do escopo `body.page` ganha do editor em silencio - foi o que
        # aconteceu: um `.card { padding }` inocente virou padding a mais no
        # deck e gap a mais no ledger. Estes tres valores sao do style.css
        # original; se algum mudar, e' porque a casca vazou de novo.
        deck = page.js("getComputedStyle(document.querySelector('.card.deck')).padding")
        check(deck == "14px 16px 10px",
              f"o deck do editor mantem o padding dele ({deck})")
        gap = page.js("getComputedStyle(document.querySelector('.card.ledger')).gap")
        check(gap == "normal", f"o ledger do editor nao ganhou gap ({gap})")
        icon = page.js("(function(){const r=document.getElementById('cfgBtn')"
                       ".getBoundingClientRect();return Math.round(r.width)+'x'"
                       "+Math.round(r.height)})()")
        check(icon == "34x34", f"os botoes de icone do editor seguem quadrados ({icon})")

        errs = errors(page)
        check(not errs, f"sem erro de console{': ' + ' | '.join(errs[:3]) if errs else ''}")

    finally:
        page.close()

    print(f"\n{ok_count} ok, {fail_count} falharam\n")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
