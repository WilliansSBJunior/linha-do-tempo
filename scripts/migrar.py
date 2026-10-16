#!/usr/bin/env python3
"""Migra data/raw/*.json para data/linha-do-tempo.sqlite (recria do zero), gera data/dump.sql e data/relatorio-migracao.md.

Idempotente e determinístico. Só stdlib. Uso: python3 scripts/migrar.py
"""
import collections
import json
import re
import sys

from comum import (DATA, RAW, SCRIPTS, SQLITE, DUMP, TS_MIGRACAO, conectar, dominio_de, gerar_dump,
                   normalizar_url, popular_fts, sha256)
from slug import (ALIASES_EXTRA, SLUG_FIXO, alias_norm, analisar_nome, slugify)

PSEUDO_PARTIDOS = {"Ex-ministros e consultores", "Órgãos e partidos"}
CANAL_ORIGENS = {"banco": "banco", "familia": "familia", "ida": "ida", "volta": "volta"}
R = collections.defaultdict(list)  # material do relatório


def J(nome):
    with open(RAW / nome, encoding="utf-8") as f:
        return json.load(f)


def verificar_hashes():
    esperado = {}
    for linha in (RAW / "hashes.txt").read_text().splitlines():
        h, n = linha.split()
        esperado[n] = h
    for n, h in esperado.items():
        if sha256(RAW / n) != h:
            sys.exit(f"hash divergente em data/raw/{n}: raw foi alterado")
    return esperado


# ---------------------------------------------------------------- datas
def parse_data(d):
    """-> (data ISO parcial, data_aprox, data_texto). data_texto só quando o original não é ISO."""
    if re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", d):
        return d, 0, None
    m = re.fullmatch(r"década de (\d{4})", d) or re.fullmatch(r"c\. (\d{4})", d)
    if m:
        return m.group(1), 1, d
    m = re.fullmatch(r"(\d{4}(?:-\d{2})?) a (\d{4}(?:-\d{2})?)", d)
    if m:
        return m.group(1), 0, d
    raise ValueError(f"data não reconhecida: {d!r}")


def slug_curto(titulo, limite=40):
    palavras = slugify(titulo, 200).split("-")
    out = ""
    for p in palavras:
        nova = f"{out}-{p}" if out else p
        if len(nova) > limite and out:
            break
        out = nova[:limite]
    return out.strip("-")


