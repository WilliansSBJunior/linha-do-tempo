#!/usr/bin/env python3
"""Título e data das fontes (evidência) ligadas a relações da teia.

A abertura das páginas NÃO é feita aqui (stdlib, sem rede): é feita com a ferramenta WebFetch do agente, que grava o resultado em
data/curadoria/evidencia-metadados.json (`[{"url","titulo","data","status"}]`). Este script:

  --listar [--limite N] [--json]   URLs pendentes (titulo ou data NULL no banco, ainda sem entrada no arquivo), na ordem de prioridade:
                                   relações do tema caso-master primeiro, depois o resto da teia; dentro de cada faixa, mais ligações primeiro.
  --incorporar LOTE.json           mescla um lote `[{"url","titulo","data","status"}]` no arquivo (entrada nova substitui a da mesma URL
                                   só se a antiga não era "ok"); valida antes de gravar.
  --validar                        confere o arquivo (formato, datas AAAA-MM-DD, status, URLs existentes no banco). Código 1 se falhar.

Regras: status "ok" ou "erro: motivo". titulo = <title>/og:title sem o sufixo do veículo; data = published_time/og/data visível em AAAA-MM-DD,
senão null. Nunca inventar. `curadoria.aplicar_evidencia_metadados` (em migrar.py) aplica o arquivo só onde titulo/data estão NULL.
"""
import argparse
import json
import re
import sys

from comum import CURADORIA, SQLITE, conectar
from curadoria import ler_json

ARQ = CURADORIA / "evidencia-metadados.json"
DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
CHAVES = {"url", "titulo", "data", "status"}


def pendentes(con, feitos):
    """[(url, ligacoes, caso_master)] ordenado por caso_master desc, ligacoes desc, url."""
    rows = con.execute("""
        SELECT e.url, count(DISTINCT re.relacao_id) AS lig,
               max(EXISTS(SELECT 1 FROM relacao_tema t WHERE t.relacao_id=r.id AND t.tema_id='caso-master')) AS cm
          FROM evidencia e
          JOIN relacao_evidencia re ON re.evidencia_id=e.id
          JOIN relacao r ON r.id=re.relacao_id AND r.origem='teia'
         WHERE e.titulo IS NULL OR e.data IS NULL
         GROUP BY e.id
         ORDER BY cm DESC, lig DESC, e.url""").fetchall()
    return [(u, l, c) for u, l, c in rows if u not in feitos]


def erros_arquivo(dados, con=None):
    erros, vistos = [], set()
    if not isinstance(dados, list):
        return ["o arquivo deve ser uma lista"]
    for i, m in enumerate(dados):
        ref = f"[{i}] {m.get('url') if isinstance(m, dict) else m!r}"
        if not isinstance(m, dict) or set(m) != CHAVES:
            erros.append(f"{ref}: chaves devem ser exatamente {sorted(CHAVES)}")
            continue
        if m["url"] in vistos:
            erros.append(f"{ref}: URL repetida")
        vistos.add(m["url"])
        st = m["status"]
        if not (st == "ok" or (isinstance(st, str) and st.startswith("erro: ") and len(st) > 6)):
            erros.append(f"{ref}: status deve ser 'ok' ou 'erro: motivo'")
        if m["data"] is not None and not (isinstance(m["data"], str) and DATA_ISO.fullmatch(m["data"])):
            erros.append(f"{ref}: data deve ser AAAA-MM-DD ou null")
        if m["titulo"] is not None and (not isinstance(m["titulo"], str) or not m["titulo"].strip()):
            erros.append(f"{ref}: titulo deve ser texto não vazio ou null")
        if st == "ok" and m["titulo"] is None and m["data"] is None:
            erros.append(f"{ref}: status ok sem titulo nem data")
        if st != "ok" and (m["titulo"] is not None or m["data"] is not None):
            erros.append(f"{ref}: entrada com erro não deve ter titulo/data")
        if con is not None and not con.execute("SELECT 1 FROM evidencia WHERE url=?", (m["url"],)).fetchone():
            erros.append(f"{ref}: URL não existe em evidencia")
    return erros


def salvar(dados):
    ARQ.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(SQLITE))
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--incorporar")
    ap.add_argument("--validar", action="store_true")
    a = ap.parse_args()
    con = conectar(a.db)
    atual = ler_json("evidencia-metadados.json", [])
    if a.listar:
        p = pendentes(con, {m["url"] for m in atual})
        if a.limite:
            p = p[:a.limite]
        if a.json:
            print(json.dumps([u for u, _, _ in p], ensure_ascii=False, indent=1))
        else:
            for u, l, c in p:
                print(f"{l}\t{'caso-master' if c else 'outros'}\t{u}")
        print(f"# {len(p)} pendente(s)", file=sys.stderr)
    elif a.incorporar:
        lote = json.loads(open(a.incorporar, encoding="utf-8").read())
        er = erros_arquivo(lote, con)
        if er:
            sys.exit("lote inválido:\n  " + "\n  ".join(er))
        idx = {m["url"]: i for i, m in enumerate(atual)}
        for m in lote:
            if m["url"] in idx:
                if atual[idx[m["url"]]]["status"] == "ok":
                    continue
                atual[idx[m["url"]]] = m
            else:
                atual.append(m)
        er = erros_arquivo(atual, con)
        if er:
            sys.exit("arquivo resultante inválido:\n  " + "\n  ".join(er))
        salvar(atual)
        print(f"{len(atual)} entrada(s) em {ARQ.name} ({sum(m['status'] == 'ok' for m in atual)} ok)")
    elif a.validar:
        er = erros_arquivo(atual, con)
        for e in er:
            print("FALHA", e)
        print(f"{len(atual)} entrada(s); {len(er)} falha(s)")
        sys.exit(1 if er else 0)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
