"""Slug canônico, SLUG_FIXO e normalização de alias (regras da seção 2 do schema-proposta)."""
import re
import unicodedata


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slugify(s, limite=60):
    t = sem_acento(s).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(t) > limite:
        t = t[:limite].rstrip("-")
    return t


def alias_norm(s):
    """NFKD, sem acento, minúsculo, pontuação vira espaço (permite casar palavra inteira)."""
    return re.sub(r"[^a-z0-9]+", " ", sem_acento(s).lower()).strip()


# alias_norm(nome ou sigla) -> slug fixo. Partidos e órgãos com id curto e estável.
SLUG_FIXO = {
    "pt": "pt", "pl": "pl", "pp": "pp", "mdb": "mdb", "uniao brasil": "uniao-brasil",
    "supremo tribunal federal": "stf", "stf": "stf",
    "banco central do brasil": "bcb", "bcb": "bcb", "banco central": "bcb",
    "comissao de valores mobiliarios": "cvm", "cvm": "cvm",
    "tribunal de contas da uniao": "tcu", "tcu": "tcu",
    "procuradoria geral da republica": "pgr", "pgr": "pgr",
    "ministerio publico federal": "mpf", "mpf": "mpf",
    "policia federal": "pf", "pf": "pf",
    "inss": "inss",
    "controladoria geral da uniao": "cgu", "cgu": "cgu",
    "coaf": "coaf",
}
# Aliases acrescentados a entidades de slug fixo: slug -> [(alias, tipo_alias)]
ALIASES_FIXOS = {
    "stf": [("STF", "sigla")], "bcb": [("BCB", "sigla"), ("Banco Central", "alias")],
    "tcu": [("TCU", "sigla")], "mpf": [("MPF", "sigla")], "pf": [("PF", "sigla")],
    "pgr": [("PGR", "sigla")], "cgu": [("CGU", "sigla")], "coaf": [("COAF", "sigla")],
    "inss": [("INSS", "sigla")], "cvm": [("CVM", "sigla")],
}
# Formas completas confirmadas no inventário (seção E.2)
ALIASES_EXTRA = {
    "daniel-vorcaro": [("Daniel Bueno Vorcaro", "nome_completo")],
    "henrique-vorcaro": [("Henrique Moura Vorcaro", "nome_completo")],
}
# Parênteses que descrevem em vez de nomear: não viram alias
GENERICOS = {"fundo", "fundo multimercado", "administradora", "primo"}
# Base ambígua/curta: mantém o nome inteiro (incluindo o parêntese) no slug
NOME_COMPLETO = {
    "Partido Novo (diretório de Minas Gerais)",
    "Luis Roberto (irmão de Paulo Sérgio Neves de Souza)",
}
_SIGLA = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)?$")
_PAREN = re.compile(r"\s*(.+?)\s*\((.+)\)\s*$")


def analisar_nome(nome):
    """-> (slug_base, aliases[(texto, tipo)]). Regras 1-3 do schema-proposta; colisões são tratadas por quem chama."""
    m = _PAREN.fullmatch(nome)
    if not m or nome in NOME_COMPLETO:
        slug = SLUG_FIXO.get(alias_norm(nome)) or slugify(nome)
        return slug, list(ALIASES_FIXOS.get(slug, []))
    base, par = m.group(1).strip(), m.group(2).strip()
    eh_sigla = len(base) <= 6 and bool(_SIGLA.match(base))
    slug = SLUG_FIXO.get(alias_norm(base)) or SLUG_FIXO.get(alias_norm(nome)) or slugify(base)
    aliases = [(base, "sigla" if eh_sigla else "alias")]
    if eh_sigla:
        aliases.append((par, "nome_completo"))
    elif alias_norm(par) in GENERICOS:
        pass
    elif par.lower().startswith("ex-"):
        aliases.append((par[3:].strip(), "nome_antigo"))
    else:
        aliases.append((par.strip("'\" "), "apelido"))
    aliases += ALIASES_FIXOS.get(slug, [])
    return slug, aliases


def slug_para_nome(nome):
    return analisar_nome(nome)[0]


if __name__ == "__main__":
    for n in ["CVM (Comissão de Valores Mobiliários)", "Banco Central do Brasil", "Luiz Phillipi Mourão ('Sicário')",
              "Hans 95 (fundo multimercado)", "Partido Novo (diretório de Minas Gerais)", "Amprev (Amapá Previdência)"]:
        print(n, "->", analisar_nome(n))
