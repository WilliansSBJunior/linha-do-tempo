"""Curadoria: aplica os arquivos de data/curadoria/ ao banco depois da carga bruta e contém as regras que os geram.

migrar.py chama as funções `aplicar_*`; gerar_curadoria.py chama as funções `gerar_*` e escreve os JSON.
Só stdlib. Nada aqui edita o banco fora de migrar.py (que recria o banco do zero a cada execução).
"""
import collections
import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from comum import CURADORIA, DATA, RAW, ROOT, TS_MIGRACAO, dominio_de, normalizar_url
from slug import alias_norm, sem_acento


def ler_json(nome, padrao=None):
    p = CURADORIA / nome
    if not p.exists():
        return padrao
    return json.loads(p.read_text(encoding="utf-8"))


def salvar_json(nome, obj):
    CURADORIA.mkdir(exist_ok=True)
    (CURADORIA / nome).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ======================================================================== 1. fusões de eventos
CAMPOS_EVENTO = ["id", "titulo", "descricao", "data", "data_aprox", "data_texto", "natureza_id", "peso", "canal", "contexto",
                 "resposta", "valor_brl", "origem", "origem_ref"]


def snapshot_evento(con, eid):
    """Evento como está agora: colunas, fontes [rótulo, url, papel, ordem] e entidades [id, papel, ordem]."""
    r = con.execute(f"SELECT {','.join(CAMPOS_EVENTO)} FROM evento WHERE id=?", (eid,)).fetchone()
    d = {c: r[c] for c in CAMPOS_EVENTO}
    d["fontes"] = [[x["rotulo"] if x["rotulo"] is not None else x["veiculo"], x["url"], x["papel"], x["ordem"]] for x in con.execute(
        """SELECT x.rotulo, e.veiculo, e.url, x.papel, x.ordem FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id
           WHERE x.evento_id=? ORDER BY x.ordem""", (eid,))]
    d["entidades"] = [[x["entidade_id"], x["papel"], x["ordem"]] for x in con.execute(
        "SELECT entidade_id, papel, ordem FROM evento_entidade WHERE evento_id=? ORDER BY ordem", (eid,))]
    return d


def aplicar_fusoes(con):
    """Funde os eventos de eventos-fusoes.json. Retorna lista de dicts para o relatório."""
    fusoes = ler_json("eventos-fusoes.json", [])
    peso_nat = {r["id"]: r["peso"] for r in con.execute("SELECT id, peso FROM natureza")}
    usados, saida = set(), []
    for f in fusoes:
        manter, fundir = f["manter"], list(f["fundir"])
        ids = [manter] + fundir
        assert len(set(ids)) == len(ids), f"fusão com id repetido: {ids}"
        assert not (set(ids) & usados), f"id em duas fusões: {set(ids) & usados}"
        usados |= set(ids)
        snaps = {}
        for i in ids:
            assert con.execute("SELECT 1 FROM evento WHERE id=?", (i,)).fetchone(), f"evento inexistente na fusão: {i}"
            snaps[i] = snapshot_evento(con, i)
        datas = {snaps[i]["data"] for i in ids}
        assert len(datas) == 1, f"fusão com datas diferentes {datas}: {ids}"
        sm = snaps[manter]
        # natureza: a mais forte entre os que têm; peso: máximo
        nats = [snaps[i]["natureza_id"] for i in ids if snaps[i]["natureza_id"]]
        natureza = max(nats, key=lambda n: peso_nat[n]) if nats else None
        pesos = [snaps[i]["peso"] for i in ids if snaps[i]["peso"] is not None]
        campos = {"natureza_id": natureza, "peso": max(pesos) if pesos else None}
        for c in ("descricao", "contexto", "resposta", "valor_brl"):
            if sm[c] in (None, ""):
                outros = [snaps[i][c] for i in fundir if snaps[i][c] not in (None, "")]
                campos[c] = outros[0] if outros else sm[c]
        con.execute("UPDATE evento SET natureza_id=:natureza_id, peso=:peso, descricao=:descricao, contexto=:contexto, resposta=:resposta, valor_brl=:valor_brl WHERE id=:id",
                    {**{c: sm[c] for c in ("descricao", "contexto", "resposta", "valor_brl")}, **campos, "id": manter})
        # fontes (união, ordem: mantido primeiro) e entidades (união)
        ev_ja = {r[0] for r in con.execute("SELECT evidencia_id FROM evento_evidencia WHERE evento_id=?", (manter,))}
        ordem = len(ev_ja)
        n_fontes_novas = 0
        for i in fundir:
            for x in con.execute("SELECT evidencia_id, papel, rotulo FROM evento_evidencia WHERE evento_id=? ORDER BY ordem", (i,)).fetchall():
                if x["evidencia_id"] in ev_ja:
                    continue
                con.execute("INSERT INTO evento_evidencia(evento_id,evidencia_id,papel,ordem,rotulo) VALUES(?,?,?,?,?)",
                            (manter, x["evidencia_id"], x["papel"], ordem, x["rotulo"]))
                ev_ja.add(x["evidencia_id"])
                ordem += 1
                n_fontes_novas += 1
        en_ja = {r[0] for r in con.execute("SELECT entidade_id FROM evento_entidade WHERE evento_id=?", (manter,))}
        ordem = len(en_ja)
        n_ents_novas = 0
        for i in fundir:
            for x in con.execute("SELECT entidade_id, papel FROM evento_entidade WHERE evento_id=? ORDER BY ordem", (i,)).fetchall():
                if x["entidade_id"] in en_ja:
                    continue
                con.execute("INSERT INTO evento_entidade(evento_id,entidade_id,papel,ordem) VALUES(?,?,?,?)", (manter, x["entidade_id"], x["papel"], ordem))
                en_ja.add(x["entidade_id"])
                ordem += 1
                n_ents_novas += 1
        for i in fundir:
            for x in con.execute("SELECT relacao_id, papel FROM evento_relacao WHERE evento_id=?", (i,)).fetchall():
                con.execute("INSERT OR IGNORE INTO evento_relacao(evento_id,relacao_id,papel) VALUES(?,?,?)", (manter, x["relacao_id"], x["papel"]))
            s = snaps[i]
            con.execute("INSERT INTO evento_alias(alias,evento_id,motivo,canal_original,origem_ref_original,original_json) VALUES(?,?,?,?,?,?)",
                        (i, manter, f["motivo"], s["canal"], s["origem_ref"], json.dumps(s, ensure_ascii=False, sort_keys=True)))
            con.execute("DELETE FROM evento WHERE id=?", (i,))
        saida.append({"manter": manter, "fundir": fundir, "data": sm["data"], "natureza": natureza, "peso": campos["peso"],
                      "fontes_novas": n_fontes_novas, "entidades_novas": n_ents_novas, "motivo": f["motivo"],
                      "titulos": {i: snaps[i]["titulo"] for i in ids}, "canais": {i: snaps[i]["canal"] for i in ids}})
    return saida


# ======================================================================== 2. natureza dos eventos da teia sem st
DOMINIOS_OFICIAIS_SUFIXO = (".gov.br", ".jus.br", ".leg.br")
DOMINIOS_OFICIAIS_EXATOS = {"gov.br", "okai.com.br"}


def fonte_oficial(url):
    h = dominio_de(url)
    if h in DOMINIOS_OFICIAIS_EXATOS or h.endswith(DOMINIOS_OFICIAIS_SUFIXO):
        return True
    # PDFs hospedados pelo Poder360 são cópias de decisões, votos e relatórios (static.poder360.com.br/uploads/...)
    return h == "static.poder360.com.br" and url.lower().split("?")[0].endswith(".pdf")


VERBOS_AUTORIDADE = [
    r"(bc|banco central) (liquida|decreta|veta|rejeita|aprova|nega|autoriza)",
    r"(stf|plenario do stf|supremo) (torna publica|decide|julga|suspende|homologa)",
    r"pf prende",
    r"justica (homologa|nega|decreta|reconhece|afasta|bloqueia)",
    r"cvm (multa|condena)",
    r"(camara|senado|cldf|congresso) (aprova|rejeita|promulga)",
    r"(mendonca|toffoli|fachin|dino|moraes|gilmar|nunes marques|fux|zanin) (autoriza|afasta|levanta|tira|suspende|determina|manda|concede|nega|decreta|homologa)",
]
INVESTIGACAO = [r"\bpf (aponta|diz|suspeita)\b", r"\brelatorio da pf\b", r"\bindicia", r"\balvos?\b", r"\bbuscas?\b", r"\bdenuncia\w*"]
REPORTADA = [r"^folha liga\b", r"\brevelad[oa]s?\b", r"\bmensagens\b", r"\bteria\b", r"\bsegundo\b"]
REGRAS_NATUREZA_TEXTO = """\
R1  todas as fontes do evento são documento oficial (domínios .gov.br/gov.br, .jus.br, .leg.br, okai.com.br; PDFs em static.poder360.com.br) -> documentada
R2  o título começa por verbo de autoridade sobre ato formal consumado (BC liquida/decreta/veta/rejeita/aprova/nega/autoriza; STF torna pública/decide/julga/suspende/homologa;
    PF prende; Justiça homologa/nega/decreta/reconhece/afasta/bloqueia; CVM multa/condena; Câmara/Senado/CLDF/Congresso aprova/rejeita/promulga;
    Mendonça/Toffoli/Fachin/Dino/Moraes/Gilmar/Nunes Marques/Fux/Zanin autoriza/afasta/levanta/tira/suspende/determina/manda/concede/nega/decreta/homologa)
    e há 2 ou mais fontes de imprensa (ato público noticiado por 2+ veículos) -> documentada
R3  o título tem 'PF aponta/diz/suspeita', 'relatório da PF', 'indicia', 'alvo(s)', 'busca(s)' ou 'denúncia/denuncia(r)' -> investigacao
R4  o título começa por 'Folha liga' ou tem 'revelado/revelada', 'mensagens', 'teria', 'segundo' -> reportada
--  nenhuma das anteriores: continua NULL (nada é inventado)
Precedência: R1, R2, R3, R4. R1-R4 só se aplicam a eventos do canal 'teia' com natureza_id NULL.
R5  (canais 'brasil' e 'violencia', eventos factuais da linha do tempo; olha o tipo e o domínio das evidências ligadas ao evento com papel 'sustenta'):
    ao menos uma evidência documento_oficial/dado_oficial/decisao_judicial/comunicado (ou domínio oficial pela lista de R1; `comunicado` = nota de órgão público, como press release do Fed ou da ONU, desde a rodada 3) -> documentada;
    senão, ao menos uma reportagem/relatorio -> reportada;
    senão (só wiki/outro/video, só fonte de papel 'contexto' ou nenhuma fonte) -> nao_classificada.
    Fontes 'contexto' (as URLs do bloco-ano de brasil-fontes.json, que o bruto não separa por evento) NÃO contam: não sustentam o fato do evento.
    Muda-se isso em R5_PAPEIS.
R6  (global; data/curadoria/regras-fontes.json, decisão do dono do projeto de 18/10/2026): fonte Wikipédia (evidencia.tipo 'wiki' ou domínio
    *.wikipedia.org) nunca tem papel 'sustenta'; em evento_evidencia e relacao_evidencia é sempre 'contexto' (qualidade NULL: contexto não é
    avaliado). Aplicada por aplicar_peso_wikipedia depois de todas as cargas de evidência e antes de gerar a natureza: a wiki não conta em R5,
    nem no 'Fontes (n)' das páginas, e é exportada por último. Nenhum evento ou relação pode depender só de wiki (a migração aborta).
M   os eventos da teia que R1-R4 não pegam foram lidos um a um (título, descrição, fontes) e classificados à mão em data/curadoria/eventos-natureza-manual.json
    ([{"id","natureza","justificativa"}]), aplicado depois do gerado e só onde natureza_id IS NULL; entrada com "natureza": null é exceção explícita
    (fica NULL, a justificativa é obrigatória)."""


def classificar_natureza(titulo, urls):
    """-> (natureza, regra) ou (None, None). urls: URLs normalizadas das fontes do evento."""
    t = alias_norm(titulo)
    oficiais = [fonte_oficial(u) for u in urls]
    n_imprensa = sum(1 for o in oficiais if not o)
    if urls and all(oficiais):
        return "documentada", f"R1: {len(urls)} fonte(s), todas documento oficial"
    for padrao in VERBOS_AUTORIDADE:
        m = re.match(padrao, t)
        if m and n_imprensa >= 2:
            return "documentada", f"R2: verbo de autoridade '{m.group(0)}' e {n_imprensa} fontes de imprensa"
    for padrao in INVESTIGACAO:
        m = re.search(padrao, t)
        if m:
            return "investigacao", f"R3: título com '{m.group(0)}'"
    for padrao in REPORTADA:
        m = re.search(padrao, t)
        if m:
            return "reportada", f"R4: título com '{m.group(0)}'"
    return None, None


R5_PAPEIS = ("sustenta",)
R5_TIPOS_OFICIAIS = ("documento_oficial", "dado_oficial", "decisao_judicial", "comunicado")
R5_TIPOS_IMPRENSA = ("reportagem", "relatorio")


def classificar_natureza_r5(evidencias):
    """evidencias: [(tipo, url, papel)] ligadas ao evento -> (natureza, regra). Sempre devolve algo."""
    ev = [(t, u) for t, u, p in evidencias if p in R5_PAPEIS]
    ctx = len(evidencias) - len(ev)
    oficiais = [(t, u) for t, u in ev if t in R5_TIPOS_OFICIAIS or fonte_oficial(u)]
    if oficiais:
        return "documentada", f"R5: {len(oficiais)} de {len(ev)} fonte(s) que sustentam o evento são oficiais (tipo {oficiais[0][0]}, {dominio_de(oficiais[0][1])})"
    imp = [(t, u) for t, u in ev if t in R5_TIPOS_IMPRENSA]
    if imp:
        return "reportada", f"R5: sem fonte oficial; {len(imp)} de {len(ev)} fonte(s) que sustentam o evento são reportagem/relatório"
    return "nao_classificada", f"R5: nenhuma fonte reportagem/relatório/oficial sustenta o evento ({len(ev)} de sustentação, {ctx} só de contexto)"


def gerar_natureza_r5(con):
    out = []
    for r in con.execute("SELECT id FROM evento WHERE canal IN ('brasil','violencia') AND natureza_id IS NULL ORDER BY data, id"):
        evs = [(x[0], x[1], x[2]) for x in con.execute(
            "SELECT e.tipo, e.url, x.papel FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=? ORDER BY x.ordem", (r["id"],))]
        nat, regra = classificar_natureza_r5(evs)
        out.append({"id": r["id"], "natureza": nat, "regra": regra})
    return out


def gerar_natureza(con):
    """Para cada evento da teia ainda sem natureza, aplica as regras ao título do evento e aos títulos originais dos eventos
    fundidos nele (evento_alias), com a união das fontes; vale a natureza mais forte."""
    peso = {r["id"]: r["peso"] for r in con.execute("SELECT id, peso FROM natureza")}
    out = []
    for r in con.execute("SELECT id, titulo FROM evento WHERE canal='teia' AND natureza_id IS NULL ORDER BY data, id"):
        urls = [x[0] for x in con.execute("SELECT e.url FROM evento_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.evento_id=? ORDER BY x.ordem", (r["id"],))]
        titulos = [(r["titulo"], "")] + [(json.loads(a[0])["titulo"], " (título de evento fundido)")
                                          for a in con.execute("SELECT original_json FROM evento_alias WHERE evento_id=? ORDER BY alias", (r["id"],))]
        melhor = None
        for t, nota in titulos:
            nat, regra = classificar_natureza(t, urls)
            if nat and (melhor is None or peso[nat] > peso[melhor[0]]):
                melhor = (nat, regra + nota)
        if melhor:
            out.append({"id": r["id"], "natureza": melhor[0], "regra": melhor[1]})
    return out + gerar_natureza_r5(con)


def aplicar_natureza(con):
    itens = ler_json("eventos-natureza.json", [])
    aplicados = ignorados = 0
    aplic_regra = collections.Counter()
    for it in itens:
        cur = con.execute("UPDATE evento SET natureza_id=? WHERE id=? AND natureza_id IS NULL", (it["natureza"], it["id"]))
        aplicados += cur.rowcount
        ignorados += 1 - cur.rowcount
        if cur.rowcount:
            aplic_regra[it["regra"].split(":")[0]] += 1
    manual = ler_json("eventos-natureza-manual.json", [])
    man_aplic = man_ign = 0
    por_nat_manual = collections.Counter()
    for it in manual:
        if it.get("natureza") is None:
            continue   # exceção explícita: fica NULL
        cur = con.execute("UPDATE evento SET natureza_id=? WHERE id=? AND natureza_id IS NULL", (it["natureza"], it["id"]))
        man_aplic += cur.rowcount
        man_ign += 1 - cur.rowcount
        if cur.rowcount:
            por_nat_manual[it["natureza"]] += 1
    return {"arquivo": len(itens), "aplicados": aplicados, "ignorados": ignorados,
            "por_regra": collections.Counter(i["regra"].split(":")[0] for i in itens),
            "por_natureza": collections.Counter(i["natureza"] for i in itens),
            "aplicados_por_regra": aplic_regra,
            "manual": {"arquivo": len(manual), "aplicados": man_aplic, "ignorados": man_ign, "por_natureza": por_nat_manual,
                       "excecoes": sum(1 for i in manual if i.get("natureza") is None)}}


# ======================================================================== 3. fontes da timeline Brasil
STOP_PT = set("de da do dos das e a o as os em no na nos nas por para com ao que um uma se sua seu pelo pela ou como mais apos sobre entre ate sem".split())
GENERICOS_URL = set("http https www wikipedia org wiki pt en com br gov html htm index php amp noticias noticia news article articles materias materia "
                    "politica economia mundo brasil brazil no in the of and de da do ccivil 03 legislacao".split())


def blocos_eventos(bruto):
    """(ano, secao) -> lista de itens {bloco, ano, i, titulo, descricao, fontes} dos blocos de eventos do bruto."""
    itens = collections.defaultdict(list)
    for bloco, v in bruto.items():
        if not isinstance(v, dict) or "anos" not in v:
            continue
        if bloco.startswith("v2_pol_eventos") or bloco.startswith("v4_pol"):
            sec = "pol"
        elif "intl_eventos" in bloco:
            sec = "intl"
        else:
            continue
        for ano, y in v["anos"].items():
            for i, e in enumerate(y.get("eventos") or []):
                itens[(ano, sec)].append({"bloco": bloco, "ano": ano, "i": i, "titulo": e["titulo"], "descricao": e["descricao"],
                                          "fontes": y.get("fontes") or []})
    return itens


def tokens_texto(s, minimo=4):
    return {t for t in alias_norm(s).split() if len(t) >= minimo and t not in STOP_PT and not t.isdigit()}


def tokens_url(url):
    p = urlsplit(url)
    path = sem_acento(unquote(p.path)).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", path) if t]
    return [t for t in toks if t not in GENERICOS_URL and not t.isdigit() and len(t) >= 3]


def url_toca_evento(url, titulo, descricao):
    """Heurística conservadora: algum termo distintivo da URL (slug) aparece no título/descrição do evento."""
    ut = tokens_url(url)
    if not ut:
        return False
    ev = tokens_texto(f"{titulo} {descricao or ''}", 4)
    comum = [t for t in ut if t in ev and len(t) >= 4]
    return bool(comum) and len(comum) / len(ut) >= 0.34


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


def gerar_fontes_brasil(con, bruto):
    """Casa cada evento 'brasil' com o item do bruto (mesmo ano e seção; título igual ou Jaccard >= 0,6)."""
    itens = blocos_eventos(bruto)
    saida, sem = [], []
    for r in con.execute("SELECT id, titulo, descricao, ano, origem_ref FROM evento WHERE canal='brasil' ORDER BY id"):
        m = re.fullmatch(r"Y\[(\d+)\]\.(pol|intl)\.eventos\[(\d+)\]", r["origem_ref"])
        ano, sec = m.group(1), m.group(2)
        cands = itens.get((ano, sec), [])
        iguais = [c for c in cands if c["titulo"] == r["titulo"]]
        metodo = "título igual"
        if not iguais:
            tr = tokens_texto(r["titulo"], 3)
            pontos = [(jaccard(tr, tokens_texto(c["titulo"], 3)), c) for c in cands]
            pontos = [(j, c) for j, c in pontos if j >= 0.6]
            if pontos:
                melhor = max(j for j, _ in pontos)
                iguais = [c for j, c in pontos if j == melhor]
                metodo = f"Jaccard {melhor:.2f}"
        if not iguais:
            sem.append(r["id"])
            continue
        urls, vistos = [], set()
        for c in iguais:
            for u in c["fontes"]:
                n = normalizar_url(u)
                if n not in vistos:
                    vistos.add(n)
                    urls.append(n)
        sus = [u for u in urls if url_toca_evento(u, r["titulo"], r["descricao"])]
        ctx = [u for u in urls if u not in sus]
        saida.append({"evento_id": r["id"], "bruto": [f"{c['bloco']}/{c['ano']}/eventos[{c['i']}]" for c in iguais], "casamento": metodo,
                      "sustenta": sus, "contexto": ctx})
    return saida, sem


def aplicar_fontes_brasil(con, evid):
    itens = ler_json("brasil-fontes.json", [])
    n_ev = n_lig = n_sus = n_ctx = n_ign = 0
    for it in itens:
        if not con.execute("SELECT 1 FROM evento WHERE id=?", (it["evento_id"],)).fetchone():
            n_ign += 1
            continue
        n_ev += 1
        ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM evento_evidencia WHERE evento_id=?", (it["evento_id"],)).fetchone()[0]
        for papel, urls in (("sustenta", it["sustenta"]), ("contexto", it["contexto"])):
            for u in urls:
                eid = evid(u)
                cur = con.execute("INSERT OR IGNORE INTO evento_evidencia(evento_id,evidencia_id,papel,ordem,rotulo) VALUES(?,?,?,?,NULL)",
                                  (it["evento_id"], eid, papel, ordem))
                if cur.rowcount:
                    ordem += 1
                    n_lig += 1
                    n_sus += papel == "sustenta"
                    n_ctx += papel == "contexto"
    return {"eventos": n_ev, "ligacoes": n_lig, "sustenta": n_sus, "contexto": n_ctx, "ignorados": n_ign}


