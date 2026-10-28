# Validação da proposta — atualização em 2026-10-27

Branch de trabalho: `codex/extraction-core`, baseada nos dois commits já existentes
do destino (base atual `8d732b3cc9609332de0d0d03ebb5ba3382c93d35`). Após a preparação local,
o dono autorizou a abertura do PR. A proposta incorpora o histórico revisado e os
arquivos novos em um commit de integração/adaptação, sem substituir os commits antigos.
O PR está aberto para revisão. Merge do PR, mudança de visibilidade e releases de pacote
ou corpus não fazem parte desta autorização.

## Incremento do corpus canônico

O escopo atual está restrito ao repositório público `leis-brasileiras`. A adaptação
dos repositórios privados da Justina será posterior. Os READMEs foram integrados
sobre o commit concorrente `37ceff1`, com autorização do dono, preservando o catálogo,
as perguntas frequentes e o exemplo JSON histórico.

O contrato `canonical-v1` preserva unidades inteiras e leituras ambíguas, separa
anotações editoriais e registra observação e revisões sem afirmar vigência jurídica.
`legacy-blocks-v1` mantém o contrato congelado das 15 leis; a divisão 6.000/400 pertence
somente à compatibilidade. Diagnósticos de RAG passam a ser opcionais e não bloqueiam
a aceitação do corpus. Não há servidor MCP implementado: somente contrato e decisões
de distribuição documentados.

JSON Schemas são conferidos em desenvolvimento/CI; o runtime aplica validação
estrutural e semântica sem resolução remota. A verificação de captura também reproduz
o documento a partir do HTML, rejeitando adulterações mesmo com hashes recalculados.

| Verificação do incremento | Resultado local (Windows, Python 3.14.3) |
|---|---|
| Suíte completa final | 713 testes passaram, sem falhas ou skips |
| Cobertura | 87,79%; piso de 86% preservado |
| Compatibilidade | 15 leis reproduzem os registros congelados; 6.276 registros |
| Inventário | 23 grupos multipartes em 54 partes; 21 artigos em 47 partes, mais anexo e signatários |
| Corpus canônico histórico | 15 normas, 6.231 unidades e 12 identidades ambíguas explicitadas |
| Reprodutibilidade | ZIP canônico final idêntico byte a byte em duas construções; 59 hashes de artefatos e schema do manifesto conferidos em cada formato |
| Contratos | JSON Schemas dos documentos e manifestos; rejeição de estruturas malformadas mesmo com hashes recalculados |
| Capturas | Reprodução a partir do HTML, seleção explícita de subconjuntos e limites de entrada |
| Isolamento editorial | Metadados das ocorrências não compartilham objetos mutáveis com o legado; nota editorial do Art. 555 da CLT permanece separada |
| Documentação | Links locais, 15 linhas de catálogo por README, exemplo histórico do CDC e sintaxe Python conferidos |
| Empacotamento | Wheel/sdist; schemas incluídos; instalação fora do checkout; captura/validação/bundle parcial nos dois formatos; `pip check` aprovado |

A medição final foi executada com o código estabilizado. Uma medição intermediária,
durante edição do parser, passou nos testes mas reprovou em cobertura; foi descartada
e substituída pela execução completa acima. Resultados anteriores de AST descrevem
a extração inicial: o parser agora inclui o ponto de emissão das ocorrências canônicas
e o splitter histórico foi movido para o módulo de compatibilidade.

A coleta `extract ALL --force --format canonical-v1` foi tentada em 2026-10-27:
as 15 normas retornaram `ConnectionError` e o comando encerrou com código 1.
Nenhuma captura atual bem-sucedida foi produzida. O gate de coleta ao vivo continua
pendente, independentemente dos resultados offline.

## Resultados da preparação inicial (formato histórico)

