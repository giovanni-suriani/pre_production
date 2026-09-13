--[[
GiAutoSubs - lado Resolve

Le o `legendas.lua` que o giautosubs.py escreveu e monta os clipes de legenda
na timeline, com cor por falante e destaque na palavra falada.

Convencao: COMENTARIOS em portugues sem acento; MENSAGENS (log, UI) em ingles.

Instalar
--------
Copie este arquivo para:
  %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\
Depois: Workspace > Scripts > GiAutoSubs

O que ele reaproveita, e por que
--------------------------------
O grafo do destaque (Follower1 -> CharacterLevelStyling -> spline de
keyframes) mora no macro "AutoSubs Caption". Reconstruir aquilo do zero em
Fusion e' de longe a parte mais cara, e nao traria nada de novo.

Tres coisas que este arquivo aprendeu do jeito caro
---------------------------------------------------
a) O macro do AutoSubs REAGE ao que a gente escreve. Mexer no input "Text"
   dispara UpdateTextContent -> ApplyWordTiming -> UpdateHighlight ->
   ApplyHighlight, que repinta Red2/Green2/Blue2, forca Enabled4 = 0 e
   reescreve o spline por cima dos nossos keyframes. Quem desarma essa cadeia
   e' o gerar_macro.py; aqui o texto e' escrito ANTES do estilo, pra que quem
   fale por ultimo sejamos nos de qualquer jeito.

b) `Level`, `ExtendHorizontal`, `ExtendVertical` e `Round` sao propriedades de
   BORDA. Num elemento de texto o Text+ aceita todas e nao desenha caixa
   nenhuma. Quem troca isso e' `ElementShape{n}`.

c) A cor tem CINCO origens possiveis, e vence a ultima (ver MACRO.md):
   INP_Default -> InstanceInput.Default -> Text+ -> Follower1 -> keyframe do
   spline. O macro vem com keyframes de EXEMPLO no spline que pintam o outline
   de rgb(0, 0.35, 1) caractere a caractere - era esse o "outline azul que nao
   muda com nada". Por isso o spline e' reescrito em TODA legenda, mesmo sem
   tempo por palavra.
]]

-- As tres perguntas da rodada
-- ---------------------------
-- Toda rodada pergunta, nesta ordem:
--
--   1) QUAL LEGENDA PADRAO   o Title instalado em Templates/Edit/Titles
--                            (`ESTILO_FIXO`, mais abaixo)
--   2) QUAL CONFIGURACAO     um preset exportado pelo botao "Export Config" do
--                            Inspector (`PRESET_FIXO`)
--   3) QUAL ARQUIVO          o legendas.lua que o giautosubs.py escreveu
--                            (`ARQUIVO`)
--
-- As tres tem o mesmo escape: com a constante preenchida, o dialogo nao abre.
-- Era assim que o script funcionava inteiro - caminho escrito no codigo, editar
-- o arquivo pra trocar de corte. Perguntar existe porque as tres respostas
-- mudam de uma rodada pra outra, e nenhuma delas o script tem como adivinhar.
--
-- O dialogo e' `fusion:RequestFile` nos tres casos, e nao `AskUser`: o AskUser
-- EXISTE como atributo e vem nil quando o script roda via Workspace > Scripts
-- fora da pagina Fusion, que e' o caso normal aqui (ver SpeakerSwitch.py).
--
-- Cancelar nunca e' erro: cai no que estava valendo antes (o padrao instalado,
-- nenhum preset, o ultimo arquivo) e o log diz o que foi usado - senao
-- "cancelei e veio outra coisa" vira bug.

-- Caminho do legendas.lua. Vazio = PERGUNTA.
local ARQUIVO = ""

-- Onde ficam as respostas da ultima rodada, pra os dialogos abrirem no lugar
-- certo em vez de na raiz do disco. E' conveniencia, nao configuracao: apagar
-- este arquivo nao muda nada alem de onde a caixa de dialogo comeca.
local ESCOLHAS = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_giescolhas.txt]]

-- Templates aceitos, em ordem de preferencia. O nosso vem primeiro: ele traz
-- Open Sans como fonte PADRAO (a do AutoSubs e' "Arial Rounded MT Bold", que
-- nao existe aqui e enche o Console de erro) e os controles novos no Inspector.
local TEMPLATES_PADRAO = { "GiAutoSubs Caption", "AutoSubs Caption" }

-- Qual legenda padrao (Title) usar. Vazio = PERGUNTA; com um nome dentro, usa
-- esse e nao pergunta nada.
--
-- Cada Title carrega o proprio estilo assado dentro - e' o que o
-- `gerar_macro.py --nome <estilo>` produz. Entao ESCOLHER O TITLE E' ESCOLHER O
-- ESTILO PADRAO desta rodada; o preset abaixo e' o que muda esse padrao sem
-- gerar Title nenhum.
local ESTILO_FIXO = ""

-- Qual configuracao de legenda aplicar por cima do padrao. Vazio = PERGUNTA
-- (quando houver algum preset gravado); com um caminho dentro, usa esse.
--
-- Um preset e' o que o botao "Export Config" do Inspector grava: os ~58
-- controles do clipe, `chave<TAB>valor`, com o nome que voce deu. E' o caminho
-- de volta do ajuste manual - voce mexe numa legenda ate' ficar do jeito que
-- quer, exporta, e a proxima rodada nasce assim, sem passar pelo estilos.json
-- e sem regerar o Title.
--
-- Ele VENCE o estilo assado no legendas.lua: entra em `dados.controles`, que e'
-- por onde o macro escreve o estilo (ver `fundir_preset`). O que o preset nao
-- disser continua vindo do estilo.
local PRESET_FIXO = ""

-- Onde o botao "Export Config" grava os presets - a mesma pasta que o
-- `gerar_macro.py` conhece por `PRESETS_DIR`.
local PRESETS_DIR = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\presets]]

-- A pasta com as tres opcoes da pergunta de conflito, uma por arquivo.
--
-- Sim, e' um menu feito de arquivos. O motivo: o unico dialogo que comprovada-
-- mente funciona daqui e' o `fusion:RequestFile` - `AskUser` vem nil fora da
-- pagina Fusion, e este script roda em Workspace > Scripts, da pagina Edit. As
-- perguntas 1 e 2 ja sao isso (escolha o .setting, escolha o preset); aqui as
-- opcoes nao eram arquivos, entao viraram. Os tres sao reescritos a cada
-- rodada, e' so' apagar a pasta pra ela voltar.
local CONFLITO_DIR = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\conflito]]

-- Onde o Fusion procura os Titles - a mesma pasta em que o
-- `gerar_macro.py --instalar` escreve.
local TITLES_DIR = (os.getenv("APPDATA") or "") ..
	[[\Blackmagic Design\DaVinci Resolve\Support\Fusion\Templates\Edit\Titles]]

-- A ordem de verdade, decidida na etapa 3 pelo `templates_preferidos()`. Nasce
-- igual ao padrao porque o modo "atualizar" nao chega a passar por la' e ainda
-- assim le `TEMPLATES[1]` no relatorio do fim.
local TEMPLATES = TEMPLATES_PADRAO

-- Bin exportado com o template dentro. E' o que mata o passo manual do Media
-- Pool - o mesmo truque do `caption-bin.drb` do AutoSubs.
--
-- Nao existe API pra por um Fusion Title no Media Pool; o que existe e'
-- `mediaPool:ImportFolderFromFile`, que importa um bin `.drb`. E existe o
-- caminho de volta: `mediaPool:ExportFolder`. Entao o arquivo nao precisa mais
-- ser exportado a mao - na primeira vez que o template estiver no Media Pool
-- deste projeto, o script exporta o bin sozinho, e o proximo projeto ja importa
-- sem ninguem arrastar nada.
--
-- O `.drb` guarda uma COPIA do macro do momento da exportacao, entao ele
-- envelhece igual a copia do Media Pool. Por isso o carimbo mora ao lado, num
-- arquivo `.versao`: importar um bin velho seria reimportar o problema que o
-- carimbo existe pra detectar.
local BIN_DRB = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\giautosubs-bin.drb]]
local BIN_VERSAO = BIN_DRB .. ".versao"

-- Trava de uma tentativa de importacao por projeto (a mesma do AutoSubs).
--
-- Sem ela, uma importacao que falha pela metade e' repetida a cada rodada, e
-- cada tentativa pode deixar um bin a mais no projeto - metade da confusao das
-- copias nasce dai.
local BIN_TENTADO = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_bin_importado.txt]]

-- Exportar o bin sozinho quando ele nao existir (ou estiver defasado).
local AUTO_EXPORTAR_BIN = true

-- O que fazer com legendas do GiAutoSubs que JA estao na timeline (MODO =
-- "criar"). Antes isso nao era decisao: a rodada criava por cima e a pilha
-- duplicada so aparecia depois, como "129 legendas achadas contra 128 criadas"
-- - voce editava a de baixo e via a de cima.
--
--   "substituir"  apaga as legendas da rodada anterior e reaproveita a track
--                 delas. So mexe em clipe que carrega o carimbo
--                 `GiAutoSubsVersao`: video, audio e titulo de outra gente
--                 nao sao tocados.
--   "contornar"   deixa tudo onde esta e NAO cria legenda onde ja existe uma.
--                 E' o modo pra completar uma rodada interrompida.
--   "track_nova"  ignora o que existe e empilha a rodada nova numa track
--                 acima. E' o comportamento antigo, agora por escolha.
--
-- Isto virou PERGUNTA (ver `escolher_conflito`). Continua aqui como o padrao
-- que vale quando nao ha o que perguntar - timeline sem legenda antiga - e
-- quando o dialogo e' cancelado. "substituir" APAGA clipe da timeline, e era a
-- unica das decisoes destrutivas da rodada que acontecia sem ninguem ser
-- consultado: voce so ficava sabendo lendo `conflict mode` no resumo, depois.
local CONFLITO = "substituir"

-- Escape: com um destes tres valores, nao pergunta nada. Irmao do ESTILO_FIXO
-- e do PRESET_FIXO.
local CONFLITO_FIXO = ""

-- As legendas entram em tracks NOVAS, acima de tudo que ja existe.
--
-- Com false, o `track` do estilos.json vira numero absoluto de track - e ai as
-- legendas caem em cima das tracks de video do SpeakerSwitch (V1/V2/V3), que
-- ja tem clipe. O Resolve recusa cada uma dessas insercoes e devolve nil no
-- lugar: foi assim que "129 clipes criados" viraram 9 estilizados.
local TRACKS_ACIMA = true

-- TODAS as legendas numa track so.
--
-- Uma track por falante so faz sentido quando se quer ligar/desligar as
-- legendas de cada pessoa separadamente. Para o caso normal - legenda que so
-- muda de cor conforme quem fala - tres tracks e' so tres coisas pra arrastar
-- junto toda vez. Com true, o `track` de cada falante no estilos.json e'
-- ignorado (a COR dele continua valendo).
local TRACK_UNICA = true

-- Com true: dump completo das propriedades de todos os elementos, no primeiro
-- clipe. Deixe ligado enquanto algo estiver saindo com a cara errada.
local DEBUG_PROPRIEDADES = true

-- "criar"     apaga nada, cria as legendas do zero na timeline
-- "atualizar" NAO cria clipe nenhum: reescreve o estilo nas legendas que ja
--             estao la. E' o modo pra mexer no estilos.json e ver o resultado
--             sem perder o que voce ajustou na mao (texto corrigido, clipe
--             movido, clipe aparado). Ver ATUALIZAR_TEXTO logo abaixo.
local MODO = "criar"

-- No modo "atualizar", reescrever tambem o TEXTO de cada legenda.
--
-- Fica false de proposito: corrigir texto na mao pelo Inspector e' o uso
-- normal, e sobrescrever isso a cada rodada de estilo seria destruir trabalho.
-- Ponha true quando a transcricao mudou e voce quer resincronizar tudo.
local ATUALIZAR_TEXTO = false

-- Com true: cria UM clipe so, faz o dump e para.
local DIAGNOSTICO = false

-- Quando o macro do Media Pool estiver defasado, trocar ele sozinho.
--
-- O Resolve guarda uma COPIA do titulo dentro do projeto quando ele entra no
-- Media Pool, e reinstalar o .setting nao mexe nessa copia. Dava pra mandar o
-- usuario apagar e reimportar na mao toda vez; da' pra fazer aqui.
--
-- Sobre apagar o item do Media Pool: a comp Fusion mora DENTRO de cada clipe
-- da timeline, nao e' lida do pool na hora de tocar - e' por isso que o macro
-- de um clipe pode estar defasado, e e' de la que o `conferir_macro` le o
-- carimbo. Um titulo arrastado de Effects > Titles direto pra timeline
-- funciona sem existir item nenhum no Media Pool, o que reforca que o clipe
-- nao depende do pool.
--
-- NAO VERIFICADO na marra: apagar o item com legendas antigas na timeline. A
-- evidencia diz que elas continuam inteiras; se algum dia aparecer clipe
-- offline depois de uma troca automatica, e' aqui que se desliga.
local AUTO_ATUALIZAR_TEMPLATE = true

--------------------------------------------------------------------------
-- Codigos internos do StyledText do Fusion. Sao os mesmos que o macro do
-- AutoSubs usa; opacidade (2600) fica de fora de proposito porque briga com
-- as animacoes de fade.
local COD = { Red = 2401, Green = 2402, Blue = 2403, Enabled = 2000 }

-- Inputs de elemento que precisam ser escritos TAMBEM no Follower1.
--
-- O StyledTextFollower e' um modificador: ele GERA o StyledText que alimenta o
-- Text+, e os inputs de elemento que ELE tem sobrescrevem os do Text+
-- caractere a caractere. O macro do AutoSubs traz `Red2 = 0.929,
-- Green2 = 0.051, Thickness2 = 0.8, Softness1..8 = 1` la dentro.
--
-- `Opacity{n}` de fora de proposito: no Follower1 as opacidades 1..4 estao
-- CONECTADAS ao AnimationKeyframeStretcher, e escrever um numero por cima
-- trocaria a conexao por um valor fixo, matando o fade sem dar erro nenhum.
-- Ver CHAVES_DO_FOLLOWER em giautosubs.py - as duas listas sao a mesma coisa.
local CHAVES_DO_FOLLOWER = {
	Enabled = true, Red = true, Green = true, Blue = true,
	Thickness = true, Softness = true,
}

-- Propriedades listadas no dump. Existe pra parar de adivinhar: o SetInput do
-- Fusion aceita nome errado e valor errado sem reclamar, entao a unica prova
-- de que algo entrou e' ler de volta.
local PROPRIEDADES = {
	"Enabled", "Name", "ElementShape", "Level", "Red", "Green", "Blue",
	"Alpha", "Opacity", "Softness", "Thickness", "ExtendHorizontal",
	"ExtendVertical", "Round", "Offset", "Position", "Expand", "BlendMode",
}

-- Controles do macro que o Inspector mostra. Sao a origem que o macro usa pra
-- repintar o Text+ - se eles discordarem do que esta na tela, um clique em
-- qualquer controle desfaz o estilo.
local CONTROLES = {
	"FillEnabled", "FillColorRed", "FillColorGreen", "FillColorBlue",
	"OutlineEnabled", "OutlineThickness",
	"OutlineColorRed", "OutlineColorGreen", "OutlineColorBlue",
	"ShadowEnabled", "ShadowColorRed", "ShadowColorGreen", "ShadowColorBlue",
	"BubbleEnabled", "BubbleColorRed", "BubbleColorGreen", "BubbleColorBlue",
	"BubbleOpacity", "BubbleLevel", "BubbleExtendHorizontal",
	"BubbleExtendVertical", "BubbleRound",
	"TextBoxEnabled", "TextBoxColorRed", "TextBoxColorGreen", "TextBoxColorBlue",
	"BoxShadowOnHighlight", "BoxShadowOnNormal",
	"BoxShadowColorRed", "BoxShadowColorGreen", "BoxShadowColorBlue",
	"BoxShadowCenterX", "BoxShadowCenterY", "BoxShadowOpacity",
	"BoxShadowSoftness", "GiAutoSubsVersao",
}

