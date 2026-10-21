# Relatório de migração

Gerado por `scripts/migrar.py` (timestamp fixo 2026-10-16T00:00:00Z). Fonte: `data/raw/` (hashes em `data/raw/hashes.txt`).

## 1. Contagens antes (raw) e depois (banco)

| Antes (raw) | n |
|---|---|
| N | 198 |
| E (pares) | 319 |
| relações (E[].r) | 343 |
| EV teia | 167 |
| PREC | 36 |
| EV origens | 89 |
| SEM teia | 52 |
| SEM origens | 22 |
| LAC teia | 12 |
| LAC origens | 46 |
| NARR origens (parágrafos) | 25 |
| SINT teia/origens | 5/2 |
| dossiê brb.eventos | 30 |
| timeline eventos pol+intl | 280 |
| timeline empresas | 397 |
| timeline setores | 372 |
| pares indicadores | 18 |
| pares pontos não nulos | 4806 |
| violência marcos | 10 |
| violência DATA | 45 |

| Depois (banco) | n |
|---|---|
| entidade | 412 |
|   da teia (N) | 198 |
|   extras (timeline/pares) | 214 |
| entidade_alias | 544 |
| relacao (origem teia, de E[].r) | 343 |
| relacao (fam_de) | 21 |
| relacao (lig_de) | 3 |
| relacao (origem linha_do_tempo: mandato/filiação) | 472 |
| relacao total | 839 |
| evento total | 507 |
| tema | 13 |
| relacao_tema | 928 |
| evento_tema | 633 |
| fonte (era video) | 0 |
| evidencia | 1738 |
| relacao_evidencia | 1280 |
| evento_evidencia | 3229 |
| evento_entidade | 935 |
| nota | 570 |
| indicador | 83 |
| serie | 6837 |
| ranking_empresa | 504 |
| mandato | 324 |
| bancada | 634 |
| entidade_valor | 60 |
| post_rede | 2126 |
| post_triagem | 169 |

Eventos por canal:

| canal | n |
|---|---|
| banco | 27 |
| brasil | 282 |
| brb | 18 |
| familia | 22 |
| ida | 22 |
| precatorios | 35 |
| teia | 73 |
| violencia | 10 |
| volta | 18 |

## 2. Eventos sem natureza (`natureza_id` NULL)

| canal | n |
|---|---|
| brasil | 280 |
| teia | 92 |
| violencia | 10 |

Situação na carga bruta, antes da curadoria (seções 9 e 10 dizem o que mudou). Os eventos da timeline Brasil (`brasil`) e os marcos legais (`violencia`) nunca tiveram `st`; os da teia são os 92 abaixo (todos canal `teia`, nenhum casa com origens). Lista completa dos 92 da teia:

| id | d | título |
|---|---|---|
| ev-2019-10-14-bc-aprova-controle-do-maxima-por-vorcaro | 2019-10-14 | BC aprova controle do Máxima por Vorcaro |
| ev-2021-08-02-maxima-relanca-se-como-banco-master | 2021-08-02 | Máxima relança-se como Banco Master digital |
| ev-2022-02-fgc-denuncia-grupo-master-a-cvm-caso-e | 2022-02 | FGC denuncia Grupo Master à CVM; caso é arquivado |
| ev-2023-10-rioprevidencia-inicia-aportes-em-letras | 2023-10 | Rioprevidência inicia aportes em letras financeiras do Master |
| ev-2023-10-comecam-as-aplicacoes-de-rpps-em-letras | 2023-10 | Começam as aplicações de RPPS em letras do Master |
| ev-2024-05-27-bc-aprova-a-compra-da-will-no-dia | 2024-05-27 | BC aprova a compra da Will; no dia seguinte, exigência de capital |
| ev-2024-07-brb-comeca-a-comprar-carteiras-de | 2024-07 | BRB começa a comprar carteiras de crédito do Master |
| ev-2024-10-fundos-hans-95-e-reag-growth-aportam | 2024-10 | Fundos Hans 95 e Reag Growth aportam mais de R$ 1 bi no Master |
| ev-2024-12-04-lula-recebe-vorcaro-no-planalto-fora-da | 2024-12-04 | Lula recebe Vorcaro no Planalto, fora da agenda |
| ev-2025-03-28-brb-anuncia-compra-de-58-do-master | 2025-03-28 | BRB anuncia compra de 58% do Master |
| ev-2025-03-brb-e-master-fecham-acordo-para-venda-de | 2025-03 | BRB e Master fecham acordo para venda de 58% por R$ 2 bilhões |
| ev-2025-04-23-operacao-sem-desconto-pf-e-cgu-miram | 2025-04-23 | Operação Sem Desconto: PF e CGU miram descontos no INSS |
| ev-2025-04-balanco-2024-ativo-de-r-63-bi-e-r-8-7-bi | 2025-04 | Balanço 2024: ativo de R$ 63 bi e R$ 8,7 bi em precatórios |
| ev-2025-05-05-fgc-comeca-a-dar-assistencia-financeira | 2025-05-05 | FGC começa a dar assistência financeira ao Master |
| ev-2025-05-27-btg-compra-r-1-5-bi-em-ativos-de-vorcaro | 2025-05-27 | BTG compra R$ 1,5 bi em ativos de Vorcaro |
| ev-2025-07-15-bc-comunica-ao-mpf-indicios-de-crimes-na | 2025-07-15 | BC comunica ao MPF indícios de crimes na venda de carteiras ao BRB |
| ev-2025-08-28-carbono-oculto-quasar-e-tank-operacoes | 2025-08-28 | Carbono Oculto, Quasar e Tank: operações miram suposto esquema do PCC no setor de combustíveis |
| ev-2025-08-28-reag-e-alvo-de-buscas-na-carbono-oculto | 2025-08-28 | Reag é alvo de buscas na Carbono Oculto; ações caem cerca de 16% |
| ev-2025-08-cldf-aprova-em-uma-semana-compra-do | 2025-08 | CLDF aprova em uma semana compra do Master pelo BRB; Ibaneis sanciona |
| ev-2025-09-03-bc-veta-a-compra-do-master-pelo-brb | 2025-09-03 | BC veta a compra do Master pelo BRB |
| ev-2025-09-03-banco-central-rejeita-a-compra-do-master | 2025-09-03 | Banco Central rejeita a compra do Master pelo BRB |
| ev-2025-09-12-pf-prende-careca-do-inss-e-mauricio | 2025-09-12 | PF prende Careca do INSS e Maurício Camisotti |
| ev-2025-09-21-master-apresenta-ao-bc-plano-de | 2025-09-21 | Master apresenta ao BC plano de salvamento |
| ev-2025-10-10-inss-nao-renova-acordo-consignado-do | 2025-10-10 | INSS não renova acordo consignado do Master |
| ev-2025-10-14-gaeco-aponta-executivos-da-reag-e-fundo | 2025-10-14 | Gaeco aponta executivos da Reag e fundo Mabruk II na Usina Itajobi |
| ev-2025-11-17-fictor-anuncia-compra-do-master-vorcaro | 2025-11-17 | Fictor anuncia compra do Master; Vorcaro é preso |
| ev-2025-11-17-pf-prende-daniel-vorcaro-em-sao-paulo | 2025-11-17 | PF prende Daniel Vorcaro em São Paulo |
| ev-2025-11-17-bc-comunica-ao-mpf-indicios-de-fraude | 2025-11-17 | BC comunica ao MPF indícios de fraude entre Master e fundos da Reag |
| ev-2025-11-18-bc-decreta-a-liquidacao-extrajudicial-do | 2025-11-18 | BC decreta a liquidação extrajudicial do Master |
| ev-2025-11-18-1a-fase-da-compliance-zero-7-prisoes-e | 2025-11-18 | 1ª fase da Compliance Zero: 7 prisões e 25 buscas |
| ev-2025-11-18-bc-liquida-o-banco-master-pf-faz-buscas | 2025-11-18 | BC liquida o Banco Master; PF faz buscas no BRB e Justiça afasta o presidente |
| ev-2025-11-18-bc-liquida-o-master-pf-deflagra-a | 2025-11-18 | BC liquida o Master; PF deflagra a Compliance Zero |
| ev-2025-11-relatorio-do-inss-aponta-251-718 | 2025-11 | Relatório do INSS aponta 251.718 consignados do Master sem prova |
| ev-2025-12-04-cpmi-do-inss-aprova-convocacao-e-quebra | 2025-12-04 | CPMI do INSS aprova convocação e quebra de sigilo de Vorcaro |
| ev-2025-12-09-revelado-contrato-de-r-129-mi-com | 2025-12-09 | Revelado contrato de R$ 129 mi com escritório da esposa de Moraes |
| ev-2025-12-19-justica-nega-enviar-carbono-oculto-e | 2025-12-19 | Justiça nega enviar Carbono Oculto e Quasar ao STF a pedido de Vorcaro |
| ev-2025-12-caso-chega-ao-stf-toffoli-e-relator-e | 2025-12 | Caso chega ao STF; Toffoli é relator e impõe sigilo |
| ev-2026-01-14-2a-fase-buscas-bloqueio-de-r-5-7-bi-e | 2026-01-14 | 2ª fase: buscas, bloqueio de R$ 5,7 bi e prisão de Zettel |
| ev-2026-01-14-2a-fase-da-compliance-zero-bloqueia-r-5 | 2026-01-14 | 2ª fase da Compliance Zero bloqueia R$ 5,7 bilhões |
| ev-2026-01-15-bc-liquida-a-reag-cbsf-dtvm | 2026-01-15 | BC liquida a Reag (CBSF DTVM) |
| ev-2026-01-15-bc-decreta-liquidacao-da-reag-trust-cbsf | 2026-01-15 | BC decreta liquidação da Reag Trust (CBSF DTVM) |
| ev-2026-01-16-inss-bloqueia-repasses-ao-master-r-2-bi | 2026-01-16 | INSS bloqueia repasses ao Master: R$ 2 bi e 254 mil contratos |
| ev-2026-01-17-fgc-inicia-pagamento-a-cerca-de-800-mil | 2026-01-17 | FGC inicia pagamento a cerca de 800 mil credores |
| ev-2026-01-17-fgc-comeca-a-pagar-garantia-a-credores | 2026-01-17 | FGC começa a pagar garantia a credores do Master (desembolso projetado de ~R$ 40,6 bi) |
| ev-2026-01-17-fgc-inicia-o-maior-ressarcimento-de-sua | 2026-01-17 | FGC inicia o maior ressarcimento de sua história |
| ev-2026-01-21-bc-liquida-a-will-financeira-fgc-estima | 2026-01-21 | BC liquida a Will Financeira; FGC estima R$ 6,3 bi |
| ev-2026-01-23-pf-deflagra-barco-de-papel-castro | 2026-01-23 | PF deflagra Barco de Papel; Castro exonera chefe do Rioprevidência |
| ev-2026-01-23-pf-faz-a-operacao-barco-de-papel-no | 2026-01-23 | PF faz a operação Barco de Papel no Rioprevidência |
| ev-2026-02-06-pf-mira-a-amprev-brb-entrega-plano-de | 2026-02-06 | PF mira a Amprev; BRB entrega plano de capital ao BC |
| ev-2026-02-09-pf-entrega-a-fachin-relatorio-sobre | 2026-02-09 | PF entrega a Fachin relatório sobre Toffoli e arguição de suspeição |
| ev-2026-02-10-fgc-aprova-plano-emergencial-para | 2026-02-10 | FGC aprova plano emergencial para recompor o caixa |
| ev-2026-02-12-toffoli-deixa-a-relatoria-mendonca | 2026-02-12 | Toffoli deixa a relatoria; Mendonça assume |
| ev-2026-02-18-bc-liquida-o-banco-pleno-ex-voiter | 2026-02-18 | BC liquida o Banco Pleno (ex-Voiter) |
| ev-2026-02-24-cvm-lista-18-procedimentos-sobre-os | 2026-02-24 | CVM lista 18 procedimentos sobre os grupos Master e Reag |
| ev-2026-03-04-3a-fase-vorcaro-e-preso-de-novo | 2026-03-04 | 3ª fase: Vorcaro é preso de novo |
| ev-2026-03-04-vorcaro-e-preso-de-novo-pf-mira-ex | 2026-03-04 | Vorcaro é preso de novo; PF mira ex-diretores do BC |
| ev-2026-03-04-vorcaro-e-preso-decisao-cita-r-2-2-bi-na | 2026-03-04 | Vorcaro é preso; decisão cita R$ 2,2 bi na Reag |
| ev-2026-03-11-mansur-na-cpi-master-era-cliente-da-reag | 2026-03-11 | Mansur na CPI: Master era cliente da Reag e nega vínculo com PCC |
| ev-2026-03-17-master-multiplo-e-liquidado-liquidante | 2026-03-17 | Master Múltiplo é liquidado; liquidante move ação em SP |
| ev-2026-03-28-cpmi-do-inss-termina-sem-relatorio-final | 2026-03-28 | CPMI do INSS termina sem relatório final |
| ev-2026-04-08-receita-mostra-pagamentos-do-master-a-ex | 2026-04-08 | Receita mostra pagamentos do Master a ex-ministros e políticos |
| ev-2026-04-16-4a-fase-ex-presidente-do-brb-e-preso | 2026-04-16 | 4ª fase: ex-presidente do BRB é preso |
| ev-2026-04-16-ex-presidente-do-brb-paulo-henrique | 2026-04-16 | Ex-presidente do BRB, Paulo Henrique Costa, é preso |
| ev-2026-04-16-ex-presidente-do-brb-e-preso-pf-cita | 2026-04-16 | Ex-presidente do BRB é preso; PF cita imóveis de R$ 74 a 146 mi |
| ev-2026-04-20-brb-e-quadra-fecham-memorando-para | 2026-04-20 | BRB e Quadra fecham memorando para vender ativos do Master |
| ev-2026-05-04-cvm-acusa-reag-trust-e-ex-diretor-por | 2026-05-04 | CVM acusa Reag Trust e ex-diretor por ocultar cotistas e liquidez |
| ev-2026-05-05-defesa-de-vorcaro-oferece-delacao-e | 2026-05-05 | Defesa de Vorcaro oferece delação e devolução de R$ 40 bi |
| ev-2026-05-07-5a-fase-senador-ciro-nogueira-e-alvo | 2026-05-07 | 5ª fase: senador Ciro Nogueira é alvo |
| ev-2026-05-07-pf-faz-buscas-contra-o-senador-ciro | 2026-05-07 | PF faz buscas contra o senador Ciro Nogueira (5ª fase) |
| ev-2026-05-26-justica-das-bahamas-reconhece-a | 2026-05-26 | Justiça das Bahamas reconhece a liquidação do Master |
| ev-2026-05-28-uniao-e-gdf-acordam-emprestimo-de-ate-r | 2026-05-28 | União e GDF acordam empréstimo de até R$ 6,6 bi do FGC ao BRB |
| ev-2026-06-09-presidente-do-brb-fala-em-corrida-de | 2026-06-09 | Presidente do BRB fala em corrida de liquidez e provisão de R$ 8,8 bi |
| ev-2026-06-11-folha-liga-o-gold-style-a-bk-bank-aster | 2026-06-11 | Folha liga o Gold Style a BK Bank, Aster e Super Empreendimentos |
| ev-2026-06-18-9a-fase-jaques-wagner-e-augusto-lima-sao | 2026-06-18 | 9ª fase: Jaques Wagner e Augusto Lima são alvos |
| ev-2026-06-18-9a-fase-da-compliance-zero-tem-jaques | 2026-06-18 | 9ª fase da Compliance Zero tem Jaques Wagner como alvo |
| ev-2026-07-14-pf-indicia-48-pessoas-na-sem-desconto | 2026-07-14 | PF indicia 48 pessoas na Sem Desconto, incluindo ex-presidente do INSS |
| ev-2026-07-17-brb-encerra-o-memorando-com-a-quadra | 2026-07-17 | BRB encerra o memorando com a Quadra |
| ev-2026-07-23-mendonca-autoriza-inquerito-sobre | 2026-07-23 | Mendonça autoriza inquérito sobre repasses de Vorcaro ao Dark Horse |
| ev-2026-08-18-mp-sp-denuncia-16-pessoas-da-carbono | 2026-08-18 | MP-SP denuncia 16 pessoas da Carbono Oculto |
| ev-2026-08-26-mansur-entrega-a-pgr-proposta-de-delacao | 2026-08-26 | Mansur entrega à PGR proposta de delação com 17 anexos |
| ev-2026-09-01-mendonca-tira-sigilo-de-relatorio-da-pf | 2026-09-01 | Mendonça tira sigilo de relatório da PF sobre mensagens a Moraes |
| ev-2026-09-01-mendonca-levanta-sigilo-de-relatorio-da | 2026-09-01 | Mendonça levanta sigilo de relatório da PF com 52 mensagens a número atribuído a Moraes |
| ev-2026-09-02-pgr-fecha-acordo-de-delacao-com-mansur | 2026-09-02 | PGR fecha acordo de delação com Mansur; homologação pendente |
| ev-2026-09-08-mendonca-afasta-o-diretor-geral-da-pf | 2026-09-08 | Mendonça afasta o diretor-geral da PF; CVM multa Vorcaro |
| ev-2026-09-09-fachin-suspende-decisoes-de-mendonca-e | 2026-09-09 | Fachin suspende decisões de Mendonça e Dino sobre a PF |
| ev-2026-09-13-stf-torna-publica-decisao-que-bloqueou | 2026-09-13 | STF torna pública decisão que bloqueou bens de Vorcaro |
| ev-2026-09-15-plenario-do-stf-discute-moraes-e | 2026-09-15 | Plenário do STF discute Moraes e Mendonça; Dino pede vista |
| ev-2026-09-15-plenario-do-stf-comeca-a-analisar | 2026-09-15 | Plenário do STF começa a analisar questão de ordem sobre pedido de investigar Moraes; Dino pede vista |
| ev-2026-09-24-dino-manda-a-pf-investigar-a-atuacao-da | 2026-09-24 | Dino manda a PF investigar a atuação da CVM no caso Master |
| ev-2026-09-24-credito-oculto-3a-fase-da-carbono-oculto | 2026-09-24 | Crédito Oculto: 3ª fase da Carbono Oculto mira Freixo, apontado pela PF como operador de Vorcaro |
| ev-2026-10-01-pf-indicia-13-executivos-na-quasar-e | 2026-10-01 | PF indicia 13 executivos na Quasar e envia relatório ao MPF |
| ev-2026-10-02-fachin-pede-a-pf-lista-de-ministros | 2026-10-02 | Fachin pede à PF lista de ministros citados nas conversas de Vorcaro |

## 3. Eventos de origens dedupados com os da teia

75 eventos coincidem por `(d, t)`; recebem o id de origens (canal = capítulo de origens) e fundem f (união), r, v, n, p. 14 eventos existem só em origens (ids preservados); 92 só na teia.

Diferença de nº de fontes origens − teia nos dedupados: {0: 53, 1: 22}. Casos em que a teia tem URL que origens não tem: 0; casos em que a ordem de f diverge do prefixo de origens: 0.

