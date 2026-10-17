# Revisão das ressalvas das evidências adicionais

Gerado por `scripts/migrar.py` (`curadoria.relatorio_revisao_evidencias`) a partir de `data/curadoria/evento-correcoes.json` e `data/curadoria/relacao-correcoes.json`, aplicados por `curadoria.aplicar_evento_correcoes` e `curadoria.aplicar_relacao_correcoes`. Determinístico.

As ressalvas de `data/relatorio-evidencias-adicionais.md` foram decididas pelo dono do projeto; as decisões estão nos dois arquivos acima (o relatório de evidências continua sendo gerado só de `evidencias-adicionais.json`). Princípio: a descrição no banco tem de corresponder à evidência anexada; onde a fonte oficial contradiz um número ou data o banco muda; onde a fonte só não confirma um detalhe, o detalhe sai ou fica mais vago; onde a fonte é fraca mas o fato é notório, mantém-se marcado para troca de fonte.

## Contagens

| | |
|---|---:|
| eventos corrigidos | 23 |
| &nbsp;&nbsp;campo `descricao` | 21 |
| &nbsp;&nbsp;campo `titulo` | 2 |
| relações de linha do tempo corrigidas (período/descrição) | 7 |
| vínculos da teia ajustados (subtipo/rótulo/tipo) | 11 |
| &nbsp;&nbsp;`subtipo` definido | 11 |
| &nbsp;&nbsp;`rotulo` trocado | 4 |
| &nbsp;&nbsp;`tipo` trocado | 1 |
| itens mantidos com nota (relações/vínculos sem mudança) | 4 |
| ressalvas mantidas com nota, sem mudança no banco (ids de ressalva) | 37 |

Fontes fracas: as entradas marcadas `fraca` continuam marcadas para a rodada de substituição por fontes primárias; nenhuma foi removida (`data/relatorio-evidencias-adicionais.md`, seção "Fontes fracas").

## Eventos corrigidos

