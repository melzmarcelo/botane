"""Colher o código de barras que a NOTA FISCAL já trouxe.

🔑 **A maior fonte gratuita de EAN que a casa tem é a própria compra**
(08/09/2026). Medido na base: 1.164 dos 3.183 produtos têm código de barras —
os outros 2.019 não têm nenhum, e **nenhuma API de GTIN ajuda quem não tem o
número**. O XML da NF-e traz `cEAN` do item, o parser já o guarda em
`nota_itens.codigo_barras`, e ele ficava parado ali.

⚠️ **É uma fonte melhor que qualquer base pública**, e por dois motivos: o
fornecedor está declarando o GTIN do que ELE mandou, num documento fiscal; e
cobre exatamente o que a casa compra — inclusive o que o Open Food Facts nunca
vai ter, que é o item de food service (`MORT DEF SOLTIS FAT 200G 3UN CX21UN`).

⚠️ **Ainda assim, SUGERE e não aplica sozinho.** Três armadilhas justificam a
confirmação humana, e as três aparecem na prévia:

1. **O EAN da nota pode ser o da CAIXA, não o da unidade.** `cEAN` é o GTIN da
   unidade COMERCIAL — se a nota vende caixa com 12, o código é o da caixa. O
   produto aqui é estocado na unidade, e gravar o código da caixa nele rotula
   errado o que se conta na prateleira. Por isso a prévia mostra a unidade da
   nota ao lado da unidade do produto: quando diferem, é sinal de alerta.
2. **O vínculo item→produto pode estar errado.** Ele vem do de-para, e de-para
   errado leva o EAN do produto do vizinho.
3. **`codigo_barras` é ÚNICO** (`ux_produto_barras`). Dois produtos recebendo o
   mesmo EAN é o sintoma de (2), e o banco recusaria o segundo no meio do lote.
   Aqui isso vira conflito na prévia, exibido antes, em vez de erro no fim.
"""

from services.openfoodfacts import digito_verificador_ok


def _utilizavel(codigo: str | None) -> bool:
    """Serve para gravar no cadastro?

    ⚠️ **A régua aqui é MAIS FROUXA que a do Open Food Facts**, de propósito, e
    a diferença é a pergunta que cada uma responde. Lá o código precisa
    identificar o produto no MUNDO — por isso a faixa 2 (uso interno de loja) é
    recusada: o que a base pública devolver para ela é outro produto qualquer.
    Aqui o código só precisa ser um GTIN bem formado que o fornecedor declarou
    na nota; ele identifica a embalagem que entrou pela porta, e é isso que se
    quer guardar. O dígito verificador continua obrigatório: sem ele, entra
    qualquer sequência que o emitente digitou errado.
    """
    codigo = (codigo or "").strip()
    return bool(codigo) and digito_verificador_ok(codigo)


