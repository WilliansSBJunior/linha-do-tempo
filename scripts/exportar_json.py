#!/usr/bin/env python3
"""Exporta o banco para JSON (e regenera data/dump.sql). Só lê o banco.

Gera em data/: entities.json, teia.json, origens.json, series.json, mapa_indices.json, dossie.json, pares.json, temas.json, dump.sql.
Uso: python3 scripts/exportar_json.py [--db caminho.sqlite]
"""
import argparse
import json
import re
from collections import OrderedDict, defaultdict

from comum import DATA, DUMP, SQLITE, TS_MIGRACAO, conectar, gerar_dump

PSEUDO_PARTIDOS = {"Ex-ministros e consultores", "Órgãos e partidos"}
VERSAO = 1


def _num(v):
    """REAL do SQLite -> int quando for inteiro (BRL inteiro no original)."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _st_inverso(con):
    d = {r["natureza_id"]: r["codigo_externo"] for r in con.execute("SELECT * FROM natureza_mapa WHERE sistema='teia'")}
    return d


def _fontes(con, tabela, col):
    out = defaultdict(list)
    rot = "COALESCE(x.rotulo, e.veiculo)" if tabela == "evento_evidencia" else "e.veiculo"
    for r in con.execute(f"""SELECT x.{col} AS dono, {rot} AS veiculo, e.url FROM {tabela} x JOIN evidencia e ON e.id=x.evidencia_id
                             ORDER BY x.{col}, x.ordem"""):
        out[r["dono"]].append([r["veiculo"], r["url"]])
    return out


def _temas_de(con, tabela, col):
    """dono -> [tema_id] na ordem de tema.ordem."""
    out = defaultdict(list)
    for r in con.execute(f"SELECT x.{col} AS dono, x.tema_id FROM {tabela} x JOIN tema t ON t.id=x.tema_id ORDER BY x.{col}, t.ordem, t.id"):
        out[r["dono"]].append(r["tema_id"])
    return out


def mapa_indices(con):
    n = OrderedDict((str(r["ind_legado"]), r["id"]) for r in
                    con.execute("SELECT id, ind_legado FROM entidade WHERE ind_legado IS NOT NULL ORDER BY ind_legado"))
    ev = OrderedDict()
    for r in con.execute("SELECT id, origem_ref FROM evento WHERE origem_ref LIKE '%teia:EV[%'"):
        ev[int(re.search(r"teia:EV\[(\d+)\]", r["origem_ref"]).group(1))] = r["id"]
    for r in con.execute("SELECT evento_id, origem_ref_original FROM evento_alias WHERE origem_ref_original LIKE '%teia:EV[%'"):
        ev[int(re.search(r"teia:EV\[(\d+)\]", r["origem_ref_original"]).group(1))] = r["evento_id"]  # fundido: aponta para o evento mantido
    alias = OrderedDict((r["alias"], r["evento_id"]) for r in con.execute("SELECT alias, evento_id FROM evento_alias ORDER BY alias"))
    return OrderedDict([
        ("versao", VERSAO),
        ("descricao", "N: índice antigo (posição em teia.N) -> slug de entidade. EV: índice antigo em teia.EV -> id de evento "
                      "(vários índices podem apontar para o mesmo id: eventos fundidos pela curadoria). evento_alias: id fundido -> id mantido."),
        ("N", n), ("EV", OrderedDict((str(k), ev[k]) for k in sorted(ev))), ("evento_alias", alias)])


def montar_teia(con):
    st_inv = _st_inverso(con)
    ents = [dict(r) for r in con.execute("SELECT * FROM entidade WHERE ind_legado IS NOT NULL ORDER BY ind_legado")]
    idx = {e["id"]: e["ind_legado"] for e in ents}
    cats = [[r["id"], r["nome"]] for r in con.execute("SELECT id, nome FROM categoria WHERE ordem>0 ORDER BY ordem")]
    fam, lig = {}, {}
    for r in con.execute("SELECT de, para, origem_ref FROM relacao WHERE origem_ref LIKE 'N[%'"):
        (fam if r["origem_ref"].endswith(".fam_de") else lig)[r["de"]] = r["para"]
    N = []
    for e in ents:
        n = {"n": e["nome"], "c": e["categoria_id"], "t": e["tipo"], "g": e["cargo"] or "", "d": e["descricao"] or "", "id": e["id"]}
        if e["grupo"] in PSEUDO_PARTIDOS:
            n["p"] = e["grupo"]
        else:
            if e["grupo"]:
                n["sg"] = e["grupo"]
            if e["partido"]:
                n["p"] = e["partido"]
        if e["id"] in fam:
            n["fam_de"], n["fam_de_id"] = idx[fam[e["id"]]], fam[e["id"]]
        if e["id"] in lig:
            n["lig_de"], n["lig_de_id"] = idx[lig[e["id"]]], lig[e["id"]]
        N.append(n)
    fontes_rel = _fontes(con, "relacao_evidencia", "relacao_id")
    tema_rel, tema_ev = _temas_de(con, "relacao_tema", "relacao_id"), _temas_de(con, "evento_tema", "evento_id")
    por_aresta = defaultdict(dict)
    for r in con.execute("SELECT * FROM relacao WHERE origem_ref LIKE 'E[%'"):
        m = re.fullmatch(r"E\[(\d+)\]\.r\[(\d+)\]", r["origem_ref"])
        ei, ri = int(m.group(1)), int(m.group(2))
        rel = OrderedDict([
            ("a", idx[r["de"]]), ("b", idx[r["para"]]), ("a_id", r["de"]), ("b_id", r["para"]),
            ("rot", r["rotulo"]), ("desc", r["descricao"]), ("st", st_inv[r["natureza_id"]]), ("tipo", r["tipo"]),
            ("de", None if r["periodo_inicio"] is None else int(r["periodo_inicio"])),
            ("ate", None if r["periodo_fim"] is None else int(r["periodo_fim"])),
            ("val", _num(r["valor_brl"])), ("resp", r["resposta"]), ("f", fontes_rel.get(r["id"], [])), ("tema", tema_rel[r["id"]])])
        por_aresta[ei][ri] = rel
    leg = {r["e_idx"]: (r["a"], r["b"]) for r in con.execute("SELECT e_idx, a, b FROM aresta_legado")}
    E = []
    for ei in sorted(por_aresta):
        rs = [por_aresta[ei][k] for k in sorted(por_aresta[ei])]
        a, b = leg[ei]
        E.append(OrderedDict([("a", idx[a]), ("b", idx[b]), ("r", rs)]))
    # EV
    fontes_ev = _fontes(con, "evento_evidencia", "evento_id")
    ents_ev = defaultdict(list)
    for r in con.execute("SELECT evento_id, entidade_id FROM evento_entidade ORDER BY evento_id, ordem"):
        ents_ev[r["evento_id"]].append(r["entidade_id"])
    evs = []
    for r in con.execute("SELECT * FROM evento WHERE origem_ref LIKE '%teia:EV[%'"):
        i = int(re.search(r"teia:EV\[(\d+)\]", r["origem_ref"]).group(1))
        ev = OrderedDict([("d", r["data_texto"] or r["data"]), ("y", r["ano"]), ("t", r["titulo"]), ("x", r["descricao"]),
                          ("p", r["peso"]), ("f", fontes_ev.get(r["id"], [])),
                          ("n", [idx[s] for s in ents_ev[r["id"]]]), ("ids", ents_ev[r["id"]]), ("id", r["id"]), ("tema", tema_ev[r["id"]])])
        if r["natureza_id"]:
            ev["st"] = st_inv[r["natureza_id"]]
        evs.append((i, ev))
    EV = [e for _, e in sorted(evs, key=lambda x: x[0])]
    # notas da teia
    SINT = OrderedDict((r["chave"], r["texto"]) for r in con.execute(
        "SELECT chave, texto FROM nota WHERE pagina='teia' AND tipo='sintese' ORDER BY ordem"))
    nots = defaultdict(list)
    for r in con.execute("SELECT nota_id, entidade_id FROM nota_entidade ORDER BY nota_id, ordem"):
        nots[r["nota_id"]].append(r["entidade_id"])
    SEM = []
    for r in con.execute("SELECT * FROM nota WHERE pagina='teia' AND tipo='nao_sustentado' ORDER BY ordem"):
        SEM.append(OrderedDict([("l", r["titulo"]), ("x", r["texto"]), ("k", r["chave"]),
                                ("n", [idx[s] for s in nots[r["id"]]]), ("ids", nots[r["id"]])]))
    LAC = [r["texto"] for r in con.execute("SELECT texto FROM nota WHERE pagina='teia' AND tipo='lacuna' ORDER BY ordem")]
    # NUM
    NUM = OrderedDict()
    campos = {"master.ativos_brl_bi": "ativos_brl_bi", "master.patrimonio_liquido_brl_bi": "patrimonio_liquido_brl_bi",
              "master.captacao_brl_bi": "captacao_brl_bi", "master.lucro_brl_bi": "lucro_brl_bi"}
    for r in con.execute("""SELECT s.*, e.url FROM serie s LEFT JOIN evidencia e ON e.id=s.evidencia_id
                            WHERE s.indicador_id LIKE 'master.%' ORDER BY s.ano, s.indicador_id"""):
        d = NUM.setdefault(str(r["ano"]), OrderedDict())
        d[campos[r["indicador_id"]]] = r["valor"]
        d["obs"] = r["obs"]
        d["fonte"] = r["url"]
    for r in con.execute("SELECT chave, texto FROM nota WHERE pagina='teia' AND tipo='aviso' AND chave LIKE 'NUM.%'"):
        ano = r["chave"].split(".")[1]
        NUM[ano]["fontes_adicionais"] = r["texto"].split("\n")
    for ano in NUM:
        NUM[ano] = OrderedDict((k, NUM[ano].get(k)) for k in
                               ["ativos_brl_bi", "patrimonio_liquido_brl_bi", "captacao_brl_bi", "lucro_brl_bi", "obs", "fonte"]
                               + (["fontes_adicionais"] if "fontes_adicionais" in NUM[ano] else []))
    # PREC
    prec = []
    for r in con.execute("SELECT * FROM evento WHERE canal='precatorios'"):
        i = int(re.fullmatch(r"PREC\[(\d+)\]", r["origem_ref"]).group(1))
        prec.append((i, OrderedDict([("d", r["data_texto"] or r["data"]), ("t", r["titulo"]), ("x", r["descricao"]),
                                     ("st", st_inv[r["natureza_id"]]), ("f", fontes_ev.get(r["id"], [])), ("tema", tema_ev[r["id"]])])))
    PREC = [p for _, p in sorted(prec, key=lambda x: x[0])]
    return OrderedDict([("cats", cats), ("N", N), ("E", E), ("EV", EV), ("SINT", SINT), ("SEM", SEM), ("LAC", LAC),
                        ("NUM", NUM), ("PREC", PREC)])


def montar_origens(con):
    st_inv = _st_inverso(con)
    fontes_ev = _fontes(con, "evento_evidencia", "evento_id")
    tema_ev = _temas_de(con, "evento_tema", "evento_id")
    evs = []
    for r in con.execute("SELECT * FROM evento WHERE origem_ref LIKE '%origens:EV[%'"):
        k = int(re.search(r"origens:EV\[(\d+)\]", r["origem_ref"]).group(1))
        evs.append((k, OrderedDict([
            ("id", r["id"]), ("ch", r["canal"]), ("d", r["data_texto"] or r["data"]), ("y", r["ano"]), ("t", r["titulo"]),
            ("x", r["descricao"]), ("st", st_inv[r["natureza_id"]]), ("r", r["resposta"] or ""), ("v", _num(r["valor_brl"])),
            ("f", fontes_ev.get(r["id"], [])), ("tema", tema_ev[r["id"]])])))
    EV = [e for _, e in sorted(evs, key=lambda x: x[0])]
    NARR, LAC = OrderedDict(), OrderedDict()
    for r in con.execute("SELECT chave, texto FROM nota WHERE pagina='origens' AND tipo='narrativa' ORDER BY id"):
        NARR.setdefault(r["chave"], []).append(r["texto"])
    for r in con.execute("SELECT chave, texto FROM nota WHERE pagina='origens' AND tipo='lacuna' ORDER BY id"):
        LAC.setdefault(r["chave"], []).append(r["texto"])
    SINT = OrderedDict((r["chave"], r["texto"]) for r in con.execute(
        "SELECT chave, texto FROM nota WHERE pagina='origens' AND tipo='sintese' ORDER BY ordem"))
    SEM = [OrderedDict([("l", r["titulo"]), ("x", r["texto"]), ("k", r["chave"])]) for r in con.execute(
        "SELECT * FROM nota WHERE pagina='origens' AND tipo='nao_sustentado' ORDER BY ordem")]
    return OrderedDict([("EV", EV), ("NARR", NARR), ("SINT", SINT), ("SEM", SEM), ("LAC", LAC)])


def _sem_nulos(d):
    return OrderedDict((k, v) for k, v in d.items() if v is not None and v != "")


def montar_series(con):
    inds = [OrderedDict(_sem_nulos(dict(r))) for r in con.execute(
        "SELECT id, nome, unidade, dominio, descricao, fonte_padrao FROM indicador ORDER BY id")]
    series = OrderedDict()
    for r in con.execute("""SELECT s.indicador_id, s.ano, s.dimensao, s.valor, s.valor_texto, s.qualidade, e.url AS evidencia, s.obs
                            FROM serie s LEFT JOIN evidencia e ON e.id=s.evidencia_id ORDER BY s.indicador_id, s.ano, s.dimensao"""):
        d = _sem_nulos(dict(r))
        d["valor"] = r["valor"] if r["valor"] is None else _num(r["valor"])
        d.pop("indicador_id")
        if d["valor"] is None:
            del d["valor"]
        if d["qualidade"] == "oficial":
            del d["qualidade"]
        series.setdefault(r["indicador_id"], []).append(d)
    rank = [OrderedDict(_sem_nulos(dict(r))) for r in con.execute(
        """SELECT r.ano, r.entidade_id, r.posicao, r.setor, r.setor_k, r.lucro_brl_bi, r.receita_brl_bi, r.pct_total, r.controle, r.holding, r.derivado,
                  r.cobertura, r.obs, e.url AS evidencia FROM ranking_empresa r LEFT JOIN evidencia e ON e.id=r.evidencia_id
           ORDER BY r.ano, r.posicao""")]
    mand = [OrderedDict(_sem_nulos(dict(r))) for r in con.execute(
        "SELECT entidade_id, cargo, orgao_id, partido, uf, inicio, fim, motivo, votos, periodo_texto FROM mandato ORDER BY id")]
    banc = [OrderedDict(_sem_nulos(dict(r))) for r in con.execute(
        "SELECT legislatura, ano, casa, partido_id, nome_epoca, cadeiras, campo FROM bancada ORDER BY ano, casa, cadeiras DESC, partido_id")]
    return OrderedDict([("versao", VERSAO), ("gerado_em", TS_MIGRACAO), ("indicadores", inds), ("series", series),
                        ("ranking_empresa", rank), ("mandato", mand), ("bancada", banc)])


def montar_entities(con):
    ents = []
    alias_por = defaultdict(list)
    for r in con.execute("SELECT alias, alias_norm, entidade_id FROM entidade_alias ORDER BY entidade_id, tipo_alias, alias"):
        alias_por[r["entidade_id"]].append(r["alias"])
    tema_ent = _temas_de(con, "v_entidade_tema", "entidade_id")
    for r in con.execute("""SELECT * FROM entidade ORDER BY (ind_legado IS NULL), ind_legado, id"""):
        al = [a for a in dict.fromkeys(alias_por[r["id"]]) if a != r["nome"]]
        d = OrderedDict([("id", r["id"]), ("nome", r["nome"]), ("tipo", r["tipo"]), ("categoria", r["categoria_id"]),
                         ("grupo", r["grupo"]), ("partido", r["partido"]), ("campo", r["campo"]), ("cargo", r["cargo"]),
                         ("descricao", r["descricao"]), ("uf", r["uf"]), ("indice_legado", r["ind_legado"]),
                         ("origem", r["origem"]), ("aliases", al), ("temas", tema_ent[r["id"]])])
        ents.append(d)
    por_norm = defaultdict(set)
    for r in con.execute("SELECT alias_norm, entidade_id FROM entidade_alias"):
        por_norm[r["alias_norm"]].add(r["entidade_id"])
    indice = OrderedDict((k, next(iter(v))) for k, v in sorted(por_norm.items()) if len(v) == 1)
    return OrderedDict([
        ("versao", VERSAO), ("gerado_em", TS_MIGRACAO),
        ("tipos", [r[0] for r in con.execute("SELECT DISTINCT tipo FROM entidade ORDER BY tipo")]),
        ("naturezas", [OrderedDict([("id", r["id"]), ("nome", r["nome"]), ("peso", r["peso"])]) for r in con.execute("SELECT * FROM natureza ORDER BY peso DESC")]),
        ("tipos_relacao", [r[0] for r in con.execute("SELECT DISTINCT tipo FROM relacao ORDER BY tipo")]),
        ("entidades", ents), ("indice_alias", indice)])


# ---------------------------------------------------------------- dossiê e pares (formato embutido nas páginas)
def _meta(con, chave):
    r = con.execute("SELECT valor FROM meta WHERE chave=?", (chave,)).fetchone()
    return r[0] if r else None


def _notas(con, pagina, chave):
    return con.execute("SELECT * FROM nota WHERE pagina=? AND chave=? ORDER BY ordem, id", (pagina, chave)).fetchall()


def _texto(con, pagina, chave):
    r = _notas(con, pagina, chave)
    return r[0]["texto"] if r else ""


def _lista(con, pagina, chave):
    return [r["texto"] for r in _notas(con, pagina, chave)]


def _pares_txt(con, pagina, chave):
    """Listas de [a, b] guardadas como titulo=a, texto='a | b'."""
    return [[r["titulo"], r["texto"][len(r["titulo"]) + 3:]] for r in _notas(con, pagina, chave)]


def _eventos_brb(con, st_inv):
    """30 eventos do dossiê.brb.eventos na ordem original: os que ainda existem + os fundidos (evento_alias.original_json)."""
    itens = []
    fontes = _fontes(con, "evento_evidencia", "evento_id")
    for r in con.execute("SELECT * FROM evento WHERE canal='brb'"):
        itens.append((int(re.fullmatch(r"dossie\.brb\.eventos\[(\d+)\]", r["origem_ref"]).group(1)),
                      dict(r), fontes.get(r["id"], [])))
    for r in con.execute("SELECT original_json FROM evento_alias WHERE canal_original='brb'"):
        o = json.loads(r["original_json"])
        itens.append((int(re.fullmatch(r"dossie\.brb\.eventos\[(\d+)\]", o["origem_ref"]).group(1)), o, [[f[0], f[1]] for f in o["fontes"]]))
    out = []
    for _, r, src in sorted(itens, key=lambda x: x[0]):
        ctx = r["contexto"] or ""
        ev = OrderedDict([("d", r["data_texto"] or r["data"]), ("t", r["titulo"]), ("x", r["descricao"] or ""),
                          ("st", st_inv[r["natureza_id"]]), ("lado", re.match(r"lado: (\w+)", ctx).group(1))])
        if "; crítico" in ctx:
            ev["critico"] = True
        ev["src"] = src
        out.append(ev)
    return out


def montar_dossie(con):
    st_inv = _st_inverso(con)
    urls_par = defaultdict(list)
    for r in con.execute("""SELECT x.par_id, x.rotulo, e.url FROM dossie_par_evidencia x JOIN evidencia e ON e.id=x.evidencia_id ORDER BY x.par_id, x.ordem"""):
        urls_par[r["par_id"]].append([r["rotulo"], r["url"]])
    pares = []
    for r in con.execute("SELECT * FROM dossie_par WHERE sub=0 ORDER BY ordem"):
        pares.append(OrderedDict([
            ("ator", r["ator_texto"]), ("campo", r["campo"] or ""), ("partido", r["partido"] or ""), ("alavanca", r["alavanca"] or ""),
            ("recebeu", r["recebeu"] or ""), ("ato", r["ato"] or ""), ("liga", r["liga"]), ("liga_x", r["liga_x"] or ""),
            ("st", st_inv[r["natureza_id"]]), ("estagio", r["estagio"] or ""), ("resp", r["resposta"] or ""), ("src", urls_par[r["id"]])]))
    entes = [OrderedDict([("n", r["nome_texto"]), ("uf", r["uf"] or ""), ("v", _num(r["valor_mi"])), ("gov", r["governante"] or ""),
                          ("p", r["partido"] or ""), ("x", r["obs"] or ""), ("st", st_inv[r["natureza_id"]])])
             for r in con.execute("SELECT * FROM previdencia_ente ORDER BY ordem")]

    def pagamentos(cat):
        out = []
        for r in con.execute("SELECT * FROM pagamento WHERE categoria=? ORDER BY ordem", (cat,)):
            d = OrderedDict([("n", r["nome_texto"]), ("v", _num(r["valor_mi"]))])
            if cat == "contrato":
                d["g"] = r["grupo"] or ""
            if cat == "doacao":
                d["de"] = r["de_texto"] or ""
            out.append(d)
        return out

    def limites(tipo):
        return list(con.execute("SELECT * FROM limite WHERE tipo=? ORDER BY ordem", (tipo,)))

    placar = []
    for r in _notas(con, "dossie", "tese.placar"):
        arena, resultado = r["titulo"].split(": ", 1)
        placar.append(OrderedDict([("arena", arena), ("resultado", resultado), ("x", r["texto"])]))
    status = OrderedDict((k, _texto(con, "dossie", f"meta.status.{k}")) for k in ("doc", "inv", "rep", "ale", "nc"))
    return OrderedDict([
        ("meta", OrderedDict([("titulo", _meta(con, "dossie.titulo")), ("data_base", _meta(con, "dossie.data_base")),
                              ("aviso", _texto(con, "dossie", "meta.aviso")), ("status", status),
                              ("paginas", json.loads(_texto(con, "dossie", "meta.paginas")))])),
        ("tese", OrderedDict([("pergunta", _texto(con, "dossie", "tese.pergunta")), ("resposta", _texto(con, "dossie", "tese.resposta")),
                              ("placar", placar)])),
        ("brb", OrderedDict([("hipotese", _texto(con, "dossie", "brb.hipotese")), ("sustenta", _lista(con, "dossie", "brb.sustenta")),
                             ("nao_sustenta", _lista(con, "dossie", "brb.nao_sustenta")),
                             ("valores", _pares_txt(con, "dossie", "brb.valores")), ("eventos", _eventos_brb(con, st_inv)),
                             ("alternativas", _pares_txt(con, "dossie", "brb.alternativas"))])),
        ("mercado", OrderedDict([("intro", _texto(con, "dossie", "mercado.intro")), ("pares", pares)])),
        ("maquina", OrderedDict([("intro", _texto(con, "dossie", "maquina.intro")),
                                 ("indicios", [OrderedDict([("t", r["titulo"]), ("x", r["texto"]), ("contra", r["contra"]), ("forca", r["forca"])])
                                               for r in con.execute("SELECT * FROM indicio_maquina ORDER BY ordem")])])),
        ("previdencia", OrderedDict([("intro", _texto(con, "dossie", "previdencia.intro")), ("entes", entes),
                                     ("intermediarios", _pares_txt(con, "dossie", "previdencia.intermediarios")),
                                     ("contraprova", _lista(con, "dossie", "previdencia.contraprova")),
                                     ("fonte", _pares_txt(con, "dossie", "previdencia.fonte"))])),
        ("dinheiro", OrderedDict([("intro", _texto(con, "dossie", "dinheiro.intro")), ("contratos", pagamentos("contrato")),
                                  ("midia", pagamentos("midia")), ("doacoes", pagamentos("doacao")),
                                  ("notas", _lista(con, "dossie", "dinheiro.notas")), ("fonte", _pares_txt(con, "dossie", "dinheiro.fonte"))])),
        ("limites", OrderedDict([("derrubado", [[r["titulo"], r["texto"]] for r in limites("derrubado")]),
                                 ("aberto", [r["texto"] for r in limites("aberto")]),
                                 ("agenda", [[r["data_texto"], r["texto"]] for r in limites("agenda")])]))])


def montar_pares(con):
    iso_de = {r["entidade_id"]: r["alias"] for r in con.execute(
        "SELECT a.entidade_id, a.alias FROM entidade_alias a JOIN entidade e ON e.id=a.entidade_id WHERE e.tipo='pais' AND a.tipo_alias='sigla'")}
    nome_de = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM entidade WHERE tipo='pais'")}
    ordem = json.loads(_meta(con, "pares.ordem_paises"))
    paises = OrderedDict((iso, next(nome_de[e] for e, i in iso_de.items() if i == iso)) for iso in ordem)
    inds = OrderedDict()
    pisa_ids = {"pares.pisa_leitura", "pares.pisa_matematica", "pares.pisa_ciencias", "pares.pisa_matematica_estado"}
    for r in con.execute("SELECT * FROM indicador WHERE dominio='pares' ORDER BY rowid"):
        if r["id"] in pisa_ids:
            continue
        m = re.fullmatch(r"grupo=(.*); fmt=(.*)", r["descricao"])
        inds[r["id"][len("pares."):]] = OrderedDict([("grupo", m.group(1)), ("nome", r["nome"]), ("unidade", r["unidade"]),
                                                       ("fonte", r["fonte_padrao"]), ("fmt", m.group(2)), ("dados", OrderedDict())])
    pisa = OrderedDict()
    for r in con.execute("SELECT s.indicador_id, s.ano, s.dimensao, s.valor, s.obs FROM serie s JOIN indicador i ON i.id=s.indicador_id WHERE i.dominio='pares' ORDER BY s.indicador_id, s.dimensao, s.ano"):
        iso = re.match(r"pais=([A-Z]{3})", r["dimensao"]).group(1)
        if r["indicador_id"] in pisa_ids:
            d = pisa.setdefault(iso, OrderedDict()).setdefault(str(r["ano"]), OrderedDict())
            if r["indicador_id"] == "pares.pisa_matematica_estado":
                d.setdefault("matematica_por_estado", OrderedDict())[r["dimensao"].split("estado=", 1)[1]] = _num(r["valor"])
            else:
                d[r["indicador_id"].split("pisa_", 1)[1]] = _num(r["valor"])
            if r["obs"]:
                d["cobertura"] = r["obs"]
        else:
            inds[r["indicador_id"][len("pares."):]]["dados"].setdefault(iso, OrderedDict())[str(r["ano"])] = _num(r["valor"])
    pi = con.execute("SELECT * FROM indicador WHERE id='pares.pisa_leitura'").fetchone()
    foruns = OrderedDict()
    for iso in ordem:
        pais = next(e for e, i in iso_de.items() if i == iso)
        rows = {r["forum"]: r for r in con.execute("SELECT * FROM forum WHERE pais_entidade_id=?", (pais,))}
        f = OrderedDict([("G20", rows["G20"]["status_texto"]), ("BRICS", rows["BRICS"]["status_texto"]), ("OCDE", rows["OCDE"]["status_texto"]),
                         ("CSNU", json.loads(rows["CSNU"]["anos"]) if rows["CSNU"]["anos"] else rows["CSNU"]["status_texto"]),
                         ("nuclear", rows["nuclear"]["status_texto"] == "sim")])
        if rows["nuclear"]["primeiro_teste"] is not None:
            f["primeiro_teste_nuclear"] = rows["nuclear"]["primeiro_teste"]
        foruns[iso] = f
    notas = OrderedDict()
    for grp in ("pib_idh", "educacao", "peso_economico", "influencia_inovacao"):
        notas[grp] = _lista(con, "pares", f"notas.{grp}")
    return OrderedDict([("gerado_em", _meta(con, "pares.gerado_em")), ("anos", json.loads(_meta(con, "pares.anos"))), ("paises", paises),
                        ("indicadores", inds), ("pisa", OrderedDict([("nome", pi["descricao"]), ("fonte", pi["fonte_padrao"]), ("dados", pisa)])),
                        ("foruns", foruns), ("notas", notas)])


def montar_temas(con):
    """Temas com contagens e a pertinência de relações (id), eventos (id) e entidades (id, derivada de v_entidade_tema)."""
    def membros(tabela, col):
        out = defaultdict(list)
        for r in con.execute(f"SELECT x.tema_id, x.{col} AS dono FROM {tabela} x ORDER BY x.tema_id, x.{col}"):
            out[r["tema_id"]].append(r["dono"])
        return out
    rel, ev, ent = membros("relacao_tema", "relacao_id"), membros("evento_tema", "evento_id"), membros("v_entidade_tema", "entidade_id")
    temas = [OrderedDict([("id", r["id"]), ("nome", r["nome"]), ("descricao", r["descricao"]), ("cor", r["cor"]), ("ordem", r["ordem"]),
                          ("principal", bool(r["principal"])), ("n_relacoes", len(rel[r["id"]])), ("n_eventos", len(ev[r["id"]])),
                          ("n_entidades", len(ent[r["id"]]))]) for r in con.execute("SELECT * FROM tema ORDER BY ordem, id")]
    return OrderedDict([("versao", VERSAO), ("gerado_em", TS_MIGRACAO),
                        ("descricao", "Tema é N:N. `relacoes` usa relacao.id e `eventos` usa evento.id; `entidades` é derivada (view v_entidade_tema): "
                                      "a entidade pertence ao tema se tem relação/evento nele (ou mandato/bancada/ranking -> brasil-ano-a-ano, forum -> pares, dossiê -> caso-master). "
                                      "Cada relação/evento de teia.json e origens.json traz `tema`."),
                        ("temas", temas), ("relacoes", OrderedDict((t["id"], rel[t["id"]]) for t in temas)),
                        ("eventos", OrderedDict((t["id"], ev[t["id"]]) for t in temas)),
                        ("entidades", OrderedDict((t["id"], ent[t["id"]]) for t in temas))])


def salvar(nome, obj):
    (DATA / nome).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def todos(con):
    return {"entities.json": montar_entities(con), "teia.json": montar_teia(con), "origens.json": montar_origens(con),
            "series.json": montar_series(con), "mapa_indices.json": mapa_indices(con),
            "dossie.json": montar_dossie(con), "pares.json": montar_pares(con), "temas.json": montar_temas(con)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(SQLITE))
    a = ap.parse_args()
    con = conectar(a.db)
    for nome, obj in todos(con).items():
        salvar(nome, obj)
        print("escrito data/" + nome)
    gerar_dump(con, DUMP)
    print("escrito data/dump.sql")


if __name__ == "__main__":
    main()
