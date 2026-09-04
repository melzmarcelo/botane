"""Períodos de consumo — o ciclo que se abre, acumula e se fecha no pagamento.

🔑 **Pedido do dono (04/09/2026):** o administrador abre um período de tal a tal
dia; o consumo do pessoal cai nele; quando o pagamento acontece, o período é
fechado. E quem consumiu consulta o próprio saldo, sem depender de ninguém.

⚠️ **`/consumo/meu` NÃO exige permissão, só autenticação** — e é a mesma regra
de todo dado pessoal escopado ao chamador. Exigir uma chave ali faria a pessoa
precisar de permissão para ver a própria dívida, que é o oposto do pedido ("para
saber o valor do seu consumo"). O escopo vem do vínculo usuário↔pessoa, nunca de
um `id_pessoa` mandado pelo cliente: aceitá-lo deixaria qualquer um ler o
consumo de qualquer outro.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import auditoria
from database import get_cursor
from models.consumo import PeriodoAbrir, PeriodoFechar
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import consumo_periodo as motor

router = APIRouter(prefix="/consumo", tags=["consumo"])

# ⚠️ **`cmv.painel` NÃO basta aqui, de propósito.** Estas telas mostram o que
# cada PESSOA deve — dívida individual, não número de negócio — e `cmv.painel` é
# a chave mais larga da casa: quem só acompanha o CMV passaria a ver o saldo dos
# colegas. Fica com a mesma chave do relatório que mostra os mesmos números
# (`cmv.relatorios`), mais quem gere os ciclos.
_ver = requer_permissao("consumo.periodos", "cmv.relatorios")
_gerir = requer_permissao("consumo.periodos")


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


@router.get("/meu")
def meu_consumo(ctx: Contexto = Depends(contexto_atual)) -> dict:
    """O que EU consumi e ainda não paguei.

    ⚠️ **Login sem pessoa ligada não é erro** — é o estado da maioria (quem só
    opera o sistema e nunca consome). A tela precisa dizer isso em vez de
    mostrar zero, porque "não devo nada" e "não estou ligado a um cadastro" são
    coisas diferentes, e a segunda se resolve no cadastro de usuários.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        pessoa = _pessoa_do_usuario(cur, ctx.id_usuario)
        if not pessoa:
            return {"vinculado": False, "pessoa": None, "aberto": None,
                    "cupons": [], "total": 0, "total_cheio": 0, "desconto": 0,
                    "periodo": None, "historico": []}

        linhas = motor.em_aberto_por_pessoa(cur, id_unidade, pessoa["id"])
        resumo = linhas[0] if linhas else {}
        cupons = motor.cupons_em_aberto(cur, id_unidade, pessoa["id"])

        # O histórico do que já foi fechado — o recibo de cada ciclo.
        cur.execute(
            """SELECT p.id, p.nome, p.inicio, p.fim, p.fechado_em,
                      c.cupons, c.itens, c.total_cheio, c.desconto, c.total
                 FROM consumo_periodo_pessoas c
                 JOIN consumo_periodos p ON p.id = c.id_periodo
                WHERE c.id_pessoa = %s AND p.id_unidade = %s
                ORDER BY p.fim DESC
                LIMIT 24""",
            (pessoa["id"], id_unidade),
        )
        historico = [dict(r) for r in cur.fetchall()]

        return {
            "vinculado": True,
            "pessoa": pessoa,
            "periodo": motor.periodo_aberto(cur, id_unidade),
            "cupons": cupons,
            "total": float(resumo.get("total") or 0),
            "total_cheio": float(resumo.get("total_cheio") or 0),
            "desconto": float(resumo.get("desconto") or 0),
            "historico": historico,
        }


