# Exportar

Quando o app funcionar com ++f5++, transforme-o em algo que outras pessoas
possam instalar. Escolha **Projeto › Exportar aplicativo…** (++ctrl+shift+e++).

Construir nunca executa o projeto: o Makebench só empacota os arquivos dele.

## 1. Para quem é?

A janela começa perguntando quem vai usar o app; cada resposta é um formato.

| Resposta | Formato | O que você recebe |
|---|---|---|
| **Qualquer pessoa no Linux** | AppImage | um arquivo que roda sem instalar |
| **Ubuntu, Debian ou Mint** | DEB | instala com entrada no menu (feito para Ubuntu 24.04 x86_64) |
| **Fedora ou openSUSE** | RPM | instala com entrada no menu (feito para Fedora 44 x86_64) |
| **Qualquer distribuição, isolado** | Flatpak | roda separado do sistema |
| **Programadores** | código-fonte Python | um ZIP com o código Python, para ler e mudar |

DEB, RPM e AppImage levam o Python e o toolkit dentro, então nada mais precisa
ser instalado. O Flatpak usa o runtime do GNOME para apps GTK e o do KDE para
apps Qt, e mantém o isolamento do Flatpak. O código-fonte Python precisa do
Python e do toolkit no computador de destino (o `README` dele explica como
rodar).

**Aplicativo…** edita o nome, o identificador, a versão, o ícone e o idioma do
app. Os mesmos ajustes estão em **Projeto › Configurações do aplicativo…**.

## 2. Verificação

**Verificar** procura problemas antes de construir: funções que faltam,
componentes que um toolkit não suporta, opções de janela que o GTK no Wayland
ignora, dependências grandes (como o Qt WebEngine) e parecidos. Corrija o que
ele apontar, ou construa mesmo assim se um aviso não importar para você.

## 3. Construção

**Construir com** escolhe as ferramentas:

- **Ferramentas preparadas pelo Makebench**: o Makebench baixa e prepara as
  ferramentas de construção em contêineres Podman sem root, guardadas em
  `~/.cache/makebench/builders`. Nada é instalado no seu sistema.
- **Ferramentas do sistema**: usa as ferramentas de empacotamento já
  instaladas.
- **Automático**: escolhe a que estiver pronta.

Preparar as ferramentas é sempre um passo separado (**Preparar ferramentas…**),
com a saída visível e um botão **Cancelar**. Depois clique em **Construir…** e
escolha onde salvar. **Mostrar detalhes** mostra o log completo; no fim,
**Abrir pasta** e **Copiar caminho** levam ao resultado.

**Exportar somente a receita** gera um ZIP com os arquivos de construção em vez
de um pacote, para construir em outro lugar.

## Qt, GTK ou app HTML leve

O toolkit é escolhido ao criar o projeto (**Aparência do aplicativo**) e pode
ser trocado nas configurações do aplicativo.

| | Qt | GTK 4 | App HTML leve |
|---|---|---|---|
| Aparência | igual em todo desktop | a aparência do GNOME (Adwaita) | uma página HTML numa janela GTK |
| O que o pacote leva | o próprio Qt (PySide6 Essentials) | usa o GTK do sistema | usa o WebKitGTK do sistema |
| Medido na *Oficina completa* | abre em cerca de 0,6 s, cerca de 125 MB | cerca de 2 s, cerca de 185 MB | — |

**App HTML leve** é um modelo em **Novo projeto**. Edite a página dele com o
plugin oficial **Visão web** (**Plugins › Editar página da Visão web…**, depois
de ligar o plugin). Uma janela com Visão web no **Qt** precisa do Qt
WebEngine, o que deixa o pacote bem maior; a verificação avisa.

## Opções de janela nos apps exportados

- **Tela cheia** abre a janela em tela cheia; nos apps Qt, ++f11++ alterna.
- **Centralizada** e **Sempre na frente** funcionam no Qt; o GTK 4 no Wayland
  as ignora, e a verificação avisa.
- Itens de menu podem ter um atalho depois de `|`, como `Salvar | Ctrl+S`; ele
  funciona no app exportado.

## O editor Makebench como AppImage

No campo **Exportar**, **Editor Makebench (AppImage)** constrói o próprio
editor, com os exemplos, como um AppImage. É assim que as versões são feitas.

## Licenças

O runtime que vai dentro do seu app usa a licença MIT, então você escolhe a
licença do seu app. As partes de terceiros (PySide6/Qt, GTK e outras) mantêm
as próprias licenças; o app exportado inclui os avisos delas.
