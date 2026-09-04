"""Usuários e o vínculo deles com papéis (por loja)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

import auditoria
from database import get_cursor
from paginacao import com_total
from models.acesso import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from seguranca import Contexto, hash_senha, requer_permissao
from services import email as correio
from services import senhas

router = APIRouter(
    prefix="/usuarios",
    tags=["usuários"],
    dependencies=[Depends(requer_permissao("admin.usuarios"))],
)


def _papeis_do_usuario(cur, id_usuario: int) -> list[dict]:
    cur.execute(
        """SELECT up.id_papel, p.nome AS papel, up.id_unidade, un.nome AS unidade
             FROM usuario_papeis up
             JOIN papeis p ON p.id = up.id_papel
             LEFT JOIN unidades un ON un.id = up.id_unidade
            WHERE up.id_usuario = %s
            ORDER BY p.nome""",
        (id_usuario,),
    )
    return [dict(r) for r in cur.fetchall()]


def _setores_do_usuario(cur, id_usuario: int) -> list[dict]:
    """Os setores da pessoa. ⚠️ **Vazio quer dizer TODOS** — ver a migração 052."""
    cur.execute(
        """SELECT s.id, s.nome FROM usuario_setores us
             JOIN setores s ON s.id = us.id_setor
            WHERE us.id_usuario = %s AND s.ativo
            ORDER BY s.ordem, s.nome""",
        (id_usuario,),
    )
    return [dict(r) for r in cur.fetchall()]


def _gravar_setores(cur, id_usuario: int, setores: list[int], ctx: Contexto) -> None:
    """Grava de que parte da casa a pessoa cuida.

    ⚠️ **Lista vazia é "todos", não "nenhum"** — e é por isso que ela apaga as
    linhas sem gravar nada. Um usuário sem linha nenhuma vê a casa inteira, que
    é o padrão de quem nunca respondeu a pergunta.

    🔑 **Quem não enxerga o setor não põe ninguém nele**, pela mesma razão da
    loja: dar a outra pessoa um alcance que quem edita não tem é o caminho
    clássico para escalar acesso sem tocar em permissão. ⚠️ Com `todos_setores`
    ligado — o caso de todo administrador hoje — a trava não barra nada, e é
    isso que faz esta migração não travar a configuração inicial.

    🔑 **E ninguém encolhe o PRÓPRIO alcance.** Quem se restringisse a um setor
    perderia os outros de vista, e a trava de cima o impediria de devolvê-los a
    si mesmo. É o mesmo erro que a loja já paga, pela outra porta.
    """
    pedidos = sorted(set(setores))
    for id_setor in pedidos:
        cur.execute("SELECT nome, ativo FROM setores WHERE id = %s", (id_setor,))
        setor = cur.fetchone()
        if not setor:
            raise HTTPException(status_code=404, detail="Setor não encontrado")
        if not setor["ativo"]:
            raise HTTPException(
                status_code=400,
                detail=f"{setor['nome']} está inativo — não dá para lotar alguém nele.")
        if not ctx.ve_setor(id_setor):
            raise HTTPException(
                status_code=403,
                detail=(f"Você não cuida de {setor['nome']}, então não pode "
                        "colocar ninguém nele."))

    if id_usuario == ctx.id_usuario and pedidos:
        # Sem `todos_setores`, o conjunto novo tem de conter o atual: encolher o
        # próprio alcance deixa a pessoa sem como voltar.
        if ctx.todos_setores or not ctx.setores.issubset(set(pedidos)):
            raise HTTPException(
                status_code=400,
                detail=("Você não pode reduzir os seus próprios setores — ficaria sem "
                        "como voltar atrás. Peça a outro administrador."))

    cur.execute("DELETE FROM usuario_setores WHERE id_usuario = %s", (id_usuario,))
    for id_setor in pedidos:
        cur.execute(
            """INSERT INTO usuario_setores (id_usuario, id_setor)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (id_usuario, id_setor),
        )


