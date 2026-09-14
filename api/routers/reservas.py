"""Reservas — o módulo que a casa liga uma loja de cada vez.

A porta de entrada de tudo é `parametros.reservas_ligado`. Enquanto ele estiver
desligado nesta loja, o menu não mostra o módulo, a tela não abre e **estas
rotas recusam** — as três coisas, e não só a primeira.

⚠️ **A trava do servidor não é redundância da do menu.** Esconder o item do menu
é conforto; o que impede uma loja sem o módulo de ganhar configuração de reserva
é a recusa aqui. É a regra da casa desde sempre: nada de checagem só na tela.

Construído até aqui: a **configuração** (janela de funcionamento e permanência) e
o **salão** (salões, mesas, lugares e a junta entre mesas vizinhas). A regra de
disponibilidade, que consome as duas, e a reserva em si vêm depois — o estudo
está em `docs/reservas-esboco.md`.
"""

from fastapi import APIRouter, Depends, HTTPException

import auditoria
from database import get_cursor
from models.reservas import (
    ConfiguracaoReservas, MesaCreate, MesasEmLote, MesaUpdate, SalaoCreate, SalaoUpdate,
)
from seguranca import Contexto, requer_permissao, unidade_atual
from services import reservas as servico

router = APIRouter(prefix="/reservas", tags=["Reservas"])

# 🔑 **Ver, operar e configurar são três chaves** (migração 068), e a divisão
# tem razão de ser: quem atende o telefone precisa marcar e cancelar, e não
# precisa poder mudar o horário de funcionamento da casa. É a mesma divisão que
# Transferências já faz entre enviar e receber.
_CONFIGURAR = requer_permissao("reservas.configurar")


def _exige(cur, tabela: str, id_registro: int, id_unidade: int, mensagem: str) -> None:
    """A linha existe E é desta loja.

    ⚠️ **As duas coisas na mesma pergunta.** Conferir só a existência deixaria a
    filial editar a mesa da matriz mandando o `id` na URL — e o nome da tabela
    nunca vem de fora, só destas chamadas, então a interpolação é segura.
    """
    cur.execute(f"SELECT 1 FROM {tabela} WHERE id = %s AND id_unidade = %s",
                (id_registro, id_unidade))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail=mensagem)


def _recusar_nome_repetido(cur, tabela: str, id_unidade: int, nome: str,
                           id_ignorar: int | None = None) -> None:
    """Recusa ANTES de o índice único estourar.

    ⚠️ O índice já garante a unicidade — o que ele não faz é explicar. Deixar o
    banco falhar devolveria um 500 com texto de Postgres para quem só digitou
    "Mesa 01" duas vezes.
    """
    cur.execute(
        f"SELECT nome FROM {tabela} WHERE id_unidade = %s AND lower(nome) = lower(%s)"
        "   AND (%s::int IS NULL OR id <> %s)",
        (id_unidade, nome.strip(), id_ignorar, id_ignorar or 0),
    )
    achado = cur.fetchone()
    if achado:
        rotulo = "salão" if tabela == "saloes" else "mesa"
        raise HTTPException(status_code=409,
                            detail=f'Já existe {rotulo} com o nome "{achado["nome"]}".')


def _unidade(cur, ctx: Contexto) -> int:
    """A loja atual — desde que ela tenha o módulo ligado."""
    id_unidade = unidade_atual(cur, ctx)
    if not servico.ligado(cur, id_unidade):
        raise HTTPException(
            status_code=409,
            detail=("O módulo de Reservas não está ligado nesta loja. "
                    "Ligue em Administração → Lojas, no parâmetro Reservas."),
        )
    return id_unidade


