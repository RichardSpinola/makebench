# Makebench

Crie aplicativos Linux visualmente, com Qt, blocos e funções Python.

**0.6.0.dev2 — Bancada nativa.** Tela inicial, projetos recentes, Designer, Lógica, Código,
Mapa de janelas/estados, execução supervisionada e exportação em janela própria, com fonte Python e construção de pacotes Linux.
Tudo funciona localmente, sem conta, servidor ou IA em tempo de execução.

## Executar

Requer Python 3.12–3.14 e PySide6 6.11.2 com Widgets, SVG, WebEngine e WebChannel.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

O inicializador também usa a versão de PySide6 fornecida pelo sistema, quando
compatível. Blockly 13.4 está incorporado e não exige rede ou Node.

## Começar e retomar

A abertura sem projeto usa uma janela separada e fixa, com X interno: **Novo**, **Abrir**, recentes e modelos recentes. A bancada aparece depois da escolha; “Mostrar na inicialização” pode ser desligado.
Os cinco modelos ficam dentro do diálogo **Novo projeto**. Defina nome, pasta e
backend do aplicativo (GTK ou Qt). O editor permanece Qt e segue o estilo/paleta
nativos do desktop, sem tema próprio. Os modos permanecem no canto superior direito. Painéis têm abas na base e barras compactas, seguindo a organização do Kdenlive.

O projeto reúne JSON, `project.actions.py` e `assets/`; código próprio nunca é
substituído pela geração. Recentes oferecem busca, localizar, remover da lista e
mover arquivos para a lixeira. A pasta inteira exige uma escolha explícita.

**Salvar como** copia funções e recursos e recusa fontes conflitantes.
**Compartilhar projeto** gera um ZIP editável. Abrir um ZIP extrai primeiro em
pasta vazia, validando caminhos, links e tamanho. Isso não exporta um aplicativo.

Alterações pendentes têm recuperação periódica em
`$XDG_STATE_HOME/makebench/recovery/`, sem tocar no original. Recuperar abre uma
cópia independente e exige salvar; descartar não apaga o arquivo original.
Mudanças externas no arquivo de funções mostram **Recarregar / Manter minha versão**.

## A bancada

- **Design:** Qt usa controles e barra de título desenhados pelo estilo nativo. GTK usa imagem produzida pelo próprio GTK4/Adwaita, com as áreas reais dos componentes para selecionar e editar; não há QSS para imitar GTK. Essa prévia exige `gtk4-broadwayd` e PyGObject/GTK4, roda num display privado e nunca recebe funções ou scripts. Se faltar uma biblioteca, mostra o motivo.
  Ferramentas de inserção por clique, biblioteca por arraste, árvore
  pesquisável e inspetor com seções. Duplo clique ou F2 edita texto na própria
  composição; Escape cancela. Contêineres têm Coluna, Linha, Grade e Livre,
  margens, espaçamento, alinhamento e dimensionamento dos filhos. Alças ajustam
  margens/espaçamento. Livre oferece seleção por retângulo, guias e geometria;
  uma seleção de irmãos pode ser alinhada/distribuída como grupo. Inserir tem busca e ocupa a altura do painel; o menu de contexto oferece todos os tipos, incluindo Separador e Espaçador.
- **Lógica:** abra o evento de uma janela ou botão, escolha o filtro de estado e
  conecte blocos. O painel Python mostra só o fluxo atual e conserva o mapa de
  linhas do arquivo completo. Use Espaço para buscar blocos. Scripts de várias
  linhas são editados na gaveta; salvar confirma também o texto pendente.
- **Código:** arquivos gerado/próprio separados, funções e seus usos, busca,
  recuo, comentários e diagnóstico de sintaxe. Erros continuam salváveis;
  **Problemas** leva ao arquivo/linha ou ao bloco correspondente.
- **Mapa:** janelas reais agrupam suas variações. Duplo clique abre a composição;
  arrastar entre portas ou usar **Conectar** cria o bloco de navegação no evento.
  Excluir uma conexão remove esse bloco. Posições são independentes da lógica.
- **Exportar (janela separada):** abra as configurações do aplicativo para identidade, ícone, dependências e permissões; verifique
  o projeto e construa **Fonte Python**. O ZIP inclui código, funções, recursos,
  runtime, `run.py` e dependências. Roda fora do Makebench com Python e o backend escolhido.
  Construção usa pasta temporária, cancelamento e resultado com SHA-256.

GTK4/PyGObject é um backend real para os aplicativos criados; libadwaita é opcional.
AppImage, Flatpak, DEB e RPM podem ser construídos com ferramentas preparadas em
ambiente separado pelo Makebench. Somente receita é uma escolha explícita.
DEB, RPM e AppImage incluem Python, backend e dependências declaradas. Flatpak
resolve seu runtime e mantém terminal/tarefas isolados. Requisitos de sistema e
resultados de instalação por destino estão em `.dev/round-3-distribution.md`.

Lógica oferece blocos ou nós com fios por comportamento; terminal interativo e
depurador de snapshot estão integrados. A exportação também oferece o próprio
editor como AppImage. Notas técnicas das três rodadas estão em `.dev/handoff.md`.

## Janelas, páginas, estados e dados

**Janela** é uma janela real do sistema. **Página** alterna conteúdo dentro de
um componente de abas. **Estado** guarda diferenças da mesma composição, sem
copiar sua estrutura. **Diálogo** faz uma pergunta ou mostra uma mensagem.

