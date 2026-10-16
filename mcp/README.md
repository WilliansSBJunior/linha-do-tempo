# mcp/ — servidor MCP da Linha do Tempo

Servidor MCP (stdio, SDK oficial `mcp`) sobre `data/linha-do-tempo.sqlite`. **É o único escritor do banco.** O classificador de vídeos
(sessão separada) não abre o sqlite: chama `inserir_video`.

Regras de ouro:
- **Nunca cria entidade.** `de`/`para`/`entidades` precisam existir; senão o servidor devolve erro com até 3 sugestões por id.
- Relações novas entram com `status='revisar'` (nunca rebaixa uma relação `publicada`).
- Toda escrita = uma transação (`BEGIN IMMEDIATE` → `foreign_key_check` → `COMMIT`) e, em seguida, **regrava `data/dump.sql`** de forma
  determinística (`scripts/comum.gerar_dump`, via arquivo temporário + rename).
- **O commit no git é manual**: depois de uma sessão de escrita, `git add data/ && git commit`. O `.sqlite` é ignorado.
- Rejeições de validação voltam como `{"ok": false, "erro": ..., ...}` (não como erro de protocolo); nada é gravado.

## Instalação

```bash
pip install --break-system-packages -r mcp/requirements.txt   # ou: python3 -m venv .venv && .venv/bin/pip install -r mcp/requirements.txt
python3 scripts/importar.py          # se ainda não existir data/linha-do-tempo.sqlite (reconstrói do dump)
python3 mcp/test_server.py -v        # testes (usam cópia temporária)
python3 mcp/smoke_stdio.py           # sobe o servidor por stdio e lista as ferramentas
```

Funciona com o SDK 1.x (`FastMCP`) e 2.x (`MCPServer`). Rode scripts por caminho (`python3 mcp/server.py`), não com `python -m mcp...`
(a pasta `mcp/` do repo sombrearia o pacote do SDK).

Variáveis opcionais: `LDT_DB` (sqlite), `LDT_DUMP` (dump.sql), `LDT_EXPORT_JSON=1` (após cada escrita roda também `scripts/exportar_json.py`;
mais lento, ~1 s extra). Variáveis do RAG: ver a seção "RAG" abaixo.

## Registro

Claude Code (da raiz do repo; usar caminhos absolutos):

```bash
claude mcp add linha-do-tempo -- python3 /home/claude/linha-do-tempo/mcp/server.py
# com export JSON automático:
claude mcp add linha-do-tempo -e LDT_EXPORT_JSON=1 -- python3 /home/claude/linha-do-tempo/mcp/server.py
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "linha-do-tempo": {
    "command": "python3", "args": ["/home/claude/linha-do-tempo/mcp/server.py"],
    "env": { "LDT_EXPORT_JSON": "0" } } } }
```

## Ferramentas e exemplos

Os argumentos abaixo são os do `tools/call`.

**`buscar_entidade(consulta, tipo=None, limite=20)`** — slug exato (100) > alias/nome normalizado exato (90) > palavras inteiras do alias/nome (60)
> FTS5 em nome/cargo/descrição/aliases (30). Desempate por nº de relações. Campo `casou_por` diz como casou.
```json
{"consulta": "Vorcaro", "limite": 5}
→ [{"id":"daniel-vorcaro","nome":"Daniel Vorcaro","tipo":"pessoa","categoria":"hub","cargo":null,"descricao":"…","aliases":["Daniel Bueno Vorcaro","Daniel Vorcaro"],"n_relacoes":69,"casou_por":"alias (palavra)"}, …]
```

**`buscar_relacoes(entidade|de|para, tipo, natureza, ano_inicio, ano_fim, status, limite=50)`** — `entidade` casa `de` OU `para`; os três aceitam id ou
alias exato e único. `natureza` aceita qualquer vocabulário. Anos: sobreposição de período (sem `periodo_fim` conta como pontual; sem início é excluída
quando há filtro de ano). Cada relação traz `evidencias` (url, veiculo, titulo, data, tipo, papel) e `cortes`.
```json
{"entidade": "banco-master", "natureza": "doc", "ano_inicio": 2024, "limite": 10}
```

