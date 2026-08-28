"""Botané Deli e Café — API da fase 1 (fundação).

Sobe o pool, roda as migrações e garante que exista um administrador.
"""

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import validate_email
from pydantic_core import PydanticCustomError

import arquivos
from services.omie import agenda as agenda_omie
from services.pdv import agenda as agenda_pdv
import impressao
from config import (
    ADMIN_EMAIL,
    ADMIN_EMAIL_PADRAO,
    ADMIN_NOME,
    ADMIN_SENHA,
    ADMIN_SENHA_PADRAO,
    CORS_ORIGINS,
    DEBUG,
    PORT,
    SENHA_MINIMA,
)
from database import close_pool, get_cursor, init_pool
from db_updater import run_migrations
from routers import (
    ajustes,
    alertas,
    autenticacao,
    cadastros,
    cmv,
    email_config,
    empresa,
    estoque,
    exportacoes,
    fichas,
    fornecedores,
    historico,
    inicio,
    inventario,
    notas,
    omie,
    papeis,
    pdv,
    producao_agenda,
    produtos,
    usuarios,
    vendas,
)
from seguranca import hash_senha

VERSAO = "0.1.0"


def garantir_admin() -> None:
    """Primeiro acesso: sem nenhum usuário, cria o administrador do .env.

    ⚠️ **Fora de desenvolvimento, recusa subir com a senha padrão.** Ela está
    escrita no README, que é público — e o primeiro deploy real subiu com ela
    porque as variáveis não tinham sido definidas no painel. O sistema ficou na
    internet com senha de administrador conhecida, e nada avisou: a linha
    "administrador criado" saiu igual à de sempre.

    ⚠️ **E recusa e-mail que não seja e-mail.** O segundo deploy subiu com o
    marcador `DEFINA_NO_PAINEL` copiado do `app.yaml` para as duas variáveis:
    passou nas conferências acima (não é o valor padrão, e tem 16 caracteres) e
    criou um administrador com login `defina_no_painel`. A conta nasceu MORTA —
    `LoginRequest.email` é `EmailStr`, então o pedido morre na validação, com
    422, antes de chegar ao banco. Ninguém nunca ia entrar, e a única saída era
    apagar a linha direto no Postgres. Por isso a conferência usa a MESMA regra
    do login: se não passar aqui, não passaria lá.

    Parar o start é o único aviso que ninguém deixa passar. E vale só na
    criação: sistema que já tem gente dentro não é afetado.
    """
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM usuarios")
        if cur.fetchone()["n"]:
            return

        if not DEBUG:
            faltando = []
            if ADMIN_SENHA == ADMIN_SENHA_PADRAO:
                faltando.append("ADMIN_SENHA")
            if ADMIN_EMAIL == ADMIN_EMAIL_PADRAO:
                faltando.append("ADMIN_EMAIL")
            if len(ADMIN_SENHA) < SENHA_MINIMA:
                faltando.append(
                    f"ADMIN_SENHA (curta demais: mínimo {SENHA_MINIMA} caracteres)")
            # O marcador do `app.yaml` está no repositório: é senha publicada,
            # igual à do README, e o tamanho dele engana a conferência acima.
            if ADMIN_SENHA.strip().upper() == "DEFINA_NO_PAINEL":
                faltando.append("ADMIN_SENHA (é o marcador do app.yaml, que está no repositório)")
            try:
                validate_email(ADMIN_EMAIL)
            except (PydanticCustomError, ValueError):
                faltando.append(f"ADMIN_EMAIL ({ADMIN_EMAIL!r} não é um endereço de e-mail — "
                                "seria uma conta impossível de usar: o login recusa na validação)")
            if faltando:
                raise RuntimeError(
                    "Recusando criar o administrador com valor de desenvolvimento: "
                    + ", ".join(faltando)
                    + ". Defina essas variáveis no ambiente e suba de novo — a senha padrão "
                    "está escrita no README, que é público."
                )

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

    # ⚠️ **Os agendadores sobem SEMPRE; quem decide é a configuração.** O padrão
    # de `agenda_frequencia` é MANUAL, então numa casa que não ligou nada estes
    # laços acordam de minuto em minuto, fazem uma consulta com índice e voltam
    # a dormir. Ligar ou desligar não exige reiniciar a API — se o laço só
    # subisse quando houvesse agenda, mudar a configuração pediria um restart, e
    # ninguém lembraria disso.
    #
    # ⚠️ **Dois laços separados, não um.** As integrações falham por motivos
    # diferentes e em momentos diferentes; um laço só faria a busca de notas
    # esperar a de vendas terminar — e um erro no meio derrubaria as duas.
    parar = asyncio.Event()
    tarefas = [asyncio.create_task(agenda_omie.laco(parar)),
               asyncio.create_task(agenda_pdv.laco(parar))]

    print(f"[botane] API {VERSAO} pronta em http://localhost:{PORT}")
    yield

    # ⚠️ Avisa e ESPERA. Sem o `await`, o processo morre no meio de uma busca e
    # a transação fica para o Postgres desfazer — com o advisory lock preso até
    # a conexão cair, o que atrasa a próxima instância.
    parar.set()
    for tarefa in tarefas:
        try:
            await asyncio.wait_for(tarefa, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            tarefa.cancel()
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
    # Sem isto o navegador não deixa o front ler o nome do arquivo exportado:
    # em requisição de outra origem, só os cabeçalhos expostos são visíveis.
    # X-Total sustenta a paginação: sem expor, o navegador não o entrega à tela.
    expose_headers=["Content-Disposition", "X-Total"],
)

