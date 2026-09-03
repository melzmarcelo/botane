"""Junta, de uma vez, os cadastros que têm exatamente o mesmo nome.

    python vincular_por_nome.py --simular          mostra os grupos, sem mexer
    python vincular_por_nome.py --simular --so-omie  só os que vieram do Omie
    python vincular_por_nome.py --sim              executa (pede confirmação sem isto)
    python vincular_por_nome.py --sem-baixa        não baixa o que foi vendido e não saiu

🔑 **O caso do ABACATE, em lote** (pedido do dono, 03/09/2026). O catálogo do
Omie cria um cadastro por CÓDIGO, e o mesmo abacate aparece uma vez para cada
fornecedor que já o vendeu. Juntar de dois em dois pela tela do Vincular resolve,
mas com centenas de repetidos ninguém percorre a lista — e o trabalho não é feito.

⚠️ **Por que isto é um script e NÃO uma migração.** Migração roda sozinha no
start da API, sobre a base de produção, sem ninguém ver a lista — e **fusão não
tem desfazer**. Um nome repetido é um sinal forte dentro de um catálogo só, mas
continua sendo um sinal: "VALE-PRESENTE" pode ser três valores diferentes, e o
mapeador do Omie **apara todo texto no tamanho da coluna**, o que faz dois nomes
longos e diferentes chegarem aqui iguais. A regra da casa é que a fusão sempre
mostra a prévia antes; uma migração seria a única operação do projeto que junta
centenas de cadastros sem que ninguém tenha olhado.

⚠️ **`--simular` primeiro, sempre.** Ele imprime cada grupo com os códigos de
cada cadastro, que é o que permite reconhecer o "VALE-PRESENTE" antes de juntar.

⚠️ **Grupo com DOIS que têm história é pulado**, não forçado: unir dois razões
exigiria reescrever movimento, e o custo médio resultante seria invenção. Eles
aparecem na saída como pulados, com o motivo.

⚠️ A mesma detecção alimenta a tela **Produtos ▸ Cadastros com o mesmo nome**,
que é o caminho para quem prefere olhar grupo a grupo. Nenhum dos dois tem lógica
própria: os dois chamam `produtos_vinculo`.
"""

import sys

sys.path.insert(0, ".")

from config import ADMIN_EMAIL  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402
from services import produtos_vinculo  # noqa: E402


def _quem_assina(cur) -> int | None:
    """A fusão vai para a auditoria, e auditoria sem autor não serve de nada."""
    cur.execute("SELECT id FROM usuarios WHERE email = %s", (ADMIN_EMAIL,))
    linha = cur.fetchone()
    if linha:
        return linha["id"]
    cur.execute("SELECT id FROM usuarios WHERE ativo ORDER BY id LIMIT 1")
    return (cur.fetchone() or {}).get("id")


def main() -> int:
    argumentos = set(sys.argv[1:])
    simular = "--simular" in argumentos
    sem_perguntar = "--sim" in argumentos
    so_omie = "--so-omie" in argumentos
    baixar = "--sem-baixa" not in argumentos

    init_pool()
    with get_cursor() as cur:
        grupos = produtos_vinculo.grupos_por_nome(cur, so_do_omie=so_omie, limite=1000)

    if not grupos:
        print("Nenhum cadastro repetido pelo nome" + (" entre os do Omie" if so_omie else "")
              + ". Nada a juntar.")
        return 0

    prontos = [g for g in grupos if g["pode"]]
    pulados = [g for g in grupos if not g["pode"]]
    a_juntar = sum(g["quantos"] - 1 for g in prontos)

    print(f"{len(grupos)} nome(s) repetido(s). "
          f"{len(prontos)} pronto(s), {len(pulados)} pulado(s) por história.\n")
    for g in grupos:
        marca = "  " if g["pode"] else "! "
        print(f"{marca}{g['nome']}  ({g['quantos']} cadastros)")
        for i in g["itens"]:
            papel = ("FICA " if i["id"] == g["id_principal"]
                     else "sai  " if not i["travas"] else "TRAVA")
            codigos = " ".join(filter(None, [
                f"omie:{i['codigo_omie']}" if i["codigo_omie"] else None,
                f"pdv:{i['codigo_pdv']}" if i["codigo_pdv"] else None,
            ])) or "sem código externo"
            print(f"      {papel} {i['codigo']:<18} {codigos}"
                  + (f"  [{'; '.join(i['travas'])}]" if i["travas"] else ""))
        print()

    if pulados:
        print("! = mais de um cadastro do grupo tem história (razão, mês fechado, inventário"
              " ou produção). Esses ficam como estão.\n")

    if simular:
        print(f"(--simular: nada foi feito. Seriam {a_juntar} cadastro(s) absorvido(s).)")
        return 0

    if not prontos:
        print("Nada a juntar: todos os grupos têm mais de um cadastro com história.")
        return 0

    print(f"Isto vai absorver {a_juntar} cadastro(s) em {len(prontos)} cadastro(s) principais.")
    print("⚠️  A fusão NÃO tem desfazer.")
    if not sem_perguntar:
        # ⚠️ Confirmação DIGITADA, como no `limpar_dados.py`: um "s" apertado sem
        # ler é o mesmo que não perguntar.
        if input('Digite "juntar" para continuar: ').strip().lower() != "juntar":
            print("Cancelado — nada foi feito.")
            return 1

    id_usuario = None
    with get_cursor() as cur:
        id_usuario = _quem_assina(cur)

    feitos, erros = 0, []
    for g in prontos:
        saem = [i["id"] for i in g["itens"] if i["id"] != g["id_principal"]]
        try:
            # ⚠️ **Uma transação por GRUPO.** Falhando um grupo, os anteriores
            # continuam feitos — que é um estado bom, não pela metade: cada grupo
            # é a mesma operação repetida. É a lição do envio ao PDV, onde o laço
            # inteiro numa transação só desfez 29 registros já gravados do outro
            # lado.
            with get_cursor() as cur:
                produtos_vinculo.fundir_grupo(cur, g["id_principal"], saem,
                                              id_usuario, baixar)
            feitos += len(saem)
            print(f"  ok   {g['nome']}: {len(saem)} absorvido(s)")
        except Exception as e:  # noqa: BLE001 — um grupo ruim não derruba o resto
            erros.append((g["nome"], str(e)))
            print(f"  FALHA {g['nome']}: {e}")

    print(f"\n{feitos} cadastro(s) absorvido(s).")
    if erros:
        print(f"{len(erros)} grupo(s) falharam e ficaram como estavam.")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
