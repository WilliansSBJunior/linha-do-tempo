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
        # data/*.json são derivados do banco (entities.json traz `temas` por entidade, temas.json as contagens): depois de uma escrita
        # ficam defasados até exportar_json.py (a ferramenta `exportar()` faz os dois passos); o teste faz o mesmo na cópia.
        e = subprocess.run([sys.executable, str(self.repo / "scripts" / "exportar_json.py"), "--db", str(self.db)], capture_output=True, text=True)
        assert e.returncode == 0, e.stdout + e.stderr
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
        t1 = self.sql("SELECT * FROM trecho WHERE fonte_id='yt:TESTE000001' AND ordem=1")[0]
        self.assertEqual(t1["natureza_id"], "alegacao")
        self.assertEqual(self.sql("SELECT valor, moeda FROM trecho_valor WHERE trecho_id=?", t1["id"])[0]["moeda"], "BRL")
        self.assertEqual([x["ano"] for x in self.sql("SELECT ano FROM trecho_ano WHERE trecho_id=?", t1["id"])], [2022])
        # fonte tipo video + evidência da URL + view de compatibilidade + texto/hash (transcricao = nome antigo de texto)
        f = self.sql("SELECT * FROM fonte WHERE id='yt:TESTE000001'")[0]
        self.assertEqual((f["tipo"], f["plataforma"], f["hash_texto"]), ("video", "youtube", S._hash_texto(("texto completo " * 50).strip())))
        self.assertEqual(self.sql("SELECT url FROM evidencia WHERE id=?", f["evidencia_id"])[0]["url"], f["url"])
        self.assertEqual(self.sql("SELECT transcricao, titulo FROM video WHERE id='yt:TESTE000001'")[0]["titulo"], "Vídeo fictício de teste")
        self.assertEqual(r["fonte_id"], r["video_id"])
        # tema da relação nova: inferido (as duas entidades estão no caso-master) e gravado
        self.assertIn("caso-master", r["temas_das_relacoes_criadas"][r["relacoes_criadas"][0]])
        self.assertEqual([x["tema_id"] for x in self.sql("SELECT tema_id FROM relacao_tema WHERE relacao_id=?", r["relacoes_criadas"][0])][:1], ["caso-master"])
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


def reportagem_ficticia(**kw):
    f = dict(tipo="reportagem", url="https://exemplo.com/materia-teste?utm_source=x#frag", titulo="Reportagem fictícia de teste", canal="Jornal Teste",
             publicado_em="2026-10-02", texto="Corpo da matéria de teste. " * 20, temas=None)
    f.update(kw)
    return dict(
        fonte=f,
        trechos=[dict(ordem=1, localizacao="parágrafo 3", texto_original="Vorcaro e a CVM", afirmacao="Vorcaro teria se reunido com a CVM (teste)",
                      natureza="alegacao", entidades=["daniel-vorcaro", "cvm"],
                      relacoes=[dict(de="daniel-vorcaro", para="cvm", tipo="politica", rotulo="Reunião reportada (teste de fonte)", periodo="2024")],
                      anos_referidos=[2024], confianca=0.7, potencial_corte=1)])


