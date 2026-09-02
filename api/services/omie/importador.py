"""Importador de notas de entrada: do Omie até o razão de estoque.

O caminho, e o que cada passo garante:

    ListarRecebimentos ─▶ notas_entrada   chave da NF-e única: reimportar não duplica
                  ─▶ CONCILIAÇÃO          item da nota encontra (ou não) o produto daqui
                  ─▶ CONVERSÃO            unidade da nota (CX) → unidade de estoque (KG)
                  ─▶ RATEIO               frete, desconto e IPI/ST diluídos por valor
                  ─▶ ENTRADA_NF           uma por item, pelo motor de custo médio

**Item sem produto não entra no estoque.** A nota fica conciliada pela metade e
aparece na fila de pendências — importar errado é pior que não importar.
"""

import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from fastapi import HTTPException

from services import estoque as motor
from services import custos
from services.custos import CASAS_CUSTO, dec
from services.omie import mapeadores
from services.omie import vinculo
from services.omie.cliente import DIALETO_HUNGARO, DIALETO_POSICAO, ClienteOmie, ErroOmie

SISTEMA = "OMIE"


# ---------------------------------------------------------------- utilidades


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.lower().split())


def _semelhanca(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio() * 100


def _ums(cur) -> dict:
    cur.execute("SELECT sigla, grandeza, fator_base FROM unidades_medida")
    return {r["sigla"]: dict(r) for r in cur.fetchall()}


def _registrar(cur, servico: str, chamada: str, status: str, registros: int = 0,
               mensagem: str | None = None, modo: str = "simulado", pagina: int | None = None):
    cur.execute(
        """INSERT INTO sync_log (servico, chamada, pagina, registros, status, mensagem, modo,
                                 terminado_em)
           VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
        (servico, chamada, pagina, registros, status, mensagem, modo),
    )


# ---------------------------------------------------------------- conciliação


def conciliar_item(cur, item: dict, id_fornecedor: int | None) -> tuple[int | None, int | None,
                                                                        float | None, str]:
    """A cascata do de-para. Devolve (id_produto, sugestão, score, como).

    Só os três primeiros níveis vinculam sozinhos. Semelhança de texto **sugere**:
    "FILÉ FRANGO CONG" e "FILE FRANGO RESF" são parecidos e não são a mesma coisa,
    e errar aqui contamina o custo de dois produtos ao mesmo tempo.
    """
    codigo = item.get("codigo_fornecedor")
    ean = item.get("codigo_barras")

    # 1. vínculo que alguém já confirmou
    if codigo:
        cur.execute(
            "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
            (SISTEMA, codigo),
        )
        achado = cur.fetchone()
        if achado:
            return achado["id_produto"], None, 100.0, "vinculo"

    # 2. identidade do produto no próprio Omie. O item do recebimento traz o
    # `nIdProduto`, e o catálogo importado guardou esse mesmo número em
    # `codigo_omie`: é o de-para que o Omie já fez, e não depende de EAN nem de
    # texto. Quem importou o catálogo antes das notas encontra tudo por aqui.
    # 🔑 **A coluna, e depois os APELIDOS** (`vinculo.por_codigo_omie`). Um
    # produto da casa pode ser vários lá — o catálogo cria um cadastro por
    # código, e o ABACATE aparece uma vez por fornecedor. Ao juntá-los, o código
    # do absorvido vira apelido; sem este passo, a próxima nota que o trouxesse
    # não acharia o principal e o duplicado renasceria.
    if item.get("codigo_omie"):
        achado = vinculo.por_codigo_omie(cur, item["codigo_omie"])
        if achado:
            return achado, None, 100.0, "codigo_omie"

    # 3. EAN — chave natural, não depende de quem digitou
    if ean:
        cur.execute(
            "SELECT id FROM produtos WHERE codigo_barras = %s AND ativo", (ean,)
        )
        achado = cur.fetchone()
        if achado:
            return achado["id"], None, 100.0, "ean"

    # 4. código no fornecedor — resolve hortifrúti e distribuidor sem EAN.
    # Só produto ativo, como no EAN: produto desativado guarda saldo e razão, mas
    # amarrar nota nova nele o ressuscitaria na compra sem ninguém ter decidido.
    if codigo and id_fornecedor:
        cur.execute(
            """SELECT pf.id_produto FROM produto_fornecedor pf
                JOIN produtos p ON p.id = pf.id_produto AND p.ativo
                WHERE pf.id_fornecedor = %s AND lower(pf.codigo_no_fornecedor) = lower(%s)""",
            (id_fornecedor, codigo),
        )
        achado = cur.fetchone()
        if achado:
            return achado["id_produto"], None, 100.0, "fornecedor"

    # 5. semelhança de descrição (+ NCM igual) → só sugestão
    descricao = item.get("descricao_fornecedor") or ""
    cur.execute(
        "SELECT id, nome, ncm FROM produtos WHERE ativo AND controla_estoque LIMIT 2000"
    )
    melhor, melhor_score = None, 0.0
    for p in cur.fetchall():
        score = _semelhanca(descricao, p["nome"])
        if item.get("ncm") and p["ncm"] and item["ncm"] == p["ncm"]:
            score = min(99.0, score + 10)
        if score > melhor_score:
            melhor, melhor_score = p["id"], score
    if melhor and melhor_score >= 55:
        return None, melhor, round(melhor_score, 2), "sugestao"

    return None, None, None, "pendente"


def _fator_do_item(cur, id_produto: int, id_fornecedor: int | None, codigo: str | None,
                   um_nota: str | None = None) -> Decimal:
    """Quantas unidades de estoque vêm em uma unidade da nota.

    A ordem é da resposta mais específica para a mais genérica:

    1. **de-para confirmado** — alguém disse que este código deste fornecedor é
       este produto, com este fator. Ninguém sabe mais que quem confirmou.
    2. **a unidade da nota no cadastro do produto** — a caixa desta água tem 12.
       Vem antes do fator do fornecedor porque casa pela UNIDADE: o fornecedor
       pode ter mudado de embalagem, e o número dele ficou para trás.
    3. **fator do fornecedor** — a embalagem que aquele fornecedor costuma
       mandar, sem dizer em que unidade.
    4. **fator de compra do produto** — o padrão antigo, de quando havia um só.
    """
    # ⚠️ **Fator 1 não é resposta, é a falta dela.** Tanto `codigos_externos`
    # quanto `produto_fornecedor` nascem com fator 1 por padrão — e o
    # lançamento da nota CRIA a linha de `produto_fornecedor` só para guardar o
    # último preço. Aceitar esse 1 como informação faz o vínculo recém-criado
    # encobrir o `fator_compra` do produto: o azeite de 5 L entrou certo na
    # primeira nota e virou 1 L na segunda, sem nada mudar no cadastro.
    # Quem quer dizer "um por um" não precisa dizer nada: 1 já é o resultado.
    if codigo:
        cur.execute(
            "SELECT fator FROM codigos_externos WHERE sistema = %s AND codigo = %s",
            (SISTEMA, codigo),
        )
        linha = cur.fetchone()
        if linha and dec(linha["fator"]) > 0 and dec(linha["fator"]) != 1:
            return dec(linha["fator"])
    da_embalagem = custos.fator_de_embalagem(cur, id_produto, um_nota)
    if da_embalagem:
        return da_embalagem
    if id_fornecedor:
        cur.execute(
            """SELECT fator FROM produto_fornecedor
                WHERE id_produto = %s AND id_fornecedor = %s""",
            (id_produto, id_fornecedor),
        )
        linha = cur.fetchone()
        if linha and dec(linha["fator"]) > 0 and dec(linha["fator"]) != 1:
            return dec(linha["fator"])
    cur.execute("SELECT fator_compra FROM produtos WHERE id = %s", (id_produto,))
    linha = cur.fetchone()
    return dec(linha["fator_compra"]) if linha and dec(linha["fator_compra"]) > 0 else Decimal(1)


def calcular_nota(cur, id_nota: int) -> dict:
    """Rateia frete/desconto/outros e calcula o custo de aquisição de cada item.

    **Custo de aquisição ≠ valor unitário da nota**: caixa de 12 a R$ 60 com R$ 6
    de frete dá R$ 5,50 por unidade, não R$ 5,00.
    """
    cur.execute(
        """SELECT id_fornecedor, valor_frete, valor_desconto, valor_outros
             FROM notas_entrada WHERE id = %s""",
        (id_nota,),
    )
    nota = cur.fetchone()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada")

    cur.execute(
        """SELECT id, quantidade, valor_unitario, valor_total, valor_desconto,
                  valor_acrescimo, um_nota, id_produto, codigo_fornecedor,
                  frete_informado, outros_informado
             FROM nota_itens WHERE id_nota = %s ORDER BY seq""",
        (id_nota,),
    )
    itens = [dict(r) for r in cur.fetchall()]
    if not itens:
        return {"itens": 0}

    base = sum(dec(i["valor_total"]) or dec(i["quantidade"]) * dec(i["valor_unitario"])
               for i in itens) or Decimal(1)
    frete, desconto_nota, outros = (dec(nota["valor_frete"]), dec(nota["valor_desconto"]),
                                    dec(nota["valor_outros"]))
    ums = _ums(cur)
    pendentes = 0

    for item in itens:
        bruto = dec(item["valor_total"]) or dec(item["quantidade"]) * dec(item["valor_unitario"])
        peso = bruto / base
        # O XML da NF-e costuma trazer frete e IPI/ST **já rateados pelo
        # emitente**, item a item. Quando vieram, valem: são o rateio de quem
        # emitiu a nota, e refazê-lo por valor daria outro número.
        frete_item = (dec(item["frete_informado"]) if item["frete_informado"] is not None
                      else (frete * peso).quantize(Decimal("0.01")))
        outros_item = (dec(item["outros_informado"]) if item["outros_informado"] is not None
                       else (outros * peso).quantize(Decimal("0.01")))
        desconto_item = dec(item["valor_desconto"]) + (desconto_nota * peso).quantize(
            Decimal("0.01")
        )
        # Acréscimo do item: taxa de entrega, embalagem cobrada à parte. Entra
        # no custo como o frete entra — encarece o que chega na prateleira.
        acrescimo_item = dec(item.get("valor_acrescimo"))

        convertida, custo_unitario, variacao = None, None, None
        if item["id_produto"]:
            cur.execute("SELECT um_estoque FROM produtos WHERE id = %s", (item["id_produto"],))
            um_estoque = cur.fetchone()["um_estoque"]
            fator = _fator_do_item(cur, item["id_produto"], nota["id_fornecedor"],
                                   item["codigo_fornecedor"], item["um_nota"])
            # A quantidade da nota vira quantidade de estoque por um de dois
            # caminhos, e a ORDEM importa: CX e UN são as duas "unidade" com
            # fator 1, então a conversão de grandeza diria que 4 CX = 4 UN e
            # engoliria a caixa de 12. O fator da embalagem vem primeiro.
            qtd_nota = dec(item["quantidade"])
            if item["um_nota"] and um_estoque and item["um_nota"] == um_estoque:
                convertida = qtd_nota
            elif fator and fator != 1:
                convertida = qtd_nota * fator
            else:
                direta, _como = custos.converter_para_estoque(
                    cur, qtd_nota, item["id_produto"], item["um_nota"], um_estoque, ums)
                # Aqui a nota NÃO para: o item já está vinculado a um produto, e
                # 1:1 com a unidade da nota à vista na tela é melhor que recusar
                # o lançamento inteiro por falta de uma linha de cadastro.
                convertida = direta if direta is not None else qtd_nota

            liquido = bruto - desconto_item + acrescimo_item + frete_item + outros_item
            if convertida and convertida > 0:
                custo_unitario = (liquido / convertida).quantize(CASAS_CUSTO)

                cur.execute(
                    """SELECT custo_unitario FROM estoque_movimentos
                        WHERE id_produto = %s AND tipo IN ('ENTRADA_NF', 'ENTRADA_MANUAL')
                        ORDER BY id DESC LIMIT 1""",
                    (item["id_produto"],),
                )
                ultimo = cur.fetchone()
                if ultimo and dec(ultimo["custo_unitario"]) > 0:
                    anterior = dec(ultimo["custo_unitario"])
                    variacao = ((custo_unitario - anterior) / anterior * 100).quantize(
                        Decimal("0.01")
                    )
        else:
            pendentes += 1

        cur.execute(
            """UPDATE nota_itens
                  SET valor_frete_rateado = %s, valor_outros_rateado = %s,
                      quantidade_convertida = %s, custo_aquisicao_unitario = %s,
                      variacao_preco_pct = %s
                WHERE id = %s""",
            (frete_item, outros_item, convertida, custo_unitario, variacao, item["id"]),
        )

    cur.execute(
        """UPDATE notas_entrada SET status = %s WHERE id = %s AND status <> 'LANCADA'""",
        ("IMPORTADA" if pendentes else "CONCILIADA", id_nota),
    )
    return {"itens": len(itens), "pendentes": pendentes}


def vincular_item(cur, id_item: int, id_produto: int, fator: float | None = None,
                  id_usuario: int | None = None, aprender: bool = True) -> dict:
    """Liga o item ao produto e **ensina o sistema**: da próxima vez entra sozinho."""
    cur.execute(
        """SELECT ni.id_nota, ni.codigo_fornecedor, ni.descricao_fornecedor, n.id_fornecedor
             FROM nota_itens ni JOIN notas_entrada n ON n.id = ni.id_nota
            WHERE ni.id = %s""",
        (id_item,),
    )
    item = cur.fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    cur.execute(
        "UPDATE nota_itens SET id_produto = %s, ignorado = false WHERE id = %s",
        (id_produto, id_item),
    )

    if aprender and item["codigo_fornecedor"]:
        cur.execute(
            """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                             fator, id_fornecedor, origem_vinculo, confirmado_por)
               VALUES (%s, %s, %s, %s, %s, %s, 'MANUAL', %s)
               ON CONFLICT (sistema, codigo) DO UPDATE
                   SET id_produto = EXCLUDED.id_produto, fator = EXCLUDED.fator,
                       confirmado_por = EXCLUDED.confirmado_por, confirmado_em = now()""",
            (SISTEMA, item["codigo_fornecedor"], id_produto, item["descricao_fornecedor"],
             fator or 1, item["id_fornecedor"], id_usuario),
        )
    return calcular_nota(cur, item["id_nota"])


def vincular_fornecedores(cur, id_unidade: int) -> dict:
    """Cria o vínculo produto × fornecedor a partir das notas que já entraram.

    ⚠️ **O catálogo do Omie não diz quem fornece o quê** — o `ListarProdutos`
    devolve o produto, não a origem dele. Quem sabe isso é a NOTA: se o item do
    açúcar veio numa nota da distribuidora, a distribuidora fornece açúcar. É a
    mesma informação, vinda de onde ela de fato existe.

    Até aqui o vínculo só nascia no **lançamento** da nota, para guardar o
    último preço. Numa base real isso deixou 120 pares de fora: 227 produtos já
    tinham aparecido em nota com fornecedor e só 107 tinham vínculo — o resto
    eram notas importadas e ainda não lançadas, que é o estado normal de quem
    acabou de sincronizar.

    ⚠️ **Preço só de nota LANÇADA.** `custo_aquisicao_unitario` é calculado no
    lançamento (frete rateado, desconto abatido, convertido para a unidade de
    estoque); numa nota pendente ele ainda não existe. Gravar o valor bruto da
    linha ali poria na reserva de custo um número que não é custo — e a ficha
    de um insumo sem saldo passaria a mentir.

    ⚠️ **Não sobrescreve.** Vínculo que já existe fica como está: o preço dele
    veio de um lançamento de verdade, e o código no fornecedor pode ter sido
    corrigido à mão.
    """
    cur.execute(
        """
        WITH pares AS (
            SELECT ni.id_produto, n.id_fornecedor,
                   -- O código do produto NO fornecedor: é o nível 3 da cascata
                   -- de conciliação, o que resolve hortifrúti e distribuidor
                   -- sem EAN na próxima nota que chegar.
                   (array_agg(ni.codigo_fornecedor ORDER BY n.id DESC)
                        FILTER (WHERE ni.codigo_fornecedor IS NOT NULL))[1] AS codigo,
                   max(coalesce(n.data_entrada, n.data_emissao))
                       FILTER (WHERE n.status = 'LANCADA') AS ultima_compra
              FROM nota_itens ni
              JOIN notas_entrada n ON n.id = ni.id_nota
             WHERE n.id_unidade = %s
               AND ni.id_produto IS NOT NULL AND n.id_fornecedor IS NOT NULL
               AND n.status <> 'CANCELADA'
             GROUP BY ni.id_produto, n.id_fornecedor
        )
        INSERT INTO produto_fornecedor (id_produto, id_fornecedor, codigo_no_fornecedor,
                                        ultima_compra)
        SELECT id_produto, id_fornecedor, codigo, ultima_compra FROM pares
        ON CONFLICT (id_produto, id_fornecedor) DO NOTHING
        """,
        (id_unidade,),
    )
    criados = cur.rowcount

    # Quantos produtos passaram a ter ao menos um fornecedor conhecido — é o
    # número que interessa a quem vai cotar, não a contagem de linhas.
    cur.execute(
        """SELECT count(DISTINCT pf.id_produto) AS produtos,
                  count(DISTINCT pf.id_fornecedor) AS fornecedores
             FROM produto_fornecedor pf"""
    )
    r = cur.fetchone()
    return {"vinculos_criados": criados, "produtos_com_fornecedor": r["produtos"],
            "fornecedores": r["fornecedores"]}


def reconciliar(cur, id_unidade: int, id_nota: int | None = None) -> dict:
    """Passa a cascata de novo nos itens que ficaram sem produto.

    Existe por causa da ordem em que as coisas acontecem de verdade: é a NOTA
    que revela quais insumos a casa compra, então quase sempre as notas entram
    antes de o cadastro estar pronto. Sem isto, cada item que não encontrou
    produto no dia da importação ficaria pendente para sempre — numa conta real,
    109 de 114 itens passaram a encontrar produto assim que o catálogo do Omie
    chegou, e vinculá-los na mão seria trabalho de um dia inteiro.

    ⚠️ **Nota já lançada não se mexe**: os movimentos dela estão no razão, e
    trocar o produto do item faria a tela contar uma história diferente do que
    o estoque registrou. Item que alguém marcou como ignorado também fica —
    é decisão tomada, não pendência.
    """
    onde = "AND i.id_nota = %s" if id_nota else ""
    parametros = [id_unidade] + ([id_nota] if id_nota else [])
    cur.execute(
        f"""SELECT i.id, i.id_nota, i.codigo_fornecedor, i.codigo_omie, i.codigo_barras,
                   i.ncm, i.descricao_fornecedor, n.id_fornecedor
              FROM nota_itens i
              JOIN notas_entrada n ON n.id = i.id_nota
             WHERE n.id_unidade = %s AND n.status <> 'LANCADA'
               AND i.id_produto IS NULL AND NOT i.ignorado {onde}
             ORDER BY i.id_nota, i.seq""",
        parametros,
    )
    pendentes = [dict(r) for r in cur.fetchall()]

    vinculados, sugeridos, notas_mexidas = 0, 0, set()
    for item in pendentes:
        achado, sugestao, score, _como = conciliar_item(cur, item, item["id_fornecedor"])
        if not achado and not sugestao:
            continue
        cur.execute(
            "UPDATE nota_itens SET id_produto = %s, sugestao_produto = %s, sugestao_score = %s"
            " WHERE id = %s",
            (achado, sugestao, score, item["id"]),
        )
        vinculados += 1 if achado else 0
        sugeridos += 1 if (sugestao and not achado) else 0
        notas_mexidas.add(item["id_nota"])

    # ⚠️ Recalcula TODAS as notas ainda não lançadas, não só as que ganharam
    # vínculo agora. O custo de aquisição e a quantidade convertida ficam
    # gravados no item desde a importação — e o que muda entre uma coisa e
    # outra costuma ser o CADASTRO: alguém definiu a unidade de estoque que
    # faltava, ou o fator da embalagem. Sem passar tudo a limpo, a tela
    # continuaria mostrando o número velho até o lançamento, que recalcula.
    # A conta é barata e o conjunto é pequeno: nota lançada não entra.
    cur.execute(
        """SELECT id FROM notas_entrada
            WHERE id_unidade = %s AND status <> 'LANCADA'"""
        + (" AND id = %s" if id_nota else ""),
        parametros,
    )
    recalculadas = [r["id"] for r in cur.fetchall()]
    for nota in recalculadas:
        calcular_nota(cur, nota)

    return {"pendentes": len(pendentes), "vinculados": vinculados, "sugeridos": sugeridos,
            "notas": len(notas_mexidas), "recalculadas": len(recalculadas)}


def lancar_nota(cur, id_nota: int, id_usuario: int, id_local: int | None = None,
                pode_retroativo: bool = False) -> dict:
    """Transforma a nota em movimento de estoque. Só com tudo conciliado."""
    cur.execute("SELECT * FROM notas_entrada WHERE id = %s", (id_nota,))
    nota = cur.fetchone()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    if nota["status"] == "LANCADA":
        raise HTTPException(status_code=400, detail="Esta nota já foi lançada no estoque.")

    calcular_nota(cur, id_nota)

    cur.execute(
        """SELECT count(*) AS n FROM nota_itens
            WHERE id_nota = %s AND id_produto IS NULL AND NOT ignorado""",
        (id_nota,),
    )
    pendentes = cur.fetchone()["n"]
    if pendentes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{pendentes} item(ns) ainda sem produto vinculado. "
                "Vincule ou marque como 'não controla estoque' antes de lançar."
            ),
        )

    # ⚠️ **Produto sem unidade de estoque não entra no razão.** Quantidade sem
    # unidade é número sem significado: "3" de champignon não diz se são três
    # bandejas ou três quilos, e o custo médio que sair daí contamina a ficha, o
    # CMV e a próxima compra. O catálogo do Omie cria rascunho sem unidade de
    # propósito (a sigla do fornecedor pode não existir na casa) — é aqui que a
    # dívida é cobrada. Todos de uma vez: quem for corrigir corrige a nota
    # inteira numa ida, não descobre um por lançamento recusado.
    cur.execute(
        """SELECT p.nome FROM nota_itens i
             JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_nota = %s AND NOT i.ignorado AND p.um_estoque IS NULL
            ORDER BY i.seq""",
        (id_nota,),
    )
    sem_unidade = [r["nome"] for r in cur.fetchall()]
    if sem_unidade:
        mostra = ", ".join(sem_unidade[:3])
        resto = f" e mais {len(sem_unidade) - 3}" if len(sem_unidade) > 3 else ""
        raise HTTPException(
            status_code=400,
            detail=(f"{len(sem_unidade)} produto(s) ainda sem unidade de estoque: {mostra}{resto}. "
                    "Defina a unidade no cadastro antes de lançar — sem ela a quantidade "
                    "não significa nada."),
        )

    # `id_local_padrao` vem junto: o local é do PRODUTO. Uma nota traz congelado
    # e seco na mesma folha, e um local só para a nota inteira obrigaria a
    # lançar duas vezes ou a aceitar o sorvete no estoque seco. O local da nota
    # é a reserva de quem ainda não tem um definido.
    cur.execute(
        """SELECT i.id, i.id_produto, i.quantidade_convertida, i.custo_aquisicao_unitario,
                  i.lote_nf, i.validade_nf, p.id_local_padrao
             FROM nota_itens i
             JOIN produtos p ON p.id = i.id_produto
            WHERE i.id_nota = %s AND i.id_produto IS NOT NULL AND NOT i.ignorado
            ORDER BY i.seq""",
        (id_nota,),
    )
    itens = [dict(r) for r in cur.fetchall()]
    if not itens:
        raise HTTPException(status_code=400, detail="Nada a lançar: todos os itens foram ignorados.")

    lancados, valor = 0, Decimal(0)
    for item in itens:
        r = motor.lancar(
            cur,
            id_unidade=nota["id_unidade"],
            id_local=item["id_local_padrao"] or id_local or nota["id_local"],
            id_produto=item["id_produto"],
            tipo="ENTRADA_NF",
            quantidade=item["quantidade_convertida"],
            custo_unitario=item["custo_aquisicao_unitario"],
            data_movimento=nota["data_entrada"] or nota["data_emissao"],
            origem_tipo="NOTA",
            origem_id=id_nota,
            documento=f"NF {nota['numero'] or ''}".strip(),
            id_usuario=id_usuario,
            lote=item["lote_nf"],
            validade=item["validade_nf"],
            pode_retroativo=pode_retroativo,
        )
        lancados += 1
        valor += dec(r["custo_total"])

        # O preço do fornecedor passa a valer para a próxima ficha e cotação.
        # É INSERT quando ainda não havia vínculo: um UPDATE só não pegava nada
        # na primeira compra, e a reserva de custo (produto sem saldo) ficava
        # vazia justamente para quem acabou de comprar pela primeira vez.
        # O valor é o custo POR UNIDADE DE ESTOQUE, não o da embalagem —
        # `custo_do_insumo` lê daqui sem dividir por fator nenhum.
        if nota["id_fornecedor"]:
            cur.execute(
                """INSERT INTO produto_fornecedor (id_produto, id_fornecedor,
                                                   ultimo_preco, ultima_compra)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (id_produto, id_fornecedor) DO UPDATE
                       SET ultimo_preco = EXCLUDED.ultimo_preco,
                           ultima_compra = EXCLUDED.ultima_compra""",
                (item["id_produto"], nota["id_fornecedor"],
                 item["custo_aquisicao_unitario"], nota["data_entrada"] or date.today()),
            )

    cur.execute(
        """UPDATE notas_entrada SET status = 'LANCADA', lancada_em = now(), lancada_por = %s,
                                    id_local = coalesce(%s, id_local)
            WHERE id = %s""",
        (id_usuario, id_local, id_nota),
    )
    return {"itens_lancados": lancados, "valor": float(valor)}


# ---------------------------------------------------------------- sincronização


def _fornecedor_da_nota(cur, cnpj: str | None, nome: str | None) -> int | None:
    if cnpj:
        cur.execute("SELECT id FROM fornecedores WHERE cnpj = %s", (cnpj,))
        achado = cur.fetchone()
        if achado:
            return achado["id"]
    if nome:
        cur.execute("SELECT id FROM fornecedores WHERE lower(nome) = lower(%s)", (nome,))
        achado = cur.fetchone()
        if achado:
            return achado["id"]
    if cnpj or nome:
        # Fornecedor novo entra no cadastro: sem ele a nota fica órfã e o
        # de-para por código do fornecedor nunca funciona.
        cur.execute(
            "INSERT INTO fornecedores (nome, cnpj) VALUES (%s, %s) RETURNING id",
            (nome or f"Fornecedor {cnpj}", cnpj),
        )
        return cur.fetchone()["id"]
    return None


def gravar_nota(cur, id_unidade: int, nota: dict, bruto: dict | None = None,
                origem: str = "OMIE", xml: str | None = None,
                id_fornecedor: int | None = None) -> tuple[int, bool]:
    """Grava (ou reconhece) a nota. Devolve (id, nova?).

    O mesmo caminho serve às três entradas — Omie, XML e digitação — porque a
    partir daqui a nota é só uma nota. Muda a porta, não o que acontece dentro.
    """
    chave, id_omie = nota.get("chave_nfe"), nota.get("id_omie")
    if chave:
        cur.execute("SELECT id FROM notas_entrada WHERE chave_nfe = %s", (chave,))
    elif id_omie:
        cur.execute("SELECT id FROM notas_entrada WHERE id_omie = %s", (id_omie,))
    else:
        # Nota digitada não tem chave: a repetição se reconhece por fornecedor +
        # número + série. Sem isso a mesma nota entra duas vezes e dobra o custo.
        cur.execute(
            """SELECT id FROM notas_entrada
                WHERE chave_nfe IS NULL AND id_unidade = %s AND id_fornecedor IS NOT DISTINCT FROM %s
                  AND numero IS NOT DISTINCT FROM %s AND coalesce(serie, '') = coalesce(%s, '')""",
            (id_unidade, id_fornecedor, nota.get("numero"), nota.get("serie")),
        )
    existente = cur.fetchone()
    if existente and existente["id"]:
        return existente["id"], False

    if id_fornecedor is None:
        id_fornecedor = _fornecedor_da_nota(cur, nota.get("cnpj_emitente"),
                                            nota.get("nome_emitente"))
    cur.execute(
        """INSERT INTO notas_entrada
               (id_unidade, chave_nfe, numero, serie, id_fornecedor, cnpj_emitente,
                nome_emitente, data_emissao, data_entrada, valor_produtos, valor_frete,
                valor_desconto, valor_outros, valor_total, origem, id_omie, bruto, xml_bruto,
                id_local)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (id_unidade, chave, nota.get("numero"), nota.get("serie"), id_fornecedor,
         nota.get("cnpj_emitente"), nota.get("nome_emitente"), nota.get("data_emissao"),
         nota.get("data_entrada"), nota.get("valor_produtos"), nota.get("valor_frete"),
         nota.get("valor_desconto"), nota.get("valor_outros"), nota.get("valor_total"),
         origem, id_omie, __import__("json").dumps(bruto, default=str) if bruto else None,
         xml, nota.get("id_local")),
    )
    id_nota = cur.fetchone()["id"]

    for item in nota.get("itens", []):
        # Item digitado já nasce com o produto escolhido na tela — a cascata só
        # trabalha quando ninguém disse qual é.
        id_produto, sugestao, score = item.get("id_produto"), None, None
        if not id_produto:
            id_produto, sugestao, score, _como = conciliar_item(cur, item, id_fornecedor)
        cur.execute(
            """INSERT INTO nota_itens
                   (id_nota, seq, descricao_fornecedor, codigo_fornecedor, codigo_barras, ncm,
                    quantidade, um_nota, valor_unitario, valor_total, valor_desconto,
                    valor_acrescimo, lote_nf, validade_nf, id_produto, sugestao_produto,
                    sugestao_score, frete_informado, outros_informado, ignorado,
                    codigo_omie)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s)""",
            (id_nota, item["seq"], item["descricao_fornecedor"], item.get("codigo_fornecedor"),
             item.get("codigo_barras"), item.get("ncm"), item["quantidade"], item.get("um_nota"),
             item["valor_unitario"], item["valor_total"], item.get("valor_desconto") or 0,
             item.get("valor_acrescimo") or 0,
             item.get("lote_nf"), item.get("validade_nf"), id_produto, sugestao, score,
             item.get("frete_informado"), item.get("outros_informado"),
             bool(item.get("ignorado")), item.get("codigo_omie")),
        )

    calcular_nota(cur, id_nota)
    return id_nota, True