# ---- complementos do bruto: receita das empresas e períodos de mandato
def gerar_complementos_brasil(con, bruto, brasil):
    # receita: ranking_empresa (ano, posicao) <-> brasil.json Y[ano].empresas[posicao-1] <-> item do bruto (ano, lucro, fonte|nome)
    brutas = collections.defaultdict(list)
    for bloco, v in bruto.items():
        if "_emp_" in bloco:
            for ano, y in v["anos"].items():
                for sec in ("empresas", "maiores_prejuizos"):
                    for e in y.get(sec) or []:
                        brutas[ano].append((bloco, e))
    receita, ambiguos, sem_receita = [], [], 0
    for r in con.execute("SELECT ano, entidade_id, posicao, lucro_brl_bi FROM ranking_empresa ORDER BY ano, posicao"):
        pub = brasil["Y"][str(r["ano"])]["empresas"][r["posicao"] - 1]
        assert pub["lucro"] == r["lucro_brl_bi"], (r["ano"], r["posicao"], pub["nome"])
        cands = [(b, e) for b, e in brutas[str(r["ano"])]
                 if e["lucro_liquido_brl_bi"] == pub["lucro"] and (e["fonte"] == pub["fonte"] or alias_norm(e["nome"]) == alias_norm(pub["nome"]))]
        vals = {e["receita_liquida_brl_bi"] for _, e in cands if e["receita_liquida_brl_bi"] is not None}
        if len(vals) == 1:
            receita.append({"ano": r["ano"], "entidade_id": r["entidade_id"], "receita_brl_bi": vals.pop(),
                            "bruto": sorted({f"{b}/{e['nome']}" for b, e in cands if e["receita_liquida_brl_bi"] is not None})})
        elif len(vals) > 1:
            ambiguos.append({"ano": r["ano"], "entidade_id": r["entidade_id"], "valores": sorted(vals)})
        else:
            sem_receita += 1
    # períodos: mandato (presidente_camara/senado) <-> pol_estrutura/presidencias do bruto por nome e ano
    por_ano = collections.defaultdict(list)  # (ano, cargo) -> [(nome_norm, periodo)]
    est = bruto["v2_pol_estrutura"]["anos"]
    for ano, y in est.items():
        for chave, cargo in (("presidente_camara", "presidente_camara"), ("presidente_senado", "presidente_senado")):
            for p in y.get(chave) or []:
                por_ano[(int(ano), cargo)].append((alias_norm(p["nome"]), p["periodo"]))
    for ano, y in bruto["v4_estrutura"]["presidencias"].items():
        for chave in ("presidente_camara", "presidente_senado"):
            for p in y.get(chave) or []:
                por_ano[(int(ano), chave)].append((alias_norm(p["nome"]), p["periodo"]))
    nomes = collections.defaultdict(set)
    for r in con.execute("SELECT entidade_id, alias_norm FROM entidade_alias"):
        nomes[r["entidade_id"]].add(r["alias_norm"])
    periodos, sem_periodo = [], []
    for m in con.execute("SELECT entidade_id, cargo, inicio, fim FROM mandato WHERE cargo IN ('presidente_camara','presidente_senado') ORDER BY id"):
        textos = []
        for ano in range(int(m["inicio"]), int(m["fim"]) + 1):
            for nn, per in por_ano.get((ano, m["cargo"]), []):
                if nn in nomes[m["entidade_id"]] and per not in textos:
                    textos.append(per)
        if textos:
            periodos.append({"entidade_id": m["entidade_id"], "cargo": m["cargo"], "inicio": m["inicio"], "fim": m["fim"], "periodo_texto": " | ".join(textos)})
        else:
            sem_periodo.append((m["entidade_id"], m["cargo"], m["inicio"], m["fim"]))
    return {"receita": receita, "mandato_periodo": periodos,
            "_descartes": {"receita_ambigua": ambiguos, "empresas_sem_receita_no_bruto": sem_receita, "mandatos_sem_periodo": sem_periodo}}


def aplicar_complementos_brasil(con):
    c = ler_json("brasil-complementos.json", {"receita": [], "mandato_periodo": []})
    n_r = n_m = 0
    for r in c["receita"]:
        n_r += con.execute("UPDATE ranking_empresa SET receita_brl_bi=? WHERE ano=? AND entidade_id=? AND receita_brl_bi IS NULL",
                           (r["receita_brl_bi"], r["ano"], r["entidade_id"])).rowcount
    for m in c["mandato_periodo"]:
        n_m += con.execute("UPDATE mandato SET periodo_texto=? WHERE entidade_id=? AND cargo=? AND inicio=? AND fim=?",
                           (m["periodo_texto"], m["entidade_id"], m["cargo"], m["inicio"], m["fim"])).rowcount
    return {"receita": n_r, "mandato_periodo": n_m, "descartes": c.get("_descartes", {})}


# ======================================================================== 4. evento <-> entidade por alias
def _tokens(texto):
    """[(original, normalizado)] para tokens alfanuméricos."""
    return [(m.group(0), sem_acento(m.group(0)).lower()) for m in re.finditer(r"[0-9A-Za-zÀ-ÿ]+", texto)]


def regras_ligacao():
    return ler_json("evento-entidade-regras.json", {})


def indice_aliases(con, regras):
    """alias_norm -> (entidade_id, tipo_entidade, alias_original, tipo_alias) só para alias_norm único no banco."""
    por_norm = collections.defaultdict(list)
    for r in con.execute("""SELECT a.alias, a.alias_norm, a.entidade_id, a.tipo_alias, e.tipo FROM entidade_alias a
                            JOIN entidade e ON e.id=a.entidade_id ORDER BY a.alias_norm, a.entidade_id"""):
        por_norm[r["alias_norm"]].append((r["entidade_id"], r["tipo"], r["alias"], r["tipo_alias"]))
    excl_ent = set(regras.get("excluir_entidades", []))
    indice = {}
    for n, v in por_norm.items():
        if len({x[0] for x in v}) != 1 or v[0][0] in excl_ent:
            continue
        indice[tuple(n.split())] = v[0]
    return indice


def casar_texto(texto, indice, regras):
    """-> [(entidade_id, alias_original)] na ordem de aparição, palavra inteira, mais longo primeiro, sem sobreposição."""
    toks = _tokens(texto)
    norm = [n for _, n in toks]
    maxlen = max(len(k) for k in indice) if indice else 1
    ok1 = set(regras.get("pessoa_um_token_ok", []))
    amb = set(regras.get("sobrenomes_ambiguos", []))
    excl1 = set(regras.get("excluir_alias_um_token", []))
    maiuscula = set(regras.get("exigir_inicial_maiuscula", []))
    nao_antes = regras.get("nao_precedido_por", {})
    nao_depois = regras.get("nao_seguido_por", {})
    achados, i = [], 0
    while i < len(toks):
        achou = False
        for n in range(min(maxlen, len(toks) - i), 0, -1):
            chave = tuple(norm[i:i + n])
            hit = indice.get(chave)
            if not hit:
                continue
            ent, tipo, alias, tipo_alias = hit
            ch = " ".join(chave)
            if n == 1:
                if ch in amb or ch in excl1:
                    continue
                if tipo == "pessoa" and ch not in ok1:
                    continue
                orig = toks[i][0]
                # siglas ('PT', 'PL', 'STF'): só em maiúsculas e não seguidas de número ('PL 2338')
                sigla = tipo_alias == "sigla" or alias.isupper()
                if sigla and not orig.isupper():
                    continue
                if sigla and i + 1 < len(toks) and toks[i + 1][1].isdigit():
                    continue
            if ch in maiuscula and not toks[i][0][0].isupper():
                continue
            if i > 0 and norm[i - 1] in nao_antes.get(ch, []):
                continue
            if i + n < len(toks) and norm[i + n] in nao_depois.get(ch, []):
                continue
            achados.append((ent, alias))
            i += n
            achou = True
            break
        if not achou:
            i += 1
    vistos, saida = set(), []
    for ent, alias in achados:
        if ent not in vistos:
            vistos.add(ent)
            saida.append((ent, alias))
    return saida


def gerar_ligacoes(con):
    regras = regras_ligacao()
    indice = indice_aliases(con, regras)
    saida = []
    for r in con.execute("""SELECT id, titulo, descricao FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_entidade x WHERE x.evento_id=e.id)
                            ORDER BY canal, data, id"""):
        achados = casar_texto(f"{r['titulo']}. {r['descricao'] or ''}", indice, regras)
        if achados:
            saida.append({"evento_id": r["id"], "entidades": [{"id": e, "alias": a} for e, a in achados], "papel": "citado"})
    return saida


def aplicar_ligacoes(con):
    itens = ler_json("evento-entidade-auto.json", [])
    n = n_ign = 0
    for it in itens:
        if not con.execute("SELECT 1 FROM evento WHERE id=?", (it["evento_id"],)).fetchone():
            n_ign += 1
            continue
        ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM evento_entidade WHERE evento_id=?", (it["evento_id"],)).fetchone()[0]
        for e in it["entidades"]:
            cur = con.execute("INSERT OR IGNORE INTO evento_entidade(evento_id,entidade_id,papel,ordem) VALUES(?,?,?,?)",
                              (it["evento_id"], e["id"], it.get("papel", "citado"), ordem))
            if cur.rowcount:
                ordem += 1
                n += 1
    return {"eventos": len(itens), "ligacoes": n, "ignorados": n_ign}


# ======================================================================== 4b. aliases e correções de mandato escritos à mão
def aplicar_aliases(con):
    """data/curadoria/entidade-aliases.json: `[{"entidade_id","alias","motivo"}]`. Acrescenta `entidade_alias` (tipo 'grafia', origem 'curadoria');
    nunca remove nem troca alias existente. Falha se a entidade não existe. -> {'aplicados': n, 'ja_existiam': n}"""
    r = {"aplicados": 0, "ja_existiam": 0}
    for a in ler_json("entidade-aliases.json", []):
        if not con.execute("SELECT 1 FROM entidade WHERE id=?", (a["entidade_id"],)).fetchone():
            raise SystemExit(f"entidade-aliases.json: entidade inexistente: {a['entidade_id']}")
        n = alias_norm(a["alias"])
        cur = con.execute("INSERT OR IGNORE INTO entidade_alias(alias,alias_norm,entidade_id,tipo_alias,origem) VALUES(?,?,?,'grafia','curadoria')",
                          (a["alias"], n, a["entidade_id"]))
        r["aplicados" if cur.rowcount else "ja_existiam"] += 1
    return r


def aplicar_mandato_correcoes(con):
    """data/curadoria/mandato-correcoes.json (à mão): `[{"entidade_id","cargo","inicio","campo","de","para","motivo","fonte_url"}]`.
    Troca `mandato.<campo>` (partido, uf ou fim) de `de` para `para` na linha (entidade_id, cargo, inicio); falha se a linha não existe ou o valor atual não é `de`
    (a correção ficou obsoleta ou o dado mudou). Roda depois da carga e antes de aplicar_mandato_oficial / gerar_relacoes_mandato."""
    r = {"aplicadas": []}
    for c in ler_json("mandato-correcoes.json", []):
        if c["campo"] not in ("partido", "uf", "fim"):
            raise SystemExit(f"mandato-correcoes.json: campo não permitido: {c['campo']}")
        cur = con.execute(f"UPDATE mandato SET {c['campo']}=? WHERE entidade_id=? AND cargo=? AND inicio=? AND {c['campo']}=?",
                          (c["para"], c["entidade_id"], c["cargo"], c["inicio"], c["de"]))
        if cur.rowcount != 1:
            raise SystemExit(f"mandato-correcoes.json: nenhuma linha {c['entidade_id']}/{c['cargo']}/{c['inicio']} com {c['campo']}={c['de']!r}")
        r["aplicadas"].append(c)
    return r


# ======================================================================== 5. teia <-> timeline: mandato/bancada -> relações institucionais
def _ano(s):
    return int(str(s)[:4])


def _mais_cedo(a, b):
    return a if (_ano(a), len(str(a))) <= (_ano(b), len(str(b))) else b


def _mais_tarde(a, b):
    return a if (_ano(a), len(str(a))) >= (_ano(b), len(str(b))) else b


def gerar_relacoes_mandato(con, extras=None):
    """Cria relações `institucional` (origem='linha_do_tempo', natureza documentada, status publicada) a partir de `mandato`:
      - subtipo 'mandato:<cargo>': pessoa -> órgão (Presidência, Câmara, Senado), uma por linha de `mandato`, com o período dela;
      - subtipo 'filiacao': pessoa -> partido, uma por sequência contínua de mandatos do mesmo partido (período inferido dos mandatos).
    Regras e exceções em data/curadoria/mandato-relacoes.json. Retorna dict para o relatório.
    `extras` {mandato.id: evidencia.id}: evidência oficial (aplicar_mandato_oficial) a acrescentar onde o mandato já tinha outra."""
    extras = extras or {}
    cfg = ler_json("mandato-relacoes.json", {})
    rotulos, orgao_cargo = cfg.get("rotulos", {}), cfg.get("orgao_por_cargo", {})
    sem_filiacao = set(cfg.get("sem_filiacao", []))
    por_norm = collections.defaultdict(set)
    for r in con.execute("""SELECT a.alias_norm, a.entidade_id FROM entidade_alias a JOIN entidade e ON e.id=a.entidade_id WHERE e.tipo='partido'"""):
        por_norm[r["alias_norm"]].add(r["entidade_id"])
    manual = {alias_norm(k): v for k, v in cfg.get("partido_manual", {}).items()}

    def partido_de(txt):
        if not txt or txt in sem_filiacao:
            return None
        n = alias_norm(txt)
        if n in manual:
            return manual[n]
        c = por_norm.get(n, set())
        return next(iter(c)) if len(c) == 1 else None

    ts = "2026-10-16T00:00:00Z"
    ins = """INSERT INTO relacao(de,para,tipo,subtipo,rotulo,descricao,natureza_id,periodo_inicio,periodo_fim,periodo_aprox,periodo_texto,
                                direcional,origem,origem_ref,status,criado_em,atualizado_em)
             VALUES(?,?,'institucional',?,?,?,'documentada',?,?,?,?,1,'linha_do_tempo',?,'publicada',?,?)"""
    n_mand = n_fil = 0
    sem_orgao, sem_partido, por_cargo = [], [], collections.Counter()
    fil = collections.defaultdict(list)  # (pessoa, partido_id) -> [(inicio, fim, sigla, cargo, mandato_id, evidencia_id, evidencia_extra)]
    for m in con.execute("SELECT * FROM mandato ORDER BY id").fetchall():
        orgao = m["orgao_id"] or orgao_cargo.get(m["cargo"])
        if not orgao or not con.execute("SELECT 1 FROM entidade WHERE id=?", (orgao,)).fetchone():
            sem_orgao.append((m["id"], m["entidade_id"], m["cargo"]))
            continue
        destaque = m["motivo"] is not None  # parlamentar em destaque da timeline: o período é o ano do destaque, não o mandato inteiro
        rot = rotulos.get(m["cargo"], m["cargo"])
        fim = m["fim"] or m["inicio"]
        desc = f"{rot}" + (f" ({m['partido']})" if m["partido"] else "") + f", {m['inicio']}" + (f" a {fim}" if fim != m["inicio"] else "") + "."
        if destaque:
            desc += f" Parlamentar em destaque na linha do tempo de {m['inicio']} ({m['motivo']}); o período é o ano do destaque, não o mandato inteiro."
        cur = con.execute(ins, (m["entidade_id"], orgao, f"mandato:{m['cargo']}", rot, desc, m["inicio"], fim, int(destaque),
                                m["periodo_texto"], f"mandato:{m['id']}", ts, ts))
        if m["evidencia_id"]:
            con.execute("INSERT INTO relacao_evidencia(relacao_id,evidencia_id,ordem) VALUES(?,?,0)", (cur.lastrowid, m["evidencia_id"]))
        if m["id"] in extras and extras[m["id"]] != m["evidencia_id"]:
            con.execute("INSERT INTO relacao_evidencia(relacao_id,evidencia_id,ordem) VALUES(?,?,1)", (cur.lastrowid, extras[m["id"]]))
        n_mand += 1
        por_cargo[m["cargo"]] += 1
        p = partido_de(m["partido"])
        if m["partido"] and p is None and m["partido"] not in sem_filiacao:
            sem_partido.append((m["id"], m["entidade_id"], m["partido"]))
        if p and p != m["entidade_id"]:
            fil[(m["entidade_id"], p)].append((m["inicio"], fim, m["partido"], m["cargo"], m["id"], m["evidencia_id"], extras.get(m["id"])))
    for (pessoa, partido), itens in sorted(fil.items()):
        itens.sort(key=lambda x: (_ano(x[0]), len(str(x[0])), x[4]))
        runs = []
        for it in itens:
            if runs and _ano(it[0]) <= _ano(runs[-1]["fim"]) + 1:
                r = runs[-1]
                r["fim"] = _mais_tarde(r["fim"], it[1])
                r["itens"].append(it)
            else:
                runs.append({"inicio": it[0], "fim": it[1], "itens": [it]})
        for r in runs:
            it0 = r["itens"][0]
            cargos = sorted({i[3] for i in r["itens"]})
            nome_p = con.execute("SELECT nome FROM entidade WHERE id=?", (partido,)).fetchone()[0]
            rot = f"Filiado ao {it0[2]}"
            desc = (f"Partido registrado em {len(r['itens'])} mandato(s) da linha do tempo ({', '.join(cargos)}); {nome_p}. "
                    "O período é inferido dos mandatos, não da data de filiação.")
            cur = con.execute(ins, (pessoa, partido, "filiacao", rot, desc, r["inicio"], r["fim"], 1, "inferido dos mandatos",
                                    f"filiacao:{pessoa}:{partido}:{r['inicio']}", ts, ts))
            evs = []   # evidências distintas dos mandatos da sequência (a ordem é a dos mandatos)
            for i in r["itens"]:
                for e in (i[5], i[6]):
                    if e and e not in evs:
                        evs.append(e)
            for ordem, ev in enumerate(evs):
                con.execute("INSERT INTO relacao_evidencia(relacao_id,evidencia_id,ordem) VALUES(?,?,?)", (cur.lastrowid, ev, ordem))
            n_fil += 1
    return {"mandato": n_mand, "filiacao": n_fil, "por_cargo": dict(por_cargo), "sem_orgao": sem_orgao, "sem_partido": sem_partido}


# ======================================================================== 6. temas (data/curadoria/temas.json)
def _padrao(p):
    """Padrão de texto -> regex sobre texto normalizado (alias_norm): palavra inteira; '*' no fim = prefixo ('precatorio*')."""
    estrela = p.endswith("*")
    n = alias_norm(p.rstrip("*"))
    return re.compile(r"(?<![a-z0-9])" + re.escape(n).replace(r"\ ", " ") + (r"[a-z0-9]*" if estrela else "") + r"(?![a-z0-9])")


def _casa(rg, alvo, reg, atuais, ents, texto, pats):
    """A regra casa com o registro? `atuais`: temas que o registro já tem; `ents`: entidades (relação: de/para; evento: evento_entidade)."""
    if rg.get("dentro_de") and not (set(rg["dentro_de"]) & atuais):
        return False
    if "origem" in rg and reg.get("origem") not in rg["origem"]:
        return False
    if "canal" in rg and (alvo == "relacao" or reg.get("canal") not in rg["canal"]):
        return False
    if "entidade" in rg and not (ents & set(rg["entidade"])):
        return False
    if pats and not any(p.search(texto) for p in pats):
        return False
    return True


def _alvos(rg):
    return ["relacao", "evento"] if rg["alvo"] == "ambos" else [rg["alvo"]]


def inferir_temas_relacao(con, de, para, rotulo, descricao=None):
    """Temas para uma relação nova (MCP). Base = temas principais comuns às duas entidades (v_entidade_tema; se não houver comum, a união);
    depois as regras de temas.json por entidade/texto (as por origem/canal só valem na carga). Sem nada: ['a-classificar']."""
    cfg = ler_json("temas.json", {"regras": []})
    def principais(e):
        return {r[0] for r in con.execute("SELECT v.tema_id FROM v_entidade_tema v JOIN tema t ON t.id=v.tema_id WHERE v.entidade_id=? AND t.principal=1", (e,))}
    a, b = principais(de), principais(para)
    atuais = set(a & b or a | b)
    texto = alias_norm(f"{rotulo} {descricao or ''}")
    for rg in cfg["regras"]:
        if "relacao" not in _alvos(rg) or "origem" in rg or "canal" in rg:
            continue
        if rg["tema"] not in atuais and _casa(rg, "relacao", {}, atuais, {de, para}, texto, [_padrao(x) for x in rg.get("texto", [])]):
            atuais.add(rg["tema"])
    return sorted(atuais) or ["a-classificar"]


def aplicar_temas(con):
    """Semeia `tema` e atribui relacao_tema/evento_tema pelas regras de temas.json, na ordem; depois exceções (por origem_ref da relação ou id do
    evento); o que sobrar sem tema vai para 'a-classificar'. Regra: {id, tema, alvo: relacao|evento|ambos, e UM OU MAIS filtros (E):
    origem[], canal[] (só evento), entidade[] (relação: de/para; evento: evento_entidade), texto[] (relação: rótulo+descrição; evento:
    título+descrição+contexto+resposta), dentro_de[] (só registros que já têm um desses temas)}."""
    cfg = ler_json("temas.json", {"temas": [], "regras": [], "excecoes": []})
    for t in cfg["temas"]:
        con.execute("INSERT INTO tema(id,nome,descricao,cor,ordem,principal) VALUES(?,?,?,?,?,?)",
                    (t["id"], t["nome"], t.get("descricao"), t.get("cor"), t["ordem"], int(bool(t.get("principal")))))
    validos = {t["id"] for t in cfg["temas"]}
    rel = {r["id"]: dict(r) for r in con.execute("SELECT id, de, para, origem, origem_ref, rotulo, descricao FROM relacao ORDER BY id")}
    evs = {r["id"]: dict(r) for r in con.execute("SELECT id, canal, origem, titulo, descricao, contexto, resposta FROM evento ORDER BY id")}
    ent_ev = collections.defaultdict(set)
    for r in con.execute("SELECT evento_id, entidade_id FROM evento_entidade"):
        ent_ev[r["evento_id"]].add(r["entidade_id"])
    texto_rel = {i: alias_norm(f"{r['rotulo']} {r['descricao'] or ''}") for i, r in rel.items()}
    texto_ev = {i: alias_norm(f"{r['titulo']} {r['descricao'] or ''} {r['contexto'] or ''} {r['resposta'] or ''}") for i, r in evs.items()}
    atrib = {"relacao": collections.defaultdict(dict), "evento": collections.defaultdict(dict)}  # tipo -> id -> {tema: (origem, regra)}
    stats = collections.defaultdict(lambda: {"relacao": 0, "evento": 0})
    ids_regra = set()
    for rg in cfg["regras"]:
        assert rg["id"] not in ids_regra, f"regra repetida: {rg['id']}"
        assert rg["tema"] in validos, f"tema inexistente: {rg['tema']}"
        ids_regra.add(rg["id"])
        pats = [_padrao(p) for p in rg.get("texto", [])]
        for alvo in _alvos(rg):
            for i, r in (rel if alvo == "relacao" else evs).items():
                ents = {r["de"], r["para"]} if alvo == "relacao" else ent_ev[i]
                texto = texto_rel[i] if alvo == "relacao" else texto_ev[i]
                if _casa(rg, alvo, r, set(atrib[alvo][i]), ents, texto, pats) and rg["tema"] not in atrib[alvo][i]:
                    atrib[alvo][i][rg["tema"]] = ("regra", rg["id"])
                    stats[rg["id"]][alvo] += 1
    por_ref = {r["origem_ref"]: i for i, r in rel.items() if r["origem_ref"]}
    n_exc = 0
    for ex in cfg.get("excecoes", []):
        alvo = ex["alvo"]
        i = por_ref.get(ex["ref"]) if alvo == "relacao" else ex["ref"]
        assert i is not None and i in (rel if alvo == "relacao" else evs), f"exceção para registro inexistente: {ex}"
        for t in ex.get("incluir", []):
            assert t in validos, t
            atrib[alvo][i][t] = ("excecao", f"excecao:{ex['ref']}")
        for t in ex.get("excluir", []):
            atrib[alvo][i].pop(t, None)
        n_exc += 1
    n_fallback = {"relacao": 0, "evento": 0}
    for alvo, base in (("relacao", rel), ("evento", evs)):
        for i in base:
            if not atrib[alvo][i]:
                atrib[alvo][i]["a-classificar"] = ("regra", "fallback")
                n_fallback[alvo] += 1
    for i in sorted(rel):
        for t, (o, rg) in sorted(atrib["relacao"][i].items()):
            con.execute("INSERT INTO relacao_tema(relacao_id,tema_id,origem,regra) VALUES(?,?,?,?)", (i, t, o, rg))
    for i in sorted(evs):
        for t, (o, rg) in sorted(atrib["evento"][i].items()):
            con.execute("INSERT INTO evento_tema(evento_id,tema_id,origem,regra) VALUES(?,?,?,?)", (i, t, o, rg))
    return {"regras": cfg["regras"], "por_regra": {k: dict(v) for k, v in stats.items()}, "excecoes": n_exc, "fallback": n_fallback}


