r"""Gera o macro do GiAutoSubs a partir do macro do AutoSubs.

Por que gerar em vez de editar na mao
-------------------------------------
O `autosubs-macro.setting` tem 77 KB de tabela Fusion. Editar aquilo na mao
uma vez ja e' desagradavel; refazer a cada versao nova deles e' insustentavel.
Aqui as mudancas ficam declaradas como patches - quando o macro deles mudar,
roda de novo.

O que este arquivo descobriu (e por que ele mudou tanto)
--------------------------------------------------------
O macro do AutoSubs NAO e' um Text+ passivo: ele carrega rotinas Lua em
`CustomData` que reescrevem o Text+ sozinhas. A cadeia que quebrava tudo:

    tool:SetInput("Text", ...)          <- o que o GiAutoSubs.lua faz por clipe
      -> INPS_ExecuteOnChange do controle "Text"
      -> UpdateTextContent  (linha 55: o `attempt to index a nil value` do log)
      -> ApplyWordTiming
      -> UpdateHighlight -> ApplyHighlight
           -> UpdateAllStyleColors    <- SOBRESCREVE Red2/Green2/Blue2
           -> get_current_style       <- FORCA Enabled4 = 0
           -> spline:SetKeyFrames     <- APAGA nossos keyframes por palavra

E os defaults do proprio macro sao `OutlineColorRed=0, Green=0.35, Blue=1.0`.
Isso e' azul. E' literalmente o "outline aparece azul" do relatorio: o script
escrevia preto e a rotina do macro repintava de azul meio segundo depois.

O segundo achado esta na aparencia dos elementos. O Text+ tem um input
`ElementShape{n}` ("Appearance": Text Fill / Text Outline / Border Fill /
Border Outline). `Level`, `ExtendHorizontal`, `ExtendVertical` e `Round` so
valem para as formas de BORDA. Os elementos 1..4 nascem dos presets de fabrica
(White Solid Fill / Red Outline / Black Shadow / Blue Border) - por isso a
bolha do AutoSubs no elemento 4 funciona sem ninguem tocar em `ElementShape`.
Os elementos 5..8 nascem como TEXTO. Escrever `Round6` num elemento de texto e'
aceito e ignorado: era essa a caixa que nunca aparecia.

O que muda aqui
---------------
1. Fonte padrao: "Arial Rounded MT Bold" nao existe nesta maquina e o Fusion
   reclama a cada render intermediario, enchendo o Console de ruido antes do
   nosso SetInput chegar. Trocar o DEFAULT mata o problema na origem.

2. Desarma as rotinas que competem com o script (UpdateTextContent,
   ApplyHighlight, RemoveHighlight, ToggleHighlight, UpdateHighlight,
   ApplyWordTiming). Quem cronometra palavra aqui e' o nosso pipeline; o
   cronometro do AutoSubs so tinha como discordar.

3. `UpdateAllStyleColors` reescrito: o laco original iterava
   {Fill, Outline, Shadow, Bubble} e lia `BubbleEnabled` / `BubbleColorRed`,
   que nunca existiram no macro - mandava `nil` pro Text+ a cada volta. Agora
   Fill/Outline/Shadow seguem o original e bolha/caixas saem no `ApplyGiStyle`.

4. `ApplyGiStyle`: rotina nova, dona dos elementos 4..7 (bolha, caixa do texto
   e as sombras das duas). E' ela que troca o `ElementShape` pra Border Fill.

4b. Os keyframes de EXEMPLO do spline de character-level styling sao apagados.
   Eram eles que pintavam o outline de rgb(0, 0.35, 1) caractere a caractere -
   e estilo por caractere vence tanto o Text+ quanto o Follower1, entao nao
   adiantava escrever preto em lugar nenhum. Ver MACRO.md, secao 2.

5. Grupos novos no Inspector, com seletor de cor de verdade (ColorControl, o
   mesmo padrao do FillColorRed do AutoSubs), nao tres sliders soltos:
     - Bolha        (elemento 4)
     - Caixa        (elemento 6)
     - Box Shadow   (elementos 5 e 7)

6. Aba "Style" eliminada: todo `Page = "Style"` vira `Page = "Text"`.

7. Defaults do outline: preto, espessura 0.15 - nos TRES lugares onde o Fusion
   guarda um default (o `Input` do Text+, o `INP_Default` do UserControl e o
   `Default` do InstanceInput). Patchear so um dos tres deixa o outro voltando.

8. Animacao de entrada DESLIGADA: `AnimationLevel = 0` ("Segment Level"),
   `FadeEnabled`/`PopInEnabled`/`SlideUpEnabled` = 0. Os checkboxes sozinhos nao
   bastam - o fade e' um spline (`KeyframeStretcher1Keyframes`) ligado nas
   `Opacity1..4` do Follower1, e quem le os checkboxes e' o `SetAnimations`, que
   aqui so' roda no botao Apply Style. Por isso o spline tambem e' achatado em 1
   constante, que e' o mesmo estado que o `SetAnimations` produziria com o fade
   desligado. Ver `_desligar_fade`.

Uso
---
    python gerar_macro.py            # usa o macro vendorado em giautosubs/vendor
    python gerar_macro.py --de <arquivo.setting>
"""

import argparse
import json
import os
import re
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(_RAIZ, "giautosubs", "GiAutoSubs Caption.setting")

# A VARIANTE `Fixo`: a caixa e' um RETANGULO de verdade, e nao a borda do Text+.
#
# Variante e nao opcao do macro unico, apesar de a fusao do macro 30 ter sido pelo
# caminho oposto - e as duas decisoes estao certas. O que o 30 juntou eram
# superconjuntos de CONTROLE, com custo zero pra quem nao usava. Esta muda o GRAFO
# (nove tools a mais) e cobra render por frame: um Background solido + mascara +
# Merge, tres vezes, em todo frame do clipe. Constante - nao cresce com palavra nem
# com legenda -, mas nao e' zero, e quem nao quer caixa fixa nao tem por que pagar.
#
# `gerar_macro.py --fixo` -> `GiAutoSubs Fixo.setting`.
COM_FIXO = False
VENDOR = os.path.join(_RAIZ, "giautosubs", "vendor", "autosubs-macro.setting")

# Mapa de elementos do Text+ (1 desenha na frente, 8 ao fundo).
# Precisa bater com o de giautosubs.py - os dois escrevem no mesmo Text+.
EL_FILL, EL_OUTLINE, EL_SOMBRA = 1, 2, 3
EL_BOLHA, EL_BOLHA_SOMBRA = 4, 5
EL_CAIXA, EL_CAIXA_SOMBRA = 6, 7
# A terceira cor da caixa. O efeito de "caixa de 3 cores" NAO e' tres bordas
# concentricas com Extend crescente (isso daria moldura nos quatro lados): e' a
# MESMA caixa desenhada tres vezes, deslocada em X/Y. Dai o elemento 7 - que ja'
# e' um Border Fill com cor propria e Offset - virar a segunda cor sem mudar uma
# linha, e sobrar pro 8 so' a terceira.
#
#   6 caixa base, centrada  |  7 segunda cor, deslocada  |  8 terceira cor
#
# Quem decide isso e' o ESTILO (as cores e os dois Offset), nao a estrutura: com
# o BoxLayer3 desligado o elemento 7 continua sendo a sombra de sempre.
EL_CAMADA3 = 8

FONTE_FAMILIA = "Open Sans"
FONTE_ESTILO = "Bold"

# Grupos de cor do Inspector. O AutoSubs ja usa 20..23 (UserControl) e
# 120..123 (InstanceInput); colidir junta dois seletores num widget so.
GRUPO_BOLHA, GRUPO_CAIXA, GRUPO_SOMBRA, GRUPO_PALAVRA = 24, 25, 26, 27
# 28, nao 27: o 27 ja' e' o `Word Color` do Spoken Word, e dois seletores no
# mesmo grupo viram um widget so'.
GRUPO_CAMADA3 = 28

# A terceira cor da caixa e o spin fazem parte do macro, SEMPRE.
#
# Foram variante (`--camada3` / `--spin`, cada uma num Title proprio) entre
# 05/09 e 27/09 de 2026. Medido na hora de desfazer: as quatro variantes eram
# uma cadeia de superconjuntos ESTRITOS - nenhuma tirava nada da anterior -, o
# `TikTokNovo` tinha os mesmos 99 InstanceInput do Caption (diferia em 40
# linhas, todas VALOR de Input: era um preset assado num Title), e
# `BoxSpinSpeed = 0` ja' da' a caixa parada, porque `deslocar()` cai em `pin()`.
#
# Custo de existir desligado: ZERO por frame. O elemento 8 esta' fora do fade,
# nao ha callback por controle desde o macro 11, e o custo medido deste projeto
# e' o array de estilo por caractere - nenhum numero jamais foi atribuido a
# controle publicado. O preco real e' uma linha no Inspector.
#
# O que a separacao cobrava: cinco recortes por marcador (a familia do
# `str.replace` silencioso que custou o macro 16), quatro instalacoes e
# validacoes por versao, e UM carimbo de versao para QUATRO variantes - escolher
# o Title errado era silencioso. Nada disso existe mais.


# --------------------------------------------------------------- utilidades

def _ind(texto, tabs):
    """Reindenta um bloco pra profundidade do arquivo (o .setting usa tabs)."""
    pre = "\t" * tabs
    return "\n".join(pre + ln if ln.strip() else ln
                     for ln in texto.strip("\n").split("\n"))


def _bloco(nome, sufixo=r"\{"):
    """Casa `<nome> = {` ... `}` (ou `= InstanceInput {`) fechando na MESMA
    indentacao da abertura. Sem ancorar no recuo, o `}` de um sub-bloco
    encerraria o match no meio."""
    return re.compile(r"(?ms)^(\t+)" + nome + r" = " + sufixo + r".*?^\1\},?$")


def _trocar_chunk(texto, nome, corpo, contador):
    """Troca o corpo de um `<nome> = [[ ... ]]` do CustomData.

    As rotinas do macro sao codigo Lua guardado como string. Trocar o corpo e'
    a unica forma de mudar comportamento sem reescrever o arquivo inteiro.
    """
    padrao = re.compile(r"(?ms)^(\t+)" + nome + r" = \[\[\n.*?^\1\]\],$")
    m = padrao.search(texto)
    if not m:
        contador.append(f"WARNING: routine '{nome}' not found - the macro changed shape")
        return texto
    tabs = len(m.group(1))
    novo = (m.group(1) + nome + " = [[\n" + _ind(corpo, tabs + 1) + "\n"
            + m.group(1) + "]],")
    return texto[:m.start()] + novo + texto[m.end():]


def _inserir_apos(texto, padrao, novo, contador, oque):
    """Insere logo DEPOIS do bloco casado.

    A ordem importa de verdade aqui: no Inspector do Fusion um LabelControl
    engole os `LBLC_NumInputs` controles SEGUINTES. A versao anterior enfiava
    os controles novos no topo da lista, e o "Box Shadow" acabava adotando os
    controles de texto do AutoSubs - era esse o Inspector embaralhado.
    """
    m = padrao.search(texto)
    if not m:
        contador.append(f"WARNING: could not find where to insert {oque}")
        return texto
    fim = m.end()
    trecho = m.group(0)
    virgula = "" if trecho.rstrip().endswith(",") else ","
    return texto[:fim] + virgula + "\n" + novo.rstrip("\n") + texto[fim:]


# ------------------------------------------------- rotinas Lua do CustomData

# Desarmadas: cada uma delas reescrevia, sozinha, algo que o GiAutoSubs.lua
# tinha acabado de escrever. Manter o nome (em vez de apagar a chave) mantem
# vivo o `loadstring(tool:GetData(...))` de quem as chama.
_NOOP = {
    "UpdateTextContent": (
        "return function(comp, tool, text)\n"
        "\t-- Desarmado no GiAutoSubs. O original recalculava o tempo de cada\n"
        "\t-- palavra a partir do TEXTO (chutando ~15 caracteres por segundo) e\n"
        "\t-- ainda chamava ApplyWordTiming -> UpdateHighlight. Aqui o tempo por\n"
        "\t-- palavra vem do Whisper, medido; estimar por cima disso so podia\n"
        "\t-- piorar. Era tambem a origem do `[string \"...\"]:55: attempt to\n"
        "\t-- index a nil value` que aparecia a cada execucao.\n"
        "end"),
    "ApplyWordTiming": (
        "return function(comp, tool, wordTiming)\n"
        "\t-- Desarmado: escrevia keyframes no spline de delay a partir do\n"
        "\t-- WordTiming de exemplo do macro (tres palavras ficticias).\n"
        "end"),
    "ApplyHighlight": (
        "return function(comp, tool)\n"
        "\t-- Desarmado: sobrescrevia os keyframes por palavra que o\n"
        "\t-- GiAutoSubs.lua escreve, repintava Red2/Green2/Blue2 com as cores\n"
        "\t-- do AutoSubs e forcava Enabled4 = 0 quando o estilo de destaque\n"
        "\t-- nao era \"Bubble\" - matando a bolha.\n"
        "end"),
    "RemoveHighlight": (
        "return function(comp, tool)\n"
        "\t-- Desarmado: limpava o spline e desligava o elemento 4.\n"
        "end"),
    "ToggleHighlight": (
        "return function(comp, tool)\n"
        "\t-- Desarmado junto com ApplyHighlight/RemoveHighlight.\n"
        "end"),
    "UpdateHighlight": (
        "return function(comp, tool)\n"
        "\t-- Desarmado. E' o ponto por onde ApplyHighlight era chamado de\n"
        "\t-- quatro lugares diferentes (UpdateStyleColor, ApplyWordTiming,\n"
        "\t-- SetInputValues e o botao do Inspector).\n"
        "end"),
}


# Toda linha que o macro imprime vai TAMBEM pra um arquivo.
#
# O Console do Resolve nao deixa copiar log longo - ele rola pra fora antes de
# dar pra selecionar - e as linhas por atributo sao justamente as que precisam
# ser lidas depois. `io` pode nao existir no sandbox de um callback, entao a
# escrita e' protegida por pcall e o `print` continua valendo de qualquer jeito.
#
# Append, nao truncate: um callback nao tem "inicio de rodada" pra zerar o
# arquivo.
#
# Mas "uma linha por ajuste" era otimismo: um arrasto de slider dispara o
# callback a cada valor intermediario (~40), e uma rodada de 128 legendas
# escreve o preset em cada uma. O arquivo passou de 2 MB. Dai o teto: ao
# cruzar LOG_MAXIMO ele recomeca, em vez de crescer pra sempre num arquivo que
# ninguem consegue abrir.
LOG_MACRO = r"D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_gimacro.log"
LOG_MAXIMO = 2 * 1024 * 1024

# Onde o botao "Export Config" grava os presets de legenda.
#
# Um arquivo por preset, com o nome que voce der - e' esta pasta que o
# `GiAutoSubs.lua` lista quando pergunta QUAL CONFIGURACAO usar na rodada. O
# botao que existia antes aqui ("Display Config") so' imprimia o estilo no
# Console: dava pra ler e nao dava pra usar. Exportar fecha o circulo - o que
# voce ajustou no Inspector vira a configuracao da proxima rodada sem passar
# pelo estilos.json.
PRESETS_DIR = os.path.join(_RAIZ, "giautosubs", "presets")

# A PONTE pro Python, hardcoded como o LOG_MACRO e o PRESETS_DIR acima: um
# caminho de maquina nao tem de onde ser descoberto dentro do Fusion, e um macro
# que carrega o caminho errado avisa no log em vez de falhar calado.
#
# O `.venv` e nao o python do sistema: e' o interpretador do fluxo de trabalho do
# projeto (ver o CLAUDE.md do giautosubs), e o do sistema nao tem as dependencias.
PYTHON_EXE = os.path.join(_RAIZ, ".venv", "Scripts", "python.exe")
GIAUTOSUBS_PY = os.path.join(_RAIZ, "src", "giautosubs.py")
ESTILOS_JSON = os.path.join(_RAIZ, "estilos.json")

# O recado do botao pro GiAutoSubs.lua: `chave<TAB>valor`, o mesmo formato do
# `_giescolhas.txt` e dos presets.
#
# Por que um ARQUIVO e nao um argumento: quem recria os clipes e' o
# `GiAutoSubs.lua`, e a unica forma de chama-lo de dentro do macro e' `dofile` -
# que nao passa argumento nenhum. O arquivo e' lido UMA vez e apagado, senao a
# proxima rodada manual herdaria as respostas de um clique antigo.
PEDIDO = os.path.join(_RAIZ, "giautosubs", "_gipedido.txt")

# Onde a saida do giautosubs.py e' despejada pro botao poder mostra-la no log.
#
# Arquivo em vez de pipe (`io.popen`): ler pipe na thread da interface do Resolve
# e' um dos dois suspeitos do crash do macro 28, e o redirecionamento faz o mesmo.
RELATO = os.path.join(_RAIZ, "giautosubs", "_girebuild.txt")

# ATENCAO: nada de `[[ ]]` aqui dentro. Este trecho e' colado DENTRO de um
# chunk que ja mora num `[[ ]]` do .setting - um `]]` no meio fecha a string do
# chunk mais cedo e o macro inteiro deixa de compilar. Por isso o caminho vai
# entre aspas, com as barras invertidas dobradas.
#
# `gi_chunk` mora aqui junto porque toda rotina precisa das duas coisas.
#
# O QUE ELE CONSERTA (custou o "Apply Style: nothing was applied"): o codigo do
# macro mora no `CustomData` do MacroOperator, e os controles moram no Text+ de
# dentro (`Template`). Sao tools DIFERENTES. O `tool` que o Fusion entrega pro
# `BTNCS_Execute` de um botao do Inspector e' o Text+ - entao
# `tool:GetData("SetInputValues")` volta nil, sempre, e o botao imprimia "nothing
# was applied" sem nunca ter chance de aplicar. Procurar na comp inteira e' o que
# faz uma rotina ser encontrada venha a chamada de onde vier.
_LOG_LUA = r"""
	local function diga(linha)
		print(linha)
		pcall(function()
			local fh = io.open("__LOG__", "a")
			if not fh then return end
			-- `seek("end")` devolve o tamanho sem uma segunda abertura: no
			-- caminho normal isto continua sendo UM open por linha.
			if fh:seek("end") > __LOG_MAXIMO__ then
				fh:close()
				fh = io.open("__LOG__", "w")
				if not fh then return end
				fh:write("-- log restarted (it had passed __LOG_MAXIMO__ bytes) --\n")
			end
			fh:write(linha, "\n")
			fh:close()
		end)
	end

	local function gi_dono(comp, tool, nome)
		local v
		pcall(function() v = tool and tool:GetData(nome) end)
		if v ~= nil then return tool end
		local c = comp
		if c == nil and tool then pcall(function() c = tool.Comp end) end
		local tools
		pcall(function() tools = c:GetToolList(false) end)
		for _, t in pairs(tools or {}) do
			pcall(function() v = t:GetData(nome) end)
			if v ~= nil then return t end
		end
		return nil
	end

	local function gi_chunk(comp, tool, nome)
		local d = gi_dono(comp, tool, nome)
		if not d then return nil end
		local v
		pcall(function() v = d:GetData(nome) end)
		return v
	end

	-- O MacroOperator, achado pelo que ele E' (o dono do `InputKeys`) e nao pelo
	-- nome - o nome do macro muda de clipe pra clipe.
	--
	-- Para que ele serve na LEITURA: o Inspector de um clipe edita os
	-- `InstanceInput` do MACRO, nao os UserControls do Text+. Ler o valor so' do
	-- Text+ devolve o valor VELHO de qualquer controle que o Fusion nao tenha
	-- propagado - e o sintoma e' exatamente "clico em Apply Style e ESTE atributo
	-- nao muda", com `0 written` no log enquanto os vizinhos mudam.
	local function gi_macro(comp, tool)
		return gi_dono(comp, tool, "InputKeys")
	end
"""


# Fill/Outline/Shadow continuam como no AutoSubs. O que sai e' a volta do laco
# para "Bubble": ela lia `BubbleEnabled` e `BubbleColorRed`, controles que o
# macro nunca teve, e escrevia nil em Enabled4/Red4/Green4/Blue4.
_UPDATE_ALL = """
return function(comp, tool, origem, spline)
	local template, follower = comp:FindTool("Template"), comp:FindTool("Follower1")
	origem = origem or "script"
__LOG_LUA__

	-- Le na ordem macro -> tool -> Text+. O macro primeiro porque e' onde o
	-- Inspector do clipe grava (ver `gi_macro`); os outros dois porque nem todo
	-- controle esta exposto la.
	local macro = gi_macro(comp, tool)
	local function ctl(nome)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil then return v end
			end
		end
		return nil
	end

	-- Mesma economia do ApplyGiStyle: nao reescrever o que ja esta certo.
	local escritos, iguais = 0, 0
	local function pin(chave, valor)
		if valor == nil then return end
		for _, alvo in ipairs({ template, follower }) do
			if alvo then
				local atual
				pcall(function() atual = alvo:GetInput(chave) end)
				local mesmo = (atual ~= nil) and (type(atual) == type(valor))
					and ((type(valor) == "number" and math.abs(atual - valor) < 1e-6)
						or (type(valor) ~= "number" and type(valor) ~= "table"
							and atual == valor))
				if mesmo then
					iguais = iguais + 1
				else
					pcall(function() alvo:SetInput(chave, valor) end)
					escritos = escritos + 1
				end
			end
		end
	end

	for _, par in ipairs({ { "Fill", "1" }, { "Outline", "2" }, { "Shadow", "3" } }) do
		local tipo, id = par[1], par[2]
		pin("Enabled" .. id, ctl(tipo .. "Enabled"))
		pin("Red" .. id, ctl(tipo .. "ColorRed"))
		pin("Green" .. id, ctl(tipo .. "ColorGreen"))
		pin("Blue" .. id, ctl(tipo .. "ColorBlue"))
		if tipo == "Outline" then
			pin("Thickness" .. id, ctl("OutlineThickness"))
		end
	end

	diga(string.format("[GiAutoSubs] fill/outline/shadow -> UpdateAllStyleColors: "
		.. "%d written, %d already ok", escritos, iguais))

	-- bolha, caixa e as sombras das duas moram no ApplyGiStyle. `origem` vem de
	-- quem chamou (o nome do controle mexido, ou "script"): e' ela que decide se
	-- o spline precisa ser refeito. Chegando "script", refaz por seguranca -
	-- dali nao da' pra saber QUAL controle disparou, e fill/outline/shadow podem
	-- ser camadas animadas.
	local f = gi_chunk(comp, tool, "ApplyGiStyle")
	if f then
		loadstring(f)()(comp, tool, origem, spline)
	else
		diga("[GiAutoSubs] UpdateAllStyleColors: ApplyGiStyle not found - "
			.. "bubble and boxes were not applied")
	end
end
"""


_UPDATE_ONE = """
return function(comp, tool, type)
__LOG_LUA__
	-- O original terminava chamando UpdateHighlight, que repintava tudo de
	-- novo a partir de outros controles. Um clique em "Update Fill Color"
	-- mexia no outline. Aqui cada botao mexe no que diz que mexe.
	local f = gi_chunk(comp, tool, "UpdateAllStyleColors")
	if f then loadstring(f)()(comp, tool, type or "script") end
end
"""


# O par do AutoSubs, com o schema apontando pra NOSSA lista de controles.
#
# `GetInputValues` le o estilo do clipe como uma tabela OPACA: quem recebe nao
# precisa saber o que tem dentro, porque o schema (`InputKeys`) mora aqui no
# macro. E' o que faz um controle novo deixar de exigir codigo novo do lado do
# script - basta ele entrar naquela lista.
#
# O original nao protegia contra `InputKeys` ausente (`ipairs(nil)` levanta) nem
# contra input que ainda nao existe. Um elemento desligado nao materializa os
# inputs dele (MACRO.md 3.1), entao ler `Red6` com o 6 apagado devolve nil - e
# guardar nil e' guardar uma chave que some da tabela sem ninguem notar.
_GET_INPUTS = """
return function(tool)
__LOG_LUA__
	local keys = gi_chunk(nil, tool, "InputKeys") or {}
	local settings = {}
	for _, key in ipairs(keys) do
		local v
		pcall(function() v = tool:GetInput(key) end)
		if v ~= nil then settings[key] = v end
	end
	return settings
end
"""


# O UNICO caminho de escrita do estilo.
#
# Antes cada um dos controles novos chamava o ApplyGiStyle direto, e os do
# AutoSubs chamavam UpdateAllStyleColors ou SetAnimations - tres portas de
# entrada pra mesma coisa, cada uma com a sua chance de "esse controle nao surte
# efeito". Agora todas passam por aqui.
#
# `settings` nil quer dizer "nao mudou valor nenhum, so refaz o que deriva
# deles": e' o caso do callback de um controle do Inspector, que ja gravou o
# proprio valor antes de disparar.
_SET_INPUTS = """
return function(comp, tool, settings, origem, spline)
__LOG_LUA__

	-- Escreve no tool E no macro.
	--
	-- Sao dois lugares com o mesmo valor: o UserControl do Text+ e o
	-- `InstanceInput` do MacroOperator que aponta pra ele. O Inspector do clipe
	-- edita o segundo, o script escrevia so' no primeiro - e quem le tinha que
	-- adivinhar qual dos dois estava em dia. Escrever nos dois acaba com a
	-- pergunta; a comparacao abaixo garante que isso nao custa escrita nenhuma
	-- quando ja estao iguais.
	local macro = gi_macro(comp, tool)
	local alvos = { tool }
	if macro and macro ~= tool then alvos[#alvos + 1] = macro end

	-- Mesma economia das outras rotinas: reescrever um input com o valor que
	-- ele ja tem custa o mesmo que mudar de verdade (invalida o cache e
	-- re-renderiza). Ver MACRO.md, secao 6.
	local escritos, iguais = 0, 0
	for key, value in pairs(settings or {}) do
		for _, alvo in ipairs(alvos) do
			local atual
			pcall(function() atual = alvo:GetInput(key) end)
			local mesmo = (atual ~= nil) and (type(atual) == type(value))
				and ((type(value) == "number" and math.abs(atual - value) < 1e-6)
					or (type(value) ~= "number" and type(value) ~= "table"
						and atual == value))
			if mesmo then
				iguais = iguais + 1
			else
				pcall(function() alvo:SetInput(key, value) end)
				escritos = escritos + 1
			end
		end
	end

	local function chamar(nome, ...)
		local f = gi_chunk(comp, tool, nome)
		if not f then
			diga("[GiAutoSubs] SetInputValues: " .. nome .. " not found on this "
				.. "tool - that half of the style was NOT applied")
			return
		end
		local ok, erro = pcall(loadstring(f)(), ...)
		if not ok then
			diga("[GiAutoSubs] SetInputValues: " .. nome .. " FAILED: "
				.. tostring(erro))
		end
	end

	-- Duas origens, so' duas: o BOTAO Apply Style e o script.
	--
	-- Aqui existiam duas tabelas (ANIMACAO, ESTILO_BASE) que roteavam cada
	-- controle pra rotina que ele alcanca. Elas serviam ao Inspector reagindo
	-- controle a controle - ~40 disparos por arrasto de slider, cada um pagando
	-- so' o pedaco dele. Sem os callbacks isso deixou de existir: aplicar e' um
	-- clique consciente, uma vez, e o barato e' fazer TUDO sem perguntar de onde
	-- veio.
	--
	-- SetAnimations so' no botao: ele reescreve os keyframes de animacao do
	-- AutoSubs, e rodar isso nas 128 legendas de uma rodada do script seria
	-- estrear um comportamento novo no meio do caminho.
	if origem == "button" then
		chamar("SetAnimations", comp, tool)
	end
	-- UpdateAllStyleColors cuida dos elementos 1..3 e termina chamando o
	-- ApplyGiStyle, dono dos 4..7.
	chamar("UpdateAllStyleColors", comp, tool, origem or "script", spline)

	diga(string.format("[GiAutoSubs] %s -> SetInputValues: %d written, "
		.. "%d already ok (%d keys)", tostring(origem or "script"),
		escritos, iguais, escritos + iguais))
	return escritos
end
"""


