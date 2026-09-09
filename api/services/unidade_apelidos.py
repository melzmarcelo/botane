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
