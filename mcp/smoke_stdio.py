#!/usr/bin/env python3
"""Sobe `python3 mcp/server.py` por stdio, faz initialize + tools/list + uma chamada. Usa uma cópia temporária do banco.
Uso: python3 mcp/smoke_stdio.py"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAIZ = Path(__file__).resolve().parent.parent


async def main():
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(RAIZ / "data" / "linha-do-tempo.sqlite", tmp / "db.sqlite")
    env = dict(os.environ, LDT_DB=str(tmp / "db.sqlite"), LDT_DUMP=str(tmp / "dump.sql"))
    params = StdioServerParameters(command=sys.executable, args=[str(RAIZ / "mcp" / "server.py")], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("servidor:", init.server_info.name)
            tools = await s.list_tools()
            for t in tools.tools:
                print(" -", t.name, "|", sorted(t.input_schema.get("properties", {})))
            res = await s.call_tool("buscar_entidade", {"consulta": "Vorcaro", "limite": 2})
            print("buscar_entidade('Vorcaro') ->", json.loads(res.content[0].text)["id"] if not res.is_error else res)
            res = await s.call_tool("listar_temas", {})
            temas = [json.loads(c.text)["id"] for c in res.content] if not res.is_error else res
            print("listar_temas ->", temas)
            res = await s.call_tool("resumo_banco", {})
            print("resumo_banco ->", res.content[0].text[:160], "...")
    shutil.rmtree(tmp)


asyncio.run(main())