# Folga sobre a última sincronização. Nota emitida antes e lançada no Omie
# depois entraria fora da janela se ela começasse exatamente onde a anterior
# parou — e ninguém perceberia, porque o resultado seria "0 novas".
FOLGA_DIAS = 7

# Quando nunca se sincronizou, não há de onde partir: dois meses cobrem o
# giro de compras de um restaurante sem puxar o histórico inteiro.
JANELA_PADRAO = 60


def janela(cur, id_unidade: int, desde: date | None = None,
           dias: int | None = None) -> tuple[date, str]:
    """De quando buscar, e por quê — a frase vai para a tela e para o log.

    Três casos, nesta ordem:

    * `desde` — a data que a pessoa escolheu (a carga inicial do histórico);
    * `dias` — janela fixa pedida na chamada;
    * nada — **desde a última sincronização, com folga**. É o padrão, e é o que
      impede a nota lançada com atraso de cair fora da janela para sempre.
    """
    if desde:
        return desde, f"desde {desde.strftime('%d/%m/%Y')}"
    if dias:
        return date.today() - timedelta(days=dias), f"últimos {dias} dias"

    cur.execute(
        """SELECT ultima_sincronizacao FROM integracoes
            WHERE id_unidade = %s AND servico = 'OMIE'""",
        (id_unidade,),
    )
    linha = cur.fetchone()
    ultima = linha["ultima_sincronizacao"] if linha else None
    if not ultima:
        return (date.today() - timedelta(days=JANELA_PADRAO),
                f"primeira vez: últimos {JANELA_PADRAO} dias")
    inicio = ultima.date() - timedelta(days=FOLGA_DIAS)
    return inicio, (f"desde a última sincronização ({ultima.strftime('%d/%m/%Y')}), "
                    f"com {FOLGA_DIAS} dias de folga")


