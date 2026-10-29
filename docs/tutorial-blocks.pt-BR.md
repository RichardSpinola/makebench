# Tutorial: seu primeiro app com blocos

Em uns quinze minutos você vai criar o **Minhas notas**: uma janela onde você
digita um título e um texto, salva a nota, vê todas as notas numa tabela e as
exporta para um arquivo CSV. O projeto pronto está em
**Arquivo › Abrir exemplo… › Minhas notas**, se quiser comparar.

Você vai usar as três áreas do editor: **Design** para a janela, o painel
**Dados** para as notas salvas e **Lógica** para o que os botões fazem.

## 1. Crie o projeto

1. Escolha **Arquivo › Novo projeto** (++ctrl+n++).
2. Em **Modelo**, escolha **Em branco** ("Uma janela para começar do seu jeito").
3. Em **Programar com**, escolha **Blocos**.
4. Em **Aparência do aplicativo**, mantenha **Qt — controles do desktop** (ou escolha GTK se tiver o
   GTK 4 instalado).
5. Dê o nome `Minhas notas` e confirme.

O Makebench abre a área **Design** com uma janela vazia.

## 2. Desenhe a janela

Ache cada componente no painel **Componentes** (digite na busca dele) e
arraste para a janela, de cima para baixo:

| Componente | O que ajustar em **Propriedades** |
|---|---|
| **Texto** | **Texto**: `Minhas notas` |
| **Campo de texto** | **Dica do campo**: `Título da nota` |
| **Texto longo** | **Dica do campo**: `Escreva aqui…` |
| **Botão** | **Texto**: `Adicionar nota` |
| **Botão** | **Texto**: `Exportar CSV` |
| **Tabela** | nada por enquanto |
| **Texto** | **Texto**: `Pronto.` |

!!! tip "Dê nomes a eles"
    Em **Avançado**, **Nome no código** dá ao componente um nome legível, como
    `title_input` ou `status`. Os blocos não precisam disso, mas o Ver Python e
    os projetos Python ficam mais fáceis de ler.

Quer os dois botões lado a lado? Solte antes um **Contêiner**, escolha
**Linha** na seção **Layout** dele e ponha os dois botões dentro.

## 3. Crie uma coleção para as notas

Uma *coleção* é como uma tabela de banco de dados: guarda os registros depois
que o app fecha.

1. Abra o painel **Dados** (**Exibir › Painéis › Dados**) e clique em
   **+ Coleção**.
2. **Nome**: `Notas`.
3. Clique duas vezes em **+ Campo** e preencha os campos:
    - `Título`, tipo **Texto**;
    - `Texto`, tipo **Texto**.
4. Salve. O primeiro campo de texto (`Título`) é o que dá nome a cada registro.

## 4. Mostre as notas quando o app abrir

1. Clique numa parte vazia da janela para selecioná-la. Em **Propriedades**,
   clique em **+ Ao iniciar**. A Lógica abre com um fluxo *Ao iniciar* vazio.
2. Da categoria **Registros**, arraste **mostrar registros de** para o fluxo.
   Escolha a tabela e a coleção `Notas`.

## 5. Salve uma nota

Volte ao **Design** (++ctrl+2++), selecione o botão **Adicionar nota** e
clique em **+ Ao clicar** em Propriedades. Depois monte este fluxo:

1. **se … então … senão …** (Condições).
2. Como condição, uma comparação **… + …** (Operações; escolha `=` no menu
   dela) entre **texto de** o campo do título (Interface e navegação) e um
   bloco **"texto"** vazio (Texto).
3. Em *então*: **alterar texto de** o texto de status para
   `Escreva um título antes.`
4. Em *senão*:
    1. **adicionar registro em** `Notas`, com **texto de** o campo do título
       para `Título` e **texto de** o texto longo para `Texto`;
    2. dois blocos **alterar texto de** que deixam o campo do título e o texto
       longo vazios;
    3. **mostrar registros de** a tabela e `Notas` de novo;
    4. **alterar texto de** o texto de status para `Nota salva.`

Clique em **Ver Python** na barra da Lógica para ver o código que esses blocos
geram. Ele é só leitura, e selecionar um bloco destaca a linha dele.

## 6. Exporte as notas

Selecione o botão **Exportar CSV**, clique em **+ Ao clicar** e adicione:

1. **perguntar … guardar em …** (Tarefas): escolha *arquivo para salvar*,
   encaixe um bloco **"texto"** com `Salvar as notas em` e digite `csv_path`
   depois de *guardar em*.
2. **exportar tabela** (Registros): escolha a tabela e encaixe **valor de …**
   (Variáveis e dados) com `csv_path`.

Se a pessoa cancelar a janela, o fluxo simplesmente para.

## 7. Teste

Aperte ++f5++ (**Executar › Testar aplicativo**). Digite um título e um texto,
clique em **Adicionar nota**, e a nota aparece na tabela. Feche o app e aperte
++f5++ de novo: as notas continuam lá.

Durante os testes, os registros vão para uma pasta de teste separada.
**Apagar dados de teste…** no painel Dados a esvazia.

Quando algo dá errado, abra a gaveta com ++ctrl+j++: **Ir ao erro** leva ao
bloco que falhou. ++f9++ inicia o depurador, que para nos pontos de parada
marcados pelo menu de cada bloco.

## 8. Exporte o app

Escolha **Projeto › Exportar aplicativo…** (++ctrl+shift+e++), diga para quem é
(por exemplo **Qualquer pessoa no Linux**, para um AppImage) e clique em
**Construir…**. Veja todos os formatos em [Exportar](export.md).

## Próximos passos

- Faça o mesmo com Python no [tutorial de Python](tutorial-python.md).
- Saiba mais sobre [dados e gráficos](data.md).
- Veja todos os blocos na [referência de blocos](reference/blocks.md).
