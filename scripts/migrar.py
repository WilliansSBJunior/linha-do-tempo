#!/usr/bin/env python3
"""Migra data/raw/*.json para data/linha-do-tempo.sqlite (recria do zero), gera data/dump.sql e data/relatorio-migracao.md.

Idempotente e determinístico. Só stdlib. Uso: python3 scripts/migrar.py
"""
import collections
import json
import re
import sys

import curadoria
import dossie_rel
from comum import (CURADORIA, DATA, RAW, SCRIPTS, SQLITE, DUMP, TS_MIGRACAO, conectar, dominio_de, gerar_dump,
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
def main(destino=SQLITE, pular=(), escrever=True):
    """destino: caminho do sqlite. pular: etapas de curadoria geradas a ignorar ({'natureza','ligacoes','fontes_brasil','complementos'});
    usado por gerar_curadoria.py. escrever=False não grava dump.sql nem o relatório."""
    destino = type(SQLITE)(destino)
    hashes = verificar_hashes()
    teia, origens, dossie = J("dados-caso-master-v2.json"), J("origens.json"), J("dossie.json")
    pares, brasil, viol = J("pares.json"), J("brasil.json"), J("violencia.json")
    fusoes = json.loads((SCRIPTS / "fusoes.json").read_text(encoding="utf-8"))
    FUSAO = {f["de"]: f["para"] for f in fusoes}

    for p in (destino, destino.with_name(destino.name + "-wal"), destino.with_name(destino.name + "-shm")):
        if p.exists():
            p.unlink()
    con = conectar(destino)
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
    # órgão dos mandatos de presidente/vice (mandato.orgao_id fica NULL); alvo das relações institucionais geradas em curadoria.gerar_relacoes_mandato
    presidencia = extra("Presidência da República", "orgao_publico", ("orgao_publico",), LT, "Y.pol.presidente")
    assert presidencia == "presidencia-da-republica", presidencia

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

    # entidades novas pedidas pela curadoria do dossiê (fundo_previdencia sem nó próprio)
    cfg_dossie = curadoria.ler_json("dossie-entidades.json", {})
    for n in cfg_dossie.get("entidades_novas", []):
        assert n["id"] not in ENTS, n["id"]
        criar(n["id"], n["nome"], n["tipo"], "manual", "curadoria:dossie-entidades.json", descricao=n.get("descricao"), uf=n.get("uf"))
        add_alias(n["id"], n["nome"], "alias", "curadoria")
        for a in n.get("aliases", []):
            add_alias(n["id"], a, "alias", "curadoria")

    # entidades pedidas pela curadoria da rodada 6 (empresas do ranking e parlamentares sem nó; data/curadoria/entidades-adicionais.json)
    R["entidades_adicionais"] = []
    for n in curadoria.ler_json("entidades-adicionais.json", {}).get("entidades", []):
        if n["id"] in ENTS:
            raise SystemExit(f"entidades-adicionais.json: entidade já existe: {n['id']}")
        criar(n["id"], n["nome"], n["tipo"], "manual", "curadoria:entidades-adicionais.json", descricao=n.get("descricao"), uf=n.get("uf"))
        add_alias(n["id"], n["nome"], "alias", "curadoria")
        for a in n.get("aliases", []):
            add_alias(n["id"], a, "alias", "curadoria")
        R["entidades_adicionais"].append(n["id"])

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
            if tabela == "evento_evidencia":
                con.execute(f"INSERT INTO {tabela}({col},evidencia_id,ordem,rotulo) VALUES(?,?,?,?)", (dono, eid, ordem, dom))
            else:
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
        if prefixo in dossie_rel.RELACIONAIS:
            return  # vira tabela relacional (dossie_rel.carregar)
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
    nota("dossie", "aviso", "meta.paginas", None, json.dumps(dossie["meta"]["paginas"], ensure_ascii=False), 0)
    # pares.notas (descarta linhas de log de coleta), foruns (JSON)
    descartadas = []
    for grp, lst in pares["notas"].items():
        for o, t in enumerate(lst):
            if re.match(r"^\s*Cota:", t):
                descartadas.append(t)
                continue
            nota("pares", "aviso", f"notas.{grp}", None, t, o)
    con.execute("INSERT INTO meta(chave,valor) VALUES('pares.gerado_em',?)", (pares["gerado_em"],))
    con.execute("INSERT INTO meta(chave,valor) VALUES('pares.anos',?)", (json.dumps(pares["anos"]),))
    con.execute("INSERT INTO meta(chave,valor) VALUES('pares.ordem_paises',?)", (json.dumps(list(pares["paises"])),))
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
    MARCO_ID = {}
    for i, m in enumerate(viol["MARCOS"]):
        eid = MARCO_ID[i] = id_evento(m["data"], m["curto"], f"MARCOS[{i}]")
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

    # ================================================================ RÓTULOS DE ÉPOCA (nota tipo 'aviso'; páginas brasil e violencia)
    # Textos que as páginas mostram ano a ano e que o modelo relacional não guarda: `mandato` junta anos seguidos do mesmo cargo
    # (o partido do presidente e o texto do vice mudam no meio do mandato), `ranking_empresa` liga a empresa à entidade (o nome
    # da época se perde) e `evidencia` tem uma linha por URL (recortes da violência citam a mesma URL com rótulos e tipos
    # diferentes). Vêm depois de todas as outras notas (não mudam ids antigos). exportar_json.py os junta a series.json e violencia.json.
    for ano in ANOS:
        pol = brasil["Y"][ano]["pol"]
        if pol["partido"]:
            nota("brasil", "aviso", f"Y.{ano}.pol.partido", None, pol["partido"], 0)
        if pol["vice"]:
            nota("brasil", "aviso", f"Y.{ano}.pol.vice", None, pol["vice"], 0)
        for pos, e in enumerate(brasil["Y"][ano]["empresas"], 1):
            if e["nome"] != ENTS[emp_slug[e["k"]]]["nome"]:
                nota("brasil", "aviso", f"Y.{ano}.empresa.{emp_slug[e['k']]}", None, e["nome"], pos)
    # partido do presidente da Câmara/do Senado no ano, quando difere do partido gravado no mandato (o do primeiro ano da sequência)
    for chave in ("presCamara", "presSenado"):
        por_nome = collections.OrderedDict()
        for ano in ANOS:
            for r in brasil["Y"][ano]["pol"][chave]:
                por_nome.setdefault(r["nome"], []).append((ano, r["nome"], r))
        for nome_p, its in por_nome.items():
            for _, a, b, r0 in runs(its):
                for ano, _, r in its:
                    if a <= int(ano) <= b and r["partido"] != r0["partido"]:
                        nota("brasil", "aviso", f"Y.{ano}.{chave}.{pessoas_pol[nome_p]}", None, r["partido"], 0)
    for c, cut in viol["CUTS"].items():
        for ano, e in sorted(cut["years"].items(), key=lambda kv: int(kv[0])):
            if e.get("src"):
                s = viol["CSRC"][e["src"]]
                nota("violencia", "aviso", f"recorte.{c}.{ano}.fonte", s["nome"], s["tipo"], 0)
            if e.get("rateNote"):
                nota("violencia", "aviso", f"recorte.{c}.{ano}.nota_taxa", None, e["rateNote"], 0)
    for i, m in enumerate(viol["MARCOS"]):
        nota("violencia", "aviso", f"marco.{MARCO_ID[i]}.curto", None, m["curto"], i)

    # ================================================================ DOSSIÊ RELACIONAL e FÓRUNS (data/curadoria/dossie-entidades.json)
    dossie_rel.carregar(con, dossie, pares, evid, nat_map, IDX_ALIAS, pais_slug, R)

    # ================================================================ CURADORIA (data/curadoria/*.json), depois da carga bruta
    R["eventos_adic"] = curadoria.aplicar_eventos_adicionais(con)   # à mão (rodada 6); antes da natureza e das fontes, que os veem como os da carga bruta
    n_antes_fusao = con.execute("SELECT count(*) FROM evento").fetchone()[0]
    R["fusoes"] = curadoria.aplicar_fusoes(con)
    R["n_eventos_antes_fusao"] = n_antes_fusao
    if "natureza" not in pular:
        R["natureza"] = curadoria.aplicar_natureza(con)
    if "ligacoes" not in pular:
        R["ligacoes"] = curadoria.aplicar_ligacoes(con)
    if "fontes_brasil" not in pular:
        R["fontes_brasil"] = curadoria.aplicar_fontes_brasil(con, evid)
    if "complementos" not in pular:
        R["complementos"] = curadoria.aplicar_complementos_brasil(con)
    R["aliases_curadoria"] = curadoria.aplicar_aliases(con)
    R["mandato_correcoes"] = curadoria.aplicar_mandato_correcoes(con)   # à mão; antes de confrontar com as APIs e de gerar as relações
    R["mandatos_adic"] = curadoria.aplicar_mandatos_adicionais(con)    # à mão (rodada 6); linhas novas, também confrontadas com as APIs
    R["mandato_oficial"] = curadoria.aplicar_mandato_oficial(con) if "mandato_oficial" not in pular else {"evidencias": 0, "preenchidos": 0, "extras": {}, "complementados": 0, "obsoletas": [], "resumo": {}}
    R["mandato_rel"] = curadoria.gerar_relacoes_mandato(con, R["mandato_oficial"]["extras"])   # teia <-> timeline (herda a evidência oficial dos mandatos)
    R["mandatos_adic_fontes"] = curadoria.ligar_fontes_mandatos_adicionais(con)   # fonte oficial própria de cada linha nova, na relação mandato:<id>
    R["evid_adic"] = curadoria.aplicar_evidencias_adicionais(con)   # à mão; precisa das relações de mandato/filiação; antes dos temas (que leem a descrição)
    R["evid_corr"] = curadoria.aplicar_evidencia_correcoes(con)     # à mão; tipo de evidências oficiais registradas como reportagem
    R["evid_meta"] = curadoria.aplicar_evidencia_metadados(con)     # título/data só onde NULL (rodadas de WebFetch)
    R["ent_valores"] = curadoria.aplicar_entidade_valores(con)      # à mão; estimativas em R$ por entidade; depois dos metadados (só preenche título/data NULL)
    # à mão (rodada 6): lucros, fontes, cobertura, posição e % do PIB do ranking; depois dos complementos do bruto (gerar_curadoria.py pula
    # esta etapa no banco temporário, porque gerar_complementos_brasil casa as linhas com o bruto pela posição original)
    R["ranking_corr"] = curadoria.aplicar_ranking_empresa_correcoes(con) if "ranking_correcoes" not in pular else \
        {"cobertura": [], "atualizadas": [], "inseridas": [], "posicoes": {}, "pct": {}, "evid_novas": [], "ligacoes": 0}
    R["ranking_corr7"] = curadoria.aplicar_ranking_empresa_correcoes(con, curadoria.ARQ_RANKING_CORR_R7) if "ranking_correcoes" not in pular else \
        {"cobertura": [], "atualizadas": [], "inseridas": [], "posicoes": {}, "pct": {}, "evid_novas": [], "ligacoes": 0}   # rodada 7: depois da 6, sobre o que ela gravou
    R["evento_corr"] = curadoria.aplicar_evento_correcoes(con)      # à mão; decisões sobre as ressalvas das evidências adicionais; antes dos temas (leem título/descrição)
    R["relacao_corr"] = curadoria.aplicar_relacao_correcoes(con)
    R["evid_qualidade"] = curadoria.aplicar_evidencia_qualidade(con)   # à mão; revisão do critério 'fraca'; depois de tudo que grava qualidade
    R["peso_wiki"] = curadoria.aplicar_peso_wikipedia(con)   # R6 (regras-fontes.json): wiki nunca 'sustenta'; depois de todas as funções de evidência
    R["temas"] = curadoria.aplicar_temas(con)                  # por último: precisa de todas as relações e ligações evento-entidade

    # ================================================================ META, FTS, DUMP
    meta = {"schema_versao": "2", "migrado_em": TS_MIGRACAO, "migrar_py": "scripts/migrar.py"}
    for n, h in hashes.items():
        meta[f"raw.sha256.{n}"] = h
    con.executemany("INSERT INTO meta(chave,valor) VALUES(?,?)", sorted(meta.items()))
    con.commit()
    popular_fts(con)
    con.commit()
    # decisões humanas da fila de revisão (data/curadoria/decisoes.jsonl), aplicadas por scripts/aplicar_decisoes.py
    decisoes = CURADORIA / "decisoes.jsonl"
    if "decisoes" not in pular and decisoes.exists():
        import subprocess
        r = subprocess.run([sys.executable, str(SCRIPTS / "aplicar_decisoes.py"), "--db", str(destino),
                            "--decisoes", str(decisoes)], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            raise SystemExit("aplicar_decisoes.py falhou:\n" + r.stdout + r.stderr)
        popular_fts(con)
        con.commit()
    if escrever:
        gerar_dump(con)
        (DATA / "relatorio-evidencias-adicionais.md").write_text(curadoria.relatorio_evidencias_adicionais(con, R["evid_adic"], R["evento_corr"]), encoding="utf-8")
        (DATA / "relatorio-revisao-evidencias.md").write_text(curadoria.relatorio_revisao_evidencias(con, R["evento_corr"], R["relacao_corr"]), encoding="utf-8")

        # ================================================================ RELATÓRIO
        escrever_relatorio(con, antes, R, VARIANTES, dup_na_mesma, sem_natureza, mapa, n_rel_teia, n_fam, n_lig, sem_f,
                           n_so_origens, ENTS, IDX_ALIAS, EV_ID_TEIA, hashes)
        print("migração concluída:", destino)
    con.close()
    return destino


def secoes_curadoria(con, R, w):
    """Seções 9 a 13: o que a curadoria (data/curadoria/*.json) e a carga relacional do dossiê fizeram."""
    q = lambda s, *a: con.execute(s, a).fetchall()
    ent = {r["id"]: r["nome"] for r in q("SELECT id, nome FROM entidade")}
    # ---------------------------------------------------------------- 9
    fus = R["fusoes"]
    w("\n## 9. Eventos quase-duplicados fundidos (`data/curadoria/eventos-fusoes.json`)\n")
    w(f"{len(fus)} fusões, {sum(len(f['fundir']) for f in fus)} eventos absorvidos: {R['n_eventos_antes_fusao']} -> {R['n_eventos_antes_fusao'] - sum(len(f['fundir']) for f in fus)} eventos. "
      "Regra: mesma `data` e mesmo fato. O evento `manter` conserva o id e recebe a união de fontes (`evento_evidencia`) e entidades (`evento_entidade`), "
      "`peso` máximo, a natureza mais forte entre os que têm natureza e descrição/contexto/resposta/valor do mantido (ou do primeiro fundido que tenha). "
      "Os ids fundidos viram `evento_alias(alias, evento_id)` e guardam o evento original em `original_json` (título, descrição, data, natureza, fontes com rótulo, entidades). "
      "`mapa_indices.json` aponta os índices antigos de `teia.EV` (e `evento_alias`) para o id mantido. Os candidatos duvidosos estão em `data/curadoria/eventos-candidatos.md`.\n")
    w("| data | mantido | fundidos | natureza resultante | fontes novas | entidades novas |\n|---|---|---|---|---|---|")
    for f in fus:
        w(f"| {f['data']} | `{f['manter']}` | " + ", ".join(f"`{i}`" for i in f["fundir"]) + f" | {f['natureza'] or '-'} | {f['fontes_novas']} | {f['entidades_novas']} |")
    w("")
    por_canal = collections.Counter(c for f in fus for i, c in f["canais"].items() if i != f["manter"])
    w("Eventos absorvidos por canal de origem: " + ", ".join(f"{c} {n}" for c, n in sorted(por_canal.items())) + ".\n")
    # ---------------------------------------------------------------- 10
    n = R.get("natureza", {"arquivo": 0, "aplicados": 0, "por_regra": {}, "por_natureza": {}})
    w("## 10. Natureza dos eventos sem `st` (`data/curadoria/eventos-natureza.json`, `eventos-natureza-manual.json`)\n")
    w("Regras determinísticas (`scripts/curadoria.py`, `classificar_natureza`; o arquivo é regenerado por `scripts/gerar_curadoria.py`). Só atribui onde `natureza_id IS NULL`; nada é inventado. R1-R4 valem para a `teia`; **R5** cobre os eventos factuais da linha do tempo (`brasil`, `violencia`) pelo tipo/domínio das evidências com papel `sustenta`; o que as regras não pegam na teia foi classificado à mão (`M`).\n")
    w("```\n" + curadoria.REGRAS_NATUREZA_TEXTO + "\n```\n")
    w(f"- Atribuídas por regra: {n['aplicados']} (arquivo com {n['arquivo']}). Por regra: " + ", ".join(f"{k} {v}" for k, v in sorted(n["por_regra"].items()))
      + ". Por natureza: " + ", ".join(f"{k} {v}" for k, v in sorted(n["por_natureza"].items())) + ".")
    mn = n.get("manual", {"arquivo": 0, "aplicados": 0, "ignorados": 0, "por_natureza": {}, "excecoes": 0})
    w(f"- Por regra, efetivamente aplicadas: " + ", ".join(f"{k} {v}" for k, v in sorted(n.get("aplicados_por_regra", {}).items())) + ".")
    w(f"- R5 por canal e natureza: " + ", ".join(f"{r[0]}/{r[1]} {r[2]}" for r in q("SELECT canal, COALESCE(natureza_id,'(NULL)'), count(*) FROM evento WHERE canal IN ('brasil','violencia') GROUP BY 1, 2 ORDER BY 1, 2")) + ".")
    w(f"- Classificação manual (`eventos-natureza-manual.json`): {mn['arquivo']} entradas, {mn['aplicados']} aplicadas ({', '.join(f'{k} {v}' for k, v in sorted(mn['por_natureza'].items()))}), "
      f"{mn['ignorados']} ignoradas (já tinham natureza), {mn['excecoes']} exceções explícitas (ficam NULL).")
    ficou = q("SELECT id, data, titulo FROM evento WHERE canal='teia' AND natureza_id IS NULL ORDER BY data, id")
    fus_nat = sum(1 for f in fus if f["natureza"])
    n_teia = q("SELECT count(*) FROM evento WHERE canal='teia'")[0][0]
    abs_teia = sum(1 for f in fus for i, c in f["canais"].items() if i != f["manter"] and c == "teia")
    w(f"- Dos 92 eventos da teia sem `st`: {abs_teia} foram absorvidos em fusões (seção 9) e os demais, somados aos mantidos, são os {n_teia} eventos `teia` atuais. "
      f"Destes, {n['aplicados_por_regra'].get('R1', 0) + n['aplicados_por_regra'].get('R2', 0) + n['aplicados_por_regra'].get('R3', 0) + n['aplicados_por_regra'].get('R4', 0) + mn['aplicados']} ganharam natureza pelas regras R1-R4 ou à mão, {n_teia - (n['aplicados_por_regra'].get('R1', 0) + n['aplicados_por_regra'].get('R2', 0) + n['aplicados_por_regra'].get('R3', 0) + n['aplicados_por_regra'].get('R4', 0)) - mn['aplicados'] - len(ficou)} ficaram com a natureza mais forte do grupo fundido (dossiê BRB, PREC ou origens) e {len(ficou)} seguem NULL.")
    n_outros_null = q("SELECT count(*) FROM evento WHERE canal IN ('brasil','violencia') AND natureza_id IS NULL")[0][0]
    w(f"- **Ficaram NULL: {len(ficou)} eventos do canal `teia`** (lista abaixo; `validar.py` exige zero ou exceção explícita no arquivo manual). Eventos `brasil` e `violencia` NULL: {n_outros_null}.\n")
    w("| id | data | título | fontes |\n|---|---|---|---|")
    for r in ficou:
        nf = q("SELECT count(*) FROM evento_evidencia WHERE evento_id=?", r["id"])[0][0]
        w(f"| {r['id']} | {r['data']} | {r['titulo'].replace('|', '/')} | {nf} |")
    w("")
    # ---------------------------------------------------------------- 11
    fb = R.get("fontes_brasil", {"eventos": 0, "ligacoes": 0, "sustenta": 0, "contexto": 0})
    comp = R.get("complementos", {"receita": 0, "mandato_periodo": 0, "descartes": {}})
    sem = q("SELECT ano, count(*) c FROM evento e WHERE canal='brasil' AND NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id) GROUP BY ano ORDER BY ano")
    w("## 11. Fontes da timeline Brasil (`data/curadoria/brasil-fontes.json`, de `data/raw/dados-brutos-31-anos.json`)\n")
    w("`data/raw/dados-brutos-31-anos.json` entrou em `data/raw/` com hash em `hashes.txt` (única exceção à regra de não mexer no raw: cópia de `projeto-json/`, sem alteração). "
      "Cada evento da timeline foi casado com o item do bruto de mesmo ano e seção (`pol`: blocos `v2_pol_eventos_*` e `v4_pol_*`; `intl`: `v2_intl_eventos_*`) por título igual "
      "(Jaccard >= 0,6 era o plano B; nenhum caso precisou). **O bruto só tem a lista `fontes` por ano e bloco, não por evento**: por isso toda URL do bloco-ano entra em `evento_evidencia`, "
      "como `contexto`; entra como `sustenta` só quando um termo distintivo do slug da URL aparece no título/descrição do evento (heurística conservadora; `url_toca_evento`).\n")
    w(f"- Eventos casados: {fb['eventos']} de 280; sem fonte: {280 - fb['eventos']}.")
    w(f"- Ligações novas em `evento_evidencia`: {fb['ligacoes']} ({fb['sustenta']} `sustenta`, {fb['contexto']} `contexto`).")
    w("- Sem item no bruto (o bruto não traz o primeiro ano de cada bloco de eventos): " + ", ".join(f"{r['ano']} ({r['c']})" for r in sem) + ". Ficam sem fonte.")
    w(f"- URLs de `evidencia` agora: {q('SELECT count(*) FROM evidencia')[0][0]} (todas ligadas a alguma coisa; `validar.py` confere).")
    w(f"- `ranking_empresa.receita_brl_bi`: {comp['receita']} das 397 linhas da carga bruta preenchidas (a rodada 6, seção 23, acrescenta linhas sem receita). Mapeamento inequívoco = mesmo ano, mesmo lucro e mesma fonte ou nome; onde o bruto repete a empresa em dois blocos com receita nula num e valor no outro, vale o valor; "
      f"conflito de dois valores diferentes: {len(comp['descartes'].get('receita_ambigua', []))}. As outras {comp['descartes'].get('empresas_sem_receita_no_bruto', 0)} linhas têm `receita_liquida_brl_bi` nulo no bruto.")
    w(f"- `mandato.periodo_texto`: {comp['mandato_periodo']} mandatos de presidente da Câmara/Senado (nome + ano em `v2_pol_estrutura`/`v4_estrutura.presidencias`; textos de anos diferentes do mesmo mandato unidos por ` | `); sem correspondência: {len(comp['descartes'].get('mandatos_sem_periodo', []))}.")
    w("- **Do bruto não carregado** (sem mapeamento inequívoco ou sem tabela): `lideres` (líderes de governo e de bancada por ano, `v2_pol_estrutura` e `v4_estrutura`); `legislaturas` e `senado` com bancadas e as notas de método (`camara_base`, `senado_base`); "
      "`notas` de cada ano/bloco (limites da coleta, itens 'NÃO CONFIRMADO'); `maiores_prejuizos` só entra quando a empresa já está no ranking publicado; `exportacoes_total_wits_usd_mi`; "
      "e as `fontes` dos blocos macro, setores, comércio, intl e estrutura (262 URLs únicas ainda fora de `evidencia`, porque a fonte vale para o bloco-ano inteiro e `serie` tem uma única `evidencia_id` por ponto).\n")
    # ---------------------------------------------------------------- 12
    lg = curadoria.ler_json("evento-entidade-auto.json", [])
    por_alias = collections.defaultdict(list)
    for it in lg:
        for e in it["entidades"]:
            por_alias[(e["id"], e["alias"])].append(it["evento_id"])
    rg = curadoria.regras_ligacao()
    w("## 12. Ligação evento -> entidade por alias (`data/curadoria/evento-entidade-auto.json`)\n")
    w("Candidatos: eventos sem nenhuma linha em `evento_entidade` (origens, PREC, brb, brasil, violência). Casamento de `titulo + descricao` com `entidade_alias` (só `alias_norm` único no banco), "
      "palavra inteira, normalizado sem acento, alias mais longo primeiro e sem sobreposição, `papel='citado'`. Regras em `data/curadoria/evento-entidade-regras.json`:\n")
    w("- alias de pessoa com um só token só vale se estiver em `pessoa_um_token_ok` (" + ", ".join(rg.get("pessoa_um_token_ok", [])) + "); sobrenomes ambíguos barrados sozinhos: " + ", ".join(rg.get("sobrenomes_ambiguos", [])) + ".")
    w("- siglas (alias em maiúsculas ou `tipo_alias='sigla'`) só em maiúsculas e não seguidas de número (evita 'PL 2338' e 'pl').")
    w("- entidades excluídas: " + ", ".join(rg.get("excluir_entidades", [])) + " (aparece em tudo). Exigem inicial maiúscula: " + ", ".join(rg.get("exigir_inicial_maiuscula", []))
      + ". Contextos barrados: " + "; ".join(f"'{k}' seguido de {'/'.join(v)}" for k, v in rg.get("nao_seguido_por", {}).items())
      + "; " + "; ".join(f"'{k}' precedido de {'/'.join(v)}" for k, v in rg.get("nao_precedido_por", {}).items()) + ".\n")
    lig = R.get("ligacoes", {"eventos": 0, "ligacoes": 0})
    w(f"- Resultado: {lig['eventos']} eventos receberam ligação, {lig['ligacoes']} linhas novas em `evento_entidade`.")
    w("- Eventos ainda sem entidade por canal: " + ", ".join(f"{r['canal']} {r['c']}" for r in q("SELECT canal, count(*) c FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.evento_id=e.id) GROUP BY canal ORDER BY canal")) + ".")
    sus = sorted(((len(v), k) for k, v in por_alias.items() if len(v) > 15), reverse=True)
    w("\nAliases com mais de 15 ligações (suspeitos por volume; são nomes de órgãos e partidos que aparecem muito nos textos da timeline; a amostra abaixo não achou falso positivo entre eles, mas vale conferir os eventos):\n")
    w("| ligações | entidade | alias casado |\n|---|---|---|")
    for n_, (e, a) in sus:
        w(f"| {n_} | `{e}` ({ent.get(e, e)}) | {a} |")
    w("\nAmostra de 30 ligações para conferência (a cada k-ésima, em ordem de evento):\n")
    w("| evento | título | alias -> entidade |\n|---|---|---|")
    flat = [(it["evento_id"], e) for it in lg for e in it["entidades"]]
    passo = max(1, len(flat) // 30)
    tit = {r["id"]: r["titulo"] for r in q("SELECT id, titulo FROM evento")}
    for ev_id, e in flat[::passo][:30]:
        w(f"| `{ev_id}` | {tit[ev_id].replace('|', '/')[:80]} | {e['alias']} -> `{e['id']}` |")
    w("")
    # ---------------------------------------------------------------- 13
    w("## 13. Dossiê e fóruns relacionais (`scripts/dossie_rel.py`)\n")
    w("`mercado.pares`, `previdencia.entes`, `dinheiro.{contratos,midia,doacoes}`, `maquina.indicios`, `limites.*` e `pares.foruns` deixaram de ir para `nota.texto`. Tabelas (cada uma guarda também o texto original, para exportar igual ao embutido):\n")
    w("| tabela | linhas | observação |\n|---|---|---|")
    obs = {"dossie_par": "13 pares; 'Antônio Rueda e ACM Neto' vira 2 linhas (mesma `ordem`, `sub` 0 e 1); `liga` sim/apura/nao",
           "dossie_par_evidencia": "fontes de cada par (`rotulo` = veículo como no original)",
           "previdencia_ente": "11 entes (inclui a linha agregada 'Outros oito'); soma R$ 1.867,45 mi",
           "pagamento": "contratos 8, mídia 3, doações 3 (`ano` extraído do texto das doações; valores em R$ mi, como no dossiê)",
           "indicio_maquina": "5 indícios (`forca` 1-2)", "limite": "derrubado 6, aberto 4, agenda 3 (`data` ISO quando reconhecível, `data_texto` original)",
           "forum": "10 países x (G20, BRICS, OCDE, CSNU, nuclear); CSNU com lista vira `anos` (JSON); nuclear: `status_texto` sim/nao e `primeiro_teste`"}
    for t, o in obs.items():
        w(f"| {t} | {q(f'SELECT count(*) FROM {t}')[0][0]} | {o} |")
    w("")
    novas = curadoria.ler_json("dossie-entidades.json", {}).get("entidades_novas", [])
    w("Entidades criadas (tipo `fundo_previdencia`, origem `manual`, sem nó na teia, com alias): " + ", ".join(f"`{n['id']}`" for n in novas) + ".\n")
    por = collections.Counter(c for _, _, es, c in R["dossie_vinculos"] if es)
    n_sem = sum(1 for _, _, es, _ in R["dossie_vinculos"] if not es)
    w(f"Vínculo texto -> entidade ({len(R['dossie_vinculos'])} textos): {por['manual']} pelo mapa manual (`data/curadoria/dossie-entidades.json`), {por['alias']} por alias único exato, {n_sem} sem entidade.")
    w("\nTextos sem entidade (ficam só como texto):\n")
    for sec, t, es, c in R["dossie_vinculos"]:
        if not es:
            w(f"- {sec}: {t}")
    w("\nVinculados pelo mapa manual (as aproximações estão justificadas em `justificativas` no JSON; as mais discutíveis: Amazonprev, escritórios -> pessoa, Metrópoles):\n")
    for sec, t, es, c in R["dossie_vinculos"]:
        if c == "manual" and es:
            w(f"- {sec}: {t} -> " + ", ".join(f"`{e}`" for e in es))
    w("\n`exportar_json.py` gera `data/dossie.json` e `data/pares.json` a partir dessas tabelas e `validar.py` os compara com `data/raw/dossie.json` e `data/raw/pares.json`. Diferenças aceitas e documentadas:\n")
    w("- URLs em `src` saem normalizadas (sem barra final): 29 URLs; a comparação normaliza os dois lados.")
    w("- `pares.json`: 230 valores `null` explícitos dos indicadores e 18 do PISA não viram linha em `serie` (já era assim); e a linha de log \"Cota: 39 buscas/fetches usados.\" de `pares.notas` continua descartada.")
    w("- `meta.paginas` do dossiê fica em `nota` (chave `meta.paginas`, JSON) e as `meta` do banco ganham `pares.gerado_em`, `pares.anos` e `pares.ordem_paises`.")
    w("- `dossie.json` inclui os 30 eventos BRB como no original (os fundidos saem de `evento_alias.original_json`); `teia.json` e `origens.json` refletem a curadoria (eventos fundidos saem da lista; `mapa_indices.json` ainda resolve os índices antigos).\n")


def secoes_modelo(con, R, w):
    """Seções 14 a 16: tema N:N, fonte genérica, ligação teia <-> timeline."""
    q = lambda s, *a: con.execute(s, a).fetchall()
    cfg = curadoria.ler_json("temas.json", {})
    nome = {r["id"]: r["nome"] for r in q("SELECT id, nome FROM tema")}
    # ---------------------------------------------------------------- 14
    w("\n## 14. Tema como dimensão N:N (`data/curadoria/temas.json`)\n")
    w("Tabelas: `tema(id, nome, descricao, cor, ordem, principal)`, `relacao_tema(relacao_id, tema_id, origem, regra)`, `evento_tema(evento_id, tema_id, origem, regra)`. "
      "**A entidade não tem tabela**: `v_entidade_tema` (view) deriva a pertinência: a entidade está no tema se tem relação ou evento nele; acrescentei como fontes estruturais "
      "`mandato`/`bancada`/`ranking_empresa` -> `brasil-ano-a-ano`, `forum` -> `pares` e o dossiê relacional (par, ente de previdência, pagamento) -> `caso-master` "
      "(sem isso empresas do ranking, partidos da bancada e países de `forum` ficariam sem tema, e as 'fusões' dependem disso). `entidade.categoria_id` continua sendo a categoria da teia. "
      "`migrar.py` aplica `temas.json` por último (`curadoria.aplicar_temas`), depois de fusões, ligações evento-entidade e relações de mandato; "
      "`exportar_json.py` emite `tema` em cada relação/evento de `teia.json` (e nos eventos de `origens.json`), `temas` em cada entidade de `entities.json` e o novo `temas.json`.\n")
    w("Regras (aplicadas na ordem; filtros combinados com E; `dentro_de` = só registros que já têm aquele tema; texto = palavra inteira, sem acento/caixa, `*` = prefixo):\n")
    w("| regra | tema | alvo | filtros | relações | eventos |\n|---|---|---|---|---|---|")
    st = R["temas"]["por_regra"]
    for rg in cfg.get("regras", []):
        filtros = "; ".join(f"{k}={v}" for k, v in rg.items() if k not in ("id", "tema", "alvo"))
        s_ = st.get(rg["id"], {"relacao": 0, "evento": 0})
        w(f"| {rg['id']} | {rg['tema']} | {rg['alvo']} | {filtros.replace('|', '/')} | {s_['relacao']} | {s_['evento']} |")
    w("\nExceções (`excecoes` em `temas.json`; falso positivo de texto removido à mão, com motivo):\n")
    w("| alvo | ref | incluir | excluir | motivo |\n|---|---|---|---|---|")
    for ex in cfg.get("excecoes", []):
        w(f"| {ex['alvo']} | `{ex['ref']}` | {', '.join(ex.get('incluir', [])) or '-'} | {', '.join(ex.get('excluir', [])) or '-'} | {ex.get('motivo', '')} |")
    w("\nContagens por tema (entidades vêm da view; um registro pode estar em vários temas):\n")
    w("| tema | relações | eventos | entidades |\n|---|---|---|---|")
    ent = {r[0]: r[1] for r in q("SELECT tema_id, count(*) FROM v_entidade_tema GROUP BY tema_id")}
    rel = {r[0]: r[1] for r in q("SELECT tema_id, count(*) FROM relacao_tema GROUP BY tema_id")}
    evn = {r[0]: r[1] for r in q("SELECT tema_id, count(*) FROM evento_tema GROUP BY tema_id")}
    for t in cfg.get("temas", []):
        w(f"| `{t['id']}` ({nome[t['id']]}) | {rel.get(t['id'], 0)} | {evn.get(t['id'], 0)} | {ent.get(t['id'], 0)} |")
    multi_r = q("SELECT count(*) FROM (SELECT relacao_id FROM relacao_tema GROUP BY relacao_id HAVING count(*)>1)")[0][0]
    multi_e = q("SELECT count(*) FROM (SELECT evento_id FROM evento_tema GROUP BY evento_id HAVING count(*)>1)")[0][0]
    multi_n = q("SELECT count(*) FROM (SELECT entidade_id FROM v_entidade_tema GROUP BY entidade_id HAVING count(*)>1)")[0][0]
    w(f"\nEm mais de um tema: {multi_r} relações, {multi_e} eventos, {multi_n} entidades. Registros no tema-caixa `a-classificar`: {R['temas']['fallback']['relacao']} relações, {R['temas']['fallback']['evento']} eventos "
      "(o MCP usa esse tema quando não consegue inferir; `validar.py` avisa se houver algum).\n")
    w("Limites conhecidos: (a) os temas por texto (`inss`, `pcc`, `brb`, `precatorios`, `lagoinha`) marcam **citação**, não centralidade: uma relação que só menciona a CPMI do INSS como origem de um documento entra em `inss` "
      "(retirei os casos mais óbvios nas exceções); (b) `usinas` ficou de fora do `pcc-texto` (a maior parte das ocorrências é o setor sucroalcooleiro dos precatórios, não o PCC); só 'Usina Itajobi'; "
      "(c) `pares` não tem relação nem evento (só 10 países via `forum`), e `violencia` só 10 eventos: séries (`indicador`/`serie`) **não** têm tema ainda; (d) eventos novos não entram por MCP (não há ferramenta), só por migração.\n")
    # ---------------------------------------------------------------- 15
    w("\n## 15. Fonte genérica (`fonte` no lugar de `video`)\n")
    w("`video` virou `fonte(id, tipo, plataforma?, url?, titulo, canal, canal_entidade_id, publicado_em, duracao_s, texto, hash_texto, arquivo_texto, resumo, evidencia_id, ...)` com "
      "`tipo IN ('video','reportagem','documento','pdf','depoimento','decisao','transcricao','outro')`. `texto` substitui `transcricao` (conteúdo extraído; para vídeo é a transcrição) e `hash_texto` é o sha256 do texto. "
      "`evidencia_id` é obrigatório quando há `url` (CHECK) e a evidência tem a mesma URL normalizada; sem URL (depoimento oral, documento físico) fica NULL. "
      "`trecho.video_id` virou `trecho.fonte_id`; `inicio_s`/`fim_s` passaram a ser opcionais (trigger exige para fonte tipo video) e entrou `localizacao` (página/parágrafo). "
      "`corte` continua com a coluna `video_id`, agora referenciando `fonte(id)`; triggers `trg_corte_so_video_*` recusam corte em fonte que não seja `video` (e a troca de tipo de uma fonte com cortes). "
      "A view `video` reproduz as colunas antigas (somente leitura; `transcricao` = `texto`). `busca_fts` ganhou linhas `fonte` (título, canal, resumo, texto).\n")
    w(f"Dados migrados: a tabela `video` estava vazia (0 linhas), então não houve conversão de registros: {q('SELECT count(*) FROM fonte')[0][0]} fontes agora. "
      "Nota: `migrar.py` recria o banco do zero a partir de `data/raw/` + `data/curadoria/`; o que o MCP gravou (vídeos, relações `classificador`) só sobrevive no `dump.sql` versionado, não numa nova migração.\n")
    # ---------------------------------------------------------------- 16
    mr = R["mandato_rel"]
    w("\n## 16. Teia <-> timeline: mandato e bancada -> relações institucionais (`data/curadoria/mandato-relacoes.json`)\n")
    w(f"`curadoria.gerar_relacoes_mandato` cria **{mr['mandato'] + mr['filiacao']} relações novas** (`tipo='institucional'`, `natureza='documentada'`, `origem='linha_do_tempo'`, `status='publicada'`, tema `brasil-ano-a-ano`), "
      "depois de toda a carga bruta (ids novos, os antigos não mudam):\n")
    w(f"- **{mr['mandato']} de mandato** (`subtipo='mandato:<cargo>'`, pessoa -> órgão, uma por linha de `mandato`, `origem_ref='mandato:<id>'`, período = o do mandato): "
      + ", ".join(f"{k} {v}" for k, v in sorted(mr["por_cargo"].items())) + ".")
    w(f"- **{mr['filiacao']} de filiação** (`subtipo='filiacao'`, pessoa -> partido, rótulo 'Filiado ao <sigla>'): uma por sequência contínua de mandatos do mesmo partido (anos consecutivos se fundem); "
      "o período é **inferido dos mandatos** (`periodo_aprox=1`, `periodo_texto='inferido dos mandatos'`), não a data de filiação.")
    w("- Órgãos: `camara-dos-deputados`, `senado-federal` (já existiam, origem timeline) e **`presidencia-da-republica`** (nova, `orgao_publico`; presidente e vice-presidente, em que `mandato.orgao_id` é NULL).")
    mo = R["mandato_oficial"]
    n_ev = q("SELECT count(*) FROM mandato WHERE evidencia_id IS NOT NULL")[0][0]
    rs = mo.get("resumo") or {}
    pt = rs.get("confirmados_por_tipo", {})
    w(f"- `mandato.evidencia_id`: {n_ev} de {mr['mandato']} linhas têm evidência oficial: {pt.get('legislatura', 0)} por legislatura e {pt.get('eleicao', 0)} por eleição "
      "(`tipo='dado_oficial'`, Dados Abertos da Câmara/Senado; a de eleição prova o mandato da legislatura seguinte, não o exercício no ano), "
      f"{pt.get('pagina', 0)} por página oficial da presidência da Casa (`tipo='documento_oficial'`, `presidente_camara`/`presidente_senado`). "
      "Fonte: `data/curadoria/mandato-oficial.json`, gerado de `data/raw/oficial/`; "
      f"as relações de mandato e de filiação herdam essa evidência via `relacao_evidencia`. Complementos de partido/UF: {mo['complementados']}. "
      f"Divergentes: {rs.get('divergentes', 0)}; sem fonte oficial: {rs.get('sem_fonte_oficial', 0)} (presidente e vice-presidente: não há página pública). "
      "As listas estão em `data/relatorio-mandatos-oficial.md`; o banco não foi alterado por elas.")
    n_cor = len(R["mandato_correcoes"]["aplicadas"])
    w(f"- Escritos à mão em `data/curadoria/`: `mandato-correcoes.json` ({n_cor} correção de partido/UF em `mandato`, aplicada antes do confronto com as fontes oficiais; Miro Teixeira 2004, PT -> PPS, pelo histórico da Câmara) "
      f"e `entidade-aliases.json` ({R['aliases_curadoria']['aplicados']} aliases de grafia: Enéas, Luís Eduardo, Luiz Carlos Santos).")
    w("- **Parlamentares em destaque** (`deputado`/`senador`, `mandato` de um ano = ano do destaque na timeline): a relação tem `periodo_aprox=1` e a descrição avisa que o período é o ano do destaque, não o mandato inteiro.")
    sp = mr["sem_partido"]
    w("- Mandatos sem filiação (partido sem entidade): " + (", ".join(f"{e} ({p})" for _, e, p in sp) if sp else "nenhum") + ". Não criei entidade de partido (PRTB, PSOL); decisão pendente.")
    w(f"- Mandatos sem órgão resolvido: {len(mr['sem_orgao'])}.\n")
    fus = [r[0] for r in q("""SELECT e.id FROM entidade e WHERE e.origem='teia' AND (EXISTS (SELECT 1 FROM mandato m WHERE m.entidade_id=e.id OR m.orgao_id=e.id)
        OR EXISTS (SELECT 1 FROM bancada b WHERE b.partido_id=e.id) OR EXISTS (SELECT 1 FROM ranking_empresa k WHERE k.entidade_id=e.id)
        OR EXISTS (SELECT 1 FROM evento_entidade x JOIN evento v ON v.id=x.evento_id WHERE x.entidade_id=e.id AND v.canal='brasil')) ORDER BY e.id""")]
    w(f"Entidades da teia que aparecem na timeline (as 10 fusões da seção 5 mais as ligadas por eventos `brasil`): {len(fus)}, todas em `brasil-ano-a-ano` **e** `caso-master` pela view: "
      + ", ".join(f"`{e}`" for e in fus) + ".")
    # ---------------------------------------------------------------- 17
    ev = R["ent_valores"]
    w("\n## 17. Estimativas em R$ por entidade (`data/curadoria/entidade-valores.json`)\n")
    w(f"`curadoria.aplicar_entidade_valores` grava **{ev['entradas']} valores em {ev['entidades']} entidades** na tabela aditiva `entidade_valor` "
      f"({ev['principais']} principais, {ev['fracas']} com fonte fraca), depois dos metadados de evidência. Cada valor tem uma `natureza` "
      "(o que o número mede); números de naturezas diferentes não se somam. A URL de cada valor é uma `evidencia` "
      f"({ev['evid_novas']} novas, {ev['evid_reaproveitadas']} reaproveitadas; título preenchido em {ev['titulos']} e data em {ev['datas']} que estavam NULL). "
      f"No arquivo, só como registro: {ev['descartados']} valor descartado e {ev['sem_estimativa']} entidade sem estimativa encontrada.\n")
    w("| natureza | n |\n|---|---|")
    for k, n in sorted(ev["por_natureza"].items()):
        w(f"| {k} | {n} |")
    w("\n| entidade | principal | natureza | valor (R$) | quem estima | qualidade |\n|---|---|---|---|---|---|")
    for r in q("""SELECT v.entidade_id, v.principal, v.natureza, v.valor_brl, v.quem_estima, v.qualidade FROM entidade_valor v
                  ORDER BY v.entidade_id, v.ordem"""):
        w(f"| `{r['entidade_id']}` | {'sim' if r['principal'] else ''} | {r['natureza']} | {format(r['valor_brl'], ',.0f').replace(',', '.')} | {r['quem_estima']} | {r['qualidade']} |")
    if ev["sem_principal"]:
        w("\nEntidades com valores mas sem principal (o painel mostra só as linhas secundárias): " + ", ".join(f"`{k}`" for k in ev["sem_principal"]) + ".")
    w("\nNa teia (`teia.json`), cada nó com valores ganha `val` (a lista, principal primeiro) e `val_lig` (soma de `relacao.valor_brl` das ligações "
      "`E[].r` do nó e quantas têm valor): a soma das ligações é outra coisa que a estimativa do escândalo e não se soma a ela.")
    # ---------------------------------------------------------------- 18
    eq = R["evid_qualidade"]
    tabs = ("evento_evidencia", "relacao_evidencia")
    w("\n## 18. Revisão do critério 'fraca' (`data/curadoria/evidencia-qualidade-revisao.json`)\n")
    w("Regra (do `_doc` do arquivo): `fraca` descreve a fonte, não a lacuna da nota. `curadoria.aplicar_evidencia_qualidade` roda depois de tudo que grava "
      "`qualidade` (evidências adicionais, substituições, metadados, valores, correções) e troca `fraca` -> `boa` na ligação de cada entrada de `revisoes`, "
      "achada por evento (id ou alias de fusão) + URL normalizada ou por relação (`origem` + `origem_ref`) + URL. A `nota` do pesquisador fica intacta; o "
      "`motivo` não vai para o banco (não há coluna para ele) e fica só aqui. Aborta sem aplicar nada se a ligação não existe ou a qualidade atual não é `fraca`, "
      "com duas exceções registradas abaixo: entrada repetida idêntica (conta uma vez) e fonte `fraca` já substituída em `evidencias-adicionais.json` "
      "(`substituida_por`), que por desenho não está ligada ao alvo.\n")
    w("| | evento_evidencia | relacao_evidencia | total |\n|---|---:|---:|---:|")
    ap = collections.Counter(x["tabela"] for x in eq["aplicadas"])
    w(f"| ligações `fraca` antes | {eq['antes'][tabs[0]]} | {eq['antes'][tabs[1]]} | {sum(eq['antes'].values())} |")
    w(f"| revistas para `boa` | {ap[tabs[0]]} | {ap[tabs[1]]} | {len(eq['aplicadas'])} |")
    w(f"| ligações `fraca` depois | {eq['depois'][tabs[0]]} | {eq['depois'][tabs[1]]} | {sum(eq['depois'].values())} |")
    w(f"\nEntradas em `revisoes`: {eq['entradas']} = {len(eq['aplicadas'])} aplicadas + {len(eq['duplicadas'])} repetidas (idênticas) + "
      f"{len(eq['substituidas'])} sobre fontes já substituídas (nada a mudar no banco). `mantidas_fracas` do arquivo = {eq['mantidas_fracas_arquivo']} "
      f"(= {eq['adic_fracas']} entradas `fraca` de `evidencias-adicionais.json` − {eq['entradas']} entradas de `revisoes`, contando as "
      f"{eq['adic_substituidas']} substituídas, que não estão ligadas, e as repetidas). No banco ficam {sum(eq['depois'].values())} = "
      f"{sum(eq['antes'].values())} fracas ligadas (= {eq['adic_fracas']} − {eq['adic_substituidas']} substituídas) − {len(eq['aplicadas'])} revistas "
      f"(= `mantidas_fracas` − {eq['adic_substituidas']} substituídas + {len(eq['substituidas'])} revisões sobre substituídas + {len(eq['duplicadas'])} repetidas).\n")
    w("| motivo | aplicadas |\n|---|---:|")
    for m, n in sorted(collections.Counter(x["motivo"] for x in eq["aplicadas"]).items()):
        w(f"| {m} | {n} |")
    if eq["substituidas"]:
        w("\nSobre fontes já substituídas (a `fraca` não está ligada; a substituta `boa` está):\n")
        w("| alvo | fraca | substituída por |\n|---|---|---|")
        for x in eq["substituidas"]:
            a = x["evento_id"] if x["alvo_tipo"] == "evento" else f"{x['relacao_origem']} {x['relacao_origem_ref']}"
            sp = x["substituida_por"]
            w(f"| `{a}` | {x['url']} | {', '.join(sp) if isinstance(sp, list) else sp} |")
    if eq["duplicadas"]:
        w("\nRepetidas (idênticas a uma entrada anterior; contadas uma vez):\n")
        for x in eq["duplicadas"]:
            a = x["evento_id"] if x["alvo_tipo"] == "evento" else f"{x['relacao_origem']} {x['relacao_origem_ref']}"
            w(f"- `{a}`: {x['url']}")
    w("\n| alvo | url | motivo |\n|---|---|---|")
    for x in eq["aplicadas"]:
        a = x["evento_id"] if x["alvo_tipo"] == "evento" else f"{x['relacao_origem']} {x['relacao_origem_ref']}"
        w(f"| `{a}` | {x['url']} | {x['motivo']} |")
    # ---------------------------------------------------------------- 19
    r3 = [e for e in R["evid_adic"]["entradas"] if e.get("rodada") == 3]
    if r3:
        ev3 = sorted({e["evento_id"] for e in r3})
        nat3 = collections.Counter(con.execute("SELECT natureza_id FROM evento WHERE id=?", (i,)).fetchone()[0] for i in ev3)
        corr3 = [c for c in R["evento_corr"]["aplicadas"] if c.get("rodada") == 3]
        restam = [r[0] for r in q("SELECT id FROM evento WHERE natureza_id='nao_classificada' ORDER BY data, id")]
        w("\n## 19. Rodada 3 de fontes (`data/curadoria/evidencias-rodada3.json`)\n")
        w(f"{len(r3)} entradas para {len(ev3)} eventos que a rodada 2 deixou `nao_classificada`, aplicadas por `curadoria.aplicar_evidencias_adicionais` "
          "junto com `evidencias-adicionais.json` (`curadoria.ler_evidencias_adicionais`), papel `sustenta`; as ligações wiki/outro que esses eventos já tinham ficam. "
          "A natureza vem de `eventos-natureza.json`, regerado (R5) depois da rodada. Decisão desta rodada: R5 passa a contar `comunicado` (nota de órgão público) "
          "como fonte oficial, como `documento_oficial`/`dado_oficial`/`decisao_judicial`; sem isso, 4 eventos sustentados só por press release do Fed e da ONU "
          "continuariam `nao_classificada` (nenhum outro evento muda). "
          f"Correções de texto da rodada: {len(corr3)} (`evento-correcoes.json`, `\"rodada\": 3`; detalhe em `relatorio-evidencias-adicionais.md`, seção \"Rodada 3\").\n")
        w("| natureza dos eventos cobertos | eventos |\n|---|---:|")
        for k, n in sorted(nat3.items()):
            w(f"| {k} | {n} |")
        w("\n| natureza (todos os eventos) | eventos |\n|---|---:|")
        for r in q("SELECT COALESCE(natureza_id,'(NULL)') n, count(*) c FROM evento GROUP BY 1 ORDER BY 1"):
            w(f"| {r['n']} | {r['c']} |")
        w(f"\nEventos `nao_classificada` depois da rodada: {len(restam)}" + (" (" + ", ".join(f"`{i}`" for i in restam) + ")." if restam else "."))
    # ---------------------------------------------------------------- 20
    ea = R["evid_adic"]
    r4 = [e for e in ea["entradas"] if e.get("rodada") == 4]
    if r4:
        corr4 = [c for c in R["evento_corr"]["aplicadas"] if c.get("rodada") == 4]
        fr_dist = {(curadoria._chave_alvo(e), curadoria.normalizar_url(e["substitui"])) for e in r4}
        nf = sum(eq["depois"].values())
        n5s = len({(curadoria._chave_alvo(e), curadoria.normalizar_url(e["substitui"])) for e in ea["entradas"] if e.get("rodada") == 5 and e.get("substitui")})
        w("\n## 20. Rodada 4: substituição das fontes fracas (`data/curadoria/substituicoes-rodada4.json`)\n")
        w(f"{len(r4)} fontes novas (`boa`, papel `sustenta`) para {len({curadoria._chave_alvo(e) for e in r4})} alvos, cada uma com `substitui`; "
          f"{len(fr_dist)} fontes fracas distintas substituídas (todas registradas em `evidencias-adicionais.json`, que ganham `substituida_por`). "
          "Aplicadas por `curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, depois das rodadas 1-3), conferidas antes por "
          "`curadoria.conferir_substituicoes`. Uma fraca substituída deixa de ser ligada ao alvo; se a URL também é fonte bruta do bloco-ano do evento "
          f"(`brasil-fontes.json`), a ligação volta a ser `contexto` sem avaliação ({len(ea['contexto_mantidas'])} já eram `contexto`; "
          f"{len(ea['rebaixadas'])} eram `sustenta` por slug e foram rebaixadas). {len(ea['r4_ja_ligadas'])} substitutas já eram fonte `boa` do alvo "
          f"(rodadas 2-3; a ligação existente fica), {len(ea['r4_reavaliadas'])} são a mesma URL relida (reavaliação) e {len(ea['r4_promovidas'])} eram "
          f"`contexto` do bloco-ano e subiram a `sustenta`. Ligações `fraca` no banco ao fim da rodada (antes da R6 e da rodada 5): {nf + n5s + len(fr_dist)} -> {nf + n5s}. "
          f"Correções de texto: {len(corr4)} em `evento-correcoes.json` (`\"rodada\": 4`) e a descrição de `N[197].fam_de` em `relacao-correcoes.json`. "
          "Detalhe em `relatorio-evidencias-adicionais.md`, seção \"Rodada 4\".\n")
        w("| natureza (todos os eventos) | eventos |\n|---|---:|")
        for r in q("SELECT COALESCE(natureza_id,'(NULL)') n, count(*) c FROM evento GROUP BY 1 ORDER BY 1"):
            w(f"| {r['n']} | {r['c']} |")
    # ---------------------------------------------------------------- 21
    pw = R["peso_wiki"]
    if pw.get("ativo"):
        fracas_depois = sum(curadoria._contar_fracas(con).values())
        w("\n## 21. R6: peso da Wikipédia (`data/curadoria/regras-fontes.json`)\n")
        w(f"Registro da decisão (`motivo` do arquivo): {pw['motivo']}\n")
        w("`curadoria.aplicar_peso_wikipedia` roda depois de todas as funções de evidência (inclusive `aplicar_evidencia_qualidade`, que exige a `fraca` "
          "ainda gravada) e antes de gerar a natureza (`gerar_curadoria.py --so natureza` parte de um banco com R6 aplicada; R5 só olha `sustenta`). "
          "Rebaixa toda ligação de fonte wiki (`evidencia.tipo='wiki'` ou domínio `*.wikipedia.org`) com papel `sustenta` para `contexto`, mantendo "
          "rótulo, trecho e nota; `qualidade` passa a NULL (contexto não é avaliado). Aborta sem mudar nada se algum evento ou relação ficaria sem "
          "fonte `sustenta` (nenhum dependia só de wiki).\n")
        w("| | evento_evidencia | relacao_evidencia |\n|---|---:|---:|")
        w(f"| wiki `sustenta` rebaixadas a `contexto` | {len(pw['evento'])} | {len(pw['relacao'])} |")
        w(f"| alvos distintos | {len({x[0] for x in pw['evento']})} | {len({x[0] for x in pw['relacao']})} |")
        w(f"\nQualidade antes: {len(pw['fracas'])} `fraca`, {pw['boas']} `boa`, "
          f"{len(pw['evento']) + len(pw['relacao']) - len(pw['fracas']) - pw['boas']} não avaliadas (NULL). Wiki `sustenta` depois: {pw['restantes']}.")
        w(f"Ligações `fraca` no banco: {fracas_depois + len(pw['fracas'])} -> {fracas_depois} (as wiki rebaixadas deixam de ser `fraca` por serem contexto; "
          "`validar.py` confere `FRACAS_RESTANTES_RODADA4` menos `FRACAS_REBAIXADAS_R6` menos as substituídas pela rodada 5 = `FRACAS_DEPOIS_RODADA5`).\n")
        if pw["fracas"]:
            w("| alvo | wiki que era `fraca` (agora `contexto`, qualidade NULL) |\n|---|---|")
            for alvo, dono, url in pw["fracas"]:
                w(f"| {alvo} `{dono}` | {url} |")
        if pw["relacao"]:
            w("\n| relação (origem_ref) | wiki rebaixada |\n|---|---|")
            for dono, url, _ in pw["relacao"]:
                ref = con.execute("SELECT origem || ' ' || origem_ref FROM relacao WHERE id=?", (dono,)).fetchone()[0]
                w(f"| `{ref}` | {url} |")

    # ---------------------------------------------------------------- 22
    r5 = [e for e in ea["entradas"] if e.get("rodada") == 5]
    if r5:
        subs5 = [e for e in r5 if e.get("substitui")]
        fracas_final = sum(curadoria._contar_fracas(con).values())
        w("\n## 22. Rodada 5: as últimas lacunas de fonte (`data/curadoria/evidencias-rodada5.json`)\n")
        w(f"{len(r5)} fontes novas (`boa`, papel `sustenta`) para {len({curadoria._chave_alvo(e) for e in r5})} alvos e "
          f"{len({curadoria.normalizar_url(e['url']) for e in r5})} URLs distintas (uma URL pode estar ligada a vários alvos: a matéria do Estadão sobre Caio Carvalho Barros está em "
          f"{max(collections.Counter(curadoria.normalizar_url(e['url']) for e in r5).values())} relações, com uma só `evidencia`). {len(subs5)} têm `substitui` (cscb.ca no evento de 2018; Brasil 247 em `N[138].fam_de`): a fraca recebe `substituida_por` em "
          "`evidencias-adicionais.json` e sai da ligação, como na rodada 4; as outras são fontes adicionais. Aplicadas por "
          "`curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, depois das rodadas 1-4) e conferidas por "
          "`curadoria.conferir_substituicoes`. "
          f"Ligações `fraca` no banco: {fracas_final + len(subs5) + len(pw.get('fracas', []))} -> {fracas_final} "
          "(depois da rodada 5: 0; as 2 wiki que sobravam já eram `contexto` pela R6). A natureza vem de `eventos-natureza.json`, regerado (R5). "
          "Detalhe em `relatorio-evidencias-adicionais.md`, seção \"Rodada 5\".\n")
        w("| natureza (todos os eventos) | eventos |\n|---|---:|")
        for r in q("SELECT COALESCE(natureza_id,'(NULL)') n, count(*) c FROM evento GROUP BY 1 ORDER BY 1"):
            w(f"| {r['n']} | {r['c']} |")

    # ---------------------------------------------------------------- 23
    secao_rodada6(con, R, w)
    secao_rodada7(con, R, w)


def secao_rodada7(con, R, w):
    """Seção 24: rodada 7 (ranking de lucros 1995-1997, Folha; ranking-empresa-correcoes-r7.json, aplicado depois da rodada 6)."""
    q = lambda s, *a: con.execute(s, a).fetchall()
    rk = R.get("ranking_corr7") or {}
    if not (rk.get("atualizadas") or rk.get("inseridas")):
        return
    cfg = curadoria.ler_json(curadoria.ARQ_RANKING_CORR_R7, {})
    w("\n## 24. Rodada 7: ranking de lucros de 1995-1997 com a Folha de S.Paulo\n")
    w("Arquivo à mão: `ranking-empresa-correcoes-r7.json` (mesmo formato da rodada 6, aplicado por `curadoria.aplicar_ranking_empresa_correcoes(con, ARQ_RANKING_CORR_R7)` "
      "logo depois dela; `gerar_curadoria.py` também o pula no banco temporário) e a entidade `telesp` em `entidades-adicionais.json`. Os `de` são os valores que a rodada 6 gravou; "
      "uma `anterior` que já estava em `ranking_evidencia` (Souza Cruz 1995) é reclassificada para `contexto` em vez de duplicada. "
      "Mesma base (lucro em R$ pela legislação societária) e mesmas regras de `posicao` e `pct_total` da rodada 6. "
      "**Telesp 1996** (subsidiária da Telebrás) foi inserida: o ranking já convive com holding e subsidiária no mesmo ano (Telebrás e Embratel em 1997; Itaúsa e Itaú Unibanco de 2010 a 2020), "
      "e a obs registra a dupla contagem.\n")
    w("| ano | empresa | o que mudou | fonte principal |\n|---|---|---|---|")
    princ = lambda a, e: q("SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)[0][0]
    for x in sorted(rk["inseridas"] + rk["atualizadas"], key=lambda x: (x["ano"], x["entidade_id"])):
        if "campos" in x:
            o = "; ".join(f"{k} {v['de']} -> {v['para']}" for k, v in x["campos"].items() if k != "obs") + ("; obs" if "obs" in x["campos"] else "")
            o = o.strip("; ") or "só fonte"
        else:
            o = f"**inserida** ({x['lucro_brl_bi']})"
        w(f"| {x['ano']} | `{x['entidade_id']}` | {o} | {princ(x['ano'], x['entidade_id'])} |")
    w("\nPosições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):\n")
    for a in sorted(rk["posicoes"]):
        w(f"- {a}: " + ", ".join(f"`{e}` {p0} -> {p1}" for e, p0, p1 in rk["posicoes"][a]))
    w(f"\n{rk['ligacoes']} ligações novas em `ranking_evidencia` ({len(rk['evid_novas'])} evidências novas). Lacunas registradas no arquivo: "
      + " ".join(f"({i + 1}) {t}" for i, t in enumerate(cfg.get("lacunas", []))) + "\n")


def secao_rodada6(con, R, w):
    """Seção 23: rodada 6 (ranking de empresas, mandatos, fatos novos, correções de texto e fontes)."""
    q = lambda s, *a: con.execute(s, a).fetchall()
    rk, ma, ea = R.get("ranking_corr") or {}, R.get("mandatos_adic") or {}, R.get("eventos_adic") or {}
    if not (rk.get("atualizadas") or rk.get("inseridas") or ma.get("inseridos") or ea.get("inseridos")):
        return
    cfg_rk = curadoria.ler_json("ranking-empresa-correcoes.json", {})
    w("\n## 23. Rodada 6: ranking de empresas, lideranças parlamentares e fatos de 2024\n")
    w("Arquivos à mão: `entidades-adicionais.json` (entidades novas, criadas no mesmo ponto das `entidades_novas` do dossiê: "
      + ", ".join(f"`{i}`" for i in R.get("entidades_adicionais", [])) + "), `ranking-empresa-correcoes.json` (`curadoria.aplicar_ranking_empresa_correcoes`), "
      "`mandatos-adicionais.json` (`aplicar_mandatos_adicionais` + `ligar_fontes_mandatos_adicionais`), `eventos-adicionais.json` (`aplicar_eventos_adicionais`), "
      "`evidencias-rodada6.json` (via `ler_evidencias_adicionais`, depois das rodadas 1-5) e as correções `\"rodada\": 6` de `evento-correcoes.json`. "
      "Regerados: `eventos-natureza.json` (R5), `evento-entidade-auto.json` e `mandato-oficial.json` (+ `relatorio-mandatos-oficial.md`); "
      "`gerar_curadoria.py` pula `ranking_correcoes` no banco temporário porque `gerar_complementos_brasil` casa as linhas com o bruto pela posição original.\n")
    w("### Ranking de empresas\n")
    w("Base do ranking: lucro líquido em R$ pela legislação societária (BR GAAP); US GAAP/Euromoney em US$ só como fonte de `contexto`. "
      "Fontes na tabela aditiva `ranking_evidencia` (papel, trecho, nota); `ranking_empresa.evidencia_id` = fonte principal. "
      "Nos anos tocados, `posicao` e `pct_total` foram recalculados com as regras da carga bruta (conferidas nas 397 linhas de `data/raw/brasil.json`): "
      "lucros em ordem decrescente e depois os prejuízos do maior para o menor; `pct_total = round(lucro / PIB do ano (macro.pib) * 100, 3)`.\n")
    w("| ano | cobertura | linhas | inseridas | atualizadas (valor) | só fontes/obs |\n|---|---|---:|---:|---:|---:|")
    anos = sorted({x["ano"] for x in rk["atualizadas"] + rk["inseridas"]} | {c[0] for c in rk["cobertura"]})
    for a in anos:
        cob = q("SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", a)[0][0]
        mud = next((f"{c[1]} -> {c[2]}" for c in rk["cobertura"] if c[0] == a), cob)
        at = [x for x in rk["atualizadas"] if x["ano"] == a]
        w(f"| {a} | {mud} | {q('SELECT count(*) FROM ranking_empresa WHERE ano=?', a)[0][0]} | {sum(1 for x in rk['inseridas'] if x['ano'] == a)} | "
          f"{sum(1 for x in at if 'lucro_brl_bi' in x['campos'])} | {sum(1 for x in at if 'lucro_brl_bi' not in x['campos'])} |")
    w("\n| ano | empresa | o que mudou | fonte principal |\n|---|---|---|---|")
    princ = lambda a, e: q("SELECT v.url FROM ranking_empresa k JOIN evidencia v ON v.id=k.evidencia_id WHERE k.ano=? AND k.entidade_id=?", a, e)[0][0]
    for x in sorted(rk["inseridas"] + rk["atualizadas"], key=lambda x: (x["ano"], x["entidade_id"])):
        if "campos" in x:
            partes = [f"{k} {v['de']} -> {v['para']}" for k, v in x["campos"].items() if k != "obs"] + (["obs"] if "obs" in x["campos"] else [])
            o = "; ".join(partes) or "só fontes"
        else:
            o = f"**inserida** ({x['lucro_brl_bi']})"
        w(f"| {x['ano']} | `{x['entidade_id']}` | {o} | {princ(x['ano'], x['entidade_id'])} |")
    w("\nPosições que mudaram (`entidade`: antes -> depois; as inseridas entram direto na posição final):\n")
    for a in sorted(rk["posicoes"]):
        w(f"- {a}: " + ", ".join(f"`{e}` {p0} -> {p1}" for e, p0, p1 in rk["posicoes"][a]))
    w(f"\n{rk['ligacoes']} ligações em `ranking_evidencia`; {len(rk['evid_novas'])} evidências novas. Lacunas registradas no arquivo: "
      + " ".join(f"({i + 1}) {t}" for i, t in enumerate(cfg_rk.get("lacunas", []))) + "\n")
    w("### Lideranças parlamentares (`mandatos-adicionais.json`)\n")
    mo = R.get("mandato_oficial", {}).get("resumo", {})
    w("| entidade | cargo | ano | partido/UF | motivo | evidência da linha |\n|---|---|---|---|---|---|")
    for mid, ent, ini in ma.get("inseridos", []):
        m = q("SELECT m.*, v.url FROM mandato m LEFT JOIN evidencia v ON v.id=m.evidencia_id WHERE m.id=?", mid)[0]
        w(f"| `{ent}` | {m['cargo']} | {ini} | {m['partido']}/{m['uf']} | {m['motivo']} | {m['url'] or 'sem API (sem fonte oficial)'} |")
    w(f"\nCada linha traz a fonte oficial do destaque ligada à relação `mandato:<id>` ({R.get('mandatos_adic_fontes', {}).get('ligacoes', 0)} ligações, "
      "inclusive na filiação das linhas sem API). Confronto com as APIs (`mandato-oficial.json`): "
      f"{mo.get('mandatos_no_banco')} linhas, {mo.get('confirmados')} confirmadas, {mo.get('divergentes')} divergentes, {mo.get('sem_fonte_oficial')} sem fonte oficial "
      "(as linhas de pessoa fora da coleta das APIs entram em `sem_fonte`). Pendências: "
      + " ".join(f"{p['nome']} ({p['ano']}): {p['motivo']}" for p in curadoria.ler_json("mandatos-adicionais.json", {}).get("pendencias", [])) + "\n")
    w("### Fatos novos e correções de texto\n")
    for i in ea.get("inseridos", []):
        r = q("SELECT titulo, natureza_id, peso, origem_ref FROM evento WHERE id=?", i)[0]
        w(f"- `{i}` ({r['origem_ref']}, peso {r['peso']}, {r['natureza_id']}): {r['titulo']}")
    for c in [c for c in curadoria.ler_json("evento-correcoes.json", {}).get("correcoes", []) if c.get("rodada") == 6]:
        w(f"- correção `{c['evento_id']}` ({c['campo']}): \"{c['de']}\" -> \"{c['para']}\"")
    w("\nBancadas: não alteradas (a tabela acadêmica da Câmara não substitui a carga; o snapshot oficial do Senado em 2000 traz blocos, não os 81 nomes; "
      "não há linhas de bancada do Senado 1995-1998 no banco e a aproximação da pesquisa não foi usada).\n")


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
        ("relacao (origem linha_do_tempo: mandato/filiação)", "SELECT count(*) FROM relacao WHERE origem='linha_do_tempo'"),
        ("relacao total", "SELECT count(*) FROM relacao"), ("evento total", "SELECT count(*) FROM evento"),
        ("tema", "SELECT count(*) FROM tema"), ("relacao_tema", "SELECT count(*) FROM relacao_tema"), ("evento_tema", "SELECT count(*) FROM evento_tema"),
        ("fonte (era video)", "SELECT count(*) FROM fonte"),
        ("evidencia", "SELECT count(*) FROM evidencia"), ("relacao_evidencia", "SELECT count(*) FROM relacao_evidencia"),
        ("evento_evidencia", "SELECT count(*) FROM evento_evidencia"), ("evento_entidade", "SELECT count(*) FROM evento_entidade"),
        ("nota", "SELECT count(*) FROM nota"), ("indicador", "SELECT count(*) FROM indicador"), ("serie", "SELECT count(*) FROM serie"),
        ("ranking_empresa", "SELECT count(*) FROM ranking_empresa"), ("mandato", "SELECT count(*) FROM mandato"),
        ("bancada", "SELECT count(*) FROM bancada"), ("entidade_valor", "SELECT count(*) FROM entidade_valor")]
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
    w(f"\nSituação na carga bruta, antes da curadoria (seções 9 e 10 dizem o que mudou). Os eventos da timeline Brasil (`brasil`) e os marcos legais (`violencia`) nunca tiveram `st`; os da teia são os 92 abaixo "
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
    w("- Eventos da timeline Brasil (280): `data` = ano do agrupamento, canal `brasil` (subcanal `pol`/`intl` em `origem_ref`); na carga bruta sem fonte e sem natureza (as fontes entram pela curadoria, seção 11).")
    w(f"- `pares.notas`: linhas de log de coleta descartadas ({len(R['pares_notas_descartadas'])}): " + "; ".join(f"\"{t}\"" for t in R["pares_notas_descartadas"]))
    w("- `pares.indicadores`: valores `null` explícitos (ex.: IDH) não viram linha em `serie`; só os pontos não nulos.")
    w("- `pares.foruns` e as seções estruturadas do dossiê (mercado, previdência, dinheiro, limites, máquina) deixaram de ir para `nota.texto`: viraram tabelas relacionais (seção 13); a seção `brb.eventos` virou 30 eventos canal `brb`.")
    w("- URLs dentro de `nota.texto` do dossiê (`previdencia.fonte`, `dinheiro.fonte`) não passam por `evidencia`; as fontes de `mercado.pares` e `brb.eventos` passam.")
    w("- `mandato`: presidentes/vices/presidentes das casas são agregados por anos consecutivos (granularidade de ano; Dilma/Temer em 2016 usam 12/5); `partido` = valor do primeiro ano do período. Parlamentares em destaque (`pol.parl`) viram `mandato` de um ano (`inicio=fim=ano`) com `motivo` e `votos`.")
    w("- `ranking_empresa.posicao` = posição na lista do ano (a lista original não traz posição explícita).")
    w("- Países em `pares` viram entidades `pais` (alias sigla = ISO3); `serie.dimensao` usa `pais=<ISO3>`. Destinos de exportação usam `pais=<nome>` (sem ISO na fonte).")
    w("- `serie` de pares = pontos não nulos dos 18 indicadores (4.806) + PISA (leitura/matemática/ciências e matemática por estado da Índia).")
    w("- Desvios do DDL proposto (marcados `-- DESVIO:` em `scripts/schema.sql`): o DDL original roda sem erro no SQLite 3.45 (incl. STRICT, colunas geradas e FTS5); "
      "acrescentados `entidade.ind_legado`, `evento.valor_brl`, `evento.canal='brb'`, `evento.origem='dossie'`, `ordem` em `relacao_evidencia`/`evento_evidencia`/`evento_entidade`/`nota_entidade`, "
      "`mandato.motivo`/`mandato.votos`; `evento.contexto`/`resposta` passam a significar o que os dados dizem (ver acima). Rodada de modelo (seções 14 a 16): "
      "`tema`/`relacao_tema`/`evento_tema`/`v_entidade_tema`, `fonte` no lugar de `video` (e `trecho.fonte_id`), `relacao.origem='linha_do_tempo'`.")
    w("- Passo 3 do plano (ligar eventos a entidades por alias): feito pela curadoria, seção 12. Continua não feita a extração de eventos a partir de datas internas de `N.d`/`desc`.")
    w("- `evento_evidencia.rotulo` (desvio) guarda o rótulo da fonte como veio no original; `evidencia.veiculo` guarda só o do primeiro uso da URL. O exportador usa o rótulo.")
    for a in R["aviso"]:
        w(f"- AVISO: {a}")
    secoes_curadoria(con, R, w)
    secoes_modelo(con, R, w)
    (DATA / "relatorio-migracao.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