local NOME_ELEMENTO = {
	[1] = "fill", [2] = "outline", [3] = "text shadow",
	[4] = "highlight bubble", [5] = "bubble shadow",
	[6] = "text box", [7] = "text box shadow", [8] = "free",
}

-- Alem do Console, toda linha vai pra um arquivo ao lado deste script.
--
-- O Console do Resolve nao tem como copiar um log longo: uma rodada de 128
-- legendas com dump de propriedades passa de trezentas linhas e rola pra fora
-- antes de dar pra selecionar. Com o arquivo, mandar o resultado e' mandar o
-- caminho. Aberto e fechado a cada linha de proposito: se o script morrer no
-- meio, o que ja saiu esta no disco.
local LOG = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\_giautosubs.log]]

local function _para_arquivo(linha, modo)
	local fh = io.open(LOG, modo or "a")
	if not fh then return end          -- sem permissao: segue so' com o Console
	fh:write(linha, "\n")
	fh:close()
end

_para_arquivo("=== GiAutoSubs " .. os.date("%Y-%m-%d %H:%M:%S") .. " ===", "w")

local function log(...)
	local linha = "[GiAutoSubs] " .. table.concat({ ... }, " ")
	print(linha)
	_para_arquivo(linha)
end

local function etapa(n, total, texto)
	print(string.format("[GiAutoSubs] [%d/%d] %s", n, total, texto))
end

