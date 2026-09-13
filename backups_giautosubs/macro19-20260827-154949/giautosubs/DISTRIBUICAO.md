# De ferramenta pessoal a script para outros

O que precisa mudar — e o que precisa ser *decidido* — para o GiAutoSubs sair
desta máquina e rodar na de outra pessoa.

Ordenado por bloqueio: os primeiros itens impedem a distribuição, os últimos só
tornam a experiência ruim.

---

## 0. Antes de qualquer código: a licença

**Este é o único item que pode impedir a distribuição por completo.**

O `giautosubs/vendor/autosubs-macro.setting` é obra de terceiros — do projeto
[AutoSubs](https://github.com/tmoroney/auto-subs), de Tom Moroney. O GiAutoSubs
não é inspirado nele: ele **redistribui** o arquivo dele, patcheado. O grafo de
animação inteiro (Follower1 → CharacterLevelStyling → BezierSpline) é dele.

A instalação local não traz nenhum `LICENSE` — verifiquei. Então:

- [ ] Ler a licença no repositório do AutoSubs (não a assuma; pode ser MIT, GPL,
      ou nenhuma — cada uma leva a um desfecho diferente).
- [ ] Se for permissiva: manter o aviso de copyright e o texto da licença junto
      do `.setting` vendorado, e creditar no README.
- [ ] Se for copyleft: o GiAutoSubs herda a obrigação.
- [ ] Se não houver licença: **não redistribua o arquivo.** O caminho alternativo
      é pedir que o usuário instale o AutoSubs e gerar o macro a partir da cópia
      dele — o `gerar_macro.py` já procura em
      `%LOCALAPPDATA%\AutoSubs\resources\` antes do `vendor/`. Basta inverter a
      ordem e remover o `vendor/` do pacote.

Vale também abrir uma issue lá contando o que foi encontrado (os keyframes de
exemplo que pintam o outline de azul, o laço de `UpdateAllStyleColors` que lê
`BubbleEnabled` inexistente). São bugs reais no projeto deles.

---

## 1. Caminhos presos a esta máquina

Todos precisam sair do código. Inventário real:

| Arquivo | O que está fixo |
|---|---|
| `giautosubs/GiAutoSubs.lua:43` | `ARQUIVO` = o caminho do `legendas.lua` do seu corte |
| `Scripts/Utility/GiAutoSubs.lua` | o lançador aponta para `D:\CanalYtbe\...\giautosubs\GiAutoSubs.lua` |
| `src/gerar_macro.py` (`FUSCRIPT`) | `C:\Program Files\...\fuscript.exe` |
| `src/giautosubs.py` (`pasta_dos_scripts`) | fallback `D:\CanalYtbe\BatataQuente\scriptsPrimarios` |
| `src/config.py` | `sources_dir`, `scripts_dir` |

O mais grave é o `ARQUIVO`: hoje o usuário edita um `.lua` para escolher o corte.
Isso não sobrevive a outra pessoa.

- [ ] `ARQUIVO = nil` como padrão e usar o seletor de arquivo — o código já tem
      `fusion:RequestFile`, mas só cai nele quando o caminho está vazio. **Ainda
      não foi testado dentro do Resolve**: em script da página Edit o `fusion`
      pode não existir, e aí o script morre em silêncio.
- [ ] Alternativa mais robusta: um `giautosubs.json` ao lado do script, com o
      último caminho usado, gravado pelo lado Python.
- [ ] `FUSCRIPT`: procurar no `PATH`, depois nos locais conhecidos por
      plataforma, e seguir sem validar se não achar (já é o comportamento — mas
      o caminho é só o do Windows).
- [ ] O lançador em `Scripts/Utility` precisa ser **gerado** por um instalador,
      não copiado à mão com um caminho dentro.

---

## 2. Suposições verificadas em UMA máquina só

Esta é a parte que mais me preocuparia. Cada número abaixo foi lido de um
DaVinci Resolve 21.0.4.5 free, Windows 11. Nenhum deles está documentado pela
Blackmagic.

| Suposição | Onde | Risco se mudar |
|---|---|---|
| `ElementShape`: 0 Text Fill, 1 Text Outline, **2 Border Fill**, 3 Border Outline | `giautosubs.py` `FORMA_BORDA` | caixa some ou vira contorno |
| Elementos 1–4 nascem White Solid Fill / Red Outline / Black Shadow / Blue Border | mapa de elementos | outline e sombra saem errados |
| `Level`: 1 caractere, 2 palavra, 3 linha | `giautosubs.py` `NIVEIS` | caixa por letra em vez de por palavra |
| Códigos do StyledText: `Enabled 2000`, `Red 2401`, `Green 2402`, `Blue 2403` | `GiAutoSubs.lua` `COD` | destaque não acende |
| `Offset{n}` existe e é relativo; `Position{n}` é absoluto | `OFFSET_CANDIDATOS` | sombra no canto da tela |
| `bmd.wait` **não** existe no host de Scripts | `esperar()` | só afeta desempenho |
| Inputs de um elemento só materializam após `Enabled{n}=1` | ordem de escrita | escrita descartada em silêncio |

O que fazer:

- [ ] Nenhum desses deve ser um número solto no código. Já não são — mas hoje a
      única prova para outra build é o `DEBUG_PROPRIEDADES` **ligado**.
- [ ] **Deixe `DEBUG_PROPRIEDADES = true` no release inicial.** O custo é log
      verboso; o benefício é que o primeiro relatório de bug de qualquer usuário
      já vem com a resposta dentro.
- [ ] Melhor ainda: um comando "diagnose" que roda em um clipe, imprime o dump e
      pede para colar na issue. O `DIAGNOSTICO = true` já faz quase isso.
- [ ] Testar em uma versão do Resolve **Studio** e em uma **outra major**
      (20.x). O item 3 abaixo explica por que Studio importa.

---

## 3. Versão e edição do Resolve

- O lado Resolve é Lua rodando *de dentro* porque a API de scripting **externa**
  é Studio-only desde a 19.1. Num Resolve Studio o usuário poderia rodar por
  fora, em Python, o que seria bem melhor — vale detectar e oferecer.
- [ ] Declarar a versão mínima testada e **verificar em tempo de execução**
      (`resolve:GetVersionString()`), avisando em vez de falhar torto.
- [ ] O macro do AutoSubs muda entre versões deles. O `gerar_macro.py` avisa
      quando um patch não acha o alvo (`WARNING: ...`) — bom — mas hoje ele
      **continua e grava mesmo assim**. Para outros usuários, um patch que não
      aplicou deveria ser erro, não aviso.
- [ ] Fusion varre `Templates/Edit/Titles` **no boot**. Qualquer instalador
      precisa dizer isso, ou o usuário instala e nada muda.

---

## 4. Windows-only

- [ ] `%APPDATA%` / `%LOCALAPPDATA%` estão espalhados. No macOS os caminhos são
      `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/`
      e o Linux é outro. Concentrar em uma função `caminhos_do_resolve()`.
- [ ] Separadores de caminho e `newline="\n"` na escrita do `.setting`.
- [ ] `fuscript` tem nome e local diferentes por plataforma.

---

## 5. O pipeline em volta não é generalizável (e tudo bem)

O GiAutoSubs hoje lê `corte.json`, `turnsManual.json`, `turnsWhisper_*.json` —
o formato do **seu** app. Ninguém de fora tem isso.

A decisão de escopo importa mais que o código:

- **Opção A — só o lado Resolve.** Distribuir `GiAutoSubs.lua` + o macro + um
  formato de entrada documentado (`legendas.lua`/`.json`). Quem quiser gera o
  arquivo como preferir. É de longe o menor recorte e o mais útil: o valor real
  está no que foi descoberto sobre o Text+, não no seu pipeline.
- **Opção B — aceitar `.srt` / `.json` do Whisper direto.** Um conversor de
  entrada em vez do seu `corte.json`. Cobre 90% dos usuários.
- **Opção C — o app inteiro.** Muito maior, e a maior parte não tem a ver com
  legenda.

Recomendo A, com B logo em seguida.

- [ ] Documentar o schema do `legendas.lua` como contrato público (hoje só
      existe implícito no `giautosubs.py` e no fixture `amostra_legendas.lua`).
- [ ] Versionar esse schema (`versao = 2` já existe — usar de verdade: o Lua
      deveria recusar um número que não conhece).

---

## 6. Configuração que hoje é constante no topo do arquivo

Ninguém deveria editar `.lua` para mudar comportamento:

| Constante | O que faz |
|---|---|
| `TRACK_UNICA` | todas as legendas numa track |
| `TRACKS_ACIMA` | tracks novas acima do que existe |
| `AUTO_ATUALIZAR_TEMPLATE` | troca o template defasado sozinho |
| `DEBUG_PROPRIEDADES` | dump completo |
| `DIAGNOSTICO` | um clipe só |
| `TEMPLATES` | nomes aceitos no Media Pool |

- [ ] Mover para o `legendas.json` (o lado Python já escreve) ou para um
      `giautosubs.json` de preferências.
- [ ] `AUTO_ATUALIZAR_TEMPLATE` merece atenção especial: ele **apaga um item do
      Media Pool**, o que deixa offline legendas de rodadas anteriores. Numa
      ferramenta pessoal isso é aceitável porque você sabe. Para outros, precisa
      de confirmação explícita ou de detecção de uso antes de apagar.

---

## 7. Dependências que o usuário precisa ter

- [ ] **Fonte.** O estilo padrão pede Open Sans. Se não estiver instalada, o
      Fusion cai num fallback silencioso e a legenda sai com outra cara. Checar
      e avisar — o `GiAutoSubs.lua` já lê `Font` de volta, basta comparar.
- [ ] **faster-whisper + ffmpeg** para o tempo por palavra. Documentar versões.
- [ ] **Python** para o lado gerador. Qual versão mínima? Hoje roda no 3.12.
- [ ] O `.venv` do projeto não é o mesmo Python dos scripts de transcrição —
      isso já confunde aqui dentro; para outros vira suporte.

---

## 8. Idioma

Decisão pendente e que fica pior com o tempo:

- Mensagens e CLI: **inglês** (feito).
- Comentários: português.
- `MACRO.md`, este arquivo: português.
- **As chaves do `estilos.json` são em português** (`fonte`, `familia`,
  `destaque`, `caixa`, `nivel: "palavra"`) — e elas aparecem no log em inglês
  (`level palavra`). Para outros usuários isso é um obstáculo real: é o arquivo
  que eles vão editar.

- [ ] Ou traduzir as chaves e manter um mapa de compatibilidade, ou assumir o
      português e documentar. Não deixar meio a meio.
- [ ] Nomes de falantes do exemplo (`Cupertino`, `Heitor`, `Giovanni`) e o estilo
      `batata_shorts` são deste canal. Precisam virar exemplos neutros.

---

## 9. Falha e suporte

O Fusion erra em silêncio — é o tema do `MACRO.md`. Numa ferramenta pessoal
você lê o log; outros não vão.

- [ ] O resumo já agrupa falhas por motivo e conta clipes recusados. Manter.
- [ ] Gravar o log em arquivo, ao lado do `legendas.lua`. Pedir "cole o Console"
      dá um relato truncado — como aconteceu nesta própria história.
- [ ] Mensagem de erro que diz **o que fazer**, não só o que houve. O bloco do
      macro defasado é o modelo a seguir.
- [ ] Nenhuma telemetria. Não adicione.

---

## 10. O que já está pronto para outros (não estrague)

Vale listar porque é o que dá confiança para distribuir:

- `valida_macro.lua` — valida o `.setting` fora do Resolve e compila as 83
  rotinas embutidas. O `gerar_macro.py` roda ele sozinho e **recusa** um arquivo
  quebrado.
- `testes.lua` — roda o `main` inteiro contra um Resolve falso, incluindo a
  regra de materialização de inputs, as cores do Follower1 e a troca do template
  defasado.
- `GiAutoSubsVersao` — o carimbo que detecta macro velho no Media Pool.
- `MACRO.md` — a documentação que evita que a próxima pessoa perca as mesmas
  três rodadas.

- [ ] CI que rode os dois validadores. Eles não precisam do Resolve aberto, só
      do `fuscript` — dá para rodar num runner Windows com o Resolve instalado.

---

## Checklist mínimo antes do primeiro release

1. [ ] Licença do AutoSubs resolvida (seção 0)
2. [ ] `ARQUIVO` deixa de ser caminho fixo, e o seletor testado dentro do Resolve
3. [ ] Instalador que gera o lançador e copia o macro, nas 3 plataformas ou só
       no Windows **declarado**
4. [ ] `DEBUG_PROPRIEDADES = true` e log em arquivo
5. [ ] Estilo de exemplo neutro, sem nomes deste canal
6. [ ] Testado em pelo menos uma outra máquina, e numa versão do Resolve
       diferente
7. [ ] README com: o que faz, o que precisa, o formato de entrada, e o passo do
       reinício do Resolve
8. [ ] Escopo declarado (seção 5) — o que a ferramenta **não** faz

---

## Uma observação sobre esforço

A distância entre "funciona aqui" e "funciona na máquina dos outros" neste
projeto é quase toda de **empacotamento e suposições**, não de recurso faltando.
As seções 1, 4, 6 e 7 são trabalho mecânico. A seção 2 é a que exige outra
máquina para fechar, e a seção 0 é a que pode terminar a conversa — vale ser a
primeira a ser resolvida, antes de investir nas outras.