# Imagens enviadas pela tela (logo). Local por enquanto.
# A pasta precisa existir ANTES do mount — o StaticFiles confere no import.
arquivos.garantir_pasta()
app.mount(arquivos.PREFIXO_URL, StaticFiles(directory=arquivos.PASTA), name="arquivos")

app.include_router(autenticacao.router)
app.include_router(usuarios.router)
app.include_router(papeis.router)
app.include_router(empresa.router)
app.include_router(email_config.router)
app.include_router(historico.router)
app.include_router(cadastros.router)
app.include_router(fornecedores.router)
app.include_router(produtos.router)
app.include_router(fichas.router)
app.include_router(estoque.router)
app.include_router(inventario.router)
app.include_router(vendas.router)
app.include_router(cmv.router)
app.include_router(notas.router)
app.include_router(omie.router)
app.include_router(pdv.router)
app.include_router(producao_agenda.router)
app.include_router(inicio.router)
app.include_router(ajustes.router)
app.include_router(alertas.router)
app.include_router(exportacoes.router)


@app.get("/saude", tags=["infra"])
def saude() -> dict:
    """Diz que está de pé — e QUAL código está de pé.

    ⚠️ A `versao` é fixa no código e não distingue um deploy do outro. Quem
    responde "o que subiu é o que eu publiquei?" é a `impressao`: o mesmo
    cálculo roda na máquina de quem publicou (`python -c "import impressao;
    print(impressao.CODIGO)"`, de dentro de `api/`) e os dois se comparam.
    Sem isso não dava para separar "a correção não funcionou" de "a correção
    não foi publicada".

    A última migração aplicada vai junto porque é a outra metade da mesma
    pergunta: código novo com migração pendente é um estado real, e ele
    aparece aqui em vez de virar erro estranho numa tela qualquer.
    """
    with get_cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        cur.fetchone()
        cur.execute(
            "SELECT script_name FROM schema_migrations ORDER BY script_name DESC LIMIT 1")
        linha = cur.fetchone()
    return {"status": "ok", "versao": VERSAO,
            "migracao": (linha or {}).get("script_name"),
            **impressao.CODIGO}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=DEBUG)
