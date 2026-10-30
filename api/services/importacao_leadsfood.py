"""A importação do LeadsFood — contatos, reservas, selos em aberto e prêmios.

🔑 **Pedido do dono (30/10/2026):** *"siga para a importação do LeadsFood"*. Sem ela, trocar de
sistema zera o cartão de quem está no meio dele, e o Plano de ação e o Painel das reservas
ficam sem o histórico (170 reservas desde 11/2025). Leitura do sistema antigo:
`docs/leadsfood-analise.md`.

Os quatro arquivos, todos CSV:
- **Contatos** — a exportação de Contatos do LeadsFood.
- **Reservas** — a exportação de Reservas. ⚠️ Lá, a reserva que passou fica ARQUIVADA
  ("registro excluído"): exportar com "Exibir registros excluídos", senão vêm só as futuras.
- **Selos em aberto** — o LeadsFood não exporta check-in. O arquivo é a lista da tela de
  Check-ins sem filtro e sem os arquivados (`nome,celular,pin,campanha,status,criado_em`). Os
  arquivados são os cartões já completados — viraram prêmio, e o prêmio vem no arquivo dele.
- **Prêmios** — a exportação de Prêmios (vouchers), sem filtro de status.

🔑 **Pode repetir.** A casa continua usando o LeadsFood até virar a chave, e a última
importação tem de valer por cima da anterior sem duplicar:
- cliente pelo telefone (único desde a 087); o que já existe aqui só ganha os campos vazios;
- reserva por loja + telefone + dia + hora, prêmio por cliente + validade (índices da 145); a
  repetida atualiza o status;
- ⚠️ **os selos em aberto são uma FOTO**: o selo importado antes que não está mais no arquivo
  é retirado (o cartão fechou lá e virou prêmio). Selo que nasceu aqui nunca é tocado.

🔑 **A prévia é a importação de verdade, desfeita** (`SAVEPOINT`): o número que a tela mostra
antes de gravar sai do mesmo código que grava, e não de uma segunda conta que pode divergir.
"""

import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from services import fidelidade
from services.reserva_clientes import so_digitos

MARCA = "LEADSFOOD"
MAXIMO_BYTES = 5 * 1024 * 1024
MOTIVO_SELO = "Importado do LeadsFood"

# Status da reserva no LeadsFood → aqui. "Notificado" é um confirmado que recebeu o lembrete.
STATUS = {
    "compareceu": "ENCERRADA",
    "não compareceu": "NAO_COMPARECEU",
    "confirmado": "CONFIRMADA",
    "notificado": "CONFIRMADA",
    "pendente": "PENDENTE",
    "cancelado pelo cliente": "CANCELADA",
    "cancelado": "CANCELADA",
    "cancelado pelo estabelecimento": "CANCELADA",
}
GENERO = {"F": "FEMININO", "M": "MASCULINO"}

# A coluna que denuncia cada arquivo — a tela não precisa acertar em que campo o soltou.
ASSINATURAS = {
    "contatos": {"Nome completo", "Celular", "Data de criação", "Total checkins"},
    "reservas": {"Nome completo", "Celular", "Pessoas", "Data e hora", "Status"},
    "selos": {"nome", "celular", "pin", "status", "criado_em"},
    "premios": {"Nome completo", "Celular", "Campanha", "Expiração", "Status"},
}


class ArquivoInvalido(ValueError):
    pass


def ler(conteudo: bytes, esperado: str) -> list[dict]:
    """O CSV em linhas, conferindo que é o arquivo certo para aquele campo."""
    if len(conteudo) > MAXIMO_BYTES:
        raise ArquivoInvalido("Arquivo maior que 5 MB.")
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    linhas = list(csv.DictReader(io.StringIO(texto)))
    colunas = set(linhas[0]) if linhas else set()
    if not ASSINATURAS[esperado] <= colunas:
        tipo = next((k for k, v in ASSINATURAS.items() if v <= colunas), None)
        raise ArquivoInvalido(
            f"Este não é o arquivo de {esperado}"
            + (f" — parece o de {tipo}." if tipo else ". Confira se é o CSV exportado do LeadsFood."))
    return [{k: (v or "").strip() for k, v in x.items() if k} for x in linhas]


def telefone(bruto: str) -> str | None:
    """Como o cadastro guarda: só dígitos, sem o 55. Fora de 10/11 dígitos não é celular daqui."""
    d = so_digitos(bruto)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    return d if len(d) in (10, 11) else None


