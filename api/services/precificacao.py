"""Precificação — a configuração da loja, a conta do preço e a aplicação.

🔑 **Pedido do dono (05/10/2026)**; o estudo é `docs/precificacao-estudo.md` e as
decisões que este arquivo carrega são as dele:

1. **Por loja, podendo seguir outra.** `precificacao_config.id_unidade_origem`
   preenchido quer dizer "esta loja usa a configuração daquela" — e aí aqui é
   só consulta. Sem corrente: quem é seguido não pode seguir ninguém.
2. **Cada linha vale para TUDO, para uma CATEGORIA ou para um SETOR.** A mais
   específica de mesmo nome SUBSTITUI a geral (categoria ganha de setor, que
   ganha de tudo). É o que deixa o custo operacional ser único, por categoria
   ou por setor sem três mecanismos.
3. **O preço aplicado vale na hora.** Se ele vai ao PDV, quem decide é o
   parâmetro de envio da loja — a fila de pendências já nasce sozinha, pelo
   gatilho de `produto_precos` (migração 044).

🔑 **A conta é o markup divisor**, e mora AQUI e só aqui:

    preço sugerido = custo direto ÷ (1 − soma dos percentuais sobre a venda)

com a margem dentro da soma. ⚠️ Não é "custo + percentual": imposto e cartão
incidem sobre o PREÇO, e somar sobre o custo come a margem inteira.

⚠️ **O sugerido é o PISO**, não o alvo: o menor preço que entrega a margem.
Produto vendido acima dele tem FOLGA, e a análise não manda baixar preço.
⚠️ **Dinheiro e percentual em `Decimal`**, nunca float. ⚠️ **Sem custo não há
sugestão** — nulo, nunca zero.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from fastapi import HTTPException

import auditoria
from services import cmv as motor_cmv
from services import precos

CEM = Decimal(100)
CENTAVO = Decimal("0.01")
MARGEM = "MARGEM"
PERCENTUAL = "PERCENTUAL"
VALOR = "VALOR"


def dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


# ---------------------------------------------------------------- a configuração


def _linhas(cur, id_unidade: int) -> list[dict]:
    cur.execute(
        """SELECT l.id, l.nome, l.tipo, l.valor, l.alcance, l.id_categoria, l.id_setor,
                  c.nome AS categoria, s.nome AS setor
             FROM precificacao_linhas l
             LEFT JOIN categorias c ON c.id = l.id_categoria
             LEFT JOIN setores s ON s.id = l.id_setor
            WHERE l.id_unidade = %s
            ORDER BY CASE l.tipo WHEN 'PERCENTUAL' THEN 0 WHEN 'VALOR' THEN 1 ELSE 2 END,
                     l.ordem, l.id""",
        (id_unidade,),
    )
    return [dict(r) for r in cur.fetchall()]


def config(cur, id_unidade: int) -> dict:
    """A configuração que VALE para esta loja — a dela, ou a de quem ela segue.

    ⚠️ Loja sem configuração nenhuma não é erro: devolve a forma vazia, e a
    análise responde "configure antes" em vez de calcular com zeros.
    """
    cur.execute(
        """SELECT k.id_unidade_origem, k.arredondamento, k.atualizado_em,
                  coalesce(nullif(o.apelido, ''), o.nome) AS origem
             FROM precificacao_config k
             LEFT JOIN unidades o ON o.id = k.id_unidade_origem
            WHERE k.id_unidade = %s""",
        (id_unidade,),
    )
    propria = cur.fetchone()
    id_efetiva = (propria or {}).get("id_unidade_origem") or id_unidade
    arredondamento = "NOVENTA"
    if propria and not propria["id_unidade_origem"]:
        arredondamento = propria["arredondamento"]
    elif propria:
        cur.execute("SELECT arredondamento FROM precificacao_config WHERE id_unidade = %s",
                    (id_efetiva,))
        da_origem = cur.fetchone()
        arredondamento = da_origem["arredondamento"] if da_origem else "NOVENTA"

    cur.execute(
        """SELECT u.id, coalesce(nullif(u.apelido, ''), u.nome) AS nome
             FROM precificacao_config k JOIN unidades u ON u.id = k.id_unidade
            WHERE k.id_unidade_origem = %s ORDER BY 2""",
        (id_unidade,),
    )
    seguidores = [dict(r) for r in cur.fetchall()]
    linhas = _linhas(cur, id_efetiva)
    return {
        "id_unidade": id_unidade,
        # 🔑 `somente_leitura`: esta loja segue outra, e é lá que se edita.
        "somente_leitura": id_efetiva != id_unidade,
        "id_unidade_origem": (propria or {}).get("id_unidade_origem"),
        "origem": (propria or {}).get("origem"),
        "seguida_por": seguidores,
        "arredondamento": arredondamento,
        "linhas": [l | {"valor": float(l["valor"])} for l in linhas],
        "configurada": any(l["tipo"] != VALOR for l in linhas),
        "_linhas": linhas,          # com `Decimal`, para a conta; não sai pela rota
    }


def salvar(cur, id_unidade: int, corpo: dict, id_usuario: int, ve_unidade) -> dict:
    """Grava a configuração INTEIRA da loja (ou a decisão de seguir outra)."""
    origem = corpo.get("id_unidade_origem")
    cur.execute("SELECT id_unidade_origem FROM precificacao_config WHERE id_unidade = %s",
                (id_unidade,))
    anterior = cur.fetchone()
    seguia = (anterior or {}).get("id_unidade_origem")

    if origem is not None:
        if origem == id_unidade:
            raise HTTPException(status_code=400, detail="A loja não pode seguir a si mesma.")
        cur.execute(
            """SELECT u.ativo, coalesce(nullif(u.apelido, ''), u.nome) AS nome,
                      k.id_unidade_origem
                 FROM unidades u LEFT JOIN precificacao_config k ON k.id_unidade = u.id
                WHERE u.id = %s""", (origem,))
        alvo = cur.fetchone()
        # ⚠️ Loja que a pessoa não enxerga responde igual à que não existe.
        if not alvo or not alvo["ativo"] or not ve_unidade(origem):
            raise HTTPException(status_code=404, detail="Loja de origem não encontrada.")
        # ⚠️ **Sem corrente.** A seguiria B, que segue C: a pergunta "de quem é a
        # configuração de A?" passaria a depender de dois saltos, e um dia de um
        # laço. Segue-se quem TEM a configuração.
        if alvo["id_unidade_origem"]:
            raise HTTPException(
                status_code=409,
                detail=(f"{alvo['nome']} também segue a configuração de outra loja. "
                        "Escolha a loja que tem a configuração própria."))
        cur.execute(
            """SELECT coalesce(nullif(u.apelido, ''), u.nome) AS nome
                 FROM precificacao_config k JOIN unidades u ON u.id = k.id_unidade
                WHERE k.id_unidade_origem = %s LIMIT 1""", (id_unidade,))
        seguidor = cur.fetchone()
        if seguidor:
            raise HTTPException(
                status_code=409,
                detail=(f"{seguidor['nome']} segue a configuração desta loja — ela não pode "
                        "passar a seguir outra. Mude lá primeiro."))

    linhas = [] if origem is not None else list(corpo.get("linhas") or [])
    # 🔑 **Voltar de "seguir outra" para "própria" sem mandar linha COPIA a
    # herdada.** Começar do zero deixaria a loja sem sugestão de preço até
    # alguém preencher tudo de novo.
    if origem is None and seguia and not linhas:
        linhas = [{"nome": l["nome"], "tipo": l["tipo"], "valor": l["valor"],
                   "alcance": l["alcance"], "id_categoria": l["id_categoria"],
                   "id_setor": l["id_setor"]} for l in _linhas(cur, seguia)]

    # ⚠️ Categoria ou setor que não existe estouraria na chave estrangeira, como
    # 500 sem frase. Conferido antes, com o nome da linha na mensagem.
    for tabela, campo, palavra in (("categorias", "id_categoria", "categoria"),
                                   ("setores", "id_setor", "setor")):
        pedidos = {l[campo] for l in linhas if l.get(campo) is not None}
        if pedidos:
            cur.execute(f"SELECT id FROM {tabela} WHERE id = ANY(%s)", (list(pedidos),))
            achados = {r["id"] for r in cur.fetchall()}
            falta = next((l for l in linhas if l.get(campo) is not None
                          and l[campo] not in achados), None)
            if falta:
                raise HTTPException(
                    status_code=400,
                    detail=f"“{falta['nome']}”: a {palavra} escolhida não existe mais.")

    vistos = set()
    for l in linhas:
        chave = (l["tipo"], l["nome"].strip().lower(), l["alcance"],
                 l.get("id_categoria"), l.get("id_setor"))
        if chave in vistos:
            raise HTTPException(
                status_code=400,
                detail=f"“{l['nome']}” aparece duas vezes para o mesmo alcance.")
        vistos.add(chave)
    # ⚠️ **A soma GERAL não pode chegar a 100%**: com 100% ou mais não existe
    # preço que pague a conta. As combinações por categoria e por setor são
    # conferidas na hora de calcular — e aí o produto fica sem sugestão, com o
    # motivo, em vez de a gravação recusar por um caso que talvez nem ocorra.
    gerais = sum((dec(l["valor"]) for l in linhas
                  if l["tipo"] != VALOR and l["alcance"] == "TUDO"), Decimal(0))
    if gerais >= CEM:
        raise HTTPException(
            status_code=400,
            detail=(f"Os percentuais que valem para tudo somam {gerais.normalize():f}%, com a "
                    "margem. Com 100% ou mais não existe preço que pague a conta."))

    cur.execute(
        """INSERT INTO precificacao_config (id_unidade, id_unidade_origem, arredondamento,
                                            atualizado_por, atualizado_em)
           VALUES (%s, %s, %s, %s, now())
           ON CONFLICT (id_unidade) DO UPDATE
               SET id_unidade_origem = EXCLUDED.id_unidade_origem,
                   arredondamento = EXCLUDED.arredondamento,
                   atualizado_por = EXCLUDED.atualizado_por, atualizado_em = now()""",
        (id_unidade, origem, corpo.get("arredondamento") or "NOVENTA", id_usuario),
    )
    # ⚠️ Seguindo outra loja, as linhas daqui não são tocadas — só deixam de valer.
    if origem is None:
        cur.execute("DELETE FROM precificacao_linhas WHERE id_unidade = %s", (id_unidade,))
        for ordem, l in enumerate(linhas):
            cur.execute(
                """INSERT INTO precificacao_linhas (id_unidade, nome, tipo, valor, alcance,
                                                    id_categoria, id_setor, ordem)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (id_unidade, l["nome"].strip(), l["tipo"], dec(l["valor"]), l["alcance"],
                 l.get("id_categoria"), l.get("id_setor"), ordem),
            )
    auditoria.registrar(cur, id_usuario, "precificacao", id_unidade, "configurar",
                        depois={"segue": origem, "linhas": len(linhas),
                                "arredondamento": corpo.get("arredondamento")},
                        id_unidade=id_unidade)
    return config(cur, id_unidade)


