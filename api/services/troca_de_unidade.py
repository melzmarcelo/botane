"""Trocar a unidade de estoque de um produto — e levar junto o que depende dela.

🔑 **O caso do dono (08/09/2026):** "o custo está em CX, mas alteramos para o
estoque em UN e a unidade de compra CX — deve fazer a alteração. E caso haja
alteração e não for possível fazer a conversão, apresentar uma mensagem de
validação."

⚠️ **A unidade de estoque não é um rótulo: é o denominador de tudo.** Saldo,
custo médio, custo de referência, mínimo, máximo e os fatores de embalagem são
todos *por unidade de estoque*. Trocar CX por UN sem mexer neles multiplica ou
divide por doze, calado, o custo de tudo que usa o insumo — e o erro só aparece
no CMV do mês, longe da causa.

⚠️ **Quem já tem RAZÃO não troca de unidade, e isso é recusa, não conversão.**
`estoque_movimentos` é append-only: as quantidades históricas estão gravadas na
unidade antiga e não há como reescrevê-las. Converter só o cadastro deixaria o
saldo dizendo "10" numa unidade e o histórico "10" noutra — a mesma prateleira
valendo dois números diferentes. O caminho honesto é a mensagem de validação.

⚠️ **A conversão usa o conversor central** (`custos.converter` e o par
`um_compra`/`fator_compra`), nunca uma conta escrita aqui. Duas implementações
divergiriam, e a divergência seria entre o cadastro e o razão.
"""

from decimal import Decimal

from services.custos import converter, dec


def _fator(cur, id_produto: int, antiga: str, nova: str, ums: dict,
           um_compra: str | None, fator_compra) -> tuple[Decimal | None, str]:
    """Quantas unidades NOVAS cabem em uma ANTIGA. E de onde saiu o número.

    Duas fontes, nesta ordem:

    1. **A unidade de compra que está sendo cadastrada.** É o caso do pedido: o
       estoque vira UN e a compra vira CX com fator 12, então 1 CX = 12 UN. Vem
       primeiro porque é a informação que a pessoa acabou de dar, na tela, para
       este produto — mais específica que qualquer regra geral.
    2. **A grandeza** (kg↔g, L↔ml): 1 KG = 1000 G, e isso vale em qualquer
       produto.

    ⚠️ **CX, PCT, FD e BDJ não convertem entre si por grandeza** — todas são
    UNIDADE com fator 1, e a conta genérica diria 1 CX = 1 PCT. Por isso a
    fonte (1) existe: quantas unidades cabem na caixa é do PRODUTO.
    """
    if (um_compra or "").strip().upper() == antiga.strip().upper():
        f = dec(fator_compra)
        if f > 0:
            return f, f"a unidade de compra {antiga} com fator {f:g}"

    direto = converter(Decimal(1), antiga, nova, ums)
    if direto is not None and direto > 0:
        return dec(direto), "a grandeza das duas unidades"

    return None, ""


