#!/usr/bin/env python3
"""Valida o banco: integridade, contagens, órfãos e round-trip contra data/raw. Sai com código 1 em qualquer falha.

Uso: python3 scripts/validar.py [--db caminho.sqlite]
Se data/*.json e data/dump.sql existirem, confere também que estão iguais ao que o banco exporta agora.
"""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import exportar_json as ex
from comum import CURADORIA, DATA, DUMP, RAW, SQLITE, conectar, gerar_dump, normalizar_url
from slug import slug_para_nome

FALHAS = []


def falha(msg):
    FALHAS.append(msg)
    print("  FALHA:", msg)


def secao(t):
    print(f"\n== {t} ==")


def tabela(titulo, linhas):
    print(titulo)
    for k, v in linhas:
        print(f"  {k:<45} {v}")


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def esperar(nome, real, esperado):
    ok = real == esperado
    print(f"  {'ok ' if ok else 'ERR'} {nome}: {real}" + ("" if ok else f" (esperado {esperado})"))
    if not ok:
        falha(f"{nome}: {real} != {esperado}")


def urls(f):
    return {normalizar_url(u) for _, u in f}


def contagens(con, raw, orig):
    secao("Contagens")
    tabela("entidade:", [(r["origem"], r["c"]) for r in q(con, "SELECT origem, count(*) c FROM entidade GROUP BY origem ORDER BY origem")]
           + [("TOTAL", q(con, "SELECT count(*) FROM entidade")[0][0])])
    tabela("entidade_alias:", [("total", q(con, "SELECT count(*) FROM entidade_alias")[0][0])])
    rel_origem = [("E[].r (teia)", "origem_ref LIKE 'E[%'"), ("fam_de", "origem_ref LIKE '%.fam_de'"), ("lig_de", "origem_ref LIKE '%.lig_de'"),
                  ("linha_do_tempo (mandato/filiacao)", "origem='linha_do_tempo'"), ("classificador/manual (MCP)", "origem IN ('classificador','manual','origens')")]
    tabela("relacao por origem:", [(n, q(con, f"SELECT count(*) FROM relacao WHERE {w}")[0][0]) for n, w in rel_origem]
           + [("TOTAL", q(con, "SELECT count(*) FROM relacao")[0][0])])
    tabela("evento por canal:", [(r["canal"], r["c"]) for r in q(con, "SELECT canal, count(*) c FROM evento GROUP BY canal ORDER BY canal")]
           + [("TOTAL", q(con, "SELECT count(*) FROM evento")[0][0])])
    tabela("evidencia / ligações:", [("evidencia", q(con, "SELECT count(*) FROM evidencia")[0][0]),
                                      ("relacao_evidencia", q(con, "SELECT count(*) FROM relacao_evidencia")[0][0]),
                                      ("evento_evidencia", q(con, "SELECT count(*) FROM evento_evidencia")[0][0]),
                                      ("evento_entidade", q(con, "SELECT count(*) FROM evento_entidade")[0][0])])
    tabela("serie por domínio:", [(r["dominio"], r["c"]) for r in q(con, "SELECT i.dominio, count(*) c FROM serie s JOIN indicador i ON i.id=s.indicador_id GROUP BY i.dominio ORDER BY i.dominio")]
           + [("TOTAL serie", q(con, "SELECT count(*) FROM serie")[0][0]), ("indicador", q(con, "SELECT count(*) FROM indicador")[0][0])])
    tabela("outras:", [("nota " + f"{r['pagina']}/{r['tipo']}", r["c"]) for r in q(con, "SELECT pagina, tipo, count(*) c FROM nota GROUP BY pagina, tipo ORDER BY pagina, tipo")]
           + [(t, q(con, f"SELECT count(*) FROM {t}")[0][0]) for t in ("ranking_empresa", "mandato", "bancada", "categoria")])

    secao("Histograma de natureza")
    h_teia = {r["natureza_id"]: r["c"] for r in q(con, "SELECT natureza_id, count(*) c FROM relacao WHERE origem_ref LIKE 'E[%' GROUP BY natureza_id")}
    tabela("relacoes da teia (E[].r):", sorted(h_teia.items()))
    esperar("relações da teia por natureza", h_teia, {"documentada": 127, "investigacao": 94, "reportada": 114, "alegacao": 8})
    h_fl = {r["natureza_id"]: r["c"] for r in q(con, "SELECT natureza_id, count(*) c FROM relacao WHERE origem_ref LIKE 'N[%' GROUP BY natureza_id")}
    tabela("relacoes fam_de/lig_de:", sorted(h_fl.items()))
    tabela("eventos por natureza:", [(r["n"], r["c"]) for r in q(con, "SELECT COALESCE(natureza_id,'(NULL)') n, count(*) c FROM evento GROUP BY n ORDER BY n")])
    tabela("eventos com natureza NULL por canal:", [(r["canal"], r["c"]) for r in q(con, "SELECT canal, count(*) c FROM evento WHERE natureza_id IS NULL GROUP BY canal ORDER BY canal")])

    secao("Contagens esperadas (derivadas de data/raw)")
    esperar("relacao E[].r", q(con, "SELECT count(*) FROM relacao WHERE origem_ref LIKE 'E[%'")[0][0], sum(len(e["r"]) for e in raw["E"]))
    esperar("relacao fam_de", q(con, "SELECT count(*) FROM relacao WHERE origem_ref LIKE '%.fam_de'")[0][0], sum("fam_de" in n for n in raw["N"]))
    esperar("relacao lig_de", q(con, "SELECT count(*) FROM relacao WHERE origem_ref LIKE '%.lig_de'")[0][0], sum("lig_de" in n for n in raw["N"]))
    esperar("entidade da teia", q(con, "SELECT count(*) FROM entidade WHERE origem='teia'")[0][0], len(raw["N"]))
    chaves_t = {(e["d"], e["t"]) for e in raw["EV"]}
    chaves_o = {(e["d"], e["t"]) for e in orig["EV"]}
    fund_t = q(con, "SELECT count(*) FROM evento_alias WHERE canal_original IN ('teia','banco','familia','ida','volta')")[0][0]
    fund_p = q(con, "SELECT count(*) FROM evento_alias WHERE canal_original='precatorios'")[0][0]
    fund_b = q(con, "SELECT count(*) FROM evento_alias WHERE canal_original='brb'")[0][0]
    esperar("eventos teia ∪ origens (dedup por (d,t)) menos fundidos pela curadoria", q(con, "SELECT count(*) FROM evento WHERE canal IN ('teia','banco','familia','ida','volta')")[0][0], len(chaves_t | chaves_o) - fund_t)
    esperar("eventos de origens (89) preservados com id", q(con, "SELECT count(*) FROM evento WHERE origem_ref LIKE '%origens:EV[%'")[0][0], len(orig["EV"]))
    esperar("eventos PREC (+ fundidos)", q(con, "SELECT count(*) FROM evento WHERE canal='precatorios'")[0][0] + fund_p, len(raw["PREC"]))
    esperar("eventos brb do dossiê (+ fundidos)", q(con, "SELECT count(*) FROM evento WHERE canal='brb'")[0][0] + fund_b, 30)
    ids_o = {e["id"] for e in orig["EV"]}
    esperar("ids de origens presentes", len({r[0] for r in q(con, "SELECT id FROM evento")} & ids_o), len(ids_o))
    # evidência: todas as URLs normalizadas de E+EV da teia continuam ligadas (EV fundido: ao evento mantido, via mapa_indices/evento_alias)
    raw_urls = set()
    for e in raw["E"]:
        for r in e["r"]:
            raw_urls |= urls(r["f"])
    for e in raw["EV"]:
        raw_urls |= urls(e["f"])
    ligadas = {r[0] for r in q(con, """SELECT e.url FROM evidencia e JOIN relacao_evidencia x ON x.evidencia_id=e.id""")}
    ligadas |= {r[0] for r in q(con, """SELECT e.url FROM evidencia e JOIN evento_evidencia x ON x.evidencia_id=e.id JOIN evento v ON v.id=x.evento_id
                                         WHERE v.origem_ref LIKE '%teia:EV[%'
                                            OR v.id IN (SELECT evento_id FROM evento_alias WHERE origem_ref_original LIKE '%teia:EV[%')""")}
    esperar("URLs normalizadas únicas em E+EV da teia", len(ligadas & raw_urls), len(raw_urls))
    ev_url = {r[0] for r in q(con, "SELECT url FROM evidencia")}
    for e in orig["EV"]:
        if not urls(e["f"]) <= ev_url:
            falha(f"origens {e['id']}: URL ausente")
    # normalização
    mal = [u for u in ev_url if u != normalizar_url(u)]
    esperar("URLs em evidencia já normalizadas (não normalizadas)", len(mal), 0)


