# Classificador de vídeos → banco (via MCP `inserir_video`)

> Documento para colar na sessão **"Canal de cortes automation"**. Substitui o fluxo antigo (salvar `data/videos/<id>.json` no repositório).
> Fonte da verdade do contrato: `mcp/README.md` (repo `linha-do-tempo`). Se este texto divergir dele, vale o README.

## 1. O que muda

- **Pare de commitar JSON.** Não crie mais `data/videos/<id>.json`, não faça `git add` de saída do classificador.
- **Chame a ferramenta MCP `inserir_video`** (servidor `linha-do-tempo`) com três argumentos: `video`, `trechos`, `cortes_sugeridos`.
  O servidor grava tudo numa transação no SQLite e regrava `data/dump.sql`. **O commit no git continua manual** (feito por um humano na sessão do repositório).
- Você **não abre o SQLite** e **não cria entidades**. O servidor é o único escritor.
- Reenviar o mesmo `video.id` é seguro: substitui os trechos/cortes anteriores daquele vídeo e não duplica relações.
- Relações novas entram com `status='revisar'`, `origem='classificador'`; nada vira `publicada` sem revisão humana.
- Além de `inserir_video`, você tem leitura: `buscar_entidade`, `buscar_relacoes`, `buscar_trechos`, `buscar_semantica`, `relacoes_similares`.

## 2. Regra de IDs canônicos (obrigatória)

1. **Antes de preencher `entidades`, `relacoes[].de/para` ou `relacoes_cobertas[].de/para`, consulte `buscar_entidade`** para cada pessoa/empresa/órgão citado.
   ```json
   {"consulta": "Vorcaro", "limite": 5}
   → [{"id":"daniel-vorcaro","nome":"Daniel Vorcaro","tipo":"pessoa","aliases":["Daniel Bueno Vorcaro","Daniel Vorcaro"],"n_relacoes":69,"casou_por":"alias (palavra)"}, …]
   ```
   Use o campo `id` (slug) exatamente como veio. Exemplos reais: `daniel-vorcaro`, `ciro-nogueira`, `banco-master`, `brb`, `andre-valadao`, `cvm`.
2. **Nunca invente slug**, nem "adivinhe" a partir do nome (`daniel-vorkaro` é rejeitado). Se houver homônimos (`ciro-nogueira` × `ciro-soares`), desambigue pelo contexto do vídeo;
   se continuar ambíguo, trate como não resolvido.
3. **Entidade que não existe** (a consulta volta vazia ou só com resultados que não são a pessoa certa): **não envie o vídeo ainda.** Coloque o termo em
   `nao_resolvidas` **no seu próprio JSON de trabalho** (campo auxiliar que você mantém fora da chamada: `{"termo": "...", "trecho": 3, "contexto": "..."}`) e devolva ao humano a lista para
   decidir (cadastrar a entidade, mapear para outra, ou omitir a menção). Só envie depois da decisão.
   *Alternativa aceitável:* enviar mesmo assim e tratar a rejeição (o servidor devolve `{"ok":false,"nao_resolvidas":[…]}` e **grava nada**), mas isso gasta uma chamada e não resolve sozinho:
   o cadastro de entidades é feito por migração/edição editorial, nunca por este servidor.
4. **Antes de criar relação nova, verifique se ela já existe**: `buscar_relacoes` com `de`/`para` e `relacoes_similares(rotulo, de, para)` para o par.
   Se vier algo com `reutilizaria_na_insercao: true`, o servidor vai reutilizar sozinho; ainda assim **escreva o rótulo no mesmo estilo dos existentes** (curto, factual, com valor se houver).
   O servidor também faz essa deduplicação por embedding (`dedup_por: "embedding"` na resposta) quando `(de, para, tipo)` coincidem e o rótulo é praticamente o mesmo; ela é uma rede de segurança, não um substituto da checagem.
5. A direção importa: `de → para` deve seguir quem pratica/paga/aciona (`felipe-cancado-vorcaro → ciro-nogueira` "Teria pago a mesada"). Consulte `buscar_relacoes` para ver como o par já está orientado.

## 3. Vocabulários fechados

**`natureza`** (por trecho; qualquer outra string é rejeitada):