# O módulo das notas de compra. Não é `produtos/notaentrada` — ver o mapeador
# `recebimento_de_nfe`: aquele é o lançamento manual do Omie, este é o que
# recebe as NF-e dos fornecedores.
MODULO_NOTAS = "produtos/recebimentonfe"
LISTA_NOTAS = "ListarRecebimentos"
ITENS_DA_NOTA = "ConsultarRecebimento"

# Falhas seguidas no detalhe param a varredura. Uma nota problemática é uma
# nota; cinco em sequência é a conta recusando — e insistir é o que faz o Omie
# bloquear a integração inteira.
FALHAS_SEGUIDAS = 5


def _ja_temos(cur, id_unidade: int, nota: dict) -> bool:
    """A nota já está aqui? É o que evita a chamada cara do detalhe."""
    if nota.get("chave_nfe"):
        cur.execute("SELECT 1 FROM notas_entrada WHERE chave_nfe = %s", (nota["chave_nfe"],))
    elif nota.get("id_omie"):
        cur.execute("SELECT 1 FROM notas_entrada WHERE id_omie = %s", (nota["id_omie"],))
    else:
        return False
    return cur.fetchone() is not None


def sincronizar(cur, id_unidade: int, cliente: ClienteOmie, dias: int | None = None,
                desde: date | None = None, teto_paginas: int = 40) -> dict:
    """Puxa as notas de entrada da janela e grava o que ainda não existe aqui.

    ⚠️ **`ListarRecebimentos` não aceita filtro de data.** Foram testados
    `dDtInicial`, `dDataInicial`, `dEmissaoDe`, `dDtEmissaoDe` e
    `dRegistroInicial` — todos "não faz parte da estrutura". O que ele aceita é
    `cEtapa` e `nIdFornecedor`, que não servem para janela. Então o recorte de
    período é FEITO AQUI, varrendo **da última página para a primeira**: a lista
    vem da nota mais velha para a mais nova, e parar na primeira página inteira
    fora da janela é o que impede uma sincronização diária de atravessar três
    anos de histórico.

    ⚠️ **O detalhe só é pedido para nota que ainda não existe aqui.** A lista
    não traz itens, e cada `ConsultarRecebimento` é uma chamada: numa conta de
    3.670 notas, pedir o detalhe de todas custaria mais de meia hora e a conta
    bloqueada no meio. Como a dedução é pela chave da NF-e, a segunda
    sincronização do dia faz zero chamada de detalhe.
    """
    inicio, motivo = janela(cur, id_unidade, desde, dias)
    novas, repetidas, paginas, antigas, falhas = 0, 0, 0, 0, 0
    seguidas, truncou = 0, {}

    def parou_no_teto(trazidos, total):
        truncou.update({"trazidos": trazidos, "total_no_omie": total})

    try:
        for _dados, registros in cliente.paginar(
            MODULO_NOTAS, LISTA_NOTAS, "recebimentos",
            por_pagina=50, maximo=teto_paginas, ao_truncar=parou_no_teto,
            dialeto=DIALETO_HUNGARO, do_fim=True,
        ):
            paginas += 1
            fora = 0
            # Dentro da página, da mais nova para a mais velha — assim o corte
            # da janela acontece o quanto antes.
            for bruto in reversed(registros):
                cabecalho = mapeadores.recebimento_de_nfe(bruto)
                data = cabecalho.get("data_entrada") or cabecalho.get("data_emissao")
                if data and data < inicio:
                    fora += 1
                    continue
                if _ja_temos(cur, id_unidade, cabecalho):
                    repetidas += 1
                    continue
                try:
                    detalhe = cliente.chamar(MODULO_NOTAS, ITENS_DA_NOTA,
                                             {"nIdReceb": int(cabecalho["id_omie"])})
                    seguidas = 0
                except (ErroOmie, TypeError, ValueError):
                    # Uma nota que não abre não pode levar junto as que já
                    # entraram: conta, segue, e o log diz quantas ficaram.
                    falhas += 1
                    seguidas += 1
                    if seguidas >= FALHAS_SEGUIDAS:
                        raise
                    continue
                nota = mapeadores.recebimento_de_nfe(detalhe)
                _id, nova = gravar_nota(cur, id_unidade, nota, detalhe)
                novas += 1 if nova else 0
                repetidas += 0 if nova else 1
            antigas += fora
            # Página inteira fora da janela: daqui para trás só fica mais velho.
            if fora == len(registros):
                break
    except ErroOmie as e:
        _registrar(cur, MODULO_NOTAS, LISTA_NOTAS, "ERRO", novas, e.mensagem,
                   cliente.modo, paginas)
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    recado = f"{novas} nova(s), {repetidas} já existiam — {motivo}"
    if falhas:
        recado += f"; {falhas} nota(s) sem detalhe"
    _registrar(cur, MODULO_NOTAS, LISTA_NOTAS,
               "OK" if novas or repetidas else "VAZIO", novas + repetidas,
               recado, cliente.modo, paginas)

    # Fornecedor que nasce da nota entra com nome e CNPJ e mais nada. Completar
    # agora custa uma chamada e evita a lista de fornecedores pela metade.
    # `apenas_completar`: a lista do Omie mistura cliente e fornecedor, e não é
    # aqui que se decide quem entra no cadastro.
    completados = 0
    if novas:
        try:
            completados = importar_fornecedores(
                cur, cliente, None, apenas_completar=True)["completados"]
        except Exception:
            # As notas já estão gravadas; falhar aqui desfaria o que deu certo.
            # O log de sincronização registra, e a importação manual resolve.
            _registrar(cur, "geral/clientes", "ListarClientes", "ERRO", 0,
                       "não deu para completar os fornecedores desta leva", cliente.modo)

    return {"novas": novas, "repetidas": repetidas, "paginas": paginas, "modo": cliente.modo,
            "desde": inicio, "janela": motivo, "fornecedores_completados": completados,
            "fora_da_janela": antigas, "sem_detalhe": falhas,
            # Só preenchido quando a varredura parou no teto de páginas: sem
            # isso, "0 nova(s)" não se distingue de "não deu tempo de chegar lá".
            "faltou_varrer": truncou or None}


