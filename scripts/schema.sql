-- Linha do Tempo: schema SQLite (STRICT exige SQLite >= 3.37).
-- Base: docs-projeto/schema-proposta.md. Desvios em relação à proposta estão marcados com "-- DESVIO:".
-- Este arquivo é a única fonte do DDL: migrar.py e importar.py o executam; data/dump.sql o reproduz no início.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL) STRICT;

-- Vocabulários
CREATE TABLE categoria (
  id TEXT PRIMARY KEY,          -- 'pol','jus','pcc','inss','reag','din','grp','lag','fam','adv','mid','usi','hub'
  nome TEXT NOT NULL,
  ordem INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE TABLE natureza (
  id TEXT PRIMARY KEY,          -- 'documentada','investigacao','reportada','alegacao','opiniao','nao_classificada'
  nome TEXT NOT NULL,
  peso INTEGER NOT NULL         -- 5..0, força probatória
) STRICT;
INSERT INTO natureza VALUES
 ('documentada','documentada',5),('investigacao','sob investigação',4),
 ('reportada','revelada pela imprensa',3),('alegacao','alegação',2),
 ('opiniao','opinião',1),('nao_classificada','não classificada',0);

CREATE TABLE natureza_mapa (
  sistema TEXT NOT NULL,         -- 'teia' | 'classificador'
  codigo_externo TEXT NOT NULL,  -- doc/inv/rep/ale/nc | fato_documentado/alegacao/opiniao
  natureza_id TEXT NOT NULL REFERENCES natureza(id),
  PRIMARY KEY (sistema, codigo_externo)
) STRICT;
INSERT INTO natureza_mapa VALUES
 ('teia','doc','documentada'),('teia','inv','investigacao'),('teia','rep','reportada'),
 ('teia','ale','alegacao'),('teia','nc','nao_classificada'),
 ('classificador','fato_documentado','documentada'),
 ('classificador','alegacao','alegacao'),('classificador','opiniao','opiniao');

-- Entidade (nós)
CREATE TABLE entidade (
  id TEXT PRIMARY KEY CHECK (id GLOB '[a-z0-9]*' AND id NOT GLOB '*[^a-z0-9-]*'), -- slug: 'daniel-vorcaro'
  nome TEXT NOT NULL UNIQUE,                 -- N.n
  tipo TEXT NOT NULL CHECK (tipo IN ('pessoa','empresa','banco','fundo','fundo_previdencia','orgao_publico',
    'partido','associacao','organizacao_criminosa','operacao_policial','igreja','escritorio_advocacia',
    'veiculo_midia','pais','outro')),
  categoria_id TEXT REFERENCES categoria(id), -- N.c (NULL = fora da teia)
  grupo TEXT,                                -- N.sg e pseudo-partidos de N.p
  partido TEXT,                              -- sigla real
  campo TEXT CHECK (campo IN ('esquerda','centro','direita') OR campo IS NULL),
  cargo TEXT,                                -- N.g
  descricao TEXT,                            -- N.d
  dossie TEXT,                               -- markdown longo, opcional
  uf TEXT CHECK (length(uf)=2 OR uf IS NULL),
  nascimento TEXT,
  origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('teia','linha_do_tempo','classificador','manual')),
  origem_ref TEXT,                           -- 'N[12]'
  ind_legado INTEGER UNIQUE,                 -- DESVIO: índice posicional em teia.N (NULL fora da teia); usado só para exportar a ordem antiga
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  atualizado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE INDEX ix_entidade_tipo ON entidade(tipo);
CREATE INDEX ix_entidade_cat ON entidade(categoria_id);

CREATE TABLE entidade_alias (
  alias TEXT NOT NULL,
  alias_norm TEXT NOT NULL,                  -- NFKD sem acento, minúsculo
  entidade_id TEXT NOT NULL REFERENCES entidade(id) ON DELETE CASCADE,
  tipo_alias TEXT NOT NULL DEFAULT 'alias' CHECK (tipo_alias IN ('alias','sigla','apelido','nome_antigo','nome_completo','grafia')),
  origem TEXT NOT NULL DEFAULT 'manual',
  PRIMARY KEY (alias_norm, entidade_id)
) STRICT;
CREATE INDEX ix_alias_norm ON entidade_alias(alias_norm);

-- Relação (arestas com tempo)
CREATE TABLE relacao (
  id INTEGER PRIMARY KEY,
  de TEXT NOT NULL REFERENCES entidade(id),      -- r.a
  para TEXT NOT NULL REFERENCES entidade(id),    -- r.b
  tipo TEXT NOT NULL CHECK (tipo IN ('financeira','societaria','contratual','juridica','investigacao','politica',
    'pessoal','familiar','profissional','institucional','religiosa','midia','outra')),
  subtipo TEXT,
  rotulo TEXT NOT NULL,                          -- r.rot
  descricao TEXT,                                -- r.desc
  natureza_id TEXT NOT NULL REFERENCES natureza(id),
  confianca REAL CHECK (confianca IS NULL OR (confianca BETWEEN 0 AND 1)), -- só classificador
  periodo_inicio TEXT CHECK (periodo_inicio IS NULL OR periodo_inicio GLOB '[0-9][0-9][0-9][0-9]*'),
  periodo_fim TEXT CHECK (periodo_fim IS NULL OR periodo_fim GLOB '[0-9][0-9][0-9][0-9]*'),
  periodo_aprox INTEGER NOT NULL DEFAULT 0 CHECK (periodo_aprox IN (0,1)),
  periodo_texto TEXT,
  ano_inicio INTEGER GENERATED ALWAYS AS (CAST(substr(periodo_inicio,1,4) AS INTEGER)) STORED,
  ano_fim INTEGER GENERATED ALWAYS AS (CAST(substr(periodo_fim,1,4) AS INTEGER)) STORED,
  valor_brl REAL,                                -- r.val
  valor_texto TEXT,                              -- 'US$ 30 milhões'
  resposta TEXT,                                 -- r.resp
  direcional INTEGER NOT NULL DEFAULT 1 CHECK (direcional IN (0,1)),
  origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('teia','origens','classificador','manual')),
  origem_ref TEXT,                               -- 'E[17].r[0]' | 'trecho:123'
  status TEXT NOT NULL DEFAULT 'publicada' CHECK (status IN ('rascunho','revisar','publicada','descartada')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  atualizado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (de <> para)
) STRICT;
CREATE INDEX ix_relacao_de ON relacao(de);
CREATE INDEX ix_relacao_para ON relacao(para);
CREATE INDEX ix_relacao_ano ON relacao(ano_inicio, ano_fim);
CREATE UNIQUE INDEX ux_relacao_dedup ON relacao(de, para, tipo, rotulo, IFNULL(periodo_inicio,''));

-- Evento (fato pontual datado)
CREATE TABLE evento (
  id TEXT PRIMARY KEY,                           -- slug ou id antigo (fam11)
  titulo TEXT NOT NULL, descricao TEXT,
  data TEXT CHECK (data GLOB '[0-9][0-9][0-9][0-9]*'),
  data_aprox INTEGER NOT NULL DEFAULT 0 CHECK (data_aprox IN (0,1)),
  data_texto TEXT,                               -- 'década de 1970'
  ano INTEGER GENERATED ALWAYS AS (CAST(substr(data,1,4) AS INTEGER)) STORED,
  natureza_id TEXT REFERENCES natureza(id),      -- NULL nos 92 sem st
  peso INTEGER CHECK (peso BETWEEN 1 AND 5),     -- EV.p
  canal TEXT NOT NULL DEFAULT 'teia' CHECK (canal IN ('teia','banco','familia','ida','volta','precatorios','violencia','brasil','pares','brb')), -- DESVIO: + 'brb' (dossiê, 30 eventos)
  contexto TEXT,                                 -- DESVIO: livre (dossiê: lado/crítico). A proposta mapeava origens EV.r aqui, mas r é a resposta do citado
  resposta TEXT,                                 -- origens EV.r (resposta do citado). A proposta dizia EV.v, que é o valor
  valor_brl REAL,                                -- DESVIO: origens EV.v (BRL inteiro); não havia coluna na proposta
  origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('teia','origens','prec','violencia','linha_do_tempo','dossie','classificador','manual')), -- DESVIO: + 'dossie'
  origem_ref TEXT,
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  atualizado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE INDEX ix_evento_ano ON evento(ano);
CREATE INDEX ix_evento_canal ON evento(canal, ano);

CREATE TABLE evento_entidade (
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  entidade_id TEXT NOT NULL REFERENCES entidade(id),
  papel TEXT,
  ordem INTEGER NOT NULL DEFAULT 0,              -- DESVIO: preserva a ordem de EV.n
  PRIMARY KEY (evento_id, entidade_id)
) STRICT;
CREATE TABLE evento_relacao (
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  papel TEXT CHECK (papel IN ('inicia','encerra','altera','menciona') OR papel IS NULL),
  PRIMARY KEY (evento_id, relacao_id)
) STRICT;

-- Evidência (uma linha por URL)
CREATE TABLE evidencia (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  veiculo TEXT NOT NULL,                         -- domínio ou nome
  titulo TEXT, data TEXT, autor TEXT, resumo TEXT, arquivo TEXT, acessado_em TEXT,
  tipo TEXT NOT NULL DEFAULT 'reportagem' CHECK (tipo IN ('reportagem','documento_oficial','decisao_judicial',
    'processo','comunicado','relatorio','dado_oficial','wiki','video','outro')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE TABLE relacao_evidencia (
  relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  papel TEXT NOT NULL DEFAULT 'sustenta' CHECK (papel IN ('sustenta','contesta','contexto')),
  trecho_citado TEXT,
  ordem INTEGER NOT NULL DEFAULT 0,              -- DESVIO: preserva a ordem de r.f
  PRIMARY KEY (relacao_id, evidencia_id)
) STRICT;
CREATE TABLE evento_evidencia (
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  papel TEXT NOT NULL DEFAULT 'sustenta' CHECK (papel IN ('sustenta','contesta','contexto')),
  ordem INTEGER NOT NULL DEFAULT 0,              -- DESVIO: preserva a ordem de EV.f
  PRIMARY KEY (evento_id, evidencia_id)
) STRICT;

-- Vídeo / trecho / corte (saída do classificador)
CREATE TABLE video (
  id TEXT PRIMARY KEY,                           -- 'yt:<id>'
  plataforma TEXT NOT NULL CHECK (plataforma IN ('youtube','instagram','tiktok','x','podcast','outro')),
  url TEXT NOT NULL UNIQUE, titulo TEXT NOT NULL, canal TEXT,
  canal_entidade_id TEXT REFERENCES entidade(id),
  publicado_em TEXT, duracao_s INTEGER, transcricao TEXT, arquivo_transcricao TEXT, resumo TEXT,
  classificado_em TEXT, classificador_versao TEXT,
  status TEXT NOT NULL DEFAULT 'classificado' CHECK (status IN ('pendente','classificado','revisado','descartado')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE TABLE trecho (
  id INTEGER PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES video(id) ON DELETE CASCADE,
  ordem INTEGER NOT NULL, inicio_s REAL NOT NULL, fim_s REAL NOT NULL CHECK (fim_s >= inicio_s),
  texto_original TEXT, afirmacao TEXT NOT NULL,
  natureza_id TEXT NOT NULL REFERENCES natureza(id),
  confianca REAL NOT NULL CHECK (confianca BETWEEN 0 AND 1),
  potencial_corte INTEGER NOT NULL DEFAULT 0 CHECK (potencial_corte BETWEEN 0 AND 5),
  UNIQUE (video_id, ordem)
) STRICT;
CREATE TABLE trecho_entidade (
  trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE,
  entidade_id TEXT NOT NULL REFERENCES entidade(id),
  mencao TEXT, PRIMARY KEY (trecho_id, entidade_id)
) STRICT;
CREATE TABLE trecho_ano (trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE,
  ano INTEGER NOT NULL, PRIMARY KEY (trecho_id, ano)) STRICT;
CREATE TABLE trecho_valor (id INTEGER PRIMARY KEY, trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE,
  valor REAL NOT NULL, moeda TEXT NOT NULL DEFAULT 'BRL' CHECK (moeda IN ('BRL','USD','EUR','pct','outro')), descricao TEXT) STRICT;
CREATE TABLE trecho_relacao (
  trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE,
  relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  papel TEXT NOT NULL DEFAULT 'afirma' CHECK (papel IN ('afirma','contesta','menciona')),
  PRIMARY KEY (trecho_id, relacao_id)
) STRICT;
CREATE TABLE corte (
  id INTEGER PRIMARY KEY, video_id TEXT NOT NULL REFERENCES video(id) ON DELETE CASCADE,
  titulo TEXT NOT NULL, inicio_s REAL NOT NULL, fim_s REAL NOT NULL CHECK (fim_s > inicio_s),
  justificativa TEXT, tema TEXT, url_publicado TEXT,
  status TEXT NOT NULL DEFAULT 'sugerido' CHECK (status IN ('sugerido','aprovado','publicado','descartado')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE TABLE corte_trecho (corte_id INTEGER NOT NULL REFERENCES corte(id) ON DELETE CASCADE,
  trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE, PRIMARY KEY (corte_id, trecho_id)) STRICT;
CREATE TABLE relacao_corte (relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  corte_id INTEGER NOT NULL REFERENCES corte(id) ON DELETE CASCADE, PRIMARY KEY (relacao_id, corte_id)) STRICT;

-- Notas editoriais (SINT, SEM, LAC, NARR, tese/placar do dossiê)
CREATE TABLE nota (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('sintese','nao_sustentado','lacuna','narrativa','tese','placar','aviso')),
  pagina TEXT NOT NULL CHECK (pagina IN ('teia','origens','dossie','violencia','brasil','pares')),
  chave TEXT, titulo TEXT, texto TEXT NOT NULL, ordem INTEGER NOT NULL DEFAULT 0,
  natureza_id TEXT REFERENCES natureza(id)
) STRICT;
CREATE TABLE nota_entidade (nota_id INTEGER NOT NULL REFERENCES nota(id) ON DELETE CASCADE,
  entidade_id TEXT NOT NULL REFERENCES entidade(id), ordem INTEGER NOT NULL DEFAULT 0, -- DESVIO: preserva a ordem de SEM.n
  PRIMARY KEY (nota_id, entidade_id)) STRICT;

-- Séries numéricas (macro, setores, intl, pares, violência, NUM do Master)
CREATE TABLE indicador (
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, unidade TEXT NOT NULL,
  dominio TEXT NOT NULL CHECK (dominio IN ('macro','setor','politica','intl','comercio','violencia','pares','master')),
  descricao TEXT, fonte_padrao TEXT
) STRICT;
CREATE TABLE serie (
  id INTEGER PRIMARY KEY,
  indicador_id TEXT NOT NULL REFERENCES indicador(id),
  ano INTEGER NOT NULL CHECK (ano BETWEEN 1800 AND 2100),
  dimensao TEXT NOT NULL DEFAULT '',             -- '' | 'pais=CHN' | 'setor=x' | 'sexo=f' | 'faixa=15-29' | 'raca=negra' | 'fonte=atlas'
  valor REAL, valor_texto TEXT,
  qualidade TEXT NOT NULL DEFAULT 'oficial' CHECK (qualidade IN ('oficial','proxy','preliminar','derivado','imprensa')),
  evidencia_id INTEGER REFERENCES evidencia(id), obs TEXT,
  UNIQUE (indicador_id, ano, dimensao)
) STRICT;
CREATE INDEX ix_serie_ano ON serie(ano);

CREATE TABLE ranking_empresa (
  ano INTEGER NOT NULL, entidade_id TEXT NOT NULL REFERENCES entidade(id),
  posicao INTEGER, setor TEXT, setor_k TEXT, lucro_brl_bi REAL, receita_brl_bi REAL, pct_total REAL,
  controle TEXT CHECK (controle IN ('estatal','privado','misto','estrangeiro') OR controle IS NULL),
  holding INTEGER NOT NULL DEFAULT 0, derivado INTEGER NOT NULL DEFAULT 0,
  cobertura TEXT CHECK (cobertura IN ('completa','parcial','fraca') OR cobertura IS NULL),
  obs TEXT, evidencia_id INTEGER REFERENCES evidencia(id),
  PRIMARY KEY (ano, entidade_id)
) STRICT;

CREATE TABLE mandato (
  id INTEGER PRIMARY KEY, entidade_id TEXT NOT NULL REFERENCES entidade(id),
  cargo TEXT NOT NULL CHECK (cargo IN ('presidente','vice_presidente','presidente_camara','presidente_senado','ministro','senador','deputado','governador','outro')),
  orgao_id TEXT REFERENCES entidade(id), partido TEXT, uf TEXT,
  inicio TEXT NOT NULL, fim TEXT, evidencia_id INTEGER REFERENCES evidencia(id),
  motivo TEXT, votos INTEGER                     -- DESVIO: parlamentares em destaque (timeline pol.parl): motivo do destaque e votos
) STRICT;
CREATE TABLE bancada (
  legislatura INTEGER NOT NULL, ano INTEGER NOT NULL,
  casa TEXT NOT NULL CHECK (casa IN ('camara','senado')),
  partido_id TEXT NOT NULL REFERENCES entidade(id), nome_epoca TEXT, cadeiras INTEGER NOT NULL,
  campo TEXT CHECK (campo IN ('esquerda','centro','direita') OR campo IS NULL),
  PRIMARY KEY (ano, casa, partido_id)
) STRICT;

-- DESVIO: orientação original de cada par de teia.E (E[i].a/E[i].b), só para round-trip fiel (a cor da aresta na página depende dela).
-- A direção semântica continua em relacao.de/para.
CREATE TABLE aresta_legado (
  e_idx INTEGER PRIMARY KEY,
  a TEXT NOT NULL REFERENCES entidade(id),
  b TEXT NOT NULL REFERENCES entidade(id)
) STRICT;

-- Busca textual (FTS5 antes do sqlite-vec)
CREATE VIRTUAL TABLE busca_fts USING fts5(origem_tabela, origem_id, texto, tokenize='unicode61 remove_diacritics 2');
