"""Inventário: contar o que existe e acertar o razão pela diferença.

A contagem não escreve no razão — só ao fechar. E o acerto entra como
movimento de ajuste, com o custo médio do momento: some estoque sem virar
perda anônima, mas com nome e rastro.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from paginacao import com_total
from models.estoque import (
    ContagemRequest,
    InventarioCreate,
    InventarioRenomear,
    InventarioResponse,
)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import custos
from services import estoque as motor
from services import inventario_selecao as selecao
from services.custos import dec

router = APIRouter(prefix="/inventarios", tags=["inventário"])

# Contar e montar a contagem são trabalhos diferentes, feitos por gente
# diferente: quem vai à prateleira precisa de uma coisa só — abrir a contagem
# que já existe e digitar o que viu.
_perm = requer_permissao("estoque.inventario")
_perm_criar = requer_permissao("estoque.inventario_criar")


def _pode_contar(cur, id_inventario: int, ctx: Contexto) -> bool:
    """Esta pessoa foi escalada para ESTA contagem?

    🔑 **Lista vazia quer dizer "qualquer um que tenha a permissão"** — é o
    comportamento de sempre, e é o que faz as contagens antigas continuarem
    valendo sem ninguém reconfigurar nada.
    ⚠️ Quem pode CRIAR passa por cima da escala: é quem monta a contagem, e
    ficar de fora da própria contagem seria uma trava sem propósito.
    """
    if "estoque.inventario_criar" in ctx.permissoes:
        return True
    cur.execute(
        "SELECT id_usuario FROM inventario_contadores WHERE id_inventario = %s",
        (id_inventario,),
    )
    escalados = {r["id_usuario"] for r in cur.fetchall()}
    return not escalados or ctx.id_usuario in escalados


def _exigir_contador(cur, id_inventario: int, ctx: Contexto) -> None:
    if not _pode_contar(cur, id_inventario, ctx):
        raise HTTPException(
            status_code=403,
            detail=("Esta contagem foi escalada para outras pessoas. "
                    "Quem a abriu escolhe quem conta."))


def _locais_por_produto(cur, id_inventario: int) -> dict[int, list[int]]:
    """Em que locais cada produto aparece nesta contagem."""
    cur.execute(
        "SELECT id_produto, id_local FROM inventario_itens WHERE id_inventario = %s",
        (id_inventario,),
    )
    mapa: dict[int, list[int]] = {}
    for r in cur.fetchall():
        mapa.setdefault(r["id_produto"], []).append(r["id_local"])
    return mapa


def _local_do_item(item, mapa: dict[int, list[int]], local_do_cabecalho: int | None) -> int:
    """Onde gravar a contagem deste produto.

    ⚠️ **Ambiguidade é recusa, não escolha.** Com o produto em dois locais da
    mesma contagem, adivinhar gravaria na prateleira errada — e o erro só
    apareceria no fechamento, como ajuste em duas pontas: falta num lugar, sobra
    no outro. Nada na tela denunciaria.
    """
    if item.id_local:
        return item.id_local
    locais = mapa.get(item.id_produto) or []
    if len(locais) == 1:
        return locais[0]
    if not locais and local_do_cabecalho:
        return local_do_cabecalho
    if not locais:
        raise HTTPException(
            status_code=400,
            detail=(f"Produto {item.id_produto} não está nesta contagem. "
                    "Informe o local para incluí-lo."),
        )
    raise HTTPException(
        status_code=400,
        detail=(f"O produto {item.id_produto} está em {len(locais)} locais desta contagem. "
                "Informe em qual deles a quantidade foi contada."),
    )


def _rotulo_do_recorte(inv: dict) -> str:
    """Como a contagem se chama quando não é de um local só.

    Prefere o nome que a pessoa deu; sem ele, descreve o recorte. "Contagem"
    sozinho não distingue duas na mesma lista.
    """
    if inv.get("nome"):
        return inv["nome"]
    partes = []
    if inv.get("filtro_setores"):
        partes.append("setores escolhidos")
    if inv.get("filtro_categorias"):
        partes.append("categorias escolhidas")
    if inv.get("filtro_tipos"):
        partes.append(", ".join(t.lower().replace("_", " ") for t in inv["filtro_tipos"]))
    if not partes:
        return "todos os locais"
    return "todos os locais · " + " · ".join(partes)


def _descrever(cur, inv: dict) -> dict:
    """Traduz os filtros gravados em nomes — a tela não remonta isso sozinha.

    ⚠️ Quem abre uma contagem de três meses atrás vê 40 produtos e precisa saber
    por que aqueles 40. Guardar só os ids e deixar o front resolver exigiria que
    ele carregasse setores e categorias inativos, ou apagados — e aí a explicação
    some justamente na contagem velha, que é a que ninguém lembra.
    """
    def nomes(tabela, ids):
        if not ids:
            return []
        cur.execute(f"SELECT nome FROM {tabela} WHERE id = ANY(%s) ORDER BY lower(nome)", (ids,))
        return [r["nome"] for r in cur.fetchall()]

    return {
        "locais": nomes("locais_estoque", inv.get("filtro_locais")),
        "setores": nomes("setores", inv.get("filtro_setores")),
        "categorias": nomes("categorias", inv.get("filtro_categorias")),
        "tipos": list(inv.get("filtro_tipos") or []),
    }


def _montar(cur, id_inventario: int) -> dict:
    cur.execute(
        """SELECT i.*, l.nome AS local_unico FROM inventarios i
             LEFT JOIN locais_estoque l ON l.id = i.id_local
            WHERE i.id = %s""",
        (id_inventario,),
    )
    inv = cur.fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    inv = dict(inv)
    inv["filtros"] = _descrever(cur, inv)
    # ⚠️ Sem local único, o campo `local` traz o recorte por extenso em vez de
    # ficar vazio: é o que aparece no cabeçalho da contagem e na lista, e uma
    # linha sem nada ali não diz o que se está contando.
    inv["local"] = inv.pop("local_unico", None) or _rotulo_do_recorte(inv)

    # Quem foi escalado. Lista vazia = qualquer um com a permissão de contar, e
    # a tela precisa dizer isso em vez de mostrar um espaço em branco.
    cur.execute(
        """SELECT c.id_usuario, u.nome FROM inventario_contadores c
             JOIN usuarios u ON u.id = c.id_usuario
            WHERE c.id_inventario = %s ORDER BY u.nome""",
        (id_inventario,),
    )
    inv["contadores"] = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """SELECT ii.id, ii.id_produto, p.codigo, p.nome AS produto, p.um_estoque,
                  ii.qtd_sistema, ii.qtd_contada, ii.custo_medio, ii.observacao,
                  ii.qtd_informada, ii.um_informada, ii.contado_em, u.nome AS contado_por,
                  c.nome AS categoria, se.nome AS setor, p.tipo,
                  ii.id_local, l.nome AS local,
                  (coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema) AS diferenca,
                  -- Em que unidades este produto pode ser contado. Vai junto
                  -- para o celular não precisar de uma chamada por produto.
                  coalesce((SELECT json_agg(json_build_object('um', pu.um, 'fator', pu.fator)
                                              ORDER BY pu.fator)
                              FROM produto_unidades pu
                             WHERE pu.id_produto = p.id), '[]'::json) AS unidades
             FROM inventario_itens ii
             JOIN produtos p ON p.id = ii.id_produto
             LEFT JOIN usuarios u ON u.id = ii.contado_por
             LEFT JOIN categorias c ON c.id = p.id_categoria
             LEFT JOIN setores se ON se.id = p.id_setor
             LEFT JOIN locais_estoque l ON l.id = ii.id_local
            WHERE ii.id_inventario = %s
            ORDER BY lower(l.nome), lower(p.nome)""",
        (id_inventario,),
    )
    itens = [dict(r) for r in cur.fetchall()]

    inv["itens"] = itens
    inv["total_itens"] = len(itens)
    inv["contados"] = sum(1 for i in itens if i["qtd_contada"] is not None)
    inv["diferenca_valor"] = float(
        sum(dec(i["diferenca"]) * dec(i["custo_medio"]) for i in itens)
    )

    # Contagem CEGA: enquanto está aberta, o esperado não sai do servidor.
    # Esconder só na tela não é esconder — o número estaria no JSON, na aba de
    # rede do navegador e na folha impressa. E o objetivo é justamente que quem
    # conta não saiba o que "deveria" dar.
    if inv.get("cega") and inv["status"] == "ABERTO":
        for i in itens:
            i["qtd_sistema"] = None
            i["diferenca"] = None
            i["custo_medio"] = None
        inv["diferenca_valor"] = None
    return inv


@router.get("", response_model=list[InventarioResponse])
def listar(limite: int = Query(default=100, ge=1, le=500),
           offset: int = Query(default=0, ge=0),
           resposta: Response = None,
           ctx: Contexto = Depends(_perm)) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        # 🔑 **Quem só CONTA vê só o que pode contar.** Mostrar a lista inteira
        # para o conferente seria oferecer contagens que ele abre e não consegue
        # preencher — o 403 chegaria no primeiro número digitado, depois de ele
        # ter andado até a prateleira. Escala vazia continua valendo para todos.
        so_as_minhas = "estoque.inventario_criar" not in ctx.permissoes
        cur.execute(
            """SELECT i.id, i.nome, i.id_local, l.nome AS local_unico, i.data, i.status,
                      i.observacao, i.criado_em, i.fechado_em, i.cega,
                      i.filtro_locais, i.filtro_setores, i.filtro_categorias, i.filtro_tipos,
                      (SELECT count(*) FROM inventario_itens ii WHERE ii.id_inventario = i.id) AS total_itens,
                      (SELECT count(*) FROM inventario_itens ii
                        WHERE ii.id_inventario = i.id AND ii.qtd_contada IS NOT NULL) AS contados,
                      count(*) OVER () AS _total
                 FROM inventarios i
                 LEFT JOIN locais_estoque l ON l.id = i.id_local
                -- ⚠️ A listagem não filtrava por loja: com duas, a contagem de
                -- uma aparecia na tela da outra. Mesma correção que a de vendas
                -- já tinha precisado.
                WHERE i.id_unidade = %(u)s
                  AND (NOT %(so_minhas)s OR NOT EXISTS (
                        SELECT 1 FROM inventario_contadores c
                         WHERE c.id_inventario = i.id)
                       OR EXISTS (
                        SELECT 1 FROM inventario_contadores c
                         WHERE c.id_inventario = i.id AND c.id_usuario = %(eu)s))
                ORDER BY i.data DESC, i.id DESC
                LIMIT %(limite)s OFFSET %(offset)s""",
            {"u": id_unidade, "so_minhas": so_as_minhas, "eu": ctx.id_usuario,
             "limite": limite, "offset": offset},
        )
        linhas = []
        for r in cur.fetchall():
            d = dict(r)
            # ⚠️ `LEFT JOIN`: contagem de vários locais não tem local único, e
            # o `JOIN` de antes a faria sumir da lista sem erro nenhum.
            d["local"] = d.pop("local_unico", None) or _rotulo_do_recorte(d)
            linhas.append(d)
    return com_total(linhas, resposta, offset)


@router.get("/previa")
def previa(
    locais: list[int] = Query(default=[]),
    setores: list[int] = Query(default=[]),
    categorias: list[int] = Query(default=[]),
    tipos: list[str] = Query(default=[]),
    ctx: Contexto = Depends(_perm_criar),
) -> dict:
    """Quantos itens este recorte traria — antes de abrir a contagem.

    ⚠️ Existe para ninguém abrir uma contagem de 2.000 linhas sem querer. Numa
    base real o filtro em branco traz o cadastro inteiro, e descobrir isso
    depois de abrir custa cancelar e recomeçar. Também avisa do choque com
    contagem aberta aqui, e não no meio do POST.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        pares = selecao.selecionar(cur, id_unidade, {
            "locais": locais, "setores": setores,
            "categorias": categorias, "tipos": tipos,
        })
        resumo = selecao.resumo(pares)
        choques = selecao.em_contagem_aberta(cur, pares)
    resumo["ja_em_contagem"] = [
        {"produto": c["produto"], "local": c["local"], "inventario": c["id_inventario"]}
        for c in choques[:10]
    ]
    resumo["ja_em_contagem_total"] = len(choques)
    return resumo


