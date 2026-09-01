"""Exportações — a mesma declaração de relatório, em planilha ou em PDF.

Cada relatório usa a **mesma permissão da tela** que o mostra: exportar não é
uma porta lateral para ver o que a pessoa não poderia ver.

🔑 **A extensão na URL é o formato, e por isso a URL nunca mente.**
`/exportar/saldos.csv` traz planilha, `/exportar/saldos.pdf` traz PDF, e o
mesmo relatório sai dos dois pela mesma consulta e pela mesma declaração de
colunas. Quando o caminho traz extensão é ela que manda — um `?formato=pdf`
pendurado num `.csv` deixaria o arquivo baixado discordar do endereço que o
gerou, que é o tipo de divergência que ninguém percebe até mandar o arquivo
errado ao contador.

⚠️ **Toda exportação vai para a auditoria, com o filtro que a gerou.** Sem o
filtro, o registro diria "fulano exportou o estoque" — e a pergunta que se faz
depois é sempre *o quê*, exatamente.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

import auditoria
from database import get_cursor
from seguranca import Contexto, contexto_atual, unidade_atual
from services import custos
from services import estoque as estoque_motor
from services import exportacao
from services import exportacao_catalogo as catalogo_motor

router = APIRouter(prefix="/exportar", tags=["exportações"])

FORMATOS = ("csv", "pdf")
_MIME = {"csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}


def _exige(ctx: Contexto, chave: str) -> None:
    if not ctx.pode(chave):
        raise HTTPException(status_code=403, detail=f"Sem permissão para esta ação ({chave})")


def _exige_alguma(ctx: Contexto, *chaves: str) -> None:
    """Qualquer um dos níveis serve — é como `fichas.py` deixa ver a ficha."""
    if not any(ctx.pode(c) for c in chaves):
        raise HTTPException(status_code=403,
                            detail=f"Sem permissão para esta ação ({' ou '.join(chaves)})")


def _centavos(v):
    """Dinheiro de APRESENTAÇÃO. O cálculo continua exato — quem arredonda é a
    linha do relatório."""
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _junta_fiscais(prod: dict) -> str | None:
    """NCM, EAN, CEST e marca numa linha só — cada um aparece se existir."""
    pedacos = [f"NCM {prod['ncm']}" if prod.get("ncm") else None,
               f"EAN {prod['codigo_barras']}" if prod.get("codigo_barras") else None,
               f"CEST {prod['cest']}" if prod.get("cest") else None,
               prod.get("marca")]
    return " · ".join(p for p in pedacos if p) or None


def _id_do_caminho(bruto: str, oque: str) -> int:
    try:
        return int(bruto)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"{oque} não encontrado")


def _partir(nome: str, formato: str | None) -> tuple[str, str]:
    """"saldos.csv" → ("saldos", "csv"); "saldos" + formato → ("saldos", formato)."""
    chave, ponto, ext = nome.rpartition(".")
    if not ponto:
        chave, ext = nome, (formato or "csv")
    ext = ext.lower()
    if ext not in FORMATOS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato que não existe: {ext}. Os que existem: {', '.join(FORMATOS)}.")
    return chave, ext


def _entregar(conteudo: bytes, nome: str, ext: str) -> Response:
    return Response(
        content=conteudo,
        media_type=_MIME[ext],
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _render(saida: catalogo_motor.Saida, base: str, ext: str,
            timbre: dict | None = None, por: str | None = None) -> Response:
    nome = exportacao.nome_arquivo(base, saida.inicio, saida.fim, ext=ext)
    if ext == "pdf":
        # ⚠️ O teto conta o arquivo INTEIRO, anexo incluído: são as páginas do
        # mesmo PDF, e medir só o quadro principal deixaria passar um documento
        # que o anexo sozinho já torna impossível de abrir.
        catalogo_motor.limite_do_pdf(
            len(saida.linhas) + sum(len(a[0]) for a in saida.anexos))
        return _entregar(
            exportacao.pdf_de(saida.linhas, saida.colunas, saida.titulo, saida.resumo,
                              anexos=saida.anexos, empresa=timbre, emitido_por=por),
            nome, ext)
    texto = exportacao.csv_de(saida.linhas, saida.colunas, saida.titulo, saida.resumo,
                              anexos=saida.anexos)
    return _entregar(texto.encode("utf-8"), nome, ext)


class _Filtros:
    """Os filtros que qualquer relatório pode receber.

    ⚠️ Um relatório ignora o que não declarou — mandar `classes` para o razão
    não muda nada em vez de dar erro. É de propósito: a tela só oferece o que o
    catálogo declarou, e um 422 aqui transformaria um filtro esquecido numa
    tela que não baixa nada, sem dizer por quê.
    """

    def __init__(
        self,
        inicio: date | None = None,
        fim: date | None = None,
        locais: list[int] | None = Query(default=None),
        setores: list[int] | None = Query(default=None),
        categorias: list[int] | None = Query(default=None),
        tipos_produto: list[str] | None = Query(default=None),
        tipos_movimento: list[str] | None = Query(default=None),
        situacao: list[str] | None = Query(default=None),
        classes: list[str] | None = Query(default=None),
        produtos: list[int] | None = Query(default=None),
        busca: str | None = None,
        dias: int | None = Query(default=None, ge=0, le=365),
        # ⚠️ Booleano, e não lista: "só as provisórias" é uma pergunta de sim ou
        # não. Ausente e `false` são a mesma coisa — todos os movimentos.
        provisorio: bool = False,
    ):
        self.como_dict = {
            "inicio": inicio, "fim": fim, "locais": locais, "setores": setores,
            "categorias": categorias, "tipos_produto": tipos_produto,
            "tipos_movimento": tipos_movimento, "situacao": situacao,
            "classes": classes, "produtos": produtos, "busca": busca, "dias": dias,
            "provisorio": provisorio,
        }

    def preenchidos(self) -> dict:
        """Só o que veio — é isto que vai para a auditoria.

        ⚠️ **`False` sai por IDENTIDADE, não por igualdade.** Um booleano
        desmarcado é "não filtrei", e registrá-lo em toda exportação encheria a
        auditoria de `provisorio: false`. Mas `v not in (None, [], "", False)`
        derrubaria junto o `dias=0` — que é um filtro legítimo ("vencendo
        hoje") —, porque em Python `0 == False`.
        """
        return {k: (str(v) if isinstance(v, date) else v)
                for k, v in self.como_dict.items()
                if v is not False and v not in (None, [], "")}


# ⚠️ `/catalogo` e `/inventario/...` são declarados ANTES de `/{relatorio}`: o
# FastAPI casa rotas na ordem de declaração, e com o parâmetro na frente
# "catalogo" viraria o nome de um relatório que não existe.
@router.get("/catalogo")
def catalogo(ctx: Contexto = Depends(contexto_atual)) -> list[dict]:
    """O que ESTA pessoa pode exportar, e com que filtros — a fonte do diálogo."""
    with get_cursor() as cur:
        return catalogo_motor.catalogo(cur, unidade_atual(cur, ctx), ctx.pode)


@router.get("/inventario/{nome}")
def inventario(nome: str, formato: str | None = None,
               ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A folha de contagem — imprimir, contar no papel e digitar depois."""
    _exige(ctx, "estoque.inventario")
    bruto, ext = _partir(nome, formato)
    id_inventario = _id_do_caminho(bruto, "Inventário")

    with get_cursor() as cur:
        cur.execute(
            # ⚠️ `LEFT JOIN`: a contagem de vários locais não tem local único, e
            # o `JOIN` a fazia sumir — a folha respondia 404 sem explicar nada.
            """SELECT i.data, i.status, i.cega, i.nome,
                      coalesce(l.nome, i.nome, 'vários locais') AS local
                 FROM inventarios i
                 LEFT JOIN locais_estoque l ON l.id = i.id_local WHERE i.id = %s""",
            (id_inventario,),
        )
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventário não encontrado")
        cur.execute(
            """SELECT p.codigo, p.nome AS produto, p.um_estoque,
                      l.nome AS local, ii.qtd_sistema,
                      ii.qtd_contada, ii.custo_medio,
                      (coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema) AS diferenca,
                      round((coalesce(ii.qtd_contada, ii.qtd_sistema) - ii.qtd_sistema)
                            * ii.custo_medio, 2) AS impacto
                 FROM inventario_itens ii
                 JOIN produtos p ON p.id = ii.id_produto
                 LEFT JOIN locais_estoque l ON l.id = ii.id_local
                WHERE ii.id_inventario = %s ORDER BY lower(l.nome), lower(p.nome)""",
            (id_inventario,),
        )
        linhas = [dict(r) for r in cur.fetchall()]
        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", f"inventario-{id_inventario}",
                            "exportar", depois={"formato": ext, "linhas": len(linhas)})

    # Contagem CEGA aberta: a folha impressa é o caminho mais fácil de furar o
    # sigilo — quem conta leria o esperado no papel. As colunas do sistema saem.
    cega_aberta = inv["cega"] and inv["status"] == "ABERTO"
    # ⚠️ A coluna do local só aparece quando a contagem cobre mais de um: numa
    # folha de um local só ela seria a mesma palavra repetida em cada linha.
    varios_locais = len({l["local"] for l in linhas}) > 1
    colunas = [("codigo", "Código"), ("produto", "Produto"), ("um_estoque", "Unidade")]
    if varios_locais:
        colunas.append(("local", "Local"))
    if not cega_aberta:
        colunas.append(("qtd_sistema", "Saldo no sistema"))
    colunas.append(("qtd_contada", "Contado"))
    if not cega_aberta:
        colunas += [("diferenca", "Diferença"), ("custo_medio", "Custo médio"),
                    ("impacto", "Impacto (R$)")]

    saida = catalogo_motor.Saida(
        linhas, colunas,
        f"Inventário #{id_inventario} — {inv['local']}",
        [("Data", inv["data"]), ("Situação", inv["status"]),
         ("Contagem", "cega — o saldo do sistema não sai daqui" if cega_aberta else "aberta"),
         ("Itens", len(linhas))],
    )
    apelido = exportacao.slug(inv["nome"] or inv["local"]) or str(id_inventario)
    return _render(saida, f"inventario-{apelido}", ext, timbre, ctx.nome)


