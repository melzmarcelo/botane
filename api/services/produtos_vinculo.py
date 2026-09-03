"""Dizer que dois cadastros são o mesmo produto — e fundi-los.

O sistema recebe produto por três portas: o catálogo do **Omie** (o que a casa
compra), o cardápio do **PDV Legal** (o que a casa vende) e a mão de quem
cadastra. Nenhuma chave impede o mesmo produto de existir duas vezes — entre
portas não há chave nenhuma, e dentro de uma a chave garante que o
*identificador* não repita, não que o *produto* não repita.

⚠️ **Aqui não se adivinha NADA.** Existiu um detector que cruzava os nomes por
semelhança, e ele errava nos dois sentidos: não achava "BEB CERV HEINEKEN 350ML"
contra "CERVEJA HEINEKEN PILSEN" (63,8% — o mesmo produto) e juntava "CAKE BOARD
N19" com "CAKE BOARD N21", que são tamanhos diferentes. Nenhum piso de
semelhança separa os dois casos, porque a diferença não está no texto. Quem
reconhece produto é gente; este arquivo guarda o que ela disse.

⚠️ **O estrago que a fusão conserta.** Com dois cadastros para o mesmo item: a
compra entra no estoque por um, a venda não sai por nenhum (o item do cardápio
nasce sem controlar estoque), e a sobra aparece na contagem como "ajuste de
inventário" — onde a diferença some sem nome. Dentro de uma porta, é o custo
médio existindo em dois lugares, com cada ficha puxando o de um deles.
"""

# ⚠️ **O que o absorvido NÃO pode ter — e a lista já foi maior.** A primeira
# versão barrava nota de entrada e vínculo de fornecedor, e isso estava errado:
# são PONTEIROS, não história. Um item de nota diz "esta linha é deste produto";
# se os dois cadastros são o mesmo produto, a linha muda de dono e pronto. O
# sintoma foi um caso real — "AGUA MINERAL C/GAS 600ML PLATINA", com ZERO
# movimento no razão, recusado por ter uma nota não lançada.
#
# O que sobrou aqui é o que de fato não se move:
#
# * o razão é **append-only** — saldo e custo médio são construídos dele;
# * o mês fechado é **congelado**, e já foi ao contador;
# * a contagem registra **o que foi contado naquele dia**;
# * uma produção **aconteceu**;
# * duas fichas próprias não cabem num cadastro só (uma vigente por produto).
#
# ⚠️ Nota LANÇADA não escapa: ela gerou movimento, e `estoque_movimentos` barra.
_IMPEDIMENTOS = (
    ("estoque_movimentos", "id_produto", "tem movimento no razão, que é append-only"),
    ("estoque_lotes", "id_produto", "tem lote em estoque"),
    ("cmv_movimentacao", "id_produto", "aparece num mês já fechado, que é congelado"),
    ("inventario_itens", "id_produto", "foi contado num inventário"),
    ("producoes", "id_produto", "tem produção registrada"),
    ("fichas_tecnicas", "id_produto", "tem ficha técnica própria"),
)

# ⚠️ O que MUDA DE DONO na fusão: ponteiros, não fatos. Cada linha é "esta
# entrada é deste produto", e se os dois cadastros são o mesmo produto, ela passa
# para o que fica.
#
# ⚠️ **Quatro destas têm unicidade COMPOSTA com o produto**, e mudar o dono às
# cegas estouraria o índice — derrubando a fusão inteira, não só aquela linha. O
# terceiro campo é a expressão que identifica a linha GÊMEA do lado que fica
# (`{a}` vira o apelido da tabela); existindo a gêmea, a do absorvido é
# descartada, porque a que fica já diz a mesma coisa.
_REAPONTAVEIS = (
    ("nota_itens", "id_produto", None),
    ("nota_itens", "sugestao_produto", None),
    ("produto_fornecedor", "id_produto", "{a}.id_fornecedor"),
    ("produto_unidades", "id_produto", "upper({a}.um)"),
    ("producao_agenda", "id_produto", "{a}.data_prevista"),
    ("ficha_itens", "id_insumo", None),
    ("kit_itens", "id_componente", "{a}.id_kit"),
    ("kit_itens", "id_kit", "{a}.id_componente"),
)

