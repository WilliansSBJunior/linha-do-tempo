#!/usr/bin/env python3
"""Fila de revisão da Linha do Tempo: lista o que entrou automático e grava as decisões humanas.

Registrado no servidor MCP por UMA linha no fim de server.py (`revisao.registrar(sys.modules[__name__])`); também usado por
scripts/servir_revisao.py (página local) e scripts/aplicar_decisoes.py (reaplica as decisões depois de migrar.py).

Cada decisão:
  1. aplica no sqlite numa transação (mesmo lock/flock/BEGIN IMMEDIATE das outras escritas do servidor) e regrava data/dump.sql;
  2. guarda em `revisao_log` (tabela só do sqlite, fora do dump) as linhas antes/depois, para `desfazer`;
  3. APPENDA uma linha em data/curadoria/decisoes.jsonl {id, quando, tipo, alvo, acao, campos, motivo}: é isso que sobrevive a uma
     remigração (migrar.py recria o banco do zero; scripts/aplicar_decisoes.py reaplica o jsonl, idempotente).
  Fusão de evento grava também em data/curadoria/eventos-fusoes.json (é o que migrar.py e validar.py leem).

`alvo` guarda o id E uma chave natural (relação: de, para, tipo, rótulo, início; corte: vídeo, início, fim, título), porque ids
inteiros de relação/corte mudam numa remigração ou numa reinserção de vídeo.

Variáveis de ambiente: as do server.py (LDT_DB, LDT_DUMP...) e
  LDT_CURADORIA  pasta de curadoria (padrão: <pasta do banco>/curadoria, ou seja data/curadoria)
  LDT_DECISOES   arquivo de decisões (padrão: <curadoria>/decisoes.jsonl)
"""
import contextlib
import json
import os
import re
import secrets
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

_S = None  # módulo server (o que está rodando: '__main__' quando server.py é o processo)

TIPOS_PENDENCIA = ["relacao", "corte", "evento_natureza", "evento_fusao", "entidade"]
ACOES_RELACAO = ["aprovar", "descartar", "fundir_em", "editar"]
ACOES_CORTE = ["aprovar", "descartar", "editar"]
ACOES_EVENTO = ["natureza", "fundir_em", "editar", "manter_separados"]
STATUS_CORTE = {"aprovar": "aprovado", "descartar": "descartado"}
CANAIS_SEM_NATUREZA_POR_DESENHO = ("brasil", "violencia")  # timeline e marcos legais nunca tiveram natureza (relatorio-migracao.md §2)
CAMPOS_REL = ["rotulo", "descricao", "tipo", "subtipo", "natureza", "confianca", "periodo_inicio", "periodo_fim", "valor_brl",
              "valor_texto", "resposta", "de", "para", "temas"]
CAMPOS_EVENTO = ["titulo", "descricao", "data", "data_aprox", "data_texto", "peso", "contexto", "resposta", "valor_brl", "natureza", "temas"]
CAMPOS_CORTE = ["titulo", "inicio_s", "fim_s", "justificativa", "tema", "url_publicado"]


def registrar(server_mod):
    """Chamada por UMA linha no fim de server.py: guarda o módulo e embrulha criar_servidor para registrar as ferramentas de revisão."""
    global _S
    _S = server_mod
    if getattr(server_mod.criar_servidor, "_com_revisao", False):
        return
    original = server_mod.criar_servidor

    def criar_servidor():
        srv = original()
        for f in FERRAMENTAS:
            srv.tool()(f)
        return srv

    criar_servidor._com_revisao = True
    server_mod.criar_servidor = criar_servidor


def S():
    global _S
    if _S is None:
        import server  # noqa: F401  (o fim de server.py chama registrar(), que preenche _S)
        if _S is None:
            _S = server
    return _S


class _NadaMudou(Exception):
    def __init__(self, res):
        super().__init__("nada mudou")
        self.res = res


def _rej(msg, **extra):
    return S().Rejeitado(msg, **extra)


# --------------------------------------------------------------------------- caminhos e arquivos
def pasta_curadoria():
    return Path(os.environ.get("LDT_CURADORIA") or (S().caminho_db().parent / "curadoria"))


def caminho_decisoes():
    return Path(os.environ.get("LDT_DECISOES") or (pasta_curadoria() / "decisoes.jsonl"))


def _ler_curadoria(nome):
    """Lê da pasta de curadoria do banco; se não houver (ex.: banco temporário), da do repo (só leitura)."""
    for p in (pasta_curadoria() / nome, RAIZ / "data" / "curadoria" / nome):
        if p.exists():
            return p
    return None


