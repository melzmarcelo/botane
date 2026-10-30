"""O Plano de ação das reservas — quem vale a pena chamar de volta.

🔑 **Pedido do dono (30/10/2026)**, depois de ver o LeadsFood que a casa usa: *"comece pelo
plano de ação de reservas"*. Três listas, cada uma com o botão de WhatsApp:

- **VIPs em risco** — reservaram muitas vezes e pararam de vir. Vínculo forte, recuperável.
- **Organizadores de grupo sumidos** — trouxeram grupos grandes e não voltaram. É o maior
  retorno por mensagem: uma resposta traz a mesa inteira.
- **Adormecidos** — vieram uma ou duas vezes e sumiram. O volume está aqui.

⚠️ **A pessoa é o TELEFONE, não o `id_cliente`.** A reserva do balcão não liga ao cadastro do
site (só a do site preenche `reservas.id_cliente`), e quem liga duas vezes pelo telefone e uma
pelo site é a mesma pessoa. O telefone é normalizado como o cadastro guarda (só dígitos, sem
o 55): é o que faz a reserva de balcão "(47) 99910-5033" e o cadastro "47999105033" caírem
juntos. Reserva sem telefone válido fica de fora — não haveria a quem mandar mensagem.

🔑 **Reserva que conta**: CONFIRMADA, CHEGOU ou ENCERRADA, em data que já passou (ou hoje).
CONFIRMADA no passado conta porque a casa nem sempre marca a chegada; contá-la como falta
puniria o cliente pelo esquecimento do balcão. Cancelada e não-comparecimento não contam
como visita (as faltas vêm à parte, como informação).

⚠️ **Quem já tem reserva marcada para frente não entra em lista nenhuma**: chamar de volta
quem já está voltando é a mensagem que faz a casa parecer desatenta.

⚠️ **Cada pessoa aparece numa lista só**, na ordem VIP → organizador → adormecido. O
organizador de dois grupos tem duas reservas e também caberia nos adormecidos; mandar duas
mensagens diferentes para ele seria pior que não mandar nenhuma.
"""

from datetime import date

# Os critérios, com o padrão que o LeadsFood usa — a casa já olha estes números lá.
PADRAO = {
    "vip_reservas": 3,       # VIP: pelo menos N reservas…
    "vip_dias": 120,         # …e sem vir há N dias
    "grupo_pessoas": 6,      # grupo grande: N pessoas ou mais
    "grupo_reservas": 2,     # organizador: pelo menos N grupos grandes…
    "grupo_dias": 120,       # …e sem vir há N dias
    "adormecido_max": 2,     # adormecido: até N reservas…
    "adormecido_dias": 90,   # …e sem vir há N dias
}

# 🔑 **Quem é a pessoa de uma reserva `r`** — usado aqui e no painel (`reservas_painel`).
# ⚠️ O telefone como o cadastro guarda: só dígitos e, se vier com o 55 do país, sem ele.
# `FONE_JUNTAS` vai no FROM, logo depois de `reservas r`; `FONE` é a expressão.
FONE_JUNTAS = r"""
          LEFT JOIN reserva_clientes c ON c.id = r.id_cliente
          CROSS JOIN LATERAL
               (SELECT regexp_replace(coalesce(r.telefone, ''), '\D', '', 'g') AS d) x"""
FONE = """coalesce(c.telefone,
                        CASE WHEN length(x.d) IN (12, 13) AND x.d LIKE '55%%'
                             THEN substr(x.d, 3) ELSE x.d END)"""