@router.get("/produto/{nome}")
def produto(nome: str, formato: str | None = None,
            ctx: Contexto = Depends(contexto_atual)) -> Response:
    """Tudo o que a casa sabe de UM produto, num arquivo só.

    A tela do produto junta cadastro, saldo, embalagens, fornecedores e o
    razão dele em abas e blocos; quem precisa levar isso para fora — para
    conferir uma compra, para discutir preço com o fornecedor, para responder
    ao contador — não tinha como.

    ⚠️ **O bloco de ESTOQUE exige `estoque.saldos`.** Saldo, custo médio e
    razão são dados de estoque, e não passam a ser de cadastro por estarem no
    arquivo de um produto — é a mesma regra do custo na ficha técnica: o PDF é
    o que sai da tela e circula, e não pode ser a porta lateral de nada.
    """
    _exige(ctx, "cadastros.produtos")
    bruto, ext = _partir(nome, formato)
    id_produto = _id_do_caminho(bruto, "Produto")
    ve_estoque = ctx.pode("estoque.saldos")

    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        cur.execute(
            """SELECT p.*, c.nome AS categoria, s.nome AS setor, l.nome AS local_padrao,
                      (SELECT pp.preco_venda FROM produto_precos pp
                        WHERE pp.id_produto = p.id AND pp.vigente_ate IS NULL
                          AND (pp.id_unidade = %s OR pp.id_unidade IS NULL)
                        ORDER BY pp.id_unidade NULLS LAST LIMIT 1) AS preco_venda
                 FROM produtos p
                 LEFT JOIN categorias c ON c.id = p.id_categoria
                 LEFT JOIN setores s ON s.id = p.id_setor
                 LEFT JOIN locais_estoque l ON l.id = p.id_local_padrao
                WHERE p.id = %s""",
            # A loja vem primeiro: o `%s` dela está na lista do SELECT.
            (id_unidade, id_produto),
        )
        prod = cur.fetchone()
        if not prod:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        prod = dict(prod)

        saldos: list[dict] = []
        movimentos: list[dict] = []
        if ve_estoque:
            cur.execute(
                """SELECT l.nome AS local, e.quantidade, e.custo_medio,
                          round(e.quantidade * e.custo_medio, 2) AS valor
                     FROM estoque_saldos e
                     JOIN locais_estoque l ON l.id = e.id_local
                    WHERE e.id_produto = %s AND e.id_unidade = %s AND e.quantidade <> 0
                    ORDER BY lower(l.nome)""",
                (id_produto, id_unidade),
            )
            saldos = [dict(r) for r in cur.fetchall()]
            # ⚠️ Os ÚLTIMOS, não todos: o razão de um insumo movimentado pode
            # ter milhares de linhas, e quem abre a ficha de um produto quer o
            # que aconteceu com ele agora. O razão inteiro tem relatório próprio.
            cur.execute(
                """SELECT m.data_movimento, m.tipo, l.nome AS local, m.quantidade,
                          m.custo_unitario, m.saldo_apos, m.custo_medio_apos, m.documento
                     FROM estoque_movimentos m
                     JOIN locais_estoque l ON l.id = m.id_local
                    WHERE m.id_produto = %s AND m.id_unidade = %s
                    ORDER BY m.id DESC LIMIT 50""",
                (id_produto, id_unidade),
            )
            movimentos = [dict(r) for r in cur.fetchall()][::-1]
            for m in movimentos:
                m["tipo"] = estoque_motor.ROTULOS.get(m["tipo"], m["tipo"])

        cur.execute(
            """SELECT um, fator, padrao, observacao FROM produto_unidades
                WHERE id_produto = %s ORDER BY padrao DESC, fator""",
            (id_produto,),
        )
        embalagens = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """SELECT f.nome AS fornecedor, pf.codigo_no_fornecedor, pf.embalagem, pf.fator,
                      pf.ultimo_preco, pf.ultima_compra, pf.preferencial
                 FROM produto_fornecedor pf
                 JOIN fornecedores f ON f.id = pf.id_fornecedor
                WHERE pf.id_produto = %s
                ORDER BY pf.preferencial DESC, lower(f.nome)""",
            (id_produto,),
        )
        fornecedores = [dict(r) for r in cur.fetchall()]

        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", f"produto-{id_produto}",
                            "exportar", depois={"formato": ext, "com_estoque": ve_estoque},
                            id_unidade=id_unidade)

    resumo: list[tuple[str, object]] = [
        ("Código", prod["codigo"]),
        ("Tipo", prod["tipo"]),
        ("Categoria", prod["categoria"] or "—"),
        ("Setor", prod["setor"] or "—"),
        ("Unidade de estoque", prod["um_estoque"] or "—"),
        ("Situação", f"{prod['status']} · {'ativo' if prod['ativo'] else 'inativo'}"),
    ]
    if prod["um_compra"]:
        resumo.append(("Unidade de compra",
                       f"{prod['um_compra']} × {exportacao.quantidade_br(prod['fator_compra'])}"))
    if prod["preco_venda"] is not None:
        resumo.append(("Preço de venda", _centavos(prod["preco_venda"])))
    if prod["local_padrao"]:
        resumo.append(("Local padrão", prod["local_padrao"]))
    if prod["estoque_minimo"]:
        resumo.append(("Estoque mínimo",
                       exportacao.quantidade_br(prod["estoque_minimo"], prod["um_estoque"])))
    if prod["perecivel"]:
        resumo.append(("Perecível", f"validade de {prod['validade_dias']} dia(s)"
                                    if prod["validade_dias"] else "sim"))
    if prod["controla_lote"]:
        resumo.append(("Controla lote", True))
    fiscais = _junta_fiscais(prod)
    if fiscais:
        resumo.append(("Fiscal", fiscais))
    if ve_estoque:
        resumo.append(("Saldo total",
                       exportacao.quantidade_br(
                           sum(s["quantidade"] for s in saldos) if saldos else 0,
                           prod["um_estoque"])))
        resumo.append(("Valor em estoque",
                       _centavos(sum(s["valor"] or 0 for s in saldos)) if saldos else 0))

    # Os quadros do arquivo, na ordem em que se lê um produto: onde ele está,
    # em que embalagem entra, com quem se compra, e o que aconteceu com ele.
    # ⚠️ Quadro vazio não entra — um produto recém-cadastrado não tem saldo nem
    # fornecedor, e três tabelas vazias fazem o arquivo parecer defeituoso.
    blocos: list[tuple] = []
    if saldos:
        blocos.append((saldos,
                       [("local", "Local"), ("quantidade", "Saldo"),
                        ("custo_medio", "Custo médio"), ("valor", "Valor")],
                       "Saldo por local", None))
    if embalagens:
        blocos.append((embalagens,
                       [("um", "Unidade"), ("fator", "Equivale a (un. de estoque)"),
                        ("padrao", "Padrão"), ("observacao", "Observação")],
                       "Embalagens de compra", None))
    if fornecedores:
        blocos.append((fornecedores,
                       [("fornecedor", "Fornecedor"),
                        ("codigo_no_fornecedor", "Código lá"), ("embalagem", "Embalagem"),
                        ("fator", "Fator"), ("ultimo_preco", "Último preço"),
                        ("ultima_compra", "Última compra"),
                        ("preferencial", "Preferencial")],
                       "Quem fornece", None))
    if movimentos:
        blocos.append((movimentos,
                       [("data_movimento", "Data"), ("tipo", "Movimento"),
                        ("local", "Local"), ("quantidade", "Quantidade"),
                        ("custo_unitario", "Custo unitário"), ("saldo_apos", "Saldo depois"),
                        ("custo_medio_apos", "Custo médio depois"),
                        ("documento", "Documento")],
                       "Últimos movimentos", None))

    titulo = f"Produto — {prod['nome']}"
    apelido = exportacao.slug(prod["nome"]) or str(id_produto)
    nome_arq = exportacao.nome_arquivo(f"produto-{apelido}", ext=ext)
    vazio = ("Este produto ainda não tem saldo, embalagem, fornecedor nem movimento — "
             "só o cadastro acima.")

    # ⚠️ Aqui NÃO há quadro principal: são quatro assuntos do mesmo produto, e
    # promover um deles a "a tabela" faria os outros três parecerem apêndice.
    # O bloco principal fica só com o título e o resumo (colunas vazias), e
    # cada quadro entra como anexo, com o nome dele em cima.
    notas = [] if blocos else [("", vazio)]
    if ext == "pdf":
        catalogo_motor.limite_do_pdf(sum(len(b[0]) for b in blocos))
        return _entregar(
            exportacao.pdf_de([], [], titulo, resumo, anexos=blocos, notas=notas,
                              empresa=timbre, emitido_por=ctx.nome),
            nome_arq, ext)
    return _entregar(
        exportacao.csv_de([], [], titulo, resumo, anexos=blocos,
                          notas=notas).encode("utf-8"),
        nome_arq, ext)


