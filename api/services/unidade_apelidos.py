"""As unidades que chegam de fora, e o que elas querem dizer aqui.

🔑 **Decisão do dono (09/09/2026):** *"conforme as unidades vão chegando pelas
notas podemos ir vinculando ou cadastrando"* — em vez de importar de uma vez as
603 unidades do cadastro do Omie, que é global e tem `%`, `01` e `18x4x4` no
meio. Mesmo restrito às que os produtos da casa usam sobram 57 siglas para uns
doze conceitos, e criá-las como unidades faria o combo oferecer sete coisas
diferentes que significam "unidade".

⚠️ **O silêncio que isto vem consertar.** Item de nota com unidade desconhecida
não parava o lançamento: a conversão não achava caminho e a quantidade entrava
**1:1**. Dez BJ de um produto contado em KG viravam dez quilos no razão, e o
custo unitário saía dividido por dez. Nada avisava — e a diferença só aparecia
no CMV do mês, longe da causa. Não parar a nota continua certo; o que faltava
era a unidade ficar SABIDA depois.

⚠️ **A fila é uma CONSULTA, não uma tabela.** É a mesma decisão da fila de envio
ao PDV: uma fila mantida à mão precisaria ser alimentada em todo lugar que grava
um item de nota, e o próximo lugar — que vai existir — nasceria sem ela. Aqui a
pergunta é feita ao dado: o que apareceu nas notas, menos o que já é unidade,
menos o que já foi traduzido.
"""


def limpar(um: str | None) -> str:
    """O texto como ele é comparado: maiúsculas, sem espaço nas pontas.

    ⚠️ **A pontuação de DANFE fica.** "CX." e "CX" são apelidos DIFERENTES de
    propósito: tirar o ponto aqui seria uma regra de tradução escondida na
    função de limpeza, e a próxima ("CX 12"?) não caberia nela. Quem traduz é o
    de-para, à vista de quem decidiu.
    """
    return (um or "").strip().upper()[:20]


def resolver(cur, um: str | None) -> str | None:
    """A unidade que ESTE texto significa aqui — ou `None` se ninguém sabe.

    Devolve o próprio texto quando ele já é uma unidade cadastrada: quem chama
    não precisa perguntar duas coisas.

    ⚠️ **A unidade de verdade vem PRIMEIRO.** Se "KG" existir como unidade e
    também como apelido (o `CHECK` do banco impede, mas a ordem não depende
    disso), o cadastro vence — um de-para nunca redefine o que a casa já
    definiu.
    """
    texto = limpar(um)
    if not texto:
        return None
    cur.execute("SELECT sigla FROM unidades_medida WHERE upper(sigla) = %s", (texto,))
    linha = cur.fetchone()
    if linha:
        return linha["sigla"]
    cur.execute("SELECT sigla FROM unidade_apelidos WHERE apelido = %s", (texto,))
    linha = cur.fetchone()
    return linha["sigla"] if linha else None


def pendentes(cur) -> list[dict]:
    """As unidades vistas em notas que o sistema ainda não sabe ler.

    Ordenadas pelo PESO — quantos itens de nota carregam cada uma. Quem vai
    resolver uma fila resolve primeiro a que aparece em 194 linhas, não a que
    apareceu uma vez em 2024.

    ⚠️ **Traz exemplos junto.** "PC" sozinho não diz se é peça, pacote ou peso;
    ver que ele veio em "COPO DESCARTAVEL 200ML" e "GUARDANAPO" resolve a dúvida
    sem sair da tela. Sem isso a pessoa teria de abrir as notas uma a uma.
    """
    cur.execute(
        """SELECT upper(trim(ni.um_nota))       AS apelido,
                  count(*)                      AS itens,
                  count(DISTINCT ni.id_nota)    AS notas,
                  max(n.data_emissao)           AS ultima_vez,
                  (array_agg(DISTINCT ni.descricao_fornecedor))[1:3] AS exemplos
             FROM nota_itens ni
             JOIN notas_entrada n ON n.id = ni.id_nota
            WHERE ni.um_nota IS NOT NULL
              AND trim(ni.um_nota) <> ''
              AND NOT EXISTS (SELECT 1 FROM unidades_medida u
                               WHERE upper(u.sigla) = upper(trim(ni.um_nota)))
              AND NOT EXISTS (SELECT 1 FROM unidade_apelidos a
                               WHERE a.apelido = upper(trim(ni.um_nota)))
            GROUP BY 1
            ORDER BY itens DESC, apelido"""
    )
    return [dict(r) for r in cur.fetchall()]


