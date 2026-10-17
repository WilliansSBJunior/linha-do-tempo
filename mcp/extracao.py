"""Ponta de EXTRAÇÃO da Linha do Tempo: qualquer coisa (URL, PDF, HTML salvo, texto colado) -> fonte + trechos anotados.

Não há modelo de linguagem aqui. O módulo faz só o que é determinístico:
  extrair()   URL/arquivo/texto -> {tipo, titulo, veiculo, data_publicacao, texto, hash}
  segmentar() texto -> trechos de 1 a 3 frases (<= 600 caracteres), sem boilerplate
  anotar()    entidades (entidade_alias, mesmas regras de scripts/curadoria.py), anos, valores, co-citações
  ingerir()   ferramenta MCP: modo 'rascunho' (devolve o JSON de inserir_fonte, sem gravar) ou 'gravar'

`server.py` registra `ingerir` com UMA linha no fim do arquivo (`registrar`), que embrulha `criar_servidor`.
Este módulo só importa `server` de forma tardia (o servidor roda como __main__ e não pode ser carregado duas vezes).

Dependências opcionais (nenhuma é obrigatória): trafilatura (HTML), pypdf (PDF), `pdftotext`/`pdfinfo` do poppler (PDF).
Sem elas: parser HTML da stdlib (html.parser) e `pdftotext`. PDF escaneado (sem camada de texto) NÃO tem OCR.
"""
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import dominio_de, normalizar_url  # noqa: E402
from slug import alias_norm, sem_acento  # noqa: E402
import curadoria as CUR  # noqa: E402

LIMITE_TRECHO = 600
MAX_BYTES = 8 * 1024 * 1024
TIPOS_FONTE = ["video", "reportagem", "documento", "pdf", "depoimento", "decisao", "transcricao", "outro"]
UA = "Mozilla/5.0 (compatible; LinhaDoTempoBot/1.0; +extracao)"
_S = None  # módulo server (injetado por registrar(); import tardio como plano B)


def _srv():
    global _S
    if _S is None:
        import server  # noqa: PLC0415
        _S = server
    return _S


def _hash(texto):
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()  # igual a server._hash_texto sobre texto.strip()


# =============================================================================== extrair
class ExtracaoErro(Exception):
    pass


MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
         "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
_RE_DATA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_DATA_EXT = re.compile(r"\b(\d{1,2})\s*(?:º|°)?\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})\b", re.I)
_RE_DATA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def _iso(a, m, d):
    try:
        a, m, d = int(a), int(m), int(d)
        if 1990 <= a <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            return f"{a:04d}-{m:02d}-{d:02d}"
    except ValueError:
        pass
    return None


def normalizar_data(s):
    """'2024-05-03T10:00:00-03:00' | '03/05/2024' | '3 de maio de 2024' -> '2024-05-03' (ou None)."""
    if not s:
        return None
    s = str(s).strip()
    m = _RE_DATA_ISO.search(s)
    if m:
        return _iso(*m.groups())
    m = _RE_DATA_NUM.search(s)
    if m:
        return _iso(m.group(3), m.group(2), m.group(1))
    m = _RE_DATA_EXT.search(sem_acento(s))
    if m:
        return _iso(m.group(3), MESES[m.group(2).lower()], m.group(1))
    return None


def data_no_texto(texto, janela=900):
    """Primeira data nas primeiras `janela` letras do texto (bylines costumam ficar no topo)."""
    topo = texto[:janela]
    achados = []
    for rx, ordem in ((_RE_DATA_NUM, (3, 2, 1)), (_RE_DATA_ISO, (1, 2, 3))):
        for m in rx.finditer(topo):
            g = m.groups()
            d = _iso(g[ordem[0] - 1], g[ordem[1] - 1], g[ordem[2] - 1])
            if d:
                achados.append((m.start(), d))
    for m in _RE_DATA_EXT.finditer(sem_acento(topo)):
        d = _iso(m.group(3), MESES[m.group(2).lower()], m.group(1))
        if d:
            achados.append((m.start(), d))
    return min(achados)[1] if achados else None


# ---- HTML (parser stdlib) ---------------------------------------------------------------------------------------------
_IGNORAR = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe", "button", "template",
            "select", "figcaption", "dialog", "menu"}
