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

## Branches — `main` é local, `producao` é o que vai ao ar

```
desenvolvimento  →  main       roda local (Postgres + FastAPI 9200 + Next 3100)
                       ↓  merge quando validado
                    producao   o que fica online
```

⚠️ **Ao contrário dos outros projetos da casa, `main` NÃO é produção.** Aqui ela é a base de
trabalho local: é onde se experimenta, se limpa a base, se roda a bateria inteira e se quebra
coisa à vontade. Só o que passou por isso é promovido.

### Regras
- Todo desenvolvimento vai para `main` primeiro — nunca commit direto em `producao`
- `producao` recebe **merge de `main`**, nunca commits próprios: `git checkout producao &&
  git merge main`
- Promover só depois de a bateria passar inteira (API + navegador) na base local
- ⚠️ **Migração nova é o ponto de não retorno.** Ela roda no start da API e reescreve dado;
  antes de promover, conferir que é idempotente e que já rodou aqui sobre base COM dado, não
  só sobre base vazia
- ⚠️ **Configuração não se promove por merge.** `api/.env` está fora do versionamento de
  propósito: `DEBUG`, `CORS_ORIGINS`, `WEB_URL`, `DB_*` e a senha do admin são de cada
  ambiente. O que estiver online tem o `.env` dele

Há remoto (`github.com/melzmarcelo/botane`) e os dois branches estão publicados nele.
`producao` é quem alimenta o que está no ar: **https://sistema.botanedeliecafe.com.br**,
um app no DigitalOcean App Platform.

⚠️ **Push em `producao` NÃO põe no ar.** `deploy_on_push: false` nos dois componentes do
`.do/app.yaml`, de propósito: cada promoção é um ato consciente, feito à mão
(`doctl apps update <id> --spec .do/app.yaml`, ou o botão do painel). O efeito colateral é
que o branch e o ar andam separados, e é normal o segundo ficar para trás sem que nada
avise — conferir sempre com `curl https://sistema.botanedeliecafe.com.br/api/saude`, que
devolve a versão e a última migração aplicada.
⚠️ Já aconteceu de a defasagem passar despercebida: em 08/09/2026 o ar estava em
**1.1.13 / migração 054** enquanto `producao` já tinha 1.1.14 / 057 — as três entregas de
setembro (pessoas, cupom cheio, período de consumo) estavam commitadas e empurradas, mas
não implantadas. Em 10/09/2026 o ar foi para **1.1.15 / migração 061**, alinhado com
`producao`. O id do app, para o `doctl`, sai do cabeçalho `x-do-app-origin` de qualquer
resposta: `0daa9b68-87b6-4d47-8433-77c32e4b9d20`.
⚠️ **`api/verificar_deploy.py` compara a `impressao` do ar com os arquivos DESTE repositório** —
é o que prova que o deploy carregou o commit certo, e não só que o app subiu. As checagens 4 a 7
pedem `--com-login` e senha digitada, então ficam fora de uma rodada automática.

### Preparado para o dia do deploy
- **`.do/app.yaml`** — o app inteiro no DigitalOcean App Platform: web em `/`, API em `/api` e
  Postgres gerenciado. ⚠️ **Mesmo domínio de propósito**: com isso o navegador nunca faz
  requisição entre origens e o CORS deixa de existir como problema. O App Platform remove o
  prefixo antes de repassar, então nada muda no FastAPI — e o service worker já previa isso.
- **`api/verificar_deploy.py`** — doze checagens **só de leitura** contra o que está no ar.
  ⚠️ A suíte de fumaça NÃO serve para produção: ela cria produto, lança nota e grava
  credencial de teste na mesma linha da real.
- ⚠️ **A versão do Python vai em `api/.python-version`, NUNCA em `runtime.txt`** — o buildpack
  da DO recusa o segundo, que foi descontinuado, e o primeiro deploy morre no build. Só o
  número maior (`3.13`), sem prefixo e sem a versão de correção: prender a correção impede o
  app de receber atualização de segurança. O Python online é o mesmo de casa; o Node não
  (local 24, `.nvmrc` 22, que é LTS e o que o `engines` já pedia).
- ⚠️ **Filesystem efêmero no App Platform**: `api/uploads/` (logo) e `api/arquivos/emails/`
  somem a cada deploy. Nada insubstituível, mas a saída definitiva é o Spaces —
  `api/arquivos.py` já foi escrito para essa troca.
- **[`docs/deploy.md`](docs/deploy.md)** — o roteiro: o que decidir, banco, API, web,
  verificação em oito passos, backup e como promover uma versão
- **`api/.env.producao.exemplo`** e **`web/.env.producao.exemplo`** — as variáveis, com o
  porquê de cada uma. `api/.env` continua fora do versionamento
- ⚠️ **`requirements.txt` tem as versões PRESAS** no que passou nos testes. Estava com 10 de
  11 sem `==`: o servidor instalaria o que estivesse mais novo no dia, e a quebra apareceria
  no start, em produção, falando de uma biblioteca que ninguém tocou