@router.get("/ficha/{nome}")
def ficha(nome: str, formato: str | None = None,
          ctx: Contexto = Depends(contexto_atual)) -> Response:
    """A ficha técnica para IMPRIMIR — o cartão que fica pendurado na cozinha.

    🔑 **Ver a ficha e ver o CUSTO são permissões diferentes, e isso vale aqui
    igual.** Sem `fichas.custos` nenhum campo de dinheiro entra no arquivo — não
    é a tela que esconde, é o servidor. Um PDF é justamente o que sai da tela e
    circula: se o dinheiro vazasse por aqui, a regra do router de fichas viraria
    enfeite.

    ⚠️ **O modo de preparo não é tabela** — é o texto que a cozinha lê enquanto
    faz. Vai como NOTA, depois dos ingredientes, que é a ordem em que se usa.
    """
    _exige_alguma(ctx, "fichas.visualizar", "fichas.editar")
    bruto, ext = _partir(nome, formato)
    id_ficha = _id_do_caminho(bruto, "Ficha")
    ve_custo = ctx.pode("fichas.custos")

    with get_cursor() as cur:
        cur.execute(
            """SELECT f.*, p.nome AS produto, p.codigo, u.nome AS homologada_por_nome
                 FROM fichas_tecnicas f
                 JOIN produtos p ON p.id = f.id_produto
                 LEFT JOIN usuarios u ON u.id = f.homologada_por
                WHERE f.id = %s""",
            (id_ficha,),
        )
        f = cur.fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="Ficha não encontrada")
        calculo = custos.custo_da_ficha(cur, id_ficha)
        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(cur, ctx.id_usuario, "exportacao", f"ficha-{id_ficha}",
                            "exportar", depois={"formato": ext, "com_custo": ve_custo})

    linhas = []
    for i in calculo["itens"]:
        linha = {
            # ⚠️ A linha da ficha aponta para um insumo OU um preparo com ficha
            # própria, e a cozinha precisa saber qual: um se pega na prateleira,
            # o outro foi feito antes. O nome sozinho não diz isso.
            "origem": "preparo" if i["id_subficha"] else "insumo",
            "nome": i["nome"],
            "qtd_bruta": i["qtd_bruta"],
            "um": i["um"],
            "qtd_liquida": i["qtd_liquida"],
            "fator_correcao": i["fator_correcao"],
            "fator_coccao": i["fator_coccao"],
            "no_estoque": (exportacao.quantidade_br(i["qtd_estoque"], i["um_estoque"])
                           if i.get("qtd_estoque") is not None and i.get("um_estoque")
                           else None),
            # ⚠️ Guardado só para decidir se a coluna entra: ela existe para o
            # caso de a receita pedir 1 CX e o razão baixar 12 PCT. Sem
            # conversão, "No estoque" é a cópia das duas colunas anteriores.
            "_converteu": bool(i.get("um_estoque")) and i.get("um_estoque") != i["um"],
            "observacao": i["observacao"],
        }
        if ve_custo:
            # ⚠️ O custo unitário é um PREÇO (R$ por KG) e fica com a precisão
            # que tiver; o custo total é o dinheiro daquela linha, e sai em
            # CENTAVOS — a coluna vinha com "2,375" e "1,287" no meio de valores
            # de dois dígitos, e é uma coluna que alguém soma com o dedo.
            linha["custo_unitario"] = i["custo_unitario"]
            linha["custo_total"] = _centavos(i["custo_total"])
        linhas.append(linha)

    colunas = [("origem", "Tipo"), ("nome", "Ingrediente"), ("qtd_bruta", "Qtd bruta"),
               ("um", "Un."), ("qtd_liquida", "Qtd líquida"),
               ("fator_correcao", "Fator correção"), ("fator_coccao", "Fator cocção"),
               ("no_estoque", "No estoque"), ("observacao", "Observação")]
    if ve_custo:
        colunas += [("custo_unitario", "Custo unitário"), ("custo_total", "Custo total")]

    # ⚠️ **Coluna sem informação SAI da ficha.** É a mesma regra da folha de
    # contagem, que só mostra o local quando a contagem cobre mais de um: numa
    # receita simples, "Qtd líquida" e "Observação" vêm vazias em todas as
    # linhas e "Fator correção" é 1,00 repetido — três colunas ocupando a
    # página, empurrando o documento para PAISAGEM. Sem elas a ficha cabe em
    # RETRATO, que é o formato de quem vai pendurar o papel na cozinha.
    # ⚠️ Elas voltam sozinhas na receita que as usa: quem descasca cebola tem
    # fator de correção, e aí a coluna é a informação mais importante da linha.
    def _tem_informacao(chave: str) -> bool:
        valores = [l.get(chave) for l in linhas]
        if all(v is None or v == "" for v in valores):
            return False
        if chave in ("fator_correcao", "fator_coccao"):
            return any(v is not None and float(v) != 1 for v in valores)
        if chave == "no_estoque":
            return any(l.get("_converteu") for l in linhas)
        if chave == "origem":
            # A coluna existe para separar o que se pega da prateleira do que
            # foi preparado antes. Só de insumo, ela é a mesma palavra repetida.
            return len({v for v in valores}) > 1
        return True

    colunas = [(c, cab) for c, cab in colunas if _tem_informacao(c)]

    resumo: list[tuple[str, object]] = [
        ("Código do produto", f["codigo"]),
        ("Versão", f["versao"]),
        ("Situação", f["status"]),
        ("Rendimento", exportacao.quantidade_br(f["rendimento_qtd"], f["rendimento_um"])),
        ("Porções", exportacao.quantidade_br(f["porcoes"])),
    ]
    if f["tempo_preparo_min"]:
        resumo.append(("Tempo de preparo", f"{f['tempo_preparo_min']} min"))
    if f["alergenos"]:
        resumo.append(("Alérgenos", f["alergenos"]))
    if f["homologada_em"]:
        resumo.append(("Homologada em", f["homologada_em"]))
        resumo.append(("Homologada por", f["homologada_por_nome"] or "—"))
    if ve_custo:
        # ⚠️ O total do resumo é o número AUTORIZADO — o mesmo que a tela
        # mostra e que o CMV usa. Ele não vira a soma das linhas arredondadas:
        # somar a coluna com o dedo pode dar um centavo de diferença, e é
        # preferível a um relatório que discorde do sistema sobre o custo da
        # receita.
        resumo.append(("Custo da receita", _centavos(calculo["custo_total"])))
        resumo.append(("Custo por porção", _centavos(calculo["custo_por_porcao"])))
        if calculo["itens_sem_custo"]:
            # ⚠️ O aviso vem no RESUMO, junto do número, não num rodapé: quem lê
            # "R$ 4,20 a porção" sem saber que dois itens estão sem preço leva
            # daqui um custo que não é o custo.
            resumo.append(("⚠ Itens sem preço conhecido",
                           f"{calculo['itens_sem_custo']} — o custo acima é parcial"))

    saida = catalogo_motor.Saida(
        linhas, colunas, f"Ficha técnica — {f['produto']}", resumo,
        anexos=[],
    )
    # ⚠️ O nome do arquivo é o que a pessoa vê na pasta de Downloads:
    # `botane-ficha-431.pdf` obriga a abrir para saber de que prato é, e quem
    # baixa cinco fichas seguidas fica com cinco números. A VERSÃO entra junto
    # porque duas versões do mesmo prato são dois documentos diferentes.
    apelido = exportacao.slug(f["produto"]) or str(id_ficha)
    nome_arq = exportacao.nome_arquivo(f"ficha-{apelido}-v{f['versao']}", ext=ext)
    notas = [("Modo de preparo", f["modo_preparo"] or ""),
             ("Observações", f["observacao"] or "")]
    if ext == "pdf":
        catalogo_motor.limite_do_pdf(len(linhas))
        return _entregar(
            exportacao.pdf_de(saida.linhas, saida.colunas, saida.titulo, saida.resumo,
                              # ⚠️ Sem o nome da casa: ele está no timbre, logo
                              # acima. Repetido, envelhece num dos dois lugares.
                              subtitulo=(f"versão {f['versao']}"
                                         f" · {str(f['status']).lower()}"),
                              notas=notas, empresa=timbre, emitido_por=ctx.nome,
                              # A ficha é um CARTÃO DE RECEITA: sai em retrato,
                              # que é a forma do papel que se pendura. Só cede à
                              # paisagem quando a receita usa colunas demais.
                              orientacao="retrato" if len(saida.colunas) <= 9 else "auto"),
            nome_arq, ext)
    return _entregar(
        exportacao.csv_de(saida.linhas, saida.colunas, saida.titulo, saida.resumo,
                          notas=notas).encode("utf-8"),
        nome_arq, ext)