# ⚠️ Os campos que se completam quando estão em branco no que fica. `nome` e
# `nome_curto` ficam de FORA de propósito: eles têm regra própria, ver `_nomes`.
_COMPLETAVEIS = (
    "id_categoria", "id_setor", "um_estoque", "um_compra", "ncm", "cest", "marca",
    "peso_liquido", "peso_bruto", "id_local_padrao", "codigo_barras", "observacao",
)


def impedimentos(cur, id_produto: int) -> list[str]:
    """O que impede este cadastro de ser absorvido — em português."""
    achados = []
    for tabela, coluna, frase in _IMPEDIMENTOS:
        cur.execute(f"SELECT 1 FROM {tabela} WHERE {coluna} = %s LIMIT 1", (id_produto,))
        if cur.fetchone():
            achados.append(frase)
    return achados


def _carregar(cur, id_produto: int) -> dict | None:
    cur.execute(
        # ⚠️ `p.*` de propósito: os campos que se completam são uma LISTA
        # (`_COMPLETAVEIS`), e enumerá-los aqui também faria a lista viver em dois
        # lugares — um campo novo entraria na lista, não no SELECT, e passaria a
        # não migrar sem ninguém notar. Foi o que aconteceu com `marca`.
        """SELECT p.*, c.nome AS categoria,
                  (SELECT count(*) FROM estoque_movimentos m WHERE m.id_produto = p.id)
                      AS movimentos,
                  (SELECT count(*) FROM fichas_tecnicas f WHERE f.id_produto = p.id) AS fichas,
                  (SELECT coalesce(sum(vi.quantidade), 0) FROM venda_itens vi
                     JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
                    WHERE vi.id_produto = p.id) AS vendido
             FROM produtos p
             LEFT JOIN categorias c ON c.id = p.id_categoria
            WHERE p.id = %s""",
        (id_produto,),
    )
    linha = cur.fetchone()
    return dict(linha) if linha else None


def direcao(cur, id_tela: int, id_escolhido: int) -> tuple[int, int, bool]:
    """Quem fica e quem sai — decidido pelos FATOS, não pela tela em que se está.

    ⚠️ **Existe porque a versão anterior mandava a pessoa trocar de tela.** Quem
    abria o cadastro do cardápio e escolhia o do Omie levava "não pode ser
    absorvido… faça a fusão a partir dele" — uma recusa que já sabia a resposta e
    ainda assim exigia refazer o caminho. Se um lado tem história e o outro não,
    a direção não é escolha: é o único jeito que funciona.

    ⚠️ **Com os dois sem história, manda a TELA.** É o contexto de quem está
    olhando, e não há motivo para contrariá-lo.

    ⚠️ Com os DOIS carregando história, ninguém fica: a recusa é legítima e o
    chamador a levanta. Juntar duas histórias de estoque exigiria reescrever o
    razão, e o custo médio resultante seria invenção.

    A ordem dos critérios:

    1. **história** — só um lado pode ser absorvido, então não há escolha;
    2. **controlar estoque** — o cadastro que controla é o operacional; o do
       cardápio é um lugar-guardado que nasce sem controlar. Sem este critério,
       fundir o do Omie no rascunho do PDV produzia um produto com os dois
       códigos e **sem controlar estoque**: a compra deixaria de entrar no razão,
       calada, e o saldo pararia de existir para aquele item;
    3. **a tela** — sendo os dois iguais nos critérios acima, manda o contexto de
       quem está olhando.
    """
    if impedimentos(cur, id_escolhido) and not impedimentos(cur, id_tela):
        return id_escolhido, id_tela, True

    tela, escolhido = _carregar(cur, id_tela), _carregar(cur, id_escolhido)
    if (escolhido or {}).get("controla_estoque") and not (tela or {}).get("controla_estoque"):
        return id_escolhido, id_tela, True

    return id_tela, id_escolhido, False