def _resolver_pessoa(cur, body, id_usuario: int | None, ctx: Contexto) -> int | None | str:
    """Qual pessoa este usuário é. Devolve o id, `None`, ou "nao mexer".

    🔑 **Duas portas, nunca as duas ao mesmo tempo**: vincular uma pessoa que já
    existe (`id_pessoa`) ou criar uma ali mesmo com nome e e-mail
    (`pessoa_nova`). Mandar os dois é ambíguo — qual delas vale? — e a resposta
    honesta é recusar em vez de escolher por quem pediu.

    ⚠️ **A pessoa criada daqui NÃO nasce fornecedor.** Quem cadastra um usuário
    está cadastrando gente da casa, não quem vende para ela: marcá-la faria o
    seletor de fornecedor da nota encher de funcionários. Quem for as duas
    coisas marca a caixa depois, na tela de Pessoas.

    ⚠️ **`id_pessoa: 0` DESVINCULA.** Nulo já quer dizer "não mexi" no PUT, e
    sem um valor para "tire o vínculo" não haveria como desfazer — só trocar.
    """
    tem_nova = getattr(body, "pessoa_nova", None) is not None
    tem_id = getattr(body, "id_pessoa", None) is not None
    if tem_nova and tem_id:
        raise HTTPException(
            status_code=400,
            detail="Escolha uma pessoa existente OU crie uma nova — não os dois.")

    if tem_nova:
        cur.execute(
            """INSERT INTO fornecedores (nome, email, fornecedor, ativo, criado_por)
               VALUES (%s, %s, false, true, %s) RETURNING id""",
            (body.pessoa_nova.nome.strip(), body.pessoa_nova.email, ctx.id_usuario),
        )
        return cur.fetchone()["id"]

    if not tem_id:
        return "nao mexer"
    if body.id_pessoa == 0:
        return None

    cur.execute("SELECT nome, ativo FROM fornecedores WHERE id = %s", (body.id_pessoa,))
    pessoa = cur.fetchone()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if not pessoa["ativo"]:
        raise HTTPException(
            status_code=400,
            detail=f"{pessoa['nome']} está inativa — reative antes de vincular.")
    # ⚠️ Uma pessoa, um usuário. Dois logins apontando para a mesma pessoa
    # fariam a política de cupom dela responder por duas credenciais, e ninguém
    # saberia qual das duas comprou.
    cur.execute(
        "SELECT nome FROM usuarios WHERE id_pessoa = %s AND id <> coalesce(%s, 0) AND ativo",
        (body.id_pessoa, id_usuario),
    )
    outro = cur.fetchone()
    if outro:
        raise HTTPException(
            status_code=409,
            detail=f"{pessoa['nome']} já está vinculada ao usuário {outro['nome']}.")
    return body.id_pessoa


def _conferir_lojas(cur, papeis, ctx: Contexto) -> None:
    """Só se dá acesso a loja que EXISTE e que quem está dando enxerga.

    ⚠️ `id_unidade` nulo quer dizer **todas** — é o padrão de quem trabalha numa
    casa só, e continua sendo o que a tela manda quando não há filial.
    🔑 **Quem não enxerga a loja não põe ninguém dentro dela.** Sem esta trava,
    um gerente escopado à filial poderia criar um usuário com acesso à matriz —
    dando a outra pessoa um alcance que ele mesmo não tem, que é o caminho
    clássico para escalar privilégio sem tocar em permissão nenhuma.
    ⚠️ E loja inexistente estouraria na chave estrangeira, como 500: a frase
    aqui diz o que aconteceu.
    """
    for id_unidade in {v.id_unidade for v in papeis if v.id_unidade is not None}:
        cur.execute("SELECT nome, ativo FROM unidades WHERE id = %s", (id_unidade,))
        loja = cur.fetchone()
        if not loja:
            raise HTTPException(status_code=404, detail="Loja não encontrada")
        if not loja["ativo"]:
            raise HTTPException(
                status_code=400,
                detail=f"{loja['nome']} está inativa — não dá para lotar alguém nela.")
        if not ctx.ve_unidade(id_unidade):
            raise HTTPException(
                status_code=403,
                detail=f"Você não tem acesso a {loja['nome']}, então não pode dá-lo a ninguém.")


def _nao_encolher_o_proprio_alcance(id_usuario: int, papeis, ctx: Contexto) -> None:
    """Ninguém se tranca para fora sozinho.

    🔑 **Quem se restringe fica sem como voltar.** Um administrador que se
    lotasse só na filial perderia a matriz de vista — e a trava de cima o
    impediria de devolvê-la a si mesmo, porque ele já não a enxerga. Não é
    hipótese: é o primeiro erro de quem está configurando as lojas e testa em
    si. Mesma regra do `PUT /auth/me`, onde papel e loja ficam de fora.
    ⚠️ Aumentar o próprio alcance também não passa — quem confere isso é a trava
    de cima, e a mensagem daqui só fala do encolhimento.
    """
    if id_usuario != ctx.id_usuario:
        return
    novas = {v.id_unidade for v in papeis}
    if None in novas:
        return   # continua valendo em todas: não encolheu
    if ctx.todas_unidades or not ctx.unidades.issubset(novas):
        raise HTTPException(
            status_code=400,
            detail=("Você não pode reduzir as suas próprias lojas — ficaria sem como "
                    "voltar atrás. Peça a outro administrador."))


