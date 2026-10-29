# Aparência e temas

Há duas coisas separadas para estilizar:

- **o editor**, com temas de cores (arquivos `.mbtheme`);
- **seus apps**, com a aparência de cada janela e o estilo de cada componente.

Um tema do editor nunca muda seus apps, e vice-versa.

## Temas do editor

Escolha **Plugins › Temas…**. A janela lista:

- temas **Embutidos**: o padrão, sóbrio e compacto, e **Cores do sistema**,
  que usa a paleta do seu sistema como outros apps do KDE ou do GNOME;
- temas **Oficiais**: Catppuccin, Dracula, Gruvbox, Nord e Solarized;
- **Seus**: os temas que você criou ou importou.

Escolha um e clique em **Aplicar**. O botão claro/escuro da barra de status
escolhe qual metade do tema é usada.

![O editor no modo escuro](images/design-dark.png)

### Criando um tema

Clique em **Novo tema…**, dê um nome e escolha as cores de cada superfície
(**Fundo**, **Barras**, **Painéis**, **Linhas**, **Botões**, **Texto**,
**Texto fraco** e o **Destaque**) para o escuro e o claro. Uma prévia mostra o
resultado. Temas embutidos e oficiais não podem ser alterados; crie um novo a
partir deles.

**Exportar .mbtheme…** salva um tema para compartilhar; **Importar…** adiciona
um que você recebeu. Seus temas ficam em `~/.local/share/makebench/themes/`
(**Abrir pasta de temas**).

### O formato `.mbtheme`

Um tema é um pequeno arquivo JSON:

```json
{
  "format": "mbtheme",
  "version": 1,
  "name": "Nord",
  "about": "An arctic, north-bluish palette, calm and clean.",
  "accent": "#5e81ac",
  "dark": {
    "win": "#2e3440", "side": "#292e39", "base": "#242933", "line": "#434c5e",
    "btn": "#3b4252", "btnLine": "#4c566a", "fg": "#d8dee9", "mut": "#a5adbd"
  },
  "light": {
    "win": "#e5e9f0", "side": "#d8dee9", "base": "#eceff4", "line": "#c2cad6",
    "btn": "#eceff4", "btnLine": "#b3bccb", "fg": "#2e3440", "mut": "#4c566a"
  }
}
```

| Chave | Significado |
|---|---|
| `format`, `version` | sempre `"mbtheme"` e `1` |
| `name` | até 60 caracteres |
| `about` | opcional, até 200 caracteres |
| `accent` | a cor de destaque |
| `win` | fundo da janela |
| `side` | barras |
| `base` | painéis |
| `line` | linhas e bordas |
| `btn`, `btnLine` | preenchimento e borda dos botões |
| `fg`, `mut` | texto normal e texto fraco |

Toda cor é `#rrggbb`, e tanto `dark` quanto `light` precisam das oito chaves.
Um tema é só cores: não pode executar código. Arquivos maiores que 64 KB são
recusados.

## A aparência de uma janela

Selecione uma janela (clique numa parte vazia dela no Design) e abra
**Aparência da janela** em Propriedades:

- **Tema**: **Sistema**, **Claro** ou **Escuro**;
- **Cor de destaque** e **Cor de fundo**;
- **Imagem de fundo**: **Escolher imagem de fundo…** copia a imagem para a
  pasta `assets/` do projeto e a desenha atrás dos controles.
  **Trocar imagem de fundo…** e **Remover imagem de fundo** fazem o que dizem.

Cada janela tem a sua aparência, então um projeto pode misturar uma janela
principal escura com uma caixa de diálogo clara.

## Estilo dos componentes

Todo componente tem uma seção **Estilo** em Propriedades:

| Ajuste | Valores |
|---|---|
| **Cor do texto** | qualquer cor |
| **Cor de preenchimento** | qualquer cor |
| **Tamanho da fonte (pt)** | 0 mantém o padrão, até 96 |
| **Cantos arredondados (px)** | até 48 |
| **Negrito**, **Itálico** | ligado ou desligado |

Os estilos funcionam em apps Qt e GTK.

**Editar › Copiar estilo** (++ctrl+alt+c++) copia o estilo do componente
selecionado; **Editar › Colar estilo** (++ctrl+alt+v++) o aplica a todos os
componentes selecionados, num só passo de desfazer.

## Mudando a aparência com o app rodando

| Bloco | Python | Faz |
|---|---|---|
| **mudar tema da janela para … destaque …** | `ctx.set_theme("dark", "#e66100")` | muda a janela atual para `system`, `light` ou `dark`, com um destaque opcional |
| **mudar fundo da janela para …** | `ctx.set_background("#1e1e2e")` | pinta o fundo da janela; `""` restaura |

Por exemplo, uma caixa de seleção *Modo escuro*:

```python
def on_modo_escuro_change(ctx):
    ctx.set_theme("dark" if ctx.read("dark_mode", "checked") else "system")
```

## Peças reutilizáveis

Um grupo de componentes estilizados pode virar uma **peça reutilizável**:
clique com o botão direito num componente da árvore de componentes e escolha
**Salvar como peça reutilizável…**, ou use o menu Editar.
**Editar › Inserir peça** insere uma cópia independente; **Gerenciar peças…**
renomeia, exporta e importa. O Makebench vem com algumas peças, como uma
*Barra OK / Cancelar*, um *Formulário de login* e um *Cabeçalho de tela*.
