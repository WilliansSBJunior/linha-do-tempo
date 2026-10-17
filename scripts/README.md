# scripts/

Python 3 padrão (só stdlib; SQLite >= 3.37 com FTS5). Nenhuma dependência extra. Rode a partir da raiz do repo.

| Script | O que faz |
|---|---|
| `migrar.py` | Recria `data/linha-do-tempo.sqlite` a partir de `data/raw/` (confere `hashes.txt`), gera `data/dump.sql` e `data/relatorio-migracao.md`. Determinístico. |
| `validar.py [--db X]` | Integridade, contagens, órfãos e round-trip contra `data/raw/dados-caso-master-v2.json`; tema (toda relação/evento tem tema, regras de origem/canal valem em 100%, exceções aplicadas, toda entidade tem tema), fonte (URL -> evidência, `hash_texto`, corte só em vídeo, view `video`; fonte sem trecho é aviso) e teia <-> timeline (relações de mandato/filiação, fusões nos dois temas). Sai com código 1 em qualquer falha. |
| `exportar_json.py [--db X]` | Só lê o banco: escreve `data/{entities,teia,origens,series,mapa_indices,dossie,pares,temas}.json` e regenera `data/dump.sql`. Campos aditivos: `tema` em cada relação/EV/PREC de `teia.json` e EV de `origens.json`, `temas` em cada entidade de `entities.json`; `temas.json` traz contagens e a pertinência (relações por id, eventos por id, entidades pela view). `dossie.json` e `pares.json` têm o mesmo conteúdo do JSON embutido nas páginas (comparados com `data/raw/` pelo `validar.py`). |
| `importar.py [--db X] [--force]` | Reconstrói o sqlite a partir de `data/dump.sql` (é o que se faz depois de um `git clone`). |
| `extrair_violencia.py` | Uma vez só: extrai os literais JS de `paginas/violencia.html` (via Node) para `data/raw/violencia.json`. |
| `schema.sql` | DDL (desvios da proposta marcados `-- DESVIO:`). Modelo v2: `tema`/`relacao_tema`/`evento_tema`, view `v_entidade_tema`, `fonte` (+ view `video` de compatibilidade, `trecho.fonte_id`, triggers de corte/tempo). |
| `slug.py` | `slugify`, `SLUG_FIXO`, `alias_norm`, regra de nome base. |
| `fusoes.json` | Fusões de entidades aprovadas (`[{"de": "slug-velho", "para": "slug-novo"}]`); vazio por ora. |
| `comum.py` | Caminhos, normalização de URL, dump determinístico, FTS. |
| `curadoria.py` | Aplica `data/curadoria/*.json` depois da carga bruta (fusões, natureza, fontes da timeline, ligações evento-entidade, complementos, **relações de mandato/filiação, temas**) e contém as regras que geram parte deles; `inferir_temas_relacao` também é usado pelo MCP. |
| `gerar_curadoria.py [--so ...]` | Regenera os JSON derivados por regra (`eventos-natureza`, `brasil-fontes`, `brasil-complementos`, `evento-entidade-auto`) a partir de um banco temporário. Determinístico. |
| `dossie_rel.py` | Carga relacional do dossiê (`dossie_par`, `previdencia_ente`, `pagamento`, `indicio_maquina`, `limite`) e de `pares.foruns` (`forum`). |

Fluxo normal:

```
python3 scripts/migrar.py && python3 scripts/validar.py && python3 scripts/exportar_json.py && python3 scripts/validar.py
python3 scripts/importar.py --force   # reconstrói o sqlite a partir do dump
python3 scripts/gerar_curadoria.py    # só quando mudar uma regra ou um arquivo escrito à mão em data/curadoria/ que alimente as regras
```

## data/curadoria/

Princípio: `migrar.py` recria o banco do zero a partir de `data/raw/` e **depois** aplica estes arquivos JSON (versionados e legíveis). Toda correção editorial entra aqui; ninguém edita o banco à mão. Dois tipos:

