"""Botané Deli e Café — API da fase 1 (fundação).

Sobe o pool, roda as migrações e garante que exista um administrador.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import arquivos
from config import ADMIN_EMAIL, ADMIN_NOME, ADMIN_SENHA, CORS_ORIGINS, DEBUG, PORT
from database import close_pool, get_cursor, init_pool
from db_updater import run_migrations
from routers import (
    autenticacao,
    cadastros,
    cmv,
    empresa,
    estoque,
    fichas,
    fornecedores,
    historico,
    inventario,
    omie,
    papeis,
    produtos,
    usuarios,
    vendas,
)
from seguranca import hash_senha

VERSAO = "0.1.0"


def garantir_admin() -> None:
    """Primeiro acesso: sem nenhum usuário, cria o administrador do .env."""
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM usuarios")
        if cur.fetchone()["n"]:
            return
        cur.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, ativo, trocar_senha)
               VALUES (%s, %s, %s, true, true) RETURNING id""",
            (ADMIN_NOME, ADMIN_EMAIL.lower(), hash_senha(ADMIN_SENHA)),
        )
        id_usuario = cur.fetchone()["id"]
        cur.execute("SELECT id FROM papeis WHERE nome = 'Administrador'")
        papel = cur.fetchone()
        if papel:
            # id_unidade NULL = vale em todas as lojas, inclusive nas que ainda não existem.
            cur.execute(
                "INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade) VALUES (%s, %s, NULL)",
                (id_usuario, papel["id"]),
            )
    print(f"[botane] administrador criado: {ADMIN_EMAIL} (troque a senha no primeiro acesso)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    arquivos.garantir_pasta()
    run_migrations()
    garantir_admin()
    print(f"[botane] API {VERSAO} pronta em http://localhost:{PORT}")
    yield
    close_pool()


app = FastAPI(
    title="Botané Deli e Café · API",
    version=VERSAO,
    description="Base cadastral e CMV para café/restaurante.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Imagens enviadas pela tela (logo). Local por enquanto.
# A pasta precisa existir ANTES do mount — o StaticFiles confere no import.
arquivos.garantir_pasta()
app.mount(arquivos.PREFIXO_URL, StaticFiles(directory=arquivos.PASTA), name="arquivos")

app.include_router(autenticacao.router)
app.include_router(usuarios.router)
app.include_router(papeis.router)
app.include_router(empresa.router)
app.include_router(historico.router)
app.include_router(cadastros.router)
app.include_router(fornecedores.router)
app.include_router(produtos.router)
app.include_router(fichas.router)
app.include_router(estoque.router)
app.include_router(inventario.router)
app.include_router(vendas.router)
app.include_router(cmv.router)
app.include_router(omie.router)


@app.get("/saude", tags=["infra"])
def saude() -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        cur.fetchone()
    return {"status": "ok", "versao": VERSAO}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=DEBUG)