| Verificação | Resultado |
|---|---|
| Suíte completa independente | 631 passaram; nenhuma falha ou skip |
| Cobertura do pacote | 86,71%; piso do projeto elevado para 86% |
| Parser da origem versus pacote (AST) | 39 funções preservadas sem mudança estrutural |
| Comparação clean → JSON | 15 leis, igualdade dos campos públicos; `capture_id` excluído deliberadamente |
| HTML → clean e completude | 14 leis com HTML bruto disponível; nenhuma whitelist nova para LEP |
| Validação strict do corpus | 15 arquivos, 6.276 blocos, zero FAILs e zero WARNs; 29 INFOs, 3 INFOs conhecidos suprimidos |
| Integridade de arquivos e multipartes | Zero erros; 23 grupos multipartes em 54 partes (contagem corrigida pelo inventário reproduzível) |
| Manifesto do corpus | 59 hashes de artefatos conferidos |
| Empacotamento | Wheel e sdist construídos com sucesso |
| Instalação limpa | Venv de desenvolvimento e segundo venv somente com wheel/deps de runtime |
| Execução fora do checkout | Import via site-packages, catálogo de 15 leis, extração/verificação do CDC e validação das 15 leis |
| Dependências | `pip check` passou; runtime sem db/psycopg2/dotenv/OpenAI |
| Histórico selecionado | 64 commits e 175 blobs examinados, incluindo descompressão das fixtures; bundle verificado |
| Autoria histórica | Autor, committer e ambas as datas comparados para os 64 commits; preservados |
| Padronização em 2026-10-27 | 69 mensagens padronizadas; 42 coautorias de provedor removidas; todas as árvores, autores humanos, committers e datas preservados |
| Segurança da árvore atual | Scan dos arquivos selecionados, inclusive gzip; único match de URL com credencial era um exemplo sintético de rejeição no teste |
| Repositórios privados | Pipeline, backend e dados sem alterações de trabalho |

Ambiente executado: Windows, Python 3.14.3. Em 2026-10-27, o dono definiu Python 3.14
como padrão do projeto: requisito mínimo `>=3.14` no pacote e uma única versão (3.14)
no CI Linux. Os resultados remotos devem ser conferidos nos checks do PR, separadamente
dos testes locais registrados aqui. O lock de desenvolvimento permanece fixado em
`coverage==7.16.2`, já validado com Python 3.14; não é necessário atualizar dependências
para alterar a política de suporte. Python 3.10 e 3.11 não fazem parte dessa política.
O CI Linux também revelou uma seleção ambígua de fixture no teste de integridade:
o glob podia retornar o sidecar de trechos riscados antes do JSON de artigos. O teste
agora seleciona explicitamente o snapshot congelado do CDC, sem depender da ordem
de arquivos do sistema operacional.
O piso de cobertura do projeto de origem não foi alterado.

A fixture de texto limpo da LEP continha 884 finais de linha CRLF; a nova fixture de
comparação HTML normaliza somente CRLF → LF. O texto e os registros extraídos continuam
iguais ao contrato congelado. O corpus foi preparado sem IDs operacionais de captura.

## Coleta ao vivo: pendência de validação

`extract ALL --force` tentou as 15 fontes oficiais e terminou com falha de conexão em
todas. A investigação adicional com Requests e curl do Windows confirmou timeout de
resposta do Planalto. A tentativa de alternativa no WSL falhou ao montar o disco da
distribuição (`ERROR_PATH_NOT_FOUND`); isso descreve aquela execução, não ausência
geral de configuração da máquina. Nenhum ajuste de rede/WSL foi realizado.

Portanto **a reextração atual de todas as leis ainda não foi concluída**. A validação
offline reproduz a referência histórica, não comprova coleta atual nem cobertura de
mudanças posteriores da fonte. L9099 ainda não possui HTML bruto na referência.
Antes de aprovar o PR ou publicar uma release, repetir a coleta completa em ambiente com acesso à fonte,
validar saída strict, completude e multipartes, investigar qualquer divergência.

## Histórico e publicação

Fonte do código: `e243ec4bf91aead633cc0427adb76b3ecbc19458` do pipeline. Destino: dois
commits existentes preservados. O bundle completo revisado foi incorporado à branch
da proposta, com mapa em `history-review.json`. O commit novo tem como pais a base do
destino e a ponta do histórico filtrado: os 64 commits continuam navegáveis, sem um
import achatado. Não houve merge na branch principal. Mensagens originais continuam
no repositório privado; os corpos foram
omitidos na seleção pública por conterem contexto de atendimento/operação interna.

Em 2026-10-27, o dono solicitou remover as coautorias de provedor de IA e padronizar
todas as mensagens. Os 69 commits foram revisados para títulos em inglês no formato
`tipo(escopo): descrição`, com até 72 caracteres, sem os corpos repetitivos de
sanitização. Os hashes mudaram também nos dois commits iniciais de `main`, cujo
conteúdo permaneceu idêntico. O mapa de origem em `history-review.json` foi atualizado.
O histórico do pipeline privado permanece intacto. A suíte local foi repetida:
631 testes passaram, cobertura de 86,71%, e o corpus de 15 leis/6.276 blocos foi
validado novamente sem erros. A reescrita foi verificada commit a commit.