@router.get("/configuracao")
def obter_configuracao(ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Horário de funcionamento e permanência desta loja.

    ⚠️ **Cria a configuração se ela ainda não existe** — o mesmo desenho
    preguiçoso de `parametros`. Loja ligada hoje, configurada amanhã.
    """
    with get_cursor() as cur:
        return servico.obter(cur, _unidade(cur, ctx))


@router.put("/configuracao")
def salvar_configuracao(body: ConfiguracaoReservas,
                        ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Grava a tela inteira de uma vez.

    ⚠️ A auditoria guarda o ANTES: mudança de horário é o tipo de coisa que
    alguém faz e ninguém lembra de ter feito, e a agenda de amanhã depende dela.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        antes = servico.obter(cur, id_unidade)
        depois = servico.salvar(cur, id_unidade, body)
        auditoria.registrar(cur, ctx.id_usuario, "reserva_config", id_unidade,
                            "atualizar", antes=antes, depois=depois)
    return depois | {"message": "Configuração de reservas salva"}


# ---------------------------------------------------------------- o salão
#
# 🔑 **Pedido do dono (14/09/2026):** *"para controle interno, ter o cadastro de
# salões, cadastro de mesas, lugares por mesas."*
#
# ⚠️ **Cada recurso com o seu endereço, e não um PUT que reescreve tudo.** A
# tentação era gravar a tela inteira de uma vez, como a configuração faz — mas
# ali as faixas de permanência não são apontadas por ninguém, e aqui a mesa vai
# ser: `reserva_mesas` nasce apontando para ela. Apagar e reinserir a cada
# gravação trocaria o `id` da mesma mesa física, e a reserva de sábado passaria
# a apontar para outra.


@router.get("/salao")
def obter_salao(ctx: Contexto = Depends(requer_permissao("reservas.ver"))) -> dict:
    """Salões, mesas, lugares e o maior grupo que a casa acomoda."""
    with get_cursor() as cur:
        return servico.salao(cur, _unidade(cur, ctx))


@router.post("/saloes", status_code=201)
def criar_salao(body: SalaoCreate, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _recusar_nome_repetido(cur, "saloes", id_unidade, body.nome)
        cur.execute(
            """INSERT INTO saloes (id_unidade, nome, ativo, ordem)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (id_unidade, body.nome.strip(), body.ativo, body.ordem),
        )
        id_salao = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "salao", id_salao, "criar",
                            depois={"nome": body.nome})
    return {"id": id_salao, "message": f"Salão {body.nome} criado"}


@router.put("/saloes/{id_salao}")
def atualizar_salao(id_salao: int, body: SalaoUpdate,
                    ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Muda nome, ordem ou liga/desliga o salão.

    🔑 **Desligar é o jeito de tirar a Varanda do inverno** sem mexer em mesa por
    mesa, e sem perder o cadastro. As mesas dele saem da disponibilidade na
    mesma hora — quem filtra é `_mesas_vivas`, que exige salão ativo.
    """
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para alterar.")
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _exige(cur, "saloes", id_salao, id_unidade, "Salão não encontrado")
        if "nome" in dados:
            _recusar_nome_repetido(cur, "saloes", id_unidade, dados["nome"], id_salao)
            dados["nome"] = dados["nome"].strip()
        sets = ", ".join(f"{c} = %s" for c in dados)
        cur.execute(f"UPDATE saloes SET {sets} WHERE id = %s AND id_unidade = %s",
                    (*dados.values(), id_salao, id_unidade))
        auditoria.registrar(cur, ctx.id_usuario, "salao", id_salao, "atualizar", depois=dados)
    return {"message": "Salão atualizado"}


@router.delete("/saloes/{id_salao}")
def excluir_salao(id_salao: int, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Só o salão VAZIO se exclui; com mesa, desliga.

    ⚠️ **Apagar um salão com mesas levaria as mesas junto** (o `ON DELETE
    CASCADE` da chave composta), e com elas a resposta para "onde aquela reserva
    de agosto sentou". Quem quer o salão fora de circulação desliga: o cadastro
    fica, a disponibilidade não o enxerga, e religar devolve tudo.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _exige(cur, "saloes", id_salao, id_unidade, "Salão não encontrado")
        cur.execute("SELECT count(*) AS n FROM mesas WHERE id_salao = %s", (id_salao,))
        quantas = cur.fetchone()["n"]
        if quantas:
            raise HTTPException(
                status_code=409,
                detail=(f"Este salão tem {quantas} mesa(s). Mova-as para outro salão ou "
                        "apenas DESLIGUE o salão — desligado, ele sai da disponibilidade "
                        "sem perder o cadastro."),
            )
        cur.execute("DELETE FROM saloes WHERE id = %s AND id_unidade = %s",
                    (id_salao, id_unidade))
        auditoria.registrar(cur, ctx.id_usuario, "salao", id_salao, "excluir")
    return {"message": "Salão excluído"}


@router.post("/mesas", status_code=201)
def criar_mesa(body: MesaCreate, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _exige(cur, "saloes", body.id_salao, id_unidade, "Salão não encontrado")
        _recusar_nome_repetido(cur, "mesas", id_unidade, body.nome)
        cur.execute(
            """INSERT INTO mesas (id_unidade, id_salao, nome, lugares, capacidade_max, ativo)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (id_unidade, body.id_salao, body.nome.strip(), body.lugares,
             body.capacidade_max, body.ativo),
        )
        id_mesa = cur.fetchone()["id"]
        auditoria.registrar(cur, ctx.id_usuario, "mesa", id_mesa, "criar",
                            depois={"nome": body.nome, "lugares": body.lugares})
    return {"id": id_mesa, "message": f"Mesa {body.nome} criada"}