# A rotina nova. E' a unica dona dos elementos 4..7 - o Inspector inteiro passa
# por aqui, entao um checkbox que "nao surte efeito" deixa de ser possivel:
# nao ha um segundo caminho onde ele pudesse se perder.
_APPLY_GI = """
return function(comp, tool, origem, spline, soCaixa)
	local template = comp:FindTool("Template") or tool
	if not template then return end
	origem = origem or "script"
__LOG_LUA__

	-- macro primeiro: e' onde o Inspector do clipe grava (ver `gi_macro`).
	local macro = gi_macro(comp, tool)
	local function ctl(nome, padrao)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil then return v end
			end
		end
		return padrao
	end

	local escritos, iguais = 0, 0

	-- Escreve nos DOIS tools.
	--
	-- O Follower1 gera o StyledText que o Text+ consome, e os inputs de
	-- elemento que ele tem sobrescrevem os do Text+. Escrever so no Template
	-- era o motivo de mexer na cor da bolha no Inspector nao mudar nada na
	-- tela. E' a mesma razao de o UpdateStyleColor do AutoSubs fazer
	-- `template:SetInput(...)` seguido de `follower:SetInput(...)`.
	--
	-- `Opacity` dos elementos 1..4 fica FORA do Follower: la elas estao
	-- conectadas ao AnimationKeyframeStretcher, e trocar a conexao por um
	-- numero mata o fade sem dar erro. Da' 5 em diante nao ha conexao.
	local follower = comp:FindTool("Follower1")

	-- Reescrever um input com o valor que ele JA tem custa o mesmo que mudar
	-- de verdade: o Fusion invalida o cache e re-renderiza. Um arrastar de
	-- slider dispara este callback a cada valor intermediario, e em cada
	-- disparo UM input mudou - os outros ~80 eram reafirmacao. Comparar antes
	-- e' o que tira o grosso da espera.
	local function igual(atual, valor)
		if type(atual) ~= type(valor) then return false end
		if type(valor) == "number" then return math.abs(atual - valor) < 1e-6 end
		if type(valor) == "table" then return false end   -- Offset e afins
		return atual == valor
	end

	local function um(alvo, chave, valor)
		if not alvo then return end
		local atual
		pcall(function() atual = alvo:GetInput(chave) end)
		if atual ~= nil and igual(atual, valor) then
			iguais = iguais + 1
			return
		end
		pcall(function() alvo:SetInput(chave, valor) end)
		escritos = escritos + 1
	end

	-- A opacidade dos elementos 1..4 chega no Follower1 CONECTADA ao
	-- `AnimationKeyframeStretcher` - e' assim que o fade do AutoSubs e' feito. E
	-- o Follower vence o Text+. Era exatamente por isso que `BubbleOpacity` nao
	-- mudava nada na tela: o valor era escrito no Text+ e ignorado.
	--
	-- Para a bolha valer, a conexao tem que sair. O jeito de fazer isso e' o
	-- mesmo do `RemoveFade` do AutoSubs: `follower.Opacity4 = nil` e so' entao
	-- `SetInput`. Escrever sem desconectar e' aceito e ignorado.
	--
	-- So' a bolha. Nos elementos 1..3 essa conexao E' o fade do texto, e trocar
	-- por um numero mataria o fade sem dizer nada.
	local stretcher = comp:FindTool("AnimationKeyframeStretcher")
	local chave_bolha = "Opacity" .. __EL_BOLHA__
	local function opacidade_da_bolha(valor)
		if not follower then return end
		if valor >= 1 then
			-- 1 = "sem opacidade propria": devolve a bolha pro fade, se ele
			-- estiver la. Sem isto, mexer no slider e voltar pra 1 deixaria a
			-- bolha fora do fade pra sempre.
			if stretcher then
				pcall(function() follower[chave_bolha] = stretcher.Result end)
				return
			end
		end
		pcall(function() follower[chave_bolha] = nil end)
		um(follower, chave_bolha, valor)
	end

	local function pin(n, chave, valor)
		if valor == nil then return end
		um(template, chave .. n, valor)
		if not follower then return end
		if chave == "Opacity" and n <= 4 then
			if n == __EL_BOLHA__ then opacidade_da_bolha(valor) end
			return
		end
		um(follower, chave .. n, valor)
	end

	-- 2 = "Border Fill" (0 Text Fill, 1 Text Outline, 2 Border Fill,
	-- 3 Border Outline). Lido do dump dentro do Resolve: o elemento 1
	-- ("White Solid Fill") da' 0 e o 2 ("Red Outline") da' 1. O elemento 4
	-- nasce em 3, que e' so o CONTORNO do retangulo - nao serve pra bolha.
	local BORDA = 2

	-- O SPIN: as duas cores extras ORBITANDO o texto em vez de paradas.
	--
	-- Gira o DESLOCAMENTO, nao a geometria. Rotacionar o retangulo deixaria a
	-- caixa base reta e as coloridas em losango por tras dela - canto em angulo
	-- aleatorio le como defeito, nao como estilo. Com as tres caixas alinhadas e
	-- o vetor de offset percorrendo um circulo, a borda colorida orbita o texto:
	-- e' o efeito parado de hoje, animado.
	--
	-- Raio e fase saem do offset que o usuario JA ajustou no Inspector - o par
	-- (x,y) e' um vetor, tem os dois dentro. Por isso isto acrescenta UM
	-- controle so', e `BoxSpinSpeed = 0` da' exatamente a caixa parada de hoje.
	--
	-- Os 180 graus entre a segunda e a terceira cor vem de graca: os dois
	-- offsets ja' nascem em lados OPOSTOS, entao meia volta E' as duas cores
	-- trocando de lado.
	--
	-- `time` e' da COMPOSICAO, entao cada legenda comeca numa fase diferente.
	-- E' de proposito: todas girando em unissono viraria metronomo.
	local function expressao_spin(x, y)
		local raio = math.sqrt(x * x + y * y)
		-- Offset zerado nao tem direcao pra girar, e a expressao viraria um
		-- ponto parado na origem - as tres cores empilhadas, sem efeito nenhum.
		if raio < 1e-9 then return nil end
		local fase = math.deg(math.atan2(y, x))
		return string.format(
			"Point(%.6f*cos((Template.BoxSpinSpeed*time+%.4f)*pi/180),"
			.. "%.6f*sin((Template.BoxSpinSpeed*time+%.4f)*pi/180))",
			raio, fase, raio, fase)
	end

	-- Escrever NUMERO num input que carrega expressao e' a mesma armadilha do
	-- `SourceOp`: aceito e ignorado, ou pior, a conexao cai sem erro. Por isso a
	-- expressao sai ANTES, sempre - e' o que faz desligar o spin devolver a
	-- caixa pro lugar em vez de deixa-la girando pra sempre.
	--
	-- Nos DOIS tools: o Follower1 vence o Text+ nos inputs de elemento, e uma
	-- expressao so' no Template teria o sintoma classico de "aceita e nao muda
	-- nada na tela".
	local function deslocar(n, x, y)
		local chave = "Offset" .. n
		local expr = (ctl("BoxSpinSpeed", 0) ~= 0) and expressao_spin(x, y) or nil
		for _, alvo in ipairs({ template, follower }) do
			if alvo then
				pcall(function() alvo[chave]:SetExpression(nil) end)
			end
		end
		if not expr then
			pin(n, "Offset", { x, y })
			return
		end
		for _, alvo in ipairs({ template, follower }) do
			if alvo then
				pcall(function() alvo[chave]:SetExpression(expr) end)
				escritos = escritos + 1
			end
		end
	end

	-- CAIXA FIXA: a largura deixa de depender do texto.
	--
	-- O Text+ nao tem largura fixa - toda caixa em forma de BORDA acompanha a
	-- extensao do texto no `Level` escolhido, e nao existe input pra desligar
	-- isso. Entao largura fixa aqui e' COMPENSACAO: a caixa desenha sempre o
	-- que uma linha CHEIA desenharia, e o que falta pra chegar la' entra nos
	-- dois lados do `Extend Horizontal`. O tamanho na tela continua sendo dado
	-- por `Size` + `Extend Horizontal` + `Extend Vertical`, como sem a opcao -
	-- o que sai da conta e' o comprimento do texto.
	--
	-- "Linha cheia" e' o `Characters per Box` da aba Meta, o MESMO numero que
	-- reparte as legendas (`quebra.max_chars` do giautosubs.py). Por isso a
	-- caixa fixa e a aba Meta sao um trabalho so': mudar os caracteres por caixa
	-- muda a largura da caixa junto, sem um segundo numero pra manter em dia.
	--
	-- `MetaCharWidth` e' quanto UM caractere vale na unidade do Extend. Ele e'
	-- um controle calibravel, e nao uma constante no codigo, porque a unidade do
	-- Extend e' relativa ao tamanho da fonte e nao ha como medi-la de fora do
	-- Resolve (licenca nao-Studio): um numero errado escondido no gerador seria
	-- um numero que ninguem consegue corrigir sem reinstalar o macro.
	local function utf8_len(s)
		-- Lua 5.1 nao tem `utf8.len` e `#s` conta BYTE: com acento a linha
		-- pareceria mais larga do que e' e a caixa encolheria sozinha. Contar
		-- os bytes que NAO sao continuacao (10xxxxxx) da' o numero de
		-- caracteres - a mesma regua que o `max_chars` usa no Python.
		local _, n = tostring(s):gsub("[^\\128-\\191]", "")
		return n
	end

	-- A linha mais larga, nao o texto todo: a caixa envolve a LINHA (Level 1),
	-- e com duas linhas o comprimento somado nao diz nada sobre a largura.
	--
	-- `GiTextOriginal` primeiro porque e' o texto antes do `Case`, que e' o que
	-- o `GiApplyText` mantem em dia; ele tem o mesmo comprimento do que esta na
	-- tela. Os dois inputs sao reserva pro clipe arrastado da aba Effects, que
	-- nunca passou pelo script e nao tem esse dado.
	local function linha_mais_larga()
		local texto = template:GetData("GiTextOriginal")
		if texto == nil then
			pcall(function() texto = template:GetInput("StyledText") end)
		end
		if texto == nil then
			pcall(function() texto = template:GetInput("Text") end)
		end
		local maior = 0
		for linha in tostring(texto or ""):gmatch("[^\\r\\n]+") do
			local n = utf8_len(linha)
			if n > maior then maior = n end
		end
		return maior
	end

	-- Quantos PIXELS vale uma unidade de Extend.
	--
	-- Uma unidade de Extend e' a altura da fonte, e o `Size` do Text+ e' fracao da
	-- ALTURA do frame - entao a conversao precisa da resolucao do comp. Num efeito
	-- de Edit page o comp herda a resolucao da timeline.
	--
	-- Devolve nil quando nao da' pra saber: e' o que faz a caixa fixa cair no alvo
	-- por caracteres em vez de inventar uma escala.
	local function px_por_unidade()
		-- O CONTROLE vence a estimativa.
		--
		-- `Px per Unit` (aba Meta) existe porque o fator abaixo e' palpite: a FORMA
		-- da conta e' certa (uma unidade de Extend e' a altura da fonte, e `Size` e'
		-- fracao da altura do frame), mas so' quem ve a tela sabe se o numero
		-- bate - este projeto nao tem licenca Studio pra medir de fora.
		--
		-- Errar num controle se corrige em dois segundos; errar no gerador custa
		-- reinstalar o macro, reiniciar o Resolve e trocar o Title do Media Pool.
		local manual = tonumber(ctl("MetaPxPorUnidade", 0)) or 0
		if manual > 0 then return manual end

		local size, altura
		pcall(function() size = template:GetInput("Size") end)
		pcall(function() altura = comp:GetPrefs("Comp.FrameFormat.Height") end)
		size = tonumber(size)
		altura = tonumber(altura)
		if not size or not altura or size <= 0 or altura <= 0 then return nil end
		-- 0.578 e' MEDIDO, nao deduzido: em 27/09/2026 o usuario pediu uma caixa de
		-- 346px de altura e saiu 200px com a escala `Size` x altura. A altura de uma
		-- unidade de Extend nao e' o `Size` cheio - e' a altura do OLHO da fonte,
		-- que e' uma fracao dele, e essa fracao depende da fonte.
		--
		-- Por isso o `Px per Unit` continua vencendo: outra fonte, outro numero.
		return size * altura * 0.578
	end

	-- A largura do texto desta legenda, em EM.
	--
	-- `GiTextEm` e' MEDIDO na fonte de verdade pelo giautosubs.py (Pillow) e
	-- carimbado no clipe. E' ele que faz a caixa fixa sair do MESMO tamanho em toda
	-- legenda: a folga e' o que falta pro alvo, e com a largura certa a soma fecha
	-- sempre no alvo. O palpite errava por muito - `19 x 0.5 = 9.5 em` contra
	-- `10.61 em` medidos numa legenda de 19 caracteres.
	--
	-- Sem o carimbo (clipe arrastado da aba Effects, ou criado antes do macro 34)
	-- cai no palpite `caracteres x Char Width`, avisando UMA vez: e' ele que faz as
	-- caixas sairem de tamanhos diferentes, e o usuario precisa poder ligar o
	-- sintoma a' causa.
	local function largura_do_texto(em_por_char, chars)
		local medido
		pcall(function() medido = tonumber(template:GetData("GiTextEm")) end)
		if medido and medido > 0 then return medido, true end
		if not _G.GI_SEM_MEDIDA_AVISADO then
			_G.GI_SEM_MEDIDA_AVISADO = true
			diga("[GiAutoSubs] Fixed Box: this clip has no measured text width "
				.. "(GiTextEm), so the box falls back to guessing "
				.. "characters x Char Width - captions with different text will "
				.. "come out with DIFFERENT widths. Recreate the captions with the "
				.. "script to get the measured value.")
		end
		return chars * em_por_char, false
	end

	local function extend_h(prefixo)
		local base = ctl(prefixo .. "ExtendHorizontal", 0)
		-- So' a caixa do TEXTO. A bolha abraca a palavra falada - e' a graca
		-- dela - e a sombra e a camada 3 COPIAM a geometria da caixa base
		-- (invariante do macro 23), entao elas ficam fixas junto, sem controle
		-- proprio e sem chance de desalinhar.
		if prefixo ~= "TextBox" or ctl("TextBoxFixed", 0) ~= 1 then return base end
		local em = ctl("MetaCharWidth", 0)
		local maior = linha_mais_larga()

		-- WIDTH EM PIXELS, quando voce deu um. E' o alvo mais direto que existe: o
		-- tamanho na tela, sem passar por contagem de caractere.
		--
		-- Zero quer dizer "nao pedi largura": ai vale o alvo por CARACTERES (uma
		-- linha cheia de `Characters per Box`), que e' o que o macro 25 fazia. Os
		-- dois convivem de proposito - quem nao quer pensar em pixel nao precisa.
		-- DAQUI PRA BAIXO o `base` (o valor do Extend) nao aparece mais: com a caixa
		-- fixa, o controle `Extend Horizontal` esta' DESLIGADO, e usa-lo em qualquer
		-- ramo faria o tamanho da caixa mudar conforme um slider que o rotulo diz
		-- que nao vale. O unico `return base` que sobra e' o de la' de cima, quando
		-- a caixa NAO e' fixa.
		local largura_px = tonumber(ctl(prefixo .. "Width", 0)) or 0
		if largura_px > 0 and maior > 0 then
			local escala = px_por_unidade()
			if escala then
				local alvo_unidades = largura_px / escala
				local texto_unidades = largura_do_texto(em, maior)
				local falta = alvo_unidades - texto_unidades
				-- Legenda MAIS larga que o alvo: sem folga (zero), e nao a folga do
				-- Extend. Ela nao encolhe - caixa menor que o proprio texto seria
				-- pior que caixa que vaza - mas tambem nao volta a obedecer o
				-- controle desligado.
				if falta <= 0 then return 0 end
				return falta / 2
			end
			diga("[GiAutoSubs] Fixed Box: Width is in pixels, but the font Size or "
				.. "the comp resolution could not be read - falling back to the "
				.. "Characters per Box target")
		end

		-- Sem `Width`, o alvo e' uma linha CHEIA de `Characters per Box`. Aqui o
		-- palpite e' inevitavel dos dois lados (o alvo tambem e' em caracteres),
		-- entao ele e' coerente: a mesma regua mede o alvo e o texto.
		local alvo = ctl("MetaCharsPerBox", 0)
		if alvo <= 0 or em <= 0 or maior <= 0 then
			diga("[GiAutoSubs] Fixed Box is on but there is nothing to measure "
				.. "against (Width 0, Characters per Box " .. tostring(alvo)
				.. ", Char Width " .. tostring(em) .. ", widest line "
				.. tostring(maior) .. ") - the box gets NO padding. Set Width (px) "
				.. "or Characters per Box.")
			return 0
		end
		-- Legenda MAIS larga que o alvo nao encolhe. Caixa que vaza da tela e' o
		-- sintoma de `max_chars` alto demais, e a unica coisa pior que o sintoma
		-- seria esconde-lo: encolhendo aqui, a legenda larga ficaria com a caixa
		-- menor que o proprio texto.
		local falta = alvo - maior
		if falta <= 0 then return 0 end
		-- Sem o `base`: a largura da caixa fixa e' o alvo, e so'. Somar o Extend
		-- aqui era o que fazia a caixa "fixa" mudar de tamanho junto com um slider
		-- desligado.
		return falta * em / 2
	end

	-- A ALTURA da caixa fixa, em pixels. Mesma conta da largura, com uma diferenca:
	-- a altura do texto nao depende do texto - uma linha e' UMA unidade de Extend.
	-- Por isso ela nao precisa medir nada, e por isso a caixa nunca "pula" de
	-- altura de legenda pra legenda.
	--
	-- Com duas linhas (`Lines` = 2) a altura do texto sao duas unidades; o numero
	-- vem da aba Meta, que e' quem sabe com quantas linhas as legendas foram
	-- repartidas.
	local function extend_v(prefixo)
		local base = ctl(prefixo .. "ExtendVertical", 0)
		-- Caixa livre: manda o Extend, como sempre.
		if prefixo ~= "TextBox" or ctl("TextBoxFixed", 0) ~= 1 then return base end

		-- Caixa FIXA: o Extend Vertical esta' desligado. Sem `Height` nao ha alvo, e
		-- a resposta e' ZERO (a caixa abraca o texto) e nao o valor do controle -
		-- senao "desligado" seria mentira, e a altura mudaria com um slider que o
		-- rotulo diz que nao vale. O log pede o numero que falta.
		local altura_px = tonumber(ctl(prefixo .. "Height", 0)) or 0
		if altura_px <= 0 then
			diga("[GiAutoSubs] Fixed Box is on and Height (px) is 0 - the box gets "
				.. "no vertical padding (Extend Vertical does not apply to a fixed "
				.. "box). Set Height (px).")
			return 0
		end
		local escala = px_por_unidade()
		if not escala then
			diga("[GiAutoSubs] Fixed Box: Height is in pixels, but the font Size or "
				.. "the comp resolution could not be read - no vertical padding")
			return 0
		end
		local linhas = math.max(1, math.floor(tonumber(ctl("MetaLines", 1)) or 1))
		local falta = (altura_px / escala) - linhas
		if falta <= 0 then return 0 end
		return falta / 2
	end

	-- DESABILITAR o Extend na interface quando a caixa e' fixa.
	--
	-- Os macros de FABRICA nao fazem isso declarativamente (nenhum `IC_Visible` nem
	-- `INP_Disabled` nos 417 `.setting` do Templates.drfx; os que tem UI reativa
	-- usam `INPS_ExecuteOnChange`, 44 vezes). Entao o caminho e' `SetAttrs` em
	-- tempo de execucao, daqui - que e' chamado tambem pelo callback do preview, e
	-- portanto no instante em que voce marca o checkbox.
	--
	-- No MACRO e no Text+: o Inspector do clipe mostra os `InstanceInput` do
	-- MacroOperator, mas o UserControl vive no Text+ - e qual dos dois manda no
	-- atributo nao esta' documentado. Escrever nos dois custa duas chamadas.
	--
	-- LE DE VOLTA e diz no log, uma vez por sessao: isto nao da' pra testar fora do
	-- Resolve, e um "desabilita" que nao desabilita e' pior que nao tentar - o
	-- usuario precisa saber qual dos dois aconteceu.
	local function ui_extend(fixa)
		local alvos = {}
		if macro then alvos[#alvos + 1] = macro end
		if template and template ~= macro then alvos[#alvos + 1] = template end
		local colou = nil
		for _, alvo in ipairs(alvos) do
			for _, chave in ipairs({ "TextBoxExtendHorizontal",
				"TextBoxExtendVertical" }) do
				pcall(function()
					alvo[chave]:SetAttrs({ INP_Disabled = fixa, IC_Visible = not fixa })
				end)
				pcall(function()
					local at = alvo[chave]:GetAttrs()
					if at ~= nil then
						colou = (at.INP_Disabled == fixa) or (at.IC_Visible == (not fixa))
					end
				end)
			end
		end
		if colou ~= nil and not _G.GI_UI_AVISADO then
			_G.GI_UI_AVISADO = true
			if colou then
				diga("[GiAutoSubs] Extend Horizontal/Vertical greyed out in the "
					.. "Inspector while Fixed Box is on (SetAttrs works here).")
			else
				diga("[GiAutoSubs] NOTE: this Fusion build ignores SetAttrs on a "
					.. "macro input, so Extend Horizontal/Vertical stay clickable "
					.. "while Fixed Box is on. They have NO effect - the label says "
					.. "'(free box)' for that reason.")
			end
		end
	end

	local function caixa(n, prefixo, ligada)
		-- MODO SO'-A-CAIXA: e' o preview do slider (`Width`/`Height`/`Fixed Box`).
		-- Escreve os dois Extend e mais nada - nem Enabled, nem cor, nem forma.
		-- Custa 12 escritas no pior caso e ZERO por frame, o que e' o que permite
		-- ele rodar a cada valor intermediario de um arrasto.
		if soCaixa then
			if not ligada then return end
			if not (n == __EL_BOLHA__ and ctl("BubblePopEnabled", 0) == 1) then
				pin(n, "ExtendHorizontal", extend_h(prefixo))
				pin(n, "ExtendVertical", extend_v(prefixo))
			end
			return
		end
		pin(n, "Enabled", ligada and 1 or 0)
		if not ligada then return end
		-- ElementShape ANTES da geometria: Level/Extend/Round so existem pra
		-- forma de borda. Na ordem trocada o Text+ aceita e descarta.
		pin(n, "ElementShape", BORDA)
		pin(n, "Red", ctl(prefixo .. "ColorRed", 0))
		pin(n, "Green", ctl(prefixo .. "ColorGreen", 0))
		pin(n, "Blue", ctl(prefixo .. "ColorBlue", 0))
		pin(n, "Opacity", ctl(prefixo .. "Opacity", 1))
		pin(n, "Level", ctl(prefixo .. "Level", 2))
		-- Com o "pop" ligado, quem manda nos dois Extend da BOLHA e' um spline
		-- de keyframes (o `GiRebuildHighlight` monta), e escrever um numero num
		-- input conectado e' aceito e ignorado - ou pior, derruba a conexao.
		if not (n == __EL_BOLHA__ and ctl("BubblePopEnabled", 0) == 1) then
			pin(n, "ExtendHorizontal", extend_h(prefixo))
			pin(n, "ExtendVertical", extend_v(prefixo))
		end
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
	end

	-- A sombra copia a GEOMETRIA da caixa e muda so cor, opacidade, borrao e
	-- deslocamento. Sombra de tamanho diferente entrega que sao dois
	-- elementos empilhados em vez de uma caixa com sombra.
	local function sombra(n, prefixo, ligada)
		if soCaixa then
			if not ligada then return end
			pin(n, "ExtendHorizontal", extend_h(prefixo))
			pin(n, "ExtendVertical", extend_v(prefixo))
			return
		end
		pin(n, "Enabled", ligada and 1 or 0)
		if not ligada then return end
		pin(n, "ElementShape", BORDA)
		pin(n, "Red", ctl("BoxShadowColorRed", 0))
		pin(n, "Green", ctl("BoxShadowColorGreen", 0))
		pin(n, "Blue", ctl("BoxShadowColorBlue", 0))
		pin(n, "Opacity", ctl("BoxShadowOpacity", 0.55))
		pin(n, "Softness", ctl("BoxShadowSoftness", 2))
		pin(n, "Level", ctl(prefixo .. "Level", 2))
		pin(n, "ExtendHorizontal", extend_h(prefixo))
		pin(n, "ExtendVertical", extend_v(prefixo))
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
		-- Offset, nao Position: Position e' coordenada ABSOLUTA e joga o
		-- elemento pro canto da tela.
		-- So' a caixa do TEXTO orbita. O elemento __EL_BOLHA_SOMBRA__ e' a
		-- sombra da BOLHA, que acompanha a palavra falada e vive um instante -
		-- girar junto seria ruido, nao efeito.
		if n == __EL_CAIXA_SOMBRA__ then
			deslocar(n, ctl("BoxShadowCenterX", 0.005),
				ctl("BoxShadowCenterY", -0.007))
		else
			pin(n, "Offset", { ctl("BoxShadowCenterX", 0.005),
				ctl("BoxShadowCenterY", -0.007) })
		end
	end

	-- A TERCEIRA cor da caixa (elemento 8). Mesma forma da `sombra` acima, e de
	-- proposito: as tres camadas so' podem diferir em COR e em OFFSET. Se o
	-- Level, os dois Extend ou o Round divergirem, o deslocamento deixa de ser
	-- limpo e o que se ve e' um contorno torto - por isso a geometria e' COPIADA
	-- do prefixo da caixa base em vez de ter controle proprio.
	--
	-- Transparencia vai por `Alpha`, nao por `Opacity`: o fade do AutoSubs mora
	-- em `Opacity1..4` do Follower1 (conectadas ao AnimationKeyframeStretcher), e
	-- os elementos 5..8 nao estao nele. Escrever `Opacity8` aqui nao ligaria a
	-- camada no fade - so' gastaria o input que sobraria pra isso um dia.
	local function camada3(n, prefixo, ligada)
		if soCaixa then
			if not ligada then return end
			pin(n, "ExtendHorizontal", extend_h(prefixo))
			pin(n, "ExtendVertical", extend_v(prefixo))
			return
		end
		pin(n, "Enabled", ligada and 1 or 0)
		if not ligada then return end
		-- Os elementos 5..8 nascem em forma de TEXTO. Sem esta linha o Text+
		-- aceita Level/Extend/Round e nao desenha caixa nenhuma.
		pin(n, "ElementShape", BORDA)
		pin(n, "Red", ctl("BoxLayer3ColorRed", 1))
		pin(n, "Green", ctl("BoxLayer3ColorGreen", 0.3))
		pin(n, "Blue", ctl("BoxLayer3ColorBlue", 0.65))
		pin(n, "Alpha", ctl("BoxLayer3Alpha", 1))
		pin(n, "Level", ctl(prefixo .. "Level", 2))
		pin(n, "ExtendHorizontal", extend_h(prefixo))
		pin(n, "ExtendVertical", extend_v(prefixo))
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
		deslocar(n, ctl("BoxLayer3CenterX", -0.005),
			ctl("BoxLayer3CenterY", 0.007))
	end

	-- A CAIXA COMO RETANGULO (macro `Fixo`).
	--
	-- Existe quando o comp tem `GiBoxMask1`. E' a caixa que NAO olha o texto: o
	-- tamanho vem de `Width (px)`/`Height (px)` e mais nada - sem `Char Width`, sem
	-- `Px per Unit`, sem medir fonte. Era o pedido: "nao usa tamanho do texto para
	-- nada para renderizar a text-box".
	--
	-- As tres camadas empilhadas sao as mesmas cores do macro normal: 1 = TextBox,
	-- 2 = BoxShadow (que no 3color e' cor, nao sombra), 3 = BoxLayer3. Os offsets
	-- X/Y de cada uma continuam sendo os controles que ja existiam.
	--
	-- RESSALVA que nao da' pra verificar daqui (licenca nao-Studio): o `Height` de
	-- um RectangleMask pode ser relativo a' LARGURA do frame em vez da altura,
	-- conforme a versao. Se for, a altura sai errada pelo fator de aspecto (1,78 num
	-- 1080x1920) - o log diz o que foi escrito, e o conserto e' uma linha.
	-- O SPIN na caixa-retangulo: o mesmo giro do `expressao_spin` (o offset do
	-- Inspector da' raio e fase, `Template.BoxSpinSpeed` da' a velocidade, `time`
	-- da timeline da' a fase de cada legenda), aplicado ao CENTRO da mascara. Sem
	-- isto o `Fixo` desligava os elementos 7/8 do Text+ - onde o giro morava - e
	-- a caixa fixa saia parada mesmo com Spin Speed ligado (queixa de 28/09).
	--
	-- Em PIXELS, nao na coordenada normalizada: Center e' fracao da largura em x
	-- e da altura em y, entao um circulo em normalizado vira elipse 1,78x mais
	-- larga num 16:9. O offset e' convertido pra px, gira, e volta dividido por
	-- lw/lh. Com giro 0 a posicao inicial e' a mesma da caixa parada.
	--
	-- CUSTO: por frame, uma expressao trivial por camada (cos/sin), CONSTANTE -
	-- nada no array por caractere. Ver feedback-custo-playback.
	local girando = 0
	local function centro_da_camada(mask, cx, cy, ox, oy, lw, lh)
		local velocidade = tonumber(ctl("BoxSpinSpeed", 0)) or 0
		local dx, dy = ox * lw, oy * lh
		local raio = math.sqrt(dx * dx + dy * dy)
		-- A expressao sai ANTES, sempre: numero escrito em input com expressao
		-- e' aceito e ignorado (a armadilha do `deslocar`).
		pcall(function() mask.Center:SetExpression(nil) end)
		if velocidade == 0 or raio < 1e-6 then
			um(mask, "Center", { cx + ox, cy + oy })
			return
		end
		local fase = math.deg(math.atan2(dy, dx))
		local expr = string.format(
			"Point(%.6f + %.4f*cos((Template.BoxSpinSpeed*time+%.4f)*pi/180)/%d,"
			.. " %.6f + %.4f*sin((Template.BoxSpinSpeed*time+%.4f)*pi/180)/%d)",
			cx, raio, fase, lw, cy, raio, fase, lh)
		pcall(function() mask.Center:SetExpression(expr) end)
		escritos = escritos + 1
		girando = girando + 1
	end

	local function retangulo()
		local mask1 = comp:FindTool("GiBoxMask1")
		if not mask1 then return false end
		girando = 0

		local lw, lh
		pcall(function() lw = comp:GetPrefs("Comp.FrameFormat.Width") end)
		pcall(function() lh = comp:GetPrefs("Comp.FrameFormat.Height") end)
		lw, lh = tonumber(lw) or 1920, tonumber(lh) or 1080

		local largura_px = tonumber(ctl("TextBoxWidth", 0)) or 0
		local altura_px = tonumber(ctl("TextBoxHeight", 0)) or 0
		-- Zero nao e' tamanho: sem numero, a caixa ficaria invisivel e pareceria
		-- que o macro nao funciona. Um quarto da tela e' palpite declarado, e o
		-- log pede o numero.
		if largura_px <= 0 or altura_px <= 0 then
			diga("[GiAutoSubs] fixed box: Width (px) and Height (px) are 0 - "
				.. "nothing to draw. Set them in the Text Box group (this macro "
				.. "draws a real rectangle, so the size is yours to give).")
			largura_px = largura_px > 0 and largura_px or lw * 0.25
			altura_px = altura_px > 0 and altura_px or lh * 0.06
		end

		local centro = ctl("TextPosition", { 0.5, 0.22 })
		local cx = (type(centro) == "table" and centro[1]) or 0.5
		local cy = (type(centro) == "table" and centro[2]) or 0.22

		local ligada = ctl("TextBoxEnabled", 0) == 1
		local camadas = {
			{ mask = "GiBoxMask1", bg = "GiBoxBG1", pref = "TextBox",
			  liga = ligada, ox = 0, oy = 0,
			  alpha = ctl("TextBoxOpacity", 1) },
			{ mask = "GiBoxMask2", bg = "GiBoxBG2", pref = "BoxShadow",
			  liga = ligada and ctl("BoxShadowOnNormal", 0) == 1,
			  ox = ctl("BoxShadowCenterX", 0), oy = ctl("BoxShadowCenterY", 0),
			  alpha = ctl("BoxShadowOpacity", 1) },
			{ mask = "GiBoxMask3", bg = "GiBoxBG3", pref = "BoxLayer3",
			  liga = ligada and ctl("BoxLayer3Enabled", 0) == 1,
			  ox = ctl("BoxLayer3CenterX", 0), oy = ctl("BoxLayer3CenterY", 0),
			  alpha = ctl("BoxLayer3Alpha", 1) },
		}

		for _, c in ipairs(camadas) do
			local mask, bg = comp:FindTool(c.mask), comp:FindTool(c.bg)
			if mask and bg then
				-- Camada desligada = alpha ZERO. Nao existe `Enabled` num
				-- Background, e apagar o tool tiraria ele do grafo (e da' pra
				-- religar depois) - alpha zero custa o mesmo render e volta.
				local a = c.liga and (tonumber(c.alpha) or 1) or 0
				um(bg, "TopLeftRed", ctl(c.pref .. "ColorRed", 0))
				um(bg, "TopLeftGreen", ctl(c.pref .. "ColorGreen", 0))
				um(bg, "TopLeftBlue", ctl(c.pref .. "ColorBlue", 0))
				um(bg, "TopLeftAlpha", a)
				um(mask, "MaskWidth", lw)
				um(mask, "MaskHeight", lh)
				um(mask, "Width", largura_px / lw)
				um(mask, "Height", altura_px / lh)
				um(mask, "CornerRadius", ctl("TextBoxRound", 0))
				centro_da_camada(mask, cx, cy, tonumber(c.ox) or 0,
					tonumber(c.oy) or 0, lw, lh)
			end
		end
		if girando > 0 then
			diga(string.format("[GiAutoSubs] fixed box: %d colour layer(s) orbiting "
				.. "at Spin Speed %s deg/frame", girando, tostring(ctl("BoxSpinSpeed", 0))))
		end

		diga(string.format("[GiAutoSubs] fixed box (rectangle): %dx%dpx at "
			.. "%.3f,%.3f on a %dx%d frame - the caption text does not affect it",
			math.floor(largura_px + 0.5), math.floor(altura_px + 0.5), cx, cy,
			lw, lh))
		return true
	end

	-- Um Lock so' pra escrita: sem ele o Fusion re-avalia a arvore a cada
	-- SetInput, e sao dezenas por disparo. O Unlock tem que acontecer mesmo se
	-- algo levantar no meio, senao a composicao fica travada na cara do
	-- usuario - dai o pcall em volta.
	-- Antes do Lock: mexer em atributo de interface nao e' render, e o Lock existe
	-- pra agrupar as escritas de INPUT.
	ui_extend(ctl("TextBoxFixed", 0) == 1)

	local travou = pcall(function() comp:Lock() end)
	local ok, erro = pcall(function()
		local bolha = ctl("BubbleEnabled", 0) == 1
		caixa(__EL_BOLHA__, "Bubble", bolha)
		sombra(__EL_BOLHA_SOMBRA__, "Bubble", bolha and ctl("BoxShadowOnHighlight", 0) == 1)

		local cx = ctl("TextBoxEnabled", 0) == 1

		-- No macro `Fixo` quem desenha a caixa e' o RETANGULO, e os elementos
		-- 6/7/8 do Text+ ficam desligados: dois lugares desenhando a mesma caixa
		-- seria o problema de duas verdades, com a diferenca de que uma delas
		-- acompanha o texto - justamente o que esta variante veio tirar.
		local por_retangulo = retangulo()
		if por_retangulo then cx = false end

		caixa(__EL_CAIXA__, "TextBox", cx)
		sombra(__EL_CAIXA_SOMBRA__, "TextBox", cx and ctl("BoxShadowOnNormal", 0) == 1)
		-- Depende da caixa: terceira cor de caixa que nao existe nao e' nada.
		camada3(__EL_CAMADA3__, "TextBox",
			cx and ctl("BoxLayer3Enabled", 0) == 1)
	end)
	if travou then pcall(function() comp:Unlock() end) end
	if not ok then
		diga("[GiAutoSubs] " .. origem .. " -> ApplyGiStyle FAILED: " .. tostring(erro))
		return
	end

	-- O PREVIEW PARA AQUI.
	--
	-- Sem spline e sem GiBubblePop: sao as duas metades caras (o array de estilo
	-- por caractere e' quadratico nas palavras), e sao justamente as que o preview
	-- nao precisa - arrastar `Width` nao muda cor de palavra nenhuma. E' isto que
	-- faz o custo por FRAME deste recurso ser zero.
	--
	-- E sem log: ~40 disparos por arrasto encheriam o `_gimacro.log` de linhas
	-- iguais, que foi metade do motivo de os callbacks terem morrido no macro 11.
	if soCaixa then return end

	-- E por ultimo o spline. Num elemento ANIMADO a cor mora no array de
	-- keyframe, que vence os inputs do Text+ e do Follower1 - entao mexer no
	-- seletor de cor nao muda nada ate o array ser reconstruido. E' a mesma
	-- razao de o UpdateStyleColor do AutoSubs terminar chamando UpdateHighlight.
	--
	-- Aqui existia uma tabela NO_SPLINE dizendo quais controles vivem dentro do
	-- array de keyframe, pra pular a metade cara (N palavras x camadas x 4
	-- codigos) quando o controle mexido nao chegava la. Ela pagava o Inspector
	-- reagindo a cada valor intermediario de slider. Com a aplicacao vindo de um
	-- clique, refazer sempre custa uma vez e nao ha o que adivinhar.
	--
	-- `spline` (o argumento) continua sendo a palavra final de quem chamou:
	-- false quer dizer "nao refaca, eu vou reescrever o array em seguida" - e' o
	-- GiAutoSubs.lua criando as legendas, onde refazer aqui seria trabalho
	-- jogado fora 128 vezes.
	local refazer = spline
	if refazer == nil then refazer = true end
	-- O pop roda SEMPRE, mesmo quando o spline e' pulado: ele e' geometria
	-- animada, nao o array de estilo por caractere, e quem pula o array (o
	-- script, que o escreve ele mesmo) quer o pop do mesmo jeito.
	local estadoPop = "no GiBubblePop"
	do
		local f = gi_chunk(comp, tool, "GiBubblePop")
		if f then estadoPop = loadstring(f)()(comp, tool) or "done" end
	end

	-- O texto: a caixa das letras, e a sincronia entre o campo `Text` que voce
	-- edita e o tool que de fato desenha. Mexe no TEXTO, nao no estilo - mas
	-- entra aqui pelo mesmo motivo do pop: e' o Apply Style que aplica tudo que
	-- o Inspector pede, e um segundo botao seria um segundo lugar pra "nao
	-- surtiu efeito".
	local estadoCase = "no GiApplyText"
	do
		local f = gi_chunk(comp, tool, "GiApplyText")
		if f then estadoCase = loadstring(f)()(comp, tool) or "done" end
	end

	local estadoSpline = "skipped (not in the spline)"
	if refazer then
		local f = gi_chunk(comp, tool, "GiRebuildHighlight")
		if f then
			estadoSpline = loadstring(f)()(comp, tool) or "rebuilt"
		else
			estadoSpline = "GiRebuildHighlight MISSING"
		end
	end

	-- Uma linha por aplicacao, sempre: qual rotina rodou, quanto trabalho deu, e
	-- se o spline foi refeito. Com um caminho so', estas linhas sao o log
	-- inteiro - da' pra ler o bloco de um clique de ponta a ponta.
	diga(string.format("[GiAutoSubs] %s -> ApplyGiStyle: %d written, %d already ok; "
		.. "spline: %s; bubble pop: %s; text: %s",
		origem, escritos, iguais, estadoSpline, estadoPop, estadoCase))
end
"""


