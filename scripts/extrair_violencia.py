#!/usr/bin/env python3
"""Extrai os literais JS de paginas/violencia.html (SOURCES, DATA, GROUPS, CSRC, RACE_RATES, MARCOS, CUTS)
avaliando o trecho com Node e grava data/raw/violencia.json. Rodado uma vez; migrar.py lê só o JSON congelado."""
import json, re, subprocess, sys
from comum import ROOT, RAW

html = (ROOT / "paginas" / "violencia.html").read_text(encoding="utf-8")
ini = html.index("  var SOURCES = {")
fim = html.index("  // Linha do tempo contínua")
trecho = html[ini:fim]
js = ("var TOT_MAPA, TOT_CONT;\n" + trecho +
      "\nprocess.stdout.write(JSON.stringify({SOURCES:SOURCES,DATA:DATA,SOURCE_BREAK_AFTER:SOURCE_BREAK_AFTER,"
      "GROUPS:GROUPS,TIPO_TXT:TIPO_TXT,CSRC:CSRC,RACE_RATES:RACE_RATES,MARCOS:MARCOS,CUTS:CUTS}));")
r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stderr)
d = json.loads(r.stdout)
(RAW / "violencia.json").write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in d.items()})