Use **Projeto > Nova janela / Novo estado** e os seletores de contexto. Fora do
Padrão, edite propriedades como texto, imagem, visível, habilitado e página ativa.
O indicador ● identifica diferenças; o menu do campo restaura o Padrão.
A estrutura e os layouts são editados no Padrão. Defina janela e estado iniciais
pelo menu Projeto. Os blocos abrem/fecham janelas e mudam estados.

Declare dados do projeto/janela em **Dados**; os blocos também oferecem variáveis
locais do fluxo. Funções próprias são compartilhadas e recebem `ctx` e `valor`.
Uma sessão processa eventos em sequência, mantendo todas as interfaces responsivas.

O leitor aceita formatos 1–5. Projetos sem recursos novos continuam no formato 4;
janelas, estados, escopos, layout expandido ou configuração do app usam 5. Ao
atualizar um arquivo antigo, uma cópia `.bak-v4` preserva o original. IDs,
comentários, rascunhos, fonte própria e recursos permanecem preservados.

## Testar e observar

**F5** testa um snapshot, incluindo alterações ainda não salvas. Com uma instância
ativa, reinicia o teste; uma tarefa em andamento exige confirmação.
**Shift+F5** encerra a instância e os processos comuns supervisionados.
A gaveta reúne saída por execução, problemas, tarefas, script e erro com origem
navegável. stderr é aviso; código de saída não zero determina falha de tarefa.
O componente de saída do app mostra só o que seu código escreve nele.

Programas recebem argv separado, sem shell implícito. Bash é explícito, com
argumentos em `$1`, `$2` etc. Perguntas de texto/opção/arquivo/pasta e confirmações
são declaradas: não tentamos interpretar prompts no stdout.

Ações administrativas usam pkexec/Polkit e o diálogo do sistema, sem receber
senhas no Makebench. É preciso agente Polkit ativo. Aguarde o término ou cancele
na autenticação do sistema; não há interrupção forçada de tarefa elevada.

**Abrir, editar, salvar, recuperar e construir não executam código do projeto.**
Testar e iniciar o aplicativo exportado executam Python e scripts com as
permissões do usuário. O processo separado mantém a interface responsiva e não
é uma sandbox. Projetos não revisados abrem com explicação e revisão do código.

## Atalhos e aparência

Ctrl+1–4: Mapa, Design, Lógica, Código. Ctrl+Shift+E: Exportar. Ctrl+K: comandos e localização de
componentes, estados, fluxos e funções. Ctrl+J: gaveta. F6: regiões de foco.
Ctrl+0 enquadra; Ctrl+Alt+0 mostra tamanho real; Ctrl+roda ajusta zoom.
No canvas, V/C/T/B/I escolhem ferramenta e Enter entra no contêiner, Shift+Enter
sobe. Escape cancela gestos. Ctrl+D duplica; Delete remove; setas ajustam Livre.

Em **Exibir > Preferências**, escolha Sistema/Claro/Escuro, escala de fonte e
redução de movimento. A interface e os diálogos controlados pelo Makebench usam
português do Brasil. Os painéis podem ser redimensionados e recolhidos.

## Exemplos

- `examples/welcome-states/project.makebench.json`: três etapas, Voltar/Próximo,
  Concluir e abertura de uma segunda janela.
- `examples/script-center/app.makebench.json`: perguntas, instalação **simulada**,
  progresso, argumentos, falha, cancelamento e exemplo administrativo por `id -u`.
  Não instala pacotes; não executamos a tarefa administrativa no host nos testes.
- `examples/welcome/project.makebench.json`: exemplo anterior de páginas/funções.
- `examples/script-center/project.makebench.json`: formato 1 preservado.

```bash
./run-makebench examples/welcome-states/project.makebench.json
./run-makebench --run examples/welcome-states/project.makebench.json
```

`--run` é execução explícita de um projeto conhecido, com supervisão de teste.

## Verificar

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/blockly_smoke.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/capture_ui.py /tmp/makebench-capturas
```

A sandbox Chromium permanece ativa. Polkit real é testado apenas no contêiner
isolado descrito em `checks/polkit/README.md`. Documentação técnica em `.dev/`.
Licença própria e publicação continuam decisões do proprietário; a licença do
Blockly permanece preservada nos recursos incorporados.

## Preferências e diagnóstico

**Ctrl+,** abre preferências do Makebench com busca, aplicação imediata e
restauração por página. **Projeto → Configurações do aplicativo** é uma central
separada: suas alterações entram no histórico do projeto. Exportar não duplica
campos. **Ajuda → Diagnóstico do ambiente** copia informações sem executar
ferramentas nem instalar pacotes.

WebEngine é preparado antes da primeira apresentação da janela no inicializador,
evita recriação nativa na primeira abertura de Lógica. Atalhos WebChannel são
adiados para não bloquear a confirmação dos blocos. Propriedades simples da
imagem atualizam os widgets existentes, preservando campo/foco. Logs das tarefas
aparecem na gaveta e nos painéis de saída da janela do aplicativo.

Verificação GTK, em display descartável já aberto:

```bash
GDK_BACKEND=broadway BROADWAY_DISPLAY=:12 PYTHONPATH=src python3 checks/gtk_runtime_smoke.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/task_center_smoke.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/native_preview_smoke.py
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/startup_smoke.py
```

O display Broadway é só infraestrutura de teste; não é necessário ao aplicativo
no desktop Wayland/X11. Administração real no desktop, escala/Orca e instalação
de pacotes em VM ainda precisam do checklist.
