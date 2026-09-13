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

# A terceira cor da caixa e' uma VARIANTE, nao parte do macro padrao.
#
# O `GiAutoSubs Caption` continua sendo o macro de sempre: quem nao usa caixa de
# tres cores nao ganha um grupo a mais no Inspector, e um macro que ja mora
# dentro de centenas de clipes nao muda de forma sem necessidade. A variante sai
# com `--camada3`, num Title proprio (`GiAutoSubs 3color.setting`).
#
# Ligado, isto acrescenta: os controles do grupo `Box Layer 3`, a rotina
# `camada3` do ApplyGiStyle, e a entrada [8] do LIGA no GiRebuildHighlight.
COM_CAMADA3 = False

# O spin e' uma variante DA variante: sai com `--spin` (que implica `--camada3`),
# num Title proprio (`GiAutoSubs 3color_spinning.setting`). Acrescenta um
# controle so' - `BoxSpinSpeed` - porque raio e fase da orbita ja' estao no
# offset que o usuario ajustou. Em 0 o macro se comporta como o 3color.
COM_SPIN = False

_NOMES_SPIN = ("BoxSpinSpeed",)

# Os nomes que a variante publica. Tem que sair das QUATRO listas juntas
# (UserControls, InstanceInputs, LAYOUT, rodapes) - o validador recusa um
# controle que exista numa e falte na outra, e e' assim que se descobre que
# faltou tirar de alguma.
_NOMES_CAMADA3 = (
    "BoxLayer3Label", "BoxLayer3Enabled",
    "BoxLayer3ColorRed", "BoxLayer3ColorGreen", "BoxLayer3ColorBlue",
    "BoxLayer3CenterX", "BoxLayer3CenterY", "BoxLayer3Alpha",
    "ApplyStyleBoxLayer3",
)


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
return function(comp, tool, origem, spline)
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

__SPIN_DEF__
	-- O SPIN: as duas cores extras ORBITANDO o texto em vez de paradas.
	--
	-- Gira o DESLOCAMENTO, nao a geometria. Rotacionar o retangulo deixaria a
	-- caixa base reta e as coloridas em losango por tras dela - canto em angulo
	-- aleatorio le como defeito, nao como estilo. Com as tres caixas alinhadas e
	-- o vetor de offset percorrendo um circulo, a borda colorida orbita o texto:
	-- e' o efeito parado de hoje, animado.
	--
	-- Raio e fase saem do offset que o usuario JA ajustou no Inspector - o par
	-- (x,y) e' um vetor, tem os dois dentro. Por isso a variante acrescenta UM
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
__FIM_SPIN_DEF__

	local function caixa(n, prefixo, ligada)
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
			pin(n, "ExtendHorizontal", ctl(prefixo .. "ExtendHorizontal", 0))
			pin(n, "ExtendVertical", ctl(prefixo .. "ExtendVertical", 0))
		end
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
	end

	-- A sombra copia a GEOMETRIA da caixa e muda so cor, opacidade, borrao e
	-- deslocamento. Sombra de tamanho diferente entrega que sao dois
	-- elementos empilhados em vez de uma caixa com sombra.
	local function sombra(n, prefixo, ligada)
		pin(n, "Enabled", ligada and 1 or 0)
		if not ligada then return end
		pin(n, "ElementShape", BORDA)
		pin(n, "Red", ctl("BoxShadowColorRed", 0))
		pin(n, "Green", ctl("BoxShadowColorGreen", 0))
		pin(n, "Blue", ctl("BoxShadowColorBlue", 0))
		pin(n, "Opacity", ctl("BoxShadowOpacity", 0.55))
		pin(n, "Softness", ctl("BoxShadowSoftness", 2))
		pin(n, "Level", ctl(prefixo .. "Level", 2))
		pin(n, "ExtendHorizontal", ctl(prefixo .. "ExtendHorizontal", 0))
		pin(n, "ExtendVertical", ctl(prefixo .. "ExtendVertical", 0))
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
		-- Offset, nao Position: Position e' coordenada ABSOLUTA e joga o
		-- elemento pro canto da tela.
