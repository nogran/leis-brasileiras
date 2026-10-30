# Validação da consolidação — 2026-10-29

A correção introduz `observed-law-v1` e `observed-jurisprudence-v1`, sem exportação
de lápides ou anotações editoriais. Os critérios atuais são preservação rastreável,
reprodução da captura, reconciliação independente e limites explícitos. O
[registro de validação anterior](archive/validation-2026-10-27.md) foi preservado
como histórico; suas afirmações sobre os formatos antigos não validam esta entrega.

## Resultados da consolidação anterior (PR #6)

Windows, Python 3.14.3, dependências do lock; importação conferida na worktree isolada.

| Verificação | Resultado |
|---|---|
| Suíte completa, após resumo do inventário | 951 passaram, sem falhas ou skips |
| Cobertura | 89,12%; piso de 86% mantido |
| Wheel e sdist | Construídos como 0.2.0.dev1; wheel instalado em ambiente novo fora do repo, catálogos e schema/extrator verificados |
| Inventário e READMEs | Regeneração determinística e `--check` aprovado |
| Arquivo legislativo | Duas construções idênticas; SHA-256 `c09f69f54e9ed5214c95e14ccb4ae2d568f944c56fa798aaaee904004beab492` |
| 15 normas históricas | Referências preservadas e validadas; 14 com HTML, L9099 apenas derivado |
| CF88 | Censo e estrutura: 276 identidades principais + 148 ADCT; 13 omissões confirmadas recuperadas |
| Seis fontes judiciais históricas | Replay integral aprovado; PDFs passaram pelo scan e extrator isolado |
| Arquivo de jurisprudência | Reproduzido byte a byte; SHA-256 `0a998a5985223b492c733974b015956c79dbe72f4a491851f3af622efd9dee85` |
| Intervenções históricas | 15 lápides e oito overrides inventariados; excluídos da nova exportação |

A regressão de rótulo `Art. 40 - Aos servidores` evita interpretar o início do texto
como sufixo `40-A`. A fonte histórica permanece inalterada. As contagens são
recalculadas, não corrigidas manualmente nos READMEs.

## Resultados deste incremento (2026-10-30)

Windows, Python 3.14.3, dependências do lock, no checkout público de
`leis-brasileiras`. A pasta aninhada não faz parte do commit. Nenhuma fixture
HTML foi regravada.

| Verificação | Resultado |
|---|---|
| Suíte completa | 965 passaram, sem falhas ou skips |
| Cobertura | 89,25%; piso de 86% mantido |
| Inventário | `--check` aprovado; relatório completo gerado em `dist/` |
| Arquivo legislativo | `complete=false`; SHA-256 `ca4357c7c63dd156715eed594a67efd19b4a81ca3b23215d2d8ed9f796a8dcfb` com `--version ci-reference` |
| CP | 432 identidades e 434 ocorrências; rótulos 187–196 com as notas oficiais; nove rubricas entram no artigo seguinte |

As outras 14 normas mantêm as contagens de candidatos, artigos e ocorrências.
Mudam a revisão do parser (`observed-legislation@3`) e o método do censo
(`stdlib-htmlparser-block-break-labels@2`), então o hash de reconciliação de
cada norma também muda. Isso não certifica completude.

## O que a validação não certifica

Todas as fontes continuam com `complete=false`: o censo de rótulos não comprova
limites de cada redação, contexto de notas, hierarquia inteira ou semântica de
tabelas. No CP, o incremento de 30/10/2026 recupera no censo os dez rótulos 187–196
e guarda cada rubrica dentro do artigo do rótulo seguinte, sem número inventado
e sem vigência.
A igualdade de 432 identidades/434 ocorrências não certifica os demais limites.
LMP contém um byte final não decodificado
na fonte UTF-16, preservado e sinalizado. L9099 não tem HTML histórico disponível.
Nenhuma dessas lacunas recebe texto substituto.

Jurisprudência mantém ocorrências duplicadas (inclusive sumário/corpo nos PDFs),
campos não interpretados e situações desconhecidas. Preservação não permite declarar
uma ocorrência como redação vigente. As datas são das capturas históricas, não de
consulta atual aos tribunais. Não houve recaptura atual das 15 leis nesta validação.

## Reprodução

