# Jurisprudência: extração, evidência e corpus público

O pacote contém uma biblioteca e comandos de CLI para seis fontes oficiais. O corpus
de jurisprudência usa `observed-jurisprudence-v1`, com núcleo de observação
compartilhado com `observed-law-v1`. A integração não exige banco de dados, embeddings,
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

Cada `extract` captura os endpoints previstos de uma fonte; isso não certifica
completude estrutural. Os comandos devolvem JSON e código zero
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

O contrato é `observed-jurisprudence-v1`, com `source-observation-v1` compartilhado
com legislação. A identidade usa coleção + número oficial; no CSV do STJ, usa
`sequencialPrecedente`. Ausência de identificação mantém um localizador técnico
explicitamente não classificado. Duplicatas conservam ocorrências separadas.

Cada ocorrência referencia o registro original e sua localização. CSV preserva
todas as colunas/células; JSON, todos os campos; HTML, elementos e textos; PDF,
todas as páginas extraídas e intervalos de texto. Nada é preenchido com explicação
jurídica nossa. Registro sem tese continua sem tese; questão submetida permanece
no campo original. Situação não informada é nula, vigência é desconhecida e datas
sem adaptador próprio permanecem literais, sem interpretação temporal.

As marcações de cancelamento são menções com localização, não status inferido.
O índice de súmulas vinculantes do STF fica vinculado ao detalhe correspondente.
Notas oficiais e atributos desconhecidos permanecem na evidência. A seleção de um
texto vigente não faz parte do parser. Veja [semântica e hashes](format.md).

Os schemas atuais são `jurisprudence.schema.json`,
`jurisprudence-capture.schema.json` e `jurisprudence-corpus.schema.json`.
A validação Python acrescenta invariantes e a reprodução da captura é obrigatória.
`complete=false` identifica as pendências de limites dos registros, campos, tabelas
e transcrição PDF. As contagens históricas acima não são metas que validam o parser.

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
python -m tools.build_jurisprudence_reference --raw-root /path/to/raw \
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
incorporação. As fixtures antigas permanecem, mas a geração pública de formatos legados foi desativada.
A migração de consumidores terá seu próprio contrato e validação de compatibilidade.

O contrato do futuro MCP inclui consulta de jurisprudência. O servidor MCP e a busca
continuam planejados, sem implementação nesta entrega. O licenciamento do código e
dos elementos próprios do corpus continua [em revisão](licensing.md); a inclusão de
fontes judiciais não concede uma licença por presunção.

Referências técnicas: [extração de texto do pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
e [índice oficial de súmulas vinculantes](https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26).
