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
    ):
        self.como_dict = {
            "inicio": inicio, "fim": fim, "locais": locais, "setores": setores,
            "categorias": categorias, "tipos_produto": tipos_produto,
            "tipos_movimento": tipos_movimento, "situacao": situacao,
            "classes": classes, "produtos": produtos, "busca": busca, "dias": dias,
        }

    def preenchidos(self) -> dict:
        """Só o que veio — é isto que vai para a auditoria."""
        return {k: (str(v) if isinstance(v, date) else v)
                for k, v in self.como_dict.items() if v not in (None, [], "")}


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
    return _render(saida, f"inventario-{id_inventario}", ext, timbre, ctx.nome)


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
    nome_arq = exportacao.nome_arquivo(f"ficha-{id_ficha}", ext=ext)
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
                                      filtros.como_dict)
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
        saida = catalogo_motor.montar(cur, chave, id_unidade, filtros.como_dict)
        timbre = catalogo_motor.papel_timbrado(cur)
        auditoria.registrar(
            cur, ctx.id_usuario, "exportacao", chave, "exportar",
            depois={"formato": ext, "linhas": len(saida.linhas), **filtros.preenchidos()},
            id_unidade=id_unidade)
    return _render(saida, rel.base, ext, timbre, ctx.nome)
