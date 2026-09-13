# listas — o que se importa nos jogos

Os dois jogos que importam arquivo guardam aqui o material, uma pasta cada:

```
listas\adivinha_rank\        os top100: lista_do_rank.txt de cada tema
listas\so_resposta_errada\   perguntas: "pergunta | resposta certa" por linha
```

Não é o serviço que lê esta pasta — quem lê é o **navegador**, quando você
clica em `Escolher lista_do_rank.txt` (Adivinha rank) ou `Importar .txt` (Só
resposta errada). O conteúdo entra no jogo do roteiro e passa a morar no JSON
dele; mexer no .txt depois não muda um jogo já cadastrado. A pasta é o
arquivo-morte do material, não a fonte da verdade da gravação.

## adivinha_rank

Uma posição por linha: `1. Nome — valor opcional`. O parser aceita `1.`,
`1)`, `1 -` ou só `Nome` (que vira a próxima posição), e o campo depois de
TAB, ` | `, ` — ` ou `;` vira o **extra** que aparece na revelação.

Título, "Fonte:" e as notas do fim **são ignorados**: a lista começa na
primeira linha numerada e termina na última (mais o que estiver colado nela sem
número — o que separa o rodapé é a linha em branco). Foi por causa destes
arquivos que isso passou a ser assim: antes o título virava o 1º colocado e
empurrava o rank inteiro, e só na hora de jogar se via.

## so_resposta_errada

Quem importa o arquivo é o navegador, e ele **carimba o nome do .txt** em cada
pergunta. Quando você joga uma no lixo durante a gravação, é esse nome que vai
junto para `dados\lixeira_perguntas.json` — o caminho de volta até a linha ruim
aqui nesta pasta. Pergunta digitada à mão fica sem origem, e a lixeira mostra
o campo vazio.

Uma pergunta por linha: `pergunta | resposta certa`, separando com TAB, `|` ou
`;`. Linha vazia e linha com `#` são ignoradas, então dá para separar o arquivo
em seções comentadas.
