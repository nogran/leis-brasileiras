# Validação da consolidação — 2026-10-29

A correção introduz `observed-law-v1` e `observed-jurisprudence-v1`, sem exportação
de lápides ou anotações editoriais. Os critérios atuais são preservação rastreável,
reprodução da captura, reconciliação independente e limites explícitos. O
[registro de validação anterior](archive/validation-2026-10-27.md) foi preservado
como histórico; suas afirmações sobre os formatos antigos não validam esta entrega.

## Resultados locais

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

## O que a validação não certifica

Todas as fontes continuam com `complete=false`: o censo de rótulos não comprova
limites de cada redação, contexto de notas, hierarquia inteira ou semântica de
tabelas. No CP, o censo restrito a parágrafos não encontra dez rótulos recuperados
pelo mapa DOM; a divergência é publicada. LMP contém um byte final não decodificado
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