| id origens | índice teia EV | d | título |
|---|---|---|---|
| ida0 | 0 | 1957-12-20 | Fundação da Igreja Batista da Lagoinha, em Belo Horizonte |
| max0 | 1 | década de 1970 | Origem como corretora Máxima (anos 1970; 1974 em parte das fontes) |
| ida1 | 2 | 1972-07-31 | Márcio Valadão assume a Lagoinha e muda o perfil da igreja |
| fam0 | 3 | 1983-10-06 | Nasce Daniel Bueno Vorcaro, em Belo Horizonte |
| max1 | 4 | década de 1990 | A corretora se torna banco (anos 1990, sem ato datado) |
| fam1 | 5 | c. 1991 | Henrique Vorcaro funda o Grupo Multipar, há cerca de 35 anos segundo o site do grupo (c. 1991) |
| ida2 | 6 | 2000 | Igreja assume a TV que vira Rede Super; Lagoinha tem rádio e TV próprias |
| ida3 | 7 | 2000 | Henrique Vorcaro teria sido um dos principais financiadores da Rede Super |
| ida4 | 8 | 2000 | Henrique Vorcaro é descrito como convertido que financiou projetos da igreja |
| fam2 | 9 | c. 2003 | Daniel, aos 19 ou 20 anos, atua em negócio de educação da família |
| ida5 | 10 | 2008 | Daniel Vorcaro apresenta programa gospel na Rede Super |
| max2 | 11 | 2009-11-11 | BC aprova diretor da Máxima S.A. CTVM; corretora e banco são CNPJs distintos |
| max3 | 12 | 2010-01-11 | Cristiano Abdalla declara propósito de ser diretor adjunto da Máxima CTVM |
| fam3 | 13 | 2011-10-20 | Estado de Minas: obra de hotel de luxo no Bulevar Arrudas, com a Multipar |
| max4 | 14 | 2013-08 | Moody's rebaixa notas do Banco Máxima (ago/2013) |
| max5 | 15 | 2013-09-26 | Máxima compra carteiras imobiliárias de incorporadoras; carteira de R$ 250 mi |
| max6 | 16 | 2014-11 | Fundo Ravena e FC Max: operação que o MPF diz ter inflado o resultado do banco (nov/2014) |
| fam4 | 17 | 2014 | Daniel é negativado no Serasa por dívida com escritório de advocacia |
| max7 | 18 | 2015-01 a 2016-03 | Acusação do MPF: informações incorretas ao BC para ocultar falta de capital (jan/2015 a mar/2016) |
| max8 | 19 | 2015-07 | Holding da família Vorcaro teria contrato para comprar ações do banco (jul/2015) |
| max9 | 20 | 2016 | Crise de inadimplência na carteira imobiliária e risco de liquidação, segundo reportagens (2016) |
| max10 | 21 | 2016 | Sabbá oferece a Vorcaro participação no controle do banco (2016) |
| fam6 | 22 | 2017-08 | Daniel entra no Máxima com 20% como participação qualificada |
| max11 | 23 | 2017-09-15 | Contrato de compra e venda do controle entre Sabbá e Vorcaro (15/09/2017) |
| max12 | 24 | 2017-11-01 | BC publica declaração de propósito; sede do banco era em Copacabana (RJ) |
| fam8 | 25 | 2017-11 | Minutas de 2016-2017 previam sociedade de Henrique no Máxima, diz O Fator |
| max13 | 26 | 2017 | Sabbá diz ter se desligado formalmente da gestão em 2017 |
| max14 | 27 | 2018-01 | Nova diretoria assume em janeiro de 2018 (versão do banco) |
| fam10 | 28 | 2018-04 | Bahia regulamenta por decreto, em abril de 2018, o consignado Credcesta, depois ligado ao Master |
| fam11 | 29 | 2018-06-28 | Negócios de cotas do fundo CARE11 em 28 e 29/6/2018 viram caso na CVM |
| max15 | 30 | 2018-07-27 | BC multa o banco e inabilita Sabbá (9 anos) e Caló (8 anos) |
| ida6 | 31 | 2018 | André Valadão celebra casamento de Fabiano Zettel e Natália Vorcaro |
| max18 | 32 | 2019 a 2020 | CVM: parecer de 21/10/2020 sobre debêntures da C.I.P. e da Simsan colocadas pela Máxima CCTVM (ofertas de 2019) |
| fam13 | 33 | 2019-01-16 | Sete novos sócios aparecem no quadro do Máxima, entre eles Augusto Lima |
| max16 | 34 | 2019-02-13 | BC rejeita a compra do controle por Vorcaro (voto 20/2019, 13/02/2019) |
| fam16 | 35 | 2019-05-02 | Novo pedido ao BC, com Simonsen e Gallo, e aportes de R$ 100 mi até junho |
| max17 | 37 | 2019-10-14 | BC aprova a mudança de controle (voto 218/2019, 14/10/2019) |
| fam19 | 38 | 2019-10-29 | Mandado de prisão preventiva de cinco dias expedido em Ji-Paraná (RO) |
| fam15 | 39 | 2019 | Fontes dizem que a má reputação da família em BH dominou a discussão no BC; o voto não a analisou |
| fam20 | 40 | 2019 | Delação de 2019 cita captação de R$ 100 mi de fundos de pensão para o hotel |
| fam23 | 41 | 2020-09-08 | Hapvida compra o grupo Promed por R$ 1,5 bi; Máxima assessora |
| max19 | 42 | 2020-11-17 | CRSFN pautado para julgar recurso do Banco Máxima, Sabbá e Caló |
| max20 | 43 | 2020-11-17 | CRSFN: pauta inclui segundo recurso, de Máxima CCTVM, Abdalla, Gonçalves e Sabbá |
| fam24 | 44 | 2020-12-01 | CVM: voto de 1º/12/2020 defende aceitar termo de compromisso de R$ 2,325 mi no caso das debêntures |
| fam21 | 45 | 2020 | Augusto Lima, dono do Credcesta, entra na sociedade do Master em 2020, segundo a CNN |
| fam22 | 46 | 2020 | Maurício Quadrado associa-se ao Master para tocar o banco de investimento |
| fam25 | 47 | 2020 | Máxima (futuro Master) adquire o banco de investimento Vipal (fim de 2020; ainda sob análise do BC em mai/2021) |
| max21 | 48 | 2021-07-24 | Justiça Federal recebe denúncia do MPF e torna réus cinco acusados ligados ao Máxima (reportado em 24/07/2021) |
| max22 | 50 | 2021-08-02 | Máxima passa a se chamar Banco Master (reportagem de 02/08/2021) |
| fam27 | 51 | 2021-12-23 | Brazil Journal: Master vira 'banco de investimento e merchant bank' |
| ida9 | 53 | 2022-03 | Coaf: R$ 3,9 mi do Banco Master a produtora de André Valadão (negado) |
| ida7 | 54 | 2022-10-20 | Nikolas Ferreira e o pastor Guilherme Batista voam em jato ligado a Vorcaro; Lagoinha diz que o pastor não é membro |
| ida8 | 55 | 2022-12-11 | Márcio deixa a liderança; André Valadão assume a Lagoinha Global |
| ida10 | 58 | 2024-03 | Clava Forte Bank, fintech de André e Cassiane Valadão |
| vol3 | 59 | 2024-03 | Valadão e a esposa fundam o Clava Forte Bank, fintech cristã |
| vol4 | 60 | 2024-04-27 | Vorcaro pede a Valadão que fale com Nikolas sobre críticas ao Master |
| ida11 | 63 | 2024-09 | Lagoinha Belvedere: CNPJ aberto em setembro de 2024 e templo de alto padrão presidido por Zettel |
| vol7 | 65 | 2024-10 | Folha: Zettel fez 54 repasses de R$ 40,9 milhões à unidade Belvedere |
| ida12 | 67 | 2024-12-24 | Coaf: Zettel enviou R$ 19,2 mi à conta da Lagoinha Belvedere |
| ida13 | 68 | 2024-12-24 | Coaf: Henrique Vorcaro fez R$ 120 mil em aportes à Lagoinha Belvedere |
| ida14 | 69 | 2024-12-24 | Coaf: ex-mulher de Daniel e duas empresas também aparecem entre os remetentes da conta |
| ida17 | 74 | 2025-04 | Valadão chama Henrique e Aline Vorcaro de 'amigos da minha vida' |
| ida16 | 78 | 2025-07 | Mensagens reportadas: Zettel teria cobrado Vorcaro por recursos para a obra do Belvedere |
| vol10 | 95 | 2025-11-25 | CPMI do INSS: Rogério Correia pede quebra de sigilo de Valadão |
| ida18 | 97 | 2025-11 | Lagoinha diz ter afastado Zettel do pastoreio; prisões e nota de janeiro |
| ida15 | 99 | 2025-12-08 | Coaf e Banco do Brasil apontam movimentação atípica de R$ 57,1 mi (créditos e débitos) na conta da Belvedere |
| vol12 | 107 | 2026-01-15 | Lagoinha publica nota: não é parte de investigação e afastou Zettel |
| vol13 | 108 | 2026-01-15 | Damares divulga lista de requerimentos da CPMI; Valadão e Zettel aparecem |
| vol14 | 116 | 2026-01-27 | Valadão nega negócios com Vorcaro e diz que o conhece da igreja |
| vol17 | 126 | 2026-03-10 | Lagoinha responde ao O Globo: relações são pessoais entre famílias |
| ida19 | 128 | 2026-03-15 | Lagoinha Belvedere encerra atividades |
| vol21 | 130 | 2026-03-19 | Dino cobra Viana sobre R$ 3,6 mi em emendas à Fundação Oásis, da Lagoinha |
| ida20 | 131 | 2026-03-22 | Valadão pede perdão por ter confiado em pessoas e nega vínculo |
| vol23 | 132 | 2026-03-24 | Zettel declarou R$ 190,2 mi em lucros do fundo Kairós, ligado à Super Empreendimentos |
| vol28 | 160 | 2026-09-14 | STF abre sigilo e Coaf sobre a Belvedere vem a público |

## 4. Colisões de slug

Entidades: nenhuma.

Eventos (sufixo `-2`, `-3`...): 3
- dossie.brb[8]: `ev-2024-12-04-lula-recebe-vorcaro-no-planalto-fora-da` → `ev-2024-12-04-lula-recebe-vorcaro-no-planalto-fora-da-2`
- dossie.brb[12]: `ev-2025-05-27-btg-compra-r-1-5-bi-em-ativos-de-vorcaro` → `ev-2025-05-27-btg-compra-r-1-5-bi-em-ativos-de-vorcaro-2`
- Y[2020].intl.eventos[0]: `ev-2020-pandemia-de-covid-19` → `ev-2020-pandemia-de-covid-19-2`

## 5. Fusões automáticas (slug exato / alias único) com entidades já existentes

- `Michel Temer` → `michel-temer` (entidade de origem `teia`)
- `Luiz Inácio Lula da Silva` → `luiz-inacio-lula-da-silva` (entidade de origem `teia`)
- `Eduardo Bolsonaro` → `eduardo-bolsonaro` (entidade de origem `teia`)
- `Flávio Bolsonaro` → `flavio-bolsonaro` (entidade de origem `teia`)
- `Jair Bolsonaro` → `jair-bolsonaro` (entidade de origem `teia`)
- `Davi Alcolumbre` → `davi-alcolumbre` (entidade de origem `teia`)
- `Jaques Wagner` → `jaques-wagner` (entidade de origem `teia`)
- `Nikolas Ferreira` → `nikolas-ferreira` (entidade de origem `teia`)
- `Hugo Motta` → `hugo-motta` (entidade de origem `teia`)
- `BTG Pactual` → `btg-pactual` (entidade de origem `teia`)

## 6. Candidatos a dedup (para aprovação; aprovados vão em `scripts/fusoes.json`)

| slug A | slug B | nome A | nome B | critério |
|---|---|---|---|---|
| dias-toffoli | irmaos-de-toffoli | Dias Toffoli | Irmãos de Toffoli (José Carlos e José Eugênio Dias Toffoli) | tokens ⊂ + mesmo sobrenome |
| paulo-sergio-neves-de-souza | luis-roberto-irmao-de-paulo-sergio-neves-de-souza | Paulo Sérgio Neves de Souza | Luis Roberto (irmão de Paulo Sérgio Neves de Souza) | tokens ⊂ + mesmo sobrenome |

Aliases ambíguos (mesmo `alias_norm` em mais de uma entidade; fora de `indice_alias`):

- `telesp`: telefonica-brasil, telesp

## 7. URLs normalizadas (evidência)

Regra: strip de `#fragment`, barra final e parâmetros `utm_*`. Nada mais (host e esquema intactos).

- URLs normalizadas distintas (linhas em `evidencia`): 1116
- URLs originais distintas: 1116
- Normalizações que alteraram a URL: 375
- Colisões (2+ URLs originais → 1 normalizada): 0

Alteradas sem colisão: 375 só pela barra final (não listadas) e 0 por `#fragment`/`utm_*`/outros:


Quase-colisões (mesma URL base, queries diferentes; mantidas distintas): 8

- `https://bpmoney.com.br/?p=154390` , `https://bpmoney.com.br/?p=385085` , `https://bpmoney.com.br/?p=385092` , `https://bpmoney.com.br/?p=420995`
- `https://iclnoticias.com.br/?p=109117` , `https://iclnoticias.com.br/?p=110036` , `https://iclnoticias.com.br/?p=111826` , `https://iclnoticias.com.br/?p=127728` , `https://iclnoticias.com.br/?p=129374`
- `https://jovempan.com.br/?p=291021` , `https://jovempan.com.br/?p=5429`
- `https://www.brasil247.com/?p=1049476` , `https://www.brasil247.com/?p=1049764` , `https://www.brasil247.com/?p=263632` , `https://www.brasil247.com/?p=626399` , `https://www.brasil247.com/?p=876131` , `https://www.brasil247.com/?p=927102` , `https://www.brasil247.com/?p=940854` , `https://www.brasil247.com/?p=943810` , `https://www.brasil247.com/?p=945134` , `https://www.brasil247.com/?p=949224`
- `https://www.cartacapital.com.br/?p=493025` , `https://www.cartacapital.com.br/?p=587967` , `https://www.cartacapital.com.br/?p=636191` , `https://www.cartacapital.com.br/?p=79516`
- `https://www.infomoney.com.br/?p=1412193` , `https://www.infomoney.com.br/?p=3107708` , `https://www.infomoney.com.br/?p=3107925` , `https://www.infomoney.com.br/?p=3107979` , `https://www.infomoney.com.br/?p=3165413` , `https://www.infomoney.com.br/?p=3174200` , `https://www.infomoney.com.br/?p=3175363` , `https://www.infomoney.com.br/?p=3182375` , `https://www.infomoney.com.br/?p=3194419` , `https://www.infomoney.com.br/?p=3263363` , `https://www.infomoney.com.br/?p=3302923` , `https://www.infomoney.com.br/?p=3377440` , `https://www.infomoney.com.br/?p=357219` , `https://www.infomoney.com.br/?p=422330`
- `https://www.sedep.com.br/?p=150753` , `https://www.sedep.com.br/?p=168820`
- `https://www.suno.com.br/noticias/?p=52455` , `https://www.suno.com.br/noticias/?p=53367` , `https://www.suno.com.br/noticias/?p=538608` , `https://www.suno.com.br/noticias/?p=599920`

URLs repetidas dentro da mesma relação/evento após normalização (descartadas na junção): 0

## 8. Outras decisões e avisos

- Relações da teia sem nenhuma fonte: 0.
- `fam_de` (21) e `lig_de` (3) viram relações `familiar`/`profissional` (subtipo `escritorio_ligado`) com `natureza_id='nao_classificada'` (NULL não é permitido em `relacao`), `direcional=0`, sem fontes.
- Pseudo-partidos de `N.p` ("Ex-ministros e consultores", "Órgãos e partidos") foram para `entidade.grupo`; `partido` guarda só siglas reais. O exportador reconstrói `p` quando `grupo` é um pseudo-partido, senão `sg`.
- `E.a/E.b` do `teia.json` exportado reproduz a orientação ORIGINAL de cada par (tabela `aresta_legado`; a cor da aresta na página depende dela). A direção semântica vem de `relacao.de/para` (`r.a→r.b`). Índices `E[i]` e `r[j]` preservados.
- Eventos de origens com `r` vazio gravam `resposta` NULL (exportam de volta como ""); `v` vai para `evento.valor_brl` (a proposta mapeava `r`→`contexto` e `v`→`resposta`, o que invertia o significado).
- Eventos da timeline Brasil (280): `data` = ano do agrupamento, canal `brasil` (subcanal `pol`/`intl` em `origem_ref`); na carga bruta sem fonte e sem natureza (as fontes entram pela curadoria, seção 11).
- `pares.notas`: linhas de log de coleta descartadas (1): "Cota: 39 buscas/fetches usados."
- `pares.indicadores`: valores `null` explícitos (ex.: IDH) não viram linha em `serie`; só os pontos não nulos.
- `pares.foruns` e as seções estruturadas do dossiê (mercado, previdência, dinheiro, limites, máquina) deixaram de ir para `nota.texto`: viraram tabelas relacionais (seção 13); a seção `brb.eventos` virou 30 eventos canal `brb`.
- URLs dentro de `nota.texto` do dossiê (`previdencia.fonte`, `dinheiro.fonte`) não passam por `evidencia`; as fontes de `mercado.pares` e `brb.eventos` passam.
- `mandato`: presidentes/vices/presidentes das casas são agregados por anos consecutivos (granularidade de ano; Dilma/Temer em 2016 usam 12/5); `partido` = valor do primeiro ano do período. Parlamentares em destaque (`pol.parl`) viram `mandato` de um ano (`inicio=fim=ano`) com `motivo` e `votos`.
- `ranking_empresa.posicao` = posição na lista do ano (a lista original não traz posição explícita).
- Países em `pares` viram entidades `pais` (alias sigla = ISO3); `serie.dimensao` usa `pais=<ISO3>`. Destinos de exportação usam `pais=<nome>` (sem ISO na fonte).
- `serie` de pares = pontos não nulos dos 18 indicadores (4.806) + PISA (leitura/matemática/ciências e matemática por estado da Índia).
- Desvios do DDL proposto (marcados `-- DESVIO:` em `scripts/schema.sql`): o DDL original roda sem erro no SQLite 3.45 (incl. STRICT, colunas geradas e FTS5); acrescentados `entidade.ind_legado`, `evento.valor_brl`, `evento.canal='brb'`, `evento.origem='dossie'`, `ordem` em `relacao_evidencia`/`evento_evidencia`/`evento_entidade`/`nota_entidade`, `mandato.motivo`/`mandato.votos`; `evento.contexto`/`resposta` passam a significar o que os dados dizem (ver acima). Rodada de modelo (seções 14 a 16): `tema`/`relacao_tema`/`evento_tema`/`v_entidade_tema`, `fonte` no lugar de `video` (e `trecho.fonte_id`), `relacao.origem='linha_do_tempo'`.
- Passo 3 do plano (ligar eventos a entidades por alias): feito pela curadoria, seção 12. Continua não feita a extração de eventos a partir de datas internas de `N.d`/`desc`.
- `evento_evidencia.rotulo` (desvio) guarda o rótulo da fonte como veio no original; `evidencia.veiculo` guarda só o do primeiro uso da URL. O exportador usa o rótulo.

## 9. Eventos quase-duplicados fundidos (`data/curadoria/eventos-fusoes.json`)

23 fusões, 32 eventos absorvidos: 539 -> 507 eventos. Regra: mesma `data` e mesmo fato. O evento `manter` conserva o id e recebe a união de fontes (`evento_evidencia`) e entidades (`evento_entidade`), `peso` máximo, a natureza mais forte entre os que têm natureza e descrição/contexto/resposta/valor do mantido (ou do primeiro fundido que tenha). Os ids fundidos viram `evento_alias(alias, evento_id)` e guardam o evento original em `original_json` (título, descrição, data, natureza, fontes com rótulo, entidades). `mapa_indices.json` aponta os índices antigos de `teia.EV` (e `evento_alias`) para o id mantido. Os candidatos duvidosos estão em `data/curadoria/eventos-candidatos.md`.

| data | mantido | fundidos | natureza resultante | fontes novas | entidades novas |
|---|---|---|---|---|---|
| 2019-02-13 | `max16` | `ev-2019-02-13-bc-nega-a-compra-do-maxima-por-vorcaro` | documentada | 0 | 0 |
| 2019-10-14 | `max17` | `ev-2019-10-14-bc-aprova-a-compra-ja-com-nova-diretoria`, `ev-2019-10-14-bc-aprova-controle-do-maxima-por-vorcaro` | documentada | 1 | 1 |
| 2021-08-02 | `max22` | `ev-2021-08-02-maxima-relanca-se-como-banco-master` | documentada | 2 | 0 |
| 2024-07 | `ev-2024-07-brb-comeca-a-comprar-carteiras-de` | `ev-2024-07-brb-comeca-a-comprar-carteiras-do-master` | reportada | 1 | 0 |
| 2024-12-04 | `ev-2024-12-04-lula-recebe-vorcaro-no-planalto-fora-da` | `ev-2024-12-04-lula-recebe-vorcaro-no-planalto-fora-da-2` | documentada | 1 | 0 |
| 2025-03-28 | `ev-2025-03-28-brb-anuncia-compra-de-58-do-master` | `ev-2025-03-28-conselho-do-brb-aprova-comprar-58-do` | documentada | 1 | 0 |
| 2025-05-27 | `ev-2025-05-27-btg-compra-r-1-5-bi-em-ativos-de-vorcaro` | `ev-2025-05-27-btg-compra-r-1-5-bi-em-ativos-de-vorcaro-2` | reportada | 1 | 0 |
| 2025-07-15 | `ev-2025-07-15-bc-comunica-ao-mpf-indicios-de-crimes-na` | `ev-2025-07-15-bc-comunica-ao-ministerio-publico` | reportada | 0 | 0 |
| 2025-09-03 | `ev-2025-09-03-bc-veta-a-compra-do-master-pelo-brb` | `ev-2025-09-03-banco-central-rejeita-a-compra-do-master`, `ev-2025-09-03-banco-central-veta-a-compra-por` | documentada | 3 | 0 |
| 2025-11-17 | `ev-2025-11-17-fictor-anuncia-compra-do-master-vorcaro` | `ev-2025-11-17-fictor-e-investidores-dos-emirados` | documentada | 1 | 0 |
| 2025-11-18 | `ev-2025-11-18-bc-decreta-a-liquidacao-extrajudicial-do` | `ev-2025-11-18-banco-central-liquida-o-master`, `ev-2025-11-18-bc-liquida-o-banco-master-pf-faz-buscas`, `ev-2025-11-18-bc-liquida-o-master-pf-deflagra-a`, `ev-2025-11-18-bc-liquida-o-master-vorcaro-e-preso` | documentada | 7 | 4 |
| 2026-01-14 | `ev-2026-01-14-2a-fase-da-compliance-zero-bloqueia-r-5` | `ev-2026-01-14-2a-fase-buscas-bloqueio-de-r-5-7-bi-e` | - | 3 | 1 |
| 2026-01-15 | `ev-2026-01-15-bc-decreta-liquidacao-da-reag-trust-cbsf` | `ev-2026-01-15-bc-liquida-a-reag-cbsf-dtvm` | - | 0 | 2 |
| 2026-01-17 | `ev-2026-01-17-fgc-inicia-o-maior-ressarcimento-de-sua` | `ev-2026-01-17-fgc-comeca-a-pagar-garantia-a-credores`, `ev-2026-01-17-fgc-inicia-pagamento-a-cerca-de-800-mil` | - | 1 | 1 |
| 2026-01-23 | `ev-2026-01-23-pf-deflagra-barco-de-papel-castro` | `ev-2026-01-23-pf-faz-a-operacao-barco-de-papel-no` | - | 1 | 0 |
| 2026-03-04 | `ev-2026-03-04-3a-fase-vorcaro-e-preso-de-novo` | `ev-2026-03-04-vorcaro-e-preso-de-novo-pf-mira-ex`, `ev-2026-03-04-vorcaro-e-preso-decisao-cita-r-2-2-bi-na` | - | 3 | 3 |
| 2026-03-28 | `vol24` | `ev-2026-03-28-cpmi-do-inss-termina-sem-relatorio-final` | documentada | 2 | 3 |
| 2026-04-16 | `ev-2026-04-16-ex-presidente-do-brb-paulo-henrique` | `ev-2026-04-16-4a-fase-ex-presidente-do-brb-e-preso`, `ev-2026-04-16-ex-presidente-do-brb-e-preso`, `ev-2026-04-16-ex-presidente-do-brb-e-preso-pf-cita` | investigacao | 6 | 4 |
| 2026-05-07 | `ev-2026-05-07-pf-faz-buscas-contra-o-senador-ciro` | `ev-2026-05-07-5a-fase-senador-ciro-nogueira-e-alvo` | - | 1 | 2 |
| 2026-05-28 | `ev-2026-05-28-uniao-e-gdf-acordam-emprestimo-de-ate-r` | `ev-2026-05-28-acordo-no-stf-abre-caminho-para` | documentada | 1 | 0 |
| 2026-06-18 | `ev-2026-06-18-9a-fase-jaques-wagner-e-augusto-lima-sao` | `ev-2026-06-18-9a-fase-da-compliance-zero-tem-jaques` | - | 1 | 1 |
| 2026-09-01 | `ev-2026-09-01-mendonca-levanta-sigilo-de-relatorio-da` | `ev-2026-09-01-mendonca-tira-sigilo-de-relatorio-da-pf` | - | 3 | 0 |
| 2026-09-15 | `ev-2026-09-15-plenario-do-stf-comeca-a-analisar` | `ev-2026-09-15-plenario-do-stf-discute-moraes-e` | - | 3 | 1 |

Eventos absorvidos por canal de origem: brb 12, precatorios 1, teia 19.

## 10. Natureza dos eventos sem `st` (`data/curadoria/eventos-natureza.json`, `eventos-natureza-manual.json`)

Regras determinísticas (`scripts/curadoria.py`, `classificar_natureza`; o arquivo é regenerado por `scripts/gerar_curadoria.py`). Só atribui onde `natureza_id IS NULL`; nada é inventado. R1-R4 valem para a `teia`; **R5** cobre os eventos factuais da linha do tempo (`brasil`, `violencia`) pelo tipo/domínio das evidências com papel `sustenta`; o que as regras não pegam na teia foi classificado à mão (`M`).

