"""Quem reserva pelo site: achar pelo telefone, cadastrar, e conter abuso.

🔑 **Pedido do dono (21/09/2026):** *"para a realização de reserva, precisamos de
um cadastro simples do usuário. Clica em Reserve sua Mesa, abre uma tela com o
número do telefone; caso não tenha cadastrada, realiza o cadastro com Nome,
telefone, gênero e cidade."*

⚠️ **Este é o primeiro lugar do sistema onde a INTERNET grava.** Todo o resto do
que o público alcança (`routers/publico.py`) só lê o que a casa já publicou. Uma
rota que cria registro muda o problema: não basta cuidar do que sai, é preciso
cuidar de quanto entra. É o item que o esboço de Reservas deixou anotado como
pendência desde o começo — *"conter abuso: uma rota pública que CRIA registro
precisa de limite por telefone e por origem, senão o salão amanhece lotado de
reservas que ninguém fez."*
"""

import hashlib
import re
import unicodedata

from datetime import date

from fastapi import HTTPException

from relogio import hoje_da_casa

GENEROS = ("FEMININO", "MASCULINO", "OUTRO", "NAO_INFORMADO")

# 🔑 **Os dois limites respondem a ataques diferentes**, e por isso são dois.
# O do telefone contém quem usa o site como devia e exagera (ou quem marca em
# todos os horários "para decidir depois"); o da origem contém o roteiro que
# inventa um telefone novo a cada requisição, para quem o primeiro limite não
# existe.
RESERVAS_ATIVAS_POR_TELEFONE = 3

_NOME_NAO_CONFERE = ("Já temos um cadastro neste telefone, mas o nome não confere. "
                     "Confira como você se cadastrou, ou fale com a casa.")
TENTATIVAS_POR_HORA = 20


def so_digitos(v: str | None) -> str:
    """O telefone como ele é guardado: só números.

    ⚠️ **Normalizar é o que faz o cadastro ser ACHADO.** "(47) 99910-5033" e
    "47999105033" são a mesma pessoa; guardar como veio faria a pessoa se
    recadastrar a cada reserva, e a casa ficaria com três fichas dela — cada uma
    com parte do histórico.
    """
    return "".join(c for c in str(v or "") if c.isdigit())


def telefone_valido(telefone: str) -> str:
    """O telefone aparado, ou 422 dizendo o que falta.

    ⚠️ **Dez ou onze dígitos**, que é DDD + número no Brasil. Aceitar menos deixa
    entrar engano de digitação que a casa só descobre ao ligar; aceitar muito
    mais deixa entrar lixo de roteiro.
    """
    d = so_digitos(telefone)
    if not 10 <= len(d) <= 13:
        raise HTTPException(
            status_code=422,
            detail="Confira o telefone: precisa do DDD e do número, como (47) 99910-5033.",
        )
    return d


def _sem_acento(s: str) -> str:
    sem = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in sem if not unicodedata.combining(c))


def _primeiro_nome(nome: str) -> str:
    limpo = re.sub(r"\s+", " ", _sem_acento(nome or "").strip().lower())
    return limpo.split(" ")[0] if limpo else ""


def dica_do_nome(nome: str) -> str:
    """O nome mascarado: primeira letra de cada parte, como "M••• S•••".

    🔑 **Decisão do dono (21/09/2026)**, entre mostrar o nome e confirmá-lo: a
    tela CONFIRMA, não revela.
    ⚠️ **Sem isto o site vira uma consulta aberta de telefone→nome.** A rota não
    tem login nenhum na frente: quem quisesse bastaria digitar números em
    sequência e colher o dono de cada um. A dica é o suficiente para a pessoa
    reconhecer o próprio cadastro e insuficiente para alguém descobrir o alheio.
    """
    partes = [p for p in re.split(r"\s+", (nome or "").strip()) if p]
    return " ".join(p[0].upper() + "•" * max(len(p) - 1, 1) for p in partes[:3])


# 🔑 **O cliente é da CASA, não da loja** (migração 087, pedido do dono 24/09/2026:
# *"o cadastro de cliente seria o mesmo"*). As buscas daqui são só pelo telefone;
# `id_unidade` continua nos parâmetros porque é a loja onde um cadastro NOVO nasce
# — e é por loja que continuam o limite de reservas e as tentativas.
def procurar(cur, id_unidade: int, telefone: str) -> dict:
    """Existe cadastro para este telefone? Sem dizer de quem é.

    ⚠️ **A resposta é a MESMA forma nos dois casos** (um booleano e uma dica que
    pode ser nula). Uma resposta 404 para telefone desconhecido e 200 para
    conhecido diria a mesma coisa que mostrar o nome, só que pelo código de
    status.
    """
    cur.execute(
        """SELECT nome FROM reserva_clientes
            WHERE telefone = %s""",
        (telefone,),
    )
    achado = cur.fetchone()
    return {
        "cadastrado": bool(achado),
        "dica": dica_do_nome(achado["nome"]) if achado else None,
        # 🔑 **O primeiro nome, para o site cumprimentar** (24/09/2026). Com a
        # identificação só pelo telefone, é o que diz à pessoa "é você mesmo".
        # ⚠️ Só o PRIMEIRO: o sobrenome não ajuda a saudação e completaria a
        # consulta telefone→pessoa que a dica existia para evitar.
        "nome": _primeiro_nome_exibido(achado["nome"]) if achado else None,
    }


