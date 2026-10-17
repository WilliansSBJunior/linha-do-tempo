"""Curadoria: aplica os arquivos de data/curadoria/ ao banco depois da carga bruta e contém as regras que os geram.

migrar.py chama as funções `aplicar_*`; gerar_curadoria.py chama as funções `gerar_*` e escreve os JSON.
Só stdlib. Nada aqui edita o banco fora de migrar.py (que recria o banco do zero a cada execução).
"""
import collections
import json
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from comum import CURADORIA, RAW, dominio_de, normalizar_url
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
Precedência: R1, R2, R3, R4. Só se aplica a eventos do canal 'teia' com natureza_id NULL."""


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
    return out


def aplicar_natureza(con):
    itens = ler_json("eventos-natureza.json", [])
    aplicados = ignorados = 0
    for it in itens:
        cur = con.execute("UPDATE evento SET natureza_id=? WHERE id=? AND natureza_id IS NULL", (it["natureza"], it["id"]))
        aplicados += cur.rowcount
        ignorados += 1 - cur.rowcount
    return {"arquivo": len(itens), "aplicados": aplicados, "ignorados": ignorados,
            "por_regra": collections.Counter(i["regra"].split(":")[0] for i in itens),
            "por_natureza": collections.Counter(i["natureza"] for i in itens)}


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


# ======================================================================== 5. teia <-> timeline: mandato/bancada -> relações institucionais
def _ano(s):
    return int(str(s)[:4])


def _mais_cedo(a, b):
    return a if (_ano(a), len(str(a))) <= (_ano(b), len(str(b))) else b


def _mais_tarde(a, b):
    return a if (_ano(a), len(str(a))) >= (_ano(b), len(str(b))) else b


def gerar_relacoes_mandato(con):
    """Cria relações `institucional` (origem='linha_do_tempo', natureza documentada, status publicada) a partir de `mandato`:
      - subtipo 'mandato:<cargo>': pessoa -> órgão (Presidência, Câmara, Senado), uma por linha de `mandato`, com o período dela;
      - subtipo 'filiacao': pessoa -> partido, uma por sequência contínua de mandatos do mesmo partido (período inferido dos mandatos).
    Regras e exceções em data/curadoria/mandato-relacoes.json. Retorna dict para o relatório."""
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
    fil = collections.defaultdict(list)  # (pessoa, partido_id) -> [(inicio, fim, sigla, cargo, mandato_id, evidencia_id)]
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
        n_mand += 1
        por_cargo[m["cargo"]] += 1
        p = partido_de(m["partido"])
        if m["partido"] and p is None and m["partido"] not in sem_filiacao:
            sem_partido.append((m["id"], m["entidade_id"], m["partido"]))
        if p and p != m["entidade_id"]:
            fil[(m["entidade_id"], p)].append((m["inicio"], fim, m["partido"], m["cargo"], m["id"], m["evidencia_id"]))
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
            ev = next((i[5] for i in r["itens"] if i[5]), None)
            if ev:
                con.execute("INSERT INTO relacao_evidencia(relacao_id,evidencia_id,ordem) VALUES(?,?,0)", (cur.lastrowid, ev))
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
