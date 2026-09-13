--[[
GiDiag - diagnostico SOMENTE LEITURA das legendas do GiAutoSubs.

    Workspace > Scripts > GiDiag
    A saida vai pro Console: Workspace > Console

Nao escreve nada. Nao cria clipe, nao apaga, nao muda input nenhum.

Responde uma pergunta so: o clipe que esta na sua timeline conhece os
controles novos do Inspector, ou e' uma copia de um macro antigo?

Um titulo do Fusion guarda uma COPIA do macro dentro do clipe, de quando ele
nasceu. Reinstalar o `.setting` nao atualiza clipe existente - por isso o
`gerar_macro.py` carimba `GiAutoSubsVersao` no macro: e' assim que da' pra
saber a idade de cada clipe sem adivinhar.

Convencao do projeto: COMENTARIOS em portugues sem acento; MENSAGENS em ingles.
]]

-- Versao do macro que esta hoje em Templates/Edit/Titles. Lida do proprio
-- .setting instalado, nao chutada aqui: numero copiado a mao envelhece calado,
-- e um diagnostico que mente sobre a referencia e' pior que nenhum.
local MACRO_INSTALADO = os.getenv("APPDATA") ..
	[[\Blackmagic Design\DaVinci Resolve\Support\Fusion\Templates\Edit\Titles\GiAutoSubs Caption.setting]]

local function versao_no_disco()
	local fh = io.open(MACRO_INSTALADO, "r")
	if not fh then return nil end
	local texto = fh:read("*a")
	fh:close()
	-- o carimbo e' um UserControl; o numero e' o INP_Default logo abaixo dele
	local trecho = texto:match("GiAutoSubsVersao = {(.-)}")
	local v = trecho and trecho:match('INP_Default%s*=%s*"?(%d+)"?')
	return v and tonumber(v) or nil
end

local VERSAO_ESPERADA = versao_no_disco()

-- Quantos clipes descrever por inteiro. O resto vira so contagem.
local MAX_DETALHE = 3


-- Alem do Console, tudo vai pra arquivo: o diagnostico passa de cem linhas e
-- o Console do Resolve nao deixa copiar isso.
local LOG = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_gidiag.log]]

local function _para_arquivo(linha, modo)
	local fh = io.open(LOG, modo or "a")
	if not fh then return end
	fh:write(linha, "\n")
	fh:close()
end

_para_arquivo("=== GiDiag " .. os.date("%Y-%m-%d %H:%M:%S") .. " ===", "w")

local function log(s)
	local linha = "[GiDiag] " .. tostring(s)
	print(linha)
	_para_arquivo(linha)
end

-- Como chegar no Resolve depende de ONDE o script roda (mesmo caminho do
-- GiAutoSubs.lua).
local function obter_resolve()
	local tentativas = {
		{ "Resolve()", function() return Resolve and Resolve() end },
		{ "resolve", function() return resolve end },
		{ "bmd.scriptapp", function() return bmd and bmd.scriptapp and bmd.scriptapp("Resolve") end },
		{ "app", function() return app end },
	}
	for _, t in ipairs(tentativas) do
		local ok, r = pcall(t[2])
		if ok and r then
			log("Resolve obtained via " .. t[1])
			return r
		end
	end
	return nil
end

-- GetInput num input que nao existe devolve nil; num tool errado, levanta.
-- Os dois casos interessam, e nenhum pode derrubar o diagnostico.
local function gin(tool, nome)
	if not tool then return nil end
	local v
	local ok = pcall(function() v = tool:GetInput(nome) end)
	if not ok then return nil end
	return v
end

local function fmt(v)
	if v == nil then return "MISSING" end
	if type(v) == "number" then return string.format("%.4g", v) end
	if type(v) == "string" then
		if #v > 40 then v = v:sub(1, 40) .. "..." end
		return '"' .. v .. '"'
	end
	return tostring(v)
end

