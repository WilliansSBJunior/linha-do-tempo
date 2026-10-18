#!/usr/bin/env python3
"""Valida o banco: integridade, contagens, órfãos e round-trip contra data/raw. Sai com código 1 em qualquer falha.

Uso: python3 scripts/validar.py [--db caminho.sqlite]
Se data/*.json e data/dump.sql existirem, confere também que estão iguais ao que o banco exporta agora.
"""
import argparse
import collections
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

import curadoria as CUR
import exportar_json as ex
from comum import CURADORIA, DATA, DUMP, RAW, SQLITE, conectar, dominio_de, gerar_dump, normalizar_url
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
                  AND NOT EXISTS (SELECT 1 FROM fonte s WHERE s.evidencia_id=e.id)
                  AND NOT EXISTS (SELECT 1 FROM entidade_valor s WHERE s.evidencia_id=e.id)""")[0][0]
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
        # `sat` (aditivo): relação implícita do satélite com a descrição ATUAL do banco e as fontes; o raw não tem esse campo.
        # Não entra no round-trip contra o raw; é conferido contra o banco logo abaixo (descrição e URLs).
        # `val`/`val_lig` (aditivos): estimativas em R$ e soma das ligações, do banco; conferidos contra o banco na seção "Valores".
        b2 = {k: v for k, v in b.items() if k not in ("id", "fam_de_id", "lig_de_id", "sat", "val", "val_lig")}
        if a != b2:
            dif.append(f"N[{i}] difere: {a} != {b2}")
        sats = [k for k in ("fam_de", "lig_de") if k in a]
        if ("sat" in b) != bool(sats):
            dif.append(f"N[{i}].sat presente sem fam_de/lig_de (ou ausente com eles)")
        for k in sats:
            rel = con.execute("SELECT id, rotulo, descricao FROM relacao WHERE origem='teia' AND origem_ref=?", (f"N[{i}].{k}",)).fetchone()
            s = b.get("sat") or {}
            ub = {x[0] for x in con.execute("SELECT e.url FROM relacao_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.relacao_id=?", (rel["id"],))} if rel else set()
            if not rel or (s.get("rot"), s.get("desc")) != (rel["rotulo"], rel["descricao"]) or {f["url"] for f in s.get("fontes", [])} != ub:
                dif.append(f"N[{i}].sat difere da relação N[{i}].{k} no banco")
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
        if "fontes" in b and {f["url"] for f in b["fontes"]} != {f[1] for f in b["f"]}:
            dif.append(f"{k}: `fontes` e `f` não trazem as mesmas URLs")
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
            if "fontes" in b and {f["url"] for f in b["fontes"]} != {f[1] for f in b["f"]}:
                dif.append(f"EV[{i}]: `fontes` e `f` não trazem as mesmas URLs")
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
    exp_d = json.loads(json.dumps(exp["dossie.json"]))
    # aditivos de brb.eventos (`id` do evento no banco, `fontes` ricas): fora do round-trip com o raw, conferidos contra o banco
    ruins = []
    for i, ev in enumerate(exp_d["brb"]["eventos"]):
        eid, fontes = ev.pop("id", None), ev.pop("fontes", None)
        ub = {r[0] for r in q(con, "SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=?", eid)}
        if not ub or fontes is None or {f["url"] for f in fontes} != ub or not urls(ev["src"]) <= ub:
            ruins.append(f"brb.eventos[{i}] ({eid})")
    esperar("dossie.json: brb.eventos com `id` existente e `fontes` == evidências do evento no banco (⊇ src)", ruins, [])
    d = dif_json(_norm_json(raw_d), _norm_json(exp_d))
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


def _rodada3():
    p = CURADORIA / "evidencias-rodada3.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _rodada4():
    p = CURADORIA / "substituicoes-rodada4.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _evidencias_adicionais():
    """Entradas de evidencias-adicionais.json seguidas das `evidencias` de evidencias-rodada3.json e de substituicoes-rodada4.json (mesma lista
    que curadoria.ler_evidencias_adicionais aplica; lida aqui de forma independente)."""
    return (json.loads((CURADORIA / "evidencias-adicionais.json").read_text(encoding="utf-8")) + _rodada3().get("evidencias", [])
            + _rodada4().get("evidencias", []))


def _subst_por(e):
    """URLs normalizadas de `substituida_por` (uma URL ou, se duas fontes novas substituem a mesma fraca, uma lista)."""
    s = e.get("substituida_por")
    return [normalizar_url(u) for u in (s if isinstance(s, list) else [s])] if s else []


def _alvo(e):
    return (e["alvo_tipo"], e.get("evento_id") or (e["relacao_origem"], e["relacao_origem_ref"]))


def _repeticoes_rodada4(ent):
    """{índice da entrada: 'reavaliada' | 'ja_ligada'} para as entradas da rodada 4 cuja (alvo, URL) já aparece antes na lista: 'reavaliada' = a
    própria fraca substituída tem a mesma URL (a página foi relida); 'ja_ligada' = a URL nova já era entrada `boa` do alvo (rodadas 2-3).
    Qualquer outra repetição fica de fora (e é falha em evidencias_adicionais)."""
    vistos, out = {}, {}
    for i, e in enumerate(ent):
        k = (_alvo(e), normalizar_url(e["url"]))
        if k in vistos:
            ant = vistos[k]
            if e.get("rodada") == 4 and ant["qualidade"] == "fraca" and normalizar_url(e.get("substitui") or "") == k[1] and k[1] in _subst_por(ant):
                out[i] = "reavaliada"
            elif e.get("rodada") == 4 and ant["qualidade"] == "boa" and not ant.get("substituida_por"):
                out[i] = "ja_ligada"
            continue
        vistos[k] = e
    return out


def _fontes_brasil():
    """{evento_id: URLs normalizadas (sustenta + contexto) de brasil-fontes.json}: as ligações da carga bruta da timeline."""
    fon = json.loads((CURADORIA / "brasil-fontes.json").read_text(encoding="utf-8"))
    return {it["evento_id"]: {normalizar_url(u) for u in it["sustenta"] + it["contexto"]} for it in fon}


# Fontes fracas que ficam no banco depois da rodada 4 (substituicoes-rodada4.json, `continuam_fracas` + `nao_encontrados`): (alvo, URL).
# Nenhuma outra fraca ficou sem substituta (as 47 restantes foram cobertas pela rodada 4).
FRACAS_RESTANTES_RODADA4 = sorted([
    (("evento", "ev-1999-segundo-mandato-de-fhc"), "https://pt.wikipedia.org/wiki/Fernando_Henrique_Cardoso"),
    (("evento", "ev-2011-s-p-rebaixa-a-nota-dos-estados-unidos"), "https://en.wikipedia.org/wiki/United_States_federal_government_credit-rating_downgrades"),
    (("evento", "ev-2018-guerra-comercial-eua-china-tarifas-sobre"), "https://cscb.ca/en/article/us-tariffs-take-effect-34b-chinese-imports-beijing-announces-retaliation"),
    (("relacao", ("teia", "N[138].fam_de")), "https://www.brasil247.com/regionais/brasilia/filho-de-ibaneis-e-aliado-venderam-credito-de-r-38-milhoes-a-reag-antes-de-brb-negociar-com-master"),
])
# R6 (data/curadoria/regras-fontes.json): das fracas acima, as da Wikipédia viraram `contexto` sem avaliação (qualidade NULL; trecho e nota ficam).
# Ficam `fraca` no banco só as outras (FRACAS_DEPOIS_R6: cscb.ca e Brasil 247). As fórmulas de contagem descontam estas explicitamente.
FRACAS_REBAIXADAS_R6 = sorted([
    (("evento", "ev-1999-segundo-mandato-de-fhc"), "https://pt.wikipedia.org/wiki/Fernando_Henrique_Cardoso"),
    (("evento", "ev-2011-s-p-rebaixa-a-nota-dos-estados-unidos"), "https://en.wikipedia.org/wiki/United_States_federal_government_credit-rating_downgrades"),
])
FRACAS_DEPOIS_R6 = sorted(set(FRACAS_RESTANTES_RODADA4) - set(FRACAS_REBAIXADAS_R6))


def _eh_wiki(tipo, url):
    """R6, lida aqui de forma independente de curadoria.eh_wiki: tipo 'wiki' ou domínio *.wikipedia.org."""
    h = dominio_de(url or "")
    return tipo == "wiki" or h == "wikipedia.org" or h.endswith(".wikipedia.org")


def _r6():
    """Conteúdo de data/curadoria/regras-fontes.json ({} se não existe)."""
    p = CURADORIA / "regras-fontes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _fracas_no_banco(con):
    """[(alvo, URL)] das ligações com qualidade 'fraca' (evento por id; relação por origem + origem_ref), ordenadas."""
    ev = [(("evento", r[0]), r[1]) for r in q(con, "SELECT l.evento_id, v.url FROM evento_evidencia l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.qualidade='fraca'")]
    rl = [(("relacao", (r[0], r[1])), r[2]) for r in q(con, """SELECT r.origem, r.origem_ref, v.url FROM relacao_evidencia l JOIN evidencia v ON v.id=l.evidencia_id
                                                               JOIN relacao r ON r.id=l.relacao_id WHERE l.qualidade='fraca'""")]
    return sorted(ev + rl)


def rodada4(con):
    """Rodada 4 (data/curadoria/substituicoes-rodada4.json): substituição das fontes fracas restantes. O conteúdo de cada entrada contra o banco
    já é conferido em evidencias_adicionais (a lista inclui a rodada 4); aqui: contagens == arquivo; toda substituta ligada ao alvo como
    'sustenta'/'boa'; toda fraca de `substitui` registrada no arquivo de origem com `substituida_por` e desligada do alvo (ou rebaixada a
    'contexto' quando a URL é também fonte bruta do bloco-ano); fracas restantes no banco == FRACAS_RESTANTES_RODADA4 == `continuam_fracas`
    == `nao_encontrados`; aviso de trecho no lote A; e as decisões de correção presentes em evento-correcoes.json/relacao-correcoes.json."""
    cfg = _rodada4()
    if not cfg:
        return
    secao("Rodada 4 (substituicoes-rodada4.json aplicada: substituição das fontes fracas)")
    ent = cfg.get("evidencias", [])
    todas = _evidencias_adicionais()
    base = len(todas) - len(ent)
    rep = {i - base: c for i, c in _repeticoes_rodada4(todas).items() if i >= base}
    esperar("substituicoes-rodada4.json: toda entrada tem \"rodada\": 4, `substitui` e qualidade boa",
            sum(1 for e in ent if e.get("rodada") == 4 and e.get("substitui") and e.get("qualidade") == "boa"), len(ent))
    n_ev = sum(1 for e in ent if e["alvo_tipo"] == "evento")
    n_rl = sum(1 for e in ent if e["alvo_tipo"] == "relacao")
    print(f"  info: rodada 4: {len(ent)} entradas ({n_ev} de evento, {n_rl} de relação), {len({_alvo(e) for e in ent})} alvos, "
          f"{len({(_alvo(e), normalizar_url(e['substitui'])) for e in ent})} fracas distintas substituídas; "
          f"{sum(1 for c in rep.values() if c == 'ja_ligada')} substitutas já ligadas desde a rodada 2/3, {sum(1 for c in rep.values() if c == 'reavaliada')} reavaliações (mesma URL)")
    fb = _fontes_brasil()
    origem = {}   # (alvo, url) -> entrada fraca anterior (evidencias-adicionais.json / rodada 3)
    for e in todas[:base]:
        origem.setdefault((_alvo(e), normalizar_url(e["url"])), e)

    def ligacao(alvo, url):
        if alvo[0] == "evento":
            return q(con, """SELECT l.papel, l.qualidade, l.trecho_citado, l.nota, l.rotulo FROM evento_evidencia l JOIN evidencia v ON v.id=l.evidencia_id
                             WHERE v.url=? AND l.evento_id IN (SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?)""",
                     url, alvo[1], alvo[1])
        return q(con, """SELECT l.papel, l.qualidade, l.trecho_citado, l.nota, NULL AS rotulo FROM relacao_evidencia l JOIN evidencia v ON v.id=l.evidencia_id
                         JOIN relacao r ON r.id=l.relacao_id WHERE v.url=? AND r.origem=? AND r.origem_ref=?""", url, *alvo[1])
    ruins, n_lig, n_desl, n_rebx, n_reav = [], 0, 0, 0, 0
    for i, e in enumerate(ent):
        a, u, uf = _alvo(e), normalizar_url(e["url"]), normalizar_url(e["substitui"])
        lig = ligacao(a, u)
        if len(lig) != 1 or (lig[0]["papel"], lig[0]["qualidade"]) != ("sustenta", "boa"):
            ruins.append(f"substituta não ligada como sustenta/boa: {a} {e['url']} {[tuple(x) for x in lig]}")
        else:
            n_lig += 1
        fr = origem.get((a, uf))
        if not fr or fr["qualidade"] != "fraca":
            ruins.append(f"`substitui` sem fonte fraca registrada no alvo: {a} {e['substitui']}")
            continue
        if u not in _subst_por(fr):
            ruins.append(f"fraca {e['substitui']} sem `substituida_por` com a substituta {e['url']} ({a})")
        if uf == u:   # reavaliação: a mesma URL, agora com o trecho/nota da rodada 4
            n_reav += 1
            if rep.get(i) != "reavaliada" or not lig or lig[0]["trecho_citado"] != e["trecho"]:
                ruins.append(f"reavaliação sem a ligação da rodada 4: {a} {e['url']}")
            continue
        lf = ligacao(a, uf)
        if not lf:
            n_desl += 1
        elif (len(lf) == 1 and a[0] == "evento" and uf in fb.get(a[1], set()) and lf[0]["papel"] == "contexto"
              and (lf[0]["qualidade"], lf[0]["trecho_citado"], lf[0]["nota"], lf[0]["rotulo"]) == (None, None, None, None)):
            n_rebx += 1   # fonte do bloco-ano (brasil-fontes.json): volta a ser só contexto, sem avaliação
        else:
            ruins.append(f"fraca substituída ainda ligada ao alvo: {a} {e['substitui']} {[tuple(x) for x in lf]}")
    for r in ruins[:20]:
        print("   -", r)
    esperar("rodada 4: substituições conferidas (divergências)", len(ruins), 0)
    esperar("rodada 4: substitutas ligadas como sustenta/boa == entradas do arquivo", n_lig, len(ent))
    esperar("rodada 4: substituições == desligadas + rebaixadas a contexto (fonte do bloco-ano) + reavaliadas", n_desl + n_rebx + n_reav, len(ent))
    print(f"  info: rodada 4: {n_desl} substituições com a fraca desligada, {n_rebx} com a fraca de volta a contexto do bloco-ano, {n_reav} reavaliações")
    # nenhuma ligação 'sustenta' de fonte bruta sem avaliação aponta para uma fraca substituída (a ligação fraca some de 'sustenta')
    ruins = []
    for e in todas[:base]:
        if e["qualidade"] == "fraca" and e.get("substituida_por") and e["alvo_tipo"] == "evento":
            for x in ligacao(_alvo(e), normalizar_url(e["url"])):
                if x["papel"] == "sustenta" and normalizar_url(e["url"]) not in _subst_por(e):
                    ruins.append(f"{e['evento_id']}: {e['url']}")
    esperar("fracas substituídas (todas as rodadas) ligadas como 'sustenta'", ruins, [])
    # fracas restantes
    restam = _fracas_no_banco(con)
    for r in restam:
        print("   - continua fraca:", r[0], r[1])
    esperar("FRACAS_REBAIXADAS_R6 ⊆ FRACAS_RESTANTES_RODADA4 e todas da Wikipédia",
            all(x in FRACAS_RESTANTES_RODADA4 and _eh_wiki(None, x[1]) for x in FRACAS_REBAIXADAS_R6), True)
    esperar("FRACAS_DEPOIS_R6 sem Wikipédia", [x for x in FRACAS_DEPOIS_R6 if _eh_wiki(None, x[1])], [])
    # sem a R6 (regras-fontes.json ausente), as wiki continuam fracas: a lista esperada volta a ser a da rodada 4
    rebx = FRACAS_REBAIXADAS_R6 if _r6() else []
    esperar("fracas no banco depois da rodada 4 e da R6 == FRACAS_RESTANTES_RODADA4 − FRACAS_REBAIXADAS_R6",
            restam, FRACAS_DEPOIS_R6 if rebx else FRACAS_RESTANTES_RODADA4)
    ruins = []
    for a, u in rebx:   # a wiki que era fraca: continua ligada, agora `contexto`, sem avaliação, com o trecho e a nota da curadoria
        lig = ligacao(a, normalizar_url(u))
        if len(lig) != 1 or (lig[0]["papel"], lig[0]["qualidade"]) != ("contexto", None) or not lig[0]["trecho_citado"]:
            ruins.append(f"{a} {u} {[tuple(x) for x in lig]}")
    esperar("R6: fracas da Wikipédia ligadas como contexto, qualidade NULL, trecho mantido (divergências)", ruins, [])
    antes_r6 = sorted(restam + rebx)
    esperar("fracas depois da rodada 4 (antes da R6) == FRACAS_RESTANTES_RODADA4", antes_r6, FRACAS_RESTANTES_RODADA4)
    cobertas = {(_alvo(e), normalizar_url(e["substitui"])) for e in ent}
    esperar("fracas no banco cobertas por um `substitui` da rodada 4", [r for r in antes_r6 if (r[0], normalizar_url(r[1])) in cobertas], [])
    nao = sorted(_alvo(dict(n, alvo_tipo=n.get("alvo_tipo", "evento"))) for n in cfg.get("nao_encontrados", []))
    esperar("alvos das fracas restantes da rodada 4 (fracas + rebaixadas pela R6) == alvos de `nao_encontrados`", sorted(r[0] for r in antes_r6), nao)
    cont = cfg.get("decisoes", {}).get("continuam_fracas", [])
    ids_cont = sorted(re.match(r"(ev-[a-z0-9-]+)", c).group(1) for c in cont if c.startswith("ev-"))
    esperar("`continuam_fracas`: uma linha por fraca restante da rodada 4", len(cont), len(antes_r6))
    esperar("`continuam_fracas`: eventos == eventos das fracas restantes da rodada 4", ids_cont, sorted(r[0][1] for r in antes_r6 if r[0][0] == "evento"))
    # aviso de trecho no lote A
    lote_a = ent[:27]
    sem = [e["url"] for e in lote_a if "[trecho via resumo do WebFetch]" not in (e.get("nota") or "") and "literal" not in (e.get("nota") or "").lower()]
    esperar("rodada 4, lote A (27 primeiras): nota com 'trecho via resumo do WebFetch' (ou trecho declarado literal)", sem, [])
    # decisões de correção
    corr_e = json.loads((CURADORIA / "evento-correcoes.json").read_text(encoding="utf-8"))["correcoes"]
    c4 = collections.Counter((c["evento_id"], c["campo"]) for c in corr_e if c.get("rodada") == 4 and c.get("decisao") == "aceitar")
    dec = cfg.get("decisoes", {}).get("correcoes", [])
    esperado = collections.Counter((d["evento_id"], campo) for d in dec if d.get("alvo_tipo", "evento") == "evento" for campo in d["campo"].split("+"))
    esperar("rodada 4: correções de evento (evento, campo) em evento-correcoes.json == decisões do arquivo", sorted(c4.items()), sorted(esperado.items()))
    corr_r = _correcoes_relacao()
    for d in dec:
        if d.get("alvo_tipo") == "relacao":
            c = corr_r.get(d["relacao_origem_ref"], {})
            ok = d["campo"] in c.get("para", {}) and (c.get("rodada_campos") or {}).get(d["campo"]) == 4
            esperar(f"rodada 4: correção de relação {d['relacao_origem_ref']}.{d['campo']} em relacao-correcoes.json", ok, True)
            row = q(con, "SELECT " + d["campo"] + " FROM relacao WHERE origem=? AND origem_ref=?", d["relacao_origem"], d["relacao_origem_ref"])
            esperar(f"rodada 4: {d['relacao_origem_ref']}.{d['campo']} no banco == para", row and row[0][0] == c.get("para", {}).get(d["campo"]), True)
    p = DATA / "relatorio-evidencias-adicionais.md"
    esperar("relatorio-evidencias-adicionais.md tem a seção Rodada 4", "## Rodada 4" in p.read_text(encoding="utf-8"), True)


def rodada3(con):
    """Rodada 3 (data/curadoria/evidencias-rodada3.json): o conteúdo de cada entrada contra o banco já é conferido em evidencias_adicionais
    (a lista inclui a rodada 3); aqui: contagens == arquivo, toda entrada ligada ao evento com papel 'sustenta', correções da rodada
    presentes em evento-correcoes.json e nenhum evento 'nao_classificada' (ou a lista explícita dos que restam)."""
    cfg = _rodada3()
    if not cfg:
        return
    secao("Rodada 3 de fontes (evidencias-rodada3.json aplicada)")
    ent = cfg.get("evidencias", [])
    esperar("evidencias-rodada3.json: toda entrada tem \"rodada\": 3 e alvo_tipo evento", sum(1 for e in ent if e.get("rodada") == 3 and e.get("alvo_tipo") == "evento"), len(ent))
    eventos = {e["evento_id"] for e in ent}
    urls = {normalizar_url(e["url"]) for e in ent}
    ruins, ligadas = [], 0
    for e in ent:
        a = q(con, "SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?", e["evento_id"], e["evento_id"])
        lig = q(con, """SELECT x.papel FROM evento_evidencia x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.evento_id=? AND v.url=?""",
                a[0][0], normalizar_url(e["url"])) if a else []
        if not a:
            ruins.append(f"evento inexistente: {e['evento_id']}")
        elif len(lig) != 1 or lig[0]["papel"] != "sustenta":
            ruins.append(f"{e['evento_id']}: {e['url']} não ligada com papel sustenta ({[r[0] for r in lig]})")
        else:
            ligadas += 1
    for r in ruins[:20]:
        print("   -", r)
    esperar("rodada 3: entradas ligadas ao evento com papel 'sustenta' == entradas do arquivo", ligadas, len(ent))
    n_ev = q(con, f"SELECT count(DISTINCT x.evento_id) FROM evento_evidencia x JOIN evidencia v ON v.id=x.evidencia_id "
                  f"WHERE x.papel='sustenta' AND v.url IN ({','.join('?' * len(urls))})", *urls)[0][0] if urls else 0
    print(f"  info: rodada 3: {len(ent)} entradas, {len(eventos)} eventos, {len(urls)} URLs distintas ({n_ev} eventos ligados a elas por 'sustenta')")
    esperar("rodada 3: evidências no banco para as URLs do arquivo", q(con, f"SELECT count(*) FROM evidencia WHERE url IN ({','.join('?' * len(urls))})", *urls)[0][0], len(urls))
    # correções: toda decisão com campo de texto tem correção 'rodada': 3 em evento-correcoes.json; 'nenhum' não gera correção
    corr = json.loads((CURADORIA / "evento-correcoes.json").read_text(encoding="utf-8"))["correcoes"]
    c3 = {c["evento_id"] for c in corr if c.get("rodada") == 3}
    dec = cfg.get("decisoes", {}).get("correcoes", [])
    falta = [d["evento_id"] for d in dec if d.get("campo") != "nenhum" and d["evento_id"] not in c3]
    sobra = sorted(c3 - {d["evento_id"] for d in dec if d.get("campo") != "nenhum"})
    esperar("rodada 3: decisões com campo de texto sem correção em evento-correcoes.json", falta, [])
    esperar("rodada 3: correções 'rodada': 3 sem decisão no arquivo", sobra, [])
    esperar("rodada 3: correções só em eventos da rodada", sorted(c3 - eventos), [])
    for n in cfg.get("nao_encontrados", []):
        esperar(f"rodada 3: não encontrado {n['evento_id']} tem evidência registrada mesmo assim", n["evento_id"] in eventos, True)
    restam = [r[0] for r in q(con, "SELECT id FROM evento WHERE natureza_id='nao_classificada' ORDER BY data, id")]
    for i in restam:
        print("   - continua nao_classificada:", i)
    esperar("eventos nao_classificada depois da rodada 3", len(restam), 0)
    esperar("rodada 3: eventos cobertos que continuam nao_classificada", sorted(eventos & set(restam)), [])
    p = DATA / "relatorio-evidencias-adicionais.md"
    esperar("relatorio-evidencias-adicionais.md tem a seção Rodada 3", "## Rodada 3" in p.read_text(encoding="utf-8"), True)


def evidencias_adicionais(con):
    secao("Evidências adicionais (data/curadoria/evidencias-adicionais.json + evidencias-rodada3.json + substituicoes-rodada4.json aplicadas)")
    n = q(con, "SELECT count(*) FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id)")[0][0]
    esperar("eventos sem nenhuma evidência", n, 0)
    n = q(con, "SELECT count(*) FROM relacao r WHERE r.status='publicada' AND NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id)")[0][0]
    esperar("relações publicadas sem nenhuma evidência", n, 0)
    ent = _evidencias_adicionais()
    revistas = _revisoes_qualidade()   # (alvo_tipo, alvo, url) que a revisão do critério devolveu a 'boa'
    rep4 = _repeticoes_rodada4(ent)    # repetições aceitas da rodada 4 (reavaliada: mesma URL da fraca; ja_ligada: a URL já era `boa` no alvo)
    fb = _fontes_brasil()
    chaves, ruins, fracas, n_revistas, n_r6 = set(), [], 0, 0, 0
    r6 = bool(_r6())
    for i, e in enumerate(ent):
        k = (e["alvo_tipo"], e.get("evento_id") or (e["relacao_origem"], e["relacao_origem_ref"]), normalizar_url(e["url"]))
        if k in chaves and i not in rep4:
            ruins.append(f"entrada repetida: {k}")
        chaves.add(k)
        if rep4.get(i) == "ja_ligada":
            # a ligação é a da entrada anterior (trecho/nota da rodada 2/3, já conferidos acima); aqui só papel e qualidade
            a = q(con, "SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?", e["evento_id"], e["evento_id"]) \
                if e["alvo_tipo"] == "evento" else []
            lig = q(con, "SELECT l.papel, l.qualidade FROM evento_evidencia l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.evento_id=? AND v.url=?",
                    a[0][0], k[2]) if a else []
            if [tuple(x) for x in lig] != [("sustenta", "boa")]:
                ruins.append(f"substituta já ligada sem ligação sustenta/boa: {k}")
            continue
        if e["qualidade"] not in ("boa", "fraca") or (e["qualidade"] == "fraca") != bool(e.get("motivo_fraca")):
            ruins.append(f"qualidade/motivo_fraca inconsistentes: {k}")
        if e.get("substituida_por") and e["qualidade"] != "fraca":
            ruins.append(f"substituida_por em entrada que não é fraca: {k}")
        if e.get("substituida_por") and e.get("substitui"):
            ruins.append(f"entrada ao mesmo tempo substituída e substituta: {k}")
        subs_url = bool(e.get("substituida_por")) and e["qualidade"] == "fraca"
        fracas += e["qualidade"] == "fraca" and not subs_url
        for su in _subst_por(e):   # cada nova fonte tem de estar no arquivo, no mesmo alvo, apontando de volta (`substitui`) e ligada
            nova = [x for x in ent if (x["alvo_tipo"], x.get("evento_id") or (x["relacao_origem"], x["relacao_origem_ref"])) == k[:2]
                    and normalizar_url(x["url"]) == su and x.get("substitui")]
            if any(x.get("rodada") == 4 for x in nova):   # rodada 4: a substituta aponta exatamente para esta fraca
                nova = [x for x in nova if x.get("rodada") == 4 and normalizar_url(x["substitui"]) == k[2]]
            if len(nova) != 1:
                ruins.append(f"substituida_por sem entrada substituta (com `substitui`) no mesmo alvo: {k} -> {su}")
            elif nova[0]["qualidade"] != "boa":
                ruins.append(f"substituta não é de qualidade boa: {k}")
        ev = q(con, "SELECT id, tipo FROM evidencia WHERE url=?", normalizar_url(e["url"]))
        if subs_url:   # fraca substituída: fica só no arquivo (histórico); não pode estar ligada ao alvo como fonte avaliada
            if e["alvo_tipo"] == "evento":
                a = q(con, "SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?", e["evento_id"], e["evento_id"])
                lig = q(con, "SELECT papel, qualidade, trecho_citado, nota, rotulo FROM evento_evidencia WHERE evento_id=? AND evidencia_id=?",
                        a[0][0], ev[0][0]) if a and ev else []
            else:
                a = q(con, "SELECT id FROM relacao WHERE origem=? AND origem_ref=?", e["relacao_origem"], e["relacao_origem_ref"])
                lig = q(con, "SELECT papel, qualidade, trecho_citado, nota, NULL AS rotulo FROM relacao_evidencia WHERE relacao_id=? AND evidencia_id=?",
                        a[0][0], ev[0][0]) if a and ev else []
            if not a:
                ruins.append(f"alvo ausente: {k}")
            if lig and k[2] in _subst_por(e):
                pass   # reavaliação (rodada 4): a mesma URL foi relida; a ligação é a da substituta, conferida na entrada dela
            elif lig and not (e["alvo_tipo"] == "evento" and k[2] in fb.get(e["evento_id"], set()) and lig[0]["papel"] == "contexto"
                              and (lig[0]["qualidade"], lig[0]["trecho_citado"], lig[0]["nota"], lig[0]["rotulo"]) == (None, None, None, None)):
                # única ligação aceita: a fonte bruta do bloco-ano (brasil-fontes.json) de volta a `contexto`, sem avaliação
                ruins.append(f"fonte fraca substituída ainda ligada ao alvo: {k}")
            continue
        if not ev:
            ruins.append(f"evidência ausente: {e['url']}")
            continue
        if e["alvo_tipo"] == "evento":
            a = q(con, "SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?", e["evento_id"], e["evento_id"])
            lig = q(con, "SELECT trecho_citado, nota, qualidade, rotulo, papel FROM evento_evidencia WHERE evento_id=? AND evidencia_id=?", a[0][0], ev[0][0]) if a else []
            if lig and lig[0]["rotulo"] != e["titulo"]:
                ruins.append(f"rótulo != título: {k}")
        else:
            a = q(con, "SELECT id FROM relacao WHERE origem=? AND origem_ref=?", e["relacao_origem"], e["relacao_origem_ref"])
            lig = q(con, "SELECT trecho_citado, nota, qualidade, papel FROM relacao_evidencia WHERE relacao_id=? AND evidencia_id=?", a[0][0], ev[0][0]) if a else []
            if a and e.get("descricao_nova"):
                d = q(con, "SELECT descricao FROM relacao WHERE id=?", a[0][0])[0][0]
                esperada = _correcoes_relacao().get(e["relacao_origem_ref"], {}).get("para", {}).get("descricao", e["descricao_nova"])   # correção aceita posterior vale
                if d != esperada:
                    ruins.append(f"descricao de {k[1]} difere de descricao_nova")
        if not a:
            ruins.append(f"alvo ausente: {k}")
        elif not lig:
            ruins.append(f"ligação ausente: {k}")
        else:
            # qualidade esperada = a do arquivo, salvo se a revisão do critério (evidencia-qualidade-revisao.json) devolveu esta fonte fraca a 'boa'
            revista = k in revistas
            if revista and e["qualidade"] != "fraca":
                ruins.append(f"revisão de qualidade sobre entrada que não é fraca: {k}")
            n_revistas += revista
            q_esp, p_esp = ("boa" if revista else e["qualidade"]), "sustenta"
            if r6 and (_eh_wiki(e.get("tipo"), k[2]) or _eh_wiki(ev[0]["tipo"], k[2])):   # R6: wiki é `contexto`, sem avaliação
                n_r6 += q_esp == "fraca"
                q_esp, p_esp = None, "contexto"
            if (lig[0]["trecho_citado"], lig[0]["nota"], lig[0]["qualidade"], lig[0]["papel"]) != (e["trecho"], e["nota"] or None, q_esp, p_esp):
                ruins.append(f"trecho/nota/qualidade/papel diferem do arquivo: {k}")
    for r in ruins[:20]:
        print("   -", r)
    esperar("evidencias-adicionais.json: entradas aplicadas e idênticas ao banco (divergências)", len(ruins), 0)
    nf = (q(con, "SELECT count(*) FROM evento_evidencia WHERE qualidade='fraca'")[0][0] + q(con, "SELECT count(*) FROM relacao_evidencia WHERE qualidade='fraca'")[0][0])
    esperar("ligações com qualidade 'fraca' no banco == entradas fracas do arquivo sem `substituida_por` − revistas para 'boa' − wiki rebaixadas pela R6 "
            f"({fracas} − {n_revistas} − {n_r6})", nf, fracas - n_revistas - n_r6)
    esperar("wiki fracas rebaixadas pela R6 (evidências adicionais) == FRACAS_REBAIXADAS_R6", n_r6, len(FRACAS_REBAIXADAS_R6) if r6 else 0)
    p = DATA / "relatorio-evidencias-adicionais.md"
    esperar("data/relatorio-evidencias-adicionais.md existe", p.exists(), True)


def _revisoes_qualidade():
    """Chaves (alvo_tipo, alvo, URL normalizada) de `revisoes` em data/curadoria/evidencia-qualidade-revisao.json."""
    p = CURADORIA / "evidencia-qualidade-revisao.json"
    if not p.exists():
        return set()
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return {(x["alvo_tipo"], x.get("evento_id") or (x["relacao_origem"], x["relacao_origem_ref"]), normalizar_url(x["url"]))
            for x in cfg.get("revisoes", [])}


def evidencia_qualidade(con):
    """Revisão do critério 'fraca' (data/curadoria/evidencia-qualidade-revisao.json, aplicada por curadoria.aplicar_evidencia_qualidade).
    Toda entrada de `revisoes` tem de apontar para uma ligação existente com qualidade 'boa', salvo as que revisam uma fonte fraca já substituída
    em evidencias-adicionais.json (`substituida_por`), que tem de continuar DESligada do alvo. Contagem: fracas no banco (evento_evidencia +
    relacao_evidencia) == fracas ligadas antes da revisão − revisões distintas aplicadas; e, equivalente, == `mantidas_fracas` − substituídas
    (que entram em `mantidas_fracas` mas não estão ligadas) + revisões sobre substituídas + revisões repetidas (que `mantidas_fracas` desconta
    duas vezes)."""
    p = CURADORIA / "evidencia-qualidade-revisao.json"
    if not p.exists():
        return
    secao("Revisão do critério 'fraca' (evidencia-qualidade-revisao.json aplicada)")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    rev = cfg.get("revisoes", [])
    adic = {}
    for e in _evidencias_adicionais():   # a primeira entrada de cada (alvo, URL): as repetições aceitas da rodada 4 não são fontes novas a avaliar
        adic.setdefault((e["alvo_tipo"], e.get("evento_id") or (e["relacao_origem"], e["relacao_origem_ref"]), normalizar_url(e["url"])), e)
    ruins, vistos, aplic, sobre_subst, repetidas = [], {}, 0, 0, 0
    for x in rev:
        k = (x["alvo_tipo"], x.get("evento_id") or (x["relacao_origem"], x["relacao_origem_ref"]), normalizar_url(x["url"]))
        if x.get("qualidade") != "boa" or not x.get("motivo"):
            ruins.append(f"qualidade != 'boa' ou motivo ausente: {k}")
        if k in vistos:
            repetidas += 1
            if vistos[k] != (x.get("qualidade"), x.get("motivo")):
                ruins.append(f"repetida com conteúdo diferente: {k}")
            continue
        vistos[k] = (x.get("qualidade"), x.get("motivo"))
        orig = adic.get(k)
        if not orig or orig["qualidade"] != "fraca":
            ruins.append(f"revisão sem entrada fraca correspondente em evidencias-adicionais.json: {k}")
            continue
        if x["alvo_tipo"] == "evento":
            a = q(con, "SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?", x["evento_id"], x["evento_id"])
            lig = q(con, "SELECT l.qualidade, l.nota FROM evento_evidencia l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.evento_id=? AND v.url=?",
                    a[0][0], k[2]) if a else []
        else:
            a = q(con, "SELECT id FROM relacao WHERE origem=? AND origem_ref=?", x["relacao_origem"], x["relacao_origem_ref"])
            lig = q(con, "SELECT l.qualidade, l.nota FROM relacao_evidencia l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.relacao_id=? AND v.url=?",
                    a[0][0], k[2]) if a else []
        if not a:
            ruins.append(f"alvo ausente: {k}")
        elif orig.get("substituida_por"):
            sobre_subst += 1
            if lig:
                ruins.append(f"fonte fraca substituída ligada ao alvo: {k}")
        elif len(lig) != 1 or lig[0]["qualidade"] != "boa":
            ruins.append(f"ligação ausente ou qualidade != 'boa': {k} {[tuple(r) for r in lig]}")
        elif lig[0]["nota"] != (orig.get("nota") or None):
            ruins.append(f"nota do pesquisador alterada: {k}")
        else:
            aplic += 1
    for r in ruins[:20]:
        print("   -", r)
    esperar("revisoes: toda entrada aponta para uma ligação 'boa' com a nota intacta (ou para fraca substituída, desligada) (divergências)", len(ruins), 0)
    esperar("revisoes: entradas == aplicadas + sobre substituídas + repetidas", len(rev), aplic + sobre_subst + repetidas)
    fr_arq = [e for e in adic.values() if e["qualidade"] == "fraca"]
    subst = sum(1 for e in fr_arq if e.get("substituida_por"))
    ligadas_antes = len(fr_arq) - subst
    nf = {t: q(con, f"SELECT count(*) FROM {t} WHERE qualidade='fraca'")[0][0] for t in ("evento_evidencia", "relacao_evidencia")}
    print(f"  fracas no banco: evento_evidencia {nf['evento_evidencia']}, relacao_evidencia {nf['relacao_evidencia']}")
    # R6: fracas ligadas, não revistas, da Wikipédia: viraram `contexto` sem avaliação (não contam mais como fracas)
    r6 = sorted((k[:2], k[2]) for k, e in adic.items() if _r6() and e["qualidade"] == "fraca" and not e.get("substituida_por")
                and k not in vistos and _eh_wiki(e.get("tipo"), k[2]))
    esperar("R6: fracas da Wikipédia rebaixadas a contexto == FRACAS_REBAIXADAS_R6", [(a, normalizar_url(u)) for a, u in r6],
            [(a, normalizar_url(u)) for a, u in FRACAS_REBAIXADAS_R6] if _r6() else [])
    esperar(f"ligações 'fraca' no banco == fracas ligadas antes ({ligadas_antes}) − revistas ({aplic}) − rebaixadas pela R6 ({len(r6)})",
            sum(nf.values()), ligadas_antes - aplic - len(r6))
    mant = cfg.get("mantidas_fracas")
    esperar("mantidas_fracas do arquivo == fracas em evidencias-adicionais.json − entradas de revisoes", mant, len(fr_arq) - len(rev))
    esperar(f"ligações 'fraca' no banco == mantidas_fracas ({mant}) − substituídas ({subst}) + revisões sobre substituídas ({sobre_subst}) + repetidas ({repetidas})"
            f" − rebaixadas pela R6 ({len(r6)})",
            sum(nf.values()), mant - subst + sobre_subst + repetidas - len(r6))
    # nenhuma fonte de origem diferente de evidencias-adicionais.json tem qualidade avaliada: toda 'fraca' no banco tem entrada fraca no arquivo
    fora = [r for t, c in (("evento_evidencia", "evento_id"), ("relacao_evidencia", "relacao_id"))
            for r in q(con, f"SELECT '{t}' t, {c} a, v.url FROM {t} l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.qualidade='fraca'")
            if not any(k[2] == r["url"] and e["qualidade"] == "fraca" and not e.get("substituida_por") for k, e in adic.items())]
    esperar("ligações 'fraca' no banco sem entrada fraca (não substituída) em evidencias-adicionais.json", len(fora), 0)


_PAPEIS_FONTE = {"sustenta": 0, "contesta": 1, "contexto": 2}


def _chave_fonte(f):
    """Ordem especificada das listas `fontes` exportadas: sustenta (oficial, imprensa, outros), contexto, Wikipédia por último de tudo."""
    oficial = f["tipo"] in ("documento_oficial", "dado_oficial", "decisao_judicial", "comunicado") or CUR.fonte_oficial(f["url"])
    return (_eh_wiki(f["tipo"], f["url"]), _PAPEIS_FONTE.get(f.get("papel"), 9), 0 if oficial else 1 if f["tipo"] in ("reportagem", "relatorio") else 2)


def peso_wikipedia(con, exp):
    """R6 (data/curadoria/regras-fontes.json, curadoria.aplicar_peso_wikipedia): fonte Wikipédia nunca tem papel 'sustenta'; ligações wiki sem
    avaliação; nenhum evento/relação com wiki fica sem fonte 'sustenta'; R6 não muda a natureza (R5 recalculado com as wiki como 'sustenta' ==
    natureza no banco); e as listas `fontes` exportadas (teia E[].r/EV/N[].sat, series eventos, violencia marcos, dossie brb.eventos) trazem
    `papel` em toda fonte, igual ao do banco, na ordem especificada (sustenta: oficial, imprensa, outros; contexto; Wikipédia por último;
    empate pela ordem da ligação)."""
    secao("R6: peso da Wikipédia (regras-fontes.json aplicada; fontes exportadas com papel e ordem)")
    cfg = _r6()
    esperar("regras-fontes.json: {\"wikipedia\": \"contexto\", \"motivo\": ...}", (cfg.get("wikipedia"), bool(cfg.get("motivo"))), ("contexto", True))
    lig = {t: [x for x in q(con, f"SELECT x.{c} AS dono, x.papel, x.qualidade, x.ordem, v.url, v.tipo FROM {t} x JOIN evidencia v ON v.id=x.evidencia_id")]
           for t, c in (("evento_evidencia", "evento_id"), ("relacao_evidencia", "relacao_id"))}
    for t, ls in lig.items():
        w = [x for x in ls if _eh_wiki(x["tipo"], x["url"])]
        esperar(f"{t}: nenhuma ligação wiki com papel sustenta", sorted((str(x["dono"]), x["url"]) for x in w if x["papel"] == "sustenta"), [])
        esperar(f"{t}: ligações wiki com qualidade avaliada (contexto não é avaliado)", sorted((str(x["dono"]), x["url"]) for x in w if x["qualidade"] is not None), [])
        com_wiki = {x["dono"] for x in w}
        com_sust = {x["dono"] for x in ls if x["papel"] == "sustenta"}
        esperar(f"{t}: alvos com fonte wiki e sem nenhuma fonte 'sustenta'", sorted(map(str, com_wiki - com_sust)), [])
        print(f"  info: {t}: {len(w)} ligações wiki, todas 'contexto', em {len(com_wiki)} alvos")
    # R6 não muda a natureza: R5 com as wiki de volta a 'sustenta' (cota superior do que a R6 tirou) dá a mesma natureza do banco
    gerado = json.loads((CURADORIA / "eventos-natureza.json").read_text(encoding="utf-8"))
    por_ev = collections.defaultdict(list)
    for x in sorted(lig["evento_evidencia"], key=lambda x: (x["dono"], x["ordem"])):
        por_ev[x["dono"]].append((x["tipo"], x["url"], "sustenta" if _eh_wiki(x["tipo"], x["url"]) else x["papel"]))
    muda, n_r5 = [], 0
    for n in gerado:
        if n["regra"].startswith("R5"):
            n_r5 += 1
            nat = q(con, "SELECT natureza_id FROM evento WHERE id=?", n["id"])
            sem_r6 = CUR.classificar_natureza_r5(por_ev.get(n["id"], []))[0]
            if not nat or sem_r6 != nat[0][0] or n["natureza"] != nat[0][0]:
                muda.append((n["id"], n["natureza"], sem_r6))
    print(f"  info: {n_r5} eventos com natureza por R5 conferidos")
    esperar("R6 não muda a natureza de nenhum evento (R5 com as wiki como 'sustenta' == natureza no banco)", muda, [])
    # fontes exportadas: papel em toda fonte, igual ao do banco, e ordem especificada
    ordem_db = {t: {(x["dono"], x["url"]): (x["papel"], x["ordem"]) for x in ls} for t, ls in lig.items()}
    rel_id = {r["origem_ref"]: r["id"] for r in q(con, "SELECT id, origem_ref FROM relacao WHERE origem='teia'")}
    sat_id = {r["de"]: r["id"] for r in q(con, "SELECT id, de FROM relacao WHERE origem_ref LIKE 'N[%'")}
    listas = []   # (onde, tabela, dono, fontes)
    t = exp["teia.json"]
    for i, e in enumerate(t["E"]):
        for j, r in enumerate(e["r"]):
            listas.append((f"teia E[{i}].r[{j}]", "relacao_evidencia", rel_id.get(f"E[{i}].r[{j}]"), r.get("fontes")))
    for i, e in enumerate(t["EV"]):
        listas.append((f"teia EV[{i}]", "evento_evidencia", e.get("id"), e.get("fontes")))
    for i, n in enumerate(t["N"]):
        if "sat" in n:
            listas.append((f"teia N[{i}].sat", "relacao_evidencia", sat_id.get(n["id"]), n["sat"].get("fontes")))
    for e in exp["series.json"]["eventos"]:
        listas.append((f"series {e['id']}", "evento_evidencia", e["id"], e.get("fontes")))
    for m in exp["violencia.json"]["marcos"]:
        listas.append((f"violencia {m['id']}", "evento_evidencia", m["id"], m.get("fontes")))
    for e in exp["dossie.json"]["brb"]["eventos"]:
        listas.append((f"dossie brb {e.get('id')}", "evento_evidencia", e.get("id"), e.get("fontes")))
    sem_papel, papel_dif, fora_ordem, n_f = [], [], [], 0
    for onde, tab, dono, fs in listas:
        if fs is None or dono is None:
            sem_papel.append(f"{onde}: sem `fontes` ou sem alvo no banco")
            continue
        n_f += len(fs)
        for f in fs:
            db = ordem_db[tab].get((dono, f["url"]))
            if "papel" not in f:
                sem_papel.append(f"{onde}: {f['url']}")
            elif not db or db[0] != f["papel"]:
                papel_dif.append(f"{onde}: {f['url']} {f.get('papel')} != {db and db[0]}")
        if all("papel" in f and (dono, f["url"]) in ordem_db[tab] for f in fs):
            esperado = sorted(fs, key=lambda f: (_chave_fonte(f), ordem_db[tab][(dono, f["url"])][1]))
            if [f["url"] for f in fs] != [f["url"] for f in esperado]:
                fora_ordem.append(onde)
    print(f"  info: {len(listas)} listas `fontes` exportadas, {n_f} fontes")
    esperar("fontes exportadas sem `papel` (ou lista sem alvo)", sem_papel[:10], [])
    esperar("fontes exportadas com `papel` diferente do banco", papel_dif[:10], [])
    esperar("fontes exportadas fora da ordem (sustenta: oficial, imprensa, outros; contexto; Wikipédia por último; empate: ordem da ligação)", fora_ordem[:10], [])
    wiki_sust = [onde for onde, _, _, fs in listas for f in (fs or []) if _eh_wiki(f["tipo"], f["url"]) and f.get("papel") != "contexto"]
    esperar("fontes exportadas: Wikipédia sempre com papel contexto", wiki_sust[:10], [])


def _correcoes_relacao():
    """{origem_ref: entrada} das correções de relação aceitas (data/curadoria/relacao-correcoes.json), de linha_do_tempo e da teia."""
    p = CURADORIA / "relacao-correcoes.json"
    if not p.exists():
        return {}
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return {c["origem_ref"]: c for g in ("periodos", "vinculos_teia") for c in cfg.get(g, []) if c.get("decisao") == "aceitar"}


def revisao_evidencias(con):
    secao("Revisão das ressalvas (evento-correcoes.json e relacao-correcoes.json aplicados)")
    cfg_e = json.loads((CURADORIA / "evento-correcoes.json").read_text(encoding="utf-8"))
    ruins = []
    n_e = 0
    for c in cfg_e["correcoes"]:
        if c.get("decisao") == "manter":
            continue
        n_e += 1
        r = q(con, "SELECT id, titulo, descricao FROM evento WHERE id=?", c["evento_id"]) or \
            q(con, "SELECT e.id, e.titulo, e.descricao FROM evento_alias a JOIN evento e ON e.id=a.evento_id WHERE a.alias=?", c["evento_id"])
        if not r:
            ruins.append(f"evento inexistente: {c['evento_id']}")
            continue
        valor = r[0][c["campo"]] or ""
        if valor.count(c["para"]) != 1:
            ruins.append(f"{c['evento_id']}/{c['campo']}: `para` ocorre {valor.count(c['para'])} vez(es)")
        if c["de"] in valor and c["de"] not in c["para"]:
            ruins.append(f"{c['evento_id']}/{c['campo']}: `de` ainda presente")
    esperar("evento-correcoes.json: correções com `para` presente e `de` ausente (divergências)", len(ruins), 0)
    nao = [n["evento_id"] for n in cfg_e.get("nao_encontrados_rodada2", [])]
    cobertos_r3 = {e["evento_id"] for e in _rodada3().get("evidencias", [])}   # a rodada 3 achou fonte para eles: deixam de ser nao_classificada
    ruim_nao = [i for i in nao if (q(con, "SELECT natureza_id FROM evento WHERE id=?", i) or [[None]])[0][0] != "nao_classificada" and i not in cobertos_r3]
    ruim_nao += [i for i in nao if not q(con, "SELECT 1 FROM evento WHERE id=?", i)]
    print(f"  info: não encontrados da rodada 2: {len(nao)}, dos quais {len(set(nao) & cobertos_r3)} cobertos pela rodada 3")
    esperar("evento-correcoes.json: não encontrados da rodada 2 existem e, se a rodada 3 não os cobriu, continuam nao_classificada (divergências)", ruim_nao, [])
    for x in ruins[:20]:
        print("   -", x)
    ruins = []
    cfg_r = json.loads((CURADORIA / "relacao-correcoes.json").read_text(encoding="utf-8"))
    tipos = set(re.findall(r"'([a-z_]+)'", re.search(r"tipo TEXT NOT NULL CHECK \(tipo IN \(([^)]*)\)", q(con, "SELECT sql FROM sqlite_master WHERE name='relacao'")[0][0]).group(1)))
    n_r = 0
    for g in ("periodos", "vinculos_teia"):
        for c in cfg_r[g]:
            row = q(con, """SELECT r.*, d.nome AS nome_de FROM relacao r JOIN entidade d ON d.id=r.de WHERE r.origem=? AND r.origem_ref=?""", c["origem"], c["origem_ref"])
            if not row:
                ruins.append(f"relação inexistente: {c['origem']} {c['origem_ref']}")
                continue
            row = row[0]
            if row["nome_de"] != c["alvo"]["de"] or row["rotulo"] != (c["para"]["rotulo"] if c.get("decisao") == "aceitar" and "rotulo" in c["para"] else c["alvo"]["rotulo"]):
                ruins.append(f"{c['origem_ref']}: alvo não bate com o banco")
            if c.get("decisao") != "aceitar":
                continue
            n_r += 1
            for k, v in c["para"].items():
                if row[k] != v:
                    ruins.append(f"{c['origem_ref']}: {k}={row[k]!r} != {v!r}")
            if row["tipo"] not in tipos:
                ruins.append(f"{c['origem_ref']}: tipo {row['tipo']!r} fora do CHECK")
            for k in ("periodo_inicio", "periodo_fim"):
                if row[k] is not None and not re.match(r"[0-9]{4}", row[k]):
                    ruins.append(f"{c['origem_ref']}: {k} fora do CHECK")
            if row["ano_fim"] is not None and row["ano_inicio"] is not None and row["ano_fim"] < row["ano_inicio"]:
                ruins.append(f"{c['origem_ref']}: periodo_fim anterior ao início")
    esperar("relacao-correcoes.json: correções com valores novos no banco e alvo conferido (divergências)", len(ruins), 0)
    for x in ruins[:20]:
        print("   -", x)
    esperar("relações com `tipo` fora da lista do CHECK", q(con, "SELECT count(*) FROM relacao WHERE tipo NOT IN (%s)" % ",".join("?" * len(tipos)), *sorted(tipos))[0][0], 0)
    p = DATA / "relatorio-revisao-evidencias.md"
    esperar("data/relatorio-revisao-evidencias.md existe", p.exists(), True)
    if p.exists():
        esperar("relatório: eventos corrigidos == correções aceitas do arquivo", f"| eventos corrigidos | {n_e} |" in p.read_text(encoding="utf-8"), True)


def evidencia_curadoria(con):
    secao("Evidências: correções de tipo e metadados (evidencia-correcoes.json e evidencia-metadados.json aplicados)")
    ruins = []
    corr = json.loads((CURADORIA / "evidencia-correcoes.json").read_text(encoding="utf-8"))
    tipos = set(re.findall(r"'([a-z_]+)'", re.search(r"tipo TEXT NOT NULL DEFAULT 'reportagem' CHECK \(tipo IN \(([^)]*)\)",
                                                      (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")).group(1)))
    for c in corr:
        r = q(con, "SELECT tipo FROM evidencia WHERE url=?", normalizar_url(c["url"]))
        if not r:
            ruins.append(f"evidência inexistente: {c['url']}")
        elif r[0][0] != c["para"]:
            ruins.append(f"{c['url']}: tipo {r[0][0]!r} != {c['para']!r}")
        if c["para"] not in tipos or c["de"] == c["para"] or not c.get("motivo"):
            ruins.append(f"{c['url']}: entrada inválida (para fora do CHECK, de == para ou sem motivo)")
    esperar("evidencia-correcoes.json: tipo no banco == `para` (divergências)", len(ruins), 0)
    for x in ruins[:20]:
        print("   -", x)
    # nenhum domínio oficial restante como reportagem fora da lista de exceções documentada (notícias das Casas legislativas são jornalismo institucional)
    oficiais = q(con, """SELECT url FROM evidencia WHERE tipo IN ('reportagem','outro') AND (url LIKE '%://www.gov.br/%' OR url LIKE '%://gov.br/%'
                         OR url LIKE '%.jus.br/%')""")
    esperar("evidências de gov.br/jus.br ainda como reportagem/outro", len(oficiais), 0)
    for x in oficiais[:10]:
        print("   -", x[0])
    import enriquecer_evidencias as en
    meta = json.loads((CURADORIA / "evidencia-metadados.json").read_text(encoding="utf-8"))
    ruins = en.erros_arquivo(meta, con)
    for m in meta:
        if m["status"] != "ok":
            continue
        r = q(con, "SELECT titulo, data FROM evidencia WHERE url=?", m["url"])
        if r and ((m["titulo"] and r[0][0] is None) or (m["data"] and r[0][1] is None)):
            ruins.append(f"{m['url']}: metadado do arquivo não chegou ao banco")
    esperar("evidencia-metadados.json: formato válido e aplicado ao banco (divergências)", len(ruins), 0)
    for x in ruins[:20]:
        print("   -", x)
    print(f"  entradas de metadados: {len(meta)} ({sum(m['status'] == 'ok' for m in meta)} ok); correções de tipo: {len(corr)}")


def valores(con, exp):
    """Estimativas em R$ por entidade: entidade_valor == data/curadoria/entidade-valores.json e teia.json N[].val/val_lig == banco."""
    secao("Valores (entidade-valores.json -> entidade_valor -> teia.json N[].val / val_lig)")
    cfg = json.loads((CURADORIA / "entidade-valores.json").read_text(encoding="utf-8"))
    vs = cfg.get("valores", [])
    esperar("entidade_valor: linhas == entradas da curadoria", q(con, "SELECT count(*) FROM entidade_valor")[0][0], len(vs))
    por_ent = collections.Counter(v["entidade_id"] for v in vs)
    no_banco = {r[0]: r[1] for r in q(con, "SELECT entidade_id, count(*) FROM entidade_valor GROUP BY entidade_id")}
    esperar("entidade_valor: valores por entidade == curadoria", no_banco, dict(por_ent))
    esperar("entidade_valor: principais == curadoria", q(con, "SELECT count(*) FROM entidade_valor WHERE principal=1")[0][0],
            sum(bool(v["principal"]) for v in vs))
    esperar("entidades com mais de um principal", len(q(con, "SELECT entidade_id FROM entidade_valor WHERE principal=1 GROUP BY entidade_id HAVING count(*)>1")), 0)
    nats = set(re.findall(r"'([a-z_]+)'", re.search(r"natureza TEXT NOT NULL CHECK \(natureza IN \(([^)]*)\)\),\n  texto TEXT NOT NULL,",
                                                    (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")).group(1)))
    esperar("naturezas do CHECK de entidade_valor", sorted(nats), sorted(cfg.get("naturezas", {})))
    esperar("entidade_valor com natureza fora da lista", q(con, "SELECT count(*) FROM entidade_valor WHERE natureza NOT IN (%s)" % ",".join("?" * len(nats)), *sorted(nats))[0][0], 0)
    esperar("entidade_valor sem evidência", q(con, "SELECT count(*) FROM entidade_valor v WHERE NOT EXISTS (SELECT 1 FROM evidencia e WHERE e.id=v.evidencia_id)")[0][0], 0)
    esperar("entidade_valor fraca sem motivo", q(con, "SELECT count(*) FROM entidade_valor WHERE qualidade='fraca' AND motivo_fraca IS NULL")[0][0], 0)
    # cada entrada da curadoria está no banco, campo a campo (chave: entidade + ordem dentro da entidade)
    ruins, ordem = [], collections.Counter()
    for v in vs:
        k = v["entidade_id"]
        r = q(con, """SELECT v.*, e.url FROM entidade_valor v JOIN evidencia e ON e.id=v.evidencia_id WHERE v.entidade_id=? AND v.ordem=?""", k, ordem[k])
        ordem[k] += 1
        if not r:
            ruins.append(f"{k}[{ordem[k] - 1}]: ausente")
            continue
        r = r[0]
        esp = (float(v["valor_brl"]), v["natureza"], v["texto"], v["quem_estima"], v.get("data"), int(v["principal"]), v["qualidade"],
               v.get("motivo_fraca") or None, v.get("nota") or None, normalizar_url(v["url"]))
        real = (r["valor_brl"], r["natureza"], r["texto"], r["quem_estima"], r["data"], r["principal"], r["qualidade"], r["motivo_fraca"], r["nota"], r["url"])
        if esp != real:
            ruins.append(f"{k}[{ordem[k] - 1}]: banco {real} != curadoria {esp}")
    esperar("entidade_valor == entidade-valores.json campo a campo (divergências)", len(ruins), 0)
    for x in ruins[:20]:
        print("   -", x)
    # teia.json
    teia = exp["teia.json"]
    ev_urls = {r[0] for r in q(con, "SELECT url FROM evidencia")}
    ruins = []
    banco = collections.defaultdict(list)
    for r in q(con, """SELECT v.*, e.url, e.veiculo, e.tipo, e.titulo FROM entidade_valor v JOIN evidencia e ON e.id=v.evidencia_id
                       ORDER BY v.entidade_id, v.principal DESC, v.ordem"""):
        banco[r["entidade_id"]].append((r["valor_brl"], r["natureza"], r["texto"], r["quem_estima"], r["data"], bool(r["principal"]), r["qualidade"],
                                        (r["url"], r["veiculo"], r["tipo"], r["titulo"])))
    lig = {r[0]: (r[1], r[2]) for r in q(con, """SELECT ent, SUM(valor_brl), COUNT(*) FROM (
                SELECT de AS ent, valor_brl FROM relacao WHERE origem_ref LIKE 'E[%' AND valor_brl IS NOT NULL
                UNION ALL SELECT para, valor_brl FROM relacao WHERE origem_ref LIKE 'E[%' AND valor_brl IS NOT NULL) GROUP BY ent""")}
    vistos = set()
    for i, n in enumerate(teia["N"]):
        if "val" not in n:
            if "val_lig" in n:
                ruins.append(f"N[{i}] ({n['id']}): val_lig sem val")
            continue
        vistos.add(n["id"])
        exp_v = [(float(x["brl"]), x["nat"], x["txt"], x["quem"], x["data"], x["principal"], x["qual"],
                  (x["fonte"]["url"], x["fonte"]["veiculo"], x["fonte"]["tipo"], x["fonte"]["titulo"])) for x in n["val"]]
        if exp_v != banco.get(n["id"]):
            ruins.append(f"N[{i}] ({n['id']}): val != banco")
        if sum(x["principal"] for x in n["val"]) > 1 or (any(x["principal"] for x in n["val"]) and not n["val"][0]["principal"]):
            ruins.append(f"N[{i}] ({n['id']}): mais de um principal ou principal fora da primeira posição")
        for x in n["val"]:
            if x["fonte"]["url"] not in ev_urls:
                ruins.append(f"N[{i}] ({n['id']}): fonte.url fora de evidencia: {x['fonte']['url']}")
        l = lig.get(n["id"])
        if (l is None) != ("val_lig" not in n) or (l and (float(n["val_lig"]["brl"]), n["val_lig"]["n"]) != (l[0], l[1])):
            ruins.append(f"N[{i}] ({n['id']}): val_lig {n.get('val_lig')} != banco {l}")
    teia_ids = {r[0] for r in q(con, "SELECT id FROM entidade WHERE ind_legado IS NOT NULL")}
    falt = sorted((set(banco) & teia_ids) - vistos)
    if falt:
        ruins.append("nós com valor no banco sem `val` em teia.json: " + ", ".join(falt))
    fora = sorted(set(banco) - teia_ids)
    print(f"  info: entidades com valor fora da teia (não aparecem no painel): {len(fora)}" + (" -> " + ", ".join(fora) if fora else ""))
    esperar("teia.json N[].val / val_lig == banco; fonte.url ∈ evidencia (divergências)", len(ruins), 0)
    for x in ruins[:20]:
        print("   -", x)
    print(f"  {len(vs)} valores em {len(por_ent)} entidades; {sum(v['qualidade'] == 'fraca' for v in vs)} com fonte fraca; "
          f"{sum('val_lig' in n for n in teia['N'])} nós com soma das ligações")


def natureza_eventos(con, gerado):
    """Nenhum evento sem natureza (salvo exceção explícita, com justificativa, em eventos-natureza-manual.json) e toda natureza
    aplicada por regra (R1-R5) ou à mão tem regra/justificativa registrada e igual à do banco."""
    manual_p = CURADORIA / "eventos-natureza-manual.json"
    manual = json.loads(manual_p.read_text(encoding="utf-8")) if manual_p.exists() else []
    nat_validas = {r[0] for r in q(con, "SELECT id FROM natureza")}
    ids_ger = {n["id"] for n in gerado}
    for n in gerado:
        if not str(n.get("regra", "")).strip():
            falha(f"eventos-natureza.json: {n['id']} sem regra")
    ids_man = set()
    for m in manual:
        if m["id"] in ids_man:
            falha(f"eventos-natureza-manual.json: id repetido {m['id']}")
        ids_man.add(m["id"])
        if not str(m.get("justificativa", "")).strip():
            falha(f"eventos-natureza-manual.json: {m['id']} sem justificativa")
        if m.get("natureza") is not None and m["natureza"] not in nat_validas:
            falha(f"eventos-natureza-manual.json: natureza inválida em {m['id']}: {m['natureza']}")
        if not q(con, "SELECT 1 FROM evento WHERE id=?", m["id"]):
            falha(f"eventos-natureza-manual.json: evento inexistente {m['id']}")
    excecoes = {m["id"] for m in manual if m.get("natureza") is None}
    nulos = {r[0] for r in q(con, "SELECT id FROM evento WHERE natureza_id IS NULL")}
    esperar("eventos sem natureza fora da lista de exceções (eventos-natureza-manual.json)", sorted(nulos - excecoes), [])
    esperar("exceções declaradas == eventos com natureza NULL", sorted(excecoes - nulos), [])
    # o que o banco tem tem de coincidir com o arquivo que o produziu (gerado primeiro; manual só onde o gerado não pegou)
    dif = []
    revisados = set()   # natureza trocada por decisão humana (decisoes.jsonl) vale mais que a regra
    dec_p = CURADORIA / "decisoes.jsonl"
    if dec_p.exists():
        for linha in dec_p.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                d = json.loads(linha)
                if d.get("tipo") == "evento" and (d.get("acao") == "natureza" or "natureza" in (d.get("campos") or {})):
                    revisados.add(d["alvo"]["id"])
    for n in gerado:
        got = q(con, "SELECT natureza_id FROM evento WHERE id=?", n["id"])
        if n["id"] in revisados:
            continue
        if got and got[0][0] is not None and got[0][0] != n["natureza"]:
            dif.append(n["id"])
    for m in manual:
        if m["id"] in ids_ger or m.get("natureza") is None or m["id"] in revisados:
            continue
        got = q(con, "SELECT natureza_id FROM evento WHERE id=?", m["id"])
        if got and got[0][0] != m["natureza"]:
            dif.append(m["id"])
    esperar("natureza no banco == a registrada em eventos-natureza(.manual).json", dif, [])
    sem_reg = [r[0] for r in q(con, "SELECT id FROM evento WHERE canal IN ('brasil','violencia') AND natureza_id IS NOT NULL") if r[0] not in ids_ger and r[0] not in ids_man]
    esperar("eventos brasil/violencia com natureza sem regra registrada", sem_reg, [])
    print(f"  info: natureza por regra gerada: {len(gerado)} eventos; à mão: {len(manual)} (exceções: {len(excecoes)})")


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
    adic = collections.defaultdict(set)   # URLs que evidencias-adicionais.json liga a cada evento (as fracas substituídas não são ligadas)
    for x in _evidencias_adicionais():
        if x["alvo_tipo"] == "evento" and not (x["qualidade"] == "fraca" and x.get("substituida_por")):
            adic[x["evento_id"]].add(normalizar_url(x["url"]))
    ok = sum(1 for it in fon if {normalizar_url(r[0]) for r in q(con, "SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=?", it["evento_id"])}
             == {normalizar_url(u) for u in it["sustenta"] + it["contexto"]} | adic.get(it["evento_id"], set()))
    esperar("brasil-fontes.json: eventos com todas as fontes ligadas", ok, len(fon))
    n_sem = q(con, "SELECT count(*) FROM evento e WHERE canal='brasil' AND NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id)")[0][0]
    print(f"  info: eventos da timeline Brasil sem fonte (sem item no bruto): {n_sem}")
    natureza_eventos(con, nat)
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
    corr = _correcoes_relacao()   # filiação com período corrigido à mão (Bolsonaro/PSL e Alencar/PL) é a única exceção abaixo
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
    for r in q(con, "SELECT de, para, ano_inicio, ano_fim, origem_ref FROM relacao WHERE subtipo='filiacao'"):
        # filiação com `periodo_fim` corrigido à mão (relacao-correcoes.json; hoje só Bolsonaro/PSL 2019 e Alencar/PL 2003) só precisa sobrepor um mandato do partido; as demais continuam exigindo o mandato dentro do período
        cobre = (lambda a, b: r["ano_inicio"] <= b and a <= r["ano_fim"]) if "periodo_fim" in corr.get(r["origem_ref"], {}).get("para", {}) else (lambda a, b: r["ano_inicio"] <= a <= b <= r["ano_fim"])
        if not any((manual.get(p) == r["para"] or (p, r["para"]) in por_alias) and cobre(a, b)
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
        pt = rs["confirmados_por_tipo"]
        esperar("resumo: confirmados == legislatura + eleicao + pagina", rs["confirmados"], pt["legislatura"] + pt["eleicao"] + pt["pagina"])
        esperar("linhas de mandato com evidência dado_oficial == confirmados por legislatura/eleição", q(con, "SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id WHERE e.tipo='dado_oficial'")[0][0], pt["legislatura"] + pt["eleicao"])
        esperar("linhas de mandato com evidência documento_oficial (página da presidência) == confirmados por página", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.tipo='documento_oficial' AND e.veiculo IN ('www2.camara.leg.br','www25.senado.leg.br')""")[0][0], pt["pagina"])
        esperar("confirmação de eleição só em deputado/senador sem legislatura que toque o ano", [c for c in mo["confirmacoes"] if c["confirmacao"] == "eleicao" and c["cargo"] not in ("deputado", "senador")], [])
        esperar("confirmação por página só em presidente_camara/presidente_senado", [c for c in mo["confirmacoes"] if c["confirmacao"] == "pagina" and c["cargo"] not in ("presidente_camara", "presidente_senado")], [])
        esperar("evidência dos mandatos só em domínios oficiais (Câmara/Senado)", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.veiculo NOT IN ('dadosabertos.camara.leg.br','legis.senado.leg.br','www2.camara.leg.br','www25.senado.leg.br') OR e.url NOT LIKE 'https://'||e.veiculo||'/%'""")[0][0], 0)
        esperar("evidência de API (dado_oficial) só nos domínios das APIs; de página (documento_oficial) só nos das páginas", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE (e.tipo='dado_oficial' AND e.veiculo NOT IN ('dadosabertos.camara.leg.br','legis.senado.leg.br'))
               OR (e.tipo='documento_oficial' AND e.veiculo NOT IN ('www2.camara.leg.br','www25.senado.leg.br'))
               OR e.tipo NOT IN ('dado_oficial','documento_oficial')""")[0][0], 0)
        esperar("relações de mandato confirmado sem a evidência oficial", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id AND e.tipo IN ('dado_oficial','documento_oficial')
            JOIN relacao r ON r.origem_ref='mandato:'||m.id WHERE NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id AND x.evidencia_id=e.id)""")[0][0], 0)
        esperar("divergente/sem fonte com evidência oficial no mandato", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.tipo='dado_oficial' AND m.cargo NOT IN ('deputado','senador')""")[0][0], 0)
        esperar("evidência de página oficial em presidente/vice ou em linha divergente", q(con, """SELECT count(*) FROM mandato m JOIN evidencia e ON e.id=m.evidencia_id
            WHERE e.tipo='documento_oficial' AND (m.cargo NOT IN ('presidente_camara','presidente_senado')
              OR EXISTS (SELECT 1 FROM json_each(?) d WHERE json_extract(d.value,'$.entidade_id')=m.entidade_id AND json_extract(d.value,'$.cargo')=m.cargo AND json_extract(d.value,'$.inicio')=m.inicio))""",
            json.dumps(mo["divergencias"]))[0][0], 0)
        cor_p = CURADORIA / "mandato-correcoes.json"
        cor = json.loads(cor_p.read_text(encoding="utf-8")) if cor_p.exists() else []
        esperar("correções à mão de mandato aplicadas (valor atual == 'para')", [c for c in cor if not q(con, "SELECT 1 FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=? AND "+c["campo"]+"=?", c["entidade_id"], c["cargo"], c["inicio"], c["para"])], [])
        al_p = CURADORIA / "entidade-aliases.json"
        al = json.loads(al_p.read_text(encoding="utf-8")) if al_p.exists() else []
        esperar("aliases à mão presentes em entidade_alias (origem curadoria)", [a for a in al if not q(con, "SELECT 1 FROM entidade_alias WHERE entidade_id=? AND alias=? AND origem='curadoria'", a["entidade_id"], a["alias"])], [])
        n_comp = q(con, "SELECT count(*) FROM mandato WHERE partido IS NULL AND cargo IN ('deputado','senador')")[0][0]
        esperar("deputado/senador com partido NULL após complementos", n_comp, 0)


