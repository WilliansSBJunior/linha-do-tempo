#!/usr/bin/env python3
"""Testes da extração (mcp/extracao.py) contra uma CÓPIA do repo em diretório temporário (o banco real nunca é aberto para escrita).

Uso (da raiz do repo):  python3 mcp/test_extracao.py -v
Rede: nenhum teste depende dela, exceto `test_url_real`, que só roda com LDT_TEST_REDE=1 (e pula se o proxy bloquear).
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import server as S  # noqa: E402
import extracao as X  # noqa: E402

REAL_DB, REAL_DUMP = RAIZ / "data" / "linha-do-tempo.sqlite", RAIZ / "data" / "dump.sql"


def estado_real():
    return {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in (REAL_DB, REAL_DUMP)}


TEXTO = """Reportagem de teste sobre o caso

Daniel Vorcaro e o BRB negociaram a compra de uma carteira de crédito em 2024. A operação foi revelada pela imprensa.

O senador Ciro Nogueira recebeu R$ 300 mil, segundo o relato. Os pagamentos teriam começado em 2023.

Leia também: outras notícias do dia. A economia segue em debate no Congresso.
"""

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Banco liquidado e política | Jornal Teste</title>
<meta property="og:title" content="Banco é liquidado e atinge a política | Jornal Teste">
<meta property="article:published_time" content="2025-11-18T09:30:00-03:00">
<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2020-01-01T00:00:00Z"}</script>
<script>var x = "Não deve aparecer no texto";</script></head>
<body><nav><ul><li><a href="/">Home</a></li></ul><p>Menu principal com bastante texto de navegação que não deve entrar no corpo.</p></nav>
<div class="cookie-banner"><p>Usamos cookies para melhorar sua experiência. Aceitar todos os cookies.</p></div>
<article><h1>Banco é liquidado e atinge a política</h1>
<p>O Banco Central decretou a liquidação do Banco Master na terça-feira, segundo comunicado oficial. A decisão afetou investidores em todo o país.</p>
<p>Daniel Vorcaro, controlador da instituição, é investigado pela Polícia Federal desde 2025. A defesa nega irregularidades.</p>
<p>Leia também: veja as outras notícias do dia</p>
<p>Assine o jornal e tenha acesso ilimitado a todo o conteúdo.</p>
<div class="related"><p>Conteúdo relacionado que não pertence à reportagem principal e é bem longo para tentar enganar o parser.</p></div>
</article>
<aside><p>Barra lateral com publicidade e muito texto que não deve ser considerado conteúdo principal da página.</p></aside>
<footer><p>Todos os direitos reservados. Jornal Teste.</p></footer></body></html>"""


