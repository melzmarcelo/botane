"""Importador de notas de entrada: do Omie até o razão de estoque.

O caminho, e o que cada passo garante:

    ListarNotaEnt ─▶ notas_entrada        chave da NF-e única: reimportar não duplica
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
from services.custos import CASAS_CUSTO, converter, dec
from services.omie import mapeadores
from services.omie.cliente import ClienteOmie, ErroOmie

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

    # 2. EAN — chave natural, não depende de quem digitou
    if ean:
        cur.execute(
            "SELECT id FROM produtos WHERE codigo_barras = %s AND ativo", (ean,)
        )
        achado = cur.fetchone()
        if achado:
            return achado["id"], None, 100.0, "ean"

    # 3. código no fornecedor — resolve hortifrúti e distribuidor sem EAN
    if codigo and id_fornecedor:
        cur.execute(
            """SELECT pf.id_produto FROM produto_fornecedor pf
                WHERE pf.id_fornecedor = %s AND lower(pf.codigo_no_fornecedor) = lower(%s)""",
            (id_fornecedor, codigo),
        )
        achado = cur.fetchone()
        if achado:
            return achado["id_produto"], None, 100.0, "fornecedor"

    # 4. semelhança de descrição (+ NCM igual) → só sugestão
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


def _fator_do_item(cur, id_produto: int, id_fornecedor: int | None, codigo: str | None) -> Decimal:
    """Quantas unidades de estoque vêm em uma unidade da nota."""
    if codigo:
        cur.execute(
            "SELECT fator FROM codigos_externos WHERE sistema = %s AND codigo = %s",
            (SISTEMA, codigo),
        )
        linha = cur.fetchone()
        if linha and dec(linha["fator"]) > 0:
            return dec(linha["fator"])
    if id_fornecedor:
        cur.execute(
            """SELECT fator FROM produto_fornecedor
                WHERE id_produto = %s AND id_fornecedor = %s""",
            (id_produto, id_fornecedor),
        )
        linha = cur.fetchone()
        if linha and dec(linha["fator"]) > 0:
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
        """SELECT id, quantidade, valor_unitario, valor_total, valor_desconto, um_nota,
                  id_produto, codigo_fornecedor, frete_informado, outros_informado
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

        convertida, custo_unitario, variacao = None, None, None
        if item["id_produto"]:
            cur.execute("SELECT um_estoque FROM produtos WHERE id = %s", (item["id_produto"],))
            um_estoque = cur.fetchone()["um_estoque"]
            fator = _fator_do_item(cur, item["id_produto"], nota["id_fornecedor"],
                                   item["codigo_fornecedor"])
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
                direta = converter(qtd_nota, item["um_nota"], um_estoque, ums)
                convertida = direta if direta is not None else qtd_nota

            liquido = bruto - desconto_item + frete_item + outros_item
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

    cur.execute(
        """SELECT id, id_produto, quantidade_convertida, custo_aquisicao_unitario,
                  lote_nf, validade_nf
             FROM nota_itens
            WHERE id_nota = %s AND id_produto IS NOT NULL AND NOT ignorado ORDER BY seq""",
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
            id_local=id_local or nota["id_local"],
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
        if nota["id_fornecedor"]:
            cur.execute(
                """UPDATE produto_fornecedor
                      SET ultimo_preco = %s, ultima_compra = %s
                    WHERE id_produto = %s AND id_fornecedor = %s""",
                (item["custo_aquisicao_unitario"], nota["data_entrada"] or date.today(),
                 item["id_produto"], nota["id_fornecedor"]),
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
                    lote_nf, validade_nf, id_produto, sugestao_produto, sugestao_score,
                    frete_informado, outros_informado)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (id_nota, item["seq"], item["descricao_fornecedor"], item.get("codigo_fornecedor"),
             item.get("codigo_barras"), item.get("ncm"), item["quantidade"], item.get("um_nota"),
             item["valor_unitario"], item["valor_total"], item.get("valor_desconto") or 0,
             item.get("lote_nf"), item.get("validade_nf"), id_produto, sugestao, score,
             item.get("frete_informado"), item.get("outros_informado")),
        )

    calcular_nota(cur, id_nota)
    return id_nota, True


