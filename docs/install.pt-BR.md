# Instalar

O Makebench roda em **Linux x86_64**. Tudo funciona sem internet: não há
conta, servidor nem IA durante o uso.

## AppImage (recomendado)

O AppImage é um único arquivo com o Makebench, o Python e o Qt dentro. Nada é
instalado no sistema.

1. Baixe `Makebench-<versão>-x86_64.AppImage` e `SHA256SUMS` da
   [página de versões](https://github.com/RichardSpinola/makebench/releases).
2. Confira o download e torne o arquivo executável:

    ```bash
    sha256sum -c SHA256SUMS --ignore-missing
    chmod +x Makebench-*-x86_64.AppImage
    ```

3. Execute:

    ```bash
    ./Makebench-*-x86_64.AppImage
    ```

!!! tip "Sistema sem FUSE?"
    AppImages normalmente se montam com FUSE. Sem ele, abra o arquivo com
    `--appimage-extract-and-run`.

O AppImage precisa de uma distribuição com glibc 2.39 ou mais nova (Ubuntu
24.04, Fedora 40 ou posterior e outras da mesma época).

## A partir do código-fonte

Você precisa do Python 3.12, 3.13 ou 3.14 e do Git. No Ubuntu, o Qt WebEngine
também precisa destas bibliotecas:

```bash
sudo apt install libegl1 libgl1 libxkbcommon0 libnss3 libdbus-1-3 libasound2t64
```

Depois:

```bash
git clone https://github.com/RichardSpinola/makebench.git
cd makebench
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

Tudo vai para a pasta `.venv`; nada é instalado no sistema. Para atualizar,
rode `git pull` e de novo a linha do `pip install`.

## Peças opcionais

| Para | Você precisa de |
|---|---|
| Projetos GTK 4 e a prévia fiel deles | GTK 4, PyGObject e `gtk4-broadwayd` da sua distribuição |
| Construir pacotes DEB, RPM, AppImage e Flatpak | Podman (sem root), para o Makebench preparar as ferramentas de construção; ou as ferramentas de empacotamento instaladas no sistema |
| Histórico de versões e cópias na nuvem | Git; `gh` conectado para criar repositórios no GitHub |
| Tarefas que precisam de administrador | Polkit (`pkexec`), presente na maioria dos desktops |

**Ajuda › Diagnóstico do ambiente…** mostra o que o Makebench encontrou e o que
falta.

## Idioma

A interface está em inglês ou português do Brasil. Troque em
**Exibir › Preferências… › Aparência › Idioma da interface**; vale na próxima
vez que o Makebench abrir.

## Próximos passos

- [Crie seu primeiro app com blocos](tutorial-blocks.md), ou o mesmo
  [com Python](tutorial-python.md).
- Abra um projeto pronto nos [exemplos](examples.md).