def listar(cur) -> list[dict]:
    """Os apelidos já traduzidos, com o que cada um virou."""
    cur.execute(
        """SELECT a.apelido, a.sigla, u.nome AS unidade, a.criado_em,
                  us.nome AS quem
             FROM unidade_apelidos a
             JOIN unidades_medida u ON u.sigla = a.sigla
             LEFT JOIN usuarios us ON us.id = a.criado_por
            ORDER BY a.apelido"""
    )
    return [dict(r) for r in cur.fetchall()]


def vincular(cur, apelido: str, sigla: str, id_usuario: int | None) -> dict:
    """Diz que este texto de fora significa esta unidade daqui.

    ⚠️ **Regravar é permitido, e é o caso comum.** Quem traduziu "PC" para UN e
    percebeu que era PCT precisa poder corrigir — e a correção vale para a
    próxima nota, não para as que já foram lançadas: o razão é append-only, e
    quantidade já gravada se corrige por estorno.
    """
    from fastapi import HTTPException

    apelido = limpar(apelido)
    sigla = (sigla or "").strip().upper()
    if not apelido or not sigla:
        raise HTTPException(status_code=400, detail="Informe o apelido e a unidade.")

    cur.execute("SELECT sigla FROM unidades_medida WHERE upper(sigla) = %s", (sigla,))
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(
            status_code=404,
            detail=f"Não existe unidade {sigla} aqui. Cadastre-a antes, ou escolha outra.")
    sigla = linha["sigla"]

    # ⚠️ Um apelido que é uma unidade de verdade traduziria o cadastro por cima
    # de si mesmo: "KG" apontando para "G" faria o quilo virar grama em toda
    # nota. O banco também recusa; aqui a recusa tem frase.
    cur.execute("SELECT 1 FROM unidades_medida WHERE upper(sigla) = %s", (apelido,))
    if cur.fetchone():
        raise HTTPException(
            status_code=409,
            detail=(f"{apelido} já é uma unidade cadastrada — ela não precisa de tradução. "
                    f"Se ela está errada, corrija a unidade em Cadastros."))

    cur.execute(
        """INSERT INTO unidade_apelidos (apelido, sigla, criado_por)
           VALUES (%s, %s, %s)
           ON CONFLICT (apelido) DO UPDATE
               SET sigla = EXCLUDED.sigla, criado_em = now(),
                   criado_por = EXCLUDED.criado_por""",
        (apelido, sigla, id_usuario),
    )
    return {"apelido": apelido, "sigla": sigla,
            "message": f"{apelido} passa a valer como {sigla}."}


def remover(cur, apelido: str) -> dict:
    """Desfaz a tradução. A unidade volta para a fila na próxima consulta."""
    cur.execute("DELETE FROM unidade_apelidos WHERE apelido = %s", (limpar(apelido),))
    return {"message": "Tradução removida."}


# ---------------------------------------------------------------------------
# Juntar unidades: a que veio do Omie como unidade de verdade vira apelido
# ---------------------------------------------------------------------------
#
# 🔑 **Pedido do dono (23/10/2026):** *"no Omie tem vários cadastros de unidades
# representando a mesma unidade. Exemplo: 1UNID/UN/UN1 é tudo UN … gostaria de um
# DE/PARA … e considerar somente uma no nosso sistema"*.
# ⚠️ **O de-para acima não alcançava esse caso**: ele só traduz texto que NÃO é
# unidade, e no ar `1UNID`, `UN1` e `UNID` foram CADASTRADAS como unidades (e `PAC`,
# `PCT` e `PT` são três "PACOTE"). Unidade diferente não converte (`custos.converter`
# só junta CX e UN quando o produto diz quantas cabem), então cada uma partia o
# custo e o combo do cadastro oferecia quatro "UNIDADE".
# 🔑 **Juntar = mover tudo o que USA a absorvida para a principal, apagar a absorvida
# e deixá-la como APELIDO da principal.** Assim a nota e o catálogo do Omie que
# chegarem com "UN1" continuam entendidos, agora como UN, sem ninguém traduzir de novo.
# ⚠️ **O razão NÃO se reescreve** (regra 1): `estoque_movimentos.um` continua dizendo
# "UN1" nas linhas antigas, e quem compara essa coluna com a unidade do produto
# resolve pelo apelido (`sql_resolvida`). O mesmo vale para o que é HISTÓRIA ou texto
# de fora: `nota_itens.um_nota`, `produtos.um_omie`, `cmv_movimentacao.um_estoque`.