```
R1  todas as fontes do evento são documento oficial (domínios .gov.br/gov.br, .jus.br, .leg.br, okai.com.br; PDFs em static.poder360.com.br) -> documentada
R2  o título começa por verbo de autoridade sobre ato formal consumado (BC liquida/decreta/veta/rejeita/aprova/nega/autoriza; STF torna pública/decide/julga/suspende/homologa;
    PF prende; Justiça homologa/nega/decreta/reconhece/afasta/bloqueia; CVM multa/condena; Câmara/Senado/CLDF/Congresso aprova/rejeita/promulga;
    Mendonça/Toffoli/Fachin/Dino/Moraes/Gilmar/Nunes Marques/Fux/Zanin autoriza/afasta/levanta/tira/suspende/determina/manda/concede/nega/decreta/homologa)
    e há 2 ou mais fontes de imprensa (ato público noticiado por 2+ veículos) -> documentada
R3  o título tem 'PF aponta/diz/suspeita', 'relatório da PF', 'indicia', 'alvo(s)', 'busca(s)' ou 'denúncia/denuncia(r)' -> investigacao
R4  o título começa por 'Folha liga' ou tem 'revelado/revelada', 'mensagens', 'teria', 'segundo' -> reportada
--  nenhuma das anteriores: continua NULL (nada é inventado)
Precedência: R1, R2, R3, R4. R1-R4 só se aplicam a eventos do canal 'teia' com natureza_id NULL.
R5  (canais 'brasil' e 'violencia', eventos factuais da linha do tempo; olha o tipo e o domínio das evidências ligadas ao evento com papel 'sustenta'):
    ao menos uma evidência documento_oficial/dado_oficial/decisao_judicial/comunicado (ou domínio oficial pela lista de R1; `comunicado` = nota de órgão público, como press release do Fed ou da ONU, desde a rodada 3) -> documentada;
    senão, ao menos uma reportagem/relatorio -> reportada;
    senão (só wiki/outro/video, só fonte de papel 'contexto' ou nenhuma fonte) -> nao_classificada.
    Fontes 'contexto' (as URLs do bloco-ano de brasil-fontes.json, que o bruto não separa por evento) NÃO contam: não sustentam o fato do evento.
    Muda-se isso em R5_PAPEIS.
R6  (global; data/curadoria/regras-fontes.json, decisão do dono do projeto de 18/10/2026): fonte Wikipédia (evidencia.tipo 'wiki' ou domínio
    *.wikipedia.org) nunca tem papel 'sustenta'; em evento_evidencia e relacao_evidencia é sempre 'contexto' (qualidade NULL: contexto não é
    avaliado). Aplicada por aplicar_peso_wikipedia depois de todas as cargas de evidência e antes de gerar a natureza: a wiki não conta em R5,
    nem no 'Fontes (n)' das páginas, e é exportada por último. Nenhum evento ou relação pode depender só de wiki (a migração aborta).
R7  (ranking_empresa; data/curadoria/regras-fontes.json, decisão do coordenador do projeto de 18/10/2026): base do lucro. Para instituições financeiras a
    'legislação societária' é o BR GAAP/COSIF exigido pelo Bacen (o lucro de manchete de Itaú, Bradesco, BB e o 2,69 do Santander 2012); o IFRS dos
    20-F é sempre `contexto` para bancos. Para não financeiras vale o IFRS a partir de 2010. Recorrente/gerencial/ajustado, US GAAP, reapresentações e
    conversões de US$ também só `contexto`. Aplicada a partir da rodada 10 (ranking-empresa-correcoes-r10.json).
M   os eventos da teia que R1-R4 não pegam foram lidos um a um (título, descrição, fontes) e classificados à mão em data/curadoria/eventos-natureza-manual.json
    ([{"id","natureza","justificativa"}]), aplicado depois do gerado e só onde natureza_id IS NULL; entrada com "natureza": null é exceção explícita
    (fica NULL, a justificativa é obrigatória).
```

- Atribuídas por regra: 314 (arquivo com 314). Por regra: R1 1, R2 10, R3 9, R4 2, R5 292. Por natureza: documentada 185, investigacao 9, reportada 120.
- Por regra, efetivamente aplicadas: R1 1, R2 10, R3 9, R4 2, R5 292.
- R5 por canal e natureza: brasil/documentada 164, brasil/reportada 118, violencia/documentada 10.
- Classificação manual (`eventos-natureza-manual.json`): 41 entradas, 41 aplicadas (alegacao 5, investigacao 11, reportada 25), 0 ignoradas (já tinham natureza), 0 exceções explícitas (ficam NULL).
- Dos 92 eventos da teia sem `st`: 19 foram absorvidos em fusões (seção 9) e os demais, somados aos mantidos, são os 73 eventos `teia` atuais. Destes, 63 ganharam natureza pelas regras R1-R4 ou à mão, 10 ficaram com a natureza mais forte do grupo fundido (dossiê BRB, PREC ou origens) e 0 seguem NULL.
- **Ficaram NULL: 0 eventos do canal `teia`** (lista abaixo; `validar.py` exige zero ou exceção explícita no arquivo manual). Eventos `brasil` e `violencia` NULL: 0.

| id | data | título | fontes |
|---|---|---|---|

## 11. Fontes da timeline Brasil (`data/curadoria/brasil-fontes.json`, de `data/raw/dados-brutos-31-anos.json`)

`data/raw/dados-brutos-31-anos.json` entrou em `data/raw/` com hash em `hashes.txt` (única exceção à regra de não mexer no raw: cópia de `projeto-json/`, sem alteração). Cada evento da timeline foi casado com o item do bruto de mesmo ano e seção (`pol`: blocos `v2_pol_eventos_*` e `v4_pol_*`; `intl`: `v2_intl_eventos_*`) por título igual (Jaccard >= 0,6 era o plano B; nenhum caso precisou). **O bruto só tem a lista `fontes` por ano e bloco, não por evento**: por isso toda URL do bloco-ano entra em `evento_evidencia`, como `contexto`; entra como `sustenta` só quando um termo distintivo do slug da URL aparece no título/descrição do evento (heurística conservadora; `url_toca_evento`).

- Eventos casados: 221 de 280; sem fonte: 59.
- Ligações novas em `evento_evidencia`: 2397 (149 `sustenta`, 2248 `contexto`).
- Sem item no bruto (o bruto não traz o primeiro ano de cada bloco de eventos): . Ficam sem fonte.
- URLs de `evidencia` agora: 1738 (todas ligadas a alguma coisa; `validar.py` confere).
- `ranking_empresa.receita_brl_bi`: 91 das 397 linhas da carga bruta preenchidas (a rodada 6, seção 23, acrescenta linhas sem receita). Mapeamento inequívoco = mesmo ano, mesmo lucro e mesma fonte ou nome; onde o bruto repete a empresa em dois blocos com receita nula num e valor no outro, vale o valor; conflito de dois valores diferentes: 0. As outras 306 linhas têm `receita_liquida_brl_bi` nulo no bruto.
- `mandato.periodo_texto`: 30 mandatos de presidente da Câmara/Senado (nome + ano em `v2_pol_estrutura`/`v4_estrutura.presidencias`; textos de anos diferentes do mesmo mandato unidos por ` | `); sem correspondência: 0.
- **Do bruto não carregado** (sem mapeamento inequívoco ou sem tabela): `lideres` (líderes de governo e de bancada por ano, `v2_pol_estrutura` e `v4_estrutura`); `legislaturas` e `senado` com bancadas e as notas de método (`camara_base`, `senado_base`); `notas` de cada ano/bloco (limites da coleta, itens 'NÃO CONFIRMADO'); `maiores_prejuizos` só entra quando a empresa já está no ranking publicado; `exportacoes_total_wits_usd_mi`; e as `fontes` dos blocos macro, setores, comércio, intl e estrutura (262 URLs únicas ainda fora de `evidencia`, porque a fonte vale para o bloco-ano inteiro e `serie` tem uma única `evidencia_id` por ponto).

## 12. Ligação evento -> entidade por alias (`data/curadoria/evento-entidade-auto.json`)

Candidatos: eventos sem nenhuma linha em `evento_entidade` (origens, PREC, brb, brasil, violência). Casamento de `titulo + descricao` com `entidade_alias` (só `alias_norm` único no banco), palavra inteira, normalizado sem acento, alias mais longo primeiro e sem sobreposição, `papel='citado'`. Regras em `data/curadoria/evento-entidade-regras.json`:

- alias de pessoa com um só token só vale se estiver em `pessoa_um_token_ok` (lula, dilma, fhc, temer); sobrenomes ambíguos barrados sozinhos: costa, silva, mendonca, nunes, santos, souza, oliveira, lima, pereira, alves, rocha, moraes, neto, filho, junior, ferreira, ribeiro, carvalho, gomes, barbosa, martins, campos, fernandes, sousa, dias, castro, cunha.
- siglas (alias em maiúsculas ou `tipo_alias='sigla'`) só em maiúsculas e não seguidas de número (evita 'PL 2338' e 'pl').
- entidades excluídas: brasil (aparece em tudo). Exigem inicial maiúscula: vale, rede, caixa, senado, camara. Contextos barrados: 'camara' seguido de do/legislativa/municipal/distrital; 'vale' seguido de do/da/de; 'caixa' seguido de de; 'senado' precedido de radio; 'camara' precedido de radio.

- Resultado: 206 eventos receberam ligação, 426 linhas novas em `evento_entidade`.
- Eventos ainda sem entidade por canal: banco 2, brasil 126, brb 5, familia 2, precatorios 10, teia 1, violencia 9.

Aliases com mais de 15 ligações (suspeitos por volume; são nomes de órgãos e partidos que aparecem muito nos textos da timeline; a amostra abaixo não achou falso positivo entre eles, mas vale conferir os eventos):

| ligações | entidade | alias casado |
|---|---|---|
| 37 | `senado-federal` (Senado Federal) | Senado |
| 35 | `camara-dos-deputados` (Câmara dos Deputados) | Câmara |
| 32 | `stf` (Supremo Tribunal Federal) | STF |
| 18 | `pt` (PT) | PT |

Amostra de 30 ligações para conferência (a cada k-ésima, em ordem de evento):

| evento | título | alias -> entidade |
|---|---|---|
| `max23` | CRSFN pauta recurso de Sabbá e das empresas Máxima em processo da CVM | CVM -> `cvm` |
| `ev-1997-novas-mesas-da-camara-e-do-senado` | Novas Mesas da Câmara e do Senado | Câmara -> `camara-dos-deputados` |
| `ev-1998-fhc-e-reeleito-no-primeiro-turno` | FHC é reeleito no primeiro turno | PPS -> `pps` |
| `ev-2000-cassacao-do-senador-luiz-estevao` | Cassação do senador Luiz Estêvão | Senado -> `senado-federal` |
| `ev-2001-jader-barbalho-deixa-a-presidencia-do` | Jader Barbalho deixa a presidência do Senado | PMDB -> `mdb` |
| `ev-2002-lula-e-eleito-presidente` | Lula é eleito presidente | PSDB -> `psdb` |
| `ev-2003-sarney-volta-a-presidencia-do-senado` | Sarney volta à presidência do Senado | PMDB -> `mdb` |
| `ev-2005-eleicao-e-renuncia-de-severino` | Eleição e renúncia de Severino Cavalcanti | Severino Cavalcanti -> `severino-cavalcanti` |
| `ev-2006-sancionada-a-lei-maria-da-penha` | Sancionada a Lei Maria da Penha | Lula -> `luiz-inacio-lula-da-silva` |
| `ev-2008-operacao-satiagraha-prende-daniel-dantas` | Operação Satiagraha prende Daniel Dantas | Polícia Federal -> `pf` |
| `ev-2009-stf-mantem-a-demarcacao-da-raposa-serra` | STF mantém a demarcação da Raposa Serra do Sol | STF -> `stf` |
| `ev-2012-argentina-reestatiza-a-petroleira-ypf` | Argentina reestatiza a petroleira YPF | Câmara -> `camara-dos-deputados` |
| `ev-2013-camara-mantem-o-mandato-de-natan-donadon` | Câmara mantém o mandato de Natan Donadon | Câmara -> `camara-dos-deputados` |
| `ev-2014-reeleicao-de-dilma-rousseff` | Reeleição de Dilma Rousseff | PT -> `pt` |
| `ev-2015-eduardo-cunha-assume-a-camara` | Eduardo Cunha assume a Câmara | Arlindo Chinaglia -> `arlindo-chinaglia` |
| `ev-2016-pec-do-teto-de-gastos-vira-a-emenda` | PEC do teto de gastos vira a Emenda Constitucional 95 | Câmara -> `camara-dos-deputados` |
| `ev-2017-primeira-greve-geral-em-cerca-de-20-anos` | Primeira greve geral em cerca de 20 anos | Temer -> `michel-temer` |
| `ev-2019-alberto-fernandez-derrota-macri-na` | Alberto Fernández derrota Macri na Argentina | Argentina -> `argentina` |
| `ev-2021-atos-de-7-de-setembro-e-carta-de` | Atos de 7 de Setembro e carta de Bolsonaro | Alexandre de Moraes -> `alexandre-de-moraes` |
| `ev-2021-lira-e-pacheco-sao-eleitos-presidentes` | Lira e Pacheco são eleitos presidentes das Casas | Câmara -> `camara-dos-deputados` |
| `ev-2022-lula-derrota-bolsonaro-na-eleicao` | Lula derrota Bolsonaro na eleição presidencial | PT -> `pt` |
| `ev-2023-ataques-de-8-de-janeiro-em-brasilia` | Ataques de 8 de janeiro em Brasília | STF -> `stf` |
| `ev-2023-tse-torna-bolsonaro-inelegivel-por-oito` | TSE torna Bolsonaro inelegível por oito anos | Jair Bolsonaro -> `jair-bolsonaro` |
| `ev-2024-presos-por-suposto-plano-de-golpe-pf` | Presos por suposto plano de golpe; PF indicia Bolsonaro | Jair Bolsonaro -> `jair-bolsonaro` |
| `ev-2025-tarifas-dos-eua-sobre-o-brasil` | Tarifas dos EUA sobre o Brasil | Alexandre de Moraes -> `alexandre-de-moraes` |
| `ev-2025-08-28-voo-no-jato-de-vorcaro-com-ciro-nogueira` | Voo no jato de Vorcaro com Ciro Nogueira, Isnaldo Bulhões, Rodrigo Gambale e Fáb | Ciro Nogueira -> `ciro-nogueira` |
| `fam29` | CVM aplica multas a Daniel, Henrique e Felipe Vorcaro e ao Master no caso do fun | Banco Master -> `banco-master` |
| `ev-2023-10-05-banco-central-publica-regra-prudencial` | Banco Central publica regra prudencial sobre precatórios | Banco Central -> `bcb` |
| `ev-2025-01-presidencia-do-trf-1-nega-levantar-a` | Presidência do TRF-1 nega levantar a suspensão | TRF-1 -> `trf-1` |
| `ev-2026-09-28-segunda-cautelar-do-cnj-e-oficios-de` | Segunda cautelar do CNJ e ofícios de Gilmar a Fachin e ao STJ | CNJ -> `cnj` |

## 13. Dossiê e fóruns relacionais (`scripts/dossie_rel.py`)

`mercado.pares`, `previdencia.entes`, `dinheiro.{contratos,midia,doacoes}`, `maquina.indicios`, `limites.*` e `pares.foruns` deixaram de ir para `nota.texto`. Tabelas (cada uma guarda também o texto original, para exportar igual ao embutido):

| tabela | linhas | observação |
|---|---|---|
| dossie_par | 14 | 13 pares; 'Antônio Rueda e ACM Neto' vira 2 linhas (mesma `ordem`, `sub` 0 e 1); `liga` sim/apura/nao |
| dossie_par_evidencia | 14 | fontes de cada par (`rotulo` = veículo como no original) |
| previdencia_ente | 11 | 11 entes (inclui a linha agregada 'Outros oito'); soma R$ 1.867,45 mi |
| pagamento | 14 | contratos 8, mídia 3, doações 3 (`ano` extraído do texto das doações; valores em R$ mi, como no dossiê) |
| indicio_maquina | 5 | 5 indícios (`forca` 1-2) |
| limite | 13 | derrubado 6, aberto 4, agenda 3 (`data` ISO quando reconhecível, `data_texto` original) |
| forum | 50 | 10 países x (G20, BRICS, OCDE, CSNU, nuclear); CSNU com lista vira `anos` (JSON); nuclear: `status_texto` sim/nao e `primeiro_teste` |

Entidades criadas (tipo `fundo_previdencia`, origem `manual`, sem nó na teia, com alias): `rpps-cajamar`, `rpps-itaguai`, `rpps-araras`, `rpps-congonhas`.

Vínculo texto -> entidade (41 textos): 22 pelo mapa manual (`data/curadoria/dossie-entidades.json`), 17 por alias único exato, 2 sem entidade.

Textos sem entidade (ficam só como texto):

- mercado.pares: Dois ex-chefes da supervisão do BC
- previdencia.entes: Outros oito

Vinculados pelo mapa manual (as aproximações estão justificadas em `justificativas` no JSON; as mais discutíveis: Amazonprev, escritórios -> pessoa, Metrópoles):

- mercado.pares: Três dirigentes da Amazonprev -> `amazonprev`
- mercado.pares: Escritório de Viviane Barci de Moraes -> `viviane-barci-de-moraes`
- mercado.pares: Antônio Rueda e ACM Neto -> `antonio-rueda`, `acm-neto`
- previdencia.entes: Rioprevidência -> `rioprevidencia`
- previdencia.entes: Amprev -> `amprev`
- previdencia.entes: Maceió -> `iprev-maceio`
- previdencia.entes: São Roque -> `sao-roque-prev`
- previdencia.entes: Cajamar -> `rpps-cajamar`
- previdencia.entes: Itaguaí -> `rpps-itaguai`
- previdencia.entes: Amazonprev -> `amazonprev`
- previdencia.entes: Aparecida de Goiânia -> `aparecidaprev`
- previdencia.entes: Araras -> `rpps-araras`
- previdencia.entes: Congonhas -> `rpps-congonhas`
- dinheiro.contratos: Escritório de Viviane Barci de Moraes -> `viviane-barci-de-moraes`
- dinheiro.contratos: Escritório de Michel Temer -> `michel-temer`
- dinheiro.contratos: Escritórios de Antônio Rueda -> `antonio-rueda`
- dinheiro.contratos: Escritório da família Lewandowski -> `lewandowski-advocacia`
- dinheiro.midia: Metrópoles e empresas de Luiz Estevão -> `metropoles-marketing-e-propaganda`
- dinheiro.midia: Grupo Massa, de Ratinho -> `grupo-massa-ratinho`
- dinheiro.doacoes: Jair Bolsonaro (PL), 2022 -> `jair-bolsonaro`
- dinheiro.doacoes: Tarcísio de Freitas (Republicanos), 2022 -> `tarcisio-de-freitas`
- dinheiro.doacoes: Diretório do Novo, 2022 -> `partido-novo-diretorio-de-minas-gerais`

`exportar_json.py` gera `data/dossie.json` e `data/pares.json` a partir dessas tabelas e `validar.py` os compara com `data/raw/dossie.json` e `data/raw/pares.json`. Diferenças aceitas e documentadas:

- URLs em `src` saem normalizadas (sem barra final): 29 URLs; a comparação normaliza os dois lados.
- `pares.json`: 230 valores `null` explícitos dos indicadores e 18 do PISA não viram linha em `serie` (já era assim); e a linha de log "Cota: 39 buscas/fetches usados." de `pares.notas` continua descartada.
- `meta.paginas` do dossiê fica em `nota` (chave `meta.paginas`, JSON) e as `meta` do banco ganham `pares.gerado_em`, `pares.anos` e `pares.ordem_paises`.
- `dossie.json` inclui os 30 eventos BRB como no original (os fundidos saem de `evento_alias.original_json`); `teia.json` e `origens.json` refletem a curadoria (eventos fundidos saem da lista; `mapa_indices.json` ainda resolve os índices antigos).


## 14. Tema como dimensão N:N (`data/curadoria/temas.json`)

Tabelas: `tema(id, nome, descricao, cor, ordem, principal)`, `relacao_tema(relacao_id, tema_id, origem, regra)`, `evento_tema(evento_id, tema_id, origem, regra)`. **A entidade não tem tabela**: `v_entidade_tema` (view) deriva a pertinência: a entidade está no tema se tem relação ou evento nele; acrescentei como fontes estruturais `mandato`/`bancada`/`ranking_empresa` -> `brasil-ano-a-ano`, `forum` -> `pares` e o dossiê relacional (par, ente de previdência, pagamento) -> `caso-master` (sem isso empresas do ranking, partidos da bancada e países de `forum` ficariam sem tema, e as 'fusões' dependem disso). `entidade.categoria_id` continua sendo a categoria da teia. `migrar.py` aplica `temas.json` por último (`curadoria.aplicar_temas`), depois de fusões, ligações evento-entidade e relações de mandato; `exportar_json.py` emite `tema` em cada relação/evento de `teia.json` (e nos eventos de `origens.json`), `temas` em cada entidade de `entities.json` e o novo `temas.json`.

Regras (aplicadas na ordem; filtros combinados com E; `dentro_de` = só registros que já têm aquele tema; texto = palavra inteira, sem acento/caixa, `*` = prefixo):

| regra | tema | alvo | filtros | relações | eventos |
|---|---|---|---|---|---|
| master-relacoes | caso-master | relacao | origem=['teia', 'origens'] | 367 | 0 |
| master-eventos | caso-master | evento | canal=['teia', 'banco', 'familia', 'ida', 'volta', 'precatorios', 'brb'] | 0 | 215 |
| brasil-eventos | brasil-ano-a-ano | evento | canal=['brasil'] | 0 | 282 |
| brasil-relacoes | brasil-ano-a-ano | relacao | origem=['linha_do_tempo'] | 472 | 0 |
| pares-eventos | pares | evento | canal=['pares'] | 0 | 0 |
| violencia-eventos | violencia | evento | canal=['violencia'] | 0 | 10 |
| brb-canal | brb | evento | canal=['brb'] | 0 | 18 |
| brb-entidade | brb | ambos | dentro_de=['caso-master']; entidade=['brb'] | 10 | 15 |
| brb-texto | brb | ambos | dentro_de=['caso-master']; texto=['BRB', 'Banco de Brasília'] | 19 | 1 |
| precatorios-canal | precatorios | evento | canal=['precatorios'] | 0 | 35 |
| precatorios-texto | precatorios | ambos | dentro_de=['caso-master']; texto=['precatorio*'] | 12 | 2 |
| inss-entidade | inss | ambos | entidade=['inss', 'cpmi-do-inss'] | 9 | 14 |
| inss-texto | inss | ambos | texto=['INSS', 'Sem Desconto', 'consignado*'] | 12 | 4 |
| pcc-entidade | pcc | ambos | entidade=['pcc', 'operacao-carbono-oculto', 'operacao-quasar'] | 7 | 8 |
| pcc-texto | pcc | ambos | dentro_de=['caso-master']; texto=['PCC', 'Carbono Oculto', 'Quasar', 'Tank', 'Usina Itajobi'] | 7 | 1 |
| lagoinha-entidade | lagoinha | ambos | entidade=['igreja-batista-da-lagoinha', 'lagoinha-belvedere'] | 9 | 26 |
| lagoinha-texto | lagoinha | ambos | dentro_de=['caso-master']; texto=['Lagoinha'] | 8 | 6 |

Exceções (`excecoes` em `temas.json`; falso positivo de texto removido à mão, com motivo):

| alvo | ref | incluir | excluir | motivo |
|---|---|---|---|---|
| evento | `fam10` | - | inss | Credcesta/Bahia é consignado estadual, não INSS |
| evento | `fam16` | - | inss | Credcesta/Bahia é consignado estadual, não INSS |
| evento | `fam21` | - | inss | Credcesta/Bahia é consignado estadual, não INSS |
| evento | `max5` | - | inss | 'consignado' só descreve a carreira anterior do empresário |
| relacao | `E[65].r[0]` | - | inss | Credcesta/Bahia é consignado estadual, não INSS |
| relacao | `E[318].r[0]` | - | inss | INSS aparece só como a CPMI de onde vêm os documentos (palestra de Tony Blair) |
| relacao | `E[212].r[0]` | - | inss | INSS aparece só como a CPMI de onde vem a nota do escritório (honorários de precatório) |
| relacao | `E[130].r[0]` | - | inss | INSS aparece só como a CPMI que recebeu o IR de Vorcaro (ganho com cotas do Hans II) |

