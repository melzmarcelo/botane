"""Unifica o custo médio das prateleiras NO AR — com prévia obrigatória.

    python unificar_custo_producao.py                      # só a prévia (não grava nada)
    python unificar_custo_producao.py --unificar           # pergunta e executa
    python unificar_custo_producao.py https://outro.dominio --unificar

🔑 **Por que existe** (pedido do dono, 11/09/2026): a migração 064 fez o custo
médio ser da loja, mas ela NÃO reavalia o que já está em estoque — isso é
lançamento, não conserto de dado. A tela tem o botão; este script é o mesmo
botão para quem prefere a linha de comando, e é o que dá para rodar com o
relatório inteiro à vista antes de decidir.

⚠️ **Fala com a API, nunca com o banco.** Todas as travas moram no servidor: a
permissão `estoque.custo`, a recusa em período fechado, o lote de ajuste, o
movimento no razão e a auditoria. Um script que escrevesse direto no Postgres
teria de reimplementar as cinco — e a primeira que ficasse de fora só apareceria
meses depois, como um número que não fecha.

⚠️ **A prévia é o padrão e não grava nada.** Sem `--unificar` este arquivo é tão
seguro quanto `verificar_deploy.py`: ele pergunta e não responde.

⚠️ **Reavaliar mexe no CMV do período corrente** — estoque mais caro deixa o CMV
menor, e o painel mostra isso na linha "ajuste de custo". Por isso a confirmação
é digitada por extenso, e não um "s/n" que se aperta sem ler.

⚠️ **Não desfaz barato.** O razão é append-only: voltar atrás é estornar um
movimento por prateleira. É para isso que a prévia existe.
"""

import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PADRAO = "https://sistema.botanedeliecafe.com.br"

# ⚠️ **O console do Windows não é UTF-8, e isso DERRUBAVA o script.** Ele morria
# com `UnicodeEncodeError` ao imprimir o primeiro acento — no meio de uma
# unificação, depois do login, o que é o pior lugar possível. `errors="replace"`
# troca o que o console não sabe desenhar por `?` e segue; nenhum aviso se perde
# por causa de um caractere.
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


# ⚠️ **No ar a API mora sob `/api`; em casa ela é uma porta própria.** Descoberto
# uma vez, no `/saude`, em vez de virar um parâmetro que alguém esquece de passar
# — e o erro apareceria como um 404 seco no meio da unificação.
_PREFIXO = {"valor": None}


def _descobrir_prefixo(base) -> str:
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


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    executar = "--unificar" in sys.argv
    base = argumentos[0] if argumentos else PADRAO

    print(f"Botané — unificação do custo médio por loja\n  alvo: {base}")
    st, saude = chamar(base, "GET", "/saude", tempo=30)
    if st != 200:
        print(f"  a API não respondeu ({st}): {saude}")
        return 1
    print(f"  versão {saude.get('versao')} · migração {saude.get('migracao')}")
    # ⚠️ A rota só existe a partir da 064. Sem esta conferência o erro apareceria
    # como um 404 seco, que qualquer pessoa leria como "o script está quebrado".
    if (saude.get("migracao") or "") < "064":
        print("  ERRO: este ambiente ainda nao tem a migracao 064 — promova antes.")
        return 1

    email = input("  e-mail: ").strip()
    # ⚠️ `getpass` lê do TERMINAL, não da entrada padrão: num cano ele trava, e
    # o script parece morto. Fora do terminal a senha é lida como texto comum —
    # e o aviso é obrigatório, porque aí ela FICA no histórico de quem chamou.
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

    st, p = chamar(base, "GET", "/ajustes/custo-geral/previa", token=token)
    if st != 200:
        print(f"  a prévia falhou ({st}): {p.get('detail')}")
        return 1

    print()
    print(f"  produtos com prateleiras discordando : {p['produtos']}")
    print(f"  prateleiras a REAVALIAR (têm saldo)  : {p['prateleiras_reavaliadas']}")
    print(f"  prateleiras só a preencher (saldo 0) : {p['prateleiras_so_preenchidas']}")
    print(f"  efeito no ESTOQUE                    : {reais(p['efeito_no_estoque'])}")
    # O sinal do CMV é o inverso: estoque mais caro, CMV menor.
    efeito = float(p["efeito_no_estoque"])
    print(f"  … o que {'REDUZ' if efeito >= 0 else 'AUMENTA'} o CMV do período em "
          f"{reais(abs(efeito))}")

    if p["produtos"]:
        print("\n  as primeiras linhas:")
        for l in p["linhas"][:15]:
            marca = "—" if l["quantidade"] == 0 else reais(l["diferenca"])
            print(f"    {(l['produto'] or '')[:30]:32} {(l['local'] or '')[:14]:16} "
                  f"qtd={l['quantidade']:>10} {l['custo_medio']:>10} -> "
                  f"{l['custo_novo']:<10} {marca}")
        if len(p["linhas"]) > 15:
            print(f"    … e mais {len(p['linhas']) - 15} linha(s)")

    if not p["produtos"]:
        print("\n  Nada a unificar: todas as prateleiras já estão com o mesmo custo.")
        return 0

    if not executar:
        print("\n  (só a prévia — nada foi gravado. Rode com --unificar para lançar.)")
        return 0

    print("\n  ⚠️  Cada prateleira com saldo vira um lançamento de ajuste de custo no")
    print("      custo no razao, num lote so. O razao nao se apaga: desfazer e")
    print("      estornar um movimento por prateleira.")
    if input('      Digite "unificar" para confirmar: ').strip().lower() != "unificar":
        print("      cancelado — nada foi gravado.")
        return 0

    st, feito = chamar(base, "POST", "/ajustes/custo-geral", {}, token=token, tempo=600)
    if st != 201:
        print(f"  falhou ({st}): {feito.get('detail')}")
        return 1
    print(f"\n  {feito['message']}")
    print(f"  lote {feito['id_lote']} · efeito no estoque {reais(feito['efeito_no_estoque'])}")
    print("  confira em Estoque → Ajuste de custo → Últimos ajustes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
