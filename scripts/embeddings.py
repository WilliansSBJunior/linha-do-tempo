#!/usr/bin/env python3
"""Embeddings da Linha do Tempo (RAG pequeno). Biblioteca + CLI.

Interface:   embed(textos: list[str]) -> list[list[float]]     (vetores normalizados, norma 1)
             provedor_ativo() -> {"provedor", "modelo", "dim", "disponivel", "motivo"}

Provedor, por env (LDT_EMBED_PROVIDER):
  auto (padrao)  sentence-transformers se estiver instalado E o modelo carregar; senao 'hash' (sem rede, sem dependencia)
  st             sentence-transformers (LDT_EMBED_MODEL, padrao intfloat/multilingual-e5-small;
                 alternativa paraphrase-multilingual-MiniLM-L12-v2). Falha se nao instalado/baixado.
  openai         POST {LDT_EMBED_URL|https://api.openai.com/v1}/embeddings   chave: LDT_EMBED_API_KEY ou OPENAI_API_KEY   (padrao text-embedding-3-small)
  voyage         POST https://api.voyageai.com/v1/embeddings                 chave: LDT_EMBED_API_KEY ou VOYAGE_API_KEY   (padrao voyage-multilingual-2)
  ollama         POST {LDT_EMBED_URL|http://localhost:11434}/api/embed       (padrao bge-m3)
  hash           feature hashing de n-gramas de caracteres + palavras, 256 dim. Fraco (lexical), deterministico.
Os provedores openai/voyage/ollama estao implementados mas NAO foram testados contra a rede real.

Armazenamento: tabela `embedding` (scripts/schema_rag.sql), vetor float32 em BLOB. Busca: numpy (cosseno = produto escalar).
A extensao sqlite-vec nao e usada (nao instalavel no ambiente de desenvolvimento; ver mcp/README.md).

CLI:  python3 scripts/embeddings.py [--db DB] [--rebuild] [--tabelas trecho,evidencia,relacao,evento,entidade] [--lote 64]
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.request
import zlib
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
SCHEMA_RAG = AQUI / "schema_rag.sql"
TABELAS_PADRAO = ["trecho", "evidencia", "relacao", "evento", "entidade"]
TABELAS_VALIDAS = TABELAS_PADRAO + ["nota", "relacao_rotulo"]
HASH_DIM = 256
HASH_MODELO = "hash-ngram-256-v1"

# Limiares de cosseno por familia de modelo. Modelos reais (e5/MiniLM/openai...) separam melhor; o hash lexical e calibrado
# (ver docs de mcp/README.md). Sobrescreva com LDT_SIM_MIN / LDT_SIM_DEDUP.
LIMIARES = {"hash": (0.45, 0.60), "real": (0.80, 0.90)}


class ProvedorIndisponivel(RuntimeError):
    pass


# --------------------------------------------------------------------------- provedores
def _norm(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _hash_vec(texto):
    v = np.zeros(HASH_DIM, dtype=np.float32)
    palavras = _norm(texto).split()
    feats = {}

    def add(f, peso):
        feats[f] = feats.get(f, 0.0) + peso

    for p in palavras:
        add("w:" + p, 1.5)
        q = f"^{p}$"
        for n in (3, 4, 5):
            for i in range(len(q) - n + 1):
                add(f"c{n}:" + q[i:i + n], 1.0)
    for a, b in zip(palavras, palavras[1:]):
        add(f"b:{a}_{b}", 1.0)
    for f, w in feats.items():
        h = zlib.crc32(f.encode("utf-8"))
        v[h % HASH_DIM] += (1.0 if (h >> 16) & 1 else -1.0) * (1.0 + np.log(w))
    n = float(np.linalg.norm(v))
    return v / n if n else v


def _prov_hash(textos, tipo):
    return [_hash_vec(t).tolist() for t in textos]


_ST = {}


def _st_modelo():
    return os.environ.get("LDT_EMBED_MODEL") or "intfloat/multilingual-e5-small"


def _st_carregar():
    nome = _st_modelo()
    if nome not in _ST:
        try:
            from sentence_transformers import SentenceTransformer
            _ST[nome] = SentenceTransformer(nome)
        except Exception as e:
            raise ProvedorIndisponivel(f"sentence-transformers/{nome} indisponivel: {type(e).__name__}: {e}") from e
    return _ST[nome]


def _prov_st(textos, tipo):
    m = _st_carregar()
    if "e5" in _st_modelo().lower():
        textos = [("query: " if tipo == "query" else "passage: ") + t for t in textos]
    return m.encode(textos, normalize_embeddings=True, show_progress_bar=False).tolist()


def _post_json(url, corpo, headers):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        raise ProvedorIndisponivel(f"chamada remota falhou ({url}): {type(e).__name__}: {e}") from e


def _chave(*nomes):
    for n in nomes:
        if os.environ.get(n):
            return os.environ[n]
    raise ProvedorIndisponivel(f"chave ausente: defina {' ou '.join(nomes)}")


def _prov_openai(textos, tipo):
    base = (os.environ.get("LDT_EMBED_URL") or "https://api.openai.com/v1").rstrip("/")
    r = _post_json(base + "/embeddings", {"model": _modelo_remoto("text-embedding-3-small"), "input": textos},
                   {"Authorization": "Bearer " + _chave("LDT_EMBED_API_KEY", "OPENAI_API_KEY")})
    return [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]


def _prov_voyage(textos, tipo):
    r = _post_json("https://api.voyageai.com/v1/embeddings",
                   {"model": _modelo_remoto("voyage-multilingual-2"), "input": textos,
                    "input_type": "query" if tipo == "query" else "document"},
                   {"Authorization": "Bearer " + _chave("LDT_EMBED_API_KEY", "VOYAGE_API_KEY")})
    return [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]


def _prov_ollama(textos, tipo):
    base = (os.environ.get("LDT_EMBED_URL") or "http://localhost:11434").rstrip("/")
    r = _post_json(base + "/api/embed", {"model": _modelo_remoto("bge-m3"), "input": textos}, {})
    return r["embeddings"]


def _modelo_remoto(padrao):
    return os.environ.get("LDT_EMBED_MODEL") or padrao


_IMPL = {"hash": _prov_hash, "st": _prov_st, "openai": _prov_openai, "voyage": _prov_voyage, "ollama": _prov_ollama}
_PADROES_REMOTOS = {"openai": "text-embedding-3-small", "voyage": "voyage-multilingual-2", "ollama": "bge-m3"}
_auto_cache = {}


def _resolver():
    """-> (provedor, motivo_do_fallback|None)."""
    p = (os.environ.get("LDT_EMBED_PROVIDER") or "auto").strip().lower()
    if p in ("st", "sentence-transformers"):
        return "st", None
    if p in _IMPL:
        return p, None
    if p != "auto":
        raise ProvedorIndisponivel(f"LDT_EMBED_PROVIDER='{p}' invalido (auto|st|openai|voyage|ollama|hash)")
    chave = os.environ.get("LDT_EMBED_MODEL", "")
    if chave not in _auto_cache:
        try:
            _st_carregar()
            _auto_cache[chave] = ("st", None)
        except ProvedorIndisponivel as e:
            _auto_cache[chave] = ("hash", str(e))
    return _auto_cache[chave]


def _modelo_de(p):
    if p == "hash":
        return HASH_MODELO
    if p == "st":
        return "st:" + _st_modelo()
    return f"{p}:{_modelo_remoto(_PADROES_REMOTOS[p])}"


def provedor_ativo():
    """Nao chama a rede (exceto, no modo auto, a tentativa local de carregar o sentence-transformers). dim so e conhecida apos o 1o embed
    nos provedores remotos."""
    try:
        p, motivo = _resolver()
    except ProvedorIndisponivel as e:
        return {"provedor": None, "modelo": None, "dim": None, "disponivel": False, "motivo": str(e)}
    out = {"provedor": p, "modelo": _modelo_de(p), "dim": HASH_DIM if p == "hash" else None, "disponivel": True,
           "familia_limiar": "hash" if p == "hash" else "real"}
    if motivo:
        out["motivo"] = "fallback para hash: " + motivo
    if p in ("openai", "voyage"):
        try:
            _chave("LDT_EMBED_API_KEY", "OPENAI_API_KEY" if p == "openai" else "VOYAGE_API_KEY")
        except ProvedorIndisponivel as e:
            out.update(disponivel=False, motivo=str(e))
    return out


def embed(textos, tipo="passage"):
    """textos -> vetores float (norma 1). `tipo`: 'passage' (documento) ou 'query' (consulta); so muda o prefixo do e5 e o input_type do voyage."""
    textos = [t if t and t.strip() else " " for t in textos]
    if not textos:
        return []
    p, _ = _resolver()
    vs = np.asarray(_IMPL[p](textos, tipo), dtype=np.float32)
    n = np.linalg.norm(vs, axis=1, keepdims=True)
    n[n == 0] = 1
    return (vs / n).tolist()


def limiares():
    """(sim_min, sim_dedup) do provedor ativo; LDT_SIM_MIN / LDT_SIM_DEDUP sobrescrevem."""
    info = provedor_ativo()
    a, b = LIMIARES.get(info.get("familia_limiar") or "real")
    return float(os.environ.get("LDT_SIM_MIN", a)), float(os.environ.get("LDT_SIM_DEDUP", b))


# --------------------------------------------------------------------------- schema / textos
def garantir_schema(con):
    """Idempotente; seguro dentro de transacao (nao usa executescript)."""
    sql = re.sub(r"--[^\n]*", "", SCHEMA_RAG.read_text(encoding="utf-8"))
    for st in sql.split(";"):
        if st.strip():
            con.execute(st)


_SQL_TEXTO = {
    "trecho": "SELECT CAST(id AS TEXT) id, afirmacao || ' ' || COALESCE(texto_original,'') t FROM trecho",
    "evidencia": "SELECT CAST(id AS TEXT) id, veiculo || ' ' || COALESCE(titulo,'') || ' ' || COALESCE(resumo,'') || ' ' || url t FROM evidencia",
    "relacao": """SELECT CAST(r.id AS TEXT) id, r.rotulo || ' ' || COALESCE(r.descricao,'') || ' ' || d.nome || ' ' || p.nome t
                  FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para""",
    "relacao_rotulo": "SELECT CAST(id AS TEXT) id, rotulo t FROM relacao",
    "evento": "SELECT id, titulo || ' ' || COALESCE(descricao,'') t FROM evento",
    "entidade": """SELECT e.id id, e.nome || ' ' || COALESCE(e.cargo,'') || ' ' || COALESCE(e.descricao,'') || ' ' ||
                   COALESCE((SELECT group_concat(alias,' ') FROM entidade_alias a WHERE a.entidade_id=e.id),'') t FROM entidade e""",
    "nota": "SELECT CAST(id AS TEXT) id, COALESCE(titulo,'') || ' ' || texto t FROM nota",
}
_SQL_ORFAOS = {  # origem_id sem linha de origem
    "trecho": "SELECT CAST(id AS TEXT) FROM trecho", "evidencia": "SELECT CAST(id AS TEXT) FROM evidencia",
    "relacao": "SELECT CAST(id AS TEXT) FROM relacao", "relacao_rotulo": "SELECT CAST(id AS TEXT) FROM relacao",
    "evento": "SELECT id FROM evento", "entidade": "SELECT id FROM entidade", "nota": "SELECT CAST(id AS TEXT) FROM nota"}


def _h(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _limpo(t):
    return re.sub(r"\s+", " ", t).strip()


def textos_de(con, tabela, ids=None):
    """-> {origem_id: texto}. Texto montado por tabela (ver _SQL_TEXTO)."""
    sql = _SQL_TEXTO[tabela]
    p = []
    if ids is not None:
        ids = list(ids)
        if not ids:
            return {}
        # subselect: evita colar WHERE/AND numa consulta que já tem WHERE interno (caso 'entidade')
        sql = f"SELECT id, t FROM ({sql}) WHERE id IN ({','.join('?' * len(ids))})"
        p = ids
    return {r[0]: _limpo(r[1]) for r in con.execute(sql, p)}


def atualizar(con, tabela, ids=None, lote=64, rebuild=False, modelo=None):
    """Gera/atualiza embeddings de `tabela` (todas as linhas ou `ids`). Pula linhas com mesmo modelo+hash. Remove orfaos quando ids=None.
    Nao faz commit. -> {"novos","atualizados","pulados","removidos"}. Levanta ProvedorIndisponivel."""
    garantir_schema(con)
    info = provedor_ativo()
    if not info["disponivel"]:
        raise ProvedorIndisponivel(info.get("motivo") or "provedor indisponivel")
    modelo = modelo or info["modelo"]
    if ids is not None:  # ids nao numericos tambem ok; normaliza para texto
        ids = [str(i) for i in ids]
    textos = textos_de(con, tabela, ids)
    atuais = {r[0]: r[1] for r in con.execute("SELECT origem_id, texto_hash FROM embedding WHERE origem_tabela=? AND modelo=?", (tabela, modelo))}
    if rebuild and ids is None:
        con.execute("DELETE FROM embedding WHERE origem_tabela=? AND modelo=?", (tabela, modelo))
        atuais = {}
    fila = [(i, t) for i, t in textos.items() if atuais.get(i) != _h(t)]
    stats = {"novos": 0, "atualizados": 0, "pulados": len(textos) - len(fila), "removidos": 0}
    for k in range(0, len(fila), lote):
        parte = fila[k:k + lote]
        vs = np.asarray(embed([t for _, t in parte]), dtype=np.float32)
        for (i, t), v in zip(parte, vs):
            stats["atualizados" if i in atuais else "novos"] += 1
            con.execute("""INSERT OR REPLACE INTO embedding(origem_tabela, origem_id, modelo, dim, texto_hash, vetor)
                           VALUES(?,?,?,?,?,?)""", (tabela, i, modelo, int(v.shape[0]), _h(t), v.astype("<f4").tobytes()))
    if ids is None:
        vivos = {r[0] for r in con.execute(_SQL_ORFAOS[tabela])}
        orf = [i for i in {r[0] for r in con.execute("SELECT origem_id FROM embedding WHERE origem_tabela=? AND modelo=?", (tabela, modelo))} if i not in vivos]
        for i in orf:
            con.execute("DELETE FROM embedding WHERE origem_tabela=? AND origem_id=? AND modelo=?", (tabela, i, modelo))
        stats["removidos"] = len(orf)
    return stats


def limpar_orfaos(con, tabelas=("trecho", "relacao", "relacao_rotulo", "evidencia")):
    garantir_schema(con)
    n = 0
    for t in tabelas:
        vivos = {r[0] for r in con.execute(_SQL_ORFAOS[t])}
        for (i,) in con.execute("SELECT DISTINCT origem_id FROM embedding WHERE origem_tabela=?", (t,)).fetchall():
            if i not in vivos:
                n += con.execute("DELETE FROM embedding WHERE origem_tabela=? AND origem_id=?", (t, i)).rowcount
    return n


# --------------------------------------------------------------------------- busca vetorial (numpy)
def carregar_matriz(con, tabelas, modelo):
    """-> (matriz float32 [n, dim], [(origem_tabela, origem_id)]) ou (None, [])."""
    ph = ",".join("?" * len(tabelas))
    try:
        rows = con.execute(f"SELECT origem_tabela, origem_id, dim, vetor FROM embedding WHERE modelo=? AND origem_tabela IN ({ph})",
                           [modelo, *tabelas]).fetchall()
    except sqlite3.OperationalError:  # tabela embedding ainda nao existe
        return None, []
    if not rows:
        return None, []
    dim = rows[0][2]
    rows = [r for r in rows if r[2] == dim]
    m = np.frombuffer(b"".join(r[3] for r in rows), dtype="<f4").reshape(len(rows), dim)
    return m, [(r[0], r[1]) for r in rows]


def vetores_de(con, tabela, ids, modelo=None, textos=None):
    """-> {origem_id: vetor np.float32}. Usa os armazenados; os que faltam sao embutidos na hora (nao persiste) a partir de `textos`
    ({id: texto}, padrao: textos_de). Levanta ProvedorIndisponivel se faltar vetor e nao houver provedor."""
    modelo = modelo or provedor_ativo()["modelo"]
    ids = [str(i) for i in ids]
    out = {}
    try:
        for k in range(0, len(ids), 500):
            parte = ids[k:k + 500]
            for oid, dim, vet in con.execute(
                    f"SELECT origem_id, dim, vetor FROM embedding WHERE origem_tabela=? AND modelo=? AND origem_id IN ({','.join('?' * len(parte))})",
                    [tabela, modelo, *parte]):
                out[oid] = np.frombuffer(vet, dtype="<f4")
    except sqlite3.OperationalError:
        pass
    falta = [i for i in ids if i not in out]
    if falta:
        textos = textos or textos_de(con, tabela, falta)
        falta = [i for i in falta if i in textos]
        for i, v in zip(falta, embed([textos[i] for i in falta])):
            out[i] = np.asarray(v, dtype=np.float32)
    return out


def top_k(con, vetor, tabelas, k=50, modelo=None, apenas_ids=None):
    """Cosseno (vetores normalizados). -> [(origem_tabela, origem_id, cos)] decrescente. `apenas_ids`: conjunto de (tabela,id) permitido."""
    modelo = modelo or provedor_ativo()["modelo"]
    m, chaves = carregar_matriz(con, list(tabelas), modelo)
    if m is None:
        return []
    q = np.asarray(vetor, dtype=np.float32)
    if q.shape[0] != m.shape[1]:
        return []
    sc = m @ q
    ordem = np.argsort(-sc)
    out = []
    for i in ordem:
        if apenas_ids is not None and chaves[i] not in apenas_ids:
            continue
        out.append((chaves[i][0], chaves[i][1], float(sc[i])))
        if len(out) >= k:
            break
    return out


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    sys.path.insert(0, str(AQUI))
    from comum import SQLITE
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(SQLITE))
    ap.add_argument("--rebuild", action="store_true", help="apaga e regera os embeddings do modelo ativo nas tabelas escolhidas")
    ap.add_argument("--tabelas", default=",".join(TABELAS_PADRAO), help="lista separada por virgula (+ nota, relacao_rotulo)")
    ap.add_argument("--lote", type=int, default=64)
    a = ap.parse_args(argv)
    tabelas = [t.strip() for t in a.tabelas.split(",") if t.strip()]
    ruim = [t for t in tabelas if t not in TABELAS_VALIDAS]
    if ruim:
        ap.error(f"tabelas invalidas: {ruim}; validas: {TABELAS_VALIDAS}")
    if "relacao" in tabelas and "relacao_rotulo" not in tabelas:
        tabelas.append("relacao_rotulo")  # usado na deduplicacao; barato
    info = provedor_ativo()
    print("provedor:", json.dumps(info, ensure_ascii=False))
    if not info["disponivel"]:
        print("provedor indisponivel; nada feito", file=sys.stderr)
        return 2
    con = sqlite3.connect(a.db, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 30000")
    t0 = time.time()
    try:
        con.execute("BEGIN IMMEDIATE")
        for t in tabelas:
            t1 = time.time()
            s = atualizar(con, t, None, a.lote, a.rebuild)
            print(f"{t:15s} novos={s['novos']:5d} atualizados={s['atualizados']:4d} pulados={s['pulados']:5d} removidos={s['removidos']:3d}  {time.time() - t1:6.2f}s")
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    tot = con.execute("SELECT origem_tabela, count(*) FROM embedding WHERE modelo=? GROUP BY 1 ORDER BY 1", (info["modelo"],)).fetchall()
    print("total no banco (modelo %s):" % info["modelo"], {r[0]: r[1] for r in tot}, f"| {time.time() - t0:.2f}s")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