**`buscar_trechos(texto, entidade, video, natureza, limite=50)`** — FTS em afirmação + texto original; `video` = id (`yt:…`) ou url. Devolve entidades, anos,
valores, relações e cortes de cada trecho.
```json
{"texto": "Valadão", "entidade": "banco-master"}
```

**`inserir_relacao(de, para, tipo, rotulo, natureza, descricao?, subtipo?, periodo_inicio?, periodo_fim?, valor_brl?, valor_texto?, resposta?, evidencias?, origem='manual', status='revisar')`**
Upsert pela chave `(de, para, tipo, rotulo, periodo_inicio)`. Evidências: upsert por URL normalizada (sem `#frag`, `utm_*`, barra final). Retorna
`{"ok":true,"acao":"criada|atualizada","relacao_id":…}`.
```json
{"de":"banco-master","para":"andre-valadao","tipo":"financeira","rotulo":"Patrocínio X","natureza":"rep","periodo_inicio":"2023",
 "evidencias":[{"url":"https://exemplo.com/materia","veiculo":"Exemplo","titulo":"…","data":"2024-01-10","tipo":"reportagem"}]}
```
Tipos: `financeira societaria contratual juridica investigacao politica pessoal familiar profissional institucional religiosa midia outra`.
Naturezas aceitas: `doc inv rep ale nc` · `fato_documentado alegacao opiniao` · `documentada investigacao reportada alegacao opiniao nao_classificada`.

**`inserir_video(video, trechos, cortes_sugeridos)`** — ver contrato abaixo.

**`buscar_semantica(texto, tabelas=None, limite=20, k_fts=50)`** — busca híbrida: candidatos do FTS5 (`busca_fts`, consulta OR sem stopwords, top `k_fts`) ∪ top-`k_fts`
vetorial; reordenação por RRF (`Σ 1/(60+posição)`). `tabelas` ⊂ `trecho evidencia relacao evento entidade` (+`nota`, só FTS). Cada resultado:
`origem_tabela, origem_id, titulo, trecho, score` (+ `cos, rank_fts, rank_vetorial` e, conforme a tabela, `de/para/tipo/status`, `url`, `video_id`...).
Envelope: `{"ok","provedor","metodo":"rrf(fts5, vetorial)"|"fts5","avisos":[…],"n_candidatos","resultados":[…]}`. Sem provedor ou sem vetores: só FTS e um aviso.
```json
{"texto": "venda do banco ao BRB", "tabelas": ["relacao","evento"], "limite": 5}
```

**`relacoes_similares(rotulo, de=None, para=None, limite=10, cos_min=None, tipo=None)`** — relações existentes cujo **rótulo** é próximo do informado.
Com `de` e `para`: só aquele par (qualquer direção; `invertida:true` avisa). `cos_min` padrão = limiar do provedor (0,80 modelo real / 0,45 hash).
Cada item traz `cos` e `reutilizaria_na_insercao` (mesmo `de,para,tipo` na mesma direção e `cos` ≥ limiar de dedup). Chame antes de inserir.
```json
{"rotulo": "Mesada mensal de R$ 300 mil", "de": "daniel-vorcaro", "para": "ciro-nogueira"}
→ {"ok":true,"modelo":"hash-ngram-256-v1","limiar_cos":0.45,"limiar_dedup":0.6,"similares":[{"id":59,"rotulo":"Mesada de R$ 300-500 mil (segundo a PF)","cos":0.5497,"invertida":true,"reutilizaria_na_insercao":false,…}]}
```

**`resumo_banco()`** — contagens por tabela e distribuição de relações/cortes. **`exportar()`** — roda `scripts/exportar_json.py` e `scripts/validar.py` no banco
configurado e devolve a saída e os códigos de saída (esses scripts gravam em `data/` do repo).