def grupos_por_nome(cur, so_do_omie: bool = False, limite: int = 300) -> list[dict]:
    """Cadastros ATIVOS que têm exatamente o mesmo nome — os candidatos a fusão.

    🔑 **O caso do ABACATE, em lote** (pedido do dono, 03/09/2026). O catálogo do
    Omie cria um cadastro por CÓDIGO, e o mesmo abacate aparece uma vez para cada
    fornecedor que já o vendeu. Juntar de dois em dois pela tela do Vincular
    resolve, mas com centenas de repetidos ninguém percorre a lista.

    ⚠️ **Isto DETECTA, e não decide.** É a distinção que o projeto já pagou uma
    vez: existiu uma cascata que vinculava sozinha por semelhança de nome, e ela
    foi removida porque errava nos dois sentidos — não achava "BEB CERV HEINEKEN
    350ML" contra "CERVEJA HEINEKEN PILSEN" (o mesmo produto) e juntava "CAKE
    BOARD N19" com "CAKE BOARD N21", que são tamanhos diferentes.
    **Nome IDÊNTICO é um sinal muito mais forte que semelhança** — dentro de um
    catálogo só, é quase sempre o mesmo item —, mas continua sendo um sinal: o
    mapeador do Omie **apara todo texto no tamanho da coluna**, e dois nomes
    longos e diferentes podem chegar aqui iguais. Por isso a lista existe para
    ser OLHADA antes de virar fusão, e quem confirma é gente.

    ⚠️ **Só ATIVOS.** O absorvido de uma fusão anterior fica inativo e com o
    mesmo nome; incluí-lo faria a lista nunca esvaziar, propondo de novo o que já
    foi feito.

    ⚠️ **O principal é resolvido pelos MESMOS critérios da tela** (`direcao`),
    dobrando o grupo dois a dois — história primeiro, depois quem controla
    estoque. O desempate final é o **menor id**, que é o cadastro mais antigo:
    num grupo não há "a tela" para desempatar, e um critério estável é o que faz
    a prévia e a execução concordarem.
    """
    cur.execute(
        """SELECT p.nome, count(*) AS n
             FROM produtos p
            WHERE p.ativo
              AND (NOT %(so_omie)s OR p.codigo_omie IS NOT NULL)
            GROUP BY p.nome
           HAVING count(*) > 1
            ORDER BY count(*) DESC, p.nome
            LIMIT %(limite)s""",
        {"so_omie": so_do_omie, "limite": limite},
    )
    nomes = [dict(r) for r in cur.fetchall()]

    grupos = []
    for linha in nomes:
        cur.execute(
            """SELECT p.id, p.codigo, p.nome, p.codigo_omie, p.codigo_pdv, p.tipo,
                      p.controla_estoque, p.um_estoque, c.nome AS categoria,
                      (SELECT count(*) FROM estoque_movimentos m WHERE m.id_produto = p.id)
                          AS movimentos
                 FROM produtos p
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                WHERE p.ativo AND p.nome = %(nome)s
                  AND (NOT %(so_omie)s OR p.codigo_omie IS NOT NULL)
                ORDER BY p.id""",
            {"nome": linha["nome"], "so_omie": so_do_omie},
        )
        itens = [dict(r) for r in cur.fetchall()]
        for i in itens:
            i["travas"] = impedimentos(cur, i["id"])

        # O principal, pelos mesmos critérios da tela, dobrando o grupo.
        principal = itens[0]["id"]
        for outro in itens[1:]:
            principal, _sai, _inv = direcao(cur, principal, outro["id"])

        # ⚠️ **Grupo com DOIS que têm história não se funde**, e a lista diz isso
        # em vez de omitir: juntar duas histórias de estoque exigiria reescrever
        # o razão, e o custo médio resultante seria invenção.
        com_travas = [i for i in itens if i["travas"] and i["id"] != principal]
        grupos.append({
            "nome": linha["nome"],
            "quantos": len(itens),
            "id_principal": principal,
            "itens": itens,
            "pode": not com_travas,
            "impedidos": [i["id"] for i in com_travas],
        })
    return grupos


def fundir_grupo(cur, id_principal: int, ids_que_saem: list[int], id_usuario: int,
                 baixar_vendas: bool = True) -> dict:
    """Funde vários cadastros num só — o grupo inteiro de uma vez.

    🔑 **É a mesma `fundir`, repetida**, nunca uma segunda implementação: o
    de-para, a baixa do que foi vendido e sem sair do estoque, o custo dos itens
    de venda e o arquivamento do absorvido são os mesmos do botão Vincular. Duas
    implementações divergiriam na primeira correção.

    ⚠️ **Recusa ANTES de começar quando algum dos que saem tem história.** No
    meio do laço a recusa deixaria o grupo pela metade, e quem olhasse a lista
    depois não saberia dizer o que aconteceu com quais.

    ⚠️ **Recusa também quando o principal está na lista dos que saem** — seria o
    mesmo id dos dois lados, que é justamente o defeito que a tela do Vincular
    teve.
    """
    if id_principal in ids_que_saem:
        raise ValueError("O cadastro que fica não pode estar na lista dos que saem.")
    if not ids_que_saem:
        raise ValueError("Nenhum cadastro para juntar.")

    travados = {i: impedimentos(cur, i) for i in ids_que_saem}
    travados = {i: t for i, t in travados.items() if t}
    if travados:
        raise ValueError(
            "Estes cadastros têm história e não podem ser absorvidos: "
            + "; ".join(f"{i} ({', '.join(t)})" for i, t in travados.items()))

    feitos, baixados = [], 0
    for id_sai in ids_que_saem:
        r = fundir(cur, id_principal, id_sai, id_usuario, baixar_vendas)
        feitos.append(id_sai)
        # A chave real é `baixa_de_estoque`, posta só quando houve baixa.
        baixados += 1 if r.get("baixa_de_estoque") else 0
    return {"id_principal": id_principal, "juntados": feitos, "baixas": baixados}


