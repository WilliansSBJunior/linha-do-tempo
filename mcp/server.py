#!/usr/bin/env python3
"""MCP server da Linha do Tempo (stdio). ÚNICO escritor de data/linha-do-tempo.sqlite.

Variáveis de ambiente (todas opcionais):
  LDT_DB           caminho do sqlite            (padrão data/linha-do-tempo.sqlite)
  LDT_DUMP         caminho do dump.sql          (padrão data/dump.sql)
  LDT_EXPORT_JSON  "1" => após cada escrita roda scripts/exportar_json.py (padrão: não)
  LDT_EMBED_PROVIDER / LDT_EMBED_MODEL / LDT_EMBED_API_KEY / LDT_EMBED_URL  provedor de embeddings (ver scripts/embeddings.py)
  LDT_DEDUP_EMBEDDING  "0" => não reutiliza relações semanticamente iguais em inserir_relacao/inserir_fonte/inserir_video (padrão: ligado)
  LDT_SIM_MIN / LDT_SIM_DEDUP  limiares de cosseno (padrão depende do provedor: 0.80/0.90 modelos reais, 0.45/0.60 fallback hash)

Toda ferramenta de escrita: lock de arquivo -> BEGIN IMMEDIATE -> ... -> foreign_key_check -> COMMIT -> regrava o dump.
O commit no git é manual.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import DUMP, SQLITE, dominio_de, gerar_dump, normalizar_url  # noqa: E402
from slug import alias_norm, slugify  # noqa: E402
import curadoria as CUR  # noqa: E402  (regras de temas: inferir_temas_relacao)
try:  # RAG: precisa de numpy; sem ele as ferramentas semânticas respondem erro e a escrita segue sem embeddings
    import embeddings as EMB  # noqa: E402
except ImportError as _e:  # pragma: no cover
    EMB = None
    _EMB_ERRO = str(_e)

try:  # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except Exception:  # SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server

TIPOS_RELACAO = ["financeira", "societaria", "contratual", "juridica", "investigacao", "politica", "pessoal",
                 "familiar", "profissional", "institucional", "religiosa", "midia", "outra"]
STATUS_RELACAO = ["rascunho", "revisar", "publicada", "descartada"]
ORIGENS_RELACAO = ["teia", "origens", "classificador", "manual", "linha_do_tempo"]
TIPOS_EVIDENCIA = ["reportagem", "documento_oficial", "decisao_judicial", "processo", "comunicado", "relatorio",
                   "dado_oficial", "wiki", "video", "outro"]
PLATAFORMAS = ["youtube", "instagram", "tiktok", "x", "podcast", "outro"]
TIPOS_FONTE = ["video", "reportagem", "documento", "pdf", "depoimento", "decisao", "transcricao", "outro"]
# tipo da fonte -> evidencia.tipo (neutro quando não há como saber: 'documento'/'pdf' podem ser qualquer coisa)
EVIDENCIA_DE_FONTE = {"video": "video", "reportagem": "reportagem", "decisao": "decisao_judicial", "documento": "outro", "pdf": "outro",
                      "depoimento": "outro", "transcricao": "outro", "outro": "outro"}
MOEDAS = {"BRL": "BRL", "R$": "BRL", "REAL": "BRL", "REAIS": "BRL", "USD": "USD", "US$": "USD", "$": "USD",
          "DOLAR": "USD", "EUR": "EUR", "€": "EUR", "EURO": "EUR", "PCT": "pct", "%": "pct", "PERCENT": "pct"}

_trava_thread = threading.Lock()


class Rejeitado(Exception):
    """Entrada inválida: vira {'ok': False, ...} em vez de exceção do protocolo."""

    def __init__(self, erro, **extra):
        super().__init__(erro)
        self.payload = {"ok": False, "erro": erro, **extra}


# --------------------------------------------------------------------------- infra
def caminho_db():
    return Path(os.environ.get("LDT_DB") or SQLITE)


def caminho_dump():
    return Path(os.environ.get("LDT_DUMP") or DUMP)


def abrir():
    con = sqlite3.connect(str(caminho_db()), timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    return con


def agora():
    with contextlib.closing(sqlite3.connect(":memory:")) as c:
        return c.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')").fetchone()[0]


@contextlib.contextmanager
def leitura():
    con = abrir()
    try:
        yield con
    finally:
        con.close()


def _gravar_dump(con):
    destino = caminho_dump()
    tmp = destino.with_name(destino.name + ".tmp")
    gerar_dump(con, tmp)
    os.replace(tmp, destino)


@contextlib.contextmanager
def escrita():
    """Transação única serializada (threads + processos). Ao fim, regrava o dump. Rejeição/erro => rollback."""
    resultado = {}
    with _trava_thread:
        lock_path = caminho_db().with_name(".mcp-escrita.lock")
        with open(lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            con = abrir()
            try:
                con.execute("BEGIN IMMEDIATE")
                try:
                    yield con, resultado
                    sincronizar_fts(con)
                    viol = con.execute("PRAGMA foreign_key_check").fetchall()
                    if viol:
                        raise Rejeitado("foreign_key_check falhou; transação desfeita", violacoes=[tuple(v) for v in viol[:10]])
                    con.execute("COMMIT")
                except BaseException:
                    if con.in_transaction:
                        con.execute("ROLLBACK")
                    raise
                resultado["dump"] = _pos_commit(con)
            finally:
                con.close()
                fcntl.flock(lf, fcntl.LOCK_UN)
    return None


def _pos_commit(con):
    saida = {"dump_sql": str(caminho_dump()), "commit_git": "manual (git add data/ && git commit)"}
    try:
        _gravar_dump(con)
        saida["dump_status"] = "ok"
    except Exception as e:  # dados já estão no sqlite; só o dump ficou defasado
        saida["dump_status"] = f"ERRO ao regravar dump: {e} (rode exportar())"
    if os.environ.get("LDT_EXPORT_JSON") == "1":
        saida["exportar_json"] = _rodar([sys.executable, str(RAIZ / "scripts" / "exportar_json.py"), "--db", str(caminho_db())])
    return saida


def _rodar(cmd):
    p = subprocess.run(cmd, cwd=str(RAIZ), capture_output=True, text=True)
    return {"codigo": p.returncode, "saida": (p.stdout + p.stderr).strip()}


def operacao_escrita(fn):
    """Executa fn(con, resultado) numa transação; converte Rejeitado em payload."""
    try:
        with escrita() as (con, resultado):
            out = fn(con)
            resultado.update(out)
        return {"ok": True, **resultado}
    except Rejeitado as r:
        return r.payload
    except sqlite3.IntegrityError as e:
        return {"ok": False, "erro": f"violação de integridade no banco: {e}"}


# --------------------------------------------------------------------------- FTS auxiliar
def _texto_trecho(r):
    return f"{r['afirmacao']} {r['texto_original'] or ''}"


def sincronizar_fts(con):
    """Trechos, relações e fontes novos entram em busca_fts (importar.py/popular_fts não cobrem 'trecho')."""
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='trecho' AND CAST(origem_id AS INTEGER) NOT IN (SELECT id FROM trecho)")
    for r in con.execute("""SELECT id, afirmacao, texto_original FROM trecho
                            WHERE CAST(id AS TEXT) NOT IN (SELECT origem_id FROM busca_fts WHERE origem_tabela='trecho')""").fetchall():
        con.execute("INSERT INTO busca_fts(origem_tabela, origem_id, texto) VALUES('trecho', ?, ?)", (str(r["id"]), _texto_trecho(r)))
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='relacao' AND CAST(origem_id AS INTEGER) NOT IN (SELECT id FROM relacao)")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'relacao', CAST(id AS TEXT), rotulo || ' ' || COALESCE(descricao,'') FROM relacao
        WHERE CAST(id AS TEXT) NOT IN (SELECT origem_id FROM busca_fts WHERE origem_tabela='relacao')""")
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='fonte' AND origem_id NOT IN (SELECT id FROM fonte)")
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'fonte', id, titulo || ' ' || COALESCE(canal,'') || ' ' || COALESCE(resumo,'') || ' ' || COALESCE(texto,'') FROM fonte
        WHERE id NOT IN (SELECT origem_id FROM busca_fts WHERE origem_tabela='fonte')""")


def _fts_trechos_defasado(con):
    a = con.execute("SELECT count(*) FROM trecho").fetchone()[0]
    b = con.execute("SELECT count(*) FROM busca_fts WHERE origem_tabela='trecho'").fetchone()[0]
    return a != b


def _fts_expr(texto, modo="AND"):
    toks = re.findall(r"\w+", texto, flags=re.UNICODE)
    if not toks:
        return None
    return f" {modo} ".join('"' + t.replace('"', '') + '"*' for t in toks)


# --------------------------------------------------------------------------- entidades
def _n_relacoes(con, eid):
    return con.execute("SELECT count(*) FROM relacao WHERE de=? OR para=?", (eid, eid)).fetchone()[0]


def _ficha(con, r, motivo=None):
    f = {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "categoria": r["categoria_id"], "cargo": r["cargo"],
         "descricao": (r["descricao"] or "")[:220] + ("…" if r["descricao"] and len(r["descricao"]) > 220 else ""),
         "aliases": [a["alias"] for a in con.execute("SELECT alias FROM entidade_alias WHERE entidade_id=? ORDER BY alias", (r["id"],))],
         "n_relacoes": _n_relacoes(con, r["id"])}
    if motivo:
        f["casou_por"] = motivo
    return f


def _candidatos(con, consulta, tipo=None):
    """-> {id: (score, motivo)}. 100 slug exato; 90 alias/nome normalizado exato; 60 palavras inteiras; 30 FTS."""
    q = consulta.strip()
    qn = alias_norm(q)
    res = {}

    def marca(eid, score, motivo):
        if eid not in res or res[eid][0] < score:
            res[eid] = (score, motivo)

    if not qn:
        return res
    slug = q.lower() if re.fullmatch(r"[a-z0-9-]+", q.lower()) else slugify(q)
    for r in con.execute("SELECT id FROM entidade WHERE id=?", (slug,)):
        marca(r["id"], 100, "slug")
    for r in con.execute("SELECT entidade_id FROM entidade_alias WHERE alias_norm=?", (qn,)):
        marca(r["entidade_id"], 90, "alias")
    nomes = [(r["id"], alias_norm(r["nome"])) for r in con.execute("SELECT id, nome FROM entidade")]
    for eid, nn in nomes:
        if nn == qn:
            marca(eid, 90, "nome")
    toks = qn.split()
    for r in con.execute("SELECT entidade_id, alias_norm FROM entidade_alias"):
        an = f" {r['alias_norm']} "
        if all(f" {t} " in an for t in toks):
            marca(r["entidade_id"], 60, "alias (palavra)")
    for eid, nn in nomes:
        nn = f" {nn} "
        if all(f" {t} " in nn for t in toks):
            marca(eid, 60, "nome (palavra)")
    for modo in ("AND", "OR"):
        expr = _fts_expr(q, modo)
        if not expr:
            break
        try:
            rows = con.execute("SELECT origem_id FROM busca_fts WHERE origem_tabela='entidade' AND busca_fts MATCH ? ORDER BY rank LIMIT 50", (expr,)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for r in rows:
            marca(r["origem_id"], 30 if modo == "AND" else 20, "texto (FTS)")
        if rows:
            break
    if tipo:
        ok = {r["id"] for r in con.execute("SELECT id FROM entidade WHERE tipo=?", (tipo,))}
        res = {k: v for k, v in res.items() if k in ok}
    return res


def buscar_entidade_core(con, consulta, tipo=None, limite=20):
    cands = _candidatos(con, consulta, tipo)
    linhas = []
    for eid, (score, motivo) in cands.items():
        r = con.execute("SELECT * FROM entidade WHERE id=?", (eid,)).fetchone()
        linhas.append((score, _n_relacoes(con, eid), r, motivo))
    linhas.sort(key=lambda x: (-x[0], -x[1], x[2]["id"]))
    return [_ficha(con, r, m) for _, _, r, m in linhas[:max(1, limite)]]


def _sugestoes(con, termo, n=3):
    return [{"id": e["id"], "nome": e["nome"], "tipo": e["tipo"], "casou_por": e["casou_por"]}
            for e in buscar_entidade_core(con, str(termo), None, n)]


def _existe(con, eid):
    return con.execute("SELECT 1 FROM entidade WHERE id=?", (eid,)).fetchone() is not None


def _resolver_ref(con, s, campo):
    """Para filtros de leitura: id, ou alias/nome exato e único. Senão Rejeitado com sugestões."""
    s = str(s).strip()
    if _existe(con, s):
        return s
    c = _candidatos(con, s)
    exatos = [k for k, (sc, _) in c.items() if sc >= 90]
    if len(exatos) == 1:
        return exatos[0]
    raise Rejeitado(f"'{s}' ({campo}) não resolve para uma entidade única", sugestoes=_sugestoes(con, s, 5))


def natureza_id(con, valor, campo="natureza"):
    v = str(valor).strip()
    r = con.execute("SELECT natureza_id FROM natureza_mapa WHERE codigo_externo=? ORDER BY sistema LIMIT 1", (v,)).fetchone()
    if r:
        return r[0]
    r = con.execute("SELECT id FROM natureza WHERE id=?", (v,)).fetchone()
    if r:
        return r[0]
    validos = sorted({x[0] for x in con.execute("SELECT codigo_externo FROM natureza_mapa")} | {x[0] for x in con.execute("SELECT id FROM natureza")})
    raise Rejeitado(f"{campo} '{valor}' inválida", validos=validos)


# --------------------------------------------------------------------------- relações: leitura
def _relacao_dict(con, r):
    nm = lambda i: con.execute("SELECT nome FROM entidade WHERE id=?", (i,)).fetchone()[0]
    d = {"id": r["id"], "de": {"id": r["de"], "nome": nm(r["de"])}, "para": {"id": r["para"], "nome": nm(r["para"])},
         "tipo": r["tipo"], "subtipo": r["subtipo"], "rotulo": r["rotulo"], "descricao": r["descricao"],
         "natureza": r["natureza_id"], "confianca": r["confianca"], "periodo_inicio": r["periodo_inicio"],
         "periodo_fim": r["periodo_fim"], "valor_brl": r["valor_brl"], "valor_texto": r["valor_texto"],
         "resposta": r["resposta"], "status": r["status"], "origem": r["origem"], "origem_ref": r["origem_ref"]}
    d["temas"] = [x[0] for x in con.execute("SELECT x.tema_id FROM relacao_tema x JOIN tema t ON t.id=x.tema_id WHERE x.relacao_id=? ORDER BY t.ordem, t.id", (r["id"],))]
    d["evidencias"] = [dict(x) for x in con.execute(
        """SELECT e.url, e.veiculo, e.titulo, e.data, e.tipo, x.papel FROM relacao_evidencia x JOIN evidencia e ON e.id=x.evidencia_id
           WHERE x.relacao_id=? ORDER BY x.ordem, e.id""", (r["id"],))]
    d["cortes"] = [dict(x) for x in con.execute(
        """SELECT c.id, c.video_id, c.titulo, c.inicio_s, c.fim_s, c.status FROM relacao_corte rc JOIN corte c ON c.id=rc.corte_id
           WHERE rc.relacao_id=? ORDER BY c.id""", (r["id"],))]
    return d


def _checar_temas(con, temas, campo="temas"):
    """Lista de slugs de tema existentes (sem repetição, ordem preservada)."""
    out = []
    validos = [r[0] for r in con.execute("SELECT id FROM tema ORDER BY ordem, id")]
    for t in temas or []:
        t = str(t).strip()
        if t not in validos:
            raise Rejeitado(f"{campo}: tema '{t}' não existe; este servidor nunca cria temas", validos=validos)
        if t not in out:
            out.append(t)
    return out


def buscar_relacoes_core(con, entidade=None, de=None, para=None, tipo=None, natureza=None, ano_inicio=None, ano_fim=None,
                         status=None, limite=50, tema=None):
    w, p = [], []
    if tema:
        t = _checar_temas(con, [tema], "tema")[0]
        w.append("id IN (SELECT relacao_id FROM relacao_tema WHERE tema_id=?)"); p.append(t)
    if entidade:
        e = _resolver_ref(con, entidade, "entidade")
        w.append("(de=? OR para=?)"); p += [e, e]
    if de:
        w.append("de=?"); p.append(_resolver_ref(con, de, "de"))
    if para:
        w.append("para=?"); p.append(_resolver_ref(con, para, "para"))
    if tipo:
        w.append("tipo=?"); p.append(tipo)
    if natureza:
        w.append("natureza_id=?"); p.append(natureza_id(con, natureza))
    if status:
        w.append("status=?"); p.append(status)
    # Sobreposição de períodos; relação sem fim é tratada como pontual (fim = início). Sem início: excluída se houver filtro de ano.
    if ano_inicio is not None:
        w.append("COALESCE(ano_fim, ano_inicio) >= ?"); p.append(int(ano_inicio))
    if ano_fim is not None:
        w.append("ano_inicio <= ?"); p.append(int(ano_fim))
    sql = "SELECT * FROM relacao" + (" WHERE " + " AND ".join(w) if w else "") + " ORDER BY COALESCE(ano_inicio, 9999), id LIMIT ?"
    rows = con.execute(sql, p + [max(1, int(limite))]).fetchall()
    return [_relacao_dict(con, r) for r in rows]


def _resolver_fonte(con, ref, tipo=None):
    """id ou URL (normalizada ou como veio) de uma fonte; `tipo` restringe (ex.: 'video')."""
    ref = str(ref).strip()
    r = con.execute("SELECT id FROM fonte WHERE (id=? OR url=? OR url=?)" + (" AND tipo=?" if tipo else ""),
                    [ref, ref, normalizar_url(ref)] + ([tipo] if tipo else [])).fetchone()
    if not r:
        raise Rejeitado(f"{'vídeo' if tipo == 'video' else 'fonte'} '{ref}' não encontrad{'o' if tipo == 'video' else 'a'}")
    return r["id"]


def buscar_trechos_core(con, texto=None, entidade=None, video=None, natureza=None, limite=50, fonte=None, tipo=None):
    w, p = [], []
    ordem = "t.fonte_id, t.ordem"
    if texto:
        expr = _fts_expr(texto, "AND")
        if not expr:
            raise Rejeitado("texto sem termos pesquisáveis")
        w.append("t.id IN (SELECT CAST(origem_id AS INTEGER) FROM busca_fts WHERE origem_tabela='trecho' AND busca_fts MATCH ?)")
        p.append(expr)
    if entidade:
        e = _resolver_ref(con, entidade, "entidade")
        w.append("t.id IN (SELECT trecho_id FROM trecho_entidade WHERE entidade_id=?)"); p.append(e)
    if video:  # legado: só fontes tipo video
        w.append("t.fonte_id=?"); p.append(_resolver_fonte(con, video, "video"))
    if fonte:
        w.append("t.fonte_id=?"); p.append(_resolver_fonte(con, fonte))
    if tipo:
        if tipo not in TIPOS_FONTE:
            raise Rejeitado(f"tipo '{tipo}' inválido", validos=TIPOS_FONTE)
        w.append("f.tipo=?"); p.append(tipo)
    if natureza:
        w.append("t.natureza_id=?"); p.append(natureza_id(con, natureza))
    sql = ("SELECT t.*, f.titulo AS fonte_titulo, f.url AS fonte_url, f.tipo AS fonte_tipo FROM trecho t JOIN fonte f ON f.id=t.fonte_id"
           + (" WHERE " + " AND ".join(w) if w else "") + f" ORDER BY {ordem} LIMIT ?")
    out = []
    for t in con.execute(sql, p + [max(1, int(limite))]).fetchall():
        d = {k: t[k] for k in ("id", "fonte_id", "fonte_tipo", "fonte_titulo", "fonte_url", "ordem", "inicio_s", "fim_s", "localizacao",
                               "texto_original", "afirmacao", "confianca", "potencial_corte")}
        d.update(video_id=t["fonte_id"], video_titulo=t["fonte_titulo"], video_url=t["fonte_url"])  # nomes antigos (compatibilidade)
        d["natureza"] = t["natureza_id"]
        d["entidades"] = [x[0] for x in con.execute("SELECT entidade_id FROM trecho_entidade WHERE trecho_id=? ORDER BY entidade_id", (t["id"],))]
        d["anos_referidos"] = [x[0] for x in con.execute("SELECT ano FROM trecho_ano WHERE trecho_id=? ORDER BY ano", (t["id"],))]
        d["valores"] = [dict(x) for x in con.execute("SELECT valor, moeda, descricao FROM trecho_valor WHERE trecho_id=? ORDER BY id", (t["id"],))]
        d["relacoes"] = [dict(x) for x in con.execute(
            """SELECT r.id, r.de, r.para, r.tipo, r.rotulo, r.status, tr.papel FROM trecho_relacao tr JOIN relacao r ON r.id=tr.relacao_id
               WHERE tr.trecho_id=? ORDER BY r.id""", (t["id"],))]
        d["cortes"] = [dict(x) for x in con.execute(
            "SELECT c.id, c.titulo, c.inicio_s, c.fim_s FROM corte_trecho ct JOIN corte c ON c.id=ct.corte_id WHERE ct.trecho_id=?", (t["id"],))]
        out.append(d)
    return out


# --------------------------------------------------------------------------- relações: escrita
_RE_ANO = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _periodo_val(v, campo):
    if v is None or v == "":
        return None
    s = str(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v).strip()
    if not _RE_ANO.match(s):
        raise Rejeitado(f"{campo} '{v}' inválido (use 'AAAA', 'AAAA-MM' ou 'AAAA-MM-DD')")
    return s


def parse_periodo(p):
    """dict {inicio?, fim?} | 'AAAA' | 'AAAA-AAAA' | None -> (inicio, fim)."""
    if p is None or p == "":
        return None, None
    if isinstance(p, dict):
        return _periodo_val(p.get("inicio"), "periodo.inicio"), _periodo_val(p.get("fim"), "periodo.fim")
    if isinstance(p, (int, float)) and not isinstance(p, bool):
        return _periodo_val(p, "periodo"), None
    s = str(p).strip()
    m = re.fullmatch(r"(\d{4})\s*(?:-|–|/|a|até)\s*(\d{4})?", s)
    if m:
        return m.group(1), m.group(2)
    return _periodo_val(s, "periodo"), None


def _checar_entidade(con, campo, eid):
    if not eid or not _existe(con, str(eid)):
        raise Rejeitado(f"entidade '{eid}' ({campo}) não existe; este servidor nunca cria entidades",
                        sugestoes=_sugestoes(con, eid or ""))


def _upsert_evidencia(con, ev):
    if not isinstance(ev, dict) or not ev.get("url"):
        raise Rejeitado(f"evidência inválida (precisa de 'url'): {ev!r}")
    url = normalizar_url(ev["url"])
    tipo = ev.get("tipo") or "reportagem"
    if tipo not in TIPOS_EVIDENCIA:
        raise Rejeitado(f"evidência.tipo '{tipo}' inválido", validos=TIPOS_EVIDENCIA)
    r = con.execute("SELECT * FROM evidencia WHERE url=?", (url,)).fetchone()
    if r:
        for campo in ("titulo", "data"):
            if ev.get(campo) and not r[campo]:
                con.execute(f"UPDATE evidencia SET {campo}=? WHERE id=?", (ev[campo], r["id"]))
        return r["id"]
    cur = con.execute("INSERT INTO evidencia(url, veiculo, titulo, data, tipo, criado_em) VALUES(?,?,?,?,?,?)",
                      (url, ev.get("veiculo") or dominio_de(url), ev.get("titulo"), ev.get("data"), tipo, agora()))
    return cur.lastrowid


def _ligar_evidencia(con, rid, eid, papel="sustenta", trecho_citado=None):
    if con.execute("SELECT 1 FROM relacao_evidencia WHERE relacao_id=? AND evidencia_id=?", (rid, eid)).fetchone():
        return False
    ordem = con.execute("SELECT COALESCE(MAX(ordem)+1, 0) FROM relacao_evidencia WHERE relacao_id=?", (rid,)).fetchone()[0]
    con.execute("INSERT INTO relacao_evidencia(relacao_id, evidencia_id, papel, trecho_citado, ordem) VALUES(?,?,?,?,?)",
                (rid, eid, papel, trecho_citado, ordem))
    return True


def _achar_relacao(con, de, para, tipo, rotulo, inicio):
    return con.execute("SELECT * FROM relacao WHERE de=? AND para=? AND tipo=? AND rotulo=? AND IFNULL(periodo_inicio,'')=?",
                       (de, para, tipo, rotulo, inicio or "")).fetchone()


def _inserir_relacao_tx(con, d, existente=None):
    """d já validado/normalizado. `existente`: linha já escolhida (dedup por embedding) que substitui a busca pela chave.
    -> (id, 'criada'|'atualizada')."""
    ex = existente or _achar_relacao(con, d["de"], d["para"], d["tipo"], d["rotulo"], d["periodo_inicio"])
    t = agora()
    if ex:
        sets, vals = [], []
        for campo in ("descricao", "subtipo", "periodo_fim", "valor_brl", "valor_texto", "resposta"):
            if d.get(campo) is not None:
                sets.append(f"{campo}=?"); vals.append(d[campo])
        if d.get("natureza_id"):
            sets.append("natureza_id=?"); vals.append(d["natureza_id"])
        if d.get("confianca") is not None:
            sets.append("confianca=?"); vals.append(d["confianca"])
        # nunca rebaixa uma relação já publicada para 'revisar'
        if d.get("status") and not (ex["status"] == "publicada" and d["status"] == "revisar"):
            sets.append("status=?"); vals.append(d["status"])
        if sets:
            sets.append("atualizado_em=?"); vals.append(t)
            con.execute(f"UPDATE relacao SET {', '.join(sets)} WHERE id=?", vals + [ex["id"]])
        return ex["id"], "atualizada"
    cur = con.execute(
        """INSERT INTO relacao(de, para, tipo, subtipo, rotulo, descricao, natureza_id, confianca, periodo_inicio, periodo_fim,
                               valor_brl, valor_texto, resposta, origem, origem_ref, status, criado_em, atualizado_em)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["de"], d["para"], d["tipo"], d.get("subtipo"), d["rotulo"], d.get("descricao"), d["natureza_id"], d.get("confianca"),
         d["periodo_inicio"], d["periodo_fim"], d.get("valor_brl"), d.get("valor_texto"), d.get("resposta"),
         d["origem"], d.get("origem_ref"), d["status"], t, t))
    return cur.lastrowid, "criada"


