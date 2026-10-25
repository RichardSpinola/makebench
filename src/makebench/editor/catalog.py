"""Catálogo de componentes para inserção; todos os tipos listados têm renderizador Qt/GTK."""

from PySide6.QtCore import Qt

CATEGORIES = {
    "layout": "Estrutura",
    "content": "Conteúdo",
    "input": "Entrada e ações",
    "feedback": "Saída e estado",
}
COMPONENTS = {
    "container": ("layout", "Agrupa elementos em linha, coluna, grade ou posição livre."),
    "pages": ("layout", "Um conjunto de páginas com abas dentro da mesma janela."),
    "page": ("layout", "Uma página que pertence a um conjunto de abas."),
    "spacer": ("layout", "Ocupa espaço livre no layout."),
    "separator": ("layout", "Separa visualmente grupos de controles."),
    "label": ("content", "Texto exibido na interface."),
    "image": ("content", "Imagem importada e salva junto do projeto."),
    "button": ("input", "Dispara um evento de clique e suas ações."),
    "text_input": ("input", "Recebe texto digitado pelo usuário."),
    "checkbox": ("input", "Uma opção que pode ser marcada ou desmarcada."),
    "terminal": (
        "feedback",
        "Terminal Linux interativo, com cores e teclado. A prévia não inicia processos.",
    ),
    "progress": ("feedback", "Exibe um valor entre 0 e 100."),
    "output": ("feedback", "Mostra mensagens e saída das tarefas."),
}


def filter_library(window):
    """Pesquisa nome/descrição e categoria sem recriar a seleção ou os itens arrastáveis."""
    query = window.insert_search.text().casefold()
    category = window.insert_category.currentData()
    for index in range(window.palette.count()):
        item = window.palette.item(index)
        kind = item.data(Qt.ItemDataRole.UserRole)
        group, description = COMPONENTS[kind]
        item.setHidden(
            bool(category and group != category)
            or query not in (item.text() + " " + description).casefold()
        )
        item.setToolTip(description + "\nDisponível em Qt e GTK4.")