Contagens por tema (entidades vêm da view; um registro pode estar em vários temas):

| tema | relações | eventos | entidades |
|---|---|---|---|
| `caso-master` (Caso Master) | 367 | 215 | 212 |
| `brasil-ano-a-ano` (Brasil ano a ano) | 472 | 282 | 227 |
| `pares` (Comparação de países) | 0 | 0 | 10 |
| `violencia` (Violência) | 0 | 10 | 1 |
| `inss` (INSS) | 17 | 14 | 26 |
| `pcc` (PCC e crime organizado) | 14 | 9 | 25 |
| `brb` (BRB) | 29 | 34 | 42 |
| `precatorios` (Precatórios) | 12 | 37 | 26 |
| `lagoinha` (Lagoinha) | 17 | 32 | 27 |
| `crime-organizado` (Crime organizado) | 0 | 0 | 0 |
| `cultura-e-entretenimento` (Cultura e entretenimento) | 0 | 0 | 0 |
| `financiamento-politico` (Financiamento político) | 0 | 0 | 0 |
| `a-classificar` (A classificar) | 0 | 0 | 0 |

Em mais de um tema: 84 relações, 118 eventos, 117 entidades. Registros no tema-caixa `a-classificar`: 0 relações, 0 eventos (o MCP usa esse tema quando não consegue inferir; `validar.py` avisa se houver algum).

Limites conhecidos: (a) os temas por texto (`inss`, `pcc`, `brb`, `precatorios`, `lagoinha`) marcam **citação**, não centralidade: uma relação que só menciona a CPMI do INSS como origem de um documento entra em `inss` (retirei os casos mais óbvios nas exceções); (b) `usinas` ficou de fora do `pcc-texto` (a maior parte das ocorrências é o setor sucroalcooleiro dos precatórios, não o PCC); só 'Usina Itajobi'; (c) `pares` não tem relação nem evento (só 10 países via `forum`), e `violencia` só 10 eventos: séries (`indicador`/`serie`) **não** têm tema ainda; (d) eventos novos não entram por MCP (não há ferramenta), só por migração.


## 15. Fonte genérica (`fonte` no lugar de `video`)

`video` virou `fonte(id, tipo, plataforma?, url?, titulo, canal, canal_entidade_id, publicado_em, duracao_s, texto, hash_texto, arquivo_texto, resumo, evidencia_id, ...)` com `tipo IN ('video','reportagem','documento','pdf','depoimento','decisao','transcricao','outro')`. `texto` substitui `transcricao` (conteúdo extraído; para vídeo é a transcrição) e `hash_texto` é o sha256 do texto. `evidencia_id` é obrigatório quando há `url` (CHECK) e a evidência tem a mesma URL normalizada; sem URL (depoimento oral, documento físico) fica NULL. `trecho.video_id` virou `trecho.fonte_id`; `inicio_s`/`fim_s` passaram a ser opcionais (trigger exige para fonte tipo video) e entrou `localizacao` (página/parágrafo). `corte` continua com a coluna `video_id`, agora referenciando `fonte(id)`; triggers `trg_corte_so_video_*` recusam corte em fonte que não seja `video` (e a troca de tipo de uma fonte com cortes). A view `video` reproduz as colunas antigas (somente leitura; `transcricao` = `texto`). `busca_fts` ganhou linhas `fonte` (título, canal, resumo, texto).

Dados migrados: a tabela `video` estava vazia (0 linhas), então não houve conversão de registros: 0 fontes agora. Nota: `migrar.py` recria o banco do zero a partir de `data/raw/` + `data/curadoria/`; o que o MCP gravou (vídeos, relações `classificador`) só sobrevive no `dump.sql` versionado, não numa nova migração.


## 16. Teia <-> timeline: mandato e bancada -> relações institucionais (`data/curadoria/mandato-relacoes.json`)

`curadoria.gerar_relacoes_mandato` cria **472 relações novas** (`tipo='institucional'`, `natureza='documentada'`, `origem='linha_do_tempo'`, `status='publicada'`, tema `brasil-ano-a-ano`), depois de toda a carga bruta (ids novos, os antigos não mudam):

- **324 de mandato** (`subtipo='mandato:<cargo>'`, pessoa -> órgão, uma por linha de `mandato`, `origem_ref='mandato:<id>'`, período = o do mandato): deputado 169, presidente 6, presidente_camara 16, presidente_senado 14, senador 114, vice_presidente 5.
- **148 de filiação** (`subtipo='filiacao'`, pessoa -> partido, rótulo 'Filiado ao <sigla>'): uma por sequência contínua de mandatos do mesmo partido (anos consecutivos se fundem); o período é **inferido dos mandatos** (`periodo_aprox=1`, `periodo_texto='inferido dos mandatos'`), não a data de filiação.
- Órgãos: `camara-dos-deputados`, `senado-federal` (já existiam, origem timeline) e **`presidencia-da-republica`** (nova, `orgao_publico`; presidente e vice-presidente, em que `mandato.orgao_id` é NULL).
- `mandato.evidencia_id`: 302 de 324 linhas têm evidência oficial: 270 por legislatura e 4 por eleição (`tipo='dado_oficial'`, Dados Abertos da Câmara/Senado; a de eleição prova o mandato da legislatura seguinte, não o exercício no ano), 28 por página oficial da presidência da Casa (`tipo='documento_oficial'`, `presidente_camara`/`presidente_senado`). Fonte: `data/curadoria/mandato-oficial.json`, gerado de `data/raw/oficial/`; as relações de mandato e de filiação herdam essa evidência via `relacao_evidencia`. Complementos de partido/UF: 1. Divergentes: 2; sem fonte oficial: 20 (presidente e vice-presidente: não há página pública). As listas estão em `data/relatorio-mandatos-oficial.md`; o banco não foi alterado por elas.
- Escritos à mão em `data/curadoria/`: `mandato-correcoes.json` (6 correção de partido/UF em `mandato`, aplicada antes do confronto com as fontes oficiais; Miro Teixeira 2004, PT -> PPS, pelo histórico da Câmara) e `entidade-aliases.json` (3 aliases de grafia: Enéas, Luís Eduardo, Luiz Carlos Santos).
- **Parlamentares em destaque** (`deputado`/`senador`, `mandato` de um ano = ano do destaque na timeline): a relação tem `periodo_aprox=1` e a descrição avisa que o período é o ano do destaque, não o mandato inteiro.
- Mandatos sem filiação (partido sem entidade): hamilton-mourao (PRTB), heloisa-helena (PSOL). Não criei entidade de partido (PRTB, PSOL); decisão pendente.
- Mandatos sem órgão resolvido: 0.

Entidades da teia que aparecem na timeline (as 10 fusões da seção 5 mais as ligadas por eventos `brasil`): 20, todas em `brasil-ano-a-ano` **e** `caso-master` pela view: `alexandre-de-moraes`, `bcb`, `btg-pactual`, `davi-alcolumbre`, `edson-fachin`, `eduardo-bolsonaro`, `estados-e-municipios`, `flavio-bolsonaro`, `flavio-dino`, `gilmar-mendes`, `hugo-motta`, `ibaneis-rocha`, `jair-bolsonaro`, `jaques-wagner`, `luiz-estevao`, `luiz-inacio-lula-da-silva`, `michel-temer`, `nikolas-ferreira`, `pf`, `stf`.

## 17. Estimativas em R$ por entidade (`data/curadoria/entidade-valores.json`)

`curadoria.aplicar_entidade_valores` grava **60 valores em 45 entidades** na tabela aditiva `entidade_valor` (45 principais, 34 com fonte fraca), depois dos metadados de evidência. Cada valor tem uma `natureza` (o que o número mede); números de naturezas diferentes não se somam. A URL de cada valor é uma `evidencia` (12 novas, 39 reaproveitadas; título preenchido em 25 e data em 25 que estavam NULL). No arquivo, só como registro: 1 valor descartado e 1 entidade sem estimativa encontrada.

| natureza | n |
|---|---|
| bloqueado | 5 |
| desviado | 2 |
| investigado | 8 |
| movimentado | 15 |
| outro | 19 |
| passivo | 4 |
| prejuizo | 5 |
| sonegado | 2 |

| entidade | principal | natureza | valor (R$) | quem estima | qualidade |
|---|---|---|---|---|---|
| `agro-industrial-tabu` | sim | outro | 5.000.000.000 | Voto do ministro André Mendonça (STF, STP 976) | boa |
| `agu` | sim | outro | 255.300.000.000 | AGU/governo, via Novacana | fraca |
| `amazonprev` | sim | investigado | 390.000.000 | Polícia Federal, segundo a Folha de Pernambuco | fraca |
| `amprev` | sim | investigado | 400.000.000 | Polícia Federal, segundo a Folha de Pernambuco | boa |
| `aparecidaprev` | sim | investigado | 40.000.000 | Times Brasil (valor); Ministério Público de Goiás (apuração, segundo a relação da teia) | fraca |
| `astralo-95` | sim | movimentado | 294.000.000 | Liquidante do Master, via Metrópoles | fraca |
| `banco-master` | sim | prejuizo | 40.600.000.000 | FGC, segundo Poder360 | boa |
| `banco-master` |  | passivo | 83.200.000.000 | Banco Central (IFData), via Agência Estado | boa |
| `banco-pleno` | sim | passivo | 4.900.000.000 | FGC, segundo a Revista Oeste | boa |
| `brb` | sim | investigado | 12.760.000.000 | Investigações da PF e do MPF; BRB (comunicado), via Jornal de Brasília | boa |
| `brb` |  | outro | 21.900.000.000 | Presidente do BRB, via Jornal de Brasília | fraca |
| `btg-pactual` | sim | movimentado | 6.700.000.000 | Bloomberg Línea | boa |
| `cnj` | sim | outro | 4.700.000.000 | CNJ, via Times Brasil | fraca |
| `cpmi-do-inss` | sim | desviado | 3.300.000.000 | Relatório da maioria da CPMI do INSS | fraca |
| `cvm` | sim | outro | 201.500.000 | CVM (colegiado), via Poder360 | fraca |
| `daniel-vorcaro` | sim | bloqueado | 5.700.000.000 | Ministro Dias Toffoli (STF), segundo o portal oficial do STF | boa |
| `easynvest` | sim | movimentado | 2.900.000.000 | Bloomberg Línea | fraca |
| `efb-regimes-especiais-de-empresas` | sim | outro | 4.800.000.000 | Liquidante do Master, via Metrópoles | fraca |
| `entre-investimentos-e-participacoes` | sim | movimentado | 1.440.000.000 | Liquidante do Master, via Times Brasil | fraca |
| `entre-investimentos-e-participacoes` |  | outro | 1.280.000.000 | Liquidante do Master, via Times Brasil | fraca |
| `fgc` | sim | prejuizo | 40.600.000.000 | FGC, segundo o Poder360 | boa |
| `fgc` |  | prejuizo | 37.200.000.000 | FGC, segundo a CNN Brasil | boa |
| `fgc` |  | prejuizo | 58.000.000.000 | Revista Oeste (sem atribuição nominal no trecho) | fraca |
| `gabino-kruschewsky-advogados-associados` | sim | movimentado | 54.000.000 | Revista Oeste | fraca |
| `gold-style-fidc` | sim | outro | 1.840.000.000 | Comunicados do fundo, via Jornal de Brasília (Folhapress) | fraca |
| `gold-style-fidc` |  | movimentado | 311.700.000 | Comunicados do fundo, via Jornal de Brasília (Folhapress) | fraca |
| `governo-do-distrito-federal` | sim | outro | 1.170.000.000 | Jornal de Brasília | fraca |
| `grupo-fictor` | sim | outro | 3.000.000.000 | Comunicado da Fictor, via InfoMoney | fraca |
| `hans-95` | sim | outro | 27.000.000.000 | CVM, segundo o Letsmoney | fraca |
| `hans-95` |  | movimentado | 1.000.000.000 | CVM, segundo o Letsmoney | fraca |
| `inss` | sim | prejuizo | 6.300.000.000 | Polícia Federal, segundo a Agência Câmara | boa |
| `inss` |  | outro | 2.000.000.000 | INSS, via O Povo | fraca |
| `instituto-abradecont` | sim | outro | 100.000.000 | Petição do Instituto Abradecont, segundo o Times Brasil | fraca |
| `iprev-maceio` | sim | outro | 97.000.000 | Poder360, com base em dados dos regimes | boa |
| `lagoinha-belvedere` | sim | movimentado | 19.200.000 | Coaf, via Itatiaia | fraca |
| `monteiro-rusu-cameirao-e-bercht-advogados` | sim | movimentado | 79.100.000 | Revista Oeste | fraca |
| `operacao-carbono-oculto` | sim | movimentado | 52.000.000.000 | Receita Federal (nota de 28/8/2025, transcrita no Relatório ANP 1/2026) | boa |
| `operacao-carbono-oculto` |  | sonegado | 8.670.000.000 | Receita Federal (nota de 28/8/2025, transcrita no Relatório ANP 1/2026) | boa |
| `operacao-compliance-zero` | sim | investigado | 12.000.000.000 | Polícia Federal (Andrei Rodrigues, em depoimento à CPI do Crime Organizado) | boa |
| `operacao-compliance-zero` |  | outro | 12.200.000.000 | PF e MPF (segundo reportagem) | boa |
| `operacao-compliance-zero` |  | bloqueado | 5.700.000.000 | Ministro Dias Toffoli (STF), segundo o portal oficial do STF | boa |
| `operacao-compliance-zero` |  | bloqueado | 22.000.000.000 | Times Brasil, resumo das fases da operação | fraca |
| `operacao-credito-oculto` | sim | outro | 153.000.000 | Investigação (Receita/Gaeco), segundo JB | boa |
| `operacao-quasar` | sim | bloqueado | 1.200.000.000 | Justiça Federal / PF | boa |
| `operacao-sem-desconto` | sim | desviado | 6.300.000.000 | Polícia Federal, segundo a Agência Câmara | boa |
| `pcc` | sim | movimentado | 52.000.000.000 | Receita Federal (nota de 28/8/2025, transcrita no Relatório ANP 1/2026) | boa |
| `pcc` |  | sonegado | 8.670.000.000 | Receita Federal (nota de 28/8/2025, transcrita no Relatório ANP 1/2026) | boa |
| `reag-trust-dtvm` | sim | investigado | 11.500.000.000 | Banco Central (relatório ao TCU), via Jornal de Brasília/Folhapress | fraca |
| `rioprevidencia` | sim | investigado | 970.000.000 | Polícia Federal (Operação Barco de Papel), segundo a Folha de Pernambuco | boa |
| `rioprevidencia` |  | investigado | 2.010.000.000 | Polícia Federal, segundo a Folha de Pernambuco | fraca |
| `sao-roque-prev` | sim | outro | 93.150.000 | Times Brasil, com base nos regimes | fraca |
| `seis-usinas-cedidas-a-entre` | sim | movimentado | 1.440.000.000 | Liquidante do Master, via Times Brasil | fraca |
| `stf` | sim | bloqueado | 5.700.000.000 | Ministro Dias Toffoli (STF), portal oficial do STF | boa |
| `usina-cambahyba` | sim | outro | 2.500.000.000 | Justiça Federal (10ª Vara/RJ), via Times Brasil | fraca |
| `usina-capricho` | sim | outro | 4.700.000.000 | CNJ, via Times Brasil | fraca |
| `usina-santa-tereza` | sim | movimentado | 180.000.000 | Estadão, via Novacana | fraca |
| `warde-advogados` | sim | movimentado | 76.600.000 | Revista Oeste | fraca |
| `will-financeira` | sim | passivo | 6.300.000.000 | FGC, segundo a CNN Brasil | boa |
| `will-financeira` |  | passivo | 6.060.000.000 | FGC, segundo o Letsmoney | fraca |
| `xp-investimentos` | sim | movimentado | 26.000.000.000 | Bloomberg Línea | boa |

Na teia (`teia.json`), cada nó com valores ganha `val` (a lista, principal primeiro) e `val_lig` (soma de `relacao.valor_brl` das ligações `E[].r` do nó e quantas têm valor): a soma das ligações é outra coisa que a estimativa do escândalo e não se soma a ela.

## 18. Revisão do critério 'fraca' (`data/curadoria/evidencia-qualidade-revisao.json`)

Regra (do `_doc` do arquivo): `fraca` descreve a fonte, não a lacuna da nota. `curadoria.aplicar_evidencia_qualidade` roda depois de tudo que grava `qualidade` (evidências adicionais, substituições, metadados, valores, correções) e troca `fraca` -> `boa` na ligação de cada entrada de `revisoes`, achada por evento (id ou alias de fusão) + URL normalizada ou por relação (`origem` + `origem_ref`) + URL. A `nota` do pesquisador fica intacta; o `motivo` não vai para o banco (não há coluna para ele) e fica só aqui. Aborta sem aplicar nada se a ligação não existe ou a qualidade atual não é `fraca`, com duas exceções registradas abaixo: entrada repetida idêntica (conta uma vez) e fonte `fraca` já substituída em `evidencias-adicionais.json` (`substituida_por`), que por desenho não está ligada ao alvo.

| | evento_evidencia | relacao_evidencia | total |
|---|---:|---:|---:|
| ligações `fraca` antes | 89 | 2 | 91 |
| revistas para `boa` | 87 | 2 | 89 |
| ligações `fraca` depois | 2 | 0 | 2 |

Entradas em `revisoes`: 108 = 89 aplicadas + 2 repetidas (idênticas) + 17 sobre fontes já substituídas (nada a mudar no banco). `mantidas_fracas` do arquivo = 66 (= 174 entradas `fraca` de `evidencias-adicionais.json` − 108 entradas de `revisoes`, contando as 83 substituídas, que não estão ligadas, e as repetidas). No banco ficam 2 = 91 fracas ligadas (= 174 − 83 substituídas) − 89 revistas (= `mantidas_fracas` − 83 substituídas + 17 revisões sobre substituídas + 2 repetidas).

| motivo | aplicadas |
|---|---:|
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto | 15 |
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: 32,3% (Agência Brasil) | 1 |
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: Pazuello interino em 15/5/2020 | 1 |
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: cerca de 57,7 milhões de votos | 1 |
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: médias do Brent 2005/2004 pela série EIA/FRED anexada (54,57 e 38,26) | 1 |
| a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: publicação no DOU em 23/12/2003 | 1 |
| fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte | 21 |
| veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota | 48 |

Sobre fontes já substituídas (a `fraca` não está ligada; a substituta `boa` está):

| alvo | fraca | substituída por |
|---|---|---|
| `ev-2000-argentina-em-recessao` | https://api.worldbank.org/v2/country/ARG/indicator/NY.GDP.MKTP.KD.ZG?date=1998:2001&format=json | https://wits.worldbank.org/CountryProfile/es/Country/BRA/Year/2000/Summarytext |
| `ev-2000-lei-de-responsabilidade-fiscal` | https://www25.senado.leg.br/web/atividade/materias/-/materia/43190 | https://www25.senado.leg.br/web/atividade/materias/-/materia/43190/pdf |
| `ev-2005-china-encerra-a-paridade-fixa-com-o` | https://www.frbsf.org/research-and-insights/publications/economic-letter/2005/09/a-look-at-china-new-exchange-rate-regime | https://www.nbcnews.com/id/wbna8655469 |
| `ev-2005-fed-sobe-juros-em-todas-as-reunioes-do` | https://www.federalreserve.gov/boarddocs/press/monetary/2005/20051213/default.htm | https://www.federalreserve.gov/monetarypolicy/openmarket.htm |
| `ev-2010-china-a-frente-do-japao-e-principal` | https://www.rferl.org/a/china_economy/2308720.html | https://www.aljazeera.com/amp/economy/2011/2/14/chinese-economy-overtakes-japan |
| `ev-2015-fed-inicia-o-ciclo-de-alta-de-juros` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20151216a.htm | https://www.federalreserve.gov/monetarypolicy/openmarket.htm |
| `ev-2015-turbulencia-na-china-bolsa-e-yuan` | https://investing.com/news/economy-news/a-surprise-devaluation-for-the-yuan-355385 | https://www.everycrsreport.com/files/20150817_IN10342_ce6eb700a4e769c5c91c750981a3c7cd98358793.html |
| `ev-2020-novo-fundeb` | https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc108.htm | https://www12.senado.leg.br/noticias/materias/2020/08/26/senadores-comemoram-promulgacao-da-emenda-que-torna-o-fundeb-permanente |
| `ev-2020-saida-de-sergio-moro-do-governo` | https://www.agazeta.com.br/es/politica/interferencia-na-pf-fraude-e-demissao-veja-dez-frases-de-moro-0420 | https://istoedinheiro.com.br/moro-anuncia-demissao-e-acusa-bolsonaro-de-interferir-na-pf |
| `ev-2025-eua-impoem-tarifa-de-50-a-produtos` | https://www.whitehouse.gov/presidential-actions/2025/11/modifying-the-scope-of-tariffs-on-the-government-of-brazil | https://www.govinfo.gov/content/pkg/FR-2025-08-05/pdf/2025-14896.pdf |
| `ev-2025-eua-impoem-tarifa-de-50-a-produtos` | https://agenciabrasil.ebc.com.br/economia/noticia/2025-08/tarifaco-sobre-parte-das-exportacoes-brasileiras-entra-em-vigor-hoje | https://www.govinfo.gov/content/pkg/FR-2025-08-05/pdf/2025-14896.pdf |
| `ev-2025-eua-isentam-parte-dos-produtos-agricolas` | https://www.whitehouse.gov/presidential-actions/2025/11/modifying-the-scope-of-the-reciprocal-tariff-with-respect-to-certain-agricultural-products | https://www.whitehouse.gov/presidential-actions/2025/11/modifying-the-scope-of-tariffs-on-the-government-of-brazil |
| `ev-2025-fed-corta-juros-tres-vezes` | https://federalreserve.gov/newsevents/pressreleases/monetary20251210a.htm | https://www.federalreserve.gov/newsevents/pressreleases/monetary20250917a.htm |
| `ev-2025-isencao-do-ir-ate-r-5-mil` | https://www.opovo.com.br/noticias/economia/2025/11/26/lula-sanciona-isencao-do-ir-para-quem-ganha-ate-rs-5-mil.html | https://www.camara.leg.br/noticias/1206672-camara-aprova-projeto-que-isenta-do-imposto-de-renda-quem-ganha-ate-r-5-mil-por-mes/ |
| `ev-2025-stf-torna-bolsonaro-reu-e-o-condena` | https://www.moneytimes.com.br/stf-condena-bolsonaro-a-27-anos-e-3-meses-de-prisao-em-regime-inicial-fechado-por-tentativa-de-golpe-de-estado-e-outros-crimes-kda | https://agenciabrasil.ebc.com.br/justica/noticia/2025-09/stf-condena-bolsonaro-27-anos-e-tres-meses-de-prisao |
| `linha_do_tempo filiacao:jair-bolsonaro:psl:2019` | https://www.camara.leg.br/noticias/546904-jair-bolsonaro-e-eleito-presidente-do-brasil | https://agenciabrasil.ebc.com.br/politica/noticia/2019-11/bolsonaro-anuncia-saida-do-psl-e-criacao-da-alianca-pelo-brasil |
| `linha_do_tempo filiacao:jose-alencar:pl:2003` | https://www12.senado.leg.br/noticias/materias/2002/12/30/congresso-nacional-dara-posse-ao-37-presidente-da-republica-do-brasil | https://www2.senado.leg.br/jspui/bitstream/id/460123/1/noticia.htm |

