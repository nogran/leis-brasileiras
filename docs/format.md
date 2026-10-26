# Formato, proveniência e limites / Format, provenance and limits

## Contrato preservado

Cada JSON principal é uma lista de blocos. `id`, `lei`, `artigo`, `texto_limpo`,
`hash_artigo`, `parte_num` e `total_partes` preservam a saída do núcleo de origem.
Os nomes portugueses dos campos fazem parte do contrato e não foram traduzidos.

| Campos | Significado |
|---|---|
| `id`, `lei`, `artigo` | Identificador técnico, sigla do catálogo e rótulo do dispositivo; preservar exatamente |
| `versao`, `versao_consolidada` | Nome da norma e indicador do parser; não são uma determinação autônoma de vigência |
| `texto_limpo`, `hash_artigo` | Texto estruturado e hash legado de compatibilidade |
| `livro*`, `titulo*`, `subtitulo*`, `capitulo*`, `secao*`, `path_hierarquico` | Hierarquia, nomes e breadcrumb |
| `epigrafe` | Rubrica marginal capturada em CP/CLT; omitida nas demais fontes |
| `status` | Classificação observada: `vigente`, `revogado`, `vetado_total` |
| `vetos_parciais`, `alteracoes`, `referencias` | Metadados e remissões extraídos |
| `notas_legais`, `controle_constitucionalidade` | Notas da fonte e referências de controle constitucional |
| `parte_num`, `total_partes` | Inteiros para partes; nulos quando não multipartes |
| `url_fonte`, `data_extracao` | URL oficial e data da observação/extração, preservada no snapshot |

O `capture_id` da aplicação foi excluído: é uma chave estrangeira privada, não identidade
do dispositivo. Um adaptador privado deve inserir/reusar sua captura e atribuir esse ID
antes da ingestão. Não envie identificadores SHA-256 públicos ao campo UUID do banco.

`hash_artigo` mantém o algoritmo legado, inclusive particularidades das lápides. Não
o substitua por um hash do arquivo ou um hash de texto recomposto. SHA-256 nos manifestos
verifica bytes de artefatos; `content_hash` verifica UTF-8 do texto limpo completo.

## Multipartes e redações

O dedup de redações roda no artigo inteiro **antes** do corte. O corte preserva a
convenção `(Parte N/M)`, normalmente até 6.000 caracteres com overlap de 400; as guardas
do splitter evitam fatias minúsculas. Nada edita as partes depois do corte.
Não concatene partes cegamente: o overlap repetiria texto. Não traduza rótulos nem
remova `(ADCT)` ou o sufixo de parte para ingerir.

O sidecar `{base}_{data}_riscadas.json` tem `lei`, `versao`, `data_extracao`, `url_fonte`,
`total`, `riscadas`. Cada entrada registra `artigo_base`, `dispositivo`, `texto`,
`fonte_marcacao`, `hash`, `ordem`. Ele inclui riscos HTML/CSS, descartes do dedup de
redações e duplicatas por rótulo. **Nunca ingeri-lo como lista de artigos vigentes.**
Essas redações não constituem histórico completo de vigência: faltam textos originais,
intervalos de eficácia e emendas ausentes das páginas observadas.

## Distribuição

Captura nova: um diretório imutável com JSON principal, texto limpo, sidecar, HTML bruto
e `manifest.json`. O manifesto registra `format_version`, `captured_at` com fuso, fonte,
versões, hashes e tamanho de cada arquivo. O verificador rejeita arquivos extras,
symlinks, alterações de hash, mistura de leis e saída que não se reproduza do HTML.

Corpus novo: ZIP com uma captura validada de cada lei e manifesto raiz versionado.
Corpus de referência: ZIP plano produzido exclusivamente das fixtures selecionadas,
com `kind=historical-reference`, datas com precisão de dia e HTML bruto quando disponível.
As duas modalidades são explícitas; o builder histórico não afirma coleta atual.
Arquivos ZIP são escritos com ordem e timestamps determinísticos. Não extrair um ZIP
não confiável sem verificar caminhos, limites e hashes em um consumidor futuro.

## Fontes e limitações

Todas as URLs vêm de `src/leis_brasileiras/laws.yml`, sob HTTPS no Planalto. O catálogo
é instalado junto do pacote, sem caminhos relativos para repositórios privados.
O `docs/source-inventory.json` mede disponibilidade e hashes das referências.

| Caso | Tratamento e teste |
|---|---|
| UTF-16 sem BOM e padding corrompido | Decode determinístico e guardas NUL; testes de extração |
| Riscos `<strike>`, `<s>`, `<del>` e `line-through` inline | Removidos do texto observado, arquivados em sidecar; completude |
| Kerning que fatia palavras | Junção de spans; golden HTML |
| Anotações sem parêntese final | Remoção limitada à linha; regressão contra perda de parágrafo |
| Caput revogado, vetos e dispositivos órfãos | Literal da fonte ou lápides de `known_issues.json`; regressões dedicadas |
| Artigos duplicados, ANEXO e ADCT | Dedup com arquivo, boundaries por lei e integridade multiparte |
| Rubricas e cabeçalhos inline | Captura sem truncar texto; golden e testes de rubrica |

Limites: subseções não têm nível próprio; tabelas como imagem exigiriam outro pipeline;
seletores CSS de risco por classe não têm cobertura universal; notas legais são
deduplicadas por artigo e nem sempre localizam o inciso alterado. As exceções verificadas
em `known_issues.json` são parte da curadoria e devem ser revisadas, não ampliadas para
silenciar falhas. Nenhum resultado substitui a conferência da publicação oficial.

## English contract summary

Portuguese JSON field names and multipart identifiers are intentionally unchanged.
Observation date, parser status and legal effective date are different concepts.
Private application capture IDs are omitted and must be supplied by the consuming
adapter. Historical redaction sidecars must never be ingested as current articles.
Raw fixtures cover 14 laws; all 15 have frozen article and cleaned-text references.
Manifests distinguish fresh captures from historical references and hash exact bytes.
