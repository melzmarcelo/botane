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
"""

from datetime import datetime, timedelta

FREQUENCIAS = ("MANUAL", "HORARIA", "DIARIA")

# De quanto em quanto tempo o agendador acorda e olha o relógio. Um minuto é
# fino o bastante para a hora escolhida ser respeitada e grosso o bastante para
# a consulta (uma, com índice) não pesar.
INTERVALO_DE_CHECAGEM = 60


def deve_rodar(linha: dict, agora: datetime) -> bool:
    """Chegou a hora desta integração?

    ⚠️ A DIÁRIA dispara na hora escolhida **e só uma vez no dia**: sem a segunda
    condição, ela rodaria a cada minuto durante os sessenta minutos daquela hora.
    """
    freq = linha["agenda_frequencia"]
    if freq == "MANUAL" or not linha["ativa"]:
        return False

    ultima = linha["agenda_rodou_em"]
    if freq == "HORARIA":
        return ultima is None or (agora - ultima) >= timedelta(hours=1)

    if freq == "DIARIA":
        if agora.hour != linha["agenda_hora"]:
            return False
        return ultima is None or ultima.date() < agora.date()

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
