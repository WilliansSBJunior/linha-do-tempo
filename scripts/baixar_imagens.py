#!/usr/bin/env python3
"""Baixa as fotos do manifesto, recorta 256x256 (centro) e salva JPEG q85.

Etapa 1: itens com status "ok" (URL oficial confirmada).
Etapa 2 ("commons"): itens tipo "foto" com status "pendente" e campo `wiki_pt`
(verbete da Wikipédia pt) ou `commons_file` ("File:Nome.jpg", tem prioridade).
Só aceita licença livre (CC BY*, CC0, domínio público/PD); senão fica "pendente"
com `motivo`. Logos nunca são baixados.

Uso: python scripts/baixar_imagens.py
Idempotente: itens "baixado" são ignorados.
"""
import html
import io
import json
import re
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO = RAIZ / "data" / "imagens" / "manifest.json"
TAM = 256
HEADERS = {
    "User-Agent": "linha-do-tempo-imagens/1.0 (projeto Linha do Tempo, teia do Caso Master; willians.sbjr@gmail.com) python-requests"
}
WIKI_API = "https://pt.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
LICENCA_LIVRE = re.compile(r"^\s*(CC[ -]?BY|CC[ -]?0|CC0|Public domain|PD\b|Domínio público|Attribution)", re.I)  # "Attribution" é o modelo livre do Commons (crédito obrigatório)


def salvar(conteudo, destino):
    img = Image.open(io.BytesIO(conteudo))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (TAM, TAM), Image.LANCZOS, centering=(0.5, 0.3))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "JPEG", quality=85, optimize=True)


def baixar(item, destino):
    r = requests.get(item["url"], headers=HEADERS, timeout=60)
    r.raise_for_status()
    salvar(r.content, destino)


def limpa(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def nome_do_arquivo(item):
    """Retorna 'File:Nome.ext' a partir de commons_file ou do verbete wiki_pt."""
    if item.get("commons_file"):
        f = item["commons_file"].strip()
        return f if f.lower().startswith("file:") else "File:" + f
    r = requests.get(WIKI_API, headers=HEADERS, timeout=30, params={
        "action": "query", "prop": "pageimages", "piprop": "name", "titles": item["wiki_pt"],
        "redirects": 1, "format": "json"})
    r.raise_for_status()
    paginas = r.json().get("query", {}).get("pages", {})
    for p in paginas.values():
        if "missing" in p:
            raise LookupError(f"verbete inexistente: {item['wiki_pt']}")
        if p.get("pageimage"):
            return "File:" + p["pageimage"]
    raise LookupError(f"verbete sem imagem principal: {item['wiki_pt']}")


def etapa_commons(item, destino):
    """Atualiza item e salva a imagem; retorna True se baixou."""
    arquivo = nome_do_arquivo(item)
    r = requests.get(COMMONS_API, headers=HEADERS, timeout=30, params={
        "action": "query", "titles": arquivo, "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 512, "format": "json"})
    r.raise_for_status()
    pg = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
    info = (pg.get("imageinfo") or [None])[0]
    if not info:
        raise LookupError(f"arquivo não encontrado no Commons: {arquivo}")
    meta = info.get("extmetadata", {})
    licenca = limpa(meta.get("LicenseShortName", {}).get("value"))
    if not licenca or not LICENCA_LIVRE.match(licenca):
        item["motivo"] = f"Commons: licença não livre ou não encontrada ({licenca or 'ausente'})"
        item["pagina"] = "https://commons.wikimedia.org/wiki/" + arquivo.replace(" ", "_")
        return False
    url = info.get("thumburl") or info["url"]
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    salvar(resp.content, destino)
    item.update({
        "status": "baixado",
        "url": url,
        "origem": "Wikimedia Commons",
        "licenca": licenca,
        "autor": limpa(meta.get("Artist", {}).get("value")),
        "pagina": "https://commons.wikimedia.org/wiki/" + arquivo.replace(" ", "_"),
        "arquivo": item.get("arquivo") or str(destino.relative_to(RAIZ)),
    })
    item.pop("motivo", None)
    item.pop("erro", None)
    return True


def main():
    m = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    mudou = False
    cont = {"baixado": 0, "erro": 0, "commons_baixado": 0, "commons_recusado": 0, "commons_falha": 0}
    for id_, item in m["itens"].items():
        destino = RAIZ / item.get("arquivo", f"data/imagens/{id_}.jpg")
        if item.get("status") == "ok":
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
    for id_, item in m["itens"].items():
        if item.get("tipo") != "foto" or item.get("status") != "pendente":
            continue
        if not (item.get("wiki_pt") or item.get("commons_file")):
            continue
        item.setdefault("arquivo", f"data/imagens/{id_}.jpg")
        destino = RAIZ / item["arquivo"]
        try:
            if etapa_commons(item, destino):
                cont["commons_baixado"] += 1
            else:
                cont["commons_recusado"] += 1
        except Exception as e:  # noqa: BLE001
            item["motivo"] = f"Commons: {type(e).__name__}: {e}"[:300]
            cont["commons_falha"] += 1
            print(f"COMMONS {id_}: {item['motivo']}", file=sys.stderr)
        mudou = True
    if mudou:
        MANIFESTO.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(cont)
    return 0


if __name__ == "__main__":
    sys.exit(main())