# ---------------------------------------------------------------- a conta


def resolver(linhas: list[dict], id_categoria: int | None, id_setor: int | None) -> dict:
    """As linhas que valem para UM produto, depois da precedência.

    🔑 **A mais específica de mesmo nome substitui a geral**: categoria ganha de
    setor, que ganha de tudo. Linha que só existe para outra categoria
    simplesmente não se aplica (é o caso da taxa que só o delivery paga).
    """
    escolhida: dict[tuple, tuple[int, dict]] = {}
    for l in linhas:
        if l["alcance"] == "CATEGORIA":
            if l["id_categoria"] != id_categoria or id_categoria is None:
                continue
            peso = 2
        elif l["alcance"] == "SETOR":
            if l["id_setor"] != id_setor or id_setor is None:
                continue
            peso = 1
        else:
            peso = 0
        # A margem é UMA por produto, qualquer que seja o nome da linha.
        chave = (MARGEM,) if l["tipo"] == MARGEM else (l["tipo"], l["nome"].strip().lower())
        if chave not in escolhida or peso > escolhida[chave][0]:
            escolhida[chave] = (peso, l)
    valem = [l for _p, l in escolhida.values()]
    return {
        "percentuais": [{"nome": l["nome"], "pct": dec(l["valor"]), "alcance": l["alcance"]}
                        for l in valem if l["tipo"] == PERCENTUAL],
        "valores": [{"nome": l["nome"], "valor": dec(l["valor"]), "alcance": l["alcance"]}
                    for l in valem if l["tipo"] == VALOR],
        "margem": next((dec(l["valor"]) for l in valem if l["tipo"] == MARGEM), Decimal(0)),
    }