| valor enviado | vira no banco | quando usar |
|---|---|---|
| `fato_documentado` | `documentada` | há documento/decisão/dado oficial citado ou mostrado |
| `alegacao` | `alegacao` | atribuído a alguém (PF, delator, reportagem) sem comprovação no vídeo |
| `opiniao` | `opiniao` | juízo do apresentador/entrevistado |

(O servidor também aceita `doc/inv/rep/ale/nc` e os ids canônicos `documentada, investigacao, reportada, alegacao, opiniao, nao_classificada`, mas o classificador deve usar só os três acima.)

**`relacoes[].tipo`** (obrigatório, um destes 13):
`financeira` · `societaria` · `contratual` · `juridica` · `investigacao` · `politica` · `pessoal` · `familiar` · `profissional` · `institucional` · `religiosa` · `midia` · `outra`

**`video.plataforma`**: `youtube` · `instagram` · `tiktok` · `x` · `podcast` · `outro`

**`valores[].moeda`**: `BRL` · `USD` · `EUR` · `pct` · `outro` (aceita também `R$`, `US$`, `€`, `%`; qualquer outra vira `outro`)

**Faixas**: `confianca` 0..1 · `potencial_corte` 0..5 · `periodo`: `"AAAA"`, `"AAAA-MM"`, `"AAAA-MM-DD"`, `"AAAA-AAAA"` ou `{"inicio": …, "fim": …}`

## 4. Contrato completo de `inserir_video`

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
(Os comentários `//` acima são só explicação: o JSON enviado não pode tê-los.)

Comportamento do servidor:
- **Uma transação**: video → trecho → trecho_entidade/ano/valor → relacao (upsert; nova = `origem='classificador'`, `status='revisar'`, natureza e `confianca` do trecho,
  `origem_ref='trecho:<id>'`, vídeo ligado como evidência `tipo=video`) → trecho_relacao → corte → corte_trecho → relacao_corte.
- **Relação existente** (mesma chave, ou rótulo equivalente por embedding no mesmo `de,para,tipo`) não muda natureza/status/confiança nem ganha evidência; só ganha o vínculo com o trecho
  (e `periodo_fim` se estava vazio). `relacoes_cobertas` casa por `(de, para, tipo)`, preferindo relações ligadas aos trechos deste vídeo.
- **Entidade desconhecida** (em `entidades`, `relacoes` ou `relacoes_cobertas`): o vídeo inteiro é rejeitado, nada é gravado.
- **Erro de formato** (natureza inválida, `fim_s < inicio_s`, tipo fora do vocabulário, `ordem` repetida…): rejeitado inteiro com `{"ok":false,"erro":"entrada inválida; nada foi gravado","erros":[…]}`.
- **Idempotente por `video.id`**: reenviar substitui trechos e cortes anteriores daquele vídeo (ids novos), sem duplicar relações; `status` do vídeo é preservado.
  Atenção: cortes já `aprovado`/`publicado` daquele vídeo também são substituídos (a resposta traz aviso). Relações criadas por uma versão anterior permanecem.
- `transcricao` é opcional e vai inteira para `data/dump.sql` (incha o diff do git). Prefira **não enviar a transcrição**; envie só os trechos.

## 5. Checklist de qualidade por trecho

Antes de enviar, cada trecho precisa passar em todos:

