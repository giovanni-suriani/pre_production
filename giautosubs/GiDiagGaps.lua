--[[
GiDiagGaps - as legendas estao COLADAS na timeline, ou sobra buraco entre elas?

    Workspace > Scripts > GiDiagGaps
    A saida vai pro Console: Workspace > Console

SOMENTE LEITURA. Nao cria, nao apaga, nao muda nada.

Existe porque o "sem buracos" (--no-gaps) chega certo no arquivo (cada legenda
termina onde a proxima comeca) e o GiAutoSubs.lua ainda apara 1 frame de cada
uma, supondo que o `endFrame` do AppendToTimeline e' INCLUSIVO. Essa suposicao
nunca foi medida. Se estiver errada, sobra 1 frame vazio entre toda legenda e a
caixa pisca - e so' o Resolve de verdade sabe a resposta.

Convencao do projeto: COMENTARIOS em portugues sem acento; MENSAGENS em ingles.
]]

local function log(linha)
	print("[GiDiagGaps] " .. tostring(linha))
end

local function obter_resolve()
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

local app_ = obter_resolve()
if not app_ then log("Resolve NOT found - run this from Workspace > Scripts."); return end
local project = app_:GetProjectManager():GetCurrentProject()
if not project then log("no project open."); return end
local timeline = project:GetCurrentTimeline()
if not timeline then log("no timeline open."); return end

log("timeline: " .. tostring(timeline:GetName()))

-- legenda = clipe com comp Fusion que tem um Text+ dentro (o mesmo criterio do
-- GiDiagFixo). Descrever so' as tracks que tem legenda.
local function eh_legenda(item)
	local sim = false
	pcall(function()
		if (item:GetFusionCompCount() or 0) < 1 then return end
		local comp = item:GetFusionCompByIndex(1)
		if comp and (comp:FindTool("Template") or comp:FindToolByID("TextPlus")) then
			sim = true
		end
	end)
	return sim
end

local total = timeline:GetTrackCount("video") or 0
local achou = false
for track = 1, total do
	local itens = {}
	pcall(function() itens = timeline:GetItemListInTrack("video", track) or {} end)
	local legendas = {}
	for _, item in ipairs(itens) do
		if eh_legenda(item) then
			local s, e, d
			pcall(function() s = item:GetStart() end)
			pcall(function() e = item:GetEnd() end)
			pcall(function() d = item:GetDuration() end)
			if s then legendas[#legendas + 1] = { s = s, e = e, d = d } end
		end
	end
	if #legendas > 1 then
		achou = true
		table.sort(legendas, function(a, b) return a.s < b.s end)
		-- buraco = frames vazios entre o FIM de uma e o INICIO da proxima.
		-- O fim vem de start + duration (sem depender de GetEnd ser inclusivo
		-- ou nao); o GetEnd e' impresso ao lado pra conferencia.
		local hist, maior, exemplos = {}, 0, {}
		for k = 1, #legendas - 1 do
			local a, b = legendas[k], legendas[k + 1]
			local fim = a.s + (a.d or 0)
			local buraco = b.s - fim
			hist[buraco] = (hist[buraco] or 0) + 1
			if buraco > maior then maior = buraco end
			if #exemplos < 3 then
				exemplos[#exemplos + 1] = string.format(
					"   #%d start %d dur %s GetEnd %s | next start %d -> gap %d",
					k, a.s, tostring(a.d), tostring(a.e), b.s, buraco)
			end
		end
		log("")
		log(string.format("=== video track %d: %d captions ===", track, #legendas))
		local chaves = {}
		for g in pairs(hist) do chaves[#chaves + 1] = g end
		table.sort(chaves)
		for _, g in ipairs(chaves) do
			local rotulo = g == 0 and "touching (no gap)"
				or (g < 0 and "OVERLAP" or "empty frame(s) between")
			log(string.format("   gap %3d frame(s): %4d pair(s)  %s", g, hist[g], rotulo))
		end
		for _, l in ipairs(exemplos) do log(l) end
	end
end

if not achou then log("no track with 2+ captions found.") end
log("")
log("done - copy everything above and send it over.")
