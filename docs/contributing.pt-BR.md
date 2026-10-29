# Contribuir

Relatos de bugs, traduções, documentação e código são todos bem-vindos. Issues
e pull requests podem ser escritos em português ou inglês.

## Antes de começar

- Para algo maior que uma correção pequena, abra antes uma
  [issue](https://github.com/RichardSpinola/makebench/issues) para combinarmos
  a abordagem.
- Leia a [arquitetura](architecture.md). Algumas regras não se negociam:
    - `makebench.core` nunca importa Qt.
    - Abrir, editar, ver a prévia, salvar e construir um projeto nunca executam
      o código dele.
    - Mudanças no formato de projeto precisam de um leitor para os formatos
      antigos e de testes que os abram.
    - Nada de acesso à rede durante a execução, e nada de novas dependências de
      runtime sem conversa.

## Fluxo de trabalho

1. Prepare um ambiente virtual como em [Construir e testar](building.md).
2. Faça commits focados, com mensagens claras em inglês.
3. Antes de abrir um pull request, rode:

    ```bash
    .venv/bin/ruff format src tests checks examples
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
    .venv/bin/python checks/i18n.py
    QT_QPA_PLATFORM=offscreen .venv/bin/python checks/blockly_smoke.py
    .venv/bin/python checks/docs.py
    ```

4. Adicione ou atualize testes para o comportamento que mudar. Mudanças de
   interface devem dizer como foram conferidas (capturas de tela são
   bem-vindas).

## Estilo de código

- A formatação é `ruff format` com linhas de até 100 caracteres (configurado
  em `pyproject.toml`).
- Docstrings e comentários em inglês. Todo módulo, classe e função tem uma
  docstring curta que diz o que garante, não como.
- Arquivos Python novos começam com uma linha `SPDX-License-Identifier` (veja
  Licença, abaixo).
- Use o estilo e a paleta nativos do Qt; não adicione folhas de estilo globais.

## Textos e traduções

Todo texto visível é escrito em inglês e envolvido em `tr()` ou `ntr()`.
Depois de adicionar ou mudar textos, rode `python checks/i18n.py --update` e,
se puder, adicione a tradução em `src/makebench/locale/pt_BR/makebench.po`.
Novos idiomas são bem-vindos; veja [Traduções](building.md#translations).

Mantenha as mensagens curtas e concretas: diga o que aconteceu e o que a
pessoa pode fazer em seguida. Janelas de erro usam `editor/errors.show_error`,
que deixa os detalhes técnicos atrás de **Mostrar detalhes**.

## Documentação

Este site é feito com MkDocs Material a partir da pasta `docs/`. Toda página
tem um arquivo em inglês (`page.md`) e um em português (`page.pt-BR.md`). As
páginas em `reference/` e os atalhos de teclado são gerados a partir do
código: mude o código e rode `python checks/build_reference.py`, nunca os edite
à mão. Para ver o site localmente:

```bash
.venv/bin/pip install -r docs/requirements.txt
.venv/bin/mkdocs serve
```

## Licença

Ao contribuir, você concorda que suas contribuições usam a mesma licença do
código que mudam: GPL-3.0-or-later para o editor (`editor/`) e a licença MIT
para o runtime que vai nos apps exportados (`core/`, `runtime/`,
`gtk_runtime/`, `ui/`, `terminal/`, `portable/`, `i18n.py`). Arquivos novos
começam com a linha `SPDX-License-Identifier` correspondente.
