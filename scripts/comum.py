"""Utilidades compartilhadas: caminhos, normalização de URL, dump determinístico, FTS."""
import hashlib, os, re, sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
SCRIPTS = ROOT / "scripts"
SQLITE = DATA / "linha-do-tempo.sqlite"
DUMP = DATA / "dump.sql"

# Timestamp fixo da migração: mantém dump.sql e JSONs reproduzíveis byte a byte entre execuções.
TS_MIGRACAO = "2026-10-16T00:00:00Z"

# Tabelas na ordem de dependência (FK) usada no dump. natureza/natureza_mapa vêm no schema.sql.
TABELAS = ["meta", "categoria", "entidade", "entidade_alias", "evidencia", "relacao", "evento",
           "evento_entidade", "evento_relacao", "relacao_evidencia", "evento_evidencia",
           "video", "trecho", "trecho_entidade", "trecho_ano", "trecho_valor", "trecho_relacao",
           "corte", "corte_trecho", "relacao_corte", "nota", "nota_entidade", "indicador", "serie",
           "ranking_empresa", "mandato", "bancada", "aresta_legado"]
TABELAS_NO_SCHEMA = {"natureza", "natureza_mapa"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def normalizar_url(u):
    """Strip de #fragment, barra final e parâmetros utm_*. Nada além disso."""
    u = u.strip()
    p = urlsplit(u)
    query = "&".join(x for x in p.query.split("&") if x and not x.lower().startswith("utm_"))
    # barra final sai só quando não há query (WordPress usa /?p=123: tirar a barra mudaria a rota)
    path = p.path if query else p.path.rstrip("/")
    return urlunsplit((p.scheme, p.netloc, path, query, ""))


def dominio_de(url):
    h = urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def conectar(caminho):
    con = sqlite3.connect(str(caminho))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def popular_fts(con):
    """Reconstrói busca_fts a partir das tabelas (determinístico)."""
    con.execute("DELETE FROM busca_fts")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'entidade', e.id, e.nome || ' ' || COALESCE(e.cargo,'') || ' ' || COALESCE(e.descricao,'') || ' ' ||
               COALESCE((SELECT group_concat(alias,' ') FROM entidade_alias a WHERE a.entidade_id=e.id),'')
        FROM entidade e ORDER BY e.id""")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'evento', id, titulo || ' ' || COALESCE(descricao,'') FROM evento ORDER BY id""")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'relacao', CAST(id AS TEXT), rotulo || ' ' || COALESCE(descricao,'') FROM relacao ORDER BY id""")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'nota', CAST(id AS TEXT), COALESCE(titulo,'') || ' ' || texto FROM nota ORDER BY id""")
    con.commit()


def _pk_order(con, t):
    cols = [r for r in con.execute(f"PRAGMA table_info({t})")]
    pk = [r["name"] for r in sorted(cols, key=lambda r: r["pk"]) if r["pk"]]
    return ", ".join(pk) if pk else "rowid"


def gerar_dump(con, destino=DUMP):
    """dump.sql = schema.sql + INSERTs (colunas explícitas, sem colunas geradas, ordenados por PK). FTS é reconstruída ao importar."""
    partes = [(SCRIPTS / "schema.sql").read_text(encoding="utf-8").rstrip() + "\n",
              "\n-- Dados (gerado por scripts/comum.gerar_dump; não editar à mão)\nBEGIN;\n"]
    existentes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in TABELAS:
        if t not in existentes:
            continue
        cols = [r["name"] for r in con.execute(f"PRAGMA table_xinfo({t})") if r["hidden"] == 0]
        expr = " || ',' || ".join(f"quote({c})" for c in cols)
        sql = f"SELECT 'INSERT INTO {t}({', '.join(cols)}) VALUES(' || {expr} || ');' FROM {t} ORDER BY {_pk_order(con, t)}"
        linhas = [r[0] for r in con.execute(sql)]
        if linhas:
            partes.append(f"-- {t} ({len(linhas)})\n" + "\n".join(linhas) + "\n")
    partes.append("COMMIT;\n")
    Path(destino).write_text("".join(partes), encoding="utf-8")
    return Path(destino)
