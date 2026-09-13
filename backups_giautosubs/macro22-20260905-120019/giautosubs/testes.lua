--[[
Testes do GiAutoSubs - rodam FORA do Resolve.

    "C:\Program Files\Blackmagic Design\DaVinci Resolve\fuscript.exe" -l lua testes.lua
    ... testes.lua <caminho\para\legendas.lua>    (verifica tambem um arquivo real)

O GiAutoSubs.lua vira modulo quando nao existe Resolve, entao da' pra testar a
parte que erra em silencio - indice de caractere e keyframe por palavra - sem
abrir o editor. Um indice errado por 1 nao quebra nada: so acende a palavra
errada no video inteiro.
]]

local aqui = debug.getinfo(1, "S").source:match("@(.*[\\/])") or ""
local M = dofile(aqui .. "GiAutoSubs.lua")

local falhas = 0
local function checa(cond, msg)
	if not cond then falhas = falhas + 1; print("  FAILED: " .. msg) end
end

-- fatia por CODEPOINT (Lua indexa byte; acento ocupa 2 bytes)
local function fatia(s, ini, fim)
	local out, idx = {}, 0
	for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
		if idx >= ini and idx <= fim then out[#out + 1] = ch end
		idx = idx + 1
	end
	return table.concat(out)
end

-- a quebra de linha troca um espaco por \n: mesmo comprimento, caractere
-- diferente. Normalizar compara justo sem esconder desalinhamento.
local function norm(s) return (s:gsub("%s", " ")) end

--------------------------------------------------------------- unitarios
do
	local seg = {
		start = 10.0, ["end"] = 12.0,
		text = "você começa aí",
		words = {
			{ word = "você",    start = 10.0, ["end"] = 10.4 },
			{ word = " começa", start = 10.4, ["end"] = 11.2 },
			{ word = " aí",     start = 11.2, ["end"] = 12.0 },
		},
	}
	local t = M.tempos_das_palavras(seg, 60)
	checa(#t == 3, "expected 3 words")
	for i, w in ipairs(seg.words) do
		checa(norm(fatia(seg.text, t[i].startIndex, t[i].endIndex)) == norm(w.word),
			"word " .. i .. " does not slice back to itself")
	end
	checa(t[1].startFrame == 0 and t[2].startFrame == 24 and t[3].startFrame == 72,
		"frames should be 0/24/72")

	-- tres camadas juntas: fill que so troca de cor, caixa que acende/apaga,
	-- e a sombra da caixa acompanhando
	local ROSA, BRANCO, PRETO = { 1, 0.3, 0.65 }, { 1, 1, 1 }, { 0, 0, 0 }
	local destaque = { camadas = {
		{ elemento = 1, cor_ativa = ROSA,  cor_base = BRANCO, on_ativo = 1, on_base = 1 },
		{ elemento = 4, cor_ativa = { 1, 0.85, 0.3 }, cor_base = { 1, 0.85, 0.3 }, on_ativo = 1, on_base = 0 },
		{ elemento = 5, cor_ativa = PRETO, cor_base = PRETO,  on_ativo = 1, on_base = 0 },
	} }
	local kf = M.montar_keyframes(t, destaque, 60)
	local n = 0; for _ in pairs(kf) do n = n + 1 end
	checa(n == 3, "expected 3 keyframes, got " .. n)
	-- 3 palavras x 3 camadas x 4 canais
	checa(#kf[24].Value.Array == 36, "array should have 36 entries, got " .. #kf[24].Value.Array)

	-- no keyframe da palavra 2: caixa (Index 3) e sombra (Index 4) acesas SO nela
	local l4, l5, fill_on = {}, {}, 0
	for _, e in ipairs(kf[24].Value.Array) do
		if e[1] == 2000 and e.Value == 1 then
			if e.Index == 3 then l4[#l4 + 1] = e[2] end
			if e.Index == 4 then l5[#l5 + 1] = e[2] end
			if e.Index == 0 then fill_on = fill_on + 1 end
		end
	end
	checa(#l4 == 1 and l4[1] == t[2].startIndex, "box lit only on the active word")
	checa(#l5 == 1 and l5[1] == t[2].startIndex, "shadow following the box")
	checa(fill_on == 3, "fill should stay lit on all 3 words, got " .. fill_on)

	-- e o fill da palavra ativa tem que estar ROSA, as outras brancas
	local rosa, branco = 0, 0
	for _, e in ipairs(kf[24].Value.Array) do
		if e.Index == 0 and e[1] == 2401 then  -- canal Red do elemento 1
			if e[2] == t[2].startIndex then
				if math.abs(e.Value - ROSA[1]) < 1e-6 then rosa = rosa + 1 end
			elseif math.abs(e.Value - BRANCO[1]) < 1e-6 then branco = branco + 1 end
		end
	end
	checa(rosa == 1, "active word should be pink")
	checa(branco == 2, "the others should stay white, got " .. branco)
end

-- palavras de duracao zero nao podem colidir no mesmo keyframe
do
	local seg = {
		start = 0, ["end"] = 2, text = "a b c",
		words = {
			{ word = "a",  start = 0.10, ["end"] = 0.10 },
			{ word = " b", start = 0.10, ["end"] = 0.10 },
			{ word = " c", start = 0.10, ["end"] = 2.00 },
		},
	}
	local t = M.tempos_das_palavras(seg, 60)
	local kf = M.montar_keyframes(t, { camadas = {
		{ elemento = 4, cor_ativa = { 1, 1, 1 }, cor_base = { 1, 1, 1 }, on_ativo = 1, on_base = 0 },
	} }, 60)
	local n = 0; for _ in pairs(kf) do n = n + 1 end
	checa(n == 3, "3 words at the same instant should become 3 keyframes, got " .. n)
end

-- O preset alcanca as CAMADAS, e nao so' os controles.
--
-- O array e' escrito no passo 8 a partir do estilo, DEPOIS de o preset ter
-- escrito os controles no passo 5 - e o array vence os inputs. Sem este caminho,
-- um preset com `WordFillEnabled = 0` produzia um clipe com o Inspector dizendo
-- "off" e o spline pintando a palavra falada assim mesmo.
do
	local function novo()
		return { controles = { FillColorRed = 1, FillColorGreen = 1,
			FillColorBlue = 1, WordFillColorRed = 1, WordFillColorGreen = 0.91,
			WordFillColorBlue = 0 },
			destaque = { camadas = {
				{ elemento = 1, cor_ativa = { 1, 0.91, 0 }, cor_base = { 1, 1, 1 },
				  on_ativo = 1, on_base = 1 },
				{ elemento = 4, cor_ativa = { 0, 0, 0 }, cor_base = { 0, 0, 0 },
				  on_ativo = 1, on_base = 0 },
			} } }
	end

	local d = novo()
	M.fundir_preset(d, { WordFillEnabled = 0 })
	checa(#d.destaque.camadas == 1 and d.destaque.camadas[1].elemento == 4,
		"WordFillEnabled = 0 in the config must DROP the fill layer, not just "
		.. "the checkbox (the array beats the inputs)")

	d = novo()
	M.fundir_preset(d, { BubbleEnabled = 0 })
	checa(#d.destaque.camadas == 1 and d.destaque.camadas[1].elemento == 1,
		"BubbleEnabled = 0 in the config must drop the bubble layer too")

	d = novo()
	M.fundir_preset(d, { WordFillEnabled = 1 })
	checa(#d.destaque.camadas == 2, "WordFillEnabled = 1 keeps what is there")

	-- ligar pelo preset num estilo que nao tem a camada: ela nasce, com a cor
	-- ATIVA vinda do Word Color e a BASE do Fill Color
	d = novo()
	table.remove(d.destaque.camadas, 1)
	M.fundir_preset(d, { WordFillEnabled = 1, WordFillColorRed = 0.5 })
	local fill
	for _, c in ipairs(d.destaque.camadas) do
		if c.elemento == 1 then fill = c end
	end
	checa(fill ~= nil, "WordFillEnabled = 1 creates the fill layer when missing")
	checa(fill and fill.cor_ativa[1] == 0.5 and fill.cor_ativa[2] == 0.91,
		"the new layer's active colour comes from Word Color, preset first")
	checa(fill and fill.cor_base[1] == 1 and fill.cor_base[2] == 1,
		"and its base colour from Fill Color")

	-- desligar as duas: sem camada nenhuma. Quem trata isso e' o passo 8, que
	-- cai no `keyframes_vazios` - um spline VAZIO seria o `cannot get Parameter`.
	d = novo()
	M.fundir_preset(d, { WordFillEnabled = 0, BubbleEnabled = 0 })
	checa(#d.destaque.camadas == 0, "turning both off leaves no animated layer")

	-- o Offset continua funcionando (foi a primeira excecao desta funcao)
	d = novo()
	M.fundir_preset(d, { Offset3 = { 0.01, -0.02 } })
	checa(d.inputs and d.inputs._offset3 and d.inputs._offset3[1] == 0.01,
		"Offset{n} still reaches dados.inputs._offset{n}")
end

-- Texto corrigido a mao com palavra A MAIS: "i love potato" -> "i love the
-- potato". O `GiWordTiming` endereca por indice de caractere, entao os indices
-- velhos passam a apontar pro lugar errado (" potato" vira " the po") e a
-- palavra nova nao tem tempo nenhum. O macro so' realinha quando o numero de
-- palavras NAO muda; mudou, quem conserta e' o `refazer_tempos`.
do
	local antes = M.tempos_das_palavras({
		start = 0, ["end"] = 3, text = "i love potato",
		words = {
			{ word = "i",       start = 0.0, ["end"] = 0.5 },
			{ word = " love",   start = 0.5, ["end"] = 1.5 },
			{ word = " potato", start = 1.5, ["end"] = 3.0 },
		},
	}, 60)
	checa(#antes == 3 and antes[3].startIndex == 6 and antes[3].endIndex == 12,
		"fixture: ' potato' ocupa 6..12 no texto antigo")

	local novo = "i love the potato"
	local depois, quantas = M.refazer_tempos(novo, antes)
	checa(depois and quantas == 4, "quatro palavras depois da correcao")

	-- os indices tem que cobrir o texto NOVO, sem buraco e sem sobra
	checa(depois[1].startIndex == 0, "a primeira palavra comeca no zero")
	for k = 2, #depois do
		checa(depois[k].startIndex == depois[k - 1].endIndex + 1,
			"os pedacos tem que ser contiguos (o espaco pertence ao seguinte)")
	end
	checa(depois[#depois].endIndex == 16,
		"o ultimo pedaco tem que terminar no fim do texto (17 caracteres), "
		.. "terminou em " .. tostring(depois[#depois].endIndex))
	-- e cada pedaco tem que ser a palavra que ele diz ser
	checa(norm(fatia(novo, depois[3].startIndex, depois[3].endIndex)) == " the",
		"a palavra 3 tem que ser ' the', veio '"
		.. fatia(novo, depois[3].startIndex, depois[3].endIndex) .. "'")
	checa(norm(fatia(novo, depois[4].startIndex, depois[4].endIndex)) == " potato",
		"a palavra 4 tem que ser ' potato', veio '"
		.. fatia(novo, depois[4].startIndex, depois[4].endIndex) .. "'")

	-- as pontas ficam onde estavam; a bolha continua no mesmo intervalo
	checa(depois[1].startFrame == antes[1].startFrame,
		"a primeira palavra nao muda de frame")
	checa(depois[#depois].startFrame == antes[#antes].startFrame,
		"a ultima palavra nao muda de frame")
	-- e ninguem colide (duas no mesmo frame = uma nunca acende)
	for k = 2, #depois do
		checa(depois[k].startFrame > depois[k - 1].startFrame,
			"os frames tem que ser estritamente crescentes")
	end

	-- mesmo numero de palavras: nao e' caso deste conserto, o macro realinha
	checa(M.refazer_tempos("i love batata", antes) == nil,
		"com o mesmo numero de palavras o macro e' que realinha, nao este")

	-- palavra a MENOS tambem
	local menos = M.refazer_tempos("i love", antes)
	checa(menos and #menos == 2, "palavra a menos tambem e' refeita")
	checa(menos[#menos].endIndex == 5,
		"e os indices acompanham o texto mais curto")
end

------------------------------------------------------ arquivo real (opcional)
local alvo = arg and arg[1]
if alvo then
	local d = M.ler_dados(alvo)
	local palavras, erros, ok_kf, com_w = 0, 0, 0, 0
	for i, seg in ipairs(d.segments) do
		local t = M.tempos_das_palavras(seg, 60)
		if t then
			com_w = com_w + 1
			for j, w in ipairs(seg.words) do
				palavras = palavras + 1
				if norm(fatia(seg.text, t[j].startIndex, t[j].endIndex)) ~= norm(w.word) then
					erros = erros + 1
					if erros <= 3 then print("  caption " .. i .. " word " .. j .. " is misaligned") end
				end
			end
			local kf = M.montar_keyframes(t, d.destaque, 60)
			local n = 0; for _ in pairs(kf) do n = n + 1 end
			if n == #t then ok_kf = ok_kf + 1 end
		end
	end
	print(string.format("file: %d captions, %d with words, %d words, %d index errors",
		#d.segments, com_w, palavras, erros))
	checa(erros == 0, "misaligned indices in the real file")
	checa(ok_kf == com_w, "keyframes missing on some caption")
end

-------------------------------------------------- o laco inteiro, sem Resolve
--
-- Um Resolve de mentira. Serve pra rodar `main` de ponta a ponta aqui fora:
-- ate agora, qualquer erro no laco principal (nome trocado, ordem de escrita,
-- contador errado) so aparecia DENTRO do Resolve, que e' a rodada cara.
--
-- O Text+ falso reproduz de proposito a regra que mais custou tempo neste
-- projeto: os inputs de um elemento so existem depois de `Enabled{n}` = 1;
-- antes disso o SetInput e' aceito e descartado, sem erro. E ele nasce com o
-- azul do AutoSubs em Red2/Green2/Blue2, pra o teste provar que o estilo
-- sobrescreve aquilo.
local function textplus_falso(versao)
	local v = {
		Enabled1 = 1, Enabled2 = 1, Enabled3 = 1,
		-- presets de fabrica do Text+: o 1 e' "White Solid Fill" (texto) e o
		-- 4 e' "Blue Border" (borda). E' dai que sai a forma da caixa.
		ElementShape1 = 1, ElementShape4 = 3,
		-- o outline azul do macro do AutoSubs, pra o teste provar que o estilo
		-- sobrescreve. No Follower1 os valores de fabrica sao outros
		-- (0.929 / 0.051), mas o que importa e' que NAO sejam os do estilo.
		Red2 = 0, Green2 = 0.35, Blue2 = 1,
		Thickness2 = 0.8,
		-- carimbo do gerar_macro.py: sem ele o script para achando que o
		-- Media Pool tem uma copia velha do macro
		GiAutoSubsVersao = versao,
	}
	local t = { valores = v, escritas = 0 }
	local function bloqueado(k)
		local n = tostring(k):match("^%a[%w]-([1-8])$")
		return n and not tostring(k):match("^Enabled%d$") and v["Enabled" .. n] ~= 1
	end
	function t:GetInput(k)
		if bloqueado(k) then return nil end
		return v[k]
	end
	function t:SetInput(k, val)
		if bloqueado(k) then return end
		v[k] = val
		t.escritas = t.escritas + 1
	end
	-- `SetData`/`GetData` sao o CustomData do tool. E' onde o tempo por palavra
	-- fica guardado DENTRO do clipe, pro macro conseguir refazer os keyframes
	-- quando alguem mexe numa cor sem o script por perto.
	t.dados = {}
	function t:SetData(k, v) t.dados[k] = v end
	function t:GetData(k) return t.dados[k] end
	function t:GetName() return "Template" end
	return t
end

-- `versao_do_macro` e' o carimbo que o Text+ falso devolve. Quando
-- `versao_apos_troca` vem junto, o Media Pool falso simula o caso real: o item
-- guardado no projeto esta defasado, e so' depois de trocado pelo arquivo em
-- Effects > Titles e' que a versao certa aparece.
local function resolve_falso(versao_do_macro, versao_apos_troca)
	local reg = { keyframes = {}, comps = {}, cores = 0, apagados = 0,
		trocas = 0, apagados_do_pool = 0 }

	local function saida(alvo) return { GetTool = function() return alvo end } end

	-- a versao que os clipes novos enxergam. Muda quando o script troca o
	-- template do Media Pool.
	local versao_corrente = versao_do_macro

	local function comp_falsa()
		local tool = textplus_falso(versao_corrente)
		local spline = { SetKeyFrames = function(_, kf) reg.keyframes[#reg.keyframes + 1] = kf end }
		local cls = { CharacterLevelStyling = { GetConnectedOutput = function() return saida(spline) end },
			SetInput = function() end }
		-- O Follower1 tambem e' um Text+ falso: e' nele que moram as cores que
		-- de fato aparecem na tela (Red2 = 0.929 no macro do AutoSubs). Se o
		-- script escrever so no Template, este teste pega.
		local fol = textplus_falso(versao_corrente)
		fol.Text = { GetConnectedOutput = function() return saida(cls) end }
		-- valores de fabrica do Follower1 no macro do AutoSubs: sao ESTES que
		-- apareciam na tela quando o script escrevia so no Template
		fol.valores.Red2, fol.valores.Green2 = 0.9294117647059, 0.0509803921569
		fol.valores.Thickness2 = 0.8
		-- O MacroOperator. E' ELE que carrega os chunks (`SetInputValues` e
		-- companhia) no `CustomData` - nao o `Template`, nao a comp.
		--
		-- Esta distincao e' o teste: quem procura a rotina so' no tool que tem em
		-- maos (o Text+) acha nil e cai no caminho longo, e foi exatamente isso
		-- que fez o resumo do run dizer "one by one (the chunks are not reachable
		-- from a script)" e o botao do Inspector dizer "nothing was applied". O
		-- unico jeito de achar e' varrer a comp tool a tool.
		--
		-- `reg.com_contrato` liga o caminho novo: com ele, o script tem que
		-- entregar o preset pro macro em UMA chamada em vez de escrever controle
		-- por controle.
		local macro = { GetName = function() return "AutoSubs" end }
		function macro:GetData(k)
			-- O pop da bolha responde SEMPRE: quem o chama e' o script, direto,
			-- e nao o contrato. Ele so' registra que foi chamado - o que ele
			-- escreve sao keyframes num spline, territorio do Resolve.
			if k == "GiBubblePop" then
				return [[
					return function(comp, tool)
						tool:SetData("_pop_chamado", true)
						return "fake pop"
					end
				]]
			end
			if not reg.com_contrato then return nil end
			if k ~= "SetInputValues" then return nil end
			-- Um SetInputValues de mentira, com o mesmo contrato do de verdade:
			-- recebe a tabela opaca e escreve chave por chave no tool.
			return [[
				return function(comp, tool, settings, origem, spline)
					local n = 0
					for k, v in pairs(settings or {}) do
						tool:SetInput(k, v)
						n = n + 1
					end
					tool:SetData("_preset_recebido", settings or {})
					tool:SetData("_preset_origem", tostring(origem))
					tool:SetData("_preset_spline", tostring(spline))
					return n
				end
			]]
		end

		local mapa = { Template = tool, Follower1 = fol, CharacterLevelStyling1 = cls }
		local c = { tool = tool, follower = fol, macro = macro }
		function c:FindTool(n) return mapa[n] end
		function c:FindToolByID(_) return tool end
		function c:GetToolList() return { tool, fol, macro } end
		function c:GetAttrs() return {} end
		-- a comp NAO e' dona de CustomData nenhum, igual a de verdade
		function c:GetData() return nil end

		reg.comps[#reg.comps + 1] = c
		return c
	end

	local template = { GetName = function() return "GiAutoSubs Caption" end }
	local folder = {
		GetSubFolderList = function() return {} end,
		-- `reg.pool_vazio` simula o Media Pool sem o template. No modo
		-- "atualizar" isso tem que ser irrelevante: as legendas ja estao na
		-- timeline e o macro mora dentro delas.
		GetClipList = function()
			if reg.pool_vazio then return {} end
			return { template }
		end,
	}
	local mediaPool = {
		GetRootFolder = function() return folder end,
		DeleteClips = function(_, lista)
			reg.apagados_do_pool = reg.apagados_do_pool + #lista
		end,
		-- O caminho do bin `.drb`. `ExportFolder` e' o que dispensa o
		-- "right-click > Export Bin File..." - o bin passa a sair do proprio
		-- script, uma vez, e os projetos seguintes importam sozinhos.
		AddSubFolder = function(_, _, nome)
			reg.bins_criados = (reg.bins_criados or 0) + 1
			return { GetName = function() return nome end }
		end,
		CopyClips = function(_, lista, _)
			reg.copiados = (reg.copiados or 0) + #lista
			return true
		end,
		ExportFolder = function(_, _, caminho)
			reg.exportado = caminho
			return not reg.export_falha
		end,
		DeleteFolders = function(_, lista)
			reg.bins_apagados = (reg.bins_apagados or 0) + #lista
			return true
		end,
		ImportFolderFromFile = function(_, caminho)
			reg.importado = caminho
			return true
		end,
		AppendToTimeline = function(_, clipes)
			reg.pedidos_de_append = (reg.pedidos_de_append or 0) + 1
			local itens = {}
			for _ = 1, #clipes do
				local comp = comp_falsa()
				itens[#itens + 1] = {
					GetFusionCompCount = function() return 1 end,
					GetFusionCompByIndex = function() return comp end,
					SetClipColor = function() reg.cores = reg.cores + 1 end,
				}
			end
			reg.pedidos = clipes
			reg.itens_criados = itens
			return itens
		end,
	}
	-- A timeline falsa conta tracks de verdade. Com `GetTrackCount` fixo, o
	-- `while GetTrackCount() < alvo do AddTrack() end` do script rodava pra
	-- sempre - e um teste que trava e' pior que um teste que falha.
	reg.tracks = 7
	local timeline = {
		GetSetting = function() return "60" end,
		GetStartFrame = function() return 0 end,
		GetName = function() return "test timeline" end,
		GetTrackCount = function() return reg.tracks end,
		AddTrack = function() reg.tracks = reg.tracks + 1 end,
		-- No modo "atualizar" o script nao cria nada: ele varre as tracks
		-- procurando legendas que ja estao la. `reg.na_timeline` e' o que
		-- fingimos ja existir.
		GetItemListInTrack = function(_, _, track)
			if track ~= reg.tracks then return {} end
			local out = {}
			for k, item in ipairs(reg.na_timeline or {}) do
				-- `reg.inicios` deixa o teste dizer em que frame cada legenda ja
				-- existente comeca. E' o que o modo "contornar" compara: sem
				-- frames de verdade, o teste passaria sem exercitar a regra.
				local inicio = reg.inicios and reg.inicios[k] or k * 100
				item.GetStart = function() return inicio end
				out[#out + 1] = item
			end
			return out
		end,
		DeleteClips = function(_, lista) reg.apagados = #lista end,
		-- E' assim que o Resolve re-le o titulo do arquivo em Effects > Titles.
		-- Aqui isso passa a valer a `versao_apos_troca`: o item defasado do
		-- Media Pool da' lugar a um recem-lido.
		InsertFusionTitleIntoTimeline = function(_, nome)
			reg.trocas = reg.trocas + 1
			-- `reg.sem_media_pool_item` reproduz o comportamento REAL do
			-- Resolve 21: o titulo entra na timeline, mas o item nao carrega
			-- MediaPoolItem nenhum. E' o caso em que semear falha.
			if reg.sem_media_pool_item then
				return { GetName = function() return nome end }
			end
			versao_corrente = versao_apos_troca or versao_do_macro
			return {
				GetMediaPoolItem = function()
					return { GetName = function() return nome end }
				end,
			}
		end,
	}
	local resolve = {
		GetProjectManager = function()
			return { GetCurrentProject = function()
				return {
					GetMediaPool = function() return mediaPool end,
					GetCurrentTimeline = function() return timeline end,
				}
			end }
		end,
	}
	return resolve, reg
end

-- Onde o bin `.drb` de mentira mora durante os testes.
--
-- Isto vale pra rodada INTEIRA, nao so' pro bloco que testa a exportacao: o
-- Resolve falso responde "exportei" sem escrever arquivo nenhum, e a rotina
-- grava o carimbo em seguida. Apontando pro caminho real, um teste deixaria um
-- `.versao` dizendo que existe um bin que nao existe - e a proxima rodada de
-- verdade acreditaria nele. Teste que estraga o estado do projeto e' pior que
-- teste nenhum.
local BIN_DE_TESTE = aqui .. "_teste_bin.drb"

local function roda_falso(alvo_lua)
	local d = M.ler_dados(alvo_lua)
	if d then
		print("  -- main against a fake Resolve: " .. alvo_lua .. " --")
		M.definir_arquivo(alvo_lua)
		local bin_real = M.definir_bin(BIN_DE_TESTE)

		-- Macro velho no Media Pool que NAO da' pra consertar: o arquivo em
		-- Effects > Titles tambem esta velho (o Fusion varre aquela pasta no
		-- boot). O script tem que desistir depois de UMA tentativa, sem se
		-- rechamar pra sempre, e sem deixar legenda errada na timeline.
		do
			local r_velho, reg_velho = resolve_falso(nil, nil)
			local ok_velho = pcall(M.main, r_velho)
			checa(ok_velho, "main blew up on the old-macro case")
			checa(reg_velho.cores == 0,
				"with an old macro no clip should be styled, but "
				.. reg_velho.cores)
			checa(reg_velho.trocas == 1,
				"the template should be refreshed exactly once, it was "
				.. reg_velho.trocas .. " time(s)")
			checa(reg_velho.apagados_do_pool == 1,
				"the stale Media Pool item should be deleted once, it was "
				.. reg_velho.apagados_do_pool)
		end

		-- Semear FALHA (o caso real: o Resolve nao expoe MediaPoolItem num
		-- titulo inserido na timeline). O template velho tem que continuar
		-- inteiro no Media Pool - apagar antes de ter o substituto na mao
		-- deixava o usuario sem template nenhum.
		do
			local r_sem, reg_sem = resolve_falso(nil, d.macro_versao)
			reg_sem.sem_media_pool_item = true
			local ok_sem = pcall(M.main, r_sem)
			checa(ok_sem, "main blew up when seeding failed")
			checa(reg_sem.apagados_do_pool == 0,
				"the stale template must NOT be deleted when seeding fails, "
				.. "but " .. reg_sem.apagados_do_pool .. " item(s) were")
		end

		-- E o caso que interessa: o Media Pool esta defasado mas o arquivo em
		-- Effects > Titles esta novo. O script troca sozinho e termina a
		-- rodada - sem passo manual nenhum.
		do
			local r_troca, reg_troca = resolve_falso(nil, d.macro_versao)
			local ok_troca = pcall(M.main, r_troca)
			checa(ok_troca, "main blew up while refreshing the template")
			checa(reg_troca.trocas == 1,
				"the template should be refreshed once, it was "
				.. reg_troca.trocas .. " time(s)")
			checa(reg_troca.cores == #d.segments,
				"after refreshing, all " .. #d.segments .. " clips should be "
				.. "styled, but " .. reg_troca.cores .. " were")
		end

		-- Modo "atualizar": as legendas ja estao na timeline. O script nao pode
		-- criar clipe nenhum, e tem que restilizar o que encontrou.
		do
			local r_up, reg_up = resolve_falso(d.macro_versao)
			-- primeiro cria (do jeito normal) pra ter o que atualizar depois
			local ok1 = pcall(M.main, r_up)
			checa(ok1, "main blew up while seeding the update-mode fixture")
			reg_up.na_timeline = reg_up.itens_criados
			-- Em que frame cada legenda ja existente comeca. Sem isto o Resolve
			-- falso inventa `k * 100`, e o pareamento por FRAME DE INICIO nao
			-- casa nada - o pareamento por ordem, que existia antes, passava sem
			-- olhar frame nenhum. E' o mesmo fixture que o teste do "contornar"
			-- ja montava.
			reg_up.inicios = {}
			for k, seg in ipairs(d.segments) do
				reg_up.inicios[k] = M.segundos_para_frames(seg.start, 60)
			end
			local criados = reg_up.cores

			-- alguem corrigiu uma legenda na mao pelo Inspector
			local tool1 = reg_up.itens_criados[1]:GetFusionCompByIndex(1).tool
			tool1.valores.Text = "corrigido na mao"

			M.definir_modo("atualizar", false)
			local ok2 = pcall(M.main, r_up)
			M.definir_modo("criar", false)
			checa(ok2, "main blew up in update mode")
			checa(reg_up.pedidos_de_append == 1,
				"update mode must not call AppendToTimeline, it was called "
				.. (reg_up.pedidos_de_append - 1) .. " extra time(s)")
			checa(reg_up.cores == criados + math.min(#d.segments, criados),
				"update mode should restyle the captions it found")
			-- a promessa do modo: estilo novo, texto do usuario intacto
			checa(tool1.valores.Text == "corrigido na mao",
				"update mode overwrote a hand-edited caption (got '"
				.. tostring(tool1.valores.Text) .. "')")
			checa(tool1.valores.Red2 == d.inputs.Red2,
				"update mode did not restyle the hand-edited caption")

			-- e com o Media Pool VAZIO: o modo atualizar nao pode depender do
			-- template estar la, porque nao usa o template pra nada
			reg_up.pool_vazio = true
			tool1.valores.Red2 = 0.42
			M.definir_modo("atualizar", false)
			local ok3 = pcall(M.main, r_up)
			M.definir_modo("criar", false)
			checa(ok3, "update mode blew up with an empty Media Pool")
			checa(tool1.valores.Red2 == d.inputs.Red2,
				"update mode needed the Media Pool template, but it should not")
			reg_up.pool_vazio = nil

			-- O pareamento por FRAME DE INICIO, que e' o motivo de ele existir:
			-- com uma legenda a MENOS na timeline que no arquivo (foi o que a
			-- reparticao em duas captions passou a produzir), o pareamento por
			-- ordem deslocava tudo depois do buraco - o clipe recebia o texto e o
			-- tempo por palavra do vizinho, calado. Por frame, quem tem par casa
			-- e o resto fica de fora.
			local r_pf, reg_pf = resolve_falso(d.macro_versao)
			pcall(M.main, r_pf)
			-- tira a PRIMEIRA da timeline: por ordem, a segunda legenda passaria
			-- a casar com o primeiro segmento
			local restantes, inicios = {}, {}
			for k = 2, #reg_pf.itens_criados do
				restantes[#restantes + 1] = reg_pf.itens_criados[k]
				inicios[#inicios + 1] = M.segundos_para_frames(d.segments[k].start, 60)
			end
			reg_pf.na_timeline, reg_pf.inicios = restantes, inicios
			local antes_pf = reg_pf.cores

			M.definir_modo("atualizar", true)   -- com o texto, pra poder conferir
			local ok_pf = pcall(M.main, r_pf)
			M.definir_modo("criar", false)
			checa(ok_pf, "main blew up while matching by start frame")
			checa(reg_pf.cores == antes_pf + #restantes,
				string.format("every caption still on the timeline should have "
					.. "matched: %d restyled, %d expected",
					reg_pf.cores - antes_pf, #restantes))

			-- a prova de que nao deslocou: cada clipe ficou com o SEU texto
			for k = 2, #reg_pf.itens_criados do
				local t = reg_pf.itens_criados[k]:GetFusionCompByIndex(1).tool
				checa(norm(t.valores.Text or "") == norm(d.segments[k].text),
					string.format("caption %d got the wrong segment's text: '%s'",
						k, tostring(t.valores.Text)))
			end
		end

		-- O contrato do macro (`SetInputValues`). Quando os chunks estao ao
		-- alcance, o estilo tem que entrar por UMA chamada, com a tabela opaca
		-- inteira - e nao controle por controle.
		do
			local r_ct, reg_ct = resolve_falso(d.macro_versao)
			reg_ct.com_contrato = true
			local ok_ct = pcall(M.main, r_ct)
			checa(ok_ct, "main blew up with the macro contract available")

			local guardado = reg_ct.comps[1] and reg_ct.comps[1].tool.dados
			local recebido = guardado and guardado._preset_recebido
			checa(recebido ~= nil,
				"SetInputValues was never called - the script wrote the controls "
				.. "one by one even though the contract was reachable")
			-- a tabela e' OPACA: o teste nao sabe o que tem dentro, so' que e' a
			-- mesma coisa que o giautosubs.py mandou
			local n_pedido, n_recebido = 0, 0
			for _ in pairs(d.controles or {}) do n_pedido = n_pedido + 1 end
			for _ in pairs(recebido or {}) do n_recebido = n_recebido + 1 end
			checa(n_recebido == n_pedido,
				string.format("the preset arrived with %d keys, legendas.lua has "
					.. "%d", n_recebido, n_pedido))
			-- e o spline nao pode ser refeito aqui: o array por palavra e'
			-- reescrito logo em seguida, e refazer duas vezes e' a metade cara
			-- do callback paga a toa
			checa(guardado._preset_spline == "false",
				"the script should tell SetInputValues to skip the spline, it "
				.. "said " .. tostring(guardado._preset_spline))

			-- Numa legenda SEM tempo por palavra a bolha precisa chegar
			-- desligada no PRESET. So' apagar o Enabled4 nao bastaria: quem
			-- escreve o estilo agora e' o macro, lendo BubbleEnabled.
			local i_sem
			for k, seg in ipairs(d.segments) do
				if not (seg.words and #seg.words > 0) then i_sem = k break end
			end
			if i_sem then
				local p = reg_ct.comps[i_sem].tool.dados._preset_recebido
				checa(p and p.BubbleEnabled == 0,
					"a caption with no word timings should get BubbleEnabled = 0 "
					.. "in its preset, it got " .. tostring(p and p.BubbleEnabled))
			end

			-- O pop da bolha. O script escreve o array de estilo ele mesmo e
			-- manda o rebuild PULAR - se o pop dependesse do rebuild, ele nao
			-- aconteceria em nenhuma das 128 legendas, e ninguem veria isso a
			-- nao ser olhando quadro a quadro.
			checa(guardado._pop_chamado == true,
				"GiBubblePop was never called - the bubble pop would be missing "
				.. "on every caption the script creates")
		end

		-- A CONFIGURACAO da rodada (o preset do botao "Export Config").
		--
		-- Ele tem que VENCER o estilo assado no legendas.lua, e vencer no lugar
		-- certo: os controles vao pro macro (`SetInputValues`), mas os
		-- `Offset{n}` sao escritos direto pelo script, num passo POSTERIOR - um
		-- offset que ficasse so' nos controles seria reescrito pelo estilo logo
		-- em seguida, sem uma linha de log dizendo isso.
		do
			local preset_teste = aqui .. "_teste_preset.txt"
			local fh = io.open(preset_teste, "w")
			checa(fh ~= nil, "could not write the test preset")
			if fh then
				fh:write("#nome\tteste\n")
				fh:write("#versao\t" .. tostring(d.macro_versao) .. "\n")
				fh:write("BubbleRound\t0.789\n")
				fh:write("Offset3\t{0.0125,-0.5}\n")
				fh:write("Font\tComic Sans MS\n")
				fh:close()

				local lido = M.ler_preset(preset_teste)
				checa(lido and lido.nome == "teste", "the preset name was not read")
				checa(lido and lido.n == 3,
					"expected 3 values in the preset, got "
					.. tostring(lido and lido.n))
				checa(lido and type(lido.valores.Offset3) == "table"
					and math.abs(lido.valores.Offset3[1] - 0.0125) < 1e-9,
					"a {a,b} value has to come back as a TABLE - as a string the "
					.. "Fusion would accept it and draw nothing")

				M.definir_preset(preset_teste)
				local r_pr, reg_pr = resolve_falso(d.macro_versao)
				reg_pr.com_contrato = true
				local ok_pr = pcall(M.main, r_pr)
				M.definir_preset(nil)
				checa(ok_pr, "main blew up with a config preset chosen")

				local comp1 = reg_pr.comps[1]
				local p = comp1 and comp1.tool.dados._preset_recebido
				checa(p and math.abs((p.BubbleRound or 0) - 0.789) < 1e-9,
					"the config did not reach SetInputValues (BubbleRound is "
					.. tostring(p and p.BubbleRound) .. ")")
				checa(p and p.Font == "Comic Sans MS",
					"a text value from the config did not survive the merge")
				-- o que o preset NAO diz continua vindo do estilo
				checa(p and p.BubbleExtendVertical
					== (d.controles or {}).BubbleExtendVertical,
					"the config replaced a value it never mentioned - it should "
					.. "merge over the style, not replace it")
				local v3 = comp1 and comp1.tool.valores
				local off3 = v3 and (v3.Offset3 or v3.TextOffset3
					or v3.ShadowOffset3)
				checa(off3 and math.abs(off3[1] - 0.0125) < 1e-9,
					"Offset3 from the config was overwritten by the style's own "
					.. "offset (it is written in a later step)")
				os.remove(preset_teste)
			end
		end

		-- CONFLITO: o que fazer com a rodada anterior.
		do
			-- "substituir": apaga as legendas que ja estavam la e reaproveita a
			-- track delas, em vez de empilhar uma rodada em cima da outra. E' o
			-- conserto do "129 achadas contra 128 criadas".
			local r_sub, reg_sub = resolve_falso(d.macro_versao)
			pcall(M.main, r_sub)
			reg_sub.na_timeline = reg_sub.itens_criados
			local tracks_antes = reg_sub.tracks
			reg_sub.apagados = 0

			M.definir_conflito("substituir")
			local ok_sub = pcall(M.main, r_sub)
			M.definir_conflito("substituir")
			checa(ok_sub, "main blew up with CONFLITO = substituir")
			checa(reg_sub.apagados == #d.segments,
				string.format("substituir should delete the %d captions already "
					.. "there, it deleted %d", #d.segments, reg_sub.apagados))
			checa(reg_sub.tracks == tracks_antes,
				string.format("substituir should reuse the emptied track, but the "
					.. "timeline went from %d tracks to %d", tracks_antes,
					reg_sub.tracks))

			-- "contornar": nao apaga nada, e nao cria legenda onde ja existe uma.
			local r_ct, reg_ct = resolve_falso(d.macro_versao)
			pcall(M.main, r_ct)
			reg_ct.na_timeline = reg_ct.itens_criados
			-- os frames em que as legendas ja existentes comecam
			reg_ct.inicios = {}
			for k, seg in ipairs(d.segments) do
				reg_ct.inicios[k] = M.segundos_para_frames(seg.start, 60)
			end
			reg_ct.apagados = 0
			local criados_antes = reg_ct.cores

			M.definir_conflito("contornar")
			local ok_cont = pcall(M.main, r_ct)
			M.definir_conflito("substituir")
			checa(ok_cont, "main blew up with CONFLITO = contornar")
			checa(reg_ct.apagados == 0,
				"contornar must not delete anything, it deleted " .. reg_ct.apagados)
			checa(reg_ct.cores == criados_antes,
				string.format("contornar should create no clip where a caption "
					.. "already starts, but %d were styled",
					reg_ct.cores - criados_antes))
		end

		-- O bin `.drb`: exportado sozinho depois que o carimbo do macro bate.
		do
			local temp = BIN_DE_TESTE
			os.remove(temp .. ".versao")   -- pra este bloco ver a exportacao
			local r_bin, reg_bin = resolve_falso(d.macro_versao)
			local ok_bin = pcall(M.main, r_bin)
			checa(ok_bin, "main blew up while exporting the bin")
			checa(reg_bin.exportado == temp,
				"the template bin should be exported once the macro stamp "
				.. "matches, got " .. tostring(reg_bin.exportado))
			-- o template sai copiado pra uma pasta so' dele: exportar a pasta
			-- onde ele estava levaria junto o Media Pool inteiro
			checa((reg_bin.copiados or 0) == 1 and (reg_bin.bins_criados or 0) == 1,
				"the export should copy the template into a bin of its own")
			checa((reg_bin.bins_apagados or 0) == 1,
				"the temporary bin must be deleted afterwards - a leftover folder "
				.. "in the user's Media Pool is not an acceptable side effect")

			-- e o carimbo do bin fica no disco, senao a proxima rodada exporta
			-- de novo (ou importa um bin velho sem saber)
			local fh = io.open(temp .. ".versao", "r")
			checa(fh ~= nil, "the bin version stamp was not written")
			if fh then
				checa(tonumber((fh:read("*a") or ""):match("%d+")) == d.macro_versao,
					"the bin stamp does not carry the macro version")
				fh:close()
			end
		end

		local resolve, reg = resolve_falso(d.macro_versao)
		local ok, err = pcall(M.main, resolve)
		checa(ok, "main blew up: " .. tostring(err))

		if ok then
			checa(#reg.comps == #d.segments,
				string.format("expected %d clips, got %d", #d.segments, #reg.comps))
			checa(reg.cores == #d.segments,
				string.format("%d clips marked done, expected %d",
					reg.cores, #d.segments))

			local tool = reg.comps[1] and reg.comps[1].tool
			checa(tool ~= nil, "the first clip exposed no Text+")

			-- A caixa so' e' conferida numa legenda que TENHA tempo por
			-- palavra: sem isso ela fica desligada de proposito (ver o teste
			-- logo abaixo), e elemento desligado nao materializa input nenhum.
			local i_com_words
			for k, seg in ipairs(d.segments) do
				if seg.words and #seg.words > 0 then i_com_words = k break end
			end
			if tool then
				local v = tool.valores
				-- o macro nasce azul (0, 0.35, 1); o estilo pede preto. Se o
				-- azul sobrar aqui, sobra na tela.
				checa(v.Red2 == d.inputs.Red2 and v.Green2 == d.inputs.Green2
					and v.Blue2 == d.inputs.Blue2,
					string.format("outline ended up (%s %s %s), asked (%s %s %s)",
						tostring(v.Red2), tostring(v.Green2), tostring(v.Blue2),
						tostring(d.inputs.Red2), tostring(d.inputs.Green2),
						tostring(d.inputs.Blue2)))
				checa(v.Font == d.inputs.Font, "font did not land")
				checa(v.Text == d.segments[1].text, "text did not land")

				-- E o Follower1, que e' quem de fato pinta. Enquanto o script
				-- escrevia so no Template, aqui ficava o 0.929 do AutoSubs e a
				-- legenda saia com a cor errada apesar de o log dizer "ok".
				local fv = reg.comps[1].follower.valores
				checa(fv.Red2 == d.inputs.Red2 and fv.Green2 == d.inputs.Green2
					and fv.Blue2 == d.inputs.Blue2,
					string.format("Follower1 outline ended up (%s %s %s), "
						.. "asked (%s %s %s)", tostring(fv.Red2),
						tostring(fv.Green2), tostring(fv.Blue2),
						tostring(d.inputs.Red2), tostring(d.inputs.Green2),
						tostring(d.inputs.Blue2)))
				checa(fv.Thickness2 == d.inputs.Thickness2,
					"Follower1 outline thickness ended up "
					.. tostring(fv.Thickness2) .. ", asked "
					.. tostring(d.inputs.Thickness2))
				-- e as opacidades NAO podem ter sido escritas la: no macro de
				-- verdade elas estao conectadas ao stretcher do fade
				checa(fv.Opacity3 == nil,
					"Opacity3 must not be written on Follower1 (breaks the fade)")

				-- toda caixa pedida tem que ter virado BORDA. Sem isso o Text+
				-- aceita Level/Extend/Round e nao desenha nada - e' o bug do
				-- box shadow.
				-- 2 = "Border Fill". O dump do Resolve confirmou o mapeamento
				-- lendo os presets de fabrica: elemento 1 (White Solid Fill)
				-- da' 0, elemento 2 (Red Outline) da' 1, elemento 4 (Blue
				-- Border) da' 3. Uma caixa e' um retangulo PREENCHIDO, entao 2.
				if i_com_words then
					local cv = reg.comps[i_com_words].tool.valores
					for chave in pairs(d.inputs) do
						local n = chave:match("^_borda(%d+)$")
						if n then
							checa(cv["ElementShape" .. n] == 2,
								"element " .. n .. " did not become a filled border "
								.. "(ElementShape=" .. tostring(cv["ElementShape" .. n])
								.. ", expected 2)")
							checa(cv["Round" .. n] ~= nil,
								"element " .. n .. " has no geometry (did SetInput "
								.. "land before Enabled?)")
						end
					end
				end

				-- a bolha marca a palavra falada: sem tempo por palavra ela
				-- tem que ficar DESLIGADA, senao vira uma caixa em cada
				-- palavra (ou em cada letra, conforme o Level)
				local so_destaque = {}
				for _, c in ipairs((d.destaque or {}).camadas or {}) do
					if c.on_base == 0 then so_destaque[c.elemento] = true end
				end
				for k, comp in ipairs(reg.comps) do
					local seg = d.segments[k]
					local tem_words = seg and seg.words and #seg.words > 0
					for el in pairs(so_destaque) do
						local esperado = tem_words and 1 or 0
						checa(comp.tool.valores["Enabled" .. el] == esperado,
							string.format("caption %d: element %d should be "
								.. "%s (words=%s), it is %s", k, el,
								esperado == 1 and "ON" or "off",
								tostring(tem_words),
								tostring(comp.tool.valores["Enabled" .. el])))
					end
				end
			end

			local com_w = 0
			for _, seg in ipairs(d.segments) do
				if seg.words and #seg.words > 0 then com_w = com_w + 1 end
			end
			-- O spline e' escrito em TODA legenda: com as palavras, ou vazio.
			-- Nao escrever deixava de pe os keyframes de exemplo do macro, que
			-- pintam o outline de azul caractere a caractere.
			checa(#reg.keyframes == #d.segments,
				string.format("the spline should be written on all %d captions, "
					.. "got %d", #d.segments, #reg.keyframes))

			-- O tempo por palavra tem que ficar guardado DENTRO do clipe: e' o
			-- que permite ao macro refazer os keyframes quando voce mexe numa
			-- cor no Inspector. Sem isso o seletor de cor de um elemento
			-- animado nao muda nada, porque a cor mora no keyframe.
			if i_com_words then
				local guardado = reg.comps[i_com_words].tool.dados
				local wt = guardado and guardado.GiWordTiming
				local cam = guardado and guardado.GiCamadas
				checa(wt and #wt == #d.segments[i_com_words].words,
					"GiWordTiming should hold " ..
					#d.segments[i_com_words].words .. " words, holds "
					.. tostring(wt and #wt))
				checa(cam and #cam == #d.destaque.camadas,
					"GiCamadas should hold " .. #d.destaque.camadas
					.. " layers, holds " .. tostring(cam and #cam))
				-- e cada camada precisa dizer de qual controle vem a cor dela,
				-- senao o macro nao sabe onde ler
				local com_ctl = 0
				for _, c in ipairs(cam or {}) do
					if c.controle then com_ctl = com_ctl + 1 end
				end
				checa(com_ctl > 0,
					"no stored layer names an Inspector control - the colour "
					.. "pickers would be decoration")
			end

			local com_array, vazios = 0, 0
			for _, kf in ipairs(reg.keyframes) do
				local tem = false
				for _, k in pairs(kf) do
					if k.Value and k.Value.Array and #k.Value.Array > 0 then
						tem = true
					end
				end
				if tem then com_array = com_array + 1 else vazios = vazios + 1 end
			end
			checa(com_array == com_w,
				string.format("%d captions with words should give %d splines "
					.. "with an array, got %d", com_w, com_w, com_array))
			checa(vazios == #d.segments - com_w,
				string.format("the %d captions without words should clear the "
					.. "spline, %d did", #d.segments - com_w, vazios))

			-- o keyframe da 1a palavra tem que acender a bolha SO nela
			-- o primeiro spline COM array: os de legenda sem words sao vazios
			-- de proposito
			local kf
			for _, cand in ipairs(reg.keyframes) do
				for _, k in pairs(cand) do
					if k.Value and k.Value.Array and #k.Value.Array > 0 then
						kf = cand
					end
				end
				if kf then break end
			end
			if kf then
				local por_indice = {}
				for _, k in pairs(kf) do
					for _, e in ipairs(k.Value.Array) do
						if e[1] == 2000 and e.Value == 1 then
							por_indice[e.Index] = (por_indice[e.Index] or 0) + 1
						end
					end
					break   -- basta o primeiro keyframe
				end
				-- O `Index` do array e' o elemento em base ZERO: 3 e' a bolha
				-- (elemento 4) e 4 e' a sombra dela (elemento 5).
				--
				-- QUAIS camadas existem sai do estilo, nao daqui. Com a sombra
				-- da bolha desligada (`box_shadow.ativo = false`) a camada 5 nem
				-- entra no destaque; exigir as duas fixas fazia o teste falhar
				-- por uma escolha de estilo em vez de por um defeito, e a
				-- mensagem apontava pro lugar errado.
				-- Duas naturezas de camada, e a diferenca esta no `on_base`:
				--
				--   on_base = 0  a camada MARCA a palavra falada (a bolha) -
				--                tem que acender em exatamente uma
				--   on_base = 1  a camada esta acesa em todas e o que muda na
				--                palavra falada e' a COR (o fill) - contar 1
				--                aqui seria exigir o oposto do que ela faz
				local esperadas = 0
				for _, c in ipairs((d.destaque or {}).camadas or {}) do
					if c.on_ativo == 1 then
						esperadas = esperadas + 1
						local i, n = c.elemento - 1, por_indice[c.elemento - 1]
						if c.on_base == 0 then
							checa(n == 1, "on the 1st keyframe the layer at "
								.. "Index " .. i .. " (element " .. c.elemento
								.. ") marks the spoken word, so it should light "
								.. "exactly 1, it lit " .. tostring(n))
						else
							checa(n ~= nil and n >= 1, "the layer at Index " .. i
								.. " (element " .. c.elemento .. ") stays lit on "
								.. "every word, it lit " .. tostring(n))
						end
					end
				end
				checa(esperadas > 0,
					"the style has no highlight layer that lights up - the "
					.. "first keyframe would have nothing to say")
			end
		end

		-- devolve o caminho real e leva embora o que este arquivo escreveu
		os.remove(BIN_DE_TESTE .. ".versao")
		os.remove(BIN_DE_TESTE .. ".tentado")
		M.definir_bin(bin_real)
	end
end

-- sempre o fixture (que TEM tempo por palavra, ao contrario da transcricao
-- real de hoje - sem ele o caminho do destaque nunca era exercitado)
roda_falso(aqui .. "amostra_legendas.lua")
if alvo then roda_falso(alvo) end

print(falhas == 0 and "ALL OK" or (falhas .. " failure(s)"))
os.exit(falhas == 0 and 0 or 1)
