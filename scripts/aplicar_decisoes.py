#!/usr/bin/env python3
"""Reaplica data/curadoria/decisoes.jsonl (decisões da fila de revisão) sobre o banco. Idempotente.

Rode DEPOIS de migrar.py (que recria o banco do zero a partir de raw + curadoria e, portanto, perde as decisões gravadas pelo MCP):

    python3 scripts/migrar.py && python3 scripts/aplicar_decisoes.py && python3 scripts/exportar_json.py && python3 scripts/validar.py

Uso: python3 scripts/aplicar_decisoes.py [--db data/linha-do-tempo.sqlite] [--decisoes data/curadoria/decisoes.jsonl] [--dump data/dump.sql]

- Pula as decisões desfeitas (linha {tipo:'desfazer'}) e as que já estão aplicadas.
- Relações e cortes são achados pela chave natural gravada em `alvo` (de, para, tipo, rótulo, início / vídeo, início, fim, título),
  não só pelo id; o que não existir no banco (ex.: relação criada pelo MCP a partir de um vídeo que a migração não recria) é listado
  em "ignoradas" e não interrompe as demais.
- Fusões de evento já entram por migrar.py (eventos-fusoes.json); aqui só se confirma a natureza resultante.
- Usa o mesmo núcleo de mcp/revisao.py, numa única transação, e regrava o dump ao fim. Não escreve no jsonl.
"""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "mcp"))
sys.path.insert(0, str(RAIZ / "scripts"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=os.environ.get("LDT_DB") or str(RAIZ / "data" / "linha-do-tempo.sqlite"))
    ap.add_argument("--decisoes", default=None, help="padrão: <pasta do banco>/curadoria/decisoes.jsonl")
    ap.add_argument("--dump", default=None, help="padrão: <pasta do banco>/dump.sql")
    a = ap.parse_args(argv)
    db = Path(a.db).resolve()
    os.environ["LDT_DB"] = str(db)
    os.environ["LDT_DUMP"] = str(Path(a.dump).resolve() if a.dump else db.parent / "dump.sql")
    if a.decisoes:
        os.environ["LDT_DECISOES"] = str(Path(a.decisoes).resolve())
    import revisao as R  # depois do env: server lê LDT_DB por chamada
    caminho = R.caminho_decisoes()
    if not caminho.exists():
        print(f"{caminho}: não existe; nada a aplicar")
        return 0
    res = R.aplicar_todas(caminho=caminho)
    if not res.get("ok"):
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 1
    print(f"{caminho}: {res['total']} linhas, {res['desfeitas']} desfeitas; aplicadas agora {len(res['aplicadas'])}, "
          f"já estavam {res['ja_estavam']}, ignoradas {len(res['ignoradas'])}; dump: {res.get('dump', {}).get('dump_status')}")
    for i in res["ignoradas"]:
        print(f"  ignorada {i['id']}: {i['motivo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