local function mostrar(v)
	if v == nil then return "-" end
	if type(v) == "table" then
		local partes = {}
		for _, x in ipairs(v) do partes[#partes + 1] = tostring(x) end
		return "{" .. table.concat(partes, ",") .. "}"
	end
	if type(v) == "number" then
		if v == math.floor(v) then return tostring(math.floor(v)) end
		return string.format("%.4f", v)
	end
	return tostring(v)
end

-- Espera de verdade.
--
-- A versao anterior usava `if bmd and bmd.wait then ... end`. No host de
-- Scripts do Resolve `bmd.wait` nao existe, entao a condicao era falsa e as
-- tentativas de esperar a comp aconteciam todas no mesmo instante.
local function esperar(segundos)
	if bmd and bmd.wait then
		bmd.wait(segundos)
		return
	end
	-- os.clock conta tempo de CPU, entao o laco tem que queimar CPU pra
	-- avancar. Nao e' elegante; e' o que existe sem biblioteca aqui.
	local ate = os.clock() + segundos
	while os.clock() < ate do end
end

-- Confere lendo de volta. Anunciar "aplicou" nao vale nada quando o SetInput
-- foi aceito e ignorado. So o GetInput depois prova.
local function verificar(tool, chave, esperado)
	local v
	pcall(function() v = tool:GetInput(chave) end)
	if v == nil then return "MISSING", nil end
	if esperado ~= nil then
		if type(esperado) == "number" and type(v) == "number" then
			return (math.abs(v - esperado) < 1e-6) and "ok" or "DIFFERS", v
		end
		return (tostring(v) == tostring(esperado)) and "ok" or "DIFFERS", v
	end
	return "ok", v
end

-- Direcao da sombra: o Text+ recebe um PONTO (x,y), e o nome do input varia
-- entre versoes do Fusion. "Offset" ANTES de "Position": os dois existem e sao
-- coisas diferentes. Position e' posicao ABSOLUTA - sondar ele primeiro fez o
-- outline com deslocamento (0,0) ir parar no canto da tela.
local OFFSET_CANDIDATOS = { "Offset", "Position", "Translate" }

--------------------------------------------------------------------------
-- Forma do elemento (o "Appearance" do Inspector: Text Fill / Text Outline /
-- Border Fill / Border Outline, no input `ElementShape{n}`).
--
-- Os elementos 1..4 do Text+ nascem dos presets de fabrica (White Solid Fill /
-- Red Outline / Black Shadow / Blue Border). O 4 ja e' borda, e e' por isso
-- que a bolha do AutoSubs funciona sem ninguem tocar em ElementShape; os
-- elementos 5..8 nascem como texto.
--
-- O mapeamento saiu do dump, lendo os defaults de fabrica de volta:
--
--     elemento 1 "White Solid Fill" -> ElementShape = 0
--     elemento 2 "Red Outline"      -> ElementShape = 1
--     elemento 4 "Blue Border"      -> ElementShape = 3
--
-- Ou seja: 0 Text Fill, 1 Text Outline, 2 Border Fill, 3 Border Outline.
--
-- Uma bolha/caixa e' um retangulo PREENCHIDO, entao o valor certo e' 2. A
-- versao anterior "calibrava" lendo o elemento 4 e pegava 3 - contorno de
-- caixa, nao caixa. Calibragem saiu: o numero agora esta escrito, e o dump
-- imprime os rotulos do combo pra qualquer duvida ser resolvida lendo o log.
local FORMA = { TEXTO = 0, TEXTO_CONTORNO = 1, BORDA = 2, BORDA_CONTORNO = 3 }

function aplicar_offset(tool, n, xy, logar)
	for _, base in ipairs(OFFSET_CANDIDATOS) do
		local nome = base .. n
		local ok = pcall(function() tool:SetInput(nome, { xy[1], xy[2] }) end)
		if ok then
			local v
			pcall(function() v = tool:GetInput(nome) end)
			if v ~= nil then
				if logar then
					log(string.format("      element %d offset via input '%s' (x=%.4f y=%.4f)",
						n, nome, xy[1], xy[2]))
				end
				return nome
			end
		end
	end
	if logar then
		log("      WARNING: no offset input accepted on element " .. n
			.. " - this shadow will have no direction.")
		log("      tried: " .. table.concat(OFFSET_CANDIDATOS, n .. ", ") .. n)
	end
	return nil
end

--------------------------------------------------------------------------
-- O contrato do macro: uma funcao escreve o estilo, outra le.
--
-- As rotinas moram no `CustomData` do MacroOperator - NAO do `Template`. Sao
-- dois tools diferentes, entao `tool:GetData(...)` no Text+ volta nil e o
-- `comp:GetData(...)` tambem: a comp nao e' dona de nada disso. O unico jeito
-- que funciona e' perguntar a cada tool da comp quem responde pelo nome.
--
-- Isto nao e' teoria: era por nao fazer esta varredura que o resumo do run dizia
-- "one by one (the chunks are not reachable from a script)" e que o botao do
-- Inspector dizia "nothing was applied".
local function dado_do_macro(comp, tool, nome)
	local v
	pcall(function() v = tool:GetData(nome) end)
	if v ~= nil then return v end

	local tools
	pcall(function() tools = comp:GetToolList(false) end)
	for _, t in pairs(tools or {}) do
		pcall(function() v = t:GetData(nome) end)
		if v ~= nil then return v end
	end
	return nil
end

local function rotina_do_macro(comp, tool, nome)
	local f = dado_do_macro(comp, tool, nome)
	if type(f) ~= "string" then return nil end
	return f
end

-- Qual controle do Inspector liga cada elemento de caixa. Serve pra uma coisa
-- so, mas importante: numa legenda SEM tempo por palavra a bolha precisa nascer
-- desligada (nao ha palavra falada pra marcar), e como agora quem escreve o
-- estilo e' o macro - a partir dos controles - desligar so o `Enabled4` nao
-- basta: o ApplyGiStyle leria `BubbleEnabled = 1` e reacenderia.
local CHAVE_LIGA_ELEMENTO = {
	[4] = "BubbleEnabled", [5] = "BoxShadowOnHighlight",
	[6] = "TextBoxEnabled", [7] = "BoxShadowOnNormal",
}

-- O estilo entra por UMA porta.
--
-- `preset` e' a tabela opaca que o giautosubs.py montou: este script nao sabe
-- (nem precisa saber) o que tem dentro. O schema e' o `InputKeys`, e ele mora
-- no macro - e' por isso que um controle novo nao pede uma linha de codigo
-- aqui.
--
-- `false` no spline e' de proposito: o array por palavra e' reescrito logo
-- adiante, e refazer aqui seria pagar a metade cara do callback 128 vezes por
-- nada.
--
-- O fallback nao e' zelo. Quando o script nao alcanca os chunks (ver acima),
-- escrever controle por controle e' exatamente o que este arquivo fazia antes:
-- o estilo entra igual, so' sem o caminho unico.
-- `refazerSpline`: quem reconstroi o array de estilo por caractere. Falso (o
-- normal) quer dizer "nao refaca, eu escrevo o array em seguida" - e' o passo 8.
-- Verdadeiro e' a opcao "use these" do conflito, onde o passo 8 nao escreve nada
-- pra preservar o `GiWordTiming` do clipe, e o macro refaz o array a partir
-- DESSE mesmo tempo por palavra.
local function aplicar_preset(comp, tool, preset, refazerSpline)
	local porque = "the chunks are not reachable from a script"
	local f = rotina_do_macro(comp, tool, "SetInputValues")
	if f then
		local ok, erro = pcall(function()
			loadstring(f)()(comp, tool, preset, "script", refazerSpline or false)
		end)
		if ok then return "SetInputValues (the macro's own contract)" end
		-- Cair pro caminho longo aqui e' o ponto: uma rotina que levanta nao
		-- pode virar 128 legendas sem estilo nenhum.
		porque = "SetInputValues raised: " .. tostring(erro)
	end
	for chave, valor in pairs(preset or {}) do
		pcall(function() tool:SetInput(chave, valor) end)
	end
	return "one by one (" .. porque .. ")"
end

--------------------------------------------------------------------------
-- As respostas da ultima rodada.
--
-- Guardadas so' pra o dialogo abrir onde voce estava - com tres perguntas por
-- rodada, comecar da raiz do disco toda vez seria pior que a constante que
-- estas perguntas vieram substituir. Uma linha por chave, `chave<TAB>valor`,
-- porque um arquivo que da' pra ler com os olhos da' pra consertar no Notepad.
local function escolhas_lidas()
	local t = {}
	local fh = io.open(ESCOLHAS, "r")
	if not fh then return t end
	for linha in fh:lines() do
		local k, v = linha:match("^([^\t]+)\t(.*)$")
		if k then t[k] = (v:gsub("%s+$", "")) end
	end
	fh:close()
	return t
end

local function lembrar(chave, valor)
	local t = escolhas_lidas()
	t[chave] = valor or ""
	pcall(function()
		local fh = io.open(ESCOLHAS, "w")
		if not fh then return end
		for k, v in pairs(t) do fh:write(k, "\t", v, "\n") end
		fh:close()
	end)
end

-- Pergunta um arquivo. Devolve nil quando o usuario cancela OU quando o
-- dialogo nao existe nesta forma de rodar - quem chama decide o que fazer,
-- porque nos dois casos a resposta certa e' "segue no padrao, dizendo qual".
local function perguntar_arquivo(titulo, pasta, arquivo, filtro)
	local escolhido
	pcall(function()
		if not (fusion and fusion.RequestFile) then return end
		local pedido = { FReqB_SeqGather = false, FReqS_Title = titulo }
		if filtro then pedido.FReqS_Filter = filtro end
		local caminho = fusion:RequestFile(pasta or "", arquivo or "", pedido)
		if caminho and caminho ~= "" then escolhido = caminho end
	end)
	return escolhido
end

-- A pasta de um caminho, com a barra no fim (e' o que o RequestFile quer).
local function pasta_de(caminho)
	return caminho and caminho:match("^(.*[\\/])") or nil
end

--------------------------------------------------------------------------
-- O preset: a configuracao exportada de um clipe.
--
-- Mesmo formato do "Generate Caption Style" (`chave<TAB>valor`), e por isso o
-- mesmo arquivo serve pros dois lados: aqui ele vira o estilo da rodada, e no
-- Python o `gerar_macro.py --importar-estilo <arquivo>` transforma o mesmo
-- dump num estilo nomeado do estilos.json.
--
-- Valores: numero, `{a,b}` (os inputs de par, como Offset e Center) ou texto
-- (Font, Style). Um `{}` que nao vire tabela aqui chegaria no SetInput como a
-- string "{0.5,0.22}" e o Fusion aceitaria calado.
local function ler_preset(caminho)
	local fh = io.open(caminho, "r")
	if not fh then return nil, "could not open " .. tostring(caminho) end
	local valores, nome, n = {}, nil, 0
	for linha in fh:lines() do
		local chave, valor = linha:match("^([^\t]+)\t(.*)$")
		if chave then
			valor = (valor:gsub("%s+$", ""))
			if chave == "#nome" then
				nome = valor
			elseif chave:sub(1, 1) ~= "#" then
				local dentro = valor:match("^{(.*)}$")
				if dentro then
					local par = {}
					for p in dentro:gmatch("[^,]+") do
						par[#par + 1] = tonumber(p)
					end
					valores[chave] = par
				else
					valores[chave] = tonumber(valor) or valor
				end
				n = n + 1
			end
		end
	end
	fh:close()
	if n == 0 then
		return nil, "no 'key<TAB>value' line in " .. tostring(caminho)
			.. " - is this a preset from the Export Config button?"
	end
	return { valores = valores, nome = nome, n = n }
end

-- O preset ganha do estilo assado no legendas.lua.
--
-- Ele entra em `dados.controles` porque quem escreve o estilo e' o MACRO, a
-- partir dos controles (`aplicar_preset` -> SetInputValues). Os `Offset{n}` sao
-- a excecao: eles nao passam pelo contrato do macro - o script os escreve
-- direto, no passo 6, DEPOIS do preset - entao um offset que ficasse so' nos
-- controles seria reescrito pelo estilo logo em seguida, calado.
--
-- O que o preset nao disser continua vindo do estilo: fundir, nao substituir.
--
-- A SEGUNDA excecao sao as camadas animadas, e ela tem a mesma forma do Offset:
-- o array de estilo por caractere e' escrito no passo 8 a partir de
-- `dados.destaque.camadas` - o ESTILO -, DEPOIS de o preset ter escrito os
-- controles no passo 5 (que ainda por cima manda `spline = false`, pra nao
-- refazer duas vezes). Como o array vence os inputs, um preset com
-- `WordFillEnabled = 0` produzia um clipe com o Inspector dizendo "off" e o
-- spline pintando a palavra falada de amarelo assim mesmo, ate' alguem clicar em
-- Apply Style. O preset precisa de caminho ate' as camadas, nao so' ate' os
-- controles.
local CONTROLE_QUE_LIGA = {
	[1] = "WordFillEnabled",       -- Spoken Word: a cor da palavra falada
	[4] = "BubbleEnabled",         -- a bolha
	[5] = "BoxShadowOnHighlight",  -- a sombra da bolha
}

-- A cor de um par de controles (`FillColor*`, `WordFillColor*`), com o valor do
-- estilo como reserva - o preset pode trazer o checkbox sem trazer a cor.
local function cor_dos_controles(controles, prefixo, reserva)
	reserva = reserva or { 1, 1, 1 }
	local function canal(sufixo, padrao)
		local v = controles[prefixo .. "Color" .. sufixo]
		if type(v) == "number" then return v end
		return padrao
	end
	return { canal("Red", reserva[1]), canal("Green", reserva[2]),
		canal("Blue", reserva[3]) }
end

local function fundir_preset(dados, valores)
	dados.controles = dados.controles or {}
	dados.inputs = dados.inputs or {}
	local n = 0
	for chave, valor in pairs(valores) do
		dados.controles[chave] = valor
		local el = chave:match("^Offset(%d+)$")
		if el then dados.inputs["_offset" .. el] = valor end
		n = n + 1
	end

	-- As camadas, agora que os controles ja estao fundidos (as cores abaixo
	-- saem deles, entao a ordem importa).
	local camadas = (dados.destaque or {}).camadas
	if camadas then
		for i = #camadas, 1, -1 do
			local chave = CONTROLE_QUE_LIGA[camadas[i].elemento]
			if chave and valores[chave] ~= nil and valores[chave] ~= 1 then
				table.remove(camadas, i)
			end
		end

		-- Ligar pelo preset so' vale pro elemento 1, e e' de proposito: e' a
		-- unica camada que da' pra criar do nada, porque a cor dela sai de dois
		-- controles e nao ha geometria pra montar. E' a mesma regra do
		-- `GiRebuildHighlight` no macro, que tambem so' cria a do fill.
		if valores.WordFillEnabled == 1 then
			local tem = false
			for _, c in ipairs(camadas) do
				if c.elemento == 1 then tem = true end
			end
			if not tem then
				camadas[#camadas + 1] = {
					elemento = 1, on_base = 1, on_ativo = 1, controle = "Fill",
					cor_base = cor_dos_controles(dados.controles, "Fill"),
					cor_ativa = cor_dos_controles(dados.controles, "WordFill"),
				}
			end
		end
	end
	return n
end

local function ler_dados(caminho)
	local fh = io.open(caminho, "r")
	if not fh then return nil, "could not open " .. tostring(caminho) end
	local txt = fh:read("*a")
	fh:close()
	local chunk, err = loadstring(txt)
	if not chunk then return nil, "invalid legendas.lua: " .. tostring(err) end
	local ok, dados = pcall(chunk)
	if not ok then return nil, "error evaluating legendas.lua: " .. tostring(dados) end
	return dados
end

local function segundos_para_frames(s, fps)
	return math.floor(tonumber(s) * fps + 0.5)
end

-- Procura o template no Media Pool. Igual ao AutoSubs: varre as subpastas
-- primeiro, e casa por prefixo porque o nome do macro carrega a versao.
--
-- Devolve tambem a PASTA onde ele estava - e' o que permite exportar um bin com
-- o template dentro sem levar junto o resto do Media Pool.
local function achar_template_e_pasta(folder, nome)
	for _, sub in ipairs(folder:GetSubFolderList()) do
		local achado, pasta = achar_template_e_pasta(sub, nome)
		if achado then return achado, pasta end
	end
	for _, clip in ipairs(folder:GetClipList()) do
		local n = clip:GetName() or ""
		if n == nome or n:sub(1, #nome) == nome then return clip, folder end
	end
	return nil
end

local function achar_template(folder, nome)
	local achado = achar_template_e_pasta(folder, nome)
	return achado
end

-- Os Titles GiAutoSubs instalados no disco, pelo nome (sem `.setting`).
--
-- `bmd.readdir` e' a leitura de pasta do proprio Fusion; o `dir /b` esta' ali
-- porque ela nao existe em toda forma de rodar script, e uma lista vazia aqui
-- viraria "so' existe um estilo" calado - que e' pior que perguntar a' toa.
local function titles_instalados()
	local nomes, vistos = {}, {}
	local function juntar(arquivo)
		local nome = arquivo:match("^(.+)%.setting$")
		if nome and nome:sub(1, 10) == "GiAutoSubs" and not vistos[nome] then
			vistos[nome] = true
			nomes[#nomes + 1] = nome
		end
	end

	pcall(function()
		for _, item in ipairs(bmd.readdir(TITLES_DIR .. [[\*.setting]]) or {}) do
			if not item.IsDir then juntar(item.Name or "") end
		end
	end)

	if #nomes == 0 then
		pcall(function()
			local p = io.popen('dir /b "' .. TITLES_DIR .. [[\GiAutoSubs*.setting"]])
			if not p then return end
			for linha in p:lines() do juntar((linha:gsub("%s+$", ""))) end
			p:close()
		end)
	end

	table.sort(nomes)
	return nomes
end

-- PERGUNTA 1: qual legenda padrao (Title) usar nesta rodada.
--
-- Devolve a ordem de preferencia dos templates, ja com a escolha na frente.
--
-- Pergunta mesmo com UM Title instalado. Antes so' perguntava com dois ou mais
-- ("um dialogo de um botao so' e' um passo a mais entre voce e as legendas"),
-- e o preco disso era nao ter onde dizer "hoje quero o outro" sem editar o
-- script - a pergunta e' justamente o que o usuario pediu. Com ZERO instalados
-- nao ha o que perguntar: cai no `TEMPLATES_PADRAO`, que ainda pode achar uma
-- copia velha no Media Pool.
--
-- O dialogo e' `fusion:RequestFile` e nao `AskUser` de proposito. O AskUser
-- EXISTE como atributo e vem nil quando o script roda via Workspace > Scripts
-- fora da pagina Fusion, que e' o caso normal aqui (ver SpeakerSwitch.py). O
-- RequestFile ja e' usado neste arquivo pra achar o legendas.lua, e funciona.
-- De quebra ele mostra a pasta de Titles de verdade: o que voce ve na caixa e'
-- exatamente o que o Fusion vai carregar.
local function templates_preferidos()
	local lista = {}
	local function poe(nome)
		if nome and nome ~= "" then lista[#lista + 1] = nome end
	end

	if ESTILO_FIXO ~= "" then
		log("      style fixed in the script: '" .. ESTILO_FIXO .. "'")
		poe(ESTILO_FIXO)
		for _, n in ipairs(TEMPLATES_PADRAO) do poe(n) end
		return lista
	end

	local instalados = titles_instalados()
	if #instalados > 0 then
		log("      " .. #instalados .. " caption style(s) installed:")
		for _, n in ipairs(instalados) do log("        - " .. n) end

		local anterior = escolhas_lidas().estilo
		local caminho = perguntar_arquivo(
			"1/3  Pick the default caption (Title) for this run",
			TITLES_DIR .. [[\]],
			anterior and (anterior .. ".setting") or "",
			"Fusion Titles (*.setting)|*.setting")
		local escolhido = caminho and caminho:match("([^\\/]+)%.setting$")

		if escolhido then
			log("      chosen: '" .. escolhido .. "'")
			lembrar("estilo", escolhido)
			poe(escolhido)
		else
			-- Cancelou, ou o dialogo nao existe nesta forma de rodar. Nos dois
			-- casos seguir com o padrao e' melhor que parar - mas dizendo qual
			-- foi usado, senao "escolhi outro e veio o de sempre" vira bug.
			if #instalados == 1 then poe(instalados[1]) end
			log("      no choice made (dialog cancelled or unavailable) - "
				.. "using the default order below.")
			log("      to skip the dialog, set ESTILO_FIXO at the top of this file.")
		end
	end

	for _, n in ipairs(TEMPLATES_PADRAO) do poe(n) end
	return lista
end

-- PERGUNTA 2: qual configuracao de legenda (preset) aplicar por cima.
--
-- Devolve (valores, rotulo) - `nil` quando nao ha preset nenhum, quando o
-- usuario cancela, ou quando o arquivo escolhido nao e' um preset. Nenhum
-- desses casos e' erro: sem preset, vale o estilo assado no legendas.lua, que
-- e' como o script rodou a vida inteira.
local function escolher_preset()
	local caminho = PRESET_FIXO
	if caminho ~= "" then
		log("      config fixed in the script: " .. caminho)
	else
		-- So' pergunta se ha o que oferecer. A pasta so' existe depois do
		-- primeiro "Export Config", e um dialogo vazio nao ensina nada.
		local tem = false
		pcall(function()
			for _, item in ipairs(bmd.readdir(PRESETS_DIR .. [[\*.txt]]) or {}) do
				if not item.IsDir then tem = true end
			end
		end)
		if not tem then
			log("      no caption config saved yet - using the style baked into")
			log("      legendas.lua. The 'Export Config' button in a caption's")
			log("      Inspector writes one into " .. PRESETS_DIR)
			return nil
		end

		local anterior = escolhas_lidas().preset
		caminho = perguntar_arquivo(
			"2/3  Pick the caption config (Cancel = the style in legendas.lua)",
			pasta_de(anterior) or (PRESETS_DIR .. [[\]]),
			anterior and anterior:match("([^\\/]+)$") or "",
			"GiAutoSubs config (*.txt)|*.txt")
		if not caminho then
			log("      no config chosen - using the style baked into legendas.lua")
			return nil
		end
	end

	local preset, err = ler_preset(caminho)
	if not preset then
		log("      WARNING: " .. tostring(err))
		log("      continuing with the style baked into legendas.lua")
		return nil
	end
	if PRESET_FIXO == "" then lembrar("preset", caminho) end
	return preset.valores,
		string.format("%s (%d values%s)", caminho, preset.n,
			preset.nome and (", '" .. preset.nome .. "'") or "")
end

-- PERGUNTA 4: o que fazer com as legendas da rodada anterior.
--
-- So' e' feita quando ha o que perguntar. Com a timeline limpa a resposta nao
-- muda nada, e um dialogo que nao muda nada e' um passo a mais entre voce e as
-- legendas - o mesmo argumento que a pergunta 1 usou pra NAO existir quando so'
-- havia um Title. A diferenca e' que aqui a resposta APAGA clipe, e por isso
-- ela nao pode continuar sendo uma constante no topo de um arquivo de 2300
-- linhas: o padrao `substituir` deleta a rodada anterior inteira, e a unica
-- pista disso era uma linha no resumo, depois de feito.
--
-- Ordem: 1 substituir, 2 contornar, 3 track nova. O numero na frente e' o que a
-- leitura casa - assim o resto do nome pode mudar sem quebrar o mapeamento, que
-- e' exatamente o tipo de `replace` silencioso que ja custou tres bugs nesta
-- serie (ver ESTADO.md, "os combos estavam vazios").
local OPCOES_CONFLITO = {
	{ n = 1, valor = "substituir",
	  arquivo = "1 - REPLACE - delete the previous run.txt",
	  texto = "Deletes the captions from the previous run and reuses their "
		.. "track.\nOnly clips carrying the GiAutoSubsVersao stamp are "
		.. "touched - video, audio and other people's titles are left alone." },
	{ n = 2, valor = "contornar",
	  arquivo = "2 - KEEP - only fill in what is missing.txt",
	  texto = "Deletes nothing. Captions that already start on a given frame "
		.. "are skipped.\nThis is the mode for finishing an interrupted run." },
	{ n = 3, valor = "track_nova",
	  arquivo = "3 - NEW TRACK - stack this run above the old one.txt",
	  texto = "Leaves the old captions alone and stacks this run on a track "
		.. "above.\nBoth sets stay on the timeline: you edit the one below and "
		.. "see the one on top." },
	{ n = 4, valor = "usar_existentes",
	  arquivo = "4 - USE THESE - restyle the captions already here.txt",
	  texto = "Creates nothing and deletes nothing. Restyles the captions that "
		.. "are already\non the timeline, keeping their position, their trims, "
		.. "the text you corrected\nby hand and their per-word timing - so the "
		.. "bubble stays exactly as synced as\nit is now.\n\n"
		.. "Each caption is matched to the transcript BY START FRAME, not by "
		.. "order, so\nit survives a clip you moved and a caption count that no "
		.. "longer matches.\nCaptions in the file with no clip here are listed "
		.. "at the end and left out." },
}

local function escolher_conflito(quantas, resumo)
	if CONFLITO_FIXO ~= "" then
		log("      conflict fixed in the script: '" .. CONFLITO_FIXO .. "'")
		return CONFLITO_FIXO
	end

	-- Semeia a pasta. Falhar aqui nao e' erro: sem os arquivos o dialogo abre
	-- vazio, o usuario cancela e vale o padrao - dito no log, como sempre.
	pcall(function() bmd.createdir(CONFLITO_DIR) end)
	local escritos = 0
	for _, o in ipairs(OPCOES_CONFLITO) do
		pcall(function()
			local fh = io.open(CONFLITO_DIR .. [[\]] .. o.arquivo, "w")
			if not fh then return end
			fh:write(o.texto, "\n")
			fh:close()
			escritos = escritos + 1
		end)
	end
	if escritos < #OPCOES_CONFLITO then
		log("      could not write the choice files in " .. CONFLITO_DIR)
		log("      keeping CONFLITO = '" .. CONFLITO .. "' from the top of this file")
		return nil
	end

	-- Reabre no que voce escolheu da ultima vez.
	local anterior = escolhas_lidas().conflito
	local sugerido = OPCOES_CONFLITO[1].arquivo
	for _, o in ipairs(OPCOES_CONFLITO) do
		if o.valor == anterior then sugerido = o.arquivo end
	end

	local caminho = perguntar_arquivo(
		string.format("%d caption(s) from a previous run are here (%s) - "
			.. "what should this run do with them?", quantas, resumo),
		CONFLITO_DIR .. [[\]], sugerido, "Choices (*.txt)|*.txt")
	-- O numero sai do NOME do arquivo, ancorado no comeco - nao do caminho.
	-- Procurar "digito seguido de tracinho" no caminho inteiro casaria com uma
	-- pasta chamada `my-stuff` antes de chegar no arquivo, e a escolha viraria
	-- outra sem uma linha de aviso.
	local nome = caminho and caminho:match("([^\\/]+)$")
	local numero = nome and nome:match("^(%d)")

	for _, o in ipairs(OPCOES_CONFLITO) do
		if numero == tostring(o.n) then
			log("      chosen: '" .. o.valor .. "'")
			lembrar("conflito", o.valor)
			return o.valor
		end
	end

	log("      no choice made (dialog cancelled or unavailable) - keeping "
		.. "CONFLITO = '" .. CONFLITO .. "'")
	log("      to skip this dialog, set CONFLITO_FIXO at the top of this file.")
	return nil
end

-- Todas as copias do template, em qualquer pasta. Duplicata no Media Pool nao
-- e' inofensiva: `achar_template` devolve a primeira que encontrar, e se a
-- primeira for a velha o script cria 128 legendas com o macro defasado.
local function todos_os_templates(folder, nome, acc)
	acc = acc or {}
	for _, sub in ipairs(folder:GetSubFolderList()) do
		todos_os_templates(sub, nome, acc)
	end
	for _, clip in ipairs(folder:GetClipList()) do
		local n = clip:GetName() or ""
		if n == nome or n:sub(1, #nome) == nome then acc[#acc + 1] = clip end
	end
	return acc
end

--------------------------------------------------------------------------
-- O bin `.drb`: o que mata o passo manual do Media Pool.
--
-- Um `.drb` e' uma copia CONGELADA do macro, entao ele envelhece exatamente
-- como a copia que o projeto guarda. Importar um bin velho seria reimportar o
-- problema que o carimbo existe pra detectar - dai o `.versao` ao lado.
local function versao_do_bin()
	local fh = io.open(BIN_VERSAO, "r")
	if not fh then return nil end
	local txt = fh:read("*a") or ""
	fh:close()
	return tonumber(txt:match("%d+"))
end

local function marcar_bin(versao)
	local fh = io.open(BIN_VERSAO, "w")
	if not fh then return end
	fh:write(tostring(versao or 0), "\n")
	fh:close()
end

-- Trava de uma tentativa por projeto - a mesma do AutoSubs.
--
-- Sem ela, uma importacao que falha e' repetida a cada rodada, e cada tentativa
-- pode deixar mais um bin no projeto. A trava vale pra combinacao projeto +
-- versao do bin: bin novo destrava sozinho, que e' o unico caso em que tentar
-- de novo faz sentido.
local function chave_da_trava(projeto, versao)
	return tostring(projeto) .. "\t" .. tostring(versao)
end

local function ja_tentou_importar(projeto, versao)
	local fh = io.open(BIN_TENTADO, "r")
	if not fh then return false end
	local txt = fh:read("*a") or ""
	fh:close()
	local alvo = chave_da_trava(projeto, versao)
	for linha in txt:gmatch("[^\r\n]+") do
		if linha == alvo then return true end
	end
	return false
end

local function marcar_tentativa(projeto, versao)
	local fh = io.open(BIN_TENTADO, "a")
	if not fh then return end
	fh:write(chave_da_trava(projeto, versao), "\n")
	fh:close()
end

-- Exporta o bin a partir do template que ja esta no Media Pool.
--
-- Existe pra que "arraste o titulo pro Media Pool" seja feito UMA vez na vida,
-- e nao uma vez por projeto: com o `.drb` no disco, o proximo projeto importa
-- sozinho.
--
-- O template vai pra uma pasta so' dele antes de exportar. Exportar a pasta
-- onde ele estava levaria junto tudo que estiver la - e a pasta raiz e' o Media
-- Pool inteiro. `CopyClips` copia em vez de mover: o Media Pool do usuario sai
-- daqui como entrou.
local function exportar_bin(mediaPool, nome, versao)
	if not AUTO_EXPORTAR_BIN then return end
	if versao_do_bin() == versao then return end
	if not (mediaPool.ExportFolder and mediaPool.AddSubFolder
		and mediaPool.CopyClips) then
		log("      (this build cannot export a bin from a script - do it by")
		log("       hand once: right-click the bin > Export Bin File...)")
		return
	end

	local template = achar_template(mediaPool:GetRootFolder(), nome)
	if not template then return end

	local temp, exportou
	pcall(function()
		temp = mediaPool:AddSubFolder(mediaPool:GetRootFolder(), "_GiAutoSubs bin")
	end)
	if not temp then
		log("      could not create the temporary bin - the .drb was not exported")
		return
	end
	pcall(function() mediaPool:CopyClips({ template }, temp) end)
	pcall(function() exportou = mediaPool:ExportFolder(temp, BIN_DRB) end)
	-- A limpeza tem que acontecer mesmo se a exportacao falhar, senao sobra uma
	-- pasta no Media Pool do usuario por causa de um passo opcional.
	pcall(function() mediaPool:DeleteFolders({ temp }) end)

	if exportou then
		marcar_bin(versao)
		log("      exported the template bin -> " .. BIN_DRB)
		log("      (from now on this is imported automatically, in any project)")
	else
		log("      ExportFolder refused - the .drb was not written")
	end
end

-- Apaga as copias velhas do template, deixando so' a que acabou de entrar.
--
-- So' roda depois de uma semeadura bem-sucedida: apagar antes de ter o
-- substituto na mao ja deixou o usuario sem template nenhum uma vez.
local function limpar_templates_obsoletos(mediaPool, nome, manter)
	if not mediaPool.DeleteClips then return 0 end
	local velhos = {}
	for _, clip in ipairs(todos_os_templates(mediaPool:GetRootFolder(), nome)) do
		if clip ~= manter then velhos[#velhos + 1] = clip end
	end
	if #velhos == 0 then return 0 end
	local ok = pcall(function() mediaPool:DeleteClips(velhos) end)
	if ok then
		log(string.format("      removed %d stale copy(ies) of '%s' from the "
			.. "Media Pool", #velhos, nome))
		return #velhos
	end
	log("      WARNING: the new template is in, but the stale copies could not")
	log("      be deleted - you may end up with more than one entry.")
	return 0
end

--------------------------------------------------------------------------
-- Destaque: monta os keyframes de estilo por caractere.
--
-- A ideia: para cada palavra i, escrevemos UM keyframe que descreve o estado
-- de TODAS as palavras naquele instante - a palavra i acesa, as outras
-- apagadas. Trocar de palavra e' trocar de keyframe.
--------------------------------------------------------------------------
local function entradas_para(elemento, palavra, ligado, cor)
	-- Index do StyledText e' 0-based; os inputs do Text+ sao 1-based.
	local idx = elemento - 1
	local vals = {
		[COD.Enabled] = ligado and 1 or 0,
		[COD.Red] = cor and cor[1] or 0,
		[COD.Green] = cor and cor[2] or 0,
		[COD.Blue] = cor and cor[3] or 0,
	}
	local out = {}
	for codigo, valor in pairs(vals) do
		table.insert(out, {
			codigo, palavra.startIndex, palavra.endIndex,
			Value = valor, __flags = 256, Index = idx,
		})
	end
	return out
end

-- `destaque.camadas` e' uma LISTA porque um destaque util quase nunca mexe num
-- elemento so: "fill rosa na palavra falada + caixa atras dela + sombra da
-- caixa" sao tres elementos animados no mesmo keyframe.
local function montar_keyframes(tempos, destaque, fps)
	local camadas = destaque.camadas
	if not camadas or #camadas == 0 then return {} end

	-- Duas palavras podem cair no MESMO frame: o Whisper as vezes devolve
	-- duracao zero (start == end), e ai a segunda sobrescreveria a chave da
	-- primeira e uma palavra nunca acenderia.
	local ultimo = -1
	for _, t in ipairs(tempos) do
		if t.startFrame <= ultimo then t.startFrame = ultimo + 1 end
		ultimo = t.startFrame
	end

	local keyframes, n = {}, 0
	for i, _ in ipairs(tempos) do
		local array = {}
		for j, palavra in ipairs(tempos) do
			local ativa = (j == i)
			for _, c in ipairs(camadas) do
				local ligado = (ativa and c.on_ativo or c.on_base) == 1
				local cor = ativa and c.cor_ativa or c.cor_base
				for _, e in ipairs(entradas_para(c.elemento, palavra, ligado, cor)) do
					table.insert(array, e)
				end
			end
		end

		keyframes[tempos[i].startFrame] = {
			n,
			Value = {
				__ctor = "StyledText",
				Array = array,
				Flags = { StepIn = true, LockedY = true, __flags = 256 },
			},
		}
		n = n + 1
	end
	return keyframes
end

-- Keyframe unico com array VAZIO = "sem estilo por caractere".
--
-- Precisa existir porque o macro do AutoSubs vem com keyframes de EXEMPLO no
-- spline de character-level styling, e eles pintam o outline de rgb(0, .35, 1)
-- - azul - caractere a caractere. Estilo por caractere vence tanto o Text+
-- quanto o Follower1: era esse o outline azul que sobrevivia a tudo, inclusive
-- ao seletor de cor do Inspector.
--
-- No AutoSubs quem limpava era o RemoveHighlight, desarmado aqui porque ele
-- tambem apagava os NOSSOS keyframes. O gerar_macro.py ja apaga os de exemplo
-- do arquivo; isto cobre o clipe que veio de um macro velho.
local function keyframes_vazios()
	return {
		[0] = {
			0,
			Value = {
				__ctor = "StyledText",
				Array = {},
				Flags = { StepIn = true, LockedY = true, __flags = 256 },
			},
		},
	}
end

-- Qual controle do Inspector manda na cor de cada camada animada.
--
-- Serve pro macro refazer o array sozinho quando alguem mexe numa cor: num
-- elemento animado a cor mora no keyframe, nao no input, entao sem este mapa o
-- seletor de cor da bolha seria enfeite.
--
-- O elemento 1 (fill) e' o unico com DOIS controles: a cor base vem do
-- `Fill Color` e a da palavra falada vem do `Word Color` (grupo Spoken Word),
-- enquanto o checkbox dele estiver marcado. Quem resolve esse par e' o
-- `cor_de` do `GiRebuildHighlight`, no macro - aqui fica so' o controle da
-- base, que e' o que o nome da camada consegue dizer.
--
-- Ate o macro 21 o 1 ficava FORA desta tabela, porque a cor base dele era a do
-- FALANTE, escrita clipe a clipe. Essa ideia saiu no 22: o resultado era um
-- Fill Color que nao pintava nada e uma legenda de cor imprevisivel.
local CONTROLE_DA_CAMADA = {
	[1] = "Fill",
	[4] = "Bubble", [5] = "BoxShadow", [6] = "TextBox", [7] = "BoxShadow",
}

local function camadas_para_dados(camadas)
	local out = {}
	for _, c in ipairs(camadas or {}) do
		out[#out + 1] = {
			elemento = c.elemento,
			on_ativo = c.on_ativo,
			on_base = c.on_base,
			cor_ativa = c.cor_ativa,
			cor_base = c.cor_base,
			controle = CONTROLE_DA_CAMADA[c.elemento],
		}
	end
	return out
end

local function tempos_das_palavras(seg, fps)
	if not seg.words or #seg.words == 0 then return nil end
	local out, inicio = {}, 0
	for _, w in ipairs(seg.words) do
		-- conta CARACTERE (o texto e' exatamente a concatenacao dos tokens,
		-- garantido pelo 4_transcribe_whisper.py)
		local _, n = w.word:gsub("[^\128-\191]", "")
		local fim = inicio + n - 1
		table.insert(out, {
			startIndex = inicio,
			endIndex = fim,
			startFrame = math.max(0, segundos_para_frames(w.start - seg.start, fps)),
		})
		inicio = fim + 1
	end
	return out
end

-- Reparte um texto em palavras, por INDICE DE CARACTERE.
--
-- Mesma regra do `tempos_das_palavras` e do `fatiar` do macro: o espaco
-- separador pertence a palavra SEGUINTE (" ir."), entao os pedacos sao
-- contiguos e a concatenacao e' exatamente o texto. Anda em CODEPOINT e nao em
-- byte - o array de estilo por caractere conta caractere, e "acao" com cedilha
-- tem 4, nao 6.
local function fatiar_texto(s)
	local pedacos, ini, pos, branco_antes = {}, 0, 0, nil
	local i = 1
	while i <= #s do
		local b = s:byte(i)
		local n = 1
		if b >= 240 then n = 4 elseif b >= 224 then n = 3
		elseif b >= 192 then n = 2 end
		local ch = s:sub(i, i + n - 1)
		local branco = (ch == " " or ch == "\n" or ch == "\t")
		if pos > 0 and branco and not branco_antes then
			pedacos[#pedacos + 1] = { startIndex = ini, endIndex = pos - 1 }
			ini = pos
		end
		branco_antes = branco
		pos = pos + 1
		i = i + n
	end
	if pos > 0 then
		pedacos[#pedacos + 1] = { startIndex = ini, endIndex = pos - 1 }
	end
	return pedacos
end

-- Refaz o tempo por palavra a partir do texto que ESTA no clipe.
--
-- O caso: voce corrigiu "i love potato" para "i love the potato" no Inspector. O
-- `GiWordTiming` endereca por indice de caractere, entao os indices velhos
-- passam a apontar pro lugar errado - " potato" (6..12) vira " the po" - e a
-- palavra nova nao tem tempo nenhum, porque ela nunca foi falada. O macro sabe
-- realinhar enquanto o NUMERO de palavras nao muda; mudou, ele avisa e (ate'
-- agora) reconstruia com os indices velhos assim mesmo.
--
-- O que da' pra fazer honestamente e' espalhar as palavras novas pelo MESMO
-- intervalo que a legenda ja ocupava: o frame de cada palavra sai de uma
-- interpolacao linear sobre os frames que estao gravados. A primeira e a ultima
-- palavra ficam exatamente onde estavam, e as do meio se redistribuem.
--
-- E' estimativa, e e' declarada como tal: o tempo da palavra nova nao existe em
-- lugar nenhum. Em troca, a bolha anda na ordem certa e nos caracteres certos -
-- que e' o que se ve. Nao mexer era deixa-la acendendo " the po" pra sempre.
--
-- Nao usa a duracao do clipe nem o segmento da transcricao de proposito: os
-- frames gravados sao o unico dado que pertence ao clipe, e este e' o modo que
-- promete nao re-sincronizar pela transcricao.
--
-- Devolve (tempos_novos, quantas_palavras) ou nil quando nao ha o que fazer.
local function refazer_tempos(texto, tempos)
	if type(texto) ~= "string" or not tempos or #tempos == 0 then return nil end
	local pedacos = fatiar_texto(texto)
	if #pedacos == #tempos then return nil end   -- o macro ja resolve esse caso
	if #pedacos == 0 then return nil end

	local m, n = #pedacos, #tempos
	for k, p in ipairs(pedacos) do
		local frame
		if m == 1 or n == 1 then
			frame = tempos[1].startFrame
		else
			-- posicao de k na escala dos frames velhos, em 0..n-1
			local t = (k - 1) * (n - 1) / (m - 1)
			local a = math.floor(t)
			local b = math.min(a + 1, n - 1)
			local f = t - a
			local fa = tempos[a + 1].startFrame
			local fb = tempos[b + 1].startFrame
			frame = math.floor(fa + (fb - fa) * f + 0.5)
		end
		p.startFrame = math.max(0, frame)
	end

	-- duas palavras no mesmo frame fariam uma delas nunca acender: o keyframe da
	-- segunda sobrescreve a chave da primeira. E' a mesma regra do
	-- `montar_keyframes`, e aqui ela e' mais provavel - a interpolacao amontoa
	-- palavras quando o texto cresce muito.
	local ultimo = -1
	for _, p in ipairs(pedacos) do
		if p.startFrame <= ultimo then p.startFrame = ultimo + 1 end
		ultimo = p.startFrame
	end
	return pedacos, m
end

--------------------------------------------------------------------------
-- Dump de propriedades: em vez de adivinhar, o Resolve conta.
--------------------------------------------------------------------------
local function dump_propriedades(comp, tool, follower, dados)
	log("")
	log("--------------------- PROPERTY DUMP ---------------------")
	log("Every value below was READ BACK from the tool, not assumed.")

	-- 1) Text+ e Follower1, elemento a elemento. As duas colunas existem
	-- porque o Follower vence o Text+ na tela: se elas divergirem, o que voce
	-- ve e' a coluna da direita.
	for n = 1, 8 do
		local ligado
		pcall(function() ligado = tool:GetInput("Enabled" .. n) end)
		local partes = {}
		for _, chave in ipairs(PROPRIEDADES) do
			local a, b
			pcall(function() a = tool:GetInput(chave .. n) end)
			if follower then
				pcall(function() b = follower:GetInput(chave .. n) end)
			end
			if a ~= nil or b ~= nil then
				local txt = chave .. "=" .. mostrar(a)
				-- so mostra o Follower quando ele DISCORDA: repetir o valor
				-- igual em 18 propriedades vira parede de texto
				if b ~= nil and mostrar(b) ~= mostrar(a) then
					txt = txt .. "/fol:" .. mostrar(b)
				end
				partes[#partes + 1] = txt
			end
		end
		log(string.format("  element %d %-17s %s", n,
			"(" .. (NOME_ELEMENTO[n] or "?") .. ")",
			#partes > 0 and table.concat(partes, " ")
			or (ligado == 1 and "(no readable inputs)"
				or "(disabled - inputs not materialised yet)")))
	end
	log("  (a/fol:b means Text+ says a and Follower1 says b - Follower1 wins)")

	-- Os rotulos dos combos, lidos do proprio input.
	--
	-- `ElementShape` e `Level` sao numeros sem significado obvio, e cada
	-- palpite errado sobre eles custou uma rodada: caixa que nao aparece
	-- (forma errada) e caixa em toda letra (level errado). Aqui o Resolve diz
	-- os nomes, e a duvida acaba lendo o log.
	log("")
	log("  combo labels (so these numbers stop being guesswork):")
	for _, chave in ipairs({ "ElementShape4", "Level4" }) do
		local rotulos = {}
		pcall(function()
			local attrs = tool[chave]:GetAttrs()
			-- o Fusion expoe a lista com nomes que variam entre versoes,
			-- entao qualquer chave que traga uma tabela de strings serve
			for k, v in pairs(attrs or {}) do
				if type(v) == "table" then
					for idx, nome in pairs(v) do
						if type(nome) == "string" then
							rotulos[#rotulos + 1] = tostring(idx) .. "=" .. nome
						end
					end
				elseif type(v) == "string" and tostring(k):find("Name") then
					rotulos[#rotulos + 1] = tostring(k) .. ":" .. v
				end
			end
		end)
		table.sort(rotulos)
		log(string.format("    %-15s %s", chave,
			#rotulos > 0 and table.concat(rotulos, "  ")
			or "(no labels exposed by GetAttrs)"))
	end

	-- 2) os controles do Inspector. Se eles discordarem do Text+, qualquer
	-- clique no Inspector desfaz o estilo.
	log("")
	-- A lista vem do proprio macro quando da'. `InputKeys` E' o schema do
	-- estilo: lendo dali, um controle acrescentado ao macro aparece no dump sem
	-- ninguem lembrar de atualizar a lista deste arquivo - que e' exatamente o
	-- tipo de coisa que ninguem lembra.
	local doMacro = dado_do_macro(comp, tool, "InputKeys")
	local lista = CONTROLES
	if type(doMacro) == "table" and #doMacro > 0 then
		lista = {}
		for _, k in ipairs(doMacro) do lista[#lista + 1] = k end
		lista[#lista + 1] = "GiAutoSubsVersao"   -- fora do preset, mas o dump quer
		log(string.format("  macro controls (%d, from the macro's own InputKeys):",
			#lista))
	else
		log("  macro controls (what the Inspector shows):")
	end
	local linha = {}
	for _, nome in ipairs(lista) do
		local v
		pcall(function() v = tool:GetInput(nome) end)
		if v ~= nil then
			linha[#linha + 1] = nome .. "=" .. mostrar(v)
			if #linha == 4 then
				log("    " .. table.concat(linha, "  "))
				linha = {}
			end
		end
	end
	if #linha > 0 then log("    " .. table.concat(linha, "  ")) end

	-- 3) o spline de character-level styling. E' a camada que vence TODAS as
	-- outras, e e' onde estavam os keyframes de exemplo que pintavam o
	-- outline de azul.
	log("")
	local ok = pcall(function()
		local cls = follower.Text:GetConnectedOutput():GetTool()
		local spline = cls.CharacterLevelStyling:GetConnectedOutput():GetTool()
		local kfs = spline:GetKeyFrames()
		local n, amostra = 0, nil
		for chave, kf in pairs(kfs or {}) do
			n = n + 1
			if amostra == nil and type(kf) == "table" and kf.Value
				and type(kf.Value) == "table" and kf.Value.Array then
				amostra = { chave, #kf.Value.Array }
			end
		end
		log(string.format("  character-level styling spline: %d keyframe(s)%s",
			n, amostra and string.format(", first at frame %s with %d entries",
				tostring(amostra[1]), amostra[2]) or ""))
		if n > 0 and not amostra then
			log("    (keyframes present but no StyledText array read back)")
		end
	end)
	if not ok then
		log("  character-level styling spline: could not be read")
	end

	log("---------------------------------------------------------")
	log("")
end

--------------------------------------------------------------------------
-- O macro que esta REALMENTE em uso e' o mesmo que o gerar_macro.py escreveu?
--
-- Quando um titulo Fusion entra no Media Pool, o Resolve guarda uma COPIA dele
-- dentro do projeto. Reinstalar o .setting em Templates/Edit/Titles nao mexe
-- nessa copia: o script continua criando clipes a partir do macro velho, e o
-- sintoma e' "consertei e nao mudou nada".
local function conferir_macro(tool, dados)
	local esperado = dados.macro_versao
	if not esperado then return true end

	local atual
	pcall(function() atual = tool:GetInput("GiAutoSubsVersao") end)
	if atual ~= nil and math.floor(atual + 0.5) >= esperado then
		return true
	end

	log("")
	log("  the macro in the Media Pool is out of date: version "
		.. (atual == nil and "none (old macro)" or mostrar(atual))
		.. ", expected " .. esperado)
	log("  Resolve keeps a COPY of the title inside the project, and")
	log("  reinstalling the .setting does not touch that copy.")
	return false
end


-- Troca o item defasado do Media Pool por um recem-lido do arquivo.
--
-- O caminho e' o mesmo que o Resolve usa quando voce arrasta o titulo de
-- Effects > Titles: `InsertFusionTitleIntoTimeline` le a biblioteca de titulos
-- (o .setting no disco), e o clipe resultante carrega um MediaPoolItem novo.
-- Depois disso o clipe temporario sai da timeline e o item fica no Media Pool.
--
-- Devolve o MediaPoolItem novo, ou nil + o motivo.
-- Poe o template no Media Pool - a unica forma de o `AppendToTimeline` ter o
-- que instanciar.
--
-- NAO existe API de "arrastar um Fusion Title de Effects pro Media Pool".
-- `InsertFusionTitleIntoTimeline` poe o titulo na TIMELINE, e titulo na
-- timeline nao vira item do Media Pool - exatamente como arrastar com o mouse
-- pra timeline tambem nao cria nada la. E' por isso que o AutoSubs distribui um
-- `caption-bin.drb`: um bin exportado, que `ImportFolderFromFile` devolve pro
-- Media Pool ja com o macro dentro.
--
-- Ordem das tentativas, da menos invasiva pra mais:
--   1. importar o .drb ao lado deste script, se existir
--   2. inserir na timeline e ver se o item expoe GetMediaPoolItem (aqui nao
--      expoe, mas outras builds podem)
local function semear_template(mediaPool, timeline, nome, versao, projeto)
	local tentado = {}

	-- 1) bin exportado
	if BIN_DRB and mediaPool.ImportFolderFromFile then
		local fh = io.open(BIN_DRB, "r")
		local vbin = versao_do_bin()
		if not fh then
			tentado[#tentado + 1] = "no bin file at " .. BIN_DRB
		elseif versao and vbin and vbin < versao then
			-- Importar aqui traria de volta um macro velho, e o carimbo pararia
			-- a rodada logo em seguida - com a diferenca de que agora haveria um
			-- item defasado no Media Pool pra alguem apagar depois.
			fh:close()
			tentado[#tentado + 1] = string.format(
				"the .drb holds macro %d, this run needs %d (it will be "
				.. "re-exported once a fresh template is in the pool)", vbin, versao)
		elseif projeto and ja_tentou_importar(projeto, vbin) then
			fh:close()
			tentado[#tentado + 1] =
				"the .drb was already tried once in this project and did not "
				.. "produce '" .. nome .. "' (delete " .. BIN_TENTADO .. " to retry)"
		else
			fh:close()
			if projeto then marcar_tentativa(projeto, vbin) end
			local ok = pcall(function()
				return mediaPool:ImportFolderFromFile(BIN_DRB)
			end)
			if ok then
				local achado = achar_template(mediaPool:GetRootFolder(), nome)
				if achado then
					log("      imported '" .. nome .. "' from " .. BIN_DRB)
					return achado
				end
			end
			tentado[#tentado + 1] = "the .drb import did not produce '" .. nome .. "'"
		end
	else
		tentado[#tentado + 1] = "BIN_DRB not set or ImportFolderFromFile missing"
	end

	-- 2) o truque da timeline
	if timeline.InsertFusionTitleIntoTimeline then
		local novo
		pcall(function()
			local temp = timeline:InsertFusionTitleIntoTimeline(nome)
			if not temp then return end
			if temp.GetMediaPoolItem then novo = temp:GetMediaPoolItem() end
			-- o clipe temporario nao pode ficar: ele entra no playhead, por
			-- cima do que estiver la
			pcall(function() timeline:DeleteClips({ temp }) end)
		end)
		if novo then
			log("      seeded '" .. nome .. "' from Effects > Titles")
			return novo
		end
		tentado[#tentado + 1] =
			"Effects > Titles inserted the title but it carries no MediaPoolItem"
	else
		tentado[#tentado + 1] = "no InsertFusionTitleIntoTimeline in this build"
	end

	return nil, table.concat(tentado, "; ")
end


local function atualizar_template(mediaPool, timeline, nome, versao, projeto)
	-- ORDEM: semeia o novo PRIMEIRO, confere que veio, e so' entao apaga o
	-- velho.
	--
	-- A versao anterior apagava primeiro. Quando o passo de semear falhava - e
	-- ele falha, porque `InsertFusionTitleIntoTimeline` nao cria item no Media
	-- Pool - o usuario ficava sem template nenhum, e o script seguinte parava
	-- com "no template available". Apagar antes de ter o substituto na mao e'
	-- o tipo de erro que so aparece no dia em que o outro passo falha.
	local novo, motivo = semear_template(mediaPool, timeline, nome, versao, projeto)
	if not novo then
		return nil, motivo
	end

	-- Apaga TODAS as copias velhas, nao so' a que `achar_template` devolveu.
	-- Duas rodadas de troca deixavam duas defasadas no pool, e a proxima busca
	-- podia acertar qualquer uma delas.
	limpar_templates_obsoletos(mediaPool, nome, novo)
	return novo
end


--------------------------------------------------------------------------
-- Acha as legendas que JA estao na timeline.
--
-- Serve pro modo "atualizar": em vez de apagar e recriar 129 clipes (o que
-- joga fora qualquer texto corrigido na mao, e qualquer clipe que voce tenha
-- movido ou aparado), a gente reescreve o estilo nos que ja existem.
--
-- Como reconhecer uma legenda NOSSA: o Text+ dela responde a
-- `GiAutoSubsVersao`, o carimbo que o gerar_macro.py grava. Nenhum outro
-- titulo tem esse input, entao nao ha risco de pegar um Text+ qualquer da
-- timeline pela frente.
local function achar_legendas_existentes(timeline)
	local achadas = {}
	if not timeline.GetItemListInTrack then return achadas, "no GetItemListInTrack" end

	local total = timeline:GetTrackCount("video")
	-- de cima pra baixo: legenda quase sempre esta nas tracks de cima
	for track = total, 1, -1 do
		local itens
		pcall(function() itens = timeline:GetItemListInTrack("video", track) end)
		for _, item in ipairs(itens or {}) do
			local ok = pcall(function()
				if (item:GetFusionCompCount() or 0) < 1 then return end
				local comp = item:GetFusionCompByIndex(1)
				local tool = comp and (comp:FindTool("Template")
					or comp:FindToolByID("TextPlus"))
				if not tool then return end
				if tool:GetInput("GiAutoSubsVersao") == nil then return end
				local inicio
				pcall(function() inicio = item:GetStart() end)
				achadas[#achadas + 1] = {
					item = item, track = track, inicio = inicio,
					texto = tool:GetInput("Text"),
				}
			end)
			if not ok then end   -- item estranho na track: ignora e segue
		end
	end

	table.sort(achadas, function(a, b)
		return (a.inicio or 0) < (b.inicio or 0)
	end)
	return achadas
end


--------------------------------------------------------------------------
-- O que fazer com o que ja esta la (CONFLITO, no topo do arquivo).
--
-- Antes isto nao era decisao. A rodada nova entrava numa track acima e a
-- anterior continuava embaixo, viva: era dai que saia "129 legendas achadas
-- contra 128 criadas" - voce editava a de baixo e via a de cima, e a unica
-- pista era a contagem nao bater.
--
-- Devolve (o que fazer, relatorio). Nada e' apagado aqui: quem age e' o main,
-- depois de dizer no log o que vai fazer.
local function conferir_conflitos(timeline)
	local existentes = achar_legendas_existentes(timeline)
	local porTrack, tracks = {}, {}
	local menorTrack
	for _, e in ipairs(existentes) do
		if not porTrack[e.track] then
			porTrack[e.track] = 0
			tracks[#tracks + 1] = e.track
		end
		porTrack[e.track] = porTrack[e.track] + 1
		if not menorTrack or e.track < menorTrack then menorTrack = e.track end
	end
	table.sort(tracks)

	local partes = {}
	for _, t in ipairs(tracks) do
		partes[#partes + 1] = string.format("V%d: %d", t, porTrack[t])
	end
	return {
		existentes = existentes,
		quantas = #existentes,
		tracks = tracks,
		menorTrack = menorTrack,
		resumo = table.concat(partes, ", "),
	}
end


-- Le de volta o que foi escrito, no primeiro clipe.
local function conferir(tool, follower, dados, ordem, offsets, nomesOffset)
	log("      -- verifying on the first clip (reading values back) --")
	local st, v = verificar(tool, "Font", dados.inputs.Font)
	log(string.format("      font        %-8s asked '%s'  got '%s'",
		st, tostring(dados.inputs.Font), tostring(v)))
	st, v = verificar(tool, "Style", dados.inputs.Style)
	log(string.format("      font style  %-8s asked '%s'  got '%s'",
		st, tostring(dados.inputs.Style), tostring(v)))

	for n = 1, 8 do
		local pedido = dados.inputs["Enabled" .. n]
		if pedido ~= nil then
			local s1, v1 = verificar(tool, "Enabled" .. n, pedido)
			local linha = string.format("      el %d %-18s %-8s (%s)",
				n, ordem[n] or "?", s1, mostrar(v1))

			local r = dados.inputs["Red" .. n]
			if r and pedido == 1 then
				local sr, vr = verificar(tool, "Red" .. n, r)
				local _, vg = verificar(tool, "Green" .. n)
				local _, vb = verificar(tool, "Blue" .. n)
				linha = linha .. string.format("  color %s asked(%.2f %.2f %.2f) "
					.. "got(%s %s %s)", sr, r, dados.inputs["Green" .. n] or 0,
					dados.inputs["Blue" .. n] or 0,
					mostrar(vr), mostrar(vg), mostrar(vb))
			end
			if dados.inputs["_borda" .. n] then
				local _, vs = verificar(tool, "ElementShape" .. n)
				linha = linha .. "  shape=" .. mostrar(vs)
			end
			if n == 2 and dados.inputs.Thickness2 then
				local s2 = verificar(tool, "Thickness2", dados.inputs.Thickness2)
				linha = linha .. "  thickness " .. s2
			end
			if offsets[n] then
				linha = linha .. "  offset " ..
					(nomesOffset[n] and ("via " .. nomesOffset[n]) or "NOT ACCEPTED")
			end
			log(linha)

			-- A cor do Follower1 aparece SEPARADA de proposito: ela e' a que
			-- vence na tela. Enquanto so' a do Text+ era mostrada, o log dizia
			-- "black ok" com a legenda azul na frente do usuario.
			if follower and r and pedido == 1 then
				local _, fr = verificar(follower, "Red" .. n)
				local _, fg = verificar(follower, "Green" .. n)
				local _, fb = verificar(follower, "Blue" .. n)
				if fr ~= nil or fg ~= nil or fb ~= nil then
					local igual = (fr == nil or math.abs((fr or 0) - r) < 1e-6)
					log(string.format("           Follower1  %s  (%s %s %s)",
						igual and "ok" or "DIFFERS - this is the one you see",
						mostrar(fr), mostrar(fg), mostrar(fb)))
				end
			end
		end
	end
end


--------------------------------------------------------------------------
-- `jaTentou` marca a segunda passada, depois de o template ter sido trocado.
-- Sem isso, um template que continua defasado depois da troca (o Fusion varre
-- a pasta de Titles no boot, entao um .setting instalado com o Resolve aberto
-- pode nao ser visto) faria o script se rechamar pra sempre.
--
-- `respostas` carrega as tres escolhas entre uma passada e outra: sem isso a
-- segunda passada (template atualizado) abriria os tres dialogos de novo, e a
-- resposta que interessa - a que acabou de ser dada - seria perguntada duas
-- vezes seguidas.
local function main(resolve, jaTentou, respostas)
	respostas = respostas or {}
	local project = resolve:GetProjectManager():GetCurrentProject()
	local mediaPool = project:GetMediaPool()

	-- PERGUNTA 3: qual arquivo com o texto das legendas.
	--
	-- Ultima das tres porque e' a que muda a cada corte: o dialogo abre na
	-- pasta do arquivo da rodada anterior, que quase sempre e' a pasta certa.
	local caminho = respostas.arquivo or ARQUIVO
	if not caminho or caminho == "" then
		local anterior = escolhas_lidas().arquivo
		caminho = perguntar_arquivo(
			"3/3  Pick the legendas.lua with the caption text",
			pasta_de(anterior) or "", "legendas.lua",
			"GiAutoSubs captions (*.lua)|*.lua")
		if caminho then lembrar("arquivo", caminho) end
	end
	if not caminho or caminho == "" then
		log("ERROR: no input file chosen (the dialog was cancelled, or it is not")
		log("available in this host). Set ARQUIVO at the top of:")
		log("  " .. debug.getinfo(1, "S").source:sub(2))
		return
	end
	respostas.arquivo = caminho

	if jaTentou then
		log("")
		log("      -- second pass, with the refreshed template --")
	end

	etapa(1, 6, "reading " .. caminho)
	local dados, err = ler_dados(caminho)
	if not dados then log("ERROR: " .. err); return end
	log(string.format("      %d captions | style '%s'",
		#dados.segments, tostring(dados.estilo)))

	-- Espelha o resumo que o giautosubs.py imprimiu, pra dar pra comparar os
	-- dois lados quando o que aparece na tela nao bate com o pedido.
	log("      style requested:")
	local ordem = NOME_ELEMENTO
	for n = 1, 8 do
		local on = dados.inputs["Enabled" .. n]
		if on ~= nil then
			local extra = ""
			local off = dados.inputs["_offset" .. n]
			if off then extra = string.format("  offset x=%+.4f y=%+.4f", off[1], off[2]) end
			local r = dados.inputs["Red" .. n]
			if r then
				extra = string.format("  rgb(%.2f %.2f %.2f)", r,
					dados.inputs["Green" .. n] or 0,
					dados.inputs["Blue" .. n] or 0) .. extra
			end
			if dados.inputs["_borda" .. n] then extra = extra .. "  [border]" end
			log(string.format("        el %d %-18s %s%s", n, ordem[n] or "?",
				(on == 1) and "ON " or "off", extra))
		end
	end
	local nCamadas = dados.destaque and dados.destaque.camadas
		and #dados.destaque.camadas or 0
	local quais = {}
	for _, c in ipairs((dados.destaque or {}).camadas or {}) do
		quais[#quais + 1] = "el " .. c.elemento
	end
	log(string.format("        highlight: %d animated layer(s)%s", nCamadas,
		nCamadas > 0 and (" -> " .. table.concat(quais, ", ")) or ""))

	etapa(2, 6, "timeline")
	local timeline = project:GetCurrentTimeline()
	if not timeline then log("ERROR: no timeline open."); return end

	local fps = tonumber(timeline:GetSetting("timelineFrameRate"))
	local inicioTimeline = timeline:GetStartFrame()
	local tracksAntes = timeline:GetTrackCount("video")
	log(string.format("      '%s' | %.3f fps | starts at frame %d | %d video tracks",
		tostring(timeline:GetName()), fps, inicioTimeline, tracksAntes))

	-- A pergunta de conflito acontece AQUI, e nao la' no passo 4 onde ela age.
	--
	-- E' por causa da opcao 4 ("use these"): ela nao cria clipe nenhum, entao
	-- nao precisa do template do Media Pool - e o passo 3, que vem antes do 4,
	-- pode reimportar o bin, trocar o item do pool e ate' reiniciar o `main`
	-- inteiro. Perguntar depois disso seria pagar o passo caro pra descobrir que
	-- ele nao era necessario.
	--
	-- `conferir_conflitos` roda de novo no passo 4, e nao e' desperdicio: entre
	-- um ponto e outro o passo 3 pode ter inserido o Title na timeline pra semear
	-- o Media Pool, e esse clipe TAMBEM carrega o carimbo. Aqui a resposta so'
	-- decide o MODO; la' ela decide o que apagar, com a timeline como ela esta'.
	local modo = respostas.modo or MODO
	if modo ~= "atualizar" then
		local conf = conferir_conflitos(timeline)
		if conf.quantas > 0 then
			log(string.format("      %d GiAutoSubs caption(s) from a previous run "
				.. "are here (%s)", conf.quantas, conf.resumo))
			if not respostas.conflitoFeito then
				respostas.conflito = escolher_conflito(conf.quantas, conf.resumo)
				respostas.conflitoFeito = true
			end
			if respostas.conflito == "usar_existentes" then
				modo = "atualizar"
				respostas.manterTempos = true
			end
		end
	end
	respostas.modo = modo
	-- "manter o tempo por palavra" so' vale pra opcao 4. O `MODO = "atualizar"`
	-- classico existe pra ver uma mudanca do estilos.json nas legendas que ja
	-- estao la, e ali re-sincronizar pela transcricao e' o que se quer.
	local manterTempos = respostas.manterTempos or false

	-- O template do Media Pool so' interessa pra CRIAR: o `AppendToTimeline`
	-- exige um MediaPoolItem. No modo "atualizar" as legendas ja existem e o
	-- macro mora dentro de cada uma - procurar o item ali seria exigir do
	-- usuario uma coisa que o script nao vai usar.
	local nomeProjeto = "(project)"
	pcall(function() nomeProjeto = project:GetName() or nomeProjeto end)

	local template, nomeTemplate
	if modo == "atualizar" then
		etapa(3, 6, "template not needed (update mode)")
		log("      the macro lives inside each caption that is already on the")
		log("      timeline - nothing is read from the Media Pool.")
	else
		etapa(3, 6, "template")
		-- Aqui, e nao no topo do arquivo: perguntar antes de saber que ha uma
		-- timeline e um Media Pool seria abrir um dialogo pra depois falhar.
		TEMPLATES = respostas.templates or templates_preferidos()
		respostas.templates = TEMPLATES
		for _, nome in ipairs(TEMPLATES) do
			template = achar_template(mediaPool:GetRootFolder(), nome)
			if template then nomeTemplate = nome break end
		end
		local porque
		if not template then
			log("      not in the Media Pool - trying to seed it")
			template, porque = semear_template(mediaPool, timeline, TEMPLATES[1],
				dados.macro_versao, nomeProjeto)
			if template then nomeTemplate = TEMPLATES[1] end
		end

		if not template then
			log("")
			log("ERROR: the template is not in the Media Pool, and this build")
			log("does not offer a way to put it there from a script.")
			log("  tried: " .. tostring(porque))
			log("")
			log("  Do it once, by hand - it takes ten seconds and it sticks:")
			log("    1. Effects > Titles, find 'GiAutoSubs Caption'")
			log("    2. drag it into the MEDIA POOL (not onto the timeline -")
			log("       dropping a title on the timeline creates nothing here)")
			log("    3. run this script again")
			log("")
			log("  To skip that step on the next project, export it as a bin:")
			log("    right-click the bin holding it > Export Bin File... and")
			log("    save as " .. tostring(BIN_DRB))
			log("    (the script imports that automatically when it exists)")
			return
		end
		log("      using '" .. tostring(template:GetName()) .. "'")
		if nomeTemplate == "AutoSubs Caption" then
			log("      WARNING: that is the AutoSubs template, not ours. Its default")
			log("      font is Arial Rounded MT Bold (missing on this machine) and")
			log("      the Bubble / Box Shadow controls will not exist.")
		elseif nomeTemplate ~= TEMPLATES[1] then
			-- O estilo escolhido esta' instalado em Titles mas ainda nao foi
			-- pro Media Pool deste projeto. Sem este aviso o sintoma seria
			-- "escolhi um estilo e veio outro", sem nada explicando.
			log("      WARNING: '" .. tostring(TEMPLATES[1]) .. "' was chosen, but it")
			log("      is not in this project's Media Pool - fell back to the above.")
			log("      Drag it from Effects > Titles into the Media Pool once.")
		end
	end

	-- A configuracao da rodada, por cima do estilo que veio no legendas.lua.
	--
	-- Depois do template de proposito: a pergunta so' faz sentido se a rodada
	-- chegou ate' aqui, e perguntar antes seria abrir um dialogo pra depois
	-- descobrir que nao ha timeline.
	if not respostas.presetFeito then
		respostas.preset, respostas.rotuloPreset = escolher_preset()
		respostas.presetFeito = true
	end
	local configUsada = "none (the style baked into legendas.lua)"
	-- Nasce no padrao porque a pergunta so' acontece quando ha legenda antiga:
	-- sem nada na timeline, o que vale e' a constante, e o resumo tem que dizer
	-- isso em vez de mentir que alguem escolheu.
	local conflitoUsado = CONFLITO .. " (nothing from a previous run was here)"
	if respostas.preset then
		local n = fundir_preset(dados, respostas.preset)
		configUsada = respostas.rotuloPreset
		log(string.format("      config: %d value(s) from %s", n,
			tostring(respostas.rotuloPreset)))
		log("      they win over the style in legendas.lua; what the config does")
		log("      not mention still comes from the style.")
	end

	-- Track por falante, resolvida UMA vez por falante e memorizada.
	--
	-- Com TRACKS_ACIMA, o `track` do estilos.json e' uma FAIXA de legenda
	-- (1, 2, 3...) contada a partir do topo das tracks existentes - e nao o
	-- numero absoluto da track. Sem isso as legendas caem em cima das tracks
	-- de video do SpeakerSwitch, o Resolve recusa cada insercao e devolve nil
	-- no lugar do clipe.
	--
	-- `trackLivre`, quando existe, e' a track que o modo "substituir" acabou de
	-- esvaziar: reaproveita-la e' o que impede a rodada de subir uma track a
	-- cada execucao ate a timeline virar uma escada.
	local cacheTrack, trackLivre = {}, nil
	local function track_do(id)
		if cacheTrack[id] then return cacheTrack[id] end

		local sp = dados.speakers and dados.speakers[id]
		local faixa = TRACK_UNICA and 1 or ((sp and sp.track) or 1)
		local alvo = TRACKS_ACIMA and (tracksAntes + faixa) or faixa
		if trackLivre then alvo = trackLivre + faixa - 1 end
		-- Laco LIMITADO. `while GetTrackCount() < alvo do AddTrack() end` roda
		-- pra sempre no dia em que o AddTrack falhar (timeline travada, limite
		-- de tracks) - e um script travado nao diz o que houve.
		local tentativas = 0
		while timeline:GetTrackCount("video") < alvo and tentativas < 64 do
			timeline:AddTrack("video")
			tentativas = tentativas + 1
		end
		if timeline:GetTrackCount("video") < alvo then
			log(string.format("      WARNING: could not create video track %d "
				.. "(AddTrack had no effect after %d tries)", alvo, tentativas))
			alvo = timeline:GetTrackCount("video")
		end
		cacheTrack[id] = alvo
		log(string.format("      %-12s -> video track %d%s",
			tostring(sp and sp.nome or "(no speaker)"), alvo,
			TRACKS_ACIMA and string.format(" (lane %d above the existing %d)",
				faixa, tracksAntes) or ""))
		return alvo
	end
	if TRACK_UNICA then
		log("      all captions go on a single track "
			.. "(TRACK_UNICA at the top of this script)")
	end

	local segmentos = dados.segments
	if DIAGNOSTICO then
		log("      DIAGNOSTIC MODE: a single clip, nothing else touched")
		segmentos = { dados.segments[1] }
	end

	-- No modo "atualizar" nada e' criado: as legendas ja estao na timeline e o
	-- que muda e' o estilo delas. Cada clipe e' uma copia INDEPENDENTE do
	-- macro - nao existe um "mestre" pra editar - entao restilizar significa
	-- passar em cada um. A vantagem sobre recriar e' preservar o que voce
	-- ajustou na mao: texto corrigido, clipe movido, clipe aparado.
	local clipes, itens, existentes = {}, nil, nil
	local contornados = {}
	local pares, semPar = nil, {}
	if modo == "atualizar" then
		etapa(4, 6, "finding the captions already on the timeline")
		existentes = achar_legendas_existentes(timeline)
		log(string.format("      %d GiAutoSubs captions found", #existentes))
		if #existentes == 0 then
			log("ERROR: no GiAutoSubs caption found on this timeline.")
			log("      Set MODO = \"criar\" at the top of this script to create them.")
			return
		end

		-- Pareamento por FRAME DE INICIO, nao por ordem.
		--
		-- Por ordem (o que existia aqui) a primeira casava com a primeira, a
		-- segunda com a segunda, e pronto. Bastava a contagem divergir - e ela
		-- diverge assim que uma legenda e' repartida em duas - pra tudo depois
		-- daquele ponto casar com o vizinho: texto de uma legenda no clipe da
		-- outra, calado. O aviso existia, mas avisar nao e' parear.
		--
		-- Por frame cada clipe procura o segmento que comeca onde ele comeca. O
		-- que nao achar par fica de fora, dos DOIS lados, e o log diz quais.
		local TOLERANCIA = math.max(2, math.floor(fps / 4))   -- ~250 ms
		local usados = {}
		pares = {}
		for _, e in ipairs(existentes) do
			local alvo = (e.inicio or 0) - inicioTimeline
			local melhor, dist
			for k, seg in ipairs(segmentos) do
				if not usados[k] then
					local d = math.abs(segundos_para_frames(seg.start, fps) - alvo)
					if not dist or d < dist then melhor, dist = k, d end
				end
			end
			if melhor and dist <= TOLERANCIA then
				usados[melhor] = true
				pares[#pares + 1] = { item = e.item, i = melhor, texto = e.texto }
			else
				pares[#pares + 1] = { item = e.item, i = nil, texto = e.texto }
			end
		end
		for k, seg in ipairs(segmentos) do
			if not usados[k] then semPar[#semPar + 1] = { i = k, seg = seg } end
		end

		local casados = 0
		for _, p in ipairs(pares) do if p.i then casados = casados + 1 end end
		log(string.format("      %d of %d matched to the transcript by start "
			.. "frame (within %d frames)", casados, #existentes, TOLERANCIA))
		if casados < #existentes then
			log(string.format("      %d caption(s) on the timeline had no match "
				.. "and are left untouched", #existentes - casados))
		end
		if #semPar > 0 then
			log(string.format("      %d caption(s) in legendas.lua have no clip "
				.. "here and were NOT created (this mode creates nothing):",
				#semPar))
			for _, s in ipairs(semPar) do
				log(string.format("        %8.2fs  %s", s.seg.start,
					(s.seg.text or ""):gsub("\n", " / ")))
			end
			log("      Run again choosing REPLACE if you want them.")
		end
		if manterTempos then
			log("      per-word timing is kept as it is in each clip - the bubble")
			log("      stays exactly as synced as it is now.")
		end
		etapa(5, 6, "no clip created (restyling what is already here)")
	else
		-- CONFLITO: o que fazer com a rodada anterior, dito antes de criar
		-- qualquer coisa. Ver o topo do arquivo.
		local conf = conferir_conflitos(timeline)
		local ocupados = {}
		local conflito = CONFLITO
		if conf.quantas > 0 then
			log(string.format("      %d GiAutoSubs caption(s) already on this "
				.. "timeline (%s)", conf.quantas, conf.resumo))

			-- A resposta viaja no `respostas` como as outras tres: o `main`
			-- roda DUAS vezes quando o template precisa ser atualizado, e sem
			-- isto a segunda passada reabriria o dialogo - agora com as
			-- legendas que a primeira acabou de criar na conta.
			if not respostas.conflitoFeito then
				respostas.conflito = escolher_conflito(conf.quantas, conf.resumo)
				respostas.conflitoFeito = true
			end
			conflito = respostas.conflito or CONFLITO
			conflitoUsado = conflito .. (respostas.conflito and " (you chose it)"
				or " (default - the dialog was cancelled or unavailable)")

			if conflito == "substituir" then
				local alvos = {}
				for _, e in ipairs(conf.existentes) do alvos[#alvos + 1] = e.item end
				local ok = pcall(function() timeline:DeleteClips(alvos) end)
				if ok then
					log(string.format("      CONFLITO = substituir: %d removed. "
						.. "Only clips carrying the GiAutoSubs stamp were touched.",
						#alvos))
					-- A track deles ficou vazia; usar ela evita a escada.
					if conf.menorTrack and conf.menorTrack <= tracksAntes then
						trackLivre = conf.menorTrack
					end
				else
					log("      WARNING: DeleteClips refused - the old captions are")
					log("      still there and this run will stack on top of them.")
				end
			elseif conflito == "contornar" then
				for _, e in ipairs(conf.existentes) do
					if e.inicio then ocupados[#ocupados + 1] = e.inicio end
				end
				log(string.format("      CONFLITO = contornar: keeping them, and "
					.. "skipping any caption that starts on an occupied frame"))
			else
				log("      CONFLITO = track_nova: leaving them alone and stacking "
					.. "this run above")
				log("      (this is how the same captions end up counted twice - "
					.. "you edit the one below and see the one on top)")
			end
		end

		etapa(4, 6, "tracks per speaker")
		for i, seg in ipairs(segmentos) do
			local f0 = segundos_para_frames(seg.start, fps)
			local f1 = segundos_para_frames(seg["end"], fps)

			-- "contornar": o frame de entrada e' a identidade da legenda aqui -
			-- a mesma transcricao sempre poe a mesma legenda no mesmo lugar.
			local livre = true
			for _, inicio in ipairs(ocupados) do
				if inicio == inicioTimeline + f0 then livre = false break end
			end

			if livre then
				-- O indice do SEGMENTO viaja junto. `clipes` deixou de ser uma
				-- copia 1-pra-1 de `segmentos` no dia em que "contornar" passou a
				-- pular alguns, e todo o resto do arquivo indexa `segmentos[i]` -
				-- sem isto, pular uma legenda faria as seguintes receberem o texto
				-- da vizinha, calado.
				clipes[#clipes + 1] = {
					seg = i,
					mediaPoolItem = template,
					mediaType = 1,
					startFrame = 0,
					endFrame = math.max(1, f1 - f0),
					recordFrame = inicioTimeline + f0,
					trackIndex = track_do(seg.speaker_id),
				}
			else
				contornados[#contornados + 1] = i
			end
		end
		if #contornados > 0 then
			log(string.format("      CONFLITO = contornar: %d caption(s) already "
				.. "exist at that frame and were left as they are", #contornados))
		end

		-- `seg` nao e' campo do AppendToTimeline; ele so' viaja aqui dentro. Se
		-- sobrar na tabela o Resolve ignora, mas mandar lixo pra API e' como se
		-- descobre, meses depois, que ela nao ignorava tanto assim.
		local pedido = {}
		for k, c in ipairs(clipes) do
			pedido[k] = { mediaPoolItem = c.mediaPoolItem, mediaType = c.mediaType,
				startFrame = c.startFrame, endFrame = c.endFrame,
				recordFrame = c.recordFrame, trackIndex = c.trackIndex }
		end

		etapa(5, 6, string.format("creating %d clips", #pedido))
		itens = mediaPool:AppendToTimeline(pedido)
		if not itens then
			log("ERROR: AppendToTimeline returned nothing.")
			return
		end
	end

	etapa(6, 6, "applying style")

	-- Contadores por INDICE de legenda, nao somas. Um clipe pode ser tentado
	-- duas vezes (repescagem), e soma contaria a mesma legenda de novo.
	local falhas, comDestaque, semWords = {}, {}, {}
	local splineLimpo, recusados, bolhaDesligada = {}, {}, {}
	local textoMudou = {}
	-- legendas cujo tempo por palavra foi refeito porque o texto no clipe ganhou
	-- ou perdeu palavra (so' no modo "use these")
	local reajustados = {}
	local nomesOffset, viaTexto, viaPreset = {}, "?", "?"

	-- `esperar` aqui e' laco quente de CPU (nao existe `bmd.wait` no host de
	-- Scripts). Na primeira passada nao vale a pena esperar clipe nenhum: o
	-- tempo gasto estilizando os outros ja da' ao Resolve o que ele precisa, e
	-- quem nao estiver pronto volta na repescagem. Na segunda, ai sim espera.
	local function comp_do(item, insistir)
		for tentativa = 1, (insistir and 30 or 1) do
			if (item:GetFusionCompCount() or 0) >= 1 then
				local c = item:GetFusionCompByIndex(1)
				if c then return c end
			end
			if insistir then esperar(0.1) end
		end
		return nil
	end

	-- `ipairs` NAO serve aqui: ele para no primeiro nil, e o AppendToTimeline
	-- devolve nil no lugar de cada clipe que o Resolve se recusou a criar
	-- (track ocupada, sobreposicao). Com um buraco no indice 10, `ipairs`
	-- entregava 9 tarefas e as outras 120 legendas sumiam sem uma linha de
	-- log - era esse, de verdade, o "129 created, 9 styled".
	local tarefas = {}
	if modo == "atualizar" then
		-- os pares vieram do casamento por frame de inicio, la' em cima. Clipe
		-- sem par nao vira tarefa: sem segmento nao ha estilo pra escrever, e
		-- inventar um vizinho e' o defeito que o pareamento por ordem tinha.
		for _, p in ipairs(pares) do
			if p.i then
				tarefas[#tarefas + 1] = { i = p.i, item = p.item,
					texto_atual = p.texto }
			end
		end
	else
		for k = 1, #clipes do
			if itens[k] ~= nil then
				tarefas[#tarefas + 1] = { i = clipes[k].seg, item = itens[k] }
			else
				recusados[#recusados + 1] = clipes[k].seg
			end
		end
		log(string.format("      %d clips created, %d refused by Resolve",
			#tarefas, #recusados))
		if #recusados > 0 then
			log("      Resolve refuses a clip when the track is already busy at")
			log("      that point. Check TRACKS_ACIMA at the top of this script and")
			log("      the 'track' values in estilos.json.")
		end
	end
	if #tarefas == 0 then
		log("      nothing left to do - no clip was created"
			.. (#contornados > 0
				and " (CONFLITO = contornar found every caption already there)"
				or ""))
		return
	end

	-- Antes de estilizar qualquer coisa: o macro em uso e' o novo?
	do
		local c = comp_do(tarefas[1].item, true)
		local t = c and (c:FindTool("Template") or c:FindToolByID("TextPlus"))
		if t and not conferir_macro(t, dados) then
			-- No modo "atualizar" as legendas sao do usuario, nao nossas:
			-- apaga-las aqui seria destruir trabalho por causa de um carimbo.
			-- E trocar o template do Media Pool tambem nao ajudaria - os clipes
			-- que ja existem carregam a copia velha DENTRO deles.
			if modo == "atualizar" then
				log("      the captions on the timeline came from an older macro.")
				log("      Update mode only restyles what is there; it cannot")
				log("      replace the macro inside an existing clip.")
				log("      Run once with MODO = \"criar\" to rebuild them.")
				return
			end
			pcall(function() timeline:DeleteClips(itens) end)
			log("      (the clips just created were removed)")

			if not AUTO_ATUALIZAR_TEMPLATE then
				log("      AUTO_ATUALIZAR_TEMPLATE is off - swap it by hand:")
				log("        delete '" .. nomeTemplate .. "' from the Media Pool,")
				log("        then drag it in again from Effects > Titles.")
				return
			end
			if jaTentou then
				log("")
				log("  STOPPING: the template was refreshed and is STILL out of")
				log("  date. That means Effects > Titles is serving an old file:")
				log("  Fusion scans the Titles folder when Resolve starts.")
				log("    1. Quit Resolve")
				log("    2. Run: python gerar_macro.py --instalar")
				log("    3. Reopen Resolve and run this script")
				return
			end

			log("      refreshing the template from Effects > Titles...")
			local novo, motivo = atualizar_template(mediaPool, timeline,
				nomeTemplate, dados.macro_versao, nomeProjeto)
			if not novo then
				log("      could not refresh it automatically: " .. motivo)
				log("      do it by hand: delete '" .. nomeTemplate .. "' from")
				log("      the Media Pool, then drag it in from Effects > Titles.")
				return
			end
			-- de novo, do zero: os clipes precisam nascer do item novo
			log("      starting over with the refreshed template")
			return main(resolve, true, respostas)
		end

		-- O carimbo bateu: o item do Media Pool E' o macro desta rodada. So'
		-- agora da' pra exportar o bin com seguranca - exportar antes da
		-- conferencia congelaria um macro velho num arquivo que os proximos
		-- projetos importariam de olhos fechados.
		--
		-- E' isto que faz o "arraste o titulo pro Media Pool" ser um passo de
		-- uma vez na vida, em vez de um por projeto.
		if modo ~= "atualizar" and nomeTemplate == TEMPLATES[1] then
			pcall(exportar_bin, mediaPool, nomeTemplate, dados.macro_versao)
		end
	end

	-- O trabalho de UM clipe. Sai como funcao porque ele pode ser tentado duas
	-- vezes (ver a fila logo abaixo).
	local function estilizar(i, item, insistir, texto_atual)
		local seg = segmentos[i]
		local comp = comp_do(item, insistir)
		if not comp then
			error("clip has no Fusion composition yet")
		end
		local tool = comp:FindTool("Template") or comp:FindToolByID("TextPlus")
		if not tool then error("Text+ not found in the composition") end
		local follower = comp:FindTool("Follower1")

		-- ORDEM. Nada aqui e' estetico:
		--   1) TEXTO primeiro - o macro reage ao input "Text" (ver o topo).
		--   2) fonte antes dos elementos - a fonte do AutoSubs nao existe aqui
		--      e cada input mexido com ela valendo dispara um render que falha.
		--   3) Enabled antes dos atributos - o Text+ so MATERIALIZA os inputs
		--      de um elemento depois que ele e' habilitado; antes disso o
		--      SetInput e' aceito e descartado, em silencio.
		--   4) ElementShape antes da geometria - Level/Extend/Round so valem
		--      pra forma de borda.
		--   5) o spline por ultimo - ele vence todo o resto.

		-- 1) texto.
		--
		-- No modo "atualizar" com ATUALIZAR_TEXTO = false o texto NAO e'
		-- tocado: quem corrigiu uma legenda na mao nao quer isso desfeito a
		-- cada mudanca de estilo.
		local mexerNoTexto = (modo ~= "atualizar") or ATUALIZAR_TEXTO
		local textoNaTela = mexerNoTexto and seg.text or texto_atual

		-- No macro animado o StyledText do Text+ vem CONECTADO ao Follower1:
		-- escrever nele arrebenta a cadeia. O input certo e' "Text", e o
		-- CharacterLevelStyling precisa ser sincronizado junto.
		if mexerNoTexto then
			if follower then
				tool:SetInput("Text", seg.text)
				local cls = comp:FindTool("CharacterLevelStyling1")
				if cls then pcall(function() cls:SetInput("Text", seg.text) end) end
				viaTexto = "Text (animated macro)"
			else
				tool:SetInput("StyledText", seg.text)
				viaTexto = "StyledText (plain Text+)"
			end
		else
			viaTexto = "left as it is (update mode, ATUALIZAR_TEXTO = false)"
		end

		-- 1b) o texto do clipe ganhou ou perdeu PALAVRA desde que o destaque foi
		-- montado ("i love potato" -> "i love the potato"): refaz o tempo por
		-- palavra a partir do texto que esta no clipe. Ver `refazer_tempos`.
		--
		-- AQUI, e nao no passo 8: neste modo quem reconstroi o array e' o macro,
		-- chamado no passo 5 pelo `aplicar_preset`. Consertar o `GiWordTiming`
		-- depois disso deixaria o array com o errado ate' o proximo Apply Style.
		--
		-- So' no `manterTempos` (a opcao "use these"): o `atualizar` classico
		-- re-sincroniza pela transcricao e ja tem regra propria pra texto
		-- editado - ele DESLIGA o destaque, logo abaixo. Sao duas respostas pra
		-- mesma pergunta, e cada modo tem a sua.
		if manterTempos then
			local atuais
			pcall(function() atuais = tool:GetData("GiWordTiming") end)
			local novos, quantas = refazer_tempos(textoNaTela, atuais)
			if novos and pcall(function()
					tool:SetData("GiWordTiming", novos) end) then
				reajustados[i] = { de = #atuais, para = quantas }
			end
		end

		-- 2) fonte
		pcall(function() tool:SetInput("Font", dados.inputs.Font) end)
		pcall(function() tool:SetInput("Style", dados.inputs.Style) end)

		-- Tem tempo por palavra nesta legenda? A resposta muda o que fica
		-- LIGADO, entao precisa vir antes dos Enabled.
		local tempos = dados.destaque and tempos_das_palavras(seg, fps)
		if dados.destaque and not tempos then semWords[i] = true end

		-- O destaque acende por INDICE DE CARACTERE dentro da frase. Se o texto
		-- na tela nao e' mais o da transcricao (alguem corrigiu no Inspector),
		-- esses indices apontam pra letra errada e a bolha acende no lugar
		-- errado o video inteiro. Nesse caso e' melhor nao animar do que animar
		-- errado - e dizer por que.
		if tempos and textoNaTela ~= nil and textoNaTela ~= seg.text then
			tempos = nil
			textoMudou[i] = true
		end

		-- 3) habilita todo mundo antes de escrever atributo em alguem.
		--
		-- Menos as camadas que existem SO pra marcar a palavra falada
		-- (`on_base == 0`: a bolha e a sombra dela). Sem tempo por palavra nao
		-- ha palavra falada pra marcar, e o Text+ desenha a caixa em cada
		-- palavra - ou em cada letra, conforme o Level. Uma legenda inteira
		-- coberta de caixinhas e' pior que legenda sem caixa nenhuma.
		local so_no_destaque = {}
		for _, c in ipairs((dados.destaque or {}).camadas or {}) do
			if c.on_base == 0 then so_no_destaque[c.elemento] = true end
		end

		for n = 1, 8 do
			local on = dados.inputs["Enabled" .. n]
			if on ~= nil then
				if so_no_destaque[n] and not tempos then on = 0 end
				pcall(function() tool:SetInput("Enabled" .. n, on) end)
				if follower then
					pcall(function() follower:SetInput("Enabled" .. n, on) end)
				end
				if on == 0 and dados.inputs["Enabled" .. n] == 1 then
					bolhaDesligada[i] = true
				end
			end
		end

		-- 4) forma dos elementos de caixa: borda PREENCHIDA.
		-- Tambem no Follower1 - o elemento 4 dele vem com 2 e o 5 com 0, e e'
		-- o Follower que vence na tela.
		for chave in pairs(dados.inputs) do
			local n = chave:match("^_borda(%d+)$")
			if n then
				pcall(function() tool:SetInput("ElementShape" .. n, FORMA.BORDA) end)
				if follower then
					pcall(function()
						follower:SetInput("ElementShape" .. n, FORMA.BORDA)
					end)
				end
			end
		end

		-- 5) o resto do estilo. As chaves "_..." nao sao inputs: sao recados.
		local offsets = {}
		for chave, valor in pairs(dados.inputs) do
			local n = chave:match("^_offset(%d+)$")
			if n then
				offsets[tonumber(n)] = valor
			elseif chave:sub(1, 1) ~= "_" and chave ~= "Font"
				and chave ~= "Style" and not chave:match("^Enabled%d$") then
				pcall(function() tool:SetInput(chave, valor) end)
				local base = chave:match("^(%a+)[1-8]$")
				if follower and base and CHAVES_DO_FOLLOWER[base] then
					pcall(function() follower:SetInput(chave, valor) end)
				end
			end
		end

		-- 5b) o preset, pelo contrato do macro.
		--
		-- Isto e' o que faz o painel contar a mesma historia que a tela: sem os
		-- controles em dia, um clique em qualquer um deles repinta tudo com o
		-- estilo de exemplo do AutoSubs.
		--
		-- Numa legenda sem tempo por palavra a bolha tem que nascer DESLIGADA -
		-- sem palavra falada pra marcar, o Text+ desenha uma caixa em cada
		-- palavra. Antes bastava nao escrever `Enabled4`; agora quem escreve o
		-- estilo e' o macro, a partir dos controles, entao o desligamento
		-- precisa estar no PRESET. (De quebra, o Inspector passa a dizer a
		-- verdade sobre essa legenda em vez de mostrar uma bolha ligada que nao
		-- aparece.)
		local preset = dados.controles
		if not tempos and next(so_no_destaque) then
			preset = {}
			for k, v in pairs(dados.controles or {}) do preset[k] = v end
			for el in pairs(so_no_destaque) do
				local chave = CHAVE_LIGA_ELEMENTO[el]
				if chave then preset[chave] = 0 end
			end
		end
		-- `manterTempos` (a opcao 4 do conflito) inverte quem refaz o array.
		--
		-- No caminho normal o script escreve o array ele mesmo, no passo 8, e
		-- manda o macro PULAR (`spline = false`) - refazer duas vezes seria a
		-- metade cara, 175 vezes a' toa. Aqui o passo 8 nao escreve nada, porque
		-- o tempo por palavra do clipe e' pra ser preservado; entao quem refaz o
		-- array e' o macro, a partir do `GiWordTiming` que JA ESTA no clipe.
		--
		-- E' a diferenca entre "nao mexer no tempo" e "nao mexer no array": o
		-- tempo e' o que sincroniza a bolha, e ele fica intacto; o array e' onde
		-- mora a COR, e sem refaze-lo uma mudanca de aparencia nao chegaria na
		-- tela - voce teria que clicar Apply Style clipe a clipe.
		viaPreset = aplicar_preset(comp, tool, preset, manterTempos)

		-- 6) direcao das sombras / do outline
		for n, xy in pairs(offsets) do
			local usado = aplicar_offset(tool, n, xy, i == tarefas[1].i)
			-- `false` e nao nil: com nil a chave nem existe, e o `pairs` do
			-- resumo passava batido.
			if i == tarefas[1].i then nomesOffset[n] = usado or false end
		end

		-- 7) (vago) - aqui morava a COR DO FALANTE, tirada no macro 22.
		--
		-- Ela escrevia Red1/Green1/Blue1 por clipe e reescrevia o `cor_base` da
		-- camada do elemento 1 no array de keyframes. O efeito colateral era
		-- inteiro: o controle `Fill Color` do Inspector ficava parado no valor do
		-- estilo enquanto a tela mostrava outra coisa em cada legenda, e mudar o
		-- controle nao mudava um pixel - estilo por caractere vence os inputs, e
		-- o array trazia a cor gravada na criacao. Quem manda no elemento 1 agora
		-- e' o Inspector, como em todo o resto.
		--
		-- O falante continua decidindo TRACK (ver `track_do`).

		-- 8) o spline e' escrito SEMPRE - com as palavras, ou vazio. Ver
		-- keyframes_vazios: nao escrever deixava de pe os keyframes de exemplo
		-- do macro, que pintam o outline de azul caractere a caractere.
		-- `comArray` em vez de reusar `tempos`: com o preset podendo APAGAR a
		-- ultima camada (ver `fundir_preset`), "tem tempo por palavra" deixou de
		-- querer dizer "tem destaque". Sem isto, um estilo sem camada nenhuma
		-- cairia no `montar_keyframes` com `destaque` nil e quebraria ali - e o
		-- que ele devolve quando nao ha camada e' `{}`, um spline VAZIO, que e' o
		-- `cannot get Parameter` da secao 5 do ESTADO.md.
		--
		-- Com `manterTempos` o passo 8 inteiro nao acontece: nem o array, nem o
		-- `GiWordTiming`, nem o `GiCamadas`. Escrever qualquer um dos tres
		-- re-sincronizaria a bolha pela transcricao, que e' exatamente o que
		-- este modo promete NAO fazer - o clipe pode ter sido movido ou aparado,
		-- e o tempo que vale e' o dele.
		local kf, comArray = keyframes_vazios(), false
		local destaque = dados.destaque
		if not manterTempos and tempos and destaque
				and #(destaque.camadas or {}) > 0 then
			kf = montar_keyframes(tempos, destaque, fps)
			comArray = true
		end

		-- Guarda o tempo por palavra DENTRO do clipe.
		--
		-- Sem isso o macro nao tem como refazer o array quando voce mexe numa
		-- cor no Inspector - e num elemento animado a cor mora no array, nao
		-- no input. E' o mesmo motivo de o AutoSubs guardar `WordTiming` no
		-- CustomData: o Inspector precisa funcionar sem o script por perto.
		if not manterTempos then
			pcall(function()
				tool:SetData("GiWordTiming", tempos or {})
				tool:SetData("GiCamadas", tempos
					and camadas_para_dados((destaque or {}).camadas) or {})
			end)
		end

		if follower and not manterTempos then
			local cls = follower.Text:GetConnectedOutput():GetTool()
			local spline = cls.CharacterLevelStyling:GetConnectedOutput():GetTool()
			spline:SetKeyFrames(kf, true)
			if comArray then comDestaque[i] = true else splineLimpo[i] = true end
		end

		-- 8b) o "pop" da bolha (ela entra menor e cresce, a cada palavra).
		--
		-- Aqui e nao antes: a rotina le o `GiWordTiming` que acabou de ser
		-- gravado no clipe. E por isso ela e' separada do estilo - o
		-- ApplyGiStyle roda antes de o clipe saber os tempos.
		do
			local f = rotina_do_macro(comp, tool, "GiBubblePop")
			if f then
				local ok, r = pcall(function() return loadstring(f)()(comp, tool) end)
				if ok and i == tarefas[1].i then
					log("      bubble pop: " .. tostring(r))
				end
			end
		end

		-- 9) prova de que entrou. So no primeiro clipe: o que vale e' saber se
		-- o Text+ ACEITOU cada coisa, e isso e' igual nas 129.
		if i == tarefas[1].i then
			conferir(tool, follower, dados, ordem, offsets, nomesOffset)
			if DEBUG_PROPRIEDADES or DIAGNOSTICO then
				dump_propriedades(comp, tool, follower, dados)
			end
		end

		item:SetClipColor("Green")
	end

	-- Fila com repescagem. Um clipe que chega antes de a comp existir volta
	-- pro fim da fila em vez de ser perdido.
	local repescagem, feitos = {}, 0
	local passadas = { tarefas, repescagem }

	for passo = 1, 2 do
		if passo == 2 and #repescagem > 0 then
			log(string.format("      retrying %d clip(s) whose composition was "
				.. "not ready yet", #repescagem))
			esperar(1)
		end
		for k, tarefa in ipairs(passadas[passo]) do
			if passo == 1 and k % 25 == 0 then
				log(string.format("      %d/%d", k, #tarefas))
			end
			local ok, e = pcall(estilizar, tarefa.i, tarefa.item, passo == 2,
				tarefa.texto_atual)
			if ok then
				feitos = feitos + 1
			elseif passo == 1 and tostring(e):find("Fusion composition") then
				repescagem[#repescagem + 1] = tarefa
			else
				falhas[tarefa.i] = tostring(e)
			end
		end
	end

	--------------------------------------------------------------- resumo
	local function contar(t)
		local n = 0
		for _ in pairs(t) do n = n + 1 end
		return n
	end

	log("")
	log("== summary ==")
	log(string.format("  mode              %s", modo
		.. (manterTempos and " (restyling what was already here)" or "")))
	if modo ~= "atualizar" then
		log(string.format("  conflict mode     %s", conflitoUsado))
		if #contornados > 0 then
			log(string.format("  SKIPPED           %d captions already existed at "
				.. "that frame and were kept", #contornados))
		end
	end
	if template then
		log(string.format("  template          %s", tostring(template:GetName())))
	end
	log(string.format("  caption file      %s", tostring(caminho)))
	log(string.format("  config            %s", tostring(configUsada)))
	if modo == "atualizar" then
		log(string.format("  captions          %d on the timeline, %d matched, "
			.. "%d restyled, %d failed", #existentes, #tarefas, feitos,
			contar(falhas)))
		if #semPar > 0 then
			log(string.format("  NOT CREATED       %d caption(s) in legendas.lua "
				.. "had no clip here (listed above)", #semPar))
		end
		local nReaj = contar(reajustados)
		if nReaj > 0 then
			log(string.format("  RE-TIMED          %d caption(s) had words added "
				.. "or removed by hand; the per-word timing was rebuilt from the "
				.. "text in the clip", nReaj))
			log("                    (the new words' timing is ESTIMATED - spread "
				.. "over the span the caption already used)")
		end
	else
		log(string.format("  clips             %d requested, %d created, %d styled, "
			.. "%d failed", #clipes, #tarefas, feitos, contar(falhas)))
	end
	if contar(textoMudou) > 0 then
		log(string.format("  EDITED TEXT       %d captions no longer match the "
			.. "transcript,", contar(textoMudou)))
		log("                    so the word highlight was left off on them: the")
		log("                    timings point at character positions that moved.")
		log("                    Set ATUALIZAR_TEXTO = true to resync the text")
		log("                    (this discards those manual edits).")
	end
	log(string.format("  text applied      via %s", viaTexto))
	log(string.format("  style applied     via %s", viaPreset))
	log(string.format("  word highlight    %d clips with per-word keyframes",
		contar(comDestaque)))
	log(string.format("  spline cleared    %d clips (removes the macro's sample "
		.. "keyframes)", contar(splineLimpo)))
	if contar(bolhaDesligada) > 0 then
		log(string.format("  bubble skipped    %d clips - the bubble marks the "
			.. "spoken word,", contar(bolhaDesligada)))
		log("                    and without word timings there is no spoken")
		log("                    word to mark. Drawing it on every word (or")
		log("                    every letter) would be worse than nothing.")
	end

	if #recusados > 0 then
		local amostra = {}
		for k = 1, math.min(8, #recusados) do amostra[k] = recusados[k] end
		log(string.format("  REFUSED           %d clips Resolve would not create "
			.. "(captions %s%s)", #recusados, table.concat(amostra, ", "),
			#recusados > 8 and ", ..." or ""))
		log("                    the track was already busy at that point")
	end

	-- As falhas agrupadas por MOTIVO. Antes so' a primeira era logada, e com
	-- 120 clipes falhando do mesmo jeito isso parecia um caso isolado.
	local motivos, ordemMotivos = {}, {}
	for _, msg in pairs(falhas) do
		if not motivos[msg] then
			motivos[msg] = 0
			ordemMotivos[#ordemMotivos + 1] = msg
		end
		motivos[msg] = motivos[msg] + 1
	end
	for _, msg in ipairs(ordemMotivos) do
		log(string.format("  FAILED (%dx)      %s", motivos[msg], msg))
	end

	local n_sw = contar(semWords)
	if n_sw > 0 then
		log(string.format("  NO HIGHLIGHT      %d of %d captions have no 'words'",
			n_sw, #tarefas))
		log("                    the current transcript only has the start and")
		log("                    end of each sentence - the highlight needs to")
		log("                    know when each WORD is spoken. Run:")
		log("                      4_transcribe_whisper.py <audio.wav> --words"
			.. " --out turnsWhisper_words.json")
		log("                      giautosubs.py <folder> --transcript"
			.. " turnsWhisper_words.json")
	end

	local semOffset = {}
	for n, v in pairs(nomesOffset) do
		if not v then semOffset[#semOffset + 1] = tostring(n) end
	end
	if #semOffset > 0 then
		log("  NO OFFSET         elements with no accepted input: "
			.. table.concat(semOffset, ", "))
	end
end

-- Sem Resolve por perto o arquivo vira modulo em vez de estourar. Serve pra
-- rodar os testes com o fuscript, e evita um traceback feio pra quem abrir
-- isto no lugar errado.
print("[GiAutoSubs] starting...")

-- Como chegar no Resolve depende de ONDE o script roda. Em Scripts/Utility o
-- normal e' a funcao global `Resolve()`, mas o host as vezes ja entrega o
-- objeto pronto em `resolve`, ou so expoe `bmd.scriptapp`.
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
			print("[GiAutoSubs] Resolve obtained via " .. t[1])
			return r
		end
	end
	return nil
end

local app = obter_resolve()
if not app then
	print("[GiAutoSubs] Resolve NOT found. Globals available here:")
	local vistos = {}
	for _, nome in ipairs({ "Resolve", "resolve", "fusion", "fu", "bmd", "app",
		"composition", "comp", "PROJECT_NAME" }) do
		if _G[nome] ~= nil then vistos[#vistos + 1] = nome .. "=" .. type(_G[nome]) end
	end
	print("[GiAutoSubs]   " .. (#vistos > 0 and table.concat(vistos, "  ") or "(none)"))
	print("[GiAutoSubs] continuing in module mode (expected outside Resolve).")
	return {
		tempos_das_palavras = tempos_das_palavras,
		fatiar_texto = fatiar_texto,
		refazer_tempos = refazer_tempos,
		montar_keyframes = montar_keyframes,
		keyframes_vazios = keyframes_vazios,
		ler_dados = ler_dados,
		segundos_para_frames = segundos_para_frames,
		descobrir_forma_borda = descobrir_forma_borda,
		-- `main` sai daqui pro testes.lua poder rodar a coisa inteira contra
		-- um Resolve de mentira. Sem isso, um erro de digitacao no laco
		-- principal so aparecia dentro do Resolve - que e' a rodada cara.
		main = main,
		ler_preset = ler_preset,
		fundir_preset = fundir_preset,
		definir_arquivo = function(caminho) ARQUIVO = caminho end,
		-- Mesmo motivo do `definir_bin` abaixo: uma rodada de teste nao pode
		-- escolher o preset da rodada de verdade nem carimbar o `_giescolhas`
		-- que guarda onde os dialogos abrem.
		definir_preset = function(caminho) PRESET_FIXO = caminho or "" end,
		definir_escolhas = function(caminho) ESCOLHAS = caminho end,
		definir_modo = function(m, texto)
			MODO, ATUALIZAR_TEXTO = m, texto
		end,
		definir_conflito = function(c) CONFLITO = c end,
		-- Os testes precisam apontar o bin pra um caminho descartavel. Sem isso
		-- uma rodada de teste escreveria o carimbo `.versao` ao lado do bin de
		-- verdade, e o run seguinte acharia que um `.drb` inexistente estava em
		-- dia - um teste que estraga o estado do projeto e' pior que nenhum.
		definir_bin = function(caminho)
			local antes = BIN_DRB
			BIN_DRB = caminho
			BIN_VERSAO = caminho .. ".versao"
			BIN_TENTADO = caminho .. ".tentado"
			return antes            -- pra quem chamou conseguir desfazer
		end,
	}
end

-- pcall pra que um erro apareca no Console em vez de sumir: o Resolve engole
-- excecao de script e o sintoma vira "rodei e nao aconteceu nada"
local ok, err = pcall(main, app)
if not ok then
	log("ERROR: " .. tostring(err))
end
print("[GiAutoSubs] done.")