@router.post("/mesas/em-lote", status_code=201)
def criar_mesas_em_lote(body: MesasEmLote, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Cria N mesas iguais de uma vez, numerando a partir do primeiro nome livre.

    🔑 **É o trabalho real do cadastro**, e acontece uma vez só: no dia em que a
    casa entra no sistema. Clicar "+ mesa" doze vezes e renomear cada uma é
    exatamente quando ninguém tem paciência — e cadastro mal feito no primeiro
    dia é o que faz a disponibilidade responder errado no segundo.

    ⚠️ **Pula os nomes já usados em vez de recusar o lote.** O nome é único por
    LOJA: pedir dez mesas num salão que já tem a 03 e a 07 devolveria um erro
    inútil ("já existe mesa 03") para quem só quis dizer "quero mais dez". Aqui
    ele procura o próximo livre e segue — a resposta diz quais nasceram.

    ⚠️ **A busca do nome livre tem teto.** Sem ele, um prefixo que colidisse com
    tudo faria o laço rodar para sempre segurando a transação — e o sintoma
    seria a tela pendurada, não um erro.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _exige(cur, "saloes", body.id_salao, id_unidade, "Salão não encontrado")

        cur.execute("SELECT lower(nome) AS n FROM mesas WHERE id_unidade = %s", (id_unidade,))
        usados = {r["n"] for r in cur.fetchall()}

        criadas: list[str] = []
        numero = 1
        teto = body.quantidade + len(usados) + 100
        while len(criadas) < body.quantidade and numero <= teto:
            nome = f"{body.prefixo.strip()}{numero:02d}"
            numero += 1
            if nome.lower() in usados:
                continue
            usados.add(nome.lower())
            cur.execute(
                """INSERT INTO mesas (id_unidade, id_salao, nome, lugares, capacidade_max)
                   VALUES (%s, %s, %s, %s, %s)""",
                (id_unidade, body.id_salao, nome, body.lugares, body.capacidade_max),
            )
            criadas.append(nome)

        if len(criadas) < body.quantidade:
            # Só acontece com prefixo que colide com tudo; melhor dizer do que
            # entregar metade calado.
            raise HTTPException(
                status_code=409,
                detail=("Não consegui achar nomes livres para todas as mesas. "
                        "Use um prefixo diferente."),
            )
        auditoria.registrar(cur, ctx.id_usuario, "mesa", body.id_salao, "criar_em_lote",
                            depois={"nomes": criadas, "lugares": body.lugares})
    return {
        "criadas": criadas,
        "message": (f"{len(criadas)} mesas criadas ({criadas[0]} a {criadas[-1]}), "
                    f"com {body.lugares} lugares cada."),
    }


@router.put("/mesas/{id_mesa}")
def atualizar_mesa(id_mesa: int, body: MesaUpdate,
                   ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Muda a mesa — e a junta, quando ela vier no corpo.

    ⚠️ **`junta_com` só é tocada se veio no corpo** (`model_fields_set`): nulo
    significa "desfaça a junta", e ausente significa "não falei dela". Sem essa
    distinção, renomear a mesa 07 soltaria a 08 sem ninguém pedir.
    """
    dados = body.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nada para alterar.")
    mexe_na_junta = "junta_com" in body.model_fields_set
    id_par = dados.pop("junta_com", None)

    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        cur.execute(
            "SELECT lugares, capacidade_max FROM mesas WHERE id = %s AND id_unidade = %s",
            (id_mesa, id_unidade),
        )
        atual = cur.fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Mesa não encontrada")
        if "id_salao" in dados:
            _exige(cur, "saloes", dados["id_salao"], id_unidade, "Salão não encontrado")
        if "nome" in dados:
            _recusar_nome_repetido(cur, "mesas", id_unidade, dados["nome"], id_mesa)
            dados["nome"] = dados["nome"].strip()

        # ⚠️ **A coerência é entre o valor NOVO e o que FICA**, não entre os dois
        # novos: quem manda só `lugares` tem de ser comparado ao máximo que já
        # está gravado, senão dá para subir os lugares acima do máximo antigo
        # sem o banco reclamar até o próximo `UPDATE`.
        lugares = dados.get("lugares", atual["lugares"])
        maximo = dados.get("capacidade_max", atual["capacidade_max"])
        if maximo < lugares:
            raise HTTPException(
                status_code=422,
                detail=(f"A capacidade máxima ({maximo}) não pode ser menor que os "
                        f"lugares ({lugares})."),
            )

        if dados:
            sets = ", ".join(f"{c} = %s" for c in dados)
            cur.execute(f"UPDATE mesas SET {sets} WHERE id = %s AND id_unidade = %s",
                        (*dados.values(), id_mesa, id_unidade))
        if mexe_na_junta:
            if id_par is not None:
                _exige(cur, "mesas", id_par, id_unidade, "A mesa da junta não existe")
                if id_par == id_mesa:
                    raise HTTPException(status_code=422,
                                        detail="Uma mesa não encosta nela mesma.")
            servico.casar_junta(cur, id_unidade, id_mesa, id_par)
        auditoria.registrar(cur, ctx.id_usuario, "mesa", id_mesa, "atualizar",
                            depois=dados | ({"junta_com": id_par} if mexe_na_junta else {}))
    return {"message": "Mesa atualizada"}


@router.delete("/mesas/{id_mesa}")
def excluir_mesa(id_mesa: int, ctx: Contexto = Depends(_CONFIGURAR)) -> dict:
    """Apaga a mesa — enquanto ninguém tiver sentado nela.

    ⚠️ **Quem vai barrar isto é o BANCO, não uma lista escrita à mão.** Quando
    `reserva_mesas` nascer, a chave estrangeira dela recusa apagar mesa que já
    hospedou reserva, e esta rota passa a devolver o erro sem ninguém ter de se
    lembrar de acrescentar a regra aqui. É a mesma escolha de `_quem_referencia`
    em `limpar_dados.py`: perguntar ao Postgres em vez de manter uma lista que
    envelhece.
    """
    with get_cursor() as cur:
        id_unidade = _unidade(cur, ctx)
        _exige(cur, "mesas", id_mesa, id_unidade, "Mesa não encontrada")
        # A junta é simétrica: soltar a vizinha ANTES evita deixá-la apontando
        # para o vazio (o `ON DELETE SET NULL` faria isso, mas depois — e o
        # `salao()` já teria devolvido a resposta velha nesta transação).
        cur.execute("UPDATE mesas SET junta_com = NULL WHERE junta_com = %s", (id_mesa,))
        cur.execute("DELETE FROM mesas WHERE id = %s AND id_unidade = %s",
                    (id_mesa, id_unidade))
        auditoria.registrar(cur, ctx.id_usuario, "mesa", id_mesa, "excluir")
    return {"message": "Mesa excluída"}
