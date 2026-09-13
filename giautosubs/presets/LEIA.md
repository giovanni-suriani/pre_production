# Configurações de legenda (presets)

Cada `.txt` aqui é uma legenda ajustada **no Inspector do Resolve** e exportada
pelo botão **Export Config** (grupo `Config`, no fim do Inspector do clipe).

É o caminho de volta do ajuste manual: você mexe numa legenda até ela ficar do
jeito que quer, clica em *Export Config*, dá um nome — e a **próxima rodada do
GiAutoSubs** oferece esse arquivo na pergunta *"qual configuração de legenda"*.
As legendas nascem assim, sem passar pelo `estilos.json` e sem regerar Title
nenhum.

## `None(3color).txt` — a opção "nenhuma configuração"

Arquivo **vazio**, de propósito. Escolher ele na pergunta 2 é dizer *"não
aplique configuração nenhuma por cima"*: vale inteiro o estilo assado no
`legendas.lua` — hoje, a caixa de três cores.

Existe porque o diálogo que funciona da página Edit (`fusion:RequestFile`) só
lista **arquivos** — uma opção que não seja arquivo não existe. Antes dele, a
única forma de dizer "nenhuma" era **Cancelar**, que é o mesmo gesto de "errei,
quero sair daqui".

O `GiAutoSubs.lua` reconhece pelo **nome**: qualquer arquivo começando com
`None`. O que vem depois é recado pra você (`None(3color)`), e o conteúdo nunca
é lido — não adiante linhas `chave<TAB>valor` ali.

## O formato

`chave<TAB>valor`, uma por linha. As linhas `#nome` e `#versao` são cabeçalho.
Valores são número, `{a,b}` (os inputs de par, como `Offset3` e `TextPosition`)
ou texto (`Font`, `Style`).

É o mesmo formato do botão **Generate Caption Style** — os dois botões
compartilham o corpo e o leitor. Então um preset daqui também serve para virar
um estilo nomeado do `estilos.json`:

```powershell
.\.venv\Scripts\python.exe src\gerar_macro.py ^
    --importar-estilo "giautosubs\presets\<nome>.txt" --nome <nome> --instalar
```

## O que o preset ganha, e o que ele não decide

Ganha do estilo assado no `legendas.lua` — mas só no que ele diz. O que o
arquivo não mencionar continua vindo do estilo. A **cor de cada falante** também
continua valendo: ela é escrita depois, por cima.

## Nome com data e hora?

O diálogo que pergunta o nome (`AskUser` do Fusion) não existe na página Edit —
é esperado. Quando ele não aparece, o arquivo sai como
`preset-AAAAMMDD-HHMMSS.txt`. Renomeie para algo que você reconheça: um arquivo
com nome feio se conserta, uma exportação recusada custa o ajuste inteiro de
novo.
