"""Exclui as notas de entrada anteriores a uma data — estornando o que já entrou.

    python excluir_notas_antigas.py                      SIMULA (não apaga nada)
    python excluir_notas_antigas.py --aplicar            apaga (pede confirmação)
    python excluir_notas_antigas.py --aplicar --sim      apaga sem perguntar
    python excluir_notas_antigas.py --ate 2026-09-01     a data de corte (padrão)
    python excluir_notas_antigas.py --campo entrada      corta pela data de ENTRADA
    python excluir_notas_antigas.py --so-nao-lancadas    deixa as lançadas em paz

🔑 **Pedido do dono (09/09/2026):** *"cria um script para mim excluir todas as
notas anteriores a 01/09/2026"*.

⚠️ **A nota LANÇADA é estornada antes de sair, e isso não é opcional.** Os
movimentos dela estão em `estoque_movimentos`, que é append-only e **não tem
chave estrangeira** para a nota: apagar a nota direto deixaria o razão com 60
movimentos órfãos — o saldo continuaria contando mercadoria cuja origem
desapareceu, e ninguém teria como descobrir de onde ela veio. O estorno é o
caminho que o próprio sistema exige (`DELETE /notas/{id}` recusa nota lançada
com essa frase), e ele devolve o estoque ao que era antes daquela entrada.

⚠️ **O estorno MOVIMENTA o estoque.** Não é uma limpeza silenciosa: o saldo dos
produtos daquelas notas vai cair, e o custo médio vai se recalcular. Numa base
com inventário fechado depois daquelas notas, isso muda números que alguém já
conferiu. A simulação mostra quanto sai antes de qualquer escrita.

⚠️ **`--so-nao-lancadas` é a saída conservadora**: apaga só o que nunca tocou o
razão, e não mexe em saldo nenhum.

⚠️ **Tudo numa transação só.** Meio caminho aqui é pior que não começar: notas
estornadas e não apagadas deixariam o estoque baixado e os documentos de pé.

⚠️ **Faça um dump antes.** Isto não se desfaz — nem o estorno, que vira
movimento novo no razão.
"""

import argparse
import sys
from datetime import date, datetime

sys.path.insert(0, ".")

from config import ADMIN_EMAIL, DB_HOST, DB_NAME  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

CORTE_PADRAO = "2026-09-01"


def quem_assina(cur, pedido: int | None) -> int | None:
    """O usuário que fica no estorno e na auditoria.

    ⚠️ **Estorno sem dono é linha de razão sem ninguém a quem perguntar.** A
    coluna aceita nulo, mas seis meses depois "quem tirou 60 movimentos do
    estoque?" não tem resposta. Sem `--id-usuario`, assina o administrador da
    instalação — que é quem está rodando o script.
    """
    if pedido:
        return pedido
    cur.execute("SELECT id FROM usuarios WHERE email = %s", (ADMIN_EMAIL,))
    linha = cur.fetchone()
    return linha["id"] if linha else None


def _data(texto: str) -> date:
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"Data invalida: {texto!r} - use o formato AAAA-MM-DD.")


def levantar(cur, corte: date, campo: str) -> list[dict]:
    """As notas que entram no corte, com o peso de cada uma.

    ⚠️ **A coluna do corte é ESCOLHA de quem roda.** `data_emissao` é a data do
    documento — o que uma pessoa quer dizer com "notas anteriores a setembro".
    `data_entrada` é quando a mercadoria chegou, e é ela que decide em que mês a
    compra pesou no CMV. Nesta base as duas dão o mesmo conjunto, mas isso é
    coincidência do dado, não uma regra.
    """
    coluna = ("coalesce(data_entrada, data_emissao)" if campo == "entrada"
              else "data_emissao")
    cur.execute(
        f"""SELECT n.id, n.numero, n.serie, n.status, n.origem, n.valor_total,
                   n.data_emissao, n.data_entrada,
                   coalesce(f.nome, n.nome_emitente, '(sem fornecedor)') AS fornecedor,
                   (SELECT count(*) FROM nota_itens i WHERE i.id_nota = n.id) AS itens,
                   (SELECT count(*) FROM estoque_movimentos m
                     WHERE m.origem_tipo = 'NOTA' AND m.origem_id = n.id
                       AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                        WHERE e.id_estorno_de = m.id)) AS a_estornar
              FROM notas_entrada n
              LEFT JOIN fornecedores f ON f.id = n.id_fornecedor
             WHERE {coluna} IS NOT NULL AND {coluna} < %s
             ORDER BY {coluna}, n.id""",
        (corte,),
    )
    return [dict(r) for r in cur.fetchall()]