def _atribuir_temas(con, rid, temas, origem="mcp"):
    """Liga a relação aos temas (só acrescenta; nunca remove). -> temas efetivos da relação."""
    for t in temas:
        con.execute("INSERT OR IGNORE INTO relacao_tema(relacao_id, tema_id, origem, regra) VALUES(?,?,?,NULL)", (rid, t, origem))
    return [x[0] for x in con.execute("SELECT x.tema_id FROM relacao_tema x JOIN tema t ON t.id=x.tema_id WHERE x.relacao_id=? ORDER BY t.ordem, t.id", (rid,))]


def _temas_nova_relacao(con, explicitos, de, para, rotulo, descricao):
    """Temas informados (validados) ou inferidos (curadoria.inferir_temas_relacao; sem nada: 'a-classificar')."""
    if explicitos:
        return _checar_temas(con, explicitos), "informados"
    return CUR.inferir_temas_relacao(con, de, para, rotulo, descricao), "inferidos"


def inserir_relacao_core(de, para, tipo, rotulo, natureza, descricao=None, subtipo=None, periodo_inicio=None, periodo_fim=None,
                         valor_brl=None, valor_texto=None, resposta=None, evidencias=None, origem="manual", status="revisar", temas=None):
    def tx(con):
        _checar_entidade(con, "de", de)
        _checar_entidade(con, "para", para)
        if de == para:
            raise Rejeitado("de e para não podem ser a mesma entidade")
        if tipo not in TIPOS_RELACAO:
            raise Rejeitado(f"tipo '{tipo}' inválido", validos=TIPOS_RELACAO)
        if not rotulo or not str(rotulo).strip():
            raise Rejeitado("rotulo é obrigatório")
        if status not in STATUS_RELACAO:
            raise Rejeitado(f"status '{status}' inválido", validos=STATUS_RELACAO)
        if origem not in ORIGENS_RELACAO:
            raise Rejeitado(f"origem '{origem}' inválida", validos=ORIGENS_RELACAO)
        d = dict(de=de, para=para, tipo=tipo, rotulo=str(rotulo).strip(), natureza_id=natureza_id(con, natureza), descricao=descricao,
                 subtipo=subtipo, periodo_inicio=_periodo_val(periodo_inicio, "periodo_inicio"),
                 periodo_fim=_periodo_val(periodo_fim, "periodo_fim"), valor_brl=valor_brl, valor_texto=valor_texto,
                 resposta=resposta, origem=origem, status=status)
        evs = list(evidencias or [])
        nota, extra, existente = _nota_emb(), {}, None
        if not _achar_relacao(con, d["de"], d["para"], d["tipo"], d["rotulo"], d["periodo_inicio"]):
            sim = _achar_similar(con, d["de"], d["para"], d["tipo"], d["rotulo"], d["periodo_inicio"], nota)
            if sim:
                existente = con.execute("SELECT * FROM relacao WHERE id=?", (sim["id"],)).fetchone()
                extra = {"dedup_por": "embedding", "cos": sim["cos"], "rotulo_enviado": d["rotulo"], "rotulo_existente": sim["rotulo"]}
        rid, acao = _inserir_relacao_tx(con, d, existente)
        novas = 0
        for ev in evs:
            novas += _ligar_evidencia(con, rid, _upsert_evidencia(con, ev), "sustenta")
        if acao == "criada":
            tm, como = _temas_nova_relacao(con, temas, d["de"], d["para"], d["rotulo"], d.get("descricao"))
            extra["temas_" + como] = tm
            efetivos = _atribuir_temas(con, rid, tm)
        else:  # existente: só acrescenta temas pedidos; sem pedido, não mexe
            efetivos = _atribuir_temas(con, rid, _checar_temas(con, temas) if temas else [])
        _emb_gravar(con, nota, {"relacao": [rid], "relacao_rotulo": [rid]})
        return {"acao": acao, "relacao_id": rid, "temas": efetivos, "evidencias_novas_ligadas": novas, **extra, "embeddings": nota}

    return operacao_escrita(tx)