def orfaos(con):
    secao("Órfãos e integridade")
    esperar("PRAGMA integrity_check", q(con, "PRAGMA integrity_check")[0][0], "ok")
    fk = q(con, "PRAGMA foreign_key_check")
    esperar("PRAGMA foreign_key_check (violações)", len(fk), 0)
    n = q(con, """SELECT count(*) FROM entidade e WHERE origem='teia' AND NOT EXISTS (SELECT 1 FROM relacao r WHERE r.de=e.id OR r.para=e.id)""")[0][0]
    esperar("nós da teia sem nenhuma relação", n, 0)
    n = q(con, """SELECT count(*) FROM evidencia e WHERE NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM serie s WHERE s.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM ranking_empresa s WHERE s.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM dossie_par_evidencia s WHERE s.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM mandato s WHERE s.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM fonte s WHERE s.evidencia_id=e.id)""")[0][0]
    esperar("evidências sem nenhum uso", n, 0)
    n = q(con, "SELECT count(*) FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id) AND canal IN ('teia','banco','familia','ida','volta','precatorios','brb')")[0][0]
    esperar("eventos de fonte única (teia/origens/prec/brb) sem evidência", n, 0)
    n = q(con, "SELECT count(*) FROM relacao r WHERE r.origem_ref LIKE 'E[%' AND NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id)")[0][0]
    esperar("relações da teia sem evidência", n, 0)
    n = q(con, "SELECT count(*) FROM relacao WHERE de=para")[0][0]
    esperar("auto-laços", n, 0)
    esperar("aresta_legado (pares E)", q(con, "SELECT count(*) FROM aresta_legado")[0][0], 319)
    sem_ref = q(con, """SELECT id, tipo FROM entidade e WHERE NOT EXISTS (SELECT 1 FROM relacao r WHERE r.de=e.id OR r.para=e.id)
                        AND NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM mandato m WHERE m.entidade_id=e.id OR m.orgao_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM bancada b WHERE b.partido_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM ranking_empresa b WHERE b.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM nota_entidade b WHERE b.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM dossie_par b WHERE b.ator_entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM previdencia_ente b WHERE b.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM pagamento b WHERE b.para_entidade_id=e.id OR b.de_entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM forum b WHERE b.pais_entidade_id=e.id)""")
    print(f"  info: entidades sem nenhuma referência estrutural (aviso, não falha): {len(sem_ref)}"
          + (" -> " + ", ".join(f"{r['id']}({r['tipo']})" for r in sem_ref[:20]) if sem_ref else ""))
    nao_pais = [r["id"] for r in sem_ref if r["tipo"] != "pais"]
    esperar("entidades órfãs que não sejam país (séries de pares usam dimensao pais=ISO3)", len(nao_pais), 0)
    n_ev = q(con, "SELECT count(*) FROM entidade e WHERE origem='teia' AND NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.entidade_id=e.id)")[0][0]
    print(f"  info: nós da teia sem evento ligado: {n_ev} (inventário: 117 sem EV.n/SEM.n)")
    n = q(con, "SELECT count(*) FROM entidade_alias a WHERE NOT EXISTS (SELECT 1 FROM entidade e WHERE e.id=a.entidade_id)")[0][0]
    esperar("aliases sem entidade", n, 0)