## Contrato JSON de `inserir_video` (colar no prompt do classificador)

```json
{
  "video": {
    "id": "yt:dQw4w9WgXcQ",              // id OU url (YouTube: um deriva o outro). Outras plataformas: id e url obrigatórios
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "plataforma": "youtube",             // youtube|instagram|tiktok|x|podcast|outro
    "titulo": "…", "canal": "…",
    "publicado_em": "2026-10-01",        // opcional
    "duracao_s": 3600,                   // opcional
    "transcricao": "…",                  // opcional (texto inteiro, guardado em video.transcricao)
    "classificador_versao": "v1"         // opcional
  },
  "trechos": [
    {
      "ordem": 1,                        // inteiro, único no vídeo
      "inicio_s": 10.5, "fim_s": 40.0,   // fim_s >= inicio_s
      "texto_original": "…",             // opcional
      "afirmacao": "frase normalizada do que foi afirmado",
      "natureza": "fato_documentado",    // fato_documentado | alegacao | opiniao
      "entidades": ["banco-master", "daniel-vorcaro"],   // ids canônicos EXISTENTES (use buscar_entidade)
      "relacoes": [
        {"de": "banco-master", "para": "andre-valadao", "tipo": "financeira",
         "rotulo": "opcional",           // se ausente: reutiliza relação (de,para,tipo[,início]) existente; se não houver, cria "Relação <tipo> (a revisar)"
         "periodo": {"inicio": "2023", "fim": "2024"}}   // ou "2023" ou "2023-2024"; opcional
      ],
      "anos_referidos": [2023, 2024],
      "valores": [{"valor": 1500000, "moeda": "BRL", "descricao": "…"}],   // moeda: BRL|USD|EUR|pct|outro
      "confianca": 0.8,                  // 0..1
      "potencial_corte": 4               // 0..5
    }
  ],
  "cortes_sugeridos": [
    {"titulo": "…", "inicio_s": 10.5, "fim_s": 90.0,   // fim_s > inicio_s
     "justificativa": "…", "tema": "…",
     "trechos": [1, 2],                  // ordens dos trechos; se omitido, usa os trechos totalmente contidos no intervalo
     "relacoes_cobertas": [{"de": "banco-master", "para": "andre-valadao", "tipo": "financeira"}]}
  ]
}
```

Comportamento:
- **Uma transação**: video → trecho → trecho_entidade/ano/valor → relacao (upsert; nova = `origem='classificador'`, `status='revisar'`, natureza e `confianca`
  do trecho, `origem_ref='trecho:<id>'`, vídeo ligado como evidência `tipo=video`) → trecho_relacao → corte → corte_trecho → relacao_corte.
- **Relação existente** (mesma chave) não muda natureza/status/confiança nem ganha evidência; só ganha o vínculo com o trecho (e `periodo_fim` se estava vazio).
  `relacoes_cobertas` casa por `(de, para, tipo)`, preferindo relações ligadas aos trechos deste vídeo.
- **Entidade desconhecida** (em `entidades`, `relacoes` ou `relacoes_cobertas`): o vídeo inteiro é rejeitado, nada é gravado. Resposta:
  `{"ok":false,"erro":…,"nao_resolvidas":[{"id":"x","usado_em":["trechos[1].entidades"],"sugestoes":[{"id","nome","tipo","casou_por"}×≤3]}],"outros_erros":[…]}`.
- **Dedup por embedding** (`dedup_por='embedding'`): quando o rótulo enviado não coincide exatamente com nenhuma relação, mas existe, no **mesmo `(de, para, tipo)` e mesma
  direção**, uma relação com `cos(rótulo) ≥` limiar de dedup (0,90 modelo real / 0,60 hash; períodos de início em anos diferentes nunca se fundem), ela é **reutilizada**
  (tratada como "relação existente": só ganha o vínculo com o trecho). A resposta lista `dedup:[{trecho, dedup_por, cos, relacao_id, rotulo_enviado, rotulo_existente}]`.
  Vale também para `inserir_relacao` (campos `dedup_por`, `cos`, `rotulo_existente`; atualiza a relação existente em vez de criar). `LDT_DEDUP_EMBEDDING=0` desliga.
