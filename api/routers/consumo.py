"""Meu consumo — o que EU consumi, o que me foi cobrado e o que já paguei.

🔑 **Pedido do dono (04/09/2026):** quem consumiu consulta o próprio saldo, sem
depender de ninguém. Desde 22/10/2026 o período deu lugar às contas a receber
(`routers/receber.py`): aqui a pessoa vê o que está EM ABERTO, os lotes EM
COBRANÇA (o que já lhe foi mandado) e o histórico dos lotes RECEBIDOS.

⚠️ **`/consumo/meu` NÃO exige permissão, só autenticação** — e é a mesma regra
de todo dado pessoal escopado ao chamador. Exigir uma chave ali faria a pessoa
precisar de permissão para ver a própria dívida, que é o oposto do pedido. O
escopo vem do vínculo usuário↔pessoa, nunca de um `id_pessoa` mandado pelo
cliente: aceitá-lo deixaria qualquer um ler o consumo de qualquer outro.
"""

from fastapi import APIRouter, Depends

from database import get_cursor
from seguranca import Contexto, contexto_atual, unidade_atual
from services import receber as motor

router = APIRouter(prefix="/consumo", tags=["consumo"])


def _pessoa_do_usuario(cur, id_usuario: int) -> dict | None:
    """A pessoa ligada a este login — o escopo de *Meu consumo*."""
    cur.execute(
        """SELECT f.id, f.nome, f.cupom_base, f.cupom_desconto_pct
             FROM usuarios u
             JOIN fornecedores f ON f.id = u.id_pessoa
            WHERE u.id = %s""",
        (id_usuario,),
    )
    linha = cur.fetchone()
    return dict(linha) if linha else None


def _cupons_em_aberto(cur, id_unidade: int, id_pessoa: int) -> list[dict]:
    """Os documentos ainda sem lote desta pessoa — o extrato de *Meu consumo*."""
    cur.execute(
        """SELECT v.id, v.data, v.hora, v.documento,
                  sum(vi.quantidade * coalesce(vi.valor_unitario_cheio,
                                               vi.valor_unitario)) AS total_cheio,
                  sum(vi.valor_total) - v.desconto AS total,
                  count(*) AS itens
             FROM vendas v
             JOIN venda_itens vi ON vi.id_venda = v.id
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.id_pessoa = %s AND v.id_consumo_lote IS NULL
            GROUP BY v.id, v.data, v.hora, v.documento, v.desconto
            ORDER BY v.data DESC, v.hora DESC NULLS LAST, v.id DESC""",
        (id_unidade, id_pessoa),
    )
    return [dict(r) for r in cur.fetchall()]


@router.get("/meu")
def meu_consumo(ctx: Contexto = Depends(contexto_atual)) -> dict:
    """O que EU consumi e ainda não paguei, e o que já paguei.

    ⚠️ **Login sem pessoa ligada não é erro** — é o estado da maioria (quem só
    opera o sistema e nunca consome). A tela precisa dizer isso em vez de
    mostrar zero, porque "não devo nada" e "não estou ligado a um cadastro" são
    coisas diferentes, e a segunda se resolve no cadastro de usuários.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        pessoa = _pessoa_do_usuario(cur, ctx.id_usuario)
        if not pessoa:
            return {"vinculado": False, "pessoa": None, "cupons": [], "total": 0,
                    "total_cheio": 0, "desconto": 0, "em_cobranca": [], "historico": [],
                    "formas": motor.FORMAS}

        linhas = motor.em_aberto(cur, id_unidade, ids_pessoa=[pessoa["id"]])
        resumo = linhas[0] if linhas else {}
        lotes = motor.lotes(cur, id_unidade, ["ABERTO", "RECEBIDO"], pessoa["id"], 48)
        return {
            "vinculado": True,
            "pessoa": pessoa,
            "cupons": _cupons_em_aberto(cur, id_unidade, pessoa["id"]),
            "total": float(resumo.get("total") or 0),
            "total_cheio": float(resumo.get("total_cheio") or 0),
            "desconto": float(resumo.get("desconto") or 0),
            "em_cobranca": [l for l in lotes if l["status"] == "ABERTO"],
            "historico": [l for l in lotes if l["status"] == "RECEBIDO"][:24],
            "formas": motor.FORMAS,
        }
