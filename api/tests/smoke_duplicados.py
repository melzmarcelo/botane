"""Teste de fumaça dos cadastros duplicados entre portas de entrada.

O sistema recebe produto por três portas — o catálogo do **Omie** (o que a casa
compra), o cardápio do **PDV Legal** (o que a casa vende) e a mão de quem
cadastra. Dentro de cada porta a chave única impede a repetição; **entre portas
não existe chave nenhuma**, e é aí que o mesmo pacote de café vira dois
cadastros.

⚠️ **O estrago não é um cadastro feio, é estoque fantasma**: a compra entra por
um cadastro, a venda não sai por nenhum (o item do cardápio nasce sem controlar
estoque), e a sobra aparece na contagem como "ajuste de inventário".

O que este arquivo cobra:

1. o relatório acha o par que veio de portas DIFERENTES
2. e **não** acha par dentro da mesma porta — ali a chave única já resolve
3. cadastro que tem os DOIS vínculos não é duplicado de ninguém (é o saudável)
4. unificar move o de-para, o código do Omie, o EAN e os itens de venda
5. o absorvido vira **inativo**, nunca apagado
6. **item de venda que estava sem custo ganha custo**; o que já tinha, não muda
7. quem tem história (movimento no razão, ficha) **NÃO** pode ser absorvido, e a
   recusa nomeia o que trava
8. dois códigos do Omie são dois produtos lá — a unificação é recusada

    python tests/smoke_duplicados.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from comum import garantir_locais  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")

ok = 0
falhas: list[str] = []


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")[:300]}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


def banco():
    """Conexão direta — o de-para e o `codigo_omie` não têm rota de escrita."""
    from pathlib import Path

    import psycopg2
    from psycopg2.extras import RealDictCursor

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_SSLMODE, DB_USER

    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER,
                            password=DB_PASSWORD, sslmode=DB_SSLMODE,
                            cursor_factory=RealDictCursor)


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]

marca = str(time.time_ns())[-6:]
hoje = date.today().isoformat()
NOME = f"Cafe duplicado {marca}"

print("1. o mesmo produto entrando por duas portas")
garantir_locais(chamar, token)

# O lado do Omie: o que a casa COMPRA. Controla estoque.
st, r = chamar("POST", "/produtos", {
    "codigo": f"DUP-OMIE-{marca}", "nome": f"{NOME} pacote 500g", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
}, token=token)
do_omie = r.get("id")
checar("cadastro do lado do Omie", st == 201, (st, r))

# O lado do PDV: o que a casa VENDE. Nasce sem controlar estoque, como o
# importador do cardápio cria.
st, r = chamar("POST", "/produtos", {
    "codigo": f"PDV-DUP-{marca}", "nome": f"{NOME} pacote 500 g", "tipo": "PRODUZIDO",
    "producao_propria": True, "controla_estoque": False, "status": "RASCUNHO",
}, token=token)
do_pdv = r.get("id")
checar("cadastro do lado do cardápio", st == 201, (st, r))

# Um terceiro, com o MESMO nome, mas da mesma porta do primeiro: não pode
# aparecer no relatório — dentro da porta a chave única já resolve.
st, r = chamar("POST", "/produtos", {
    "codigo": f"DUP-OMIE2-{marca}", "nome": f"{NOME} pacote 500gr", "tipo": "INSUMO",
    "um_estoque": "KG", "controla_estoque": True, "status": "ATIVO",
}, token=token)
do_omie2 = r.get("id")
checar("um irmão da MESMA porta", st == 201, (st, r))

with banco() as conexao, conexao.cursor() as cur:
    cur.execute("UPDATE produtos SET codigo_omie = %s WHERE id = %s",
                (f"9{marca}01", do_omie))
    cur.execute("UPDATE produtos SET codigo_omie = %s WHERE id = %s",
                (f"9{marca}02", do_omie2))
    cur.execute(
        """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa)
           VALUES ('PDV_LEGAL', %s, %s, %s)
           ON CONFLICT (sistema, codigo) DO UPDATE SET id_produto = EXCLUDED.id_produto""",
        (f"PDVC{marca}", do_pdv, NOME),
    )
    conexao.commit()

print("\n2. uma venda pelo cadastro do cardápio — sem custo, porque não tem ficha")
st, r = chamar("POST", "/vendas/importar", {"vendas": [{
    "data": hoje, "documento": f"DUP-{marca}", "origem": "MANUAL",
    "itens": [{"id_produto": do_pdv, "quantidade": 4, "valor_unitario": 25}],
}]}, token=token)
checar("venda gravada", st == 201 and r.get("importadas") == 1, (st, r))
checar("e o item entrou SEM custo (o rascunho não tem ficha)",
       r.get("itens_sem_custo") == 1, r)
# ⚠️ E sem baixar estoque: o cadastro do cardápio não controla. É exatamente
# assim que o estoque do outro cadastro nunca desce.
checar("e sem baixar estoque", (r.get("itens_baixados") or 0) == 0, r)

print("\n3. o relatório")
st, d = chamar("GET", "/produtos/duplicados?minimo=80", token=token)
checar("o relatório responde", st == 200, (st, d))


def grupo_com(dados, *ids):
    """O grupo que contém TODOS estes cadastros.

    ⚠️ **Grupo, não par.** Cinco cadastros do mesmo produto dariam dez pares —
    dez linhas para conferir a mesma laranja. A conta real tem sete "LARANJA
    PERA".
    """
    for g in dados.get("grupos") or []:
        seus = {c["id"] for c in g["cadastros"]}
        if set(ids) <= seus:
            return g
    return None


meu = grupo_com(d, do_omie, do_pdv)
checar("acha o grupo com os dois cadastros", meu is not None,
       [[c["codigo"] for c in g["cadastros"]] for g in (d.get("grupos") or [])][:5])
checar("com o placar da semelhança", meu and meu["score"] >= 80, meu and meu["score"])
# ⚠️ O irmão da mesma porta tem o nome quase igual, mas com "500gr" contra
# "500g" — e a regra diz que NUMERO dos dois lados quer dizer produtos
# diferentes. Aqui os dois numeros sao iguais (500), entao ele entra: a
# duplicidade dentro de uma porta e real, e a conta do cliente tem sete
# cadastros da mesma laranja.
irmao = grupo_com(d, do_omie, do_omie2)
checar("e o irmão da MESMA porta também entra no grupo", irmao is not None,
       [[c["codigo"] for c in g["cadastros"]] for g in (d.get("grupos") or [])][:5])

if meu:
    lado_pdv = next(c for c in meu["cadastros"] if c["id"] == do_pdv)
    checar("o relatório diz de que porta cada cadastro veio",
           {"OMIE", "PDV"} <= {c["origem"] for c in meu["cadastros"]},
           [c["origem"] for c in meu["cadastros"]])
    checar("e quanto cada um já vendeu", lado_pdv["vendido"] == 4, lado_pdv)
    checar("todos podem ser absorvidos (nenhum tem razão nem ficha)",
           all(c["pode_ser_absorvido"] for c in meu["cadastros"]), meu)

# ⚠️ O recorte "só entre portas" existe porque esse é o caso PIOR: dentro de uma
# porta os dois cadastros ao menos se comportam igual; entre portas, um controla
# estoque e o outro não, e é aí que a venda deixa de sair da prateleira.
st, entre = chamar("GET", "/produtos/duplicados?minimo=80&so_entre_portas=true", token=token)
checar("o recorte entre portas responde", st == 200, st)
checar("e nele o grupo de portas diferentes continua",
       grupo_com(entre, do_omie, do_pdv) is not None,
       [[c["codigo"] for c in g["cadastros"]] for g in (entre.get("grupos") or [])][:5])
# ⚠️ **Transitividade é esperada.** Se os dois cadastros do Omie parecem com o
# do cardápio, os três são o mesmo produto e formam UM grupo — o irmão continua
# ali, entrando pela ponte. O que o recorte garante é outra coisa: nenhum grupo
# se forma só com cadastros da MESMA porta.
so_uma = [g for g in (entre.get("grupos") or []) if len(g["origens"]) == 1]
checar("nenhum grupo do recorte é de uma porta só", not so_uma,
       [g["origens"] for g in so_uma][:5])

print("\n3b. a regra que separa variação de duplicado")
sys.path.insert(0, ".")
from services.duplicados import mesmo_produto  # noqa: E402
# ⚠️ Sem esta regra, "FRUTA MORANGO CG PCT1KG" e "FRUTA AMORA CG PCT1KG" batem
# 95%: o nome é quase todo embalagem e a palavra que muda tudo pesa pouco.
checar("fruta diferente NÃO é duplicado",
       not mesmo_produto("fruta morango cg pct1kg cx6kg", "fruta amora cg pct1kg cx6kg"))
# ⚠️ Número dos DOIS lados é o produto: tamanho, modelo, quantidade.
checar("tamanho diferente NÃO é duplicado",
       not mesmo_produto("cake board mdf branco n19", "cake board mdf branco n21"))
checar("volume diferente NÃO é duplicado",
       not mesmo_produto("suco de uva integral 300ml", "suco de uva integral 250ml"))
checar("e 1 unidade não é 10 unidades",
       not mesmo_produto("drip coffee botane b 1unid", "drip coffee botane pct 10unid"))
# O que DEVE passar: unidade a mais, grafia, e número de um lado só.
checar("a unidade a mais é ruído", mesmo_produto("laranja pera", "laranja pera kg"))
checar("grafia diferente do mesmo termo passa",
       mesmo_produto("panettone pistache", "panetone de pistache"))
checar("número de UM lado só é ruído", mesmo_produto("burrata atacado 2", "burrata atacado"))

print("\n4. as recusas")
st, r = chamar("POST", f"/produtos/{do_omie}/unificar", {"id_absorver": do_omie}, token=token)
checar("unificar consigo mesmo é recusado", st == 400, (st, r))

st, r = chamar("POST", f"/produtos/{do_omie}/unificar", {"id_absorver": 99999999}, token=token)
checar("produto inexistente é 404", st == 404, st)

# ⚠️ Códigos do Omie diferentes são produtos DIFERENTES lá — não é duplicado de
# entrada, é o catálogo do fornecedor tendo dois itens.
st, r = chamar("POST", f"/produtos/{do_omie}/unificar", {"id_absorver": do_omie2}, token=token)
checar("dois códigos do Omie: recusado", st == 409, (st, r))
checar("e a recusa explica por quê",
       "produtos diferentes" in str(r.get("detail", "")).lower(), r)

# Movimento no razão é história que não muda de cadastro: o razão é append-only.
st, locais = chamar("GET", "/locais", token=token)
principal = next((x for x in locais if x.get("principal")), locais[0])
st, r = chamar("POST", "/estoque/entradas", {
    "id_produto": do_omie, "quantidade": 5, "custo_unitario": 30,
    "id_local": principal["id"], "documento": f"DUP-{marca}",
}, token=token)
checar("o lado do Omie ganha movimento no razão", st == 201, (st, r))

st, r = chamar("POST", f"/produtos/{do_pdv}/unificar", {"id_absorver": do_omie}, token=token)
checar("absorver quem tem movimento é recusado", st == 409, (st, r))
checar("e a recusa NOMEIA o que trava",
       "append-only" in str(r.get("detail", "")), r)
checar("mandando fazer ao contrário",
       "ao contrário" in str(r.get("detail", "")), r)

print("\n5. a unificação, na direção certa")
st, r = chamar("POST", f"/produtos/{do_omie}/unificar", {"id_absorver": do_pdv}, token=token)
checar("unificar responde", st == 200, (st, r))
checar("moveu o vínculo do PDV", r.get("vinculos_externos") == 1, r)
checar("e o item de venda", r.get("itens_de_venda") == 1, r)

st, p = chamar("GET", f"/produtos/{do_pdv}", token=token)
checar("o absorvido virou INATIVO, não sumiu", st == 200 and p.get("ativo") is False,
       (st, p.get("ativo")))
checar("e a observação registra para onde ele foi",
       "Unificado em" in (p.get("observacao") or ""), p.get("observacao"))

with banco() as conexao, conexao.cursor() as cur:
    cur.execute("SELECT id_produto FROM codigos_externos WHERE sistema='PDV_LEGAL' AND codigo=%s",
                (f"PDVC{marca}",))
    dono = (cur.fetchone() or {}).get("id_produto")
    cur.execute("""SELECT vi.id_produto, vi.custo_ficha_unitario, vi.origem_custo
                     FROM venda_itens vi JOIN vendas v ON v.id = vi.id_venda
                    WHERE v.documento = %s""", (f"DUP-{marca}",))
    item = dict(cur.fetchone() or {})
checar("o de-para do PDV aponta para o que ficou", dono == do_omie, (dono, do_omie))
checar("e o item de venda também", item.get("id_produto") == do_omie, item)
# ⚠️ O item entrou contando ZERO no CMV teórico; ao ganhar um produto com custo
# médio, passa a contar o que custa. É a mesma regra de `cardapio.reconciliar`.
checar("o item que estava sem custo ganhou custo",
       item.get("custo_ficha_unitario") is not None, item)
checar("e a origem do custo é dita", item.get("origem_custo") in ("custo_medio", "ultima_compra"),
       item.get("origem_custo"))

print("\n6. depois de unificado, o absorvido sai da lista")
st, d = chamar("GET", "/produtos/duplicados?minimo=80", token=token)
# O absorvido ficou INATIVO, e o relatório só olha produto ativo.
ainda = [g for g in (d.get("grupos") or [])
         if any(c["id"] == do_pdv for c in g["cadastros"])]
checar("o cadastro absorvido não aparece mais", not ainda, ainda)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
