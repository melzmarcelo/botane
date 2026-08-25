# Colocar o Botané no ar

Roteiro do primeiro deploy e dos seguintes. Escrito em 25/08/2026, quando ainda **não havia
servidor escolhido** — as decisões estão marcadas como tal, e o resto vale para qualquer
hospedagem.

O sistema tem três peças: **banco** (Postgres), **API** (FastAPI na 9200) e **web** (Next.js
na 3100). As três podem morar em máquinas diferentes.

---

## 0. Antes de tudo: o que decidir

| Decisão | Por quê importa |
|---|---|
| Onde hospedar | Define o resto do roteiro |
| **Postgres gerenciado ou no próprio servidor** | Gerenciado já vem com backup e restauração. Vale o custo: o razão é a memória de todo o custo da casa |
| Domínio | Um para a web, outro para a API (ou a API atrás de `/api` no mesmo) |
| Quem guarda o `JWT_SECRET` | Ele não se troca depois — ver abaixo |

⚠️ **O `JWT_SECRET` é o ponto sem retorno.** Dele sai a chave que cifra as credenciais do Omie
e do SMTP guardadas no banco. Trocá-lo invalida todas, e elas não voltam em claro nem para o
administrador — a única saída é redigitar. Gere uma vez, guarde junto com as senhas.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 0b. Escolhido: DigitalOcean App Platform + GitHub

**`.do/app.yaml`** descreve o app inteiro: web, API e Postgres gerenciado. As seções 1 a 3
abaixo descrevem o que ele faz — leia-as para entender, execute o `app.yaml`.

```bash
doctl apps create --spec .do/app.yaml        # primeira vez
doctl apps update <id> --spec .do/app.yaml   # depois
```

### A decisão que simplifica tudo: um domínio só

Os dois componentes vivem no **mesmo endereço** — a web em `/`, a API em `/api`. Com isso o
navegador nunca faz requisição entre origens, e **o CORS deixa de existir como problema**. Era
o erro nº 1 do primeiro deploy, e some por construção.

O App Platform **remove o prefixo** antes de repassar: o navegador chama `/api/notas` e o
FastAPI recebe `/notas`. Nada muda no código — nem `root_path`, nem prefixo de router. O
service worker já previa isto: ele ignora `/api` explicitamente.

### Antes de rodar o `doctl`

1. **Criar o repositório no GitHub** e apontar `github.repo` no `app.yaml` para ele.
   ⚠️ **Privado.** O repositório não tem segredo (o `.env` está fora), mas tem o modelo de
   dados e a lógica de custo da casa.
2. **Autorizar o App Platform** a ler o repositório (uma vez, pelo painel da DO).
3. **Pôr os três segredos pelo painel**, nunca no arquivo: `JWT_SECRET`, `ADMIN_EMAIL` e
   `ADMIN_SENHA`.

### Depois que subir

```bash
python api/verificar_deploy.py https://<o-endereço-que-a-DO-deu>
```

São doze checagens **só de leitura** — a suíte de fumaça NÃO serve aqui: ela cria produto,
lança nota e chega a gravar credencial de teste na mesma linha da real.

### Três coisas que o App Platform impõe