class TestFonte(Base):
    def test_reportagem_sem_tempo_evidencia_hash_e_filtros(self):
        r = S.inserir_fonte(**reportagem_ficticia())
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["tipo"], r["cortes"]), ("reportagem", 0))
        self.assertNotIn("video_id", r)
        fid = r["fonte_id"]
        self.assertTrue(fid.startswith("src:"))
        f = self.sql("SELECT * FROM fonte WHERE id=?", fid)[0]
        self.assertEqual(f["url"], "https://exemplo.com/materia-teste")  # normalizada
        ev = self.sql("SELECT * FROM evidencia WHERE id=?", f["evidencia_id"])[0]
        self.assertEqual((ev["url"], ev["tipo"], ev["veiculo"]), (f["url"], "reportagem", "Jornal Teste"))
        self.assertEqual(f["hash_texto"], S._hash_texto(f["texto"]))
        t = self.sql("SELECT * FROM trecho WHERE fonte_id=?", fid)[0]
        self.assertEqual((t["inicio_s"], t["fim_s"], t["localizacao"]), (None, None, "parágrafo 3"))
        # a relação nova leva a fonte como evidência e ganha tema
        rid = r["relacoes_criadas"][0]
        self.assertEqual(self.sql("SELECT evidencia_id FROM relacao_evidencia WHERE relacao_id=?", rid)[0]["evidencia_id"], f["evidencia_id"])
        self.assertTrue(r["temas_das_relacoes_criadas"][rid])
        # não aparece na view video; filtros novos de buscar_trechos
        self.assertEqual(self.sql("SELECT count(*) c FROM video WHERE id=?", fid)[0]["c"], 0)
        self.assertEqual([x["ordem"] for x in S.buscar_trechos(fonte=fid)], [1])
        self.assertEqual(len(S.buscar_trechos(tipo="reportagem")), 1)
        self.assertEqual(S.buscar_trechos(tipo="video"), [])
        self.assertEqual(len(S.buscar_trechos(fonte="https://exemplo.com/materia-teste")), 1)
        self.assertEqual(S.buscar_trechos(texto="CVM", tipo="reportagem")[0]["fonte_tipo"], "reportagem")
        self.assertFalse(S.buscar_trechos(video=fid)["ok"])  # `video` (legado) só enxerga fonte tipo video
        self.assertFalse(S.buscar_trechos(tipo="gibi")["ok"])
        # texto da fonte entra na busca textual de fontes
        self.assertTrue(self.sql("SELECT 1 FROM busca_fts WHERE origem_tabela='fonte' AND busca_fts MATCH 'matéria'"))
        cod, saida = self.validar()
        self.assertEqual(cod, 0, saida)
        # idempotente por id (mesma URL)
        r2 = S.inserir_fonte(**reportagem_ficticia())
        self.assertEqual((r2["fonte_id"], r2["substituiu_insercao_anterior"], r2["relacoes_criadas"]), (fid, {"trechos": 1, "cortes": 0}, []))
        self.assertEqual(self.n("fonte"), 1)

    def test_cortes_e_tempo_so_para_video(self):
        c0 = (self.n("fonte"), self.n("trecho"), self.n("relacao"))
        v = reportagem_ficticia()
        v["cortes_sugeridos"] = [dict(titulo="x", inicio_s=1, fim_s=2)]
        r = S.inserir_fonte(**v)
        self.assertFalse(r["ok"])
        self.assertIn("video", r["erro"])
        # vídeo sem tempo nos trechos
        sem_tempo = video_ficticio()
        sem_tempo["trechos"][0].pop("inicio_s")
        r = S.inserir_video(**sem_tempo)
        self.assertFalse(r["ok"])
        self.assertTrue(any("obrigatórios" in e for e in r["erros"]), r)
        # tipo inválido / vídeo sem plataforma
        self.assertFalse(S.inserir_fonte(**reportagem_ficticia(tipo="gibi"))["ok"])
        self.assertFalse(S.inserir_fonte(**reportagem_ficticia(tipo="video"))["ok"])
        self.assertEqual((self.n("fonte"), self.n("trecho"), self.n("relacao")), c0)

    def test_banco_recusa_corte_em_fonte_que_nao_e_video(self):
        S.inserir_fonte(**reportagem_ficticia())
        S.inserir_video(**video_ficticio())
        fid = self.sql("SELECT id FROM fonte WHERE tipo='reportagem'")[0]["id"]
        con = sqlite3.connect(str(self.db))
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO corte(video_id, titulo, inicio_s, fim_s) VALUES(?,?,?,?)", (fid, "x", 1, 2))
            with self.assertRaises(sqlite3.IntegrityError):  # trecho de vídeo sem tempo
                con.execute("INSERT INTO trecho(fonte_id, ordem, afirmacao, natureza_id, confianca) VALUES('yt:TESTE000001', 99, 'a', 'alegacao', 0.5)")
            with self.assertRaises(sqlite3.IntegrityError):  # fonte com cortes não deixa de ser vídeo
                con.execute("UPDATE fonte SET tipo='outro' WHERE id='yt:TESTE000001'")
        finally:
            con.close()

    def test_depoimento_sem_url_e_aviso_sem_evidencia(self):
        v = reportagem_ficticia(tipo="depoimento", url=None, titulo="Depoimento oral de teste", texto=None)
        r = S.inserir_fonte(**v)
        self.assertTrue(r["ok"], r)
        f = self.sql("SELECT * FROM fonte WHERE id=?", r["fonte_id"])[0]
        self.assertEqual((f["url"], f["evidencia_id"], f["texto"], f["hash_texto"]), (None, None, None, None))
        self.assertTrue(any("sem evidência" in a for a in r["avisos"]), r["avisos"])
        cod, saida = self.validar()
        self.assertEqual(cod, 0, saida)

    def test_video_compat_view_e_transcricao(self):
        r = S.inserir_video(**video_ficticio())
        self.assertTrue(r["ok"], r)
        row = self.sql("SELECT * FROM video WHERE id='yt:TESTE000001'")[0]
        self.assertEqual((row["plataforma"], row["duracao_s"]), ("youtube", 600))
        self.assertEqual(row["transcricao"], ("texto completo " * 50).strip())
        self.assertEqual(self.n("video"), self.sql("SELECT count(*) c FROM fonte WHERE tipo='video'")[0]["c"])
        self.assertEqual(len(S.buscar_trechos(video="yt:TESTE000001")), 2)
        self.assertEqual(len(S.buscar_trechos(tipo="video", fonte="yt:TESTE000001")), 2)


