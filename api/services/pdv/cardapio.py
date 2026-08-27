"""O cardápio do PDV Legal, e o de-para que liga item vendido a prato daqui.

Sem isto a venda entra e o **CMV teórico é zero**: a receita aparece, o CMV real
aparece, e a variância — que é o número que interessa — não tem com o que
comparar. Numa primeira importação real, 100 itens de 57 produtos distintos
entraram sem vínculo nenhum.

O vínculo mora em `codigos_externos` com `sistema = 'PDV_LEGAL'`, a mesma tabela
que já servia ao Omie e aos códigos de fornecedor. A chave é o `codigo` do PDV
(que chega no item da venda como `codproduto`), e não a descrição: nome de prato
muda de cardápio para cardápio e o número não.

⚠️ **A cascata só vincula o que é certo**: o de-para que já existe, o **EAN** e o
nome IDÊNTICO. Semelhança sugere e para por aí. É a mesma regra da conciliação
de nota, e pela mesma razão: um vínculo errado não fica errado sozinho — ele
contamina o CMV teórico de todo mês em que aquele prato foi vendido, e ninguém
vai procurar ali.

⚠️ **E não se casa código com código.** O `codReferencia` do cardápio e o
`produtos.codigo` daqui são espaços de nome diferentes; ver `_candidato`.

⚠️ **A fonte é `produtos/get`, não `produtos/getlistaresumida`.** A resumida traz
quatro campos (código, referência, descrição) e, na conta real do cliente, 570 de
630 itens — sessenta pratos a menos, sem dizer que faltavam. A completa traz o
grupo do cardápio, a impressora, o NCM e a unidade, que é o que transforma 464
rascunhos vazios em 464 rascunhos já classificados. A resumida ficou como
reserva, para o caso de a rota completa não estar liberada numa conta.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from services.pdv.cliente import ClientePdv, ErroPdv

SISTEMA = "PDV_LEGAL"

# Teto de páginas do `getlistaresumida` (100 por página). Cardápio de mil itens
# é cardápio de rede, não de café — e um laço sem teto contra API de terceiro é
# um jeito de descobrir o limite deles do pior jeito.
TETO_DE_PAGINAS = 40

# Abaixo disto nem sugere. Um palpite fraco na tela é pior que nenhum: ele
# convida ao clique, e quem clica não confere.
SCORE_MINIMO = 55.0

# ⚠️ "Nenhum" é o texto que o PDV usa para "não imprime em estação nenhuma" —
# não é o nome de um setor. Criar um setor chamado "Nenhum" poria 83 itens de
# mercearia e catering debaixo de um rótulo que não quer dizer nada.
SEM_IMPRESSORA = {"", "nenhum", "nenhuma", "0", "none"}

# O PDV escreve a grama como "GR"; aqui a sigla é "G". As demais coincidem, e o
# que não coincidir fica sem unidade — que é o estado honesto de um rascunho.
SIGLAS = {"GR": "G", "UND": "UN", "UNID": "UN"}


def _normalizar(texto: str | None) -> str:
    """Sem acento, sem pontuação, espaços colapsados, minúsculo.

    "PÃO DE QUEIJO C/ REQ." e "pao de queijo c req" viram a mesma coisa — que é
    o que permite o nome idêntico valer como vínculo em vez de só sugestão.
    """
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", sem_acento.lower())).strip()


def _primeiro(bruto: dict, *nomes: str) -> str:
    """O primeiro campo preenchido, na ordem dada.

    Mesma ideia do mapeador do Omie: a mesma informação tem nome diferente em
    cada rota da mesma API, e ler por lista de nomes possíveis é o que impede um
    campo renomeado de virar um cadastro em branco que ninguém percebe.
    """
    for nome in nomes:
        valor = bruto.get(nome)
        if valor not in (None, "", 0):
            return str(valor).strip()
    return ""


def _item(bruto: dict) -> dict:
    """Um item do cardápio, com os nomes daqui.

    Serve as duas rotas: a completa (`descricaoCupom`, `status`, `nomeGrupo`…) e
    a resumida (`descricao` e mais nada). O que a resumida não tem vira vazio, e
    `ativo` vira True — uma rota que não fala de status não está dizendo que o
    item está fora do cardápio.
    """
    impressora = _primeiro(bruto, "nomeImpressora")
    sigla = _primeiro(bruto, "unidade").upper()
    return {
        "codigo": _primeiro(bruto, "codigo"),
        "descricao": _primeiro(
            bruto, "descricaoCupom", "descricao", "descricaoDetalhada", "descrTabletQrCodeMesa"
        )[:200],
        "ativo": bool(bruto.get("status", True)),
        "grupo": _primeiro(bruto, "nomeGrupo")[:80],
        "setor": "" if impressora.lower() in SEM_IMPRESSORA else impressora[:80],
        "ncm": re.sub(r"\D", "", _primeiro(bruto, "codigoNCM"))[:8],
        "ean": re.sub(r"\D", "", _primeiro(bruto, "codigoEAN"))[:14],
        "unidade": SIGLAS.get(sigla, sigla)[:10],
    }


def baixar(cliente: ClientePdv) -> list[dict]:
    """Todo o cardápio, já com os nomes daqui.

    Tenta a rota completa primeiro. Só cai na resumida quando a completa não
    responde — e aí a paginação e o envelope voltam a importar.

    ⚠️ **A resposta da resumida é um ENVELOPE, não uma lista**: `{total_count,
    total, pagina, data}`. Tratá-la como lista devolveria as quatro chaves como
    se fossem quatro produtos — e o importador diria "4 itens" numa conta com 630.
    """
    try:
        completa = cliente.get("/produtos/get")
    except ErroPdv:
        completa = None
    if isinstance(completa, dict):
        completa = completa.get("data")
    if completa:
        return [_item(b) for b in completa]

    itens: list[dict] = []
    pagina = 1
    while pagina <= TETO_DE_PAGINAS:
        envelope = cliente.get(f"/produtos/getlistaresumida/{pagina}")
        if isinstance(envelope, list):        # modo simulado, ou API que mudou
            lote, total = envelope, len(envelope)
        else:
            lote = (envelope or {}).get("data") or []
            total = int((envelope or {}).get("total") or 0)
        if not lote:
            break
        itens.extend(lote)
        if len(itens) >= total:
            break
        pagina += 1
    return [_item(b) for b in itens]


# ------------------------------------------------------- classificação de apoio


class _Apoio:
    """Categoria, setor e unidade — achados ou criados, uma vez cada.

    ⚠️ **Existe para não fazer 630 SELECTs iguais.** Um cardápio de 630 itens tem
    30 grupos e 4 impressoras; sem o cache, cada item repetiria a mesma busca.
    """

    def __init__(self, cur):
        self.cur = cur
        self._categorias: dict[str, int | None] = {}
        self._setores: dict[str, int | None] = {}
        self._unidades: set[str] | None = None

    def categoria(self, nome: str) -> int | None:
        """O grupo do cardápio vira categoria de produto.

        ⚠️ Nasce com `tipo = 'PRODUZIDO'`, não `'INSUMO'`: são categorias de
        coisa que se VENDE (CAFETERIA, SANDUICHES, ALMOCO), e misturá-las com as
        de insumo faria a tela de cadastro oferecer "Sanduíches" para classificar
        um quilo de farinha.
        """
        if not nome:
            return None
        chave = nome.strip().lower()
        if chave in self._categorias:
            return self._categorias[chave]
        self.cur.execute(
            "SELECT id FROM categorias WHERE lower(nome) = %s LIMIT 1", (chave,)
        )
        achada = self.cur.fetchone()
        if achada:
            self._categorias[chave] = achada["id"]
        else:
            self.cur.execute(
                "INSERT INTO categorias (nome, tipo, ativo) VALUES (%s, 'PRODUZIDO', true) "
                "RETURNING id",
                (nome,),
            )
            self._categorias[chave] = self.cur.fetchone()["id"]
        return self._categorias[chave]

    def setor(self, nome: str) -> int | None:
        """A impressora do PDV vira setor.

        VITRINE, BAR, COZINHA — é onde o item é preparado, que é exatamente o que
        o setor significa aqui. Sai de graça um CMV por setor que faria sentido
        para quem toca a casa, e que de outro jeito alguém teria de digitar 630
        vezes.
        """
        if not nome:
            return None
        chave = nome.strip().lower()
        if chave in self._setores:
            return self._setores[chave]
        self.cur.execute(
            "SELECT id FROM setores WHERE lower(nome) = %s LIMIT 1", (chave,)
        )
        achado = self.cur.fetchone()
        if achado:
            self._setores[chave] = achado["id"]
        else:
            self.cur.execute(
                "INSERT INTO setores (nome, ativo) VALUES (%s, true) RETURNING id", (nome,)
            )
            self._setores[chave] = self.cur.fetchone()["id"]
        return self._setores[chave]

    def unidade(self, sigla: str) -> str | None:
        """A sigla, só se ela existir aqui.

        ⚠️ **Sigla desconhecida vira nulo, nunca uma unidade nova.** É a mesma
        regra do item da nota: `um_estoque` é chave estrangeira, e criar "M" de
        metro porque o cardápio mandou é criar um problema no lugar de recusar um
        dado.
        """
        if not sigla:
            return None
        if self._unidades is None:
            self.cur.execute("SELECT sigla FROM unidades_medida WHERE ativo")
            self._unidades = {r["sigla"] for r in self.cur.fetchall()}
        return sigla if sigla in self._unidades else None


def _candidato(cur, codigo: str, descricao: str, ean: str,
               por_nome: dict[str, int]) -> tuple[int | None, str, float]:
    """A cascata: onde este item do cardápio encontra um produto daqui.

    A ordem é da certeza para o palpite, e o palpite não vincula:

    1. **código do PDV** já registrado em `codigos_externos` — o de-para de antes
    2. **EAN/GTIN** — identificador global, e único no cadastro
    3. **nome idêntico**, normalizado
    4. **semelhança** — só sugestão, nunca vínculo

    ⚠️ **NÃO existe passo por código da casa, e isso custou caro para descobrir.**
    A primeira versão casava o `codReferencia` do cardápio ("72", "75", "141")
    com `produtos.codigo` — e os dois são espaços de nome diferentes. Numa base
    com 2.189 insumos importados do Omie, **os 78 vínculos criados assim estavam
    todos errados**: REDBULL virou LIMÃO TAITY, PÃO COM MANTEIGA virou
    MANJERICÃO, BOLO virou ADESIVO VINIL PRETO. Nenhum deles daria erro em lugar
    nenhum — apenas o CMV teórico de todo mês sairia com o custo do insumo
    errado, para sempre, e ninguém iria procurar ali.

    ⚠️ **O EAN é o oposto disso: ele identifica o mesmo objeto físico no mundo
    todo.** É o que impede o mesmo pacote de café de virar dois cadastros — um
    vindo do catálogo do Omie (onde ele é comprado) e outro do cardápio (onde é
    vendido) —, que é o duplicado que ninguém enxerga: a compra entra no estoque
    por um cadastro, a venda não sai por nenhum, e a sobra aparece na contagem
    como "ajuste de inventário", que é onde a diferença some sem nome.
    ⚠️ Sem ambiguidade por construção: `ux_produto_barras` é único. **A conta
    real do cliente devolve EAN vazio em 100% do cardápio** — este passo dorme
    hoje e passa a valer no dia em que alguém preencher, do lado de lá ou daqui.
    """
    if codigo:
        cur.execute(
            "SELECT id_produto FROM codigos_externos WHERE sistema = %s AND codigo = %s",
            (SISTEMA, codigo),
        )
        achado = cur.fetchone()
        if achado:
            return achado["id_produto"], "ja_vinculado", 100.0

    if ean:
        cur.execute("SELECT id FROM produtos WHERE codigo_barras = %s", (ean,))
        achado = cur.fetchone()
        if achado:
            return achado["id"], "ean", 100.0

    chave = _normalizar(descricao)
    if chave and chave in por_nome:
        return por_nome[chave], "nome", 100.0

    melhor, melhor_score = None, 0.0
    for nome, id_produto in por_nome.items():
        score = SequenceMatcher(None, chave, nome).ratio() * 100
        if score > melhor_score:
            melhor, melhor_score = id_produto, score
    if melhor and melhor_score >= SCORE_MINIMO:
        return melhor, "semelhanca", round(melhor_score, 2)
    return None, "sem_candidato", 0.0


# ⚠️ Só campo que o cardápio ENSINA. `tipo`, `modo_producao` e `id_local_padrao`
# ficam de fora de propósito: o PDV não sabe se um item de mercearia é revenda ou
# produção própria, e chutar poria o prato na fila errada — a de "falta ficha"
# em vez da de "falta compra", ou o contrário.
_DO_CARDAPIO = ("id_categoria", "id_setor", "ncm", "codigo_barras", "um_estoque")


# ⚠️ Colunas com índice ÚNICO. Escrever nelas um valor que já é de outro produto
# não derruba só aquele item — derruba a importação inteira, porque a transação é
# uma só. Ver `_completar`.
_UNICOS = ("codigo_barras",)


def _completar(cur, id_produto: int, campos: dict) -> tuple[bool, int]:
    """Preenche só o que está EM BRANCO no produto. Devolve (mudou, conflitos).

    ⚠️ **Nunca sobrescreve.** Reimportar o cardápio depois de alguém corrigir a
    categoria de um prato não pode desfazer a correção — é a mesma lição do
    importador de fornecedores do Omie. Sem isto, a reimportação também não
    faria nada (`continue` no item já vinculado), e os rascunhos criados por uma
    versão anterior ficariam vazios para sempre.

    ⚠️ **EAN que já pertence a OUTRO produto é PULADO, não gravado.** O cenário
    acontece em três tempos: o item entra sem EAN e vira rascunho; depois o
    catálogo do Omie traz o produto de verdade, com o EAN; depois alguém
    preenche o EAN no PDV. Na reimportação o item já está vinculado — o primeiro
    passo da cascata responde antes do EAN —, e a gravação batia no
    `ux_produto_barras`. Não é um item que falha: é a importação inteira que
    morre, e nada entra.

    ⚠️ **E o conflito é INFORMAÇÃO, não erro**: dois cadastros disputando o mesmo
    EAN são o mesmo produto. Quem resolve isso é `/produtos/duplicados`, que sabe
    mover o de-para, os itens de venda e o custo junto — repontar o vínculo aqui
    deixaria as vendas passadas presas no rascunho.
    """
    cur.execute(
        f"SELECT {', '.join(_DO_CARDAPIO)} FROM produtos WHERE id = %s", (id_produto,)
    )
    antes = cur.fetchone()
    if not antes:
        return False, 0
    faltando = {c: v for c, v in campos.items() if v is not None and not antes[c]}

    conflitos = 0
    for coluna in _UNICOS:
        valor = faltando.get(coluna)
        if valor is None:
            continue
        cur.execute(
            f"SELECT 1 FROM produtos WHERE {coluna} = %s AND id <> %s LIMIT 1",
            (valor, id_produto),
        )
        if cur.fetchone():
            faltando.pop(coluna)
            conflitos += 1

    if not faltando:
        return False, conflitos
    sets = ", ".join(f"{c} = %s" for c in faltando)
    cur.execute(
        f"UPDATE produtos SET {sets} WHERE id = %s", [*faltando.values(), id_produto]
    )
    return True, conflitos


def importar(cur, cliente: ClientePdv, id_usuario: int,
             criar_ausentes: bool = True) -> dict:
    """Traz o cardápio e liga o que dá para ligar.

    ⚠️ **Semelhança NÃO vincula** — vira uma linha na observação do rascunho
    criado ("parece com X"), para quem for fazer a ficha conferir. Vínculo
    errado não fica errado sozinho: contamina o CMV teórico de todo mês em que
    aquele prato foi vendido, e ninguém vai procurar ali.

    ⚠️ **`criar_ausentes` faz o prato nascer RASCUNHO.** O item do cardápio é um
    PRATO — ele precisa de ficha para virar custo. Criá-lo como rascunho com
    `producao_propria` marcada o põe na fila de "produzido sem ficha", que é
    exatamente a lista que alguém precisa percorrer.

    ⚠️ **Item fora do cardápio nasce INATIVO, não deixa de nascer.** Na conta
    real, 166 dos 630 estão desligados no PDV — mas venda antiga aponta para
    eles, e um item sem cadastro é uma venda sem vínculo que ninguém consegue
    resolver depois. Inativo resolve os dois lados: o de-para existe, o histórico
    fecha, e a fila de "falta ficha" continua mostrando só os 464 que ainda se
    vendem.
    """
    itens = baixar(cliente)
    apoio = _Apoio(cur)

    cur.execute("SELECT id, nome FROM produtos WHERE ativo")
    por_nome = {_normalizar(r["nome"]): r["id"] for r in cur.fetchall()}

    resumo = {"itens": len(itens), "vinculados": 0, "ja_vinculados": 0,
              "criados": 0, "inativos": 0, "completados": 0,
              # ⚠️ Contado à parte porque é o vínculo mais forte que existe, e
              # porque hoje ele vale ZERO nesta conta: ver o número em 0 é o que
              # diz que o cardápio do cliente não tem EAN preenchido.
              "por_ean": 0, "sugestoes": 0, "sem_vinculo": 0,
              # ⚠️ EAN que já é de outro cadastro: os dois são o mesmo produto.
              # Não é erro — é o caminho para `/produtos/duplicados`.
              "ean_de_outro": 0}

    for item in itens:
        codigo, descricao = item["codigo"], item["descricao"]
        if not codigo:
            continue

        campos = {
            "id_categoria": apoio.categoria(item["grupo"]),
            "id_setor": apoio.setor(item["setor"]),
            "ncm": item["ncm"] or None,
            "codigo_barras": item["ean"] or None,
            "um_estoque": apoio.unidade(item["unidade"]),
        }

        id_produto, origem, score = _candidato(cur, codigo, descricao, item["ean"], por_nome)

        if origem == "ja_vinculado":
            resumo["ja_vinculados"] += 1
            mudou, conflitos = _completar(cur, id_produto, campos)
            resumo["completados"] += 1 if mudou else 0
            resumo["ean_de_outro"] += conflitos
            continue

        dica = None
        if origem == "semelhanca":
            # Sugestão só: a dica viaja com o rascunho, mas não amarra nada.
            resumo["sugestoes"] += 1
            cur.execute("SELECT nome FROM produtos WHERE id = %s", (id_produto,))
            parecido = (cur.fetchone() or {}).get("nome")
            dica = (f"Parece com “{parecido}” ({score:.0f}%). Confira antes de "
                    "fazer a ficha — o palpite não vinculou nada.")
            id_produto = None

        if not id_produto and criar_ausentes:
            # ⚠️ O código da casa nasce com prefixo: `codigo` é único, e o número
            # do PDV pode colidir com um código que alguém já usou aqui.
            cur.execute(
                """INSERT INTO produtos (codigo, nome, tipo, status, origem,
                                         producao_propria, controla_estoque, observacao,
                                         ativo, id_categoria, id_setor, ncm,
                                         codigo_barras, um_estoque, criado_por)
                   VALUES (%s, %s, 'PRODUZIDO', 'RASCUNHO', 'PDV', true, false, %s,
                           %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (f"PDV-{codigo}"[:40], descricao or f"Item {codigo}", dica, item["ativo"],
                 campos["id_categoria"], campos["id_setor"], campos["ncm"],
                 campos["codigo_barras"], campos["um_estoque"], id_usuario),
            )
            criado = cur.fetchone()
            if criado:
                id_produto = criado["id"]
                origem = "criado"
                resumo["criados"] += 1
                if not item["ativo"]:
                    resumo["inativos"] += 1

        if not id_produto:
            resumo["sem_vinculo"] += 1
            continue

        if origem != "criado":
            mudou, conflitos = _completar(cur, id_produto, campos)
            resumo["completados"] += 1 if mudou else 0
            resumo["ean_de_outro"] += conflitos

        cur.execute(
            """INSERT INTO codigos_externos (sistema, codigo, id_produto, descricao_externa,
                                             origem_vinculo, confirmado_por)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (sistema, codigo) DO UPDATE
                   SET descricao_externa = EXCLUDED.descricao_externa""",
            (SISTEMA, codigo, id_produto, descricao, origem.upper()[:20], id_usuario),
        )
        if origem != "criado":
            resumo["vinculados"] += 1
            if origem == "ean":
                resumo["por_ean"] += 1

    return resumo