# ======================================================================== 7. mandato oficial (data/raw/oficial/ -> data/curadoria/mandato-oficial.json)
OFICIAL = RAW / "oficial"
RELATORIO_MANDATO_OFICIAL = DATA / "relatorio-mandatos-oficial.md"
# Siglas que são a mesma legenda renomeada (sucessão). Só renomeações inequívocas; PL/PR e fusões (União) ficam de fora de propósito.
SUCESSAO_PARTIDO = [{"PMDB", "MDB"}, {"PFL", "DEM"}, {"PPR", "PPB", "PP"}, {"PRB", "REPUBLICANOS"}, {"PTDOB", "AVANTE"}, {"UNIAO", "UNIAOBRASIL"}]
CARGOS_OFICIAIS = {"deputado": "camara", "senador": "senado"}


def _norm_partido(s):
    if not s:
        return None
    u = sem_acento(s).upper().replace("*", "")
    if re.match(r"(SEM PARTIDO|S[./ ]\s*PART)", u):
        return "SEMPARTIDO"
    return re.sub(r"[^A-Z0-9]", "", u)


def _partido_igual(a, b):
    """-> 'igual' | 'sucessao' | None"""
    na, nb = _norm_partido(a), _norm_partido(b)
    if na is None or nb is None:
        return None
    if na == nb:
        return "igual"
    return "sucessao" if any({na, nb} <= g for g in SUCESSAO_PARTIDO) else None