# O que se reescreve: as colunas que apontam para o CADASTRO (as cinco com chave
# estrangeira) e duas sem chave que descrevem o presente — o que se conta no
# inventário e o que diz a etiqueta. (tabela, coluna)
_REAPONTAR = (("produtos", "um_estoque"), ("produtos", "um_compra"),
              ("fichas_tecnicas", "rendimento_um"), ("ficha_itens", "um"),
              ("inventario_itens", "um_informada"), ("etiquetas", "um"))


def sql_resolvida(coluna: str) -> str:
    """A expressão SQL que lê uma sigla gravada já traduzida pelo de-para.

    Para comparar o que foi gravado ANTES de uma junção ("UN1" no razão) com o
    cadastro de HOJE ("UN"). Sem tradução, a sigla como está, em maiúsculas.
    """
    return (f"coalesce((SELECT a_.sigla FROM unidade_apelidos a_ "
            f"WHERE a_.apelido = upper(trim({coluna}))), upper(trim({coluna})))")


def _par(cur, absorvida: str, principal: str) -> tuple[dict, dict]:
    from fastapi import HTTPException

    a, p = absorvida.strip().upper(), principal.strip().upper()
    if a == p:
        raise HTTPException(status_code=400, detail="Escolha outra unidade para ficar.")
    cur.execute("""SELECT sigla, nome, grandeza, fator_base, ativo FROM unidades_medida
                    WHERE upper(sigla) IN (%s, %s)""", (a, p))
    achadas = {r["sigla"].upper(): dict(r) for r in cur.fetchall()}
    if a not in achadas:
        raise HTTPException(status_code=404, detail=f"Não existe unidade {a} aqui.")
    if p not in achadas:
        raise HTTPException(status_code=404, detail=f"Não existe unidade {p} aqui.")
    ua, up = achadas[a], achadas[p]
    # ⚠️ **Só junta o que é a MESMA medida.** CX12 e DZ têm o mesmo fator e não são a
    # mesma coisa para quem compra; KG e G têm grandeza igual e fatores diferentes —
    # juntar trocaria quilo por grama em toda ficha. A grandeza E o fator têm de bater.
    if ua["grandeza"] != up["grandeza"] or float(ua["fator_base"]) != float(up["fator_base"]):
        raise HTTPException(
            status_code=409,
            detail=(f"{a} ({ua['nome'].lower()}, {ua['grandeza'].lower()} × "
                    f"{float(ua['fator_base']):g}) e {p} ({up['nome'].lower()}, "
                    f"{up['grandeza'].lower()} × {float(up['fator_base']):g}) não são a mesma "
                    f"medida — juntar mudaria quantidades. Use o fator do produto."))
    return ua, up


def _conflitos_de_compra(cur, a: str, p: str) -> list[dict]:
    """Produto com as DUAS unidades de compra e fatores diferentes: quem decide é gente."""
    cur.execute(
        """SELECT pr.id, pr.codigo, pr.nome, ua.fator AS fator_absorvida,
                  up.fator AS fator_principal
             FROM produto_unidades ua
             JOIN produto_unidades up ON up.id_produto = ua.id_produto
                                     AND upper(up.um) = %s
             JOIN produtos pr ON pr.id = ua.id_produto
            WHERE upper(ua.um) = %s AND ua.fator <> up.fator
            ORDER BY pr.nome""", (p, a))
    return [dict(r) for r in cur.fetchall()]


