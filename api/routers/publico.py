"""O que o SITE DO CLIENTE pode ler — sem login, sem token, sem cabeçalho.

🔑 **Pedido do dono (21/09/2026):** *"agora vamos criar o site para o cliente,
onde o front será separado, no oficial vamos colocar em
reserva.botanedeliecafe.com.br. Os itens serão: Reserva, Catálogos cadastrados e
ativos, Entre em Contato (onde vai abrir o whatsapp para enviar mensagem para o
número cadastrado para a empresa)."*

⚠️ **Este é o único router SEM permissão, e por isso ele é o mais estreito do
sistema.** Todo o resto da casa declara a chave que exige; aqui quem entra é o
público da internet. A regra que substitui a permissão é a do CONTEÚDO: só sai
daqui o que a casa já decidiu publicar — o catálogo que ela marcou como ativo, o
telefone que ela cadastrou, os horários que o salão comporta.

⚠️ **Nada de `id` interno, nada de contagem, nada de dado de negócio.** A
tentação num endpoint público é reaproveitar o serializador de dentro; o preço é
vazar o que ninguém pediu — quantas mesas a casa tem, quantas reservas existem
hoje, o nome de quem atendeu. Cada resposta aqui é montada à mão.

⚠️ **A loja vem no CAMINHO, não no cabeçalho `X-Unidade`.** O site do cliente não
tem sessão para guardar loja; e um dia haverá duas casas com reserva, cada uma no
seu endereço. `/publico/{id_unidade}/...` deixa isso resolvido desde já.

🔑 **A porta continua sendo `parametros.reservas_ligado`**: casa que não faz
reserva não aparece aqui — nem o catálogo dela, que é do site de reservas.
"""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query

from database import get_cursor
from services import reservas as reservas_servico
from services import reservas_agenda as agenda

router = APIRouter(prefix="/publico", tags=["site do cliente"])


def _so_digitos(v: str | None) -> str | None:
    """O telefone como o `wa.me` pede: só números, sem máscara.

    ⚠️ **O cadastro aceita o número digitado de qualquer jeito** — "(47) 99910-5033"
    é o normal —, e o link do WhatsApp não aceita nada além de dígitos. Quem
    limpa é aqui, não a tela: o site do cliente não deve saber o formato do
    cadastro da casa.
    """
    if not v:
        return None
    d = "".join(c for c in str(v) if c.isdigit())
    return d or None


def _casa_aberta(cur, id_unidade: int) -> dict:
    """A loja, se ela existe, está ativa e faz reserva. Senão, 404.

    ⚠️ **404, não 403.** Loja que não faz reserva não é um segredo guardado: do
    ponto de vista do site do cliente, ela simplesmente não existe. Um 403 diria
    ao público que aquele número corresponde a uma casa real.
    """
    cur.execute(
        "SELECT id, nome, apelido, cidade, uf, telefone FROM unidades WHERE id = %s AND ativo",
        (id_unidade,),
    )
    loja = cur.fetchone()
    if not loja or not reservas_servico.ligado(cur, id_unidade):
        raise HTTPException(status_code=404, detail="Casa não encontrada.")
    return dict(loja)