# --------------------------------------------------------------------------- fonte (vídeo, reportagem, documento, PDF, depoimento...)
def _hash_texto(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _normalizar_fonte(v, rotulo="fonte"):
    """dict de entrada -> colunas de `fonte`. `rotulo` ('video'|'fonte') só muda o texto das mensagens."""
    if not isinstance(v, dict):
        raise Rejeitado(f"'{rotulo}' deve ser um objeto")
    tipo = str(v.get("tipo") or "").strip().lower()
    if tipo not in TIPOS_FONTE:
        raise Rejeitado(f"{rotulo}.tipo '{v.get('tipo')}' inválido", validos=TIPOS_FONTE)
    plat = str(v.get("plataforma") or "").strip().lower() or None
    plat = {"yt": "youtube"}.get(plat, plat)
    if plat is not None and plat not in PLATAFORMAS:
        raise Rejeitado(f"{rotulo}.plataforma '{v.get('plataforma')}' inválida", validos=PLATAFORMAS)
    if tipo == "video" and plat is None:
        raise Rejeitado(f"{rotulo}.plataforma é obrigatória para tipo 'video'", validos=PLATAFORMAS)
    fid, url = (v.get("id") or "").strip(), (v.get("url") or "").strip()
    if plat == "youtube":
        if not fid and url:
            u = urlsplit(url)
            yid = (parse_qs(u.query).get("v") or [None])[0] if "youtube" in u.netloc else None
            if "youtu.be" in u.netloc:
                yid = u.path.strip("/").split("/")[0]
            if not yid:
                m = re.search(r"/(?:shorts|embed|live)/([\w-]{6,})", u.path)
                yid = m.group(1) if m else None
            if not yid:
                raise Rejeitado(f"não consegui extrair o id do YouTube de '{url}'; passe {rotulo}.id")
            fid = "yt:" + yid
        elif fid and ":" not in fid:
            fid = "yt:" + fid
        if not url and fid.startswith("yt:"):
            url = "https://www.youtube.com/watch?v=" + fid[3:]
    if tipo == "video" and (not fid or not url):
        raise Rejeitado("video precisa de 'id' e 'url' (para plataformas não-YouTube, ambos)" if plat != "youtube" else "video precisa de 'id' ou 'url'")
    if not v.get("titulo"):
        raise Rejeitado(f"{rotulo}.titulo é obrigatório")
    if not fid:  # fonte sem id: derivado da URL normalizada (ou do título + data, para depoimento/documento sem URL)
        base = normalizar_url(url) if url else f"{tipo}|{v['titulo']}|{v.get('publicado_em') or ''}"
        fid = "src:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    if re.search(r"\s", fid):
        raise Rejeitado(f"{rotulo}.id '{fid}' não pode ter espaços")
    texto = v.get("texto", v.get("transcricao"))  # 'transcricao' = nome antigo de video.transcricao
    texto = texto.strip() if isinstance(texto, str) and texto.strip() else None
    ev_tipo = v.get("evidencia_tipo") or EVIDENCIA_DE_FONTE[tipo]
    if ev_tipo not in TIPOS_EVIDENCIA:
        raise Rejeitado(f"{rotulo}.evidencia_tipo '{ev_tipo}' inválido", validos=TIPOS_EVIDENCIA)
    return dict(id=fid, tipo=tipo, plataforma=plat, url=normalizar_url(url) if url else None, titulo=v["titulo"], canal=v.get("canal"),
                publicado_em=v.get("publicado_em"), duracao_s=int(v["duracao_s"]) if v.get("duracao_s") is not None else None,
                texto=texto, hash_texto=_hash_texto(texto) if texto else None, resumo=v.get("resumo"),
                classificador_versao=v.get("classificador_versao"), evidencia_tipo=ev_tipo, temas=list(v.get("temas") or []))


def _ent_id(x):
    return (x.get("id") if isinstance(x, dict) else x)


def _validar_fonte(con, fonte, trechos, cortes):
    """Valida tudo sem escrever. Rejeita a fonte inteira (entidades desconhecidas listadas com sugestões)."""
    erros, nao_res = [], {}
    eh_video = fonte["tipo"] == "video"

    def ent(eid, onde):
        eid = str(_ent_id(eid) or "").strip()
        if not eid or not _existe(con, eid):
            nao_res.setdefault(eid, []).append(onde)
        return eid

    if not isinstance(trechos, list) or not trechos:
        raise Rejeitado("'trechos' deve ser uma lista não vazia")
    if cortes and not eh_video:
        raise Rejeitado(f"cortes_sugeridos só se aplica a fonte do tipo 'video' (esta é '{fonte['tipo']}')")
    ordens = set()
    for i, t in enumerate(trechos):
        loc = f"trechos[{i}]"
        if not isinstance(t, dict):
            erros.append(f"{loc}: deve ser objeto"); continue
        try:
            o = int(t["ordem"])
            if o in ordens:
                erros.append(f"{loc}: ordem {o} repetida")
            ordens.add(o); t["ordem"] = o
            tem_i, tem_f = t.get("inicio_s") is not None, t.get("fim_s") is not None
            if eh_video and not (tem_i and tem_f):
                erros.append(f"{loc}: inicio_s e fim_s são obrigatórios em fonte do tipo video")
            elif tem_i != tem_f:
                erros.append(f"{loc}: informe inicio_s e fim_s juntos (ou nenhum)")
            if tem_i and tem_f:
                t["inicio_s"], t["fim_s"] = float(t["inicio_s"]), float(t["fim_s"])
                if t["fim_s"] < t["inicio_s"]:
                    erros.append(f"{loc}: fim_s < inicio_s")
            else:
                t["inicio_s"] = t["fim_s"] = None
            if not t.get("afirmacao"):
                erros.append(f"{loc}: afirmacao obrigatória")
            t["_nat"] = natureza_id(con, t.get("natureza"), f"{loc}.natureza")
            c = float(t["confianca"])
            if not 0 <= c <= 1:
                erros.append(f"{loc}: confianca fora de 0..1")
            t["confianca"] = c
            pc = int(t.get("potencial_corte", 0) or 0)
            if not 0 <= pc <= 5:
                erros.append(f"{loc}: potencial_corte fora de 0..5")
            t["potencial_corte"] = pc
            t["_anos"] = sorted({int(a) for a in (t.get("anos_referidos") or [])})
            t["_valores"] = []
            for val in t.get("valores") or []:
                m = MOEDAS.get(str(val.get("moeda") or "BRL").strip().upper(), "outro")
                t["_valores"].append((float(val["valor"]), m, val.get("descricao")))
            t["_ents"] = [ent(e, f"{loc}.entidades") for e in t.get("entidades") or []]
            t["_rels"] = []
            for j, r in enumerate(t.get("relacoes") or []):
                rl = f"{loc}.relacoes[{j}]"
                de, para = ent(r.get("de"), rl + ".de"), ent(r.get("para"), rl + ".para")
                if de and para and de == para:
                    erros.append(f"{rl}: de == para")
                if r.get("tipo") not in TIPOS_RELACAO:
                    erros.append(f"{rl}: tipo '{r.get('tipo')}' inválido (validos: {', '.join(TIPOS_RELACAO)})")
                ini, fim = parse_periodo(r.get("periodo"))
                t["_rels"].append(dict(de=de, para=para, tipo=r.get("tipo"), rotulo=(r.get("rotulo") or "").strip() or None,
                                       periodo_inicio=ini, periodo_fim=fim, temas=list(r.get("temas") or [])))
        except Rejeitado as e:
            erros.append(f"{loc}: {e}")
        except (KeyError, TypeError, ValueError) as e:
            erros.append(f"{loc}: campo ausente/inválido ({type(e).__name__}: {e})")
    for k, c in enumerate(cortes or []):
        loc = f"cortes_sugeridos[{k}]"
        try:
            c["inicio_s"], c["fim_s"] = float(c["inicio_s"]), float(c["fim_s"])
            if c["fim_s"] <= c["inicio_s"]:
                erros.append(f"{loc}: fim_s deve ser > inicio_s")
            if not c.get("titulo"):
                erros.append(f"{loc}: titulo obrigatório")
            for o in c.get("trechos") or []:
                if int(o) not in ordens:
                    erros.append(f"{loc}: trecho de ordem {o} não existe")
            c["_cob"] = []
            for j, r in enumerate(c.get("relacoes_cobertas") or []):
                rl = f"{loc}.relacoes_cobertas[{j}]"
                c["_cob"].append((ent(r.get("de"), rl + ".de"), ent(r.get("para"), rl + ".para"), r.get("tipo")))
        except (KeyError, TypeError, ValueError) as e:
            erros.append(f"{loc}: campo ausente/inválido ({type(e).__name__}: {e})")
    try:
        fonte["temas"] = _checar_temas(con, fonte.get("temas"), f"{'video' if eh_video else 'fonte'}.temas")
        for t in trechos:
            for r in t.get("_rels", []):
                r["temas"] = _checar_temas(con, r.get("temas"), "relacoes[].temas")
    except Rejeitado as e:
        erros.append(str(e))
    if nao_res:
        raise Rejeitado("entidades desconhecidas: a fonte inteira foi rejeitada (nada foi gravado). Peça cadastro ou corrija os ids.",
                        nao_resolvidas=[{"id": k, "usado_em": v, "sugestoes": _sugestoes(con, k) if k else []} for k, v in nao_res.items()],
                        outros_erros=erros)
    if erros:
        raise Rejeitado("entrada inválida; nada foi gravado", erros=erros)


def _escolher_relacao_existente(con, r):
    """Sem rótulo: reutiliza relação (de, para, tipo[, início]) mais antiga, se houver."""
    sql, p = "SELECT id FROM relacao WHERE de=? AND para=? AND tipo=?", [r["de"], r["para"], r["tipo"]]
    if r["periodo_inicio"]:
        sql += " AND periodo_inicio=?"; p.append(r["periodo_inicio"])
    rows = con.execute(sql + " ORDER BY id", p).fetchall()
    return rows[0]["id"] if rows else None, len(rows)


def inserir_fonte_core(fonte, trechos, cortes_sugeridos=None, rotulo="fonte"):
    """Núcleo único de gravação de fonte + trechos (+ cortes, só vídeo). `inserir_video_core` chama isto com tipo='video'."""
    cortes = list(cortes_sugeridos or [])

    def tx(con):
        v = _normalizar_fonte(fonte, rotulo)
        eh_video = v["tipo"] == "video"
        _validar_fonte(con, v, trechos, cortes)
        if v["url"]:
            outro = con.execute("SELECT id FROM fonte WHERE url=? AND id<>?", (v["url"], v["id"])).fetchone()
            if outro:
                raise Rejeitado(f"a url já pertence {'ao vídeo' if eh_video else 'à fonte'} '{outro['id']}'; ids divergentes para a mesma fonte")
        avisos, t0 = [], agora()
        antigo = con.execute("SELECT * FROM fonte WHERE id=?", (v["id"],)).fetchone()
        substituiu = None
        canal_ent = None
        if v["canal"]:
            ca = _candidatos(con, v["canal"])
            ex = [k for k, (s, _) in ca.items() if s >= 90]
            canal_ent = ex[0] if len(ex) == 1 else None
        ev_fonte = None
        if v["url"]:  # toda fonte com URL gera/aponta uma evidência (mesma URL normalizada)
            ev_fonte = _upsert_evidencia(con, {"url": v["url"], "veiculo": v["canal"] or v["plataforma"], "titulo": v["titulo"],
                                               "data": v["publicado_em"], "tipo": v["evidencia_tipo"]})
        if antigo:
            ids_t = [r[0] for r in con.execute("SELECT id FROM trecho WHERE fonte_id=?", (v["id"],))]
            perdidos = [dict(r) for r in con.execute("SELECT id, titulo, status FROM corte WHERE video_id=? AND status<>'sugerido'", (v["id"],))]
            if perdidos:
                avisos.append(f"cortes com status avançado foram substituídos: {perdidos}")
            substituiu = {"trechos": len(ids_t), "cortes": con.execute("SELECT count(*) FROM corte WHERE video_id=?", (v["id"],)).fetchone()[0]}
            con.execute("DELETE FROM corte WHERE video_id=?", (v["id"],))
            con.execute("DELETE FROM trecho WHERE fonte_id=?", (v["id"],))  # cascata: trecho_entidade/ano/valor/relacao, corte_trecho
            status = antigo["status"] if antigo["status"] != "pendente" else "classificado"
            con.execute("""UPDATE fonte SET tipo=?, plataforma=?, url=?, titulo=?, canal=?, canal_entidade_id=?, publicado_em=?, duracao_s=?,
                           texto=COALESCE(?, texto), hash_texto=COALESCE(?, hash_texto), resumo=COALESCE(?, resumo), evidencia_id=?,
                           classificado_em=?, classificador_versao=?, status=? WHERE id=?""",
                        (v["tipo"], v["plataforma"], v["url"], v["titulo"], v["canal"], canal_ent, v["publicado_em"], v["duracao_s"],
                         v["texto"], v["hash_texto"], v["resumo"], ev_fonte, t0, v["classificador_versao"], status, v["id"]))
            con.execute("DELETE FROM busca_fts WHERE origem_tabela='fonte' AND origem_id=?", (v["id"],))  # sincronizar_fts reindexa
        else:
            con.execute("""INSERT INTO fonte(id, tipo, plataforma, url, titulo, canal, canal_entidade_id, publicado_em, duracao_s, texto, hash_texto,
                           resumo, evidencia_id, classificado_em, classificador_versao, status, criado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'classificado',?)""",
                        (v["id"], v["tipo"], v["plataforma"], v["url"], v["titulo"], v["canal"], canal_ent, v["publicado_em"], v["duracao_s"],
                         v["texto"], v["hash_texto"], v["resumo"], ev_fonte, t0, v["classificador_versao"], t0))
        tid_por_ordem, criadas, existentes, rel_por_trecho = {}, [], [], {}
        nota_emb, dedups, temas_rel = _nota_emb(), [], {}
        for t in sorted(trechos, key=lambda x: x["ordem"]):
            cur = con.execute("""INSERT INTO trecho(fonte_id, ordem, inicio_s, fim_s, localizacao, texto_original, afirmacao, natureza_id, confianca, potencial_corte)
                                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (v["id"], t["ordem"], t["inicio_s"], t["fim_s"], t.get("localizacao"), t.get("texto_original"), t["afirmacao"],
                               t["_nat"], t["confianca"], t["potencial_corte"]))
            tid = cur.lastrowid
            tid_por_ordem[t["ordem"]] = tid
            ents = list(t["_ents"])
            for r in t["_rels"]:
                for e in (r["de"], r["para"]):
                    if e not in ents:
                        ents.append(e)
            for e in ents:
                con.execute("INSERT OR IGNORE INTO trecho_entidade(trecho_id, entidade_id) VALUES(?,?)", (tid, e))
            for a in t["_anos"]:
                con.execute("INSERT INTO trecho_ano(trecho_id, ano) VALUES(?,?)", (tid, a))
            for val, moeda, desc in t["_valores"]:
                con.execute("INSERT INTO trecho_valor(trecho_id, valor, moeda, descricao) VALUES(?,?,?,?)", (tid, val, moeda, desc))
            rel_por_trecho[t["ordem"]] = []
            for r in t["_rels"]:
                rid = None
                pedidos = r["temas"] or v["temas"]  # tema da relação > tema da fonte > inferido
                if r["rotulo"] is None:
                    rid, n = _escolher_relacao_existente(con, r)
                    if n > 1:
                        avisos.append(f"trecho {t['ordem']}: {n} relações ({r['de']}->{r['para']}, {r['tipo']}) sem rótulo; usada a de menor id ({rid})")
                    if rid is None:
                        r["rotulo"] = f"Relação {r['tipo']} (a revisar)"
                if rid is None:
                    novo = dict(de=r["de"], para=r["para"], tipo=r["tipo"], rotulo=r["rotulo"], natureza_id=t["_nat"],
                                confianca=t["confianca"], periodo_inicio=r["periodo_inicio"], periodo_fim=r["periodo_fim"],
                                origem="classificador", origem_ref=f"trecho:{tid}", status="revisar")
                    ex = _achar_relacao(con, r["de"], r["para"], r["tipo"], r["rotulo"], r["periodo_inicio"])
                    if not ex:
                        sim = _achar_similar(con, r["de"], r["para"], r["tipo"], r["rotulo"], r["periodo_inicio"], nota_emb)
                        if sim:
                            ex = con.execute("SELECT * FROM relacao WHERE id=?", (sim["id"],)).fetchone()
                            dedups.append({"trecho": t["ordem"], "dedup_por": "embedding", "cos": sim["cos"], "relacao_id": sim["id"],
                                           "rotulo_enviado": r["rotulo"], "rotulo_existente": sim["rotulo"]})
                    if ex:  # existente: não altera natureza/status/confiança (decisão editorial já tomada); só completa fim do período
                        rid = ex["id"]
                        if r["periodo_fim"] and not ex["periodo_fim"]:
                            con.execute("UPDATE relacao SET periodo_fim=?, atualizado_em=? WHERE id=?", (r["periodo_fim"], agora(), rid))
                        existentes.append(rid)
                    else:
                        rid, _ = _inserir_relacao_tx(con, novo)
                        criadas.append(rid)
                        tm = pedidos or CUR.inferir_temas_relacao(con, r["de"], r["para"], r["rotulo"], None)
                        temas_rel[rid] = _atribuir_temas(con, rid, tm)
                        _emb_gravar(con, nota_emb, {"relacao": [rid], "relacao_rotulo": [rid]})  # já vale para o dedup dos próximos trechos
                        if ev_fonte:
                            _ligar_evidencia(con, rid, ev_fonte, "sustenta", t["afirmacao"])
                        else:
                            avisos.append(f"relação {rid} criada sem evidência: a fonte não tem URL")
                else:
                    existentes.append(rid)
                if rid in existentes and pedidos and r["temas"]:  # tema pedido explicitamente numa relação reaproveitada: só acrescenta
                    temas_rel[rid] = _atribuir_temas(con, rid, pedidos)
                con.execute("INSERT OR IGNORE INTO trecho_relacao(trecho_id, relacao_id, papel) VALUES(?,?,'afirma')", (tid, rid))
                rel_por_trecho[t["ordem"]].append(rid)
        n_cortes = 0
        for c in cortes:
            ordens = [int(o) for o in (c.get("trechos") or [])]
            if not ordens:  # sem lista: trechos totalmente contidos no corte
                ordens = [t["ordem"] for t in trechos if t["inicio_s"] >= c["inicio_s"] and t["fim_s"] <= c["fim_s"]]
            cur = con.execute("""INSERT INTO corte(video_id, titulo, inicio_s, fim_s, justificativa, tema, status, criado_em)
                                 VALUES(?,?,?,?,?,?,'sugerido',?)""", (v["id"], c["titulo"], c["inicio_s"], c["fim_s"], c.get("justificativa"), c.get("tema"), t0))
            cid = cur.lastrowid
            n_cortes += 1
            for o in ordens:
                con.execute("INSERT OR IGNORE INTO corte_trecho(corte_id, trecho_id) VALUES(?,?)", (cid, tid_por_ordem[o]))
            for de, para, tipo in c["_cob"]:
                vinculadas = {rid for rids in rel_por_trecho.values() for rid in rids}
                rows = [r["id"] for r in con.execute("SELECT id FROM relacao WHERE de=? AND para=? AND tipo=? ORDER BY id", (de, para, tipo))]
                alvo = [r for r in rows if r in vinculadas] or rows
                if not alvo:
                    avisos.append(f"corte '{c['titulo']}': relacao coberta {de}->{para} ({tipo}) não existe; ignorada")
                for rid in alvo:
                    con.execute("INSERT OR IGNORE INTO relacao_corte(relacao_id, corte_id) VALUES(?,?)", (rid, cid))
        if EMB is not None:
            EMB.limpar_orfaos(con)  # trechos antigos apagados na reinserção
        _emb_gravar(con, nota_emb, {"trecho": list(tid_por_ordem.values()), "evidencia": [ev_fonte] if ev_fonte else []})
        out = {"fonte_id": v["id"], "tipo": v["tipo"], "evidencia_id": ev_fonte, "trechos": len(trechos), "cortes": n_cortes,
               "relacoes_criadas": sorted(set(criadas)),
               "relacoes_existentes_reutilizadas": sorted(set(existentes) - set(criadas)), "temas_das_relacoes_criadas": temas_rel,
               "dedup": dedups, "substituiu_insercao_anterior": substituiu, "avisos": avisos, "embeddings": nota_emb}
        if eh_video:
            out["video_id"] = v["id"]  # nome antigo (compatibilidade)
        return out

    return operacao_escrita(tx)


def inserir_video_core(video, trechos, cortes_sugeridos=None):
    """Atalho: grava como fonte tipo='video' (aceita 'transcricao' como nome antigo de 'texto')."""
    if not isinstance(video, dict):
        return Rejeitado("'video' deve ser um objeto").payload
    return inserir_fonte_core({**video, "tipo": "video"}, trechos, cortes_sugeridos, rotulo="video")


# --------------------------------------------------------------------------- RAG (embeddings)
def _nota_emb():
    return {"status": "ok", "gerados": {}}


def _emb_gravar(con, nota, ids_por_tabela):
    """Gera embeddings das linhas novas/alteradas dentro da transação. Sem provedor: pula e anota (nada falha)."""
    if nota.get("status") != "ok":
        return
    if EMB is None:
        nota.update(status="ignorado", motivo=f"numpy/embeddings indisponível: {_EMB_ERRO}")
        return
    try:
        for t, ids in ids_por_tabela.items():
            s = EMB.atualizar(con, t, ids)
            g = nota["gerados"].setdefault(t, 0)
            nota["gerados"][t] = g + s["novos"] + s["atualizados"]
        nota["modelo"] = EMB.provedor_ativo()["modelo"]
    except sqlite3.Error:
        raise
    except Exception as e:  # provedor fora do ar, sem chave, etc.
        nota.update(status="ignorado", motivo=f"{type(e).__name__}: {e}; embeddings não gerados (rode scripts/embeddings.py depois)")


def _achar_similar(con, de, para, tipo, rotulo, periodo_inicio, nota):
    """Relação existente no MESMO (de, para, tipo) com cosseno(rótulo) >= limiar de dedup e período compatível. -> dict|None."""
    if EMB is None or os.environ.get("LDT_DEDUP_EMBEDDING") == "0" or nota.get("status") != "ok":
        return None
    try:
        rows = con.execute("SELECT id, rotulo, periodo_inicio FROM relacao WHERE de=? AND para=? AND tipo=?", (de, para, tipo)).fetchall()
        if not rows:
            return None
        vs = EMB.vetores_de(con, "relacao_rotulo", [r["id"] for r in rows])
        q = np_vec(EMB.embed([str(rotulo)], "query")[0])
        _, lim = EMB.limiares()
        melhor = None
        for r in rows:
            if periodo_inicio and r["periodo_inicio"] and r["periodo_inicio"][:4] != str(periodo_inicio)[:4]:
                continue  # períodos diferentes = relações diferentes
            v = vs.get(str(r["id"]))
            if v is None:
                continue
            c = float(v @ q)
            if c >= lim and (melhor is None or c > melhor["cos"]):
                melhor = {"id": r["id"], "rotulo": r["rotulo"], "cos": round(c, 4)}
        return melhor
    except sqlite3.Error:
        raise
    except Exception as e:
        nota.update(status="ignorado", motivo=f"dedup por embedding pulado: {type(e).__name__}: {e}")
        return None


def np_vec(v):
    import numpy as np
    return np.asarray(v, dtype=np.float32)


_STOP = {"de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "no", "na", "nos", "nas", "ao", "aos", "um", "uma", "por",
         "para", "com", "que", "se", "ou"}


def _fts_or(texto):
    toks = [t for t in re.findall(r"\w+", texto, flags=re.UNICODE) if len(t) > 1 and t.lower() not in _STOP]
    return " OR ".join('"' + t.replace('"', '') + '"' for t in toks) or None


def _resumo_hit(con, tabela, oid):
    """-> (titulo, trecho, extra) legível da linha de origem."""
    cut = lambda s, n=260: (s or "")[:n] + ("…" if s and len(s) > n else "")
    if tabela == "relacao":
        r = con.execute("SELECT r.*, d.nome dn, p.nome pn FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para WHERE r.id=?", (oid,)).fetchone()
        return (f"{r['rotulo']} ({r['dn']} → {r['pn']})", cut(r["descricao"]), {"de": r["de"], "para": r["para"], "tipo": r["tipo"], "status": r["status"]}) if r else None
    if tabela == "entidade":
        r = con.execute("SELECT * FROM entidade WHERE id=?", (oid,)).fetchone()
        return (r["nome"], cut(r["descricao"]), {"tipo": r["tipo"]}) if r else None
    if tabela == "evento":
        r = con.execute("SELECT * FROM evento WHERE id=?", (oid,)).fetchone()
        return (r["titulo"], cut(r["descricao"]), {"data": r["data"]}) if r else None
    if tabela == "evidencia":
        r = con.execute("SELECT * FROM evidencia WHERE id=?", (oid,)).fetchone()
        return (r["titulo"] or r["veiculo"], cut(r["resumo"] or r["url"]), {"url": r["url"], "veiculo": r["veiculo"]}) if r else None
    if tabela == "trecho":
        r = con.execute("SELECT t.*, f.titulo vt, f.url vu, f.tipo ft FROM trecho t JOIN fonte f ON f.id=t.fonte_id WHERE t.id=?", (oid,)).fetchone()
        return (f"{r['vt']} #{r['ordem']}" + (f" ({r['inicio_s']:.0f}s)" if r["inicio_s"] is not None else ""), cut(r["afirmacao"]),
                {"fonte_id": r["fonte_id"], "fonte_tipo": r["ft"], "video_id": r["fonte_id"], "video_url": r["vu"], "fonte_url": r["vu"]}) if r else None
    if tabela == "nota":
        r = con.execute("SELECT * FROM nota WHERE id=?", (oid,)).fetchone()
        return (r["titulo"] or r["tipo"], cut(r["texto"]), {"pagina": r["pagina"]}) if r else None
    return None


def buscar_semantica_core(texto, tabelas=None, limite=20, k_fts=50):
    if not texto or not str(texto).strip():
        raise Rejeitado("texto vazio")
    if EMB is None:
        raise Rejeitado(f"RAG indisponível (numpy ausente?): {_EMB_ERRO}")
    tabelas = list(tabelas) if tabelas else list(EMB.TABELAS_PADRAO)
    ruins = [t for t in tabelas if t not in EMB.TABELAS_PADRAO + ["nota"]]
    if ruins:
        raise Rejeitado(f"tabelas inválidas: {ruins}", validas=EMB.TABELAS_PADRAO + ["nota"])
    limite, k_fts = max(1, int(limite)), max(1, int(k_fts))
    avisos = []
    if "trecho" in tabelas:
        with leitura() as con:
            defasado = _fts_trechos_defasado(con)
        if defasado:
            with escrita() as (con, _):
                sincronizar_fts(con)
    with leitura() as con:
        fts = {}
        expr = _fts_or(texto)
        if expr:
            ph = ",".join("?" * len(tabelas))
            try:
                for i, r in enumerate(con.execute(
                        f"SELECT origem_tabela, origem_id FROM busca_fts WHERE origem_tabela IN ({ph}) AND busca_fts MATCH ? ORDER BY rank LIMIT ?",
                        [*tabelas, expr, k_fts])):
                    fts[(r[0], r[1])] = i + 1
            except sqlite3.OperationalError as e:
                avisos.append(f"FTS falhou: {e}")
        info = EMB.provedor_ativo()
        vec, cos = {}, {}
        if info["disponivel"]:
            try:
                q = EMB.embed([str(texto)], "query")[0]
                for i, (t, oid, c) in enumerate(EMB.top_k(con, q, tabelas, k_fts, info["modelo"])):
                    vec[(t, oid)], cos[(t, oid)] = i + 1, c
                if not vec:
                    avisos.append(f"sem embeddings do modelo {info['modelo']} nessas tabelas: só FTS. Rode scripts/embeddings.py")
            except Exception as e:
                avisos.append(f"busca vetorial indisponível ({type(e).__name__}: {e}); só FTS")
        else:
            avisos.append(f"provedor de embedding indisponível ({info.get('motivo')}); só FTS")
        RRF_K = 60
        chaves = set(fts) | set(vec)
        pont = {k: (1 / (RRF_K + fts[k]) if k in fts else 0) + (1 / (RRF_K + vec[k]) if k in vec else 0) for k in chaves}
        out = []
        for k in sorted(chaves, key=lambda k: (-pont[k], k))[:limite]:
            h = _resumo_hit(con, *k)
            if not h:
                continue
            out.append({"origem_tabela": k[0], "origem_id": k[1], "titulo": h[0], "trecho": h[1], "score": round(pont[k], 5),
                        "cos": round(cos[k], 4) if k in cos else None, "rank_fts": fts.get(k), "rank_vetorial": vec.get(k), **h[2]})
        return {"ok": True, "provedor": info.get("modelo"), "metodo": "rrf(fts5, vetorial)" if vec else "fts5", "avisos": avisos,
                "n_candidatos": len(chaves), "resultados": out}


def relacoes_similares_core(rotulo, de=None, para=None, limite=10, cos_min=None, tipo=None):
    if not rotulo or not str(rotulo).strip():
        raise Rejeitado("rotulo é obrigatório")
    if EMB is None:
        raise Rejeitado(f"RAG indisponível (numpy ausente?): {_EMB_ERRO}")
    info = EMB.provedor_ativo()
    if not info["disponivel"]:
        raise Rejeitado(f"provedor de embedding indisponível: {info.get('motivo')}")
    smin, sdedup = EMB.limiares()
    cos_min = smin if cos_min is None else float(cos_min)
    with leitura() as con:
        d = _resolver_ref(con, de, "de") if de else None
        p = _resolver_ref(con, para, "para") if para else None
        w, a = [], []
        if d and p:
            w.append("((de=? AND para=?) OR (de=? AND para=?))"); a += [d, p, p, d]
        elif d or p:
            w.append("(de=? OR para=?)"); a += [d or p, d or p]
        if tipo:
            w.append("tipo=?"); a.append(tipo)
        rows = con.execute("SELECT * FROM relacao" + (" WHERE " + " AND ".join(w) if w else "") + " ORDER BY id", a).fetchall()
        avisos = []
        if not (d or p) and len(rows) > 2000:
            raise Rejeitado("informe de e/ou para para restringir a busca")
        vs = EMB.vetores_de(con, "relacao_rotulo", [r["id"] for r in rows], info["modelo"])
        q = np_vec(EMB.embed([str(rotulo)], "query")[0])
        cand = []
        for r in rows:
            v = vs.get(str(r["id"]))
            if v is None:
                continue
            c = float(v @ q)
            if c >= cos_min:
                cand.append((c, r))
        cand.sort(key=lambda x: (-x[0], x[1]["id"]))
        out = []
        for c, r in cand[:max(1, int(limite))]:
            nm = lambda i: con.execute("SELECT nome FROM entidade WHERE id=?", (i,)).fetchone()[0]
            out.append({"id": r["id"], "de": {"id": r["de"], "nome": nm(r["de"])}, "para": {"id": r["para"], "nome": nm(r["para"])},
                        "tipo": r["tipo"], "rotulo": r["rotulo"], "descricao": (r["descricao"] or "")[:200], "natureza": r["natureza_id"],
                        "status": r["status"], "periodo_inicio": r["periodo_inicio"], "periodo_fim": r["periodo_fim"], "cos": round(c, 4),
                        "invertida": bool(d and p and r["de"] == p and r["para"] == d),
                        "reutilizaria_na_insercao": bool(c >= sdedup and (not d or r["de"] == d) and (not p or r["para"] == p)
                                                         and (not tipo or r["tipo"] == tipo))})
        return {"ok": True, "modelo": info["modelo"], "limiar_cos": cos_min, "limiar_dedup": sdedup, "avisos": avisos,
                "n_relacoes_comparadas": len(rows), "similares": out}


# --------------------------------------------------------------------------- extras
def resumo_banco_core():
    with leitura() as con:
        tabelas = ["entidade", "entidade_alias", "relacao", "evidencia", "evento", "fonte", "video", "trecho", "corte", "nota", "serie", "tema"]
        out = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tabelas}  # video = view (fontes tipo video)
        out["fonte_por_tipo"] = {r[0]: r[1] for r in con.execute("SELECT tipo, count(*) FROM fonte GROUP BY tipo")}
        out["relacao_por_tema"] = {r[0]: r[1] for r in con.execute("SELECT tema_id, count(*) FROM relacao_tema GROUP BY tema_id ORDER BY tema_id")}
        out["evento_por_tema"] = {r[0]: r[1] for r in con.execute("SELECT tema_id, count(*) FROM evento_tema GROUP BY tema_id ORDER BY tema_id")}
        out["relacao_por_status"] = {r[0]: r[1] for r in con.execute("SELECT status, count(*) FROM relacao GROUP BY status")}
        out["relacao_por_origem"] = {r[0]: r[1] for r in con.execute("SELECT origem, count(*) FROM relacao GROUP BY origem")}
        out["relacao_por_natureza"] = {r[0]: r[1] for r in con.execute("SELECT natureza_id, count(*) FROM relacao GROUP BY natureza_id")}
        out["corte_por_status"] = {r[0]: r[1] for r in con.execute("SELECT status, count(*) FROM corte GROUP BY status")}
        out["banco"] = str(caminho_db())
        return out


def listar_temas_core():
    with leitura() as con:
        ents = {r[0]: r[1] for r in con.execute("SELECT tema_id, count(*) FROM v_entidade_tema GROUP BY tema_id")}
        rels = {r[0]: r[1] for r in con.execute("SELECT tema_id, count(*) FROM relacao_tema GROUP BY tema_id")}
        evs = {r[0]: r[1] for r in con.execute("SELECT tema_id, count(*) FROM evento_tema GROUP BY tema_id")}
        return [{"id": t["id"], "nome": t["nome"], "descricao": t["descricao"], "principal": bool(t["principal"]),
                 "n_relacoes": rels.get(t["id"], 0), "n_eventos": evs.get(t["id"], 0), "n_entidades": ents.get(t["id"], 0)}
                for t in con.execute("SELECT * FROM tema ORDER BY ordem, id")]


def exportar_core():
    """Dump + exportar_json + validar. Só faz sentido com o banco/dumps reais (os scripts gravam em data/)."""
    with _trava_thread:
        with open(caminho_db().with_name(".mcp-escrita.lock"), "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                db = str(caminho_db())
                ex = _rodar([sys.executable, str(RAIZ / "scripts" / "exportar_json.py"), "--db", db])
                va = _rodar([sys.executable, str(RAIZ / "scripts" / "validar.py"), "--db", db])
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    return {"ok": ex["codigo"] == 0 and va["codigo"] == 0, "exportar_json": ex, "validar": va,
            "commit_git": "manual (git add data/ && git commit)"}


# --------------------------------------------------------------------------- ferramentas MCP
def buscar_entidade(consulta: str, tipo: str | None = None, limite: int = 20) -> list[dict]:
    """Resolve uma entidade por slug exato, alias/nome normalizado (sem acento, minúsculo), palavras inteiras do alias/nome ou busca
    textual FTS5 (nome/cargo/descrição/aliases). Ordena por força do casamento e nº de relações. Nunca cria entidade.
    Retorna: id, nome, tipo, categoria, cargo, descricao (curta), aliases, n_relacoes, casou_por."""
    with leitura() as con:
        return buscar_entidade_core(con, consulta, tipo, limite)


def buscar_relacoes(entidade: str | None = None, de: str | None = None, para: str | None = None, tipo: str | None = None,
                    natureza: str | None = None, ano_inicio: int | None = None, ano_fim: int | None = None,
                    status: str | None = None, limite: int = 50, tema: str | None = None) -> list[dict] | dict:
    """Relações com evidências (url, veiculo, ...) e cortes ligados. `entidade` casa de OU para; `de`/`para` aceitam id ou alias exato.
    `natureza` aceita qualquer vocabulário (doc/inv/rep/ale/nc, fato_documentado/alegacao/opiniao, ou canônico).
    ano_inicio/ano_fim filtram por sobreposição de período (relação sem fim conta como pontual). `tema`: slug de tema (ver listar_temas);
    cada relação volta com `temas`."""
    try:
        with leitura() as con:
            return buscar_relacoes_core(con, entidade, de, para, tipo, natureza, ano_inicio, ano_fim, status, limite, tema)
    except Rejeitado as r:
        return r.payload


def buscar_trechos(texto: str | None = None, entidade: str | None = None, video: str | None = None, natureza: str | None = None,
                   limite: int = 50, fonte: str | None = None, tipo: str | None = None) -> list[dict] | dict:
    """Trechos de qualquer fonte (FTS em afirmação+texto original, mais filtros) com entidades, anos, valores, relações e cortes do trecho.
    `fonte` = id ou URL de uma fonte; `tipo` = tipo da fonte (video, reportagem, documento, pdf, depoimento, decisao, transcricao, outro);
    `video` = id/URL de uma fonte tipo video (nome antigo, continua valendo)."""
    try:
        if texto:
            with leitura() as con:
                defasado = _fts_trechos_defasado(con)
            if defasado:  # ex.: banco recém-importado do dump; busca_fts não traz trechos
                with escrita() as (con, _):
                    sincronizar_fts(con)
        with leitura() as con:
            return buscar_trechos_core(con, texto, entidade, video, natureza, limite, fonte, tipo)
    except Rejeitado as r:
        return r.payload


def inserir_relacao(de: str, para: str, tipo: str, rotulo: str, natureza: str, descricao: str | None = None,
                    subtipo: str | None = None, periodo_inicio: str | None = None, periodo_fim: str | None = None,
                    valor_brl: float | None = None, valor_texto: str | None = None, resposta: str | None = None,
                    evidencias: list[dict] | None = None, origem: str = "manual", status: str = "revisar",
                    temas: list[str] | None = None) -> dict:
    """Cria ou atualiza (upsert por de+para+tipo+rotulo+periodo_inicio) uma relação. `de`/`para` devem ser ids existentes (senão erro com
    sugestões; nunca cria entidade). `natureza` aceita doc/inv/rep/ale/nc, fato_documentado/alegacao/opiniao ou canônico.
    `evidencias`: [{url, veiculo?, titulo?, data?, tipo?}], upsert por URL normalizada. Uma única transação; regrava data/dump.sql.
    Não rebaixa relação 'publicada' para 'revisar'. `temas`: slugs de tema (ver listar_temas); sem eles, uma relação nova recebe os temas
    principais comuns às duas entidades + as regras por entidade/texto de data/curadoria/temas.json (resposta traz temas_inferidos);
    numa relação existente só acrescenta."""
    return inserir_relacao_core(de, para, tipo, rotulo, natureza, descricao, subtipo, periodo_inicio, periodo_fim, valor_brl,
                                valor_texto, resposta, evidencias, origem, status, temas)


def inserir_fonte(fonte: dict, trechos: list[dict], cortes_sugeridos: list[dict] | None = None) -> dict:
    """Grava uma fonte de qualquer tipo (video, reportagem, documento, pdf, depoimento, decisao, transcricao, outro) e seus trechos em UMA
    transação: fonte (com evidência quando há URL), trechos, entidades/anos/valores, relações em upsert (origem='classificador', status='revisar',
    com tema), cortes (só tipo video). Entidades desconhecidas: rejeita a fonte inteira e lista sugestões. Idempotente por fonte.id.
    `fonte`: {tipo, titulo, url?, id?, plataforma? (obrigatória p/ video), canal?, publicado_em?, duracao_s?, texto?, resumo?, temas?, evidencia_tipo?}.
    Trechos de fonte sem tempo usam `localizacao` (página, parágrafo) no lugar de inicio_s/fim_s. Contrato completo em mcp/README.md."""
    return inserir_fonte_core(fonte, trechos, cortes_sugeridos)


def inserir_video(video: dict, trechos: list[dict], cortes_sugeridos: list[dict] | None = None) -> dict:
    """Atalho de inserir_fonte com tipo='video' (contrato do classificador de vídeos: 'transcricao' = texto da fonte). Grava a saída do
    classificador em UMA transação (fonte, trechos, entidades/anos/valores, relações em upsert com origem='classificador' e status='revisar',
    cortes). Entidades desconhecidas: rejeita o vídeo inteiro e lista sugestões. Idempotente por video.id: reinserir substitui trechos e
    cortes anteriores sem duplicar relações. Contrato completo em mcp/README.md."""
    return inserir_video_core(video, trechos, cortes_sugeridos)


def listar_temas() -> list[dict]:
    """Temas (id, nome, descrição, principal) com contagem de relações, eventos e entidades. Use os ids em `temas` de inserir_relacao/inserir_fonte
    e no filtro `tema` de buscar_relacoes. Este servidor nunca cria temas (ficam em data/curadoria/temas.json)."""
    return listar_temas_core()


def buscar_semantica(texto: str, tabelas: list[str] | None = None, limite: int = 20, k_fts: int = 50) -> dict:
    """Busca híbrida: candidatos do FTS5 (busca_fts) ∪ top-k vetorial (embeddings), reordenados por RRF (1/(60+rank) somado).
    `tabelas` ⊂ trecho, evidencia, relacao, evento, entidade (+nota, só FTS); padrão: as cinco. Retorna origem_tabela, origem_id, titulo,
    trecho, score (RRF) e cos/rank_fts/rank_vetorial. Sem provedor de embedding ou sem vetores, cai para só FTS e diz em `avisos`.
    Qualidade depende do provedor (o fallback 'hash' é lexical; ver mcp/README.md)."""
    try:
        return buscar_semantica_core(texto, tabelas, limite, k_fts)
    except Rejeitado as r:
        return r.payload


def relacoes_similares(rotulo: str, de: str | None = None, para: str | None = None, limite: int = 10, cos_min: float | None = None,
                       tipo: str | None = None) -> dict:
    """Relações existentes com rótulo semanticamente próximo (cosseno >= cos_min; padrão 0,80 com modelo real, 0,45 no fallback hash).
    Com `de` e `para`: só o mesmo par (qualquer direção; `invertida` avisa). `reutilizaria_na_insercao`=true quando inserir_relacao/inserir_video
    reutilizariam essa relação (mesmo de,para,tipo na mesma direção e cosseno >= limiar de dedup, 0,90 / 0,60 hash). Use antes de inserir
    para evitar duplicatas."""
    try:
        return relacoes_similares_core(rotulo, de, para, limite, cos_min, tipo)
    except Rejeitado as r:
        return r.payload


def resumo_banco() -> dict:
    """Contagens do banco (entidades, relações por status/origem/natureza, vídeos, trechos, cortes...)."""
    return resumo_banco_core()


def exportar() -> dict:
    """Roda scripts/exportar_json.py (JSONs + dump) e scripts/validar.py e devolve a saída. Commit no git continua manual."""
    return exportar_core()


def criar_servidor():
    srv = _Server("linha-do-tempo", instructions=(
        "Banco da Linha do Tempo política brasileira. Este servidor é o único escritor do SQLite. Nunca cria entidades: "
        "use buscar_entidade antes de inserir (e listar_temas para os temas). Relações novas entram com status 'revisar'. "
        "inserir_fonte grava qualquer tipo de fonte (vídeo, reportagem, documento...); inserir_video é o atalho para vídeos."))
    for f in (buscar_entidade, buscar_relacoes, buscar_trechos, buscar_semantica, relacoes_similares, inserir_relacao, inserir_fonte,
              inserir_video, listar_temas, resumo_banco, exportar):
        srv.tool()(f)
    return srv


def preparar():
    """Na subida: falha cedo se o banco não existe e sincroniza busca_fts (trechos/relações) sem regravar o dump."""
    con = abrir()
    try:
        con.execute("SELECT 1 FROM entidade LIMIT 1")
        con.execute("BEGIN IMMEDIATE")
        sincronizar_fts(con)
        if EMB is not None:
            EMB.garantir_schema(con)  # tabela `embedding` (derivada; não entra no dump). Vazia até rodar scripts/embeddings.py
        con.execute("COMMIT")
    finally:
        con.close()


import extracao as _extracao; _extracao.registrar(sys.modules[__name__])  # ferramenta `ingerir` (mcp/extracao.py)
import revisao as _revisao; _revisao.registrar(sys.modules[__name__])  # fila de revisão (mcp/revisao.py)


if __name__ == "__main__":
    preparar()
    criar_servidor().run("stdio")
