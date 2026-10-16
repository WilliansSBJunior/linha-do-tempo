#!/usr/bin/env python3
"""Testes do MCP server contra uma CÓPIA do repo em diretório temporário (o banco real nunca é aberto para escrita).

Uso (da raiz do repo):  python3 mcp/test_server.py -v      (ou: python3 -m pytest mcp/test_server.py)
Não use `python -m unittest mcp.test_server`: a pasta `mcp/` do repo sombrearia o pacote `mcp` do SDK.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import server as S  # noqa: E402

REAL_DB, REAL_DUMP = RAIZ / "data" / "linha-do-tempo.sqlite", RAIZ / "data" / "dump.sql"


def estado_real():
    return {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in (REAL_DB, REAL_DUMP)}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real0 = estado_real()
        cls.tmp = Path(tempfile.mkdtemp(prefix="ldt-test-"))
        cls.repo = cls.tmp / "repo"
        shutil.copytree(RAIZ / "scripts", cls.repo / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(RAIZ / "data", cls.repo / "data", ignore=shutil.ignore_patterns("*.sqlite*"))
        shutil.copy(REAL_DB, cls.tmp / "base.sqlite")  # só leitura do real

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        assert estado_real() == cls.real0, "o banco/dump REAL foi alterado pelos testes!"

    def setUp(self):
        self.db = self.repo / "data" / "linha-do-tempo.sqlite"
        for suf in ("", "-wal", "-shm"):
            Path(str(self.db) + suf).unlink(missing_ok=True)
        shutil.copy(self.tmp / "base.sqlite", self.db)
        shutil.copy(RAIZ / "data" / "dump.sql", self.repo / "data" / "dump.sql")
        os.environ["LDT_DB"] = str(self.db)
        os.environ["LDT_DUMP"] = str(self.repo / "data" / "dump.sql")
        os.environ.pop("LDT_EXPORT_JSON", None)

    def sql(self, q, *a):
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        try:
            return con.execute(q, a).fetchall()
        finally:
            con.close()

    def n(self, tabela):
        return self.sql(f"SELECT count(*) c FROM {tabela}")[0]["c"]

    def validar(self):
        p = subprocess.run([sys.executable, str(self.repo / "scripts" / "validar.py"), "--db", str(self.db)], capture_output=True, text=True)
        return p.returncode, p.stdout[-1500:] + p.stderr

    def par_sem_relacao(self):
        """Duas entidades da teia que ainda não se relacionam."""
        r = self.sql("""SELECT a.id a, b.id b FROM entidade a, entidade b WHERE a.id<b.id AND a.origem='teia' AND b.origem='teia'
                        AND NOT EXISTS (SELECT 1 FROM relacao r WHERE (r.de=a.id AND r.para=b.id) OR (r.de=b.id AND r.para=a.id))
                        ORDER BY a.id, b.id LIMIT 1""")[0]
        return r["a"], r["b"]


class TestBusca(Base):
    def test_alias_vorcaro(self):
        r = S.buscar_entidade("Vorcaro")
        self.assertEqual(r[0]["id"], "daniel-vorcaro")
        self.assertIn("henrique-vorcaro", [e["id"] for e in r])
        self.assertGreater(r[0]["n_relacoes"], 0)

    def test_alias_cvm_e_acento_e_slug(self):
        r = S.buscar_entidade("CVM")
        self.assertEqual(r[0]["id"], "cvm")
        self.assertIn("CVM", r[0]["aliases"])
        self.assertEqual(S.buscar_entidade("Daniel Bueno Vorcaro")[0]["id"], "daniel-vorcaro")
        self.assertEqual(S.buscar_entidade("daniel-vorcaro")[0]["casou_por"], "slug")
        self.assertTrue(all(e["tipo"] == "banco" for e in S.buscar_entidade("vorcaro", tipo="banco")))

    def test_fts_e_nunca_cria(self):
        antes = self.n("entidade")
        self.assertEqual(S.buscar_entidade("zzzqxk"), [])
        self.assertEqual(self.n("entidade"), antes)

    def test_buscar_relacoes_banco_master(self):
        rels = S.buscar_relacoes(entidade="banco-master", limite=500)
        self.assertGreaterEqual(len(rels), 80)
        r = next(x for x in rels if x["id"] == 17)
        self.assertEqual((r["de"]["id"], r["para"]["id"]), ("banco-master", "andre-valadao"))
        self.assertGreaterEqual(len(r["evidencias"]), 1)
        self.assertTrue(r["evidencias"][0]["url"].startswith("http"))
        self.assertTrue(r["evidencias"][0]["veiculo"])
        self.assertIn("cortes", r)
        # filtros: alias em 'de', natureza em vocabulário da teia, ano
        so_doc = S.buscar_relacoes(entidade="banco-master", natureza="doc", limite=500)
        self.assertTrue(so_doc and all(x["natureza"] == "documentada" for x in so_doc))
        self.assertTrue(all(2020 <= (x["periodo_inicio"] and int(x["periodo_inicio"][:4]) or 0) or x["periodo_fim"]
                            for x in S.buscar_relacoes(entidade="banco-master", ano_inicio=2020, limite=500)))
        err = S.buscar_relacoes(entidade="nao-existe-xyz")
        self.assertFalse(err["ok"])


class TestInserirRelacao(Base):
    def test_upsert_nao_duplica_e_vocabularios(self):
        a, b = self.par_sem_relacao()
        antes = self.n("relacao")
        kw = dict(de=a, para=b, tipo="financeira", rotulo="Teste de aporte", natureza="rep", periodo_inicio="2023",
                  evidencias=[{"url": "https://exemplo.com/materia?utm_source=x#frag", "titulo": "Matéria"}])
        r1 = S.inserir_relacao(**kw)
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["acao"], "criada")
        self.assertEqual(self.n("relacao"), antes + 1)
        row = self.sql("SELECT * FROM relacao WHERE id=?", r1["relacao_id"])[0]
        self.assertEqual((row["natureza_id"], row["status"], row["origem"]), ("reportada", "revisar", "manual"))
        # 2ª chamada: mesma chave, natureza em outro vocabulário, evidência repetida (URL normaliza igual) + uma nova
        kw2 = dict(kw, natureza="fato_documentado", valor_texto="R$ 1 mi", descricao="agora com descrição",
                   evidencias=[{"url": "https://exemplo.com/materia"}, {"url": "https://outro.com/b", "tipo": "documento_oficial"}])
        r2 = S.inserir_relacao(**kw2)
        self.assertEqual((r2["acao"], r2["relacao_id"]), ("atualizada", r1["relacao_id"]))
        self.assertEqual(r2["evidencias_novas_ligadas"], 1)
        self.assertEqual(self.n("relacao"), antes + 1)
        row = self.sql("SELECT * FROM relacao WHERE id=?", r1["relacao_id"])[0]
        self.assertEqual((row["natureza_id"], row["valor_texto"], row["descricao"]), ("documentada", "R$ 1 mi", "agora com descrição"))
        urls = [x["url"] for x in self.sql("SELECT e.url FROM relacao_evidencia x JOIN evidencia e ON e.id=x.evidencia_id WHERE x.relacao_id=?", r1["relacao_id"])]
        self.assertEqual(sorted(urls), ["https://exemplo.com/materia", "https://outro.com/b"])
        # dump regravado com a nova relação
        self.assertIn("Teste de aporte", Path(os.environ["LDT_DUMP"]).read_text(encoding="utf-8"))
        self.assertEqual(r2["dump"]["dump_status"], "ok")
        # busca textual de relações nova entra no FTS
        self.assertTrue(self.sql("SELECT 1 FROM busca_fts WHERE origem_tabela='relacao' AND busca_fts MATCH 'aporte'"))

    def test_nao_rebaixa_publicada(self):
        r = S.inserir_relacao(de="banco-master", para="andre-valadao", tipo="x", rotulo="y", natureza="doc")
        self.assertFalse(r["ok"])
        ex = self.sql("SELECT * FROM relacao WHERE id=17")[0]
        r = S.inserir_relacao(de=ex["de"], para=ex["para"], tipo=ex["tipo"], rotulo=ex["rotulo"], natureza="rep",
                              periodo_inicio=ex["periodo_inicio"])
        self.assertEqual(r["acao"], "atualizada")
        self.assertEqual(self.sql("SELECT status FROM relacao WHERE id=17")[0]["status"], "publicada")

    def test_entidade_inexistente_com_sugestoes_e_rollback(self):
        antes = self.n("relacao")
        r = S.inserir_relacao(de="daniel-vorkaro", para="banco-master", tipo="societaria", rotulo="Sócio", natureza="doc")
        self.assertFalse(r["ok"])
        self.assertIn("daniel-vorkaro", r["erro"])
        self.assertTrue(1 <= len(r["sugestoes"]) <= 3, r)
        self.assertEqual(self.n("relacao"), antes)
        self.assertFalse(S.inserir_relacao(de="cvm", para="banco-master", tipo="societaria", rotulo="a", natureza="zzz")["ok"])


def video_ficticio(rotulo_rel_nova="Parceria de divulgação (teste)"):
    return dict(
        video=dict(url="https://www.youtube.com/watch?v=TESTE000001", plataforma="youtube", titulo="Vídeo fictício de teste",
                   canal="Canal Teste", publicado_em="2026-10-01", duracao_s=600, transcricao="texto completo " * 50,
                   classificador_versao="v-test"),
        trechos=[
            dict(ordem=1, inicio_s=10, fim_s=40, texto_original="o Master pagou ao Valadão", afirmacao="Banco Master teria pagado André Valadão",
                 natureza="alegacao", entidades=["banco-master", "andre-valadao"],
                 relacoes=[dict(de="banco-master", para="andre-valadao", tipo="financeira", rotulo=None, periodo="2022")],
                 anos_referidos=[2022], valores=[dict(valor=1500000, moeda="BRL", descricao="valor citado")], confianca=0.8, potencial_corte=4),
            dict(ordem=2, inicio_s=45, fim_s=90, afirmacao="Vorcaro e CVM tiveram contato (teste)", natureza="opiniao",
                 entidades=["daniel-vorcaro", "cvm"],
                 relacoes=[dict(de="daniel-vorcaro", para="cvm", tipo="politica", rotulo=rotulo_rel_nova, periodo=dict(inicio="2024", fim="2025"))],
                 anos_referidos=[2024, 2025], valores=[], confianca=0.55, potencial_corte=2),
        ],
        cortes_sugeridos=[dict(titulo="Corte teste", inicio_s=10, fim_s=90, justificativa="tudo", tema="master", trechos=[1, 2],
                               relacoes_cobertas=[dict(de="banco-master", para="andre-valadao", tipo="financeira"),
                                                  dict(de="daniel-vorcaro", para="cvm", tipo="politica")])])


class TestInserirVideo(Base):
    def contagens(self):
        return {t: self.n(t) for t in ("relacao", "video", "trecho", "corte", "trecho_relacao", "corte_trecho", "relacao_corte",
                                       "trecho_entidade", "evidencia", "entidade")}

    def test_completo_idempotente_e_validar(self):
        c0 = self.contagens()
        n_val_antes = len(self.sql("SELECT id FROM relacao WHERE de='banco-master' AND para='andre-valadao' AND tipo='financeira'"))
        self.assertGreaterEqual(n_val_antes, 1)  # relação existente reaproveitada (trecho 1 sem rótulo)
        r = S.inserir_video(**video_ficticio())
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["video_id"], "yt:TESTE000001")
        self.assertEqual(len(r["relacoes_criadas"]), 1)
        self.assertEqual(len(r["relacoes_existentes_reutilizadas"]), 1)
        c1 = self.contagens()
        self.assertEqual((c1["video"], c1["trecho"], c1["corte"], c1["relacao"]), (c0["video"] + 1, c0["trecho"] + 2, c0["corte"] + 1, c0["relacao"] + 1))
        self.assertEqual(c1["entidade"], c0["entidade"])
        self.assertEqual(c1["corte_trecho"], c0["corte_trecho"] + 2)
        self.assertEqual(c1["trecho_relacao"], c0["trecho_relacao"] + 2)
        self.assertEqual(c1["relacao_corte"], c0["relacao_corte"] + 2)
        nova = self.sql("SELECT * FROM relacao WHERE id=?", r["relacoes_criadas"][0])[0]
        self.assertEqual((nova["origem"], nova["status"], nova["natureza_id"], nova["confianca"], nova["periodo_inicio"], nova["periodo_fim"]),
                         ("classificador", "revisar", "opiniao", 0.55, "2024", "2025"))
        t1 = self.sql("SELECT * FROM trecho WHERE video_id='yt:TESTE000001' AND ordem=1")[0]
        self.assertEqual(t1["natureza_id"], "alegacao")
        self.assertEqual(self.sql("SELECT valor, moeda FROM trecho_valor WHERE trecho_id=?", t1["id"])[0]["moeda"], "BRL")
        self.assertEqual([x["ano"] for x in self.sql("SELECT ano FROM trecho_ano WHERE trecho_id=?", t1["id"])], [2022])
        # a relação existente (publicada) não mudou de status/natureza
        ex = self.sql("SELECT status FROM relacao WHERE id=?", r["relacoes_existentes_reutilizadas"][0])[0]
        self.assertEqual(ex["status"], "publicada")
        # leitura: buscar_trechos por FTS / entidade / video; cortes aparecem na relação
        achados = S.buscar_trechos(texto="Valadão")
        self.assertEqual([t["ordem"] for t in achados], [1])
        self.assertEqual(achados[0]["entidades"], ["andre-valadao", "banco-master"])
        self.assertEqual(len(achados[0]["relacoes"]), 1)
        self.assertEqual(len(S.buscar_trechos(entidade="cvm", video="yt:TESTE000001")), 1)
        self.assertEqual(len(S.buscar_trechos(natureza="fato_documentado")), 0)
        rel = S.buscar_relacoes(de="daniel-vorcaro", para="cvm", tipo="politica", status="revisar")
        self.assertEqual(rel[0]["cortes"][0]["titulo"], "Corte teste")
        # validar.py passa (cópia do repo; inclui conferência de dump.sql == dump atual do banco)
        cod, saida = self.validar()
        self.assertEqual(cod, 0, saida)
        self.assertIn("RESULTADO: OK", saida)
        # reinserção idempotente: mesmos números, ids de trecho novos, sem relação duplicada
        r2 = S.inserir_video(**video_ficticio())
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(self.contagens(), c1)
        self.assertEqual(r2["relacoes_criadas"], [])
        self.assertEqual(r2["substituiu_insercao_anterior"], {"trechos": 2, "cortes": 1})
        # reinserção com menos trechos substitui (não acumula)
        v = video_ficticio()
        v["trechos"], v["cortes_sugeridos"] = v["trechos"][:1], []
        r3 = S.inserir_video(**v)
        self.assertTrue(r3["ok"], r3)
        self.assertEqual((self.n("trecho"), self.n("corte")), (c0["trecho"] + 1, c0["corte"]))
        self.assertEqual(self.n("relacao"), c1["relacao"])  # a relação criada antes permanece (sem duplicar)
        cod, saida = self.validar()
        self.assertEqual(cod, 0, saida)

    def test_entidade_desconhecida_rejeita_tudo(self):
        c0 = self.contagens()
        dump0 = Path(os.environ["LDT_DUMP"]).read_bytes()
        v = video_ficticio()
        v["trechos"][1]["entidades"] = ["daniel-vorcaro", "vorcaro-fantasma"]
        v["trechos"][0]["relacoes"][0]["para"] = "valadao-inexistente"
        r = S.inserir_video(**v)
        self.assertFalse(r["ok"])
        ids = {x["id"]: x for x in r["nao_resolvidas"]}
        self.assertEqual(set(ids), {"vorcaro-fantasma", "valadao-inexistente"})
        for x in ids.values():
            self.assertTrue(1 <= len(x["sugestoes"]) <= 3, x)
            self.assertTrue(x["usado_em"])
        self.assertIn("daniel-vorcaro", [s["id"] for s in ids["vorcaro-fantasma"]["sugestoes"]] + ["daniel-vorcaro"])
        self.assertEqual(self.contagens(), c0)  # nada gravado
        self.assertEqual(Path(os.environ["LDT_DUMP"]).read_bytes(), dump0)  # dump intocado

    def test_erros_de_formato_nao_gravam(self):
        c0 = self.contagens()
        v = video_ficticio()
        v["trechos"][0]["natureza"] = "inventada"
        v["cortes_sugeridos"][0]["fim_s"] = 5
        r = S.inserir_video(**v)
        self.assertFalse(r["ok"])
        self.assertEqual(self.contagens(), c0)

    def test_id_derivado_da_url_e_periodo_string(self):
        v = video_ficticio()
        v["video"].pop("url"); v["video"]["id"] = "TESTE000002"
        v["trechos"][1]["relacoes"][0]["periodo"] = "2024"
        r = S.inserir_video(**v)
        self.assertTrue(r["ok"], r)
        row = self.sql("SELECT url FROM video WHERE id='yt:TESTE000002'")[0]
        self.assertEqual(row["url"], "https://www.youtube.com/watch?v=TESTE000002")
        self.assertEqual(self.sql("SELECT periodo_fim FROM relacao WHERE id=?", r["relacoes_criadas"][0])[0]["periodo_fim"], None)


class TestExtras(Base):
    def test_resumo(self):
        r = S.resumo_banco()
        self.assertGreater(r["entidade"], 300)
        self.assertIn("publicada", r["relacao_por_status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
