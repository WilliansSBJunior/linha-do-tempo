#!/usr/bin/env python3
"""Gera (ou regenera) os JSON de curadoria que são DERIVADOS por regra:

  data/curadoria/eventos-natureza.json       natureza dos eventos da teia sem `st` (regras R1-R4 na teia, R5 em brasil/violencia; curadoria.py)
  data/curadoria/brasil-fontes.json          fontes dos eventos da timeline Brasil, casadas com data/raw/dados-brutos-31-anos.json
  data/curadoria/brasil-complementos.json    receita das empresas e períodos de mandato vindos do bruto
  data/curadoria/evento-entidade-auto.json   evento -> entidade por alias (regras em evento-entidade-regras.json)
  data/curadoria/mandato-oficial.json        mandatos confirmados/divergentes contra data/raw/oficial/ (+ data/relatorio-mandatos-oficial.md)

Os demais arquivos (eventos-fusoes.json, dossie-entidades.json, evento-entidade-regras.json) são editados à mão.
O gerador constrói um banco temporário com migrar.main(pular=...) (para não partir de um banco que já tem o resultado
aplicado), lê e escreve os JSON. Depois rode migrar.py normalmente.

Uso: python3 scripts/gerar_curadoria.py [--so natureza,fontes,complementos,ligacoes,mandato-oficial]
"""
import argparse
import collections
import json
import tempfile
from pathlib import Path

import curadoria
import migrar
from comum import RAW, conectar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="natureza,fontes,complementos,ligacoes,mandato-oficial")
    a = ap.parse_args()
    quais = {"natureza" if x == "eventos-natureza" else x for x in a.so.split(",")}
    bruto = json.loads((RAW / "dados-brutos-31-anos.json").read_text(encoding="utf-8"))
    brasil = json.loads((RAW / "brasil.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as t:
        db = Path(t) / "gerar.sqlite"
        migrar.main(destino=db, pular={"natureza", "ligacoes", "fontes_brasil", "complementos", "mandato_oficial"}, escrever=False)
        con = conectar(db)
        if "fontes" in quais:
            fontes, sem = curadoria.gerar_fontes_brasil(con, bruto)
            curadoria.salvar_json("brasil-fontes.json", fontes)
            print(f"brasil-fontes.json: {len(fontes)} eventos casados, {len(sem)} sem item no bruto")
        if "complementos" in quais:
            comp = curadoria.gerar_complementos_brasil(con, bruto, brasil)
            curadoria.salvar_json("brasil-complementos.json", comp)
            print(f"brasil-complementos.json: receita {len(comp['receita'])}, períodos de mandato {len(comp['mandato_periodo'])}")
        if "ligacoes" in quais:
            lig = curadoria.gerar_ligacoes(con)
            curadoria.salvar_json("evento-entidade-auto.json", lig)
            print(f"evento-entidade-auto.json: {len(lig)} eventos, {sum(len(x['entidades']) for x in lig)} ligações")
        if "mandato-oficial" in quais:
            mo = curadoria.gerar_mandato_oficial(con)
            curadoria.salvar_json("mandato-oficial.json", mo)
            nomes = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM entidade")}
            curadoria.RELATORIO_MANDATO_OFICIAL.write_text(curadoria.relatorio_mandato_oficial(mo, nomes) + "\n", encoding="utf-8")
            print("mandato-oficial.json:", mo["resumo"])
        con.close()
        if "natureza" in quais:
            # R5 precisa das fontes da timeline (brasil-fontes.json já aplicado, inclusive o que acabou de ser regerado acima)
            db2 = Path(t) / "natureza.sqlite"
            migrar.main(destino=db2, pular={"natureza", "ligacoes", "complementos", "mandato_oficial"}, escrever=False)
            con = conectar(db2)
            nat = curadoria.gerar_natureza(con)
            curadoria.salvar_json("eventos-natureza.json", nat)
            por = collections.Counter(i["regra"].split(":")[0] for i in nat)
            print(f"eventos-natureza.json: {len(nat)} eventos (" + ", ".join(f"{k} {v}" for k, v in sorted(por.items())) + ")")
            con.close()


if __name__ == "__main__":
    main()