| Arquivo | Origem | O que faz |
|---|---|---|
| `eventos-fusoes.json` | à mão | `[{"manter": id, "fundir": [ids], "motivo": "..."}]`: funde eventos quase-duplicados (mesma data, mesmo fato). O mantido recebe a união de fontes e entidades, `peso` máximo e a natureza mais forte; os ids fundidos viram `evento_alias` (com `original_json`). Mesmo grupo = mesma `data`. |
| `eventos-candidatos.md` | à mão | Pares duvidosos que ficaram de fora, para decisão. |
| `dossie-entidades.json` | à mão | Vínculo texto livre do dossiê -> entidade (`mapa`, lista vazia = sem entidade), `justificativas` e `entidades_novas` (fundos de previdência sem nó). |
| `evento-entidade-regras.json` | à mão | Regras do casamento por alias (sobrenomes ambíguos, siglas, contextos barrados). |
| `eventos-natureza.json` | gerado | `[{"id", "natureza", "regra"}]` para eventos da teia sem `st`; aplicado só onde `natureza_id IS NULL`. Regras R1-R4 documentadas em `relatorio-migracao.md` (seção 10) e em `curadoria.REGRAS_NATUREZA_TEXTO`. |
| `brasil-fontes.json` | gerado | Fontes dos eventos da timeline Brasil, vindas de `data/raw/dados-brutos-31-anos.json` (URLs por bloco-ano: `contexto`; `sustenta` quando o slug da URL toca o evento). |
| `brasil-complementos.json` | gerado | `ranking_empresa.receita_brl_bi` e `mandato.periodo_texto` do bruto, só onde o mapeamento é inequívoco. |
| `evento-entidade-auto.json` | gerado | Ligações `evento_entidade` com `papel='citado'` por alias. |
| `temas.json` | à mão | Seed de `tema`, regras de atribuição a `relacao_tema`/`evento_tema` (por origem, canal, entidade, texto; `dentro_de`) e `excecoes` (falso positivo/ajuste por registro, com motivo). Aplicado por último em `migrar.py`; quem ficar sem tema vai para `a-classificar`. |
| `mandato-relacoes.json` | à mão | Rótulo por cargo, órgão de presidente/vice (`presidencia-da-republica`), mapa manual de partido e textos que não são filiação, para `gerar_relacoes_mandato` (relações `institucional` `mandato:<cargo>` e `filiacao`, `origem='linha_do_tempo'`, tema `brasil-ano-a-ano`). |

Tema, fonte e relações de mandato (modelo v2, seções 14 a 16 do `data/relatorio-migracao.md`): `temas.json` e `mandato-relacoes.json` são escritos à mão (o gerador não os toca). `data/*.json` derivam do banco: depois de qualquer escrita do MCP rode `exportar_json.py` antes de `validar.py`.

Os arquivos gerados são regenerados por `gerar_curadoria.py`; para corrigir um deles na mão, edite o JSON e **não** rode o gerador (ele sobrescreve), ou acrescente a exceção nas regras/arquivos escritos à mão. Após qualquer mudança em `data/curadoria/`: `migrar.py` -> `validar.py` -> `exportar_json.py` -> `validar.py`.

`data/raw/dados-brutos-31-anos.json` é a única adição ao raw nesta rodada (cópia exata de `projeto-json/dados-brutos-31-anos.json`, hash em `hashes.txt`).

Git versiona `data/dump.sql` e os JSONs; `data/linha-do-tempo.sqlite` fica no `.gitignore`.
Só o servidor MCP escreve no banco; estes scripts não gravam nele fora da migração (`exportar_json.py` e `validar.py` só leem).
`data/raw/` é cópia congelada dos dados de origem (não editar; `migrar.py` recusa rodar se um hash mudar).

## Decisões humanas (fila de revisão)

`migrar.py` reaplica automaticamente `data/curadoria/decisoes.jsonl` (gravado pelas ferramentas `revisar_*` do MCP e pela página local `ferramentas/revisao.html`, servida por `python3 scripts/servir_revisao.py`). Para reaplicar à mão ou num banco reconstruído por `importar.py`: `python3 scripts/aplicar_decisoes.py [--db ...]` (idempotente). Pule com `migrar.py --pular decisoes` se a função `main` for chamada com `pular=("decisoes",)`.