@router.get("/{id_unidade}/casa")
def casa(id_unidade: int) -> dict:
    """Quem é a casa, e como falar com ela.

    🔑 **É o que alimenta o "Entre em Contato"**: o WhatsApp sai daqui, do
    cadastro da empresa, e não escrito no site. O dia em que a casa trocar de
    número, ela troca em Administração ▸ Empresa e o site acompanha.
    ⚠️ **`whatsapp` pode vir nulo, e o site precisa lidar com isso** — hoje o
    campo está em branco nesta base. Devolver um número inventado seria pior que
    devolver nada: o cliente mandaria mensagem para um desconhecido.
    """
    with get_cursor() as cur:
        loja = _casa_aberta(cur, id_unidade)
        cur.execute(
            """SELECT nome_fantasia, razao_social, whatsapp, telefone, email,
                      instagram, logradouro, numero, bairro, cidade, uf, logo_url,
                      cor_primaria
                 FROM empresa WHERE id = 1""",
        )
        e = dict(cur.fetchone() or {})

        # ⚠️ O telefone da LOJA ganha do da empresa: é para ele que quem quer
        # falar com esta casa deve ligar. O WhatsApp é da empresa porque é o
        # canal único que o dono cadastrou.
        zap = _so_digitos(e.get("whatsapp"))
        endereco = ", ".join(
            [p for p in (e.get("logradouro"), e.get("numero"), e.get("bairro")) if p])

        return {
            "loja": loja["apelido"] or loja["nome"],
            "casa": e.get("nome_fantasia") or e.get("razao_social") or "Botané",
            "cidade": loja.get("cidade") or e.get("cidade"),
            "uf": loja.get("uf") or e.get("uf"),
            "endereco": endereco or None,
            "telefone": loja.get("telefone") or e.get("telefone"),
            # 🔑 Só os dígitos: é o que o `https://wa.me/<numero>` pede.
            "whatsapp": zap,
            "email": e.get("email"),
            "instagram": e.get("instagram"),
            # 🔑 **A logo cadastrada** (pedido do dono, 21/09/2026). Nula quando
            # a casa ainda não enviou uma — e aí o site desenha o medalhão com o
            # nome, como o protótipo. ⚠️ Inventar uma imagem seria pior: o
            # cliente veria a marca de outra pessoa.
            "logo_url": e.get("logo_url"),
            # A cor da casa, que o cadastro já guarda. O site pinta a capa com
            # ela em vez de trazer um verde escrito no HTML.
            "cor": e.get("cor_primaria"),
            **_quando_atende(cur, id_unidade),
            **_textos_do_zap(cur, id_unidade),
        }


