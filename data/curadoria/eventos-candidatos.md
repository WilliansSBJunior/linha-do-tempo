# Candidatos a fusão de eventos (para decisão do usuário)

Eventos com a mesma data (ou mesmo ano-mês) e títulos parecidos que **não** entraram em `eventos-fusoes.json`
porque não é certo que descrevam exatamente o mesmo fato. Para aprovar um par, copie-o para
`eventos-fusoes.json` (`{"manter": id, "fundir": [ids], "motivo": "..."}`) e rode `python3 scripts/migrar.py`.

Critério de geração: mesma `data` (ou mesmo ano-mês quando uma das duas tem só o mês), título sem stopwords com Jaccard >= 0,3
(os com >= 0,5 ou mesmo verbo+objeto e data idêntica e fato idêntico foram fundidos). Procurei também pares em dias
diferentes do mesmo ano com Jaccard >= 0,5: não há nenhum.

| # | data | eventos | por que ficou de fora |
|---|---|---|---|
| 1 | 2024-03 | `ida10` "Clava Forte Bank, fintech de André e Cassiane Valadão" e `vol3` "Valadão e a esposa fundam o Clava Forte Bank, fintech cristã" | Mesmo fato (fundação do Clava Forte), mas são dois eventos de origens em capítulos diferentes (`ida` e `volta`) com ids estáveis; fundir tiraria um deles da página de origens. |
| 2 | 2020-11-17 | `max19` "CRSFN pautado para julgar recurso do Banco Máxima, Sabbá e Caló" e `max20` "CRSFN: pauta inclui segundo recurso, de Máxima CCTVM, Abdalla, Gonçalves e Sabbá" | Recursos diferentes na mesma pauta. Não é duplicata. |
| 3 | 2025-03 / 2025-03-28 | `ev-2025-03-brb-e-master-fecham-acordo-para-venda-de` (só mês) e `ev-2025-03-28-brb-anuncia-compra-de-58-do-master` (já fundido com a aprovação do conselho) | Provavelmente o mesmo ato (acordo para BRB comprar 58% por R$ 2 bi), mas a data de um tem só o mês. |
| 4 | 2025-08-28 | `ev-2025-08-28-carbono-oculto-quasar-e-tank-operacoes-miram-suposto` e `ev-2025-08-28-reag-e-alvo-de-buscas-na-carbono-oculto` | O segundo é um desdobramento (Reag como alvo) da mesma deflagração. Fatos de granularidade diferente. |
| 5 | 2025-11-17 | `ev-2025-11-17-pf-prende-daniel-vorcaro-em-sao-paulo` e o título composto "Fictor anuncia compra do Master; Vorcaro é preso" (já fundido com a Fictor) | A prisão aparece nos dois. O dossiê BRB data "BC liquida o Master; Vorcaro é preso" em 18/11, a teia diz que a detenção foi na noite de 17/11: há divergência de data entre as fontes. |
| 6 | 2025-11-18 | `ev-2025-11-18-1a-fase-da-compliance-zero-7-prisoes-e` e o evento fundido "BC decreta a liquidação extrajudicial do Master" | Os títulos compostos fundidos mencionam a 1ª fase da Compliance Zero; a operação continua como evento próprio. Se quiser, o evento da operação pode absorver o trecho "PF faz buscas no BRB" (ver motivo da fusão de 18/11). |
| 7 | 2026-01-14 | `vol11` "PF detém Zettel em Guarulhos na 2ª fase da Compliance Zero" e o evento fundido da 2ª fase | A detenção de Zettel é parte da 2ª fase, mas `vol11` é de origens (id estável, resposta do citado) e tem foco diferente. |
| 8 | 2026-03-04 | `vol16` "Fase 3: PF prende Zettel como suposto operador financeiro de Vorcaro" e o evento fundido da 3ª fase | Prisão de outra pessoa na mesma fase. Não é o mesmo fato. |
| 9 | 2026-09-08 | `fam29` "CVM aplica multas a Daniel, Henrique e Felipe Vorcaro e ao Master..." e `ev-2026-09-08-mendonca-afasta-o-diretor-geral-da-pf-cvm-multa-vorcaro` | O título da teia junta dois fatos (afastamento do diretor-geral da PF e multa da CVM). Só o segundo coincide com `fam29`; fundir esconderia o primeiro. |
| 10 | 2026-01-15 | `vol12` (nota da Lagoinha), `vol13` (lista de requerimentos da CPMI) e os eventos fundidos da liquidação da Reag | Fatos distintos que caem no mesmo dia. |

Observação sobre o critério: nos títulos compostos ("A; B") fundi com o evento que nomeia o mesmo fato principal
(a primeira oração) quando a segunda oração já existe como evento próprio (liquidação do Master, Fictor, 3ª e 4ª fases,
Barco de Papel). Os textos e as fontes originais de cada evento fundido ficam em `evento_alias.original_json`.
