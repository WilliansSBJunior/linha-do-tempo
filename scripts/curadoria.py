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
    Troca `mandato.<campo>` de `de` para `para` na linha (entidade_id, cargo, inicio); falha se a linha não existe ou o valor atual não é `de`
    (a correção ficou obsoleta ou o dado mudou). Roda depois da carga e antes de aplicar_mandato_oficial / gerar_relacoes_mandato."""
    r = {"aplicadas": []}
    for c in ler_json("mandato-correcoes.json", []):
        if c["campo"] not in ("partido", "uf"):
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
