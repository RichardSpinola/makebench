# Makebench

[![Checks](https://github.com/RichardSpinola/makebench/actions/workflows/checks.yml/badge.svg)](https://github.com/RichardSpinola/makebench/actions/workflows/checks.yml)
[![License: GPL-3.0-or-later + MIT](https://img.shields.io/badge/license-GPL--3.0--or--later%20%2B%20MIT-blue.svg)](#licença)

**Crie aplicativos Linux visualmente — e continue com o código.**

O Makebench é um editor visual de aplicativos nativos para Linux. Você monta
janelas com controles reais Qt ou GTK 4, descreve o comportamento com
blocos, escreve seu próprio Python onde quiser e exporta um aplicativo executável
ou pacotes DEB, RPM, AppImage e Flatpak. Tudo roda localmente: sem conta, sem
servidor e sem IA em tempo de execução.

[Read in English](README.md) ·
[Guia de uso](docs/user-guide.pt-BR.md) ·
[Arquitetura (inglês)](docs/architecture.md) ·
[Compilar e testar (inglês)](docs/building.md) ·
[Como contribuir (inglês)](CONTRIBUTING.md)

![Área Design com prévia Qt nativa, árvore de componentes e propriedades](docs/images/design.png)

> **Situação: alfa (0.9.0).** O editor é utilizável e coberto por testes
> automatizados, mas o formato dos projetos e as APIs ainda podem mudar. Ainda
> há um AppImage na
> [página de versões](https://github.com/RichardSpinola/makebench/releases); ou rode a partir do código-fonte (abaixo).

## O que dá para fazer

- **Mapa:** veja todas as janelas e estados do aplicativo e ligue-os arrastando
  entre portas. Cada ligação é uma ação de navegação real na lógica.
- **Design:** monte janelas com controles nativos: linhas, colunas, grades e
  posicionamento livre, páginas, imagens, terminais e mais. A prévia Qt usa o
  estilo do seu desktop; a prévia GTK é desenhada pelo próprio GTK.
- **Lógica:** blocos no estilo Scratch (Blockly). O Python gerado fica sempre visível.
- **Código:** suas funções e módulos Python, com sugestões, ir para a definição
  (F12), diagnósticos e busca no projeto inteiro.
- **Testar e depurar** com F5 e F9: processo separado e supervisionado, saída ao
  vivo, tarefas com stdout/stderr, terminal interativo, pontos de parada em
  blocos ou linhas, e pilha e variáveis somente para leitura.
- **Exportar** em fonte Python ou construir pacotes DEB, RPM, AppImage e Flatpak
  com Python e o toolkit escolhido incluídos. O próprio editor também pode ser
  construído como AppImage.

## Começo rápido (pelo código-fonte)

Requisitos: Linux, Python 3.12–3.14 e as bibliotecas de sistema que o Qt usa para
o WebEngine (no Ubuntu: `libegl1 libgl1 libxkbcommon0 libnss3 libdbus-1-3 libasound2t64`).
Para aplicativos GTK, instale também PyGObject e GTK 4 da sua distribuição.

```bash
git clone https://github.com/RichardSpinola/makebench.git
cd makebench
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

A interface abre em inglês. Para usar português, vá em
**View › Preferences › Appearance › Interface language**, escolha
**Português (Brasil)** e abra o Makebench de novo. Na tela inicial, **Abrir
exemplo…** abre uma cópia de um exemplo; pressione **F5** para testá-lo. Os
exemplos em português ficam em [`examples`](examples) e os em inglês em
[`examples/en`](examples/en). O [guia de uso](docs/user-guide.pt-BR.md) apresenta
cada área.

## Modelo de segurança

Abrir, editar, pré-visualizar, salvar e construir um projeto **nunca executam o
código dele**. Seu Python e seus scripts só rodam quando você pressiona F5/F9 ou
inicia um aplicativo exportado, com as permissões do seu usuário. O processo de
teste separado mantém o editor responsivo, mas **não é uma sandbox** para projetos
desconhecidos: revise o código de terceiros antes de testar. Tarefas
administrativas usam Polkit (`pkexec`) e o diálogo de autenticação do sistema; o
Makebench nunca pede senhas. Veja [SECURITY.md](SECURITY.md).

## Limitações conhecidas

- Apenas Linux x86_64. Os pacotes nativos visam Ubuntu 24.04 (DEB) e Fedora 44
  (RPM) e exigem glibc 2.39 ou mais nova; outras distribuições não foram testadas.
- A assistência de código é estática (sem servidor de linguagem nem inferência de tipos).
- Salvar grava cada arquivo de forma atômica, mas não todos numa única transação.
- Pacotes Flatpak são isolados: programas do sistema e ações administrativas não
  ficam disponíveis dentro deles.
- A QA visual usou renderização por software e um compositor privado; nem toda
  GPU e todo compositor foram qualificados.

## Como foi feito

O Makebench foi escrito com a ajuda de assistentes de programação com IA, revisado e
testado pelo autor. **Não há IA dentro do programa**: nem o editor nem os aplicativos
que ele exporta chamam qualquer serviço de IA. A ideia é o contrário — programas
simples feitos por pessoas, com blocos e um pouco de Python, que qualquer um pode ler
e mudar.

## Licença

- O **editor** é software livre sob a [GNU GPL, versão 3 ou posterior](LICENSE).
- O **runtime** que vai dentro dos aplicativos que você exporta (`core`, `runtime`,
  `gtk_runtime`, `ui`, `terminal`, `portable`, `i18n.py` e as traduções), além dos
  modelos, exemplos e plugins oficiais, usa a [licença MIT](LICENSE-MIT). Assim, **você escolhe a
  licença dos seus próprios aplicativos**. Componentes de terceiros (Blockly,
PySide6/Qt, pyte, wcwidth) mantêm suas licenças; veja
[`src/makebench/notices/THIRD_PARTY.md`](src/makebench/notices/THIRD_PARTY.md).