_VAZIAS = {"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "base", "col", "embed", "param", "track"}
_CLASSE_RUIM = {"comment", "comments", "comentarios", "share", "social", "related", "relacionadas", "relacionados", "newsletter", "cookie",
                "cookies", "banner", "menu", "sidebar", "promo", "publicidade", "advert", "advertisement", "ads", "ad", "outbrain",
                "taboola", "breadcrumb", "breadcrumbs", "footer", "nav", "subscribe", "paywall", "widget", "tags", "leia", "mais-lidas",
                "mais", "toolbar", "author-box", "bio"}


def _ruim(attrs):
    toks = set(re.split(r"[^a-z0-9]+", ((attrs.get("class") or "") + " " + (attrs.get("id") or "")).lower()))
    toks.discard("")
    return bool(toks & _CLASSE_RUIM) or (attrs.get("aria-hidden") == "true") or ("hidden" in attrs and attrs.get("hidden") != "false")


class _Pagina(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = {"tag": "#raiz", "filhos": [], "ps": [], "pai": None, "ign": False}
        self.no = self.raiz
        self.pilha = [self.raiz]
        self.metas, self.ld, self.titulo_tag, self.h1, self.time_dt = {}, [], "", "", None
        self._buf_p = None
        self._ctx = None  # 'title' | 'h1' | 'ld'
        self._ctxbuf = []
        self.todos = []  # (seq, nó, texto) de cada <p>
        self.texto_corpo = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if k and a.get("content"):
                self.metas.setdefault(k, a["content"])
            return
        if tag == "time" and a.get("datetime") and self.time_dt is None:
            self.time_dt = a["datetime"]
        if tag in _VAZIAS:
            if tag == "br" and self._buf_p is not None:
                self._buf_p.append(" ")
            return
        if tag == "p" and self._buf_p is not None:
            self._fechar_p()
        n = {"tag": tag, "filhos": [], "ps": [], "pai": self.no, "ign": self.no["ign"] or tag in _IGNORAR or _ruim(a)}
        self.no["filhos"].append(n)
        self.no = n
        self.pilha.append(n)
        if tag == "p":
            self._buf_p = []
        if tag == "title":
            self._ctx, self._ctxbuf = "title", []
        elif tag == "h1" and not self.h1:
            self._ctx, self._ctxbuf = "h1", []
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._ctx, self._ctxbuf = "ld", []

    def handle_endtag(self, tag):
        if tag in _VAZIAS:
            return
        idx = next((i for i in range(len(self.pilha) - 1, 0, -1) if self.pilha[i]["tag"] == tag), None)
        if idx is None:
            return
        for n in reversed(self.pilha[idx:]):
            if n["tag"] == "p":
                self._fechar_p()
        del self.pilha[idx:]
        self.no = self.pilha[-1]
        if tag in ("title", "h1", "script") and self._ctx:
            txt = "".join(self._ctxbuf)
            if self._ctx == "title":
                self.titulo_tag = txt.strip()
            elif self._ctx == "h1":
                self.h1 = re.sub(r"\s+", " ", txt).strip()
            elif self._ctx == "ld":
                self.ld.append(txt)
            self._ctx = None

    def _fechar_p(self):
        if self._buf_p is None:
            return
        txt = re.sub(r"\s+", " ", "".join(self._buf_p)).strip()
        self._buf_p = None
        pai = self.no
        while pai["tag"] == "p" and pai["pai"] is not None:
            pai = pai["pai"]
        if txt and not self.no["ign"]:
            item = (len(self.todos), pai, txt)
            self.todos.append(item)
            pai["ps"].append(item)

    def handle_data(self, data):
        if self._ctx:
            self._ctxbuf.append(data)
        if self._buf_p is not None:
            self._buf_p.append(data)
        elif not self.no["ign"] and data.strip():
            self.texto_corpo.append(data.strip())

    def close(self):
        super().close()
        self._fechar_p()


def _total(no):
    if "_t" not in no:
        no["_t"] = sum(len(t) for _, _, t in no["ps"]) + sum(_total(f) for f in no["filhos"])
    return no["_t"]


def _contem(no, alvo):
    while alvo is not None:
        if alvo is no:
            return True
        alvo = alvo["pai"]
    return False


def _ld_campos(blocos):
    """datePublished/headline do JSON-LD (inclusive @graph e listas)."""
    achados = {}

    def anda(o):
        if isinstance(o, dict):
            for k in ("datePublished", "dateCreated", "headline", "name"):
                if isinstance(o.get(k), str) and o[k].strip():
                    achados.setdefault(k, o[k].strip())
            for v in o.values():
                anda(v)
        elif isinstance(o, list):
            for v in o:
                anda(v)

    for b in blocos:
        try:
            anda(json.loads(b))
        except ValueError:
            continue
    return achados


def _limpar_titulo(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    for sep in (" | ", " – ", " — ", " - "):
        if sep in t:
            ini, fim = t.rsplit(sep, 1)
            if len(fim) <= 30 and len(ini) >= 15:
                t = ini.strip()
    return t


def extrair_html(html, url=None):
    """HTML (str) -> dict(titulo, data_publicacao, texto, metodo, data_origem). Sem rede."""
    p = _Pagina()
    p.feed(html)
    p.close()
    m = p.metas
    ld = _ld_campos(p.ld)
    titulo = _limpar_titulo(m.get("og:title") or m.get("twitter:title") or ld.get("headline") or p.h1 or p.titulo_tag)
    data, origem = None, None
    for k in ("article:published_time", "og:article:published_time", "datepublished", "date", "pubdate", "publishdate",
              "dc.date.issued", "dc.date", "sailthru.date", "parsely-pub-date", "article:published", "publication_date"):
        if normalizar_data(m.get(k)):
            data, origem = normalizar_data(m[k]), f"meta:{k}"
            break
    if not data and normalizar_data(ld.get("datePublished") or ld.get("dateCreated")):
        data, origem = normalizar_data(ld.get("datePublished") or ld.get("dateCreated")), "json-ld"
    if not data and normalizar_data(p.time_dt):
        data, origem = normalizar_data(p.time_dt), "time"
    texto, metodo = None, "stdlib"
    try:  # opcional: trafilatura, se instalada
        import trafilatura  # noqa: PLC0415
        t = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True, url=url)
        if t and len(t) >= 200:
            texto, metodo = t, "trafilatura"
    except Exception:
        pass
    if texto is None:
        texto = _texto_principal(p)
    if not data:
        data = data_no_texto(texto)
        origem = "texto" if data else None
    return {"titulo": titulo, "data_publicacao": data, "texto": texto, "metodo": metodo, "data_origem": origem}


def _texto_principal(p):
    total = _total(p.raiz)
    if total < 80:  # página sem <p>: cai para o texto solto do corpo
        return "\n\n".join(p.texto_corpo)
    artigos = []

    def acha(no):
        if no["tag"] == "article" and not no["ign"]:
            artigos.append(no)
        for f in no["filhos"]:
            acha(f)

    acha(p.raiz)
    no = max(artigos, key=_total) if artigos and max(_total(a) for a in artigos) >= 200 else p.raiz
    while no["filhos"]:  # desce enquanto um único filho concentra a maior parte do texto
        melhor = max(no["filhos"], key=_total)
        if _total(melhor) >= 0.7 * _total(no) and _total(melhor) > 0:
            no = melhor
        else:
            break
    blocos = [t for _, n, t in p.todos if _contem(no, n)]
    longos = [t for t in blocos if len(t) >= 40]
    return "\n\n".join(longos if sum(map(len, longos)) >= 200 else blocos)


# ---- PDF ---------------------------------------------------------------------------------------------------------------
def extrair_pdf_bytes(dados):
    """-> (texto, titulo_meta, metodo). pypdf se existir; senão `pdftotext` (poppler). PDF escaneado devolve texto vazio (sem OCR)."""
    try:
        import io  # noqa: PLC0415
        import pypdf  # noqa: PLC0415
        r = pypdf.PdfReader(io.BytesIO(dados))
        paginas = [(pg.extract_text() or "") for pg in r.pages]
        titulo = (r.metadata.title if r.metadata and r.metadata.title else None)
        return _juntar_linhas_pdf("\n\n".join(paginas)), titulo, "pypdf"
    except ImportError:
        pass
    exe = shutil.which("pdftotext")
    if not exe:
        raise ExtracaoErro("nenhum extrator de PDF disponível (instale pypdf ou o poppler-utils/pdftotext)")
    tmp = Path(__import__("tempfile").mkdtemp(prefix="ldt-pdf-"))
    try:
        f = tmp / "entrada.pdf"
        f.write_bytes(dados)
        out = subprocess.run([exe, "-enc", "UTF-8", str(f), "-"], capture_output=True, timeout=120)
        if out.returncode != 0:
            raise ExtracaoErro(f"pdftotext falhou: {out.stderr.decode('utf-8', 'replace')[:200]}")
        titulo = None
        info = shutil.which("pdfinfo")
        if info:
            r = subprocess.run([info, str(f)], capture_output=True, timeout=30)
            m = re.search(r"^Title:\s*(.+)$", r.stdout.decode("utf-8", "replace"), re.M)
            titulo = m.group(1).strip() if m else None
        return _juntar_linhas_pdf(out.stdout.decode("utf-8", "replace")), titulo, "pdftotext"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _juntar_linhas_pdf(t):
    """Parágrafos separados por linha em branco; quebras de linha dentro do parágrafo viram espaço (e remove hifenização de fim de linha)."""
    t = t.replace("\f", "\n\n").replace("\r", "")
    paras = []
    for bloco in re.split(r"\n\s*\n", t):
        linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
        if not linhas:
            continue
        out = ""
        for l in linhas:
            if out.endswith("-") and l[:1].islower():
                out = out[:-1] + l
            else:
                out = (out + " " + l).strip()
        paras.append(out)
    return "\n\n".join(paras)


# ---- fontes: URL / arquivo / texto -------------------------------------------------------------------------------------
_RE_DECISAO = re.compile(r"\b(ac[óo]rd[ãa]o|ementa|relator[a]?|habeas corpus|agravo|mandado de seguran[çc]a|apela[çc][ãa]o|recurso extraordin[áa]rio|"
                         r"voto d[oa] relator|decis[ãa]o monocr[áa]tica|senten[çc]a|dispositivo|ministro relator|tribunal)\b", re.I)


def _parece_decisao(texto):
    return len({m.group(1).lower() for m in _RE_DECISAO.finditer(texto[:6000])}) >= 3


def _baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*;q=0.8",
                                               "Accept-Language": "pt-BR,pt;q=0.9", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            dados = r.read(MAX_BYTES + 1)
            ctype = r.headers.get("Content-Type", "")
            if r.headers.get("Content-Encoding", "").lower() == "gzip":
                dados = gzip.decompress(dados)
            final = r.geturl()
    except Exception as e:
        raise ExtracaoErro(f"não consegui baixar {url}: {type(e).__name__}: {e}") from e
    if len(dados) > MAX_BYTES:
        raise ExtracaoErro(f"resposta maior que {MAX_BYTES // 1024 // 1024} MB")
    return dados, ctype, final


def _decodificar(dados, ctype=""):
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", dados[:4096], re.I)
    cands = []
    if m:
        cands.append(m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1))
    cands += ["utf-8", "cp1252"]
    for c in cands:
        try:
            return dados.decode(c)
        except (UnicodeDecodeError, LookupError):
            continue
    return dados.decode("utf-8", "replace")


def _normalizar_texto_livre(t):
    """Texto colado: normaliza quebras. Sem linha em branco => cada linha é um parágrafo; com => junta as linhas internas."""
    t = unicodedata.normalize("NFC", t.replace("\r\n", "\n").replace("\r", "\n")).replace(" ", " ")
    if re.search(r"\n\s*\n", t):
        paras = [re.sub(r"\s*\n\s*", " ", b).strip() for b in re.split(r"\n\s*\n", t)]
    else:
        paras = [l.strip() for l in t.split("\n")]
    return "\n\n".join(re.sub(r"[ \t]+", " ", p) for p in paras if p)


def _titulo_do_texto(t):
    primeira = t.split("\n\n", 1)[0].strip()
    if len(t.split("\n\n")) > 1 and len(primeira) <= 160 and not primeira.endswith((".", ";")):
        return primeira
    return (primeira[:80].rsplit(" ", 1)[0] + "…") if len(primeira) > 80 else primeira


def extrair(url=None, arquivo=None, texto=None):
    """Exatamente uma entrada. -> {tipo, titulo, veiculo, data_publicacao, texto, hash} (+ url, metodo, data_origem).
    `tipo` é a melhor estimativa (reportagem|pdf|decisao|documento); quem chama pode sobrescrever."""
    dados_ent = [x for x in (url, arquivo, texto) if x]
    if len(dados_ent) != 1:
        raise ExtracaoErro("informe exatamente um entre url, arquivo e texto")
    veiculo = url_norm = titulo = data = metodo = origem_data = None
    tipo = "documento"
    if url:
        url = url.strip()
        if not re.match(r"^https?://", url, re.I):
            raise ExtracaoErro("url deve começar com http:// ou https://")
        url_norm = normalizar_url(url)
        veiculo = dominio_de(url_norm)
        dados, ctype, final = _baixar(url)
        if "pdf" in ctype.lower() or dados[:5] == b"%PDF-":
            txt, tmeta, metodo = extrair_pdf_bytes(dados)
            tipo, titulo = "pdf", tmeta
        else:
            r = extrair_html(_decodificar(dados, ctype), url)
            txt, titulo, data, metodo, origem_data = r["texto"], r["titulo"], r["data_publicacao"], r["metodo"], r["data_origem"]
            tipo = "reportagem"
    elif arquivo:
        p = Path(arquivo).expanduser()
        if not p.is_file():
            raise ExtracaoErro(f"arquivo não encontrado: {arquivo}")
        dados = p.read_bytes()
        if p.suffix.lower() == ".pdf" or dados[:5] == b"%PDF-":
            txt, tmeta, metodo = extrair_pdf_bytes(dados)
            tipo, titulo = "pdf", tmeta
        elif p.suffix.lower() in (".html", ".htm") or re.search(rb"<(html|body|article|p)[\s>]", dados[:4096], re.I):
            r = extrair_html(_decodificar(dados))
            txt, titulo, data, metodo, origem_data = r["texto"], r["titulo"], r["data_publicacao"], r["metodo"], r["data_origem"]
            tipo = "reportagem"
        else:
            txt, metodo = _normalizar_texto_livre(_decodificar(dados)), "texto"
    else:
        txt, metodo = _normalizar_texto_livre(texto), "texto"
    txt = (txt or "").strip()
    if len(txt) < 40:
        raise ExtracaoErro("texto extraído vazio ou curto demais" + (" (PDF escaneado? não há OCR)" if tipo == "pdf" else ""))
    if not titulo:
        titulo = _titulo_do_texto(txt)
    if not data:
        data, origem_data = data_no_texto(txt), "texto"
        if not data:
            origem_data = None
    if tipo in ("pdf", "documento") and _parece_decisao(txt):
        tipo = "decisao"
    elif tipo == "reportagem" and veiculo and veiculo.endswith(".jus.br") and _parece_decisao(txt):
        tipo = "decisao"
    return {"tipo": tipo, "titulo": titulo, "veiculo": veiculo, "data_publicacao": data, "texto": txt, "hash": _hash(txt),
            "url": url_norm, "metodo": metodo, "data_origem": origem_data}


# =============================================================================== segmentar
_ABREV = ["sr", "sra", "srs", "dr", "dra", "min", "exmo", "exma", "art", "arts", "no", "nº", "n", "etc", "inc", "cia", "ltda", "dep", "sen", "gov",
          "pres", "des", "prof", "av", "jr", "st", "fl", "fls", "p", "pág", "ex", "obs", "vs", "cap", "col", "tel"]
_RE_ABREV = re.compile(r"\b(" + "|".join(_ABREV) + r")\.", re.I)
_RE_INICIAL = re.compile(r"\b([A-ZÀ-Ý])\.(?=\s*[A-ZÀ-Ý])")
_RE_SIGLA_PONTO = re.compile(r"\b((?:[A-Z]\.){2,})")
_RE_FIM_FRASE = re.compile(r"(?:(?<=[.!?…])|(?<=[.!?…][\"”’')\]]))\s+(?=[\"“‘(\[]?[A-ZÀ-Ý0-9])")
_BOILER_SEMPRE = re.compile(r"\b(cookies?|pol[ií]tica de privacidade|aceitar todos|termos de uso|todos os direitos reservados|copyright|©)\b", re.I)
_BOILER_CURTO = re.compile(
    r"\b(assine|assinantes?|leia tamb[eé]m|leia mais|veja tamb[eé]m|saiba mais|continua ap[oó]s|publicidade|compartilh(e|ar)|siga[- ](o|a|nos|no)|"
    r"receba (nossa|nossas|as|a)|newsletter|inscreva-se|clique aqui|baixe o app|whatsapp|fale conosco|anuncie|foto:|cr[eé]dito:|reprodu[cç][aã]o|"
    r"ver coment[aá]rios|deixe seu coment[aá]rio|mais lidas|ler mais|veja o v[ií]deo|acompanhe)\b", re.I)


def _e_boilerplate(frase):
    f = frase.strip()
    if _BOILER_SEMPRE.search(f):
        return True
    return len(f) < 220 and bool(_BOILER_CURTO.search(f))


def _frases(par):
    s = _RE_ABREV.sub(lambda m: m.group(0).replace(".", "\u0001"), par)
    s = _RE_SIGLA_PONTO.sub(lambda m: m.group(0).replace(".", "\u0001"), s)
    s = _RE_INICIAL.sub(lambda m: m.group(0).replace(".", "\u0001"), s)
    return [x.replace("\u0001", ".").strip() for x in _RE_FIM_FRASE.split(s) if x and x.strip()]


def _quebrar_longa(f, limite):
    if len(f) <= limite:
        return [f]
    saida = []
    while len(f) > limite:
        corte = max(f.rfind("; ", 0, limite), f.rfind(", ", 0, limite), f.rfind(" ", 0, limite))
        if corte < limite // 3:
            corte = limite
        saida.append(f[:corte + 1].strip())
        f = f[corte + 1:].strip()
    if f:
        saida.append(f)
    return saida


def segmentar(texto, limite=LIMITE_TRECHO, min_chars=25):
    """texto -> [{ordem, texto}] com 1 a 3 frases (<= `limite` caracteres) por trecho; nunca atravessa parágrafos; descarta boilerplate."""
    saida, vistos = [], set()
    for par in re.split(r"\n\s*\n|\n", texto):
        par = re.sub(r"\s+", " ", par).strip()
        if not par:
            continue
        frases = []
        for f in _frases(par):
            if _e_boilerplate(f):
                continue
            frases.extend(_quebrar_longa(f, limite))
        grupo = []
        for f in frases + [None]:
            if f is not None and len(grupo) < 3 and len(" ".join(grupo + [f])) <= limite:
                grupo.append(f)
                continue
            if grupo:
                t = " ".join(grupo)
                chave = alias_norm(t)
                if len(t) >= min_chars and chave not in vistos:
                    vistos.add(chave)
                    saida.append({"ordem": len(saida) + 1, "texto": t})
            grupo = [f] if f is not None else []
    return saida


# =============================================================================== anotar
_MULT = {"mil": 1e3, "mi": 1e6, "mn": 1e6, "milhao": 1e6, "milhoes": 1e6, "bi": 1e9, "bn": 1e9, "bilhao": 1e9, "bilhoes": 1e9,
         "tri": 1e12, "trilhao": 1e12, "trilhoes": 1e12}
_MOEDA_SIMB = {"r$": "BRL", "us$": "USD", "u$s": "USD", "usd": "USD", "$": "USD", "€": "EUR", "eur": "EUR"}
_MOEDA_NOME = {"real": "BRL", "reais": "BRL", "dolar": "USD", "dolares": "USD", "euro": "EUR", "euros": "EUR"}
_MULT_RX = r"(?:mil(?:h[aã]o|h[oõ]es)?|mi|mn|bi|bn|bilh[aã]o|bilh[oõ]es|tri|trilh[aã]o|trilh[oõ]es)"
_NUM_RX = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"
_RE_VAL_SIMB = re.compile(r"(?<![\w$])(R\$|US\$|U\$S|USD|EUR|€)\s*(" + _NUM_RX + r")(?:\s*(" + _MULT_RX + r")\b)?", re.I)
_RE_VAL_NOME = re.compile(r"(?<![\w$])(" + _NUM_RX + r")\s*(" + _MULT_RX + r")?\s*(?:de\s+)?(reais|real|d[oó]lares|d[oó]lar|euros?)\b", re.I)
_RE_PCT = re.compile(r"(?<![\w.,])(" + _NUM_RX + r")\s*(%|por\s*cento\b)", re.I)
_RE_ANO = re.compile(r"(?<![\d.,])(?<!\$)(?<!\$ )\b((?:19|20)\d{2})\b(?![\d,.]\d|%|\s*(?:mil|milh|bi|reais|d[oó]lares))")


def _num_br(s):
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        return float(s.replace(".", "").replace(",", "."))
    if "," in s:
        return float(s.replace(".", "").replace(",", "."))
    return float(s)  # '1.5' ou '300'


def _mult(txt):
    return _MULT.get(sem_acento(txt or "").lower(), 1.0) if txt else 1.0


def extrair_valores(texto):
    """-> [{valor, moeda, descricao}] sem sobreposição. 'R$ 1,5 bi' -> 1.5e9 BRL; '300 mil reais'; 'US$ 30 milhões'; '10%' -> pct."""
    achados = []
    for m in _RE_VAL_SIMB.finditer(texto):
        moeda = _MOEDA_SIMB[m.group(1).lower()]
        achados.append((m.start(), m.end(), _num_br(m.group(2)) * _mult(m.group(3)), moeda))
    for m in _RE_VAL_NOME.finditer(texto):
        achados.append((m.start(), m.end(), _num_br(m.group(1)) * _mult(m.group(2)), _MOEDA_NOME[sem_acento(m.group(3)).lower()]))
    for m in _RE_PCT.finditer(texto):
        achados.append((m.start(), m.end(), _num_br(m.group(1)), "pct"))
    achados.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    saida, fim = [], -1
    for ini, f, v, moeda in achados:
        if ini < fim:
            continue
        fim = f
        saida.append({"valor": round(v, 2), "moeda": moeda, "descricao": texto[ini:f].strip()})
    return saida


def extrair_anos(texto):
    return sorted({int(m.group(1)) for m in _RE_ANO.finditer(texto)})


_TIPOS_QUALIF = {"pessoa", "empresa", "banco", "fundo", "escritorio_advocacia"}
_STOP_INICIO = {"o", "a", "os", "as", "um", "uma", "segundo", "para", "por", "com", "sem", "sob", "na", "no", "nas", "nos", "em", "de", "do", "da", "dos",
                "das", "ao", "aos", "apos", "ate", "desde", "entre", "sobre", "contra", "depois", "antes", "durante", "nesta", "neste", "nessa", "nesse",
                "esta", "este", "essa", "esse", "isso", "isto", "quando", "enquanto", "como", "mas", "porem", "contudo", "entretanto", "mesmo", "outro",
                "outra", "ainda", "tambem", "assim", "alem", "foi", "era", "ser", "e", "ou", "se", "que", "seu", "sua", "seus", "suas", "ele", "ela",
                "eles", "elas", "todos", "todas", "cada", "ontem", "hoje", "amanha", "agora", "ha", "mais", "menos", "pelo", "pela", "pelos", "pelas"}
_DIAS_MESES = set(MESES) | {"segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo", "feira", "segunda-feira"}
_SIGLAS_IGNORAR = {"DF", "SP", "RJ", "RS", "MG", "PR", "SC", "BA", "GO", "PA", "PE", "CE", "MA", "MT", "MS", "AM", "ES", "US", "UF", "CPF", "CNPJ",
                   "PDF", "TV", "RG", "OK", "EUA", "NE", "AL", "AC", "AP", "PB", "PI", "RN", "RO", "RR", "SE", "TO", "ID", "II", "III", "IV", "VI"}
_RE_CAP = re.compile(r"[A-ZÀ-Ý][\wÀ-ÿ’'-]*(?:\s+(?:(?:de|da|do|das|dos|e)\s+)?[A-ZÀ-Ý][\wÀ-ÿ’'-]*){1,4}")
_RE_SIGLA = re.compile(r"\b[A-Z][A-Z0-9]{2,6}\b")


def _indice(con):
    regras = CUR.regras_ligacao()
    return CUR.indice_aliases(con, regras), regras


def _entidades_do_texto(con, texto, indice, regras):
    """-> [{id, nome, tipo, mencao}] na ordem de aparição (curadoria.casar_texto: palavra inteira, sobrenomes ambíguos barrados)."""
    saida = []
    for eid, alias in CUR.casar_texto(texto, indice, regras):
        r = con.execute("SELECT nome, tipo FROM entidade WHERE id=?", (eid,)).fetchone()
        if r:
            saida.append({"id": eid, "nome": r["nome"], "tipo": r["tipo"], "mencao": alias})
    return saida


def _candidatos_nao_resolvidos(texto, resolvidas):
    """Sequências capitalizadas (>= 2 palavras) e siglas que não casaram com nenhum alias. Ruído esperado: é lista de SUGESTÃO para o Claude."""
    cobertas = [alias_norm(x["mencao"]) for x in resolvidas] + [alias_norm(x["nome"]) for x in resolvidas]
    cands = []
    for m in _RE_CAP.finditer(texto):
        toks = m.group(0).split()
        while toks and sem_acento(toks[0]).lower() in _STOP_INICIO:
            toks.pop(0)
        if len(toks) < 2 or any(sem_acento(t).lower() in _DIAS_MESES for t in toks):
            continue
        cands.append(" ".join(toks))
    for m in _RE_SIGLA.finditer(texto):
        if m.group(0) not in _SIGLAS_IGNORAR and not m.group(0).isdigit():
            cands.append(m.group(0))
    saida = []
    for c in cands:
        n = alias_norm(c)
        if not n or any(n == x or f" {n} " in f" {x} " or f" {x} " in f" {n} " for x in cobertas if x):
            continue
        saida.append(c)
    return saida


def anotar(trechos, db, veiculo=None, data=None, titulo=None):
    """Acrescenta a cada trecho {ordem, texto}: entidades (resolvidas), anos, valores, relacoes (co-citação) e temas sugeridos.
    `db`: conexão sqlite (leitura). Retorna (trechos_anotados, nao_resolvidas) — a 2ª parte é a lista agregada de menções sem entidade.
    Co-citação: trecho com 2 ou 3 entidades resolvidas, ao menos uma pessoa/empresa/banco; cada par vira relação tipo 'outra',
    rótulo 'Co-citação em <veículo> (<data>)', a ser gravada como natureza 'reportada', confiança 0,3, status 'revisar'."""
    S = _srv()
    indice, regras = _indice(db)
    fonte_nome = veiculo or (titulo[:50] if titulo else "fonte")
    rotulo = f"Co-citação em {fonte_nome} ({data or 's/d'})"
    pares_existentes = {}
    anot, agregado = [], {}
    for t in trechos:
        texto = t["texto"]
        ents = _entidades_do_texto(db, texto, indice, regras)
        o = dict(t)
        o.update(entidades=[e["id"] for e in ents], mencoes=ents, anos_referidos=extrair_anos(texto), valores=extrair_valores(texto), relacoes=[])
        if 2 <= len(ents) <= 3 and any(e["tipo"] in _TIPOS_QUALIF for e in ents):
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    a, b = ents[i], ents[j]
                    if a["tipo"] not in _TIPOS_QUALIF and b["tipo"] not in _TIPOS_QUALIF:
                        continue  # órgão↔órgão (ou partido↔órgão) não vira relação
                    chave = (a["id"], b["id"])
                    if chave not in pares_existentes:
                        pares_existentes[chave] = _relacoes_do_par(db, S, a["id"], b["id"], rotulo)
                    if pares_existentes[chave]:
                        o.setdefault("pares_ja_relacionados", []).append({"de": a["id"], "para": b["id"], "relacoes": pares_existentes[chave]})
                        continue
                    temas = CUR.inferir_temas_relacao(db, a["id"], b["id"], rotulo, texto[:600])
                    o["relacoes"].append({"de": a["id"], "para": b["id"], "tipo": "outra", "rotulo": rotulo, "temas": temas})
        if ents:
            ref = ents[0]["id"]
            o["temas_sugeridos"] = CUR.inferir_temas_relacao(db, ref, ents[1]["id"] if len(ents) > 1 else ref, "", texto[:600])
        else:
            o["temas_sugeridos"] = []
        for c in _candidatos_nao_resolvidos(texto, ents):
            d = agregado.setdefault(c, {"mencao": c, "n": 0, "trechos": []})
            d["n"] += 1
            if t["ordem"] not in d["trechos"]:
                d["trechos"].append(t["ordem"])
        anot.append(o)
    nao_res = []
    for d in sorted(agregado.values(), key=lambda x: (-x["n"], x["trechos"][0]))[:30]:
        d["sugestoes"] = S._sugestoes(db, d["mencao"], 3)
        nao_res.append(d)
    return anot, nao_res


def _relacoes_do_par(db, S, a, b, rotulo):
    """Relações já existentes entre a e b (qualquer direção, exceto descartadas). Com RAG disponível, junta o cosseno do rótulo (relacoes_similares)."""
    rows = db.execute("SELECT id, de, para, tipo, rotulo, status FROM relacao WHERE ((de=? AND para=?) OR (de=? AND para=?)) AND status<>'descartada' ORDER BY id",
                      (a, b, b, a)).fetchall()
    if not rows:
        return []
    cos = {}
    try:
        rs = S.relacoes_similares_core(rotulo, a, b, limite=50, cos_min=0.0)
        cos = {x["id"]: x["cos"] for x in rs.get("similares", [])}
    except Exception:  # RAG indisponível: segue só com a existência
        pass
    return [{"id": r["id"], "tipo": r["tipo"], "rotulo": r["rotulo"], "status": r["status"], **({"cos": cos[r["id"]]} if r["id"] in cos else {})} for r in rows]


# =============================================================================== ingerir (ferramenta MCP)
def _preparar(url, arquivo, texto, titulo, tipo, temas):
    S = _srv()
    if tipo is not None and tipo not in TIPOS_FONTE:
        raise S.Rejeitado(f"tipo '{tipo}' inválido", validos=TIPOS_FONTE)
    try:
        ex = extrair(url, arquivo, texto)
    except ExtracaoErro as e:
        raise S.Rejeitado(str(e)) from e
    tipo = tipo or ex["tipo"]
    titulo = (titulo or ex["titulo"] or "Sem título").strip()
    trechos = segmentar(ex["texto"])
    if not trechos:
        raise S.Rejeitado("nenhum trecho aproveitável depois de remover boilerplate")
    with S.leitura() as con:
        anot, nao_res = anotar(trechos, con, ex["veiculo"], ex["data_publicacao"], titulo)
        if temas:
            S._checar_temas(con, temas, "temas")
    fonte = {"tipo": tipo, "titulo": titulo, "canal": ex["veiculo"], "publicado_em": ex["data_publicacao"], "texto": ex["texto"],
             "temas": list(temas or [])}
    if ex["url"]:
        fonte["url"] = ex["url"]
        if ex["veiculo"] and (ex["veiculo"].endswith(".gov.br") or ex["veiculo"].endswith(".jus.br")) and tipo in ("pdf", "documento"):
            fonte["evidencia_tipo"] = "documento_oficial"
    fonte["id"] = ("src:" + hashlib.sha256(ex["url"].encode("utf-8")).hexdigest()[:12]) if ex["url"] else ("src:" + ex["hash"][:12])
    saida_trechos = []
    for t in anot:
        n = dict(t)
        n.update(localizacao=f"parágrafo {t['ordem']}", texto_original=t["texto"], afirmacao=t["texto"], natureza="reportada", confianca=0.3,
                 potencial_corte=0)
        n.pop("texto", None)
        saida_trechos.append(n)
    return ex, fonte, saida_trechos, nao_res


def _ja_gravada(con, fonte, ex):
    r = con.execute("SELECT id, url, hash_texto, titulo FROM fonte WHERE hash_texto=?", (ex["hash"],)).fetchone()
    por = "hash_texto"
    if not r and fonte.get("url"):
        r = con.execute("SELECT id, url, hash_texto, titulo FROM fonte WHERE url=?", (fonte["url"],)).fetchone()
        por = "url"
    if not r:
        return None
    return {"fonte_id": r["id"], "url": r["url"], "titulo": r["titulo"], "igual_por": por, "texto_identico": r["hash_texto"] == ex["hash"],
            "n_trechos": con.execute("SELECT count(*) FROM trecho WHERE fonte_id=?", (r["id"],)).fetchone()[0]}


def ingerir(url: str | None = None, arquivo: str | None = None, texto: str | None = None, titulo: str | None = None, tipo: str | None = None,
            temas: list[str] | None = None, modo: str = "rascunho") -> dict:
    """Extrai uma fonte (informe EXATAMENTE um entre `url` de reportagem/PDF, `arquivo` local .pdf/.html/.txt, ou `texto` colado), segmenta em trechos
    de 1-3 frases, resolve entidades pelos aliases do banco, extrai anos/valores e propõe co-citações. Sem modelo de linguagem: o servidor NÃO entende
    o que o texto afirma. `titulo`/`tipo` (reportagem|documento|pdf|decisao|depoimento|transcricao|outro) sobrescrevem a detecção; `temas` (ids de listar_temas)
    vão para a fonte. modo='rascunho' (padrão): NÃO grava; devolve {fonte, trechos, cortes_sugeridos:[]} no contrato de inserir_fonte + relacoes_propostas +
    entidades_nao_resolvidas (cada uma com até 3 sugestões). Revise/enriqueça (natureza, afirmacao, relações reais) e mande por inserir_fonte.
    modo='gravar': grava direto (fonte, evidência se há URL, trechos, entidades/anos/valores e co-citações com natureza 'reportada', confiança 0,3, status
    'revisar'). Idempotente por hash do texto e por URL normalizada: repetir devolve idempotente=true sem escrever."""
    S = _srv()
    if modo not in ("rascunho", "gravar"):
        return {"ok": False, "erro": "modo deve ser 'rascunho' ou 'gravar'"}
    try:
        ex, fonte, trechos, nao_res = _preparar(url, arquivo, texto, titulo, tipo, temas)
        with S.leitura() as con:
            ja = _ja_gravada(con, fonte, ex)
    except S.Rejeitado as r:
        return r.payload
    avisos = []
    if not ex["data_publicacao"]:
        avisos.append("data de publicação não encontrada; rótulos das co-citações ficam com 's/d'. Informe fonte.publicado_em ao enviar por inserir_fonte.")
    if ex["data_origem"] == "texto":
        avisos.append("data deduzida do texto (primeira data nas primeiras linhas): confira.")
    if not ex["url"]:
        avisos.append("fonte sem URL: relações novas ficam sem evidência vinculada (o trecho é a única prova).")
    props = {}
    for t in trechos:
        for r in t["relacoes"]:
            p = props.setdefault((r["de"], r["para"]), {**r, "trechos": []})
            p["trechos"].append(t["ordem"])
    resumo = {"fonte_id": fonte["id"], "extracao": {"tipo": ex["tipo"], "metodo": ex["metodo"], "veiculo": ex["veiculo"],
                                                    "data_publicacao": ex["data_publicacao"], "data_origem": ex["data_origem"], "hash": ex["hash"],
                                                    "n_caracteres": len(ex["texto"]), "n_trechos": len(trechos)}}
    if modo == "rascunho":
        return {"ok": True, "modo": "rascunho", "gravado": False, **resumo, "fonte": fonte, "trechos": trechos, "cortes_sugeridos": [],
                "relacoes_propostas": list(props.values()), "entidades_nao_resolvidas": nao_res, "ja_gravada": ja, "avisos": avisos,
                "proximo_passo": "Revise e enriqueça `trechos` (natureza/afirmacao/relações reais; entidades não resolvidas precisam de cadastro) e "
                                 "envie {fonte, trechos} por inserir_fonte, ou repita ingerir com modo='gravar'."}
    if ja and ja["texto_identico"]:
        return {"ok": True, "modo": "gravar", "gravado": False, "idempotente": True, **resumo, "fonte_id": ja["fonte_id"], "ja_gravada": ja,
                "avisos": ["texto idêntico já gravado; nada foi escrito."]}
    if ja and ja["igual_por"] == "url" and ja["n_trechos"] and not _tem_hash(ja["fonte_id"]):
        return {"ok": False, "erro": f"a URL já existe como fonte '{ja['fonte_id']}' sem texto extraído e com {ja['n_trechos']} trecho(s) possivelmente curados; "
                                     "gravar substituiria os trechos. Use modo='rascunho' e inserir_fonte, ou apague a fonte antes.", "ja_gravada": ja}
    if ja and ja["igual_por"] == "url":
        fonte["id"] = ja["fonte_id"]
        avisos.append("a URL já existia com texto diferente: trechos anteriores foram substituídos (conteúdo atualizado).")
    res = S.inserir_fonte_core(fonte, trechos, None)
    res.update(modo="gravar", gravado=bool(res.get("ok")), idempotente=False, avisos_extracao=avisos, entidades_nao_resolvidas=nao_res)
    res.setdefault("extracao", resumo["extracao"])
    return res


def _tem_hash(fonte_id):
    S = _srv()
    with S.leitura() as con:
        r = con.execute("SELECT hash_texto FROM fonte WHERE id=?", (fonte_id,)).fetchone()
    return bool(r and r["hash_texto"])


def registrar(server_mod):
    """Chamada por UMA linha no fim de server.py: embrulha criar_servidor para também registrar `ingerir`."""
    global _S
    _S = server_mod
    if getattr(server_mod.criar_servidor, "_com_ingerir", False):
        return
    original = server_mod.criar_servidor

    def criar_servidor():
        srv = original()
        srv.tool()(ingerir)
        return srv

    criar_servidor._com_ingerir = True
    server_mod.criar_servidor = criar_servidor
