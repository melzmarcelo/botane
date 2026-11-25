"""Recebimento de notas (migração 162): registrar que a nota chegou, com foto opcional.

O que este arquivo cobra:

1. registrar com fornecedor do cadastro e fora dele, com e sem foto
2. a validação: sem número, sem fornecedor, data no futuro, foto que não é imagem
3. a mesma nota duas vezes avisa (409) e passa com "mesmo assim"
4. a situação é CONTA: sem nota no sistema = FALTA; nota conciliada = NO_SISTEMA; lançada =
   LANCADA — casando o número sem zeros à esquerda e pelo fornecedor
5. a foto só sai pela rota autenticada, e só para quem vê os recebimentos
6. permissões: a cozinha registra e apaga o próprio; não apaga o dos outros
7. o relatório responde

    python tests/smoke_recebimentos.py      (API de pé na 9200)
"""

import atexit
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
# Um PNG de 1×1 de verdade (o servidor confere que é imagem).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def chamar(metodo, caminho, corpo=None, token=None, bruto=False):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("X-Unidade", "1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = None
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
        dados = json.dumps(corpo, default=str).encode()
    try:
        with urllib.request.urlopen(req, dados, timeout=60) as r:
            conteudo = r.read()
            return r.status, (conteudo if bruto else json.loads(conteudo or b"null"))
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def enviar(campos: dict, token, foto: tuple[str, bytes, str] | None = None):
    """POST multipart à mão (urllib não tem)."""
    fronteira = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        if v is None:
            continue
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    if foto:
        nome, conteudo, tipo = foto
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="foto"; filename="{nome}"\r\n'
                      f"Content-Type: {tipo}\r\n\r\n".encode() + conteudo + b"\r\n")
    corpo = b"".join(partes) + f"--{fronteira}--\r\n".encode()
    req = urllib.request.Request(BASE + "/recebimentos", data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={fronteira}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Unidade", "1")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": b.decode(errors="replace")}


