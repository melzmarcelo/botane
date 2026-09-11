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


def _saldo_de(cur, id_unidade: int, id_produto: int, local: int, travar: bool,
              exigir: bool = True):
    """O saldo do produto naquele local.

    ⚠️ **Sem linha de saldo NÃO é impedimento** para o acerto de quantidade: é
    justamente o caso de "a prateleira tem 5 e o sistema não tem nada". Recusar
    ali obrigaria a lançar uma entrada falsa antes, que é pior — inventa uma
    compra que não houve. Quando `exigir` é falso, a ausência vira zero.

    Para o ajuste de CUSTO a ausência continua barrando, e não por política:
    sem quantidade, `(novo − atual) × saldo` é zero. Não há valor a corrigir.
    """
    cur.execute(
        f"""SELECT s.quantidade, s.custo_medio, p.nome, p.codigo, p.um_estoque
              FROM estoque_saldos s JOIN produtos p ON p.id = s.id_produto
             WHERE s.id_unidade = %s AND s.id_local = %s AND s.id_produto = %s
             {"FOR UPDATE OF s" if travar else ""}""",
        (id_unidade, local, id_produto),
    )
    linha = cur.fetchone()
    if linha:
        return linha
    if exigir:
        raise HTTPException(status_code=404,
                            detail="Este produto não tem saldo neste local.")

    # Sem linha ainda: o produto existe, o saldo é zero. O `lancar` cria a
    # linha quando o movimento entrar.
    cur.execute("SELECT nome, codigo, um_estoque FROM produtos WHERE id = %s", (id_produto,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return {"quantidade": 0, "custo_medio": 0, "nome": p["nome"],
            "codigo": p["codigo"], "um_estoque": p["um_estoque"]}


def previa_saldo(cur, id_unidade: int, id_produto: int, id_local: int | None,
                 quantidade_certa) -> dict:
    """O que o acerto faria, sem fazer.

    Mostra a diferença em QUANTIDADE e em REAIS: quem confere conta unidades,
    mas quem lê o CMV depois vê dinheiro — e é o dinheiro que entra na linha
    de ajustes do painel.
    """
    local = id_local or estoque.local_padrao(cur, id_unidade)
    linha = _saldo_de(cur, id_unidade, id_produto, local, travar=False, exigir=False)

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
    linha = _saldo_de(cur, id_unidade, id_produto, local, travar=True, exigir=False)

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

    # 🔑 **No modo geral (migração 064) o ajuste é da LOJA, não da prateleira.**
    # Corrigir só o local escolhido deixaria as outras prateleiras discordando
    # até a próxima entrada reconciliá-las — que é exatamente a divergência que
    # o custo geral veio acabar, reintroduzida pela tela que existe para
    # corrigir custo.
    # ⚠️ **Cada prateleira com saldo ganha o PRÓPRIO movimento**, com a diferença
    # dela: o valor reavaliado é `quantidade × (novo − velho)` e essa quantidade
    # é de cada uma. Um movimento só, no local escolhido, com a diferença da
    # loja inteira, faria `valor = quantidade × custo_medio` deixar de fechar
    # naquela linha.
    # ⚠️ Prateleira com saldo zero vai por `UPDATE`: não há valor a reavaliar, e
    # um movimento de diferença zero só sujaria o razão.
    diferenca_total = diferenca
    if not estoque._parametros(cur, id_unidade).get("custo_por_local", False):
        cur.execute(
            """SELECT id_local, quantidade, custo_medio FROM estoque_saldos
                WHERE id_unidade = %s AND id_produto = %s AND id_local <> %s
                  AND custo_medio IS DISTINCT FROM %s
                ORDER BY id_local
                FOR UPDATE""",
            (id_unidade, id_produto, local, novo_arred),
        )
        for outra in cur.fetchall():
            q, c = dec(outra["quantidade"]), dec(outra["custo_medio"])
            if q != 0:
                d = ((q * novo_arred) - (q * c)).quantize(Decimal("0.01"))
                cur.execute(
                    """INSERT INTO estoque_movimentos
                           (id_unidade, id_local, id_produto, tipo, quantidade,
                            custo_unitario, custo_total, saldo_apos, custo_medio_apos,
                            origem_tipo, origem_id, documento, observacao, id_usuario)
                       VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s,
                               'AJUSTE_LOTE', %s, %s, %s, %s)""",
                    (id_unidade, outra["id_local"], id_produto, AJUSTE_CUSTO, novo_arred,
                     d, q, novo_arred, id_lote, documento,
                     "Custo único da loja", id_usuario),
                )
                diferenca_total += d
            cur.execute(
                """UPDATE estoque_saldos SET custo_medio = %s, atualizado_em = now()
                    WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
                (novo_arred, id_unidade, outra["id_local"], id_produto),
            )

    return {
        "id_movimento": id_movimento,
        "id_produto": id_produto,
        "produto": linha["nome"],
        "saldo": float(saldo),
        "custo_anterior": float(atual),
        "custo_novo": float(novo_arred),
        # ⚠️ A diferença é a da LOJA quando o custo é geral — é ela que bate com
        # o que o estoque passou a valer, e é ela que o painel vai mostrar.
        "diferenca": float(diferenca_total),
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


# ------------------------------------------- unificar o custo por loja (064)


def _divergentes(cur, id_unidade: int) -> list[dict]:
    """Produtos cujas prateleiras discordam do custo — e qual seria o custo único.

    🔑 **O alvo é o ponderado das prateleiras POSITIVAS com custo**, o mesmo
    recorte da cascata (`custos.custo_do_insumo`) e o que a tela adotou. Saldo
    negativo é dívida, não mercadoria, e prateleira com custo zero é justamente
    a que não sabe — deixar qualquer um dos dois pesar puxaria o custo da casa
    para baixo com um número que ninguém pagou.

    ⚠️ **Produto de que NINGUÉM sabe o custo fica de fora.** Sem uma prateleira
    valorada não há o que unificar: zerar todas seria trocar "não sei" por "é de
    graça", que é pior porque cala o aviso.
    """
    cur.execute(
        """WITH alvo AS (
               SELECT id_produto,
                      sum(quantidade) FILTER (WHERE quantidade > 0 AND custo_medio > 0) AS q,
                      sum(quantidade * custo_medio)
                          FILTER (WHERE quantidade > 0 AND custo_medio > 0) AS v
                 FROM estoque_saldos
                WHERE id_unidade = %(u)s
                GROUP BY id_produto
                HAVING sum(quantidade) FILTER (WHERE quantidade > 0 AND custo_medio > 0) > 0
           )
           SELECT s.id_produto, s.id_local, s.quantidade, s.custo_medio,
                  p.codigo, p.nome AS produto, l.nome AS local,
                  round(a.v / a.q, 6) AS custo_novo
             FROM estoque_saldos s
             JOIN alvo a ON a.id_produto = s.id_produto
             JOIN produtos p ON p.id = s.id_produto
             JOIN locais_estoque l ON l.id = s.id_local
            WHERE s.id_unidade = %(u)s
              AND s.custo_medio IS DISTINCT FROM round(a.v / a.q, 6)
            ORDER BY lower(p.nome), l.nome""",
        {"u": id_unidade},
    )
    return [dict(r) for r in cur.fetchall()]


def previa_custo_geral(cur, id_unidade: int) -> dict:
    """O que a unificação faria, sem fazer. Prévia antes do botão.

    ⚠️ **Duas listas, e a diferença entre elas é o que importa.** Prateleira com
    saldo reavalia estoque: muda quanto a casa tem em mercadoria e portanto o
    CMV do período, e por isso vira `AJUSTE_CUSTO` no razão. Prateleira com
    saldo ZERO não muda valor nenhum — só passa a saber o custo para a próxima
    saída. Misturar as duas num número só faria a pessoa aprovar uma reavaliação
    achando que estava só preenchendo campo vazio.
    """
    linhas = _divergentes(cur, id_unidade)
    com_saldo = [l for l in linhas if dec(l["quantidade"]) != 0]
    sem_saldo = [l for l in linhas if dec(l["quantidade"]) == 0]

    for l in linhas:
        atual, novo = dec(l["custo_medio"]), dec(l["custo_novo"])
        l["quantidade"] = float(dec(l["quantidade"]))
        l["custo_medio"] = float(atual)
        l["custo_novo"] = float(novo)
        l["diferenca"] = float(
            ((dec(str(l["quantidade"])) * novo) - (dec(str(l["quantidade"])) * atual))
            .quantize(Decimal("0.01"))
        )

    return {
        "produtos": len({l["id_produto"] for l in linhas}),
        "prateleiras_reavaliadas": len(com_saldo),
        "prateleiras_so_preenchidas": len(sem_saldo),
        # O efeito no ESTOQUE. No CMV ele entra com o sinal trocado (estoque
        # mais caro, CMV menor) — é o que a linha "ajuste de custo" do painel
        # mostra, e a tela diz isso ao lado.
        "efeito_no_estoque": round(sum(l["diferenca"] for l in com_saldo), 2),
        "linhas": linhas,
    }


def unificar_custo_geral(cur, *, id_unidade: int, id_usuario: int | None = None,
                         pode_retroativo: bool = False) -> dict:
    """Põe todas as prateleiras no mesmo custo, num lote só.

    🔑 **Pedido do dono (11/09/2026)**: "gostaria que neste primeiro momento o
    custo fosse geral, inclusive ajustar isto já nos produtos cadastrados". A
    migração 064 muda o comportamento dali para a frente; o que já está no
    estoque precisa deste botão.

    ⚠️ **Reavaliar estoque é LANÇAMENTO, não conserto de dado.** Cada prateleira
    com saldo vira um `AJUSTE_CUSTO` (migração 039) dentro de um lote com
    observação — o mesmo caminho da conferência de custo feita à mão. Um
    `UPDATE` calado mudaria o CMV do período sem nada explicando de onde veio, e
    o painel tem uma linha própria justamente para essa pergunta.

    ⚠️ **Prateleira com saldo zero é o caso oposto e vai por `UPDATE` mesmo.**
    Não há valor a reavaliar (zero vezes qualquer coisa é zero), e gravar um
    movimento de diferença zero encheria o razão de linhas que não dizem nada.
    """
    previa = previa_custo_geral(cur, id_unidade)
    com_saldo = [l for l in previa["linhas"] if l["quantidade"] != 0]
    sem_saldo = [l for l in previa["linhas"] if l["quantidade"] == 0]

    resultado = {"id_lote": None, "reavaliadas": 0, "preenchidas": 0,
                 "efeito_no_estoque": 0.0}

    if com_saldo:
        id_lote = _lote(cur, id_unidade=id_unidade, natureza="CUSTO",
                        observacao="Unificação do custo médio por loja (parâmetro "
                                   "“custo geral”)",
                        documento=None, id_usuario=id_usuario)
        # ⚠️ **Uma chamada por PRODUTO, não por prateleira.** No modo geral
        # `_ajustar_um` já propaga para as outras prateleiras do produto, com um
        # movimento para cada uma; chamá-lo prateleira a prateleira lançaria o
        # mesmo ajuste várias vezes e somaria o efeito em dobro no relatório.
        primeira_de_cada: dict[int, dict] = {}
        for linha in com_saldo:
            primeira_de_cada.setdefault(linha["id_produto"], linha)

        feitos = []
        for linha in primeira_de_cada.values():
            feitos.append(_ajustar_um(
                cur, id_unidade=id_unidade, id_produto=linha["id_produto"],
                id_local=linha["id_local"], custo_novo=linha["custo_novo"],
                observacao="Custo unificado entre as prateleiras", documento=None,
                id_usuario=id_usuario, id_lote=id_lote, pode_retroativo=pode_retroativo,
            ))
        resultado["id_lote"] = id_lote
        resultado["reavaliadas"] = len(com_saldo)
        resultado["efeito_no_estoque"] = round(sum(f["diferenca"] for f in feitos), 2)

    # ⚠️ Depois da propagação, a maioria destas já foi preenchida pelo próprio
    # ajuste — o `UPDATE` aqui alcança as que sobraram (produto cujas
    # prateleiras divergentes têm todas saldo zero) e é inofensivo nas demais.
    for linha in sem_saldo:
        cur.execute(
            """UPDATE estoque_saldos SET custo_medio = %s, atualizado_em = now()
                WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
            (linha["custo_novo"], id_unidade, linha["id_local"], linha["id_produto"]),
        )
    resultado["preenchidas"] = len(sem_saldo)

    resultado["message"] = (
        f"{resultado['reavaliadas']} prateleira(s) reavaliada(s) e "
        f"{resultado['preenchidas']} preenchida(s) com o custo da loja."
        if (resultado["reavaliadas"] or resultado["preenchidas"])
        else "Nada a unificar: todas as prateleiras já estão com o mesmo custo."
    )
    return resultado
