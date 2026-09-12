"""Trocar a unidade de estoque de um produto — e levar junto o que depende dela.

🔑 **O caso do dono (08/09/2026):** "o custo está em CX, mas alteramos para o
estoque em UN e a unidade de compra CX — deve fazer a alteração. E caso haja
alteração e não for possível fazer a conversão, apresentar uma mensagem de
validação."

⚠️ **A unidade de estoque não é um rótulo: é o denominador de tudo.** Saldo,
custo médio, custo de referência, mínimo, máximo e os fatores de embalagem são
todos *por unidade de estoque*. Trocar CX por UN sem mexer neles multiplica ou
divide por doze, calado, o custo de tudo que usa o insumo — e o erro só aparece
no CMV do mês, longe da causa.

⚠️ **Quem já tem RAZÃO não troca de unidade, e isso é recusa, não conversão.**
`estoque_movimentos` é append-only: as quantidades históricas estão gravadas na
unidade antiga e não há como reescrevê-las. Converter só o cadastro deixaria o
saldo dizendo "10" numa unidade e o histórico "10" noutra — a mesma prateleira
valendo dois números diferentes. O caminho honesto é a mensagem de validação.

⚠️ **A conversão usa o conversor central** (`custos.converter`,
`custos.fator_de_embalagem` e o par `um_compra`/`fator_compra`), nunca uma conta
escrita aqui. Duas implementações divergiriam, e a divergência seria entre o
cadastro e o razão.

🔑 **O segundo caso do dono (12/09/2026):** *"no estoque o produto está em KG e a
compra em PCT, às vezes dá uma mensagem que a conversão não aceita e não é
permitido salvar"*. A relação estava cadastrada — o pacote de 5 KG —, só que
lida numa direção só: a regra perguntava se a unidade de compra era a ANTIGA, e
ali ela era a NOVA. O sistema recusava por não saber algo que sabia.
⚠️ **E a frase da recusa mandava fazer o que não funcionava**: "cadastre a
embalagem do produto", sendo que `produto_unidades` não era consultado aqui.
Agora é — pelo mesmo `fator_de_embalagem` da nota e da ficha.
"""

from decimal import Decimal

from services.custos import converter, dec, fator_de_embalagem


def _br(v) -> str:
    """O número como esta casa escreve: vírgula, e sem zero à toa.

    ⚠️ **A frase vai para a TELA**, e era o único lugar do sistema que mostrava
    "0.2" a quem lê "0,2". O `:g` do Python resolve o zero sobrando e não sabe
    de vírgula nenhuma.
    ⚠️ **O `float` antes do `:g` não é descuido.** Em `Decimal` o `:g` respeita a
    escala guardada, e `fator_compra` vem do banco como `numeric(18,6)`: a frase
    saía "1 PCT = 1,000000 KG". Aqui é texto de tela, não conta — quem calcula
    continua em `Decimal` do começo ao fim.
    """
    return f"{float(v):g}".replace(".", ",")


def _reais(v) -> str:
    """R$ 1.234,56 — a frase do 409 chega inteira na tela, e falava "R$ 8.00".

    ⚠️ O `translate` troca os dois separadores de uma vez: em dois `replace` o
    segundo desfaz o primeiro, e 1.234,56 sai como 1,234,56.
    """
    trocado = f"{float(v):,.2f}".translate(str.maketrans({",": ".", ".": ","}))
    return f"R$ {trocado}"