@router.get("/{id_inventario}", response_model=InventarioResponse)
def obter(id_inventario: int, ctx: Contexto = Depends(_perm)) -> dict:
    with get_cursor() as cur:
        return _montar(cur, id_inventario)


@router.post("", status_code=201)
def abrir(body: InventarioCreate, ctx: Contexto = Depends(_perm_criar)) -> dict:
    """Abre a contagem congelando o saldo de cada par produto × local, agora.

    Os quatro filtros combinam com E, e vazio quer dizer "todos". `id_local`
    continua aceito e vale como `locais = [ele]`: contar um lugar só é o caso
    comum, e nada do que já chamava esta API mudou.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)

        locais = list(body.locais)
        if body.id_local and body.id_local not in locais:
            locais.append(body.id_local)
        if locais:
            cur.execute(
                "SELECT id FROM locais_estoque WHERE id = ANY(%s) AND ativo", (locais,)
            )
            achados = {r["id"] for r in cur.fetchall()}
            faltando = [l for l in locais if l not in achados]
            if faltando:
                raise HTTPException(
                    status_code=404,
                    detail=f"Local não encontrado: {', '.join(map(str, faltando))}",
                )

        filtros = {"locais": locais, "setores": body.setores,
                   "categorias": body.categorias, "tipos": body.tipos,
                   "produtos": body.produtos}
        pares = selecao.selecionar(cur, id_unidade, filtros)
        if not pares:
            raise HTTPException(
                status_code=400,
                detail=("Nenhum produto neste recorte. Confira os filtros — só entra o que "
                        "tem saldo ou já se moveu nos locais escolhidos."),
            )

        # ⚠️ **A guarda deixou de ser "um inventário aberto por local".** Com o
        # recorte, contar as bebidas e contar o hortifrúti do mesmo local ao
        # mesmo tempo é legítimo e não se atravessa. O que não pode é o MESMO
        # produto no MESMO local estar em duas contagens: as duas congelaram o
        # saldo, as duas lançariam ajuste, e a segunda desfaria a primeira.
        choques = selecao.em_contagem_aberta(cur, pares)
        if choques:
            quais = "; ".join(
                f"{c['produto']} em {c['local']} (contagem #{c['id_inventario']})"
                for c in choques[:3]
            )
            resto = f" e mais {len(choques) - 3}" if len(choques) > 3 else ""
            raise HTTPException(
                status_code=409,
                detail=(f"Já há contagem aberta com estes itens: {quais}{resto}. "
                        "Feche ou cancele a outra, ou estreite o filtro."),
            )

        # O local do cabeçalho só existe quando é UM: é o atalho de que o resto
        # do sistema depende, e mentir aqui faria o fechamento lançar tudo no
        # mesmo lugar.
        distintos = {p["id_local"] for p in pares}
        local_unico = distintos.pop() if len(distintos) == 1 else None

        cur.execute(
            """INSERT INTO inventarios (id_unidade, id_local, data, nome, observacao,
                                        id_usuario, cega, filtro_locais, filtro_setores,
                                        filtro_categorias, filtro_tipos)
               VALUES (%s, %s, coalesce(%s, current_date), %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (id_unidade, local_unico, body.data, (body.nome or "").strip() or None,
             body.observacao, ctx.id_usuario, body.cega,
             locais or None, body.setores or None,
             body.categorias or None, body.tipos or None),
        )
        novo = cur.fetchone()["id"]

        for par in pares:
            cur.execute(
                """INSERT INTO inventario_itens
                       (id_inventario, id_produto, id_local, qtd_sistema, custo_medio)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (id_inventario, id_produto, id_local) DO NOTHING""",
                (novo, par["id_produto"], par["id_local"], par["quantidade"],
                 par["custo_medio"]),
            )

        # ⚠️ **Só quem existe e está ativo.** Escalar alguém desligado deixaria a
        # contagem com um dono que não entra no sistema — e a lista vazia, que
        # quer dizer "qualquer um", é o oposto do que se pediu.
        if body.contadores:
            cur.execute("SELECT id FROM usuarios WHERE id = ANY(%s) AND ativo",
                        (list(set(body.contadores)),))
            validos = [r["id"] for r in cur.fetchall()]
            if not validos:
                raise HTTPException(
                    400, "Nenhum dos usuários escolhidos para contar está ativo.")
            for id_u in validos:
                cur.execute(
                    """INSERT INTO inventario_contadores (id_inventario, id_usuario)
                       VALUES (%s, %s) ON CONFLICT DO NOTHING""", (novo, id_u))

        auditoria.registrar(cur, ctx.id_usuario, "inventario", novo, "abrir",
                            depois={"nome": body.nome, "itens": len(pares),
                                    "locais": locais, "setores": body.setores,
                                    "categorias": body.categorias, "tipos": body.tipos,
                                    "contadores": body.contadores})
        return _montar(cur, novo)


