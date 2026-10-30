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

No CP, a fixture de 07/07/2026 contém os artigos 187–196 em quatro parágrafos
iniciados por rubricas: 187–191 nas linhas 6217–6233 do HTML descomprimido,
192–193 em 6241–6248, 194–195 em 6251–6256 e 196 em 6263–6266. Os artigos são
separados por `br`; `Art` e `187` ainda têm uma quebra de linha entre si.
O censo anterior examinava somente o início do parágrafo e perdia os dez rótulos.
O DOM reparado recuperava esses rótulos, mas a estruturação absorvia rubricas
seguintes no artigo anterior ou no cabeçalho do capítulo.

`observed-legislation@3` corrige ambos os mecanismos. O censo independente usa
limites explícitos de bloco/`br`. As nove rubricas do fluxo entram no artigo do
rótulo seguinte (187–190, 192–194, 196 e 197), antes do rótulo e da nota, sem
número inventado e sem vigência. As dez notas oficiais e todas as marcações
permanecem.
Os `strike` nesse intervalo contêm somente quebras/espaços, sem corpo jurídico a
reconstruir. O hash SHA-256 dos bytes HTML é
`5ec15272038b6552a08fe6c3444a3a557033de52dea8a53f0b150b138085c282`;
a fixture comprimida não foi regravada. São 432 identidades e 434 ocorrências,
conferidas por rótulo, nota e ordem, sem certificação de completude. A revisão
geral das demais rubricas, limites, hierarquia e tabelas continua pendente.

Na LGPD, a fixture de 07/07/2026 não contém a sequência contígua `Art. 57`. Entre os artigos 56 e 58 o número está em spans do mesmo parágrafo (`Art. 5`, `7.`, `(VETADO).`). `observed-legislation@4` junta esses dígitos quando o primeiro fragmento é só o rótulo. O artigo 5 real permanece uma leitura. O censo independente aplica o mesmo critério (`stdlib-htmlparser-block-break-labels@3`) sem importar o segmentador. O título seguinte `Seção II` continua dentro dessa leitura, porque o detector de cabeçalho exige `SEÇÃO`. Nenhuma vigência é escolhida.

LMP preserva o byte UTF-16 terminal incompleto. L9099 conserva
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