**O filesystem é efêmero.** `api/uploads/` (a logo da empresa) e `api/arquivos/emails/` (os
`.eml` de quando não há SMTP) **somem a cada deploy**. Nada insubstituível se perde — a logo se
reenvia em dez segundos e o `.eml` é consumido na hora —, mas é preciso saber. A saída
definitiva é o Spaces: `api/arquivos.py` já foi escrito para isso ("quando houver nuvem, só
este módulo muda").

**Um worker no começo.** As migrações rodam no start de **cada** worker. São idempotentes e o
`schema_migrations` segura a repetição, mas com um só dá para ler o log e entender.

**A versão do runtime não é a de casa.** Local roda Python 3.13 e Node 24; o `runtime.txt` e o
`.nvmrc` declaram **3.12** e **22**, que é o que os buildpacks suportam com segurança. É uma
divergência conhecida entre o que foi testado e o que vai rodar — e é por isso que o
`verificar_deploy.py` existe. Se a DO já suportar as versões de casa, prefira-as.

---

## 1. Banco

```sql
CREATE DATABASE botane;
CREATE USER botane WITH PASSWORD '…';
GRANT ALL PRIVILEGES ON DATABASE botane TO botane;
```

**Não rode script de criação de tabela.** O `db_updater` aplica as migrações de
`api/db_scripts/` no start da API, em ordem, por checksum. Banco vazio recebe as 27 de uma vez
e sai pronto — com os papéis de fábrica, as permissões, as unidades de medida e os motivos de
perda.

⚠️ **O administrador nasce no primeiro start**, com `ADMIN_EMAIL` e `ADMIN_SENHA` do `.env`, e
já marcado para trocar a senha no primeiro acesso. Depois disso essas variáveis não fazem mais
nada: mudar ali não muda o usuário que já existe.

---

## 2. API

```bash
git clone <repo> && cd botane/api
git checkout producao          # nunca main: main é a base local
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.producao.exemplo .env  # e preencher
python -c "import config"      # confere que o .env é legível antes de subir
```

Rodar com workers, **sem `--reload`**:

```bash
uvicorn main:app --host 127.0.0.1 --port 9200 --workers 3
```

⚠️ **`--host 127.0.0.1`, não `0.0.0.0`.** A API fica atrás do proxy; exposta direto, ela
responde na porta 9200 sem TLS e sem os cabeçalhos de segurança que o proxy põe.

⚠️ **As migrações rodam no start de CADA worker.** Elas são idempotentes e o `schema_migrations`
segura a repetição, mas suba **um worker primeiro**, confira o log, e só então os demais — é a
diferença entre uma migração que falhou e três falhando ao mesmo tempo.

Serviço (systemd) para reiniciar sozinho, e proxy (nginx/Caddy) para o TLS:

```
api.botane…  →  127.0.0.1:9200
botane…      →  127.0.0.1:3100
```

### A pasta de arquivos
`api/arquivos/` guarda a logo da empresa e os `.eml` gerados quando não há SMTP. Ela **não
está no versionamento**: num servidor efêmero (contêiner que reinicia do zero) esse conteúdo
some a cada deploy. Ou é um volume que persiste, ou vira armazenamento externo.

---

## 3. Web

```bash
cd botane/web
git checkout producao
npm ci
cp .env.producao.exemplo .env.local   # e preencher
npm run build
npm start -- -p 3100
```

⚠️ **`NEXT_PUBLIC_API` é lido na COMPILAÇÃO.** Mudar depois do `build` não muda nada — tem de
compilar de novo. É o segundo erro mais comum de deploy, atrás do CORS.

---

## 4. Verificar, na ordem

Cada item falha de um jeito diferente. Vale rodar todos, e nesta ordem:

1. `curl https://api.…/saude` → **200**
2. Log da API mostra as migrações aplicadas e `API … pronta`
3. Abrir a web e **fazer login** — se o navegador barrar com erro de CORS, é o
   `CORS_ORIGINS` sem o domínio exato (com `https://`, sem barra no fim)
4. Cadastrar um local de estoque — sem ele nenhum movimento entra
5. Entrar em **Ajuda**: prova que o estático (`public/`) está sendo servido
6. Pedir recuperação de senha e conferir o LINK do e-mail: se apontar para
   `localhost`, é o `WEB_URL`
7. Instalar o PWA pelo navegador — só funciona em HTTPS
8. Configurar SMTP e Omie pela tela de **Integrações** (não vão no `.env`)

---

## 5. Backup — antes de existir dado, não depois

O razão é **append-only**: correção é estorno, nunca alteração. Isso o torna auditável e
**não** o torna recuperável. Sem backup, um banco perdido é o custo inteiro da casa perdido.

```bash
pg_dump --format=custom --no-owner "$DATABASE_URL" > botane-$(date +%F).dump
```

O mínimo aceitável:
- **diário**, automático, e guardado **fora** do servidor que roda o banco
- **restauração testada** ao menos uma vez — backup que nunca foi restaurado é hipótese
- retenção de 30 dias, para o erro que só se descobre no fechamento do mês

Com Postgres gerenciado isso costuma vir pronto: confira **retenção** e **como se restaura**,
não só se a caixinha está marcada.

---

## 6. Promover uma versão

```bash
git checkout producao && git merge main
```

Do lado do servidor:

```bash
git pull                       # já em producao
# API:  pip install -r requirements.txt  →  reiniciar o serviço (migrações rodam no start)
# Web:  npm ci && npm run build          →  reiniciar
```

⚠️ **Backup ANTES de promover**, sempre que a versão traz migração nova. Migração roda no
start e reescreve dado: as 024 e 025 desta base consertaram R$ 74 de frete contado em dobro —
se estivessem erradas, teriam feito o contrário, e sem backup não haveria volta.

### Voltar atrás
Código volta com `git checkout <commit anterior>` e novo build. **Migração não volta** — ela
não tem desfazer. Por isso a regra: toda migração é idempotente e é exercitada aqui, sobre
base COM dado, antes de ir.

---

## 7. O que não fazer

- Commitar em `producao` — ela só recebe merge de `main`
- Levar o `.env` de um ambiente para o outro
- Trocar o `JWT_SECRET` de um sistema que já tem credencial guardada
- Rodar `api/limpar_dados.py` apontando para o banco online (ele **recusa** host que não seja
  local — mas não conte com isso como única proteção)
- Promover sem a bateria de testes ter passado na base local