def pdf_minimo(linhas):
    """PDF de 1 página, Helvetica/WinAnsi, só com a stdlib (um objeto Tj por linha)."""
    def esc(s):
        return s.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    conteudo = b"BT /F1 11 Tf 14 TL 50 780 Td\n" + b"".join(b"(" + esc(l) + b") Tj T*\n" for l in linhas) + b"ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real0 = estado_real()
        cls.tmp = Path(tempfile.mkdtemp(prefix="ldt-extr-"))
        cls.repo = cls.tmp / "repo"
        shutil.copytree(RAIZ / "scripts", cls.repo / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(RAIZ / "data", cls.repo / "data", ignore=shutil.ignore_patterns("*.sqlite*"))
        shutil.copy(REAL_DB, cls.tmp / "base.sqlite")

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


class TestSegmentar(unittest.TestCase):
    def test_limites_e_boilerplate(self):
        longa = " ".join(f"Frase número {i} com algum texto relevante para o teste de tamanho." for i in range(30))
        tr = X.segmentar("Primeiro parágrafo curto, mas válido. Segunda frase. Terceira frase. Quarta frase vai para outro trecho.\n\n"
                         "Assine o jornal e receba nossa newsletter.\n\nUsamos cookies para melhorar a navegação do site em geral.\n\n" + longa)
        textos = [t["texto"] for t in tr]
        self.assertEqual([t["ordem"] for t in tr], list(range(1, len(tr) + 1)))
        self.assertTrue(all(len(t) <= X.LIMITE_TRECHO for t in textos))
        self.assertTrue(all(1 <= len(X._frases(t)) <= 3 for t in textos))
        self.assertFalse(any("Assine" in t or "cookies" in t for t in textos))
        self.assertTrue(textos[0].startswith("Primeiro parágrafo") and "Quarta" not in textos[0])

    def test_abreviaturas_nao_quebram(self):
        fr = X._frases("O Sr. Ciro Nogueira e o Min. Dias Toffoli falaram sobre o art. 5 da lei. Depois saíram. R$ 1.500,50 foram citados.")
        self.assertEqual(len(fr), 3, fr)

    def test_valores_e_anos(self):
        v = X.extrair_valores("Recebeu R$ 1,5 bi, US$ 30 milhões, 300 mil reais, R$ 12.500,75 e 10% do total; alta de 2,5 por cento.")
        got = [(x["valor"], x["moeda"]) for x in v]
        self.assertEqual(got, [(1.5e9, "BRL"), (3e7, "USD"), (3e5, "BRL"), (12500.75, "BRL"), (10.0, "pct"), (2.5, "pct")])
        self.assertEqual(X.extrair_anos("Em 2024, desde 1998, em 12/03/2023, R$ 2024 e 20245"), [1998, 2023, 2024])


class TestExtrair(unittest.TestCase):
    def test_html_sintetico(self):
        r = X.extrair_html(HTML)
        self.assertEqual(r["titulo"], "Banco é liquidado e atinge a política")
        self.assertEqual(r["data_publicacao"], "2025-11-18")  # meta vence o JSON-LD
        self.assertEqual(r["data_origem"], "meta:article:published_time")
        t = r["texto"]
        self.assertIn("liquidação do Banco Master", t)
        self.assertIn("Daniel Vorcaro", t)
        for ruim in ("Menu principal", "cookies", "Conteúdo relacionado", "Barra lateral", "direitos reservados", "Não deve aparecer"):
            self.assertNotIn(ruim, t)
        # boilerplate dentro do <article> sai na segmentação
        seg = " ".join(s["texto"] for s in X.segmentar(t))
        self.assertNotIn("Leia também", seg)
        self.assertNotIn("Assine", seg)

    def test_html_json_ld_e_data_no_texto(self):
        ld = '<html><head><title>X</title><script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","datePublished":"2023-04-05T10:00:00Z","headline":"Título LD"}]}</script></head><body><div><p>' + "Texto longo da reportagem. " * 12 + "</p></div></body></html>"
        r = X.extrair_html(ld)
        self.assertEqual((r["data_publicacao"], r["titulo"], r["data_origem"]), ("2023-04-05", "Título LD", "json-ld"))
        r2 = X.extrair_html("<html><body><div><p>Publicado em 3 de março de 2022 por Fulano. " + "Mais texto da matéria. " * 12 + "</p></div></body></html>")
        self.assertEqual((r2["data_publicacao"], r2["data_origem"]), ("2022-03-03", "texto"))

    def test_url_com_download_simulado(self):
        with mock.patch.object(X, "_baixar", return_value=(HTML.encode(), "text/html; charset=utf-8", "https://www.jornalteste.com.br/a")):
            r = X.extrair(url="https://www.jornalteste.com.br/a?utm_source=x#topo")
        self.assertEqual((r["tipo"], r["veiculo"], r["data_publicacao"], r["url"]), ("reportagem", "jornalteste.com.br", "2025-11-18", "https://www.jornalteste.com.br/a"))
        self.assertEqual(len(r["hash"]), 64)

    def test_entrada_invalida(self):
        with self.assertRaises(X.ExtracaoErro):
            X.extrair()
        with self.assertRaises(X.ExtracaoErro):
            X.extrair(url="http://a.com", texto="x" * 100)

    def test_pdf(self):
        try:
            from reportlab.pdfgen import canvas  # noqa: PLC0415
            gerador = "reportlab"
        except ImportError:
            gerador = "stdlib"
        try:
            import pypdf  # noqa: F401, PLC0415
        except ImportError:
            if not shutil.which("pdftotext"):
                self.skipTest("sem pypdf e sem pdftotext: PDF não testável aqui")
        d = Path(tempfile.mkdtemp(prefix="ldt-pdf-"))
        try:
            f = d / "nota.pdf"
            linhas = ["Relatório da Polícia Federal de 05/06/2024", "", "A PF cita Daniel Vorcaro e o BRB em operação de R$ 12 milhões.",
                      "Segundo o documento, os pagamentos ocorreram em 2023."]
            if gerador == "reportlab":
                c = canvas.Canvas(str(f))
                for i, l in enumerate(linhas):
                    c.drawString(50, 780 - 16 * i, l)
                c.save()
            else:
                f.write_bytes(pdf_minimo(linhas))
            r = X.extrair(arquivo=str(f))
            self.assertEqual(r["tipo"], "pdf")
            self.assertIn("Daniel Vorcaro", r["texto"])
            self.assertEqual(r["data_publicacao"], "2024-06-05")
            self.assertIn(r["metodo"], ("pypdf", "pdftotext"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless(os.environ.get("LDT_TEST_REDE") == "1", "defina LDT_TEST_REDE=1 para o teste com rede real")
    def test_url_real(self):
        url = os.environ.get("LDT_TEST_URL", "https://www.poder360.com.br/")
        try:
            r = X.extrair(url=url)
        except X.ExtracaoErro as e:
            self.skipTest(f"rede indisponível/bloqueada: {e}")
        self.assertGreater(len(r["texto"]), 200)
        self.assertEqual(r["veiculo"], "poder360.com.br")


class TestIngerir(Base):
    def test_texto_colado_rascunho_e_gravar(self):
        antes = {t: self.n(t) for t in ("fonte", "trecho", "relacao", "evidencia")}
        rs = X.ingerir(texto=TEXTO, modo="rascunho")
        self.assertTrue(rs["ok"], rs)
        self.assertFalse(rs["gravado"])
        self.assertEqual(rs["fonte"]["titulo"], "Reportagem de teste sobre o caso")
        self.assertEqual(rs["fonte"]["tipo"], "documento")
        tr = rs["trechos"]
        self.assertGreaterEqual(len(tr), 3)
        t1 = next(t for t in tr if "daniel-vorcaro" in t["entidades"])
        self.assertEqual(sorted(t1["entidades"]), ["brb", "daniel-vorcaro"])
        self.assertEqual(t1["anos_referidos"], [2024])
        t2 = next(t for t in tr if "ciro-nogueira" in t["entidades"])
        self.assertEqual([(v["valor"], v["moeda"]) for v in t2["valores"]], [(300000.0, "BRL")])
        self.assertEqual(t2["anos_referidos"], [2023])
        self.assertTrue(all(t["natureza"] == "reportada" and t["confianca"] == 0.3 and t["localizacao"] for t in tr))
        # exatamente UMA co-citação (Vorcaro<->BRB); boilerplate fora
        self.assertEqual(len(rs["relacoes_propostas"]), 1)
        rel = rs["relacoes_propostas"][0]
        self.assertEqual((rel["de"], rel["para"], rel["tipo"]), ("daniel-vorcaro", "brb", "outra"))
        self.assertTrue(rel["rotulo"].startswith("Co-citação em Reportagem de teste"), rel["rotulo"])
        validos = {r["id"] for r in self.sql("SELECT id FROM tema")}
        self.assertTrue(rel["temas"] and set(rel["temas"]) <= validos, rel["temas"])
        self.assertNotIn("Leia também", " ".join(t["afirmacao"] for t in tr))
        # rascunho não grava
        self.assertEqual({t: self.n(t) for t in antes}, antes)
        # o rascunho é aceito por inserir_fonte como veio (contrato)
        # modo gravar
        rg = X.ingerir(texto=TEXTO, modo="gravar")
        self.assertTrue(rg["ok"], rg)
        self.assertTrue(rg["gravado"] and not rg["idempotente"])
        self.assertEqual(self.n("fonte"), antes["fonte"] + 1)
        self.assertEqual(self.n("trecho"), antes["trecho"] + len(tr))
        self.assertEqual(self.n("relacao"), antes["relacao"] + 1)
        r = self.sql("SELECT * FROM relacao WHERE rotulo LIKE 'Co-citação em Reportagem de teste%'")
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["status"], r[0]["confianca"], r[0]["natureza_id"], r[0]["tipo"], r[0]["origem"]), ("revisar", 0.3, "reportada", "outra", "classificador"))
        self.assertGreaterEqual(len(self.sql("SELECT 1 FROM relacao_tema WHERE relacao_id=?", r[0]["id"])), 1)
        self.assertEqual(self.sql("SELECT valor, moeda FROM trecho_valor")[0]["valor"], 300000.0)
        self.assertIn(2024, [x["ano"] for x in self.sql("SELECT ano FROM trecho_ano")])
        self.assertGreaterEqual(self.n("trecho_entidade"), 3)
        # 2ª chamada: idempotente, nada escrito
        snap = {t: self.n(t) for t in ("fonte", "trecho", "relacao", "trecho_entidade", "trecho_valor")}
        r2 = X.ingerir(texto=TEXTO, modo="gravar")
        self.assertTrue(r2["ok"] and r2["idempotente"] and not r2["gravado"], r2)
        self.assertEqual({t: self.n(t) for t in snap}, snap)
        r3 = X.ingerir(texto=TEXTO, modo="rascunho")
        self.assertEqual(r3["ja_gravada"]["fonte_id"], rg["fonte_id"])

    def test_rascunho_e_aceito_por_inserir_fonte(self):
        rs = X.ingerir(texto=TEXTO, modo="rascunho")
        r = S.inserir_fonte({"tipo": "reportagem", **{k: v for k, v in rs["fonte"].items() if k != "tipo"}}, rs["trechos"])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["relacoes_criadas"]), 1)
        self.assertEqual(r["trechos"], len(rs["trechos"]))
        # depois do inserir_fonte (mesmo texto/hash), ingerir(gravar) é idempotente
        self.assertTrue(X.ingerir(texto=TEXTO, modo="gravar")["idempotente"])

    def test_par_ja_relacionado_nao_duplica(self):
        t = "Daniel Vorcaro teria pago mesada ao senador Ciro Nogueira, segundo a investigação em curso."
        rs = X.ingerir(texto=t, titulo="Mesada", modo="rascunho")
        self.assertEqual(rs["relacoes_propostas"], [])
        pj = rs["trechos"][0]["pares_ja_relacionados"][0]
        self.assertEqual({pj["de"], pj["para"]}, {"daniel-vorcaro", "ciro-nogueira"})
        self.assertEqual(pj["relacoes"][0]["tipo"], "politica")

    def test_tres_entidades_e_orgao_com_orgao(self):
        with S.leitura() as con:
            ant, _ = X.anotar([{"ordem": 1, "texto": "Daniel Vorcaro, o BRB e Ciro Nogueira apareceram juntos na reportagem."},
                               {"ordem": 2, "texto": "O STF e o TCU analisaram o caso do banco em sessão."},
                               {"ordem": 3, "texto": "Daniel Vorcaro, BRB, Ciro Nogueira e Henrique Vorcaro apareceram na lista."}], con, "x.com", "2025-01-02")
        pares = {(r["de"], r["para"]) for r in ant[0]["relacoes"]}
        self.assertEqual(pares, {("daniel-vorcaro", "brb"), ("brb", "ciro-nogueira")})  # Vorcaro<->Ciro já existe no banco
        self.assertEqual(ant[1]["relacoes"], [])  # órgão <-> órgão
        self.assertEqual(ant[2]["relacoes"], [])  # 4 entidades: nenhuma relação
        self.assertIn("Co-citação em x.com (2025-01-02)", ant[0]["relacoes"][0]["rotulo"])

    def test_sobrenome_ambiguo_e_nao_resolvidas(self):
        t = "O ministro Silva e o doutor Souza conversaram com Fulano Beltrano de Tal sobre a empresa XPTO Holding no Rio."
        rs = X.ingerir(texto=t, titulo="Teste", modo="rascunho")
        self.assertEqual(rs["trechos"][0]["entidades"], [])
        ments = {n["mencao"]: n for n in rs["entidades_nao_resolvidas"]}
        self.assertIn("Fulano Beltrano de Tal", ments)
        self.assertLessEqual(len(ments["Fulano Beltrano de Tal"]["sugestoes"]), 3)
        self.assertEqual(ments["Fulano Beltrano de Tal"]["trechos"], [1])

    def test_url_simulada_grava_evidencia_e_idempotente_por_url(self):
        url = "https://www.jornalteste.com.br/materia?utm_campaign=z"
        with mock.patch.object(X, "_baixar", return_value=(HTML.encode(), "text/html; charset=utf-8", url)):
            r = X.ingerir(url=url, modo="gravar")
            self.assertTrue(r["ok"], r)
            ev = self.sql("SELECT * FROM evidencia WHERE url='https://www.jornalteste.com.br/materia'")
            self.assertEqual(len(ev), 1)
            f = self.sql("SELECT * FROM fonte WHERE url='https://www.jornalteste.com.br/materia'")[0]
            self.assertEqual((f["tipo"], f["canal"], f["publicado_em"], f["evidencia_id"]), ("reportagem", "jornalteste.com.br", "2025-11-18", ev[0]["id"]))
            self.assertEqual(f["hash_texto"], X._hash(f["texto"]))
            n_tr = self.n("trecho")
            r2 = X.ingerir(url="https://jornalteste.com.br/materia".replace("https://", "https://www."), modo="gravar")
            self.assertTrue(r2["idempotente"], r2)
            self.assertEqual(self.n("trecho"), n_tr)

    def test_url_existente_sem_texto_com_trechos_nao_e_sobrescrita(self):
        url = "https://www.jornalteste.com.br/curada"
        r = S.inserir_fonte_core({"tipo": "reportagem", "titulo": "Curada à mão", "url": url},
                                 [{"ordem": 1, "afirmacao": "Algo curado", "natureza": "documentada", "confianca": 0.9}])
        self.assertTrue(r["ok"], r)
        with mock.patch.object(X, "_baixar", return_value=(HTML.encode(), "text/html", url)):
            g = X.ingerir(url=url, modo="gravar")
        self.assertFalse(g["ok"])
        self.assertEqual(self.n("trecho"), 1)

    def test_rejeicoes(self):
        self.assertFalse(X.ingerir(modo="gravar")["ok"])
        self.assertFalse(X.ingerir(texto="Texto qualquer longo o bastante para passar do mínimo.", modo="xx")["ok"])
        self.assertFalse(X.ingerir(texto="Texto qualquer longo o bastante para passar do mínimo.", tipo="invalido")["ok"])

    def test_ferramenta_registrada(self):
        srv = S.criar_servidor()
        nomes = {t.name for t in asyncio.run(srv.list_tools())}
        self.assertIn("ingerir", nomes)
        self.assertIn("inserir_fonte", nomes)


if __name__ == "__main__":
    unittest.main()
