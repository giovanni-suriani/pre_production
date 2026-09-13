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

Os dois apagam o roteiro que criaram no fim (e isso leva os jogos e a partida
junto). As imagens de cada tela, que o `ui.py` salva em `tests\_telas\`, ficam
fora do git.

| arquivo | cobre |
|---|---|
| `smoke.py` | parse do `lista_do_rank.txt` nos 4 formatos de linha; participantes e jogos morando no roteiro; **salvar o roteiro não comer os `attrs` dos jogos**; reordenar; uma partida por roteiro (abrir de novo continua, não recomeça); clicar/desclicar vida; busca por nome parcial e por rank; chute fora da lista virando log; sorteio do impostor; o tempo começando em 2min, andando de 30 em 30 e **não descendo abaixo de 30s**; entrar gente na mesa no meio sem devolver vidas gastas; Reiniciar; apagar o roteiro levando jogos e partida; os 400/404 esperados |
| `ui.py` | o fluxo inteiro pela tela: criar roteiro → digitar a mesa → adicionar jogos → abrir o jogo pelo clique → importar a lista → Jogar roteiro. Confere que os campos removidos (regras, dica, discussão, vidas sugeridas) não voltaram; que **não há pontuação** e o rótulo é "Jogos do roteiro"; que o coração mede **45px** (1.5×); que o clique grava no disco; as duas buscas; o gabarito fechado; o cronômetro ±30s gravando; F5 mantendo o placar; e o Reinício zerando tudo |
