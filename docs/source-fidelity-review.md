# Revisão da fidelidade às fontes

A consolidação inclui o trabalho de inventário e a limpeza dos READMEs. O objetivo
é impedir a exportação de conteúdo jurídico criado pelo extrator e preservar o que
pode ser rastreado às capturas. O HTML original precede a estruturação; não há
remoção de strike, escolha do maior texto nem aplicação de curadoria na nova saída.

## Intervenções antigas

O [inventário técnico](legacy-assertion-audit.json) enumera cada uma das oito
intervenções pós-extração e as 15 lápides encontradas nas fixtures. Os dois títulos
(LGPD capítulo IX, CF88 título IX) devem vir do texto capturado, sem substituição
pelo registro manual. As cinco notas de CLT (554, 555, 571, 572, 575) são afirmações
editoriais, não citações verificadas da fonte; nenhuma é exportada. A supressão
manual de alteração no CP 121-A também foi retirada: a menção original fica ligada
à evidência, sem atribuição automática a um dispositivo.

Essa decisão não valida nem refuta juridicamente as afirmações históricas. Retira
um mecanismo que as apresentava como dados coletados. O registro antigo permanece
somente para diagnóstico. O extrator privado ainda precisa de migração própria.

## Evidência e pendências por fonte

As 15 normas possuem resumo reproduzível em [source-inventory.json](source-inventory.json).
As listas completas são geradas localmente ou baixadas do artefato do CI, conforme
[reprodução da auditoria](validation.md#reprodução).
A CF88 recupera os artigos principais 117, 171 e 233 e os artigos ADCT 91, 106–112,
111-A e 114 antes ausentes. Os rótulos permanecem distintos por componente. A
contagem 424 refere-se exclusivamente à fixture de 07/07/2026.

No CP, artigos 187–196 aparecem no mapa estrutural mas não no censo independente
restrito a parágrafos. LMP preserva o byte UTF-16 terminal incompleto. L9099 conserva
apenas o derivado histórico com ausência de fonte explícita. Notas, preâmbulos,
anexos e tabelas ficam preservados, mas a revisão de delimitação segue pendente em
todas as normas; os pacotes não declaram completude.

A auditoria das seis fontes judiciais reprocessou os arquivos históricos de julho
/agosto de 2026: 2.347 identidades STJ temas (2.384 linhas), 676 súmulas STJ,
1.284 temas STF, 63 súmulas vinculantes, 172 súmulas TJPE e 89 TJMG (178 ocorrências
entre sumário e corpo). Esses valores são diagnósticos da captura, não metas de
cobertura atual. O TJPE possui índice histórico previamente redigido no arquivo
privado; não é possível atestar seus bytes originais anteriores à redação. PDFs
foram novamente escaneados e extraídos em processo isolado.

CSV/JSON não perdem colunas desconhecidas. Ausência de tese não recebe texto gerado;
cancelamentos não recebem data inventada. O índice do STF permanece vinculado ao
detalhe. Os PDFs conservam páginas, intervalos e duplicatas, com revisão estrutural
pendente. A aprovação dos testes não elimina essas restrições.

Ver [contratos](format.md), [validação](validation.md) e [consumidores](transition.md).
