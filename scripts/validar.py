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
                  AND NOT EXISTS (SELECT 1 FROM ranking_evidencia s WHERE s.evidencia_id=e.id)
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


_ADIC_REL = {}


def _urls_adicionais_relacao(ref):
    """URLs normalizadas de fontes `boa` de evidencias-adicionais*.json (todas as rodadas, ligadas: sem `substituida_por`) para a relação da teia `ref`."""
    if not _ADIC_REL:
        _ADIC_REL[None] = set()
        for e in _evidencias_adicionais():
            if e["alvo_tipo"] == "relacao" and e["relacao_origem"] == "teia" and not e.get("substituida_por"):
                _ADIC_REL.setdefault(e["relacao_origem_ref"], set()).add(normalizar_url(e["url"]))
    return _ADIC_REL.get(ref, set())


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
        # fontes do export = fontes do raw + as ligadas por evidencias-adicionais*.json a esta relação (rodada 5: a matéria do Estadão em E[209..213].r[0]);
        # qualquer outra diferença continua sendo falha
        extra = _urls_adicionais_relacao(f"E[{ej}].r[{rj}]")
        if urls(a["f"]) | (urls(b["f"]) & extra) != urls(b["f"]) or (urls(b["f"]) - urls(a["f"])) - extra:
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


def _rodada5():
    p = CURADORIA / "evidencias-rodada5.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _rodada6():
    p = CURADORIA / "evidencias-rodada6.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _evidencias_adicionais():
    """Entradas de evidencias-adicionais.json seguidas das `evidencias` de evidencias-rodada3.json, de substituicoes-rodada4.json, de
    evidencias-rodada5.json e de evidencias-rodada6.json (mesma lista que curadoria.ler_evidencias_adicionais aplica; lida aqui de forma independente)."""
    return (json.loads((CURADORIA / "evidencias-adicionais.json").read_text(encoding="utf-8")) + _rodada3().get("evidencias", [])
            + _rodada4().get("evidencias", []) + _rodada5().get("evidencias", []) + _rodada6().get("evidencias", []))


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
# Rodada 5 (evidencias-rodada5.json): substitui as 2 de FRACAS_DEPOIS_R6 (cscb.ca pelo comunicado do USTR; Brasil 247 pelo Estadão). Depois dela: 0.
FRACAS_SUBSTITUIDAS_RODADA5 = list(FRACAS_DEPOIS_R6)
FRACAS_DEPOIS_RODADA5 = sorted(set(FRACAS_DEPOIS_R6) - set(FRACAS_SUBSTITUIDAS_RODADA5))   # = [] (zero ligações `fraca` no banco)


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
    r5 = _rodada5().get("evidencias", [])
    base = len(todas) - len(ent) - len(r5) - len(_rodada6().get("evidencias", []))   # as rodadas 5 e 6 vêm depois da 4 na lista
    rep = {i - base: c for i, c in _repeticoes_rodada4(todas).items() if base <= i < base + len(ent)}
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
    subst5 = {(_alvo(e), normalizar_url(e["substitui"])) for e in r5 if e.get("substitui")}   # as fracas que a rodada 5 desligou depois desta

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
    # a rodada 5 (se aplicada) desligou as FRACAS_SUBSTITUIDAS_RODADA5; o estado ao fim da rodada 4 é o do banco mais elas
    fim_r4 = sorted(restam + [(a, u) for a, u in FRACAS_SUBSTITUIDAS_RODADA5 if (a, normalizar_url(u)) in subst5])
    esperar("fracas no banco ao fim da rodada 4 e da R6 (mais as desligadas pela rodada 5) == FRACAS_RESTANTES_RODADA4 − FRACAS_REBAIXADAS_R6",
            fim_r4, FRACAS_DEPOIS_R6 if rebx else FRACAS_RESTANTES_RODADA4)
    esperar("fracas substituídas pela rodada 5 == FRACAS_SUBSTITUIDAS_RODADA5 (se a rodada 5 está aplicada)",
            sorted((a, u) for a, u in FRACAS_SUBSTITUIDAS_RODADA5 if (a, normalizar_url(u)) in subst5), FRACAS_SUBSTITUIDAS_RODADA5 if r5 else [])
    ruins = []
    for a, u in rebx:   # a wiki que era fraca: continua ligada, agora `contexto`, sem avaliação, com o trecho e a nota da curadoria
        lig = ligacao(a, normalizar_url(u))
        if len(lig) != 1 or (lig[0]["papel"], lig[0]["qualidade"]) != ("contexto", None) or not lig[0]["trecho_citado"]:
            ruins.append(f"{a} {u} {[tuple(x) for x in lig]}")
    esperar("R6: fracas da Wikipédia ligadas como contexto, qualidade NULL, trecho mantido (divergências)", ruins, [])
    antes_r6 = sorted(fim_r4 + rebx)
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


def rodada5(con):
    """Rodada 5 (data/curadoria/evidencias-rodada5.json): as 2 últimas substituições (`substitui`: cscb.ca e Brasil 247) e as fontes adicionais
    (sem `substitui`). O conteúdo de cada entrada contra o banco já é conferido em evidencias_adicionais (a lista inclui a rodada 5); aqui: toda
    entrada `"rodada": 5`/`boa`/papel `sustenta` no banco; cada fraca de `substitui` registrada com `substituida_por` e desligada do alvo; a URL
    compartilhada por vários alvos é uma só `evidencia`; fracas no banco == FRACAS_DEPOIS_RODADA5 (zero, sem afrouxar) e == FRACAS_DEPOIS_R6 −
    FRACAS_SUBSTITUIDAS_RODADA5; natureza do evento de 2018 e relatório com a seção Rodada 5."""
    cfg = _rodada5()
    if not cfg:
        return
    secao("Rodada 5 (evidencias-rodada5.json aplicada: últimas lacunas de fonte)")
    ent = cfg.get("evidencias", [])
    todas = _evidencias_adicionais()
    anteriores = todas[:len(todas) - len(ent) - len(_rodada6().get("evidencias", []))]   # entradas antes da rodada 5 (a rodada 6 vem depois)
    esperar("evidencias-rodada5.json: toda entrada tem \"rodada\": 5 e qualidade boa",
            sum(1 for e in ent if e.get("rodada") == 5 and e.get("qualidade") == "boa"), len(ent))
    subs = [e for e in ent if e.get("substitui")]
    esperar("rodada 5: substituições (entradas com `substitui`) == FRACAS_SUBSTITUIDAS_RODADA5",
            sorted((_alvo(e), normalizar_url(e["substitui"])) for e in subs), sorted((a, normalizar_url(u)) for a, u in FRACAS_SUBSTITUIDAS_RODADA5))
    print(f"  info: rodada 5: {len(ent)} entradas ({sum(1 for e in ent if e['alvo_tipo'] == 'evento')} de evento, {sum(1 for e in ent if e['alvo_tipo'] == 'relacao')} de relação), "
          f"{len({_alvo(e) for e in ent})} alvos, {len({normalizar_url(e['url']) for e in ent})} URLs distintas, {len(subs)} substituições, {len(ent) - len(subs)} fontes adicionais")

    def ligacao(alvo, url):
        if alvo[0] == "evento":
            return q(con, """SELECT l.papel, l.qualidade, l.trecho_citado FROM evento_evidencia l JOIN evidencia v ON v.id=l.evidencia_id
                             WHERE v.url=? AND l.evento_id IN (SELECT id FROM evento WHERE id=? UNION SELECT evento_id FROM evento_alias WHERE alias=?)""",
                     url, alvo[1], alvo[1])
        return q(con, """SELECT l.papel, l.qualidade, l.trecho_citado FROM relacao_evidencia l JOIN evidencia v ON v.id=l.evidencia_id
                         JOIN relacao r ON r.id=l.relacao_id WHERE v.url=? AND r.origem=? AND r.origem_ref=?""", url, *alvo[1])
    ruins = []
    for e in ent:
        a, u = _alvo(e), normalizar_url(e["url"])
        lig = ligacao(a, u)
        if len(lig) != 1 or (lig[0]["papel"], lig[0]["qualidade"], lig[0]["trecho_citado"]) != ("sustenta", "boa", e["trecho"]):
            ruins.append(f"fonte da rodada 5 não ligada como sustenta/boa com o trecho do arquivo: {a} {e['url']} {[tuple(x) for x in lig]}")
        if e.get("substitui"):
            uf = normalizar_url(e["substitui"])
            fr = [x for x in anteriores if (_alvo(x), normalizar_url(x["url"])) == (a, uf)]
            if len(fr) != 1 or fr[0]["qualidade"] != "fraca":
                ruins.append(f"`substitui` sem exatamente uma fonte fraca registrada no alvo: {a} {e['substitui']}")
            elif u not in _subst_por(fr[0]):
                ruins.append(f"fraca {e['substitui']} sem `substituida_por` com {e['url']} ({a})")
            if ligacao(a, uf):
                ruins.append(f"fraca substituída ainda ligada ao alvo: {a} {e['substitui']}")
    for r in ruins[:20]:
        print("   -", r)
    esperar("rodada 5: entradas ligadas, fracas desligadas e `substituida_por` conferidos (divergências)", len(ruins), 0)
    # uma URL ligada a vários alvos é uma só evidência
    n_url = collections.Counter(normalizar_url(e["url"]) for e in ent)
    multi = {u: n for u, n in n_url.items() if n > 1}
    for u, n in multi.items():
        esperar(f"rodada 5: URL ligada a {n} alvos tem uma só `evidencia`", q(con, "SELECT count(*) FROM evidencia WHERE url=?", u)[0][0], 1)
    # zero fracas no banco depois da rodada 5 (constantes, sem afrouxar)
    restam = _fracas_no_banco(con)
    for r in restam:
        print("   - continua fraca:", r[0], r[1])
    esperar("fracas no banco depois da rodada 5 == FRACAS_DEPOIS_RODADA5 (zero)", restam, FRACAS_DEPOIS_RODADA5)
    esperar("FRACAS_DEPOIS_RODADA5 == FRACAS_DEPOIS_R6 − FRACAS_SUBSTITUIDAS_RODADA5 e vazia", (sorted(set(FRACAS_DEPOIS_R6) - set(FRACAS_SUBSTITUIDAS_RODADA5)), FRACAS_DEPOIS_RODADA5), ([], []))
    nf = q(con, "SELECT (SELECT count(*) FROM evento_evidencia WHERE qualidade='fraca') + (SELECT count(*) FROM relacao_evidencia WHERE qualidade='fraca')")[0][0]
    esperar("ligações com qualidade 'fraca' no banco depois da rodada 5", nf, 0)
    p = DATA / "relatorio-evidencias-adicionais.md"
    esperar("relatorio-evidencias-adicionais.md tem a seção Rodada 5", "## Rodada 5" in p.read_text(encoding="utf-8"), True)


def _json_curadoria(nome):
    p = CURADORIA / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _ov_r11():
    """O que a rodada 11 (ranking-empresa-correcoes-r11.json, aplicada depois da 10) sobrescreve em linhas de rodadas anteriores: campos (ano, entidade, campo),
    linhas com principal nova (ano, entidade) e ligações cujo papel/nota a r11 troca (ano, entidade, URL normalizada): as `anterior` e as `reclassificar`.
    As seções das rodadas 6-10 pulam essas conferências (o que a r11 deixa no banco é conferido na seção "Rodada 11")."""
    rk = _json_curadoria("ranking-empresa-correcoes-r11.json")
    campo = {(x["ano"], x["entidade_id"], k) for x in rk.get("atualizar", []) for k in x["campos"]}
    princ = {(x["ano"], x["entidade_id"]) for x in rk.get("atualizar", []) if any(f.get("principal") for f in x["fontes"])}
    url = {(x["ano"], x["entidade_id"], normalizar_url(x["anterior"]["url"])) for x in rk.get("atualizar", []) if x.get("anterior")} \
        | {(x["ano"], x["entidade_id"], normalizar_url(rc["url"])) for x in rk.get("atualizar", []) for rc in x.get("reclassificar", [])}
    return campo, princ, url


