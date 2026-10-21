# Makebench

Editor visual de aplicativos Linux em Qt e Python.

**Estado atual:** primeira etapa funcional. É possível montar uma interface com
componentes básicos, editar propriedades, usar layouts, desfazer/refazer e
salvar/reabrir projetos. Blocos, execução de scripts e exportadores ainda serão
implementados; esta entrega não é a primeira versão completa planejada.

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
./run-makebench examples/script-center/project.makebench.json
```

Selecione um componente na árvore ou na prévia para editar. Para inserir um
grupo, escolha **Contêiner**. A organização **Livre** permite ajustar posição e
tamanho nos campos de propriedades; o arraste com alças será uma próxima etapa.

## Verificar

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

As notas de implementação e continuidade ficam em [`.dev/README.md`](.dev/README.md).
A documentação pública completa e a licença serão definidas antes da publicação.
