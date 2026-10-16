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
mais lento, ~1 s extra).

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
- **Idempotente por `video.id`**: reenviar substitui trechos e cortes anteriores daquele vídeo (ids novos), sem duplicar relações; `status` do vídeo é preservado.
- Sucesso: `{"ok":true,"video_id","trechos","cortes","relacoes_criadas":[ids],"relacoes_existentes_reutilizadas":[ids],"substituiu_insercao_anterior":null|{trechos,cortes},"avisos":[…],"dump":{…}}`.

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
- `busca_fts` não é preenchida para `trecho` por `importar.py`; o servidor a sincroniza na subida e a cada escrita.
- Entidades novas só entram por migração/script editorial, não por este servidor.
