# Arquitetura

Uma visão geral para quem contribui. Organização dos pacotes em
`src/makebench/`:

| Pacote | Papel |
|---|---|
| `core/` | Modelo do projeto, modelo de lógica, geração de código, armazenamento, empacotamento. **Nunca importa Qt.** |
| `editor/` | A bancada Qt: Mapa, Design, Lógica (blocos ou Python), Exportar, preferências. |
| `ui/` | Desenho compartilhado pela tela de Design e pelo runtime Qt; janelas; tema. |
| `runtime/` | Executar um projeto: processo worker, tarefas supervisionadas, depurador, janela Qt. |
| `gtk_runtime/` | O mesmo contrato de runtime no GTK 4, mais a prévia de design GTK. Sem Qt. |
| `terminal/` | Sessões PTY e o componente de terminal compartilhado por Qt e GTK. |
| `web/` | A página Blockly local usada pela área Lógica. |
| `portable/`, `templates/`, `locale/`, `notices/` | Auxiliares de empacotamento, modelos de projeto novo, traduções, licenças. |

## Princípios

- **Abrir, editar, ver a prévia, salvar e construir nunca executam o código do
  projeto.** O Python é analisado com `ast`, nunca importado, exceto no
  processo de teste iniciado por F5/F9 e nos aplicativos exportados.
- **O documento é a autoridade.** Tela, árvore, mapa e Blockly são vistas.
  Cada gesto é uma entrada no histórico; Esc cancela um gesto em andamento.
- **Aparência nativa.** O Qt usa o estilo e a paleta do desktop (sem QSS
  global); as prévias GTK são desenhadas pelo próprio GTK.
- **Sem rede durante a execução.** O Blockly e suas mídias vêm embutidos; a
  página web tem uma CSP que bloqueia conexões.

## Documento

`core/project.py` define `Project`, `Component`, os tipos e layouts de
componente e o formato JSON. O leitor aceita os formatos 1–12, exceto projetos
que usam o editor de nós removido na 1.0. O formato 9 adiciona
`metadata.programming`: cada projeto é escrito em `blocks` ou `python`. Para
projetos antigos, `infer_programming()` escolhe blocos quando há fluxos,
Python quando há módulos ou um arquivo de funções editado, e nada para um
projeto vazio, e então o editor pergunta. Salvar grava o formato mais baixo
que comporta os recursos em uso (6 terminal, 8 módulos Python, 9 escolha de
programação, 10 os componentes e eventos da 1.0, 11 dados e gráficos, 12
aparência) e nunca rebaixa um formato mais novo já declarado. Quando salvar
sobe o formato, o arquivo anterior fica guardado como `.bak-vN`.

`core/storage.py` tem um único caminho de gravação, `save_workspace()`, usado
tanto pelo `Document` sem interface quanto pela janela do editor. Ele valida,
grava os recursos e os arquivos Python e depois o JSON do projeto (cada um por
um arquivo temporário, `fsync` e `os.replace`), e então marca as fontes como
salvas. O conjunto de arquivos não é transacional, e o erro diz quais arquivos
foram gravados.

O formato 10 adiciona os componentes número, controle deslizante, texto longo,
escolha, data e tabela, os eventos `change`, `close`, `timer` e `menu`, os
`menus` de janela, `frame`, `centered` e `on_top`. Um evento de menu é
`menu:<id do item>` (os ids são feitos a partir do texto do item por
`core/menus.py` e mantidos quando o texto muda), então os fluxos continuam
casando eventos por igualdade. Uma mudança feita por `ctx` nunca dispara
`change`: o Qt bloqueia os sinais e o GTK liga uma marca `programmatic`.
`close` não cancela.

O formato 11 adiciona `metadata.collections` (`id`, `name`, `fields` do tipo
`text`, `number`, `date`, `bool` ou `ref` com uma coleção `target`) e o
componente `chart`. `core/datamodel.py` valida e localiza coleções e campos.
`core/datastore.py` mantém uma tabela SQLite por coleção (`c_<id>`, colunas
`f_<id>`), migra adicionando tabelas e colunas e nunca descarta dados, e
recusa apagar um registro que outros registros ainda referenciam. O banco vive
no processo worker, então Qt e GTK o compartilham: `ctx.data` (`add`,
`update`, `delete`, `get`, `find`, `count`, `sum`, `name`) e
`ctx.show_records` passam por ele. Os dados ficam em
`$XDG_DATA_HOME/<app-id>/data.sqlite` nos apps exportados e numa pasta de
teste por projeto quando rodam pelo editor. Os gráficos são desenhados por uma
geometria comum em `core/chart.py` (QPainter em `ui/chart.py`, cairo em
`gtk_runtime/chart.py`).