def conferir_notas(cur, id_unidade: int, cliente: ClienteOmie,
                   inicio: date, fim: date) -> dict:
    """As notas que o Omie tem no período contra as que existem aqui.

    Existe porque "0 novas" é ambíguo: pode ser que não haja nada novo, ou que a
    janela tenha passado por cima de uma nota lançada com atraso. Aqui a
    pergunta é outra — **quais** faltam, com número e emitente, para dar para ir
    atrás de cada uma.
    """
    do_omie: dict[str, dict] = {}
    try:
        for _dados, registros in cliente.paginar(
            MODULO_NOTAS, LISTA_NOTAS, "recebimentos", por_pagina=50,
            dialeto=DIALETO_HUNGARO, do_fim=True,
        ):
            # A lista vem da mais velha para a mais nova e não aceita filtro de
            # data: varre-se de trás e para-se quando a página inteira já é
            # anterior ao período. O corte é nosso — sem ele a conferência
            # atravessaria o histórico inteiro para comparar uma semana.
            antes_do_periodo = 0
            for bruto in reversed(registros):
                n = mapeadores.recebimento_de_nfe(bruto)
                data = n.get("data_entrada") or n.get("data_emissao")
                if data and _como_data(data) < inicio:
                    antes_do_periodo += 1
                    continue
                if data and _como_data(data) > fim:
                    continue
                chave = n.get("chave_nfe") or f"omie:{n.get('id_omie')}"
                do_omie[chave] = {
                    "chave_nfe": n.get("chave_nfe"),
                    "numero": n.get("numero"),
                    "emitente": n.get("nome_emitente"),
                    "data": data,
                    "valor_total": float(dec(n.get("valor_total"))),
                }
            if antes_do_periodo == len(registros):
                break
    except ErroOmie as e:
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    cur.execute(
        """SELECT chave_nfe, id_omie, numero, nome_emitente, status,
                  coalesce(data_entrada, data_emissao) AS data
             FROM notas_entrada
            WHERE id_unidade = %s AND origem = 'OMIE'
              AND coalesce(data_entrada, data_emissao) BETWEEN %s AND %s""",
        (id_unidade, inicio, fim),
    )
    aqui = {(r["chave_nfe"] or f"omie:{r['id_omie']}"): dict(r) for r in cur.fetchall()}

    faltando = [v for k, v in do_omie.items() if k not in aqui]
    return {
        "inicio": inicio,
        "fim": fim,
        "no_omie": len(do_omie),
        "aqui": len(aqui),
        "faltando": sorted(faltando, key=lambda x: (x["data"] or date.min), reverse=True)[:100],
        "modo": cliente.modo,
        # Nota que existe aqui e não veio na lista do Omie: quase sempre é nota
        # cancelada lá depois de importada. Vale mostrar, não vale alarmar.
        "so_aqui": [
            {"numero": v["numero"], "emitente": v["nome_emitente"], "status": v["status"]}
            for k, v in aqui.items() if k not in do_omie
        ][:50],
    }


