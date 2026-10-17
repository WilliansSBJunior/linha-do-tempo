#!/usr/bin/env python3
"""Coleta, nas APIs oficiais da Câmara e do Senado, os mandatos e filiações dos parlamentares
que constam em `mandato` (e as páginas oficiais da Presidência e das presidências das Casas),
gravando tudo em data/raw/oficial/. Roda na SUA máquina (precisa de internet sem proxy).

    python3 scripts/importar.py          # se data/linha-do-tempo.sqlite não existir
    python3 scripts/coletar_mandatos.py  # [--so camara|senado|presidencia] [--forcar]

Cada resposta HTTP é guardada em data/raw/oficial/cache/<sha>.json (ou .html) e nunca é
baixada de novo, a não ser com --forcar. O resultado consolidado vai para
data/raw/oficial/{camara,senado,presidencia}.json e o relatório para
data/raw/oficial/RELATORIO.md. Depois: git add data/raw/oficial && git commit && git push.

Só stdlib. Nada é inventado: o que a API não devolver fica como "nao_encontrado".
"""
import argparse, hashlib, json, re, sqlite3, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE = ROOT / "data" / "linha-do-tempo.sqlite"
OFICIAL = ROOT / "data" / "raw" / "oficial"
CACHE = OFICIAL / "cache"
UA = "linha-do-tempo/1.0 (coleta de dados abertos; github.com/WilliansSBJunior/linha-do-tempo)"

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
LEGISLATURAS = list(range(50, 58))  # 50 = 1995-1999 ... 57 = 2023-2027

