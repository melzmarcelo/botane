"""O cardápio do PDV Legal — e o preço de venda que vem junto.

Sem o cardápio a venda entra e o **CMV teórico é zero**: a receita aparece, o CMV
real aparece, e a variância — que é o número que interessa — não tem com o que
comparar.

⚠️ **NADA aqui adivinha.** O item é reconhecido pelo **código do PDV**
(`services/pdv/vinculo.py`) ou pelo **EAN**, que é identificador global e não
palpite. Não achou? Nasce rascunho, e quem reconhece o produto liga com o botão
Vincular na tela dele.

A versão anterior casava por nome idêntico e sugeria por semelhança, e errava
nos dois sentidos: não achava "BEB CERV HEINEKEN 350ML" contra "CERVEJA HEINEKEN
PILSEN" (63,8% — o mesmo produto), e juntava "CAKE BOARD N19" com "CAKE BOARD
N21", que são tamanhos diferentes. Um palpite errado não fica errado sozinho:
contamina o CMV teórico de todo mês em que aquele prato foi vendido, e ninguém
vai procurar ali.

⚠️ **A fonte do cadastro é `produtos/get`, não `produtos/getlistaresumida`.** A
resumida traz quatro campos e, na conta real, 570 de 630 itens — sessenta pratos
a menos, sem dizer que faltavam.

⚠️ **O preço vem de OUTRA rota** (`tabelapreco/get/{filial}`), não do cadastro
do produto: `valor`, preenchido em 629 dos 630 na conta real. Sem ela os pratos
nasciam sem preço nenhum, com o número a uma chamada de distância.
"""

import re

from services.pdv import vinculo
from services.pdv.cliente import ClientePdv, ErroPdv

SISTEMA = "PDV_LEGAL"

# Teto de páginas do `getlistaresumida` (100 por página). Cardápio de mil itens
# é cardápio de rede, não de café — e um laço sem teto contra API de terceiro é
# um jeito de descobrir o limite deles do pior jeito.
TETO_DE_PAGINAS = 40

# ⚠️ "Nenhum" é o texto que o PDV usa para "não imprime em estação nenhuma" —
# não é o nome de um setor. Criar um setor chamado "Nenhum" poria 83 itens de
# mercearia e catering debaixo de um rótulo que não quer dizer nada.
SEM_IMPRESSORA = {"", "nenhum", "nenhuma", "0", "none"}

# O PDV escreve a grama como "GR"; aqui a sigla é "G". As demais coincidem, e o
# que não coincidir fica sem unidade — que é o estado honesto de um rascunho.
SIGLAS = {"GR": "G", "UND": "UN", "UNID": "UN"}


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


def precos(cliente: ClientePdv, filial: str) -> dict[str, float]:
    """O preço de venda de cada item, por código do PDV.

    ⚠️ **Vem de OUTRA rota** (`tabelapreco/get/{filial}`), não do cadastro do
    produto — foi por isso que os pratos nasciam sem preço nenhum durante toda a
    primeira versão: o número estava a uma chamada de distância. Na conta real,
    `valor` vem preenchido em 629 dos 630.

    ⚠️ **O preço é POR FILIAL.** Sem filial não há preço, e devolver vazio é a
    resposta honesta: melhor prato sem preço do que prato com o preço de outra
    loja.
    """
    if not filial:
        return {}
    try:
        bruto = cliente.get(f"/tabelapreco/get/{filial}")
    except ErroPdv:
        return {}
    if isinstance(bruto, dict):
        bruto = bruto.get("data") or []
    tabela = {}
    for linha in bruto or []:
        codigo = _primeiro(linha, "codProduto", "codigo")
        valor = linha.get("valor")
        if codigo and valor:
            tabela[codigo] = float(valor)
    return tabela


def _gravar_preco(cur, id_produto: int, preco: float, id_usuario: int) -> bool:
    """Abre o preço de venda vigente, se ele mudou.

    ⚠️ **Só grava quando MUDA.** `produto_precos` é histórico: uma linha nova a
    cada importação transformaria "quando o preço subiu" em ruído, e é essa
    pergunta que a tabela existe para responder.
    """
    cur.execute(
        """SELECT id, preco_venda FROM produto_precos
            WHERE id_produto = %s AND id_unidade IS NULL AND vigente_ate IS NULL""",
        (id_produto,),
    )
    atual = cur.fetchone()
    if atual and float(atual["preco_venda"]) == float(preco):
        return False
    if atual:
        cur.execute(
            "UPDATE produto_precos SET vigente_ate = current_date WHERE id = %s", (atual["id"],)
        )
    cur.execute(
        "INSERT INTO produto_precos (id_produto, preco_venda, criado_por) VALUES (%s, %s, %s)",
        (id_produto, preco, id_usuario),
    )
    return True