def _como_data(valor):
    """A data pode chegar como `date` ou como texto ISO, conforme o mapeador."""
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


# Os campos que a sincronização COMPLETA — nunca sobrescreve.
#
# ⚠️ **Só o que está em branco.** É a mesma regra do importador de fornecedores,
# e pela mesma razão: reimportar não pode desfazer correção. Se alguém arrumou
# o nome, corrigiu o peso ou escolheu outra categoria aqui, foi porque o dado
# de lá estava errado — e a próxima sincronização apagaria o conserto.
#
# `nome` fica FORA de propósito: ele é o que mais se corrige à mão (o rodapé de
# tributos do DANFE já entrou em 59 cadastros), e completá-lo não faz sentido
# porque ele nunca está vazio.
_COMPLETAVEIS = ("codigo_barras", "ncm", "marca", "cest", "peso_liquido", "peso_bruto",
                 "estoque_minimo")


def _categoria_da_familia(cur, familia: str | None, cache: dict[str, int]) -> int | None:
    """A família do Omie vira categoria aqui, criada na primeira vez que aparece.

    ⚠️ **É a classificação que a casa já fez do outro lado.** Numa conta real,
    2.189 produtos vieram com NCM e NENHUM com categoria — e sem categoria o CMV
    por grupo e a curva ABC não separam nada. A família é a resposta que já
    existia; deixá-la para trás obrigava a classificar dois mil itens à mão.
    """
    if not familia:
        return None
    chave = familia.strip().lower()
    if not chave:
        return None
    if chave in cache:
        return cache[chave]

    cur.execute("SELECT id FROM categorias WHERE lower(nome) = %s", (chave,))
    linha = cur.fetchone()
    if not linha:
        cur.execute(
            "INSERT INTO categorias (nome, tipo) VALUES (%s, 'INSUMO') RETURNING id",
            (familia.strip()[:80],),
        )
        linha = cur.fetchone()
    cache[chave] = linha["id"]
    return cache[chave]