# ---------------------------------------------------------------- main
def main():
    hashes = verificar_hashes()
    teia, origens, dossie = J("dados-caso-master-v2.json"), J("origens.json"), J("dossie.json")
    pares, brasil, viol = J("pares.json"), J("brasil.json"), J("violencia.json")
    fusoes = json.loads((SCRIPTS / "fusoes.json").read_text(encoding="utf-8"))
    FUSAO = {f["de"]: f["para"] for f in fusoes}

    for p in (SQLITE, SQLITE.with_name(SQLITE.name + "-wal"), SQLITE.with_name(SQLITE.name + "-shm")):
        if p.exists():
            p.unlink()
    con = conectar(SQLITE)
    con.executescript((SCRIPTS / "schema.sql").read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = ON")
    nat_map = {r["codigo_externo"]: r["natureza_id"] for r in con.execute("SELECT * FROM natureza_mapa WHERE sistema='teia'")}

    antes = {
        "N": len(teia["N"]), "E (pares)": len(teia["E"]), "relações (E[].r)": sum(len(e["r"]) for e in teia["E"]),
        "EV teia": len(teia["EV"]), "PREC": len(teia["PREC"]), "EV origens": len(origens["EV"]),
        "SEM teia": len(teia["SEM"]), "SEM origens": len(origens["SEM"]),
        "LAC teia": len(teia["LAC"]), "LAC origens": sum(len(v) for v in origens["LAC"].values()),
        "NARR origens (parágrafos)": sum(len(v) for v in origens["NARR"].values()),
        "SINT teia/origens": f"{len(teia['SINT'])}/{len(origens['SINT'])}",
        "dossiê brb.eventos": len(dossie["brb"]["eventos"]),
        "timeline eventos pol+intl": sum(len(y["pol"]["eventos"]) + len(y["intl"]["eventos"]) for y in brasil["Y"].values()),
        "timeline empresas": sum(len(y["empresas"]) for y in brasil["Y"].values()),
        "timeline setores": sum(len(y["setores"]) for y in brasil["Y"].values()),
        "pares indicadores": len(pares["indicadores"]),
        "pares pontos não nulos": sum(1 for i in pares["indicadores"].values() for s in i["dados"].values() for v in s.values() if v is not None),
        "violência marcos": len(viol["MARCOS"]), "violência DATA": len(viol["DATA"]),
    }

    # ================================================================ ENTIDADES (em memória)
    ENTS, ALIAS, IDX_ALIAS = {}, collections.OrderedDict(), collections.defaultdict(set)

    def add_alias(slug, texto, tipo="alias", origem="teia"):
        n = alias_norm(texto or "")
        if not n or (n, slug) in ALIAS:
            return
        ALIAS[(n, slug)] = (texto, tipo, origem)
        IDX_ALIAS[n].add(slug)

    def slug_livre(base, nome):
        s = FUSAO.get(base, base)
        if s not in ENTS:
            return s
        i = 2
        while f"{s}-{i}" in ENTS:
            i += 1
        R["colisoes"].append((nome, s, f"{s}-{i}", ENTS[s]["nome"]))
        return f"{s}-{i}"

    def criar(slug, nome, tipo, origem, origem_ref, **kw):
        ENTS[slug] = dict(id=slug, nome=nome, tipo=tipo, categoria_id=None, grupo=None, partido=None, campo=None,
                          cargo=None, descricao=None, uf=None, origem=origem, origem_ref=origem_ref, ind_legado=None)
        ENTS[slug].update(kw)
        return slug

    mapa = {}  # índice antigo -> slug
    for i, n in enumerate(teia["N"]):
        base, als = analisar_nome(n["n"])
        slug = base
        if slug in FUSAO and FUSAO[slug] in ENTS:
            slug = FUSAO[slug]
            add_alias(slug, n["n"], "nome_antigo")
        else:
            slug = slug_livre(base, n["n"])
        p, sg = n.get("p"), n.get("sg")
        if p in PSEUDO_PARTIDOS:
            if sg:
                R["aviso"].append(f"N[{i}] {n['n']}: tem sg e pseudo-partido; usado sg")
            grupo, partido = sg or p, None
        else:
            grupo, partido = sg, p
        criar(slug, n["n"], n["t"], "teia", f"N[{i}]", categoria_id=n["c"], grupo=grupo, partido=partido,
              cargo=n["g"] or None, descricao=n["d"] or None, ind_legado=i)
        mapa[i] = slug
        if n["n"] != slug:
            add_alias(slug, n["n"], "alias")
        for a, t in als + ALIASES_EXTRA.get(slug, []):
            add_alias(slug, a, t)
    # nomes do mapa teia para checagem dos extras
    N_SLUGS = set(ENTS)

    def achar(nome, tipos, extra_slugs=()):
        """Procura entidade existente por slug exato ou alias único (só entre os tipos dados)."""
        cands = [slugify(nome)] + list(extra_slugs)
        for c in cands:
            if c in ENTS and ENTS[c]["tipo"] in tipos:
                return c
        s = IDX_ALIAS.get(alias_norm(nome), set())
        s = [x for x in s if ENTS[x]["tipo"] in tipos]
        if len(s) == 1:
            return s[0]
        return None

    def extra(nome, tipo, tipos_match, origem, ref, apelido=None, **kw):
        ex = [slugify(apelido)] if apelido else []
        achado = achar(nome, tipos_match, ex)
        if achado:
            if ENTS[achado]["nome"] != nome:
                add_alias(achado, nome, "nome_completo" if tipo == "pessoa" else "alias", origem)
            if apelido:
                add_alias(achado, apelido, "apelido", origem)
            R["fusao_auto"].append((nome, achado, ENTS[achado]["origem"]))
            return achado
        slug = slug_livre(slugify(nome), nome)
        criar(slug, nome, tipo, origem, ref, **kw)
        add_alias(slug, nome, "alias", origem)
        if apelido:
            add_alias(slug, apelido, "apelido", origem)
        return slug

    LT = "linha_do_tempo"
    PESSOA = ("pessoa",)

    # ---- timeline: órgãos, partidos (bancada), pessoas (pol), empresas (ranking)
    camara = extra("Câmara dos Deputados", "orgao_publico", ("orgao_publico",), LT, "Y.pol.presCamara")
    senado = extra("Senado Federal", "orgao_publico", ("orgao_publico",), LT, "Y.pol.presSenado")
    add_alias(camara, "Câmara", "apelido", LT)
    add_alias(senado, "Senado", "apelido", LT)

    PARTIDO_SLUG = {"PP1993": "pp-1993", "Outros": "outros-partidos", "FE Brasil (PT/PCdoB/PV)": "fe-brasil"}
    PARTIDO_NOME = {"PP1993": "PP (de 1993)", "Outros": "Outros partidos (bancada)",
                    "FE Brasil (PT/PCdoB/PV)": "Federação Brasil da Esperança (PT/PCdoB/PV)"}
    partido_slug, partido_campo, partido_nomes = {}, {}, collections.defaultdict(list)
    for ano in sorted(brasil["Y"]):
        pol = brasil["Y"][ano]["pol"]
        for casa in ("camara", "senado"):
            for r in pol[casa] or []:
                partido_nomes[r["k"]].append(r["nome"])
                if r.get("esp"):
                    partido_campo[r["k"]] = r["esp"]
    for k in partido_nomes:
        fixo = PARTIDO_SLUG.get(k) or SLUG_FIXO.get(alias_norm(k)) or slugify(k)
        if fixo in ENTS:
            partido_slug[k] = fixo
            continue
        nome = PARTIDO_NOME.get(k, k)
        tipo = "outro" if k == "Outros" else "partido"
        criar(fixo, nome, tipo, LT, f"Y.pol.camara[k={k}]", campo=partido_campo.get(k))
        add_alias(fixo, nome, "alias", LT)
        add_alias(fixo, k, "sigla", LT)
        for nm in dict.fromkeys(partido_nomes[k]):
            if nm != k:
                add_alias(fixo, nm, "nome_antigo", LT)
        partido_slug[k] = fixo
    for k, s in partido_slug.items():
        if ENTS[s]["tipo"] == "partido" and ENTS[s]["campo"] is None and partido_campo.get(k):
            ENTS[s]["campo"] = partido_campo[k]

    pessoas_pol = {}  # nome -> slug
    ANOS = sorted(brasil["Y"])

    def pessoa(nome, apelido=None):
        if nome not in pessoas_pol:
            pessoas_pol[nome] = extra(nome, "pessoa", PESSOA, LT, "Y.pol", apelido=apelido)
        elif apelido:
            add_alias(pessoas_pol[nome], apelido, "apelido", LT)
        return pessoas_pol[nome]

    # presidentes / vices / presidentes das casas / parlamentares em destaque (só cria as entidades aqui)
    for ano in ANOS:
        pol = brasil["Y"][ano]["pol"]
        m = re.fullmatch(r"(.+?) até (\d+/\d+); (.+?) a partir de então", pol["presidente"])
        if m:
            pessoa(m.group(1), "Dilma"); pessoa(m.group(3))
        else:
            pessoa(pol["presidente"], pol["pres"])
        if pol["vice"]:
            pessoa(re.sub(r"\s*\(.*\)$", "", pol["vice"]))
        for r in pol["presCamara"] + pol["presSenado"]:
            pessoa(r["nome"])
        for r in pol["parl"]:
            pessoa(r["nome"])

    # empresas do ranking
    emp_nomes = collections.OrderedDict()  # k -> lista de (ano, nome, setor)
    for ano in ANOS:
        for e in brasil["Y"][ano]["empresas"]:
            emp_nomes.setdefault(e["k"], []).append((ano, e["nome"], e["setor"]))
    emp_slug = {}
    NAO_PESSOA = ("empresa", "banco", "fundo", "outro", "orgao_publico", "fundo_previdencia")
    for k, lst in emp_nomes.items():
        ultimo = lst[-1][1]
        tipo = "banco" if lst[-1][2] == "Bancos" else "empresa"
        achado = None
        for _, nome, _s in reversed(lst):
            achado = achar(nome, NAO_PESSOA)
            if achado:
                break
        if achado:
            R["fusao_auto"].append((ultimo, achado, ENTS[achado]["origem"]))
            emp_slug[k] = achado
        else:
            emp_slug[k] = criar(slug_livre(slugify(ultimo), ultimo), ultimo, tipo, LT, f"Y.empresas[k={k}]")
            add_alias(emp_slug[k], ultimo, "alias", LT)
        for _, nome, _s in lst:
            if nome != ENTS[emp_slug[k]]["nome"]:
                add_alias(emp_slug[k], nome, "nome_antigo", LT)

    # países de pares
    pais_slug = {}
    for iso, nome in pares["paises"].items():
        s = extra(nome, "pais", ("pais",), LT, f"pares.paises.{iso}")
        add_alias(s, iso, "sigla", LT)
        pais_slug[iso] = s

    # ================================================================ INSERÇÃO: categoria, entidade, alias
    cats = [(c, n, i + 1) for i, (c, n) in enumerate(teia["cats"])] + [("hub", "Centro do caso", 0)]
    con.executemany("INSERT INTO categoria(id,nome,ordem) VALUES(?,?,?)", cats)
    for s in sorted(ENTS, key=lambda s: (ENTS[s]["ind_legado"] is None, ENTS[s]["ind_legado"] if ENTS[s]["ind_legado"] is not None else 0, s)):
        e = ENTS[s]
        con.execute("""INSERT INTO entidade(id,nome,tipo,categoria_id,grupo,partido,campo,cargo,descricao,uf,origem,origem_ref,ind_legado,criado_em,atualizado_em)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (e["id"], e["nome"], e["tipo"], e["categoria_id"], e["grupo"], e["partido"], e["campo"], e["cargo"],
                     e["descricao"], e["uf"], e["origem"], e["origem_ref"], e["ind_legado"], TS_MIGRACAO, TS_MIGRACAO))
    for (n, s), (texto, tipo, origem) in sorted(ALIAS.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        con.execute("INSERT INTO entidade_alias(alias,alias_norm,entidade_id,tipo_alias,origem) VALUES(?,?,?,?,?)",
                    (texto, n, s, tipo, origem))

    # ================================================================ EVIDÊNCIA
    EVID, VARIANTES = {}, collections.defaultdict(set)

    def tipo_evid(url, dom):
        h = dominio_de(url)
        if re.search(r"\.(gov|jus|leg|mp)\.br$", h) or h.endswith(".gov") or h in ("planalto.gov.br",):
            return "documento_oficial"
        if "wikipedia.org" in h:
            return "wiki"
        if url.lower().split("?")[0].endswith(".pdf"):
            return "relatorio"
        return "reportagem"

    def evid(url, veiculo=None, titulo=None, tipo=None):
        norm = normalizar_url(url)
        VARIANTES[norm].add(url)
        if norm not in EVID:
            cur = con.execute("INSERT INTO evidencia(url,veiculo,titulo,tipo,criado_em) VALUES(?,?,?,?,?)",
                              (norm, veiculo or dominio_de(norm), titulo, tipo or tipo_evid(norm, veiculo), TS_MIGRACAO))
            EVID[norm] = cur.lastrowid
        elif titulo:
            con.execute("UPDATE evidencia SET titulo=COALESCE(titulo,?) WHERE id=?", (titulo, EVID[norm]))
        return EVID[norm]

    dup_na_mesma = []

    def ligar(tabela, col, dono, fontes, rotulo):
        vistos = {}
        for ordem, par in enumerate(fontes):
            dom, url = par
            eid = evid(url, dom)
            if eid in vistos:
                dup_na_mesma.append((rotulo, url))
                continue
            vistos[eid] = ordem
            con.execute(f"INSERT INTO {tabela}({col},evidencia_id,ordem) VALUES(?,?,?)", (dono, eid, ordem))

    # ================================================================ RELAÇÕES (teia)
    rel_ids = {}
    sem_f = 0
    for ei, e in enumerate(teia["E"]):
        for ri, r in enumerate(e["r"]):
            de, para = mapa[r["a"]], mapa[r["b"]]
            cur = con.execute("""INSERT INTO relacao(de,para,tipo,rotulo,descricao,natureza_id,periodo_inicio,periodo_fim,valor_brl,resposta,origem,origem_ref,status,criado_em,atualizado_em)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (de, para, r["tipo"], r["rot"], r["desc"], nat_map[r["st"]],
                               None if r["de"] is None else str(r["de"]), None if r["ate"] is None else str(r["ate"]),
                               r["val"], r["resp"], "teia", f"E[{ei}].r[{ri}]", "publicada", TS_MIGRACAO, TS_MIGRACAO))
            rid = cur.lastrowid
            rel_ids[(ei, ri)] = rid
            if not r["f"]:
                sem_f += 1
            ligar("relacao_evidencia", "relacao_id", rid, r["f"], f"E[{ei}].r[{ri}]")
    for ei, e in enumerate(teia["E"]):
        con.execute("INSERT INTO aresta_legado(e_idx,a,b) VALUES(?,?,?)", (ei, mapa[e["a"]], mapa[e["b"]]))
    n_rel_teia = len(rel_ids)
    # fam_de / lig_de -> relações (natureza não classificada; NULL não é permitido em relacao)
    n_fam = n_lig = 0
    for i, n in enumerate(teia["N"]):
        if "fam_de" in n:
            con.execute("""INSERT INTO relacao(de,para,tipo,rotulo,descricao,natureza_id,direcional,origem,origem_ref,status,criado_em,atualizado_em)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (mapa[i], mapa[n["fam_de"]], "familiar", "Familiar ou próximo de",
                         "Vínculo de satélite registrado em N.fam_de (sem descrição na fonte original).",
                         "nao_classificada", 0, "teia", f"N[{i}].fam_de", "publicada", TS_MIGRACAO, TS_MIGRACAO))
            n_fam += 1
        if "lig_de" in n:
            con.execute("""INSERT INTO relacao(de,para,subtipo,tipo,rotulo,descricao,natureza_id,direcional,origem,origem_ref,status,criado_em,atualizado_em)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (mapa[i], mapa[n["lig_de"]], "escritorio_ligado", "profissional", "Escritório ligado a",
                         "Vínculo registrado em N.lig_de (sem descrição na fonte original).",
                         "nao_classificada", 0, "teia", f"N[{i}].lig_de", "publicada", TS_MIGRACAO, TS_MIGRACAO))
            n_lig += 1

    # ================================================================ EVENTOS
    EVENTO_IDS = set()
    sem_natureza = collections.defaultdict(list)

    def id_evento(data, titulo, titulo_ref):
        base = f"ev-{data}-{slug_curto(titulo)}"
        s, i = base, 2
        while s in EVENTO_IDS:
            s = f"{base}-{i}"
            i += 1
        if s != base:
            R["colisoes_evento"].append((titulo_ref, base, s))
        EVENTO_IDS.add(s)
        return s

    def inserir_evento(eid, titulo, descricao, d, natureza, peso, canal, origem, ref, contexto=None, resposta=None, valor=None):
        data, aprox, texto = parse_data(d)
        con.execute("""INSERT INTO evento(id,titulo,descricao,data,data_aprox,data_texto,natureza_id,peso,canal,contexto,resposta,valor_brl,origem,origem_ref,criado_em,atualizado_em)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (eid, titulo, descricao, data, aprox, texto, natureza, peso, canal, contexto, resposta, valor, origem, ref,
                     TS_MIGRACAO, TS_MIGRACAO))
        if natureza is None:
            sem_natureza[canal].append((eid, d, titulo, ref))
        return data

    o_por_chave = {(e["d"], e["t"]): (k, e) for k, e in enumerate(origens["EV"])}
    assert len(o_por_chave) == len(origens["EV"]) and len({(e["d"], e["t"]) for e in teia["EV"]}) == len(teia["EV"])
    EV_ID_TEIA = {}
    usados_origens = set()
    for i, ev in enumerate(teia["EV"]):
        chave = (ev["d"], ev["t"])
        nat = nat_map[ev["st"]] if "st" in ev else None
        if chave in o_por_chave:
            k, o = o_por_chave[chave]
            usados_origens.add(k)
            eid = o["id"]
            EVENTO_IDS.add(eid)
            assert o["x"] == ev["x"] and o.get("st") == ev.get("st"), f"divergência em {chave}"
            R["dedup_origens"].append((eid, i, ev["d"], ev["t"]))
            data = inserir_evento(eid, ev["t"], ev["x"], ev["d"], nat, ev["p"], CANAL_ORIGENS[o["ch"]], "origens",
                                  f"teia:EV[{i}]|origens:EV[{k}]", resposta=o["r"] or None, valor=o["v"])
            assert parse_data(ev["d"])[0][:4] == str(ev["y"]) == str(o["y"]), chave
            # f: ordem de origens; fontes só da teia vêm depois
            ordem_f = [tuple(p) for p in o["f"]]
            nor = {normalizar_url(u) for _, u in ordem_f}
            extra_t = [tuple(p) for p in ev["f"] if normalizar_url(p[1]) not in nor]
            if extra_t:
                R["f_so_na_teia"].append((eid, [u for _, u in extra_t]))
            prefixo_ok = [normalizar_url(u) for _, u in ordem_f][:len(ev["f"])] == [normalizar_url(u) for _, u in ev["f"]]
            if not prefixo_ok:
                R["f_ordem_diferente"].append(eid)
            fontes = ordem_f + extra_t
            R["f_extra_origens"].append(len(o["f"]) - len(ev["f"]))
        else:
            eid = id_evento(parse_data(ev["d"])[0], ev["t"], f"teia EV[{i}]")
            inserir_evento(eid, ev["t"], ev["x"], ev["d"], nat, ev["p"], "teia", "teia", f"teia:EV[{i}]")
            assert parse_data(ev["d"])[0][:4] == str(ev["y"]), ev
            fontes = ev["f"]
        EV_ID_TEIA[i] = eid
        for ordem, n in enumerate(ev["n"]):
            con.execute("INSERT INTO evento_entidade(evento_id,entidade_id,ordem) VALUES(?,?,?)", (eid, mapa[n], ordem))
        ligar("evento_evidencia", "evento_id", eid, fontes, f"EV[{i}]")
    n_so_origens = 0
    for k, o in enumerate(origens["EV"]):
        if k in usados_origens:
            continue
        n_so_origens += 1
        EVENTO_IDS.add(o["id"])
        inserir_evento(o["id"], o["t"], o["x"], o["d"], nat_map[o["st"]], None, CANAL_ORIGENS[o["ch"]], "origens",
                       f"origens:EV[{k}]", resposta=o["r"] or None, valor=o["v"])
        ligar("evento_evidencia", "evento_id", o["id"], o["f"], f"origens EV[{k}]")
    # PREC
    for i, p in enumerate(teia["PREC"]):
        eid = id_evento(parse_data(p["d"])[0], p["t"], f"PREC[{i}]")
        inserir_evento(eid, p["t"], p["x"], p["d"], nat_map[p["st"]] if p.get("st") else None, None, "precatorios", "prec", f"PREC[{i}]")
        ligar("evento_evidencia", "evento_id", eid, p["f"], f"PREC[{i}]")
    # dossiê: eventos BRB
    for i, p in enumerate(dossie["brb"]["eventos"]):
        eid = id_evento(parse_data(p["d"])[0], p["t"], f"dossie.brb[{i}]")
        ctx = f"lado: {p['lado']}" + ("; crítico" if p.get("critico") else "")
        inserir_evento(eid, p["t"], p["x"], p["d"], nat_map.get(p.get("st")), None, "brb", "dossie", f"dossie.brb.eventos[{i}]", contexto=ctx)
        ligar("evento_evidencia", "evento_id", eid, [(rot, url) for rot, url in p["src"]], f"dossie.brb[{i}]")
        # `rot` é o nome do veículo (não domínio): evid() só o usa na primeira vez que vê a URL

    # ================================================================ NOTAS
    def nota(pagina, tipo, chave, titulo, texto, ordem, natureza=None, ents=()):
        cur = con.execute("INSERT INTO nota(tipo,pagina,chave,titulo,texto,ordem,natureza_id) VALUES(?,?,?,?,?,?,?)",
                          (tipo, pagina, chave, titulo, texto, ordem, natureza))
        for o, s in enumerate(ents):
            con.execute("INSERT INTO nota_entidade(nota_id,entidade_id,ordem) VALUES(?,?,?)", (cur.lastrowid, s, o))
        return cur.lastrowid

    for o, (k, v) in enumerate(teia["SINT"].items()):
        nota("teia", "sintese", k, None, v, o)
    for o, s in enumerate(teia["SEM"]):
        nota("teia", "nao_sustentado", s["k"], s["l"], s["x"], o, ents=[mapa[n] for n in s["n"]])
    for o, t in enumerate(teia["LAC"]):
        nota("teia", "lacuna", None, None, t, o)
    for ano, v in teia["NUM"].items():
        if v.get("fontes_adicionais"):
            nota("teia", "aviso", f"NUM.{ano}.fontes_adicionais", None, "\n".join(v["fontes_adicionais"]), 0)
    for cap, paras in origens["NARR"].items():
        for o, t in enumerate(paras):
            nota("origens", "narrativa", cap, None, t, o)
    for o, (k, v) in enumerate(origens["SINT"].items()):
        nota("origens", "sintese", k, None, v, o)
    for o, s in enumerate(origens["SEM"]):
        nota("origens", "nao_sustentado", s["k"], s["l"], s["x"], o)
    for cap, lst in origens["LAC"].items():
        for o, t in enumerate(lst):
            nota("origens", "lacuna", cap, None, t, o)

    def titulo_de(row):
        for k in ("ator", "n", "arena", "t", "nome", "afirmacao"):
            if isinstance(row, dict) and isinstance(row.get(k), str):
                return row[k]
        return None

    def walk(prefixo, v, tipo):
        if isinstance(v, str):
            nota("dossie", tipo, prefixo, None, v, 0)
        elif isinstance(v, list):
            for o, x in enumerate(v):
                if isinstance(x, str):
                    nota("dossie", tipo, prefixo, None, x, o)
                elif isinstance(x, dict):
                    nat = nat_map.get(x.get("st")) if isinstance(x.get("st"), str) else None
                    if prefixo == "tese.placar":
                        nota("dossie", "placar", prefixo, f"{x['arena']}: {x['resultado']}", x["x"], o)
                    else:
                        nota("dossie", tipo, prefixo, titulo_de(x), json.dumps(x, ensure_ascii=False), o, natureza=nat)
                else:
                    nota("dossie", tipo, prefixo, str(x[0]) if x else None, " | ".join(str(y) for y in x), o)
        elif isinstance(v, dict):
            for k, x in v.items():
                sub = f"{prefixo}.{k}"
                if sub in ("brb.eventos", "meta.paginas", "meta.titulo", "meta.data_base"):
                    continue
                t = "aviso" if sub.startswith("meta.") else ("tese" if sub in ("tese.pergunta", "tese.resposta") else "narrativa")
                walk(sub, x, t)

    for sec, v in dossie.items():
        walk(sec, v, "narrativa")
    for k in ("titulo", "data_base"):
        con.execute("INSERT INTO meta(chave,valor) VALUES(?,?)", (f"dossie.{k}", dossie["meta"][k]))
    # pares.notas (descarta linhas de log de coleta), foruns (JSON)
    descartadas = []
    for grp, lst in pares["notas"].items():
        for o, t in enumerate(lst):
            if re.match(r"^\s*Cota:", t):
                descartadas.append(t)
                continue
            nota("pares", "aviso", f"notas.{grp}", None, t, o)
    for iso, f in pares["foruns"].items():
        nota("pares", "narrativa", f"foruns.{iso}", pares["paises"][iso], json.dumps(f, ensure_ascii=False), 0)
    R["pares_notas_descartadas"] = descartadas

    # ================================================================ INDICADORES / SÉRIES
    def ind(i, nome, unidade, dominio, descricao=None, fonte=None):
        con.execute("INSERT OR IGNORE INTO indicador(id,nome,unidade,dominio,descricao,fonte_padrao) VALUES(?,?,?,?,?,?)",
                    (i, nome, unidade, dominio, descricao, fonte))

    def ser(i, ano, valor, dim="", vt=None, q="oficial", ev=None, obs=None, ignorar=False, forcar=False):
        if valor is None and vt is None and not forcar:
            return  # ausência = sem dado (só teia.NUM guarda NULL explícito para preservar as chaves)
        verbo = "INSERT OR IGNORE" if ignorar else "INSERT"
        con.execute(f"{verbo} INTO serie(indicador_id,ano,dimensao,valor,valor_texto,qualidade,evidencia_id,obs) VALUES(?,?,?,?,?,?,?,?)",
                    (i, int(ano), dim, valor, vt, q, ev, obs))

    # -- teia.NUM
    NUMI = {"ativos_brl_bi": "Ativos", "patrimonio_liquido_brl_bi": "Patrimônio líquido", "captacao_brl_bi": "Captação", "lucro_brl_bi": "Lucro"}
    for k, nome in NUMI.items():
        ind(f"master.{k}", f"Banco Master: {nome}", "R$ bi", "master", "teia.NUM (balanços/notas técnicas; não usado na UI original)")
    for ano, v in sorted(teia["NUM"].items()):
        ev = evid(v["fonte"])
        q = "imprensa" if con.execute("SELECT tipo FROM evidencia WHERE id=?", (ev,)).fetchone()[0] == "reportagem" else "oficial"
        for k in NUMI:
            ser(f"master.{k}", ano, v[k], q=q, ev=ev, obs=v.get("obs"), forcar=True)

    # -- brasil: macro, setores, intl
    MACRO = {"pib": ("PIB nominal", "R$ bi"), "pibUsd": ("PIB em dólares", "US$ bi"), "cresc": ("Crescimento real do PIB", "%"),
             "ipca": ("IPCA", "%"), "selic": ("Selic", "% a.a."), "cambio": ("Câmbio médio", "R$/US$"),
             "desemp": ("Desemprego", "%"), "desempG": ("Grupo da pesquisa de desemprego (código interno)", "código")}
    for k, (nome, un) in MACRO.items():
        ind(f"macro.{k}", nome, un, "macro", "timeline Brasil, macro" + ("; valor_texto = selicTipo" if k == "selic" else "; valor_texto = desempPesq" if k == "desemp" else ""))
    setor_nomes = {s_["k"]: s_["nome"] for ano in ANOS for s_ in brasil["Y"][ano]["setores"]}
    ind("setor.va_pct", "Participação no valor adicionado", "% do valor adicionado", "setor",
        "Setores: " + "; ".join(f"{k}={v}" for k, v in setor_nomes.items()))
    for ano in ANOS:
        y = brasil["Y"][ano]
        for k, (nome, un) in MACRO.items():
            vt = y["macro"]["selicTipo"] if k == "selic" else y["macro"]["desempPesq"] if k == "desemp" else None
            ser(f"macro.{k}", ano, y["macro"].get(k), vt=vt)
        q = "proxy" if y["setoresProxy"] else "preliminar" if y["setoresPrelim"] else "oficial"
        for s in y["setores"]:
            ser("setor.va_pct", ano, s["v"], dim=f"setor={s['k']}", q=q)
    INTL = {"mundo": ("Crescimento do PIB mundial", "%"), "eua": ("Crescimento do PIB dos EUA", "%"), "china": ("Crescimento do PIB da China", "%"),
            "fed": ("Taxa do Fed", "% a.a."), "brent": ("Petróleo Brent", "US$/barril"), "minerio": ("Minério de ferro", "US$/t"),
            "soja": ("Soja", "US$/t"), "ranking": ("Posição do Brasil no ranking mundial do PIB", "posição"),
            "exp": ("Exportações", "US$ bi"), "imp": ("Importações", "US$ bi")}
    for k, (nome, un) in INTL.items():
        ind(f"intl.{k}", nome, un, "intl" if k not in ("exp", "imp") else "comercio", "timeline Brasil, intl" + ("; qualidade=proxy quando impAprox" if k == "imp" else ""))
    ind("comercio.destino_pct", "Destino das exportações (participação)", "%", "comercio", "top 5 por ano; dimensão pais=<nome>")
    ind("comercio.produto_pct", "Produto exportado (participação)", "%", "comercio", "top 5 por ano; dimensão produto=<nome>")
    for ano in ANOS:
        it = brasil["Y"][ano]["intl"]
        for k in INTL:
            ser(f"intl.{k}", ano, it.get(k), q="proxy" if (k == "imp" and it.get("impAprox")) else "oficial")
        for d in it["destinos"]:
            ser("comercio.destino_pct", ano, d["participacao_pct"], dim=f"pais={d['pais']}")
        for d in it["produtos"]:
            ser("comercio.produto_pct", ano, d["participacao_pct"], dim=f"produto={d['produto']}")

    # -- pares
    for k, i in pares["indicadores"].items():
        ev = evid(i["fonte"], tipo="dado_oficial", titulo=i["nome"])
        ind(f"pares.{k}", i["nome"], i["unidade"], "pares", f"grupo={i['grupo']}; fmt={i['fmt']}", i["fonte"])
        for iso, anos in i["dados"].items():
            for ano, v in anos.items():
                if v is not None:
                    ser(f"pares.{k}", ano, v, dim=f"pais={iso}", ev=ev)
    for m, nome in (("leitura", "PISA: leitura"), ("matematica", "PISA: matemática"), ("ciencias", "PISA: ciências")):
        ind(f"pares.pisa_{m}", nome, "pontos", "pares", pares["pisa"]["nome"], pares["pisa"]["fonte"])
    ind("pares.pisa_matematica_estado", "PISA: matemática por estado (Índia)", "pontos", "pares", pares["pisa"]["nome"], pares["pisa"]["fonte"])
    for iso, anos in pares["pisa"]["dados"].items():
        for ano, v in anos.items():
            for m in ("leitura", "matematica", "ciencias"):
                if v.get(m) is not None:
                    ser(f"pares.pisa_{m}", ano, v[m], dim=f"pais={iso}", obs=v.get("cobertura"))
            for est, val in (v.get("matematica_por_estado") or {}).items():
                ser("pares.pisa_matematica_estado", ano, val, dim=f"pais={iso};estado={est}", obs=v.get("cobertura"))

    # -- violência
    TIPOV = {"tabela": "relatorio", "imprensa": "reportagem", "sintese": "documento_oficial"}

    class Lazy(dict):  # registra a evidência só quando a fonte é usada (evita evidência órfã)
        def __init__(self, fonte, tipo):
            super().__init__()
            self.f, self.t = fonte, tipo

        def __missing__(self, k):
            v = self.f[k]
            self[k] = evid(v["url"], titulo=v["nome"], tipo=self.t(v))
            return self[k]

        def get(self, k, d=None):
            return self[k] if k in self.f else d

    SRC = Lazy(viol["SOURCES"], lambda v: "relatorio")
    CS = Lazy(viol["CSRC"], lambda v: TIPOV[v["tipo"]])
    ind("violencia.homicidios", "Homicídios no Brasil (contador)", "vítimas", "violencia",
        f"Mapa da Violência até {viol['SOURCE_BREAK_AFTER']}; Atlas da Violência depois (séries não estritamente comparáveis)")
    for d in viol["DATA"]:
        ser("violencia.homicidios", d["ano"], d["homicidios"], ev=SRC[d["fonte"]])
    gnome = {k: v["nome"] for k, v in viol["GROUPS"].items()}
    for c, cut in viol["CUTS"].items():
        grupos = sorted({g for e in cut["years"].values() for g, _ in e.get("segs", [])} | {g for e in cut["years"].values() for g in (e.get("rates") or {})} | {g for e in cut["years"].values() for g in (e.get("pct") or {})})
        desc = f"{cut['nome']}; grupos: " + "; ".join(f"{g}={gnome.get(g, g)}" for g in grupos) + (f"; quebra de série após {cut['breakAfter']}" if cut.get("breakAfter") else "")
        ind(f"violencia.{c}.total", f"Violência, {cut['nome']}: total usado como denominador", "vítimas", "violencia", desc)
        ind(f"violencia.{c}", f"Violência, {cut['nome']}: vítimas do grupo", "vítimas", "violencia", desc)
        ind(f"violencia.{c}.taxa", f"Violência, {cut['nome']}: taxa", "por 100 mil", "violencia", desc)
        ind(f"violencia.{c}.pct", f"Violência, {cut['nome']}: percentual publicado sem número absoluto", "fração (0 a 1)", "violencia", desc)
        ind(f"violencia.{c}.pct_publicado", f"Violência, {cut['nome']}: percentual publicado", "%", "violencia", desc)
        for ano, e in sorted(cut["years"].items(), key=lambda kv: int(kv[0])):
            ev = CS.get(e.get("src"))
            obs = " ".join(x for x in (e.get("note"), e.get("rateNote")) if x) or None
            ser(f"violencia.{c}.total", ano, e["tot"], ev=ev, obs=e.get("totNote"))
            for g, n in e.get("segs", []):
                ser(f"violencia.{c}", ano, n, dim=f"grupo={g}", ev=ev, obs=obs)
            for g, v in (e.get("rates") or {}).items():
                ser(f"violencia.{c}.taxa", ano, v, dim=f"grupo={g}", ev=ev, obs=obs)
            for g, v in (e.get("pct") or {}).items():
                ser(f"violencia.{c}.pct", ano, v, dim=f"grupo={g}", ev=ev, obs=obs)
            if e.get("pub") is not None:
                ser(f"violencia.{c}.pct_publicado", ano, e["pub"], dim=f"grupo={e['segs'][0][0]}", ev=ev)
    for ano, (neg, nneg) in viol["RACE_RATES"].items():
        ser("violencia.raca.taxa", ano, neg, dim="grupo=negros", ignorar=True, obs="RACE_RATES")
        ser("violencia.raca.taxa", ano, nneg, dim="grupo=naoNegros", ignorar=True, obs="RACE_RATES")
    # marcos legais -> eventos
    for i, m in enumerate(viol["MARCOS"]):
        eid = id_evento(m["data"], m["curto"], f"MARCOS[{i}]")
        inserir_evento(eid, m["titulo"], m["texto"], m["data"], None, None, "violencia", "violencia", f"MARCOS[{i}]")
        ligar("evento_evidencia", "evento_id", eid, [(None, m["url"])], f"MARCOS[{i}]")

    # ================================================================ RANKING, MANDATO, BANCADA
    for ano in ANOS:
        y = brasil["Y"][ano]
        for pos, e in enumerate(y["empresas"], 1):
            con.execute("""INSERT INTO ranking_empresa(ano,entidade_id,posicao,setor,setor_k,lucro_brl_bi,pct_total,controle,holding,derivado,cobertura,obs,evidencia_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (int(ano), emp_slug[e["k"]], pos, e["setor"], e["sk"], e["lucro"], e["pct"], e["controle"],
                         int(e["holding"]), int(e["derivado"]), y["cobertura"], e["obs"] or None, evid(e["fonte"]) if e["fonte"] else None))
        for casa, chave in (("camara", "camara"), ("senado", "senado")):
            for r in y["pol"][chave] or []:
                con.execute("INSERT INTO bancada(legislatura,ano,casa,partido_id,nome_epoca,cadeiras,campo) VALUES(?,?,?,?,?,?,?)",
                            (int(y["pol"]["leg"]), int(ano), casa, partido_slug[r["k"]], r["nome"], r["n"], r.get("esp")))

    def runs(itens):
        """itens: lista de (ano, chave, dados). Junta anos consecutivos da mesma chave -> [(chave, ano_ini, ano_fim, dados_do_primeiro)]"""
        out = []
        for ano, chave, dados in itens:
            if out and out[-1][0] == chave and out[-1][2] == int(ano) - 1:
                out[-1][2] = int(ano)
            else:
                out.append([chave, int(ano), int(ano), dados])
        return out

    def mandato(slug, cargo, ini, fim, partido, uf=None, orgao=None, motivo=None, votos=None):
        con.execute("INSERT INTO mandato(entidade_id,cargo,orgao_id,partido,uf,inicio,fim,motivo,votos) VALUES(?,?,?,?,?,?,?,?,?)",
                    (slug, cargo, orgao, partido or None, uf, ini, fim, motivo, votos))

    pres, vices = [], []
    over = {}
    for ano in ANOS:
        pol = brasil["Y"][ano]["pol"]
        m = re.fullmatch(r"(.+?) até (\d+)/(\d+); (.+?) a partir de então", pol["presidente"])
        if m:
            fim_d = f"{ano}-{int(m.group(3)):02d}-{int(m.group(2)):02d}"
            pres.append((ano, m.group(1), {"partido": "PT"}))
            over[(m.group(1), "fim")] = fim_d
            pres.append((ano, m.group(4), {"partido": "PMDB"}))
            over[(m.group(4), "ini")] = fim_d
        else:
            pres.append((ano, pol["presidente"], {"partido": pol["partido"]}))
        if pol["vice"]:
            mv = re.fullmatch(r"(.+?)\s*\((.*)\)", pol["vice"])
            vices.append((ano, mv.group(1) if mv else pol["vice"], {"partido": mv.group(2) if mv else None}))
    for nome, a, b, d in runs(pres):
        mandato(pessoas_pol[nome], "presidente", over.get((nome, "ini"), str(a)), over.get((nome, "fim"), str(b)), d["partido"])
    for nome, a, b, d in runs(vices):
        mandato(pessoas_pol[nome], "vice_presidente", str(a), str(b), d["partido"])
    for chave, cargo, orgao in (("presCamara", "presidente_camara", camara), ("presSenado", "presidente_senado", senado)):
        itens = [(ano, r["nome"], r) for ano in ANOS for r in brasil["Y"][ano]["pol"][chave]]
        # runs exige ordem por pessoa: agrupa por nome preservando ordem cronológica
        por_nome = collections.OrderedDict()
        for ano, nome, r in itens:
            por_nome.setdefault(nome, []).append((ano, nome, r))
        for nome, its in por_nome.items():
            for _, a, b, r in runs(its):
                mandato(pessoas_pol[nome], cargo, str(a), str(b), r["partido"], r["uf"], orgao)
    for ano in ANOS:
        for r in brasil["Y"][ano]["pol"]["parl"]:
            mandato(pessoas_pol[r["nome"]], "deputado" if r["casa"] == "Câmara" else "senador", str(ano), str(ano), r["partido"],
                    r["uf"], camara if r["casa"] == "Câmara" else senado, r["motivo"], r["votos"])

    # ================================================================ EVENTOS DA TIMELINE (sem fonte, sem natureza)
    for ano in ANOS:
        for sec in ("pol", "intl"):
            for i, ev in enumerate(brasil["Y"][ano][sec]["eventos"]):
                eid = id_evento(ano, ev["titulo"], f"Y[{ano}].{sec}.eventos[{i}]")
                inserir_evento(eid, ev["titulo"], ev["descricao"], ano, None, ev["peso"], "brasil", "linha_do_tempo", f"Y[{ano}].{sec}.eventos[{i}]")

    # ================================================================ META, FTS, DUMP
    meta = {"schema_versao": "1", "migrado_em": TS_MIGRACAO, "migrar_py": "scripts/migrar.py"}
    for n, h in hashes.items():
        meta[f"raw.sha256.{n}"] = h
    con.executemany("INSERT INTO meta(chave,valor) VALUES(?,?)", sorted(meta.items()))
    con.commit()
    popular_fts(con)
    con.commit()
    gerar_dump(con)

    # ================================================================ RELATÓRIO
    escrever_relatorio(con, antes, R, VARIANTES, dup_na_mesma, sem_natureza, mapa, n_rel_teia, n_fam, n_lig, sem_f,
                       n_so_origens, ENTS, IDX_ALIAS, EV_ID_TEIA, hashes)
    con.close()
    print("migração concluída:", SQLITE)


def tokens(s):
    return [t for t in alias_norm(s).split() if t not in ("de", "da", "do", "dos", "das", "e")]


def candidatos_dedup(ENTS):
    lista = [(s, e) for s, e in ENTS.items()]
    out = []
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            (s1, e1), (s2, e2) = lista[i], lista[j]
            if e1["tipo"] != e2["tipo"]:
                continue
            t1, t2 = tokens(e1["nome"]), tokens(e2["nome"])
            if not t1 or not t2:
                continue
            a, b = set(t1), set(t2)
            if e1["tipo"] == "pessoa":
                if (a < b or b < a) and t1[-1] == t2[-1] and min(len(a), len(b)) >= 2:
                    out.append((s1, s2, e1["nome"], e2["nome"], "tokens ⊂ + mesmo sobrenome"))
            else:
                if len(a & b) / len(a | b) >= 0.8:
                    out.append((s1, s2, e1["nome"], e2["nome"], f"Jaccard {len(a & b) / len(a | b):.2f}"))
    return out


def escrever_relatorio(con, antes, R, VARIANTES, dup_na_mesma, sem_natureza, mapa, n_rel_teia, n_fam, n_lig, sem_f,
                       n_so_origens, ENTS, IDX_ALIAS, EV_ID_TEIA, hashes):
    q = lambda s, *a: con.execute(s, a).fetchall()
    L = []
    w = L.append
    w("# Relatório de migração\n")
    w(f"Gerado por `scripts/migrar.py` (timestamp fixo {TS_MIGRACAO}). Fonte: `data/raw/` (hashes em `data/raw/hashes.txt`).\n")
    w("## 1. Contagens antes (raw) e depois (banco)\n")
    w("| Antes (raw) | n |\n|---|---|")
    for k, v in antes.items():
        w(f"| {k} | {v} |")
    w("")
    depois = [
        ("entidade", "SELECT count(*) FROM entidade"), ("  da teia (N)", "SELECT count(*) FROM entidade WHERE origem='teia'"),
        ("  extras (timeline/pares)", "SELECT count(*) FROM entidade WHERE origem<>'teia'"),
        ("entidade_alias", "SELECT count(*) FROM entidade_alias"),
        ("relacao (origem teia, de E[].r)", "SELECT count(*) FROM relacao WHERE origem_ref LIKE 'E[%'"),
        ("relacao (fam_de)", "SELECT count(*) FROM relacao WHERE origem_ref LIKE '%.fam_de'"),
        ("relacao (lig_de)", "SELECT count(*) FROM relacao WHERE origem_ref LIKE '%.lig_de'"),
        ("relacao total", "SELECT count(*) FROM relacao"), ("evento total", "SELECT count(*) FROM evento"),
        ("evidencia", "SELECT count(*) FROM evidencia"), ("relacao_evidencia", "SELECT count(*) FROM relacao_evidencia"),
        ("evento_evidencia", "SELECT count(*) FROM evento_evidencia"), ("evento_entidade", "SELECT count(*) FROM evento_entidade"),
        ("nota", "SELECT count(*) FROM nota"), ("indicador", "SELECT count(*) FROM indicador"), ("serie", "SELECT count(*) FROM serie"),
        ("ranking_empresa", "SELECT count(*) FROM ranking_empresa"), ("mandato", "SELECT count(*) FROM mandato"),
        ("bancada", "SELECT count(*) FROM bancada")]
    w("| Depois (banco) | n |\n|---|---|")
    for k, s in depois:
        w(f"| {k} | {q(s)[0][0]} |")
    w("\nEventos por canal:\n\n| canal | n |\n|---|---|")
    for r in q("SELECT canal, count(*) c FROM evento GROUP BY canal ORDER BY canal"):
        w(f"| {r['canal']} | {r['c']} |")
    w("")
    w("## 2. Eventos sem natureza (`natureza_id` NULL)\n")
    w("| canal | n |\n|---|---|")
    for c, l in sorted(sem_natureza.items()):
        w(f"| {c} | {len(l)} |")
    w(f"\nOs eventos da timeline Brasil (`brasil`) e os marcos legais (`violencia`) nunca tiveram `st`; os da teia são os 92 abaixo "
      f"(todos canal `teia`, nenhum casa com origens). Lista completa dos {len(sem_natureza.get('teia', []))} da teia:\n")
    w("| id | d | título |\n|---|---|---|")
    for eid, d, t, ref in sem_natureza.get("teia", []):
        w(f"| {eid} | {d} | {t.replace('|', '/')} |")
    w("")
    w("## 3. Eventos de origens dedupados com os da teia\n")
    w(f"{len(R['dedup_origens'])} eventos coincidem por `(d, t)`; recebem o id de origens (canal = capítulo de origens) e fundem f (união), r, v, n, p. "
      f"{n_so_origens} eventos existem só em origens (ids preservados); {antes['EV teia'] - len(R['dedup_origens'])} só na teia.\n")
    ex = collections.Counter(R["f_extra_origens"])
    w(f"Diferença de nº de fontes origens − teia nos dedupados: {dict(ex)}. Casos em que a teia tem URL que origens não tem: {len(R['f_so_na_teia'])}"
      f"; casos em que a ordem de f diverge do prefixo de origens: {len(R['f_ordem_diferente'])}.\n")
    w("| id origens | índice teia EV | d | título |\n|---|---|---|---|")
    for eid, i, d, t in R["dedup_origens"]:
        w(f"| {eid} | {i} | {d} | {t.replace('|', '/')} |")
    w("")
    w("## 4. Colisões de slug\n")
    w("Entidades: " + ("nenhuma." if not R["colisoes"] else ""))
    for nome, s, novo, outro in R["colisoes"]:
        w(f"- `{nome}` queria `{s}` (já de `{outro}`) → `{novo}`")
    w("\nEventos (sufixo `-2`, `-3`...): " + ("nenhuma." if not R["colisoes_evento"] else f"{len(R['colisoes_evento'])}"))
    for ref, base, novo in R["colisoes_evento"]:
        w(f"- {ref}: `{base}` → `{novo}`")
    w("")
    w("## 5. Fusões automáticas (slug exato / alias único) com entidades já existentes\n")
    if R["fusao_auto"]:
        for nome, s, origem in R["fusao_auto"]:
            w(f"- `{nome}` → `{s}` (entidade de origem `{origem}`)")
    else:
        w("nenhuma.")
    w("")
    w("## 6. Candidatos a dedup (para aprovação; aprovados vão em `scripts/fusoes.json`)\n")
    cand = candidatos_dedup(ENTS)
    if cand:
        w("| slug A | slug B | nome A | nome B | critério |\n|---|---|---|---|---|")
        for s1, s2, n1, n2, c in cand:
            w(f"| {s1} | {s2} | {n1} | {n2} | {c} |")
    else:
        w("nenhum.")
    w("")
    w("Aliases ambíguos (mesmo `alias_norm` em mais de uma entidade; fora de `indice_alias`):\n")
    amb = {k: v for k, v in IDX_ALIAS.items() if len(v) > 1}
    for k, v in sorted(amb.items()):
        w(f"- `{k}`: {', '.join(sorted(v))}")
    if not amb:
        w("nenhum.")
    w("")
    w("## 7. URLs normalizadas (evidência)\n")
    w("Regra: strip de `#fragment`, barra final e parâmetros `utm_*`. Nada mais (host e esquema intactos).\n")
    alteradas = [(n, sorted(v)) for n, v in VARIANTES.items() if v != {n}]
    colid = [(n, sorted(v)) for n, v in VARIANTES.items() if len(v) > 1]
    w(f"- URLs normalizadas distintas (linhas em `evidencia`): {len(VARIANTES)}")
    w(f"- URLs originais distintas: {sum(len(v) for v in VARIANTES.values())}")
    w(f"- Normalizações que alteraram a URL: {sum(1 for n, v in alteradas for o in v if o != n)}")
    w(f"- Colisões (2+ URLs originais → 1 normalizada): {len(colid)}\n")
    if colid:
        w("Colisões:\n")
        for n, v in colid:
            w(f"- `{n}` ← " + " , ".join(f"`{o}`" for o in v))
        w("")
    mudou = [(n, o) for n, v in alteradas for o in v if o != n and len(v) == 1]
    so_barra = [(n, o) for n, o in mudou if o.rstrip("/") == n]
    outras = [(n, o) for n, o in mudou if o.rstrip("/") != n]
    w(f"Alteradas sem colisão: {len(so_barra)} só pela barra final (não listadas) e {len(outras)} por `#fragment`/`utm_*`/outros:\n")
    for n, o in outras:
        w(f"- `{o}` → `{n}`")
    w("")
    # quase-colisões: mesma URL sem query, query diferente (o inventário apontava 8 candidatas por query/barra)
    base = collections.defaultdict(list)
    for n in VARIANTES:
        base[n.split("?")[0].lower()].append(n)
    quase = {b: sorted(v) for b, v in base.items() if len(v) > 1}
    w(f"Quase-colisões (mesma URL base, queries diferentes; mantidas distintas): {len(quase)}\n")
    for b, v in sorted(quase.items()):
        w("- " + " , ".join(f"`{u}`" for u in v))
    w("")
    w(f"URLs repetidas dentro da mesma relação/evento após normalização (descartadas na junção): {len(dup_na_mesma)}")
    for rot, u in dup_na_mesma:
        w(f"- {rot}: {u}")
    w("")
    w("## 8. Outras decisões e avisos\n")
    w(f"- Relações da teia sem nenhuma fonte: {sem_f}.")
    w(f"- `fam_de` ({n_fam}) e `lig_de` ({n_lig}) viram relações `familiar`/`profissional` (subtipo `escritorio_ligado`) com `natureza_id='nao_classificada'` (NULL não é permitido em `relacao`), `direcional=0`, sem fontes.")
    w("- Pseudo-partidos de `N.p` (\"Ex-ministros e consultores\", \"Órgãos e partidos\") foram para `entidade.grupo`; `partido` guarda só siglas reais. O exportador reconstrói `p` quando `grupo` é um pseudo-partido, senão `sg`.")
    w("- `E.a/E.b` do `teia.json` exportado reproduz a orientação ORIGINAL de cada par (tabela `aresta_legado`; a cor da aresta na página depende dela). A direção semântica vem de `relacao.de/para` (`r.a→r.b`). Índices `E[i]` e `r[j]` preservados.")
    w("- Eventos de origens com `r` vazio gravam `resposta` NULL (exportam de volta como \"\"); `v` vai para `evento.valor_brl` (a proposta mapeava `r`→`contexto` e `v`→`resposta`, o que invertia o significado).")
    w("- Eventos da timeline Brasil (280): `data` = ano do agrupamento, sem fonte, sem natureza, canal `brasil` (subcanal `pol`/`intl` em `origem_ref`).")
    w(f"- `pares.notas`: linhas de log de coleta descartadas ({len(R['pares_notas_descartadas'])}): " + "; ".join(f"\"{t}\"" for t in R["pares_notas_descartadas"]))
    w("- `pares.indicadores`: valores `null` explícitos (ex.: IDH) não viram linha em `serie`; só os pontos não nulos.")
    w("- `pares.foruns` e as seções estruturadas do dossiê (mercado, previdência, dinheiro, limites, máquina) estão em `nota.texto` como JSON (sem modelagem relacional ainda); a seção `brb.eventos` virou 30 eventos canal `brb`.")
    w("- URLs dentro de `nota.texto` do dossiê não passam por `evidencia`.")
    w("- `mandato`: presidentes/vices/presidentes das casas são agregados por anos consecutivos (granularidade de ano; Dilma/Temer em 2016 usam 12/5); `partido` = valor do primeiro ano do período. Parlamentares em destaque (`pol.parl`) viram `mandato` de um ano (`inicio=fim=ano`) com `motivo` e `votos`.")
    w("- `ranking_empresa.posicao` = posição na lista do ano (a lista original não traz posição explícita).")
    w("- Países em `pares` viram entidades `pais` (alias sigla = ISO3); `serie.dimensao` usa `pais=<ISO3>`. Destinos de exportação usam `pais=<nome>` (sem ISO na fonte).")
    w("- `serie` de pares = pontos não nulos dos 18 indicadores (4.806) + PISA (leitura/matemática/ciências e matemática por estado da Índia).")
    w("- Desvios do DDL proposto (marcados `-- DESVIO:` em `scripts/schema.sql`): o DDL original roda sem erro no SQLite 3.45 (incl. STRICT, colunas geradas e FTS5); "
      "acrescentados `entidade.ind_legado`, `evento.valor_brl`, `evento.canal='brb'`, `evento.origem='dossie'`, `ordem` em `relacao_evidencia`/`evento_evidencia`/`evento_entidade`/`nota_entidade`, "
      "`mandato.motivo`/`mandato.votos`; `evento.contexto`/`resposta` passam a significar o que os dados dizem (ver acima).")
    w("- Não feito: ligação de eventos de origens a entidades por `indice_alias` (passo 3 do plano) e extração de eventos de datas internas de `N.d`/`desc`.")
    for a in R["aviso"]:
        w(f"- AVISO: {a}")
    (DATA / "relatorio-migracao.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
