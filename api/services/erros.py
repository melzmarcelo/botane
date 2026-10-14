"""O erro que estourou sem ninguém tratar, guardado no banco (migração 112).

🔑 **Para o erro do ar poder ser lido sem o log da nuvem.** No incidente de 09 a
11/10/2026 a mensagem que fechou o diagnóstico só existia na tela de
Integrações, e foi o dono quem a colou. Agora todo 500 da API e toda falha
inesperada dos agendadores ficam aqui, com o traceback, e a tela de Auditoria os
mostra.

⚠️ **`registrar` NUNCA levanta.** Ele roda dentro do tratamento de outro erro: se
o registro falhasse e subisse, a exceção original — a que importa — seria
trocada pela dele, e o 500 viraria um 500 diferente, sobre o registro.
"""

import traceback

from database import get_cursor

# Posta por `main.py` no start: importar `main` daqui seria circular.
VERSAO: str | None = None

# O fim do traceback é o que diz onde quebrou; o começo é o caminho do
# framework até a rota, igual em todo erro.
TETO_DO_DETALHE = 8000

# 🔑 **O registro se poda sozinho.** Um erro em laço (um agendador que falha a
# cada minuto) não pode crescer a tabela para sempre — e uma rotina de limpeza
# separada seria mais uma coisa para alguém lembrar de agendar.
DIAS_GUARDADOS = 90


def registrar(origem: str, erro: BaseException, *, metodo: str | None = None,
              rota: str | None = None, id_usuario: int | None = None,
              id_unidade: int | None = None) -> int | None:
    """Grava o erro e devolve o número do registro — ou None, se nem isso deu."""
    detalhe = "".join(traceback.format_exception(type(erro), erro, erro.__traceback__))
    # ⚠️ Também no log do processo, como sempre foi: se o banco for justamente o
    # que caiu, o registro abaixo falha e o print é o único rastro.
    print(f"[botane] ERRO {origem} {metodo or ''} {rota or ''}\n{detalhe}", flush=True)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO erros_sistema (origem, metodo, rota, id_usuario, id_unidade,
                                              tipo, mensagem, detalhe, versao)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (origem, metodo, rota, id_usuario, id_unidade, type(erro).__name__,
                 str(erro).strip() or type(erro).__name__,
                 detalhe[-TETO_DO_DETALHE:], VERSAO),
            )
            numero = cur.fetchone()["id"]
            if numero % 100 == 0:
                cur.execute("DELETE FROM erros_sistema WHERE quando < now() - %s * interval '1 day'",
                            (DIAS_GUARDADOS,))
            return numero
    except Exception as e:  # noqa: BLE001 — ver a docstring do módulo
        print(f"[botane] o registro do erro também falhou: {type(e).__name__}: {e}", flush=True)
        return None


def listar(cur, limite: int = 50, origem: str | None = None) -> list[dict]:
    """Os mais recentes primeiro. O detalhe vai junto: é para ler, não para contar."""
    cur.execute(
        """SELECT e.id, e.quando, e.origem, e.metodo, e.rota, e.tipo, e.mensagem,
                  e.detalhe, e.versao, e.id_unidade, u.nome AS usuario
             FROM erros_sistema e LEFT JOIN usuarios u ON u.id = e.id_usuario
            WHERE %(origem)s::text IS NULL OR e.origem = %(origem)s
            ORDER BY e.quando DESC, e.id DESC
            LIMIT %(limite)s""",
        {"origem": origem, "limite": limite},
    )
    return [dict(r) for r in cur.fetchall()]