def _completar_produto(cur, id_produto: int, p: dict, id_categoria: int | None) -> bool:
    """Preenche no produto o que está em branco. Devolve se mexeu em algo.

    O `coalesce(coluna, %s)` faz a regra no próprio UPDATE: coluna preenchida
    fica como está, coluna nula recebe o valor de fora. Conferir antes em
    Python custaria um SELECT por produto — são milhares.
    """
    campos = {c: p.get(c) for c in _COMPLETAVEIS if p.get(c) is not None}
    if id_categoria:
        campos["id_categoria"] = id_categoria
    if p.get("descricao_detalhada"):
        campos["observacao"] = p["descricao_detalhada"]
    if not campos:
        return False

    sets = ", ".join(f"{c} = coalesce({c}, %s)" for c in campos)
    condicoes = " OR ".join(f"{c} IS NULL" for c in campos)
    cur.execute(
        f"UPDATE produtos SET {sets}, sincronizado_em = now() "
        f"WHERE id = %s AND ({condicoes})",
        [*campos.values(), id_produto],
    )
    return cur.rowcount > 0


def importar_catalogo(cur, cliente: ClienteOmie, id_usuario: int) -> dict:
    """Traz o catálogo do Omie como **rascunho**.

    É o jeito mais barato de nascer com centenas de insumos cadastrados. Rascunho
    não entra no estoque enquanto não tiver unidade e fator — a trava que protege
    o custo.

    ⚠️ **`filtrar_apenas_omiepdv: "N"` não é opcional.** Sem ele, o
    `ListarProdutos` de uma conta real devolveu **zero** produto onde havia
    2.198 — e "0 criado(s)" não se distingue de "a conta não tem catálogo".
    O padrão do Omie devolve só o que veio do PDV dele.
    """
    criados, atualizados, paginas, sem_unidade = 0, 0, 0, 0
    completados = 0
    # Cache de família → categoria: uma conta real tem dezenas de famílias e
    # milhares de produtos, e uma consulta por produto seria uma por linha.
    categorias: dict[str, int] = {}
    truncou: dict = {}

    def parou_no_teto(trazidos, total):
        truncou.update({"trazidos": trazidos, "total_no_omie": total})

    try:
        for _dados, registros in cliente.paginar(
            "geral/produtos", "ListarProdutos", "produto_servico_cadastro",
            param={"apenas_importado_api": "N", "filtrar_apenas_omiepdv": "N"},
            ao_truncar=parou_no_teto,
        ):
            paginas += 1
            for bruto in registros:
                p = mapeadores.produto_do_catalogo(bruto)
                if not p["codigo_omie"]:
                    continue
                # ⚠️ A unidade do fornecedor pode não existir na casa (um
                # catálogo real trouxe "M", de metro). Deixar entrar rebentava a
                # chave estrangeira e derrubava a importação INTEIRA — 2.198
                # produtos parados por um. Sem unidade conhecida, o produto
                # nasce sem ela: é rascunho, e rascunho existe justamente para
                # lembrar que alguém precisa conferir unidade e fator.
                if p["um"]:
                    cur.execute("SELECT 1 FROM unidades_medida WHERE upper(sigla) = upper(%s)",
                                (p["um"],))
                    if not cur.fetchone():
                        sem_unidade += 1
                        p["um"] = None
                id_categoria = _categoria_da_familia(cur, p["familia"], categorias)

                # 🔑 **A COLUNA e depois os APELIDOS** — e sem o segundo o
                # duplicado renascia por esta porta. Ao juntar dois cadastros do
                # mesmo abacate, o código do absorvido vira apelido e a coluna
                # dele é zerada: esta consulta não achava mais nada e o catálogo
                # criava um rascunho novo, desfazendo o trabalho de juntar. É o
                # mesmo defeito que a cascata da nota já tinha, pela outra porta.
                # ⚠️ Sem `AND ativo`, ao contrário da cascata: aqui a pergunta é
                # "este produto do Omie já existe aqui?", e cadastro inativo
                # existe — completá-lo é certo, duplicá-lo não.
                cur.execute("SELECT id FROM produtos WHERE codigo_omie = %s", (p["codigo_omie"],))
                existente = cur.fetchone()
                if not existente:
                    cur.execute(
                        """SELECT id_produto AS id FROM codigos_externos
                            WHERE sistema = %s AND codigo = %s""",
                        (vinculo.SISTEMA_PRODUTO, str(p["codigo_omie"])),
                    )
                    existente = cur.fetchone()
                if existente:
                    # ⚠️ **Produto que já existe passou a RECEBER o que falta.**
                    # Antes esta linha só contava "atualizado" e seguia sem
                    # escrever nada — e era por isso que o EAN, o NCM e a marca
                    # ficavam vazios aqui enquanto estavam preenchidos lá:
                    # quem foi criado antes de o campo ser mapeado, ou criado a
                    # partir do item da nota, nunca mais era completado.
                    if _completar_produto(cur, existente["id"], p, id_categoria):
                        completados += 1
                    atualizados += 1
                    continue
                cur.execute(
                    """INSERT INTO produtos (codigo, nome, tipo, um_estoque, ncm, codigo_barras,
                                             codigo_omie, marca, cest, peso_liquido, peso_bruto,
                                             estoque_minimo, id_categoria, observacao,
                                             sincronizado_em, origem, status, controla_estoque,
                                             criado_por)
                       VALUES (%s, %s, 'INSUMO', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               now(), 'OMIE', 'RASCUNHO', true, %s)
                       ON CONFLICT DO NOTHING RETURNING id""",
                    (p["codigo"] or f"OMIE-{p['codigo_omie']}", p["nome"], p["um"], p["ncm"],
                     p["codigo_barras"], p["codigo_omie"], p["marca"], p["cest"],
                     p["peso_liquido"], p["peso_bruto"], p["estoque_minimo"], id_categoria,
                     p["descricao_detalhada"], id_usuario),
                )
                if cur.fetchone():
                    criados += 1
    except ErroOmie as e:
        _registrar(cur, "geral/produtos", "ListarProdutos", "ERRO", criados, e.mensagem,
                   cliente.modo, paginas)
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    _registrar(cur, "geral/produtos", "ListarProdutos", "OK", criados + atualizados,
               f"{criados} criado(s) em rascunho, {completados} completado(s)",
               cliente.modo, paginas)
    return {"criados": criados, "ja_existiam": atualizados,
            # Quantos JÁ EXISTIAM e ganharam campo que estava vazio — EAN,
            # marca, peso, categoria. É o número que explica por que reimportar
            # deixou de ser inútil.
            "completados": completados,
            "categorias_usadas": len(categorias),
            "sem_unidade": sem_unidade, "modo": cliente.modo,
            # Preenchido só quando a varredura parou no teto: sem isso, "992
            # criado(s)" não se distingue de "o catálogo tem 992".
            "faltou_varrer": truncou or None}