@router.put("/{id_inventario}/nome")
def renomear(id_inventario: int, body: InventarioRenomear,
             ctx: Contexto = Depends(_perm_criar)) -> dict:
    """Troca o nome da contagem. É rótulo: não mexe em item nem em razão.

    Vale também depois de fechada — quem quer achar "a contagem do Natal" seis
    meses depois não deveria depender de ter acertado o nome na abertura.
    """
    with get_cursor() as cur:
        cur.execute("SELECT nome FROM inventarios WHERE id = %s", (id_inventario,))
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        cur.execute("UPDATE inventarios SET nome = %s WHERE id = %s",
                    (body.nome.strip(), id_inventario))
        auditoria.registrar(cur, ctx.id_usuario, "inventario", id_inventario, "renomear",
                            antes={"nome": antes["nome"]}, depois={"nome": body.nome})
    return {"message": "Nome atualizado"}


@router.put("/{id_inventario}/contagem")
def contar(id_inventario: int, body: ContagemRequest, ctx: Contexto = Depends(_perm)) -> dict:
    """Grava a contagem. Ainda não mexe no razão — isso é no fechamento."""
    with get_cursor() as cur:
        _exigir_contador(cur, id_inventario, ctx)
        cur.execute("SELECT status, id_local FROM inventarios WHERE id = %s", (id_inventario,))
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] != "ABERTO":
            raise HTTPException(status_code=400, detail="Inventário já fechado.")

        ums = custos._carregar_ums(cur)
        locais_do_item = _locais_por_produto(cur, id_inventario)
        for item in body.itens:
            # A pessoa conta na embalagem que está na mão; o sistema guarda na
            # unidade de estoque. A conversão é a MESMA da ficha e da nota.
            convertida, informada, um_informada = item.qtd_contada, None, None
            if item.qtd_contada is not None and item.um:
                cur.execute("SELECT um_estoque, nome FROM produtos WHERE id = %s",
                            (item.id_produto,))
                p = cur.fetchone()
                if not p:
                    raise HTTPException(status_code=404,
                                        detail=f"Produto {item.id_produto} não encontrado")
                convertida, _como = custos.converter_para_estoque(
                    cur, dec(item.qtd_contada), item.id_produto, item.um, p["um_estoque"], ums)
                if convertida is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(f"{p['nome']}: {item.um} não converte para "
                                f"{p['um_estoque'] or '?'}. Cadastre esta unidade de compra "
                                f"no produto."),
                    )
                informada, um_informada = item.qtd_contada, item.um.upper()

            # ⚠️ **De que prateleira é este número?** Com o recorte, o mesmo
            # café pode estar na câmara e no seco: são duas linhas, e gravar na
            # errada esconderia a diferença de uma e inventaria a da outra. O
            # local vem do pedido quando a tela o manda; se não vier e o produto
            # tiver uma linha só, é aquela; com duas, o servidor recusa em vez
            # de escolher.
            id_local = _local_do_item(item, locais_do_item, inv["id_local"])

            cur.execute(
                """INSERT INTO inventario_itens (id_inventario, id_produto, id_local,
                                                 qtd_sistema, custo_medio, qtd_contada,
                                                 qtd_informada, um_informada, observacao,
                                                 contado_em, contado_por)
                   SELECT %s, %s, %s, coalesce(s.quantidade, 0), coalesce(s.custo_medio, 0),
                          %s, %s, %s, %s, now(), %s
                     FROM (SELECT 1) x
                     LEFT JOIN estoque_saldos s
                            ON s.id_produto = %s AND s.id_local = %s
                   ON CONFLICT (id_inventario, id_produto, id_local) DO UPDATE
                       SET qtd_contada = EXCLUDED.qtd_contada,
                           qtd_informada = EXCLUDED.qtd_informada,
                           um_informada = EXCLUDED.um_informada,
                           observacao = EXCLUDED.observacao,
                           contado_em = now(),
                           contado_por = EXCLUDED.contado_por""",
                (id_inventario, item.id_produto, id_local, convertida, informada,
                 um_informada, item.observacao, ctx.id_usuario, item.id_produto, id_local),
            )
        return _montar(cur, id_inventario)


