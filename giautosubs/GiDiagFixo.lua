--[[
GiDiagFixo - por que a caixa-retangulo do `GiAutoSubs Fixo` nao aparece.

    Workspace > Scripts > GiDiagFixo
    A saida vai pro Console: Workspace > Console

SOMENTE LEITURA. Nao cria clipe, nao apaga, nao muda input nenhum - da' pra rodar
com a timeline do jeito que esta'.

Existe porque o sintoma (`no frame available for MediaOut1`, Media Offline) nao
aponta pra causa, e quem escreve o macro nao tem licenca Studio pra abrir o Resolve
e olhar. Este script responde, de uma vez, as quatro perguntas que decidem:

  1. o clipe carrega a copia NOVA do macro? (cada clipe guarda a sua - reinstalar o
     Title nao atualiza clipe que ja existe)
  2. os nove tools da caixa estao dentro dele, e a saida do macro vem do Merge?
  3. algum tool tem FIM DE VALIDADE (`GlobalOut`) menor que o clipe? Foi o que
     derrubou a primeira tentativa: input sem imagem faz o Merge nao devolver nada
  4. o tamanho que foi escrito na mascara e no solido bate com a resolucao da
     timeline? (e' onde mora a duvida do `Height` do RectangleMask)

Convencao do projeto: COMENTARIOS em portugues sem acento; MENSAGENS em ingles.
]]

local function log(linha)
	print("[GiDiagFixo] " .. tostring(linha))
end

-- A cadeia de sempre pra alcancar o Resolve: de onde o objeto vem depende de como o
-- Fusion foi carregado, e nenhuma tentativa serve sozinha.
local function obter_resolve()
	-- Cada tentativa e' CONFERIDA antes de valer: rodando fora do Resolve, uma delas
	-- devolve uma FUNCAO em vez do app, e o script morria em
	-- "attempt to index local 'app_' (a function value)" - erro que fala do meu
	-- codigo e nao do problema que ele veio diagnosticar. Pegou na primeira rodada a
	-- seco, pelo fuscript.
	local function serve(x)
		if type(x) ~= "userdata" and type(x) ~= "table" then return nil end
		local ok = false
		pcall(function() ok = x.GetProjectManager ~= nil end)
		return ok and x or nil
	end

	local r = serve(_G.resolve) or serve(_G.Resolve)
	if r then return r end
	pcall(function() r = serve(bmd.scriptapp("Resolve")) end)
	if r then return r end
	pcall(function() r = serve(app:GetResolve()) end)
	if r then return r end
	pcall(function() r = serve(fusion:GetResolve()) end)
	return r
end

local TOOLS_CAIXA = {
	"GiBoxMask1", "GiBoxBG1", "GiBoxMask2", "GiBoxBG2",
	"GiBoxMask3", "GiBoxBG3", "GiBoxMerge32", "GiBoxMerge21", "GiBoxMerge",
}

local app_ = obter_resolve()
if not app_ then
	log("Resolve NOT found - run this from Workspace > Scripts.")
	return
end

local project = app_:GetProjectManager():GetCurrentProject()
if not project then log("no project open."); return end
local timeline = project:GetCurrentTimeline()
if not timeline then log("no timeline open."); return end

log("timeline: " .. tostring(timeline:GetName()))
log(string.format("timeline resolution: %sx%s",
	tostring(project:GetSetting("timelineResolutionWidth")),
	tostring(project:GetSetting("timelineResolutionHeight"))))

-- Acha o PRIMEIRO clipe de legenda de cada track. Um por track basta: eles nascem
-- todos da mesma copia do macro, e descrever 122 clipes enche o Console sem dizer
-- nada novo.
local total = timeline:GetTrackCount("video") or 0
local achados = {}
for track = total, 1, -1 do
	local itens
	pcall(function() itens = timeline:GetItemListInTrack("video", track) end)
	for _, item in ipairs(itens or {}) do
		local parar = false
		pcall(function()
			if (item:GetFusionCompCount() or 0) < 1 then return end
			local comp = item:GetFusionCompByIndex(1)
			if not comp then return end
			local tool = comp:FindTool("Template") or comp:FindToolByID("TextPlus")
			if not tool then return end
			achados[#achados + 1] = { item = item, track = track, comp = comp,
				tool = tool }
			parar = true
		end)
		if parar then break end
	end
end

log(#achados .. " caption clip(s) inspected (the first one of each video track)")
if #achados == 0 then
	log("no caption clip found - is the caption track disabled, or empty?")
	return
end

for _, a in ipairs(achados) do
	log("")
	log("=== video track " .. a.track .. " ===")

	-- 1. a idade da copia do macro que ESTE clipe carrega
	local versao
	pcall(function() versao = a.tool:GetInput("GiAutoSubsVersao") end)
	if versao == nil then
		-- o carimbo vive no MacroOperator; o `tool` aqui e' o Text+
		pcall(function()
			for _, t in pairs(a.comp:GetToolList(false) or {}) do
				local v = t:GetInput("GiAutoSubsVersao")
				if v ~= nil then versao = v end
			end
		end)
	end
	log("macro copy in this clip: version " .. tostring(versao or "no stamp"))

	-- 2. os tools da caixa, e de onde sai a imagem do macro
	local faltando, presentes = {}, {}
	for _, nome in ipairs(TOOLS_CAIXA) do
		local t
		pcall(function() t = a.comp:FindTool(nome) end)
		if t then presentes[#presentes + 1] = nome
		else faltando[#faltando + 1] = nome end
	end
	log("rectangle tools present: " .. #presentes .. "/9"
		.. (#faltando > 0 and ("  MISSING: " .. table.concat(faltando, ", ")) or ""))
	if #presentes == 0 then
		log("  -> this clip does NOT carry the Fixo macro. Either the Title used was")
		log("     'GiAutoSubs Caption', or the clip was created before the Fixo")
		log("     macro was installed (each clip keeps its own copy of the macro).")
	end

	-- 3. o tempo: a faixa do clipe e o fim de validade de cada tool
	local attrs = {}
	pcall(function() attrs = a.comp:GetAttrs() or {} end)
	log(string.format("comp time: GlobalStart %s  GlobalEnd %s  "
		.. "RenderStart %s  RenderEnd %s",
		tostring(attrs.COMPN_GlobalStart), tostring(attrs.COMPN_GlobalEnd),
		tostring(attrs.COMPN_RenderStart), tostring(attrs.COMPN_RenderEnd)))

	local com_limite = {}
	pcall(function()
		for nome, t in pairs(a.comp:GetToolList(false) or {}) do
			local ta = t:GetAttrs() or {}
			local gi, go = ta.TOOLNT_GlobalIn, ta.TOOLNT_GlobalOut
			local nomeT = (ta.TOOLS_Name or tostring(nome))
			if go ~= nil and attrs.COMPN_GlobalEnd
				and tonumber(go) and tonumber(go) < tonumber(attrs.COMPN_GlobalEnd) then
				com_limite[#com_limite + 1] = string.format(
					"%s (GlobalIn %s, GlobalOut %s)", nomeT, tostring(gi),
					tostring(go))
			end
		end
	end)
	if #com_limite > 0 then
		log("TOOLS THAT RUN OUT OF IMAGE before the clip ends:")
		for _, l in ipairs(com_limite) do log("   " .. l) end
		log("   -> a Merge whose input has no image returns nothing, and the comp")
		log("      answers 'no frame available for MediaOut1'. THIS is the cause.")
	else
		log("no tool runs out of image before the clip ends (good)")
	end

	-- 4. o tamanho escrito na caixa
	for _, par in ipairs({ { "GiBoxMask1", { "MaskWidth", "MaskHeight", "Width",
		"Height", "Center", "CornerRadius" } },
		{ "GiBoxBG1", { "Width", "Height", "UseFrameFormatSettings",
			"TopLeftRed", "TopLeftAlpha" } } }) do
		local t
		pcall(function() t = a.comp:FindTool(par[1]) end)
		if t then
			local partes = {}
			for _, chave in ipairs(par[2]) do
				local v
				pcall(function() v = t:GetInput(chave) end)
				if type(v) == "table" then
					v = string.format("{%s,%s}", tostring(v[1]), tostring(v[2]))
				end
				partes[#partes + 1] = chave .. "=" .. tostring(v)
			end
			log(par[1] .. ": " .. table.concat(partes, "  "))
		end
	end

	-- 5. e o que o Inspector diz que a caixa deveria ser
	local macro
	pcall(function()
		for _, t in pairs(a.comp:GetToolList(false) or {}) do
			if t:GetData("InputKeys") ~= nil then macro = t end
		end
	end)
	if macro then
		local partes = {}
		for _, chave in ipairs({ "TextBoxEnabled", "TextBoxFixed", "TextBoxWidth",
			"TextBoxHeight", "TextBoxRound", "MetaPxPorUnidade" }) do
			local v
			pcall(function() v = macro:GetInput(chave) end)
			partes[#partes + 1] = chave .. "=" .. tostring(v)
		end
		log("Inspector says: " .. table.concat(partes, "  "))
	else
		log("could not reach the MacroOperator of this clip (old macro copy?)")
	end
end

log("")
log("done - copy everything above and send it over.")
