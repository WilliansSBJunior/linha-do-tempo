# Mandatos: conferência com as APIs oficiais

Gerado por `scripts/gerar_curadoria.py --so mandato-oficial` a partir de `data/raw/oficial/` (Câmara coletada em 2026-10-17T16:04:21Z, Senado em 2026-10-17T16:04:40Z). Aplicado por `curadoria.aplicar_mandato_oficial` (arquivo `data/curadoria/mandato-oficial.json`). Nada do que já estava em `mandato` foi sobrescrito.

| | linhas de `mandato` |
|---|---:|
| no banco | 311 |
| confirmadas (legislatura bate; partido e UF sem conflito) | 253 |
| com complemento de partido/UF (campo estava NULL) | 0 |
| divergentes (listadas abaixo, banco intacto) | 17 |
| sem fonte oficial nesta rodada | 41 |

Confirmadas + divergentes + sem fonte = 311. Linhas confirmadas que já tinham evidência antes: 0 (nesses casos a oficial entra como evidência adicional das relações).

Regras: o ano de `inicio` pertence à legislatura que contém 1/jul desse ano; a linha só é confirmada se a pessoa consta na API nessa legislatura e partido/UF do banco batem com a API (mesma sigla, renomeação inequívoca da mesma legenda como PMDB/MDB e PFL/DEM, ou legenda vigente naquele ano segundo o histórico da Câmara / filiações do Senado). Qualquer outra coisa é divergência. Campo NULL no banco só é preenchido quando a linha não tem divergência alguma.

## Divergências

Por tipo: ano_fora_das_legislaturas 6, nao_encontrado_na_api 9, partido 2.

| pessoa | cargo | início | tipo | banco | oficial | legislatura | fonte |
|---|---|---|---|---|---|---|---|
| Aloizio Mercadante | senador | 2002 | ano_fora_das_legislaturas | 2002 | legislaturas listadas: 52, 53 |  | https://legis.senado.leg.br/dadosabertos/senador/845 |
| Eunício Oliveira | senador | 2019 | ano_fora_das_legislaturas | 2019 | legislaturas listadas: 54, 55 |  | https://legis.senado.leg.br/dadosabertos/senador/612 |
| Flávio Bolsonaro | senador | 2018 | ano_fora_das_legislaturas | 2018 | legislaturas listadas: 56, 57 |  | https://legis.senado.leg.br/dadosabertos/senador/5894 |
| Henrique Eduardo Alves | deputado | 2015 | ano_fora_das_legislaturas | 2015 | legislaturas listadas: 50, 51, 52, 53, 54 |  | https://dadosabertos.camara.leg.br/api/v2/deputados/74324 |
| Joice Hasselmann | deputado | 2018 | ano_fora_das_legislaturas | 2018 | legislaturas listadas: 56 |  | https://dadosabertos.camara.leg.br/api/v2/deputados/204546 |
| Michel Temer | deputado | 2011 | ano_fora_das_legislaturas | 2011 | legislaturas listadas: 50, 51, 52, 53 |  | https://dadosabertos.camara.leg.br/api/v2/deputados/73552 |
| Enéas Carneiro | deputado | 2002 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=En%C3%A9as%20Carneiro&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Enéas Carneiro | deputado | 2003 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=En%C3%A9as%20Carneiro&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Enéas Carneiro | deputado | 2005 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=En%C3%A9as%20Carneiro&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Enéas Carneiro | deputado | 2006 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=En%C3%A9as%20Carneiro&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| João Maia | deputado | 1997 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=Jo%C3%A3o%20Maia&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Luís Carlos Santos | deputado | 1995 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=Lu%C3%ADs%20Carlos%20Santos&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Luís Eduardo Magalhães | deputado | 1995 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=Lu%C3%ADs%20Eduardo%20Magalh%C3%A3es&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Luís Eduardo Magalhães | deputado | 1996 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=Lu%C3%ADs%20Eduardo%20Magalh%C3%A3es&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Luís Eduardo Magalhães | deputado | 1997 | nao_encontrado_na_api | deputado | (sem dado) |  | https://dadosabertos.camara.leg.br/api/v2/deputados?nome=Lu%C3%ADs%20Eduardo%20Magalh%C3%A3es&idLegislatura=50&itens=100&ordem=ASC&ordenarPor=nome |
| Miro Teixeira | deputado | 2004 | partido | PT | PDT | 52 | https://dadosabertos.camara.leg.br/api/v2/deputados/74862 |
| Ronivon Santiago | deputado | 1997 | partido | PFL | PPR | 50 | https://dadosabertos.camara.leg.br/api/v2/deputados/74184 |

## Pessoas não encontradas na API

- Enéas Carneiro (camara): nao_encontrado:nenhum; 4 linha(s) de mandato sem fonte. Provável diferença de grafia do nome parlamentar; resolver com alias e nova coleta.
- João Maia (camara): nao_encontrado:ambiguo:2; 1 linha(s) de mandato sem fonte. Provável diferença de grafia do nome parlamentar; resolver com alias e nova coleta.
- Luís Carlos Santos (camara): nao_encontrado:nenhum; 1 linha(s) de mandato sem fonte. Provável diferença de grafia do nome parlamentar; resolver com alias e nova coleta.
- Luís Eduardo Magalhães (camara): nao_encontrado:nenhum; 3 linha(s) de mandato sem fonte. Provável diferença de grafia do nome parlamentar; resolver com alias e nova coleta.

## Sem fonte oficial nesta rodada

presidente 6, presidente_camara 16, presidente_senado 14, vice_presidente 5. páginas oficiais da Presidência/Casas fora do ar na coleta (presidentes_camara, presidentes_republica, presidentes_senado, vice_presidentes). Linhas não tocadas.

## Complementos aplicados

Nenhum: em `deputado`/`senador` todo `partido` e `uf` do banco já estava preenchido.

## Como as linhas confirmadas bateram

| campo | igual | sucessao | historico | nao_informado | complemento |
|---|---:|---:|---:|---:|---:|
| partido | 166 | 45 | 42 | 0 | 0 |
| uf | 253 | 0 | 0 | 0 | 0 |

`sucessao` = renomeação da mesma legenda; `historico` = não bate com a lista da legislatura mas bate com o histórico de partido/UF do ano; `nao_informado` = a API não traz o dado.

