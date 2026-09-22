"""Catálogos — o cabeçalho do que a casa publica para o cliente.

🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de catálogos.
Onde teremos o cabeçalho do catálogo, origem — neste momento somente vamos ter
PDF —, o nome dele no site do cliente, o período de publicação, a situação:
rascunho, ativo, inativo."*

🔑 **O catálogo pertence a RESERVAS** (correção do dono no mesmo dia: *"o menu de
catálogo fica dentro de reservas, onde somente será demonstrada quando utilizado
reserva"*). A porta é a mesma da migração 068: enquanto `reservas_ligado`
estiver desligado nesta loja, o menu não mostra o item e **estas rotas
recusam** — as duas coisas, não só a primeira.
⚠️ **A trava do servidor não é redundância da do menu.** Esconder o item é
conforto; o que impede uma casa sem reservas de ganhar catálogo é a recusa aqui.

⚠️ **É a CAPA, e só ela.** Os itens do catálogo são a próxima fatia.

🔑 **Cada rota declara a permissão que exige** — regra da casa, nada de checagem
só na tela. `catalogos.ver` para ler, `catalogos.editar` para mexer.

⚠️ **Toda consulta passa por `unidade_atual`**, e não é zelo: o catálogo é de
cada loja, e uma rota que esquecesse o filtro deixaria a filial alterar o
cardápio da matriz. É a lição que `listar_fechamentos` do CMV pagou.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

import arquivos
import auditoria
from database import get_cursor
from models.catalogos import (
    CatalogoCreate, CatalogoResponse, CatalogoUpdate, CategoriaCreate, ItemCreate,
    ORIGENS, SITUACOES, SubcategoriaCreate,
)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import catalogo_conteudo as conteudo
from services import catalogos as servico
from services import reservas as reservas_servico

router = APIRouter(prefix="/catalogos", tags=["catálogos"])

_VER = requer_permissao("catalogos.ver")
_EDITAR = requer_permissao("catalogos.editar")


def _unidade(cur, ctx: Contexto) -> int:
    """A loja atual — desde que ela tenha Reservas ligado.

    ⚠️ **409, não 403**: não é falta de permissão, é módulo desligado. A frase
    diz onde se liga, como a de Reservas — recusar sem dizer o caminho manda a
    pessoa procurar num menu que, justamente, não mostra o item.
    """
    id_unidade = unidade_atual(cur, ctx)
    if not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(
            status_code=409,
            detail=("O catálogo é do site de reservas, e o módulo de Reservas não está "
                    "ligado nesta loja. Ligue em Administração → Lojas, no parâmetro "
                    "Reservas."),
        )
    return id_unidade


# ⚠️ **`/opcoes` é declarado ANTES de `/{id_catalogo}`**: o FastAPI casa rotas
# na ordem de declaração, e com o parâmetro na frente "opcoes" viraria o id de
# um catálogo que não existe — 422 por um caminho que deveria funcionar.
@router.get("/opcoes")
def opcoes(ctx: Contexto = Depends(_VER)) -> dict:
    """O vocabulário do cadastro, dito pelo SERVIDOR.

    🔑 **Para a tela não manter a segunda cópia da lista.** É a mesma lição das
    três listas de `TIPOS` que divergiram caladas: a tela ofereceria uma origem
    que o servidor recusa, e nada denunciaria até alguém salvar.
    """
    with get_cursor() as cur:
        _unidade(cur, ctx)
    return {"origens": list(ORIGENS), "situacoes": list(SITUACOES)}


@router.get("/produtos-disponiveis")
def listar_produtos(busca: str | None = Query(default=None, max_length=80),
                    ctx: Contexto = Depends(_VER)) -> list[dict]:
    """Os produtos que podem entrar no cardápio: ativos e vendidos no PDV.

    ⚠️ **Com teto de 50 e busca**, porque a base real tem milhares de produtos —
    uma lista inteira numa caixa de seleção é uma lista que ninguém percorre.
    """
    with get_cursor() as cur:
        _unidade(cur, ctx)
        return conteudo.produtos_disponiveis(cur, busca)


@router.get("", response_model=list[CatalogoResponse])
def listar(
    situacao: str | None = Query(default=None),
    ctx: Contexto = Depends(_VER),
) -> list[dict]:
    with get_cursor() as cur:
        return servico.listar(cur, _unidade(cur, ctx), situacao)


@router.get("/{id_catalogo}", response_model=CatalogoResponse)
def obter(id_catalogo: int, ctx: Contexto = Depends(_VER)) -> dict:
    with get_cursor() as cur:
        return servico.obter(cur, _unidade(cur, ctx), id_catalogo)


@router.post("", status_code=201, response_model=CatalogoResponse)
def criar(body: CatalogoCreate, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        novo = servico.criar(cur, id_unidade, body.model_dump(), ctx.id_usuario)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo", novo["id"], "criar",
                            depois=body.model_dump(mode="json"), id_unidade=id_unidade)
        return novo


@router.put("/{id_catalogo}", response_model=CatalogoResponse)
def atualizar(id_catalogo: int, body: CatalogoUpdate,
              ctx: Contexto = Depends(_EDITAR)) -> dict:
    """⚠️ `exclude_unset`: campo ausente não é campo nulo — ver o service."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        dados = body.model_dump(exclude_unset=True)
        depois = servico.atualizar(cur, id_unidade, id_catalogo, dados)
        # 🔑 **Publicar é o que muda o que o cliente vê**, então a situação fica
        # na auditoria com o antes e o depois. Um catálogo que saiu do ar sem
        # ninguém saber quem tirou é a pergunta que a auditoria existe para
        # responder.
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "alterar",
            antes={k: str(antes.get(k)) for k in dados if k in antes},
            depois={k: str(depois.get(k)) for k in dados if k in depois},
            id_unidade=id_unidade)
        return depois


