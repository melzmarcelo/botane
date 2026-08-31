"""Produtos — o cadastro central.

Leitura só exige autenticação: a cozinha consulta produto sem poder editar.
Escrita exige `cadastros.produtos`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import auditoria
from database import get_cursor
from models.produtos import (
    PrecoDaLoja,
    KitRequest,
    UnidadesCompraRequest,
    ContagemProdutos,
    ProdutoCreate,
    ProdutoResponse,
    ProdutoResumo,
    ProdutoUpdate,
    STATUS,
    TIPOS,
    VincularRequest,
)
from paginacao import pagina
from seguranca import Contexto, contexto_atual, requer_permissao, unidade_atual
from services import kits, precos, produtos_vinculo

router = APIRouter(prefix="/produtos", tags=["produtos"])

_EDITAVEIS = (
    "codigo", "nome", "nome_curto", "tipo", "id_categoria", "id_setor",
    "producao_propria", "controla_estoque", "um_estoque", "um_compra", "fator_compra",
    "id_local_padrao", "modo_producao",
    "perecivel", "validade_dias", "controla_lote", "controla_validade",
    "estoque_minimo", "estoque_maximo", "ncm", "codigo_barras", "codigo_omie",
    "codigo_pdv",
    # ⚠️ Quem já tem `codigo_pdv` nasce marcado, e quem GANHA o código depois
    # também — quem garante isso é o gatilho da 040, não esta lista. Aqui ele é
    # editável porque a marca é uma DECISÃO: um prato novo pode ser marcado
    # antes de existir no PDV (é o que o põe na fila de criação), e um produto
    # que veio de lá pode ser desmarcado para o Botané não mexer nele.
    "integrado_pdv",
    # Vêm do cadastro do Omie e são COMPLETADOS na sincronização — mas
    # continuam editáveis: quem corrige aqui é porque o dado de lá está errado,
    # e a completagem só preenche o que está em branco.
    "cest", "marca", "peso_liquido", "peso_bruto",
    "observacao", "status", "ativo",
)


# ⚠️ As três colunas com índice único além do `codigo`. Deixar a constraint
# estourar devolve "Internal Server Error" para quem só digitou um código que já
# é de outro produto — mesma família do nome repetido em tabela de apoio, que já
# custou um chamado. Ver `_recusar_codigo_de_outro`.
_UNICOS = (
    ("codigo_omie", "o código do Omie"),
    ("codigo_pdv", "o código do PDV"),
    ("codigo_barras", "o código de barras"),
)


def _recusar_codigo_de_outro(cur, dados: dict, id_produto: int | None = None) -> None:
    """Código único que já é de outro cadastro vira 409 com frase, não 500.

    ⚠️ E a frase **nomeia o dono** — porque a ação seguinte quase sempre é abrir
    aquele produto e usar o botão Vincular: dois cadastros disputando o mesmo
    identificador externo costumam ser o mesmo produto.
    """
    for coluna, rotulo in _UNICOS:
        valor = (dados.get(coluna) or "").strip() if isinstance(dados.get(coluna), str) \
            else dados.get(coluna)
        if not valor:
            continue
        cur.execute(
            f"SELECT id, codigo, nome FROM produtos WHERE {coluna} = %s AND id <> %s",
            (str(valor), id_produto or 0),
        )
        dono = cur.fetchone()
        if dono:
            raise HTTPException(
                status_code=409,
                detail=(f"{rotulo} {valor} já é de “{dono['nome']}” ({dono['codigo']}). "
                        "Se for o mesmo produto, abra aquele cadastro e use Vincular."),
            )


def _proximo_codigo(cur) -> str:
    cur.execute("SELECT nextval('seq_codigo_produto') AS n")
    return f"P{cur.fetchone()['n']:04d}"


MODOS_PRODUCAO = ("PARA_ESTOQUE", "NA_HORA")


def _valida_basico(dados: dict) -> None:
    if dados.get("tipo") and dados["tipo"] not in TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {', '.join(TIPOS)}")
    if dados.get("status") and dados["status"] not in STATUS:
        raise HTTPException(status_code=400, detail=f"Status inválido. Use: {', '.join(STATUS)}")
    if dados.get("modo_producao") and dados["modo_producao"] not in MODOS_PRODUCAO:
        raise HTTPException(
            status_code=400,
            detail=f"Modo de produção inválido. Use: {', '.join(MODOS_PRODUCAO)}",
        )
    if dados.get("modo_producao") == "NA_HORA" and dados.get("producao_propria") is False:
        raise HTTPException(
            status_code=400,
            detail="Produzido na hora precisa ser de produção própria — é a ficha que baixa.",
        )
    if dados.get("producao_propria") and dados.get("tipo") not in (None, "PRODUZIDO", "KIT"):
        raise HTTPException(
            status_code=400,
            detail="Produção própria só vale para produto produzido ou kit.",
        )
    # ⚠️ **A trava do banco (`ck_produto_rascunho`) vazava como 500.** Produto
    # ATIVO precisa de unidade de estoque — é ela que decide o custo por
    # unidade, e sem ela ficha, CMV e compra herdam um número sem significado.
    # A regra é certa; o que estava errado era a mensagem: quem cadastrava um
    # prato sem escolher unidade recebia "Internal Server Error" e não tinha
    # como adivinhar. Mesma família do nome repetido em tabela de apoio.
    if (dados.get("status") or "ATIVO") == "ATIVO" and not dados.get("um_estoque"):
        raise HTTPException(
            status_code=400,
            detail=("Produto ativo precisa de unidade de estoque — é ela que dá sentido à "
                    "quantidade. Escolha uma, ou salve como rascunho para conferir depois."),
        )


def _gravar_preco(cur, id_produto: int, preco: float | None, id_usuario: int) -> None:
    """Fecha o preço vigente e abre outro. O histórico é o que sustenta a margem.

    ⚠️ **O formulário do produto grava o preço da CASA**, não o da loja atual —
    de propósito. Numa casa de uma loja só não existe distinção, e fazer o
    formulário gravar por loja faria o preço "da casa" nunca ser definido: cada
    filial teria o seu e nenhuma herdaria nada. O preço de uma loja específica
    se define no bloco próprio da tela do produto.
    """
    from services import precos

    precos.gravar(cur, id_produto, preco, id_usuario, None)

def _gravar_fornecedores(cur, id_produto: int, lista) -> None:
    """Só sai da tabela quem saiu da lista.

    Apagar tudo e reinserir levava junto o que a tela não manda: `ultima_compra`
    (e o `ultimo_preco`, quando a linha é nova) são escritos pelo LANÇAMENTO da
    nota, não pelo formulário. Salvar o produto zerava o preço de compra e, com
    ele, o custo de reserva de toda ficha do insumo sem entrada no estoque.
    """
    ids = [f.id_fornecedor for f in lista]
    if ids:
        cur.execute(
            "DELETE FROM produto_fornecedor WHERE id_produto = %s AND id_fornecedor <> ALL(%s)",
            (id_produto, ids),
        )
    else:
        cur.execute("DELETE FROM produto_fornecedor WHERE id_produto = %s", (id_produto,))
    for f in lista:
        cur.execute(
            """INSERT INTO produto_fornecedor
                   (id_produto, id_fornecedor, codigo_no_fornecedor, embalagem, fator,
                    ultimo_preco, preferencial)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_produto, id_fornecedor) DO UPDATE
                   SET codigo_no_fornecedor = EXCLUDED.codigo_no_fornecedor,
                       embalagem = EXCLUDED.embalagem,
                       fator = EXCLUDED.fator,
                       ultimo_preco = coalesce(EXCLUDED.ultimo_preco,
                                               produto_fornecedor.ultimo_preco),
                       preferencial = EXCLUDED.preferencial""",
            (id_produto, f.id_fornecedor, f.codigo_no_fornecedor, f.embalagem,
             f.fator, f.ultimo_preco, f.preferencial),
        )


@router.get("", response_model=list[ProdutoResumo])
def listar(
    busca: str | None = Query(default=None, max_length=80),
    tipo: str | None = None,
    id_categoria: int | None = None,
    id_setor: int | None = None,
    status: str | None = None,
    # ⚠️ Filtro do SERVIDOR porque a lista de fichas é paginada: comparar os
    # produzidos com "as fichas que vieram nesta página" apontaria como sem
    # ficha todo produto cuja ficha ficou na página seguinte.
    sem_ficha: bool = False,
    incluir_inativos: bool = False,
    limite: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    resposta: Response = None,
    ctx: Contexto = Depends(contexto_atual),
) -> list[dict]:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        linhas = pagina(
            cur,
            """
            SELECT p.id, p.codigo, p.nome, p.tipo, c.nome AS categoria, s.nome AS setor,
                   p.um_estoque, p.producao_propria, p.controla_estoque, p.controla_lote,
                   p.status, p.ativo,
                   -- ⚠️ Nem filtrava por loja: com um preço da casa e um da
                   -- loja, escolhia o de `vigente_de` mais recente, que é
                   -- arbitrário. A regra mora em `services/precos.py`.
                   (SELECT pp.preco_venda FROM produto_precos pp
                     WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                       AND (pp.id_unidade = %s OR pp.id_unidade IS NULL)
                     ORDER BY pp.id_unidade NULLS LAST LIMIT 1) AS preco_venda
              FROM produtos p
              LEFT JOIN categorias c ON c.id = p.id_categoria
              LEFT JOIN setores s ON s.id = p.id_setor
             WHERE (%s OR p.ativo)
               AND (%s::varchar IS NULL OR p.tipo = %s)
               AND (%s::int IS NULL OR p.id_categoria = %s)
               AND (%s::int IS NULL OR p.id_setor = %s)
               AND (%s::varchar IS NULL OR p.status = %s)
               AND (NOT %s OR NOT EXISTS
                    (SELECT 1 FROM fichas_tecnicas f WHERE f.id_produto = p.id))
               AND (%s::varchar IS NULL
                    OR lower(p.nome) LIKE lower('%%' || %s || '%%')
                    OR lower(p.codigo) LIKE lower('%%' || %s || '%%')
                    OR coalesce(p.codigo_barras, '') LIKE '%%' || %s || '%%')
             ORDER BY p.ativo DESC, lower(p.nome)
            """,
            # ⚠️ A loja vai PRIMEIRO: o `%s` dela está na lista do SELECT, que
            # vem antes do WHERE. Parâmetro posicional é assim — a ordem do SQL
            # é a ordem da tupla.
            (id_unidade,
             incluir_inativos, tipo, tipo, id_categoria, id_categoria, id_setor, id_setor,
             status, status, sem_ficha, busca, busca, busca, busca),
            limite=limite, offset=offset, resposta=resposta,
        )
    return linhas


@router.get("/contagem", response_model=ContagemProdutos)
def contagem(ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT tipo, count(*) FILTER (WHERE ativo) AS n,
                      count(*) FILTER (WHERE NOT ativo) AS inativos,
                      count(*) FILTER (WHERE status = 'RASCUNHO' AND ativo) AS rascunhos
                 FROM produtos GROUP BY tipo"""
        )
        linhas = cur.fetchall()
    return {
        "total": sum(l["n"] for l in linhas),
        "por_tipo": {l["tipo"]: l["n"] for l in linhas},
        "rascunhos": sum(l["rascunhos"] for l in linhas),
        "inativos": sum(l["inativos"] for l in linhas),
    }