# Reconstroi os keyframes por palavra a partir dos controles do Inspector.
#
# O `GiAutoSubs.lua` guarda, em cada clipe, o tempo de cada palavra
# (`GiWordTiming`) e quais elementos sao animados (`GiCamadas`) - do mesmo jeito
# que o AutoSubs guarda `WordTiming` no CustomData. Com isso o macro consegue
# refazer o array sozinho quando alguem mexe numa cor, sem precisar do arquivo
# nem do script.
_REBUILD = """
return function(comp, tool)
__LOG_LUA__
	local template = comp:FindTool("Template") or tool
	local follower = comp:FindTool("Follower1")
	if not template or not follower then return "no Follower1" end

	-- Devolve SEMPRE uma string: quem chama imprime isso no log. Sair calado
	-- aqui era indistinguivel de ter funcionado.
	local tempos = template:GetData("GiWordTiming")
	local camadas = template:GetData("GiCamadas")
	if not tempos or not camadas then return "no GiWordTiming/GiCamadas" end
	if #tempos == 0 then return "empty GiWordTiming" end
	-- `camadas` vazio nao aborta aqui: o `WordFill` mais abaixo pode criar a
	-- dele, e e' o unico destaque que um estilo sem camada nenhuma teria.

	-- macro primeiro: e' onde o Inspector do clipe grava (ver `gi_macro`).
	local macro = gi_macro(comp, tool)
	local function ctl(nome, padrao)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil then return v end
			end
		end
		return padrao
	end

	-- A cor da palavra FALADA (o fill do elemento 1).
	local palavra_colorida = ctl("WordFillEnabled", 0) == 1

	-- A cor sai do Inspector quando a camada diz de qual controle ela vem
	-- (a bolha vem de Bubble*, a sombra dela de BoxShadow*). Sem isso o
	-- seletor de cor de um elemento animado seria enfeite.
	--
	-- O ELEMENTO 1 e' o caso que custou duas queixas de uma vez, e as duas tinham
	-- a mesma causa: ele lia a cor do `GiCamadas`, congelado quando o clipe
	-- nasceu. Entao (a) mexer em `Fill Color` e clicar Apply Style nao mudava um
	-- pixel - o array vence os inputs, e o array trazia a cor velha; e
	-- (b) DESMARCAR `Spoken Word > Enabled` tambem nao mudava nada, porque a cor
	-- ativa continuava vindo do `cor_ativa` gravado, nao do controle. Agora as
	-- duas saem do Inspector: base = `Fill Color`, ativa = `Word Color` enquanto
	-- o checkbox estiver marcado e a MESMA base quando ele nao estiver - que e'
	-- literalmente "a palavra falada nao muda de cor".
	local function cor_de(c, qual)
		local base = c[qual]
		local de = c.controle
		if c.elemento == 1 then
			de = "Fill"
			if qual == "cor_ativa" and palavra_colorida then de = "WordFill" end
		end
		if de then
			return {
				ctl(de .. "ColorRed", base and base[1] or 0),
				ctl(de .. "ColorGreen", base and base[2] or 0),
				ctl(de .. "ColorBlue", base and base[3] or 0),
			}
		end
		return base
	end

	-- O estilo pode nao ter camada de fill nenhuma (e' o caso do `capcut_bolha`,
	-- onde o destaque e' so' a bolha). Sem uma camada, o `Spoken Word` nao teria
	-- onde agir - entao ela nasce aqui. As cores vem do `cor_de` acima, entao
	-- basta a camada existir.
	if palavra_colorida then
		local tem = false
		for _, c in ipairs(camadas) do
			if c.elemento == 1 then tem = true end
		end
		if not tem then
			camadas[#camadas + 1] = { elemento = 1, on_base = 1, on_ativo = 1 }
		end
	end

	if #camadas == 0 then return "no highlight layers (nothing animates)" end

	-- O checkbox que LIGA cada camada animada, por elemento.
	--
	-- Sem isto o `Enabled` de uma camada animada vinha so' do `on_base`/
	-- `on_ativo` gravados no clipe quando ele nasceu, e o array vence o input:
	-- desmarcar "Bubble > Enabled" no Inspector escrevia `Enabled4 = 0` no Text+
	-- e no Follower1, e o keyframe da palavra falada devolvia 1 logo em seguida.
	-- O sintoma era o checkbox da bolha nao fazer nada.
	--
	-- A sombra depende da caixa que ela acompanha: sombra de bolha desligada nao
	-- e' sombra de coisa nenhuma.
	local LIGA = {
		[4] = { "BubbleEnabled" },
		[5] = { "BubbleEnabled", "BoxShadowOnHighlight" },
		[6] = { "TextBoxEnabled" },
		[7] = { "TextBoxEnabled", "BoxShadowOnNormal" },
		-- Hoje nenhum estilo anima a terceira cor (ela e' estatica, como a
		-- caixa). A entrada existe pra que, no dia em que um animar, o checkbox
		-- valha - sem ela o array devolveria `Enabled8 = 1` por cima do input,
		-- que e' exatamente o bug que a bolha teve.
		[8] = { "TextBoxEnabled", "BoxLayer3Enabled" },
	}
	-- Resolvido UMA vez por camada, nao por palavra: o laco abaixo e' N x N x
	-- camadas, e uma leitura de input ali dentro se multiplica por tudo isso.
	local permitida, cores = {}, {}
	for idx, c in ipairs(camadas) do
		permitida[idx] = true
		for _, nome in ipairs(LIGA[c.elemento] or {}) do
			if ctl(nome, 1) ~= 1 then permitida[idx] = false end
		end
		cores[idx] = { base = cor_de(c, "cor_base"), ativa = cor_de(c, "cor_ativa") }
	end

	local keyframes, k = {}, 0
	for i = 1, #tempos do
		local array = {}
		for j = 1, #tempos do
			local palavra = tempos[j]
			local ativa = (j == i)
			for idx, c in ipairs(camadas) do
				local ligado = permitida[idx]
					and ((ativa and c.on_ativo or c.on_base) == 1)
				local cor = ativa and cores[idx].ativa or cores[idx].base
				-- `Index` do array e' o elemento em base ZERO
				local elem = c.elemento - 1
				local vals = {
					[2000] = ligado and 1 or 0,
					[2401] = cor and cor[1] or 0,
					[2402] = cor and cor[2] or 0,
					[2403] = cor and cor[3] or 0,
				}
				for codigo, valor in pairs(vals) do
					table.insert(array, {
						codigo, palavra.startIndex, palavra.endIndex,
						Value = valor, __flags = 256, Index = elem,
					})
				end
			end
		end
		keyframes[tempos[i].startFrame] = {
			k,
			Value = {
				__ctor = "StyledText",
				Array = array,
				Flags = { StepIn = true, LockedY = true, __flags = 256 },
			},
		}
		k = k + 1
	end

	local ok = pcall(function()
		local cls = follower.Text:GetConnectedOutput():GetTool()
		local spline = cls.CharacterLevelStyling:GetConnectedOutput():GetTool()
		spline:SetKeyFrames(keyframes, true)
	end)
	if not ok then return "could not reach the spline" end
	return string.format("rebuilt %d keyframes (%d words x %d layers)",
		k, #tempos, #camadas)
end
"""


# Tudo em MAIUSCULAS ou tudo em minusculas.
#
# Duas decisoes que valem mais que o codigo:
#
# 1. NAO E' DESTRUTIVO. O texto que voce digitou fica guardado em
#    `GiTextOriginal`, e a transformacao sai SEMPRE dele. Sem isso, alternar
#    MAIUSCULAS -> minusculas perderia a capitalizacao original pra sempre - e a
#    primeira vez que alguem percebesse seria relendo uma legenda ja exportada.
#
#    E se o texto foi editado a mao no Inspector (que e' um habito deste
#    projeto: o MODO "atualizar" existe pra preservar isso), o texto novo vira o
#    original. Sem essa regra, clicar Apply Style depois de corrigir uma palavra
#    devolveria a legenda ao texto antigo.
#
# 2. ACENTO. `string.upper` do Lua e' ASCII: "acao" vira "ACAO", mas "acao" com
#    cedilha e til vira "AcaO" com cedilha e til minusculos - errado, e bem
#    visivel numa legenda. As letras acentuadas que o portugues usa moram no
#    bloco Latin-1 do UTF-8, onde a minuscula e' a maiuscula + 0x20 e as duas
#    ocupam os mesmos 2 bytes. Dai o `gsub` no byte de continuacao: o
#    comprimento em caracteres nao muda, que e' condicao pro array de estilo por
#    caractere (startIndex/endIndex) continuar valendo.
_CASE = """
return function(comp, tool)
__LOG_LUA__
	local template = comp:FindTool("Template") or tool
	if not template then return "no Template" end

	local macro = gi_macro(comp, tool)
	local function ctl(nome, padrao)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil then return v end
			end
		end
		return padrao
	end

	-- <<CASE_FUNCS
	-- (o validador extrai daqui ate' o fecho e roda em cima de exemplos - o
	-- marcador fica SOZINHO na linha, senao o resto do comentario entra no
	-- trecho extraido sem o `--` e o chunk nao compila)
	--
	-- 0xC3 e' o primeiro byte de todo acentuado latino em UTF-8; o segundo diz
	-- qual letra e' e se e' maiuscula (0x80..0x9E) ou minuscula (0xA0..0xBE).
	-- 0x97 e 0xB7 sao 'x' e '/' de multiplicacao e divisao - nao sao letras.
	local function maiuscula(s)
		s = s:gsub("\\195(.)", function(c)
			local b = string.byte(c)
			if b >= 160 and b <= 190 and b ~= 183 then
				return "\\195" .. string.char(b - 32)
			end
		end)
		return (s:upper())
	end

	local function minuscula(s)
		s = s:gsub("\\195(.)", function(c)
			local b = string.byte(c)
			if b >= 128 and b <= 158 and b ~= 151 then
				return "\\195" .. string.char(b + 32)
			end
		end)
		return (s:lower())
	end

	-- CAMEL CASE: primeira letra de cada palavra em maiuscula, o resto minusculo.
	--
	-- "eu adoro torresmo, uhuu" -> "Eu Adoro Torresmo, Uhuu", e tambem
	-- "ELES SO SAO MEIO TIMIDOS" -> "Eles So Sao Meio Timidos": comeca
	-- MINUSCULANDO tudo, senao um texto que ja esta em caixa alta (o padrao deste
	-- projeto) sairia igual ao que entrou.
	--
	-- Anda de CARACTERE, nao de byte: acentuado latino ocupa dois bytes em UTF-8,
	-- e pular de um em um poria maiuscula no meio da letra - o mesmo motivo do
	-- `utf8_len` do Fixed Box.
	--
	-- Hifen e apostrofo NAO comecam palavra nova ("Bem-vindo", "D'agua"), e
	-- digito faz parte da palavra ("3d" nao vira "3D"). Quem comeca palavra e'
	-- pontuacao e espaco - foi o que o exemplo pedido mostrou: a virgula de
	-- "torresmo, uhuu" reinicia.
	local function camel(s)
		s = minuscula(s)
		local saida, comeco, i = {}, true, 1
		while i <= #s do
			local b = s:byte(i)
			local n = (b == 195) and 2 or 1
			local pedaco = s:sub(i, i + n - 1)
			local dentro = (n == 2) or pedaco:match("[%w'%-]") ~= nil
			if dentro and comeco and (n == 2 or pedaco:match("%a")) then
				pedaco = maiuscula(pedaco)
				comeco = false
			elseif dentro then
				comeco = false
			else
				comeco = true
			end
			saida[#saida + 1] = pedaco
			i = i + n
		end
		return table.concat(saida)
	end

	local function transformar(s, modo)
		if modo == 1 then return minuscula(s) end
		if modo == 2 then return maiuscula(s) end
		if modo == 3 then return camel(s) end
		return s
	end
	-- CASE_FUNCS>>

	local modo = math.floor(ctl("TextCase", 0))
	local atual
	pcall(function() atual = template:GetInput("Text") end)
	if type(atual) ~= "string" then return "no text" end

	local original = template:GetData("GiTextOriginal")
	local ultimo = template:GetData("GiTextCase") or 0
	if type(original) ~= "string" or transformar(original, ultimo) ~= atual then
		-- primeira vez, ou o texto foi editado a mao: o que esta na tela agora
		-- passa a ser o original
		original = atual
		pcall(function() template:SetData("GiTextOriginal", original) end)
	end

	local novo = transformar(original, modo)
	pcall(function() template:SetData("GiTextCase", modo) end)

	-- Escreve o texto nos DOIS tools, comparando CADA UM com o que vai entrar.
	--
	-- Duas coisas moram aqui, e a segunda so' apareceu depois:
	--
	-- 1. O que o Text+ RENDERIZA nao e' o `Text` dele: o `StyledText` vem
	--    conectado ao Follower1, que vem do CharacterLevelStyling1 - e o texto
	--    de verdade e' o `Text` do CLS1.
	--
	-- 2. Editar o texto no Inspector escreve so' no Text+. Quem sincronizava os
	--    dois no AutoSubs era o `UpdateTextContent`, uma das seis rotinas que
	--    este macro DESARMA (ela vinha junto com a cadeia que repintava tudo).
	--    Sem ela, digitar no campo Text nao mudava a legenda - e o Apply Style
	--    tambem nao, porque a versao anterior desta rotina comparava com o Text+
	--    e concluia "ja esta certo" enquanto o CLS1 seguia com o texto velho.
	--
	-- Comparar por alvo e' o que fecha os dois casos de uma vez.
	local escritos = 0
	local cls = comp:FindTool("CharacterLevelStyling1")
	for _, alvo in ipairs({ template, cls }) do
		if alvo then
			local tem
			pcall(function() tem = alvo:GetInput("Text") end)
			if tem ~= novo then
				local ok = pcall(function() alvo:SetInput("Text", novo) end)
				if ok then escritos = escritos + 1 end
			end
		end
	end

	local nome = ({ [0] = "as typed", [1] = "lowercase", [2] = "UPPERCASE" })[modo]
		or "as typed"

	-- Editar o texto a mao MOVE os caracteres, e o destaque por palavra endereca
	-- o texto por INDICE de caractere (`GiWordTiming`). Trocar "vale" por
	-- "valendo" no Inspector nao mexia nesses indices: o destaque seguia pintando
	-- os 4 caracteres de "vale" e as tres letras novas ficavam de fora. Era esse
	-- o "so' 'vale' recebe a cor do Spoken Word".
	--
	-- O que da' pra refazer aqui e' a REPARTICAO, nao o tempo: enquanto o numero
	-- de palavras nao muda, cada palavra continua comecando no mesmo frame e o
	-- unico dado defasado e' onde ela comeca e acaba no texto. Palavra a mais ou
	-- a menos e' outro problema - dai o aviso, em vez de um alinhamento
	-- inventado que erraria calado.
	--
	-- A quebra e' a MESMA do pipeline (`tempos_das_palavras`): o espaco separador
	-- pertence a palavra SEGUINTE (" ir."), entao o texto e' exatamente a
	-- concatenacao dos pedacos e os indices ficam contiguos, sem buraco.
	local function fatiar(s)
		local pedacos, ini, pos, branco_antes = {}, 0, 0, nil
		local i = 1
		while i <= #s do
			local b = s:byte(i)
			-- passo em CODEPOINT, nao em byte: os indices do array de estilo por
			-- caractere contam caractere, e "ação" tem 4, nao 6
			local n = 1
			if b >= 240 then n = 4 elseif b >= 224 then n = 3
			elseif b >= 192 then n = 2 end
			local ch = s:sub(i, i + n - 1)
			local branco = (ch == " " or ch == "\\n" or ch == "\\t")
			if pos > 0 and branco and not branco_antes then
				pedacos[#pedacos + 1] = { ini, pos - 1 }
				ini = pos
			end
			branco_antes = branco
			pos = pos + 1
			i = i + n
		end
		pedacos[#pedacos + 1] = { ini, pos - 1 }
		return pedacos
	end

	local tempos = template:GetData("GiWordTiming")
	local realinhadas = 0
	if tempos and #tempos > 0 then
		local pedacos = fatiar(novo)
		if #pedacos == #tempos then
			for i, t in ipairs(tempos) do
				if t.startIndex ~= pedacos[i][1] or t.endIndex ~= pedacos[i][2] then
					t.startIndex, t.endIndex = pedacos[i][1], pedacos[i][2]
					realinhadas = realinhadas + 1
				end
			end
			if realinhadas > 0 then
				pcall(function() template:SetData("GiWordTiming", tempos) end)
			end
		else
			diga(string.format("[GiAutoSubs] WARNING: the text now has %d word(s) "
				.. "but the per-word highlight was built for %d - run the script "
				.. "again to realign it", #pedacos, #tempos))
		end
	end

	if realinhadas > 0 then
		return string.format("%s (%d tools, %d word(s) realigned)",
			nome, escritos, realinhadas)
	end
	if escritos == 0 then return nome .. " (already in sync)" end
	return string.format("%s (%d tools)", nome, escritos)
end
"""


