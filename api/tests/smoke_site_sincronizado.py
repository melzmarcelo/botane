"""O site do cliente existe em DOIS lugares, e eles têm de ser o MESMO arquivo.

🔑 **Desde 15/10/2026** (pedido do dono: "o site e o cardápio pareciam dois sistemas"):
  * `site/index.html` é a FONTE — é a pasta publicada em `reservas.botanedeliecafe.com.br`;
  * `web/public/portal/index.html` é a cópia que o app do sistema serve em `/portal`, para o
    feed do Cardápio Vivo voltar ao site e levar a encomenda do catering no MESMO endereço
    (o carrinho mora no `sessionStorage` da aba, que é por domínio).
⚠️ Duas cópias divergem caladas: uma correção no site que não chegasse à outra faria o
cliente ver um site diferente conforme chegasse pelo feed ou pelo link. Esta suíte, que roda
na bateria (e o `promover.ps1` exige a bateria verde), recusa qualquer diferença.
Para sincronizar: `cp site/index.html web/public/portal/index.html`.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FONTE = RAIZ / "site" / "index.html"
COPIA = RAIZ / "web" / "public" / "portal" / "index.html"

ok, falhas = 0, []


def checar(nome: str, cond: bool, detalhe="") -> None:
    global ok
    if cond:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHA {nome} {detalhe}")


def texto(p: Path) -> str:
    # ⚠️ Compara o TEXTO, não os bytes: o git troca LF por CRLF no Windows conforme a pasta,
    # e isso não é diferença de conteúdo.
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


print("1. o site e a cópia do /portal")
checar("os dois arquivos existem", FONTE.exists() and COPIA.exists(), (FONTE, COPIA))
if FONTE.exists() and COPIA.exists():
    a, b = texto(FONTE), texto(COPIA)
    primeira = next((n for n, (x, y) in enumerate(zip(a.splitlines(), b.splitlines()), 1) if x != y), None)
    checar("e são o MESMO arquivo (cp site/index.html web/public/portal/index.html)", a == b,
           f"primeira linha diferente: {primeira}" if primeira else "tamanhos diferentes")

print()
print(f"{ok} passaram, {len(falhas)} falharam")
for x in falhas:
    print("  -", x)
sys.exit(1 if falhas else 0)
