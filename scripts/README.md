# scripts/

Python 3 padrão (só stdlib; SQLite >= 3.37 com FTS5). Nenhuma dependência extra. Rode a partir da raiz do repo.

| Script | O que faz |
|---|---|
| `migrar.py` | Recria `data/linha-do-tempo.sqlite` a partir de `data/raw/` (confere `hashes.txt`), gera `data/dump.sql` e `data/relatorio-migracao.md`. Determinístico. |
| `validar.py [--db X]` | Integridade, contagens, órfãos e round-trip contra `data/raw/dados-caso-master-v2.json`. Sai com código 1 em qualquer falha. |
| `exportar_json.py [--db X]` | Só lê o banco: escreve `data/{entities,teia,origens,series,mapa_indices}.json` e regenera `data/dump.sql`. |
| `importar.py [--db X] [--force]` | Reconstrói o sqlite a partir de `data/dump.sql` (é o que se faz depois de um `git clone`). |
| `extrair_violencia.py` | Uma vez só: extrai os literais JS de `paginas/violencia.html` (via Node) para `data/raw/violencia.json`. |
| `schema.sql` | DDL (desvios da proposta marcados `-- DESVIO:`). |
| `slug.py` | `slugify`, `SLUG_FIXO`, `alias_norm`, regra de nome base. |
| `fusoes.json` | Fusões de entidades aprovadas (`[{"de": "slug-velho", "para": "slug-novo"}]`); vazio por ora. |
| `comum.py` | Caminhos, normalização de URL, dump determinístico, FTS. |

Fluxo normal:

```
python3 scripts/migrar.py && python3 scripts/validar.py && python3 scripts/exportar_json.py && python3 scripts/validar.py
python3 scripts/importar.py --force   # reconstrói o sqlite a partir do dump
```

Git versiona `data/dump.sql` e os JSONs; `data/linha-do-tempo.sqlite` fica no `.gitignore`.
Só o servidor MCP escreve no banco; estes scripts não gravam nele fora da migração (`exportar_json.py` e `validar.py` só leem).
`data/raw/` é cópia congelada dos dados de origem (não editar; `migrar.py` recusa rodar se um hash mudar).