# O que o Omie sabe do fornecedor e vale a pena trazer. Fica de fora o que é
# decisão da casa (prazo de entrega, pedido mínimo, dias de entrega): isso o
# dono negocia, não vem de cadastro fiscal.
CAMPOS_FORNECEDOR = ("nome_fantasia", "email", "telefone", "cidade", "uf")


def _completar_fornecedor(cur, atual: dict, vindo: dict) -> bool:
    """Preenche só o que está em branco aqui. Devolve se mexeu em algo.

    Nunca sobrescreve: o telefone que alguém digitou porque o do Omie estava
    desatualizado é mais confiável que o do Omie. Importar duas vezes não pode
    desfazer correção feita à mão.
    """
    mudancas = {c: vindo.get(c) for c in CAMPOS_FORNECEDOR
                if vindo.get(c) and not atual.get(c)}
    if vindo.get("codigo_omie") and not atual.get("codigo_omie"):
        mudancas["codigo_omie"] = vindo["codigo_omie"]
    # Nome genérico ("Fornecedor 12345678000195") é o que a nota cria quando não
    # veio o nome: esse vale trocar pela razão social de verdade.
    if vindo.get("nome") and (atual.get("nome") or "").startswith("Fornecedor "):
        mudancas["nome"] = vindo["nome"]
    if not mudancas:
        return False
    campos = ", ".join(f"{c} = %s" for c in mudancas)
    cur.execute(f"UPDATE fornecedores SET {campos} WHERE id = %s",
                (*mudancas.values(), atual["id"]))
    return True


def importar_fornecedores(cur, cliente: ClienteOmie, id_usuario: int,
                          apenas_completar: bool = False,
                          tag: str | None = "Fornecedor") -> dict:
    """Traz o cadastro de fornecedores do Omie.

    Faz duas coisas de uma vez: cria quem não existe aqui e **completa** quem já
    existe — os que nasceram da nota entram com nome e CNPJ e mais nada, e o
    Omie tem cidade, telefone e e-mail.

    ⚠️ **No Omie, cliente e fornecedor moram na mesma lista**, separados por
    ETIQUETA. Sem filtrar, uma conta real trouxe 888 pessoas físicas — os
    clientes da casa — para o cadastro de fornecedores. O filtro vai no
    SERVIDOR (`clientesFiltro.tags`): numa conta de 919 cadastros ele desce 648,
    e o que não é fornecedor nem trafega.

    `tag=None` traz todo mundo, para a conta que não usa etiqueta — e aí a
    responsabilidade de separar é de quem configurou.
    """
    criados, completados, ja_ok, paginas = 0, 0, 0, 0
    filtro = {"clientesFiltro": {"tags": [{"tag": tag}]}} if tag else {}
    try:
        for _dados, registros in cliente.paginar(
            "geral/clientes", "ListarClientes", "clientes_cadastro", param=filtro,
        ):
            paginas += 1
            for bruto in registros:
                f = mapeadores.fornecedor_do_cadastro(bruto)
                cnpj = f.get("cnpj")
                atual = None
                if cnpj:
                    cur.execute(
                        "SELECT * FROM fornecedores WHERE regexp_replace(coalesce(cnpj,''),"
                        " '[^0-9]', '', 'g') = %s", (cnpj,))
                    atual = cur.fetchone()
                if not atual and f.get("nome"):
                    cur.execute("SELECT * FROM fornecedores WHERE lower(nome) = lower(%s)",
                                (f["nome"],))
                    atual = cur.fetchone()

                if atual:
                    if _completar_fornecedor(cur, dict(atual), f):
                        completados += 1
                    else:
                        ja_ok += 1
                    continue

                if apenas_completar:
                    continue
                cur.execute(
                    """INSERT INTO fornecedores (nome, nome_fantasia, cnpj, email, telefone,
                                                 cidade, uf, codigo_omie, criado_por)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING RETURNING id""",
                    (f["nome"], f.get("nome_fantasia"), cnpj, f.get("email"), f.get("telefone"),
                     f.get("cidade"), f.get("uf"), f.get("codigo_omie"), id_usuario),
                )
                if cur.fetchone():
                    criados += 1
    except ErroOmie as e:
        _registrar(cur, "geral/clientes", "ListarClientes", "ERRO", criados, e.mensagem,
                   cliente.modo, paginas)
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    _registrar(cur, "geral/clientes", "ListarClientes", "OK", criados + completados,
               f"{criados} criado(s), {completados} completado(s)", cliente.modo, paginas)
    return {"criados": criados, "completados": completados, "ja_estavam": ja_ok,
            "tag": tag, "modo": cliente.modo}


