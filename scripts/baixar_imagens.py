#!/usr/bin/env python3
"""Baixa as fotos do manifesto (status "ok"), recorta 256x256 (centro) e salva JPEG q85.

Uso: python scripts/baixar_imagens.py
Idempotente: itens "baixado" com arquivo existente são ignorados.
Só baixa status "ok"; logos nunca são baixados (ver data/imagens/README.md).
"""
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO = RAIZ / "data" / "imagens" / "manifest.json"
TAM = 256
HEADERS = {"User-Agent": "linha-do-tempo-imagens/1.0 (+https://github.com)"}


def baixar(item, destino):
    r = requests.get(item["url"], headers=HEADERS, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (TAM, TAM), Image.LANCZOS, centering=(0.5, 0.3))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "JPEG", quality=85, optimize=True)


def main():
    m = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    mudou = False
    cont = {"baixado": 0, "erro": 0, "ignorado": 0}
    for id_, item in m["itens"].items():
        if item.get("status") != "ok":
            cont["ignorado"] += 1
            continue
        destino = RAIZ / item.get("arquivo", f"data/imagens/{id_}.jpg")
        try:
            baixar(item, destino)
            item["status"] = "baixado"
            item.pop("erro", None)
            cont["baixado"] += 1
        except Exception as e:  # noqa: BLE001
            item["status"] = "erro"
            item["erro"] = f"{type(e).__name__}: {e}"[:300]
            cont["erro"] += 1
            print(f"ERRO {id_}: {item['erro']}", file=sys.stderr)
        mudou = True
    if mudou:
        MANIFESTO.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(cont)
    return 0


if __name__ == "__main__":
    sys.exit(main())