def _fator(cur, id_produto: int, antiga: str, nova: str, ums: dict,
           um_compra: str | None, fator_compra) -> tuple[Decimal | None, str]:
    """Quantas unidades NOVAS cabem em uma ANTIGA. E de onde saiu o número.

    Três fontes, nesta ordem:

    1. **A unidade de compra que está sendo cadastrada.** É o caso do pedido: o
       estoque vira UN e a compra vira CX com fator 12, então 1 CX = 12 UN. Vem
       primeiro porque é a informação que a pessoa acabou de dar, na tela, para
       este produto — mais específica que qualquer regra geral.
    2. **O que o cadastro já sabe sobre a unidade NOVA, lido ao contrário.**
       🔑 **É a mesma relação, na outra direção** (12/09/2026, relato do dono:
       "no estoque o produto está em KG e a compra em PCT, às vezes dá uma
       mensagem que a conversão não aceita"). Com o estoque em KG e um pacote
       de 5 KG cadastrado, o sistema JÁ SABE que 1 PCT = 5 KG — então sabe
       também que 1 KG = 0,2 PCT, que é exatamente o que a troca precisa. A
       fonte (1) só responde quando a unidade de compra é a ANTIGA; sem esta,
       quem comprava em PCT e quis estocar em PCT levava uma recusa por falta
       de um número que estava gravado ali do lado.
       ⚠️ **Vem do BANCO, não do formulário**, e de propósito: `fator_compra`
       quer dizer "quantas unidades de estoque cabem em uma de compra", e a
       unidade de estoque do formulário é a NOVA — com as duas iguais o campo
       vale 1 e não diria nada. O que responde é o cadastro de antes da troca.
       ⚠️ Usa o `fator_de_embalagem` do motor de custos, que é quem já olha
       `produto_unidades` e depois o par `um_compra`/`fator_compra` — a mesma
       cascata da nota e da ficha. É também o que faz a frase da recusa
       ("cadastre a embalagem do produto") passar a ser verdade: antes ela
       mandava fazer uma coisa que não era consultada aqui.
    3. **A grandeza** (kg↔g, L↔ml): 1 KG = 1000 G, e isso vale em qualquer
       produto.

    ⚠️ **CX, PCT, FD e BDJ não convertem entre si por grandeza** — todas são
    UNIDADE com fator 1, e a conta genérica diria 1 CX = 1 PCT. Por isso as
    fontes (1) e (2) existem: quantas unidades cabem na caixa é do PRODUTO.
    """
    if (um_compra or "").strip().upper() == antiga.strip().upper():
        f = dec(fator_compra)
        if f > 0:
            return f, f"pela unidade de compra {antiga}, de fator {_br(f)}"

    # Quantas ANTIGAS cabem em uma NOVA — invertido, é quantas NOVAS cabem numa
    # antiga. ⚠️ Antes da grandeza pela mesma razão de `converter_para_estoque`:
    # o cadastro DESTE produto ganha da regra geral.
    de_volta = fator_de_embalagem(cur, id_produto, nova)
    if de_volta and de_volta > 0:
        return Decimal(1) / de_volta, (
            f"pelo cadastro de {nova} no produto, lido ao contrário: "
            f"1 {nova} = {_br(de_volta)} {antiga}")

    direto = converter(Decimal(1), antiga, nova, ums)
    if direto is not None and direto > 0:
        return dec(direto), "pela grandeza das duas unidades"

    return None, ""


