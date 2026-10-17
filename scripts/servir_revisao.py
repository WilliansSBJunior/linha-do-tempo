#!/usr/bin/env python3
"""Página LOCAL da fila de revisão (ferramentas/revisao.html) + API JSON. Não vai para o GitHub Pages.

Uso: python3 scripts/servir_revisao.py [--porta 8765] [--host 127.0.0.1] [--db data/linha-do-tempo.sqlite]
Abra http://127.0.0.1:8765/

Rotas:
  GET  /                     ferramentas/revisao.html
  GET  /api/pendencias       ?tipo=relacao|corte|evento_natureza|evento_fusao|entidade &tema=slug &limite=50 &similares=0|1
  GET  /api/decisoes         ?limite=20
  POST /api/decidir          JSON {tipo: relacao|corte|evento|entidade|desfazer, id, acao, alvo_id?, natureza?, campos?, motivo?}
                             (entidade: {tipo:'entidade', id: de, alvo_id: para}; desfazer: {tipo:'desfazer', id: decisao_id})
As funções chamadas são as MESMAS de mcp/revisao.py (e o mesmo lock de escrita do servidor MCP: threading.Lock + flock em
<pasta do banco>/.mcp-escrita.lock + BEGIN IMMEDIATE), então a página e o MCP podem rodar ao mesmo tempo.
Escuta só em 127.0.0.1 por padrão; POST exige Content-Type application/json e Origin local (barra formulário de outro site).
"""
import argparse
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "ferramentas" / "revisao.html"
sys.path.insert(0, str(RAIZ / "mcp"))
sys.path.insert(0, str(RAIZ / "scripts"))
R = None  # mcp/revisao.py, importado em main() depois do env


def decidir(d):
    if not isinstance(d, dict):
        return {"ok": False, "erro": "corpo deve ser um objeto JSON"}
    tipo, i = d.get("tipo"), d.get("id")
    if i in (None, ""):
        return {"ok": False, "erro": "id é obrigatório"}
    if tipo == "relacao":
        return R.revisar_relacao_core(i, d.get("acao"), d.get("alvo_id"), d.get("campos"), d.get("motivo"))
    if tipo == "corte":
        return R.revisar_corte_core(i, d.get("acao"), d.get("campos"), d.get("motivo"))
    if tipo == "evento":
        return R.revisar_evento_core(i, d.get("acao"), d.get("alvo_id"), d.get("natureza"), d.get("campos"), d.get("motivo"))
    if tipo == "entidade":
        return R.fundir_entidade_core(i, d.get("alvo_id") or (d.get("campos") or {}).get("para"), d.get("motivo"))
    if tipo == "desfazer":
        return R.desfazer_core(i, d.get("motivo"))
    return {"ok": False, "erro": f"tipo '{tipo}' inválido", "validos": ["relacao", "corte", "evento", "entidade", "desfazer"]}


class H(BaseHTTPRequestHandler):
    server_version = "revisao-ldt/1"

    def log_message(self, fmt, *a):
        if os.environ.get("LDT_REVISAO_LOG") == "1":
            super().log_message(fmt, *a)

    def _json(self, obj, codigo=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlsplit(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/revisao.html", "/index.html"):
                b = PAGINA.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/api/pendencias":
                self._json(R.listar_pendencias_core(q.get("tipo") or None, q.get("tema") or None, int(q.get("limite") or 50),
                                                    q.get("similares", "1") != "0"))
            elif u.path == "/api/decisoes":
                self._json(R.listar_decisoes_core(int(q.get("limite") or 20)))
            else:
                self._json({"ok": False, "erro": "rota inexistente"}, 404)
        except Exception as e:
            traceback.print_exc()
            self._json({"ok": False, "erro": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/decidir":
            return self._json({"ok": False, "erro": "rota inexistente"}, 404)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"ok": False, "erro": "use Content-Type: application/json"}, 415)
        org = self.headers.get("Origin")
        if org and urlsplit(org).hostname not in ("127.0.0.1", "localhost", "::1", self.server.server_address[0]):
            return self._json({"ok": False, "erro": f"origem recusada: {org}"}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n) or b"{}")
            out = decidir(d)
            self._json(out, 200 if out.get("ok") else 422)
        except json.JSONDecodeError as e:
            self._json({"ok": False, "erro": f"JSON inválido: {e}"}, 400)
        except Exception as e:
            traceback.print_exc()
            self._json({"ok": False, "erro": f"{type(e).__name__}: {e}"}, 500)


def main(argv=None):
    global R
    ap = argparse.ArgumentParser(description="Página local da fila de revisão")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--db", default=None, help="padrão: LDT_DB ou data/linha-do-tempo.sqlite")
    ap.add_argument("--dump", default=None, help="padrão: LDT_DUMP ou <pasta do banco>/dump.sql")
    a = ap.parse_args(argv)
    if a.db:
        os.environ["LDT_DB"] = str(Path(a.db).resolve())
        if not a.dump and not os.environ.get("LDT_DUMP"):
            os.environ["LDT_DUMP"] = str(Path(a.db).resolve().parent / "dump.sql")
    if a.dump:
        os.environ["LDT_DUMP"] = str(Path(a.dump).resolve())
    import revisao
    R = revisao
    S = R.S()
    S.preparar()
    srv = ThreadingHTTPServer((a.host, a.porta), H)
    print(f"fila de revisão em http://{a.host}:{srv.server_address[1]}/  (banco {S.caminho_db()}, decisões {R.caminho_decisoes()})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
