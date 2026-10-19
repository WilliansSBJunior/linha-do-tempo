# Imagens das entidades da Teia

`manifest.json` classifica as 198 entidades de `data/teia.json`. O workflow `.github/workflows/imagens.yml` roda `scripts/baixar_imagens.py`, que baixa só os itens com `status: "ok"`, recorta 256x256 (centro) e salva JPEG q85 em `data/imagens/<id>.jpg`. O item passa a `baixado` (ou `erro`, com a mensagem).

## Regras

- Pessoas públicas (parlamentares, ministros, governadores, procuradores, presidentes de órgãos): só foto oficial de fonte aberta (Dados Abertos da Câmara e do Senado, Agência Brasil/EBC CC BY 3.0 BR, Wikimedia Commons com licença livre, portal do STF). Sem fonte confirmada, `pendente`.
- Pessoas privadas (familiares, sócios, pastores, advogados, jornalistas, influenciadores, operadores): nunca foto. `sem_foto`. Na dúvida, privada.
- Logos e brasões (empresas, partidos, igrejas, fundos, bancos, órgãos): nunca baixados automaticamente. `pendente_usuario`, com `sugestao_origem`.
- Operações policiais, CPIs, organizações criminosas, grupos genéricos: `simbolo` (ícone desenhado pela página).

## Status

| status | significado |
|---|---|
| ok | URL confirmada, pronta para o workflow baixar |
| baixado / erro | escrito pelo script |
| pendente | pessoa pública sem foto oficial aberta confirmada |
| pendente_usuario | logo/brasão que o usuário providencia |
| sem_foto | pessoa privada |
| simbolo | ícone desenhado, sem download |

## Como acrescentar um logo

1. Verifique a licença/permissão de uso.
2. Salve o arquivo em `data/imagens/<id>.png` (ou `.svg`/`.jpg`).
3. No manifesto, troque o item para:
   `{"tipo": "logo", "status": "baixado", "arquivo": "data/imagens/<id>.png", "origem": "...", "licenca": "...", "autor": "", "pagina": "<url>"}`
4. O workflow só dispara com mudança no manifesto, e só processa `ok`; seu item `baixado` fica como está.

Para empresas-veículo, fundos e escritórios sem logo, pode marcar `{"tipo": "simbolo", "status": "simbolo"}`.

Para uma foto nova de pessoa pública: preencha `url`, `origem`, `licenca`, `autor`, `pagina` e mude para `status: "ok"`; o workflow baixa ao receber o push.

## Pendências do usuário

Veja `status` em `manifest.json`. Resumo (91 logos, 28 fotos):

- Fotos de pessoas públicas (`pendente`, 28): Ibaneis, Cláudio Castro, Tarcísio, Lula, Mantega, Meirelles, Lewandowski, Antônio Rueda, os 8 ministros do STF (Moraes, Toffoli, Mendonça, Gilmar, Fachin, Dino, Nunes Marques, Fux), Gonet, Galípolo, Campos Neto, Newton Ramos, Benedito Gonçalves, Ronaldo Bento, Wajngarten, Paulo Henrique Costa, Stefanutto, Jocildo Lemos, Paulo Sérgio Neves de Souza, Belline Santana.
- Logos (`pendente_usuario`, 91): órgãos e brasões (STF, MPF, BCB, CVM, TCU, PF, INSS, CNJ, AGU, TRF-1, FGC, BRB, Ministério da Previdência, Governo do DF, Gaeco/MP-SP, Rioprevidência, Amprev, Amazonprev, AparecidaPrev, RPPS), partido (Partido Novo MG, logomarcas no TSE), bancos e empresas (Banco Master, XP, BTG, Easynvest, Máxima, Letsbank, Pleno, Will, Reag e fundos, usinas, escritórios, mídia, Lagoinha). Muitas empresas-veículo, fundos e escritórios não têm logo: marque `simbolo`.
