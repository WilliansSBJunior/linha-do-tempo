"""Carga relacional do dossiê (mercado.pares, previdencia.entes, dinheiro.*, maquina.indicios, limites.*) e de pares.foruns.

Antes essas seções viviam em nota.texto como JSON. Cada tabela guarda o texto original e, quando possível, o vínculo com entidade.
O vínculo vem de data/curadoria/dossie-entidades.json ("mapa": texto -> lista de ids, [] = sem entidade) e, na falta dele,
de alias_norm único em entidade_alias (casamento exato, nunca por substring).
"""
import json
import re

from curadoria import ler_json
from slug import alias_norm

RELACIONAIS = {"mercado.pares", "previdencia.entes", "dinheiro.contratos", "dinheiro.midia", "dinheiro.doacoes",
               "maquina.indicios", "limites.derrubado", "limites.aberto", "limites.agenda"}
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def data_agenda(txt):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.fullmatch(r"([a-z]{3})/(\d{4})", txt.lower())
    if m and m.group(1) in MESES:
        return f"{m.group(2)}-{MESES[m.group(1)]:02d}"
    return None


def carregar(con, dossie, pares, evid, nat_map, idx_alias, pais_slug, R):
    """idx_alias: alias_norm -> set(slugs). R: dict de listas para o relatório."""
    cfg = ler_json("dossie-entidades.json", {})
    mapa = cfg.get("mapa", {})
    existentes = {r[0] for r in con.execute("SELECT id FROM entidade")}

    def resolver(texto):
        """-> (lista de slugs, como) com como em 'manual' | 'alias' | 'nenhum'."""
        if texto in mapa:
            for s in mapa[texto]:
                assert s in existentes, f"dossie-entidades.json: entidade inexistente {s!r} para {texto!r}"
            return list(mapa[texto]), "manual"
        s = idx_alias.get(alias_norm(texto), set())
        if len(s) == 1:
            return list(s), "alias"
        return [], "nenhum"

    def registra(secao, texto, ents, como):
        R["dossie_vinculos"].append((secao, texto, ents, como))

    def nz(v):
        return v if v not in ("", None) else None

    # ---- mercado.pares
    for i, p in enumerate(dossie["mercado"]["pares"]):
        ents, como = resolver(p["ator"])
        registra("mercado.pares", p["ator"], ents, como)
        for sub, ent in enumerate(ents or [None]):
            cur = con.execute("""INSERT INTO dossie_par(ordem,sub,ator_texto,ator_entidade_id,campo,partido,alavanca,recebeu,ato,liga,liga_x,natureza_id,estagio,resposta)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (i, sub, p["ator"], ent, nz(p["campo"]), nz(p["partido"]), nz(p["alavanca"]), nz(p["recebeu"]), nz(p["ato"]),
                               p["liga"], nz(p["liga_x"]), nat_map.get(p["st"]), nz(p["estagio"]), nz(p["resp"])))
            vistos = set()
            for o, (rot, url) in enumerate(p["src"]):
                eid = evid(url, rot)
                if eid in vistos:
                    continue
                vistos.add(eid)
                con.execute("INSERT INTO dossie_par_evidencia(par_id,evidencia_id,ordem,rotulo) VALUES(?,?,?,?)", (cur.lastrowid, eid, o, rot))
    # ---- previdencia.entes
    for i, e in enumerate(dossie["previdencia"]["entes"]):
        ents, como = resolver(e["n"])
        registra("previdencia.entes", e["n"], ents, como)
        assert len(ents) <= 1, e["n"]
        con.execute("""INSERT INTO previdencia_ente(ordem,nome_texto,entidade_id,uf,valor_mi,governante,partido,obs,natureza_id)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (i, e["n"], ents[0] if ents else None, nz(e["uf"]), e["v"], nz(e["gov"]), nz(e["p"]), nz(e["x"]), nat_map.get(e["st"])))
    # ---- dinheiro
    def pagamento(cat, i, row):
        ents, como = resolver(row["n"])
        registra(f"dinheiro.{cat}", row["n"], ents, como)
        assert len(ents) <= 1, row["n"]
        de = row.get("de")
        de_ents, de_como = resolver(de) if de else ([], "nenhum")
        if de:
            registra(f"dinheiro.{cat}.de", de, de_ents, de_como)
        m = re.search(r",\s*(\d{4})$", row["n"])
        con.execute("""INSERT INTO pagamento(categoria,ordem,nome_texto,para_entidade_id,valor_mi,grupo,de_texto,de_entidade_id,ano) VALUES(?,?,?,?,?,?,?,?,?)""",
                    ({"contratos": "contrato", "midia": "midia", "doacoes": "doacao"}[cat], i, row["n"], ents[0] if ents else None, row["v"],
                     nz(row.get("g")), de, de_ents[0] if de_ents else None, int(m.group(1)) if (m and cat == "doacoes") else None))

    for cat in ("contratos", "midia", "doacoes"):
        for i, row in enumerate(dossie["dinheiro"][cat]):
            pagamento(cat, i, row)
    # ---- maquina.indicios
    for i, x in enumerate(dossie["maquina"]["indicios"]):
        con.execute("INSERT INTO indicio_maquina(ordem,titulo,texto,contra,forca) VALUES(?,?,?,?,?)", (i, x["t"], x["x"], x["contra"], x["forca"]))
    # ---- limites
    for i, (afirm, porque) in enumerate(dossie["limites"]["derrubado"]):
        con.execute("INSERT INTO limite(tipo,ordem,titulo,texto) VALUES('derrubado',?,?,?)", (i, afirm, porque))
    for i, t in enumerate(dossie["limites"]["aberto"]):
        con.execute("INSERT INTO limite(tipo,ordem,texto) VALUES('aberto',?,?)", (i, t))
    for i, (d, t) in enumerate(dossie["limites"]["agenda"]):
        con.execute("INSERT INTO limite(tipo,ordem,texto,data,data_texto) VALUES('agenda',?,?,?,?)", (i, t, data_agenda(d), d))
    # ---- pares.foruns
    for iso, f in pares["foruns"].items():
        pais = pais_slug[iso]
        for chave in ("G20", "BRICS", "OCDE"):
            con.execute("INSERT INTO forum(pais_entidade_id,forum,status_texto) VALUES(?,?,?)", (pais, chave, f[chave]))
        csnu = f["CSNU"]
        if isinstance(csnu, list):
            con.execute("INSERT INTO forum(pais_entidade_id,forum,anos) VALUES(?,?,?)", (pais, "CSNU", json.dumps(csnu)))
        else:
            con.execute("INSERT INTO forum(pais_entidade_id,forum,status_texto) VALUES(?,?,?)", (pais, "CSNU", csnu))
        con.execute("INSERT INTO forum(pais_entidade_id,forum,status_texto,primeiro_teste) VALUES(?,?,?,?)",
                    (pais, "nuclear", "sim" if f["nuclear"] else "nao", f.get("primeiro_teste_nuclear")))
