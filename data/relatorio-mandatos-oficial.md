# Mandatos: conferência com as fontes oficiais

Gerado por `scripts/gerar_curadoria.py --so mandato-oficial` a partir de `data/raw/oficial/` (Câmara coletada em 2026-10-17T21:31:28Z, Senado em 2026-10-17T21:31:48Z, páginas das presidências das Casas em 2026-10-17T21:31:59Z). Aplicado por `curadoria.aplicar_mandato_oficial` (arquivo `data/curadoria/mandato-oficial.json`). Nada do que já estava em `mandato` foi sobrescrito (a única mudança de valor é a correção à mão listada abaixo).

| | linhas de `mandato` |
|---|---:|
| no banco | 311 |
| confirmadas | 298 |
| &nbsp;&nbsp;por legislatura (deputado/senador; a pessoa consta na API em legislatura que toca o ano; partido e UF sem conflito) | 266 |
| &nbsp;&nbsp;por eleição (a pessoa só consta na legislatura que começa em 1/fev do ano seguinte; ver abaixo) | 4 |
| &nbsp;&nbsp;por página oficial da presidência da Casa (nome e ano de início) | 28 |
| com complemento de partido/UF (campo estava NULL) | 0 |
| divergentes (listadas abaixo, banco intacto) | 2 |
| sem fonte oficial nesta rodada | 11 |

Confirmadas + divergentes + sem fonte = 311. Linhas confirmadas que já tinham evidência antes: 0 (nesses casos a oficial entra como evidência adicional das relações).

Regras:

- `legislatura`: as linhas de `deputado`/`senador` são destaques anuais (inicio = fim = ano). Uma legislatura vai de 1/fev do ano N a 31/jan do ano N+4; a linha é confirmada se a pessoa consta na API em **qualquer** legislatura que toque algum dia do ano (a que contém 1/jul é comparada primeiro) e partido/UF do banco batem com a API (mesma sigla, renomeação inequívoca da mesma legenda como PMDB/MDB e PFL/DEM, ou legenda vigente naquele ano segundo o histórico da Câmara / filiações do Senado). Nas entradas do histórico da Câmara com descrição "Nome no início da legislatura / Partido no início da legislatura" a `dataHora` é falsa (2023); valem como o partido no início da legislatura indicada (1/fev do início dela).
- `eleicao`: se a pessoa **não** consta em legislatura que toque o ano, mas consta na que começa em 1/fev do ano seguinte, **e** o `motivo` da linha menciona eleição (eleit / votos / mais votad), a linha é confirmada com essa evidência e o partido/UF comparados são os da legislatura seguinte. Isso prova o mandato subsequente; **não** prova que a pessoa exercia mandato no ano da eleição.
- `pagina`: `presidente_camara` e `presidente_senado` são conferidos pelo nome (sem acento/caixa; um nome contido no outro, com a variante "Tião Vianna" = "Tião Viana") e pelo ano de `inicio` contra o período da página oficial ("AAAA - BBBB" cobre AAAA a BBBB; "AAAA" só AAAA; "- BBBB" só BBBB). `presidente` e `vice_presidente` seguem sem fonte oficial (não há página pública).
- Qualquer outra coisa é divergência. Campo NULL no banco só é preenchido quando a linha não tem divergência alguma (e não em linha confirmada por eleição).

## Confirmadas por eleição

Evidência é a legislatura seguinte; a pessoa não exercia mandato naquele ano.

| pessoa | cargo | ano da linha | legislatura que prova | partido (banco / oficial) | UF (banco / oficial) |
|---|---|---|---|---|---|
| Aloizio Mercadante | senador | 2002 | 52 | PT / PT | SP / SP |
| Enéas Carneiro | deputado | 2002 | 52 | PRONA / PR | SP / SP |
| Flávio Bolsonaro | senador | 2018 | 56 | PSL / PL | RJ / RJ |
| Joice Hasselmann | deputado | 2018 | 56 | PSL / PSDB | SP / SP |

## Confirmadas por página oficial

