"""Catálogos — o cabeçalho do que a casa publica para o cliente.

🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de catálogos.
Onde teremos o cabeçalho do catálogo, origem — neste momento somente vamos ter
PDF —, o nome dele no site do cliente, o período de publicação, a situação:
rascunho, ativo, inativo."*

🔑 **PDF, não PDV**, e **o catálogo pertence a RESERVAS** (correção do dono no
mesmo dia): a origem é um arquivo PDF importado, apresentado no **site de
reservas**. O módulo inteiro passa pela porta de `parametros.reservas_ligado` —
desligado, o catálogo não existe.

⚠️ **É a CAPA, e só ela.** Os itens do catálogo são a próxima fatia. Esta aqui
existe para que a capa possa ser criada, nomeada e publicada antes de alguém
decidir como o item se liga ao produto — decisão que fica melhor depois de a
capa existir.

🔑 **De cada LOJA** (decisão do dono). Toda consulta filtra `id_unidade`, e é
essa linha que impede a filial de ver — e pior, de alterar — o cardápio da
matriz. É a mesma lição que o fechamento do CMV pagou caro: `listar_fechamentos`
não filtrava a loja, e reabrir de fora devolvia 200.

⚠️ **Vários ATIVOS são permitidos** (decisão do dono: *"vários, sem trava
nenhuma"*). O cadastro não escolhe entre eles; quem publicar no site vai
precisar de uma regra que escolha, e ela é da fatia do site.
"""

from datetime import date

from fastapi import HTTPException

import arquivos

from models.catalogos import ORIGEM_PRODUTOS, ORIGENS, SITUACOES

# As colunas que a tela lê, num lugar só: a lista e o registro têm de mostrar o
# mesmo catálogo, e duas listas de campos divergem na primeira coluna nova.
_CAMPOS = """c.id, c.nome, c.origem, c.publica_de, c.publica_ate, c.situacao,
             c.observacao, u.nome AS criado_por,
             c.arquivo_url, c.arquivo_nome, c.arquivo_bytes, c.arquivo_em"""


def _publicado_hoje(linha: dict, hoje: date) -> bool:
    """Está no ar AGORA? Não é o mesmo que estar ativo.

    🔑 **É a pergunta que a lista responde de relance.** Um catálogo ATIVO cujo
    período terminou ontem não está publicado — e mostrá-lo igual ao que está no
    ar faria a casa procurar no site um cardápio que saiu sozinho.
    ⚠️ **Ponta nula é "sem limite" daquele lado**, não "hoje": sem `publica_de`
    vale desde sempre, sem `publica_ate` vale sem prazo.
    """
    if linha["situacao"] != "ATIVO":
        return False
    if linha["publica_de"] and linha["publica_de"] > hoje:
        return False
    if linha["publica_ate"] and linha["publica_ate"] < hoje:
        return False
    return True


def _com_publicado(linhas: list[dict]) -> list[dict]:
    hoje = date.today()
    return [{**l, "publicado_hoje": _publicado_hoje(l, hoje)} for l in linhas]


def guardar_arquivo(cur, id_unidade: int, id_catalogo: int, conteudo: bytes,
                    tipo: str, extensao: str, nome_original: str | None) -> dict:
    """Guarda o PDF do catálogo e aponta para ele. Tudo numa transação.

    🔑 **Pedido do dono (21/09/2026):** *"criei o catálogo, agora tenho que
    poder carregar o PDF, neste caso para ele ser exibido."*

    ⚠️ **Gravar o novo, apontar para ele e apagar o velho são UMA coisa só.** É
    a lição que a logo pagou: a versão antiga gravava numa transação e apagava
    noutra, e um erro no meio deixava o registro apontando para um arquivo que
    já não existia — o link quebrava e nada explicava. Aqui as três acontecem
    no mesmo cursor, ou nenhuma acontece.
    """
    atual = obter(cur, id_unidade, id_catalogo)
    # 🔑 **Pedido do dono (22/09/2026):** *"quando for PRODUTO, tirar o campo
    # para carregar PDF."* A tela esconde o botão; esta recusa é o que GARANTE —
    # tela é conforto, e um PDF pendurado num catálogo que o site nunca lê é um
    # arquivo que ninguém sabe que existe.
    if atual.get("origem") == ORIGEM_PRODUTOS:
        raise HTTPException(
            status_code=409,
            detail=(f'"{atual["nome"]}" é um cardápio montado por produtos, e não '
                    "exibe PDF. Monte as categorias na tela do catálogo."),
        )
    antigo = atual.get("arquivo_url")

    url = arquivos.gravar(cur, conteudo, tipo, extensao, f"catalogo-{id_catalogo}")
    cur.execute(
        """UPDATE catalogos
              SET arquivo_url = %s, arquivo_nome = %s, arquivo_bytes = %s,
                  arquivo_em = now(), atualizado_em = now()
            WHERE id = %s AND id_unidade = %s""",
        (url, (nome_original or "").strip()[:255] or None, len(conteudo),
         id_catalogo, id_unidade),
    )
    # ⚠️ **Depois de o registro já apontar para o novo**, e no mesmo cursor.
    arquivos.remover(antigo, cur)
    return obter(cur, id_unidade, id_catalogo)


