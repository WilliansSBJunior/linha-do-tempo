#!/usr/bin/env python3
"""Valida o banco: integridade, contagens, órfãos e round-trip contra data/raw. Sai com código 1 em qualquer falha.

Uso: python3 scripts/validar.py [--db caminho.sqlite]
Se data/*.json e data/dump.sql existirem, confere também que estão iguais ao que o banco exporta agora.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import exportar_json as ex
from comum import DATA, DUMP, RAW, SQLITE, conectar, gerar_dump, normalizar_url
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
    rel_origem = [("E[].r (teia)", "origem_ref LIKE 'E[%'"), ("fam_de", "origem_ref LIKE '%.fam_de'"), ("lig_de", "origem_ref LIKE '%.lig_de'")]
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
    h_fl = {r["natureza_id"]: r["c"] for r in q(con, "SELECT natureza_id, count(*) c FROM relacao WHERE origem_ref NOT LIKE 'E[%' GROUP BY natureza_id")}
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
    esperar("eventos teia ∪ origens (dedup por (d,t))", q(con, "SELECT count(*) FROM evento WHERE canal IN ('teia','banco','familia','ida','volta')")[0][0], len(chaves_t | chaves_o))
    esperar("eventos de origens (89) preservados com id", q(con, "SELECT count(*) FROM evento WHERE origem_ref LIKE '%origens:EV[%'")[0][0], len(orig["EV"]))
    esperar("eventos PREC", q(con, "SELECT count(*) FROM evento WHERE canal='precatorios'")[0][0], len(raw["PREC"]))
    ids_o = {e["id"] for e in orig["EV"]}
    esperar("ids de origens presentes", len({r[0] for r in q(con, "SELECT id FROM evento")} & ids_o), len(ids_o))
    # evidência: todas as URLs normalizadas de E+EV da teia existem e são exatamente as ligadas a relações/eventos da teia
    raw_urls = set()
    for e in raw["E"]:
        for r in e["r"]:
            raw_urls |= urls(r["f"])
    for e in raw["EV"]:
        raw_urls |= urls(e["f"])
    ligadas = {r[0] for r in q(con, """SELECT e.url FROM evidencia e JOIN relacao_evidencia x ON x.evidencia_id=e.id""")}
    ligadas |= {r[0] for r in q(con, """SELECT e.url FROM evidencia e JOIN evento_evidencia x ON x.evidencia_id=e.id JOIN evento v ON v.id=x.evento_id
                                         WHERE v.origem_ref LIKE '%teia:EV[%'""")}
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
                  AND NOT EXISTS (SELECT 1 FROM mandato s WHERE s.evidencia_id=e.id)""")[0][0]
    esperar("evidências sem nenhum uso", n, 0)
    n = q(con, "SELECT count(*) FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id) AND canal IN ('teia','banco','familia','ida','volta','precatorios','brb')")[0][0]
    esperar("eventos de fonte única (teia/origens/prec/brb) sem evidência", n, 0)
    n = q(con, "SELECT count(*) FROM relacao r WHERE r.origem_ref LIKE 'E[%' AND NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id)")[0][0]
    esperar("relações da teia sem evidência", n, 0)
    n = q(con, "SELECT count(*) FROM relacao WHERE de=para")[0][0]
    esperar("auto-laços", n, 0)
    sem_ref = q(con, """SELECT id, tipo FROM entidade e WHERE NOT EXISTS (SELECT 1 FROM relacao r WHERE r.de=e.id OR r.para=e.id)
                        AND NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM mandato m WHERE m.entidade_id=e.id OR m.orgao_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM bancada b WHERE b.partido_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM ranking_empresa b WHERE b.entidade_id=e.id)
                        AND NOT EXISTS (SELECT 1 FROM nota_entidade b WHERE b.entidade_id=e.id)""")
    print(f"  info: entidades sem nenhuma referência estrutural (aviso, não falha): {len(sem_ref)}"
          + (" -> " + ", ".join(f"{r['id']}({r['tipo']})" for r in sem_ref[:20]) if sem_ref else ""))
    nao_pais = [r["id"] for r in sem_ref if r["tipo"] != "pais"]
    esperar("entidades órfãs que não sejam país (séries de pares usam dimensao pais=ISO3)", len(nao_pais), 0)
    n_ev = q(con, "SELECT count(*) FROM entidade e WHERE origem='teia' AND NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.entidade_id=e.id)")[0][0]
    print(f"  info: nós da teia sem evento ligado: {n_ev} (inventário: 117 sem EV.n/SEM.n)")
    n = q(con, "SELECT count(*) FROM entidade_alias a WHERE NOT EXISTS (SELECT 1 FROM entidade e WHERE e.id=a.entidade_id)")[0][0]
    esperar("aliases sem entidade", n, 0)