@router.post("/{id_inventario}/fechar")
def fechar(id_inventario: int, ctx: Contexto = Depends(requer_permissao("estoque.ajuste"))) -> dict:
    """Fecha e acerta o razão: cada diferença vira um movimento de ajuste."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id_unidade, id_local, status FROM inventarios WHERE id = %s",
            (id_inventario,),
        )
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] != "ABERTO":
            raise HTTPException(status_code=400, detail="Inventário já fechado.")

        # ⚠️ O local vem do ITEM, não do cabeçalho: numa contagem de vários
        # locais o cabeçalho não tem um, e lançar tudo no mesmo lugar sumiria
        # com o estoque de todos os outros.
        cur.execute(
            """SELECT id_produto, id_local, qtd_sistema, qtd_contada FROM inventario_itens
                WHERE id_inventario = %s AND qtd_contada IS NOT NULL""",
            (id_inventario,),
        )
        itens = [dict(r) for r in cur.fetchall()]
        if not itens:
            raise HTTPException(status_code=400, detail="Nenhum item contado.")

        ajustes, valor = 0, 0.0
        for item in itens:
            # O saldo do sistema pode ter mudado depois da abertura: o ajuste
            # olha o saldo de AGORA, senão o inventário desfaz movimento válido.
            cur.execute(
                """SELECT quantidade FROM estoque_saldos
                    WHERE id_unidade = %s AND id_local = %s AND id_produto = %s""",
                (inv["id_unidade"], item["id_local"] or inv["id_local"], item["id_produto"]),
            )
            linha = cur.fetchone()
            atual = dec(linha["quantidade"]) if linha else dec(0)
            diferenca = dec(item["qtd_contada"]) - atual
            if diferenca == 0:
                continue
            r = motor.lancar(
                cur, id_unidade=inv["id_unidade"],
                id_local=item["id_local"] or inv["id_local"],
                id_produto=item["id_produto"],
                tipo="AJUSTE_INVENTARIO_ENTRADA" if diferenca > 0 else "AJUSTE_INVENTARIO_SAIDA",
                quantidade=abs(diferenca), origem_tipo="INVENTARIO", origem_id=id_inventario,
                observacao=f"Inventário #{id_inventario}", id_usuario=ctx.id_usuario,
            )
            ajustes += 1
            valor += float(r["custo_total"]) * (1 if diferenca > 0 else -1)

        cur.execute(
            """UPDATE inventarios SET status = 'FECHADO', fechado_em = now(), fechado_por = %s
                WHERE id = %s""",
            (ctx.id_usuario, id_inventario),
        )
        auditoria.registrar(cur, ctx.id_usuario, "inventario", id_inventario, "fechar",
                            depois={"ajustes": ajustes, "valor": round(valor, 2)})
    return {"message": f"Inventário fechado com {ajustes} ajuste(s)",
            "ajustes": ajustes, "diferenca_valor": round(valor, 2)}


@router.delete("/{id_inventario}")
def cancelar(id_inventario: int, ctx: Contexto = Depends(_perm_criar)) -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT status FROM inventarios WHERE id = %s", (id_inventario,))
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        if inv["status"] == "FECHADO":
            raise HTTPException(
                status_code=400,
                detail="Inventário fechado não se cancela — os ajustes já estão no razão.",
            )
        cur.execute("UPDATE inventarios SET status = 'CANCELADO' WHERE id = %s", (id_inventario,))
        auditoria.registrar(cur, ctx.id_usuario, "inventario", id_inventario, "cancelar")
    return {"message": "Inventário cancelado"}