PAGINAS = {  # páginas oficiais guardadas como evidência (HTML bruto no cache)
    "presidentes_republica": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia/acervo/galeria-de-presidentes",
    "vice_presidentes": "https://www.gov.br/planalto/pt-br/vice-presidencia/galeria-de-vice-presidentes",
    "presidentes_camara": "https://www.camara.leg.br/a-camara/conheca/presidentes-da-camara",
    "presidentes_senado": "https://www25.senado.leg.br/web/senadores/presidentes-do-senado",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def baixar(url, json_=True, forcar=False, tentativas=3):
    """Baixa com cache em disco. Devolve (objeto|texto, caminho_cache, status)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(url.encode()).hexdigest()[:20]
    arq = CACHE / (h + (".json" if json_ else ".html"))
    if arq.exists() and not forcar:
        txt = arq.read_text(encoding="utf-8")
        return (json.loads(txt) if json_ else txt), arq, "cache"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json" if json_ else "text/html"})
    erro = None
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode("utf-8", "replace")
            if json_:
                obj = json.loads(txt)
                arq.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
                return obj, arq, "ok"
            arq.write_text(txt, encoding="utf-8")
            return txt, arq, "ok"
        except urllib.error.HTTPError as e:
            erro = f"HTTP {e.code}"
            if e.code == 404:
                break
            time.sleep(2 * (i + 1))
        except Exception as e:  # rede, JSON inválido
            erro = repr(e)
            time.sleep(2 * (i + 1))
    return None, arq, "erro: " + str(erro)


def pessoas_do_banco():
    if not SQLITE.exists():
        sys.exit("data/linha-do-tempo.sqlite não existe: rode `python3 scripts/importar.py` antes")
    con = sqlite3.connect(SQLITE)
    rows = con.execute("""SELECT e.id, e.nome, m.cargo, m.uf, m.partido, m.inicio, m.fim
                          FROM mandato m JOIN entidade e ON e.id=m.entidade_id ORDER BY e.nome, m.inicio""").fetchall()
    alias = {}
    for eid, a in con.execute("SELECT entidade_id, alias FROM entidade_alias"):
        alias.setdefault(eid, []).append(a)
    con.close()
    pessoas = {}
    for eid, nome, cargo, uf, partido, ini, fim in rows:
        p = pessoas.setdefault(eid, {"id": eid, "nome": nome, "aliases": alias.get(eid, []), "cargos": set(), "ufs": set(), "anos": set(), "partidos": set()})
        p["cargos"].add(cargo); p["anos"].add(int(ini[:4]))
        if uf: p["ufs"].add(uf)
        if partido: p["partidos"].add(partido)
    for p in pessoas.values():
        for k in ("cargos", "ufs", "anos", "partidos"):
            p[k] = sorted(p[k])
    return pessoas


def casa_de(p):
    c = set(p["cargos"])
    casas = set()
    if c & {"deputado", "presidente_camara"}: casas.add("camara")
    if c & {"senador", "presidente_senado"}: casas.add("senado")
    if c & {"presidente", "vice_presidente"}: casas.add("presidencia")
    return casas


def match_nome(alvo, candidatos, chave):
    """Escolhe o candidato cujo nome (normalizado) é igual ou contém/é contido pelo alvo."""
    a = norm(alvo)
    toks = set(a.split())
    exatos = [c for c in candidatos if norm(c[chave]) == a]
    if len(exatos) == 1:
        return exatos[0], "exato"
    parciais = [c for c in candidatos if toks and (toks <= set(norm(c[chave]).split()) or set(norm(c[chave]).split()) <= toks)]
    if len(parciais) == 1:
        return parciais[0], "parcial"
    return None, ("ambiguo:%d" % len(parciais or exatos)) if (parciais or exatos) else "nenhum"


# ------------------------------------------------------------------ CÂMARA
def coletar_camara(pessoas, forcar, rel):
    out = {"fonte": CAMARA, "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "legislaturas": {}, "deputados": {}}
    for leg in LEGISLATURAS:
        obj, arq, st = baixar(f"{CAMARA}/legislaturas/{leg}", forcar=forcar)
        if obj:
            d = obj.get("dados", {})
            out["legislaturas"][leg] = {"dataInicio": d.get("dataInicio"), "dataFim": d.get("dataFim"), "url": f"{CAMARA}/legislaturas/{leg}"}
        rel.append(f"camara legislatura {leg}: {st}")
    for eid, p in sorted(pessoas.items()):
        if "camara" not in casa_de(p):
            continue
        reg = {"id_entidade": eid, "nome_banco": p["nome"], "busca": [], "deputado": None, "mandatos": [], "historico_url": None, "status": None}
        nomes = [p["nome"]] + [a for a in p["aliases"] if len(a.split()) >= 2]
        cand = []
        for nome in nomes:
            q = urllib.parse.quote(nome)
            for leg in LEGISLATURAS:
                url = f"{CAMARA}/deputados?nome={q}&idLegislatura={leg}&itens=100&ordem=ASC&ordenarPor=nome"
                obj, arq, st = baixar(url, forcar=forcar)
                reg["busca"].append({"nome": nome, "legislatura": leg, "status": st, "url": url})
                if obj:
                    for d in obj.get("dados", []):
                        d["_legislatura"] = leg
                        cand.append(d)
            if cand:
                break
        # mesmo deputado (id) em várias legislaturas
        por_id = {}
        for d in cand:
            por_id.setdefault(d["id"], {"id": d["id"], "nome": d["nome"], "legs": []})["legs"].append(d)
        escolhido, como = match_nome(p["nome"], list(por_id.values()), "nome")
        if not escolhido:
            # tenta pelos aliases
            for a in p["aliases"]:
                escolhido, como = match_nome(a, list(por_id.values()), "nome")
                if escolhido:
                    break
        if not escolhido:
            reg["status"] = "nao_encontrado:" + como
            out["deputados"][eid] = reg
            rel.append(f"camara {p['nome']}: NÃO encontrado ({como})")
            continue
        reg["deputado"] = {"id": escolhido["id"], "nome": escolhido["nome"], "match": como, "url": f"{CAMARA}/deputados/{escolhido['id']}"}
        for d in escolhido["legs"]:
            leg = d["_legislatura"]
            lg = out["legislaturas"].get(leg, {})
            reg["mandatos"].append({"legislatura": leg, "siglaPartido": d.get("siglaPartido"), "siglaUf": d.get("siglaUf"),
                                    "dataInicio": lg.get("dataInicio"), "dataFim": lg.get("dataFim"), "url": d.get("uri"),
                                    "url_lista": f"{CAMARA}/deputados?idLegislatura={leg}&nome={urllib.parse.quote(escolhido['nome'])}"})
        # histórico de situação/partido (mudanças com data)
        hurl = f"{CAMARA}/deputados/{escolhido['id']}/historico"
        obj, arq, st = baixar(hurl, forcar=forcar)
        reg["historico_url"] = hurl
        reg["historico"] = obj.get("dados", []) if obj else None
        reg["historico_status"] = st
        reg["status"] = "ok"
        out["deputados"][eid] = reg
        rel.append(f"camara {p['nome']}: ok ({como}, {len(reg['mandatos'])} legislaturas, histórico {st})")
        time.sleep(0.3)
    return out


# ------------------------------------------------------------------ SENADO
def coletar_senado(pessoas, forcar, rel):
    out = {"fonte": SENADO, "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "listas": {}, "senadores": {}}
    todos = {}
    for leg in LEGISLATURAS:
        url = f"{SENADO}/senador/lista/legislatura/{leg}"
        obj, arq, st = baixar(url, forcar=forcar)
        out["listas"][leg] = {"url": url, "status": st}
        rel.append(f"senado lista legislatura {leg}: {st}")
        if not obj:
            continue
        try:
            parls = obj["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"]
        except (KeyError, TypeError):
            parls = []
        for pr in parls:
            ident = pr.get("IdentificacaoParlamentar", {})
            cod = ident.get("CodigoParlamentar")
            if not cod:
                continue
            t = todos.setdefault(cod, {"codigo": cod, "nome": ident.get("NomeParlamentar"), "nome_completo": ident.get("NomeCompletoParlamentar"), "legs": []})
            t["legs"].append({"legislatura": leg, "partido": ident.get("SiglaPartidoParlamentar"), "uf": ident.get("UfParlamentar"),
                              "mandato": pr.get("Mandato")})
    cands = list(todos.values())
    for eid, p in sorted(pessoas.items()):
        if "senado" not in casa_de(p):
            continue
        reg = {"id_entidade": eid, "nome_banco": p["nome"], "senador": None, "legislaturas": [], "mandatos_url": None, "filiacoes_url": None, "status": None}
        esc, como = match_nome(p["nome"], cands, "nome")
        if not esc:
            esc, como = match_nome(p["nome"], cands, "nome_completo")
        if not esc:
            for a in p["aliases"]:
                esc, como = match_nome(a, cands, "nome")
                if esc:
                    break
        if not esc:
            reg["status"] = "nao_encontrado:" + como
            out["senadores"][eid] = reg
            rel.append(f"senado {p['nome']}: NÃO encontrado ({como})")
            continue
        cod = esc["codigo"]
        reg["senador"] = {"codigo": cod, "nome": esc["nome"], "nome_completo": esc["nome_completo"], "match": como, "url": f"{SENADO}/senador/{cod}"}
        reg["legislaturas"] = esc["legs"]
        for chave, caminho in (("mandatos", "mandatos"), ("filiacoes", "filiacoes")):
            url = f"{SENADO}/senador/{cod}/{caminho}"
            obj, arq, st = baixar(url, forcar=forcar)
            reg[chave + "_url"] = url
            reg[chave] = obj
            reg[chave + "_status"] = st
        reg["status"] = "ok"
        out["senadores"][eid] = reg
        rel.append(f"senado {p['nome']}: ok ({como}, {len(esc['legs'])} legislaturas)")
        time.sleep(0.3)
    return out


# ------------------------------------------------------------------ PRESIDÊNCIA E PRESIDÊNCIAS DAS CASAS
def coletar_paginas(forcar, rel):
    out = {"coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "paginas": {}}
    for chave, url in PAGINAS.items():
        txt, arq, st = baixar(url, json_=False, forcar=forcar)
        out["paginas"][chave] = {"url": url, "status": st, "arquivo_cache": str(arq.relative_to(ROOT)) if txt else None,
                                 "titulo": (re.search(r"<title>(.*?)</title>", txt, re.S | re.I).group(1).strip() if txt else None),
                                 "tamanho": len(txt) if txt else 0}
        rel.append(f"pagina {chave}: {st}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", choices=["camara", "senado", "presidencia"])
    ap.add_argument("--forcar", action="store_true", help="ignora o cache")
    a = ap.parse_args()
    OFICIAL.mkdir(parents=True, exist_ok=True)
    pessoas = pessoas_do_banco()
    rel = [f"# Coleta oficial — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
           f"Pessoas com mandato no banco: {len(pessoas)}", ""]
    if a.so in (None, "camara"):
        (OFICIAL / "camara.json").write_text(json.dumps(coletar_camara(pessoas, a.forcar, rel), ensure_ascii=False, indent=1), encoding="utf-8")
    if a.so in (None, "senado"):
        (OFICIAL / "senado.json").write_text(json.dumps(coletar_senado(pessoas, a.forcar, rel), ensure_ascii=False, indent=1), encoding="utf-8")
    if a.so in (None, "presidencia"):
        (OFICIAL / "presidencia.json").write_text(json.dumps(coletar_paginas(a.forcar, rel), ensure_ascii=False, indent=1), encoding="utf-8")
    (OFICIAL / "RELATORIO.md").write_text("\n".join(rel) + "\n", encoding="utf-8")
    print("\n".join(rel))
    print("\nPronto. Agora: git add data/raw/oficial && git commit -m 'Coleta oficial de mandatos' && git push")


if __name__ == "__main__":
    main()
