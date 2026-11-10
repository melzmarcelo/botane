"""Teste de fumaça da entrega 2 da ficha do bem (migração 157).

🔑 Decisões do dono (10/11/2026): responsável em texto livre; garantia em meses + tipo com a
data calculada da compra (editável); fotos e documentos no banco; checklist da preventiva;
situação no Omie dos custos (só leitura, na hora). Confere:

    1. Responsável e garantia: os meses calculam a data final pela compra (31/01 + 1 mês =
       fim de fevereiro); a data digitada vale; mudar a compra sem a data refaz; a busca acha
       pelo responsável.
    2. Checklist: o plano limpa vazio e repetido; a preventiva grava o que foi marcado, como
       foto ("2 de 3 itens"), e o plano mudar depois não mexe na visita antiga.
    3. Anexos: foto e PDF entram, o arquivo é servido, formato errado é 400, o que não é
       imagem é 400; apagar o anexo apaga o arquivo; apagar o bem leva os anexos.
    4. Situação no Omie (modo simulado, fixture): compra paga, manutenção com parcela
       atrasada, título cancelado, fornecedor sem código e nota que não existe.
    5. Relatórios: bens trazem responsável, garantia e checklist; a planilha volta pela
       importação sem mudar nada; manutenções trazem NF e checklist.
    6. Cozinha (manutenção) anexa, mas não edita o bem.

    python tests/smoke_patrimonio_ficha2.py      (API de pé na 9200)
"""

import io
import os
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from comum import garantir_cozinha  # noqa: E402
from database import get_cursor, init_pool  # noqa: E402

BASE = os.environ.get("API_URL", "http://127.0.0.1:9200")
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


def bruto(caminho, token=None):
    req = urllib.request.Request(BASE + urllib.parse.quote(caminho, safe="/?=&.,"))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", e.read()


def enviar(caminho, nome, conteudo, tipo, token):
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
             f"filename=\"{nome}\"\r\nContent-Type: {tipo}\r\n\r\n").encode() \
        + conteudo + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(BASE + caminho, data=corpo, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
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


def png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (40, 120, 60)).save(b, "PNG")
    return b.getvalue()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def login(email, senha):
    st, r = chamar("POST", "/auth/login", {"email": email, "senha": senha})
    return r["access_token"]