Repetidas (idênticas a uma entrada anterior; contadas uma vez):

- `linha_do_tempo filiacao:jair-bolsonaro:psl:2019`: https://www.camara.leg.br/noticias/546904-jair-bolsonaro-e-eleito-presidente-do-brasil
- `linha_do_tempo filiacao:jose-alencar:pl:2003`: https://www12.senado.leg.br/noticias/materias/2002/12/30/congresso-nacional-dara-posse-ao-37-presidente-da-republica-do-brasil

| alvo | url | motivo |
|---|---|---|
| `ev-2000-cassacao-do-senador-luiz-estevao` | https://www.congressoemfoco.com.br/noticia/60130/por-56-votos-19-senado-cassa-demostenes-torres | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2000-eleicoes-municipais` | https://www.dgabc.com.br/Noticia/269296/marta-vence-maluf-e-e-eleita-prefeita-de-s-paulo | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2005-katrina-e-petroleo-mais-caro` | https://fred.stlouisfed.org/data/ACOILBRENTEU | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: médias do Brent 2005/2004 pela série EIA/FRED anexada (54,57 e 38,26) |
| `ev-2015-turbulencia-na-china-bolsa-e-yuan` | https://www.business-standard.com/amp/article/news-ians/chinese-stocks-sink-below-3-000-points-115082500699_1.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2020-china-cresce-e-compra-um-terco-das` | https://agenciabrasil.ebc.com.br/economia/noticia/2021-01/china-contribuiu-com-mais-da-metade-do-superavit-comercial-do-brasil | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: 32,3% (Agência Brasil) |
| `ev-2020-guerra-de-precos-do-petroleo` | https://www.cnbc.com/2020/06/16/how-negative-oil-prices-revealed-the-dangers-of-futures-trading.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2020-trocas-no-ministerio-da-saude` | https://www.poder360.com.br/governo/ministro-da-saude-nelson-teich-pede-demissao-do-governo-bolsonaro | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: Pazuello interino em 15/5/2020 |
| `teia N[139].fam_de` | https://www.folhavitoria.com.br/politica/eduardo-tratou-sobre-filme-com-vorcaro-e-pediu-para-enviar-maximo-de-recursos-aos-eua | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `teia N[142].fam_de` | https://www.diariodepernambuco.com.br/politica/2026/09/11724589-contrato-de-vorcaro-previa-ate-rs-427-mi-em-honorarios-a-escritorio-de-esposa-de-desembargador-da-turma-do-kn.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-1996-acordo-de-tecnologia-da-informacao-na` | https://www.wto.org/english/tratop_e/inftec_e/itaintro_e.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1996-chile-assina-acordo-de-associacao-ao` | https://www.gov.br/agricultura/pt-br/assuntos/relacoes-internacionais/negociacoes-comerciais/brasil-mercosul-1/documentos-mercosul/chile.pdf | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1996-criacao-da-cpmf` | https://www.planalto.gov.br/ccivil_03/leis/l9311.htm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-1996-greenspan-fala-em-exuberancia-irracional` | https://www.federalreserve.gov/boarddocs/speeches/1996/19961205.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1996-lei-kandir` | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1997-denuncia-de-compra-de-votos-pela` | https://www.poder360.com.br/brasil/entenda-como-foi-a-compra-de-votos-a-favor-da-emenda-da-reeleicao-em-1997/ | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-1997-emenda-da-reeleicao-ec-16` | https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc16.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1997-lei-geral-de-telecomunicacoes` | https://www.planalto.gov.br/ccivil_03/leis/l9472.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1997-pacote-de-resgate-de-us-17-bilhoes-a` | https://www.mof.go.jp/english/about_mof/councils/customs_foreign_exchange/report/e1a703n21a.htm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-1998-fmi-e-paises-ricos-montam-pacote-para-o` | https://www.imf.org/external/np/tr/1998/tr981113.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-1998-privatizacao-do-sistema-telebras` | https://teletime.com.br/29/07/1998/telebras-e-vendida-com-agio-de-6374/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-1999-fim-da-banda-cambial-e-cambio-flutuante` | https://www.bcb.gov.br/rex/MerCambio/Port/cambio991/1999-1Flutuante.asp?frame=1 | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2001-china-entra-na-omc` | https://www.wto.org/english/thewto_e/acc_e/a1_chine_e.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2001-violacao-do-painel-do-senado-e-renuncia` | https://www12.senado.leg.br/noticias/materias/2001/05/16/saturnino-acm-e-arruda-cometeram-irregularidade-grave | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2002-fmi-aprova-o-maior-emprestimo-da` | https://www.imf.org/external/np/sec/pr/2002/pr0240.htm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2003-estatuto-do-desarmamento` | https://www.planalto.gov.br/ccivil_03/leis/2003/l10.826.htm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: publicação no DOU em 23/12/2003 |
| `ev-2003-pt-expulsa-heloisa-helena-e-tres` | https://exame.com/economia/pt-expulsa-radicais-m0060399/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2004-caso-waldomiro-diniz` | https://sbtnews.sbt.com.br/noticia/politica/escandalo-waldomiro-diniz-ex-membro-de-confianca-do-pt-completa-20-anos | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2004-eleicoes-municipais-de-2004` | https://memoria.ebc.com.br/agenciabrasil//noticia/2004-11-01/pmdb-maintains-hegemony-small-municipalities-psdb-and-pt-win-big-cities | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2004-lei-das-parcerias-publico-privadas` | https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11079.htm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2004-petroleo-passa-de-us-50-o-barril` | https://www.wosu.org/npr-news/2004-09-28/oil-prices-hit-new-record-of-50-a-barrel | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2006-bolivia-nacionaliza-os-hidrocarbonetos` | https://www.ipsnews.net/portuguese/2006/05/america-latina/bolivia-como-foi-nacionalizado-o-enorme-negocio-do-petroleo/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2006-fed-sobe-juros-para-5-25` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20060629a.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2006-negociacoes-da-rodada-doha-sao-suspensas` | https://www.jb.com.br/internacional/noticias/2007/03/04/amp/encontros-em-londres-sobre-sobre-a-omc-terminam-sem-avancos.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2006-operacao-sanguessuga-e-cpmi-das` | https://www.congressoemfoco.com.br/noticia/71007/entenda-o-caso-o-que-foi-a-operacao-sanguessuga | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2006-reeleicao-de-lula` | https://www.congressoemfoco.com.br/noticia/87895/tse-lula-foi-reeleito-com-60-83-dos-votos-validos | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2006-sancionada-a-lei-maria-da-penha` | https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2006-venezuela-assina-protocolo-de-adesao-ao` | https://www2.camara.leg.br/legin/fed/decleg/2009/decretolegislativo-934-16-dezembro-2009-598334-exposicaodemotivos-153923-pl.html | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2007-bnp-paribas-congela-fundos-e-bce-injeta` | https://observador.pt/especiais/9-de-agosto-de-2007-o-dia-em-que-o-mundo-mudou/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2007-fed-comeca-a-cortar-juros` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20070918a.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2007-petrobras-anuncia-a-descoberta-de-tupi` | https://www.infomoney.com.br/mercados/o-anuncio-do-potencial-do-pre-sal-que-mudou-a-historia-da-petrobras-e-levou-as-acoes-as-alturas/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2008-brasil-obtem-grau-de-investimento` | https://www.infomoney.com.br/?p=1522698 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2008-eleicoes-municipais-de-2008` | https://www.congressoemfoco.com.br/noticia/102082/pmdb-tem-maior-numero-de-prefeitos | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2008-marina-silva-deixa-o-ministerio-do-meio` | https://www.congressoemfoco.com.br/noticia/84438/bancada-comemora-demissao-de-marina | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2008-operacao-satiagraha-prende-daniel-dantas` | https://www.gazetadopovo.com.br/vida-publica/confira-os-principais-fatos-da-operacao-satiagraha-bjsiht1vlclo5g7w1ubvfhiku/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2008-petroleo-bate-recorde-e-despenca` | https://www.telemetro.com/economia/2008/07/11/barril-crudo-supera-primera-dolares/2112756.html/amp | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2008-quebra-do-lehman-brothers` | https://www.infomoney.com.br/?p=386374 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2009-crise-dos-atos-secretos-no-senado` | https://www.congressoemfoco.com.br/noticia/2681/conselho-de-etica-mantem-arquivadas-todas-as-acusacoes-contra-sarney | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2009-grecia-revela-deficit-de-12-7-do-pib` | https://www.esm.europa.eu/publications/safeguarding-euro/runaway-train-greece-sounds-alarm | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2009-operacao-caixa-de-pandora-no-distrito` | https://www.congressoemfoco.com.br/noticia/72793/policia-federal-investiga-governo-arruda | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2009-operacao-caixa-de-pandora-no-distrito` | https://www.congressoemfoco.com.br/noticia/72313/todos-os-detalhes-da-prisao-de-arruda | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2011-palocci-deixa-a-casa-civil` | https://www.congressoemfoco.com.br/noticias/antonio-palocci-pede-demissao-do-governo | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2011-promulgada-a-lei-de-acesso-a-informacao` | https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2011-segundo-resgate-a-grecia-e-contagio-na` | https://www.publico.es/economia/eurozona-pone-al-rescate-grecia.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2012-argentina-reestatiza-a-petroleira-ypf` | https://www.diariodecuyo.com.ar/noticias/la-reestatizacion-de-ypf-es-ley-765379.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2012-stf-valida-a-ficha-limpa-eleicoes` | https://noticias.stf.jus.br/postsnoticias/135-anos-do-stf-decisoes-da-corte-consolidam-a-lei-da-ficha-limpa-como-marco-da-moralidade-eleitoral/ | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2014-morte-de-eduardo-campos` | https://www.jb.com.br/pais/noticias/2014/08/13/amp/eduardo-campos-morre-em-acidente-aereo-em-santos.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2014-reeleicao-de-dilma-rousseff` | https://www12.senado.leg.br/radio/1/noticia/2014/10/27/presidente-dilma-rousseff-e-reeleita-com-51-64-dos-votos | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2014-relatorio-final-da-comissao-nacional-da` | https://www12.senado.leg.br/radio/1/noticia/2014/12/10/renan-recebe-relatorio-final-da-comissao-nacional-da-verdade | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2014-sancionado-o-marco-civil-da-internet` | https://www12.senado.leg.br/noticias/materias/2014/04/23/sancionada-a-lei-do-marco-civil-da-internet | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2016-cunha-tem-o-mandato-cassado-pela-camara` | https://www.congressoemfoco.com.br/noticias/camara-cassa-mandato-de-eduardo-cunha-deputado-fica-inelegivel-por-oito-anos/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2016-opep-faz-seu-primeiro-corte-de-producao` | https://exame.com/economia/petroleiras-fora-da-opep-tambem-vao-cortar-producao | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2017-camara-barra-denuncias-contra-temer` | https://www.jornalopcao.com.br/ultimas-noticias/camara-rejeita-denuncia-contra-michel-temer-101355/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2017-camara-barra-denuncias-contra-temer` | https://www.congressoemfoco.com.br/noticias/janot-denuncia-temer-pela-segunda-vez-e-o-acusa-de-liderar-organizacao-criminosa-leia-a-integra | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2017-delacao-da-jbs-e-gravacao-envolvendo` | https://www.jb.com.br/pais/noticias/2017/05/17/amp/dono-da-jbs-grava-temer-dando-aval-para-compra-de-silencio-de-cunha.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2017-mercosul-suspende-a-venezuela-por-tempo` | https://www.poder360.com.br/internacional/por-ruptura-da-ordem-democratica-mercosul-suspende-venezuela-do-bloco/ | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2017-moro-condena-lula-no-caso-do-triplex` | https://www.poder360.com.br/eleicoes/lula-e-condenado-a-9-anos-e-6-meses-de-prisao-no-processo-do-triplex/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2017-reforma-trabalhista-e-aprovada-e` | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13467.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2018-bolsonaro-e-eleito-presidente` | https://istoe.com.br/tse-conclui-totalizacao-das-secoes-eleitorais-no-segundo-turno | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto — após correção: cerca de 57,7 milhões de votos |
| `ev-2018-crise-da-lira-turca-assusta-os` | https://www.gazetasp.com.br/cotidiano/42349-trump-autoriza-dobrar-tarifa-sobre-metais-da-turquia-e-ag/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2018-fed-leva-os-juros-a-2-25-2-50` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20181219a.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2018-greve-dos-caminhoneiros` | https://www.poder360.com.br/brasil/temer-recua-outra-vez-cede-a-caminhoneiros-e-congela-diesel-por-60-dias/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2018-intervencao-federal-na-seguranca-do-rio` | https://www.poder360.com.br/brasil/por-ampla-maioria-camara-aprova-decreto-de-intervencao-do-rio/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2018-lula-e-preso-em-curitiba` | https://oimparcial.com.br/brasil/2018/04/stf-rejeita-habeas-corpus-de-lula-por-6-votos-a-5/ | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2018-tse-barra-lula-e-pt-lanca-haddad` | https://www.agazeta.com.br/brasil/tse-usa-lei-da-ficha-limpa-para-barrar-lula-0918 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2018-tse-barra-lula-e-pt-lanca-haddad` | https://www.correio24horas.com.br/brasil/haddad-e-confirmado-como-candidato-do-pt-no-lugar-de-lula-0918 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2019-lula-e-solto-apos-580-dias-preso` | https://www.agazeta.com.br/brasil/lula-deixa-a-prisao-em-curitiba-apos-decisao-do-stf-1119 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2019-queimadas-na-amazonia-chegam-a-agenda-do` | https://www.aosfatos.org/noticias/desenhamos-fatos-sobre-as-queimadas-no-brasil/ | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2019-queimadas-na-amazonia-chegam-a-agenda-do` | https://www.arabnews.com/node/1545521 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2019-ue-e-mercosul-fecham-acordo-politico` | https://www.eeas.europa.eu/node/64856_be | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2021-condenacoes-de-lula-anuladas-moro` | https://agenciabrasil.ebc.com.br/justica/noticia/2021-03/stf-considera-que-moro-foi-parcial-nos-processos-de-lula | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2021-cop26-declaracao-de-glasgow-sobre` | https://www.cnbc.com/2021/11/02/cop26-china-brazil-among-nations-pledging-to-end-deforestation-by-2030.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2022-acordo-de-graos-do-mar-negro` | https://www.un.org/en/black-sea-grain-initiative | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2022-choque-de-commodities-brent-acima-de-us` | https://www.business-standard.com/article/international/brent-crude-goes-over-130-per-barrel-surpassing-top-2012-mark-122030700078_1.html | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2022-russia-invade-a-ucrania` | https://www.malaymail.com/news/world/2022/02/24/russia-invades-ukraine-dozens-killed/2043785 | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2023-brics-convida-seis-paises-a-aderir` | https://newarab.com/news/brics-admit-egypt-iran-saudi-arabia-uae-next-year | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2023-fed-leva-os-juros-a-5-25-5-50` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20230726a.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |
| `ev-2023-milei-e-eleito-e-o-peso-argentino-e` | https://www.noticel.com/mundo/20231129/asamblea-legislativa-argentina-consagra-el-triunfo-de-milei-con-el-55-65-de-los-votos | veículo de imprensa estabelecido (inclui regionais e estrangeiros) que confirma o núcleo do evento; lacunas ficam na nota |
| `ev-2023-milei-e-eleito-e-o-peso-argentino-e` | https://www.infomoney.com.br/?p=2323239 | a divergência apontada foi resolvida corrigindo o evento/relação (evento-correcoes/relacao-correcoes); a fonte agora sustenta o texto |
| `ev-2024-fed-corta-os-juros-em-1-ponto-e-chega-a` | https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm | fonte primária/oficial que sustenta o núcleo do evento; o que a página não traz fica registrado na nota, não desqualifica a fonte |

## 19. Rodada 3 de fontes (`data/curadoria/evidencias-rodada3.json`)

40 entradas para 33 eventos que a rodada 2 deixou `nao_classificada`, aplicadas por `curadoria.aplicar_evidencias_adicionais` junto com `evidencias-adicionais.json` (`curadoria.ler_evidencias_adicionais`), papel `sustenta`; as ligações wiki/outro que esses eventos já tinham ficam. A natureza vem de `eventos-natureza.json`, regerado (R5) depois da rodada. Decisão desta rodada: R5 passa a contar `comunicado` (nota de órgão público) como fonte oficial, como `documento_oficial`/`dado_oficial`/`decisao_judicial`; sem isso, 4 eventos sustentados só por press release do Fed e da ONU continuariam `nao_classificada` (nenhum outro evento muda). Correções de texto da rodada: 7 (`evento-correcoes.json`, `"rodada": 3`; detalhe em `relatorio-evidencias-adicionais.md`, seção "Rodada 3").

| natureza dos eventos cobertos | eventos |
|---|---:|
| documentada | 21 |
| reportada | 12 |

| natureza (todos os eventos) | eventos |
|---|---:|
| alegacao | 6 |
| documentada | 245 |
| investigacao | 36 |
| reportada | 220 |

Eventos `nao_classificada` depois da rodada: 0.

## 20. Rodada 4: substituição das fontes fracas (`data/curadoria/substituicoes-rodada4.json`)

56 fontes novas (`boa`, papel `sustenta`) para 46 alvos, cada uma com `substitui`; 47 fontes fracas distintas substituídas (todas registradas em `evidencias-adicionais.json`, que ganham `substituida_por`). Aplicadas por `curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, depois das rodadas 1-3), conferidas antes por `curadoria.conferir_substituicoes`. Uma fraca substituída deixa de ser ligada ao alvo; se a URL também é fonte bruta do bloco-ano do evento (`brasil-fontes.json`), a ligação volta a ser `contexto` sem avaliação (9 já eram `contexto`; 4 eram `sustenta` por slug e foram rebaixadas). 17 substitutas já eram fonte `boa` do alvo (rodadas 2-3; a ligação existente fica), 2 são a mesma URL relida (reavaliação) e 3 eram `contexto` do bloco-ano e subiram a `sustenta`. Ligações `fraca` no banco ao fim da rodada (antes da R6 e da rodada 5): 51 -> 4. Correções de texto: 6 em `evento-correcoes.json` (`"rodada": 4`) e a descrição de `N[197].fam_de` em `relacao-correcoes.json`. Detalhe em `relatorio-evidencias-adicionais.md`, seção "Rodada 4".

| natureza (todos os eventos) | eventos |
|---|---:|
| alegacao | 6 |
| documentada | 245 |
| investigacao | 36 |
| reportada | 220 |

## 21. R6: peso da Wikipédia (`data/curadoria/regras-fontes.json`)

Registro da decisão (`motivo` do arquivo): Dar menos peso à Wikipédia: fonte Wikipédia (evidencia.tipo='wiki' ou domínio *.wikipedia.org) nunca tem papel 'sustenta'; em evento_evidencia e relacao_evidencia é sempre 'contexto', não conta para a natureza (R5 só olha 'sustenta') nem no 'Fontes (n)' das páginas e aparece por último, apagada, como 'Wikipédia (contexto)'. Regra R6, global e permanente: decisão do dono do projeto, 18/10/2026.

`curadoria.aplicar_peso_wikipedia` roda depois de todas as funções de evidência (inclusive `aplicar_evidencia_qualidade`, que exige a `fraca` ainda gravada) e antes de gerar a natureza (`gerar_curadoria.py --so natureza` parte de um banco com R6 aplicada; R5 só olha `sustenta`). Rebaixa toda ligação de fonte wiki (`evidencia.tipo='wiki'` ou domínio `*.wikipedia.org`) com papel `sustenta` para `contexto`, mantendo rótulo, trecho e nota; `qualidade` passa a NULL (contexto não é avaliado). Aborta sem mudar nada se algum evento ou relação ficaria sem fonte `sustenta` (nenhum dependia só de wiki).

| | evento_evidencia | relacao_evidencia |
|---|---:|---:|
| wiki `sustenta` rebaixadas a `contexto` | 96 | 3 |
| alvos distintos | 77 | 3 |

Qualidade antes: 2 `fraca`, 0 `boa`, 97 não avaliadas (NULL). Wiki `sustenta` depois: 0.
Ligações `fraca` no banco: 2 -> 0 (as wiki rebaixadas deixam de ser `fraca` por serem contexto; `validar.py` confere `FRACAS_RESTANTES_RODADA4` menos `FRACAS_REBAIXADAS_R6` menos as substituídas pela rodada 5 = `FRACAS_DEPOIS_RODADA5`).

| alvo | wiki que era `fraca` (agora `contexto`, qualidade NULL) |
|---|---|
| evento `ev-1999-segundo-mandato-de-fhc` | https://pt.wikipedia.org/wiki/Fernando_Henrique_Cardoso |
| evento `ev-2011-s-p-rebaixa-a-nota-dos-estados-unidos` | https://en.wikipedia.org/wiki/United_States_federal_government_credit-rating_downgrades |

| relação (origem_ref) | wiki rebaixada |
|---|---|
| `teia E[8].r[0]` | https://en.wikipedia.org/wiki/Rede_Super |
| `teia E[11].r[0]` | https://en.wikipedia.org/wiki/Daniel_Vorcaro |
| `teia E[13].r[0]` | https://en.wikipedia.org/wiki/Andr%C3%A9_Valad%C3%A3o |

## 22. Rodada 5: as últimas lacunas de fonte (`data/curadoria/evidencias-rodada5.json`)

8 fontes novas (`boa`, papel `sustenta`) para 8 alvos e 4 URLs distintas (uma URL pode estar ligada a vários alvos: a matéria do Estadão sobre Caio Carvalho Barros está em 5 relações, com uma só `evidencia`). 2 têm `substitui` (cscb.ca no evento de 2018; Brasil 247 em `N[138].fam_de`): a fraca recebe `substituida_por` em `evidencias-adicionais.json` e sai da ligação, como na rodada 4; as outras são fontes adicionais. Aplicadas por `curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, depois das rodadas 1-4) e conferidas por `curadoria.conferir_substituicoes`. Ligações `fraca` no banco: 4 -> 0 (depois da rodada 5: 0; as 2 wiki que sobravam já eram `contexto` pela R6). A natureza vem de `eventos-natureza.json`, regerado (R5). Detalhe em `relatorio-evidencias-adicionais.md`, seção "Rodada 5".

| natureza (todos os eventos) | eventos |
|---|---:|
| alegacao | 6 |
| documentada | 245 |
| investigacao | 36 |
| reportada | 220 |

## 23. Rodada 6: ranking de empresas, lideranças parlamentares e fatos de 2024