@router.get("/periodos")
def listar(ctx: Contexto = Depends(_ver)) -> dict:
    """Os ciclos, o mais recente primeiro, e o que está em aberto agora."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT p.id, p.nome, p.inicio, p.fim, p.status, p.aberto_em,
                      p.fechado_em, p.observacao,
                      ua.nome AS abriu, uf.nome AS fechou,
                      (SELECT count(*) FROM consumo_periodo_pessoas c
                        WHERE c.id_periodo = p.id) AS pessoas,
                      (SELECT coalesce(sum(c.total), 0) FROM consumo_periodo_pessoas c
                        WHERE c.id_periodo = p.id) AS total
                 FROM consumo_periodos p
                 LEFT JOIN usuarios ua ON ua.id = p.id_usuario_abriu
                 LEFT JOIN usuarios uf ON uf.id = p.id_usuario_fechou
                WHERE p.id_unidade = %s
                ORDER BY p.fim DESC, p.id DESC""",
            (id_unidade,),
        )
        periodos = [dict(r) for r in cur.fetchall()]
        aberto = motor.periodo_aberto(cur, id_unidade)
        em_aberto = motor.em_aberto_por_pessoa(cur, id_unidade)
        previa = motor.previa_do_fechamento(cur, id_unidade, aberto) if aberto else None
        return {
            "periodos": periodos,
            "aberto": aberto,
            "em_aberto": em_aberto,
            "previa": previa,
            "total_em_aberto": round(
                sum(float(l["total"] or 0) for l in em_aberto), 2),
        }


@router.get("/periodos/{id_periodo}")
def detalhe(id_periodo: int, ctx: Contexto = Depends(_ver)) -> dict:
    """Um ciclo: o recibo por pessoa, se fechado; o que está caindo, se aberto."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT id, nome, inicio, fim, status, aberto_em, fechado_em, observacao
                 FROM consumo_periodos WHERE id = %s AND id_unidade = %s""",
            (id_periodo, id_unidade),
        )
        periodo = cur.fetchone()
        if not periodo:
            raise HTTPException(status_code=404, detail="Período não encontrado")
        periodo = dict(periodo)

        if periodo["status"] == "FECHADO":
            # 🔑 O RECIBO congelado, não um recálculo. Recalcular faria o
            # documento do pagamento mudar quando alguém corrigisse uma venda
            # antiga — e o valor cobrado na época deixaria de ser respondível.
            cur.execute(
                """SELECT c.id_pessoa, f.nome AS pessoa, c.cupons, c.itens,
                          c.total_cheio, c.desconto, c.total
                     FROM consumo_periodo_pessoas c
                     JOIN fornecedores f ON f.id = c.id_pessoa
                    WHERE c.id_periodo = %s
                    ORDER BY c.total DESC, f.nome""",
                (id_periodo,),
            )
            linhas = [dict(r) for r in cur.fetchall()]
        else:
            linhas = motor.em_aberto_por_pessoa(cur, id_unidade)

        return {
            "periodo": periodo,
            "linhas": linhas,
            "previa": (motor.previa_do_fechamento(cur, id_unidade, periodo)
                       if periodo["status"] == "ABERTO" else None),
            "total": round(sum(float(l["total"] or 0) for l in linhas), 2),
            "total_cheio": round(sum(float(l["total_cheio"] or 0) for l in linhas), 2),
            "desconto": round(sum(float(l["desconto"] or 0) for l in linhas), 2),
        }


