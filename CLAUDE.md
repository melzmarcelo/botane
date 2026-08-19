# Botane — guia para Claude Code

Sistema de gestão para café/restaurante, sob encomenda, construído **por partes**.
Projeto **independente** do Gestor Civil (o `D:\dsv\CLAUDE.md` do diretório acima é
de outro sistema — não vale aqui, exceto pelos padrões de código citados abaixo).

**Antes de qualquer coisa, leia [`MAPEAMENTO.md`](MAPEAMENTO.md)** — é o documento-fonte:
escopo, modelo de dados, regras de negócio, permissões, integração Omie e ordem de
construção. Rascunho do DDL em `docs/schema_draft.sql`.
Apresentação para o cliente: `apresentacao/index.html` (arquivo local, autocontido;
só as fontes vêm da internet). Publicada também como artifact — republicar sempre com a
mesma URL para não criar link novo.

⚠️ **Tudo deste projeto mora no D:.** Não usar o scratchpad da sessão (`%TEMP%`, que fica no C:)
para arquivo nenhum — gravar direto aqui.

## Estado

- Fase 0 (mapeamento) e **etapa 1 (fundação) concluídas em 18/08/2026**.
- Roda local: `.\iniciar_local.ps1`. Admin inicial `admin@botane.com.br` / `botane123`.
- **Próxima: etapa 2 — cadastros** (produtos, categorias, setores, locais, UM, fornecedores).

### O que já existe
- `api/` FastAPI: `database.py` (pool, sessão em America/Sao_Paulo), `db_updater.py`
  (migrações por checksum — **todo script tem de ser idempotente**), `seguranca.py`
  (bcrypt, JWT, refresh rotativo com hash no banco, `requer_permissao`),
  `auditoria.py` (grava no MESMO cursor da operação e filtra senha/credencial).
- `api/db_scripts/`: 001 acesso+empresa, 002 permissões e papéis de fábrica, 003 empresa inicial.
- `web/` Next.js 16 (App Router): `lib/api.ts` (cliente único, renova o token sozinho),
  `lib/sessao.tsx` (contexto + `pode()`), telas de início, empresa, lojas, usuários, papéis,
  auditoria e troca de senha.
- Testes: `api/tests/smoke_fundacao.py` (35 checagens) e `web/scripts/verificar.mjs`
  (15 checagens no Chrome, com fotos em `web/scripts/_fotos`).

### Armadilhas já pagas
- **`allowedDevOrigins` no `next.config.mjs`**: sem isso o dev server do Next devolve **403
  nos chunks** quando a página é aberta por `127.0.0.1` (ou pelo IP, no teste em celular).
  A tela renderiza, nunca hidrata, e o formulário vira submit nativo — parece bug de login.
- **`EmailStr` recusa domínio `.local`** (reservado). Por isso o admin é `@botane.com.br`.
- Componente `Aviso` renderiza `<p>`: não colocar dentro de outro `<p>` (erro de hidratação).

## Stack e portas

| Camada | Escolha | Porta |
|---|---|---|
| Banco | PostgreSQL local (`botane_db`) | 5432 |
| API | FastAPI + psycopg, migrações `.sql` numeradas rodando no start | 9200 |
| Web | Next.js App Router + Tailwind, PWA | 3100 |
| App | Capacitor sobre o mesmo web (fase 8) | — |

Não há deploy: o projeto roda só local nesta primeira parte.

## Regras que valem para todo código deste repositório

1. `estoque_movimentos` é **append-only**. Correção é estorno, nunca `UPDATE`/`DELETE`.
2. Dinheiro e quantidade em `numeric` (custo unitário com 6 casas), **jamais float**.
3. Só o service de estoque escreve no razão, sempre com `SELECT … FOR UPDATE` no saldo.
4. Toda rota declara a permissão que exige; nada de checagem só na tela.
5. Toda tabela de movimento carrega `id_unidade` (multi-loja desde o início).
6. Banco em UTC, sessão em `America/Sao_Paulo`.
7. Ficha técnica é versionada; o custo é congelado no momento do uso.
8. Idempotência de importação é do **banco** (índice único), nunca do gatilho.

## Padrões herdados dos outros projetos da casa

- Migração `.sql` numerada e idempotente, executada no start da API
- Router FastAPI protegido por dependência de permissão; nada de `body: dict` (Pydantic)
- Front com camada de service — nenhuma chamada de API crua dentro da página
- Service worker do PWA **nunca** cacheia `/api`
