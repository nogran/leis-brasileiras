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

## Instalação local reproduzível

Python 3.10 ou superior. Execute a partir de uma cópia deste repositório:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock .
leis-brasileiras catalog
```

Os arquivos de lock fixam as versões verificadas; `pyproject.toml` declara os intervalos
compatíveis. A licença do código e dos elementos próprios do dataset ainda depende do
dono: disponibilidade do código não deve ser interpretada como licença concedida.

## Extração e validação

```bash
leis-brasileiras extract CDC --output corpus/captures
leis-brasileiras extract ALL --force --output corpus/captures
leis-brasileiras verify-capture corpus/captures/IDENTIFICADOR_DA_CAPTURA
leis-brasileiras validate PASTA_COM_JSONS_DE_ARTIGOS --strict
leis-brasileiras integrity PASTA_COM_JSONS_DE_ARTIGOS
leis-validate PASTA_COM_JSONS_DE_ARTIGOS --strict --no-color
```

Cada extração é nova e imutável; `--force` explicita essa intenção. A saída informa o
caminho de cada captura. O comando de extração retorna erro se qualquer lei falhar.
Falhas de rede, formato, integridade ou avisos impedem o selo de captura validada.
Uma captura gravada que reprove na validação permanece disponível para investigação,
mas o comando `bundle` a rejeita. Nunca execute o HTML coletado no navegador.

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

Para reproduzir a referência histórica revisada, usando somente fixtures legislativas:

```bash
python tools/build_reference.py --version reference-2026-08 --output dist/reference.zip
```

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