def previa(cur, id_tela: int, id_escolhido: int) -> dict:
    """O que a fusão faria — para ver ANTES de mandar.

    ⚠️ Existe porque fusão não tem desfazer. Quem confirma precisa ver com que
    nome o produto vai ficar, o que muda de dono e o que impede.

    ⚠️ **A direção é resolvida aqui** (`direcao`), e a resposta diz quando ela foi
    invertida — a tela mostra "Fica / Sai" pelo resultado, não pelo cadastro em
    que a pessoa estava.
    """
    if id_tela == id_escolhido:
        raise ValueError("Escolha dois cadastros diferentes.")
    if not _carregar(cur, id_tela) or not _carregar(cur, id_escolhido):
        raise LookupError("Produto não encontrado.")

    id_fica, id_sai, invertido = direcao(cur, id_tela, id_escolhido)
    fica, sai = _carregar(cur, id_fica), _carregar(cur, id_sai)

    # ⚠️ Trocar a direção sem dizer por quê é pior que não trocar: a pessoa
    # confirma achando que o cadastro que abriu é o que fica.
    motivo = None
    if invertido:
        motivo = ("tem história que não muda de cadastro"
                  if impedimentos(cur, id_sai) or fica["movimentos"]
                  else "é o cadastro que controla estoque")

    travas = impedimentos(cur, id_sai)
    nome, nome_curto, de_onde = _nomes(fica, sai)

    cur.execute("SELECT count(*) AS n FROM venda_itens WHERE id_produto = %s", (id_sai,))
    itens_venda = cur.fetchone()["n"]

    return {
        "fica": fica, "sai": sai,
        "impedimentos": travas,
        "pode": not travas,
        "resultado": {
            "nome": nome, "nome_curto": nome_curto, "de_onde": de_onde,
            "codigo_omie": fica["codigo_omie"] or sai["codigo_omie"],
            "codigo_pdv": fica["codigo_pdv"] or sai["codigo_pdv"],
            "codigo_barras": fica["codigo_barras"] or sai["codigo_barras"],
        },
        "itens_de_venda": itens_venda,
        # 🔑 **As linhas de código EXTERNO que o cadastro passa a ter.** É o que
        # responde ao ABACATE: o catálogo do Omie cria um produto por código, e
        # juntar os cinco só é confiável se dá para ver, ANTES de confirmar, que
        # o principal vai responder pelos cinco códigos de lá.
        "codigos_externos": _codigos_do_resultado(cur, fica, sai),
        # ⚠️ A tela precisa saber que a direção foi trocada — senão a pessoa
        # confirma achando que o cadastro que ela abriu é o que fica.
        "invertido": invertido,
        "motivo_da_direcao": motivo,
        "id_fica": id_fica,
        "id_sai": id_sai,
        "baixa": _baixa_pendente(cur, fica, sai),
        "completa": [c for c in _COMPLETAVEIS
                     if not fica.get(c) and sai.get(c)],
    }