def rodada6(con, exp):
    """Rodada 6: ranking-empresa-correcoes.json, mandatos-adicionais.json, eventos-adicionais.json, entidades-adicionais.json e
    evidencias-rodada6.json contra o banco (as entradas de evidencias-rodada6.json também passam por evidencias_adicionais). Regras do ranking
    conferidas em TODAS as linhas (não só nas tocadas), reimplementadas aqui: posição contígua 1..n por ano, lucros em ordem decrescente e depois
    os prejuízos do maior para o menor; pct_total = round(lucro / PIB do ano * 100, 3)."""
    rk, ma, ea, en, r6 = (_json_curadoria(n) for n in ("ranking-empresa-correcoes.json", "mandatos-adicionais.json", "eventos-adicionais.json",
                                                         "entidades-adicionais.json", "evidencias-rodada6.json"))
    if not (rk or ma or ea or en or r6):
        return
    secao("Rodada 6 (ranking-empresa-correcoes, mandatos-adicionais, eventos-adicionais, entidades-adicionais, evidencias-rodada6)")
    # ---- entidades
    ruins = [n["id"] for n in en.get("entidades", []) if [tuple(r) for r in q(con, "SELECT nome, tipo, origem, origem_ref FROM entidade WHERE id=?", n["id"])]
             != [(n["nome"], n["tipo"], "manual", "curadoria:entidades-adicionais.json")]]
    esperar("entidades-adicionais.json: entidades no banco com nome/tipo/origem do arquivo (divergências)", ruins, [])
    # ---- ranking: regras em todas as linhas
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    pos_ruins, pct_ruins = [], []
    for a in [r[0] for r in q(con, "SELECT DISTINCT ano FROM ranking_empresa ORDER BY ano")]:
        rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=? ORDER BY posicao", a)
        if [r["posicao"] for r in rs] != list(range(1, len(rs) + 1)):
            pos_ruins.append(f"{a}: posições {[r['posicao'] for r in rs]}")
        luc = [r["lucro_brl_bi"] for r in rs]
        pos_, neg_ = [x for x in luc if x >= 0], [x for x in luc if x < 0]
        if luc != sorted(pos_, reverse=True) + sorted(neg_):
            pos_ruins.append(f"{a}: ordem dos lucros {luc}")
        pct_ruins += [f"{a}/{r['entidade_id']}: {r['pct_total']} != {round(r['lucro_brl_bi'] / pib[a] * 100, 3)}" for r in rs
                      if r["pct_total"] != round(r["lucro_brl_bi"] / pib[a] * 100, 3)]
    esperar("ranking_empresa: posição contígua 1..n por ano e na regra da carga bruta (lucros decrescentes, depois prejuízos do maior ao menor)", pos_ruins, [])
    esperar("ranking_empresa: pct_total == round(lucro / PIB do ano * 100, 3) em todas as linhas", pct_ruins[:10], [])
    esperar("ranking_empresa: cobertura uniforme por ano", [r[0] for r in q(con, "SELECT ano FROM ranking_empresa GROUP BY ano HAVING count(DISTINCT cobertura) > 1")], [])
    # ---- ranking: arquivo == banco
    ruins, esperado_lig = [], 0
    # Rodada 7 vem por cima da 6 (mesmo formato): o que ela reescreve (campos, fonte principal, papel de uma fonte da 6) é conferido na seção
    # "Rodada 7"; aqui a rodada 6 só é cobrada no que a 7 não toca, e o total de ligações é a união (ano, entidade, URL) dos dois arquivos.
    # A rodada 8 (ranking-empresa-correcoes-r8.json) vem por cima da 7 do mesmo jeito: entra nos conjuntos de sobreposição e na união das ligações.
    # A rodada 9 (ranking-empresa-correcoes-r9.json, 2009-2012) vem por cima da 8 do mesmo jeito.
    rk7 = _json_curadoria("ranking-empresa-correcoes-r7.json")
    rk8 = _json_curadoria("ranking-empresa-correcoes-r8.json")
    rk9 = _json_curadoria("ranking-empresa-correcoes-r9.json")
    # A rodada 10 (ranking-empresa-correcoes-r10.json, fontes primárias) vem por cima da 9 do mesmo jeito.
    rk10 = _json_curadoria("ranking-empresa-correcoes-r10.json")
    # A rodada 11 (ranking-empresa-correcoes-r11.json, BR GAAP do Santander e 6-K de Itaú e Bradesco) vem por cima da 10 do mesmo jeito; ela também reclassifica ligações (`reclassificar`).
    rk11 = _json_curadoria("ranking-empresa-correcoes-r11.json")
    _o11_campo, _o11_princ, _o11_url = _ov_r11()
    ov_campo = {(x["ano"], x["entidade_id"], k) for r in (rk7, rk8, rk9, rk10, rk11) for x in r.get("atualizar", []) for k in x["campos"]}
    ov_princ = {(x["ano"], x["entidade_id"]) for r in (rk7, rk8, rk9, rk10, rk11) for x in r.get("atualizar", []) if any(f.get("principal") for f in x["fontes"])}
    ov_url = {(x["ano"], x["entidade_id"], normalizar_url(x["anterior"]["url"])) for r in (rk7, rk8, rk9, rk10, rk11) for x in r.get("atualizar", []) if x.get("anterior")} | _o11_url
    todas_lig = {(x["ano"], x["entidade_id"], normalizar_url(f["url"])) for arq in (rk, rk7, rk8, rk9, rk10, rk11) for k in ("atualizar", "inserir") for x in arq.get(k, []) for f in x["fontes"]} \
        | {(x["ano"], x["entidade_id"], normalizar_url(x["anterior"]["url"])) for arq in (rk, rk7, rk8, rk9, rk10, rk11) for k in ("atualizar", "inserir") for x in arq.get(k, []) if x.get("anterior")}

    def lig(ano, ent, url):
        return q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                         WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", ano, ent, normalizar_url(url))

    def principal(ano, ent):
        r = q(con, "SELECT v.url, v.tipo FROM ranking_empresa k LEFT JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", ano, ent)
        return (r[0]["url"], r[0]["tipo"]) if r else (None, None)
    _cob_depois = {c["ano"] for arq in ("ranking-empresa-correcoes-r7.json", "ranking-empresa-correcoes-r8.json", "ranking-empresa-correcoes-r9.json", "ranking-empresa-correcoes-r10.json", "ranking-empresa-correcoes-r11.json")
                   for c in (json.load(open(CURADORIA / arq, encoding="utf-8")) if (CURADORIA / arq).exists() else {}).get("cobertura", [])}
    for c in rk.get("cobertura", []):
        if c["ano"] in _cob_depois:      # rodada posterior reescreveu a cobertura deste ano (ex.: 2002 completa -> parcial na rodada 8)
            continue
        if {r[0] for r in q(con, "SELECT cobertura FROM ranking_empresa WHERE ano=?", c["ano"])} != {c["para"]}:
            ruins.append(f"cobertura {c['ano']} != {c['para']}")
    for x in rk.get("atualizar", []) + rk.get("inserir", []):
        a, e = x["ano"], x["entidade_id"]
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        campos = {k: v["para"] for k, v in x["campos"].items()} if "campos" in x else \
            {k: x[k] for k in ("lucro_brl_bi", "setor", "setor_k", "controle", "holding", "derivado", "obs")}
        for k, v in campos.items():
            if row[k] != v and (a, e, k) not in ov_campo:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v!r}")
        for f in x["fontes"]:
            l = lig(a, e, f["url"])
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)] and (a, e, normalizar_url(f["url"])) not in ov_url:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            if f.get("principal") and principal(a, e)[0] != normalizar_url(f["url"]) and (a, e) not in ov_princ:
                ruins.append(f"{a}/{e}: principal != {f['url']}")
        if x.get("anterior"):
            l = lig(a, e, x["anterior"]["url"])
            if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("trecho"), x["anterior"].get("nota"))] \
                    and (a, e, normalizar_url(x["anterior"]["url"])) not in ov_url:
                ruins.append(f"{a}/{e}: anterior {x['anterior']['url']} {[tuple(r) for r in l]}")
        if any(f.get("principal") for f in x["fontes"]) and _eh_wiki(principal(a, e)[1], principal(a, e)[0]):
            ruins.append(f"{a}/{e}: fonte principal é Wikipédia")
        if "campos" not in x:   # inserida: cobertura do ano e nome da época
            if x.get("nome_epoca") and not q(con, "SELECT 1 FROM nota WHERE pagina='brasil' AND tipo='aviso' AND chave=? AND texto=?", f"Y.{a}.empresa.{e}", x["nome_epoca"]):
                ruins.append(f"{a}/{e}: nome_epoca sem nota")
    for r in ruins[:20]:
        print("   -", r)
    esperar("ranking-empresa-correcoes.json == banco (campos, cobertura, fontes, principal, anterior, nome da época; divergências)", len(ruins), 0)
    esperar("ranking_evidencia: ligações == fontes + anteriores dos arquivos (rodadas 6, 7, 8, 9, 10 e 11; união ano/entidade/URL)", q(con, "SELECT count(*) FROM ranking_evidencia")[0][0], len(todas_lig))
    esperar("ranking: linha com fonte `sustenta` em ranking_evidencia e sem evidencia_id (fonte principal)",
            q(con, "SELECT count(*) FROM ranking_empresa k WHERE k.evidencia_id IS NULL AND EXISTS (SELECT 1 FROM ranking_evidencia x WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND x.papel='sustenta')")[0][0], 0)
    esperar("ranking: linhas sem fonte principal (evidencia_id NULL)", q(con, "SELECT count(*) FROM ranking_empresa WHERE evidencia_id IS NULL")[0][0], 0)
    s = exp["series.json"]
    n_exp = {(r["ano"], r["entidade_id"]): r for r in s["ranking_empresa"]}
    esperar("series.json: ranking_empresa == linhas do banco", len(n_exp), q(con, "SELECT count(*) FROM ranking_empresa")[0][0])
    esperar("series.json: linhas inseridas exportadas com a fonte principal",
            [f"{x['ano']}/{x['entidade_id']}" for x in rk.get("inserir", []) if (x["ano"], x["entidade_id"]) not in ov_princ and n_exp.get((x["ano"], x["entidade_id"]), {}).get("evidencia")
             != normalizar_url(next(f["url"] for f in x["fontes"] if f.get("principal")))], [])
    # ---- mandatos adicionais
    mo = _json_curadoria("mandato-oficial.json")
    sem_fonte = {(x["entidade_id"], x["cargo"], x["inicio"]) for x in mo.get("sem_fonte", [])}
    conf = {(x["entidade_id"], x["cargo"], x["inicio"]) for x in mo.get("confirmacoes", [])}
    ruins = []
    for m in ma.get("mandatos", []):
        k = (m["entidade_id"], m["cargo"], m["inicio"])
        row = q(con, "SELECT * FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=?", *k)
        if len(row) != 1:
            ruins.append(f"{k}: {len(row)} linhas")
            continue
        row = row[0]
        for c in ("orgao_id", "partido", "motivo"):
            if row[c] != m.get(c):
                ruins.append(f"{k}: {c} {row[c]!r} != {m.get(c)!r}")
        if m.get("uf") is not None and row["uf"] != m["uf"]:
            ruins.append(f"{k}: uf {row['uf']!r} != {m['uf']!r}")
        if row["fim"] != m["inicio"] or row["votos"] is not None:
            ruins.append(f"{k}: fim/votos")
        if (k in conf) == (k in sem_fonte):
            ruins.append(f"{k}: tem de estar em confirmacoes OU em sem_fonte de mandato-oficial.json")
        if (row["evidencia_id"] is not None) != (k in conf):
            ruins.append(f"{k}: evidencia_id só na linha confirmada pela API")
        l = q(con, """SELECT x.papel, x.qualidade, x.trecho_citado FROM relacao_evidencia x JOIN relacao r ON r.id=x.relacao_id JOIN evidencia v ON v.id=x.evidencia_id
                      WHERE r.origem='linha_do_tempo' AND r.origem_ref=? AND v.url=?""", f"mandato:{row['id']}", normalizar_url(m["fonte"]["url"]))
        if [tuple(r) for r in l] != [("sustenta", "boa", m["fonte"]["trecho"])]:
            ruins.append(f"{k}: fonte do destaque não ligada à relação mandato:{row['id']}")
        if row["evidencia_id"] is None and not q(con, """SELECT 1 FROM relacao_evidencia x JOIN relacao r ON r.id=x.relacao_id JOIN evidencia v ON v.id=x.evidencia_id
                      WHERE r.subtipo='filiacao' AND r.de=? AND v.url=? AND x.nota=?""", m["entidade_id"], normalizar_url(m["fonte"]["url"]), m.get("nota_partido")):
            ruins.append(f"{k}: linha sem API e filiação sem a fonte do destaque")
    for r in ruins[:20]:
        print("   -", r)
    esperar("mandatos-adicionais.json == banco (campos, fonte na relação, API x sem fonte oficial; divergências)", len(ruins), 0)
    print(f"  info: mandatos adicionais: {len(ma.get('mandatos', []))} ({sum(1 for m in ma.get('mandatos', []) if (m['entidade_id'], m['cargo'], m['inicio']) in conf)} confirmados pela API, "
          f"{sum(1 for m in ma.get('mandatos', []) if (m['entidade_id'], m['cargo'], m['inicio']) in sem_fonte)} sem fonte oficial de API); pendências: {len(ma.get('pendencias', []))}")
    # ---- eventos adicionais
    ruins = []
    ev_exp = {e["id"]: e for e in s["eventos"]}
    for e in ea.get("eventos", []):
        row = q(con, "SELECT * FROM evento WHERE id=?", e["id"])
        if not row:
            ruins.append(f"{e['id']}: ausente")
            continue
        row = row[0]
        if (row["titulo"], row["descricao"], row["peso"], row["canal"], row["origem"], row["origem_ref"], row["data"]) != \
                (e["titulo"], e["descricao"], e["peso"], "brasil", "manual", f"Y[{e['ano']}].{e['secao']}.eventos[{e['ordem']}]", str(e["ano"])):
            ruins.append(f"{e['id']}: campos diferem do arquivo")
        if row["natureza_id"] is None:
            ruins.append(f"{e['id']}: sem natureza")
        if not q(con, "SELECT 1 FROM evento_evidencia WHERE evento_id=? AND papel='sustenta'", e["id"]):
            ruins.append(f"{e['id']}: sem fonte `sustenta`")
        x = ev_exp.get(e["id"])
        if not x or (x["secao"], x["ordem"], x["ano"]) != (e["secao"], e["ordem"], e["ano"]):
            ruins.append(f"{e['id']}: series.json sem o fato ou com seção/ordem diferentes")
    esperar("eventos-adicionais.json == banco e series.json, com natureza e fonte `sustenta` (divergências)", ruins, [])
    # ---- correções de texto da rodada 6 e fontes da rodada 6
    ruins = []
    for c in [c for c in _json_curadoria("evento-correcoes.json").get("correcoes", []) if c.get("rodada") == 6]:
        v = q(con, f"SELECT {c['campo']} FROM evento WHERE id=?", c["evento_id"])[0][0]
        if c["para"] not in v or c["de"] in v:
            ruins.append(f"{c['evento_id']}.{c['campo']}")
    esperar("evento-correcoes.json (rodada 6): `para` no banco e `de` não", ruins, [])
    ent = r6.get("evidencias", [])
    esperar("evidencias-rodada6.json: toda entrada com \"rodada\": 6, qualidade boa e sem `substitui`",
            sum(1 for e in ent if e.get("rodada") == 6 and e.get("qualidade") == "boa" and not e.get("substitui")), len(ent))
    sem = [e["id"] for e in ea.get("eventos", []) if e["id"] not in {x["evento_id"] for x in ent if x["alvo_tipo"] == "evento"}]
    esperar("eventos-adicionais: todo fato novo tem fonte em evidencias-rodada6.json", sem, [])
    for nome, sec in (("relatorio-evidencias-adicionais.md", "## Rodada 6"), ("relatorio-migracao.md", "Rodada 6")):
        esperar(f"{nome} tem a seção da rodada 6", sec in (DATA / nome).read_text(encoding="utf-8"), True)