@router.post("/periodos", status_code=201)
def abrir(body: PeriodoAbrir, ctx: Contexto = Depends(_gerir)) -> dict:
    """Abre o ciclo. Um por loja de cada vez — a garantia é do índice único."""
    if body.fim < body.inicio:
        raise HTTPException(status_code=400, detail="A data final é anterior à inicial.")
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        if motor.periodo_aberto(cur, id_unidade):
            raise HTTPException(
                status_code=409,
                detail="Já existe um período aberto. Feche-o antes de abrir outro.")
        # ⚠️ Sobreposição recusada: um mesmo dia em dois ciclos faria o consumo
        # daquele dia ser cobrado duas vezes, e nada na tela denunciaria.
        cur.execute(
            """SELECT id, inicio, fim FROM consumo_periodos
                WHERE id_unidade = %s AND inicio <= %s AND fim >= %s
                LIMIT 1""",
            (id_unidade, body.fim, body.inicio),
        )
        choque = cur.fetchone()
        if choque:
            raise HTTPException(
                status_code=409,
                detail=f"O período se sobrepõe ao de {choque['inicio']} a {choque['fim']}.")

        cur.execute(
            """INSERT INTO consumo_periodos
                   (id_unidade, nome, inicio, fim, id_usuario_abriu, observacao)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (id_unidade, body.nome, body.inicio, body.fim, ctx.id_usuario, body.observacao),
        )
        id_periodo = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "consumo_periodo", id_periodo,
                            "abrir",
                            depois={"inicio": str(body.inicio), "fim": str(body.fim)})
        return {"id": id_periodo, "message": "Período aberto"}


@router.post("/periodos/{id_periodo}/fechar")
def fechar(id_periodo: int, body: PeriodoFechar | None = None,
           ctx: Contexto = Depends(_gerir)) -> dict:
    """Fecha o ciclo: grava o recibo por pessoa e carimba as vendas.

    ⚠️ **Leva TUDO que está em aberto até a data final**, inclusive consumo
    anterior ao início que ninguém pagou — deixá-lo de fora faria o saldo
    daquela pessoa ficar errado para sempre. A resposta diz quantos vieram de
    antes, para que a decisão não seja calada.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT id, inicio, fim, status FROM consumo_periodos
                WHERE id = %s AND id_unidade = %s""",
            (id_periodo, id_unidade),
        )
        periodo = cur.fetchone()
        if not periodo:
            raise HTTPException(status_code=404, detail="Período não encontrado")
        antes = motor.previa_do_fechamento(cur, id_unidade, dict(periodo))

        r = motor.fechar(cur, id_unidade, id_periodo, ctx.id_usuario,
                         (body.observacao if body else None))
        if "erro" in r:
            raise HTTPException(status_code=409, detail=r["erro"])
        auditoria.registrar(cur, ctx.id_usuario, "consumo_periodo", id_periodo,
                            "fechar", depois=r)
        anteriores = antes.get("anteriores") or 0
        return {
            **r,
            "anteriores": anteriores,
            "message": (f"Período fechado · {r['pessoas']} pessoa(s), "
                        f"{r['cupons']} cupom(ns), total {r['total']:.2f}"
                        + (f" · {anteriores} cupom(ns) vieram de antes do início, "
                           "ainda em aberto" if anteriores else "")),
        }


@router.delete("/periodos/{id_periodo}")
def excluir(id_periodo: int, ctx: Contexto = Depends(_gerir)) -> dict:
    """Apaga um ciclo ABERTO — o conserto de quem errou as datas.

    🔑 **Existe porque a alternativa era destrutiva.** Sem isto, quem abrisse o
    período com as datas erradas só sairia dele FECHANDO — e fechar carimba
    todo o consumo em aberto como pago. O conserto de um engano de digitação
    não pode ser cobrar todo mundo.

    ⚠️ **Só o ABERTO se apaga**, e é justamente porque nada foi carimbado nele:
    não há venda apontando para cá, nem recibo emitido. Apagar um fechado
    devolveria dívida já paga ao limbo, sem recibo e sem carimbo — para isso
    existe o `reabrir`, que desfaz explicitamente.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT id, status FROM consumo_periodos
                WHERE id = %s AND id_unidade = %s""",
            (id_periodo, id_unidade),
        )
        periodo = cur.fetchone()
        if not periodo:
            raise HTTPException(status_code=404, detail="Período não encontrado")
        if periodo["status"] != "ABERTO":
            raise HTTPException(
                status_code=409,
                detail="Período já fechado não se apaga — reabra primeiro.")
        cur.execute("DELETE FROM consumo_periodos WHERE id = %s", (id_periodo,))
        auditoria.registrar(cur, ctx.id_usuario, "consumo_periodo", id_periodo,
                            "excluir")
        return {"message": "Período apagado"}


@router.post("/periodos/{id_periodo}/reabrir")
def reabrir(id_periodo: int, ctx: Contexto = Depends(_gerir)) -> dict:
    """Desfaz o fechamento — só o último, e só se não houver ciclo aberto."""
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        r = motor.reabrir(cur, id_unidade, id_periodo)
        if "erro" in r:
            raise HTTPException(status_code=409, detail=r["erro"])
        auditoria.registrar(cur, ctx.id_usuario, "consumo_periodo", id_periodo,
                            "reabrir", depois=r)
        return {**r, "message": f"Período reaberto · {r['cupons']} cupom(ns) "
                                "voltaram para em aberto"}