| evento | campo | de -> para | motivo | ressalvas |
|---|---|---|---|---|
| `ev-1995-efeito-tequila-apos-a-crise-do-peso` | descricao | os EUA coordenaram em janeiro de 1995 um pacote de US$ 50 bilhões -> os EUA e organismos internacionais montaram no início de 1995 um pacote de socorro de cerca de US$ 50 bilhões | Fontes abertas falam em ~US$ 50 bi no total, no início de 1995, não em um pacote único de janeiro. | r004 |
| `ev-1995-mercosul-vira-uniao-aduaneira` | descricao | Em 1º de janeiro de 1995 o Mercosul (Argentina, Brasil, Paraguai e Uruguai) passou a operar como união aduaneira, com tarifa externa comum. -> Em janeiro de 1995 o Mercosul (Argentina, Brasil, Paraguai e Uruguai) passou a operar como união aduaneira, com tarifa externa comum ainda sujeita a exceções. | A única fonte aberta (Câmara) dá 11/1/1995 e diz que a TEC não estava plenamente em vigor; 1º/1 não foi confirmado. | r008 |
| `ev-1995-posse-de-fernando-henrique-cardoso` | descricao | com 54,28% dos votos -> com cerca de 54,3% dos votos válidos | Fundação FHC: 54,3% dos válidos; o 54,28% vinha da Wikipédia. | r009, r010 |
| `ev-2000-argentina-em-recessao` | descricao | , e a Argentina era o segundo destino das exportações brasileiras, com 11,33% do total. -> , e a Argentina era um dos principais destinos das exportações brasileiras. | A posição de 2º destino e o 11,33% não foram verificados em nenhuma fonte aberta. | r011 |
| `ev-2000-cassacao-do-senador-luiz-estevao` | descricao | Em 28/6/2000 o Senado cassa o mandato de Luiz Estêvão por quebra de decoro parlamentar, por 52 votos a 18, -> Em junho de 2000 o Senado cassa o mandato de Luiz Estêvão por quebra de decoro parlamentar, por 52 votos a 18 (10 abstenções), | O dia 28/6 não foi confirmado; a fonte traz o placar completo. | r012 |
| `ev-2000-lei-de-responsabilidade-fiscal` | descricao | os relatores foram Pedro Novais na Câmara e Jefferson Peres no Senado. -> no Senado, Jefferson Péres foi o relator na CAE e Álvaro Dias na CCJ. | Pedro Novais como relator na Câmara não foi confirmado em nenhuma fonte; o Senado confirma Péres (CAE) e Álvaro Dias (CCJ). | r016 |
| `ev-2005-cassacoes-de-roberto-jefferson-e-jose` | descricao | e o de José Dirceu em 30/11/2005, -> e o de José Dirceu na madrugada de 1/12/2005 (sessão iniciada em 30/11), | Congresso em Foco: votação concluída logo após a meia-noite. | r020 |
| `ev-2005-katrina-e-petroleo-mais-caro` | descricao | o Brent teve média anual de US$ 54,68 em 2005, ante US$ 38,23 em 2004. -> o Brent teve média anual de US$ 54,57 em 2005, ante US$ 38,26 em 2004 (série da EIA). | Os números do banco não batem com a série anexada (EIA/FRED); a evidência manda. | r027 |
| `ev-2010-china-a-frente-do-japao-e-principal` | descricao | O PIB nominal da China (US$ 6,19 tri) ficou acima do japonês (US$ 5,81 tri) em 2010 -> O PIB nominal da China (US$ 5,88 tri, pelos dados oficiais divulgados em fevereiro de 2011) ficou acima do japonês (US$ 5,47 tri) em 2010 | Os valores do banco não têm fonte; os da evidência são os divulgados pelos dois governos. | r032 |
| `ev-2010-primeiro-resgate-da-grecia` | descricao | Em 3 de maio de 2010 -> Em 2 de maio de 2010 | O comunicado do Eurogrupo/FMI é de 2/5/2010. | r038 |
| `ev-2015-acordo-de-paris-na-cop21` | descricao | 195 países-membros da UNFCCC e a União Europeia chegaram a consenso sobre o texto do Acordo de Paris na COP21. -> as 195 Partes da UNFCCC (incluindo a União Europeia) adotaram o Acordo de Paris na COP21. | A UNFCCC conta 195 Partes já com a UE; 'consenso' não consta das fontes. | r040 |
| `ev-2015-colapso-do-preco-das-commodities` | descricao | o do minério de ferro de US$ 97,39 para US$ 56,14 por tonelada (séries do FMI). -> o do minério de ferro de US$ 96,8 para US$ 55,2 por tonelada (séries do FMI, boletim de janeiro de 2016). | Alinhado ao boletim do FMI anexado como evidência. | r041 |
| `ev-2015-manifestacoes-contra-o-governo` | descricao | reúnem centenas de milhares de pessoas contra o governo -> reúnem multidões contra o governo (cerca de 2 milhões em 15/3, 560 mil em 12/4 e 795 mil em 16/8, por estimativas das polícias militares) | A fonte dá números muito acima de 'centenas de milhares'. | r044 |
| `ev-2015-turbulencia-na-china-bolsa-e-yuan` | descricao | A bolsa de Xangai caiu de mais de 5.000 pontos em meados de junho para menos de 3.000 no fim de agosto, -> A bolsa de Xangai fechou abaixo de 3.000 pontos em 25 de agosto de 2015, | O pico acima de 5.000 em junho não foi confirmado em fonte aberta. | r048 |
| `ev-2020-china-cresce-e-compra-um-terco-das` | descricao | a China respondeu por 32,41% das exportações brasileiras. -> a China respondeu por 32,3% das exportações brasileiras. | Agência Brasil (dados do governo): 32,3%. | r051 |
| `ev-2020-guerra-de-precos-do-petroleo` | descricao | iniciada em 8 de março, -> iniciada no início de março, | O dia 8/3 não consta da fonte. | r053 |
| `ev-2020-novo-fundeb` | descricao | promulgada em 26/8/2020 após aprovação por 79 votos a zero no Senado, torna o Fundeb permanente -> promulgada em 26/8/2020, torna o Fundeb permanente (art. 212-A da Constituição) | O placar 79x0 não foi verificado; a permanência é a substância da EC 108. | r054 |
| `ev-2020-pandemia-de-covid-19` | titulo | Pandemia de covid-19 -> Pandemia de covid-19: resposta do Congresso | Dois eventos com o mesmo título e fatos distintos; títulos distintos evitam fusão indevida. | r056 |
| `ev-2020-pandemia-de-covid-19-2` | titulo | Pandemia de covid-19 -> Pandemia de covid-19: declaração da OMS e PIB mundial | Idem. | r056 |
| `ev-2020-saida-de-sergio-moro-do-governo` | descricao |  na Polícia Federal; Bolsonaro contesta a versão. ->  na Polícia Federal. | A contestação não está na fonte anexada. | r058 |
| `ev-2020-trocas-no-ministerio-da-saude` | descricao | o general Eduardo Pazuello assume a pasta em 16/5. -> o general Eduardo Pazuello assume a pasta interinamente em 15/5. | Poder360 e O Popular: 15/5, interino. | r059 |
| `ev-2025-eua-isentam-parte-dos-produtos-agricolas` | descricao | Em 14 de novembro de 2025 os EUA retiraram da tarifa produtos como café, carne bovina, frutas tropicais, cacau, bananas e laranjas, incluindo itens brasileiros. -> Em 14 de novembro de 2025 os EUA retiraram da tarifa 'recíproca' produtos agrícolas como café, carne bovina, frutas tropicais, cacau, bananas e laranjas e, em 20 de novembro, retiraram também a tarifa adicional de 40% sobre esses itens brasileiros (EO 14361). | A isenção para itens brasileiros é de 20/11 (EO 14361); 14/11 é a ordem geral. | r064, r065 |
| `ev-2025-stf-torna-bolsonaro-reu-e-o-condena` | descricao | o condena a 27 anos de prisão. -> o condena a 27 anos e 3 meses de prisão. | Pena exata conforme a fonte. | r070 |

