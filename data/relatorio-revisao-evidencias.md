# Revisão das ressalvas das evidências adicionais

Gerado por `scripts/migrar.py` (`curadoria.relatorio_revisao_evidencias`) a partir de `data/curadoria/evento-correcoes.json` e `data/curadoria/relacao-correcoes.json`, aplicados por `curadoria.aplicar_evento_correcoes` e `curadoria.aplicar_relacao_correcoes`. Determinístico.

As ressalvas de `data/relatorio-evidencias-adicionais.md` foram decididas pelo dono do projeto; as decisões estão nos dois arquivos acima (o relatório de evidências continua sendo gerado só de `evidencias-adicionais.json`). Princípio: a descrição no banco tem de corresponder à evidência anexada; onde a fonte oficial contradiz um número ou data o banco muda; onde a fonte só não confirma um detalhe, o detalhe sai ou fica mais vago; onde a fonte é fraca mas o fato é notório, mantém-se marcado para troca de fonte.

Os fins de mandato de Lula, Alckmin, Temer (vice) e Hugo Motta foram corrigidos na tabela `mandato` (`data/curadoria/mandato-correcoes.json`, campo `fim`); por isso as relações de mandato/filiação correspondentes já nascem com o período certo e não aparecem nas tabelas abaixo.

## Contagens

| | |
|---|---:|
| eventos corrigidos | 63 |
| &nbsp;&nbsp;campo `descricao` | 56 |
| &nbsp;&nbsp;campo `titulo` | 7 |
| &nbsp;&nbsp;da rodada 2 (eventos da linha do tempo sem fonte própria) | 24 |
| &nbsp;&nbsp;da rodada 3 (eventos que continuavam `nao_classificada`; decisões de `evidencias-rodada3.json`) | 7 |
| &nbsp;&nbsp;da rodada 4 (substituição das fontes fracas; decisões de `substituicoes-rodada4.json`) | 6 |
| &nbsp;&nbsp;eventos com correção em mais de uma rodada (aplicadas em sequência, cada `de` no texto já corrigido) | 2 |
| relações de linha do tempo corrigidas (período/descrição) | 5 |
| vínculos da teia ajustados (subtipo/rótulo/tipo) | 12 |
| &nbsp;&nbsp;`subtipo` definido | 11 |
| &nbsp;&nbsp;`rotulo` trocado | 4 |
| &nbsp;&nbsp;`tipo` trocado | 1 |
| itens mantidos com nota (relações/vínculos sem mudança) | 2 |
| ressalvas mantidas com nota, sem mudança no banco (ids de ressalva) | 37 |
| vínculos da teia com campo corrigido na rodada 4 (`rodada_campos`) | 1 |

Fontes fracas: a rodada 4 (`substituicoes-rodada4.json`) substituiu as que tinham fonte aberta melhor; ficam 4 ligações `fraca` no banco, marcadas (`data/relatorio-evidencias-adicionais.md`, seções "Fontes fracas" e "Rodada 4"). As substituídas ficam no arquivo como histórico.

## Eventos corrigidos

