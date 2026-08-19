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

# --- primeiro acesso ---
# Só é usado quando a tabela de usuários está vazia.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@botane.com.br")
ADMIN_SENHA = os.getenv("ADMIN_SENHA", "botane123")
ADMIN_NOME = os.getenv("ADMIN_NOME", "Administrador")