def _lista(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


FALSO_INICIO = "Nome no início da legislatura"   # descricaoStatus das entradas "Nome no início da legislatura / Partido no início da legislatura"


def _info_camara(rec, datas):
    """Dados oficiais de um deputado: url, título, {legislatura: {partido, uf}}, partidos/UFs vigentes num ano (pelo histórico).
    As entradas do histórico com descricaoStatus 'Nome no início da legislatura / Partido no início da legislatura' trazem uma dataHora falsa
    (a da exportação, 2023): valem como 'partido no início da legislatura idLegislatura' e entram datadas no 1/fev desse mandato
    (legislaturas fora de 50-57, sem data conhecida, são descartadas)."""
    dep = rec["deputado"]
    legs = {int(m["legislatura"]): {"partido": m.get("siglaPartido"), "uf": m.get("siglaUf")} for m in rec.get("mandatos", [])}
    pontos = []
    for h in rec.get("historico") or []:
        if (h.get("descricaoStatus") or "").startswith(FALSO_INICIO):
            d = datas.get(int(h["idLegislatura"])) if h.get("idLegislatura") is not None else None
            dh = d["dataInicio"] + "T00:00" if d else None
        else:
            dh = h.get("dataHora")
        if dh:
            pontos.append((dh, h.get("siglaPartido"), h.get("siglaUf")))
    hist = sorted(pontos, key=lambda x: (x[0], x[1] or "", x[2] or ""))

    def no_ano(ano, col):
        vals = {h[col] for h in hist if h[0][:4] == str(ano) and h[col]}
        antes = [h[col] for h in hist if h[0][:4] < str(ano) and h[col]]
        if antes:
            vals.add(antes[-1])
        return vals
    return {"url": dep["url"], "titulo": f"Dados Abertos da Câmara — deputado {dep['id']}", "legs": legs,
            "partidos_no_ano": lambda a: no_ano(a, 1), "ufs_no_ano": lambda a: no_ano(a, 2)}


def _info_senado(rec, datas=None):
    sen = rec["senador"]
    legs = {int(l["legislatura"]): {"partido": l.get("partido"), "uf": l.get("uf")} for l in rec.get("legislaturas", [])}
    uf_mandato = {}
    par = ((rec.get("mandatos") or {}).get("MandatoParlamentar") or {}).get("Parlamentar") or {}
    for md in _lista((par.get("Mandatos") or {}).get("Mandato")):
        for k in ("PrimeiraLegislaturaDoMandato", "SegundaLegislaturaDoMandato"):
            n = (md.get(k) or {}).get("NumeroLegislatura")
            if n and md.get("UfParlamentar"):
                uf_mandato.setdefault(int(n), set()).add(md["UfParlamentar"])
    for n, l in legs.items():
        if not l["uf"] and len(uf_mandato.get(n, ())) == 1:
            l["uf"] = next(iter(uf_mandato[n]))          # UF do mandato (endpoint /mandatos) quando a lista da legislatura não traz
    fil = []
    pf = ((rec.get("filiacoes") or {}).get("FiliacaoParlamentar") or {}).get("Parlamentar") or {}
    for f in _lista((pf.get("Filiacoes") or {}).get("Filiacao")):
        fil.append(((f.get("Partido") or {}).get("SiglaPartido"), (f.get("DataFiliacao") or "")[:4], (f.get("DataDesfiliacao") or "")[:4]))

    def partidos(ano):
        a = str(ano)
        return {s for s, i, f in fil if s and i and i <= a and (not f or f >= a)}
    return {"url": sen["url"], "titulo": f"Dados Abertos do Senado — senador {sen['codigo']}", "legs": legs,
            "partidos_no_ano": partidos, "ufs_no_ano": lambda a: set()}


def _cmp(banco, oficial, historico, partido):
    """Compara um campo. -> (resultado, divergente). Resultados: igual, sucessao, historico, nao_informado, divergente."""
    if oficial is not None:
        if partido:
            r = _partido_igual(banco, oficial)
            if r:
                return r, False
        elif banco == oficial:
            return "igual", False
    for h in historico:
        if (_partido_igual(banco, h) if partido else (banco == h)):
            return "historico", False
    if oficial is None:
        return "nao_informado", False
    return "divergente", True


# Variantes de grafia do nome na página oficial (nome normalizado da página -> nome normalizado do banco).
VARIANTES_NOME_PAGINA = {"tiao vianna": "tiao viana"}
REGEX_ELEICAO = re.compile(r"eleit|votos|mais votad")   # sobre o `motivo` sem acento e em minúsculas


def _nome_norm(s):
    n = re.sub(r"[^a-z0-9]+", " ", sem_acento(s or "").lower()).strip()
    return VARIANTES_NOME_PAGINA.get(n, n)


def _nome_casa(a, b):
    """Nome do banco e nome da página casam se um está contido no outro (por palavras): 'Luís Eduardo' ~ 'Luís Eduardo Magalhães'."""
    ta, tb = set(_nome_norm(a).split()), set(_nome_norm(b).split())
    return bool(ta and tb and (ta <= tb or tb <= ta))


def _texto_html(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", h)).replace("\xa0", " ")).strip()


def _periodos_camara(htm):
    """Página 'Presidentes da Câmara': cada presidente é um link com o texto 'Nome AAAA - AAAA', 'Nome AAAA' ou 'Nome - AAAA'."""
    saida = []
    for inner in re.findall(r"(?s)<a\b[^>]*>(.*?)</a>", htm):
        t = _texto_html(inner)
        m = re.fullmatch(r"(.+?) (\d{4}) ?- ?(\d{4})", t)
        if m:
            saida.append((m.group(1), int(m.group(2)), int(m.group(3))))
            continue
        m = re.fullmatch(r"(.+?) ?- ?(\d{4})", t) or re.fullmatch(r"(.+?) (\d{4})", t)
        if m:
            saida.append((m.group(1), int(m.group(2)), int(m.group(2))))
    return sorted(set(saida), key=lambda x: (x[1], x[2], x[0]))


def _periodos_senado(htm):
    """Página 'Nova República' do Senado: <figcaption>AAAA - AAAA</figcaption> ... <p class="senador">Nome [*]</p>."""
    saida = []
    for m in re.finditer(r'(?s)<figcaption>\s*(\d{4})\s*-\s*(\d{4})\s*</figcaption>.*?<p class="senador">(.*?)</p>', htm):
        saida.append((_texto_html(m.group(3)).replace("*", "").strip(), int(m.group(1)), int(m.group(2))))
    return sorted(set(saida), key=lambda x: (x[1], x[2], x[0]))


def _texto_periodo(ini, fim):
    return str(ini) if ini == fim else f"{ini} - {fim}"


def _carregar_paginas(pres):
    """-> {cargo: {url, titulo, veiculo, entradas[(nome, ini, fim)]}} para presidente_camara / presidente_senado, só das páginas baixadas (status ok)."""
    saida = {}
    for chave, cargo, f in (("presidentes_camara", "presidente_camara", _periodos_camara), ("presidentes_senado", "presidente_senado", _periodos_senado)):
        pg = pres["paginas"].get(chave) or {}
        if pg.get("status") != "ok" or not pg.get("arquivo_cache"):
            continue
        txt = (ROOT / pg["arquivo_cache"]).read_text(encoding="utf-8")
        if pg.get("sha256") and hashlib.sha256(txt.encode("utf-8")).hexdigest() != pg["sha256"]:
            raise SystemExit(f"{pg['arquivo_cache']}: sha256 diferente do registrado em presidencia.json")
        saida[cargo] = {"url": pg["url"], "titulo": pg["titulo"], "veiculo": urlsplit(pg["url"]).netloc, "entradas": f(txt)}
    return saida


def gerar_mandato_oficial(con):
    """Casa as linhas de `mandato` com data/raw/oficial/{camara,senado,presidencia}.json. Não altera o banco. -> dict (conteúdo de mandato-oficial.json).
    deputado/senador (destaque anual, inicio=fim=ano): confirmada se a pessoa consta na API em ALGUMA legislatura que toque o ano
    (1/fev de N a 31/jan de N+4), `confirmacao: "legislatura"`; se não consta em nenhuma e o `motivo` fala de eleição, vale a legislatura que
    começa em 1/fev do ano seguinte, `confirmacao: "eleicao"` (prova o mandato subsequente, não o exercício no ano da eleição).
    presidente_camara/presidente_senado: nome e ano de `inicio` contra a página oficial da presidência da Casa, `confirmacao: "pagina"`."""
    cam = json.loads((OFICIAL / "camara.json").read_text(encoding="utf-8"))
    sen = json.loads((OFICIAL / "senado.json").read_text(encoding="utf-8"))
    pres = json.loads((OFICIAL / "presidencia.json").read_text(encoding="utf-8"))
    legs_datas = {int(k): v for k, v in cam["legislaturas"].items()}
    coletado = {"camara": cam["coletado_em"], "senado": sen["coletado_em"], "presidencia": pres["coletado_em"]}
    fontes = {"camara": (cam["deputados"], _info_camara, "dadosabertos.camara.leg.br"),
              "senado": (sen["senadores"], _info_senado, "legis.senado.leg.br")}
    paginas = _carregar_paginas(pres)
    indisponiveis = {k: v for k, v in sorted(pres["paginas"].items()) if v.get("status") != "ok"}
    out = {"gerado_de": ["data/raw/oficial/camara.json", "data/raw/oficial/senado.json", "data/raw/oficial/presidencia.json"],
           "coletado_em": coletado, "evidencias": [], "confirmacoes": [], "complementos": [], "divergencias": [], "sem_fonte": [],
           "nao_encontrados": []}
    evid, n_total, n_ev_previa = {}, 0, 0
    adicionais = mandatos_adicionais_chaves()
    q = """SELECT m.id, m.entidade_id, e.nome, m.cargo, m.partido, m.uf, m.inicio, m.motivo, m.evidencia_id
           FROM mandato m JOIN entidade e ON e.id=m.entidade_id ORDER BY m.entidade_id, m.cargo, m.inicio, m.id"""
    for m in con.execute(q).fetchall():
        n_total += 1
        chave = {"entidade_id": m["entidade_id"], "cargo": m["cargo"], "inicio": m["inicio"]}
        ano = int(m["inicio"][:4])
        casa = CARGOS_OFICIAIS.get(m["cargo"])
        if m["cargo"] in ("presidente_camara", "presidente_senado") and m["cargo"] in paginas:
            pg = paginas[m["cargo"]]
            mesmos = [e for e in pg["entradas"] if _nome_casa(m["nome"], e[0])]
            cobre = [e for e in mesmos if e[1] <= ano <= e[2]]
            if cobre:
                nome_pg, ini, fim = cobre[0]
                out["confirmacoes"].append({**chave, "casa": "camara" if m["cargo"] == "presidente_camara" else "senado", "confirmacao": "pagina",
                                            "nome_pagina": nome_pg, "periodo": _texto_periodo(ini, fim), "url": pg["url"]})
                if m["evidencia_id"]:
                    n_ev_previa += 1
                evid.setdefault(pg["url"], {"url": pg["url"], "veiculo": pg["veiculo"], "titulo": pg["titulo"], "tipo": "documento_oficial",
                                            "acessado_em": coletado["presidencia"]})
                continue
            if mesmos:
                out["divergencias"].append({**chave, "tipo": "pagina_periodo", "banco": m["inicio"],
                                            "oficial": "; ".join(f"{e[0]} {_texto_periodo(e[1], e[2])}" for e in mesmos), "legislatura": None, "url": pg["url"],
                                            "nota": f"a página lista a pessoa, mas nenhum período cobre {ano}"})
            else:
                out["divergencias"].append({**chave, "tipo": "pagina_pessoa", "banco": m["nome"], "oficial": None, "legislatura": None, "url": pg["url"],
                                            "nota": f"nome não consta na página (presidentes listados de {pg['entradas'][0][1]} a {max(e[2] for e in pg['entradas'])})"})
            continue
        if not casa:
            if m["cargo"] in ("presidente", "vice_presidente", "presidente_camara", "presidente_senado"):
                motivo = ("sem página oficial pública das presidências na coleta de " + pres["coletado_em"][:10] + ": "
                          + "; ".join(f"{k} ({v.get('status')}" + (f": {v['motivo']}" if v.get("motivo") else "") + ")" for k, v in indisponiveis.items()))
            else:
                motivo = "cargo sem fonte oficial coletada"
            out["sem_fonte"].append({**chave, "motivo": motivo})
            continue
        recs, montar, dominio = fontes[casa]
        rec = recs.get(m["entidade_id"])
        chave_rec = "deputado" if casa == "camara" else "senador"
        if not rec and (m["entidade_id"], m["cargo"], m["inicio"]) in adicionais:
            # linha de mandatos-adicionais.json de pessoa criada depois da coleta (fora de data/raw/oficial, congelado): sem fonte oficial
            # de API; a fonte oficial própria do destaque fica ligada à relação mandato:<id> (curadoria.ligar_fontes_mandatos_adicionais)
            out["sem_fonte"].append({**chave, "motivo": f"pessoa fora da coleta das APIs de {coletado[casa][:10]} (linha de mandatos-adicionais.json, "
                                                        "entidade criada depois da coleta); a fonte oficial do destaque está ligada à relação do mandato"})
            continue
        if not rec or not rec.get(chave_rec):
            busca = (rec or {}).get("busca") or []
            d = {**chave, "tipo": "nao_encontrado_na_api", "banco": m["cargo"], "oficial": None, "legislatura": None,
                 "url": busca[0]["url"] if busca else None,
                 "nota": "pessoa não encontrada na API (" + str((rec or {}).get("status") or "ausente do JSON") + "); nada foi inferido"}
            out["divergencias"].append(d)
            if not any(x["entidade_id"] == m["entidade_id"] and x["casa"] == casa for x in out["nao_encontrados"]):
                out["nao_encontrados"].append({"entidade_id": m["entidade_id"], "casa": casa, "status": (rec or {}).get("status")})
            continue
        info = montar(rec, legs_datas)
        meio = f"{ano}-07-01"
        # legislaturas em que a API lista a pessoa e que tocam algum dia do ano; a que contém 1/jul é comparada primeiro
        tocam = sorted((n for n in info["legs"] if legs_datas[n]["dataInicio"] <= f"{ano}-12-31" and legs_datas[n]["dataFim"] >= f"{ano}-01-01"),
                       key=lambda n: (not (legs_datas[n]["dataInicio"] <= meio <= legs_datas[n]["dataFim"]), n))
        tipo_conf, complementar = "legislatura", True
        if tocam:
            cands = tocam
        else:
            prox = sorted(n for n in info["legs"] if legs_datas[n]["dataInicio"] == f"{ano + 1}-02-01")
            if prox and REGEX_ELEICAO.search(sem_acento(m["motivo"] or "").lower()):
                cands, tipo_conf, complementar = prox[:1], "eleicao", False
            else:
                extra = (f"; a legislatura que começa em 1/2/{ano + 1} ({prox[0]}) lista a pessoa, mas o motivo da linha não fala de eleição" if prox else "")
                out["divergencias"].append({**chave, "tipo": "ano_fora_das_legislaturas", "banco": m["inicio"],
                                            "oficial": "legislaturas listadas: " + (", ".join(str(n) for n in sorted(info["legs"])) or "nenhuma"),
                                            "legislatura": None, "url": info["url"],
                                            "nota": f"nenhuma legislatura em que a API lista a pessoa toca {ano}" + extra})
                continue
        resultados = []
        for leg in cands:
            o = info["legs"][leg]
            divs, confirm, compl = [], {**chave, "casa": casa, "confirmacao": tipo_conf, "legislatura": leg, "url": info["url"]}, []
            for campo in ("partido", "uf"):
                banco, oficial = m[campo], o[campo]
                if banco is None:
                    if complementar and oficial is not None and not (campo == "partido" and _norm_partido(oficial) == "SEMPARTIDO"):
                        compl.append({**chave, "campo": campo, "valor": oficial, "legislatura": leg, "url": info["url"]})
                        confirm[campo] = {"banco": None, "oficial": oficial, "resultado": "complemento"}
                    else:
                        confirm[campo] = {"banco": None, "oficial": oficial, "resultado": "nao_informado"}
                    continue
                ano_hist = ano + 1 if tipo_conf == "eleicao" else ano   # eleição: partido/UF vigentes no ano em que a legislatura seguinte começa
                hist = info["partidos_no_ano"](ano_hist) if campo == "partido" else info["ufs_no_ano"](ano_hist)
                res, div = _cmp(banco, oficial, hist, campo == "partido")
                confirm[campo] = {"banco": banco, "oficial": oficial, "resultado": res}
                if div:
                    quando = (f"legislatura {leg} ({legs_datas[leg]['dataInicio'][:4]}-{legs_datas[leg]['dataFim'][:4]})"
                              + ("; a linha é de ano de eleição e foi comparada com a legislatura seguinte" if tipo_conf == "eleicao" else ""))
                    divs.append({**chave, "tipo": campo, "banco": banco, "oficial": oficial, "legislatura": leg, "url": info["url"],
                                 "nota": quando + (f"; no ano {ano_hist} o histórico/filiações oficiais traz: " + ", ".join(sorted(hist)) if hist else "")})
            resultados.append((divs, confirm, compl))
            if not divs:
                break
        divs, confirm, compl = next((r for r in resultados if not r[0]), resultados[0])
        if divs:
            out["divergencias"].extend(divs)
            continue
        out["confirmacoes"].append(confirm)
        out["complementos"].extend(compl)
        if m["evidencia_id"]:
            n_ev_previa += 1
        if info["url"] not in evid:
            evid[info["url"]] = {"url": info["url"], "veiculo": dominio, "titulo": info["titulo"], "tipo": "dado_oficial",
                                 "acessado_em": coletado[casa]}
    out["evidencias"] = [evid[u] for u in sorted(evid)]
    por_tipo = collections.Counter(c["confirmacao"] for c in out["confirmacoes"])
    out["resumo"] = {"mandatos_no_banco": n_total, "confirmados": len(out["confirmacoes"]),
        "confirmados_por_tipo": {k: por_tipo.get(k, 0) for k in ("legislatura", "eleicao", "pagina")},
        "complementados": len({(c["entidade_id"], c["cargo"], c["inicio"]) for c in out["complementos"]}),
        "divergentes": len({(d["entidade_id"], d["cargo"], d["inicio"]) for d in out["divergencias"]}),
        "sem_fonte_oficial": len(out["sem_fonte"]), "confirmados_com_evidencia_previa": n_ev_previa,
        "divergencias_registradas": len(out["divergencias"])}
    return out


def aplicar_mandato_oficial(con):
    """Aplica data/curadoria/mandato-oficial.json: evidência `dado_oficial` e complementos nas linhas confirmadas; nunca sobrescreve.
    -> dict com contagens e `extras` {mandato.id: evidencia.id} (evidência oficial a acrescentar nas relações de mandatos que já tinham outra)."""
    cfg = ler_json("mandato-oficial.json")
    r = {"evidencias": 0, "preenchidos": 0, "extras": {}, "complementados": 0, "obsoletas": [], "resumo": (cfg or {}).get("resumo", {})}
    if not cfg:
        return r
    ev = {}
    for e in cfg["evidencias"]:
        url = normalizar_url(e["url"])
        linha = con.execute("SELECT id FROM evidencia WHERE url=?", (url,)).fetchone()
        if linha:
            ev[e["url"]] = linha[0]
            continue
        cur = con.execute("INSERT INTO evidencia(url,veiculo,titulo,tipo,acessado_em,criado_em) VALUES(?,?,?,?,?,?)",
                          (url, e["veiculo"], e["titulo"], e["tipo"], e["acessado_em"], TS_MIGRACAO))
        ev[e["url"]] = cur.lastrowid
        r["evidencias"] += 1
    q = "SELECT id, evidencia_id FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=?"
    for c in cfg["confirmacoes"]:
        m = con.execute(q, (c["entidade_id"], c["cargo"], c["inicio"])).fetchone()
        if not m:
            r["obsoletas"].append((c["entidade_id"], c["cargo"], c["inicio"]))
            continue
        if m["evidencia_id"] is None:
            con.execute("UPDATE mandato SET evidencia_id=? WHERE id=?", (ev[c["url"]], m["id"]))
            r["preenchidos"] += 1
        elif m["evidencia_id"] != ev[c["url"]]:
            r["extras"][m["id"]] = ev[c["url"]]
    for c in cfg["complementos"]:
        if c["campo"] not in ("partido", "uf"):
            continue
        cur = con.execute(f"UPDATE mandato SET {c['campo']}=? WHERE entidade_id=? AND cargo=? AND inicio=? AND {c['campo']} IS NULL",
                          (c["valor"], c["entidade_id"], c["cargo"], c["inicio"]))
        r["complementados"] += cur.rowcount
    return r


def relatorio_mandato_oficial(cfg, nomes):
    """Markdown determinístico (data/relatorio-mandatos-oficial.md). `nomes`: {entidade_id: nome}."""
    rs, L = cfg["resumo"], []
    w = L.append
    nome = lambda e: nomes.get(e, e)
    pt = rs["confirmados_por_tipo"]
    w("# Mandatos: conferência com as fontes oficiais\n")
    w(f"Gerado por `scripts/gerar_curadoria.py --so mandato-oficial` a partir de `data/raw/oficial/` (Câmara coletada em {cfg['coletado_em']['camara']}, "
      f"Senado em {cfg['coletado_em']['senado']}, páginas das presidências das Casas em {cfg['coletado_em']['presidencia']}). "
      "Aplicado por `curadoria.aplicar_mandato_oficial` (arquivo `data/curadoria/mandato-oficial.json`). "
      "Nada do que já estava em `mandato` foi sobrescrito (a única mudança de valor é a correção à mão listada abaixo).\n")
    w("| | linhas de `mandato` |\n|---|---:|")
    w(f"| no banco | {rs['mandatos_no_banco']} |")
    w(f"| confirmadas | {rs['confirmados']} |")
    w(f"| &nbsp;&nbsp;por legislatura (deputado/senador; a pessoa consta na API em legislatura que toca o ano; partido e UF sem conflito) | {pt['legislatura']} |")
    w(f"| &nbsp;&nbsp;por eleição (a pessoa só consta na legislatura que começa em 1/fev do ano seguinte; ver abaixo) | {pt['eleicao']} |")
    w(f"| &nbsp;&nbsp;por página oficial da presidência da Casa (nome e ano de início) | {pt['pagina']} |")
    w(f"| com complemento de partido/UF (campo estava NULL) | {rs['complementados']} |")
    w(f"| divergentes (listadas abaixo, banco intacto) | {rs['divergentes']} |")
    w(f"| sem fonte oficial nesta rodada | {rs['sem_fonte_oficial']} |")
    w(f"\nConfirmadas + divergentes + sem fonte = {rs['confirmados'] + rs['divergentes'] + rs['sem_fonte_oficial']}. "
      f"Linhas confirmadas que já tinham evidência antes: {rs['confirmados_com_evidencia_previa']} (nesses casos a oficial entra como evidência adicional das relações).\n")
    w("Regras:\n")
    w("- `legislatura`: as linhas de `deputado`/`senador` são destaques anuais (inicio = fim = ano). Uma legislatura vai de 1/fev do ano N a 31/jan do ano N+4; "
      "a linha é confirmada se a pessoa consta na API em **qualquer** legislatura que toque algum dia do ano (a que contém 1/jul é comparada primeiro) "
      "e partido/UF do banco batem com a API (mesma sigla, renomeação inequívoca da mesma legenda como PMDB/MDB e PFL/DEM, ou legenda vigente naquele ano segundo o histórico da Câmara / filiações do Senado). "
      "Nas entradas do histórico da Câmara com descrição \"Nome no início da legislatura / Partido no início da legislatura\" a `dataHora` é falsa (2023); "
      "valem como o partido no início da legislatura indicada (1/fev do início dela).")
    w("- `eleicao`: se a pessoa **não** consta em legislatura que toque o ano, mas consta na que começa em 1/fev do ano seguinte, **e** o `motivo` da linha menciona eleição "
      "(eleit / votos / mais votad), a linha é confirmada com essa evidência e o partido/UF comparados são os da legislatura seguinte. "
      "Isso prova o mandato subsequente; **não** prova que a pessoa exercia mandato no ano da eleição.")
    w("- `pagina`: `presidente_camara` e `presidente_senado` são conferidos pelo nome (sem acento/caixa; um nome contido no outro, com a variante \"Tião Vianna\" = \"Tião Viana\") "
      "e pelo ano de `inicio` contra o período da página oficial (\"AAAA - BBBB\" cobre AAAA a BBBB; \"AAAA\" só AAAA; \"- BBBB\" só BBBB). "
      "`presidente` e `vice_presidente` seguem sem fonte oficial (não há página pública).")
    w("- Qualquer outra coisa é divergência. Campo NULL no banco só é preenchido quando a linha não tem divergência alguma (e não em linha confirmada por eleição).\n")
    eleicao = [c for c in cfg["confirmacoes"] if c["confirmacao"] == "eleicao"]
    w("## Confirmadas por eleição\n")
    w("Evidência é a legislatura seguinte; a pessoa não exercia mandato naquele ano.\n")
    w("| pessoa | cargo | ano da linha | legislatura que prova | partido (banco / oficial) | UF (banco / oficial) |\n|---|---|---|---|---|---|")
    for c in sorted(eleicao, key=lambda c: (c["entidade_id"], c["cargo"], c["inicio"])):
        w(f"| {nome(c['entidade_id'])} | {c['cargo']} | {c['inicio']} | {c['legislatura']} | {c['partido']['banco']} / {c['partido']['oficial']} | {c['uf']['banco']} / {c['uf']['oficial']} |")
    if not eleicao:
        w("| (nenhuma) | | | | | |")
    pagina = [c for c in cfg["confirmacoes"] if c["confirmacao"] == "pagina"]
    w("\n## Confirmadas por página oficial\n")
    w("| pessoa | cargo | início | nome na página | período na página |\n|---|---|---|---|---|")
    for c in sorted(pagina, key=lambda c: (c["cargo"], c["inicio"], c["entidade_id"])):
        w(f"| {nome(c['entidade_id'])} | {c['cargo']} | {c['inicio']} | {c['nome_pagina']} | {c['periodo']} |")
    if not pagina:
        w("| (nenhuma) | | | | |")
    por_tipo = collections.Counter(d["tipo"] for d in cfg["divergencias"])
    w("\n## Divergências\n")
    w("Por tipo: " + (", ".join(f"{k} {v}" for k, v in sorted(por_tipo.items())) or "nenhuma") + ".\n")
    w("| pessoa | cargo | início | tipo | banco | oficial | legislatura | fonte |\n|---|---|---|---|---|---|---|---|")
    for d in sorted(cfg["divergencias"], key=lambda d: (d["tipo"], d["entidade_id"], d["cargo"], d["inicio"])):
        w(f"| {nome(d['entidade_id'])} | {d['cargo']} | {d['inicio']} | {d['tipo']} | {d['banco']} | {d['oficial'] if d['oficial'] is not None else '(sem dado)'} | "
          f"{d['legislatura'] or ''} | {d['url'] or ''} |")
    w("\n## Pessoas não encontradas na API\n")
    nf = cfg["nao_encontrados"]
    for x in nf:
        n = sum(1 for d in cfg["divergencias"] if d["entidade_id"] == x["entidade_id"] and d["tipo"] == "nao_encontrado_na_api")
        w(f"- {nome(x['entidade_id'])} ({x['casa']}): {x['status']}; {n} linha(s) de mandato sem fonte. Provável diferença de grafia do nome parlamentar; resolver com alias (`data/curadoria/entidade-aliases.json`) e nova coleta.")
    if not nf:
        w("- nenhuma")
    sf = collections.Counter(s["cargo"] for s in cfg["sem_fonte"])
    w("\n## Sem fonte oficial nesta rodada\n")
    w(", ".join(f"{k} {v}" for k, v in sorted(sf.items())) + ". "
      + (cfg["sem_fonte"][0]["motivo"] if cfg["sem_fonte"] else "") + ". Linhas não tocadas.")
    cor = ler_json("mandato-correcoes.json", [])
    w("\n## Correções à mão aplicadas antes do confronto\n")
    w("\n".join(f"- {nome(c['entidade_id'])} {c['cargo']} {c['inicio']}: {c['campo']} {c['de']} -> {c['para']}. {c['motivo']}. Fonte: {c['fonte_url']}" for c in cor)
      if cor else "Nenhuma (`data/curadoria/mandato-correcoes.json`).")
    comp = cfg["complementos"]
    w("\n## Complementos aplicados\n")
    w("\n".join(f"- {nome(c['entidade_id'])} {c['cargo']} {c['inicio']}: {c['campo']} = {c['valor']}" for c in comp) if comp
      else "Nenhum: em `deputado`/`senador` todo `partido` e `uf` do banco já estava preenchido.")
    res = collections.Counter()
    for c in cfg["confirmacoes"]:
        if c["confirmacao"] == "pagina":
            continue
        for campo in ("partido", "uf"):
            res[(campo, c[campo]["resultado"])] += 1
    w("\n## Como as linhas confirmadas por legislatura/eleição bateram\n")
    w("| campo | " + " | ".join(["igual", "sucessao", "historico", "nao_informado", "complemento"]) + " |\n|---|---:|---:|---:|---:|---:|")
    for campo in ("partido", "uf"):
        w(f"| {campo} | " + " | ".join(str(res[(campo, k)]) for k in ["igual", "sucessao", "historico", "nao_informado", "complemento"]) + " |")
    w("\n`sucessao` = renomeação da mesma legenda; `historico` = não bate com a lista da legislatura mas bate com o histórico de partido/UF do ano; "
      "`nao_informado` = a API não traz o dado.\n")
    return "\n".join(L)


# ======================================================================== 7. evidências adicionais (pesquisa de fontes para eventos/relações sem evidência)
ARQ_RODADA3 = "evidencias-rodada3.json"
ARQ_RODADA4 = "substituicoes-rodada4.json"
ARQ_RODADA5 = "evidencias-rodada5.json"
ARQ_RODADA6 = "evidencias-rodada6.json"
RODADAS_SUBST = (4, 5)   # rodadas em que `substitui` desliga uma fonte fraca (a rodada 5 também traz fontes adicionais, sem `substitui`)
LOTE_A_RODADA4 = 27   # as 27 primeiras entradas de substituicoes-rodada4.json (lote A: trechos devolvidos pelo WebFetch como resumo)
AVISO_TRECHO_RODADA4 = "[trecho via resumo do WebFetch]"


def ler_evidencias_adicionais():
    """Todas as entradas de evidência adicional, na ordem de aplicação: `evidencias-adicionais.json` (rodadas 1 e 2), `evidencias` de
    `evidencias-rodada3.json` (rodada 3), `evidencias` de `substituicoes-rodada4.json` (rodada 4: substitutas de fontes fracas, cada uma com
    `substitui`) e `evidencias` de `evidencias-rodada5.json` (rodada 5: as 2 últimas substituições, com `substitui`, e fontes adicionais
    `sustenta`/`boa`, sem). Os arquivos das rodadas 3 e 4 guardam também `decisoes` e `nao_encontrados`, que só vão para o relatório e para
    evento-correcoes.json/relacao-correcoes.json. Formato idêntico; toda entrada do arquivo da rodada 3 tem de trazer `"rodada": 3`, e toda
    entrada do da rodada 4, `"rodada": 4` e `substitui`, e toda entrada do da rodada 5, `"rodada": 5` e qualidade `boa` (senão aborta)."""
    r3 = ler_json(ARQ_RODADA3, {}).get("evidencias", [])
    ruins = [e.get("url") for e in r3 if e.get("rodada") != 3]
    if ruins:
        raise SystemExit(f"{ARQ_RODADA3}: entradas sem \"rodada\": 3: {ruins}")
    r4 = ler_json(ARQ_RODADA4, {}).get("evidencias", [])
    ruins = [e.get("url") for e in r4 if e.get("rodada") != 4 or not e.get("substitui")]
    if ruins:
        raise SystemExit(f"{ARQ_RODADA4}: entradas sem \"rodada\": 4 ou sem `substitui`: {ruins}")
    r5 = ler_json(ARQ_RODADA5, {}).get("evidencias", [])
    ruins = [e.get("url") for e in r5 if e.get("rodada") != 5 or e.get("qualidade") != "boa"]
    if ruins:
        raise SystemExit(f"{ARQ_RODADA5}: entradas sem \"rodada\": 5 ou que não são `boa`: {ruins}")
    # rodada 6: fontes dos fatos novos de 2024, das correções de texto e das lideranças já no banco; todas `boa`, sem `substitui`
    r6 = ler_json(ARQ_RODADA6, {}).get("evidencias", [])
    ruins = [e.get("url") for e in r6 if e.get("rodada") != 6 or e.get("qualidade") != "boa" or e.get("substitui")]
    if ruins:
        raise SystemExit(f"{ARQ_RODADA6}: entradas sem \"rodada\": 6, que não são `boa` ou com `substitui`: {ruins}")
    return ler_json("evidencias-adicionais.json", []) + r3 + r4 + r5 + r6


def lista_substituida_por(e):
    """URLs (normalizadas) que substituem uma entrada fraca: `substituida_por` é uma URL ou, quando duas fontes novas substituem a mesma fraca,
    uma lista de URLs."""
    s = e.get("substituida_por")
    if not s:
        return []
    return [normalizar_url(u) for u in (s if isinstance(s, list) else [s])]


def _chave_alvo(e):
    return (e["alvo_tipo"], e.get("evento_id") or (e.get("relacao_origem"), e.get("relacao_origem_ref")))


def conferir_substituicoes(entradas):
    """Confere, antes de qualquer escrita, os dois lados de cada substituição de fonte fraca: toda entrada com `substitui` aponta para uma
    entrada `fraca` ANTERIOR do mesmo alvo com aquela URL, cujo `substituida_por` inclui a URL nova; e toda URL de `substituida_por` tem
    exatamente uma entrada substituta (`boa`, mesmo alvo, `substitui` apontando de volta). Também classifica as repetições (alvo, URL), que só
    são aceitas na rodada 4: (a) `reavaliada` = a substituta tem a mesma URL da fraca (a página foi relida; a fraca sai e a substituta liga com
    trecho/nota novos); (b) `ja_ligada` = a URL nova já estava no arquivo como entrada `boa` do mesmo alvo (rodadas 2-3), então a ligação
    existente (trecho e nota da rodada anterior) é a substituta e a entrada da rodada 4 fica só como registro. Qualquer outra repetição, um
    `substitui` sem fraca correspondente ou um `substituida_por` sem substituta aborta a migração com a lista dos problemas.
    -> {id(entrada): 'reavaliada' | 'ja_ligada'}"""
    erros, vistos, classe = [], {}, {}
    for e in entradas:
        k = (_chave_alvo(e), normalizar_url(e["url"]))
        if k in vistos:
            ant = vistos[k]
            if e.get("rodada") == 4 and ant["qualidade"] == "fraca" and normalizar_url(e["substitui"]) == k[1] and k[1] in lista_substituida_por(ant):
                classe[id(e)] = "reavaliada"
            elif e.get("rodada") == 4 and ant["qualidade"] == "boa" and not ant.get("substituida_por"):
                classe[id(e)] = "ja_ligada"
            else:
                erros.append(f"entrada repetida para o mesmo alvo e URL: {k[0]} {e['url']}")
            continue
        vistos[k] = e
    anteriores = []
    novas_r4 = {(_chave_alvo(e), normalizar_url(e["url"])) for e in entradas if e.get("rodada") in RODADAS_SUBST}
    for e in entradas:
        if e.get("substitui") and e.get("rodada") in RODADAS_SUBST:   # rodadas 1-2: `substitui` também marca substituição parcial (a fraca fica) e é só registro
            ks = (_chave_alvo(e), normalizar_url(e["substitui"]))
            fr = [x for x in anteriores if (_chave_alvo(x), normalizar_url(x["url"])) == ks]
            if not fr or fr[0]["qualidade"] != "fraca":
                erros.append(f"`substitui` não corresponde a nenhuma fonte fraca registrada para o alvo {ks[0]}: {e['substitui']} (nova: {e['url']})")
            elif lista_substituida_por(fr[0]) and normalizar_url(e["url"]) not in lista_substituida_por(fr[0]):
                erros.append(f"{ks[0]}: a fraca {e['substitui']} tem `substituida_por` sem a URL nova {e['url']}")
            elif not lista_substituida_por(fr[0]):
                erros.append(f"{ks[0]}: a fraca {e['substitui']} substituída na rodada {e['rodada']} não traz `substituida_por` (marque-a em evidencias-adicionais.json)")
            if e["qualidade"] != "boa":
                erros.append(f"{ks[0]}: substituta {e['url']} não é `boa`")
        anteriores.append(e)
    for e in entradas:
        for u in lista_substituida_por(e):
            if e["qualidade"] != "fraca":
                erros.append(f"`substituida_por` em entrada que não é fraca: {_chave_alvo(e)} {e['url']}")
            if (_chave_alvo(e), u) not in novas_r4:   # substituições das rodadas 1-2: conferidas como antes pelo validar.py
                continue
            nv = [x for x in entradas if x.get("rodada") in RODADAS_SUBST and x.get("substitui") and _chave_alvo(x) == _chave_alvo(e)
                  and normalizar_url(x["url"]) == u and normalizar_url(x["substitui"]) == normalizar_url(e["url"])]
            if len(nv) != 1:
                erros.append(f"{_chave_alvo(e)}: `substituida_por` {u} sem exatamente uma entrada substituta apontando de volta ({len(nv)})")
    if erros:
        raise SystemExit("evidências adicionais (substituições): nada foi aplicado.\n  " + "\n  ".join(erros))
    return classe


def _alvo_evidencia(con, e):
    """(tabela_de_ligação, coluna, id do alvo) de uma entrada de evidencias-adicionais.json; falha se o alvo não existe.
    Evento: `evento_id` (via evento_alias se foi fundido). Relação: ids de relação são atribuídos na migração, então a chave estável é
    (`relacao_origem`, `relacao_origem_ref`) = (relacao.origem, relacao.origem_ref)."""
    if e["alvo_tipo"] == "evento":
        r = con.execute("SELECT id FROM evento WHERE id=?", (e["evento_id"],)).fetchone()
        if not r:
            r = con.execute("SELECT e.id FROM evento_alias a JOIN evento e ON e.id=a.evento_id WHERE a.alias=?", (e["evento_id"],)).fetchone()
        if not r:
            raise SystemExit(f"evidencias-adicionais.json: evento inexistente: {e['evento_id']}")
        return "evento_evidencia", "evento_id", r[0]
    if e["alvo_tipo"] == "relacao":
        r = con.execute("SELECT id FROM relacao WHERE origem=? AND origem_ref=?", (e["relacao_origem"], e["relacao_origem_ref"])).fetchone()
        if not r:
            raise SystemExit(f"evidencias-adicionais.json: relação inexistente: {e['relacao_origem']} {e['relacao_origem_ref']}")
        return "relacao_evidencia", "relacao_id", r[0]
    raise SystemExit(f"evidencias-adicionais.json: alvo_tipo inválido: {e['alvo_tipo']}")


def aplicar_evidencias_adicionais(con):
    """data/curadoria/evidencias-adicionais.json (à mão): uma entrada por (alvo, URL). Cria `evidencia` (URL normalizada; se já existe, reaproveita
    e NÃO altera veiculo/tipo/título; uma entrada `fraca` com `substituida_por` NÃO é ligada nem cria evidência, só fica no arquivo como histórico; a
    `descricao_nova` dela ainda vale), liga em `evento_evidencia` (rotulo = titulo) ou `relacao_evidencia` (papel 'sustenta') e guarda por ligação
    `trecho_citado`, `nota` e `qualidade` ('boa'/'fraca'; colunas aditivas do schema). Nas relações da teia (entrada com `descricao_nova`) troca
    `relacao.descricao` só quando a atual começa com "Vínculo" e contém "sem descrição na fonte". Nunca muda rótulo, tipo, subtipo nem descrição de evento.
    Roda depois das relações de mandato/filiação (que precisam existir) e antes dos temas. Lê também as rodadas 3 (`evidencias-rodada3.json`)
    e 4 (`substituicoes-rodada4.json`), via ler_evidencias_adicionais, com as mesmas regras; as substituições são conferidas antes por
    conferir_substituicoes. Uma fraca substituída cuja URL também vem da carga bruta para o mesmo evento (fonte do bloco-ano de
    brasil-fontes.json, ligação sem trecho e sem avaliação) não é apagada: se essa ligação bruta é `sustenta`, é rebaixada a `contexto`
    ("rebaixadas"); se já é `contexto`, fica ("contexto_mantidas"). Uma entrada da rodada 4 `ja_ligada` (a URL nova já era `boa` no mesmo alvo)
    não cria ligação: exige a ligação existente `sustenta`/`boa`. -> dict para o relatório."""
    entradas = ler_evidencias_adicionais()
    classe = conferir_substituicoes(entradas)
    r = {"entradas": entradas, "alvos": {}, "evid_novas": collections.Counter(), "evid_reaproveitadas": 0, "ligacoes": 0, "ja_ligadas": 0,
         "descricoes_trocadas": [], "descricoes_mantidas": [], "substituidas": [], "promovidas": 0,
         "rebaixadas": [], "contexto_mantidas": [], "r4_ja_ligadas": [], "r4_reavaliadas": [], "r4_promovidas": []}
    for e in entradas:
        tab, col, aid = _alvo_evidencia(con, e)
        if (tab, aid) not in r["alvos"]:
            r["alvos"][(tab, aid)] = con.execute(f"SELECT count(*) FROM {tab} WHERE {col}=?", (aid,)).fetchone()[0]   # ligações antes
    criadas = set()
    for e in entradas:
        tab, col, aid = _alvo_evidencia(con, e)
        url = normalizar_url(e["url"])
        substituida = e["qualidade"] == "fraca" and bool(e.get("substituida_por"))   # fonte fraca já trocada por outra: fica no arquivo como histórico, não é ligada
        if classe.get(id(e)) == "ja_ligada":
            lig = con.execute(f"SELECT x.papel, x.qualidade FROM {tab} x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.{col}=? AND v.url=?",
                              (aid, url)).fetchone()
            if not lig or tuple(lig) != ("sustenta", "boa"):
                raise SystemExit(f"{ARQ_RODADA4}: {e['url']} devia já estar ligada ao alvo como sustenta/boa (rodada anterior): {lig and tuple(lig)}")
            r["r4_ja_ligadas"].append(e)
            continue
        if classe.get(id(e)) == "reavaliada":
            r["r4_reavaliadas"].append(e)
        if substituida:
            r["substituidas"].append(e)
            bruta = con.execute(f"SELECT x.papel FROM {tab} x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.{col}=? AND v.url=? "
                                "AND x.trecho_citado IS NULL AND x.qualidade IS NULL AND x.nota IS NULL", (aid, url)).fetchone()
            if bruta and tab != "evento_evidencia":
                raise SystemExit(f"evidencias-adicionais.json: fraca substituída {e['url']} ligada à relação pela carga bruta (caso não previsto)")
            if bruta and bruta[0] == "sustenta":
                con.execute("UPDATE evento_evidencia SET papel='contexto' WHERE evento_id=? AND evidencia_id=(SELECT id FROM evidencia WHERE url=?)",
                            (aid, url))
                r["rebaixadas"].append(e)
            elif bruta:
                r["contexto_mantidas"].append(e)
        linha = None if substituida else con.execute("SELECT id FROM evidencia WHERE url=?", (url,)).fetchone()
        if substituida:
            pass
        elif linha:
            evid = linha[0]
            r["evid_reaproveitadas"] += url not in criadas   # só as que já existiam antes desta etapa (a mesma URL em 2 alvos conta 1 nova)
        else:
            criadas.add(url)
            cur = con.execute("INSERT INTO evidencia(url,veiculo,titulo,data,tipo,criado_em) VALUES(?,?,?,?,?,?)",
                              (url, e["veiculo"], e["titulo"], e["data"], e["tipo"], TS_MIGRACAO))
            evid = cur.lastrowid
            r["evid_novas"][e["tipo"]] += 1
        if not substituida:
            ordem = con.execute(f"SELECT COALESCE(MAX(ordem)+1,0) FROM {tab} WHERE {col}=?", (aid,)).fetchone()[0]
        nota = e.get("nota") or None
        if substituida:
            cur = None
        elif tab == "evento_evidencia":
            cur = con.execute("INSERT OR IGNORE INTO evento_evidencia(evento_id,evidencia_id,papel,ordem,rotulo,trecho_citado,nota,qualidade) VALUES(?,?,'sustenta',?,?,?,?,?)",
                              (aid, evid, ordem, e["titulo"], e["trecho"], nota, e["qualidade"]))
        else:
            cur = con.execute("INSERT OR IGNORE INTO relacao_evidencia(relacao_id,evidencia_id,papel,trecho_citado,ordem,nota,qualidade) VALUES(?,?,'sustenta',?,?,?,?)",
                              (aid, evid, e["trecho"], ordem, nota, e["qualidade"]))
        if cur is not None and not cur.rowcount and tab == "evento_evidencia":
            # a URL já estava ligada ao evento por uma carga anterior (fonte de `contexto` do bloco-ano de brasil-fontes.json, ou `sustenta` por slug), sem trecho
            # nem avaliação: a pesquisa leu a página e confirma que ela sustenta o evento, então a ligação sobe para `sustenta` com rótulo, trecho, nota e qualidade
            up = con.execute("UPDATE evento_evidencia SET papel='sustenta', rotulo=?, trecho_citado=?, nota=?, qualidade=? "
                             "WHERE evento_id=? AND evidencia_id=? AND trecho_citado IS NULL AND qualidade IS NULL",
                             (e["titulo"], e["trecho"], nota, e["qualidade"], aid, evid))
            if up.rowcount:
                r["promovidas"] += 1
                promovida = True
            else:
                promovida = False
        else:
            promovida = False
        if e.get("rodada") in RODADAS_SUBST and cur is not None and not cur.rowcount and not promovida:
            raise SystemExit(f"rodada {e['rodada']}: {e['url']} já estava ligada ao alvo com trecho/avaliação e não é `ja_ligada` (caso não previsto)")
        if e.get("rodada") == 4 and promovida:
            r["r4_promovidas"].append(e)
        if cur is not None and not promovida:
            r["ligacoes" if cur.rowcount else "ja_ligadas"] += 1
        if e.get("descricao_nova"):
            atual = con.execute("SELECT descricao FROM relacao WHERE id=?", (aid,)).fetchone()[0] or ""
            if atual.startswith("Vínculo") and "sem descrição na fonte" in atual:
                con.execute("UPDATE relacao SET descricao=? WHERE id=?", (e["descricao_nova"], aid))
                r["descricoes_trocadas"].append(aid)
            else:
                r["descricoes_mantidas"].append(aid)
    r["alvos"] = {f"{t}:{i}": n for (t, i), n in r["alvos"].items()}
    return r


# ======================================================================== correções de tipo e metadados de evidência
CAMPOS_EVIDENCIA_CORRECAO = ("tipo",)
DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def aplicar_evidencia_correcoes(con):
    """data/curadoria/evidencia-correcoes.json (à mão): `[{"url","campo":"tipo","de","para","motivo"}]`. Troca `evidencia.tipo` de uma evidência
    identificada pela URL (normalizada). Todas as entradas são conferidas antes de qualquer UPDATE; aborta (sem aplicar nada) se a URL não existe,
    o campo não é permitido, a entrada se repete, falta o motivo ou o valor atual não é `de`. Roda depois das cargas de evidência (inclusive as
    adicionais). -> dict."""
    r = {"aplicadas": []}
    erros, plano, vistos = [], [], set()
    for c in ler_json("evidencia-correcoes.json", []):
        url = normalizar_url(c.get("url", ""))
        ref = f"{c.get('url')}/{c.get('campo')}"
        if c.get("campo") not in CAMPOS_EVIDENCIA_CORRECAO:
            erros.append(f"{ref}: campo não permitido")
            continue
        if (url, c["campo"]) in vistos:
            erros.append(f"{ref}: entrada repetida")
            continue
        vistos.add((url, c["campo"]))
        if not c.get("motivo"):
            erros.append(f"{ref}: motivo obrigatório")
        row = con.execute("SELECT id, tipo FROM evidencia WHERE url=?", (url,)).fetchone()
        if not row:
            erros.append(f"{ref}: evidência inexistente")
        elif row[1] != c.get("de"):
            erros.append(f"{ref}: valor atual {row[1]!r} diferente de `de` {c.get('de')!r}")
        else:
            plano.append((row[0], c))
    if erros:
        raise SystemExit("evidencia-correcoes.json: nada foi aplicado.\n  " + "\n  ".join(erros))
    for eid, c in plano:
        try:
            con.execute(f"UPDATE evidencia SET {c['campo']}=? WHERE id=?", (c["para"], eid))
        except Exception as ex:   # CHECK do schema
            raise SystemExit(f"evidencia-correcoes.json: {c['url']}: {ex}")
        r["aplicadas"].append(dict(c, id_efetivo=eid))
    return r


def aplicar_evidencia_metadados(con):
    """data/curadoria/evidencia-metadados.json: `[{"url","titulo","data","status"}]` (rodadas de WebFetch; ver scripts/enriquecer_evidencias.py).
    Só preenche `evidencia.titulo`/`evidencia.data` onde estão NULL e só para `status == "ok"`; nunca sobrescreve. -> dict com contagens."""
    r = {"entradas": 0, "ok": 0, "erro": 0, "titulos": 0, "datas": 0, "sem_evidencia": []}
    for m in ler_json("evidencia-metadados.json", []):
        r["entradas"] += 1
        if m.get("status") != "ok":
            r["erro"] += 1
            continue
        r["ok"] += 1
        row = con.execute("SELECT id, titulo, data FROM evidencia WHERE url=?", (normalizar_url(m["url"]),)).fetchone()
        if not row:
            r["sem_evidencia"].append(m["url"])
            continue
        if row[1] is None and m.get("titulo"):
            con.execute("UPDATE evidencia SET titulo=? WHERE id=?", (m["titulo"], row[0]))
            r["titulos"] += 1
        if row[2] is None and m.get("data"):
            con.execute("UPDATE evidencia SET data=? WHERE id=?", (m["data"], row[0]))
            r["datas"] += 1
    return r


# ======================================================================== estimativas em R$ por entidade (escândalos)
NATUREZAS_VALOR = ("movimentado", "sonegado", "desviado", "bloqueado", "passivo", "prejuizo", "investigado", "outro")


def aplicar_entidade_valores(con):
    """data/curadoria/entidade-valores.json (à mão): `valores` = [{entidade_id, valor_brl, natureza, texto, quem_estima, data, url, veiculo, tipo,
    titulo, trecho, nota, principal, qualidade[, motivo_fraca]}]. Cada entrada vira uma linha de `entidade_valor` (tabela aditiva; `ordem` = posição
    da entrada entre as da mesma entidade) ligada a uma `evidencia` pela URL normalizada: se a URL já existe, reaproveita e só preenche
    titulo/data onde estão NULL (veiculo/tipo são NOT NULL e nunca mudam); senão cria com veiculo/tipo/titulo/data da entrada.
    Todas as entradas são conferidas antes de qualquer escrita; aborta (sem aplicar nada) se a entidade não existe, a natureza não é válida,
    há mais de um `principal` por entidade, `fraca` sem `motivo_fraca` ou falta campo obrigatório. -> dict com contagens."""
    cfg = ler_json("entidade-valores.json", {})
    entradas = cfg.get("valores", [])
    r = {"entradas": len(entradas), "entidades": 0, "principais": 0, "fracas": 0, "evid_novas": 0, "evid_reaproveitadas": 0,
         "titulos": 0, "datas": 0, "por_natureza": collections.Counter(), "descartados": len(cfg.get("descartados", [])),
         "sem_estimativa": len(cfg.get("sem_estimativa", []))}
    erros, princ, ordem = [], collections.Counter(), collections.Counter()
    for i, e in enumerate(entradas):
        ref = f"valores[{i}] ({e.get('entidade_id')})"
        for c in ("entidade_id", "valor_brl", "natureza", "texto", "quem_estima", "url", "veiculo", "tipo", "qualidade"):
            if e.get(c) in (None, ""):
                erros.append(f"{ref}: campo obrigatório ausente: {c}")
        if not con.execute("SELECT 1 FROM entidade WHERE id=?", (e.get("entidade_id"),)).fetchone():
            erros.append(f"{ref}: entidade inexistente")
        if e.get("natureza") not in NATUREZAS_VALOR:
            erros.append(f"{ref}: natureza inválida {e.get('natureza')!r}")
        if e.get("qualidade") not in ("boa", "fraca") or (e.get("qualidade") == "fraca" and not e.get("motivo_fraca")):
            erros.append(f"{ref}: qualidade inválida ou `fraca` sem motivo_fraca")
        if not isinstance(e.get("principal"), bool):
            erros.append(f"{ref}: `principal` tem de ser true/false")
        elif e["principal"]:
            princ[e.get("entidade_id")] += 1
    erros += [f"{k}: {n} valores com principal=true (máximo 1)" for k, n in sorted(princ.items()) if n > 1]
    if erros:
        raise SystemExit("entidade-valores.json: nada foi aplicado.\n  " + "\n  ".join(erros))
    criadas = set()
    for e in entradas:
        url = normalizar_url(e["url"])
        row = con.execute("SELECT id, titulo, data FROM evidencia WHERE url=?", (url,)).fetchone()
        if row:
            evid = row[0]
            r["evid_reaproveitadas"] += url not in criadas
            if row[1] is None and e.get("titulo"):
                con.execute("UPDATE evidencia SET titulo=? WHERE id=?", (e["titulo"], evid))
                r["titulos"] += 1
            if row[2] is None and e.get("data"):
                con.execute("UPDATE evidencia SET data=? WHERE id=?", (e["data"], evid))
                r["datas"] += 1
        else:
            try:
                evid = con.execute("INSERT INTO evidencia(url,veiculo,titulo,data,tipo,criado_em) VALUES(?,?,?,?,?,?)",
                                   (url, e["veiculo"], e.get("titulo"), e.get("data"), e["tipo"], TS_MIGRACAO)).lastrowid
            except Exception as ex:   # CHECK de evidencia.tipo
                raise SystemExit(f"entidade-valores.json: {e['url']}: {ex}")
            criadas.add(url)
            r["evid_novas"] += 1
        k = e["entidade_id"]
        con.execute("""INSERT INTO entidade_valor(entidade_id,valor_brl,natureza,texto,quem_estima,data,principal,nota,qualidade,motivo_fraca,
                       ordem,evidencia_id,trecho_citado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (k, float(e["valor_brl"]), e["natureza"], e["texto"], e["quem_estima"], e.get("data"), int(e["principal"]),
                     e.get("nota") or None, e["qualidade"], e.get("motivo_fraca") or None, ordem[k], evid, e.get("trecho") or None))
        ordem[k] += 1
        r["por_natureza"][e["natureza"]] += 1
        r["fracas"] += e["qualidade"] == "fraca"
    r["entidades"] = len(ordem)
    r["principais"] = sum(princ.values())
    r["sem_principal"] = sorted(k for k in ordem if not princ[k])
    return r


# ======================================================================== revisão do critério 'fraca' (evidencia-qualidade-revisao.json)
def _chave_revisao(e):
    """Chave estável de uma entrada de revisão ou de evidencias-adicionais.json: (alvo_tipo, alvo, URL normalizada)."""
    alvo = e.get("evento_id") if e.get("alvo_tipo") == "evento" else (e.get("relacao_origem"), e.get("relacao_origem_ref"))
    return (e.get("alvo_tipo"), alvo, normalizar_url(e.get("url") or ""))


def _contar_fracas(con):
    return {t: con.execute(f"SELECT count(*) FROM {t} WHERE qualidade='fraca'").fetchone()[0] for t in ("evento_evidencia", "relacao_evidencia")}


def aplicar_evidencia_qualidade(con):
    """data/curadoria/evidencia-qualidade-revisao.json (à mão): `revisoes` = [{alvo_tipo, evento_id | relacao_origem+relacao_origem_ref, url,
    qualidade:'boa', motivo}]. Para cada entrada acha a ligação (evento_evidencia por evento (id ou alias de fusão) + URL normalizada;
    relacao_evidencia pela relação (origem, origem_ref) + URL) e troca `qualidade` 'fraca' -> 'boa'; a `nota` do pesquisador fica intacta e o
    `motivo` NÃO vai para o banco (não há coluna para ele; só entra no relatório). Exceções explícitas, que não abortam e vão para o relatório:
    (a) entrada repetida, idêntica (mesma chave e mesmo motivo): conta uma vez; (b) a fonte é uma entrada `fraca` com `substituida_por` em
    evidencias-adicionais.json, que por desenho não está ligada ao alvo (já foi trocada por uma fonte `boa`): nada a mudar no banco.
    Aborta sem aplicar nada se: alvo_tipo/qualidade inválidos, motivo ausente, alvo inexistente, ligação inexistente (fora do caso b), qualidade
    atual diferente de 'fraca', ou repetição com conteúdo diferente. Roda DEPOIS de tudo que grava qualidade (evidências adicionais, substituições,
    metadados, valores, correções). `correcoes_pendentes`/`mantidas_fracas` do arquivo não são lidos aqui (as correções de texto vão por
    evento-correcoes.json). -> dict para o relatório."""
    cfg = ler_json("evidencia-qualidade-revisao.json", {})
    revisoes = cfg.get("revisoes", [])
    adic = {}
    for e in ler_evidencias_adicionais():
        adic.setdefault(_chave_revisao(e), e)   # a primeira entrada de cada (alvo, URL); as repetições da rodada 4 (reavaliada/ja_ligada) não contam aqui
    r = {"entradas": len(revisoes), "antes": _contar_fracas(con), "aplicadas": [], "duplicadas": [], "substituidas": [],
         "mantidas_fracas_arquivo": cfg.get("mantidas_fracas"),
         "adic_fracas": sum(1 for e in adic.values() if e.get("qualidade") == "fraca"),
         "adic_substituidas": sum(1 for e in adic.values() if e.get("qualidade") == "fraca" and e.get("substituida_por"))}
    erros, plano, vistos = [], [], {}
    for x in revisoes:
        k = _chave_revisao(x)
        ref = f"{k[0]}:{k[1]} {x.get('url')}"
        if x.get("alvo_tipo") not in ("evento", "relacao"):
            erros.append(f"{ref}: alvo_tipo inválido")
            continue
        if x.get("qualidade") != "boa" or not x.get("motivo"):
            erros.append(f"{ref}: qualidade tem de ser 'boa' e o motivo é obrigatório")
            continue
        if k in vistos:
            if vistos[k] != (x["qualidade"], x["motivo"]):
                erros.append(f"{ref}: entrada repetida com conteúdo diferente")
            else:
                r["duplicadas"].append(x)
            continue
        vistos[k] = (x["qualidade"], x["motivo"])
        if x["alvo_tipo"] == "evento":
            a = con.execute("SELECT id FROM evento WHERE id=?", (x["evento_id"],)).fetchone() or \
                con.execute("SELECT e.id FROM evento_alias a JOIN evento e ON e.id=a.evento_id WHERE a.alias=?", (x["evento_id"],)).fetchone()
            tab, col = "evento_evidencia", "evento_id"
        else:
            a = con.execute("SELECT id FROM relacao WHERE origem=? AND origem_ref=?", (x["relacao_origem"], x["relacao_origem_ref"])).fetchone()
            tab, col = "relacao_evidencia", "relacao_id"
        if not a:
            erros.append(f"{ref}: alvo inexistente")
            continue
        ev = con.execute("SELECT id FROM evidencia WHERE url=?", (k[2],)).fetchone()
        lig = con.execute(f"SELECT qualidade FROM {tab} WHERE {col}=? AND evidencia_id=?", (a[0], ev[0])).fetchone() if ev else None
        if not lig:
            orig = adic.get(k)
            if orig and orig.get("qualidade") == "fraca" and orig.get("substituida_por"):
                r["substituidas"].append(dict(x, substituida_por=orig["substituida_por"]))
            else:
                erros.append(f"{ref}: ligação inexistente")
            continue
        if lig[0] != "fraca":
            erros.append(f"{ref}: qualidade atual {lig[0]!r}, esperado 'fraca'")
            continue
        plano.append((tab, col, a[0], ev[0], x))
    if erros:
        raise SystemExit("evidencia-qualidade-revisao.json: nada foi aplicado.\n  " + "\n  ".join(erros))
    for tab, col, aid, evid, x in plano:
        con.execute(f"UPDATE {tab} SET qualidade='boa' WHERE {col}=? AND evidencia_id=? AND qualidade='fraca'", (aid, evid))
        r["aplicadas"].append(dict(x, tabela=tab, alvo_efetivo=aid))
    r["depois"] = _contar_fracas(con)
    return r


# ======================================================================== R6: peso da Wikipédia (regras-fontes.json)
def eh_wiki(tipo, url):
    """Fonte Wikipédia: evidencia.tipo='wiki' ou domínio *.wikipedia.org (R6)."""
    h = dominio_de(url or "")
    return tipo == "wiki" or h == "wikipedia.org" or h.endswith(".wikipedia.org")


def aplicar_peso_wikipedia(con):
    """R6 (data/curadoria/regras-fontes.json, decisão do dono do projeto): fonte Wikipédia nunca tem papel 'sustenta'. Rebaixa toda ligação
    evento_evidencia/relacao_evidencia de fonte wiki (eh_wiki) com papel 'sustenta' para 'contexto', mantendo rótulo, trecho e nota;
    `qualidade` passa a NULL (contexto não é avaliado), e as que eram 'fraca' são contadas no relatório. Roda DEPOIS de todas as funções de
    evidência (inclusive aplicar_evidencia_qualidade, que exige a 'fraca' ainda gravada) e antes de gerar a natureza (gerar_curadoria.py parte
    de um banco com R6 aplicada; R5 só olha 'sustenta'). Sem o arquivo, não roda (devolve {"ativo": False}). Aborta sem mudar nada se o
    arquivo não diz "wikipedia": "contexto" com motivo, ou se algum evento/relação ficaria sem nenhuma fonte 'sustenta' (dependia só de wiki)."""
    cfg = ler_json("regras-fontes.json")
    if cfg is None:
        return {"ativo": False}
    if cfg.get("wikipedia") != "contexto" or not cfg.get("motivo"):
        raise SystemExit('regras-fontes.json: esperado {"wikipedia": "contexto", "motivo": "..."}; nada foi aplicado.')
    r = {"ativo": True, "motivo": cfg["motivo"], "evento": [], "relacao": [], "fracas": [], "boas": 0}
    erros = []
    for tab, col, alvo in (("evento_evidencia", "evento_id", "evento"), ("relacao_evidencia", "relacao_id", "relacao")):
        lig = [x for x in con.execute(f"""SELECT x.{col} AS dono, x.evidencia_id, x.qualidade, v.url, v.tipo FROM {tab} x
                                          JOIN evidencia v ON v.id=x.evidencia_id WHERE x.papel='sustenta' ORDER BY x.{col}, x.ordem""")]
        wiki = [x for x in lig if eh_wiki(x["tipo"], x["url"])]
        resto = collections.Counter(x["dono"] for x in lig if not eh_wiki(x["tipo"], x["url"]))
        for dono in sorted({x["dono"] for x in wiki}, key=str):
            if not resto[dono]:
                erros.append(f"{alvo} {dono}: só fonte Wikipédia sustenta")
        r[alvo] = [(x["dono"], x["url"], x["qualidade"]) for x in wiki]
    if erros:
        raise SystemExit("regras-fontes.json (R6): nada foi aplicado.\n  " + "\n  ".join(erros))
    for tab, col, alvo in (("evento_evidencia", "evento_id", "evento"), ("relacao_evidencia", "relacao_id", "relacao")):
        for dono, url, qual in r[alvo]:
            con.execute(f"""UPDATE {tab} SET papel='contexto', qualidade=NULL
                            WHERE {col}=? AND evidencia_id=(SELECT id FROM evidencia WHERE url=?) AND papel='sustenta'""", (dono, url))
            if qual == "fraca":
                r["fracas"].append((alvo, dono, url))
            r["boas"] += qual == "boa"
    r["restantes"] = sum(eh_wiki(x[0], x[1]) for t in ("evento_evidencia", "relacao_evidencia")
                         for x in con.execute(f"SELECT v.tipo, v.url FROM {t} x JOIN evidencia v ON v.id=x.evidencia_id WHERE x.papel='sustenta'"))
    return r


# ======================================================================== correções de revisão (ressalvas das evidências adicionais)
CAMPOS_EVENTO_CORRECAO = ("titulo", "descricao")
CAMPOS_RELACAO_CORRECAO = ("periodo_fim", "descricao", "subtipo", "rotulo", "tipo")


def aplicar_evento_correcoes(con):
    """data/curadoria/evento-correcoes.json (à mão): `correcoes` = [{"evento_id","campo","decisao","de","para","motivo","ressalvas"}].
    Substituição textual exata em `evento.titulo` ou `evento.descricao`: `de` tem de ocorrer EXATAMENTE uma vez no valor atual do campo.
    Todas as entradas são conferidas antes de qualquer UPDATE; se uma falhar (evento inexistente, `de` ausente ou repetido) a migração aborta
    sem aplicar nada. O evento é achado pelo id ou, se foi fundido, pelo evento_alias. Roda depois das cargas e das evidências adicionais,
    antes dos temas (as regras de tema leem título e descrição). -> dict para o relatório."""
    cfg = ler_json("evento-correcoes.json", {})
    r = {"aplicadas": [], "mantidas": [], "ressalvas_mantidas": list(cfg.get("ressalvas_mantidas_com_nota", {}).get("ressalvas", [])), "pendentes": []}
    erros, plano, vistos = [], [], set()
    texto = {}   # (evento, campo) -> valor depois das correções anteriores do arquivo (uma rodada posterior corrige outro trecho do mesmo campo)
    for c in cfg.get("correcoes", []):
        ref = f"{c.get('evento_id')}/{c.get('campo')}"
        if c.get("decisao") == "manter":
            r["mantidas"].append(c)
            continue
        if c.get("campo") not in CAMPOS_EVENTO_CORRECAO:
            erros.append(f"{ref}: campo não permitido")
            continue
        if (ref, c.get("rodada")) in vistos:   # o mesmo campo só pode ser corrigido de novo por outra rodada
            erros.append(f"{ref}: entrada repetida")
            continue
        vistos.add((ref, c.get("rodada")))
        row = con.execute("SELECT id FROM evento WHERE id=?", (c["evento_id"],)).fetchone() or \
            con.execute("SELECT e.id FROM evento_alias a JOIN evento e ON e.id=a.evento_id WHERE a.alias=?", (c["evento_id"],)).fetchone()
        if not row:
            erros.append(f"{ref}: evento inexistente")
            continue
        k = (row[0], c["campo"])
        if k not in texto:
            texto[k] = con.execute(f"SELECT {c['campo']} FROM evento WHERE id=?", (row[0],)).fetchone()[0] or ""
        atual = texto[k]
        n = atual.count(c["de"]) if c.get("de") else 0
        if n != 1:
            erros.append(f"{ref}: o texto `de` ocorre {n} vez(es) em evento.{c['campo']} (esperado 1): {c.get('de')!r}; valor atual: {atual!r}")
            continue
        texto[k] = atual.replace(c["de"], c["para"], 1)
        plano.append((row[0], c, texto[k]))
    if erros:
        raise SystemExit("evento-correcoes.json: nada foi aplicado.\n  " + "\n  ".join(erros))
    for eid, c, novo in plano:
        con.execute(f"UPDATE evento SET {c['campo']}=?, atualizado_em=? WHERE id=?", (novo, TS_MIGRACAO, eid))
        r["aplicadas"].append(dict(c, id_efetivo=eid))
    return r


def aplicar_relacao_correcoes(con):
    """data/curadoria/relacao-correcoes.json (à mão): `periodos` (relações de origem linha_do_tempo) e `vinculos_teia` (relações da teia), cada entrada
    {"origem","origem_ref","alvo":{...},"decisao":"aceitar"|"manter","de":{campo: valor atual},"para":{campo: valor novo},"motivo","ressalvas"}.
    Chave estável: (origem, origem_ref). `alvo` confere a identidade (nome da entidade `de`, rótulo, periodo_inicio e/ou nome de `para`); cada campo de `de`
    tem de valer o valor atual do banco. Tudo é conferido antes do primeiro UPDATE; qualquer divergência aborta a migração sem aplicar nada.
    O valor novo de `tipo` tem de respeitar o CHECK do schema (o UPDATE falharia). decisao 'manter' só entra no relatório. -> dict para o relatório."""
    cfg = ler_json("relacao-correcoes.json", {})
    r = {"aplicadas": [], "mantidas": [], "grupos": {}}
    erros, plano, vistos = [], [], set()
    for grupo in ("periodos", "vinculos_teia"):
        for c in cfg.get(grupo, []):
            ref = f"{c.get('origem')} {c.get('origem_ref')}"
            if (c.get("origem"), c.get("origem_ref")) in vistos:
                erros.append(f"{ref}: entrada repetida")
                continue
            vistos.add((c.get("origem"), c.get("origem_ref")))
            row = con.execute("""SELECT r.id, r.rotulo, r.tipo, r.subtipo, r.descricao, r.periodo_inicio, r.periodo_fim, d.nome AS nome_de, p.nome AS nome_para
                                 FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para WHERE r.origem=? AND r.origem_ref=?""",
                              (c["origem"], c["origem_ref"])).fetchone()
            if not row:
                erros.append(f"{ref}: relação inexistente")
                continue
            al = c.get("alvo", {})
            for k_alvo, k_row in (("de", "nome_de"), ("para", "nome_para"), ("rotulo", "rotulo"), ("periodo_inicio", "periodo_inicio")):
                if k_alvo in al and al[k_alvo] != row[k_row]:
                    erros.append(f"{ref}: alvo.{k_alvo}={al[k_alvo]!r} não bate com o banco ({row[k_row]!r}); relação {row['id']}")
            if c.get("decisao") == "manter":
                r["mantidas"].append(dict(c, relacao_id=row["id"], grupo=grupo))
                continue
            de, para = c.get("de", {}), c.get("para", {})
            if not para or set(de) != set(para):
                erros.append(f"{ref}: `de` e `para` têm de ter os mesmos campos (e não vazios)")
                continue
            for campo, v in de.items():
                if campo not in CAMPOS_RELACAO_CORRECAO:
                    erros.append(f"{ref}: campo não permitido: {campo}")
                elif row[campo] != v:
                    erros.append(f"{ref}: relação {row['id']}: {campo} atual {row[campo]!r} != de {v!r}")
            plano.append((row["id"], c, grupo))
    if erros:
        raise SystemExit("relacao-correcoes.json: nada foi aplicado.\n  " + "\n  ".join(erros))
    for rid, c, grupo in plano:
        sets = ", ".join(f"{k}=?" for k in c["para"])
        try:
            con.execute(f"UPDATE relacao SET {sets}, atualizado_em=? WHERE id=?", (*c["para"].values(), TS_MIGRACAO, rid))
        except Exception as ex:   # CHECK do schema
            raise SystemExit(f"relacao-correcoes.json: {c['origem']} {c['origem_ref']}: valor novo recusado pelo schema ({ex})")
        r["aplicadas"].append(dict(c, relacao_id=rid, grupo=grupo))
    return r


def relatorio_revisao_evidencias(con, E, Rl):
    """Markdown determinístico (data/relatorio-revisao-evidencias.md) a partir dos resultados de aplicar_evento_correcoes e aplicar_relacao_correcoes."""
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    tit = {x["id"]: x["titulo"] for x in con.execute("SELECT id, titulo FROM evento")}
    ap_per = [c for c in Rl["aplicadas"] if c["grupo"] == "periodos"]
    ap_vin = [c for c in Rl["aplicadas"] if c["grupo"] == "vinculos_teia"]
    mant = Rl["mantidas"]
    campos = collections.Counter(k for c in ap_vin for k in c["para"])
    L = []
    w = L.append
    w("# Revisão das ressalvas das evidências adicionais\n")
    w("Gerado por `scripts/migrar.py` (`curadoria.relatorio_revisao_evidencias`) a partir de `data/curadoria/evento-correcoes.json` e "
      "`data/curadoria/relacao-correcoes.json`, aplicados por `curadoria.aplicar_evento_correcoes` e `curadoria.aplicar_relacao_correcoes`. Determinístico.\n")
    w("As ressalvas de `data/relatorio-evidencias-adicionais.md` foram decididas pelo dono do projeto; as decisões estão nos dois arquivos acima "
      "(o relatório de evidências continua sendo gerado só de `evidencias-adicionais.json`). Princípio: a descrição no banco tem de corresponder à evidência anexada; "
      "onde a fonte oficial contradiz um número ou data o banco muda; onde a fonte só não confirma um detalhe, o detalhe sai ou fica mais vago; "
      "onde a fonte é fraca mas o fato é notório, mantém-se marcado para troca de fonte.\n")
    w("Os fins de mandato de Lula, Alckmin, Temer (vice) e Hugo Motta foram corrigidos na tabela `mandato` (`data/curadoria/mandato-correcoes.json`, campo `fim`); por isso as relações de mandato/filiação correspondentes já nascem com o período certo e não aparecem nas tabelas abaixo.\n")
    w("## Contagens\n")
    w("| | |\n|---|---:|")
    w(f"| eventos corrigidos | {len(E['aplicadas'])} |")
    w(f"| &nbsp;&nbsp;campo `descricao` | {sum(1 for c in E['aplicadas'] if c['campo'] == 'descricao')} |")
    w(f"| &nbsp;&nbsp;campo `titulo` | {sum(1 for c in E['aplicadas'] if c['campo'] == 'titulo')} |")
    w(f"| &nbsp;&nbsp;da rodada 2 (eventos da linha do tempo sem fonte própria) | {sum(1 for c in E['aplicadas'] if c.get('rodada') == 2)} |")
    w(f"| &nbsp;&nbsp;da rodada 3 (eventos que continuavam `nao_classificada`; decisões de `evidencias-rodada3.json`) | {sum(1 for c in E['aplicadas'] if c.get('rodada') == 3)} |")
    w(f"| &nbsp;&nbsp;da rodada 4 (substituição das fontes fracas; decisões de `substituicoes-rodada4.json`) | {sum(1 for c in E['aplicadas'] if c.get('rodada') == 4)} |")
    w(f"| &nbsp;&nbsp;eventos com correção em mais de uma rodada (aplicadas em sequência, cada `de` no texto já corrigido) | "
      f"{sum(1 for n in collections.Counter((c['id_efetivo'], c['campo']) for c in E['aplicadas']).values() if n > 1)} |")
    w(f"| relações de linha do tempo corrigidas (período/descrição) | {len(ap_per)} |")
    w(f"| vínculos da teia ajustados (subtipo/rótulo/tipo) | {len(ap_vin)} |")
    w(f"| &nbsp;&nbsp;`subtipo` definido | {campos['subtipo']} |")
    w(f"| &nbsp;&nbsp;`rotulo` trocado | {campos['rotulo']} |")
    w(f"| &nbsp;&nbsp;`tipo` trocado | {campos['tipo']} |")
    w(f"| itens mantidos com nota (relações/vínculos sem mudança) | {len(mant)} |")
    w(f"| ressalvas mantidas com nota, sem mudança no banco (ids de ressalva) | {len(E['ressalvas_mantidas'])} |")
    rc4 = [c for c in Rl["aplicadas"] if 4 in (c.get("rodada_campos") or {}).values()]
    w(f"| vínculos da teia com campo corrigido na rodada 4 (`rodada_campos`) | {len(rc4)} |")
    nf = sum(con.execute(f"SELECT count(*) FROM {t} WHERE qualidade='fraca'").fetchone()[0] for t in ("evento_evidencia", "relacao_evidencia"))
    w(f"\nFontes fracas: a rodada 4 (`substituicoes-rodada4.json`) substituiu as que tinham fonte aberta melhor e a rodada 5 (`evidencias-rodada5.json`) "
      f"as 2 últimas; ficam {nf} ligações `fraca` no banco (depois da rodada 5: 0; `data/relatorio-evidencias-adicionais.md`, seções \"Fontes fracas\", \"Rodada 4\" e "
      "\"Rodada 5\"). As substituídas ficam no arquivo como histórico.\n")
    w("## Eventos corrigidos\n")
    w("| evento | campo | de -> para | motivo | ressalvas |\n|---|---|---|---|---|")
    for c in sorted(E["aplicadas"], key=lambda c: (c["id_efetivo"], c["campo"])):
        w(f"| `{c['id_efetivo']}` | {c['campo']} | {esc(c['de'])} -> {esc(c['para'])} | {esc(c['motivo'])} | {esc(', '.join(c.get('ressalvas', [])))} |")
    w("\n## Relações de linha do tempo corrigidas\n")
    w("| relação | alvo | campo | de -> para | motivo |\n|---|---|---|---|---|")
    for c in sorted(ap_per, key=lambda c: c["relacao_id"]):
        for k in c["para"]:
            w(f"| {c['relacao_id']} `{c['origem_ref']}` | {esc(c['alvo']['de'])}: {esc(c['alvo']['rotulo'])} ({c['alvo']['periodo_inicio']}) | {k} | {esc(c['de'][k])} -> {esc(c['para'][k])} | {esc(c['motivo'])} |")
    w("\n## Vínculos da teia ajustados\n")
    w("| relação | alvo | campo | de -> para | motivo |\n|---|---|---|---|---|")
    for c in sorted(ap_vin, key=lambda c: c["relacao_id"]):
        for k in c["para"]:
            w(f"| {c['relacao_id']} `{c['origem_ref']}` | {esc(c['alvo']['de'])} -> {esc(c['alvo']['para'])} | {k} | {esc(c['de'][k]) if c['de'][k] is not None else '(vazio)'} -> {esc(c['para'][k])} | {esc(c['motivo'])} |")
    w("\n## Mantidos com nota (nada mudou)\n")
    w("| relação | alvo | motivo |\n|---|---|---|")
    for c in sorted(mant, key=lambda c: c["relacao_id"]):
        al = c["alvo"]
        w(f"| {c['relacao_id']} `{c['origem_ref']}` | {esc(al['de'])}{' -> ' + esc(al['para']) if 'para' in al else ''}: {esc(al['rotulo'])} | {esc(c['motivo'])} |")
    w("\n## Ressalvas mantidas sem mudança no banco\n")
    w(f"{len(E['ressalvas_mantidas'])} ressalvas: " + ", ".join(E["ressalvas_mantidas"]) + ".\n")
    return "\n".join(L) + "\n"


def relatorio_evidencias_adicionais(con, R, E=None):
    """Markdown determinístico (data/relatorio-evidencias-adicionais.md) a partir do resultado de aplicar_evidencias_adicionais
    (e, se dado, de aplicar_evento_correcoes: `E`, para a seção da rodada 2)."""
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    entradas = R["entradas"]
    rot = {r["id"]: r for r in con.execute("SELECT id, origem_ref, rotulo, descricao, de, para FROM relacao")}
    nome = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM entidade")}
    tit = {r["id"]: r["titulo"] for r in con.execute("SELECT id, titulo FROM evento")}

    def alvo(e):
        if e["alvo_tipo"] == "evento":
            return f"evento `{e['evento_id']}` ({esc(tit.get(e['evento_id'], ''))})"
        rid = con.execute("SELECT id FROM relacao WHERE origem=? AND origem_ref=?", (e["relacao_origem"], e["relacao_origem_ref"])).fetchone()[0]
        x = rot[rid]
        return f"relação {rid} `{x['origem_ref']}` ({esc(nome[x['de']])} -> {esc(nome[x['para']])}: {esc(x['rotulo'])})"

    ev = {e["evento_id"] for e in entradas if e["alvo_tipo"] == "evento"}
    rl = {(e["relacao_origem"], e["relacao_origem_ref"]) for e in entradas if e["alvo_tipo"] == "relacao"}
    sem_ev = {k: n for k, n in R["alvos"].items() if n == 0}
    n_ev_antes = sum(1 for k in sem_ev if k.startswith("evento_evidencia:"))
    n_rl_antes = sum(1 for k in sem_ev if k.startswith("relacao_evidencia:"))
    n_ev_dep = con.execute("SELECT count(*) FROM evento e WHERE NOT EXISTS (SELECT 1 FROM evento_evidencia x WHERE x.evento_id=e.id)").fetchone()[0]
    n_rl_dep = con.execute("SELECT count(*) FROM relacao r WHERE r.status='publicada' AND NOT EXISTS (SELECT 1 FROM relacao_evidencia x WHERE x.relacao_id=r.id)").fetchone()[0]
    todas_fracas = [e for e in entradas if e["qualidade"] == "fraca"]
    fracas = [e for e in todas_fracas if not e.get("substituida_por")]   # as ligadas ao alvo
    chave_alvo = lambda e: (e["alvo_tipo"], e.get("evento_id") or (e["relacao_origem"], e["relacao_origem_ref"]))
    subst_de = collections.defaultdict(list)   # (alvo, url normalizada da fraca) -> entradas novas que a substituem
    for e in entradas:
        if e.get("substitui"):
            subst_de[(chave_alvo(e), normalizar_url(e["substitui"]))].append(e)
    n_subst = [e for e in todas_fracas if e.get("substituida_por")]
    n_parc = [e for e in fracas if subst_de.get((chave_alvo(e), normalizar_url(e["url"])))]
    n_sem = [e for e in fracas if e not in n_parc]

    def qual_banco(e):   # qualidade atual da ligação (a revisão do critério, evidencia-qualidade-revisao.json, pode ter trocado 'fraca' por 'boa')
        tab, col, aid = _alvo_evidencia(con, e)
        x = con.execute(f"SELECT l.qualidade FROM {tab} l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.{col}=? AND v.url=?",
                        (aid, normalizar_url(e["url"]))).fetchone()
        return x[0] if x else None
    revistas = [e for e in fracas if qual_banco(e) == "boa"]
    r6w = [e for e in fracas if e not in revistas and qual_banco(e) is None and eh_wiki(e.get("tipo"), e["url"])]   # R6: wiki, hoje `contexto`
    L = []
    w = L.append
    w("# Evidências adicionais\n")
    w("Gerado por `scripts/migrar.py` (`curadoria.relatorio_evidencias_adicionais`) a partir de `data/curadoria/evidencias-adicionais.json`, "
      "aplicado por `curadoria.aplicar_evidencias_adicionais`. Determinístico: não muda entre execuções.\n")
    w("Pesquisa de fontes para os eventos e relações que a migração deixava sem nenhuma evidência. Nada foi descartado: as fontes de qualidade "
      "`fraca` entram marcadas (coluna `qualidade` de `evento_evidencia`/`relacao_evidencia`) para serem substituídas depois. "
      "Esta etapa não altera rótulo, tipo, subtipo das relações nem a descrição dos eventos: as divergências abaixo eram decisão humana, hoje registrada em `data/curadoria/evento-correcoes.json` e `data/curadoria/relacao-correcoes.json` (resumo em `data/relatorio-revisao-evidencias.md`); as tabelas mostram o estado atual do banco.\n")
    w("## Contagens\n")
    w("| | |\n|---|---:|")
    w(f"| entradas (alvo, URL) | {len(entradas)} |")
    w(f"| eventos cobertos | {len(ev)} |")
    w(f"| relações cobertas | {len(rl)} |")
    w(f"| eventos sem evidência antes -> depois | {n_ev_antes} -> {n_ev_dep} |")
    w(f"| relações publicadas sem evidência antes -> depois | {n_rl_antes} -> {n_rl_dep} |")
    w(f"| evidências novas (linhas em `evidencia`) | {sum(R['evid_novas'].values())} |")
    w(f"| ligações a URLs que já existiam em `evidencia` antes desta etapa (reaproveitadas; veículo e tipo intactos) | {R['evid_reaproveitadas']} |")
    w(f"| ligações criadas | {R['ligacoes']} |")
    w(f"| ligações que já existiam (fonte de contexto do bloco-ano) e passaram a `sustenta` com trecho, nota e qualidade | {R['promovidas']} |")
    w(f"| qualidade `boa` | {len(entradas) - len(todas_fracas)} |")
    w(f"| qualidade `fraca` (no arquivo, inclusive as substituídas, que ficam como histórico) | {len(todas_fracas)} |")
    w(f"| qualidade `fraca` ligadas ao alvo (como entraram) | {len(fracas)} |")
    w(f"| &nbsp;&nbsp;das quais voltaram a `boa` na revisão do critério (`evidencia-qualidade-revisao.json`, seção 18 de `relatorio-migracao.md`) | {len(revistas)} |")
    if r6w:
        w(f"| &nbsp;&nbsp;das quais, da Wikipédia, viraram `contexto` sem avaliação pela R6 (`regras-fontes.json`, seção 21 de `relatorio-migracao.md`) | {len(r6w)} |")
    w(f"| &nbsp;&nbsp;continuam `fraca` no banco | {len(fracas) - len(revistas) - len(r6w)} |")
    w(f"| descrições de relação da teia substituídas | {len(R['descricoes_trocadas'])} |")
    w(f"| descrições mantidas (a atual já não era o texto padrão \"Vínculo ... sem descrição na fonte\") | {len(R['descricoes_mantidas'])} |")
    w("\nEvidências novas por tipo:\n")
    w("| tipo | evidências novas |\n|---|---:|")
    for t, n in sorted(R["evid_novas"].items()):
        w(f"| {t} | {n} |")
    w("\nOnde ficam os dados (colunas aditivas, ver `-- DESVIO` em `scripts/schema.sql`): `trecho_citado` (em `relacao_evidencia` já existia; em `evento_evidencia` é novo), "
      "`nota` (ressalva do pesquisador) e `qualidade` ('boa'/'fraca'; NULL nas ligações antigas, que não foram avaliadas). "
      "`evidencia.veiculo`/`tipo` vêm da primeira entrada que criou a URL; `evento_evidencia.rotulo` = título da fonte.\n")
    w("## Relações da teia: vínculo descrito pela fonte difere do rótulo do grafo\n")
    div = [e for e in entradas if e.get("divergencia_rotulo")]
    w(f"{len(div)} relações. O rótulo (`Familiar ou próximo de` / `Escritório ligado a`) continua como estava; a `descricao` agora diz o que a fonte diz. "
      "Decidir se o rótulo, o `tipo` ou o `subtipo` devem mudar.\n")
    w("| relação | rótulo atual | a fonte descreve | descrição nova |\n|---|---|---|---|")
    for e in div:
        rid = con.execute("SELECT id FROM relacao WHERE origem=? AND origem_ref=?", (e["relacao_origem"], e["relacao_origem_ref"])).fetchone()[0]
        w(f"| {alvo(e)} | {esc(rot[rid]['rotulo'])} | {esc(e['divergencia_rotulo'])} | {esc(e['descricao_nova'])} |")
    w("\n## Fontes fracas (para substituição futura)\n")
    w(f"{len(fracas)} entradas ainda ligadas ao alvo ({len(n_parc)} com substituição parcial, {len(n_sem)} sem substituto); "
      f"as outras {len(n_subst)} foram substituídas e ficam no arquivo só como histórico. Das ligadas, {len(revistas)} voltaram a `boa` na revisão do critério "
      f"(a nota do pesquisador fica)"
      + (f" e {len(r6w)}, da Wikipédia, viraram `contexto` sem avaliação pela R6 ({', '.join(f'`{e['evento_id']}`' if e['alvo_tipo'] == 'evento' else f'`{e['relacao_origem_ref']}`' for e in r6w)})" if r6w else "")
      + f"; a tabela lista as {len(fracas) - len(revistas) - len(r6w)} que continuam `fraca` no banco.\n")
    w("| alvo | url | motivo |\n|---|---|---|")
    for e in fracas:
        if e not in revistas and e not in r6w:
            w(f"| {alvo(e)} | {esc(e['url'])} | {esc(e['motivo_fraca'])} |")
    w("\n## Substituições de fontes fracas\n")
    w("Uma entrada `fraca` com `substituida_por` não é ligada ao alvo (continua no arquivo como histórico); a nova evidência (`boa`) traz `substitui: <url da fraca>`. "
      "Quando a nova fonte sustenta só parte do fato, a fraca continua ligada, sem `substituida_por`, e a nota registra o que falta.\n")
    w("| | |\n|---|---:|")
    w(f"| fontes fracas no arquivo | {len(todas_fracas)} |")
    w(f"| substituídas (desligadas do alvo) | {len(n_subst)} |")
    w(f"| substituídas parcialmente (fraca continua ligada) | {len(n_parc)} |")
    w(f"| sem substituto (continuam ligadas) | {len(n_sem)} |")
    w(f"| fraca ligadas ao alvo depois | {len(fracas)} |")
    w("\n| alvo | fraca -> nova | tipo |\n|---|---|---|")
    for f in todas_fracas:
        for nv in subst_de.get((chave_alvo(f), normalizar_url(f["url"])), []):
            parc = " (parcial: a fraca continua ligada)" if not f.get("substituida_por") else ""
            w(f"| {alvo(f)} | {esc(f['url'])} -> {esc(nv['url'])}{parc} | {nv['tipo']} |")
    if n_sem:
        w("\nSem substituto (continuam ligadas e marcadas):\n")
        for e in n_sem:
            w(f"- {alvo(e)}: {esc(e['url'])}")
    w("\n## Contradições e ressalvas para decisão humana\n")
    com_nota = [e for e in entradas if e.get("nota")]
    w(f"Todas as notas não vazias dos pesquisadores ({len(com_nota)}). Entre elas: Mercosul em 11/1/1995 e não 1/1; Efeito Tequila (US$ 50 bi não sustentado); "
      "LRF (Pedro Novais como relator não confirmado; Álvaro Dias foi relator na CCJ); Luiz Estêvão em 28/6 não confirmado; posse de FHC com 54,3% vs 55,22%; "
      "cassação de Dirceu já em 1/12/2005; médias do Brent 54,57 e 38,26; Grécia em 2/5/2010; manifestações de 2015 com cerca de 2 milhões e não \"centenas de milhares\"; "
      "minério de ferro 96,8 e 55,2; Pazuello em 15/5; Acordo de Paris com 195 Partes (a UE já está incluída); placar do STF sobre doações (8x2 ou 8x3); "
      "condenação de Bolsonaro a 27 anos e 3 meses; tarifa agrícola em 20/11/2025 (EO 14361); Bolsonaro deixou o PSL em 2019 (relação \"PSL 2019-2022\" inexata); "
      "Temer vice até 2016; posse definitiva de Temer em 31/8/2016; Lula e Alckmin com mandato até 2026; Alckmin no PSB desde março de 2022; "
      "Hugo Motta no biênio 2025-2026; Alencar no PRB em 2011; Maciel vice até 1/1/2003.\n")
    w("| alvo | fonte | nota |\n|---|---|---|")
    for e in com_nota:
        w(f"| {alvo(e)} | {esc(e['veiculo'])}: {esc(e['url'])} | {esc(e['nota'])} |")
    L += _secao_rodada2(con, entradas, E, esc)
    L += _secao_rodada3(con, entradas, E, esc)
    L += _secao_rodada4(con, R, E, esc, alvo)
    L += _secao_rodada5(con, R, esc, alvo)
    L += _secao_rodada6(con, R, esc, alvo)
    return "\n".join(L) + "\n"


def _secao_rodada4(con, R, E, esc, alvo):
    """Seção "Rodada 4": substituição das fontes fracas restantes (`substituicoes-rodada4.json`): cada substituição com a origem da fraca e o
    que aconteceu com a ligação dela, as correções de texto com `"rodada": 4`, as decisões só registradas e as fracas que ficam."""
    entradas = R["entradas"]
    r4 = [e for e in entradas if e.get("rodada") == 4]
    if not r4:
        return []
    cfg = ler_json(ARQ_RODADA4, {})
    dec = cfg.get("decisoes", {})
    corr = [c for c in (E["aplicadas"] if E else []) if c.get("rodada") == 4]
    corr_rel = [c for c in ler_json("relacao-correcoes.json", {}).get("vinculos_teia", []) if 4 in (c.get("rodada_campos") or {}).values()]
    anteriores = [e for e in entradas if e.get("rodada") not in RODADAS_SUBST]
    fraca_de = {}
    for e in anteriores:
        fraca_de.setdefault((_chave_alvo(e), normalizar_url(e["url"])), e)
    ids = lambda lst: {id(x) for x in lst}
    ja, reav, prom = ids(R["r4_ja_ligadas"]), ids(R["r4_reavaliadas"]), ids(R["r4_promovidas"])
    rebx = {(_chave_alvo(e), normalizar_url(e["url"])) for e in R["rebaixadas"]}
    ctxm = {(_chave_alvo(e), normalizar_url(e["url"])) for e in R["contexto_mantidas"]}
    distintas = sorted({(_chave_alvo(e), normalizar_url(e["substitui"])) for e in r4}, key=str)
    por_fraca = collections.Counter((_chave_alvo(e), normalizar_url(e["substitui"])) for e in r4)
    origem = lambda f: ("evidencias-adicionais.json, rodada 2" if f.get("rodada") == 2 else
                        "evidencias-adicionais.json, rodada 1" if not f.get("rodada") else f"rodada {f['rodada']}")
    por_origem = collections.Counter(origem(fraca_de[k]) for k in distintas)
    restam = []
    for t, c, extra in (("evento_evidencia", "evento_id", ""), ("relacao_evidencia", "relacao_id", "")):
        for r in con.execute(f"SELECT l.{c}, v.url FROM {t} l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.qualidade='fraca' ORDER BY l.{c}, v.url"):
            restam.append((t, r[0], r[1]))
    # a rodada 5 fechou as 2 últimas (cscb.ca, Brasil 247): este quadro é o estado ao fim da rodada 4, então as soma de volta
    for e in entradas:
        if e.get("rodada") == 5 and e.get("substitui"):
            tab5, _col5, aid5 = _alvo_evidencia(con, e)
            restam.append((tab5, aid5, normalizar_url(e["substitui"])))
    restam.sort(key=lambda x: (x[0], str(x[1]), x[2]))
    # R6 (regras-fontes.json): fracas wiki que ficaram depois da rodada e hoje são `contexto` sem avaliação (aplicar_peso_wikipedia)
    r6 = []
    for e in R["entradas"]:
        if e["qualidade"] == "fraca" and not e.get("substituida_por") and eh_wiki(e.get("tipo"), e["url"]):
            tab, col, aid = _alvo_evidencia(con, e)
            x = con.execute(f"SELECT l.papel, l.qualidade FROM {tab} l JOIN evidencia v ON v.id=l.evidencia_id WHERE l.{col}=? AND v.url=?",
                            (aid, normalizar_url(e["url"]))).fetchone()
            if x and tuple(x) == ("contexto", None) and (tab, aid, normalizar_url(e["url"])) not in r6:
                r6.append((tab, aid, normalizar_url(e["url"])))
    tit = {x["id"]: x["titulo"] for x in con.execute("SELECT id, titulo FROM evento")}
    nat = lambda i: (con.execute("SELECT COALESCE(natureza_id,'(NULL)') FROM evento WHERE id=?", (i,)).fetchone() or ["(inexistente)"])[0]
    eventos = sorted({e["evento_id"] for e in r4 if e["alvo_tipo"] == "evento"})
    por_nat = collections.Counter(nat(i) for i in eventos)

    def como(e):
        k = (_chave_alvo(e), normalizar_url(e["substitui"]))
        if id(e) in reav:
            return "reavaliada (mesma URL; trecho/nota da rodada 4)"
        f = "fraca desligada"
        if k in rebx:
            f = "fraca: ligação bruta `sustenta` rebaixada a `contexto`"
        elif k in ctxm:
            f = "fraca: volta a ser só `contexto` do bloco-ano"
        if id(e) in ja:
            return f + "; substituta já ligada (rodada 2/3, trecho e nota de lá)"
        if id(e) in prom:
            return f + "; substituta era `contexto` do bloco-ano e subiu a `sustenta`"
        return f
    L = []
    w = L.append
    w("\n## Rodada 4 — substituição das fontes fracas restantes\n")
    w("Os números desta seção são o estado ao fim da rodada 4 (e da R6); a rodada 5 (seção seguinte) substituiu as 2 fracas que sobraram.\n")
    w("As entradas ficam em `data/curadoria/substituicoes-rodada4.json` (`evidencias`, formato idêntico ao de `evidencias-adicionais.json`, com "
      "`\"rodada\": 4` e `substitui: <url da fraca>`) e são aplicadas pela mesma `curadoria.aplicar_evidencias_adicionais` (via "
      "`ler_evidencias_adicionais`, depois das rodadas 1-3), papel `sustenta`, qualidade `boa`. Cada fraca substituída recebe `substituida_por` "
      "(uma URL ou, se duas fontes novas a substituem, a lista) no arquivo onde está registrada e deixa de ser ligada ao alvo; "
      "`curadoria.conferir_substituicoes` confere os dois lados antes de qualquer escrita e aborta se um `substitui` não corresponde a nenhuma "
      "fonte fraca registrada. Quando a URL da fraca é também fonte bruta do bloco-ano do evento (`brasil-fontes.json`), a ligação não some: "
      "volta a ser `contexto` sem trecho nem avaliação (se a carga bruta a fazia `sustenta` por slug, é rebaixada a `contexto`). "
      "Duas repetições de (alvo, URL) são aceitas só nesta rodada: a substituta com a mesma URL da fraca (página relida: a fraca sai, a "
      "substituta entra com trecho/nota novos) e a substituta que já era fonte `boa` do alvo nas rodadas 2-3 (a ligação existente fica, com o "
      "trecho e a nota de lá; a entrada da rodada 4 é só registro). Nas 27 primeiras entradas (lote A) o WebFetch devolveu resumo: a nota leva "
      f"`{AVISO_TRECHO_RODADA4}` (`aviso_trechos` do arquivo).\n")
    w("| | |\n|---|---:|")
    w(f"| entradas | {len(r4)} |")
    w(f"| &nbsp;&nbsp;de evento / de relação | {sum(1 for e in r4 if e['alvo_tipo'] == 'evento')} / {sum(1 for e in r4 if e['alvo_tipo'] == 'relacao')} |")
    w(f"| alvos | {len({_chave_alvo(e) for e in r4})} |")
    w(f"| fontes fracas distintas substituídas | {len(distintas)} |")
    w(f"| &nbsp;&nbsp;substituídas por duas fontes novas | {sum(1 for n in por_fraca.values() if n > 1)} |")
    for o, n in sorted(por_origem.items()):
        w(f"| &nbsp;&nbsp;fraca registrada em {o} | {n} |")
    w(f"| &nbsp;&nbsp;fraca só na carga bruta (sem entrada de curadoria) | 0 |")
    w(f"| fraca desligada do alvo | {len(distintas) - len(rebx) - len(ctxm) - len({(_chave_alvo(e), normalizar_url(e['substitui'])) for e in R['r4_reavaliadas']})} |")
    w(f"| fraca de volta a `contexto` do bloco-ano (já era `contexto` na carga bruta) | {len(ctxm)} |")
    w(f"| fraca rebaixada de `sustenta` (carga bruta, slug) a `contexto` | {len(rebx)} |")
    w(f"| reavaliadas (mesma URL, trecho e nota novos) | {len(R['r4_reavaliadas'])} |")
    w(f"| substitutas que já eram fonte `boa` do alvo (rodadas 2-3; ligação existente mantida) | {len(R['r4_ja_ligadas'])} |")
    w(f"| substitutas que eram `contexto` do bloco-ano e subiram a `sustenta` | {len(R['r4_promovidas'])} |")
    w(f"| ligações `fraca` no banco antes -> depois da rodada | {len(restam) + len(r6) + len(distintas)} -> {len(restam) + len(r6)} |")
    if r6:
        w(f"| ligações `fraca` depois da R6 (wiki vira `contexto`, sem avaliação; `regras-fontes.json`) | {len(restam)} |")
    w(f"| correções de texto de evento (`evento-correcoes.json`, `\"rodada\": 4`) | {len(corr)} em {len({c['id_efetivo'] for c in corr})} eventos |")
    w(f"| correções de relação (`relacao-correcoes.json`, `rodada_campos`) | {len(corr_rel)} |")
    w("\nNatureza dos eventos cobertos (regra R5 sobre as fontes que sustentam):\n")
    w("| natureza | eventos |\n|---|---:|")
    for t, n in sorted(por_nat.items()):
        w(f"| {t} | {n} |")
    w("\n### Substituições\n")
    w("| alvo | fraca (registro) -> nova | tipo | ligação |\n|---|---|---|---|")
    for e in r4:
        f = fraca_de[(_chave_alvo(e), normalizar_url(e["substitui"]))]
        w(f"| {alvo(e)} | {esc(e['substitui'])} ({origem(f)}) -> {esc(e['url'])} | {e['tipo']} | {como(e)} |")
    w("\n### Correções aplicadas\n")
    w("| alvo | campo | de -> para | motivo |\n|---|---|---|---|")
    for c in sorted(corr, key=lambda c: (c["id_efetivo"], c["campo"])):
        w(f"| `{c['id_efetivo']}` | {c['campo']} | {esc(c['de'])} -> {esc(c['para'])} | {esc(c['motivo'])} |")
    for c in corr_rel:
        for k in [k for k, v in c["rodada_campos"].items() if v == 4]:
            w(f"| relação `{c['origem_ref']}` ({esc(c['alvo']['de'])} -> {esc(c['alvo']['para'])}) | {k} | {esc(c['de'][k])} -> {esc(c['para'][k])} | {esc(c['motivo'])} |")
    w("\n### Mantidas com nota (o banco não muda; a nota segue na ligação)\n")
    for m in dec.get("manter_com_nota", []):
        w(f"- {esc(m)}")
    w("\n### Continuam fracas\n")
    w(f"{len(restam) + len(r6)} ligações `fraca` no banco depois da rodada (as que nenhuma fonte aberta substituiu; `continuam_fracas` e `nao_encontrados` do arquivo)"
      + (f"; {len(r6)} delas, da Wikipédia, deixaram de ser `fraca` pela R6 (`regras-fontes.json`: wiki é sempre `contexto`, que não é avaliado) e ficam "
         f"{len(restam)}" if r6 else "") + ":\n")
    w("| alvo | url |\n|---|---|")
    for t, a, u in restam:
        if t == "evento_evidencia":
            w(f"| evento `{a}` ({esc(tit.get(a, ''))}) | {esc(u)} |")
        else:
            x = con.execute("SELECT r.origem_ref, d.nome dn, p.nome pn, r.rotulo FROM relacao r JOIN entidade d ON d.id=r.de JOIN entidade p ON p.id=r.para WHERE r.id=?", (a,)).fetchone()
            w(f"| relação {a} `{x['origem_ref']}` ({esc(x['dn'])} -> {esc(x['pn'])}: {esc(x['rotulo'])}) | {esc(u)} |")
    if r6:
        w("\nDa Wikipédia, hoje `contexto` (R6; o evento continua sustentado pelas outras fontes):\n")
        w("| alvo | url |\n|---|---|")
        for t, a, u in r6:
            w(f"| evento `{a}` ({esc(tit.get(a, ''))}) | {esc(u)} |" if t == "evento_evidencia" else f"| relação {a} | {esc(u)} |")
    w("\nDecisão do pesquisador (`continuam_fracas`):\n")
    for m in dec.get("continuam_fracas", []):
        w(f"- {esc(m)}")
    w("\n### Não encontrados\n")
    w("| alvo | tentativas |\n|---|---|")
    for n in cfg.get("nao_encontrados", []):
        a = f"evento `{n['evento_id']}`" if n.get("evento_id") else f"relação `{n['relacao_origem_ref']}`"
        w(f"| {a} | {esc(n['tentado'])} |")
    if dec.get("aviso_trechos"):
        w("\nAviso sobre os trechos (`decisoes.aviso_trechos`): " + esc(dec["aviso_trechos"]) + "\n")
    return L


def _secao_rodada5(con, R, esc, alvo):
    """Seção "Rodada 5": `evidencias-rodada5.json` (`"rodada": 5`): as 2 últimas substituições de fonte fraca (`substitui`) e as fontes adicionais
    `sustenta`/`boa` (sem `substitui`), com a natureza atual dos eventos cobertos e as ligações `fraca` antes -> depois."""
    r5 = [e for e in R["entradas"] if e.get("rodada") == 5]
    if not r5:
        return []
    cfg = ler_json(ARQ_RODADA5, {})
    subs = [e for e in r5 if e.get("substitui")]
    adic = [e for e in r5 if not e.get("substitui")]
    fracas_depois = sum(_contar_fracas(con).values())
    nat = lambda i: (con.execute("SELECT COALESCE(natureza_id,'(NULL)') FROM evento WHERE id=?", (i,)).fetchone() or ["(inexistente)"])[0]
    urls = collections.Counter(normalizar_url(e["url"]) for e in r5)
    L = []
    w = L.append
    w("\n## Rodada 5 — as últimas lacunas de fonte\n")
    w("As entradas ficam em `data/curadoria/evidencias-rodada5.json` (`evidencias`, formato idêntico ao de `evidencias-adicionais.json`, com "
      "`\"rodada\": 5` e qualidade `boa`) e são aplicadas pela mesma `curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, "
      "depois das rodadas 1-4). Mesma semântica da rodada 4: `substitui: <url da fraca>` desliga a fraca (que recebe `substituida_por` em "
      "`evidencias-adicionais.json`, onde está registrada); entrada sem `substitui` é fonte adicional `sustenta`. A mesma URL pode estar ligada a "
      "vários alvos (uma `evidencia`, uma ligação por alvo). " + (esc(cfg["_doc"]) if cfg.get("_doc") else "") + "\n")
    w("| | |\n|---|---:|")
    w(f"| entradas | {len(r5)} |")
    w(f"| &nbsp;&nbsp;de evento / de relação | {sum(1 for e in r5 if e['alvo_tipo'] == 'evento')} / {sum(1 for e in r5 if e['alvo_tipo'] == 'relacao')} |")
    w(f"| alvos | {len({_chave_alvo(e) for e in r5})} |")
    w(f"| URLs distintas | {len(urls)} |")
    w(f"| substituições (`substitui`; fraca desligada do alvo) | {len(subs)} |")
    w(f"| fontes adicionais (`sustenta`/`boa`, sem `substitui`) | {len(adic)} |")
    w(f"| ligações `fraca` no banco antes -> depois da rodada | {fracas_depois + len(subs)} -> {fracas_depois} |")
    w("\n| alvo | fonte | tipo | data | o que faz |\n|---|---|---|---|---|")
    for e in r5:
        acao = f"substitui {esc(e['substitui'])}" if e.get("substitui") else "fonte adicional"
        extra = f"; mesma URL ligada a {urls[normalizar_url(e['url'])]} alvos" if urls[normalizar_url(e["url"])] > 1 else ""
        w(f"| {alvo(e)} | {esc(e['url'])} | {e['tipo']} | {esc(str(e.get('data') or ''))} | {acao}{extra} |")
    eventos = sorted({e["evento_id"] for e in r5 if e["alvo_tipo"] == "evento"})
    w("\nNatureza atual dos eventos cobertos (regra R5 sobre as fontes que sustentam; `eventos-natureza.json` regerado):\n")
    w("| evento | natureza |\n|---|---|")
    for i in eventos:
        w(f"| `{i}` | {nat(i)} |")
    w("")
    return L


def _secao_rodada6(con, R, esc, alvo):
    """Seção "Rodada 6": `evidencias-rodada6.json` (`"rodada": 6`): fontes dos fatos novos de 2024, das correções de texto e das lideranças
    já no banco; e, por referência, as fontes que a rodada liga fora deste arquivo (ranking e linhas de mandato novas)."""
    r6 = [e for e in R["entradas"] if e.get("rodada") == 6]
    if not r6:
        return []
    cfg = ler_json(ARQ_RODADA6, {})
    nat = lambda i: (con.execute("SELECT COALESCE(natureza_id,'(NULL)') FROM evento WHERE id=?", (i,)).fetchone() or ["(inexistente)"])[0]
    urls = collections.Counter(normalizar_url(e["url"]) for e in r6)
    L = []
    w = L.append
    w("\n## Rodada 6 — fatos de 2024, correções de texto e lideranças\n")
    w("As entradas ficam em `data/curadoria/evidencias-rodada6.json` (formato idêntico, `\"rodada\": 6`, qualidade `boa`, sem `substitui`) e são "
      "aplicadas pela mesma `curadoria.aplicar_evidencias_adicionais` (depois das rodadas 1-5). " + (esc(cfg["_doc"]) if cfg.get("_doc") else "") + "\n")
    w("| | |\n|---|---:|")
    w(f"| entradas | {len(r6)} |")
    w(f"| &nbsp;&nbsp;de evento / de relação | {sum(1 for e in r6 if e['alvo_tipo'] == 'evento')} / {sum(1 for e in r6 if e['alvo_tipo'] == 'relacao')} |")
    w(f"| alvos | {len({_chave_alvo(e) for e in r6})} |")
    w(f"| URLs distintas | {len(urls)} |")
    w(f"| linhas de mandato novas com fonte própria (mandatos-adicionais.json) | {len(ler_json(ARQ_MANDATOS_ADIC, {}).get('mandatos', []))} |")
    w(f"| ligações do ranking de empresas (ranking_evidencia) | {con.execute('SELECT count(*) FROM ranking_evidencia').fetchone()[0]} |")
    w("\n| alvo | fonte | tipo | data | nota |\n|---|---|---|---|---|")
    for e in r6:
        w(f"| {alvo(e)} | {esc(e['url'])} | {e['tipo']} | {esc(str(e.get('data') or ''))} | {esc(e.get('nota') or '')} |")
    eventos = sorted({e["evento_id"] for e in r6 if e["alvo_tipo"] == "evento"})
    w("\nNatureza atual dos eventos cobertos (R5; `eventos-natureza.json` regerado):\n")
    w("| evento | natureza |\n|---|---|")
    for i in eventos:
        w(f"| `{i}` | {nat(i)} |")
    if cfg.get("nao_encontrados"):
        w("\nNão encontrados: " + " ".join(f"({i + 1}) {esc(t)}" for i, t in enumerate(cfg["nao_encontrados"])) + "\n")
    w("")
    return L


def _secao_rodada3(con, entradas, E, esc):
    """Seção "Rodada 3": entradas de `evidencias-rodada3.json` (`"rodada": 3`; fontes para os eventos que a rodada 2 deixou `nao_classificada`),
    as correções de evento-correcoes.json com `"rodada": 3`, as decisões sem correção (`campo: "nenhum"`) e `nao_encontrados` do arquivo."""
    r3 = [e for e in entradas if e.get("rodada") == 3]
    if not r3:
        return []
    cfg = ler_json(ARQ_RODADA3, {})
    corr = [c for c in (E["aplicadas"] if E else []) if c.get("rodada") == 3]
    sem_corr = [c for c in cfg.get("decisoes", {}).get("correcoes", []) if c.get("campo") == "nenhum"]
    nao = cfg.get("nao_encontrados", [])
    eventos = sorted({e["evento_id"] for e in r3})
    fracas = [e for e in r3 if e["qualidade"] == "fraca"]
    por_tipo = collections.Counter(e["tipo"] for e in r3)
    nat = lambda i: (con.execute("SELECT COALESCE(natureza_id,'(NULL)') FROM evento WHERE id=?", (i,)).fetchone() or ["(inexistente)"])[0]
    por_nat = collections.Counter(nat(i) for i in eventos)
    restam = [r[0] for r in con.execute("SELECT id FROM evento WHERE natureza_id='nao_classificada' ORDER BY data, id")]
    tit = {x["id"]: x["titulo"] for x in con.execute("SELECT id, titulo FROM evento")}
    L = []
    w = L.append
    w("\n## Rodada 3 — eventos que continuavam `nao_classificada`\n")
    w("Pesquisa de fonte aberta (oficial ou reportagem) para os eventos da linha do tempo que a rodada 2 deixou `nao_classificada` pela regra R5. "
      "As entradas ficam em `data/curadoria/evidencias-rodada3.json` (`evidencias`, formato idêntico ao de `evidencias-adicionais.json`, com `\"rodada\": 3`) e são "
      "aplicadas pela mesma `curadoria.aplicar_evidencias_adicionais` (via `ler_evidencias_adicionais`, depois das entradas de `evidencias-adicionais.json`): "
      "papel `sustenta`; as ligações wiki/outro já existentes desses eventos ficam como estavam. As correções textuais decididas no arquivo (`decisoes.correcoes`) "
      "estão em `evento-correcoes.json` com `\"rodada\": 3`.\n")
    w("| | |\n|---|---:|")
    w(f"| eventos cobertos | {len(eventos)} |")
    w(f"| entradas (evento, URL) | {len(r3)} |")
    w(f"| qualidade `boa` | {len(r3) - len(fracas)} |")
    w(f"| qualidade `fraca` | {len(fracas)} |")
    w(f"| eventos com descrição/título corrigidos | {len({c['id_efetivo'] for c in corr})} |")
    w(f"| correções aplicadas (campo) | {len(corr)} |")
    w(f"| decisões sem correção (`campo: \"nenhum\"`, só registro) | {len(sem_corr)} |")
    w(f"| `nao_encontrados` do arquivo (evidência parcial registrada mesmo assim) | {len(nao)} |")
    w(f"| eventos `nao_classificada` no banco depois da rodada | {len(restam)} |")
    w("\nEntradas por tipo de evidência:\n")
    w("| tipo | entradas | fracas |\n|---|---:|---:|")
    for t, n in sorted(por_tipo.items()):
        w(f"| {t} | {n} | {sum(1 for e in fracas if e['tipo'] == t)} |")
    w("\nNatureza dos eventos cobertos (regra R5 sobre as fontes que sustentam):\n")
    w("| natureza | eventos |\n|---|---:|")
    for t, n in sorted(por_nat.items()):
        w(f"| {t} | {n} |")
    if restam:
        w("\nContinuam `nao_classificada`: " + ", ".join(f"`{i}`" for i in restam) + ".\n")
    w("\n### Correções aplicadas\n")
    w("| evento | campo | de -> para | motivo |\n|---|---|---|---|")
    for c in sorted(corr, key=lambda c: (c["id_efetivo"], c["campo"])):
        w(f"| `{c['id_efetivo']}` | {c['campo']} | {esc(c['de'])} -> {esc(c['para'])} | {esc(c['motivo'])} |")
    w("\n### Decisões sem correção (o banco não muda; a nota segue em `evento_evidencia.nota`)\n")
    w("| evento | decisão |\n|---|---|")
    for c in sem_corr:
        w(f"| `{c['evento_id']}` ({esc(tit.get(c['evento_id'], ''))}) | {esc(c['instrucao'])} |")
    w("\n### Não encontrados\n")
    w("Fonte aberta que confirme o evento como está descrito não foi achada; a evidência parcial encontrada foi registrada mesmo assim (com nota) e sustenta o "
      "que confirma, e a descrição foi ajustada ao que a fonte diz (ver correções acima).\n")
    w("| evento | natureza no banco | motivo |\n|---|---|---|")
    for n in nao:
        w(f"| `{n['evento_id']}` ({esc(tit.get(n['evento_id'], ''))}) | {nat(n['evento_id'])} | {esc(n['motivo'])} |")
    return L


def _secao_rodada2(con, entradas, E, esc):
    """Seção "Rodada 2": entradas de evidencias-adicionais.json com `"rodada": 2` (eventos da linha do tempo sem fonte própria), as correções de
    evento-correcoes.json com `"rodada": 2` e a lista `nao_encontrados_rodada2`."""
    r2 = [e for e in entradas if e.get("rodada") == 2]
    if not r2:
        return []
    cfg = ler_json("evento-correcoes.json", {})
    corr = [c for c in (E["aplicadas"] if E else []) if c.get("rodada") == 2]
    nao = cfg.get("nao_encontrados_rodada2", [])
    eventos = sorted({e["evento_id"] for e in r2})
    fracas = [e for e in r2 if e["qualidade"] == "fraca"]
    por_tipo = collections.Counter(e["tipo"] for e in r2)
    nat = lambda i: (con.execute("SELECT COALESCE(natureza_id,'(NULL)') FROM evento WHERE id=?", (i,)).fetchone() or ["(inexistente)"])[0]
    por_nat = collections.Counter(nat(i) for i in eventos)
    nat_nao = collections.Counter(nat(n["evento_id"]) for n in nao)
    L = []
    w = L.append
    w("\n## Rodada 2 — eventos da linha do tempo sem fonte própria\n")
    w("Pesquisa de fonte aberta para eventos factuais da linha do tempo (canais `brasil` e `violencia`) que só tinham fontes de contexto do bloco-ano e, por isso, ficavam "
      "`nao_classificada` pela regra R5. As entradas desta rodada trazem `\"rodada\": 2` em `evidencias-adicionais.json`; as correções textuais, em `evento-correcoes.json`. "
      "Todas entram como papel `sustenta`; `fraca` = wiki, tipo `outro`, veículo fora dos estabelecidos ou nota do pesquisador dizendo que a fonte não confirma parte do evento.\n")
    w("| | |\n|---|---:|")
    w(f"| eventos cobertos | {len(eventos)} |")
    w(f"| entradas (evento, URL) | {len(r2)} |")
    w(f"| qualidade `boa` | {len(r2) - len(fracas)} |")
    w(f"| qualidade `fraca` | {len(fracas)} |")
    w(f"| eventos com descrição/título corrigidos | {len({c['id_efetivo'] for c in corr})} |")
    w(f"| correções aplicadas (campo) | {len(corr)} |")
    w(f"| eventos sem fonte aberta (não encontrados) | {len(nao)} |")
    w("\nEntradas por tipo de evidência:\n")
    w("| tipo | entradas | fracas |\n|---|---:|---:|")
    for t, n in sorted(por_tipo.items()):
        w(f"| {t} | {n} | {sum(1 for e in fracas if e['tipo'] == t)} |")
    w("\nNatureza dos eventos cobertos (regra R5 sobre as fontes que sustentam):\n")
    w("| natureza | eventos |\n|---|---:|")
    for t, n in sorted(por_nat.items()):
        w(f"| {t} | {n} |")
    w("\n### Correções aplicadas\n")
    w("| evento | campo | de -> para | motivo |\n|---|---|---|---|")
    for c in sorted(corr, key=lambda c: (c["id_efetivo"], c["campo"])):
        w(f"| `{c['id_efetivo']}` | {c['campo']} | {esc(c['de'])} -> {esc(c['para'])} | {esc(c['motivo'])} |")
    w("\n### Não encontrados (continuam `nao_classificada`)\n")
    w(f"{len(nao)} eventos; natureza no banco: " + ", ".join(f"{k} {v}" for k, v in sorted(nat_nao.items())) + ".\n")
    w("| evento | motivo | tentativas |\n|---|---|---|")
    tit = {x["id"]: x["titulo"] for x in con.execute("SELECT id, titulo FROM evento")}
    for n in nao:
        w(f"| `{n['evento_id']}` ({esc(tit.get(n['evento_id'], ''))}) | {esc(n['motivo'])} | {esc(n.get('tentativas', ''))} |")
    if cfg.get("manter_com_nota_rodada2"):
        w("\nRessalvas mantidas com nota (o banco não muda; a nota segue em `evento_evidencia.nota`): " + esc(cfg["manter_com_nota_rodada2"]) + "\n")
    return L


# ======================================================================== 8. rodada 6: eventos, mandatos e ranking de empresas acrescentados à mão
ARQ_EVENTOS_ADIC = "eventos-adicionais.json"
ARQ_MANDATOS_ADIC = "mandatos-adicionais.json"
ARQ_RANKING_CORR = "ranking-empresa-correcoes.json"
ARQ_RANKING_CORR_R7 = "ranking-empresa-correcoes-r7.json"   # rodada 7: mesmo formato, aplicado depois da rodada 6
ARQ_RANKING_CORR_R8 = "ranking-empresa-correcoes-r8.json"   # rodada 8: mesmo formato, aplicado depois da rodada 7 (Folha, 1997-2009)
ARQ_RANKING_CORR_R9 = "ranking-empresa-correcoes-r9.json"   # rodada 9: mesmo formato, aplicado depois da rodada 8 (Folha, 2009-2012)
ARQ_RANKING_CORR_R10 = "ranking-empresa-correcoes-r10.json"   # rodada 10: mesmo formato, aplicado depois da rodada 9 (fontes primárias: SEC e sites das empresas)
REGEX_REF_BRASIL = re.compile(r"Y\[(\d{4})\]\.(pol|intl)\.eventos\[(\d+)\]")


def _slug_curto(titulo, limite=40):
    """Mesmo corte de migrar.slug_curto (id dos eventos da timeline: ev-<ano>-<slug_curto(titulo)>)."""
    from slug import slugify
    out = ""
    for p in slugify(titulo, 200).split("-"):
        nova = f"{out}-{p}" if out else p
        if len(nova) > limite and out:
            break
        out = nova[:limite]
    return out.strip("-")


def _evidencia_id(con, f, criadas=None):
    """id da evidência da URL (normalizada) de `f`; cria com veiculo/titulo/data/tipo se não existe (se existe, não muda nada). -> (id, nova?)"""
    url = normalizar_url(f["url"])
    linha = con.execute("SELECT id FROM evidencia WHERE url=?", (url,)).fetchone()
    if linha:
        return linha[0], False
    cur = con.execute("INSERT INTO evidencia(url,veiculo,titulo,data,tipo,criado_em) VALUES(?,?,?,?,?,?)",
                      (url, f["veiculo"], f.get("titulo"), f.get("data"), f["tipo"], TS_MIGRACAO))
    if criadas is not None:
        criadas.append(url)
    return cur.lastrowid, True


def aplicar_eventos_adicionais(con):
    """data/curadoria/eventos-adicionais.json (à mão): fatos novos da linha do tempo (canal `brasil`). Insere o evento (origem 'manual',
    origem_ref Y[<ano>].<secao>.eventos[<ordem>], data = ano, natureza NULL: vem de R5 por eventos-natureza.json, regerado). Confere tudo antes de
    escrever: id = ev-<ano>-<slug_curto(titulo)> e livre, ordem = continuação do bloco (ano, seção), seção pol/intl, peso 1-5.
    Roda no início da curadoria (antes das fusões e da natureza). As fontes vêm de evidencias-rodada6.json. -> {'inseridos': [ids]}"""
    evs = ler_json(ARQ_EVENTOS_ADIC, {}).get("eventos", [])
    erros, prox = [], {}
    for r in con.execute("SELECT origem_ref FROM evento WHERE canal='brasil'"):
        m = REGEX_REF_BRASIL.fullmatch(r[0] or "")
        if m:
            k = (int(m.group(1)), m.group(2))
            prox[k] = max(prox.get(k, 0), int(m.group(3)) + 1)
    for e in evs:
        esperado = f"ev-{e['ano']}-{_slug_curto(e['titulo'])}"
        if e["id"] != esperado:
            erros.append(f"{e['id']}: id fora do padrão (esperado {esperado})")
        if con.execute("SELECT 1 FROM evento WHERE id=? UNION SELECT 1 FROM evento_alias WHERE alias=?", (e["id"], e["id"])).fetchone():
            erros.append(f"{e['id']}: id já existe")
        if e["secao"] not in ("pol", "intl") or not 1 <= int(e["peso"]) <= 5:
            erros.append(f"{e['id']}: seção/peso inválidos")
        k = (int(e["ano"]), e["secao"])
        if e["ordem"] != prox.get(k, 0):
            erros.append(f"{e['id']}: ordem {e['ordem']} não continua o bloco Y[{e['ano']}].{e['secao']} (próxima: {prox.get(k, 0)})")
        prox[k] = e["ordem"] + 1
    if erros:
        raise SystemExit(f"{ARQ_EVENTOS_ADIC}: nada foi aplicado.\n  " + "\n  ".join(erros))
    for e in evs:
        con.execute("""INSERT INTO evento(id,titulo,descricao,data,data_aprox,natureza_id,peso,canal,origem,origem_ref,criado_em,atualizado_em)
                       VALUES(?,?,?,?,0,NULL,?,'brasil','manual',?,?,?)""",
                    (e["id"], e["titulo"], e["descricao"], str(e["ano"]), int(e["peso"]), f"Y[{e['ano']}].{e['secao']}.eventos[{e['ordem']}]",
                     TS_MIGRACAO, TS_MIGRACAO))
    return {"inseridos": [e["id"] for e in evs]}


def aplicar_mandatos_adicionais(con):
    """data/curadoria/mandatos-adicionais.json (à mão): linhas de `mandato` novas (parlamentar em destaque: cargo senador/deputado, um ano,
    `motivo`). Insere na ordem do arquivo, sem evidencia_id (a confirmação pelas APIs, mandato-oficial.json, preenche onde a pessoa consta).
    Roda depois de aplicar_mandato_correcoes e antes de aplicar_mandato_oficial/gerar_relacoes_mandato. Aborta sem aplicar nada se a entidade
    ou o órgão não existem, se o cargo não é senador/deputado ou se (entidade, cargo, início) já existe. -> {'inseridos': [(id, entidade, início)]}"""
    ms = ler_json(ARQ_MANDATOS_ADIC, {}).get("mandatos", [])
    erros = []
    for m in ms:
        for col in ("entidade_id", "orgao_id"):
            if not con.execute("SELECT 1 FROM entidade WHERE id=?", (m[col],)).fetchone():
                erros.append(f"{m['entidade_id']} {m['inicio']}: {col} inexistente: {m[col]}")
        if m["cargo"] not in ("senador", "deputado") or not m.get("motivo") or not m.get("fonte"):
            erros.append(f"{m['entidade_id']} {m['inicio']}: cargo/motivo/fonte inválidos")
        if con.execute("SELECT 1 FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=?", (m["entidade_id"], m["cargo"], m["inicio"])).fetchone():
            erros.append(f"{m['entidade_id']} {m['cargo']} {m['inicio']}: linha já existe")
    if erros:
        raise SystemExit(f"{ARQ_MANDATOS_ADIC}: nada foi aplicado.\n  " + "\n  ".join(erros))
    out = []
    for m in ms:
        cur = con.execute("INSERT INTO mandato(entidade_id,cargo,orgao_id,partido,uf,inicio,fim,motivo,votos) VALUES(?,?,?,?,?,?,?,?,NULL)",
                          (m["entidade_id"], m["cargo"], m["orgao_id"], m.get("partido"), m.get("uf"), m["inicio"], m["inicio"], m["motivo"]))
        out.append((cur.lastrowid, m["entidade_id"], m["inicio"]))
    return {"inseridos": out}


def ligar_fontes_mandatos_adicionais(con):
    """Liga a `fonte` de cada linha de mandatos-adicionais.json à relação `mandato:<id>` (papel sustenta, qualidade boa, trecho e nota),
    depois de gerar_relacoes_mandato. Não toca `mandato.evidencia_id`. -> {'ligacoes': n, 'evid_novas': [urls]}"""
    novas, n = [], 0
    for m in ler_json(ARQ_MANDATOS_ADIC, {}).get("mandatos", []):
        mid = con.execute("SELECT id FROM mandato WHERE entidade_id=? AND cargo=? AND inicio=?", (m["entidade_id"], m["cargo"], m["inicio"])).fetchone()[0]
        rid = con.execute("SELECT id FROM relacao WHERE origem='linha_do_tempo' AND origem_ref=?", (f"mandato:{mid}",)).fetchone()[0]
        f = m["fonte"]
        ev, _ = _evidencia_id(con, f, novas)
        ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM relacao_evidencia WHERE relacao_id=?", (rid,)).fetchone()[0]
        con.execute("INSERT INTO relacao_evidencia(relacao_id,evidencia_id,papel,trecho_citado,ordem,nota,qualidade) VALUES(?,?,'sustenta',?,?,?,'boa')",
                    (rid, ev, f["trecho"], ordem, f.get("nota") or None))
        n += 1
        # linha sem evidência de API (pessoa fora da coleta): a filiação inferida dela também não teria fonte; a fonte do destaque passa a
        # sustentá-la, com `nota_partido` (de onde vem o partido) como nota da ligação
        # (validar.py exige `nota_partido` e essa ligação nas linhas que ficam sem API no banco final; no banco temporário de
        # gerar_curadoria.py, que pula aplicar_mandato_oficial, nenhuma linha tem evidência e só as que trazem `nota_partido` são ligadas)
        if con.execute("SELECT evidencia_id FROM mandato WHERE id=?", (mid,)).fetchone()[0] is None and m.get("nota_partido"):
            for fr in con.execute("""SELECT r.id FROM relacao r WHERE r.origem='linha_do_tempo' AND r.subtipo='filiacao' AND r.de=?
                                     AND CAST(substr(r.periodo_inicio,1,4) AS INTEGER) <= ? AND ? <= CAST(substr(r.periodo_fim,1,4) AS INTEGER)""",
                                  (m["entidade_id"], int(m["inicio"][:4]), int(m["inicio"][:4]))).fetchall():
                ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM relacao_evidencia WHERE relacao_id=?", (fr[0],)).fetchone()[0]
                cur = con.execute("INSERT OR IGNORE INTO relacao_evidencia(relacao_id,evidencia_id,papel,trecho_citado,ordem,nota,qualidade) "
                                  "VALUES(?,?,'sustenta',?,?,?,'boa')", (fr[0], ev, f["trecho"], ordem, m["nota_partido"]))
                n += cur.rowcount
    return {"ligacoes": n, "evid_novas": novas}


def mandatos_adicionais_chaves():
    """{(entidade_id, cargo, inicio)} das linhas de mandatos-adicionais.json (usado por gerar_mandato_oficial e validar.py)."""
    return {(m["entidade_id"], m["cargo"], m["inicio"]) for m in ler_json(ARQ_MANDATOS_ADIC, {}).get("mandatos", [])}


def posicoes_ranking(linhas):
    """Regra da carga bruta (conferida nas 397 linhas de data/raw/brasil.json): lucros (>= 0) em ordem decrescente e, depois, os prejuízos
    do maior para o menor (lucro crescente); empate pelo id da entidade. linhas: [(entidade_id, lucro)] -> {entidade_id: posicao}"""
    pos = sorted((x for x in linhas if x[1] >= 0), key=lambda x: (-x[1], x[0])) + sorted((x for x in linhas if x[1] < 0), key=lambda x: (x[1], x[0]))
    return {e: i for i, (e, _) in enumerate(pos, 1)}


def pct_total_ranking(lucro, pib):
    """Fórmula da carga bruta (conferida nas 397 linhas): lucro / PIB nominal do ano (R$ bi, serie macro.pib) em %, 3 casas."""
    return round(lucro / pib * 100, 3)


def aplicar_ranking_empresa_correcoes(con, arquivo=ARQ_RANKING_CORR):
    """data/curadoria/ranking-empresa-correcoes.json (à mão): `cobertura` (troca a do ano inteiro), `atualizar` (campos de -> para e fontes) e
    `inserir` (linhas novas). Fontes -> `evidencia` + `ranking_evidencia` (papel, trecho, nota); `principal` -> ranking_empresa.evidencia_id e a
    principal anterior fica com o papel/nota de `anterior`. Depois recalcula posicao e pct_total nos anos tocados (posicoes_ranking,
    pct_total_ranking). Confere tudo antes de escrever e aborta sem aplicar nada se: entidade ou linha não existem; linha a inserir já existe;
    um `de` não bate; `anterior.url` não é a fonte principal atual (ou falta quando a principal muda); cobertura do ano não uniforme ou != `de`;
    mais de uma principal; PIB do ano ausente. `arquivo`: ARQ_RANKING_CORR (rodada 6), ARQ_RANKING_CORR_R7 (rodada 7, aplicado depois e sobre
    o resultado da 6), ARQ_RANKING_CORR_R8 (rodada 8, depois da 7) ou ARQ_RANKING_CORR_R9 (rodada 9, depois da 8) ou ARQ_RANKING_CORR_R10 (rodada 10, depois da 9): o `de` é o valor que a rodada anterior gravou; quando a `anterior` já está em ranking_evidencia, a ligação é reclassificada em vez de
    duplicada). -> dict para o relatório."""
    cfg = ler_json(arquivo, {})
    vazio = {"cobertura": [], "atualizadas": [], "inseridas": [], "posicoes": {}, "pct": {}, "evid_novas": [], "ligacoes": 0}
    if not cfg:
        return vazio
    erros = []
    CAMPOS = ("lucro_brl_bi", "derivado", "holding", "obs", "setor", "setor_k", "controle")

    def linha(ano, ent):
        return con.execute("SELECT r.*, e.url AS url_principal FROM ranking_empresa r LEFT JOIN evidencia e ON e.id=r.evidencia_id "
                           "WHERE r.ano=? AND r.entidade_id=?", (ano, ent)).fetchone()
    for c in cfg.get("cobertura", []):
        cobs = {r[0] for r in con.execute("SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", (c["ano"],))}
        if cobs != {c["de"]}:
            erros.append(f"cobertura {c['ano']}: atual {sorted(cobs, key=str)} != de {c['de']!r}")
    for u in cfg.get("atualizar", []):
        r = linha(u["ano"], u["entidade_id"])
        if not r:
            erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: linha inexistente")
            continue
        for k, v in u["campos"].items():
            if k not in CAMPOS:
                erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: campo não permitido {k}")
            elif r[k] != v["de"]:
                erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: {k} atual {r[k]!r} != de {v['de']!r}")
        princ = [f for f in u["fontes"] if f.get("principal")]
        if len(princ) > 1:
            erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: mais de uma fonte principal")
        muda = bool(princ) and normalizar_url(princ[0]["url"]) != r["url_principal"]
        if muda and (not u.get("anterior") or normalizar_url(u["anterior"]["url"]) != r["url_principal"]):
            erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: a principal muda e `anterior.url` != fonte atual {r['url_principal']}")
        if not muda and u.get("anterior"):
            erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: `anterior` sem troca de principal")
        if u.get("anterior") and u["anterior"]["papel"] not in ("sustenta", "contexto"):
            erros.append(f"atualizar {u['ano']}/{u['entidade_id']}: papel de `anterior` inválido")
    for i in cfg.get("inserir", []):
        if not con.execute("SELECT 1 FROM entidade WHERE id=?", (i["entidade_id"],)).fetchone():
            erros.append(f"inserir {i['ano']}/{i['entidade_id']}: entidade inexistente")
        elif linha(i["ano"], i["entidade_id"]):
            erros.append(f"inserir {i['ano']}/{i['entidade_id']}: linha já existe")
        if sum(1 for f in i["fontes"] if f.get("principal")) != 1:
            erros.append(f"inserir {i['ano']}/{i['entidade_id']}: precisa de exatamente uma fonte principal")
    anos = sorted({x["ano"] for k in ("cobertura", "atualizar", "inserir") for x in cfg.get(k, [])})
    pib = {r[0]: r[1] for r in con.execute("SELECT ano, valor FROM serie WHERE indicador_id='macro.pib' AND dimensao=''")}
    erros += [f"PIB de {a} ausente (serie macro.pib)" for a in anos if not pib.get(a)]
    for x in [x for k in ("atualizar", "inserir") for x in cfg.get(k, [])]:
        urls = [normalizar_url(f["url"]) for f in x["fontes"]] + ([normalizar_url(x["anterior"]["url"])] if x.get("anterior") else [])
        if len(urls) != len(set(urls)):
            erros.append(f"{x['ano']}/{x['entidade_id']}: URL repetida nas fontes")
        for f in x["fontes"]:
            if f["papel"] not in ("sustenta", "contexto") or (f.get("principal") and f["papel"] != "sustenta") or not f.get("trecho"):
                erros.append(f"{x['ano']}/{x['entidade_id']} fonte {f['url']}: papel/principal/trecho inválidos")
    if erros:
        raise SystemExit(f"{arquivo}: nada foi aplicado.\n  " + "\n  ".join(erros))

    R = vazio
    for c in cfg.get("cobertura", []):
        n = con.execute("UPDATE ranking_empresa SET cobertura=? WHERE ano=?", (c["para"], c["ano"])).rowcount
        R["cobertura"].append((c["ano"], c["de"], c["para"], n))

    def ligar(ano, ent, fontes):
        for f in fontes:
            ev, _ = _evidencia_id(con, f, R["evid_novas"])
            ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM ranking_evidencia WHERE ano=? AND entidade_id=?", (ano, ent)).fetchone()[0]
            con.execute("INSERT INTO ranking_evidencia(ano,entidade_id,evidencia_id,papel,ordem,trecho_citado,nota) VALUES(?,?,?,?,?,?,?)",
                        (ano, ent, ev, f["papel"], ordem, f["trecho"], f.get("nota") or None))
            R["ligacoes"] += 1
            if f.get("principal"):
                con.execute("UPDATE ranking_empresa SET evidencia_id=? WHERE ano=? AND entidade_id=?", (ev, ano, ent))

    cob_ano = {}
    for i in cfg.get("inserir", []):
        if i["ano"] not in cob_ano:
            cob_ano[i["ano"]] = con.execute("SELECT DISTINCT cobertura FROM ranking_empresa WHERE ano=?", (i["ano"],)).fetchone()[0]
        con.execute("""INSERT INTO ranking_empresa(ano,entidade_id,posicao,setor,setor_k,lucro_brl_bi,receita_brl_bi,pct_total,controle,holding,derivado,cobertura,obs,evidencia_id)
                       VALUES(?,?,NULL,?,?,?,NULL,NULL,?,?,?,?,?,NULL)""",
                    (i["ano"], i["entidade_id"], i["setor"], i["setor_k"], i["lucro_brl_bi"], i["controle"], int(i["holding"]), int(i["derivado"]),
                     cob_ano[i["ano"]], i.get("obs") or None))
        ligar(i["ano"], i["entidade_id"], i["fontes"])
        nome = con.execute("SELECT nome FROM entidade WHERE id=?", (i["entidade_id"],)).fetchone()[0]
        if i.get("nome_epoca") and i["nome_epoca"] != nome:
            con.execute("INSERT INTO nota(tipo,pagina,chave,titulo,texto,ordem) VALUES('aviso','brasil',?,NULL,?,0)",
                        (f"Y.{i['ano']}.empresa.{i['entidade_id']}", i["nome_epoca"]))
        R["inseridas"].append(i)
    for u in cfg.get("atualizar", []):
        r = linha(u["ano"], u["entidade_id"])
        for k, v in u["campos"].items():
            con.execute(f"UPDATE ranking_empresa SET {k}=? WHERE ano=? AND entidade_id=?", (v["para"], u["ano"], u["entidade_id"]))
        ligar(u["ano"], u["entidade_id"], u["fontes"])
        if u.get("anterior"):
            if con.execute("SELECT 1 FROM ranking_evidencia WHERE ano=? AND entidade_id=? AND evidencia_id=?", (u["ano"], u["entidade_id"], r["evidencia_id"])).fetchone():
                # a principal anterior já estava ligada (rodada 6): só muda papel e nota; o trecho já registrado fica
                con.execute("UPDATE ranking_evidencia SET papel=?, nota=?, trecho_citado=COALESCE(?, trecho_citado) WHERE ano=? AND entidade_id=? AND evidencia_id=?",
                            (u["anterior"]["papel"], u["anterior"].get("nota"), u["anterior"].get("trecho"), u["ano"], u["entidade_id"], r["evidencia_id"]))
            else:
                ordem = con.execute("SELECT COALESCE(MAX(ordem)+1,0) FROM ranking_evidencia WHERE ano=? AND entidade_id=?", (u["ano"], u["entidade_id"])).fetchone()[0]
                con.execute("INSERT INTO ranking_evidencia(ano,entidade_id,evidencia_id,papel,ordem,trecho_citado,nota) VALUES(?,?,?,?,?,?,?)",
                            (u["ano"], u["entidade_id"], r["evidencia_id"], u["anterior"]["papel"], ordem, u["anterior"].get("trecho"), u["anterior"].get("nota")))
                R["ligacoes"] += 1
        R["atualizadas"].append(u)
    # posição e % do PIB nos anos tocados (mesmas regras da carga bruta)
    for a in anos:
        rs = con.execute("SELECT entidade_id, lucro_brl_bi, posicao, pct_total FROM ranking_empresa WHERE ano=?", (a,)).fetchall()
        pos = posicoes_ranking([(r[0], r[1]) for r in rs])
        for r in rs:
            novo_pct = pct_total_ranking(r[1], pib[a])
            if r[2] != pos[r[0]] or r[3] != novo_pct:
                con.execute("UPDATE ranking_empresa SET posicao=?, pct_total=? WHERE ano=? AND entidade_id=?", (pos[r[0]], novo_pct, a, r[0]))
            if r[2] is not None and r[2] != pos[r[0]]:
                R["posicoes"].setdefault(a, []).append((r[0], r[2], pos[r[0]]))
            if r[3] is not None and r[3] != novo_pct:
                R["pct"].setdefault(a, []).append((r[0], r[3], novo_pct))
    return R
