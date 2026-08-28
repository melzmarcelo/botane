"""Ajustes em lote — de estoque (quantidade) e de custo (valor).

São **dois processos**, e a separação não é de tela: mexer na quantidade é
dizer que a prateleira tem outra coisa; mexer no custo é dizer que o dinheiro é
outro. O segundo altera o CMV do período sem que nada tenha entrado ou saído,
e por isso tem permissão própria (`estoque.custo`).

Os dois lançam **um lote**: um cabeçalho com autor, data e observação, e N
movimentos apontando para ele por `origem_tipo = 'AJUSTE_LOTE'`. Sem o
cabeçalho, cinco ajustes da mesma conferência ficam indistinguíveis de cinco
avulsos, e a pergunta "de onde veio isto?" não tem resposta.

⚠️ **Tudo num cursor só.** O lote inteiro entra ou não entra nada — meio lote
gravado é pior que nenhum, porque ninguém sabe qual metade passou.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from services import estoque
from services.custos import CASAS_CUSTO, dec

# O tipo mora em `estoque` junto com os outros — é lá que `TIPOS` valida e é
# de lá que sai o rótulo do razão.
AJUSTE_CUSTO = estoque.AJUSTE_CUSTO


def _lote(cur, *, id_unidade: int, natureza: str, observacao: str | None,
          documento: str | None, id_usuario: int | None) -> int:
    cur.execute(
        """INSERT INTO ajuste_lotes (id_unidade, natureza, observacao, documento, id_usuario)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (id_unidade, natureza, observacao, documento, id_usuario),
    )
    return cur.fetchone()["id"]


# ----------------------------------------------------------------- saldo
#
# 🔑 **"A prateleira tem 12, o sistema diz 15."** Entrada e Saída dizem o que se
# MOVEU; este diz quanto realmente TEM. É o mesmo gesto do ajuste de custo —
# declara-se a verdade e o sistema calcula a diferença —, e é para ele que a
# permissão `estoque.ajuste` ("Ajustar saldo fora do inventário") existe desde o
# começo, sem funcionalidade atrás dela.
#
# ⚠️ **Reusa os tipos do inventário** (`AJUSTE_INVENTARIO_ENTRADA/SAIDA`) de
# propósito: é a mesma natureza de correção, e assim o valor cai na linha
# "Ajustes de inventário" que o painel de CMV já mostra. Um tipo novo criaria
# uma segunda linha para a mesma coisa, e a soma das explicações deixaria de
# bater com o que a pessoa entende por "ajuste".


def _saldo_de(cur, id_unidade: int, id_produto: int, local: int, travar: bool):
    cur.execute(
        f"""SELECT s.quantidade, s.custo_medio, p.nome, p.codigo, p.um_estoque
              FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
             WHERE s.id_unidade = %s AND s.id_local = %s AND s.id_produto = %s
             {"FOR UPDATE OF s" if travar else ""}""",
        (id_unidade, local, id_produto),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404,
                            detail="Este produto não tem saldo neste local.")
    return linha


def previa_saldo(cur, id_unidade: int, id_produto: int, id_local: int | None,
                 quantidade_certa) -> dict:
    """O que o acerto faria, sem fazer.

    Mostra a diferença em QUANTIDADE e em REAIS: quem confere conta unidades,
    mas quem lê o CMV depois vê dinheiro — e é o dinheiro que entra na linha
    de ajustes do painel.
    """
    local = id_local or estoque.local_padrao(cur, id_unidade)
    linha = _saldo_de(cur, id_unidade, id_produto, local, travar=False)

    atual = dec(linha["quantidade"])
    certa = dec(quantidade_certa)
    if certa < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa.")
    medio = dec(linha["custo_medio"])
    diferenca = certa - atual

    return {
        "id_produto": id_produto,
        "produto": linha["nome"],
        "codigo": linha["codigo"],
        "um": linha["um_estoque"],
        "id_local": local,
        "saldo_atual": float(atual),
        "saldo_novo": float(certa),
        "diferenca": float(diferenca),
        # Sobra entra, falta sai — e o rótulo diz qual, porque o sinal sozinho
        # não conta a história para quem está conferindo.
        "movimento": "sobra" if diferenca > 0 else "falta" if diferenca < 0 else "nenhum",
        "custo_medio": float(medio),
        "valor": float((diferenca * medio).quantize(Decimal("0.01"))),
        # ⚠️ Ao contrário do ajuste de custo, aqui o sinal NÃO se inverte: falta
        # no estoque baixa o estoque final, e o CMV é `inicial + compras −
        # final` — menos estoque, CMV maior. Falta encarece o mês.
        "efeito_no_cmv": float((-diferenca * medio).quantize(Decimal("0.01"))),
        "sem_efeito": diferenca == 0,
    }


