# Dúvidas e problemas

## Instalar e abrir

**O AppImage não abre.**
:   Torne-o executável (`chmod +x Makebench-*.AppImage`). Se o sistema não tem
    FUSE, rode com `--appimage-extract-and-run`. O AppImage precisa de glibc
    2.39 ou mais nova (Ubuntu 24.04, Fedora 40 e posteriores). Veja
    [Instalar](install.md).

**A prévia GTK ou os apps GTK não funcionam.**
:   Apps GTK precisam do GTK 4 e do PyGObject da sua distribuição; a prévia
    GTK no editor também precisa do `gtk4-broadwayd`. **Ajuda › Diagnóstico do
    ambiente…** lista o que existe e o que falta. Projetos Qt funcionam sem
    nada disso.

**Como mudo a interface para português?**
:   **Exibir › Preferências… › Aparência › Idioma da interface** e reabra o
    Makebench.

## Projetos e arquivos

**O Makebench pediu para atualizar meu projeto.**
:   Projetos feitos com um Makebench mais antigo abrem normalmente. Ao salvar,
    o arquivo passa para o formato atual e o anterior fica guardado ao lado
    como `<nome>.makebench.json.bak-vN` (N é o número do formato antigo). Um
    projeto feito por um Makebench mais novo é recusado com uma mensagem clara,
    em vez de ser estragado. Veja [Compatibilidade](compatibility.md).

**Editei o arquivo Python em outro editor.**
:   O Makebench percebe. Se você não tem mudanças não salvas, ele recarrega o
    arquivo; senão mostra *Funções alteradas fora do Makebench.* com
    **Recarregar arquivo** e **Manter minha versão**.

**Abrir um projeto ou exemplo executa o código dele?**
:   Não. Abrir, editar, ver a prévia, salvar e construir nunca executam o
    código do projeto. Só **Executar › Testar aplicativo** (++f5++) e
    **Depurar aplicativo** (++f9++) executam.

## Segurança

**O app que eu testo fica isolado do meu computador?**
:   Não. Testar executa a lógica, os programas e os scripts do projeto com as
    permissões do seu usuário, como qualquer programa que você abre. O
    Makebench mostra o que roda e deixa você parar, mas não é um sandbox. Só
    abra projetos em que você confia, como faria com um script. Apps Flatpak
    exportados rodam, sim, no isolamento do Flatpak.

**Um app pode pedir permissão de administrador?**
:   Só pelo Polkit, para as ações administrativas declaradas na lógica dele
    (**Projeto › Configurações do aplicativo… › Permissões** as lista). O
    sistema pede a senha na própria janela dele; o Makebench nunca pede nem vê
    senhas.

**Um plugin ou tema pode prejudicar meu computador?**
:   Temas são só cores e não executam código. Plugins são código Python que
    roda dentro do editor com as suas permissões; o Makebench lista o que cada
    um pede antes de você ligá-lo. Instale plugins só de fontes em que você
    confia. Veja [Escrever plugins](plugins.md).

## Dados

**Onde ficam os registros do meu app?**
:   Num arquivo SQLite. Apps exportados usam
    `~/.local/share/<id do app>/data.sqlite`; os testes no editor usam um banco
    separado, então testar nunca mexe nos dados de um app instalado. Veja
    [Dados e gráficos](data.md#onde-ficam-os-dados).

**Como começo de novo com dados de teste vazios?**
:   Clique em **Apagar dados de teste…** no painel Dados.

## Apps exportados

**Minha janela não fica centralizada (ou na frente) no GNOME.**
:   O GTK 4 no Wayland deixa o desktop posicionar as janelas, então
    **Centralizada** e **Sempre na frente** são ignoradas ali. Apps Qt as
    respeitam. A verificação da exportação avisa.

**Por que meu pacote Qt é tão grande?**
:   Um pacote Qt leva o próprio Qt. Uma janela com **Visão web** adiciona o Qt
    WebEngine, que é bem maior. Apps GTK usam o GTK do sistema, e o modelo
    **App HTML leve** usa o WebKitGTK do sistema. Veja [Exportar](export.md).

**Preciso usar a GPL no meu app?**
:   Não. O runtime dentro dos apps exportados é MIT, então você escolhe a
    licença do seu app. O editor em si é GPL-3.0-or-later.

## Ainda com problema?

Abra uma issue no
[GitHub](https://github.com/RichardSpinola/makebench/issues) com o que você
fez, o que aconteceu e o texto de **Ajuda › Diagnóstico do ambiente…**. Issues
podem ser escritas em português ou inglês.