Arquivos à mão: `entidades-adicionais.json` (entidades novas, criadas no mesmo ponto das `entidades_novas` do dossiê: `sandra-starling`, `jose-anibal`, `pedrinho-abrao`, `odelmo-leao`, `walter-pinheiro`, `souza-cruz`, `brahma`, `elcio-alvares`, `telesp`, `furnas`, `eletropaulo`, `cesp`, `embraer`, `klabin`, `belgo-mineira`, `aracruz`, `tam`, `sabesp`, `marfrig`, `tim`, `hsbc-brasil`), `ranking-empresa-correcoes.json` (`curadoria.aplicar_ranking_empresa_correcoes`), `mandatos-adicionais.json` (`aplicar_mandatos_adicionais` + `ligar_fontes_mandatos_adicionais`), `eventos-adicionais.json` (`aplicar_eventos_adicionais`), `evidencias-rodada6.json` (via `ler_evidencias_adicionais`, depois das rodadas 1-5) e as correções `"rodada": 6` de `evento-correcoes.json`. Regerados: `eventos-natureza.json` (R5), `evento-entidade-auto.json` e `mandato-oficial.json` (+ `relatorio-mandatos-oficial.md`); `gerar_curadoria.py` pula `ranking_correcoes` no banco temporário porque `gerar_complementos_brasil` casa as linhas com o bruto pela posição original.

### Ranking de empresas

Base do ranking: lucro líquido em R$ pela legislação societária (BR GAAP); US GAAP/Euromoney em US$ só como fonte de `contexto`. Fontes na tabela aditiva `ranking_evidencia` (papel, trecho, nota); `ranking_empresa.evidencia_id` = fonte principal. Nos anos tocados, `posicao` e `pct_total` foram recalculados com as regras da carga bruta (conferidas nas 397 linhas de `data/raw/brasil.json`): lucros em ordem decrescente e depois os prejuízos do maior para o menor; `pct_total = round(lucro / PIB do ano (macro.pib) * 100, 3)`.

| ano | cobertura | linhas | inseridas | atualizadas (valor) | só fontes/obs |
|---|---|---:|---:|---:|---:|
| 1995 | fraca -> parcial | 13 | 6 | 1 | 1 |
| 1996 | fraca -> parcial | 17 | 3 | 4 | 1 |
| 1997 | fraca -> parcial | 18 | 1 | 3 | 2 |
| 1998 | parcial | 15 | 0 | 2 | 4 |
| 1999 | parcial | 18 | 0 | 1 | 1 |
| 2002 | parcial -> completa | 24 | 0 | 0 | 3 |
| 2008 | parcial | 20 | 0 | 0 | 1 |
| 2013 | parcial | 15 | 1 | 1 | 1 |
| 2014 | parcial | 16 | 1 | 0 | 0 |
| 2015 | parcial | 15 | 0 | 0 | 13 |
| 2022 | parcial | 15 | 0 | 2 | 2 |

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 1995 | `banco-do-brasil` | obs | https://www25.senado.leg.br/web/atividade/pronunciamentos/-/p/pronunciamento/184275 |
| 1995 | `bradesco` | **inserida** (0.54) | https://www1.folha.uol.com.br/fsp/1996/1/24/dinheiro/14.html |
| 1995 | `eletrobras` | **inserida** (0.75) | https://www1.folha.uol.com.br/fsp/1997/3/20/dinheiro/11.html |
| 1995 | `itau-unibanco` | **inserida** (0.374) | https://www1.folha.uol.com.br/fsp/1996/2/14/dinheiro/24.html |
| 1995 | `petrobras` | **inserida** (0.57) | https://www1.folha.uol.com.br/fsp/1997/2/01/dinheiro/25.html |
| 1995 | `souza-cruz` | **inserida** (0.21) | https://www1.folha.uol.com.br/fsp/1996/2/03/dinheiro/8.html |
| 1995 | `unibanco` | **inserida** (0.1546) | https://www1.folha.uol.com.br/fsp/1996/2/14/dinheiro/24.html |
| 1995 | `vale` | lucro_brl_bi 0.31 -> 0.329; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/1996/2/17/brasil/29.html |
| 1996 | `banco-do-brasil` | lucro_brl_bi -7.28 -> -7.525; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi210225.htm |
| 1996 | `bradesco` | lucro_brl_bi 0.82 -> 0.8245; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi180215.htm |
| 1996 | `eletrobras` | **inserida** (2.393) | https://www1.folha.uol.com.br/fsp/1997/3/20/dinheiro/11.html |
| 1996 | `itau-unibanco` | obs | https://www1.folha.uol.com.br/fsp/1997/2/19/dinheiro/18.html |
| 1996 | `petrobras` | **inserida** (0.664) | https://www1.folha.uol.com.br/fsp/1997/2/01/dinheiro/25.html |
| 1996 | `souza-cruz` | **inserida** (0.204) | https://www1.folha.uol.com.br/fsp/dinheiro/fi010221.htm |
| 1996 | `unibanco` | lucro_brl_bi 0.28 -> 0.285; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi260221.htm |
| 1996 | `vale` | lucro_brl_bi 0.518 -> 0.517; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi11039811.htm |
| 1997 | `brahma` | **inserida** (0.469) | https://www1.folha.uol.com.br/fsp/dinheiro/fi19029820.htm |
| 1997 | `embratel` | só fontes | https://teletime.com.br/16/04/1999/embratel-divulga-resultados-do-exercicio-de-1998 |
| 1997 | `itau-unibanco` | lucro_brl_bi 0.874 -> 0.721; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi10029805.htm |
| 1997 | `telebras` | lucro_brl_bi 4.3 -> 3.9; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi240110.htm |
| 1997 | `unibanco` | lucro_brl_bi 0.42 -> 0.4308; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi15029817.htm |
| 1997 | `vale` | só fontes | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 1998 | `bradesco` | lucro_brl_bi 0.539 -> 1.014; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi04039921.htm |
| 1998 | `embratel` | só fontes | https://teletime.com.br/16/04/1999/embratel-divulga-resultados-do-exercicio-de-1998 |
| 1998 | `itau-unibanco` | só fontes | https://www1.folha.uol.com.br/fsp/dinheiro/fi23029921.htm |
| 1998 | `petrobras` | lucro_brl_bi 1.4 -> 1.433; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi1502200020.htm |
| 1998 | `unibanco` | só fontes | https://www.sec.gov/Archives/edgar/data/0001038583/000103858303000017/form20f.htm |
| 1998 | `vale` | só fontes | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 1999 | `petrobras` | lucro_brl_bi 1.7 -> 1.771; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi1502200020.htm |
| 1999 | `vale` | só fontes | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 2002 | `embratel` | só fontes | https://www.sec.gov/Archives/edgar/data/0001066117/000119312504093082/d20f.htm |
| 2002 | `telemar` | obs | https://www.sec.gov/Archives/edgar/data/0001066113/000095012305007975/y10162e20vf.htm |
| 2002 | `telesp-celular-participacoes` | só fontes | https://www.sec.gov/Archives/edgar/data/1071337/000095012304008074/y98693e20vf.htm |
| 2008 | `sadia` | só fontes | https://www.latibex.com/docs/Documentos/esp/resulta/2009/Sadia_Release_4T08.pdf |
| 2013 | `banco-do-brasil` | obs | https://api.mziq.com/mzfilemanager/v2/d/0501147c-6489-4fc5-8ac2-a39baa2721b9/f03b39dd-280e-1d2b-9633-0af4b617fc82?origin=1 |
| 2013 | `bndes` | lucro_brl_bi 8.154 -> 8.15; derivado 1 -> 0; obs | https://bndes.gov.br/SiteBNDES/bndes/bndes_en/conteudos/noticia/BNDES-posts-net-earnings-of-R$-8.15-billion-in-2013 |
| 2013 | `itausa` | **inserida** (6.011) | https://api.mziq.com/mzfilemanager/v2/d/afd9200b-9b01-4d1c-bdd9-9b2c1e9b3b4d/40c47fd1-5af8-4dd5-aa70-b2287e8f1f81?origin=2 |
| 2014 | `itausa` | **inserida** (8.161) | https://api.mziq.com/mzfilemanager/v2/d/afd9200b-9b01-4d1c-bdd9-9b2c1e9b3b4d/40c47fd1-5af8-4dd5-aa70-b2287e8f1f81?origin=2 |
| 2015 | `ambev` | só fontes | https://data.sec.gov/api/xbrl/companyconcept/CIK0001565025/ifrs-full/ProfitLossAttributableToOwnersOfParent.json |
| 2015 | `banco-do-brasil` | só fontes | https://api.mziq.com/mzfilemanager/v2/d/0501147c-6489-4fc5-8ac2-a39baa2721b9/0356392e-5816-866a-bc0d-e4a5b3d257de?origin=1 |
| 2015 | `bb-seguridade` | só fontes | https://exame.com/negocios/bb-seguridade-lucro-liquido-ajustado-vai-a-r-3-9-bi-alta-de-22-4 |
| 2015 | `bndes` | só fontes | https://bndes.gov.br/SiteBNDES/bndes/bndes_en/conteudos/noticia/BNDES-posts-earnings-of-R$-6.2-billion-in-2015 |
| 2015 | `bradesco` | só fontes | https://www.sec.gov/Archives/edgar/data/0001160330/000129281416003473/bbdbook4q15_6k.htm |
| 2015 | `eletrobras` | só fontes | https://exame.com/negocios/os-25-maiores-prejuizos-de-2015-ano-de-perdas-historicas |
| 2015 | `itau-unibanco` | só fontes | https://www.sec.gov/Archives/edgar/data/0001132597/000114420416081111/v430347_ex99-1.htm |
| 2015 | `itausa` | só fontes | https://api.mziq.com/mzfilemanager/v2/d/afd9200b-9b01-4d1c-bdd9-9b2c1e9b3b4d/40c47fd1-5af8-4dd5-aa70-b2287e8f1f81?origin=2 |
| 2015 | `jbs` | só fontes | https://www.wattagnet.com/broilers-turkeys/processing-slaughter/article/15517159/jbs-net-income-up-128-percent-in-2015-despite-q4-losses |
| 2015 | `petrobras` | só fontes | https://istoedinheiro.com.br/petrobras-fecha-2015-com-prejuizo-recorde-de-r-348-bilhoes |
| 2015 | `santander-brasil` | obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281416003390/bsbrdfbrgaap4q15_6k.htm |
| 2015 | `telefonica-brasil` | obs | https://data.sec.gov/api/xbrl/companyconcept/CIK0001066119/ifrs-full/ProfitLoss.json |
| 2015 | `vale` | só fontes | https://exame.com/negocios/os-25-maiores-prejuizos-de-2015-ano-de-perdas-historicas |
| 2022 | `americanas` | lucro_brl_bi -13.22 -> -12.9; obs | https://forbes.com.br/negocios/2023/11/americanas-perda-de-r-13-bi-em-2022-e-de-r-62-bi-em-2021-revertendo-lucro |
| 2022 | `bradesco` | lucro_brl_bi 21.223 -> 20.732; obs | https://api.mziq.com/mzfilemanager/v2/d/80f2e993-0a30-421a-9470-a4d5c8ad5e9f/3053f2d1-0b01-5a5c-b1c8-755424d14edb?origin=1 |
| 2022 | `gerdau` | obs | https://data.sec.gov/api/xbrl/companyconcept/CIK0001073404/ifrs-full/ProfitLossAttributableToOwnersOfParent.json |
| 2022 | `santander-brasil` | obs | https://www.sec.gov/Archives/edgar/data/1471055/000147105523000001/EDGAR_BRGAAP_4T22.htm |

Posições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):

- 1995: `banco-do-brasil` 6 -> 12, `cosipa` 5 -> 11, `csn` 4 -> 10, `cst` 3 -> 8, `usiminas` 1 -> 6, `vale` 2 -> 5
- 1996: `banco-do-brasil` 12 -> 15, `banco-real` 5 -> 7, `bndes` 1 -> 2, `bradesco` 2 -> 3, `caixa` 8 -> 10, `csn` 7 -> 9, `cst` 10 -> 13, `gerdau` 11 -> 14, `itau-unibanco` 3 -> 4, `unibanco` 6 -> 8, `usiminas` 9 -> 11, `vale` 4 -> 6
- 1997: `acominas` 13 -> 14, `banco-real` 10 -> 11, `bradesco` 3 -> 2, `cosipa` 14 -> 15, `csn` 7 -> 8, `cst` 12 -> 13, `gerdau` 11 -> 12, `itau-unibanco` 2 -> 4, `unibanco` 8 -> 9, `usiminas` 9 -> 10, `vale` 4 -> 3
- 1998: `bradesco` 5 -> 4, `itau-unibanco` 4 -> 5
- 2013: `cemig` 10 -> 11, `cielo` 11 -> 12, `eletrobras` 14 -> 15, `ogpar` 13 -> 14, `santander-brasil` 8 -> 9, `telefonica-brasil` 9 -> 10, `vale` 12 -> 13
- 2014: `bb-seguridade` 9 -> 10, `btg-pactual` 10 -> 11, `caixa` 6 -> 7, `cemig` 12 -> 13, `cielo` 11 -> 12, `eletrobras` 15 -> 16, `ogpar` 14 -> 15, `petrobras` 13 -> 14, `santander-brasil` 7 -> 8, `telefonica-brasil` 8 -> 9

91 ligações em `ranking_evidencia`; 36 evidências novas. Lacunas registradas no arquivo: (1) Petrobras 1997: sem lucro em R$ pela legislação societária (o 20-F FY2001 traz US$ 1.419 mi em US GAAP; 1º semestre/1997 ≈ R$ 252 mi pela Folha de 14/8/1998). Não inserida: o US GAAP em US$ não é a base do ranking. (2) Itaú 1996 anual (derivável: 721/1,22 ≈ 591 mi; fica na obs do 0,676). (3) Telebrás 1995 e 1996 anual (9 meses de 1996: holding R$ 2,38 bi). (4) Eletrobras 1997; Light e Banco Real 1995-1997; Brahma 1995-1996 (1996 ≈ R$ 400 mi derivável, não confirmado). (5) Banco do Brasil 1998 (US$ 720 mi na Euromoney): o BB não está na lista de 1998 e o valor em R$ não foi aberto; nada inserido.

### Lideranças parlamentares (`mandatos-adicionais.json`)

| entidade | cargo | ano | partido/UF | motivo | evidência da linha |
|---|---|---|---|---|---|
| `elcio-alvares` | senador | 1995 | PFL/ES | Líder do governo FHC no Senado | sem API (sem fonte oficial) |
| `elcio-alvares` | senador | 1998 | PFL/ES | Líder do governo FHC no Senado (desde o primeiro ano do mandato de FHC) | sem API (sem fonte oficial) |
| `jose-roberto-arruda` | senador | 1999 | PSDB/DF | Líder do governo no Senado a partir de 3/8/1999 | https://legis.senado.leg.br/dadosabertos/senador/46 |
| `romero-juca` | senador | 2001 | PSDB/RR | Líder do governo FHC no Senado, depois da saída de José Roberto Arruda (24/5/2001) | https://legis.senado.leg.br/dadosabertos/senador/73 |
| `romero-juca` | senador | 2002 | PSDB/RR | Líder do governo FHC no Senado (dois anos na liderança, segundo ele próprio) | https://legis.senado.leg.br/dadosabertos/senador/73 |
| `jutahy-junior` | deputado | 2001 | PSDB/BA | Líder do PSDB (Bloco PSDB/PTB) na Câmara a partir de 21/2/2001, no lugar de Aécio Neves | https://dadosabertos.camara.leg.br/api/v2/deputados/74570 |
| `elcio-alvares` | senador | 1996 | PFL/ES | Líder do governo FHC no Senado | sem API (sem fonte oficial) |
| `elcio-alvares` | senador | 1997 | PFL/ES | Líder do governo FHC no Senado | sem API (sem fonte oficial) |
| `sandra-starling` | deputado | 1996 | PT/None | Líder do PT na Câmara em 1996 | sem API (sem fonte oficial) |
| `jose-anibal` | deputado | 1996 | PSDB/None | Líder do PSDB na Câmara em 1996 | sem API (sem fonte oficial) |
| `pedrinho-abrao` | deputado | 1996 | PTB/None | Líder do PTB na Câmara em 1996 | sem API (sem fonte oficial) |
| `odelmo-leao` | deputado | 1996 | PPB/None | Líder do PPB (Bloco PPB/PL) na Câmara em 1996 | sem API (sem fonte oficial) |
| `walter-pinheiro` | deputado | 2001 | PT/BA | Líder do PT na Câmara a partir de fev/2001 (Diário da Câmara de 21/2/2001) | sem API (sem fonte oficial) |

Cada linha traz a fonte oficial do destaque ligada à relação `mandato:<id>` (22 ligações, inclusive na filiação das linhas sem API). Confronto com as APIs (`mandato-oficial.json`): 324 linhas, 302 confirmadas, 2 divergentes, 20 sem fonte oficial (as linhas de pessoa fora da coleta das APIs entram em `sem_fonte`). Pendências: José Roberto Arruda (1995-1998): '2º Vice-Líder do Governo' (perfil/46, 20/3/1995 a 31/1/1999) não é destaque: sem linha. (mais votado de 1998) (1998): Não encontrado. Enéas refutado (a API da Câmara não o lista na 51ª legislatura; concorreu à Presidência em 1998); a Folha de 8/11/1998 só traz o partido mais votado (PFL, 10,863 milhões). Nada inserido. Líder do governo no Senado (jan-ago/1999) (1999): Rodada 12: lacuna. Élcio Álvares deixou o Senado em 31/1/1999 (perfil/18: mandato 1991-1999) e Arruda só assume em 3/8/1999 (perfil/46). O Relatório da Presidência do Senado de 1999 (https://www.senado.gov.br/relatorios_sgm/relpresi/1999/012-Presidencia.PDF) registra, em 20.05.99 (DSF de 21.05.99), manifestação que 'se despede da função de Líder do Governo no Senado'; o nome do líder não ficou claro na leitura automática. Abrir esse PDF e o DSF de 21/5/1999 no Chrome. Líder do PFL na Câmara (1996) (1996): Rodada 12: lacuna. Os Diários de 14, 15 e 16/2/1996 (https://imagem.camara.leg.br/Imagem/d/pdf/DCD14FEV1996.pdf, DCD15FEV1996.pdf, DCD16FEV1996.pdf) não trazem indicação do líder do PFL (nem do PMDB, que já tem linha de Michel Temer em 1996); procurar em outras edições de fev-mar/1996 (DCDddMMMaaaa.pdf). Líderes de bancada no Senado em 1996 (PFL, PSDB, PT, PPB, PTB) (1996): Rodada 12: lacuna. Só o PMDB (Jader Barbalho) tem linha. Não foi encontrada fonte oficial datada de 1996 aberta por esta coleta; os cabeçalhos 'Como Líder' dos discursos no DSF de 1996 (www25.senado.leg.br/web/atividade/pronunciamentos/-/p/parlamentar/<código>/1996) e as comunicações de liderança no DSF de fev-mar/1996 resolvem. O Relatório da Presidência de 2000 (https://www.senado.gov.br/Relatorios_SGM/RelPresi/2000/009-Lideres.pdf) só traz os líderes de 2000. Presidente e vice-presidente da República (11 mandatos sem fonte oficial de página) (1995-2023): Rodada 12: lacuna. Nenhuma fonte oficial nova aberta (a cota de WebFetch/WebSearch acabou nos Diários da Câmara). A galeria do Planalto (https://www.gov.br/planalto/pt-br/conheca-a-presidencia/acervo/galeria-de-presidentes) exige login na coleta automática; abrir no Chrome. Alternativas: perfis dos senadores Marco Maciel e José Alencar e do senador Hamilton Mourão em www25.senado.leg.br/web/senadores/senador/-/perfil/<código> (vice-presidência), diplomações no tse.jus.br e os Diários do Congresso/da Câmara das sessões de posse (1/1 de 1995, 2003, 2011, 2019 e 2023).

### Fatos novos e correções de texto

- `ev-2024-trump-e-eleito-presidente-dos-eua-pela` (Y[2024].intl.eventos[4], peso 4, documentada): Trump é eleito presidente dos EUA pela segunda vez
- `ev-2024-cupula-do-g20-no-rio-lanca-alianca` (Y[2024].intl.eventos[5], peso 4, documentada): Cúpula do G20 no Rio lança Aliança contra a Fome
- correção `ev-2012-rio-20-reune-88-chefes-de-estado-e-de` (descricao): "realizada de 13 a 22 de junho de 2012 no Rio de Janeiro" -> "realizada no Rio de Janeiro de 20 a 22 de junho de 2012 (precedida pela reunião preparatória de 13 a 15/6)"
- correção `ev-1997-novas-mesas-da-camara-e-do-senado` (descricao): "Em fevereiro de 1997 Michel Temer (PMDB-SP) assume a presidência da Câmara, no lugar de Luís Eduardo Magalhães, e Antonio Carlos Magalhães (PFL-BA) a do Senado, eleito com 52 votos, no lugar de José Sarney." -> "Em 4/2/1997 Antonio Carlos Magalhães (PFL-BA) é eleito presidente do Senado com 52 votos, no lugar de José Sarney, e em 5/2 Michel Temer (PMDB-SP) é eleito presidente da Câmara com 257 votos, no lugar de Luís Eduardo Magalhães."
- correção `ev-1999-reeleicao-de-temer-e-antonio-carlos` (descricao): "Em 1/2/1999 Michel Temer (PMDB-SP) é reeleito presidente da Câmara e Antonio Carlos Magalhães (PFL-BA), presidente do Senado, este com 70 votos." -> "Em 1/2/1999 Antonio Carlos Magalhães (PFL-BA) é reeleito presidente do Senado com 70 votos e, em 2/2, Michel Temer (PMDB-SP) é reeleito presidente da Câmara, como candidato único, com 422 votos."

Bancadas: não alteradas (a tabela acadêmica da Câmara não substitui a carga; o snapshot oficial do Senado em 2000 traz blocos, não os 81 nomes; não há linhas de bancada do Senado 1995-1998 no banco e a aproximação da pesquisa não foi usada).


## 24. Rodada 7: ranking de lucros de 1995-1997 com a Folha de S.Paulo

Arquivo à mão: `ranking-empresa-correcoes-r7.json` (mesmo formato da rodada 6, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R7)` logo depois dela; `gerar_curadoria.py` também o pula no banco temporário) e a entidade `telesp` em `entidades-adicionais.json`. Os `de` são os valores que a rodada 6 gravou; uma `anterior` que já estava em `ranking_evidencia` (Souza Cruz 1995) é reclassificada para `contexto` em vez de duplicada. Mesma base (lucro em R$ pela legislação societária) e mesmas regras de `posicao` e `pct_total` da rodada 6. **Telesp 1996** (subsidiária da Telebrás) foi inserida: o ranking já convive com holding e subsidiária no mesmo ano (Telebrás e Embratel em 1997; Itaúsa e Itaú Unibanco de 2010 a 2020), e a obs registra a dupla contagem.

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 1995 | `caixa` | **inserida** (0.2213) | https://www1.folha.uol.com.br/fsp/1997/3/19/dinheiro/8.html |
| 1995 | `csn` | lucro_brl_bi 0.107 -> 0.121; obs | https://www1.folha.uol.com.br/fsp/1997/3/06/dinheiro/18.html |
| 1995 | `itau-unibanco` | obs | https://www1.folha.uol.com.br/fsp/1996/2/14/dinheiro/24.html |
| 1995 | `souza-cruz` | lucro_brl_bi 0.21 -> 0.192; obs | https://www1.folha.uol.com.br/fsp/1996/2/03/dinheiro/8.html |
| 1996 | `caixa` | lucro_brl_bi 0.27 -> 0.26; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/1997/3/19/dinheiro/8.html |
| 1996 | `csn` | só fonte | https://web.bndes.gov.br/bib/jspui/bitstream/1408/19860/1/PR_Inform%20Set%20%20AOI2%20Geset%20Min%20e%20Metal_213893_%20n%2039_BD.pdf |
| 1996 | `itau-unibanco` | lucro_brl_bi 0.676 -> 0.602; obs | https://www1.folha.uol.com.br/fsp/1997/2/19/dinheiro/18.html |
| 1996 | `souza-cruz` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi010221.htm |
| 1996 | `telebras` | **inserida** (3.254) | https://www1.folha.uol.com.br/fsp/1997/2/27/dinheiro/17.html |
| 1996 | `telesp` | **inserida** (0.8128) | https://www1.folha.uol.com.br/fsp/1997/3/05/dinheiro/24.html |
| 1997 | `bradesco` | lucro_brl_bi 0.84 -> 0.8305; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi05029806.htm |
| 1997 | `csn` | só fonte | https://web.bndes.gov.br/bib/jspui/bitstream/1408/19860/1/PR_Inform%20Set%20%20AOI2%20Geset%20Min%20e%20Metal_213893_%20n%2039_BD.pdf |
| 1997 | `souza-cruz` | **inserida** (0.308) | https://www1.folha.uol.com.br/fsp/dinheiro/fi03029808.htm |

Posições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):

- 1995: `banco-do-brasil` 12 -> 13, `cosipa` 11 -> 12, `csn` 10 -> 11, `cst` 8 -> 9, `souza-cruz` 7 -> 8, `unibanco` 9 -> 10
- 1996: `banco-do-brasil` 15 -> 17, `banco-real` 7 -> 9, `bndes` 2 -> 3, `bradesco` 3 -> 4, `caixa` 10 -> 13, `csn` 9 -> 11, `cst` 13 -> 15, `eletrobras` 1 -> 2, `gerdau` 14 -> 16, `itau-unibanco` 4 -> 7, `petrobras` 5 -> 6, `souza-cruz` 12 -> 14, `unibanco` 8 -> 10, `usiminas` 11 -> 12, `vale` 6 -> 8
- 1997: `acominas` 14 -> 15, `banco-real` 11 -> 12, `cosipa` 15 -> 16, `cst` 13 -> 14, `gerdau` 12 -> 13

17 ligações novas em `ranking_evidencia` (9 evidências novas). Lacunas registradas no arquivo: (1) Petrobras 1997 (R$ societário) (2) Eletrobras 1997 (não achada nos índices de fev–mai/1998) (3) Telebrás 1995 (4) Light 1995–97 anual (só 1º tri/97 e /98) (5) Banco Real 1995–97 (só ganho FCVS 1996) (6) Telebrás 1996: só a manchete da matéria foi aberta (o trecho é a própria manchete); não se distingue consolidado de controladora.


## 25. Rodada 8: ranking de lucros de 1997-2009 com a Folha de S.Paulo

Arquivo à mão: `ranking-empresa-correcoes-r8.json` (mesmo formato das rodadas 6 e 7, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R8)` logo depois da 7; `gerar_curadoria.py` também o pula no banco temporário). Material: 145 blocos de texto literal de matérias da Folha (acervo `fsp`, 1999-2010) e 4 matérias de resultados de 1998. Base: lucro líquido em R$ pela legislação societária, valor do balanço divulgado na época; reapresentações, IFRS, US GAAP e lucro 'recorrente' só como contexto. Atualiza onde a Folha diverge além do arredondamento ou onde o banco tinha valor derivado/aproximado; insere as empresas que entram no top 15 de lucros do ano (e prejuízos de R$ 0,2 bi ou mais); onde o valor já era igual, a Folha só é ligada (`sustenta`) se a fonte do banco não era imprensa nem documento primário da época, e passa a principal onde a principal era a Wikipédia. Nomes de época por `nome_epoca` (Banespa e Santander Banespa em `santander-brasil`, ABN Amro Real em `banco-real`, Oi em `telemar`, Telesp em `telefonica-brasil`). Entidades novas em `entidades-adicionais.json`: `furnas`, `eletropaulo`, `cesp`, `embraer`, `klabin`, `belgo-mineira`, `aracruz`, `tam`. A cobertura dos anos não muda: a Folha não é ranking fechado.