R12_MANDATOS = [   # (entidade, cargo, início, partido, UF, motivo exato, URL da fonte, trecho literal) das linhas novas da rodada 12 (mandatos-adicionais.json)
    ("elcio-alvares", "senador", "1996", "PFL", "ES", "Líder do governo FHC no Senado",
     "https://www25.senado.leg.br/web/atividade/pronunciamentos/-/p/pronunciamento/192650", "Sinto que é do meu dever, como Líder do Governo, não silenciar neste momento"),
    ("elcio-alvares", "senador", "1997", "PFL", "ES", "Líder do governo FHC no Senado",
     "https://www25.senado.leg.br/web/atividade/pronunciamentos/-/p/pronunciamento/215016", "que faz algumas críticas muito pesadas e fortes em relação à Liderança do Governo"),
    ("sandra-starling", "deputado", "1996", "PT", None, "Líder do PT na Câmara em 1996",
     "https://imagem.camara.leg.br/Imagem/d/pdf/DCD14FEV1996.pdf", "Deputada Sandra Starling, Líder do PT"),
    ("jose-anibal", "deputado", "1996", "PSDB", None, "Líder do PSDB na Câmara em 1996",
     "https://imagem.camara.leg.br/Imagem/d/pdf/DCD15FEV1996.pdf", "De acordo, Deputado José Anibal, Líder do PSDB."),
    ("pedrinho-abrao", "deputado", "1996", "PTB", None, "Líder do PTB na Câmara em 1996",
     "https://imagem.camara.leg.br/Imagem/d/pdf/DCD16FEV1996.pdf", "Deputado Pedrinho Abrão, Líder do PTB"),
    ("odelmo-leao", "deputado", "1996", "PPB", None, "Líder do PPB (Bloco PPB/PL) na Câmara em 1996",
     "https://imagem.camara.leg.br/Imagem/d/pdf/DCD16FEV1996.pdf", "escolheram o Deputado Odelmo Leão, para Líder do Bloco Parlamentar PPB/PL"),
    ("walter-pinheiro", "deputado", "2001", "PT", "BA", "Líder do PT na Câmara a partir de fev/2001 (Diário da Câmara de 21/2/2001)",
     "https://imagem.camara.leg.br/Imagem/d/pdf/DCD21FEV2001.pdf", "Votos de profícua gestão ao novo Líder do partido, Deputado Walter Pinheiro."),
]


def rodada12_mandatos(con):
    """Rodada 12 (parlamentares): líder do governo no Senado em 1996-1997 (Élcio Álvares), líderes de bancada na Câmara em 1996, Walter Pinheiro (PT, 2001),
    `motivo` de Temer em 1999 (mandato-correcoes.json com campo `motivo`) e lacunas registradas. Expectativas escritas aqui (não lidas do JSON), para o
    arquivo não validar a si mesmo; o confronto genérico linha-a-linha de mandatos-adicionais.json continua na rodada 6."""
    secao("Rodada 12 (mandatos: líder do governo no Senado, líderes de bancada, Temer 1999, lacunas)")
    mo = _json_curadoria("mandato-oficial.json")
    sem_fonte = {(x["entidade_id"], x["cargo"], x["inicio"]) for x in mo.get("sem_fonte", [])}
    conf = {(x["entidade_id"], x["cargo"], x["inicio"]) for x in mo.get("confirmacoes", [])}
    ruins = []
    for ent, cargo, ini, partido, uf, motivo, url, trecho in R12_MANDATOS:
        k = (ent, cargo, ini)
        row = q(con, "SELECT * FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=?", *k)
        if len(row) != 1:
            ruins.append(f"{k}: {len(row)} linhas")
            continue
        row = row[0]
        if (row["partido"], row["uf"], row["motivo"], row["fim"]) != (partido, uf, motivo, ini):
            ruins.append(f"{k}: partido/uf/motivo/fim {(row['partido'], row['uf'], row['motivo'], row['fim'])!r}")
        if k in conf or k not in sem_fonte or row["evidencia_id"] is not None:
            ruins.append(f"{k}: tem de estar só em sem_fonte de mandato-oficial.json, sem evidencia_id (pessoa nova fora da coleta das APIs)" if ent != "elcio-alvares" else f"{k}: Élcio tem de estar em sem_fonte")
        l = q(con, """SELECT x.papel, x.qualidade, x.trecho_citado, v.tipo, v.veiculo FROM relacao_evidencia x JOIN relacao r ON r.id=x.relacao_id JOIN evidencia v ON v.id=x.evidencia_id
                      WHERE r.origem='linha_do_tempo' AND r.origem_ref=? AND v.url=?""", f"mandato:{row['id']}", normalizar_url(url))
        if len(l) != 1 or (l[0][0], l[0][1], l[0][2], l[0][3]) != ("sustenta", "boa", trecho, "documento_oficial"):
            ruins.append(f"{k}: fonte/trecho na relação mandato:{row['id']}")
        if not re.match(r"https://(www25\.senado\.leg\.br|imagem\.camara\.leg\.br)/", url) or "wikipedia" in url:
            ruins.append(f"{k}: URL não oficial")
    for r in ruins[:20]:
        print("   -", r)
    esperar("rodada 12: 7 linhas novas (Élcio 1996/1997, líderes da Câmara 1996, Walter Pinheiro 2001) com campos, API x sem fonte e fonte oficial com trecho literal", len(ruins), 0)
    # Élcio: linha contínua 1995-1998 como líder do governo no Senado (1999: lacuna registrada abaixo)
    esperar("Élcio Álvares: líder do governo no Senado em 1995, 1996, 1997 e 1998",
            [r[0] for r in q(con, "SELECT inicio FROM mandato WHERE entidade_id='elcio-alvares' AND cargo='senador' AND motivo LIKE 'Líder do governo FHC no Senado%' ORDER BY inicio")],
            ["1995", "1996", "1997", "1998"])
    # líderes de bancada na Câmara em 1996: PMDB (Temer, de antes) + os quatro novos
    lid = {r[0]: r[1] for r in q(con, "SELECT partido, entidade_id FROM mandato WHERE cargo='deputado' AND inicio='1996' AND motivo LIKE 'Líder do P%'")}
    lid_pmdb = q(con, "SELECT entidade_id FROM mandato WHERE cargo='deputado' AND inicio='1996' AND motivo LIKE 'Líder do PMDB%'")
    esperar("líderes de bancada na Câmara em 1996 (PT, PSDB, PTB, PPB com linha nova)", {p: lid.get(p) for p in ("PT", "PSDB", "PTB", "PPB")},
            {"PT": "sandra-starling", "PSDB": "jose-anibal", "PTB": "pedrinho-abrao", "PPB": "odelmo-leao"})
    esperar("líder do PMDB na Câmara em 1996 (Michel Temer, linha de antes)", [r[0] for r in lid_pmdb], ["michel-temer"])
    # entidades novas
    esperar("rodada 12: entidades novas (pessoa, origem manual, UF só a de Walter Pinheiro)",
            [tuple(r) for r in q(con, "SELECT id, nome, tipo, origem, origem_ref, uf FROM entidade WHERE id IN ('sandra-starling','jose-anibal','pedrinho-abrao','odelmo-leao','walter-pinheiro') ORDER BY id")],
            [("jose-anibal", "José Aníbal", "pessoa", "manual", "curadoria:entidades-adicionais.json", None),
             ("odelmo-leao", "Odelmo Leão", "pessoa", "manual", "curadoria:entidades-adicionais.json", None),
             ("pedrinho-abrao", "Pedrinho Abrão", "pessoa", "manual", "curadoria:entidades-adicionais.json", None),
             ("sandra-starling", "Sandra Starling", "pessoa", "manual", "curadoria:entidades-adicionais.json", None),
             ("walter-pinheiro", "Walter Pinheiro", "pessoa", "manual", "curadoria:entidades-adicionais.json", "BA")])
    # Temer 1999: motivo corrigido pelo mecanismo novo (campo motivo em mandato-correcoes.json); as demais linhas dele intactas
    cor = [c for c in json.loads((CURADORIA / "mandato-correcoes.json").read_text(encoding="utf-8")) if c["campo"] == "motivo"]
    esperar("mandato-correcoes.json: correção de `motivo` de Temer 1999 (de/para exatos, fonte do Diário da Câmara de 3/2/1999)",
            [(c["entidade_id"], c["cargo"], c["inicio"], c["de"], c["para"], c["fonte_url"]) for c in cor],
            [("michel-temer", "deputado", "1999", "Presidente da Câmara dos Deputados, reeleito em 1/2/1999", "Presidente da Câmara dos Deputados, reeleito em 2/2/1999",
              "https://imagem.camara.leg.br/Imagem/d/pdf/DCD03FEV1999.pdf")])
    esperar("Temer deputado 1999: motivo == 'reeleito em 2/2/1999'",
            [r[0] for r in q(con, "SELECT motivo FROM mandato WHERE entidade_id='michel-temer' AND cargo='deputado' AND inicio='1999'")],
            ["Presidente da Câmara dos Deputados, reeleito em 2/2/1999"])
    esperar("Temer deputado 1999: relação do mandato herda a data certa na descrição (nada de 1/2/1999)",
            q(con, "SELECT count(*) FROM relacao WHERE origem='linha_do_tempo' AND subtipo='mandato:deputado' AND de='michel-temer' AND periodo_inicio='1999' AND descricao LIKE '%1/2/1999%'")[0][0], 0)
    esperar("Temer: demais linhas de deputado com motivo (1996-1998, 2000, 2001, 2009-2011) intactas",
            q(con, "SELECT count(*) FROM mandato WHERE entidade_id='michel-temer' AND cargo='deputado' AND motivo IS NOT NULL")[0][0], 9)
    # presidente/vice: 11 mandatos, nenhum com fonte oficial de página (lacuna registrada); se um dia ganharem fonte, ajustar este número
    pv = q(con, "SELECT entidade_id, cargo, inicio, evidencia_id FROM mandato WHERE cargo IN ('presidente','vice_presidente')")
    esperar("presidente/vice-presidente: 11 mandatos, todos em sem_fonte de mandato-oficial.json e sem evidencia_id (lacuna da rodada 12, URL em pendencias)",
            (len(pv), sum(1 for r in pv if (r[0], r[1], r[2]) in sem_fonte and r[3] is None)), (11, 11))
    # lacunas registradas, cada uma com a URL a abrir
    pend = _json_curadoria("mandatos-adicionais.json").get("pendencias", [])
    quer = ["Líder do governo no Senado (jan-ago/1999)", "Líder do PFL na Câmara (1996)", "Líderes de bancada no Senado em 1996 (PFL, PSDB, PT, PPB, PTB)",
            "Presidente e vice-presidente da República (11 mandatos sem fonte oficial de página)"]
    esperar("lacunas da rodada 12 em mandatos-adicionais.json/pendencias, cada uma com `url` https", [n for n in quer if not any(p["nome"] == n and str(p.get("url", "")).startswith("https://") for p in pend)], [])
    esperar("pendências resolvidas na rodada 12 (Walter Pinheiro, Élcio 1996-1997) saíram de pendencias", [p["nome"] for p in pend if p["nome"] in ("Walter Pinheiro", "Élcio Álvares")], [])


