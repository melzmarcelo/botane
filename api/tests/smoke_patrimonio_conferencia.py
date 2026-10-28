"""Teste de fumaça da CONFERÊNCIA do patrimônio (migração 140, etapa 3).

🔑 Pedido do dono (28/10/2026): *"pode seguir com a etapa 3 do patrimônio"* — abrir a
conferência por setor, ler as plaquetas e fechar com transferência ou baixa. Confere:

    1. Abrir fotografa os bens do setor (o baixado não entra); uma segunda aberta no mesmo
       setor é 409, e a da loja inteira também (sobreposição).
    2. Ler: pelo LINK do QR, pelo código e pelo apelido; a segunda leitura diz "já lido";
       o bem de outro setor entra como "de fora"; código que não existe é 404; o baixado
       é 409. A leitura conta (lidos / faltam).
    3. Desfazer a leitura volta a "falta ler"; o de fora sai da lista.
    4. Fechar: o lido fica com `conferido_em` e "A confirmar" vira "Em uso"; o de fora é
       TRANSFERIDO para o setor (e perde o local de outro setor); o não lido escolhido é
       BAIXADO com o motivo; o resto é mantido. Fechada, não lê mais (409).
    5. Bem que passou por conferência fechada não se apaga (409).
    6. A plaqueta lida pela câmera acha a conferência aberta (`conferencia_aberta`).
    7. Cancelar não muda bem nenhum. A folha da conferência sai em PDF e CSV.
    8. Cozinha vê, mas não abre conferência (403).

    python tests/smoke_patrimonio_conferencia.py      (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
ok = 0
falhas: list[str] = []
marca = str(int(time.time()))[-6:]
hoje = date.today()


def chamar(metodo, caminho, corpo=None, token=None):
    caminho = urllib.parse.quote(caminho, safe="/?=&.,")
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo, default=str).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def baixar(caminho, token):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&.,"))
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def checar(nome, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
init_pool()
setores: list[int] = []
locais: list[int] = []


def bem(**campos) -> dict:
    st, b = chamar("POST", "/patrimonio", {"descricao": f"Bem conf {marca}", **campos}, token=token)
    assert st == 201, (st, b)
    return b


def item(c: dict, id_bem: int) -> dict:
    return next((i for i in c["itens"] if i["id_bem"] == id_bem), {})


try:
    print("1. abrir")
    for nome in ("BAR", "COZINHA"):
        st, s = chamar("POST", "/setores", {"nome": f"{nome} CONF {marca}"}, token=token)
        setores.append(s["id"])
    bar, cozinha = setores
    st, l = chamar("POST", "/locais", {"nome": f"PRATELEIRA COZ CONF {marca}", "tipo": "SECO",
                                       "id_setor": cozinha}, token=token)
    locais.append(l["id"])
    local_cozinha = l["id"]

    b1 = bem(descricao=f"Cafeteira conf {marca}", id_setor=bar, apelido=f"CB{marca}")
    b2 = bem(descricao=f"Moedor conf {marca}", id_setor=bar, situacao="A_CONFIRMAR")
    b3 = bem(descricao=f"Liquidificador conf {marca}", id_setor=bar)
    b4 = bem(descricao=f"Geladeira conf {marca}", id_setor=bar)
    baixado = bem(descricao=f"Velho conf {marca}", id_setor=bar, situacao="BAIXADO",
                  motivo_baixa="quebrou")
    de_fora = bem(descricao=f"Batedeira conf {marca}", id_setor=cozinha, id_local=local_cozinha)

    st, c = chamar("POST", "/patrimonio/conferencias", {"id_setor": bar}, token=token)
    checar("abre a conferência do bar", st == 201, (st, c))
    id_c = c["id"]
    checar("com os 4 bens do bar esperados (o baixado não entra)",
           c["esperados"] == 4 and not item(c, baixado["id"]), (c["esperados"], c["itens"]))
    st, r = chamar("POST", "/patrimonio/conferencias", {"id_setor": bar}, token=token)
    checar("outra no mesmo setor é 409", st == 409, (st, r))
    st, r = chamar("POST", "/patrimonio/conferencias", {}, token=token)
    checar("e a da loja inteira também (sobreporia)", st == 409, (st, r))

    print("2. ler")
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": f"https://sistema.exemplo/patrimonio/b/{b1['codigo']}"}, token=token)
    checar("o LINK do QR é lido", st == 201 and not r["ja_lido"] and not r["de_fora"], (st, r))
    checar("e a contagem anda", r["contagem"]["lidos"] == 1 and r["contagem"]["faltam"] == 3,
           r.get("contagem"))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": b1["codigo"].lower()}, token=token)
    checar("ler de novo (código em minúscula) diz já lido", st == 201 and r["ja_lido"], (st, r))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": b2["codigo"]}, token=token)
    checar("o código digitado é lido", st == 201 and r["contagem"]["lidos"] == 2, (st, r))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": b3["codigo"]}, token=token)
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": de_fora["codigo"]}, token=token)
    checar("o bem de outro setor entra como de fora", st == 201 and r["de_fora"] and r["novo"],
           (st, r))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": "PAT-99999999"}, token=token)
    checar("código que não existe é 404", st == 404, (st, r))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": baixado["codigo"]}, token=token)
    checar("bem baixado é 409, dizendo que está baixado",
           st == 409 and "BAIXADO" in r.get("detail", ""), (st, r))

    print("3. desfazer")
    st, c = chamar("GET", f"/patrimonio/conferencias/{id_c}", token=token)
    st, c = chamar("DELETE", f"/patrimonio/conferencias/{id_c}/leituras/{item(c, b3['id'])['id']}",
                   token=token)
    checar("desfazer volta o bem a falta ler", st == 200 and not item(c, b3["id"])["lido_em"],
           (st, item(c, b3["id"])))
    # Lê pelo APELIDO da casa — o que está escrito no equipamento antigo.
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": f"cb{marca}"}, token=token)
    checar("o apelido da casa também acha o bem (já lido)", st == 201 and r["ja_lido"], (st, r))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": b3["codigo"]}, token=token)

    print("6. a câmera do celular acha a conferência")
    st, r = chamar("GET", f"/patrimonio/codigo/{b4['codigo']}", token=token)
    checar("a plaqueta do bar diz qual conferência está aberta",
           st == 200 and r.get("conferencia_aberta") == id_c, (st, r))

    print("4. fechar")
    st, c = chamar("GET", f"/patrimonio/conferencias/{id_c}", token=token)
    checar("antes de fechar: 3 lidos, 1 falta, 1 de fora",
           (c["lidos"], c["faltam"], c["de_fora"]) == (3, 1, 1), (c["lidos"], c["faltam"], c["de_fora"]))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/fechar",
                   {"baixar": [item(c, b1["id"])["id"]]}, token=token)
    checar("baixar o que FOI lido é recusado", st == 400, (st, r))
    st, c = chamar("POST", f"/patrimonio/conferencias/{id_c}/fechar",
                   {"baixar": [item(c, b4["id"])["id"]], "motivo_baixa": "sumiu"}, token=token)
    checar("fecha", st == 200 and c["status"] == "FECHADA", (st, c))
    checar("e diz o que fez", c.get("resultado") == {"CONFERIDO": 3, "TRANSFERIDO": 1,
                                                       "NAO_ENCONTRADO": 0, "BAIXADO": 1},
           c.get("resultado"))
    _, x1 = chamar("GET", f"/patrimonio/{b1['id']}", token=token)
    _, x2 = chamar("GET", f"/patrimonio/{b2['id']}", token=token)
    _, x4 = chamar("GET", f"/patrimonio/{b4['id']}", token=token)
    _, xf = chamar("GET", f"/patrimonio/{de_fora['id']}", token=token)
    checar("o lido fica com a data da conferência", x1["conferido_em"] == hoje.isoformat(),
           x1["conferido_em"])
    checar("o A confirmar visto vira Em uso", x2["situacao"] == "EM_USO", x2["situacao"])
    checar("o escolhido é baixado com o motivo",
           x4["situacao"] == "BAIXADO" and x4["motivo_baixa"] == "sumiu", (x4["situacao"], x4["motivo_baixa"]))
    checar("o de fora vem para o bar e perde a prateleira da cozinha",
           xf["id_setor"] == bar and xf["id_local"] is None and xf["conferido_em"],
           (xf["id_setor"], xf["id_local"]))
    st, r = chamar("POST", f"/patrimonio/conferencias/{id_c}/leituras",
                   {"texto": b3["codigo"]}, token=token)
    checar("fechada não lê mais (409)", st == 409, (st, r))

    print("5. a conferência é história do bem")
    st, r = chamar("DELETE", f"/patrimonio/{b3['id']}", token=token)
    checar("bem conferido não se apaga (409)", st == 409, (st, r))

    print("7. cancelar e a folha")
    st, c2 = chamar("POST", "/patrimonio/conferencias",
                    {"id_setor": bar, "observacao": "segunda volta"}, token=token)
    chamar("POST", f"/patrimonio/conferencias/{c2['id']}/leituras", {"texto": b2["codigo"]},
           token=token)
    st, r = chamar("POST", f"/patrimonio/conferencias/{c2['id']}/cancelar", token=token)
    _, x3 = chamar("GET", f"/patrimonio/{b3['id']}", token=token)
    checar("cancelar fecha sem mexer em bem nenhum",
           st == 200 and r["status"] == "CANCELADA" and x3["situacao"] == "EM_USO", (st, r.get("status")))
    st, tipo, pdf = baixar(f"/exportar/conferencia-patrimonio/{id_c}.pdf", token)
    checar("a folha da conferência sai em PDF", st == 200 and pdf[:4] == b"%PDF", (st, tipo))
    st, tipo, csv = baixar(f"/exportar/conferencia-patrimonio/{id_c}.csv", token)
    texto = csv.decode("utf-8-sig")
    checar("e em planilha, com o resultado de cada bem",
           "Transferido para cá" in texto and "Baixado" in texto and b1["codigo"] in texto,
           texto[:400])
    st, lista = chamar("GET", "/patrimonio/conferencias", token=token)
    checar("a lista traz as duas", {id_c, c2["id"]} <= {x["id"] for x in lista}, lista[:3])
    st, tipo, rel = baixar("/exportar/patrimonio.csv?busca_bem=" + urllib.parse.quote(f"conf {marca}"), token)
    checar("o relatório de bens traz o Conferido em",
           "Conferido em" in rel.decode("utf-8-sig"), rel[:300])

    print("8. permissões")
    tk = garantir_cozinha(chamar, token)
    st, _ = chamar("GET", "/patrimonio/conferencias", token=tk)
    checar("cozinha vê as conferências", st == 200, st)
    st, _ = chamar("POST", "/patrimonio/conferencias", {"id_setor": cozinha}, token=tk)
    checar("mas não abre (403)", st == 403, st)
finally:
    with get_cursor() as cur:
        cur.execute("DELETE FROM bem_conferencias WHERE id_setor = ANY(%s)", (setores,))
        cur.execute("DELETE FROM bens WHERE descricao LIKE %s", (f"%conf {marca}",))
    for i in locais:
        chamar("DELETE", f"/locais/{i}", token=token)
    for i in setores:
        chamar("DELETE", f"/setores/{i}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