def _primeiro_nome_exibido(nome: str) -> str:
    partes = (nome or "").strip().split()
    return partes[0].capitalize() if partes else ""


def conferir(cur, id_unidade: int, telefone: str, nome: str | None = None) -> dict | None:
    """O cadastro deste telefone. Sem cadastro, None.

    🔑 **O telefone basta** (pedido do dono, 24/09/2026). O nome, SE vier, ainda é
    conferido — mandar um nome errado continua sendo recusado.

    ⚠️ **Nome que não confere é 409, com a MESMA frase de `resolver`** — é a
    mesma prova, e duas frases para ela ensinariam qual das portas é mais frouxa.
    """
    cur.execute(
        """SELECT id, nome FROM reserva_clientes
            WHERE telefone = %s""",
        (telefone,),
    )
    achado = cur.fetchone()
    if not achado:
        return None
    if nome and _primeiro_nome(nome) != _primeiro_nome(achado["nome"]):
        raise HTTPException(status_code=409, detail=_NOME_NAO_CONFERE)
    return dict(achado)


def marcar_tentativa(cur, id_unidade: int, origem: str | None) -> None:
    """Conta mais uma batida nesta porta, e recusa quando passa do limite.

    ⚠️ **O que se guarda é o HASH da origem.** Contar quantas vieram do mesmo
    lugar não exige saber qual lugar é, e endereço de visitante é dado pessoal
    que a casa não tem por que acumular.
    ⚠️ **Sem origem identificável, a contagem cai num balde só** (`"?"`): um
    proxy que esconde todo mundo faz o limite ficar mais apertado para todos, e
    isso é melhor do que não ter limite nenhum.
    """
    marca = hashlib.sha256((origem or "?").encode()).hexdigest() if origem else "?"
    cur.execute(
        """SELECT count(*) AS n FROM reserva_tentativas
            WHERE id_unidade = %s AND origem = %s AND em > now() - interval '1 hour'""",
        (id_unidade, marca),
    )
    if cur.fetchone()["n"] >= TENTATIVAS_POR_HORA:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas em pouco tempo. Tente de novo daqui a pouco.",
        )
    cur.execute(
        "INSERT INTO reserva_tentativas (id_unidade, origem) VALUES (%s, %s)",
        (id_unidade, marca),
    )


def _recusar_telefone_cheio(cur, id_unidade: int, telefone: str) -> None:
    """Um telefone só segura algumas mesas de cada vez.

    🔑 **É o limite que protege o SALÃO**, não o servidor: sem ele, uma pessoa
    marca todos os horários do sábado "para decidir depois" e a casa recusa
    clientes de verdade a noite inteira.
    ⚠️ **Conta só o que está VIVO e à frente.** Reserva cancelada não ocupa nada,
    e a de semana passada já aconteceu — somá-las faria o cliente fiel ser
    barrado justamente por ser fiel.
    """
    cur.execute(
        """SELECT count(*) AS n FROM reservas
            WHERE id_unidade = %s AND telefone = %s
              AND status IN ('PENDENTE', 'CONFIRMADA')
              AND data >= current_date""",
        (id_unidade, telefone),
    )
    if cur.fetchone()["n"] >= RESERVAS_ATIVAS_POR_TELEFONE:
        raise HTTPException(
            status_code=429,
            detail=(f"Este telefone já tem {RESERVAS_ATIVAS_POR_TELEFONE} reservas em "
                    "aberto. Para marcar outra, fale com a casa."),
        )


def _nascimento_valido(nascimento: date | None) -> date | None:
    """A data de nascimento, se plausível. Nula passa: é "não informou".

    ⚠️ **Futuro e antes de 1900 são engano de digitação**, não gente: o seletor
    de data do celular começa no ano corrente, e um toque a menos grava "2026".
    Aceitar isso poria um recém-nascido na lista de aniversariantes.
    """
    if nascimento and (nascimento > hoje_da_casa() or nascimento.year < 1900):
        raise HTTPException(status_code=422, detail="Confira a data de nascimento.")
    return nascimento