def _codigos_do_resultado(cur, fica: dict, sai: dict) -> list[dict]:
    """Os códigos de fora que vão cair no cadastro que fica, e de onde vêm.

    Três origens, e a tela mostra as três porque respondem a perguntas
    diferentes:

    * **principal** — a coluna `codigo_omie`/`codigo_pdv` do que fica;
    * **vira apelido** — a coluna do ABSORVIDO, quando os dois lados têm uma.
      É a linha que não existia: o `codigo_omie` de sair era simplesmente
      descartado, e a próxima nota que o trouxesse não achava o principal;
    * **já aponta** — o que já estava em `codigos_externos` dos dois lados (o do
      absorvido muda de dono na fusão).
    """
    linhas: list[dict] = []
    for coluna, sistema in (("codigo_omie", "OMIE_PRODUTO"), ("codigo_pdv", "PDV_LEGAL")):
        if fica.get(coluna):
            linhas.append({"sistema": sistema, "codigo": fica[coluna],
                           "origem": "principal", "descricao": fica["nome"]})
        if sai.get(coluna):
            # Sem código do lado que fica, ele sobe a PRINCIPAL em vez de virar
            # apelido — é o que `_absorver` faz, e a prévia tem de dizer o mesmo.
            linhas.append({
                "sistema": sistema, "codigo": sai[coluna],
                "origem": "principal" if not fica.get(coluna) else "vira apelido",
                "descricao": sai["nome"],
            })

    cur.execute(
        """SELECT c.sistema, c.codigo, c.descricao_externa, f.nome AS fornecedor
             FROM codigos_externos c
             LEFT JOIN fornecedores f ON f.id = c.id_fornecedor
            WHERE c.id_produto = ANY(%s)
            ORDER BY c.sistema, c.codigo""",
        ([fica["id"], sai["id"]],),
    )
    for r in cur.fetchall():
        linhas.append({"sistema": r["sistema"], "codigo": r["codigo"], "origem": "já aponta",
                       "descricao": r["descricao_externa"] or r["fornecedor"]})
    return linhas


def _baixa_pendente(cur, fica: dict, sai: dict) -> dict | None:
    """Quanto foi VENDIDO pelo cadastro absorvido e nunca saiu do estoque.

    ⚠️ **É o buraco que a fusão precisa fechar.** O item do cardápio nasce sem
    controlar estoque, então as vendas dele nunca tocaram o razão. Fundido no
    cadastro que compra, o resultado seria: comprou 15, vendeu 10, e o saldo
    dizendo 15. Na primeira contagem faltariam 10 unidades, aparecendo como
    "ajuste de inventário" — que é exatamente onde a diferença some sem nome, e é
    o problema que a fusão existe para resolver.

    ⚠️ **A conta é simples porque a trava garante**: só se absorve cadastro SEM
    movimento no razão, então NENHUMA venda dele baixou estoque. Não há o que
    separar entre "já baixou" e "não baixou".

    ⚠️ Só faz sentido quando o cadastro que FICA controla estoque. Se ele também
    não controla, não há prateleira de onde tirar — e a resposta honesta é nada.

    ⚠️ **O saldo pode ficar NEGATIVO**, e a prévia diz isso antes. Não é erro: o
    razão aceita, a saída sai por custo provisório e a próxima entrada revaloriza.
    Mas quem confirma precisa ver.
    """
    if not fica.get("controla_estoque"):
        return None

    cur.execute(
        """SELECT coalesce(sum(vi.quantidade), 0) AS qtd
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda AND NOT v.cancelada
            WHERE vi.id_produto = %s""",
        (sai["id"],),
    )
    quantidade = float(cur.fetchone()["qtd"] or 0)
    if quantidade <= 0:
        return None

    id_local = _local_da_baixa(cur, fica)
    cur.execute(
        """SELECT coalesce(sum(quantidade), 0) AS saldo FROM estoque_saldos
            WHERE id_produto = %s""",
        (fica["id"],),
    )
    saldo = float(cur.fetchone()["saldo"] or 0)

    cur.execute("SELECT nome FROM locais_estoque WHERE id = %s", (id_local,))
    local = (cur.fetchone() or {}).get("nome")

    return {
        "quantidade": quantidade,
        "um": fica.get("um_estoque"),
        "saldo_atual": saldo,
        "saldo_depois": saldo - quantidade,
        "fica_negativo": saldo - quantidade < 0,
        "id_local": id_local,
        "local": local,
    }


def _local_da_baixa(cur, fica: dict) -> int | None:
    """De qual prateleira a saída sai: a do produto, senão a principal da loja.

    Mesma ordem que a produção e a venda usam. Local errado registra a baixa por
    onde a mercadoria nunca passou, e o saldo do lugar certo continua cheio.
    """
    if fica.get("id_local_padrao"):
        return fica["id_local_padrao"]
    cur.execute(
        "SELECT id FROM locais_estoque WHERE ativo ORDER BY principal DESC, id LIMIT 1"
    )
    linha = cur.fetchone()
    return linha["id"] if linha else None