def arredondar(valor: Decimal, modo: str) -> Decimal:
    """Sempre PARA CIMA: arredondar para baixo entrega a margem recém-calculada."""
    if modo == "NOVENTA":
        base = valor.to_integral_value(rounding="ROUND_FLOOR") + Decimal("0.90")
        return base if base >= valor else base + 1
    if modo == "MEIO":
        return (valor * 2).to_integral_value(rounding=ROUND_CEILING) / 2
    return valor.quantize(CENTAVO, rounding=ROUND_CEILING)


def calcular(custo, preco, regra: dict, modo: str) -> dict:
    """A conta de UM produto: o custo direto, o piso sugerido e a leitura do preço atual."""
    soma = sum((p["pct"] for p in regra["percentuais"]), Decimal(0))
    por_unidade = sum((v["valor"] for v in regra["valores"]), Decimal(0))
    margem = regra["margem"]
    custo_direto = (dec(custo) + por_unidade) if custo is not None else None

    sugerido, motivo = None, None
    if custo_direto is None:
        motivo = "sem_custo"
    elif soma + margem >= CEM:
        # A combinação DESTE produto (categoria/setor) não fecha: não há preço possível.
        motivo = "soma_acima_de_100"
    else:
        sugerido = arredondar(custo_direto / (1 - (soma + margem) / CEM), modo)

    leitura = None
    if custo_direto is not None and preco:
        preco = dec(preco)
        lucro = preco - (preco * soma / CEM) - custo_direto
        leitura = {
            "lucro": lucro.quantize(CENTAVO, rounding=ROUND_HALF_UP),
            "lucro_pct": (lucro / preco * CEM).quantize(CENTAVO, rounding=ROUND_HALF_UP),
            "food_cost_pct": (custo_direto / preco * CEM).quantize(CENTAVO, rounding=ROUND_HALF_UP),
        }
    return {"custo_direto": custo_direto, "soma_pct": soma, "margem_pct": margem,
            "sugerido": sugerido, "motivo": motivo, "leitura": leitura}