def _com_as_lojas(cur, ctx: Contexto, filtros: dict) -> dict:
    """Põe no filtro as lojas que ESTA pessoa enxerga.

    🔑 **Só o relatório da rede usa, e ele não poderia resolver isto sozinho:**
    `exportacao_catalogo` não conhece `ve_unidade`, e inventar a lista lá
    somaria estoque de loja que a pessoa não pode consultar — vazando pelo
    total, que é o pior lugar para vazar, porque nada na tela denuncia.
    ⚠️ Vai com `_` na frente: é um parâmetro INTERNO, não um filtro que a janela
    oferece. Quem escolhe as lojas é a permissão, não quem baixa.
    """
    cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY matriz DESC, id")
    filtros["_lojas"] = [r["id"] for r in cur.fetchall() if ctx.ve_unidade(r["id"])]
    return filtros


@router.get("/{relatorio}/previa")
def previa(relatorio: str, filtros: _Filtros = Depends(),
           ctx: Contexto = Depends(contexto_atual)) -> dict:
    """Quantas linhas viriam, ANTES do botão.

    ⚠️ É a mesma ideia da prévia do inventário: numa base real o filtro em
    branco traz o cadastro inteiro, e descobrir isso depois custa abrir um
    arquivo de 3.226 linhas para ver que não era aquilo. Diz também se cabe em
    PDF, porque o teto do PDF não pode ser uma surpresa no clique.
    """
    rel = catalogo_motor.RELATORIOS.get(relatorio)
    if not rel:
        raise HTTPException(status_code=404, detail=f"Relatório que não existe: {relatorio}")
    _exige(ctx, rel.permissao)
    with get_cursor() as cur:
        saida = catalogo_motor.montar(cur, relatorio, unidade_atual(cur, ctx),
                                      _com_as_lojas(cur, ctx, filtros.como_dict))
    # O número tem de ser o do ARQUIVO, anexo incluído — senão a prévia diz 10
    # e o contador abre uma planilha de 500 linhas.
    total = len(saida.linhas) + sum(len(a[0]) for a in saida.anexos)
    return {
        "linhas": total,
        "titulo": saida.titulo,
        "cabe_no_pdf": total <= exportacao.MAXIMO_PDF,
        "maximo_pdf": exportacao.MAXIMO_PDF,
    }


@router.get("/{relatorio}")
def exportar(relatorio: str, formato: str | None = None, filtros: _Filtros = Depends(),
             ctx: Contexto = Depends(contexto_atual)) -> Response:
    chave, ext = _partir(relatorio, formato)
    rel = catalogo_motor.RELATORIOS.get(chave)
    if not rel:
        raise HTTPException(
            status_code=404,
            detail=f"Relatório que não existe: {chave}. "
                   f"Os que existem: {', '.join(sorted(catalogo_motor.RELATORIOS))}.")
    _exige(ctx, rel.permissao)
    with get_cursor() as cur:
        id_unidade = unidade_atual(cur, ctx)
        saida = catalogo_motor.montar(cur, chave, id_unidade,
                                      _com_as_lojas(cur, ctx, filtros.como_dict))
        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(
            cur, ctx.id_usuario, "exportacao", chave, "exportar",
            depois={"formato": ext, "linhas": len(saida.linhas), **filtros.preenchidos()},
            id_unidade=id_unidade)
    return _render(saida, rel.base, ext, timbre, ctx.nome)