-- Quantos keyframes tem o spline de character-level styling. Zero significa
-- que a legenda nao renderiza em tempo nenhum (o erro "cannot get Parameter").
local function keyframes_do_spline(comp, follower)
	if not follower then return nil, "no Follower1" end
	local kfs
	local ok = pcall(function()
		local cls = follower.Text:GetConnectedOutput():GetTool()
		local spline = cls.CharacterLevelStyling:GetConnectedOutput():GetTool()
		kfs = spline:GetKeyFrames()
	end)
	if not ok or not kfs then return nil, "could not be read" end
	local n = 0
	for _ in pairs(kfs) do n = n + 1 end
	return n
end


log("read-only diagnostic. Nothing is written.")

local app = obter_resolve()
if not app then
	log("Resolve NOT found - run this from Workspace > Scripts.")
	return
end

local project = app:GetProjectManager():GetCurrentProject()
if not project then log("no project open."); return end
local timeline = project:GetCurrentTimeline()
if not timeline then log("no timeline open."); return end

log("timeline: " .. tostring(timeline:GetName()))
log("macro version installed on disk: " ..
	(VERSAO_ESPERADA and tostring(VERSAO_ESPERADA)
	 or "could not read " .. MACRO_INSTALADO))

-- Varre TODAS as tracks e aceita qualquer Text+, com ou sem carimbo. O clipe
-- sem carimbo e' exatamente o que a gente esta procurando, entao filtrar por
-- carimbo aqui esconderia a resposta.
local total = timeline:GetTrackCount("video")
log("video tracks: " .. tostring(total))

local achados = {}
for track = total, 1, -1 do
	local itens
	pcall(function() itens = timeline:GetItemListInTrack("video", track) end)
	for _, item in ipairs(itens or {}) do
		pcall(function()
			if (item:GetFusionCompCount() or 0) < 1 then return end
			local comp = item:GetFusionCompByIndex(1)
			if not comp then return end
			local tool = comp:FindTool("Template")
			local via = "Template"
			if not tool then
				tool = comp:FindToolByID("TextPlus")
				via = "TextPlus (fallback)"
			end
			if not tool then return end
			local inicio
			pcall(function() inicio = item:GetStart() end)
			achados[#achados + 1] = {
				item = item, track = track, comp = comp, tool = tool,
				via = via, inicio = inicio or 0,
				nome = (item.GetName and item:GetName()) or "?",
			}
		end)
	end
end