| evento | campo | de -> para | motivo | ressalvas |
|---|---|---|---|---|
| `ev-1995-efeito-tequila-apos-a-crise-do-peso` | descricao | os EUA coordenaram em janeiro de 1995 um pacote de US$ 50 bilhões -> os EUA e organismos internacionais montaram no início de 1995 um pacote de socorro de cerca de US$ 50 bilhões | Fontes abertas falam em ~US$ 50 bi no total, no início de 1995, não em um pacote único de janeiro. | r004 |
| `ev-1995-mercosul-vira-uniao-aduaneira` | descricao | Em 1º de janeiro de 1995 o Mercosul (Argentina, Brasil, Paraguai e Uruguai) passou a operar como união aduaneira, com tarifa externa comum. -> Em janeiro de 1995 o Mercosul (Argentina, Brasil, Paraguai e Uruguai) passou a operar como união aduaneira, com tarifa externa comum ainda sujeita a exceções. | A única fonte aberta (Câmara) dá 11/1/1995 e diz que a TEC não estava plenamente em vigor; 1º/1 não foi confirmado. | r008 |
| `ev-1995-posse-de-fernando-henrique-cardoso` | descricao | com 54,28% dos votos -> com cerca de 54,3% dos votos válidos | Fundação FHC (fonte ligada ao evento): 54,3% dos válidos; o 54,28% vinha da Wikipédia. A página oficial do TSE para 1994 só traz o resultado do exterior (55,22% ali); não há número nacional oficial aberto. Fica 54,3% (Fundação FHC). | r009, r010 |
| `ev-1996-criacao-da-cpmf` | descricao | com alíquota inicial de 0,25% -> com alíquota inicial de 0,20% | Lei 9.311, art. 7º. |  |
| `ev-1997-denuncia-de-compra-de-votos-pela` | descricao | o governo nega envolvimento e não há investigação formal. -> o governo nega envolvimento; um inquérito da PF não teve resultado, a PGR não denunciou e a CPI não foi instalada. | Poder360. |  |
| `ev-1997-pacote-de-resgate-de-us-17-bilhoes-a` | descricao | US$ 2,9 bilhões aprovados em 20 de agosto -> US$ 3,9 bilhões do FMI aprovados em 20 de agosto | Cronologia do Ministério das Finanças do Japão. |  |
| `ev-1997-queda-em-hong-kong-e-em-wall-street` | descricao | Entre 20 e 23 de outubro de 1997 o índice Hang Seng caiu 23% e, -> No fim de outubro de 1997 o índice Hang Seng sofreu quedas de dois dígitos em um único dia e, | A queda de 23% entre 20 e 23/10 não foi confirmada; as fontes dão -14% em um dia. |  |
| `ev-1998-russia-desvaloriza-o-rublo-e-declara` | descricao | desvalorizou o rublo, deixou de pagar dívida interna e declarou moratória da dívida externa, um mês depois de um pacote de US$ 22,6 bilhões do FMI e do Banco Mundial, aprovado em 13 de julho. -> desvalorizou o rublo e declarou moratória de 90 dias sobre a dívida externa, um mês depois de um pacote de US$ 22,6 bilhões do FMI e do Banco Mundial, aprovado em 20 de julho. | Fonte: aprovação em 20/7; moratória externa de 90 dias; a suspensão da dívida interna não foi verificada. |  |
| `ev-1998-tse-rejeita-candidatura-de-collor` | descricao | rejeita por unanimidade o registro -> rejeita o registro | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): a página do TSE (Resolução 20.297, de 12/8/1998) não informa se a decisão foi unânime; o detalhe sai. |  |
| `ev-2000-argentina-em-recessao` | descricao | , e a Argentina era o segundo destino das exportações brasileiras, com 11,33% do total. -> , e a Argentina era um dos principais destinos das exportações brasileiras. | A posição de 2º destino e o 11,33% não foram verificados em nenhuma fonte aberta. | r011 |
| `ev-2000-cassacao-do-senador-luiz-estevao` | descricao | Em 28/6/2000 o Senado cassa o mandato de Luiz Estêvão por quebra de decoro parlamentar, por 52 votos a 18, -> Em junho de 2000 o Senado cassa o mandato de Luiz Estêvão por quebra de decoro parlamentar, por 52 votos a 18 (10 abstenções), | O dia 28/6 não foi confirmado; a fonte traz o placar completo. | r012 |
| `ev-2000-lei-de-responsabilidade-fiscal` | descricao | os relatores foram Pedro Novais na Câmara e Jefferson Peres no Senado. -> no Senado, Jefferson Péres foi o relator na CAE e Álvaro Dias na CCJ. | Pedro Novais como relator na Câmara não foi confirmado em nenhuma fonte; o Senado confirma Péres (CAE) e Álvaro Dias (CCJ). | r016 |
| `ev-2002-eneas-e-o-deputado-federal-mais-votado` | descricao | cerca de 1,57 milhão de votos -> cerca de 1,5 milhão de votos | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): Congresso em Foco: 'o maior número de votos da história: 1,5 milhão'; o número exato 1,57 mi não foi confirmado. A superação em 2018 fica como está (não verificada; nota na evidência). |  |
| `ev-2002-fmi-aprova-o-maior-emprestimo-da` | descricao | um stand-by de cerca de US$ 30 bilhões para o Brasil, o maior crédito do Fundo até então, com US$ 6 bilhões liberados antes da eleição de outubro. -> um stand-by de US$ 30,4 bilhões para o Brasil, o maior crédito do Fundo até então, com cerca de US$ 3 bilhões liberados de imediato e o restante condicionado a revisões. | Comunicado do FMI (PR 02/40). |  |
| `ev-2003-comeca-a-invasao-do-iraque` | descricao | US$ 28,78, ante US$ 25,12 em 2002 -> US$ 28,85, ante US$ 24,99 em 2002 | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): série anual do Brent EIA/FRED (2003 = 28,85; 2002 = 24,99). |  |
| `ev-2003-estatuto-do-desarmamento` | descricao | A Lei 10.826, publicada em 22/12/2003, -> A Lei 10.826, sancionada em 22/12/2003 e publicada no DOU em 23/12/2003, | evidencia-qualidade-revisao.json, correcoes_pendentes idx 86: a fonte anexada (Planalto, texto da Lei 10.826) traz "Brasília, 22 de dezembro de 2003" e "publicado no DOU de 23.12.2003"; a descrição dizia publicada em 22/12. |  |
| `ev-2004-eleicoes-municipais-de-2004` | descricao | PSDB 870, PFL 789 e PT 411 -> PSDB 871, PFL 789 e PT 409 | Agência Brasil, 1/11/2004. |  |
| `ev-2004-lei-das-parcerias-publico-privadas` | descricao | valor mínimo de R$ 10 milhões -> valor mínimo de R$ 20 milhões (reduzido a R$ 10 milhões pela Lei 13.529/2017) | Lei 11.079, art. 2º §4º, texto original. |  |
| `ev-2004-mercosul-e-comunidade-andina-firmam` | descricao | Em 8 de dezembro de 2004 a Comunidade Andina assinou um acordo de cooperação com o Mercosul, que levou os quatro membros plenos do bloco a se tornarem associados da CAN em julho de 2005. -> Em 18 de outubro de 2004 a Comunidade Andina e o Mercosul assinaram o Acordo de Complementação Econômica nº 59 (ACE 59); posteriormente, os membros plenos do Mercosul tornaram-se associados da CAN. | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): OEA/SICE: ACE 59 assinado em 18/10/2004 (8/12/2004 é a Declaração de Cusco). A associação em 7/2005 não foi confirmada em fonte aberta: fica vaga ('posteriormente'). |  |
| `ev-2004-petroleo-passa-de-us-50-o-barril` | descricao | superou US$ 50 o barril em outubro de 2004 -> superou US$ 50 o barril em 28 de setembro de 2004 | NPR, 28/9/2004. |  |
| `ev-2004-petroleo-passa-de-us-50-o-barril` | descricao | US$ 38,23, ante US$ 28,78 em 2003 -> US$ 38,26, ante US$ 28,85 em 2003 | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): série anual do Brent EIA/FRED (2004 = 38,26; 2003 = 28,85). |  |
| `ev-2005-cassacoes-de-roberto-jefferson-e-jose` | descricao | e o de José Dirceu em 30/11/2005, -> e o de José Dirceu na madrugada de 1/12/2005 (sessão iniciada em 30/11), | Congresso em Foco: votação concluída logo após a meia-noite. | r020 |
| `ev-2005-katrina-e-petroleo-mais-caro` | descricao | o Brent teve média anual de US$ 54,68 em 2005, ante US$ 38,23 em 2004. -> o Brent teve média anual de US$ 54,57 em 2005, ante US$ 38,26 em 2004 (série da EIA). | Os números do banco não batem com a série anexada (EIA/FRED); a evidência manda. | r027 |
| `ev-2007-corrida-ao-northern-rock-no-reino-unido` | descricao | a primeira grande corrida bancária britânica em 150 anos. -> a primeira grande corrida bancária britânica desde 1866. | Relatório do Treasury Committee (Câmara dos Comuns). |  |
| `ev-2008-eleicoes-municipais-de-2008` | descricao | o PMDB elege o maior número de prefeitos (1.202), seguido por PSDB (791) e PT (557). -> o PMDB elege o maior número de prefeitos (1.193 já no 1º turno), seguido por PSDB (778) e PT (545). | Congresso em Foco, 7/10/2008; os totais finais não foram verificados. |  |
| `ev-2008-petroleo-bate-recorde-e-despenca` | descricao | O petróleo chegou a US$ 147,27 o barril em 11 de julho de 2008 e caiu para cerca de US$ 32 em dezembro, com a recessão global. -> O petróleo WTI chegou a US$ 147,27 o barril em 11 de julho de 2008 (Brent a 147,50) e desabou no fim do ano, com a recessão global. | Fonte identifica o contrato; a queda a US$ 32 não foi verificada. |  |
| `ev-2009-crise-dos-atos-secretos-no-senado` | descricao | e as 11 representações apresentadas contra Sarney -> e as representações apresentadas contra Sarney | O total de 11 não foi confirmado. |  |
| `ev-2009-grecia-revela-deficit-de-12-7-do-pib` | descricao | revisou a previsão do déficit de 6% a 8% para 12,7% do PIB, -> revisou o déficit de 2009 para cerca de 12,5% do PIB, mais que o triplo dos 3,7% projetados pelo governo anterior, | ESM (Safeguarding the euro). |  |
| `ev-2009-grecia-revela-deficit-de-12-7-do-pib` | titulo | Grécia revela déficit de 12,7% do PIB -> Grécia revela déficit de cerca de 12,5% do PIB | ESM (Safeguarding the euro). |  |
| `ev-2010-china-a-frente-do-japao-e-principal` | descricao | O PIB nominal da China (US$ 6,19 tri) ficou acima do japonês (US$ 5,81 tri) em 2010 -> O PIB nominal da China (US$ 5,88 tri, pelos dados oficiais divulgados em fevereiro de 2011) ficou acima do japonês (US$ 5,47 tri) em 2010 | Os valores do banco não têm fonte; os da evidência são os divulgados pelos dois governos. | r032 |
| `ev-2010-primeiro-resgate-da-grecia` | descricao | Em 3 de maio de 2010 -> Em 2 de maio de 2010 | O comunicado do Eurogrupo/FMI é de 2/5/2010. | r038 |
| `ev-2011-guerra-na-libia-e-brent-a-us-111-54` | descricao | US$ 111,54, ante US$ 79,81 em 2010 -> US$ 111,26, ante US$ 79,61 em 2010 | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): série anual do Brent EIA/FRED (2011 = 111,26; 2010 = 79,61). |  |
| `ev-2011-guerra-na-libia-e-brent-a-us-111-54` | titulo | US$ 111,54 -> US$ 111,26 | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): série anual do Brent EIA/FRED (2011 = 111,26). |  |
| `ev-2012-rio-20-reune-88-chefes-de-estado-e-de` | descricao | cerca de 45,4 mil participantes credenciados -> cerca de 46 mil participantes | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): ONU (press.un.org, ENV/DEV/1310): 'total participation at close to 46,000'. Fonte oficial. |  |
| `ev-2012-rio-20-reune-88-chefes-de-estado-e-de` | titulo | reúne 88 chefes -> reúne mais de 100 chefes | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): ONU (press.un.org, ENV/DEV/1310): 'over 100 Heads of State and Government'. Fonte oficial. |  |
| `ev-2013-camara-mantem-o-mandato-de-natan-donadon` | descricao | em voto secreto em 28-29/8 -> em voto secreto em 28/8 | Agência Câmara. |  |
| `ev-2013-governo-lanca-o-programa-mais-medicos` | descricao | com meta de 15 mil profissionais. -> com estimativa inicial de 10 mil vagas. | A meta de 15 mil só aparece na Wikipédia; a fonte da época fala em 10 mil. |  |
| `ev-2014-argentina-entra-em-default-seletivo` | descricao | que detinham cerca de US$ 4 bilhões em títulos. -> com sentença de cerca de US$ 1,33 bilhão. | La República. |  |
| `ev-2014-inicio-da-operacao-lava-jato` | descricao | , que investiga o doleiro Alberto Youssef e o executivo da Petrobras Paulo Roberto Costa em esquema -> , com a prisão do doleiro Alberto Youssef; o ex-diretor da Petrobras Paulo Roberto Costa é preso em 20/3, em esquema | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): Agência Brasil (20/3/2014): Paulo Roberto Costa foi preso em 20/3, depois da fase de 17/3. |  |
| `ev-2015-acordo-de-paris-na-cop21` | descricao | 195 países-membros da UNFCCC e a União Europeia chegaram a consenso sobre o texto do Acordo de Paris na COP21. -> as 195 Partes da UNFCCC (incluindo a União Europeia) adotaram o Acordo de Paris na COP21. | A UNFCCC conta 195 Partes já com a UE; 'consenso' não consta das fontes. | r040 |
| `ev-2015-colapso-do-preco-das-commodities` | descricao | o do minério de ferro de US$ 97,39 para US$ 56,14 por tonelada (séries do FMI). -> o do minério de ferro de US$ 96,8 para US$ 55,2 por tonelada (séries do FMI, boletim de janeiro de 2016). | Alinhado ao boletim do FMI anexado como evidência. | r041 |
| `ev-2015-manifestacoes-contra-o-governo` | descricao | reúnem centenas de milhares de pessoas contra o governo -> reúnem multidões contra o governo (cerca de 2 milhões em 15/3, 560 mil em 12/4 e 795 mil em 16/8, por estimativas das polícias militares) | A fonte dá números muito acima de 'centenas de milhares'. | r044 |
| `ev-2015-turbulencia-na-china-bolsa-e-yuan` | descricao | A bolsa de Xangai caiu de mais de 5.000 pontos em meados de junho para menos de 3.000 no fim de agosto, -> A bolsa de Xangai fechou abaixo de 3.000 pontos em 25 de agosto de 2015, | O pico acima de 5.000 em junho não foi confirmado em fonte aberta. | r048 |
| `ev-2016-opep-faz-seu-primeiro-corte-de-producao` | descricao | Rússia e outros dez produtores -> Rússia e outros onze produtores | Exame, 10/12/2016: 12 produtores de fora da Opep. |  |
| `ev-2016-opep-faz-seu-primeiro-corte-de-producao` | descricao | média de US$ 45,08 -> média de US$ 43,64 | Rodada 4 (substituicoes-rodada4.json, decisoes.correcoes): série anual do Brent EIA/FRED (2016 = 43,64). |  |
| `ev-2017-brent-sobe-para-us-54-89-de-media-com` | descricao | média de US$ 54,89 por barril, ante US$ 45,08 em 2016, segundo o FMI. -> média de US$ 54,13 por barril, ante US$ 43,64 em 2016, segundo a série da EIA. | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): alinhado à série anexada (EIA, Brent spot: 2017 = 54,13; 2016 = 43,64); a fonte citada passa de FMI a EIA. |  |
| `ev-2017-brent-sobe-para-us-54-89-de-media-com` | titulo | US$ 54,89 -> US$ 54,13 | Rodada 3 (evidencias-rodada3.json, decisoes.correcoes): alinhado à série anexada (EIA, Brent spot, média anual 2017 = 54,13), como já feito para 2005. |  |
| `ev-2017-mercosul-suspende-a-venezuela-por-tempo` | descricao | aplicada em 1º de dezembro de 2016 -> aplicada em dezembro de 2016 | O dia 1º não consta da fonte. |  |
| `ev-2018-bolsonaro-e-eleito-presidente` | descricao | 55,13% (57,8 milhões de votos) -> 55,13% (cerca de 57,7 milhões de votos) | evidencia-qualidade-revisao.json, correcoes_pendentes idx 148: a fonte anexada (IstoÉ, 29/10/2018, totalização do TSE) diz "55,13% dos votos válidos, o equivalente a 57,7 milhões de votos"; Haddad 44,87% e 47 milhões, como já está. O 1º turno (46,03% x 29,28%) segue sem verificação nesta fonte (nota mantida). |  |
| `ev-2019-queimadas-na-amazonia-chegam-a-agenda-do` | descricao | 77% mais focos de incêndio -> 78,6% mais focos de incêndio na Amazônia | Aos Fatos, com dados do Inpe. |  |
| `ev-2020-china-cresce-e-compra-um-terco-das` | descricao | a China respondeu por 32,41% das exportações brasileiras. -> a China respondeu por 32,3% das exportações brasileiras. | Agência Brasil (dados do governo): 32,3%. | r051 |
| `ev-2020-guerra-de-precos-do-petroleo` | descricao | iniciada em 8 de março, -> iniciada no início de março, | O dia 8/3 não consta da fonte. | r053 |
| `ev-2020-novo-fundeb` | descricao | promulgada em 26/8/2020 após aprovação por 79 votos a zero no Senado, torna o Fundeb permanente -> promulgada em 26/8/2020, torna o Fundeb permanente (art. 212-A da Constituição) | O placar 79x0 não foi verificado; a permanência é a substância da EC 108. | r054 |
| `ev-2020-pandemia-de-covid-19` | titulo | Pandemia de covid-19 -> Pandemia de covid-19: resposta do Congresso | Dois eventos com o mesmo título e fatos distintos; títulos distintos evitam fusão indevida. | r056 |
| `ev-2020-pandemia-de-covid-19-2` | titulo | Pandemia de covid-19 -> Pandemia de covid-19: declaração da OMS e PIB mundial | Idem. | r056 |
| `ev-2020-saida-de-sergio-moro-do-governo` | descricao |  na Polícia Federal; Bolsonaro contesta a versão. ->  na Polícia Federal. | A contestação não está na fonte anexada. | r058 |
| `ev-2020-trocas-no-ministerio-da-saude` | descricao | o general Eduardo Pazuello assume a pasta em 16/5. -> o general Eduardo Pazuello assume a pasta interinamente em 15/5. | Poder360 e O Popular: 15/5, interino. | r059 |
| `ev-2022-acordo-de-graos-do-mar-negro` | descricao | cerca de 33 milhões de toneladas -> mais de 32 milhões de toneladas | DevelopmentAid/ONU. |  |
| `ev-2022-stf-condena-o-deputado-daniel-silveira` | descricao | concede-lhe indulto -> concede-lhe graça constitucional (perdão individual) | A fonte (Poder360) chama o ato de graça constitucional, não de indulto; aplicada porque "indulto" ocorre exatamente uma vez na descrição (evento localizado pelo título, o id sugerido no pedido não existe). |  |
| `ev-2022-stf-condena-o-deputado-daniel-silveira` | titulo | Bolsonaro o indulta -> Bolsonaro lhe concede graça | Alinha o título à descrição já corrigida (graça constitucional, perdão individual, e não indulto), como diz a fonte (Poder360). |  |
| `ev-2023-milei-e-eleito-e-o-peso-argentino-e` | descricao | em 12 de dezembro o câmbio oficial passou de 366,5 para 800 pesos por dólar, desvalorização de 54%. -> em 12 de dezembro o governo anunciou a desvalorização do câmbio oficial, de 366,5 para cerca de 800 pesos por dólar (54%), em vigor no dia seguinte. | InfoMoney: anúncio em 12/12, abertura a ~801 em 13/12. |  |
| `ev-2025-eua-isentam-parte-dos-produtos-agricolas` | descricao | Em 14 de novembro de 2025 os EUA retiraram da tarifa produtos como café, carne bovina, frutas tropicais, cacau, bananas e laranjas, incluindo itens brasileiros. -> Em 14 de novembro de 2025 os EUA retiraram da tarifa 'recíproca' produtos agrícolas como café, carne bovina, frutas tropicais, cacau, bananas e laranjas e, em 20 de novembro, retiraram também a tarifa adicional de 40% sobre esses itens brasileiros (EO 14361). | A isenção para itens brasileiros é de 20/11 (EO 14361); 14/11 é a ordem geral. | r064, r065 |
| `ev-2025-stf-torna-bolsonaro-reu-e-o-condena` | descricao | o condena a 27 anos de prisão. -> o condena a 27 anos e 3 meses de prisão. | Pena exata conforme a fonte. | r070 |