def ajustar_saldo(cur, *, id_unidade: int, id_produto: int, id_local: int | None,
                  quantidade_certa, observacao: str | None = None,
                  documento: str | None = None, id_usuario: int | None = None,
                  pode_retroativo: bool = False) -> dict:
    """Leva o saldo do sistema à quantidade que a prateleira tem."""
    local = id_local or estoque.local_padrao(cur, id_unidade)
    linha = _saldo_de(cur, id_unidade, id_produto, local, travar=True)

    atual = dec(linha["quantidade"])
    certa = dec(quantidade_certa)
    if certa < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa.")
    diferenca = certa - atual
    if diferenca == 0:
        raise HTTPException(
            status_code=400,
            detail=f"{linha['nome']} já está com {atual} neste local.",
        )

    id_lote = _lote(cur, id_unidade=id_unidade, natureza="ESTOQUE",
                    observacao=observacao, documento=documento, id_usuario=id_usuario)

    sobra = diferenca > 0
    m = estoque.lancar(
        cur,
        id_unidade=id_unidade,
        id_produto=id_produto,
        tipo="AJUSTE_INVENTARIO_ENTRADA" if sobra else "AJUSTE_INVENTARIO_SAIDA",
        quantidade=abs(diferenca),
        id_local=local,
        # ⚠️ Sem custo informado: a sobra entra pelo MÉDIO que já existe. Item
        # encontrado vale o que os outros valem, e assim o acerto de quantidade
        # não mexe no custo médio — que é o que o outro tipo faz.
        custo_unitario=None,
        origem_tipo="AJUSTE_LOTE",
        origem_id=id_lote,
        documento=documento,
        observacao=observacao,
        id_usuario=id_usuario,
        pode_retroativo=pode_retroativo,
    )

    return {
        "id_lote": id_lote,
        "id_movimento": m["id"],
        "produto": linha["nome"],
        "saldo_anterior": float(atual),
        "saldo_novo": float(certa),
        "diferenca": float(diferenca),
        "movimento": "sobra" if sobra else "falta",
        "valor": float(m["custo_total"]) * (1 if sobra else -1),
    }


# ------------------------------------------------------------------ custo


def previa_custo(cur, id_unidade: int, id_produto: int, id_local: int | None,
                 custo_novo) -> dict:
    """O que o ajuste faria, sem fazer.

    Existe porque ajuste de custo **não tem desfazer barato**: ele entra no
    razão, muda o CMV do período e só sai por estorno. Quem confirma precisa
    ver o valor de antes, o de depois e a diferença — em reais, não em custo
    unitário, que é onde o erro de casa decimal se esconde.
    """
    local = id_local or estoque.local_padrao(cur, id_unidade)
    cur.execute(
        """SELECT s.quantidade, s.custo_medio, p.nome, p.codigo, p.um_estoque
             FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
            WHERE s.id_unidade = %s AND s.id_local = %s AND s.id_produto = %s""",
        (id_unidade, local, id_produto),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404,
                            detail="Este produto não tem saldo neste local.")

    saldo = dec(linha["quantidade"])
    atual = dec(linha["custo_medio"])
    novo = dec(custo_novo)
    if novo < 0:
        raise HTTPException(status_code=400, detail="Custo não pode ser negativo.")

    valor_atual = (saldo * atual).quantize(Decimal("0.01"))
    valor_novo = (saldo * novo).quantize(Decimal("0.01"))
    return {
        "id_produto": id_produto,
        "produto": linha["nome"],
        "codigo": linha["codigo"],
        "um": linha["um_estoque"],
        "id_local": local,
        "saldo": float(saldo),
        "custo_atual": float(atual),
        "custo_novo": float(novo),
        "valor_atual": float(valor_atual),
        "valor_novo": float(valor_novo),
        "diferenca": float(valor_novo - valor_atual),
        # ⚠️ O sinal importa e é contraintuitivo: subir o custo do estoque
        # AUMENTA o estoque final, e o CMV é `inicial + compras − final`.
        # Estoque mais caro, CMV menor. Quem confirma precisa ler isso antes.
        "efeito_no_cmv": float(valor_atual - valor_novo),
        "sem_efeito": saldo == 0,
    }


def lancar_custo(cur, *, id_unidade: int, linhas: list[dict], observacao: str | None = None,
                 documento: str | None = None, id_usuario: int | None = None,
                 pode_retroativo: bool = False) -> dict:
    """N correções de custo médio, num lote só.

    Para cada produto: lê o saldo e o custo médio de agora, calcula a diferença
    de VALOR e grava um movimento de quantidade zero com essa diferença. O
    custo médio do saldo passa a ser o informado.

    ⚠️ **Saldo zero não se ajusta.** Sem quantidade não há valor a corrigir, e
    o custo médio de um saldo zerado é reescrito pela próxima entrada de
    qualquer jeito. Lançar aí seria um movimento que não muda nada e que
    aparece no razão como se tivesse mudado.
    """
    if not linhas:
        raise HTTPException(status_code=400, detail="Nenhuma linha para lançar.")

    id_lote = _lote(cur, id_unidade=id_unidade, natureza="CUSTO", observacao=observacao,
                    documento=documento, id_usuario=id_usuario)

    resultados = []
    for i, linha in enumerate(linhas, start=1):
        try:
            r = _ajustar_um(
                cur,
                id_unidade=id_unidade,
                id_produto=linha["id_produto"],
                id_local=linha.get("id_local"),
                custo_novo=linha["custo_novo"],
                observacao=linha.get("observacao") or observacao,
                documento=documento,
                id_usuario=id_usuario,
                id_lote=id_lote,
                pode_retroativo=pode_retroativo,
            )
        except HTTPException as e:
            raise HTTPException(status_code=e.status_code,
                                detail=f"Linha {i}: {e.detail}") from e
        resultados.append(r)

    return {
        "id_lote": id_lote,
        "lancados": len(resultados),
        "diferenca_total": round(sum(r["diferenca"] for r in resultados), 2),
        "linhas": resultados,
    }


