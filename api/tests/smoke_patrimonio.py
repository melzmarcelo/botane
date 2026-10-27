"""Teste de fumaça do Patrimônio (migração 139): bens, plaqueta, planilha e manutenção.

🔑 Pedido do dono (27/10/2026): *"um processo para inventariar o patrimônio"*, com a
planilha `Inventario_Equipamentos_Botane.xlsx` — e, da proposta, *"pode seguir com as
etapas 1 e 2"*. Confere:

    1. Cadastro: o código da plaqueta nasce sozinho (PAT-…); apelido repetido é 409;
       local de outra loja é 400; o detalhe diz quanto estoque está no local do bem.
    2. Preventiva: a próxima é calculada (última + meses) e o status vira VENCIDA,
       VENCE_30 ou EM_DIA; o alerta cobra a vencida e o crítico parado.
    3. Manutenção: a preventiva anda o plano; data no futuro é 400; a corretiva devolve o
       bem ao uso; apagar a preventiva volta a "última" para a anterior.
    4. Baixa pede motivo; bem com histórico não se apaga (409); a lista esconde o baixado.
    5. Planilha .xlsx da casa (aba por setor, cabeçalho procurado): prévia, recusa nomeada,
       sugestão como "A confirmar"; importar de novo não duplica; célula mudada atualiza.
    6. O relatório exportado volta pela importação sem mudar nada.
    7. Plaqueta em PDF, o QR acha o bem, e o relatório de manutenções traz o custo.
    8. Cozinha vê e registra manutenção, mas não cadastra (403).
    9. O produto Patrimônio (pedido do dono, 27/10/2026): o que ENTRA vira pendência
       ("faltam N bens") e alerta; o Novo bem sugere da última entrada; só produto do tipo
       Patrimônio pode ser o do bem; a planilha liga pelo código do produto.

    python tests/smoke_patrimonio.py      (API de pé na 9200)
"""

import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import date, timedelta

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


def enviar(caminho, nome, conteudo, token):
    """multipart/form-data à mão: um campo `arquivo`."""
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
             f"filename=\"{nome}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
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


