# Makebench

Editor visual de aplicativos Linux em Qt e Python.

**Estado atual: M3 — interface, blocos e código.** Monte a interface, conecte
cliques/início da janela a blocos e acompanhe o Python gerado. Escreva suas
funções na aba Código; elas ficam separadas da geração. Execução de tarefas e
exportadores são os próximos marcos. Esta ainda não é a versão completa.

## Executar

Requer Python 3.13+ e PySide6 6.11.2, incluindo Qt WebEngine e WebChannel.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench examples/welcome/project.makebench.json
```

Se o sistema já fornece a versão indicada de PySide6, o inicializador funciona
diretamente. O Blockly está incorporado e funciona sem internet, conta ou IA.

## Usar

- **Interface:** arraste componentes, organize contêineres/páginas e importe
  imagens. Em áreas livres, use as alças para redimensionar, setas para ajustar,
  Ctrl+D para duplicar e Ctrl+arraste para transferir. Esc cancela o gesto.
- **Lógica:** selecione a janela ou um botão e use **Editar lógica deste evento**
  nas propriedades. Também é possível criar vínculos na própria aba Lógica.
  Encaixe ações no evento, combine condições, repetição, variáveis e funções.
  Selecione um bloco para destacar a linha Python. Botão direito adiciona
  comentários em blocos e na área. Blocos soltos/incompletos ficam como rascunho.
- **Código:** o Python gerado é somente leitura; suas funções são editáveis à
  direita. O bloco “chamar função” recebe o nome da função e um valor; a função
  recebe `ctx` e `valor`. Erros de sintaxe são indicados sem executar o arquivo.

Desfazer/refazer funciona para interface e blocos; na aba Código, atua sobre suas
funções. Abrir, salvar e editar nunca executa o código do projeto. Os blocos de
mensagem, saída e navegação já geram Python; a execução será conectada em M4.

Ao salvar `project.makebench.json`, as funções ficam em `project.actions.py` e
as imagens em `assets/`. Compartilhe esses arquivos juntos. **Salvar como** copia
funções e recursos. Uma edição externa no arquivo Python é detectada antes de
sobrescrevê-lo. Faça Salvar como em outro local para preservar ambas as versões.

O leitor aceita formatos 1, 2 e 3; a escrita usa 3. O exemplo original de formato 1
continua em `examples/script-center/`, como verificação de compatibilidade.

## Verificar

Testes do documento, gerador, arquivos e interface nativa:

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Integração com Qt WebEngine e Blockly reais, em processo separado:

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 checks/blockly_smoke.py
```

A proteção do Chromium permanece ativa. Ambientes de automação que impedem sua
inicialização precisam permitir os processos necessários ao WebEngine. Não
configure desativação de sandbox no inicializador de produção.

Notas técnicas em [`.dev/README.md`](.dev/README.md). A documentação pública completa
e a licença do Makebench serão definidas antes da publicação. A licença do Blockly
está preservada nos recursos incorporados.