def rodada7(con, exp):
    """Rodada 7 (data/curadoria/ranking-empresa-correcoes-r7.json, aplicada depois da 6): 11 valores da Folha no ranking de lucros. Confere o arquivo
    contra o banco (campos, fonte principal, `anterior`, papéis, trechos), as contagens == arquivo, posições contíguas e na regra do raw nos anos
    1995-1997, pct_total, Telebrás em 1º lugar em 1996, Souza Cruz 1995 = 0,192, Telesp 1996 inserida com a holding no mesmo ano, e o export."""
    rk = _json_curadoria("ranking-empresa-correcoes-r7.json")
    if not rk:
        return
    secao("Rodada 7 (ranking-empresa-correcoes-r7.json: Folha, ranking de lucros 1995-1997)")
    ats, ins = rk.get("atualizar", []), rk.get("inserir", [])
    # 11 valores da pesquisa = 4 linhas inseridas + 7 atualizadas (Itaú 1995 e Souza Cruz 1996 só ganham obs/fonte; CSN 1996/1997 só fonte)
    esperar("r7: arquivo traz 4 linhas inseridas e 9 atualizações (7 com valor novo ou confirmado da pesquisa + 2 só de obs/fonte)", (len(ins), len(ats)), (4, 9))
    esperar("r7: valores da pesquisa cobertos == 11 (4 inseridas + 7 atualizadas; as 2 de só obs/fonte não são valores novos)",
            len(ins) + sum(1 for x in ats if not (set(x["campos"]) <= {"obs"} and "lucro_brl_bi" not in x["campos"] and x["fontes"][0]["papel"] == "contexto")), 11)
    ruins = []
    for x in ats + ins:
        a, e = x["ano"], x["entidade_id"]
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        campos = {k: v["para"] for k, v in x["campos"].items()} if "campos" in x else \
            {k: x[k] for k in ("lucro_brl_bi", "setor", "setor_k", "controle", "holding", "derivado", "obs")}
        for k, v in campos.items():
            if row[k] != v:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v!r}")
        for f in x["fontes"]:
            l = q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(f["url"]))
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)]:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            if f.get("principal"):
                pr = q(con, "SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
                if not pr or pr[0][0] != normalizar_url(f["url"]):
                    ruins.append(f"{a}/{e}: principal != {f['url']}")
        if x.get("anterior"):
            l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(x["anterior"]["url"]))
            if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("nota"))]:
                ruins.append(f"{a}/{e}: anterior {[tuple(r) for r in l]}")
    for r in ruins[:20]:
        print("   -", r)
    esperar("r7: arquivo == banco (campos, fonte principal, anterior, papel/trecho/nota de cada fonte; divergências)", len(ruins), 0)
    # posições contíguas e regra do raw nos anos tocados
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    ruins = []
    for a in sorted({x["ano"] for x in ats + ins}):
        rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=? ORDER BY posicao", a)
        if [r["posicao"] for r in rs] != list(range(1, len(rs) + 1)):
            ruins.append(f"{a}: posições não contíguas")
        luc = [r["lucro_brl_bi"] for r in rs]
        if luc != sorted([x for x in luc if x >= 0], reverse=True) + sorted(x for x in luc if x < 0):
            ruins.append(f"{a}: ordem dos lucros")
        ruins += [f"{a}/{r['entidade_id']}: pct_total" for r in rs if r["pct_total"] != round(r["lucro_brl_bi"] / pib[a] * 100, 3)]
    esperar("r7: anos 1995-1997 com posição contígua, lucros decrescentes e depois prejuízos, pct_total == lucro/PIB*100", ruins, [])
    esperar("r7: Telebrás é o 1º de 1996 (3,254)", [tuple(r) for r in q(con, "SELECT entidade_id, lucro_brl_bi FROM ranking_empresa WHERE ano=1996 AND posicao=1")], [("telebras", 3.254)])
    esperar("r7: Eletrobrás 2ª em 1996", [r[0] for r in q(con, "SELECT entidade_id FROM ranking_empresa WHERE ano=1996 AND posicao=2")], ["eletrobras"])
    esperar("r7: Souza Cruz 1995 = 0,192 (correção da rodada 6, que gravou 0,210), principal Folha de 3/2/1996",
            [tuple(r) for r in q(con, "SELECT k.lucro_brl_bi, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=1995 AND k.entidade_id='souza-cruz'")],
            [(0.192, "https://www1.folha.uol.com.br/fsp/1996/2/03/dinheiro/8.html")])
    esperar("r7: Souza Cruz 1995: a fonte de 1/2/1997 (0,210) ficou como contexto, sem ligação duplicada",
            [tuple(r) for r in q(con, """SELECT x.papel FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                                         WHERE x.ano=1995 AND x.entidade_id='souza-cruz' AND v.url=?""", normalizar_url("https://www1.folha.uol.com.br/fsp/dinheiro/fi010221.htm"))],
            [("contexto",)])
    esperar("r7: Itaú 1995 (0,374) e Souza Cruz 1996 (0,204) mantêm o valor e trazem o número divergente na obs",
            [tuple(r) for r in q(con, """SELECT entidade_id, lucro_brl_bi, obs LIKE '%403,5%' FROM ranking_empresa WHERE ano=1995 AND entidade_id='itau-unibanco'
                                         UNION ALL SELECT entidade_id, lucro_brl_bi, obs LIKE '%220 milh%' FROM ranking_empresa WHERE ano=1996 AND entidade_id='souza-cruz'""")],
            [("itau-unibanco", 0.374, 1), ("souza-cruz", 0.204, 1)])
    esperar("r7: Telesp 1996 inserida junto da holding Telebrás (o ranking já convive com holding e subsidiária: Telebrás/Embratel 1997, Itaúsa/Itaú 2010-2020)",
            [tuple(r) for r in q(con, "SELECT entidade_id, holding FROM ranking_empresa WHERE ano=1996 AND entidade_id IN ('telebras','telesp') ORDER BY entidade_id")],
            [("telebras", 1), ("telesp", 0)])
    esperar("r7: entidade `telesp` criada por entidades-adicionais.json (origem manual)",
            [tuple(r) for r in q(con, "SELECT origem, origem_ref FROM entidade WHERE id='telesp'")], [("manual", "curadoria:entidades-adicionais.json")])
    n_exp = {(r["ano"], r["entidade_id"]): r for r in exp["series.json"]["ranking_empresa"]}
    esperar("r7: series.json traz as linhas de 1995-1997 com lucro e posição do banco",
            [f"{a}/{e}" for a, e, l, p in q(con, "SELECT ano, entidade_id, lucro_brl_bi, posicao FROM ranking_empresa WHERE ano BETWEEN 1995 AND 1997")
             if (n_exp.get((a, e)) or {}).get("lucro_brl_bi") != l or (n_exp.get((a, e)) or {}).get("posicao") != p], [])
    esperar("relatorio-migracao.md tem a seção da rodada 7", "Rodada 7" in (DATA / "relatorio-migracao.md").read_text(encoding="utf-8"), True)