def sincronizar(cur, id_unidade: int, cliente: ClienteOmie, dias: int = 30) -> dict:
    """Puxa as notas de entrada da janela e grava o que ainda não existe aqui."""
    desde = (date.today() - timedelta(days=dias)).strftime("%d/%m/%Y")
    novas, repetidas, paginas = 0, 0, 0
    try:
        for dados, registros in cliente.paginar(
            "produtos/notaentrada", "ListarNotaEnt", "nfe_encontradas",
            {"dDtInicial": desde, "apenas_importado": "N"},
        ):
            paginas += 1
            for bruto in registros:
                nota = mapeadores.nota_de_entrada(bruto)
                _id, nova = gravar_nota(cur, id_unidade, nota, bruto)
                novas += 1 if nova else 0
                repetidas += 0 if nova else 1
    except ErroOmie as e:
        _registrar(cur, "produtos/notaentrada", "ListarNotaEnt", "ERRO", novas, e.mensagem,
                   cliente.modo, paginas)
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    _registrar(cur, "produtos/notaentrada", "ListarNotaEnt",
               "OK" if novas or repetidas else "VAZIO", novas + repetidas,
               f"{novas} nova(s), {repetidas} já existiam", cliente.modo, paginas)
    return {"novas": novas, "repetidas": repetidas, "paginas": paginas, "modo": cliente.modo}


def importar_catalogo(cur, cliente: ClienteOmie, id_usuario: int) -> dict:
    """Traz o catálogo do Omie como **rascunho**.

    É o jeito mais barato de nascer com centenas de insumos cadastrados. Rascunho
    não entra no estoque enquanto não tiver unidade e fator — a trava que protege
    o custo.
    """
    criados, atualizados, paginas = 0, 0, 0
    try:
        for _dados, registros in cliente.paginar(
            "geral/produtos", "ListarProdutos", "produto_servico_cadastro",
        ):
            paginas += 1
            for bruto in registros:
                p = mapeadores.produto_do_catalogo(bruto)
                if not p["codigo_omie"]:
                    continue
                cur.execute("SELECT id FROM produtos WHERE codigo_omie = %s", (p["codigo_omie"],))
                existente = cur.fetchone()
                if existente:
                    atualizados += 1
                    continue
                cur.execute(
                    """INSERT INTO produtos (codigo, nome, tipo, um_estoque, ncm, codigo_barras,
                                             codigo_omie, origem, status, controla_estoque,
                                             criado_por)
                       VALUES (%s, %s, 'INSUMO', %s, %s, %s, %s, 'OMIE', 'RASCUNHO', true, %s)
                       ON CONFLICT DO NOTHING RETURNING id""",
                    (p["codigo"] or f"OMIE-{p['codigo_omie']}", p["nome"], p["um"], p["ncm"],
                     p["codigo_barras"], p["codigo_omie"], id_usuario),
                )
                if cur.fetchone():
                    criados += 1
    except ErroOmie as e:
        _registrar(cur, "geral/produtos", "ListarProdutos", "ERRO", criados, e.mensagem,
                   cliente.modo, paginas)
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")

    _registrar(cur, "geral/produtos", "ListarProdutos", "OK", criados + atualizados,
               f"{criados} criado(s) em rascunho", cliente.modo, paginas)
    return {"criados": criados, "ja_existiam": atualizados, "modo": cliente.modo}


def conferir_estoque(cur, cliente: ClienteOmie) -> list[dict]:
    """Compara o custo médio daqui com o CMC do Omie — conferência cruzada de graça.

    Divergência quer dizer que alguma entrada não foi conciliada de um dos lados.
    """
    linhas = []
    try:
        for _dados, registros in cliente.paginar(
            "estoque/consulta", "ListarPosEstoque", "produtos", {"dDataPosicao": ""},
        ):
            for bruto in registros:
                pos = mapeadores.posicao_de_estoque(bruto)
                if not pos["codigo_omie"]:
                    continue
                cur.execute(
                    """SELECT p.id, p.nome,
                              coalesce(sum(s.quantidade), 0) AS saldo,
                              CASE WHEN coalesce(sum(s.quantidade), 0) > 0
                                   THEN sum(s.quantidade * s.custo_medio) / sum(s.quantidade)
                                   ELSE 0 END AS custo_medio
                         FROM produtos p
                         LEFT JOIN estoque_saldos s ON s.id_produto = p.id
                        WHERE p.codigo_omie = %s
                        GROUP BY p.id, p.nome""",
                    (pos["codigo_omie"],),
                )
                nosso = cur.fetchone()
                if not nosso:
                    continue
                diferenca = dec(nosso["custo_medio"]) - pos["cmc"]
                linhas.append({
                    "produto": nosso["nome"],
                    "codigo_omie": pos["codigo_omie"],
                    "saldo_botane": float(dec(nosso["saldo"])),
                    "saldo_omie": float(pos["saldo"]),
                    "custo_medio_botane": float(dec(nosso["custo_medio"])),
                    "cmc_omie": float(pos["cmc"]),
                    "diferenca": float(diferenca),
                    "divergente": abs(diferenca) > Decimal("0.01"),
                })
    except ErroOmie as e:
        raise HTTPException(status_code=502, detail=f"Omie: {e.mensagem}")
    return linhas