def importar(cur, cliente: ClientePdv, id_usuario: int, filial: str = "",
             criar_ausentes: bool = True) -> dict:
    """Traz o cardápio e liga o que o CÓDIGO manda ligar.

    ⚠️ **Duas portas, e nenhuma delas é palpite**: o código do PDV
    (`vinculo.por_codigo`, que olha o campo do produto e os apelidos) e o **EAN**,
    que é identificador global. Não achou nenhuma? Nasce rascunho — e quem
    reconhece o produto liga com o botão Vincular na tela dele.

    ⚠️ **`criar_ausentes` faz o prato nascer RASCUNHO.** O item do cardápio é um
    PRATO — ele precisa de ficha para virar custo. Criá-lo como rascunho com
    `producao_propria` marcada o põe na fila de "produzido sem ficha", que é
    exatamente a lista que alguém precisa percorrer.

    ⚠️ **Item fora do cardápio nasce INATIVO, não deixa de nascer.** Na conta
    real, 166 dos 630 estão desligados no PDV — mas venda antiga aponta para
    eles, e um item sem cadastro é uma venda sem vínculo que ninguém consegue
    resolver depois. Inativo fecha os dois lados: o vínculo existe, o histórico
    fecha, e a fila de "falta ficha" mostra só os que ainda se vendem.
    """
    itens = baixar(cliente)
    apoio = _Apoio(cur)
    tabela = precos(cliente, filial)

    resumo = {"itens": len(itens), "vinculados": 0, "ja_vinculados": 0,
              "criados": 0, "inativos": 0, "completados": 0,
              # ⚠️ Contado à parte porque é o vínculo mais forte que existe, e
              # porque hoje ele vale ZERO nesta conta: ver o número em 0 é o que
              # diz que o cardápio do cliente não tem EAN preenchido.
              "por_ean": 0, "apelidos": 0, "sem_vinculo": 0,
              # ⚠️ EAN que já é de outro cadastro: os dois são o mesmo produto.
              # Não é erro — é o caminho para o botão Vincular.
              "ean_de_outro": 0, "precos": 0}

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

        # ---- porta 1: o código do PDV, principal ou apelido
        id_produto = vinculo.por_codigo(cur, codigo)
        origem = "ja_vinculado" if id_produto else None

        # ---- porta 2: o EAN, que é identificador global e não palpite
        if not id_produto and item["ean"]:
            cur.execute("SELECT id FROM produtos WHERE codigo_barras = %s", (item["ean"],))
            achado = cur.fetchone()
            if achado:
                id_produto, origem = achado["id"], "ean"

        if not id_produto and criar_ausentes:
            # ⚠️ O código da casa nasce com prefixo: `codigo` é único, e o número
            # do PDV pode colidir com um código que alguém já usou aqui.
            cur.execute(
                """INSERT INTO produtos (codigo, nome, nome_curto, tipo, status, origem,
                                         producao_propria, controla_estoque,
                                         ativo, id_categoria, id_setor, ncm,
                                         codigo_barras, um_estoque, codigo_pdv, criado_por)
                   VALUES (%s, %s, %s, 'PRODUZIDO', 'RASCUNHO', 'PDV', true, false,
                           %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (f"PDV-{codigo}"[:40], descricao or f"Item {codigo}", (descricao or "")[:60],
                 item["ativo"], campos["id_categoria"], campos["id_setor"], campos["ncm"],
                 campos["codigo_barras"], campos["um_estoque"], str(codigo), id_usuario),
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
            onde = vinculo.gravar(cur, id_produto, codigo, descricao, id_usuario)
            resumo["apelidos"] += 1 if onde == "apelido" else 0
            resumo["vinculados"] += 1
            resumo["por_ean"] += 1 if origem == "ean" else 0

        preco = tabela.get(str(codigo))
        if preco and _gravar_preco(cur, id_produto, preco, id_usuario):
            resumo["precos"] += 1

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

    # ⚠️ **Os dois níveis do vínculo**, não só os apelidos: desde que o código do
    # PDV virou campo do produto, procurar apenas em `codigos_externos` deixava
    # de fora justamente o vínculo principal — o que a tela mostra.
    mapa = vinculo.de_para(cur)
    cur.execute(
        """SELECT vi.id, vi.codigo_pdv
             FROM venda_itens vi
             JOIN vendas v ON v.id = vi.id_venda
            WHERE v.id_unidade = %s AND vi.id_produto IS NULL AND NOT v.cancelada""",
        (id_unidade,),
    )
    pendentes = [
        {**dict(r), "id_produto": mapa[str(r["codigo_pdv"])]}
        for r in cur.fetchall()
        if str(r["codigo_pdv"]) in mapa
    ]

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