def previa(cur, id_unidade: int) -> dict:
    """O que a colheita preencheria — antes de preencher.

    Uma linha por produto SEM código de barras que apareça em alguma nota com um
    EAN válido. Traz a nota de origem, o fornecedor e as duas unidades, que é o
    que permite reconhecer o caso da caixa.
    """
    cur.execute(
        """WITH candidato AS (
               SELECT ni.id_produto,
                      ni.codigo_barras,
                      ni.um_nota,
                      ni.descricao_fornecedor,
                      ne.numero AS nota,
                      ne.data_emissao,
                      f.nome AS fornecedor,
                      -- ⚠️ **A nota mais RECENTE ganha.** Embalagem muda, e o
                      -- código da compra de ontem descreve melhor o que está na
                      -- prateleira hoje que o de dois anos atrás.
                      row_number() OVER (
                          PARTITION BY ni.id_produto
                          ORDER BY ne.data_emissao DESC NULLS LAST, ne.id DESC
                      ) AS ordem
                 FROM nota_itens ni
                 JOIN notas_entrada ne ON ne.id = ni.id_nota
                 LEFT JOIN fornecedores f ON f.id = ne.id_fornecedor
                 JOIN produtos p ON p.id = ni.id_produto
                WHERE ne.id_unidade = %s
                  AND NOT coalesce(ni.ignorado, false)
                  AND ni.codigo_barras IS NOT NULL AND ni.codigo_barras <> ''
                  AND (p.codigo_barras IS NULL OR p.codigo_barras = '')
           )
           SELECT c.id_produto, p.codigo, p.nome, p.um_estoque,
                  c.codigo_barras, c.um_nota, c.descricao_fornecedor,
                  c.nota, c.data_emissao, c.fornecedor,
                  -- Quem já tem este código: o conflito da unicidade, dito antes.
                  (SELECT o.nome FROM produtos o
                    WHERE o.codigo_barras = c.codigo_barras LIMIT 1) AS ja_e_de
             FROM candidato c
             JOIN produtos p ON p.id = c.id_produto
            WHERE c.ordem = 1
            ORDER BY p.nome""",
        (id_unidade,),
    )

    linhas, conflitos, vistos = [], [], {}
    for bruto in cur.fetchall():
        linha = dict(bruto)
        codigo = linha["codigo_barras"]

        if not _utilizavel(codigo):
            # Dígito que não fecha é digitação do emitente, não código.
            linha["motivo"] = "O dígito verificador não confere — o emitente digitou errado."
            conflitos.append(linha)
            continue
        if linha["ja_e_de"]:
            linha["motivo"] = f"Este código já é de “{linha['ja_e_de']}”."
            conflitos.append(linha)
            continue
        if codigo in vistos:
            # Dois produtos com o mesmo EAN: um dos dois de-para está errado, e
            # o banco recusaria o segundo. Nenhum dos dois entra.
            linha["motivo"] = f"O mesmo código apareceu em “{vistos[codigo]}”."
            conflitos.append(linha)
            continue

        vistos[codigo] = linha["nome"]
        # 🔑 A unidade da nota diferente da do estoque é o sinal do caso da
        # CAIXA. Não impede — quem olha decide —, mas precisa estar à vista.
        linha["unidade_diverge"] = bool(
            linha["um_nota"] and linha["um_estoque"]
            and linha["um_nota"].strip().upper() != linha["um_estoque"].strip().upper())
        linhas.append(linha)

    return {
        "linhas": linhas,
        "conflitos": conflitos,
        "total": len(linhas),
        "com_unidade_diferente": sum(1 for x in linhas if x["unidade_diverge"]),
    }


def colher(cur, id_unidade: int, ids_produto: list[int], id_usuario: int | None) -> dict:
    """Grava o EAN nos produtos escolhidos. Devolve quantos entraram.

    ⚠️ **Recalcula a prévia em vez de confiar no que a tela mandou.** A tela
    manda ids; o CÓDIGO de cada um vem daqui, agora. Aceitar o par
    (produto, código) do cliente deixaria qualquer chamador gravar o código que
    quisesse em qualquer produto — e este campo é único, então um código
    plantado aqui bloqueia o produto legítimo dele para sempre.

    ⚠️ **`WHERE codigo_barras IS NULL` no UPDATE**, mesmo já filtrado na prévia:
    entre ver a tela e clicar, alguém pode ter preenchido à mão. Quem digitou
    ganha de quem colheu.
    """
    if not ids_produto:
        return {"gravados": 0, "message": "Nenhum produto escolhido."}

    escolhidos = set(ids_produto)
    gravados = 0
    for linha in previa(cur, id_unidade)["linhas"]:
        if linha["id_produto"] not in escolhidos:
            continue
        cur.execute(
            """UPDATE produtos
                  SET codigo_barras = %s, revisado_em = now(), revisado_por = %s
                WHERE id = %s AND (codigo_barras IS NULL OR codigo_barras = '')""",
            (linha["codigo_barras"], id_usuario, linha["id_produto"]),
        )
        gravados += cur.rowcount

    return {
        "gravados": gravados,
        "message": (f"{gravados} produto(s) ganharam código de barras."
                    if gravados else "Nada foi gravado."),
    }
