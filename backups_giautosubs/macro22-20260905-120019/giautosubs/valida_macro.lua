--[[
Valida o macro gerado SEM abrir o Resolve.

    "C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe" -l lua valida_macro.lua
    ... valida_macro.lua <outro.setting>

Um `.setting` e' uma tabela Lua com construtores da Blackmagic
(`ordered()`, `Input {}`, `InstanceInput {}`...). Trocando esses construtores
por stubs, o proprio interpretador do Fusion diz se a tabela fecha - e um
arquivo que nao fecha, no Resolve, aparece so como "o titulo nao carrega",
sem uma linha de erro.

O que ele confere:
  1. o arquivo inteiro compila e avalia como tabela Lua
  2. cada rotina Lua guardada em CustomData compila sozinha - e' onde o erro
     fica escondido, porque o Fusion so compila aquilo na hora do clique
  3. os controles novos existem como UserControl E como InstanceInput
  4. nenhum controle sobrou na aba "Style"
  4c. as duas abas ("Text" e "Extras") existem de verdade, todo controle esta
     numa delas, e cada grupo de atributos tem seu "Apply Style" de rodape
]]

local aqui = debug.getinfo(1, "S").source:match("@(.*[\\/])") or ""
local alvo = (arg and arg[1]) or (aqui .. "GiAutoSubs Caption.setting")

local falhas = 0
local function checa(cond, msg)
	if not cond then falhas = falhas + 1; print("  FAILED: " .. msg) end
end

local fh = io.open(alvo, "r")
if not fh then
	print("could not open " .. alvo)
	os.exit(1)