def comparar_teia(exp, raw, idx_slug):
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
        if {a["a"], a["b"]} != {b["a"], b["b"]}:
            dif.append(f"E[{ei}] par difere")
    if len(raw["E"]) != len(exp["E"]):
        dif.append(f"E: {len(raw['E'])} != {len(exp['E'])}")
    # eventos
    if len(raw["EV"]) != len(exp["EV"]):
        dif.append(f"EV: {len(raw['EV'])} != {len(exp['EV'])}")
    for i, (a, b) in enumerate(zip(raw["EV"], exp["EV"])):
        for c in ("d", "y", "t", "x", "p", "n"):
            if a[c] != b[c]:
                dif.append(f"EV[{i}].{c}: {a[c]!r} != {b[c]!r}")
        if a.get("st") != b.get("st"):
            dif.append(f"EV[{i}].st: {a.get('st')!r} != {b.get('st')!r}")
        if b["ids"] != [idx_slug[k] for k in a["n"]]:
            dif.append(f"EV[{i}].ids")
        ua, ub = urls(a["f"]), urls(b["f"])
        fundido = not b["id"].startswith("ev-")
        if (fundido and not ua <= ub) or (not fundido and ua != ub):
            dif.append(f"EV[{i}].f difere ({'fundido' if fundido else 'só-teia'}): {ua ^ ub}")
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
    # PREC
    if len(raw["PREC"]) != len(exp["PREC"]):
        dif.append("PREC: tamanho")
    for i, (a, b) in enumerate(zip(raw["PREC"], exp["PREC"])):
        for c in ("d", "t", "x", "st"):
            if a[c] != b[c]:
                dif.append(f"PREC[{i}].{c}")
        if urls(a["f"]) != urls(b["f"]):
            dif.append(f"PREC[{i}].f")
    return dif


def comparar_origens(exp, raw):
    dif = []
    if len(raw["EV"]) != len(exp["EV"]):
        dif.append("EV tamanho")
    for i, (a, b) in enumerate(zip(raw["EV"], exp["EV"])):
        for c in ("id", "ch", "d", "y", "t", "x", "st", "r", "v"):
            if a[c] != b[c]:
                dif.append(f"origens EV[{i}].{c}: {a[c]!r} != {b[c]!r}")
        if urls(a["f"]) != urls(b["f"]):
            dif.append(f"origens EV[{i}].f: {urls(a['f']) ^ urls(b['f'])}")
    for c in ("NARR", "SINT", "SEM", "LAC"):
        if raw[c] != exp[c]:
            dif.append(f"origens {c} difere")
    return dif


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
    dif = comparar_teia(exp["teia.json"], raw, idx_slug)
    print(f"  relações comparadas pela chave (slug(r.a), slug(r.b), rot): {sum(len(e['r']) for e in raw['E'])}")
    print(f"  diferenças na teia: {len(dif)}")
    for d in dif[:30]:
        print("   -", d)
    if dif:
        falha(f"round-trip teia: {len(dif)} diferenças")
    dif_o = comparar_origens(exp["origens.json"], orig)
    print(f"  diferenças em origens: {len(dif_o)}")
    for d in dif_o[:30]:
        print("   -", d)
    if dif_o:
        falha(f"round-trip origens: {len(dif_o)} diferenças")
    mapa = exp["mapa_indices.json"]
    esperar("mapa_indices.N cobre todos os nós", len(mapa["N"]), len(raw["N"]))
    esperar("slugs únicos no mapa", len(set(mapa["N"].values())), len(raw["N"]))

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
