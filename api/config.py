"""Configuração lida do .env. Nada de segredo com valor padrão em produção."""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- banco ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_DATABASE", "botane_db")
DB_SSLMODE = os.getenv("DB_SSLMODE", "prefer")

SCRIPTS_DIR = os.path.join(BASE_DIR, "db_scripts")

# --- sessão ---
# ⚠️ **O padrão está aqui para o desenvolvimento funcionar sem `.env`, e só.**
# Fora dele, `conferir_segredo()` recusa o start — ver `main.py`. O nome da
# constante existe para a trava poder comparar sem repetir a string.
JWT_SECRET_PADRAO = "troque-este-valor-no-env"
JWT_SECRET = os.getenv("JWT_SECRET", JWT_SECRET_PADRAO)
# Mínimo defensivo, não recomendação: o roteiro de deploy manda gerar 48 bytes
# com `secrets.token_urlsafe(48)`. Isto só barra o que é curto demais para
# assinar qualquer coisa.
JWT_SECRET_MINIMO = 24
# 🔑 **O segredo ANTERIOR, só para a troca.** O `JWT_SECRET` deriva a chave que
# cifra as credenciais de integração (`services/segredos.py`): trocá-lo deixava
# Omie, PDV e a senha de SMTP ilegíveis, para serem redigitados à mão. Com esta
# variável definida, o start regrava cada credencial com a chave nova e a casa
# não perde nada.
# ⚠️ **É temporária, e o start diz isso.** Ela existe durante UM deploy; deixada
# para trás, mantém um segredo aposentado vivo na configuração do ambiente —
# que é metade do motivo de estar sendo trocado.
JWT_SECRET_ANTERIOR = os.getenv("JWT_SECRET_ANTERIOR", "")
# Token curto de propósito: quem some da equipe perde acesso rápido.
JWT_EXPIRY_MIN = int(os.getenv("JWT_EXPIRY_MIN", "60"))
REFRESH_EXPIRY_DIAS = int(os.getenv("REFRESH_EXPIRY_DIAS", "30"))
# Sessão de quem NÃO marcou "manter conectado". O token morre com o navegador
# (o front guarda em sessionStorage), mas o servidor não pode confiar nisso: a
# validade curta é o que garante que um refresh copiado não sirva por um mês.
REFRESH_SESSAO_HORAS = int(os.getenv("REFRESH_SESSAO_HORAS", "12"))
# ⚠️ Folga para o refresh ROTATIVO. Duas abas (ou duas chamadas que escapem da
# trava do front) apresentam o mesmo token: a primeira rotaciona e revoga, a
# segunda chegaria com token morto e derrubaria a sessão de quem não fez nada
# errado. Dentro desta janela o token recém-revogado ainda é aceito.
REFRESH_GRACA_SEGUNDOS = int(os.getenv("REFRESH_GRACA_SEGUNDOS", "30"))
MAX_TENTATIVAS_LOGIN = int(os.getenv("MAX_TENTATIVAS_LOGIN", "5"))
BLOQUEIO_MINUTOS = int(os.getenv("BLOQUEIO_MINUTOS", "15"))

# --- servidor ---
# 🔑 **O fuso da CASA, e não o do contêiner** (04/09/2026). O agendador
# perguntava a hora ao sistema operacional (`datetime.now().astimezone()`), e no
# App Platform o contêiner roda em **UTC**: quem configurava "buscar às 20h"
# tinha a busca disparada às 20h UTC, que são 17h em Brasília — e nunca achava
# registro no horário que escolheu.
#
# ⚠️ **É invisível em desenvolvimento**, porque a máquina de casa está no mesmo
# fuso que o sistema presumia. Nenhuma suíte pegaria: todas rodam local.
#
# ⚠️ O banco já resolvia isso do lado dele (`database.py` abre a sessão em
# America/Sao_Paulo); faltava o processo Python fazer o mesmo.
FUSO_DA_CASA = os.getenv("FUSO_DA_CASA", "America/Sao_Paulo")

PORT = int(os.getenv("PORT", "9200"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3100").split(",") if o.strip()
]

# --- endereço do sistema ---
# Entra no link do e-mail de recuperação de senha. O primeiro CORS_ORIGINS é o
# padrão razoável: é justamente de onde o navegador do usuário fala com a API.
WEB_URL = os.getenv("WEB_URL", (CORS_ORIGINS[0] if CORS_ORIGINS else "http://localhost:3100"))

# Quanto tempo o link de recuperação vale, e quantos pedidos cabem por hora.
SENHA_TOKEN_MINUTOS = int(os.getenv("SENHA_TOKEN_MINUTOS", "30"))
SENHA_PEDIDOS_HORA = int(os.getenv("SENHA_PEDIDOS_HORA", "3"))

# Tamanho mínimo de senha, em UM lugar só.
#
# Vale para o administrador que nasce no primeiro start, para a troca de senha,
# para a redefinição por e-mail e para a senha que o admin define ao cadastrar
# alguém. Antes o número estava escrito quatro vezes no Python e mais quatro no
# front — e o do start era 12 enquanto o dos formulários era 8, então uma senha
# aceita na criação era recusada na primeira troca obrigatória.
#
# ⚠️ Curto o bastante para caber na cabeça é curto o bastante para ser
# adivinhado: seis caracteres são poucos milhões de combinações, e o sistema
# está na internet. Quem subir esse número aqui sobe em todo lugar.
SENHA_MINIMA = 6

# --- primeiro acesso ---
# Só é usado quando a tabela de usuários está vazia.
# ⚠️ São os valores de DESENVOLVIMENTO, e estão escritos no README — que é
# público. `garantir_admin` recusa subir com eles quando `DEBUG` está desligado.
ADMIN_EMAIL_PADRAO = "admin@botane.com.br"
ADMIN_SENHA_PADRAO = "botane123"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", ADMIN_EMAIL_PADRAO)
ADMIN_SENHA = os.getenv("ADMIN_SENHA", ADMIN_SENHA_PADRAO)
ADMIN_NOME = os.getenv("ADMIN_NOME", "Administrador")