end
local texto = fh:read("*a")
fh:close()
print("file: " .. alvo .. "  (" .. #texto .. " bytes)")

------------------------------------------------------------ 1. tabela fecha
-- Qualquer nome desconhecido vira um stub que aceita ser chamado. Assim
-- `ordered() { ... }` (chamada dupla) e `Input { ... }` (chamada simples)
-- passam pelo mesmo shim.
local function shim(x)
	if x == nil then return shim end
	return x
end
local ambiente = setmetatable({}, { __index = function(t, k)
	rawset(t, k, shim)
	return shim
end })

local chunk, err = loadstring("return " .. texto, "macro")
checa(chunk ~= nil, "the .setting does not compile: " .. tostring(err))

local raiz
if chunk then
	setfenv(chunk, ambiente)
	local ok, res = pcall(chunk)
	checa(ok, "the .setting does not evaluate: " .. tostring(res))
	if ok then raiz = res end
end

------------------------------------------------- 2. cada rotina Lua compila
-- As rotinas do CustomData sao codigo guardado como string: o Fusion so as
-- compila quando alguem mexe no controle. Um erro de sintaxe ali fica em
-- silencio ate o clique - e ai vira "o checkbox nao faz nada".
local rotinas, quebradas = 0, 0
-- sem virgula no fim do padrao: nem todo bloco fecha com `]],` - varios
-- ExecuteOnChange do macro original fecham so com `]]`, e exigir a virgula
-- fazia a captura passar por cima do fechamento e engolir o proximo bloco
for nome, corpo in texto:gmatch("(%w+) = %[%[\n(.-)\n%s*%]%]") do
	if corpo:find("function") or corpo:find("tool:") then
		rotinas = rotinas + 1
		local c, e = loadstring(corpo, nome)
		if not c then
			quebradas = quebradas + 1
			falhas = falhas + 1
			print("  FAILED: routine '" .. nome .. "' does not compile: " .. tostring(e))
		end
	end
end
checa(rotinas > 0, "no embedded Lua routine found - the macro changed shape")
print(string.format("  %d embedded Lua routines, %d with syntax errors",
	rotinas, quebradas))

------------------------------------------------------------ 3. controles
local NOVOS = {
	"TextCase",
	"WordFillLabel", "WordFillEnabled", "WordFillColorRed",
	"WordFillColorGreen", "WordFillColorBlue",
	"BubbleLabel", "BubbleEnabled", "BubbleColorRed", "BubbleColorGreen",
	"BubbleColorBlue", "BubbleOpacity", "BubbleLevel",
	"BubbleExtendHorizontal", "BubbleExtendVertical", "BubbleRound",
	"BubblePopEnabled", "BubblePopAmount", "BubblePopFrames",
	"TextBoxLabel", "TextBoxEnabled", "TextBoxColorRed", "TextBoxColorGreen",
	"TextBoxColorBlue", "TextBoxOpacity", "TextBoxLevel",
	"TextBoxExtendHorizontal", "TextBoxExtendVertical", "TextBoxRound",
	"BoxShadowLabel", "BoxShadowOnHighlight", "BoxShadowOnNormal",
	"BoxShadowColorRed", "BoxShadowColorGreen", "BoxShadowColorBlue",
	"BoxShadowCenterX", "BoxShadowCenterY", "BoxShadowOpacity",
	"BoxShadowSoftness",
	"ApplyStyleLabel", "ApplyStyle",
	"ConfigLabel", "ExportConfig",
}

-- Controles que existem no Inspector mas NAO no preset. `ApplyStyle` e' uma
-- acao: nao tem valor pra guardar nem pra restaurar.
local FORA_DO_PRESET = { ApplyStyle = true, ExportConfig = true }

-- `Tools` do topo tem MAIS de uma ferramenta: alem do macro esta o
-- Follower1DelaybyCharacterPosition (um BezierSpline solto). A versao
-- anterior pegava "a ultima tabela" do `pairs`, e como a ordem de `pairs`
-- muda a cada processo, o teste passava ou falhava conforme o sorteio - o
-- pior tipo de teste que existe. Aqui o macro e' escolhido pelo que ele E':
-- a unica ferramenta que tem ferramentas dentro.
local template, instancias, paginas
for _, ferramenta in pairs((raiz or {}).Tools or {}) do
	if type(ferramenta) == "table" and type(ferramenta.Tools) == "table"
		and ferramenta.Tools.Template then
		template = ferramenta.Tools.Template
		instancias = ferramenta.Inputs
		paginas = ferramenta.UserControls
	end
end
checa(template ~= nil, "the 'Template' tool was not found inside the macro")
checa(instancias ~= nil, "the macro InstanceInputs were not found")

local uc = template and template.UserControls or {}
for _, nome in ipairs(NOVOS) do
	checa(uc[nome] ~= nil, nome .. " does not exist as a UserControl")
	checa(instancias and instancias[nome] ~= nil,
		nome .. " does not exist as an InstanceInput (invisible in the Inspector)")
end

-- um LabelControl engole os N controles seguintes: contagem errada mistura
-- os grupos no Inspector.
--
-- Os numeros ja contam o `Apply Style` de RODAPE que cada grupo de atributos
-- ganhou no macro 22 - ele e' um controle do grupo como qualquer outro. Quem os
-- recalcula e' o `_recontar_grupos` do gerador; o que se confere aqui e' se o
-- resultado bate com o Inspector que foi pedido.
for _, par in ipairs({
	{ "SubtitleLabel", 7 },     -- Text, Font, Style, Case, Size, Center, Apply
	{ "ApplyStyleLabel", 3 },   -- os tres botoes; o grupo Actions nao tem rodape
	{ "AnimationLabel", 7 },
	{ "FillLabel", 5 },
	{ "OutlineLabel", 6 },
	{ "ConfigLabel", 1 },       -- ferramenta, nao estilo: sem rodape
	{ "TextBoxLabel", 10 }, { "BubbleLabel", 13 },
	{ "WordFillLabel", 5 }, { "BoxShadowLabel", 10 },
	{ "ShadowLabel", 5 },
}) do
	local l = uc[par[1]]
	checa(l and l.LBLC_NumInputs == par[2],
		par[1] .. " should group " .. par[2] .. " controls, it has "
		.. tostring(l and l.LBLC_NumInputs))
end

-- todo ComboControl precisa das opcoes DENTRO dele.
--
-- `{ CCS_AddString = "..." }` e' o que o Fusion mostra na lista. Sem nenhuma, o
-- combo aparece no Inspector, abre, e nao tem o que escolher - foi o que
-- aconteceu com os dois `Level` e com o `Case`, e o sintoma que chegou foi "o
-- Case nao funciona". A tabela do `.setting` guarda essas entradas como parte
-- ARRAY do bloco, entao contar `#c` e' contar as opcoes.
for nome, c in pairs(uc) do
	if type(c) == "table" and c.INPID_InputControl == "ComboControl" then
		checa(#c > 0, nome .. " is a ComboControl with no CCS_AddString - it "
			.. "opens empty, there is nothing to pick")
		-- `INP_MaxAllowed` maior que a lista deixaria escolher um valor sem
		-- rotulo. O contrario (mais opcoes que o maximo) e' so' desperdicio, e
		-- o macro do AutoSubs faz isso no `HighlightStyle` - nao e' erro nosso
		-- e nao vale recusar o macro por causa dele.
		checa(#c >= (c.INP_MaxAllowed or 0) + 1,
			nome .. " has " .. #c .. " options but INP_MaxAllowed lets you pick "
			.. tostring(c.INP_MaxAllowed) .. " - the top value has no label")
	end
end

-- os tres canais de uma cor precisam do MESMO IC_ControlGroup, senao viram
-- tres sliders soltos em vez de um seletor de cor
for _, pref in ipairs({ "Bubble", "TextBox", "BoxShadow" }) do
	local g = uc[pref .. "ColorRed"] and uc[pref .. "ColorRed"].IC_ControlGroup
	checa(g ~= nil, pref .. "ColorRed has no IC_ControlGroup (will not be a picker)")
	for _, canal in ipairs({ "Green", "Blue" }) do
		local c = uc[pref .. "Color" .. canal]
		checa(c and c.IC_ControlGroup == g,
			pref .. "Color" .. canal .. " is in a different colour group")
	end
	checa(uc[pref .. "ColorRed"]
		and uc[pref .. "ColorRed"].INPID_InputControl == "ColorControl",
		pref .. " is not a ColorControl")
end

--------------------------------- 3b. o contrato do macro (InputKeys + o par)
-- `InputKeys` E' o schema do estilo: `GetInputValues` le exatamente essas
-- chaves e `SetInputValues` escreve exatamente essas chaves. Um controle que
-- existe no Inspector e nao esta la e' um controle que o preset esquece - e o
-- sintoma ("mexi, salvei, e voltou ao que era") so aparece depois de uma rodada
-- inteira dentro do Resolve.
do
	local macro
	for _, ferramenta in pairs((raiz or {}).Tools or {}) do
		if type(ferramenta) == "table" and type(ferramenta.Tools) == "table"
			and ferramenta.Tools.Template then
			macro = ferramenta
		end
	end
	local cd = macro and macro.CustomData or {}
	local chaves = cd.InputKeys
	checa(type(chaves) == "table" and #chaves > 0,
		"InputKeys is missing or empty - SetInputValues would have no schema")

	local tem = {}
	for _, k in ipairs(chaves or {}) do tem[k] = true end
	for _, nome in ipairs(NOVOS) do
		if not nome:find("Label$") and not FORA_DO_PRESET[nome] then
			checa(tem[nome], nome .. " is not in InputKeys - the preset would "
				.. "silently drop it")
		end
	end
	for nome in pairs(FORA_DO_PRESET) do
		checa(not tem[nome], nome .. " is an action, it must not be in "
			.. "InputKeys (GetInputValues would store a button press)")
	end
	-- e o destaque do AutoSubs nao pode ter sobrado la: aquelas rotinas foram
	-- desarmadas, entao a chave leria nil todo dia
	for _, nome in ipairs({ "HighlightEnabled", "HighlightStyle",
		"HighlightColorRed" }) do
		checa(not tem[nome], nome .. " is still in InputKeys, but that control "
			.. "was disarmed and hidden")
	end

	-- o `SetInputValues` tem que apontar pras NOSSAS rotinas. O do AutoSubs
	-- terminava em UpdateHighlight, que aqui e' uma das seis desarmadas: o
	-- contrato compilaria, rodaria, e nao faria nada.
	local set = tostring(cd.SetInputValues or "")
	checa(set:find("UpdateAllStyleColors", 1, true) ~= nil,
		"SetInputValues does not call UpdateAllStyleColors - it is still wired "
		.. "to the AutoSubs routines")
	checa(type(cd.GetInputValues) == "string",
		"GetInputValues is missing - there is no way to read a style back")
end

------------------------------------------------------- 4. aba Style sumiu
local _, sobrou = texto:gsub('Page = "Style"', "")
checa(sobrou == 0, sobrou .. ' controls are still on the "Style" tab')

-- e a ABA em si: ela e' um ControlPage declarado a parte, entao esvaziar nao
-- basta - sem esconder o ControlPage a aba continua aparecendo, vazia
local aba = paginas and paginas.Style
checa(aba ~= nil and aba.CT_Visible == false,
	'the "Style" tab is still visible (CT_Visible = ' ..
	tostring(aba and aba.CT_Visible) .. ")")

-- e os controles do destaque do AutoSubs nao podem mais aparecer: a
-- maquinaria por tras deles foi desarmada. Os botoes "Update ..." tambem nao:
-- os controles agora avisam sozinhos.
for _, nome in ipairs({ "HighlightEnabled", "HighlightStyle", "ModifyWordTiming",
	"UpdateFillColor", "UpdateOutlineColor", "UpdateShadowColor",
	"UpdateAnimationButton", "UpdateHighlight" }) do
	checa(not instancias or instancias[nome] == nil,
		nome .. " is still exposed in the Inspector")
end

-- Nenhum botao do AutoSubs sobrou no Inspector.
--
-- As excecoes sao NOSSAS. Os botoes deles ("Update Fill Color" e companhia)
-- aplicavam um pedaco do estilo cada um, e podiam discordar entre si. Os nossos
-- nao tem como discordar: os quatro leem o estilo pelo MESMO `GetInputValues`,
-- e quem escreve e' sempre o `SetInputValues`.
--
--   ApplyStyle      aplica o estilo neste clipe
--   ApplyStyleAll   aplica o estilo deste clipe em todas as legendas (macro 20)
--   GenerateStyle   exporta o estilo deste clipe pro estilos.json  (macro 20)
--   ExportConfig    exporta o estilo deste clipe como preset da rodada (21)
local BOTOES_PERMITIDOS = {
	ApplyStyle = true, ExportConfig = true,
	ApplyStyleAll = true, GenerateStyle = true,
}

for nome, inst in pairs(instancias or {}) do
	local fonte = uc[inst.Source or ""]
	if fonte and fonte.INPID_InputControl == "ButtonControl" then
		checa(BOTOES_PERMITIDOS[inst.Source or ""],
			"the button '" .. tostring(nome) .. "' still shows in the Inspector")
	end
end

-- E o nosso botao tem que executar de verdade. Um ButtonControl declarado com
-- `INPS_ExecuteOnChange` (o atributo dos OUTROS controles) aparece no
-- Inspector, aceita o clique e nao faz nada - e o Fusion nao reclama. Quem
-- manda num botao e' `BTNCS_Execute`.
do
	local b = uc.ApplyStyle
	checa(b ~= nil, "ApplyStyle does not exist as a UserControl")
	checa(b and b.INPID_InputControl == "ButtonControl",
		"ApplyStyle is not a ButtonControl")
	checa(b and type(b.BTNCS_Execute) == "string",
		"ApplyStyle has no BTNCS_Execute - it would be a button that does "
		.. "nothing (INPS_ExecuteOnChange does not fire on a button)")
	checa(b and tostring(b.BTNCS_Execute or ""):find("SetInputValues", 1, true) ~= nil,
		"ApplyStyle does not go through SetInputValues - a second write path "
		.. "is a second place for 'it had no effect' to hide")
end

------------------------------------------------------- 4c. as duas abas
--
-- A aba nao nasce do `Page = "Extras"` dos InstanceInput: isso so' diz onde o
-- controle mora. A ABA e' um `ControlPage` no UserControls do MACRO - a mesma
-- camada por causa da qual a aba "Style" continuava aparecendo depois de
-- esvaziada. Sem o ControlPage, todo mundo com `Page = "Extras"` cai calado na
-- primeira pagina visivel, e o Inspector volta a ter uma aba so'.
local ABAS = { Text = true, Extras = true }
do
	local extras = paginas and paginas.Extras
	checa(extras ~= nil,
		'the "Extras" ControlPage does not exist - the controls sent there would '
		.. 'fall back into "Text"')
	checa(extras == nil or extras.CT_Visible ~= false,
		'the "Extras" tab exists but is hidden (CT_Visible = false)')
end

-- todo InstanceInput tem que dizer em que aba esta: sem `Page` ele cai na
-- primeira pagina visivel, o que hoje da' certo por acidente
for nome, inst in pairs(instancias or {}) do
	checa(ABAS[tostring(inst.Page)] ~= nil,
		nome .. ' is on the "' .. tostring(inst.Page)
		.. '" tab, which is neither "Text" nor "Extras"')
end

-- E um `Apply Style` no rodape de cada grupo de atributos.
--
-- Sao INSTANCIAS do mesmo botao (`Source = "ApplyStyle"`), nao botoes novos -
-- um segundo corpo de codigo seria um segundo lugar pra divergir. Sem o
-- InstanceInput o botao existe e nao aparece, que e' o mesmo que nao existir.
for _, par in ipairs({
	{ "ApplyStyleText", "Text" }, { "ApplyStyleAnimation", "Animation" },
	{ "ApplyStyleFill", "Fill" }, { "ApplyStyleOutline", "Outline" },
	{ "ApplyStyleTextBox", "Text Box" }, { "ApplyStyleBubble", "Bubble" },
	{ "ApplyStyleWordFill", "Spoken Word" },
	{ "ApplyStyleBoxShadow", "Box Shadow" },
	{ "ApplyStyleShadow", "Shadow / Glow" },
}) do
	local inst = instancias and instancias[par[1]]
	checa(inst ~= nil,
		"the Apply Style footer of the '" .. par[2] .. "' group is missing")
	checa(inst == nil or inst.Source == "ApplyStyle",
		par[1] .. " points at '" .. tostring(inst and inst.Source)
		.. "' instead of the one ApplyStyle button")
end

-- e NENHUM controle pode reagir sozinho.
--
-- Ate a versao 10 este teste era o inverso: cada controle tinha que trazer seu
-- `INPS_ExecuteOnChange`. Duas medidas viraram a regra do avesso - o callback
-- dispara a cada valor intermediario de um arrasto de slider (~40 por ajuste),
-- e o `tool` que ele recebe e' o Text+ interno, onde o codigo do macro NAO
-- mora: metade dos disparos so' sabia imprimir "nothing was applied". Hoje quem
-- aplica e' o botao, e um callback sobrevivente seria um segundo caminho,
-- invisivel, disparado sem ninguem pedir.
do
	local sobraram = {}
	for nome, c in pairs(uc) do
		if type(c) == "table" and c.INPS_ExecuteOnChange ~= nil then
			sobraram[#sobraram + 1] = nome
		end
	end
	checa(#sobraram == 0, #sobraram .. " control(s) still react on their own ("
		.. table.concat(sobraram, ", ") .. ") - Apply Style is the only way in")
end

------------------------- 4b. o spline nao pode ficar SEM keyframe
-- Spline vazio nao tem valor em tempo nenhum, e o Fusion responde com
-- "CharacterLevelStyling1 cannot get Parameter ... at time N". O erro sobe pela
-- cadeia (Follower1 -> MediaOut1) e a legenda para de renderizar - com o
-- Console cuspindo tres linhas por frame. Um keyframe com array vazio e' o
-- estado neutro correto; zero keyframes e' um macro quebrado.
do
	local spline
	for _, ferramenta in pairs((raiz or {}).Tools or {}) do
		if type(ferramenta) == "table" and type(ferramenta.Tools) == "table" then
			for nome, t in pairs(ferramenta.Tools) do
				if tostring(nome):find("CharacterLevelStyling")
					and tostring(nome):find("Animate") then
					spline = t
				end
			end
		end
	end
	checa(spline ~= nil, "the character-level styling spline was not found")
	local n = 0
	for _ in pairs((spline or {}).KeyFrames or {}) do n = n + 1 end
	checa(n >= 1,
		"the character-level styling spline has NO keyframes - every caption "
		.. "would fail to render")
end

------------------------------------- 5. o outline tem que nascer preto
local ins = template and template.Inputs or {}
for _, canal in ipairs({ "Red2", "Green2", "Blue2" }) do
	checa(ins[canal] and tonumber(ins[canal].Value) == 0,
		canal .. " should start at 0 (black), it is "
		.. tostring(ins[canal] and ins[canal].Value))
end
for _, canal in ipairs({ "Red", "Green", "Blue" }) do
	local c = uc["OutlineColor" .. canal]
	checa(c and tonumber(c.INP_Default) == 0,
		"OutlineColor" .. canal .. " default should be 0, it is "
		.. tostring(c and c.INP_Default))
	local i = instancias and instancias["OutlineColor" .. canal]
	checa(i and tonumber(i.Default) == 0,
		"InstanceInput OutlineColor" .. canal .. " default should be 0, it is "
		.. tostring(i and i.Default))
end

print(falhas == 0 and "MACRO OK" or (falhas .. " failure(s)"))
os.exit(falhas == 0 and 0 or 1)
