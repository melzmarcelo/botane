"""Sonda: quanto do catálogo da casa o Open Food Facts conhece?

    python sonda_openfoodfacts.py            60 produtos ao acaso
    python sonda_openfoodfacts.py 150        outra amostra

Só LÊ — não escreve nada no banco e não altera produto nenhum. Existe para
responder uma pergunta antes de qualquer código de verdade: **vale a pena?**

🔑 **A taxa de acerto é o que decide.** Enriquecer produto por código de barras
só se paga se o OFF conhecer uma fatia relevante do que a casa compra. O
catálogo daqui é de food service — caixa com 21 unidades, saco de lixo, grampo
de grampeador — e o OFF é um cadastro de produto de PRATELEIRA, alimentado por
consumidor com o celular. A sonda mede em vez de supor.

⚠️ **User-Agent identificado, e uma pausa entre chamadas.** O OFF é gratuito e
mantido por doação; pedir sem se identificar e sem ritmo é o que faz projetos
serem bloqueados.

⚠️ **O limite real é MUITO menor que os 100/min documentados.** Com 0,7 s entre
as chamadas (~85/min) o OFF devolveu **429 em metade da amostra** — e a primeira
versão desta sonda contou cada 429 como "erro de rede", produzindo uma taxa de
acerto de 8% que não media nada. 429 não é resposta: é "pergunte de novo mais
devagar". Agora espera e repete, honrando o `Retry-After` quando ele vem.
"""

import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from database import get_cursor, init_pool  # noqa: E402

API = "https://world.openfoodfacts.org/api/v2/product/{}.json"
UA = "Botane/0.1 (sonda de viabilidade; contato via github.com/melzmarcelo/botane)"
PAUSA = 1.6

# Os campos que teriam serventia AQUI, e o porquê de cada um. O OFF devolve 129;
# pedir só estes deixa a resposta menor e a intenção explícita.
#   - nome e marca: conferir se o cadastro bate com o que o código diz ser
#   - quantidade: a embalagem, que é a origem do fator de conversão
#   - categoria: o palpite de categoria para produto novo
#   - imagem: a foto, que hoje ninguém tem
CAMPOS = "product_name,product_name_pt,brands,quantity,categories_tags,image_url"


def consultar(ean: str, tentativas: int = 4) -> dict | None:
    """O produto no OFF, ou None se ele não conhece este código.

    ⚠️ **429 não é falha, é ritmo.** Tratá-lo como erro foi o que fez a primeira
    medição dizer 8% de acerto sobre uma amostra em que metade nunca chegou a
    ser perguntada.
    """
    req = urllib.request.Request(
        API.format(ean) + f"?fields={CAMPOS}", headers={"User-Agent": UA})
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                corpo = json.loads(r.read().decode("utf-8"))
            return corpo.get("product") if corpo.get("status") == 1 else None
        except urllib.error.HTTPError as e:
            # 404 é resposta legítima: o OFF não conhece este código.
            if e.code == 404:
                return None
            if e.code == 429 and n < tentativas - 1:
                # O servidor diz quanto esperar; sem isso, recuo dobrado.
                espera = float(e.headers.get("Retry-After") or 0) or PAUSA * 2 ** (n + 1)
                time.sleep(espera)
                continue
            return {"erro": f"HTTP {e.code}"}
        except Exception as e:  # rede, timeout, JSON quebrado
            if n < tentativas - 1:
                time.sleep(PAUSA * 2 ** (n + 1))
                continue
            return {"erro": type(e).__name__}
    return {"erro": "esgotou as tentativas"}


def main() -> int:
    quantos = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    init_pool()
    with get_cursor() as cur:
        # ⚠️ Só o que TEM cara de EAN. Código interno ("S000006", "GUA002") não
        # é código de barras, e mandá-lo ao OFF só gastaria chamada.
        cur.execute(
            """SELECT codigo_barras, nome FROM produtos
                WHERE codigo_barras ~ '^[0-9]{8,14}$'
                ORDER BY random() LIMIT %s""",
            (quantos,),
        )
        amostra = [dict(r) for r in cur.fetchall()]

    print(f"Sonda Open Food Facts — {len(amostra)} produto(s) da casa\n")
    achados, erros = [], 0
    for i, p in enumerate(amostra, 1):
        r = consultar(p["codigo_barras"])
        if r and "erro" in r:
            erros += 1
            marca = "!"
        elif r:
            achados.append((p, r))
            marca = "+"
        else:
            marca = "."
        print(marca, end="", flush=True)
        if i % 50 == 0:
            print()
        time.sleep(PAUSA)

    total = len(amostra)
    print(f"\n\n{'=' * 62}")
    print(f"ACHOU {len(achados)} de {total}  ({100 * len(achados) / total:.0f}%)"
          f"   erros de rede: {erros}")
    print("=" * 62)

    if achados:
        print("\nO que o OFF sabe sobre eles (cadastro daqui -> OFF):\n")
        for p, r in achados[:15]:
            nome_off = r.get("product_name_pt") or r.get("product_name") or "—"
            print(f"  {p['codigo_barras']}")
            print(f"    aqui: {p['nome'][:62]}")
            print(f"     OFF: {nome_off[:62]}")
            extras = []
            if r.get("brands"):
                extras.append(f"marca={r['brands'][:22]}")
            if r.get("quantity"):
                extras.append(f"qtd={r['quantity'][:16]}")
            if r.get("image_url"):
                extras.append("tem foto")
            if r.get("categories_tags"):
                extras.append(f"cat={r['categories_tags'][-1][:24]}")
            if extras:
                print(f"          {' | '.join(extras)}")
            print()

    # 🔑 A conclusão em números, que é o que a decisão precisa.
    com_foto = sum(1 for _, r in achados if r.get("image_url"))
    com_qtd = sum(1 for _, r in achados if r.get("quantity"))
    com_marca = sum(1 for _, r in achados if r.get("brands"))
    print(f"Dos {len(achados)} achados: {com_marca} com marca, "
          f"{com_qtd} com quantidade, {com_foto} com foto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
