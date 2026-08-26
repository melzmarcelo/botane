"""Os grupos com que a casa separa o CMV por tipo de produto.

O CMV já mostrava Perdas, Consumo interno e Ajustes de inventário como linhas
que **explicam** o número. Faltava a pergunta que o dono faz olhando a nota do
mês: *quanto disto não é comida?* Detergente, sacola e marmita entram no custo
pela mesma porta dos insumos e somem no total — e o food cost sai mais alto do
que a cozinha realmente custa.

Aqui a casa monta os próprios grupos, escolhendo os tipos de produto que entram
em cada um. Um grupo pode juntar vários tipos ("Material de limpeza e
embalagem" = EMBALAGEM + MATERIAL_LIMPEZA).

⚠️ **Um tipo só entra em UM grupo, e quem garante é o banco**: `tipo` é a chave
primária de `cmv_grupo_tipos`. Conferir só na aplicação deixaria passar duas
telas gravando ao mesmo tempo — e o mesmo custo apareceria em dois grupos, com
a soma dos grupos deixando de fechar com o CMV do período, que é justamente a
propriedade que dá sentido ao relatório.

⚠️ **O vínculo é com o TIPO, não com o produto.** Mudar a configuração
reclassifica o passado inteiro sem tocar em cadastro nenhum. Gravar o grupo no
produto exigiria varrer o cadastro a cada mudança — e deixaria para trás
exatamente os produtos antigos, que são os que têm histórico.
"""

from datetime import date

from fastapi import HTTPException

from models.produtos import TIPOS
from services import relatorios


def listar(cur) -> list[dict]:
    """Os grupos e os tipos de cada um, na ordem em que aparecem no CMV."""
    cur.execute(
        """SELECT g.id, g.nome, g.ordem, g.ativo, g.considerar_no_cmv,
                  coalesce(array_agg(t.tipo ORDER BY t.tipo)
                           FILTER (WHERE t.tipo IS NOT NULL), '{}') AS tipos
             FROM cmv_grupos g
             LEFT JOIN cmv_grupo_tipos t ON t.id_grupo = g.id
            GROUP BY g.id
            ORDER BY g.ordem, lower(g.nome)"""
    )
    return [dict(r) for r in cur.fetchall()]


def tipos_livres(cur, id_grupo: int | None = None) -> list[str]:
    """Os tipos que ainda não pertencem a grupo nenhum.

    Ao editar um grupo, os tipos DELE também são livres — senão a tela abriria
    sem as próprias escolhas e quem só quisesse renomear perderia a seleção.
    """
    cur.execute(
        "SELECT tipo FROM cmv_grupo_tipos WHERE id_grupo IS DISTINCT FROM %s",
        (id_grupo,),
    )
    ocupados = {r["tipo"] for r in cur.fetchall()}
    return [t for t in TIPOS if t not in ocupados]


def _validar(cur, nome: str, tipos: list[str], id_grupo: int | None) -> None:
    if not nome.strip():
        raise HTTPException(status_code=400, detail="O grupo precisa de um nome.")

    desconhecidos = [t for t in tipos if t not in TIPOS]
    if desconhecidos:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de produto que não existe: {', '.join(desconhecidos)}.",
        )

    # ⚠️ Nome repetido daria duas linhas iguais na tela do CMV, e ninguém
    # saberia qual é qual. O índice único do banco é quem manda; a conferência
    # aqui existe só para a mensagem sair em português, e não como 500.
    cur.execute(
        "SELECT id FROM cmv_grupos WHERE lower(nome) = lower(%s) AND id IS DISTINCT FROM %s",
        (nome.strip(), id_grupo),
    )
    if cur.fetchone():
        raise HTTPException(status_code=409, detail=f"Já existe um grupo chamado {nome}.")

    if tipos:
        cur.execute(
            """SELECT t.tipo, g.nome FROM cmv_grupo_tipos t
                 JOIN cmv_grupos g ON g.id = t.id_grupo
                WHERE t.tipo = ANY(%s) AND t.id_grupo IS DISTINCT FROM %s""",
            (tipos, id_grupo),
        )
        tomados = cur.fetchall()
        if tomados:
            quais = ", ".join(f"{r['tipo']} (já está em {r['nome']})" for r in tomados)
            raise HTTPException(
                status_code=409,
                detail=(f"Um tipo de produto só pode estar num grupo: {quais}. "
                        "Tire-o do outro grupo antes."),
            )