- **Idempotente por `video.id`**: reenviar substitui trechos e cortes anteriores daquele vídeo (ids novos), sem duplicar relações; `status` do vídeo é preservado.
- Sucesso: `{"ok":true,"video_id","trechos","cortes","relacoes_criadas":[ids],"relacoes_existentes_reutilizadas":[ids],"dedup":[…],"substituiu_insercao_anterior":null|{trechos,cortes},"avisos":[…],"embeddings":{"status":"ok"|"ignorado","gerados":{…},"modelo"|"motivo"},"dump":{…}}`.

## RAG (embeddings, `buscar_semantica`, dedup)

- **Tabela** `embedding(origem_tabela, origem_id, modelo, dim, texto_hash, vetor BLOB float32)` (`scripts/schema_rag.sql`, idempotente; o servidor a cria na subida).
  É **derivada**: não entra em `data/dump.sql` e some quando o banco é reconstruído por `importar.py` → rode `python3 scripts/embeddings.py` depois de importar.
- **Caminho de busca ativo: numpy, não sqlite-vec.** `sqlite-vec` não pôde ser instalado no ambiente onde isto foi desenvolvido (PyPI inacessível pelo proxy); o código usa
  o fallback puro previsto: vetores normalizados em BLOB e cosseno por produto escalar em numpy (tudo em memória a cada consulta; ~2 mil vetores × 256 dim < 1 ms).
  Trocar por `vec0` só exigiria reescrever `scripts/embeddings.py:top_k` — a tabela `embedding` e as ferramentas continuam iguais.
- **Provedor** (`LDT_EMBED_PROVIDER`, ver `scripts/embeddings.py`): `auto` (padrão) = `sentence-transformers` local se instalado e o modelo carregar
  (`LDT_EMBED_MODEL`, padrão `intfloat/multilingual-e5-small`), senão `hash`. Explícitos: `st`, `openai`, `voyage`, `ollama` (chave em `LDT_EMBED_API_KEY` ou `OPENAI_API_KEY`/`VOYAGE_API_KEY`;
  `LDT_EMBED_URL` para endpoint compatível/ollama) — **não testados contra a rede real**. `hash` = feature hashing de n-gramas de caracteres (3–5) + palavras + bigramas,
  256 dim, determinístico, sem rede: **só captura sobreposição lexical** (sinônimos como "pagamento mensal" ↔ "mesada" não aproximam).
  Cada vetor é guardado com o nome do modelo; trocar de provedor cria um segundo conjunto de vetores (reindexe; os antigos ficam até `--rebuild`/limpeza).
- **Limiares de cosseno** (`LDT_SIM_MIN`, `LDT_SIM_DEDUP` sobrescrevem): modelo real 0,80/0,90; hash 0,45/0,60 (calibrado nos 367 rótulos atuais: nenhuma relação distinta do mesmo
  `(de,para,tipo)` passa de 0,60; ver "Limitações"). Com e5, cosseno de textos não relacionados já costuma ficar em 0,7–0,8: **recalibre ao trocar para e5** (rode
  `relacoes_similares` em pares conhecidos e ajuste `LDT_SIM_*`).
- **Reindexar**: `python3 scripts/embeddings.py [--db …] [--rebuild] [--tabelas trecho,evidencia,relacao,evento,entidade]`. Pula linhas com mesmo modelo + mesmo hash do texto;
  remove vetores órfãos. Referência (hash, 2 050 linhas + 367 rótulos = 2 417 vetores): ~1,1 s na primeira passada, ~0,04 s sem mudanças. Com modelo local/remoto o custo é
  proporcional ao nº de linhas novas ou alteradas (e5-small em CPU: dezenas de ms por linha; API: 1 chamada por lote de 64).
