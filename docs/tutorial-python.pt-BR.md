# Tutorial: o mesmo app em Python

Este tutorial cria o app **Minhas notas** do
[tutorial de blocos](tutorial-blocks.md), mas escreve a lógica em Python. A
janela e os dados são feitos do mesmo jeito; só muda do passo 4 em diante.

## 1. Crie um projeto Python

**Arquivo › Novo projeto** (++ctrl+n++), modelo **Em branco**, **Programar com:
Python**, nome `Minhas notas`.

Seu código fica no arquivo `.actions.py` do projeto, ao lado do arquivo
`.makebench.json`. O Makebench o lê para ajudar você (sugestões, erros enquanto
digita, **F12** para ir à definição), mas nunca o importa nem executa até você
apertar ++f5++.

## 2. Desenhe a janela e dê nomes aos componentes

Adicione os mesmos componentes do tutorial de blocos. Agora os nomes importam,
porque o código se refere a eles. Selecione cada um e, em **Avançado**,
preencha **Nome no código**:

| Componente | Texto ou dica do campo | Nome no código |
|---|---|---|
| Campo de texto | `Título da nota` | `title_input` |
| Texto longo | `Escreva aqui…` | `text_input` |
| Botão | `Adicionar nota` | `add_button` |
| Botão | `Exportar CSV` | `export_button` |
| Tabela | | `notes_table` |
| Texto | `Pronto.` | `status` |

## 3. Crie a coleção

No painel **Dados**, **+ Coleção** chamada `Notas` com dois campos **Texto**,
`Título` e `Texto`. O código usa esses nomes: `ctx.data` aceita nomes de
coleções e campos (ou os identificadores internos deles).

## 4. Ligue os eventos

1. Selecione a janela e clique em **+ Ao iniciar** em Propriedades. O Makebench
   adiciona ao arquivo de ações uma função vazia como
   `def on_minhas_notas_start(ctx):` e a abre.
2. Selecione **Adicionar nota** e clique em **+ Ao clicar**:
   `def on_add_button_click(ctx):`.
3. Selecione **Exportar CSV** e clique em **+ Ao clicar**:
   `def on_export_button_click(ctx):`.

A lista **Eventos** na Lógica mostra qual função cada evento chama. Se você
renomear uma função à mão, Problemas avisa que o evento a perdeu.

## 5. Escreva o código

Preencha as três funções:

```python
def on_minhas_notas_start(ctx):
    ctx.show_records("notes_table", "Notas")


def on_add_button_click(ctx):
    titulo = ctx.read("title_input", "text")
    if titulo == "":
        ctx.set_text("status", "Escreva um título antes.")
        return
    ctx.data.add("Notas", Título=titulo, Texto=ctx.read("text_input", "text"))
    ctx.set_text("title_input", "")
    ctx.set_text("text_input", "")
    ctx.show_records("notes_table", "Notas")
    ctx.set_text("status", "Nota salva.")


def on_export_button_click(ctx):
    caminho = ctx.ask("save_file", "Salvar as notas em")
    ctx.export_table_csv(caminho, "notes_table")
```

O que cada chamada faz:

- `ctx.read(componente, "text")` devolve o que a pessoa digitou.
- `ctx.set_text(componente, valor)` muda um texto na janela em execução.
- `ctx.data.add(coleção, **campos)` salva um registro e devolve o id dele.
- `ctx.show_records(componente, coleção)` preenche a tabela com os registros.
- `ctx.ask("save_file", pergunta)` abre uma janela de salvar; **Cancelar**
  encerra a função ali, então `caminho` é sempre um caminho de verdade.
- `ctx.export_table_csv(caminho, componente)` grava o que a tabela mostra.

O painel **O que posso usar**, à direita do código, lista todos os métodos de
`ctx`, seus componentes e suas coleções; clique duas vezes num item para
inseri-lo. **Inserir exemplo** adiciona receitas curtas no cursor. A lista
completa está na [referência da API Python](reference/ctx.md).

## 6. Teste e depure

Aperte ++f5++ para testar. Erros no código são sublinhados enquanto você digita
e listados em **Problemas**; erros durante a execução aparecem na gaveta
(++ctrl+j++) com **Ir ao erro**.

Para parar numa linha, clique na margem do código para marcar um ponto de
parada e aperte ++f9++. Com o app pausado, ++f10++ avança uma linha, ++f11++
entra na função, ++shift+f11++ sai dela e ++f8++ continua.

## Indo além

- Divida o código em módulos: eles ficam na pasta `makebench_user/` do projeto
  e são importados com `from makebench_user.checks import validate`.
- Um projeto de blocos pode virar Python com **Projeto › Converter para
  Python…**; cada fluxo vira uma função que faz o mesmo. Os arquivos anteriores
  ficam guardados com o sufixo `.bak-blocks`.
- O exemplo **Módulos Python** mostra um projeto com vários arquivos.