def _gravar_tipos(cur, id_grupo: int, tipos: list[str]) -> None:
    cur.execute("DELETE FROM cmv_grupo_tipos WHERE id_grupo = %s", (id_grupo,))
    for tipo in tipos:
        cur.execute(
            "INSERT INTO cmv_grupo_tipos (tipo, id_grupo) VALUES (%s, %s)",
            (tipo, id_grupo),
        )


def criar(cur, nome: str, tipos: list[str], ordem: int = 0,
          considerar_no_cmv: bool = True) -> int:
    _validar(cur, nome, tipos, None)
    cur.execute(
        "INSERT INTO cmv_grupos (nome, ordem, considerar_no_cmv) VALUES (%s, %s, %s) "
        "RETURNING id",
        (nome.strip(), ordem, considerar_no_cmv),
    )
    novo = cur.fetchone()["id"]
    _gravar_tipos(cur, novo, tipos)
    return novo


def atualizar(cur, id_grupo: int, nome: str, tipos: list[str],
              ordem: int = 0, ativo: bool = True,
              considerar_no_cmv: bool = True) -> None:
    cur.execute("SELECT id FROM cmv_grupos WHERE id = %s", (id_grupo,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    _validar(cur, nome, tipos, id_grupo)
    cur.execute(
        "UPDATE cmv_grupos SET nome = %s, ordem = %s, ativo = %s, considerar_no_cmv = %s "
        "WHERE id = %s",
        (nome.strip(), ordem, ativo, considerar_no_cmv, id_grupo),
    )
    _gravar_tipos(cur, id_grupo, tipos)


def excluir(cur, id_grupo: int) -> None:
    """Apaga o grupo. Os tipos voltam a ficar livres (cascata no banco).

    ⚠️ Grupo do CMV não vira inativo ao ser apagado, ao contrário de produto e
    fornecedor: ele não é referenciado por movimento nenhum: é só um jeito de
    somar. Apagar não perde histórico — o próximo relatório soma sem ele.
    """
    cur.execute("SELECT id FROM cmv_grupos WHERE id = %s", (id_grupo,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    cur.execute("DELETE FROM cmv_grupos WHERE id = %s", (id_grupo,))


def valores(cur, id_unidade: int, inicio: date, fim: date) -> list[dict]:
    """Quanto do CMV do período está em cada grupo configurado.

    ⚠️ Passa pela MESMA conta do relatório por setor (`cmv_por_grupo`), e não
    por uma soma escrita à parte: o painel e o relatório mostram o mesmo número
    lado a lado, e duas implementações discordariam no primeiro caso de borda —
    com o agravante de que ninguém saberia qual das duas está certa.

    "Sem grupo" fica de fora: no painel a linha explica o que FOI separado; o
    resto já é o próprio CMV.
    """
    grupos = [g for g in listar(cur) if g["ativo"] and g["tipos"]]
    if not grupos:
        return []

    # ⚠️ **Grupo configurado aparece mesmo valendo zero.** O relatório por grupo
    # descarta quem não teve movimento — ali é a lista do que pesou. No painel a
    # linha é uma resposta a uma pergunta que a casa fez ao configurar o grupo, e
    # "não apareceu" é indistinguível de "não salvou". É o mesmo motivo pelo qual
    # Perdas mostra R$ 0,00 num mês sem perda em vez de sumir da tabela.
    medido = {l["grupo"]: l for l in
              relatorios.cmv_por_grupo(cur, id_unidade, inicio, fim, "grupo")}

    # ⚠️ Na ordem que a CASA definiu, não na do valor. O relatório ordena pelo
    # que pesa mais; aqui as linhas ficam paradas onde o dono as pôs, senão elas
    # trocam de lugar entre um período e outro e ninguém acha a que procura.
    return [
        {
            "nome": g["nome"],
            "cmv": float(medido[g["nome"]]["cmv"]) if g["nome"] in medido else 0.0,
            "compras": float(medido[g["nome"]]["compras"]) if g["nome"] in medido else 0.0,
            "produtos": medido[g["nome"]]["produtos"] if g["nome"] in medido else 0,
            "tipos": list(g["tipos"]),
            # ⚠️ A tela precisa dizer isso ao lado do número: um grupo fora do
            # CMV mostra um valor que NÃO está no total acima, e sem o aviso
            # parece que a conta não fecha.
            "considerar_no_cmv": g["considerar_no_cmv"],
        }
        for g in grupos
    ]
