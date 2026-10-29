# Escrever plugins do Makebench

Plugins adicionam comandos de menu, modelos de projeto, peças reutilizáveis e
trechos de código ao editor. Eles são Python comum, então um plugin roda
**com as permissões do seu usuário**: o Makebench vem com todos os plugins
desligados e pergunta antes de ligar um. Instale plugins só de pessoas em quem
você confia.

## Onde ficam os plugins

```
~/.local/share/makebench/plugins/<id>/
    plugin.json
    plugin.py
```

Use **Plugins › Gerenciar plugins…** para instalar uma pasta, abrir a pasta de
plugins e ligar ou desligar cada um. Nada de um plugin é importado até você
ligá-lo.

## plugin.json

```json
{
  "id": "word-count",
  "name": "Word count",
  "version": "1.0.0",
  "api": 1,
  "description": "What it does, in a sentence.",
  "author": "Your name"
}
```

Campos opcionais que o Makebench mostra antes de você ligar um plugin:
`"license"`, `"source"` (o endereço web do código) e `"permissions"` (veja
abaixo).

O `id` precisa ser igual ao nome da pasta (letras minúsculas, dígitos, `-` e
`_`). `api` é `1` ou `2`; qualquer outro valor aparece como incompatível e
nunca é carregado.

## plugin.py

```python
def register(api):
    def shout(project):            # `project` é uma cópia que você pode mudar
        project.root.properties["title"] = project.root.properties["title"].upper()

    api.add_command("Shout the title", shout)
    api.add_snippet("greet", 'ctx.message("Hello")\n')
    api.add_piece(piece_dict)      # o mesmo JSON de uma peça reutilizável salva
```

- `api.add_command(nome, função)` adiciona o comando ao menu **Plugins**. A
  função recebe uma cópia do projeto; quando ela retorna, o resultado substitui
  o projeto como **uma única mudança que pode ser desfeita**.
- `api.add_snippet(nome, código)` oferece `código` nas sugestões do editor
  Python (Ctrl+Espaço) quando você digita o começo de `nome`.
- `api.add_piece(peça)` adiciona uma peça pronta em **Editar › Inserir peça**.

## API v2

Plugins que declaram `"api": 2` também podem usar:

- `api.add_template(nome, descrição, build)` adiciona um modelo em
  **Novo projeto** e na tela inicial. `build(nome)` devolve um novo `Project`.
- Comandos com dois parâmetros, `função(project, context)`, recebem um
  `context` com `window` (o id da janela aberta no Design), `parent` (um widget
  onde abrir janelas), `read_asset(nome)` e `import_image(caminho)`, que copia
  uma imagem para o projeto e devolve o nome `assets/...` dela.
- `raise api.Refusal("mensagem")` interrompe um comando com uma mensagem para a
  pessoa, sem desligar o plugin. Retorne sem mudanças (uma janela cancelada) e
  nada entra no histórico.

## Plugins oficiais

Alguns plugins vêm com o Makebench. Eles aparecem como **Oficial** em
**Gerenciar plugins…**, começam desligados como qualquer outro e ficam em
`src/makebench/pluginpack/`. Um plugin que você instala não pode reutilizar os
ids deles.

**Visão web** (`pluginpack/webview`) é a referência da API v2. Ele adiciona um
modelo de Visão web e comandos para transformar uma janela em Visão web, voltar
a uma janela normal e editar a página dela com prévia ao vivo. Uma janela de
Visão web mostra uma página HTML de ponta a ponta e não tem componentes; links
para sites abrem no navegador. O próprio Makebench mostra, salva e exporta
essas janelas, então projetos feitos com o plugin continuam funcionando com ele
desligado. O app Qt exportado precisa do Qt WebEngine, e o runtime GTK precisa
do WebKitGTK 6.

## Permissões

Um plugin roda com as suas permissões, então declare o que ele faz. O Makebench
lê o Python do plugin sem executá-lo e mostra o que ele claramente pode fazer.
Declare isto no `plugin.json` como `"permissions": [...]`:

| Permissão | Encontrada quando o código |
|---|---|
| `network` | importa `socket`, `urllib`, `http`, `requests`… |
| `programs` | importa `subprocess` ou chama `os.system`… |
| `native-code` | importa `ctypes` |
| `dynamic-code` | chama `eval`, `exec`, `compile` ou `__import__` |
| `files-outside` | apaga arquivos (`shutil.rmtree`, `os.remove`…) |

**Gerenciar plugins…** também mostra a licença, a fonte e uma impressão digital
SHA-256 de todos os arquivos do plugin. Se o código usa algo que o plugin não
declarou, aparece um aviso. A análise só encontra casos simples: é uma ajuda,
não uma garantia, então leia o código de um plugin que você não conhece.

## Índice do catálogo

Um catálogo é um arquivo JSON (`"format": "makebench-plugin-index"`,
`"version": 1`) que lista plugins com `id`, `name`, `version`, `api`,
`license`, `source`, `download` (https), `sha256` (a impressão digital acima),
`permissions` e `reviewed`. O Makebench recusa um download cuja impressão
digital, API ou permissões sejam diferentes das do índice. `reviewed` quer
dizer que alguém leu o código; não é uma garantia.

## Boas práticas

- Mantenha `register` rápido e sem efeitos colaterais; faça o trabalho dentro
  dos comandos.
- Nunca grave fora do projeto que você recebeu; trabalhe na cópia e devolva-a.
- Use `api.Refusal` para problemas esperados, em vez de deixar uma exceção
  desligar o plugin.
- Escolha a menor `api` de que precisa, para mais versões carregarem o plugin.
- Declare todas as permissões e diga o porquê na descrição.

## Segurança e falhas

Se `register` ou um comando gerar um erro, só aquele plugin é desligado, e a
mensagem aparece em **Gerenciar plugins…**. O editor continua rodando e o seu
projeto não é alterado por um comando que falhou.

Um exemplo completo está em `examples/plugins/word-count`.