def rodada8(con, exp):
    """Rodada 8 (data/curadoria/ranking-empresa-correcoes-r8.json, aplicada depois da 7): ranking de lucros 1997-2009 com a Folha. Confere o
    arquivo contra o banco (campos, fonte principal, `anterior`, papel/trecho/nota de cada fonte, nome da época), as contagens == arquivo, as
    entidades novas, posições contíguas e na regra do raw e pct_total nos anos 1997-2009, a cobertura sem mudança, Petrobras 1997 presente, o
    corte do top 15 nas inseridas, nenhuma linha sem fonte principal (nem Wikipédia como principal nas linhas tocadas) e o export."""
    rk = _json_curadoria("ranking-empresa-correcoes-r8.json")
    if not rk:
        return
    secao("Rodada 8 (ranking-empresa-correcoes-r8.json: Folha, ranking de lucros 1997-2009)")
    ats, ins = rk.get("atualizar", []), rk.get("inserir", [])
    esperar("r8: arquivo traz 72 linhas inseridas e 34 atualizações", (len(ins), len(ats)), (72, 34))
    esperar("r8: atualizações com valor novo (lucro_brl_bi) == 17; só obs/fonte == 17",
            (sum(1 for x in ats if "lucro_brl_bi" in x["campos"]), sum(1 for x in ats if "lucro_brl_bi" not in x["campos"])), (17, 17))
    esperar("r8: `cobertura` só rebaixa 2002 de completa para parcial (a Folha não é ranking fechado: nenhum ano sobe de cobertura)", [(c["ano"], c["de"], c["para"]) for c in rk.get("cobertura", [])], [(2002, "completa", "parcial")])
    # A rodada 9 vem por cima da 8: ela não reescreve campo, fonte principal nem ligação de linha da 8 (a conferência abaixo continua integral);
    # nas linhas da 8 ela só acrescenta fontes de contexto com URL nova (TAM 2008, Oi 2009), conferidas na seção "Rodada 9".
    rk9 = _json_curadoria("ranking-empresa-correcoes-r9.json")
    chaves8 = {(x["ano"], x["entidade_id"]) for x in ats + ins}
    urls8 = {(x["ano"], x["entidade_id"], normalizar_url(f["url"])) for x in ats + ins for f in x["fontes"]} \
        | {(x["ano"], x["entidade_id"], normalizar_url(x["anterior"]["url"])) for x in ats if x.get("anterior")}
    esperar("r8: linhas da 8 em que a 9 muda campo ou fonte principal, ou religa uma URL da 8 (nenhuma)",
            sorted({(x["ano"], x["entidade_id"]) for x in rk9.get("atualizar", []) if (x["ano"], x["entidade_id"]) in chaves8
                    and (x["campos"] or any(f.get("principal") for f in x["fontes"]) or x.get("anterior")
                         or any((x["ano"], x["entidade_id"], normalizar_url(f["url"])) in urls8 for f in x["fontes"]))}), [])
    esperar("r8: linhas da 8 que a 9 só complementa com fonte de contexto",
            sorted((x["ano"], x["entidade_id"]) for x in rk9.get("atualizar", []) if (x["ano"], x["entidade_id"]) in chaves8), [(2008, "tam"), (2009, "telemar")])
    ruins = []
    for x in ats + ins:
        a, e = x["ano"], x["entidade_id"]
        if not 1997 <= a <= 2009:
            ruins.append(f"{a}/{e}: ano fora de 1997-2009")
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        campos = {k: v["para"] for k, v in x["campos"].items()} if "campos" in x else \
            {k: x[k] for k in ("lucro_brl_bi", "setor", "setor_k", "controle", "holding", "derivado", "obs")}
        for k, v in campos.items():
            if row[k] != v:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v!r}")
        for f in x["fontes"]:
            if (f["veiculo"], f["tipo"]) != ("Folha de S.Paulo", "reportagem") or not f.get("trecho") or not f.get("titulo") \
                    or not re.fullmatch(r"\d{4}-\d\d-\d\d", f.get("data") or "") or "folha.uol.com.br/fsp/" not in f["url"]:
                ruins.append(f"{a}/{e}: fonte {f['url']} sem veiculo/tipo/titulo/data/trecho da Folha")
            l = q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(f["url"]))
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)] and (a, e, normalizar_url(f["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            if f.get("principal"):
                pr = q(con, "SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
                if (not pr or pr[0][0] != normalizar_url(f["url"])) and (a, e) not in _ov_r11()[1]:
                    ruins.append(f"{a}/{e}: principal != {f['url']}")
        if x.get("anterior"):
            l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(x["anterior"]["url"]))
            if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("nota"))] and (a, e, normalizar_url(x["anterior"]["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: anterior {[tuple(r) for r in l]}")
        if "campos" not in x and x.get("nome_epoca") and \
                not q(con, "SELECT 1 FROM nota WHERE pagina='brasil' AND tipo='aviso' AND chave=? AND texto=?", f"Y.{a}.empresa.{e}", x["nome_epoca"]):
            ruins.append(f"{a}/{e}: nome_epoca sem nota")
        pr = q(con, "SELECT v.url, v.tipo FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
        if pr and _eh_wiki(pr[0]["tipo"], pr[0]["url"]):
            ruins.append(f"{a}/{e}: fonte principal é Wikipédia")
    for r in ruins[:20]:
        print("   -", r)
    esperar("r8: arquivo == banco (campos, fonte principal, anterior, papel/trecho/nota, nome da época, fonte da Folha completa; divergências)", len(ruins), 0)
    # entidades novas da rodada
    novas = [n for n in _json_curadoria("entidades-adicionais.json").get("entidades", []) if "ranking-empresa-correcoes-r8.json" in (n.get("motivo") or "")]
    esperar("r8: entidades novas em entidades-adicionais.json (origem manual) e todas usadas no ranking",
            sorted(n["id"] for n in novas if q(con, "SELECT 1 FROM entidade WHERE id=? AND origem='manual' AND origem_ref='curadoria:entidades-adicionais.json'", n["id"])
                   and q(con, "SELECT 1 FROM ranking_empresa WHERE entidade_id=?", n["id"])),
            sorted(["furnas", "eletropaulo", "cesp", "embraer", "klabin", "belgo-mineira", "aracruz", "tam"]))
    # regras do ranking nos anos da rodada (também conferidas em todas as linhas pela seção "Rodada 6")
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    ruins, corte = [], []
    for a in range(1997, 2010):
        rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=? ORDER BY posicao", a)
        if [r["posicao"] for r in rs] != list(range(1, len(rs) + 1)):
            ruins.append(f"{a}: posições não contíguas")
        luc = [r["lucro_brl_bi"] for r in rs]
        if luc != sorted([x for x in luc if x >= 0], reverse=True) + sorted(x for x in luc if x < 0):
            ruins.append(f"{a}: ordem dos lucros")
        ruins += [f"{a}/{r['entidade_id']}: pct_total" for r in rs if r["pct_total"] != round(r["lucro_brl_bi"] / pib[a] * 100, 3)]
        for i in [i for i in ins if i["ano"] == a]:
            r = next(r for r in rs if r["entidade_id"] == i["entidade_id"])
            if (i["lucro_brl_bi"] >= 0 and r["posicao"] > 15) or (i["lucro_brl_bi"] < 0 and i["lucro_brl_bi"] > -0.2):
                corte.append(f"{a}/{i['entidade_id']}: posição {r['posicao']}, lucro {i['lucro_brl_bi']}")
    esperar("r8: anos 1997-2009 com posição contígua, lucros decrescentes e depois prejuízos, pct_total == round(lucro/PIB*100, 3)", ruins, [])
    esperar("r8: toda inserida está no top 15 de lucros do ano ou é prejuízo de R$ 0,2 bi ou mais", corte, [])
    cob = {a: sorted(c for (c,) in q(con, "SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", a)) for a in range(1997, 2010)}
    esperar("r8: cobertura de 1997-2009 toda parcial (2002 rebaixada de completa para parcial na rodada 8)",
            cob, {a: ["parcial"] for a in range(1997, 2010)})
    esperar("r8: Petrobras 1997 presente (1,53; Folha de 13/2/1999)",
            [tuple(r) for r in q(con, "SELECT k.lucro_brl_bi, k.derivado, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=1997 AND k.entidade_id='petrobras'")],
            [(1.53, 0, "https://www1.folha.uol.com.br/fsp/dinheiro/fi13029916.htm")])
    esperar("r8: nenhuma linha do ranking sem fonte principal (evidencia_id NULL ou sem evidência)",
            q(con, "SELECT count(*) FROM ranking_empresa k LEFT JOIN evidencia v ON v.id=k.evidencia_id WHERE v.id IS NULL")[0][0], 0)
    usadas = {normalizar_url(f["url"]) for x in ats + ins for f in x["fontes"]}
    esperar("r8: registro (`nao_aplicados`, `fora_do_corte`, `confirmados`) só com URLs da Folha e motivo",
            [x.get("url") for k in ("nao_aplicados", "fora_do_corte", "confirmados") for x in rk.get(k, []) if "folha.uol.com.br/fsp/" not in (x.get("url") or "") or not x.get("motivo")], [])
    esperar("r8: `confirmados` não ligados (só registro)", sorted(normalizar_url(x["url"]) for x in rk.get("confirmados", []) if normalizar_url(x["url"]) in usadas), [])
    n_exp = {(r["ano"], r["entidade_id"]): r for r in exp["series.json"]["ranking_empresa"]}
    esperar("r8: series.json traz as linhas de 1997-2009 com lucro, posição, fonte principal e nome da época do banco",
            [f"{a}/{e}" for a, e, l, p, u in q(con, """SELECT k.ano, k.entidade_id, k.lucro_brl_bi, k.posicao, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                                     WHERE k.ano BETWEEN 1997 AND 2009""")
             if (n_exp.get((a, e)) or {}).get("lucro_brl_bi") != l or (n_exp.get((a, e)) or {}).get("posicao") != p or (n_exp.get((a, e)) or {}).get("evidencia") != u]
            + [f"{x['ano']}/{x['entidade_id']}: nome_epoca" for x in ins if x.get("nome_epoca") and (n_exp.get((x["ano"], x["entidade_id"])) or {}).get("nome_epoca") != x["nome_epoca"]], [])
    esperar("relatorio-migracao.md tem a seção da rodada 8", "Rodada 8" in (DATA / "relatorio-migracao.md").read_text(encoding="utf-8"), True)


def rodada9(con, exp):
    """Rodada 9 (data/curadoria/ranking-empresa-correcoes-r9.json, aplicada depois da 8): ranking de lucros 2009-2012 com a Folha. Confere o
    arquivo contra o banco (campos, fonte principal, `anterior`, papel/trecho/nota de cada fonte, nome da época, fonte da Folha completa), as
    contagens == arquivo, as entidades novas, posições contíguas e na regra do raw e pct_total em 2008-2012, o corte do top 15, a cobertura sem
    mudança, o 1º lugar de cada ano, Santander 2012 no lucro contábil, os valores da época mantidos onde o comparativo diverge, nenhuma linha sem
    fonte principal (nem Wikipédia como principal nas linhas tocadas), o registro (só Folha, 37 blocos) e o export."""
    rk = _json_curadoria("ranking-empresa-correcoes-r9.json")
    if not rk:
        return
    secao("Rodada 9 (ranking-empresa-correcoes-r9.json: Folha, ranking de lucros 2009-2012)")
    ats, ins = rk.get("atualizar", []), rk.get("inserir", [])
    esperar("r9: arquivo traz 18 linhas inseridas e 10 atualizações", (len(ins), len(ats)), (18, 10))
    esperar("r9: atualizações com valor novo (lucro_brl_bi) == 1 (Santander 2012); só obs/fonte == 9",
            (sum(1 for x in ats if "lucro_brl_bi" in x["campos"]), sum(1 for x in ats if "lucro_brl_bi" not in x["campos"])), (1, 9))
    esperar("r9: inseridas por ano (2009: 1; 2010: 5; 2011: 8; 2012: 4)",
            {a: sum(1 for x in ins if x["ano"] == a) for a in (2009, 2010, 2011, 2012)}, {2009: 1, 2010: 5, 2011: 8, 2012: 4})
    esperar("r9: `cobertura` vazia (a Folha não é ranking fechado: nenhum ano muda de cobertura)", rk.get("cobertura"), [])
    ruins = []
    for x in ats + ins:
        a, e = x["ano"], x["entidade_id"]
        if not (2009 <= a <= 2012 or ("campos" in x and a == 2008)):
            ruins.append(f"{a}/{e}: ano fora de 2009-2012 (2008 só em atualização)")
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        campos = {k: v["para"] for k, v in x["campos"].items()} if "campos" in x else \
            {k: x[k] for k in ("lucro_brl_bi", "setor", "setor_k", "controle", "holding", "derivado", "obs")}
        for k, v in campos.items():
            if row[k] != v:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v!r}")
        for f in x["fontes"]:
            if (f["veiculo"], f["tipo"]) != ("Folha de S.Paulo", "reportagem") or not f.get("trecho") or not f.get("titulo") \
                    or not re.fullmatch(r"\d{4}-\d\d-\d\d", f.get("data") or "") or "folha.uol.com.br/fsp/" not in f["url"]:
                ruins.append(f"{a}/{e}: fonte {f['url']} sem veiculo/tipo/titulo/data/trecho da Folha")
            if not (f.get("data") or "0") > f"{a}-12-31":
                ruins.append(f"{a}/{e}: fonte {f['url']} anterior ao fim do exercício")
            l = q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(f["url"]))
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)] and (a, e, normalizar_url(f["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            if f.get("principal"):
                pr = q(con, "SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
                if (not pr or pr[0][0] != normalizar_url(f["url"])) and (a, e) not in _ov_r11()[1]:
                    ruins.append(f"{a}/{e}: principal != {f['url']}")
        if x.get("anterior"):
            l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(x["anterior"]["url"]))
            if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("nota"))] and (a, e, normalizar_url(x["anterior"]["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: anterior {[tuple(r) for r in l]}")
        if "campos" not in x and x.get("nome_epoca") and \
                not q(con, "SELECT 1 FROM nota WHERE pagina='brasil' AND tipo='aviso' AND chave=? AND texto=?", f"Y.{a}.empresa.{e}", x["nome_epoca"]):
            ruins.append(f"{a}/{e}: nome_epoca sem nota")
        pr = q(con, "SELECT v.url, v.tipo FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
        if pr and _eh_wiki(pr[0]["tipo"], pr[0]["url"]):
            ruins.append(f"{a}/{e}: fonte principal é Wikipédia")
    for r in ruins[:20]:
        print("   -", r)
    esperar("r9: arquivo == banco (campos, fonte principal, anterior, papel/trecho/nota, nome da época, fonte da Folha completa e posterior ao exercício; divergências)", len(ruins), 0)
    esperar("r9: nomes de época na convenção da rodada 8 (Oi em `telemar`, Telesp em `telefonica-brasil` só em 2010)",
            sorted((x["ano"], x["entidade_id"], x["nome_epoca"]) for x in ins if x.get("nome_epoca")),
            [(2010, "telefonica-brasil", "Telesp"), (2010, "telemar", "Oi"), (2011, "telemar", "Oi")])
    esperar("r9: atualizações só de contexto mantêm o valor da época (TAM 2008 = -1,3; Oi 2009 = -0,436) e a fonte nova entra como `contexto`",
            [tuple(r) for r in q(con, """SELECT k.ano, k.entidade_id, k.lucro_brl_bi, x.papel FROM ranking_empresa k JOIN ranking_evidencia x ON x.ano=k.ano AND x.entidade_id=k.entidade_id
                                         JOIN evidencia v ON v.id=x.evidencia_id WHERE (k.ano, k.entidade_id) IN ((2008,'tam'),(2009,'telemar')) AND v.url LIKE '%folha.uol.com.br/fsp/%'
                                         AND v.url IN (?, ?) ORDER BY k.ano""", normalizar_url("https://www1.folha.uol.com.br/fsp/dinheiro/fi0104201020.htm"),
                                 normalizar_url("https://www1.folha.uol.com.br/fsp/mercado/me0503201111.htm"))],
            [(2008, "tam", -1.3, "contexto"), (2009, "telemar", -0.436, "contexto")])
    # entidades novas da rodada
    novas = [n for n in _json_curadoria("entidades-adicionais.json").get("entidades", []) if "ranking-empresa-correcoes-r9.json" in (n.get("motivo") or "")]
    esperar("r9: entidades novas em entidades-adicionais.json (origem manual) e todas usadas no ranking",
            sorted(n["id"] for n in novas if q(con, "SELECT 1 FROM entidade WHERE id=? AND origem='manual' AND origem_ref='curadoria:entidades-adicionais.json'", n["id"])
                   and q(con, "SELECT 1 FROM ranking_empresa WHERE entidade_id=?", n["id"])),
            sorted(["sabesp", "marfrig", "tim", "hsbc-brasil"]))
    # regras do ranking nos anos da rodada (também conferidas em todas as linhas pela seção "Rodada 6")
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    ruins, corte = [], []
    for a in range(2008, 2013):
        rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=? ORDER BY posicao", a)
        if [r["posicao"] for r in rs] != list(range(1, len(rs) + 1)):
            ruins.append(f"{a}: posições não contíguas")
        luc = [r["lucro_brl_bi"] for r in rs]
        if luc != sorted([x for x in luc if x >= 0], reverse=True) + sorted(x for x in luc if x < 0):
            ruins.append(f"{a}: ordem dos lucros")
        ruins += [f"{a}/{r['entidade_id']}: pct_total" for r in rs if r["pct_total"] != round(r["lucro_brl_bi"] / pib[a] * 100, 3)]
        for i in [i for i in ins if i["ano"] == a]:
            r = next(r for r in rs if r["entidade_id"] == i["entidade_id"])
            if (i["lucro_brl_bi"] >= 0 and r["posicao"] > 15) or (i["lucro_brl_bi"] < 0 and i["lucro_brl_bi"] > -0.2):
                corte.append(f"{a}/{i['entidade_id']}: posição {r['posicao']}, lucro {i['lucro_brl_bi']}")
    esperar("r9: anos 2008-2012 com posição contígua, lucros decrescentes e depois prejuízos, pct_total == round(lucro/PIB*100, 3)", ruins, [])
    esperar("r9: toda inserida está no top 15 de lucros do ano ou é prejuízo de R$ 0,2 bi ou mais", corte, [])
    esperar("r9: `fora_do_corte` de fato fora (lucro abaixo do 15º lucro do ano no banco, ou prejuízo menor que R$ 0,2 bi)",
            [f"{x['ano']}/{x['entidade']}" for x in rk.get("fora_do_corte", [])
             if (x["lucro_brl_bi"] >= 0 and x["lucro_brl_bi"] > (sorted((r[0] for r in q(con, "SELECT lucro_brl_bi FROM ranking_empresa WHERE ano=? AND lucro_brl_bi >= 0", x["ano"])), reverse=True)[14:15] or [-1])[0])
             or (x["lucro_brl_bi"] < 0 and x["lucro_brl_bi"] <= -0.2)], [])
    cob = {a: sorted(c for (c,) in q(con, "SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", a)) for a in range(2008, 2013)}
    esperar("r9: cobertura sem mudança (2008-2009 parcial; 2010-2012 completa, como antes da rodada)",
            cob, {2008: ["parcial"], 2009: ["parcial"], 2010: ["completa"], 2011: ["completa"], 2012: ["completa"]})
    esperar("r9: 1º lugar de cada ano sem mudança (Petrobras 2009, 2010 e 2012; Vale 2011)",
            [tuple(r) for r in q(con, "SELECT ano, entidade_id FROM ranking_empresa WHERE ano BETWEEN 2009 AND 2012 AND posicao=1 ORDER BY ano")],
            [(2009, "petrobras"), (2010, "petrobras"), (2011, "vale"), (2012, "petrobras")])
    esperar("r9: Santander 2012 no lucro contábil (2,69; Folha de 1/2/2013), com o 'LL gerencial' do DIEESE (6,329) como contexto",
            [tuple(r) for r in q(con, """SELECT k.lucro_brl_bi, k.derivado, v.url, (SELECT x.papel FROM ranking_evidencia x JOIN evidencia w ON w.id=x.evidencia_id
                                         WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND w.url LIKE '%desempenhoBancos2012.pdf') FROM ranking_empresa k
                                         JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=2012 AND k.entidade_id='santander-brasil'""")],
            [(2.69, 0, normalizar_url("https://www1.folha.uol.com.br/fsp/mercado/91652-lucro-do-santander-no-brasil-cai-24-em-2012-e-atinge-r-27-bi.shtml"), "contexto")])
    esperar("r9: nenhuma linha do ranking sem fonte principal (evidencia_id NULL ou sem evidência)",
            q(con, "SELECT count(*) FROM ranking_empresa k LEFT JOIN evidencia v ON v.id=k.evidencia_id WHERE v.id IS NULL")[0][0], 0)
    usadas = {normalizar_url(f["url"]) for x in ats + ins for f in x["fontes"]}
    reg = [x for k in ("nao_aplicados", "fora_do_corte", "confirmados") for x in rk.get(k, [])]
    esperar("r9: registro (`nao_aplicados`, `fora_do_corte`, `confirmados`) só com URLs da Folha e motivo",
            [x.get("url") for x in reg if "folha.uol.com.br/fsp/" not in (x.get("url") or "") or not x.get("motivo")], [])
    esperar("r9: `confirmados` não ligados (só registro)", sorted(normalizar_url(x["url"]) for x in rk.get("confirmados", []) if normalizar_url(x["url"]) in usadas), [])
    esperar("r9: os 37 blocos do material estão todos no arquivo (fontes ligadas + registro, URLs distintas)",
            len(usadas | {normalizar_url(x["url"]) for x in reg}), 37)
    n_exp = {(r["ano"], r["entidade_id"]): r for r in exp["series.json"]["ranking_empresa"]}
    esperar("r9: series.json traz as linhas de 2008-2012 com lucro, posição, fonte principal e nome da época do banco",
            [f"{a}/{e}" for a, e, l, p, u in q(con, """SELECT k.ano, k.entidade_id, k.lucro_brl_bi, k.posicao, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                                     WHERE k.ano BETWEEN 2008 AND 2012""")
             if (n_exp.get((a, e)) or {}).get("lucro_brl_bi") != l or (n_exp.get((a, e)) or {}).get("posicao") != p or (n_exp.get((a, e)) or {}).get("evidencia") != u]
            + [f"{x['ano']}/{x['entidade_id']}: nome_epoca" for x in ins if x.get("nome_epoca") and (n_exp.get((x["ano"], x["entidade_id"])) or {}).get("nome_epoca") != x["nome_epoca"]], [])
    esperar("relatorio-migracao.md tem a seção da rodada 9", "Rodada 9" in (DATA / "relatorio-migracao.md").read_text(encoding="utf-8"), True)


def rodada10(con, exp):
    """Rodada 10 (data/curadoria/ranking-empresa-correcoes-r10.json, aplicada depois da 9): lacunas do ranking de lucros fechadas com fontes primárias
    (SEC, sites das empresas). Confere o arquivo contra o banco (campos, fonte principal, `anterior`, papel/trecho/nota de cada fonte), as contagens
    exatas, nenhuma fonte da Folha ou da Wikipédia, tipo da fonte (SEC = documento_oficial; Caixa = relatorio), Santander 2009-2011 e 2022, Itaú e
    Bradesco 2011 e Caixa 2008 e 2012 sem mudança de valor e com principal primária, Gerdau 2009 inserida (15º) e a Eletrobras empurrada para o 16º,
    posições contíguas e pct_total em 2009, cobertura e 1º lugar sem mudança, o registro (`nao_aplicados`, `lacunas`) e o export."""
    rk = _json_curadoria("ranking-empresa-correcoes-r10.json")
    if not rk:
        return
    secao("Rodada 10 (ranking-empresa-correcoes-r10.json: fontes primárias, lacunas do ranking de lucros)")
    ats, ins = rk.get("atualizar", []), rk.get("inserir", [])
    esperar("r10: arquivo traz 1 linha inserida e 8 atualizações", (len(ins), len(ats)), (1, 8))
    esperar("r10: atualizações com valor novo (lucro_brl_bi) == 1 (Santander 2022, IFRS -> BR GAAP pela R7); só obs/fonte == 7",
            (sum(1 for x in ats if "lucro_brl_bi" in x["campos"]), sum(1 for x in ats if "lucro_brl_bi" not in x["campos"])), (1, 7))
    esperar("r10: `cobertura` vazia (nada sobe a completa)", rk.get("cobertura"), [])
    esperar("r10: linhas tocadas (ano, entidade)", sorted((x["ano"], x["entidade_id"]) for x in ats + ins),
            sorted([(2008, "caixa"), (2009, "gerdau"), (2009, "santander-brasil"), (2010, "santander-brasil"), (2011, "bradesco"),
                    (2011, "itau-unibanco"), (2011, "santander-brasil"), (2012, "caixa"), (2022, "santander-brasil")]))
    ruins = []
    for x in ats + ins:
        a, e = x["ano"], x["entidade_id"]
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        campos = {k: v["para"] for k, v in x["campos"].items()} if "campos" in x else \
            {k: x[k] for k in ("lucro_brl_bi", "setor", "setor_k", "controle", "holding", "derivado", "obs")}
        for k, v in campos.items():
            if row[k] != v and (a, e, k) not in _ov_r11()[0]:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v!r}")
        for f in x["fontes"]:
            esperado_tipo = "documento_oficial" if "sec.gov" in f["url"] else "relatorio"
            if f["tipo"] != esperado_tipo or not f.get("trecho") or not f.get("titulo") or not f.get("veiculo") \
                    or any(t in f["url"].lower() for t in ("folha.uol", "wikipedia.org")):
                ruins.append(f"{a}/{e}: fonte {f['url']} sem tipo/titulo/veiculo/trecho ou da Folha/Wikipédia")
            l = q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(f["url"]))
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)] and (a, e, normalizar_url(f["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            ev = q(con, "SELECT tipo FROM evidencia WHERE url=?", normalizar_url(f["url"]))
            if not ev or ev[0][0] != f["tipo"]:
                ruins.append(f"{a}/{e}: tipo da evidência {f['url']} != {f['tipo']}")
            if f.get("principal"):
                pr = q(con, "SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
                if (not pr or pr[0][0] != normalizar_url(f["url"])) and (a, e) not in _ov_r11()[1]:
                    ruins.append(f"{a}/{e}: principal != {f['url']}")
        if x.get("anterior"):
            l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(x["anterior"]["url"]))
            if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("nota"))] and (a, e, normalizar_url(x["anterior"]["url"])) not in _ov_r11()[2]:
                ruins.append(f"{a}/{e}: anterior {[tuple(r) for r in l]}")
        pr = q(con, "SELECT v.tipo, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
        if any(f.get("principal") for f in x["fontes"]) and \
                (not pr or pr[0]["tipo"] not in ("documento_oficial", "relatorio") or "dieese" in pr[0]["url"] or _eh_wiki(pr[0]["tipo"], pr[0]["url"])):
            ruins.append(f"{a}/{e}: principal não é documento oficial/relatório da empresa")
        for f in x["fontes"]:
            if "sec.gov" in f["url"] and not re.fullmatch(r"\d{4}-\d\d-\d\d", f.get("data") or ""):
                ruins.append(f"{a}/{e}: fonte {f['url']} sem data (Filing Date do índice EDGAR / data do documento)")
    for r in ruins[:20]:
        print("   -", r)
    esperar("r10: arquivo == banco (campos, fonte principal, anterior, papel/trecho/nota, tipo da evidência, nada da Folha/Wikipédia; divergências)", len(ruins), 0)
    # Santander 2009-2011: a r10 deixou 1,805 (derivado de US$), 7,383 e 7,756 (IFRS do 20-F de 2011); a r11 troca os três pelo BR GAAP (1,806; 3,863; 3,557). Aqui:
    # o que a r10 gravou (no arquivo: `de` da r11 == `para`/valor da r10) e o 2022 no banco; o resultado da r11 é conferido na seção "Rodada 11".
    _r11 = {(x["ano"], x["entidade_id"]): x for x in _json_curadoria("ranking-empresa-correcoes-r11.json").get("atualizar", [])}
    esperar("r10: Santander Brasil: 2009 = 1,805 (derivado de US$), 2010 = 7,383 e 2011 = 7,756 (IFRS do 20-F de 2011) como a r10 deixou (= `de` da r11 quando a r11 os troca); 2022 = 12,57 (BR GAAP, R7) no banco",
            ([(a, (_r11.get((a, "santander-brasil")) or {}).get("campos", {}).get("lucro_brl_bi", {}).get("de")) for a in (2010, 2011)],
             (_r11.get((2009, "santander-brasil")) or {}).get("campos", {}).get("lucro_brl_bi", {}).get("de"), (_r11.get((2009, "santander-brasil")) or {}).get("campos", {}).get("derivado", {}).get("de"),
             [tuple(r) for r in q(con, "SELECT ano, lucro_brl_bi, derivado FROM ranking_empresa WHERE entidade_id='santander-brasil' AND ano=2022")]),
            ([(2010, 7.383), (2011, 7.756)], 1.805, 1, [(2022, 12.57, 0)]))
    esperar("r10: Santander 2009: o IFRS do 20-F de 2009 (5,508) é só `contexto`; 2010-2011: 20-F de 2011 e DIEESE ligados (na r10 o 20-F era a principal e o DIEESE `contexto`; após a r11 a principal é o 6-K BR GAAP e o 20-F virou `contexto`)",
            [tuple(r) for r in q(con, """SELECT k.ano, v.url LIKE '%istoedinheiro%', v.url LIKE '%sec.gov/Archives/edgar/data/%1471055%',
                                         (SELECT group_concat(DISTINCT x.papel) FROM ranking_evidencia x JOIN evidencia w ON w.id=x.evidencia_id
                                          WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND (w.url LIKE '%dieese%' OR w.url LIKE '%sec.gov/Archives/edgar/data/%1471055%'))
                                         FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.entidade_id='santander-brasil' AND k.ano IN (2009, 2010, 2011) ORDER BY k.ano""")],
            [(2009, 0, 1, "contexto,sustenta"), (2010, 0, 1, "contexto,sustenta"), (2011, 0, 1, "contexto,sustenta")])
    esperar("r10: Santander 2010-2011 com a obs (no arquivo da r10) dizendo base IFRS (20-F 2011) e BR GAAP da época não localizado",
            [("IFRS (20-F 2011" in (o or "") or "Base IFRS (20-F 2011" in (o or "")) and "BR GAAP da época não localizado" in (o or "")
             for o in [x["campos"]["obs"]["para"] for x in sorted(ats, key=lambda x: x["ano"]) if x["entidade_id"] == "santander-brasil" and x["ano"] in (2010, 2011)]], [True, True])
    esperar("r10: Santander 2022: BR GAAP do 4T22 (12,57) principal e o IFRS do 20-F (14,287) `contexto`; posição 11 (era 10)",
            [tuple(r) for r in q(con, """SELECT k.lucro_brl_bi, k.posicao, v.url LIKE '%EDGAR_BRGAAP_4T22%', (SELECT x.papel FROM ranking_evidencia x JOIN evidencia w ON w.id=x.evidencia_id
                                         WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND w.url LIKE '%companyconcept%CIK0001471055%')
                                         FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=2022 AND k.entidade_id='santander-brasil'""")],
            [(12.57, 11, 1, "contexto")])
    esperar("r10: R7 registrada em regras-fontes.json (bancos em BR GAAP/COSIF; não financeiras em IFRS a partir de 2010) e no texto de regras de curadoria.py",
            ((_r6().get("R7") or {}).get("ranking_empresa_bancos"), (_r6().get("R7") or {}).get("ranking_empresa_nao_financeiras"), "R7  (ranking_empresa" in CUR.REGRAS_NATUREZA_TEXTO),
            ("BR GAAP/COSIF", "IFRS a partir de 2010", True))
    esperar("r10: Cielo 2015 com a principal (apresentação da própria Cielo) retipada para `relatorio` por evidencia-correcoes.json",
            [tuple(r) for r in q(con, "SELECT v.tipo FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=2015 AND k.entidade_id='cielo'")], [("relatorio",)])
    esperar("r10: Itaú 2011 (14,621), Bradesco 2011 (11,028), Caixa 2008 (3,9) e Caixa 2012 (6,066) mantêm o valor, com documento primário como principal e a fonte anterior como `sustenta`",
            [tuple(r) for r in q(con, """SELECT k.ano, k.entidade_id, k.lucro_brl_bi, v.tipo, (SELECT group_concat(DISTINCT x.papel) FROM ranking_evidencia x JOIN evidencia w ON w.id=x.evidencia_id
                                         WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND (w.url LIKE '%dieese%' OR w.url LIKE '%jornaldaparaiba%'))
                                         FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                         WHERE (k.ano, k.entidade_id) IN ((2011,'itau-unibanco'),(2011,'bradesco'),(2008,'caixa'),(2012,'caixa')) ORDER BY k.ano, k.entidade_id""")],
            [(2008, "caixa", 3.9, "relatorio", "sustenta"), (2011, "bradesco", 11.028, "documento_oficial", "sustenta"),
             (2011, "itau-unibanco", 14.621, "documento_oficial", "sustenta"), (2012, "caixa", 6.066, "relatorio", "sustenta")])
    esperar("r10: IFRS dos 20-F de Itaú e Bradesco 2011 ligado só como contexto",
            sorted(tuple(r) for r in q(con, """SELECT k.entidade_id, x.papel FROM ranking_empresa k JOIN ranking_evidencia x ON x.ano=k.ano AND x.entidade_id=k.entidade_id
                                               JOIN evidencia w ON w.id=x.evidencia_id WHERE k.ano=2011 AND k.entidade_id IN ('itau-unibanco','bradesco') AND w.url LIKE '%20f%'""")),
            [("bradesco", "contexto"), ("itau-unibanco", "contexto")])
    # 2009: Gerdau entra no top 15; Eletrobras (0,17) passa a 16º; posições contíguas e pct_total
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=2009 ORDER BY posicao")
    luc = [r["lucro_brl_bi"] for r in rs]
    esperar("r10: 2009 com posição contígua, lucros decrescentes e depois prejuízos, pct_total == round(lucro/PIB*100, 3)",
            ([r["posicao"] for r in rs] == list(range(1, len(rs) + 1)), luc == sorted([v for v in luc if v >= 0], reverse=True) + sorted(v for v in luc if v < 0),
             [r["entidade_id"] for r in rs if r["pct_total"] != round(r["lucro_brl_bi"] / pib[2009] * 100, 3)]), (True, True, []))
    esperar("r10: 2009: Gerdau 15º (1,122), Eletrobras 16º (0,17), Santander Brasil 12º (sem mudança de posição; o valor 1,805 virou 1,806 na r11)",
            sorted((r["entidade_id"], r["posicao"], r["lucro_brl_bi"]) for r in rs if r["entidade_id"] in ("gerdau", "eletrobras", "santander-brasil")),
            [("eletrobras", 16, 0.17), ("gerdau", 15, 1.122), ("santander-brasil", 12, 1.806)])
    esperar("r10: cobertura sem mudança nos anos tocados (2008, 2009 e 2022 parcial; 2010-2012 completa)",
            {a: sorted(c for (c,) in q(con, "SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", a)) for a in (2008, 2009, 2010, 2011, 2012, 2022)},
            {2008: ["parcial"], 2009: ["parcial"], 2010: ["completa"], 2011: ["completa"], 2012: ["completa"], 2022: ["parcial"]})
    esperar("r10: 1º lugar de 2022 sem mudança (Petrobras)",
            [tuple(r) for r in q(con, "SELECT ano, entidade_id FROM ranking_empresa WHERE ano=2022 AND posicao=1")], [(2022, "petrobras")])
    esperar("r10: 1º lugar sem mudança em 2008-2012 (Petrobras 2008, 2009, 2010 e 2012; Vale 2011)",
            [tuple(r) for r in q(con, "SELECT ano, entidade_id FROM ranking_empresa WHERE ano BETWEEN 2008 AND 2012 AND posicao=1 ORDER BY ano")],
            [(2008, "petrobras"), (2009, "petrobras"), (2010, "petrobras"), (2011, "vale"), (2012, "petrobras")])
    esperar("r10: nenhuma linha do ranking sem fonte principal (evidencia_id NULL ou sem evidência)",
            q(con, "SELECT count(*) FROM ranking_empresa k LEFT JOIN evidencia v ON v.id=k.evidencia_id WHERE v.id IS NULL")[0][0], 0)
    esperar("r10: registro: 5 `nao_aplicados` com URL, ano e motivo, `confirmados` vazio, e as lacunas registradas (>= 8)",
            (len([x for x in rk.get("nao_aplicados", []) if x.get("url") and x.get("motivo") and x.get("ano")]), rk.get("confirmados"), len(rk.get("lacunas", [])) >= 8),
            (5, [], True))
    esperar("r10: `nao_aplicados` não ligados (só registro)",
            sorted(normalizar_url(x["url"]) for x in rk.get("nao_aplicados", []) if q(con, "SELECT 1 FROM evidencia WHERE url=?", normalizar_url(x["url"]))), [])
    n_exp = {(r["ano"], r["entidade_id"]): r for r in exp["series.json"]["ranking_empresa"]}
    esperar("r10: series.json traz as linhas tocadas com lucro, posição e fonte principal do banco",
            [f"{a}/{e}" for a, e, l, p, u in q(con, """SELECT k.ano, k.entidade_id, k.lucro_brl_bi, k.posicao, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                                     WHERE k.ano=2009 OR (k.ano, k.entidade_id) IN ((2008,'caixa'),(2010,'santander-brasil'),(2011,'bradesco'),(2011,'itau-unibanco'),
                                                     (2011,'santander-brasil'),(2012,'caixa'),(2022,'santander-brasil'))""")
             if (n_exp.get((a, e)) or {}).get("lucro_brl_bi") != l or (n_exp.get((a, e)) or {}).get("posicao") != p or (n_exp.get((a, e)) or {}).get("evidencia") != u], [])
    esperar("relatorio-migracao.md tem a seção da rodada 10", "Rodada 10" in (DATA / "relatorio-migracao.md").read_text(encoding="utf-8"), True)


def rodada11(con, exp):
    """Rodada 11 (data/curadoria/ranking-empresa-correcoes-r11.json, aplicada depois da 10): Santander Brasil em BR GAAP (2009, 2010, 2011 e 2015; R7) e
    fontes primárias (6-K da SEC, relatório e site da própria empresa) para Itaú, Bradesco, Banco do Brasil e BNDES em 2013-2015. Confere o arquivo
    contra o banco (campos, fonte principal, `anterior`, `reclassificar`, papel/trecho/nota de cada fonte, tipo da evidência, data EDGAR), as contagens
    exatas, nenhuma fonte da Folha ou da Wikipédia nas fontes novas, valores e posições novos, o IFRS dos 20-F de banco só como `contexto` nas linhas
    tocadas, as matérias com valor da base antiga ou arredondado como `contexto`, as cinco maiores de 2013-2015 sem imprensa/DIEESE/Wikipédia como
    principal, posições contíguas e pct_total, cobertura e 1º lugar sem mudança, Itaúsa retipada, o registro (`nao_aplicados`, `lacunas`) e o export."""
    rk = _json_curadoria("ranking-empresa-correcoes-r11.json")
    if not rk:
        return
    secao("Rodada 11 (ranking-empresa-correcoes-r11.json: Santander em BR GAAP; 6-K de Itaú e Bradesco 2013-2015)")
    ats, ins = rk.get("atualizar", []), rk.get("inserir", [])
    esperar("r11: arquivo traz 0 linhas inseridas e 12 atualizações", (len(ins), len(ats)), (0, 12))
    esperar("r11: atualizações com valor novo (lucro_brl_bi) == 8 (Santander 2009, 2010, 2011 e 2015; Bradesco 2013-2015; Itaú 2015); só obs/fonte == 4",
            (sum(1 for x in ats if "lucro_brl_bi" in x["campos"]), sum(1 for x in ats if "lucro_brl_bi" not in x["campos"])), (8, 4))
    esperar("r11: `cobertura` vazia (nada sobe a completa) e 4 `reclassificar` (Folha 2010, Vermelho 2015, Infomoney e Gazeta 2015)",
            (rk.get("cobertura"), sorted((x["ano"], x["entidade_id"]) for x in ats for _ in x.get("reclassificar", []))),
            ([], [(2010, "santander-brasil"), (2015, "bradesco"), (2015, "itau-unibanco"), (2015, "santander-brasil")]))
    esperar("r11: linhas tocadas (ano, entidade)", sorted((x["ano"], x["entidade_id"]) for x in ats + ins),
            sorted([(2009, "santander-brasil"), (2010, "santander-brasil"), (2011, "santander-brasil"), (2015, "santander-brasil"),
                    (2013, "itau-unibanco"), (2014, "itau-unibanco"), (2015, "itau-unibanco"),
                    (2013, "bradesco"), (2014, "bradesco"), (2015, "bradesco"), (2014, "banco-do-brasil"), (2014, "bndes")]))
    ruins = []
    for x in ats + ins:
        a, e = x["ano"], x["entidade_id"]
        row = q(con, "SELECT * FROM ranking_empresa WHERE ano=? AND entidade_id=?", a, e)
        if not row:
            ruins.append(f"{a}/{e}: linha ausente")
            continue
        row = row[0]
        for k, v in x["campos"].items():
            if row[k] != v["para"]:
                ruins.append(f"{a}/{e}: {k} = {row[k]!r} != {v['para']!r}")
        for f in x["fontes"]:
            esperado_tipo = "documento_oficial" if "sec.gov" in f["url"] else "relatorio"
            if f["tipo"] != esperado_tipo or not f.get("trecho") or not f.get("titulo") or not f.get("veiculo") \
                    or any(t in f["url"].lower() for t in ("folha.uol", "wikipedia.org", "dieese", "exame.com", "gazetadopovo", "infomoney")):
                ruins.append(f"{a}/{e}: fonte {f['url']} sem tipo/titulo/veiculo/trecho ou de imprensa/DIEESE/Wikipédia")
            l = q(con, """SELECT x.papel, x.trecho_citado, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(f["url"]))
            if [tuple(r) for r in l] != [(f["papel"], f["trecho"], f.get("nota") or None)]:
                ruins.append(f"{a}/{e}: fonte {f['url']} {[tuple(r) for r in l]}")
            ev = q(con, "SELECT tipo FROM evidencia WHERE url=?", normalizar_url(f["url"]))
            if not ev or ev[0][0] != f["tipo"]:
                ruins.append(f"{a}/{e}: tipo da evidência {f['url']} != {f['tipo']}")
            if "sec.gov" in f["url"] and not re.fullmatch(r"\d{4}-\d\d-\d\d", f.get("data") or ""):
                ruins.append(f"{a}/{e}: fonte {f['url']} sem data (Filing Date do índice EDGAR)")
            if f.get("principal"):
                pr = q(con, "SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
                if not pr or pr[0][0] != normalizar_url(f["url"]):
                    ruins.append(f"{a}/{e}: principal != {f['url']}")
        if sum(1 for f in x["fontes"] if f.get("principal")) != 1:
            ruins.append(f"{a}/{e}: precisa de exatamente uma principal")
        l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                      WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(x["anterior"]["url"]))
        if [tuple(r) for r in l] != [(x["anterior"]["papel"], x["anterior"].get("nota"))]:
            ruins.append(f"{a}/{e}: anterior {[tuple(r) for r in l]}")
        for rc in x.get("reclassificar", []):
            l = q(con, """SELECT x.papel, x.nota FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                          WHERE x.ano=? AND x.entidade_id=? AND v.url=?""", a, e, normalizar_url(rc["url"]))
            if [tuple(r) for r in l] != [(rc["papel"], rc.get("nota"))]:
                ruins.append(f"{a}/{e}: reclassificar {rc['url']} {[tuple(r) for r in l]}")
        pr = q(con, "SELECT v.tipo, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)
        if not pr or pr[0]["tipo"] not in ("documento_oficial", "relatorio") or "dieese" in pr[0]["url"] or _eh_wiki(pr[0]["tipo"], pr[0]["url"]):
            ruins.append(f"{a}/{e}: principal não é documento oficial/relatório da empresa")
    for r in ruins[:20]:
        print("   -", r)
    esperar("r11: arquivo == banco (campos, fonte principal, anterior, reclassificar, papel/trecho/nota, tipo da evidência, data EDGAR, nada de imprensa/DIEESE/Wikipédia nas fontes novas; divergências)", len(ruins), 0)
    esperar("r11: Santander Brasil em BR GAAP: 2009 = 1,806 (direto em R$, derivado 0), 2010 = 3,863, 2011 = 3,557, 2012 = 2,69 (r9, mesma base), 2015 = 6,998, 2022 = 12,57",
            [tuple(r) for r in q(con, "SELECT ano, lucro_brl_bi, derivado FROM ranking_empresa WHERE entidade_id='santander-brasil' AND ano IN (2009, 2010, 2011, 2012, 2015, 2022) ORDER BY ano")],
            [(2009, 1.806, 0), (2010, 3.863, 0), (2011, 3.557, 0), (2012, 2.69, 0), (2015, 6.998, 0), (2022, 12.57, 0)])
    esperar("r11: Santander 2009, 2010, 2011 e 2015: principal = 6-K BR GAAP do 4T10, 4T10, 4T11 e 4T15 (documento_oficial) com data EDGAR",
            [tuple(r) for r in q(con, """SELECT k.ano, substr(v.url, instr(v.url, '/bsbr') + 1), v.tipo, v.data FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                         WHERE k.entidade_id='santander-brasil' AND k.ano IN (2009, 2010, 2011, 2015) ORDER BY k.ano""")],
            [(2009, "bsbrdfbrgaap4q10_6k.htm", "documento_oficial", "2011-02-03"), (2010, "bsbrdfbrgaap4q10_6k.htm", "documento_oficial", "2011-02-03"),
             (2011, "bsbrdfbrgaap4q11_6k.htm", "documento_oficial", "2012-01-31"), (2015, "bsbrdfbrgaap4q15_6k.htm", "documento_oficial", "2016-01-27")])
    esperar("r11: Santander: o IFRS do 20-F (2009, 2010, 2011), o gerencial do Relatório Anual 2015, a Istoé 2009, a Folha 2010 e o Vermelho 2015 ficam só como `contexto`",
            [tuple(r) for r in q(con, """SELECT k.ano, group_concat(DISTINCT x.papel) FROM ranking_empresa k JOIN ranking_evidencia x ON x.ano=k.ano AND x.entidade_id=k.entidade_id
                                         JOIN evidencia w ON w.id=x.evidencia_id
                                         WHERE k.entidade_id='santander-brasil' AND k.ano IN (2009, 2010, 2011, 2015)
                                           AND (w.url LIKE '%dp17792_20f%' OR w.url LIKE '%dp29493_20f%' OR w.url LIKE '%relat%anual+2015%' OR w.url LIKE '%istoedinheiro%'
                                                OR w.url LIKE '%me0402201115%' OR w.url LIKE '%vermelho.org.br%' OR w.url LIKE '%dieese%' OR w.url LIKE '%companyconcept%')
                                         GROUP BY k.ano ORDER BY k.ano""")],
            [(2009, "contexto"), (2010, "contexto"), (2011, "contexto"), (2015, "contexto")])
    esperar("r11: Bradesco 2013 = 12,011 (Book Net Income; o 12,202 do DIEESE é o Adjusted Net Income, `contexto`), 2014 = 15,089, 2015 = 17,19; Itaú 2013 = 15,696, 2014 = 20,242, 2015 = 23,36",
            [tuple(r) for r in q(con, """SELECT entidade_id, ano, lucro_brl_bi FROM ranking_empresa WHERE entidade_id IN ('bradesco','itau-unibanco') AND ano BETWEEN 2013 AND 2015
                                         ORDER BY entidade_id, ano""")],
            [("bradesco", 2013, 12.011), ("bradesco", 2014, 15.089), ("bradesco", 2015, 17.19), ("itau-unibanco", 2013, 15.696), ("itau-unibanco", 2014, 20.242), ("itau-unibanco", 2015, 23.36)])
    esperar("r11: Bradesco 2013: o 12,202 aparece na obs como Adjusted Net Income e o DIEESE (desempenhoBancos2014) é `contexto`",
            ("Adjusted Net Income" in q(con, "SELECT obs FROM ranking_empresa WHERE ano=2013 AND entidade_id='bradesco'")[0][0],
             [tuple(r) for r in q(con, """SELECT x.papel FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                                          WHERE x.ano=2013 AND x.entidade_id='bradesco' AND v.url LIKE '%desempenhoBancos2014%'""")]),
            (True, [("contexto",)]))
    esperar("r11: principal dos 6-K de Itaú e Bradesco 2013-2015 (documento_oficial da SEC, com data EDGAR) e Wikipédia/Exame/Gazeta/DIEESE fora da principal",
            [tuple(r) for r in q(con, """SELECT k.entidade_id, k.ano, v.tipo, v.data, v.url LIKE '%sec.gov%' FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                         WHERE k.entidade_id IN ('bradesco','itau-unibanco') AND k.ano BETWEEN 2013 AND 2015 ORDER BY k.entidade_id, k.ano""")],
            [("bradesco", 2013, "documento_oficial", "2014-02-07", 1), ("bradesco", 2014, "documento_oficial", "2015-02-06", 1), ("bradesco", 2015, "documento_oficial", "2016-02-05", 1),
             ("itau-unibanco", 2013, "documento_oficial", "2014-03-25", 1), ("itau-unibanco", 2014, "documento_oficial", "2015-02-06", 1), ("itau-unibanco", 2015, "documento_oficial", "2016-02-12", 1)])
    esperar("r11: Itaú 2013 com duas fontes `sustenta` (Manual das Assembleias de 2014 e MD&A do 4T14) e a Wikipédia só `contexto`",
            [tuple(r) for r in q(con, """SELECT x.papel, v.tipo FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.ano=2013 AND x.entidade_id='itau-unibanco'
                                         ORDER BY x.papel, v.tipo""")],
            [("contexto", "wiki"), ("sustenta", "documento_oficial"), ("sustenta", "documento_oficial")])
    esperar("r11: R7: nas linhas de banco tocadas, todo IFRS de 20-F/XBRL ligado é `contexto`",
            [tuple(r) for r in q(con, """SELECT x.ano, x.entidade_id, x.papel FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                                         WHERE (x.ano, x.entidade_id) IN ((2009,'santander-brasil'),(2010,'santander-brasil'),(2011,'santander-brasil'),(2015,'santander-brasil'),
                                                                          (2015,'itau-unibanco'),(2015,'bradesco'))
                                           AND (v.url LIKE '%20f%' OR v.url LIKE '%companyconcept%') AND x.papel != 'contexto'""")], [])
    esperar("r11: matérias com valor da base antiga ou 10 milhões abaixo do balanço viram `contexto` (Infomoney 2015 do Itaú, Gazeta 2015 do Bradesco)",
            [tuple(r) for r in q(con, """SELECT x.ano, x.entidade_id, x.papel FROM ranking_evidencia x JOIN evidencia v ON v.id=x.evidencia_id
                                         WHERE v.url IN ('https://www.infomoney.com.br/?p=377271',
                                                         'https://www.gazetadopovo.com.br/economia/lucro-do-bradesco-aumenta-139-em-2015-para-r-17180-bilhoes-5b78p565pguo8zygz9p3ebh0w')
                                         ORDER BY x.ano, x.entidade_id""")],
            [(2015, "bradesco", "contexto"), (2015, "itau-unibanco", "contexto")])
    esperar("r11: Banco do Brasil 2014 (11,246): Relatório Anual 2015 do BB como principal (relatorio) e Wikipédia `contexto`; BNDES 2014 (8,594): site do BNDES principal (relatorio) e Exame `sustenta`",
            [tuple(r) for r in q(con, """SELECT k.entidade_id, k.lucro_brl_bi, v.tipo, v.url LIKE '%0356392e%', v.url LIKE '%bndes.gov.br%',
                                         (SELECT group_concat(DISTINCT x.papel) FROM ranking_evidencia x JOIN evidencia w ON w.id=x.evidencia_id
                                          WHERE x.ano=k.ano AND x.entidade_id=k.entidade_id AND (w.url LIKE '%wikipedia%' OR w.url LIKE '%exame.com%'))
                                         FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                         WHERE k.ano=2014 AND k.entidade_id IN ('banco-do-brasil','bndes') ORDER BY k.entidade_id""")],
            [("banco-do-brasil", 11.246, "relatorio", 1, 0, "contexto"), ("bndes", 8.594, "relatorio", 0, 1, "sustenta")])
    esperar("r11: Itaúsa 2014 e 2015: Relatório Anual 2015 da Itaúsa retipado de `reportagem` para `relatorio` em evidencia-correcoes.json",
            ([tuple(r) for r in q(con, """SELECT k.ano, v.tipo FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.entidade_id='itausa' AND k.ano IN (2014, 2015) ORDER BY k.ano""")],
             sum(1 for c in _json_curadoria("evidencia-correcoes.json") if "afd9200b-9b01-4d1c-bdd9-9b2c1e9b3b4d/40c47fd1" in c["url"] and (c["campo"], c["de"], c["para"]) == ("tipo", "reportagem", "relatorio"))),
            ([(2014, "relatorio"), (2015, "relatorio")], 1))
    # as cinco maiores de 2013-2015: nenhuma com imprensa, DIEESE ou Wikipédia como principal
    esperar("r11: as cinco maiores de 2013, 2014 e 2015 têm documento oficial ou relatório da empresa como principal (nada de imprensa, DIEESE nem Wikipédia)",
            [tuple(r) for r in q(con, """SELECT k.ano, k.entidade_id, v.tipo FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                         WHERE k.ano BETWEEN 2013 AND 2015 AND k.posicao <= 5 AND (v.tipo NOT IN ('documento_oficial', 'relatorio') OR v.url LIKE '%dieese%'
                                               OR v.url LIKE '%desempenhoBancos%' OR v.url LIKE '%wikipedia%')""")], [])
    esperar("r11: posições que mudaram: 2010 (Itaúsa 9 -> 8, Santander 8 -> 9) e 2011 (Santander 8 -> 12; Caixa 10 -> 9, CSN 12 -> 11, Itaúsa 9 -> 8, Telefônica Brasil 11 -> 10)",
            [tuple(r) for r in q(con, """SELECT ano, entidade_id, posicao FROM ranking_empresa WHERE (ano=2010 AND entidade_id IN ('itausa','santander-brasil'))
                                         OR (ano=2011 AND entidade_id IN ('santander-brasil','caixa','csn','itausa','telefonica-brasil')) ORDER BY ano, entidade_id""")],
            [(2010, "itausa", 8), (2010, "santander-brasil", 9), (2011, "caixa", 9), (2011, "csn", 11), (2011, "itausa", 8), (2011, "santander-brasil", 12), (2011, "telefonica-brasil", 10)])
    esperar("r11: sem mudança de posição em 2009 (Santander 12º), 2013, 2014 e 2015 (Itaú, Bradesco, BB, Ambev, Itaúsa, Caixa, Santander, BNDES)",
            [tuple(r) for r in q(con, """SELECT ano, entidade_id, posicao FROM ranking_empresa WHERE (ano=2009 AND entidade_id='santander-brasil')
                                         OR (ano IN (2013, 2014, 2015) AND posicao <= 9 AND entidade_id IN ('petrobras','banco-do-brasil','itau-unibanco','bradesco','ambev','bndes','caixa','itausa','santander-brasil'))
                                         ORDER BY ano, posicao""")],
            [(2009, "santander-brasil", 12),
             (2013, "petrobras", 1), (2013, "banco-do-brasil", 2), (2013, "itau-unibanco", 3), (2013, "bradesco", 4), (2013, "ambev", 5), (2013, "bndes", 6), (2013, "caixa", 7), (2013, "itausa", 8), (2013, "santander-brasil", 9),
             (2014, "itau-unibanco", 1), (2014, "bradesco", 2), (2014, "ambev", 3), (2014, "banco-do-brasil", 4), (2014, "bndes", 5), (2014, "itausa", 6), (2014, "caixa", 7), (2014, "santander-brasil", 8),
             (2015, "itau-unibanco", 1), (2015, "bradesco", 2), (2015, "banco-do-brasil", 3), (2015, "ambev", 4), (2015, "itausa", 5), (2015, "caixa", 6), (2015, "santander-brasil", 7), (2015, "bndes", 8)])
    pib = {r[0]: r[1] for r in q(con, "SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    ruins = []
    for a in (2009, 2010, 2011, 2013, 2014, 2015):
        rs = q(con, "SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=? ORDER BY posicao", a)
        luc = [r["lucro_brl_bi"] for r in rs]
        if [r["posicao"] for r in rs] != list(range(1, len(rs) + 1)) or luc != sorted([v for v in luc if v >= 0], reverse=True) + sorted(v for v in luc if v < 0):
            ruins.append(f"{a}: posição/ordem")
        ruins += [f"{a}/{r['entidade_id']}: pct_total" for r in rs if r["pct_total"] != round(r["lucro_brl_bi"] / pib[a] * 100, 3)]
    esperar("r11: 2009, 2010, 2011 e 2013-2015 com posição contígua, lucros decrescentes e depois prejuízos, pct_total == round(lucro/PIB*100, 3)", ruins, [])
    esperar("r11: cobertura sem mudança (2009 parcial; 2010-2012 completa; 2013-2015 parcial)",
            {a: sorted(c for (c,) in q(con, "SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", a)) for a in (2009, 2010, 2011, 2012, 2013, 2014, 2015)},
            {2009: ["parcial"], 2010: ["completa"], 2011: ["completa"], 2012: ["completa"], 2013: ["parcial"], 2014: ["parcial"], 2015: ["parcial"]})
    esperar("r11: 1º lugar sem mudança (Petrobras em 2009, 2010 e 2013; Vale em 2011; Itaú Unibanco em 2014 e 2015)",
            [tuple(r) for r in q(con, "SELECT ano, entidade_id FROM ranking_empresa WHERE ano IN (2009, 2010, 2011, 2013, 2014, 2015) AND posicao=1 ORDER BY ano")],
            [(2009, "petrobras"), (2010, "petrobras"), (2011, "vale"), (2013, "petrobras"), (2014, "itau-unibanco"), (2015, "itau-unibanco")])
    esperar("r11: nenhuma linha do ranking sem fonte principal (evidencia_id NULL ou sem evidência)",
            q(con, "SELECT count(*) FROM ranking_empresa k LEFT JOIN evidencia v ON v.id=k.evidencia_id WHERE v.id IS NULL")[0][0], 0)
    esperar("r11: registro: 2 `nao_aplicados` com URL, ano e motivo, `confirmados` vazio, e as lacunas registradas (>= 8, com Usiminas 2009 e Santander 2013-2014)",
            (len([x for x in rk.get("nao_aplicados", []) if x.get("url") and x.get("motivo") and x.get("ano")]), rk.get("confirmados"), len(rk.get("lacunas", [])) >= 8,
             any("Usiminas 2009" in t for t in rk.get("lacunas", [])), any("Santander Brasil 2013" in t for t in rk.get("lacunas", []))),
            (2, [], True, True, True))
    esperar("r11: `nao_aplicados` não ligados (só registro)",
            sorted(normalizar_url(x["url"]) for x in rk.get("nao_aplicados", []) if q(con, "SELECT 1 FROM evidencia WHERE url=?", normalizar_url(x["url"]))), [])
    n_exp = {(r["ano"], r["entidade_id"]): r for r in exp["series.json"]["ranking_empresa"]}
    esperar("r11: series.json traz as linhas tocadas com lucro, posição e fonte principal do banco",
            [f"{x['ano']}/{x['entidade_id']}" for x in ats
             for (l, p, u) in [tuple(q(con, """SELECT k.lucro_brl_bi, k.posicao, v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id
                                              WHERE k.ano=? AND k.entidade_id=?""", x["ano"], x["entidade_id"])[0])]
             if (n_exp.get((x["ano"], x["entidade_id"])) or {}).get("lucro_brl_bi") != l or (n_exp.get((x["ano"], x["entidade_id"])) or {}).get("posicao") != p
             or (n_exp.get((x["ano"], x["entidade_id"])) or {}).get("evidencia") != u], [])
    esperar("relatorio-migracao.md tem a seção da rodada 11", "Rodada 11" in (DATA / "relatorio-migracao.md").read_text(encoding="utf-8"), True)


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
    secao("Evidências adicionais (data/curadoria/evidencias-adicionais.json + evidencias-rodada3.json + substituicoes-rodada4.json + evidencias-rodada5.json aplicadas)")
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
            if any(x.get("rodada") in (4, 5) for x in nova):   # rodadas 4 e 5: a substituta aponta exatamente para esta fraca
                nova = [x for x in nova if x.get("rodada") in (4, 5) and normalizar_url(x["substitui"]) == k[2]]
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
    # depois da rodada 5 (evidencias-rodada5.json): as fracas que sobravam foram substituídas, então o banco não tem nenhuma
    esperar("ligações 'fraca' no banco == len(FRACAS_DEPOIS_RODADA5) (zero depois da rodada 5; FRACAS_DEPOIS_R6 se a rodada 5 não está aplicada)",
            sum(nf.values()), len(FRACAS_DEPOIS_RODADA5) if _rodada5() else len(FRACAS_DEPOIS_R6) if _r6() else len(FRACAS_RESTANTES_RODADA4))
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
    for e in exp["origens.json"]["EV"]:
        listas.append((f"origens {e['id']}", "evento_evidencia", e["id"], e.get("fontes")))
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
    # a R6 só tirou a avaliação das 2 wiki fracas; depois da rodada 5 não resta nenhuma ligação `fraca` (FRACAS_REBAIXADAS_R6 + FRACAS_DEPOIS_RODADA5)
    fr_banco = _fracas_no_banco(con)
    esperar("R6: ligações 'fraca' no banco == FRACAS_DEPOIS_RODADA5 (zero) com a rodada 5 aplicada",
            fr_banco, FRACAS_DEPOIS_RODADA5 if _rodada5() else FRACAS_DEPOIS_R6)


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


def rodada13_valores(con, exp):
    """Rodada 13 (valores): contagens exatas de entidade_valor depois da rodada (60 valores em 45 entidades; 36 entidades novas além das 9 da rodada 2),
    conferidas no banco e em teia.json (N[].val)."""
    secao("Rodada 13 (valores: entidades com estimativa em R$, naturezas, qualidade)")
    esperar("entidade_valor: valores", q(con, "SELECT count(*) FROM entidade_valor")[0][0], 60)
    esperar("entidade_valor: entidades com valor", q(con, "SELECT count(DISTINCT entidade_id) FROM entidade_valor")[0][0], 45)
    esperar("entidade_valor: principais (um por entidade)", q(con, "SELECT count(*) FROM entidade_valor WHERE principal=1")[0][0], 45)
    esperar("entidade_valor: por natureza", {r[0]: r[1] for r in q(con, "SELECT natureza, count(*) FROM entidade_valor GROUP BY natureza")},
            {"bloqueado": 5, "desviado": 2, "investigado": 8, "movimentado": 15, "outro": 19, "passivo": 4, "prejuizo": 5, "sonegado": 2})
    esperar("entidade_valor: fracas / boas", (q(con, "SELECT count(*) FROM entidade_valor WHERE qualidade='fraca'")[0][0],
                                              q(con, "SELECT count(*) FROM entidade_valor WHERE qualidade='boa'")[0][0]), (34, 26))
    esperar("entidade_valor: entidades da teia com valor (nós com `val` em teia.json)", sum("val" in n for n in exp["teia.json"]["N"]), 45)
    esperar("entidade_valor: valor sem trecho citado", q(con, "SELECT count(*) FROM entidade_valor WHERE trecho_citado IS NULL OR trecho_citado=''")[0][0], 0)
    esperar("entidade_valor: tipos de entidade (nós da teia) com valor", {r[0]: r[1] for r in q(con, """SELECT e.tipo, count(DISTINCT v.entidade_id) FROM entidade_valor v
            JOIN entidade e ON e.id=v.entidade_id GROUP BY e.tipo""")},
            {"banco": 4, "empresa": 15, "fundo": 3, "fundo_previdencia": 2, "operacao_policial": 5, "organizacao_criminosa": 1, "orgao_publico": 12,
             "outro": 2, "pessoa": 1})


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
    rodada5(con)
    rodada6(con, exp)
    rodada12_mandatos(con)
    rodada7(con, exp)
    rodada8(con, exp)
    rodada9(con, exp)
    rodada10(con, exp)
    rodada11(con, exp)
    revisao_evidencias(con)
    evidencia_curadoria(con)
    valores(con, exp)
    rodada13_valores(con, exp)
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
