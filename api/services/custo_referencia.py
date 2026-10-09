"""Conferência do custo de REFERÊNCIA: achar o que está furado e corrigir.

🔑 **Pedido do dono (05/10/2026)**: *"tem alguns produtos que, por conta da
conversão do Omie, ficam com o custo furado"*. O caso que ele trouxe: o ANA &
GRAZI VINHO ROSÉ, vendido a R$ 109,00 com custo de R$ 264,00 — o preço da CAIXA
de seis —, enquanto o razão do mesmo produto saía a R$ 44,00 a garrafa.

O custo de referência é o último degrau da cascata (`custos.custo_do_insumo`):
só responde quando não há médio em prateleira com saldo nem preço de fornecedor.
É o caso de quase todo o catálogo que veio do Omie e ainda não recebeu nota. E
**ele não tem tela de edição** — um número errado ali ficava até a primeira nota
chegar, alimentando ficha, CMV teórico, margem e a Precificação.

⚠️ **A referência NÃO é razão.** Corrigir é um `UPDATE` no cadastro, com o antes
e o depois na auditoria — nada aqui cria movimento nem mexe em saldo.

⚠️ **Só entra na lista quem HOJE é custeado pela referência.** Produto com médio
de verdade ou preço de fornecedor tem a referência parada, sem efeito: listá-lo
seria pedir conferência de um número que ninguém lê.
"""

from decimal import Decimal

from fastapi import HTTPException

import auditoria
from services import precos
from services.custos import CASAS_CUSTO, dec

# A partir de quanto a referência e o razão "discordam". Meio a meio para cima:
# variação de preço entre uma compra e outra não chega a isso, embalagem chega.
DISCORDA = Decimal("1.5")
# Quão perto a razão entre os dois precisa estar de um fator de embalagem para
# a tela poder dizer "é o preço da caixa".
FOLGA_DO_FATOR = Decimal("0.03")

ORIGEM = "CORRECAO"
# 🔑 **O custo que alguém DIGITOU no cadastro** (08/10/2026, pedido do dono: *"temos
# o produto Água, que é água encanada, não tem estoque, mas precisa ter custo, e
# não conseguimos informar este custo em local nenhum"*). É o mesmo degrau da
# referência — o último, só responde quando não há médio nem fornecedor —, com a
# origem dizendo que foi uma pessoa, e não outro sistema, quem afirmou o número.
# ⚠️ A carga do Omie NÃO passa por cima dele (`importador.custos_iniciais`).
ORIGEM_MANUAL = "MANUAL"


def _fatores(cur, ids: list[int]) -> dict[int, list[tuple[str, Decimal]]]:
    """As embalagens de cada produto: (sigla, quantas unidades de estoque cabem)."""
    fatores: dict[int, list[tuple[str, Decimal]]] = {i: [] for i in ids}
    if not ids:
        return fatores
    cur.execute(
        """SELECT id AS id_produto, upper(um_compra) AS um, fator_compra AS fator
             FROM produtos
            WHERE id = ANY(%(ids)s) AND um_compra IS NOT NULL AND fator_compra > 0
           UNION
           SELECT id_produto, upper(um), fator FROM produto_unidades
            WHERE id_produto = ANY(%(ids)s) AND fator > 0""",
        {"ids": ids},
    )
    for r in cur.fetchall():
        f = dec(r["fator"])
        if f != 1 and (r["um"], f) not in fatores[r["id_produto"]]:
            fatores[r["id_produto"]].append((r["um"], f))
    return fatores


def _embalagem_que_explica(razao_entre: Decimal, fatores: list[tuple[str, Decimal]]):
    """A embalagem cujo fator é a razão entre os dois custos — ou nada."""
    for um, f in fatores:
        if f > 0 and abs(razao_entre / f - 1) <= FOLGA_DO_FATOR:
            return um, f
    return None


