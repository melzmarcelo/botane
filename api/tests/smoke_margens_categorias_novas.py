"""A migração 138: as margens por categoria passam para as categorias novas.

🔑 Pedido do dono (27/10/2026): as 27 margens da configuração ficaram presas a
categorias que a reestruturação de 25/10 desativou. Esta suíte monta o cenário do ar
numa transação DESFEITA e roda o arquivo da migração por cima:

    1. com margens presas (categoria antiga desativada): as novas entram com o valor
       combinado e o mesmo nome; as antigas saem; a geral e o resto ficam;
    2. rodar de novo não muda nada (a migração é reaplicada se o arquivo mudar);
    3. linha que alguém já criou na categoria nova é mantida, com o valor dela;
    4. sem margem presa (a base de testes, uma loja nova) nada acontece.

    python tests/smoke_margens_categorias_novas.py      (não precisa da API)
"""

import os
import sys

sys.path.insert(0, ".")
from database import get_cursor, init_pool  # noqa: E402

ok = 0
falhas: list[str] = []
SQL = open(os.path.join("db_scripts", "138_margens_nas_categorias_novas.sql"),
           encoding="utf-8").read()


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


class Desfazer(Exception):
    pass


def categoria(cur, nome, ativa):
    cur.execute("SELECT id FROM categorias WHERE upper(nome) = %s ORDER BY id LIMIT 1", (nome,))
    r = cur.fetchone()
    if r:
        cur.execute("UPDATE categorias SET ativo = %s WHERE id = %s", (ativa, r["id"]))
        return r["id"]
    cur.execute("INSERT INTO categorias (nome, ativo) VALUES (%s, %s) RETURNING id", (nome, ativa))
    return cur.fetchone()["id"]


def linhas(cur, id_unidade):
    cur.execute("""SELECT l.nome, l.tipo, l.valor, l.alcance, upper(c.nome) AS categoria
                     FROM precificacao_linhas l LEFT JOIN categorias c ON c.id = l.id_categoria
                    WHERE l.id_unidade = %s ORDER BY l.id""", (id_unidade,))
    return [dict(r) for r in cur.fetchall()]


def cenario(nome, corpo):
    print(nome)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM unidades WHERE ativo ORDER BY id LIMIT 1")
            u = cur.fetchone()["id"]
            cur.execute("DELETE FROM precificacao_linhas WHERE id_unidade = %s", (u,))
            corpo(cur, u)
            raise Desfazer
    except Desfazer:
        pass


def com_presas(cur, u):
    cha = categoria(cur, "CHA", False)
    louca = categoria(cur, "MERCEARIA LOUCAS", False)
    categoria(cur, "BEBIDAS PREPARADAS", True)
    categoria(cur, "PRESENTES, LOUÇAS E ACESSÓRIOS", True)
    nova_doces = categoria(cur, "DOCES, BOLOS E SOBREMESAS", True)
    cur.execute("""INSERT INTO precificacao_linhas (id_unidade, nome, tipo, valor, alcance, id_categoria)
                   VALUES (%s, 'Impostos', 'PERCENTUAL', 11.2, 'TUDO', NULL),
                          (%s, 'Margem', 'MARGEM', 35.5, 'TUDO', NULL),
                          (%s, 'Margem', 'MARGEM', 48.5, 'CATEGORIA', %s),
                          (%s, 'Margem', 'MARGEM', 13.5, 'CATEGORIA', %s),
                          -- alguém já refez Doces na tela, com outro valor
                          (%s, 'Margem', 'MARGEM', 40, 'CATEGORIA', %s)""",
                (u, u, u, cha, u, louca, u, nova_doces))
    cur.execute(SQL)
    ls = linhas(cur, u)
    por_cat = {l["categoria"]: l for l in ls if l["alcance"] == "CATEGORIA"}
    checar("as antigas presas saem (Chá, Mercearia louças)",
           "CHA" not in por_cat and "MERCEARIA LOUCAS" not in por_cat, sorted(por_cat))
    checar("Bebidas preparadas entra com 38,5%, chamada 'Margem'",
           por_cat.get("BEBIDAS PREPARADAS", {}).get("valor") == 38.5
           and por_cat["BEBIDAS PREPARADAS"]["nome"] == "Margem", por_cat.get("BEBIDAS PREPARADAS"))
    checar("Presentes, louças e acessórios entra com 13,5%",
           float(por_cat.get("PRESENTES, LOUÇAS E ACESSÓRIOS", {}).get("valor") or 0) == 13.5)
    checar("a linha que já existia em Doces fica com o valor dela (40%)",
           float(por_cat.get("DOCES, BOLOS E SOBREMESAS", {}).get("valor") or 0) == 40.0)
    checar("a geral e os impostos ficam",
           any(l["alcance"] == "TUDO" and l["tipo"] == "MARGEM" and float(l["valor"]) == 35.5
               for l in ls)
           and any(l["nome"] == "Impostos" for l in ls))
    checar("Pratos preparados NÃO ganha linha (seria igual à geral)",
           "PRATOS PREPARADOS" not in por_cat)
    antes = linhas(cur, u)
    cur.execute(SQL)
    checar("rodar de novo não muda nada", linhas(cur, u) == antes)


def sem_presas(cur, u):
    cur.execute("""INSERT INTO precificacao_linhas (id_unidade, nome, tipo, valor, alcance)
                   VALUES (%s, 'Margem', 'MARGEM', 30, 'TUDO')""", (u,))
    antes = linhas(cur, u)
    cur.execute(SQL)
    checar("sem margem presa, nada acontece", linhas(cur, u) == antes, linhas(cur, u))


init_pool()
cenario("1-3. a configuração do ar: margens presas a categorias desativadas", com_presas)
cenario("\n4. sem margem presa", sem_presas)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
