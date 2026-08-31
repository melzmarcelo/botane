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
        "cest": re.sub(r"\D", "", _primeiro(bruto, "codigoCest"))[:7],
        "ean": re.sub(r"\D", "", _primeiro(bruto, "codigoEAN"))[:14],
        "unidade": SIGLAS.get(sigla, sigla)[:10],
        # ⚠️ **O nome do cupom e o detalhado são campos DIFERENTES**, e viram
        # coisas diferentes aqui: o do cupom é o `nome_curto` (o que sai impresso
        # e aparece no botão do PDV), o detalhado só vira `nome` quando o produto
        # não tem lado do Omie. Ver `_atualizar`.
        "nome_cupom": _primeiro(bruto, "descricaoCupom", "descricao")[:60],
        "nome_longo": _primeiro(bruto, "descricaoDetalhada", "descricaoCupom",
                                "descricao")[:200],
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
# O que o cardápio do PDV sabe sobre um produto e este sistema também guarda.
# ⚠️ `nome` não entra aqui: ele é decidido à parte, porque tem DONO diferente
# conforme a origem do cadastro — ver `_atualizar`.
_DO_CARDAPIO = ("id_categoria", "id_setor", "ncm", "cest", "codigo_barras",
                "um_estoque", "nome_curto", "ativo")


# ⚠️ Colunas com índice ÚNICO. Escrever nelas um valor que já é de outro produto
# não derruba só aquele item — derruba a importação inteira, porque a transação é
# uma só. Ver `_atualizar`.
_UNICOS = ("codigo_barras",)


