# Leis Brasileiras — legislação brasileira em JSON com Python

[English](README.en.md) · [Formato e fontes](docs/format.md) · [Validação](docs/validation.md) · [Transição](docs/transition.md) · [Licenciamento pendente](docs/licensing.md)

**Leis Brasileiras** é um projeto Python para extrair e validar textos de **15 normas
federais brasileiras** a partir de fontes oficiais do Planalto. Gera arquivos JSON e
um corpus versionado com fontes, datas de captura e verificações de integridade,
para pesquisa e consulta de textos legislativos. O objetivo do projeto é oferecer
um **servidor MCP para consulta estruturada e busca textual em legislação brasileira**,
com identificação de dispositivos, fontes oficiais e corpus versionado.

Destina-se a desenvolvedores de legaltech, pesquisadores e equipes que precisam
transformar legislação brasileira em dados estruturados. O uso básico funciona sem
banco de dados, Docker ou chave de OpenAI.

**Estado do projeto:** núcleo de extração em revisão no [PR #1](https://github.com/nogran/leis-brasileiras/pull/1).
Não há pacote ou corpus publicado em releases, API hospedada ou servidor MCP nesta
entrega. O licenciamento está pendente; consulte os [termos atuais](docs/licensing.md).

## Casos de uso: dados estruturados e pesquisa legislativa

- **Legislação brasileira em JSON:** extrair textos do Planalto com identificação
  dos dispositivos, hierarquia, fonte e data de observação.
- **Corpus para NLP jurídico:** preparar uma referência reproduzível para análise
  textual e experimentos, preservando os limites da cobertura e das datas.
- **Consulta via MCP, planejada:** localizar normas, consultar artigos identificados
  e pesquisar palavras ou expressões em uma versão explícita do corpus.
- **Validação de capturas:** verificar formato, hashes e integridade, inclusive de
  artigos divididos em partes, antes de integrar os dados a outro sistema.

## MCP planejado: consulta estruturada e busca textual

O servidor Model Context Protocol (MCP) será uma interface de consulta somente leitura
sobre o corpus validado. **Ainda não está implementado nesta entrega.** O escopo
aprovado para a primeira versão é:

| Capacidade planejada | Exemplo de consulta |
|---|---|
| Consultar o catálogo por identificação da norma | Quais normas estão disponíveis? Onde está a Lei 8.078/1990? |
| Recuperar um dispositivo identificado | Mostre o artigo 18 do CDC |
| Buscar palavras ou expressões, com filtros e paginação | Busque “dados pessoais sensíveis” na LGPD |
| Consultar metadados e proveniência | Qual é a fonte, a data de observação e a versão desse texto? |

Cada resultado deverá identificar a norma, o dispositivo quando aplicável, a fonte
oficial, a data de observação e a versão do corpus. Ausência de cobertura, identidades
ambíguas e granularidade não suportada deverão ser informadas explicitamente. Consulta
individual a parágrafos e incisos depende de extração e identificação próprias,
ainda não disponíveis; o servidor não deverá inferir essa estrutura.

A paginação limita o texto devolvido por chamada; não define chunks de RAG nem overlap
no corpus. Embeddings, busca vetorial, chunking por tamanho ou tokens e estratégias
de RAG ficam sob responsabilidade dos consumidores, incluindo a Justina privada.
O MCP planejado fornece textos e metadados; a interpretação da pergunta e a geração
da resposta ficam com a aplicação de IA que o utiliza. Os comandos de extração e
atualização do corpus permanecem separados das ferramentas de consulta.

## Legislação coberta e fontes oficiais

O catálogo cobre as normas abaixo, não toda a legislação brasileira. Esta tabela é
uma apresentação derivada de [`laws.yml`](src/leis_brasileiras/laws.yml), a fonte de
verdade do catálogo; os links apontam para as páginas oficiais utilizadas pelo extrator.

| Sigla na CLI | Norma | Identificação e fonte no Planalto |
|---|---|---|
| `CF88` | Constituição Federal de 1988 | [Constituição Federal 1988](https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm) |
| `CDC` | Código de Defesa do Consumidor | [Lei 8.078/1990](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm) |
| `CLT` | Consolidação das Leis do Trabalho | [Decreto-Lei 5.452/1943](https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm) |
| `CC` | Código Civil | [Lei 10.406/2002](https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm) |
| `CPC` | Código de Processo Civil | [Lei 13.105/2015](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/L13105compilada.htm) |
| `CP` | Código Penal | [Decreto-Lei 2.848/1940](https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm) |
| `LGPD` | Lei Geral de Proteção de Dados | [Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709compilado.htm) |
| `ECA` | Estatuto da Criança e do Adolescente | [Lei 8.069/1990](https://www.planalto.gov.br/ccivil_03/leis/L8069Compilado.htm) |
| `LI` | Lei do Inquilinato | [Lei 8.245/1991](https://www.planalto.gov.br/ccivil_03/leis/L8245compilado.htm) |
| `LMP` | Lei Maria da Penha | [Lei 11.340/2006](https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm) |
| `LC123` | Estatuto Nacional da Microempresa e da Empresa de Pequeno Porte | [Lei Complementar 123/2006](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) |
| `LT` | Lei do Trabalho Temporário e Terceirização | [Lei 6.019/1974](https://www.planalto.gov.br/ccivil_03/leis/l6019compilado.htm) |
| `CADPOS` | Lei do Cadastro Positivo | [Lei 12.414/2011](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12414.htm) |
| `L9099` | Lei dos Juizados Especiais Cíveis e Criminais | [Lei 9.099/1995](https://www.planalto.gov.br/ccivil_03/leis/l9099.htm) |
| `LEP` | Lei de Execução Penal | [Lei 7.210/1984](https://www.planalto.gov.br/ccivil_03/leis/l7210compilado.htm) |

## Formatos públicos

`canonical-v1` representa unidades legislativas inteiras, sem divisão por tamanho ou
overlap. Mantém identidade pública, ordem, hierarquia observada, leituras da fonte,
proveniência e anotações editoriais separadas. Identidades ambíguas conservam todas as
leituras, sem eleger um texto vigente. A granularidade atual é de artigo; incisos e
parágrafos ainda não têm identidade própria. Veja a [arquitetura](docs/architecture.md).

`legacy-blocks-v1` preserva o contrato histórico, incluindo partes e overlap. Continua
sendo o padrão da API/CLI para compatibilidade; os exemplos novos abaixo selecionam
explicitamente `canonical-v1`. Estratégias de RAG pertencem aos consumidores.

## Exemplo do JSON histórico de compatibilidade

Campos selecionados de um registro real do CDC na
[fixture histórica de 7 de julho de 2026](tests/fixtures/baseline/cdc_2026-07-07.json.gz).
Neste formato histórico, o JSON de uma lei contém uma lista de blocos; este objeto é apenas um deles, com
campos adicionais omitidos para facilitar a leitura.

```json
{
  "lei": "CDC",
  "artigo": "Art. 1",
  "texto_limpo": "Art. 1° O presente código estabelece normas de proteção e defesa do consumidor, de ordem pública e interesse social, nos termos dos arts. 5°, inciso XXXII, 170, inciso V, da Constituição Federal e art. 48 de suas Disposições Transitórias.",
  "url_fonte": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
  "data_extracao": "2026-07-07",
  "parte_num": null,
  "total_partes": null
}
```

`lei` e `artigo` identificam o dispositivo; `texto_limpo` contém o texto extraído;
`url_fonte` e `data_extracao` registram a origem e a observação. Valores nulos em
`parte_num` e `total_partes` indicam que este bloco não foi dividido. A data do
exemplo é histórica e não atesta a vigência atual. Veja o [contrato completo](docs/format.md).

## Início rápido: extrair leis do Planalto

Você precisa de **Git e Python 3.14 ou superior**. A instalação baixa dependências e a
extração consulta as fontes oficiais pela internet. O uso básico não exige PostgreSQL,
Docker nem chave de OpenAI.

### 1. Obter o código

O núcleo descrito aqui está na branch de revisão `codex/extraction-core`:

```bash
git clone --branch codex/extraction-core https://github.com/nogran/leis-brasileiras.git
cd leis-brasileiras
```

Se você já tem essa branch no computador, entre na pasta existente.

### 2. Criar o ambiente e instalar

**Windows (PowerShell):** os comandos abaixo usam o ambiente diretamente, sem precisar
ativar scripts no shell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock .
.\.venv\Scripts\leis-brasileiras.exe catalog
```

**Linux/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock .
leis-brasileiras catalog
```

O comando `catalog` lista as siglas aceitas e suas fontes. Nos exemplos seguintes,
no PowerShell substitua `leis-brasileiras` por `.\.venv\Scripts\leis-brasileiras.exe`
e `python` por `.\.venv\Scripts\python.exe`. No Linux/macOS, mantenha o ambiente ativado.

Os arquivos de lock fixam as versões verificadas; `pyproject.toml` declara os intervalos
compatíveis. A licença do código e dos elementos próprios do dataset ainda depende do
dono: disponibilidade do código não deve ser interpretada como licença concedida.

### 3. Extrair uma lei

Comece pelo Código de Defesa do Consumidor (`CDC`):

```bash
leis-brasileiras extract CDC --format canonical-v1 --output corpus/captures
```

Em caso de sucesso, a saída inclui `law`, `capture` (o caminho da pasta criada) e
`status: "validated"`. Essa pasta contém `canonical.json`, `clean.txt`, `source.html`
e `manifest.json`. Redações riscadas observadas ficam no documento canônico, separadas
das unidades. O manifesto registra proveniência e hashes. Os arquivos ficam no seu computador.

Para extrair todas as leis do catálogo:

```bash
leis-brasileiras extract ALL --force --format canonical-v1 --output corpus/captures
```

### 4. Conferir a captura

Substitua `CAMINHO_DA_CAPTURA` pelo valor de `capture` retornado na extração. Use a pasta
daquela captura, e não a pasta geral `corpus/captures`:

```bash
leis-brasileiras verify-capture "CAMINHO_DA_CAPTURA"
leis-brasileiras validate "CAMINHO_DA_CAPTURA" --format canonical-v1
```

`verify-capture` confere o conjunto da captura, incluindo hashes e reprodução a partir
do HTML; `validate --format canonical-v1` verifica identidades, relações, leituras e
revisões do documento. `integrity` atende somente ao formato histórico. Consulte as opções com:

```bash
leis-brasileiras --help
leis-brasileiras extract --help
```

Cada extração é nova e imutável; `--force` explicita essa intenção. A saída informa o
caminho de cada captura. O comando de extração retorna erro se qualquer lei falhar.
Falhas de rede, formato, integridade ou avisos impedem o selo de captura validada.
Uma captura gravada que reprove na validação permanece disponível para investigação,
mas o comando `bundle` a rejeita. Nunca execute o HTML coletado no navegador.

### Uso em Python

```python
from pathlib import Path
from leis_brasileiras.capture import extract_html

capture = extract_html(
    Path("captura-oficial.html").read_bytes(),
    law="CDC",
    captured_at="2026-07-07T12:00:00-03:00",  # use o horário real da sua captura
    format="canonical-v1",
)
print(capture.canonical["units"][0]["id"])
```

`extract_html` não realiza rede nem persistência. Ela recebe HTML como dado e devolve
o documento em `capture.canonical`, texto limpo e HTML original. `write_capture` é o adaptador de filesystem;
uma integração de banco pode consumir o mesmo resultado sem duplicar o parser.

## Corpus jurídico brasileiro versionado

Prepare uma release local nova passando **explicitamente uma captura validada por lei**:

```bash
leis-brasileiras bundle CAMINHO_CF88 CAMINHO_CDC OUTRAS_13_CAPTURAS --version 2026-10-26.1 --output dist/corpus.zip
```

Um subconjunto exige seleção explícita, registrada no manifesto:

```bash
leis-brasileiras bundle CAMINHO_CDC --laws CDC --version 2026-10-27.1 --output dist/cdc.zip
```

Não misture formatos no mesmo corpus.

Para experimentar **sem acessar as fontes externas após a instalação**, reproduza a
referência histórica revisada usando as fixtures legislativas incluídas no repositório:

```bash
python tools/build_reference.py --format canonical-v1 --version reference-2026-08 --output dist/reference.zip
```

O resultado é `dist/reference.zip`. Ele contém os dados históricos de referência,
não uma extração atual. O destino deve ser novo; para repetir, escolha outro nome de ZIP.

Os ZIPs incluem manifesto, hashes SHA-256, fontes, datas, versão do pacote e versão do
parser. A referência histórica explicita a precisão das datas e a ausência do HTML
bruto de L9099. Prefira anexar corpus volumosos a releases após aprovação; os comandos
acima **não publicam** nada. Não copie diretórios privados de dados para o repositório.

## Qualidade, atualização e limites

O corpus histórico de compatibilidade contém **6.276 blocos**, incluindo ementas, anexos e signatários,
com capturas registradas em julho/agosto de 2026. Há **23 grupos multipartes em
54 partes**, incluindo anexo e signatários. Os 6.276 blocos não correspondem a
artigos únicos; consulte o
[inventário reproduzível](docs/source-inventory.json).

- **Proveniência:** manifestos registram fontes, datas, versões do parser e hashes.
  Capturas novas e a referência histórica são distribuições distintas.
- **Atualização:** uma nova extração consulta o Planalto; não há atualização automática.
  A coleta atual das 15 normas ainda está pendente por falhas de conexão registradas
  na [validação da proposta](docs/validation.md). Os testes offline não comprovam
  acesso atual às fontes.
- **Cobertura histórica:** 14 normas têm HTML bruto nas fixtures; L9099 possui texto
  limpo e JSON. Redações riscadas ficam separadas e não formam um histórico completo
  de vigência.
- **Compatibilidade multipartes:** no formato histórico, preserve os identificadores e trate o overlap ao recompor
  o texto; concatenar as partes diretamente repete trechos. Veja [formato e limites](docs/format.md).
- **Significado da validação:** `validated` descreve verificações técnicas da captura.
  Data de coleta, status observado pelo parser e vigência jurídica são conceitos
  distintos. Os dados não substituem a conferência da publicação oficial.

## Perguntas frequentes

### Posso baixar um dataset pronto de leis brasileiras?

Ainda não há release publicada do corpus. Após instalar o projeto, você pode gerar
localmente o ZIP histórico com `tools/build_reference.py`, como mostrado acima,
ou preparar um corpus a partir de capturas novas validadas.

### Preciso de OpenAI, PostgreSQL ou Docker?

Não. O núcleo usa Python 3.14+ e as dependências declaradas no projeto. A instalação
baixa dependências; a extração de textos atuais precisa de acesso às fontes oficiais.
A construção da referência histórica funciona offline após a instalação.

### Existe API de legislação brasileira ou servidor MCP?

Esta entrega oferece biblioteca Python e CLI. Não oferece API HTTP hospedada nem
servidor Model Context Protocol (MCP). A consulta estruturada e a busca textual
somente leitura descritas acima estão
previstas no [contrato MCP proposto](docs/mcp-contract.md), ainda sem implementação.

### Posso usar o corpus em uma aplicação de IA?

Sim. O projeto fornece dados legislativos; cada consumidor define sua aplicação,
inclusive estratégias de RAG, embeddings e chunks quando necessários. Preserve as
identidades, fontes e datas; respeite as convenções do formato consumido, incluindo
partes no contrato histórico. Trate texto recuperado como dado não confiável, nunca
como instrução de sistema. Consulte
[segurança](docs/security-and-resilience.md) e resolva o licenciamento antes de adotar
ou redistribuir código e elementos próprios do dataset.

### Qual é a licença?

O licenciamento está pendente de decisão do titular. A disponibilidade pública do
repositório não concede uma licença ao código ou aos elementos próprios do dataset.
Veja a [revisão de licenciamento](docs/licensing.md).

## Relação com a Justina

A **Justina** é uma assistente de inteligência artificial para consulta à legislação
brasileira pelo WhatsApp. Conheça o projeto em **[www.justina.com.br](https://www.justina.com.br)**.

O **Leis Brasileiras** nasceu desse trabalho de extração. Este repositório reúne o núcleo
legislativo público, independente das políticas de RAG e da infraestrutura da Justina.
A adaptação dos repositórios privados será uma etapa posterior à conclusão deste
núcleo público. Veja o [plano de transição](docs/transition.md).

## Testes e contribuição

```bash
python -m pip install -r requirements-dev.lock .
python -m pytest -q --cov=leis_brasileiras
python tools/build_inventory.py --check
python tools/build_reference.py --version test-reference --output dist/test-reference.zip
python tools/build_reference.py --format canonical-v1 --version test-reference --output dist/test-canonical.zip
python -m build
```

A suíte compara os JSONs das 15 leis, verifica completude do HTML das 14 fontes com
captura disponível e testa numeração, overlap, duplicatas e tamanho das partes. Testes
de abuso cobrem URLs externas, tentativa de exfiltração, conteúdo ativo, instruções
maliciosas tratadas como texto, entradas malformadas, volume e isolamento de capturas.
Não há chamadas pagas nem acesso ao banco nos testes.

Para contribuir, descreva o problema ou a melhoria em uma
[issue](https://github.com/nogran/leis-brasileiras/issues), indicando a norma, a fonte
e como reproduzir o caso. Em mudanças de extração, preserve os identificadores e
acrescente uma regressão com os testes pertinentes. Não envie dados pessoais,
credenciais ou capturas de sistemas privados.

## Origem e transição

Derivado do núcleo legislativo do pipeline Justina. A seleção histórica preserva
autores, datas e atribuições; corpos de mensagens com contexto privado foram omitidos.
Veja [revisão do histórico](docs/history-review.json) e [plano de integração](docs/transition.md).
Esta entrega não altera os repositórios privados nem conclui a migração da Justina.
