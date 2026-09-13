# Testes do video_script

Não são unitários — dirigem o serviço de verdade, um pela API e outro por um
Chrome headless, pela mesma razão dos testes do `pre_production`: é assim que
este app quebra. Um clique de coração que a tela mostra mas o disco não tem, um
gabarito que vaza na tela, uma página em branco por um erro de javascript que o
servidor nunca vê.

O servidor precisa estar de pé (`video_script\run.bat`).

```powershell
# 1. API ponta a ponta: roteiro -> participantes + jogos -> partida
..\..\.venv\Scripts\python.exe tests\smoke.py

# 2. interface: monta um episódio pela tela num Chrome headless
C:\Users\talco\AppData\Local\Programs\Python\Python312\python.exe tests\ui.py
```

O `ui.py` roda com o Python **do sistema** porque é lá que o playwright mora —
o venv do `pre_production` só tem fastapi/uvicorn/numpy, de propósito.

A lixeira é do serviço inteiro e não morre com o roteiro, então os dois testes
guardam `dados\lixeira_perguntas.json` antes e devolvem no fim — rodar teste
não pode sujar a lixeira de verdade.

Os dois apagam o roteiro que criaram no fim (e isso leva os jogos e a partida
junto). As imagens de cada tela, que o `ui.py` salva em `tests\_telas\`, ficam
fora do git.

| arquivo | cobre |
|---|---|
| `smoke.py` | parse do `lista_do_rank.txt` nos 4 formatos de linha; participantes e jogos morando no roteiro; **salvar o roteiro não comer os `attrs` dos jogos**; reordenar; uma partida por roteiro (abrir de novo continua, não recomeça); o placar **por jogo** (3 vidas num, 2 no outro, o gasto num nao vazando pro outro); clicar/desclicar vida; subir as vidas do jogo no meio da partida sem perder o gasto; busca por nome parcial e por rank; chute fora da lista virando log; sorteio do impostor; o tempo começando em 2min, andando de 30 em 30 e **não descendo abaixo de 30s**; o **Só resposta errada** (bolinha que alterna, embaralho tirando as marcadas da tela sem apagá-las do cadastro, e o 'trazer de volta'; a **lixeira** (sai do cadastro, entra no arquivo com pergunta/resposta/origem/roteiro, sem duplicar, e a marcação das de baixo acompanhando a renumeração)); a **Discussão** com 10min de padrão, `sem tema` até cadastrar e o relógio ajustável; entrar gente na mesa no meio sem devolver vidas gastas; Reiniciar; apagar o roteiro levando jogos e partida; os 400/404 esperados |
| `ui.py` | o fluxo inteiro pela tela: criar roteiro → digitar a mesa → adicionar jogos → abrir o jogo pelo clique → importar a lista → Jogar roteiro. Confere que os campos removidos (regras, dica, discussão, vidas sugeridas) não voltaram; que **não há pontuação** e o rótulo é "Jogos do roteiro"; que o coração mede **45px** (1.5×); que as vidas sumiram do participante e o placar troca junto com o chip do jogo; as 6 perguntas importadas de um **.txt de verdade** pelo `<input type=file>` (com a linha `#` e a vazia ignoradas), as três colunas com a resposta certa **aberta**, a bolinha marcando/desmarcando, a linha marcada ficando **verde de verdade** (cor calculada, não só a classe) com o × dentro da bolinha, o embaralho tirando-a da tela, e o **lixo** mandando a pergunta pra lixeira com o nome do .txt que foi importado lá na aba Jogos; a Discussão com o tema aberto (nada tapado nela), o relógio em 10:00 e os minutos mudados no editor voltando o relógio junto; que o clique grava no disco; as duas buscas; o gabarito fechado; o cronômetro ±30s gravando; F5 mantendo o placar; e o Reinício zerando tudo. Confere também as **duplas** do impostor (`jogador | impostor`) nos dois jogos: coladas em lote, digitadas à mão, e o lado do impostor vazio sobrevivendo; que **não sobrou nenhum seletor de imagem** na aba Jogos; que o sorteio nasce tapado e, aberto, lista **cada pessoa com a sua palavra**, com um único `(impostor)`. E o editor inline do in-game: dupla acrescentada ali mesmo (e só indo pro disco no botão, não a cada tecla), nº de impostores gravando sozinho, posição nova entrando fechada no gabarito — cada um conferido também no disco, sem a URL sair do `/in-game`, e o editor seguindo aberto entre um cadastro e outro |