O formato 12 adiciona a `background_image` da janela (o caminho de um recurso,
desenhado no modo cobrir: um filho `BackgroundImage` posto sob os controles no
Qt, um `Gtk.Overlay` cuja imagem mede zero no GTK), as propriedades `style_*`
por componente e os blocos `set_theme`/`set_background`. `core/style.py`
valida os valores de estilo (só `#rrggbb`, inteiros limitados e booleanos),
então eles nunca podem injetar CSS. O Qt restringe as regras de um componente
com a propriedade dinâmica `mbOwn`; o GTK adiciona uma classe `mb-c<N>` por
componente estilizado ao provedor de CSS da janela.

`core/history.py` guarda instantâneos nomeados da interface e da lógica (200
por padrão). Os arquivos Python usam a pilha de desfazer do próprio editor de
texto.

## Lógica

`core/logic.py` valida o modelo de lógica neutro
(`metadata.logic_version = 1`): eventos (`start` numa janela, `click` num
botão), comandos e expressões, cada um com um id. Um fluxo cujo `body` é
`null` é um rascunho e não gera código. Em projetos Python, um fluxo tem
`function` em vez de `body`/`workspace`: o tratador chama
`ctx.handle_event(nome)`, e `codegen.convert_to_python()` transforma fluxos de
blocos nessas funções.
As funções em blocos ficam em `metadata.functions` como `{id, name, params,
body, workspace}`. O gerador as emite primeiro como `def fn_<nome>(ctx,
*params)`, com as entradas copiadas para `local_variables`; `call_function`
(comando ou valor) se refere à função pelo id e passa os `args` em ordem, e
`return` só vale dentro de uma função. A conversão para Python copia essas
definições como estão. Fluxos e funções podem ter um nome de `module`
opcional (1–60 caracteres), que só os agrupa na barra lateral.
Limites: 48 níveis e 5000 nós por fluxo.

- `web/logic.js` traduz os blocos do Blockly de e para esse modelo. Ao abrir,
  ele compila o workspace salvo e reconstrói os blocos a partir do modelo se os
  dois discordarem. Campos de texto livre nunca são tratados como Python.
- `core/codegen.py` gera tratadores determinísticos sobre a API `ctx`. Os
  valores são escapados com `repr`, os operadores vêm de uma lista permitida, e
  `GeneratedCode.lines` liga `(flow_id, block_id)` a uma linha, para destaque,
  navegação de erros e pontos de parada.
- `core/navigation.py` deriva as janelas, estados e ligações do Mapa a partir
  das ações de navegação reais e edita essas ações quando você desenha
  ligações.

### Ponte com o Blockly

`editor/logic.py` carrega o WebEngine sob demanda. A página roda num perfil
temporário, só pode navegar para a página de entrada embutida, e o
interceptador de requisições só permite recursos embutidos. `LogicBridge`
troca apenas JSON, seleção e estado: nenhuma função de shell, arquivo ou
importação é exposta. Antes de salvar, trocar ou desfazer, o editor descarrega
o workspace diretamente por JavaScript; mensagens de um contexto antigo são
ignoradas por token.

## Seu Python

