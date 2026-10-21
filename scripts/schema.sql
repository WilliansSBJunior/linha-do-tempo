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
  origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('teia','origens','classificador','manual','linha_do_tempo')), -- DESVIO: + 'linha_do_tempo' (mandato/filiação derivados da timeline)
  origem_ref TEXT,                               -- 'E[17].r[0]' | 'trecho:123' | 'mandato:57' | 'filiacao:<pessoa>:<partido>:<início>'
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

-- Tema: dimensão N:N (um registro pode estar em vários temas). Seed e regras de atribuição: data/curadoria/temas.json.
-- A pertinência de ENTIDADE a tema é derivada (view v_entidade_tema, fim do arquivo); `categoria_id` da entidade continua sendo a categoria da teia.
CREATE TABLE tema (
  id TEXT PRIMARY KEY CHECK (id GLOB '[a-z0-9]*' AND id NOT GLOB '*[^a-z0-9-]*'),  -- slug: 'caso-master'
  nome TEXT NOT NULL UNIQUE,
  descricao TEXT,
  cor TEXT CHECK (cor IS NULL OR cor GLOB '#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]*'),
  ordem INTEGER NOT NULL DEFAULT 0,
  principal INTEGER NOT NULL DEFAULT 0 CHECK (principal IN (0,1))  -- DESVIO: 1 = tema de domínio (caso-master, brasil-ano-a-ano...); o MCP o usa para inferir o tema de relação nova
) STRICT;
CREATE TABLE relacao_tema (
  relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  tema_id TEXT NOT NULL REFERENCES tema(id),
  origem TEXT NOT NULL DEFAULT 'regra' CHECK (origem IN ('regra','excecao','manual','mcp')),
  regra TEXT,                                    -- identificador da regra de temas.json que atribuiu
  PRIMARY KEY (relacao_id, tema_id)
) STRICT;
CREATE INDEX ix_relacao_tema ON relacao_tema(tema_id);
CREATE TABLE evento_tema (
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  tema_id TEXT NOT NULL REFERENCES tema(id),
  origem TEXT NOT NULL DEFAULT 'regra' CHECK (origem IN ('regra','excecao','manual','mcp')),
  regra TEXT,
  PRIMARY KEY (evento_id, tema_id)
) STRICT;
CREATE INDEX ix_evento_tema ON evento_tema(tema_id);

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
  nota TEXT,                                     -- DESVIO (aditivo): ressalva do pesquisador sobre o que a fonte não confirma (curadoria/evidencias-adicionais.json)
  qualidade TEXT CHECK (qualidade IS NULL OR qualidade IN ('boa','fraca')), -- DESVIO (aditivo): NULL = não avaliada; 'fraca' = candidata a substituição
  PRIMARY KEY (relacao_id, evidencia_id)
) STRICT;
CREATE TABLE evento_evidencia (
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  papel TEXT NOT NULL DEFAULT 'sustenta' CHECK (papel IN ('sustenta','contesta','contexto')),
  ordem INTEGER NOT NULL DEFAULT 0,              -- DESVIO: preserva a ordem de EV.f
  rotulo TEXT,                                   -- DESVIO: rótulo da fonte como no original ([rótulo, url]); evidencia.veiculo guarda só o do primeiro uso da URL
  trecho_citado TEXT,                            -- DESVIO (aditivo): trecho da fonte que sustenta o evento (como relacao_evidencia.trecho_citado)
  nota TEXT,                                     -- DESVIO (aditivo): ressalva do pesquisador sobre o que a fonte não confirma (curadoria/evidencias-adicionais.json)
  qualidade TEXT CHECK (qualidade IS NULL OR qualidade IN ('boa','fraca')), -- DESVIO (aditivo): NULL = não avaliada; 'fraca' = candidata a substituição
  PRIMARY KEY (evento_id, evidencia_id)
) STRICT;