def _gravar_papeis(cur, id_usuario: int, papeis, ctx: Contexto) -> None:
    _conferir_lojas(cur, papeis, ctx)
    _nao_encolher_o_proprio_alcance(id_usuario, papeis, ctx)
    cur.execute("DELETE FROM usuario_papeis WHERE id_usuario = %s", (id_usuario,))
    for v in papeis:
        cur.execute(
            """INSERT INTO usuario_papeis (id_usuario, id_papel, id_unidade)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (id_usuario, v.id_papel, v.id_unidade),
        )


@router.get("", response_model=list[UsuarioResponse])
def listar(incluir_inativos: bool = False,
           limite: int = Query(default=100, ge=1, le=500),
           offset: int = Query(default=0, ge=0),
           resposta: Response = None) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, email, telefone, ativo, ultimo_acesso, id_pessoa,
                      (SELECT f.nome FROM fornecedores f WHERE f.id = usuarios.id_pessoa)
                          AS pessoa,
                      (bloqueado_ate IS NOT NULL AND bloqueado_ate > now()) AS bloqueado,
                      count(*) OVER () AS _total
                 FROM usuarios
                WHERE (%s OR ativo)
                ORDER BY ativo DESC, nome
                LIMIT %s OFFSET %s""",
            (incluir_inativos, limite, offset),
        )
        usuarios = [dict(r) for r in cur.fetchall()]
        com_total(usuarios, resposta, offset)
        for u in usuarios:
            u["papeis"] = _papeis_do_usuario(cur, u["id"])
            u["setores"] = _setores_do_usuario(cur, u["id"])
    return usuarios


