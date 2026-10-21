# Makebench

Editor visual de aplicativos Linux em Qt e Python.

**Estado atual: M4 — interface, blocos, funções e execução.** Monte a interface,
conecte os eventos a blocos e use **Testar aplicativo (F5)**. A janela de teste
mostra saída, resultados e erros sem executar código dentro do editor.
Exportadores e pacotes são a próxima etapa da versão completa.

## Executar

Requer Python 3.13+ e PySide6 6.11.2, incluindo WebEngine e WebChannel.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench examples/script-center/app.makebench.json
```

Se o sistema já fornece a versão indicada de PySide6, o inicializador funciona
diretamente. Blockly está incorporado; não exige internet, conta ou IA.

## Usar

- **Interface:** arraste componentes, monte páginas e importe imagens. Em áreas
  livres, use alças, setas e Ctrl+arraste. Ctrl+D duplica; Esc cancela um gesto.
- **Lógica:** selecione a janela/botão e use **Editar lógica deste evento**.
  Conecte condições, repetição, variáveis, perguntas, programas e scripts.
  Selecione um bloco para localizar a linha Python. Para escrever várias linhas,
  selecione o texto ou bloco Bash e use **Editar texto ou script**.
- **Código:** Python gerado é somente leitura; funções próprias ficam à direita.
  Elas recebem `ctx` e `valor`. A geração nunca sobrescreve suas funções.
- **Testar aplicativo (F5):** abre uma instância do projeto atual, incluindo
  alterações ainda não salvas. Se já houver uma em execução, traz essa janela
  para frente. Pare a instância antes de testar outra versão.

A janela de teste executa início da janela e cliques. Perguntas de texto, opção,
arquivo/pasta e confirmações são declaradas; cancelar/recusar encerra o fluxo.
A saída chega ao vivo. Código de saída não zero interrompe as próximas ações;
um aviso em stderr com código zero pode ter sucesso. **Ir ao erro** localiza o
bloco ou a linha da função própria. O traceback fica em **Detalhes do erro**.
Desfazer/refazer no editor continua separado
do estado da instância em execução.

O bloco de programa recebe uma lista de argumentos, sem shell implícito. Bash
é explícito; argumentos ficam em `$1`, `$2` etc. Funções podem usar `ctx.run`,
`ctx.run_script`, `ctx.ask`, `ctx.confirm`, leitura/alteração de controles e logs.
**Parar execução** encerra a instância e seus processos comuns supervisionados.

A opção **administrador** usa pkexec/Polkit e o diálogo do sistema, sem receber
senhas no Makebench. É necessário um agente Polkit ativo no ambiente gráfico.
Durante uma tarefa elevada, aguarde o término ou cancele a autenticação no
sistema; a janela e o editor não oferecem interrupção forçada dessa tarefa.

Abrir, editar e salvar nunca executa funções/scripts. **F5 e `--run` executam
código com as permissões do usuário**: o processo separado evita travar o editor,
mas não é uma sandbox para projetos desconhecidos.

## Exemplos e arquivos

- `examples/script-center/app.makebench.json`: central executável; simulação de
  instalação, progresso, argumentos, falha, cancelamento, arquivos e autorização.
  A instalação é simulada e não instala pacotes.
- `examples/welcome/project.makebench.json`: navegação e saudação por função própria.
- `examples/script-center/project.makebench.json`: interface original de formato 1,
  preservada para compatibilidade.

Para executar diretamente um projeto conhecido, sem abrir o editor:

```bash
./run-makebench --run examples/welcome/project.makebench.json
```

Ao salvar `project.makebench.json`, funções ficam em `project.actions.py` e imagens
em `assets/`. Compartilhe esses arquivos juntos. Salvar como copia funções e
recursos, sem sobrescrever fonte diferente no destino. Alterações externas são
detectadas. O leitor aceita formatos 1–4; a escrita usa 4.

## Verificar

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/blockly_smoke.py
```

A proteção Chromium permanece ativa. Testes de Polkit real são exclusivos do
contêiner rootless descrito em `checks/polkit/README.md`.

Notas técnicas em [`.dev/README.md`](.dev/README.md). Licença própria e documentação
pública completa serão definidas antes da publicação. A licença do Blockly está
preservada nos recursos incorporados.