-- Curadoria (data/curadoria/eventos-fusoes.json): ids fundidos continuam resolvendo para o evento mantido.
-- original_json guarda o evento como era antes da fusão (colunas, fontes com rótulo, entidades) para exportar o dossiê/PREC fielmente.
CREATE TABLE evento_alias (
  alias TEXT PRIMARY KEY,
  evento_id TEXT NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  motivo TEXT,
  canal_original TEXT NOT NULL,
  origem_ref_original TEXT,
  original_json TEXT NOT NULL
) STRICT;
CREATE INDEX ix_evento_alias_evento ON evento_alias(evento_id);

-- Fonte genérica (vídeo, reportagem, documento, PDF, depoimento, decisão, transcrição...) / trecho / corte (saída do classificador)
-- DESVIO: `video` virou `fonte` (tipo + plataforma opcional + texto extraído); `video` agora é uma VIEW de compatibilidade (fim deste arquivo).
CREATE TABLE fonte (
  id TEXT PRIMARY KEY CHECK (id <> '' AND id NOT GLOB '*[ ]*'),  -- vídeo: 'yt:<id>'; demais: 'src:<hash12>' ou slug livre
  tipo TEXT NOT NULL CHECK (tipo IN ('video','reportagem','documento','pdf','depoimento','decisao','transcricao','outro')),
  plataforma TEXT CHECK (plataforma IS NULL OR plataforma IN ('youtube','instagram','tiktok','x','podcast','outro')), -- obrigatória só para tipo='video'
  url TEXT UNIQUE,                               -- opcional (depoimento oral, documento físico); URL normalizada em evidencia.url
  titulo TEXT NOT NULL, canal TEXT,              -- canal: canal do vídeo / veículo / órgão emissor
  canal_entidade_id TEXT REFERENCES entidade(id),
  publicado_em TEXT, duracao_s INTEGER,
  texto TEXT,                                    -- conteúdo extraído (vídeo: transcrição; reportagem/PDF: texto)
  hash_texto TEXT,                               -- sha256 do texto (strip), preenchido junto com `texto`
  arquivo_texto TEXT, resumo TEXT,
  evidencia_id INTEGER REFERENCES evidencia(id), -- toda fonte com URL gera/aponta uma evidencia (mesma URL normalizada)
  classificado_em TEXT, classificador_versao TEXT,
  status TEXT NOT NULL DEFAULT 'classificado' CHECK (status IN ('pendente','classificado','revisado','descartado')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (tipo <> 'video' OR (plataforma IS NOT NULL AND url IS NOT NULL)),
  CHECK (url IS NULL OR evidencia_id IS NOT NULL),
  CHECK ((texto IS NULL) = (hash_texto IS NULL))
) STRICT;
CREATE INDEX ix_fonte_tipo ON fonte(tipo);
CREATE TABLE trecho (
  id INTEGER PRIMARY KEY,
  fonte_id TEXT NOT NULL REFERENCES fonte(id) ON DELETE CASCADE,  -- DESVIO: era video_id
  ordem INTEGER NOT NULL,
  inicio_s REAL, fim_s REAL,                     -- obrigatórios só quando a fonte é tipo='video' (trigger); NULL nas demais
  localizacao TEXT,                              -- fontes sem tempo: página, parágrafo, seção
  texto_original TEXT, afirmacao TEXT NOT NULL,
  natureza_id TEXT NOT NULL REFERENCES natureza(id),
  confianca REAL NOT NULL CHECK (confianca BETWEEN 0 AND 1),
  potencial_corte INTEGER NOT NULL DEFAULT 0 CHECK (potencial_corte BETWEEN 0 AND 5),
  UNIQUE (fonte_id, ordem),
  CHECK ((inicio_s IS NULL) = (fim_s IS NULL)),
  CHECK (fim_s IS NULL OR fim_s >= inicio_s)
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
  id INTEGER PRIMARY KEY, video_id TEXT NOT NULL REFERENCES fonte(id) ON DELETE CASCADE, -- DESVIO: referencia fonte; só tipo='video' (triggers abaixo)
  titulo TEXT NOT NULL, inicio_s REAL NOT NULL, fim_s REAL NOT NULL CHECK (fim_s > inicio_s),
  justificativa TEXT, tema TEXT, url_publicado TEXT,
  status TEXT NOT NULL DEFAULT 'sugerido' CHECK (status IN ('sugerido','aprovado','publicado','descartado')),
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
) STRICT;
CREATE TABLE corte_trecho (corte_id INTEGER NOT NULL REFERENCES corte(id) ON DELETE CASCADE,
  trecho_id INTEGER NOT NULL REFERENCES trecho(id) ON DELETE CASCADE, PRIMARY KEY (corte_id, trecho_id)) STRICT;
CREATE TABLE relacao_corte (relacao_id INTEGER NOT NULL REFERENCES relacao(id) ON DELETE CASCADE,
  corte_id INTEGER NOT NULL REFERENCES corte(id) ON DELETE CASCADE, PRIMARY KEY (relacao_id, corte_id)) STRICT;

-- Corte só faz sentido para fonte tipo='video'; trecho de vídeo exige tempo.
CREATE TRIGGER trg_corte_so_video_ins BEFORE INSERT ON corte
WHEN (SELECT tipo FROM fonte WHERE id = NEW.video_id) IS NOT 'video'
BEGIN SELECT RAISE(ABORT, 'corte só faz sentido para fonte do tipo video'); END;
CREATE TRIGGER trg_corte_so_video_upd BEFORE UPDATE OF video_id ON corte
WHEN (SELECT tipo FROM fonte WHERE id = NEW.video_id) IS NOT 'video'
BEGIN SELECT RAISE(ABORT, 'corte só faz sentido para fonte do tipo video'); END;
CREATE TRIGGER trg_fonte_tipo_com_corte BEFORE UPDATE OF tipo ON fonte
WHEN OLD.tipo = 'video' AND NEW.tipo <> 'video' AND EXISTS (SELECT 1 FROM corte WHERE video_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'fonte com cortes tem de continuar tipo video'); END;
CREATE TRIGGER trg_trecho_video_exige_tempo_ins BEFORE INSERT ON trecho
WHEN NEW.inicio_s IS NULL AND (SELECT tipo FROM fonte WHERE id = NEW.fonte_id) = 'video'
BEGIN SELECT RAISE(ABORT, 'trecho de vídeo exige inicio_s e fim_s'); END;
CREATE TRIGGER trg_trecho_video_exige_tempo_upd BEFORE UPDATE OF inicio_s, fim_s, fonte_id ON trecho
WHEN NEW.inicio_s IS NULL AND (SELECT tipo FROM fonte WHERE id = NEW.fonte_id) = 'video'
BEGIN SELECT RAISE(ABORT, 'trecho de vídeo exige inicio_s e fim_s'); END;

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
-- DESVIO (aditivo, rodada 6): fontes de uma linha do ranking com trecho e nota (data/curadoria/ranking-empresa-correcoes.json,
-- curadoria.aplicar_ranking_empresa_correcoes). `ranking_empresa.evidencia_id` continua sendo a fonte principal (a que a página mostra);
-- aqui ficam também as que confirmam o valor (`sustenta`) e as de outra base contábil/corroboração (`contexto`). NULL nas linhas sem curadoria.
CREATE TABLE ranking_evidencia (
  ano INTEGER NOT NULL, entidade_id TEXT NOT NULL,
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  papel TEXT NOT NULL CHECK (papel IN ('sustenta','contexto')),
  ordem INTEGER NOT NULL DEFAULT 0,
  trecho_citado TEXT,                            -- trecho da fonte (NULL na fonte principal anterior, registrada como `anterior`)
  nota TEXT,                                     -- ressalva do pesquisador / base contábil
  PRIMARY KEY (ano, entidade_id, evidencia_id),
  FOREIGN KEY (ano, entidade_id) REFERENCES ranking_empresa(ano, entidade_id) ON UPDATE CASCADE ON DELETE CASCADE
) STRICT;

CREATE TABLE mandato (
  id INTEGER PRIMARY KEY, entidade_id TEXT NOT NULL REFERENCES entidade(id),
  cargo TEXT NOT NULL CHECK (cargo IN ('presidente','vice_presidente','presidente_camara','presidente_senado','ministro','senador','deputado','governador','outro')),
  orgao_id TEXT REFERENCES entidade(id), partido TEXT, uf TEXT,
  inicio TEXT NOT NULL, fim TEXT, evidencia_id INTEGER REFERENCES evidencia(id),
  motivo TEXT, votos INTEGER,                    -- DESVIO: parlamentares em destaque (timeline pol.parl): motivo do destaque e votos
  periodo_texto TEXT                             -- DESVIO: texto de `periodo` de dados-brutos-31-anos (presidentes da Câmara/Senado), via curadoria
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

-- Dossiê "mercado ou máquina" e fóruns de pares, antes em nota.texto como JSON.
-- Cada tabela guarda o texto original (ator_texto, nome_texto...) além do vínculo opcional com entidade, para exportar data/dossie.json igual ao embutido.
CREATE TABLE dossie_par (
  id INTEGER PRIMARY KEY,
  ordem INTEGER NOT NULL,                        -- posição em mercado.pares
  sub INTEGER NOT NULL DEFAULT 0,                -- 2+ linhas por par quando o ator é mais de uma entidade (ex.: 'Antônio Rueda e ACM Neto')
  ator_texto TEXT NOT NULL,                      -- texto original de `ator`
  ator_entidade_id TEXT REFERENCES entidade(id), -- NULL quando não há entidade (ex.: 'Dois ex-chefes da supervisão do BC')
  campo TEXT, partido TEXT, alavanca TEXT, recebeu TEXT, ato TEXT,
  liga TEXT NOT NULL CHECK (liga IN ('sim','apura','nao')),
  liga_x TEXT,
  natureza_id TEXT REFERENCES natureza(id),
  estagio TEXT, resposta TEXT,
  UNIQUE (ordem, sub)
) STRICT;
CREATE TABLE dossie_par_evidencia (
  par_id INTEGER NOT NULL REFERENCES dossie_par(id) ON DELETE CASCADE,
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  ordem INTEGER NOT NULL DEFAULT 0, rotulo TEXT,
  PRIMARY KEY (par_id, evidencia_id)
) STRICT;
CREATE TABLE previdencia_ente (
  id INTEGER PRIMARY KEY,
  ordem INTEGER NOT NULL UNIQUE,
  nome_texto TEXT NOT NULL,                      -- texto original de `n`
  entidade_id TEXT REFERENCES entidade(id),      -- NULL na linha agregada 'Outros oito'
  uf TEXT, valor_mi REAL, governante TEXT, partido TEXT, obs TEXT,
  natureza_id TEXT REFERENCES natureza(id)
) STRICT;
CREATE TABLE pagamento (
  id INTEGER PRIMARY KEY,
  categoria TEXT NOT NULL CHECK (categoria IN ('contrato','midia','doacao')),
  ordem INTEGER NOT NULL,                        -- posição em dinheiro.contratos / midia / doacoes
  nome_texto TEXT NOT NULL,                      -- texto original de `n`
  para_entidade_id TEXT REFERENCES entidade(id),
  valor_mi REAL NOT NULL,
  grupo TEXT,                                    -- `g` (só contratos)
  de_texto TEXT,                                 -- `de` (só doações)
  de_entidade_id TEXT REFERENCES entidade(id),
  ano INTEGER,                                   -- doações: ano extraído de `n` ('..., 2022')
  UNIQUE (categoria, ordem)
) STRICT;
CREATE TABLE indicio_maquina (
  id INTEGER PRIMARY KEY, ordem INTEGER NOT NULL UNIQUE,
  titulo TEXT NOT NULL, texto TEXT NOT NULL, contra TEXT NOT NULL, forca INTEGER NOT NULL
) STRICT;
CREATE TABLE limite (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('derrubado','aberto','agenda')),
  ordem INTEGER NOT NULL,
  titulo TEXT,                                   -- derrubado: afirmação; agenda: NULL
  texto TEXT NOT NULL,
  data TEXT,                                     -- agenda: ISO parcial quando reconhecível ('2026-10-13', '2026-12')
  data_texto TEXT,                               -- agenda: texto original ('13/10/2026', 'dez/2026')
  UNIQUE (tipo, ordem)
) STRICT;
CREATE TABLE forum (
  pais_entidade_id TEXT NOT NULL REFERENCES entidade(id),
  forum TEXT NOT NULL CHECK (forum IN ('G20','BRICS','OCDE','CSNU','nuclear')),
  status_texto TEXT,                             -- texto livre do original; nuclear: 'sim'/'nao'; CSNU com lista de anos: NULL
  anos TEXT,                                     -- JSON (lista de anos de mandato rotativo no CSNU)
  primeiro_teste INTEGER,                        -- nuclear: primeiro_teste_nuclear
  PRIMARY KEY (pais_entidade_id, forum)
) STRICT;

-- DESVIO (aditivo): estimativa em R$ de um escândalo/entidade (data/curadoria/entidade-valores.json, curadoria.aplicar_entidade_valores).
-- Cada linha mede uma `natureza` (o que o número é); números de naturezas diferentes não se somam. A URL da fonte é uma `evidencia`.
CREATE TABLE entidade_valor (
  id INTEGER PRIMARY KEY,
  entidade_id TEXT NOT NULL REFERENCES entidade(id),
  valor_brl REAL NOT NULL CHECK (valor_brl > 0),
  natureza TEXT NOT NULL CHECK (natureza IN ('movimentado','sonegado','desviado','bloqueado','passivo','prejuizo','investigado','outro')),
  texto TEXT NOT NULL,                           -- frase da estimativa como a fonte a sustenta
  quem_estima TEXT NOT NULL,                     -- autoridade/órgão que fez a conta (e por qual veículo)
  data TEXT CHECK (data IS NULL OR data GLOB '[0-9][0-9][0-9][0-9]*'),  -- data da estimativa (ISO parcial)
  principal INTEGER NOT NULL DEFAULT 0 CHECK (principal IN (0,1)),   -- 1 = a que aparece como "Estimativa" no painel (no máximo uma por entidade: índice abaixo)
  nota TEXT,                                     -- ressalva do pesquisador
  qualidade TEXT NOT NULL CHECK (qualidade IN ('boa','fraca')),
  motivo_fraca TEXT CHECK (qualidade = 'boa' OR motivo_fraca IS NOT NULL),
  ordem INTEGER NOT NULL DEFAULT 0,              -- ordem no arquivo de curadoria, por entidade
  evidencia_id INTEGER NOT NULL REFERENCES evidencia(id),
  trecho_citado TEXT                             -- trecho da fonte que sustenta o número
) STRICT;
CREATE UNIQUE INDEX ux_entidade_valor_principal ON entidade_valor(entidade_id) WHERE principal = 1;
CREATE UNIQUE INDEX ux_entidade_valor_ordem ON entidade_valor(entidade_id, ordem);

-- DESVIO (aditivo): posts de redes sociais coletados como PISTAS (nunca fonte que sustenta relação) e a triagem deles.
-- Entrada: data/raw/x/<conta>-*.jsonl (congelado, sha256 em hashes.txt) -> post_rede; data/curadoria/x-triagem.jsonl -> post_triagem*.
-- (curadoria.aplicar_posts_x). Regra do projeto: tweet é pista; quando corroborado por reportagem/documento, a relação entra pelo fluxo
-- normal e o post entra só como evidência de papel `contexto`. validar.py (seção "Pistas do X") proíbe pista como `sustenta`.
CREATE TABLE post_rede (
  id TEXT PRIMARY KEY CHECK (id GLOB '[a-z]:[0-9]*'),   -- 'x:<id do tweet>'
  plataforma TEXT NOT NULL CHECK (plataforma IN ('x')),
  conta TEXT NOT NULL,                           -- sem '@'
  url TEXT NOT NULL,                             -- https://x.com/<conta>/status/<id>
  publicado_em TEXT NOT NULL,                    -- 'AAAA-MM-DDTHH:MM'
  texto TEXT NOT NULL,
  card TEXT,                                     -- título/descrição do card de link, quando houver
  links TEXT NOT NULL DEFAULT '[]',              -- JSON: lista de URLs do tweet
  tem_video INTEGER NOT NULL DEFAULT 0 CHECK (tem_video IN (0,1)),
  consultas TEXT NOT NULL DEFAULT '[]',          -- JSON: tags das buscas que trouxeram o post (ex. ["master","faccoes"])
  arquivo_bruto TEXT NOT NULL,                   -- caminho relativo a data/raw (ex. 'x/republiqueBRA-2026-10.jsonl')
  coletado_em TEXT                               -- opcional (campo `k` do bruto); NULL quando o bruto não diz
) STRICT;
CREATE INDEX ix_post_rede_data ON post_rede(publicado_em);
-- Sem FK para post_rede de propósito: a triagem pode existir antes do bruto completo (validar.py lista as triagens sem post bruto).
CREATE TABLE post_triagem (
  post_id TEXT PRIMARY KEY CHECK (post_id GLOB 'x:[0-9]*' AND post_id NOT GLOB 'x:*[^0-9]*'),
  data_post TEXT NOT NULL,                       -- data do post como na triagem (AAAA-MM-DD)
  relevancia TEXT NOT NULL CHECK (relevancia IN ('pista','contexto','coberto','descartar')),
  tipo_afirmacao TEXT NOT NULL CHECK (tipo_afirmacao IN ('fato_atribuido','alegacao','opiniao')),
  afirmacao TEXT NOT NULL,                       -- frase normalizada
  fonte_citada TEXT,                             -- o que o tweet diz ser a fonte ("PF (operação)", "Folha"...)
  prioridade INTEGER NOT NULL CHECK (prioridade BETWEEN 1 AND 3),
  nota TEXT,
  triado_por TEXT NOT NULL,                      -- ex. 'claude-opus-piloto'
  triado_em TEXT NOT NULL
) STRICT;
CREATE INDEX ix_post_triagem_rel ON post_triagem(relevancia);
CREATE TABLE post_triagem_tema (
  post_id TEXT NOT NULL REFERENCES post_triagem(post_id) ON DELETE CASCADE,
  tema_id TEXT NOT NULL REFERENCES tema(id),
  PRIMARY KEY (post_id, tema_id)
) STRICT;
CREATE INDEX ix_post_triagem_tema ON post_triagem_tema(tema_id);
CREATE TABLE post_triagem_entidade (
  post_id TEXT NOT NULL REFERENCES post_triagem(post_id) ON DELETE CASCADE,
  nome TEXT NOT NULL,                            -- nome citado, como na triagem
  entidade_id TEXT REFERENCES entidade(id),      -- NULL quando o nome não casa, exato, com um único nome/alias do banco (nada de adivinhar)
  ordem INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (post_id, nome)
) STRICT;
CREATE INDEX ix_post_triagem_ent ON post_triagem_entidade(entidade_id);
CREATE TABLE post_relacionado (
  post_id TEXT NOT NULL REFERENCES post_triagem(post_id) ON DELETE CASCADE,
  relacionado_id TEXT NOT NULL,                  -- 'x:<id>'; sem FK: pode apontar para post ainda não triado/coletado
  tipo TEXT NOT NULL CHECK (tipo IN ('duplicata','relacionado')),
  PRIMARY KEY (post_id, relacionado_id, tipo)
) STRICT;

-- DESVIO (aditivo): marcadores = etiquetas finas (vocabulário controlado em data/curadoria/x-marcadores.json) para reaproveitar cada tweet em
-- vários casos (Master, facções, política, bets, INSS...). Diferente de `tema` (lista curta que organiza as páginas). Marcador fora do
-- vocabulário aborta a migração; o que ainda não existe vai em `post_triagem_marcador_sugerido` (texto livre, só para revisão).
CREATE TABLE marcador (
  id TEXT PRIMARY KEY,
  grupo TEXT NOT NULL,                           -- caso | ator | eleicoes | tipo-de-fato
  descricao TEXT NOT NULL
) STRICT;
CREATE TABLE post_triagem_marcador (
  post_id TEXT NOT NULL REFERENCES post_triagem(post_id) ON DELETE CASCADE,
  marcador_id TEXT NOT NULL REFERENCES marcador(id),
  PRIMARY KEY (post_id, marcador_id)
) STRICT;
CREATE INDEX ix_post_triagem_marcador ON post_triagem_marcador(marcador_id);
CREATE TABLE post_triagem_marcador_sugerido (
  post_id TEXT NOT NULL REFERENCES post_triagem(post_id) ON DELETE CASCADE,
  texto TEXT NOT NULL,
  PRIMARY KEY (post_id, texto)
) STRICT;

-- Views --------------------------------------------------------------------------------------------------------------
-- Compatibilidade com o modelo antigo: `video` = fontes do tipo video (somente leitura; escreva em `fonte`).
CREATE VIEW video AS
  SELECT id, plataforma, url, titulo, canal, canal_entidade_id, publicado_em, duracao_s, texto AS transcricao,
         arquivo_texto AS arquivo_transcricao, resumo, classificado_em, classificador_versao, status, criado_em
  FROM fonte WHERE tipo = 'video';

-- Entidade x tema, derivada: a entidade pertence ao tema se tem relação ou evento nele. Fontes estruturais acrescentadas (sem elas
-- a empresa do ranking, o partido da bancada e o país de `forum` não teriam relação/evento): mandato/bancada/ranking_empresa -> 'brasil-ano-a-ano',
-- forum -> 'pares', dossiê relacional (par, ente de previdência, pagamento) -> 'caso-master'.
CREATE VIEW v_entidade_tema AS
  SELECT DISTINCT entidade_id, tema_id FROM (
    SELECT r.de AS entidade_id, t.tema_id FROM relacao r JOIN relacao_tema t ON t.relacao_id = r.id
    UNION ALL SELECT r.para, t.tema_id FROM relacao r JOIN relacao_tema t ON t.relacao_id = r.id
    UNION ALL SELECT x.entidade_id, t.tema_id FROM evento_entidade x JOIN evento_tema t ON t.evento_id = x.evento_id
    UNION ALL SELECT entidade_id, 'brasil-ano-a-ano' FROM mandato
    UNION ALL SELECT orgao_id, 'brasil-ano-a-ano' FROM mandato WHERE orgao_id IS NOT NULL
    UNION ALL SELECT partido_id, 'brasil-ano-a-ano' FROM bancada
    UNION ALL SELECT entidade_id, 'brasil-ano-a-ano' FROM ranking_empresa
    UNION ALL SELECT pais_entidade_id, 'pares' FROM forum
    UNION ALL SELECT ator_entidade_id, 'caso-master' FROM dossie_par WHERE ator_entidade_id IS NOT NULL
    UNION ALL SELECT entidade_id, 'caso-master' FROM previdencia_ente WHERE entidade_id IS NOT NULL
    UNION ALL SELECT para_entidade_id, 'caso-master' FROM pagamento WHERE para_entidade_id IS NOT NULL
    UNION ALL SELECT de_entidade_id, 'caso-master' FROM pagamento WHERE de_entidade_id IS NOT NULL
  ) WHERE tema_id IN (SELECT id FROM tema);
