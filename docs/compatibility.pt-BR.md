# Promessas de compatibilidade

O que fica estável, o que pode mudar e como o Makebench avisa.

## Arquivos de projeto

- Um arquivo de projeto registra uma **versão de formato**. O Makebench grava a
  versão **mais baixa** que comporta os recursos usados no projeto, então um
  projeto simples continua legível por versões mais antigas do Makebench.
- Todo formato antigo é lido pelas versões novas. Os formatos 1 a 3 são salvos
  como formato 4.
- Salvar um projeto num formato mais novo que o do arquivo guarda uma cópia ao
  lado (`nome.makebench.json.bak-v<antigo>`), para você poder voltar.
- Um arquivo de um Makebench **mais novo** nunca é aberto pela metade: o erro
  pede que você use uma versão compatível.
- `tests/test_compatibility_policy.py` confere essas promessas, inclusive que
  os exemplos distribuídos abrem e salvam sem mudanças.

## Plugins

- Um plugin declara a API de plugins para a qual foi escrito (`"api": N` no
  `plugin.json`).
- Cada versão lista as APIs que entende. Um plugin que cita outra API aparece
  como incompatível e o código dele **nunca é importado**.
- APIs antigas continuam suportadas por pelo menos uma versão menor depois que
  uma nova aparece; o changelog avisa quando uma é aposentada.
- Plugins rodam com as permissões do seu usuário e ficam desligados até você
  ligá-los.

## Temas

Um tema (`.mbtheme`) é só dados: cores. Ele não pode executar código.

## Apps exportados

Um app exportado leva o pequeno runtime com licença MIT de que precisa e não
depende do editor, então atualizar o Makebench nunca muda um app que você já
exportou.