- **Na escrita**: `inserir_relacao`/`inserir_video` gravam, na mesma transação, os vetores de `relacao`, `relacao_rotulo` (só o rótulo, usado no dedup), `trecho` e da evidência do vídeo.
  Sem provedor disponível a escrita **continua**, o dedup por embedding é pulado e a resposta traz `embeddings:{status:"ignorado", motivo}`; a linha fica sem vetor até
  `scripts/embeddings.py`. `buscar_semantica` sem provedor/vetores cai para FTS; `relacoes_similares` sem provedor devolve `{ok:false}`.

## Limitações e o que acontece em falhas

- **Concorrência**: escritas são serializadas por `threading.Lock` + `flock` em `data/.mcp-escrita.lock` + `BEGIN IMMEDIATE` (vários servidores, ex. Desktop e Code,
  podem coexistir). Leituras não bloqueiam (WAL). O lock de arquivo exige filesystem local (não NFS).
- **Transcrição**: guardada inteira em `video.transcricao` e, portanto, também em `data/dump.sql` (cada linha do dump é um INSERT; transcrições longas
  incham o dump e o diff do git). Não há limite no servidor; o limite prático é o do cliente MCP. Considere enviar só trechos e deixar `transcricao` de fora.
- **Dump/commit**: se a regravação do dump falhar após o COMMIT, os dados ficam no sqlite e a resposta traz `dump.dump_status` com o erro; rode `exportar()`.
  Se `LDT_EXPORT_JSON=1` e a exportação falhar, o código/saída aparecem em `dump.exportar_json`. O commit no git nunca é feito pelo servidor.
- **`validar.py` não roda a cada escrita** (só na ferramenta `exportar()`); dentro da transação o servidor checa `foreign_key_check` e os CHECK/UNIQUE do schema, e desfaz tudo se falhar.
  Se `validar.py` falhar depois de uma inserção, nada é revertido automaticamente: leia a saída, corrija com outra chamada de `inserir_relacao`/`inserir_video`, ou descarte
  tudo com `git checkout data/dump.sql && python3 scripts/importar.py --force` (reconstrói o sqlite do último dump commitado).
  Atenção: `validar.py` compara `data/*.json` com o export do banco; se a inserção criou um `tipo` de relação inédito, `tipos_relacao` de `entities.json` muda — rode `exportar()`.
- Reinserir um vídeo apaga seus cortes anteriores, inclusive os já `aprovado`/`publicado` (a resposta traz um aviso). Relações criadas por uma versão anterior do mesmo vídeo
  permanecem (com `status='revisar'`) mesmo que a nova versão não as repita.
- **Qualidade do fallback `hash`**: busca "venda do banco ao BRB" coloca a relação Banco Master↔BRB em 5º (entidades "Banco …" vêm antes por casarem em "banco"); dedup só
  funde rótulos com palavras em comum (ex.: "Mesada de R$ 300 mil" ↔ "Mesada de R$ 300-500 mil (segundo a PF)": 0,66). Paráfrases reais exigem modelo de verdade.
  Risco inverso no hash: rótulos curtos com mesmos números ("Carteiras inexistentes? (R$ 12,2 bi)" × "Carteiras negociadas (R$ 12,76 bi)": 0,48) ficam abaixo de 0,60, mas
  isso é margem estreita. Relações fundidas por dedup continuam `status='revisar'` se novas; as existentes não mudam de natureza/status.
- Evidências não estão no FTS (`busca_fts` não as indexa): em `buscar_semantica` elas só entram pelo lado vetorial.
- `busca_fts` não é preenchida para `trecho` por `importar.py`; o servidor a sincroniza na subida e a cada escrita.
- Entidades novas só entram por migração/script editorial, não por este servidor.