| ano | linhas | inseridas | valor atualizado | só fonte/obs | 1º lugar |
|---|---:|---:|---:|---:|---|
| 1997 | 18 | 2 | 0 | 1 | `telebras` (3.9) |
| 1998 | 15 | 2 | 1 | 0 | `petrobras` (1.433) |
| 1999 | 18 | 5 | 3 | 1 | `itau-unibanco` (1.869) |
| 2000 | 16 | 4 | 3 | 2 | `petrobras` (9.942) |
| 2001 | 21 | 8 | 3 | 1 | `petrobras` (9.9) |
| 2002 | 24 | 13 | 0 | 1 | `petrobras` (8.1) |
| 2003 | 19 | 5 | 1 | 1 | `petrobras` (17.795) |
| 2004 | 19 | 8 | 1 | 2 | `petrobras` (17.861) |
| 2005 | 15 | 5 | 1 | 1 | `petrobras` (23.725) |
| 2006 | 15 | 5 | 1 | 2 | `petrobras` (25.919) |
| 2007 | 15 | 4 | 1 | 3 | `petrobras` (21.512) |
| 2008 | 20 | 7 | 1 | 0 | `petrobras` (33.9) |
| 2009 | 17 | 4 | 1 | 2 | `petrobras` (28.982) |

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 1997 | `petrobras` | **inserida** (1.53) | https://www1.folha.uol.com.br/fsp/dinheiro/fi13029916.htm |
| 1997 | `santander-brasil` | **inserida** (2.0, nome da época Banespa) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1602200004.htm |
| 1997 | `souza-cruz` | só fonte | https://www1.folha.uol.com.br/fsp/dinheiro/fi03029808.htm |
| 1998 | `banco-do-brasil` | **inserida** (0.87) | https://www1.folha.uol.com.br/fsp/dinheiro/fi09029909.htm |
| 1998 | `itau-unibanco` | lucro_brl_bi 0.963 -> 0.88; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi23029921.htm |
| 1998 | `souza-cruz` | **inserida** (0.4805) | https://www1.folha.uol.com.br/fsp/dinheiro/fi05029918.htm |
| 1999 | `banco-real` | **inserida** (0.253) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2902200015.htm |
| 1999 | `bndes` | **inserida** (0.682) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1003200113.htm |
| 1999 | `bradesco` | lucro_brl_bi 0.744 -> 1.105; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0102200015.htm |
| 1999 | `caixa` | **inserida** (0.3945) | https://www1.folha.uol.com.br/fsp/dinheiro/fi3003200014.htm |
| 1999 | `csn` | lucro_brl_bi 0.197 -> 0.332; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0103200020.htm |
| 1999 | `eletropaulo` | **inserida** (0.4044) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1603200120.htm |
| 1999 | `furnas` | **inserida** (0.334) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1303200137.htm |
| 1999 | `itau-unibanco` | lucro_brl_bi 1.955 -> 1.869; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi1602200004.htm |
| 1999 | `vale` | só fonte | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 2000 | `banco-real` | **inserida** (0.6492, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0903200204.htm |
| 2000 | `bndes` | **inserida** (0.8666) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1003200113.htm |
| 2000 | `bradesco` | lucro_brl_bi 1.799 -> 1.74; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0602200118.htm |
| 2000 | `csn` | lucro_brl_bi 0.5 -> 1.6; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200214.htm |
| 2000 | `eletrobras` | obs | https://brasilenergia.com.br/petroleoegas/arquivo/lucro-da-eletrobras-em-2001-cresce-324-e-supera-os-r-3-bilhoes |
| 2000 | `furnas` | **inserida** (0.629) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1303200137.htm |
| 2000 | `petrobras` | lucro_brl_bi 9.8 -> 9.942; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi1702200133.htm |
| 2000 | `telefonica-brasil` | **inserida** (1.47, nome da época Telesp) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2702200210.htm |
| 2000 | `vale` | só fonte | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 2001 | `banco-real` | **inserida** (0.7843, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0903200204.htm |
| 2001 | `bradesco` | lucro_brl_bi 2.27 -> 2.17; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0502200230.htm |
| 2001 | `caixa` | **inserida** (-4.687) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1203200221.htm |
| 2001 | `cesp` | **inserida** (-0.813) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1503200302.htm |
| 2001 | `csn` | lucro_brl_bi 1.24 -> 0.296; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200214.htm |
| 2001 | `eletrobras` | lucro_brl_bi 3.0 -> 3.3; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi1403200315.htm |
| 2001 | `eletropaulo` | **inserida** (0.567) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2603200315.htm |
| 2001 | `embraer` | **inserida** (1.1) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200211.htm |
| 2001 | `light` | **inserida** (-0.951) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200326.htm |
| 2001 | `santander-brasil` | **inserida** (1.089, nome da época Banespa) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2302200223.htm |
| 2001 | `telefonica-brasil` | **inserida** (1.576, nome da época Telesp) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2702200210.htm |
| 2001 | `vale` | só fonte | https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Julia_Campos_Alves_de_Brito.pdf |
| 2002 | `banco-real` | **inserida** (1.208, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1402200309.htm |
| 2002 | `brasil-telecom-participacoes` | **inserida** (0.443) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2102200308.htm |
| 2002 | `caixa` | **inserida** (1.081) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0103200312.htm |
| 2002 | `cesp` | **inserida** (-3.417) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1503200302.htm |
| 2002 | `csn` | **inserida** (-0.219) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200320.htm |
| 2002 | `eletrobras` | **inserida** (1.1) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1403200315.htm |
| 2002 | `eletropaulo` | **inserida** (-0.871) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2603200315.htm |
| 2002 | `embraer` | **inserida** (1.179) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200319.htm |
| 2002 | `klabin` | **inserida** (-0.208) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902200425.htm |
| 2002 | `light` | **inserida** (-1.255) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2703200326.htm |
| 2002 | `santander-brasil` | **inserida** (2.8, nome da época Banespa) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0402200322.htm |
| 2002 | `telefonica-brasil` | **inserida** (1.076, nome da época Telesp) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1202200311.htm |
| 2002 | `usiminas` | **inserida** (-0.321) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0503200417.htm |
| 2002 | `vale` | só fonte | https://www.maxwell.vrac.puc-rio.br/6590/6590_5.PDF |
| 2003 | `bndes` | **inserida** (1.038) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2603200424.htm |
| 2003 | `caixa` | **inserida** (1.616) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1202200409.htm |
| 2003 | `csn` | lucro_brl_bi 1.63 -> 1.031; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0203200531.htm |
| 2003 | `eletrobras` | **inserida** (0.323) | https://www1.folha.uol.com.br/fsp/dinheiro/fi3103200425.htm |
| 2003 | `klabin` | **inserida** (1.0) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902200425.htm |
| 2003 | `usiminas` | **inserida** (1.3) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0503200417.htm |
| 2003 | `vale` | só fonte | https://www.maxwell.vrac.puc-rio.br/6590/6590_5.PDF |
| 2004 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2202200517.htm |
| 2004 | `belgo-mineira` | **inserida** (1.291) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0203200531.htm |
| 2004 | `bndes` | **inserida** (1.498) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1802200616.htm |
| 2004 | `cst` | **inserida** (1.624) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0203200531.htm |
| 2004 | `eletrobras` | **inserida** (1.29) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2303200613.htm |
| 2004 | `embratel` | **inserida** (-0.3393) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0202200531.htm |
| 2004 | `gerdau` | lucro_brl_bi 3.38 -> 3.235; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0202200514.htm |
| 2004 | `santander-brasil` | **inserida** (1.75, nome da época Santander Banespa) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0902200616.htm |
| 2004 | `telesp-celular-participacoes` | **inserida** (-0.4902) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902200519.htm |
| 2004 | `usiminas` | **inserida** (3.019) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2602200513.htm |
| 2004 | `vale` | só fonte | https://monitormercantil.com.br/perdas-do-estado-na-privatizauuo-das-estatais-o-caso-vale |
| 2005 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2102200602.htm |
| 2005 | `banco-real` | **inserida** (1.4, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0902200722.htm |
| 2005 | `bndes` | **inserida** (3.202) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1802200616.htm |
| 2005 | `bradesco` | lucro_brl_bi 5.5 -> 5.514; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2302200608.htm |
| 2005 | `eletrobras` | **inserida** (0.9746) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2303200613.htm |
| 2005 | `santander-brasil` | **inserida** (1.643, nome da época Santander Banespa) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0902200616.htm |
| 2005 | `usiminas` | **inserida** (3.91) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0703200728.htm |
| 2006 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2802200730.htm |
| 2006 | `banco-real` | **inserida** (2.0, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0902200722.htm |
| 2006 | `bndes` | **inserida** (6.331) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902200822.htm |
| 2006 | `caixa` | só fonte | https://www.brasil247.com/?p=626399 |
| 2006 | `csn` | **inserida** (1.2) | https://www1.folha.uol.com.br/fsp/dinheiro/fi3103200726.htm |
| 2006 | `gerdau` | lucro_brl_bi 3.547 -> 3.492; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0802200721.htm |
| 2006 | `telemar` | **inserida** (1.3) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0903200719.htm |
| 2006 | `usiminas` | **inserida** (2.51) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0703200728.htm |
| 2007 | `ambev` | lucro_brl_bi 5.003 -> 2.8; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2902200822.htm |
| 2007 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2702200840.htm |
| 2007 | `banco-real` | **inserida** (2.975, nome da época ABN Amro Real) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2902200823.htm |
| 2007 | `bndes` | **inserida** (7.314) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902200822.htm |
| 2007 | `caixa` | só fonte | https://monitormercantil.com.br/?p=105425 |
| 2007 | `itau-unibanco` | só fonte | https://jornaldaparaiba.com.br/_/116258 |
| 2007 | `santander-brasil` | **inserida** (1.86) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2902200823.htm |
| 2007 | `telemar` | **inserida** (2.358, nome da época Oi) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2902200832.htm |
| 2008 | `aracruz` | **inserida** (-4.19) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2803200917.htm |
| 2008 | `bndes` | **inserida** (5.3) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1702200904.htm |
| 2008 | `braskem` | **inserida** (-2.49) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0603200916.htm |
| 2008 | `cemig` | **inserida** (1.88) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2403201009.htm |
| 2008 | `petrobras` | lucro_brl_bi 32.988 -> 33.9; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi0703200908.htm |
| 2008 | `suzano` | **inserida** (-0.451) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2503200921.htm |
| 2008 | `tam` | **inserida** (-1.3) | https://www1.folha.uol.com.br/fsp/dinheiro/fi3103200938.htm |
| 2008 | `telemar` | **inserida** (1.2, nome da época Oi) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0603200926.htm |
| 2009 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2602201002.htm |
| 2009 | `bndes` | **inserida** (6.7) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1902201018.htm |
| 2009 | `caixa` | só fonte | https://www.brasil247.com/?p=626399 |
| 2009 | `cemig` | **inserida** (1.86) | https://www1.folha.uol.com.br/fsp/dinheiro/fi2403201009.htm |
| 2009 | `cielo` | **inserida** (1.534) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0402201022.htm |
| 2009 | `csn` | lucro_brl_bi 2.598 -> 2.6; derivado 1 -> 0; obs | https://www1.folha.uol.com.br/fsp/dinheiro/fi2702201022.htm |
| 2009 | `telemar` | **inserida** (-0.436, nome da época Oi) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1603201028.htm |

Posições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):

- 1997: `acominas` 15 -> 17, `banco-do-brasil` 5 -> 7, `banco-real` 12 -> 14, `bradesco` 2 -> 4, `brahma` 7 -> 9, `cosipa` 16 -> 18, `csn` 8 -> 10, `cst` 14 -> 16, `embratel` 6 -> 8, `gerdau` 13 -> 15, `itau-unibanco` 4 -> 6, `souza-cruz` 11 -> 13, `unibanco` 9 -> 11, `usiminas` 10 -> 12, `vale` 3 -> 5
- 1998: `acesita` 11 -> 13, `acos-villares` 13 -> 15, `cosipa` 12 -> 14, `csn` 7 -> 9, `embratel` 10 -> 12, `gerdau` 9 -> 11, `unibanco` 6 -> 8, `usiminas` 8 -> 10
- 1999: `acesita` 11 -> 16, `acos-villares` 13 -> 18, `banco-do-brasil` 4 -> 5, `bradesco` 5 -> 4, `csn` 9 -> 12, `cst` 12 -> 17, `gerdau` 7 -> 10, `telesp-celular-participacoes` 10 -> 15, `unibanco` 6 -> 7, `usiminas` 8 -> 13
- 2000: `ambev` 11 -> 15, `banco-do-brasil` 6 -> 8, `csn` 10 -> 6, `embratel` 9 -> 14, `gerdau` 12 -> 16, `telemar` 8 -> 11, `unibanco` 7 -> 10
- 2001: `ambev` 9 -> 11, `banco-do-brasil` 7 -> 9, `csn` 6 -> 15, `eletrobras` 3 -> 2, `embratel` 13 -> 21, `gerdau` 10 -> 14, `telemar` 11 -> 16, `telesp-celular-participacoes` 12 -> 18, `unibanco` 8 -> 10, `vale` 2 -> 3
- 2002: `ambev` 6 -> 7, `banco-do-brasil` 4 -> 5, `bradesco` 5 -> 6, `embratel` 10 -> 20, `gerdau` 8 -> 14, `itau-unibanco` 2 -> 3, `telemar` 11 -> 21, `telesp-celular-participacoes` 9 -> 18, `unibanco` 7 -> 13, `vale` 3 -> 4
- 2003: `brasil-telecom-participacoes` 14 -> 19, `csn` 6 -> 13, `embratel` 11 -> 16, `telemar` 12 -> 17, `telesp-celular-participacoes` 13 -> 18, `unibanco` 10 -> 11
- 2004: `ambev` 10 -> 16, `csn` 8 -> 9, `telefonica-brasil` 7 -> 8, `telemar` 11 -> 17, `unibanco` 9 -> 15
- 2005: `ambev` 10 -> 13, `caixa` 8 -> 10, `gerdau` 6 -> 7, `telefonica-brasil` 7 -> 9, `unibanco` 9 -> 11
- 2006: `ambev` 8 -> 9, `banco-do-brasil` 3 -> 4, `bradesco` 4 -> 5, `caixa` 9 -> 11, `gerdau` 6 -> 7, `itau-unibanco` 5 -> 6, `telefonica-brasil` 7 -> 8, `unibanco` 10 -> 13
- 2007: `ambev` 6 -> 11, `banco-do-brasil` 5 -> 6, `caixa` 10 -> 12, `csn` 9 -> 10, `telefonica-brasil` 11 -> 13
- 2008: `ambev` 8 -> 9, `caixa` 10 -> 11, `gerdau` 9 -> 10, `sadia` 13 -> 18, `santander-brasil` 12 -> 14, `telefonica-brasil` 11 -> 12
- 2009: `ambev` 6 -> 7, `caixa` 7 -> 8, `csn` 8 -> 9, `eletrobras` 11 -> 14, `santander-brasil` 10 -> 12, `telefonica-brasil` 9 -> 10

137 ligações novas em `ranking_evidencia` (87 evidências novas). Registro no arquivo: 22 blocos `nao_aplicados` (sem o número anual claro, agregados, 'recorrente' ou outra base), 10 valores `fora_do_corte` (abaixo do 15º lucro do ano ou prejuízo menor que R$ 0,2 bi) e 41 blocos `confirmados` (valor igual ao do banco, que já tinha fonte primária ou imprensa da época). Lacunas: (1) Petrobras 2001 (9,9) e 2002 (8,1): a Folha dá 9,867/9,86 e 8,098 (consolidado); diferenças de arredondamento, valores mantidos (fonte primária da época já no banco). (2) Eletrobras 2000: continua o mínimo derivado (2,27); a Folha de 2003 dá 3,3 para 2001, o que sugere ≈ 2,49 (registrado na obs). (3) Bradesco 2009 e AmBev 2008-2009: não apareceram nos índices da Folha. (4) Eletrobras 2006 (1,161), Light 2007 (1,077) e outros: fora do top 15 (lista `fora_do_corte`). (5) Ano de 2002 continua `completa` (decisão da rodada 6) mesmo com 14 linhas novas da Folha, entre elas o Banespa em 2º lugar: a revisar pelo dono do projeto.


## 26. Rodada 9: ranking de lucros de 2009-2012 com a Folha de S.Paulo

Arquivo à mão: `ranking-empresa-correcoes-r9.json` (mesmo formato das rodadas 6-8, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R9)` logo depois da 8; `gerar_curadoria.py` também o pula no banco temporário). Material: 37 blocos de texto literal de matérias da Folha (acervo `fsp`, cadernos Dinheiro e Mercado, abril de 2010 a março de 2013), marcados pelo ano do resultado. Base: lucro líquido em R$ divulgado na época; de 2010 em diante o IFRS é a base societária das companhias abertas e vale o 'lucro líquido' do balanço ('recorrente', 'gerencial' e ajustado só como contexto). O valor do ano anterior citado na matéria do ano seguinte é aproveitado quando a linha não existe (CSN 2011); quando a linha já tem o valor da época e o comparativo do balanço seguinte diverge (reapresentação), fica o da época e a matéria entra como contexto (TAM 2008, Oi 2009). Mesmas regras de inserção (top 15 de lucros do ano e prejuízos de R$ 0,2 bi ou mais), de ligação (`sustenta` adicional só onde a fonte do banco não era imprensa nem documento primário da época; principal no lugar da Wikipédia) e de nome de época da rodada 8 (Oi em `telemar`, Telesp em `telefonica-brasil` em 2010). Entidades novas em `entidades-adicionais.json`: `sabesp`, `marfrig`, `tim`, `hsbc-brasil`. A cobertura dos anos não muda (2009 `parcial`; 2010-2012 `completa`, porque as linhas novas ficam abaixo dos maiores lucros já conferidos).

| ano | linhas | inseridas | valor atualizado | só fonte/obs | 1º lugar |
|---|---:|---:|---:|---:|---|
| 2008 | 20 | 0 | 0 | 1 | `petrobras` (33.9) |
| 2009 | 17 | 1 | 0 | 1 | `petrobras` (28.982) |
| 2010 | 15 | 5 | 0 | 4 | `petrobras` (35.189) |
| 2011 | 18 | 8 | 0 | 2 | `vale` (37.81) |
| 2012 | 17 | 4 | 1 | 1 | `petrobras` (21.182) |

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 2008 | `tam` | só fonte (contexto) | https://www1.folha.uol.com.br/fsp/dinheiro/fi3103200938.htm |
| 2009 | `tam` | **inserida** (1.343) | https://www1.folha.uol.com.br/fsp/dinheiro/fi0104201020.htm |
| 2009 | `telemar` | só fonte (contexto) | https://www1.folha.uol.com.br/fsp/dinheiro/fi1603201028.htm |
| 2010 | `banco-do-brasil` | só fonte | https://www.dieese.org.br/desempenhodosbancos/2012/desempenhoBancos2011.pdf |
| 2010 | `bradesco` | só fonte | https://www.dieese.org.br/desempenhodosbancos/2012/desempenhoBancos2011.pdf |
| 2010 | `braskem` | **inserida** (1.889) | https://www1.folha.uol.com.br/fsp/mercado/me1803201126.htm |
| 2010 | `csn` | **inserida** (2.5) | https://www1.folha.uol.com.br/fsp/mercado/me3003201121.htm |
| 2010 | `itau-unibanco` | só fonte | https://www.dieese.org.br/desempenhodosbancos/2012/desempenhoBancos2011.pdf |
| 2010 | `santander-brasil` | só fonte | https://www.sec.gov/Archives/edgar/data/0001471055/000129281411000268/bsbrdfbrgaap4q10_6k.htm |
| 2010 | `suzano` | **inserida** (0.769) | https://www1.folha.uol.com.br/fsp/mercado/me0203201116.htm |
| 2010 | `telefonica-brasil` | **inserida** (2.4, nome da época Telesp) | https://www1.folha.uol.com.br/fsp/mercado/me1702201109.htm |
| 2010 | `telemar` | **inserida** (1.75, nome da época Oi) | https://www1.folha.uol.com.br/fsp/mercado/me0503201111.htm |
| 2011 | `banco-do-brasil` | só fonte | https://www.dieese.org.br/desempenhodosbancos/2012/desempenhoBancos2011.pdf |
| 2011 | `csn` | **inserida** (3.7) | https://www1.folha.uol.com.br/fsp/mercado/101037-csn-tem-lucro-trimestral-60-menor-e-fecha-2012-com-prejuizo.shtml |
| 2011 | `gol` | **inserida** (-0.7104) | https://www1.folha.uol.com.br/fsp/mercado/33855-gol-corta-voos-depois-de-prejuizo-de-r-710-mi.shtml |
| 2011 | `marfrig` | **inserida** (-0.746) | https://www1.folha.uol.com.br/fsp/mercado/33631-marfrig-tem-prejuizo-de-r-746-milhoes-em-2011.shtml |
| 2011 | `sabesp` | **inserida** (1.22) | https://www1.folha.uol.com.br/fsp/mercado/33288-sabesp-tem-lucro-de-r-122-bi-em-2011.shtml |
| 2011 | `tam` | **inserida** (-0.3351) | https://www1.folha.uol.com.br/fsp/mercado/25750-tam-encerra-2011-com-prejuizo-de-r-335-milhoes.shtml |
| 2011 | `telefonica-brasil` | **inserida** (5.1) | https://www1.folha.uol.com.br/fsp/mercado/26329-telefonica-e-tim-tem-receita-e-lucro-maiores-em-2011.shtml |
| 2011 | `telemar` | **inserida** (1.006, nome da época Oi) | https://www1.folha.uol.com.br/fsp/mercado/34424-lucro-da-oi-cai-49-apos-aumento-de-despesas.shtml |
| 2011 | `tim` | **inserida** (1.3) | https://www1.folha.uol.com.br/fsp/mercado/26329-telefonica-e-tim-tem-receita-e-lucro-maiores-em-2011.shtml |
| 2011 | `vale` | só fonte | https://forbes.com.br/forbes-money/2023/03/estes-sao-os-maiores-lucros-anuais-de-empresas-listadas-na-bolsa |
| 2012 | `banco-do-brasil` | obs | https://www1.folha.uol.com.br/fsp/mercado/95021-bb-eleva-fatia-de-mercado-e-ganha-cliente-com-juro-baixo.shtml |
| 2012 | `csn` | **inserida** (-0.4201) | https://www1.folha.uol.com.br/fsp/mercado/101037-csn-tem-lucro-trimestral-60-menor-e-fecha-2012-com-prejuizo.shtml |
| 2012 | `embraer` | **inserida** (0.698) | https://www1.folha.uol.com.br/fsp/mercado/98347-lucro-da-embraer-sobe-347-em-2012.shtml |
| 2012 | `gol` | **inserida** (-1.5) | https://www1.folha.uol.com.br/fsp/mercado/100723-so-a-agua-sera-gratuita-nos-voos-da-gol.shtml |
| 2012 | `hsbc-brasil` | **inserida** (1.3) | https://www1.folha.uol.com.br/fsp/mercado/97147-lucro-do-hsbc-brasil-cai-26-em-2012.shtml |
| 2012 | `santander-brasil` | lucro_brl_bi 6.329 -> 2.69; obs | https://www1.folha.uol.com.br/fsp/mercado/91652-lucro-do-santander-no-brasil-cai-24-em-2012-e-atinge-r-27-bi.shtml |

Posições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):

- 2009: `eletrobras` 14 -> 15, `telemar` 15 -> 16
- 2012: `caixa` 9 -> 8, `cemig` 12 -> 11, `eletrobras` 13 -> 15, `itausa` 10 -> 9, `santander-brasil` 8 -> 12, `telefonica-brasil` 11 -> 10

30 ligações novas em `ranking_evidencia` (24 evidências novas). Registro no arquivo: 3 blocos `nao_aplicados` (sem o lucro anual em R$ ou outra base), 6 valores `fora_do_corte` (abaixo do 15º lucro do ano ou prejuízo menor que R$ 0,2 bi) e 8 blocos `confirmados` (valor igual ao do banco, que já tinha fonte primária ou imprensa da época). Lacunas: (1) Derivados, não inseridos (o trecho só dá a variação): Suzano 2009 (R$ 769 mi com queda de 18,8% ≈ R$ 0,95 bi), Sabesp 2010 (R$ 1,22 bi com queda de 25% ≈ R$ 1,63 bi; seria o 14º lucro de 2010), HSBC Brasil 2011 (R$ 1,3 bi com queda de 2,6% ≈ R$ 1,33 bi) e Santander Brasil 2011 contábil (R$ 2,69 bi com queda de 24% ≈ R$ 3,5 bi). (2) Santander Brasil: 2012 passa ao lucro contábil (2,69); 2010 e 2011 continuam no número do DIEESE (7,383 e 7,756, o mesmo que a Folha dá para 2010 sem dizer a base) e 2009 no contábil derivado de US$ (1,805): a série mistura bases até achar o contábil de 2010-2011. (3) Comparativos reapresentados (provavelmente na adoção do IFRS completo em 2010), valores da época mantidos: Oi 2009 (R$ 5,09 bi no balanço de 2010 contra o prejuízo de R$ 436 mi), Oi 2010 (≈ R$ 1,97 bi implícito no balanço de 2011 contra R$ 1,75 bi), TAM 2008 (R$ 1,51 bi de prejuízo no balanço de 2009 contra 'da ordem de R$ 1,3 bilhão') e TAM 2009 (≈ R$ 1,25 bi implícito no balanço de 2010 contra R$ 1,343 bi). (4) Itaú Unibanco 2012 (13,589, derivado, principal Wikipédia), Caixa 2010-2012 e Itaúsa 2010-2012: sem bloco da Folha com o valor anual. (5) Cobertura de 2010-2012 continua `completa`: em 2010 e 2011 as linhas novas ficam todas abaixo do 10º lucro (a lista conferida era a dos 10 maiores); em 2012 o Santander desce de 8º para 12º com o lucro contábil, sem empresa nova acima dele. Nenhum ano muda de cobertura por causa da Folha.


## 27. Rodada 10: lacunas do ranking de lucros fechadas com fontes primárias

Arquivo à mão: `ranking-empresa-correcoes-r10.json` (mesmo formato das rodadas 6-9, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R10)` logo depois da 9; `gerar_curadoria.py` também o pula no banco temporário). Material: documentos da SEC (20-F e 6-K de Santander Brasil, Itaú Unibanco, Bradesco e Gerdau) e release/relatório da Caixa, lidos pelo WebFetch; nem Folha nem Wikipédia. Base: lucro líquido em R$ pela legislação societária, valor do balanço divulgado na época (regra R7, `regras-fontes.json`: para banco a legislação societária é o BR GAAP/COSIF, o lucro de manchete do balanço, e o IFRS dos 20-F é sempre contexto; para não financeiras vale o IFRS a partir de 2010); reapresentações e 'gerencial' só como contexto. Santander 2010-2011 ficam em IFRS (BR GAAP da época não localizado). A cobertura dos anos não muda.

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 2008 | `caixa` | só fonte | https://www.caixa.gov.br/Downloads/caixa-demonstrativo-financeiro/ra2008.pdf |
| 2009 | `gerdau` | **inserida** (1.122) | https://www.sec.gov/Archives/edgar/data/0001073404/000110465910032711/a10-11270_120f.htm |
| 2009 | `santander-brasil` | obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281411000268/bsbrdfbrgaap4q10_6k.htm |
| 2010 | `santander-brasil` | obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281411000268/bsbrdfbrgaap4q10_6k.htm |
| 2011 | `bradesco` | obs | https://www.sec.gov/Archives/edgar/data/0001160330/000129281412000247/bbdbook4q11_6k.htm |
| 2011 | `itau-unibanco` | obs | https://www.sec.gov/Archives/edgar/data/1132597/000094787112000198/ss139116_ex9901.htm |
| 2011 | `santander-brasil` | obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281412000173/bsbrdfbrgaap4q11_6k.htm |
| 2012 | `caixa` | só fonte | https://www.caixa.gov.br/Downloads/caixa-demonstrativo-financeiro/PressRelease2012.pdf |
| 2022 | `santander-brasil` | lucro_brl_bi 14.287 -> 12.57; obs | https://www.sec.gov/Archives/edgar/data/1471055/000147105523000001/EDGAR_BRGAAP_4T22.htm |

Posições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):

- 2009: `eletrobras` 15 -> 16, `telemar` 16 -> 17
- 2022: `itausa` 11 -> 10, `santander-brasil` 10 -> 11

17 ligações novas em `ranking_evidencia` (10 evidências novas). Registro no arquivo: 5 blocos `nao_aplicados`. Lacunas: (1) Santander Brasil 2009: o valor da linha segue o 1,805 derivado de US$ (Economática x câmbio): o 20-F de 2009 traz só o IFRS em R$ (5,508, agora `contexto`), e o BR GAAP em R$ de 2009 não foi localizado (a tabela em Brazilian GAAP do item 3.A cobre 2006 e 2005; o resto do 20-F não trouxe a reconciliação nos trechos lidos). O 1,805 é provavelmente baixo demais (a Folha de 2011 implica cerca de R$ 5,5 bi) e a linha continua `derivado`. (2) Santander Brasil 2010 e 2011 (7,383 e 7,756): base IFRS (20-F de 2011); o BR GAAP/Cosif da época (após a amortização do ágio; cerca de R$ 3,5 bi em 2011, pela queda de 24% da Folha de 2013) não foi localizado, e a série fica em base diferente de 2012 (2,69, BR GAAP) e de 2022 (agora BR GAAP, 12,57). O DIEESE chamava esses números de 'LL gerencial', mas são o IFRS do 20-F. Santander 2015 (6,624) também está em base 'gerencial' no banco (IFRS 9,784 na obs) e não foi revisto. (3) Santander Brasil 2022: pela R7 o principal passa a ser o BR GAAP consolidado do 6-K do 4T22 (12,57); o IFRS atribuível do 20-F (14,287) e o gerencial (12,9) são contexto. (4) Itaú Unibanco e Bradesco 2011: ficam no BR GAAP/Cosif de manchete (14,621 e 11,028), a base da R7; o IFRS dos 20-F (Itaú 13,837 atribuível/14,610 consolidado; Bradesco 11,089) entrou como contexto. (5) Caixa 2015 (7,2): o banco tem Brasil 247 como principal; as demonstrações BRGAAP de dez/2015 (DC_BrGaap_Dez15_English.pdf), o Relatório de Gestão 2015 e o press release 1T16 existem no site da Caixa, mas o WebFetch foi recusado por robots.txt; sem fonte primária nova. (6) Cielo 2015 (3,511): a principal já é a apresentação da própria Cielo (api.mziq.com); só o `tipo` da evidência foi corrigido de `reportagem` para `relatorio` em `evidencia-correcoes.json`. A busca pelo release do 4T15 só devolveu documentos de outros períodos (4T23); nenhuma fonte acrescentada. (7) Usiminas 2009: nenhuma demonstração ou release de 2009 achado nas buscas (só materiais de 2020 e 2024 no api.mziq.com); a linha não foi inserida. O top 15 de 2009 pode ainda estar incompleto: Usiminas (lucro de 2009 possivelmente na casa de R$ 1 bi, não verificado) poderia entrar à frente da Eletrobras. (8) Eletrobras 1997, Telebras 1995, Light 1995-1997 e Banco Real 1995-1997: a busca restrita ao sec.gov não devolveu nenhum 20-F anterior a 1999; sem fonte, nenhuma linha inserida. Light não tem linhas nesses anos no banco; `real` não existe como entidade (o Banco Real é `banco-real`). (9) Embratel 2000, AmBev 2002 e 2009 e Bradesco 2009: o banco já tem 20-F/6-K da SEC como principal (documento_oficial); não foram reabertos nesta rodada (a Embratel 2000 vem do 20-F de 2003, série 1999-2003, possível reapresentação; a AmBev 2002 do 20-F de 2004). (10) Etapa 4 (conferir com release/20-F as 5 maiores de 2013-2015 que só têm imprensa) não feita: a cota de buscas foi usada nas etapas 1-3. Candidatos: Itaú Unibanco 2013 e 2014 (Wikipédia pt), Bradesco 2013 (DIEESE de 2014) e 2014 (Exame), BB 2014 (Wikipédia), BNDES 2014 (Exame), Itaú e Bradesco 2015 (Exame/Gazeta do Povo). (11) Acesso: sec.gov respondeu pelo WebFetch (diretórios Archives, documentos e índices -index.htm, de onde vêm as datas de arquivamento), mas não por curl (403 do proxy, igual a www.rad.cvm.gov.br e www.santander.com.br), e a página browse-edgar é barrada por robots.txt; a CVM não pôde ser consultada. Os trechos vêm do texto devolvido pelo WebFetch (um modelo menor lê a página): as linhas de tabela estão com as colunas separadas por ' | ' e foram reproduzidas como devolvidas. O Itaú 6-K (data 2012-02-29) é a data de arquivamento; o comunicado é de 28/2/2012.


## 28. Rodada 11: Santander em BR GAAP (2009-2011 e 2015) e fontes primárias de Itaú, Bradesco, BB e BNDES em 2013-2015

Arquivo à mão: `ranking-empresa-correcoes-r11.json` (mesmo formato das rodadas 6-10, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R11)` logo depois da 10; aceita a chave opcional `reclassificar`, que só troca o papel/nota de ligações já existentes da linha; `gerar_curadoria.py` também o pula no banco temporário). Material: 6-K da SEC (Santander, Itaú e Bradesco), Relatório Anual 2015 do BB, notícia do site do BNDES, lidos pelo WebFetch; nem Folha nem Wikipédia. Regra R7: banco em BR GAAP/COSIF (lucro de manchete); o IFRS dos 20-F, o 'gerencial' e o 'ajustado' ficam como contexto. O Santander 2009-2011 e 2015 passa do IFRS/gerencial para o BR GAAP; o Bradesco 2013 passa do Adjusted Net Income (DIEESE) para o Book Net Income. A cobertura dos anos não muda.

| ano | empresa | o que mudou | fonte principal |
|---|---|---|---|
| 2009 | `santander-brasil` | lucro_brl_bi 1.805 -> 1.806; derivado 1 -> 0; obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281411000268/bsbrdfbrgaap4q10_6k.htm |
| 2010 | `santander-brasil` | lucro_brl_bi 7.383 -> 3.863; obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281411000268/bsbrdfbrgaap4q10_6k.htm |
| 2011 | `santander-brasil` | lucro_brl_bi 7.756 -> 3.557; obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281412000173/bsbrdfbrgaap4q11_6k.htm |
| 2013 | `bradesco` | lucro_brl_bi 12.202 -> 12.011; obs | https://www.sec.gov/Archives/edgar/data/0001160330/000129281414000222/bbdbook4q13_6k.htm |
| 2013 | `itau-unibanco` | só fonte | https://www.sec.gov/Archives/edgar/data/0001132597/000094787114000185/ss207556_ex9901.htm |
| 2014 | `banco-do-brasil` | só fonte | https://api.mziq.com/mzfilemanager/v2/d/0501147c-6489-4fc5-8ac2-a39baa2721b9/0356392e-5816-866a-bc0d-e4a5b3d257de?origin=1 |
| 2014 | `bndes` | só fonte | https://bndes.gov.br/SiteBNDES/bndes/bndes_en/conteudos/noticia/BNDES-profit-rises-5.4-reaching-R$-8.59-billion-in-2014 |
| 2014 | `bradesco` | lucro_brl_bi 15.088 -> 15.089; obs | https://www.sec.gov/Archives/edgar/data/0001160330/000129281415000249/bbdbook4q14_6k.htm |
| 2014 | `itau-unibanco` | só fonte | https://www.sec.gov/Archives/edgar/data/1132597/000114420415006738/v400373_ex99-1.htm |
| 2015 | `bradesco` | lucro_brl_bi 17.18 -> 17.19; obs | https://www.sec.gov/Archives/edgar/data/0001160330/000129281416003473/bbdbook4q15_6k.htm |
| 2015 | `itau-unibanco` | lucro_brl_bi 23.35 -> 23.36; obs | https://www.sec.gov/Archives/edgar/data/0001132597/000114420416081111/v430347_ex99-1.htm |
| 2015 | `santander-brasil` | lucro_brl_bi 6.624 -> 6.998; obs | https://www.sec.gov/Archives/edgar/data/0001471055/000129281416003390/bsbrdfbrgaap4q15_6k.htm |

Posições que mudaram (`entidade`: antes -> depois):

- 2010: `itausa` 9 -> 8, `santander-brasil` 8 -> 9
- 2011: `caixa` 10 -> 9, `csn` 12 -> 11, `itausa` 9 -> 8, `santander-brasil` 8 -> 12, `telefonica-brasil` 11 -> 10

23 ligações novas em `ranking_evidencia` (10 evidências novas). Registro no arquivo: 2 blocos `nao_aplicados`. Lacunas: (1) Santander Brasil 2013 (5,744) e 2014 (5,85): fora do pedido, mas o mesmo 6-K do 4T15 mostra que o BR GAAP de 2014 é 2.161,2 (coluna 12M14 da demonstração) e que os R$ 5.850,0 mi do texto do relatório são o lucro 'excluída a amortização de ágio', uma base não contábil; a linha de 2014 (5,85) e provavelmente a de 2013 estão fora da R7 e não foram alteradas. Para a próxima rodada: 6-K do 4T13 e do 4T14 (BR GAAP). O 2,69 de 2012 confere com o 6-K do 4T12 (R$ 2.692 mi). (2) Santander Brasil 2009: o 1,806 é o comparativo de 2009 no relatório da administração do 6-K do 4T10 (arquivado em 2011-02-03), não o balanço de 2009 em si; o 6-K do 4T09 (fevereiro de 2010) não foi aberto. Em 2010, 2011 e 2015 o valor vem do relatório da administração (2010 e 2011) ou da demonstração do resultado (2015) do mesmo 6-K; nos 6-K de 2011 e 2012 a demonstração do resultado fica além dos 100.000 caracteres que o WebFetch devolve por chamada e não foi lida (nenhuma divisão controladores/não controladores conferida; o valor é o 'net income' consolidado do relatório). (3) Itaú Unibanco 2013: o principal é o Manual das Assembleias de 2014 (6-K de 2014-03-25, 'consolidated net income amounted to R$15,696 million'), com a MD&A do 4T14 (comparativo 2013) como `sustenta`; o MD&A do 4T13 (fevereiro de 2014) não foi localizado pelas buscas. O cabeçalho da tabela de destaques da MD&A diz '$ million' e o texto 'R$ million' (R$). (4) Banco do Brasil 2014 (11,246): o BB não é registrante na SEC; a fonte é o comparativo de 2014 no Relatório Anual 2015 do próprio BB (tabela 'Resultado do Período'), não o release do 4T14, que as buscas não devolveram (só matérias, tabelas do DIEESE e releases de outros períodos no api.mziq.com). O mesmo relatório traz 15.758 (2013) e 14.400 (2015), iguais aos do banco. Um mesmo Relatório Anual 2015 do BB cita 'R$ 14,1 bilhões' no Perfil e 14,4 na mensagem e na tabela; vale 14,4. (5) Itaú e Bradesco 2015 e Bradesco 2014: a imprensa da época (Exame 23,35 e 15,088; Gazeta do Povo 17,18/17,180; Infomoney 23,35) difere do balanço em R$ 10 milhões ou menos (arredondamento); o 6-K prevalece, e essas matérias ficaram `contexto`. O Itaúsa 2014 e 2015 (8,161 e 8,868) não foram revistos além da retipagem da fonte: são o consolidado/controladora do Relatório Anual 2015 da Itaúsa, holding do Itaú (dupla contagem). (6) Conferência por abertura de documento só onde o banco tinha imprensa, DIEESE ou Wikipédia: Itaú 2013-2015, Bradesco 2013-2015, BB 2014, BNDES 2014 e Itaúsa. Petrobras 2013 (6-K do 4T14, comparativo 23,57), AmBev 2013 (6-K do 4T13), AmBev 2014 (20-F) e AmBev 2015 (XBRL da SEC) já eram documento oficial da SEC e não foram reabertos; Vale 2013 (0,115) não está entre as cinco maiores. BB 2013 e 2015 já tinham relatório do próprio BB. Caixa 2013-2015 (6ª/7ª) e BNDES 2013 ficaram fora do top 5; Caixa 2015 (7,2, Brasil 247) segue sem fonte primária (robots.txt, como na rodada 10). (7) Usiminas 2009: duas buscas pelo release do 4T09 / demonstrações de 2009 só devolveram arquivos do repositório de RI (api.mziq.com) sem título, de períodos que não são 2009 (as da rodada 10 eram de 2020 e 2024), e uma matéria de 2009 do 1T no SteelOrbis (secundária); nenhum documento do 4T09 achado, a linha não foi inserida e o top 15 de 2009 pode ainda estar incompleto. (8) Acesso: a listagem de diretório da SEC (https://www.sec.gov/Archives/edgar/data/1471055/) vem em ordem decrescente e truncada em jan/2015, de modo que os 6-K foram achados por WebSearch e as datas de arquivamento conferidas nos índices -index.htm; browse-edgar, rad.cvm.gov.br e www.santander.com.br não foram tentados. Os trechos vêm do texto devolvido pelo WebFetch (um modelo menor lê a página) e foram reproduzidos como devolvidos; os valores dos 6-K de Itaú e Bradesco conferem com os comparativos dos 6-K seguintes (Itaú 2014 em duas MD&A; Bradesco 2014 e 2013 em duas tabelas). 43 chamadas web usadas.