def _ajustar_um(cur, *, id_unidade: int, id_produto: int, id_local: int | None,
                custo_novo, observacao: str | None, documento: str | None,
                id_usuario: int | None, id_lote: int, pode_retroativo: bool) -> dict:
    local = id_local or estoque.local_padrao(cur, id_unidade)

    # ⚠️ `FOR UPDATE` pela mesma razão de `lancar`: entre ler o saldo e gravar o
    # movimento, outra requisição pode ter lançado uma entrada — e o ajuste
    # calcularia a diferença sobre um saldo que já não existe.
    cur.execute(
        """SELECT s.quantidade, s.custo_medio, p.nome
             FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
            WHERE s.id_unidade = %s AND s.id_local = %s AND s.id_produto = %s
              FOR UPDATE OF s""",
        (id_unidade, local, id_produto),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404,
                            detail="Este produto não tem saldo neste local.")

    saldo = dec(linha["quantidade"])
    atual = dec(linha["custo_medio"])
    novo = dec(custo_novo)
    if novo < 0:
        raise HTTPException(status_code=400, detail="Custo não pode ser negativo.")
    if saldo == 0:
        raise HTTPException(
            status_code=400,
            detail=(f"{linha['nome']} está com saldo zero neste local: não há valor a "
                    "corrigir, e a próxima entrada define o custo médio."),
        )
    if novo == atual:
        raise HTTPException(
            status_code=400,
            detail=f"{linha['nome']} já está com este custo médio.",
        )

    # ⚠️ Mês fechado recusa ajuste de custo como recusa qualquer movimento: ele
    # muda o estoque final, e o estoque final é metade da conta do CMV daquele
    # período. Deixar passar reescreveria um número já entregue.
    estoque._travar_periodo_fechado(cur, id_unidade, datetime.now(), pode_retroativo)

    diferenca = ((saldo * novo) - (saldo * atual)).quantize(Decimal("0.01"))
    # CASAS_CUSTO já É o passo de arredondamento (Decimal("0.000001")), não a
    # contagem de casas — o razão guarda custo unitário com seis.
    novo_arred = novo.quantize(CASAS_CUSTO)

    cur.execute(
        """INSERT INTO estoque_movimentos
               (id_unidade, id_local, id_produto, tipo, quantidade,
                custo_unitario, custo_total, saldo_apos, custo_medio_apos,
                origem_tipo, origem_id, documento, observacao, id_usuario)
           VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s, 'AJUSTE_LOTE', %s, %s, %s, %s)
           RETURNING id""",
        (id_unidade, local, id_produto, AJUSTE_CUSTO, novo_arred, diferenca,
         saldo, novo_arred, id_lote, documento, observacao, id_usuario),
    )
    id_movimento = cur.fetchone()["id"]

    cur.execute(
        """UPDATE estoque_saldos SET custo_medio = %s, atualizado_em = now()
            WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
        (novo_arred, id_unidade, local, id_produto),
    )

    return {
        "id_movimento": id_movimento,
        "id_produto": id_produto,
        "produto": linha["nome"],
        "saldo": float(saldo),
        "custo_anterior": float(atual),
        "custo_novo": float(novo_arred),
        "diferenca": float(diferenca),
    }


# ------------------------------------------------------------------ leitura


def listar_lotes(cur, id_unidade: int, natureza: str | None = None,
                 limite: int = 50, offset: int = 0) -> list[dict]:
    filtro = "AND l.natureza = %(natureza)s" if natureza else ""
    cur.execute(
        f"""SELECT l.id, l.natureza, l.observacao, l.documento, l.criado_em,
                   u.nome AS usuario,
                   count(m.id) AS linhas,
                   coalesce(sum(m.custo_total), 0) AS valor
              FROM ajuste_lotes l
              LEFT JOIN usuarios u ON u.id = l.id_usuario
              LEFT JOIN estoque_movimentos m
                     ON m.origem_tipo = 'AJUSTE_LOTE' AND m.origem_id = l.id
             WHERE l.id_unidade = %(u)s {filtro}
             GROUP BY l.id, u.nome
             ORDER BY l.criado_em DESC
             LIMIT %(limite)s OFFSET %(offset)s""",
        {"u": id_unidade, "natureza": natureza, "limite": limite, "offset": offset},
    )
    return [
        {**dict(r), "valor": float(r["valor"]), "linhas": int(r["linhas"])}
        for r in cur.fetchall()
    ]