@router.get("/{id_produto}/vincular/previa")
def previa_do_vinculo(id_produto: int, id_sai: int,
                      ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """O que a fusão faria — antes de mandar fazer.

    ⚠️ Existe porque fusão não tem desfazer. Quem confirma precisa ver com que
    nome o produto vai ficar, quais campos serão completados, quantos itens de
    venda mudam de dono, e — quando não dá — o que exatamente trava.
    """
    with get_cursor() as cur:
        try:
            return produtos_vinculo.previa(cur, id_produto, id_sai)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/{id_produto}/vincular")
def vincular(id_produto: int, body: VincularRequest,
             ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Diz que dois cadastros são o mesmo produto. `id_produto` é o que FICA.

    ⚠️ **Nada aqui adivinha.** Quem reconhece o produto é quem está olhando a
    tela; o sistema guarda o que ela disse. A descrição longa fica com o nome do
    lado do Omie e a curta com o do PDV, os códigos das duas integrações migram
    para o mesmo cadastro, e o que sai é **inativado** — nunca apagado, porque a
    auditoria e o histórico continuam apontando para ele.
    """
    with get_cursor() as cur:
        try:
            r = produtos_vinculo.fundir(cur, id_produto, body.id_sai, ctx.id_usuario,
                                        body.baixar_vendas)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "vincular",
                            depois={k: v for k, v in r.items() if k != "message"})
    return r


@router.get("/{id_produto}", response_model=ProdutoResponse)
def obter(id_produto: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT p.*, c.nome AS categoria, s.nome AS setor, l.nome AS local_padrao
                 FROM produtos p
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                 LEFT JOIN locais_estoque l ON l.id = p.id_local_padrao
                WHERE p.id = %s""",
            (id_produto,),
        )
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        produto = dict(p)

        # 🔑 Os DOIS lado a lado: o da casa e o desta loja. A tela precisa
        # dizer de quem é o número que está mostrando — "R$ 12,00" sem dono não
        # responde se a filial cobra isso ou se herdou da matriz.
        cur.execute(
            """SELECT id_unidade, preco_venda, vigente_de FROM produto_precos
                WHERE id_produto = %(p)s AND vigente_ate IS NULL
                  AND (id_unidade = %(u)s OR id_unidade IS NULL)""",
            {"p": id_produto, "u": id_unidade},
        )
        # ⚠️ Não chamar de `precos`: o módulo `services.precos` está importado
        # neste arquivo, e a variável local o sombrearia dentro da função.
        vigentes = {r["id_unidade"]: r for r in cur.fetchall()}
        da_casa, da_loja = vigentes.get(None), vigentes.get(id_unidade)
        vale = da_loja or da_casa
        produto["preco_venda"] = vale["preco_venda"] if vale else None
        produto["preco_desde"] = vale["vigente_de"] if vale else None
        produto["preco_casa"] = da_casa["preco_venda"] if da_casa else None
        produto["preco_loja"] = da_loja["preco_venda"] if da_loja else None

        # ⚠️ Os códigos EXTRAS do cardápio. "ENTREGA" tem quatro na conta real;
        # o campo `codigo_pdv` guarda o principal e estes são os apelidos — sem
        # eles, a tela diria que o produto tem um vínculo quando tem quatro.
        cur.execute(
            """SELECT codigo FROM codigos_externos
                WHERE sistema = 'PDV_LEGAL' AND id_produto = %s ORDER BY codigo""",
            (id_produto,),
        )
        produto["apelidos_pdv"] = [r["codigo"] for r in cur.fetchall()]

        cur.execute(
            """SELECT pf.id_fornecedor, f.nome AS fornecedor, pf.codigo_no_fornecedor,
                      pf.embalagem, pf.fator, pf.ultimo_preco, pf.ultima_compra, pf.preferencial
                 FROM produto_fornecedor pf
                 JOIN fornecedores f ON f.id = pf.id_fornecedor
                WHERE pf.id_produto = %s
                ORDER BY pf.preferencial DESC, lower(f.nome)""",
            (id_produto,),
        )
        produto["fornecedores"] = [dict(r) for r in cur.fetchall()]
    return produto


@router.post("", status_code=201)
def criar(body: ProdutoCreate,
          ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    dados = body.model_dump()
    fornecedores = dados.pop("fornecedores", [])
    preco = dados.pop("preco_venda", None)
    _valida_basico(dados)

    with get_cursor() as cur:
        codigo = (dados.get("codigo") or "").strip() or _proximo_codigo(cur)
        cur.execute("SELECT nome FROM produtos WHERE lower(codigo) = lower(%s)", (codigo,))
        existente = cur.fetchone()
        if existente:
            raise HTTPException(
                status_code=409, detail=f"O código {codigo} já é de {existente['nome']}"
            )
        _recusar_codigo_de_outro(cur, dados)
        dados["codigo"] = codigo
        dados["criado_por"] = ctx.id_usuario
        dados["nome"] = dados["nome"].strip()

        colunas = ", ".join(dados)
        marcas = ", ".join(["%s"] * len(dados))
        cur.execute(
            f"INSERT INTO produtos ({colunas}) VALUES ({marcas}) RETURNING id",
            list(dados.values()),
        )
        novo = cur.fetchone()["id"]
        _gravar_preco(cur, novo, preco, ctx.id_usuario)
        _gravar_fornecedores(cur, novo, body.fornecedores)
        auditoria.registrar(cur, ctx.id_usuario, "produto", novo, "criar",
                            depois={"codigo": codigo, "nome": dados["nome"], "tipo": dados["tipo"]})
    return {"id": novo, "codigo": codigo, "message": "Produto criado"}


@router.put("/{id_produto}/preco-loja")
def preco_da_loja(id_produto: int, body: PrecoDaLoja,
                  ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Define — ou apaga — o preço DESTA loja para este produto.

    🔑 **O preço da loja manda; sem ele, vale o da casa.** É a mesma forma da
    reserva do custo: o específico primeiro, o geral depois. E é o que permite a
    filial cobrar diferente sem obrigar a recadastrar centenas de pratos que
    custam o mesmo nos dois lugares.

    ⚠️ **Apagar não é zerar.** Mandar nulo fecha a linha da loja e o produto
    volta a valer o preço da casa; mandar zero seria dizer que ali ele é de
    graça. São coisas diferentes, e o histórico guarda as duas.
    """
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute("SELECT nome FROM produtos WHERE id = %s", (id_produto,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        if body.preco_venda is None:
            cur.execute(
                """UPDATE produto_precos SET vigente_ate = current_date
                    WHERE id_produto = %s AND id_unidade = %s AND vigente_ate IS NULL""",
                (id_produto, id_unidade),
            )
            mudou = bool(cur.rowcount)
            mensagem = ("Preço desta loja removido — vale o preço da casa."
                        if mudou else "Esta loja já usava o preço da casa.")
        else:
            mudou = precos.gravar(cur, id_produto, body.preco_venda, ctx.id_usuario,
                                  id_unidade)
            mensagem = "Preço desta loja salvo." if mudou else "O preço já era esse."

        if mudou:
            auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "preco_da_loja",
                                depois={"preco_venda": body.preco_venda},
                                id_unidade=id_unidade)
    return {"message": mensagem}


@router.put("/{id_produto}")
def atualizar(id_produto: int, body: ProdutoUpdate,
              ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    dados = body.model_dump(exclude_unset=True)
    fornecedores = dados.pop("fornecedores", None)
    preco = dados.pop("preco_venda", None)

    with get_cursor() as cur:
        cur.execute(
            # ⚠️ `um_estoque` entra aqui porque a validação o consulta: sem ele
            # no "antes", um PUT que só muda o preço pareceria estar deixando o
            # produto ativo sem unidade — e levava 400 sem ter mexido nisso.
            "SELECT codigo, nome, tipo, status, producao_propria, um_estoque "
            "  FROM produtos WHERE id = %s",
            (id_produto,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        # O tipo que vale na validação é o novo, se veio; senão o que já estava.
        _valida_basico({**dict(antes), **dados})
        _recusar_codigo_de_outro(cur, dados, id_produto)

        if "codigo" in dados and dados["codigo"]:
            cur.execute(
                "SELECT nome FROM produtos WHERE lower(codigo) = lower(%s) AND id <> %s",
                (dados["codigo"], id_produto),
            )
            outro = cur.fetchone()
            if outro:
                raise HTTPException(status_code=409, detail=f"O código já é de {outro['nome']}")

        campos = {k: v for k, v in dados.items() if k in _EDITAVEIS}
        if campos:
            sets = ", ".join(f"{c} = %s" for c in campos)
            cur.execute(
                f"UPDATE produtos SET {sets} WHERE id = %s", [*campos.values(), id_produto]
            )
        _gravar_preco(cur, id_produto, preco, ctx.id_usuario)
        if fornecedores is not None:
            _gravar_fornecedores(cur, id_produto, body.fornecedores or [])

        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "atualizar",
                            antes=dict(antes), depois=campos)
    return {"message": "Produto atualizado"}


@router.get("/{id_produto}/unidades")
def unidades_de_compra(id_produto: int, ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """Em que unidades este produto é comprado, e quantas de estoque vêm em cada.

    O saldo e o custo vivem numa unidade só — a de estoque. Isto aqui é a
    tabela de conversão: a mesma água vem em caixa de 12, fardo de 6 e palete
    de 480, e a nota chega em qualquer uma delas.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.um, u.fator, u.padrao, u.observacao, m.nome AS unidade_nome
                 FROM produto_unidades u
                 LEFT JOIN unidades_medida m ON m.sigla = u.um
                WHERE u.id_produto = %s
                ORDER BY u.padrao DESC, u.fator""",
            (id_produto,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.put("/{id_produto}/unidades")
def gravar_unidades(id_produto: int, body: UnidadesCompraRequest,
                    ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Substitui a tabela de conversão inteira."""
    with get_cursor() as cur:
        cur.execute("SELECT nome, um_estoque FROM produtos WHERE id = %s", (id_produto,))
        produto = cur.fetchone()
        if not produto:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        vistas, padroes = set(), 0
        for u in body.itens:
            sigla = u.um.strip().upper()
            if sigla in vistas:
                raise HTTPException(
                    status_code=400,
                    detail=f"{sigla} aparece duas vezes — some numa linha só.",
                )
            vistas.add(sigla)
            padroes += 1 if u.padrao else 0
            cur.execute("SELECT sigla FROM unidades_medida WHERE upper(sigla) = %s", (sigla,))
            if not cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"{sigla} não é uma unidade cadastrada em Tabelas de apoio.",
                )
            # A unidade de estoque com fator diferente de 1 seria o produto
            # valendo outro tanto dele mesmo.
            if produto["um_estoque"] and sigla == produto["um_estoque"].upper() and u.fator != 1:
                raise HTTPException(
                    status_code=400,
                    detail=(f"{sigla} é a unidade de estoque: nela o fator é sempre 1."),
                )
        if padroes > 1:
            raise HTTPException(status_code=400, detail="Só uma unidade pode ser a padrão.")

        cur.execute("DELETE FROM produto_unidades WHERE id_produto = %s", (id_produto,))
        for u in body.itens:
            cur.execute(
                """INSERT INTO produto_unidades (id_produto, um, fator, padrao, observacao)
                   VALUES (%s, %s, %s, %s, %s)""",
                (id_produto, u.um.strip().upper(), u.fator, u.padrao, u.observacao),
            )

        # `um_compra`/`fator_compra` continuam existindo e sustentam o cálculo
        # quando a nota vem numa unidade que ninguém cadastrou: a padrão daqui
        # mantém os dois em dia.
        padrao = next((u for u in body.itens if u.padrao), None) or (
            body.itens[0] if body.itens else None)
        if padrao:
            cur.execute(
                "UPDATE produtos SET um_compra = %s, fator_compra = %s WHERE id = %s",
                (padrao.um.strip().upper(), padrao.fator, id_produto),
            )
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "unidades_compra",
                            depois={"unidades": len(body.itens)})
    return {"itens": len(body.itens), "message": f"{len(body.itens)} unidade(s) de compra gravada(s)"}


@router.get("/{id_produto}/kit")
def obter_kit(id_produto: int, ctx: Contexto = Depends(contexto_atual)) -> dict:
    """A composição do combo e quanto ele custa hoje.

    O custo vem junto de propósito: montar a composição sem ver o custo sair é
    trabalhar às cegas — o combo existe para ter preço, e o preço depende disto.
    """
    with get_cursor() as cur:
        itens = kits.componentes(cur, id_produto)
        valor, origem, detalhe = kits.custo(cur, id_produto)
        # Dinheiro só para quem pode ver custo de ficha: a mesma chave que
        # esconde o custo da receita esconde o do combo.
        if not ctx.pode("fichas.custos"):
            return {"itens": itens, "custo": None, "origem": None, "detalhe": []}
    return {
        "itens": itens,
        "custo": float(valor) if valor is not None else None,
        "origem": origem,
        "detalhe": detalhe,
    }


@router.put("/{id_produto}/kit")
def gravar_kit(id_produto: int, body: KitRequest,
               ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    with get_cursor() as cur:
        r = kits.gravar(cur, id_produto, [i.model_dump() for i in body.itens])
        valor, origem, _ = kits.custo(cur, id_produto)
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "kit_composicao",
                            depois={"itens": r["itens"]})
    return r | {
        "custo": float(valor) if valor is not None else None,
        "origem": origem,
        "message": f"Composição gravada com {r['itens']} componente(s)",
    }


@router.post("/{id_produto}/revisar")
def revisar(id_produto: int,
            ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Tira o produto de rascunho — o que libera ele para entrar no estoque."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT um_estoque, fator_compra, status FROM produtos WHERE id = %s", (id_produto,)
        )
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        if not p["um_estoque"] or not p["fator_compra"]:
            raise HTTPException(
                status_code=400,
                detail="Defina a unidade de estoque e o fator de conversão antes de ativar.",
            )
        cur.execute(
            """UPDATE produtos SET status = 'ATIVO', revisado_em = now(), revisado_por = %s
                WHERE id = %s""",
            (ctx.id_usuario, id_produto),
        )
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "revisar",
                            antes={"status": p["status"]}, depois={"status": "ATIVO"})
    return {"message": "Produto revisado e ativo"}


@router.delete("/{id_produto}")
def desativar(id_produto: int,
              ctx: Contexto = Depends(requer_permissao("cadastros.produtos"))) -> dict:
    """Desativa. Produto com movimento no razão nunca pode sumir do histórico."""
    with get_cursor() as cur:
        cur.execute("UPDATE produtos SET ativo = false WHERE id = %s", (id_produto,))
        auditoria.registrar(cur, ctx.id_usuario, "produto", id_produto, "desativar")
    return {"message": "Produto desativado"}
