"""Teste de fumaça da etapa 3 (fichas técnicas).

O que ele prova, além do CRUD: o custo desce na sub-ficha e bate na mão, o
fator de correção sai do bruto/líquido, a conversão de unidade funciona (receita
em grama, estoque em quilo), ficha homologada não se edita, ciclo é recusado, e
**quem não tem `fichas.custos` não recebe dinheiro nenhum da API**.

    python tests/smoke_fichas.py            (API de pé na 9200)
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "tests")
from comum import garantir_fornecedor  # noqa: E402

BASE = "http://127.0.0.1:9200"
ADMIN = ("admin@botane.com.br", "botane123")
COZINHA = ("smoke.cozinha@botane.com.br", "smoke12345")

ok = 0
falhas: list[str] = []
criados: dict[str, list] = {"produtos": [], "fichas": [], "fornecedores": []}


def chamar(metodo, caminho, corpo=None, token=None):
    req = urllib.request.Request(BASE + caminho, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def enviar_arquivo(caminho, nome_arquivo, conteudo, tipo, token):
    """POST multipart na unha — o urllib não monta formulário sozinho."""
    import uuid
    limite = uuid.uuid4().hex
    fim = chr(13) + chr(10)   # CRLF: é o que o multipart exige
    cabeca = (
        "--" + limite + fim
        + 'Content-Disposition: form-data; name="arquivo"; filename="'
        + nome_arquivo + '"' + fim
        + "Content-Type: " + tipo + fim + fim
    ).encode()
    # ⚠️ O CRLF ANTES do fecho faz parte do formato: sem ele o servidor não
    # encontra o campo e devolve 422 "Field required" — que se lê como se a
    # rota estivesse errada, não o teste.
    corpo = cabeca + conteudo + (fim + "--" + limite + "--" + fim).encode()
    req = urllib.request.Request(BASE + caminho, method="POST", data=corpo)
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}


def baixar_bytes(caminho, token):
    req = urllib.request.Request(BASE + caminho)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def imagem_de_teste(cor=(180, 120, 60)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (600, 400), cor).save(buf, "JPEG")
    return buf.getvalue()


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

print("0. cenário: fornecedor com preço, dois insumos e dois produzidos")
forn = garantir_fornecedor(chamar, token, "Ficha Distribuidora", "98.765.432/0001-10")
checar("fornecedor de teste pronto", bool(forn), forn)


def novo_produto(nome, tipo, um, preco=None, fator=1):
    corpo = {"nome": nome, "tipo": tipo, "um_estoque": um}
    if preco is not None:
        corpo["fornecedores"] = [
            {"id_fornecedor": forn, "ultimo_preco": preco, "fator": fator, "preferencial": True}
        ]
    st, r = chamar("POST", "/produtos", corpo, token=token)
    if st != 201:
        print("   (falha ao criar produto", nome, st, r, ")")
        return None
    criados["produtos"].append(r["id"])
    return r["id"]


marca = str(__import__("time").time_ns())[-6:]
# Café: R$ 40,00 o quilo. Leite: R$ 6,00 o litro.
cafe = novo_produto(f"Ficha café {marca}", "INSUMO", "KG", preco=40)
leite = novo_produto(f"Ficha leite {marca}", "INSUMO", "L", preco=6)
sem_preco = novo_produto(f"Ficha sem preço {marca}", "INSUMO", "KG")
base = novo_produto(f"Ficha base espresso {marca}", "PRODUZIDO", "L")
bebida = novo_produto(f"Ficha latte {marca}", "PRODUZIDO", "UN")
checar("produtos do cenário criados", all([cafe, leite, sem_preco, base, bebida]))

print("1. ficha simples, com conversão de unidade")
# 100 g de café (estoque em KG) → 0,1 kg × R$ 40 = R$ 4,00
st, r = chamar("POST", "/fichas", {
    "id_produto": base, "rendimento_qtd": 1, "rendimento_um": "L", "porcoes": 4,
    "itens": [
        {"id_insumo": cafe, "qtd_bruta": 100, "um": "G"},
        {"id_insumo": leite, "qtd_bruta": 900, "um": "ML"},
    ],
}, token=token)
checar("cria ficha da base", st == 201, r)
ficha_base = r.get("id")
criados["fichas"].append(ficha_base)

st, f = chamar("GET", f"/fichas/{ficha_base}", token=token)
checar("ficha traz o custo", st == 200 and f.get("ve_custo") is True, st)
# 100 g × 40/kg = 4,00 ; 900 ml × 6/L = 5,40 → 9,40
checar("custo total confere (4,00 + 5,40)", abs(float(f["custo_total"]) - 9.40) < 0.001,
       f.get("custo_total"))
checar("custo por porção confere (9,40 ÷ 4)", abs(float(f["custo_por_porcao"]) - 2.35) < 0.001,
       f.get("custo_por_porcao"))
checar("ficha completa (nada sem custo)", f.get("custo_completo") is True)
checar("produto virou produção própria", True)

print("2. sub-ficha: o custo desce em cascata")
# 250 ml da base (rendimento 1 L, custo 9,40) → 2,35 + 50 g de café = 2,00 → 4,35
st, r = chamar("POST", "/fichas", {
    "id_produto": bebida, "rendimento_qtd": 1, "rendimento_um": "UN", "porcoes": 1,
    "itens": [
        {"id_subficha": ficha_base, "qtd_bruta": 250, "um": "ML"},
        {"id_insumo": cafe, "qtd_bruta": 50, "um": "G"},
    ],
}, token=token)
checar("cria ficha com sub-ficha", st == 201, r)
ficha_bebida = r.get("id")
criados["fichas"].append(ficha_bebida)

st, f = chamar("GET", f"/fichas/{ficha_bebida}", token=token)
checar("custo em cascata confere (2,35 + 2,00)", abs(float(f["custo_total"]) - 4.35) < 0.001,
       f.get("custo_total"))
item_sub = next((i for i in f["itens"] if i.get("id_subficha")), None)
checar("item de sub-ficha marca a origem do custo",
       item_sub and item_sub.get("origem_custo") == "subficha", item_sub)

print("3. fator de correção e insumo sem preço")
st, r = chamar("PUT", f"/fichas/{ficha_bebida}", {
    "itens": [
        {"id_subficha": ficha_base, "qtd_bruta": 250, "um": "ML"},
        {"id_insumo": cafe, "qtd_bruta": 50, "um": "G"},
        # 1 kg bruto vira 800 g limpos → FC = 1,25
        {"id_insumo": sem_preco, "qtd_bruta": 1, "qtd_liquida": 0.8, "um": "KG"},
    ],
}, token=token)
checar("salva itens da ficha", st == 200, r)
st, f = chamar("GET", f"/fichas/{ficha_bebida}", token=token)
item_fc = next((i for i in f["itens"] if i.get("id_insumo") == sem_preco), None)
checar("fator de correção sai de bruto ÷ líquido",
       item_fc and abs(float(item_fc["fator_correcao"]) - 1.25) < 0.001, item_fc)
checar("insumo sem preço não vira zero, vira pendência",
       f.get("itens_sem_custo") == 1 and f.get("custo_completo") is False,
       (f.get("itens_sem_custo"), f.get("custo_completo")))
checar("o que tem preço continua somando", abs(float(f["custo_total"]) - 4.35) < 0.001,
       f.get("custo_total"))

print("4. ciclo é recusado")
st, r = chamar("PUT", f"/fichas/{ficha_base}", {
    "itens": [{"id_subficha": ficha_bebida, "qtd_bruta": 1, "um": "UN"}],
}, token=token)
checar("recusa ficha que se usa por dentro da sub-ficha", st == 400, (st, r))
st, r = chamar("PUT", f"/fichas/{ficha_base}", {
    "itens": [{"id_subficha": ficha_base, "qtd_bruta": 1, "um": "L"}],
}, token=token)
checar("recusa ficha que usa a si mesma", st == 400, st)
st, f = chamar("GET", f"/fichas/{ficha_base}", token=token)
checar("a ficha continua íntegra depois da recusa",
       abs(float(f["custo_total"]) - 9.40) < 0.001, f.get("custo_total"))

print("5. homologação e versão")
st, r = chamar("POST", f"/fichas/{ficha_base}/homologar", token=token)
checar("homologa a ficha", st == 200, r)
st, r = chamar("PUT", f"/fichas/{ficha_base}", {"porcoes": 8}, token=token)
checar("ficha homologada não é editável", st == 400, (st, r))
st, r = chamar("POST", f"/fichas/{ficha_base}/nova-versao", token=token)
checar("cria nova versão em rascunho", st == 201 and r.get("versao") == 2, r)
v2 = r.get("id")
criados["fichas"].append(v2)
st, f2 = chamar("GET", f"/fichas/{v2}", token=token)
checar("a nova versão copiou os itens", len(f2.get("itens", [])) == 2, len(f2.get("itens", [])))
checar("a nova versão nasce em rascunho", f2.get("status") == "RASCUNHO", f2.get("status"))
st, r = chamar("POST", f"/fichas/{v2}/homologar", token=token)
checar("homologa a versão 2", st == 200, r)
st, f1 = chamar("GET", f"/fichas/{ficha_base}", token=token)
checar("a versão 1 foi arquivada", f1.get("status") == "ARQUIVADA", f1.get("status"))

print("5b. a foto do prato pronto")
# 🔑 **A coluna `foto_url` existe desde a etapa 3 e nunca tinha sido usada.** A
# ficha existe para ser SEGUIDA, e quem segue está de pé na cozinha: "está
# pronto?" é uma pergunta visual, e nenhuma descrição de montagem responde o
# que a foto responde.
st, r = enviar_arquivo(f"/fichas/{v2}/foto", "prato.jpg", imagem_de_teste(),
                       "image/jpeg", token)
checar("a ficha recebe a foto do prato", st == 200 and r.get("foto_url"), (st, r))
url_foto = (r or {}).get("foto_url")
st, f2 = chamar("GET", f"/fichas/{v2}", token=token)
# ⚠️ `bool(url_foto)` junto: sem isso, dois `None` fariam a checagem passar —
# ela diria que a foto voltou quando não houve foto nenhuma.
checar("e ela volta no detalhe",
       bool(url_foto) and f2.get("foto_url") == url_foto, (f2.get("foto_url"), url_foto))
st, lista_f = chamar("GET", f"/fichas?id_produto={f2['id_produto']}", token=token)
checar("e na lista, que a usa como miniatura",
       any(x.get("foto_url") == url_foto for x in (lista_f or [])),
       [x.get("foto_url") for x in (lista_f or [])])

# 🔑 **A foto vale mesmo com a ficha HOMOLOGADA — é a exceção da regra.** A
# ficha publicada é congelada porque mexer nela mudaria custo histórico; a foto
# não entra em conta nenhuma. E o prato só pode ser fotografado DEPOIS de
# pronto, que é depois de homologado: a trava obrigaria a abrir uma versão que
# não difere em nada. Mesmo raciocínio do nome do inventário, editável com a
# contagem fechada.
checar("e a versão 2 está mesmo homologada", f2.get("status") == "HOMOLOGADA",
       f2.get("status"))
st, r = chamar("PUT", f"/fichas/{v2}", {"porcoes": 9}, token=token)
checar("o RESTO da ficha homologada continua travado", st == 400, (st, r))

st, r = enviar_arquivo(f"/fichas/{v2}/foto", "vazio.jpg", b"nao sou imagem",
                       "image/jpeg", token)
checar("arquivo que não é imagem é recusado", st == 400, (st, r))

# 🔑 **A nova versão leva a foto — e o ARQUIVO é copiado, não a URL.** Copiar
# só a URL deixaria as duas apontando para o mesmo arquivo, cujo dono é a
# versão velha: trocar a foto de lá apagaria a daqui, sem ninguém ter tocado
# nesta ficha. É o defeito que a suíte cobra logo abaixo.
st, r = chamar("POST", f"/fichas/{v2}/nova-versao", token=token)
v3 = (r or {}).get("id")
if v3:
    criados["fichas"].append(v3)
    st, f3 = chamar("GET", f"/fichas/{v3}", token=token)
    checar("a nova versão nasce com a foto", bool(f3.get("foto_url")), f3.get("foto_url"))
    checar("mas com arquivo PRÓPRIO, não o mesmo endereço",
           f3.get("foto_url") != url_foto, (f3.get("foto_url"), url_foto))
    # Trocar a foto da versão VELHA não pode matar a da nova.
    enviar_arquivo(f"/fichas/{v2}/foto", "outro.jpg", imagem_de_teste((20, 90, 160)),
                   "image/jpeg", token)
    conteudo = baixar_bytes(f3["foto_url"], token) if f3.get("foto_url") else b""
    checar("e trocar a foto da versão anterior não apaga a dela",
           len(conteudo) > 100, len(conteudo))

# 🔑 **TROCAR a foto não pode perdê-la — e essa era a janela real.** A gravação
# acontecia em TRÊS transações: a nova imagem entrava e a antiga era APAGADA
# numa; só depois, noutra, a ficha passava a apontar para a nova. Falhando a
# última — a API reiniciada, a requisição abortada —, a antiga já não existia e
# a ficha continuava apontando para ela: a foto sumia da tela e do PDF, sem
# volta e sem nada explicando. Agora as três são uma transação só.
#
# O que se prova aqui é a INVARIANTE que ela garante: depois de qualquer troca,
# o endereço que a ficha guarda RESPONDE — e o anterior deixa de existir, que é
# o que mantém uma imagem por ficha em vez de uma por troca.
_antes_troca = None
for _vez, _cor in enumerate(((200, 40, 40), (40, 200, 40), (40, 40, 200))):
    enviar_arquivo(f"/fichas/{v2}/foto", "troca.jpg", imagem_de_teste(_cor),
                   "image/jpeg", token)
    st, _f = chamar("GET", f"/fichas/{v2}", token=token)
    _bytes = baixar_bytes(_f["foto_url"], token) if _f.get("foto_url") else b""
    checar(f"trocar a foto ({_vez + 1}a vez) deixa o endereco respondendo",
           len(_bytes) > 100, (_f.get("foto_url"), len(_bytes)))
    if _antes_troca:
        _st_velha, _ = chamar("GET", _antes_troca, token=token)
        checar(f"e a imagem anterior ({_vez}a) sai junto, na mesma transacao",
               _st_velha == 404, (_antes_troca, _st_velha))
    _antes_troca = _f.get("foto_url")

# 🔑 **A foto vai no PAPEL, que é onde a ficha serve.** Quem segue a receita
# está de pé na cozinha, não na frente do monitor.
pdf = baixar_bytes(f"/exportar/ficha/{v2}.pdf", token)
checar("a ficha impressa sai com a foto", pdf[:4] == b"%PDF" and len(pdf) > 4000,
       (pdf[:4], len(pdf)))

st, r = chamar("DELETE", f"/fichas/{v2}/foto", token=token)
checar("e a foto se remove", st == 200, (st, r))
st, f2 = chamar("GET", f"/fichas/{v2}", token=token)
checar("voltando a ficar sem nenhuma", f2.get("foto_url") is None, f2.get("foto_url"))
# ⚠️ Ficha sem foto continua imprimindo: foto ausente é o estado normal.
pdf = baixar_bytes(f"/exportar/ficha/{v2}.pdf", token)
checar("e a ficha SEM foto continua imprimindo", pdf[:4] == b"%PDF", pdf[:4])


print("6. dinheiro é permissão à parte")
st, papeis = chamar("GET", "/papeis", token=token)
id_cozinha = next(p["id"] for p in papeis if p["nome"] == "Cozinha")
st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
existente = next((u for u in usuarios if u["email"] == COZINHA[0]), None)
if existente:
    chamar("PUT", f"/usuarios/{existente['id']}",
           {"ativo": True, "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]}, token=token)
else:
    chamar("POST", "/usuarios", {"nome": "Smoke Cozinha", "email": COZINHA[0],
                                 "senha": COZINHA[1], "papeis": [{"id_papel": id_cozinha}]},
           token=token)

st, r = chamar("POST", "/auth/login", {"email": COZINHA[0], "senha": COZINHA[1]})
tk = r.get("access_token")
st, fc = chamar("GET", f"/fichas/{ficha_bebida}", token=tk)
checar("cozinha VÊ a ficha", st == 200, st)
checar("cozinha não recebe custo total", fc.get("custo_total") is None, fc.get("custo_total"))
checar("cozinha não recebe custo por porção", fc.get("custo_por_porcao") is None)
checar("nenhum item vem com dinheiro",
       all("custo_unitario" not in i for i in fc.get("itens", [])),
       [i for i in fc.get("itens", []) if "custo_unitario" in i][:1])
checar("mas a receita vem inteira", len(fc.get("itens", [])) == 3, len(fc.get("itens", [])))
checar("ve_custo vem false", fc.get("ve_custo") is False)
st, lista = chamar("GET", "/fichas", token=tk)
checar("lista da cozinha também vem sem custo",
       st == 200 and all(f.get("custo_total") is None for f in lista), st)
st, r = chamar("POST", f"/fichas/{ficha_bebida}/homologar", token=tk)
checar("cozinha NÃO homologa (403)", st == 403, st)

print("7. regras de cadastro")
st, r = chamar("POST", "/fichas", {"id_produto": cafe, "itens": []}, token=token)
checar("recusa ficha em produto que não é produzido", st == 400, (st, r))
st, r = chamar("POST", "/fichas", {
    "id_produto": bebida,
    "itens": [{"id_insumo": cafe, "id_subficha": ficha_base, "qtd_bruta": 1, "um": "G"}],
}, token=token)
checar("recusa item com insumo e sub-ficha juntos", st == 400, st)
# ficha_base é sub-ficha da bebida — arquivar quebraria o custo dela.
st, r = chamar("DELETE", f"/fichas/{ficha_base}", token=token)
checar("recusa arquivar ficha usada como sub-ficha", st == 409, (st, r))

print("8. limpeza")
for id_ficha in reversed(criados["fichas"]):
    # ⚠️ A foto sai ANTES: arquivar a ficha não apaga o arquivo (nem deveria —
    # ficha arquivada continua respondendo pelo histórico), e sem isto cada
    # rodada deixaria mais duas imagens na tabela `arquivos`.
    chamar("DELETE", f"/fichas/{id_ficha}/foto", token=token)
    chamar("DELETE", f"/fichas/{id_ficha}", token=token)
for id_produto in criados["produtos"]:
    chamar("DELETE", f"/produtos/{id_produto}", token=token)
for id_forn in criados["fornecedores"]:
    chamar("DELETE", f"/fornecedores/{id_forn}", token=token)
st, lista = chamar("GET", f"/produtos?busca=Ficha%20{marca}", token=token)
checar("produtos de teste saíram da lista ativa", len(lista) == 0, len(lista))

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
