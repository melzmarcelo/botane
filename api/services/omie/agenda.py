"""A busca das notas no Omie rodando sozinha.

Até aqui alguém tinha de abrir Compras e clicar em "Buscar no Omie". Nota que
chega na sexta e ninguém busca até segunda é nota que não entrou no estoque — e
o CMV do fim de semana sai com compra a menos, sem nada na tela denunciando.

Três ritmos por loja: ``MANUAL`` (o padrão), ``HORARIA`` e ``DIARIA`` numa hora
escolhida.

⚠️ **Cada busca consome cota da conta do cliente, e o Omie BLOQUEIA quem
consome demais** — o bloqueio pega a integração inteira, não só a chamada. Daí
três decisões deste arquivo:

* o padrão é MANUAL, e ligar é decisão de quem paga a conta;
* o agendador **não repete o que falhou**: erro fica registrado e a próxima
  tentativa é no horário seguinte, não em dois minutos. Repetir em cima de um
  bloqueio é o jeito mais rápido de prolongá-lo;
* duas instâncias da API não rodam a mesma busca: quem entra pega um
  **advisory lock** e quem não pega vai embora.

⚠️ **O relógio é `agenda_rodou_em`, não `ultima_sincronizacao`.** A segunda só
avança quando alguma nota chega; usá-la como relógio faria o agendador tentar
de novo a cada minuto numa casa sem nota nova — que é a casa normal de domingo.
"""

import asyncio
import traceback
from datetime import datetime, timedelta

from database import get_cursor
from services import segredos
from services.omie import importador
from services.omie.cliente import ClienteOmie, ErroOmie

SERVICO = "OMIE"

# De quanto em quanto tempo o agendador acorda e olha o relógio. Um minuto é
# fino o bastante para a hora escolhida ser respeitada e grosso o bastante para
# a consulta (uma, com índice) não pesar.
INTERVALO_DE_CHECAGEM = 60

# ⚠️ Chave do advisory lock. Número fixo e único no sistema: dois locks com o
# mesmo número se bloqueariam sem ter nada a ver um com o outro.
LOCK_AGENDA_OMIE = 8_120_331


def _deve_rodar(linha: dict, agora: datetime) -> bool:
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


def pendentes(cur, agora: datetime) -> list[dict]:
    """As integrações que estão devendo uma busca."""
    cur.execute(
        """SELECT id, id_unidade, modo, ativa, credenciais, agenda_frequencia,
                  agenda_hora, agenda_janela_dias, agenda_rodou_em
             FROM integracoes
            WHERE servico = %s AND agenda_frequencia <> 'MANUAL'""",
        (SERVICO,),
    )
    return [dict(r) for r in cur.fetchall() if _deve_rodar(dict(r), agora)]


def rodar_uma(cur, linha: dict) -> dict:
    """Busca as notas de uma loja. Marca o relógio ACONTEÇA O QUE ACONTECER.

    ⚠️ O relógio avança mesmo quando dá erro. Sem isso, uma conta bloqueada faria
    o agendador tentar de novo no minuto seguinte, para sempre — e cada tentativa
    prolonga o bloqueio. O erro fica gravado em `agenda_ultimo_erro`, à vista na
    tela de Integrações.
    """
    cred = segredos.decifrar(linha["credenciais"]) if linha["credenciais"] else {}
    cliente = ClienteOmie(cred.get("app_key"), cred.get("app_secret"), linha["modo"])

    resultado: dict = {}
    erro: str | None = None
    try:
        resultado = importador.sincronizar(
            cur, linha["id_unidade"], cliente, dias=linha["agenda_janela_dias"]
        )
    except ErroOmie as e:
        erro = e.mensagem
    except Exception as e:  # noqa: BLE001 — o agendador não pode morrer por uma loja
        erro = f"{type(e).__name__}: {e}"

    cur.execute(
        """UPDATE integracoes
              SET agenda_rodou_em = now(), agenda_ultimo_erro = %s
            WHERE id = %s""",
        (erro, linha["id"]),
    )
    return {"id_unidade": linha["id_unidade"], "erro": erro, **resultado}


def rodar_pendentes() -> list[dict]:
    """Uma passada do agendador. Devolve o que rodou — vazio é o caso comum."""
    feitos: list[dict] = []
    with get_cursor() as cur:
        # ⚠️ **Advisory lock antes de olhar o relógio.** Duas instâncias da API
        # (ou o worker do `--reload` junto com um sobrevivente órfão) leriam a
        # mesma linha "vencida" e disparariam duas buscas — cota gasta em dobro
        # por nada. `pg_try_advisory_xact_lock` não espera: quem não pega vai
        # embora e tenta no minuto seguinte.
        cur.execute("SELECT pg_try_advisory_xact_lock(%s) AS peguei", (LOCK_AGENDA_OMIE,))
        if not cur.fetchone()["peguei"]:
            return feitos

        agora = datetime.now().astimezone()
        for linha in pendentes(cur, agora):
            feitos.append(rodar_uma(cur, linha))
    return feitos


async def laco(parar: asyncio.Event) -> None:
    """O laço que acorda de minuto em minuto. Vive no `lifespan` da aplicação.

    ⚠️ **Roda em thread separada** (`asyncio.to_thread`): o importador é síncrono
    e conversa com o Omie, o que leva dezenas de segundos. Chamá-lo direto no
    laço de eventos travaria a API inteira enquanto isso — a casa ficaria sem
    sistema durante a busca.

    ⚠️ **Nada aqui pode levantar exceção para cima.** Um agendador que morre no
    primeiro erro é pior que não ter agendador: some sem avisar, e meses depois
    alguém descobre que as notas pararam de entrar.
    """
    while not parar.is_set():
        try:
            await asyncio.wait_for(parar.wait(), timeout=INTERVALO_DE_CHECAGEM)
            return  # o evento foi disparado: a aplicação está parando
        except asyncio.TimeoutError:
            pass

        try:
            feitos = await asyncio.to_thread(rodar_pendentes)
            for f in feitos:
                if f.get("erro"):
                    print(f"[botane] agenda Omie (loja {f['id_unidade']}): {f['erro']}")
                else:
                    print(f"[botane] agenda Omie (loja {f['id_unidade']}): "
                          f"{f.get('novas', 0)} nota(s) nova(s)")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
