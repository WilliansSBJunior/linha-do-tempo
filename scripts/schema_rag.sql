-- RAG pequeno da Linha do Tempo. Aplicado a parte do schema.sql (idempotente): scripts/embeddings.py e mcp/server.py rodam isto.
-- Caminho ativo sem a extensao sqlite-vec: vetor float32 em BLOB + busca por cosseno em numpy (ver mcp/README.md, secao RAG).
-- origem_tabela: trecho | evidencia | relacao | evento | entidade | nota | relacao_rotulo (so rotulo+tipo, usado na deduplicacao).
-- Esta tabela NAO entra em data/dump.sql (e derivada e reconstruivel): depois de importar.py rode scripts/embeddings.py.
CREATE TABLE IF NOT EXISTS embedding (
  origem_tabela TEXT NOT NULL,
  origem_id TEXT NOT NULL,
  modelo TEXT NOT NULL,          -- ex.: 'hash-ngram-256-v1', 'st:intfloat/multilingual-e5-small'
  dim INTEGER NOT NULL,
  texto_hash TEXT NOT NULL,      -- sha256 do texto embutido; igual => nao reindexa
  vetor BLOB NOT NULL,           -- float32 little-endian, normalizado (norma 1)
  criado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  PRIMARY KEY (origem_tabela, origem_id, modelo)
) STRICT;
CREATE INDEX IF NOT EXISTS ix_embedding_modelo ON embedding(modelo, origem_tabela);
