"""PDV Legal — credencial, autenticação e teste de conexão.

⚠️ **Só isto, e é de propósito.** O `POST /token` da Tablet Cloud é a única
parte da API documentada publicamente; o catálogo de endpoints — vendas do dia,
itens, cancelamentos, cardápio — fica no portal de parceiros, fechado. Sem ele,
escrever importador é adivinhar endereço: exatamente o que, na integração com o
Omie, custou uma conta bloqueada por parâmetro inventado.

O que existe aqui destrava o resto: com a credencial guardada e o token
funcionando, o importador que vier depois só precisa saber **quais** endereços
chamar.

Enquanto isso, a venda continua entrando por planilha — o plano B previsto no
mapeamento, que funciona e alimenta o mesmo `vendas`/`venda_itens`.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auditoria
from database import get_cursor
from seguranca import Contexto, requer_permissao, unidade_atual
from services import segredos
from services.pdv.cliente import ClientePdv

router = APIRouter(prefix="/pdv", tags=["PDV Legal"])

SERVICO = "PDV_LEGAL"


class ConfigPdv(BaseModel):
    # ⚠️ Os quatro em branco mantêm o que já estava: a tela mostra mascarado, e
    # exigir redigitar a senha para mudar o modo é o caminho mais curto para
    # alguém guardar a credencial num bloco de notas.
    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=200)
    # O `client_id` é o código do grupo econômico; o `client_secret`, o token do
    # grupo. Nomes deles, não nossos.
    client_id: str | None = Field(default=None, max_length=120)
    client_secret: str | None = Field(default=None, max_length=200)
    modo: str = "simulado"          # simulado | real
    ativa: bool = False


def _cliente(cur, id_unidade: int) -> ClientePdv:
    cur.execute(
        "SELECT credenciais, modo FROM integracoes WHERE id_unidade = %s AND servico = %s",
        (id_unidade, SERVICO),
    )
    linha = cur.fetchone()
    if not linha:
        return ClientePdv(modo="simulado")
    c = segredos.decifrar(linha["credenciais"])
    return ClientePdv(c.get("username"), c.get("password"), c.get("client_id"),
                      c.get("client_secret"), linha["modo"])


@router.get("/config")
def config(ctx: Contexto = Depends(requer_permissao("integracao.pdv", "admin.integracoes"))
           ) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT modo, ativa, credenciais, ultima_sincronizacao, ultimo_status,
                      ultima_mensagem
                 FROM integracoes WHERE id_unidade = %s AND servico = %s""",
            (id_unidade, SERVICO),
        )
        linha = cur.fetchone()

    cred = segredos.decifrar(linha["credenciais"]) if linha else {}
    return {
        "configurada": bool(cred.get("username") and cred.get("client_id")),
        "modo": linha["modo"] if linha else "simulado",
        "ativa": linha["ativa"] if linha else False,
        # ⚠️ Nada volta em claro — nem o usuário. A senha e o segredo do grupo
        # são credencial; o usuário e o código do grupo identificam a conta, e
        # mascarados ainda dão para reconhecer qual foi configurada.
        "username": segredos.mascarar(cred.get("username")),
        "password": segredos.mascarar(cred.get("password")),
        "client_id": segredos.mascarar(cred.get("client_id")),
        "client_secret": segredos.mascarar(cred.get("client_secret")),
        "ultima_sincronizacao": linha["ultima_sincronizacao"] if linha else None,
        "ultimo_status": linha["ultimo_status"] if linha else None,
        "ultima_mensagem": linha["ultima_mensagem"] if linha else None,
        # O que ainda falta para a venda entrar sozinha. Vai no JSON porque é a
        # tela que precisa explicar por que só há um botão de testar aqui.
        "importador_disponivel": False,
        "pendencia": ("O catálogo de endpoints do PDV Legal não é público. Com ele, "
                      "a venda passa a entrar sozinha; até lá, ela entra por planilha."),
    }


@router.put("/config")
def salvar_config(body: ConfigPdv,
                  ctx: Contexto = Depends(requer_permissao("admin.integracoes"))) -> dict:
    if body.modo not in ("simulado", "real"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'simulado' ou 'real'.")

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            "SELECT credenciais FROM integracoes WHERE id_unidade = %s AND servico = %s",
            (id_unidade, SERVICO),
        )
        atual = cur.fetchone()
        cred = segredos.decifrar(atual["credenciais"]) if atual else {}
        for campo in ("username", "password", "client_id", "client_secret"):
            valor = getattr(body, campo)
            if valor:
                cred[campo] = valor.strip()

        # ⚠️ Modo real sem os quatro é promessa que a primeira chamada quebra —
        # e o erro apareceria como "não autorizado", que manda quem configurou
        # procurar a credencial errada.
        if body.modo == "real" and not all(cred.get(c) for c in
                                           ("username", "password", "client_id",
                                            "client_secret")):
            raise HTTPException(
                status_code=400,
                detail=("Para o modo real faltam credenciais. O PDV Legal precisa dos "
                        "quatro: usuário, senha, código do grupo econômico (client_id) e "
                        "token do grupo (client_secret)."),
            )

        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, ativa, modo, credenciais)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ativa = EXCLUDED.ativa, modo = EXCLUDED.modo,
                       credenciais = EXCLUDED.credenciais, atualizado_em = now()""",
            (id_unidade, SERVICO, body.ativa, body.modo, segredos.cifrar(cred)),
        )
        # A auditoria registra a mudança sem registrar o segredo.
        auditoria.registrar(cur, ctx.id_usuario, "integracao", SERVICO, "configurar",
                            depois={"modo": body.modo, "ativa": body.ativa,
                                    "username": segredos.mascarar(cred.get("username"))},
                            id_unidade=id_unidade)
    return {"message": "Integração do PDV Legal salva"}


@router.post("/testar")
def testar(ctx: Contexto = Depends(requer_permissao("integracao.pdv", "admin.integracoes"))
           ) -> dict:
    """Pede um token e diz se veio. É a única chamada real que existe hoje.

    ⚠️ Registra o resultado em `integracoes`, inclusive a falha: quem configurou
    fecha a tela, e a próxima pessoa precisa ver que a última tentativa não
    passou — sem isso, "configurada" pareceria "funcionando".
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = _cliente(cur, id_unidade).testar()
        cur.execute(
            """INSERT INTO integracoes (id_unidade, servico, modo, ultimo_status,
                                        ultima_mensagem)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, servico) DO UPDATE
                   SET ultimo_status = EXCLUDED.ultimo_status,
                       ultima_mensagem = EXCLUDED.ultima_mensagem""",
            (id_unidade, SERVICO, r["modo"], "OK" if r["ok"] else "ERRO", r["detalhe"]),
        )
    return r
