"""Mudar o mesmo campo em VÁRIOS produtos de uma vez.

🔑 **O pedido do dono (09/09/2026):** "gostaria de selecionar vários produtos e
inativar, ou selecionar vários e colocar em um tipo ou categoria ou setor".

O catálogo tem 3.183 produtos e 2.229 vieram do Omie sem categoria nem setor.
Arrumar isso um a um é abrir a ficha, escolher, salvar e voltar — quatro passos
por produto, e ninguém faz duas mil vezes. O trabalho não é feito, e o CMV por
grupo responde com "sem categoria" no maior pedaço da lista.

⚠️ **PRÉVIA antes, sempre** (`simular=True`). É a mesma regra da fusão e da
colheita de EAN, e aqui vale mais: quem marcou 300 linhas não tem como conferir
uma a uma depois. A prévia diz quantos MUDAM de verdade, quantos já estavam
assim, e quais o servidor recusa — antes de qualquer escrita.

⚠️ **A prévia e a aplicação são a MESMA função.** Duas implementações
divergiriam no primeiro caso especial, e a divergência apareceria como "a prévia
prometeu 300 e mudou 280" — sem ninguém saber qual das duas estava certa.
"""

from models.produtos import TIPOS

# Só estes. `um_estoque`, `codigo` e preço ficam de fora de propósito: o
# primeiro converte custo e saldo (ver `troca_de_unidade`), e os outros dois são
# identidade de UM produto — mudá-los em lote não quer dizer nada.
CAMPOS = ("tipo", "id_categoria", "id_setor", "ativo")


def _recusa(produto: dict, mudancas: dict) -> str | None:
    """Por que ESTE produto não pode receber esta mudança. `None` = pode."""
    tipo = mudancas.get("tipo") or produto["tipo"]
    # ⚠️ **Produção própria só existe em produzido/kit.** Mudar o tipo de um
    # prato para INSUMO deixaria `producao_propria` verdadeiro num tipo que não
    # a aceita — o banco recusa, e num lote isso derrubaria a transação inteira
    # no meio. Aqui vira recusa nomeada, e os outros seguem.
    if produto["producao_propria"] and tipo not in ("PRODUZIDO", "KIT"):
        return (f"é de produção própria e {tipo} não aceita isso — "
                "desmarque a produção própria antes")
    return None


def aplicar(cur, ids: list[int], mudancas: dict, id_usuario: int | None,
            simular: bool = True) -> dict:
    """O que a alteração faria, ou fez. Devolve o mesmo formato nos dois casos."""
    campos = {c: v for c, v in mudancas.items() if c in CAMPOS and v is not None}
    if not campos:
        return {"mudam": [], "iguais": [], "recusados": [],
                "message": "Nenhuma alteração escolhida."}
    if "tipo" in campos and campos["tipo"] not in TIPOS:
        return {"mudam": [], "iguais": [], "recusados": [],
                "message": f"Tipo inválido. Use: {', '.join(TIPOS)}"}
    if not ids:
        return {"mudam": [], "iguais": [], "recusados": [],
                "message": "Nenhum produto escolhido."}

    cur.execute(
        """SELECT p.id, p.codigo, p.nome, p.tipo, p.id_categoria, p.id_setor,
                  p.ativo, p.producao_propria,
                  c.nome AS categoria, s.nome AS setor
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores s ON s.id = p.id_setor
            WHERE p.id = ANY(%s)
            ORDER BY p.nome""",
        (ids,),
    )
    produtos = [dict(r) for r in cur.fetchall()]

    mudam, iguais, recusados = [], [], []
    for p in produtos:
        motivo = _recusa(p, campos)
        if motivo:
            recusados.append({**_resumo(p), "motivo": motivo})
            continue
        # 🔑 **"Já estava assim" não é mudança, e a prévia separa os dois.**
        # Quem marca 300 linhas para pôr numa categoria quer saber quantas
        # realmente estavam sem ela — "300 alterados" quando 280 já estavam
        # certos não informa nada.
        diferentes = {c: v for c, v in campos.items() if p[c] != v}
        (mudam if diferentes else iguais).append(
            {**_resumo(p), "muda": sorted(diferentes)})

    if not simular and mudam:
        alvos = [x["id"] for x in mudam]
        sets = ", ".join(f"{c} = %s" for c in campos)
        cur.execute(
            f"UPDATE produtos SET {sets} WHERE id = ANY(%s)",
            [*campos.values(), alvos],
        )
        # ⚠️ **Um registro de auditoria por PRODUTO, não um pelo lote.** Quem
        # for entender daqui a seis meses por que este produto mudou de
        # categoria procura pelo produto, não por um lote que não sabe que
        # existiu.
        import auditoria
        for x in mudam:
            auditoria.registrar(cur, id_usuario, "produto", x["id"],
                                "alteracao_multipla", depois=campos)

    verbo = "mudariam" if simular else "mudaram"
    partes = [f"{len(mudam)} {verbo}"]
    if iguais:
        partes.append(f"{len(iguais)} já estava(m) assim")
    if recusados:
        partes.append(f"{len(recusados)} recusado(s)")
    return {
        "mudam": mudam, "iguais": iguais, "recusados": recusados,
        "aplicado": not simular,
        "message": ", ".join(partes) + ".",
    }


def _resumo(p: dict) -> dict:
    return {"id": p["id"], "codigo": p["codigo"], "nome": p["nome"],
            "tipo": p["tipo"], "categoria": p["categoria"], "setor": p["setor"],
            "ativo": p["ativo"]}
