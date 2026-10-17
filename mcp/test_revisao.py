#!/usr/bin/env python3
"""Testes da fila de revisão (mcp/revisao.py, scripts/aplicar_decisoes.py, scripts/servir_revisao.py + ferramentas/revisao.html).

Tudo roda numa CÓPIA do repo em diretório temporário; o banco, o dump e data/curadoria reais nunca são escritos.
Uso (da raiz do repo):  python3 mcp/test_revisao.py -v
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import server as S  # noqa: E402
import revisao as R  # noqa: E402

REAL = [RAIZ / "data" / "linha-do-tempo.sqlite", RAIZ / "data" / "dump.sql", RAIZ / "data" / "curadoria" / "eventos-fusoes.json"]
PW_BROWSERS = Path("/opt/pw-browsers")


def estado_real():
    out = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in REAL}
    out["decisoes"] = (RAIZ / "data" / "curadoria" / "decisoes.jsonl").exists()
    return out


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real0 = estado_real()
        cls.tmp = Path(tempfile.mkdtemp(prefix="ldt-revisao-"))
        cls.repo = cls.tmp / "repo"
        ign = shutil.ignore_patterns("__pycache__", "*.sqlite*", ".mcp-escrita.lock")
        for d in ("scripts", "data", "mcp", "ferramentas"):
            shutil.copytree(RAIZ / d, cls.repo / d, ignore=ign)
        (cls.repo / "data" / "curadoria" / "decisoes.jsonl").unlink(missing_ok=True)
        shutil.copy(REAL[0], cls.tmp / "base.sqlite")
        cls._env = {k: os.environ.get(k) for k in ("LDT_EMBED_PROVIDER", "LDT_DB", "LDT_DUMP", "LDT_CURADORIA", "LDT_DECISOES", "LDT_EXPORT_JSON")}
        os.environ["LDT_EMBED_PROVIDER"] = "hash"  # determinístico, sem rede (similares/dedup)
        sys.path.insert(0, str(RAIZ / "scripts"))
        import embeddings as E
        with open(os.devnull, "w") as nul:
            sys.stdout, so = nul, sys.stdout
            try:
                assert E.main(["--db", str(cls.tmp / "base.sqlite"), "--tabelas", "relacao,relacao_rotulo"]) == 0
            finally:
                sys.stdout = so
        cls.fusoes0 = (cls.repo / "data" / "curadoria" / "eventos-fusoes.json").read_bytes()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)
        assert estado_real() == cls.real0, "o banco/dump/curadoria REAL foi alterado pelos testes!"

    def setUp(self):
        self.db = self.repo / "data" / "linha-do-tempo.sqlite"
        for suf in ("", "-wal", "-shm"):
            Path(str(self.db) + suf).unlink(missing_ok=True)
        shutil.copy(self.tmp / "base.sqlite", self.db)
        shutil.copy(RAIZ / "data" / "dump.sql", self.repo / "data" / "dump.sql")
        self.cur = self.repo / "data" / "curadoria"
        (self.cur / "decisoes.jsonl").unlink(missing_ok=True)
        (self.cur / "eventos-fusoes.json").write_bytes(self.fusoes0)
        os.environ.update(LDT_DB=str(self.db), LDT_DUMP=str(self.repo / "data" / "dump.sql"), LDT_CURADORIA=str(self.cur))
        os.environ.pop("LDT_DECISOES", None)
        os.environ.pop("LDT_EXPORT_JSON", None)

    def sql(self, q, *a, db=None):
        con = sqlite3.connect(str(db or self.db))
        con.row_factory = sqlite3.Row
        try:
            return con.execute(q, a).fetchall()
        finally:
            con.close()

    def um(self, q, *a, db=None):
        r = self.sql(q, *a, db=db)
        return r[0][0] if r else None

    def jsonl(self):
        p = self.cur / "decisoes.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def validar(self):
        e = subprocess.run([sys.executable, str(self.repo / "scripts" / "exportar_json.py"), "--db", str(self.db)], capture_output=True, text=True)
        assert e.returncode == 0, e.stdout + e.stderr
        p = subprocess.run([sys.executable, str(self.repo / "scripts" / "validar.py"), "--db", str(self.db)], capture_output=True, text=True)
        return p.returncode, "\n".join(x for x in p.stdout.splitlines() if "FALHA" in x or "ERR" in x)[-2000:] + p.stderr

    def tres_relacoes(self):
        """3 relações 'revisar' + 1 'publicada' (alvo da fusão), todas novas entre entidades da teia, com evidências próprias."""
        r = self.sql("""SELECT a.id a, b.id b FROM entidade a, entidade b WHERE a.id<b.id AND a.origem='teia' AND b.origem='teia'
                        AND NOT EXISTS (SELECT 1 FROM relacao r WHERE (r.de=a.id AND r.para=b.id) OR (r.de=b.id AND r.para=a.id))
                        ORDER BY a.id, b.id LIMIT 1""", db=os.environ["LDT_DB"])[0]
        a, b = r["a"], r["b"]
        ids = []
        os.environ["LDT_DEDUP_EMBEDDING"] = "0"  # o alvo tem rótulo parecido com a 3ª de propósito; sem isto o MCP reutilizaria a 3ª
        self.addCleanup(os.environ.pop, "LDT_DEDUP_EMBEDDING", None)
        for i, rot in enumerate(["Repasse de consultoria (revisão 1)", "Encontro reservado (revisão 2)", "Pagamento a escritório (revisão 3)"]):
            out = S.inserir_relacao_core(a, b, ["financeira", "pessoal", "financeira"][i], rot, "rep", periodo_inicio="2024",
                                         evidencias=[{"url": f"https://exemplo.org/rev/{i}", "titulo": f"Reportagem {i}"}])
            self.assertTrue(out["ok"], out)
            ids.append(out["relacao_id"])
        alvo = S.inserir_relacao_core(a, b, "financeira", "Pagamentos ao escritório", "doc", periodo_inicio="2024", status="publicada",
                                      evidencias=[{"url": "https://exemplo.org/rev/alvo"}])
        self.assertTrue(alvo["ok"], alvo)
        return a, b, ids, alvo["relacao_id"]


class TestRelacoes(Base):
    def estado(self, ids, db=None):
        out = {}
        for i in ids:
            out[i] = (self.um("SELECT status FROM relacao WHERE id=?", i, db=db),
                      sorted(r[0] for r in self.sql("SELECT e.url FROM relacao_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.relacao_id=?", i, db=db)))
        return out

    def test_aprovar_descartar_fundir_desfazer_e_reaplicar(self):
        a, b, (r1, r2, r3), alvo = self.tres_relacoes()
        pend = R.listar_pendencias_core("relacao")
        self.assertEqual(pend["contagem"]["relacao"], 3)
        it = next(x for x in pend["itens"] if x["id"] == r3)
        self.assertIn(alvo, [s["id"] for s in it["similares"]] + [m["id"] for m in it["mesmo_par"]])  # candidato a fusão aparece
        self.assertEqual(it["evidencias"][0]["url"], "https://exemplo.org/rev/2")

        d1 = R.revisar_relacao_core(r1, "aprovar", motivo="ok")
        d2 = R.revisar_relacao_core(r2, "descartar")
        d3 = R.revisar_relacao_core(r3, "fundir_em", alvo_id=alvo)
        for d in (d1, d2, d3):
            self.assertTrue(d["ok"], d)
            self.assertEqual(d["dump"]["dump_status"], "ok")
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r1), "publicada")
        self.assertEqual(self.um("SELECT origem FROM relacao WHERE id=?", r1), "manual")  # mantém origem
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r2), "descartada")
        self.assertEqual(self.um("SELECT count(*) FROM relacao_evidencia WHERE relacao_id=?", r2), 1)  # descartar não apaga evidência
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r3), "descartada")
        self.assertEqual(self.um("SELECT count(*) FROM relacao_evidencia WHERE relacao_id=?", r3), 0)
        urls_alvo = {r[0] for r in self.sql("SELECT e.url FROM relacao_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.relacao_id=?", alvo)}
        self.assertEqual(urls_alvo, {"https://exemplo.org/rev/alvo", "https://exemplo.org/rev/2"})
        self.assertEqual(d3["movidos"]["evidencias"], 1)
        linhas = self.jsonl()
        self.assertEqual(len(linhas), 3)
        self.assertEqual([x["acao"] for x in linhas], ["aprovar", "descartar", "fundir_em"])
        self.assertEqual(set(linhas[0]), {"id", "quando", "tipo", "alvo", "acao", "campos", "motivo"})
        self.assertEqual(linhas[2]["campos"]["fundir_em"]["rotulo"], "Pagamentos ao escritório")  # chave natural, não só id
        self.assertIn("Repasse de consultoria (revisão 1)", (self.repo / "data" / "dump.sql").read_text(encoding="utf-8"))

        # repetir = idempotente, não appenda
        again = R.revisar_relacao_core(r1, "aprovar")
        self.assertTrue(again["ok"] and again["ja_aplicada"], again)
        self.assertEqual(len(self.jsonl()), 3)
        # erro não grava nada
        self.assertFalse(R.revisar_relacao_core(r1, "publicar")["ok"])
        self.assertFalse(R.revisar_relacao_core(r1, "fundir_em", alvo_id=r1)["ok"])
        self.assertFalse(R.revisar_relacao_core(r1, "editar", campos={"natureza": "xyz"})["ok"])
        self.assertEqual(len(self.jsonl()), 3)

        # desfazer a 1ª
        u = R.desfazer_core(linhas[0]["id"])
        self.assertTrue(u["ok"], u)
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r1), "revisar")
        self.assertEqual(len(self.jsonl()), 4)
        self.assertEqual(self.jsonl()[-1]["tipo"], "desfazer")
        self.assertFalse(R.desfazer_core(linhas[0]["id"])["ok"])  # já desfeita
        self.assertEqual(R.listar_pendencias_core("relacao")["contagem"]["relacao"], 1)
        vivo = self.estado([r1, r2, r3, alvo])

        # desfazer a fusão e refazê-la: evidência volta para a origem
        u3 = R.desfazer_core(linhas[2]["id"])
        self.assertTrue(u3["ok"], u3)
        self.assertEqual(self.um("SELECT count(*) FROM relacao_evidencia WHERE relacao_id=?", r3), 1)
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r3), "revisar")
        self.assertTrue(R.revisar_relacao_core(r3, "fundir_em", alvo_id=alvo)["ok"])
        self.assertEqual(self.estado([r1, r2, r3, alvo]), vivo)

        rc, saida = self.validar()
        self.assertEqual(rc, 0, saida)

        # cópia limpa: o banco de antes das decisões (base + as mesmas inserções do MCP) + aplicar_decisoes.py => mesmo estado
        limpo = self.tmp / "limpo.sqlite"
        shutil.copy(self.tmp / "base.sqlite", limpo)
        os.environ["LDT_DB"] = str(limpo)
        os.environ["LDT_DUMP"] = str(self.tmp / "limpo.sql")
        a2, b2, ids2, alvo2 = self.tres_relacoes()
        self.assertEqual((a2, b2, ids2, alvo2), (a, b, [r1, r2, r3], alvo))
        p = subprocess.run([sys.executable, str(self.repo / "scripts" / "aplicar_decisoes.py"), "--db", str(limpo),
                            "--decisoes", str(self.cur / "decisoes.jsonl"), "--dump", str(self.tmp / "limpo.sql")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        print("\n  aplicar_decisoes.py:", p.stdout.strip().replace("\n", " | "))
        # 6 linhas: aprovar(desfeita), descartar, fundir(desfeita), desfazer, desfazer, fundir de novo => 2 efetivas
        self.assertIn("6 linhas, 2 desfeitas; aplicadas agora 2", p.stdout)
        self.assertEqual(self.estado([r1, r2, r3, alvo], db=limpo), vivo)
        p2 = subprocess.run([sys.executable, str(self.repo / "scripts" / "aplicar_decisoes.py"), "--db", str(limpo),
                             "--decisoes", str(self.cur / "decisoes.jsonl"), "--dump", str(self.tmp / "limpo.sql")], capture_output=True, text=True)
        self.assertIn("aplicadas agora 0", p2.stdout)  # idempotente
        self.assertEqual(self.estado([r1, r2, r3, alvo], db=limpo), vivo)

    def test_editar_e_aprovar_com_campos(self):
        a, b, (r1, _, _), _ = self.tres_relacoes()
        d = R.revisar_relacao_core(r1, "aprovar", campos={"rotulo": "Repasse de consultoria", "natureza": "inv", "temas": ["caso-master"]})
        self.assertTrue(d["ok"], d)
        r = self.sql("SELECT * FROM relacao WHERE id=?", r1)[0]
        self.assertEqual((r["rotulo"], r["natureza_id"], r["status"]), ("Repasse de consultoria", "investigacao", "publicada"))
        self.assertEqual([x[0] for x in self.sql("SELECT tema_id FROM relacao_tema WHERE relacao_id=?", r1)], ["caso-master"])
        self.assertTrue(self.sql("SELECT 1 FROM busca_fts WHERE origem_tabela='relacao' AND origem_id=? AND busca_fts MATCH 'consultoria'", str(r1)))
        self.assertTrue(R.desfazer_core(d["decisao"]["id"])["ok"])
        self.assertEqual(self.um("SELECT rotulo FROM relacao WHERE id=?", r1), "Repasse de consultoria (revisão 1)")

    def test_desfazer_recusa_quando_ha_decisao_posterior_na_mesma_linha(self):
        _, _, (r1, _, _), _ = self.tres_relacoes()
        d1 = R.revisar_relacao_core(r1, "editar", campos={"descricao": "x"})
        d2 = R.revisar_relacao_core(r1, "aprovar")
        u = R.desfazer_core(d1["decisao"]["id"])
        self.assertFalse(u["ok"])
        self.assertEqual(u["conflitos"], [d2["decisao"]["id"]])
        self.assertTrue(R.desfazer_core(d2["decisao"]["id"])["ok"])
        self.assertTrue(R.desfazer_core(d1["decisao"]["id"])["ok"])
        self.assertIsNone(self.um("SELECT descricao FROM relacao WHERE id=?", r1))


class TestCorteEventoEntidade(Base):
    def test_corte_sugerido(self):
        out = S.inserir_fonte_core({"tipo": "video", "plataforma": "youtube", "url": "https://www.youtube.com/watch?v=revisao0001", "titulo": "Vídeo teste"},
                                   [{"ordem": 1, "inicio_s": 10, "fim_s": 30, "afirmacao": "Afirmação", "natureza": "alegacao", "confianca": 0.7,
                                     "relacoes": [{"de": "daniel-vorcaro", "para": "brb", "tipo": "financeira", "rotulo": "Teste de corte"}]}],
                                   [{"inicio_s": 5, "fim_s": 40, "titulo": "Corte teste"}])
        self.assertTrue(out["ok"], out)
        p = R.listar_pendencias_core("corte")
        self.assertEqual(p["contagem"]["corte"], 1)
        it = p["itens"][0]
        self.assertIn("t=5s", it["url"])
        rel = R.listar_pendencias_core("relacao")["itens"][0]
        self.assertEqual(rel["trechos"][0]["afirmacao"], "Afirmação")  # trecho de origem vai junto
        self.assertIn("t=10s", rel["trechos"][0]["url"])
        d = R.revisar_corte_core(it["id"], "aprovar")
        self.assertTrue(d["ok"], d)
        self.assertEqual(self.um("SELECT status FROM corte WHERE id=?", it["id"]), "aprovado")
        self.assertEqual(R.listar_pendencias_core("corte")["contagem"]["corte"], 0)

    def test_pendencias_eventos(self):
        p = R.listar_pendencias_core(limite=100, com_similares=False)
        self.assertEqual(p["contagem"]["evento_natureza"], 41)
        ev = [x for x in p["itens"] if x["tipo"] == "evento_natureza"]
        self.assertEqual(len(ev), 41)
        self.assertTrue(all(x["canal"] == "teia" and x["natureza"] is None for x in ev))
        self.assertEqual(p["contagem"]["evento_fusao"], 10)
        fus = {x["n"]: [e["id"] for e in x["eventos"]] for x in p["itens"] if x["tipo"] == "evento_fusao"}
        self.assertEqual(fus[1], ["ida10", "vol3"])
        self.assertEqual(fus[4], ["ev-2025-08-28-carbono-oculto-quasar-e-tank-operacoes", "ev-2025-08-28-reag-e-alvo-de-buscas-na-carbono-oculto"])
        self.assertTrue(all(len(v) >= 2 for v in fus.values()))
        self.assertEqual(R.listar_pendencias_core("evento_natureza", tema="brasil-ano-a-ano")["contagem"]["evento_natureza"], 0)
        self.assertFalse(R.listar_pendencias_core("xyz")["ok"])

    def test_natureza_sobrevive_a_remigracao(self):
        eid = R.listar_pendencias_core("evento_natureza", limite=1)["itens"][0]["id"]
        d = R.revisar_evento_core(eid, "natureza", natureza="rep")
        self.assertTrue(d["ok"], d)
        self.assertEqual(self.um("SELECT natureza_id FROM evento WHERE id=?", eid), "reportada")
        self.assertEqual(R.listar_pendencias_core("evento_natureza")["contagem"]["evento_natureza"], 40)
        # migrar.py recria o banco do zero e já reaplica decisoes.jsonl; aplicar_decisoes.py de novo é idempotente; validar.py passa
        m = subprocess.run([sys.executable, str(self.repo / "scripts" / "migrar.py")], capture_output=True, text=True, cwd=str(self.repo))
        self.assertEqual(m.returncode, 0, m.stderr[-2000:])
        self.assertEqual(self.um("SELECT natureza_id FROM evento WHERE id=?", eid), "reportada")
        p = subprocess.run([sys.executable, str(self.repo / "scripts" / "aplicar_decisoes.py"), "--db", str(self.db)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.um("SELECT natureza_id FROM evento WHERE id=?", eid), "reportada")
        rc, saida = self.validar()
        self.assertEqual(rc, 0, saida)

    def test_fundir_evento_grava_curadoria_e_desfaz(self):
        a, b = "ev-2025-08-28-reag-e-alvo-de-buscas-na-carbono-oculto", "ev-2025-08-28-carbono-oculto-quasar-e-tank-operacoes"
        fontes_a = {r[0] for r in self.sql("SELECT evidencia_id FROM evento_evidencia WHERE evento_id=?", a)}
        d = R.revisar_evento_core(a, "fundir_em", alvo_id=b, motivo="Mesma deflagração (teste).")
        self.assertTrue(d["ok"], d)
        self.assertIsNone(self.um("SELECT id FROM evento WHERE id=?", a))
        self.assertEqual(self.um("SELECT evento_id FROM evento_alias WHERE alias=?", a), b)
        self.assertTrue(fontes_a <= {r[0] for r in self.sql("SELECT evidencia_id FROM evento_evidencia WHERE evento_id=?", b)})
        fus = json.loads((self.cur / "eventos-fusoes.json").read_text(encoding="utf-8"))
        self.assertIn({"manter": b, "fundir": [a], "motivo": "Mesma deflagração (teste)."}, fus)
        self.assertEqual(R.listar_pendencias_core("evento_fusao")["contagem"]["evento_fusao"], 9)
        # datas diferentes: recusado sem gravar nada
        r = R.revisar_evento_core("ev-2025-03-brb-e-master-fecham-acordo-para-venda-de", "fundir_em", alvo_id="ev-2025-03-28-brb-anuncia-compra-de-58-do-master")
        self.assertFalse(r["ok"])
        self.assertEqual(len(self.jsonl()), 1)
        u = R.desfazer_core(d["decisao"]["id"])
        self.assertTrue(u["ok"], u)
        self.assertEqual((self.cur / "eventos-fusoes.json").read_bytes(), self.fusoes0)
        self.assertEqual(self.um("SELECT count(*) FROM evento WHERE id=?", a), 1)
        self.assertEqual(self.um("SELECT count(*) FROM evento_alias"), 32)
        rc, saida = self.validar()
        self.assertEqual(rc, 0, saida)

    def test_manter_separados_tira_da_fila(self):
        d = R.revisar_evento_core("max19", "manter_separados", alvo_id="max20", motivo="recursos diferentes")
        self.assertTrue(d["ok"], d)
        self.assertNotIn(2, [x["n"] for x in R.listar_pendencias_core("evento_fusao")["itens"]])
        self.assertTrue(R.desfazer_core(d["decisao"]["id"])["ok"])
        self.assertIn(2, [x["n"] for x in R.listar_pendencias_core("evento_fusao")["itens"]])

    def test_fundir_entidade(self):
        de, para = "aecio-neves", "aldo-rebelo"
        # um trecho que cita `de` (para conferir que trechos também migram)
        out = S.inserir_fonte_core({"tipo": "reportagem", "url": "https://exemplo.org/rev/ent", "titulo": "Reportagem entidade"},
                                   [{"ordem": 1, "localizacao": "p. 1", "afirmacao": "Cita Aécio", "natureza": "alegacao", "confianca": 0.5, "entidades": [de]}])
        self.assertTrue(out["ok"], out)
        antes = {"rel": self.um("SELECT count(*) FROM relacao WHERE de=? OR para=?", de, de),
                 "ev": self.um("SELECT count(*) FROM evento_entidade WHERE entidade_id=?", de),
                 "tr": self.um("SELECT count(*) FROM trecho_entidade WHERE entidade_id=?", de),
                 "mand": self.um("SELECT count(*) FROM mandato WHERE entidade_id=?", de)}
        self.assertTrue(all(antes.values()), antes)
        rel_para0 = self.um("SELECT count(*) FROM relacao WHERE de=? OR para=?", para, para)
        d = R.fundir_entidade_core(de, para, motivo="teste")
        self.assertTrue(d["ok"], d)
        self.assertIsNone(self.um("SELECT id FROM entidade WHERE id=?", de))
        for t, c in [("relacao", "de"), ("relacao", "para"), ("evento_entidade", "entidade_id"), ("trecho_entidade", "entidade_id"),
                     ("mandato", "entidade_id"), ("entidade_alias", "entidade_id")]:
            self.assertEqual(self.um(f"SELECT count(*) FROM {t} WHERE {c}=?", de), 0, t)
        self.assertEqual(self.um("SELECT count(*) FROM relacao WHERE de=? OR para=?", para, para), rel_para0 + antes["rel"])
        self.assertEqual(self.um("SELECT tipo_alias FROM entidade_alias WHERE entidade_id=? AND alias='Aécio Neves'", para), "nome_antigo")
        self.assertEqual(S.buscar_entidade("Aécio Neves", limite=1)[0]["id"], para)
        again = R.fundir_entidade_core(de, para)
        self.assertTrue(again["ok"] and again.get("ja_fundida"), again)
        self.assertEqual(len(self.jsonl()), 1)
        self.assertFalse(R.fundir_entidade_core("daniel-vorcaro", "banco-master")["ok"])  # nó da teia original
        u = R.desfazer_core(d["decisao"]["id"])
        self.assertTrue(u["ok"], u)
        self.assertEqual(self.um("SELECT count(*) FROM relacao WHERE de=? OR para=?", de, de), antes["rel"])
        self.assertEqual(self.um("SELECT count(*) FROM trecho_entidade WHERE entidade_id=?", de), antes["tr"])
        self.assertIsNone(self.um("SELECT 1 FROM entidade_alias WHERE entidade_id=? AND tipo_alias='nome_antigo'", para))


class TestPagina(Base):
    def setUp(self):
        super().setUp()
        self.proc = None

    def tearDown(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(10)

    def subir(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        self.proc = subprocess.Popen([sys.executable, str(self.repo / "scripts" / "servir_revisao.py"), "--db", str(self.db), "--porta", str(porta)],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=dict(os.environ))
        base = f"http://127.0.0.1:{porta}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/decisoes", timeout=1).read()
                return base
            except OSError:
                time.sleep(0.1)
        self.fail("servidor não subiu: " + (self.proc.stdout.read() if self.proc.poll() is not None else ""))

    def post(self, base, corpo):
        req = urllib.request.Request(base + "/api/decidir", json.dumps(corpo).encode(), {"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def test_api_e_pagina(self):
        _, _, (r1, r2, r3), alvo = self.tres_relacoes()
        base = self.subir()
        html = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        self.assertIn("Fila de revisão", html)
        p = json.loads(urllib.request.urlopen(base + "/api/pendencias?tipo=relacao", timeout=30).read())
        self.assertEqual(p["contagem"]["relacao"], 3)
        d = self.post(base, {"tipo": "relacao", "id": r2, "acao": "descartar"})
        self.assertTrue(d["ok"], d)
        self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", r2), "descartada")
        self.assertFalse(self.post(base, {"tipo": "relacao", "id": r2, "acao": "xyz"})["ok"])
        u = self.post(base, {"tipo": "desfazer", "id": d["decisao"]["id"]})
        self.assertTrue(u["ok"], u)
        self.assertEqual(len(self.jsonl()), 2)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright não instalado: teste visual não feito")
        if not PW_BROWSERS.exists():
            self.skipTest("/opt/pw-browsers ausente: teste visual não feito")
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PW_BROWSERS))
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            pg = nav.new_page(viewport={"width": 1280, "height": 900})
            erros = []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector("#lista li")
            n_itens = pg.locator("#lista li").count()
            self.assertGreaterEqual(n_itens, 1)
            total = int(pg.locator("#total").inner_text())
            self.assertEqual(total, 3 + 41 + 10)
            primeiro = pg.locator("#card .kind span").first.inner_text()  # "Relação <id>"
            rid = int(primeiro.split()[-1])
            pg.locator(".acts [data-acao=aprovar]").click()
            pg.wait_for_function("document.querySelector('#total').textContent === '53'")
            self.assertEqual(self.um("SELECT status FROM relacao WHERE id=?", rid), "publicada")
            pg.keyboard.press("d")  # tecla D no próximo item (outra relação)
            pg.wait_for_function("document.querySelector('#total').textContent === '52'")
            pg.keyboard.press("u")  # desfaz a última
            pg.wait_for_function("document.querySelector('#total').textContent === '53'")
            pg.set_viewport_size({"width": 390, "height": 800})
            largura = pg.evaluate("document.documentElement.scrollWidth")
            nav.close()
        self.assertEqual(erros, [])
        self.assertLessEqual(largura, 390)  # sem rolagem horizontal no celular
        acoes = [(x["tipo"], x["acao"]) for x in self.jsonl()]
        self.assertEqual(acoes[-3:], [("relacao", "aprovar"), ("relacao", "descartar"), ("desfazer", "desfazer")])
        print(f"\n  página: {n_itens} itens na lista, aprovar/D/U pela página ok")


if __name__ == "__main__":
    unittest.main()