def remover_arquivo(cur, id_unidade: int, id_catalogo: int) -> dict:
    """Tira o PDF do catálogo — o cadastro continua, sem arquivo.

    ⚠️ **Não é o mesmo que excluir o catálogo.** Trocar o cardápio por outro é
    rotina; apagar a capa junto perderia o nome, o período e o histórico.
    """
    atual = obter(cur, id_unidade, id_catalogo)
    if not atual.get("arquivo_url"):
        raise HTTPException(status_code=409,
                            detail="Este catálogo não tem arquivo para remover.")
    cur.execute(
        """UPDATE catalogos
              SET arquivo_url = NULL, arquivo_nome = NULL, arquivo_bytes = NULL,
                  arquivo_em = NULL, atualizado_em = now()
            WHERE id = %s AND id_unidade = %s""",
        (id_catalogo, id_unidade),
    )
    arquivos.remover(atual["arquivo_url"], cur)
    return obter(cur, id_unidade, id_catalogo)


def listar(cur, id_unidade: int, situacao: str | None = None) -> list[dict]:
    """Os catálogos DESTA loja.

    ⚠️ **A ordem é a de quem procura, não a do banco.** Primeiro o que está no
    ar, depois o que vai entrar, e os inativos por último — quem abre a tela
    quer ver o cardápio de hoje, não o mais recente por id.
    """
    if situacao and situacao not in SITUACOES:
        raise HTTPException(
            status_code=422,
            detail=f"Situação desconhecida: {situacao}. As que existem: "
                   f"{', '.join(SITUACOES)}.")
    cur.execute(
        f"""SELECT {_CAMPOS}
              FROM catalogos c
              LEFT JOIN usuarios u ON u.id = c.criado_por
             WHERE c.id_unidade = %s
               AND (%s::varchar IS NULL OR c.situacao = %s)
             ORDER BY CASE c.situacao
                          WHEN 'ATIVO' THEN 0 WHEN 'RASCUNHO' THEN 1 ELSE 2 END,
                      c.publica_de NULLS FIRST, lower(c.nome)""",
        (id_unidade, situacao, situacao),
    )
    return _com_publicado([dict(r) for r in cur.fetchall()])


def obter(cur, id_unidade: int, id_catalogo: int) -> dict:
    """Um catálogo da loja atual.

    ⚠️ **404 de fora da loja, nunca 403.** 403 confirmaria que aquele número
    existe noutra casa — é a mesma escolha que `reabrir` do CMV passou a fazer.
    """
    cur.execute(
        f"""SELECT {_CAMPOS}
              FROM catalogos c
              LEFT JOIN usuarios u ON u.id = c.criado_por
             WHERE c.id = %s AND c.id_unidade = %s""",
        (id_catalogo, id_unidade),
    )
    linha = cur.fetchone()
    if not linha:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
    return _com_publicado([dict(linha)])[0]


def _recusar_nome_repetido(cur, id_unidade: int, nome: str,
                           ignorar: int | None = None) -> None:
    """A frase em português para o que o índice único já garante.

    ⚠️ **Quem GARANTE é o banco; quem EXPLICA é isto.** A pergunta antes não
    substitui `ux_catalogo_nome` — é ele que não envelhece sob concorrência —,
    acrescenta a frase. É a mesma divisão que `mesas` pagou com um 500 e texto
    de Postgres na cara do usuário.
    """
    # ⚠️ **Traz o nome GRAVADO, não repete o digitado.** O índice ignora a
    # caixa: quem tenta "cardapio PERMANENTE" e lê "já existe um chamado
    # cardapio PERMANENTE" vai procurar esse nome na lista e não achar — lá
    # está "Cardápio permanente". A frase tem de apontar para o que a pessoa
    # consegue encontrar.
    cur.execute(
        """SELECT id, nome, situacao FROM catalogos
            WHERE id_unidade = %s AND lower(nome) = lower(%s)
              AND (%s::int IS NULL OR id <> %s)""",
        (id_unidade, nome.strip(), ignorar, ignorar),
    )
    achado = cur.fetchone()
    if achado:
        raise HTTPException(
            status_code=409,
            detail=(f"Esta loja já tem um catálogo chamado “{achado['nome']}” "
                    f"({achado['situacao'].lower()}) — o nome não diferencia maiúscula de "
                    f"minúscula. Dois com o mesmo nome são o mesmo catálogo cadastrado "
                    f"duas vezes, e quem for publicar escolhe um dos dois sem saber qual."),
        )


