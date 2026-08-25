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
JWT_SECRET = os.getenv("JWT_SECRET", "troque-este-valor-no-env")
# Token curto de propósito: quem some da equipe perde acesso rápido.
JWT_EXPIRY_MIN = int(os.getenv("JWT_EXPIRY_MIN", "60"))
REFRESH_EXPIRY_DIAS = int(os.getenv("REFRESH_EXPIRY_DIAS", "30"))
MAX_TENTATIVAS_LOGIN = int(os.getenv("MAX_TENTATIVAS_LOGIN", "5"))
BLOQUEIO_MINUTOS = int(os.getenv("BLOQUEIO_MINUTOS", "15"))

# --- servidor ---
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
