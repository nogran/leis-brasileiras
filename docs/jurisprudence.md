# Jurisprudência: extração, evidência e corpus público

O pacote contém uma biblioteca e comandos de CLI para seis fontes oficiais. O corpus
de jurisprudência usa `jurisprudence-v1`, separado dos formatos legislativos
`canonical-v1` e `legacy-blocks-v1`. A integração não exige banco de dados, embeddings,
OpenAI, credenciais da Justina ou importação de repositórios privados.

## Cobertura

| Identificador | Conteúdo | Referência histórica |
|---|---|---|
| `stj_temas` | Temas repetitivos, controvérsias, IAC, PUIL e SIRDR; inclui registros sem tese | 2.347 registros, 20/07/2026 |
| `stj_sumulas` | Súmulas, inclusive canceladas | 676 registros, 21/07/2026 |
| `stf_teses_rg` | Listas com e sem tese de repercussão geral | 1.284 registros, 21/07/2026 |
| `stf_sumulas_vinculantes` | Índice e enunciados das súmulas vinculantes | 63 registros, 21/07/2026 |
| `tjpe_sumulas` | Livros oficiais de súmulas do tribunal | 172 registros, 17/08/2026 |
| `tjmg_sumulas` | PDF consolidado de enunciados do tribunal | 89 registros, 17/08/2026 |

São 4.631 registros na referência histórica. Essas contagens não comprovam a
quantidade ou situação atual dos entendimentos. Os pisos impedem substituição
silenciosa por captura menor; uma remoção legítima exige revisão do catálogo.
As URLs, contagens por tipo/situação e data do inventário ficam em
`src/leis_brasileiras/jurisprudence/sources.json`.

O endpoint JSON do STF é uma interface interna do portal, sem contrato público
de estabilidade. O parser verifica sua estrutura e interrompe a captura se ela mudar.

## Comandos

```bash
leis-brasileiras jurisprudence catalog
leis-brasileiras jurisprudence extract stj_temas --output corpus/jurisprudence
leis-brasileiras jurisprudence extract tjmg_sumulas --output corpus/jurisprudence
leis-brasileiras jurisprudence validate CAPTURE/document.json
leis-brasileiras jurisprudence verify-capture CAPTURE
leis-brasileiras jurisprudence bundle CAPTURE --sources stj_temas \
  --version 2026-10-27 --output dist/stj-temas.zip
```

Cada `extract` coleta uma fonte completa. Os comandos devolvem JSON e código zero
somente quando a operação termina; falhas devolvem código 1 e diagnóstico sem corpo
remoto, credenciais ou caminhos internos. `validate` verifica estrutura e consistência;
`verify-capture` também reproduz o documento a partir dos bytes capturados.

Sem `--sources`, o bundle exige as seis fontes. Subconjuntos devem ser explícitos.
Capturas de teste com `coverage=sample` exigem `--allow-samples` e mantêm essa marca
no manifesto. A opção não transforma uma amostra em fonte completa.

PDFs exigem ClamAV (`clamscan` no PATH) ou Windows Defender. Pode-se indicar o
executável com `--scanner`; falha, infecção ou indisponibilidade bloqueiam o PDF.
O parser usa `pypdf`, sem OCR, após quarentena e verificação antimalware. Extrai
página a página em processo separado: 24 MiB de entrada, 300 páginas, 768 MiB de
memória, 60 segundos e 16 MiB de texto por PDF, com teto agregado de 32 MiB de texto
por captura. Conteúdo ativo, anexos, macros e JavaScript
nunca são executados. O isolamento de processo e recursos não é um sandbox de rede
do sistema operacional.

Links HTTP para PDFs do mesmo host e caminho oficial são convertidos para HTTPS
antes da primeira requisição; o índice bruto preserva o link observado. Não há
requisição HTTP nem acompanhamento de redirecionamento. TLS permanece obrigatório. Se um portal não fornecer a cadeia completa, um bundle
de CAs previamente revisado pode ser indicado com `--ca-bundle`; não existe opção
para desligar a verificação. Proxy, `.netrc` e credenciais ambientais não são herdados.

## Modelo e limites semânticos

