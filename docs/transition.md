# Migração do núcleo / Core transition

Status: proposta em revisão; Justina ainda depende do extrator antigo. Nenhum banco,
backend, schema, dado operacional, credencial, ingestion job ou modelo foi alterado.

## Fronteira e dependências

| Origem | Destino nesta preparação |
|---|---|
| `extrair_leis.py` (parsers e helpers) | `src/leis_brasileiras/extraction.py` |
| `laws.py`, `laws.yml` | `catalog.py`, `laws.yml` no pacote |
| `known_issues.json` | Recurso instalado junto do parser, preservado |
| `validar_leis.py`, `verificar_integridade.py` | `validation.py`, `integrity.py` |
| Testes de extração, catálogo, golden, conteúdo, epígrafe, normalização e multipartes | `tests/`, com imports do pacote e fixtures explícitas |
| Captura HTTP e persistência do extrator | Separadas em `transport.py` e `capture.py`; nenhuma implementação de banco migrou |
| Distribuição | `corpus.py`, CLI, `tools/build_reference.py`, manifestos e hashes |

Dependências de runtime: Requests, BeautifulSoup4 e PyYAML, com transitivas fixadas nos
locks. O parser utiliza `html.parser` da biblioteca padrão, portanto lxml não é necessário.
PostgreSQL, psycopg2, dotenv, OpenAI, embeddings, pipeline.py, geração de perguntas,
curadoria e jurisprudência permanecem na integração original. O backend real local é
`nogran-justina-backend`; referências antigas a `nogran-justina-api` não guiam alterações.

O repositório `nogranlabs/nogran-justina-data`, ainda chamado `nogran-justina-dados`
localmente, contém artefatos de coleta. Dele foram selecionados apenas os artefatos
legislativos da LEP de 2026-08-18. Não confundir esse armazenamento com o pipeline ou
com o destino público `nogran/leis-brasileiras`.

## Período de transição

Começa nesta preparação e termina apenas quando todos os gates abaixo forem aceitos.
O código antigo continua disponível e usado em produção; nenhuma cópia foi removida.
Mudanças no extrator devem nascer no pacote público. Durante a validação, qualquer fix
urgente no original precisa ser transportado para o núcleo e acompanhado por teste de
compatibilidade, evitando duas linhas permanentes de desenvolvimento.

1. **Revisar o PR em rascunho:** testes, corpus, histórico, licenças e limitações da coleta
   ao vivo. Abertura do PR autorizada pelo dono; merge do PR e releases continuam fora
   do escopo desta etapa. Uma branch pública de revisão não concede uma nova licença.
2. **Histórico incorporado à proposta:** os dois commits existentes do destino e os
   64 commits filtrados são ancestrais do commit novo de integração/adaptação. Nenhum
   force-push ou alteração de `main`. Histórico tem autores/committers/datas reais;
   corpos de mensagens privados foram omitidos, títulos e coautorias antigas preservados.
   A árvore final remove os seis caminhos antigos da raiz
   (`extrair_leis.py`, `laws.py`, `laws.yml`, `known_issues.json`, `validar_leis.py`,
   `verificar_integridade.py`) e os testes renomeados (`test_extrair_leis.py`,
   `test_validar_leis.py`, `test_normalizar.py`, `test_epigrafe.py`). Seus substitutos
   estão no pacote e nos testes em inglês; não há uma segunda implementação na árvore final.
3. **Fixar uma versão:** após licença e release aprovada, a dependência privada aponta
   para versão exata com hash de distribuição; nunca `main`, `latest` ou caminho relativo.
4. **Adaptador privado futuro:** `extrair_leis.py` vira uma fachada fina. Faz fetch,
   chama `html_to_clean_text`, compara seu `content_hash` no gate existente e chama o
   parser público. A integração privada continua gravando raw_captures em transação,
   anotando seu UUID `capture_id`, escrevendo handoff e coordenando ingestão. Evitar
   downloads duplos: passar os mesmos bytes capturados. Não implementar parser paralelo.
5. **Compatibilidade em ambiente de teste:** comparar todas as chaves, rótulos, texto,
   hashes, metadados, partes, sidecars e mapeamento `_to_record`; validar append-only,
   fechamento de versões, aposentadoria de rótulos, no-op por hash e falhas de transação.
   Congelar `capture_id` nos testes ou comparar separadamente; é a única exclusão
   deliberada da comparação pública atual.
6. **Consumidores Java:** conferir `RagResultAssembler`, `CitationChunks`,
   `ArticleLookupTool`, queries e fixtures de avaliação. O sufixo de parte e `(ADCT)`
   precisam continuar intactos. Nenhuma migration de `justina` é necessária para esta
   fronteira. Alterações descobertas exigem revisão explícita antes de ingestão.
7. **Cutover autorizado:** executar testes do pipeline e `mvn test`/checks do backend,
   reextrair e validar todas as leis, realizar piloto de ingestão em banco local e só
   então planejar rollout. Ingestão com embeddings e qualquer chamada paga exigem
   autorização separada. Rollback: fixar a versão anterior do pacote/fachada, preservando
   dados append-only. Retirar a implementação antiga apenas após equivalência confirmada.

## MCP posterior

Projetar `list_laws`, `get_article`, `search_legislation`, `get_law_metadata` sobre a
mesma distribuição validada, com consulta local somente leitura, inicialmente textual.
Antes da implementação: contrato de recomposição sem overlap duplicado, limites de
consulta/paginação, resultado com proveniência, resposta a corpus ausente/inválido,
isolamento de sessões e testes de prompt injection/exfiltração. Nenhum acesso ao banco
privado, atualização do corpus, execução de comandos ou rede arbitrária via ferramenta.
Não há stub MCP nesta entrega.

## English transition summary

The original extractor remains active. The public package becomes the single maintained
core only after a pinned-version private adapter passes full contract and multipart
compatibility checks. Database transactions, capture foreign keys, embeddings and
orchestration remain private. Existing destination commits and the separately prepared
64-commit history are retained as ancestors of the proposal branch. Opening the draft
PR was authorized separately; merging the PR and publishing releases remain out of scope.
MCP is a subsequent read-only consumer of the same validated corpus.