- ⚠️ Os três erros que o roteiro antecipa, porque são os que sempre acontecem: **CORS** sem o
  domínio exato (o navegador barra o login e a tela fica muda), **`NEXT_PUBLIC_API` lido na
  compilação** (mudar depois do build não muda nada) e **`WEB_URL` apontando para localhost**
  (o link do e-mail de recuperação chega e não abre)

## Estado

- Mapeamento e **etapas 1 a 6 — a primeira parte inteira** (fundação, cadastros, fichas,
  estoque, Omie e CMV) concluídas em 18 e 19/08/2026.
- Roda local: `.\iniciar_local.ps1`. As credenciais do admin inicial estão em
  `api/.env.example` — e só valem em desenvolvimento.
- ⚠️ **Com `DEBUG=false`, a API RECUSA SUBIR se `ADMIN_EMAIL`/`ADMIN_SENHA` forem as de
  desenvolvimento** (ou a senha for menor que `SENHA_MINIMA`). O primeiro deploy real
  subiu com `admin@botane.com.br` e a senha padrão, porque as variáveis não tinham sido
  definidas no painel — e nada avisou: a linha "administrador criado" saiu igual à de
  sempre. Parar o start é o único aviso que ninguém deixa passar. A trava vale só na
  CRIAÇÃO: sistema que já tem gente dentro não é afetado.
- **O Omie já foi exercitado contra a conta REAL do cliente** (24/08/2026): 37 notas do
  período, 2.183 produtos e 793 fornecedores importados de verdade. Sem credencial, o
  importador cai no **modo simulado** sobre fixtures, e as duas rotas passam pelo mesmo código.
  ⚠️ **A credencial que estava configurada se perdeu** quando a suíte `smoke_omie` estourou no
  meio, depois de gravar a chave de teste na mesma linha (ver `preservar_credenciais`, já
  corrigido) — para voltar ao modo real é preciso redigitar `app_key`/`app_secret` em
  Integrações.


## Os módulos, e a memória de cada um

🔑 **O sistema é pensado por MÓDULO** — área de negócio, não camada. O mapa
completo (rotas, serviços, telas, permissões e suítes de cada um) está em
[`MODULOS.md`](MODULOS.md). ⚠️ Módulo é organização, não pasta: o código continua
em `api/routers/`, `api/services/` e `web/app/(app)/`.

O histórico de decisões e armadilhas NÃO fica neste arquivo (ele passava de 266
mil caracteres e parava de carregar por inteiro). Fica em `docs/memoria/`, **um
arquivo por módulo**. **Antes de mexer num módulo, leia o arquivo dele.**

| Módulo | Memória | O que cobre |
|---|---|---|
| Cadastros | [`cadastros.md`](docs/memoria/cadastros.md) | produtos, pessoas, tabelas de apoio |
| Produção | [`producao.md`](docs/memoria/producao.md) | ficha técnica e produção |
| Compras | [`compras.md`](docs/memoria/compras.md) | notas de entrada |
| Custos | [`custos.md`](docs/memoria/custos.md) | tudo que decide quanto uma coisa custa |
| Estoque | [`estoque.md`](docs/memoria/estoque.md) | saldos, movimentos, ajustes, inventário |
| Vendas | [`vendas.md`](docs/memoria/vendas.md) | vendas, PDV e períodos de consumo |
| Administrativo | [`administrativo.md`](docs/memoria/administrativo.md) | empresa, lojas, parâmetros, integrações, usuários |
| CMV | [`cmv.md`](docs/memoria/cmv.md) | o painel do CMV |

E o que atravessa todos, em [`docs/memoria/_transversais/`](docs/memoria/_transversais/):
`padroes-de-ui.md`, `exportacao-e-relatorios.md`, `infra-e-deploy.md` e `geral.md`.

⚠️ **Esses arquivos não carregam sozinhos no início da sessão** (só o CLAUDE.md da raiz carrega).
Se a tarefa tocar num módulo, abra o arquivo dele antes de editar código — é lá que estão os
"já tentei assim e quebrou".

⚠️ **Decisão nova vai para a memória do módulo DONO da regra**, com ponteiro no outro quando
o recurso cruza módulos (a colheita de EAN nasce em Compras e escreve em Cadastros).

## Stack e portas

| Camada | Escolha | Porta |
|---|---|---|
| Banco | PostgreSQL local (`botane_db`) | 5432 |
| API | FastAPI + psycopg, migrações `.sql` numeradas rodando no start | 9200 |
| Web | Next.js App Router + Tailwind, PWA | 3100 |
| App | Capacitor sobre o mesmo web (fase 8) | — |

As portas acima são as de casa. No ar, web e API dividem o mesmo domínio (a API sob
`/api`) — ver a seção de branches e [`docs/deploy.md`](docs/deploy.md).

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