def custos_iniciais(cur, cliente: ClienteOmie, id_usuario: int | None = None,
                    aplicar: bool = False) -> dict:
    """Traz o custo médio do Omie para os produtos que aqui não têm custo nenhum.

    🔑 **O problema, medido na base em 01/09/2026: 2.323 produtos ativos que
    controlam estoque sem custo algum** — nunca entrou nota deles aqui e não há
    preço de fornecedor. Sem custo não há ficha, nem CMV teórico, nem margem: o
    prato entra na conta valendo zero e o food cost sai bom demais, calado. O
    Omie já sabe o número (o CMC da posição de estoque), e trazê-lo destrava a
    conta para todos de uma vez.

    ⚠️ **É REFERÊNCIA, não movimento.** Nada aqui cria saldo nem entra no razão:
    o CMV real continua saindo do que a casa comprou e contou. Fosse movimento,
    uma carga errada não se apagaria — o razão é append-only —, e 2.323 linhas
    erradas entrariam no CMV do período em que a carga fosse feita.

    ⚠️ **Só quem NÃO tem custo.** Nunca sobrescreve o médio do razão (que é o
    que a casa pagou de verdade, com o frete desta casa rateado dentro) nem o
    último preço negociado com o fornecedor. Rodar de novo só alcança quem
    continua sem — é o mesmo "completa o que está em branco" do importador de
    fornecedores e do de produtos.

    ⚠️ **CMC zero é PULADO.** Zero não é um custo: é o Omie dizendo que não
    sabe, e gravá-lo faria a ficha calcular com um número inventado — pior que
    calcular sem, porque o "sem_custo" some do aviso.

    ⚠️ **O de-para é o mesmo da nota** (`vinculo.por_codigo_omie`): a coluna e
    depois os apelidos. Um cadastro que absorveu o duplicado responde pelos
    códigos dos dois, e olhar só a coluna deixaria o principal de fora.

    `aplicar=False` é a PRÉVIA — mesma varredura, sem gravar. Ela existe porque
    2.323 produtos é grande demais para se descobrir o efeito depois.
    """
    achados: list[dict] = []
    vistos = 0
    sem_cadastro = 0
    ja_tem_custo = 0
    sem_cmc = 0
    truncou = {"foi": False}

    def marcar(trazidos, total):
        truncou["foi"] = True
        truncou["trazidos"], truncou["total"] = trazidos, total

    try:
        for _dados, registros in cliente.paginar(
            "estoque/consulta", "ListarPosEstoque", "produtos",
            dialeto=DIALETO_POSICAO, por_pagina=200, maximo=30, ao_truncar=marcar,
        ):
            for bruto in registros:
                pos = mapeadores.posicao_de_estoque(bruto)
                if not pos["codigo_omie"]:
                    continue
                vistos += 1
                id_produto = vinculo.por_codigo_omie(cur, pos["codigo_omie"])
                if not id_produto:
                    sem_cadastro += 1
                    continue
                if not pos["cmc"] or pos["cmc"] <= 0:
                    sem_cmc += 1
                    continue

                # ⚠️ Pergunta pela MESMA cascata que a ficha usa — e sem loja,
                # porque a referência é da rede: o custo que veio de fora não é
                # de uma prateleira, é do produto.
                atual, origem = custos.custo_do_insumo(cur, id_produto)
                if atual is not None and origem != "referencia":
                    ja_tem_custo += 1
                    continue

                cur.execute("SELECT codigo, nome FROM produtos WHERE id = %s", (id_produto,))
                p = cur.fetchone()
                achados.append({
                    "id_produto": id_produto,
                    "codigo": p["codigo"],
                    "produto": p["nome"],
                    "codigo_omie": pos["codigo_omie"],
                    "custo_omie": float(pos["cmc"]),
                    # Já tinha referência de uma rodada anterior? A linha diz, e
                    # o número novo substitui — referência sobrescreve
                    # referência, nunca custo de verdade.
                    "ja_era_referencia": origem == "referencia",
                })
    except ErroOmie as e:
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    if aplicar and achados:
        for a in achados:
            cur.execute(
                """UPDATE produtos
                      SET custo_referencia = %s, custo_referencia_em = now(),
                          custo_referencia_origem = 'OMIE'
                    WHERE id = %s""",
                (a["custo_omie"], a["id_produto"]),
            )

    achados.sort(key=lambda x: -x["custo_omie"])
    return {
        "linhas": achados[:500],
        "produtos": len(achados),
        "conferidos": vistos,
        "sem_cadastro_aqui": sem_cadastro,
        "ja_tinham_custo": ja_tem_custo,
        "sem_custo_no_omie": sem_cmc,
        "aplicado": bool(aplicar),
        "truncado": truncou["foi"],
        "message": (
            (f"{len(achados)} produto(s) receberam custo de referência do Omie"
             if aplicar else
             f"{len(achados)} produto(s) receberiam custo de referência do Omie")
            + f" — {vistos} conferido(s)"
            + (f", {ja_tem_custo} já tinham custo" if ja_tem_custo else "")
            + (f", {sem_cadastro} sem cadastro aqui" if sem_cadastro else "")
            + (f", {sem_cmc} sem custo no Omie" if sem_cmc else "")
            + (". A varredura parou no teto de páginas — há mais no Omie."
               if truncou["foi"] else "")
        ),
    }


def conferir_estoque(cur, cliente: ClienteOmie, so_divergentes: bool = True) -> dict:
    """Saldo e custo médio daqui × posição de estoque do Omie.

    Divergência quer dizer que alguma entrada não foi conciliada de um dos lados
    — e é a conferência cruzada mais barata que existe, porque o Omie já mantém
    o número por outros motivos.

    ⚠️ **`ListarPosEstoque` tem um dialeto de paginação SÓ DELE**
    (`DIALETO_POSICAO`): aceita `nPagina`, recusa `nRegistrosPorPagina` e quer
    `nRegPorPagina`. Com o dialeto errado, **toda** chamada voltava "Tag [PAGINA]
    não faz parte da estrutura" — a conferência nunca funcionou, e cada recusa
    gastava cota.

    ⚠️ **O de-para é `nCodProd` → `produtos.codigo_omie`**, nunca `cCodigo`: esse
    é o código da CASA registrado no Omie, e comparar com `codigo_omie` não casa
    nunca. O sintoma seria pior que o erro — lista vazia, que se lê como "está
    tudo certo".

    ⚠️ **Só compara produto que existe DOS DOIS LADOS.** Produto do Omie que não
    tem cadastro aqui não é divergência: é catálogo que ninguém importou, e
    contá-lo encheria a lista de linhas sem ação possível. O resumo diz quantos
    foram por esse caminho, para o número não sumir.
    """
    linhas: list[dict] = []
    vistos = 0
    sem_cadastro = 0
    truncou = {"foi": False}

    def marcar(trazidos, total):
        truncou["foi"] = True
        truncou["trazidos"], truncou["total"] = trazidos, total

    try:
        for _dados, registros in cliente.paginar(
            "estoque/consulta", "ListarPosEstoque", "produtos",
            dialeto=DIALETO_POSICAO, por_pagina=200, maximo=30, ao_truncar=marcar,
        ):
            for bruto in registros:
                pos = mapeadores.posicao_de_estoque(bruto)
                if not pos["codigo_omie"]:
                    continue
                vistos += 1
                cur.execute(
                    """SELECT p.id, p.codigo, p.nome, p.um_estoque,
                              coalesce(sum(s.quantidade), 0) AS saldo,
                              CASE WHEN coalesce(sum(s.quantidade), 0) > 0
                                   THEN sum(s.quantidade * s.custo_medio) / sum(s.quantidade)
                                   ELSE 0 END AS custo_medio
                         FROM produtos p
                         LEFT JOIN estoque_saldos s ON s.id_produto = p.id
                        WHERE p.codigo_omie = %s
                        GROUP BY p.id, p.codigo, p.nome, p.um_estoque""",
                    (pos["codigo_omie"],),
                )
                nosso = cur.fetchone()
                if not nosso:
                    sem_cadastro += 1
                    continue

                dif_saldo = dec(nosso["saldo"]) - dec(pos["saldo"])
                dif_custo = dec(nosso["custo_medio"]) - pos["cmc"]
                # ⚠️ Duas divergências, não uma. A versão anterior olhava só o
                # custo — e saldo diferente com custo igual é o caso mais comum
                # de todos: a entrada foi lançada de um lado só.
                divergente = abs(dif_saldo) > Decimal("0.001") or abs(dif_custo) > Decimal("0.01")
                if so_divergentes and not divergente:
                    continue
                linhas.append({
                    "id_produto": nosso["id"],
                    "codigo": nosso["codigo"],
                    "produto": nosso["nome"],
                    "um_estoque": nosso["um_estoque"],
                    "codigo_omie": pos["codigo_omie"],
                    "saldo_botane": float(dec(nosso["saldo"])),
                    "saldo_omie": float(pos["saldo"]),
                    "diferenca_saldo": float(dif_saldo),
                    "custo_medio_botane": float(dec(nosso["custo_medio"])),
                    "cmc_omie": float(pos["cmc"]),
                    "diferenca_custo": float(dif_custo),
                    "divergente": divergente,
                })
    except ErroOmie as e:
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    linhas.sort(key=lambda x: -abs(x["diferenca_saldo"]))
    return {
        "linhas": linhas,
        "conferidos": vistos,
        "sem_cadastro_aqui": sem_cadastro,
        "divergentes": sum(1 for x in linhas if x["divergente"]),
        # ⚠️ Truncar calado foi o erro que custou "992 criado(s)" no catálogo:
        # indistinguível de "o catálogo tem 992". Aqui o mesmo teto existe, e
        # quando bate, a tela precisa dizer.
        "truncado": truncou["foi"],
        "message": (
            f"{vistos} produto(s) conferido(s)"
            + (f", {sem_cadastro} sem cadastro aqui" if sem_cadastro else "")
            + f" — {sum(1 for x in linhas if x['divergente'])} divergente(s)"
            + (". A varredura parou no teto de páginas — há mais no Omie."
               if truncou["foi"] else "")
        ),
    }
