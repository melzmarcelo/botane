"""Leva o saldo do local PADRÃO para o local do produto — com prévia obrigatória.

    python esvaziar_local_padrao.py                      # só a prévia (não grava nada)
    python esvaziar_local_padrao.py --executar           # pergunta e executa
    python esvaziar_local_padrao.py https://outro.dominio --executar

🔑 **Por que existe** (pedido do dono, 05/10/2026): na casa, muitos produtos
ficaram com saldo — positivo e negativo — no local padrão da loja ("GERAL SEM
CATEGORIA (ESTOQUE ENTRADA)") mesmo já tendo a prateleira deles. O mesmo
produto aparece em dois lugares, e o saldo de verdade é a soma que ninguém vê.
Roda UMA vez; rodar de novo não acha mais nada a fazer.

O que ele faz, produto a produto, na loja de quem entra:

    está no local padrão E em outro local?
        saldo POSITIVO no padrão  -> transfere do padrão para o local do produto
        saldo NEGATIVO no padrão  -> transfere do local do produto para o padrão
                                     (zera o padrão; a dívida passa para o local)
        saldo ZERO no padrão      -> nada a mover
    e então tira o produto do local padrão.

🔑 **Para ONDE vai:** se o produto está em UM outro local, é para lá. Se está em
vários, vai para o "local padrão do produto" do cadastro — desde que seja um
deles. Sem isso o script NÃO adivinha: o produto fica como está e sai numa lista
à parte.

⚠️ **Fala com a API, nunca com o banco.** A transferência é a mesma da tela:
dois movimentos no razão (saída e entrada, pelo mesmo custo), com auditoria,
período fechado e permissão conferidos pelo servidor. Um UPDATE direto no saldo
faria o estoque mudar de lugar sem movimento explicando — e o razão é a única
memória do custo.

⚠️ **Não mexe no valor do estoque nem no CMV.** Transferência entre locais da
mesma loja sai e entra pelo mesmo custo. O que muda é o relatório por SETOR e
por LOCAL, que passa a ver a mercadoria onde ela está.

⚠️ **Não mexe no cadastro.** Se o "local padrão do produto" for o próprio local
de entrada, a próxima nota lançada põe o produto lá de novo — é o desenho da
casa (entra no estoque de entrada, depois vai para o setor).

⚠️ **Não desfaz barato.** O razão é append-only: voltar atrás é uma
transferência no sentido contrário por produto. É para isso que a prévia existe.

⚠️ **Só produto ATIVO.** O arquivado com saldo fica como está.
"""

import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PADRAO = "https://sistema.botanedeliecafe.com.br"

# ⚠️ O console do Windows não é UTF-8: sem isto o script morre no primeiro
# acento, no meio da execução. Mesma nota de `unificar_custo_producao.py`.
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

_PREFIXO = {"valor": None}


def _descobrir_prefixo(base) -> str:
    """No ar a API mora sob `/api`; em casa ela é uma porta própria."""
    if _PREFIXO["valor"] is None:
        for tentativa in ("/api", ""):
            try:
                with urllib.request.urlopen(base.rstrip("/") + tentativa + "/saude",
                                            timeout=30) as r:
                    if r.status == 200:
                        _PREFIXO["valor"] = tentativa
                        break
            except Exception:
                continue
        else:
            _PREFIXO["valor"] = "/api"
    return _PREFIXO["valor"]