def avaliar(cur, id_produto: int, antiga: str | None, nova: str | None,
            um_compra: str | None, fator_compra, ums: dict) -> dict:
    """A troca é possível? Devolve o plano, ou o motivo da recusa.

    `{"muda": False}` quando não há troca de unidade — o caso de quase todo PUT.
    """
    a = (antiga or "").strip().upper()
    n = (nova or "").strip().upper()
    if not a or not n or a == n:
        return {"muda": False}

    # ⚠️ **O razão manda.** Antes de qualquer conta: se há movimento, a unidade
    # antiga está gravada em linhas que não se reescrevem.
    cur.execute(
        "SELECT count(*) AS n FROM estoque_movimentos WHERE id_produto = %s",
        (id_produto,),
    )
    movimentos = cur.fetchone()["n"]
    if movimentos:
        return {
            "muda": True, "pode": False,
            "motivo": (
                f"Este produto já tem {movimentos} movimento(s) de estoque gravados em {a}. "
                f"O razão não se reescreve, então trocar para {n} faria o histórico e o saldo "
                f"falarem unidades diferentes. Para mudar a unidade, zere o saldo e estorne o "
                f"que houver, ou cadastre outro produto."),
        }

    fator, origem = _fator(cur, id_produto, a, n, ums, um_compra, fator_compra)
    if not fator:
        return {
            "muda": True, "pode": False,
            # ⚠️ **A frase diz os DOIS caminhos, e os dois funcionam.** A versão
            # anterior mandava "cadastre a embalagem do produto" e não olhava
            # `produto_unidades` em lugar nenhum: quem seguia a instrução levava
            # a mesma recusa e não tinha como saber por quê.
            "motivo": (
                f"Não dá para converter de {a} para {n}: o sistema não sabe quantos {n} cabem "
                f"em um {a}. Diga a relação entre as duas — cadastre {n} como embalagem deste "
                f"produto (quantos {a} vêm em um {n}), ou informe a unidade de compra {a} com "
                f"o fator correspondente."),
        }

    # O que a troca leva junto, e como.
    cur.execute(
        """SELECT custo_referencia, estoque_minimo, estoque_maximo
             FROM produtos WHERE id = %s""",
        (id_produto,),
    )
    p = dict(cur.fetchone() or {})
    conversoes = []
    custo_salto = None
    # ⚠️ **O custo DIVIDE, as quantidades MULTIPLICAM.** O custo é por unidade:
    # se a caixa de 12 custava 60, a unidade custa 5. A quantidade é o inverso:
    # um mínimo de 2 caixas é um mínimo de 24 unidades. Trocar os dois sentidos
    # é o engano natural aqui, e daria 720 de custo por unidade.
    if p.get("custo_referencia") is not None:
        antes_custo = dec(p["custo_referencia"])
        depois_custo = antes_custo / fator
        conversoes.append({
            "campo": "custo_referencia",
            "de": float(antes_custo),
            "para": float(depois_custo),
        })
        # 🔑 **"O custo vai ZERAR" é a pergunta que precisa ser feita antes**
        # (09/09/2026, relatado pelo dono). Aconteceu com uma caixa de 1.000
        # unidades a R$ 33,99: um fator de conversão invertido dividiu por mil, o
        # custo virou R$ 0,03 — que a tela mostra com duas casas como 0,00 — e
        # nada avisou. Corrigir o fator de volta NÃO desfaz, porque a conversão
        # só roda quando a unidade muda, e `custo_referencia` não é editável por
        # tela nenhuma. O valor some e não volta.
        #
        # ⚠️ **O corte é a QUEDA, não o valor final.** A primeira versão perguntou
        # só quando o resultado ficava abaixo de meio centavo — e o caso real não
        # passou: R$ 33,99 ÷ 1000 dá R$ 0,03, que não é "zero" para o computador
        # e é exatamente "zerado" para quem olha. O que denuncia o engano é a
        # ORDEM DE GRANDEZA: dividir o custo por cem ou mais quase nunca é o que
        # alguém quis fazer de propósito.
        #
        # ⚠️ Uma conversão legítima e grande (KG para G divide por mil) também
        # cai aqui e pede confirmação. É o preço certo a pagar: o Sim custa um
        # clique, e o Não custa o custo do produto.
        #
        # 🔑 **E a pergunta vale nos DOIS sentidos** (12/09/2026, pedido do dono).
        # O custo multiplicado por mil é o MESMO engano visto do outro lado — o
        # fator invertido —, e é tão irreversível quanto: a conversão só roda
        # quando a unidade muda, e `custo_referencia` não tem tela de edição. Um
        # insumo de R$ 0,03 que vira R$ 33,99 não some da vista como o zero, mas
        # contamina toda ficha que o usa e aparece no CMV do mês, longe da causa.
        # ⚠️ **A direção subiu de importância** quando a troca passou a aceitar a
        # relação lida ao contrário: antes, multiplicar o custo por mil exigia
        # uma conversão de grandeza (G para KG); agora, basta um fator de
        # embalagem errado, que é o número que mais tem palpite no cadastro.
        # ⚠️ **O corte é a ORDEM DE GRANDEZA nos dois casos, e é o mesmo cem.**
        # Uma régua diferente por sentido seria uma decisão a mais para defender
        # sem nenhum caso que a peça.
        if antes_custo > 0 and depois_custo > 0:
            if depois_custo < Decimal("0.01") or antes_custo / depois_custo >= 100:
                custo_salto = "zera"
            elif depois_custo / antes_custo >= 100:
                custo_salto = "dispara"
    for campo in ("estoque_minimo", "estoque_maximo"):
        if p.get(campo) is not None:
            conversoes.append({
                "campo": campo,
                "de": float(dec(p[campo])),
                "para": float(dec(p[campo]) * fator),
            })

    # ⚠️ **As embalagens também são POR unidade de estoque.** `produto_unidades.
    # fator` diz quantas unidades de estoque cabem em uma embalagem: com o
    # estoque em CX, a caixa tinha fator 1; com o estoque em UN ela passa a
    # valer 12. Deixá-las como estavam faria a nota de uma caixa baixar uma
    # unidade.
    cur.execute(
        "SELECT count(*) AS n FROM produto_unidades WHERE id_produto = %s", (id_produto,))
    embalagens = cur.fetchone()["n"]

    return {
        "muda": True, "pode": True,
        # "zera" quando o custo desaparece aos olhos de quem olha, "dispara"
        # quando ele multiplica de vez. Quem chama tem de perguntar antes de
        # gravar — nos dois casos.
        "custo_salto": custo_salto,
        "de": a, "para": n,
        "fator": float(fator), "origem_do_fator": origem,
        "conversoes": conversoes,
        "embalagens": embalagens,
        # ⚠️ Sem "(por a unidade de compra...)": a origem já traz a
        # preposição, porque só ela sabe se é "pela" ou "pelo".
        "resumo": (f"1 {a} = {_br(fator)} {n} — {origem}."),
    }