```bash
python -m pytest -q --cov=leis_brasileiras --cov-report=term
python -m tools.build_inventory --check --report dist/source-fidelity-report.json
python -m tools.build_reference --version fidelity-check --output dist/fidelity-check.zip
python -m tools.audit_source_fidelity
python -m tools.audit_legacy_assertions --output dist/legacy-audit.json
python -m build
```

O arquivo versionado `docs/source-inventory.json` contém somente o resumo: contagens,
componentes, datas, fonte, versão do parser, divergências e hash da reconciliação
completa. As listas integrais de identidades e ocorrências são geradas no relatório
`dist/source-fidelity-report.json`; `dist/` não é versionado. O `report_sha256` de
cada resumo corresponde ao objeto de reconciliação completo, excluído o próprio
campo de hash, usando a serialização determinística do contrato.

O comando acima recalcula o relatório integral e confere o resumo e os READMEs.
Uma divergência continua retornando erro; o relatório é salvo mesmo nesse caso
para investigação. O CI disponibiliza o arquivo como artefato `source-fidelity-report`
por 14 dias, vinculado à execução. Após expirar, ele pode ser regenerado a partir
do mesmo commit e das fixtures. Falha de upload aparece no job e não muda os
resultados da auditoria. Nenhum dado operacional privado entra nesse artefato.

`audit_source_fidelity` retorna 2 quando há estrutura incompleta. Isso é esperado no
estado atual e não deve virar uma declaração de completude no CI. O CI reprova
inventário/documentação divergente, perdas cobertas pelas regressões, falha de replay,
contrato inválido e adulterações. Fixtures antigas não foram regravadas.

Casos de abuso cobrem conteúdo ativo/instruções tratados como dados, URLs externas,
exfiltração, comandos indevidos, conteúdo malformado, volume, referências entre leis
ou capturas, datas/status inventados e adulteração com hashes recalculados. A suíte
não usa APIs pagas nem conecta a bancos de produção.

O diagnóstico operacional e o plano de correção do corpus privado estão preservados
no repositório de dados. Nenhum deploy, ingestão ou alteração de banco foi executado.

## Captura ao vivo — 2026-10-30

O Planalto fecha a conexão para o token `leis-brasileiras/0.1 (legislation research)`.
Responde ao token compatível `Mozilla/5.0 (compatible; leis-brasileiras/0.2; +https://github.com/nogran/leis-brasileiras)`.
A URL catalogada da LGPD com `L13709` devolve 301 para a mesma URL com `l13709`.
O catálogo passou a guardar o endereço que responde 200. Redirecionamento continua recusado.

`extract LGPD` em 2026-10-30 gravou HTML de 230.913 bytes, SHA-256
`d3e5975ae30a0919e0fffb3d673c4919b289ff74bfd81dd0517b19596c0fe9c9`,
`verify-capture` aprovado, `complete=false`. O transcript de conteúdo tem o mesmo
SHA-256 da fixture histórica (`351267171aba34dfd6e258573c85d5dff70ce6b08d0ddd3d0b5af9182174b6d8`);
o HTML bruto não é o mesmo.

Nessa fixture o artigo 57 não aparece como string contígua. O número está partido
em spans no mesmo parágrafo (`Art. 5`, `7.`, `(VETADO).`). Com `observed-legislation@4`
esses dígitos viram `main/57`, uma leitura, e `main/5` permanece a leitura que
define dado pessoal. O texto observado de `main/57` ainda inclui o título `Seção II`,
porque o detector de cabeçalho exige `SEÇÃO`. Nenhuma vigência é escolhida.

## Número partido em spans — 2026-10-30

Windows, Python 3.14.3, dependências do lock. Nenhuma fixture HTML foi regravada.

| Verificação | Resultado |
|---|---|
| Suíte completa | 969 passaram, sem falhas ou skips |
| Cobertura | 89,30%; piso de 86% mantido |
| Inventário | `--check` aprovado |

Na fixture da LGPD, candidatos e artigos estruturados passam de 79 para 80.
Ocorrências continuam 80 e as divergências continuam 2. As outras 14 normas
mantêm candidatos, artigos e ocorrências. O `report_sha256` muda nas normas com
HTML, porque o método do censo (`stdlib-htmlparser-block-break-labels@3`) entra
no objeto hasheado. L9099 não tem censo, então o hash de reconciliação dela
permanece. `complete=false` permanece.

