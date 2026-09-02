"""Quando uma integração deve rodar sozinha — a regra, num lugar só.

Omie e PDV Legal têm o mesmo problema e a mesma resposta: nota que chega na
sexta e ninguém busca até segunda é nota que não entrou no estoque; venda do
sábado que ninguém importa é receita que falta no CMV do fim de semana. Os dois
ganharam três ritmos — ``MANUAL`` (o padrão), ``HORARIA`` e ``DIARIA`` numa hora
escolhida — e os dois guardam a configuração nas MESMAS colunas de
``integracoes``, porque desde o começo elas não tinham nada de específico do
Omie.

⚠️ **A pergunta "chegou a hora?" é feita aqui e em nenhum outro lugar.** Ela
estava escrita dentro do agendador do Omie; copiá-la para o do PDV faria os dois
divergirem na primeira correção — e o sintoma seria uma integração buscando na
hora certa e a outra não, sem nada explicando a diferença.

⚠️ **O relógio é `agenda_rodou_em`, não `ultima_sincronizacao`.** A segunda só
avança quando algo chega; usá-la como relógio faria o agendador tentar de novo a
cada minuto numa casa sem nota nova — que é a casa normal de domingo. Por isso
`marcar` avança o relógio **mesmo com erro**: o erro fica à vista em
`agenda_ultimo_erro` e a próxima tentativa é no horário seguinte. Repetir em
cima de um bloqueio do fornecedor só o prolonga.

⚠️ **E só o AGENDADOR move esse relógio.** Busca manual não consome a cota do
dia: quem clica no botão está pedindo agora, não dispensando a busca da
madrugada. As duas coisas são pedidos diferentes, feitos por razões diferentes.
"""

from datetime import datetime, timedelta

FREQUENCIAS = ("MANUAL", "HORARIA", "DIARIA")

# De quanto em quanto tempo o agendador acorda e olha o relógio. Um minuto é
# fino o bastante para a hora escolhida ser respeitada e grosso o bastante para
# a consulta (uma, com índice) não pesar.
INTERVALO_DE_CHECAGEM = 60


def deve_rodar(linha: dict, agora: datetime) -> bool:
    """Chegou a hora desta integração?

    🔑 **A DIÁRIA é "uma vez por dia, a partir da hora escolhida" — e não "na
    hora escolhida, se alguém estiver acordado".** A primeira versão exigia
    `agora.hour == agenda_hora`: o disparo só existia dentro daqueles sessenta
    minutos, e fora deles o dia inteiro passava em branco. Se a API estivesse
    parada às 4h — um deploy, um reinício, a máquina desligada —, a busca
    daquele dia **simplesmente não acontecia**, e nada dizia isso: a tela
    mostrava a última sincronização (que uma busca manual havia atualizado) e a
    agenda parecia em dia. Medido na base local em 02/09/2026: a diária das 4h
    tinha rodado pela última vez em **31/08**, pulando dois dias inteiros de
    notas e cupons — compra a menos e receita a menos no CMV, em silêncio.

    Agora a pergunta é a que a casa faz: *já buscou hoje?* Não tendo buscado e
    já passada a hora marcada, busca — assim que houver alguém para buscar.

    ⚠️ **E continua sendo UMA vez por dia.** Voltando depois de três dias fora
    do ar, roda uma vez, não três: quem responde é a data do último disparo, não
    quantos horários passaram. Três buscas seguidas só gastariam cota — e a
    janela adaptativa da busca já cobre o período inteiro numa ida só.

    ⚠️ **O relógio é `agenda_rodou_em`, e só o AGENDADOR o move.** Busca manual
    não consome a cota do dia: quem clica no botão está pedindo agora, não
    dispensando a busca da madrugada. Era o pedido do dono, e o `marcar` já era
    chamado só daqui — a exceção estava no cardápio do PDV, corrigida junto.
    """
    freq = linha["agenda_frequencia"]
    if freq == "MANUAL" or not linha["ativa"]:
        return False

    ultima = linha["agenda_rodou_em"]
    if freq == "HORARIA":
        return ultima is None or (agora - ultima) >= timedelta(hours=1)

    if freq == "DIARIA":
        if ultima is not None and ultima.date() >= agora.date():
            return False  # já buscou hoje
        return agora.hour >= linha["agenda_hora"]

    return False


def pendentes(cur, servico: str, agora: datetime) -> list[dict]:
    """As integrações deste serviço que estão devendo uma busca."""
    cur.execute(
        """SELECT id, id_unidade, modo, ativa, credenciais, agenda_frequencia,
                  agenda_hora, agenda_janela_dias, agenda_rodou_em, agenda_id_usuario
             FROM integracoes
            WHERE servico = %s AND agenda_frequencia <> 'MANUAL'""",
        (servico,),
    )
    return [dict(r) for r in cur.fetchall() if deve_rodar(dict(r), agora)]


def marcar(cur, id_integracao: int, erro: str | None) -> None:
    """Avança o relógio e registra o erro — ou o apaga, quando deu certo."""
    cur.execute(
        "UPDATE integracoes SET agenda_rodou_em = now(), agenda_ultimo_erro = %s WHERE id = %s",
        (erro, id_integracao),
    )


def peguei_o_lock(cur, chave: int) -> bool:
    """Só uma instância roda a busca.

    ⚠️ **Antes de olhar o relógio.** Duas instâncias da API (ou o worker do
    `--reload` junto com um sobrevivente órfão) leriam a mesma linha "vencida" e
    disparariam duas buscas — cota gasta em dobro por nada. `try` e não `wait`:
    quem não pega vai embora e tenta no minuto seguinte.
    """
    cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS peguei", (chave,))
    return bool(cur.fetchone()["peguei"])
