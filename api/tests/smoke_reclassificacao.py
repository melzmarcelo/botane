"""A reestruturação de tipos (131) e a reclassificação de produtos por planilha.

🔑 Pedido do dono (23/10/2026), pelo documento "Tabelas tipo, categoria, setor" da casa.

O que esta suíte afirma:
1. os tipos: MATERIAL_OPERACIONAL no lugar de MATERIAL_LIMPEZA (que passa a ser
   recusado), PATRIMONIO e SERVICO novos; serviço nunca controla estoque; os dois novos
   ficam num grupo FORA do CMV; categoria pode nascer sem tipo
2. a planilha: a exportada do cadastro volta sem mudar nada; corrigida, a prévia diz o
   que muda (pelo nome, sem acento, tipo pelo rótulo) e NÃO grava; linha com nome que
   não existe, código desconhecido, produto repetido e produção própria virando insumo
   são recusadas nomeadas, e as outras seguem; aplicar grava e audita; reaplicar não
   muda nada; vírgula também serve; planilha sem a coluna Código é 400; a cozinha, 403

    python tests/smoke_reclassificacao.py      (API de pé; BOTANE_API muda a porta)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from database import get_cursor, init_pool  # noqa: E402
from comum import garantir_cozinha  # noqa: E402

BASE = os.environ.get("BOTANE_API", "http://127.0.0.1:9200")
ok = 0
falhas: list[str] = []
marca = uuid.uuid4().hex[:6].upper()
produtos: list[int] = []
categorias: list[int] = []
setores: list[int] = []


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&[]"),
                                 method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=120) as r:
            corpo_r = r.read()
            return r.status, (corpo_r if bruto else json.loads(corpo_r or b"null"))
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def enviar(texto: str, simular: bool, token, separador_ok=True):
    """POST multipart da planilha (CSV)."""
    fronteira = "----botane" + uuid.uuid4().hex
    corpo = (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
             f"filename=\"produtos.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode()
    corpo += texto.encode("utf-8-sig") + f"\r\n--{fronteira}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/produtos/reclassificar?simular={'true' if simular else 'false'}",
        data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={fronteira}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def produto(nome, **extra):
    st, r = chamar("POST", "/produtos", {"nome": f"{nome} {marca}", "um_estoque": "UN",
                                         "status": "ATIVO", **extra}, token)
    if (r or {}).get("id"):
        produtos.append(r["id"])
    return st, (r or {}).get("id")


def detalhe(id_produto):
    return chamar("GET", f"/produtos/{id_produto}", token=token)[1]


_st, r = chamar("POST", "/auth/login", {"email": "admin@botane.com.br", "senha": "botane123"})
token = (r or {}).get("access_token")
checar("o administrador entra", bool(token))
init_pool()

print("\n1. os tipos reestruturados")
st, op = produto("Copo descartavel", tipo="MATERIAL_OPERACIONAL")
checar("MATERIAL_OPERACIONAL é aceito", st == 201 and bool(op), st)
st, r = chamar("POST", "/produtos", {"nome": f"Detergente {marca}", "tipo": "MATERIAL_LIMPEZA",
                                     "um_estoque": "UN", "status": "ATIVO"}, token)
checar("MATERIAL_LIMPEZA não existe mais (400, com a lista certa)",
       st == 400 and "MATERIAL_OPERACIONAL" in (r or {}).get("detail", ""), (st, r))
st, pat = produto("Batedeira planetaria", tipo="PATRIMONIO")
checar("PATRIMONIO é aceito", st == 201 and bool(pat), st)
st, srv = produto("Taxa de entrega", tipo="SERVICO", controla_estoque=True)
checar("SERVICO é aceito", st == 201 and bool(srv), st)
checar("e serviço nunca controla estoque, mesmo pedido", detalhe(srv).get("controla_estoque")
       is False, detalhe(srv).get("controla_estoque"))
chamar("PUT", f"/produtos/{op}", {"tipo": "SERVICO"}, token)
checar("virar serviço pela edição também desliga o estoque",
       detalhe(op).get("controla_estoque") is False, detalhe(op).get("controla_estoque"))
chamar("PUT", f"/produtos/{op}", {"tipo": "MATERIAL_OPERACIONAL", "controla_estoque": True},
       token)
with get_cursor() as cur:
    cur.execute("""SELECT t.tipo, g.considerar_no_cmv FROM cmv_grupo_tipos t
                     JOIN cmv_grupos g ON g.id = t.id_grupo
                    WHERE t.tipo IN ('PATRIMONIO', 'SERVICO', 'MATERIAL_OPERACIONAL')""")
    grupos = {r["tipo"]: r["considerar_no_cmv"] for r in cur.fetchall()}
    cur.execute("SELECT count(*) AS n FROM produtos WHERE tipo = 'MATERIAL_LIMPEZA'")
    restos = cur.fetchone()["n"]
checar("patrimônio e serviço estão num grupo FORA do CMV real",
       grupos.get("PATRIMONIO") is False and grupos.get("SERVICO") is False, grupos)
with get_cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM cmv_grupo_tipos WHERE tipo = 'MATERIAL_LIMPEZA'")
    checar("nenhum grupo do CMV ficou com o tipo antigo (o de limpeza virou o operacional)",
           cur.fetchone()["n"] == 0)
checar("nenhum produto ficou com o tipo antigo", restos == 0, restos)
st, r = chamar("POST", "/categorias", {"nome": f"OUTROS {marca}"}, token)
checar("categoria nasce SEM tipo (é independente do tipo)", st == 201, (st, r))
if (r or {}).get("id"):
    categorias.append(r["id"])
    _st, lista = chamar("GET", "/categorias", token=token)
    linha = next((c for c in lista or [] if c["id"] == r["id"]), {})
    checar("e a lista a devolve com tipo vazio", linha.get("tipo") is None, linha)

print("\n2. a planilha")
_st, velha = chamar("POST", "/categorias", {"nome": f"Velha {marca}", "tipo": "PRODUZIDO"},
                    token)
_st, nova = chamar("POST", "/categorias", {"nome": f"Hortifrúti {marca}"}, token)
_st, setor = chamar("POST", "/setores", {"nome": f"Almoxarifado {marca}"}, token)
categorias += [velha["id"], nova["id"]]
setores.append(setor["id"])
_st, a = produto("Abacate", tipo="PRODUZIDO", id_categoria=velha["id"])
_st, b = produto("Brownie", tipo="PRODUZIDO", id_categoria=velha["id"])
_st, c = produto("Croissant", tipo="PRODUZIDO", id_categoria=velha["id"],
                 producao_propria=True)

# A ida e a volta de verdade: a planilha que o sistema exporta.
st, csv_bytes = chamar("GET", f"/exportar/produtos.csv?categorias={velha['id']}",
                       token=token, bruto=True)
exportada = csv_bytes.decode("utf-8-sig") if st == 200 else ""
checar("a planilha do cadastro sai (com Código, Tipo, Categoria, Setor, Local padrão)",
       st == 200 and all(c in exportada for c in ("Código", "Tipo", "Categoria", "Setor",
                                                   "Local padrão")), st)
st, r = enviar(exportada, True, token)
checar("mandada de volta sem mexer, nada muda", st == 200 and not r["mudam"]
       and r["iguais"] == 3 and not r["recusados"], (st, r))

linhas_csv = exportada.splitlines()
i_cab = next(i for i, l in enumerate(linhas_csv) if l.startswith("Código"))
cab = linhas_csv[i_cab].split(";")
col = {n: cab.index(n) for n in ("Código", "Tipo", "Categoria", "Setor")}


def trocar(linha: str, **novos) -> str:
    partes = linha.split(";")
    for nome, valor in novos.items():
        partes[col[nome]] = valor
    return ";".join(partes)


corpo = []
for l in linhas_csv[i_cab + 1:]:
    if f"Abacate {marca}".upper() in l.upper():
        # Rótulo do tipo, nome sem acento e em minúsculas: como a pessoa digita.
        l = trocar(l, Tipo="Insumo", Categoria=f"hortifruti {marca.lower()}",
                   Setor=f"ALMOXARIFADO {marca}")
    elif f"Croissant {marca}".upper() in l.upper():
        l = trocar(l, Tipo="INSUMO")
    elif f"Brownie {marca}".upper() in l.upper():
        l = trocar(l, Categoria=f"Inexistente {marca}")
    corpo.append(l)
corpo.append(f"NAOEXISTE{marca};x;INSUMO;;;")
corpo.append(next(l for l in corpo if f"Abacate {marca}".upper() in l.upper()))
planilha = "\n".join(linhas_csv[:i_cab + 1] + corpo)

st, r = enviar(planilha, True, token)
mudam = {m["id"]: m for m in (r or {}).get("mudam", [])}
recusas = {x["codigo"]: x["motivo"] for x in (r or {}).get("recusados", [])}
checar("a prévia diz o que muda, pelo nome", st == 200 and a in mudam
       # ⚠️ Comparado sem caixa: o cadastro grava os nomes em maiúsculas.
       and (mudam[a]["para"].get("categoria") or "").upper() == f"HORTIFRÚTI {marca}"
       and (mudam[a]["para"].get("setor") or "").upper() == f"ALMOXARIFADO {marca}"
       and mudam[a]["para"].get("tipo") == "INSUMO", (st, r))
checar("e mostra o de-para (de PRODUZIDO, da Velha)",
       mudam.get(a, {}).get("de", {}).get("tipo") == "PRODUZIDO"
       and (mudam.get(a, {}).get("de", {}).get("categoria") or "").upper() == f"VELHA {marca}",
       mudam.get(a))
checar("a prévia NÃO grava", detalhe(a).get("tipo") == "PRODUZIDO")
checar("categoria que não existe recusa a linha, dizendo qual",
       any("Inexistente" in m for m in recusas.values()), recusas)
checar("produção própria virando insumo é recusada",
       any("produção própria" in m for m in recusas.values()), recusas)
checar("código desconhecido é recusado", f"NAOEXISTE{marca}" in recusas, recusas)
checar("o produto repetido na planilha é apontado",
       any("de novo" in m for m in recusas.values()), recusas)
checar("e só o Abacate muda", list(mudam) == [a], list(mudam))

st, r = enviar(planilha, False, token)
d = detalhe(a)
checar("aplicar grava tipo, categoria e setor",
       st == 200 and r.get("aplicado") and d.get("tipo") == "INSUMO"
       and d.get("id_categoria") == nova["id"] and d.get("id_setor") == setor["id"], (st, d))
checar("e os recusados ficam como estavam",
       detalhe(c).get("tipo") == "PRODUZIDO" and detalhe(b).get("id_categoria") == velha["id"])
with get_cursor() as cur:
    cur.execute("""SELECT antes, depois FROM auditoria WHERE entidade = 'produto'
                    AND id_entidade::text = %s AND acao = 'reclassificar'""", (str(a),))
    aud = cur.fetchone()
checar("um registro de auditoria por produto, com o antes",
       aud is not None and (aud["antes"] or {}).get("tipo") == "PRODUZIDO", aud)
st, r = enviar(planilha, True, token)
checar("reaplicada, a mesma planilha não muda mais nada", st == 200 and not r["mudam"], r)

# Desativada a categoria velha, a linha NÃO mexida de quem está nela não é recusada.
chamar("PUT", f"/categorias/{velha['id']}", {"ativo": False}, token)
_st, de_novo = chamar("GET", f"/exportar/produtos.csv?categorias={velha['id']}",
                      token=token, bruto=True)
st, r = enviar(de_novo.decode("utf-8-sig"), True, token)
checar("linha não mexida em categoria desativada não é recusada",
       st == 200 and r["iguais"] == 2 and not r["recusados"], r)
# Mas PEDIR a categoria desativada é recusado: a planilha velha manda o Abacate de volta.
st, r = enviar(exportada, True, token)
checar("pedir uma categoria desativada é recusado, dizendo que está inativa",
       any("inativ" in x["motivo"] for x in r["recusados"]), r)

virgula = (f"Codigo,Tipo,Categoria\r\n{d['codigo']},Revenda,\r\n")
st, r = enviar(virgula, True, token)
checar("planilha com vírgula, sem acento no cabeçalho, também serve",
       st == 200 and [m["id"] for m in r["mudam"]] == [a], (st, r))
st, r = enviar("Nome;Tipo\r\nqualquer;INSUMO\r\n", True, token)
checar("sem a coluna Código é 400, dizendo por quê",
       st == 400 and "Código" in (r or {}).get("detail", ""), (st, r))
cozinha = garantir_cozinha(chamar, token)
st, _r = enviar(planilha, True, cozinha)
checar("a cozinha não reclassifica (403)", st == 403, st)

print("\n3. limpeza")
for pid in produtos:
    chamar("DELETE", f"/produtos/{pid}", token=token)
with get_cursor() as cur:
    cur.execute("UPDATE produtos SET id_categoria = NULL, id_setor = NULL WHERE id = ANY(%s)",
                (produtos,))
for cid in categorias:
    chamar("DELETE", f"/categorias/{cid}", token=token)
for sid in setores:
    chamar("DELETE", f"/setores/{sid}", token=token)

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
raise SystemExit(1 if falhas else 0)
