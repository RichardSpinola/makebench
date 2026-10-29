# Exemplos

O Makebench vem com projetos prontos. Escolha **Arquivo › Abrir exemplo…**
(também na tela inicial): o Makebench copia o exemplo para a sua pasta de
projetos e abre a cópia, então você pode mudar à vontade. O original nunca
muda.

Abrir um exemplo não executa nada. Aperte ++f5++ para testá-lo.

## Comece por aqui

**Minhas notas** — lista salva, exportar CSV
:   Uma janela com um campo de texto, um texto longo, uma tabela e dois botões.
    As notas ficam salvas numa coleção e são exportadas para CSV. É o app
    criado no [tutorial de blocos](tutorial-blocks.md).

**Assistente de boas-vindas** — estados e duas janelas
:   Um assistente que troca o conteúdo com **estados** em vez de janelas
    separadas e abre uma segunda janela no fim. Bom para aprender o **Mapa**:
    cada linha entre os cartões é uma transição de verdade.

## Lógica, tarefas e depuração

**Central de tarefas** — tarefas, perguntas e saída ao vivo
:   Executa programas e scripts Bash como tarefas supervisionadas, faz
    perguntas à pessoa e mostra a saída ao vivo num painel.

**Terminal e depuração** — pontos de parada, passo a passo
:   Um componente de terminal interativo e um fluxo preparado para o
    depurador: marque pontos de parada, aperte ++f9++ e avance passo a passo.

**Gêmeos em Python**
:   *Assistente de boas-vindas · Python*, *Central de tarefas · Python* e
    *Terminal e depuração · Python* fazem exatamente o mesmo que os três
    exemplos acima, em Python. Foram gerados com **Projeto › Converter para
    Python…**, para comparar blocos e código lado a lado.

**Módulos Python** — vários arquivos
:   Um projeto Python com o código dividido em módulos em `makebench_user/`.

## Dados

**Livraria** — livros, clientes, vendas e estoque
:   Três coleções: *Livros* (título, preço, estoque), *Clientes* (nome) e
    *Vendas*, cujos campos *Cliente* e *Livro* são referências. Registrar uma
    venda confere e baixa o estoque, calcula o total e atualiza o caixa; uma
    venda pode ser marcada como entregue. Veja o [guia de dados](data.md).

## Tudo junto

**Oficina completa** — todos os componentes, lógica em blocos
:   Usa todos os tipos de componente, várias janelas com aparências
    diferentes, um estado, uma tarefa, um terminal, funções em blocos, módulos
    e um ponto de parada. Tem uma página de Dados com autores, livros, uma
    tabela, um gráfico e exportação CSV. A janela *Roteiro de testes* dela
    lista o que experimentar.

## Exemplos de plugins

A pasta [`examples/plugins`](https://github.com/RichardSpinola/makebench/tree/main/examples/plugins)
do repositório tem plugins pequenos para ler antes de
[escrever o seu](plugins.md).

!!! note "Idioma"
    Com a interface em português, **Abrir exemplo…** oferece as versões em
    português dos projetos; em inglês, as versões em inglês.
