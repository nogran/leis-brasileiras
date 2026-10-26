# Validação da proposta — 2026-10-26

Branch de trabalho: `codex/extraction-core`, baseada nos dois commits já existentes
do destino (base `0c5eace8a895a564008a1a9ff49bafd8716f4882`). Após a preparação local,
o dono autorizou a abertura do PR. A proposta incorpora o histórico revisado e os
arquivos novos em um commit de integração/adaptação, sem substituir os commits antigos.
O PR permanece em rascunho. Merge do PR, mudança de visibilidade e releases de pacote
ou corpus não fazem parte desta autorização.

## Resultados medidos

| Verificação | Resultado |
|---|---|
| Suíte completa independente | 631 passaram; nenhuma falha ou skip |
| Cobertura do pacote | 86,71%; piso do projeto elevado para 86% |
| Parser da origem versus pacote (AST) | 39 funções preservadas sem mudança estrutural |
| Comparação clean → JSON | 15 leis, igualdade dos campos públicos; `capture_id` excluído deliberadamente |
| HTML → clean e completude | 14 leis com HTML bruto disponível; nenhuma whitelist nova para LEP |
| Validação strict do corpus | 15 arquivos, 6.276 blocos, zero FAILs e zero WARNs; 29 INFOs, 3 INFOs conhecidos suprimidos |
| Integridade de arquivos e multipartes | Zero erros; 24 dispositivos multipartes em 54 partes |
| Manifesto do corpus | 59 hashes de artefatos conferidos |
| Empacotamento | Wheel e sdist construídos com sucesso |
| Instalação limpa | Venv de desenvolvimento e segundo venv somente com wheel/deps de runtime |
| Execução fora do checkout | Import via site-packages, catálogo de 15 leis, extração/verificação do CDC e validação das 15 leis |
| Dependências | `pip check` passou; runtime sem db/psycopg2/dotenv/OpenAI |
| Histórico selecionado | 64 commits e 175 blobs examinados, incluindo descompressão das fixtures; bundle verificado |
| Autoria histórica | Autor, committer e ambas as datas comparados para os 64 commits; preservados |
| Segurança da árvore atual | Scan dos arquivos selecionados, inclusive gzip; único match de URL com credencial era um exemplo sintético de rejeição no teste |
| Repositórios privados | Pipeline, backend e dados sem alterações de trabalho |

Ambiente executado: Windows, Python 3.14.3. CI preparada para Python 3.10 e 3.14 no
Linux; o resultado remoto deve ser conferido nos checks do PR, separadamente dos testes
locais registrados aqui. Suporte a 3.10 está declarado e as dependências fixadas são
compatíveis; a execução nessa versão cabe ao CI.
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
  Git e o perfil GitHub do dono. Atribuições históricas foram preservadas.
- Apenas o código, documentação e fixtures revisadas integram o PR. Wheel, sdist,
  corpus ZIP, logs e ferramentas privadas de migração não são enviados na branch.
- Merge do PR e publicação no PyPI ou em releases continuam fora do escopo.
- Integrar futuramente a Justina por versão definida e validar em ambiente de teste.
  A migração **não está completa** enquanto o extrator antigo continuar como dependência.

Commit da proposta: `feat(core): extract standalone Brazilian legislation package`.