def comparar_teia(exp, raw, idx_slug, con):
    """Round-trip: exp (do banco) contra raw. Retorna lista de diferenças."""
    dif = []
    N_raw, N_exp = raw["N"], exp["N"]
    if len(N_raw) != len(N_exp):
        dif.append(f"N: {len(N_raw)} != {len(N_exp)}")
    for i, (a, b) in enumerate(zip(N_raw, N_exp)):
        b2 = {k: v for k, v in b.items() if k not in ("id", "fam_de_id", "lig_de_id")}
        if a != b2:
            dif.append(f"N[{i}] difere: {a} != {b2}")
        if b["id"] != idx_slug[i]:
            dif.append(f"N[{i}].id {b['id']} != slug(nome) {idx_slug[i]}")
        for k in ("fam_de", "lig_de"):
            if k in a and b.get(k + "_id") != idx_slug[a[k]]:
                dif.append(f"N[{i}].{k}_id errado")
    if raw["cats"] != exp["cats"]:
        dif.append("cats difere")
    # relações pela chave (slug(a), slug(b), rot)
    def chaves(E, via_idx):
        d = {}
        for ei, e in enumerate(E):
            for ri, r in enumerate(e["r"]):
                k = (idx_slug[r["a"]], idx_slug[r["b"]], r["rot"])
                if k in d:
                    dif.append(f"chave de relação duplicada {k}")
                d[k] = (ei, ri, r)
        return d
    kr, ke = chaves(raw["E"], True), chaves(exp["E"], False)
    for k in kr.keys() - ke.keys():
        dif.append(f"relação ausente no export: {k}")
    for k in ke.keys() - kr.keys():
        dif.append(f"relação extra no export: {k}")
    for k in kr.keys() & ke.keys():
        (ei, ri, a), (ej, rj, b) = kr[k], ke[k]
        if (ei, ri) != (ej, rj):
            dif.append(f"{k}: posição E[{ei}].r[{ri}] != E[{ej}].r[{rj}]")
        for c in ("st", "tipo", "de", "ate", "val", "desc", "resp", "a", "b"):
            if a[c] != b[c] or type(a[c]) is not type(b[c]) and not (a[c] is None and b[c] is None):
                dif.append(f"{k}: campo {c}: {a[c]!r} != {b[c]!r}")
        if urls(a["f"]) != urls(b["f"]):
            dif.append(f"{k}: URLs diferem {urls(a['f']) ^ urls(b['f'])}")
        if (idx_slug[b["a"]], idx_slug[b["b"]]) != (b["a_id"], b["b_id"]):
            dif.append(f"{k}: a_id/b_id inconsistentes")
    for ei, (a, b) in enumerate(zip(raw["E"], exp["E"])):
        if (a["a"], a["b"]) != (b["a"], b["b"]):
            dif.append(f"E[{ei}].a/b difere da orientação original: ({a['a']},{a['b']}) != ({b['a']},{b['b']})")
    if len(raw["E"]) != len(exp["E"]):
        dif.append(f"E: {len(raw['E'])} != {len(exp['E'])}")
    for c in ("SINT", "LAC"):
        if raw[c] != exp[c]:
            dif.append(f"{c} difere")
    if len(raw["SEM"]) != len(exp["SEM"]):
        dif.append("SEM: tamanho")
    for i, (a, b) in enumerate(zip(raw["SEM"], exp["SEM"])):
        if {k: a[k] for k in ("l", "x", "k", "n")} != {k: b[k] for k in ("l", "x", "k", "n")} or b["ids"] != [idx_slug[k] for k in a["n"]]:
            dif.append(f"SEM[{i}] difere")
    # NUM
    if raw["NUM"].keys() != exp["NUM"].keys():
        dif.append("NUM: anos")
    for ano in raw["NUM"].keys() & exp["NUM"].keys():
        a, b = raw["NUM"][ano], exp["NUM"][ano]
        for c in ("ativos_brl_bi", "patrimonio_liquido_brl_bi", "captacao_brl_bi", "lucro_brl_bi", "obs"):
            if a.get(c) != b.get(c):
                dif.append(f"NUM[{ano}].{c}: {a.get(c)!r} != {b.get(c)!r}")
        if normalizar_url(a["fonte"]) != b["fonte"]:
            dif.append(f"NUM[{ano}].fonte")
        if [normalizar_url(u) for u in a.get("fontes_adicionais", [])] != [normalizar_url(u) for u in b.get("fontes_adicionais", [])]:
            dif.append(f"NUM[{ano}].fontes_adicionais")
    # PREC: os fundidos pela curadoria saem da lista (conferidos em comparar_eventos_teia)
    fund = fundidos_por_ref(con, r"PREC\[(\d+)\]")
    prec_raw = [p for i, p in enumerate(raw["PREC"]) if i not in fund]
    if len(prec_raw) != len(exp["PREC"]):
        dif.append(f"PREC: {len(prec_raw)} != {len(exp['PREC'])}")
    for i, (a, b) in enumerate(zip(prec_raw, exp["PREC"])):
        for c in ("d", "t", "x", "st"):
            if a[c] != b[c]:
                dif.append(f"PREC[{i}].{c}")
        if urls(a["f"]) != urls(b["f"]):
            dif.append(f"PREC[{i}].f")
    return dif


def fundidos_por_ref(con, regex):
    """índices (do raw) cujo evento foi fundido pela curadoria, por origem_ref_original."""
    out = set()
    for r in con.execute("SELECT origem_ref_original FROM evento_alias"):
        m = re.search(regex, r[0] or "")
        if m:
            out.add(int(m.group(1)))
    return out