`core/source.py` lê o arquivo `.actions.py` do projeto e os módulos
`makebench_user` declarados como UTF-8. `SourceText` leva um instantâneo de
cada arquivo, então o worker importa o instantâneo, e não a pasta ao vivo. Um
código inválido continua editável e pode ser salvo. Mudanças externas são
detectadas comparando com o conteúdo original. `core/code_index.py`,
`editor/code_assist.py` e `editor/code_workspace.py` fornecem sugestões,
definições e diagnósticos estáticos. O índice guarda o resumo de cada arquivo
até a árvore dele mudar e entrega a árvore já analisada ao `diagnose`, então,
depois de uma edição, só aquele arquivo é analisado e percorrido de novo.
`core/python_check.py` (MIT, sem importar código do usuário) encontra todos os
erros de sintaxe (primeiro o do Python, depois os do parso com recuperação de
erros), nomes indefinidos via `symtable`, membros de `ctx`/`ctx.data` que não
existem em `runtime/worker.py` e ids de componentes desconhecidos, cada um com
uma dica traduzível; ele também tem `tidy()`, a limpeza opcional ao salvar.
`editor/code_reference.py` monta o painel "O que posso usar" a partir de
`editor/stubs/makebench_ctx.pyi`, e `editor/code_examples.py` guarda as
receitas de "Inserir exemplo".

## Execução e depuração

- `runtime/worker.py` roda os tratadores num processo separado. O protocolo de
  controle é JSON num descritor de stdout duplicado; o fd 1 é redirecionado
  para o stderr, para que prints comuns não sejam confundidos com mensagens de
  controle. `core/lines.py` divide esse fluxo em linhas sem reler bytes
  antigos, com limite de 64 MB por mensagem (o bastante para tabelas com
  centenas de milhares de linhas).
- `ui/table.py` mostra as tabelas Qt por um `QAbstractTableModel`, então só as
  células visíveis são desenhadas; 50.000 linhas se preenchem em poucos
  centésimos de segundo.
- `runtime/session.py` supervisiona o worker com `QProcess` numa sessão
  própria. As tarefas rodam em `QProcess`es separados; uma saída diferente de
  zero gera `TaskError`, e stderr sozinho não é falha. Parar envia TERM e,
  depois de 700 ms, KILL.
- `runtime/process.py` resolve programas sem shell implícito. O Bash só é usado
  por ações de script explícitas, com os argumentos passados como parâmetros
  posicionais.
- Tarefas administrativas usam `pkexec --disable-internal-agent` e continuam
  supervisionadas mesmo se o worker morrer. O Makebench nunca coleta senhas.
- `runtime/debugger.py` fornece pontos de parada por id de bloco ou
  arquivo/linha e um instantâneo limitado e só de leitura da pilha e das
  variáveis.
- `gtk_runtime/` implementa as mesmas operações de `ctx` no GTK 4;
  `runtime/gtk_bridge.py` o supervisiona a partir do Qt.

O processo de teste **não é um sandbox**: o código do projeto roda com as
permissões do usuário.

## Distribuição

- `core/packages.py` e `core/exporter.py` constroem código-fonte Python, DEB,
  RPM, AppImage e Flatpak numa pasta de preparo inerte. Os metadados são
  limpos para uma só linha, para não injetarem entradas de desktop ou
  comandos.
- `core/build_environment.qt_packages()` pede `PySide6-Essentials`, mais
  `PySide6-Addons` (Qt WebEngine) só quando uma janela é Visão web; a
  exportação de código-fonte, o runtime portátil e o Flatpak usam essa função.
- `checks/footprint.py` mede a abertura do editor, os apps exportados, uma
  tabela de 50.000 linhas e o tamanho da exportação contra
  `checks/footprint_limits.json` na CI.
- `core/build_environment.py` prepara as ferramentas explicitamente em
  contêineres Podman sem root, com downloads oficiais de versão fixa e wheels
  conferidas por hash, em `~/.cache/makebench/builders`.
- `core/portable.py` prepara o runtime Python embutido e constrói o AppImage
  do editor.
- `editor/publish.py` é a janela Exportar; preparo e construções rodam em
  threads, com saída visível e cancelamento.

## Idioma da interface

`makebench/i18n.py` fornece `tr()` e `ntr()`. Os textos em inglês do código
são os identificadores das mensagens; os arquivos
`locale/<código>/makebench.po` são lidos diretamente (sem etapa `.mo`). O
idioma é definido antes de importar os módulos que montam constantes
traduzidas e é passado aos processos filhos por `MAKEBENCH_LANGUAGE`. A página
do Blockly carrega `index.html` (inglês) ou `index.pt_BR.html`, e
`web/logic.js` guarda o próprio dicionário pequeno. Veja
[Construir e testar](building.md#translations) para o fluxo de trabalho.
