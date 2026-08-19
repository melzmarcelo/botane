# Botane — Sistema de Gestão para Café/Restaurante

Sistema sob encomenda, construído **por partes**. A primeira parte é o **CMV**
(Custo de Mercadoria Vendida) e a base cadastral que o sustenta.

- **Mapeamento completo:** [`MAPEAMENTO.md`](MAPEAMENTO.md) — leia antes de escrever código
- **Rascunho do modelo de dados:** [`docs/schema_draft.sql`](docs/schema_draft.sql)
- **Integração Omie (notas fiscais):** seção 8 do mapeamento
- **Apresentação (página local):** [`apresentacao/index.html`](apresentacao/index.html) —
  abra com dois cliques, ou `.presentacaobrir.ps1` (use `-Servir` para subir em
  `http://127.0.0.1:8899`). A mesma página está publicada em
  https://claude.ai/code/artifact/f50546a2-e117-4f8a-a83c-fa948e9a8951

## Stack (decidida em 18/08/2026)

| Camada | Escolha | Pasta |
|---|---|---|
| Banco | PostgreSQL local | `db/` (migrações em `api/migrations/`) |
| API | FastAPI + psycopg | `api/` |
| Web | Next.js (App Router) + Tailwind, PWA instalável | `web/` |
| App de loja | Capacitor embrulhando o mesmo web (fase 7) | `app/` |

Custeio do estoque: **custo médio ponderado móvel**.

## Como subir (local)

```powershell
.\iniciar_local.ps1              # API 9200 + web 3100
.\iniciar_local.ps1 -Verificar   # roda os dois testes com tudo de pé
```

Primeiro acesso: **admin@botane.com.br / botane123** — o sistema obriga a troca.
Banco `botane_db` no Postgres local; as migrações rodam sozinhas no start da API.

- API e documentação: <http://localhost:9200/docs>
- Web: <http://localhost:3100>

## Testes

| O quê | Comando |
|---|---|
| API (login, permissão, refresh, auditoria) | `cd api && python tests/smoke_fundacao.py` |
| API — cadastros (produtos, fornecedores, árvore de categorias) | `cd api && python tests/smoke_cadastros.py` |
| API — fichas técnicas (custo em cascata, ciclo, permissão de custo) | `cd api && python tests/smoke_fichas.py` |
| API — estoque (custo médio, estorno, inventário, produção) | `cd api && python tests/smoke_estoque.py` |
| Telas no Chrome de verdade, com fotos | `cd web && node scripts/verificar.mjs` |

## Status

- **Etapa 0 — mapeamento:** concluída em 18/08/2026
- **Etapa 1 — fundação:** concluída em 18/08/2026 — banco, migrações, login com JWT +
  refresh rotativo, papéis e permissões por chave, empresa, lojas e parâmetros, auditoria,
  e as telas correspondentes
- **Etapa 2 — cadastros:** concluída em 19/08/2026 — produtos, fornecedores, categorias em
  árvore, setores, locais de estoque e unidades de medida
- **Etapa 3 — fichas técnicas:** concluída em 19/08/2026 — sub-ficha em cascata, fator de
  correção, custo por porção, versão com homologação
- **Etapa 4 — estoque:** concluída em 19/08/2026 — razão append-only, custo médio móvel,
  perdas com motivo, transferência, produção pela ficha e inventário
- **Etapa 5 — Omie / etapa 6 — CMV:** as próximas
