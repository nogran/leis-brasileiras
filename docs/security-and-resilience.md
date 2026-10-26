# Entradas e falhas / Inputs and failures

O catálogo instalado é a única fonte de URLs do CLI. O transporte aceita apenas HTTPS
do Planalto em `/ccivil_03/`, sem credenciais, query ou fragmento. Redirecionamentos são
rejeitados. Toda resposta é HTML não confiável: não executar JavaScript, macros,
attachments ou handlers. A API pura não visita links contidos no HTML.

| Dependência/falha | Resposta e limite | Recuperação |
|---|---|---|
| DNS, conexão, timeout | Duas tentativas no máximo, backoff de 1s; conexão 10s/leitura 25s | Registrar sigla/tipo de erro e sair não zero |
| HTTP 4xx/5xx, redirect, MIME incorreto | Falha fechada, sem fallback para HTML de outro domínio | Conferir fonte/catalogação antes de tentar novamente |
| Corpo excessivo/lento | Limite de 16 MiB descomprimidos, deadline observado de 90s durante streaming | Recusar entrada; não truncar lei silenciosamente |
| Parser/estrutura inválida | Guardas de tamanho, NUL e ausência de artigos; validadores | Captura fica inelegível para release |
| Manifesto ou JSON adulterado | Tamanho máximo de 64 MiB por artefato, hashes, allowlist de arquivos, reparsing | Rejeitar; reconstruir a partir da captura íntegra |
| Escrita interrompida | Staging em diretório temporário; rename final; nunca sobrescrever captura existente | Nova execução em diretório novo |
| Fonte indisponível | Sem substituição por dado antigo no fluxo de captura nova | Referência histórica disponível em comando separado e identificada como tal |

O processo é batch e finito: não há worker infinito; o limite de tentativas serve como
interrupção local. Um serviço futuro deverá acrescentar circuit breaker compartilhado,
limites de concorrência e métricas. Timeouts de Requests não cancelam o resolvedor DNS
do sistema; o limite de tempo não é uma garantia de deadline de processo. Para serviço
remoto, isolar parsing/resolução em worker com deadline e limite de memória.

Cada fetch usa sessão própria, sem `.netrc`, proxies ambientais ou cookies herdados.
O cliente não conhece segredos da Justina. Logs do CLI mostram sigla e classe de erro,
sem corpos da resposta. A camada `transport.fetch_html` é substituível sem mexer nos
parsers, que recebem bytes; fixtures permitem validar o comportamento offline.

Os testes verificam injeção de instruções como dados, scripts inertes, URLs de
exfiltração, ação indevida, traversal em manifesto, volume, entradas malformadas e
independência entre capturas/sessões. O núcleo é uma biblioteca/CLI local, não um
serviço multiusuário; autenticação, autorização por usuário e quotas precisam ser
projetadas antes de expor uma API ou MCP remoto.

English: all external content is data, never authority or executable instructions.
Network and file inputs are bounded; failed or tampered captures are excluded from
release preparation. Session state is not shared across fetches. Remote service
isolation, authorization and hard process deadlines are explicitly future work.