def resolver(cur, id_unidade: int, corpo, exige_completo: bool) -> dict:
    """O cliente de uma RESERVA: confere o limite do telefone e identifica.

    ⚠️ **O limite de reservas em aberto é só daqui.** Quem se identifica para abrir
    o catálogo (`identificar`) não está segurando mesa nenhuma.
    """
    telefone = telefone_valido(corpo.telefone)
    _recusar_telefone_cheio(cur, id_unidade, telefone)
    return identificar(cur, id_unidade, corpo, exige_completo)


def identificar(cur, id_unidade: int, corpo, exige_completo: bool) -> dict:
    """Quem é esta pessoa: o cadastro que já existe, ou um novo.

    🔑 **Uma identificação só, para a reserva e para o catálogo** (pedido do dono,
    24/09/2026: *"adicionar a validação do cliente ao acessar o catálogo"*). Duas
    portas de cadastro divergiriam na primeira regra nova — e a pessoa que se
    cadastrou para ver o cardápio já é conhecida quando vai reservar.

    🔑 **O nome é o que prova que o telefone é seu**, neste nível. Não há login,
    e não há código por WhatsApp (que exigiria Business API, provedor e modelo
    aprovado — justamente o que o site evitou ao usar só o link `wa.me`). Quem
    digita um telefone alheio precisa saber o nome de quem o tem; quem sabe o
    nome e o telefone já sabe as duas coisas que a reserva revelaria.

    ⚠️ **Confere só o PRIMEIRO nome, sem acento e sem caixa.** Exigir "Maria
    Eduarda da Silva Santos" idêntico ao que ela digitou meses atrás faria a
    dona do cadastro ser recusada no próprio telefone — e a saída dela seria se
    cadastrar de novo, que é o que o índice único impede.
    """
    telefone = telefone_valido(corpo.telefone)
    nascimento = _nascimento_valido(getattr(corpo, "nascimento", None))

    cur.execute(
        """SELECT id, nome, genero, cidade FROM reserva_clientes
            WHERE telefone = %s""",
        (telefone,),
    )
    achado = cur.fetchone()

    if achado:
        # ⚠️ Só confere o nome que VEIO: desde 24/09 o site não o pede a quem
        # já tem cadastro (pedido do dono). Nome mandado e errado é recusado.
        if corpo.nome and _primeiro_nome(corpo.nome) != _primeiro_nome(achado["nome"]):
            raise HTTPException(status_code=409, detail=_NOME_NAO_CONFERE)
        # 🔑 **Cidade e gênero podem ser COMPLETADOS numa visita seguinte**, se o
        # cadastro antigo não os tiver. ⚠️ Mas o que já está preenchido não é
        # sobrescrito pelo que a tela mandar: quem corrigiu a cidade pelo balcão
        # não pode perder a correção porque o site reenviou o valor antigo.
        cur.execute(
            """UPDATE reserva_clientes
                  SET genero = COALESCE(genero, %s),
                      cidade = COALESCE(cidade, %s),
                      nascimento = COALESCE(nascimento, %s),
                      atualizado_em = now()
                WHERE id = %s""",
            (corpo.genero, (corpo.cidade or "").strip() or None, nascimento,
             achado["id"]),
        )
        return {"id": achado["id"], "nome": achado["nome"], "telefone": telefone,
                "novo": False}

    # ⚠️ **O que o cadastro novo exige sai da CONFIGURAÇÃO da loja**
    # (`reserva_config.cadastro_completo`), não do código. A casa que só quer o
    # nome desliga a caixa e o site para de perguntar o resto.
    if exige_completo:
        faltando = []
        if not corpo.genero:
            faltando.append("gênero")
        if not (corpo.cidade or "").strip():
            faltando.append("cidade")
        if not nascimento:
            faltando.append("data de nascimento")
        if faltando:
            raise HTTPException(
                status_code=422,
                detail=f"Para o primeiro cadastro, informe também: {', '.join(faltando)}.",
            )
    # ⚠️ Sem cadastro, o nome é o mínimo: é por ele que a casa chama a pessoa.
    if not (corpo.nome or "").strip():
        raise HTTPException(status_code=422, detail="Diga seu nome para o cadastro.")
    if corpo.genero and corpo.genero not in GENEROS:
        raise HTTPException(status_code=422, detail="Gênero inválido.")

    # 🔑 **`ON CONFLICT` em vez de "perguntar e depois inserir".** Duas abas do
    # mesmo celular tocando "cadastrar" ao mesmo tempo passam as duas pela
    # consulta acima; quem decide é o índice único, como manda a regra 8.
    cur.execute(
        """INSERT INTO reserva_clientes (id_unidade, telefone, nome, genero, cidade,
                                         nascimento)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (telefone) DO UPDATE SET atualizado_em = now()
           RETURNING id, nome""",
        (id_unidade, telefone, corpo.nome.strip(), corpo.genero,
         (corpo.cidade or "").strip() or None, nascimento),
    )
    novo = cur.fetchone()
    return {"id": novo["id"], "nome": novo["nome"], "telefone": telefone, "novo": True}