# O "pop" do CapCut: a bolha entra menor nos dois eixos e cresce ate o tamanho
# normal, a cada palavra.
#
# Por que da' pra fazer com um input GLOBAL: nao existe "escala" por elemento no
# Text+, entao quem faz o tamanho da bolha e' o par
# ExtendHorizontal/ExtendVertical - e eles nao sao por caractere. Acontece que
# num instante qualquer so' existe UMA bolha na tela (o array do spline acende a
# da palavra falada e apaga as outras), entao animar o input global anima
# exatamente a bolha que se ve.
#
# Rotina separada do `GiRebuildHighlight` de proposito: o pop e' geometria, nao
# tem nada a ver com o array de character-level styling, e as duas coisas sao
# pedidas em momentos diferentes - o `GiAutoSubs.lua` escreve o array ele mesmo
# nas 128 legendas (e manda o rebuild PULAR), mas o pop ele quer nas duas.
#
# Os dois inputs so' existem no Text+; o Follower1 nao traz geometria de caixa.
_POP = """
return function(comp, tool)
__LOG_LUA__
	local template = comp:FindTool("Template") or tool
	if not template then return "no Template" end

	-- macro primeiro: e' onde o Inspector do clipe grava (ver `gi_macro`).
	local macro = gi_macro(comp, tool)
	local function ctl(nome, padrao)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil then return v end
			end
		end
		return padrao
	end

	local eixos = { ExtendHorizontal__EL_BOLHA__ = "BubbleExtendHorizontal",
		ExtendVertical__EL_BOLHA__ = "BubbleExtendVertical" }

	local tempos = template:GetData("GiWordTiming")
	local ligado = ctl("BubblePopEnabled", 0) == 1
		and ctl("BubbleEnabled", 0) == 1
		and tempos ~= nil and #tempos > 0

	if not ligado then
		-- Devolve os dois inputs pro valor fixo. Sem isto, desmarcar o Pop
		-- deixaria o spline mandando pra sempre - e os sliders de Extend
		-- virariam enfeite, que e' o mesmo tipo de armadilha da opacidade.
		for chave, controle in pairs(eixos) do
			pcall(function() template[chave] = nil end)
			pcall(function() template:SetInput(chave, ctl(controle, 0)) end)
		end
		return "off"
	end

	local quanto = ctl("BubblePopAmount", 0.15)
	local dura = math.max(1, math.floor(ctl("BubblePopFrames", 3)))

	local feitos = 0
	for chave, controle in pairs(eixos) do
		local cheio = ctl(controle, 0)
		local kf = {}
		for i = 1, #tempos do
			local inicio = tempos[i].startFrame
			kf[inicio] = { cheio - quanto }
			kf[inicio + dura] = { cheio }
			-- SEGURA o tamanho ate a proxima palavra. Sem este keyframe a
			-- interpolacao entre o fim do pop e a palavra seguinte vira uma
			-- rampa longa: a bolha encolheria devagar durante a palavra
			-- inteira, que nao e' pop nenhum.
			local prox = tempos[i + 1] and tempos[i + 1].startFrame
			if prox and prox - 1 > inicio + dura then
				kf[prox - 1] = { cheio }
			end
		end
		local ok = pcall(function()
			-- AddModifier repetido empilha modificador em cima de modificador;
			-- so' cria quando ainda nao ha um.
			if not template[chave]:GetConnectedOutput() then
				template:AddModifier(chave, "BezierSpline")
			end
			template[chave]:GetConnectedOutput():GetTool():SetKeyFrames(kf, true)
		end)
		if ok then feitos = feitos + 1 end
	end

	return string.format("%d/2 axes, -%.2f over %d frames on %d words",
		feitos, quanto, dura, #tempos)
end
"""


# A PONTE: muda os caracteres por caixa e refaz as legendas.
#
# Um corpo so', DOIS chamadores - o botao "Rebuild Captions" da aba Meta e o
# "Apply Style to This Track" quando o numero de caracteres por caixa mudou.
# Dois corpos seriam duas copias da mesma sequencia destrutiva pra divergir.
#
# Por que o Apply Style nao basta: mudar os caracteres por caixa muda o NUMERO de
# legendas - repartir o segmento que nao cabe e' o que o `repartir()` do
# giautosubs.py faz. Restilizar 156 clipes nao produz os 191 que o limite novo
# pede; e' preciso gerar o arquivo de novo e recriar os clipes.
#
# A sequencia, e por que nesta ordem:
#
#   1. roda o giautosubs.py com o `--max-chars` novo, gravando um `.lua` de NOME
#      NOVO (`legendas_c25.lua`). Nome novo e nao sobrescrita: o arquivo anterior
#      fica no disco pra voltar atras, e o campo `Captions File` da Meta passa a
#      dizer qual esta valendo - com sobrescrita ele nunca mudaria de valor e o
#      campo nao informaria nada.
#   2. so' se o arquivo apareceu, relinka o clipe e carimba `GiCharsBuilt`.
#   3. grava o PEDIDO e para. Quem recria os clipes e' a rodada do menu.
#
# Nada e' destruido antes de o arquivo novo existir: na ordem trocada, um erro no
# Python deixaria a track vazia e sem arquivo pra recriar dela.
#
# POR QUE O BOTAO NAO RECRIA (macro 29, custou um crash do Resolve):
#
# O botao roda DENTRO da comp do clipe clicado. Chamar o GiAutoSubs.lua daqui
# (era um `dofile`) faz o modo `substituir` rodar `DeleteClips` em todas as
# legendas - INCLUSIVE a deste clipe. O codigo apagava a comp que estava
# executando ele: o Resolve cai, sem mensagem nenhuma.
#
# Nao ha como contornar mantendo o mesmo clique: o REPLACE tem que apagar a
# legenda de onde o clique saiu. Entao o botao prepara tudo e a rodada acontece
# no menu - com o `_gipedido.txt` respondendo as quatro perguntas, e' um clique
# em Workspace > Scripts > GiAutoSubs e mais nada.
_RECONSTRUIR = r"""
return function(comp, tool, rotulo)
__LOG_LUA__
	local ROTULO = rotulo or "Rebuild with Selected"
	local template = comp:FindTool("Template") or tool
	local macro = gi_macro(comp, tool)
	if not macro then
		diga("[GiAutoSubs] " .. ROTULO .. ": this clip has no InputKeys - it "
			.. "carries an old copy of the macro, so there is no Meta tab to read")
		return false
	end

	-- Le na ordem macro -> tool -> Text+, igual ao `ctl` das outras rotinas: o
	-- Inspector do clipe grava no MacroOperator. Campo de texto VAZIO conta como
	-- ausente - caminho em branco nao e' resposta, e' falta de resposta.
	local function meta(nome, padrao)
		local v
		for _, alvo in ipairs({ macro, tool, template }) do
			if alvo then
				pcall(function() v = alvo:GetInput(nome) end)
				if v ~= nil and v ~= "" then return v end
			end
		end
		return padrao
	end

	local lua_atual = tostring(meta("MetaCaptionsFile", ""))
	local corte = tostring(meta("MetaCutFolder", ""))
	local estilo = tostring(meta("MetaStyle", ""))
	local transcricao = tostring(meta("MetaTranscript", ""))
	local title = tostring(meta("MetaTitle", ""))
	local preset = tostring(meta("MetaConfig", ""))
	local chars = math.floor(tonumber(meta("MetaCharsPerBox", 0)) or 0)
	local linhas = math.floor(tonumber(meta("MetaLines", 1)) or 1)

	-- AS OPCOES SAO AS CAIXAS MARCADAS, e nao o botao que foi clicado.
	--
	-- Antes eram tres botoes (um por opcao), e eles nao combinavam: "largura fixa
	-- E sem buracos" pedia duas rodadas inteiras. Com checkbox + submit a rodada
	-- acontece uma vez, com o que esta marcado - e o que esta marcado continua
	-- visivel depois, em vez de sumir no clique.
	--
	-- `Fixed Width` na Meta e' o MESMO controle da caixa fixa no grupo Text Box
	-- (`TextBoxFixed`), exposto duas vezes. Um controle proprio aqui seria uma
	-- segunda verdade sobre a mesma coisa.
	local fixa = (tonumber(meta("TextBoxFixed", 0)) or 0) == 1
	local semBuracos = (tonumber(meta("MetaNoGaps", 0)) or 0) == 1

	diga("[GiAutoSubs] ===== " .. ROTULO .. " =====")
	diga("[GiAutoSubs] linked captions : " .. (lua_atual ~= "" and lua_atual or "(none)"))
	diga("[GiAutoSubs] cut folder      : " .. (corte ~= "" and corte or "(none)"))
	diga("[GiAutoSubs] style / title   : " .. estilo .. " / " .. title)
	diga("[GiAutoSubs] config (preset) : " .. (preset ~= "" and preset or "(none)"))
	diga(string.format("[GiAutoSubs] wrapping        : %d char(s) per box, %d line(s)",
		chars, linhas))
	diga("[GiAutoSubs] fixed width     : " .. (fixa and "yes - every caption "
		.. "gets the width of a full line" or "no - the box follows the text"))
	diga("[GiAutoSubs] gaps            : " .. (semBuracos and "filled - each "
		.. "caption lasts until the next one starts" or "kept as the speech is"))

	-- A pasta do corte e' o unico campo sem substituto: e' o argumento do
	-- giautosubs.py. Sem ela o clipe nasceu antes da aba Meta (ou foi arrastado
	-- da aba Effects) e nao ha' o que reconstruir.
	if corte == "" or chars <= 0 then
		diga("[GiAutoSubs] " .. ROTULO .. ": the Meta tab does not say which cut "
			.. "folder this caption came from (or Characters per Box is 0). "
			.. "Recreate the captions with the script once and it fills itself.")
		return false
	end

	-- O nome novo. O `_c%d+` sai antes de entrar: senao um segundo clique
	-- produziria `legendas_c25_c19.lua`.
	local dir, arq = lua_atual:match("^(.*)[\\/]([^\\/]+)$")
	if not dir then
		dir = corte .. "\\legendas"
		arq = "legendas.lua"
	end
	local base = (arq:gsub("%.lua$", ""))
	base = (base:gsub("_c%d+$", ""))
	local novo_json = dir .. "\\" .. base .. "_c" .. chars .. ".json"
	local novo_lua = dir .. "\\" .. base .. "_c" .. chars .. ".lua"

	-- Aspas em volta do comando INTEIRO, alem das de cada caminho: com o
	-- `cmd /c` do Windows, um primeiro token entre aspas faz o resto da linha ser
	-- lido errado. Este embrulho e' o conserto conhecido disso.
	local cmd = string.format('""%s" "%s" "%s" --max-chars %d --max-lines %d --out "%s"',
		"__PYTHON__", "__GIAUTOSUBS__", corte, chars, linhas, novo_json)
	if estilo ~= "" then cmd = cmd .. ' --estilo "' .. estilo .. '"' end
	-- A LARGURA FIXA da rodada inteira.
	--
	-- O checkbox `Fixed Box` vale por clipe e o Apply Style o levaria pros
	-- outros, mas mudar os caracteres por caixa recria os clipes de qualquer
	-- jeito - entao o lugar honesto de pedir "todas fixas" e' aqui, na geracao.
	-- Assim as legendas NASCEM com a caixa do mesmo tamanho, e a borda colorida
	-- orbita um retangulo parado enquanto o texto troca dentro dele.
	-- Os DOIS sentidos, sempre explicitos: sem o `--free-box`, uma rodada que
	-- quer a caixa livre cairia no que o estilos.json disser - e o que manda aqui
	-- e' o clipe que esta na tela, nao o estilo no disco.
	cmd = cmd .. (fixa and " --fixed-box" or " --free-box")
	if semBuracos then cmd = cmd .. " --no-gaps" end
	if transcricao ~= "" then cmd = cmd .. ' --transcript "' .. transcricao .. '"' end

	-- `os.execute` com a saida redirecionada pra arquivo, e nao `io.popen`: ler
	-- um pipe na thread da interface do Resolve e' o segundo suspeito do crash, e
	-- nao faz nada que isto nao faca. Trava a interface pelos segundos que o
	-- Python leva - e' sincrono, e e' o preco de nao ter onde rodar em paralelo.
	--
	-- O redirecionamento vai DENTRO da aspa externa. O `cmd /c` tira a primeira e
	-- a ULTIMA aspa da linha; com o `> "relato"` depois do embrulho, a ultima era a
	-- do relato, e o `--transcript` engolia o redirecionamento: o Python morria em
	-- `Invalid argument: '...turnsWhisper.json" > ...'` e todo Rebuild com
	-- transcricao falhava calado (28/09 - o "No Gaps nao funciona").
	local relato = "__RELATO__"
	diga("[GiAutoSubs] running (Resolve freezes for a few seconds): " .. cmd .. '"')
	-- O relato velho sai antes: senao, com o Python morto, as linhas da rodada
	-- ANTERIOR apareceriam aqui como se fossem desta.
	pcall(function() os.remove(relato) end)
	pcall(function() os.execute(cmd .. ' > "' .. relato .. '" 2>&1"') end)
	local saida = {}
	pcall(function()
		local fh = io.open(relato, "r")
		if not fh then return end
		for linha in fh:lines() do saida[#saida + 1] = linha end
		fh:close()
	end)
	-- So' as ultimas linhas: o resumo do giautosubs.py e' o que interessa, e o
	-- log do macro nao e' lugar pra despejo (a mesma regra do `erro_curto`).
	for i = math.max(1, #saida - 12), #saida do
		diga("[GiAutoSubs]   | " .. tostring(saida[i]))
	end

	-- Sucesso = o Python DISSE que escreveu este arquivo. So' conferir que o .lua
	-- existe nao prova nada: o nome e' o mesmo da rodada anterior, entao com o
	-- Python morto o arquivo VELHO passava por novo e o botao dizia "ready".
	local existe = false
	for _, linha in ipairs(saida) do
		if linha:find(novo_lua, 1, true) and linha:find("GiAutoSubs.lua reads", 1, true) then
			existe = true
		end
	end
	if not existe then
		diga("[GiAutoSubs] " .. ROTULO .. ": " .. novo_lua .. " was NOT written - "
			.. "nothing was changed on the timeline. Check the lines above "
			.. "(python path, cut folder, transcript).")
		return false
	end

	-- Relinka ANTES de recriar: se o passo seguinte falhar, o clipe pelo menos
	-- diz qual arquivo esta valendo agora.
	pcall(function() macro:SetInput("MetaCaptionsFile", novo_lua) end)
	pcall(function() macro:SetData("GiCharsBuilt", chars) end)
	diga("[GiAutoSubs] linked now: " .. novo_lua)

	-- O recado pro GiAutoSubs.lua. `substituir` = REPLACE: o pedido veio de quem
	-- estava olhando as legendas antigas e pediu outras no lugar delas, entao
	-- perguntar o conflito de novo seria perguntar o que acabou de ser respondido.
	local pedido = "__PEDIDO__"
	local escrito = false
	pcall(function()
		local f = io.open(pedido, "w")
		if not f then return end
		f:write("arquivo\t", novo_lua, "\n")
		f:write("conflito\tsubstituir\n")
		if title ~= "" then f:write("estilo\t", title, "\n") end
		if preset ~= "" then f:write("preset\t", preset, "\n") end
		f:close()
		escrito = true
	end)
	if not escrito then
		diga("[GiAutoSubs] " .. ROTULO .. ": could not write " .. pedido
			.. " - the captions file was generated but the clips were NOT "
			.. "recreated. Run Workspace > Scripts > GiAutoSubs and pick "
			.. novo_lua)
		return false
	end

	-- E PARA AQUI. Recriar daqui apagaria a legenda deste clipe - a comp que
	-- esta' rodando este codigo - e o Resolve cai sem mensagem (ver o topo).
	diga("[GiAutoSubs] ===== ready =====")
	diga("[GiAutoSubs] now run:  Workspace > Scripts > GiAutoSubs")
	diga("[GiAutoSubs] it will NOT ask anything - the file, the title, the config "
		.. "and the REPLACE were all answered by this click.")
	diga("[GiAutoSubs] (the button cannot recreate the clips itself: it runs "
		.. "inside this caption's own composition, and REPLACE deletes this "
		.. "caption - Resolve crashes when the code that is running gets "
		.. "deleted under it.)")
	return true
end
"""


def _reconstruir():
    """O `_RECONSTRUIR` com os quatro caminhos de maquina dentro.

    Barras DOBRADAS: o trecho vira string Lua com aspas, dentro de um `[[ ]]` do
    .setting - `\\` solto viraria escape na hora de carregar. Mesma razao do
    `_DESTINO_PRESET`.
    """
    def esc(p):
        return p.replace("\\", "\\\\")
    return (_com_log(_RECONSTRUIR)
            .replace("__PYTHON__", esc(PYTHON_EXE))
            .replace("__GIAUTOSUBS__", esc(GIAUTOSUBS_PY))
            .replace("__PEDIDO__", esc(PEDIDO))
            .replace("__RELATO__", esc(RELATO)))


# O submit da aba Meta. UM botao, e as opcoes sao as caixas marcadas acima dele.
#
# Corpo de uma chamada so': quem faz o trabalho e' o chunk `GiRebuild`, que e' o
# mesmo codigo que o "Apply Style to This Track" chama quando percebe que os
# caracteres por caixa mudaram.
_BOTAO_RECONSTRUIR = """
__LOG_LUA__
local f = gi_chunk(comp, tool, "GiRebuild")
if f then
	loadstring(f)()(comp, tool, "Rebuild with Selected")
else
	print("[GiAutoSubs] Rebuild with Selected: no tool in this comp owns "
		.. "GiRebuild - the clip carries an old copy of the macro "
		.. "(see MACRO_VERSAO)")
end
"""


def _com_log(texto):
    """Injeta o `diga()` no lugar do marcador `__LOG_LUA__`.

    O caminho vai entre ASPAS, nao entre `[[ ]]`: o trecho e' colado dentro de
    um chunk que ja esta num `[[ ]]` do .setting, e um `]]` a mais fecharia a
    string cedo demais - o macro inteiro para de compilar. Como e' string com
    aspas, as barras invertidas do Windows precisam ser dobradas.
    """
    return texto.replace(
        "__LOG_LUA__",
        _LOG_LUA.replace("__LOG__", LOG_MACRO.replace("\\", "\\\\"))
                .replace("__LOG_MAXIMO__", str(LOG_MAXIMO)))


def _update_all():
    return _com_log(_UPDATE_ALL)


def _apply_gi():
    # Nada de recortar: o ApplyGiStyle sai inteiro, com a rotina `camada3` e com
    # o `deslocar` dos elementos 7 e 8. `deslocar` cai em `pin` quando
    # `BoxSpinSpeed` e' 0, entao o ramo sem spin nao tinha o que fazer aqui.
    corpo = _APPLY_GI
    return _com_log(corpo
            .replace("__EL_BOLHA__", str(EL_BOLHA))
            .replace("__EL_BOLHA_SOMBRA__", str(EL_BOLHA_SOMBRA))
            .replace("__EL_CAIXA__", str(EL_CAIXA))
            .replace("__EL_CAIXA_SOMBRA__", str(EL_CAIXA_SOMBRA))
            .replace("__EL_CAMADA3__", str(EL_CAMADA3)))


def _pop():
    return _com_log(_POP.replace("__EL_BOLHA__", str(EL_BOLHA)))


# -------------------------------------------------------- controles novos

# Nenhum controle reage sozinho. Quem aplica e' o botao Apply Style, e so' ele.
#
# Por que os callbacks sairam (eles existiram, e por uma sessao inteira):
#
# 1. `INPS_ExecuteOnChange` dispara a CADA valor intermediario de um arrasto de
#    slider - ~40 vezes por ajuste. Cada disparo escrevia ~80 inputs em dois
#    tools e podia refazer o spline. Metade do codigo daqui (as tabelas
#    ANIMACAO, ESTILO_BASE, NO_SPLINE) existia so' pra amortecer isso.
# 2. O `tool` que o Fusion entrega pro callback e' o Text+ interno, nao o
#    MacroOperator onde o codigo mora - entao metade dos disparos so' sabia
#    imprimir "nothing was applied". O log ficava ilegivel e nao dava pra
#    diagnosticar nada.
#
# Um clique explicito faz o mesmo trabalho uma vez, com um bloco de log que se
# consegue ler. `_desautomatizar` garante que nem os callbacks que vem no macro
# do AutoSubs sobrem - senao voltariam a ser um segundo caminho invisivel.
def _uc(nome, campos):
    linhas = [f"{nome} = {{"]
    for chave, valor in campos:
        linhas.append(f"\t{chave} = {valor},")
    linhas.append("},")
    return "\n".join(linhas)


def _rotulo(nome, texto, n):
    return _uc(nome, [
        ("LINKS_Name", f'"{texto}"'),
        ("LINKID_DataType", '"Number"'),
        ("INPID_InputControl", '"LabelControl"'),
        ("LBLC_DropDownButton", "true"),
        ("LBLC_NumInputs", str(n)),
        ("INP_Default", "1"),
        ("INP_Integer", "false"),
        ("INP_Passive", "true"),
    ])


def _checkbox(nome, texto, padrao=0):
    return _uc(nome, [
        ("LINKS_Name", f'"{texto}"'),
        ("LINKID_DataType", '"Number"'),
        ("INPID_InputControl", '"CheckboxControl"'),
        ("INP_Integer", "true"),
        ("INP_Default", str(padrao)),
        ("INP_MinAllowed", "0"),
        ("INP_MaxAllowed", "1"),
        ("CBC_TriState", "false"),
        ("INP_External", "false"),
        ("INP_Passive", "false"),
    ])


def _slider(nome, texto, padrao, minimo, maximo, inteiro=False):
    campos = [
        ("LINKS_Name", f'"{texto}"'),
        ("LINKID_DataType", '"Number"'),
        ("INPID_InputControl", '"SliderControl"'),
        ("INP_Default", str(padrao)),
        ("INP_MinScale", str(minimo)),
        ("INP_MaxScale", str(maximo)),
        ("INP_MinAllowed", "-1000000"),
        ("INP_MaxAllowed", "1000000"),
        ("INP_Integer", "true" if inteiro else "false"),
        ("INP_External", "false"),
        ("INP_Passive", "false"),
    ]
    return _uc(nome, campos)


def _combo(nome, texto, opcoes, padrao):
    """Combo com as opcoes DENTRO do bloco.

    As `{ CCS_AddString = "..." }` sao o que o Fusion mostra na lista. Um
    ComboControl sem nenhuma e' um combo vazio: ele aparece no Inspector, abre,
    e nao tem o que escolher.

    Elas eram enfiadas com um `replace` na linha do `INPS_ExecuteOnChange` - e
    quando os callbacks sairam (macro 11) essa linha deixou de existir, o
    replace parou de casar, e os tres combos (`Level` da bolha, `Level` da
    caixa, e depois o `Case`) nasceram vazios sem ninguem reclamar. Por isso
    agora elas entram na propria montagem do bloco, e o validador conta.
    """
    linhas = [f"{nome} = {{"]
    for chave, valor in [
        ("LINKS_Name", f'"{texto}"'),
        ("LINKID_DataType", '"Number"'),
        ("INPID_InputControl", '"ComboControl"'),
        ("INP_Integer", "true"),
        ("INP_Default", str(padrao)),
        ("INP_MinAllowed", "0"),
        ("INP_MaxAllowed", str(len(opcoes) - 1)),
        ("INP_External", "false"),
        ("INP_Passive", "false"),
    ]:
        linhas.append(f"\t{chave} = {valor},")
    linhas.extend(f'\t{{ CCS_AddString = "{o}" }},' for o in opcoes)
    linhas.append("},")
    return "\n".join(linhas)


def _texto(nome, rotulo, linhas=1):
    """Campo de TEXTO no Inspector.

    O primeiro controle do projeto que nao e' `Number`. Um caminho de arquivo
    nao cabe em numero, e a alternativa (guardar so' no `SetData` do clipe) seria
    um dado que existe e nao aparece - justamente o contrario do que a aba Meta
    veio resolver.

    Editavel de proposito: trocar o `.lua` linkado na mao e' a saida quando a
    ponte pro Python nao esta disponivel (outra maquina, outro caminho).
    """
    return _uc(nome, [
        ("LINKS_Name", f'"{rotulo}"'),
        ("LINKID_DataType", '"Text"'),
        ("INPID_InputControl", '"TextEditControl"'),
        ("TEC_Lines", str(linhas)),
        ("TEC_ReadOnly", "false"),
        ("INP_External", "false"),
        ("INP_Passive", "false"),
    ])


def _cor(prefixo, rotulo, grupo, padrao=(0, 0, 0)):
    """Seletor de cor de verdade.

    Tres sliders soltos (o que estava aqui antes) nao viram um seletor: o que
    junta R, G e B num unico widget com roda de cor e' o par
    `INPID_InputControl = "ColorControl"` + `IC_ControlGroup` igual nos tres,
    exatamente como o AutoSubs faz em FillColorRed/Green/Blue.
    """
    out = []
    for i, (canal, valor) in enumerate(zip(("Red", "Green", "Blue"), padrao)):
        campos = [
            ("LINKID_DataType", '"Number"'),
            ("INPID_InputControl", '"ColorControl"'),
            ("INP_Default", str(valor)),
            ("IC_ControlID", str(i)),
            ("IC_ControlGroup", str(grupo)),
            ("ICS_ControlPage", '"Controls"'),
            ("CLRC_NoSliders", "false"),
            ("IC_Visible", "true"),
            ("INP_Integer", "false"),
            ("INP_External", "false"),
            ("INP_Passive", "false"),
        ]
        if i == 0:
            campos.insert(0, ("LINKS_Name", f'"{rotulo}"'))
            campos.insert(4, ("CLRC_ShowWheel", "true"))
        out.append(_uc(f"{prefixo}Color{canal}", campos))
    return "\n".join(out)


# O corpo do botao "Apply Style" - o UNICO caminho de aplicacao pelo Inspector.
#
# `nil` nos settings porque cada controle ja guardou o proprio valor ao ser
# mexido; o que falta e' propagar isso pro Text+, pro Follower1 e pro spline.
# "button" na origem: e' o que faz o SetInputValues rodar tambem o SetAnimations
# e o que faz o spline ser refeito - num elemento ANIMADO a cor mora no
# keyframe, entao sem refazer o array o seletor de cor nao muda um pixel.
#
# `gi_chunk` em vez de `tool:GetData`: o `tool` que chega aqui e' o Text+, e o
# codigo mora no MacroOperator. Era esse o "nothing was applied".
#
# A linha de cabecalho existe pro log ficar legivel: um clique = um bloco que
# comeca em `--- Apply Style HH:MM:SS ---`.
_APLICAR_AGORA = """
local function gi_chunk(comp, tool, nome)
	local v
	pcall(function() v = tool and tool:GetData(nome) end)
	if v ~= nil then return v end
	local c = comp
	if c == nil and tool then pcall(function() c = tool.Comp end) end
	local tools
	pcall(function() tools = c:GetToolList(false) end)
	for _, t in pairs(tools or {}) do
		pcall(function() v = t:GetData(nome) end)
		if v ~= nil then return v end
	end
	return nil
end

local quando = ""
pcall(function() quando = " " .. os.date("%H:%M:%S") end)
print("[GiAutoSubs] --- Apply Style" .. quando .. " ---")

local f = gi_chunk(comp, tool, "SetInputValues")
if f then
	loadstring(f)()(comp, tool, nil, "button")
else
	print("[GiAutoSubs] Apply Style: no tool in this comp owns SetInputValues - "
		.. "the clip carries an old copy of the macro (see MACRO_VERSAO)")
end
"""




# Onde o botao "Generate Caption Style" grava o estilo exportado. Formato
# `chave<TAB>valor`, uma por linha - nao JSON.
#
# A montagem do JSON aninhado fica no Python (`estilo_de_controles`), que ja
# sabe a forma do estilos.json e ja tem teste de ida-e-volta. Escrever JSON a
# mao em Lua, dentro de um chunk que ja mora num `[[ ]]`, seria a terceira
# copia da mesma regra - e a que ninguem conseguiria testar sem abrir o Resolve.
ESTILO_EXPORTADO = r"D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_giestilo.txt"


