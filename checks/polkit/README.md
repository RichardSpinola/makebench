# Teste descartável de Polkit real

Não executar smoke.py ou cancel_agent.py diretamente no host. Estes arquivos
só pertencem ao contêiner de teste: criam uma regra local e um agente que sempre
cancela, exclusivos do usuário descartável tester e do programa /usr/bin/id.

```bash
podman build -t localhost/makebench-polkit-test:local -f checks/polkit/Containerfile checks/polkit
podman run --rm --network none --pids-limit 256 localhost/makebench-polkit-test:local
podman image rm localhost/makebench-polkit-test:local
```

Usar Podman rootless, sem --privileged e sem montar diretórios do host. O build
instala dependências apenas na imagem. O teste não usa senha nem altera regras,
pacotes ou serviços do host. id -u comprova privilégio somente no namespace do
contêiner. Resultados esperados: autorizado 0/uid 0; recusado 127; agente cancela
126. O agente gráfico real do usuário não faz parte deste teste.

Resultado local: três casos passaram em Fedora 44 com Polkit 127, Python 3.14.8.
Testes do supervisor Qt, sem elevação, ficam em tests/test_runtime.py.