table.sort(achados, function(a, b) return a.inicio < b.inicio end)
log(#achados .. " clip(s) with a Text+ found")
if #achados == 0 then
	log("nothing to inspect. Is the subtitle track disabled or the timeline empty?")
	return
end

-- Distribuicao dos carimbos: e' a resposta curta.
local por_versao = {}
for _, a in ipairs(achados) do
	local v = gin(a.tool, "GiAutoSubsVersao")
	a.versao = v
	local chave = (v == nil) and "no stamp (old macro)" or tostring(v)
	por_versao[chave] = (por_versao[chave] or 0) + 1
end

log("")
log("--- stamp distribution ---")
for chave, n in pairs(por_versao) do
	log(string.format("  %-24s %d clip(s)", chave, n))
end

-- Legendas em DUAS tracks explicam sozinhas um "mexo e nao muda": voce edita
-- a de baixo e a de cima e' que aparece. 128 criadas contra 129 achadas ja
-- diz que sobrou clipe de alguma rodada anterior.
local por_track = {}
for _, a in ipairs(achados) do
	por_track[a.track] = (por_track[a.track] or 0) + 1
end
log("")
log("--- captions per track ---")
for track = total, 1, -1 do
	if por_track[track] then
		log(string.format("  V%-3d %d clip(s)", track, por_track[track]))
	end
end

log("")
log("--- detail (first " .. MAX_DETALHE .. ") ---")
for i = 1, math.min(MAX_DETALHE, #achados) do
	local a = achados[i]
	local follower = a.comp:FindTool("Follower1")

	log(string.format("clip %d  V%d  start=%s  %s  [Text+ via %s]",
		i, a.track, tostring(a.inicio), a.nome, a.via))
	log("    GiAutoSubsVersao   : " .. fmt(a.versao))
	local temApply
	pcall(function() temApply = a.tool:GetData("ApplyGiStyle") end)
	log("    ApplyGiStyle data  : " .. ((temApply ~= nil) and "present" or "ABSENT"))
	log("    Follower1          : " .. (follower and "present" or "ABSENT"))

	-- Se estes controles vierem MISSING, o Inspector desse clipe nao tem o
	-- que voce esta tentando mexer - nenhum ajuste ali podia funcionar.
	log("    new Inspector controls:")
	for _, nome in ipairs({ "OutlineThickness", "OutlineEnabled",
		"BoxShadowOnNormal", "BoxShadowOnHighlight", "BubbleEnabled",
		"TextBoxEnabled", "GiDebug" }) do
		log(string.format("        %-22s %s", nome, fmt(gin(a.tool, nome))))
	end

	-- O que de fato decide o desenho. Template e Follower1 diferentes = o
	-- Follower ganha, e mexer no Inspector nao muda a tela.
	log("    render values        Template / Follower1:")
	for _, nome in ipairs({ "Enabled1", "Enabled2", "Thickness2",
		"Red2", "Green2", "Blue2", "Enabled5", "Enabled6" }) do
		log(string.format("        %-22s %s / %s", nome,
			fmt(gin(a.tool, nome)), fmt(gin(follower, nome))))
	end

	local n, erro = keyframes_do_spline(a.comp, follower)
	log("    char-level spline  : " ..
		(n and (n .. " keyframe(s)" .. (n == 0 and "  <-- renders nothing" or ""))
		    or ("could not read (" .. tostring(erro) .. ")")))
	log("")
end

-- ONDE MORA O CODIGO DOS CALLBACKS
--
-- No `.setting`, os chunks (UpdateTextContent do AutoSubs, ApplyGiStyle nosso)
-- ficam no CustomData do MacroOperator, mas os controles que os chamam ficam
-- no Text+ ("Template"), e o callback faz `tool:GetData(...)`. Se `tool` for o
-- Text+ e o CustomData estiver no macro, GetData volta nil e o callback
-- desiste em silencio - que e' exatamente o sintoma.
--
-- Isto aqui varre TODOS os tools do clipe e diz quem responde por cada chave.
local CHAVES = {
	"ApplyGiStyle", "GiRebuildHighlight", "UpdateAllStyleColors",
	"UpdateTextContent", "UpdateStyleColor", "SetAnimations",
}

log("--- where the callback code actually lives (clip 1) ---")
do
	local a = achados[1]
	local tools
	pcall(function() tools = a.comp:GetToolList(false) end)
	if not tools then
		log("  GetToolList failed")
	else
		local n = 0
		for _ in pairs(tools) do n = n + 1 end
		log("  " .. n .. " tool(s) in the clip's composition")
		for _, t in pairs(tools) do
			local nome, id = "?", "?"
			pcall(function()
				local at = t:GetAttrs()
				nome = at.TOOLS_Name or "?"
				id = at.TOOLS_RegID or "?"
			end)
			local achadas = {}
			for _, chave in ipairs(CHAVES) do
				local v
				pcall(function() v = t:GetData(chave) end)
				if v ~= nil then achadas[#achadas + 1] = chave end
			end
			log(string.format("    %-26s %-22s %s", nome, id,
				(#achadas > 0) and table.concat(achadas, ", ") or "-"))
		end
	end

	-- O CustomData pode ter ido parar na propria composicao.
	local naComp = {}
	for _, chave in ipairs(CHAVES) do
		local v
		pcall(function() v = a.comp:GetData(chave) end)
		if v ~= nil then naComp[#naComp + 1] = chave end
	end
	log("  comp:GetData -> " ..
		((#naComp > 0) and table.concat(naComp, ", ") or "nothing"))
end
log("")

local alvo = VERSAO_ESPERADA and tostring(VERSAO_ESPERADA) or "the installed version"
log("--- how to read this ---")
log("  GiAutoSubsVersao MISSING or < " .. alvo ..
	"  ->  this clip carries an old macro copy.")
log("      The Media Pool template is stale: regenerate legendas.lua so it")
log("      demands the new version, then recreate the captions.")
log("  Stamp is " .. alvo .. " and it still does not react")
log("      ->  compare Template / Follower1 above: different values mean the")
log("          Follower wins and the Inspector edit never reaches the screen.")
log("  spline with 0 keyframe(s)  ->  the caption does not render at all.")
log("done. Nothing was written.")