def _atualizar(cur, id_produto: int, campos: dict) -> tuple[bool, int]:
    """Traz do PDV o que o PDV TEM. Devolve (mudou, conflitos).

    🔑 **O botão "Importar cardápio" passa a ser o momento de alinhar** — decisão
    do dono, 30/08/2026. Antes ele só preenchia o que estava em branco, com a
    regra "reimportar não desfaz correção de quem cadastrou aqui"; o efeito era
    que nome, situação e preço alterados no PDV **nunca** chegavam. Agora ele
    sobrescreve, e o que evita o ping-pong é ser MANUAL: nada disso acontece
    sozinho, e a busca de vendas — que roda por agenda — não chama esta função.

    ⚠️ **"O que o PDV TEM", não "o que o PDV mandou".** Campo vazio de lá NÃO
    apaga o daqui: o cardápio real tem produto com NCM e CEST em branco, e
    sobrescrever com vazio destruiria dado que alguém preencheu. Foi a condição
    que o dono pôs na própria frase: *"com todas as informações presentes no PDV,
    caso contrário não"*.

    ⚠️ **`ativo` é a exceção e entra SEMPRE**: ele é booleano, nunca "vazio", e
    trazê-lo é justamente a volta que se pediu — produto desligado no cardápio
    fica inativo aqui na próxima importação.

    ⚠️ **EAN que já pertence a OUTRO produto é PULADO, não gravado.** O cenário
    acontece em três tempos: o item entra sem EAN e vira rascunho; depois o
    catálogo do Omie traz o produto de verdade, com o EAN; depois alguém
    preenche o EAN no PDV. Na reimportação o item já está vinculado — o primeiro
    passo da cascata responde antes do EAN —, e a gravação batia no
    `ux_produto_barras`. Não é um item que falha: é a importação inteira que
    morre, e nada entra.

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
    # ⚠️ As colunas lidas saem das CHAVES do que veio, não de uma lista fixa: o
    # `nome` entra só em alguns produtos (ver o chamador), e uma lista fixa
    # ou o traria sempre ou nunca.
    colunas = [c for c in campos if c in (*_DO_CARDAPIO, "nome")]
    if not colunas:
        return False, 0
    cur.execute(
        f"SELECT {', '.join(colunas)} FROM produtos WHERE id = %s", (id_produto,)
    )
    antes = cur.fetchone()
    if not antes:
        return False, 0
    # Só o que o PDV tem, e só o que está diferente daqui. `ativo` passa mesmo
    # sendo `False`, porque ali o falso É a informação.
    faltando = {
        c: v for c, v in campos.items()
        if (v not in (None, "") or c == "ativo") and antes[c] != v
    }

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


def _gravar_preco(cur, id_produto: int, preco: float, id_usuario: int,
                  id_unidade: int | None = None) -> bool:
    """O preço que veio do cardápio — e ele é **da loja**, não da casa.

    🔑 **`tabelapreco/get/{filial}` é POR FILIAL**, e por isso o preço importado
    passa a nascer com `id_unidade`. Gravá-lo como preço da casa fazia o valor da
    filial sobrescrever o da matriz a cada importação, sem nada denunciando —
    duas lojas que cobram diferente pelo mesmo prato terminavam com um preço só,
    o da última que sincronizou.

    ⚠️ **Só grava quando MUDA**: `produto_precos` é histórico, e uma linha por
    importação transformaria "quando o preço subiu?" em ruído.
    """
    from services import precos

    return precos.gravar(cur, id_produto, preco, id_usuario, id_unidade)

def importar(cur, cliente: ClientePdv, id_usuario: int, filial: str = "",
             criar_ausentes: bool = True, id_unidade: int = 1) -> dict:
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

    # 🔑 **O preço vem, mesmo com o Botané sendo o dono dele** — decisão do dono,
    # 30/08/2026: *"o preço que deve ser considerado no cupom é o que vem do
    # PDV"*. Houve uma versão que parava de lê-lo quando `enviar_ao_pdv` estava
    # ligado, para evitar o ping-pong; o remédio era pior que a doença, porque o
    # valor alterado lá simplesmente se perdia.
    # ⚠️ **O que evita o ping-pong é isto ser MANUAL.** Esta função só roda pelo
    # botão "Importar cardápio"; a busca de vendas, que roda por agenda, chama a
    # `reconciliar` e nunca esta. Então "ser dono do preço" quer dizer *o preço
    # daqui é o que SAI* — e alinhar os dois é um clique de alguém, não um
    # efeito colateral.
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
            "cest": item["cest"] or None,
            "codigo_barras": item["ean"] or None,
            "um_estoque": apoio.unidade(item["unidade"]),
            # O que sai impresso no cupom e no botão do PDV.
            "nome_curto": item["nome_cupom"] or None,
            "ativo": item["ativo"],
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
            else:
                # 🔑 **O `ON CONFLICT DO NOTHING` engolia o caso em que o
                # cadastro JÁ nasceu daqui e perdeu o vínculo.** `PDV-<codigo>` é
                # derivado do código do PDV, então quem tem esse código É este
                # item — não é palpite por nome, é o mesmo número. Sem isto, um
                # `codigo_pdv` apagado (uma limpeza, um Vincular desfeito) virava
                # item sem vínculo PARA SEMPRE: a criação colidia calada e a
                # cascata não tinha por onde reconhecê-lo.
                cur.execute("SELECT id FROM produtos WHERE codigo = %s",
                            (f"PDV-{codigo}"[:40],))
                achado = cur.fetchone()
                if achado:
                    id_produto, origem = achado["id"], "codigo_da_casa"
                    cur.execute(
                        """UPDATE produtos SET codigo_pdv = %s
                            WHERE id = %s AND codigo_pdv IS NULL""",
                        (str(codigo), id_produto))

        if not id_produto:
            resumo["sem_vinculo"] += 1
            continue

        if origem != "criado":
            # 🔑 **O `nome` tem DONO diferente conforme a origem do cadastro.**
            # Quando o produto existe nos dois sistemas, a decisão da casa é:
            # `nome` = o do OMIE (o fiscal, o que aparece na nota do fornecedor e
            # o que se procura ao conferir uma compra) e `nome_curto` = o do PDV
            # (o que sai no cupom). Trazer o `descricaoDetalhada` por cima
            # apagaria o nome fiscal — e não há como recuperá-lo sem reimportar o
            # catálogo do Omie inteiro. Por isso ele só entra quando NÃO há lado
            # do Omie; tendo, o do PDV já está guardado no `nome_curto`.
            cur.execute("SELECT codigo_omie FROM produtos WHERE id = %s", (id_produto,))
            do_omie = (cur.fetchone() or {}).get("codigo_omie")
            campos_do_item = dict(campos)
            if not do_omie and item["nome_longo"]:
                campos_do_item["nome"] = item["nome_longo"]
            mudou, conflitos = _atualizar(cur, id_produto, campos_do_item)
            resumo["completados"] += 1 if mudou else 0
            resumo["ean_de_outro"] += conflitos
            onde = vinculo.gravar(cur, id_produto, codigo, descricao, id_usuario)
            resumo["apelidos"] += 1 if onde == "apelido" else 0
            resumo["vinculados"] += 1
            resumo["por_ean"] += 1 if origem == "ean" else 0

        preco = tabela.get(str(codigo))
        if preco and _gravar_preco(cur, id_produto, preco, id_usuario, id_unidade):
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
            # A loja vai junto: este custo é CONGELADO no item de venda, e a
            # reconciliação é justamente quem o grava depois do fato.
            custos[id_produto] = motor.custo_teorico_do_produto(
                cur, id_produto, id_unidade=id_unidade)
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