@router.post("/{id_catalogo}/arquivo", response_model=CatalogoResponse)
async def enviar_arquivo(id_catalogo: int, arquivo: UploadFile = File(...),
                         ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Carrega o PDF que o site de reservas vai exibir.

    🔑 **Pedido do dono (21/09/2026):** *"criei o catálogo, agora tenho que
    poder carregar o PDF, neste caso para ele ser exibido."*

    ⚠️ **Os bytes são lidos ANTES de pedir a conexão.** Até 10 MB vindos pela
    rede com uma transação aberta prenderiam uma conexão do pool durante todo o
    envio — é a mesma razão pela qual `ler_pdf` é separado de `gravar`.

    ⚠️ **Substitui o anterior**, se houver: um catálogo tem UM arquivo, e a
    troca do cardápio é rotina. O antigo é apagado na mesma transação, depois de
    o registro já apontar para o novo.
    """
    conteudo, tipo, extensao = await arquivos.ler_pdf(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        depois = servico.guardar_arquivo(
            cur, id_unidade, id_catalogo, conteudo, tipo, extensao, arquivo.filename)
        # 🔑 **O arquivo é o que o cliente vê.** Trocá-lo muda o cardápio
        # publicado sem mexer em campo nenhum da capa — a auditoria é o único
        # lugar onde isso fica registrado.
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "enviar_arquivo",
            antes={"arquivo_nome": antes.get("arquivo_nome")},
            depois={"arquivo_nome": depois.get("arquivo_nome"),
                    "bytes": depois.get("arquivo_bytes")},
            id_unidade=id_unidade)
        return depois


@router.delete("/{id_catalogo}/arquivo", response_model=CatalogoResponse)
def remover_arquivo(id_catalogo: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Tira o PDF — o catálogo continua, sem arquivo.

    ⚠️ **Declarada ANTES de `DELETE /{id_catalogo}`**, como `/opcoes`: o FastAPI
    casa rotas na ordem, e o caminho mais específico precisa vir primeiro.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        depois = servico.remover_arquivo(cur, id_unidade, id_catalogo)
        auditoria.registrar(
            cur, ctx.id_usuario, "catalogo", id_catalogo, "remover_arquivo",
            antes={"arquivo_nome": antes.get("arquivo_nome")},
            id_unidade=id_unidade)
        return depois


@router.delete("/{id_catalogo}")
def excluir(id_catalogo: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """⚠️ Só rascunho se apaga — o resto se inativa. A regra mora no service."""
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade, id_catalogo)
        r = servico.excluir(cur, id_unidade, id_catalogo)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo", id_catalogo, "excluir",
                            antes={"nome": antes["nome"], "situacao": antes["situacao"]},
                            id_unidade=id_unidade)
        return r


# ---------------------------------------------------------------------------
# O conteúdo do catálogo de origem PRODUTOS
# ---------------------------------------------------------------------------
#
# 🔑 **Pedido do dono (22/09/2026):** *"vamos adicionar a Origem Produtos. Quando
# for esta origem, ao listar os catálogos, ao clicar sobre vai abrir uma nova
# página para configuração. Neste, podemos criar Categorias e suas SubCategorias,
# cada item terá o Nome, Descrição e uma foto. Após isto, podemos vincular os
# produtos disponíveis no PDV para a subcategoria. Somente produtos ativos."*
#
# ⚠️ **Declaradas depois de `/{id_catalogo}` porque todas têm um segmento extra**
# (`/conteudo`, `/categorias`, `/itens`): o FastAPI casa rotas na ORDEM, e um
# caminho de dois segmentos nunca é lido como um id.
# ⚠️ **`/produtos-disponiveis` é a exceção e mora lá em cima, junto de
# `/opcoes`.** Ela tem um segmento só, e aqui embaixo era engolida por
# `/{id_catalogo}` — a resposta era um 422 dizendo que "produtos-disponiveis"
# não é um número inteiro. Escrito aqui como aviso e violado na linha seguinte,
# na primeira versão deste bloco.


@router.get("/{id_catalogo}/conteudo")
def ver_conteudo(id_catalogo: int, ctx: Contexto = Depends(_VER)) -> dict:
    """O cardápio inteiro, em árvore — é o que a página de configuração abre."""
    with get_cursor() as cur:
        return conteudo.montar(cur, _unidade(cur, ctx), id_catalogo)


@router.post("/{id_catalogo}/categorias", status_code=201)
def criar_categoria(id_catalogo: int, body: CategoriaCreate,
                    ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        nova = conteudo.criar_categoria(cur, id_unidade, id_catalogo, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_categoria", nova["id"],
                            "criar", depois={"nome": nova["nome"]},
                            id_unidade=id_unidade)
        return nova


@router.put("/categorias/{id_categoria}")
def atualizar_categoria(id_categoria: int, body: CategoriaCreate,
                        ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        muda = conteudo.atualizar_categoria(cur, id_unidade, id_categoria,
                                            body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_categoria", id_categoria,
                            "atualizar", depois={"nome": muda["nome"]},
                            id_unidade=id_unidade)
        return muda


@router.delete("/categorias/{id_categoria}")
def excluir_categoria(id_categoria: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Apaga a categoria — e leva subcategorias e vínculos junto.

    🔑 **A resposta diz QUANTOS produtos saíram**, para a tela poder avisar
    antes: apagar "Menu Principal" com trinta itens dentro não pode ser um
    clique sem consequência visível.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = conteudo.excluir_categoria(cur, id_unidade, id_categoria)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_categoria", id_categoria,
                            "excluir", antes={"itens": fora["itens_removidos"]},
                            id_unidade=id_unidade)
        return fora


@router.post("/categorias/{id_categoria}/subcategorias", status_code=201)
def criar_subcategoria(id_categoria: int, body: SubcategoriaCreate,
                       ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        nova = conteudo.criar_subcategoria(cur, id_unidade, id_categoria,
                                           body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_subcategoria", nova["id"],
                            "criar", depois={"nome": nova["nome"]},
                            id_unidade=id_unidade)
        return nova


@router.put("/subcategorias/{id_sub}")
def atualizar_subcategoria(id_sub: int, body: SubcategoriaCreate,
                           ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        muda = conteudo.atualizar_subcategoria(cur, id_unidade, id_sub,
                                               body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_subcategoria", id_sub,
                            "atualizar", depois={"nome": muda["nome"]},
                            id_unidade=id_unidade)
        return muda


@router.delete("/subcategorias/{id_sub}")
def excluir_subcategoria(id_sub: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = conteudo.excluir_subcategoria(cur, id_unidade, id_sub)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_subcategoria", id_sub,
                            "excluir", antes={"itens": fora["itens_removidos"]},
                            id_unidade=id_unidade)
        return fora


# --------------------------------------------------------------- a foto ----
#
# ⚠️ **Uma rota para os dois tipos de seção**, com o tipo no caminho. Duplicar
# quatro rotas para categoria e subcategoria daria oito trechos iguais onde a
# única diferença é o nome da tabela — e a próxima correção teria de ser feita
# em dois lugares, que é onde se esquece um.

_SECOES = ("categoria", "subcategoria")


def _tipo_valido(tipo: str) -> str:
    if tipo not in _SECOES:
        raise HTTPException(status_code=404, detail="Seção desconhecida.")
    return tipo


@router.post("/secoes/{tipo}/{id_secao}/foto")
async def enviar_foto_da_secao(tipo: str, id_secao: int,
                               arquivo: UploadFile = File(...),
                               ctx: Contexto = Depends(_EDITAR)) -> dict:
    """A foto da categoria ou da subcategoria.

    ⚠️ **Os bytes são lidos ANTES de pedir a conexão** — até 2 MB vindos pela
    rede com transação aberta prenderiam uma conexão do pool durante o envio.
    """
    _tipo_valido(tipo)
    dados, mime, extensao = await arquivos.ler_enviada(arquivo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posta = conteudo.guardar_foto(cur, id_unidade, tipo, id_secao, dados, mime,
                                      extensao, arquivo.filename)
        auditoria.registrar(cur, ctx.id_usuario, f"catalogo_{tipo}", id_secao,
                            "enviar_foto", depois={"foto_nome": arquivo.filename},
                            id_unidade=id_unidade)
        return posta


@router.delete("/secoes/{tipo}/{id_secao}/foto")
def remover_foto_da_secao(tipo: str, id_secao: int,
                          ctx: Contexto = Depends(_EDITAR)) -> dict:
    _tipo_valido(tipo)
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = conteudo.remover_foto(cur, id_unidade, tipo, id_secao)
        auditoria.registrar(cur, ctx.id_usuario, f"catalogo_{tipo}", id_secao,
                            "remover_foto", id_unidade=id_unidade)
        return fora


# ------------------------------------------------------- os produtos -------

@router.post("/categorias/{id_categoria}/itens", status_code=201)
def vincular_produto(id_categoria: int, body: ItemCreate,
                     ctx: Contexto = Depends(_EDITAR)) -> dict:
    """Pendura um produto na categoria — ou na subcategoria dela.

    ⚠️ **A recusa é AQUI, não só na tela**: a lista de produtos disponíveis é um
    conforto; quem garante que só entra produto ativo e vendido no PDV é o
    servidor. É a regra 4 da casa.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        posto = conteudo.vincular(cur, id_unidade, id_categoria, body.model_dump())
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_item", posto["id"],
                            "vincular", depois={"produto": posto["produto"]},
                            id_unidade=id_unidade)
        return posto


@router.delete("/itens/{id_item}")
def desvincular_produto(id_item: int, ctx: Contexto = Depends(_EDITAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        fora = conteudo.desvincular(cur, id_unidade, id_item)
        auditoria.registrar(cur, ctx.id_usuario, "catalogo_item", id_item,
                            "desvincular", id_unidade=id_unidade)
        return fora