def _nomes(fica: dict, sai: dict) -> tuple[str, str | None, dict]:
    """De onde vem a descrição e a descrição curta.

    ⚠️ **A descrição longa vem do lado do OMIE e a curta do lado do PDV**, e não
    é preferência estética: são nomes com funções diferentes. O do Omie é o nome
    fiscal, o que aparece na nota do fornecedor e o que a pessoa procura quando
    confere uma compra — "BEB CERV HEINEKEN 350ML". O do PDV é o que sai no
    cupom e o que a equipe fala — "CERVEJA HEINEKEN PILSEN". Guardar os dois é o
    que faz o mesmo cadastro ser reconhecível nas duas pontas.

    ⚠️ Sem lado do Omie ou sem lado do PDV, vale o que o cadastro que FICA já
    tinha — nunca apagar para ficar em branco.
    """
    lado_omie = fica if fica["codigo_omie"] else (sai if sai["codigo_omie"] else None)
    lado_pdv = fica if fica["codigo_pdv"] else (sai if sai["codigo_pdv"] else None)

    nome = (lado_omie or fica)["nome"] or fica["nome"]
    curto = None
    if lado_pdv:
        curto = lado_pdv["nome_curto"] or lado_pdv["nome"]
    curto = curto or fica["nome_curto"]

    return nome, (curto[:60] if curto else None), {
        "nome": "omie" if lado_omie else "cadastro que fica",
        "nome_curto": "pdv" if lado_pdv else "cadastro que fica",
    }


