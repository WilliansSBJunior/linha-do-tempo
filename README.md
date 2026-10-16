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

- `index.html` é leve (menos de 60 KB): cabeçalho, menu fixo, seções e rodapé. Os dados ficam nas páginas de `paginas/`.
- Cada página de `paginas/` também abre sozinha e traz no topo o link “← Página completa”.
- `index.html#teia-3d` abre a teia já no modo 3D.
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

Rode `python -m http.server` nesta pasta e abra <http://localhost:8000/>. Abrir o `index.html` direto do disco também funciona,
mas alguns navegadores tratam cada arquivo local como origem separada.

## Conteúdo

Levantamento até 14 out 2026. No Caso Master, ninguém citado foi condenado no caso, nas fontes consultadas; cada relação traz o seu status
(documentada, sob investigação, revelada pela imprensa ou alegação), a versão de quem foi citado e as fontes.