@router.get("/{id_usuario}", response_model=UsuarioResponse)
def obter(id_usuario: int) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, nome, email, telefone, ativo, ultimo_acesso, id_pessoa,
                      (SELECT f.nome FROM fornecedores f WHERE f.id = usuarios.id_pessoa)
                          AS pessoa,
                      (bloqueado_ate IS NOT NULL AND bloqueado_ate > now()) AS bloqueado,
                      count(*) OVER () AS _total
                 FROM usuarios WHERE id = %s""",
            (id_usuario,),
        )
        u = cur.fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        u = dict(u)
        u["papeis"] = _papeis_do_usuario(cur, id_usuario)
        u["setores"] = _setores_do_usuario(cur, id_usuario)
    return u


@router.post("", status_code=201)
def criar(body: UsuarioCreate, request: Request,
          ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    email = body.email.strip().lower()
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM usuarios WHERE lower(email) = %s", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Já existe usuário com este e-mail")
        cur.execute(
            """INSERT INTO usuarios (nome, email, senha_hash, telefone, ativo,
                                     trocar_senha, criado_por)
               VALUES (%s, %s, %s, %s, %s, true, %s) RETURNING id""",
            (body.nome.strip(), email, hash_senha(body.senha), body.telefone,
             body.ativo, ctx.id_usuario),
        )
        novo = cur.fetchone()["id"]
        pessoa = _resolver_pessoa(cur, body, novo, ctx)
        if pessoa != "nao mexer":
            cur.execute("UPDATE usuarios SET id_pessoa = %s WHERE id = %s", (pessoa, novo))
        _gravar_papeis(cur, novo, body.papeis, ctx)
        _gravar_setores(cur, novo, body.setores, ctx)
        auditoria.registrar(
            cur, ctx.id_usuario, "usuario", novo, "criar",
            depois={"nome": body.nome, "email": email, "ativo": body.ativo},
            ip=request.client.host if request.client else None,
        )
    return {"id": novo, "message": "Usuário criado"}


@router.put("/{id_usuario}")
def atualizar(id_usuario: int, body: UsuarioUpdate, request: Request,
              ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, nome, email, telefone, ativo FROM usuarios WHERE id = %s",
            (id_usuario,),
        )
        antes = cur.fetchone()
        if not antes:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        campos, valores = [], []
        for campo in ("nome", "telefone", "ativo"):
            valor = getattr(body, campo)
            if valor is not None:
                campos.append(f"{campo} = %s")
                valores.append(valor)
        if body.email:
            email = body.email.strip().lower()
            cur.execute(
                "SELECT 1 FROM usuarios WHERE lower(email) = %s AND id <> %s",
                (email, id_usuario),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="E-mail já usado por outro usuário")
            campos.append("email = %s")
            valores.append(email)
        if body.senha:
            campos.append("senha_hash = %s")
            valores.append(hash_senha(body.senha))
            campos.append("trocar_senha = true")

        if campos:
            valores.append(id_usuario)
            cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = %s", valores)

        # Desativar derruba as sessões abertas na hora.
        if body.ativo is False:
            cur.execute(
                """UPDATE sessoes SET revogada_em = now()
                    WHERE id_usuario = %s AND revogada_em IS NULL""",
                (id_usuario,),
            )
        if body.papeis is not None:
            _gravar_papeis(cur, id_usuario, body.papeis, ctx)
        # ⚠️ `is not None`, nunca `if body.setores`: lista vazia é a escolha
        # explícita de "todos os setores" e precisa apagar as linhas. Testar a
        # verdade do valor confundiria "não mexi" com "liberei tudo".
        if body.setores is not None:
            _gravar_setores(cur, id_usuario, body.setores, ctx)
        pessoa = _resolver_pessoa(cur, body, id_usuario, ctx)
        if pessoa != "nao mexer":
            cur.execute("UPDATE usuarios SET id_pessoa = %s WHERE id = %s",
                        (pessoa, id_usuario))

        auditoria.registrar(
            cur, ctx.id_usuario, "usuario", id_usuario, "atualizar",
            antes=dict(antes), depois=body.model_dump(exclude_none=True),
            ip=request.client.host if request.client else None,
        )
    return {"id": id_usuario, "message": "Usuário atualizado"}


@router.post("/{id_usuario}/recuperar-senha")
def recuperar_senha(id_usuario: int, request: Request,
                    ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    """Manda o e-mail de recuperação para o usuário — e devolve o link.

    O link volta na resposta de propósito, e só aqui: enquanto não houver SMTP
    configurado, é assim que o dono resolve o "esqueci minha senha" da equipe —
    lê o link e passa pelo WhatsApp. Continua valendo meia hora e um uso só, o
    que é bem melhor que ele escolher uma senha nova pela pessoa e mandar a
    senha por mensagem.
    """
    with get_cursor() as cur:
        cur.execute("SELECT nome, email, ativo FROM usuarios WHERE id = %s", (id_usuario,))
        u = cur.fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        if not u["ativo"]:
            raise HTTPException(status_code=400, detail="Usuário inativo")

        try:
            envio = senhas.enviar_link(
                cur, {"id": id_usuario, "nome": u["nome"], "email": u["email"]},
                request.client.host if request.client else None, origem="ADMIN",
            )
        except correio.ErroEmail as e:
            raise HTTPException(status_code=502, detail=e.mensagem)
        auditoria.registrar(cur, ctx.id_usuario, "senha", id_usuario, "recuperacao_pelo_admin",
                            depois={"modo": envio["modo"]})

    return {
        "link": envio["link"],
        "modo": envio["modo"],
        "message": (f"E-mail enviado para {u['email']}." if envio["modo"] == "real"
                    else "Sem SMTP configurado: passe o link abaixo para a pessoa."),
    }


@router.post("/{id_usuario}/desbloquear")
def desbloquear(id_usuario: int,
                ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET bloqueado_ate = NULL, tentativas_login = 0 WHERE id = %s",
            (id_usuario,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "usuario", id_usuario, "desbloquear")
    return {"message": "Usuário desbloqueado"}


@router.delete("/{id_usuario}")
def desativar(id_usuario: int,
              ctx: Contexto = Depends(requer_permissao("admin.usuarios"))) -> dict:
    """Nunca apaga: desativa. Usuário apagado levaria a auditoria junto."""
    if id_usuario == ctx.id_usuario:
        raise HTTPException(status_code=400, detail="Você não pode desativar a si mesmo")
    with get_cursor() as cur:
        cur.execute("UPDATE usuarios SET ativo = false WHERE id = %s", (id_usuario,))
        cur.execute(
            "UPDATE sessoes SET revogada_em = now() WHERE id_usuario = %s AND revogada_em IS NULL",
            (id_usuario,),
        )
        auditoria.registrar(cur, ctx.id_usuario, "usuario", id_usuario, "desativar")
    return {"message": "Usuário desativado"}
