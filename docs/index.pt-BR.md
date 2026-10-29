---
hide:
  - toc
---

# Makebench

<div class="mb-hero" markdown>

![](assets/logo.svg)

Uma oficina visual para pequenos apps de desktop Linux. Desenhe as janelas,
programe com **blocos** ou **Python**, teste no editor e exporte um pacote
que roda sem o Makebench.

[Instalar](install.md){ .md-button .md-button--primary }
[Crie seu primeiro app](tutorial-blocks.md){ .md-button }

</div>

![A área Design](images/design.png)

## Comece por aqui

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Instalar**

    ---

    Um AppImage, sem conta e sem precisar de internet.

    [:octicons-arrow-right-24: Instalar](install.md)

-   :material-puzzle:{ .lg .middle } **Tutorial: blocos**

    ---

    Crie um app de notas com lista salva e exportação CSV, sem digitar código.

    [:octicons-arrow-right-24: Começar](tutorial-blocks.md)

-   :material-language-python:{ .lg .middle } **Tutorial: Python**

    ---

    O mesmo app, com a lógica escrita em Python e a ajuda do editor.

    [:octicons-arrow-right-24: Começar](tutorial-python.md)

-   :material-folder-open:{ .lg .middle } **Exemplos**

    ---

    Projetos prontos para abrir, testar e mudar.

    [:octicons-arrow-right-24: Exemplos](examples.md)

</div>

## Guias

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **[Guia de uso](user-guide.md)**

    ---

    A bancada, uma área por vez: Mapa, Design, Lógica, testes e depuração.

-   :material-database:{ .lg .middle } **[Dados e gráficos](data.md)**

    ---

    Coleções salvas em SQLite, referências, CSV e gráficos.

-   :material-palette:{ .lg .middle } **[Aparência e temas](appearance.md)**

    ---

    Temas do editor, aparência das janelas, estilos dos componentes e peças
    reutilizáveis.

-   :material-package-variant-closed:{ .lg .middle } **[Exportar](export.md)**

    ---

    AppImage, DEB, RPM, Flatpak ou código Python, em Qt ou GTK.

</div>

## Referência

<div class="grid cards" markdown>

-   :material-widgets:{ .lg .middle } **[Componentes](reference/components.md)**

    ---

    Todos os componentes, suas propriedades e seus eventos.

-   :material-view-grid-plus:{ .lg .middle } **[Blocos](reference/blocks.md)**

    ---

    Todos os blocos, o que fazem e o Python que geram.

-   :material-code-braces:{ .lg .middle } **[API Python](reference/ctx.md)**

    ---

    O objeto `ctx` que suas funções recebem.

-   :material-keyboard:{ .lg .middle } **[Atalhos de teclado](shortcuts.md)**

    ---

    Atalhos do editor e do editor de código.

</div>

## Princípios

- **Nada roda de surpresa.** Abrir, editar, ver a prévia, salvar e construir
  nunca executam o código do projeto; só testar (++f5++) e depurar (++f9++).
- **Sem internet.** Sem conta, sem servidor e sem IA durante o uso.
- **Seu app é seu.** O editor é GPL-3.0-or-later; o pequeno runtime que vai
  dentro dos apps exportados é MIT, então você escolhe a licença do seu app.

O Makebench também tem [plugins](plugins.md), uma
[promessa de compatibilidade](compatibility.md) e notas sobre
[construção](building.md) e [arquitetura](architecture.md) para quem quer
contribuir.