def _data(texto: str) -> date | None:
    try:
        return datetime.strptime(texto[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def _data_hora(texto: str) -> datetime | None:
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None


class _Clientes:
    """Acha (ou cria) o cliente pelo telefone, contando o que fez."""

    def __init__(self, cur, id_unidade: int):
        self.cur, self.u = cur, id_unidade
        self.ids: dict[str, int] = {}
        self.novos = self.completados = self.iguais = 0

    def garantir(self, fone: str, nome: str, extra: dict | None = None,
                 criado_em: datetime | None = None) -> int:
        cur, e = self.cur, extra or {}
        cur.execute("""SELECT id, genero, cidade, nascimento, email, uf, origem, etiquetas,
                              criado_em FROM reserva_clientes WHERE telefone = %s""", (fone,))
        atual = cur.fetchone()
        if not atual:
            cur.execute(
                """INSERT INTO reserva_clientes (id_unidade, telefone, nome, genero, cidade,
                                                 nascimento, email, uf, origem, etiquetas,
                                                 importado_de, criado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
                   RETURNING id""",
                (self.u, fone, (nome or "Sem nome")[:120], e.get("genero"), e.get("cidade"),
                 e.get("nascimento"), e.get("email"), e.get("uf"), e.get("origem"),
                 e.get("etiquetas") or [], MARCA, criado_em))
            self.novos += 1
            self.ids[fone] = cur.fetchone()["id"]
            return self.ids[fone]
        # ⚠️ Só o que está VAZIO aqui: o cadastro do site é mais novo que o do LeadsFood.
        mudou = {k: v for k, v in e.items()
                 if v and k != "etiquetas" and not atual[k]}
        if e.get("etiquetas") and not atual["etiquetas"]:
            mudou["etiquetas"] = e["etiquetas"]
        if criado_em and criado_em.date() < atual["criado_em"].date():
            mudou["criado_em"] = criado_em  # o primeiro contato foi lá
        if mudou:
            sets = ", ".join(f"{k} = %s" for k in mudou)
            cur.execute(f"UPDATE reserva_clientes SET {sets}, atualizado_em = now() WHERE id = %s",
                        [*mudou.values(), atual["id"]])
            self.completados += 1
        elif extra is not None:
            self.iguais += 1
        self.ids[fone] = atual["id"]
        return atual["id"]

    def id_de(self, fone: str, nome: str) -> int:
        """Para reservas, selos e prêmios: o cliente que o arquivo de contatos já criou, ou um
        cadastro mínimo com nome e telefone (quando os contatos não vieram junto)."""
        return self.ids.get(fone) or self.garantir(fone, nome)


def _contatos(linhas: list[dict], cli: _Clientes, rec: list) -> None:
    for i, x in enumerate(linhas, start=2):
        fone = telefone(x.get("Celular", ""))
        if not fone:
            rec.append({"arquivo": "contatos", "linha": i, "nome": x.get("Nome completo"),
                        "motivo": "celular fora do padrão (DDD + número)"})
            continue
        nasc = _data(x.get("Nascimento", ""))
        if nasc and not (date(1900, 1, 1) <= nasc <= date.today()):
            nasc = None
        extra = {
            "genero": GENERO.get(x.get("Gênero", "").upper()),
            "cidade": x.get("Cidade") or None,
            "nascimento": nasc,
            "email": (x.get("E-mail") or None),
            "uf": (x.get("Estado") or "")[:2].upper() or None,
            "origem": x.get("Origem") or None,
            "etiquetas": [t.strip() for t in x.get("Tags", "").split(",") if t.strip()],
        }
        cli.garantir(fone, x.get("Nome completo", ""), extra, _data_hora(x.get("Data de criação", "")))


def _reservas(cur, u: int, linhas: list[dict], cli: _Clientes, rec: list) -> dict:
    n = {"novas": 0, "atualizadas": 0, "iguais": 0}
    for i, x in enumerate(linhas, start=2):
        fone = telefone(x.get("Celular", ""))
        quando = _data_hora(x.get("Data e hora", ""))
        status = STATUS.get(x.get("Status", "").lower())
        try:
            pessoas = int(x.get("Pessoas") or 0)
        except ValueError:
            pessoas = 0
        motivo = ("celular fora do padrão" if not fone else "data e hora ilegíveis" if not quando
                  else f"status desconhecido: {x.get('Status')}" if not status
                  else "número de pessoas fora de 1 a 99" if not 1 <= pessoas <= 99 else None)
        if motivo:
            rec.append({"arquivo": "reservas", "linha": i, "nome": x.get("Nome completo"),
                        "motivo": motivo})
            continue
        id_cliente = cli.id_de(fone, x.get("Nome completo", ""))
        interna = " · ".join(p for p in (
            f"Mesa no LeadsFood: {x['Mesa']}" if x.get("Mesa") else "", x.get("Notas", "")) if p)
        criado = _data_hora(x.get("Data de criação", "")) or quando
        mudou = _data_hora(x.get("Última atualização", "")) or criado
        cur.execute(
            """INSERT INTO reservas (id_unidade, data, hora, pessoas, status, origem, nome,
                                     telefone, id_cliente, objetivo, observacao_cliente,
                                     observacao_interna, criado_em, status_em, importado_de)
               VALUES (%s, %s, %s, %s, %s, 'SITE', %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_unidade, telefone, data, hora) WHERE importado_de IS NOT NULL
               DO UPDATE SET status = EXCLUDED.status, status_em = EXCLUDED.status_em,
                             pessoas = EXCLUDED.pessoas
                       WHERE (reservas.status, reservas.pessoas)
                             IS DISTINCT FROM (EXCLUDED.status, EXCLUDED.pessoas)
               RETURNING (xmax = 0) AS nova""",
            (u, quando.date(), quando.time(), pessoas, status,
             (x.get("Nome completo") or "Sem nome")[:120], fone, id_cliente,
             (x.get("Objetivo") or None) and x["Objetivo"][:40],
             x.get("Observações") or None, interna or None, criado, mudou, MARCA))
        r = cur.fetchone()
        n["iguais" if r is None else "novas" if r["nova"] else "atualizadas"] += 1
    return n


def _selos(cur, u: int, linhas: list[dict], cli: _Clientes, rec: list) -> dict:
    """Um selo por check-in; vários no mesmo dia viram UMA visita com `selos` = quantos."""
    por_dia: dict[tuple[str, date], dict] = {}
    for i, x in enumerate(linhas, start=2):
        if x.get("status", "").lower() not in ("confirmado", ""):
            continue  # pendente ou cancelado lá não é selo
        fone = telefone(x.get("celular", ""))
        quando = _data_hora(x.get("criado_em", ""))
        if not fone or not quando:
            rec.append({"arquivo": "selos", "linha": i, "nome": x.get("nome"),
                        "motivo": "celular fora do padrão" if not fone else "data ilegível"})
            continue
        d = por_dia.setdefault((fone, quando.date()), {"nome": x.get("nome", ""), "selos": 0,
                                                        "primeiro": quando})
        d["selos"] += 1
        d["primeiro"] = min(d["primeiro"], quando)

    n = {"clientes": len({f for f, _ in por_dia}), "selos": 0, "dias": 0, "ja_tinham": 0,
         "retirados": 0, "conflitos": 0}
    no_arquivo: dict[int, set[date]] = defaultdict(set)
    for (fone, dia), d in sorted(por_dia.items(), key=lambda kv: kv[1]["primeiro"]):
        id_cliente = cli.id_de(fone, d["nome"])
        no_arquivo[id_cliente].add(dia)
        cur.execute("""SELECT selos, importado_de, id_premio FROM fidelidade_checkins
                        WHERE id_cliente = %s AND data = %s AND parte = 0""", (id_cliente, dia))
        existe = cur.fetchone()
        if existe:
            if existe["importado_de"] == MARCA:
                n["ja_tinham"] += 1
            else:
                # ⚠️ Visita registrada AQUI no mesmo dia: a daqui vale, a de lá não entra —
                # contar as duas daria selo em dobro pela mesma ida à casa.
                n["conflitos"] += 1
            continue
        cur.execute(
            """INSERT INTO fidelidade_checkins (id_cliente, id_unidade, data, criado_em, selos,
                                                parte, origem, motivo, importado_de)
               VALUES (%s, %s, %s, %s, %s, 0, 'VISITA', %s, %s)""",
            (id_cliente, u, dia, d["primeiro"], d["selos"], MOTIVO_SELO, MARCA))
        n["dias"] += 1
        n["selos"] += d["selos"]

    # A FOTO: o selo importado antes, ainda aberto, que não está no arquivo novo, sai.
    cur.execute("""SELECT id, id_cliente, data FROM fidelidade_checkins
                    WHERE importado_de = %s AND id_premio IS NULL""", (MARCA,))
    for s in cur.fetchall():
        if s["data"] not in no_arquivo.get(s["id_cliente"], set()):
            cur.execute("DELETE FROM fidelidade_checkins WHERE id = %s", (s["id"],))
            n["retirados"] += 1
    return n


def _premios(cur, u: int, linhas: list[dict], cli: _Clientes, rec: list) -> dict:
    cfg = fidelidade.config(cur)
    n = {"novos": 0, "atualizados": 0, "iguais": 0, "abertos": 0}
    for i, x in enumerate(linhas, start=2):
        fone = telefone(x.get("Celular", ""))
        vence = _data(x.get("Expiração", ""))
        if not fone or not vence:
            rec.append({"arquivo": "premios", "linha": i, "nome": x.get("Nome completo"),
                        "motivo": "celular fora do padrão" if not fone else "validade ilegível"})
            continue
        id_cliente = cli.id_de(fone, x.get("Nome completo", ""))
        uso = _data_hora(x.get("Data utilização", "")) if x.get("Status") == "Utilizado" else None
        if uso and uso.time() == time(0, 0):
            uso = datetime.combine(uso.date(), time(12, 0))
        # O LeadsFood não exporta quando o prêmio nasceu: volta a validade da casa a partir
        # do vencimento (aqui, nasce hoje e vence em `validade_dias`).
        vale_de = vence - timedelta(days=int(cfg["validade_dias"]) - 1)
        if uso and uso.date() < vale_de:
            vale_de = uso.date()
        emitido = datetime.combine(vale_de - timedelta(days=1), time(12, 0))
        cur.execute(
            """SELECT id, usado_em FROM fidelidade_premios
                WHERE id_cliente = %s AND vence_em = %s AND importado_de IS NOT NULL""",
            (id_cliente, vence))
        existe = cur.fetchone()
        if existe:
            # ⚠️ Só ANDA para usado: entregue aqui (usado_em sem marca de lá) não desfaz.
            if uso and not existe["usado_em"]:
                cur.execute("""UPDATE fidelidade_premios SET usado_em = %s, id_unidade_uso = %s
                                WHERE id = %s""", (uso, u, existe["id"]))
                n["atualizados"] += 1
            else:
                n["iguais"] += 1
        else:
            cur.execute(
                """INSERT INTO fidelidade_premios (id_cliente, id_unidade, codigo, premio, visitas,
                                                   dias_consumo, emitido_em, vence_em, vale_de,
                                                   usado_em, id_unidade_uso, importado_de)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (id_cliente, u, fidelidade._codigo(cur), (x.get("Descrição") or cfg["premio"])[:120],
                 cfg["visitas"], cfg["dias_consumo"], emitido, vence, vale_de, uso,
                 u if uso else None, MARCA))
            n["novos"] += 1
        if not uso and vence >= date.today():
            n["abertos"] += 1
    return n


def aplicar(cur, id_unidade: int, arquivos: dict[str, list[dict]], simular: bool) -> dict:
    """Importa o que veio (qualquer combinação dos quatro). Com `simular`, desfaz no fim."""
    cur.execute("SAVEPOINT importacao_leadsfood")
    cli = _Clientes(cur, id_unidade)
    recusados: list[dict] = []
    saida: dict = {}
    # ⚠️ Contatos PRIMEIRO: eles trazem gênero, nascimento e cidade; quem vier antes por uma
    # reserva nasceria com nome e telefone só, e os contatos então só completariam.
    if "contatos" in arquivos:
        _contatos(arquivos["contatos"], cli, recusados)
    if "reservas" in arquivos:
        saida["reservas"] = _reservas(cur, id_unidade, arquivos["reservas"], cli, recusados)
    if "selos" in arquivos:
        saida["selos"] = _selos(cur, id_unidade, arquivos["selos"], cli, recusados)
    if "premios" in arquivos:
        saida["premios"] = _premios(cur, id_unidade, arquivos["premios"], cli, recusados)
    saida["clientes"] = {"novos": cli.novos, "completados": cli.completados, "iguais": cli.iguais}
    saida["recusados"] = recusados
    saida["linhas"] = {k: len(v) for k, v in arquivos.items()}
    if simular:
        cur.execute("ROLLBACK TO SAVEPOINT importacao_leadsfood")
    else:
        cur.execute("RELEASE SAVEPOINT importacao_leadsfood")
    saida["aplicado"] = not simular
    return saida