# O unico chunk do projeto que sai do proprio clipe.
#
# Que isso e' possivel nao foi deduzido: o `GetTimelineItem` do proprio AutoSubs
# ja faz a mesma cadeia de tentativas pra alcancar o Resolve de dentro de um
# callback do Inspector. A cadeia tem quatro tentativas porque de onde o objeto
# vem depende de como o Fusion foi carregado, e nenhuma serve sozinha.
#
# A ARMADILHA (a mesma que custou o "Apply Style: nothing was applied"): cada
# clipe carrega a PROPRIA copia do macro. O chunk `SetInputValues` do clipe A
# nao serve pro clipe B - ele fecharia sobre o comp errado. Por isso o laco
# procura o dono do chunk DENTRO de cada comp, um por um.
_APLICAR_EM_TODAS = """
__LOG_LUA__

-- Um corpo so', dois botoes: `__SO_ESTA_TRACK__` vira true no "Apply Style to
-- This Track" e false no "to All Captions" (ver controles_topo). Dois corpos
-- seriam duas copias da mesma regra pra divergir.
local SO_ESTA_TRACK = __SO_ESTA_TRACK__
local ROTULO = SO_ESTA_TRACK and "Apply Style to This Track"
	or "Apply Style to All Captions"

local macro = gi_macro(comp, tool)
if not macro then
	diga("[GiAutoSubs] " .. ROTULO .. ":this clip has no InputKeys - it carries an "
		.. "old copy of the macro, so there is no style to copy FROM")
	return
end

-- CARACTERES POR CAIXA MUDOU? Entao isto nao e' trabalho de estilo.
--
-- Mudar o `Characters per Box` da aba Meta muda como as frases sao REPARTIDAS,
-- e com isso o numero de legendas (156 a 19 caracteres, 191 a 25). Restilizar os
-- clipes que existem nao produz os que faltam: e' preciso gerar o `legendas.lua`
-- de novo e recriar. E' o `GiRebuild` que faz isso, e este botao so' reconhece
-- que e' ele que foi pedido.
--
-- `GiCharsBuilt` e' o carimbo do que o arquivo LINKADO usou - `SetData` e nao
-- controle, porque e' registro do passado e nao escolha: um controle a mais no
-- Inspector convidaria a mexer justamente no numero que nao se mexe.
--
-- So' no "This Track": o outro botao alcanca a timeline inteira, onde
-- convivem cortes de legendas diferentes, e reconstruir a partir de um clipe
-- levaria a procedencia dele pra cima de todos.
if SO_ESTA_TRACK then
	local pedidos, feitos = 0, 0
	pcall(function() pedidos = math.floor(tonumber(macro:GetInput("MetaCharsPerBox")) or 0) end)
	pcall(function() feitos = math.floor(tonumber(macro:GetData("GiCharsBuilt")) or 0) end)
	if pedidos > 0 and feitos > 0 and pedidos ~= feitos then
		diga(string.format("[GiAutoSubs] %s: Characters per Box went from %d to "
			.. "%d - that changes how many captions there ARE, so restyling them "
			.. "cannot do it. Preparing the rebuild instead.", ROTULO, feitos,
			pedidos))
		local f = gi_chunk(comp, tool, "GiRebuild")
		if f then
			loadstring(f)()(comp, tool, ROTULO)
		else
			diga("[GiAutoSubs] " .. ROTULO .. ": no tool in this comp owns "
				.. "GiRebuild - the clip carries an old copy of the macro")
		end
		return
	end
end

-- O estilo sai pelo mesmo contrato que o script usa. Nada de montar a tabela a
-- mao aqui: `InputKeys` E' o schema, e uma segunda lista divergiria calada.
local preset
do
	local f = macro:GetData("GetInputValues")
	if f then
		local ok, r = pcall(function() return loadstring(f)()(macro) end)
		if ok then preset = r end
	end
end
if not preset or next(preset) == nil then
	diga("[GiAutoSubs] " .. ROTULO .. ":could not read this clip's style "
		.. "(GetInputValues came back empty) - nothing was applied")
	return
end

-- SetAnimations custa caro e so' tem o que fazer se alguma animacao estiver
-- ligada. Com tudo desligado (o padrao desde o macro 19) o "script" basta, e
-- 128 legendas deixam de pagar por uma reconstrucao de spline que nao muda
-- nada. Ligou o fade e mandou aplicar em todas? Ai o botao paga.
local anima = (preset.FadeEnabled == 1) or (preset.PopInEnabled == 1)
	or (preset.SlideUpEnabled == 1)
local origem = anima and "button" or "script"

local resolve = _G.resolve
	or (fusion and fusion.GetResolve and fusion:GetResolve())
	or (app and app.GetResolve and app:GetResolve())
	or (bmd and bmd.scriptapp and bmd.scriptapp("Resolve"))
	or (comp:GetApp() and comp:GetApp():GetResolve())

if type(resolve) ~= "userdata" and type(resolve) ~= "table" then
	diga("[GiAutoSubs] " .. ROTULO .. ":could not reach Resolve from inside the "
		.. "macro. This needs Resolve Studio (or the scripting API enabled).")
	return
end

local timeline
pcall(function()
	timeline = resolve:GetProjectManager():GetCurrentProject():GetCurrentTimeline()
end)
if not timeline then
	diga("[GiAutoSubs] " .. ROTULO .. ":no timeline open.")
	return
end

local total, aplicados, velhos, pulados, erros = 0, 0, 0, 0, 0
local trilhas = timeline:GetTrackCount("video") or 0
local primeira, ultima = 1, trilhas

if SO_ESTA_TRACK then
	-- A track do clipe clicado. Primeiro pelo proprio comp - a mesma igualdade
	-- `c2 == comp` que o laco de baixo usa pra pular a fonte. Se ela nao valer,
	-- pelo frame de inicio: num efeito de Edit page o COMPN_GlobalStart e' o
	-- inicio do clipe na timeline (verificado 2026-09-08). Duas legendas
	-- comecando no mesmo frame em tracks diferentes e' ambiguo - para, em vez
	-- de chutar uma track e restilizar a pessoa errada.
	local achada, inicio, porInicio = nil, nil, {}
	pcall(function() inicio = comp:GetAttrs().COMPN_GlobalStart end)
	for trilha = 1, trilhas do
		local itens
		pcall(function() itens = timeline:GetItemListInTrack("video", trilha) end)
		for _, item in ipairs(itens or {}) do
			pcall(function()
				if (item:GetFusionCompCount() or 0) < 1 then return end
				local c2 = item:GetFusionCompByIndex(1)
				if not c2 or not c2:FindTool("Template") then return end
				if c2 == comp and not achada then achada = trilha end
				if inicio and math.floor(item:GetStart() + 0.5)
						== math.floor(inicio + 0.5) then
					porInicio[#porInicio + 1] = trilha
				end
			end)
		end
	end
	if not achada and #porInicio == 1 then achada = porInicio[1] end
	if not achada then
		diga("[GiAutoSubs] " .. ROTULO .. ": could not tell which track this "
			.. "clip is on" .. (#porInicio > 1 and (" (" .. #porInicio
			.. " captions start on the same frame)") or "")
			.. " - nothing was applied")
		return
	end
	primeira, ultima = achada, achada
end

diga("[GiAutoSubs] ===== " .. ROTULO .. " =====")
diga("[GiAutoSubs] source clip: macro version "
	.. tostring(preset.GiAutoSubsVersao or "?")
	.. "  |  animations " .. (anima and "ON (SetAnimations will run)" or "off")
	.. "  |  " .. tostring(origem))
if SO_ESTA_TRACK then
	diga("[GiAutoSubs] only video track " .. primeira)
end

for trilha = ultima, primeira, -1 do
	local itens
	pcall(function() itens = timeline:GetItemListInTrack("video", trilha) end)
	for _, item in ipairs(itens or {}) do
		pcall(function()
			if (item:GetFusionCompCount() or 0) < 1 then return end
			local c2 = item:GetFusionCompByIndex(1)
			if not c2 then return end

			local t2 = c2:FindTool("Template")
			if not t2 then return end
			total = total + 1

			-- O proprio clipe ja esta com o estilo - ele E' a fonte.
			if c2 == comp then pulados = pulados + 1 return end

			local f = gi_chunk(c2, nil, "SetInputValues")
			if not f then
				velhos = velhos + 1
				return
			end

			-- `t2` (o Text+) e NAO o macro: o SetInputValues escreve em
			-- { tool, gi_macro(tool) }. Passando o macro como `tool`, os dois
			-- alvos viram o mesmo e a escrita PULA o Text+ - que e' quem desenha.
			local ok, erro = pcall(function()
				loadstring(f)()(c2, t2, preset, origem, nil)
			end)
			if ok then
				aplicados = aplicados + 1
			else
				erros = erros + 1
				diga("[GiAutoSubs]   FAILED on one clip: " .. tostring(erro))
			end
		end)
	end
end

diga(string.format("[GiAutoSubs] %d caption(s) found | %d styled | %d skipped "
	.. "(the source) | %d with an old macro copy | %d failed",
	total, aplicados, pulados, velhos, erros))
if velhos > 0 then
	diga("[GiAutoSubs] the clips with an old copy cannot be reached from here - "
		.. "recreate them with the script so they carry the current macro.")
end
diga("[GiAutoSubs] ===== done =====")
"""


# Exporta o estilo DESTE clipe pro disco. Um corpo so', dois destinos:
#
#   "Export Config"          -> `presets\\<nome>.txt`, o que o GiAutoSubs.lua
#                               oferece quando pergunta qual configuracao usar
#   "Generate Caption Style" -> o dump fixo que o `--importar-estilo` transforma
#                               num estilo nomeado do estilos.json
#
# O formato e' o mesmo `chave<TAB>valor` nos dois, e o leitor tambem
# (`ler_estilo_exportado`): duas serializacoes do mesmo estilo seriam duas
# chances de divergir - e a que divergisse seria a que ninguem confere.
#
# Le pelo `GetInputValues`, o mesmo par que o script usa: assim o que sai daqui
# e' exatamente o que entra la, e um controle novo aparece no dump sozinho por
# estar no `InputKeys` - sem lista pra manter em dia.
_EXPORTAR = """
__LOG_LUA__

local macro = gi_macro(comp, tool)
local template = comp:FindTool("Template") or tool
if not macro then
	diga("[GiAutoSubs] __ROTULO__: this clip has no InputKeys - it carries "
		.. "an old copy of the macro. Recreate it with the script first.")
	return
end

local valores = {}
do
	local f = macro:GetData("GetInputValues")
	if f then
		local ok, r = pcall(function() return loadstring(f)()(macro) end)
		if ok then valores = r or {} end
	end
end
if next(valores) == nil then
	diga("[GiAutoSubs] __ROTULO__: GetInputValues came back empty - "
		.. "nothing was exported.")
	return
end

-- Inputs que o estilo precisa e o `InputKeys` NAO carrega: a suavidade do
-- outline e a sombra do texto inteira (opacidade, suavidade, deslocamento).
-- Sem eles o estilo exportado voltaria pros padroes do codigo nesses campos e
-- nao renderizaria igual ao clipe de onde saiu.
local EXTRAS = { "Softness2", "Offset2", "Opacity3", "Softness3", "Offset3" }
local extras = {}
for _, chave in ipairs(EXTRAS) do
	local v
	pcall(function() v = template:GetInput(chave) end)
	if v ~= nil then extras[chave] = v end
end
pcall(function() extras.TextPosition = template:GetInput("Center") end)

-- O NOME, por dialogo NATIVO do sistema.
--
-- Era um `comp:AskUser` - e o AskUser nao tem parametro de posicao: quem coloca a
-- janela e' o Fusion, e ela sai fora do lugar (relatado pelo usuario). Nao ha' API
-- pra centraliza-la.
--
-- O `fusion:RequestFile` e' a caixa de arquivo do sistema: centralizada, lembra a
-- pasta, e e' o mesmo dialogo que o GiAutoSubs.lua usa nas quatro perguntas dele -
-- pela regra que o proprio projeto escreveu, o AskUser "existe como atributo e vem
-- nil" fora da pagina Fusion, que e' o caso normal aqui.
--
-- O nome e' o NOME DO ARQUIVO escolhido, sem a extensao. Para o Export Config o
-- caminho escolhido e' o proprio destino, entao da' pra salvar em outra pasta ou
-- sobrescrever um preset existente vendo a lista - o que um campo de texto nao
-- oferece. Cancelar continua caindo no carimbo de hora (ver o destino abaixo).
--
-- `FReqB_Saving` pede a caixa de SALVAR. Se esta versao do Fusion nao conhecer o
-- atributo, ela abre como caixa de abrir - e ai escolher um preset existente
-- ainda funciona, e cancelar cai no carimbo de hora. Degradado, nao quebrado.
local nome, escolhido
pcall(function()
	if not (fusion and fusion.RequestFile) then return end
	local caminho = fusion:RequestFile("__PASTA__", "__SUGESTAO__", {
		FReqB_SeqGather = false,
		FReqB_Saving = true,
		FReqS_Title = "__ROTULO__ - __CAMPO__",
		FReqS_Filter = "GiAutoSubs config (*.txt)|*.txt",
	})
	if caminho and caminho ~= "" then
		escolhido = caminho
		-- Quatro barras: este trecho atravessa o parser do Python (a string do
		-- gerador) e depois o do Lua. Duas chegariam ao Lua como `\/`, que e um
		-- escape invalido - o macro inteiro para de compilar (armadilha do macro 25).
		nome = caminho:match("([^\\\\/]+)$")
		if nome then nome = (nome:gsub("%.[^.]*$", "")) end
	end
end)
if nome then
	nome = nome:gsub("^%s+", ""):gsub("%s+$", "")
	if nome == "" then nome = nil end
end
local semNome = (nome == nil)

local function num(v)
	if type(v) == "table" then
		local partes = {}
		for i = 1, 4 do
			if v[i] == nil then break end
			partes[#partes + 1] = string.format("%.10g", v[i])
		end
		return "{" .. table.concat(partes, ",") .. "}"
	elseif type(v) == "number" then
		return string.format("%.10g", v)
	end
	return tostring(v)
end

local linhas = {}
if nome and nome ~= "" then
	linhas[#linhas + 1] = "#nome\\t" .. nome
end
linhas[#linhas + 1] = "#versao\\t" .. tostring(valores.GiAutoSubsVersao or "?")

-- Ordenado pra o arquivo ser comparavel entre duas exportacoes: um diff que
-- muda de ordem sozinho nao serve pra ver o que mudou de verdade.
local chaves = {}
for k in pairs(valores) do chaves[#chaves + 1] = k end
for k in pairs(extras) do chaves[#chaves + 1] = k end
table.sort(chaves)

local fonte = {}
for k, v in pairs(valores) do fonte[k] = v end
for k, v in pairs(extras) do fonte[k] = v end
for _, k in ipairs(chaves) do
	linhas[#linhas + 1] = k .. "\\t" .. num(fonte[k])
end

__DESTINO__

local escrito = false
pcall(function()
	local fh = io.open(destino, "w")
	if not fh then return end
	fh:write(table.concat(linhas, "\\n"), "\\n")
	fh:close()
	escrito = true
end)

if not escrito then
	diga("[GiAutoSubs] __ROTULO__: could not write " .. destino)
	return
end

diga("[GiAutoSubs] ===== __ROTULO__ =====")
diga("[GiAutoSubs] " .. (#chaves) .. " values written to " .. destino)
__FECHO__
"""


# O destino do "Export Config": um preset nomeado na pasta que a rodada le.
#
# Sem o dialogo (a pagina Edit nao o oferece) o preset sai carimbado com a hora
# em vez de nao sair: um arquivo com nome feio da' pra renomear, uma exportacao
# recusada custa o ajuste inteiro de novo. `bmd.createdir` porque `io.open`
# numa pasta que nao existe falha calado.
_DESTINO_PRESET = """
-- O caminho que voce escolheu na caixa E' o destino: foi voce quem apontou a
-- pasta e o nome, e reconstruir o caminho a partir do nome jogaria a sua escolha
-- fora (salvar num pendrive, por exemplo).
--
-- Sem escolha (cancelou, ou o dialogo nao existe nesta forma de rodar) o preset
-- sai carimbado com a hora, na pasta que a rodada le. Um arquivo com nome feio
-- da' pra renomear; uma exportacao recusada custa o ajuste inteiro de novo.
-- `bmd.createdir` porque `io.open` numa pasta que nao existe falha calado.
local destino
if escolhido then
	destino = escolhido
	if not destino:lower():match("%.txt$") then destino = destino .. ".txt" end
else
	nome = "preset-" .. os.date("%Y%m%d-%H%M%S")
	pcall(function() bmd.createdir("__PRESETS__") end)
	destino = "__PRESETS__" .. "\\\\" .. nome .. ".txt"
end
"""

_FECHO_PRESET = """
diga("[GiAutoSubs] the next GiAutoSubs run offers this file when it asks which "
	.. "caption config to use.")
if semNome then
	diga("[GiAutoSubs] no name was given (the Fusion dialog is not available "
		.. "from the Edit page - that is expected), so the file carries the "
		.. "time instead. Rename it to something you will recognise.")
end
"""

_DESTINO_ESTILO = """
local destino = "__ESTILO__"
"""

_FECHO_ESTILO = """
if nome then
	diga("[GiAutoSubs] style name: " .. nome)
	diga("[GiAutoSubs] now run, in PowerShell:")
	diga("[GiAutoSubs]   gerar_macro.py --importar-estilo --instalar")
else
	diga("[GiAutoSubs] no name was given (the Fusion dialog is not available "
		.. "from this page - that is expected on the Edit page).")
	diga("[GiAutoSubs] now run, in PowerShell, choosing the name there:")
	diga("[GiAutoSubs]   gerar_macro.py --importar-estilo --nome <name> --instalar")
end
diga("[GiAutoSubs] that writes the style into estilos.json and builds a Title "
	.. "of its own in Templates/Edit/Titles.")
"""


def _exportar(rotulo, campo, destino, fecho, pasta, sugestao):
    """Monta o corpo de um dos dois botoes de exportar.

    `pasta` e `sugestao` sao onde a caixa de arquivo abre e com que nome ela abre -
    o dialogo nativo substituiu o AskUser (que nao da' pra posicionar na tela).
    """
    return (_com_log(_EXPORTAR)
            .replace("__DESTINO__", destino.strip("\n"))
            .replace("__FECHO__", fecho.strip("\n"))
            .replace("__ROTULO__", rotulo)
            .replace("__CAMPO__", campo)
            .replace("__PASTA__", pasta.replace("\\", "\\\\"))
            .replace("__SUGESTAO__", sugestao))


def _exportar_config():
    return _exportar("Export Config", "Config name",
                     _DESTINO_PRESET.replace("__PRESETS__",
                                             PRESETS_DIR.replace("\\", "\\\\")),
                     _FECHO_PRESET,
                     PRESETS_DIR + "\\", "meu-preset.txt")


def _exportar_estilo():
    # A caixa abre na pasta dos presets tambem, mas aqui ela serve so' pra COLHER
    # O NOME: o dump vai pro arquivo fixo que o `--importar-estilo` le. Salvar o
    # dump onde o usuario aponta seria um segundo lugar pra ele procurar depois.
    return _exportar("Generate Caption Style", "Style name",
                     _DESTINO_ESTILO.replace(
                         "__ESTILO__", ESTILO_EXPORTADO.replace("\\", "\\\\")),
                     _FECHO_ESTILO,
                     PRESETS_DIR + "\\", "meu-estilo.txt")


# O callback do PREVIEW. Um so', em tres controles.
#
# Ele existe contra a regra da casa ("nenhum controle reage sozinho", macro 11) e o
# validador cobra que sejam exatamente estes tres - a excecao e' nomeada pra nao
# virar porta aberta. O que a justifica: o macro 11 matou callbacks que disparavam
# ~40 vezes por arrasto CADA UM fazendo o trabalho inteiro (incluindo reconstruir o
# array por caractere) e enchendo o log. Este passa `spline = false` e o modo
# "so' a caixa": doze escritas de geometria, zero por frame, zero linha de log.
#
# `gi_chunk` e nao `tool:GetData`: o `tool` que o Fusion entrega ao callback e' o
# Text+ interno, e o codigo mora no MacroOperator (a mesma razao do botao).
_PREVIEW_CAIXA = """
__LOG_LUA__
local f = gi_chunk(comp, tool, "ApplyGiStyle")
if f then
	loadstring(f)()(comp, tool, "preview", false, true)
elseif not _G.GI_PREVIEW_AVISADO then
	-- UMA vez por sessao: um arrasto de slider num clipe velho imprimiria isto
	-- quarenta vezes, e log repetido e' log que ninguem le.
	_G.GI_PREVIEW_AVISADO = true
	diga("[GiAutoSubs] live preview: no tool in this comp owns ApplyGiStyle - "
		.. "this clip carries an old copy of the macro, so the box only updates "
		.. "when you click Apply Style")
end
"""

# Os controles que reagem sozinhos - a lista COMPLETA, e ela e' o contrato com o
# validador. Os tres sao os que mudam o TAMANHO da caixa fixa, que e' o que nao da'
# pra acertar sem ver na tela.
CALLBACK_PREVIEW = ("TextBoxFixed", "TextBoxWidth", "TextBoxHeight")


def _injetar_preview(texto, contador):
    """Poe o `INPS_ExecuteOnChange` nos tres controles do preview.

    DEPOIS do `_desautomatizar`, de proposito: ele varre o macro e tira TODO
    callback (inclusive os do AutoSubs), e um callback inserido antes seria levado
    junto - calado, porque a remocao e' um regex que nao sabe o que era nosso.
    """
    corpo = _ind(_com_log(_PREVIEW_CAIXA), 7)
    n = 0
    for nome in CALLBACK_PREVIEW:
        bloco = _bloco(nome).search(texto)
        if not bloco:
            contador.append(f"WARNING: {nome} does not exist - the live preview "
                            f"callback was NOT installed on it")
            continue
        alvo = bloco.group(0)
        if "INPS_ExecuteOnChange" in alvo:
            continue
        ind = re.match(r"(\t+)", alvo).group(1)
        novo = alvo.rstrip()[:-len("},")].rstrip() + "\n"
        novo += f"{ind}\tINPS_ExecuteOnChange = [[\n{corpo}\n{ind}\t]],\n{ind}}},"
        texto = texto[:bloco.start()] + novo + texto[bloco.end():]
        n += 1
    contador.append(f"{n} live-preview callback(s) installed "
                    f"({', '.join(CALLBACK_PREVIEW)}) - the fixed box follows the "
                    f"slider without Apply Style; they write geometry only, so the "
                    f"cost per FRAME is zero")
    return texto


def _botao(nome, texto, corpo):
    """Botao do Inspector.

    A diferenca que importa: um botao executa `BTNCS_Execute`, NAO
    `INPS_ExecuteOnChange`. Um ButtonControl declarado com ExecuteOnChange
    aparece, clica, e nao faz nada - e o Fusion nao reclama. Isso e' lido do
    macro do AutoSubs (`UpdateAnimationButton`), nao deduzido.
    """
    linhas = [f"{nome} = {{",
              f'\tLINKS_Name = "{texto}",',
              '\tLINKID_DataType = "Number",',
              '\tINPID_InputControl = "ButtonControl",',
              "\tIC_NoLabel = false,",
              "\tIC_Visible = true,",
              "\tINP_External = false,",
              "\tINP_Passive = true,",
              "\tBTNCS_Execute = [[",
              _ind(corpo, 2),
              "\t]],",
              "},"]
    return "\n".join(linhas)


# A ORDEM destas strings E' o valor gravado em `Level{n}` - o indice na lista,
# a partir de ZERO. Esta e' a lista REAL do Text+, lida do PROPERTY DUMP dentro
# do Resolve (e coerente com o `ElementShape`, onde Border Fill = 2 e' o valor
# que de fato desenha a caixa).
#
# Estava errada desde sempre: `("Text+ default", "Character", "Word", "Line")`
# trocava Character com Line e inventava um "Text+ default" no lugar de "Text".
# "Word" acertava por coincidencia e era o unico que os estilos usavam - por
# isso atravessou 21 versoes. Corrigido no macro 22, junto com o `NIVEIS` do
# giautosubs.py: mudar so' um dos dois faz o Inspector e o script discordarem.
_NIVEIS = ("Text", "Line", "Word", "Character")


def controles():
    """UserControls novos, na ordem em que aparecem no Inspector.

    Cada `_rotulo` abre um grupo dobravel e engole os N controles seguintes -
    por isso a contagem tem que bater com o que vem logo abaixo dela.

    O grupo "Actions" nao esta aqui: ele e' o unico que precisa aparecer no TOPO
    do Inspector, acima dos controles do proprio AutoSubs, e por isso e' gerado
    a parte (`controles_topo`).
    """
    partes = [
        # A palavra falada. Vem antes da bolha porque e' o destaque mais
        # simples: pintar a palavra que esta sendo dita. A bolha e' a mesma
        # ideia com geometria em volta.
        _rotulo("WordFillLabel", "Spoken Word", 4),
        _checkbox("WordFillEnabled", "Enabled"),
        _cor("WordFill", "Word Color", GRUPO_PALAVRA, (1, 0.3, 0.65)),

        _rotulo("BubbleLabel", "Bubble", 9),
        _checkbox("BubbleEnabled", "Enabled"),
        _cor("Bubble", "Bubble Color", GRUPO_BOLHA, (1, 0.85, 0.3)),
        _slider("BubbleOpacity", "Opacity", 1, 0, 1),
        _combo("BubbleLevel", "Level", _NIVEIS, 2),
        _slider("BubbleExtendHorizontal", "Extend Horizontal", 0.15, -0.5, 2),
        _slider("BubbleExtendVertical", "Extend Vertical", 0.1, -0.5, 2),
        _slider("BubbleRound", "Round", 0.4, 0, 1),
        # O "pop" do CapCut: a bolha entra menor nos dois eixos e cresce ate o
        # tamanho normal. `Amount` esta na MESMA escala dos dois Extend acima -
        # 0.15 quer dizer "comeca 0.15 mais justa" - pra o numero significar a
        # mesma coisa que o slider de cima.
        _checkbox("BubblePopEnabled", "Pop"),
        _slider("BubblePopAmount", "Pop Amount", 0.15, 0, 0.5),
        _slider("BubblePopFrames", "Pop Frames", 3, 1, 15, inteiro=True),

        _rotulo("TextBoxLabel", "Text Box", 12),
        _checkbox("TextBoxEnabled", "Enabled"),
        # Logo abaixo do Enabled porque ele muda o SIGNIFICADO dos dois Extend
        # que vem depois: ligado, eles deixam de ser folga em volta do texto e
        # passam a ser o tamanho da caixa (ver `extend_h` no ApplyGiStyle).
        # O rotulo diz o que o controle FAZ porque um Inspector de macro nao tem
        # condicional: nao da' pra esconder nem cinzar o Extend conforme este
        # checkbox (dependia dos callbacks por controle, que sairam no macro 11).
        _checkbox("TextBoxFixed", "Fixed Box (Width/Height below)"),
        # ZERO = "nao pedi": ai a largura alvo volta a ser uma linha cheia de
        # `Characters per Box` (aba Meta). O teto de 4000 cobre 4K com folga; o
        # `INP_MaxAllowed` do `_slider` ja e' maior que qualquer tela.
        _slider("TextBoxWidth", "Width (px)", 0, 0, 4000, inteiro=True),
        _slider("TextBoxHeight", "Height (px)", 0, 0, 4000, inteiro=True),
        _cor("TextBox", "Text Box Color", GRUPO_CAIXA, (0, 0, 0)),
        _slider("TextBoxOpacity", "Opacity", 0.45, 0, 1),
        # 1 = Line. A caixa do texto envolve a LINHA; a bolha (elemento 4)
        # envolve a palavra falada, dai o 2 dela. Era 3 aqui, que na lista real
        # e' Character - uma caixa por letra.
        _combo("TextBoxLevel", "Level", _NIVEIS, 1),
        # "(free box)" no rotulo porque o Inspector nao consegue cinzar um controle
        # conforme outro (dependia dos callbacks que sairam no macro 11). Com o
        # `Fixed Box` ligado estes dois valem ZERO - quem decide o tamanho e'
        # Width/Height, e o rotulo e' o unico lugar onde isso da' pra avisar antes
        # do clique.
        _slider("TextBoxExtendHorizontal", "Extend Horizontal (free box)",
                0.2, -0.5, 2),
        _slider("TextBoxExtendVertical", "Extend Vertical (free box)",
                0.12, -0.5, 2),
        _slider("TextBoxRound", "Round", 0.25, 0, 1),

        _rotulo("BoxShadowLabel", "Box Shadow", 9),
        _checkbox("BoxShadowOnHighlight", "Shadow on Bubble"),
        _checkbox("BoxShadowOnNormal", "Shadow on Text Box"),
        _cor("BoxShadow", "Shadow Color", GRUPO_SOMBRA, (0, 0, 0)),
        _slider("BoxShadowCenterX", "Offset X", 0.005, -0.05, 0.05),
        _slider("BoxShadowCenterY", "Offset Y", -0.007, -0.05, 0.05),
        _slider("BoxShadowOpacity", "Opacity", 0.55, 0, 1),
        _slider("BoxShadowSoftness", "Softness", 2, 0, 10),
    ]
    # A terceira cor da caixa. Fica logo depois do Text Box porque e' a
    # mesma caixa: ela copia Level/Extend/Round de la' e so' escolhe a cor e
    # pra onde se desloca. Os dois Offset default vao pro lado OPOSTO ao da
    # Box Shadow (+0.005 / -0.007), que e' o que faz uma cor sair em cima e
    # a outra embaixo em vez de as duas empilharem no mesmo canto.
    #
    # A ORDEM aqui nao decide onde ele aparece: quem decide e' o LAYOUT.
    i = partes.index(_rotulo("BoxShadowLabel", "Box Shadow", 9))
    partes[i:i] = [
        _rotulo("BoxLayer3Label", "Box Layer 3", 7),
        _checkbox("BoxLayer3Enabled", "Enabled"),
        _cor("BoxLayer3", "Layer 3 Color", GRUPO_CAMADA3, (1, 0.3, 0.65)),
        _slider("BoxLayer3CenterX", "Offset X", -0.005, -0.05, 0.05),
        _slider("BoxLayer3CenterY", "Offset Y", 0.007, -0.05, 0.05),
        # Alpha e nao Opacity: `Opacity8` fica livre porque e' por onde o
        # fade entraria (ver `camada3` no ApplyGiStyle).
        _slider("BoxLayer3Alpha", "Alpha", 1, 0, 1),
    ]
    # GRAUS POR FRAME, e o default e' ZERO: enquanto o spin era um Title
    # proprio, escolher aquele Title JA' era pedir o giro, e o default 2 fazia
    # sentido. No macro universal todo mundo nasce com este controle, e uma
    # legenda que comeca girando sem ninguem pedir seria o macro decidindo
    # estilo no lugar do usuario. Em 0, `deslocar` cai em `pin` e nenhuma
    # expressao e' escrita - e' a caixa parada, byte a byte.
    #
    # 2 continua sendo o valor bom pra experimentar: a 30fps da' uma volta a
    # cada 6 segundos, lento o bastante pra ler como movimento intencional. A
    # legenda fica 1 a 3 segundos na tela, entao cada uma mostra meia volta ou
    # menos e o olho le deriva suave em vez de rodopio. Acima de ~6 vira
    # estroboscopio e o texto cansa de ler no volume que este projeto produz -
    # dai o teto em 10 em vez de 360.
    i = partes.index(_slider("BoxLayer3Alpha", "Alpha", 1, 0, 1))
    partes.insert(i + 1,
                  _slider("BoxSpinSpeed", "Spin Speed", 0, 0, 10))
    return "\n".join(partes)