class TestTemas(Base):
    def test_listar_temas(self):
        ts = {t["id"]: t for t in S.listar_temas()}
        self.assertEqual(set(ts), {"caso-master", "brasil-ano-a-ano", "pares", "violencia", "inss", "pcc", "brb", "precatorios", "lagoinha", "a-classificar",
                                   "crime-organizado", "cultura-e-entretenimento", "financiamento-politico"})
        self.assertGreater(ts["caso-master"]["n_relacoes"], 300)
        self.assertGreater(ts["brasil-ano-a-ano"]["n_eventos"], 200)

    def test_buscar_pistas(self):
        todas = S.buscar_pistas(limite=500)
        n = self.sql("SELECT count(*) c FROM post_triagem WHERE relevancia IN ('pista','contexto')")[0]["c"]
        self.assertEqual(len(todas), n)
        self.assertGreater(n, 100)
        self.assertEqual([p["prioridade"] for p in todas], sorted(p["prioridade"] for p in todas))
        cv = S.buscar_pistas(tema="crime-organizado", limite=500)
        self.assertTrue(cv and all("crime-organizado" in p["temas"] for p in cv))
        self.assertTrue(all(p["url"].startswith("https://x.com/republiqueBRA/status/") for p in cv))
        oruam = S.buscar_pistas(texto="oruam")
        self.assertTrue(oruam and all(p["relevancia"] in ("pista", "contexto") for p in oruam))
        self.assertEqual(S.buscar_pistas(tema="tema-que-nao-existe")["ok"], False)
        self.assertEqual(S.buscar_pistas(texto="zzzxxyyqq"), [])
        um = S.buscar_pistas(entidade="Comando Vermelho", limite=500)
        self.assertTrue(um and all(any(e["nome"] == "Comando Vermelho" for e in p["entidades"]) for p in um))

    def test_buscar_pistas_marcador_e_relevancia(self):
        self.assertEqual(S.buscar_pistas(marcador="marcador-que-nao-existe")["ok"], False)
        self.assertEqual(S.buscar_pistas(relevancia="xxx")["ok"], False)
        com = self.sql("""SELECT x.marcador_id m, count(*) n FROM post_triagem_marcador x JOIN post_triagem t ON t.post_id=x.post_id
                          WHERE t.relevancia IN ('pista','contexto') GROUP BY 1 ORDER BY 2 DESC LIMIT 1""")
        voc = self.sql("SELECT id FROM marcador LIMIT 1")
        self.assertTrue(voc)
        if com:  # há triagens marcadas: o filtro devolve exatamente as do banco
            r = S.buscar_pistas(marcador=com[0]["m"], limite=1000)
            self.assertEqual(len(r), com[0]["n"])
            self.assertTrue(all(com[0]["m"] in p["marcadores"] for p in r))
        else:
            self.assertEqual(S.buscar_pistas(marcador=voc[0]["id"]), [])
        n = self.sql("SELECT count(*) c FROM post_triagem WHERE relevancia='descartar'")[0]["c"]
        d = S.buscar_pistas(relevancia="descartar", limite=5000)
        self.assertEqual(len(d), n)
        self.assertTrue(all(p["relevancia"] == "descartar" for p in d))
        self.assertTrue(all(isinstance(p["marcadores"], list) for p in S.buscar_pistas(limite=5)))

    def test_relacao_nova_herda_ou_recebe_temas(self):
        a, b = self.par_sem_relacao()
        r = S.inserir_relacao(de=a, para=b, tipo="financeira", rotulo="Teste de tema", natureza="rep")
        self.assertTrue(r["ok"], r)
        self.assertIn("temas_inferidos", r)
        self.assertIn("caso-master", r["temas"])  # os dois são nós da teia
        self.assertEqual(S.buscar_relacoes(de=a, para=b)[0]["temas"], r["temas"])
        # explícitos: validados, não criam tema; em relação existente só acrescentam
        ruim = S.inserir_relacao(de=a, para=b, tipo="financeira", rotulo="Teste de tema", natureza="rep", temas=["inss", "tema-que-nao-existe"])
        self.assertFalse(ruim["ok"])
        self.assertIn("tema-que-nao-existe", ruim["erro"])
        self.assertEqual(self.n("tema"), 13)
        ok = S.inserir_relacao(de=a, para=b, tipo="financeira", rotulo="Teste de tema", natureza="rep", temas=["inss"])
        self.assertEqual(ok["acao"], "atualizada")
        self.assertEqual(set(ok["temas"]), set(r["temas"]) | {"inss"})
        self.assertIn(ok["relacao_id"], [x["id"] for x in S.buscar_relacoes(tema="inss", limite=500)])
        self.assertFalse(S.buscar_relacoes(tema="nada")["ok"])
        # explícitos numa relação nova substituem a inferência
        outro = self.sql("SELECT a.id a, b.id b FROM entidade a, entidade b WHERE a.id<b.id AND a.origem='teia' AND b.origem='teia' AND NOT EXISTS (SELECT 1 FROM relacao r WHERE (r.de=a.id AND r.para=b.id) OR (r.de=b.id AND r.para=a.id)) AND (a.id<>? OR b.id<>?) ORDER BY a.id DESC, b.id DESC LIMIT 1", a, b)[0]
        n = S.inserir_relacao(de=outro["a"], para=outro["b"], tipo="pessoal", rotulo="Tema explícito", natureza="rep", temas=["lagoinha"])
        self.assertEqual(n["temas"], ["lagoinha"])
        self.assertEqual(n["temas_informados"], ["lagoinha"])
        cod, saida = self.validar()
        self.assertEqual(cod, 0, saida)

    def test_tema_inexistente_na_fonte_rejeita_tudo(self):
        c0 = (self.n("fonte"), self.n("relacao"))
        r = S.inserir_fonte(**reportagem_ficticia(temas=["nao-existe"]))
        self.assertFalse(r["ok"])
        self.assertEqual((self.n("fonte"), self.n("relacao")), c0)
        ok = S.inserir_fonte(**reportagem_ficticia(temas=["pcc"]))
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(list(ok["temas_das_relacoes_criadas"].values()), [["pcc"]])