def reconciliar(cur, id_unidade: int) -> dict:
    """Passa o de-para nos itens de venda que ficaram sem produto.

    ⚠️ **Existe pela mesma razão que a reconciliação de nota**: a ordem real é a
    venda chegar antes de o cardápio estar ligado. Sem isto, item que não achou
    produto no dia da importação ficaria pendente para sempre — e o CMV teórico
    daquele mês nunca fecharia, mesmo depois de alguém arrumar o de-para.

    ⚠️ **O custo é recalculado AGORA, não herdado.** `custo_ficha_unitario` é
    congelado no momento do uso; um item que entrou sem produto entrou sem custo,
    e ao ganhar produto precisa do custo de hoje — que é o que o mês passa a
    contar. Isso muda o CMV teórico do período, e é o efeito desejado: antes ele
    estava contando zero.
    """
    from services import cmv as motor

    cur.execute(
        """SELECT vi.id, vi.codigo_pdv, ce.id_produto
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
             JOIN codigos_externos ce ON ce.sistema = %s AND ce.codigo = vi.codigo_pdv
            WHERE v.id_unidade = %s AND vi.id_produto IS NULL AND NOT v.cancelada""",
        (SISTEMA, id_unidade),
    )
    pendentes = [dict(r) for r in cur.fetchall()]

    custos: dict[int, tuple] = {}
    vinculados, com_custo = 0, 0
    for item in pendentes:
        id_produto = item["id_produto"]
        if id_produto not in custos:
            custos[id_produto] = motor.custo_teorico_do_produto(cur, id_produto)
        custo, origem = custos[id_produto]
        cur.execute(
            """UPDATE venda_itens
                  SET id_produto = %s, custo_ficha_unitario = %s, origem_custo = %s
                WHERE id = %s""",
            (id_produto, custo, origem, item["id"]),
        )
        vinculados += 1
        if custo is not None:
            com_custo += 1

    return {"vinculados": vinculados, "com_custo": com_custo,
            "sem_custo": vinculados - com_custo}