| pessoa | cargo | início | nome na página | período na página |
|---|---|---|---|---|
| Luís Eduardo Magalhães | presidente_camara | 1995 | Luís Eduardo | 1995 - 1997 |
| Michel Temer | presidente_camara | 1997 | Michel Temer | 1997 - 1999 |
| Aécio Neves | presidente_camara | 2001 | Aécio Neves | 2001 - 2002 |
| Efraim Morais | presidente_camara | 2002 | Efraim Morais | 2002 - 2003 |
| João Paulo Cunha | presidente_camara | 2003 | João Paulo Cunha | 2003 - 2005 |
| Aldo Rebelo | presidente_camara | 2005 | Aldo Rebelo | 2005 - 2007 |
| Severino Cavalcanti | presidente_camara | 2005 | Severino Cavalcanti | 2005 |
| Arlindo Chinaglia | presidente_camara | 2007 | Arlindo Chinaglia | 2007 - 2009 |
| Michel Temer | presidente_camara | 2009 | Michel Temer | 2009 - 2010 |
| Marco Maia | presidente_camara | 2011 | Marco Maia | 2011 - 2013 |
| Henrique Eduardo Alves | presidente_camara | 2013 | Henrique Eduardo Alves | 2013 - 2015 |
| Eduardo Cunha | presidente_camara | 2015 | Eduardo Cunha | 2015 - 2016 |
| Rodrigo Maia | presidente_camara | 2016 | Rodrigo Maia | 2016 - 2017 |
| Waldir Maranhão | presidente_camara | 2016 | Waldir Maranhão | 2016 |
| Arthur Lira | presidente_camara | 2021 | Arthur Lira | 2021 - 2023 |
| José Sarney | presidente_senado | 1995 | José Sarney | 1995 - 1997 |
| Antonio Carlos Magalhães | presidente_senado | 1997 | Antonio Carlos Magalhães | 1997 - 1999 |
| Jader Barbalho | presidente_senado | 2001 | Jader Barbalho | 2001 |
| Ramez Tebet | presidente_senado | 2001 | Ramez Tebet | 2001 - 2003 |
| José Sarney | presidente_senado | 2003 | José Sarney | 2003 - 2005 |
| Renan Calheiros | presidente_senado | 2005 | Renan Calheiros | 2005 - 2007 |
| Garibaldi Alves Filho | presidente_senado | 2007 | Garibaldi Alves | 2007 - 2009 |
| Tião Viana | presidente_senado | 2007 | Tião Vianna | 2007 |
| José Sarney | presidente_senado | 2009 | José Sarney | 2009 - 2011 |
| Renan Calheiros | presidente_senado | 2013 | Renan Calheiros | 2013 - 2015 |
| Eunício Oliveira | presidente_senado | 2017 | Eunício Oliveira | 2017 - 2019 |
| Davi Alcolumbre | presidente_senado | 2019 | Davi Alcolumbre | 2019 - 2021 |
| Rodrigo Pacheco | presidente_senado | 2021 | Rodrigo Pacheco | 2021 - 2023 |

## Divergências

Por tipo: pagina_periodo 1, pagina_pessoa 1.

| pessoa | cargo | início | tipo | banco | oficial | legislatura | fonte |
|---|---|---|---|---|---|---|---|
| Davi Alcolumbre | presidente_senado | 2025 | pagina_periodo | 2025 | Davi Alcolumbre 2019 - 2021 |  | https://www25.senado.leg.br/web/senadores/nova-republica |
| Hugo Motta | presidente_camara | 2025 | pagina_pessoa | Hugo Motta | (sem dado) |  | https://www2.camara.leg.br/a-camara/conheca/historia/presidentes |

## Pessoas não encontradas na API

- nenhuma

## Sem fonte oficial nesta rodada

presidente 6, vice_presidente 5. sem página oficial pública das presidências na coleta de 2026-10-17: presidentes_republica (indisponivel: não há página pública hoje: a galeria do Planalto redireciona para login (acl_users/credentials_cookie_auth); a Biblioteca da Presidência está em manutenção; variantes de URL dão 404); vice_presidentes (indisponivel: não há página pública hoje: URL da galeria de vice-presidentes dá 404 e as variantes testadas também). Linhas não tocadas.

## Correções à mão aplicadas antes do confronto

- Miro Teixeira deputado 2004: partido PT -> PPS. histórico oficial da Câmara: PDT até 13/4/2004, PPS de 13/4/2004 a 14/2/2005; PT só a partir de 14/2/2005. Fonte: https://dadosabertos.camara.leg.br/api/v2/deputados/74862/historico

## Complementos aplicados

Nenhum: em `deputado`/`senador` todo `partido` e `uf` do banco já estava preenchido.

## Como as linhas confirmadas por legislatura/eleição bateram

| campo | igual | sucessao | historico | nao_informado | complemento |
|---|---:|---:|---:|---:|---:|
| partido | 174 | 45 | 51 | 0 | 0 |
| uf | 270 | 0 | 0 | 0 | 0 |

`sucessao` = renomeação da mesma legenda; `historico` = não bate com a lista da legislatura mas bate com o histórico de partido/UF do ano; `nao_informado` = a API não traz o dado.