def controles_texto():
    """O que entra DENTRO do grupo "Text" do AutoSubs, junto de Font e Style.

    Um combo de tres estados, nao dois checkboxes: com checkboxes existe o
    estado "os dois marcados", que nao quer dizer nada e obriga alguem a decidir
    quem ganha. Aqui o estado invalido nao e' expressavel, e o padrao ("As
    typed") diz por escrito que nao mexe em nada - dois checkboxes desmarcados
    dizem isso por ausencia.
    """
    # "Camel Case" e' o nome que o USUARIO da' a isso (tecnicamente e' title
    # case; camelCase de programador nao tem espaco). Fica o nome dele: e' o que
    # ele vai procurar no Inspector.
    return _combo("TextCase", "Case",
                  ("As typed", "lowercase", "UPPERCASE", "Camel Case"), 0)


def controles_fim():
    """O grupo "Config", que fecha o Inspector.

    Fica no fim de propÃ³sito: nao e' um controle de estilo, e' uma ferramenta -
    voce nao passa por ele ajustando uma legenda, voce vai ate' ele quando quer
    guardar ou mandar a configuracao.

    Aqui morava o "Display Config", que imprimia o estilo no Console. Ler nao
    era o que faltava: o que faltava era o ajuste do Inspector VOLTAR pra
    rodada. O botao exporta, e a proxima rodada oferece o arquivo.
    """
    return "\n".join([
        _rotulo("ConfigLabel", "Config", 1),
        _botao("ExportConfig", "Export Config", _exportar_config()),
    ])


def controles_meta():
    """A aba "Meta": a PONTE entre o clipe e o giautosubs.py.

    As outras duas abas descrevem como a legenda e' desenhada. Esta descreve de
    onde ela VEIO - qual `legendas.lua` esta linkado, de qual corte, com qual
    estilo, qual Title, qual preset, e com quantos caracteres por caixa ela foi
    repartida. Antes isso nao morava em lugar nenhum: o clipe na timeline nao
    sabia de que arquivo tinha nascido, e a unica forma de descobrir era abrir os
    candidatos e comparar o texto.

    Os campos sao EDITAVEIS de proposito. `Characters per Box` e' o unico que faz
    algo ao mudar (ver `GiRebuild`); os caminhos sao editaveis porque relinkar na
    mao e' a saida quando a ponte nao esta disponivel - outra maquina, outro
    caminho, o Python fora do lugar.

    `Char Width` fica aqui e nao no grupo Text Box, embora seja a caixa fixa que
    o use: ele e' a mesma regua dos caracteres por caixa, em unidade de Extend.
    Os dois juntos sao o que traduz "19 caracteres" em largura de caixa.
    """
    return "\n".join([
        _rotulo("MetaLabel", "Meta", 14),
        _texto("MetaCaptionsFile", "Captions File"),
        _texto("MetaCutFolder", "Cut Folder"),
        _texto("MetaTranscript", "Transcript"),
        _texto("MetaStyle", "Style"),
        _texto("MetaStylesFile", "Styles File"),
        _texto("MetaTitle", "Title"),
        _texto("MetaConfig", "Config"),
        _slider("MetaCharsPerBox", "Characters per Box", 19, 5, 60, inteiro=True),
        _slider("MetaLines", "Lines", 1, 1, 3, inteiro=True),
        _slider("MetaCharWidth", "Char Width", 0.5, 0, 2),
        # A outra regua: quantos PIXELS vale uma unidade de Extend. 0 = estimar
        # (`Size` x altura do frame). Fica aqui e nao no Text Box porque e' da
        # mesma familia do `Char Width`: as duas traduzem o que voce pede pro que
        # o Text+ entende, e as duas se corrigem olhando a tela.
        _slider("MetaPxPorUnidade", "Px per Unit (0 = auto)", 0, 0, 500),
        # As OPCOES da reconstrucao, e o submit abaixo delas.
        #
        # Sem buracos: cada legenda dura ate' a proxima entrar. E' o par da
        # largura fixa - a caixa parada de que serve se ela PISCA entre duas
        # legendas? Controle proprio porque nao existe equivalente no estilo: uma
        # estica o espaco, a outra o tempo.
        #
        # A largura fixa NAO ganha controle aqui: ela e' o `TextBoxFixed` do grupo
        # Text Box, exposto de novo nesta aba (ver `META_INSTANCIAS`).
        _checkbox("MetaNoGaps", "No Gaps"),
        _botao("MetaRebuild", "Rebuild with Selected",
               _com_log(_BOTAO_RECONSTRUIR)),
    ])


def controles_topo():
    """O grupo "Actions", que abre o Inspector.

    Nenhum controle aplica sozinho, entao o botao e' o passo final de qualquer
    ajuste - e um passo que se da' o tempo todo nao pode morar no fim de uma
    lista de 40 controles, com rolagem no meio. Grupo proprio porque um
    LabelControl engole os N controles seguintes: solto, o botao entraria no
    primeiro grupo do AutoSubs.
    """
    return "\n".join([
        _rotulo("ApplyStyleLabel", "Actions", 4),
        _botao("ApplyStyle", "Apply Style", _APLICAR_AGORA),
        # A ordem e' de alcance crescente: este clipe, a track dele, depois a
        # timeline inteira, depois o disco. O botao mais destrutivo nao pode
        # ser o primeiro que a mao encontra.
        _botao("ApplyStyleTrack", "Apply Style to This Track",
               _com_log(_APLICAR_EM_TODAS.replace("__SO_ESTA_TRACK__", "true"))),
        _botao("ApplyStyleAll", "Apply Style to All Captions",
               _com_log(_APLICAR_EM_TODAS.replace("__SO_ESTA_TRACK__", "false"))),
        _botao("GenerateStyle", "Generate Caption Style", _exportar_estilo()),
    ])


# Os InstanceInput do grupo Actions. Vao pro COMECO do bloco `Inputs` do macro -
# e' o que poe o botao no topo do Inspector do clipe.
NOVOS_TOPO = [
    ("ApplyStyleLabel", None, None),
    ("ApplyStyle", None, None),
    ("ApplyStyleTrack", None, None),
    ("ApplyStyleAll", None, None),
    ("GenerateStyle", None, None),
]

# Vai DENTRO do grupo "Text", logo depois de `Style` (o peso da fonte).
#
# Caixa das letras e' tipografia, irma de Font/Style/Size - nao e' cor, nao e'
# animacao, e nao merece grupo proprio. Quem quer "tudo em maiusculas" procura
# onde escolheu a fonte, que e' onde qualquer editor poe isso.
NOVOS_TEXTO = [
    ("TextCase", "Case", None),
]

# Um "Apply Style" no RODAPE de cada grupo de atributos.
#
# Nenhum controle reage sozinho desde a versao 11, entao todo ajuste termina num
# clique - e o clique estava a uma rolagem de distancia do controle que acabou de
# ser mexido. Repetir o botao no fim de cada grupo e' a resposta pedida: voce
# ajusta a bolha e aplica ali mesmo, sem procurar.
#
# Sao INSTANCIAS do mesmo `ApplyStyle`, nao botoes novos: um `InstanceInput` pode
# apontar pro UserControl que quiser (`Source`), e o proprio macro do AutoSubs
# documenta isso ("use distinct instance names only when exposing the same
# control in different pages/groups/roles"). Um segundo BOTAO seria um segundo
# corpo de codigo pra divergir do primeiro.
#
# So' o `Apply Style`. `Apply Style to All Captions` e `Generate Caption Style`
# ficam num lugar so' (o grupo Actions do topo): repetir um botao que mexe em
# TODAS as legendas em nove lugares e' pedir pra ele ser clicado sem querer.
RODAPES = [
    ("ApplyStyleText", "SubtitleLabel"),
    ("ApplyStyleAnimation", "AnimationLabel"),
    ("ApplyStyleFill", "FillLabel"),
    ("ApplyStyleOutline", "OutlineLabel"),
    ("ApplyStyleTextBox", "TextBoxLabel"),
    ("ApplyStyleBoxLayer3", "BoxLayer3Label"),
    ("ApplyStyleBubble", "BubbleLabel"),
    ("ApplyStyleWordFill", "WordFillLabel"),
    ("ApplyStyleBoxShadow", "BoxShadowLabel"),
    ("ApplyStyleShadow", "ShadowLabel"),
]

# Os controles da aba Meta. Lista propria porque eles sao a unica parte do
# Inspector que NAO e' estilo: nenhum deles viaja no preset (ver
# `_FORA_DO_PRESET`), e quem os escreve e' o `GiAutoSubs.lua` a cada rodada, do
# `dados.meta` do legendas.lua - nao o `SetInputValues`.
#
# Se eles entrassem no `InputKeys`, o "Apply Style to All Captions" carimbaria o
# caminho do clipe de origem em cima de todos os outros, e o "Export Config"
# gravaria caminhos de maquina dentro de um preset de estilo.
NOVOS_META = [
    ("MetaLabel", None, None),
    ("MetaCaptionsFile", None, None),
    ("MetaCutFolder", None, None),
    ("MetaTranscript", None, None),
    ("MetaStyle", None, None),
    ("MetaStylesFile", None, None),
    ("MetaTitle", None, None),
    ("MetaConfig", None, None),
    ("MetaCharsPerBox", None, None),
    ("MetaLines", None, None),
    ("MetaCharWidth", None, None),
    ("MetaPxPorUnidade", None, None),
    ("MetaNoGaps", "No Gaps", None),
    ("MetaRebuild", None, None),
]

# A largura fixa aparece DUAS vezes no Inspector: no grupo Text Box (onde ela e'
# geometria) e na aba Meta (onde ela e' opcao da reconstrucao). Um `InstanceInput`
# pode apontar pro UserControl que quiser, e e' assim que os nove `Apply Style` de
# rodape sao o mesmo botao - um controle proprio aqui seria uma segunda verdade
# sobre a mesma coisa, livre pra discordar.
#
# (nome da instancia, UserControl de origem, rotulo)
META_INSTANCIAS = [
    ("MetaFixedWidth", "TextBoxFixed", "Fixed Width"),
]

# Ordem identica a de `controles()` - InstanceInput fora de ordem quebra o
# agrupamento dos LabelControl no Inspector do clipe.
NOVOS = [
    ("WordFillLabel", None, None),
    ("WordFillEnabled", "Enabled", None),
    ("WordFillColorRed", "Word Color", GRUPO_PALAVRA + 100),
    ("WordFillColorGreen", None, GRUPO_PALAVRA + 100),
    ("WordFillColorBlue", None, GRUPO_PALAVRA + 100),

    ("BubbleLabel", None, None),
    ("BubbleEnabled", "Enabled", None),
    ("BubbleColorRed", "Bubble Color", GRUPO_BOLHA + 100),
    ("BubbleColorGreen", None, GRUPO_BOLHA + 100),
    ("BubbleColorBlue", None, GRUPO_BOLHA + 100),
    ("BubbleOpacity", None, None),
    ("BubbleLevel", None, None),
    ("BubbleExtendHorizontal", None, None),
    ("BubbleExtendVertical", None, None),
    ("BubbleRound", None, None),
    ("BubblePopEnabled", "Pop", None),
    ("BubblePopAmount", None, None),
    ("BubblePopFrames", None, None),

    ("TextBoxLabel", None, None),
    ("TextBoxEnabled", "Enabled", None),
    ("TextBoxFixed", "Fixed Box", None),
    ("TextBoxWidth", None, None),
    ("TextBoxHeight", None, None),
    ("TextBoxColorRed", "Text Box Color", GRUPO_CAIXA + 100),
    ("TextBoxColorGreen", None, GRUPO_CAIXA + 100),
    ("TextBoxColorBlue", None, GRUPO_CAIXA + 100),
    ("TextBoxOpacity", None, None),
    ("TextBoxLevel", None, None),
    ("TextBoxExtendHorizontal", None, None),
    ("TextBoxExtendVertical", None, None),
    ("TextBoxRound", None, None),

    ("BoxLayer3Label", None, None),
    ("BoxLayer3Enabled", "Enabled", None),
    ("BoxLayer3ColorRed", "Layer 3 Color", GRUPO_CAMADA3 + 100),
    ("BoxLayer3ColorGreen", None, GRUPO_CAMADA3 + 100),
    ("BoxLayer3ColorBlue", None, GRUPO_CAMADA3 + 100),
    ("BoxLayer3CenterX", None, None),
    ("BoxLayer3CenterY", None, None),
    ("BoxLayer3Alpha", None, None),
    ("BoxSpinSpeed", None, None),

    ("BoxShadowLabel", None, None),
    ("BoxShadowOnHighlight", None, None),
    ("BoxShadowOnNormal", None, None),
    ("BoxShadowColorRed", "Shadow Color", GRUPO_SOMBRA + 100),
    ("BoxShadowColorGreen", None, GRUPO_SOMBRA + 100),
    ("BoxShadowColorBlue", None, GRUPO_SOMBRA + 100),
    ("BoxShadowCenterX", None, None),
    ("BoxShadowCenterY", None, None),
    ("BoxShadowOpacity", None, None),
    ("BoxShadowSoftness", None, None),

    # Fecha o Inspector: ferramenta, nao estilo.
    ("ConfigLabel", None, None),
    ("ExportConfig", None, None),
]


# --------------------------------------------------------- as duas abas
#
# O Inspector do clipe tinha UMA aba com onze grupos: chegar na bolha era rolar
# por Animation, Fill, Outline e Shadow / Glow. A divisao separa o que se mexe
# escrevendo uma legenda do que se mexe desenhando uma.
#
#   Text     tipografia, animacao de entrada, fill, outline - e as ferramentas
#   Extras   os enfeites: caixa, bolha, palavra falada, sombras
#
# ESTA LISTA E' A ORDEM DO INSPECTOR, e a unica. A ordem do bloco `Inputs` do
# macro e' o que o Fusion desenha, e um `LabelControl` engole os
# `LBLC_NumInputs` controles SEGUINTES - entao "em que grupo o controle cai" e
# "em que aba ele aparece" sao a mesma decisao, e ela tem que morar num lugar so.
# Antes ela estava repartida entre tres funcoes de insercao posicional
# (`depois do grupo Text`, `depois de Style`, `no fim`), o que ja tinha rendido
# um grupo adotando o controle do grupo de baixo.
#
# Nome de INSTANCIA, nao de UserControl: os dois divergem (`TextLabel` aponta pro
# `SubtitleLabel`, `TextSize` pro `Size`), e quem esta no bloco e' o primeiro.
LAYOUT = [
    ("Text", [
        # tipografia
        "TextLabel", "Text", "Font", "Style", "TextCase", "TextSize",
        "TextPosition", "ApplyStyleText",
        # o grupo Actions continua ABRINDO o Inspector: o botao que fecha
        # qualquer ajuste nao pode existir so' no fim de uma lista com rolagem
        "ApplyStyleLabel", "ApplyStyle", "ApplyStyleTrack", "ApplyStyleAll",
        "GenerateStyle",
        "AnimationLabel", "AnimationLevel", "AnimationMode", "FadeEnabled",
        "PopInEnabled", "SlideUpEnabled", "AnimationLength", "ApplyStyleAnimation",
        "FillLabel", "FillEnabled",
        "FillColorRed", "FillColorGreen", "FillColorBlue", "ApplyStyleFill",
        "OutlineLabel", "OutlineEnabled", "OutlineThickness",
        "OutlineColorRed", "OutlineColorGreen", "OutlineColorBlue",
        "ApplyStyleOutline",
        # ferramenta, nao estilo - por isso fecha a aba e nao ganha rodape
        "ConfigLabel", "ExportConfig",
    ]),
    ("Extras", [
        "TextBoxLabel", "TextBoxEnabled", "TextBoxFixed",
        "TextBoxWidth", "TextBoxHeight",
        "TextBoxColorRed", "TextBoxColorGreen", "TextBoxColorBlue",
        "TextBoxOpacity", "TextBoxLevel", "TextBoxExtendHorizontal",
        "TextBoxExtendVertical", "TextBoxRound", "ApplyStyleTextBox",
        # logo abaixo do Text Box: e' a mesma caixa, outra cor e outro offset
        "BoxLayer3Label", "BoxLayer3Enabled",
        "BoxLayer3ColorRed", "BoxLayer3ColorGreen", "BoxLayer3ColorBlue",
        "BoxLayer3CenterX", "BoxLayer3CenterY", "BoxLayer3Alpha",
        # fecha o grupo: e' o unico controle que se move no TEMPO, e ele governa
        # os dois offsets acima (raio e fase saem deles)
        "BoxSpinSpeed",
        "ApplyStyleBoxLayer3",
        "BubbleLabel", "BubbleEnabled",
        "BubbleColorRed", "BubbleColorGreen", "BubbleColorBlue",
        "BubbleOpacity", "BubbleLevel", "BubbleExtendHorizontal",
        "BubbleExtendVertical", "BubbleRound",
        "BubblePopEnabled", "BubblePopAmount", "BubblePopFrames",
        "ApplyStyleBubble",
        "WordFillLabel", "WordFillEnabled",
        "WordFillColorRed", "WordFillColorGreen", "WordFillColorBlue",
        "ApplyStyleWordFill",
        "BoxShadowLabel", "BoxShadowOnHighlight", "BoxShadowOnNormal",
        "BoxShadowColorRed", "BoxShadowColorGreen", "BoxShadowColorBlue",
        "BoxShadowCenterX", "BoxShadowCenterY", "BoxShadowOpacity",
        "BoxShadowSoftness", "ApplyStyleBoxShadow",
        # o "Shadow / Glow" do AutoSubs (elemento 3, a sombra do TEXTO) - o unico
        # grupo deles que atravessa pra ca
        "ShadowLabel", "ShadowEnabled",
        "ShadowColorRed", "ShadowColorGreen", "ShadowColorBlue",
        "ApplyStyleShadow",
    ]),
    # A terceira aba: de onde a legenda veio, e a ponte de volta pro
    # giautosubs.py. Por ultimo porque nao se mexe nela pra desenhar uma
    # legenda - se mexe nela pra REFAZER as legendas.
    ("Meta", [
        "MetaLabel",
        "MetaCaptionsFile", "MetaCutFolder", "MetaTranscript",
        "MetaStyle", "MetaStylesFile", "MetaTitle", "MetaConfig",
        "MetaCharsPerBox", "MetaLines", "MetaCharWidth", "MetaPxPorUnidade",
        # as opcoes, e o submit por ultimo
        "MetaFixedWidth", "MetaNoGaps", "MetaRebuild",
    ]),
]

# Controles do AutoSubs que deixam de aparecer no Inspector. Nao sao apagados
# (outras rotinas ainda leem o valor deles) - so nao sao mais expostos.
#
# Dois grupos:
#
# 1. O destaque do AutoSubs. A maquinaria por tras foi desarmada, e botao que
#    mente e' pior que botao que falta.
#
# 2. Os botoes "Update ... Color" / "Update Animation". Eles aplicavam um
#    pedaco do estilo cada um. O Apply Style aplica o estilo inteiro, entao
#    quatro botoes viraram um - e nenhum deles pode mais discordar dos outros.
ESCONDER = ["HighlightLabel", "HighlightEnabled", "UpdateHighlight",
            "HighlightStyle", "HighlightExtendHorizontal",
            "HighlightExtendVertical", "HighlightRound", "HighlightColorRed",
            "HighlightColorGreen", "HighlightColorBlue", "ModifyWordTiming",
            "UpdateFillColor", "UpdateOutlineColor", "UpdateShadowColor",
            "UpdateAnimationButton"]


# A virgula final e' OPCIONAL: varios controles do AutoSubs trazem o callback
# como ULTIMO campo, e ali o Fusion aceita `]]` seco. Exigindo a virgula, o
# regex passava por cima desse fecha e ia parar no `]],` do proximo controle -
# levando junto os controles do meio. Foi assim que o `FillEnabled` sumiu.
_CALLBACK = re.compile(r"(?ms)^\t+INPS_ExecuteOnChange = \[\[\n.*?^\t+\]\],?\n")


# ------------------------------------------------- a caixa como RETANGULO (--fixo)
#
# Tres pares Background+RectangleMask e tres Merge, empilhados de tras pra frente:
#
#   3 (mais atras)  a terceira cor - o `BoxLayer3*`
#   2               a segunda cor  - o `BoxShadow*` (que no 3color e' cor, nao sombra)
#   1               a caixa base   - o `TextBox*`
#   e o Text+ por cima de todos
#
# O idioma (MaskWidth/MaskHeight = resolucao, Center/Width/Height em fracao,
# CornerRadius) saiu dos 89 templates de fabrica que usam RectangleMask+Background -
# nao foi inventado aqui.
#
# `UseFrameFormatSettings = 1` no Background: sem isso o solido nasce no tamanho
# gravado no arquivo e nao no da timeline, e a caixa apareceria com a resolucao
# errada em qualquer projeto que nao fosse 1920x1080.
#
# E NENHUM `GlobalIn`/`GlobalOut` nos nove tools, de proposito. O Text+ do AutoSubs
# declara `GlobalOut = 149`; se um input do Merge vale ate o frame 1000 e o outro
# ate o 149, no frame 200 um dos dois nao tem imagem - e um Merge sem um dos inputs
# nao devolve nada. O comp termina em "no frame available for MediaOut1", que foi
# exatamente o sintoma. Sem declarar faixa, cada tool vale pela comp inteira.
_TOOLS_RETANGULO = """
				GiBoxMask3 = RectangleMask {
					Inputs = {
						MaskWidth = Input { Value = 1920, },
						MaskHeight = Input { Value = 1080, },
						PixelAspect = Input { Value = { 1, 1, }, },
						ClippingMode = Input { Value = FuID { "None", }, },
						Center = Input { Value = { 0.5, 0.22, }, },
						Width = Input { Value = 0.5, },
						Height = Input { Value = 0.12, },
						CornerRadius = Input { Value = 0, },
					},
					ViewInfo = OperatorInfo { Pos = { -220, -170, }, },
				},
				GiBoxBG3 = Background {
					Inputs = {
						Width = Input { Value = 1920, },
						Height = Input { Value = 1080, },
						UseFrameFormatSettings = Input { Value = 1, },
						TopLeftRed = Input { Value = 1, },
						TopLeftGreen = Input { Value = 0.3, },
						TopLeftBlue = Input { Value = 0.65, },
						TopLeftAlpha = Input { Value = 1, },
						EffectMask = Input {
							SourceOp = "GiBoxMask3",
							Source = "Mask",
						},
					},
					ViewInfo = OperatorInfo { Pos = { -220, -115, }, },
				},
				GiBoxMask2 = RectangleMask {
					Inputs = {
						MaskWidth = Input { Value = 1920, },
						MaskHeight = Input { Value = 1080, },
						PixelAspect = Input { Value = { 1, 1, }, },
						ClippingMode = Input { Value = FuID { "None", }, },
						Center = Input { Value = { 0.5, 0.22, }, },
						Width = Input { Value = 0.5, },
						Height = Input { Value = 0.12, },
						CornerRadius = Input { Value = 0, },
					},
					ViewInfo = OperatorInfo { Pos = { -110, -170, }, },
				},
				GiBoxBG2 = Background {
					Inputs = {
						Width = Input { Value = 1920, },
						Height = Input { Value = 1080, },
						UseFrameFormatSettings = Input { Value = 1, },
						TopLeftRed = Input { Value = 0, },
						TopLeftGreen = Input { Value = 0.9, },
						TopLeftBlue = Input { Value = 1, },
						TopLeftAlpha = Input { Value = 1, },
						EffectMask = Input {
							SourceOp = "GiBoxMask2",
							Source = "Mask",
						},
					},
					ViewInfo = OperatorInfo { Pos = { -110, -115, }, },
				},
				GiBoxMask1 = RectangleMask {
					Inputs = {
						MaskWidth = Input { Value = 1920, },
						MaskHeight = Input { Value = 1080, },
						PixelAspect = Input { Value = { 1, 1, }, },
						ClippingMode = Input { Value = FuID { "None", }, },
						Center = Input { Value = { 0.5, 0.22, }, },
						Width = Input { Value = 0.5, },
						Height = Input { Value = 0.12, },
						CornerRadius = Input { Value = 0, },
					},
					ViewInfo = OperatorInfo { Pos = { 0, -170, }, },
				},
				GiBoxBG1 = Background {
					Inputs = {
						Width = Input { Value = 1920, },
						Height = Input { Value = 1080, },
						UseFrameFormatSettings = Input { Value = 1, },
						TopLeftRed = Input { Value = 0, },
						TopLeftGreen = Input { Value = 0, },
						TopLeftBlue = Input { Value = 0, },
						TopLeftAlpha = Input { Value = 1, },
						EffectMask = Input {
							SourceOp = "GiBoxMask1",
							Source = "Mask",
						},
					},
					ViewInfo = OperatorInfo { Pos = { 0, -115, }, },
				},
				GiBoxMerge32 = Merge {
					Inputs = {
						Background = Input {
							SourceOp = "GiBoxBG3",
							Source = "Output",
						},
						Foreground = Input {
							SourceOp = "GiBoxBG2",
							Source = "Output",
						},
					},
					ViewInfo = OperatorInfo { Pos = { -110, -60, }, },
				},
				GiBoxMerge21 = Merge {
					Inputs = {
						Background = Input {
							SourceOp = "GiBoxMerge32",
							Source = "Output",
						},
						Foreground = Input {
							SourceOp = "GiBoxBG1",
							Source = "Output",
						},
					},
					ViewInfo = OperatorInfo { Pos = { 0, -60, }, },
				},
				GiBoxMerge = Merge {
					Inputs = {
						Background = Input {
							SourceOp = "GiBoxMerge21",
							Source = "Output",
						},
						Foreground = Input {
							SourceOp = "Template",
							Source = "Output",
						},
					},
					ViewInfo = OperatorInfo { Pos = { 110, -60, }, },
				},
"""


def _inserir_retangulos(texto, contador):
    """Poe os nove tools da caixa no `Tools` do MACRO, e re-aponta a saida.

    O bloco `Tools` do MacroOperator termina onde comeca o `UserControls` dele -
    ancorar ali e' o unico jeito estavel: o ultimo tool muda de nome conforme a
    versao do macro do AutoSubs.

    A saida do macro (`MainOutput1`) vem do `Template`; passa a vir do `GiBoxMerge`.
    Sem isto os tools existem, renderizam e nao aparecem - o pior dos dois mundos.
    """
    # O fim do bloco `Tools` do MACRO, por CONTAGEM DE CHAVES.
    #
    # A versao anterior procurava "fecha-chaves seguido de UserControls" por regex -
    # e o Text+ tambem tem `UserControls`, entao o primeiro match podia ser o dele.
    # Os nove tools cairam FORA do bloco, o `MainOutput1` passou a apontar pra um
    # tool que nao existia, e o Resolve respondeu com Media Offline. Contar chaves
    # a partir do `Tools` certo nao depende de quem vem depois.
    inicio_macro = texto.find("= MacroOperator {")
    if inicio_macro < 0:
        raise SystemExit("nao achei o MacroOperator - o macro mudou de forma")
    m_tools = re.compile(r"Tools = ordered\(\) \{").search(texto, inicio_macro)
    if not m_tools:
        raise SystemExit("nao achei o bloco Tools do macro")

    profundidade, fim = 0, None
    for pos in range(m_tools.end() - 1, len(texto)):
        if texto[pos] == "{":
            profundidade += 1
        elif texto[pos] == "}":
            profundidade -= 1
            if profundidade == 0:
                fim = pos
                break
    if fim is None:
        raise SystemExit("o bloco Tools do macro nao fecha - arquivo truncado?")

    # O ultimo tool fecha SEM virgula (o Fusion aceita); com mais tools depois, ela
    # passa a ser obrigatoria.
    antes = texto[:fim].rstrip()
    if not antes.endswith(","):
        antes += ","
    texto = (antes + "\n" + _TOOLS_RETANGULO.strip("\n") + "\n"
             + texto[texto.rfind("\n", 0, fim) + 1:])

    novo, n = re.subn(
        r'(MainOutput1 = InstanceOutput \{\n\t+SourceOp = ")Template(",)',
        r"\g<1>GiBoxMerge\g<2>", texto, count=1)
    if not n:
        raise SystemExit("nao achei o MainOutput1 pra re-apontar")
    # Conferencia na hora: os nove tools tem que estar DENTRO do bloco `Tools` do
    # macro. Foi o erro que deu Media Offline, e ele e' invisivel em tudo o mais -
    # o arquivo compila, valida, instala, e nao aparece.
    m2 = re.compile(r"Tools = ordered\(\) \{").search(
        novo, novo.find("= MacroOperator {"))
    prof, fim2 = 0, None
    for pos in range(m2.end() - 1, len(novo)):
        if novo[pos] == "{":
            prof += 1
        elif novo[pos] == "}":
            prof -= 1
            if prof == 0:
                fim2 = pos
                break
    pos_merge = novo.find("GiBoxMerge = Merge {")
    if not (m2.end() < pos_merge < (fim2 or 0)):
        raise SystemExit("os tools do retangulo ficaram FORA do bloco Tools do "
                         "macro - seria Media Offline na timeline")

    contador.append("the box is now a RECTANGLE: 3 Background + 3 RectangleMask + "
                    "3 Merge inside the macro, and MainOutput1 comes from "
                    "GiBoxMerge (the text on top). It does not read the text at "
                    "all - which costs a constant render per frame, unlike "
                    "everything else in this macro")
    return novo

