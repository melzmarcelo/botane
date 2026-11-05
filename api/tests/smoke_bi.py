"""O Estúdio BI e a tela de Relatórios (layout novo, fases 3 e 4 — 05/11/2026).

🔑 **Pedido do dono:** relatórios padrão num lugar só, e *"um menu estilo BI, onde o usuário
administrador pode criar relatórios personalizados com suas ligações configuráveis"*.

Confere o que importa para a SEGURANÇA e para o NÚMERO:
1. a lista branca: nome fora dela é 422, ligação manual só por coluna de ligação;
2. a conta bate com o banco (cupons e faturamento de um período, por SQL independente);
3. as regras de montagem: soma no grão errado, fonte solta, "manter todos" com o recorte no ON;
4. salvar, alterar, nome repetido, apagar, rodar, imprimir e gerar planilha;
5. quem vê: EU, TODOS e PAPEIS, com o usuário de Cozinha das suítes;
6. Relatórios: o catálogo traz a área de cada um e a prévia em dados bate com a contagem.
Nomes de teste com o prefixo `Smoke BI`, apagados no começo e no fim.

    python tests/smoke_bi.py        (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from comum import garantir_cozinha  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            corpo_r = r.read()
            if bruto:
                return r.status, (r.headers.get("Content-Type") or "", corpo_r)
            return r.status, json.loads(corpo_r or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, None


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def limpar():
    with get_cursor() as cur:
        cur.execute("DELETE FROM bi_relatorios WHERE nome LIKE 'Smoke BI%%'")


init_pool()
_st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
cozinha = garantir_cozinha(chamar, token)
limpar()

DE, ATE = "2026-10-01", "2026-10-31"
BASE_DEF = {"fontes": ["vendas"], "dimensoes": ["vendas.mes"], "medidas": ["vendas.cupons", "vendas.faturado"],
            "de": DE, "ate": ATE}
try:
    print("1. a lista branca")
    st, cat = chamar("GET", "/bi/fontes", token=token)
    chaves = [f["chave"] for f in cat["fontes"]]
    checar("o catálogo traz as fontes e as ligações conhecidas",
           st == 200 and {"vendas", "itens", "produtos", "notas"} <= set(chaves) and cat["relacoes"], chaves)
    for nome, corpo in [
        ("fonte com SQL", {"fontes": ["vendas;DROP TABLE produtos"], "medidas": ["vendas.cupons"]}),
        ("campo que não existe", {"fontes": ["vendas"], "medidas": ["vendas.senha"]}),
        ("campo de fonte não escolhida", {"fontes": ["vendas"], "medidas": ["notas.valor"]}),
        ("dimensão no lugar de medida", {"fontes": ["vendas"], "medidas": ["vendas.mes"]}),
        ("sem medida", {"fontes": ["vendas"], "dimensoes": ["vendas.mes"]}),
        ("ligação manual por coluna que não é de ligação",
         {"fontes": ["vendas", "clientes"], "medidas": ["vendas.cupons"],
          "manuais": [{"a": "vendas", "ca": "valor_total", "b": "clientes", "cb": "id"}]}),
    ]:
        st, rr = chamar("POST", "/bi/consultar", corpo, token)
        checar(f"recusa {nome} (422)", st == 422, (st, rr))

    print("\n2. a conta bate com o banco")
    st, res = chamar("POST", "/bi/consultar", BASE_DEF, token)
    with get_cursor() as cur:
        cur.execute("""SELECT count(*) AS n, coalesce(sum(valor_total), 0) AS v FROM vendas
                        WHERE id_unidade = 1 AND NOT cancelada AND NOT consumo_interno
                          AND data BETWEEN %s AND %s""", (DE, ATE))
        esperado = cur.fetchone()
    linha = res["linhas"][0] if res.get("linhas") else [None, 0, 0]
    checar("cupons e faturado de outubro iguais ao SQL direto",
           st == 200 and int(linha[1] or 0) == esperado["n"]
           and abs(float(linha[2] or 0) - float(esperado["v"])) < 0.01, (linha, dict(esperado)))
    checar("o SQL vem legível, só leitura de fato (SELECT) e com o recorte da loja",
           res["sql"].startswith("SELECT") and "vendas.id_unidade = 1" in res["sql"] and "LIMIT" in res["sql"])
    st, ind = chamar("POST", "/bi/consultar", {**BASE_DEF, "dimensoes": []}, token)
    checar("sem dimensão, uma linha só com os totais (os indicadores)",
           st == 200 and len(ind["linhas"]) == 1 and int(ind["linhas"][0][0]) == esperado["n"], ind.get("linhas"))

    print("\n3. as regras de montagem")
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["itens", "vendas"], "dimensoes": ["vendas.canal"], "medidas": ["vendas.faturado"]}, token)
    checar("soma do cupom com os itens junto é recusada, com a explicação",
           st == 422 and "repete" in (rr or {}).get("detail", ""), rr)
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["itens", "vendas"], "dimensoes": ["vendas.canal"], "medidas": ["vendas.cupons", "itens.valor"]}, token)
    checar("contagem distinta do cupom com os itens junto vale", st == 200, rr)
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["vendas", "clientes"], "dimensoes": ["clientes.cidade"], "medidas": ["vendas.cupons"]}, token)
    checar("fonte sem ligação é recusada", st == 422 and "Sem ligação" in (rr or {}).get("detail", ""), rr)
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["itens"], "dimensoes": [], "medidas": ["itens.quantidade"]}, token)
    checar("itens da venda trazem Vendas junto (é por ela que se sabe a loja)",
           st == 200 and "JOIN vendas AS vendas" in rr["sql"] and "vendas.id_unidade" in rr["sql"], rr.get("sql"))
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["notas", "fornecedores"], "dimensoes": ["fornecedores.nome"], "medidas": ["notas.notas"],
                     "tipos": {"notas.id_fornecedor-fornecedores.id": "LEFT"}}, token)
    checar("'manter todos' vira LEFT JOIN", st == 200 and "LEFT JOIN fornecedores" in rr["sql"], rr.get("sql"))
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["fornecedores", "notas"], "dimensoes": ["fornecedores.nome"], "medidas": ["notas.notas"],
                     "tipos": {"notas.id_fornecedor-fornecedores.id": "LEFT"}, "de": DE}, token)
    on = rr["sql"].split("LEFT JOIN notas_entrada AS notas ON", 1)[-1].split("GROUP BY")[0] if st == 200 else ""
    checar("no LEFT, o recorte da fonte nova (loja e período) vai no ON, não no WHERE",
           st == 200 and "notas.id_unidade" in on and "WHERE" not in on.split("\n")[0], rr.get("sql"))
    st, rr = chamar("POST", "/bi/consultar",
                    {"fontes": ["vendas", "lojas"], "dimensoes": ["lojas.nome"], "medidas": ["vendas.cupons"],
                     "manuais": [{"a": "vendas", "ca": "id_unidade", "b": "lojas", "cb": "id"}],
                     "tipos": {"vendas.id_unidade-lojas.id": "NENHUMA"}}, token)
    checar("ligação manual por coluna de ligação vale (e 'não ligar' tira a sugerida)",
           st == 200 and rr["sql"].count("JOIN unidades") == 1, rr)

    print("\n4. salvar, rodar e imprimir")
    corpo = {"nome": "Smoke BI cupons", "definicao": BASE_DEF, "visibilidade": "EU", "papeis_vistos": [], "no_menu": True}
    st, novo = chamar("POST", "/bi/relatorios", corpo, token)
    id_rel = (novo or {}).get("id")
    checar("salva", st == 200 and id_rel, novo)
    st, _ = chamar("POST", "/bi/relatorios", corpo, token)
    checar("nome repetido: 409", st == 409, st)
    st, _ = chamar("POST", "/bi/relatorios", {**corpo, "nome": "Smoke BI ruim",
                                              "definicao": {"fontes": ["vendas"], "medidas": ["vendas.nada"]}}, token)
    checar("definição que não monta não se salva (422)", st == 422, st)
    st, _ = chamar("POST", "/bi/relatorios", {**corpo, "nome": "Smoke BI papeis", "visibilidade": "PAPEIS"}, token)
    checar("PAPEIS sem papel: 422", st == 422, st)
    st, lst = chamar("GET", "/bi/relatorios", token=token)
    checar("aparece na lista", any(x["id"] == id_rel for x in lst or []), lst)
    st, ex = chamar("POST", f"/bi/relatorios/{id_rel}/executar", {}, token)
    checar("roda salvo, igual à consulta", st == 200 and ex["linhas"] == res["linhas"], (ex or {}).get("linhas"))
    st, ex2 = chamar("POST", f"/bi/relatorios/{id_rel}/executar", {"de": "2026-10-15", "ate": "2026-10-15"}, token)
    with get_cursor() as cur:
        cur.execute("""SELECT count(*) AS n FROM vendas WHERE id_unidade = 1 AND NOT cancelada
                         AND NOT consumo_interno AND data = '2026-10-15'""")
        n15 = cur.fetchone()["n"]
    checar("o período de quem roda substitui o salvo",
           st == 200 and sum(int(x[1]) for x in ex2["linhas"]) == n15, (ex2.get("linhas"), n15))
    st, (tipo, pdf) = chamar("GET", f"/bi/relatorios/{id_rel}/exportar?formato=pdf", token=token, bruto=True)
    checar("Imprimir gera PDF", st == 200 and "pdf" in tipo and pdf[:4] == b"%PDF", (st, tipo))
    st, (tipo, csv) = chamar("GET", f"/bi/relatorios/{id_rel}/exportar?formato=csv", token=token, bruto=True)
    checar("Gerar planilha traz as colunas do relatório", st == 200 and "Nº de vendas" in csv.decode("utf-8", "ignore"), st)
    st, _ = chamar("PUT", f"/bi/relatorios/{id_rel}", {**corpo, "nome": "Smoke BI cupons por mês"}, token)
    _st, um = chamar("GET", f"/bi/relatorios/{id_rel}", token=token)
    checar("altera o nome", st == 200 and um["nome"] == "Smoke BI cupons por mês", um)

    print("\n5. quem vê")
    if not cozinha:
        checar("o usuário de Cozinha das suítes existe", False)
    else:
        st, _ = chamar("GET", "/bi/fontes", token=cozinha)
        checar("Cozinha não abre o estúdio (403)", st == 403, st)
        st, _ = chamar("POST", "/bi/consultar", BASE_DEF, cozinha)
        checar("nem consulta livre (403)", st == 403, st)
        st, _ = chamar("GET", f"/bi/relatorios/{id_rel}", token=cozinha)
        checar("relatório 'só eu' de outro usuário: 404 (nem existe para ele)", st == 404, st)
        st, _ = chamar("PUT", f"/bi/relatorios/{id_rel}", {**corpo, "nome": "Smoke BI cupons por mês",
                                                          "visibilidade": "TODOS"}, token)
        st, _ = chamar("GET", f"/bi/relatorios/{id_rel}", token=cozinha)
        checar("TODOS exige 'ver os relatórios personalizados' (Cozinha não tem): 404", st == 404, st)
        _st, papeis = chamar("GET", "/papeis", token=token)
        id_coz = next((p["id"] for p in papeis if p["nome"] == "Cozinha"), None)
        chamar("PUT", f"/bi/relatorios/{id_rel}", {**corpo, "nome": "Smoke BI cupons por mês",
                                                   "visibilidade": "PAPEIS", "papeis_vistos": [id_coz]}, token)
        st, lc = chamar("GET", "/bi/relatorios", token=cozinha)
        st2, exc = chamar("POST", f"/bi/relatorios/{id_rel}/executar", {}, cozinha)
        checar("publicado para o papel Cozinha: aparece e roda, mesmo sem a permissão de vendas",
               any(x["id"] == id_rel and not x["pode_editar"] for x in lc or []) and st2 == 200
               and exc["linhas"] == res["linhas"], (st2, exc if st2 != 200 else ""))
        st, _ = chamar("PUT", f"/bi/relatorios/{id_rel}", corpo, cozinha)
        checar("mas não edita (403)", st == 403, st)

    print("\n6. Relatórios: catálogo e prévia")
    st, catalogo = chamar("GET", "/exportar/catalogo", token=token)
    checar("cada relatório do catálogo traz a área", st == 200 and all(x.get("grupo") for x in catalogo),
           [x["chave"] for x in catalogo if not x.get("grupo")])
    checar("e nenhum cai em 'Outros' (área esquecida em GRUPOS)",
           not [x["chave"] for x in catalogo if x["grupo"] == "Outros"],
           [x["chave"] for x in catalogo if x["grupo"] == "Outros"])
    st, dados = chamar("GET", "/exportar/saldos/dados", token=token)
    st2, prev = chamar("GET", "/exportar/saldos/previa", token=token)
    checar("a prévia em dados traz colunas, até 200 linhas e o total igual ao da contagem",
           st == 200 and dados["colunas"] and len(dados["linhas"]) <= 200
           and dados["total"] == prev["linhas"], (dados.get("total"), (prev or {}).get("linhas")))
    st, _ = chamar("GET", "/exportar/nao-existe/dados", token=token)
    checar("relatório que não existe: 404", st == 404, st)

    print("\n7. apagar")
    st, _ = chamar("DELETE", f"/bi/relatorios/{id_rel}", token=token)
    st2, _ = chamar("GET", f"/bi/relatorios/{id_rel}", token=token)
    checar("apaga, e depois some", st == 200 and st2 == 404, (st, st2))
    st, _ = chamar("GET", "/bi/relatorios")
    checar("sem login: 401", st == 401, st)
finally:
    limpar()

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