__SEM_SPIN_SOMBRA__
		pin(n, "Offset", { ctl("BoxShadowCenterX", 0.005),
			ctl("BoxShadowCenterY", -0.007) })
__FIM_SEM_SPIN_SOMBRA__
__SPIN_SOMBRA__
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
__FIM_SPIN_SOMBRA__
	end

__CAMADA3_DEF__
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
		pin(n, "ExtendHorizontal", ctl(prefixo .. "ExtendHorizontal", 0))
		pin(n, "ExtendVertical", ctl(prefixo .. "ExtendVertical", 0))
		pin(n, "Round", ctl(prefixo .. "Round", 0.2))
__SEM_SPIN_CAMADA3__
		pin(n, "Offset", { ctl("BoxLayer3CenterX", -0.005),
			ctl("BoxLayer3CenterY", 0.007) })
__FIM_SEM_SPIN_CAMADA3__
__SPIN_CAMADA3__
		deslocar(n, ctl("BoxLayer3CenterX", -0.005),
			ctl("BoxLayer3CenterY", 0.007))
__FIM_SPIN_CAMADA3__
	end
__FIM_CAMADA3_DEF__

	-- Um Lock so' pra escrita: sem ele o Fusion re-avalia a arvore a cada
	-- SetInput, e sao dezenas por disparo. O Unlock tem que acontecer mesmo se
	-- algo levantar no meio, senao a composicao fica travada na cara do
	-- usuario - dai o pcall em volta.
	local travou = pcall(function() comp:Lock() end)
	local ok, erro = pcall(function()
		local bolha = ctl("BubbleEnabled", 0) == 1
		caixa(__EL_BOLHA__, "Bubble", bolha)
		sombra(__EL_BOLHA_SOMBRA__, "Bubble", bolha and ctl("BoxShadowOnHighlight", 0) == 1)

		local cx = ctl("TextBoxEnabled", 0) == 1
		caixa(__EL_CAIXA__, "TextBox", cx)
		sombra(__EL_CAIXA_SOMBRA__, "TextBox", cx and ctl("BoxShadowOnNormal", 0) == 1)
__CAMADA3_CALL__
		-- Depende da caixa: terceira cor de caixa que nao existe nao e' nada.
		camada3(__EL_CAMADA3__, "TextBox", cx and ctl("BoxLayer3Enabled", 0) == 1)
__FIM_CAMADA3_CALL__
	end)
	if travou then pcall(function() comp:Unlock() end) end
	if not ok then
		diga("[GiAutoSubs] " .. origem .. " -> ApplyGiStyle FAILED: " .. tostring(erro))
		return
	end

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
__CAMADA3_LIGA__
		-- Hoje nenhum estilo anima a terceira cor (ela e' estatica, como a
		-- caixa). A entrada existe pra que, no dia em que um animar, o checkbox
		-- valha - sem ela o array devolveria `Enabled8 = 1` por cima do input,
		-- que e' exatamente o bug que a bolha teve.
		[8] = { "TextBoxEnabled", "BoxLayer3Enabled" },
__FIM_CAMADA3_LIGA__
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

	local function transformar(s, modo)
		if modo == 1 then return minuscula(s) end
		if modo == 2 then return maiuscula(s) end
		return s
	end

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


def _recortar(texto, abre, fecha, manter=None):
    """Mantem ou remove um trecho marcado.

    `manter=None` = conforme `COM_CAMADA3`. Marcador em linha propria nos dois
    lados. Fora da variante o bloco inteiro sai; dentro dela sai so' o marcador.
    Isso e' o que faz o `GiAutoSubs Caption` voltar a ser exatamente o macro de
    antes da camada 3, em vez de carregar uma rotina inerte que ninguem chama.

    Os pares invertidos (`__SEM_SPIN_*__` / `__SPIN_*__`) existem pelo mesmo
    motivo: com o spin, dois pontos do ApplyGiStyle passam a chamar `deslocar`
    em vez de `pin`. Trocar o corpo em vez de embrulhar deixa o Caption e o
    3color byte a byte como estao - um macro que ja' mora dentro de centenas de
    clipes nao muda de forma por conveniencia de quem gera.
    """
    padrao = re.compile(
        r"^[ \t]*" + re.escape(abre) + r"[ \t]*\n(.*?)"
        r"^[ \t]*" + re.escape(fecha) + r"[ \t]*\n",
        re.S | re.M)
    if not padrao.search(texto):
        raise SystemExit(f"marcador {abre} nao encontrado - o macro mudou de forma")
    fica = COM_CAMADA3 if manter is None else manter
    return padrao.sub((lambda m: m.group(1)) if fica else "", texto)