class _Arquivos:
    """Escritas em arquivo que acompanham a transação: se ela não for confirmada, `restaurar()` devolve o conteúdo anterior."""

    def __init__(self):
        self.orig = {}

    def _guardar(self, p):
        if p not in self.orig:
            self.orig[p] = p.read_bytes() if p.exists() else None

    def escrever(self, p, texto):
        p = Path(p)
        self._guardar(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, p)

    def anexar(self, p, linha):
        p = Path(p)
        self._guardar(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(linha.rstrip("\n") + "\n")
            f.flush()
            os.fsync(f.fileno())

    def restaurar(self):
        for p, b in self.orig.items():
            if b is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(b)
        self.orig.clear()


def ler_decisoes(caminho=None):
    p = Path(caminho) if caminho else caminho_decisoes()
    if not p.exists():
        return []
    out = []
    for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if linha.strip():
            try:
                out.append(json.loads(linha))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{n}: linha inválida ({e})")
    return out


def desfeitas(decisoes):
    return {d["alvo"]["id"] for d in decisoes if d.get("tipo") == "desfazer"}


# eventos-fusoes.json: mesmo formato do arquivo escrito à mão (uma fusão por item, "motivo" na linha seguinte)
def _fmt_fusoes(lista):
    out = []
    for f in lista:
        m, fu, mo = (json.dumps(f[k], ensure_ascii=False) for k in ("manter", "fundir", "motivo"))
        cab = ' {"manter": %s, "fundir": %s,' % (m, fu)
        if len(cab) > 200:
            cab = ' {"manter": %s,\n  "fundir": %s,' % (m, fu)
        out.append(cab + '\n  "motivo": %s}' % mo)
    return "[\n" + ",\n".join(out) + "\n]\n"


# --------------------------------------------------------------------------- log para desfazer (gatilhos TEMP por conexão)
_COLS = {}
_TABELAS_LOG = None


def _tabelas_log():
    global _TABELAS_LOG
    if _TABELAS_LOG is None:
        from comum import TABELAS
        _TABELAS_LOG = [t for t in TABELAS if t not in ("meta", "indicador", "serie")]
    return _TABELAS_LOG


def _cols(con, t):
    if t not in _COLS:
        xi = con.execute(f"PRAGMA main.table_xinfo({t})").fetchall()
        cols = [r[1] for r in xi if r[6] == 0]
        pk = [r[1] for r in sorted(xi, key=lambda r: r[5]) if r[5]]
        _COLS[t] = (cols, pk)
    return _COLS[t]


def _instalar_log(con):
    con.execute("""CREATE TABLE IF NOT EXISTS revisao_log(decisao_id TEXT NOT NULL, seq INTEGER NOT NULL, tabela TEXT NOT NULL,
                   op TEXT NOT NULL CHECK (op IN ('I','U','D')), antes TEXT, depois TEXT, PRIMARY KEY (decisao_id, seq))""")
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _rev_log(seq INTEGER PRIMARY KEY, tabela TEXT, op TEXT, antes TEXT, depois TEXT)")
    if con.execute("SELECT 1 FROM sqlite_temp_master WHERE type='trigger' AND name='_rev_relacao_i'").fetchone():
        return
    for t in _tabelas_log():
        cols, _ = _cols(con, t)

        def jo(p):
            return "json_object(" + ",".join(f"'{c}',{p}.\"{c}\"" for c in cols) + ")"

        con.execute(f"CREATE TEMP TRIGGER _rev_{t}_i AFTER INSERT ON main.{t} BEGIN "
                    f"INSERT INTO _rev_log(tabela,op,antes,depois) VALUES('{t}','I',NULL,{jo('NEW')}); END")
        con.execute(f"CREATE TEMP TRIGGER _rev_{t}_u AFTER UPDATE ON main.{t} BEGIN "
                    f"INSERT INTO _rev_log(tabela,op,antes,depois) VALUES('{t}','U',{jo('OLD')},{jo('NEW')}); END")
        con.execute(f"CREATE TEMP TRIGGER _rev_{t}_d AFTER DELETE ON main.{t} BEGIN "
                    f"INSERT INTO _rev_log(tabela,op,antes,depois) VALUES('{t}','D',{jo('OLD')},NULL); END")


def _salvar_log(con, did):
    con.execute("DELETE FROM revisao_log WHERE decisao_id=?", (did,))
    con.execute("INSERT INTO revisao_log(decisao_id,seq,tabela,op,antes,depois) SELECT ?, seq, tabela, op, antes, depois FROM _rev_log ORDER BY seq", (did,))
    n = con.execute("SELECT count(*) FROM _rev_log").fetchone()[0]
    con.execute("DELETE FROM _rev_log")
    return n


def _chaves_log(con, did):
    out = set()
    for t, antes, depois in con.execute("SELECT tabela, antes, depois FROM revisao_log WHERE decisao_id=?", (did,)):
        _, pk = _cols(con, t)
        for js in (antes, depois):
            if js:
                d = json.loads(js)
                out.add((t, tuple(d[c] for c in pk)))
    return out


def _reverter(con, did):
    linhas = con.execute("SELECT tabela, op, antes, depois FROM revisao_log WHERE decisao_id=? ORDER BY seq DESC", (did,)).fetchall()
    for t, op, antes, depois in linhas:
        cols, pk = _cols(con, t)
        a = json.loads(antes) if antes else None
        d = json.loads(depois) if depois else None
        onde = " AND ".join(f'"{c}" IS ?' for c in pk)
        if op == "I":
            con.execute(f"DELETE FROM {t} WHERE {onde}", [d[c] for c in pk])
        elif op == "D":
            con.execute(f"INSERT INTO {t}({','.join(chr(34) + c + chr(34) for c in cols)}) VALUES({','.join('?' * len(cols))})",
                        [a[c] for c in cols])
        else:
            con.execute(f"UPDATE {t} SET {','.join(chr(34) + c + chr(34) + '=?' for c in cols)} WHERE {onde}",
                        [a[c] for c in cols] + [d[c] for c in pk])
    return len(linhas)


# --------------------------------------------------------------------------- chaves naturais e resolução
def _chave_rel(r):
    return {"id": r["id"], "de": r["de"], "para": r["para"], "tipo": r["tipo"], "rotulo": r["rotulo"],
            "periodo_inicio": r["periodo_inicio"], "origem": r["origem"], "origem_ref": r["origem_ref"]}


def _achar_rel(con, k):
    r = con.execute("SELECT * FROM relacao WHERE de=? AND para=? AND tipo=? AND rotulo=? AND IFNULL(periodo_inicio,'')=?",
                    (k.get("de"), k.get("para"), k.get("tipo"), k.get("rotulo"), k.get("periodo_inicio") or "")).fetchone()
    if r is None and k.get("id") is not None:
        r = con.execute("SELECT * FROM relacao WHERE id=? AND de=? AND para=? AND tipo=?", (k["id"], k.get("de"), k.get("para"), k.get("tipo"))).fetchone()
    return r


def _chave_corte(c):
    return {"id": c["id"], "video_id": c["video_id"], "titulo": c["titulo"], "inicio_s": c["inicio_s"], "fim_s": c["fim_s"]}


def _achar_corte(con, k):
    r = con.execute("SELECT * FROM corte WHERE id=? AND video_id=? AND inicio_s=? AND fim_s=?",
                    (k.get("id"), k.get("video_id"), k.get("inicio_s"), k.get("fim_s"))).fetchone()
    return r or con.execute("SELECT * FROM corte WHERE video_id=? AND inicio_s=? AND fim_s=? AND titulo=? ORDER BY id",
                            (k.get("video_id"), k.get("inicio_s"), k.get("fim_s"), k.get("titulo"))).fetchone()


def _resolver_evento(con, eid):
    """id de evento ou alias (evento fundido) -> id vigente, ou None."""
    if con.execute("SELECT 1 FROM evento WHERE id=?", (eid,)).fetchone():
        return eid
    r = con.execute("SELECT evento_id FROM evento_alias WHERE alias=?", (eid,)).fetchone()
    return r[0] if r else None


def _rel_ou_erro(con, rid):
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        raise _rej(f"id de relação inválido: {rid!r}")
    r = con.execute("SELECT * FROM relacao WHERE id=?", (rid,)).fetchone()
    if not r:
        raise _rej(f"relação {rid} não existe")
    return r


# --------------------------------------------------------------------------- normalização de campos editáveis
def _norm_campos_rel(con, campos):
    if not campos:
        return {}
    if not isinstance(campos, dict):
        raise _rej("campos deve ser um objeto {campo: valor}")
    ruins = [k for k in campos if k not in CAMPOS_REL]
    if ruins:
        raise _rej(f"campos não editáveis: {ruins}", validos=CAMPOS_REL)
    s, out = S(), {}
    for k, v in campos.items():
        if k == "natureza":
            out[k] = s.natureza_id(con, v)
        elif k == "tipo":
            if v not in s.TIPOS_RELACAO:
                raise _rej(f"tipo '{v}' inválido", validos=s.TIPOS_RELACAO)
            out[k] = v
        elif k in ("de", "para"):
            s._checar_entidade(con, k, v)
            out[k] = v
        elif k in ("periodo_inicio", "periodo_fim"):
            out[k] = s._periodo_val(v, k)
        elif k == "confianca":
            out[k] = None if v is None else float(v)
            if out[k] is not None and not 0 <= out[k] <= 1:
                raise _rej("confianca fora de 0..1")
        elif k == "valor_brl":
            out[k] = None if v in (None, "") else float(v)
        elif k == "rotulo":
            if not v or not str(v).strip():
                raise _rej("rotulo não pode ficar vazio")
            out[k] = str(v).strip()
        elif k == "temas":
            out[k] = s._checar_temas(con, v if isinstance(v, list) else [v])
            if not out[k]:
                raise _rej("temas: informe ao menos um tema (ou não envie o campo)")
        else:
            out[k] = v if v != "" else None
    return out


def _norm_campos_evento(con, campos):
    if not campos:
        return {}
    if not isinstance(campos, dict):
        raise _rej("campos deve ser um objeto {campo: valor}")
    ruins = [k for k in campos if k not in CAMPOS_EVENTO]
    if ruins:
        raise _rej(f"campos não editáveis: {ruins}", validos=CAMPOS_EVENTO)
    s, out = S(), {}
    for k, v in campos.items():
        if k == "natureza":
            out[k] = s.natureza_id(con, v)
        elif k == "data":
            out[k] = s._periodo_val(v, "data")
        elif k == "peso":
            out[k] = None if v in (None, "") else int(v)
            if out[k] is not None and not 1 <= out[k] <= 5:
                raise _rej("peso fora de 1..5")
        elif k == "data_aprox":
            out[k] = 1 if v else 0
        elif k == "valor_brl":
            out[k] = None if v in (None, "") else float(v)
        elif k == "titulo":
            if not v or not str(v).strip():
                raise _rej("titulo não pode ficar vazio")
            out[k] = str(v).strip()
        elif k == "temas":
            out[k] = s._checar_temas(con, v if isinstance(v, list) else [v])
            if not out[k]:
                raise _rej("temas: informe ao menos um tema")
        else:
            out[k] = v if v != "" else None
    return out


def _norm_campos_corte(campos):
    if not campos:
        return {}
    ruins = [k for k in campos if k not in CAMPOS_CORTE]
    if ruins:
        raise _rej(f"campos não editáveis: {ruins}", validos=CAMPOS_CORTE)
    out = dict(campos)
    for k in ("inicio_s", "fim_s"):
        if k in out:
            out[k] = float(out[k])
    return out


# --------------------------------------------------------------------------- FTS / embeddings das linhas tocadas
def _fts_relacao(con, ids):
    for i in ids:
        con.execute("DELETE FROM busca_fts WHERE origem_tabela='relacao' AND origem_id=?", (str(i),))  # sincronizar_fts reinsere


def _fts_evento(con, eid):
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='evento' AND origem_id=?", (eid,))
    con.execute("INSERT INTO busca_fts(origem_tabela, origem_id, texto) SELECT 'evento', id, titulo || ' ' || COALESCE(descricao,'') FROM evento WHERE id=?", (eid,))


def _fts_entidade(con, eid):
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='entidade' AND origem_id=?", (eid,))
    con.execute("""INSERT INTO busca_fts(origem_tabela, origem_id, texto)
        SELECT 'entidade', e.id, e.nome || ' ' || COALESCE(e.cargo,'') || ' ' || COALESCE(e.descricao,'') || ' ' ||
               COALESCE((SELECT group_concat(alias,' ') FROM entidade_alias a WHERE a.entidade_id=e.id),'') FROM entidade e WHERE e.id=?""", (eid,))


def _emb(con, ids_por_tabela, orfaos=False):
    s = S()
    nota = s._nota_emb()
    if orfaos and s.EMB is not None:
        try:
            s.EMB.limpar_orfaos(con, ("trecho", "relacao", "relacao_rotulo", "evidencia", "evento", "entidade"))
        except Exception:  # tabela embedding ausente etc.: derivada, não bloqueia a decisão
            pass
    for tab, ids in ids_por_tabela.items():
        try:
            s._emb_gravar(con, nota, {tab: ids})
        except sqlite3.OperationalError as e:  # ex.: embeddings.textos_de('entidade', ids) monta SQL inválido (bug conhecido)
            nota.update(status="ignorado", motivo=f"embedding de {tab} não gerado ({e}); rode scripts/embeddings.py")
    return nota


# --------------------------------------------------------------------------- aplicação (comum ao vivo e à reaplicação)
def _set(con, tabela, pk, pkv, novos, atual):
    """UPDATE só dos campos que mudam. -> dict dos alterados {campo: [antes, depois]}."""
    mud = {k: [atual[k], v] for k, v in novos.items() if atual[k] != v}
    if mud:
        extra = ", atualizado_em=?" if tabela in ("relacao", "evento", "entidade") else ""
        vals = [v[1] for v in mud.values()] + ([S().agora()] if extra else [])
        con.execute(f"UPDATE {tabela} SET {', '.join(k + '=?' for k in mud)}{extra} WHERE {pk}=?", vals + [pkv])
    return mud


def _temas_substituir(con, tabela, col, oid, temas):
    atuais = [r[0] for r in con.execute(f"SELECT tema_id FROM {tabela} WHERE {col}=? ORDER BY tema_id", (oid,))]
    if sorted(atuais) == sorted(temas):
        return None
    con.execute(f"DELETE FROM {tabela} WHERE {col}=?", (oid,))
    for t in temas:
        con.execute(f"INSERT INTO {tabela}({col}, tema_id, origem, regra) VALUES(?,?,'manual','revisao')", (oid, t))
    return [atuais, temas]


def _editar_rel(con, r, campos):
    novos = {("natureza_id" if k == "natureza" else k): v for k, v in campos.items() if k != "temas"}
    if ("de" in novos or "para" in novos) and novos.get("de", r["de"]) == novos.get("para", r["para"]):
        raise _rej("de e para não podem ser a mesma entidade")
    mud = _set(con, "relacao", "id", r["id"], novos, r)
    if "temas" in campos:
        t = _temas_substituir(con, "relacao_tema", "relacao_id", r["id"], campos["temas"])
        if t:
            mud["temas"] = t
    avisos = []
    if mud and r["origem"] == "teia" and set(mud) & {"rotulo", "descricao", "natureza_id", "periodo_inicio", "periodo_fim", "de", "para", "valor_brl", "resposta", "tipo"}:
        avisos.append("relação da teia original (raw): validar.py compara teia.json com data/raw e vai acusar a diferença")
    if set(mud) & {"rotulo", "descricao"}:
        _fts_relacao(con, [r["id"]])
        _emb(con, {"relacao": [r["id"]], "relacao_rotulo": [r["id"]]})
    return mud, avisos


def _mover_ligacoes_rel(con, src, dst):
    """Move evidências, trechos, cortes, eventos e temas de src para dst. -> contagens."""
    s, n = S(), {"evidencias": 0, "trechos": 0, "cortes": 0, "eventos": 0, "temas": 0}
    for x in con.execute("SELECT evidencia_id, papel, trecho_citado FROM relacao_evidencia WHERE relacao_id=? ORDER BY ordem", (src,)).fetchall():
        n["evidencias"] += s._ligar_evidencia(con, dst, x["evidencia_id"], x["papel"], x["trecho_citado"])
    con.execute("DELETE FROM relacao_evidencia WHERE relacao_id=?", (src,))
    for tab, col, extra in (("trecho_relacao", "trecho_id", "papel"), ("relacao_corte", "corte_id", None), ("evento_relacao", "evento_id", "papel")):
        cs = f"{col}" + (f", {extra}" if extra else "")
        cur = con.execute(f"INSERT OR IGNORE INTO {tab}(relacao_id, {cs}) SELECT ?, {cs} FROM {tab} WHERE relacao_id=?", (dst, src))
        n[{"trecho_relacao": "trechos", "relacao_corte": "cortes", "evento_relacao": "eventos"}[tab]] += cur.rowcount
        con.execute(f"DELETE FROM {tab} WHERE relacao_id=?", (src,))
    cur = con.execute("""INSERT OR IGNORE INTO relacao_tema(relacao_id, tema_id, origem, regra)
                         SELECT ?, tema_id, origem, regra FROM relacao_tema WHERE relacao_id=? AND tema_id<>'a-classificar'""", (dst, src))
    n["temas"] = cur.rowcount
    if cur.rowcount:
        con.execute("DELETE FROM relacao_tema WHERE relacao_id=? AND tema_id='a-classificar'", (dst,))
    return n


def _ap_relacao(con, dec, arq):
    r = _achar_rel(con, dec["alvo"])
    if r is None:
        return {"ignorada": "relação não encontrada neste banco (criada pelo MCP antes de uma remigração? reinsira a fonte)"}, False
    acao, campos = dec["acao"], dict(dec.get("campos") or {})
    res = {"relacao_id": r["id"]}
    if acao == "fundir_em":
        dst = _achar_rel(con, campos.get("fundir_em") or {})
        if dst is None:
            return {"ignorada": "relação-alvo da fusão não encontrada neste banco", **res}, False
        if dst["id"] == r["id"]:
            raise _rej("não dá para fundir uma relação nela mesma")
        n = _mover_ligacoes_rel(con, r["id"], dst["id"])
        mud = _set(con, "relacao", "id", r["id"], {"status": "descartada"}, r)
        res.update(fundida_em=dst["id"], movidos=n, status="descartada")
        av = []
        if dst["status"] == "descartada":
            av.append(f"a relação-alvo {dst['id']} está descartada")
        if dst["origem"] == "teia" and n["evidencias"]:
            av.append("a relação-alvo é da teia original: as evidências novas aparecem em teia.json e validar.py acusa a diferença no "
                      "round-trip com data/raw (esperado; a fonte é acréscimo legítimo)")
        if av:
            res["avisos"] = av
        return res, bool(mud) or any(n.values())
    mud, avisos = _editar_rel(con, r, {k: v for k, v in campos.items()})
    r2 = con.execute("SELECT * FROM relacao WHERE id=?", (r["id"],)).fetchone()
    if acao in ("aprovar", "descartar"):
        st = "publicada" if acao == "aprovar" else "descartada"
        m2 = _set(con, "relacao", "id", r["id"], {"status": st}, r2)
        mud.update(m2)
        res["status"] = st
    res.update(alterado=mud, origem=r["origem"])
    if avisos:
        res["avisos"] = avisos
    return res, bool(mud)


def _ap_corte(con, dec, arq):
    c = _achar_corte(con, dec["alvo"])
    if c is None:
        return {"ignorada": "corte não encontrado (vídeo reinserido ou banco remigrado?)"}, False
    novos = dict(dec.get("campos") or {})
    if dec["acao"] in STATUS_CORTE:
        novos["status"] = STATUS_CORTE[dec["acao"]]
    if novos.get("fim_s", c["fim_s"]) <= novos.get("inicio_s", c["inicio_s"]):
        raise _rej("fim_s deve ser > inicio_s")
    mud = _set(con, "corte", "id", c["id"], novos, c)
    return {"corte_id": c["id"], "status": novos.get("status", c["status"]), "alterado": mud}, bool(mud)


def _ev_origem_raw(e):
    return bool(re.search(r"(teia:EV|origens:EV|PREC)\[", e["origem_ref"] or ""))


def _ap_evento(con, dec, arq):
    acao, campos = dec["acao"], dict(dec.get("campos") or {})
    eid = dec["alvo"]["id"]
    if acao == "manter_separados":
        return {"evento_id": eid, "com": campos.get("com", []), "registrado": True}, arq is not None  # só marca a fila; nada no banco
    if acao == "fundir_em":
        return _ap_evento_fundir(con, dec, arq)
    e = con.execute("SELECT * FROM evento WHERE id=?", (eid,)).fetchone()
    if e is None:
        return {"ignorada": f"evento '{eid}' não existe neste banco"}, False
    if acao == "natureza":
        campos = {"natureza": campos["natureza"]}
    novos = {("natureza_id" if k == "natureza" else k): v for k, v in campos.items() if k != "temas"}
    mud = _set(con, "evento", "id", eid, novos, e)
    if "temas" in campos:
        t = _temas_substituir(con, "evento_tema", "evento_id", eid, campos["temas"])
        if t:
            mud["temas"] = t
    res = {"evento_id": eid, "alterado": mud}
    if set(mud) & {"titulo", "descricao"}:
        _fts_evento(con, eid)
        _emb(con, {"evento": [eid]})
    if mud and _ev_origem_raw(e) and (set(mud) & {"titulo", "descricao", "data", "data_texto", "peso"} or (e["natureza_id"] and "natureza_id" in mud)):
        res["avisos"] = ["evento vindo do raw: validar.py compara título/descrição/data/peso/natureza original com data/raw e vai acusar a diferença"]
    return res, bool(mud)


def _ap_evento_fundir(con, dec, arq):
    """Mesma regra de curadoria.aplicar_fusoes (é ela que roda); ao vivo também grava em eventos-fusoes.json."""
    import curadoria as CUR
    eid, campos = dec["alvo"]["id"], dict(dec.get("campos") or {})
    alvo = _resolver_evento(con, campos["fundir_em"])
    if alvo is None:
        return {"ignorada": f"evento-alvo '{campos['fundir_em']}' não existe neste banco"}, False
    peso = {r[0]: r[1] for r in con.execute("SELECT id, peso FROM natureza")}
    if not con.execute("SELECT 1 FROM evento WHERE id=?", (eid,)).fetchone():
        ja = con.execute("SELECT evento_id FROM evento_alias WHERE alias=?", (eid,)).fetchone()
        if not ja:
            return {"ignorada": f"evento '{eid}' não existe neste banco"}, False
        # já fundido (por migrar.py a partir de eventos-fusoes.json): só garante a natureza resultante da decisão original
        nr = campos.get("natureza_resultante")
        atual = con.execute("SELECT natureza_id FROM evento WHERE id=?", (ja[0],)).fetchone()[0]
        if nr and (atual is None or peso[atual] < peso[nr]):
            con.execute("UPDATE evento SET natureza_id=?, atualizado_em=? WHERE id=?", (nr, S().agora(), ja[0]))
            return {"evento_id": eid, "fundido_em": ja[0], "natureza": nr}, True
        return {"evento_id": eid, "fundido_em": ja[0], "ja_fundido": True}, False
    if alvo == eid:
        raise _rej("não dá para fundir um evento nele mesmo")
    if con.execute("SELECT 1 FROM evento_alias WHERE evento_id=?", (eid,)).fetchone():
        raise _rej(f"'{eid}' já absorveu outros eventos (é 'manter' em eventos-fusoes.json): funda na direção contrária "
                   f"(fundir '{alvo}' em '{eid}') ou edite eventos-fusoes.json à mão")
    d1, d2 = (con.execute("SELECT data FROM evento WHERE id=?", (i,)).fetchone()[0] for i in (eid, alvo))
    if d1 != d2:
        raise _rej(f"datas diferentes ({eid}: {d1}; {alvo}: {d2}). migrar.py só funde eventos com a mesma data: "
                   f"corrija a data em data/raw/curadoria antes, ou mantenha separados")
    motivo = dec.get("motivo") or f"Revisão {dec['quando'][:10]}: mesmo fato."
    lista, entrada = None, None
    if arq is not None:
        p = pasta_curadoria() / "eventos-fusoes.json"
        if not p.exists():
            raise _rej(f"{p} não existe: a fusão de evento precisa gravar a curadoria (migrar.py/validar.py leem esse arquivo)")
        lista = json.loads(p.read_text(encoding="utf-8"))
        if any(eid == f["manter"] or eid in f["fundir"] for f in lista):
            raise _rej(f"'{eid}' já aparece em eventos-fusoes.json")
        entrada = next((f for f in lista if f["manter"] == alvo), None)
    for t in con.execute("SELECT tema_id FROM evento_tema WHERE evento_id=? AND tema_id<>'a-classificar'", (eid,)).fetchall():
        con.execute("INSERT OR IGNORE INTO evento_tema(evento_id, tema_id, origem, regra) VALUES(?,?,'manual','revisao')", (alvo, t[0]))
    original = CUR.ler_json
    CUR.ler_json = lambda nome, padrao=None: [{"manter": alvo, "fundir": [eid], "motivo": motivo}] if nome == "eventos-fusoes.json" else original(nome, padrao)
    try:
        saida = CUR.aplicar_fusoes(con)[0]
    except AssertionError as e:
        raise _rej(f"fusão recusada pela regra de curadoria: {e}")
    finally:
        CUR.ler_json = original
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='evento' AND origem_id=?", (eid,))
    _fts_evento(con, alvo)
    _emb(con, {"evento": [alvo]}, orfaos=True)
    dec.setdefault("campos", {})["natureza_resultante"] = saida["natureza"]
    dec["campos"]["motivo_fusao"] = motivo
    if arq is not None:
        if entrada:
            entrada["fundir"].append(eid)
            entrada["motivo"] = f"{entrada['motivo']} {motivo}"
            dec["campos"]["entrada_nova"] = False
        else:
            lista.append({"manter": alvo, "fundir": [eid], "motivo": motivo})
            dec["campos"]["entrada_nova"] = True
        arq.escrever(pasta_curadoria() / "eventos-fusoes.json", _fmt_fusoes(lista))
    return {"evento_id": eid, "fundido_em": alvo, "natureza": saida["natureza"], "fontes_novas": saida["fontes_novas"],
            "entidades_novas": saida["entidades_novas"],
            "proximo_passo": "eventos-fusoes.json atualizado. Para os arquivos gerados (eventos-natureza, evento-entidade-auto, brasil-fontes) "
                             "deixarem de citar o id fundido: python3 scripts/gerar_curadoria.py && python3 scripts/migrar.py && "
                             "python3 scripts/aplicar_decisoes.py (até lá validar.py pode acusar o id em eventos-natureza.json)"}, True


# ligações de entidade: (tabela, coluna, tem a entidade na PK?)
_LIGACOES_ENT = [("entidade_alias", "entidade_id", True), ("evento_entidade", "entidade_id", True), ("trecho_entidade", "entidade_id", True),
                 ("nota_entidade", "entidade_id", True), ("fonte", "canal_entidade_id", False), ("mandato", "entidade_id", False),
                 ("mandato", "orgao_id", False), ("bancada", "partido_id", True), ("ranking_empresa", "entidade_id", True),
                 ("dossie_par", "ator_entidade_id", False), ("previdencia_ente", "entidade_id", False),
                 ("pagamento", "para_entidade_id", False), ("pagamento", "de_entidade_id", False), ("forum", "pais_entidade_id", True),
                 ("entidade_valor", "entidade_id", False)]


def _ap_entidade(con, dec, arq):
    de, para = dec["alvo"]["id"], dec["campos"]["para"]
    s = S()
    ed = con.execute("SELECT * FROM entidade WHERE id=?", (de,)).fetchone()
    ep = con.execute("SELECT * FROM entidade WHERE id=?", (para,)).fetchone()
    if ep is None:
        return {"ignorada": f"entidade-destino '{para}' não existe"}, False
    if ed is None:
        return {"de": de, "para": para, "ja_fundida": True}, False
    if de == para:
        raise _rej("de e para são a mesma entidade")
    if ed["ind_legado"] is not None or con.execute("SELECT 1 FROM aresta_legado WHERE a=? OR b=?", (de, de)).fetchone():
        raise _rej(f"'{de}' é nó da teia original (posição {ed['ind_legado']} em teia.N): fundir mudaria teia.json e quebraria o round-trip "
                   "de validar.py. Use scripts/fusoes.json + migrar.py")
    n = {"relacoes_movidas": 0, "relacoes_fundidas": [], "relacoes_apagadas": [], "ligacoes": {}}
    for r in con.execute("SELECT * FROM relacao WHERE de=? OR para=? ORDER BY id", (de, de)).fetchall():
        nd, np_ = (para if r["de"] == de else r["de"]), (para if r["para"] == de else r["para"])
        if nd == np_:  # relação entre as duas entidades fundidas
            con.execute("DELETE FROM relacao WHERE id=?", (r["id"],))
            n["relacoes_apagadas"].append({"id": r["id"], "rotulo": r["rotulo"]})
            continue
        ex = con.execute("SELECT id FROM relacao WHERE de=? AND para=? AND tipo=? AND rotulo=? AND IFNULL(periodo_inicio,'')=? AND id<>?",
                         (nd, np_, r["tipo"], r["rotulo"], r["periodo_inicio"] or "", r["id"])).fetchone()
        if ex:
            _mover_ligacoes_rel(con, r["id"], ex[0])
            con.execute("DELETE FROM relacao WHERE id=?", (r["id"],))
            n["relacoes_fundidas"].append({"de_id": r["id"], "em": ex[0]})
        else:
            con.execute("UPDATE relacao SET de=?, para=?, atualizado_em=? WHERE id=?", (nd, np_, s.agora(), r["id"]))
            n["relacoes_movidas"] += 1
    for tab, col, na_pk in _LIGACOES_ENT:
        if na_pk and tab in ("entidade_alias", "evento_entidade", "trecho_entidade", "nota_entidade"):
            cols = [c for c in _cols(con, tab)[0] if c != col]
            cs = ", ".join(cols)
            cur = con.execute(f"INSERT OR IGNORE INTO {tab}({col}, {cs}) SELECT ?, {cs} FROM {tab} WHERE {col}=?", (para, de))
            k = con.execute(f"DELETE FROM {tab} WHERE {col}=?", (de,)).rowcount
        else:
            try:
                k = con.execute(f"UPDATE {tab} SET {col}=? WHERE {col}=?", (para, de)).rowcount
            except sqlite3.IntegrityError as e:
                raise _rej(f"{tab}.{col}: '{para}' já tem linha equivalente à de '{de}' ({e}); resolva à mão antes de fundir")
        if k:
            n["ligacoes"][f"{tab}.{col}"] = n["ligacoes"].get(f"{tab}.{col}", 0) + k
    from slug import alias_norm
    con.execute("""INSERT INTO entidade_alias(alias, alias_norm, entidade_id, tipo_alias, origem) VALUES(?,?,?, 'nome_antigo', 'revisao')
                   ON CONFLICT(alias_norm, entidade_id) DO UPDATE SET alias=excluded.alias, tipo_alias='nome_antigo', origem='revisao'""",
                (ed["nome"], alias_norm(ed["nome"]), para))
    completar = {c: ed[c] for c in ("cargo", "descricao", "uf", "nascimento", "partido", "dossie") if ep[c] in (None, "") and ed[c] not in (None, "")}
    con.execute("DELETE FROM entidade WHERE id=?", (de,))
    if completar:
        _set(con, "entidade", "id", para, completar, ep)
        n["completou"] = sorted(completar)
    con.execute("DELETE FROM busca_fts WHERE origem_tabela='entidade' AND origem_id=?", (de,))
    _fts_entidade(con, para)
    rels = [r[0] for r in con.execute("SELECT id FROM relacao WHERE de=? OR para=?", (para, para))]
    _fts_relacao(con, rels)
    _emb(con, {"entidade": [para]}, orfaos=True)
    return {"de": de, "para": para, "alias_criado": ed["nome"], **n}, True


_APLICADORES = {"relacao": _ap_relacao, "corte": _ap_corte, "evento": _ap_evento, "entidade": _ap_entidade}


def _aplicar_um(con, dec, arq):
    """Uma decisão com log. -> (resultado, mudou)."""
    _instalar_log(con)
    con.execute("DELETE FROM _rev_log")
    res, mudou = _APLICADORES[dec["tipo"]](con, dec, arq)
    if mudou:
        res["linhas_registradas"] = _salvar_log(con, dec["id"])
    else:
        con.execute("DELETE FROM _rev_log")
    return res, mudou


def _publico(dec):
    return {k: dec.get(k) for k in ("id", "quando", "tipo", "alvo", "acao", "campos", "motivo")}


def _decidir(montar):
    """montar(con) -> dec (valida e monta a decisão com chave natural). Aplica, registra no jsonl e regrava o dump numa transação."""
    s, arq = S(), _Arquivos()
    caixa = {}

    def tx(con):
        dec = montar(con)
        caixa["dec"] = dec
        res, mudou = _aplicar_um(con, dec, arq)
        if not mudou:
            raise _NadaMudou(res)
        viol = con.execute("PRAGMA foreign_key_check").fetchall()
        if viol:
            raise _rej("foreign_key_check falhou; decisão desfeita", violacoes=[tuple(v) for v in viol[:10]])
        arq.anexar(caminho_decisoes(), json.dumps(_publico(dec), ensure_ascii=False, sort_keys=True))
        return {"decisao": _publico(dec), "decisoes_jsonl": str(caminho_decisoes()), **res}

    try:
        out = s.operacao_escrita(tx)
    except _NadaMudou as n:
        arq.restaurar()
        return {"ok": True, "ja_aplicada": True, "nada_mudou": True, **n.res}
    except BaseException:
        arq.restaurar()
        raise
    if not out.get("ok"):
        arq.restaurar()
    return out


def _nova_dec(tipo, alvo, acao, campos, motivo):
    q = S().agora()
    return {"id": "d" + re.sub(r"[-:]", "", q) + "-" + secrets.token_hex(3), "quando": q, "tipo": tipo, "alvo": alvo,
            "acao": acao, "campos": campos or {}, "motivo": motivo}


# --------------------------------------------------------------------------- núcleos (ao vivo)
def revisar_relacao_core(id, acao, alvo_id=None, campos=None, motivo=None):
    if acao not in ACOES_RELACAO:
        return {"ok": False, "erro": f"acao '{acao}' inválida", "validos": ACOES_RELACAO}

    def montar(con):
        r = _rel_ou_erro(con, id)
        cs = {}
        if acao == "fundir_em":
            if alvo_id is None:
                raise _rej("fundir_em exige alvo_id (id da relação que fica)")
            cs["fundir_em"] = _chave_rel(_rel_ou_erro(con, alvo_id))
            if campos:
                raise _rej("fundir_em não aceita campos: edite a relação-alvo com acao='editar'")
        else:
            cs = _norm_campos_rel(con, campos)
            if acao == "editar" and not cs:
                raise _rej("editar exige campos", validos=CAMPOS_REL)
        return _nova_dec("relacao", _chave_rel(r), acao, cs, motivo)

    return _decidir(montar)


def revisar_corte_core(id, acao, campos=None, motivo=None):
    if acao not in ACOES_CORTE:
        return {"ok": False, "erro": f"acao '{acao}' inválida", "validos": ACOES_CORTE}

    def montar(con):
        c = con.execute("SELECT * FROM corte WHERE id=?", (id,)).fetchone()
        if not c:
            raise _rej(f"corte {id} não existe")
        cs = _norm_campos_corte(campos)
        if acao == "editar" and not cs:
            raise _rej("editar exige campos", validos=CAMPOS_CORTE)
        return _nova_dec("corte", _chave_corte(c), acao, cs, motivo)

    return _decidir(montar)


def revisar_evento_core(id, acao, alvo_id=None, natureza=None, campos=None, motivo=None):
    if acao not in ACOES_EVENTO:
        return {"ok": False, "erro": f"acao '{acao}' inválida", "validos": ACOES_EVENTO}

    def montar(con):
        eid = str(id)
        if acao != "manter_separados" and not con.execute("SELECT 1 FROM evento WHERE id=?", (eid,)).fetchone():
            al = con.execute("SELECT evento_id FROM evento_alias WHERE alias=?", (eid,)).fetchone()
            raise _rej(f"evento '{eid}' não existe" + (f" (foi fundido em '{al[0]}')" if al else ""))
        cs = {}
        if acao == "natureza":
            v = natureza if natureza is not None else (campos or {}).get("natureza")
            if v is None:
                raise _rej("acao 'natureza' exige natureza", validos=[r[0] for r in con.execute("SELECT id FROM natureza ORDER BY peso DESC")])
            cs["natureza"] = S().natureza_id(con, v)
        elif acao == "fundir_em":
            if not alvo_id:
                raise _rej("fundir_em exige alvo_id (id do evento que fica)")
            a = _resolver_evento(con, str(alvo_id))
            if a is None:
                raise _rej(f"evento-alvo '{alvo_id}' não existe")
            cs["fundir_em"] = a
        elif acao == "manter_separados":
            com = alvo_id if isinstance(alvo_id, list) else ([alvo_id] if alvo_id else (campos or {}).get("com"))
            if not com:
                raise _rej("manter_separados exige alvo_id (o outro evento do candidato, ou lista)")
            cs["com"] = sorted({_resolver_evento(con, str(x)) or str(x) for x in com})
            eid = _resolver_evento(con, eid) or eid
        else:
            cs = _norm_campos_evento(con, dict(campos or {}, **({"natureza": natureza} if natureza is not None else {})))
            if not cs:
                raise _rej("editar exige campos", validos=CAMPOS_EVENTO)
        return _nova_dec("evento", {"id": eid}, acao, cs, motivo)

    return _decidir(montar)


def fundir_entidade_core(de, para, motivo=None):
    def montar(con):
        for k, v in (("de", de), ("para", para)):
            if not v:
                raise _rej(f"{k} é obrigatório")
        if not con.execute("SELECT 1 FROM entidade WHERE id=?", (para,)).fetchone():
            raise _rej(f"entidade '{para}' (para) não existe", sugestoes=S()._sugestoes(con, para))
        if not con.execute("SELECT 1 FROM entidade WHERE id=?", (de,)).fetchone():
            decs = ler_decisoes()
            canc = desfeitas(decs)
            if any(d.get("tipo") == "entidade" and d["alvo"]["id"] == de and d["campos"].get("para") == para and d["id"] not in canc for d in decs):
                raise _NadaMudou({"de": de, "para": para, "ja_fundida": True})
            raise _rej(f"entidade '{de}' (de) não existe", sugestoes=S()._sugestoes(con, de))
        return _nova_dec("entidade", {"id": de}, "fundir_em", {"para": para}, motivo)

    return _decidir(montar)  # _NadaMudou levantado no montar (já fundida) vira {ok, ja_aplicada}


def desfazer_core(decisao_id, motivo=None):
    s, arq = S(), _Arquivos()

    def tx(con):
        decs = ler_decisoes()
        alvo = next((d for d in decs if d["id"] == decisao_id), None)
        if alvo is None:
            raise _rej(f"decisão '{decisao_id}' não está em {caminho_decisoes()}")
        if alvo["tipo"] == "desfazer":
            raise _rej("um 'desfazer' não pode ser desfeito: tome a decisão de novo")
        if decisao_id in desfeitas(decs):
            raise _rej(f"decisão '{decisao_id}' já foi desfeita")
        _instalar_log(con)
        n_log = con.execute("SELECT count(*) FROM revisao_log WHERE decisao_id=?", (decisao_id,)).fetchone()[0]
        if not n_log and alvo["acao"] != "manter_separados":
            raise _rej("sem log de desfazer para esta decisão neste banco (banco reconstruído do dump?). Para revertê-la: rode "
                       "migrar.py e aplicar_decisoes.py depois de remover a linha do jsonl, ou tome a decisão contrária")
        minhas = _chaves_log(con, decisao_id)
        canceladas = desfeitas(decs)
        depois = [d for d in decs[decs.index(alvo) + 1:] if d["tipo"] != "desfazer" and d["id"] not in canceladas]
        conflitos = [d["id"] for d in depois if minhas & _chaves_log(con, d["id"])]
        if conflitos:
            raise _rej("decisões posteriores mexeram nas mesmas linhas; desfaça-as antes (da mais nova para a mais antiga)", conflitos=conflitos)
        n = _reverter(con, decisao_id)
        con.execute("DELETE FROM revisao_log WHERE decisao_id=?", (decisao_id,))
        if alvo["tipo"] == "evento" and alvo["acao"] == "fundir_em":
            p = pasta_curadoria() / "eventos-fusoes.json"
            lista = json.loads(p.read_text(encoding="utf-8"))
            eid, a = alvo["alvo"]["id"], alvo["campos"]["fundir_em"]
            mf = alvo["campos"].get("motivo_fusao") or ""
            for f in lista:
                if f["manter"] == a and eid in f["fundir"]:
                    f["fundir"].remove(eid)
                    if mf and f["motivo"].endswith(" " + mf):
                        f["motivo"] = f["motivo"][: -len(mf) - 1]
            lista = [f for f in lista if f["fundir"]]
            arq.escrever(p, _fmt_fusoes(lista))
            _fts_evento(con, eid)
            _fts_evento(con, a)
        if alvo["tipo"] == "entidade":
            _fts_entidade(con, alvo["alvo"]["id"])
            _fts_entidade(con, alvo["campos"]["para"])
        if alvo["tipo"] in ("relacao", "entidade"):
            con.execute("DELETE FROM busca_fts WHERE origem_tabela='relacao'")  # sincronizar_fts reinsere todas (rótulos restaurados)
        viol = con.execute("PRAGMA foreign_key_check").fetchall()
        if viol:
            raise _rej("foreign_key_check falhou ao desfazer; nada mudou", violacoes=[tuple(v) for v in viol[:10]])
        dec = _nova_dec("desfazer", {"id": decisao_id}, "desfazer", {"tipo": alvo["tipo"], "acao": alvo["acao"], "alvo": alvo["alvo"]}, motivo)
        arq.anexar(caminho_decisoes(), json.dumps(_publico(dec), ensure_ascii=False, sort_keys=True))
        return {"desfeita": decisao_id, "linhas_revertidas": n, "decisao": _publico(dec)}

    try:
        out = s.operacao_escrita(tx)
    except BaseException:
        arq.restaurar()
        raise
    if not out.get("ok"):
        arq.restaurar()
    return out


def aplicar_todas(decisoes=None, caminho=None):
    """Reaplica decisoes.jsonl (menos as desfeitas e os próprios 'desfazer') numa transação, idempotente. Não grava jsonl nem curadoria.
    -> {ok, aplicadas, ja_estavam, ignoradas:[{id, motivo}], dump}."""
    decs = decisoes if decisoes is not None else ler_decisoes(caminho)
    canc = desfeitas(decs)
    resumo = {"total": len(decs), "desfeitas": len(canc), "aplicadas": [], "ja_estavam": 0, "ignoradas": []}

    def tx(con):
        for d in decs:
            if d.get("tipo") == "desfazer" or d["id"] in canc:
                continue
            if d.get("tipo") not in _APLICADORES:
                resumo["ignoradas"].append({"id": d["id"], "motivo": f"tipo desconhecido {d.get('tipo')!r}"})
                continue
            con.execute("SAVEPOINT dec")
            try:
                res, mudou = _aplicar_um(con, dict(d, campos=dict(d.get("campos") or {})), None)
                con.execute("RELEASE dec")
            except S().Rejeitado as r:
                con.execute("ROLLBACK TO dec")
                con.execute("RELEASE dec")
                resumo["ignoradas"].append({"id": d["id"], "motivo": r.payload.get("erro")})
                continue
            if "ignorada" in res:
                resumo["ignoradas"].append({"id": d["id"], "motivo": res["ignorada"]})
            elif mudou:
                resumo["aplicadas"].append(d["id"])
            else:
                resumo["ja_estavam"] += 1
        return dict(resumo)

    return S().operacao_escrita(tx)


# --------------------------------------------------------------------------- pendências
def _yt_t(url, s):
    if not url or s is None:
        return url
    if "youtube.com" in url or "youtu.be" in url:
        return url + ("&" if "?" in url else "?") + f"t={int(s)}s"
    return url


def _item_relacao(con, r, com_similares):
    s = S()
    d = s._relacao_dict(con, r)
    d.update(tipo_item="relacao", chave=f"relacao:{r['id']}", confianca=r["confianca"])
    d["tipo_relacao"] = d.pop("tipo")
    d["trechos"] = [{"id": t["id"], "fonte_id": t["fonte_id"], "fonte_titulo": t["ft"], "fonte_tipo": t["fty"], "url": _yt_t(t["fu"], t["inicio_s"]),
                     "inicio_s": t["inicio_s"], "fim_s": t["fim_s"], "localizacao": t["localizacao"], "afirmacao": t["afirmacao"],
                     "texto_original": t["texto_original"], "confianca": t["confianca"], "papel": t["papel"]}
                    for t in con.execute("""SELECT t.*, f.titulo ft, f.tipo fty, f.url fu, tr.papel FROM trecho_relacao tr JOIN trecho t ON t.id=tr.trecho_id
                                            JOIN fonte f ON f.id=t.fonte_id WHERE tr.relacao_id=? ORDER BY t.fonte_id, t.ordem""", (r["id"],))]
    d["mesmo_par"] = [{"id": x["id"], "rotulo": x["rotulo"], "tipo": x["tipo"], "status": x["status"], "natureza": x["natureza_id"],
                       "invertida": x["de"] != r["de"]}
                      for x in con.execute("""SELECT * FROM relacao WHERE id<>? AND ((de=? AND para=?) OR (de=? AND para=?)) ORDER BY status<>'publicada', id LIMIT 12""",
                                           (r["id"], r["de"], r["para"], r["para"], r["de"]))]
    if com_similares:
        try:
            sim = s.relacoes_similares_core(r["rotulo"], de=r["de"], limite=7)
            d["similares"] = [x for x in sim["similares"] if x["id"] != r["id"]][:6]
        except s.Rejeitado as e:
            d["similares"], d["similares_aviso"] = [], e.payload.get("erro")
        except Exception as e:  # provedor de embedding com problema
            d["similares"], d["similares_aviso"] = [], f"{type(e).__name__}: {e}"
    return d


def _item_evento(con, e):
    return {"id": e["id"], "titulo": e["titulo"], "descricao": e["descricao"], "data": e["data"] or e["data_texto"], "canal": e["canal"],
            "natureza": e["natureza_id"], "peso": e["peso"], "origem_ref": e["origem_ref"],
            "temas": [x[0] for x in con.execute("SELECT tema_id FROM evento_tema WHERE evento_id=? ORDER BY tema_id", (e["id"],))],
            "fontes": [{"rotulo": x[0], "url": x[1]} for x in con.execute(
                "SELECT COALESCE(x.rotulo, v.veiculo), v.url FROM evento_evidencia x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.evento_id=? ORDER BY x.ordem", (e["id"],))],
            "entidades": [{"id": x[0], "nome": x[1]} for x in con.execute(
                "SELECT n.id, n.nome FROM evento_entidade x JOIN entidade n ON n.id=x.entidade_id WHERE x.evento_id=? ORDER BY x.ordem LIMIT 12", (e["id"],))],
            "fundidos": [x[0] for x in con.execute("SELECT alias FROM evento_alias WHERE evento_id=? ORDER BY alias", (e["id"],))]}


_RE_LINHA = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|(.*)\|\s*$")


def candidatos_fusao(con):
    """Candidatos a fusão de evento: eventos-candidatos.json ([{n, data, eventos:[ids], motivo}]) se existir, senão a tabela de
    eventos-candidatos.md (ids entre crases; título entre aspas casa com evento.titulo; 'evento(s) fundido(s)' = eventos do dia que já
    absorveram outros; id inexistente casa pelo maior id existente que seja prefixo dele)."""
    pj, pm = _ler_curadoria("eventos-candidatos.json"), _ler_curadoria("eventos-candidatos.md")
    brutos = []
    if pj:
        for c in json.loads(pj.read_text(encoding="utf-8")):
            brutos.append((int(c["n"]), c.get("data", ""), list(c["eventos"]), [], False, c.get("motivo", "")))
    elif pm:
        for linha in pm.read_text(encoding="utf-8").splitlines():
            m = _RE_LINHA.match(linha)
            if m:
                ev = m.group(3)
                brutos.append((int(m.group(1)), m.group(2).strip(), re.findall(r"`([^`]+)`", ev), re.findall(r"[\"“]([^\"”]+)[\"”]", ev),
                               bool(re.search(r"eventos? fundidos?", ev)), m.group(4).strip()))
    todos = [r[0] for r in con.execute("SELECT id FROM evento")]
    out = []
    for n, data, ids, titulos, fundidos, motivo in brutos:
        res, nao = [], []
        for i in ids:
            r = _resolver_evento(con, i)
            if r is None:
                pref = sorted((x for x in todos if i.startswith(x) and len(x) >= 20), key=len, reverse=True)
                r = pref[0] if pref else None
            (res.append(r) if r else nao.append(i))
        datas = [d.strip() for d in re.split(r"/", data) if d.strip()]
        for t in titulos:
            for row in con.execute("SELECT id FROM evento WHERE titulo=?", (t,)):
                res.append(row[0])
        if fundidos and datas:
            for row in con.execute(f"SELECT DISTINCT a.evento_id FROM evento_alias a JOIN evento e ON e.id=a.evento_id WHERE e.data IN ({','.join('?' * len(datas))})", datas):
                res.append(row[0])
        vistos = []
        for r in res:
            if r not in vistos:
                vistos.append(r)
        out.append({"n": n, "data": data, "ids": vistos, "nao_resolvidos": nao, "motivo": motivo})
    return out


def listar_pendencias_core(tipo=None, tema=None, limite=50, com_similares=True):
    s = S()
    if tipo is not None and tipo not in TIPOS_PENDENCIA:
        return {"ok": False, "erro": f"tipo '{tipo}' inválido", "validos": TIPOS_PENDENCIA}
    limite = max(1, int(limite))
    quer = [tipo] if tipo else TIPOS_PENDENCIA
    out = {"ok": True, "contagem": {}, "itens": [], "avisos": []}
    with s.leitura() as con:
        if tema:
            try:
                tema = s._checar_temas(con, [tema], "tema")[0]
            except s.Rejeitado as r:
                return r.payload
        decs = ler_decisoes()
        canc = desfeitas(decs)
        if "relacao" in quer:
            w, p = "status IN ('revisar','rascunho')", []
            if tema:
                w += " AND id IN (SELECT relacao_id FROM relacao_tema WHERE tema_id=?)"; p.append(tema)
            out["contagem"]["relacao"] = con.execute(f"SELECT count(*) FROM relacao WHERE {w}", p).fetchone()[0]
            for r in con.execute(f"SELECT * FROM relacao WHERE {w} ORDER BY status='rascunho', confianca DESC, id LIMIT ?", p + [limite]).fetchall():
                out["itens"].append({"tipo": "relacao", **_item_relacao(con, r, com_similares)})
        if "corte" in quer:
            w, p = "c.status='sugerido'", []
            if tema:
                w += " AND c.id IN (SELECT rc.corte_id FROM relacao_corte rc JOIN relacao_tema t ON t.relacao_id=rc.relacao_id WHERE t.tema_id=?)"; p.append(tema)
            out["contagem"]["corte"] = con.execute(f"SELECT count(*) FROM corte c WHERE {w}", p).fetchone()[0]
            for c in con.execute(f"SELECT c.*, f.titulo ft, f.url fu FROM corte c JOIN fonte f ON f.id=c.video_id WHERE {w} ORDER BY c.id LIMIT ?", p + [limite]).fetchall():
                out["itens"].append({
                    "tipo": "corte", "chave": f"corte:{c['id']}", "id": c["id"], "titulo": c["titulo"], "video_id": c["video_id"], "video_titulo": c["ft"],
                    "url": _yt_t(c["fu"], c["inicio_s"]), "inicio_s": c["inicio_s"], "fim_s": c["fim_s"], "justificativa": c["justificativa"], "tema": c["tema"],
                    "status": c["status"],
                    "trechos": [{"id": t[0], "afirmacao": t[1], "inicio_s": t[2], "fim_s": t[3]} for t in con.execute(
                        "SELECT t.id, t.afirmacao, t.inicio_s, t.fim_s FROM corte_trecho ct JOIN trecho t ON t.id=ct.trecho_id WHERE ct.corte_id=? ORDER BY t.ordem", (c["id"],))],
                    "relacoes": [{"id": x[0], "rotulo": x[1], "status": x[2]} for x in con.execute(
                        "SELECT r.id, r.rotulo, r.status FROM relacao_corte rc JOIN relacao r ON r.id=rc.relacao_id WHERE rc.corte_id=? ORDER BY r.id", (c["id"],))]})
        if "evento_natureza" in quer:
            w, p = f"natureza_id IS NULL AND canal NOT IN ({','.join('?' * len(CANAIS_SEM_NATUREZA_POR_DESENHO))})", list(CANAIS_SEM_NATUREZA_POR_DESENHO)
            if tema:
                w += " AND id IN (SELECT evento_id FROM evento_tema WHERE tema_id=?)"; p.append(tema)
            out["contagem"]["evento_natureza"] = con.execute(f"SELECT count(*) FROM evento WHERE {w}", p).fetchone()[0]
            for e in con.execute(f"SELECT * FROM evento WHERE {w} ORDER BY data, id LIMIT ?", p + [limite]).fetchall():
                out["itens"].append({"tipo": "evento_natureza", "chave": f"evento:{e['id']}", **_item_evento(con, e)})
        if "evento_fusao" in quer:
            separados = {tuple(sorted({d["alvo"]["id"], *d["campos"].get("com", [])})) for d in decs
                         if d.get("tipo") == "evento" and d.get("acao") == "manter_separados" and d["id"] not in canc}
            itens = []
            for c in candidatos_fusao(con):
                if len(c["ids"]) < 2 or tuple(sorted(c["ids"])) in separados:
                    continue
                evs = [con.execute("SELECT * FROM evento WHERE id=?", (i,)).fetchone() for i in c["ids"]]
                evs = [e for e in evs if e]
                if len(evs) < 2:
                    continue
                if tema and not con.execute(f"SELECT 1 FROM evento_tema WHERE tema_id=? AND evento_id IN ({','.join('?' * len(evs))})",
                                            [tema] + [e["id"] for e in evs]).fetchone():
                    continue
                itens.append({"tipo": "evento_fusao", "chave": f"fusao:{c['n']}", "n": c["n"], "data": c["data"], "motivo": c["motivo"],
                              "nao_resolvidos": c["nao_resolvidos"], "eventos": [_item_evento(con, e) for e in evs]})
            out["contagem"]["evento_fusao"] = len(itens)
            out["itens"] += itens[:limite]
        if "entidade" in quer:
            sql = """SELECT e.*, (SELECT count(*) FROM relacao r WHERE r.de=e.id OR r.para=e.id) nrel FROM entidade e
                     WHERE e.id IN (SELECT entidade_id FROM v_entidade_tema WHERE tema_id='a-classificar')
                        OR NOT EXISTS (SELECT 1 FROM v_entidade_tema v WHERE v.entidade_id=e.id)"""
            rows = con.execute(sql + " ORDER BY e.id").fetchall()
            out["contagem"]["entidade"] = len(rows)
            for e in rows[:limite]:
                out["itens"].append({"tipo": "entidade", "chave": f"entidade:{e['id']}", "id": e["id"], "nome": e["nome"], "tipo_entidade": e["tipo"],
                                     "descricao": e["descricao"], "n_relacoes": e["nrel"],
                                     "temas": [x[0] for x in con.execute("SELECT tema_id FROM v_entidade_tema WHERE entidade_id=?", (e["id"],))],
                                     "sugestoes_fusao": [x for x in s._sugestoes(con, e["nome"], 4) if x["id"] != e["id"]]})
        out["total"] = sum(out["contagem"].values())
        out["vocabulario"] = {"naturezas": [{"id": r[0], "nome": r[1], "peso": r[2]} for r in con.execute("SELECT id, nome, peso FROM natureza ORDER BY peso DESC")],
                              "temas": [{"id": r[0], "nome": r[1]} for r in con.execute("SELECT id, nome FROM tema ORDER BY ordem, id")],
                              "tipos_relacao": s.TIPOS_RELACAO}
    return out


def listar_decisoes_core(limite=20):
    decs = ler_decisoes()
    canc = desfeitas(decs)
    return {"ok": True, "arquivo": str(caminho_decisoes()), "total": len(decs),
            "decisoes": [dict(_publico(d), desfeita=d["id"] in canc) for d in decs[-max(1, int(limite)):]][::-1]}


# --------------------------------------------------------------------------- ferramentas MCP
def listar_pendencias(tipo: str | None = None, tema: str | None = None, limite: int = 50) -> dict:
    """Fila de revisão. `tipo` ∈ relacao (status revisar/rascunho, com evidências, trechos de origem, relações do mesmo par e
    `similares` por embedding para decidir fusão), corte (sugerido), evento_natureza (eventos sem natureza; a timeline Brasil e os
    marcos de violência ficam de fora por desenho), evento_fusao (candidatos de data/curadoria/eventos-candidatos.md ainda não decididos),
    entidade (em 'a-classificar' ou sem tema). `tema` filtra por slug de tema. `limite` vale por tipo; `contagem` traz os totais."""
    return listar_pendencias_core(tipo, tema, limite)


def revisar_relacao(id: int, acao: str, alvo_id: int | None = None, campos: dict | None = None, motivo: str | None = None) -> dict:
    """Decide uma relação. acao: aprovar (status 'publicada', mantém origem; aceita `campos` para corrigir antes), descartar (status
    'descartada'; nada é apagado), fundir_em (move evidências, trechos, cortes, eventos e temas para `alvo_id` e descarta esta),
    editar (`campos` ⊂ rotulo, descricao, tipo, subtipo, natureza, confianca, periodo_inicio, periodo_fim, valor_brl, valor_texto,
    resposta, de, para, temas). Regrava data/dump.sql e grava a decisão em data/curadoria/decisoes.jsonl (desfazível com desfazer)."""
    return revisar_relacao_core(id, acao, alvo_id, campos, motivo)


def revisar_corte(id: int, acao: str, campos: dict | None = None, motivo: str | None = None) -> dict:
    """Decide um corte sugerido. acao: aprovar (status 'aprovado'), descartar ('descartado') ou editar (`campos` ⊂ titulo, inicio_s,
    fim_s, justificativa, tema, url_publicado). Grava em decisoes.jsonl."""
    return revisar_corte_core(id, acao, campos, motivo)


def revisar_evento(id: str, acao: str, alvo_id: str | None = None, natureza: str | None = None, campos: dict | None = None,
                   motivo: str | None = None) -> dict:
    """Decide um evento. acao: natureza (`natureza` em qualquer vocabulário: doc/inv/rep/ale/nc, canônico...), fundir_em (funde `id` no
    evento `alvo_id` com a mesma regra de eventos-fusoes.json, que também é atualizado; exige a mesma data), editar (`campos` ⊂ titulo,
    descricao, data, data_aprox, data_texto, peso, contexto, resposta, valor_brl, natureza, temas), manter_separados (fecha um candidato a
    fusão: `alvo_id` = o outro evento ou lista). Grava em decisoes.jsonl."""
    return revisar_evento_core(id, acao, alvo_id, natureza, campos, motivo)


def fundir_entidade(de: str, para: str, motivo: str | None = None) -> dict:
    """Funde a entidade `de` em `para`: realoca relações (as que colidem com uma existente são fundidas nela; a relação entre as duas
    é apagada), eventos, aliases, trechos, mandatos, dossiê etc.; grava o nome de `de` como alias 'nome_antigo' de `para` e apaga `de`.
    Idempotente. Recusa nó da teia original (use scripts/fusoes.json). Grava em decisoes.jsonl."""
    return fundir_entidade_core(de, para, motivo)


def desfazer(decisao_id: str, motivo: str | None = None) -> dict:
    """Desfaz uma decisão pelo log de linhas (antes/depois) gravado no sqlite e appenda {tipo:'desfazer'} em decisoes.jsonl
    (aplicar_decisoes.py pula as desfeitas). Recusa se decisões posteriores mexeram nas mesmas linhas (desfaça-as antes)."""
    return desfazer_core(decisao_id, motivo)


def listar_decisoes(limite: int = 20) -> dict:
    """Últimas decisões de data/curadoria/decisoes.jsonl (mais nova primeiro), com `desfeita`. Use o `id` em desfazer."""
    return listar_decisoes_core(limite)


FERRAMENTAS = (listar_pendencias, revisar_relacao, revisar_corte, revisar_evento, fundir_entidade, desfazer, listar_decisoes)
