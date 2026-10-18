# Linha do tempo política do Brasil — site estático

Uma página única (`index.html`) com seis seções, cada uma carregada só quando chega perto da tela.
Não há build nem servidor: basta publicar esta pasta como está.

| Seção | Âncora | Página completa |
|---|---|---|
| Brasil ano a ano | `index.html#linha-do-tempo` | `paginas/brasil-ano-a-ano.html` |
| Brasil frente aos pares | `index.html#pares` | `paginas/pares.html` |
| Ritmo da violência | `index.html#violencia` | `paginas/violencia.html` |
| Do Máxima ao Master: as origens | `index.html#origens` | `paginas/origens.html` |
| Master: mercado ou máquina | `index.html#dossie` | `paginas/dossie.html` |
| Teia do Caso Master | `index.html#teia` | `paginas/teia.html` |

- `index.html` é leve (menos de 60 KB): cabeçalho, menu fixo, seções e rodapé. As páginas de `paginas/` não trazem dados embutidos: cada uma pede, uma vez, o seu arquivo de `data/` (exportado do banco por `scripts/exportar_json.py`) e, se ele faltar, mostra um aviso no lugar do conteúdo.

| Página | Arquivo de dados |
|---|---|
| `brasil-ano-a-ano.html` | `data/series.json` (indicadores, empresas, mandatos, bancadas, textos de época e os fatos de cada ano) |
| `pares.html` | `data/pares.json` |
| `violencia.html` | `data/violencia.json` (contador, recortes por grupo, taxas e marcos legais) |
| `origens.html` | `data/origens.json` |
| `dossie.html` | `data/dossie.json` |
| `teia.html` | `data/teia.json` |

- Em Brasil ano a ano, cada fato traz a etiqueta de natureza do banco (documentado, reportado, sob investigação, alegação, não classificado; a mesma legenda da teia) no painel e no destaque do ano; ao abrir o fato, o painel lista as fontes próprias (veículo, título com link, tipo, data; fracas marcadas) e, recolhidas, as fontes de contexto do ano. Parlamentares e presidentes da Câmara e do Senado com mandato conferido nas APIs/páginas oficiais trazem o link “fonte oficial”.
- Em Ritmo da violência, cada marco legal (recorte Arma de fogo) mostra a natureza e, aberto, a lista de fontes; no dossiê, cada fato da linha do tempo do BRB ganha a lista “Fontes” (recolhida) ao lado dos links de sempre.
- Wikipédia é só contexto (regra R6, `data/curadoria/regras-fontes.json`): nunca sustenta um fato ou uma ligação, não conta em "Fontes (n)" e aparece por último, apagada, como "Wikipédia (contexto)" (em Brasil ano a ano, no fim do grupo recolhido das fontes de contexto).
- Cada página de `paginas/` também abre sozinha e traz no topo o link “← Página completa”.
- `index.html#teia-3d` abre a teia já no modo 3D.
- Na teia (2D e 3D), o painel de uma ligação lista as fontes que a comprovam (veículo, título com link, etiqueta oficial/reportagem/decisão, data; fontes fracas marcadas; a Wikipédia por último, apagada), e o painel de um nome mostra quantas fontes tem cada ligação. Com um `teia.json` antigo (sem `fontes`), volta a lista simples.
- Na teia (2D e 3D), o painel de um escândalo com estimativa em R$ (`data/curadoria/entidade-valores.json`) traz, logo abaixo da descrição, o bloco “Estimativa”: o valor principal em destaque com o que ele mede, quem estima e quando, com link para a fonte e o tipo dela (fontes fracas marcadas); os demais valores em linhas menores; e, à parte, a soma dos valores citados nas ligações do nome, que não é estimativa do escândalo. Nomes sem estimativa não mostram o bloco.
- O tema (automático, claro ou escuro) é escolhido no menu e repassado às seções; sozinhas, as páginas seguem o sistema ou `?tema=claro|escuro`.
- As páginas usam fontes do Google Fonts; sem internet, caem nas fontes do sistema. Todos os links são relativos.
- `.nojekyll` (vazio) faz o GitHub Pages servir os arquivos sem processá-los.

## GitHub Pages

1. Crie um repositório e envie o conteúdo desta pasta para a raiz da branch `main` (o `index.html` e a pasta `paginas/` precisam ficar na raiz, junto com o `.nojekyll`).
2. No repositório, abra **Settings → Pages**.
3. Em **Build and deployment**, escolha **Source: Deploy from a branch**, branch **main**, pasta **/ (root)** e salve.
4. Em um ou dois minutos o site fica em `https://<usuario>.github.io/<repositorio>/`.

## Netlify Drop

1. Abra <https://app.netlify.com/drop>.
2. Arraste esta pasta inteira para a área indicada.
3. O Netlify publica na hora e mostra o endereço; crie uma conta para mantê-lo e trocar o nome.

## Testar no computador

Rode `python -m http.server` nesta pasta e abra <http://localhost:8000/>. Aberto direto do disco (`file://`), o navegador não deixa
as páginas lerem `data/*.json`: as seções aparecem com o aviso de que os dados não carregaram. Use sempre um servidor (local ou o site publicado).

## Conteúdo

Levantamento até 14 out 2026. No Caso Master, ninguém citado foi condenado no caso, nas fontes consultadas; cada relação traz o seu status
(documentada, sob investigação, revelada pela imprensa ou alegação), a versão de quem foi citado e as fontes.