- [ ] **Afirmação atômica**: uma única proposição verificável por trecho ("A PF afirma que X recebeu R$ Y de Z em 2024"), sem "e", sem conclusões suas. Se o vídeo faz duas afirmações, são dois trechos.
- [ ] **Atribuição explícita** na `afirmacao` quando for `alegacao` ou `opiniao` (quem disse: PF, delator, apresentador). Nunca transforme alegação em fato.
- [ ] **Natureza coerente**: `fato_documentado` só com lastro citado no próprio trecho; na dúvida, `alegacao`.
- [ ] **Período**: `anos_referidos` e `periodo` da relação preenchidos quando o vídeo dá a data (ano é suficiente); sem chute. Se não há data, deixe vazio, não invente.
- [ ] **Valores com moeda**: cada valor em `valores` com número cheio (`300000`, não "300 mil"), `moeda` correta (`BRL`/`USD`/`EUR`/`pct`/`outro`) e `descricao` ("mesada mensal citada"). Faixas ("300 a 500 mil") entram como dois valores ou no rótulo, não como média.
- [ ] **Entidades resolvidas** por `buscar_entidade` (seção 2); toda entidade que aparece em `relacoes` também está (ou pode estar) em `entidades`.
- [ ] **Rótulo da relação** curto e factual, no estilo das existentes ("Mesada de R$ 300-500 mil (segundo a PF)"); o mesmo fato em trechos diferentes usa o mesmo rótulo.
- [ ] **Tempos**: `inicio_s`/`fim_s` em segundos desde o início do vídeo, `fim_s >= inicio_s`; cortes com `fim_s > inicio_s` e cobrindo os trechos listados.
- [ ] **`confianca`** reflete a certeza da *transcrição + classificação* (0..1), não a veracidade do fato. **`potencial_corte`** 0..5 só alto quando o trecho funciona sozinho em 30–90 s.
- [ ] **Corte**: `justificativa` diz por que funciona; `relacoes_cobertas` lista só relações realmente afirmadas nos trechos do corte.

## 6. Exemplo completo

Chamada (`tools/call` → `inserir_video`). O rótulo "Mesada de R$ 300 mil" é uma paráfrase de uma relação que já existe (id 59):

```json
{
  "video": {
    "id": "yt:EXEMPLO12345",
    "plataforma": "youtube",
    "titulo": "Caso Master: o que a PF já mostrou",
    "canal": "Canal Exemplo",
    "publicado_em": "2026-10-01",
    "duracao_s": 1800,
    "classificador_versao": "v1"
  },
  "trechos": [
    {
      "ordem": 1,
      "inicio_s": 62.0,
      "fim_s": 95.5,
      "texto_original": "…a PF diz que o Ciro recebia uma mesada de uns 300 mil do Vorcaro…",
      "afirmacao": "A PF afirma que Ciro Nogueira recebeu mesada de R$ 300 mil de Daniel Vorcaro em 2024.",
      "natureza": "alegacao",
      "entidades": ["ciro-nogueira", "daniel-vorcaro"],
      "relacoes": [
        {"de": "ciro-nogueira", "para": "daniel-vorcaro", "tipo": "politica",
         "rotulo": "Mesada de R$ 300 mil", "periodo": {"inicio": "2024"}}
      ],
      "anos_referidos": [2024],
      "valores": [{"valor": 300000, "moeda": "BRL", "descricao": "mesada mensal citada"}],
      "confianca": 0.85,
      "potencial_corte": 4
    }
  ],
  "cortes_sugeridos": [
    {
      "titulo": "A mesada que a PF atribui a Ciro",
      "inicio_s": 55.0,
      "fim_s": 100.0,
      "justificativa": "Afirmação atômica com valor e fonte (PF)",
      "tema": "Caso Master",
      "trechos": [1],
      "relacoes_cobertas": [{"de": "ciro-nogueira", "para": "daniel-vorcaro", "tipo": "politica"}]
    }
  ]
}
```

### Resposta de sucesso (saída real, banco de teste)

```json
{
  "ok": true,
  "video_id": "yt:EXEMPLO12345",
  "trechos": 1,
  "cortes": 1,
  "relacoes_criadas": [],
  "relacoes_existentes_reutilizadas": [59],
  "dedup": [
    {"trecho": 1, "dedup_por": "embedding", "cos": 0.6609, "relacao_id": 59,
     "rotulo_enviado": "Mesada de R$ 300 mil", "rotulo_existente": "Mesada de R$ 300-500 mil (segundo a PF)"}
  ],
  "substituiu_insercao_anterior": null,
  "avisos": [],
  "embeddings": {"status": "ok", "gerados": {"trecho": 1, "evidencia": 1}, "modelo": "hash-ngram-256-v1"},
  "dump": {"dump_sql": "…/data/dump.sql", "commit_git": "manual (git add data/ && git commit)", "dump_status": "ok"}
}
```

Como ler: `relacoes_criadas` vazio + `relacoes_existentes_reutilizadas:[59]` = nada duplicado. `dedup[*].dedup_por == "embedding"` = o rótulo foi reconhecido como equivalente; se o humano discordar,
ele separa depois (a relação 59 continua `publicada`). Se `embeddings.status == "ignorado"`, o provedor de embeddings estava fora do ar: o vídeo foi gravado normalmente, só sem deduplicação semântica
nem vetores (o humano roda `scripts/embeddings.py` depois). Confira sempre `avisos` e `dump.dump_status`.