def fundir(cur, id_tela: int, id_escolhido: int, id_usuario: int,
           baixar_vendas: bool = True) -> dict:
    """Funde os dois: um fica, o outro é inativado.

    ⚠️ **`baixar_vendas` fecha o buraco do estoque, e é o motivo de a fusão
    existir.** O item do cardápio vendia sem baixar (não controlava estoque);
    fundido no cadastro que compra, o resultado seria "comprou 15, vendeu 10,
    saldo 15" — e as 10 faltando apareceriam na primeira contagem como ajuste de
    inventário, que é onde a diferença some sem nome.

    ⚠️ **Não é lançamento retroativo, e é por isso que pode.** O razão é
    append-only: a saída entra com a data de HOJE, num movimento só, dizendo de
    onde veio. Datá-la no passado cairia dentro de mês possivelmente já fechado e
    reescreveria número que já foi ao contador.

    ⚠️ O tipo é **`SAIDA_VENDA`, não ajuste**: aquelas unidades foram vendidas
    mesmo. Como ajuste, elas engordariam a linha de "ajuste de inventário" do
    CMV — justamente a linha que quer dizer "não sabemos o que houve".

    ⚠️ Um movimento SÓ, com `origem_tipo = 'VINCULO'`. Cancelar depois uma
    daquelas vendas antigas não devolve a unidade ao estoque (o estorno procura
    por `origem_tipo = 'VENDA'`), e isso é aceito: a alternativa seria um
    movimento por venda antiga, todos com a data de hoje, enchendo o razão de
    linhas que não correspondem a nada que aconteceu naquele dia.

    ⚠️ **O custo dos itens de venda SEM custo é recalculado agora.** O item
    entrou contando zero no CMV teórico; ao ganhar um produto com ficha, passa a
    contar o que custa. Item que já tinha custo congelado NÃO é tocado — aquele
    número é o do dia em que a venda aconteceu.
    """
    from services import cmv as motor
    from services.omie import vinculo as vinculo_omie
    from services.pdv import vinculo

    conferido = previa(cur, id_tela, id_escolhido)
    # ⚠️ A MESMA resolução da prévia: o que a pessoa confirmou é o que acontece.
    id_fica, id_sai = conferido["id_fica"], conferido["id_sai"]
    if conferido["impedimentos"]:
        # ⚠️ Chegar aqui quer dizer que os DOIS têm história — a `direcao` já
        # teria invertido se só um tivesse. A frase diz isso, em vez de mandar
        # "fazer ao contrário", que não resolveria nada.
        raise PermissionError(
            f"Os dois cadastros têm história e nenhum pode ser absorvido. "
            f"“{conferido['sai']['nome']}” " + "; ".join(conferido["impedimentos"])
            + ". Juntar duas histórias de estoque exigiria reescrever o razão, que é "
            "append-only — desative um deles à mão e siga com o outro."
        )
    fica, sai = conferido["fica"], conferido["sai"]

    # ---------------------------------------------------------- os dois nomes
    nome, nome_curto, _ = _nomes(fica, sai)
    cur.execute(
        "UPDATE produtos SET nome = %s, nome_curto = %s WHERE id = %s",
        (nome, nome_curto, id_fica),
    )

    # ------------------------------------- os códigos únicos, só para lado vazio
    movidos: dict = {}
    for coluna in ("codigo_omie", "codigo_pdv", "codigo_barras"):
        if sai[coluna] and not fica[coluna]:
            cur.execute(f"UPDATE produtos SET {coluna} = NULL WHERE id = %s", (id_sai,))
            cur.execute(
                f"UPDATE produtos SET {coluna} = %s WHERE id = %s", (sai[coluna], id_fica)
            )
            movidos[coluna] = sai[coluna]
        elif sai[coluna] and fica[coluna] and coluna == "codigo_pdv":
            # ⚠️ **Dois códigos do PDV é caso REAL**, não erro: "ENTREGA" tem
            # quatro no cardápio do cliente. O que sai vira APELIDO, senão ele
            # voltaria a criar rascunho na importação seguinte.
            cur.execute("UPDATE produtos SET codigo_pdv = NULL WHERE id = %s", (id_sai,))
            vinculo.gravar(cur, id_fica, sai[coluna], sai["nome"], id_usuario)
            movidos["apelido_pdv"] = sai[coluna]

    # 🔑 **Dois códigos do Omie também é caso REAL, e o de sair virava LIXO.**
    # Aqui ficava um `movidos["codigo_omie_descartado"]` e mais nada — a mesma
    # situação do PDV, tratada de dois jeitos na mesma função. O efeito: a casa
    # juntava os cinco cadastros de ABACATE que o catálogo tinha criado (um por
    # fornecedor) e, na primeira nota que trouxesse o código de um absorvido, o
    # sistema não achava o principal — a cascata filtra `AND ativo` e o
    # absorvido está arquivado. O item caía na fila de pendentes e quem
    # clicasse em "criar produto" recriava o duplicado: o trabalho de juntar se
    # desfazia sozinho.
    # ⚠️ A coluna do absorvido é ZERADA junto: ela é única, e deixá-la lá
    # manteria o código preso a um cadastro arquivado.
    if sai["codigo_omie"] and fica["codigo_omie"]:
        cur.execute("UPDATE produtos SET codigo_omie = NULL WHERE id = %s", (id_sai,))
        vinculo_omie.gravar_apelido(cur, id_fica, sai["codigo_omie"], sai["nome"], id_usuario)
        movidos["apelido_omie"] = sai["codigo_omie"]

    # -------------------------------------- o que estiver em branco no que fica
    completados = []
    for coluna in _COMPLETAVEIS:
        if coluna in ("codigo_barras",):
            continue
        if not fica.get(coluna) and sai.get(coluna):
            cur.execute(
                f"UPDATE produtos SET {coluna} = %s WHERE id = %s", (sai[coluna], id_fica)
            )
            completados.append(coluna)

    # ----------------------------------------- apelidos e itens de venda mudam
    cur.execute(
        "UPDATE codigos_externos SET id_produto = %s WHERE id_produto = %s",
        (id_fica, id_sai),
    )
    movidos["apelidos"] = cur.rowcount

    # ⚠️ Os PONTEIROS mudam de dono: item de nota, vínculo de fornecedor,
    # embalagem, agenda de produção, linha de ficha, componente de combo. Nenhum
    # deles é história — são "esta linha é deste produto", e se os dois cadastros
    # são o mesmo produto, a linha passa para o que fica.
    reapontados: dict[str, int] = {}
    descartados: dict[str, int] = {}
    for tabela, coluna, chave in _REAPONTAVEIS:
        if chave:
            cur.execute(
                f"""DELETE FROM {tabela} sai
                     WHERE sai.{coluna} = %s
                       AND EXISTS (SELECT 1 FROM {tabela} fica
                                    WHERE fica.{coluna} = %s
                                      AND {chave.format(a='fica')} = {chave.format(a='sai')})""",
                (id_sai, id_fica),
            )
            if cur.rowcount:
                descartados[tabela] = descartados.get(tabela, 0) + cur.rowcount
        cur.execute(
            f"UPDATE {tabela} SET {coluna} = %s WHERE {coluna} = %s",
            (id_fica, id_sai),
        )
        if cur.rowcount:
            reapontados[tabela] = reapontados.get(tabela, 0) + cur.rowcount
    if reapontados:
        movidos["reapontados"] = reapontados
    if descartados:
        movidos["descartados_por_ja_existirem"] = descartados

    cur.execute(
        "SELECT id, custo_ficha_unitario FROM venda_itens WHERE id_produto = %s", (id_sai,)
    )
    itens = [dict(r) for r in cur.fetchall()]
    # ⚠️ A loja do custo é a do LOCAL onde a baixa vai acontecer — e, sem baixa,
    # a matriz. Este número é congelado no item de venda: calculado com o
    # estoque das duas lojas, o erro fica gravado no CMV daquele mês.
    _baixa = conferido.get("baixa") or {}
    id_unidade_custo = None
    if _baixa.get("id_local"):
        cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s",
                    (_baixa["id_local"],))
        id_unidade_custo = (cur.fetchone() or {}).get("id_unidade")
    if not id_unidade_custo:
        cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
        id_unidade_custo = (cur.fetchone() or {}).get("id")
    custo, origem_custo = motor.custo_teorico_do_produto(
        cur, id_fica, id_unidade=id_unidade_custo)
    recalculados = 0
    for item in itens:
        if item["custo_ficha_unitario"] is None:
            cur.execute(
                """UPDATE venda_itens
                      SET id_produto = %s, custo_ficha_unitario = %s, origem_custo = %s
                    WHERE id = %s""",
                (id_fica, custo, origem_custo, item["id"]),
            )
            recalculados += 1 if custo is not None else 0
        else:
            cur.execute(
                "UPDATE venda_itens SET id_produto = %s WHERE id = %s", (id_fica, item["id"])
            )

    # ---------------------------------- a baixa do que foi vendido e não saiu
    baixa = conferido.get("baixa")
    if baixar_vendas and baixa and baixa["quantidade"] > 0:
        from services import estoque as motor_estoque

        cur.execute("SELECT id_unidade FROM locais_estoque WHERE id = %s", (baixa["id_local"],))
        id_unidade = (cur.fetchone() or {}).get("id_unidade")
        cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id LIMIT 1")
        id_unidade = id_unidade or (cur.fetchone() or {}).get("id")
        motor_estoque.lancar(
            cur, id_unidade=id_unidade, id_local=baixa["id_local"], id_produto=id_fica,
            tipo="SAIDA_VENDA", quantidade=baixa["quantidade"],
            origem_tipo="VINCULO", origem_id=id_sai,
            documento=f"vinculo-{id_sai}", id_usuario=id_usuario,
            observacao=(f"Vendas de “{sai['nome']}” que nunca baixaram estoque — "
                        f"{baixa['quantidade']:g} {fica.get('um_estoque') or ''}".strip()),
        )
        movidos["baixa_de_estoque"] = baixa["quantidade"]
        movidos["saldo_depois"] = baixa["saldo_depois"]

    nota = (f"Fundido em {fica['codigo']} — {nome}. "
            "Era o mesmo produto com outro cadastro.")
    cur.execute(
        """UPDATE produtos
              SET ativo = false, status = 'ARQUIVADO',
                  observacao = trim(both E'\\n' from coalesce(observacao, '') || E'\\n' || %s)
            WHERE id = %s""",
        (nota, id_sai),
    )

    return {
        "invertido": conferido["invertido"],
        "fica": {"id": id_fica, "codigo": fica["codigo"], "nome": nome,
                 "nome_curto": nome_curto},
        "saiu": {"id": id_sai, "codigo": sai["codigo"], "nome": sai["nome"]},
        "completados": completados,
        "itens_de_venda": len(itens),
        "itens_que_ganharam_custo": recalculados,
        **movidos,
        "message": (f"“{sai['nome']}” foi fundido em “{nome}”"
                    + (f" — {len(itens)} item(ns) de venda mudaram de dono"
                       if itens else "")
                    + (f", {recalculados} ganharam custo" if recalculados else "")
                    + (f". {movidos['baixa_de_estoque']:g} unidade(s) vendida(s) baixaram do "
                       f"estoque agora — saldo {movidos['saldo_depois']:g}"
                       if movidos.get("baixa_de_estoque") else "")),
    }