def comparar_eventos_teia(con, exp, raw, mapa, idx_slug):
    """EV da teia: cada EV[i] do raw ou ainda existe igual (id preservado), ou foi fundido (alias com o original intacto) e o evento
    mantido contém a união (fontes, entidades, peso >= e natureza >= a mais forte)."""
    dif = []
    peso_nat = {r["id"]: r["peso"] for r in con.execute("SELECT id, peso FROM natureza")}
    cod = {r["codigo_externo"]: r["natureza_id"] for r in con.execute("SELECT * FROM natureza_mapa WHERE sistema='teia'")}
    ev_exp = {e["id"]: e for e in exp["EV"]}
    alias_i = {}
    for r in con.execute("SELECT alias, evento_id, origem_ref_original, original_json FROM evento_alias"):
        m = re.search(r"teia:EV\[(\d+)\]", r["origem_ref_original"] or "")
        if m:
            alias_i[int(m.group(1))] = (r["alias"], r["evento_id"], json.loads(r["original_json"]))
    absorvem = {r[0] for r in con.execute("SELECT DISTINCT evento_id FROM evento_alias")}
    esperar("EV exportados na teia.json (167 - fundidos)", len(exp["EV"]), len(raw["EV"]) - len(alias_i))
    for i, a in enumerate(raw["EV"]):
        sid = mapa["EV"].get(str(i))
        if sid is None:
            dif.append(f"EV[{i}] sem entrada em mapa_indices")
            continue
        row = con.execute("SELECT * FROM evento WHERE id=?", (sid,)).fetchone()
        if row is None:
            dif.append(f"EV[{i}] -> {sid} não existe")
            continue
        ub = {r[0] for r in con.execute("SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=?", (sid,))}
        nb = {r[0] for r in con.execute("SELECT entidade_id FROM evento_entidade WHERE evento_id=?", (sid,))}
        ua, na = urls(a["f"]), {idx_slug[k] for k in a["n"]}
        if i in alias_i:
            _, mantido, o = alias_i[i]
            if mantido != sid:
                dif.append(f"EV[{i}]: alias aponta para {mantido}, mapa para {sid}")
            for c_raw, c_o in (("t", "titulo"), ("x", "descricao")):
                if a[c_raw] != o[c_o]:
                    dif.append(f"EV[{i}] fundido: {c_raw} do original diverge do raw")
            if (o["data_texto"] or o["data"]) != a["d"] or o["peso"] != a["p"]:
                dif.append(f"EV[{i}] fundido: d/p do original diverge do raw")
            if (cod.get(a.get("st")) if "st" in a else None) != o["natureza_id"]:
                dif.append(f"EV[{i}] fundido: natureza do original diverge do raw")
            if {normalizar_url(f[1]) for f in o["fontes"]} != ua or [x[0] for x in o["entidades"]] != [idx_slug[k] for k in a["n"]]:
                dif.append(f"EV[{i}] fundido: fontes/entidades do original divergem do raw")
        else:
            if row["titulo"] != a["t"] or row["descricao"] != a["x"] or (row["data_texto"] or row["data"]) != a["d"] or row["ano"] != a["y"]:
                dif.append(f"EV[{i}]: t/x/d/y diferem")
        # mantido/preservado: contém a união
        if not ua <= ub:
            dif.append(f"EV[{i}]: fontes ausentes no evento {sid}: {ua - ub}")
        if not na <= nb:
            dif.append(f"EV[{i}]: entidades ausentes no evento {sid}: {na - nb}")
        if a["p"] is not None and (row["peso"] is None or row["peso"] < a["p"]):
            dif.append(f"EV[{i}]: peso do evento {sid} menor que o original")
        if "st" in a and (row["natureza_id"] is None or peso_nat[row["natureza_id"]] < peso_nat[cod[a["st"]]]):
            dif.append(f"EV[{i}]: natureza do evento {sid} mais fraca que a original")
        if i not in alias_i and sid not in absorvem and sid in ev_exp:
            b = ev_exp[sid]
            for c in ("d", "y", "t", "x", "p", "n"):
                if a[c] != b[c]:
                    dif.append(f"EV[{i}].{c}: {a[c]!r} != {b[c]!r}")
            # st ausente no raw pode ter sido atribuído pela curadoria (eventos-natureza.json); presente tem de ser igual
            if ("st" in a and a["st"] != b.get("st")) or b["ids"] != [idx_slug[k] for k in a["n"]]:
                dif.append(f"EV[{i}].st/ids")
            if ua != urls(b["f"]) and not str(row["origem_ref"]).count("origens"):
                dif.append(f"EV[{i}].f difere: {ua ^ urls(b['f'])}")
    # PREC fundidos: original intacto no alias
    for i, (alias, mantido, o) in sorted(((i, v) for i, v in ((int(m.group(1)), (r["alias"], r["evento_id"], json.loads(r["original_json"])))
                                                              for r in con.execute("SELECT alias, evento_id, origem_ref_original, original_json FROM evento_alias")
                                                              for m in [re.fullmatch(r"PREC\[(\d+)\]", r["origem_ref_original"] or "")] if m))):
        a = raw["PREC"][i]
        if (a["t"], a["x"], a["d"]) != (o["titulo"], o["descricao"], o["data_texto"] or o["data"]) or cod[a["st"]] != o["natureza_id"]:
            dif.append(f"PREC[{i}] fundido: original diverge do raw")
    return dif


def comparar_origens(exp, raw, con):
    dif = []
    fundido = {r[0] for r in con.execute("SELECT DISTINCT evento_id FROM evento_alias")}
    if len(raw["EV"]) != len(exp["EV"]):
        dif.append("EV tamanho")
    for i, (a, b) in enumerate(zip(raw["EV"], exp["EV"])):
        for c in ("id", "ch", "d", "y", "t", "x", "st", "r", "v"):
            if a[c] != b[c] and not (c in ("st", "r", "v") and b["id"] in fundido and (c != "st" or b["st"] in ("doc", "inv", "rep", "ale"))):
                dif.append(f"origens EV[{i}].{c}: {a[c]!r} != {b[c]!r}")
        if (b["id"] in fundido and not urls(a["f"]) <= urls(b["f"])) or (b["id"] not in fundido and urls(a["f"]) != urls(b["f"])):
            dif.append(f"origens EV[{i}].f: {urls(a['f']) ^ urls(b['f'])}")
    for c in ("NARR", "SINT", "SEM", "LAC"):
        if raw[c] != exp[c]:
            dif.append(f"origens {c} difere")
    return dif


def _norm_json(o, soltar_vazios=False):
    """URLs inteiras passam por normalizar_url; opcionalmente descarta None e {} (pares: nulls explícitos não viram linha em serie)."""
    if isinstance(o, dict):
        r = {k: _norm_json(v, soltar_vazios) for k, v in o.items()}
        return {k: v for k, v in r.items() if not (soltar_vazios and (v is None or v == {}))}
    if isinstance(o, list):
        return [_norm_json(x, soltar_vazios) for x in o]
    if isinstance(o, str) and o.startswith("http") and " " not in o:
        return normalizar_url(o)
    return o