A identidade pública é `br:<tribunal>:<tipo>:<numero>`. Cada registro mantém o texto,
URL oficial, data de observação e sua precisão, hash SHA-256 do conteúdo e a projeção
completa do parser em `source_record`. Os nomes portugueses dessa projeção e dos
parsers portados foram preservados para rastrear a regressão; a interface pública
canônica usa campos em inglês. Novas capturas usam instante UTC; referências antigas
conhecidas apenas por dia não recebem um horário inventado.

`has_thesis=false` preserva registros sem tese. `text` pode conter a questão submetida
em vez de uma tese; consumidores devem observar `has_thesis` e o tipo de registro.
Quando o CSV do STJ não informa o tipo, ele permanece nulo. O registro usa a
identidade oficial `sequencialPrecedente` em `br:stj:source-record:<sequencial>`,
sem presumir que seja tema repetitivo ou outro precedente. Ausência também desse
identificador interrompe a validação. Duplicidades conflitantes interrompem a validação. O CSV do STJ agrega somente os
vínculos multivalorados já reconhecidos, sem escolher arbitrariamente um texto.

`situation` representa a classificação observada ou produzida pelo parser;
`situation_basis` declara essa origem e `legal_validity` permanece `unknown`.
Um `em_vigor` herdado do parser não comprova vigência atual. O parser de súmulas
vinculantes deixou de presumir que todas estão vigentes: ausência de marcador retorna
situação desconhecida; cancelamento explícito no título ou no link correspondente
do índice é preservado. Isso não atribui uma data de cancelamento desconhecida.

`status_observation`, quando fornecido, precisa vincular tribunal, tipo, número,
hash da versão, situação, instante de verificação, fonte e hash da evidência.
Validação estrutural dessa declaração não autentica o autor nem substitui revisão
jurídica ou consulta atual à fonte.

Os JSON Schemas empacotados são `jurisprudence.schema.json`,
`jurisprudence-capture.schema.json` e `jurisprudence-corpus.schema.json`.
As invariantes semânticas são verificadas adicionalmente pelo código Python.

## Capturas e arquivos

Cada diretório de captura contém `document.json`, `capture.json` e `raw/NNN.ext`.
O manifesto vincula cada resposta à requisição oficial, tamanho e hash. A verificação
recusa caminhos externos, arquivos inesperados, links simbólicos, campos duplicados,
alterações de metadados e documentos que não sejam reproduzidos pelas fontes.
Falhas acontecem antes da publicação do diretório; arquivos existentes não são
sobrescritos. Um ZIP é determinístico para o mesmo conjunto de capturas e versão.
Hashes detectam adulteração em relação à evidência fornecida; não são assinatura do tribunal.

Para reproduzir o acervo histórico com os arquivos originais explicitamente fornecidos:

```bash
python tools/build_jurisprudence_reference.py --raw-root /path/to/raw \
  --version historical-reference --output dist/jurisprudence-reference.zip
```

O layout é `stj-temas/2026-07-20`, `stj-sumulas/2026-07-21`,
`stf-teses/2026-07-21`, `stf-sumulas-vinculantes/2026-07-21`,
`tjpe-sumulas/2026-08-17` e `tjmg-sumulas/2026-08-17`. O adaptador documenta os nomes
dos arquivos em `tools/build_jurisprudence_reference.py`. Esse comando não acessa
a rede e mantém o mesmo scanner e verificador usados pelas capturas novas.

## Acórdãos individuais

`leis-brasileiras jurisprudence validate-decision RECORD.json [--require-review]`
valida o contrato existente de um acórdão identificado: identidade oficial do
documento, processo, fatos, questão, conclusão, limites, órgão, julgamento, fonte
e evidência. A revisão, quando exigida, é vinculada ao hash exato do conteúdo e da
evidência. Trata-se de validação de um registro fornecido, sem coleta em massa,
inferência de precedente vinculante ou inclusão automática nos seis datasets.

## Consumidores, MCP e licenciamento

O backend, a ingestão, os embeddings e o banco da Justina não são alterados por esta
incorporação. Os formatos legislativos e seus artigos multipartes são preservados.
A migração de consumidores terá seu próprio contrato e validação de compatibilidade.

O contrato do futuro MCP inclui consulta de jurisprudência. O servidor MCP e a busca
continuam planejados, sem implementação nesta entrega. O licenciamento do código e
dos elementos próprios do corpus continua [em revisão](licensing.md); a inclusão de
fontes judiciais não concede uma licença por presunção.

Referências técnicas: [extração de texto do pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
e [índice oficial de súmulas vinculantes](https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26).