def resumir(notas: list[dict], corte: date, campo: str) -> None:
    por_status: dict[str, list[dict]] = {}
    for n in notas:
        por_status.setdefault(n["status"], []).append(n)

    print(f"\nBase: {DB_NAME} em {DB_HOST}")
    print(f"Corte: notas com {campo} ANTERIOR a {corte.strftime('%d/%m/%Y')}\n")
    if not notas:
        print("  Nenhuma nota nesse periodo. Nada a fazer.")
        return

    for status in sorted(por_status):
        linhas = por_status[status]
        valor = sum(float(x["valor_total"] or 0) for x in linhas)
        movs = sum(x["a_estornar"] for x in linhas)
        print(f"  {status:12} {len(linhas):4} nota(s)   R$ {valor:>12,.2f}"
              + (f"   {movs} movimento(s) a estornar" if movs else ""))

    total_movs = sum(x["a_estornar"] for x in notas)
    print(f"\n  TOTAL        {len(notas):4} nota(s)   "
          f"R$ {sum(float(x['valor_total'] or 0) for x in notas):>12,.2f}")

    if total_movs:
        # ⚠️ O número que muda a decisão fica em destaque: quem lê "53 notas"
        # não imagina que 60 movimentos de estoque vão junto.
        print(f"\n  ATENCAO: {total_movs} movimento(s) de estoque serao ESTORNADOS antes.")
        print("      O saldo dos produtos dessas notas vai cair e o custo medio")
        print("      sera recalculado. Use --so-nao-lancadas para evitar isso.")

    print("\n  As dez primeiras:")
    for n in notas[:10]:
        print(f"    #{n['id']:<6} NF {str(n['numero'] or '-'):<10} "
              f"{str(n['data_emissao'] or ''):<10} {n['status']:<11} "
              f"R$ {float(n['valor_total'] or 0):>10,.2f}  {n['fornecedor'][:34]}")
    if len(notas) > 10:
        print(f"    ... e mais {len(notas) - 10}.")


def executar(cur, notas: list[dict], id_usuario: int | None) -> dict:
    """Estorna o que precisa e apaga tudo. Numa transação só.

    ⚠️ **A ordem importa**: estornar depois de apagar é impossível (a nota já não
    existe para gerar a contrapartida), e apagar sem estornar deixa o razão
    órfão. Por isso as duas coisas acontecem por nota, na mesma passada.
    """
    import auditoria
    from services import estoque as motor

    estornados = 0
    for n in notas:
        if n["status"] == "LANCADA":
            cur.execute(
                """SELECT m.id FROM estoque_movimentos m
                    WHERE m.origem_tipo = 'NOTA' AND m.origem_id = %s
                      AND NOT EXISTS (SELECT 1 FROM estoque_movimentos e
                                       WHERE e.id_estorno_de = m.id)
                    ORDER BY m.id""",
                (n["id"],),
            )
            for (id_movimento,) in [(r["id"],) for r in cur.fetchall()]:
                motor.estornar(cur, id_movimento, id_usuario,
                               f"Exclusão da nota #{n['id']} (limpeza de histórico)")
                estornados += 1

        # 🔑 A auditoria fica ANTES do DELETE e guarda o que a nota era: depois
        # de apagada não há de onde recuperar o número, o fornecedor e o valor —
        # e "por que sumiu a NF 4812?" é a pergunta que vem seis meses depois.
        auditoria.registrar(
            cur, id_usuario, "nota", n["id"], "excluir_antiga",
            antes={"numero": n["numero"], "serie": n["serie"], "status": n["status"],
                   "origem": n["origem"], "fornecedor": n["fornecedor"],
                   "data_emissao": str(n["data_emissao"] or ""),
                   "valor_total": float(n["valor_total"] or 0), "itens": n["itens"]},
        )

    # ⚠️ `nota_itens` sai por CASCATA (a chave estrangeira já manda isso); o que
    # não sai sozinho são os movimentos, porque não há chave entre eles e a nota
    # — e é exatamente por isso que o estorno acontece acima.
    cur.execute("DELETE FROM notas_entrada WHERE id = ANY(%s)", ([n["id"] for n in notas],))
    return {"apagadas": cur.rowcount, "estornados": estornados}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--ate", default=CORTE_PADRAO,
                   help=f"data de corte, AAAA-MM-DD (padrão {CORTE_PADRAO})")
    p.add_argument("--campo", choices=("emissao", "entrada"), default="emissao",
                   help="qual data usar no corte (padrão: emissao)")
    p.add_argument("--aplicar", action="store_true", help="apaga de verdade")
    p.add_argument("--sim", action="store_true", help="não pergunta antes de apagar")
    p.add_argument("--so-nao-lancadas", action="store_true",
                   help="deixa as notas lançadas em paz — não mexe em estoque")
    p.add_argument("--id-usuario", type=int, default=None,
                   help="quem assina o estorno e a auditoria (padrao: o administrador)")
    args = p.parse_args()

    corte = _data(args.ate)
    init_pool()

    with get_cursor() as cur:
        notas = levantar(cur, corte, args.campo)

    if args.so_nao_lancadas:
        antes = len(notas)
        notas = [n for n in notas if n["status"] != "LANCADA"]
        if antes != len(notas):
            print(f"\n(--so-nao-lancadas: {antes - len(notas)} nota(s) lancada(s) "
                  f"ficam de fora)")

    resumir(notas, corte, args.campo)
    if not notas:
        return 0

    if not args.aplicar:
        print("\n  SIMULACAO - nada foi apagado.")
        print("  Para apagar de verdade: --aplicar")
        return 0

    print("\n  ATENCAO: isto NAO se desfaz. Faca um dump da base antes.")
    if not args.sim:
        # ⚠️ Confirmação DIGITADA, não um "s/n": o enter distraído não pode
        # apagar 53 notas. É a mesma trava do `limpar_dados.py`.
        esperado = f"apagar {len(notas)}"
        resposta = input(f'\n  Digite "{esperado}" para confirmar: ').strip()
        if resposta != esperado:
            print("  Cancelado - nada foi tocado.")
            return 1

    with get_cursor() as cur:
        r = executar(cur, notas, quem_assina(cur, args.id_usuario))

    print(f"\n  {r['apagadas']} nota(s) apagada(s)"
          + (f", {r['estornados']} movimento(s) estornado(s)." if r["estornados"] else "."))
    print("  Os itens sairam junto, por cascata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
