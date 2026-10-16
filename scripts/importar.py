#!/usr/bin/env python3
"""Reconstrói o sqlite a partir de data/dump.sql (schema + INSERTs) e repopula a busca FTS.

Uso: python3 scripts/importar.py [--db caminho.sqlite] [--dump data/dump.sql] [--force]
Por segurança não sobrescreve um banco existente sem --force.
"""
import argparse
import sys
from pathlib import Path

from comum import DUMP, SQLITE, conectar, popular_fts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(SQLITE))
    ap.add_argument("--dump", default=str(DUMP))
    ap.add_argument("--force", action="store_true", help="apaga o banco existente")
    a = ap.parse_args()
    db = Path(a.db)
    if db.exists():
        if not a.force:
            sys.exit(f"{db} já existe; use --force para recriar")
        for suf in ("", "-wal", "-shm"):
            p = db.with_name(db.name + suf)
            if p.exists():
                p.unlink()
    con = conectar(db)
    con.executescript(Path(a.dump).read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = ON")
    popular_fts(con)
    n = con.execute("SELECT (SELECT count(*) FROM entidade), (SELECT count(*) FROM relacao), (SELECT count(*) FROM evento)").fetchone()
    print(f"importado em {db}: {n[0]} entidades, {n[1]} relações, {n[2]} eventos")
    con.close()


if __name__ == "__main__":
    main()
