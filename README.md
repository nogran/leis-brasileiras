# Leis Brasileiras — legislação brasileira em JSON com Python

[English](README.en.md) · [Formato e fontes](docs/format.md) · [Validação](docs/validation.md) · [Transição](docs/transition.md) · [Licenciamento pendente](docs/licensing.md)

**Leis Brasileiras** é um projeto Python para extrair e validar textos de **15 normas
federais brasileiras** a partir de fontes oficiais do Planalto. Gera arquivos JSON e
um corpus versionado com fontes, datas de captura e verificações de integridade,
para pesquisa, processamento de linguagem natural (NLP) e preparação de bases para
RAG jurídico — geração aumentada por recuperação.

Destina-se a desenvolvedores de legaltech, pesquisadores e equipes que precisam
transformar legislação brasileira em dados estruturados. O uso básico funciona sem
banco de dados, Docker ou chave de OpenAI.

**Estado do projeto:** núcleo de extração em revisão no [PR #1](https://github.com/nogran/leis-brasileiras/pull/1).
Não há pacote ou corpus publicado em releases, API hospedada ou servidor MCP nesta
entrega. O licenciamento está pendente; consulte os [termos atuais](docs/licensing.md).

## Casos de uso: JSON, pesquisa e RAG jurídico

- **Legislação brasileira em JSON:** extrair textos do Planalto com identificação
  dos dispositivos, hierarquia, fonte e data de observação.
- **Corpus para NLP jurídico:** preparar uma referência reproduzível para análise
  textual e experimentos, preservando os limites da cobertura e das datas.
- **Dados para RAG jurídico:** fornecer textos e metadados a um sistema de recuperação
  externo. O pacote não gera embeddings, não oferece busca vetorial e não responde
  perguntas com LLMs.
- **Validação de capturas:** verificar formato, hashes e integridade, inclusive de
  artigos divididos em partes, antes de integrar os dados a outro sistema.

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

## Exemplo de legislação em JSON

Campos selecionados de um registro real do CDC na
[fixture histórica de 7 de julho de 2026](tests/fixtures/baseline/cdc_2026-07-07.json.gz).
O JSON de uma lei contém uma lista de blocos; este objeto é apenas um deles, com
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
leis-brasileiras extract CDC --output corpus/captures
```

Em caso de sucesso, a saída inclui `law`, `capture` (o caminho da pasta criada) e
`status: "validated"`. Essa pasta contém o JSON dos dispositivos, o texto limpo,
as redações riscadas em arquivo separado, o HTML de origem e `manifest.json` com a
proveniência e os hashes. Os arquivos ficam no seu computador.

Para extrair todas as leis do catálogo:

```bash
leis-brasileiras extract ALL --force --output corpus/captures
```

### 4. Conferir a captura

Substitua `CAMINHO_DA_CAPTURA` pelo valor de `capture` retornado na extração. Use a pasta
daquela captura, e não a pasta geral `corpus/captures`:

```bash
leis-brasileiras verify-capture "CAMINHO_DA_CAPTURA"
leis-brasileiras validate "CAMINHO_DA_CAPTURA" --strict
leis-brasileiras integrity "CAMINHO_DA_CAPTURA"
```

`verify-capture` confere o conjunto da captura, incluindo hashes e reprodução a partir
do HTML; `validate` verifica os JSONs de artigos; `integrity` verifica a integridade dos
dados, incluindo artigos divididos em partes. Consulte as opções com:

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
)
print(capture.articles[0]["artigo"])
```

`extract_html` não realiza rede nem persistência. Ela recebe HTML como dado e devolve
artigos, texto limpo e redações arquivadas. `write_capture` é o adaptador de filesystem;
uma integração de banco pode consumir o mesmo resultado sem duplicar o parser.

## Corpus jurídico brasileiro versionado

Prepare uma release local nova passando **explicitamente uma captura validada por lei**:

```bash
leis-brasileiras bundle CAMINHO_CF88 CAMINHO_CDC OUTRAS_13_CAPTURAS --version 2026-10-26.1 --output dist/corpus.zip
```

Para experimentar **sem acessar as fontes externas após a instalação**, reproduza a
referência histórica revisada usando as fixtures legislativas incluídas no repositório:

```bash
python tools/build_reference.py --version reference-2026-08 --output dist/reference.zip
```

O resultado é `dist/reference.zip`. Ele contém os dados históricos de referência,
não uma extração atual. O destino deve ser novo; para repetir, escolha outro nome de ZIP.

Os ZIPs incluem manifesto, hashes SHA-256, fontes, datas, versão do pacote e versão do
parser. A referência histórica explicita a precisão das datas e a ausência do HTML
bruto de L9099. Prefira anexar corpus volumosos a releases após aprovação; os comandos
acima **não publicam** nada. Não copie diretórios privados de dados para o repositório.

## Qualidade, atualização e limites

O corpus de referência contém **6.276 blocos**, incluindo ementas, anexos e signatários,
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
- **Artigos multipartes:** preserve os identificadores e trate o overlap ao recompor
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
servidor Model Context Protocol (MCP). Uma interface MCP somente leitura está
prevista no [plano de transição](docs/transition.md).

### Posso usar o corpus em uma aplicação de IA?

Os textos e metadados podem servir de entrada técnica para uma integração de NLP ou
RAG. O consumidor deve preservar fontes, datas e artigos multipartes e tratar todo
texto recuperado como dado não confiável, nunca como instrução de sistema. Consulte
[segurança](docs/security-and-resilience.md) e resolva o licenciamento antes de adotar
ou redistribuir código e elementos próprios do dataset.

### Qual é a licença?

O licenciamento está pendente de decisão do titular. A disponibilidade pública do
repositório não concede uma licença ao código ou aos elementos próprios do dataset.
Veja a [revisão de licenciamento](docs/licensing.md).

## Relação com a Justina

A **Justina** é uma assistente de inteligência artificial para consulta à legislação
brasileira pelo WhatsApp. Conheça o projeto em **[www.justina.com.br](https://www.justina.com.br)**.

Sua base de consulta é construída a partir de textos legislativos extraídos de fontes
oficiais, organizados e validados pelo pipeline de dados. Ao receber uma pergunta, a
Justina busca trechos relevantes dessa base para fundamentar a resposta — uma abordagem
conhecida como RAG (geração aumentada por recuperação).

O **Leis Brasileiras** nasceu desse trabalho de extração. Este repositório reúne o núcleo
de extração e validação e os recursos para gerar um corpus versionado, com identificação
das fontes e das datas de captura. A integração da Justina com este pacote está em
transição; o extrator original continua ativo. Veja o [plano de integração](docs/transition.md).

## Testes e contribuição

```bash
python -m pip install -r requirements-dev.lock .
python -m pytest -q --cov=leis_brasileiras
python tools/build_reference.py --version test-reference --output dist/test-reference.zip
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
O extrator original continua ativo durante a transição; esta preparação não conclui a
migração da Justina. Melhorias futuras deverão ser feitas neste núcleo e consumidas
pela integração privada através de versões definidas.