def suspeitos(cur, id_unidade: int) -> dict:
    """Os produtos cuja referência não bate com o que o resto do sistema sabe.

    Duas testemunhas, nesta ordem:

    1. **O razão.** Uma saída sem saldo grava o custo do dia na prateleira, e ele
       fica lá. Se a referência de hoje é uma vez e meia isso (para qualquer
       lado), um dos dois mudou depois — e, quando a razão entre eles é o fator
       de uma embalagem do produto, dá para dizer qual: a referência virou o
       preço da caixa.
    2. **O preço de venda.** Mercadoria custeada ACIMA do que é vendida. Sozinho
       não diz o número certo; diz que há o que olhar. Se dividir pela embalagem
       traz o custo para baixo do preço, a divisão é a sugestão.

    ⚠️ **`confianca` decide o que a tela já traz marcado.** "alta" é quando duas
    coisas independentes concordam (o razão E a embalagem, ou o razão E o preço).
    O resto vem desmarcado: é palpite, e palpite precisa de um sim de alguém.

    ⚠️ **Insumo sem razão e sem preço de venda fica de fora** — não há contra o
    que comparar. Esse só se acerta pela nota de compra.
    """
    cur.execute(
        f"""
        SELECT p.id, p.codigo, p.nome, p.tipo, p.um_estoque, p.um_omie,
               p.custo_referencia AS referencia, p.custo_referencia_em AS desde,
               p.custo_referencia_origem AS origem,
               coalesce(
                 (SELECT s.custo_medio FROM estoque_saldos s
                   WHERE s.id_produto = p.id AND s.id_unidade = %(unidade)s
                     AND s.custo_medio > 0
                   ORDER BY s.quantidade DESC LIMIT 1),
                 (SELECT m.custo_medio_apos FROM estoque_movimentos m
                   WHERE m.id_produto = p.id AND m.id_unidade = %(unidade)s
                     AND m.custo_medio_apos > 0
                     AND (m.um IS NULL OR p.um_estoque IS NULL
                          OR upper(m.um) = upper(p.um_estoque))
                   ORDER BY m.id DESC LIMIT 1)) AS razao,
               {precos.sql_vigente()} AS preco
          FROM produtos p
         WHERE p.ativo AND p.custo_referencia > 0
           -- Só quem a cascata custeia pela referência: sem prateleira valorada
           -- com saldo nesta loja e sem preço de fornecedor.
           AND NOT EXISTS (SELECT 1 FROM estoque_saldos s
                            WHERE s.id_produto = p.id AND s.id_unidade = %(unidade)s
                              AND s.quantidade > 0 AND s.custo_medio > 0)
           AND NOT EXISTS (SELECT 1 FROM produto_fornecedor pf
                            WHERE pf.id_produto = p.id AND pf.ultimo_preco IS NOT NULL)
         ORDER BY lower(p.nome)
        """,
        {"unidade": id_unidade},
    )
    candidatos = [dict(r) for r in cur.fetchall()]
    fatores = _fatores(cur, [c["id"] for c in candidatos])

    linhas = []
    for c in candidatos:
        ref = dec(c["referencia"])
        razao = dec(c["razao"]) if c["razao"] is not None else None
        preco = dec(c["preco"]) if c["preco"] is not None else None
        # Quem é feito na casa custa pela ficha; o preço dele não mede a referência.
        acima_do_preco = (preco is not None and preco > 0 and ref >= preco
                          and c["tipo"] not in ("PRODUZIDO", "KIT"))

        sugerido = None
        motivo = None
        confianca = "conferir"

        if razao is not None and (ref / razao >= DISCORDA or razao / ref >= DISCORDA):
            sugerido = razao
            emb = _embalagem_que_explica(ref / razao, fatores[c["id"]])
            if emb:
                motivo = (f"a referência é o preço de 1 {emb[0]} "
                          f"({_br(emb[1])} {c['um_estoque']}); o estoque saiu por unidade")
                confianca = "alta"
            elif acima_do_preco and razao < preco:
                motivo = "a referência passa do preço de venda; o razão registra menos"
                confianca = "alta"
            else:
                motivo = "a referência e o custo registrado no estoque discordam"
        elif acima_do_preco:
            motivo = "o custo de referência é maior que o preço de venda"
            for um, f in sorted(fatores[c["id"]], key=lambda x: x[1]):
                if f > 1 and ref / f < preco:
                    sugerido = ref / f
                    motivo = (f"o custo passa do preço de venda; dividido por 1 {um} "
                              f"({_br(f)} {c['um_estoque']}) fica abaixo")
                    break
        else:
            continue

        linhas.append({
            "id_produto": c["id"],
            "codigo": c["codigo"],
            "produto": c["nome"],
            "um": c["um_estoque"],
            "um_omie": c["um_omie"],
            "referencia": float(ref),
            "desde": c["desde"],
            "origem": c["origem"],
            "razao": float(razao) if razao is not None else None,
            "preco": float(preco) if preco is not None else None,
            "sugerido": float(sugerido.quantize(CASAS_CUSTO)) if sugerido is not None else None,
            "motivo": motivo,
            "confianca": confianca,
        })

    # Os de confiança alta primeiro, e dentro de cada grupo o maior desvio na
    # frente: é a ordem em que a pessoa vai querer conferir.
    linhas.sort(key=lambda l: (l["confianca"] != "alta",
                               -abs(l["referencia"] - (l["sugerido"] or 0))))
    return {
        "analisados": len(candidatos),
        "suspeitos": len(linhas),
        "certos": sum(1 for l in linhas if l["confianca"] == "alta"),
        "linhas": linhas,
    }


