"""Chaves de acesso de máquina — o que o conector MCP usa para entrar.

🔑 **A chave age COMO o usuário dono dela.** Criar uma para alguém é dar a um
programa o alcance dessa pessoa; por isso a rota mora sob `admin.usuarios`, e
as mesmas travas de loja do cadastro valem aqui.
"""

from fastapi import APIRouter, Depends, HTTPException

import auditoria
from database import get_cursor
from models.acesso import TokenApiCreate, TokenApiCriado, TokenApiResponse
from seguranca import (Contexto, carregar_contexto, contexto_atual, gerar_token_api,
                       requer_permissao)

router = APIRouter(prefix="/usuarios/{id_usuario}/tokens", tags=["chaves de acesso"])


def _so_por_login(ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> Contexto:
    """Chave não gere chave.

    🔑 Uma chave que pudesse criar outra se tornaria imortal: revogada, ela já
    teria deixado a sucessora. Hoje a chave é só de leitura e a trava do método
    já barraria o POST — mas a LISTA também fica de fora, e a fase de escrita
    não pode herdar o buraco por esquecimento.
    """
    if ctx.id_token is not None:
        raise HTTPException(status_code=403,
                            detail="Chaves de acesso só se gerem entrando pelo sistema.")
    return ctx


def _conferir_alcance(cur, id_usuario: int, ctx: Contexto, criando: bool = False) -> dict:
    """O usuário existe, está ativo e não enxerga loja que quem gera não enxerga.

    🔑 **É a trava de `_conferir_lojas`, pela outra ponta.** Lá, ninguém põe
    outra pessoa numa loja que não vê; aqui, ninguém ganha uma chave que abre
    loja que não vê. Sem isso, o gerente da filial geraria a chave do dono e
    passaria a ler a matriz pelo Claude.
    """
    cur.execute("SELECT nome, ativo FROM usuarios WHERE id = %s", (id_usuario,))
    u = cur.fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    # ⚠️ Inativo só não RECEBE chave. Listar e revogar continuam valendo: as
    # chaves dele já não abrem nada (`carregar_contexto` recusa inativo), mas
    # quem reativar a pessoa precisa poder ver e matar o que ficou.
    if criando and not u["ativo"]:
        raise HTTPException(status_code=400, detail="Usuário inativo não recebe chave de acesso")
    # ⚠️ Lido direto dos vínculos, e não por `carregar_contexto`: aquele recusa
    # usuário inativo com 403, e aí nem a lista das chaves dele abriria.
    # Mesma leitura do servidor: basta UM vínculo sem loja para valer em todas.
    cur.execute("SELECT id_unidade FROM usuario_papeis WHERE id_usuario = %s", (id_usuario,))
    lojas = [r["id_unidade"] for r in cur.fetchall()]
    alvo_todas = any(x is None for x in lojas)
    if not ctx.todas_unidades and (alvo_todas or not set(lojas) <= ctx.unidades):
        raise HTTPException(
            status_code=403,
            detail=(f"{u['nome']} enxerga lojas que você não enxerga — a chave dele "
                    "abriria o que você mesmo não pode abrir."))
    return u


# ⚠️ `vence_em` e não `expira_em` para a tela: na conexão do Claude a chave vive
# uma hora e se renova sozinha — quem manda no fim da conexão é a renovação.
# Mostrar `expira_em` pintaria de "vencida" toda conexão parada há uma hora.
_COLUNAS = """t.id, t.nome, t.prefixo, t.somente_leitura, t.expira_em, t.criado_em,
              c.nome AS criado_por, t.ultimo_uso_em, t.revogado_em, t.origem,
              coalesce(t.refresh_expira_em, t.expira_em) AS vence_em"""


@router.get("", response_model=list[TokenApiResponse])
def listar(id_usuario: int, ctx: Contexto = Depends(_so_por_login)) -> list[dict]:
    """As chaves do usuário, vivas primeiro. Revogadas ficam, para a história."""
    with get_cursor() as cur:
        _conferir_alcance(cur, id_usuario, ctx)
        cur.execute(
            f"""SELECT {_COLUNAS}
                  FROM tokens_api t LEFT JOIN usuarios c ON c.id = t.criado_por
                 WHERE t.id_usuario = %s
                 ORDER BY (t.revogado_em IS NULL
                           AND coalesce(t.refresh_expira_em, t.expira_em) > now()) DESC,
                          t.criado_em DESC""",
            (id_usuario,),
        )
        return cur.fetchall()


@router.post("", response_model=TokenApiCriado, status_code=201)
def criar(id_usuario: int, body: TokenApiCreate,
          ctx: Contexto = Depends(_so_por_login)) -> dict:
    valor, prefixo, hashed = gerar_token_api()
    with get_cursor() as cur:
        _conferir_alcance(cur, id_usuario, ctx, criando=True)
        if not body.somente_leitura:
            # 🔑 **Chave que altera é para quem já pode conectar o Claude.** A
            # permissão é a mesma porta; dar uma chave de escrita a quem não a
            # tem seria contornar a decisão do dono por um caminho lateral.
            alvo = carregar_contexto(id_usuario)
            if not alvo.pode("integracao.claude"):
                raise HTTPException(
                    status_code=400,
                    detail=("Esta pessoa não tem a permissão de conectar o Claude, então "
                            "não pode receber uma chave que altera. Libere em Papéis."))
        cur.execute(
            """INSERT INTO tokens_api (id_usuario, nome, prefixo, token_hash, expira_em,
                                       criado_por, somente_leitura)
               VALUES (%s, %s, %s, %s, now() + make_interval(days => %s), %s, %s)
               RETURNING id""",
            (id_usuario, body.nome.strip(), prefixo, hashed, body.dias, ctx.id_usuario,
             body.somente_leitura),
        )
        novo = cur.fetchone()["id"]
        # ⚠️ Só nome, prefixo e validade vão para a auditoria — nunca o valor.
        auditoria.registrar(cur, ctx.id_usuario, "token_api", novo, "criar",
                            depois={"id_usuario": id_usuario, "nome": body.nome,
                                    "prefixo": prefixo, "dias": body.dias,
                                    "somente_leitura": body.somente_leitura})
        cur.execute(
            f"""SELECT {_COLUNAS}
                  FROM tokens_api t LEFT JOIN usuarios c ON c.id = t.criado_por
                 WHERE t.id = %s""",
            (novo,),
        )
        linha = cur.fetchone()
    return {**linha, "token": valor}


@router.delete("/{id_token}")
def revogar(id_usuario: int, id_token: int, ctx: Contexto = Depends(_so_por_login)) -> dict:
    """Revoga na hora. Não apaga: a linha diz quem usou o quê e até quando."""
    with get_cursor() as cur:
        _conferir_alcance(cur, id_usuario, ctx)
        cur.execute(
            """UPDATE tokens_api SET revogado_em = now(), revogado_por = %s
                WHERE id = %s AND id_usuario = %s AND revogado_em IS NULL
            RETURNING prefixo""",
            (ctx.id_usuario, id_token, id_usuario),
        )
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Chave não encontrada ou já revogada")
        auditoria.registrar(cur, ctx.id_usuario, "token_api", id_token, "revogar",
                            depois={"id_usuario": id_usuario, "prefixo": r["prefixo"]})
    return {"message": "Chave revogada"}


# ------------------------------------------------------------------ as minhas

# 🔑 **Quem conectou o próprio Claude precisa poder desconectá-lo** sem pedir ao
# administrador — e sem `admin.usuarios`. O escopo é o do `PUT /auth/me`: o id
# vem do TOKEN, nunca da URL, então ninguém alcança a chave de outra pessoa.
router_eu = APIRouter(prefix="/auth/me/tokens", tags=["chaves de acesso"])


def _eu_por_login(ctx: Contexto = Depends(contexto_atual)) -> Contexto:
    if ctx.id_token is not None:
        raise HTTPException(status_code=403,
                            detail="Chaves de acesso só se gerem entrando pelo sistema.")
    return ctx


@router_eu.get("", response_model=list[TokenApiResponse])
def minhas(ctx: Contexto = Depends(_eu_por_login)) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {_COLUNAS}
                  FROM tokens_api t LEFT JOIN usuarios c ON c.id = t.criado_por
                 WHERE t.id_usuario = %s
                 ORDER BY (t.revogado_em IS NULL
                           AND coalesce(t.refresh_expira_em, t.expira_em) > now()) DESC,
                          t.criado_em DESC""",
            (ctx.id_usuario,),
        )
        return cur.fetchall()


@router_eu.delete("/{id_token}")
def revogar_minha(id_token: int, ctx: Contexto = Depends(_eu_por_login)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """UPDATE tokens_api SET revogado_em = now(), revogado_por = %s
                WHERE id = %s AND id_usuario = %s AND revogado_em IS NULL
            RETURNING prefixo""",
            (ctx.id_usuario, id_token, ctx.id_usuario),
        )
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Chave não encontrada ou já revogada")
        auditoria.registrar(cur, ctx.id_usuario, "token_api", id_token, "revogar",
                            depois={"id_usuario": ctx.id_usuario, "prefixo": r["prefixo"]})
    return {"message": "Desconectado"}
