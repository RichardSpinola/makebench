# Blocos locais

O editor incorporado está em src/makebench/web, para que também entre no pacote
Python. index.html, logic.js e style.css comunicam apenas dados pelo WebChannel;
nenhuma função da ponte executa Python ou comandos do sistema.

Blockly 13.4.0 foi obtido do pacote oficial npm blockly, com SHA-512 conferido.
O vendor-lock.json registra URL, integridade e licença Apache-2.0. Foram copiados
os bundles de núcleo/blocos, tradução pt-br e imagens/cursores; os sons estão
desativados e não são distribuídos. LICENSE e package.json originais foram mantidos.
Não há CDN, download em runtime nem dependência de Node para abrir o editor.

Atualizações precisam rever a API de serialização, a licença e os testes de
checks/blockly_smoke.py. Testar especialmente comentários de blocos e o
WorkspaceCommentSerializer explicitamente registrado para comentários soltos.
Preservar o modelo neutro e migrar versões antes de mudar o protocolo salvo.
