"""Os preços daqui que não batem com a tabela do PDV.

Pedido do dono (08/10/2026): *"podemos ajustar a precificação no Botané, mas ele
não está enviando nada para o PDV … posso emitir um relatório com as diferenças
para que assim que possível estes sejam ajustados no PDV"*.

⚠️ **A comparação é exercitada com um PDV de MENTIRA, montado aqui.** O relatório
de verdade pergunta a tabela ao PDV da loja, e a base local pode estar com
credencial real, simulada ou nenhuma — afirmar sobre o que ele devolve seria
testar a configuração da máquina, não a regra. A rota do catálogo é conferida
só no que não depende disso.

    python tests/smoke_precos_pdv.py            (API de pé na 9200)
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "tests")
sys.path.insert(0, ".")
from database import get_cursor  # noqa: E402
from services.pdv import envio  # noqa: E402

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
        with urllib.request.urlopen(req, dados, timeout=90) as r:
            bruto = r.read()
            try:
                return r.status, json.loads(bruto or b"null")
            except json.JSONDecodeError:
                # O relatório responde um ARQUIVO, não JSON.
                return r.status, bruto.decode("utf-8", errors="replace")
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


class PdvDeMentira:
    """Só o que a comparação usa: a tabela de preços de uma filial."""

    modo = "real"

    def __init__(self, tabela):
        self.tabela = tabela
        self.pedidos: list[str] = []

    def get(self, caminho):
        self.pedidos.append(caminho)
        return self.tabela


st, r = chamar("POST", "/auth/login", {"email": ADMIN[0], "senha": ADMIN[1]})
assert st == 200, r
token = r["access_token"]
st, eu = chamar("GET", "/auth/me", token=token)
id_unidade = (eu or {}).get("id_unidade") or 1

marca = str(time.time_ns() // 100)[-6:]
criados: list[int] = []


def produto(sufixo: str, preco: float | None, codigo_pdv: str | None) -> int:
    st, r = chamar("POST", "/produtos", {
        "codigo": f"PP{sufixo}-{marca}", "nome": f"Preco pdv {sufixo} {marca}",
        "tipo": "REVENDA", "um_estoque": "UN", "controla_estoque": False,
        "status": "ATIVO", "preco_venda": preco, "codigo_pdv": codigo_pdv,
    }, token=token)
    assert st == 201, (st, r)
    criados.append(r["id"])
    return r["id"]


print("1. quatro produtos, quatro situações")
# Os códigos levam a marca da rodada: nada aqui pode casar com o cardápio real.
subiu = produto("A", 12.90, f"9{marca}1")      # aqui 12,90 · lá 10,00
igual = produto("B", 8.00, f"9{marca}2")       # igual dos dois lados
sem_la = produto("C", 5.00, f"9{marca}3")      # sem linha na tabela de lá
baixou = produto("D", 7.50, f"9{marca}4")      # aqui 7,50 · lá 9,00
produto("E", 30.00, None)                      # sem código do PDV: não participa

pdv = PdvDeMentira([
    {"codProduto": int(f"9{marca}1"), "valor": 10.0},
    # ⚠️ 8.0000000001: em `float`, "diferente" — em centavos, igual. É a doença
    # que faria todo produto parecer eternamente pendente.
    {"codProduto": int(f"9{marca}2"), "valor": 8.0000000001},
    {"codProduto": int(f"9{marca}4"), "valor": 9.0},
])

print("\n2. a comparação")
with get_cursor() as cur:
    r = envio.diferencas_de_preco(cur, id_unidade, pdv, 37622)
checar("pergunta a tabela da filial certa", pdv.pedidos == ["/tabelapreco/get/37622"],
       pdv.pedidos)
desta = {l["id_produto"]: l for l in r["linhas"] if l["id_produto"] in criados}
checar("o que subiu aqui entra na lista", subiu in desta, sorted(desta))
checar("com os dois preços lado a lado",
       desta.get(subiu, {}).get("preco_botane") == 12.9
       and desta.get(subiu, {}).get("preco_pdv") == 10.0, desta.get(subiu))
checar("e a diferença com sinal: +2,90 a subir no PDV",
       desta.get(subiu, {}).get("diferenca") == 2.9, desta.get(subiu))
checar("o que baixou aqui também entra, negativo",
       desta.get(baixou, {}).get("diferenca") == -1.5, desta.get(baixou))
checar("o código que vai na linha é o do PDV",
       desta.get(subiu, {}).get("codigo_pdv") == f"9{marca}1", desta.get(subiu))
checar("preço igual não entra, nem com a poeira do float", igual not in desta, desta.get(igual))
checar("sem linha na tabela de lá não é divergência", sem_la not in desta, desta.get(sem_la))
checar("mas é CONTADO, para a lista vazia não parecer 'tudo igual'",
       r["sem_preco_no_pdv"] >= 1, r["sem_preco_no_pdv"])
checar("só os que estão nesta lista de exemplo", len(desta) == 2, sorted(desta))

print("\n3. sem filial, não se compara com a loja errada")
try:
    with get_cursor() as cur:
        envio.diferencas_de_preco(cur, id_unidade, pdv, None)
    recusou = None
except Exception as e:  # noqa: BLE001 — a recusa é o que se mede
    recusou = e
checar("sem UMA filial configurada é recusa com frase",
       getattr(recusou, "status_code", None) == 409
       and "filial" in str(getattr(recusou, "detail", "")), recusou)

print("\n4. o relatório está no catálogo, com a permissão da precificação")
st, catalogo = chamar("GET", "/exportar/catalogo", token=token)
rel = next((c for c in catalogo or [] if c.get("chave") == "precos-pdv"), None)
checar("o catálogo oferece 'Preços a acertar no PDV'",
       rel is not None and rel.get("rotulo") == "Preços a acertar no PDV", rel)
st, r = chamar("GET", "/exportar/precos-pdv.csv", token=token)
# ⚠️ O que o PDV desta máquina devolve não é assunto desta suíte: ou o arquivo
# sai (200), ou a recusa explica o que falta (409 sem filial, 502 sem PDV).
checar("a rota responde o arquivo ou a recusa com frase, nunca 500",
       st in (200, 409, 502), (st, r))

for id_produto in reversed(criados):
    chamar("DELETE", f"/produtos/{id_produto}", token=token)

print(f"\n{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print(f"  - {x}")
sys.exit(1 if falhas else 0)
