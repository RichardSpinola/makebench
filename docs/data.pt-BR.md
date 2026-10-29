# Dados e gráficos

Apps costumam precisar guardar coisas: notas, clientes, vendas. No Makebench
você declara **coleções**, e o app guarda os **registros** delas num banco
SQLite local. Sem servidor e sem SQL para escrever.

## Coleções e campos

Abra o painel **Dados** (**Exibir › Painéis › Dados**) e clique em
**+ Coleção**. Uma coleção tem um nome e uma lista de campos; clique em
**+ Campo** para cada um.

| Tipo | Guarda | Exemplo |
|---|---|---|
| **Texto** | qualquer texto | um título, um nome |
| **Número** | números inteiros ou decimais | um preço, um estoque |
| **Data** | uma data no formato `AAAA-MM-DD` | `2026-10-29` |
| **Sim/Não** | verdadeiro ou falso | entregue |
| **Referência** | um vínculo com um registro de outra coleção (**Aponta para**) | o cliente de uma venda |

O **primeiro campo de texto** dá nome a cada registro. Uma tabela mostra esse
nome numa coluna de referência, e uma lista de opções o mostra como opção.

O Makebench protege o que está em uso: uma coleção ou campo usado por blocos
não pode ser removido (mude os blocos antes), e um registro para o qual outros
registros apontam não pode ser apagado.

## Trabalhando com registros

Nos blocos, a categoria **Registros** tem tudo; em Python, `ctx.data` faz o
mesmo. Coleções e campos são chamados pelo nome que você deu (os
identificadores internos também funcionam).

| Tarefa | Bloco | Python |
|---|---|---|
| Adicionar um registro | **adicionar registro em** | `ctx.data.add("Livros", Título="Duna", Preço=40)` |
| Mudar campos | **mudar registro em** | `ctx.data.update("Livros", livro_id, Preço=35)` |
| Apagar | **apagar registro de** | `ctx.data.delete("Livros", livro_id)` |
| Um registro | **registro de** | `ctx.data.get("Livros", livro_id)` |
| Buscar | **registros de** | `ctx.data.find("Livros", "Preço", "<", 50, order="Título")` |
| Contar | **contar registros de** | `ctx.data.count("Livros", "Estoque", ">", 0)` |
| Somar um campo numérico | **total em** | `ctx.data.sum("Vendas", "Total")` |
| Mostrar numa tabela ou lista de opções | **mostrar registros de** | `ctx.show_records("books_table", "Livros")` |
| O registro que a pessoa selecionou | **registro selecionado de** | `ctx.read("books_table", "record")` |
| O id recém-adicionado | **id do último registro adicionado** | o valor devolvido por `ctx.data.add` |

As buscas comparam com `=`, `!=`, `<`, `>`, `<=`, `>=` ou `contains`. Um
registro volta como um dicionário com os nomes dos campos, mais o `id` dele.
Percorra uma lista de registros com **para cada** (Repetições) ou um `for` do
Python.

Todos os blocos e métodos estão na [referência de blocos](reference/blocks.md)
e na [API Python](reference/ctx.md).

## Um exemplo: registrar uma venda

O exemplo **Livraria** (**Arquivo › Abrir exemplo…**) tem *Livros* (Título,
Preço, Estoque), *Clientes* (Nome) e *Vendas* (Cliente e Livro como
referências, Quantidade, Total, Entregue). O botão *Registrar venda* faz isto,
escrito aqui em Python:

```python
def on_registrar_venda_click(ctx):
    cliente = ctx.read("client_choice", "record")
    livro = ctx.read("book_choice", "record")
    if cliente is None or livro is None:
        ctx.set_text("status", "Escolha um cliente e um livro.")
        return
    quantidade = ctx.read("quantity", "value")
    estoque = ctx.data.get("Livros", livro)["Estoque"]
    if estoque < quantidade:
        ctx.set_text("status", "Estoque insuficiente.")
        return
    preco = ctx.data.get("Livros", livro)["Preço"]
    ctx.data.add("Vendas", Cliente=cliente, Livro=livro, Quantidade=quantidade,
                 Total=preco * quantidade, Entregue=False)
    ctx.data.update("Livros", livro, Estoque=estoque - quantidade)
    ctx.show_records("sales_table", "Vendas")
    ctx.set_text("cash", f"Caixa: {ctx.data.sum('Vendas', 'Total')}")
```

O exemplo em si é feito com blocos; abra-o e clique em **Ver Python** para ver
o código que o Makebench gera.

## Gráficos

O componente **Gráfico** desenha barras, uma linha ou uma pizza a partir de
duas listas: rótulos e números. Preencha com **definir dados do gráfico** ou
`ctx.set_chart`:

```python
def on_relatorio_start(ctx):
    livros = ctx.data.find("Livros", order="Título")
    ctx.set_chart(
        "stock_chart",
        [livro["Título"] for livro in livros],
        [livro["Estoque"] for livro in livros],
    )
```

O exemplo **Oficina completa** tem uma página de Dados com um gráfico.

## Arquivos e CSV

| Tarefa | Bloco | Python |
|---|---|---|
| Exportar registros | **exportar registros de** | `ctx.export_records_csv(caminho, "Livros")` |
| Exportar o que uma tabela mostra | **exportar tabela** | `ctx.export_table_csv(caminho, "books_table")` |
| Ler um arquivo CSV | **linhas do arquivo CSV** | `ctx.read_csv(caminho)` |
| Ler um arquivo de texto | **texto do arquivo** | `ctx.read_text(caminho)` |
| Gravar um arquivo de texto | **gravar texto** | `ctx.write_text(caminho, texto)` |
| Pedir um arquivo | **perguntar …** (arquivo, pasta ou arquivo para salvar) | `ctx.ask("save_file", "Salvar em")` |

Nos registros exportados, uma referência mostra o nome do registro para o qual
aponta. Os arquivos não ficam isolados (exceto num Flatpak): o app lê e grava
tudo o que a pessoa que o executa pode.

## Onde ficam os dados

| Quando | Arquivo |
|---|---|
| O app exportado | `$XDG_DATA_HOME/<id do app>/data.sqlite`, normalmente `~/.local/share/<id do app>/data.sqlite` |
| Um app Flatpak | o mesmo caminho dentro de `~/.var/app/<id do app>/data/` |
| Testes no editor (++f5++) | um banco de teste separado em `~/.local/share/makebench/test-data/` |

O id do app fica em **Projeto › Configurações do aplicativo…**.
**Apagar dados de teste…** no painel Dados esvazia o banco de teste; o editor
nunca mexe nos dados dos apps exportados. O arquivo do banco só é criado
quando o app usa uma coleção pela primeira vez.
