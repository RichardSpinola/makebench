# Makebench

Editor visual de aplicativos Linux em Qt e Python.

**Estado atual:** editor visual de interface (M2). Arraste componentes da paleta,
reorganize pela tela ou árvore, duplique, monte páginas com abas e importe imagens.
Layouts adaptáveis e áreas livres convivem no mesmo projeto, com desfazer/refazer
e salvamento. Blocos, execução de scripts e exportadores são os próximos marcos;
esta entrega ainda não é a primeira versão completa planejada.

## Executar

Requer Python 3.13 ou mais recente e PySide6 6.11.2.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

Se o sistema já fornece a versão indicada de PySide6, o inicializador também
funciona diretamente, sem instalar o projeto no sistema:

```bash
./run-makebench examples/welcome/project.makebench.json
```

Arraste da paleta para inserir ou dê duplo clique no tipo escolhido. Use a árvore
para transferir controles entre contêineres e páginas. O modo **Livre** oferece
movimentação e oito alças para redimensionar; Ctrl+arraste transfere para outro
contêiner. Esc cancela o gesto. As setas ajustam 1 pixel; Shift+setas, 10 pixels.
Ctrl+D duplica; Alt+setas para cima/baixo reorganiza entre irmãos. O menu Editar
também oferece alinhamento dentro da área livre. A grade pode ser desligada.

Adicione **Páginas com abas** e depois use **Adicionar página** ou Ctrl+Shift+P.
Mudar de aba no editor não altera a página inicial, definida nas propriedades do
conjunto. Imagens PNG/JPEG/WebP são copiadas para `assets/` ao salvar, inclusive em
**Salvar como**. Compartilhe a pasta contendo o JSON e seus recursos.

O exemplo anterior da central de scripts continua em `examples/script-center/`.
Arquivos do formato 1 continuam abrindo; salvamentos agora usam o formato 2.

## Verificar

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

As notas de implementação e continuidade ficam em [`.dev/README.md`](.dev/README.md).
A documentação pública completa e a licença serão definidas antes da publicação.