## Relações de linha do tempo corrigidas

| relação | alvo | campo | de -> para | motivo |
|---|---|---|---|---|
| 376 `mandato:9` | Michel Temer: Vice-presidente da República (2011) | descricao | Vice-presidente da República (PMDB), 2011 a 2016. -> Vice-presidente da República (PMDB), 2011 a 2016 (interino na Presidência a partir de 12/5/2016). | Agência Senado: vice até 2016. |
| 394 `mandato:27` | Hugo Motta: Presidente da Câmara dos Deputados (2025) | descricao | Presidente da Câmara dos Deputados (Republicanos), 2025 a 2026. -> Presidente da Câmara dos Deputados (Republicanos), biênio 2025-2026. | Agência Câmara: biênio 2025-2026. |
| 730 `filiacao:geraldo-alckmin:psb:2023` | Geraldo Alckmin: Filiado ao PSB (2023) | descricao | Partido registrado em 1 mandato(s) da linha do tempo (vice_presidente); PSB. O período é inferido dos mandatos, não da data de filiação. -> Partido registrado no mandato de vice-presidente (2023-2026); filiado ao PSB desde março de 2022, vindo do PSDB. | Agência Senado. |
| 743 `filiacao:jair-bolsonaro:psl:2019` | Jair Bolsonaro: Filiado ao PSL (2019) | periodo_fim | 2022 -> 2019 | A fonte só sustenta o PSL na eleição e na posse; 2019-2022 é inexato. |
| 743 `filiacao:jair-bolsonaro:psl:2019` | Jair Bolsonaro: Filiado ao PSL (2019) | descricao | Partido registrado em 1 mandato(s) da linha do tempo (presidente); PSL. O período é inferido dos mandatos, não da data de filiação. -> Eleito e empossado pelo PSL; deixou o partido em novembro de 2019. | A fonte só sustenta o PSL na eleição e na posse; 2019-2022 é inexato. |
| 749 `filiacao:jose-alencar:pl:2003` | José Alencar: Filiado ao PL (2003) | periodo_fim | 2010 -> 2005 | Congresso em Foco: Alencar saiu do PL no auge do mensalão e se filiou ao PMR (depois PRB) em 29/9/2005; o mandato (partido PL, 2003-2010) não muda. |
| 749 `filiacao:jose-alencar:pl:2003` | José Alencar: Filiado ao PL (2003) | descricao | Partido registrado em 1 mandato(s) da linha do tempo (vice_presidente); PL. O período é inferido dos mandatos, não da data de filiação. -> Eleito e empossado vice-presidente pelo PL (2003); deixou o PL em setembro de 2005 e filiou-se ao PMR, depois PRB. | Congresso em Foco: Alencar saiu do PL no auge do mensalão e se filiou ao PMR (depois PRB) em 29/9/2005; o mandato (partido PL, 2003-2010) não muda. |

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
| 355 `N[134].fam_de` | BN Financeira (BK Financeira) -> Jaques Wagner | subtipo | (vazio) -> empresa_de_familiar | Empresa da nora; vínculo indireto. Nome varia (BN/BK Financeira) — manter o nome com a variante entre parênteses. Descrição: Metrópoles (18/3/2026) escreve BK Financeira; a matéria de 18/6 escreve BN Financeira. Fonte da descrição: https://www.metropoles.com/colunas/milena-teixeira/master-pagou-r-11-milhoes-a-empresa-de-nora-de-jaques-wagner |
| 355 `N[134].fam_de` | BN Financeira (BK Financeira) -> Jaques Wagner | rotulo | Familiar ou próximo de -> Empresa de familiar de | Empresa da nora; vínculo indireto. Nome varia (BN/BK Financeira) — manter o nome com a variante entre parênteses. Descrição: Metrópoles (18/3/2026) escreve BK Financeira; a matéria de 18/6 escreve BN Financeira. Fonte da descrição: https://www.metropoles.com/colunas/milena-teixeira/master-pagou-r-11-milhoes-a-empresa-de-nora-de-jaques-wagner |
| 355 `N[134].fam_de` | BN Financeira (BK Financeira) -> Jaques Wagner | descricao | Empresa da qual a nora de Jaques Wagner, Bonnie Bonilha, é sócia; recebeu pagamentos do Banco Master segundo a imprensa. -> Empresa da qual a nora de Jaques Wagner, Bonnie Bonilha, é sócia; recebeu pagamentos do Banco Master segundo a imprensa. A grafia "BK Financeira" é a das matérias de março; "BN Financeira", a de junho. | Empresa da nora; vínculo indireto. Nome varia (BN/BK Financeira) — manter o nome com a variante entre parênteses. Descrição: Metrópoles (18/3/2026) escreve BK Financeira; a matéria de 18/6 escreve BN Financeira. Fonte da descrição: https://www.metropoles.com/colunas/milena-teixeira/master-pagou-r-11-milhoes-a-empresa-de-nora-de-jaques-wagner |
| 356 `N[135].fam_de` | Eduardo Sodré Martins -> Jaques Wagner | subtipo | (vazio) -> enteado | Fonte: enteado. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | subtipo | (vazio) -> empresa_atribuida | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | rotulo | Familiar ou próximo de -> Empresa atribuída pela PF a | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 358 `N[137].fam_de` | CNLF Empreendimentos Imobiliários -> Ciro Nogueira | tipo | familiar -> societaria | Não é vínculo familiar: a PF atribui a empresa ao senador; o irmão a administra formalmente. |
| 363 `N[142].fam_de` | Camilla Ramos -> Newton Ramos | subtipo | (vazio) -> conjuge | Fonte: esposa. |
| 364 `N[160].lig_de` | Queiroga, Vieira, Queiroz e Ramos Advocacia (QVQR) -> Newton Ramos | subtipo | escritorio_ligado -> escritorio_do_conjuge | Escritório é da esposa; rótulo 'Escritório ligado a' mantido, com subtipo que explicita o caminho. |
| 366 `N[163].lig_de` | Lewandowski Advocacia -> Ricardo Lewandowski | descricao | Escritório de Lewandowski que recebeu R$ 5 milhões do Banco Master, inclusive com ele já como ministro; depois representado pelo filho. -> Escritório de Lewandowski que recebeu R$ 6,5 milhões brutos do Banco Master, dos quais R$ 5,25 milhões depois de ele assumir o Ministério da Justiça, em janeiro de 2024; depois representado pelo filho. | Metrópoles (26/1/2026): total bruto de R$ 6,5 mi, R$ 5,25 mi pagos após ele virar ministro (jan/2024). |
| 367 `N[197].fam_de` | Chiquinho Feitosa -> Gilmar Mendes | subtipo | (vazio) -> ex-cunhado | Fonte: ex-cunhado. Descrição: rodada 4 (substituicoes-rodada4.json, decisoes.correcoes), Poder360: irmão da ex-mulher do ministro; R$ 500 mil mensais sem confirmação documental. |
| 367 `N[197].fam_de` | Chiquinho Feitosa -> Gilmar Mendes | descricao | Ex-cunhado do ministro Gilmar Mendes; contratado por empresa ligada a Vorcaro por R$ 500 mil mensais. -> Irmão da ex-mulher do ministro Gilmar Mendes (ex-cunhado); prestou serviços a empresa ligada a Vorcaro — o valor de R$ 500 mil mensais citado por uma fonte não tem confirmação documental. | Fonte: ex-cunhado. Descrição: rodada 4 (substituicoes-rodada4.json, decisoes.correcoes), Poder360: irmão da ex-mulher do ministro; R$ 500 mil mensais sem confirmação documental. |

## Mantidos com nota (nada mudou)

| relação | alvo | motivo |
|---|---|---|
| 365 `N[161].lig_de` | Ibaneis Advocacia -> Ibaneis Rocha: Escritório ligado a | Nome do escritório na fonte ('escritório Ibaneis Rocha') é compatível; a defesa alega afastamento desde 2018 — já na descrição. |
| 407 `mandato:40` | Davi Alcolumbre: Presidente do Senado Federal | Biênio 2025-2027 não confirmado nas páginas abertas; fica 2025 até nova fonte. |

## Ressalvas mantidas sem mudança no banco

37 ressalvas: r001, r003, r005, r006, r007, r013, r015, r019, r021, r022, r023, r025, r028, r029, r043, r046, r049, r052, r061, r062, r063, r066, r067, r068, r069, r071, r073, r076, r079, r080, r082, r084, r085, r086, r089, r090, r092.

