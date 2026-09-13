-- Lancador do GiAutoSubs.
-- O codigo de verdade mora no projeto; aqui so aponta pra la, entao editar o
-- arquivo abaixo ja vale no proximo run - sem precisar recopiar nada.
local script = [[D:\CanalYtbe\BatataQuente\pre_production\giautosubs\GiAutoSubs.lua]]

local fh = io.open(script, "r")
if not fh then
	print("[GiAutoSubs] nao achei o script em:")
	print("  " .. script)
	print("  (o projeto mudou de lugar? edite o caminho neste arquivo)")
	return
end
fh:close()

dofile(script)