## Relações de linha do tempo corrigidas

| relação | alvo | campo | de -> para | motivo |
|---|---|---|---|---|
| 373 `mandato:6` | Luiz Inácio Lula da Silva: Presidente da República (2023) | periodo_fim | 2025 -> 2026 | Mandato até 31/12/2026 (Agência Senado). |
| 373 `mandato:6` | Luiz Inácio Lula da Silva: Presidente da República (2023) | descricao | Presidente da República (PT), 2023 a 2025. -> Presidente da República (PT), 2023 a 2026. | Mandato até 31/12/2026 (Agência Senado). |
| 376 `mandato:9` | Michel Temer: Vice-presidente da República (2011) | periodo_fim | 2015 -> 2016 | Agência Senado: vice até 2016. |
| 376 `mandato:9` | Michel Temer: Vice-presidente da República (2011) | descricao | Vice-presidente da República (PMDB), 2011 a 2015. -> Vice-presidente da República (PMDB), 2011 a 2016 (interino na Presidência a partir de 12/5/2016). | Agência Senado: vice até 2016. |
| 378 `mandato:11` | Geraldo Alckmin: Vice-presidente da República (2023) | periodo_fim | 2025 -> 2026 | Idem. |
| 378 `mandato:11` | Geraldo Alckmin: Vice-presidente da República (2023) | descricao | Vice-presidente da República (PSB), 2023 a 2025. -> Vice-presidente da República (PSB), 2023 a 2026. | Idem. |
| 394 `mandato:27` | Hugo Motta: Presidente da Câmara dos Deputados (2025) | periodo_fim | 2025 -> 2026 | Agência Câmara: biênio 2025-2026. |
| 394 `mandato:27` | Hugo Motta: Presidente da Câmara dos Deputados (2025) | descricao | Presidente da Câmara dos Deputados (Republicanos), 2025. -> Presidente da Câmara dos Deputados (Republicanos), biênio 2025-2026. | Agência Câmara: biênio 2025-2026. |
| 730 `filiacao:geraldo-alckmin:psb:2023` | Geraldo Alckmin: Filiado ao PSB (2023) | periodo_fim | 2025 -> 2026 | Agência Senado. |
| 730 `filiacao:geraldo-alckmin:psb:2023` | Geraldo Alckmin: Filiado ao PSB (2023) | descricao | Partido registrado em 1 mandato(s) da linha do tempo (vice_presidente); PSB. O período é inferido dos mandatos, não da data de filiação. -> Partido registrado no mandato de vice-presidente (2023-2026); filiado ao PSB desde março de 2022, vindo do PSDB. | Agência Senado. |
| 743 `filiacao:jair-bolsonaro:psl:2019` | Jair Bolsonaro: Filiado ao PSL (2019) | periodo_fim | 2022 -> 2019 | A fonte só sustenta o PSL na eleição e na posse; 2019-2022 é inexato. |
| 743 `filiacao:jair-bolsonaro:psl:2019` | Jair Bolsonaro: Filiado ao PSL (2019) | descricao | Partido registrado em 1 mandato(s) da linha do tempo (presidente); PSL. O período é inferido dos mandatos, não da data de filiação. -> Eleito e empossado pelo PSL; deixou o partido em novembro de 2019. | A fonte só sustenta o PSL na eleição e na posse; 2019-2022 é inexato. |
| 769 `filiacao:luiz-inacio-lula-da-silva:pt:2023` | Luiz Inácio Lula da Silva: Filiado ao PT (2023) | periodo_fim | 2025 -> 2026 | Acompanha o mandato. |