def _br(n: Decimal) -> str:
    return f"{n.normalize():f}".replace(".", ",")


def _recustear_vendas(cur, ids: list[int]) -> int:
    """Refaz o custo congelado das vendas que usaram a referência errada.

    ⚠️ **Só o item que DIZ ter vindo da referência** (`origem_custo`), dos
    produtos corrigidos agora. Item custeado por médio ou por ficha guarda o que
    se sabia no dia e não é tocado.
    ⚠️ **Mês FECHADO fica de fora** — a mesma fronteira de
    `importador._custear_vendas_sem_custo`: o número já foi ao contador.
    """
    from services import cmv as motor

    cur.execute(
        """SELECT vi.id, vi.id_produto, v.id_unidade
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
            WHERE vi.id_produto = ANY(%s)
              AND vi.origem_custo = 'referencia'
              AND NOT v.cancelada
              AND NOT EXISTS (
                    SELECT 1 FROM cmv_fechamentos f
                     WHERE f.id_unidade = v.id_unidade AND f.status = 'FECHADO'
                       AND v.data BETWEEN f.inicio AND f.fim)
            ORDER BY vi.id""",
        (ids,),
    )
    cache: dict[tuple[int, int], tuple] = {}
    feitos = 0
    for item in [dict(r) for r in cur.fetchall()]:
        chave = (item["id_produto"], item["id_unidade"])
        if chave not in cache:
            cache[chave] = motor.custo_teorico_do_produto(
                cur, item["id_produto"], id_unidade=item["id_unidade"])
        custo, origem = cache[chave]
        if custo is None:
            continue
        cur.execute(
            """UPDATE venda_itens SET custo_ficha_unitario = %s, origem_custo = %s
                WHERE id = %s AND custo_ficha_unitario IS DISTINCT FROM %s""",
            (custo, origem, item["id"], custo),
        )
        feitos += cur.rowcount
    return feitos


def corrigir(cur, itens: list[dict], id_usuario: int | None, id_unidade: int,
             origem: str = ORIGEM) -> dict:
    """Grava o custo de referência informado em cada produto.

    ⚠️ **O número vem de quem confirmou, não da prévia refeita aqui.** A tela
    mostra a sugestão e deixa trocar; o que foi visto e aceito é o que entra.
    ⚠️ **Cada produto ganha a sua linha na auditoria**, com o antes e o depois:
    é dinheiro mudando sem mercadoria se mover.
    """
    corrigidos = []
    for item in itens:
        novo = dec(item["custo"]).quantize(CASAS_CUSTO)
        cur.execute(
            """SELECT id, nome, custo_referencia, custo_referencia_origem
                 FROM produtos WHERE id = %s FOR UPDATE""",
            (item["id_produto"],),
        )
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404,
                                detail=f"Produto {item['id_produto']} não encontrado")
        antes = dec(p["custo_referencia"]) if p["custo_referencia"] is not None else None
        # ⚠️ Mesmo número com OUTRA origem ainda é mudança: confirmar à mão o que
        # veio do Omie é o que impede a próxima carga de passar por cima.
        if antes == novo and p["custo_referencia_origem"] == origem:
            continue
        cur.execute(
            """UPDATE produtos
                  SET custo_referencia = %s, custo_referencia_em = now(),
                      custo_referencia_origem = %s
                WHERE id = %s""",
            (novo, origem, p["id"]),
        )
        auditoria.registrar(
            cur, id_usuario, "produto", p["id"], "custo_referencia_corrigido",
            antes={"custo_referencia": float(antes) if antes is not None else None,
                   "origem": p["custo_referencia_origem"]},
            depois={"custo_referencia": float(novo), "origem": origem},
            id_unidade=id_unidade,
        )
        corrigidos.append({"id_produto": p["id"], "produto": p["nome"],
                           "de": float(antes) if antes is not None else None,
                           "para": float(novo)})

    vendas = _recustear_vendas(cur, [c["id_produto"] for c in corrigidos]) if corrigidos else 0
    return {
        "corrigidos": len(corrigidos),
        "vendas_recalculadas": vendas,
        "linhas": corrigidos,
        "message": (f"{len(corrigidos)} custo(s) de referência corrigido(s)"
                    + (f"; {vendas} item(ns) de venda recalculado(s)" if vendas else "")),
    }