O scan por padrões não é uma prova absoluta de inexistência de segredos. Não foram
encontradas chaves privadas, tokens de provedor, URLs reais com credenciais ou atribuições
de segredo na seleção histórica; matches de endereço eram datas legislativas.
Referências técnicas genéricas ao pipeline foram mantidas como contexto histórico;
implementações privadas, dados operacionais, dumps e credenciais ficaram fora.

## Decisões e próximos gates

- Aprovar licença do código próprio e tratamento dos elementos próprios do dataset;
  nenhuma licença foi criada por presunção.
- Concluir a coleta atual/validação das 15 leis e obter fixture HTML de L9099.
- Conferir o diff e os checks do PR; autoria do commit novo confirmada com a identidade
  Git e o perfil GitHub do dono. Autores humanos e datas históricas foram preservados.
- Apenas o código, documentação e fixtures revisadas integram o PR. Wheel, sdist,
  corpus ZIP, logs e ferramentas privadas de migração não são enviados na branch.
- Merge do PR e publicação no PyPI ou em releases continuam fora do escopo.
- Integrar futuramente a Justina por versão definida e validar em ambiente de teste.
  A migração **não está completa** enquanto o extrator antigo continuar como dependência.

Commit inicial da proposta: `feat(core): extract standalone Brazilian legislation package`.

## Jurisprudence validation

Run `python -m pytest -q --cov=leis_brasileiras --cov-report=term`. The 86% floor
remains in place. The new suites cover all six parsers, source replay, schemas,
source identities, observed situation, dated evidence, individual judgments,
archive reproducibility, hostile text, SSRF, command payloads, malformed/oversized
input, cross-call state, tampering and PDF isolation. Unit network/scanner doubles
do not prove live-source availability or antivirus installation.

State parser fixtures contain real PDF excerpts and scanned extracted text; the
PDF worker test exercises the child on a real excerpt with the scan gate mocked.
Actual historical reprocessing uses the real scanner via
`tools/build_jurisprudence_reference.py`; live captures are a separate validation.
See [jurisprudence](jurisprudence.md).

### Jurisprudence incorporation — verified 2026-10-28

- Windows, Python 3.14.3: full suite **952 tests passed**, zero failures/skips.
  After the final aggregate PDF-text guard, all **240 jurisprudence regressions**
  passed, including its new abuse case; the 713 legislative tests remain unchanged.
- Coverage: **89.62%**, above the unchanged 86% gate. Measurement combines the full
  suite with final regressions; prior line mappings for amended modules were removed
  before remeasurement. Logs, JUnit and coverage JSON are local under `dist/`.
- Six historical sources reproduced **4,631 identities**, with no differences in
  thesis, summary, submitted question, update-note or cancellation-note text against
  the existing source projections. All four historical state PDFs passed real
  Windows Defender scans and isolated page extraction.
- Live captures observed on 2026-10-27/28: STJ precedents **2,369**, STJ summaries
  **676**, STF theses **1,292**, STF binding summaries **63**, TJPE summaries **172**,
  TJMG summaries **91**: **4,663 records**. Five STJ records have no type in the CSV
  and retain that uncertainty under their official sequential source identities.
- The six-source live archive was replay-verified and reproduced byte for byte:
  SHA-256 `af7a39e03132dd8a1f8e92a867a464730f979d2bc8ac51cf7b354f12cb147d57`.
- The 15-law inventory and both legislative archive formats validated successfully;
  historical legislative export remains **6,276 records**.
- Wheel/sdist built; packaged code/catalogs/schemas matched the checkout. A clean
  installation using isolated Python passed `pip check`, both catalogs, schema
  discovery, document validation and source replay without importing the checkout.
- GitHub Actions now exercises the added suites and installed jurisprudence catalog.
  Remote CI was not run in this local implementation. The PDF worker was exercised
  on Windows; a supplemental local Linux run could not start because the registered
  Ubuntu WSL distributions' virtual disks were unavailable. This does not describe
  the configuration of other WSL distributions or the developer's IDE.
- No consumer migration, database write, embedding request, package release or
  production deployment was performed. Licensing and MCP implementation remain
  separate pending work.
