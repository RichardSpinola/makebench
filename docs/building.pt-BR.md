# Construir e testar

Tudo aqui roda a partir de uma cópia do código-fonte, dentro de um ambiente
virtual. Nada precisa ser instalado no sistema; as ferramentas de construção
de pacotes rodam em contêineres Podman sem root.

## Ambiente de desenvolvimento

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install ruff==0.17.2
```

Abra o editor com `./run-makebench`, ou `./run-makebench caminho/projeto.makebench.json`
para abrir um projeto. `./run-makebench --run projeto.makebench.json` executa
um projeto numa janela de teste, sem o editor. Defina
`MAKEBENCH_LANGUAGE=pt_BR` para experimentar a interface em português sem mudar
suas preferências.

## Testes

A suíte roda fora da tela e não mexe nas preferências do seu editor:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Checagens adicionais, todas rodadas pela CI:

```bash
.venv/bin/ruff format --check src tests checks examples
.venv/bin/python checks/i18n.py
QT_QPA_PLATFORM=offscreen .venv/bin/python checks/blockly_smoke.py
```

`checks/blockly_smoke.py` usa a página Blockly de verdade no WebEngine, com a
aceleração da GPU desligada.

Checagens de aceitação mais longas ficam em `checks/` e gravam as evidências
numa pasta passada como primeiro argumento. Mantenha essa pasta fora do
repositório. Entre elas:

| Checagem | O que cobre |
|---|---|
| `capture_ui.py SAÍDA` | Capturas de todas as áreas em vários tamanhos (usadas nas imagens do README). |
| `gtk_runtime_smoke.py` | O runtime GTK 4: janelas, API `ctx`, tarefas, erros, código exportado. Precisa de PyGObject e GTK 4. |
| `terminal_debug_acceptance.py`, `workspace_acceptance.py` | Terminal, depurador e área de código de ponta a ponta. |
| `python_compatibility.py SAÍDA --minor 12\|13` | A suíte completa no Python 3.12 ou 3.13 dentro de um contêiner, usando wheels já preparadas. |
| `build_portable_examples.py SAÍDA --backend qt\|gtk [--prepare] [--editor]` | Constrói os exemplos (ou o editor) em todos os formatos de pacote. `--prepare` baixa e confere as ferramentas antes. |
| `polkit/` | Autorização Polkit real num contêiner descartável; veja o README dela. |
| `vm/` | Instala e abre pacotes em máquinas virtuais QEMU. |

## Pacotes

Os mesmos construtores são usados pela janela Exportar e por
`checks/build_portable_examples.py`:

- **Código-fonte** (ZIP): nenhuma ferramenta necessária.
- **DEB, RPM, AppImage**: um runtime Python embutido e o toolkit escolhido,
  preparados em contêineres Podman sem root baseados no Ubuntu 24.04. Os
  pacotes precisam de glibc 2.39 ou mais nova.
- **Flatpak**: `flatpak-builder` com o runtime do GNOME (GTK) ou do KDE (Qt).

Ferramentas e wheels preparadas ficam em `~/.cache/makebench/builders`
(`$XDG_CACHE_HOME` é respeitado). Os downloads têm versão fixa e são conferidos
por hash. Uma construção só monta uma pasta de preparo; ela nunca executa o
projeto.

Para construir o **próprio editor como AppImage**, abra a janela Exportar e
escolha **Editor Makebench (AppImage)** no campo **Exportar**, ou rode:

```bash
.venv/bin/python checks/build_portable_examples.py ~/makebench-builds --backend qt --editor --prepare
```

## Traduções { #translations }

Os textos em inglês do código são os identificadores das mensagens. Cada
idioma tem um catálogo gettext, `src/makebench/locale/<código>/makebench.po`,
lido diretamente durante a execução (sem arquivos `.mo` compilados).

1. Envolva todo texto visível em `tr("...")`, ou
   `ntr("singular", "plural", quantidade)` para contagens. Use marcadores com
   nome: `tr("Saved {name}").format(name=...)`.
2. Rode `python checks/i18n.py --update` para acrescentar os novos
   identificadores a todos os catálogos, com tradução vazia.
3. Preencha os `msgstr`. Os marcadores precisam ser iguais aos do texto em
   inglês.
4. `python checks/i18n.py` aponta entradas que faltam ou não batem e falha se
   alguma faltar. Texto sem tradução aparece em inglês durante a execução.

A página do Blockly tem o próprio dicionário pequeno em
`src/makebench/web/logic.js`, e as mensagens do próprio Blockly vêm dos
arquivos `en.js` e `pt-br.js` que o acompanham.

Para adicionar um idioma, inclua o código e o nome dele em `LANGUAGES` em
`src/makebench/i18n.py`, crie o arquivo `.po` e adicione uma página Blockly
como `web/index.pt_BR.html`, se o Blockly tiver esse idioma.

## Blockly embutido

O Blockly 13.4.0 vem do pacote npm oficial `blockly`, com a integridade SHA-512
conferida, e fica em `src/makebench/web/vendor/blockly/`. O `vendor-lock.json`
dessa pasta registra a URL, a integridade, a licença Apache-2.0 e os arquivos
copiados: os pacotes do núcleo e dos blocos, as mensagens `en` e `pt-br`, e
imagens e cursores. Os sons estão desligados e não são distribuídos. O
`LICENSE` e o `package.json` originais são mantidos. Não há CDN, nem download
durante a execução, nem Node.js para abrir o editor.

A página (`index.html`, `index.pt_BR.html`, `logic.js`, `style.css`) troca só
dados com o Python pelo Qt WebChannel; nenhuma função da ponte executa Python
ou comandos do sistema.

Atualizar o Blockly exige revisar a API de serialização, a licença e os testes
em `checks/blockly_smoke.py`. Teste em especial os comentários de bloco e o
`WorkspaceCommentSerializer` registrado explicitamente para comentários
soltos. Mantenha o modelo de lógica neutro e migre as versões salvas antes de
mudar o protocolo.