def previa_juntar(cur, absorvida: str, principal: str) -> dict:
    """O que a junção vai mexer, sem mexer: quantos de cada coisa, e o que impede."""
    ua, up = _par(cur, absorvida, principal)
    a, p = ua["sigla"].upper(), up["sigla"].upper()
    contas = {}
    for tabela, coluna in (*_REAPONTAR, ("produto_unidades", "um")):
        cur.execute(f"SELECT count(*) AS n FROM {tabela} WHERE upper({coluna}) = %s", (a,))
        contas[f"{tabela}.{coluna}"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM estoque_movimentos WHERE upper(um) = %s", (a,))
    no_razao = cur.fetchone()["n"]
    cur.execute("SELECT apelido FROM unidade_apelidos WHERE upper(sigla) = %s", (a,))
    apelidos = [r["apelido"] for r in cur.fetchall()]
    conflitos = _conflitos_de_compra(cur, a, p)
    return {
        "absorvida": ua, "principal": up,
        "produtos_estoque": contas["produtos.um_estoque"],
        "produtos_compra": contas["produtos.um_compra"] + contas["produto_unidades.um"],
        "fichas": contas["fichas_tecnicas.rendimento_um"] + contas["ficha_itens.um"],
        "inventario": contas["inventario_itens.um_informada"],
        "etiquetas": contas["etiquetas.um"],
        "movimentos_no_razao": no_razao,
        "apelidos_que_mudam": apelidos,
        "conflitos": conflitos,
        "pode": not conflitos,
    }


def juntar(cur, absorvida: str, principal: str, id_usuario: int | None) -> dict:
    """Junta a absorvida na principal, numa transação só. Ver o bloco acima."""
    from fastapi import HTTPException

    ua, up = _par(cur, absorvida, principal)
    a, p_sigla = ua["sigla"], up["sigla"]
    A, P = a.upper(), p_sigla.upper()
    conflitos = _conflitos_de_compra(cur, A, P)
    if conflitos:
        lista = "; ".join(f"{c['nome']} ({float(c['fator_absorvida']):g} × "
                          f"{float(c['fator_principal']):g})" for c in conflitos[:5])
        raise HTTPException(
            status_code=409,
            detail=(f"{len(conflitos)} produto(s) compram em {a} e em {p_sigla} com fatores "
                    f"diferentes — acerte a unidade de compra deles antes: {lista}"))
    feito = {}
    # A unidade de compra repetida (mesmo fator dos dois lados) sai; a padrão passa
    # para a linha que fica, para o produto não perder a sugestão da tela.
    # ⚠️ Em dois passos: o índice "uma padrão por produto" recusaria as duas
    # marcadas ao mesmo tempo, e o DELETE logo abaixo leva a absorvida.
    cur.execute(
        """SELECT ua.id_produto FROM produto_unidades ua
             JOIN produto_unidades up ON up.id_produto = ua.id_produto AND upper(up.um) = %s
            WHERE upper(ua.um) = %s AND ua.padrao""", (P, A))
    herdam_padrao = [r["id_produto"] for r in cur.fetchall()]
    if herdam_padrao:
        cur.execute("""UPDATE produto_unidades SET padrao = false
                        WHERE upper(um) = %s AND id_produto = ANY(%s)""", (A, herdam_padrao))
        cur.execute("""UPDATE produto_unidades SET padrao = true
                        WHERE upper(um) = %s AND id_produto = ANY(%s)""", (P, herdam_padrao))
    cur.execute(
        """DELETE FROM produto_unidades ua
            WHERE upper(ua.um) = %s
              AND EXISTS (SELECT 1 FROM produto_unidades up
                           WHERE up.id_produto = ua.id_produto AND upper(up.um) = %s)""",
        (A, P))
    feito["unidades_de_compra_repetidas"] = cur.rowcount
    for tabela, coluna in (*_REAPONTAR, ("produto_unidades", "um")):
        cur.execute(f"UPDATE {tabela} SET {coluna} = %s WHERE upper({coluna}) = %s",
                    (p_sigla, A))
        feito[f"{tabela}.{coluna}"] = cur.rowcount
    # Quem traduzia PARA a absorvida passa a traduzir para a principal.
    cur.execute("UPDATE unidade_apelidos SET sigla = %s WHERE upper(sigla) = %s", (p_sigla, A))
    feito["apelidos_reapontados"] = cur.rowcount
    cur.execute("DELETE FROM unidades_medida WHERE sigla = %s", (a,))
    cur.execute(
        """INSERT INTO unidade_apelidos (apelido, sigla, criado_por) VALUES (%s, %s, %s)
           ON CONFLICT (apelido) DO UPDATE SET sigla = EXCLUDED.sigla, criado_em = now(),
                                               criado_por = EXCLUDED.criado_por""",
        (limpar(a), p_sigla, id_usuario))
    return {"absorvida": a, "principal": p_sigla, "feito": feito,
            "message": (f"{a} juntada em {p_sigla}: o cadastro passa a ter só {p_sigla}, e o "
                        f"que chegar como {a} (nota ou Omie) vale como {p_sigla}.")}