# 🔑 **Os nomes dos dias, na voz de quem lê** — "Ter" e "Qua", não "2" e "3". A
# tela do cliente mostra "Ter · Qua · Qui · Sex · Sáb", como o protótipo.
# ⚠️ ISO: 1 = segunda … 7 = domingo. É a convenção da casa desde
# `parametros.fechamento_dia_semana`, e duas convenções de dia da semana no
# mesmo sistema não dão erro em lugar nenhum — só marcam no dia errado.
_DIAS = {1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom"}


def _textos_do_zap(cur, id_unidade: int) -> dict:
    """As mensagens que a casa escreveu para o WhatsApp (migração 081).

    🔑 **Pedido do dono (21/09/2026):** *"em configurações da reserva, colocar o
    texto padrão configurável para o whatsapp."* Estavam escritas no site, e
    texto de cliente escrito em código só muda quando alguém publica.

    ⚠️ **Os marcadores são trocados no SITE, não aqui.** `{pessoas}`, `{data}` e
    `{hora}` só existem no instante do clique — o servidor não sabe o que o
    cliente escolheu, e montar a frase aqui exigiria mandar a escolha de volta
    para receber um texto.
    """
    cur.execute(
        """SELECT whatsapp_texto, whatsapp_texto_reserva
             FROM reserva_config WHERE id_unidade = %s""",
        (id_unidade,),
    )
    t = dict(cur.fetchone() or {})
    return {
        "zap_texto": t.get("whatsapp_texto"),
        "zap_texto_reserva": t.get("whatsapp_texto_reserva"),
    }


def _quando_atende(cur, id_unidade: int) -> dict:
    """Em que dias a casa atende, e se ela está aberta AGORA.

    🔑 **É o que a capa do protótipo mostra**: a tarja "Aberto agora" e a linha
    com os dias. Sem isso o cliente abre o site às 23h, vê "Reservar uma mesa" e
    só descobre que a casa está fechada depois de escolher dia e horário.

    ⚠️ **"Aberto agora" é sobre a CASA, não sobre a reserva.** A última reserva
    é mais cedo que o fechamento de propósito — quem chega às 17h55 numa casa
    que fecha às 18h ainda é atendido, mas já não se reserva mesa.
    """
    cur.execute(
        """SELECT dia_semana, aberto, abre, fecha FROM reserva_horarios
            WHERE id_unidade = %s ORDER BY dia_semana""",
        (id_unidade,),
    )
    linhas = [dict(r) for r in cur.fetchall()]
    abertos = [d for d in linhas if d["aberto"]]
    agora = datetime.now()
    hoje = next((d for d in abertos if d["dia_semana"] == agora.isoweekday()), None)
    return {
        "dias": [_DIAS[d["dia_semana"]] for d in abertos],
        "aberta_agora": bool(hoje and hoje["abre"] <= agora.time() <= hoje["fecha"]),
        # ⚠️ Quando a casa abre de novo, para a tarja poder dizer "abre Sáb 11:00"
        # em vez de só "fechado" — que é uma porta na cara de quem chegou.
        "hoje": (f'{hoje["abre"].strftime("%H:%M")} às {hoje["fecha"].strftime("%H:%M")}'
                 if hoje else None),
        "proximo": next(
            (f'{_DIAS[d["dia_semana"]]} {d["abre"].strftime("%H:%M")}'
             for i in range(1, 8)
             for d in abertos
             if d["dia_semana"] == ((agora.isoweekday() + i - 1) % 7) + 1),
            None),
    }


@router.get("/{id_unidade}/catalogos")
def catalogos(id_unidade: int) -> list[dict]:
    """Os catálogos que a casa está publicando HOJE.

    🔑 *"Catálogos cadastrados e ativos"* — e "ativo" aqui é mais estreito que a
    situação: entra o que está `ATIVO`, **dentro do período** e **com arquivo**.
    ⚠️ **Sem PDF não entra na lista.** Um catálogo ativo sem arquivo é uma capa
    sem conteúdo; mostrá-lo ao cliente seria oferecer um cardápio que não abre.
    A tela de dentro avisa a casa exatamente sobre isso.
    ⚠️ **A regra do "no ar" é a MESMA de `services/catalogos.py`**, escrita em
    SQL aqui porque a consulta é outra — se ela mudar lá, muda aqui. É o preço de
    não trazer o serializador de dentro para uma rota pública.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        cur.execute(
            """SELECT nome, arquivo_url, arquivo_nome, arquivo_bytes, publica_ate
                 FROM catalogos
                WHERE id_unidade = %s
                  AND situacao = 'ATIVO'
                  AND arquivo_url IS NOT NULL
                  AND (publica_de IS NULL OR publica_de <= current_date)
                  AND (publica_ate IS NULL OR publica_ate >= current_date)
                ORDER BY publica_de NULLS FIRST, lower(nome)""",
            (id_unidade,),
        )
        return [
            {"nome": r["nome"], "arquivo_url": r["arquivo_url"],
             "bytes": r["arquivo_bytes"],
             # ⚠️ Quando termina, para o site poder dizer "até domingo". Só isso
             # — a data de início não interessa a quem já está vendo.
             "ate": r["publica_ate"]}
            for r in cur.fetchall()
        ]


@router.get("/{id_unidade}/horarios")
def horarios(
    id_unidade: int,
    dia: date,
    pessoas: int = Query(ge=1, le=50),
) -> dict:
    """Os horários que aceitam um grupo neste dia.

    🔑 **É a MESMA regra que a agenda do balcão usa** (`reservas_agenda`), e isso
    é o ponto: uma segunda regra para o público divergiria da primeira, e a
    divergência apareceria como mesa prometida ao cliente e não disponível na
    casa.

    ⚠️ **O cliente não escolhe mesa** — ele vê "19:00 disponível" e a casa decide
    onde sentar. É o que o esboço já dizia, e é o que evita que a escolha do
    cliente trave a operação.

    ⚠️ **Esta rota LÊ e não grava.** Gravar a reserva pela internet é outra
    conversa — precisa identificar a pessoa e conter abuso — e é a próxima fatia.
    """
    with get_cursor() as cur:
        _casa_aberta(cur, id_unidade)
        r = agenda.disponibilidade(cur, id_unidade, dia, pessoas)
        # ⚠️ **Só o que o cliente precisa, e nada de operação.** A resposta de
        # dentro traz `mesas_livres` por horário — quantas mesas a casa ainda
        # tem —, e isso é informação de negócio: o público não precisa saber se
        # o salão está cheio ou vazio para escolher as 19h.
        return {
            "dia": dia.isoformat(),
            "pessoas": pessoas,
            "abre": r.get("abre"),
            "fecha": r.get("fecha"),
            # 🔑 Só os LIVRES, já em texto. Mandar os ocupados junto faria a tela
            # ter de filtrar — e uma tela que filtra é uma tela que pode errar o
            # filtro e oferecer o que não há.
            "horarios": [h["hora"] for h in (r.get("horarios") or []) if h["livre"]],
            # ⚠️ **O teto do site é do CADASTRO**, e o maior grupo é do SALÃO:
            # teto maior que a maior junta é uma promessa que a casa não cumpre,
            # e o site precisa dos dois para não oferecer mesa para 12 quando a
            # maior junta senta 8.
            "teto": min(int(r.get("teto_online") or 0) or 99,
                        int(r.get("maior_grupo") or 0) or 99),
            "motivo": r.get("motivo"),
        }