def decompor(custo_direto: Decimal, preco: Decimal, regra: dict) -> list[dict]:
    """De cada venda a este preço: para onde vai cada real. É a barra da tela."""
    partes = [{"nome": p["nome"], "tipo": "percentual", "pct": float(p["pct"]),
               "valor": float((preco * p["pct"] / CEM).quantize(CENTAVO, rounding=ROUND_HALF_UP))}
              for p in regra["percentuais"]]
    partes.append({"nome": "Custo direto", "tipo": "custo", "pct": None,
                   "valor": float(custo_direto.quantize(CENTAVO, rounding=ROUND_HALF_UP))})
    lucro = preco - sum((preco * p["pct"] / CEM for p in regra["percentuais"]), Decimal(0)) \
        - custo_direto
    partes.append({"nome": "Lucro" if lucro >= 0 else "Prejuízo",
                   "tipo": "lucro" if lucro >= 0 else "prejuizo", "pct": None,
                   "valor": float(lucro.quantize(CENTAVO, rounding=ROUND_HALF_UP))})
    return partes


def _f(v):
    return float(v) if v is not None else None


# ---------------------------------------------------------------- a análise


def analise(cur, id_unidade: int, dias: int = 30, limite: int = 200,
            id_produto: int | None = None) -> dict:
    """Os produtos vendidos nos últimos `dias`: quais estão abaixo da margem, e quanto isso pesa.

    🔑 **A ordem é a do IMPACTO no mês** (diferença × quantidade vendida), com
    quem vende abaixo do custo na frente de todos. Um real a menos no café que
    sai 400 vezes pesa mais que dez no prato que sai quatro.
    ⚠️ **O custo é o de HOJE** (`cmv.custo_teorico_do_produto`), não o congelado
    na última venda: precifica-se para a frente, com o que os ingredientes
    custam agora.
    ⚠️ **O volume é o que passou**: o impacto é "se vender a mesma quantidade".
    """
    k = config(cur, id_unidade)
    cur.execute(
        f"""SELECT p.id, p.codigo, p.nome, p.id_categoria, p.id_setor,
                   c.nome AS categoria, s.nome AS setor,
                   sum(vi.quantidade) AS quantidade, sum(vi.valor_total) AS receita,
                   {precos.sql_vigente("p.id", "%(u)s")} AS preco
              FROM venda_itens vi
              JOIN vendas v ON v.id = vi.id_venda
              JOIN produtos p ON p.id = vi.id_produto
              LEFT JOIN categorias c ON c.id = p.id_categoria
              LEFT JOIN setores s ON s.id = p.id_setor
             WHERE v.id_unidade = %(u)s AND NOT v.cancelada AND p.ativo
               AND v.data >= current_date - %(dias)s
               -- ⚠️ A lista é cortada pelos que mais faturam; fixar UM produto é o que
               -- deixa perguntar por ele quando ele não está entre os primeiros.
               AND (%(p)s::int IS NULL OR p.id = %(p)s)
             GROUP BY p.id, p.codigo, p.nome, p.id_categoria, p.id_setor, c.nome, s.nome
             ORDER BY sum(vi.valor_total) DESC
             LIMIT %(limite)s""",
        {"u": id_unidade, "dias": dias, "limite": limite, "p": id_produto},
    )
    produtos = [dict(r) for r in cur.fetchall()]

    itens = []
    for p in produtos:
        custo, origem = motor_cmv.custo_teorico_do_produto(cur, p["id"], id_unidade=id_unidade)
        regra = resolver(k["_linhas"], p["id_categoria"], p["id_setor"])
        conta = calcular(custo, p["preco"], regra, k["arredondamento"])
        preco = dec(p["preco"]) if p["preco"] is not None else None
        sug = conta["sugerido"]
        diferenca = (sug - preco) if (sug is not None and preco is not None) else None
        abaixo = diferenca is not None and diferenca > Decimal("0.005")
        qtd = dec(p["quantidade"] or 0)
        prejuizo = bool(conta["leitura"] and conta["leitura"]["lucro"] < 0)
        if conta["motivo"] == "sem_custo":
            situacao = "sem_custo"
        elif preco is None:
            situacao = "sem_preco"
        elif conta["motivo"]:
            situacao = "sem_conta"
        elif prejuizo:
            situacao = "prejuizo"
        elif abaixo:
            situacao = "abaixo"
        else:
            situacao = "na_margem"
        itens.append({
            "id_produto": p["id"], "codigo": p["codigo"], "nome": p["nome"],
            "categoria": p["categoria"], "setor": p["setor"],
            "origem_custo": origem if custo is not None else None,
            "custo_direto": _f(conta["custo_direto"]),
            "preco": _f(preco), "sugerido": _f(sug),
            "margem_alvo_pct": _f(conta["margem_pct"]), "soma_pct": _f(conta["soma_pct"]),
            "lucro": _f(conta["leitura"]["lucro"]) if conta["leitura"] else None,
            "lucro_pct": _f(conta["leitura"]["lucro_pct"]) if conta["leitura"] else None,
            # Positiva: falta para chegar ao piso. Negativa: é a FOLGA — não é sugestão de baixar.
            "diferenca": _f(diferenca),
            "vendido": float(qtd),
            "impacto": _f((diferenca * qtd).quantize(CENTAVO)) if abaixo else None,
            "situacao": situacao,
        })
    ordem = {"prejuizo": 0, "abaixo": 1, "sem_preco": 2, "sem_custo": 3, "sem_conta": 3,
             "na_margem": 4}
    itens.sort(key=lambda i: (ordem[i["situacao"]], -(i["impacto"] or 0), -i["vendido"]))
    com_conta = [i for i in itens if i["lucro"] is not None]
    return {
        "dias": dias,
        "configurada": k["configurada"],
        "somente_leitura": k["somente_leitura"], "origem": k["origem"],
        "resumo": {
            "produtos": len(itens),
            "abaixo": sum(1 for i in itens if i["situacao"] in ("abaixo", "prejuizo")),
            "prejuizo": sum(1 for i in itens if i["situacao"] == "prejuizo"),
            "sem_custo": sum(1 for i in itens if i["situacao"] == "sem_custo"),
            "com_conta": len(com_conta),
            "impacto": round(sum(i["impacto"] or 0 for i in itens), 2),
        },
        "itens": itens,
    }