def xlsx(abas: list[tuple[str, list[list[str]]]]) -> bytes:
    """Uma planilha .xlsx mínima, com células de texto — o que o Excel salva, sem estilo."""
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>")
        folhas, rels = [], []
        for i, (nome, linhas) in enumerate(abas, start=1):
            folhas.append(f'<sheet name="{escape(nome)}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/'
                        f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
            corpo = []
            for n, linha in enumerate(linhas, start=1):
                celulas = "".join(
                    f'<c r="{chr(65 + j)}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                    for j, v in enumerate(linha) if v != "")
                corpo.append(f'<row r="{n}">{celulas}</row>')
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                       '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                       'spreadsheetml/2006/main"><sheetData>' + "".join(corpo)
                       + "</sheetData></worksheet>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships"><sheets>' + "".join(folhas)
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/relationships">' + "".join(rels) + "</Relationships>")
    return buf.getvalue()


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
token = r["access_token"]
init_pool()
criados_setores: list[int] = []
criados_locais: list[int] = []
criados_produtos: list[int] = []

try:
    print("1. cadastro")
    st, s = chamar("POST", "/setores", {"nome": f"SETOR PAT {marca}"}, token=token)
    id_setor = (s or {}).get("id")
    criados_setores.append(id_setor)
    st, l = chamar("POST", "/locais", {"nome": f"CAMARA PAT {marca}", "tipo": "RESFRIADO",
                                       "id_setor": id_setor}, token=token)
    id_local = (l or {}).get("id")
    criados_locais.append(id_local)
    checar("setor e local nascem", bool(id_setor and id_local), (s, l))
    st, p = chamar("POST", "/produtos", {"nome": f"QUEIJO PAT {marca}", "tipo": "INSUMO",
                                         "um_estoque": "KG", "status": "ATIVO"}, token=token)
    id_prod = p["id"]
    criados_produtos.append(id_prod)
    chamar("POST", "/estoque/entradas", {"id_produto": id_prod, "quantidade": 2,
                                         "custo_unitario": 40, "id_local": id_local,
                                         "documento": f"NF-PAT-{marca}"}, token=token)

    st, b = chamar("POST", "/patrimonio", {
        "descricao": f"Câmara fria {marca}", "apelido": f"CF-{marca}", "id_setor": id_setor,
        "id_local": id_local, "marca": "Gelopar", "criticidade": "ALTA",
        "preventiva_meses": 6, "ultima_preventiva": str(hoje - timedelta(days=220)),
        "valor_compra": 15000, "garantia_ate": str(hoje + timedelta(days=100))}, token=token)
    checar("o bem nasce com o código da plaqueta", st == 201
           and (b or {}).get("codigo", "").startswith("PAT-"), (st, b))
    id_bem, codigo = b["id"], b["codigo"]
    checar("em garantia, e a preventiva de 7 meses atrás com plano de 6 está VENCIDA",
           b["em_garantia"] and b["status_preventiva"] == "VENCIDA", b)
    st, r = chamar("POST", "/patrimonio", {"descricao": "Outro", "apelido": f"cf-{marca}"},
                   token=token)
    checar("apelido repetido (sem diferença de maiúscula) é 409", st == 409, (st, r))
    cur_local = None
    with get_cursor() as cur:
        cur.execute("SELECT id FROM locais_estoque WHERE id_unidade <> %s LIMIT 1",
                    (b["id_unidade"],))
        x = cur.fetchone()
        cur_local = x["id"] if x else None
    if cur_local:
        st, r = chamar("POST", "/patrimonio", {"descricao": "Fora", "id_local": cur_local},
                       token=token)
        checar("local de outra loja é 400", st == 400, (st, r))
    st, d = chamar("GET", f"/patrimonio/{id_bem}", token=token)
    checar("o detalhe diz o estoque guardado no local (1 produto, R$ 80)",
           d["estoque_no_local"]["produtos"] >= 1 and d["estoque_no_local"]["valor"] >= 80, d)

    print("\n2. preventiva e alertas")
    st, al = chamar("GET", "/alertas", token=token)
    chaves = {a["chave"]: a["quantidade"] for a in al}
    checar("o alerta cobra a preventiva vencida", chaves.get("patrimonio.preventiva_vencida", 0) >= 1,
           chaves)
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"situacao": "PARADO"}, token=token)
    st, al = chamar("GET", "/alertas", token=token)
    chaves = {a["chave"]: a["quantidade"] for a in al}
    checar("crítico parado é alerta crítico", chaves.get("patrimonio.critico_parado", 0) >= 1, chaves)
    st, lst = chamar("GET", f"/patrimonio?preventiva=VENCIDA&busca={marca}", token=token)
    checar("a lista filtra pelo status da preventiva", [x["id"] for x in lst] == [id_bem], lst)
    st, rs = chamar("GET", "/patrimonio/resumo", token=token)
    meu = next((s for s in rs["setores"] if s["id_setor"] == id_setor), {})
    checar("o resumo por setor conta o crítico, o parado e a vencida",
           meu.get("bens") == 1 and meu.get("criticidade_alta") == 1 and meu.get("parados") == 1
           and meu.get("vencidas") == 1, meu)

    print("\n3. manutenção")
    st, r = chamar("POST", f"/patrimonio/{id_bem}/manutencoes",
                   {"tipo": "PREVENTIVA", "data": str(hoje + timedelta(days=1))}, token=token)
    checar("data no futuro é 400", st == 400, (st, r))
    st, r = chamar("POST", f"/patrimonio/{id_bem}/manutencoes",
                   {"tipo": "CORRETIVA", "data": str(hoje - timedelta(days=2)), "custo": 350,
                    "executado_por": "Frio Sul", "descricao": "troca do compressor",
                    "situacao_depois": "EM_USO"}, token=token)
    checar("a corretiva grava e devolve o bem ao uso",
           st == 201 and r["bem"]["situacao"] == "EM_USO", (st, r))
    st, r = chamar("POST", f"/patrimonio/{id_bem}/manutencoes",
                   {"tipo": "PREVENTIVA", "data": str(hoje), "custo": 200}, token=token)
    id_prev = r.get("id")
    checar("a preventiva de hoje anda o plano: última = hoje, EM_DIA",
           st == 201 and r["bem"]["ultima_preventiva"] == str(hoje)
           and r["bem"]["status_preventiva"] == "EM_DIA"
           and r["bem"]["proxima_preventiva"] > str(hoje + timedelta(days=170)), r)
    st, r = chamar("POST", f"/patrimonio/{id_bem}/manutencoes",
                   {"tipo": "PREVENTIVA", "data": str(hoje - timedelta(days=30))}, token=token)
    st, d = chamar("GET", f"/patrimonio/{id_bem}", token=token)
    checar("uma preventiva mais VELHA não volta a última para trás",
           d["ultima_preventiva"] == str(hoje), d["ultima_preventiva"])
    checar("o detalhe soma o custo (R$ 550) e lista a mais nova primeiro",
           d["custo_manutencao"] == 550 and d["manutencoes"][0]["id"] == id_prev, d["manutencoes"])
    st, r = chamar("DELETE", f"/patrimonio/manutencoes/{id_prev}", token=token)
    st, d = chamar("GET", f"/patrimonio/{id_bem}", token=token)
    checar("apagar a preventiva de hoje volta a última para a anterior (30 dias)",
           st == 200 and d["ultima_preventiva"] == str(hoje - timedelta(days=30)), d["ultima_preventiva"])

    print("\n4. baixa")
    st, r = chamar("DELETE", f"/patrimonio/{id_bem}", token=token)
    checar("bem com histórico não se apaga (409)", st == 409, (st, r))
    st, r = chamar("PUT", f"/patrimonio/{id_bem}", {"situacao": "BAIXADO"}, token=token)
    checar("baixa sem motivo é 400", st == 400, (st, r))
    st, r = chamar("PUT", f"/patrimonio/{id_bem}",
                   {"situacao": "BAIXADO", "motivo_baixa": "trocada por uma nova"}, token=token)
    checar("baixa com motivo", st == 200 and r["situacao"] == "BAIXADO", (st, r))
    st, lst = chamar("GET", f"/patrimonio?busca={marca}", token=token)
    checar("a lista esconde o baixado", id_bem not in [x["id"] for x in lst], lst)
    st, lst = chamar("GET", f"/patrimonio?busca={marca}&situacao=BAIXADO", token=token)
    checar("e o traz quando pedido", id_bem in [x["id"] for x in lst], lst)
    st, al = chamar("GET", "/alertas", token=token)
    chaves = {a["chave"]: a["quantidade"] for a in al}

    print("\n5. planilha da casa (.xlsx)")
    nome_setor, nome_local = f"SETOR PAT {marca}", f"CAMARA PAT {marca}"
    cab = ["Código", "Equipamento", "Local no sistema", "Origem do registro", "Marca",
           "Modelo", "Nº de série / patrimônio", "Tensão", "Data de compra", "Garantia até",
           "Fornecedor / assistência", "Contato", "Criticidade", "Situação",
           "Preventiva a cada (meses)", "Última preventiva", "Próxima preventiva",
           "Status da preventiva", "Observações"]
    linhas = [
        [f"Inventário de equipamentos – Teste {marca}"],
        [f"Setor no sistema Botané: {nome_setor}  ·  Loja: Matriz"],
        ["Células amarelas: preencher."],
        cab,
        [f"T{marca}-01", f"Geladeira teste {marca}", nome_local, "Sistema Botané", "Consul",
         "", "SN-1", "220 V", "45000", "15/03/2030", "Frio Sul", "(47) 0000", "Alta",
         "Em uso", "6", "01/09/2026", "", "Sem plano", ""],
        [f"T{marca}-02", f"Liquidificador teste {marca}", "", "Sugestão"] + [""] * 15,
        [f"T{marca}-03", f"Forno teste {marca}", "", "Sistema Botané"] + [""] * 8
        + ["Altíssima"] + [""] * 6,
        [f"T{marca}-04", f"Fogão teste {marca}", "LOCAL QUE NAO EXISTE", "Sistema Botané"]
        + [""] * 15,
        [f"T{marca}-05"] + [""] * 18,
    ]
    arquivo = xlsx([("Resumo", [["Setor", "Equipamentos"]]), ("Teste", linhas)])
    st, pv = enviar("/patrimonio/importar?simular=true", "inv.xlsx", arquivo, token)
    novos = {n["apelido"]: n for n in (pv or {}).get("novos", [])}
    checar("a prévia lê a aba certa e pula a linha sem equipamento (4 linhas)",
           st == 200 and pv["linhas"] == 4, (st, pv))
    g = novos.get(f"T{marca}-01", {}).get("campos", {})
    checar("a geladeira entra com setor da aba, local, data do Excel (45000 = 15/03/2023) e Alta",
           g.get("Setor") == nome_setor and g.get("Local") == nome_local
           and g.get("Compra") == "15/03/2023" and g.get("Criticidade") == "Alta"
           and g.get("Tensão") == "220 V", g)
    checar("a sugestão entra como 'A confirmar'",
           novos.get(f"T{marca}-02", {}).get("campos", {}).get("Situação") == "A confirmar",
           novos.get(f"T{marca}-02"))
    motivos = {r["descricao"]: r["motivo"] for r in pv.get("recusados", [])}
    checar("criticidade e local inexistentes são recusas nomeadas",
           "Altíssima" in motivos.get(f"Forno teste {marca}", "")
           and "LOCAL QUE NAO EXISTE" in motivos.get(f"Fogão teste {marca}", ""), motivos)
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM bens WHERE descricao LIKE %s", (f"%teste {marca}",))
        checar("a prévia não grava nada", cur.fetchone()["n"] == 0)
    st, pv = enviar("/patrimonio/importar?simular=true&incluir_sugestoes=false", "inv.xlsx",
                    arquivo, token)
    checar("sem as sugestões, só a geladeira é nova",
           [n["apelido"] for n in pv["novos"]] == [f"T{marca}-01"], pv["novos"])
    st, ap = enviar("/patrimonio/importar?simular=false", "inv.xlsx", arquivo, token)
    checar("importa: 2 novos", st == 200 and ap["aplicado"] and len(ap["novos"]) == 2, (st, ap))
    st, de_novo = enviar("/patrimonio/importar?simular=true", "inv.xlsx", arquivo, token)
    checar("a mesma planilha de novo não duplica (2 sem mudança)",
           not de_novo["novos"] and not de_novo["mudam"] and de_novo["iguais"] == 2, de_novo)
    linhas[4][4] = "Electrolux"
    st, muda = enviar("/patrimonio/importar?simular=false", "inv.xlsx",
                      xlsx([("Teste", linhas)]), token)
    checar("a célula mudada atualiza (Consul → Electrolux)",
           len(muda["mudam"]) == 1 and muda["mudam"][0]["para"] == {"Marca": "Electrolux"}, muda)

    print("\n6. o relatório volta pela importação")
    st, tipo, csv = baixar(f"/exportar/patrimonio.csv?busca_bem={marca}", token)
    texto = csv.decode("utf-8-sig")
    checar("a planilha do relatório tem as colunas da casa",
           "Fornecedor / assistência" in texto and "Status da preventiva" in texto
           and f"Geladeira teste {marca}" in texto, texto[:400])
    st, volta = enviar("/patrimonio/importar?simular=true", "patrimonio.csv", csv, token)
    checar("e volta sem mudar nada (o código PAT acha cada bem)",
           st == 200 and not volta["novos"] and not volta["mudam"] and not volta["recusados"],
           (st, volta))

    print("\n7. plaqueta, QR e manutenções")
    st, tipo, pdf = baixar(f"/patrimonio/plaquetas.pdf?ids={id_bem}", token)
    checar("a plaqueta sai em PDF", st == 200 and "pdf" in tipo and pdf[:4] == b"%PDF")
    st, r = chamar("GET", f"/patrimonio/codigo/{codigo.lower()}", token=token)
    checar("o QR acha o bem pelo código (sem diferença de maiúscula)",
           st == 200 and r["id"] == id_bem, (st, r))
    st, tipo, rel = baixar(f"/exportar/patrimonio-manutencoes.csv?busca_bem={marca}", token)
    texto = rel.decode("utf-8-sig")
    checar("o relatório de manutenções traz a corretiva e o custo",
           "troca do compressor" in texto and "350" in texto, texto[:500])

    print("\n8. quem pode o quê")
    tk_coz = garantir_cozinha(chamar, token)
    st, r = chamar("GET", f"/patrimonio?busca={marca}", token=tk_coz)
    checar("a cozinha vê os bens", st == 200, (st, r))
    st, r = chamar("POST", "/patrimonio", {"descricao": "Tentativa"}, token=tk_coz)
    checar("e não cadastra (403)", st == 403, (st, r))
    st, lst = chamar("GET", f"/patrimonio?busca=Geladeira teste {marca}", token=token)
    st, r = chamar("POST", f"/patrimonio/{lst[0]['id']}/manutencoes",
                   {"tipo": "CORRETIVA", "data": str(hoje)}, token=tk_coz)
    checar("mas registra a visita do técnico", st == 201, (st, r))

    print("\n9. o produto Patrimônio")
    st, pp = chamar("POST", "/produtos", {"nome": f"BATEDEIRA PAT {marca}", "tipo": "PATRIMONIO",
                                          "um_estoque": "UN", "status": "ATIVO"}, token=token)
    id_pp = pp["id"]
    criados_produtos.append(id_pp)
    st, r = chamar("POST", "/estoque/entradas", {"id_produto": id_pp, "quantidade": 3,
                                                 "custo_unitario": 1200, "id_local": id_local,
                                                 "documento": f"NF-BAT-{marca}"}, token=token)
    checar("entram 3 batedeiras no estoque", st in (200, 201), (st, r))
    st, pend = chamar("GET", "/patrimonio/a-cadastrar", token=token)
    minha = next((x for x in pend if x["id_produto"] == id_pp), None)
    checar("a lista do que falta cadastrar traz o produto: faltam 3, e onde está",
           minha and minha["faltam"] == 3 and nome_local in (minha["onde"] or ""), minha)
    st, al = chamar("GET", "/alertas", token=token)
    chaves = {a["chave"]: a["quantidade"] for a in al}
    checar("e o alerta cobra os itens", chaves.get("patrimonio.a_cadastrar", 0) >= 3, chaves)
    st, dp = chamar("GET", f"/patrimonio/do-produto/{id_pp}", token=token)
    sg = dp.get("sugestao", {})
    checar("o Novo bem sugere da última entrada: nome, local, data e valor (quem vê custo)",
           sg.get("descricao") == f"BATEDEIRA PAT {marca}" and sg.get("id_local") == id_local
           and sg.get("data_compra") == str(hoje) and sg.get("valor_compra") == 1200, sg)
    st, r = chamar("POST", "/patrimonio", {"descricao": "Queijo?", "id_produto": id_prod}, token=token)
    checar("produto que não é Patrimônio é 400", st == 400 and "Patrimônio" in r["detail"], (st, r))
    st, b1 = chamar("POST", "/patrimonio", {"descricao": f"Batedeira 1 {marca}", "id_produto": id_pp},
                    token=token)
    checar("o bem nasce ligado ao produto", st == 201 and b1["id_produto"] == id_pp
           and b1["produto"] == f"BATEDEIRA PAT {marca}", (st, b1))
    st, dp = chamar("GET", f"/patrimonio/do-produto/{id_pp}", token=token)
    checar("um bem a mais: faltam 2, e o produto lista o bem", dp["faltam"] == 2
           and [b["id"] for b in dp["bens"]] == [b1["id"]], dp)
    st, lst = chamar("GET", f"/patrimonio?id_produto={id_pp}", token=token)
    checar("a lista filtra pelo produto", [x["id"] for x in lst] == [b1["id"]], lst)
    plan = xlsx([("Bens", [["Código", "Equipamento", "Código do produto", "Produto"],
                           [f"B{marca}-2", f"Batedeira 2 {marca}", pp["codigo"], ""],
                           [f"B{marca}-3", f"Batedeira 3 {marca}", "", f"Batedeira pat {marca}"],
                           [f"B{marca}-4", f"Batedeira 4 {marca}", "NAO-EXISTE", ""]])])
    st, ap = enviar("/patrimonio/importar?simular=false", "b.xlsx", plan, token)
    checar("a planilha liga pelo código do produto e pelo nome (sem maiúscula)",
           st == 200 and len(ap["novos"]) == 2
           and all(n["campos"].get("Produto") == f"BATEDEIRA PAT {marca}" for n in ap["novos"]), ap)
    checar("e recusa o código que não é de produto Patrimônio",
           len(ap["recusados"]) == 1 and "NAO-EXISTE" in ap["recusados"][0]["motivo"], ap["recusados"])
    st, pend = chamar("GET", "/patrimonio/a-cadastrar", token=token)
    checar("com os 3 cadastrados, o produto sai da lista do que falta",
           not any(x["id_produto"] == id_pp for x in pend), pend)
    st, tipo, csv = baixar(f"/exportar/patrimonio.csv?busca_bem=Batedeira 2 {marca}", token)
    texto = csv.decode("utf-8-sig")
    checar("o relatório traz o produto e o código dele",
           "Código do produto" in texto and pp["codigo"] in texto, texto[:600])
finally:
    with get_cursor() as cur:
        cur.execute("DELETE FROM bens WHERE descricao LIKE %s OR apelido LIKE %s",
                    (f"%{marca}%", f"%{marca}%"))
    for i in criados_produtos:
        chamar("DELETE", f"/produtos/{i}", token=token)
    for i in criados_locais:
        chamar("DELETE", f"/locais/{i}", token=token)
    for i in criados_setores:
        chamar("DELETE", f"/setores/{i}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