## Vínculos da teia ajustados

| relação | alvo | campo | de -> para | motivo |
|---|---|---|---|---|
| 349 `N[128].fam_de` | Mario Umberto Degani -> Dias Toffoli | subtipo | (vazio) -> primo | Fonte: primo. |
| 350 `N[129].fam_de` | Roberta Rangel -> Dias Toffoli | subtipo | (vazio) -> ex-conjuge | Fonte: ex-esposa (divórcio em 2025). |
| 350 `N[129].fam_de` | Roberta Rangel -> Dias Toffoli | rotulo | Familiar ou próximo de -> Ex-cônjuge de | Fonte: ex-esposa (divórcio em 2025). |
| 352 `N[131].fam_de` | Bianca Medeiros -> Hugo Motta | subtipo | (vazio) -> cunhada | Fonte: cunhada (irmã da esposa). |
| 353 `N[132].fam_de` | ETC Participações -> Hugo Motta | subtipo | (vazio) -> empresa_de_familiar | Empresa controlada pela cunhada; vínculo indireto. |
| 353 `N[132].fam_de` | ETC Participações -> Hugo Motta | rotulo | Familiar ou próximo de -> Empresa de familiar de | Empresa controlada pela cunhada; vínculo indireto. |
| 354 `N[133].fam_de` | Bonnie de Bonilha -> Jaques Wagner | subtipo | (vazio) -> nora | Fonte: nora (casada com o enteado). |
| 355 `N[134].fam_de` | BN Financeira (BK Financeira) -> Jaques Wagner | subtipo | (vazio) -> empresa_de_familiar | Empresa da nora; vínculo indireto. Nome varia (BN/BK Financeira) — manter o nome com a variante entre parênteses. |
| 355 `N[134].fam_de` | BN Financeira (BK Financeira) -> Jaques Wagner | rotulo | Familiar ou próximo de -> Empresa de familiar de | Empresa da nora; vínculo indireto. Nome varia (BN/BK Financeira) — manter o nome com a variante entre parênteses. |
| 356 `N[135].fam_de` | Eduardo Sodré Martins -> Jaques Wagner | subtipo | (vazio) -> enteado | Fonte: enteado. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | subtipo | (vazio) -> empresa_atribuida | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | rotulo | Familiar ou próximo de -> Empresa atribuída pela PF a | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | tipo | familiar -> societaria | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 363 `N[142].fam_de` | Camilla Ramos -> Newton Ramos | subtipo | (vazio) -> conjuge | Fonte: esposa. |
| 364 `N[160].lig_de` | Queiroga, Vieira, Queiroz e Ramos Advocacia (QVQR) -> Newton Ramos | subtipo | escritorio_ligado -> escritorio_do_conjuge | Escritório é da esposa; rótulo 'Escritório ligado a' mantido, com subtipo que explicita o caminho. |
| 367 `N[197].fam_de` | Chiquinho Feitosa -> Gilmar Mendes | subtipo | (vazio) -> ex-cunhado | Fonte: ex-cunhado. |

## Mantidos com nota (nada mudou)

| relação | alvo | motivo |
|---|---|---|
| 365 `N[161].lig_de` | Ibaneis Advocacia -> Ibaneis Rocha: Escritório ligado a | Nome do escritório na fonte ('escritório Ibaneis Rocha') é compatível; a defesa alega afastamento desde 2018 — já na descrição. |
| 366 `N[163].lig_de` | Lewandowski Advocacia -> Ricardo Lewandowski: Escritório ligado a | Nome não conferido literalmente, mas o vínculo (contrato de R$ 5 mi) está na fonte. |
| 407 `mandato:40` | Davi Alcolumbre: Presidente do Senado Federal | Biênio 2025-2027 não confirmado nas páginas abertas; fica 2025 até nova fonte. |
| 749 `filiacao:jose-alencar:pl:2003` | José Alencar: Filiado ao PL | Fonte só diz PL na eleição e PRB em 2011; a data da troca (2005) não foi verificada. Fica como está, com nota. |

## Ressalvas mantidas sem mudança no banco

37 ressalvas: r001, r003, r005, r006, r007, r013, r015, r019, r021, r022, r023, r025, r028, r029, r043, r046, r049, r052, r061, r062, r063, r066, r067, r068, r069, r071, r073, r076, r079, r080, r082, r084, r085, r086, r089, r090, r092.