def frase_do_salto(plano: dict) -> str:
    """A pergunta que precede a gravação quando o custo dá um salto.

    ⚠️ **Mora aqui, e não no router, porque a regra mora aqui.** Quem decide que
    é preciso perguntar (`custo_salto`) e quem escreve a pergunta têm de ser a
    mesma pessoa: separados, o dia em que a régua mudar a frase continua falando
    da antiga.
    ⚠️ **Os DOIS números vão na frase**, de onde e para onde — uma pergunta de
    "confirma?" sem eles não é informada, e é justamente o valor que não volta.
    """
    c = next((x for x in plano["conversoes"] if x["campo"] == "custo_referencia"), None)
    if c is None:
        return "Confirme a troca de unidade."
    cabeca = (f"Trocar de {plano['de']} para {plano['para']} com fator "
              f"{_br(plano['fator'])}")
    if plano.get("custo_salto") == "dispara":
        return (f"{cabeca} multiplica o custo de {_reais(c['de'])} para "
                f"{_reais(c['para'])}. Se o fator estiver invertido, esse número "
                f"passa a valer em toda ficha que usa este insumo, e a conversão "
                f"não se desfaz. Confirme se é isso mesmo.")
    return (f"{cabeca} derruba o custo de {_reais(c['de'])} para {_reais(c['para'])} "
            f"— na prática, zerado. Se o fator estiver invertido, o custo se perde "
            f"e não volta. Confirme se é isso mesmo.")


def aplicar(cur, id_produto: int, plano: dict, id_usuario: int | None = None) -> None:
    """Grava as conversões do plano. Só é chamado quando `pode` é verdadeiro.

    ⚠️ **Roda no MESMO cursor do UPDATE do produto.** Se a gravação da unidade
    falhar, a conversão do custo tem de falhar junto — meio caminho aqui é um
    custo dividido por doze num produto que continuou em caixa.
    """
    fator = dec(plano["fator"])
    for c in plano["conversoes"]:
        cur.execute(
            f"UPDATE produtos SET {c['campo']} = %s WHERE id = %s",
            (c["para"], id_produto),
        )
    if plano.get("embalagens"):
        cur.execute(
            "UPDATE produto_unidades SET fator = fator * %s WHERE id_produto = %s",
            (fator, id_produto),
        )
    # ⚠️ **A unidade de compra que VIRA a de estoque tem fator 1, por definição**
    # — é a mesma regra que `PUT /produtos/{id}/unidades` já cobra da embalagem
    # ("nela o fator é sempre 1"). Quem estocava em KG comprando PCT de 5 e passa
    # a estocar em PCT ficaria com "1 PCT = 5 PCT" gravado: hoje isso não muda
    # conta nenhuma (a conversão para de comparar quando as duas siglas são
    # iguais), mas é o número que a PRÓXIMA troca de unidade lê como verdade.
    # ⚠️ Roda DEPOIS do UPDATE do produto, então `um_estoque` já é o novo. E não
    # entra em `conversoes`: quando a pessoa informa o fator na mesma tela, ele
    # já vem na unidade nova — convertê-lo de novo seria multiplicar por doze
    # duas vezes.
    cur.execute(
        """UPDATE produtos SET fator_compra = 1
            WHERE id = %s AND um_compra IS NOT NULL
              AND upper(um_compra) = upper(um_estoque) AND fator_compra <> 1""",
        (id_produto,),
    )

    # 🔑 **O que a conversão reescreveu fica GRAVADO.** O `PUT` do produto audita
    # nome, tipo, status e unidades — o custo não estava na lista, então uma
    # troca de unidade errada apagava o valor antigo sem deixar de onde
    # recuperá-lo. Foi assim que R$ 33,99 viraram R$ 0,03 e não houve como
    # voltar. Aqui fica o antes e o depois de cada campo.
    import auditoria

    auditoria.registrar(
        cur, id_usuario, "produto", id_produto, "troca_de_unidade",
        antes={c["campo"]: c["de"] for c in plano["conversoes"]},
        depois={
            **{c["campo"]: c["para"] for c in plano["conversoes"]},
            "de": plano.get("de"), "para": plano.get("para"),
            "fator": plano.get("fator"),
        },
    )