def simular(cur, id_unidade: int, id_produto: int, preco) -> dict:
    """De cada venda deste produto a `preco`: para onde vai cada real, e o que sobra."""
    cur.execute("SELECT id, nome, id_categoria, id_setor FROM produtos WHERE id = %s",
                (id_produto,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    k = config(cur, id_unidade)
    custo, origem = motor_cmv.custo_teorico_do_produto(cur, id_produto, id_unidade=id_unidade)
    regra = resolver(k["_linhas"], p["id_categoria"], p["id_setor"])
    conta = calcular(custo, preco, regra, k["arredondamento"])
    if conta["custo_direto"] is None:
        raise HTTPException(
            status_code=409,
            detail=f"{p['nome']} ainda não tem custo conhecido — sem custo não há o que simular.")
    return {
        "id_produto": id_produto, "preco": float(preco),
        "origem_custo": origem,
        "custo_direto": _f(conta["custo_direto"]),
        "sugerido": _f(conta["sugerido"]),
        "margem_alvo_pct": _f(conta["margem_pct"]),
        "lucro": _f(conta["leitura"]["lucro"]),
        "lucro_pct": _f(conta["leitura"]["lucro_pct"]),
        "food_cost_pct": _f(conta["leitura"]["food_cost_pct"]),
        "partes": decompor(conta["custo_direto"], dec(preco), regra),
        "valores_por_unidade": [{"nome": v["nome"], "valor": float(v["valor"])}
                                for v in regra["valores"]],
    }


# ---------------------------------------------------------------- aplicar


def aplicar(cur, id_unidade: int, itens: list[dict], id_usuario: int) -> dict:
    """Grava os preços escolhidos. Vale na hora.

    🔑 **De quem é o preço gravado:** se o produto já tem preço próprio DESTA
    loja, é ele que muda. Senão, numa casa de uma loja só muda o preço da casa
    (que é o único que existe); com mais de uma, nasce um preço da LOJA — a
    configuração é por loja, e mexer no preço da casa mudaria o cardápio das
    outras sem ninguém de lá ter pedido.
    ⚠️ **O envio ao PDV não é decidido aqui.** A pendência nasce sozinha pelo
    gatilho de `produto_precos` para o produto integrado; se ela é ENVIADA,
    quem diz é `integracoes.enviar_ao_pdv`. A resposta conta os dois, para a
    tela dizer a verdade sobre o caixa.
    """
    cur.execute("SELECT count(*) AS n FROM unidades WHERE ativo")
    varias_lojas = cur.fetchone()["n"] > 1
    aplicados, iguais, integrados = [], 0, 0
    for item in itens:
        cur.execute("SELECT id, nome, ativo, integrado_pdv FROM produtos WHERE id = %s",
                    (item["id_produto"],))
        p = cur.fetchone()
        if not p or not p["ativo"]:
            raise HTTPException(
                status_code=404,
                detail=f"Produto {item['id_produto']} não encontrado ou inativo.")
        cur.execute(
            """SELECT 1 FROM produto_precos
                WHERE id_produto = %s AND id_unidade = %s AND vigente_ate IS NULL""",
            (p["id"], id_unidade))
        tem_da_loja = cur.fetchone() is not None
        dono = id_unidade if (tem_da_loja or varias_lojas) else None
        antes = precos.vigente(cur, p["id"], id_unidade)
        novo = dec(item["preco"]).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if not precos.gravar(cur, p["id"], novo, id_usuario, dono):
            iguais += 1
            continue
        auditoria.registrar(cur, id_usuario, "produto", p["id"], "precificacao_aplicar",
                            antes={"preco_venda": _f(antes)}, depois={"preco_venda": float(novo)},
                            id_unidade=id_unidade)
        aplicados.append({"id_produto": p["id"], "nome": p["nome"], "de": _f(antes),
                          "para": float(novo), "da_loja": dono is not None})
        integrados += 1 if p["integrado_pdv"] else 0

    cur.execute(
        """SELECT enviar_ao_pdv FROM integracoes
            WHERE id_unidade = %s AND servico = 'PDV_LEGAL'""", (id_unidade,))
    linha = cur.fetchone()
    return {"aplicados": aplicados, "sem_mudanca": iguais,
            "integrados_ao_pdv": integrados,
            "envia_ao_pdv": bool(linha and linha["enviar_ao_pdv"])}


def faturamento_recente(cur, id_unidade: int, meses: int = 3) -> list[dict]:
    """O faturamento dos últimos meses FECHADOS — a base da calculadora do custo operacional."""
    cur.execute(
        """SELECT to_char(date_trunc('month', v.data), 'YYYY-MM') AS mes,
                  sum(v.valor_total) AS receita
             FROM vendas v
            WHERE v.id_unidade = %s AND NOT v.cancelada
              AND v.data >= date_trunc('month', current_date) - make_interval(months => %s)
              AND v.data < date_trunc('month', current_date)
            GROUP BY 1 ORDER BY 1""",
        (id_unidade, meses),
    )
    return [{"mes": r["mes"], "receita": float(r["receita"] or 0)} for r in cur.fetchall()]