_SQL = f"""
    WITH base AS (
        SELECT r.id, r.data, r.pessoas, r.status, r.nome,
               {FONE} AS fone,
               r.status IN ('CONFIRMADA', 'CHEGOU', 'ENCERRADA')
                   AND r.data <= current_date AS conta
          FROM reservas r
          {FONE_JUNTAS}
         WHERE r.id_unidade = %(unidade)s
    ), por_fone AS (
        SELECT fone,
               count(*) FILTER (WHERE conta) AS reservas,
               count(*) FILTER (WHERE conta AND pessoas >= %(grupo_pessoas)s) AS grupos,
               coalesce(sum(pessoas) FILTER (WHERE conta), 0) AS pessoas,
               coalesce(max(pessoas) FILTER (WHERE conta), 0) AS maior_grupo,
               count(*) FILTER (WHERE status = 'NAO_COMPARECEU') AS faltas,
               max(data) FILTER (WHERE conta) AS ultima,
               bool_or(status IN ('PENDENTE', 'CONFIRMADA') AND data >= current_date) AS vem,
               (array_agg(nome ORDER BY data DESC, id DESC))[1] AS nome_reserva
          FROM base
         WHERE length(fone) BETWEEN 10 AND 11
         GROUP BY fone
    )
    SELECT p.fone AS telefone, coalesce(c.nome, p.nome_reserva) AS nome, c.id AS id_cliente,
           p.reservas, p.grupos, p.pessoas, p.maior_grupo, p.faltas, p.ultima,
           (current_date - p.ultima) AS dias,
           c.whatsapp_optout_em IS NOT NULL AS nao_quer_whatsapp
      FROM por_fone p
      LEFT JOIN reserva_clientes c ON c.telefone = p.fone
     WHERE p.reservas > 0 AND NOT p.vem
"""


def criterios(**informados) -> dict:
    """Os critérios do pedido, com o padrão no que não veio."""
    return {k: (informados.get(k) if informados.get(k) is not None else v)
            for k, v in PADRAO.items()}


def classificar(linha: dict, c: dict) -> str | None:
    """Em que lista a pessoa cai — UMA só, na ordem VIP → organizador → adormecido.

    Função pura (sem banco), para a regra poder ser lida e testada sozinha.
    """
    dias = linha["dias"]
    if linha["reservas"] >= c["vip_reservas"] and dias >= c["vip_dias"]:
        return "vips"
    if linha["grupos"] >= c["grupo_reservas"] and dias >= c["grupo_dias"]:
        return "organizadores"
    if linha["reservas"] <= c["adormecido_max"] and dias >= c["adormecido_dias"]:
        return "adormecidos"
    return None


def plano(cur, id_unidade: int, c: dict) -> dict:
    """As três listas da loja, com o resumo no topo."""
    cur.execute(_SQL, {"unidade": id_unidade, "grupo_pessoas": c["grupo_pessoas"]})
    listas: dict[str, list[dict]] = {"vips": [], "organizadores": [], "adormecidos": []}
    for linha in cur.fetchall():
        lista = classificar(linha, c)
        if lista:
            x = dict(linha)
            x["ultima"] = x["ultima"].isoformat() if isinstance(x["ultima"], date) else x["ultima"]
            listas[lista].append(x)
    # A ordem que a tela abre: o mais forte primeiro (a tela reordena se a pessoa pedir).
    listas["vips"].sort(key=lambda x: (-x["reservas"], -x["dias"]))
    listas["organizadores"].sort(key=lambda x: (-x["grupos"], -x["pessoas"]))
    listas["adormecidos"].sort(key=lambda x: (x["dias"], x["nome"] or ""))

    # ⚠️ O nome que vai na mensagem é o que o CLIENTE conhece: o fantasia da empresa. O
    # apelido da loja ("Matriz") é nome interno — "Aqui é do Matriz" não diz nada a ninguém.
    cur.execute(
        """SELECT coalesce(nullif(trim((SELECT nome_fantasia FROM empresa LIMIT 1)), ''),
                           u.nome) AS loja
             FROM unidades u WHERE u.id = %s""",
        (id_unidade,))
    loja = (cur.fetchone() or {}).get("loja")
    return {
        "loja": loja,
        "criterios": c,
        "resumo": {"total": sum(len(v) for v in listas.values()),
                   **{k: len(v) for k, v in listas.items()}},
        **listas,
    }