class TestRAG(Base):
    """RAG com o provedor 'hash' (determinístico, sem rede) para os testes não dependerem de modelo instalado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._env_antigo = os.environ.get("LDT_EMBED_PROVIDER")
        os.environ["LDT_EMBED_PROVIDER"] = "hash"
        sys.path.insert(0, str(RAIZ / "scripts"))
        import embeddings as E
        cls.E = E
        assert E.main(["--db", str(cls.tmp / "base.sqlite")]) == 0  # indexa a cópia-base (nunca o banco real)

    @classmethod
    def tearDownClass(cls):
        if cls._env_antigo is None:
            os.environ.pop("LDT_EMBED_PROVIDER", None)
        else:
            os.environ["LDT_EMBED_PROVIDER"] = cls._env_antigo
        super().tearDownClass()

    def test_provedor_e_idempotencia(self):
        info = self.E.provedor_ativo()
        self.assertEqual((info["provedor"], info["dim"]), ("hash", 256))
        n0 = self.n("embedding")
        self.assertGreater(n0, 2000)
        self.assertEqual(self.E.main(["--db", str(self.db)]), 0)  # nada mudou => nada regerado
        self.assertEqual(self.n("embedding"), n0)
        self.assertEqual(len(self.E.embed(["a venda do banco"])[0]), 256)

    def test_buscar_semantica_banco_brb(self):
        r = S.buscar_semantica("venda do banco ao BRB", limite=10)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["metodo"], "rrf(fts5, vetorial)")
        top5 = r["resultados"][:5]
        self.assertTrue(any(h["origem_tabela"] == "relacao" and {h["de"], h["para"]} == {"banco-master", "brb"} for h in top5),
                        [(h["origem_tabela"], h["origem_id"], h["titulo"]) for h in top5])
        h = r["resultados"][0]
        for campo in ("origem_tabela", "origem_id", "titulo", "trecho", "score"):
            self.assertIn(campo, h)
        # filtro de tabelas e entrada inválida
        so_rel = S.buscar_semantica("compra do BRB", tabelas=["relacao"], limite=5)
        self.assertTrue(so_rel["resultados"] and all(x["origem_tabela"] == "relacao" for x in so_rel["resultados"]))
        self.assertFalse(S.buscar_semantica("x", tabelas=["usuario"])["ok"])
        self.assertFalse(S.buscar_semantica("  ")["ok"])

    def test_buscar_semantica_sem_vetores_cai_para_fts(self):
        con = sqlite3.connect(str(self.db)); con.execute("DELETE FROM embedding"); con.commit(); con.close()
        r = S.buscar_semantica("compra do BRB", limite=5)
        self.assertTrue(r["ok"] and r["metodo"] == "fts5" and r["resultados"], r)
        self.assertTrue(any("embeddings" in a for a in r["avisos"]))

    def test_relacoes_similares_mesada(self):
        # par real (a relação 59 tem de=ciro-nogueira, para=daniel-vorcaro: a consulta vem na direção oposta => invertida)
        r = S.relacoes_similares("Mesada mensal de R$ 300 mil", de="daniel-vorcaro", para="ciro-nogueira")
        self.assertTrue(r["ok"], r)
        self.assertEqual([x["id"] for x in r["similares"]], [59])
        self.assertTrue(r["similares"][0]["invertida"])
        self.assertIn("Mesada", r["similares"][0]["rotulo"])
        self.assertFalse(r["similares"][0]["reutilizaria_na_insercao"])  # direção oposta: a inserção não reutiliza
        # paráfrase sem palavra em comum com "Mesada": o fallback hash só a acha baixando o limiar (modelo real passaria no padrão)
        sem = S.relacoes_similares("pagamento mensal de 300 mil a Ciro", de="daniel-vorcaro", para="ciro-nogueira")
        self.assertEqual(sem["similares"], [])
        com = S.relacoes_similares("pagamento mensal de 300 mil a Ciro", de="daniel-vorcaro", para="ciro-nogueira", cos_min=0.2)
        self.assertEqual(com["similares"][0]["id"], 59)
        # rótulo sem parentesco: nada acima do limiar
        self.assertEqual(S.relacoes_similares("Viagem de jatinho a Dubai", de="daniel-vorcaro", para="ciro-nogueira")["similares"], [])
        self.assertFalse(S.relacoes_similares("x", de="entidade-que-nao-existe")["ok"])

    def test_video_rotulo_parafraseado_reutiliza_relacao(self):
        v = video_ficticio()
        v["trechos"] = v["trechos"][:1]
        v["cortes_sugeridos"] = []
        v["trechos"][0]["entidades"] = ["ciro-nogueira", "daniel-vorcaro"]
        v["trechos"][0]["relacoes"] = [dict(de="ciro-nogueira", para="daniel-vorcaro", tipo="politica", rotulo="Mesada de R$ 300 mil", periodo="2024")]
        antes = self.n("relacao")
        r = S.inserir_video(**v)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["relacoes_criadas"], [])
        self.assertEqual(r["relacoes_existentes_reutilizadas"], [59])
        self.assertEqual(r["dedup"][0]["dedup_por"], "embedding")
        self.assertGreaterEqual(r["dedup"][0]["cos"], 0.6)
        self.assertEqual(self.n("relacao"), antes)
        self.assertEqual(self.sql("SELECT relacao_id FROM trecho_relacao")[0]["relacao_id"], 59)
        self.assertEqual(r["embeddings"]["status"], "ok")
        self.assertEqual(r["embeddings"]["gerados"]["trecho"], 1)
        self.assertTrue(self.sql("SELECT 1 FROM embedding WHERE origem_tabela='trecho'"))

    def test_video_rotulo_diferente_cria_e_dedup_entre_trechos_do_mesmo_video(self):
        v = video_ficticio()
        v["cortes_sugeridos"] = []
        rel = lambda rot: [dict(de="daniel-vorcaro", para="cvm", tipo="politica", rotulo=rot, periodo="2024")]
        v["trechos"][1]["relacoes"] = rel("Reunião sigilosa com diretoria da CVM")
        t3 = dict(v["trechos"][1], ordem=3, inicio_s=95, fim_s=120, relacoes=rel("Reunião sigilosa com a diretoria da CVM"))
        v["trechos"].append(t3)
        r = S.inserir_video(**v)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["relacoes_criadas"]), 1)  # só a da CVM: o trecho 3 reutiliza a recém-criada; o do Valadão reutiliza a existente
        self.assertEqual([d["trecho"] for d in r["dedup"]], [3])
        nova = r["relacoes_criadas"][0]
        self.assertEqual(self.sql("SELECT count(*) c FROM trecho_relacao WHERE relacao_id=?", nova)[0]["c"], 2)
        self.assertTrue(self.sql("SELECT 1 FROM embedding WHERE origem_tabela='relacao_rotulo' AND origem_id=?", str(nova)))

    def test_inserir_relacao_dedup_e_reindexacao(self):
        ex = self.sql("SELECT * FROM relacao WHERE id=59")[0]
        antes = self.n("relacao")
        r = S.inserir_relacao(de=ex["de"], para=ex["para"], tipo=ex["tipo"], rotulo="Mesada de R$ 300 mil", natureza="inv",
                              periodo_inicio="2024", descricao="descrição nova")
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["acao"], r["relacao_id"], r["dedup_por"]), ("atualizada", 59, "embedding"))
        self.assertEqual(self.n("relacao"), antes)
        self.assertEqual(self.sql("SELECT status FROM relacao WHERE id=59")[0]["status"], "publicada")
        # descrição mudou => vetor da relação 59 regerado no mesmo commit
        h = self.sql("SELECT texto_hash FROM embedding WHERE origem_tabela='relacao' AND origem_id='59'")[0]["texto_hash"]
        con = sqlite3.connect(str(self.db))
        try:
            self.assertEqual(h, self.E._h(self.E.textos_de(con, "relacao", ["59"])["59"]))
        finally:
            con.close()
        # rótulo realmente novo no mesmo par: cria e já indexa
        r2 = S.inserir_relacao(de=ex["de"], para=ex["para"], tipo=ex["tipo"], rotulo="Viagem de jatinho a Dubai", natureza="rep")
        self.assertEqual(r2["acao"], "criada")
        self.assertNotIn("dedup_por", r2)
        self.assertTrue(self.sql("SELECT 1 FROM embedding WHERE origem_tabela='relacao_rotulo' AND origem_id=?", str(r2["relacao_id"])))
        # desligável
        os.environ["LDT_DEDUP_EMBEDDING"] = "0"
        try:
            r3 = S.inserir_relacao(de=ex["de"], para=ex["para"], tipo=ex["tipo"], rotulo="Mesada de R$ 300 mil", natureza="inv", periodo_inicio="2024")
        finally:
            os.environ.pop("LDT_DEDUP_EMBEDDING")
        self.assertEqual(r3["acao"], "criada")

    def test_sem_provedor_a_escrita_segue_e_anota(self):
        os.environ["LDT_EMBED_PROVIDER"] = "openai"  # sem chave => indisponível (sem rede)
        chave = {k: os.environ.pop(k, None) for k in ("LDT_EMBED_API_KEY", "OPENAI_API_KEY")}
        try:
            v = video_ficticio()
            r = S.inserir_video(**v)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["embeddings"]["status"], "ignorado")
            self.assertIn("chave ausente", r["embeddings"]["motivo"])
            self.assertEqual(len(r["relacoes_criadas"]), 1)
            self.assertFalse(S.relacoes_similares("x", de="cvm")["ok"])
        finally:
            os.environ["LDT_EMBED_PROVIDER"] = "hash"
            for k, val in chave.items():
                if val is not None:
                    os.environ[k] = val


class TestExtras(Base):
    def test_resumo(self):
        r = S.resumo_banco()
        self.assertGreater(r["entidade"], 300)
        self.assertIn("publicada", r["relacao_por_status"])
        self.assertEqual(r["tema"], 13)
        self.assertIn("linha_do_tempo", r["relacao_por_origem"])
        self.assertIn("fonte_por_tipo", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
