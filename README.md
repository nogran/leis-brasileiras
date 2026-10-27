# Leis Brasileiras

[English](README.en.md) · [Formato e fontes](docs/format.md) · [Transição](docs/transition.md) · [Licenciamento pendente](docs/licensing.md)

Extração de legislação brasileira de fontes oficiais, catálogo e validadores em Python.
O uso básico funciona sem banco de dados e sem chave de OpenAI. Este é um núcleo em
revisão: **não há pacote publicado nem servidor MCP nesta entrega**.

O catálogo contém **15 leis federais**, não toda a legislação brasileira. O corpus de
referência contém **6.276 blocos**, incluindo ementas, anexos e signatários, com capturas
registradas em julho/agosto de 2026. Há 24 dispositivos multipartes em 54 partes.
Esses números foram medidos nos artefatos, não representam cobertura nacional nem
garantem a vigência jurídica atual. [Inventário reproduzível](docs/source-inventory.json).

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

## Como rodar localmente

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

## Corpus versionado

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

## Testes

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

## Origem e transição

Derivado do núcleo legislativo do pipeline Justina. A seleção histórica preserva
autores, datas e atribuições; corpos de mensagens com contexto privado foram omitidos.
Veja [revisão do histórico](docs/history-review.json) e [plano de integração](docs/transition.md).
O extrator original continua ativo durante a transição; esta preparação não conclui a
migração da Justina. Melhorias futuras deverão ser feitas neste núcleo e consumidas
pela integração privada através de versões definidas.
