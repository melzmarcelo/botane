"""O Open Food Facts como fonte de SUGESTÃO para o cadastro do produto.

🔑 **Pedido do dono (08/09/2026):** aproveitar o código de barras que o produto
já tem para preencher o que falta no cadastro. Medido na base real: 1.162 dos
3.071 produtos têm código de barras, e o OFF conhece **cerca de 30%** deles —
umas 350 fichas que hoje estão pela metade.

⚠️ **SUGERE, nunca escreve.** Quem aplica é a pessoa, campo a campo, olhando o
produto. É a mesma regra do "Vincular" ao lado: não existe detector honesto, e
quem reconhece está na tela. A razão está logo abaixo.

⚠️ **A armadilha que a sonda encontrou, e que sozinha justifica esta regra:**
o produto `CAIXA 30X30X14 1KG BR`, de código `0000000027083`, casa no OFF com
"Made Without Wheat Blueberry Muffins", da Marks & Spencer. Uma caixa de papelão
viraria muffin de mirtilo. O código não é EAN: é código interno preenchido com
zeros que, por acaso, bate com um registro real de lá. Aplicado sozinho, este
recurso RENOMEARIA produto — por isso `codigo_utilizavel` recusa antes de
perguntar, e por isso nada aqui grava.

⚠️ **A quantidade do OFF é texto livre e vem errada.** `AGUA MIN CRYSTAL 1 5L`
voltou como `1`, não 1,5 L. Ela é oferecida como informação, e de propósito NÃO
entra na lista de campos aplicáveis: fator de conversão errado contamina o custo
de tudo que usa o insumo.

⚠️ **O teto real de chamadas é muito menor que os 100/min documentados.** Com
0,7 s entre pedidos o OFF devolveu 429 em metade de uma amostra de 60. Aqui é
uma consulta por clique, então não há fila — mas o 429 é tratado como o que é
("pergunte de novo mais devagar") e vira uma mensagem, não um erro cru.
"""

import json
import urllib.error
import urllib.request

# ⚠️ O endereço tem `world` e `api/v2`. Sem eles a chamada não existe — foi o
# primeiro tropeço ao experimentar.
API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

# ⚠️ **User-Agent identificado.** O OFF é gratuito e mantido por doação; pedir
# sem se identificar é o que faz projetos serem bloqueados.
UA = "Botane/1.1 (ERP de restaurante; enriquecimento de cadastro por EAN)"

# Só o que teria serventia aqui. O OFF devolve 129 campos; pedir seis deixa a
# resposta pequena e a intenção explícita para quem ler depois.
CAMPOS = "product_name,product_name_pt,brands,quantity,categories_tags,image_url"

TEMPO_LIMITE = 12


def digito_verificador_ok(codigo: str) -> bool:
    """O último dígito confere com os anteriores (GTIN-8/12/13/14).

    🔑 É o que separa um código de barras de verdade de uma sequência qualquer,
    e custa uma multiplicação. Sem ele, código interno de 13 dígitos passa por
    EAN e vai perguntar ao OFF.
    """
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False
    *corpo, verificador = [int(c) for c in codigo]
    # Da direita para a esquerda, alternando peso 3 e 1.
    soma = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == verificador


def codigo_utilizavel(codigo: str | None) -> tuple[bool, str]:
    """Este código pode ser perguntado ao OFF? E, se não, por quê.

    ⚠️ **A recusa vem ANTES da chamada**, e a frase explica — "não achamos" e
    "isto não é um código global" são coisas diferentes, e a segunda é sobre o
    cadastro daqui, não sobre o OFF.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return False, "Este produto não tem código de barras cadastrado."
    if not codigo.isdigit():
        return False, "O código de barras tem letras — não é um EAN."
    if len(codigo) not in (8, 12, 13, 14):
        return False, (f"Um EAN tem 8, 12, 13 ou 14 dígitos; este tem {len(codigo)}.")
    # ⚠️ **Prefixo 2 é faixa de USO INTERNO** (loja, peso variável): não
    # identifica produto no mundo, e o que o OFF devolver para ele é outro
    # produto qualquer que ocupou o mesmo número.
    if codigo.startswith("2"):
        return False, ("Código da faixa 2 é de uso interno da loja (peso variável) "
                       "e não identifica o produto fora daqui.")
    # ⚠️ Zeros à esquerda em série são código interno preenchido à mão. Foi
    # assim que a caixa de papelão virou muffin de mirtilo.
    if codigo.startswith("0000"):
        return False, ("Código preenchido com zeros é interno da casa — no OFF ele "
                       "casa com outro produto qualquer.")
    if not digito_verificador_ok(codigo):
        return False, "O dígito verificador não confere: o código está errado ou é interno."
    return True, ""


def consultar(codigo: str) -> dict:
    """O que o OFF sabe deste código.

    Devolve `{"achou": bool, "erro": str|None, "sugestoes": {...}, "extras": {...}}`.
    Nunca levanta: falha de rede aqui não pode derrubar a tela do produto, que
    funciona perfeitamente sem esta consulta.
    """
    pode, motivo = codigo_utilizavel(codigo)
    if not pode:
        return {"achou": False, "erro": motivo, "sugestoes": {}, "extras": {}}

    req = urllib.request.Request(
        API.format(codigo) + f"?fields={CAMPOS}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as r:
            corpo = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"achou": False, "erro": None, "sugestoes": {}, "extras": {}}
        if e.code == 429:
            return {"achou": False, "sugestoes": {}, "extras": {},
                    "erro": "O Open Food Facts pediu para esperar. Tente de novo em instantes."}
        return {"achou": False, "sugestoes": {}, "extras": {},
                "erro": f"O Open Food Facts respondeu {e.code}."}
    except Exception:
        return {"achou": False, "sugestoes": {}, "extras": {},
                "erro": "Não foi possível falar com o Open Food Facts agora."}

    if corpo.get("status") != 1 or not corpo.get("product"):
        return {"achou": False, "erro": None, "sugestoes": {}, "extras": {}}

    p = corpo["product"]
    # 🔑 **Português primeiro.** O OFF guarda o nome em vários idiomas, e o
    # `product_name` genérico costuma vir em inglês num produto brasileiro.
    nome = (p.get("product_name_pt") or p.get("product_name") or "").strip()
    marca = (p.get("brands") or "").strip()

    # ⚠️ **Só o que se APLICA entra em `sugestoes`.** `quantity` e a categoria do
    # OFF ficam em `extras`: servem para a pessoa reconhecer o produto, não para
    # virar campo. Categoria do OFF é a taxonomia deles ("en:whole-milk"), que
    # não é a tabela de categorias desta casa.
    sugestoes = {}
    if nome:
        # ⚠️ **MAIÚSCULAS, que é a convenção da casa** — os 3.071 produtos da
        # base estão assim. O OFF devolve "Leite UHT Integral"; aceitá-lo como
        # veio deixaria uma linha em caixa mista no meio da lista, e quem
        # ordenasse por nome veria a diferença antes de ver o produto.
        sugestoes["nome"] = nome.upper()
    if marca:
        sugestoes["marca"] = marca.upper()

    extras = {}
    if p.get("quantity"):
        extras["quantidade"] = p["quantity"]
    if p.get("image_url"):
        extras["imagem"] = p["image_url"]
    if p.get("categories_tags"):
        extras["categoria_off"] = p["categories_tags"][-1]

    return {"achou": True, "erro": None, "sugestoes": sugestoes, "extras": extras}