def _apply_gi():
    # ORDEM: os recortes do spin ANTES dos da camada 3. O par
    # `__SEM_SPIN_CAMADA3__` mora DENTRO do bloco `__CAMADA3_DEF__`, entao tirar
    # a camada 3 primeiro leva os marcadores junto - e o `_recortar` levanta
    # "marcador nao encontrado" na geracao do proprio Caption. Marcador aninhado
    # se resolve de dentro pra fora.
    corpo = _recortar(_APPLY_GI, "__SPIN_DEF__", "__FIM_SPIN_DEF__", COM_SPIN)
    for sufixo in ("SOMBRA", "CAMADA3"):
        corpo = _recortar(corpo, f"__SEM_SPIN_{sufixo}__",
                          f"__FIM_SEM_SPIN_{sufixo}__", not COM_SPIN)
        corpo = _recortar(corpo, f"__SPIN_{sufixo}__",
                          f"__FIM_SPIN_{sufixo}__", COM_SPIN)
    corpo = _recortar(corpo, "__CAMADA3_DEF__", "__FIM_CAMADA3_DEF__")
    corpo = _recortar(corpo, "__CAMADA3_CALL__", "__FIM_CAMADA3_CALL__")
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

-- O nome. O AskUser do Fusion nao e' confiavel a partir da pagina Edit (ver
-- SpeakerSwitch.py) - ele existe como atributo e vem nil. Entao ele e' TENTADO,
-- e cada destino decide o que fazer quando nao vem nada (ver logo abaixo).
local nome
pcall(function()
	local ui = comp and comp.AskUser and comp:AskUser("__ROTULO__", {
		{ "Nome", Name = "__CAMPO__", "Text", Default = "" },
	})
	if ui then nome = ui.Nome end
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
if not nome then nome = "preset-" .. os.date("%Y%m%d-%H%M%S") end
local seguro = nome:gsub("[^%w%-_ ]", "_")
pcall(function() bmd.createdir("__PRESETS__") end)
local destino = "__PRESETS__" .. "\\\\" .. seguro .. ".txt"
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


def _exportar(rotulo, campo, destino, fecho):
    """Monta o corpo de um dos dois botoes de exportar."""
    return (_com_log(_EXPORTAR)
            .replace("__DESTINO__", destino.strip("\n"))
            .replace("__FECHO__", fecho.strip("\n"))
            .replace("__ROTULO__", rotulo)
            .replace("__CAMPO__", campo))


def _exportar_config():
    return _exportar("Export Config", "Config name",
                     _DESTINO_PRESET.replace("__PRESETS__",
                                             PRESETS_DIR.replace("\\", "\\\\")),
                     _FECHO_PRESET)


def _exportar_estilo():
    return _exportar("Generate Caption Style", "Style name",
                     _DESTINO_ESTILO.replace(
                         "__ESTILO__", ESTILO_EXPORTADO.replace("\\", "\\\\")),
                     _FECHO_ESTILO)


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

        _rotulo("TextBoxLabel", "Text Box", 9),
        _checkbox("TextBoxEnabled", "Enabled"),
        _cor("TextBox", "Text Box Color", GRUPO_CAIXA, (0, 0, 0)),
        _slider("TextBoxOpacity", "Opacity", 0.45, 0, 1),
        # 1 = Line. A caixa do texto envolve a LINHA; a bolha (elemento 4)
        # envolve a palavra falada, dai o 2 dela. Era 3 aqui, que na lista real
        # e' Character - uma caixa por letra.
        _combo("TextBoxLevel", "Level", _NIVEIS, 1),
        _slider("TextBoxExtendHorizontal", "Extend Horizontal", 0.2, -0.5, 2),
        _slider("TextBoxExtendVertical", "Extend Vertical", 0.12, -0.5, 2),
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
    if COM_CAMADA3:
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
        if COM_SPIN:
            # GRAUS POR FRAME. A 30fps, 2 da' uma volta a cada 6 segundos - lento
            # o bastante pra ler como movimento intencional. A legenda fica 1 a 3
            # segundos na tela, entao cada uma mostra meia volta ou menos e o olho
            # le deriva suave em vez de rodopio. Acima de ~6 vira estroboscopio e
            # o texto cansa de ler no volume que este projeto produz - dai o teto
            # em 10 em vez de 360.
            i = partes.index(_slider("BoxLayer3Alpha", "Alpha", 1, 0, 1))
            partes.insert(i + 1,
                          _slider("BoxSpinSpeed", "Spin Speed", 2, 0, 10))
    return "\n".join(partes)


def controles_texto():
    """O que entra DENTRO do grupo "Text" do AutoSubs, junto de Font e Style.

    Um combo de tres estados, nao dois checkboxes: com checkboxes existe o
    estado "os dois marcados", que nao quer dizer nada e obriga alguem a decidir
    quem ganha. Aqui o estado invalido nao e' expressavel, e o padrao ("As
    typed") diz por escrito que nao mexe em nada - dois checkboxes desmarcados
    dizem isso por ausencia.
    """
    return _combo("TextCase", "Case", ("As typed", "lowercase", "UPPERCASE"), 0)


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
        "TextBoxLabel", "TextBoxEnabled",
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
_FORA_DO_PRESET = {"GiAutoSubsVersao", "ApplyStyle", "ExportConfig",
                   "ApplyStyleTrack", "ApplyStyleAll", "GenerateStyle"}


def input_keys():
    """O schema completo: os controles do AutoSubs que sobraram + os nossos.

    `NOVOS_TEXTO` entra aqui junto com o resto: um controle que existe no
    Inspector e nao no `InputKeys` funciona ate' voce rodar o script, e ai volta
    calado pro que era. O validador recusa o macro antes disso.
    """
    novos = [nome for nome, _, _ in NOVOS + NOVOS_TEXTO
             if not nome.endswith("Label") and nome not in _FORA_DO_PRESET]
    return list(_INPUT_KEYS_BASE) + novos


# As listas COMPLETAS, congeladas na importacao. E' delas que cada rodada deriva
# o que publica - nunca do que a rodada anterior deixou.
_NOVOS_COM3 = tuple(NOVOS)
_RODAPES_COM3 = tuple(RODAPES)
_LAYOUT_COM3 = tuple((pagina, tuple(nomes)) for pagina, nomes in LAYOUT)


def _publicar_controles(com_camada3, com_spin=False):
    """Recompoe as tres listas que publicam controles, nos DOIS sentidos.

    Sao tres e elas tem que concordar: `NOVOS` vira InstanceInput e InputKeys,
    `RODAPES` vira o Apply Style do grupo, e `LAYOUT` decide aba e ordem. Um
    controle que sobrasse numa delas viraria "existe e nao faz nada" - por isso
    a decisao mora num lugar so.

    DERIVA das listas congeladas em vez de filtrar as atuais, e e' o ponto: a
    versao anterior removia por efeito colateral, sem volta. Dois `main()` no
    mesmo processo - um script que gerasse as duas variantes num laco, que e' o
    proximo passo natural - fariam o Caption esvaziar as listas e o `3color`
    seguinte nascer SEM os controles que sao a razao dele existir. Com o estilo
    `caixa_tres_cores` o validador ainda pegaria ("nowhere to store it"); com
    `--camada3 --estilo capcut_bolha` nao ha quem reclame, e sai um `3color` que
    e' o Caption com outro nome.
    """
    global NOVOS, RODAPES, LAYOUT
    fora = set()
    if not com_camada3:
        fora.update(_NOMES_CAMADA3)
    if not com_spin:
        fora.update(_NOMES_SPIN)
    NOVOS = [t for t in _NOVOS_COM3 if t[0] not in fora]
    RODAPES = [t for t in _RODAPES_COM3 if t[0] not in fora]
    LAYOUT = [(pagina, [n for n in nomes if n not in fora])
              for pagina, nomes in _LAYOUT_COM3]


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
                        ("GiRebuildHighlight", _com_log(_recortar(
                            _REBUILD, "__CAMADA3_LIGA__", "__FIM_CAMADA3_LIGA__"))),
                        ("GiBubblePop", _pop()),
                        ("GiApplyText", _com_log(_CASE))):
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
                               + controles_topo() + "\n" + controles_texto(), 6),
                          mudancas, "the new controls")
    mudancas.append(f"{len(NOVOS) + len(NOVOS_TOPO) + len(NOVOS_TEXTO)} new "
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
                    + "\n" + instance_inputs_rodape(), 4), mudancas)
    mudancas.append(f"InstanceInputs (the new controls showing up on the clip, "
                    f"including {len(RODAPES)} Apply Style footers)")

    # 8b) a aba Extras, que precisa existir ANTES de alguem morar nela
    texto = _criar_aba_extras(texto, mudancas)

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
    for nome, _, _ in NOVOS + NOVOS_TOPO + NOVOS_TEXTO:
        if f"{nome} = InstanceInput" not in texto:
            problemas.append(f"{nome} did not become an InstanceInput")
        if re.search(r"(?m)^\t+" + nome + r" = \{$", texto) is None:
            problemas.append(f"{nome} did not become a UserControl")
    if "ApplyGiStyle = [[" not in texto:
        problemas.append("ApplyGiStyle was not inserted")

    # As duas abas. Um `Page = "Extras"` sem o `ControlPage` correspondente e' o
    # pior dos dois mundos: o controle some da aba que deveria existir e vai
    # parar na primeira pagina visivel, calado.
    if not re.search(r"(?m)^\t+Extras = ControlPage \{", texto):
        problemas.append('the "Extras" ControlPage does not exist - its controls '
                         'would fall back into the "Text" tab')
    paginas = set(re.findall(r'(?m)^\t+Page = "([^"]*)",$', texto))
    if paginas - {"Text", "Extras"}:
        problemas.append(f"controls on unexpected tabs: "
                         f"{sorted(paginas - {'Text', 'Extras'})}")

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
    ap.add_argument("--camada3", action="store_true",
                    help="build the three-colour-box variant: adds the "
                         "'Box Layer 3' group (element 8) to the Inspector. "
                         "Goes to its own Title ('GiAutoSubs 3color.setting') "
                         "so the default Caption macro stays as it was")
    ap.add_argument("--spin", action="store_true",
                    help="build the spinning variant: the two extra box "
                         "colours orbit the text ('Spin Speed', in degrees per "
                         "frame; 0 = the still 3color). Implies --camada3 and "
                         "goes to 'GiAutoSubs 3color_spinning.setting'")
    args = ap.parse_args(argv)

    # Antes de tudo: a variante muda o que os controles(), o LAYOUT e o
    # ApplyGiStyle produzem, e todos sao lidos mais abaixo.
    global COM_CAMADA3, COM_SPIN
    COM_SPIN = args.spin
    # Girar UMA cor so' nao e' o efeito: o que se ve e' a segunda e a terceira
    # trocando de lado. Sem a camada 3 o spin nao teria o que orbitar.
    COM_CAMADA3 = args.camada3 or COM_SPIN
    _publicar_controles(COM_CAMADA3, COM_SPIN)
    if COM_CAMADA3 and args.out == SAIDA and not args.nome and not args.importar_estilo:
        # Um Title proprio: o padrao continua sendo o macro de sempre.
        args.nome = "3color_spinning" if COM_SPIN else "3color"
        args.estilo = args.estilo or "caixa_tres_cores"

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