def checar(nome, condicao, extra=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {extra}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
if st != 200:
    print("API não respondeu ao login:", st, r)
    sys.exit(1)
token = r["access_token"]
marca = str(time.time_ns() // 1000)[-7:]
hoje = date.today().isoformat()
criados: list[int] = []
notas_criadas: list[int] = []


def _limpar():
    from database import get_cursor
    try:
        for i in criados:
            chamar("DELETE", f"/recebimentos/{i}", token=token)
        with get_cursor() as cur:
            for n in notas_criadas:
                cur.execute("DELETE FROM notas_entrada WHERE id = %s", (n,))
    except Exception:
        pass


atexit.register(_limpar)


def registro(i):
    _s, l = chamar("GET", f"/recebimentos?busca={marca}&limite=50", token=token)
    return next((x for x in (l or []) if x["id"] == i), None)


print("0. preparo: um fornecedor de teste")
s, forn = chamar("POST", "/fornecedores", {"nome": f"Fornecedor recebimento {marca}", "tipo": "J"},
                 token=token)
if s not in (200, 201):
    _s, lst = chamar("GET", "/fornecedores?limite=1", token=token)
    forn = (lst or [{}])[0]
id_forn = forn.get("id")
checar("há um fornecedor para o teste", bool(id_forn), (s, forn))

print("1. registrar")
s, a = enviar({"numero_nota": f"00{marca}1", "data_nota": hoje, "id_fornecedor": id_forn,
               "observacao": "veio faltando uma caixa"}, token, ("nota.png", PNG, "image/png"))
checar("com fornecedor do cadastro e foto", s == 201 and a.get("id"), (s, a))
criados.append(a.get("id"))
r1 = registro(a["id"])
checar("aparece com a foto e quem recebeu", r1 and r1["tem_foto"] and r1["recebido_por_nome"], r1)
checar("sem a nota no sistema, a situação é FALTA", r1 and r1["situacao"] == "FALTA", r1)
s, b = enviar({"numero_nota": f"{marca}2", "data_nota": hoje,
               "fornecedor_texto": f"Feira do Zé {marca}"}, token)
checar("fora do cadastro e sem foto", s == 201, (s, b))
criados.append(b.get("id"))
checar("sem foto, tem_foto falso", registro(b["id"])["tem_foto"] is False)

print("2. validação")
s, _ = enviar({"numero_nota": "", "data_nota": hoje, "id_fornecedor": id_forn}, token)
checar("sem número: 422", s == 422, s)
s, _ = enviar({"numero_nota": f"{marca}3", "data_nota": hoje}, token)
checar("sem fornecedor: 422", s == 422, s)
amanha = (date.today() + timedelta(days=1)).isoformat()
s, _ = enviar({"numero_nota": f"{marca}3", "data_nota": amanha, "id_fornecedor": id_forn}, token)
checar("data no futuro: 422", s == 422, s)
s, _ = enviar({"numero_nota": f"{marca}3", "data_nota": hoje, "id_fornecedor": id_forn}, token,
              ("nota.png", b"isto nao e imagem", "image/png"))
checar("foto que não é imagem: 400", s == 400, s)

print("3. a mesma nota duas vezes")
s, r = enviar({"numero_nota": f"{marca}1", "data_nota": hoje, "id_fornecedor": id_forn}, token)
checar("avisa que já foi registrada (zeros à esquerda não enganam): 409",
       s == 409 and "já foi registrada" in r["detail"], (s, r))
s, r = enviar({"numero_nota": f"{marca}1", "data_nota": hoje, "id_fornecedor": id_forn,
               "mesmo_assim": "true"}, token)
checar("e passa com mesmo assim", s == 201, (s, r))
criados.append(r.get("id"))

print("4. a situação é conta")
from database import get_cursor  # noqa: E402

with get_cursor() as cur:
    cur.execute("""INSERT INTO notas_entrada (id_unidade, numero, id_fornecedor, nome_emitente,
                                              data_emissao, status, origem)
                   VALUES (1, %s, %s, %s, %s, 'CONCILIADA', 'MANUAL') RETURNING id""",
                (f"{marca}1", id_forn, f"Fornecedor recebimento {marca}", hoje))
    id_nota = cur.fetchone()["id"]
notas_criadas.append(id_nota)
r1 = registro(a["id"])
checar("a nota apareceu conciliada: NO_SISTEMA, ligada a ela",
       r1["situacao"] == "NO_SISTEMA" and r1["id_nota"] == id_nota, r1)
with get_cursor() as cur:
    cur.execute("UPDATE notas_entrada SET status = 'LANCADA' WHERE id = %s", (id_nota,))
checar("lançada: LANCADA", registro(a["id"])["situacao"] == "LANCADA")
checar("a outra, de outro fornecedor, continua FALTA", registro(b["id"])["situacao"] == "FALTA")
_s, l = chamar("GET", f"/recebimentos?situacao=FALTA&busca={marca}&limite=50", token=token)
checar("o filtro de situação funciona", all(x["situacao"] == "FALTA" for x in l) and
       any(x["id"] == b["id"] for x in l), l)
_s, res = chamar("GET", "/recebimentos/resumo", token=token)
checar("o resumo conta as que faltam", isinstance(res.get("faltam"), int) and res["faltam"] >= 1, res)

print("5. a foto")
s, img = chamar("GET", f"/recebimentos/{a['id']}/foto", token=token, bruto=True)
checar("sai pela rota autenticada, e é a imagem", s == 200 and img[:4] == PNG[:4], (s, img[:10]))
s, _ = chamar("GET", f"/recebimentos/{a['id']}/foto", bruto=True)
checar("sem login: 401", s == 401, s)
s, _ = chamar("GET", f"/recebimentos/{b['id']}/foto", token=token, bruto=True)
checar("registro sem foto: 404", s == 404, s)

print("6. permissões")
_s, papeis = chamar("GET", "/papeis", token=token)
cozinha = next(p for p in papeis if p["nome"] == "Cozinha")
_s, unidades = chamar("GET", "/unidades", token=token)
matriz = next(u["id"] for u in unidades if u.get("matriz"))
email = f"receb{marca}@teste.botane"
chamar("POST", "/usuarios", {"nome": f"Recebe {marca}", "email": email, "senha": "Teste#12345",
                             "papeis": [{"id_papel": cozinha["id"], "id_unidade": matriz}]}, token=token)
_s, lg = chamar("POST", "/auth/login", {"email": email, "senha": "Teste#12345"})
tk = (lg or {}).get("access_token")
s, c = enviar({"numero_nota": f"{marca}9", "data_nota": hoje, "id_fornecedor": id_forn}, tk)
checar("a cozinha registra", s == 201, (s, c))
s, _ = chamar("DELETE", f"/recebimentos/{a['id']}", token=tk)
checar("não apaga o registro dos outros: 403", s == 403, s)
s, _ = chamar("DELETE", f"/recebimentos/{c['id']}", token=tk)
checar("apaga o próprio", s == 200, s)

print("7. relatório")
s, rel = chamar("GET", f"/exportar/recebimentos/dados?inicio={hoje}&fim={hoje}", token=token)
texto = json.dumps(rel, ensure_ascii=False, default=str)
checar("o relatório responde, com a situação", s == 200 and "Situação" in texto and marca in texto,
       texto[:300])

print(f"\n{ok} passaram, {len(falhas)} falharam")
if falhas:
    for x in falhas:
        print("  -", x)
    sys.exit(1)
