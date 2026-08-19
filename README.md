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

## Começar do zero

Para percorrer o fluxo como o cliente vai percorrer — ou para preparar a base
antes de entregar:

```
cd api
python limpar_dados.py --simular    # mostra o que sairia, sem apagar
python limpar_dados.py              # apaga (pede confirmação digitada)
python limpar_dados.py --so-o-admin # e deixa só o administrador na equipe
python limpar_dados.py --tabelas-de-apoio   # zera setores, locais e categorias
```

⚠️ `--tabelas-de-apoio` deixa a base **mais vazia que uma instalação nova** (o seed
cria setores, locais e categorias). Sem local de estoque, nenhum movimento entra
até alguém criar o primeiro. As unidades de medida ficam sempre: elas sustentam
toda conversão de embalagem.

Sai tudo que é operação (produtos, fornecedores, fichas, razão de estoque,
notas, vendas, inventários). Fica o cadastro base (empresa, loja, parâmetros,
locais, setores, categorias, unidades de medida, motivos de perda) e o acesso
inteiro. O script **se recusa a rodar** se o banco não for local.

## Testes

| O quê | Comando |
|---|---|
| API (login, permissão, refresh, auditoria) | `cd api && python tests/smoke_fundacao.py` |
| API — cadastros (produtos, fornecedores, árvore de categorias) | `cd api && python tests/smoke_cadastros.py` |
| API — fichas técnicas (custo em cascata, ciclo, permissão de custo) | `cd api && python tests/smoke_fichas.py` |
| API — estoque (custo médio, estorno, inventário, produção) | `cd api && python tests/smoke_estoque.py` |
| API — CMV (apuração, ABC, margem, fechamento) | `cd api && python tests/smoke_cmv.py` |
| API — Omie (importação, de-para, rateio, estorno) | `cd api && python tests/smoke_omie.py` |
| API — notas sem integração (XML da NF-e e digitação) | `cd api && python tests/smoke_notas.py` |
| API — alertas e exportação em CSV | `cd api && python tests/smoke_alertas.py` |
| API — kit/combo (custo somado, ficha vigente, ciclo) | `cd api && python tests/smoke_kits.py` |
| API — relatórios do dono (CMV por setor, evolução de preço) | `cd api && python tests/smoke_relatorios.py` |
| API — FEFO (lote na saída, estorno, alerta que não mente) | `cd api && python tests/smoke_lotes.py` |
| API — recuperação de senha (token, sessões, SMTP) | `cd api && python tests/smoke_senha.py` |
| Regras de cache do service worker (sem navegador) | `cd web && node scripts/testar-sw.mjs` |
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
- **Etapa 6 — CMV:** concluída em 19/08/2026 — painel real × teórico, variância, curva ABC,
  margem por prato, importação de vendas e fechamento de período
- **Etapa 5 — Omie:** concluída em 19/08/2026 — importação de notas, de-para em cascata,
  rateio de frete, lançamento no estoque e conferência com o CMC. Roda em **modo simulado**
  até a credencial do cliente chegar
- **Notas sem integração:** concluída em 19/08/2026 — a nota entra por **três portas** (XML
  da NF-e, digitação e Omie) e segue o mesmo caminho até o razão. A casa opera inteira sem
  depender de credencial de ninguém
- **PWA:** concluída em 19/08/2026 — instala na tela inicial do celular (ícone próprio,
  tela cheia, atalhos para inventário e alertas) e avisa quando fica sem sinal. Sem loja de
  aplicativos
- **Recuperação de senha:** concluída em 19/08/2026 — "esqueci minha senha" por e-mail, com
  link de 30 minutos e uso único; sem SMTP configurado o administrador gera o link na tela de
  Usuários
- **FEFO:** concluído em 19/08/2026 — a saída escolhe o lote que vence primeiro, o saldo por
  lote passa a diminuir (o alerta de vencimento parou de mentir) e o estorno volta para o
  mesmo lote
- **Relatórios do dono:** concluídos em 19/08/2026 — CMV por setor e por categoria (a soma
  fecha com o total) e evolução de preço por insumo, ordenada pelo impacto em reais, com a
  planilha para levar ao fornecedor
- **Kit/combo:** concluído em 19/08/2026 — o combo do PDV deixa de entrar sem custo no CMV
  teórico: a composição aponta para produtos e cada um custa pela regra dele
- **A primeira parte está completa.** O que segue são as fases 2 em diante do mapeamento.