def _sem_fim_de_validade(texto, contador):
    """Tira o `GlobalOut` dos tools do macro.

    O AutoSubs salvou o Text+ numa comp de 150 frames, e o `GlobalOut = 149` veio
    junto: o tool deixa de ter imagem depois desse frame. Com o Text+ como saida do
    macro isso apenas fazia a legenda longa sumir no fim (defeito latente); com a
    variante `Fixo`, onde a saida e' um Merge, um input sem imagem faz o comp inteiro
    responder `no frame available for MediaOut1`.

    Legenda de 5 segundos a 30fps ja passa de 149, e desde o `--no-gaps` ha legendas
    de 21 segundos. Um Title de legenda nao tem prazo de validade.
    """
    texto, n = re.subn(r"(?m)^\t+GlobalOut = Input \{ Value = \d+, \},\n", "",
                       texto)
    contador.append(f"{n} GlobalOut removed (a tool with GlobalOut has no image "
                    f"after that frame - it made long captions vanish, and it is "
                    f"what made the Fixo variant answer 'no frame available for "
                    f"MediaOut1')")
    return texto


def _desautomatizar(texto, contador):
    """Tira TODO `INPS_ExecuteOnChange` do macro - inclusive os do AutoSubs.

    Um callback sobrevivente seria um segundo caminho de aplicacao, invisivel e
    disparado por arrasto de slider: exatamente o que o Apply Style veio
    substituir. Zero e' o unico numero verificavel aqui.
    """
    texto, n = _CALLBACK.subn("", texto)
    contador.append(f"{n} INPS_ExecuteOnChange callbacks removed "
                    f"(the Apply Style button is the only way in)")
    return texto


# O schema do estilo. E' A lista: `GetInputValues` le exatamente estas chaves e
# `SetInputValues` escreve exatamente estas chaves, entao acrescentar um
# controle aqui e' tudo que e' preciso pra ele passar a viajar junto com o
# estilo - sem uma linha nova no GiAutoSubs.lua nem no giautosubs.py.
#
# Da lista do AutoSubs saem os `Highlight*`: a maquinaria por tras deles foi
# desarmada (o destaque aqui e' o nosso, por keyframe de palavra) e os controles
# nao aparecem mais no Inspector. Chave de controle que nao existe seria uma
# entrada que le nil todo dia.
_INPUT_KEYS_BASE = (
    "Font", "Style", "TextSize", "TextPosition",
    "FadeEnabled", "PopInEnabled", "SlideUpEnabled",
    "AnimationLength", "AnimationLevel", "AnimationMode",
    "FillEnabled", "FillColorRed", "FillColorGreen", "FillColorBlue",
    "OutlineEnabled", "OutlineThickness",
    "OutlineColorRed", "OutlineColorGreen", "OutlineColorBlue",
    "ShadowEnabled", "ShadowColorRed", "ShadowColorGreen", "ShadowColorBlue",
)

# Fora do estilo de proposito: `GiAutoSubsVersao` e' carimbo, nao escolha -
# copiar o carimbo de um clipe velho pra um novo apagaria justamente o aviso que
# ele existe pra dar - e `ApplyStyle` e' uma ACAO: nao tem valor pra guardar nem
# pra restaurar.
#
# A aba META inteira fica fora pelo mesmo motivo, com uma consequencia a mais:
# `MetaCaptionsFile` e companhia sao de onde ESTE clipe veio. No preset, o
# "Apply Style to All Captions" carimbaria a procedencia do clipe de origem em
# cima de todos os outros, e o "Export Config" gravaria caminhos de maquina
# dentro de um estilo. Quem escreve a Meta e' o `GiAutoSubs.lua`, por clipe, a
# partir do `dados.meta`.
_FORA_DO_PRESET = {"GiAutoSubsVersao", "ApplyStyle", "ExportConfig",
                   "ApplyStyleTrack", "ApplyStyleAll", "GenerateStyle",
                   "MetaRebuild", "MetaNoGaps", "MetaFixedWidth",
                   "MetaPxPorUnidade"}


def input_keys():
    """O schema completo: os controles do AutoSubs que sobraram + os nossos.

    `NOVOS_TEXTO` entra aqui junto com o resto: um controle que existe no
    Inspector e nao no `InputKeys` funciona ate' voce rodar o script, e ai volta
    calado pro que era. O validador recusa o macro antes disso.
    """
    # `NOVOS_META` de fora: eles nao sao estilo (ver `_FORA_DO_PRESET`), e um
    # deles carrega TEXTO - o par Get/SetInputValues compara e escreve numero.
    novos = [nome for nome, _, _ in NOVOS + NOVOS_TEXTO
             if not nome.endswith("Label") and nome not in _FORA_DO_PRESET]
    return list(_INPUT_KEYS_BASE) + novos


def _trocar_input_keys(texto, contador):
    m = _bloco("InputKeys").search(texto)
    if not m:
        contador.append("WARNING: InputKeys not found - the macro changed shape")
        return texto
    tabs = m.group(1)
    chaves = input_keys()
    itens = "\n".join(f'{tabs}\t"{k}",' for k in chaves)
    novo = f"{tabs}InputKeys = {{\n{itens}\n{tabs}}},"
    contador.append(f"InputKeys rewritten with {len(chaves)} keys "
                    f"(the style schema now lives in the macro, so a new "
                    f"control costs no code anywhere else)")
    return texto[:m.start()] + novo + texto[m.end():]


_INPUTS_MACRO = re.compile(r"(?ms)^(\t+)Inputs = ordered\(\) \{\n(.*?)^\1\},$")


def _anexar_instance_inputs(texto, novo, contador):
    """Acrescenta InstanceInputs no FIM do bloco `Inputs` do macro.

    Ancorar em "logo depois do ShadowColorBlue" funcionava por acidente: bastava
    esconder um controle que vinha depois dele pra os novos caÃ­rem no meio da
    lista. E a ordem nao e' cosmetica - ver `_recontar_grupos`.
    """
    m = _INPUTS_MACRO.search(texto)
    if not m:
        contador.append("WARNING: could not find the macro Inputs block")
        return texto
    ind, corpo = m.group(1), m.group(2)
    linhas = corpo.rstrip("\n").split("\n")
    # a ultima entrada do bloco vem sem virgula (o Fusion aceita), e sem ela o
    # que for acrescentado depois nao compila
    for i in range(len(linhas) - 1, -1, -1):
        if re.fullmatch(r"\t+\}", linhas[i]):
            linhas[i] += ","
            break
        if re.fullmatch(r"\t+\},", linhas[i]):
            break
    corpo = "\n".join(linhas) + "\n" + novo.rstrip("\n") + "\n"
    return (texto[:m.start()] + ind + "Inputs = ordered() {\n" + corpo
            + ind + "}," + texto[m.end():])


def _recontar_grupos(texto, contador):
    """Recalcula o `LBLC_NumInputs` de cada rotulo a partir da lista final.

    No Inspector do Fusion um LabelControl e' so um cabecalho: ele engole os N
    controles SEGUINTES, onde N e' um numero escrito na mao. Esconder um
    controle, ou acrescentar outro, faz esse numero mentir - e o sintoma e' um
    grupo que adota o primeiro item do grupo de baixo (foi assim que o
    "Shadow" ficou com o rotulo "Bolha" dentro).

    Contar aqui, depois de todas as outras mudancas, e' o que dispensa manter
    esses numeros em dia na mao.
    """
    m = _INPUTS_MACRO.search(texto)
    if not m:
        contador.append("WARNING: could not find the Inputs block to recount the groups")
        return texto

    # o nome do InstanceInput NAO e' o do UserControl: `TextLabel` aponta pra
    # `SubtitleLabel`. Quem manda e' o Source - foi por olhar o nome que o
    # primeiro grupo escapava da recontagem.
    ordem = re.findall(
        r"(?ms)^\t+\w+ = InstanceInput \{.*?^\t+Source = \"(\w+)\",", m.group(2))
    rotulos = set(re.findall(
        r"(?ms)^\t+(\w+) = \{[^{}]*?INPID_InputControl = \"LabelControl\"", texto))

    contagens, atual = {}, None
    for fonte in ordem:
        if fonte in rotulos:
            atual, contagens[fonte] = fonte, 0
        elif atual:
            contagens[atual] += 1

    n = 0
    for nome, quantos in contagens.items():
        bloco = _bloco(nome).search(texto)
        if not bloco:
            continue
        novo, k = re.subn(r"(?m)^(\t+)LBLC_NumInputs = \d+,$",
                          rf"\g<1>LBLC_NumInputs = {quantos},", bloco.group(0),
                          count=1)
        if k:
            texto = texto[:bloco.start()] + novo + texto[bloco.end():]
            n += 1
    contador.append(f"{n} Inspector groups recounted "
                    f"({', '.join(f'{k}={v}' for k, v in contagens.items())})")
    return texto


def instance_inputs(lista=None, fonte=None):
    """Sem InstanceInput o controle existe no Text+ interno mas nao aparece no
    Inspector do clipe - que e' justamente onde ele precisa aparecer.

    `fonte` aponta todos os blocos pro MESMO UserControl. E' o que faz os nove
    rodapes serem instancias do unico `ApplyStyle` (ver RODAPES): o nome do
    InstanceInput so' precisa ser unico, quem manda e' o `Source`.

    A `Page` sai daqui de proposito: quem decide a aba (e a ordem) e' o
    `_reordenar_inputs`, com o LAYOUT na mao. Duas fontes pra mesma decisao e' o
    tipo de coisa que diverge calada.
    """
    blocos = []
    for nome, rotulo, grupo in (NOVOS if lista is None else lista):
        linhas = [f"{nome} = InstanceInput {{",
                  '\tSourceOp = "Template",',
                  f'\tSource = "{fonte or nome}",']
        if rotulo:
            linhas.append(f'\tName = "{rotulo}",')
        if grupo:
            linhas.append(f"\tControlGroup = {grupo},")
        linhas.append('\tPage = "Text",')
        linhas.append("},")
        blocos.append("\n".join(linhas))
    return "\n".join(blocos)


def instance_inputs_rodape():
    """Os nove `Apply Style` de rodape, um por grupo de atributos."""
    return instance_inputs([(nome, None, None) for nome, _ in RODAPES],
                           fonte="ApplyStyle")


def instance_inputs_meta():
    """A largura fixa exposta TAMBEM na aba Meta, apontando pro mesmo controle.

    Mesma mecanica dos rodapes (`instance_inputs_rodape`): o nome da instancia e'
    outro, o `Source` e' o mesmo. E' o que faz marcar na Meta e marcar no Text Box
    serem o MESMO ato - dois controles separados acabariam discordando, e o
    usuario veria "Fixed Width" marcado numa aba e "Fixed Box" desmarcado na
    outra.
    """
    return "\n".join(
        instance_inputs([(nome, rotulo, None)], fonte=fonte)
        for nome, fonte, rotulo in META_INSTANCIAS)


def _reordenar_inputs(texto, contador):
    """Poe o bloco `Inputs` do macro na ordem do LAYOUT e carimba a aba de cada um.

    O Inspector do clipe segue a ordem deste bloco - literalmente, de cima pra
    baixo - e um `LabelControl` engole os controles SEGUINTES. Entao ordenar e
    paginar sao a mesma operacao, e ela e' feita de uma vez so', no fim, com a
    lista completa na mao.

    Uma aba por vez, sem intercalar: um grupo que comeca na aba Text e termina
    na Extras seria contado errado pelo `_recontar_grupos` e desenhado errado
    pelo Fusion.

    Quem sobrar (um controle novo do AutoSubs, um nome que mudou numa versao
    deles) cai no fim da aba Text COM AVISO - some do lugar certo, nao do
    Inspector, e o gerador diz que isso aconteceu.
    """
    m = _INPUTS_MACRO.search(texto)
    if not m:
        contador.append("WARNING: could not find the macro Inputs block to reorder")
        return texto

    ind, corpo = m.group(1), m.group(2)
    blocos, ordem = {}, []
    for b in re.finditer(r"(?ms)^\t+(\w+) = InstanceInput \{.*?^\t+\},\n?", corpo):
        blocos[b.group(1)] = b.group(0).rstrip("\n")
        ordem.append(b.group(1))

    saida, usados = [], set()
    for pagina, nomes in LAYOUT:
        for nome in nomes:
            bloco = blocos.get(nome)
            if bloco is None:
                contador.append(f"WARNING: the LAYOUT asks for '{nome}', which is "
                                f"not an InstanceInput - it will not show up")
                continue
            saida.append(re.sub(r'(?m)^(\t+)Page = "[^"]*",$',
                                rf'\g<1>Page = "{pagina}",', bloco))
            usados.add(nome)

    sobraram = [n for n in ordem if n not in usados]
    for nome in sobraram:
        saida.append(blocos[nome])
    if sobraram:
        contador.append(f"WARNING: {len(sobraram)} InstanceInput(s) are not in the "
                        f"LAYOUT and went to the end of the Text tab "
                        f"({', '.join(sobraram)})")

    contas = ", ".join(f"{p}={sum(1 for n in ns if n in usados)}"
                       for p, ns in LAYOUT)
    contador.append(f"Inspector reordered from the LAYOUT ({contas})")
    # sem `_ind`: os blocos saem do proprio corpo, ja com o recuo do arquivo
    corpo = "\n".join(saida) + "\n"
    return (texto[:m.start()] + ind + "Inputs = ordered() {\n" + corpo
            + ind + "}," + texto[m.end():])


def _criar_aba(texto, contador, nome, depois_de, descricao):
    """Declara a `ControlPage` de uma aba, logo depois de outra.

    Mesma camada do `_criar_aba_extras` (que continua sendo o dono do caso
    Extras, por ser ele quem conhece a aba "Text"): a ORDEM das declaracoes e' a
    ordem das abas, entao ancorar na aba anterior e' o que decide onde a nova
    aparece. Um `Page = "Meta"` sem esta declaracao nao cria aba nenhuma - o
    controle cai calado na primeira pagina visivel.
    """
    if re.search(r"(?m)^\t+" + nome + r" = ControlPage \{", texto):
        return texto
    m = re.search(r"(?ms)^(\t+)" + depois_de + r" = ControlPage \{\n.*?^\1\},$",
                  texto)
    if not m:
        contador.append(f'WARNING: the "{depois_de}" ControlPage was not found - '
                        f'the {nome} tab was NOT created and its controls would '
                        f'fall back into the first visible tab')
        return texto
    ind = m.group(1)
    aba = f'{ind}{nome} = ControlPage {{\n{ind}\tCT_Visible = true,\n{ind}}},'
    contador.append(f'the "{nome}" tab created ({descricao})')
    return texto[:m.end()] + "\n" + aba + texto[m.end():]


def _criar_aba_extras(texto, contador):
    """Declara a `ControlPage` da aba Extras.

    Uma aba nao nasce de `Page = "Extras"` nos InstanceInput: isso so' diz onde o
    controle mora. A ABA e' uma camada a parte - um `ControlPage` no
    `UserControls` do MACRO (MACRO.md 1, camada 4). E' a mesma razao pela qual
    esvaziar a aba "Style" nao a fazia sumir: sem mexer no ControlPage ela
    continuava la, vazia. Aqui e' o inverso da mesma regra.

    Depois da `Text`, porque a ordem das declaracoes e' a ordem das abas.
    """
    if re.search(r"(?m)^\t+Extras = ControlPage \{", texto):
        return texto
    m = re.search(r"(?ms)^(\t+)Text = ControlPage \{\n.*?^\1\},$", texto)
    if not m:
        contador.append('WARNING: the "Text" ControlPage was not found - '
                        'the Extras tab was NOT created and its controls '
                        'would fall into the first visible page')
        return texto
    ind = m.group(1)
    aba = f'{ind}Extras = ControlPage {{\n{ind}\tCT_Visible = true,\n{ind}}},'
    contador.append('the "Extras" tab created (Text Box, Bubble, Spoken Word, '
                    'Box Shadow, Shadow / Glow)')
    return texto[:m.end()] + "\n" + aba + texto[m.end():]


# --------------------------------------------------------------- patches

def _para_follower(inputs):
    """O subconjunto do estilo que tambem precisa ir pro Follower1.

    Ver CHAVES_DO_FOLLOWER em giautosubs.py pro porque. Geometria de caixa
    (Level/Extend/Round/ElementShape) fica de fora: o Follower nao traz esses
    inputs, entao nao sobrescreve nada, e escrever neles so' criaria uma
    segunda verdade pra manter em dia.
    """
    import giautosubs as G

    out = {}
    for chave, valor in inputs.items():
        base = re.match(r"^([A-Za-z]+)([1-8])$", chave)
        if base and base.group(1) in G.CHAVES_DO_FOLLOWER:
            out[chave] = valor
    return out


def _carimbo_versao():
    """Um controle invisivel com a versao do macro dentro.

    Nao vira InstanceInput de proposito: ninguem precisa ver isso no
    Inspector. Serve pro `template:GetInput("GiAutoSubsVersao")` do Lua
    descobrir que o Media Pool esta com uma copia velha.
    """
    import giautosubs as G

    return _uc("GiAutoSubsVersao", [
        ("LINKS_Name", '"GiAutoSubs (macro version)"'),
        ("LINKID_DataType", '"Number"'),
        ("INPID_InputControl", '"SliderControl"'),
        ("INP_Default", str(G.MACRO_VERSAO)),
        ("INP_Integer", "true"),
        ("INP_MinScale", "0"),
        ("INP_MaxScale", "9999"),
        ("INP_External", "false"),
        ("INP_Passive", "true"),
        ("IC_Visible", "false"),
    ])


SPLINE_CLS = "CharacterLevelStyling1RightclickHeretoAnimateCharacterLevelStyling"


def _limpar_keyframes_de_exemplo(texto, contador):
    """Apaga os keyframes de exemplo do spline de character-level styling.

    E' a causa do "outline azul que nao muda com nada". O macro do AutoSubs vem
    com keyframes de demonstracao ali dentro:

        { 2401, 8, 15, Index = 1 },              -- Red   = 0
        { 2402, 8, 15, Index = 1, Value = 0.35 } -- Green = 0.35
        { 2403, 8, 15, Index = 1, Value = 1 },   -- Blue  = 1

    `Index = 1` e' o elemento 2, o outline; rgb(0, 0.35, 1) e' o azul. Estilo
    por caractere vence TANTO o Text+ quanto o Follower1 - entao nao importava
    o que se escrevesse nos dois, nem que cor se escolhesse no Inspector.

    No AutoSubs quem limpava isso era o `RemoveHighlight`, que aqui foi
    desarmado (ele tambem apagava os nossos keyframes). Entao a limpeza vem
    pra ca, e o GiAutoSubs.lua reescreve o spline em toda legenda - com as
    palavras, ou vazio.
    """
    m = _bloco(SPLINE_CLS, r"BezierSpline \{").search(texto)
    if not m:
        contador.append(f"WARNING: spline {SPLINE_CLS} not found")
        return texto
    bloco = m.group(0)
    # UM keyframe com array VAZIO - nunca zero keyframes.
    #
    # Um BezierSpline sem keyframe nenhum nao tem valor em tempo algum, e o
    # Fusion responde com "CharacterLevelStyling1 cannot get Parameter for
    # Right-click Here to Animate Character Level Styling at time N". O erro
    # sobe pela cadeia (Follower1 -> MediaOut1) e a legenda inteira deixa de
    # renderizar. E' por isso que o `RemoveHighlight` do AutoSubs tambem
    # escreve um keyframe vazio em vez de apagar tudo.
    vazio = ("KeyFrames = {\n"
             "\t[0] = { 0, Flags = { StepIn = true, LockedY = true }, "
             "Value = StyledText { Array = { }, Value = \"\" } }\n"
             "},")
    novo, n = re.subn(
        r"(?ms)^(\t+)KeyFrames = \{\n.*?^\1\},?$",
        lambda mm: _ind(vazio, len(mm.group(1))), bloco, count=1)
    if not n:
        contador.append("WARNING: the spline had no KeyFrames to strip")
        return texto
    contador.append("sample keyframes stripped from the spline "
                    "(they were the ones painting the outline blue)")
    return texto[:m.start()] + novo + texto[m.end():]


# O spline que DESENHA o fade de entrada/saida do AutoSubs.
SPLINE_FADE = "KeyframeStretcher1Keyframes"

# Animacao de entrada do AutoSubs, desligada de fabrica.
#
# Nao vem do estilos.json de proposito: nao e' estilo, e' comportamento do
# macro - e desligar de verdade exige mexer no spline (ver `_desligar_fade`),
# coisa que o compilador de estilo nao sabe fazer.
#
# `AnimationLevel` e' 0-BASED e, ao contrario dos combos `Level` do Text+, nao
# esta invertido: 0 = "Segment Level", 1 = "Word by Word" (a ordem dos
# `CCS_AddString` no macro, confirmada pelo `ApplyAnimationLevel`, que trata
# `== 1` como palavra por palavra e o `else` como "reveal the entire text at
# once").
ANIMACAO = {
    "AnimationLevel": 0,
    "FadeEnabled": 0,
    "PopInEnabled": 0,
    "SlideUpEnabled": 0,
}


def _desligar_fade(texto, contador):
    """Achata o spline do fade, pra legenda nascer sem animacao de entrada.

    `FadeEnabled = 0` sozinho nao apaga nada. O fade nao e' um valor: as
    `Opacity1..4` do Follower1 chegam CONECTADAS ao `AnimationKeyframeStretcher`,
    e quem da' a curva e' este BezierSpline - 0 -> 1 nos 8 primeiros centesimos
    da legenda e 1 -> 0 nos 8 ultimos. O checkbox so' e' LIDO pelo
    `SetAnimations`, e ele aqui roda so' no botao Apply Style (ver
    `SetInputValues`, `origem == "button"`). Sem esta limpeza o Inspector diria
    "off" e a tela continuaria com fade.

    A conexao NAO sai. Achatar o spline em 1 constante e' exatamente o que o
    proprio `SetAnimations` faz quando `FadeEnabled == 0`, e manter a conexao e'
    o que deixa o `opacidade_da_bolha` do ApplyGiStyle continuar podendo
    devolver a bolha pro stretcher (`follower[chave] = stretcher.Result`).
    Desconectar aqui quebraria esse caminho de volta.

    PopIn e SlideUp nao precisam de limpeza: os dois sao implementados
    ADICIONANDO modifier (KeyStretcherMod no WordSizeX/Y, XYPath no Offset1..3),
    e o template nao traz nenhum dos dois - ou seja, ja nasce no estado que o
    `ResetPopIn`/`ResetSlideUp` produziria.
    """
    m = _bloco(SPLINE_FADE, r"BezierSpline \{").search(texto)
    if not m:
        contador.append(f"WARNING: spline {SPLINE_FADE} not found - "
                        f"the caption may still be born with a fade")
        return texto
    bloco = m.group(0)
    plano = ("KeyFrames = {\n"
             "\t[0] = { 1, Flags = { StepIn = true } },\n"
             "\t[100] = { 1, Flags = { StepIn = true } }\n"
             "},")
    novo, n = re.subn(
        r"(?ms)^(\t+)KeyFrames = \{\n.*?^\1\},?$",
        lambda mm: _ind(plano, len(mm.group(1))), bloco, count=1)
    if not n:
        contador.append(f"WARNING: {SPLINE_FADE} had no KeyFrames to flatten")
        return texto
    contador.append("fade spline flattened to a constant 1 "
                    "(captions are born with no entry animation)")
    return texto[:m.start()] + novo + texto[m.end():]