def chamar(base, metodo, caminho, corpo=None, token=None, tempo=180):
    url = (base.rstrip("/") + _descobrir_prefixo(base)
           + urllib.parse.quote(caminho, safe="/?=&"))
    req = urllib.request.Request(url, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    try:
        with urllib.request.urlopen(req, dados, timeout=tempo) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except json.JSONDecodeError:
            return e.code, {"detail": bruto.decode(errors="replace")}
    except urllib.error.URLError as e:
        return 0, {"detail": str(e.reason)}


def reais(v) -> str:
    return f"R$ {float(v):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def numero(v) -> str:
    return f"{float(v):,.4f}".rstrip("0").rstrip(".").replace(",", "@").replace(".", ",") \
        .replace("@", ".")


def todos_os_saldos(base, token) -> list[dict] | None:
    """Todas as linhas de saldo da loja, de produto ativo, página a página."""
    linhas, offset, pagina = [], 0, 1000
    while True:
        st, parte = chamar(base, "GET", f"/estoque/saldos?limite={pagina}&offset={offset}",
                           token=token)
        if st != 200:
            print(f"  a leitura dos saldos falhou ({st}): {parte.get('detail')}")
            return None
        linhas += parte
        if len(parte) < pagina:
            return linhas
        offset += pagina


def planejar(base, token, padrao: dict, saldos: list[dict]) -> tuple[list[dict], list[dict]]:
    """O que fazer com cada produto que está no local padrão e em outro local.

    Devolve (plano, sem_destino). ⚠️ Decide o destino AQUI, uma vez: a execução
    segue exatamente o que a prévia mostrou.
    """
    por_produto: dict[int, list[dict]] = {}
    for s in saldos:
        por_produto.setdefault(s["id_produto"], []).append(s)

    plano, sem_destino = [], []
    for id_produto, linhas in por_produto.items():
        no_padrao = next((l for l in linhas if l["id_local"] == padrao["id"]), None)
        outros = [l for l in linhas if l["id_local"] != padrao["id"]]
        if not no_padrao or not outros:
            continue
        item = {
            "id_produto": id_produto, "codigo": no_padrao.get("codigo"),
            "produto": no_padrao.get("produto"), "um": no_padrao.get("um_estoque"),
            "quantidade": float(no_padrao["quantidade"]),
            "valor": float(no_padrao.get("valor") or 0),
        }
        if len(outros) == 1:
            destino = outros[0]
        else:
            # Vários locais: só o cadastro sabe qual é "o" do produto.
            st, p = chamar(base, "GET", f"/produtos/{id_produto}", token=token)
            preferido = (p or {}).get("id_local_padrao") if st == 200 else None
            destino = next((l for l in outros if l["id_local"] == preferido), None)
            if not destino:
                sem_destino.append(item | {"locais": [l["local"] for l in outros]})
                continue
        plano.append(item | {"id_destino": destino["id_local"], "destino": destino["local"]})
    plano.sort(key=lambda i: (i["destino"] or "", i["produto"] or ""))
    return plano, sem_destino


def mostrar(plano: list[dict], sem_destino: list[dict], padrao: dict) -> None:
    positivos = [i for i in plano if i["quantidade"] > 0]
    negativos = [i for i in plano if i["quantidade"] < 0]
    zerados = [i for i in plano if i["quantidade"] == 0]
    print()
    print(f"  local padrão desta loja              : {padrao['nome']}")
    print(f"  produtos no padrão E em outro local  : {len(plano) + len(sem_destino)}")
    print(f"    saldo POSITIVO a levar ao local    : {len(positivos)} "
          f"({reais(sum(i['valor'] for i in positivos))})")
    print(f"    saldo NEGATIVO a levar ao local    : {len(negativos)} "
          f"({reais(sum(i['valor'] for i in negativos))})")
    print(f"    saldo ZERO (só tirar do padrão)    : {len(zerados)}")
    print(f"    SEM destino claro (ficam como estão): {len(sem_destino)}")

    if plano:
        print("\n  o que será feito:")
        for i in plano:
            if i["quantidade"] > 0:
                gesto = f"{numero(i['quantidade'])} {i['um'] or ''} -> {i['destino']}"
            elif i["quantidade"] < 0:
                gesto = f"{numero(i['quantidade'])} {i['um'] or ''} (negativo) -> {i['destino']}"
            else:
                gesto = f"só tirar do padrão (fica em {i['destino']})"
            print(f"    {(i['codigo'] or '')[:14]:15} {(i['produto'] or '')[:38]:40} {gesto}")
    if sem_destino:
        print("\n  SEM destino claro — está em vários locais e o cadastro não aponta um deles:")
        for i in sem_destino:
            print(f"    {(i['codigo'] or '')[:14]:15} {(i['produto'] or '')[:38]:40} "
                  f"{numero(i['quantidade'])} {i['um'] or ''} · em: {', '.join(i['locais'])}")


def executar_plano(base, token, plano: list[dict], padrao: dict) -> tuple[int, list[str]]:
    feitos, falhas = 0, []
    for n, i in enumerate(plano, 1):
        rotulo = f"{i['codigo'] or i['id_produto']} {i['produto']}"
        if i["quantidade"] != 0:
            # Positivo: sai do padrão. Negativo: o local do produto cobre a
            # dívida do padrão — a mesma transferência, no sentido contrário.
            origem, destino = ((padrao["id"], i["id_destino"]) if i["quantidade"] > 0
                               else (i["id_destino"], padrao["id"]))
            st, r = chamar(base, "POST", "/estoque/transferencias", {
                "id_produto": i["id_produto"], "quantidade": abs(i["quantidade"]),
                "id_local_origem": origem, "id_local_destino": destino,
                "observacao": "Saldo do local padrão levado ao local do produto",
            }, token=token)
            if st != 201:
                falhas.append(f"{rotulo}: transferência recusada ({st}) — {r.get('detail')}")
                continue
        st, r = chamar(base, "DELETE", f"/produtos/{i['id_produto']}/locais/{padrao['id']}",
                       token=token)
        if st != 200:
            # ⚠️ O saldo JÁ foi movido; só a linha zerada ficou. Rodar de novo
            # tira — não há o que desfazer.
            falhas.append(f"{rotulo}: saldo movido, mas não saiu do padrão ({st}) — "
                          f"{r.get('detail')}")
            continue
        feitos += 1
        if n % 25 == 0:
            print(f"    … {n} de {len(plano)}")
    return feitos, falhas


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    executar = "--executar" in sys.argv
    base = argumentos[0] if argumentos else PADRAO

    print(f"Saldo do local padrão -> local do produto\n  alvo: {base}")
    st, saude = chamar(base, "GET", "/saude", tempo=30)
    if st != 200:
        print(f"  a API não respondeu ({st}): {saude}")
        return 1
    print(f"  versão {saude.get('versao')} · migração {saude.get('migracao')}")

    email = input("  e-mail: ").strip()
    # ⚠️ `getpass` lê do TERMINAL: num cano ele trava e o script parece morto.
    if sys.stdin.isatty():
        senha = getpass.getpass("  senha: ")
    else:
        print("  AVISO: entrada nao interativa — a senha sera lida em texto comum.")
        senha = sys.stdin.readline().strip()
    st, r = chamar(base, "POST", "/auth/login", {"email": email, "senha": senha})
    if st != 200:
        print(f"  login recusado ({st}): {r.get('detail')}")
        return 1
    token = r["access_token"]

    st, locais = chamar(base, "GET", "/locais", token=token)
    if st != 200:
        print(f"  a leitura dos locais falhou ({st}): {locais.get('detail')}")
        return 1
    principais = [l for l in locais if l.get("principal") and l.get("ativo", True)]
    if len(principais) != 1:
        print(f"  ERRO: esperava UM local padrão nesta loja e achei {len(principais)}.")
        return 1
    padrao = principais[0]

    saldos = todos_os_saldos(base, token)
    if saldos is None:
        return 1
    plano, sem_destino = planejar(base, token, padrao, saldos)
    mostrar(plano, sem_destino, padrao)

    if not plano:
        print("\n  Nada a fazer: nenhum produto está no local padrão e em outro local.")
        return 0
    if not executar:
        print("\n  (só a prévia — nada foi gravado. Rode com --executar para lançar.)")
        return 0

    print(f"\n  ⚠️  Cada produto com saldo vira uma transferência no razão (dois movimentos).")
    print("      O razão não se apaga: desfazer é transferir de volta, produto a produto.")
    if input('      Digite "executar" para confirmar: ').strip().lower() != "executar":
        print("      cancelado — nada foi gravado.")
        return 0

    feitos, falhas = executar_plano(base, token, plano, padrao)
    print(f"\n  {feitos} produto(s) levados ao local deles e tirados de {padrao['nome']}.")
    if falhas:
        print(f"  {len(falhas)} não concluído(s):")
        for f in falhas:
            print("    -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