def avaliar(cur, id_produto: int, antiga: str | None, nova: str | None,
            um_compra: str | None, fator_compra, ums: dict) -> dict:
    """A troca é possível? Devolve o plano, ou o motivo da recusa.

    `{"muda": False}` quando não há troca de unidade — o caso de quase todo PUT.
    """
    a = (antiga or "").strip().upper()
    n = (nova or "").strip().upper()
    if not a or not n or a == n:
        return {"muda": False}

    # ⚠️ **O razão manda.** Antes de qualquer conta: se há movimento, a unidade
    # antiga está gravada em linhas que não se reescrevem.
    cur.execute(
        "SELECT count(*) AS n FROM estoque_movimentos WHERE id_produto = %s",
        (id_produto,),
    )
    movimentos = cur.fetchone()["n"]
    if movimentos:
        return {
            "muda": True, "pode": False,
            "motivo": (
                f"Este produto já tem {movimentos} movimento(s) de estoque gravados em {a}. "
                f"O razão não se reescreve, então trocar para {n} faria o histórico e o saldo "
                f"falarem unidades diferentes. Para mudar a unidade, zere o saldo e estorne o "
                f"que houver, ou cadastre outro produto."),
        }

    fator, origem = _fator(cur, id_produto, a, n, ums, um_compra, fator_compra)
    if not fator:
        return {
            "muda": True, "pode": False,
            "motivo": (
                f"Não dá para converter de {a} para {n}: o sistema não sabe quantos {n} cabem "
                f"em um {a}. Informe a unidade de compra {a} com o fator correspondente, ou "
                f"cadastre a embalagem do produto."),
        }

    # O que a troca leva junto, e como.
    cur.execute(
        """SELECT custo_referencia, estoque_minimo, estoque_maximo
             FROM produtos WHERE id = %s""",
        (id_produto,),
    )
    p = dict(cur.fetchone() or {})
    conversoes = []
    custo_zera = False
    # ⚠️ **O custo DIVIDE, as quantidades MULTIPLICAM.** O custo é por unidade:
    # se a caixa de 12 custava 60, a unidade custa 5. A quantidade é o inverso:
    # um mínimo de 2 caixas é um mínimo de 24 unidades. Trocar os dois sentidos
    # é o engano natural aqui, e daria 720 de custo por unidade.
    if p.get("custo_referencia") is not None:
        antes_custo = dec(p["custo_referencia"])
        depois_custo = antes_custo / fator
        conversoes.append({
            "campo": "custo_referencia",
            "de": float(antes_custo),
            "para": float(depois_custo),
        })
        # 🔑 **"O custo vai ZERAR" é a pergunta que precisa ser feita antes**
        # (09/09/2026, relatado pelo dono). Aconteceu com uma caixa de 1.000
        # unidades a R$ 33,99: um fator de conversão invertido dividiu por mil, o
        # custo virou R$ 0,03 — que a tela mostra com duas casas como 0,00 — e
        # nada avisou. Corrigir o fator de volta NÃO desfaz, porque a conversão
        # só roda quando a unidade muda, e `custo_referencia` não é editável por
        # tela nenhuma. O valor some e não volta.
        #
        # ⚠️ **O corte é a QUEDA, não o valor final.** A primeira versão perguntou
        # só quando o resultado ficava abaixo de meio centavo — e o caso real não
        # passou: R$ 33,99 ÷ 1000 dá R$ 0,03, que não é "zero" para o computador
        # e é exatamente "zerado" para quem olha. O que denuncia o engano é a
        # ORDEM DE GRANDEZA: dividir o custo por cem ou mais quase nunca é o que
        # alguém quis fazer de propósito.
        #
        # ⚠️ Uma conversão legítima e grande (KG para G divide por mil) também
        # cai aqui e pede confirmação. É o preço certo a pagar: o Sim custa um
        # clique, e o Não custa o custo do produto.
        custo_zera = bool(
            antes_custo > 0
            and (depois_custo < Decimal("0.01")
                 or antes_custo / depois_custo >= 100)
        )
    for campo in ("estoque_minimo", "estoque_maximo"):
        if p.get(campo) is not None:
            conversoes.append({
                "campo": campo,
                "de": float(dec(p[campo])),
                "para": float(dec(p[campo]) * fator),
            })

    # ⚠️ **As embalagens também são POR unidade de estoque.** `produto_unidades.
    # fator` diz quantas unidades de estoque cabem em uma embalagem: com o
    # estoque em CX, a caixa tinha fator 1; com o estoque em UN ela passa a
    # valer 12. Deixá-las como estavam faria a nota de uma caixa baixar uma
    # unidade.
    cur.execute(
        "SELECT count(*) AS n FROM produto_unidades WHERE id_produto = %s", (id_produto,))
    embalagens = cur.fetchone()["n"]

    return {
        "muda": True, "pode": True,
        # Verdadeiro quando o custo desaparece aos olhos de quem olha. Quem
        # chama tem de perguntar antes de gravar.
        "custo_zera": custo_zera,
        "de": a, "para": n,
        "fator": float(fator), "origem_do_fator": origem,
        "conversoes": conversoes,
        "embalagens": embalagens,
        "resumo": (f"1 {a} = {fator:g} {n} (por {origem})."),
    }


def aplicar(cur, id_produto: int, plano: dict, id_usuario: int | None = None) -> None:
    """Grava as conversões do plano. Só é chamado quando `pode` é verdadeiro.

    ⚠️ **Roda no MESMO cursor do UPDATE do produto.** Se a gravação da unidade
    falhar, a conversão do custo tem de falhar junto — meio caminho aqui é um
    custo dividido por doze num produto que continuou em caixa.
    """
    fator = dec(plano["fator"])
    for c in plano["conversoes"]:
        cur.execute(
            f"UPDATE produtos SET {c['campo']} = %s WHERE id = %s",
            (c["para"], id_produto),
        )
    if plano.get("embalagens"):
        cur.execute(
            "UPDATE produto_unidades SET fator = fator * %s WHERE id_produto = %s",
            (fator, id_produto),
        )

    # 🔑 **O que a conversão reescreveu fica GRAVADO.** O `PUT` do produto audita
    # nome, tipo, status e unidades — o custo não estava na lista, então uma
    # troca de unidade errada apagava o valor antigo sem deixar de onde
    # recuperá-lo. Foi assim que R$ 33,99 viraram R$ 0,03 e não houve como
    # voltar. Aqui fica o antes e o depois de cada campo.
    import auditoria

    auditoria.registrar(
        cur, id_usuario, "produto", id_produto, "troca_de_unidade",
        antes={c["campo"]: c["de"] for c in plano["conversoes"]},
        depois={
            **{c["campo"]: c["para"] for c in plano["conversoes"]},
            "de": plano.get("de"), "para": plano.get("para"),
            "fator": plano.get("fator"),
        },
    )