def dif_json(a, b, caminho=""):
    out = []
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool)):
        return [f"{caminho}: tipo {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        for k in sorted(a.keys() | b.keys()):
            if k not in a:
                out.append(f"{caminho}/{k}: só no export")
            elif k not in b:
                out.append(f"{caminho}/{k}: só no raw")
            else:
                out += dif_json(a[k], b[k], f"{caminho}/{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{caminho}: tamanho {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += dif_json(x, y, f"{caminho}[{i}]")
    elif a != b:
        out.append(f"{caminho}: {str(a)[:60]!r} != {str(b)[:60]!r}")
    return out


def dossie_e_pares(con, exp):
    secao("Dossiê e pares (data/dossie.json e data/pares.json == data/raw, URLs normalizadas)")
    raw_d = json.loads((RAW / "dossie.json").read_text(encoding="utf-8"))
    d = dif_json(_norm_json(raw_d), _norm_json(json.loads(json.dumps(exp["dossie.json"]))))
    print(f"  diferenças dossie.json: {len(d)}")
    for x in d[:20]:
        print("   -", x)
    if d:
        falha(f"dossie.json difere do raw em {len(d)} pontos")
    raw_p = json.loads((RAW / "pares.json").read_text(encoding="utf-8"))
    cota = sum(1 for v in raw_p["notas"].values() for t in v if re.match(r"^\s*Cota:", t))
    raw_p["notas"] = {k: [t for t in v if not re.match(r"^\s*Cota:", t)] for k, v in raw_p["notas"].items()}
    nulos = sum(1 for i in raw_p["indicadores"].values() for s in i["dados"].values() for v in s.values() if v is None)
    p = dif_json(_norm_json(raw_p, True), _norm_json(json.loads(json.dumps(exp["pares.json"])), True))
    print(f"  diferenças pares.json: {len(p)} (ignorados de propósito: {cota} linha de log 'Cota:' em notas e valores null explícitos, {nulos} só nos indicadores)")
    for x in p[:20]:
        print("   -", x)
    if p:
        falha(f"pares.json difere do raw em {len(p)} pontos")
    esperar("dossie_par: pares distintos (13)", q(con, "SELECT count(DISTINCT ordem) FROM dossie_par")[0][0], 13)
    esperar("dossie_par: linhas (13 + 1 do par com 2 atores)", q(con, "SELECT count(*) FROM dossie_par")[0][0], 14)
    esperar("previdencia_ente", q(con, "SELECT count(*) FROM previdencia_ente")[0][0], 11)
    esperar("previdencia_ente: soma valor_mi (R$ mi)", round(q(con, "SELECT sum(valor_mi) FROM previdencia_ente")[0][0], 2), 1867.45)
    esperar("pagamento por categoria", {r["categoria"]: r["c"] for r in q(con, "SELECT categoria, count(*) c FROM pagamento GROUP BY categoria")},
            {"contrato": 8, "doacao": 3, "midia": 3})
    esperar("indicio_maquina", q(con, "SELECT count(*) FROM indicio_maquina")[0][0], 5)
    esperar("limite por tipo", {r["tipo"]: r["c"] for r in q(con, "SELECT tipo, count(*) c FROM limite GROUP BY tipo")}, {"aberto": 4, "agenda": 3, "derrubado": 6})
    esperar("forum (10 países x 5 fóruns)", q(con, "SELECT count(*) FROM forum")[0][0], 50)
    n = q(con, "SELECT count(*) FROM nota WHERE pagina='dossie' AND chave IN ('mercado.pares','previdencia.entes','dinheiro.contratos','dinheiro.midia','dinheiro.doacoes','maquina.indicios','limites.derrubado','limites.aberto','limites.agenda')")[0][0]
    esperar("seções relacionais não estão mais em nota", n, 0)


def curadoria(con):
    secao("Curadoria (data/curadoria/*.json aplicada)")
    fusoes = json.loads((CURADORIA / "eventos-fusoes.json").read_text(encoding="utf-8"))
    fundir = [i for f in fusoes for i in f["fundir"]]
    esperar("evento_alias == ids fundidos em eventos-fusoes.json (nº)", len(q(con, "SELECT alias FROM evento_alias")), len(fundir))
    esperar("evento_alias: mesmos ids", sorted(r[0] for r in q(con, "SELECT alias FROM evento_alias")) == sorted(fundir), True)
    esperar("ids fundidos não existem mais como evento", q(con, "SELECT count(*) FROM evento WHERE id IN (SELECT alias FROM evento_alias)")[0][0], 0)
    esperar("ids mantidos existem", q(con, f"SELECT count(*) FROM evento WHERE id IN ({','.join('?' * len(fusoes))})", *[f['manter'] for f in fusoes])[0][0], len(fusoes))
    for f in fusoes:
        for i in f["fundir"]:
            o = json.loads(q(con, "SELECT original_json FROM evento_alias WHERE alias=?", i)[0][0])
            ub = {r[0] for r in q(con, "SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=?", f["manter"])}
            if not {normalizar_url(x[1]) for x in o["fontes"]} <= ub:
                falha(f"fusão {f['manter']}: fontes de {i} não estão no evento mantido")
            nb = {r[0] for r in q(con, "SELECT entidade_id FROM evento_entidade WHERE evento_id=?", f["manter"])}
            if not {x[0] for x in o["entidades"]} <= nb:
                falha(f"fusão {f['manter']}: entidades de {i} não estão no evento mantido")
    nat = json.loads((CURADORIA / "eventos-natureza.json").read_text(encoding="utf-8"))
    ok = sum(1 for n in nat if (q(con, "SELECT natureza_id FROM evento WHERE id=?", n["id"]) or [[None]])[0][0] is not None)
    esperar("eventos-natureza.json: itens com natureza no banco", ok, len(nat))
    lig = json.loads((CURADORIA / "evento-entidade-auto.json").read_text(encoding="utf-8"))
    ok = sum(1 for it in lig for e in it["entidades"] if q(con, "SELECT 1 FROM evento_entidade WHERE evento_id=? AND entidade_id=? AND papel='citado'", it["evento_id"], e["id"]))
    esperar("evento-entidade-auto.json: ligações presentes", ok, sum(len(it["entidades"]) for it in lig))
    fon = json.loads((CURADORIA / "brasil-fontes.json").read_text(encoding="utf-8"))
    ok = sum(1 for it in fon if q(con, "SELECT count(*) FROM evento_evidencia WHERE evento_id=?", it["evento_id"])[0][0] == len(it["sustenta"]) + len(it["contexto"]))
    esperar("brasil-fontes.json: eventos com todas as fontes ligadas", ok, len(fon))
    n_sem = q(con, "SELECT count(*) FROM evento e WHERE canal='brasil' AND NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id)")[0][0]
    print(f"  info: eventos da timeline Brasil sem fonte (sem item no bruto): {n_sem}")
    n_nat = q(con, "SELECT count(*) FROM evento WHERE canal='teia' AND natureza_id IS NULL")[0][0]
    print(f"  info: eventos da teia ainda sem natureza (nenhuma regra serviu): {n_nat}")
    comp = json.loads((CURADORIA / "brasil-complementos.json").read_text(encoding="utf-8"))
    esperar("ranking_empresa com receita == brasil-complementos.json", q(con, "SELECT count(*) FROM ranking_empresa WHERE receita_brl_bi IS NOT NULL")[0][0], len(comp["receita"]))
    esperar("mandato com periodo_texto == brasil-complementos.json", q(con, "SELECT count(*) FROM mandato WHERE periodo_texto IS NOT NULL")[0][0], len(comp["mandato_periodo"]))
    n = q(con, "SELECT count(*) FROM evento_entidade WHERE papel='citado' AND entidade_id NOT IN (SELECT id FROM entidade)")[0][0]
    esperar("evento_entidade citado com entidade inexistente", n, 0)


def modelo_v2(con, exp):
    """Tema N:N, fonte genérica e ligação teia <-> timeline (mandato/bancada -> relações institucionais)."""
    secao("Temas (relacao_tema, evento_tema, v_entidade_tema)")
    cfg = json.loads((CURADORIA / "temas.json").read_text(encoding="utf-8"))
    esperar("tema == data/curadoria/temas.json", [r[0] for r in q(con, "SELECT id FROM tema ORDER BY ordem, id")], [t["id"] for t in sorted(cfg["temas"], key=lambda t: (t["ordem"], t["id"]))])
    tabela("relações por tema:", [(r[0], r[1]) for r in q(con, "SELECT tema_id, count(*) FROM relacao_tema GROUP BY tema_id ORDER BY tema_id")])
    tabela("eventos por tema:", [(r[0], r[1]) for r in q(con, "SELECT tema_id, count(*) FROM evento_tema GROUP BY tema_id ORDER BY tema_id")])
    tabela("entidades por tema (view):", [(r[0], r[1]) for r in q(con, "SELECT tema_id, count(*) FROM v_entidade_tema GROUP BY tema_id ORDER BY tema_id")])
    esperar("relações sem nenhum tema", q(con, "SELECT count(*) FROM relacao r WHERE NOT EXISTS (SELECT 1 FROM relacao_tema x WHERE x.relacao_id=r.id)")[0][0], 0)
    esperar("eventos sem nenhum tema", q(con, "SELECT count(*) FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_tema x WHERE x.evento_id=e.id)")[0][0], 0)
    esperar("entidades sem nenhum tema (v_entidade_tema)", q(con, "SELECT count(*) FROM entidade e WHERE NOT EXISTS (SELECT 1 FROM v_entidade_tema v WHERE v.entidade_id=e.id)")[0][0], 0)
    n_ac = q(con, "SELECT (SELECT count(*) FROM relacao_tema WHERE tema_id='a-classificar'), (SELECT count(*) FROM evento_tema WHERE tema_id='a-classificar')")[0]
    print(f"  {'aviso' if n_ac[0] + n_ac[1] else 'info '}: registros em 'a-classificar': {n_ac[0]} relações, {n_ac[1]} eventos")
    # regras puramente por origem/canal têm de valer em 100% dos registros (as por texto/entidade são conferidas pela exportação == banco)
    for rg in cfg["regras"]:
        if "texto" in rg or "entidade" in rg or "dentro_de" in rg:
            continue
        falt = 0
        if rg["alvo"] in ("relacao", "ambos") and "origem" in rg:
            falt += q(con, f"SELECT count(*) FROM relacao r WHERE origem IN ({','.join('?' * len(rg['origem']))}) AND NOT EXISTS (SELECT 1 FROM relacao_tema x WHERE x.relacao_id=r.id AND x.tema_id=?)", *rg["origem"], rg["tema"])[0][0]
        if rg["alvo"] in ("evento", "ambos") and "canal" in rg:
            falt += q(con, f"SELECT count(*) FROM evento e WHERE canal IN ({','.join('?' * len(rg['canal']))}) AND NOT EXISTS (SELECT 1 FROM evento_tema x WHERE x.evento_id=e.id AND x.tema_id=?)", *rg["canal"], rg["tema"])[0][0]
        esperar(f"regra {rg['id']}: registros sem o tema {rg['tema']}", falt, 0)
    for ex in cfg.get("excecoes", []):
        if ex["alvo"] == "relacao":
            i = q(con, "SELECT id FROM relacao WHERE origem_ref=?", ex["ref"])[0][0]
            tb, col = "relacao_tema", "relacao_id"
        else:
            i, tb, col = ex["ref"], "evento_tema", "evento_id"
        tem = {r[0] for r in q(con, f"SELECT tema_id FROM {tb} WHERE {col}=?", i)}
        if set(ex.get("excluir", [])) & tem or not set(ex.get("incluir", [])) <= tem:
            falha(f"exceção de tema não aplicada: {ex['ref']}")
    t = exp["teia.json"]
    sem = sum(1 for e in t["E"] for r in e["r"] if not r["tema"]) + sum(1 for e in t["EV"] if not e["tema"]) + sum(1 for e in t["PREC"] if not e["tema"])
    esperar("teia.json: relações/eventos/PREC sem `tema`", sem, 0)
    esperar("origens.json: eventos sem `tema`", sum(1 for e in exp["origens.json"]["EV"] if not e["tema"]), 0)

    secao("Fonte genérica (fonte, trecho.fonte_id, view video)")
    tabela("fonte por tipo:", [(r[0], r[1]) for r in q(con, "SELECT tipo, count(*) FROM fonte GROUP BY tipo ORDER BY tipo")] + [("TOTAL", q(con, "SELECT count(*) FROM fonte")[0][0])])
    esperar("view video == fontes tipo video", q(con, "SELECT count(*) FROM video")[0][0], q(con, "SELECT count(*) FROM fonte WHERE tipo='video'")[0][0])
    esperar("view video expõe as colunas antigas", [r[1] for r in q(con, "PRAGMA table_info(video)")][:6], ["id", "plataforma", "url", "titulo", "canal", "canal_entidade_id"])
    esperar("fonte com URL sem evidência", q(con, "SELECT count(*) FROM fonte WHERE url IS NOT NULL AND evidencia_id IS NULL")[0][0], 0)
    esperar("fonte cuja evidência tem outra URL", q(con, "SELECT count(*) FROM fonte f JOIN evidencia e ON e.id=f.evidencia_id WHERE e.url<>f.url")[0][0], 0)
    ruins = [r["id"] for r in q(con, "SELECT id, texto, hash_texto FROM fonte WHERE texto IS NOT NULL") if hashlib.sha256(r["texto"].encode("utf-8")).hexdigest() != r["hash_texto"]]
    esperar("fonte com hash_texto diferente do sha256(texto)", len(ruins), 0)
    esperar("corte em fonte que não é vídeo", q(con, "SELECT count(*) FROM corte c JOIN fonte f ON f.id=c.video_id WHERE f.tipo<>'video'")[0][0], 0)
    esperar("trecho de vídeo sem inicio_s/fim_s", q(con, "SELECT count(*) FROM trecho t JOIN fonte f ON f.id=t.fonte_id WHERE f.tipo='video' AND t.inicio_s IS NULL")[0][0], 0)
    esperar("trecho órfão de fonte", q(con, "SELECT count(*) FROM trecho t WHERE NOT EXISTS (SELECT 1 FROM fonte f WHERE f.id=t.fonte_id)")[0][0], 0)
    sem_trecho = [r["id"] for r in q(con, "SELECT id FROM fonte f WHERE NOT EXISTS (SELECT 1 FROM trecho t WHERE t.fonte_id=f.id)")]
    print(f"  {'aviso' if sem_trecho else 'info '}: fontes sem nenhum trecho: {len(sem_trecho)}" + (" -> " + ", ".join(sem_trecho[:10]) if sem_trecho else ""))

    secao("Teia <-> timeline (mandato/bancada -> relações institucionais)")
    n_m = q(con, "SELECT count(*) FROM mandato")[0][0]
    esperar("relações subtipo mandato:* == linhas de mandato", q(con, "SELECT count(*) FROM relacao WHERE origem='linha_do_tempo' AND subtipo LIKE 'mandato:%'")[0][0], n_m)
    esperar("cada mandato tem a sua relação (origem_ref mandato:<id>)", q(con, "SELECT count(*) FROM mandato m WHERE NOT EXISTS (SELECT 1 FROM relacao r WHERE r.origem_ref='mandato:'||m.id AND r.de=m.entidade_id AND r.periodo_inicio=m.inicio AND r.periodo_fim=COALESCE(m.fim,m.inicio))")[0][0], 0)
    esperar("relações linha_do_tempo: natureza/tipo/status", q(con, "SELECT count(*) FROM relacao WHERE origem='linha_do_tempo' AND (natureza_id<>'documentada' OR tipo<>'institucional' OR status<>'publicada')")[0][0], 0)
    esperar("relações linha_do_tempo sem o tema brasil-ano-a-ano", q(con, "SELECT count(*) FROM relacao r WHERE origem='linha_do_tempo' AND NOT EXISTS (SELECT 1 FROM relacao_tema x WHERE x.relacao_id=r.id AND x.tema_id='brasil-ano-a-ano')")[0][0], 0)
    esperar("mandato: de=pessoa, para=orgao_publico", q(con, "SELECT count(*) FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para WHERE r.subtipo LIKE 'mandato:%' AND (d.tipo<>'pessoa' OR p.tipo<>'orgao_publico')")[0][0], 0)
    esperar("filiação: de=pessoa, para=partido", q(con, "SELECT count(*) FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para WHERE r.subtipo='filiacao' AND (d.tipo<>'pessoa' OR p.tipo<>'partido')")[0][0], 0)
    manual = json.loads((CURADORIA / "mandato-relacoes.json").read_text(encoding="utf-8")).get("partido_manual", {})
    por_alias = {(r[0], r[1]) for r in q(con, "SELECT alias, entidade_id FROM entidade_alias")}
    mand = {}
    for m in q(con, "SELECT entidade_id, partido, inicio, COALESCE(fim, inicio) fim FROM mandato WHERE partido IS NOT NULL"):
        mand.setdefault(m["entidade_id"], []).append((m["partido"], int(m["inicio"][:4]), int(m["fim"][:4])))
    sem = 0
    for r in q(con, "SELECT de, para, ano_inicio, ano_fim FROM relacao WHERE subtipo='filiacao'"):
        if not any((manual.get(p) == r["para"] or (p, r["para"]) in por_alias) and r["ano_inicio"] <= a <= b <= r["ano_fim"]
                   for p, a, b in mand.get(r["de"], [])):
            sem += 1
    esperar("filiação sem mandato no mesmo partido dentro do período", sem, 0)
    esperar("presidencia-da-republica existe (orgao_publico)", [tuple(r) for r in q(con, "SELECT id, tipo FROM entidade WHERE id='presidencia-da-republica'")], [("presidencia-da-republica", "orgao_publico")])
    n_pr = q(con, "SELECT count(*) FROM relacao WHERE para='presidencia-da-republica' AND subtipo IN ('mandato:presidente','mandato:vice_presidente')")[0][0]
    esperar("presidentes + vices ligados à Presidência", n_pr, q(con, "SELECT count(*) FROM mandato WHERE cargo IN ('presidente','vice_presidente')")[0][0])
    # entidade da timeline que coincide com nó da teia aparece nos dois temas
    fundidas = [r[0] for r in q(con, """SELECT e.id FROM entidade e WHERE e.origem='teia' AND (
        EXISTS (SELECT 1 FROM mandato m WHERE m.entidade_id=e.id OR m.orgao_id=e.id) OR EXISTS (SELECT 1 FROM bancada b WHERE b.partido_id=e.id)
        OR EXISTS (SELECT 1 FROM ranking_empresa k WHERE k.entidade_id=e.id)
        OR EXISTS (SELECT 1 FROM evento_entidade x JOIN evento v ON v.id=x.evento_id WHERE x.entidade_id=e.id AND v.canal='brasil')) ORDER BY e.id""")]
    faltam = [e for e in fundidas if {"brasil-ano-a-ano", "caso-master"} - {r[0] for r in q(con, "SELECT tema_id FROM v_entidade_tema WHERE entidade_id=?", e)}]
    print(f"  entidades da teia que também aparecem na timeline: {len(fundidas)} ({', '.join(fundidas)})")
    esperar("... delas fora de brasil-ano-a-ano ou caso-master", faltam, [])
    n_ent_tl = q(con, "SELECT count(*) FROM entidade WHERE origem='teia' AND id IN (SELECT entidade_id FROM v_entidade_tema WHERE tema_id='brasil-ano-a-ano')")[0][0]
    print(f"  info: nós da teia no tema brasil-ano-a-ano: {n_ent_tl}")

    mo_p = CURADORIA / "mandato-oficial.json"
    if mo_p.exists():
        secao("Mandatos x APIs oficiais (data/curadoria/mandato-oficial.json)")
        mo = json.loads(mo_p.read_text(encoding="utf-8"))
        rs = mo["resumo"]
        esperar("resumo: confirmados + divergentes + sem fonte == linhas de mandato", rs["confirmados"] + rs["divergentes"] + rs["sem_fonte_oficial"], n_m)
        esperar("linhas de mandato com evidência dado_oficial == confirmados", q(con, "SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id WHERE e.tipo='dado_oficial'")[0][0], rs["confirmados"])
        esperar("evidência dos mandatos só em domínios oficiais (Câmara/Senado)", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.veiculo NOT IN ('dadosabertos.camara.leg.br','legis.senado.leg.br') OR e.url NOT LIKE 'https://'||e.veiculo||'/%'""")[0][0], 0)
        esperar("relações de mandato confirmado sem a evidência oficial", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id AND e.tipo='dado_oficial'
            JOIN relacao r ON r.origem_ref='mandato:'||m.id WHERE NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id AND x.evidencia_id=e.id)""")[0][0], 0)
        esperar("divergente/sem fonte com evidência oficial no mandato", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.tipo='dado_oficial' AND m.cargo NOT IN ('deputado','senador')""")[0][0], 0)
        n_comp = q(con, "SELECT count(*) FROM mandato WHERE partido IS NULL AND cargo IN ('deputado','senador')")[0][0]
        esperar("deputado/senador com partido NULL após complementos", n_comp, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(SQLITE))
    a = ap.parse_args()
    if not Path(a.db).exists():
        sys.exit(f"banco não encontrado: {a.db}")
    print(f"validando {a.db}")
    raw = json.loads((RAW / "dados-caso-master-v2.json").read_text(encoding="utf-8"))
    orig = json.loads((RAW / "origens.json").read_text(encoding="utf-8"))
    con = conectar(a.db)
    contagens(con, raw, orig)
    orfaos(con)

    secao("Round-trip (exportar_json -> teia.json vs data/raw/dados-caso-master-v2.json)")
    idx_slug = {i: slug_para_nome(n["n"]) for i, n in enumerate(raw["N"])}
    exp = ex.todos(con)
    dif = comparar_teia(exp["teia.json"], raw, idx_slug, con)
    dif += comparar_eventos_teia(con, exp["teia.json"], raw, exp["mapa_indices.json"], idx_slug)
    print(f"  relações comparadas pela chave (slug(r.a), slug(r.b), rot): {sum(len(e['r']) for e in raw['E'])}")
    print(f"  diferenças na teia: {len(dif)}")
    for d in dif[:30]:
        print("   -", d)
    if dif:
        falha(f"round-trip teia: {len(dif)} diferenças")
    dif_o = comparar_origens(exp["origens.json"], orig, con)
    print(f"  diferenças em origens: {len(dif_o)}")
    for d in dif_o[:30]:
        print("   -", d)
    if dif_o:
        falha(f"round-trip origens: {len(dif_o)} diferenças")
    mapa = exp["mapa_indices.json"]
    esperar("mapa_indices.N cobre todos os nós", len(mapa["N"]), len(raw["N"]))
    esperar("slugs únicos no mapa", len(set(mapa["N"].values())), len(raw["N"]))
    esperar("mapa_indices.EV cobre os 167 EV (fundidos apontam para o mantido)", len(mapa["EV"]), len(raw["EV"]))
    dossie_e_pares(con, exp)
    curadoria(con)
    modelo_v2(con, exp)

    secao("Arquivos exportados em disco")
    for nome, obj in exp.items():
        p = DATA / nome
        if not p.exists():
            print(f"  (data/{nome} ainda não gerado; rode exportar_json.py)")
            continue
        igual = json.loads(p.read_text(encoding="utf-8")) == json.loads(json.dumps(obj, ensure_ascii=False))
        print(f"  {'ok ' if igual else 'ERR'} data/{nome} == export atual do banco")
        if not igual:
            falha(f"data/{nome} desatualizado em relação ao banco")
    if DUMP.exists():
        with tempfile.TemporaryDirectory() as t:
            novo = gerar_dump(con, Path(t) / "dump.sql").read_text(encoding="utf-8")
        igual = novo == DUMP.read_text(encoding="utf-8")
        print(f"  {'ok ' if igual else 'ERR'} data/dump.sql == dump atual do banco")
        if not igual:
            falha("data/dump.sql difere do dump atual do banco")
    else:
        print("  (data/dump.sql ainda não gerado)")

    print("\n" + ("RESULTADO: FALHOU (" + str(len(FALHAS)) + " falha(s))" if FALHAS else "RESULTADO: OK, zero falhas"))
    sys.exit(1 if FALHAS else 0)


if __name__ == "__main__":
    main()