def _num(v):
    """Numero como o Fusion escreve: sem sufixo, sem notacao cientifica."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return repr(round(v, 10)) if isinstance(v, float) else str(v)


def _gravar_defaults(texto, defaults):
    """Grava o estilo nos tres lugares onde o Fusion guarda um default.

    `defaults` e' {nome_do_controle: valor}. Nomes que nao existem no macro
    sao ignorados de proposito - assim da' pra passar o dicionario inteiro do
    giautosubs.py sem filtrar controle por controle aqui.
    """
    n = 0
    for nome, valor in defaults.items():
        v = _num(valor)

        # a) UserControl (INP_Default)
        m = _bloco(nome).search(texto)
        if m:
            trecho, k = re.subn(r"(?m)^(\t+)INP_Default = [^,\n]+,$",
                                rf"\g<1>INP_Default = {v},", m.group(0), count=1)
            if k == 0:
                trecho = re.sub(r"(?m)^(\t+)LINKID_DataType = ",
                                rf"\g<1>INP_Default = {v},\n\g<1>LINKID_DataType = ",
                                m.group(0), count=1)
                k = 1 if trecho != m.group(0) else 0
            texto, n = texto[:m.start()] + trecho + texto[m.end():], n + k

        # b) InstanceInput (Default) - so' existe pros controles expostos
        m = _bloco(nome, r"InstanceInput \{").search(texto)
        if m:
            trecho, k = re.subn(r"(?m)^(\t+)Default = [^,\n]+,$",
                                rf"\g<1>Default = {v},", m.group(0), count=1)
            if k == 0:
                trecho = re.sub(r"(?m)^(\t+)Page = ",
                                rf"\g<1>Default = {v},\n\g<1>Page = ",
                                m.group(0), count=1)
                k = 1 if trecho != m.group(0) else 0
            texto, n = texto[:m.start()] + trecho + texto[m.end():], n + k
    return texto, n


def _gravar_inputs(texto, inputs):
    """Grava valores no bloco `Inputs` do Text+ interno.

    E' o que faz o titulo ja aparecer certo quando voce arrasta ele da aba
    Effects, antes de qualquer script rodar. Chave que ja existe e' trocada;
    chave nova entra logo apos a abertura do bloco.
    """
    return _gravar_inputs_em(texto, "Template", r"TextPlus \{", inputs)


def _gravar_inputs_em(texto, ferramenta, tipo, inputs):
    alvo = _bloco(ferramenta, tipo).search(texto)
    if not alvo:
        return texto, 0
    # Trabalhar so' dentro do Template. `Enabled2 = Input { Value = 1, }`
    # existe identico no Follower1 logo abaixo, e um replace global acertaria
    # o errado sem avisar.
    corpo = alvo.group(0)
    abre = re.search(r"(?m)^(\t+)Inputs = \{\n", corpo)
    if not abre:
        return texto, 0
    # nunca sobrescrever uma CONEXAO por um valor: no Follower1 as Opacity1..4
    # vem do AnimationKeyframeStretcher, e trocar isso por um numero mataria o
    # fade sem dar erro nenhum
    conectados = set(re.findall(r"(?m)^\t+(\w+) = Input \{\n\t+SourceOp", corpo))
    corte, tabs = abre.end(), abre.group(1) + "\t"

    n = 0
    for chave, valor in inputs.items():
        if chave in conectados:
            continue
        if isinstance(valor, str):
            v = f'"{valor}"'
        elif isinstance(valor, (list, tuple)):
            v = "{ " + ", ".join(_num(x) for x in valor) + " }"
        else:
            v = _num(valor)
        linha = f"{tabs}{chave} = Input {{ Value = {v}, }},\n"
        pad = re.compile(r"(?m)^\t+" + re.escape(chave)
                         + r" = Input \{ Value = [^\n]*\n")
        corpo, k = pad.subn(linha, corpo, count=1)
        if not k:
            corpo = corpo[:corte] + linha + corpo[corte:]
        n += 1
    return texto[:alvo.start()] + corpo + texto[alvo.end():], n


def aplicar(texto, defaults=None, inputs=None):
    mudancas = []
    defaults = defaults or {}
    inputs = inputs or {}

    # 1) fonte padrao
    novo, n = re.subn(r'(Font = Input \{ Value = ")[^"]*(", \})',
                      rf'\g<1>{FONTE_FAMILIA}\g<2>', texto, count=1)
    if n:
        texto, _ = novo, mudancas.append(f"default font -> {FONTE_FAMILIA}")
    novo, n = re.subn(r'(\n\t+Style = Input \{ Value = ")[^"]*(", \})',
                      rf'\g<1>{FONTE_ESTILO}\g<2>', texto, count=1)
    if n:
        texto, _ = novo, mudancas.append(f"default font style -> {FONTE_ESTILO}")

    # 1a2) fora o fim de validade dos tools (o `GlobalOut = 149` do Text+)
    texto = _sem_fim_de_validade(texto, mudancas)

    # 1b) os keyframes de exemplo do spline - a causa do outline azul
    texto = _limpar_keyframes_de_exemplo(texto, mudancas)

    # 1c) o fade de entrada. Os checkboxes vao a 0 la' embaixo, com o resto dos
    #     defaults; aqui morre o spline que os desenha - sem isto o Inspector
    #     diz "off" e a tela continua com fade.
    texto = _desligar_fade(texto, mudancas)

    # 2) desarma as rotinas que competem com o script
    for nome, corpo in _NOOP.items():
        texto = _trocar_chunk(texto, nome, corpo, mudancas)
    mudancas.append(f"{len(_NOOP)} routines disarmed ({', '.join(_NOOP)})")

    # 3) rotinas de estilo reescritas + a rotina nova dos elementos 4..7
    texto = _trocar_chunk(texto, "UpdateAllStyleColors", _update_all(), mudancas)
    texto = _trocar_chunk(texto, "UpdateStyleColor", _com_log(_UPDATE_ONE), mudancas)
    mudancas.append("UpdateAllStyleColors/UpdateStyleColor rewritten "
                    "(they no longer write nil into the bubble)")

    # 3b) o par Get/SetInputValues - o contrato do macro com o resto do mundo.
    #
    #     O AutoSubs ja trazia os dois; o que muda e' pra onde eles apontam. O
    #     `InputKeys` deles listava os controles do destaque que aqui foram
    #     desarmados, e o `SetInputValues` terminava chamando SetAnimations +
    #     UpdateHighlight - e o UpdateHighlight e' justamente uma das seis
    #     rotinas desarmadas. Apontando pras nossas, o par volta a ser o unico
    #     caminho de escrita do estilo, e o schema passa a ser propriedade do
    #     macro: controle novo entra em `InputKeys` e mais nada muda.
    texto = _trocar_input_keys(texto, mudancas)
    texto = _trocar_chunk(texto, "GetInputValues", _com_log(_GET_INPUTS), mudancas)
    texto = _trocar_chunk(texto, "SetInputValues", _com_log(_SET_INPUTS), mudancas)
    mudancas.append("GetInputValues/SetInputValues now point at our routines "
                    "(one write path: control -> SetInputValues -> "
                    "UpdateAllStyleColors -> ApplyGiStyle)")

    # Chaves novas: entram logo apos UpdateAllStyleColors
    alvo = re.compile(r"(?ms)^(\t+)UpdateAllStyleColors = \[\[\n.*?^\1\]\],$")
    m = alvo.search(texto)
    if not m:
        raise SystemExit("nao achei UpdateAllStyleColors - o macro mudou de forma")
    tabs = len(m.group(1))
    novas = ""
    for nome, corpo in (("ApplyGiStyle", _apply_gi()),
                        ("GiRebuildHighlight", _com_log(_REBUILD)),
                        ("GiBubblePop", _pop()),
                        ("GiApplyText", _com_log(_CASE)),
                        # A ponte. Chunk e nao corpo de botao: o
                        # "Apply Style to This Track" chama o MESMO codigo
                        # quando ve que os caracteres por caixa mudaram.
                        ("GiRebuild", _reconstruir())):
        novas += (m.group(1) + nome + " = [[\n" + _ind(corpo, tabs + 1)
                  + "\n" + m.group(1) + "]],\n")
    texto = texto[:m.end()] + "\n" + novas.rstrip("\n") + texto[m.end():]
    mudancas.append("ApplyGiStyle (bubble, text box and both shadows) + "
                    "GiRebuildHighlight (rebuilds the per-word keyframes so a "
                    "colour picker reaches an animated element) + GiBubblePop "
                    "(the bubble grows into place on every word)")

    # 4) UserControls novos - no FIM da lista, nunca no comeco (ver _inserir_apos).
    #    Onde o UserControl esta na lista nao muda o Inspector do clipe (quem
    #    manda la e' a ordem dos InstanceInput), mas muda o agrupamento dos
    #    LabelControl aqui dentro - dai o botao vir junto com o resto.
    texto = _inserir_apos(texto, _bloco("ShadowColorBlue"),
                          _ind(controles() + "\n" + controles_fim() + "\n"
                               + controles_topo() + "\n" + controles_texto()
                               + "\n" + controles_meta(), 6),
                          mudancas, "the new controls")
    mudancas.append(f"{len(NOVOS) + len(NOVOS_TOPO) + len(NOVOS_TEXTO) + len(NOVOS_META)} new "
                    f"controls (Case, Spoken Word, Bubble, Text Box, "
                    f"Box Shadow, Apply Style)")

    # 5) o macro nasce com o SEU estilo, nao com o de exemplo do AutoSubs.
    #
    #    Fazer isso aqui, e nao no script por clipe, e' o que mantem a coisa
    #    rapida: cada controle mexido dispara ApplyGiStyle, que escreve uns 20
    #    inputs. Trinta controles vezes 129 legendas seriam ~77 mil idas ao
    #    Resolve so pra reafirmar o que ja estava certo. O estilo e' o mesmo
    #    nas 129, entao ele pertence ao macro; o que varia por legenda (texto,
    #    cor do falante, keyframes) continua com o script.
    #
    #    O Fusion guarda default em TRES lugares e todos os tres mandam:
    #    o `Input` do Text+, o `INP_Default` do UserControl e o `Default` do
    #    InstanceInput. Patchear um so' deixa os outros dois trazendo de volta
    #    o azul do AutoSubs - era exatamente o outline "que voltava sozinho".
    texto, n_def = _gravar_defaults(texto, defaults)
    texto, n_inp = _gravar_inputs(texto, inputs)

    #    E o mesmo estilo no Follower1. O StyledTextFollower nao e' decoracao:
    #    ele GERA o StyledText que alimenta o Text+, e os inputs de elemento
    #    que ele tem sobrescrevem os do Text+ caractere a caractere. O macro
    #    do AutoSubs traz `Red2 = 0.929, Green2 = 0.051, Thickness2 = 0.8` la
    #    dentro - entao pintar o outline so' no Text+ nao muda um pixel na
    #    tela. E' exatamente por isso que o UpdateAllStyleColors deles escreve
    #    nos dois tools, e era isso que faltava aqui.
    texto, n_fol = _gravar_inputs_em(texto, "Follower1",
                                     r"StyledTextFollower \{",
                                     _para_follower(inputs))
    mudancas.append(f"style baked into the macro as its default ({n_def} control "
                    f"defaults, {n_inp} Text+ inputs, {n_fol} on Follower1)")

    # carimbo de versao: e' o que deixa o script perceber que o Media Pool
    # ainda tem uma copia velha do macro (ver MACRO_VERSAO em giautosubs.py)
    texto = _inserir_apos(texto, _bloco("ShadowColorBlue"),
                          _ind(_carimbo_versao(), 6), mudancas, "the version stamp")

    # 6) aba "Style" some: tudo que morava la vai pra "Text"...
    texto, n_pg = re.subn(r'Page = "Style"', 'Page = "Text"', texto)

    # ...inclusive quem nao dizia em que aba estava. InstanceInput sem `Page`
    # cai na primeira pagina visivel - hoje isso da' certo por acidente, e
    # deixaria de dar no dia em que a ordem das ControlPage mudasse.
    def _pagina_explicita(m):
        if 'Page = ' in m.group(0):
            return m.group(0)
        ind = re.match(r"(\t+)", m.group(0)).group(1)
        return m.group(0).replace("\n" + ind + "},",
                                  f'\n{ind}\tPage = "Text",\n{ind}}},')
    texto, n_sem = re.subn(r'(?ms)^\t+\w+ = InstanceInput \{.*?^\t+\},',
                           _pagina_explicita, texto)

    # ...e a ABA em si tambem. Mover os controles nao apaga a aba: ela e'
    # declarada a parte, num `ControlPage` no UserControls do proprio macro, e
    # continuaria aparecendo vazia. E' por isso que a aba nao tinha sumido.
    novo, n_aba = re.subn(
        r'(?ms)^(\t+)Style = ControlPage \{\n.*?^\1\},$',
        lambda m: m.group(0).replace("CT_Visible = true", "CT_Visible = false"),
        texto, count=1)
    texto = novo
    mudancas.append(f'{n_pg} controls moved from the "Style" tab to "Text"'
                    + (f'; the Style tab is now hidden' if n_aba
                       else '; WARNING: could not find the "Style" ControlPage'))

    # 7) nenhum controle reage sozinho - quem aplica e' o botao Apply Style
    texto = _desautomatizar(texto, mudancas)

    # 7b) ...com TRES excecoes nomeadas: o tamanho da caixa fixa segue o slider.
    #     Depois do passo 7 porque ele tira todo callback do macro, inclusive um
    #     que tivesse sido posto antes.
    texto = _injetar_preview(texto, mudancas)

    # ...e ai os botoes "Update ..." saem, junto com o destaque desarmado
    escondidos = 0
    for nome in ESCONDER:
        pad = _bloco(nome, r"InstanceInput \{")
        m = pad.search(texto)
        if m:
            texto = texto[:m.start()] + texto[m.end():]
            escondidos += 1
    # a remocao pode deixar linha em branco solta
    texto = re.sub(r"\n\t*\n(\t+\w+ = InstanceInput)", r"\n\g<1>", texto)
    mudancas.append(f"{escondidos} controls hidden from the Inspector "
                    f"('Update ...' buttons and the AutoSubs highlighter)")

    # 8) InstanceInputs novos - todos no fim do bloco. ONDE cada um aparece nao
    #    se decide aqui: o passo 8c reordena o bloco inteiro a partir do LAYOUT,
    #    que e' a unica descricao do Inspector. Antes eram tres insercoes
    #    posicionais ("depois do grupo Text", "depois de Style", "no fim") e a
    #    ordem final so' dava pra saber lendo as tres.
    texto = _anexar_instance_inputs(
        texto, _ind(instance_inputs() + "\n" + instance_inputs(NOVOS_TOPO)
                    + "\n" + instance_inputs(NOVOS_TEXTO)
                    + "\n" + instance_inputs(NOVOS_META)
                    + "\n" + instance_inputs_meta()
                    + "\n" + instance_inputs_rodape(), 4), mudancas)
    mudancas.append(f"InstanceInputs (the new controls showing up on the clip, "
                    f"including {len(RODAPES)} Apply Style footers)")

    # 8a2) a caixa como retangulo, na variante `--fixo`. Antes das abas porque ela
    #      mexe em `Tools` e em `Outputs`, e nao em controle nenhum.
    if COM_FIXO:
        texto = _inserir_retangulos(texto, mudancas)

    # 8b) as abas, que precisam existir ANTES de alguem morar nelas. A ORDEM
    #     das declaracoes E' a ordem das abas, e cada uma se ancora na
    #     anterior - entao a Meta so' pode nascer depois da Extras.
    texto = _criar_aba_extras(texto, mudancas)
    texto = _criar_aba(texto, mudancas, "Meta", "Extras",
                       "Captions File, Cut Folder, Transcript, Style, "
                       "Title, Config, Characters per Box, Rebuild")

    # 8c) ordem e aba de todo mundo, de uma vez, a partir do LAYOUT
    texto = _reordenar_inputs(texto, mudancas)

    # 9) por ultimo, com a lista final na mao: reconta os grupos do Inspector
    texto = _recontar_grupos(texto, mudancas)

    return texto, mudancas


def _verificar(texto, defaults=None, crus=None):
    """Confere o que da' pra conferir sem abrir o Resolve.

    Regex em 84 KB de tabela aninhada erra calado: sobra uma virgula, some um
    fecha-chaves, e o sintoma so aparece como "o titulo nao carrega".
    """
    problemas = []
    if texto.count("{") != texto.count("}"):
        problemas.append(f"unbalanced braces: {texto.count('{')} open, "
                         f"{texto.count('}')} close")
    if texto.count("[[") != texto.count("]]"):
        problemas.append(f"unbalanced long strings: {texto.count('[[')} vs "
                         f"{texto.count(']]')}")
    if 'Page = "Style"' in texto:
        problemas.append('there are still controls on the "Style" tab')
    for nome, _, _ in NOVOS + NOVOS_TOPO + NOVOS_TEXTO + NOVOS_META:
        if f"{nome} = InstanceInput" not in texto:
            problemas.append(f"{nome} did not become an InstanceInput")
        if re.search(r"(?m)^\t+" + nome + r" = \{$", texto) is None:
            problemas.append(f"{nome} did not become a UserControl")
    if "ApplyGiStyle = [[" not in texto:
        problemas.append("ApplyGiStyle was not inserted")

    # As duas abas. Um `Page = "Extras"` sem o `ControlPage` correspondente e' o
    # pior dos dois mundos: o controle some da aba que deveria existir e vai
    # parar na primeira pagina visivel, calado.
    for aba in ("Extras", "Meta"):
        if not re.search(r"(?m)^\t+" + aba + r" = ControlPage \{", texto):
            problemas.append(f'the "{aba}" ControlPage does not exist - its '
                             f'controls would fall back into the "Text" tab')
    paginas = set(re.findall(r'(?m)^\t+Page = "([^"]*)",$', texto))
    _ABAS = {"Text", "Extras", "Meta"}
    if paginas - _ABAS:
        problemas.append(f"controls on unexpected tabs: "
                         f"{sorted(paginas - _ABAS)}")
    # A ponte tem que estar la' dentro: sem o chunk, o botao Rebuild aparece,
    # clica, e imprime "no tool owns GiRebuild" - que e' o sintoma de macro
    # velho aplicado a um macro novo.
    if "GiRebuild = [[" not in texto:
        problemas.append("GiRebuild was not inserted - the Meta tab would have "
                         "a Rebuild button with nothing behind it")

    # E um rodape por grupo de atributos. Sem o InstanceInput o botao existe e
    # nao aparece - que e' o mesmo que nao existir.
    for nome, grupo in RODAPES:
        if f"{nome} = InstanceInput" not in texto:
            problemas.append(f"{nome} (the Apply Style footer of '{grupo}') "
                             f"did not become an InstanceInput")

    # O par Get/SetInputValues e o schema. Sem esta checagem, um `InputKeys` que
    # nao foi reescrito deixa o macro carregando a lista do AutoSubs - e o
    # sintoma seria "o preset esquece metade dos controles", que so aparece
    # depois de uma rodada inteira dentro do Resolve.
    bloco_keys = _bloco("InputKeys").search(texto)
    if not bloco_keys:
        problemas.append("InputKeys is missing (SetInputValues has no schema)")
    else:
        for nome in input_keys():
            if f'"{nome}",' not in bloco_keys.group(0):
                problemas.append(f"'{nome}' is not in InputKeys - the preset "
                                 f"would silently drop it")
        for nome in ("HighlightEnabled", "HighlightStyle"):
            if f'"{nome}",' in bloco_keys.group(0):
                problemas.append(f"'{nome}' is still in InputKeys, but that "
                                 f"control was disarmed and hidden")
    for rotina in ("GetInputValues", "SetInputValues"):
        if f"{rotina} = [[" not in texto:
            problemas.append(f"{rotina} is missing - the macro has no style contract")
    m_set = re.compile(r"(?ms)^(\t+)SetInputValues = \[\[\n.*?^\1\]\],$").search(texto)
    if m_set and "UpdateAllStyleColors" not in m_set.group(0):
        problemas.append("SetInputValues still points at the AutoSubs routines "
                         "(UpdateHighlight is one of the six disarmed ones)")
    for nome in ESCONDER:
        if f"{nome} = InstanceInput" in texto:
            problemas.append(f"{nome} is still exposed in the Inspector")

    # O estilo pedido tem que estar mesmo la dentro. Sem isto, um controle que
    # o macro nao expoe (ou que mudou de nome numa versao nova deles) some em
    # silencio e o titulo nasce com a cor do exemplo do AutoSubs.
    for nome, valor in (defaults or {}).items():
        m = _bloco(nome).search(texto)
        if not m:
            problemas.append(f"control '{nome}' does not exist in the macro "
                             f"(the style asks for it, but there is nowhere to store it)")
        elif f"INP_Default = {_num(valor)}," not in m.group(0):
            problemas.append(f"'{nome}' did not end up with the style value "
                             f"({_num(valor)})")
    for chave, valor in (crus or {}).items():
        if isinstance(valor, (list, tuple)):
            continue
        v = f'"{valor}"' if isinstance(valor, str) else _num(valor)
        if f"{chave} = Input {{ Value = {v}, }}" not in texto:
            problemas.append(f"input '{chave}' did not end up as {v} on the Text+")
    return problemas


FUSCRIPT = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe"
VALIDADOR = os.path.join(_RAIZ, "giautosubs", "valida_macro.lua")


def _validar_com_fuscript(caminho):
    """Roda o valida_macro.lua no arquivo recem-escrito.

    As checagens em Python contam chaves e procuram nomes; elas nao sabem se a
    tabela COMPILA. Um campo do AutoSubs sem virgula no fim, um `]]` a mais, e
    o arquivo vira 88 KB de nada - e o Resolve nao diz por que, so nao carrega
    o titulo. O `fuscript` e' o mesmo interpretador que o Resolve usa, entao a
    opiniao dele e' a que vale. Devolve None quando esta tudo certo.
    """
    if not os.path.isfile(FUSCRIPT) or not os.path.isfile(VALIDADOR):
        return None            # sem Resolve instalado, segue sem validar
    import subprocess

    r = subprocess.run([FUSCRIPT, "-l", "lua", VALIDADOR, caminho],
                       capture_output=True, text=True,
                       cwd=os.path.dirname(VALIDADOR))
    saida = r.stdout + r.stderr

    # NAO usar o returncode: o `os.exit(1)` do validador nao chega aqui - o
    # fuscript sai 0 de qualquer jeito. Quem decide e' o texto. Isso ja deixou
    # um macro que nao compila ser instalado com "tudo certo" na tela.
    if "MACRO OK" in saida:
        return None
    if not saida.strip():
        return "      the validator printed nothing - could not run it"

    linhas = [ln for ln in saida.splitlines()
              if "FAILED" in ln or "failure(s)" in ln or "does not compile" in ln]
    return "\n".join("      " + ln.strip() for ln in linhas[:12]) or saida


def ler_estilo_exportado(caminho):
    """Le o dump que o botao "Generate Caption Style" grava.

    Formato: `chave<TAB>valor` por linha, e linhas `#chave<TAB>valor` de
    cabecalho (o nome, quando o dialogo do Fusion esteve disponivel). Valores
    sao numero, `{a,b,c}` (um ponto) ou texto.

    Devolve (nome_ou_None, controles). Quem transforma isso num estilo do
    estilos.json e' o `estilo_de_controles` do giautosubs.py - aqui so' se le.
    """
    nome, valores = None, {}
    with open(caminho, "r", encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.rstrip("\n").rstrip("\r")
            if not linha or "\t" not in linha:
                continue
            chave, valor = linha.split("\t", 1)
            if chave == "#nome":
                nome = valor.strip() or None
                continue
            if chave.startswith("#"):
                continue
            valor = valor.strip()
            if valor.startswith("{") and valor.endswith("}"):
                partes = [p for p in valor[1:-1].split(",") if p.strip()]
                valores[chave] = [float(p) for p in partes]
                continue
            try:
                valores[chave] = float(valor)
            except ValueError:
                # Font e Style sao texto; qualquer outra coisa tambem passa
                # inteira em vez de virar 0.0 calado.
                valores[chave] = valor
    return nome, valores


def importar_estilo(caminho_estilos, caminho_dump, nome=None):
    """Dump exportado -> estilo nomeado no estilos.json. Devolve o nome usado.

    Escreve com `json.dump` sobre a arvore CRUA do arquivo (nao a resolvida pelo
    `carregar_estilos`): gravar a resolvida achataria todo `herda` do arquivo em
    copias literais, e o estilos.json deixaria de ser editavel a mao.
    """
    import giautosubs as G
    from datetime import datetime

    do_arquivo, controles = ler_estilo_exportado(caminho_dump)
    nome = nome or do_arquivo
    if not nome:
        raise SystemExit(
            f"o dump em {caminho_dump} nao traz nome (o dialogo do Fusion nao\n"
            f"      esta disponivel na pagina Edit - e' esperado). Passe --nome <nome>.")

    extras = {k: controles.pop(k) for k in G.EXTRAS_DO_ESTILO if k in controles}
    if "TextPosition" in controles:
        extras["TextPosition"] = controles["TextPosition"]
    estilo = G.estilo_de_controles(controles, extras)
    estilo["_e"] = (f"Exportado do Resolve pelo botao Generate Caption Style em "
                    f"{datetime.now():%d/%m/%Y %H:%M}.")

    with open(caminho_estilos, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("estilos", {})[nome] = estilo
    with open(caminho_estilos, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return nome


def estilo_do_json(caminho, nome=None):
    """Le o estilos.json e devolve (defaults_do_inspector, inputs_do_textplus).

    Reaproveita o compilador do giautosubs.py de proposito: o macro e o
    legendas.lua tem que sair do MESMO estilo, senao o titulo arrastado da aba
    Effects e o titulo criado pelo script ficam diferentes um do outro - e
    descobrir isso leva uma rodada dentro do Resolve.
    """
    import giautosubs as G

    cfg = G.carregar_estilos(caminho)
    nome = nome or cfg.get("padrao") or next(iter(cfg["estilos"]))
    if nome not in cfg["estilos"]:
        raise SystemExit(f"estilo '{nome}' nao existe em {caminho}. "
                         f"tem: {', '.join(cfg['estilos'])}")

    inputs, controles, _ = G.compilar_estilo(cfg["estilos"][nome])

    # `_borda{n}` e `_offset{n}` nao sao inputs do Text+: sao recados pro Lua.
    # `_offset` vira `Offset{n}` (aqui da' pra usar o nome final porque o macro
    # e' escrito, nao sondado). `_borda` vira `ElementShape{n}` com o valor de
    # RESERVA - o certo so' e' conhecido dentro do Resolve, e tanto o
    # ApplyGiStyle quanto o GiAutoSubs.lua corrigem depois. Fica aqui pra o
    # titulo arrastado da aba Effects ja nascer com a caixa visivel.
    crus = {}
    for chave, valor in inputs.items():
        if chave.startswith("_offset"):
            crus["Offset" + chave[len("_offset"):]] = valor
        elif chave.startswith("_borda"):
            # Border Fill em TODOS os elementos de caixa, inclusive o 4: ele
            # nasce "Blue Border" de fabrica, que e' Border OUTLINE (3) - so o
            # contorno do retangulo, nao o retangulo. Ver FORMA_BORDA.
            crus["ElementShape" + chave[len("_borda"):]] = G.FORMA_BORDA
        elif not chave.startswith("_"):
            crus[chave] = valor

    # A animacao entra nos DOIS: nos controles (UserControl + InstanceInput) e
    # nos inputs crus do Text+. Sao os tres lugares onde o Fusion guarda um
    # default, e patchear so' um deixa os outros trazendo de volta o
    # "Word by Word" com fade do AutoSubs - a mesma armadilha do outline azul.
    controles.update(ANIMACAO)
    crus.update(ANIMACAO)
    return nome, controles, crus


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", default=None,
                    help="source macro (default: the vendored copy, then the installed one)")
    ap.add_argument("--out", default=SAIDA)
    ap.add_argument("--estilos", default=os.path.join(_RAIZ, "estilos.json"))
    ap.add_argument("--estilo", default=None,
                    help="style baked into the macro as its default "
                         "(default: the 'padrao' key of estilos.json)")
    ap.add_argument("--fixo", action="store_true",
                    help="build the FIXED-BOX variant: the text box becomes a real "
                         "rectangle (Background + RectangleMask) instead of a "
                         "border around the text, so its size never depends on the "
                         "caption. Goes to 'GiAutoSubs Fixo.setting'. Costs a "
                         "constant render per frame, which the normal macro does "
                         "not")
    ap.add_argument("--sem-validar", action="store_true",
                    help="skip running valida_macro.lua through fuscript at the end")
    ap.add_argument("--instalar", action="store_true",
                    help="copy the .setting into the Resolve Titles folder "
                         "(backing up the previous one)")
    ap.add_argument("--importar-estilo", nargs="?", const=ESTILO_EXPORTADO,
                    default=None, metavar="ARQUIVO",
                    help="read the dump written by the 'Generate Caption Style' "
                         f"button (default: {ESTILO_EXPORTADO}), add it to "
                         "estilos.json and build a Title of its own. A config "
                         f"preset from {PRESETS_DIR} works here too - same "
                         "format, same reader")
    ap.add_argument("--nome", default=None,
                    help="name for the imported style; it also names the Title "
                         "file ('GiAutoSubs <name>.setting'). Required when the "
                         "dump carries no name of its own")
    args = ap.parse_args(argv)

    # Antes de tudo: o `aplicar()` le esta global pra decidir se insere os tools da
    # caixa-retangulo.
    global COM_FIXO
    COM_FIXO = args.fixo

    # --importar-estilo roda ANTES de tudo: ele decide qual estilo sera' assado
    # e como o Title vai se chamar. Sem isto, um --out passado a mao venceria o
    # nome do estilo importado e os dois Titles brigariam pelo mesmo arquivo.
    if args.importar_estilo:
        if not os.path.isfile(args.importar_estilo):
            print(f"[!] dump not found: {args.importar_estilo}", file=sys.stderr)
            print("    click 'Generate Caption Style' on a caption first.",
                  file=sys.stderr)
            return 1
        nome = importar_estilo(args.estilos, args.importar_estilo, args.nome)
        print(f"style '{nome}' written into {args.estilos}")
        args.estilo = nome
        if args.out == SAIDA:
            args.out = os.path.join(os.path.dirname(SAIDA),
                                    f"GiAutoSubs {nome}.setting")
    elif args.fixo and args.out == SAIDA:
        args.out = os.path.join(os.path.dirname(SAIDA), "GiAutoSubs Fixo.setting")
    elif args.nome and args.out == SAIDA:
        # --nome sem importar: gera um Title proprio a partir de um estilo que
        # ja esta no estilos.json.
        args.out = os.path.join(os.path.dirname(SAIDA),
                                f"GiAutoSubs {args.nome}.setting")
        args.estilo = args.estilo or args.nome

    origens = [args.de] if args.de else [
        VENDOR,
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "AutoSubs",
                     "resources", "autosubs-macro.setting"),
    ]
    origem = next((c for c in origens if c and os.path.isfile(c)), None)
    if not origem:
        print("source macro not found. looked in:", file=sys.stderr)
        for c in origens:
            print(f"  - {c}", file=sys.stderr)
        print("download it from github.com/tmoroney/auto-subs "
              "(Resolve-Integration/autosubs-macro.setting) and pass --de",
              file=sys.stderr)
        return 1

    with open(origem, "r", encoding="utf-8") as fh:
        texto = fh.read()

    nome_estilo, defaults, crus = estilo_do_json(args.estilos, args.estilo)

    print(f"from {origem}")
    print(f"style '{nome_estilo}' ({args.estilos})")
    texto, mudancas = aplicar(texto, defaults, crus)
    for m in mudancas:
        print(("  ! " if m.startswith("WARNING") else "  + ") + m)

    problemas = _verificar(texto, defaults, crus)
    if problemas:
        print("\n[!] the macro came out broken - do NOT install it:", file=sys.stderr)
        for p in problemas:
            print(f"      {p}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)

    if not args.sem_validar:
        erro = _validar_com_fuscript(args.out)
        if erro:
            print(f"\n[!] the macro did NOT pass validation:\n{erro}", file=sys.stderr)
            print("    (it was written out anyway so you can look at it; "
                  "do not install)", file=sys.stderr)
            return 2

    print(f"\n-> {args.out}")
    if args.instalar:
        destino = _instalar(args.out)
        print(f"-> {destino}   (installed)")
    else:
        print("   copy it to %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support"
              "\\Fusion\\Templates\\Edit\\Titles\\   (or use --instalar)")
    print()
    print("   NOTE: Fusion scans the Titles folder when Resolve STARTS, so a")
    print("   .setting installed with Resolve open is not visible yet.")
    print("   Restart Resolve, then just run the script - it refreshes the")
    print("   Media Pool copy of the template on its own.")
    return 0


def _instalar(origem):
    """Copia pro Titles do Resolve, guardando o anterior."""
    import shutil
    from datetime import datetime

    pasta = os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design",
                         "DaVinci Resolve", "Support", "Fusion", "Templates",
                         "Edit", "Titles")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, os.path.basename(origem))
    if os.path.isfile(destino):
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(destino, f"{destino}.{carimbo}.bak")
    shutil.copy2(origem, destino)
    return destino


if __name__ == "__main__":
    raise SystemExit(main())