# página -> arquivo de data/ que ela pede com fetch. Nenhuma página carrega mais cópia dos dados no HTML.
PAGINAS_DADOS = {"brasil-ano-a-ano.html": "series.json", "pares.html": "pares.json", "violencia.html": "violencia.json",
                 "dossie.html": "dossie.json", "teia.html": "teia.json", "origens.html": "origens.json"}
# marcadores do JSON que as páginas traziam embutido antes de lerem data/*.json
MARCADORES_EMBUTIDOS = [r'<script type="application/json"', r"(?m)^\s*(const|var|let) D\s*=\s*\{", r"(?m)^\s*var (SOURCES|CSRC|RACE_RATES)\s*=\s*\{\s*[\w\"]+\s*:",
                        r"(?m)^\s*var (DATA|MARCOS)\s*=\s*\[\s*\{", r"\"homicidios\":\s*\d", r"\"years\":\s*\[1995"]


def paginas(con, exp):
    """As páginas leem data/*.json (fetch, sem cópia embutida) e as exportações que só as páginas usam batem com o banco."""
    secao("Páginas (paginas/*.html leem data/*.json; nenhuma traz os dados embutidos)")
    pdir = DATA.parent / "paginas"
    if not pdir.is_dir():   # cópia só de scripts/ + data/ (fixtures dos testes do MCP): não há site para conferir
        print("  info: sem paginas/ ao lado de data/; conferência do HTML pulada (as exportações abaixo continuam conferidas)")
    for pag, arq in (PAGINAS_DADOS.items() if pdir.is_dir() else ()):
        h = (pdir / pag).read_text(encoding="utf-8")
        emb = [m for m in MARCADORES_EMBUTIDOS if re.search(m, h)]
        esperar(f"{pag}: marcadores de dados embutidos", emb, [])
        pede = sorted(set(re.findall(r"fetch\(\s*['\"]\.\./data/([a-z_]+\.json)['\"]", h)))
        esperar(f"{pag}: arquivo pedido com fetch", pede, [arq])
        esperar(f"{pag}: data/{arq} é exportado por exportar_json.py", arq in exp, True)
        esperar(f"{pag}: tamanho < 100 KB (sem dados)", len(h.encode("utf-8")) < 100_000 or pag == "teia.html", True)
    s, v = exp["series.json"], exp["violencia.json"]
    esperar("series.json: eventos == eventos do canal brasil", len(s["eventos"]), q(con, "SELECT count(*) FROM evento WHERE canal='brasil'")[0][0])
    nat = {r[0] for r in q(con, "SELECT id FROM natureza")}
    ruins = [e["id"] for e in s["eventos"] if e["natureza"] not in nat
             or {f["url"] for f in e["fontes"]} != {r[0] for r in q(con, "SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=?", e["id"])}]
    esperar("series.json: eventos com natureza válida e fontes == evidências no banco (divergências)", ruins, [])
    esperar("series.json: textos de época (nota brasil/aviso) exportados",
            sum(len([k for k in d if k in ("partido", "vice")]) + sum(len(d.get(c, {})) for c in ("presCamara", "presSenado")) for d in s["epoca"].values())
            + sum(1 for r in s["ranking_empresa"] if "nome_epoca" in r),
            q(con, "SELECT count(*) FROM nota WHERE pagina='brasil' AND tipo='aviso' AND chave LIKE 'Y.%'")[0][0])
    esperar("violencia.json: marcos == eventos do canal violencia", [m["id"] for m in v["marcos"]],
            [r[0] for r in q(con, "SELECT id FROM evento WHERE canal='violencia' ORDER BY data, id")])
    esperar("violencia.json: recorte-ano sem fonte", [f"{c}.{a}" for c, r in v["recortes"].items() for a, x in r["anos"].items() if not x["fonte"]], [])
    n_serie = sum(1 for c, r in v["recortes"].items() for x in r["anos"].values() for k in ("segs", "taxas", "pct") for _ in x.get(k, {})) \
        + sum(1 for r in v["recortes"].values() for x in r["anos"].values() if "pub" in x)
    esperar("violencia.json: valores de grupo dos recortes == linhas de serie (sem as taxas só de RACE_RATES)", n_serie,
            q(con, """SELECT count(*) FROM serie s WHERE s.indicador_id LIKE 'violencia.%' AND s.indicador_id NOT LIKE '%.total'
                      AND s.indicador_id <> 'violencia.homicidios' AND COALESCE(s.obs,'') <> 'RACE_RATES'""")[0][0])


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
    evidencias_adicionais(con)
    evidencia_qualidade(con)
    rodada3(con)
    rodada4(con)
    revisao_evidencias(con)
    evidencia_curadoria(con)
    valores(con, exp)
    modelo_v2(con, exp)
    paginas(con, exp)
    peso_wikipedia(con, exp)

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