def main():
    init_pool()
    token = login(*ADMIN)
    st, r = chamar("POST", "/patrimonio", {
        "descricao": f"Forno teste ficha2 {marca}", "data_compra": "2026-01-31",
        "valor_compra": 15000, "garantia_meses": 1, "garantia_tipo": "FABRICA",
        "responsavel": f"Chef Ana {marca}", "fornecedor": f"FORN FICHA2 {marca}",
        "nota_fiscal": "771", "preventiva_meses": 6,
        "preventiva_checklist": ["Limpar condensador", " limpar  condensador ", "", "Trocar filtro",
                                 "Conferir borracha"]}, token=token)
    checar("o bem nasce com responsável, garantia em meses e tipo", st == 201, (st, r))
    id_bem = r["id"]

    print("\n1. responsável e garantia")
    checar("31/01 + 1 mês = fim de fevereiro (a soma de meses do banco)",
           r["garantia_ate"] == "2026-02-28" and r["garantia_tipo_txt"] == "Fábrica", r)
    checar("o checklist limpa vazio e repetido (sem diferença de maiúscula)",
           r["preventiva_checklist"] == ["Limpar condensador", "Trocar filtro",
                                         "Conferir borracha"], r["preventiva_checklist"])
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"garantia_meses": 24}, token=token)
    checar("mudar os meses sem a data refaz a data (24 meses)", r.get("garantia_ate") == "2028-01-31", r)
    st, r = chamar("PUT", f"/patrimonio/{id_bem}",
                   {"garantia_meses": 24, "garantia_ate": "2028-06-30"}, token=token)
    checar("vindo a data digitada, vale a digitada", r.get("garantia_ate") == "2028-06-30", r)
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"data_compra": "2026-03-10"}, token=token)
    checar("mudar a compra sem a data refaz pela compra nova",
           r.get("garantia_ate") == "2028-03-10", r)
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"garantia_tipo": "QUALQUER"}, token=token)
    checar("tipo de garantia fora da lista é 422", st == 422, (st, r))
    st, lst = chamar("GET", f"/patrimonio?busca=Chef Ana {marca}", token=token)
    checar("a busca acha pelo responsável", [b["id"] for b in lst] == [id_bem], lst)

    print("\n2. checklist da preventiva")
    st, r = chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "PREVENTIVA", "data": str(hoje - timedelta(days=2)), "custo": 350,
        "executado_por": f"FORN FICHA2 {marca}", "nota_fiscal": "772",
        "checklist": [{"item": "Limpar condensador", "feito": True},
                      {"item": "Trocar filtro", "feito": True},
                      {"item": "Conferir borracha", "feito": False}]}, token=token)
    checar("a preventiva grava o checklist marcado e a NF", st == 201, (st, r))
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"preventiva_checklist": ["Só um item"]},
                   token=token)
    st, d = chamar("GET", f"/patrimonio/{id_bem}", token=token)
    m = d["manutencoes"][0]
    checar("o detalhe diz \"2 de 3 itens\" e guarda a nota",
           m["checklist_txt"] == "2 de 3 itens" and m["nota_fiscal"] == "772", m)
    checar("mudar o plano depois não mexe na visita antiga (é uma foto)",
           len(m["checklist"]) == 3 and d["preventiva_checklist"] == ["Só um item"], m["checklist"])
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"preventiva_checklist": None}, token=token)
    checar("checklist nulo vira lista vazia", st == 200 and r["preventiva_checklist"] == [], (st, r))
    chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "CORRETIVA", "data": str(hoje - timedelta(days=1)), "custo": 420,
        "executado_por": f"FORN FICHA2 {marca}", "nota_fiscal": "773"}, token=token)
    chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "CORRETIVA", "data": str(hoje - timedelta(days=1)), "custo": 90,
        "executado_por": f"FORN FICHA2 {marca}", "nota_fiscal": "774"}, token=token)
    chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "CORRETIVA", "data": str(hoje), "custo": 60,
        "executado_por": f"Técnico avulso {marca}", "nota_fiscal": "9"}, token=token)
    chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "CORRETIVA", "data": str(hoje), "custo": 30,
        "executado_por": f"FORN FICHA2 {marca}", "nota_fiscal": "999"}, token=token)
    chamar("POST", f"/patrimonio/{id_bem}/manutencoes", {
        "tipo": "CORRETIVA", "data": str(hoje), "coberta_garantia": True}, token=token)

    print("\n3. fotos e documentos")
    st, a1 = enviar(f"/patrimonio/{id_bem}/anexos", "forno.png", png(), "image/png", token)
    checar("a foto entra como FOTO", st == 201 and a1["tipo"] == "FOTO", (st, a1))
    st, a2 = enviar(f"/patrimonio/{id_bem}/anexos", "nota fiscal.pdf", PDF, "application/pdf", token)
    checar("o PDF entra como DOCUMENTO, com o nome do arquivo",
           st == 201 and a2["tipo"] == "DOCUMENTO" and a2["nome"] == "nota fiscal.pdf", (st, a2))
    st, tipo, conteudo = bruto(a2["url"])
    checar("o arquivo é servido do banco", st == 200 and conteudo == PDF and "pdf" in tipo, (st, tipo))
    checar("o nome do arquivo não é adivinhável (sufixo longo)",
           len(a2["url"].rsplit("/", 1)[1]) > 30, a2["url"])
    st, r = enviar(f"/patrimonio/{id_bem}/anexos", "planilha.csv", b"a;b", "text/csv", token)
    checar("formato fora da lista é 400", st == 400, (st, r))
    st, r = enviar(f"/patrimonio/{id_bem}/anexos", "falsa.png", b"isto nao e imagem", "image/png", token)
    checar("o que diz ser imagem e não é: 400", st == 400, (st, r))
    st, d = chamar("GET", f"/patrimonio/{id_bem}", token=token)
    checar("o detalhe traz os dois anexos, na ordem de envio",
           [a["id"] for a in d["anexos"]] == [a1["id"], a2["id"]], d["anexos"])
    st, r = chamar("DELETE", f"/patrimonio/anexos/{a1['id']}", token=token)
    st2, _, _ = bruto(a1["url"])
    checar("apagar o anexo apaga o arquivo", st == 200 and st2 == 404, (st, st2))

    print("\n4. situação no Omie (modo simulado)")
    with get_cursor() as cur:
        cur.execute("INSERT INTO fornecedores (nome, codigo_omie) VALUES (%s, '990101') RETURNING id",
                    (f"FORN FICHA2 {marca}",))
        id_forn = cur.fetchone()["id"]
        cur.execute("SELECT id_unidade FROM bens WHERE id = %s", (id_bem,))
        id_unidade = cur.fetchone()["id_unidade"]
        cur.execute("SELECT modo FROM integracoes WHERE id_unidade = %s AND servico = 'OMIE'",
                    (id_unidade,))
        integ = cur.fetchone()
    if integ and integ["modo"] != "simulado":
        print("  (Omie em modo real nesta base — a seção 4 é pulada para não gastar cota)")
    else:
        criou = False
        if not integ:
            with get_cursor() as cur:
                cur.execute("INSERT INTO integracoes (id_unidade, servico, modo, ativa) "
                            "VALUES (%s, 'OMIE', 'simulado', false)", (id_unidade,))
            criou = True
        try:
            st, s = chamar("GET", f"/patrimonio/{id_bem}/omie", token=token)
            checar("a consulta responde em modo simulado", st == 200 and s["modo"] == "simulado", (st, s))
            por = {l["nota_fiscal"]: l for l in s.get("linhas", [])}
            checar("a compra (NF 771, título 000771) está PAGA", por.get("771", {}).get("situacao") == "PAGO",
                   por.get("771"))
            checar("a preventiva com uma parcela paga e outra atrasada: ATRASADO, 1 de 2",
                   por.get("772", {}).get("situacao") == "ATRASADO"
                   and por["772"].get("pagas") == 1 and por["772"].get("parcelas") == 2, por.get("772"))
            checar("a corretiva a vencer: em aberto, com o vencimento",
                   por.get("773", {}).get("situacao") == "ABERTO"
                   and por["773"].get("proximo_vencimento"), por.get("773"))
            checar("título cancelado no Omie: CANCELADO", por.get("774", {}).get("situacao") == "CANCELADO",
                   por.get("774"))
            checar("quem fez sem cadastro com código do Omie: SEM_FORNECEDOR",
                   por.get("9", {}).get("situacao") == "SEM_FORNECEDOR", por.get("9"))
            checar("nota que o fornecedor não tem: NAO_ACHADO",
                   por.get("999", {}).get("situacao") == "NAO_ACHADO", por.get("999"))
            checar("a visita sem custo e sem nota não entra na consulta", len(s["linhas"]) == 6,
                   [l["nota_fiscal"] for l in s["linhas"]])
            checar("o resumo conta pagos, em aberto e atrasados",
                   s["pagos"] == 1 and s["em_aberto"] == 2 and s["atrasados"] == 1, s)
        finally:
            with get_cursor() as cur:
                if criou:
                    cur.execute("DELETE FROM integracoes WHERE id_unidade = %s AND servico = 'OMIE'",
                                (id_unidade,))
    with get_cursor() as cur:
        cur.execute("DELETE FROM fornecedores WHERE id = %s", (id_forn,))

    print("\n5. relatórios e planilha")
    st, tipo, rel = bruto(f"/exportar/patrimonio.csv?busca_bem=ficha2 {marca}", token)
    texto = rel.decode("utf-8-sig")
    checar("os bens trazem Responsável, Garantia (meses), Tipo de garantia e Checklist",
           all(c in texto for c in ("Responsável", "Garantia (meses)", "Tipo de garantia",
                                    "Checklist da preventiva", f"Chef Ana {marca}", "Fábrica")),
           texto[:400])
    chamar("PUT", f"/patrimonio/{id_bem}", {"preventiva_checklist": ["Item A", "Item B"]}, token=token)
    st, tipo, rel = bruto(f"/exportar/patrimonio.csv?busca_bem=ficha2 {marca}", token)
    st, r = enviar("/patrimonio/importar?simular=true", "bens.csv", rel, "text/csv", token)
    checar("a planilha exportada volta pela importação sem mudar nada",
           st == 200 and r["iguais"] >= 1 and not r["mudam"] and not r["recusados"], (st, r))
    trocado = rel.decode("utf-8-sig").replace("Item A; Item B", "Item A; Item C").encode("utf-8")
    st, r = enviar("/patrimonio/importar?simular=true", "bens.csv", trocado, "text/csv", token)
    checar("o checklist mudado na planilha aparece na prévia",
           st == 200 and len(r["mudam"]) == 1
           and r["mudam"][0]["para"].get("Checklist da preventiva") == "Item A; Item C", (st, r))
    st, tipo, rel = bruto(f"/exportar/patrimonio-manutencoes.csv?busca_bem=ficha2 {marca}", token)
    texto = rel.decode("utf-8-sig")
    checar("as manutenções trazem Nota fiscal e Checklist",
           "Nota fiscal" in texto and "Checklist" in texto and "2 de 3 itens" in texto, texto[:400])

    print("\n6. permissões")
    tc = garantir_cozinha(chamar, token)
    st, r = enviar(f"/patrimonio/{id_bem}/anexos", "laudo.pdf", PDF, "application/pdf", tc)
    checar("a cozinha (manutenção) anexa o laudo", st == 201, (st, r))
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"responsavel": "outro"}, token=tc)
    checar("mas não edita o bem (403)", st == 403, (st, r))

    print("\n7. apagar o bem leva os anexos")
    st, b2 = chamar("POST", "/patrimonio", {"descricao": f"Cadastro errado ficha2 {marca}"}, token=token)
    st, a3 = enviar(f"/patrimonio/{b2['id']}/anexos", "x.png", png(), "image/png", token)
    st, r = chamar("DELETE", f"/patrimonio/{b2['id']}", token=token)
    st2, _, _ = bruto(a3["url"])
    checar("o bem sem histórico apaga, e o arquivo some junto", st == 200 and st2 == 404, (st, st2))

    # limpeza: o bem com histórico se baixa (as suítes não apagam história)
    chamar("PUT", f"/patrimonio/{id_bem}", {"situacao": "BAIXADO", "motivo_baixa": "teste"}, token=token)

    print(f"\n{ok} ok, {len(falhas)} falha(s)")
    if falhas:
        for f in falhas:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