def criar(cur, id_unidade: int, dados: dict, id_usuario: int | None) -> dict:
    """⚠️ Nasce RASCUNHO quando ninguém disse o contrário — ver a migração."""
    nome = (dados.get("nome") or "").strip()
    _recusar_nome_repetido(cur, id_unidade, nome)
    cur.execute(
        """INSERT INTO catalogos
               (id_unidade, nome, origem, publica_de, publica_ate, situacao,
                observacao, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (id_unidade, nome, dados.get("origem") or "PDF",
         dados.get("publica_de"), dados.get("publica_ate"),
         dados.get("situacao") or "RASCUNHO",
         (dados.get("observacao") or "").strip() or None, id_usuario),
    )
    return obter(cur, id_unidade, cur.fetchone()["id"])


def atualizar(cur, id_unidade: int, id_catalogo: int, dados: dict) -> dict:
    """Salva o que veio, e só o que veio.

    ⚠️ **Campo ausente NÃO é campo nulo.** A tela manda o que mudou; tratar o
    ausente como `None` apagaria o período de quem só mexeu na situação. Por
    isso o `exclude_unset` do router e o laço sobre as chaves recebidas.
    ⚠️ **`publica_de`/`publica_ate` aceitam nulo de propósito** — limpar a data é
    uma edição legítima ("passa a valer sem prazo"), então elas entram pelo que
    ESTÁ no dicionário, não pelo que é diferente de nulo.
    """
    atual = obter(cur, id_unidade, id_catalogo)

    if "nome" in dados and dados["nome"] is not None:
        _recusar_nome_repetido(cur, id_unidade, dados["nome"], ignorar=id_catalogo)

    # ⚠️ **Trocar de PDF para PRODUTOS com arquivo carregado deixaria o PDF
    # ÓRFÃO**: ele continuaria no banco, apontado por um catálogo cuja tela não
    # mostra mais o campo — ninguém saberia que está lá para tirá-lo. A recusa
    # diz o caminho, que é curto: tirar o PDF primeiro.
    if dados.get("origem") == ORIGEM_PRODUTOS:
        de_antes = obter(cur, id_unidade, id_catalogo)
        if de_antes.get("arquivo_url"):
            raise HTTPException(
                status_code=409,
                detail=("Tire o PDF antes de mudar a origem para PRODUTOS — senão "
                        "ele fica no sistema sem tela nenhuma para removê-lo."),
            )

    if "origem" in dados and dados["origem"] not in (None, *ORIGENS):
        raise HTTPException(
            status_code=422,
            detail=f"Origem desconhecida: {dados['origem']}. "
                   f"Por enquanto só existe {', '.join(ORIGENS)}.")
    if "situacao" in dados and dados["situacao"] not in (None, *SITUACOES):
        raise HTTPException(
            status_code=422,
            detail=f"Situação desconhecida: {dados['situacao']}. "
                   f"As que existem: {', '.join(SITUACOES)}.")

    # ⚠️ **O período se valida com o que FICA, não com o que veio.** Mandar só
    # `publica_ate` numa edição precisa ser comparado com o `publica_de` que já
    # está gravado — senão dá para inverter o período em duas gravações.
    de = dados["publica_de"] if "publica_de" in dados else atual["publica_de"]
    ate = dados["publica_ate"] if "publica_ate" in dados else atual["publica_ate"]
    if de and ate and ate < de:
        raise HTTPException(
            status_code=422,
            detail="O fim da publicação não pode ser antes do começo — o catálogo "
                   "sairia do ar antes de entrar.")

    campos, valores = [], []
    for campo in ("nome", "origem", "publica_de", "publica_ate", "situacao", "observacao"):
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo in ("nome", "origem", "situacao") and valor is None:
            # Estes três não têm "vazio": deixar nulo derrubaria o NOT NULL, e a
            # mensagem do banco não diria nada a quem está na tela.
            continue
        if isinstance(valor, str):
            valor = valor.strip() or (None if campo == "observacao" else valor)
        campos.append(f"{campo} = %s")
        valores.append(valor)

    if campos:
        cur.execute(
            f"UPDATE catalogos SET {', '.join(campos)}, atualizado_em = now() "
            f" WHERE id = %s AND id_unidade = %s",
            (*valores, id_catalogo, id_unidade),
        )
    return obter(cur, id_unidade, id_catalogo)


def excluir(cur, id_unidade: int, id_catalogo: int) -> dict:
    """Apaga o catálogo — e só enquanto ele é RASCUNHO.

    🔑 **Catálogo que já esteve no ar não se apaga, se INATIVA.** Alguém leu
    aquele cardápio; apagá-lo tira do sistema o que a casa publicou, e é o tipo
    de coisa de que se sente falta meses depois, quando um cliente pergunta pelo
    prato que viu. A situação `INATIVO` existe exatamente para isso.
    """
    atual = obter(cur, id_unidade, id_catalogo)
    if atual["situacao"] != "RASCUNHO":
        raise HTTPException(
            status_code=409,
            detail=(f"Só rascunho se apaga, e este está {atual['situacao'].lower()}. "
                    f"Um catálogo que já esteve no ar é o que a casa publicou — "
                    f"deixe-o INATIVO em vez de apagar."),
        )
    cur.execute("DELETE FROM catalogos WHERE id = %s AND id_unidade = %s",
                (id_catalogo, id_unidade))
    # ⚠️ **O arquivo vai junto.** Sem isto os bytes do PDF ficariam no banco
    # sem dono nenhum apontando para eles — invisíveis, e crescendo.
    arquivos.remover(atual.get("arquivo_url"), cur)
    return {"message": f"Catálogo “{atual['nome']}” excluído."}
