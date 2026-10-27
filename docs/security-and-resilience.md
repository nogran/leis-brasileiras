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
O cliente não lê credenciais de aplicações consumidoras. Logs do CLI mostram sigla e classe de erro,
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

## Canonical corpus and future MCP

Canonical documents are bounded to 64 MiB, 50,000 units and structural depth 32.
Canonical capture verification also reparses the bounded 16 MiB raw HTML and compares
the complete result; self-consistent hashes alone are not source authentication.
Repeated readings remain explicit ambiguities; editorial assertions are separately
marked as pending review and never establish effective dates. There are no network
lookups for annotations, document identifiers or JSON schemas. Unknown source URLs
are rejected against the packaged catalog. Invalid documents return bounded errors.

The current CLI/library is not a multiuser service. Its independent capture state tests
do not establish future HTTP authorization. See [MCP contract](mcp-contract.md) for the
separate server threat model and release gates. No untrusted ZIP importer or PDF pipeline
is introduced; collected HTML is parsed as data and never opened for execution.