### Resposta de rejeição por entidade desconhecida (saída real)

Enviando `"daniel-vorkaro"` em `entidades` e `"ciro-nogueira-senador"` em `relacoes[0].de` (**nada foi gravado**):

```json
{
  "ok": false,
  "erro": "entidades desconhecidas: o vídeo inteiro foi rejeitado (nada foi gravado). Peça cadastro ou corrija os ids.",
  "nao_resolvidas": [
    {"id": "daniel-vorkaro", "usado_em": ["trechos[0].entidades"],
     "sugestoes": [{"id": "banco-master", "nome": "Banco Master", "tipo": "banco", "casou_por": "texto (FTS)"},
                   {"id": "daniel-vorcaro", "nome": "Daniel Vorcaro", "tipo": "pessoa", "casou_por": "texto (FTS)"},
                   {"id": "fabiano-zettel", "nome": "Fabiano Zettel", "tipo": "pessoa", "casou_por": "texto (FTS)"}]},
    {"id": "ciro-nogueira-senador", "usado_em": ["trechos[0].relacoes[0].de"],
     "sugestoes": [{"id": "ciro-nogueira", "nome": "Ciro Nogueira", "tipo": "pessoa", "casou_por": "texto (FTS)"}]}
  ],
  "outros_erros": []
}
```

Como tratar: para cada item de `nao_resolvidas`, escolha entre as `sugestoes` **somente se for inequivocamente a mesma entidade** (aqui `ciro-nogueira` e `daniel-vorcaro`), corrija e reenvie.
Se nenhuma sugestão serve, a entidade não existe: pare, liste para o humano e **não reenvie** até a decisão. Nunca "resolva" criando ou inventando slug.

## 7. Registrar o MCP

Pré-requisitos (uma vez, na máquina onde o repo está): `pip install --break-system-packages -r mcp/requirements.txt`; `python3 scripts/importar.py` se ainda não existir `data/linha-do-tempo.sqlite`;
`python3 scripts/embeddings.py` para gerar os vetores do RAG (sem isso `buscar_semantica` cai para FTS e o dedup por embedding não age).

**Claude Code** (usar caminhos absolutos):

```bash
claude mcp add linha-do-tempo -- python3 /home/claude/linha-do-tempo/mcp/server.py
# com export JSON automático após cada escrita:
claude mcp add linha-do-tempo -e LDT_EXPORT_JSON=1 -- python3 /home/claude/linha-do-tempo/mcp/server.py
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{ "mcpServers": { "linha-do-tempo": {
    "command": "python3", "args": ["/home/claude/linha-do-tempo/mcp/server.py"],
    "env": { "LDT_EXPORT_JSON": "0" } } } }
```

Ajuste o caminho do repo para o da máquina da sessão do classificador. O servidor roda por stdio, então a sessão precisa estar **na mesma máquina** do repositório.
Variáveis úteis: `LDT_DB`, `LDT_DUMP`, `LDT_EMBED_PROVIDER` (`auto|st|openai|voyage|ollama|hash`), `LDT_EMBED_MODEL`, `LDT_DEDUP_EMBEDDING=0` (desliga a dedup).
Depois de uma sessão de escrita, **avise o humano** para rodar `git add data/ && git commit` (o servidor nunca commita).

## 8. Fluxo recomendado, em ordem

1. Transcrição → trechos atômicos (checklist da seção 5).
2. `buscar_entidade` para cada entidade citada → IDs; pendências em `nao_resolvidas` (seção 2).
3. (Opcional, mas barato) `relacoes_similares(rotulo, de, para)` para cada relação nova; reuse o rótulo existente quando for o mesmo fato.
4. Se não há pendências: `inserir_video`. Se há: devolver ao humano a lista e aguardar.
5. Ler a resposta: `ok`, `relacoes_criadas` × `relacoes_existentes_reutilizadas`, `dedup`, `avisos`, `embeddings`. Relatar ao humano o que foi criado para revisão (`status='revisar'`).
